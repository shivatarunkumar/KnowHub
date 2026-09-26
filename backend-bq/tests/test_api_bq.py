"""The BigQuery API end to end, against real BigQuery.

Opt-in (make test-bq): each run creates a throwaway dataset knowhub_test_<random> from
infra/gcs/bq/tables, seeds it like setup-bq does, runs real sessions through the API,
and drops the dataset. The dataset also expires on its own after a day, in case a run
is killed before it can clean up. Uploaded files go to the configured GCS bucket and are
removed when the test deletes its video.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import uuid
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from app_bq.core.bq import TABLES_DIR, get_db

from app.core.config import get_settings

pytestmark = [
    pytest.mark.bigquery,
    pytest.mark.skipif(os.environ.get("KNOWHUB_TEST_BQ") != "1", reason="needs BigQuery: run make test-bq"),
]

FILE = {"file": ("clip.mp4", b"\x00\x00\x00\x20ftypisom" + b"0" * 2048, "video/mp4")}
PASSWORD = "test-password-123"


def _create_dataset(client, project: str, name: str, location: str) -> None:
    from google.cloud import bigquery

    dataset = bigquery.Dataset(f"{project}.{name}")
    dataset.location = location
    dataset.default_table_expiration_ms = 24 * 3600 * 1000
    dataset.labels = {"app": "knowhub", "purpose": "test"}
    client.create_dataset(dataset)

    def create(path: Path) -> None:
        spec = json.loads(path.read_text(encoding="utf-8"))
        table = bigquery.Table(
            f"{project}.{name}.{path.stem}",
            schema=[bigquery.SchemaField.from_api_repr(field) for field in spec["schema"]],
        )
        table.clustering_fields = spec["clustering"]
        if "time_partitioning" in spec:
            table.time_partitioning = bigquery.TimePartitioning(
                type_=spec["time_partitioning"]["type"], field=spec["time_partitioning"]["field"]
            )
        client.create_table(table)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(create, sorted(TABLES_DIR.glob("*.json"))))

    sys.path.insert(0, str(TABLES_DIR.parent))
    import setup_bq

    for filename, table in setup_bq.SEEDS.items():
        columns, rows = setup_bq.parse_seed(setup_bq.SEEDS_DIR / filename)
        client.query_and_wait(setup_bq.merge_sql(f"{project}.{name}.{table}", columns, rows))


@pytest.fixture(scope="module")
def dataset():
    from google.cloud import bigquery

    settings = get_settings()
    project, location = settings.bq_db_project_id, settings.bq_db_location
    name = f"knowhub_test_{uuid.uuid4().hex[:8]}"
    client = bigquery.Client(project=project, location=location)
    _create_dataset(client, project, name, location)

    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("BQ_DB_DATASET", name)
        get_settings.cache_clear()
        get_db.cache_clear()
        try:
            yield name
        finally:
            client.delete_dataset(f"{project}.{name}", delete_contents=True, not_found_ok=True)
            get_settings.cache_clear()
            get_db.cache_clear()


@contextlib.asynccontextmanager
async def client_for(email: str | None = None) -> AsyncIterator[tuple[httpx.AsyncClient, dict]]:
    """A browser: anonymous, or signed in as a newly registered `email`."""
    from app_bq.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=120
    ) as client:
        me: dict = {}
        if email:
            response = await client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": PASSWORD, "display_name": email.split("@")[0]},
            )
            assert response.status_code == 201, response.text
            me = response.json()
        yield client, me


async def test_health_reports_bigquery(dataset):
    async with client_for() as (client, _):
        body = (await client.get("/api/v1/health")).json()
    database = body["checks"]["database"]
    assert database["backend"] == "bigquery" and database["missing"] == [] and database["topics"] == 25


async def test_topics_and_teams_are_seeded(dataset):
    async with client_for() as (client, _):
        topics = (await client.get("/api/v1/topics")).json()
        teams = (await client.get("/api/v1/teams")).json()
    assert len(topics) == 25 and topics[0]["slug"] == "gcp" and topics[0]["video_count"] == 0
    assert len(teams) == 18


async def test_accounts(dataset):
    suffix = uuid.uuid4().hex[:6]
    email = f"acct-{suffix}@knowhub.io"
    async with client_for(email) as (client, me):
        assert me["handle"] == f"acct-{suffix}"
        duplicate = await client.post(
            "/api/v1/auth/register", json={"email": email, "password": PASSWORD, "display_name": "again"}
        )
        assert duplicate.status_code == 409 and duplicate.json()["detail"]["field"] == "email"

        assert (await client.get("/api/v1/auth/me")).json()["id"] == me["id"]
        wrong = await client.post("/api/v1/auth/login", json={"email": email, "password": "not-it-at-all"})
        assert wrong.status_code == 401

        old_refresh = client.cookies.get("knowhub_refresh")
        assert (await client.post("/api/v1/auth/refresh")).status_code == 200
        # replaying the old refresh token ends every session
        async with client_for() as (replay, _):
            replay.cookies.set("knowhub_refresh", old_refresh, path="/api/v1/auth")
            assert (await replay.post("/api/v1/auth/refresh")).status_code == 401
        assert (await client.post("/api/v1/auth/refresh")).status_code == 401

        assert (
            await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        ).status_code == 200
        assert (await client.post("/api/v1/auth/logout")).status_code == 204


async def test_video_lifecycle(dataset):
    suffix = uuid.uuid4().hex[:6]
    async with (
        client_for(f"owner-{suffix}@knowhub.io") as (owner, me),
        client_for(f"mate-{suffix}@knowhub.io") as (mate, mate_me),
        client_for() as (anon, _),
    ):
        created = await owner.post(
            "/api/v1/videos/upload",
            data={
                "title": "Fixing BQ slots",
                "category": "bug_fix",
                "topic_slug": "bigquery",
                "team_slug": "payments",
            },
            files=FILE,
        )
        assert created.status_code == 201, created.text
        video_id = created.json()["id"]
        try:
            feed = (
                await anon.get(
                    "/api/v1/videos/feed", params={"topic": ["bigquery", "gke"], "team": "payments"}
                )
            ).json()
            assert [v["id"] for v in feed["items"]] == [video_id]
            assert (await anon.get("/api/v1/videos/feed", params={"team": "fraud"})).json()["items"] == []

            stream = await anon.get(f"/api/v1/videos/{video_id}/stream", headers={"range": "bytes=0-9"})
            assert stream.status_code == 206 and len(stream.content) == 10

            # counts are computed from rows, not stored
            assert (await mate.put(f"/api/v1/videos/{video_id}/reaction", json={"value": 1})).json()[
                "like_count"
            ] == 1
            await mate.post(f"/api/v1/videos/{video_id}/view")
            comment = (
                await mate.post(
                    f"/api/v1/videos/{video_id}/comments", json={"body": f"thanks @{me['handle']}"}
                )
            ).json()
            await owner.post(
                f"/api/v1/videos/{video_id}/comments", json={"body": "np", "parent_id": comment["id"]}
            )
            await owner.put(f"/api/v1/comments/{comment['id']}/reaction")
            watched = (await anon.get(f"/api/v1/videos/{video_id}")).json()
            assert (watched["like_count"], watched["view_count"], watched["comment_count"]) == (1, 1, 2)
            thread = (await anon.get(f"/api/v1/videos/{video_id}/comments")).json()
            assert thread[0]["like_count"] == 1 and len(thread[0]["replies"]) == 1

            shared = await owner.post(
                f"/api/v1/videos/{video_id}/share", json={"to_user_ids": [mate_me["id"]]}
            )
            assert shared.json() == {"shared_with": 1}
            assert (await mate.get("/api/v1/shared-with-me")).json()[0]["video_id"] == video_id

            patched = await owner.patch(
                f"/api/v1/videos/{video_id}",
                json={
                    "visibility": "restricted",
                    "viewer_ids": [mate_me["id"]],
                    "comments_enabled": False,
                    "links": [{"kind": "jira", "url": "https://jira.example.com/KH-1"}],
                },
            )
            assert patched.status_code == 200 and patched.json()["links"][0]["kind"] == "jira"
            assert (await anon.get(f"/api/v1/videos/{video_id}")).status_code == 404
            assert (await mate.get(f"/api/v1/videos/{video_id}")).status_code == 200
            assert (
                await mate.post(f"/api/v1/videos/{video_id}/comments", json={"body": "hi"})
            ).status_code == 403

            channel = (await owner.get(f"/api/v1/channels/{me['handle']}")).json()
            assert channel["is_me"] and channel["videos"][0]["allowed_viewers"][0]["id"] == mate_me["id"]
        finally:
            assert (await owner.delete(f"/api/v1/videos/{video_id}")).status_code == 204
        assert (await mate.get(f"/api/v1/videos/{video_id}")).status_code == 404

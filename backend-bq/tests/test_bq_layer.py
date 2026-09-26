"""The BigQuery data layer, without talking to BigQuery: SQL, parameters, batching."""

import uuid
from datetime import UTC, datetime

import pytest
from app_bq.core import bq


@pytest.fixture
def db():
    database = bq.BigQueryDB.__new__(bq.BigQueryDB)
    database.project, database.dataset, database.location = "proj", "ds", "europe-west2"
    database._client = None
    return database


def test_table_names_expand_and_typos_fail(db):
    assert db.expand("SELECT * FROM {users}") == "SELECT * FROM `proj.ds.users`"
    with pytest.raises(bq.BigQueryError, match="unknown table"):
        db.expand("SELECT * FROM {user}")


def test_uuid_columns_come_back_as_uuids():
    value = uuid.uuid4()
    assert bq._from_bq("owner_id", str(value)) == value
    assert bq._from_bq("session_id", "abc") == "abc"
    assert bq._from_bq("handle", str(value)) == str(value)


def test_params_are_typed_from_python_values():
    assert bq.make_param("n", 3).type_ == "INT64"
    assert bq.make_param("b", True).type_ == "BOOL"
    assert bq.make_param("t", datetime.now(UTC)).type_ == "TIMESTAMP"
    assert bq.make_param("id", uuid.uuid4()).value.count("-") == 4
    assert bq.make_param("ids", [uuid.uuid4()]).array_type == "STRING"
    assert bq.make_param("none", bq.null("TIMESTAMP")).type_ == "TIMESTAMP"


def test_inserts_are_typed_from_the_table_schema():
    statement = bq.insert_statement(
        "upload_events", [{"id": uuid.uuid4(), "metadata": {"a": 1}, "user_id": None}]
    )
    assert "PARSE_JSON(@r0_metadata)" in statement.sql
    assert statement.params["r0_user_id"].type == "STRING"
    assert statement.table == "upload_events"


def test_unknown_columns_are_refused():
    with pytest.raises(bq.BigQueryError, match="not in infra/gcs/bq/tables"):
        bq.insert_statement("users", [{"nickname": "x"}])


def test_update_stamps_updated_at_like_the_postgres_trigger():
    statement = bq.update_statement("videos", {"id": uuid.uuid4()}, {"title": "x"})
    assert "updated_at = CURRENT_TIMESTAMP()" in statement.sql
    no_column = bq.update_statement("refresh_tokens", {"id": uuid.uuid4()}, {"revoked_at": bq.NOW})
    assert "updated_at" not in no_column.sql and "revoked_at = CURRENT_TIMESTAMP()" in no_column.sql


def test_where_handles_null_and_lists_and_refuses_everything():
    condition, params = bq.where_clause(
        "video_viewers", {"video_id": uuid.uuid4(), "user_id": [uuid.uuid4()]}
    )
    assert "user_id IN UNNEST(@w_user_id)" in condition
    assert bq.where_clause("refresh_tokens", {"revoked_at": None})[0] == "revoked_at IS NULL"
    with pytest.raises(bq.BigQueryError, match="no WHERE"):
        bq.where_clause("users", {})


def test_written_table_is_found_for_every_kind_of_dml():
    assert bq.written_table("INSERT INTO {users} (id) VALUES (@id)") == "users"
    assert bq.written_table("  UPDATE {videos} SET x = 1") == "videos"
    assert bq.written_table("DELETE FROM {comments} WHERE id = @id") == "comments"
    assert bq.written_table("MERGE {video_reactions} AS t USING ...") == "video_reactions"
    assert bq.written_table("SELECT 1") is None


def test_batch_merges_inserts_and_keeps_per_table_order(db):
    batch = db.batch()
    video_id = uuid.uuid4()
    batch.delete("video_links", {"video_id": video_id})
    batch.insert(
        "video_links", {"id": uuid.uuid4(), "video_id": video_id, "kind": "jira", "url": "https://a"}
    )
    batch.insert("video_links", {"id": uuid.uuid4(), "video_id": video_id, "kind": "pr", "url": "https://b"})
    batch.update("videos", {"id": video_id}, {"title": "t"})
    batch.insert("upload_events", {"id": uuid.uuid4(), "video_id": video_id, "event": "edited"})

    chains = batch.chains()
    by_table = {chain[0].table: chain for chain in chains}
    assert set(by_table) == {"video_links", "videos", "upload_events"}
    links = by_table["video_links"]
    # the delete runs first, then ONE insert carrying both rows
    assert links[0].sql.startswith("DELETE") and links[1].sql.startswith("INSERT") and len(links) == 2
    assert "@r1_url" in links[1].sql


def test_batch_reads_rows_at_commit_time(db):
    batch = db.batch()
    row = {"id": uuid.uuid4(), "status": "UPLOADING"}
    batch.insert("videos", row)
    row["status"] = "READY"
    statement = batch.compiled()[0]
    assert statement.params["r0_status"].value == "READY"


def test_batch_execute_needs_a_table(db):
    with pytest.raises(bq.BigQueryError):
        db.batch().execute("SELECT 1")


def test_rows_missing_a_defaulted_column_use_default():
    statement = bq.insert_statement(
        "analytics_events",
        [
            {"id": "a", "event_type": "video_view", "payload": {"x": 1}},
            {"id": "b", "event_type": "video_view"},
        ],
    )
    assert "DEFAULT" in statement.sql.split("VALUES")[1]

"""Creating, listing, reading and managing videos, on BigQuery.

Same rules as app/services/video.py (who may see what, what the owner can change, the
audit trail). Two differences:

- view, like and comment counts are computed when read, from analytics_events,
  video_reactions and comments, instead of being counters on the videos row. BigQuery
  allows only a couple of concurrent updates per table, so a counter everyone increments
  would conflict; counting rows that are only ever appended never does.
- the few facts the player and thumbnails need on every range request are cached for a
  short while (media_paths), because each lookup is a BigQuery round trip.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

from app.models.video import CATEGORIES, LINK_KINDS, VISIBILITIES
from app.services.video import PAGE_SIZE, VideoError, raw_object_name, validate_metadata
from app_bq.core.bq import Batch, BigQueryDB, Row, Typed, uuids

__all__ = ["VideoError", "raw_object_name", "validate_metadata"]

log = logging.getLogger("knowhub.video")

MEDIA_CACHE_SECONDS = 30

# Counts computed on read (see the module docstring). With @scoped, only @scope_ids are
# counted, so a single watch page doesn't count every video there is. (A flag rather than
# "@scope_ids IS NULL": BigQuery sends a NULL array parameter as an empty one.)
COUNTS = """
likes AS (
  SELECT video_id, COUNTIF(value = 1) AS n FROM {video_reactions}
  WHERE NOT @scoped OR video_id IN UNNEST(@scope_ids) GROUP BY video_id),
comment_totals AS (
  SELECT video_id, COUNT(*) AS n FROM {comments}
  WHERE deleted_at IS NULL AND (NOT @scoped OR video_id IN UNNEST(@scope_ids)) GROUP BY video_id),
views AS (
  SELECT video_id, COUNT(*) AS n FROM {analytics_events}
  WHERE event_type = 'video_view' AND (NOT @scoped OR video_id IN UNNEST(@scope_ids)) GROUP BY video_id)
"""

BASE = (
    "WITH "
    + COUNTS
    + """
SELECT v.*,
       u.display_name AS owner_display_name, u.handle AS owner_handle,
       tp.slug AS topic_slug, tp.name AS topic_name,
       tm.slug AS team_slug, tm.name AS team_name,
       COALESCE(vw.n, 0) AS view_count, COALESCE(l.n, 0) AS like_count, COALESCE(c.n, 0) AS comment_count,
       vv.user_id IS NOT NULL AS viewer_allowed
FROM {videos} AS v
JOIN {users} AS u ON u.id = v.owner_id
LEFT JOIN {topics} AS tp ON tp.id = v.primary_topic_id
LEFT JOIN {teams} AS tm ON tm.id = v.team_id
LEFT JOIN likes AS l ON l.video_id = v.id
LEFT JOIN comment_totals AS c ON c.video_id = v.id
LEFT JOIN views AS vw ON vw.video_id = v.id
LEFT JOIN {video_viewers} AS vv ON vv.video_id = v.id AND vv.user_id = @viewer_id
WHERE v.deleted_at IS NULL
"""
)

# Which videos this person may see in a list: everyone's internal ones, their own, and
# the restricted ones they were added to. Unlisted videos are link-only.
VISIBLE = """(
  v.visibility = 'internal'
  OR (@viewer_id IS NOT NULL AND v.owner_id = @viewer_id)
  OR (v.visibility = 'restricted' AND vv.user_id IS NOT NULL)
)"""


def _viewer_params(viewer: Row | None, scope_ids: list | None = None) -> dict:
    return {
        "viewer_id": Typed(str(viewer.id) if viewer else None, "STRING"),
        "scoped": scope_ids is not None,
        "scope_ids": Typed(uuids(scope_ids or []), "ARRAY<STRING>"),
    }


def to_out(row: Row) -> dict:
    out = dict(row)
    out["has_thumbnail"] = bool(row.get("thumbnail_path"))
    out.pop("viewer_allowed", None)
    return out


# ------------------------------------------------------------------ lookups
async def team_by_slug(db: BigQueryDB, slug: str | None) -> Row | None:
    if not slug:
        return None
    team = await db.row("SELECT * FROM {teams} WHERE slug = @slug AND is_active LIMIT 1", slug=slug)
    if team is None:
        raise VideoError(f"Unknown team '{slug}'", field="team_slug")
    return team


async def topic_by_slug(db: BigQueryDB, slug: str | None) -> Row | None:
    if not slug:
        return None
    topic = await db.row("SELECT * FROM {topics} WHERE slug = @slug AND is_active LIMIT 1", slug=slug)
    if topic is None:
        raise VideoError(f"Unknown topic '{slug}'", field="topic_slug")
    return topic


async def topic_and_team(
    db: BigQueryDB, topic_slug: str | None, team_slug: str | None
) -> tuple[Row | None, Row | None]:
    """Both lookups at once: they are independent, so there's no reason to wait twice."""
    return await asyncio.gather(topic_by_slug(db, topic_slug), team_by_slug(db, team_slug))


def record_event(
    batch: Batch, video_id: uuid.UUID, user_id: uuid.UUID | None, event: str, **metadata
) -> None:
    """Append to the upload audit trail (who did what to this video, and when)."""
    batch.insert(
        "upload_events",
        {
            "id": uuid.uuid4(),
            "video_id": video_id,
            "user_id": user_id,
            "event": event,
            "metadata": metadata,
            "created_at": datetime.now(UTC),
        },
    )


def save_resources(batch: Batch, video_id: uuid.UUID, links: list, snippets: list) -> None:
    """Attach the optional links and code snippets from the upload form."""
    now = datetime.now(UTC)
    for link in links:
        batch.insert(
            "video_links",
            {
                "id": uuid.uuid4(),
                "video_id": video_id,
                "kind": link.kind if link.kind in LINK_KINDS else "other",
                "url": link.url,
                "label": link.label or None,
                "created_at": now,
            },
        )
    for order, snippet in enumerate(snippets):
        batch.insert(
            "video_snippets",
            {
                "id": uuid.uuid4(),
                "video_id": video_id,
                "title": snippet.title or None,
                "language": snippet.language,
                "code": snippet.code,
                "sort_order": order,
                "created_at": now,
            },
        )


async def resources_for(db: BigQueryDB, video_id: uuid.UUID) -> dict:
    links, snippets = await asyncio.gather(
        db.rows("SELECT * FROM {video_links} WHERE video_id = @id ORDER BY created_at", id=video_id),
        db.rows("SELECT * FROM {video_snippets} WHERE video_id = @id ORDER BY sort_order", id=video_id),
    )
    return {"links": links, "snippets": snippets}


# ------------------------------------------------------------------ media cache
_media: dict[tuple[uuid.UUID, uuid.UUID | None], tuple[float, dict]] = {}


def remember_media(video: dict, viewer: Row | None) -> None:
    """What stream and thumbnail need, for a video this viewer is allowed to watch."""
    key = (video["id"], viewer.id if viewer else None)
    _media[key] = (
        time.monotonic() + MEDIA_CACHE_SECONDS,
        {"raw_gcs_path": video.get("raw_gcs_path"), "thumbnail_path": video.get("thumbnail_path")},
    )


def forget_media(video_id: uuid.UUID) -> None:
    """After anything that changes who may watch a video or where its files are."""
    for key in [k for k in _media if k[0] == video_id]:
        _media.pop(key, None)


async def media_paths(db: BigQueryDB, video_id: uuid.UUID, viewer: Row | None) -> dict:
    """Like get_video, but cached: the player asks for byte ranges many times a minute."""
    cached = _media.get((video_id, viewer.id if viewer else None))
    if cached and cached[0] > time.monotonic():
        return cached[1]
    video = await get_video(db, video_id, viewer, with_resources=False)
    return _media[(video_id, viewer.id if viewer else None)][1] if video else {}


# ------------------------------------------------------------------ queries
def may_watch(video: Row, viewer: Row | None) -> bool:
    """Whether this person may open the watch page for a single video."""
    if viewer is not None and (viewer.id == video.owner_id or viewer.role == "admin"):
        return True
    if video.visibility in ("internal", "unlisted"):
        return True
    if video.visibility == "restricted" and viewer is not None:
        return bool(video.viewer_allowed)
    return False  # private


async def list_feed(
    db: BigQueryDB,
    *,
    video_type: str | None = None,
    topic_slugs: list[str] | None = None,
    team_slug: str | None = None,
    owner_id: uuid.UUID | None = None,
    viewer: Row | None = None,
    limit: int = PAGE_SIZE,
) -> list[dict]:
    """Newest first, only what this viewer may see."""
    sql = BASE + f" AND v.status = 'READY' AND {VISIBLE}"
    params = _viewer_params(viewer)
    if video_type:
        sql += " AND v.type = @video_type"
        params["video_type"] = video_type
    if topic_slugs:
        # any of them: a video has one primary topic, so requiring all would match nothing
        sql += " AND tp.slug IN UNNEST(@topic_slugs)"
        params["topic_slugs"] = list(topic_slugs)
    if team_slug:
        sql += " AND tm.slug = @team_slug"
        params["team_slug"] = team_slug
    if owner_id:
        sql += " AND v.owner_id = @owner_id"
        params["owner_id"] = owner_id
    sql += " ORDER BY v.published_at DESC NULLS LAST LIMIT @limit"
    params["limit"] = limit

    items = [to_out(row) for row in await db.rows(sql, **params)]
    for item in items:
        remember_media(item, viewer)  # the grid's thumbnails are requested next
    log.debug(
        "  feed: type=%s topics=%s team=%s owner=%s viewer=%s -> %d video(s)",
        video_type or "any",
        topic_slugs or "any",
        team_slug or "any",
        owner_id or "any",
        viewer.handle if viewer else "anonymous",
        len(items),
    )
    return items


async def get_video(
    db: BigQueryDB, video_id: uuid.UUID, viewer: Row | None, *, with_resources: bool = True
) -> dict:
    query = db.rows(BASE + " AND v.id = @video_id", video_id=video_id, **_viewer_params(viewer, [video_id]))
    if with_resources:
        # links and snippets in parallel with the video itself: one round trip, not three
        rows, resources = await asyncio.gather(query, resources_for(db, video_id))
    else:
        rows, resources = await query, {}
    if not rows:
        log.debug("  video %s: no such row (or deleted)", video_id)
        raise VideoError("Video not found", status_code=404)
    video = rows[0]
    if not may_watch(video, viewer):
        # a 404 rather than a 403 on purpose: a stranger learns nothing about what exists
        log.info(
            "  video %s is %s; %s may not watch it, answering 404",
            video_id,
            video.visibility,
            viewer.handle if viewer else "an anonymous visitor",
        )
        raise VideoError("Video not found", status_code=404)
    if video.status != "READY" and (viewer is None or viewer.id != video.owner_id):
        log.debug("  video %s is %s, not READY", video_id, video.status)
        raise VideoError("This video is still processing", status_code=409)
    out = {**to_out(video), **resources}
    remember_media(out, viewer)
    return out


# ------------------------------------------------------ channel management
async def get_owned(db: BigQueryDB, video_id: uuid.UUID, user: Row) -> Row:
    video = await db.row("SELECT * FROM {videos} WHERE id = @id AND deleted_at IS NULL", id=video_id)
    if video is None:
        raise VideoError("Video not found", status_code=404)
    if video.owner_id != user.id and user.role != "admin":
        raise VideoError("This isn't your video", status_code=403)
    return video


async def viewers_for(db: BigQueryDB, video_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
    """The allow-list behind visibility='restricted', per video."""
    if not video_ids:
        return {}
    rows = await db.rows(
        """
        SELECT vv.video_id, u.id, u.display_name, u.handle
        FROM {video_viewers} AS vv JOIN {users} AS u ON u.id = vv.user_id
        WHERE vv.video_id IN UNNEST(@ids)
        ORDER BY u.display_name
        """,
        ids=uuids(video_ids),
    )
    people: dict[uuid.UUID, list[dict]] = {video_id: [] for video_id in video_ids}
    for row in rows:
        people[row.video_id].append({"id": row.id, "display_name": row.display_name, "handle": row.handle})
    return people


async def set_viewers(
    db: BigQueryDB,
    batch: Batch,
    video: Row,
    user_ids: list[uuid.UUID],
    added_by: Row,
    current: set[uuid.UUID],
) -> None:
    """Replace the allow-list (`current` is what it holds now). The owner is always
    allowed, so they never appear in it."""
    wanted = {uid for uid in user_ids if uid != video.owner_id}
    if wanted:
        found = {
            row.id
            for row in await db.rows(
                "SELECT id FROM {users} WHERE id IN UNNEST(@ids) AND is_active AND deleted_at IS NULL",
                ids=uuids(wanted),
            )
        }
        if missing := wanted - found:
            raise VideoError(f"{len(missing)} of those people no longer have an account")
        wanted = found

    if removed := current - wanted:
        batch.delete("video_viewers", {"video_id": video.id, "user_id": list(removed)})
    now = datetime.now(UTC)
    for user_id in wanted - current:
        batch.insert(
            "video_viewers",
            {"video_id": video.id, "user_id": user_id, "added_by": added_by.id, "created_at": now},
        )


def replace_resources(batch: Batch, video: Row, links, snippets) -> None:
    """Swap the links and snippets for the ones the owner just saved."""
    if links is not None:
        batch.delete("video_links", {"video_id": video.id})
    if snippets is not None:
        batch.delete("video_snippets", {"video_id": video.id})
    save_resources(batch, video.id, links or [], snippets or [])


async def apply_patch(db: BigQueryDB, batch: Batch, video: Row, user: Row, patch) -> list[str]:
    """Queue the owner's edits on `batch`. Returns the names of the fields that changed."""
    changed: list[str] = []
    values: dict = {}

    if patch.title is not None and patch.title.strip() != video.title:
        values["title"] = patch.title.strip()
        changed.append("title")
    if patch.description is not None:
        description = patch.description.strip() or None
        if description != video.description:
            values["description"] = description
            changed.append("description")
    if patch.category is not None and patch.category != video.category:
        if patch.category not in CATEGORIES:
            raise VideoError(f"Unknown category '{patch.category}'", field="category")
        values["category"] = patch.category
        changed.append("category")
    if patch.topic_slug is not None or patch.team_slug is not None:
        topic, team = await topic_and_team(db, patch.topic_slug or None, patch.team_slug or None)
        if patch.topic_slug is not None and (topic.id if topic else None) != video.primary_topic_id:
            values["primary_topic_id"] = topic.id if topic else None
            changed.append("topic")
        if patch.team_slug is not None and (team.id if team else None) != video.team_id:
            values["team_id"] = team.id if team else None
            changed.append("team")
    if patch.visibility is not None and patch.visibility != video.visibility:
        if patch.visibility not in VISIBILITIES:
            raise VideoError(f"Unknown visibility '{patch.visibility}'", field="visibility")
        values["visibility"] = patch.visibility
        changed.append("visibility")
    if patch.comments_enabled is not None and patch.comments_enabled != video.comments_enabled:
        values["comments_enabled"] = patch.comments_enabled
        changed.append("comments")
    if patch.viewer_ids is not None:
        before = {
            row.user_id
            for row in await db.rows("SELECT user_id FROM {video_viewers} WHERE video_id = @id", id=video.id)
        }
        await set_viewers(db, batch, video, patch.viewer_ids, user, before)
        if before != {uid for uid in patch.viewer_ids if uid != video.owner_id}:
            changed.append("people")
    if patch.links is not None or patch.snippets is not None:
        replace_resources(batch, video, patch.links, patch.snippets)
        changed.append("resources")

    if values:
        batch.update("videos", {"id": video.id}, values)
        video.update(values)
    if changed:
        log.info("video %s edited by %s: %s", video.id, user.handle, ", ".join(changed))
        record_event(batch, video.id, user.id, "edited", fields=changed)
        forget_media(video.id)
    else:
        log.debug("  video %s: nothing to change", video.id)
    if "visibility" in changed:
        record_event(batch, video.id, user.id, "visibility_changed", visibility=video.visibility)
    if "comments" in changed:
        record_event(batch, video.id, user.id, "comments_changed", enabled=video.comments_enabled)
    return changed


def soft_delete(batch: Batch, video: Row, user: Row) -> list[str]:
    """Take the video down. The row stays for the audit trail; the caller removes the files."""
    batch.update("videos", {"id": video.id}, {"deleted_at": datetime.now(UTC)})
    record_event(batch, video.id, user.id, "deleted")
    forget_media(video.id)
    return [path for path in (video.raw_gcs_path, video.thumbnail_path) if path]


async def channel_for(db: BigQueryDB, handle: str, viewer: Row | None) -> dict:
    """A user's channel: their profile and their videos. The owner sees everything,
    including drafts, failed uploads and hidden videos."""
    owner = await db.row(
        "SELECT * FROM {users} WHERE handle = @handle AND deleted_at IS NULL LIMIT 1",
        handle=handle.lstrip("@").lower(),
    )
    if owner is None:
        raise VideoError("Channel not found", status_code=404)
    is_owner = viewer is not None and viewer.id == owner.id

    sql = BASE + " AND v.owner_id = @owner_id"
    if is_owner:
        sql += " ORDER BY v.created_at DESC"
    else:
        # other people see published videos only, and never the link-only ones
        sql += f" AND v.status = 'READY' AND v.visibility != 'unlisted' AND {VISIBLE}"
        sql += " ORDER BY v.published_at DESC NULLS LAST"
    videos = [to_out(row) for row in await db.rows(sql, owner_id=owner.id, **_viewer_params(viewer))]
    for item in videos:
        remember_media(item, viewer)  # everything listed here, this viewer may watch
    if is_owner:
        people = await viewers_for(db, [item["id"] for item in videos])
        for item in videos:
            item["allowed_viewers"] = people.get(item["id"], [])

    return {
        "id": owner.id,
        "handle": owner.handle,
        "display_name": owner.display_name,
        "bio": owner.bio,
        "avatar_url": owner.avatar_url,
        "joined_at": owner.created_at,
        "is_me": is_owner,
        "video_count": len(videos),
        "total_views": sum(item["view_count"] for item in videos),
        "videos": videos,
    }

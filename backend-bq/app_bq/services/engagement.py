"""Likes, comments, in-app sharing and views, on BigQuery.

Same rules as app/services/engagement.py. Counts are never stored: likes are counted from
video_reactions, comment likes from comment_reactions, and views from analytics_events
(one row per view). Appending a row can't conflict with anyone else doing the same,
where incrementing a shared counter would.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from app.services.engagement import mentioned_handles
from app_bq.core.bq import Batch, BigQueryDB, Row, Typed, uuids
from app_bq.services.video import VideoError

log = logging.getLogger("knowhub.engagement")


def notify(
    batch: Batch,
    *,
    user_id: uuid.UUID,
    type: str,
    video_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    **payload,
) -> None:
    """Add to the recipient's in-app inbox. Never notify someone about their own action."""
    if actor_id is not None and actor_id == user_id:
        return
    batch.insert(
        "notifications",
        {
            "id": uuid.uuid4(),
            "user_id": user_id,
            "type": type,
            "video_id": video_id,
            "actor_id": actor_id,
            "payload": payload,
            "created_at": datetime.now(UTC),
        },
    )


async def notify_mentions(
    db: BigQueryDB,
    batch: Batch,
    *,
    body: str,
    video: Row,
    author: Row,
    comment_id: uuid.UUID,
    already_notified: set[uuid.UUID] | None = None,
) -> None:
    """Tell everyone named in the comment, except the author and anyone already told."""
    handles = mentioned_handles(body)
    if not handles:
        return
    people = await db.rows(
        "SELECT id FROM {users} WHERE handle IN UNNEST(@handles) AND is_active AND deleted_at IS NULL",
        handles=handles,
    )
    skip = already_notified or set()
    for person in people:
        if person.id == author.id or person.id in skip:
            continue
        notify(
            batch,
            user_id=person.id,
            type="comment_mention",
            video_id=video.id,
            actor_id=author.id,
            comment_id=str(comment_id),
            title=video.title,
            preview=body[:120],
        )


# ------------------------------------------------------------------ reactions
COUNTS_SQL = """
SELECT COUNTIF(value = 1) AS likes, COUNTIF(value = -1) AS dislikes,
       COALESCE(MAX(IF(user_id = @user_id, value, NULL)), 0) AS mine
FROM {video_reactions} WHERE video_id = @video_id
"""


async def counts_for(db: BigQueryDB, video_id: uuid.UUID, user: Row | None = None) -> tuple[int, int, int]:
    """(likes, dislikes, this user's reaction) in one query."""
    row = await db.row(COUNTS_SQL, video_id=video_id, user_id=Typed(str(user.id) if user else None, "STRING"))
    return row.likes, row.dislikes, row.mine


async def set_reaction(db: BigQueryDB, video: Row, user: Row, value: int) -> tuple[int, int, int]:
    """value: 1 like, -1 dislike, 0 clears it. Returns (likes, dislikes, mine).

    One MERGE does insert-or-update, so two clicks can't leave two rows for one person."""
    if value == 0:
        await db.delete("video_reactions", {"user_id": user.id, "video_id": video.id})
    else:
        await db.execute(
            """
            MERGE {video_reactions} AS t
            USING (SELECT @user_id AS user_id, @video_id AS video_id, @value AS value) AS s
            ON t.user_id = s.user_id AND t.video_id = s.video_id
            WHEN MATCHED THEN UPDATE SET value = s.value
            WHEN NOT MATCHED THEN INSERT (user_id, video_id, value, created_at)
              VALUES (s.user_id, s.video_id, s.value, CURRENT_TIMESTAMP())
            """,
            user_id=user.id,
            video_id=video.id,
            value=value,
        )
    likes, dislikes, _ = await counts_for(db, video.id)
    log.debug("  reaction %+d by %s on video %s -> %d like(s)", value, user.handle, video.id, likes)
    return likes, dislikes, value


# ------------------------------------------------------------------ comments
COMMENTS_SQL = """
WITH likes AS (
  SELECT r.comment_id, COUNT(*) AS n, COUNTIF(r.user_id = @viewer_id) > 0 AS mine
  FROM {comment_reactions} AS r JOIN {comments} AS c ON c.id = r.comment_id
  WHERE c.video_id = @video_id GROUP BY r.comment_id)
SELECT c.*, u.display_name AS author_name, u.handle AS author_handle, v.owner_id AS uploader_id,
       COALESCE(l.n, 0) AS like_count, COALESCE(l.mine, FALSE) AS liked_by_me
FROM {comments} AS c
JOIN {users} AS u ON u.id = c.user_id
JOIN {videos} AS v ON v.id = c.video_id
LEFT JOIN likes AS l ON l.comment_id = c.id
WHERE c.video_id = @video_id AND c.deleted_at IS NULL
ORDER BY c.is_pinned DESC, c.created_at ASC
"""


async def list_comments(
    db: BigQueryDB,
    video_id: uuid.UUID,
    viewer: Row | None,
    sort: str = "top",
    edit_window_seconds: int = 60,
) -> list[dict]:
    """Top-level comments, each with its replies. Pinned first, then top or newest."""
    rows = await db.rows(
        COMMENTS_SQL, video_id=video_id, viewer_id=Typed(str(viewer.id) if viewer else None, "STRING")
    )
    by_id: dict[uuid.UUID, dict] = {}
    replies: list[dict] = []
    for c in rows:
        item = {
            "id": c.id,
            "video_id": c.video_id,
            "parent_id": c.parent_id,
            "body": c.body,
            "like_count": c.like_count,
            "is_pinned": c.is_pinned,
            "created_at": c.created_at,
            "edited_at": c.edited_at,
            "author_id": c.user_id,
            "author_name": c.author_name,
            "author_handle": c.author_handle,
            "liked_by_me": c.liked_by_me,
            "is_mine": viewer is not None and viewer.id == c.user_id,
            "is_uploader": c.user_id == c.uploader_id,
            "editable_until": c.created_at + timedelta(seconds=edit_window_seconds),
            "replies": [],
        }
        if c.parent_id is None:
            by_id[c.id] = item
        else:
            replies.append(item)

    for reply in replies:
        parent = by_id.get(reply["parent_id"])
        if parent is not None:
            parent["replies"].append(reply)

    top_level = list(by_id.values())
    if sort == "new":
        top_level.sort(key=lambda c: (not c["is_pinned"], -c["created_at"].timestamp()))
    else:
        top_level.sort(key=lambda c: (not c["is_pinned"], -c["like_count"], -c["created_at"].timestamp()))
    return top_level


async def get_comment(db: BigQueryDB, comment_id: uuid.UUID) -> Row:
    comment = await db.row("SELECT * FROM {comments} WHERE id = @id AND deleted_at IS NULL", id=comment_id)
    if comment is None:
        raise VideoError("That comment no longer exists", status_code=404)
    return comment


async def add_comment(db: BigQueryDB, video: Row, user: Row, body: str, parent_id: uuid.UUID | None) -> Row:
    if not video.comments_enabled:
        raise VideoError("Comments are turned off for this video", status_code=403)

    parent = None
    if parent_id is not None:
        parent = await db.row("SELECT * FROM {comments} WHERE id = @id", id=parent_id)
        if parent is None or parent.video_id != video.id or parent.deleted_at is not None:
            raise VideoError("That comment no longer exists", status_code=404)
        if parent.parent_id is not None:
            # one level of replies: a reply to a reply attaches to the same thread
            parent_id = parent.parent_id

    now = datetime.now(UTC)
    comment = Row(
        id=uuid.uuid4(),
        video_id=video.id,
        user_id=user.id,
        parent_id=parent_id,
        body=body.strip(),
        is_pinned=False,
        created_at=now,
        updated_at=now,
    )
    log.debug(
        "  comment by %s on video %s (%s, %d chars)",
        user.handle,
        video.id,
        "reply" if parent_id else "top level",
        len(comment.body),
    )
    batch = db.batch()
    batch.insert("comments", dict(comment))

    notified: set[uuid.UUID] = set()
    if parent is not None:
        notify(
            batch,
            user_id=parent.user_id,
            type="comment_reply",
            video_id=video.id,
            actor_id=user.id,
            comment_id=str(comment.id),
            preview=comment.body[:120],
        )
        notified.add(parent.user_id)

    await notify_mentions(
        db,
        batch,
        body=comment.body,
        video=video,
        author=user,
        comment_id=comment.id,
        already_notified=notified,
    )
    await batch.commit()
    return comment


async def edit_comment(
    db: BigQueryDB, comment_id: uuid.UUID, user: Row, body: str, window_seconds: int
) -> Row:
    """Editing is allowed for a short window after posting."""
    comment = await get_own_comment(db, comment_id, user)
    age = (datetime.now(UTC) - comment.created_at).total_seconds()
    if age > window_seconds:
        raise VideoError(
            f"Comments can only be edited for {window_seconds} seconds after posting",
            status_code=403,
        )
    changes = {"body": body.strip(), "edited_at": datetime.now(UTC)}
    await db.update("comments", {"id": comment.id}, changes)
    comment.update(changes)
    comment.like_count = await db.scalar(
        "SELECT COUNT(*) FROM {comment_reactions} WHERE comment_id = @id", id=comment.id
    )
    return comment


async def delete_comment(db: BigQueryDB, comment_id: uuid.UUID, user: Row) -> None:
    row = await db.row(
        """
        SELECT c.user_id, v.owner_id FROM {comments} AS c JOIN {videos} AS v ON v.id = c.video_id
        WHERE c.id = @id AND c.deleted_at IS NULL
        """,
        id=comment_id,
    )
    if row is None:
        raise VideoError("That comment no longer exists", status_code=404)
    if row.user_id != user.id and row.owner_id != user.id and user.role != "admin":
        raise VideoError("You can only delete your own comments", status_code=403)
    # the comment and its replies in one statement
    await db.execute(
        "UPDATE {comments} SET deleted_at = CURRENT_TIMESTAMP(), updated_at = CURRENT_TIMESTAMP() "
        "WHERE (id = @id OR parent_id = @id) AND deleted_at IS NULL",
        id=comment_id,
    )


async def get_own_comment(db: BigQueryDB, comment_id: uuid.UUID, user: Row) -> Row:
    comment = await get_comment(db, comment_id)
    if comment.user_id != user.id:
        raise VideoError("You can only edit your own comments", status_code=403)
    return comment


async def toggle_comment_like(db: BigQueryDB, comment_id: uuid.UUID, user: Row) -> tuple[int, bool]:
    row = await db.row(
        """
        SELECT c.id,
               EXISTS(SELECT 1 FROM {comment_reactions}
                      WHERE comment_id = @id AND user_id = @user_id) AS liked
        FROM {comments} AS c WHERE c.id = @id AND c.deleted_at IS NULL
        """,
        id=comment_id,
        user_id=user.id,
    )
    if row is None:
        raise VideoError("That comment no longer exists", status_code=404)

    if row.liked:
        await db.delete("comment_reactions", {"user_id": user.id, "comment_id": comment_id})
    else:
        await db.execute(
            """
            INSERT INTO {comment_reactions} (user_id, comment_id, created_at)
            SELECT @user_id, @id, CURRENT_TIMESTAMP() FROM UNNEST([1])
            WHERE NOT EXISTS (SELECT 1 FROM {comment_reactions} WHERE comment_id = @id AND user_id = @user_id)
            """,
            user_id=user.id,
            id=comment_id,
        )
    total = await db.scalar("SELECT COUNT(*) FROM {comment_reactions} WHERE comment_id = @id", id=comment_id)
    return total or 0, not row.liked


# ------------------------------------------------------------------ sharing
async def search_people(db: BigQueryDB, query: str, exclude: Row, limit: int = 8) -> list[dict]:
    rows = await db.rows(
        """
        SELECT id, display_name, handle FROM {users}
        WHERE id != @me AND is_active AND deleted_at IS NULL
          AND (STRPOS(LOWER(display_name), @q) > 0 OR STRPOS(handle, @q) > 0)
        ORDER BY display_name LIMIT @limit
        """,
        me=exclude.id,
        q=query.strip().lower(),
        limit=limit,
    )
    return [{"id": r.id, "display_name": r.display_name, "handle": r.handle} for r in rows]


async def share_video(
    db: BigQueryDB,
    video: Row,
    sender: Row,
    to_user_ids: list[uuid.UUID],
    message: str | None,
    at_seconds: int | None,
) -> int:
    recipients = await db.rows(
        "SELECT id FROM {users} WHERE id IN UNNEST(@ids) AND is_active AND deleted_at IS NULL",
        ids=uuids(to_user_ids),
    )
    if not recipients:
        raise VideoError("Choose at least one person to share with", status_code=400)

    now = datetime.now(UTC)
    batch = db.batch()
    sent = 0
    for recipient in recipients:
        if recipient.id == sender.id:
            continue
        batch.insert(
            "video_shares",
            {
                "id": uuid.uuid4(),
                "video_id": video.id,
                "from_user_id": sender.id,
                "to_user_id": recipient.id,
                "message": message or None,
                "at_seconds": at_seconds,
                "created_at": now,
            },
        )
        sent += 1
    # notifications after the shares, so each table gets one multi-row INSERT
    for recipient in recipients:
        notify(
            batch,
            user_id=recipient.id,
            type="video_shared",
            video_id=video.id,
            actor_id=sender.id,
            title=video.title,
            message=message,
            at_seconds=at_seconds,
        )
    await batch.commit()
    return sent


async def shared_with_me(db: BigQueryDB, user: Row, limit: int = 50) -> list[dict]:
    rows = await db.rows(
        """
        SELECT s.video_id, v.title, sender.display_name AS from_name, sender.handle AS from_handle,
               s.message, s.at_seconds, s.created_at
        FROM {video_shares} AS s
        JOIN {videos} AS v ON v.id = s.video_id
        JOIN {users} AS sender ON sender.id = s.from_user_id
        WHERE s.to_user_id = @me AND v.deleted_at IS NULL
        ORDER BY s.created_at DESC LIMIT @limit
        """,
        me=user.id,
        limit=limit,
    )
    return [dict(row) for row in rows]


# ------------------------------------------------------------------ views
async def count_view(db: BigQueryDB, video_id: uuid.UUID, viewer: Row | None) -> int:
    """One more view, as a row in analytics_events; the count is those rows."""
    batch = db.batch()
    batch.insert(
        "analytics_events",
        {
            "id": uuid.uuid4(),
            "event_type": "video_view",
            "video_id": video_id,
            "user_id": viewer.id if viewer else None,
            "occurred_at": datetime.now(UTC),
        },
    )
    await batch.commit()
    return await db.scalar(
        "SELECT COUNT(*) FROM {analytics_events} WHERE event_type = 'video_view' AND video_id = @id",
        id=video_id,
    )

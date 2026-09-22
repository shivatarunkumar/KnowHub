"""Likes, comments and in-app sharing."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.engagement import Comment, CommentReaction, Notification, VideoReaction, VideoShare
from app.models.user import User
from app.models.video import Video
from app.services.video import VideoError

log = logging.getLogger("knowhub.engagement")

# @tarun.nagula14 — same shape as the handle column's CHECK constraint.
# The lookbehind keeps email addresses out: in "name@example.com" the @ follows a letter.
MENTION_RE = re.compile(r"(?<![\w.])@([a-z0-9][a-z0-9_.-]{2,29})")


def mentioned_handles(body: str) -> list[str]:
    """Handles written as @name in a comment, in order, without duplicates."""
    seen: list[str] = []
    for handle in MENTION_RE.findall(body.lower()):
        handle = handle.rstrip(".-_")  # trailing punctuation isn't part of the handle
        if len(handle) >= 3 and handle not in seen:
            seen.append(handle)
    return seen


async def notify_mentions(
    session: AsyncSession,
    *,
    body: str,
    video: Video,
    author: User,
    comment_id: uuid.UUID,
    already_notified: set[uuid.UUID] | None = None,
) -> None:
    """Tell everyone named in the comment, except the author and anyone who already got
    a reply notification for it."""
    handles = mentioned_handles(body)
    if not handles:
        return
    people = (
        await session.scalars(
            select(User).where(User.handle.in_(handles), User.is_active, User.deleted_at.is_(None))
        )
    ).all()
    skip = already_notified or set()
    for person in people:
        if person.id == author.id or person.id in skip:
            continue
        notify(
            session,
            user_id=person.id,
            type="comment_mention",
            video_id=video.id,
            actor_id=author.id,
            comment_id=str(comment_id),
            title=video.title,
            preview=body[:120],
        )


def notify(
    session: AsyncSession,
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
    session.add(
        Notification(
            user_id=user_id,
            type=type,
            video_id=video_id,
            actor_id=actor_id,
            payload=payload,
            created_at=datetime.now(UTC),
        )
    )


# ------------------------------------------------------------------ reactions
async def counts_for(session: AsyncSession, video_id: uuid.UUID) -> tuple[int, int]:
    rows = await session.execute(
        select(VideoReaction.value, func.count())
        .where(VideoReaction.video_id == video_id)
        .group_by(VideoReaction.value)
    )
    tally = dict(rows.all())
    return tally.get(1, 0), tally.get(-1, 0)


async def set_reaction(session: AsyncSession, video: Video, user: User, value: int) -> tuple[int, int, int]:
    """value: 1 like, -1 dislike, 0 clears it. Returns (likes, dislikes, mine)."""
    existing = await session.get(VideoReaction, {"user_id": user.id, "video_id": video.id})

    if value == 0:
        if existing:
            await session.delete(existing)
    elif existing:
        existing.value = value
    else:
        session.add(
            VideoReaction(user_id=user.id, video_id=video.id, value=value, created_at=datetime.now(UTC))
        )
    await session.flush()

    likes, dislikes = await counts_for(session, video.id)
    log.debug("  reaction %+d by %s on video %s -> %d like(s)", value, user.handle, video.id, likes)
    # videos.like_count is the denormalised number shown on cards and feeds
    await session.execute(update(Video).where(Video.id == video.id).values(like_count=likes))
    await session.commit()
    return likes, dislikes, value


async def my_reaction(session: AsyncSession, video_id: uuid.UUID, user: User | None) -> int:
    if user is None:
        return 0
    row = await session.get(VideoReaction, {"user_id": user.id, "video_id": video_id})
    return row.value if row else 0


# ------------------------------------------------------------------ comments
async def list_comments(
    session: AsyncSession,
    video_id: uuid.UUID,
    viewer: User | None,
    sort: str = "top",
    edit_window_seconds: int = 60,
) -> list[dict]:
    """Top-level comments, each with its replies. Pinned first, then top or newest."""
    rows = await session.execute(
        select(Comment, User.display_name, User.handle, Video.owner_id)
        .join(User, User.id == Comment.user_id)
        .join(Video, Video.id == Comment.video_id)
        .where(Comment.video_id == video_id, Comment.deleted_at.is_(None))
        .order_by(Comment.is_pinned.desc(), Comment.created_at.asc())
    )
    liked: set[uuid.UUID] = set()
    if viewer is not None:
        liked = set(
            (
                await session.scalars(
                    select(CommentReaction.comment_id).where(CommentReaction.user_id == viewer.id)
                )
            ).all()
        )

    by_id: dict[uuid.UUID, dict] = {}
    replies: list[dict] = []
    for comment, name, handle, uploader_id in rows:
        item = {
            "id": comment.id,
            "video_id": comment.video_id,
            "parent_id": comment.parent_id,
            "body": comment.body,
            "like_count": comment.like_count,
            "is_pinned": comment.is_pinned,
            "created_at": comment.created_at,
            "edited_at": comment.edited_at,
            "author_id": comment.user_id,
            "author_name": name,
            "author_handle": handle,
            "liked_by_me": comment.id in liked,
            "is_mine": viewer is not None and viewer.id == comment.user_id,
            "is_uploader": comment.user_id == uploader_id,
            "editable_until": comment.created_at + timedelta(seconds=edit_window_seconds),
            "replies": [],
        }
        if comment.parent_id is None:
            by_id[comment.id] = item
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


async def refresh_comment_count(session: AsyncSession, video_id: uuid.UUID) -> int:
    total = await session.scalar(
        select(func.count())
        .select_from(Comment)
        .where(Comment.video_id == video_id, Comment.deleted_at.is_(None))
    )
    await session.execute(update(Video).where(Video.id == video_id).values(comment_count=total or 0))
    return total or 0


async def add_comment(
    session: AsyncSession, video: Video, user: User, body: str, parent_id: uuid.UUID | None
) -> Comment:
    if not video.comments_enabled:
        raise VideoError("Comments are turned off for this video", status_code=403)

    parent = None
    if parent_id is not None:
        parent = await session.get(Comment, parent_id)
        if parent is None or parent.video_id != video.id or parent.deleted_at is not None:
            raise VideoError("That comment no longer exists", status_code=404)
        if parent.parent_id is not None:
            # one level of replies: a reply to a reply attaches to the same thread
            parent_id = parent.parent_id

    comment = Comment(video_id=video.id, user_id=user.id, parent_id=parent_id, body=body.strip())
    log.debug(
        "  comment by %s on video %s (%s, %d chars)",
        user.handle,
        video.id,
        "reply" if parent_id else "top level",
        len(body.strip()),
    )
    session.add(comment)
    await session.flush()
    await refresh_comment_count(session, video.id)

    notified: set[uuid.UUID] = set()
    if parent is not None:
        notify(
            session,
            user_id=parent.user_id,
            type="comment_reply",
            video_id=video.id,
            actor_id=user.id,
            comment_id=str(comment.id),
            preview=comment.body[:120],
        )
        notified.add(parent.user_id)

    await notify_mentions(
        session,
        body=comment.body,
        video=video,
        author=user,
        comment_id=comment.id,
        already_notified=notified,
    )
    await session.commit()
    return comment


async def edit_comment(
    session: AsyncSession, comment_id: uuid.UUID, user: User, body: str, window_seconds: int
) -> Comment:
    """Editing is allowed for a short window after posting: long enough to fix a typo,
    short enough that nobody can rewrite a comment others have already replied to."""
    comment = await get_own_comment(session, comment_id, user)
    age = (datetime.now(UTC) - comment.created_at).total_seconds()
    if age > window_seconds:
        raise VideoError(
            f"Comments can only be edited for {window_seconds} seconds after posting",
            status_code=403,
        )
    comment.body = body.strip()
    comment.edited_at = datetime.now(UTC)
    await session.commit()
    return comment


async def delete_comment(session: AsyncSession, comment_id: uuid.UUID, user: User) -> None:
    comment = await session.get(Comment, comment_id)
    if comment is None or comment.deleted_at is not None:
        raise VideoError("That comment no longer exists", status_code=404)
    video = await session.get(Video, comment.video_id)
    is_uploader = video is not None and video.owner_id == user.id
    if comment.user_id != user.id and not is_uploader and user.role != "admin":
        raise VideoError("You can only delete your own comments", status_code=403)
    comment.deleted_at = datetime.now(UTC)
    await session.execute(
        update(Comment).where(Comment.parent_id == comment.id).values(deleted_at=datetime.now(UTC))
    )
    await refresh_comment_count(session, comment.video_id)
    await session.commit()


async def get_own_comment(session: AsyncSession, comment_id: uuid.UUID, user: User) -> Comment:
    comment = await session.get(Comment, comment_id)
    if comment is None or comment.deleted_at is not None:
        raise VideoError("That comment no longer exists", status_code=404)
    if comment.user_id != user.id:
        raise VideoError("You can only edit your own comments", status_code=403)
    return comment


async def toggle_comment_like(session: AsyncSession, comment_id: uuid.UUID, user: User) -> tuple[int, bool]:
    comment = await session.get(Comment, comment_id)
    if comment is None or comment.deleted_at is not None:
        raise VideoError("That comment no longer exists", status_code=404)

    existing = await session.get(CommentReaction, {"user_id": user.id, "comment_id": comment_id})
    if existing:
        await session.delete(existing)
        liked = False
    else:
        session.add(CommentReaction(user_id=user.id, comment_id=comment_id, created_at=datetime.now(UTC)))
        liked = True
    await session.flush()

    total = await session.scalar(
        select(func.count()).select_from(CommentReaction).where(CommentReaction.comment_id == comment_id)
    )
    comment.like_count = total or 0
    await session.commit()
    return comment.like_count, liked


# ------------------------------------------------------------------ sharing
async def search_people(session: AsyncSession, query: str, exclude: User, limit: int = 8) -> list[dict]:
    pattern = f"%{query.strip().lower()}%"
    rows = await session.execute(
        select(User.id, User.display_name, User.handle)
        .where(
            User.id != exclude.id,
            User.is_active,
            User.deleted_at.is_(None),
            func.lower(User.display_name).like(pattern) | User.handle.like(pattern),
        )
        .order_by(User.display_name)
        .limit(limit)
    )
    return [{"id": r.id, "display_name": r.display_name, "handle": r.handle} for r in rows]


async def share_video(
    session: AsyncSession,
    video: Video,
    sender: User,
    to_user_ids: list[uuid.UUID],
    message: str | None,
    at_seconds: int | None,
) -> int:
    recipients = (
        await session.scalars(
            select(User).where(User.id.in_(to_user_ids), User.is_active, User.deleted_at.is_(None))
        )
    ).all()
    if not recipients:
        raise VideoError("Choose at least one person to share with", status_code=400)

    now = datetime.now(UTC)
    for recipient in recipients:
        if recipient.id == sender.id:
            continue
        session.add(
            VideoShare(
                video_id=video.id,
                from_user_id=sender.id,
                to_user_id=recipient.id,
                message=(message or None),
                at_seconds=at_seconds,
                created_at=now,
            )
        )
        notify(
            session,
            user_id=recipient.id,
            type="video_shared",
            video_id=video.id,
            actor_id=sender.id,
            title=video.title,
            message=message,
            at_seconds=at_seconds,
        )
    await session.commit()
    return len([r for r in recipients if r.id != sender.id])


async def shared_with_me(session: AsyncSession, user: User, limit: int = 50) -> list[dict]:
    sender = User.__table__.alias("sender")
    rows = await session.execute(
        select(
            VideoShare.video_id,
            Video.title,
            sender.c.display_name,
            sender.c.handle,
            VideoShare.message,
            VideoShare.at_seconds,
            VideoShare.created_at,
        )
        .join(Video, Video.id == VideoShare.video_id)
        .join(sender, sender.c.id == VideoShare.from_user_id)
        .where(VideoShare.to_user_id == user.id, Video.deleted_at.is_(None))
        .order_by(VideoShare.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "video_id": r[0],
            "title": r[1],
            "from_name": r[2],
            "from_handle": r[3],
            "message": r[4],
            "at_seconds": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]


# ------------------------------------------------------------------ views
async def count_view(session: AsyncSession, video_id: uuid.UUID) -> int:
    """One more view. Debouncing per viewer comes with the analytics phase."""
    result = await session.execute(
        update(Video)
        .where(Video.id == video_id)
        .values(view_count=Video.view_count + 1)
        .returning(Video.view_count)
    )
    await session.commit()
    return result.scalar_one_or_none() or 0

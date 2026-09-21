"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { timeAgo } from "@/lib/api";
import type { SessionUser } from "@/lib/session";
import { AiAssist } from "./AiAssist";
import { CommentBody, MentionInput } from "./MentionInput";
import { LikeIcon, TrashIcon } from "./icons";

export type Comment = {
  id: string;
  parent_id: string | null;
  body: string;
  like_count: number;
  is_pinned: boolean;
  created_at: string;
  edited_at: string | null;
  author_id: string;
  author_name: string;
  author_handle: string;
  liked_by_me: boolean;
  is_mine: boolean;
  is_uploader: boolean;
  editable_until: string | null;
  replies: Comment[];
};

/** Seconds left in the edit window, ticking down; 0 once it has passed. */
function useSecondsLeft(until: string | null): number {
  const [left, setLeft] = useState(() =>
    until ? Math.max(0, Math.ceil((new Date(until).getTime() - Date.now()) / 1000)) : 0,
  );
  useEffect(() => {
    if (!until) return;
    const timer = setInterval(() => {
      setLeft(Math.max(0, Math.ceil((new Date(until).getTime() - Date.now()) / 1000)));
    }, 1000);
    return () => clearInterval(timer);
  }, [until]);
  return left;
}

export function Comments({
  videoId,
  count,
  user,
  isUploader,
  enabled = true,
}: {
  videoId: string;
  count: number;
  user: SessionUser | null;
  isUploader: boolean;
  /** false when the uploader has turned comments off: the thread stays readable */
  enabled?: boolean;
}) {
  const [comments, setComments] = useState<Comment[]>([]);
  const [sort, setSort] = useState<"top" | "new">("top");
  const [loading, setLoading] = useState(true);
  const [body, setBody] = useState("");
  const [error, setError] = useState("");
  const [replyTo, setReplyTo] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/v1/videos/${videoId}/comments?sort=${sort}`, { cache: "no-store" });
      if (res.ok) setComments(await res.json());
    } catch {
      setError("Couldn't load comments.");
    } finally {
      setLoading(false);
    }
  }, [videoId, sort]);

  useEffect(() => {
    void load();
  }, [load]);

  async function submit(event: FormEvent, parentId: string | null, text: string, reset: () => void) {
    event.preventDefault();
    if (!text.trim()) return;
    setError("");
    try {
      const res = await fetch(`/api/v1/videos/${videoId}/comments`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ body: text.trim(), parent_id: parentId }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        setError(data?.detail?.message ?? "Couldn't post that comment.");
        return;
      }
      reset();
      setReplyTo(null);
      await load();
    } catch {
      setError("Couldn't post that comment.");
    }
  }

  const total = comments.reduce((sum, c) => sum + 1 + c.replies.length, 0) || count;

  return (
    <section className="mt-8">
      <div className="mb-4 flex items-center gap-4">
        <h2 className="text-lg font-semibold">
          {total} {total === 1 ? "comment" : "comments"}
        </h2>
        <div className="flex gap-1 text-sm">
          {(["top", "new"] as const).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setSort(option)}
              className={`rounded-full px-3 py-1 font-medium ${
                sort === option ? "bg-surface" : "text-muted hover:bg-surface-hover"
              }`}
            >
              {option === "top" ? "Top" : "Newest"}
            </button>
          ))}
        </div>
      </div>

      {!enabled ? (
        <p className="rounded-lg bg-surface px-4 py-3 text-sm text-muted">
          Comments are turned off for this video.
        </p>
      ) : user ? (
        <CommentBox
          user={user}
          value={body}
          onChange={setBody}
          onSubmit={(event) => submit(event, null, body, () => setBody(""))}
          placeholder="Add a comment…  type @ to mention someone"
        />
      ) : (
        <p className="rounded-lg bg-surface px-4 py-3 text-sm text-muted">
          <Link href="/login" className="font-medium text-brand hover:underline">
            Sign in
          </Link>{" "}
          to join the conversation.
        </p>
      )}

      {error && <p className="mt-3 text-sm text-bad">{error}</p>}

      {loading ? (
        <p className="mt-6 text-sm text-muted">Loading comments…</p>
      ) : comments.length === 0 ? (
        <p className="mt-6 text-sm text-muted">No comments yet. Be the first to add context.</p>
      ) : (
        <ul className="mt-6 grid gap-5">
          {comments.map((comment) => (
            <li key={comment.id}>
              <CommentItem
                comment={comment}
                user={enabled ? user : null}
                canModerate={isUploader}
                replyTo={replyTo}
                setReplyTo={setReplyTo}
                onSubmitReply={submit}
                reload={load}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function CommentItem({
  comment,
  user,
  canModerate,
  replyTo,
  setReplyTo,
  onSubmitReply,
  reload,
  isReply = false,
}: {
  comment: Comment;
  user: SessionUser | null;
  canModerate: boolean;
  replyTo: string | null;
  setReplyTo: (id: string | null) => void;
  onSubmitReply: (e: FormEvent, parentId: string | null, text: string, reset: () => void) => void;
  reload: () => Promise<void>;
  isReply?: boolean;
}) {
  const [liked, setLiked] = useState(comment.liked_by_me);
  const [likes, setLikes] = useState(comment.like_count);
  const [replyBody, setReplyBody] = useState("");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(comment.body);
  const [editError, setEditError] = useState("");
  const secondsLeft = useSecondsLeft(comment.is_mine ? comment.editable_until : null);
  const canEdit = comment.is_mine && secondsLeft > 0;

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    setEditError("");
    if (!draft.trim()) return;
    const res = await fetch(`/api/v1/comments/${comment.id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ body: draft.trim() }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      setEditError(data?.detail?.message ?? "Couldn't save that edit.");
      return;
    }
    setEditing(false);
    await reload();
  }

  async function toggleLike() {
    if (!user) return;
    const previous = { liked, likes };
    setLiked(!liked);
    setLikes(likes + (liked ? -1 : 1));
    try {
      const res = await fetch(`/api/v1/comments/${comment.id}/reaction`, { method: "PUT" });
      if (!res.ok) throw new Error();
      const data = await res.json();
      setLiked(data.liked_by_me);
      setLikes(data.like_count);
    } catch {
      setLiked(previous.liked);
      setLikes(previous.likes);
    }
  }

  async function remove() {
    if (!confirm("Delete this comment?")) return;
    await fetch(`/api/v1/comments/${comment.id}`, { method: "DELETE" });
    await reload();
  }

  return (
    <article className="flex gap-3">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-semibold text-brand-contrast">
        {comment.author_name.charAt(0).toUpperCase()}
      </span>

      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-medium">@{comment.author_handle}</span>
          {comment.is_uploader && (
            <span className="rounded-full bg-surface px-2 py-0.5 text-xs text-muted">Uploader</span>
          )}
          {comment.is_pinned && (
            <span className="rounded-full bg-surface px-2 py-0.5 text-xs text-muted">Pinned</span>
          )}
          <span className="text-xs text-muted">
            {timeAgo(comment.created_at)}
            {comment.edited_at && " (edited)"}
          </span>
        </p>

        {editing ? (
          <form onSubmit={saveEdit} className="mt-1">
            <MentionInput value={draft} onChange={setDraft} rows={3} autoFocus />
            {editError && <p className="mt-1 text-xs text-bad">{editError}</p>}
            <div className="mt-2 flex items-center gap-2">
              <AiAssist
                field="comment"
                value={draft}
                context={{}}
                onAccept={setDraft}
                size="sm"
                align="left"
              />
              <button
                type="submit"
                className="rounded-full bg-brand px-3 py-1 text-xs font-medium text-brand-contrast hover:bg-brand-hover"
              >
                Save
              </button>
              <button
                type="button"
                onClick={() => {
                  setEditing(false);
                  setDraft(comment.body);
                }}
                className="rounded-full px-3 py-1 text-xs font-medium hover:bg-surface-hover"
              >
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <CommentBody body={comment.body} />
        )}

        <div className="mt-1 flex items-center gap-1 text-xs">
          <button
            type="button"
            onClick={toggleLike}
            disabled={!user}
            aria-pressed={liked}
            className={`flex items-center gap-1 rounded-full px-2 py-1 hover:bg-surface-hover disabled:opacity-60 ${
              liked ? "text-brand" : "text-muted"
            }`}
          >
            <LikeIcon width={15} height={15} />
            {likes > 0 && likes}
          </button>

          {user && !isReply && !editing && (
            <button
              type="button"
              onClick={() => {
                const opening = replyTo !== comment.id;
                setReplyTo(opening ? comment.id : null);
                if (opening && !isReply) setReplyBody(`@${comment.author_handle} `);
              }}
              className="rounded-full px-2 py-1 font-medium text-muted hover:bg-surface-hover"
            >
              Reply
            </button>
          )}

          {canEdit && !editing && (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="rounded-full px-2 py-1 font-medium text-muted hover:bg-surface-hover"
            >
              Edit
            </button>
          )}

          {(comment.is_mine || canModerate) && (
            <button
              type="button"
              onClick={remove}
              aria-label="Delete comment"
              className="ml-auto rounded-full p-1 text-muted hover:bg-surface-hover hover:text-bad"
            >
              <TrashIcon width={14} height={14} />
            </button>
          )}
        </div>

        {replyTo === comment.id && user && (
          <form
            onSubmit={(event) => onSubmitReply(event, comment.id, replyBody, () => setReplyBody(""))}
            className="mt-3"
          >
            <MentionInput
              value={replyBody}
              onChange={setReplyBody}
              placeholder={`Reply to @${comment.author_handle}… use @ to mention someone`}
              autoFocus
            />
            <div className="mt-2 flex items-center gap-2">
              {replyBody.trim().length > 2 && (
                <AiAssist
                  field="comment"
                  value={replyBody}
                  context={{}}
                  onAccept={setReplyBody}
                  size="sm"
                  align="left"
                />
              )}
              <button
                type="submit"
                className="rounded-full bg-brand px-3 py-1 text-xs font-medium text-brand-contrast hover:bg-brand-hover"
              >
                Reply
              </button>
              <button
                type="button"
                onClick={() => setReplyTo(null)}
                className="rounded-full px-3 py-1 text-xs font-medium hover:bg-surface-hover"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {comment.replies.length > 0 && (
          <ul className="mt-4 grid gap-4 border-l border-line pl-4">
            {comment.replies.map((reply) => (
              <li key={reply.id}>
                <CommentItem
                  comment={reply}
                  user={user}
                  canModerate={canModerate}
                  replyTo={replyTo}
                  setReplyTo={setReplyTo}
                  onSubmitReply={onSubmitReply}
                  reload={reload}
                  isReply
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}

function CommentBox({
  user,
  value,
  onChange,
  onSubmit,
  placeholder,
}: {
  user: SessionUser;
  value: string;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  placeholder: string;
}) {
  return (
    <form onSubmit={onSubmit} className="flex gap-3">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-semibold text-brand-contrast">
        {user.display_name.charAt(0).toUpperCase()}
      </span>
      <div className="flex-1">
        <MentionInput
          value={value}
          onChange={onChange}
          rows={value ? 3 : 1}
          placeholder={placeholder}
        />
        {value && (
          <div className="mt-2 flex items-center justify-end gap-2">
            <AiAssist
              field="comment"
              value={value}
              context={{}}
              onAccept={onChange}
              size="sm"
            />
            <button
              type="button"
              onClick={() => onChange("")}
              className="rounded-full px-3 py-1.5 text-xs font-medium hover:bg-surface-hover"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="rounded-full bg-brand px-4 py-1.5 text-xs font-medium text-brand-contrast hover:bg-brand-hover"
            >
              Comment
            </button>
          </div>
        )}
      </div>
    </form>
  );
}

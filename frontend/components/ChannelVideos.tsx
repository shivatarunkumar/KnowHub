"use client";

import Link from "next/link";
import { useState } from "react";
import {
  CATEGORY_LABELS,
  type Topic,
  type Video,
  VISIBILITY_LABELS,
  formatViews,
  timeAgo,
} from "@/lib/api";
import { VideoCard } from "./VideoCard";
import { VideoManageDialog } from "./VideoManageDialog";
import { VideoThumbnail } from "./VideoThumbnail";
import { CommentIcon, PencilIcon } from "./icons";

/**
 * The videos on a channel. Visitors get the usual grid; the owner gets a list with the
 * controls: change the wording, change who can watch, turn comments off, delete.
 */
export function ChannelVideos({
  videos: initial,
  topics,
  isMe,
}: {
  videos: Video[];
  topics: Topic[];
  isMe: boolean;
}) {
  const [videos, setVideos] = useState(initial);
  const [editing, setEditing] = useState<Video | null>(null);

  if (videos.length === 0) {
    return (
      <div className="mt-10 rounded-xl bg-surface p-8 text-center">
        <p className="font-medium">{isMe ? "You haven't uploaded anything yet" : "No videos yet"}</p>
        {isMe && (
          <Link
            href="/upload"
            className="mt-4 inline-block rounded-full bg-brand px-4 py-2 text-sm font-medium text-brand-contrast hover:bg-brand-hover"
          >
            Upload a video
          </Link>
        )}
      </div>
    );
  }

  if (!isMe) {
    return (
      <div className="mt-6 grid gap-x-4 gap-y-8 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {videos.map((video) => (
          <VideoCard key={video.id} video={video} />
        ))}
      </div>
    );
  }

  return (
    <>
      <ul className="mt-6 grid gap-3">
        {videos.map((video) => (
          <li
            key={video.id}
            className="flex flex-col gap-3 rounded-xl border border-line p-3 sm:flex-row sm:items-start"
          >
            <Link href={`/watch/${video.id}`} className="w-full shrink-0 sm:w-56">
              <VideoThumbnail video={video} rounded="rounded-lg" />
            </Link>

            <div className="min-w-0 flex-1">
              <Link href={`/watch/${video.id}`} className="line-clamp-2 font-medium hover:underline">
                {video.title}
              </Link>
              <p className="mt-1 line-clamp-2 text-sm text-muted">
                {video.description || "No description."}
              </p>

              <ul className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
                <Badge tone={video.visibility === "internal" ? "plain" : "warn"}>
                  {VISIBILITY_LABELS[video.visibility] ?? video.visibility}
                  {video.visibility === "restricted" && ` · ${video.allowed_viewers?.length ?? 0}`}
                </Badge>
                {video.status !== "READY" && <Badge tone="warn">{video.status.toLowerCase()}</Badge>}
                {!video.comments_enabled && (
                  <Badge tone="warn">
                    <CommentIcon width={12} height={12} /> off
                  </Badge>
                )}
                {video.topic_name && <Badge tone="plain">{video.topic_name}</Badge>}
                <Badge tone="plain">{CATEGORY_LABELS[video.category] ?? video.category}</Badge>
              </ul>

              <p className="mt-2 text-xs text-muted">
                {formatViews(video.view_count)} · {video.like_count} likes · {video.comment_count} comments ·{" "}
                {timeAgo(video.published_at ?? video.created_at)}
              </p>
            </div>

            <button
              type="button"
              onClick={() => setEditing(video)}
              className="flex shrink-0 items-center gap-1.5 self-start rounded-full border border-line px-3 py-1.5 text-sm font-medium hover:bg-surface"
            >
              <PencilIcon width={16} height={16} /> Manage
            </button>
          </li>
        ))}
      </ul>

      {editing && (
        <VideoManageDialog
          video={editing}
          topics={topics}
          onSaved={(saved) => {
            setVideos(videos.map((v) => (v.id === saved.id ? { ...v, ...saved } : v)));
            setEditing(null);
          }}
          onDeleted={(id) => {
            setVideos(videos.filter((v) => v.id !== id));
            setEditing(null);
          }}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}

function Badge({ children, tone }: { children: React.ReactNode; tone: "plain" | "warn" }) {
  return (
    <li
      className={`flex items-center gap-1 rounded px-1.5 py-0.5 ${
        tone === "warn" ? "bg-warn/15 text-warn" : "bg-surface text-muted"
      }`}
    >
      {children}
    </li>
  );
}

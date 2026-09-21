import Link from "next/link";
import { type Video, CATEGORY_LABELS, formatViews, timeAgo } from "@/lib/api";
import { VideoThumbnail } from "./VideoThumbnail";

export function VideoCard({ video }: { video: Video }) {
  return (
    <article>
      <Link href={`/watch/${video.id}`} className="group block">
        <VideoThumbnail video={video} />
      </Link>

      <div className="mt-3 flex gap-3">
        <span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-semibold text-brand-contrast"
          aria-hidden="true"
        >
          {(video.owner_display_name ?? "?").charAt(0).toUpperCase()}
        </span>
        <div className="min-w-0">
          <Link href={`/watch/${video.id}`} className="line-clamp-2 font-medium leading-snug hover:underline">
            {video.title}
          </Link>
          {video.owner_handle ? (
            <Link
              href={`/channel/${video.owner_handle}`}
              className="mt-1 block truncate text-sm text-muted hover:text-fg"
            >
              {video.owner_display_name}
            </Link>
          ) : (
            <p className="mt-1 truncate text-sm text-muted">{video.owner_display_name}</p>
          )}
          <p className="truncate text-sm text-muted">
            {formatViews(video.view_count)} · {timeAgo(video.published_at ?? video.created_at)}
          </p>
          <p className="mt-1 flex flex-wrap gap-1.5 text-xs text-muted">
            {video.topic_name && <span className="rounded bg-surface px-1.5 py-0.5">{video.topic_name}</span>}
            <span className="rounded bg-surface px-1.5 py-0.5">
              {CATEGORY_LABELS[video.category] ?? video.category}
            </span>
          </p>
        </div>
      </div>
    </article>
  );
}

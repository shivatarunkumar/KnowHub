import Link from "next/link";
import { type Video, CATEGORY_LABELS, formatViews, timeAgo } from "@/lib/api";
import { VideoThumbnail } from "./VideoThumbnail";

/** Compact card for the watch-page sidebar: thumbnail left, details right. */
export function VideoRow({ video }: { video: Video }) {
  return (
    <article className="group flex gap-3">
      <Link href={`/watch/${video.id}`} className="w-40 shrink-0">
        <VideoThumbnail video={video} rounded="rounded-lg" />
      </Link>

      <div className="min-w-0 flex-1">
        <Link
          href={`/watch/${video.id}`}
          className="line-clamp-2 text-sm font-medium leading-snug group-hover:underline"
        >
          {video.title}
        </Link>
        <p className="mt-1 truncate text-xs text-muted">{video.owner_display_name}</p>
        <p className="truncate text-xs text-muted">
          {formatViews(video.view_count)} · {timeAgo(video.published_at ?? video.created_at)}
        </p>
        <p className="mt-1 flex flex-wrap gap-1 text-[11px] text-muted">
          {video.topic_name && <span className="rounded bg-surface px-1.5 py-0.5">{video.topic_name}</span>}
          <span className="rounded bg-surface px-1.5 py-0.5">
            {CATEGORY_LABELS[video.category] ?? video.category}
          </span>
        </p>
      </div>
    </article>
  );
}

"use client";

import { useState } from "react";
import type { Video } from "@/lib/api";
import { formatDurationBadge } from "@/lib/thumbnail";
import { ShortsIcon } from "./icons";

/**
 * Hue derived from the id, so a video's cover colour is stable but varies between videos.
 * Kept inside the brand's green-to-teal range (110°–200°) so a full grid of generated
 * covers still looks like one product.
 */
function hueFor(id: string): number {
  let hash = 0;
  for (const char of id) hash = (hash * 31 + char.charCodeAt(0)) % 360;
  return 110 + (hash % 90);
}

/**
 * The poster frame captured at upload. Videos without one (or whose image fails to load)
 * get a drawn cover with the topic and initials, so the grid never looks broken.
 */
export function VideoThumbnail({ video, rounded = "rounded-xl" }: { video: Video; rounded?: string }) {
  const [failed, setFailed] = useState(false);
  const showImage = video.has_thumbnail && !failed;
  const hue = hueFor(video.id);
  const duration = formatDurationBadge(video.duration_sec);

  return (
    <div className={`relative aspect-video w-full overflow-hidden ${rounded} bg-surface`}>
      {showImage ? (
        // a plain img: the file is served by our API, and Next's optimiser adds nothing here
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={`/api/v1/videos/${video.id}/thumbnail`}
          alt=""
          loading="lazy"
          onError={() => setFailed(true)}
          className="h-full w-full object-cover"
        />
      ) : (
        <div
          aria-hidden="true"
          className="flex h-full w-full flex-col items-center justify-center gap-2 text-white"
          style={{
            background: `linear-gradient(135deg, hsl(${hue} 42% 32%), hsl(${hue + 25} 48% 18%))`,
          }}
        >
          <span className="rounded-full bg-black/25 px-3 py-1 text-[11px] font-medium uppercase tracking-wide">
            {video.topic_name ?? "KnowHub"}
          </span>
          <span className="line-clamp-2 max-w-[85%] text-center text-sm font-semibold leading-snug">
            {video.title}
          </span>
        </div>
      )}

      {video.type === "short" && (
        <span className="absolute left-2 top-2 flex items-center gap-1 rounded-md bg-black/70 px-1.5 py-0.5 text-[11px] text-white">
          <ShortsIcon width={11} height={11} /> Short
        </span>
      )}
      {duration && (
        <span className="absolute bottom-2 right-2 rounded bg-black/75 px-1.5 py-0.5 text-[11px] font-medium tabular-nums text-white">
          {duration}
        </span>
      )}
      {video.visibility !== "internal" && (
        <span className="absolute right-2 top-2 rounded-md bg-black/70 px-1.5 py-0.5 text-[11px] capitalize text-white">
          {video.visibility}
        </span>
      )}
    </div>
  );
}

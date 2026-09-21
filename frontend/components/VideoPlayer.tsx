"use client";

import { useRef, useState } from "react";

/** Plays the video and counts one view when playback starts. */
export function VideoPlayer({ videoId }: { videoId: string }) {
  const counted = useRef(false);
  const [error, setError] = useState(false);

  function onPlay() {
    if (counted.current) return;
    counted.current = true;
    void fetch(`/api/v1/videos/${videoId}/view`, { method: "POST" }).catch(() => {
      /* a missed view isn't worth bothering the viewer about */
    });
  }

  if (error) {
    return (
      <div className="flex aspect-video w-full items-center justify-center rounded-xl bg-surface text-sm text-muted">
        This video can&apos;t be played right now.
      </div>
    );
  }

  return (
    <video
      src={`/api/v1/videos/${videoId}/stream`}
      controls
      autoPlay
      preload="metadata"
      onPlay={onPlay}
      onError={() => setError(true)}
      className="aspect-video w-full rounded-xl bg-black"
    />
  );
}

"use client";

import { useState } from "react";
import type { SessionUser } from "@/lib/session";
import { ShareDialog } from "./ShareDialog";
import { DislikeIcon, LikeIcon, ShareIcon } from "./icons";

type Reaction = { like_count: number; dislike_count: number; my_reaction: number };

export function VideoActions({
  videoId,
  videoTitle,
  initial,
  user,
}: {
  videoId: string;
  videoTitle: string;
  initial: Reaction;
  user: SessionUser | null;
}) {
  const [reaction, setReaction] = useState(initial);
  const [sharing, setSharing] = useState(false);
  const [notice, setNotice] = useState("");

  async function react(value: number) {
    if (!user) {
      setNotice("Sign in to like videos.");
      return;
    }
    // pressing the active button again clears the reaction
    const next = reaction.my_reaction === value ? 0 : value;
    const previous = reaction;
    setReaction({
      like_count: reaction.like_count + (next === 1 ? 1 : 0) - (reaction.my_reaction === 1 ? 1 : 0),
      dislike_count:
        reaction.dislike_count + (next === -1 ? 1 : 0) - (reaction.my_reaction === -1 ? 1 : 0),
      my_reaction: next,
    });
    try {
      const res = await fetch(`/api/v1/videos/${videoId}/reaction`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ value: next }),
      });
      if (!res.ok) throw new Error();
      setReaction(await res.json());
    } catch {
      setReaction(previous); // put it back if the server disagreed
      setNotice("Couldn't save that. Please try again.");
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center overflow-hidden rounded-full bg-surface">
          <button
            type="button"
            onClick={() => react(1)}
            aria-pressed={reaction.my_reaction === 1}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium hover:bg-surface-hover ${
              reaction.my_reaction === 1 ? "text-brand" : ""
            }`}
          >
            <LikeIcon width={20} height={20} />
            {reaction.like_count}
          </button>
          <span className="h-5 w-px bg-line" />
          <button
            type="button"
            onClick={() => react(-1)}
            aria-pressed={reaction.my_reaction === -1}
            aria-label="Dislike"
            className={`px-4 py-2 hover:bg-surface-hover ${
              reaction.my_reaction === -1 ? "text-brand" : ""
            }`}
          >
            <DislikeIcon width={20} height={20} />
          </button>
        </div>

        <button
          type="button"
          onClick={() => (user ? setSharing(true) : setNotice("Sign in to share videos."))}
          className="flex items-center gap-2 rounded-full bg-surface px-4 py-2 text-sm font-medium hover:bg-surface-hover"
        >
          <ShareIcon width={20} height={20} />
          Share
        </button>

        {notice && <span className="text-sm text-muted">{notice}</span>}
      </div>

      {sharing && (
        <ShareDialog videoId={videoId} videoTitle={videoTitle} onClose={() => setSharing(false)} />
      )}
    </>
  );
}

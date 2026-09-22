import { cache } from "react";

export type Topic = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  icon: string | null;
};

// Server components call FastAPI directly; the browser goes through the /api rewrite.
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

export const getTopics = cache(async (): Promise<Topic[]> => {
  try {
    const res = await fetch(`${API_INTERNAL_URL}/api/v1/topics`, { cache: "no-store" });
    return res.ok ? await res.json() : [];
  } catch {
    return []; // API down: render the shell anyway; the status pill shows the problem
  }
});

export type Team = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  division: string | null;
};

export const getTeams = cache(async (): Promise<Team[]> => {
  try {
    const res = await fetch(`${API_INTERNAL_URL}/api/v1/teams`, { cache: "no-store" });
    return res.ok ? await res.json() : [];
  } catch {
    return []; // API down: the filter just doesn't appear
  }
});

export type Video = {
  id: string;
  type: "video" | "short";
  title: string;
  description: string | null;
  category: string;
  visibility: string;
  status: string;
  duration_sec: number | null;
  size_bytes: number | null;
  view_count: number;
  like_count: number;
  comment_count: number;
  published_at: string | null;
  created_at: string;
  owner_id: string;
  owner_display_name: string | null;
  owner_handle: string | null;
  topic_slug: string | null;
  topic_name: string | null;
  team_slug: string | null;
  team_name: string | null;
  has_thumbnail: boolean;
  comments_enabled: boolean;
  allowed_viewers?: Person[];
  links?: { id: string; kind: string; url: string; label: string | null }[];
  snippets?: { id: string; title: string | null; language: string; code: string }[];
};

export type Person = { id: string; display_name: string; handle: string };

export type Channel = {
  id: string;
  handle: string;
  display_name: string;
  bio: string | null;
  avatar_url: string | null;
  joined_at: string;
  is_me: boolean;
  video_count: number;
  total_views: number;
  videos: Video[];
};

export async function getChannel(handle: string, cookieHeader?: string): Promise<Channel | null> {
  try {
    const res = await fetch(`${API_INTERNAL_URL}/api/v1/channels/${encodeURIComponent(handle)}`, {
      cache: "no-store",
      headers: cookieHeader ? { cookie: cookieHeader } : undefined,
    });
    return res.ok ? ((await res.json()) as Channel) : null;
  } catch {
    return null;
  }
}

export const VISIBILITY_LABELS: Record<string, string> = {
  internal: "Everyone",
  unlisted: "Anyone with the link",
  restricted: "Specific people",
  private: "Only you",
};

export const CATEGORY_LABELS: Record<string, string> = {
  bug_fix: "Bug fix",
  incident_resolution: "Incident resolution",
  how_to: "How-to",
  knowledge_share: "Knowledge share",
  demo: "Demo",
  reusable_component: "Reusable component",
};

export async function getFeed(
  params: { topic?: string; team?: string; type?: string } = {},
): Promise<Video[]> {
  const query = new URLSearchParams();
  if (params.topic) query.set("topic", params.topic);
  if (params.team) query.set("team", params.team);
  if (params.type) query.set("type", params.type);
  try {
    const res = await fetch(`${API_INTERNAL_URL}/api/v1/videos/feed?${query}`, { cache: "no-store" });
    if (!res.ok) return [];
    return (await res.json()).items as Video[];
  } catch {
    return [];
  }
}

export async function getVideo(id: string, cookieHeader?: string): Promise<Video | null> {
  try {
    const res = await fetch(`${API_INTERNAL_URL}/api/v1/videos/${id}`, {
      cache: "no-store",
      headers: cookieHeader ? { cookie: cookieHeader } : undefined,
    });
    return res.ok ? ((await res.json()) as Video) : null;
  } catch {
    return null;
  }
}

/** "3 days ago", "2 hours ago" — the age shown on a video card. */
export function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const seconds = Math.max(1, (Date.now() - new Date(iso).getTime()) / 1000);
  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, "second"], [3600, "minute"], [86400, "hour"],
    [604800, "day"], [2592000, "week"], [31536000, "month"], [Infinity, "year"],
  ];
  const divisors = [1, 60, 3600, 86400, 604800, 2592000, 31536000];
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (let i = 0; i < units.length; i++) {
    if (seconds < units[i][0]) return formatter.format(-Math.floor(seconds / divisors[i]), units[i][1]);
  }
  return "";
}

export function formatViews(count: number): string {
  if (count < 1000) return `${count} view${count === 1 ? "" : "s"}`;
  if (count < 1_000_000) return `${(count / 1000).toFixed(count < 10_000 ? 1 : 0)}K views`;
  return `${(count / 1_000_000).toFixed(1)}M views`;
}

export type Reaction = { like_count: number; dislike_count: number; my_reaction: number };

export async function getReaction(id: string, cookieHeader?: string): Promise<Reaction> {
  try {
    const res = await fetch(`${API_INTERNAL_URL}/api/v1/videos/${id}/reaction`, {
      cache: "no-store",
      headers: cookieHeader ? { cookie: cookieHeader } : undefined,
    });
    if (res.ok) return (await res.json()) as Reaction;
  } catch {
    /* fall through to zeros */
  }
  return { like_count: 0, dislike_count: 0, my_reaction: 0 };
}

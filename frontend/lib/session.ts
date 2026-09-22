import { cookies } from "next/headers";
import { cache } from "react";

export type SessionUser = {
  id: string;
  email: string;
  display_name: string;
  handle: string;
  avatar_url: string | null;
  bio: string | null;
  role: "user" | "admin";
  team_id: string | null;
};

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** The signed-in user for the current request, or null. Server components only. */
export const getCurrentUser = cache(async (): Promise<SessionUser | null> => {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader) return null;
  try {
    const res = await fetch(`${API_INTERNAL_URL}/api/v1/auth/me`, {
      headers: { cookie: cookieHeader },
      cache: "no-store",
    });
    return res.ok ? ((await res.json()) as SessionUser) : null;
  } catch {
    return null; // API down: render as signed out rather than erroring the page
  }
});

"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { SessionUser } from "@/lib/session";
import { CreateIcon, UserIcon } from "./icons";

export function AccountMenu({ user }: { user: SessionUser | null }) {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (!user) {
    // Signed out: keep the page you were on, and come back to it after signing in.
    const next = pathname && pathname !== "/" ? `?next=${encodeURIComponent(pathname)}` : "";
    return (
      <div className="flex items-center gap-2">
        <Link
          href={`/login${next}`}
          className="flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-sm font-medium text-brand hover:bg-surface"
        >
          <UserIcon width={20} height={20} />
          Sign in
        </Link>
      </div>
    );
  }

  async function signOut() {
    await fetch("/api/v1/auth/logout", { method: "POST" });
    setOpen(false);
    router.refresh();
    router.push("/");
  }

  return (
    <div className="flex items-center gap-2">
      <Link
        href="/upload"
        className="flex items-center gap-1.5 rounded-full bg-surface px-3 py-2 text-sm font-medium hover:bg-surface-hover"
      >
        <CreateIcon width={20} height={20} />
        <span className="hidden md:inline">Create</span>
      </Link>

      <div className="relative" ref={menuRef}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-haspopup="menu"
          aria-expanded={open}
          aria-label="Account menu"
          className="flex h-9 w-9 items-center justify-center rounded-full bg-brand text-sm font-semibold text-brand-contrast"
        >
          {user.display_name.trim().charAt(0).toUpperCase()}
        </button>

        {open && (
          <div
            role="menu"
            className="absolute right-0 top-11 w-64 overflow-hidden rounded-xl border border-line bg-bg py-2 shadow-lg"
          >
            <div className="border-b border-line px-4 pb-3">
              <p className="truncate font-medium">{user.display_name}</p>
              <p className="truncate text-sm text-muted">@{user.handle}</p>
              <p className="truncate text-xs text-muted">{user.email}</p>
            </div>
            <Link
              href={`/channel/${user.handle}`}
              role="menuitem"
              onClick={() => setOpen(false)}
              className="block px-4 py-2 text-sm hover:bg-surface-hover"
            >
              Your channel
            </Link>
            <Link
              href={`/channel/${user.handle}`}
              role="menuitem"
              onClick={() => setOpen(false)}
              className="block px-4 py-2 text-sm hover:bg-surface-hover"
            >
              Manage your videos
            </Link>
            <button
              type="button"
              role="menuitem"
              onClick={signOut}
              className="block w-full px-4 py-2 text-left text-sm hover:bg-surface-hover"
            >
              Sign out
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

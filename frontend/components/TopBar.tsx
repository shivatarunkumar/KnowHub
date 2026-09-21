"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import type { SessionUser } from "@/lib/session";
import { AccountMenu } from "./AccountMenu";
import { LogoMark, MenuIcon, SearchIcon } from "./icons";

export function TopBar({ onMenu, user }: { onMenu: () => void; user: SessionUser | null }) {
  const router = useRouter();
  const [query, setQuery] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (q) router.push(`/results?search_query=${encodeURIComponent(q)}`);
  }

  return (
    <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center justify-between gap-4 bg-bg px-4">
      <div className="flex shrink-0 items-center gap-3">
        <button
          type="button"
          onClick={onMenu}
          aria-label="Toggle navigation"
          className="rounded-full p-2 hover:bg-surface-hover"
        >
          <MenuIcon />
        </button>
        <Link href="/" className="flex items-center gap-1.5" aria-label="KnowHub home">
          <LogoMark />
          <span className="display text-lg tracking-tight">KnowHub</span>
        </Link>
      </div>

      <form onSubmit={submit} role="search" className="hidden max-w-xl flex-1 sm:flex">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search fixes, incidents, how-tos"
          aria-label="Search"
          className="h-10 w-full rounded-l-full border border-line bg-bg px-4 outline-none focus:border-brand"
        />
        <button
          type="submit"
          aria-label="Search"
          className="flex h-10 w-16 items-center justify-center rounded-r-full border border-l-0 border-line bg-surface hover:bg-surface-hover"
        >
          <SearchIcon width={20} height={20} />
        </button>
      </form>

      <AccountMenu user={user} />
    </header>
  );
}

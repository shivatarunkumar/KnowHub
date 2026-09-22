"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { Topic } from "@/lib/api";
import { CloseIcon, SearchIcon } from "./icons";

const VISIBLE = 8;

/**
 * Chips for the topics that actually have videos, and a menu for the rest.
 *
 * Listing all 25 topics made a bar that scrolled forever, most of it empty topics. The
 * ones with content lead, ordered by how much they have; everything else is one click
 * away, searchable, so a quiet topic is still reachable.
 */
export function TopicChips({
  topics,
  selected,
  team,
}: {
  topics: Topic[];
  selected: string;
  /** kept when the topic changes, so the two filters combine */
  team: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    searchRef.current?.focus();
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

  function href(slug?: string) {
    const params = new URLSearchParams();
    if (slug) params.set("topic", slug);
    if (team) params.set("team", team);
    const qs = params.toString();
    return qs ? `/?${qs}` : "/";
  }

  const withVideos = topics
    .filter((topic) => topic.video_count > 0)
    .sort((a, b) => b.video_count - a.video_count);

  const shown = withVideos.slice(0, VISIBLE);
  // whatever is selected stays on the bar, even when nothing is filed under it yet
  if (selected && !shown.some((t) => t.slug === selected)) {
    const current = topics.find((t) => t.slug === selected);
    if (current) shown.push(current);
  }
  const hidden = topics.filter((topic) => !shown.some((t) => t.slug === topic.slug));

  const term = query.trim().toLowerCase();
  const matches = term
    ? topics.filter((t) => t.name.toLowerCase().includes(term) || t.slug.includes(term))
    : hidden;

  return (
    <>
      <Chip href={href()} label="All" active={!selected} />
      {shown.map((topic) => (
        <Chip
          key={topic.slug}
          href={href(topic.slug)}
          label={topic.name}
          count={topic.video_count}
          active={topic.slug === selected}
        />
      ))}

      {hidden.length > 0 && (
        <div className="relative shrink-0" ref={menuRef}>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-haspopup="menu"
            aria-expanded={open}
            className="flex items-center gap-1 whitespace-nowrap rounded-lg border border-line px-3 py-1.5 text-sm font-medium hover:bg-surface"
          >
            {hidden.length} more
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="m6 9 6 6 6-6" />
            </svg>
          </button>

          {open && (
            <div
              role="menu"
              className="absolute left-0 top-11 z-30 w-72 overflow-hidden rounded-xl border border-line bg-bg shadow-xl"
            >
              <div className="flex items-center gap-2 border-b border-line px-3 py-2">
                <SearchIcon width={15} height={15} className="shrink-0 text-muted" />
                <input
                  ref={searchRef}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Find a topic"
                  aria-label="Find a topic"
                  className="min-w-0 flex-1 bg-transparent text-sm outline-none"
                />
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="Close"
                  className="rounded-full p-1 text-muted hover:bg-surface-hover"
                >
                  <CloseIcon width={14} height={14} />
                </button>
              </div>

              <ul className="max-h-80 overflow-y-auto py-1">
                {matches.length === 0 && (
                  <li className="px-3 py-3 text-sm text-muted">No topic matches “{query}”.</li>
                )}
                {matches.map((topic) => (
                  <li key={topic.slug}>
                    <Link
                      href={href(topic.slug)}
                      onClick={() => setOpen(false)}
                      className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-surface-hover"
                    >
                      <span className="min-w-0 flex-1 truncate">{topic.name}</span>
                      <span className="text-xs text-muted">
                        {topic.video_count > 0 ? topic.video_count : "—"}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </>
  );
}

function Chip({
  href,
  label,
  active,
  count,
}: {
  href: string;
  label: string;
  active: boolean;
  count?: number;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium ${
        active ? "bg-chip-active text-chip-active-text" : "bg-surface hover:bg-surface-hover"
      }`}
    >
      {label}
      {count !== undefined && (
        <span className={active ? "opacity-70" : "text-muted"}>{count}</span>
      )}
    </Link>
  );
}

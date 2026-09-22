"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Topic } from "@/lib/api";
import { CloseIcon, SearchIcon, TopicIcon } from "./icons";

const PANEL_WIDTH = 300;
const GUTTER = 12;

/**
 * Topics as a dropdown with checkboxes, rather than a chip bar that scrolled forever.
 *
 * Several topics mean "any of these", which is how a filter normally reads — and it has
 * to, since a video has one primary topic, so "all of these" would match nothing.
 *
 * The panel is positioned against the viewport: the bar it sits in scrolls horizontally,
 * and a scroll container clips absolutely-positioned children on both axes.
 */
export function TopicFilter({
  topics,
  selected,
  team,
}: {
  topics: Topic[];
  selected: string[];
  /** kept when topics change, so the two filters combine */
  team: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [anchor, setAnchor] = useState<{ top: number; left: number } | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const place = useCallback(() => {
    const rect = buttonRef.current?.getBoundingClientRect();
    if (!rect) return;
    setAnchor({
      top: rect.bottom + 8,
      left: Math.max(GUTTER, Math.min(rect.left, window.innerWidth - PANEL_WIDTH - GUTTER)),
    });
  }, []);

  useEffect(() => {
    if (!open) return;
    searchRef.current?.focus();
    function onPointerDown(event: MouseEvent) {
      if (!wrapperRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, place]);

  function apply(slugs: string[]) {
    const params = new URLSearchParams();
    for (const slug of slugs) params.append("topic", slug);
    if (team) params.set("team", team);
    const qs = params.toString();
    router.push(qs ? `/?${qs}` : "/");
  }

  function toggle(slug: string) {
    apply(selected.includes(slug) ? selected.filter((s) => s !== slug) : [...selected, slug]);
  }

  const term = query.trim().toLowerCase();
  const listed = term
    ? topics.filter((t) => t.name.toLowerCase().includes(term) || t.slug.includes(term))
    : // busiest first, and anything already ticked stays at the top where it can be unticked
      [...topics].sort((a, b) => {
        const picked = Number(selected.includes(b.slug)) - Number(selected.includes(a.slug));
        return picked !== 0 ? picked : b.video_count - a.video_count;
      });

  const label =
    selected.length === 0
      ? "Topics"
      : selected.length === 1
        ? (topics.find((t) => t.slug === selected[0])?.name ?? "1 topic")
        : `${selected.length} topics`;

  return (
    <div className="relative shrink-0" ref={wrapperRef}>
      <button
        type="button"
        ref={buttonRef}
        onClick={() => {
          place();
          setOpen((v) => !v);
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        className={`flex h-9 items-center gap-2 whitespace-nowrap rounded-lg pl-2.5 pr-2 text-sm font-medium ${
          selected.length ? "bg-chip-active text-chip-active-text" : "bg-surface hover:bg-surface-hover"
        }`}
      >
        <TopicIcon width={16} height={16} className={selected.length ? "" : "text-muted"} />
        {label}
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {open && anchor && (
        <div
          role="menu"
          style={{ top: anchor.top, left: anchor.left, width: PANEL_WIDTH }}
          className="fixed z-50 overflow-hidden rounded-xl border border-line bg-bg shadow-xl"
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
            {listed.length === 0 && (
              <li className="px-3 py-3 text-sm text-muted">No topic matches “{query}”.</li>
            )}
            {listed.map((topic) => {
              const checked = selected.includes(topic.slug);
              return (
                <li key={topic.slug}>
                  <label className="flex cursor-pointer items-center gap-2.5 px-3 py-2 text-sm hover:bg-surface-hover">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(topic.slug)}
                      className="h-4 w-4 shrink-0 accent-[var(--brand)]"
                    />
                    <span className="min-w-0 flex-1 truncate">{topic.name}</span>
                    <span className="shrink-0 text-xs text-muted">
                      {topic.video_count > 0 ? topic.video_count : "—"}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>

          <div className="flex items-center justify-between border-t border-line bg-surface/60 px-3 py-2 text-xs">
            <span className="text-muted">
              {selected.length === 0
                ? "Nothing selected: showing every topic"
                : `${selected.length} selected — videos in any of them`}
            </span>
            {selected.length > 0 && (
              <button
                type="button"
                onClick={() => apply([])}
                className="font-medium text-brand hover:underline"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

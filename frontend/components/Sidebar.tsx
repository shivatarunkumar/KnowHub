"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { type ComponentType, type SVGProps, useState } from "react";
import type { Topic } from "@/lib/api";
import type { SessionUser } from "@/lib/session";
import { ApiStatus } from "./ApiStatus";
import {
  ClockIcon,
  HistoryIcon,
  InfoIcon,
  HomeIcon,
  PlaylistIcon,
  ShortsIcon,
  SubscriptionsIcon,
  UserIcon,
} from "./icons";

type NavItem = { href: string; label: string; icon: ComponentType<SVGProps<SVGSVGElement>> };

const MAIN: NavItem[] = [
  { href: "/", label: "Home", icon: HomeIcon },
  { href: "/shorts", label: "Shorts", icon: ShortsIcon },
  { href: "/feed/subscriptions", label: "Subscriptions", icon: SubscriptionsIcon },
];

const YOU: NavItem[] = [
  { href: "/feed/history", label: "History", icon: HistoryIcon },
  { href: "/feed/playlists", label: "Playlists", icon: PlaylistIcon },
  { href: "/playlist/watch-later", label: "Watch later", icon: ClockIcon },
];

export function Sidebar({
  expanded,
  topics,
  user,
}: {
  expanded: boolean;
  topics: Topic[];
  user: SessionUser | null;
}) {
  const pathname = usePathname();
  const activeTopic = useSearchParams().get("topic");

  if (!expanded) {
    // Mini rail (desktop): icon + tiny label, for when the guide is collapsed.
    return (
      <nav aria-label="Main" className="flex flex-col items-center gap-1 px-1 pt-1">
        {[...MAIN, { href: "/about", label: "About", icon: InfoIcon }].map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={`flex w-16 flex-col items-center gap-1 rounded-lg py-4 text-[10px] hover:bg-surface-hover ${
              pathname === href ? "font-semibold" : ""
            }`}
          >
            <Icon />
            {label}
          </Link>
        ))}
      </nav>
    );
  }

  return (
    <nav aria-label="Main" className="flex h-full flex-col px-3 pb-4 text-sm">
      <Section items={MAIN} pathname={pathname} />
      <Divider />
      {user ? (
        <>
          <h2 className="px-3 pb-1 pt-2 text-base font-semibold">You</h2>
          <Section
            items={[{ href: `/channel/${user.handle}`, label: "Your channel", icon: UserIcon }, ...YOU]}
            pathname={pathname}
          />
        </>
      ) : (
        <div className="px-3 py-2 text-sm text-muted">
          <p>Sign in to like videos, comment and subscribe.</p>
          <Link
            href="/login"
            className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 font-medium text-brand hover:bg-surface"
          >
            Sign in
          </Link>
        </div>
      )}
      <Divider />
      <h2 className="px-3 pb-1 pt-2 text-base font-semibold">KnowHub</h2>
      <Link
        href="/about"
        className={`flex items-center gap-5 rounded-lg px-3 py-2 hover:bg-surface-hover ${
          pathname === "/about" ? "bg-surface font-semibold" : ""
        }`}
      >
        <InfoIcon width={22} height={22} />
        What is KnowHub?
      </Link>

      <Divider />
      <TopicCloud topics={topics} active={activeTopic} />

      <div className="mt-auto pt-4">
        <Divider />
        <ApiStatus />
      </div>
    </nav>
  );
}

function Section({ items, pathname }: { items: NavItem[]; pathname: string }) {
  return (
    <>
      {items.map(({ href, label, icon: Icon }) => (
        <Link
          key={href}
          href={href}
          className={`flex items-center gap-5 rounded-lg px-3 py-2 hover:bg-surface-hover ${
            pathname === href ? "bg-surface font-semibold" : ""
          }`}
        >
          <Icon width={22} height={22} />
          {label}
        </Link>
      ))}
    </>
  );
}

function Divider() {
  return <hr className="my-3 border-line" />;
}


/**
 * Topics in the guide used to be a long list of identical rows, which read as a second
 * copy of the chip bar at the top of the home page. As tags they look like what they are
 * — labels, not navigation — and eight of them fit in the space the list needed for four.
 */
function TopicCloud({ topics, active }: { topics: Topic[]; active: string | null }) {
  const [expanded, setExpanded] = useState(false);
  if (topics.length === 0) {
    return (
      <div className="px-3 py-2">
        <h2 className="pb-1 text-base font-semibold">Topics</h2>
        <p className="text-muted">No topics loaded</p>
      </div>
    );
  }

  // busiest first, so the eight that fit are the eight worth showing
  const ranked = [...topics].sort((a, b) => b.video_count - a.video_count);
  // an active topic is always visible, even when it sits past the cut
  const shown = expanded ? ranked : ranked.slice(0, 8);
  const activeHidden = active && !shown.some((t) => t.slug === active);
  const visible = activeHidden ? [...shown, ...ranked.filter((t) => t.slug === active)] : shown;
  const hiddenCount = ranked.length - visible.length;

  return (
    <div className="px-3 pb-2">
      <h2 className="flex items-baseline justify-between pb-2 pt-2 text-base font-semibold">
        Topics
        {active && (
          <Link href="/" className="text-xs font-medium text-brand hover:underline">
            Clear
          </Link>
        )}
      </h2>

      <ul className="flex flex-wrap gap-1.5">
        {visible.map((topic) => {
          const isActive = topic.slug === active;
          return (
            <li key={topic.slug}>
              <Link
                href={`/?topic=${topic.slug}`}
                title={topic.description ?? topic.name}
                aria-current={isActive ? "page" : undefined}
                className={`inline-block rounded-full px-2.5 py-1 text-xs font-medium transition ${
                  isActive
                    ? "bg-brand text-brand-contrast"
                    : "bg-surface text-muted hover:bg-surface-hover hover:text-fg"
                }`}
              >
                {topic.name}
              </Link>
            </li>
          );
        })}
        {hiddenCount > 0 && (
          <li>
            <button
              type="button"
              onClick={() => setExpanded(true)}
              className="rounded-full border border-line px-2.5 py-1 text-xs font-medium text-muted hover:bg-surface"
            >
              +{hiddenCount} more
            </button>
          </li>
        )}
        {expanded && (
          <li>
            <button
              type="button"
              onClick={() => setExpanded(false)}
              className="rounded-full border border-line px-2.5 py-1 text-xs font-medium text-muted hover:bg-surface"
            >
              Show less
            </button>
          </li>
        )}
      </ul>
    </div>
  );
}

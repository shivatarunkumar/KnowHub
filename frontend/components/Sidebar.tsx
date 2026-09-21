"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentType, SVGProps } from "react";
import type { Topic } from "@/lib/api";
import type { SessionUser } from "@/lib/session";
import { ApiStatus } from "./ApiStatus";
import {
  ClockIcon,
  HistoryIcon,
  HomeIcon,
  PlaylistIcon,
  ShortsIcon,
  SubscriptionsIcon,
  TopicIcon,
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

  if (!expanded) {
    // Mini rail (desktop): icon + tiny label, like YouTube's collapsed guide.
    return (
      <nav aria-label="Main" className="flex flex-col items-center gap-1 px-1 pt-1">
        {[...MAIN, YOU[0]].map(({ href, label, icon: Icon }) => (
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
      <h2 className="px-3 pb-1 pt-2 text-base font-semibold">Topics</h2>
      {topics.length === 0 ? (
        <p className="px-3 py-2 text-muted">No topics loaded</p>
      ) : (
        topics.map((t) => (
          <Link
            key={t.slug}
            href={`/?topic=${t.slug}`}
            title={t.description ?? t.name}
            className="flex items-center gap-5 rounded-lg px-3 py-2 hover:bg-surface-hover"
          >
            <TopicIcon width={20} height={20} />
            <span className="truncate">{t.name}</span>
          </Link>
        ))
      )}
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

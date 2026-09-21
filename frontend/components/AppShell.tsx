"use client";

import { type ReactNode, useState } from "react";
import type { Topic } from "@/lib/api";
import type { SessionUser } from "@/lib/session";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

// App frame: fixed top bar, guide sidebar (full ↔ mini on desktop,
// slide-over drawer on small screens), scrolling content area.
export function AppShell({
  topics,
  user,
  children,
}: {
  topics: Topic[];
  user: SessionUser | null;
  children: ReactNode;
}) {
  const [expanded, setExpanded] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);

  function toggle() {
    if (window.matchMedia("(min-width: 1024px)").matches) setExpanded((v) => !v);
    else setDrawerOpen((v) => !v);
  }

  return (
    <>
      <TopBar onMenu={toggle} user={user} />

      <aside
        className={`fixed bottom-0 left-0 top-14 z-30 hidden overflow-y-auto bg-bg lg:block ${
          expanded ? "w-60" : "w-[72px]"
        }`}
      >
        <Sidebar expanded={expanded} topics={topics} user={user} />
      </aside>

      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-black/50"
            onClick={() => setDrawerOpen(false)}
          />
          <aside className="absolute bottom-0 left-0 top-0 w-60 overflow-y-auto bg-bg pt-3">
            <Sidebar expanded topics={topics} user={user} />
          </aside>
        </div>
      )}

      <main className={`min-h-screen pt-14 ${expanded ? "lg:pl-60" : "lg:pl-[72px]"}`}>{children}</main>
    </>
  );
}

"use client";

import { useEffect, useState } from "react";

type Health = {
  status: "ok" | "degraded" | "down";
  checks: Record<string, { ok: boolean; error?: string }>;
};

const POLL_MS = 30_000;

// Small backend status pill: handy while building locally, shows which dependency is failing.
export function ApiStatus() {
  const [health, setHealth] = useState<Health | "unreachable" | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const res = await fetch("/api/v1/health", { cache: "no-store" });
        const body = (await res.json()) as Health;
        if (active) setHealth(body);
      } catch {
        if (active) setHealth("unreachable");
      }
    }
    load();
    const timer = setInterval(load, POLL_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  if (health === null) return <Pill color="var(--muted)" label="Checking services…" />;
  if (health === "unreachable") return <Pill color="var(--bad)" label="API unreachable" />;

  const failing = Object.entries(health.checks)
    .filter(([, c]) => !c.ok)
    .map(([name]) => name);
  const color = health.status === "ok" ? "var(--ok)" : health.status === "degraded" ? "var(--warn)" : "var(--bad)";
  const label =
    health.status === "ok" ? "All services connected" : `${health.status}: ${failing.join(", ")}`;
  return <Pill color={color} label={label} title={JSON.stringify(health.checks, null, 2)} />;
}

function Pill({ color, label, title }: { color: string; label: string; title?: string }) {
  return (
    <p className="flex items-center gap-2 px-3 py-1 text-xs text-muted" title={title} role="status">
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
      {label}
    </p>
  );
}

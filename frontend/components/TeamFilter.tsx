"use client";

import { useRouter } from "next/navigation";
import type { Team } from "@/lib/api";
import { PeopleIcon } from "./icons";

/**
 * "All teams" by default. A dropdown rather than another row of chips: there are as many
 * teams as topics, and two scrolling chip bars would be a wall of pills.
 */
export function TeamFilter({
  teams,
  selected,
  topic,
}: {
  teams: Team[];
  selected: string;
  /** kept when the team changes, so the two filters combine */
  topic: string;
}) {
  const router = useRouter();
  if (teams.length === 0) return null;

  // teams are grouped by division (Risk, Technology, …) so a long list stays scannable
  const divisions = [...new Set(teams.map((t) => t.division ?? "Other"))];

  function choose(slug: string) {
    const query = new URLSearchParams();
    if (topic) query.set("topic", topic);
    if (slug) query.set("team", slug);
    const qs = query.toString();
    router.push(qs ? `/?${qs}` : "/");
  }

  return (
    <div className="relative shrink-0">
      <PeopleIcon
        width={16}
        height={16}
        aria-hidden="true"
        className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted"
      />
      <select
        value={selected}
        onChange={(e) => choose(e.target.value)}
        aria-label="Filter by team"
        className={`h-9 appearance-none rounded-lg py-0 pl-8 pr-8 text-sm font-medium outline-none focus:border-brand ${
          selected ? "bg-chip-active text-chip-active-text" : "bg-surface hover:bg-surface-hover"
        }`}
      >
        <option value="">All teams</option>
        {divisions.map((division) => (
          <optgroup key={division} label={division}>
            {teams
              .filter((team) => (team.division ?? "Other") === division)
              .map((team) => (
                <option key={team.slug} value={team.slug}>
                  {team.name}
                </option>
              ))}
          </optgroup>
        ))}
      </select>
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <path d="m6 9 6 6 6-6" />
      </svg>
    </div>
  );
}

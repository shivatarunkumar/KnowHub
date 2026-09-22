import Link from "next/link";
import { TeamFilter } from "@/components/TeamFilter";
import { TopicFilter } from "@/components/TopicFilter";
import { VideoCard } from "@/components/VideoCard";
import { getFeed, getTeams, getTopics } from "@/lib/api";

export default async function HomePage({
  searchParams,
}: {
  // topic repeats for a multi-select: ?topic=bigquery&topic=gke
  searchParams: Promise<{ topic?: string | string[]; team?: string }>;
}) {
  const [params, topics, teams] = await Promise.all([searchParams, getTopics(), getTeams()]);
  const selectedTopics = [params.topic ?? []].flat().filter(Boolean);
  const selectedTeam = params.team ?? "";

  const videos = await getFeed({ topics: selectedTopics, team: selectedTeam });
  const team = teams.find((t) => t.slug === selectedTeam);
  const chosen = topics.filter((t) => selectedTopics.includes(t.slug));
  const filtered = chosen.length > 0 || Boolean(team);

  // dropping one topic keeps the rest, and the team
  const withoutTopic = (slug: string) => {
    const query = new URLSearchParams();
    for (const other of selectedTopics.filter((s) => s !== slug)) query.append("topic", other);
    if (selectedTeam) query.set("team", selectedTeam);
    const qs = query.toString();
    return qs ? `/?${qs}` : "/";
  };

  return (
    <div className="px-4 pb-10 lg:px-6">
      <div className="no-scrollbar sticky top-14 z-20 -mx-4 flex items-center gap-2 overflow-x-auto bg-bg px-4 py-3 lg:-mx-6 lg:px-6">
        <TeamFilter teams={teams} selected={selectedTeam} topics={selectedTopics} />
        <TopicFilter topics={topics} selected={selectedTopics} team={selectedTeam} />

        {/* what is currently on, and one click to take it off */}
        {chosen.map((topic) => (
          <Link
            key={topic.slug}
            href={withoutTopic(topic.slug)}
            className="flex shrink-0 items-center gap-1 whitespace-nowrap rounded-lg bg-surface px-2.5 py-1.5 text-sm font-medium hover:bg-surface-hover"
          >
            {topic.name}
            <span aria-hidden="true" className="text-muted">
              ×
            </span>
            <span className="sr-only">Remove {topic.name} filter</span>
          </Link>
        ))}

        {filtered && (
          <Link
            href="/"
            className="shrink-0 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-sm font-medium text-brand hover:bg-surface"
          >
            Clear all
          </Link>
        )}
      </div>

      {filtered && (
        <p className="mt-1 text-sm text-muted">
          {videos.length} {videos.length === 1 ? "video" : "videos"}
          {chosen.length > 0 && <> in {chosen.map((t) => t.name).join(" or ")}</>}
          {team && <> from {team.name}</>}
        </p>
      )}

      {videos.length === 0 ? (
        <section className="mx-auto mt-16 max-w-md text-center">
          <h1 className="text-xl">{filtered ? "Nothing matches those filters yet" : "No videos yet"}</h1>
          <p className="mt-2 text-sm text-muted">
            Share a bug fix, an incident resolution or a how-to, and it shows up here.
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Link
              href="/upload"
              className="rounded-full bg-brand px-4 py-2 text-sm font-medium text-brand-contrast hover:bg-brand-hover"
            >
              Upload a video
            </Link>
            {filtered && (
              <Link
                href="/"
                className="rounded-full border border-line px-4 py-2 text-sm font-medium hover:bg-surface"
              >
                Clear filters
              </Link>
            )}
          </div>
        </section>
      ) : (
        <div className="mt-2 grid gap-x-4 gap-y-8 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {videos.map((video) => (
            <VideoCard key={video.id} video={video} />
          ))}
        </div>
      )}
    </div>
  );
}

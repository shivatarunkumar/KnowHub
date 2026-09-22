import Link from "next/link";
import { TeamFilter } from "@/components/TeamFilter";
import { TopicChips } from "@/components/TopicChips";
import { VideoCard } from "@/components/VideoCard";
import { getFeed, getTeams, getTopics } from "@/lib/api";

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ topic?: string; team?: string }>;
}) {
  const [{ topic: selected, team: selectedTeam }, topics, teams] = await Promise.all([
    searchParams,
    getTopics(),
    getTeams(),
  ]);
  const videos = await getFeed({ topic: selected, team: selectedTeam });
  const selectedTopic = topics.find((t) => t.slug === selected);
  const team = teams.find((t) => t.slug === selectedTeam);

  return (
    <div className="px-4 pb-10 lg:px-6">
      <div className="no-scrollbar sticky top-14 z-20 -mx-4 flex items-center gap-3 overflow-x-auto bg-bg px-4 py-3 lg:-mx-6 lg:px-6">
        <TeamFilter teams={teams} selected={selectedTeam ?? ""} topic={selected ?? ""} />
        <span aria-hidden="true" className="h-6 w-px shrink-0 bg-line" />
        <TopicChips topics={topics} selected={selected ?? ""} team={selectedTeam ?? ""} />
      </div>

      {(selectedTopic || team) && (
        <p className="mt-1 text-sm text-muted">
          {videos.length} {videos.length === 1 ? "video" : "videos"}
          {selectedTopic && <> on {selectedTopic.name}</>}
          {team && <> from {team.name}</>}
        </p>
      )}

      {videos.length === 0 ? (
        <section className="mx-auto mt-16 max-w-md text-center">
          <h1 className="text-xl">
            {team && selectedTopic
              ? `Nothing from ${team.name} on ${selectedTopic.name} yet`
              : team
                ? `No videos from ${team.name} yet`
                : selectedTopic
                  ? `No ${selectedTopic.name} videos yet`
                  : "No videos yet"}
          </h1>
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
            {(team || selectedTopic) && (
              <Link href="/" className="rounded-full border border-line px-4 py-2 text-sm font-medium hover:bg-surface">
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

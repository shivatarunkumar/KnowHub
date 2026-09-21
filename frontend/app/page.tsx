import Link from "next/link";
import { VideoCard } from "@/components/VideoCard";
import { getFeed, getTopics } from "@/lib/api";

export default async function HomePage({ searchParams }: { searchParams: Promise<{ topic?: string }> }) {
  const [{ topic: selected }, topics] = await Promise.all([searchParams, getTopics()]);
  const videos = await getFeed({ topic: selected });
  const selectedTopic = topics.find((t) => t.slug === selected);

  return (
    <div className="px-4 pb-10 lg:px-6">
      <div className="no-scrollbar sticky top-14 z-20 -mx-4 flex gap-3 overflow-x-auto bg-bg px-4 py-3 lg:-mx-6 lg:px-6">
        <Chip href="/" label="All" active={!selectedTopic} />
        {topics.map((t) => (
          <Chip key={t.slug} href={`/?topic=${t.slug}`} label={t.name} active={t.slug === selected} />
        ))}
      </div>

      {videos.length === 0 ? (
        <section className="mx-auto mt-16 max-w-md text-center">
          <h1 className="text-xl font-semibold">
            {selectedTopic ? `No ${selectedTopic.name} videos yet` : "No videos yet"}
          </h1>
          <p className="mt-2 text-sm text-muted">
            Share a bug fix, an incident resolution or a how-to, and it shows up here.
          </p>
          <Link
            href="/upload"
            className="mt-6 inline-block rounded-full bg-brand px-4 py-2 text-sm font-medium text-brand-contrast hover:bg-brand-hover"
          >
            Upload a video
          </Link>
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

function Chip({ href, label, active }: { href: string; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`shrink-0 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium ${
        active ? "bg-chip-active text-chip-active-text" : "bg-surface hover:bg-surface-hover"
      }`}
    >
      {label}
    </Link>
  );
}

import { cookies } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChannelVideos } from "@/components/ChannelVideos";
import { formatViews, getChannel, getTopics } from "@/lib/api";

export default async function ChannelPage({ params }: { params: Promise<{ handle: string }> }) {
  const { handle } = await params;
  const cookieHeader = (await cookies()).toString();
  const [channel, topics] = await Promise.all([
    getChannel(decodeURIComponent(handle), cookieHeader),
    getTopics(),
  ]);
  if (!channel) notFound();

  const initial = channel.display_name.trim().charAt(0).toUpperCase();

  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-12 pt-4 lg:px-6">
      {/* banner: a drawn one for now, so the page has a shape before avatars exist */}
      <div
        aria-hidden="true"
        className="h-24 w-full rounded-xl sm:h-36"
        style={{ background: "linear-gradient(120deg, var(--brand), hsl(265 60% 45%))" }}
      />

      <header className="mt-4 flex flex-wrap items-center gap-4">
        <span className="flex h-20 w-20 items-center justify-center rounded-full bg-brand text-2xl font-semibold text-brand-contrast">
          {initial}
        </span>
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold">{channel.display_name}</h1>
          <p className="text-sm text-muted">
            @{channel.handle} · {channel.video_count} {channel.video_count === 1 ? "video" : "videos"} ·{" "}
            {formatViews(channel.total_views)}
          </p>
          {channel.bio && <p className="mt-1 max-w-2xl text-sm text-muted">{channel.bio}</p>}
        </div>

        {channel.is_me && (
          <Link
            href="/upload"
            className="ml-auto rounded-full bg-brand px-4 py-2 text-sm font-medium text-brand-contrast hover:bg-brand-hover"
          >
            Upload
          </Link>
        )}
      </header>

      <div className="mt-6 border-b border-line">
        <span className="inline-block border-b-2 border-fg pb-2 text-sm font-medium">Videos</span>
      </div>

      {channel.is_me && channel.video_count > 0 && (
        <p className="mt-4 text-sm text-muted">
          This is your channel. Only you see the controls, the hidden videos and the uploads that are
          still processing.
        </p>
      )}

      <ChannelVideos videos={channel.videos} topics={topics} isMe={channel.is_me} />
    </div>
  );
}

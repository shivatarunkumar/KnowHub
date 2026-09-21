import { cookies } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Comments } from "@/components/Comments";
import { VideoActions } from "@/components/VideoActions";
import { VideoResources } from "@/components/VideoResources";
import { VideoRow } from "@/components/VideoRow";
import { VideoPlayer } from "@/components/VideoPlayer";
import { CATEGORY_LABELS, formatViews, getFeed, getReaction, getVideo, timeAgo } from "@/lib/api";
import { getCurrentUser } from "@/lib/session";

export default async function WatchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const cookieHeader = (await cookies()).toString();
  const [video, user] = await Promise.all([getVideo(id, cookieHeader), getCurrentUser()]);
  if (!video) notFound();

  // "Up next": videos on the same topic first, then anything else recent, so the
  // sidebar is never empty just because a topic has one video in it.
  const [reaction, sameTopic, everything] = await Promise.all([
    getReaction(id, cookieHeader),
    video.topic_slug ? getFeed({ topic: video.topic_slug }) : Promise.resolve([]),
    getFeed(),
  ]);

  const seen = new Set([video.id]);
  const upNext = [...sameTopic, ...everything]
    .filter((item) => !seen.has(item.id) && seen.add(item.id))
    .slice(0, 12);
  const sameTopicCount = upNext.filter((item) => item.topic_slug === video.topic_slug).length;

  return (
    <div className="mx-auto grid max-w-[1600px] gap-6 px-4 py-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:px-6">
      <div className="min-w-0">
        <VideoPlayer videoId={video.id} />

        <h1 className="mt-4 text-xl font-semibold leading-snug">{video.title}</h1>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-brand text-sm font-semibold text-brand-contrast">
            {(video.owner_display_name ?? "?").charAt(0).toUpperCase()}
          </span>
          <Link href={`/channel/${video.owner_handle}`} className="mr-auto">
            <p className="font-medium hover:underline">{video.owner_display_name}</p>
            <p className="text-sm text-muted">@{video.owner_handle}</p>
          </Link>
          {user?.id === video.owner_id && (
            <Link
              href={`/channel/${video.owner_handle}`}
              className="rounded-full border border-line px-3 py-1.5 text-sm font-medium hover:bg-surface"
            >
              Manage
            </Link>
          )}
          <VideoActions
            videoId={video.id}
            videoTitle={video.title}
            initial={reaction}
            user={user}
          />
        </div>

        <div className="mt-4 rounded-xl bg-surface p-4">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">
              {formatViews(video.view_count)} · {timeAgo(video.published_at ?? video.created_at)}
            </span>
            {video.topic_slug && (
              <Link
                href={`/?topic=${video.topic_slug}`}
                className="rounded-full bg-bg px-2.5 py-0.5 text-xs font-medium hover:bg-surface-hover"
              >
                {video.topic_name}
              </Link>
            )}
            <span className="rounded-full bg-bg px-2.5 py-0.5 text-xs">
              {CATEGORY_LABELS[video.category] ?? video.category}
            </span>
          </div>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">
            {video.description || "No description."}
          </p>
        </div>

        <VideoResources links={video.links ?? []} snippets={video.snippets ?? []} />

        <Comments
          videoId={video.id}
          count={video.comment_count}
          user={user}
          isUploader={user?.id === video.owner_id}
          enabled={video.comments_enabled}
        />
      </div>

      <aside className="min-w-0">
        <h2 className="mb-3 font-semibold">Up next</h2>

        {upNext.length === 0 ? (
          <div className="rounded-xl bg-surface p-4 text-sm text-muted">
            <p>This is the only video so far.</p>
            <Link href="/upload" className="mt-2 inline-block font-medium text-brand hover:underline">
              Share a fix →
            </Link>
          </div>
        ) : (
          <div className="grid gap-4">
            {upNext.map((item, index) => (
              <div key={item.id}>
                {video.topic_name && index === sameTopicCount && sameTopicCount > 0 && (
                  <p className="mb-3 mt-2 text-xs font-medium uppercase tracking-wide text-muted">
                    More from KnowHub
                  </p>
                )}
                {video.topic_name && index === 0 && (
                  <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">
                    {sameTopicCount > 0 ? `More on ${video.topic_name}` : "More from KnowHub"}
                  </p>
                )}
                <VideoRow video={item} />
              </div>
            ))}
          </div>
        )}
      </aside>
    </div>
  );
}

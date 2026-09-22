"use client";

import { useRouter } from "next/navigation";
import { type DragEvent, type FormEvent, useRef, useState } from "react";
import { CATEGORY_LABELS, type Team, type Topic } from "@/lib/api";
import { captureFrame, probeVideo, uploadThumbnail } from "@/lib/thumbnail";
import { type UploadProgress, UploadError, formatBytes, uploadVideo } from "@/lib/upload";
import { AiAssist } from "./AiAssist";
import { type LinkDraft, type SnippetDraft, ResourceFields } from "./ResourceFields";
import { UploadProgressCard } from "./UploadProgress";

const CATEGORIES = Object.entries(CATEGORY_LABELS);

const VISIBILITIES = [
  { value: "internal", label: "Everyone at the company", hint: "Shows on Home and in search" },
  { value: "unlisted", label: "Unlisted", hint: "Only people with the link" },
  { value: "private", label: "Private", hint: "Only you" },
];

export function UploadForm({
  topics,
  teams,
  defaultTeamSlug = "",
}: {
  topics: Topic[];
  teams: Team[];
  /** the uploader's own team, remembered from their last upload */
  defaultTeamSlug?: string;
}) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState<"video" | "short">("video");
  const [topicSlug, setTopicSlug] = useState("");
  const [teamSlug, setTeamSlug] = useState(defaultTeamSlug);
  const [category, setCategory] = useState("bug_fix");
  const [visibility, setVisibility] = useState("internal");
  const [links, setLinks] = useState<LinkDraft[]>([]);
  const [snippets, setSnippets] = useState<SnippetDraft[]>([]);
  const [probe, setProbe] = useState<{ durationSec: number; width: number; height: number } | null>(null);
  const [posterUrl, setPosterUrl] = useState<string | null>(null);
  const [posterBlob, setPosterBlob] = useState<Blob | null>(null);
  const [posterAt, setPosterAt] = useState(0);
  const [capturing, setCapturing] = useState(false);

  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [stage, setStage] = useState<"idle" | "uploading" | "finishing" | "done">("idle");
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  function chooseFile(next: File | null) {
    setError("");
    if (!next) return;
    if (!next.type.startsWith("video/")) {
      setError(`That file is ${next.type || "not a video"}. Choose a video file.`);
      return;
    }
    setFile(next);
    if (!title) setTitle(next.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ").slice(0, 200));
    void prepareThumbnail(next);
  }

  /** Read duration and dimensions, and grab a frame a little way in as the poster. */
  async function prepareThumbnail(video: File) {
    setCapturing(true);
    try {
      const details = await probeVideo(video);
      setProbe(details);
      const at = details.durationSec > 4 ? details.durationSec * 0.1 : 0;
      setPosterAt(at);
      await grabFrame(video, at);
    } catch {
      setProbe(null); // unreadable codec: the card falls back to a drawn cover
    } finally {
      setCapturing(false);
    }
  }

  async function grabFrame(video: File, at: number) {
    const blob = await captureFrame(video, at);
    if (!blob) return;
    setPosterBlob(blob);
    setPosterUrl((old) => {
      if (old) URL.revokeObjectURL(old);
      return URL.createObjectURL(blob);
    });
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files?.[0] ?? null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!file) {
      setError("Choose a video file first.");
      return;
    }
    if (!title.trim()) {
      setError("Give your video a title.");
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    setStage("uploading");
    setProgress(null);

    try {
      const video = await uploadVideo({
        file,
        metadata: {
          title: title.trim(),
          description: description.trim(),
          type,
          category,
          topic_slug: topicSlug,
          team_slug: teamSlug,
          visibility,
          duration_sec: probe?.durationSec ?? null,
          width: probe?.width ?? null,
          height: probe?.height ?? null,
          links: links
            .filter((link) => link.url.trim())
            .map((link) => ({ kind: link.kind, url: link.url.trim(), label: link.label.trim() || null })),
          snippets: snippets
            .filter((snippet) => snippet.code.trim())
            .map((snippet) => ({
              title: snippet.title.trim() || null,
              language: snippet.language,
              code: snippet.code,
            })),
        },
        onProgress: (next) => {
          setProgress(next);
          if (next.percent >= 100) setStage("finishing");
        },
        signal: controller.signal,
      });
      if (posterBlob) await uploadThumbnail(video.id, posterBlob);
      setStage("done");
      router.push(`/watch/${video.id}`);
      router.refresh();
    } catch (uploadError) {
      setStage("idle");
      setProgress(null);
      setError(
        uploadError instanceof UploadError
          ? uploadError.message
          : "Upload failed. Please try again.",
      );
    } finally {
      abortRef.current = null;
    }
  }

  function cancel() {
    abortRef.current?.abort();
    setStage("idle");
    setProgress(null);
    setError("Upload cancelled.");
  }

  const uploading = stage !== "idle";
  const topicName = topics.find((t) => t.slug === topicSlug)?.name ?? "";
  const categoryLabel = CATEGORY_LABELS[category] ?? category;

  return (
    <form onSubmit={submit} className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Share a fix</h1>
      <p className="mt-1 text-sm text-muted">
        Record how you solved something once, and save the next person the same afternoon.
      </p>

      {error && (
        <p role="alert" className="mt-6 rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">
          {error}
        </p>
      )}

      {/* file */}
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`mt-6 flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center ${
          dragging ? "border-brand bg-surface" : "border-line hover:bg-surface"
        }`}
      >
        <span className="text-3xl">⬆</span>
        {file ? (
          <>
            <span className="font-medium">{file.name}</span>
            <span className="text-sm text-muted">{formatBytes(file.size)} · click to change</span>
          </>
        ) : (
          <>
            <span className="font-medium">Drag a video here, or click to choose</span>
            <span className="text-sm text-muted">MP4, MOV or WebM</span>
          </>
        )}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="video/*"
        className="hidden"
        onChange={(e) => chooseFile(e.target.files?.[0] ?? null)}
      />

      {file && (posterUrl || capturing) && (
        <section className="mt-4 flex flex-wrap items-center gap-4 rounded-xl border border-line p-3">
          <div className="w-44 shrink-0 overflow-hidden rounded-lg bg-surface">
            {posterUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={posterUrl} alt="Chosen thumbnail" className="aspect-video w-full object-cover" />
            ) : (
              <div className="aspect-video w-full upload-pulse" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">Thumbnail</p>
            <p className="mt-0.5 text-xs text-muted">
              {capturing
                ? "Grabbing a frame…"
                : probe?.durationSec
                  ? "Drag to pick the frame people see on the home page."
                  : "Couldn't read a frame from this file; KnowHub will draw a cover instead."}
            </p>
            {probe && probe.durationSec > 1 && (
              <input
                type="range"
                min={0}
                max={probe.durationSec}
                step={0.5}
                value={posterAt}
                aria-label="Thumbnail frame"
                onChange={(e) => setPosterAt(Number(e.target.value))}
                onMouseUp={() => file && grabFrame(file, posterAt)}
                onTouchEnd={() => file && grabFrame(file, posterAt)}
                onKeyUp={() => file && grabFrame(file, posterAt)}
                className="mt-3 w-full accent-[var(--brand)]"
              />
            )}
          </div>
        </section>
      )}

      {uploading && (
        <UploadProgressCard
          fileName={file?.name ?? "video"}
          progress={progress}
          stage={stage}
          onCancel={cancel}
        />
      )}

      {/* details */}
      <div className="mt-8 grid gap-5">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="video-title" className="text-sm font-medium">
            Title
          </label>
          <div className="relative">
            <input
              id="video-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              placeholder="Fixed BigQuery slot contention on the nightly load"
              className="h-11 w-full rounded-lg border border-line bg-bg pl-3 pr-12 outline-none focus:border-brand"
            />
            <AiAssist
              field="title"
              value={title}
              context={{ topic: topicName, category: categoryLabel, type }}
              onAccept={setTitle}
              size="sm"
              inset
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="video-description" className="text-sm font-medium">
            Description
          </label>
          <div className="relative">
            <textarea
              id="video-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={6}
              placeholder={"What broke?\nWhat was the root cause?\nHow did you fix it?\nWhat should others remember?"}
              className="w-full rounded-lg border border-line bg-bg py-2 pl-3 pr-12 outline-none focus:border-brand"
            />
            <AiAssist
              field="description"
              value={description}
              context={{ title, topic: topicName, category: categoryLabel, type }}
              onAccept={setDescription}
              size="sm"
              inset
            />
          </div>
          <span className="text-xs text-muted">
            Problem, root cause, fix, takeaways. The ✨ button tidies up your wording.
          </span>
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">Type</span>
            <select
              value={type}
              onChange={(e) => setType(e.target.value as "video" | "short")}
              className="h-10 rounded-lg border border-line bg-bg px-3 outline-none focus:border-brand"
            >
              <option value="video">Video</option>
              <option value="short">Short (under a minute)</option>
            </select>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">Category</span>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="h-10 rounded-lg border border-line bg-bg px-3 outline-none focus:border-brand"
            >
              {CATEGORIES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">Topic</span>
            <select
              value={topicSlug}
              onChange={(e) => setTopicSlug(e.target.value)}
              className="h-10 rounded-lg border border-line bg-bg px-3 outline-none focus:border-brand"
            >
              <option value="">No topic</option>
              {topics.map((topic) => (
                <option key={topic.slug} value={topic.slug}>
                  {topic.name}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">Team</span>
            <select
              value={teamSlug}
              onChange={(e) => setTeamSlug(e.target.value)}
              className="h-10 rounded-lg border border-line bg-bg px-3 outline-none focus:border-brand"
            >
              <option value="">No team</option>
              {teams.map((team) => (
                <option key={team.slug} value={team.slug}>
                  {team.name}
                </option>
              ))}
            </select>
            <span className="text-xs text-muted">Who this came from — people can filter by it</span>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">Who can watch</span>
            <select
              value={visibility}
              onChange={(e) => setVisibility(e.target.value)}
              className="h-10 rounded-lg border border-line bg-bg px-3 outline-none focus:border-brand"
            >
              {VISIBILITIES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <span className="text-xs text-muted">
              {VISIBILITIES.find((v) => v.value === visibility)?.hint}
            </span>
          </label>
        </div>
      </div>

      <ResourceFields links={links} setLinks={setLinks} snippets={snippets} setSnippets={setSnippets} />

      <div className="mt-8 flex items-center gap-3">
        <button
          type="submit"
          disabled={uploading}
          className="h-10 rounded-full bg-brand px-5 text-sm font-medium text-brand-contrast hover:bg-brand-hover disabled:opacity-60"
        >
          {stage === "uploading" ? "Uploading…" : stage === "finishing" ? "Publishing…" : "Publish"}
        </button>
        <span className="text-sm text-muted">
          Large files are sent straight to storage in chunks, and a dropped chunk retries on its own.
        </span>
      </div>
    </form>
  );
}

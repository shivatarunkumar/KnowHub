"use client";

import { useEffect, useRef, useState } from "react";
import { CATEGORY_LABELS, type Person, type Topic, type Video } from "@/lib/api";
import { AiAssist } from "./AiAssist";
import { type LinkDraft, ResourceFields, type SnippetDraft } from "./ResourceFields";
import { CloseIcon, GlobeIcon, LinkIcon, LockIcon, PeopleIcon, SpinnerIcon, TrashIcon } from "./icons";

const VISIBILITIES = [
  {
    value: "internal",
    label: "Everyone",
    hint: "Anyone on KnowHub can find and watch it.",
    icon: GlobeIcon,
  },
  {
    value: "unlisted",
    label: "Anyone with the link",
    hint: "Hidden from the home feed, search and your channel.",
    icon: LinkIcon,
  },
  {
    value: "restricted",
    label: "Specific people",
    hint: "Only the people you list below can watch it.",
    icon: PeopleIcon,
  },
  {
    value: "private",
    label: "Only you",
    hint: "Switched off for everyone else, but kept in your channel.",
    icon: LockIcon,
  },
];

/**
 * The owner's controls for one of their videos: fix the wording, change who can see it,
 * turn comments off, or take it down. Opened from the channel page.
 */
export function VideoManageDialog({
  video,
  topics,
  onSaved,
  onDeleted,
  onClose,
}: {
  video: Video;
  topics: Topic[];
  onSaved: (video: Video) => void;
  onDeleted: (id: string) => void;
  onClose: () => void;
}) {
  const [title, setTitle] = useState(video.title);
  const [description, setDescription] = useState(video.description ?? "");
  const [category, setCategory] = useState(video.category);
  const [topicSlug, setTopicSlug] = useState(video.topic_slug ?? "");
  const [visibility, setVisibility] = useState(video.visibility);
  const [commentsEnabled, setCommentsEnabled] = useState(video.comments_enabled);
  const [people, setPeople] = useState<Person[]>(video.allowed_viewers ?? []);
  const [links, setLinks] = useState<LinkDraft[]>([]);
  const [snippets, setSnippets] = useState<SnippetDraft[]>([]);

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState("");
  const titleRef = useRef<HTMLInputElement>(null);

  // The channel list carries no links or snippets, so load the full video before editing:
  // saving replaces both lists, and we must not wipe what we never showed.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/v1/videos/${video.id}`, { cache: "no-store" });
        if (res.ok && !cancelled) {
          const full = (await res.json()) as Video;
          setLinks((full.links ?? []).map((l) => ({ kind: l.kind, url: l.url, label: l.label ?? "" })));
          setSnippets(
            (full.snippets ?? []).map((s) => ({
              title: s.title ?? "",
              language: s.language,
              code: s.code,
            })),
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [video.id]);

  useEffect(() => titleRef.current?.focus(), []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) {
      setResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/v1/users/search?q=${encodeURIComponent(term)}`);
        if (res.ok) setResults(await res.json());
      } catch {
        /* the list just stays empty */
      }
    }, 200);
    return () => clearTimeout(timer);
  }, [query]);

  async function save() {
    setError("");
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        title: title.trim(),
        description: description.trim(),
        category,
        topic_slug: topicSlug,
        visibility,
        comments_enabled: commentsEnabled,
        links: links
          .filter((l) => l.url.trim())
          .map((l) => ({ kind: l.kind, url: l.url.trim(), label: l.label.trim() || null })),
        snippets: snippets
          .filter((s) => s.code.trim())
          .map((s) => ({ title: s.title.trim() || null, language: s.language, code: s.code })),
      };
      // only sent when it applies, so switching away and back remembers the list
      if (visibility === "restricted") payload.viewer_ids = people.map((p) => p.id);

      const res = await fetch(`/api/v1/videos/${video.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        setError(body?.detail?.message ?? "Couldn't save those changes.");
        return;
      }
      onSaved({ ...(body as Video), allowed_viewers: visibility === "restricted" ? people : [] });
    } catch {
      setError("Couldn't save those changes.");
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    setError("");
    setSaving(true);
    try {
      const res = await fetch(`/api/v1/videos/${video.id}`, { method: "DELETE" });
      if (!res.ok && res.status !== 204) {
        setError("Couldn't delete this video.");
        return;
      }
      onDeleted(video.id);
    } catch {
      setError("Couldn't delete this video.");
    } finally {
      setSaving(false);
    }
  }

  const available = results.filter((person) => !people.some((p) => p.id === person.id));

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4 py-10">
      <button type="button" aria-label="Close" className="fixed inset-0 bg-black/50" onClick={onClose} />

      <div
        role="dialog"
        aria-modal="true"
        aria-label="Manage video"
        className="relative w-full max-w-2xl overflow-hidden rounded-2xl border border-line bg-bg shadow-2xl"
      >
        <header className="sticky top-0 z-10 flex items-center gap-2 border-b border-line bg-bg px-5 py-3">
          <h2 className="font-semibold">Manage video</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="ml-auto rounded-full p-1 text-muted hover:bg-surface-hover"
          >
            <CloseIcon width={18} height={18} />
          </button>
        </header>

        <div className="px-5 py-4">
          {/* wording */}
          <label htmlFor="manage-title" className="text-sm font-medium">
            Title
          </label>
          <div className="relative mt-1">
            <input
              id="manage-title"
              ref={titleRef}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              className="h-10 w-full rounded-lg border border-line bg-bg pl-3 pr-12 text-sm outline-none focus:border-brand"
            />
            <AiAssist
              field="title"
              value={title}
              context={{ topic: topicSlug, category, type: video.type }}
              onAccept={setTitle}
              size="sm"
              inset
            />
          </div>

          <label htmlFor="manage-description" className="mt-4 block text-sm font-medium">
            Description
          </label>
          <div className="relative mt-1">
            <textarea
              id="manage-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={5}
              className="w-full resize-y rounded-lg border border-line bg-bg py-2 pl-3 pr-12 text-sm outline-none focus:border-brand"
            />
            <AiAssist
              field="description"
              value={description}
              context={{ title, topic: topicSlug, category, type: video.type }}
              onAccept={setDescription}
              size="sm"
              inset
            />
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="manage-topic" className="text-sm font-medium">
                Topic
              </label>
              <select
                id="manage-topic"
                value={topicSlug}
                onChange={(e) => setTopicSlug(e.target.value)}
                className="mt-1 h-10 w-full rounded-lg border border-line bg-bg px-2 text-sm outline-none focus:border-brand"
              >
                <option value="">No topic</option>
                {topics.map((topic) => (
                  <option key={topic.slug} value={topic.slug}>
                    {topic.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="manage-category" className="text-sm font-medium">
                Category
              </label>
              <select
                id="manage-category"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="mt-1 h-10 w-full rounded-lg border border-line bg-bg px-2 text-sm outline-none focus:border-brand"
              >
                {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* who can watch */}
          <fieldset className="mt-6">
            <legend className="text-sm font-medium">Who can watch</legend>
            <div className="mt-2 grid gap-1.5">
              {VISIBILITIES.map(({ value, label, hint, icon: Icon }) => (
                <label
                  key={value}
                  className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm ${
                    visibility === value ? "border-brand bg-surface" : "border-line hover:bg-surface"
                  }`}
                >
                  <input
                    type="radio"
                    name="visibility"
                    value={value}
                    checked={visibility === value}
                    onChange={() => setVisibility(value)}
                    className="sr-only"
                  />
                  <Icon width={18} height={18} className="mt-0.5 shrink-0 text-muted" />
                  <span>
                    <span className="font-medium">{label}</span>
                    <span className="block text-xs text-muted">{hint}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          {visibility === "restricted" && (
            <div className="mt-3 rounded-lg border border-line p-3">
              <label htmlFor="manage-people" className="text-sm font-medium">
                People who can watch
              </label>
              {people.length > 0 && (
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {people.map((person) => (
                    <li key={person.id}>
                      <button
                        type="button"
                        onClick={() => setPeople(people.filter((p) => p.id !== person.id))}
                        className="flex items-center gap-1 rounded-full bg-surface px-2.5 py-1 text-xs hover:bg-surface-hover"
                      >
                        {person.display_name}
                        <CloseIcon width={12} height={12} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <input
                id="manage-people"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by name or @handle"
                className="mt-2 h-10 w-full rounded-lg border border-line bg-bg px-3 text-sm outline-none focus:border-brand"
              />
              {available.length > 0 && (
                <ul className="mt-2 max-h-40 overflow-y-auto rounded-lg border border-line">
                  {available.map((person) => (
                    <li key={person.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setPeople([...people, person]);
                          setQuery("");
                          setResults([]);
                        }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface-hover"
                      >
                        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand text-xs font-semibold text-brand-contrast">
                          {person.display_name.charAt(0).toUpperCase()}
                        </span>
                        <span className="truncate">{person.display_name}</span>
                        <span className="truncate text-xs text-muted">@{person.handle}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {people.length === 0 && (
                <p className="mt-2 text-xs text-muted">
                  Nobody yet — with an empty list, only you can watch this video.
                </p>
              )}
            </div>
          )}

          {/* comments */}
          <div className="mt-6 flex items-start gap-3 rounded-lg border border-line p-3">
            <input
              id="manage-comments"
              type="checkbox"
              checked={commentsEnabled}
              onChange={(e) => setCommentsEnabled(e.target.checked)}
              className="mt-0.5 h-4 w-4 accent-[var(--brand)]"
            />
            <label htmlFor="manage-comments" className="text-sm">
              <span className="font-medium">Allow comments</span>
              <span className="block text-xs text-muted">
                Turn this off and nobody can add new comments. The ones already there stay readable.
              </span>
            </label>
          </div>

          {loading ? (
            <p className="mt-6 flex items-center gap-2 text-sm text-muted">
              <SpinnerIcon /> Loading links and snippets…
            </p>
          ) : (
            <ResourceFields links={links} setLinks={setLinks} snippets={snippets} setSnippets={setSnippets} />
          )}

          {error && <p className="mt-4 text-sm text-bad">{error}</p>}
        </div>

        <footer className="sticky bottom-0 flex flex-wrap items-center gap-2 border-t border-line bg-bg px-5 py-3">
          {confirmDelete ? (
            <>
              <span className="text-sm text-bad">Delete this video for good?</span>
              <button
                type="button"
                onClick={remove}
                disabled={saving}
                className="rounded-full bg-bad px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              >
                Yes, delete
              </button>
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                className="rounded-full px-3 py-2 text-sm font-medium hover:bg-surface-hover"
              >
                Keep it
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() => setConfirmDelete(true)}
                className="flex items-center gap-1.5 rounded-full px-3 py-2 text-sm font-medium text-bad hover:bg-surface-hover"
              >
                <TrashIcon width={16} height={16} /> Delete
              </button>
              <button
                type="button"
                onClick={onClose}
                className="ml-auto rounded-full px-4 py-2 text-sm font-medium hover:bg-surface-hover"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={save}
                disabled={saving || !title.trim() || loading}
                className="rounded-full bg-brand px-5 py-2 text-sm font-medium text-brand-contrast hover:bg-brand-hover disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save changes"}
              </button>
            </>
          )}
        </footer>
      </div>
    </div>
  );
}

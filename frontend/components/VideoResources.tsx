"use client";

import { useState } from "react";

export type VideoLink = { id: string; kind: string; url: string; label: string | null };
export type VideoSnippet = { id: string; title: string | null; language: string; code: string };

const KIND_LABELS: Record<string, string> = {
  confluence: "Confluence",
  repo: "Git repo",
  pr: "Pull request",
  doc: "Doc",
  jira: "Jira",
  incident: "Incident",
  other: "Link",
};

/** Links and copyable code attached to a video, so nobody retypes from the screen. */
export function VideoResources({
  links,
  snippets,
}: {
  links: VideoLink[];
  snippets: VideoSnippet[];
}) {
  if (links.length === 0 && snippets.length === 0) return null;

  return (
    <section className="mt-4 rounded-xl border border-line p-4">
      <h2 className="text-sm font-semibold">Resources</h2>

      {links.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2">
          {links.map((link) => (
            <li key={link.id}>
              <a
                href={link.url}
                target="_blank"
                rel="noreferrer noopener"
                className="flex items-center gap-2 rounded-full bg-surface px-3 py-1.5 text-sm hover:bg-surface-hover"
              >
                <span className="font-medium">{link.label || KIND_LABELS[link.kind] || "Link"}</span>
                <span className="max-w-56 truncate text-xs text-muted">
                  {link.url.replace(/^https?:\/\//, "")}
                </span>
                <span aria-hidden="true" className="text-xs text-muted">
                  ↗
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}

      {snippets.length > 0 && (
        <ul className="mt-4 grid gap-3">
          {snippets.map((snippet) => (
            <li key={snippet.id}>
              <Snippet snippet={snippet} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Snippet({ snippet }: { snippet: VideoSnippet }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(snippet.code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <figure className="overflow-hidden rounded-lg border border-line">
      <figcaption className="flex items-center gap-2 border-b border-line bg-surface px-3 py-1.5">
        <span className="truncate text-xs font-medium">{snippet.title || "Snippet"}</span>
        <span className="rounded bg-bg px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted">
          {snippet.language}
        </span>
        <button
          type="button"
          onClick={copy}
          className="ml-auto rounded-full px-2.5 py-1 text-xs font-medium hover:bg-surface-hover"
        >
          {copied ? "Copied ✓" : "Copy"}
        </button>
      </figcaption>
      <pre className="max-h-80 overflow-auto bg-surface/40 px-3 py-2 text-xs leading-relaxed">
        <code>{snippet.code}</code>
      </pre>
    </figure>
  );
}

"use client";

import { CloseIcon } from "./icons";

export type LinkDraft = { kind: string; url: string; label: string };
export type SnippetDraft = { title: string; language: string; code: string };

export const LINK_KINDS = [
  { value: "confluence", label: "Confluence" },
  { value: "repo", label: "Git repo" },
  { value: "pr", label: "Pull request" },
  { value: "doc", label: "Doc" },
  { value: "jira", label: "Jira ticket" },
  { value: "incident", label: "Incident" },
  { value: "other", label: "Other" },
];

const LANGUAGES = [
  "text", "bash", "sql", "python", "javascript", "typescript", "java", "go",
  "yaml", "json", "hcl", "dockerfile", "xml",
];

/**
 * Optional extras on the upload form: links to the docs/repo/ticket, and code or config
 * viewers can copy, rather than pausing the video and retyping what's on screen.
 */
export function ResourceFields({
  links,
  setLinks,
  snippets,
  setSnippets,
}: {
  links: LinkDraft[];
  setLinks: (links: LinkDraft[]) => void;
  snippets: SnippetDraft[];
  setSnippets: (snippets: SnippetDraft[]) => void;
}) {
  return (
    <div className="mt-8 rounded-xl border border-line p-4">
      <h2 className="text-sm font-semibold">Resources (optional)</h2>
      <p className="mt-1 text-xs text-muted">
        Save people from copying off the screen: link the runbook or repo, and paste the commands
        or config they&apos;ll need.
      </p>

      {/* links */}
      <div className="mt-4">
        <p className="text-sm font-medium">Links</p>
        {links.length > 0 && (
          <ul className="mt-2 grid gap-2">
            {links.map((link, index) => (
              <li key={index} className="flex flex-wrap items-center gap-2">
                <select
                  value={link.kind}
                  onChange={(e) => setLinks(links.map((l, i) => (i === index ? { ...l, kind: e.target.value } : l)))}
                  aria-label="Link type"
                  className="h-9 rounded-lg border border-line bg-bg px-2 text-sm outline-none focus:border-brand"
                >
                  {LINK_KINDS.map((kind) => (
                    <option key={kind.value} value={kind.value}>
                      {kind.label}
                    </option>
                  ))}
                </select>
                <input
                  value={link.url}
                  onChange={(e) => setLinks(links.map((l, i) => (i === index ? { ...l, url: e.target.value } : l)))}
                  placeholder="https://confluence.company.com/…"
                  aria-label="Link URL"
                  className="h-9 min-w-0 flex-1 rounded-lg border border-line bg-bg px-3 text-sm outline-none focus:border-brand"
                />
                <input
                  value={link.label}
                  onChange={(e) => setLinks(links.map((l, i) => (i === index ? { ...l, label: e.target.value } : l)))}
                  placeholder="Label (optional)"
                  aria-label="Link label"
                  className="h-9 w-40 rounded-lg border border-line bg-bg px-3 text-sm outline-none focus:border-brand"
                />
                <button
                  type="button"
                  onClick={() => setLinks(links.filter((_, i) => i !== index))}
                  aria-label="Remove link"
                  className="rounded-full p-1.5 text-muted hover:bg-surface-hover hover:text-bad"
                >
                  <CloseIcon width={16} height={16} />
                </button>
              </li>
            ))}
          </ul>
        )}
        <button
          type="button"
          onClick={() => setLinks([...links, { kind: "confluence", url: "", label: "" }])}
          className="mt-2 rounded-full border border-line px-3 py-1.5 text-xs font-medium hover:bg-surface"
        >
          + Add link
        </button>
      </div>

      {/* snippets */}
      <div className="mt-6">
        <p className="text-sm font-medium">Code &amp; config</p>
        {snippets.length > 0 && (
          <ul className="mt-2 grid gap-3">
            {snippets.map((snippet, index) => (
              <li key={index} className="rounded-lg border border-line p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    value={snippet.title}
                    onChange={(e) =>
                      setSnippets(snippets.map((s, i) => (i === index ? { ...s, title: e.target.value } : s)))
                    }
                    placeholder="What is this? (optional)"
                    aria-label="Snippet title"
                    className="h-9 min-w-0 flex-1 rounded-lg border border-line bg-bg px-3 text-sm outline-none focus:border-brand"
                  />
                  <select
                    value={snippet.language}
                    onChange={(e) =>
                      setSnippets(snippets.map((s, i) => (i === index ? { ...s, language: e.target.value } : s)))
                    }
                    aria-label="Language"
                    className="h-9 rounded-lg border border-line bg-bg px-2 text-sm outline-none focus:border-brand"
                  >
                    {LANGUAGES.map((language) => (
                      <option key={language} value={language}>
                        {language}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => setSnippets(snippets.filter((_, i) => i !== index))}
                    aria-label="Remove snippet"
                    className="rounded-full p-1.5 text-muted hover:bg-surface-hover hover:text-bad"
                  >
                    <CloseIcon width={16} height={16} />
                  </button>
                </div>
                <textarea
                  value={snippet.code}
                  onChange={(e) =>
                    setSnippets(snippets.map((s, i) => (i === index ? { ...s, code: e.target.value } : s)))
                  }
                  rows={5}
                  spellCheck={false}
                  placeholder="bq mk --table project:dataset.table schema.json"
                  aria-label="Code"
                  className="mt-2 w-full resize-y rounded-lg border border-line bg-surface px-3 py-2 font-mono text-xs outline-none focus:border-brand"
                />
              </li>
            ))}
          </ul>
        )}
        <button
          type="button"
          onClick={() => setSnippets([...snippets, { title: "", language: "bash", code: "" }])}
          className="mt-2 rounded-full border border-line px-3 py-1.5 text-xs font-medium hover:bg-surface"
        >
          + Add code snippet
        </button>
      </div>
    </div>
  );
}

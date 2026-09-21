"use client";

import { useEffect, useRef, useState } from "react";
import { CloseIcon } from "./icons";

type Person = { id: string; display_name: string; handle: string };

/** Share inside KnowHub: pick colleagues, or copy the link. */
export function ShareDialog({
  videoId,
  videoTitle,
  onClose,
}: {
  videoId: string;
  videoTitle: string;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Person[]>([]);
  const [chosen, setChosen] = useState<Person[]>([]);
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const link = typeof window === "undefined" ? "" : `${window.location.origin}/watch/${videoId}`;

  useEffect(() => searchRef.current?.focus(), []);

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
    }, 200); // debounce so we don't search on every keystroke
    return () => clearTimeout(timer);
  }, [query]);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Couldn't copy. Select the link and copy it manually.");
    }
  }

  async function send() {
    setError("");
    setStatus("sending");
    try {
      const res = await fetch(`/api/v1/videos/${videoId}/share`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          to_user_ids: chosen.map((person) => person.id),
          message: message.trim() || null,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        setError(body?.detail?.message ?? "Couldn't share. Please try again.");
        setStatus("idle");
        return;
      }
      setStatus("sent");
      setTimeout(onClose, 1200);
    } catch {
      setError("Couldn't share. Please try again.");
      setStatus("idle");
    }
  }

  const available = results.filter((person) => !chosen.some((c) => c.id === person.id));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button type="button" aria-label="Close" className="absolute inset-0 bg-black/50" onClick={onClose} />

      <div
        role="dialog"
        aria-modal="true"
        aria-label="Share video"
        className="relative w-full max-w-md overflow-hidden rounded-2xl border border-line bg-bg shadow-2xl"
      >
        <header className="flex items-center gap-2 border-b border-line px-4 py-3">
          <h2 className="font-semibold">Share</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="ml-auto rounded-full p-1 text-muted hover:bg-surface-hover"
          >
            <CloseIcon width={18} height={18} />
          </button>
        </header>

        <div className="px-4 py-4">
          <p className="mb-3 line-clamp-1 text-sm text-muted">{videoTitle}</p>

          {status === "sent" ? (
            <p className="py-6 text-center text-sm font-medium text-ok">Shared ✓</p>
          ) : (
            <>
              <label htmlFor="share-people" className="text-sm font-medium">
                Share with
              </label>
              {chosen.length > 0 && (
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {chosen.map((person) => (
                    <li key={person.id}>
                      <button
                        type="button"
                        onClick={() => setChosen(chosen.filter((c) => c.id !== person.id))}
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
                id="share-people"
                ref={searchRef}
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
                          setChosen([...chosen, person]);
                          setQuery("");
                          setResults([]);
                          searchRef.current?.focus();
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

              {chosen.length > 0 && (
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  rows={2}
                  placeholder="Add a message (optional)"
                  className="mt-3 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm outline-none focus:border-brand"
                />
              )}

              {error && <p className="mt-2 text-xs text-bad">{error}</p>}

              <button
                type="button"
                onClick={send}
                disabled={chosen.length === 0 || status === "sending"}
                className="mt-3 h-10 w-full rounded-full bg-brand text-sm font-medium text-brand-contrast hover:bg-brand-hover disabled:opacity-50"
              >
                {status === "sending"
                  ? "Sharing…"
                  : chosen.length
                    ? `Share with ${chosen.length} ${chosen.length === 1 ? "person" : "people"}`
                    : "Choose people to share with"}
              </button>
            </>
          )}

          <div className="mt-4 border-t border-line pt-4">
            <p className="text-sm font-medium">Or copy the link</p>
            <div className="mt-2 flex gap-2">
              <input
                readOnly
                value={link}
                onFocus={(e) => e.target.select()}
                className="h-9 flex-1 truncate rounded-lg border border-line bg-surface px-3 text-xs"
              />
              <button
                type="button"
                onClick={copyLink}
                className="h-9 rounded-full bg-surface px-4 text-xs font-medium hover:bg-surface-hover"
              >
                {copied ? "Copied ✓" : "Copy"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

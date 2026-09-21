"use client";

import { useEffect, useRef, useState } from "react";
import { CloseIcon, RetryIcon, SparkleIcon, SpinnerIcon } from "./icons";

type Field = "title" | "description" | "comment";

type Context = { title?: string; topic?: string; category?: string; type?: string };

/**
 * Icon-only "improve with AI" button with the suggestion in a dropdown beneath it.
 * The suggestion never touches the field until the author picks "Use this".
 */
export function AiAssist({
  field,
  value,
  context,
  onAccept,
  size = "md",
  align = "right",
  inset = false,
}: {
  field: Field;
  value: string;
  context: Context;
  onAccept: (text: string) => void;
  size?: "sm" | "md";
  align?: "left" | "right";
  /** true = sit inside the input/textarea, top-right */
  inset?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [suggestion, setSuggestion] = useState("");
  const [requestId, setRequestId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!wrapperRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  async function improve() {
    setOpen(true);
    setError("");
    setSuggestion("");
    if (value.trim().length < 3) {
      setError(`Write a few words in the ${field} first, then I'll tidy them up.`);
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/v1/ai/enhance", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ field, text: value, context }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        setError(body?.detail?.message ?? "The AI assistant isn't available right now.");
        return;
      }
      setSuggestion(body.suggestion);
      setRequestId(body.request_id);
    } catch {
      setError("The AI assistant isn't available right now.");
    } finally {
      setBusy(false);
    }
  }

  function report(accepted: boolean) {
    // fire-and-forget: tells us whether these suggestions are worth keeping
    if (requestId) {
      void fetch("/api/v1/ai/enhance/outcome", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ request_id: requestId, accepted }),
      });
    }
  }

  return (
    <div className={inset ? "absolute right-2 top-2 z-10" : "relative"} ref={wrapperRef}>
      <button
        type="button"
        onClick={improve}
        disabled={busy}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`Improve ${field} with AI`}
        title={`Improve ${field} with AI`}
        className={`flex items-center justify-center rounded-full text-muted transition hover:bg-surface-hover hover:text-brand disabled:opacity-60 ${
          size === "sm" ? "h-7 w-7" : "h-8 w-8"
        } ${open ? "bg-surface text-brand" : ""} ${inset ? "bg-bg/80 backdrop-blur" : ""}`}
      >
        {busy ? <SpinnerIcon width={size === "sm" ? 15 : 18} height={size === "sm" ? 15 : 18} /> : <SparkleIcon width={size === "sm" ? 15 : 18} height={size === "sm" ? 15 : 18} />}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="AI suggestion"
          className={`absolute top-10 z-30 w-[min(30rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-line bg-bg shadow-xl ${
            align === "left" ? "left-0" : "right-0"
          }`}
        >
          <header className="flex items-center gap-2 border-b border-line px-3 py-2">
            <SparkleIcon width={15} height={15} className="text-brand" />
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">
              AI suggestion
            </span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close"
              className="ml-auto rounded-full p-1 text-muted hover:bg-surface-hover"
            >
              <CloseIcon width={15} height={15} />
            </button>
          </header>

          <div className="px-3 py-3">
            {busy && (
              <p className="flex items-center gap-2 py-2 text-sm text-muted">
                <SpinnerIcon /> Rewriting your {field}…
              </p>
            )}

            {!busy && error && <p className="py-1 text-sm text-bad">{error}</p>}

            {!busy && !error && suggestion && (
              <>
                <p className="max-h-64 overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed">
                  {suggestion}
                </p>
                <p className="mt-3 text-xs text-muted">
                  Rewritten from your own words. Check it before using.
                </p>
              </>
            )}
          </div>

          {!busy && (
            <footer className="flex items-center gap-2 border-t border-line bg-surface/60 px-3 py-2">
              {suggestion && (
                <button
                  type="button"
                  onClick={() => {
                    onAccept(suggestion);
                    report(true);
                    setOpen(false);
                  }}
                  className="rounded-full bg-brand px-3 py-1.5 text-xs font-medium text-brand-contrast hover:bg-brand-hover"
                >
                  Use this
                </button>
              )}
              <button
                type="button"
                onClick={() => {
                  report(false);
                  setOpen(false);
                }}
                className="rounded-full px-3 py-1.5 text-xs font-medium hover:bg-surface-hover"
              >
                Keep mine
              </button>
              <button
                type="button"
                onClick={improve}
                aria-label="Try again"
                title="Try again"
                className="ml-auto flex items-center gap-1 rounded-full px-2.5 py-1.5 text-xs font-medium text-muted hover:bg-surface-hover"
              >
                <RetryIcon width={14} height={14} /> Try again
              </button>
            </footer>
          )}
        </div>
      )}
    </div>
  );
}

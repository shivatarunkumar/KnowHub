"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckIcon, CloseIcon, SpinnerIcon } from "./icons";

type Step = {
  name: string;
  label: string;
  state: "starting" | "waiting" | "done" | "failed";
  url: string | null;
  error: string | null;
};
type Status = {
  available: boolean;
  ok: boolean | null;
  account: string | null;
  cli_error: string | null;
  adc_error: string | null;
  running: boolean;
  steps: Step[];
};

const IDLE_POLL_MS = 60_000;
const SIGNING_IN_POLL_MS = 2_000;

/**
 * "Reconnect Google Cloud": for KnowHub running on a Mac with a person's own Google
 * account, whose sign-in Google expires every so often. Only appears in a browser on
 * that Mac, and only while the sign-in has expired (the API decides both; see
 * backend/app/services/gcloud_login.py). Not needed on a service account.
 */
export function GcloudReconnect() {
  const [status, setStatus] = useState<Status | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/gcloud-login", { cache: "no-store" });
      if (res.ok) setStatus(await res.json());
    } catch {
      /* API unreachable: the status pill says so */
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, open ? SIGNING_IN_POLL_MS : IDLE_POLL_MS);
    return () => clearInterval(timer);
  }, [load, open]);

  // signed in again: reload so every page shows data instead of the errors it got
  const reconnected = open && status?.ok === true && !status.running;
  useEffect(() => {
    if (!reconnected) return;
    const timer = setTimeout(() => window.location.reload(), 1500);
    return () => clearTimeout(timer);
  }, [reconnected]);

  async function start() {
    setOpen(true);
    setError("");
    try {
      const res = await fetch("/api/v1/gcloud-login", { method: "POST" });
      const body = await res.json().catch(() => null);
      if (!res.ok) setError(body?.detail ?? "Couldn't start the sign-in.");
      else setStatus(body);
    } catch {
      setError("Couldn't reach KnowHub's server.");
    }
  }

  if (!status?.available || (status.ok && !open)) return null;

  return (
    <>
      <button
        type="button"
        onClick={start}
        title={status.adc_error ?? status.cli_error ?? undefined}
        className="flex h-9 items-center gap-2 rounded-full border border-warn px-3 text-sm font-medium text-warn hover:bg-surface-hover"
      >
        <span className="h-2 w-2 rounded-full bg-warn" />
        <span className="hidden md:inline">Reconnect Google Cloud</span>
        <span className="md:hidden">Reconnect</span>
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            aria-label="Close"
            className="absolute inset-0 bg-black/50"
            onClick={() => setOpen(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Reconnect Google Cloud"
            className="relative w-full max-w-md overflow-hidden rounded-2xl border border-line bg-bg shadow-2xl"
          >
            <header className="flex items-center gap-2 border-b border-line px-4 py-3">
              <h2 className="font-semibold">Reconnect Google Cloud</h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="ml-auto rounded-full p-1 text-muted hover:bg-surface-hover"
              >
                <CloseIcon width={18} height={18} />
              </button>
            </header>

            <div className="px-4 py-4 text-sm">
              {reconnected ? (
                <p className="py-6 text-center font-medium text-ok">
                  Connected{status.account ? ` as ${status.account}` : ""} ✓ Reloading…
                </p>
              ) : (
                <>
                  <p className="text-muted">
                    Google asks this computer to sign in again from time to time. Open each step, choose your
                    work Google account and click <strong>Allow</strong>. KnowHub carries on by itself afterwards.
                  </p>
                  <ol className="mt-4 space-y-2">
                    {(status.steps.length ? status.steps : placeholderSteps).map((step, index) => (
                      <li key={step.name} className="flex items-center gap-3 rounded-lg border border-line px-3 py-2">
                        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface text-xs font-semibold">
                          {step.state === "done" ? <CheckIcon width={14} height={14} className="text-ok" /> : index + 1}
                        </span>
                        <span className="flex-1">
                          {step.label}
                          {step.state === "failed" && (
                            <span className="mt-0.5 block text-xs text-bad">{step.error ?? "Didn't finish"}</span>
                          )}
                        </span>
                        {step.state === "waiting" && step.url && (
                          <a
                            href={step.url}
                            target="_blank"
                            rel="noreferrer"
                            className="shrink-0 rounded-full bg-brand px-3 py-1.5 text-xs font-medium text-brand-contrast hover:bg-brand-hover"
                          >
                            Sign in
                          </a>
                        )}
                        {step.state === "starting" && (
                          <SpinnerIcon width={16} height={16} className="shrink-0 text-muted" />
                        )}
                        {step.state === "done" && <span className="shrink-0 text-xs text-ok">Done</span>}
                      </li>
                    ))}
                  </ol>
                  {error && <p className="mt-3 text-xs text-bad">{error}</p>}
                  {!status.running && status.steps.length > 0 && status.steps.every((s) => s.state === "done") && (
                    <p className="mt-3 text-xs text-bad">
                      Signed in, but Google Cloud still refuses: {status.adc_error ?? status.cli_error}. Check it
                      was your work account, then try again.
                    </p>
                  )}
                  {!status.running && status.steps.some((s) => s.state !== "starting") && (
                    <button
                      type="button"
                      onClick={start}
                      className="mt-3 h-9 w-full rounded-full border border-line text-sm hover:bg-surface-hover"
                    >
                      Try again
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

const placeholderSteps: Step[] = [
  { name: "cli", label: "Sign in to the gcloud command line", state: "starting", url: null, error: null },
  { name: "adc", label: "Allow KnowHub to use your Google account", state: "starting", url: null, error: null },
];

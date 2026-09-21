"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import { EyeIcon, EyeOffIcon, LogoMark } from "./icons";

function Shell({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-sm px-4 py-12">
      <div className="mb-8 flex flex-col items-center gap-3 text-center">
        <LogoMark width={44} height={33} />
        <h1 className="text-2xl tracking-tight">{title}</h1>
        <p className="text-sm text-muted">{subtitle}</p>
      </div>
      {children}
    </div>
  );
}

function PasswordInput({
  id,
  label,
  value,
  onChange,
  autoComplete,
  placeholder,
  error,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete: string;
  placeholder?: string;
  error?: string;
}) {
  const [revealed, setRevealed] = useState(false);
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={revealed ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          placeholder={placeholder}
          required
          aria-invalid={Boolean(error)}
          className={`h-10 w-full rounded-lg border bg-bg pl-3 pr-11 outline-none focus:border-brand ${
            error ? "border-bad" : "border-line"
          }`}
        />
        <button
          type="button"
          onClick={() => setRevealed((v) => !v)}
          aria-label={revealed ? "Hide password" : "Show password"}
          aria-pressed={revealed}
          className="absolute right-1 top-1 flex h-8 w-9 items-center justify-center rounded-md text-muted hover:bg-surface-hover hover:text-fg"
        >
          {revealed ? <EyeOffIcon width={18} height={18} /> : <EyeIcon width={18} height={18} />}
        </button>
      </div>
      {error && <p className="text-xs text-bad">{error}</p>}
    </div>
  );
}

/** Step one: ask for the email and send a reset link. */
export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [message, setMessage] = useState("");
  const [devLink, setDevLink] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/v1/auth/forgot-password", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        setError(body?.detail?.message ?? "Couldn't start the reset. Please try again.");
        return;
      }
      setMessage(body?.message ?? "");
      setDevLink(body?.reset_url ?? null);
      setSent(true);
    } catch {
      setError("Can't reach the server. Is the API running?");
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <Shell title="Check your email" subtitle={message}>
        {devLink && (
          <div className="rounded-xl border border-line bg-surface p-4 text-sm">
            <p className="font-medium">No mail server is configured yet</p>
            <p className="mt-1 text-muted">
              Running locally, so the link is here instead (it is also in the API log):
            </p>
            <Link href={devLink.replace(/^https?:\/\/[^/]+/, "")} className="mt-3 block break-all text-brand hover:underline">
              {devLink}
            </Link>
          </div>
        )}
        <p className="mt-6 text-center text-sm text-muted">
          <Link href="/login" className="font-medium text-brand hover:underline">
            Back to sign in
          </Link>
        </p>
      </Shell>
    );
  }

  return (
    <Shell
      title="Reset your password"
      subtitle="Tell us the email on the account and we'll send a link to set a new password."
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        {error && (
          <p role="alert" className="rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">
            {error}
          </p>
        )}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="email" className="text-sm font-medium">
            Email
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            placeholder="you@company.com"
            required
            className="h-10 rounded-lg border border-line bg-bg px-3 outline-none focus:border-brand"
          />
        </div>
        <button
          type="submit"
          disabled={busy || !email}
          className="mt-2 h-10 rounded-full bg-brand text-sm font-medium text-brand-contrast hover:bg-brand-hover disabled:opacity-60"
        >
          {busy ? "Sending…" : "Send reset link"}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-muted">
        Remembered it?{" "}
        <Link href="/login" className="font-medium text-brand hover:underline">
          Sign in
        </Link>
      </p>
    </Shell>
  );
}

/** Step two: the link lands here with ?token=… and sets the new password. */
export function ResetPasswordForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [fieldError, setFieldError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setFieldError("");
    if (password.length < 8) {
      setFieldError("Use at least 8 characters");
      return;
    }
    if (password !== confirm) {
      setFieldError("Passwords don't match");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/v1/auth/reset-password", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token, password }),
      });
      if (res.ok || res.status === 204) {
        setDone(true);
        setTimeout(() => router.push("/login"), 2000);
        return;
      }
      const body = await res.json().catch(() => null);
      setError(body?.detail?.message ?? "Couldn't set that password. Please try again.");
    } catch {
      setError("Can't reach the server. Is the API running?");
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <Shell title="That link is incomplete" subtitle="It is missing its token, so we can't tell whose password to change.">
        <p className="text-center text-sm text-muted">
          <Link href="/forgot-password" className="font-medium text-brand hover:underline">
            Request a new link
          </Link>
        </p>
      </Shell>
    );
  }

  if (done) {
    return (
      <Shell title="Password changed" subtitle="Everywhere you were signed in has been signed out. Taking you to sign in…">
        <p className="text-center text-sm text-muted">
          <Link href="/login" className="font-medium text-brand hover:underline">
            Sign in now
          </Link>
        </p>
      </Shell>
    );
  }

  return (
    <Shell title="Choose a new password" subtitle="Pick something you don't use anywhere else.">
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        {error && (
          <p role="alert" className="rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">
            {error}{" "}
            <Link href="/forgot-password" className="font-medium underline">
              Request a new link
            </Link>
          </p>
        )}
        <PasswordInput
          id="password"
          label="New password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          placeholder="At least 8 characters"
          error={fieldError}
        />
        <PasswordInput
          id="confirm"
          label="Confirm new password"
          value={confirm}
          onChange={setConfirm}
          autoComplete="new-password"
        />
        <button
          type="submit"
          disabled={busy}
          className="mt-2 h-10 rounded-full bg-brand text-sm font-medium text-brand-contrast hover:bg-brand-hover disabled:opacity-60"
        >
          {busy ? "Saving…" : "Set new password"}
        </button>
      </form>
    </Shell>
  );
}

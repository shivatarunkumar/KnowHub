"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import { LogoMark } from "./icons";

type Mode = "login" | "register";

type FieldErrors = Partial<Record<string, string>>;

const COPY = {
  login: {
    title: "Sign in to KnowHub",
    subtitle: "Watch is open to everyone. Sign in to upload, comment and subscribe.",
    submit: "Sign in",
    endpoint: "/api/v1/auth/login",
    altText: "New to KnowHub?",
    altLink: "/register",
    altLabel: "Create an account",
  },
  register: {
    title: "Create your KnowHub account",
    subtitle: "Share fixes, incident resolutions and how-tos with the rest of engineering.",
    submit: "Create account",
    endpoint: "/api/v1/auth/register",
    altText: "Already have an account?",
    altLink: "/login",
    altLabel: "Sign in",
  },
} as const;

export function AuthForm({ mode }: { mode: Mode }) {
  const copy = COPY[mode];
  const router = useRouter();
  const nextUrl = useSearchParams().get("next") || "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setFieldErrors({});

    if (mode === "register") {
      if (password.length < 8) {
        setFieldErrors({ password: "Use at least 8 characters" });
        return;
      }
      if (password !== confirm) {
        setFieldErrors({ confirm: "Passwords don't match" });
        return;
      }
    }

    setBusy(true);
    try {
      const body =
        mode === "register"
          ? { email, password, display_name: displayName }
          : { email, password };
      const res = await fetch(copy.endpoint, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });

      if (res.ok) {
        router.push(nextUrl);
        router.refresh(); // re-render the server layout so the top bar shows the account
        return;
      }

      const data = await res.json().catch(() => null);
      const detail = data?.detail;
      if (Array.isArray(detail)) {
        // FastAPI validation errors: [{loc: ["body","password"], msg: "..."}]
        const errors: FieldErrors = {};
        for (const item of detail) {
          const field = item?.loc?.[1];
          if (field) errors[field] = item.msg?.replace(/^Value error, /, "") ?? "Invalid value";
        }
        setFieldErrors(errors);
        if (!Object.keys(errors).length) setError("Please check the form and try again.");
      } else if (detail?.field) {
        setFieldErrors({ [detail.field]: detail.message });
      } else {
        setError(detail?.message ?? "Something went wrong. Please try again.");
      }
    } catch {
      setError("Can't reach the server. Is the API running?");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-sm px-4 py-12">
      <div className="mb-8 flex flex-col items-center gap-3 text-center">
        <LogoMark width={44} height={33} />
        <h1 className="text-2xl font-semibold tracking-tight">{copy.title}</h1>
        <p className="text-sm text-muted">{copy.subtitle}</p>
      </div>

      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        {error && (
          <p role="alert" className="rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad">
            {error}
          </p>
        )}

        {mode === "register" && (
          <Field
            label="Name"
            value={displayName}
            onChange={setDisplayName}
            autoComplete="name"
            placeholder="Tarun Nagula"
            error={fieldErrors.display_name}
            required
          />
        )}

        <Field
          label="Email"
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="email"
          placeholder="you@company.com"
          error={fieldErrors.email}
          required
        />

        <Field
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete={mode === "register" ? "new-password" : "current-password"}
          placeholder={mode === "register" ? "At least 8 characters" : ""}
          error={fieldErrors.password}
          required
        />

        {mode === "register" && (
          <Field
            label="Confirm password"
            type="password"
            value={confirm}
            onChange={setConfirm}
            autoComplete="new-password"
            error={fieldErrors.confirm}
            required
          />
        )}

        <button
          type="submit"
          disabled={busy}
          className="mt-2 h-10 rounded-full bg-brand text-sm font-medium text-brand-contrast hover:bg-brand-hover disabled:opacity-60"
        >
          {busy ? "Please wait…" : copy.submit}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-muted">
        {copy.altText}{" "}
        <Link href={copy.altLink} className="font-medium text-brand hover:underline">
          {copy.altLabel}
        </Link>
      </p>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  error,
  type = "text",
  ...rest
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  type?: string;
  autoComplete?: string;
  placeholder?: string;
  required?: boolean;
}) {
  const id = label.toLowerCase().replace(/\s+/g, "-");
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : undefined}
        className={`h-10 rounded-lg border bg-bg px-3 outline-none focus:border-brand ${
          error ? "border-bad" : "border-line"
        }`}
        {...rest}
      />
      {error && (
        <p id={`${id}-error`} className="text-xs text-bad">
          {error}
        </p>
      )}
    </div>
  );
}

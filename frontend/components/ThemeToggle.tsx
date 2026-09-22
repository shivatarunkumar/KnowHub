"use client";

import { useEffect, useRef, useState } from "react";
import { AutoThemeIcon, CheckIcon, MoonIcon, SunIcon } from "./icons";

export const THEME_STORAGE_KEY = "knowhub-theme";

type Theme = "light" | "dark" | "system";

const OPTIONS: { value: Theme; label: string; hint: string; icon: typeof SunIcon }[] = [
  { value: "light", label: "Light", hint: "Always the light palette", icon: SunIcon },
  { value: "dark", label: "Dark", hint: "Always the dark palette", icon: MoonIcon },
  { value: "system", label: "Auto", hint: "Follow this device's setting", icon: AutoThemeIcon },
];

/** What the page is showing right now, which for "system" depends on the OS. */
function resolved(theme: Theme): "light" | "dark" {
  if (theme !== "system") return theme;
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function apply(theme: Theme) {
  const root = document.documentElement;
  // no attribute at all means "follow the OS", which is what the CSS keys off
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
  try {
    if (theme === "system") localStorage.removeItem(THEME_STORAGE_KEY);
    else localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // private window, or storage blocked: the choice just won't outlive this page
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");
  const [open, setOpen] = useState(false);
  const [ready, setReady] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // read the saved choice after mount: the server has no way to know it, and the inline
  // script in the layout has already applied it, so this only syncs the button
  useEffect(() => {
    let saved: Theme = "system";
    try {
      const stored = localStorage.getItem(THEME_STORAGE_KEY);
      if (stored === "light" || stored === "dark") saved = stored;
    } catch {
      /* storage blocked: stay on system */
    }
    setTheme(saved);
    setReady(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
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

  function choose(next: Theme) {
    apply(next);
    setTheme(next);
    setOpen(false);
  }

  // until the saved choice is read, show the neutral icon rather than guessing wrong
  const Icon = !ready ? AutoThemeIcon : resolved(theme) === "dark" ? MoonIcon : SunIcon;
  const current = OPTIONS.find((option) => option.value === theme);

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Appearance: ${current?.label ?? "Auto"}`}
        title={`Appearance: ${current?.label ?? "Auto"}`}
        className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-surface-hover"
      >
        <Icon width={20} height={20} />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-11 z-50 w-56 overflow-hidden rounded-xl border border-line bg-bg py-1 shadow-lg"
        >
          <p className="px-4 pb-1 pt-2 text-xs font-semibold uppercase tracking-wide text-muted">
            Appearance
          </p>
          {OPTIONS.map(({ value, label, hint, icon: OptionIcon }) => (
            <button
              key={value}
              type="button"
              role="menuitemradio"
              aria-checked={theme === value}
              onClick={() => choose(value)}
              className="flex w-full items-center gap-3 px-4 py-2 text-left text-sm hover:bg-surface-hover"
            >
              <OptionIcon width={18} height={18} className="shrink-0 text-muted" />
              <span className="min-w-0 flex-1">
                <span className="block">{label}</span>
                <span className="block text-xs text-muted">{hint}</span>
              </span>
              {theme === value && <CheckIcon width={16} height={16} className="shrink-0 text-brand" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

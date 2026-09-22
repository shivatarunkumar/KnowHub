/** Shared between the server (which renders the theme) and the toggle (which sets it). */

export const THEME_COOKIE = "knowhub-theme";

export type Theme = "light" | "dark" | "system";

/** A year: this is a preference, not a session. */
const ONE_YEAR = 60 * 60 * 24 * 365;

/**
 * Store the choice where the *server* can read it, so the next page load renders the
 * right palette in its HTML instead of correcting it after paint. "system" removes the
 * cookie, which is what makes Auto keep following the device.
 */
export function rememberTheme(theme: Theme) {
  const base = `${THEME_COOKIE}=`;
  const attributes = "path=/; SameSite=Lax";
  document.cookie =
    theme === "system"
      ? `${base}; ${attributes}; max-age=0`
      : `${base}${theme}; ${attributes}; max-age=${ONE_YEAR}`;
}

/** Apply it now, so the click feels instant rather than waiting for a navigation. */
export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

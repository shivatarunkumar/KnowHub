import type { Metadata } from "next";
import { cookies } from "next/headers";
import type { ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { getTopics } from "@/lib/api";
import { getCurrentUser } from "@/lib/session";
import { THEME_COOKIE, type Theme } from "@/lib/theme";
import "./globals.css";

export const metadata: Metadata = {
  title: "KnowHub",
  description: "Engineering fixes, incident resolutions and how-tos: in videos and shorts.",
};

export const dynamic = "force-dynamic"; // topics come from the API at request time

export default async function RootLayout({ children }: { children: ReactNode }) {
  const [topics, user, jar] = await Promise.all([getTopics(), getCurrentUser(), cookies()]);

  // The chosen theme rides in a cookie so the server can render it on <html> itself.
  // That is what avoids the flash of the wrong palette: no inline script, nothing to run
  // before paint, and no hydration mismatch. No cookie means "Auto", where the CSS falls
  // back to prefers-color-scheme.
  const saved = jar.get(THEME_COOKIE)?.value;
  const theme: Theme = saved === "dark" || saved === "light" ? saved : "system";

  return (
    <html lang="en" data-theme={theme === "system" ? undefined : theme}>
      <head>
        {/* A plain stylesheet link rather than next/font: if fonts.googleapis.com is
            blocked (locked-down network, offline, or a build without internet) the page
            still renders on the fallbacks in globals.css instead of failing the build. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&display=swap"
        />
      </head>
      <body className="font-sans antialiased">
        <AppShell topics={topics} user={user} theme={theme}>
          {children}
        </AppShell>
      </body>
    </html>
  );
}

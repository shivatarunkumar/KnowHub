import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { getTopics } from "@/lib/api";
import { getCurrentUser } from "@/lib/session";
import "./globals.css";

export const metadata: Metadata = {
  title: "KnowHub",
  description: "Engineering fixes, incident resolutions and how-tos: in videos and shorts.",
};

export const dynamic = "force-dynamic"; // topics come from the API at request time

export default async function RootLayout({ children }: { children: ReactNode }) {
  const [topics, user] = await Promise.all([getTopics(), getCurrentUser()]);
  return (
    <html lang="en">
      <body className="font-sans antialiased">
        <AppShell topics={topics} user={user}>
          {children}
        </AppShell>
      </body>
    </html>
  );
}

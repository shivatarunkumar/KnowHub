import Link from "next/link";
import {
  AuthFlow,
  EngagementDiagram,
  StorageLayout,
  SystemDiagram,
  UploadFlow,
} from "@/components/about/diagrams";

export const metadata = {
  title: "About KnowHub",
  description:
    "KnowHub — a Knowledge Hub for engineering. What it is, why it exists, and how it works.",
};

const SECTIONS = [
  ["purpose", "Why it exists"],
  ["today", "What works today"],
  ["architecture", "Architecture"],
  ["video", "How a video is stored"],
  ["login", "How login works"],
  ["engagement", "Likes & comments"],
  ["stack", "Tech stack"],
  ["next", "What's next"],
] as const;

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 pb-16 pt-6 lg:px-6">
      {/* ---------------------------------------------------------------- hero */}
      <p className="text-sm font-medium text-brand">About</p>
      <h1 className="mt-1 text-3xl font-semibold leading-tight sm:text-4xl">
        KnowHub is YouTube for how we fixed things.
      </h1>

      {/* the name itself: Knowledge + Hub */}
      <p className="mt-4 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-lg">
        <span className="font-semibold">
          <span className="text-brand">Know</span>ledge <span className="text-brand">Hub</span>
        </span>
        <span className="text-muted">
          — one place where what we work out is kept, and found again.
        </span>
      </p>

      <p className="mt-4 text-lg leading-relaxed text-muted">
        When someone solves a gnarly bug, resolves an incident or works out how a service really
        behaves, that knowledge normally lives in one person&apos;s head, a closed thread, or a
        document nobody finds again. KnowHub is an internal video platform where engineers record
        the fix once — screen, voice, the actual commands — and everyone else can find and watch it
        before re-solving the same problem.
      </p>

      <nav aria-label="On this page" className="no-scrollbar mt-6 flex gap-2 overflow-x-auto pb-1">
        {SECTIONS.map(([id, label]) => (
          <a
            key={id}
            href={`#${id}`}
            className="shrink-0 whitespace-nowrap rounded-lg bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-hover"
          >
            {label}
          </a>
        ))}
      </nav>

      {/* ---------------------------------------------------------------- purpose */}
      <Section id="purpose" title="Why it exists">
        <div className="grid gap-3 sm:grid-cols-2">
          <Card title="Stop re-solving the same problem">
            Search &ldquo;how did we fix X?&rdquo; and watch the answer, instead of debugging it a
            second time from scratch.
          </Card>
          <Card title="Make sharing cheap">
            Recording a five-minute walkthrough is faster than writing a document, and it carries
            the detail a document usually loses.
          </Card>
          <Card title="Keep the context attached">
            Every video carries its topic, category, and links to the runbook, ticket, repo or PR —
            plus code snippets you can copy instead of pausing and retyping.
          </Card>
          <Card title="Tell the right people">
            Subscribe to the topics you care about — BigQuery, Pub/Sub, Cloud Run — and hear about
            new material on them.
          </Card>
        </div>
        <p className="mt-4 text-sm text-muted">
          Anyone can browse and watch without an account. Signing in is what lets you upload, like,
          comment, share and manage your own channel.
        </p>
      </Section>

      {/* ---------------------------------------------------------------- today */}
      <Section id="today" title="What works today">
        <div className="grid gap-4 sm:grid-cols-2">
          <List
            title="Built"
            tone="ok"
            items={[
              "Accounts: register, sign in, stay signed in",
              "Home feed with topic filters, and the watch page with seeking",
              "Upload straight to Cloud Storage in 8 MB chunks, with a poster frame",
              "AI writing assist for titles, descriptions and comments",
              "Links and copy-ready code snippets attached to a video",
              "Likes, comments, one level of replies, @mentions, in-app sharing",
              "Your channel: edit, restrict who can watch, turn comments off, delete",
            ]}
          />
          <List
            title="Planned"
            tone="muted"
            items={[
              "Transcoding to HLS and adaptive quality",
              "Trim and crop the video while it uploads",
              "Search, including semantic search over titles and descriptions",
              "The shorts feed",
              "Subscriptions and the notification bell",
              "Playlists, watch later and history",
              "Studio analytics, and deployment to GCP",
            ]}
          />
        </div>
      </Section>

      {/* ---------------------------------------------------------------- architecture */}
      <Section id="architecture" title="Architecture">
        <p>
          Three moving parts and four dependencies. The browser talks to a Next.js app, which
          server-renders pages and proxies API calls to FastAPI; FastAPI owns the database, storage
          and everything else. The only traffic that skips the API is the video file itself.
        </p>
        <SystemDiagram />
        <p className="mt-4">
          Each dependency sits behind an adapter chosen by configuration, so the same code runs
          against a laptop&apos;s emulators or against real GCP: storage is Cloud Storage or
          fake-gcs-server, the event bus is Pub/Sub or its emulator, and the AI provider is Ollama
          locally or Vertex AI later. Nothing GCP-specific is hardcoded outside the config module.
        </p>
      </Section>

      {/* ---------------------------------------------------------------- video */}
      <Section id="video" title="How a video gets saved">
        <p>
          The first version of the upload sent the file through the API. It broke at about 10 MB,
          because the proxy in front of it buffers request bodies. Videos are not 10 MB, so the flow
          was rebuilt: the API creates the database row and opens a{" "}
          <em>resumable upload session</em>, and the browser pushes the bytes to Cloud Storage
          itself, 8 MB at a time. A dropped connection resumes from the last acknowledged chunk
          rather than starting over.
        </p>
        <UploadFlow />
        <StorageLayout />
        <p className="mt-4">
          Nothing is trusted until it is verified: when the browser says it has finished, the API
          asks Cloud Storage for the object&apos;s size. If it is missing, the video is marked{" "}
          <code className="rounded bg-surface px-1 py-0.5 text-[13px]">FAILED</code> instead of
          appearing in the feed as a broken entry. Every step — <em>initiated</em>,{" "}
          <em>uploaded</em>, <em>published</em>, and later <em>edited</em> or <em>deleted</em> —
          is appended to an audit table, so a video&apos;s whole history is recoverable.
        </p>
        <p className="mt-3">
          The thumbnail is captured in the browser: the file is drawn into a canvas at a frame you
          pick, turned into a JPEG, and uploaded on publish. That avoids needing FFmpeg anywhere in
          the stack today. Videos without one get a generated cover, so the grid never looks broken.
        </p>
      </Section>

      {/* ---------------------------------------------------------------- login */}
      <Section id="login" title="How login works">
        <p>
          Passwords are hashed with argon2id — memory-hard, so a stolen database is expensive to
          attack. Sign-in then issues two tokens with deliberately different jobs.
        </p>
        <AuthFlow />
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Card title="Access token — 15 minutes">
            A signed JWT in an httpOnly cookie. Every request carries it; the API verifies the
            signature and reads the user id from it, with no database lookup.
          </Card>
          <Card title="Refresh token — 14 days">
            A random opaque string. Only its SHA-256 hash is stored, and each use rotates it. If an
            already-used token appears again, every token in that family is revoked — that is what a
            stolen cookie being replayed looks like.
          </Card>
        </div>
        <p className="mt-4 text-sm text-muted">
          Wrong email and wrong password return the same error, so the form cannot be used to
          discover who has an account, and five failures lock it for fifteen minutes.
        </p>
      </Section>

      {/* ---------------------------------------------------------------- engagement */}
      <Section id="engagement" title="How likes and comments are stored">
        <p>
          Engagement is ordinary relational data: a row per reaction, a row per comment, and
          counters on the video kept in step by the API.
        </p>
        <EngagementDiagram />
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Card title="Likes">
            One row per person per video holding +1 or −1. Pressing the same button again deletes
            the row, so a person can never like something twice.
          </Card>
          <Card title="Comments">
            Threads are one level deep: replying to a reply attaches to the same thread instead of
            nesting forever. You can edit for 60 seconds, long enough to fix a typo and too short to
            rewrite something people already answered.
          </Card>
          <Card title="@mentions">
            Handles written in a comment become notifications for those people. Email addresses are
            deliberately not matched, so <span className="whitespace-nowrap">name@example.com</span>{" "}
            never pings a ghost.
          </Card>
          <Card title="Sharing">
            Sharing stays inside KnowHub: pick colleagues, optionally at a timestamp, and they get a
            notification. Nothing is sent to Slack or email.
          </Card>
        </div>
      </Section>

      {/* ---------------------------------------------------------------- stack */}
      <Section id="stack" title="Tech stack">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="py-2 pr-4 font-medium">Layer</th>
                <th className="py-2 pr-4 font-medium">Choice</th>
                <th className="py-2 font-medium">Why</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {STACK.map(([layer, choice, why]) => (
                <tr key={layer}>
                  <td className="py-2.5 pr-4 font-medium">{layer}</td>
                  <td className="py-2.5 pr-4">{choice}</td>
                  <td className="py-2.5 text-muted">{why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {/* ---------------------------------------------------------------- next */}
      <Section id="next" title="What's next">
        <p>
          The next pieces are search, the notification bell, and transcoding so long videos start
          instantly at any connection speed. After that: the in-browser trim and crop editor,
          semantic search over what a video is actually about, and deployment to GCP — which is
          meant to be a configuration switch rather than a rewrite.
        </p>
        <p className="mt-4 text-sm text-muted">
          This page mirrors <code className="rounded bg-surface px-1 py-0.5">project.md</code> in the
          repository, which is the full plan: architecture, data model, API surface, roadmap and the
          decisions behind them.
        </p>
        <Link
          href="/upload"
          className="mt-6 inline-block rounded-full bg-brand px-5 py-2.5 text-sm font-medium text-brand-contrast hover:bg-brand-hover"
        >
          Share something you fixed →
        </Link>
      </Section>
    </div>
  );
}

const STACK: [string, string, string][] = [
  ["Frontend", "Next.js 16, React 19, TypeScript, Tailwind CSS", "Server-rendered pages, fast first load"],
  ["Backend", "Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 async", "Typed, async, OpenAPI docs for free"],
  ["Database", "PostgreSQL 17 with pg_trgm and pgvector", "Relational data, full-text search, and embeddings later"],
  ["Migrations", "Plain versioned SQL + a Python runner", "DDL stays readable and tool-independent"],
  ["Auth", "argon2id, PyJWT, httpOnly cookies", "Standard, and safe against database theft"],
  ["Storage", "Google Cloud Storage, resumable uploads", "Multi-GB files without passing through the API"],
  ["AI", "Ollama locally, Vertex AI on GCP", "Writing assist now, semantic search later"],
  ["Messaging", "Pub/Sub (topics ready, workers later)", "Decouples upload, processing and notifications"],
  ["Config", "pydantic-settings and one .env", "Every GCP and app setting in one place"],
  ["Testing", "pytest + httpx, TypeScript type checking", "Backend behaviour and frontend types on every change"],
];

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="mt-12 scroll-mt-20 border-t border-line pt-8">
      <h2 className="display text-2xl">{title}</h2>
      <div className="mt-3 leading-relaxed">{children}</div>
    </section>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-line p-4">
      <h3 className="font-medium">{title}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-muted">{children}</p>
    </div>
  );
}

function List({ title, items, tone }: { title: string; items: string[]; tone: "ok" | "muted" }) {
  return (
    <div className="rounded-xl border border-line p-4">
      <h3 className="flex items-center gap-2 font-medium">
        <span
          aria-hidden="true"
          className={`h-2 w-2 rounded-full ${tone === "ok" ? "bg-ok" : "bg-muted"}`}
        />
        {title}
      </h3>
      <ul className="mt-2 grid gap-1.5 text-sm text-muted">
        {items.map((item) => (
          <li key={item} className="flex gap-2">
            <span aria-hidden="true">{tone === "ok" ? "✓" : "○"}</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

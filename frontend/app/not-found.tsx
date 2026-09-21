import Link from "next/link";

// Routes in the sidebar/top bar (upload, sign in, shorts, …) land here until their phase ships.
export default function NotFound() {
  return (
    <section className="mx-auto mt-24 max-w-md px-4 text-center">
      <h1 className="text-xl font-semibold">This page isn’t here yet</h1>
      <p className="mt-2 text-sm text-muted">
        It’s part of an upcoming KnowHub phase (see the roadmap in project.md).
      </p>
      <Link
        href="/"
        className="mt-6 inline-block rounded-full bg-brand px-4 py-2 text-sm font-medium text-brand-contrast hover:bg-brand-hover"
      >
        Back to Home
      </Link>
    </section>
  );
}

import Link from "next/link";

export default function HomePage() {
  return (
    <div className="min-h-screen">
      <header className="border-b bg-white">
        <nav aria-label="Main navigation" className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link className="text-lg font-semibold tracking-tight" href="/">RepoLens</Link>
          <div className="flex items-center gap-5">
            <Link className="text-sm text-slate-600 hover:text-slate-950" href="/dashboard">Dashboard</Link>
            <span className="rounded-full border px-3 py-1 text-xs font-medium text-slate-600">Project foundation</span>
          </div>
        </nav>
      </header>
      <main className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-6xl items-center px-6 py-16">
        <section aria-labelledby="welcome-heading" className="max-w-2xl">
          <p className="mb-4 text-sm font-medium uppercase tracking-[0.16em] text-slate-500">Understand software systems, not just source code.</p>
          <h1 id="welcome-heading" className="text-4xl font-semibold tracking-tight sm:text-5xl">RepoLens foundation</h1>
          <p className="mt-5 max-w-xl text-lg leading-8 text-slate-600">
            The application shell is ready for development. Repository intelligence and dashboard capabilities have not been implemented yet.
          </p>
        </section>
      </main>
    </div>
  );
}

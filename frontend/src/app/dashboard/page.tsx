import Link from "next/link";

export default function DashboardPage() {
  return (
    <div className="min-h-screen">
      <header className="border-b bg-white">
        <nav aria-label="Main navigation" className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link className="text-lg font-semibold tracking-tight" href="/">RepoLens</Link>
          <span className="rounded-full border px-3 py-1 text-xs font-medium text-slate-600">Project foundation</span>
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-12">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard shell</h1>
        <section className="mt-8 rounded-lg border bg-white p-8" aria-label="Dashboard workspace foundation">
          <p className="font-medium">Workspace foundation</p>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Repository selection and intelligence views are not implemented at this stage.
          </p>
        </section>
      </main>
    </div>
  );
}

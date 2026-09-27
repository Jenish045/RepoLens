"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const capabilities = [
  {
    name: "Repository Overview",
    status: "Available",
    available: true,
    description: "Review repository metadata, supported-language parsing, entry points, technologies, and structural inventory.",
  },
  {
    name: "Semantic Explorer",
    status: "Available",
    available: true,
    description: "Search persisted source chunks with natural-language concepts and inspect their file and line provenance.",
  },
  {
    name: "Repository Map",
    status: "Available",
    available: true,
    description: "Explore deterministic modules and their import-derived dependencies in an interactive graph.",
  },
  {
    name: "Repository Insights",
    status: "Planned",
    available: false,
    description: "Structured observations about module distribution, dependencies, and repository organization.",
  },
  {
    name: "Ask RepoLens",
    status: "Planned",
    available: false,
    description: "Grounded conversational answers with citations to repository evidence.",
  },
  {
    name: "Export Report",
    status: "Planned",
    available: false,
    description: "Portable PDF and Markdown summaries of a completed repository analysis.",
  },
];
const errors: Record<string,string> = { oauth_configuration_missing: "GitHub sign-in is not configured yet. Add the GitHub OAuth settings to the backend environment.", github_authorization_denied: "GitHub authorization was cancelled. You can try again when you are ready.", oauth_state_invalid: "The sign-in request expired or could not be verified. Please try again.", github_sign_in_failed: "GitHub sign-in could not be completed. Please try again.", database_migration_required: "RepoLens database setup is incomplete. Ask the project administrator to apply the latest database migrations.", session_storage_unavailable: "This browser could not store the RepoLens session. Check your browser storage settings and try again.", github_scope_required: "RepoLens needs profile and public repository access to continue." };

export default function HomePage() {
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setError(new URLSearchParams(window.location.search).get("error")); }, []);
  const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  return <main className="min-h-screen overflow-hidden bg-[#f7f8fa] text-slate-950">
    <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-6"><Link className="flex items-center gap-3 text-lg font-semibold" href="/"><span className="grid size-9 place-items-center rounded-xl bg-indigo-600 text-white">R</span>RepoLens</Link><span className="text-sm text-slate-500">Repository intelligence</span></nav>
    <section className="mx-auto grid max-w-7xl items-center gap-12 px-6 pb-16 pt-10 lg:grid-cols-[1.1fr_.9fr] lg:pb-24 lg:pt-20">
      <div><p className="mb-5 text-xs font-semibold uppercase tracking-[.22em] text-indigo-700">Make any codebase easier to understand</p><h1 className="max-w-3xl text-5xl font-semibold leading-[1.08] tracking-[-.04em] sm:text-6xl">See the shape of a repository in minutes.</h1><p className="mt-6 max-w-2xl text-lg leading-8 text-slate-600">RepoLens turns a public GitHub repository into a clear, structured overview—so you can find its technologies, entry points, and code organization without reading every file first.</p>
        {error && <p role="alert" className="mt-6 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">{errors[error] ?? "GitHub sign-in could not be completed. Please try again."}</p>}
        <a href={`${api}/api/v1/auth/github`} className="mt-8 inline-flex h-12 items-center gap-3 rounded-xl bg-slate-950 px-5 font-medium text-white shadow-sm transition hover:bg-indigo-700"><GitHubMark/>Sign in with GitHub</a><p className="mt-3 text-xs text-slate-500">RepoLens reads public repository data and never changes your repositories.</p>
      </div>
      <div className="relative"><div className="absolute -inset-10 rounded-full bg-indigo-200/40 blur-3xl"/><div className="relative rounded-3xl border border-slate-200 bg-white p-5 shadow-xl shadow-slate-200/60 sm:p-7"><div className="mb-4 inline-flex rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-500">Illustrative product preview · sample content</div><div className="flex items-center justify-between border-b border-slate-100 pb-5"><div><p className="text-sm text-slate-500">Repository overview</p><p className="mt-1 font-semibold">acme / storefront</p></div><span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">Analyzed</span></div><div className="mt-5 grid grid-cols-3 gap-3">{[["Language","TypeScript"],["Files","1,284"],["Size","8.4 MB"]].map(([a,b])=><div key={a} className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">{a}</p><p className="mt-2 text-sm font-semibold">{b}</p></div>)}</div><div className="mt-5 rounded-xl border border-slate-100 p-4"><p className="text-xs font-medium text-slate-500">TECHNOLOGIES</p><div className="mt-3 flex flex-wrap gap-2">{["React","Next.js","Tailwind CSS"].map(x=><span key={x} className="rounded-lg bg-indigo-50 px-2.5 py-1.5 text-xs font-medium text-indigo-700">{x}</span>)}</div></div><div className="mt-4 rounded-xl bg-slate-950 p-4 font-mono text-xs leading-6 text-slate-300"><span className="text-indigo-300">src/</span><br/>&nbsp; app/ &nbsp; <span className="text-slate-500">application routes</span><br/>&nbsp; components/ <span className="text-slate-500">reusable UI</span><br/>&nbsp; lib/ &nbsp;&nbsp;&nbsp; <span className="text-slate-500">shared utilities</span></div></div></div>
    </section>
    <section className="border-y border-slate-200 bg-white"><div className="mx-auto max-w-7xl px-6 py-10"><p className="text-xs font-semibold uppercase tracking-[.2em] text-slate-500">Supported languages</p><div className="mt-5 flex flex-wrap gap-3">{["Python","Java","JavaScript","TypeScript"].map(x=><span key={x} className="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700">{x}</span>)}</div></div></section>
    <section className="mx-auto max-w-7xl px-6 py-16"><p className="text-xs font-semibold uppercase tracking-[.2em] text-indigo-700">Repository understanding</p><h2 className="mt-3 text-3xl font-semibold tracking-tight">Explore what works today and what is planned</h2><div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{capabilities.map((capability,i)=><article key={capability.name} className="rounded-2xl border border-slate-200 bg-white p-5"><div className="flex items-center justify-between gap-3"><span className="text-sm font-semibold text-indigo-600">0{i+1}</span><span className={`rounded-full px-2.5 py-1 text-xs font-medium ${capability.available ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>{capability.status}</span></div><h3 className="mt-4 font-semibold">{capability.name}</h3><p className="mt-2 text-sm leading-6 text-slate-600">{capability.description}</p></article>)}</div></section>
    <footer className="mx-auto max-w-7xl border-t border-slate-200 px-6 py-7 text-sm text-slate-500">RepoLens · Understand software systems, not just source code.</footer>
  </main>;
}
function GitHubMark() { return <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5 fill-current"><path d="M12 .9a11.1 11.1 0 0 0-3.51 21.63c.56.1.76-.24.76-.54v-2.1c-3.1.68-3.76-1.32-3.76-1.32-.5-1.29-1.24-1.63-1.24-1.63-1.01-.7.08-.69.08-.69 1.12.08 1.71 1.15 1.71 1.15 1 1.7 2.62 1.21 3.26.92.1-.72.39-1.21.71-1.49-2.48-.28-5.09-1.24-5.09-5.52 0-1.22.44-2.21 1.15-2.99-.12-.28-.5-1.42.11-2.96 0 0 .94-.3 3.05 1.14a10.6 10.6 0 0 1 5.55 0c2.11-1.44 3.05-1.14 3.05-1.14.61 1.54.23 2.68.11 2.96.72.78 1.15 1.77 1.15 2.99 0 4.29-2.62 5.23-5.11 5.51.4.35.76 1.03.76 2.08v3.09c0 .3.2.65.77.54A11.1 11.1 0 0 0 12 .9Z"/></svg>; }

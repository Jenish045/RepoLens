"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { apiRequest } from "@/lib/api";

type RepoOption = { id: string; owner: string; name: string; commit_sha: string | null };
type SemanticResult = { chunk_id: string; file_path: string; module_id: string | null; module_name: string | null; start_line: number; end_line: number; score: number; text: string; symbol_name: string | null };

export default function SemanticExplorerPage() {
  const [repositories, setRepositories] = useState<RepoOption[]>([]);
  const [repositoryId, setRepositoryId] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SemanticResult[] | null>(null);
  const [selected, setSelected] = useState<SemanticResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { const requestedRepo = new URLSearchParams(window.location.search).get("repository_id") ?? ""; apiRequest<RepoOption[]>("/repositories/analyzed").then((items) => {
    setRepositories(items);
    setRepositoryId((current) => items.some((item) => item.id === requestedRepo) ? requestedRepo : (current || items[0]?.id || ""));
  }).catch((reason) => setError(reason instanceof Error ? reason.message : "Could not load analyzed repositories.")); }, []);

  const repository = useMemo(() => repositories.find((item) => item.id === repositoryId), [repositories, repositoryId]);
  async function search(event: FormEvent) {
    event.preventDefault();
    if (!repositoryId || !query.trim()) { setError(!query.trim() ? "Enter a natural-language query to search." : "Choose an analyzed repository first."); return; }
    setBusy(true); setError(""); setResults(null); setSelected(null);
    try {
      const response = await apiRequest<{ results: SemanticResult[] }>("/search/semantic", { method: "POST", body: JSON.stringify({ repository_id: repositoryId, query: query.trim(), limit: 10 }) });
      setResults(response.results);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Semantic search failed."); }
    finally { setBusy(false); }
  }

  return <main className="min-h-screen bg-slate-50 text-slate-950">
    <header className="border-b bg-white"><nav className="mx-auto flex h-16 max-w-5xl items-center justify-between px-6"><Link href="/dashboard" className="font-semibold">RepoLens</Link><Link href="/dashboard" className="text-sm text-slate-600 hover:text-slate-950">All repositories</Link></nav></header>
    <section className="mx-auto max-w-5xl px-6 py-10">
      <p className="text-xs font-semibold uppercase tracking-[.2em] text-indigo-700">Semantic Explorer</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">Find code by concept or responsibility</h1>
      <p className="mt-2 text-slate-600">Search repository evidence with natural-language queries. Results show source chunks and their exact locations.</p>
      <form onSubmit={search} className="mt-7 rounded-2xl border bg-white p-5 shadow-sm">
        <label htmlFor="semantic-query" className="text-sm font-medium">What are you looking for?</label>
        <textarea id="semantic-query" value={query} onChange={(event) => setQuery(event.target.value)} maxLength={500} rows={2} placeholder="Where are fraud predictions generated?" className="mt-2 w-full resize-y rounded-xl border px-4 py-3 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" />
        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div className="min-w-0 flex-1"><label htmlFor="semantic-repository" className="text-xs font-medium text-slate-500">Repository</label><select id="semantic-repository" value={repositoryId} onChange={(event) => { setRepositoryId(event.target.value); setResults(null); }} className="mt-1 block w-full rounded-lg border bg-white px-3 py-2 text-sm"><option value="">Choose an analyzed repository</option>{repositories.map((item) => <option value={item.id} key={item.id}>{item.owner}/{item.name}</option>)}</select></div><button type="submit" disabled={busy || !repositories.length} className="h-10 rounded-lg bg-indigo-700 px-5 text-sm font-medium text-white hover:bg-indigo-800 disabled:opacity-50">{busy ? "Searching…" : "Search repository"}</button></div>
      </form>
      {error && <p role="alert" className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">{error}</p>}
      {!repositories.length && !error && <p className="mt-5 rounded-xl border bg-white p-5 text-sm text-slate-600">No completed repository analyses are available yet.</p>}
      {results && <section className="mt-8"><div className="flex items-baseline justify-between"><h2 className="text-xl font-semibold">Results</h2><span className="text-sm text-slate-500">{repository ? `${repository.owner}/${repository.name}` : ""} · {results.length} matches</span></div>
        {!results.length ? <p className="mt-4 rounded-xl border bg-white p-5 text-sm text-slate-600">No repository chunks matched this query. Try another concept or responsibility.</p> : <ol className="mt-4 space-y-4">{results.map((result, index) => <li key={result.chunk_id}><button type="button" onClick={() => setSelected(result)} className="w-full rounded-2xl border bg-white p-5 text-left transition hover:border-indigo-300 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><h3 className="break-all font-mono text-sm font-semibold text-indigo-800">{result.file_path}</h3><p className="mt-1 text-sm text-slate-700">{result.symbol_name || "Source structure"} <span className="text-slate-400">· Lines {result.start_line}–{result.end_line}</span></p></div><span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-800">Relevance {result.score.toFixed(3)}</span></div><pre className="mt-4 max-h-44 overflow-hidden whitespace-pre-wrap break-words rounded-xl bg-slate-950 p-4 text-xs leading-5 text-slate-200">{result.text}</pre><div className="mt-3 flex items-center justify-between text-xs text-slate-500"><span>Module: {result.module_name ?? "Standalone"}</span><span>Inspect source context →</span></div><span className="sr-only">Result {index + 1}</span></button></li>)}</ol>}
      </section>}
    </section>
    {selected && <><button type="button" aria-label="Close source context" onClick={() => setSelected(null)} className="fixed inset-0 z-20 bg-slate-950/30"/><section role="dialog" aria-modal="true" aria-labelledby="semantic-context-title" className="fixed inset-y-0 right-0 z-30 flex w-full max-w-2xl flex-col border-l bg-white shadow-2xl"><header className="flex items-start justify-between border-b p-6"><div><p className="text-xs font-semibold uppercase tracking-[.18em] text-indigo-700">Source evidence</p><h2 id="semantic-context-title" className="mt-2 break-all font-mono text-lg font-semibold">{selected.file_path}</h2><p className="mt-1 text-sm text-slate-600">{selected.symbol_name ?? "Source structure"} · lines {selected.start_line}–{selected.end_line}</p></div><button type="button" onClick={() => setSelected(null)} className="rounded-lg border px-3 py-1.5 text-sm">Close</button></header><div className="flex-1 overflow-auto p-6"><dl className="grid grid-cols-2 gap-4 text-sm"><div><dt className="text-slate-500">Module</dt><dd className="mt-1 font-medium">{selected.module_name ?? "Standalone"}</dd></div><div><dt className="text-slate-500">Relevance</dt><dd className="mt-1 font-medium">{selected.score.toFixed(4)}</dd></div><div className="col-span-2"><dt className="text-slate-500">Chunk ID</dt><dd className="mt-1 break-all font-mono text-xs">{selected.chunk_id}</dd></div></dl><pre className="mt-5 whitespace-pre-wrap break-words rounded-xl bg-slate-950 p-5 text-xs leading-6 text-slate-100">{selected.text}</pre></div></section></>}
  </main>;
}

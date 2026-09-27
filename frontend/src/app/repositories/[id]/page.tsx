"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { apiRequest, type Overview, type ParsedFile } from "@/lib/api";

export default function OverviewPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [parsedFilesOpen, setParsedFilesOpen] = useState(false);
  const [parsedFileSearch, setParsedFileSearch] = useState("");
  const [inventoryRefreshing, setInventoryRefreshing] = useState(false);
  const [inventoryError, setInventoryError] = useState("");

  async function rebuildInventory() {
    setInventoryRefreshing(true);
    setInventoryError("");
    try {
      const inventory = await apiRequest<{ parsed_file_count: number; parsed_files: ParsedFile[] }>(`/analysis/${id}/parsed-files/backfill`, { method: "POST" });
      setData((previous) => previous ? { ...previous, structural_data: { ...previous.structural_data, parsed_file_count: inventory.parsed_file_count, parsed_files: inventory.parsed_files } } : previous);
    } catch (reason) {
      setInventoryError(reason instanceof Error ? reason.message : "Could not rebuild the saved parse inventory.");
    } finally {
      setInventoryRefreshing(false);
    }
  }

  useEffect(() => {
    apiRequest<Overview>(`/intelligence/${id}`)
      .then(setData)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Could not load this overview."));
  }, [id]);

  if (error) {
    return <main className="grid min-h-screen place-items-center bg-slate-50"><div className="rounded-2xl border bg-white p-8"><p role="alert">{error}</p><Link className="mt-4 inline-block text-indigo-700 underline" href="/dashboard">Back to repositories</Link></div></main>;
  }
  if (!data) {
    return <main className="min-h-screen bg-slate-50 p-10"><div role="status" className="mx-auto max-w-5xl rounded-2xl border bg-white p-8">Loading repository overview…</div></main>;
  }

  const repo = data.repository;
  const structural = data.structural_data;
  const parsedFiles = structural?.parsed_files ?? [];
  const filteredParsedFiles = parsedFiles.filter((file) => file.path.toLocaleLowerCase().includes(parsedFileSearch.trim().toLocaleLowerCase()));
  const metrics = [
    ["Primary language", repo.primary_language ?? "Unknown"],
    ["Tracked files", repo.file_count?.toLocaleString() ?? "Unknown"],
    ["Repository size", repo.size_kb == null ? "Unknown" : `${repo.size_kb.toLocaleString()} KB`],
    ["Modules", repo.module_count == null ? "Not ready" : repo.module_count.toLocaleString()],
  ];

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b bg-white"><nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6"><Link href="/dashboard" className="font-semibold">RepoLens</Link><Link href="/dashboard" className="text-sm text-slate-600 hover:text-slate-950">All repositories</Link></nav></header>
      <section className="mx-auto max-w-6xl px-6 py-10">
        <p className="text-xs font-semibold uppercase tracking-[.2em] text-indigo-700">Repository Overview</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">{repo.owner} / {repo.name}</h1>
        <p className="mt-3 text-slate-600">{repo.description || "No repository description provided."}</p>
        <p className="mt-3 break-all font-mono text-xs text-slate-500">Analyzed commit {repo.commit_sha}</p>
        <div className="mt-6 flex flex-wrap gap-3"><Link href={`/repositories/${repo.id}/map`} className="rounded-lg bg-slate-950 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800">Open Repository Map</Link><Link href="/dashboard" className="rounded-lg border bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">All repositories</Link></div>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{metrics.map(([label, value]) => <div key={label} className="rounded-2xl border bg-white p-5"><p className="text-sm text-slate-500">{label}</p><p className="mt-2 text-xl font-semibold">{value}</p></div>)}</div>
        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          <section className="rounded-2xl border bg-white p-6"><h2 className="font-semibold">Technology stack</h2>{repo.technologies.length ? <div className="mt-4 flex flex-wrap gap-2">{repo.technologies.map((item) => <span key={item} className="rounded-full bg-indigo-50 px-3 py-1.5 text-sm font-medium text-indigo-700">{item}</span>)}</div> : <p className="mt-3 text-sm text-slate-500">No recognized framework or technology evidence was found in the repository manifests.</p>}<h3 className="mt-6 text-sm font-semibold">Language breakdown</h3>{repo.language_breakdown && Object.keys(repo.language_breakdown).length ? <ul className="mt-3 space-y-2">{Object.entries(repo.language_breakdown).sort((a, b) => b[1] - a[1]).map(([name, bytes]) => <li key={name} className="flex justify-between text-sm"><span>{name}</span><span className="text-slate-500">{(bytes / 1024).toFixed(1)} KB</span></li>)}</ul> : <p className="mt-2 text-sm text-slate-500">Language breakdown unavailable.</p>}</section>
          <section className="rounded-2xl border bg-white p-6"><h2 className="font-semibold">Executive summary</h2><p className="mt-3 text-sm leading-6 text-slate-600">{data.summary ?? "A generated executive summary is not part of this release. This overview shows deterministic metadata extracted from the repository."}</p><h3 className="mt-6 text-sm font-semibold">Detected entry points</h3>{repo.entry_points.length ? <ul className="mt-3 space-y-2">{repo.entry_points.map((path) => <li key={path} className="rounded-lg bg-slate-50 px-3 py-2 font-mono text-xs">{path}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">No deterministic entry point was identified.</p>}</section>
        </div>
        <section className="mt-6 rounded-2xl border bg-white p-6"><h2 className="font-semibold">Structural metadata</h2><p className="mt-1 text-sm text-slate-500">Tree-sitter parsed repository declarations; repository code was never executed. These are static syntax structures, not runtime behavior.</p><div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4"><button type="button" onClick={() => setParsedFilesOpen(true)} aria-haspopup="dialog" className="rounded-xl bg-indigo-50 p-3 text-left outline-none hover:bg-indigo-100 focus-visible:ring-2 focus-visible:ring-indigo-600"><p className="text-xs text-indigo-800">Parsed files</p><p className="mt-1 font-semibold text-indigo-950">{structural?.parsed_file_count ?? 0}</p><p className="mt-1 text-xs text-indigo-700">View successfully parsed files</p></button>{[["Symbols", structural?.symbol_count ?? 0], ["Imports and exports", structural?.import_count ?? 0], ["Parse errors", structural?.parse_error_count ?? 0]].map(([label, value]) => <div key={label} className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-500">{label}</p><p className="mt-1 font-semibold">{value}</p></div>)}</div><div className="mt-3 text-xs text-slate-500">Tracked files are every file in the repository snapshot. Parsed files are supported source files Tree-sitter successfully read and parsed.</div><div className="mt-5 grid gap-6 lg:grid-cols-2"><div><h3 className="text-sm font-semibold">Code declarations</h3><p className="mt-1 text-xs text-slate-500">Functions, classes, methods, and other structural definitions extracted from source code.</p><ul className="mt-2 max-h-80 space-y-2 overflow-auto">{(structural?.symbols ?? []).slice(0, 100).map((symbol, index) => <li key={`${symbol.path}:${symbol.start_line}:${index}`} className="rounded-lg border border-slate-100 p-3"><p className="text-sm font-medium">{symbol.name} <span className="text-xs font-normal text-slate-500">{symbol.kind}</span></p><p className="mt-1 truncate font-mono text-xs text-slate-500">{symbol.path}:{symbol.start_line}</p>{symbol.docstring && <p className="mt-2 text-xs text-slate-600">{symbol.docstring}</p>}</li>)}</ul></div><div><h3 className="text-sm font-semibold">Imports and exports</h3><ul className="mt-2 max-h-80 space-y-2 overflow-auto">{(structural?.imports ?? []).slice(0, 100).map((item, index) => <li key={`${item.path}:${item.line}:${index}`} className="rounded-lg bg-slate-50 p-3"><p className="truncate font-mono text-xs">{item.declaration}</p><p className="mt-1 truncate text-xs text-slate-500">{item.path}:{item.line}</p></li>)}</ul></div></div></section>
        <p className="mt-5 text-xs text-slate-500">Default branch: {repo.default_branch ?? "Unknown"} · Last analyzed: {repo.analyzed_at ? new Date(repo.analyzed_at).toLocaleString() : "Unknown"} · Building intelligence and generating insights remain deferred.</p>
      </section>
      {parsedFilesOpen && <><button type="button" aria-label="Close parsed files" onClick={() => setParsedFilesOpen(false)} className="fixed inset-0 z-20 bg-slate-950/30"/><section role="dialog" aria-modal="true" aria-labelledby="parsed-files-title" className="fixed inset-y-0 right-0 z-30 flex w-full max-w-2xl flex-col border-l bg-white shadow-2xl"><header className="flex items-start justify-between border-b p-6"><div><p className="text-xs font-semibold uppercase tracking-[.18em] text-indigo-700">Static parse inventory</p><h2 id="parsed-files-title" className="mt-2 text-xl font-semibold">Parsed files</h2><p className="mt-1 text-sm text-slate-600">{structural?.parsed_file_count ?? parsedFiles.length} files successfully parsed for this analysis.</p></div><button type="button" onClick={() => setParsedFilesOpen(false)} className="rounded-lg border px-3 py-1.5 text-sm">Close</button></header><div className="border-b p-5"><label htmlFor="parsed-file-search" className="text-sm font-medium">Search by file path</label><input id="parsed-file-search" type="search" value={parsedFileSearch} onChange={(event) => setParsedFileSearch(event.target.value)} placeholder="Filter paths…" className="mt-2 w-full rounded-lg border px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"/></div><div className="flex-1 overflow-auto p-5">{!structural?.parsed_files && (structural?.parsed_file_count ?? 0) > 0 ? <><p className="rounded-lg bg-amber-50 p-4 text-sm text-amber-900">This saved analysis predates per-file inventory support. Its individual parse records were not saved, so the exact file list cannot be recovered from this analysis.</p><p className="mt-3 text-sm text-slate-600">You can rebuild an exact inventory from the public repository revision saved with this analysis. RepoLens will verify its totals before saving file records; this does not rerun or replace the analysis.</p>{inventoryError && <p role="alert" className="mt-3 text-sm text-red-700">{inventoryError}</p>}<button type="button" disabled={inventoryRefreshing} onClick={rebuildInventory} className="mt-4 rounded-lg bg-indigo-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">{inventoryRefreshing ? "Reading saved commit…" : "Build exact inventory from saved commit"}</button></> : filteredParsedFiles.length === 0 ? <p className="rounded-lg bg-slate-50 p-5 text-sm text-slate-600">{parsedFiles.length ? "No parsed files match this path." : "No files were successfully parsed in this repository analysis."}</p> : <><p className="mb-3 text-xs text-slate-500">Showing {filteredParsedFiles.length} of {parsedFiles.length} parsed files</p><ul className="space-y-2">{filteredParsedFiles.map((file) => <li key={file.path} className="rounded-xl border border-slate-200 p-4"><p className="break-all font-mono text-sm font-medium text-slate-900">{file.path}</p><div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600"><span>Language: {file.language}</span><span>Declarations: {file.declaration_count}</span><span>Imports/exports: {file.import_export_count}</span><span>Parse status: {file.parse_status === "parsed_with_errors" ? "Parsed with syntax errors" : "Parsed"}</span>{Object.prototype.hasOwnProperty.call(file, "module_name") && <span>Module: {file.module_name ?? "Standalone (not assigned to a module)"}</span>}</div></li>)}</ul></>}</div></section></>}
    </main>
  );
}

"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, apiRequest, type RepositoryMap, type RepositoryMapNode } from "@/lib/api";

type ModuleNodeData = RepositoryMapNode & Record<string, unknown>;
type ModuleFlowNode = Node<ModuleNodeData, "module">;

function ModuleNodeView({ data, selected }: NodeProps<ModuleFlowNode>) {
  return (
    <div className={`w-[260px] rounded-xl border bg-white p-4 shadow-sm transition-shadow ${selected ? "border-indigo-500 shadow-lg ring-2 ring-indigo-100" : "border-slate-200"}`}>
      <Handle type="target" position={Position.Left} className="!size-2 !bg-indigo-500" />
      <p className="truncate text-sm font-semibold text-slate-900">{data.name}</p>
      <div className="mt-2 flex items-center gap-2">
        {data.category && <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-medium capitalize text-indigo-700">{data.category}</span>}
        <span className="text-xs text-slate-500">{data.file_count.toLocaleString()} files</span>
      </div>
      {data.description && <p className="mt-2 line-clamp-2 text-xs leading-4 text-slate-500">{data.description}</p>}
      <Handle type="source" position={Position.Right} className="!size-2 !bg-indigo-500" />
    </div>
  );
}

const nodeTypes = { module: ModuleNodeView };

export default function RepositoryMapPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [graph, setGraph] = useState<RepositoryMap | null>(null);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);
  const [selected, setSelected] = useState<RepositoryMapNode | null>(null);

  useEffect(() => {
    let active = true;
    apiRequest<RepositoryMap>(`/map/${id}`)
      .then((result) => { if (active) setGraph(result); })
      .catch((reason: unknown) => {
        if (!active) return;
        if (reason instanceof ApiError && (reason.code === "module_analysis_incomplete" || reason.code === "analysis_incomplete")) {
          setError({ title: "Repository Map is not ready", message: reason.message });
        } else if (reason instanceof ApiError && reason.status === 404) {
          setError({ title: "Repository not found", message: "This repository is unavailable in your account." });
        } else if (reason instanceof ApiError && reason.status === 401) {
          setError({ title: "Sign-in required", message: "Sign in again to view this repository map." });
        } else {
          setError({ title: "Map could not be loaded", message: reason instanceof Error ? reason.message : "Please retry in a moment." });
        }
      });
    return () => { active = false; };
  }, [id]);

  const nodes = useMemo<ModuleFlowNode[]>(() => graph?.nodes.map((module) => ({
    id: module.id,
    type: "module",
    position: module.position,
    data: module,
  })) ?? [], [graph]);
  const edges = useMemo<Edge[]>(() => graph?.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.weight > 1 ? String(edge.weight) : undefined,
    markerEnd: { type: MarkerType.ArrowClosed, color: "#64748b" },
    style: { stroke: "#64748b", strokeWidth: Math.min(4, 1 + Math.log2(edge.weight)) },
    labelStyle: { fill: "#475569", fontSize: 11 },
    labelBgStyle: { fill: "#f8fafc" },
    type: "smoothstep",
  })) ?? [], [graph]);

  const selectNode = useCallback((_event: React.MouseEvent, node: ModuleFlowNode) => setSelected(node.data), []);

  return (
    <main className="flex min-h-screen flex-col bg-slate-50">
      <header className="border-b bg-white"><nav className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between px-6"><div className="flex items-center gap-4"><Link href={`/repositories/${id}`} className="font-semibold text-slate-900">RepoLens</Link><span className="text-slate-300">/</span><span className="text-sm text-slate-600">Repository Map</span></div><Link href={`/repositories/${id}`} className="text-sm font-medium text-indigo-700 hover:text-indigo-900">Back to Overview</Link></nav></header>
      <section className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-6 py-6">
        <div className="mb-5"><p className="text-xs font-semibold uppercase tracking-[.2em] text-indigo-700">Interactive Repository Map</p><h1 className="mt-2 text-2xl font-semibold tracking-tight">Explore modules and dependencies</h1><p className="mt-2 text-sm text-slate-600">Each node represents a logical module. Directed edges show imports between modules; individual files appear in the module details.</p></div>
        {error ? <div className="grid min-h-[55vh] place-items-center rounded-2xl border bg-white p-8 text-center"><div><h2 className="text-lg font-semibold">{error.title}</h2><p role="alert" className="mt-2 max-w-xl text-sm text-slate-600">{error.message}</p><div className="mt-5 flex justify-center gap-3"><button onClick={() => router.refresh()} className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-medium text-white">Retry</button><Link href={`/repositories/${id}`} className="rounded-lg border px-4 py-2 text-sm font-medium">Repository Overview</Link></div></div></div>
          : graph === null ? <div role="status" className="grid min-h-[55vh] place-items-center rounded-2xl border bg-white text-sm text-slate-600">Loading the saved module graph…</div>
            : graph.nodes.length === 0 ? <div className="grid min-h-[55vh] place-items-center rounded-2xl border bg-white p-8 text-center"><div><h2 className="text-lg font-semibold">No cohesive modules detected</h2><p className="mt-2 max-w-lg text-sm text-slate-600">The analyzed source files did not form non-trivial directory groups or connected import communities. No placeholder graph was created.</p><Link href={`/repositories/${id}`} className="mt-5 inline-block text-sm font-semibold text-indigo-700 underline">Return to Repository Overview</Link></div></div>
              : <><div className="relative h-[62vh] min-h-[446px] flex-1 overflow-hidden rounded-2xl border bg-white" aria-label="Interactive module graph">
                <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodeClick={selectNode} className="!h-[62vh] !w-full" fitView fitViewOptions={{ padding: 0.2 }} nodesDraggable={false} nodesConnectable={false} onlyRenderVisibleElements minZoom={0.2} maxZoom={2} proOptions={{ hideAttribution: false }}>
                  <Background color="#cbd5e1" gap={24} size={1} />
                  <MiniMap pannable zoomable nodeColor={(node) => node.data.category ? "#6366f1" : "#64748b"} />
                  <Controls />
                </ReactFlow>
                <p className="pointer-events-none absolute bottom-3 left-4 rounded-md bg-white/90 px-2 py-1 text-[11px] text-slate-500">{graph.parsed_file_count != null && graph.assigned_file_count != null && graph.standalone_file_count != null ? <>{graph.parsed_file_count.toLocaleString()} parsed files · {graph.assigned_file_count.toLocaleString()} assigned to modules · {graph.standalone_file_count.toLocaleString()} standalone</> : <>{nodes.length.toLocaleString()} modules · {edges.length.toLocaleString()} dependency links</>}</p>
              </div>{(graph.standalone_files?.length ?? 0) > 0 && <details className="mt-3 rounded-xl border bg-white p-4"><summary className="cursor-pointer text-sm font-medium">{graph.standalone_file_count?.toLocaleString()} parsed files are standalone (not assigned to a module)</summary><ul className="mt-3 space-y-1">{graph.standalone_files?.map((file) => <li key={file} className="break-all font-mono text-xs text-slate-600">{file}</li>)}</ul></details>}</>}
      </section>
      {selected && <><button aria-label="Close module details" onClick={() => setSelected(null)} className="fixed inset-0 z-20 cursor-default bg-slate-950/20"/><aside aria-label="Module details" className="fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col border-l bg-white shadow-2xl"><header className="flex items-start justify-between border-b p-6"><div><p className="text-xs font-semibold uppercase tracking-[.18em] text-indigo-700">Module details</p><h2 className="mt-2 text-xl font-semibold">{selected.name}</h2>{selected.category && <p className="mt-1 text-sm capitalize text-slate-500">{selected.category}</p>}</div><button aria-label="Close module details" onClick={() => setSelected(null)} className="rounded-lg border px-3 py-1.5 text-sm">Close</button></header><div className="flex-1 space-y-6 overflow-y-auto p-6"><section><h3 className="text-sm font-semibold">Responsibility</h3><p className="mt-2 text-sm leading-6 text-slate-600">{selected.description || "No responsibility description is available for this module."}</p><p className="mt-3 text-xs text-slate-500">{selected.file_count.toLocaleString()} files</p></section><section><h3 className="text-sm font-semibold">Files</h3>{selected.files.length ? <ul className="mt-2 max-h-64 space-y-1 overflow-y-auto rounded-lg bg-slate-50 p-3">{selected.files.map((file) => <li key={file} className="break-all font-mono text-xs leading-5 text-slate-700">{file}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">No file paths are available.</p>}</section><section><h3 className="text-sm font-semibold">Exported symbols</h3>{selected.exported_symbols.length ? <ul className="mt-2 flex flex-wrap gap-2">{selected.exported_symbols.map((symbol) => <li key={symbol} className="rounded-md bg-indigo-50 px-2 py-1 font-mono text-xs text-indigo-800">{symbol}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">No exported symbols were identified by static analysis.</p>}</section><section><h3 className="text-sm font-semibold">Technology dependencies</h3>{selected.technology_dependencies.length ? <ul className="mt-2 flex flex-wrap gap-2">{selected.technology_dependencies.map((dependency) => <li key={dependency} className="rounded-md bg-slate-100 px-2 py-1 font-mono text-xs">{dependency}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">No external imports were identified for this module.</p>}</section></div></aside></>}
    </main>
  );
}

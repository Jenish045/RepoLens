const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const PREFIX = "/api/v1";

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) { super(message); this.name = "ApiError"; }
}

export type RepoCard = { id: number; name: string; owner: string; full_name: string; description: string | null; primary_language: string | null; size_kb: number; updated_at: string | null; default_branch: string | null };
export type RepoList = { data: RepoCard[]; meta: { page: number; per_page: number; has_more: boolean } };
export type AnalysisStatus = { analysis_id: string; repository_id: string; status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED"; stage: string; stage_index: number; progress: number; completed_stages: string[]; deferred_stages: string[]; failure: { code: string; message: string } | null };
export type ParsedFile = { path: string; language: string; declaration_count: number; import_export_count: number; parse_status: "parsed" | "parsed_with_errors"; module_name?: string | null };
export type Overview = { repository: { id: string; name: string; owner: string; description: string | null; default_branch: string | null; primary_language: string | null; language_breakdown: Record<string, number> | null; file_count: number | null; size_kb: number | null; technologies: string[]; module_count: number | null; entry_points: string[]; commit_sha: string | null; analyzed_at: string | null; analysis_status: string }; summary: string | null; architecture_summary: string | null; structural_data: { parsed_file_count?: number; parsed_files?: ParsedFile[]; symbol_count?: number; import_count?: number; parse_error_count?: number; symbols?: {path:string;kind:string;name:string;start_line:number;docstring?:string|null;decorators?:string[];exported?:boolean}[]; imports?: {path:string;declaration:string;line:number;kind?:string}[]; completed_stages?: string[]; deferred_stages?: string[] } | null };
export type RepositoryMapNode = { id: string; name: string; category: string | null; description: string | null; file_count: number; position: { x: number; y: number }; files: string[]; exported_symbols: string[]; technology_dependencies: string[] };
export type RepositoryMapEdge = { id: string; source: string; target: string; weight: number };
export type RepositoryMap = { repository_id: string; commit_sha: string; nodes: RepositoryMapNode[]; edges: RepositoryMapEdge[]; parsed_file_count?: number | null; assigned_file_count?: number | null; standalone_file_count?: number | null; standalone_files?: string[] | null };

export function getToken(): string | null { if (typeof window === "undefined") return null; return sessionStorage.getItem("repolens_session"); }
export function clearSession() { if (typeof window !== "undefined") sessionStorage.removeItem("repolens_session"); }
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = getToken(); if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try { response = await fetch(new URL(`${PREFIX}${path}`, API_BASE_URL), { ...init, headers }); }
  catch { throw new ApiError("RepoLens could not reach the API. Check that the backend is running.", 0); }
  if (response.status === 401 && typeof window !== "undefined") { clearSession(); window.location.assign("/"); }
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new ApiError(body.message ?? "The request could not be completed.", response.status, body.error); }
  return response.json() as Promise<T>;
}

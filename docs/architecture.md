# Architecture notes

The normative architecture and roadmap are in [RepoLens_Engineering_Specification.pdf](../RepoLens_Engineering_Specification.pdf), Version 2.0 Expanded. This file summarizes the architecture implemented in this repository; it does not replace the specification.

## Shape

RepoLens is a modular monolith: one Next.js frontend and one FastAPI backend with internal boundaries for the Repository Processing Engine, Repository Intelligence Engine, and Report Engine. The processing and intelligence paths are implemented; the Report Engine package exists as a boundary but has no report workflow yet. Do not introduce service decomposition, Redis, or additional infrastructure without evidence that current in-process processing is a bottleneck.

## Data and trust boundaries

- GitHub OAuth identifies the user. The GitHub token is encrypted in the user record; the browser receives a short-lived RepoLens JWT.
- Only public repositories are analyzed. Source is untrusted input: clone it into a unique temporary workspace, read it without executing it, and guarantee cleanup on both success and failure.
- PostgreSQL/Neon is the durable system of record. Repository intelligence, module metadata, source chunks, embeddings, and analysis jobs are persisted there.
- Analysis is keyed to the exact Git commit SHA. A hit is valid only when the relevant Overview, module, and semantic artifacts match that commit.
- FAISS `IndexFlatIP` is an in-memory derived index rebuilt from normalized 384-dimensional PostgreSQL vectors. It is not durable authority.

## Implemented pipeline

The backend validates a public repository and its size, shallow-clones and verifies the commit, enumerates tracked files, detects technologies, parses Python/Java/JavaScript/TypeScript using Tree-sitter, extracts structural metadata, detects deterministic modules, lays them out with server-side Dagre, builds semantic chunks and BGE embeddings, persists those vectors, and prepares the dashboard. Analysis reports the final `PREPARING_DASHBOARD` stage and then completes. `Generating insights` remains deferred.

The clone subprocess uses the standard `subprocess` module through `asyncio.to_thread`; it does not depend on the active Windows asyncio loop's subprocess transport. Keep the shallow clone flags, token handling, return-code and timeout behavior, commit verification, and `TemporaryDirectory` lifecycle intact.

## Implemented user surfaces

- Repository Overview: metadata, technologies, entry points, language inventory, parse counts, symbols, and imports/exports.
- Repository Map: deterministic logical modules, aggregated import edges, server-persisted Dagre positions, and React Flow rendering.
- Semantic Explorer: concept-based retrieval over saved semantic chunks, with module, score, file, line, symbol, and source context.

Repository Insights, generated summaries, grounded conversational Q&A, PDF/Markdown reports, and generated learning paths are not implemented. The presence of dependency packages or schema placeholders does not mean those flows are available.

## Migrations

Alembic is the only schema migration mechanism. The chain is linear from `0001_initial_schema` through `0004_semantic_chunks`; the current intended head is `0004_semantic_chunks`. Its additive changes include chunk commit provenance, module/symbol metadata, chunk ordering, and a repository/commit index. Apply migrations with the backend's configured database; never drop or recreate the database to resolve drift.

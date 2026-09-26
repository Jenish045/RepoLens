# Architecture notes

The accepted design is maintained in `RepoLens_Engineering_Specification.pdf`. RepoLens is one modular monolith and one FastAPI process, with three internal engine boundaries: Repository Processing, Repository Intelligence, and Report. The Next.js frontend calls a path-versioned REST API.

PostgreSQL is the durable source of truth. FAISS is a disposable in-memory retrieval structure reconstructed from normalized embedding vectors persisted with repository chunks. Repository intelligence is cached by commit SHA. Deterministic static analysis precedes generative explanations; source repository code is treated as untrusted data and is never executed.

## Foundation status

Currently present: frontend shell and configuration, FastAPI application and `/health`, settings and lazy database engine configuration, ORM model definitions for the six specified entities, and a first Alembic migration. Engine packages, schemas, and versioned API router are boundaries only. OAuth, analysis, AI, search, graph, insights, exports, and dashboard workflows remain future implementation work.

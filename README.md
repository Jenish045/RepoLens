# RepoLens

**Understand software systems, not just source code.**

RepoLens analyzes public GitHub repositories to make their structure easier to understand. It produces a repository overview, a deterministic module map, and semantic search over persisted source chunks. It reads source as data and never executes repository code.

## Current implementation

- GitHub OAuth sign-in and public repository selection.
- Commit-SHA validation and same-commit analysis caching.
- Asynchronous analysis with isolated, temporary shallow clones.
- Tree-sitter parsing for Python, Java, JavaScript, and TypeScript.
- Repository Overview with metadata, technologies, entry points, parse inventory, and structural counts.
- Deterministic two-pass module detection and an interactive Dagre/React Flow Repository Map.
- AST-aligned semantic chunks, CPU BGE embeddings, PostgreSQL persistence, and semantic search backed by a rebuildable in-memory FAISS index.

Repository Insights, generated summaries, grounded Ask RepoLens answers, PDF/Markdown report export, and a generated learning path are not implemented in the current application. The master specification describes the target system and remains authoritative for architecture and roadmap decisions; the project-state document distinguishes those plans from shipped code.

## Architecture

RepoLens is a modular monolith served by one FastAPI application. Its internal boundaries are the Repository Processing Engine, Repository Intelligence Engine, and Report Engine. The current processing and intelligence code is implemented; the Report Engine remains a reserved boundary. Next.js provides the web UI. Neon PostgreSQL is the system of record for users, repositories, analysis metadata, modules, semantic chunks, and vectors. FAISS is an in-memory derived index reconstructed from PostgreSQL.

The product is public-repository-only and supports repositories up to 3,000 tracked files by default. GitHub credentials remain server-side and encrypted at rest. The backend makes read requests. The configured classic OAuth `public_repo` scope is broader than read-only at the token level; see the security note below and the project-state document.

## Technology stack

- Frontend: Next.js 15, React 19, TypeScript, Tailwind CSS, React Flow, Dagre.
- Backend: Python 3.12, FastAPI, Pydantic Settings, SQLAlchemy 2, Alembic, psycopg 3.
- Analysis and retrieval: Tree-sitter grammars for four languages, sentence-transformers with `BAAI/bge-small-en-v1.5` (384 dimensions), FAISS `IndexFlatIP`.
- Persistence and development targets: Neon PostgreSQL; Vercel/Render are planned deployment targets.

See [SETUP_REQUIREMENTS.md](SETUP_REQUIREMENTS.md) for credentials and setup, [docs/architecture.md](docs/architecture.md) for the architecture summary, and [docs/RepoLens_Project_State_and_Decisions.txt](docs/RepoLens_Project_State_and_Decisions.txt) for the detailed current state and decisions. The authoritative design reference is [RepoLens_Engineering_Specification.pdf](RepoLens_Engineering_Specification.pdf), Version 2.0 Expanded.

## Quick start

### Backend (PowerShell)

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
# Fill in DATABASE_URL, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, and JWT_SECRET.
alembic upgrade head
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`; `GET /health` is a process liveness check. Versioned product routes use `/api/v1`.

### Frontend (PowerShell)

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

Set `NEXT_PUBLIC_API_URL=http://localhost:8000`. The local UI is served at `http://localhost:3000`.

### Checks

```powershell
cd backend
python -m pytest

cd ..\frontend
npm run typecheck
npm run lint
npm run build
```

### Migration state

Run from `backend/` with the configured database reachable:

```powershell
alembic current
alembic heads
alembic upgrade head
```

The intended chain has one head, `0004_semantic_chunks`. Migrations are additive schema changes; do not reset or recreate the database.

## Analysis flow

1. The user signs in with GitHub; the browser receives a short-lived RepoLens JWT while the GitHub token stays encrypted server-side.
2. RepoLens lists public repositories and resolves the current commit SHA.
3. If stored Overview, module, and semantic data match that SHA, the cached result is served. Otherwise a background analysis is queued.
4. The backend shallow-clones the commit into a temporary workspace, verifies `HEAD`, enumerates tracked files, detects technologies, parses supported source, and extracts metadata.
5. Deterministic module detection assigns files using directory topology and import cohesion; Dagre positions are persisted for the React Flow map.
6. Semantic chunks retain file/line/commit provenance; normalized BGE vectors are stored in PostgreSQL and loaded into a bounded FAISS index for retrieval.
7. The temporary workspace is removed on success and failure.

## API surfaces currently present

- `GET /api/v1/auth/github` and `GET /api/v1/auth/callback`: GitHub sign-in.
- `GET /api/v1/repositories`: authenticated user's public repositories.
- `GET /api/v1/repositories/analyzed`: completed repositories for semantic search.
- `POST /api/v1/analysis/trigger`, `GET /api/v1/analysis/{id}/status`: analysis trigger and progress.
- `GET /api/v1/intelligence/{repo_id}`: Repository Overview data.
- `GET /api/v1/map/{repo_id}`: owner-scoped module graph and positions.
- `POST /api/v1/search/semantic`: owner-scoped semantic retrieval.
- `POST /api/v1/analysis/{repo_id}/parsed-files/backfill`: verified metadata backfill for older completed records.

## Security note

RepoLens itself uses GitHub read endpoints and never changes repositories. The classic OAuth `public_repo` scope requested by the implementation can authorize writes to public repositories at the credential level. Do not describe that token scope as read-only. Narrowing it would require an explicit authentication-contract change (for example, changing the OAuth application model) and is not part of this polish pass.

Never commit `.env` files or real credentials. `.env.example` files contain placeholders; frontend `NEXT_PUBLIC_` variables are browser-visible and must not hold secrets. Analyzed repository code is untrusted input, is only read as data, and is never executed.

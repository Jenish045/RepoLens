# RepoLens

**Understand software systems, not just source code.**

RepoLens is an AI-powered Repository Intelligence Platform intended to help developers understand unfamiliar software repositories quickly. Its architecture prioritizes deterministic source structure and evidence-grounded explanations.

> **Current stage: Capabilities 1–2.** GitHub sign-in, public repository selection, SHA-based analysis caching, asynchronous Tree-sitter metadata analysis, the Repository Overview, and the deterministic Interactive Repository Map are implemented. Semantic Explorer, Insights, Ask RepoLens, and report export remain out of scope.

## Architecture

RepoLens is a modular monolith with one FastAPI application. Its planned internal engines are Repository Processing, Repository Intelligence, and Report. PostgreSQL (Neon) is the durable system of record; a future in-memory FAISS `IndexFlatIP` is derived and rebuildable from stored vectors. The frontend is a Next.js application.

Supported analysis languages: Python, Java, JavaScript, and TypeScript. Only public repositories are supported.

### Technology stack

- Frontend: Next.js 15, React 19, TypeScript, Tailwind CSS, shadcn/ui foundation, React Flow
- Backend: Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic
- Data and future analysis: Neon PostgreSQL, Tree-sitter, BAAI/bge-small-en-v1.5, sentence-transformers, FAISS, Gemini 2.5 Flash, Jinja2, WeasyPrint
- Later deployment: Vercel, Render, and Neon

## Repository layout

```text
frontend/                   Next.js application shell
backend/
  app/
    api/                    Versioned API routers
    core/                   Settings and shared primitives
    database/               SQLAlchemy base and connection setup
    models/                 Specification entities plus persisted analysis jobs
    schemas/                Pydantic API schemas
    engines/
      processing/           Isolated clone, Tree-sitter metadata, and persisted Dagre layout
      intelligence/         Deterministic two-pass module detection
      reports/              Report Engine boundary
  migrations/               Alembic environment and initial schema migration
  tests/                    Backend foundation tests
docs/                       Architecture and development notes
.github/                    Reserved for future repository configuration
```

## Requirements and setup

See [SETUP_REQUIREMENTS.md](SETUP_REQUIREMENTS.md) for all software, accounts, credentials, environment variables, and setup steps. The authoritative design reference is [RepoLens_Engineering_Specification.pdf](RepoLens_Engineering_Specification.pdf).

Copy the relevant `.env.example` files to `.env.local` in `frontend/` and `.env` in `backend/`, then fill local values. Templates contain placeholders only.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

The local UI is served at `http://localhost:3000` by default. Frontend checks:

```powershell
npm run typecheck
npm run lint
npm run build
```

### Backend

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

The API is served at `http://localhost:8000`; `GET /health` checks process liveness. Product endpoints use `/api/v1`.

### Database and migrations

Create a Neon PostgreSQL database and set `DATABASE_URL` to its SQLAlchemy-compatible connection string (`postgresql+psycopg://...`). With the backend environment active:

```powershell
alembic upgrade head
```

Migrations create the specification entities and add encrypted OAuth credentials, repository overview metadata, structural intelligence, and durable analysis job status. Running migrations requires a reachable configured PostgreSQL database. Importing the app does not connect to the database.

### Tests

```powershell
cd backend
python -m pytest
```

Backend tests cover OAuth state, public-only/supported scope, Tree-sitter metadata, evidence-based technology detection, SHA cache hit/miss behavior, deterministic module assignment, module coupling, owner-scoped map access, and repeatable Dagre layout. Frontend typecheck/lint/build commands are listed above.

## Security and data handling

GitHub tokens are encrypted in the server-side user record and users are keyed by numeric GitHub ID. RepoLens only makes read requests and never changes repositories. Repository clones are temporary, only tracked metadata is persisted, and repository code is never executed. See `SETUP_REQUIREMENTS.md` for local OAuth setup.

## Repository analysis and map

1. Create a GitHub OAuth App with homepage `http://localhost:3000` and callback `http://localhost:8000/api/v1/auth/callback`.
2. Copy `.env.example` to `backend/.env`, set `DATABASE_URL`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, and a long random `JWT_SECRET`. OAuth requests `read:user public_repo`.
3. Apply the schema with `alembic upgrade head`, then start the backend and frontend.
4. Sign in from `http://localhost:3000`; RepoLens returns a short-lived application JWT in the browser URL fragment, while the GitHub token remains encrypted on the server.
5. Select a public repository. RepoLens checks its current default-branch commit SHA. A completed matching SHA with module data returns cached intelligence; older same-SHA Overview records are upgraded without repeating parsing.
6. The task shallow-clones into a `repolens_` temporary directory, parses supported source files and recognized manifests without executing code, deterministically groups modules from directory topology and import cohesion, lays out the module graph on the server with Dagre, persists bounded metadata, and removes the temporary workspace.
7. View Overview data at `GET /api/v1/intelligence/{repo_id}` and the owner-scoped module graph at `GET /api/v1/map/{repo_id}`. Repository Map nodes are logical modules and directed edges aggregate inter-module imports. React Flow renders the saved server positions and opens a module detail drawer; individual files are listed only inside that drawer.

Local OAuth requires valid GitHub OAuth settings and a reachable PostgreSQL database. Without those credentials, `/auth/github` redirects back to the landing page with a clear configuration message. Analysis supports up to 3,000 tracked files by default. Semantic Explorer, generated insights, Q&A, and report export are not implemented in this release.

**Permission note:** GitHub's required OAuth `public_repo` scope can grant read/write access to public repositories. RepoLens itself only performs read requests, but this scope is broader than read-only at the token level. GitHub Apps support granular repository permissions if the project later changes its authentication contract.

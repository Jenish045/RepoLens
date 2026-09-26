# RepoLens

**Understand software systems, not just source code.**

RepoLens is an AI-powered Repository Intelligence Platform intended to help developers understand unfamiliar software repositories quickly. Its architecture prioritizes deterministic source structure and evidence-grounded explanations.

> **Current stage: Project Foundation.** This repository contains the application skeleton, database schema foundation, and developer setup. Repository analysis, dashboard capabilities, GitHub sign-in, and AI features are not implemented.

## Architecture

RepoLens is a modular monolith with one FastAPI application. Its planned internal engines are Repository Processing, Repository Intelligence, and Report. PostgreSQL (Neon) is the durable system of record; a future in-memory FAISS `IndexFlatIP` is derived and rebuildable from stored vectors. The frontend is a Next.js application.

Supported repository languages in the specification: Python, Java, JavaScript, and TypeScript. This describes intended analysis scope, not current functionality.

### Technology stack

- Frontend: Next.js 15, React 19, TypeScript, Tailwind CSS, shadcn/ui foundation, React Flow and Dagre (for future module graph)
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
    models/                 Six specification-aligned entities
    schemas/                Pydantic API schemas
    engines/
      processing/           Repository Processing Engine boundary
      intelligence/         Repository Intelligence Engine boundary
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

The API is served at `http://localhost:8000`; the foundation health endpoint is `GET /health`. The configured API prefix is `/api/v1` for future versioned routes.

### Database and migrations

Create a Neon PostgreSQL database and set `DATABASE_URL` to its SQLAlchemy-compatible connection string (`postgresql+psycopg://...`). With the backend environment active:

```powershell
alembic upgrade head
```

The initial migration creates the six entities described in the specification. Running migrations requires a reachable configured PostgreSQL database. Importing the FastAPI app and loading settings does not connect to the database.

### Tests

```powershell
cd backend
python -m pytest
```

The foundation test suite checks app import, the health response, configuration loading, and Alembic configuration. Frontend typecheck/lint/build commands are listed above. No product capability tests exist at this foundation stage.

## Security and data handling

Never commit actual environment files, tokens, or keys. The eventual OAuth access token remains server-side and users are keyed by numeric GitHub ID. Future analysis must not execute repository code and must remove its temporary clone even on failure. See the full security checklist in `SETUP_REQUIREMENTS.md`.

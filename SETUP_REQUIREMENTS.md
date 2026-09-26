# RepoLens setup requirements

This guide covers the project foundation only. No repository analysis or dashboard feature is implemented. Keep [RepoLens_Engineering_Specification.pdf](RepoLens_Engineering_Specification.pdf) as the normative architecture reference.

## A. Required software

| Item | Needed when | Notes |
|---|---|---|
| Git | Immediately | Local source control. Do not configure a remote until the project owner provides one. |
| Node.js 24 LTS (recommended) | Immediately | Next.js 15 requires Node.js 18.18 or newer. Use a maintained LTS release. Check with `node --version`. ([Next.js 15 requirements](https://nextjs.org/docs/15/pages/getting-started/installation), [Node.js release schedule](https://nodejs.org/en/about/previous-releases)) |
| npm (included with Node.js) | Immediately | This foundation selects npm and commits `package-lock.json` when generated. |
| Python 3.12 | Immediately | Backend runtime. Check with `py -3.12 --version` on Windows or `python3.12 --version` elsewhere. |
| PostgreSQL-compatible database | For migration/integration work | Neon PostgreSQL account/instance; no local PostgreSQL server is required if Neon is used. |
| Docker | Recommended now; needed for container/deployment work later | Backend Dockerfile is a foundation for a later Render deployment. |
| C/C++ build tools and platform libraries | When installing analysis dependencies as needed | Some Python packages (notably FAISS/Tree-sitter/model dependencies and WeasyPrint) may have platform-specific wheels or OS library requirements. |

## B. Required accounts

- GitHub account, for the eventual public-repository OAuth flow.
- GitHub OAuth application owned/configured by the project team.
- Google AI Studio / Gemini API access for the eventual Gemini integration.
- Neon account and PostgreSQL project for shared development data.
- Deployment accounts are not needed for local work. Later targets are Vercel (frontend), Render (backend), and Neon (database).
- The project budget is $0 billed: use free tiers only and check provider quota/billing settings before enabling hosted services.

## C. Required API keys and credentials

Required before implementing their respective integrations:

- GitHub OAuth **Client ID** and **Client Secret**.
- Gemini **API key**.
- Neon PostgreSQL **connection string**.
- Application **JWT signing secret**, generated locally for development and securely generated in each deployed environment.

Tree-sitter, BAAI/bge-small-en-v1.5, sentence-transformers, FAISS, React Flow, Dagre, SQLAlchemy, Alembic, Jinja2, and WeasyPrint do **not** require external API keys. The BGE model, FAISS index, and Tree-sitter parsing run locally. Gemini is the hosted generative-model integration and does require a key.

## D. Environment variables

The authoritative placeholders live in `backend/.env.example` and `frontend/.env.example`. Names below are consistent with those templates and backend settings.

| Variable | Location | Purpose | Needed now? |
|---|---|---|---|
| `DATABASE_URL` | Backend | SQLAlchemy PostgreSQL connection string, e.g. `postgresql+psycopg://<user>:<password>@<host>/<database>?sslmode=require` | For migrations/database access |
| `GITHUB_CLIENT_ID` | Backend | OAuth application client ID | Later, for OAuth |
| `GITHUB_CLIENT_SECRET` | Backend | OAuth application secret (server-side only) | Later, for OAuth |
| `GITHUB_CALLBACK_URL` | Backend | Registered OAuth callback URL | Later, for OAuth |
| `GEMINI_API_KEY` | Backend | Gemini API credential | Later, for generative features |
| `JWT_SECRET` | Backend | Signs application session JWTs | Later, for authentication |
| `FRONTEND_URL` | Backend | Frontend origin used by backend configuration | Local CORS/configuration |
| `BACKEND_URL` | Backend | Backend's externally reachable base URL | Local callback/link configuration |
| `NEXT_PUBLIC_API_URL` | Frontend | Browser-visible base URL for the API | Frontend API client |
| `API_V1_PREFIX` | Backend | Versioned API route prefix; foundation default is `/api/v1` | Optional; default is sufficient |
| `ENVIRONMENT` | Backend | Runtime environment label; default is `development` | Optional |

`NEXT_PUBLIC_API_URL` is public configuration, not a secret. Never expose GitHub secrets, Gemini keys, database credentials, or `JWT_SECRET` through a `NEXT_PUBLIC_` variable. Environment files are ignored by Git; `.env.example` files are intentionally tracked and contain placeholders only.

## E. Local development setup

1. Install the software in section A.
2. Copy `backend/.env.example` to `backend/.env` and `frontend/.env.example` to `frontend/.env.local`.
3. Replace only values needed for your local work. Do not commit the copied environment files.
4. Follow the backend and frontend instructions below.
5. Configure Neon and apply Alembic migrations when working on database persistence.

The foundation can import and start the backend without connecting to PostgreSQL. Database operations and migrations require a valid reachable `DATABASE_URL`.

## F. Database setup

1. Create a Neon PostgreSQL project/database.
2. Copy the pooled or direct connection string as appropriate for development, and use the SQLAlchemy `postgresql+psycopg://` driver form in `DATABASE_URL`.
3. Run migrations from `backend/` with its virtual environment active: `alembic upgrade head`.
4. For schema changes, generate/review migrations before applying them. PostgreSQL is the durable system of record. Future FAISS indexes are derived, disposable, and reconstructed from the stored 384-dimensional normalized vectors.

The initial schema has `users`, `repositories`, `repository_intelligence`, `modules`, `repository_chunks`, and `reports`. It follows the specification's UUID identities, numeric unique `github_id`, commit SHA cache key, JSONB metadata, report/status enums, and cascading repository-child relationships.

## G. GitHub OAuth setup

OAuth is not implemented yet. When implementing it:

1. Register a GitHub OAuth application in the project owner's GitHub account.
2. Set its homepage to the selected frontend URL and its callback to the exact `GITHUB_CALLBACK_URL`.
3. Store its Client ID and Client Secret in backend environment configuration only.
4. The specification requires read-only `read:user` and `public_repo` access. Do not request private repository permissions in v1.
5. Keep the GitHub access token on the server; the browser is intended to receive a signed application JWT. User identity must use numeric `github_id`, not username.

Local callback example (replace if the route/port changes): `http://localhost:8000/api/v1/auth/callback`.

## H. Gemini setup

Gemini 2.5 Flash is the specified hosted model for future grounded intelligence and answers. Obtain an API key through the team's Google AI Studio / Gemini setup and set `GEMINI_API_KEY` in `backend/.env`. Do not put it in frontend configuration. No Gemini calls occur in this project foundation.

## I. Frontend setup

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_URL` to `http://localhost:8000` for local use. Available foundation checks: `npm run typecheck`, `npm run lint`, and `npm run build`. React Flow and Dagre are dependencies for later graph implementation; no repository graph is currently rendered.

## J. Backend setup

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

On macOS/Linux, use `python3.12 -m venv .venv` and `source .venv/bin/activate`. The API foundation exposes `GET /health`. The package boundaries reserve one FastAPI process for API/core/database and the processing, intelligence, and report engines.

The full specified stack includes Tree-sitter grammars, sentence-transformers/BGE, faiss-cpu, Gemini client support, Jinja2, and WeasyPrint. These are declared in the backend dependency set for later work and may require additional platform libraries. None are invoked by this foundation.

## K. Testing

Backend foundation checks:

```powershell
cd backend
python -m pytest
```

This suite checks FastAPI app import, `/health`, settings/configuration loading, and Alembic configuration. Frontend checks from `frontend/` are `npm run typecheck`, `npm run lint`, and `npm run build`. Database migrations require a reachable database. Future unit, integration, API contract, and end-to-end coverage is described in the engineering specification; those product tests are not part of this scaffold.

## L. Future deployment requirements

- Vercel project for `frontend/`, with `NEXT_PUBLIC_API_URL` set to the deployed backend API origin.
- Render web service built from `backend/Dockerfile`, with backend secrets and public service URL set in its environment.
- Neon PostgreSQL production database and secured `DATABASE_URL`.
- Production GitHub OAuth callback and Gemini key configured server-side.
- Strong, unique production `JWT_SECRET`; configure exact frontend/backend origins and OAuth callback values.
- Apply Alembic migrations as a controlled deployment step.

Do not create cloud resources or configure deployment secrets as part of this foundation task.

## M. Security and secrets checklist

- Keep `.env`, `.env.local`, and all real credentials out of commits. `.env.example` contains placeholders and must not contain usable credentials.
- Never send backend secrets to browser code or prefix them with `NEXT_PUBLIC_`.
- Keep OAuth tokens server-side; use numeric GitHub IDs as user identity.
- v1 supports public GitHub repositories only and read-only OAuth scopes.
- Never execute analyzed repository code, install its dependencies, invoke its scripts, or run its tests.
- Future analysis must use an isolated temporary workspace and guarantee cleanup on success and failure; source files must not remain stored after processing.
- Scope repository reads and writes to the authenticated user; never expose stack traces to clients.
- PostgreSQL stores durable embeddings; FAISS is only a rebuildable in-memory derived index.
- Do not add unknown Git remotes, publish credentials, create a GitHub repository, or push until the project owner separately handles GitHub initialization.

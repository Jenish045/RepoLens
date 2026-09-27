import asyncio
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import AuthenticatedUser
from app.api.routes import repositories as routes
from app.core.config import Settings
from app.core.security import create_oauth_state, validate_oauth_state
from app.database.base import Base
from app.engines.processing.languages import is_supported_language_name, language_for_path
from app.engines.processing.technologies import detect_technologies
from app.engines.processing.treesitter import parse_repository
from app.models import AnalysisStatus, Repository, RepositoryIntelligence, User
from app.schemas.repositories import AnalysisTriggerRequest


def _database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def _current_user(db: Session) -> AuthenticatedUser:
    user = User(github_id=314159, username="sample", github_access_token_encrypted="unused")
    db.add(user)
    db.flush()
    return AuthenticatedUser(user=user, github_access_token="test-token")


def test_oauth_state_is_signed_and_checked():
    settings = Settings(_env_file=None, jwt_secret="local-test-secret")
    state, cookie = create_oauth_state(settings)
    assert validate_oauth_state(state, cookie, settings)
    assert not validate_oauth_state("other", cookie, settings)
    assert not validate_oauth_state(state, None, settings)


def test_public_repository_listing_filters_private_items(monkeypatch):
    from app.api.services import github

    async def github_response(*_args, **_kwargs):
        return [{"id": 1, "private": False}, {"id": 2, "private": True}, {"id": 3}]

    monkeypatch.setattr(github, "github_get", github_response)
    rows, has_more = asyncio.run(github.list_public_repositories(object(), "test-token", page=1, per_page=30))
    assert rows == [{"id": 1, "private": False}]
    assert not has_more


def test_supported_languages_are_limited_to_capability_scope():
    assert language_for_path("src/main.tsx") == "TypeScript"
    assert all(is_supported_language_name(name) for name in ("Python", "Java", "JavaScript", "TypeScript"))
    assert not any(is_supported_language_name(name) for name in ("Go", "C++", "Rust", "Ruby"))


def test_tree_sitter_extracts_python_metadata(tmp_path):
    (tmp_path / "main.py").write_text('import os\n@decorate\nasync def run():\n    """Run it."""\n', encoding="utf-8")
    (tmp_path / "empty.py").write_text("# successfully parsed without declarations\n", encoding="utf-8")
    data = parse_repository(tmp_path, ["main.py", "empty.py"])
    assert data["import_count"] == 1
    assert data["symbol_count"] == 1
    assert data["symbols"][0]["async"] is True
    assert data["symbols"][0]["decorators"] == ["@decorate"]
    assert data["symbols"][0]["docstring"] == '"""Run it."""'
    assert data["parsed_file_count"] == len(data["parsed_files"]) == 2
    parsed = {item["path"]: item for item in data["parsed_files"]}
    assert parsed["main.py"] == {"path": "main.py", "language": "Python", "declaration_count": 1, "import_export_count": 1, "parse_status": "parsed"}
    assert parsed["empty.py"]["declaration_count"] == parsed["empty.py"]["import_export_count"] == 0


def test_tree_sitter_accepts_java_javascript_and_typescript(tmp_path):
    from app.engines.processing.technologies import _safe_file
    (tmp_path / "Main.java").write_text("package demo;\nimport java.util.List;\n@SpringBootApplication class Main { @GetMapping(\"/x\") public String run() { return \"x\"; } public static void main(String[] args) {} }", encoding="utf-8")
    (tmp_path / "main.js").write_text("const load = () => require('path');\nexport function run() {}", encoding="utf-8")
    (tmp_path / "types.ts").write_text("@sealed class Box<T> { value!: T }\ninterface Shape<T> { value: T }\ntype Id<T> = T;", encoding="utf-8")
    data = parse_repository(tmp_path, ["Main.java", "main.js", "types.ts"])
    assert data["parsed_file_count"] == 3
    assert data["imports"]
    assert {item["kind"] for item in data["symbols"]} >= {"package", "interface", "type_alias"}
    assert any(item["kind"] == "arrow_function" and item["name"] == "load" for item in data["symbols"])
    assert any(item.get("annotations") for item in data["symbols"] if item["language"] == "Java")
    assert any(item.get("decorators") for item in data["symbols"] if item["language"] == "TypeScript")
    outside = tmp_path.parent / "outside.toml"
    outside.write_text("[project]\ndependencies=['fastapi']", encoding="utf-8")
    try:
        (tmp_path / "pyproject.toml").symlink_to(outside)
    except OSError:
        return
    assert _safe_file(tmp_path, "pyproject.toml") != outside


def test_technology_detection_requires_manifest_evidence(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies":{"react":"^19","next":"15"}}', encoding="utf-8")
    found = detect_technologies(tmp_path, ["package.json"])
    assert [item["name"] for item in found] == ["Next.js", "React"]
    assert detect_technologies(tmp_path, ["src/main.tsx"]) == []


def test_cache_hit_returns_200_without_scheduling_work(monkeypatch):
    engine = _database()
    with Session(engine, expire_on_commit=False) as db:
        current = _current_user(db)
        repo = Repository(user_id=current.user.id, owner="sample", name="project", primary_language="Python", status=AnalysisStatus.COMPLETED, commit_sha="abc", file_count=2)
        repo.intelligence = RepositoryIntelligence(summary=None, structural_data_json={"symbol_count": 1, "semantic_analysis_sha": "abc", "semantic_chunk_count": 0}, module_analysis_sha="abc")
        db.add(repo)
        db.commit()

        async def remote(*_args, **_kwargs):
            return {"private": False, "language": "Python", "latest_commit_sha": "abc", "language_bytes": {}, "owner": {"login": "sample"}}

        monkeypatch.setattr(routes, "get_public_repository", remote)
        async def tree_size(*_args, **_kwargs):
            return None
        monkeypatch.setattr(routes, "validate_repository_tree_size", tree_size)
        monkeypatch.setattr(routes.httpx, "AsyncClient", lambda **_: _AsyncClient())
        tasks = BackgroundTasks()
        response = Response()
        result = asyncio.run(routes.trigger_analysis(AnalysisTriggerRequest(owner="sample", name="project"), tasks, response, db, current, Settings(_env_file=None)))
        assert result.cached is True
        assert result.repository_id == repo.id
        assert response.status_code == 200
        assert tasks.tasks == []


def test_legacy_inventory_backfill_is_sha_pinned_checked_and_does_not_replace_analysis(monkeypatch):
    engine = _database()
    with Session(engine, expire_on_commit=False) as db:
        current = _current_user(db)
        sha = "a" * 40
        repo = Repository(user_id=current.user.id, owner="sample", name="project", status=AnalysisStatus.COMPLETED, commit_sha=sha, analyzed_at=None)
        repo.intelligence = RepositoryIntelligence(module_analysis_sha=sha, structural_data_json={
            "parsed_file_count": 2, "symbol_count": 1, "import_count": 1, "parse_error_count": 0,
        })
        db.add(repo); db.flush()
        module = __import__("app.models", fromlist=["Module"]).Module(repository_id=repo.id, name="Import Cohesion Group 1", file_paths=["src/main.py"], file_count=1, position_x=0, position_y=0)
        db.add(module); db.commit()
        before_intel_id = repo.intelligence.id

        async def parsed(owner, name, commit_sha, *, max_files):
            assert (owner, name, commit_sha) == ("sample", "project", sha)
            assert max_files > 0
            return {
                "parsed_file_count": 2, "symbol_count": 1, "import_count": 1, "parse_error_count": 0,
                "parsed_files": [
                    {"path": "src/main.py", "language": "Python", "declaration_count": 1, "import_export_count": 1, "parse_status": "parsed"},
                    {"path": "src/empty.py", "language": "Python", "declaration_count": 0, "import_export_count": 0, "parse_status": "parsed"},
                ],
            }
        monkeypatch.setattr(routes, "parse_saved_public_commit", parsed)
        result = asyncio.run(routes.backfill_parsed_file_inventory(repo.id, db, current, Settings(_env_file=None)))
        assert result.backfilled is True and result.parsed_file_count == 2
        assert result.parsed_files[0].module_name == "Src"
        assert result.parsed_files[1].module_name is None
        assert repo.commit_sha == sha and repo.status == AnalysisStatus.COMPLETED
        assert repo.intelligence.module_analysis_sha == sha and repo.intelligence.id == before_intel_id
        assert repo.intelligence.structural_data_json["parsed_files"][1]["path"] == "src/empty.py"

        async def should_not_parse(*_args, **_kwargs):
            raise AssertionError("existing inventory must be idempotent")
        monkeypatch.setattr(routes, "parse_saved_public_commit", should_not_parse)
        repeated = asyncio.run(routes.backfill_parsed_file_inventory(repo.id, db, current, Settings(_env_file=None)))
        assert repeated.backfilled is False and repeated.parsed_file_count == 2
    engine.dispose()


def test_legacy_inventory_backfill_rejects_totals_mismatch_without_writing(monkeypatch):
    from app.core.errors import APIError
    engine = _database()
    with Session(engine, expire_on_commit=False) as db:
        current = _current_user(db)
        sha = "b" * 40
        repo = Repository(user_id=current.user.id, owner="sample", name="project", status=AnalysisStatus.COMPLETED, commit_sha=sha)
        repo.intelligence = RepositoryIntelligence(module_analysis_sha=sha, structural_data_json={"parsed_file_count": 1, "symbol_count": 0, "import_count": 0, "parse_error_count": 0})
        db.add(repo); db.commit()
        async def parsed(*_args, **_kwargs):
            return {"parsed_file_count": 2, "symbol_count": 0, "import_count": 0, "parse_error_count": 0, "parsed_files": []}
        monkeypatch.setattr(routes, "parse_saved_public_commit", parsed)
        try:
            asyncio.run(routes.backfill_parsed_file_inventory(repo.id, db, current, Settings(_env_file=None)))
            assert False, "expected mismatched historical totals to be rejected"
        except APIError as exc:
            assert exc.status_code == 409
        assert "parsed_files" not in repo.intelligence.structural_data_json
    engine.dispose()


class _AsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


def test_cache_miss_returns_202_and_queues_exactly_one_task(monkeypatch):
    engine = _database()
    with Session(engine, expire_on_commit=False) as db:
        current = _current_user(db)

        async def remote(*_args, **_kwargs):
            return {"private": False, "language": "TypeScript", "latest_commit_sha": "def", "language_bytes": {}, "owner": {"login": "sample"}, "updated_at": None}

        monkeypatch.setattr(routes, "get_public_repository", remote)
        async def tree_size(*_args, **_kwargs):
            return None
        monkeypatch.setattr(routes, "validate_repository_tree_size", tree_size)
        monkeypatch.setattr(routes.httpx, "AsyncClient", lambda **_: _AsyncClient())
        tasks = BackgroundTasks()
        response = Response()
        result = asyncio.run(routes.trigger_analysis(AnalysisTriggerRequest(owner="sample", name="project"), tasks, response, db, current, Settings(_env_file=None)))
        assert result.cached is False and result.analysis_id
        assert response.status_code == 202
        assert len(tasks.tasks) == 1
        assert tasks.tasks[0].args[2] == "def"


def test_workspace_is_removed_when_analysis_fails(monkeypatch, tmp_path):
    from app.core.errors import APIError
    from app.engines.processing import pipeline
    import tempfile

    engine = _database()
    repo_id, job_id = uuid4(), uuid4()
    with Session(engine) as db:
        user = User(github_id=271828, username="cleanup")
        db.add(user)
        db.flush()
        repo = Repository(id=repo_id, user_id=user.id, owner="cleanup", name="repo", commit_sha="sha", status=AnalysisStatus.QUEUED)
        db.add(repo)
        from app.models import AnalysisJob
        db.add(AnalysisJob(id=job_id, user_id=user.id, repository_id=repo_id, commit_sha="sha", status="QUEUED", stage="QUEUED", stage_index=0, progress_percent=0))
        db.commit()

    monkeypatch.setattr(pipeline, "get_engine", lambda: engine)
    real_tempdir = tempfile.TemporaryDirectory
    workspaces = []

    class TrackedTemporaryDirectory:
        def __init__(self, *args, **kwargs):
            self.inner = real_tempdir(dir=tmp_path, *args, **kwargs)
            self.name = self.inner.name
            workspaces.append(Path(self.name))

        def __enter__(self):
            return self.inner.__enter__()

        def __exit__(self, *args):
            return self.inner.__exit__(*args)

    async def fail_clone(_url, target, _token, *_args):
        target.mkdir()
        (target / "partial-clone-file").write_text("temporary", encoding="utf-8")
        raise APIError(502, "clone_failed", "safe error")

    monkeypatch.setattr(pipeline.tempfile, "TemporaryDirectory", TrackedTemporaryDirectory)
    monkeypatch.setattr(pipeline, "_clone", fail_clone)
    asyncio.run(pipeline.run_analysis(repo_id, job_id, "sha", "token"))
    assert len(workspaces) == 1
    assert not workspaces[0].exists()
    with Session(engine) as db:
        job = db.get(AnalysisJob, job_id)
        assert job.status == "FAILED"
        assert job.failure_code == "clone_failed"
        assert job.failure_message == "safe error"
        status = routes.analysis_status(job_id, db, AuthenticatedUser(user=db.get(User, job.user_id), github_access_token="test-token"))
        assert status.status == "FAILED"
        assert status.deferred_stages == ["Generating insights"]


def test_successful_background_analysis_clears_failure_and_completes(monkeypatch):
    from app.engines.processing import pipeline
    from app.models import AnalysisJob

    engine = _database()
    repo_id, job_id = uuid4(), uuid4()
    with Session(engine) as db:
        user = User(github_id=299792, username="success")
        db.add(user)
        db.flush()
        repo = Repository(id=repo_id, user_id=user.id, owner="success", name="repo", commit_sha="sha", status=AnalysisStatus.FAILED)
        job = AnalysisJob(id=job_id, user_id=user.id, repository_id=repo_id, commit_sha="sha", status="FAILED", stage="CLONING_REPOSITORY", stage_index=1, progress_percent=10, failure_code="old_failure", failure_message="old failure")
        db.add_all([repo, job])
        db.commit()

    monkeypatch.setattr(pipeline, "get_engine", lambda: engine)
    monkeypatch.setattr(pipeline, "_clone", lambda *_args, **_kwargs: asyncio.sleep(0, result="sha"))
    async def thread_call(function, *args, **kwargs):
        if function is pipeline.subprocess.run:
            return type("Result", (), {"stdout": b"main.py\0"})()
        if function is pipeline.detect_technologies:
            return [{"name": "Python", "evidence": ["requirements.txt:python"]}]
        if function is pipeline.parse_repository:
            return {"parsed_file_count": 1, "symbol_count": 0, "import_count": 0, "parse_error_count": 0, "symbols": [], "imports": [], "parsed_files": [{"path": "main.py", "language": "Python", "declaration_count": 0, "import_export_count": 0, "parse_status": "parsed"}]}
        if function is pipeline.detect_entry_points:
            return ["main.py"]
        if function is pipeline.detect_modules:
            return {"modules": [], "edges": [], "file_to_module": {}}
        if function is pipeline.layout_modules:
            return {}
        if function is pipeline.build_semantic_chunks:
            return []
        if function is pipeline.embed_texts:
            return []
        raise AssertionError("unexpected worker operation")
    monkeypatch.setattr(pipeline, "_thread_call", thread_call)
    monkeypatch.setattr(pipeline, "persist_chunks", lambda *_args, **_kwargs: 0)
    asyncio.run(pipeline.run_analysis(repo_id, job_id, "sha", "token"))
    with Session(engine) as db:
        job = db.get(AnalysisJob, job_id)
        repo = db.get(Repository, repo_id)
        assert job.status == "COMPLETED"
        assert job.failure_code is None and job.failure_message is None
        assert job.progress_percent == 100
        assert repo.status == AnalysisStatus.COMPLETED
        assert repo.intelligence is not None
        assert repo.intelligence.structural_data_json["parsed_files"] == [{"path": "main.py", "language": "Python", "declaration_count": 0, "import_export_count": 0, "parse_status": "parsed"}]


def test_overview_is_scoped_to_authenticated_user():
    from uuid import uuid4
    import pytest
    from app.core.errors import APIError

    engine = _database()
    with Session(engine) as db:
        current = _current_user(db)
        other = User(github_id=161803, username="other")
        db.add(other)
        db.flush()
        repo = Repository(user_id=other.id, owner="other", name="secret", status=AnalysisStatus.COMPLETED, commit_sha="sha")
        repo.intelligence = RepositoryIntelligence(structural_data_json={"symbol_count": 99})
        db.add(repo)
        db.commit()
        with pytest.raises(APIError) as denied:
            routes.intelligence(repo.id, db, current)
        assert denied.value.status_code == 404
        with pytest.raises(APIError) as missing:
            routes.intelligence(uuid4(), db, current)
        assert missing.value.status_code == 404


def test_missing_oauth_configuration_redirects_safely():
    from app.api.routes.auth import github_login

    settings = Settings(_env_file=None)
    response = asyncio.run(github_login(settings))
    assert response.status_code == 303
    assert "oauth_configuration_missing" in response.headers["location"]


def test_oauth_callback_identifies_legacy_user_schema(monkeypatch, caplog):
    """Regression for an OAuth callback against schema 0001 without the token column."""
    import logging
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    from starlette.requests import Request
    from app.api.routes import auth
    from app.core.security import create_oauth_state

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY, github_id BIGINT NOT NULL UNIQUE, username VARCHAR(255) NOT NULL, avatar_url TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"))
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    settings = Settings(_env_file=None, github_client_id="test-client", github_client_secret="test-client-secret", jwt_secret="test-signing-key-that-is-long-enough-for-hs256", frontend_url="http://localhost:3000")
    state, signed_state = create_oauth_state(settings)

    class GitHubResponse:
        is_error = False
        def json(self):
            return {"id": 7821, "login": "oauth-test-user", "avatar_url": None}

    class FakeGitHubClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def get(self, *_args, **_kwargs): return GitHubResponse()

    async def exchange(*_args, **_kwargs):
        return {"access_token": "test-only-upstream-token"}

    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **_kwargs: FakeGitHubClient())
    monkeypatch.setattr(auth, "exchange_oauth_code", exchange)
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http", "path": "/api/v1/auth/callback", "raw_path": b"/api/v1/auth/callback", "query_string": b"", "headers": [(b"cookie", f"{auth.STATE_COOKIE}={signed_state}".encode())], "server": ("localhost", 8000), "client": ("127.0.0.1", 50000), "root_path": ""}
    request = Request(scope)
    with caplog.at_level(logging.INFO, logger="app.api.routes.auth"):
        response = asyncio.run(auth.github_callback(request, code="test-code", state=state, db=db, settings=settings))
    assert response.status_code == 303
    assert "error=database_migration_required" in response.headers["location"]
    failure = [record for record in caplog.records if getattr(record, "context", {}).get("oauth_step") == "C_database_user_upsert" and getattr(record, "context", {}).get("outcome") == "failed"]
    assert len(failure) == 1
    assert failure[0].context["error_type"] == "OperationalError"
    assert "test-only-upstream-token" not in caplog.text
    assert "test-client-secret" not in caplog.text
    db.close()


def test_postgres_undefined_column_is_classified_as_migration_error():
    from sqlalchemy.exc import ProgrammingError
    from app.api.routes.auth import _is_missing_schema_error

    class UndefinedColumn(Exception):
        sqlstate = "42703"

    assert _is_missing_schema_error(ProgrammingError("statement omitted", {}, UndefinedColumn()))


def test_oauth_callback_delivers_valid_application_session(monkeypatch):
    """Verify the success redirect carries a JWT the API can authenticate."""
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker
    from fastapi.security import HTTPAuthorizationCredentials
    from starlette.requests import Request
    from app.api.routes import auth
    from app.api.dependencies import get_current_user
    from app.core.security import create_oauth_state, decode_session_token, decrypt_github_token
    from app.models import User

    engine = _database()
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    settings = Settings(_env_file=None, github_client_id="test-client", github_client_secret="test-client-secret", jwt_secret="test-signing-key-that-is-long-enough-for-hs256", frontend_url="http://localhost:3000")
    state, signed_state = create_oauth_state(settings)

    class GitHubResponse:
        is_error = False
        def json(self): return {"id": 99321, "login": "oauth-success-user", "avatar_url": "https://avatars.example/test.png"}

    class FakeGitHubClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def get(self, *_args, **_kwargs): return GitHubResponse()

    async def exchange(*_args, **_kwargs): return {"access_token": "test-only-upstream-token"}

    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **_kwargs: FakeGitHubClient())
    monkeypatch.setattr(auth, "exchange_oauth_code", exchange)
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http", "path": "/api/v1/auth/callback", "raw_path": b"/api/v1/auth/callback", "query_string": b"", "headers": [(b"cookie", f"{auth.STATE_COOKIE}={signed_state}".encode())], "server": ("localhost", 8000), "client": ("127.0.0.1", 50000), "root_path": ""}
    response = asyncio.run(auth.github_callback(Request(scope), code="test-code", state=state, db=db, settings=settings))
    assert response.status_code == 303
    assert response.headers["location"].startswith("http://localhost:3000/auth/callback#token=")
    assert auth.STATE_COOKIE in response.headers["set-cookie"]
    application_jwt = response.headers["location"].split("#token=", 1)[1]
    claims = decode_session_token(application_jwt, settings)
    user = db.scalar(select(User).where(User.github_id == 99321))
    assert claims["sub"] == str(user.id)
    assert decrypt_github_token(user.github_access_token_encrypted, settings.jwt_secret) == "test-only-upstream-token"
    authenticated = get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=application_jwt), db, settings)
    assert authenticated.user.id == user.id
    assert authenticated.github_access_token == "test-only-upstream-token"
    db.close()

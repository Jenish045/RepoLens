import json
from uuid import UUID, uuid4

import pytest

from app.core.errors import APIError
from app.engines.intelligence import modules as detector
from app.engines.processing.dagre import layout_modules
from app.models import AnalysisStatus, Module, Repository, RepositoryIntelligence, User
from app.schemas.repository_map import RepositoryMapResponse
from app.api.routes.repository_map import repository_map


def _imports(*rows):
    return [
        {"path": source, "line": index + 1, "declaration": f"from {target.replace('/', '.')} import value", "kind": "import"}
        for index, (source, target) in enumerate(rows)
    ]


def test_module_membership_is_byte_identical_across_runs_and_directory_pass_wins():
    repo_id = UUID("7483bcf9-0673-4588-9c13-3cad3a49a73e")
    paths = ["src/auth/login.py", "src/auth/session.py", "src/db/read.py", "src/db/write.py", "src/main.py"]
    structural = {"imports": _imports(
        ("src/auth/login.py", "src/auth/session"), ("src/auth/session.py", "src/auth/login"),
        ("src/db/read.py", "src/db/write"), ("src/db/write.py", "src/db/read"),
        ("src/main.py", "src/auth/login"),
    ), "symbols": []}
    first = detector.detect_modules(repo_id, "commit-1", paths, structural)
    second = detector.detect_modules(repo_id, "commit-1", reversed(paths), json.loads(json.dumps(structural)))
    assert json.dumps(first["file_to_module"], sort_keys=True, separators=(",", ":")).encode() == json.dumps(second["file_to_module"], sort_keys=True, separators=(",", ":")).encode()
    assert len(first["modules"]) == 2
    assert [item["name"] for item in first["modules"]] == ["Auth", "Db"]
    assert "src/main.py" not in first["file_to_module"]


def test_import_pass_and_cross_module_couplings_aggregate_distinct_file_pairs():
    paths = ["src/auth/a.py", "src/auth/b.py", "src/db/c.py", "src/db/d.py"]
    rows = _imports(("src/auth/a.py", "src/auth/b"), ("src/auth/a.py", "src/auth/b"), ("src/auth/b.py", "src/auth/a"), ("src/db/c.py", "src/db/d"), ("src/db/c.py", "src/db/d"), ("src/db/d.py", "src/db/c"), ("src/auth/a.py", "src/db/c"), ("src/auth/b.py", "src/db/d"))
    result = detector.detect_modules(uuid4(), "commit-2", paths, {"imports": rows, "symbols": []})
    assert len(result["modules"]) == 2
    assert result["edges"] == [{"source": result["modules"][0]["id"], "target": result["modules"][1]["id"], "weight": 2}]
    assert all("file" not in node for node in result["modules"])


def test_excluded_files_and_singletons_do_not_form_modules():
    result = detector.detect_modules(uuid4(), "commit", ["node_modules/pkg/a.js", ".venv/lib/a.py", "src/only.py"], {"imports": [], "symbols": []})
    assert result["modules"] == []
    assert result["file_to_module"] == {}


def test_import_cohesion_fallback_uses_directory_label_without_numbering():
    paths = ["src/alpha.py", "src/beta.py"]
    result = detector.detect_modules(
        uuid4(), "commit", paths,
        {"imports": _imports(("src/alpha.py", "src/beta"), ("src/beta.py", "src/alpha")), "symbols": []},
    )
    assert len(result["modules"]) == 1
    assert result["modules"][0]["name"] == "Src"
    assert "Group" not in result["modules"][0]["name"]


def test_mixed_path_fallback_names_all_represented_locations():
    name, description = detector._structural_module_name((
        "main.py", "tests/test_a.py", "tests/test_b.py", "tests/test_c.py",
    ))
    assert name == "Tests + Main"
    assert "under tests" not in description
    assert "Tests, Main" in description


def test_large_component_hub_ties_and_membership_are_deterministic(monkeypatch):
    monkeypatch.setattr(detector, "MAX_MODULE_SIZE", 3)
    paths = [f"f{i}.py" for i in range(8)]
    rows = _imports(*[(f"f{i}.py", f"f{(i + 1) % len(paths)}") for i in range(len(paths))])
    first = detector.detect_modules(UUID("7483bcf9-0673-4588-9c13-3cad3a49a73e"), "c", paths, {"imports": rows, "symbols": []})
    second = detector.detect_modules(UUID("7483bcf9-0673-4588-9c13-3cad3a49a73e"), "c", paths, {"imports": list(reversed(rows)), "symbols": []})
    assert first["file_to_module"] == second["file_to_module"]
    assert json.dumps(first["edges"], sort_keys=True) == json.dumps(second["edges"], sort_keys=True)
    assert len(first["modules"]) >= 2


def test_dagre_positions_are_repeatable_and_distinct():
    modules = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    edges = [{"source": "a", "target": "b", "weight": 2}, {"source": "b", "target": "c", "weight": 1}]
    first = layout_modules(modules, edges)
    second = layout_modules(list(reversed(modules)), list(reversed(edges)))
    assert first == second
    assert len({(p["x"], p["y"]) for p in first.values()}) == 3


def test_repository_map_requires_owned_completed_module_analysis():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool
    from app.database.base import Base
    from app.api.dependencies import AuthenticatedUser

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(github_id=824661, username="map-owner")
        stranger = User(github_id=824662, username="map-stranger")
        db.add_all([user, stranger]); db.flush()
        repo = Repository(user_id=user.id, owner="map-owner", name="repo", status=AnalysisStatus.COMPLETED, commit_sha="sha")
        repo.intelligence = RepositoryIntelligence(module_analysis_sha="sha", structural_data_json={"parsed_file_count": 3, "parsed_files": [
            {"path": "src/a.py", "language": "Python"},
            {"path": "src/b.py", "language": "Python"},
            {"path": "src/standalone.py", "language": "Python"},
        ]})
        db.add(repo); db.flush()
        one, two = uuid4(), uuid4()
        db.add_all([
            Module(id=one, repository_id=repo.id, name="One", file_paths=["src/a.py"], file_count=99, position_x=0, position_y=0, relationships_json={"outgoing": [{"target": str(two), "weight": 3}]}),
            Module(id=two, repository_id=repo.id, name="Two", file_paths=["src/b.py"], file_count=1, position_x=300, position_y=0, relationships_json={"outgoing": []}),
        ]); db.commit()
        current = AuthenticatedUser(user=user, github_access_token="unused")
        graph = repository_map(repo.id, db, current)
        assert isinstance(graph, RepositoryMapResponse)
        assert len(graph.nodes) == 2 and len(graph.edges) == 1
        assert graph.edges[0].weight == 3
        assert graph.parsed_file_count == 3
        assert graph.assigned_file_count == 2
        assert graph.standalone_file_count == 1
        assert graph.standalone_files == ["src/standalone.py"]
        assert sum(node.file_count for node in graph.nodes) == graph.assigned_file_count == 2
        assert graph.nodes[0].file_count == 1
        assert all(node.id not in {"src/a.py", "src/b.py"} for node in graph.nodes)
        with pytest.raises(APIError) as denied:
            repository_map(repo.id, db, AuthenticatedUser(user=stranger, github_access_token="unused"))
        assert denied.value.status_code == 404
    engine.dispose()


def test_map_relabels_legacy_numbered_fallback_from_module_paths():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool
    from app.api.dependencies import AuthenticatedUser
    from app.database.base import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(github_id=824664, username="map-label-owner")
        db.add(user); db.flush()
        repo = Repository(user_id=user.id, owner="map-label-owner", name="repo", status=AnalysisStatus.COMPLETED, commit_sha="sha")
        repo.intelligence = RepositoryIntelligence(module_analysis_sha="sha")
        db.add(repo); db.flush()
        db.add(Module(repository_id=repo.id, name="Import Cohesion Group 1", description="Source files grouped by deterministic import cohesion.", file_paths=["main.py", "tests/a.py", "tests/b.py", "tests/c.py"], file_count=4, position_x=0, position_y=0))
        db.commit()
        graph = repository_map(repo.id, db, AuthenticatedUser(user=user, github_access_token="unused"))
        assert graph.nodes[0].name == "Tests + Main"
        assert "Import Cohesion Group" not in graph.nodes[0].name
        assert "under tests" not in graph.nodes[0].description
    engine.dispose()


def test_overview_api_attaches_persisted_module_assignment_to_parsed_files():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool
    from app.api.dependencies import AuthenticatedUser
    from app.api.routes.repositories import intelligence
    from app.database.base import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(github_id=824665, username="parsed-inventory-owner")
        db.add(user); db.flush()
        repo = Repository(user_id=user.id, owner="parsed-inventory-owner", name="repo", status=AnalysisStatus.COMPLETED, commit_sha="sha")
        repo.intelligence = RepositoryIntelligence(module_analysis_sha="sha", structural_data_json={
            "parsed_file_count": 1,
            "parsed_files": [{"path": "src/main.py", "language": "Python", "declaration_count": 1, "import_export_count": 0, "parse_status": "parsed"}],
        })
        db.add(repo); db.flush()
        db.add(Module(repository_id=repo.id, name="Src", file_paths=["src/main.py"], file_count=1, position_x=0, position_y=0))
        db.commit()
        response = intelligence(repo.id, db, AuthenticatedUser(user=user, github_access_token="unused"))
        assert response.structural_data["parsed_files"] == [{"path": "src/main.py", "language": "Python", "declaration_count": 1, "import_export_count": 0, "parse_status": "parsed", "module_name": "Src"}]
    engine.dispose()


def test_same_sha_legacy_overview_queues_module_only_upgrade(monkeypatch):
    import asyncio
    from fastapi import BackgroundTasks, Response
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool
    from app.api.dependencies import AuthenticatedUser
    from app.api.routes import repositories as routes
    from app.core.config import Settings
    from app.database.base import Base
    from app.models import AnalysisStatus, Repository, RepositoryIntelligence, User
    from app.schemas.repositories import AnalysisTriggerRequest

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        user = User(github_id=824663, username="legacy-map-owner")
        db.add(user); db.flush()
        repo = Repository(user_id=user.id, owner="legacy-map-owner", name="repo", status=AnalysisStatus.COMPLETED, commit_sha="same-sha")
        repo.intelligence = RepositoryIntelligence(structural_data_json={"imports": [], "symbols": []})
        db.add(repo); db.commit()

        async def remote(*_args, **_kwargs):
            return {"private": False, "language": "Python", "latest_commit_sha": "same-sha", "language_bytes": {}, "owner": {"login": "legacy-map-owner"}}

        async def tree_size(*_args, **_kwargs):
            return None

        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *_args): return None

        monkeypatch.setattr(routes, "get_public_repository", remote)
        monkeypatch.setattr(routes, "validate_repository_tree_size", tree_size)
        monkeypatch.setattr(routes.httpx, "AsyncClient", lambda **_kwargs: Client())
        background, response = BackgroundTasks(), Response()
        current = AuthenticatedUser(user=user, github_access_token="test-token")
        result = asyncio.run(routes.trigger_analysis(AnalysisTriggerRequest(owner=repo.owner, name=repo.name), background, response, db, current, Settings(_env_file=None)))
        assert response.status_code == 202 and not result.cached
        assert len(background.tasks) == 1
        assert background.tasks[0].args[0] == repo.id
        assert background.tasks[0].args[-1] is True
        assert repo.status == AnalysisStatus.COMPLETED
    engine.dispose()

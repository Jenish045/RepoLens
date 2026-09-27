"""Authenticated, owner-scoped module graph endpoint."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import AuthenticatedUser, get_current_user
from app.core.errors import APIError
from app.database.session import get_session
from app.engines.intelligence.modules import _structural_module_name
from app.models import AnalysisStatus, Repository
from app.schemas.repository_map import MapEdge, MapNode, MapPosition, RepositoryMapResponse

router = APIRouter(tags=["repository-map"])


@router.get("/map/{repo_id}", response_model=RepositoryMapResponse)
def repository_map(
    repo_id: UUID,
    db: Session = Depends(get_session),
    current: AuthenticatedUser = Depends(get_current_user),
) -> RepositoryMapResponse:
    repo = db.scalar(
        select(Repository)
        .where(Repository.id == repo_id, Repository.user_id == current.user.id)
        .options(selectinload(Repository.modules), selectinload(Repository.intelligence))
    )
    if repo is None:
        raise APIError(404, "repository_not_found", "This repository could not be found.")
    intelligence = repo.intelligence
    if repo.status != AnalysisStatus.COMPLETED or intelligence is None:
        raise APIError(409, "analysis_incomplete", "Repository analysis has not completed yet.")
    if intelligence.module_analysis_sha != repo.commit_sha or repo.commit_sha is None:
        raise APIError(409, "module_analysis_incomplete", "The Repository Map is not ready for this commit yet.")
    structural = intelligence.structural_data_json if isinstance(intelligence.structural_data_json, dict) else {}
    parsed_records = structural.get("parsed_files")
    parsed_paths = {
        str(item["path"])
        for item in parsed_records
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    } if isinstance(parsed_records, list) else None
    nodes: list[MapNode] = []
    node_ids: set[UUID] = set()
    for module in sorted(repo.modules, key=lambda item: (item.name.casefold(), str(item.id))):
        if module.position_x is None or module.position_y is None:
            raise APIError(409, "module_analysis_incomplete", "The Repository Map layout is not ready yet.")
        files = module.file_paths if isinstance(module.file_paths, list) else []
        if parsed_paths is not None:
            files = [path for path in files if str(path) in parsed_paths]
        name, fallback_description = (module.name, module.description)
        if module.name.startswith("Import Cohesion Group "):
            name, fallback_description = _structural_module_name(tuple(sorted((str(path) for path in files), key=lambda value: (value.casefold(), value))))
        nodes.append(
            MapNode(
                id=module.id,
                name=name,
                category=module.category,
                description=fallback_description,
                file_count=len({str(path) for path in files}),
                position=MapPosition(x=module.position_x, y=module.position_y),
                files=sorted((str(path) for path in files), key=lambda value: (value.casefold(), value)),
                exported_symbols=module.exported_symbols_json or [],
                technology_dependencies=module.technology_dependencies_json or [],
            )
        )
        node_ids.add(module.id)
    edge_weights: dict[tuple[UUID, UUID], int] = {}
    for module in repo.modules:
        relationships = module.relationships_json if isinstance(module.relationships_json, dict) else {}
        outgoing = relationships.get("outgoing", [])
        for edge in outgoing if isinstance(outgoing, list) else []:
            try:
                target = UUID(str(edge["target"]))
                weight = int(edge["weight"])
            except (KeyError, TypeError, ValueError):
                continue
            if module.id in node_ids and target in node_ids and target != module.id and weight > 0:
                edge_weights[(module.id, target)] = edge_weights.get((module.id, target), 0) + weight
    edges = [
        MapEdge(id=f"{source}:{target}", source=source, target=target, weight=weight)
        for (source, target), weight in sorted(edge_weights.items(), key=lambda item: (str(item[0][0]), str(item[0][1])))
    ]
    if parsed_paths is not None:
        assigned_paths = {
            str(path)
            for module in repo.modules
            for path in (module.file_paths if isinstance(module.file_paths, list) else [])
        }
        standalone_files = sorted(parsed_paths - assigned_paths, key=lambda value: (value.casefold(), value))
        assigned_count = len(parsed_paths & assigned_paths)
        return RepositoryMapResponse(
            repository_id=repo.id,
            commit_sha=repo.commit_sha,
            nodes=nodes,
            edges=edges,
            parsed_file_count=len(parsed_paths),
            assigned_file_count=assigned_count,
            standalone_file_count=len(standalone_files),
            standalone_files=standalone_files,
        )
    return RepositoryMapResponse(repository_id=repo.id, commit_sha=repo.commit_sha, nodes=nodes, edges=edges)

"""User-scoped public repository selection, analysis, and Overview endpoints."""

import re
from datetime import datetime
from uuid import UUID

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import AuthenticatedUser, get_current_user
from app.api.services.github import get_public_repository, list_public_repositories, validate_repository_tree_size
from app.api.services.inventory import parse_saved_public_commit
from app.core.config import Settings, get_settings
from app.core.errors import APIError
from app.database.session import get_session
from app.engines.processing.languages import is_supported_language_name
from app.engines.processing.pipeline import run_analysis
from app.engines.intelligence.modules import _structural_module_name
from app.models import AnalysisJob, AnalysisStatus, Module, Repository, RepositoryChunk
from app.schemas.repositories import (
    AnalysisStatusResponse,
    AnalysisTriggerRequest,
    AnalysisTriggerResponse,
    IntelligenceRepository,
    IntelligenceResponse,
    ParsedFileInventoryResponse,
    ParsedFileRecord,
    RepositoryCard,
    RepositoryListResponse,
)

router = APIRouter(tags=["repositories", "analysis"])
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
STAGE_LABELS = {0: "QUEUED", 1: "Cloning repository", 2: "Detecting technologies", 3: "Parsing source code", 4: "Extracting metadata", 5: "Detecting modules", 6: "Building intelligence", 7: "Generating insights", 8: "Preparing dashboard"}
DEFERRED = ["Generating insights"]


def _inventory_response(repo_id: UUID, commit_sha: str, rows: list[dict], modules: list[Module], *, backfilled: bool) -> ParsedFileInventoryResponse:
    module_by_path = {}
    for module in modules:
        paths = module.file_paths if isinstance(module.file_paths, list) else []
        name = module.name
        if name.startswith("Import Cohesion Group "):
            name, _ = _structural_module_name(tuple(sorted((str(path) for path in paths), key=lambda value: (value.casefold(), value))))
        for path in paths:
            module_by_path[str(path)] = name
    parsed_files = [
        ParsedFileRecord(**row, module_name=module_by_path.get(row["path"]))
        for row in rows
    ]
    return ParsedFileInventoryResponse(repository_id=repo_id, commit_sha=commit_sha, parsed_file_count=len(parsed_files), parsed_files=parsed_files, backfilled=backfilled)


def _repo_card(item: dict) -> RepositoryCard:
    owner = item.get("owner") or {}
    return RepositoryCard(
        id=item["id"], name=item["name"], owner=owner.get("login", ""), full_name=item.get("full_name", ""),
        description=item.get("description"), primary_language=item.get("language"), size_kb=item.get("size", 0),
        updated_at=item.get("updated_at"), default_branch=item.get("default_branch"), private=False,
    )


@router.get("/repositories", response_model=RepositoryListResponse)
async def repositories(
    page: int = Query(1, ge=1), per_page: int = Query(30, ge=1, le=100),
    current: AuthenticatedUser = Depends(get_current_user),
):
    async with httpx.AsyncClient(timeout=20) as client:
        items, more = await list_public_repositories(client, current.github_access_token, page=page, per_page=per_page)
    return RepositoryListResponse(data=[_repo_card(item) for item in items], meta={"page": page, "per_page": per_page, "has_more": more})


@router.get("/repositories/analyzed")
def analyzed_repositories(db: Session = Depends(get_session), current: AuthenticatedUser = Depends(get_current_user)):
    rows = db.scalars(select(Repository).where(Repository.user_id == current.user.id, Repository.status == AnalysisStatus.COMPLETED).order_by(Repository.owner, Repository.name))
    return [{"id": row.id, "owner": row.owner, "name": row.name, "commit_sha": row.commit_sha} for row in rows]


@router.post("/analysis/trigger", response_model=AnalysisTriggerResponse)
async def trigger_analysis(
    request: AnalysisTriggerRequest,
    background: BackgroundTasks,
    response: Response,
    db: Session = Depends(get_session),
    current: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    if not NAME_PATTERN.fullmatch(request.owner) or not NAME_PATTERN.fullmatch(request.name) or request.owner in {".", ".."} or request.name in {".", ".."}:
        raise APIError(422, "invalid_repository_name", "Enter a valid GitHub repository owner and name.")
    async with httpx.AsyncClient(timeout=25) as client:
        remote = await get_public_repository(client, current.github_access_token, request.owner, request.name)
    if not is_supported_language_name(remote.get("language")):
        raise APIError(422, "unsupported_repository_language", "RepoLens currently analyzes repositories whose primary language is Python, Java, JavaScript, or TypeScript.")
    sha = remote["latest_commit_sha"]
    repo = db.scalar(select(Repository).where(Repository.user_id == current.user.id, Repository.owner == request.owner, Repository.name == request.name))
    has_overview = bool(repo and repo.status == AnalysisStatus.COMPLETED and repo.intelligence is not None)
    modules_current = bool(has_overview and repo.intelligence.module_analysis_sha == sha)
    semantic_current = bool(
        has_overview
        and isinstance(repo.intelligence.structural_data_json, dict)
        and repo.intelligence.structural_data_json.get("semantic_analysis_sha") == sha
    )
    if semantic_current:
        expected_chunks = repo.intelligence.structural_data_json.get("semantic_chunk_count")
        persisted_chunks = db.scalar(select(func.count()).select_from(RepositoryChunk).where(RepositoryChunk.repository_id == repo.id, RepositoryChunk.commit_sha == sha))
        semantic_current = expected_chunks is not None and expected_chunks == persisted_chunks
    if repo and repo.commit_sha == sha and modules_current and semantic_current:
        return AnalysisTriggerResponse(cached=True, repository_id=repo.id, commit_sha=sha, analyzed_at=repo.analyzed_at)
    pending = db.scalar(select(AnalysisJob).where(AnalysisJob.user_id == current.user.id, AnalysisJob.repository_id == repo.id if repo else False, AnalysisJob.commit_sha == sha, AnalysisJob.status.in_(["QUEUED", "RUNNING"]))) if repo else None
    if pending:
        response.status_code = 202
        return AnalysisTriggerResponse(cached=False, commit_sha=sha, analysis_id=pending.id, stage=pending.stage)
    async with httpx.AsyncClient(timeout=25) as client:
        await validate_repository_tree_size(client, current.github_access_token, request.owner, request.name, sha, settings.max_repository_files)
    if repo is None:
        repo = Repository(user_id=current.user.id, name=request.name, owner=request.owner)
        db.add(repo)
    module_only = bool(repo.commit_sha == sha and has_overview and not modules_current)
    repo.description = remote.get("description")
    repo.default_branch = remote.get("default_branch")
    repo.primary_language = remote.get("language")
    repo.size_kb = remote.get("size", 0)
    repo.remote_updated_at = datetime.fromisoformat(remote["updated_at"].replace("Z", "+00:00")).replace(tzinfo=None) if remote.get("updated_at") else None
    repo.language_breakdown_json = remote.get("language_bytes", {})
    repo.commit_sha = sha
    repo.status = AnalysisStatus.COMPLETED if module_only else AnalysisStatus.QUEUED
    db.flush()
    job = AnalysisJob(user_id=current.user.id, repository_id=repo.id, commit_sha=sha, status="QUEUED", stage="QUEUED", stage_index=0, progress_percent=0)
    db.add(job)
    db.commit()
    background.add_task(run_analysis, repo.id, job.id, sha, current.github_access_token, module_only)
    response.status_code = 202
    return AnalysisTriggerResponse(cached=False, commit_sha=sha, analysis_id=job.id, stage="QUEUED")


@router.get("/analysis/{analysis_id}/status", response_model=AnalysisStatusResponse)
def analysis_status(analysis_id: UUID, db: Session = Depends(get_session), current: AuthenticatedUser = Depends(get_current_user)):
    job = db.scalar(select(AnalysisJob).where(AnalysisJob.id == analysis_id, AnalysisJob.user_id == current.user.id))
    if not job:
        raise APIError(404, "analysis_not_found", "This analysis could not be found.")
    done = [STAGE_LABELS[i] for i in (1, 2, 3, 4, 5, 6, 8) if job.stage_index > i or (job.status == "COMPLETED" and job.stage_index >= i)]
    failure = {"code": job.failure_code, "message": job.failure_message} if job.failure_code else None
    return AnalysisStatusResponse(analysis_id=job.id, repository_id=job.repository_id, status=job.status, stage=STAGE_LABELS.get(job.stage_index, "QUEUED"), stage_index=job.stage_index, progress=job.progress_percent, completed_stages=done, deferred_stages=DEFERRED, failure=failure)


@router.get("/intelligence/{repo_id}", response_model=IntelligenceResponse)
def intelligence(repo_id: UUID, db: Session = Depends(get_session), current: AuthenticatedUser = Depends(get_current_user)):
    repo = db.scalar(select(Repository).where(Repository.id == repo_id, Repository.user_id == current.user.id).options(selectinload(Repository.modules)))
    if not repo:
        raise APIError(404, "repository_not_found", "This repository could not be found.")
    if repo.status != AnalysisStatus.COMPLETED or repo.intelligence is None:
        raise APIError(409, "intelligence_unavailable", "Repository overview is not ready yet.")
    module_count = len(repo.modules) if repo.intelligence.module_analysis_sha == repo.commit_sha else None
    info = IntelligenceRepository(id=repo.id, name=repo.name, owner=repo.owner, description=repo.description, default_branch=repo.default_branch, primary_language=repo.primary_language, language_breakdown=repo.language_breakdown_json, file_count=repo.file_count, size_kb=repo.size_kb, technologies=[item["name"] for item in (repo.technologies_json or []) if isinstance(item, dict) and "name" in item], module_count=module_count, entry_points=repo.entry_points_json or [], commit_sha=repo.commit_sha, analyzed_at=repo.analyzed_at, analysis_status=repo.status.value)
    structural = repo.intelligence.structural_data_json
    if isinstance(structural, dict):
        structural = dict(structural)
        parsed_files = structural.get("parsed_files")
        if isinstance(parsed_files, list):
            module_by_path = {
                str(path): module.name
                for module in repo.modules
                for path in (module.file_paths if isinstance(module.file_paths, list) else [])
            }
            structural["parsed_files"] = [
                {**item, "module_name": module_by_path.get(item.get("path"))}
                for item in parsed_files if isinstance(item, dict) and isinstance(item.get("path"), str)
            ]
    return IntelligenceResponse(repository=info, summary=repo.intelligence.summary, architecture_summary=repo.intelligence.architecture_summary, structural_data=structural)


@router.post("/analysis/{repo_id}/parsed-files/backfill", response_model=ParsedFileInventoryResponse)
async def backfill_parsed_file_inventory(repo_id: UUID, db: Session = Depends(get_session), current: AuthenticatedUser = Depends(get_current_user), settings: Settings = Depends(get_settings)):
    repo = db.scalar(select(Repository).where(Repository.id == repo_id, Repository.user_id == current.user.id).options(selectinload(Repository.intelligence), selectinload(Repository.modules)))
    if not repo:
        raise APIError(404, "repository_not_found", "This repository could not be found.")
    intelligence = repo.intelligence
    data = intelligence.structural_data_json if intelligence else None
    if repo.status != AnalysisStatus.COMPLETED or not intelligence or not isinstance(data, dict) or not repo.commit_sha or intelligence.module_analysis_sha != repo.commit_sha:
        raise APIError(409, "inventory_unavailable", "A completed analysis for the saved commit is required.")
    existing = data.get("parsed_files")
    if isinstance(existing, list) and existing:
        return _inventory_response(repo.id, repo.commit_sha, existing, repo.modules, backfilled=False)
    pinned_sha = repo.commit_sha
    expected = (data.get("parsed_file_count"), data.get("symbol_count"), data.get("import_count"), data.get("parse_error_count"))
    owner, name = repo.owner, repo.name
    db.rollback()
    fresh = await parse_saved_public_commit(owner, name, pinned_sha, max_files=settings.max_repository_files)
    records = fresh.get("parsed_files", [])
    actual = (fresh.get("parsed_file_count"), fresh.get("symbol_count"), fresh.get("import_count"), fresh.get("parse_error_count"))
    if actual != expected:
        raise APIError(409, "inventory_backfill_mismatch", "The saved commit no longer reproduces the stored analysis totals; inventory was not changed.")
    repo = db.scalar(select(Repository).where(Repository.id == repo_id, Repository.user_id == current.user.id).options(selectinload(Repository.intelligence), selectinload(Repository.modules)).with_for_update())
    if not repo or repo.commit_sha != pinned_sha or repo.status != AnalysisStatus.COMPLETED or not repo.intelligence or repo.intelligence.module_analysis_sha != pinned_sha:
        raise APIError(409, "analysis_changed", "The saved analysis changed while inventory was being verified.")
    data = repo.intelligence.structural_data_json
    if not isinstance(data, dict):
        raise APIError(409, "inventory_unavailable", "The saved analysis has no structural metadata.")
    if isinstance(data.get("parsed_files"), list) and data["parsed_files"]:
        return _inventory_response(repo.id, pinned_sha, data["parsed_files"], repo.modules, backfilled=False)
    repo.intelligence.structural_data_json = {**data, "parsed_files": records}
    db.commit()
    return _inventory_response(repo.id, pinned_sha, records, repo.modules, backfilled=True)

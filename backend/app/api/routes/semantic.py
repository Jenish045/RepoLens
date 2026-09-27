"""Repository-scoped semantic evidence retrieval."""

import logging
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import AuthenticatedUser, get_current_user
from app.core.errors import APIError
from app.database.session import get_session
from app.engines.intelligence.semantic import search_chunks
from app.models import AnalysisStatus, Repository, RepositoryChunk
from app.schemas.semantic import SemanticSearchRequest, SemanticSearchResponse

router = APIRouter(tags=["semantic-explorer"])
logger = logging.getLogger(__name__)


@router.post("/search/semantic", response_model=SemanticSearchResponse)
def semantic_search(
    request: SemanticSearchRequest,
    db: Session = Depends(get_session),
    current: AuthenticatedUser = Depends(get_current_user),
) -> SemanticSearchResponse:
    repo = db.scalar(select(Repository).where(
        Repository.id == request.repository_id,
        Repository.user_id == current.user.id,
    ))
    if repo is None:
        raise APIError(404, "repository_not_found", "This repository could not be found.")
    if repo.status != AnalysisStatus.COMPLETED or not repo.commit_sha:
        raise APIError(409, "semantic_search_unavailable", "Repository analysis has not completed yet.")
    intelligence = repo.intelligence
    structural = intelligence.structural_data_json if intelligence and isinstance(intelligence.structural_data_json, dict) else {}
    if structural.get("semantic_analysis_sha") != repo.commit_sha:
        raise APIError(409, "semantic_search_unavailable", "Semantic data is not available for this saved analysis. Re-analyze the repository to build it.")
    expected_chunks = structural.get("semantic_chunk_count")
    persisted_chunks = db.scalar(select(func.count()).select_from(RepositoryChunk).where(
        RepositoryChunk.repository_id == repo.id,
        RepositoryChunk.commit_sha == repo.commit_sha,
    ))
    if expected_chunks is None or expected_chunks != persisted_chunks:
        raise APIError(409, "semantic_search_unavailable", "Semantic data is incomplete for this saved analysis. Re-analyze the repository to rebuild it.")
    try:
        results = search_chunks(db, repo.id, repo.commit_sha, request.query, request.limit)
    except Exception as exc:
        logger.exception("Semantic retrieval failed", extra={"context": {"repository_id": str(repo.id)}})
        raise APIError(503, "semantic_search_unavailable", "Semantic search is temporarily unavailable.") from exc
    return SemanticSearchResponse(repository_id=repo.id, commit_sha=repo.commit_sha, query=request.query, results=results)

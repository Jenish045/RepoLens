"""Public repository and Overview response contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RepositoryCard(BaseModel):
    id: int
    name: str
    owner: str
    full_name: str
    description: str | None
    primary_language: str | None
    size_kb: int
    updated_at: datetime | None
    default_branch: str | None
    private: bool = False


class RepositoryListResponse(BaseModel):
    data: list[RepositoryCard]
    meta: dict[str, int | bool]


class AnalysisTriggerRequest(BaseModel):
    owner: str
    name: str


class AnalysisTriggerResponse(BaseModel):
    cached: bool
    repository_id: UUID | None = None
    commit_sha: str
    analyzed_at: datetime | None = None
    analysis_id: UUID | None = None
    stage: str | None = None


class AnalysisStatusResponse(BaseModel):
    analysis_id: UUID
    repository_id: UUID
    status: str
    stage: str
    stage_index: int
    progress: int
    completed_stages: list[str]
    deferred_stages: list[str]
    failure: dict[str, str] | None = None
    model_config = ConfigDict(from_attributes=True)


class IntelligenceRepository(BaseModel):
    id: UUID
    name: str
    owner: str
    description: str | None
    default_branch: str | None
    primary_language: str | None
    language_breakdown: dict[str, int] | None
    file_count: int | None
    size_kb: int | None
    technologies: list[str]
    module_count: int | None
    entry_points: list[str]
    commit_sha: str | None
    analyzed_at: datetime | None
    analysis_status: str


class IntelligenceResponse(BaseModel):
    repository: IntelligenceRepository
    summary: str | None
    architecture_summary: str | None
    structural_data: dict | list | None


class ParsedFileRecord(BaseModel):
    path: str
    language: str
    declaration_count: int
    import_export_count: int
    parse_status: Literal["parsed", "parsed_with_errors"]
    module_name: str | None = None


class ParsedFileInventoryResponse(BaseModel):
    repository_id: UUID
    commit_sha: str
    parsed_file_count: int
    parsed_files: list[ParsedFileRecord]
    backfilled: bool

"""Semantic Explorer API contracts."""

from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SemanticSearchRequest(BaseModel):
    repository_id: UUID
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def query_must_have_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Query must contain non-whitespace text")
        return value


class SemanticSearchResult(BaseModel):
    chunk_id: UUID
    file_path: str
    module_id: UUID | None
    module_name: str | None
    start_line: int
    end_line: int
    score: float
    text: str
    symbol_name: str | None


class SemanticSearchResponse(BaseModel):
    repository_id: UUID
    commit_sha: str
    query: str
    results: list[SemanticSearchResult]

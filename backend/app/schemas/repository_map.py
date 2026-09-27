"""Repository Map response contracts."""

from uuid import UUID

from pydantic import BaseModel


class MapPosition(BaseModel):
    x: float
    y: float


class MapNode(BaseModel):
    id: UUID
    name: str
    category: str | None
    description: str | None
    file_count: int
    position: MapPosition
    files: list[str]
    exported_symbols: list[str]
    technology_dependencies: list[str]


class MapEdge(BaseModel):
    id: str
    source: UUID
    target: UUID
    weight: int


class RepositoryMapResponse(BaseModel):
    repository_id: UUID
    commit_sha: str
    nodes: list[MapNode]
    edges: list[MapEdge]
    parsed_file_count: int | None = None
    assigned_file_count: int | None = None
    standalone_file_count: int | None = None
    standalone_files: list[str] | None = None

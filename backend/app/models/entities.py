"""Foundation ORM entities aligned to the specification's Appendix E schema."""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    REAL,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

JSONType = JSON().with_variant(JSONB, "postgresql")
VectorType = JSON().with_variant(ARRAY(REAL()), "postgresql")


class AnalysisStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ReportFormat(str, Enum):
    PDF = "PDF"
    MARKDOWN = "MARKDOWN"


def uuid_column() -> Mapped[UUID]:
    return mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("idx_users_github_id", "github_id"),)

    id: Mapped[UUID] = uuid_column()
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    repositories: Mapped[list["Repository"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("user_id", "owner", "name", name="uq_repositories_user_owner_name"),
        Index("idx_repo_sha", "commit_sha"),
        Index("idx_repo_status", "status"),
    )

    id: Mapped[UUID] = uuid_column()
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    primary_language: Mapped[str | None] = mapped_column(String(50))
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[AnalysisStatus] = mapped_column(
        SAEnum(AnalysisStatus, name="analysis_status", native_enum=True),
        nullable=False,
        default=AnalysisStatus.QUEUED,
        server_default=AnalysisStatus.QUEUED.value,
    )
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime)
    user: Mapped[User] = relationship(back_populates="repositories")
    intelligence: Mapped["RepositoryIntelligence | None"] = relationship(back_populates="repository", cascade="all, delete-orphan", uselist=False)
    modules: Mapped[list["Module"]] = relationship(back_populates="repository", cascade="all, delete-orphan")
    chunks: Mapped[list["RepositoryChunk"]] = relationship(back_populates="repository", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship(back_populates="repository", cascade="all, delete-orphan")


class RepositoryIntelligence(Base):
    __tablename__ = "repository_intelligence"

    id: Mapped[UUID] = uuid_column()
    repository_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), unique=True, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    tech_stack_json: Mapped[dict | list | None] = mapped_column(JSONType)
    architecture_summary: Mapped[str | None] = mapped_column(Text)
    learning_path_json: Mapped[dict | list | None] = mapped_column(JSONType)
    insights_json: Mapped[dict | list | None] = mapped_column(JSONType)
    repository: Mapped[Repository] = relationship(back_populates="intelligence")


class Module(Base):
    __tablename__ = "modules"
    __table_args__ = (Index("idx_modules_repo", "repository_id"),)

    id: Mapped[UUID] = uuid_column()
    repository_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    file_paths: Mapped[dict | list] = mapped_column(JSONType, nullable=False)
    relationships_json: Mapped[dict | list | None] = mapped_column(JSONType)
    repository: Mapped[Repository] = relationship(back_populates="modules")


class RepositoryChunk(Base):
    __tablename__ = "repository_chunks"
    __table_args__ = (Index("idx_chunks_repo", "repository_id"),)

    id: Mapped[UUID] = uuid_column()
    repository_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    chunk_content: Mapped[str] = mapped_column(Text, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_vector: Mapped[list[float]] = mapped_column(VectorType, nullable=False, comment="384 L2-normalized floats")
    repository: Mapped[Repository] = relationship(back_populates="chunks")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[UUID] = uuid_column()
    repository_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    report_type: Mapped[ReportFormat] = mapped_column(
        SAEnum(ReportFormat, name="report_format", native_enum=True), nullable=False
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    repository: Mapped[Repository] = relationship(back_populates="reports")

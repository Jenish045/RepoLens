"""Create the RepoLens foundation schema from specification Appendix E."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    analysis_status = postgresql.ENUM(
        "QUEUED", "PROCESSING", "COMPLETED", "FAILED", name="analysis_status", create_type=False
    )
    report_format = postgresql.ENUM("PDF", "MARKDOWN", name="report_format", create_type=False)
    postgresql.ENUM("QUEUED", "PROCESSING", "COMPLETED", "FAILED", name="analysis_status").create(
        op.get_bind(), checkfirst=True
    )
    postgresql.ENUM("PDF", "MARKDOWN", name="report_format").create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("avatar_url", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_users_github_id", "users", ["github_id"])

    op.create_table(
        "repositories",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("primary_language", sa.String(50)),
        sa.Column("commit_sha", sa.String(64)),
        sa.Column("status", analysis_status, server_default="QUEUED", nullable=False),
        sa.Column("analyzed_at", sa.DateTime()),
        sa.UniqueConstraint("user_id", "owner", "name", name="uq_repositories_user_owner_name"),
    )
    op.create_index("idx_repo_sha", "repositories", ["commit_sha"])
    op.create_index("idx_repo_status", "repositories", ["status"])

    op.create_table(
        "repository_intelligence",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("summary", sa.Text()),
        sa.Column("tech_stack_json", postgresql.JSONB()),
        sa.Column("architecture_summary", sa.Text()),
        sa.Column("learning_path_json", postgresql.JSONB()),
        sa.Column("insights_json", postgresql.JSONB()),
    )

    op.create_table(
        "modules",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(100)),
        sa.Column("file_paths", postgresql.JSONB(), nullable=False),
        sa.Column("relationships_json", postgresql.JSONB()),
    )
    op.create_index("idx_modules_repo", "modules", ["repository_id"])

    op.create_table(
        "repository_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("chunk_content", sa.Text(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("embedding_vector", postgresql.ARRAY(sa.REAL()), nullable=False, comment="384 L2-normalized floats"),
    )
    op.create_index("idx_chunks_repo", "repository_chunks", ["repository_id"])

    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_type", report_format, nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("reports")
    op.drop_index("idx_chunks_repo", table_name="repository_chunks")
    op.drop_table("repository_chunks")
    op.drop_index("idx_modules_repo", table_name="modules")
    op.drop_table("modules")
    op.drop_table("repository_intelligence")
    op.drop_index("idx_repo_status", table_name="repositories")
    op.drop_index("idx_repo_sha", table_name="repositories")
    op.drop_table("repositories")
    op.drop_index("idx_users_github_id", table_name="users")
    op.drop_table("users")
    postgresql.ENUM(name="report_format").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="analysis_status").drop(op.get_bind(), checkfirst=True)

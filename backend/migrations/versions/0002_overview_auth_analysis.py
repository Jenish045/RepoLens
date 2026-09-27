"""Persist OAuth credentials, Overview metadata, and analysis job status."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_overview_auth_analysis"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("github_access_token_encrypted", sa.Text(), nullable=True))

    op.add_column("repositories", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("repositories", sa.Column("default_branch", sa.String(255), nullable=True))
    op.add_column("repositories", sa.Column("size_kb", sa.Integer(), nullable=True))
    op.add_column("repositories", sa.Column("remote_updated_at", sa.DateTime(), nullable=True))
    op.add_column("repositories", sa.Column("language_breakdown_json", postgresql.JSONB(), nullable=True))
    op.add_column("repositories", sa.Column("file_count", sa.Integer(), nullable=True))
    op.add_column("repositories", sa.Column("technologies_json", postgresql.JSONB(), nullable=True))
    op.add_column("repositories", sa.Column("entry_points_json", postgresql.JSONB(), nullable=True))
    op.add_column("repository_intelligence", sa.Column("structural_data_json", postgresql.JSONB(), nullable=True))

    op.create_table(
        "analysis_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("commit_sha", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="QUEUED", nullable=False),
        sa.Column("stage", sa.String(40), server_default="QUEUED", nullable=False),
        sa.Column("stage_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("progress_percent", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failure_code", sa.String(80), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_analysis_jobs_user", "analysis_jobs", ["user_id"])
    op.create_index("idx_analysis_jobs_repository", "analysis_jobs", ["repository_id"])


def downgrade() -> None:
    op.drop_index("idx_analysis_jobs_repository", table_name="analysis_jobs")
    op.drop_index("idx_analysis_jobs_user", table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
    op.drop_column("repository_intelligence", "structural_data_json")
    for column in (
        "entry_points_json",
        "technologies_json",
        "file_count",
        "language_breakdown_json",
        "remote_updated_at",
        "size_kb",
        "default_branch",
        "description",
    ):
        op.drop_column("repositories", column)
    op.drop_column("users", "github_access_token_encrypted")

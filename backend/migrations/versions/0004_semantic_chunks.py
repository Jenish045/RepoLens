"""Add commit and structural provenance for semantic chunks."""

from alembic import op
import sqlalchemy as sa

revision = "0004_semantic_chunks"
down_revision = "0003_repository_map"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repository_chunks", sa.Column("commit_sha", sa.String(64), nullable=False, server_default=""))
    op.add_column("repository_chunks", sa.Column("module_id", sa.Uuid(), sa.ForeignKey("modules.id", ondelete="SET NULL"), nullable=True))
    op.add_column("repository_chunks", sa.Column("module_name", sa.String(255), nullable=True))
    op.add_column("repository_chunks", sa.Column("symbol_name", sa.String(512), nullable=True))
    op.add_column("repository_chunks", sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("idx_chunks_repo_commit", "repository_chunks", ["repository_id", "commit_sha"])


def downgrade() -> None:
    op.drop_index("idx_chunks_repo_commit", table_name="repository_chunks")
    op.drop_column("repository_chunks", "chunk_index")
    op.drop_column("repository_chunks", "symbol_name")
    op.drop_column("repository_chunks", "module_name")
    op.drop_column("repository_chunks", "module_id")
    op.drop_column("repository_chunks", "commit_sha")

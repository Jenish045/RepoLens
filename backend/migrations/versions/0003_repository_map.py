"""Persist module metadata, module-completion marker, and Dagre positions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_repository_map"
down_revision = "0002_overview_auth_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repository_intelligence", sa.Column("module_analysis_sha", sa.String(64), nullable=True))
    op.add_column("modules", sa.Column("file_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("modules", sa.Column("exported_symbols_json", postgresql.JSONB(), nullable=True))
    op.add_column("modules", sa.Column("technology_dependencies_json", postgresql.JSONB(), nullable=True))
    op.add_column("modules", sa.Column("position_x", sa.Float(), nullable=True))
    op.add_column("modules", sa.Column("position_y", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("modules", "position_y")
    op.drop_column("modules", "position_x")
    op.drop_column("modules", "technology_dependencies_json")
    op.drop_column("modules", "exported_symbols_json")
    op.drop_column("modules", "file_count")
    op.drop_column("repository_intelligence", "module_analysis_sha")

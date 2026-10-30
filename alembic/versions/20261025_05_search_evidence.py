"""Filtros y deduplicación de búsquedas observadas por el catálogo.

Revision ID: 20261025_05
Revises: 20261025_04
"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_05"
down_revision = "20261025_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("search_logs", sa.Column("dedupe_key", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_search_logs_dedupe_key", "search_logs", ["dedupe_key"])
    op.add_column("search_logs", sa.Column("search_filters", sa.JSON(), nullable=False, server_default="{}"))
    op.alter_column("search_logs", "search_filters", server_default=None)


def downgrade() -> None:
    op.drop_column("search_logs", "search_filters")
    op.drop_constraint("uq_search_logs_dedupe_key", "search_logs", type_="unique")
    op.drop_column("search_logs", "dedupe_key")

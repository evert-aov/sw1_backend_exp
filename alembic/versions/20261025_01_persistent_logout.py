"""Revocación JWT persistente compartida entre procesos.

Revision ID: 20261025_01
Revises: 7cfb6d153b7e
"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_01"
down_revision = "7cfb6d153b7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Crea huellas de tokens revocados sin almacenar credenciales de sesión."""
    op.create_table(
        "revoked_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_revoked_tokens_expires_at", "revoked_tokens", ["expires_at"])


def downgrade() -> None:
    """Elimina el registro de revocaciones durante una reversión explícita."""
    op.drop_index("ix_revoked_tokens_expires_at", table_name="revoked_tokens")
    op.drop_table("revoked_tokens")

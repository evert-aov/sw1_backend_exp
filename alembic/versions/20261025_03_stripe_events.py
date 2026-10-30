"""Recepción idempotente de webhooks de pago.

Revision ID: 20261025_03
Revises: 20261025_02
"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_03"
down_revision = "20261025_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Guarda el identificador único y el resultado del evento procesado."""
    op.create_table(
        "stripe_events",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("object_id", sa.String(255), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Revierte únicamente el registro de eventos de esta revisión."""
    op.drop_table("stripe_events")

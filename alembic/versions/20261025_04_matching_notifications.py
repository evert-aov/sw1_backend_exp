"""Preferencias de matching y avisos persistentes por generación de quórum.

Revision ID: 20261025_04
Revises: 20261025_03
"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_04"
down_revision = "20261025_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("experiences", sa.Column("quorum_generation", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("experiences", "quorum_generation", server_default=None)
    op.add_column("matching_members", sa.Column("preferences", sa.JSON(), nullable=False, server_default="{}"))
    op.alter_column("matching_members", "preferences", server_default=None)
    op.create_unique_constraint("uq_matching_member_group_user", "matching_members", ["matching_group_id", "user_id"])
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", sa.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("experience_id", sa.UUID(as_uuid=False), sa.ForeignKey("experiences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dedupe_key", sa.String(200), unique=True, nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_constraint("uq_matching_member_group_user", "matching_members", type_="unique")
    op.drop_column("matching_members", "preferences")
    op.drop_column("experiences", "quorum_generation")

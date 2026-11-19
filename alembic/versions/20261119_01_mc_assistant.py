"""Asistente de Maestro de Ceremonias: catálogo de dinámicas, alertas y dispositivos push.

Revision ID: 20261119_01
Revises: 20261025_05
"""

import sqlalchemy as sa
from alembic import op

revision = "20261119_01"
down_revision = "20261025_05"
branch_labels = None
depends_on = None

DYNAMIC_TYPES = ("AUDIENCE_QUESTION", "ACTIVE_BREAK", "SHORT_BREAK")
DYNAMIC_MODALITIES = ("ANY", "IN_PERSON", "VIRTUAL")
ALERT_TRIGGERS = ("SUSTAINED_INATTENTION", "MANUAL_REQUEST")
ALERT_STATUSES = ("ACTIVE", "APPLIED", "DISMISSED", "EXPIRED")


def upgrade() -> None:
    """Crea las tablas de HU-18/HU-19 sin modificar tablas existentes."""
    op.create_table(
        "mc_dynamics",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column(
            "dynamic_type", sa.Enum(*DYNAMIC_TYPES, name="mcdynamictypeenum"), nullable=False
        ),
        sa.Column(
            "modality", sa.Enum(*DYNAMIC_MODALITIES, name="mcdynamicmodalityenum"), nullable=False
        ),
        sa.Column("intensity", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("title_es", sa.String(120), nullable=False),
        sa.Column("title_en", sa.String(120), nullable=False),
        sa.Column("instructions_es", sa.Text(), nullable=False),
        sa.Column("instructions_en", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("code", name="uq_mc_dynamics_code"),
    )
    op.create_index("ix_mc_dynamics_id", "mc_dynamics", ["id"])

    op.create_table(
        "mc_alerts",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "live_session_id",
            sa.UUID(as_uuid=False),
            sa.ForeignKey("live_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dynamic_id",
            sa.UUID(as_uuid=False),
            sa.ForeignKey("mc_dynamics.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "suggestion_id",
            sa.UUID(as_uuid=False),
            sa.ForeignKey("live_suggestions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("trigger", sa.Enum(*ALERT_TRIGGERS, name="mcalerttriggerenum"), nullable=False),
        sa.Column("status", sa.Enum(*ALERT_STATUSES, name="mcalertstatusenum"), nullable=False),
        sa.Column("average_attention", sa.Float(), nullable=True),
        sa.Column("low_attention_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("break_ends_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_mc_alerts_id", "mc_alerts", ["id"])
    op.create_index("ix_mc_alerts_live_session_id", "mc_alerts", ["live_session_id"])

    op.create_table(
        "monitor_push_devices",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "live_session_id",
            sa.UUID(as_uuid=False),
            sa.ForeignKey("live_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fcm_token", sa.String(512), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("language", sa.String(5), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("fcm_token", name="uq_monitor_push_devices_fcm_token"),
    )
    op.create_index("ix_monitor_push_devices_id", "monitor_push_devices", ["id"])
    op.create_index(
        "ix_monitor_push_devices_live_session_id", "monitor_push_devices", ["live_session_id"]
    )


def downgrade() -> None:
    """Elimina las tablas y tipos del Asistente MC durante una reversión explícita."""
    op.drop_index("ix_monitor_push_devices_live_session_id", table_name="monitor_push_devices")
    op.drop_index("ix_monitor_push_devices_id", table_name="monitor_push_devices")
    op.drop_table("monitor_push_devices")
    op.drop_index("ix_mc_alerts_live_session_id", table_name="mc_alerts")
    op.drop_index("ix_mc_alerts_id", table_name="mc_alerts")
    op.drop_table("mc_alerts")
    op.drop_index("ix_mc_dynamics_id", table_name="mc_dynamics")
    op.drop_table("mc_dynamics")
    for enum_name in (
        "mcalertstatusenum",
        "mcalerttriggerenum",
        "mcdynamicmodalityenum",
        "mcdynamictypeenum",
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)

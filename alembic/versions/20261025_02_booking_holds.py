"""Dinero decimal, vencimiento e idempotencia de reservas.

Revision ID: 20261025_02
Revises: 20261025_01
"""
from alembic import op
import sqlalchemy as sa

revision = "20261025_02"
down_revision = "20261025_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Añade retenciones sin eliminar reservas ni reinterpretar su moneda histórica."""
    op.alter_column("experiences", "price", type_=sa.Numeric(14, 2), postgresql_using="round(price::numeric, 2)")
    for column in ("total_amount", "platform_fee", "host_payout"):
        op.alter_column("bookings", column, type_=sa.Numeric(14, 2), postgresql_using=f"round({column}::numeric, 2)")
    op.alter_column("payments", "amount", type_=sa.Numeric(14, 2), postgresql_using="round(amount::numeric, 2)")
    op.add_column("bookings", sa.Column("unit_price", sa.Numeric(14, 2), nullable=True))
    op.add_column("bookings", sa.Column("commission_rate", sa.Numeric(5, 4), nullable=True))
    op.add_column("bookings", sa.Column("currency", sa.String(3), nullable=True))
    # Una reserva histórica conserva la moneda de su pago cuando está disponible.
    op.execute("UPDATE bookings SET currency = upper(payments.currency) FROM payments WHERE payments.booking_id = bookings.id")
    op.execute("UPDATE bookings SET currency = 'BOB' WHERE currency IS NULL")
    op.alter_column("bookings", "currency", nullable=False)
    op.add_column("bookings", sa.Column("idempotency_key", sa.String(64), nullable=True))
    op.add_column("bookings", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("cancellation_reason", sa.String(40), nullable=True))
    op.create_index("ix_bookings_expires_at", "bookings", ["expires_at"])
    op.create_unique_constraint("uq_booking_user_idempotency", "bookings", ["user_id", "idempotency_key"])
    # No se modifica dinero histórico para forzar el balance: validar antes de imponerlo.
    op.create_check_constraint("ck_booking_positive_quantity", "bookings", "quantity > 0")
    op.create_check_constraint("ck_booking_nonnegative_amounts", "bookings", "total_amount >= 0 AND platform_fee >= 0 AND host_payout >= 0")
    op.create_check_constraint("ck_booking_balanced_amounts", "bookings", "total_amount = platform_fee + host_payout")


def downgrade() -> None:
    """Revierte las columnas añadidas en una operación de mantenimiento explícita."""
    for name in ("ck_booking_positive_quantity", "ck_booking_nonnegative_amounts", "ck_booking_balanced_amounts"):
        op.drop_constraint(name, "bookings", type_="check")
    op.drop_constraint("uq_booking_user_idempotency", "bookings", type_="unique")
    op.drop_index("ix_bookings_expires_at", table_name="bookings")
    for column in ("unit_price", "commission_rate", "currency", "idempotency_key", "expires_at", "cancellation_reason"):
        op.drop_column("bookings", column)
    for column in ("total_amount", "platform_fee", "host_payout"):
        op.alter_column("bookings", column, type_=sa.Float())
    op.alter_column("payments", "amount", type_=sa.Float())
    op.alter_column("experiences", "price", type_=sa.Float())

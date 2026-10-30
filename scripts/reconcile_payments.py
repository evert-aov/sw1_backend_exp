"""Conciliación periódica recuperable de sesiones y devoluciones Stripe pendientes."""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from sqlalchemy import func, select
from app.core.database import SessionLocal, init_db
from app.booking.entity.booking import Booking, BookingStatusEnum
from app.booking.entity.payment import Payment, PaymentStatusEnum
from app.booking.service.stripe_service import StripeService


def main() -> int:
    """Ejecuta un lote; programar cada minuto mediante cron o el gestor de procesos."""
    init_db()
    with SessionLocal() as db:
        rows = db.execute(select(Payment.booking_id, Payment.status, Payment.payment_metadata).join(Booking).where(
            Payment.stripe_checkout_session_id.is_not(None),
            (Payment.status == PaymentStatusEnum.PENDING) | (
                Payment.payment_metadata["refund_requested"].as_boolean().is_(True) &
                func.coalesce(Payment.payment_metadata["refund_status"].as_string(), "").not_in(["succeeded", "failed", "canceled"])
            ),
        ).order_by(Payment.created_at).limit(500)).all()
    failures = 0
    for booking_id, payment_status, metadata in rows:
        # Un error no impide procesar las otras reservas; cada caso usa su transacción.
        if (metadata or {}).get("refund_status") in {"succeeded", "failed", "canceled"}:
            continue
        with SessionLocal() as db:
            service = StripeService(db)
            try:
                if payment_status == PaymentStatusEnum.PENDING:
                    service.reconcile_booking(booking_id)
                service.process_refund(booking_id)
            except Exception as error:
                failures += 1
                code = error.status_code if isinstance(error, HTTPException) else type(error).__name__
                print(f"Conciliación pendiente para {booking_id}: {code}", file=sys.stderr)
    print(f"Revisadas: {len(rows)}; pendientes con error: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

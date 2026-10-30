"""Checkout, confirmación y conciliación de pagos con efectos locales atómicos."""

from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
import stripe
from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from app.booking.dto.booking_dto import CheckoutSessionDTO
from app.booking.entity.booking import Booking, BookingStatusEnum
from app.booking.entity.payment import Payment, PaymentStatusEnum
from app.booking.entity.stripe_event import StripeEvent
from app.booking.repository.payment_repository import PaymentRepository
from app.booking.service.booking_service import BookingService, utc, uuid_string
from app.booking.service.stripe_gateway import StripeGateway
from app.booking.service.stripe_errors import describe_stripe_failure
from app.core.config import settings
from app.experience.entity.experience import ExperienceStatusEnum

logger = logging.getLogger(__name__)


def minor_units(amount, currency: str) -> int:
    """Cruza a unidades menores solo para las monedas de dos decimales admitidas."""
    value = Decimal(str(amount))
    if currency.upper() not in {"BOB", "USD", "EUR"}:
        raise HTTPException(status_code=503, detail="Moneda de pago no habilitada")
    if not value.is_finite() or value <= 0 or value != value.quantize(Decimal("0.01")):
        raise HTTPException(status_code=409, detail="Importe de pago inválido")
    return int(value * 100)


class StripeService:
    """El proveedor confirma el dinero; el retorno del navegador solo consulta estado."""

    def __init__(self, db: Session, gateway=None):
        self.db = db
        self.bookings = BookingService(db)
        self.payments = PaymentRepository(db)
        self.gateway = gateway or StripeGateway()

    def _locked(self, booking_id: str):
        """Mantiene el orden experiencia → reserva → pago en todos los flujos."""
        snapshot = self.bookings._load(uuid_string(booking_id))
        experience = self.bookings.repository.lock_experience(snapshot.experience_id)
        booking = self.bookings.repository.lock_booking(snapshot.id)
        if not experience or not booking:
            raise HTTPException(status_code=404, detail="Reserva no disponible")
        return booking, experience, self.payments.get_by_booking_id(booking.id, lock=True)

    @staticmethod
    def _eligible(booking, experience) -> bool:
        now = datetime.now(timezone.utc)
        return (booking.status == BookingStatusEnum.PENDING and booking.expires_at is not None
                and utc(booking.expires_at) > now and utc(experience.event_date) > now
                and experience.status in {ExperienceStatusEnum.OPEN, ExperienceStatusEnum.CONFIRMED}
                and experience.reserved_slots + booking.quantity <= experience.max_capacity)

    @staticmethod
    def _upgrade_rejected_checkout(payment: Payment) -> None:
        """Retira el campo obsoleto solo tras un rechazo de validación, sin cambiar clave.

        Los intentos inciertos mantienen su petición original para recuperar una posible
        sesión remota; las sesiones ya creadas se consultan sin modificar sus parámetros.
        """
        if payment.stripe_checkout_session_id or payment.status != PaymentStatusEnum.PENDING:
            return
        metadata = dict(payment.payment_metadata or {})
        params = metadata.get("checkout_params")
        failure = metadata.get("last_checkout_error") or {}
        if (isinstance(params, dict) and "payment_method_types" in params
                and failure.get("category") == "InvalidRequestError"
                and failure.get("param") == "payment_method_types"):
            upgraded = dict(params)
            upgraded.pop("payment_method_types")
            metadata["checkout_params"] = upgraded
            metadata["checkout_params_version"] = 2
            payment.payment_metadata = metadata

    def create_checkout_session(self, booking_id: str, user_id: str) -> CheckoutSessionDTO:
        """Guarda un intento durable antes de llamar al proveedor y reutiliza su clave."""
        try:
            booking, experience, payment = self._locked(booking_id)
            if booking.user_id != user_id:
                raise HTTPException(status_code=403, detail="Reserva ajena")
            if not self._eligible(booking, experience):
                raise HTTPException(status_code=409, detail="La retención no está vigente")
            amount = minor_units(booking.total_amount, booking.currency)
            if not payment:
                origin = settings.FRONTEND_URL.rstrip("/")
                params = {
                    "mode": "payment",
                    "client_reference_id": booking.id,
                    "metadata": {"app": "experiencia", "booking_id": booking.id},
                    "success_url": f"{origin}/checkout/{booking.id}?payment=returned",
                    "cancel_url": f"{origin}/checkout/{booking.id}?payment=cancelled",
                    "line_items": [{"quantity": 1, "price_data": {
                        "currency": booking.currency.lower(), "unit_amount": amount,
                        "product_data": {"name": f"Reserva {booking.id}"},
                    }}],
                }
                payment = self.payments.create(Payment(
                    booking_id=booking.id, amount=booking.total_amount, currency=booking.currency,
                    status=PaymentStatusEnum.PENDING,
                    payment_metadata={"checkout_params": params, "checkout_params_version": 2},
                ))
            else:
                self._upgrade_rejected_checkout(payment)
            # El intento persiste incluso si Stripe acepta la petición y luego se pierde la respuesta.
            self.db.commit()
            booking, experience, payment = self._locked(booking_id)
            if not self._eligible(booking, experience) or payment.status != PaymentStatusEnum.PENDING:
                raise HTTPException(status_code=409, detail="Actualiza el estado de la reserva")
            metadata = dict(payment.payment_metadata or {})
            if payment.stripe_checkout_session_id:
                remote = self.gateway.retrieve_checkout(payment.stripe_checkout_session_id)
                if remote.get("status") != "open":
                    raise HTTPException(status_code=409, detail="Consulta el estado del pago o crea otra reserva")
            else:
                params = metadata.get("checkout_params")
                if not params:
                    raise HTTPException(status_code=409, detail="Pago histórico pendiente de conciliación")
                remote = self.gateway.create_checkout(params, f"checkout:{payment.id}")
            url = remote.get("url")
            if not isinstance(url, str) or not url.startswith("https://checkout.stripe.com/"):
                logger.warning("Stripe checkout failed booking=%s diagnostic=%s", booking_id, json.dumps({
                    "category": "InvalidCheckoutResponse", "code": "invalid_checkout_url",
                    "message": "Stripe no devolvió una URL Checkout con el host admitido.",
                }, ensure_ascii=False))
                raise HTTPException(status_code=502, detail="Stripe no devolvió una sesión de pago válida")
            payment.stripe_checkout_session_id = remote["id"]
            metadata["checkout_url"] = url
            metadata.pop("last_checkout_error", None)
            payment.payment_metadata = metadata
            self.db.commit()
            return CheckoutSessionDTO(booking_id=booking.id, checkout_url=url, stripe_session_id=remote["id"])
        except stripe.StripeError as error:
            self.db.rollback()
            failure = describe_stripe_failure(error)
            diagnostic = failure.diagnostic()
            logger.warning("Stripe checkout failed booking=%s diagnostic=%s", booking_id, json.dumps(diagnostic, ensure_ascii=False))
            # El intento previo ya es durable. Registrar la causa no cambia estado ni clave remota.
            try:
                payment = self.payments.get_by_booking_id(booking_id, lock=True)
                if payment:
                    metadata = dict(payment.payment_metadata or {})
                    metadata["last_checkout_error"] = diagnostic
                    payment.payment_metadata = metadata
                    self.db.commit()
            except Exception:
                self.db.rollback()
                logger.warning("No se pudo guardar el diagnóstico del checkout booking=%s", booking_id)
            raise HTTPException(status_code=failure.status, detail=failure.detail) from None
        except Exception:
            self.db.rollback()
            raise

    def _apply_session(self, remote, booking, experience, payment, *, failed: bool = False) -> str:
        """Verifica identidad, importe y moneda antes de emitir entradas o pedir devolución."""
        if remote.get("id") != payment.stripe_checkout_session_id or remote.get("client_reference_id") != booking.id:
            raise HTTPException(status_code=409, detail="La sesión no corresponde a la reserva")
        if remote.get("payment_status") != "paid":
            if (remote.get("status") == "expired" or failed) and payment.status == PaymentStatusEnum.PENDING:
                payment.status = PaymentStatusEnum.FAILED
                if booking.status == BookingStatusEnum.PENDING:
                    booking.status, booking.cancellation_reason = BookingStatusEnum.CANCELLED, "PAYMENT_EXPIRED"
            return "UNPAID"
        if remote.get("amount_total") != minor_units(booking.total_amount, booking.currency) or (remote.get("currency") or "").upper() != booking.currency.upper():
            raise HTTPException(status_code=409, detail="El importe o la moneda de Stripe no coincide")
        intent = remote.get("payment_intent")
        if not isinstance(intent, str) or not intent.startswith("pi_"):
            raise HTTPException(status_code=409, detail="Falta el identificador de pago verificado")
        if payment.stripe_payment_intent_id and payment.stripe_payment_intent_id != intent:
            raise HTTPException(status_code=409, detail="La reserva ya tiene otro pago asociado")
        payment.stripe_payment_intent_id = intent
        payment.status = PaymentStatusEnum.SUCCEEDED
        payment.paid_at = payment.paid_at or datetime.now(timezone.utc).replace(tzinfo=None)
        if booking.status in {BookingStatusEnum.PAID, BookingStatusEnum.REFUNDED}:
            return "ALREADY_PAID"
        if self._eligible(booking, experience):
            self.bookings._complete(booking, experience)
            return "PAID"
        booking.status = BookingStatusEnum.CANCELLED
        booking.cancellation_reason = booking.cancellation_reason or "LATE_PAYMENT"
        metadata = dict(payment.payment_metadata or {})
        metadata.update(refund_requested=True, refund_reason=booking.cancellation_reason)
        payment.payment_metadata = metadata
        return "REFUND_PENDING"

    def handle_webhook_event(self, payload: bytes, sig_header: str) -> dict:
        """Verifica cuerpo crudo y confirma evento, pago y entradas en un solo commit."""
        event = self.gateway.verify_event(payload, sig_header)
        try:
            event_id, event_type = event.get("id"), event.get("type", "")
            remote = event.get("data", {}).get("object", {})
            if not isinstance(event_id, str) or not event_id.startswith("evt_"):
                raise HTTPException(status_code=400, detail="Evento Stripe inválido")
            accepted = self.db.scalar(insert(StripeEvent).values(
                id=event_id, event_type=event_type, object_id=remote.get("id", ""), outcome="RECEIVED",
            ).on_conflict_do_nothing(index_elements=[StripeEvent.id]).returning(StripeEvent.id))
            if not accepted:
                self.db.commit()
                return {"received": True, "outcome": "DUPLICATE"}
            outcome = "IGNORED"
            if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded", "checkout.session.expired", "checkout.session.async_payment_failed"}:
                payment = self.payments.get_by_stripe_session(remote.get("id", ""))
                if not payment:
                    if remote.get("metadata", {}).get("app") == "experiencia":
                        raise HTTPException(status_code=503, detail="El intento de pago aún no está disponible; reintentar")
                else:
                    booking, experience, payment = self._locked(payment.booking_id)
                    outcome = self._apply_session(remote, booking, experience, payment, failed=event_type == "checkout.session.async_payment_failed")
            self.db.query(StripeEvent).filter(StripeEvent.id == event_id).update({"outcome": outcome})
            self.db.commit()
            return {"received": True, "outcome": outcome}
        except Exception:
            self.db.rollback()
            raise

    def reconcile_booking(self, booking_id: str, user_id: str | None = None):
        """Consulta Stripe desde el servidor; recupera un webhook o retorno perdido."""
        try:
            booking, experience, payment = self._locked(booking_id)
            if user_id is not None and booking.user_id != user_id:
                raise HTTPException(status_code=403, detail="Reserva ajena")
            if payment and payment.stripe_checkout_session_id:
                remote = self.gateway.retrieve_checkout(payment.stripe_checkout_session_id)
                self._apply_session(remote, booking, experience, payment)
                if remote.get("status") == "open" and not self._eligible(booking, experience):
                    self.gateway.expire_checkout(remote["id"])
            self.db.commit()
            return self.bookings.get_booking(booking_id, booking.user_id)
        except stripe.StripeError as error:
            self.db.rollback()
            raise HTTPException(status_code=502, detail="No se pudo consultar Stripe; reintenta") from error
        except Exception:
            self.db.rollback()
            raise

    def request_refund(self, booking_id: str, user_id: str):
        """Registra devolución completa propia antes del evento y antes de usar entradas."""
        try:
            booking, experience, payment = self._locked(booking_id)
            if booking.user_id != user_id:
                raise HTTPException(status_code=403, detail="Reserva ajena")
            if booking.status == BookingStatusEnum.REFUNDED:
                self.db.commit()
                return self.bookings.get_booking(booking_id, user_id)
            if booking.status != BookingStatusEnum.PAID or utc(experience.event_date) <= datetime.now(timezone.utc) or any(ticket.is_used for ticket in booking.tickets):
                raise HTTPException(status_code=409, detail="La reserva no admite devolución")
            if not payment or payment.status != PaymentStatusEnum.SUCCEEDED or not payment.stripe_payment_intent_id:
                raise HTTPException(status_code=409, detail="Falta un cobro Stripe conciliado")
            metadata = dict(payment.payment_metadata or {})
            metadata.update(refund_requested=True, refund_reason="USER")
            payment.payment_metadata = metadata
            self.db.commit()
            self.process_refund(booking_id)
            return self.bookings.get_booking(booking_id, user_id)
        except Exception:
            self.db.rollback()
            raise

    def process_refund(self, booking_id: str) -> str:
        """Reintenta devolución durable usando la misma clave incluso tras un reinicio."""
        try:
            booking, experience, payment = self._locked(booking_id)
            metadata = dict(payment.payment_metadata or {}) if payment else {}
            if not metadata.get("refund_requested") or metadata.get("refund_status") == "succeeded":
                self.db.commit()
                return metadata.get("refund_status", "NONE")
            if metadata.get("refund_status") in {"failed", "canceled"}:
                self.db.commit()
                return metadata["refund_status"]
            remote = (self.gateway.retrieve_refund(metadata["refund_id"]) if metadata.get("refund_id")
                      else self.gateway.refund(payment.stripe_payment_intent_id, f"refund:{payment.id}"))
            metadata.update(refund_id=remote["id"], refund_status=remote["status"])
            if remote["status"] == "succeeded":
                if booking.status == BookingStatusEnum.PAID:
                    if experience.reserved_slots < booking.quantity:
                        raise HTTPException(status_code=409, detail="El contador de cupos requiere conciliación")
                    experience.reserved_slots -= booking.quantity
                    if experience.status == ExperienceStatusEnum.CONFIRMED and experience.reserved_slots < experience.min_capacity:
                        experience.status = ExperienceStatusEnum.OPEN
                        from app.notifications.service import NotificationService
                        notices = NotificationService(self.db)
                        notices.stage(experience.id, notices.paid_audience(experience), "QUORUM_LOST", experience.quorum_generation,
                                      f"{experience.title}: el evento volvió a estar pendiente de quórum.")
                booking.status = BookingStatusEnum.REFUNDED
                booking.cancellation_reason = metadata.get("refund_reason", "REFUND")
            payment.payment_metadata = metadata
            self.db.commit()
            return remote["status"]
        except stripe.StripeError as error:
            self.db.rollback()
            raise HTTPException(status_code=502, detail="Devolución registrada; el conciliador reintentará") from error
        except Exception:
            self.db.rollback()
            raise

    def queue_event_refunds(self, experience) -> None:
        """Cancela retenciones y deja devoluciones durables dentro del commit del evento."""
        bookings = self.db.query(Booking).filter(Booking.experience_id == experience.id).order_by(Booking.id).with_for_update().all()
        for booking in bookings:
            if booking.status == BookingStatusEnum.PENDING:
                booking.status, booking.cancellation_reason = BookingStatusEnum.CANCELLED, "EVENT_CANCELLED"
            elif booking.status == BookingStatusEnum.PAID:
                if booking.total_amount == 0:
                    booking.status, booking.cancellation_reason = BookingStatusEnum.REFUNDED, "EVENT_CANCELLED"
                    experience.reserved_slots -= booking.quantity
                    continue
                payment = self.payments.get_by_booking_id(booking.id, lock=True)
                if not payment or payment.status != PaymentStatusEnum.SUCCEEDED or not payment.stripe_payment_intent_id:
                    raise HTTPException(status_code=409, detail="Hay cobros históricos pendientes de conciliación antes de cancelar")
                metadata = dict(payment.payment_metadata or {})
                metadata.update(refund_requested=True, refund_reason="EVENT_CANCELLED")
                payment.payment_metadata = metadata
        from app.notifications.service import NotificationService
        NotificationService(self.db).stage(experience.id, {experience.host_id, *(item.user_id for item in bookings)},
                                           "EVENT_CANCELLED", 0, f"{experience.title}: evento cancelado. Los cobros se tramitan para devolución.")

    def create_saas_subscription(self, user_id: str, plan_id: str):
        """HU-23 requiere resolver su alcance comercial antes de habilitar cobros."""
        raise HTTPException(status_code=501, detail="Contratación SaaS pendiente de definición de alcance")

    def cancel_saas_subscription(self, subscription_id: str):
        raise HTTPException(status_code=501, detail="Cancelación SaaS aún no disponible")

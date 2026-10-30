"""Reservas transaccionales, vencimiento, historial e ingreso con PostgreSQL."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from sqlalchemy import case, func, select

from app.booking.dto.booking_dto import BookingCreateDTO, BookingResponseDTO, HostIncomeDTO, TicketDTO
from app.booking.entity.booking import Booking, BookingStatusEnum
from app.booking.entity.payment import Payment, PaymentStatusEnum
from app.booking.entity.ticket import Ticket
from app.booking.repository.booking_repository import BookingRepository
from app.core.config import settings
from app.core.database import generate_uuid
from app.core.pricing import quote_price
from app.experience.entity.experience import Experience, ExperienceStatusEnum


def utc(value: datetime) -> datetime:
    """Normaliza fechas históricas UTC sin zona y fechas conscientes de zona."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def uuid_string(value: str) -> str:
    """Evita enviar IDs mal formados al tipo UUID de PostgreSQL."""
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as error:
        raise HTTPException(status_code=422, detail="Identificador UUID inválido") from error


class BookingService:
    """Aplica casos de uso de reserva y tickets sin commits parciales de repositorios."""

    def __init__(self, db: Session):
        """Recibe la sesión de la solicitud; PostgreSQL controla bloqueos y aislamiento."""
        self.db = db
        self.repository = BookingRepository(db)

    def calculate_tiered_fee(self, price: float, quantity: int) -> Decimal:
        """Consulta la política monetaria compartida, sin cálculo binario de dinero."""
        return quote_price(price, quantity).platform_fee

    def _response(self, booking: Booking) -> BookingResponseDTO:
        """Expone historial enriquecido sin datos de otros compradores."""
        result = BookingResponseDTO.model_validate(booking)
        if booking.experience:
            result.experience_title = booking.experience.title
            result.event_date = utc(booking.experience.event_date)
            result.experience_status = booking.experience.status
        if booking.payment and (booking.payment.payment_metadata or {}).get("refund_requested"):
            result.refund_status = (booking.payment.payment_metadata or {}).get("refund_status", "pending")
        return result

    def _load(self, booking_id: str) -> Booking:
        """Carga una reserva y las relaciones necesarias para su respuesta."""
        booking = self.repository.get_by_id(uuid_string(booking_id))
        if not booking:
            raise HTTPException(status_code=404, detail="Reserva no encontrada")
        return booking

    def create_booking(self, user_id: str, dto: BookingCreateDTO, idempotency_key: str) -> BookingResponseDTO:
        """Serializa por usuario y experiencia; repetir una clave no retiene cupos nuevos."""
        experience_id = uuid_string(dto.experience_id)
        if not 8 <= len(idempotency_key) <= 64:
            raise HTTPException(status_code=422, detail="Idempotency-Key debe contener entre 8 y 64 caracteres")
        try:
            # Orden de bloqueos: usuario → experiencia → reserva. No bloquear a la inversa.
            user = self.repository.lock_user(user_id)
            if not user or not user.is_active:
                raise HTTPException(status_code=403, detail="Usuario no disponible")
            existing = self.repository.get_by_idempotency(user_id, idempotency_key)
            if existing:
                if existing.experience_id != experience_id or existing.quantity != dto.quantity:
                    raise HTTPException(status_code=409, detail="La clave ya corresponde a otra solicitud")
                self.db.commit()
                return self._response(self._load(existing.id))

            experience = self.repository.lock_experience(experience_id)
            if not experience:
                raise HTTPException(status_code=404, detail="Experiencia no encontrada")
            now = datetime.now(timezone.utc)
            if experience.status not in {ExperienceStatusEnum.OPEN, ExperienceStatusEnum.CONFIRMED} or utc(experience.event_date) <= now:
                raise HTTPException(status_code=409, detail="La experiencia no admite reservas")
            # Incluye pendientes históricos sin vencimiento: requieren conciliación, no sobreventa.
            holds = self.repository.active_hold_quantity(experience_id, now)
            if experience.reserved_slots + holds + dto.quantity > experience.max_capacity:
                raise HTTPException(status_code=409, detail="No hay cupos suficientes")
            quote = quote_price(experience.price, dto.quantity)
            if quote.total_amount > Decimal("999999999999.99"):
                raise HTTPException(status_code=422, detail="Importe fuera del rango permitido")
            booking = Booking(
                user_id=user_id, experience_id=experience_id, quantity=dto.quantity,
                unit_price=quote.unit_price, commission_rate=quote.commission_rate,
                total_amount=quote.total_amount, platform_fee=quote.platform_fee,
                host_payout=quote.host_payout, currency=settings.PAYMENT_CURRENCY,
                idempotency_key=idempotency_key,
                expires_at=min(now + timedelta(minutes=settings.BOOKING_HOLD_MINUTES), utc(experience.event_date)),
                status=BookingStatusEnum.PENDING,
            )
            self.repository.create(booking)
            if quote.total_amount == 0:
                self._complete(booking, experience)
            self.db.commit()
            return self._response(self._load(booking.id))
        except Exception:
            self.db.rollback()
            raise

    def _complete(self, booking: Booking, experience: Experience) -> None:
        """Confirma bajo bloqueo; solo se invoca para pago verificado o entrada gratuita."""
        if booking.status == BookingStatusEnum.PAID:
            return
        booking.status = BookingStatusEnum.PAID
        experience.reserved_slots += booking.quantity
        crossed = False
        if experience.reserved_slots >= experience.min_capacity and experience.status == ExperienceStatusEnum.OPEN:
            experience.status = ExperienceStatusEnum.CONFIRMED
            experience.quorum_generation = (experience.quorum_generation or 0) + 1
            crossed = True
        for _ in range(booking.quantity):
            ticket_id, code = generate_uuid(), generate_uuid()
            payload = jwt.encode({
                "type": "entry", "ticket_id": ticket_id, "ticket_code": code,
                "experience_id": experience.id,
                "exp": utc(experience.event_date) + timedelta(days=2),
            }, settings.JWT_SECRET, algorithm=settings.ALGORITHM)
            self.repository.create_ticket(Ticket(id=ticket_id, booking_id=booking.id, ticket_code=code, qr_payload=payload))
        if experience.status == ExperienceStatusEnum.CONFIRMED:
            from app.notifications.service import NotificationService
            self.db.flush()
            NotificationService(self.db).confirmation(experience, booking, crossed=crossed)

    def confirm_booking(self, booking_id: str) -> BookingResponseDTO:
        """Confirma únicamente una reserva con pago ya verificado y cupo todavía retenido."""
        try:
            snapshot = self._load(booking_id)
            experience = self.repository.lock_experience(snapshot.experience_id)
            booking = self.repository.lock_booking(snapshot.id)
            if not booking or not experience:
                raise HTTPException(status_code=409, detail="La reserva o experiencia dejó de estar disponible")
            if booking.status == BookingStatusEnum.PAID:
                self.db.commit()
                return self._response(self._load(booking.id))
            payment = self.db.query(Payment).filter(Payment.booking_id == booking.id).first()
            now = datetime.now(timezone.utc)
            if not payment or payment.status != PaymentStatusEnum.SUCCEEDED or payment.amount != booking.total_amount or payment.currency.upper() != booking.currency.upper():
                raise HTTPException(status_code=409, detail="La reserva no tiene un pago verificado equivalente")
            if booking.status != BookingStatusEnum.PENDING or booking.expires_at is None or utc(booking.expires_at) <= now:
                raise HTTPException(status_code=409, detail="Retención vencida; requiere conciliación del pago")
            if experience.status not in {ExperienceStatusEnum.OPEN, ExperienceStatusEnum.CONFIRMED} or utc(experience.event_date) <= now:
                raise HTTPException(status_code=409, detail="La experiencia ya no admite confirmación")
            if experience.reserved_slots + booking.quantity > experience.max_capacity:
                raise HTTPException(status_code=409, detail="La capacidad requiere conciliación")
            self._complete(booking, experience)
            self.db.commit()
            return self._response(self._load(booking.id))
        except Exception:
            self.db.rollback()
            raise

    def get_user_bookings(self, user_id: str) -> list[BookingResponseDTO]:
        """Lista solo las reservas del comprador, con datos de evento y entradas."""
        bookings = self.repository.get_by_user(user_id)
        return [self._response(booking) for booking in bookings]

    def host_income(self, user_id: str) -> list[HostIncomeDTO]:
        """Agrega solo experiencias propias y separa monedas e importes devueltos."""
        paid = Booking.status == BookingStatusEnum.PAID
        refunded = Booking.status == BookingStatusEnum.REFUNDED
        refund_requested = Payment.payment_metadata["refund_requested"].as_boolean().is_(True)
        statement = select(
            Booking.currency.label("currency"),
            func.sum(case((paid, Booking.total_amount), else_=0)).label("gross"),
            func.sum(case((paid, Booking.platform_fee), else_=0)).label("platform_fee"),
            func.sum(case((paid, Booking.host_payout), else_=0)).label("net"),
            func.sum(case((refunded, Booking.total_amount), else_=0)).label("refunded"),
            func.sum(case((paid & refund_requested, Booking.total_amount), else_=0)).label("refund_pending"),
        ).join(Experience, Experience.id == Booking.experience_id).outerjoin(Payment, Payment.booking_id == Booking.id).where(
            Experience.host_id == user_id, Booking.status.in_([BookingStatusEnum.PAID, BookingStatusEnum.REFUNDED]),
        ).group_by(Booking.currency).order_by(Booking.currency)
        return [HostIncomeDTO(**row) for row in self.db.execute(statement).mappings()]

    def get_booking(self, booking_id: str, user_id: str) -> BookingResponseDTO:
        """Permite consultar el retorno del checkout exclusivamente a su comprador."""
        booking = self._load(booking_id)
        if booking.user_id != user_id:
            raise HTTPException(status_code=403, detail="Reserva ajena")
        return self._response(booking)

    def cancel_pending(self, booking_id: str, user_id: str) -> BookingResponseDTO:
        """Libera una retención propia; una reserva pagada requiere un reembolso real."""
        try:
            booking = self.repository.lock_booking(uuid_string(booking_id))
            if not booking:
                raise HTTPException(status_code=404, detail="Reserva no encontrada")
            if booking.user_id != user_id:
                raise HTTPException(status_code=403, detail="Reserva ajena")
            if booking.status == BookingStatusEnum.PAID:
                raise HTTPException(status_code=409, detail="Una reserva pagada requiere reembolso")
            if booking.status == BookingStatusEnum.PENDING:
                booking.status, booking.cancellation_reason = BookingStatusEnum.CANCELLED, "USER"
            self.db.commit()
            return self._response(self._load(booking.id))
        except Exception:
            self.db.rollback()
            raise

    def release_expired_holds(self) -> int:
        """Cancela pendientes vencidas una sola vez; las consultas ya excluyen su retención."""
        try:
            count = self.repository.release_expired(datetime.now(timezone.utc))
            self.db.commit()
            return count
        except Exception:
            self.db.rollback()
            raise

    def validate_ticket(self, ticket_code: str, user_id: str) -> TicketDTO:
        """Consulta una entrada sin consumirla, limitada al comprador o anfitrión."""
        ticket = self.repository.get_ticket_by_code(ticket_code)
        if not ticket:
            raise HTTPException(status_code=404, detail="Entrada no encontrada")
        booking = ticket.booking
        if user_id not in {booking.user_id, booking.experience.host_id}:
            raise HTTPException(status_code=403, detail="Entrada ajena")
        if booking.status != BookingStatusEnum.PAID or booking.experience.status == ExperienceStatusEnum.CANCELLED:
            raise HTTPException(status_code=409, detail="Entrada no válida")
        if booking.payment and (booking.payment.payment_metadata or {}).get("refund_requested"):
            raise HTTPException(status_code=409, detail="La entrada tiene una devolución solicitada")
        return TicketDTO.model_validate(ticket)

    def check_in(self, ticket_id: str, user_id: str) -> TicketDTO:
        """Registra uso atómico de una entrada para el anfitrión de ese evento."""
        try:
            snapshot = self.db.get(Ticket, uuid_string(ticket_id))
            if not snapshot:
                raise HTTPException(status_code=404, detail="Entrada no encontrada")
            self.repository.lock_experience(snapshot.booking.experience_id)
            self.repository.lock_booking(snapshot.booking_id)
            ticket = self.repository.lock_ticket(snapshot.id)
            if ticket.booking.experience.host_id != user_id:
                raise HTTPException(status_code=403, detail="No administras este evento")
            self.validate_ticket(ticket.ticket_code, user_id)
            if ticket.booking.experience.status != ExperienceStatusEnum.CONFIRMED:
                raise HTTPException(status_code=409, detail="El evento todavía no tiene quórum confirmado")
            if ticket.is_used:
                raise HTTPException(status_code=409, detail="Entrada ya utilizada")
            ticket.is_used, ticket.used_at = True, datetime.now(timezone.utc).replace(tzinfo=None)
            self.db.commit()
            return TicketDTO.model_validate(ticket)
        except Exception:
            self.db.rollback()
            raise

    def ticket_qr(self, ticket_id: str, user_id: str) -> bytes:
        """Genera SVG local del payload firmado, tras comprobar propiedad y validez."""
        ticket = self.db.get(Ticket, uuid_string(ticket_id))
        if not ticket:
            raise HTTPException(status_code=404, detail="Entrada no encontrada")
        self.validate_ticket(ticket.ticket_code, user_id)
        try:
            import qrcode
            from qrcode.image.svg import SvgPathImage
        except ImportError as error:
            raise HTTPException(status_code=503, detail="Instala requirements.txt para generar códigos QR") from error
        return qrcode.make(ticket.qr_payload, image_factory=SvgPathImage, border=4).to_string()

    def scan_ticket(self, code: str, user_id: str) -> TicketDTO:
        """Comprueba firma y correspondencia de claims antes del check-in transaccional."""
        code = code.strip()
        if "." not in code:
            ticket = self.validate_ticket(code, user_id)
            return self.check_in(ticket.id, user_id)
        try:
            payload = jwt.decode(code, settings.JWT_SECRET, algorithms=[settings.ALGORITHM], options={"require_exp": True})
        except JWTError as error:
            raise HTTPException(status_code=400, detail="QR inválido o vencido") from error
        if payload.get("type") != "entry":
            raise HTTPException(status_code=400, detail="El QR no corresponde a una entrada")
        ticket = self.db.get(Ticket, uuid_string(payload.get("ticket_id")))
        if not ticket or ticket.ticket_code != payload.get("ticket_code") or ticket.booking.experience_id != payload.get("experience_id"):
            raise HTTPException(status_code=400, detail="El QR no coincide con la entrada")
        return self.check_in(ticket.id, user_id)

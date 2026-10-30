"""Acceso SQL de reservas y entradas; la transacción pertenece al servicio."""

from datetime import datetime
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload, selectinload
from app.auth.entity.user import User
from app.booking.entity.booking import Booking, BookingStatusEnum
from app.booking.entity.ticket import Ticket
from app.experience.entity.experience import Experience


class BookingRepository:
    """Agrupa consultas y bloqueos requeridos por una operación de reserva."""

    def __init__(self, db: Session):
        """Conserva la sesión inyectada sin crear conexiones independientes."""
        self.db = db

    def get_by_id(self, booking_id: str) -> Booking | None:
        """Carga evento y entradas para el historial o retorno del checkout."""
        return self.db.query(Booking).options(joinedload(Booking.experience), joinedload(Booking.payment), selectinload(Booking.tickets)).filter(Booking.id == booking_id).first()

    def get_by_idempotency(self, user_id: str, key: str) -> Booking | None:
        """Busca el resultado anterior de una clave dentro de la misma cuenta."""
        return self.db.query(Booking).filter(Booking.user_id == user_id, Booking.idempotency_key == key).first()

    def lock_user(self, user_id: str) -> User | None:
        """Serializa solicitudes de una cuenta antes de bloquear una experiencia."""
        # NO KEY UPDATE serializa la cuenta sin bloquear los KEY SHARE de las FK de avisos.
        # FOR UPDATE causaría un ciclo con otro comprador esperando la misma experiencia.
        return self.db.query(User).filter(User.id == user_id).with_for_update(key_share=True).first()

    def lock_experience(self, experience_id: str) -> Experience | None:
        """Refresca el aforo bajo bloqueo para evitar valores obsoletos de la sesión."""
        return self.db.query(Experience).filter(Experience.id == experience_id).populate_existing().with_for_update().first()

    def lock_booking(self, booking_id: str) -> Booking | None:
        """Refresca el estado bajo bloqueo; adquirir primero experiencia cuando corresponda."""
        return self.db.query(Booking).filter(Booking.id == booking_id).populate_existing().with_for_update().first()

    def active_hold_quantity(self, experience_id: str, now: datetime) -> int:
        """Cuenta retenciones vigentes y conserva pendientes antiguos hasta conciliarlos."""
        return self.db.scalar(select(func.coalesce(func.sum(Booking.quantity), 0)).where(
            Booking.experience_id == experience_id, Booking.status == BookingStatusEnum.PENDING,
            (Booking.expires_at > now) | Booking.expires_at.is_(None),
        )) or 0

    def create(self, booking: Booking) -> Booking:
        """Agrega y obtiene el UUID sin confirmar parcialmente la operación."""
        self.db.add(booking)
        self.db.flush()
        return booking

    def update_status(self, booking_id: str, status: BookingStatusEnum) -> Booking | None:
        """Modifica el estado dentro de la transacción iniciada por el servicio."""
        booking = self.lock_booking(booking_id)
        if booking:
            booking.status = status
        return booking

    def get_by_user(self, user_id: str) -> list[Booking]:
        """Lista únicamente reservas propias, cargando relaciones en lotes."""
        return self.db.query(Booking).options(joinedload(Booking.experience), joinedload(Booking.payment), selectinload(Booking.tickets)).filter(Booking.user_id == user_id).order_by(Booking.created_at.desc()).all()

    def create_ticket(self, ticket: Ticket) -> Ticket:
        """Agrega una entrada al mismo commit de la reserva pagada."""
        self.db.add(ticket)
        return ticket

    def get_ticket_by_code(self, code: str) -> Ticket | None:
        """Carga titular y anfitrión para que el servicio aplique autorización."""
        return self.db.query(Ticket).options(joinedload(Ticket.booking).joinedload(Booking.experience)).filter(Ticket.ticket_code == code).first()

    def lock_ticket(self, ticket_id: str) -> Ticket | None:
        """Serializa el registro de ingreso para impedir doble uso."""
        return self.db.query(Ticket).filter(Ticket.id == ticket_id).populate_existing().with_for_update().first()

    def release_expired(self, now: datetime) -> int:
        """Actualiza una sola vez reservas pendientes con vencimiento conocido."""
        result = self.db.execute(update(Booking).where(
            Booking.status == BookingStatusEnum.PENDING, Booking.expires_at <= now,
        ).values(status=BookingStatusEnum.CANCELLED, cancellation_reason="EXPIRED"))
        return result.rowcount

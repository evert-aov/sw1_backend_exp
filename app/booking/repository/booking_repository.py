from typing import Optional, List
from sqlalchemy.orm import Session
from app.booking.entity.booking import Booking, BookingStatusEnum
from app.booking.entity.ticket import Ticket


# Repositorio para la entidad Booking y Ticket: únicamente firmas de métodos
class BookingRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, booking_id: str) -> Optional[Booking]:
        # Buscar reserva por ID
        pass

    def create(self, booking: Booking) -> Booking:
        # Registrar nueva reserva
        pass

    def update_status(self, booking_id: str, status: BookingStatusEnum) -> Optional[Booking]:
        # Actualizar estado de la reserva (PAID, CANCELLED, REFUNDED)
        pass

    def get_by_user(self, user_id: str) -> List[Booking]:
        # Obtener historial de reservas de un asistente
        pass

    def create_ticket(self, ticket: Ticket) -> Ticket:
        # Generar ticket de entrada con código QR
        pass

    def get_ticket_by_code(self, ticket_code: str) -> Optional[Ticket]:
        # Validar entrada por código único
        pass

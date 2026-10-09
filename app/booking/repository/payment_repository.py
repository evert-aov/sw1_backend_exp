from typing import Optional
from sqlalchemy.orm import Session
from app.booking.entity.payment import Payment, PaymentStatusEnum


# Repositorio para la entidad Payment: únicamente firmas de métodos
class PaymentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, payment_id: int) -> Optional[Payment]:
        # Buscar pago por ID
        pass

    def get_by_booking_id(self, booking_id: int) -> Optional[Payment]:
        # Obtener pago asociado a una reserva
        pass

    def get_by_stripe_session(self, session_id: str) -> Optional[Payment]:
        # Buscar pago por Session ID de Stripe Checkout
        pass

    def create(self, payment: Payment) -> Payment:
        # Registrar transacción de pago
        pass

    def update_status(self, payment_id: int, status: PaymentStatusEnum) -> Optional[Payment]:
        # Actualizar estado del pago tras confirmación del Webhook
        pass

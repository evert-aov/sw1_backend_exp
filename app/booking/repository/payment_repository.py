from typing import Optional
from sqlalchemy.orm import Session
from app.booking.entity.payment import Payment, PaymentStatusEnum


# Repositorio para la entidad Payment: únicamente firmas de métodos
class PaymentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, payment_id: str) -> Optional[Payment]:
        return self.db.get(Payment, payment_id)

    def get_by_booking_id(self, booking_id: str, *, lock: bool = False) -> Optional[Payment]:
        query = self.db.query(Payment).filter(Payment.booking_id == booking_id)
        if lock:
            query = query.populate_existing().with_for_update()
        return query.first()

    def get_by_stripe_session(self, session_id: str) -> Optional[Payment]:
        return self.db.query(Payment).filter(Payment.stripe_checkout_session_id == session_id).first()

    def create(self, payment: Payment) -> Payment:
        self.db.add(payment)
        self.db.flush()
        return payment

    def update_status(self, payment_id: str, status: PaymentStatusEnum) -> Optional[Payment]:
        payment = self.db.query(Payment).filter(Payment.id == payment_id).with_for_update().first()
        if payment:
            payment.status = status
        return payment

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.booking.dto.booking_dto import CheckoutSessionDTO
from app.booking.service.stripe_service import StripeService

payment_router = APIRouter(prefix="/payments", tags=["Payment & Stripe Controller"])


@payment_router.post("/checkout/{booking_id}", response_model=CheckoutSessionDTO)
def create_checkout(booking_id: int, db: Session = Depends(get_db)):
    # Firma de endpoint para iniciar sesión de pago Stripe
    pass


@payment_router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    # Firma de endpoint para recibir webhooks asíncronos de Stripe
    pass

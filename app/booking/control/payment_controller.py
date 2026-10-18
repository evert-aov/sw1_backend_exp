from __future__ import annotations

from typing import Annotated, Any
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session
from app.booking.dto.booking_dto import CheckoutSessionDTO
from app.booking.service.stripe_service import StripeService
from app.core.database import get_db

payment_router = APIRouter(prefix="/payments", tags=["Payment & Stripe Controller"])


@payment_router.post(
    "/checkout/{booking_id}",
    response_model=CheckoutSessionDTO,
    status_code=status.HTTP_200_OK,
    summary="Iniciar sesión de pago en Stripe Checkout (CU-06)",
    description="Genera una sesión de pago segura en Stripe Checkout para completar una reserva.",
)
def create_checkout(
    booking_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> CheckoutSessionDTO:
    """
    Crea una sesión de pago en Stripe Checkout para la reserva indicada (Sprint 2 - CU-06).

    Args:
        booking_id (int): ID de la reserva a pagar.
        db (Session): Sesión activa de base de datos.

    Returns:
        CheckoutSessionDTO: URL de pago e identificador de sesión de Stripe.
    """
    service = StripeService(db)
    return service.create_checkout_session(booking_id=booking_id)


@payment_router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Recibir eventos Webhook asíncronos desde Stripe",
    description="Procesa notificaciones firmadas de Stripe para confirmar pagos y suscripciones.",
)
async def stripe_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """
    Procesa los eventos asíncronos enviados por el Webhook de Stripe (Sprint 2 - CU-06).

    Args:
        request (Request): Petición HTTP entrante con firma de Stripe.
        db (Session): Sesión activa de base de datos.

    Returns:
        dict[str, Any]: Resultado del procesamiento del evento.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    service = StripeService(db)
    return service.handle_webhook_event(payload=payload, sig_header=sig_header)

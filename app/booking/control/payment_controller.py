from __future__ import annotations

from typing import Annotated, Any
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session
from app.booking.dto.booking_dto import BookingResponseDTO, CheckoutSessionDTO
from starlette.concurrency import run_in_threadpool
from app.booking.service.stripe_service import StripeService
from app.core.database import get_db
from app.auth.entity.user import User
from app.core.security import get_current_active_user, RoleChecker

payment_router = APIRouter(prefix="/payments", tags=["Payment & Stripe Controller"])


@payment_router.post(
    "/checkout/{booking_id}",
    response_model=CheckoutSessionDTO,
    status_code=status.HTTP_200_OK,
    summary="Iniciar sesión de pago en Stripe Checkout (CU-05)",
    description="Genera una sesión de pago segura en Stripe Checkout para completar una reserva.",
)
def create_checkout(
    booking_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["ATTENDEE"]))],
) -> CheckoutSessionDTO:
    """
    Crea una sesión de pago en Stripe Checkout para la reserva indicada (Sprint 2 - CU-05).

    Args:
        booking_id (str): ID de la reserva a pagar.
        db (Session): Sesión activa de base de datos.

    Returns:
        CheckoutSessionDTO: URL de pago e identificador de sesión de Stripe.
    """
    service = StripeService(db)
    return service.create_checkout_session(
        booking_id=booking_id, user_id=current_user.id
    )


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
    Procesa los eventos asíncronos enviados por el Webhook de Stripe (Sprint 2 - CU-05).

    Args:
        request (Request): Petición HTTP entrante con firma de Stripe.
        db (Session): Sesión activa de base de datos.

    Returns:
        dict[str, Any]: Resultado del procesamiento del evento.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    service = StripeService(db)
    return await run_in_threadpool(
        service.handle_webhook_event, payload=payload, sig_header=sig_header
    )


@payment_router.post("/status/{booking_id}", response_model=BookingResponseDTO)
def reconcile_payment(
    booking_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["ATTENDEE"]))],
) -> BookingResponseDTO:
    """Consulta al proveedor desde el backend después del retorno del checkout."""
    return StripeService(db).reconcile_booking(booking_id, current_user.id)


@payment_router.post("/refund/{booking_id}", response_model=BookingResponseDTO)
def refund_payment(
    booking_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["ATTENDEE"]))],
) -> BookingResponseDTO:
    """Solicita devolución completa propia antes del evento y sin entradas usadas."""
    return StripeService(db).request_refund(booking_id, current_user.id)

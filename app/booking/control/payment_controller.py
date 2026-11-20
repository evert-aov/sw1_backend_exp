from __future__ import annotations

from html import escape
from typing import Annotated, Any, Literal
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.booking.dto.booking_dto import BookingResponseDTO, CheckoutSessionDTO
from starlette.concurrency import run_in_threadpool
from app.booking.service.stripe_service import StripeService
from app.core.config import settings
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
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["ATTENDEE"]))],
    platform: Annotated[Literal["web", "mobile"], Query()] = "web",
) -> CheckoutSessionDTO:
    """
    Crea una sesión de pago en Stripe Checkout para la reserva indicada (Sprint 2 - CU-05).

    Args:
        booking_id (str): ID de la reserva a pagar.
        request (Request): Petición HTTP entrante.
        db (Session): Sesión activa de base de datos.
        platform (str): Origen del cliente (`web` o `mobile`).

    Returns:
        CheckoutSessionDTO: URL de pago e identificador de sesión de Stripe.
    """
    mobile_return_url: str | None = None
    if platform == "mobile":
        base = str(request.base_url).rstrip("/")
        mobile_return_url = f"{base}{settings.API_V1_STR}/payments/mobile-return/{booking_id}"
    service = StripeService(db)
    return service.create_checkout_session(
        booking_id=booking_id,
        user_id=current_user.id,
        mobile_return_url=mobile_return_url,
    )


@payment_router.get(
    "/mobile-return/{booking_id}",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    summary="Puente de retorno desde Stripe Checkout hacia la app móvil",
)
def mobile_checkout_return(
    booking_id: str,
    status_param: Annotated[str, Query(alias="status")] = "returned",
) -> HTMLResponse:
    """Redirige desde el navegador móvil de vuelta a la app mediante deep link."""
    safe_booking = escape(booking_id)
    safe_status = "cancelled" if status_param == "cancelled" else "returned"
    deep_link = f"experiencia://checkout/{safe_booking}?status={safe_status}"
    title = (
        "Pago cancelado"
        if safe_status == "cancelled"
        else "Volviendo a EXPERIENCIA"
    )
    subtitle = (
        "No se realizó ningún cobro. Puedes volver a la aplicación."
        if safe_status == "cancelled"
        else "Estamos regresando a la aplicación para verificar tu reserva."
    )
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{
      margin: 0; font-family: system-ui, -apple-system, sans-serif;
      background: #191411; color: #f3ebe2;
      display: grid; place-items: center; min-height: 100dvh; padding: 24px;
    }}
    .card {{
      max-width: 380px; width: 100%; background: #251e18;
      border: 1px solid #3a3028; border-radius: 20px; padding: 28px; text-align: center;
    }}
    h1 {{ font-family: Georgia, serif; font-size: 24px; margin: 0 0 10px; font-weight: 600; }}
    p {{ color: #a39487; font-size: 14px; line-height: 1.5; margin: 0 0 22px; }}
    a.btn {{
      display: inline-block; padding: 14px 24px; border-radius: 12px;
      background: #e27a5d; color: #191411; font-weight: 700; text-decoration: none;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{title}</h1>
    <p>{subtitle}</p>
    <a class="btn" href="{deep_link}">Volver a la app</a>
  </div>
  <script>
    window.location.replace("{deep_link}");
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)


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

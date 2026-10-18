from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from app.booking.entity.booking import BookingStatusEnum
from app.booking.entity.saas_subscription import SubscriptionStatusEnum


class BookingCreateDTO(BaseModel):
    """
    Contrato de datos para iniciar una reserva de cupo en una experiencia (CU-06 / HU-06).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    experience_id: int = Field(..., ge=1, description="ID de la experiencia a reservar")
    quantity: int = Field(default=1, ge=1, le=20, description="Cantidad de cupos a adquirir")


class TicketDTO(BaseModel):
    """
    Contrato de respuesta para el detalle de una entrada digital con código QR (HU-12).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID único del ticket")
    ticket_code: str = Field(..., description="Código alfanumérico único de validación")
    qr_payload: str = Field(..., description="Payload firmado para renderizar el código QR")
    is_used: bool = Field(default=False, description="Indica si el ticket ya fue escaneado en puerta")
    used_at: datetime | None = Field(default=None, description="Fecha y hora de escaneo del ticket")


class BookingResponseDTO(BaseModel):
    """
    Contrato de respuesta de una reserva con desglose de comisión de plataforma y entradas generadas (CU-06 / HU-06, HU-07).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID único de la reserva")
    user_id: int = Field(..., description="ID del asistente titular de la reserva")
    experience_id: int = Field(..., description="ID de la experiencia reservada")
    quantity: int = Field(..., description="Cantidad de entradas reservadas")
    total_amount: float = Field(..., description="Monto total abonado")
    platform_fee: float = Field(..., description="Comisión retenida por la plataforma")
    host_payout: float = Field(..., description="Liquidación neta para el anfitrión")
    status: BookingStatusEnum = Field(..., description="Estado actual de la reserva")
    created_at: datetime = Field(..., description="Fecha y hora de creación de la reserva")
    tickets: list[TicketDTO] = Field(
        default_factory=list,
        description="Lista de tickets digitales emitidos para la reserva",
    )


class CheckoutSessionDTO(BaseModel):
    """
    Contrato de respuesta al iniciar una sesión de pago en Stripe Checkout (CU-06).
    """

    model_config = ConfigDict(from_attributes=True)

    booking_id: int = Field(..., description="ID de la reserva vinculada al pago")
    checkout_url: str = Field(..., description="URL de redirección hacia la pasarela Stripe Checkout")
    stripe_session_id: str = Field(..., description="ID de sesión generado por Stripe")


class StripeWebhookDTO(BaseModel):
    """
    Contrato para el procesamiento de eventos webhook entrantes desde Stripe.
    """

    event_type: str = Field(..., description="Tipo de evento de Stripe (ej. checkout.session.completed)")
    data: dict[str, Any] = Field(default_factory=dict, description="Objeto de datos del evento Stripe")


class SaaSPlanDTO(BaseModel):
    """
    Contrato de respuesta para los planes de suscripción SaaS Pro de analítica avanzada (CU-14 / HU-23).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID del plan SaaS")
    name: str = Field(..., description="Nombre comercial del plan")
    monthly_price: float = Field(..., description="Precio mensual recurrente")
    features_included: dict[str, Any] = Field(
        default_factory=dict,
        description="Características y límites incluidos en el plan",
    )
    stripe_price_id: str | None = Field(default=None, description="ID de precio en Stripe Billing")
    is_active: bool = Field(default=True, description="Indica si el plan está disponible para contratación")


class SubscriptionCreateDTO(BaseModel):
    """
    Contrato de entrada para suscribirse a un plan SaaS Pro (CU-14).
    """

    plan_id: int = Field(..., ge=1, description="ID del plan SaaS a contratar")


class SubscriptionResponseDTO(BaseModel):
    """
    Contrato de respuesta con el estado de la suscripción SaaS de un anfitrión o establecimiento (CU-14).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID único de la suscripción")
    user_id: int = Field(..., description="ID del usuario suscrito")
    plan_id: int = Field(..., description="ID del plan contratado")
    stripe_subscription_id: str | None = Field(default=None, description="ID de suscripción en Stripe")
    status: SubscriptionStatusEnum = Field(..., description="Estado de la suscripción")
    current_period_start: datetime = Field(..., description="Inicio del ciclo de facturación actual")
    current_period_end: datetime | None = Field(default=None, description="Fin del ciclo de facturación actual")

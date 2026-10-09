from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from app.booking.entity.booking import BookingStatusEnum
from app.booking.entity.payment import PaymentStatusEnum
from app.booking.entity.saas_subscription import SubscriptionStatusEnum


# DTO para crear una reserva de cupo (CU-06)
class BookingCreateDTO(BaseModel):
    experience_id: int
    quantity: int = 1


# DTO para detalle de entrada/ticket con código QR
class TicketDTO(BaseModel):
    id: int
    ticket_code: str
    qr_payload: str
    is_used: bool
    used_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# DTO de respuesta para reserva
class BookingResponseDTO(BaseModel):
    id: int
    user_id: int
    experience_id: int
    quantity: int
    total_amount: float
    platform_fee: float
    host_payout: float
    status: BookingStatusEnum
    created_at: datetime
    tickets: List[TicketDTO] = []

    class Config:
        from_attributes = True


# DTO para iniciar sesión de pago Stripe Checkout
class CheckoutSessionDTO(BaseModel):
    booking_id: int
    checkout_url: str
    stripe_session_id: str


# DTO para payload de webhook entrante de Stripe
class StripeWebhookDTO(BaseModel):
    event_type: str
    data: Dict[str, Any]


# DTO para catálogo de planes SaaS Pro (CU-14)
class SaaSPlanDTO(BaseModel):
    id: int
    name: str
    monthly_price: float
    features_included: Dict[str, Any]
    stripe_price_id: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


# DTO para suscribirse a un plan SaaS
class SubscriptionCreateDTO(BaseModel):
    plan_id: int


# DTO de respuesta de suscripción
class SubscriptionResponseDTO(BaseModel):
    id: int
    user_id: int
    plan_id: int
    stripe_subscription_id: Optional[str] = None
    status: SubscriptionStatusEnum
    current_period_start: datetime
    current_period_end: Optional[datetime] = None

    class Config:
        from_attributes = True

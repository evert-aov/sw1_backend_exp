from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.booking.dto.booking_dto import (
    SaaSPlanDTO,
    SubscriptionCreateDTO,
    SubscriptionResponseDTO,
)
from app.booking.service.stripe_service import StripeService

subscription_router = APIRouter(prefix="/subscriptions", tags=["SaaS Subscriptions Controller (CU-14)"])


@subscription_router.get("/plans", response_model=List[SaaSPlanDTO])
def list_plans(db: Session = Depends(get_db)):
    # Firma de endpoint para listar planes disponibles
    pass


@subscription_router.post("/subscribe", response_model=SubscriptionResponseDTO, status_code=status.HTTP_201_CREATED)
def subscribe_to_plan(dto: SubscriptionCreateDTO, db: Session = Depends(get_db)):
    # Firma de endpoint para suscribirse a Plan Pro
    pass

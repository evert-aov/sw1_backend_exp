from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.auth.entity.user import User
from app.booking.dto.booking_dto import (
    SaaSPlanDTO,
    SubscriptionCreateDTO,
    SubscriptionResponseDTO,
)
from app.booking.service.stripe_service import StripeService
from app.core.database import get_db
from app.core.security import get_current_active_user

subscription_router = APIRouter(
    prefix="/subscriptions",
    tags=["SaaS Subscriptions Controller (CU-14)"],
)


@subscription_router.get(
    "/plans",
    response_model=list[SaaSPlanDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar planes de suscripción SaaS Pro disponibles (CU-14 / HU-23)",
    description="Consulta el catálogo de planes SaaS recurrentes para anfitriones y establecimientos.",
)
def list_plans(
    _db: Annotated[Session, Depends(get_db)],
) -> list[SaaSPlanDTO]:
    """
    Lista los planes de suscripción SaaS Pro disponibles en la plataforma (Sprint 2/4 - CU-14).

    Args:
        _db (Session): Sesión activa de base de datos.

    Returns:
        list[SaaSPlanDTO]: Lista de planes SaaS configurados.
    """
    return []


@subscription_router.post(
    "/subscribe",
    response_model=SubscriptionResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Suscribirse a un Plan Pro SaaS (CU-14 / HU-23)",
    description="Inicia la suscripción recurrente de un anfitrión o establecimiento a un plan Pro.",
)
def subscribe_to_plan(
    dto: SubscriptionCreateDTO,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SubscriptionResponseDTO:
    """
    Registra la suscripción de un usuario a un plan SaaS Pro mediante Stripe Billing (CU-14).

    Args:
        dto (SubscriptionCreateDTO): Datos del plan seleccionado.
        db (Session): Sesión activa de base de datos.
        current_user (User): Usuario autenticado en sesión.

    Returns:
        SubscriptionResponseDTO: Estado de la suscripción creada.
    """
    service = StripeService(db)
    return service.create_saas_subscription(user_id=current_user.id, plan_id=dto.plan_id)

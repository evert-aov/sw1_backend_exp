from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.auth.entity.user import User
from app.core.database import get_db
from app.core.security import RoleChecker
from app.live.dto.age_distribution_dto import AgeDistributionDTO
from app.live.service.age_estimation_service import (
    AgeDistributionService,
    get_age_distribution_service,
)

age_distribution_router = APIRouter(
    prefix="/live",
    tags=["Live Audience Age Controller (HU-16)"],
)


@age_distribution_router.get(
    "/sessions/{session_id}/age-distribution",
    response_model=AgeDistributionDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar la distribución etaria del público en vivo (HU-16)",
    description=(
        "Devuelve el porcentaje de rostros clasificados en cada rango etario (`YOUTH` <18, "
        "`YOUNG_ADULT` 18-30, `ADULT` 31-50, `SENIOR` >50) dentro de la ventana deslizante en memoria "
        "de la sesión. Solo el anfitrión propietario de la sesión puede consultarla (`HOST`, con `VENUE` "
        "como compatibilidad). Los fotogramas se procesan en RAM y nunca se almacenan; la respuesta solo "
        "contiene conteos agregados. `detections_count` acumula rostros por fotograma y no representa "
        "personas únicas. Si no hay modelo de edad registrado, `estimator_configured` es `false` y los "
        "porcentajes permanecen en cero."
    ),
    response_description="Última distribución porcentual de rangos etarios de la sesión",
)
def get_age_distribution(
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["HOST", "VENUE"]))],
    service: Annotated[AgeDistributionService, Depends(get_age_distribution_service)],
) -> AgeDistributionDTO:
    """
    Consulta la última distribución etaria de una sesión en vivo del anfitrión autenticado (HU-16).

    Args:
        session_id (str): ID (UUID) de la sesión en vivo.
        db (Session): Sesión de base de datos inyectada para verificar la propiedad.
        current_user (User): Usuario autenticado con rol `HOST` o `VENUE`.
        service (AgeDistributionService): Agregador en memoria compartido por el proceso.

    Returns:
        AgeDistributionDTO: Porcentajes por rango etario, rango dominante y tamaño de la ventana.

    Raises:
        HTTPException (401): Si no se envía un JWT válido.
        HTTPException (403): Si el usuario no tiene rol de anfitrión o la sesión es de otro anfitrión.
        HTTPException (404): Si la sesión en vivo no existe.
        HTTPException (422): Si el ID no es un UUID válido.
    """
    return service.distribution_for_host(db, session_id, current_user.id)

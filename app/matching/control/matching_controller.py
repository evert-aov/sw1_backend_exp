from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.auth.entity.user import User
from app.core.database import get_db
from app.core.security import get_current_active_user, RoleChecker
from app.matching.dto.matching_dto import (
    MatchingApplicationDTO,
    MatchingGroupResponseDTO,
)
from app.matching.service.matching_service import MatchingAlgorithmService

matching_router = APIRouter(prefix="/matching", tags=["Matching Controller (CU-06)"])


@matching_router.post(
    "/apply",
    response_model=MatchingGroupResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Postular a un grupo de matching dinámico por intereses (CU-06 / HU-09)",
    description="Agrupa participantes compatibles para alcanzar el quórum mínimo de una experiencia.",
)
def apply_to_matching_group(
    dto: MatchingApplicationDTO,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["ATTENDEE"]))],
) -> MatchingGroupResponseDTO:
    """
    Registra la postulación de un asistente a un grupo dinámico de matching (Sprint 2 - CU-06).

    Args:
        dto (MatchingApplicationDTO): ID de la experiencia objetivo.
        db (Session): Sesión activa de base de datos.
        current_user (User): Usuario autenticado en sesión.

    Returns:
        MatchingGroupResponseDTO: Estado actualizado del grupo de matching y quórum.
    """
    service = MatchingAlgorithmService(db)
    return service.apply_for_matching(user_id=current_user.id, dto=dto)


@matching_router.get(
    "/group/{experience_id}",
    response_model=MatchingGroupResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar estado de quórum de un grupo de matching (CU-06 / HU-08)",
    description="Obtiene el progreso actual de participantes postulados frente al cupo mínimo requerido.",
)
def get_matching_group_status(
    experience_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["ATTENDEE"]))],
) -> MatchingGroupResponseDTO:
    """
    Consulta el avance del quórum mínimo de un grupo de matching asociado a una experiencia (CU-06).

    Args:
        experience_id (str): ID de la experiencia.
        db (Session): Sesión activa de base de datos.
        current_user (User): Usuario autenticado en sesión.

    Returns:
        MatchingGroupResponseDTO: Información del grupo de matching.
    """
    service = MatchingAlgorithmService(db)
    return service.get_group_status(experience_id, current_user.id)


@matching_router.delete("/group/{experience_id}/membership")
def leave_matching_group(
    experience_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["ATTENDEE"]))],
):
    """Retira la postulación propia sin afectar una compra ya confirmada."""
    return MatchingAlgorithmService(db).leave_group(experience_id, current_user.id)

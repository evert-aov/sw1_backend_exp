from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth.entity.user import User
from app.core.database import get_db
from app.core.security import get_current_active_user
from app.matching.dto.matching_dto import (
    ExperienceRecommendationDTO,
    MatchingApplicationDTO,
    MatchingGroupResponseDTO,
)
from app.matching.service.matching_service import (
    ExperienceRecommendationService,
    MatchingAlgorithmService,
)

matching_router = APIRouter(prefix="/matching", tags=["Matching Controller (CU-07)"])


@matching_router.get(
    "/recommendations",
    response_model=list[ExperienceRecommendationDTO],
    status_code=status.HTTP_200_OK,
    summary="Recomendar experiencias según intereses y proximidad",
    description=(
        "Devuelve experiencias futuras, abiertas o confirmadas y con cupos disponibles. "
        "Ordena primero por afinidad temática y después por distancia y fecha. "
        "La ubicación solo se usa en esta petición; no hay radio máximo predeterminado. "
        "`radius_km` aplica un límite solo cuando el cliente lo solicita expresamente. "
        "Una recomendación no reserva un cupo ni expresa probabilidad de asistencia."
    ),
)
def get_personalized_recommendations(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    latitude: Annotated[float | None, Query(ge=-90.0, le=90.0)] = None,
    longitude: Annotated[float | None, Query(ge=-180.0, le=180.0)] = None,
    radius_km: Annotated[float | None, Query(gt=0.0)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[ExperienceRecommendationDTO]:
    """Consulta experiencias afines para el usuario autenticado sin reservar cupos.

    Args:
        current_user (User): Usuario cuyos intereses se usan para ordenar resultados.
        db (Session): Sesión de base de datos de la petición.
        latitude (float | None): Latitud opcional de la ubicación consultada.
        longitude (float | None): Longitud opcional de la ubicación consultada.
        radius_km (float | None): Radio máximo opcional en kilómetros.
        limit (int): Cantidad máxima de recomendaciones, entre 1 y 50.

    Returns:
        list[ExperienceRecommendationDTO]: Experiencias ordenadas por afinidad,
        distancia cuando aplica y fecha.

    Raises:
        HTTPException: Si las coordenadas, el radio o el límite son inválidos,
        o si el usuario no existe.
    """
    service = ExperienceRecommendationService(db)
    return service.recommend_experiences(
        user_id=current_user.id,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        limit=limit,
    )


@matching_router.post(
    "/apply",
    response_model=MatchingGroupResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Postular a un grupo de matching dinámico por intereses (CU-07 / HU-09)",
    description="Agrupa participantes compatibles para alcanzar el quórum mínimo de una experiencia.",
)
def apply_to_matching_group(
    dto: MatchingApplicationDTO,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> MatchingGroupResponseDTO:
    """
    Registra la postulación de un asistente a un grupo dinámico de matching (Sprint 2 - CU-07).

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
    "/{experience_id}",
    response_model=MatchingGroupResponseDTO,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@matching_router.get(
    "/group/{experience_id}",
    response_model=MatchingGroupResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar el grupo al que se postuló el usuario",
    description=(
        "Consulta sin modificar datos el grupo del usuario autenticado. "
        "current_members cuenta postulaciones; el quórum solo se alcanza con reservas pagadas."
    ),
)
def get_matching_group_status(
    experience_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> MatchingGroupResponseDTO:
    """Consulta el grupo de una experiencia al que se postuló el usuario.

    Args:
        experience_id (str): Identificador de la experiencia consultada.
        db (Session): Sesión de base de datos de la petición.
        current_user (User): Usuario cuya postulación se consulta.

    Returns:
        MatchingGroupResponseDTO: Estado del grupo y quórum pagado de la experiencia.

    Raises:
        HTTPException: Si no existe la experiencia o la postulación del usuario.
    """
    service = MatchingAlgorithmService(db)
    return service.get_group_status(
        user_id=current_user.id, experience_id=experience_id
    )


@matching_router.post(
    "/{experience_id}/apply",
    response_model=MatchingGroupResponseDTO,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def apply_to_matching_group_for_experience(
    experience_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> MatchingGroupResponseDTO:
    """Registra una postulación mediante la ruta legada de una experiencia.

    Args:
        experience_id (str): Identificador de la experiencia objetivo.
        db (Session): Sesión de base de datos de la petición.
        current_user (User): Asistente que solicita unirse al grupo.

    Returns:
        MatchingGroupResponseDTO: Grupo asignado y su estado actual.

    Raises:
        HTTPException: Si la experiencia o el usuario no son elegibles.
    """
    service = MatchingAlgorithmService(db)
    return service.apply_for_matching(
        user_id=current_user.id,
        dto=MatchingApplicationDTO(experience_id=experience_id),
    )


@matching_router.get(
    "/experiences/{experience_id}/groups",
    response_model=list[MatchingGroupResponseDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar grupos de matching de una experiencia",
    description=(
        "Una experiencia puede tener varios grupos. Los miembros representan interés expresado, "
        "no reservas pagadas ni participantes confirmados."
    ),
)
def list_experience_matching_groups(
    experience_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[MatchingGroupResponseDTO]:
    """Lista los grupos de postulación de una experiencia.

    Args:
        experience_id (str): Identificador de la experiencia consultada.
        db (Session): Sesión de base de datos de la petición.
        current_user (User): Usuario autenticado que realiza la consulta.

    Returns:
        list[MatchingGroupResponseDTO]: Grupos con cantidad de postulados y quórum pagado.

    Raises:
        HTTPException: Si la experiencia no existe.
    """
    service = MatchingAlgorithmService(db)
    return service.get_experience_groups(experience_id)

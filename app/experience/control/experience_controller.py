from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.auth.entity.user import User
from app.core.database import get_db
from app.core.security import RoleChecker, get_current_active_user
from app.experience.dto.experience_dto import (
    CatalogResponseDTO,
    ExperienceCreateDTO,
    ExperienceFilterDTO,
    ExperienceResponseDTO,
    ExperienceUpdateDTO,
)
from app.experience.entity.experience import ExperienceStatusEnum
from app.experience.service.experience_service import ExperienceService

experience_router = APIRouter(
    prefix="/experiences",
    tags=["Experience Controller (CU-04, CU-05)"],
)


@experience_router.post(
    "",
    response_model=ExperienceResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Publicar una nueva experiencia con aforo y precio (CU-04 / HU-04, HU-07)",
    description=(
        "Permite a un anfitrión (`HOST`), establecimiento (`VENUE`) o administrador (`ADMIN`) publicar un nuevo "
        "evento definiendo categoría, local físico, modalidad (`IN_PERSON`, `VIRTUAL`, `HYBRID`), cupo mínimo (quórum), "
        "cupo máximo y precio, calculando automáticamente el desglose de comisiones e ingresos proyectados."
    ),
    response_description="Experiencia publicada con desglose de comisiones",
)
def create_experience(
    dto: ExperienceCreateDTO,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["HOST", "VENUE", "ADMIN"]))],
) -> ExperienceResponseDTO:
    """
    Publica una nueva experiencia en el catálogo validando reglas de negocio de aforo, fecha futura
    y disponibilidad horaria del establecimiento (CU-04: Publicar Experiencia).

    Args:
        dto (ExperienceCreateDTO): Datos del evento, capacidades y precio.
        db (Session): Sesión de base de datos inyectada.
        current_user (User): Usuario autenticado con rol `HOST`, `VENUE` o `ADMIN`.

    Returns:
        ExperienceResponseDTO: Experiencia creada con proyecciones financieras de comisiones.
    """
    service = ExperienceService(db)
    return service.create_experience(host_id=current_user.id, dto=dto)


@experience_router.get(
    "/catalog",
    response_model=CatalogResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Explorar y filtrar catálogo de experiencias por geolocalización (CU-05 / HU-05)",
    description=(
        "Permite a usuarios web y móviles explorar experiencias abiertas o confirmadas filtrando por proximidad "
        "geográfica (`latitude`, `longitude`, `radius_km` mediante fórmula de Haversine), zona urbana, categoría, "
        "modalidad, rango de fechas, precio máximo y búsqueda de texto."
    ),
    response_description="Catálogo paginado de experiencias filtradas",
)
def search_catalog(
    filters: Annotated[ExperienceFilterDTO, Depends()],
    db: Annotated[Session, Depends(get_db)],
) -> CatalogResponseDTO:
    """
    Explora y filtra el catálogo público de experiencias para clientes web y móviles (CU-05).

    Args:
        filters (ExperienceFilterDTO): Criterios de búsqueda, geolocalización GPS y paginación.
        db (Session): Sesión de base de datos inyectada.

    Returns:
        CatalogResponseDTO: Resultado paginado con el listado de experiencias y metadatos de paginación.
    """
    service = ExperienceService(db)
    return service.search_catalog(filters)


@experience_router.get(
    "/me/hosted",
    response_model=list[ExperienceResponseDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar mis experiencias publicadas como anfitrión (CU-04 / HU-07)",
    description=(
        "Devuelve la lista de experiencias creadas por el anfitrión autenticado junto con el estado de quórum "
        "y el desglose financiero de ingresos brutos/netos y comisiones."
    ),
    response_description="Lista de experiencias del anfitrión actual",
)
def get_my_hosted_experiences(
    status_filter: Annotated[
        ExperienceStatusEnum | None,
        Query(alias="status", description="Filtrar opcionalmente por estado de la experiencia"),
    ] = None,
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[User, Depends(get_current_active_user)] = None,  # type: ignore[assignment]
) -> list[ExperienceResponseDTO]:
    """
    Consulta todas las experiencias publicadas por el usuario autenticado (CU-04).

    Args:
        status_filter (ExperienceStatusEnum | None): Estado opcional para filtrar (`OPEN`, `CONFIRMED`, `CANCELLED`, etc.).
        db (Session): Sesión de base de datos inyectada.
        current_user (User): Usuario autenticado en sesión.

    Returns:
        list[ExperienceResponseDTO]: Lista de experiencias del anfitrión.
    """
    service = ExperienceService(db)
    return service.get_my_hosted_experiences(host_id=current_user.id, status=status_filter)


@experience_router.get(
    "/{experience_id}",
    response_model=ExperienceResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar detalle de una experiencia por ID (CU-04, CU-05)",
    description="Obtiene toda la información de una experiencia específica, incluyendo local, coordenadas, cupos y precio.",
    response_description="Detalle completo de la experiencia",
)
def get_experience_detail(
    experience_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ExperienceResponseDTO:
    """
    Recupera el detalle completo de una experiencia específica por su ID (UUID) (CU-04, CU-05).

    Args:
        experience_id (str): Identificador único de la experiencia.
        db (Session): Sesión de base de datos inyectada.

    Returns:
        ExperienceResponseDTO: Datos detallados de la experiencia.
    """
    service = ExperienceService(db)
    return service.get_experience_by_id(experience_id)


@experience_router.put(
    "/{experience_id}",
    response_model=ExperienceResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Actualizar una experiencia publicada (CU-04 / HU-04)",
    description=(
        "Permite al anfitrión propietario modificar los datos de su experiencia, validando que no se reduzca "
        "el aforo por debajo de las reservas actuales ni se cambie el precio si ya existen entradas adquiridas."
    ),
    response_description="Experiencia actualizada",
)
def update_experience(
    experience_id: str,
    dto: ExperienceUpdateDTO,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ExperienceResponseDTO:
    """
    Actualiza una experiencia existente perteneciente al anfitrión autenticado (CU-04).

    Args:
        experience_id (str): ID de la experiencia a modificar.
        dto (ExperienceUpdateDTO): Campos a actualizar.
        db (Session): Sesión de base de datos inyectada.
        current_user (User): Usuario autenticado propietario del evento.

    Returns:
        ExperienceResponseDTO: Experiencia actualizada.
    """
    service = ExperienceService(db)
    return service.update_experience(experience_id=experience_id, host_id=current_user.id, dto=dto)


@experience_router.patch(
    "/{experience_id}/cancel",
    response_model=ExperienceResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Cancelar una experiencia publicada (CU-04)",
    description="Cambia el estado de la experiencia a `CANCELLED`. Solo puede ser ejecutado por su anfitrión creador.",
    response_description="Experiencia cancelada exitosamente",
)
def cancel_experience(
    experience_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ExperienceResponseDTO:
    """
    Cancela una experiencia activa cambiando su estado a `CANCELLED` (CU-04).

    Args:
        experience_id (str): ID de la experiencia a cancelar.
        db (Session): Sesión de base de datos inyectada.
        current_user (User): Usuario autenticado propietario del evento.

    Returns:
        ExperienceResponseDTO: Experiencia con estado actualizado a `CANCELLED`.
    """
    service = ExperienceService(db)
    return service.cancel_experience(experience_id=experience_id, host_id=current_user.id)

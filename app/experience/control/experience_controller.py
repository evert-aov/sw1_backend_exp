from __future__ import annotations

from typing import Annotated
from decimal import Decimal
from fastapi import APIRouter, Depends, Header, Query, status
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
    HostedExperienceDTO,
    CommissionQuoteDTO,
)
from app.core.pricing import quote_price
from app.experience.entity.experience import ExperienceStatusEnum
from app.experience.service.experience_service import ExperienceService

experience_router = APIRouter(
    prefix="/experiences",
    tags=["Experience Controller (CU-03, CU-04)"],
)


@experience_router.get("/commission-quote", response_model=CommissionQuoteDTO)
def commission_quote(
    price: Annotated[Decimal, Query(ge=0, le=10000000)],
) -> CommissionQuoteDTO:
    """Devuelve la misma política monetaria aplicada al guardar y reservar experiencias."""
    quote = quote_price(price)
    return CommissionQuoteDTO(
        unit_price=float(quote.unit_price),
        commission_rate=float(quote.commission_rate),
        fee_per_ticket=float(quote.fee_per_ticket),
        net_per_ticket=float(quote.net_per_ticket),
        tier=quote.tier,
    )


@experience_router.post(
    "",
    response_model=ExperienceResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Publicar una nueva experiencia con aforo y precio (CU-03 / HU-04, HU-07)",
    description=(
        "Permite a un anfitrión (`HOST`, con `VENUE` como compatibilidad) publicar un nuevo "
        "evento definiendo categoría, local físico, modalidad (`IN_PERSON`, `VIRTUAL`, `HYBRID`), cupo mínimo (quórum), "
        "cupo máximo y precio, calculando automáticamente el desglose de comisiones e ingresos proyectados."
    ),
    response_description="Experiencia publicada con desglose de comisiones",
)
def create_experience(
    dto: ExperienceCreateDTO,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["HOST", "VENUE"]))],
) -> ExperienceResponseDTO:
    """
    Publica una nueva experiencia en el catálogo validando reglas de negocio de aforo, fecha futura
    y disponibilidad horaria del establecimiento (CU-03: Publicar Experiencia).

    Args:
        dto (ExperienceCreateDTO): Datos del evento, capacidades y precio.
        db (Session): Sesión de base de datos inyectada.
        current_user (User): Usuario autenticado con rol `HOST` o `VENUE`.

    Returns:
        ExperienceResponseDTO: Experiencia creada con proyecciones financieras de comisiones.
    """
    service = ExperienceService(db)
    return service.create_experience(host_id=current_user.id, dto=dto)


@experience_router.get(
    "/catalog",
    response_model=CatalogResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Explorar y filtrar catálogo de experiencias por geolocalización (CU-04 / HU-05)",
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
    search_session: Annotated[
        str | None, Header(alias="X-Search-Session", min_length=8, max_length=64)
    ] = None,
) -> CatalogResponseDTO:
    """
    Explora y filtra el catálogo público de experiencias para clientes web y móviles (CU-04).

    Args:
        filters (ExperienceFilterDTO): Criterios de búsqueda, geolocalización GPS y paginación.
        db (Session): Sesión de base de datos inyectada.

    Returns:
        CatalogResponseDTO: Resultado paginado con el listado de experiencias y metadatos de paginación.
    """
    service = ExperienceService(db)
    return service.search_catalog(filters, search_session)


@experience_router.get(
    "/me/hosted",
    response_model=list[HostedExperienceDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar mis experiencias publicadas como anfitrión (CU-03 / HU-07)",
    description=(
        "Devuelve la lista de experiencias creadas por el anfitrión autenticado junto con el estado de quórum "
        "y el desglose financiero de ingresos brutos/netos y comisiones."
    ),
    response_description="Lista de experiencias del anfitrión actual",
)
def get_my_hosted_experiences(
    status_filter: Annotated[
        ExperienceStatusEnum | None,
        Query(
            alias="status",
            description="Filtrar opcionalmente por estado de la experiencia",
        ),
    ] = None,
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
    current_user: Annotated[User, Depends(RoleChecker(["HOST", "VENUE"]))] = None,  # type: ignore[assignment]
) -> list[HostedExperienceDTO]:
    """
    Consulta todas las experiencias publicadas por el usuario autenticado (CU-03).

    Args:
        status_filter (ExperienceStatusEnum | None): Estado opcional para filtrar (`OPEN`, `CONFIRMED`, `CANCELLED`, etc.).
        db (Session): Sesión de base de datos inyectada.
        current_user (User): Usuario autenticado en sesión.

    Returns:
        list[ExperienceResponseDTO]: Lista de experiencias del anfitrión.
    """
    service = ExperienceService(db)
    return service.get_my_hosted_experiences(
        host_id=current_user.id, status=status_filter
    )


@experience_router.get(
    "/{experience_id}",
    response_model=ExperienceResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar detalle de una experiencia por ID (CU-03, CU-04)",
    description="Obtiene toda la información de una experiencia específica, incluyendo local, coordenadas, cupos y precio.",
    response_description="Detalle completo de la experiencia",
)
def get_experience_detail(
    experience_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ExperienceResponseDTO:
    """
    Recupera el detalle completo de una experiencia específica por su ID (UUID) (CU-03, CU-04).

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
    summary="Actualizar una experiencia publicada (CU-03 / HU-04)",
    description=(
        "Permite al anfitrión propietario modificar una experiencia futura sin asistentes, "
        "reservas vigentes ni postulaciones."
    ),
    response_description="Experiencia actualizada",
)
def update_experience(
    experience_id: str,
    dto: ExperienceUpdateDTO,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["HOST", "VENUE"]))],
) -> ExperienceResponseDTO:
    """
    Actualiza una experiencia existente perteneciente al anfitrión autenticado (CU-03).

    Args:
        experience_id (str): ID de la experiencia a modificar.
        dto (ExperienceUpdateDTO): Campos a actualizar.
        db (Session): Sesión de base de datos inyectada.
        current_user (User): Usuario autenticado propietario del evento.

    Returns:
        ExperienceResponseDTO: Experiencia actualizada.
    """
    service = ExperienceService(db)
    return service.update_experience(
        experience_id=experience_id, host_id=current_user.id, dto=dto
    )


@experience_router.patch(
    "/{experience_id}/cancel",
    response_model=ExperienceResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Cancelar una experiencia publicada (CU-03)",
    description="Cambia el estado de la experiencia a `CANCELLED`. Solo puede ser ejecutado por su anfitrión creador.",
    response_description="Experiencia cancelada exitosamente",
)
def cancel_experience(
    experience_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["HOST", "VENUE"]))],
) -> ExperienceResponseDTO:
    """
    Cancela una experiencia activa cambiando su estado a `CANCELLED` (CU-03).

    Args:
        experience_id (str): ID de la experiencia a cancelar.
        db (Session): Sesión de base de datos inyectada.
        current_user (User): Usuario autenticado propietario del evento.

    Returns:
        ExperienceResponseDTO: Experiencia con estado actualizado a `CANCELLED`.
    """
    service = ExperienceService(db)
    return service.cancel_experience(
        experience_id=experience_id, host_id=current_user.id
    )


@experience_router.get("/me/hosted/{experience_id}", response_model=HostedExperienceDTO)
def get_my_experience(
    experience_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["HOST", "VENUE"]))],
):
    return ExperienceService(db).get_my_hosted_experience(
        experience_id, current_user.id
    )


@experience_router.delete("/{experience_id}", status_code=204)
def delete_my_experience(
    experience_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["HOST", "VENUE"]))],
) -> None:
    ExperienceService(db).delete_experience(experience_id, current_user.id)

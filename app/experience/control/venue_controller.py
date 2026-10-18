from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.auth.entity.user import User
from app.core.database import get_db
from app.core.security import RoleChecker
from app.experience.dto.experience_dto import VenueCreateDTO, VenueDTO
from app.experience.service.venue_service import VenueService

venue_router = APIRouter(prefix="/venues", tags=["Venues Controller"])


@venue_router.get(
    "",
    response_model=list[VenueDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar establecimientos físicos geolocalizados (CU-04, CU-05)",
    description="Consulta la lista de locales y establecimientos registrados, permitiendo filtrar opcionalmente por zona urbana.",
    response_description="Lista de establecimientos físicos",
)
def list_venues(
    zone: Annotated[str | None, Query(description="Filtrar establecimientos por zona urbana")] = None,
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
) -> list[VenueDTO]:
    """
    Lista todos los establecimientos físicos disponibles o filtra por zona urbana.

    Args:
        zone (str | None): Zona urbana opcional (ej. 'Equipetrol', 'Manzana 40').
        db (Session): Sesión de base de datos inyectada.

    Returns:
        list[VenueDTO]: Lista de establecimientos con sus coordenadas y capacidad máxima.
    """
    service = VenueService(db)
    return service.get_all_venues(zone=zone)


@venue_router.get(
    "/{venue_id}",
    response_model=VenueDTO,
    status_code=status.HTTP_200_OK,
    summary="Obtener detalles de un establecimiento por ID",
    description="Recupera la información detallada, dirección, capacidad máxima y coordenadas GPS de un local por su ID.",
    response_description="Detalle del establecimiento físico",
)
def get_venue(
    venue_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> VenueDTO:
    """
    Obtiene los detalles de un establecimiento físico por su identificador único.

    Args:
        venue_id (int): ID del establecimiento.
        db (Session): Sesión de base de datos inyectada.

    Returns:
        VenueDTO: Datos completos del establecimiento.
    """
    service = VenueService(db)
    return service.get_venue_by_id(venue_id)


@venue_router.post(
    "",
    response_model=VenueDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un nuevo establecimiento físico (CU-04)",
    description="Permite a usuarios con rol `VENUE`, `HOST` o `ADMIN` dar de alta un nuevo espacio físico geolocalizado.",
    response_description="Establecimiento registrado exitosamente",
)
def create_venue(
    dto: VenueCreateDTO,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["VENUE", "HOST", "ADMIN"]))],
) -> VenueDTO:
    """
    Registra un nuevo establecimiento comercial asociado al usuario autenticado.

    Args:
        dto (VenueCreateDTO): Nombre, dirección, zona, coordenadas GPS y capacidad máxima del local.
        db (Session): Sesión de base de datos inyectada.
        current_user (User): Usuario autenticado con rol `VENUE`, `HOST` o `ADMIN`.

    Returns:
        VenueDTO: Establecimiento creado con su ID asignado.
    """
    service = VenueService(db)
    return service.register_venue(current_user.id, dto)

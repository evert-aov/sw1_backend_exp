from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.experience.dto.experience_dto import VenueCreateDTO, VenueDTO
from app.experience.mapper.venue_mapper import VenueMapper
from app.experience.repository.venue_repository import VenueRepository


class VenueService:
    """
    Servicio de negocio para la administración y consulta de establecimientos y locales comerciales
    geolocalizados donde se desarrollan experiencias presenciales o híbridas (CU-04, CU-05).
    """

    def __init__(self, db: Session) -> None:
        """
        Inicializa el servicio de establecimientos con su repositorio colaborador.

        Args:
            db (Session): Sesión activa de SQLAlchemy.
        """
        self.db = db
        self.venue_repo = VenueRepository(db)

    def get_all_venues(self, zone: str | None = None) -> list[VenueDTO]:
        """
        Obtiene la lista de establecimientos registrados, permitiendo filtrar opcionalmente por zona urbana.

        Args:
            zone (str | None): Zona urbana opcional para filtrar (ej. 'Equipetrol').

        Returns:
            list[VenueDTO]: Lista de establecimientos encontrados.
        """
        if zone:
            venues = self.venue_repo.get_by_zone(zone)
        else:
            venues = self.venue_repo.get_all()
        return [VenueMapper.to_dto(v) for v in venues]

    def get_venue_by_id(self, venue_id: str) -> VenueDTO:
        """
        Consulta el detalle de un establecimiento específico por su ID (UUID).

        Args:
            venue_id (str): ID único del establecimiento (UUID).

        Returns:
            VenueDTO: Datos del establecimiento.

        Raises:
            HTTPException (404): Si el establecimiento no existe.
        """
        venue = self.venue_repo.get_by_id(venue_id)
        if not venue:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"El establecimiento con ID {venue_id} no fue encontrado",
            )
        return VenueMapper.to_dto(venue)

    def register_venue(self, owner_id: str | None, dto: VenueCreateDTO) -> VenueDTO:
        """
        Registra un nuevo establecimiento comercial asociado al usuario autenticado (`owner_id`).

        Args:
            owner_id (str | None): ID del usuario propietario o anfitrión que registra el local (UUID).
            dto (VenueCreateDTO): Datos físicos y coordenadas geográficas del establecimiento.

        Returns:
            VenueDTO: Establecimiento registrado y persistido.
        """
        venue = VenueMapper.to_entity(dto, owner_id)
        created = self.venue_repo.create(venue)
        return VenueMapper.to_dto(created)

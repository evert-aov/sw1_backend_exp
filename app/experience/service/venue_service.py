from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.experience.dto.experience_dto import VenueCreateDTO, VenueDTO
from app.experience.mapper.venue_mapper import VenueMapper
from app.experience.repository.venue_repository import VenueRepository
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.experience.entity.experience import Experience, ExperienceStatusEnum
from app.booking.entity.booking import Booking, BookingStatusEnum
from app.matching.entity.matching_member import MatchingMember
from app.matching.entity.matching_group import MatchingGroup


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

    def get_my_venues(self, owner_id: str) -> list[VenueDTO]:
        return [
            VenueMapper.to_dto(venue)
            for venue in self.venue_repo.get_by_owner(owner_id)
        ]

    def update_my_venue(
        self, venue_id: str, owner_id: str, dto: VenueCreateDTO
    ) -> VenueDTO:
        """Bloquea lugar→experiencias; una reserva concurrente no elude la validación."""
        try:
            venue = self.venue_repo.get_by_id(venue_id, for_update=True)
            if not venue or venue.owner_id != owner_id:
                raise HTTPException(
                    status_code=404, detail="Lugar propio no encontrado"
                )
            experiences = (
                self.db.query(Experience)
                .filter(Experience.venue_id == venue.id)
                .order_by(Experience.id)
                .with_for_update(of=Experience)
                .all()
            )
            now = datetime.now(timezone.utc)
            for experience in experiences:
                if experience.status in {
                    ExperienceStatusEnum.CANCELLED,
                    ExperienceStatusEnum.FINISHED,
                }:
                    continue
                event_date = (
                    experience.event_date.replace(tzinfo=timezone.utc)
                    if experience.event_date.tzinfo is None
                    else experience.event_date
                )
                if (
                    experience.status != ExperienceStatusEnum.LIVE
                    and event_date
                    + timedelta(minutes=experience.duration_minutes or 120)
                    <= now
                ):
                    continue
                active = self.db.scalar(
                    select(Booking.id)
                    .where(
                        Booking.experience_id == experience.id,
                        (Booking.status == BookingStatusEnum.PAID)
                        | (
                            (Booking.status == BookingStatusEnum.PENDING)
                            & (
                                (Booking.expires_at.is_(None))
                                | (Booking.expires_at > now)
                            )
                        ),
                    )
                    .limit(1)
                )
                members = self.db.scalar(
                    select(MatchingMember.id)
                    .join(MatchingGroup)
                    .where(MatchingGroup.experience_id == experience.id)
                    .limit(1)
                )
                if experience.reserved_slots or active or members:
                    raise HTTPException(
                        status_code=409,
                        detail="El lugar tiene experiencias con asistentes o reservas vigentes; no se puede modificar",
                    )
                if (
                    experience.status
                    in {
                        ExperienceStatusEnum.OPEN,
                        ExperienceStatusEnum.CONFIRMED,
                        ExperienceStatusEnum.LIVE,
                    }
                    and (dto.max_capacity or 50) < experience.max_capacity
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="La capacidad del lugar no puede ser inferior al aforo de sus experiencias activas",
                    )
            updated = VenueMapper.to_entity(dto, owner_id)
            for name in type(dto).model_fields:
                setattr(venue, name, getattr(updated, name))
            self.db.commit()
            self.db.refresh(venue)
            return VenueMapper.to_dto(venue)
        except Exception:
            self.db.rollback()
            raise

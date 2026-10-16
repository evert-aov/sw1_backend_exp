import math
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.experience.mapper.experience_mapper import ExperienceMapper
from app.experience.dto.experience_dto import (
    ExperienceCreateDTO,
    ExperienceUpdateDTO,
    ExperienceFilterDTO,
    ExperienceResponseDTO,
    CatalogResponseDTO,
)
from app.experience.entity.experience import Experience, ModalityEnum, ExperienceStatusEnum
from app.experience.repository.experience_repository import ExperienceRepository
from app.experience.repository.category_repository import CategoryRepository
from app.experience.repository.venue_repository import VenueRepository


# Servicio para gestión de experiencias, cálculo de aforos y validación de modalidades (CU-03, CU-04, CU-05)
class ExperienceService:
    def __init__(self, db: Session):
        self.db = db
        self.experience_repo = ExperienceRepository(db)
        self.category_repo = CategoryRepository(db)
        self.venue_repo = VenueRepository(db)

    def _ensure_utc(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _to_database_datetime(self, dt: datetime) -> datetime:
        return self._ensure_utc(dt).replace(tzinfo=None)

    def _to_response_dto(self, exp: Experience) -> ExperienceResponseDTO:
        return ExperienceMapper.to_response_dto(exp)

    def create_experience(self, host_id: int, dto: ExperienceCreateDTO) -> ExperienceResponseDTO:
        # 1. Validar categoría
        category = self.category_repo.get_by_id(dto.category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"La categoría con ID {dto.category_id} no existe",
            )

        # 2. Validar capacidades
        if dto.min_capacity <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El aforo mínimo (quórum) debe ser mayor a 0",
            )
        if dto.max_capacity < dto.min_capacity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El cupo máximo no puede ser inferior al aforo mínimo",
            )

        # 3. Validar fecha a futuro
        now = datetime.now(timezone.utc)
        event_dt = self._ensure_utc(dto.event_date)
        if event_dt <= now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha del evento debe ser estrictamente futura",
            )

        # 4. Validar modalidad y espacio físico / virtual
        duration = dto.duration_minutes or 120
        if dto.modality in [ModalityEnum.IN_PERSON, ModalityEnum.HYBRID]:
            if not dto.venue_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Se requiere especificar un establecimiento (venue_id) para modalidad presencial o híbrida",
                )
            venue = self.venue_repo.get_by_id(dto.venue_id)
            if not venue:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"El establecimiento con ID {dto.venue_id} no existe",
                )
            if venue.max_capacity < dto.max_capacity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El aforo solicitado ({dto.max_capacity}) excede la capacidad máxima del local ({venue.max_capacity})",
                )

            # Prevención de solapamiento físico en el mismo venue
            if self.experience_repo.has_venue_overlap(dto.venue_id, dto.event_date, duration):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El establecimiento '{venue.name}' ya cuenta con otro evento programado en ese horario",
                )

        experience = ExperienceMapper.to_entity(dto, host_id)
        experience.event_date = self._to_database_datetime(dto.event_date)
        created = self.experience_repo.create(experience)
        # Recargar con relaciones
        loaded = self.experience_repo.get_by_id(created.id)
        return self._to_response_dto(loaded or created)

    def update_experience(self, experience_id: int, host_id: int, dto: ExperienceUpdateDTO) -> ExperienceResponseDTO:
        exp = self.experience_repo.get_by_id(experience_id)
        if not exp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiencia con ID {experience_id} no encontrada",
            )

        if exp.host_id != host_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes autorización para modificar esta experiencia",
            )

        # Bloquear edición si el evento ya fue cancelado o finalizado
        if exp.status in [ExperienceStatusEnum.CANCELLED, ExperienceStatusEnum.FINISHED]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se puede modificar una experiencia en estado {exp.status.value}",
            )

        min_cap = dto.min_capacity if dto.min_capacity is not None else exp.min_capacity
        max_cap = dto.max_capacity if dto.max_capacity is not None else exp.max_capacity

        if min_cap <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El aforo mínimo debe ser mayor a 0",
            )
        if max_cap < min_cap:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El cupo máximo no puede ser menor al aforo mínimo",
            )
        if dto.max_capacity is not None and dto.max_capacity < exp.reserved_slots:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se puede reducir la capacidad a {dto.max_capacity} porque ya existen {exp.reserved_slots} cupos reservados",
            )

        # Regla de negocio real: Bloquear cambio de precio si ya existen entradas vendidas
        if exp.reserved_slots > 0 and dto.price is not None and dto.price != exp.price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede modificar el precio porque ya existen cupos adquiridos para esta experiencia",
            )

        new_date = (
            self._to_database_datetime(dto.event_date)
            if dto.event_date is not None
            else exp.event_date
        )
        new_duration = dto.duration_minutes if dto.duration_minutes is not None else (exp.duration_minutes or 120)

        if dto.event_date is not None and self._ensure_utc(dto.event_date) <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La nueva fecha del evento debe ser estrictamente futura",
            )

        target_modality = dto.modality if dto.modality is not None else exp.modality
        target_venue_id = exp.venue_id
        if "venue_id" in dto.model_fields_set:
            target_venue_id = dto.venue_id
        if target_modality == ModalityEnum.VIRTUAL:
            target_venue_id = None
        elif target_modality in [ModalityEnum.IN_PERSON, ModalityEnum.HYBRID]:
            if target_venue_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Se requiere especificar un establecimiento (venue_id) para modalidad presencial o híbrida",
                )

            venue = self.venue_repo.get_by_id(target_venue_id)
            if not venue:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"El establecimiento con ID {target_venue_id} no existe",
                )
            if venue.max_capacity < max_cap:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El aforo solicitado ({max_cap}) excede la capacidad máxima del local ({venue.max_capacity})",
                )
            if self.experience_repo.has_venue_overlap(
                target_venue_id,
                new_date,
                new_duration,
                exclude_experience_id=exp.id,
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El establecimiento ya cuenta con otro evento programado en ese horario",
                )

        exp.event_date = new_date
        exp.venue_id = target_venue_id

        if dto.title is not None:
            exp.title = dto.title.strip()
        if dto.description is not None:
            exp.description = dto.description.strip()
        if dto.cover_image_url is not None:
            exp.cover_image_url = dto.cover_image_url
        if dto.modality is not None:
            exp.modality = dto.modality
        if dto.price is not None:
            exp.price = dto.price
        if dto.min_capacity is not None:
            exp.min_capacity = dto.min_capacity
        if dto.max_capacity is not None:
            exp.max_capacity = dto.max_capacity
        if dto.duration_minutes is not None:
            exp.duration_minutes = dto.duration_minutes
        if dto.virtual_meeting_url is not None:
            exp.virtual_meeting_url = dto.virtual_meeting_url

        updated = self.experience_repo.update(exp)
        loaded = self.experience_repo.get_by_id(updated.id)
        return self._to_response_dto(loaded or updated)


    def cancel_experience(self, experience_id: int, host_id: int) -> ExperienceResponseDTO:
        exp = self.experience_repo.get_by_id(experience_id)
        if not exp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiencia con ID {experience_id} no encontrada",
            )
        if exp.host_id != host_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes autorización para cancelar esta experiencia",
            )
        if exp.status in [ExperienceStatusEnum.CANCELLED, ExperienceStatusEnum.FINISHED]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La experiencia ya se encuentra {exp.status.value.lower()}",
            )

        exp.status = ExperienceStatusEnum.CANCELLED
        updated = self.experience_repo.update(exp)
        loaded = self.experience_repo.get_by_id(updated.id)
        return self._to_response_dto(loaded or updated)

    def get_my_hosted_experiences(
        self, host_id: int, status: Optional[ExperienceStatusEnum] = None
    ) -> List[ExperienceResponseDTO]:
        experiences = self.experience_repo.get_by_host(host_id, status)
        return [self._to_response_dto(e) for e in experiences]

    def get_experience_by_id(self, experience_id: int) -> ExperienceResponseDTO:
        exp = self.experience_repo.get_by_id(experience_id)
        if not exp or exp.status == ExperienceStatusEnum.DRAFT:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiencia con ID {experience_id} no encontrada",
            )
        return self._to_response_dto(exp)

    def search_catalog(self, filters: ExperienceFilterDTO) -> CatalogResponseDTO:
        location_values = (filters.latitude, filters.longitude, filters.radius_km)
        if any(value is not None for value in location_values) and not all(
            value is not None for value in location_values
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="latitude, longitude y radius_km deben enviarse juntos.",
            )

        experiences, total_count = self.experience_repo.filter(filters)
        items = [self._to_response_dto(e) for e in experiences]
        total_pages = math.ceil(total_count / filters.page_size) if total_count > 0 else 1
        return CatalogResponseDTO(
            total=total_count,
            page=filters.page,
            page_size=filters.page_size,
            total_pages=total_pages,
            experiences=items,
        )

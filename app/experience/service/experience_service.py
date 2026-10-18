from __future__ import annotations

import math
from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.experience.dto.experience_dto import (
    CatalogResponseDTO,
    ExperienceCreateDTO,
    ExperienceFilterDTO,
    ExperienceResponseDTO,
    ExperienceUpdateDTO,
)
from app.experience.entity.experience import Experience, ExperienceStatusEnum, ModalityEnum
from app.experience.mapper.experience_mapper import ExperienceMapper
from app.experience.repository.category_repository import CategoryRepository
from app.experience.repository.experience_repository import ExperienceRepository
from app.experience.repository.venue_repository import VenueRepository


class ExperienceService:
    """
    Servicio de dominio para Publicación, Gestión y Exploración Geoespacial de Experiencias
    (CU-04: Publicar Experiencia y CU-05: Explorar y Filtrar Experiencias / HU-04, HU-05, HU-07).
    """

    def __init__(self, db: Session) -> None:
        """
        Inicializa el servicio de experiencias con sus repositorios colaboradores.

        Args:
            db (Session): Sesión activa de SQLAlchemy.
        """
        self.db = db
        self.experience_repo = ExperienceRepository(db)
        self.category_repo = CategoryRepository(db)
        self.venue_repo = VenueRepository(db)

    def _ensure_utc(self, dt: datetime) -> datetime:
        """
        Normaliza un objeto `datetime` a zona horaria UTC explícita.

        Args:
            dt (datetime): Fecha y hora a normalizar.

        Returns:
            datetime: Fecha y hora con `tzinfo=timezone.utc`.
        """
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _to_database_datetime(self, dt: datetime) -> datetime:
        """
        Convierte una fecha y hora a UTC sin zona horaria (naive UTC) para almacenamiento consistente.

        Args:
            dt (datetime): Fecha y hora de entrada.

        Returns:
            datetime: Fecha y hora UTC naive.
        """
        return self._ensure_utc(dt).replace(tzinfo=None)

    def _to_response_dto(
        self,
        exp: Experience,
        user_latitude: float | None = None,
        user_longitude: float | None = None,
    ) -> ExperienceResponseDTO:
        """
        Transforma una entidad `Experience` en su DTO de respuesta con métricas financieras y de distancia.

        Args:
            exp (Experience): Entidad ORM `Experience`.
            user_latitude (float | None): Latitud opcional del usuario para cálculo de distancia.
            user_longitude (float | None): Longitud opcional del usuario para cálculo de distancia.

        Returns:
            ExperienceResponseDTO: Contrato de respuesta enriquecido.
        """
        return ExperienceMapper.to_response_dto(
            exp,
            user_latitude=user_latitude,
            user_longitude=user_longitude,
        )

    def create_experience(self, host_id: str, dto: ExperienceCreateDTO) -> ExperienceResponseDTO:
        """
        Publica una nueva experiencia validando existencia de categoría, coherencia de aforos
        (`min_capacity` vs `max_capacity`), fecha futura, capacidad máxima del local físico y ausencia
        de cruce de horarios en el mismo establecimiento (CU-04 / HU-04, HU-07).

        Args:
            host_id (str): ID del usuario anfitrión o establecimiento que publica el evento (UUID).
            dto (ExperienceCreateDTO): Datos de configuración del evento, aforos y precio.

        Returns:
            ExperienceResponseDTO: Experiencia creada con proyecciones financieras de comisiones.

        Raises:
            HTTPException (404): Si la categoría o el establecimiento indicado no existen.
            HTTPException (400): Si los aforos son inválidos, la fecha no es futura, falta `venue_id`
                en modalidad presencial/híbrida, se excede el aforo del local o hay solapamiento horario.
        """
        category = self.category_repo.get_by_id(dto.category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"La categoría con ID {dto.category_id} no existe",
            )

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

        now = datetime.now(timezone.utc)
        event_dt = self._ensure_utc(dto.event_date)
        if event_dt <= now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha del evento debe ser estrictamente futura",
            )

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

            if self.experience_repo.has_venue_overlap(dto.venue_id, dto.event_date, duration):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El establecimiento '{venue.name}' ya cuenta con otro evento programado en ese horario",
                )

        experience = ExperienceMapper.to_entity(dto, host_id)
        if dto.modality == ModalityEnum.VIRTUAL:
            experience.venue_id = None
        experience.event_date = self._to_database_datetime(dto.event_date)
        created = self.experience_repo.create(experience)
        loaded = self.experience_repo.get_by_id(created.id)
        return self._to_response_dto(loaded or created)

    def update_experience(
        self,
        experience_id: str,
        host_id: str,
        dto: ExperienceUpdateDTO,
    ) -> ExperienceResponseDTO:
        """
        Actualiza los datos, aforos, modalidad o precio de una experiencia existente, verificando
        propiedad del anfitrión, bloqueo de precio si ya existen reservas y no solapamiento de local (CU-04).

        Args:
            experience_id (str): ID de la experiencia a modificar (UUID).
            host_id (str): ID del usuario autenticado que solicita la modificación (UUID).
            dto (ExperienceUpdateDTO): Campos a actualizar.

        Returns:
            ExperienceResponseDTO: Experiencia actualizada con sus cálculos recalculados.

        Raises:
            HTTPException (404): Si la experiencia o el nuevo establecimiento no existen.
            HTTPException (403): Si el usuario no es el anfitrión propietario de la experiencia.
            HTTPException (400): Si se violan reglas de negocio de estado, aforo, precio o horario.
        """
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
        new_duration = (
            dto.duration_minutes
            if dto.duration_minutes is not None
            else (exp.duration_minutes or 120)
        )

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

    def cancel_experience(self, experience_id: str, host_id: str) -> ExperienceResponseDTO:
        """
        Cancela una experiencia publicada cambiando su estado a `CANCELLED` (CU-04).

        Args:
            experience_id (str): ID de la experiencia a cancelar (UUID).
            host_id (str): ID del anfitrión propietario (UUID).

        Returns:
            ExperienceResponseDTO: Experiencia con estado `CANCELLED`.

        Raises:
            HTTPException (404): Si la experiencia no existe.
            HTTPException (403): Si el usuario no es el anfitrión propietario.
            HTTPException (400): Si la experiencia ya estaba cancelada o finalizada.
        """
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
        self,
        host_id: str,
        status: ExperienceStatusEnum | None = None,
    ) -> list[ExperienceResponseDTO]:
        """
        Obtiene todas las experiencias publicadas por el anfitrión autenticado (CU-04).

        Args:
            host_id (str): ID del anfitrión autenticado (UUID).
            status (ExperienceStatusEnum | None): Filtro opcional por estado del evento.

        Returns:
            list[ExperienceResponseDTO]: Lista de experiencias del anfitrión con desglose de comisiones.
        """
        experiences = self.experience_repo.get_by_host(host_id, status)
        return [self._to_response_dto(e) for e in experiences]

    def get_experience_by_id(self, experience_id: str) -> ExperienceResponseDTO:
        """
        Consulta el detalle público de una experiencia por su ID (CU-04, CU-05).

        Args:
            experience_id (str): ID de la experiencia a consultar (UUID).

        Returns:
            ExperienceResponseDTO: Detalle completo de la experiencia.

        Raises:
            HTTPException (404): Si la experiencia no existe o se encuentra en borrador (`DRAFT`).
        """
        exp = self.experience_repo.get_by_id(experience_id)
        if not exp or exp.status == ExperienceStatusEnum.DRAFT:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Experiencia con ID {experience_id} no encontrada",
            )
        return self._to_response_dto(exp)

    def search_catalog(self, filters: ExperienceFilterDTO) -> CatalogResponseDTO:
        """
        Explora y filtra el catálogo público de experiencias soportando búsqueda geoespacial
        por coordenadas (`latitude`, `longitude`, `radius_km`), zona urbana, categoría, modalidad,
        rango de fechas, precio máximo y disponibilidad de cupos (CU-05 / HU-05).

        Args:
            filters (ExperienceFilterDTO): Criterios de búsqueda, geolocalización y paginación.

        Returns:
            CatalogResponseDTO: Respuesta paginada con el listado de experiencias y metadatos de páginas.

        Raises:
            HTTPException (422): Si se envían coordenadas de geolocalización incompletas.
            HTTPException (400): Si el rango de fechas es inválido (`date_from > date_to`).
        """
        location_values = (filters.latitude, filters.longitude, filters.radius_km)
        if any(value is not None for value in location_values) and not all(
            value is not None for value in location_values
        ):
            raise HTTPException(
                status_code=422,
                detail="latitude, longitude y radius_km deben enviarse juntos.",
            )

        if (
            filters.date_from is not None
            and filters.date_to is not None
            and self._ensure_utc(filters.date_from) > self._ensure_utc(filters.date_to)
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha inicial (date_from) no puede ser posterior a la fecha final (date_to).",
            )

        experiences, total_count = self.experience_repo.filter(filters)
        items = [
            self._to_response_dto(
                e,
                user_latitude=filters.latitude,
                user_longitude=filters.longitude,
            )
            for e in experiences
        ]
        total_pages = math.ceil(total_count / filters.page_size) if total_count > 0 else 1
        return CatalogResponseDTO(
            total=total_count,
            page=filters.page,
            page_size=filters.page_size,
            total_pages=total_pages,
            experiences=items,
        )

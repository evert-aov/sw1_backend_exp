from __future__ import annotations

from datetime import datetime, timedelta, timezone
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session, joinedload
from app.experience.dto.experience_dto import ExperienceFilterDTO
from app.experience.entity.experience import Experience, ExperienceStatusEnum
from app.experience.entity.venue import Venue


class ExperienceRepository:
    """
    Repositorio de acceso a datos para la entidad `Experience`.
    Implementa consultas con carga ansiosa de relaciones (`joinedload`), prevención de solapamiento
    horario en establecimientos (CU-04) y filtrado geoespacial con fórmula de Haversine (CU-05).
    """

    def __init__(self, db: Session) -> None:
        """
        Inicializa el repositorio con una sesión activa de SQLAlchemy.

        Args:
            db (Session): Sesión de base de datos inyectada.
        """
        self.db = db

    def get_by_id(self, experience_id: int) -> Experience | None:
        """
        Obtiene una experiencia por su ID cargando sus relaciones `category`, `venue` y `host`.

        Args:
            experience_id (int): ID único de la experiencia.

        Returns:
            Experience | None: Entidad `Experience` encontrada o `None`.
        """
        return (
            self.db.query(Experience)
            .options(
                joinedload(Experience.category),
                joinedload(Experience.venue),
                joinedload(Experience.host),
            )
            .filter(Experience.id == experience_id)
            .first()
        )

    def create(self, experience: Experience) -> Experience:
        """
        Persiste una nueva experiencia en la base de datos (CU-04).

        Args:
            experience (Experience): Entidad `Experience` a guardar.

        Returns:
            Experience: Entidad persistida y refrescada.
        """
        self.db.add(experience)
        self.db.commit()
        self.db.refresh(experience)
        return experience

    def update(self, experience: Experience) -> Experience:
        """
        Guarda los cambios realizados sobre una experiencia existente (CU-04).

        Args:
            experience (Experience): Entidad `Experience` modificada.

        Returns:
            Experience: Entidad actualizada.
        """
        self.db.commit()
        self.db.refresh(experience)
        return experience

    def filter(self, filters: ExperienceFilterDTO) -> tuple[list[Experience], int]:
        """
        Filtra y pagina el catálogo público de experiencias (`OPEN` y `CONFIRMED`) aplicando
        criterios de proximidad geográfica Haversine (`latitude`, `longitude`, `radius_km`),
        zona urbana, categoría, modalidad, rango de fechas, precio máximo y texto libre (CU-05 / HU-05).

        Args:
            filters (ExperienceFilterDTO): Parámetros de filtrado y paginación.

        Returns:
            tuple[list[Experience], int]: Tupla con la lista de experiencias de la página actual
            y el conteo total de registros coincidentes.
        """
        query = self.db.query(Experience).options(
            joinedload(Experience.category),
            joinedload(Experience.venue),
            joinedload(Experience.host),
        )

        # Solo mostrar experiencias abiertas o confirmadas en el catálogo público
        query = query.filter(
            Experience.status.in_([ExperienceStatusEnum.OPEN, ExperienceStatusEnum.CONFIRMED])
        )

        distance_km = None
        if (
            filters.latitude is not None
            and filters.longitude is not None
            and filters.radius_km is not None
        ):
            query = query.join(Experience.venue)
            query = query.filter(
                Venue.latitude.isnot(None),
                Venue.longitude.isnot(None),
            )

            latitude_radians = func.radians(filters.latitude)
            venue_latitude_radians = func.radians(Venue.latitude)
            delta_latitude = venue_latitude_radians - latitude_radians
            delta_longitude = func.radians(Venue.longitude - filters.longitude)
            haversine_a = (
                func.pow(func.sin(delta_latitude / 2.0), 2)
                + func.cos(latitude_radians)
                * func.cos(venue_latitude_radians)
                * func.pow(func.sin(delta_longitude / 2.0), 2)
            )
            haversine_a = case((haversine_a > 1.0, 1.0), else_=haversine_a)
            distance_km = 6371.0088 * 2.0 * func.asin(func.sqrt(haversine_a))
            query = query.filter(distance_km <= filters.radius_km)

        if filters.category_id is not None:
            query = query.filter(Experience.category_id == filters.category_id)

        if filters.modality is not None:
            query = query.filter(Experience.modality == filters.modality)

        if filters.search:
            pattern = f"%{filters.search.strip()}%"
            query = query.filter(
                or_(
                    Experience.title.ilike(pattern),
                    Experience.description.ilike(pattern),
                )
            )

        if filters.date_from is not None:
            date_from_naive = (
                filters.date_from.astimezone(timezone.utc).replace(tzinfo=None)
                if filters.date_from.tzinfo is not None
                else filters.date_from
            )
            query = query.filter(Experience.event_date >= date_from_naive)

        if filters.date_to is not None:
            date_to_naive = (
                filters.date_to.astimezone(timezone.utc).replace(tzinfo=None)
                if filters.date_to.tzinfo is not None
                else filters.date_to
            )
            query = query.filter(Experience.event_date <= date_to_naive)

        if filters.max_price is not None:
            query = query.filter(Experience.price <= filters.max_price)

        if filters.only_available:
            query = query.filter(Experience.reserved_slots < Experience.max_capacity)

        if filters.zone:
            if filters.latitude is None:
                query = query.join(Experience.venue)
            query = query.filter(Venue.zone.ilike(f"%{filters.zone.strip()}%"))

        total_count = query.count()
        skip = (filters.page - 1) * filters.page_size
        if distance_km is not None:
            query = query.order_by(distance_km.asc(), Experience.event_date.asc())
        else:
            query = query.order_by(Experience.event_date.asc())
        items = query.offset(skip).limit(filters.page_size).all()

        return items, total_count

    def has_venue_overlap(
        self,
        venue_id: int,
        start_time: datetime,
        duration_minutes: int,
        buffer_minutes: int = 0,
        exclude_experience_id: int | None = None,
    ) -> bool:
        """
        Verifica si existe solapamiento de horario en un mismo establecimiento físico (`venue_id`)
        con otras experiencias activas (`OPEN`, `CONFIRMED`, `LIVE`).

        Args:
            venue_id (int): ID del establecimiento físico a validar.
            start_time (datetime): Fecha y hora de inicio del evento propuesto.
            duration_minutes (int): Duración del evento en minutos.
            buffer_minutes (int): Margen adicional de tiempo entre eventos en minutos.
            exclude_experience_id (int | None): ID de experiencia a excluir (útil en actualizaciones).

        Returns:
            bool: `True` si existe cruce de horarios en el local, `False` si el horario está libre.
        """

        def to_utc(dt: datetime) -> datetime:
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

        new_start_utc = to_utc(start_time)
        new_end_utc = new_start_utc + timedelta(minutes=duration_minutes)
        buffer = timedelta(minutes=buffer_minutes)

        query_start = new_start_utc.replace(tzinfo=None)
        query_end = new_end_utc.replace(tzinfo=None)

        query = self.db.query(Experience).filter(
            Experience.venue_id == venue_id,
            Experience.status.in_(
                [
                    ExperienceStatusEnum.OPEN,
                    ExperienceStatusEnum.CONFIRMED,
                    ExperienceStatusEnum.LIVE,
                ]
            ),
            Experience.event_date >= query_start - timedelta(days=1),
            Experience.event_date <= query_end + timedelta(days=1),
        )
        if exclude_experience_id is not None:
            query = query.filter(Experience.id != exclude_experience_id)

        existing_events = query.all()
        for existing in existing_events:
            ex_start_utc = to_utc(existing.event_date)
            ex_duration = existing.duration_minutes or 120
            ex_end_utc = ex_start_utc + timedelta(minutes=ex_duration)

            if ex_start_utc < (new_end_utc + buffer) and (ex_end_utc + buffer) > new_start_utc:
                return True

        return False

    def get_by_host(
        self,
        host_id: int,
        status: ExperienceStatusEnum | None = None,
    ) -> list[Experience]:
        """
        Lista todas las experiencias creadas por un anfitrión específico, con filtro opcional por estado.

        Args:
            host_id (int): ID del usuario anfitrión.
            status (ExperienceStatusEnum | None): Estado opcional para filtrar.

        Returns:
            list[Experience]: Lista de experiencias del anfitrión ordenadas por fecha descendente.
        """
        query = (
            self.db.query(Experience)
            .options(
                joinedload(Experience.category),
                joinedload(Experience.venue),
                joinedload(Experience.host),
            )
            .filter(Experience.host_id == host_id)
        )
        if status is not None:
            query = query.filter(Experience.status == status)

        return query.order_by(Experience.event_date.desc()).all()

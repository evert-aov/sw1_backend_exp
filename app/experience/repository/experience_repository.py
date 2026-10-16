from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session, joinedload
from app.experience.entity.experience import Experience, ExperienceStatusEnum
from app.experience.entity.venue import Venue
from app.experience.dto.experience_dto import ExperienceFilterDTO


# Repositorio para la entidad Experience
class ExperienceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, experience_id: int) -> Optional[Experience]:
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
        self.db.add(experience)
        self.db.commit()
        self.db.refresh(experience)
        return experience

    def update(self, experience: Experience) -> Experience:
        self.db.commit()
        self.db.refresh(experience)
        return experience

    def filter(self, filters: ExperienceFilterDTO) -> Tuple[List[Experience], int]:
        query = (
            self.db.query(Experience)
            .options(
                joinedload(Experience.category),
                joinedload(Experience.venue),
                joinedload(Experience.host),
            )
        )

        # Solo mostrar experiencias abiertas o confirmadas en catálogo público
        query = query.filter(
            Experience.status.in_([ExperienceStatusEnum.OPEN, ExperienceStatusEnum.CONFIRMED])
        )

        distance_km = None
        if filters.latitude is not None:
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

        if filters.category_id:
            query = query.filter(Experience.category_id == filters.category_id)

        if filters.modality:
            query = query.filter(Experience.modality == filters.modality)

        if filters.search:
            pattern = f"%{filters.search.strip()}%"
            query = query.filter(
                or_(
                    Experience.title.ilike(pattern),
                    Experience.description.ilike(pattern),
                )
            )

        if filters.date_from:
            query = query.filter(Experience.event_date >= filters.date_from)

        if filters.date_to:
            query = query.filter(Experience.event_date <= filters.date_to)

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
        exclude_experience_id: Optional[int] = None,
    ) -> bool:
        def to_utc(dt: datetime) -> datetime:
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

        new_start_utc = to_utc(start_time)
        new_end_utc = new_start_utc + timedelta(minutes=duration_minutes)
        buffer = timedelta(minutes=buffer_minutes)

        # Usar versión naive para el query SQL por compatibilidad con SQLite en tests
        query_start = new_start_utc.replace(tzinfo=None)
        query_end = new_end_utc.replace(tzinfo=None)

        query = (
            self.db.query(Experience)
            .filter(
                Experience.venue_id == venue_id,
                Experience.status.in_([
                    ExperienceStatusEnum.OPEN,
                    ExperienceStatusEnum.CONFIRMED,
                    ExperienceStatusEnum.LIVE,
                ]),
                Experience.event_date >= query_start - timedelta(days=1),
                Experience.event_date <= query_end + timedelta(days=1),
            )
        )
        if exclude_experience_id:
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
        self, host_id: int, status: Optional[ExperienceStatusEnum] = None
    ) -> List[Experience]:
        query = (
            self.db.query(Experience)
            .options(
                joinedload(Experience.category),
                joinedload(Experience.venue),
                joinedload(Experience.host),
            )
            .filter(Experience.host_id == host_id)
        )
        if status:
            query = query.filter(Experience.status == status)

        return query.order_by(Experience.event_date.desc()).all()

"""Demanda observada en búsquedas: agregación temporal y recomendaciones explicables."""

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from statistics import median
from uuid import uuid5, NAMESPACE_URL
from zoneinfo import ZoneInfo
from sqlalchemy import func, select
from app.experience.dto.experience_dto import ExperienceFilterDTO
from app.experience.entity.category import Category
from app.experience.repository.experience_repository import ExperienceRepository
from app.matching.dto.matching_dto import UnmetDemandInsightDTO, SuggestedExperienceDTO, SearchLogDTO
from app.matching.service.matching_service import normalized
from app.matching.repository.demand_repository import DemandRepository, SearchLogRepository


def search_key(filters: dict, session: str | None, now: datetime) -> str:
    """Agrupa reintentos/paginación por sesión efímera y ventana de cinco minutos."""
    payload = json.dumps([session or "anonymous", int(now.timestamp()) // 300, filters], sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode()).hexdigest()


def observed_preferences(samples):
    """Presupuesto mediano y franja solicitada; no inventa datos si la muestra no los contiene."""
    budgets, slots = [], []
    for sample in samples:
        budget = sample.get("max_price")
        if budget is not None:
            budgets.append(float(budget))
        requested = sample.get("date_from")
        if requested:
            value = datetime.fromisoformat(requested.replace("Z", "+00:00"))
            value = (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(ZoneInfo("America/La_Paz"))
            slots.append("Mañana" if value.hour < 12 else "Tarde" if value.hour < 19 else "Noche")
    return (median(budgets) if budgets else None, Counter(slots).most_common(1)[0][0] if slots else None)


class DemandPredictionService:
    def __init__(self, db):
        self.db = db
        self.repository = DemandRepository(db)
        self.logs = SearchLogRepository(db)

    def record_catalog(self, filters: ExperienceFilterDTO, total: int, session: str | None = None, user_id=None):
        """El servidor calcula si hubo oferta; un cliente nunca afirma found_results."""
        if filters.page != 1 or not (filters.search or filters.category_id or filters.zone or filters.date_from):
            return
        category = self.db.get(Category, filters.category_id) if filters.category_id else None
        values = filters.model_dump(mode="json", exclude={"page", "page_size"})
        for field in ("search", "zone"):
            if values.get(field):
                values[field] = normalized(values[field])
        now = datetime.now(timezone.utc)
        self.logs.log_evidence(
            user_id=user_id, query_text=values.get("search"),
            category=normalized(category.name) if category else None,
            zone=values.get("zone") or None, found_results=total > 0,
            search_filters=values, dedupe_key=search_key(values, session, now),
        )
        self.db.commit()

    def record_search(self, user_id: str | None, dto: SearchLogDTO, session=None) -> None:
        category = self.db.scalar(select(Category).where(func.lower(Category.name) == dto.category.casefold())) if dto.category else None
        filters = ExperienceFilterDTO(search=dto.query_text or (dto.category if not category else None), category_id=category.id if category else None, zone=dto.zone, only_available=True)
        _, total = ExperienceRepository(self.db).filter(filters)
        self.record_catalog(filters, total, session, user_id)

    def _observations(self, zone=None):
        return self.repository.observations(normalized(zone) if zone and zone.strip() else None)

    def get_zone_insights(self, zone: str | None = None):
        output = []
        for row in self._observations(zone):
            # Precios/horarios salen de un máximo de 500 solicitudes recientes por segmento.
            samples = self.repository.samples(row.zone, row.keyword)
            price, slot = observed_preferences(samples)
            output.append(UnmetDemandInsightDTO(
                id=str(uuid5(NAMESPACE_URL, f"experiencia-demand:{row.zone}:{row.keyword}")),
                zone=row.zone, category_keyword=row.keyword, search_count=row.search_count,
                suggested_price=price, suggested_time_slot=slot, analyzed_at=row.last_seen,
            ))
        return output

    def generate_ai_experience_suggestions(self, zone: str | None = None):
        suggestions = []
        categories = self.db.scalars(select(Category)).all()
        category_ids = {normalized(item.name): item.id for item in categories}
        for row in self.get_zone_insights(zone):
            suggestions.append(SuggestedExperienceDTO(
                zone=row.zone, category_keyword=row.category_keyword, category_id=category_ids.get(row.category_keyword),
                estimated_interest_count=row.search_count, suggested_price=row.suggested_price,
                recommended_time_slot=row.suggested_time_slot, confidence_score=None,
                rationale=f"{row.search_count} búsquedas sin oferta en los últimos 30 días. Presupuesto y horario describen filtros observados; no garantizan asistencia ni rentabilidad.",
            ))
        return suggestions

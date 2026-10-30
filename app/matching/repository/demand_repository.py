"""Consultas sobre evidencia de búsquedas; la agregación no entrena modelos ficticios."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from app.matching.entity.unmet_demand import UnmetDemand
from app.matching.entity.search_log import SearchLog

class DemandRepository:
    def __init__(self, db):
        self.db = db

    def get_by_zone(self, zone: str):
        return self.db.scalars(select(UnmetDemand).where(UnmetDemand.zone == zone)).all()

    def get_top_demanded(self, limit: int = 10):
        return self.db.scalars(select(UnmetDemand).order_by(UnmetDemand.search_count.desc()).limit(limit)).all()

    def save_aggregated_demand(self, demand: UnmetDemand):
        self.db.add(demand)
        self.db.flush()
        return demand

    def observations(self, zone=None):
        keyword = func.coalesce(SearchLog.category, func.nullif(SearchLog.query_text, ""))
        statement = select(SearchLog.zone, keyword.label("keyword"), func.count().label("search_count"),
                           func.max(SearchLog.created_at).label("last_seen")).where(
            SearchLog.found_results.is_(False), SearchLog.zone.is_not(None), keyword.is_not(None),
            SearchLog.created_at >= datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30),
            SearchLog.dedupe_key.is_not(None),
        )
        if zone:
            statement = statement.where(SearchLog.zone == zone)
        return self.db.execute(statement.group_by(SearchLog.zone, keyword).order_by(
            func.count().desc(), SearchLog.zone, keyword).limit(100)).all()

    def samples(self, zone: str, category: str):
        keyword = func.coalesce(SearchLog.category, func.nullif(SearchLog.query_text, ""))
        return self.db.scalars(select(SearchLog.search_filters).where(
            SearchLog.zone == zone, keyword == category, SearchLog.found_results.is_(False),
            SearchLog.dedupe_key.is_not(None), SearchLog.created_at >= datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30),
        ).order_by(SearchLog.created_at.desc()).limit(500)).all()

class SearchLogRepository:
    def __init__(self, db):
        self.db = db

    def log_search(self, search: SearchLog):
        self.db.add(search)
        self.db.flush()
        return search

    def log_evidence(self, **values):
        self.db.execute(insert(SearchLog).values(**values).on_conflict_do_nothing(index_elements=[SearchLog.dedupe_key]))

    def get_unanswered_searches(self):
        return self.db.scalars(select(SearchLog).where(SearchLog.found_results.is_(False))).all()

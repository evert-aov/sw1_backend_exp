from typing import List, Optional
from sqlalchemy.orm import Session
from app.matching.entity.unmet_demand import UnmetDemand
from app.matching.entity.search_log import SearchLog


# Repositorio para UnmetDemand y SearchLog: únicamente firmas de métodos
class DemandRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_zone(self, zone: str) -> List[UnmetDemand]:
        # Consultar demandas insatisfechas por zona urbana
        pass

    def get_top_demanded(self, limit: int = 10) -> List[UnmetDemand]:
        # Obtener ranking de categorías más buscadas sin oferta
        pass

    def save_aggregated_demand(self, demand: UnmetDemand) -> UnmetDemand:
        # Guardar cálculo analítico de demanda
        pass


class SearchLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def log_search(self, search: SearchLog) -> SearchLog:
        # Registrar término y filtros de búsqueda de usuario
        pass

    def get_unanswered_searches(self) -> List[SearchLog]:
        # Obtener consultas que devolvieron 0 resultados
        pass

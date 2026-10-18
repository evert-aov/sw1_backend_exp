from typing import List
from sqlalchemy.orm import Session
from app.matching.dto.matching_dto import (
    UnmetDemandInsightDTO,
    SuggestedExperienceDTO,
    SearchLogDTO,
)


# Servicio para analítica predictiva de demanda urbana y prospección (CU-08)
class DemandPredictionService:
    def __init__(self, db: Session):
        self.db = db

    def record_search(self, user_id: str | None, dto: SearchLogDTO) -> None:
        # Registrar búsquedas de usuarios para análisis territorial
        pass

    def get_zone_insights(self, zone: str) -> List[UnmetDemandInsightDTO]:
        # Generar métricas de búsquedas insatisfechas por zona urbana
        pass

    def generate_ai_experience_suggestions(self, zone: str) -> List[SuggestedExperienceDTO]:
        # Sugerir a establecimientos qué eventos abrir, formatos y precios recomendados
        pass

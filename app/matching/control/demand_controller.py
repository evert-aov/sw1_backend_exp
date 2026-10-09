from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.matching.dto.matching_dto import (
    UnmetDemandInsightDTO,
    SuggestedExperienceDTO,
    SearchLogDTO,
)
from app.matching.service.demand_prediction_service import DemandPredictionService

demand_router = APIRouter(prefix="/demand", tags=["Demand Insights Controller (CU-08)"])


@demand_router.post("/log-search")
def log_user_search(dto: SearchLogDTO, db: Session = Depends(get_db)):
    # Firma de endpoint para registrar búsqueda en analítica
    pass


@demand_router.get("/insights", response_model=List[UnmetDemandInsightDTO])
def get_unmet_demand_insights(zone: str, db: Session = Depends(get_db)):
    # Firma de endpoint para ver panel de prospección de demanda por zona
    pass


@demand_router.get("/suggestions", response_model=List[SuggestedExperienceDTO])
def get_ai_suggestions_for_venue(zone: str, db: Session = Depends(get_db)):
    # Firma de endpoint con propuestas sugeridas de creación de eventos
    pass

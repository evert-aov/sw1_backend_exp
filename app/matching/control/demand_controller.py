from __future__ import annotations

from typing import Annotated, Any
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.matching.dto.matching_dto import (
    SearchLogDTO,
    SuggestedExperienceDTO,
    UnmetDemandInsightDTO,
)
from app.matching.service.demand_prediction_service import DemandPredictionService

demand_router = APIRouter(prefix="/demand", tags=["Demand Insights Controller (CU-08)"])


@demand_router.post(
    "/log-search",
    status_code=status.HTTP_201_CREATED,
    summary="Registrar búsqueda de usuario para analítica de demanda (CU-08)",
    description="Almacena consultas de búsqueda para detectar tendencias de demanda urbana insatisfecha.",
)
def log_user_search(
    dto: SearchLogDTO,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """
    Registra una búsqueda en el historial analítico para prospección territorial (Sprint 2 - CU-08).

    Args:
        dto (SearchLogDTO): Parámetros de la búsqueda realizada.
        db (Session): Sesión activa de base de datos.

    Returns:
        dict[str, Any]: Confirmación de registro analítico.
    """
    service = DemandPredictionService(db)
    service.record_search(user_id=None, dto=dto)
    return {"status": "logged"}


@demand_router.get(
    "/insights",
    response_model=list[UnmetDemandInsightDTO],
    status_code=status.HTTP_200_OK,
    summary="Consultar prospección de demanda insatisfecha por zona (CU-08 / HU-10)",
    description="Devuelve métricas de búsquedas no cubiertas agrupadas por zona geográfica.",
)
def get_unmet_demand_insights(
    zone: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[UnmetDemandInsightDTO]:
    """
    Obtiene los indicadores de demanda urbana insatisfecha en una zona específica (Sprint 2 - CU-08).

    Args:
        zone (str): Nombre de la zona urbana a analizar.
        db (Session): Sesión activa de base de datos.

    Returns:
        list[UnmetDemandInsightDTO]: Lista de insights de demanda insatisfecha.
    """
    service = DemandPredictionService(db)
    return service.get_zone_insights(zone=zone)


@demand_router.get(
    "/suggestions",
    response_model=list[SuggestedExperienceDTO],
    status_code=status.HTTP_200_OK,
    summary="Obtener recomendaciones de creación de eventos por zona (CU-08 / HU-11)",
    description="Sugiere temáticas, horarios y precios óptimos basados en la demanda vecinal.",
)
def get_ai_suggestions_for_venue(
    zone: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[SuggestedExperienceDTO]:
    """
    Genera propuestas inteligentes de eventos rentables para establecimientos según su zona (CU-08).

    Args:
        zone (str): Zona urbana del establecimiento.
        db (Session): Sesión activa de base de datos.

    Returns:
        list[SuggestedExperienceDTO]: Lista de sugerencias de experiencias.
    """
    service = DemandPredictionService(db)
    return service.generate_ai_experience_suggestions(zone=zone)

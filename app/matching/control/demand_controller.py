from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.entity.user import User
from app.core.database import get_db
from app.core.security import get_current_active_user
from app.matching.dto.matching_dto import (
    DemandModelStatusDTO,
    SearchLogDTO,
    SuggestedExperienceDTO,
    UnmetDemandInsightDTO,
)
from app.matching.service.demand_prediction_service import DemandPredictionService

demand_router = APIRouter(prefix="/demand", tags=["Demand Insights Controller (CU-08)"])


@demand_router.post(
    "/log-search",
    status_code=status.HTTP_410_GONE,
    summary="Registro de búsqueda legado (deshabilitado)",
    description=(
        "Conserva el esquema SearchLogDTO para compatibilidad documental. "
        "Los eventos que alimentan demanda se registran internamente desde el catálogo; "
        "el cliente no puede declarar si encontró resultados."
    ),
    response_description="El endpoint legado no registra eventos y devuelve HTTP 410.",
)
def log_user_search(dto: SearchLogDTO) -> dict[str, Any]:
    """
    Conserva el DTO y el esquema OpenAPI legado, pero no registra datos enviados por clientes.

    La evidencia de demanda se captura desde `search_catalog`, donde el backend conoce el conteo
    real. Este endpoint responde 410 para guiar a clientes antiguos hacia el flujo confiable.

    Args:
        dto (SearchLogDTO): Cuerpo legado; no se persiste ni se usa para el agregado.

    Returns:
        No retorna un valor; responde siempre con HTTP 410.

    Raises:
        HTTPException (410): El registro debe ocurrir internamente en la búsqueda del catálogo.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "Endpoint legado deshabilitado. Las búsquedas verificables se registran desde el catálogo; "
            "este cuerpo no se almacena ni alimenta las métricas."
        ),
    )


@demand_router.get(
    "/insights",
    response_model=list[UnmetDemandInsightDTO],
    status_code=status.HTTP_200_OK,
    summary="Consultar búsquedas sin resultados por zona (CU-08 / HU-10)",
    description=(
        "Devuelve eventos de búsqueda sin resultados, agregados por categoría durante una ventana móvil. "
        "Los conteos representan búsquedas, no personas únicas ni asistentes potenciales. "
        "suggested_price y suggested_time_slot se conservan por compatibilidad y actualmente son null. "
        "Disponible para administradores y propietarios de establecimientos de la zona."
    ),
)
def get_unmet_demand_insights(
    zone: Annotated[str, Query(min_length=2, max_length=100)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> list[UnmetDemandInsightDTO]:
    """
    Consulta los indicadores agregados de búsqueda insatisfecha para una zona (CU-08 / HU-10).

    Args:
        zone (str): Nombre exacto de la zona asociada al venue.
        current_user (User): Administrador o propietario de un venue en la zona.
        db (Session): Sesión de base de datos de la petición.
        window_days (int): Días retrospectivos del agregado (1-365, por defecto 30).

    Returns:
        list[UnmetDemandInsightDTO]: Agregados por categoría; precio y franja se conservan como null
        hasta que exista una fuente de cálculo aprobada.
    """
    service = DemandPredictionService(db)
    return service.get_zone_insights(
        user_id=current_user.id,
        zone=zone,
        window_days=window_days,
    )


@demand_router.post(
    "/model/train",
    response_model=DemandModelStatusDTO,
    status_code=status.HTTP_200_OK,
    summary="Entrenar y validar el modelo de quórum con datos reales",
    description=(
        "Solo administradores. Usa hasta 730 días de experiencias con pagos liquidados y una única moneda "
        "(la de mayor volumen), excluye experiencias con monedas ambiguas, separa el holdout temporal más reciente "
        "y solo habilita el modelo si supera AUC y Brier baseline. No carga datos sintéticos ni persiste entidades nuevas."
    ),
)
def train_quorum_model(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DemandModelStatusDTO:
    """Entrena y valida el modelo de quórum con resultados de pagos reales.

    Args:
        current_user (User): Administrador que solicita el entrenamiento.
        db (Session): Sesión de base de datos de la petición.

    Returns:
        DemandModelStatusDTO: Estado, volumen de datos y métricas de validación.

    Raises:
        HTTPException: Si el usuario no tiene rol de administrador.
    """
    service = DemandPredictionService(db)
    return service.train_quorum_model(user_id=current_user.id)


@demand_router.get(
    "/suggestions",
    response_model=list[SuggestedExperienceDTO],
    status_code=status.HTTP_200_OK,
    summary="Sugerir eventos potencialmente viables por demanda de zona (CU-08 / HU-11)",
    description=(
        "Ordena categorías por búsquedas sin resultados y, cuando existen al menos cinco experiencias "
        "comparables que alcanzaron quórum con reservas pagadas durante el último año, propone una mediana "
        "de precio, una franja horaria y una modalidad observadas en esos antecedentes. "
        "El modelo de quórum se entrena con resultados reales y un holdout temporal; solo se sirve si mejora "
        "el baseline. Sin mínimo de datos o validación aprobada, se usa el baseline bayesiano real cuando aplica "
        "o se devuelven estimaciones null. No se cargan datasets sintéticos. Las búsquedas no representan "
        "personas interesadas ni garantizan rentabilidad. estimated_interest_count y confidence_score permanecen null; "
        "Disponible para anfitriones autenticados, administradores y propietarios de establecimientos de la zona."
    ),
)
def get_ai_suggestions_for_venue(
    zone: Annotated[str, Query(min_length=2, max_length=100)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> list[SuggestedExperienceDTO]:
    """
    Recomienda categorías y referencias históricas de eventos que alcanzaron quórum pagado (CU-08 / HU-11).

    Args:
        zone (str): Zona de un establecimiento existente donde el anfitrión puede publicar.
        current_user (User): Anfitrión, administrador o propietario autorizado.
        db (Session): Sesión de base de datos de la petición.
        window_days (int): Días retrospectivos del agregado (1-365, por defecto 30).

    Returns:
        list[SuggestedExperienceDTO]: Categorías ordenadas por demanda observada. Las referencias requieren
        historial comparable suficiente; la tasa de quórum requiere resultados positivos y negativos históricos.
    """
    service = DemandPredictionService(db)
    return service.generate_experience_suggestions(
        user_id=current_user.id,
        zone=zone,
        window_days=window_days,
    )

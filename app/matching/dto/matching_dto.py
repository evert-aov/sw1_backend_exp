from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from app.matching.entity.matching_group import MatchingGroupStatusEnum


# DTO para postulación a un grupo de matching dinámico (CU-07)
class MatchingApplicationDTO(BaseModel):
    experience_id: int


# DTO de respuesta para grupo de matching con estado de quórum
class MatchingGroupResponseDTO(BaseModel):
    id: int
    experience_id: int
    target_quorum: int
    current_members: int
    status: MatchingGroupStatusEnum
    deadline: datetime
    created_at: datetime
    is_quorum_reached: bool = False

    class Config:
        from_attributes = True


# DTO para consulta y agregación de prospección de demanda urbana (CU-08)
class UnmetDemandInsightDTO(BaseModel):
    id: int
    zone: str
    category_keyword: str
    search_count: int
    suggested_price: Optional[float] = None
    suggested_time_slot: Optional[str] = None
    analyzed_at: datetime

    class Config:
        from_attributes = True


# DTO con propuesta sugerida por IA para creación de eventos según demanda vecinal
class SuggestedExperienceDTO(BaseModel):
    zone: str
    category_keyword: str
    estimated_interest_count: int
    suggested_price: float
    recommended_time_slot: str
    confidence_score: float


# DTO para registrar búsqueda de usuario
class SearchLogDTO(BaseModel):
    query_text: Optional[str] = None
    category: Optional[str] = None
    zone: Optional[str] = None
    found_results: bool = True

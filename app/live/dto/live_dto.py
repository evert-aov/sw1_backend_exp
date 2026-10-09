from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel
from app.live.entity.audience_metric import AgeGroupEnum
from app.live.entity.live_suggestion import SuggestionTypeEnum
from app.live.entity.live_session import LiveSessionStatusEnum


# DTO para iniciar sesión en vivo de un evento
class LiveSessionCreateDTO(BaseModel):
    experience_id: int


# DTO para frame efímero recibido desde canvas web cada 2-3 segundos (procesado solo en RAM)
class FramePayloadDTO(BaseModel):
    session_id: int
    image_base64: str
    timestamp_ms: int


# DTO con métricas agregadas transmitidas por WebSocket (CU-10)
class LiveMetricsDTO(BaseModel):
    session_id: int
    recorded_at: datetime
    detected_faces_count: int
    attention_score: float      # 0.0 - 1.0 (Engagement)
    joy_score: float            # 0.0 - 1.0
    neutral_score: float        # 0.0 - 1.0
    inattention_score: float    # 0.0 - 1.0
    dominant_age_group: Optional[AgeGroupEnum] = None
    energy_traffic_light: str   # "GREEN", "YELLOW", "RED"


# DTO de sugerencia en vivo del Asistente MC o DJ Virtual (CU-11, CU-12)
class ActionSuggestionDTO(BaseModel):
    id: int
    session_id: int
    suggestion_type: SuggestionTypeEnum
    suggestion_text: str
    recommended_bpm: Optional[str] = None
    recommended_genre: Optional[str] = None
    applied: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


# DTO de punto de serie de tiempo para gráficos del reporte post-evento
class MetricTimelinePointDTO(BaseModel):
    minute: int
    average_attention: float
    average_joy: float
    dominant_age: Optional[str] = None


# DTO para reporte analítico post-evento (CU-13)
class PostEventReportDTO(BaseModel):
    session_id: int
    experience_id: int
    experience_title: str
    total_duration_minutes: int
    average_attention_score: float
    average_joy_score: float
    peak_engagement_minute: int
    timeline: List[MetricTimelinePointDTO] = []


# DTO para aceptación de consentimiento de muestreo de video efímero (GDPR)
class ConsentDTO(BaseModel):
    session_id: int
    accepted: bool
    consent_type: str = "GDPR_EPHEMERAL_VIDEO_ANALYSIS"

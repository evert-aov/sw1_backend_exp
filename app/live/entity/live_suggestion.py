from datetime import datetime, timezone
import enum
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.core.database import Base


class SuggestionTypeEnum(str, enum.Enum):
    MC_DYNAMIC = "MC_DYNAMIC"          # Alerta desatención > 5 min, pausas activas, dinámicas
    DJ_MUSIC_CHANGE = "DJ_MUSIC_CHANGE"  # Cambio de tempo BPM, estilo según energía
    BREAK = "BREAK"                    # Descanso corto recomendado


# Entidad SugerenciaEnVivo: recomendaciones inteligentes contextuales generadas para el host / DJ
class LiveSuggestion(Base):
    __tablename__ = "live_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    live_session_id = Column(Integer, ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False)

    suggestion_type = Column(Enum(SuggestionTypeEnum), nullable=False)
    suggestion_text = Column(Text, nullable=False)
    recommended_bpm = Column(String(20), nullable=True)     # Ej: "128 BPM"
    recommended_genre = Column(String(50), nullable=True)   # Ej: "Electrónica / Pop Latino"
    applied_by_host = Column(Boolean, default=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    live_session = relationship("LiveSession", back_populates="suggestions")

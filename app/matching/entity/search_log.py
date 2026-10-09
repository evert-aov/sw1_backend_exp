from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from app.core.database import Base


# Entidad LogBusqueda: registro anónimo/usuario de consultas para alimentar prospección de demanda
class SearchLog(Base):
    __tablename__ = "search_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    query_text = Column(String(200), nullable=True)
    category = Column(String(100), nullable=True)
    zone = Column(String(100), nullable=True)
    found_results = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UUID
from app.core.database import Base, generate_uuid


# Entidad LogBusqueda: registro anónimo/usuario de consultas para alimentar prospección de demanda
class SearchLog(Base):
    __tablename__ = "search_logs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    query_text = Column(String(200), nullable=True)
    category = Column(String(100), nullable=True)
    zone = Column(String(100), nullable=True)
    found_results = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

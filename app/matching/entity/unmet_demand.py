from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, UUID
from app.core.database import Base, generate_uuid


# Entidad DemandaInsatisfecha: agregación de búsquedas sin oferta en zonas urbanas (CU-08)
class UnmetDemand(Base):
    __tablename__ = "unmet_demands"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True)
    zone = Column(String(100), nullable=False, index=True)               # Ej: Equipetrol, Centro, Urubó
    category_keyword = Column(String(100), nullable=False, index=True)  # Ej: Cocina italiana, Pintura al óleo
    search_count = Column(Integer, default=1, nullable=False)           # Volumen de demanda
    suggested_price = Column(Float, nullable=True)                      # Precio sugerido por el modelo
    suggested_time_slot = Column(String(50), nullable=True)             # Horario de mayor demanda (Ej: Sábado noche)
    analyzed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

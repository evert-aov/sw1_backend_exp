from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base, generate_uuid


# Entidad Establecimiento / Venue: locales comerciales físicos donde se realizan eventos
class Venue(Base):
    __tablename__ = "venues"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True)
    owner_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(150), nullable=False, index=True)
    address = Column(String(255), nullable=True)
    city = Column(String(100), default="Santa Cruz de la Sierra")
    zone = Column(String(100), nullable=True, index=True)  # Zona urbana para análisis de demanda (CU-08)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    max_capacity = Column(Integer, default=50)
    phone = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("app.auth.entity.user.User", back_populates="venues")
    experiences = relationship("Experience", back_populates="venue")

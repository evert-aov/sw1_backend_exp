from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base, generate_uuid


# Entidad Usuario: almacena datos de cuenta, autenticación y perfil (CU-01, CU-02)
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=True)
    email = Column(String(150), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)
    avatar_url = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)
    interests = Column(JSON, default=list)  # Etiquetas para matching de intereses
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relaciones con módulos
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    venues = relationship("Venue", back_populates="owner")
    experiences = relationship("Experience", back_populates="host")
    bookings = relationship("Booking", back_populates="user")
    matching_memberships = relationship("MatchingMember", back_populates="user")
    saas_subscriptions = relationship("SaaSSubscription", back_populates="user")
    consents = relationship("Consent", back_populates="user")

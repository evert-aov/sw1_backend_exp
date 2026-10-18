from sqlalchemy import Column, String, Text, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base, generate_uuid


# Entidad Rol: define los perfiles de acceso (ATTENDEE, HOST, VENUE, ADMIN)
class Role(Base):
    __tablename__ = "roles"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Relación muchos a muchos con usuarios a través de UserRole
    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")

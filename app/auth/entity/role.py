from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


# Entidad Rol: define los perfiles de acceso (ATTENDEE, HOST, VENUE, ADMIN)
class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Relación muchos a muchos con usuarios a través de UserRole
    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")

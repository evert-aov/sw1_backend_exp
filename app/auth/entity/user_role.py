from sqlalchemy import Column, ForeignKey, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base, generate_uuid


# Tabla intermedia de asignación de roles a usuarios
class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(UUID(as_uuid=False), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)

    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")

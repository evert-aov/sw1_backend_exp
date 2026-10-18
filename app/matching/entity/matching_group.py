from datetime import datetime, timezone
import enum
from sqlalchemy import Column, Integer, DateTime, ForeignKey, Enum, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base, generate_uuid


class MatchingGroupStatusEnum(str, enum.Enum):
    OPEN = "OPEN"
    REACHED = "REACHED"    # Quórum alcanzado
    EXPIRED = "EXPIRED"


# Entidad GrupoMatching: agrupación dinámica de personas interesadas en una experiencia (CU-07)
class MatchingGroup(Base):
    __tablename__ = "matching_groups"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True)
    experience_id = Column(UUID(as_uuid=False), ForeignKey("experiences.id", ondelete="CASCADE"), nullable=False)

    target_quorum = Column(Integer, nullable=False)   # Meta de participantes
    current_members = Column(Integer, default=0, nullable=False)
    status = Column(Enum(MatchingGroupStatusEnum), default=MatchingGroupStatusEnum.OPEN, nullable=False)

    deadline = Column(DateTime, nullable=False)       # Fecha límite para completar el quórum
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relaciones
    experience = relationship("app.experience.entity.experience.Experience", back_populates="matching_groups")
    members = relationship("MatchingMember", back_populates="matching_group", cascade="all, delete-orphan")

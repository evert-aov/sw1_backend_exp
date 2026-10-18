from datetime import datetime, timezone
from sqlalchemy import Column, Integer, DateTime, ForeignKey, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base, generate_uuid


# Entidad MiembroMatching: vincula a un usuario postulado a un grupo de matching
class MatchingMember(Base):
    __tablename__ = "matching_members"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True)
    matching_group_id = Column(UUID(as_uuid=False), ForeignKey("matching_groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    matching_group = relationship("MatchingGroup", back_populates="members")
    user = relationship("app.auth.entity.user.User", back_populates="matching_memberships")

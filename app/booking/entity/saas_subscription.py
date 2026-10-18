from datetime import datetime, timezone
import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base, generate_uuid


class SubscriptionStatusEnum(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    PAST_DUE = "PAST_DUE"


# Entidad Suscripción SaaS: membresía activa gestionada con Stripe Billing
class SaaSSubscription(Base):
    __tablename__ = "saas_subscriptions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_id = Column(UUID(as_uuid=False), ForeignKey("saas_plans.id"), nullable=False)

    stripe_subscription_id = Column(String(100), unique=True, nullable=True, index=True)
    status = Column(Enum(SubscriptionStatusEnum), default=SubscriptionStatusEnum.ACTIVE, nullable=False)

    current_period_start = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    current_period_end = Column(DateTime, nullable=True)

    user = relationship("app.auth.entity.user.User", back_populates="saas_subscriptions")
    plan = relationship("SaaSPlan", back_populates="subscriptions")

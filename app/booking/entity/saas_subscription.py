from datetime import datetime, timezone
import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.core.database import Base


class SubscriptionStatusEnum(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    PAST_DUE = "PAST_DUE"


# Entidad Suscripción SaaS: membresía activa gestionada con Stripe Billing
class SaaSSubscription(Base):
    __tablename__ = "saas_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_id = Column(Integer, ForeignKey("saas_plans.id"), nullable=False)

    stripe_subscription_id = Column(String(100), unique=True, nullable=True, index=True)
    status = Column(Enum(SubscriptionStatusEnum), default=SubscriptionStatusEnum.ACTIVE, nullable=False)

    current_period_start = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    current_period_end = Column(DateTime, nullable=True)

    user = relationship("app.auth.entity.user.User", back_populates="saas_subscriptions")
    plan = relationship("SaaSPlan", back_populates="subscriptions")

from sqlalchemy import Column, Integer, String, Float, Boolean, JSON, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base, generate_uuid


# Entidad PlanSaaS: planes de suscripción para anfitriones y locales (CU-14)
class SaaSPlan(Base):
    __tablename__ = "saas_plans"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(50), unique=True, nullable=False)  # FREE, PRO, ENTERPRISE
    monthly_price = Column(Float, default=0.0, nullable=False)
    features_included = Column(JSON, default=dict)  # Métricas avanzadas, reportes PDF, sugerencias DJ/MC
    stripe_price_id = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)

    subscriptions = relationship("SaaSSubscription", back_populates="plan")

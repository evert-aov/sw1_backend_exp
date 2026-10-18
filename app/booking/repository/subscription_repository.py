from typing import Optional, List
from sqlalchemy.orm import Session
from app.booking.entity.saas_plan import SaaSPlan
from app.booking.entity.saas_subscription import SaaSSubscription, SubscriptionStatusEnum


# Repositorio para SaaSPlan y SaaSSubscription: únicamente firmas de métodos
class SubscriptionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_plans(self) -> List[SaaSPlan]:
        # Listar planes SaaS disponibles
        pass

    def get_plan_by_id(self, plan_id: str) -> Optional[SaaSPlan]:
        # Obtener plan por ID
        pass

    def create_subscription(self, subscription: SaaSSubscription) -> SaaSSubscription:
        # Registrar nueva suscripción
        pass

    def get_user_subscription(self, user_id: str) -> Optional[SaaSSubscription]:
        # Obtener suscripción activa de un usuario
        pass

    def update_subscription_status(self, subscription_id: str, status: SubscriptionStatusEnum) -> Optional[SaaSSubscription]:
        # Actualizar estado de suscripción por eventos Stripe Billing
        pass

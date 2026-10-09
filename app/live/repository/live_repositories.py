from typing import Optional, List
from sqlalchemy.orm import Session
from app.live.entity.live_session import LiveSession, LiveSessionStatusEnum
from app.live.entity.audience_metric import AudienceMetric
from app.live.entity.live_suggestion import LiveSuggestion
from app.live.entity.consent import Consent


# Repositorio para la entidad LiveSession: únicamente firmas de métodos
class LiveSessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, session_id: int) -> Optional[LiveSession]:
        # Buscar sesión en vivo por ID
        pass

    def create(self, session: LiveSession) -> LiveSession:
        # Inicializar sesión en vivo
        pass

    def update_status(self, session_id: int, status: LiveSessionStatusEnum) -> Optional[LiveSession]:
        # Cambiar estado de la sesión (ACTIVE, ENDED)
        pass


# Repositorio para métricas agregadas de audiencia (GDPR efímero)
class AudienceMetricRepository:
    def __init__(self, db: Session):
        self.db = db

    def save_metric(self, metric: AudienceMetric) -> AudienceMetric:
        # Persistir agregación numérica de atención/energía
        pass

    def get_by_session(self, session_id: int) -> List[AudienceMetric]:
        # Obtener serie temporal de métricas para reportes
        pass


# Repositorio para sugerencias de MC y DJ
class LiveSuggestionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_suggestion(self, suggestion: LiveSuggestion) -> LiveSuggestion:
        # Registrar sugerencia contextual generada
        pass

    def get_by_session(self, session_id: int) -> List[LiveSuggestion]:
        # Listar sugerencias emitidas durante la sesión
        pass


# Repositorio para consentimiento GDPR
class ConsentRepository:
    def __init__(self, db: Session):
        self.db = db

    def record_consent(self, consent: Consent) -> Consent:
        # Guardar consentimiento del asistente
        pass

    def check_user_consent(self, session_id: int, user_id: int) -> bool:
        # Verificar si el usuario autorizó análisis efímero
        pass

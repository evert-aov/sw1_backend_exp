from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.live.entity.live_session import LiveSession, LiveSessionStatusEnum
from app.live.entity.audience_metric import AudienceMetric
from app.live.entity.live_suggestion import LiveSuggestion
from app.live.entity.consent import Consent


class LiveSessionRepository:
    """Repositorio para la entidad LiveSession (CU-08, CU-09)."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, session_id: str) -> Optional[LiveSession]:
        """Buscar sesión en vivo por ID."""
        return self.db.query(LiveSession).filter(LiveSession.id == session_id).first()

    def create(self, session: LiveSession) -> LiveSession:
        """Inicializar sesión en vivo."""
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def update_status(self, session_id: str, status: LiveSessionStatusEnum) -> Optional[LiveSession]:
        """Cambiar estado de la sesión (ACTIVE, ENDED)."""
        session = self.get_by_id(session_id)
        if not session:
            return None
        session.status = status
        if status == LiveSessionStatusEnum.ENDED:
            session.ended_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(session)
        return session


class AudienceMetricRepository:
    """Repositorio para métricas agregadas de audiencia (GDPR efímero - HU-14, HU-15)."""

    def __init__(self, db: Session):
        self.db = db

    def save_metric(self, metric: AudienceMetric) -> AudienceMetric:
        """Persistir agregación numérica de atención/energía en BD."""
        self.db.add(metric)
        self.db.commit()
        self.db.refresh(metric)
        return metric

    def get_by_session(self, session_id: str) -> List[AudienceMetric]:
        """Obtener serie temporal de métricas para reportes ordenadas cronológicamente."""
        return (
            self.db.query(AudienceMetric)
            .filter(AudienceMetric.live_session_id == session_id)
            .order_by(AudienceMetric.recorded_at.asc())
            .all()
        )


class LiveSuggestionRepository:
    """Repositorio para sugerencias dinámicas de MC y DJ (CU-10, CU-11)."""

    def __init__(self, db: Session):
        self.db = db

    def create_suggestion(self, suggestion: LiveSuggestion) -> LiveSuggestion:
        """Registrar sugerencia contextual generada."""
        self.db.add(suggestion)
        self.db.commit()
        self.db.refresh(suggestion)
        return suggestion

    def get_by_session(self, session_id: str) -> List[LiveSuggestion]:
        """Listar sugerencias emitidas durante la sesión."""
        return (
            self.db.query(LiveSuggestion)
            .filter(LiveSuggestion.live_session_id == session_id)
            .order_by(LiveSuggestion.created_at.desc())
            .all()
        )


class ConsentRepository:
    """Repositorio para consentimiento GDPR de procesamiento efímero en RAM (HU-14)."""

    def __init__(self, db: Session):
        self.db = db

    def record_consent(self, consent: Consent) -> Consent:
        """Guardar consentimiento informado del asistente."""
        self.db.add(consent)
        self.db.commit()
        self.db.refresh(consent)
        return consent

    def check_user_consent(self, session_id: str, user_id: str) -> bool:
        """Verificar si el usuario autorizó análisis efímero."""
        existing = (
            self.db.query(Consent)
            .filter(
                Consent.live_session_id == session_id,
                Consent.user_id == user_id,
                Consent.accepted == True,  # noqa: E712
            )
            .first()
        )
        return existing is not None

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session

from app.live.entity.live_session import LiveSession, LiveSessionStatusEnum
from app.live.entity.audience_metric import AudienceMetric
from app.live.entity.live_suggestion import LiveSuggestion
from app.live.entity.consent import Consent


class LiveSessionRepository:
    """
    Repositorio de persistencia para la entidad LiveSession (CU-09 / HU-17).
    Administra la creación, consulta y actualización de estado de las sesiones en vivo.
    """

    def __init__(self, db: Session) -> None:
        """
        Inicializa el repositorio con la sesión de base de datos activa.

        Args:
            db (Session): Sesión transaccional de SQLAlchemy.
        """
        self.db = db

    def get_by_id(self, session_id: str) -> Optional[LiveSession]:
        """
        Busca una sesión en vivo por su identificador único (UUID).

        Args:
            session_id (str): UUID de la sesión a consultar.

        Returns:
            Optional[LiveSession]: La entidad de la sesión si existe, o None en caso contrario.
        """
        return self.db.query(LiveSession).filter(LiveSession.id == session_id).first()

    def get_active_by_experience(self, experience_id: str) -> Optional[LiveSession]:
        """
        Busca la sesión en vivo activa asociada a una experiencia específica.

        Args:
            experience_id (str): UUID de la experiencia.

        Returns:
            Optional[LiveSession]: La sesión activa si existe, o None si no hay sesión en curso.
        """
        return (
            self.db.query(LiveSession)
            .filter(
                LiveSession.experience_id == experience_id,
                LiveSession.status == LiveSessionStatusEnum.ACTIVE,
            )
            .first()
        )

    def create(self, session: LiveSession) -> LiveSession:
        """
        Persiste una nueva sesión en vivo en la base de datos.

        Args:
            session (LiveSession): Objeto entidad a guardar.

        Returns:
            LiveSession: La entidad persistida con identificador y fecha de creación asignados.
        """
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def update_status(self, session_id: str, status: LiveSessionStatusEnum) -> Optional[LiveSession]:
        """
        Actualiza el estado operativo de una sesión en vivo (INITIALIZED, ACTIVE, ENDED).

        Args:
            session_id (str): UUID de la sesión.
            status (LiveSessionStatusEnum): Nuevo estado a asignar.

        Returns:
            Optional[LiveSession]: La sesión modificada, o None si no se encontró el registro.
        """
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
    """
    Repositorio para métricas agregadas de audiencia (CU-10 / HU-15, HU-17).
    Almacena únicamente agregaciones numéricas efímeras respetando la privacidad GDPR.
    """

    def __init__(self, db: Session) -> None:
        """
        Inicializa el repositorio de métricas.

        Args:
            db (Session): Sesión transaccional de SQLAlchemy.
        """
        self.db = db

    def save_metric(self, metric: AudienceMetric) -> AudienceMetric:
        """
        Persiste una medición agregada de atención, emoción y volumen de audiencia.

        Args:
            metric (AudienceMetric): Entidad numérica con las métricas calculadas.

        Returns:
            AudienceMetric: Entidad persistida con clave generada.
        """
        self.db.add(metric)
        self.db.commit()
        self.db.refresh(metric)
        return metric

    def get_by_session(self, session_id: str) -> List[AudienceMetric]:
        """
        Recupera la serie temporal histórica de métricas de una sesión ordenada cronológicamente.

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            List[AudienceMetric]: Lista de mediciones agregadas ordenadas por tiempo.
        """
        return (
            self.db.query(AudienceMetric)
            .filter(AudienceMetric.live_session_id == session_id)
            .order_by(AudienceMetric.recorded_at.asc())
            .all()
        )

    def get_latest(self, session_id: str) -> Optional[AudienceMetric]:
        """
        Obtiene la última medición agregada registrada para una sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            Optional[AudienceMetric]: La medición más reciente o None si no hay registros.
        """
        return (
            self.db.query(AudienceMetric)
            .filter(AudienceMetric.live_session_id == session_id)
            .order_by(AudienceMetric.recorded_at.desc())
            .first()
        )


class LiveSuggestionRepository:
    """
    Repositorio para sugerencias contextuales del Asistente MC y DJ Virtual (CU-11 / HU-18..HU-21).
    """

    def __init__(self, db: Session) -> None:
        """
        Inicializa el repositorio de sugerencias.

        Args:
            db (Session): Sesión transaccional de SQLAlchemy.
        """
        self.db = db

    def create_suggestion(self, suggestion: LiveSuggestion) -> LiveSuggestion:
        """
        Registra una sugerencia contextual emitida en tiempo real.

        Args:
            suggestion (LiveSuggestion): Objeto sugerencia a registrar.

        Returns:
            LiveSuggestion: Registro almacenado con identificador asignado.
        """
        self.db.add(suggestion)
        self.db.commit()
        self.db.refresh(suggestion)
        return suggestion

    def get_by_session(self, session_id: str) -> List[LiveSuggestion]:
        """
        Lista todas las sugerencias generadas durante el curso de una sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            List[LiveSuggestion]: Sugerencias emitidas ordenadas cronológicamente.
        """
        return (
            self.db.query(LiveSuggestion)
            .filter(LiveSuggestion.live_session_id == session_id)
            .order_by(LiveSuggestion.created_at.asc())
            .all()
        )


class ConsentRepository:
    """
    Repositorio para registrar el consentimiento informado GDPR (HU-14).
    """

    def __init__(self, db: Session) -> None:
        """
        Inicializa el repositorio de consentimientos.

        Args:
            db (Session): Sesión transaccional de SQLAlchemy.
        """
        self.db = db

    def record_consent(self, consent: Consent) -> Consent:
        """
        Registra la aceptación del consentimiento GDPR de un asistente.

        Args:
            consent (Consent): Entidad de consentimiento a persistir.

        Returns:
            Consent: Registro persistido en la base de datos.
        """
        self.db.add(consent)
        self.db.commit()
        self.db.refresh(consent)
        return consent

    def check_user_consent(self, session_id: str, user_id: str) -> bool:
        """
        Verifica si un usuario particular ha otorgado consentimiento explícito en la sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.
            user_id (str): UUID del usuario asistente.

        Returns:
            bool: True si el usuario aceptó la política; False en caso contrario.
        """
        record = (
            self.db.query(Consent)
            .filter(
                Consent.live_session_id == session_id,
                Consent.user_id == user_id,
                Consent.accepted.is_(True),
            )
            .first()
        )
        return record is not None

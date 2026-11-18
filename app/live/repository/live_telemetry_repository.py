from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.live.entity.audience_metric import AudienceMetric
from app.live.entity.live_session import LiveSession


class LiveTelemetryRepository:
    """
    Repositorio de solo lectura para la telemetría agregada de la consola en vivo (HU-17).

    Lee las métricas numéricas que el pipeline de visión (HU-13 a HU-16) persiste en `audience_metrics`.
    """

    def __init__(self, db: Session) -> None:
        """
        Inicializa el repositorio con una sesión de base de datos.

        Args:
            db (Session): Sesión activa de SQLAlchemy.
        """
        self.db = db

    def get_session(self, session_id: str) -> LiveSession | None:
        """
        Busca una sesión en vivo por su ID.

        Args:
            session_id (str): UUID canónico de la sesión en vivo.

        Returns:
            LiveSession | None: La sesión encontrada o None si no existe.
        """
        return self.db.get(LiveSession, session_id)

    def get_metrics_after(self, session_id: str, after: datetime, limit: int) -> list[AudienceMetric]:
        """
        Obtiene las métricas registradas después de un instante, en orden cronológico.

        Args:
            session_id (str): UUID de la sesión en vivo.
            after (datetime): Instante exclusivo desde el cual buscar (UTC sin zona horaria).
            limit (int): Cantidad máxima de métricas a devolver (las más recientes).

        Returns:
            list[AudienceMetric]: Métricas posteriores a `after`, de la más antigua a la más reciente.
        """
        rows = (
            self.db.query(AudienceMetric)
            .filter(
                AudienceMetric.live_session_id == session_id,
                AudienceMetric.recorded_at > after,
            )
            .order_by(AudienceMetric.recorded_at.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(rows))

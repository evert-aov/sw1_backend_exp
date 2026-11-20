from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
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

    def get_metrics_after(
        self, session_id: str, after: datetime, limit: int
    ) -> list[tuple[AudienceMetric, datetime]]:
        """
        Obtiene las métricas registradas después de un instante, en orden cronológico.

        `recorded_at` es una columna sin zona horaria: PostgreSQL guarda en ella la hora convertida a
        la zona de la sesión (`TimeZone`, por ejemplo America/La_Paz) cuando el pipeline de visión
        escribe fechas UTC con zona. Por eso la comparación y el resultado se hacen en UTC real
        interpretando la columna con esa misma zona.

        Args:
            session_id (str): UUID de la sesión en vivo.
            after (datetime): Instante exclusivo en UTC con zona horaria.
            limit (int): Cantidad máxima de métricas a devolver (las más recientes).

        Returns:
            list[tuple[AudienceMetric, datetime]]: Métricas posteriores a `after` con su instante en
                UTC, de la más antigua a la más reciente.
        """
        recorded_utc = func.timezone(func.current_setting("TimeZone"), AudienceMetric.recorded_at)
        rows = (
            self.db.query(AudienceMetric, recorded_utc.label("recorded_utc"))
            .filter(
                AudienceMetric.live_session_id == session_id,
                recorded_utc > after,
            )
            .order_by(AudienceMetric.recorded_at.desc())
            .limit(limit)
            .all()
        )
        return [(metric, recorded) for metric, recorded in reversed(rows)]

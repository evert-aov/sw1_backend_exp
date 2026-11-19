from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.experience.entity.experience import Experience
from app.live.entity.live_session import LiveSession
from app.live.entity.live_suggestion import LiveSuggestion
from app.live.entity.mc_alert import McAlert, McAlertStatusEnum
from app.live.entity.mc_dynamic import McDynamic
from app.live.entity.monitor_push_device import MonitorPushDevice


class McAssistantRepository:
    """Acceso a datos del Asistente de Maestro de Ceremonias (CU-11 / HU-18, HU-19)."""

    def __init__(self, db: Session) -> None:
        """
        Inicializa el repositorio con una sesión de base de datos.

        Args:
            db (Session): Sesión activa de SQLAlchemy.
        """
        self.db = db

    def list_active_dynamics(self) -> list[McDynamic]:
        """
        Lista las dinámicas activas del catálogo.

        Returns:
            list[McDynamic]: Dinámicas activas ordenadas por código.
        """
        return (
            self.db.query(McDynamic)
            .filter(McDynamic.is_active.is_(True))
            .order_by(McDynamic.code)
            .all()
        )

    def get_dynamic(self, dynamic_id: str | None) -> McDynamic | None:
        """
        Busca una dinámica por ID.

        Args:
            dynamic_id (str | None): ID de la dinámica.

        Returns:
            McDynamic | None: La dinámica o None.
        """
        return self.db.get(McDynamic, dynamic_id) if dynamic_id else None

    def get_session_modality(self, session_id: str) -> str | None:
        """
        Obtiene la modalidad de la experiencia transmitida en la sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            str | None: `IN_PERSON`, `VIRTUAL`, `HYBRID` o None si no existe.
        """
        row = (
            self.db.query(Experience.modality)
            .join(LiveSession, LiveSession.experience_id == Experience.id)
            .filter(LiveSession.id == session_id)
            .first()
        )
        if row is None:
            return None
        modality = row[0]
        return modality.value if hasattr(modality, "value") else str(modality)

    def get_alert(self, alert_id: str) -> McAlert | None:
        """
        Busca una alerta por ID.

        Args:
            alert_id (str): UUID de la alerta.

        Returns:
            McAlert | None: La alerta o None.
        """
        return self.db.get(McAlert, alert_id)

    def get_active_alert(self, session_id: str) -> McAlert | None:
        """
        Obtiene la alerta activa más reciente de una sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            McAlert | None: Alerta en estado ACTIVE o None.
        """
        return (
            self.db.query(McAlert)
            .filter(
                McAlert.live_session_id == session_id, McAlert.status == McAlertStatusEnum.ACTIVE
            )
            .order_by(McAlert.created_at.desc())
            .first()
        )

    def get_latest_break_end(self, session_id: str) -> datetime | None:
        """
        Obtiene el fin de la pausa aplicada más reciente de la sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            datetime | None: Fin de la última pausa (UTC sin zona) o None.
        """
        row = (
            self.db.query(McAlert.break_ends_at)
            .filter(McAlert.live_session_id == session_id, McAlert.break_ends_at.isnot(None))
            .order_by(McAlert.break_ends_at.desc())
            .first()
        )
        return row[0] if row else None

    def list_alerts(self, session_id: str, limit: int) -> list[McAlert]:
        """
        Lista las alertas de una sesión de la más reciente a la más antigua.

        Args:
            session_id (str): UUID de la sesión en vivo.
            limit (int): Cantidad máxima de alertas.

        Returns:
            list[McAlert]: Alertas de la sesión.
        """
        return (
            self.db.query(McAlert)
            .filter(McAlert.live_session_id == session_id)
            .order_by(McAlert.created_at.desc())
            .limit(limit)
            .all()
        )

    def recent_dynamic_codes(self, session_id: str, limit: int = 5) -> list[str]:
        """
        Obtiene los códigos de las dinámicas propuestas recientemente en la sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.
            limit (int): Cantidad de alertas recientes a considerar.

        Returns:
            list[str]: Códigos, del más antiguo al más reciente.
        """
        rows = (
            self.db.query(McDynamic.code)
            .join(McAlert, McAlert.dynamic_id == McDynamic.id)
            .filter(McAlert.live_session_id == session_id)
            .order_by(McAlert.created_at.desc())
            .limit(limit)
            .all()
        )
        return [row[0] for row in reversed(rows)]

    def add(self, entity: McAlert | LiveSuggestion | MonitorPushDevice) -> None:
        """
        Agrega una entidad a la transacción en curso.

        Args:
            entity (McAlert | LiveSuggestion | MonitorPushDevice): Entidad a persistir.
        """
        self.db.add(entity)

    def get_suggestion(self, suggestion_id: str | None) -> LiveSuggestion | None:
        """
        Busca la sugerencia asociada a una alerta.

        Args:
            suggestion_id (str | None): ID de la sugerencia.

        Returns:
            LiveSuggestion | None: La sugerencia o None.
        """
        return self.db.get(LiveSuggestion, suggestion_id) if suggestion_id else None

    def get_push_device_by_token(self, fcm_token: str) -> MonitorPushDevice | None:
        """
        Busca un dispositivo push por su token de Firebase.

        Args:
            fcm_token (str): Token de Firebase Cloud Messaging.

        Returns:
            MonitorPushDevice | None: El dispositivo o None.
        """
        return (
            self.db.query(MonitorPushDevice)
            .filter(MonitorPushDevice.fcm_token == fcm_token)
            .first()
        )

    def list_push_devices(self, session_id: str, now: datetime) -> list[MonitorPushDevice]:
        """
        Lista los dispositivos vigentes vinculados a la sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.
            now (datetime): Instante actual (UTC sin zona).

        Returns:
            list[MonitorPushDevice]: Dispositivos cuya vinculación no venció.
        """
        return (
            self.db.query(MonitorPushDevice)
            .filter(
                MonitorPushDevice.live_session_id == session_id, MonitorPushDevice.expires_at > now
            )
            .all()
        )

    def delete_push_tokens(self, tokens: list[str]) -> None:
        """
        Elimina dispositivos cuyos tokens Firebase ya no son válidos.

        Args:
            tokens (list[str]): Tokens rechazados por Firebase.
        """
        if tokens:
            self.db.query(MonitorPushDevice).filter(MonitorPushDevice.fcm_token.in_(tokens)).delete(
                synchronize_session=False
            )

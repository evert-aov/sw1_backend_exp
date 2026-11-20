"""Registro de tokens FCM por usuario y envío asíncrono de notificaciones push (Android/iOS)."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

from app.core.database import SessionLocal, engine, generate_uuid
from app.live.service.push_notification_service import PushMessage, PushNotificationService

logger = logging.getLogger(__name__)

UserPushBase = declarative_base()
_table_ready = False

NOTIFICATION_TITLES: dict[str, str] = {
    "BOOKING_CONFIRMED": "¡Reserva confirmada!",
    "NEW_BOOKING_HOST": "Nueva reserva en tu evento",
    "EVENT_STARTED": "¡Tu evento acaba de comenzar!",
    "EVENT_FINISHED": "Evento finalizado",
    "EVENT_CANCELLED": "Evento cancelado",
    "QUORUM_CONFIRMED": "¡Evento confirmado (quórum alcanzado)!",
    "GROUP_CONFIRMED": "¡Grupo de matching confirmado!",
    "GROUP_EXPIRED": "Grupo de matching vencido",
    "REFUND_PROCESSED": "Reembolso procesado",
}


class UserPushDevice(UserPushBase):
    __tablename__ = "user_push_devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    fcm_token: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, default="android")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False
    )


def ensure_user_push_table() -> None:
    global _table_ready
    if not _table_ready:
        UserPushDevice.__table__.create(bind=engine, checkfirst=True)
        _table_ready = True


def register_user_push_device(user_id: str, fcm_token: str, platform: str = "android") -> bool:
    """Registra o reasigna un token FCM al usuario autenticado."""
    ensure_user_push_table()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as db:
        existing = db.query(UserPushDevice).filter(UserPushDevice.fcm_token == fcm_token).first()
        if existing:
            existing.user_id = str(user_id)
            existing.platform = platform
            existing.updated_at = now
        else:
            db.add(
                UserPushDevice(
                    user_id=str(user_id),
                    fcm_token=fcm_token,
                    platform=platform,
                    updated_at=now,
                )
            )
        db.commit()
    return PushNotificationService().enabled


def remove_user_push_device(user_id: str, fcm_token: str) -> None:
    ensure_user_push_table()
    with SessionLocal() as db:
        (
            db.query(UserPushDevice)
            .filter(UserPushDevice.user_id == str(user_id), UserPushDevice.fcm_token == fcm_token)
            .delete(synchronize_session=False)
        )
        db.commit()


def _send_push_worker(
    user_ids: list[str],
    kind: str,
    body: str,
    experience_id: str,
) -> None:
    try:
        push_service = PushNotificationService()
        if not push_service.enabled or not user_ids:
            return
        ensure_user_push_table()
        with SessionLocal() as db:
            devices = (
                db.query(UserPushDevice)
                .filter(UserPushDevice.user_id.in_(user_ids))
                .all()
            )
            tokens = [d.fcm_token for d in devices if d.fcm_token]
        if not tokens:
            return

        title = NOTIFICATION_TITLES.get(kind, "EXPERIENCIA")
        messages = [
            PushMessage(
                token=tok,
                title=title,
                body=body,
                data={"kind": kind, "experience_id": str(experience_id)},
            )
            for tok in tokens
        ]
        invalid_tokens = push_service.send(messages)
        if invalid_tokens:
            with SessionLocal() as db:
                (
                    db.query(UserPushDevice)
                    .filter(UserPushDevice.fcm_token.in_(invalid_tokens))
                    .delete(synchronize_session=False)
                )
                db.commit()
    except Exception as exc:
        logger.warning("No se pudo enviar push FCM (%s): %s", kind, exc)


def dispatch_push_to_users(
    users: Iterable[str],
    *,
    kind: str,
    message: str,
    experience_id: str,
) -> None:
    """Envía notificaciones push FCM en segundo plano sin bloquear la transacción HTTP."""
    user_ids = sorted({str(u) for u in users if u})
    if not user_ids:
        return
    threading.Thread(
        target=_send_push_worker,
        args=(user_ids, kind, message, str(experience_id)),
        daemon=True,
    ).start()

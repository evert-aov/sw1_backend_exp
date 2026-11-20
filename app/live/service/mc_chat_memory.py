"""Persistencia de memoria conversacional del Asistente MC por evento en PostgreSQL."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.database import SessionLocal, engine
from app.experience.entity.experience import Experience
from app.live.entity.live_session import LiveSession
from app.live.entity.mc_chat_message import McChatMessage

_table_ready = False


def ensure_chat_table() -> None:
    """Garantiza de forma idempotente que la tabla `mc_chat_messages` exista en PostgreSQL."""
    global _table_ready
    if not _table_ready:
        McChatMessage.__table__.create(bind=engine, checkfirst=True)
        _table_ready = True


def resolve_event_context(session_id: str) -> tuple[str, dict[str, Any] | None]:
    """
    Resuelve la clave canónica del evento (`experience.id` cuando existe) y sus metadatos.
    Acepta tanto un `live_sessions.id` como un `experiences.id` o un identificador demo.
    """
    raw = str(session_id or "").strip() or "session-demo"
    try:
        canonical = str(UUID(raw))
    except ValueError:
        return raw, None

    with SessionLocal() as db:
        live_session = db.get(LiveSession, canonical)
        experience = (
            db.get(Experience, live_session.experience_id)
            if live_session is not None
            else db.get(Experience, canonical)
        )
        if experience is None:
            return canonical, None

        category_name = experience.category.name if getattr(experience, "category", None) else None
        modality = (
            getattr(experience.modality, "value", str(experience.modality))
            if experience.modality
            else None
        )
        status_value = (
            getattr(experience.status, "value", str(experience.status))
            if experience.status
            else None
        )
        active_session = live_session
        if active_session is None:
            from app.live.entity.live_session import LiveSessionStatusEnum

            active_session = (
                db.query(LiveSession)
                .filter(
                    LiveSession.experience_id == experience.id,
                    LiveSession.status.in_(
                        [LiveSessionStatusEnum.INITIALIZED, LiveSessionStatusEnum.ACTIVE]
                    ),
                )
                .first()
            )
        event_key = str(experience.id)
        return event_key, {
            "id": event_key,
            "title": str(experience.title),
            "description": experience.description,
            "category": category_name,
            "modality": modality,
            "status": status_value,
            "live_session_id": str(active_session.id) if active_session is not None else None,
        }


def list_event_messages(event_key: str, limit: int = 50) -> list[dict[str, Any]]:
    """Devuelve el historial persistido de un evento en orden cronológico."""
    ensure_chat_table()
    with SessionLocal() as db:
        rows = (
            db.query(McChatMessage)
            .filter(McChatMessage.event_key == event_key)
            .order_by(McChatMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        rows.reverse()
        return [
            {
                "id": row.id,
                "role": row.role,
                "content": row.content,
                "provider": row.provider,
                "model": row.model,
                "created_at": (
                    row.created_at.replace(tzinfo=timezone.utc)
                    if row.created_at.tzinfo is None
                    else row.created_at
                ),
            }
            for row in rows
        ]


def save_chat_exchange(
    *,
    event_key: str,
    user_message: str,
    assistant_reply: str,
    provider: str,
    model: str,
) -> None:
    """Guarda el turno del usuario y la respuesta de la IA asociados al evento."""
    ensure_chat_table()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    reply_at = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as db:
        db.add(
            McChatMessage(
                event_key=event_key,
                role="user",
                content=user_message,
                created_at=now,
            )
        )
        db.add(
            McChatMessage(
                event_key=event_key,
                role="assistant",
                content=assistant_reply,
                provider=provider,
                model=model,
                created_at=reply_at,
            )
        )
        db.commit()


def clear_event_messages(event_key: str) -> int:
    """Elimina la memoria de chat de un evento específico."""
    ensure_chat_table()
    with SessionLocal() as db:
        deleted = (
            db.query(McChatMessage)
            .filter(McChatMessage.event_key == event_key)
            .delete(synchronize_session=False)
        )
        db.commit()
        return int(deleted or 0)

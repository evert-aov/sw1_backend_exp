"""Publicación transaccional: no confirma ni abre una sesión separada del caso de uso."""

from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.notifications.entity import Notification


class NotificationService:
    def __init__(self, db):
        self.db = db

    def stage(self, experience_id: str, users, kind: str, generation, message: str) -> None:
        """La restricción única absorbe reintentos y cruces simultáneos del mismo umbral."""
        values = [{"user_id": user_id, "experience_id": experience_id, "kind": kind,
                   "message": message, "dedupe_key": f"{kind}:{experience_id}:{generation}:{user_id}"}
                  for user_id in sorted(set(users))]
        if values:
            self.db.execute(insert(Notification).values(values).on_conflict_do_nothing(index_elements=[Notification.dedupe_key]))

    def paid_audience(self, experience):
        from app.booking.entity.booking import Booking, BookingStatusEnum
        return {experience.host_id, *self.db.scalars(select(Booking.user_id).where(
            Booking.experience_id == experience.id, Booking.status == BookingStatusEnum.PAID,
        ))}

    def confirmation(self, experience, booking, *, crossed: bool) -> None:
        users = self.paid_audience(experience) if crossed else {booking.user_id}
        self.stage(experience.id, users, "QUORUM_CONFIRMED", experience.quorum_generation,
                   f"{experience.title}: el evento alcanzó el mínimo de cupos confirmados.")

    def list_own(self, user_id: str, limit: int, offset: int):
        return self.db.scalars(select(Notification).where(Notification.user_id == user_id).order_by(
            Notification.created_at.desc(), Notification.id.desc()).limit(limit).offset(offset)).all()

    def mark_read(self, notification_id: str, user_id: str):
        from app.booking.service.booking_service import uuid_string
        item = self.db.scalar(select(Notification).where(
            Notification.id == uuid_string(notification_id), Notification.user_id == user_id,
        ).with_for_update())
        if not item:
            raise HTTPException(status_code=404, detail="Aviso no encontrado")
        item.read_at = item.read_at or datetime.now(timezone.utc)
        self.db.commit()
        return item

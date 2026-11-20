"""Publicación transaccional: no confirma ni abre una sesión separada del caso de uso."""

from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.notifications.entity import Notification
from app.notifications.user_push_device import dispatch_push_to_users


class NotificationService:
    def __init__(self, db):
        self.db = db

    def stage(self, experience_id: str, users, kind: str, generation, message: str) -> None:
        """La restricción única absorbe reintentos y cruces simultáneos del mismo umbral."""
        unique_users = sorted(set(users))
        values = [{"user_id": user_id, "experience_id": experience_id, "kind": kind,
                   "message": message, "dedupe_key": f"{kind}:{experience_id}:{generation}:{user_id}"}
                  for user_id in unique_users]
        if values:
            self.db.execute(insert(Notification).values(values).on_conflict_do_nothing(index_elements=[Notification.dedupe_key]))
            dispatch_push_to_users(unique_users, kind=kind, message=message, experience_id=experience_id)

    def paid_audience(self, experience):
        from app.booking.entity.booking import Booking, BookingStatusEnum
        return {experience.host_id, *self.db.scalars(select(Booking.user_id).where(
            Booking.experience_id == experience.id, Booking.status == BookingStatusEnum.PAID,
        ))}

    def paid_attendees(self, experience):
        from app.booking.entity.booking import Booking, BookingStatusEnum
        return set(self.db.scalars(select(Booking.user_id).where(
            Booking.experience_id == experience.id, Booking.status == BookingStatusEnum.PAID,
        )))

    def confirmation(self, experience, booking, *, crossed: bool) -> None:
        users = self.paid_audience(experience) if crossed else {booking.user_id}
        self.stage(experience.id, users, "QUORUM_CONFIRMED", experience.quorum_generation,
                   f"{experience.title}: el evento alcanzó el mínimo de cupos confirmados.")

    def booking_confirmed(self, experience, booking) -> None:
        """Notifica al asistente que su reserva fue confirmada y al anfitrión de la nueva reserva."""
        qty = int(booking.quantity or 1)
        cupos_txt = "cupo" if qty == 1 else "cupos"
        self.stage(
            experience.id,
            {booking.user_id},
            "BOOKING_CONFIRMED",
            str(booking.id),
            f"¡Reserva confirmada! Tienes {qty} {cupos_txt} para {experience.title}.",
        )
        if str(experience.host_id) != str(booking.user_id):
            self.stage(
                experience.id,
                {experience.host_id},
                "NEW_BOOKING_HOST",
                str(booking.id),
                f"Nueva reserva: {qty} {cupos_txt} confirmado(s) en {experience.title} ({experience.reserved_slots}/{experience.max_capacity}).",
            )

    def event_started(self, experience) -> None:
        """Avisa a todos los asistentes registrados cuando el anfitrión inicia el evento (LIVE)."""
        attendees = self.paid_attendees(experience)
        if attendees:
            self.stage(
                experience.id,
                attendees,
                "EVENT_STARTED",
                int(datetime.now(timezone.utc).timestamp()),
                f"¡{experience.title} acaba de comenzar! Ya puedes ingresar al evento.",
            )

    def event_finished(self, experience) -> None:
        """Avisa a los asistentes registrados cuando el evento finaliza."""
        attendees = self.paid_attendees(experience)
        if attendees:
            self.stage(
                experience.id,
                attendees,
                "EVENT_FINISHED",
                int(datetime.now(timezone.utc).timestamp()),
                f"¡Gracias por participar en {experience.title}! El evento ha finalizado.",
            )

    def event_cancelled(self, experience) -> None:
        """Avisa a los asistentes registrados si el evento es cancelado."""
        attendees = self.paid_attendees(experience)
        if attendees:
            self.stage(
                experience.id,
                attendees,
                "EVENT_CANCELLED",
                int(datetime.now(timezone.utc).timestamp()),
                f"{experience.title} fue cancelado por el anfitrión.",
            )

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

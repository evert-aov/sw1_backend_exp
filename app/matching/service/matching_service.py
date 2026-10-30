"""Matching explicable por intereses y disponibilidad, separado de los cupos pagados."""

from datetime import datetime, timedelta, timezone
import unicodedata
from fastapi import HTTPException
from app.auth.entity.user import User
from app.booking.service.booking_service import BookingService, utc, uuid_string
from app.experience.entity.experience import Experience, ExperienceStatusEnum
from app.matching.dto.matching_dto import MatchingApplicationDTO, MatchingGroupResponseDTO
from app.matching.entity.matching_group import MatchingGroup, MatchingGroupStatusEnum
from app.matching.entity.matching_member import MatchingMember
from app.notifications.service import NotificationService
from app.matching.repository.matching_repository import MatchingRepository


def normalized(value: str | None) -> str:
    """Conserva equivalencia de tildes, mayúsculas y espacios al comparar preferencias."""
    return " ".join("".join(char for char in unicodedata.normalize("NFKD", (value or "").casefold()) if not unicodedata.combining(char)).split())


def affinity(left, right) -> float:
    """Jaccard de etiquetas normalizadas; no se presenta como un modelo entrenado."""
    a, b = {normalized(value) for value in left if value.strip()}, {normalized(value) for value in right if value.strip()}
    return len(a & b) / len(a | b) if a or b else 0.0


class MatchingAlgorithmService:
    def __init__(self, db):
        self.db = db
        self.bookings = BookingService(db)
        self.repository = MatchingRepository(db)

    def _groups(self, experience_id: str):
        return self.repository.list_by_experience(experience_id)

    def _response(self, group, experience, user_id, interests) -> MatchingGroupResponseDTO:
        now = datetime.now(timezone.utc)
        expired = utc(group.deadline) <= now or experience.status in {ExperienceStatusEnum.CANCELLED, ExperienceStatusEnum.FINISHED}
        members = group.members
        scores = [affinity(interests, (member.preferences or {}).get("interests", [])) for member in members if member.user_id != user_id]
        return MatchingGroupResponseDTO(
            id=group.id, experience_id=group.experience_id, target_quorum=group.target_quorum,
            current_members=len(members), status=MatchingGroupStatusEnum.EXPIRED if expired else (
                MatchingGroupStatusEnum.REACHED if len(members) >= group.target_quorum else MatchingGroupStatusEnum.OPEN),
            deadline=utc(group.deadline), created_at=utc(group.created_at),
            is_quorum_reached=not expired and len(members) >= group.target_quorum,
            is_member=any(member.user_id == user_id for member in members),
            affinity_score=sum(scores) / len(scores) if scores else 1.0,
            experience_confirmed=experience.status == ExperienceStatusEnum.CONFIRMED,
            paid_slots=experience.reserved_slots,
        )

    def _context(self, experience_id, user_id, *, lock=False):
        user = self.db.get(User, user_id)
        experience = (self.bookings.repository.lock_experience(experience_id) if lock
                      else self.db.get(Experience, experience_id))
        if not user or not user.is_active:
            raise HTTPException(status_code=403, detail="Usuario no disponible")
        if not experience:
            raise HTTPException(status_code=404, detail="Experiencia no encontrada")
        interests = list(user.interests or [])
        if experience.category:
            interests.append(experience.category.name)
        return user, experience, interests

    def get_group_status(self, experience_id: str, user_id: str):
        """Consultar nunca crea grupos, inscribe usuarios ni confirma reservas."""
        experience_id = uuid_string(experience_id)
        user, experience, interests = self._context(experience_id, user_id)
        groups = self._groups(experience_id)
        own = next((group for group in groups if any(item.user_id == user_id for item in group.members)), None)
        if own:
            return self._response(own, experience, user_id, interests)
        active = [group for group in groups if utc(group.deadline) > datetime.now(timezone.utc)]
        if not active:
            raise HTTPException(status_code=404, detail="Todavía no hay un grupo disponible; puedes postularte")
        selected = max(active, key=lambda group: self._response(group, experience, user_id, interests).affinity_score)
        return self._response(selected, experience, user_id, interests)

    def apply_for_matching(self, user_id: str, dto: MatchingApplicationDTO):
        """Serializa por experiencia; repetir postulación devuelve la membresía existente."""
        try:
            experience_id = uuid_string(dto.experience_id)
            user, experience, interests = self._context(experience_id, user_id, lock=True)
            now = datetime.now(timezone.utc)
            deadline = utc(experience.event_date) - timedelta(minutes=30)
            if experience.status not in {ExperienceStatusEnum.OPEN, ExperienceStatusEnum.CONFIRMED} or deadline <= now:
                raise HTTPException(status_code=409, detail="La experiencia ya no admite postulaciones")
            if dto.available_from is not None:
                end = utc(experience.event_date) + timedelta(minutes=experience.duration_minutes or 120)
                if utc(dto.available_from) > utc(experience.event_date) or utc(dto.available_to) < end:
                    raise HTTPException(status_code=409, detail="La experiencia no coincide con tu disponibilidad")
            if dto.preferred_zone and experience.venue and normalized(dto.preferred_zone) != normalized(experience.venue.zone):
                raise HTTPException(status_code=409, detail="La experiencia no está en la zona solicitada")
            groups = self._groups(experience_id)
            own = next((group for group in groups if any(item.user_id == user_id for item in group.members)), None)
            if own:
                result = self._response(own, experience, user_id, interests)
                self.db.commit()
                return result
            candidates = [group for group in groups if utc(group.deadline) > now and len(group.members) < experience.max_capacity]
            ranked = sorted(candidates, key=lambda group: self._response(group, experience, user_id, interests).affinity_score, reverse=True)
            group = next((item for item in ranked if self._response(item, experience, user_id, interests).affinity_score >= 0.15), None)
            if group is None:
                group = MatchingGroup(experience_id=experience.id, target_quorum=experience.min_capacity,
                                      current_members=0, status=MatchingGroupStatusEnum.OPEN,
                                      deadline=deadline.replace(tzinfo=None), members=[])
                self.repository.create_group(group)
            member = MatchingMember(user_id=user_id, preferences={
                "interests": interests, "available_from": dto.available_from.isoformat() if dto.available_from else None,
                "available_to": dto.available_to.isoformat() if dto.available_to else None, "zone": dto.preferred_zone,
            })
            group.members.append(member)
            group.current_members = len(group.members)
            group.status = MatchingGroupStatusEnum.REACHED if group.current_members >= group.target_quorum else MatchingGroupStatusEnum.OPEN
            self.db.flush()
            if group.status == MatchingGroupStatusEnum.REACHED:
                NotificationService(self.db).stage(experience.id, {experience.host_id, *(item.user_id for item in group.members)},
                    "MATCHING_READY", group.id, f"{experience.title}: el grupo reunió interés suficiente. Cada asistente debe reservar y pagar para confirmar cupos.")
            result = self._response(group, experience, user_id, interests)
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    def leave_group(self, experience_id: str, user_id: str):
        """Retira interés sin alterar reservas ni cupos pagados."""
        try:
            _, experience, _ = self._context(uuid_string(experience_id), user_id, lock=True)
            for group in self._groups(experience.id):
                member = next((item for item in group.members if item.user_id == user_id), None)
                if member:
                    group.members.remove(member)
                    group.current_members = len(group.members)
                    group.status = (MatchingGroupStatusEnum.EXPIRED if utc(group.deadline) <= datetime.now(timezone.utc)
                                    else MatchingGroupStatusEnum.REACHED if group.current_members >= group.target_quorum else MatchingGroupStatusEnum.OPEN)
            self.db.commit()
            return {"status": "left"}
        except Exception:
            self.db.rollback()
            raise

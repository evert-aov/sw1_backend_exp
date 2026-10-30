"""Marca grupos vencidos sin convertir interés en reservas ni tocar cupos pagados."""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, timezone
from sqlalchemy import select
from app.core.database import SessionLocal, init_db
from app.booking.repository.booking_repository import BookingRepository
from app.matching.entity.matching_group import MatchingGroup, MatchingGroupStatusEnum
from app.notifications.service import NotificationService


def main() -> int:
    init_db()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as db:
        ids = db.scalars(select(MatchingGroup.experience_id).where(
            MatchingGroup.deadline <= now, MatchingGroup.status != MatchingGroupStatusEnum.EXPIRED,
        ).distinct()).all()
    expired = 0
    for experience_id in ids:
        with SessionLocal() as db:
            experience = BookingRepository(db).lock_experience(experience_id)
            if not experience:
                continue
            groups = db.scalars(select(MatchingGroup).where(
                MatchingGroup.experience_id == experience_id, MatchingGroup.deadline <= now,
                MatchingGroup.status != MatchingGroupStatusEnum.EXPIRED,
            ).with_for_update()).all()
            for group in groups:
                group.status = MatchingGroupStatusEnum.EXPIRED
                NotificationService(db).stage(experience.id, {item.user_id for item in group.members},
                    "MATCHING_EXPIRED", group.id, f"{experience.title}: venció el plazo del grupo. Consulta la experiencia antes de reservar.")
            db.commit()
            expired += len(groups)
    print(f"Grupos vencidos: {expired}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

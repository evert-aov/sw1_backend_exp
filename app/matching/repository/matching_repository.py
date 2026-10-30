"""Acceso SQL de grupos y miembros; el servicio conserva el commit completo."""
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.matching.entity.matching_group import MatchingGroup, MatchingGroupStatusEnum
from app.matching.entity.matching_member import MatchingMember

class MatchingRepository:
    def __init__(self, db):
        self.db = db

    def get_by_id(self, group_id: str):
        return self.db.get(MatchingGroup, group_id)

    def list_by_experience(self, experience_id: str):
        return self.db.scalars(select(MatchingGroup).options(selectinload(MatchingGroup.members)).where(
            MatchingGroup.experience_id == experience_id).order_by(MatchingGroup.created_at, MatchingGroup.id)
            .execution_options(populate_existing=True)).all()

    def get_by_experience(self, experience_id: str):
        return next(iter(self.list_by_experience(experience_id)), None)

    def create_group(self, group: MatchingGroup):
        self.db.add(group)
        self.db.flush()
        return group

    def add_member(self, member: MatchingMember):
        self.db.add(member)
        self.db.flush()
        return member

    def get_members(self, group_id: str):
        return self.db.scalars(select(MatchingMember).where(MatchingMember.matching_group_id == group_id)).all()

    def update_status(self, group_id: str, status: MatchingGroupStatusEnum):
        group = self.db.scalar(select(MatchingGroup).where(MatchingGroup.id == group_id).with_for_update())
        if group:
            group.status = status
        return group

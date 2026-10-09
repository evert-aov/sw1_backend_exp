from typing import Optional, List
from sqlalchemy.orm import Session
from app.matching.entity.matching_group import MatchingGroup, MatchingGroupStatusEnum
from app.matching.entity.matching_member import MatchingMember


# Repositorio para la entidad MatchingGroup y MatchingMember: únicamente firmas de métodos
class MatchingRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, group_id: int) -> Optional[MatchingGroup]:
        # Buscar grupo por ID
        pass

    def get_by_experience(self, experience_id: int) -> Optional[MatchingGroup]:
        # Obtener grupo activo de una experiencia
        pass

    def create_group(self, group: MatchingGroup) -> MatchingGroup:
        # Registrar nuevo grupo de matching
        pass

    def add_member(self, member: MatchingMember) -> MatchingMember:
        # Agregar asistente al grupo de matching
        pass

    def get_members(self, group_id: int) -> List[MatchingMember]:
        # Listar miembros postulados
        pass

    def update_status(self, group_id: int, status: MatchingGroupStatusEnum) -> Optional[MatchingGroup]:
        # Actualizar estado de quórum (REACHED, EXPIRED)
        pass

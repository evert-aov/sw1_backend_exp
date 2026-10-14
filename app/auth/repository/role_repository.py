from typing import Optional, List
from sqlalchemy.orm import Session
from app.auth.entity.role import Role


# Repositorio para la entidad Role: operaciones de persistencia y consultas (Alta Cohesión)
class RoleRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, role_id: int) -> Optional[Role]:
        # Buscar rol por ID numérico
        return self.db.query(Role).filter(Role.id == role_id).first()

    def get_by_name(self, name: str) -> Optional[Role]:
        # Buscar rol por nombre normalizado en mayúsculas
        return self.db.query(Role).filter(Role.name == name.upper().strip()).first()

    def create(self, role: Role) -> Role:
        # Registrar un nuevo rol en la base de datos
        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)
        return role

    def get_all(self) -> List[Role]:
        # Listar todos los roles del sistema
        return self.db.query(Role).all()

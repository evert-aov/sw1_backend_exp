from typing import Optional, List
from sqlalchemy.orm import Session
from app.auth.entity.role import Role


# Repositorio para la entidad Role: únicamente firmas de métodos
class RoleRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, role_id: int) -> Optional[Role]:
        # Buscar rol por ID
        pass

    def get_by_name(self, name: str) -> Optional[Role]:
        # Buscar rol por nombre único
        pass

    def create(self, role: Role) -> Role:
        # Crear un nuevo rol en la base de datos
        pass

    def get_all(self) -> List[Role]:
        # Listar todos los roles del sistema
        pass

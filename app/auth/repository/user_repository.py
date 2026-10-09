from typing import Optional, List
from sqlalchemy.orm import Session
from app.auth.entity.user import User
from app.auth.entity.user_role import UserRole


# Repositorio para la entidad User: únicamente firmas de métodos
class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int) -> Optional[User]:
        # Buscar usuario por ID
        pass

    def get_by_email(self, email: str) -> Optional[User]:
        # Buscar usuario por correo electrónico
        pass

    def create(self, user: User) -> User:
        # Registrar nuevo usuario en base de datos
        pass

    def update(self, user: User) -> User:
        # Actualizar datos de un usuario existente
        pass

    def assign_role(self, user_id: int, role_id: int) -> UserRole:
        # Asignar un rol a un usuario
        pass

    def get_user_roles(self, user_id: int) -> List[str]:
        # Obtener la lista de nombres de roles de un usuario
        pass

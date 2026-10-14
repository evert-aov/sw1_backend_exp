from typing import Optional, List
from sqlalchemy.orm import Session
from app.auth.entity.user import User
from app.auth.entity.user_role import UserRole
from app.auth.entity.role import Role


# Repositorio para la entidad User: encapsula la persistencia y relaciones (Alta Cohesión)
class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int) -> Optional[User]:
        # Buscar usuario por ID
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, email: str) -> Optional[User]:
        # Buscar usuario por correo electrónico normalizado en minúsculas
        return self.db.query(User).filter(User.email == email.lower().strip()).first()

    def create(self, user: User) -> User:
        # Registrar nuevo usuario en base de datos
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update(self, user: User) -> User:
        # Actualizar datos de un usuario existente
        self.db.commit()
        self.db.refresh(user)
        return user

    def assign_role(self, user_id: int, role_id: int) -> UserRole:
        # Asignar un rol a un usuario si no lo tiene asignado previamente
        existing = (
            self.db.query(UserRole)
            .filter(UserRole.user_id == user_id, UserRole.role_id == role_id)
            .first()
        )
        if existing:
            return existing

        user_role = UserRole(user_id=user_id, role_id=role_id)
        self.db.add(user_role)
        self.db.commit()
        self.db.refresh(user_role)
        return user_role

    def get_user_roles(self, user_id: int) -> List[str]:
        # Obtener lista de nombres de roles asociados al usuario
        roles = (
            self.db.query(Role.name)
            .join(UserRole, Role.id == UserRole.role_id)
            .filter(UserRole.user_id == user_id)
            .all()
        )
        return [r[0] for r in roles]

    def get_all(self, skip: int = 0, limit: int = 100) -> List[User]:
        # Listar usuarios con paginación
        return self.db.query(User).order_by(User.id).offset(skip).limit(limit).all()

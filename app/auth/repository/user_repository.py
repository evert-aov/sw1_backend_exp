from __future__ import annotations

from sqlalchemy.orm import Session
from app.auth.entity.role import Role
from app.auth.entity.user import User
from app.auth.entity.user_role import UserRole


class UserRepository:
    """
    Repositorio de acceso a datos para la entidad `User` y su relación con `Role` (`UserRole`).
    Gestiona operaciones CRUD de cuentas de usuario y asignación de roles (CU-01, CU-02, CU-03).
    """

    def __init__(self, db: Session) -> None:
        """
        Inicializa el repositorio con una sesión de base de datos activa.

        Args:
            db (Session): Sesión SQLAlchemy inyectada.
        """
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        """
        Recupera un usuario por su identificador único.

        Args:
            user_id (int): ID numérico del usuario.

        Returns:
            User | None: Entidad `User` si existe, o `None`.
        """
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, email: str) -> User | None:
        """
        Busca un usuario por su dirección de correo electrónico normalizada en minúsculas.

        Args:
            email (str): Correo electrónico a consultar.

        Returns:
            User | None: Entidad `User` correspondiente o `None`.
        """
        return self.db.query(User).filter(User.email == email.lower().strip()).first()

    def create(self, user: User) -> User:
        """
        Registra y persiste un nuevo usuario en la base de datos (CU-01).

        Args:
            user (User): Entidad `User` con contraseña previamente encriptada.

        Returns:
            User: Entidad `User` persistida con su ID autogenerado.
        """
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update(self, user: User) -> User:
        """
        Confirma y persiste los cambios realizados sobre una entidad `User` existente (CU-03).

        Args:
            user (User): Entidad `User` modificada en la sesión actual.

        Returns:
            User: Entidad `User` actualizada y sincronizada con la base de datos.
        """
        self.db.commit()
        self.db.refresh(user)
        return user

    def assign_role(self, user_id: int, role_id: int) -> UserRole:
        """
        Asigna un rol a un usuario en la tabla intermedia `user_roles` evitando duplicados.

        Args:
            user_id (int): ID del usuario.
            role_id (int): ID del rol a vincular.

        Returns:
            UserRole: Vínculo `UserRole` existente o recién creado.
        """
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

    def get_user_roles(self, user_id: int) -> list[str]:
        """
        Obtiene la lista de nombres de roles asignados a un usuario específico.

        Args:
            user_id (int): ID del usuario a consultar.

        Returns:
            list[str]: Lista de nombres de roles (ej. `["HOST"]`).
        """
        roles = (
            self.db.query(Role.name)
            .join(UserRole, Role.id == UserRole.role_id)
            .filter(UserRole.user_id == user_id)
            .all()
        )
        return [r[0] for r in roles]

    def get_all(self, skip: int = 0, limit: int = 100) -> list[User]:
        """
        Lista los usuarios registrados en el sistema con soporte de paginación.

        Args:
            skip (int): Cantidad de registros a omitir (offset).
            limit (int): Cantidad máxima de registros a devolver.

        Returns:
            list[User]: Lista paginada de entidades `User`.
        """
        return self.db.query(User).order_by(User.id.asc()).offset(skip).limit(limit).all()

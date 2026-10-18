from __future__ import annotations

from sqlalchemy.orm import Session
from app.auth.entity.role import Role


class RoleRepository:
    """
    Repositorio de acceso a datos para la entidad `Role`.
    Encapsula las consultas y persistencia de perfiles de acceso (ATTENDEE, HOST, VENUE, ADMIN).
    """

    def __init__(self, db: Session) -> None:
        """
        Inicializa el repositorio con una sesión activa de SQLAlchemy.

        Args:
            db (Session): Sesión de base de datos inyectada.
        """
        self.db = db

    def get_by_id(self, role_id: int) -> Role | None:
        """
        Busca un rol por su clave primaria numérica.

        Args:
            role_id (int): Identificador único del rol.

        Returns:
            Role | None: Entidad `Role` encontrada o `None` si no existe.
        """
        return self.db.query(Role).filter(Role.id == role_id).first()

    def get_by_name(self, name: str) -> Role | None:
        """
        Busca un rol por su nombre normalizado en mayúsculas.

        Args:
            name (str): Nombre del rol (ej. 'HOST', 'ATTENDEE', 'VENUE', 'ADMIN').

        Returns:
            Role | None: Entidad `Role` encontrada o `None` si no existe.
        """
        return self.db.query(Role).filter(Role.name == name.upper().strip()).first()

    def create(self, role: Role) -> Role:
        """
        Persiste un nuevo rol en la base de datos.

        Args:
            role (Role): Instancia de la entidad `Role` a guardar.

        Returns:
            Role: Instancia `Role` persistida y refrescada con su ID asignado.
        """
        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)
        return role

    def get_all(self) -> list[Role]:
        """
        Recupera todos los roles registrados en el sistema ordenados por ID.

        Returns:
            list[Role]: Lista de entidades `Role`.
        """
        return self.db.query(Role).order_by(Role.id.asc()).all()

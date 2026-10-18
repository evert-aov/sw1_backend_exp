from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.auth.dto.auth_dto import PreferencesUpdateDTO, ProfileDTO, ProfileUpdateDTO
from app.auth.entity.user import User
from app.auth.repository.user_repository import UserRepository


class ProfileService:
    """
    Servicio de dominio para la Gestión de Perfiles de Usuario y Preferencias (CU-03 / HU-03).
    Permite consultar y actualizar datos personales, avatar, biografía y etiquetas de intereses temáticos.
    """

    def __init__(self, db: Session) -> None:
        """
        Inicializa el servicio de perfiles con el repositorio de usuarios.

        Args:
            db (Session): Sesión activa de SQLAlchemy.
        """
        self.db = db
        self.user_repo = UserRepository(db)

    def _to_profile_dto(self, user: User) -> ProfileDTO:
        """
        Transforma una entidad `User` y sus roles asociados en un `ProfileDTO`.

        Args:
            user (User): Entidad ORM `User`.

        Returns:
            ProfileDTO: Contrato de transferencia con datos del perfil y roles.
        """
        roles = self.user_repo.get_user_roles(user.id)
        return ProfileDTO(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            phone=user.phone,
            avatar_url=user.avatar_url,
            bio=user.bio,
            interests=user.interests or [],
            roles=roles,
            is_active=user.is_active,
            created_at=user.created_at,
        )

    def get_profile(self, user_id: str) -> ProfileDTO:
        """
        Obtiene la información completa del perfil, biografía, avatar e intereses de un usuario (CU-03).

        Args:
            user_id (str): Identificador único (UUID) del usuario a consultar.

        Returns:
            ProfileDTO: Datos del perfil del usuario.

        Raises:
            HTTPException (404): Si el usuario no existe en la base de datos.
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado",
            )
        return self._to_profile_dto(user)

    def update_profile(self, user_id: str, dto: ProfileUpdateDTO) -> ProfileDTO:
        """
        Actualiza los datos personales, fotografía de perfil, biografía y etiquetas de intereses
        del usuario autenticado (CU-03 / HU-03).

        Args:
            user_id (str): ID (UUID) del usuario propietario del perfil.
            dto (ProfileUpdateDTO): Campos del perfil y preferencias a actualizar.

        Returns:
            ProfileDTO: Perfil actualizado y persistido.

        Raises:
            HTTPException (404): Si el usuario no existe.
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado",
            )

        if dto.first_name is not None:
            user.first_name = dto.first_name.strip()
        if dto.last_name is not None:
            user.last_name = dto.last_name.strip()
        if dto.phone is not None:
            user.phone = dto.phone.strip()
        if dto.avatar_url is not None:
            user.avatar_url = dto.avatar_url.strip()
        if dto.bio is not None:
            user.bio = dto.bio.strip()
        if dto.interests is not None:
            # Lista normalizada sin duplicados vacíos manteniendo orden
            clean_tags: list[str] = []
            for tag in dto.interests:
                cleaned = str(tag).strip()
                if cleaned and cleaned not in clean_tags:
                    clean_tags.append(cleaned)
            user.interests = clean_tags

        updated_user = self.user_repo.update(user)
        return self._to_profile_dto(updated_user)

    def update_preferences(self, user_id: str, dto: PreferencesUpdateDTO) -> ProfileDTO:
        """
        Actualiza específicamente las etiquetas de intereses temáticos, biografía y avatar del usuario (CU-03).

        Args:
            user_id (str): ID (UUID) del usuario autenticado.
            dto (PreferencesUpdateDTO): Nuevas preferencias temáticas.

        Returns:
            ProfileDTO: Perfil actualizado con las nuevas preferencias.
        """
        update_dto = ProfileUpdateDTO(
            interests=dto.interests,
            bio=dto.bio,
            avatar_url=dto.avatar_url,
        )
        return self.update_profile(user_id=user_id, dto=update_dto)

    def list_users(self, skip: int = 0, limit: int = 100) -> list[ProfileDTO]:
        """
        Lista todos los perfiles de usuario registrados en la plataforma con paginación.

        Args:
            skip (int): Registros a omitir (offset).
            limit (int): Límite máximo de perfiles a retornar.

        Returns:
            list[ProfileDTO]: Lista de perfiles de usuario con sus roles.
        """
        users = self.user_repo.get_all(skip=skip, limit=limit)
        return [self._to_profile_dto(u) for u in users]

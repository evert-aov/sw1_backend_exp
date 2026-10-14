from typing import List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.auth.dto.auth_dto import ProfileDTO, ProfileUpdateDTO
from app.auth.repository.user_repository import UserRepository


# Servicio de Perfiles y Preferencias de Usuario: reglas de negocio de perfiles (CU-02)
class ProfileService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)

    def get_profile(self, user_id: int) -> ProfileDTO:
        # Obtener información del perfil, biografía, avatar e intereses
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado",
            )

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
            created_at=user.created_at,
        )

    def update_profile(self, user_id: int, dto: ProfileUpdateDTO) -> ProfileDTO:
        # Actualizar datos personales, imagen de perfil y etiquetas de interés
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
            # Lista normalizada de etiquetas de interés
            user.interests = [str(tag).strip() for tag in dto.interests if str(tag).strip()]

        updated_user = self.user_repo.update(user)
        roles = self.user_repo.get_user_roles(updated_user.id)

        return ProfileDTO(
            id=updated_user.id,
            first_name=updated_user.first_name,
            last_name=updated_user.last_name,
            email=updated_user.email,
            phone=updated_user.phone,
            avatar_url=updated_user.avatar_url,
            bio=updated_user.bio,
            interests=updated_user.interests or [],
            roles=roles,
            created_at=updated_user.created_at,
        )

    def list_users(self, skip: int = 0, limit: int = 100) -> List[ProfileDTO]:
        # Listar todos los usuarios con sus respectivos roles
        users = self.user_repo.get_all(skip=skip, limit=limit)
        result = []
        for u in users:
            roles = self.user_repo.get_user_roles(u.id)
            result.append(
                ProfileDTO(
                    id=u.id,
                    first_name=u.first_name,
                    last_name=u.last_name,
                    email=u.email,
                    phone=u.phone,
                    avatar_url=u.avatar_url,
                    bio=u.bio,
                    interests=u.interests or [],
                    roles=roles,
                    created_at=u.created_at,
                )
            )
        return result

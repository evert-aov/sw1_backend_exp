from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.auth.dto.auth_dto import RegisterDTO, LoginDTO, TokenResponseDTO, ProfileDTO
from app.auth.entity.user import User
from app.auth.entity.role import Role
from app.auth.repository.user_repository import UserRepository
from app.auth.repository.role_repository import RoleRepository
from app.core.security import get_password_hash, verify_password, create_access_token, decode_token


# Servicio de Autenticación: lógica de negocio desacoplada de la capa web (CU-01)
class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.role_repo = RoleRepository(db)

    def register(self, dto: RegisterDTO) -> ProfileDTO:
        # 1. Validar que el correo no esté ya registrado
        normalized_email = dto.email.lower().strip()
        existing_user = self.user_repo.get_by_email(normalized_email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El correo electrónico ya se encuentra registrado",
            )

        # 2. Obtener o crear el rol solicitado
        role_name = (dto.role or "ATTENDEE").upper().strip()
        role = self.role_repo.get_by_name(role_name)
        if not role:
            role = self.role_repo.create(
                Role(name=role_name, description=f"Perfil asignado para {role_name}")
            )

        # 3. Crear entidad User con contraseña encriptada
        new_user = User(
            first_name=dto.first_name.strip(),
            last_name=dto.last_name.strip() if dto.last_name else None,
            email=normalized_email,
            hashed_password=get_password_hash(dto.password),
            phone=dto.phone.strip() if dto.phone else None,
            is_active=True,
            interests=[],
        )
        created_user = self.user_repo.create(new_user)

        # 4. Asignar rol al usuario
        self.user_repo.assign_role(created_user.id, role.id)
        user_roles = [role.name]

        return ProfileDTO(
            id=created_user.id,
            first_name=created_user.first_name,
            last_name=created_user.last_name,
            email=created_user.email,
            phone=created_user.phone,
            avatar_url=created_user.avatar_url,
            bio=created_user.bio,
            interests=created_user.interests or [],
            roles=user_roles,
            created_at=created_user.created_at,
        )

    def login(self, dto: LoginDTO) -> TokenResponseDTO:
        # 1. Buscar usuario por correo electrónico
        normalized_email = dto.email.lower().strip()
        user = self.user_repo.get_by_email(normalized_email)
        if not user or not verify_password(dto.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales incorrectas (correo o contraseña no válidos)",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 2. Validar que la cuenta esté activa
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="La cuenta de usuario está desactivada o suspendida. Contacte al administrador.",
            )

        # 3. Obtener roles y generar token JWT
        user_roles = self.user_repo.get_user_roles(user.id)
        access_token = create_access_token(subject=str(user.id))

        return TokenResponseDTO(
            access_token=access_token,
            token_type="bearer",
            user_id=user.id,
            email=user.email,
            roles=user_roles,
        )

    def refresh_token(self, token: str) -> TokenResponseDTO:
        # Decodificar token actual y verificar usuario activo
        payload = decode_token(token)
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token no contiene sujeto válido",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = self.user_repo.get_by_id(int(user_id_str))
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario no encontrado o inactivo",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_roles = self.user_repo.get_user_roles(user.id)
        new_token = create_access_token(subject=str(user.id))

        return TokenResponseDTO(
            access_token=new_token,
            token_type="bearer",
            user_id=user.id,
            email=user.email,
            roles=user_roles,
        )

    def refresh_token_for_user(self, user: User) -> TokenResponseDTO:
        # Generar nuevo token JWT directamente para el usuario autenticado
        user_roles = self.user_repo.get_user_roles(user.id)
        new_token = create_access_token(subject=str(user.id))
        return TokenResponseDTO(
            access_token=new_token,
            token_type="bearer",
            user_id=user.id,
            email=user.email,
            roles=user_roles,
        )

from __future__ import annotations

from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.auth.dto.auth_dto import (
    LoginDTO,
    LogoutResponseDTO,
    ProfileDTO,
    RegisterDTO,
    TokenResponseDTO,
)
from app.auth.entity.role import Role
from app.auth.entity.user import User
from app.auth.repository.role_repository import RoleRepository
from app.auth.repository.user_repository import UserRepository
from app.core.security import (
    create_access_token,
    decode_token,
    get_password_hash,
    revoke_token,
    verify_password,
)


class AuthService:
    """
    Servicio de dominio para Autenticación y Registro de Cuentas (CU-01, CU-02 / HU-01, HU-02).
    Implementa la lógica de registro seguro con bcrypt, inicio de sesión, renovación y cierre de sesión JWT.
    """

    VALID_ROLES: set[str] = {"ATTENDEE", "HOST", "VENUE", "ADMIN"}

    def __init__(self, db: Session) -> None:
        """
        Inicializa el servicio de autenticación con sus repositorios colaboradores.

        Args:
            db (Session): Sesión activa de SQLAlchemy.
        """
        self.db = db
        self.user_repo = UserRepository(db)
        self.role_repo = RoleRepository(db)

    def register(self, dto: RegisterDTO) -> ProfileDTO:
        """
        Registra una nueva cuenta de usuario validando unicidad de correo, encriptando la contraseña
        con bcrypt y asignando el rol inicial solicitado (CU-01 / HU-01).

        Args:
            dto (RegisterDTO): Datos de registro del nuevo usuario.

        Returns:
            ProfileDTO: Perfil completo del usuario recién registrado con su rol asignado.

        Raises:
            HTTPException (400): Si el correo electrónico ya se encuentra registrado o el rol es inválido.
        """
        normalized_email = dto.email.lower().strip()
        existing_user = self.user_repo.get_by_email(normalized_email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El correo electrónico ya se encuentra registrado",
            )

        role_name = (dto.role or "ATTENDEE").upper().strip()
        if role_name not in self.VALID_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rol '{role_name}' no válido. Roles permitidos: {sorted(self.VALID_ROLES)}",
            )

        role = self.role_repo.get_by_name(role_name)
        if not role:
            role = self.role_repo.create(
                Role(name=role_name, description=f"Perfil asignado para {role_name}")
            )

        normalized_interests = (
            [str(tag).strip() for tag in dto.interests if str(tag).strip()]
            if dto.interests
            else []
        )

        new_user = User(
            first_name=dto.first_name.strip(),
            last_name=dto.last_name.strip() if dto.last_name else None,
            email=normalized_email,
            hashed_password=get_password_hash(dto.password),
            phone=dto.phone.strip() if dto.phone else None,
            avatar_url=dto.avatar_url.strip() if dto.avatar_url else None,
            bio=dto.bio.strip() if dto.bio else None,
            is_active=True,
            interests=normalized_interests,
        )
        created_user = self.user_repo.create(new_user)

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
            is_active=created_user.is_active,
            created_at=created_user.created_at,
        )

    def login(self, dto: LoginDTO) -> TokenResponseDTO:
        """
        Autentica a un usuario verificando su correo electrónico y contraseña contra el hash bcrypt,
        emitiendo un token de acceso JWT firmado (CU-02 / HU-02).

        Args:
            dto (LoginDTO): Credenciales de inicio de sesión (`email`, `password`).

        Returns:
            TokenResponseDTO: Token JWT de acceso junto con datos de identificación y roles del usuario.

        Raises:
            HTTPException (401): Si las credenciales son incorrectas.
            HTTPException (403): Si la cuenta de usuario está desactivada o suspendida.
        """
        normalized_email = dto.email.lower().strip()
        user = self.user_repo.get_by_email(normalized_email)
        if not user or not verify_password(dto.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales incorrectas (correo o contraseña no válidos)",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="La cuenta de usuario está desactivada o suspendida. Contacte al administrador.",
            )

        user_roles = self.user_repo.get_user_roles(user.id)
        access_token = create_access_token(subject=str(user.id))

        return TokenResponseDTO(
            access_token=access_token,
            token_type="bearer",
            user_id=user.id,
            email=user.email,
            roles=user_roles,
        )

    def logout(self, user: User, token: str) -> LogoutResponseDTO:
        """
        Cierra la sesión activa del usuario revocando el token JWT actual para impedir
        su reutilización posterior (CU-02 / HU-02).

        Args:
            user (User): Usuario autenticado que solicita el cierre de sesión.
            token (str): Token JWT Bearer activo que será invalidado.

        Returns:
            LogoutResponseDTO: Confirmación de cierre de sesión y marca de tiempo UTC.
        """
        revoke_token(token)
        return LogoutResponseDTO(
            status="success",
            message="Sesión cerrada correctamente. El token JWT ha sido revocado.",
            user_id=user.id,
            email=user.email,
            logged_out_at=datetime.now(timezone.utc),
        )

    def refresh_token(self, token: str) -> TokenResponseDTO:
        """
        Decodifica un token JWT válido, verifica que el usuario continúe activo y emite un nuevo token (CU-02).

        Args:
            token (str): Token JWT actual.

        Returns:
            TokenResponseDTO: Nuevo token JWT firmado y roles vigentes del usuario.

        Raises:
            HTTPException (401): Si el token no contiene sujeto válido o el usuario está inactivo.
        """
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
        """
        Genera un nuevo token JWT directamente para una instancia de usuario ya autenticada (CU-02).

        Args:
            user (User): Entidad `User` autenticada.

        Returns:
            TokenResponseDTO: Nuevo token JWT y roles asociados.
        """
        user_roles = self.user_repo.get_user_roles(user.id)
        new_token = create_access_token(subject=str(user.id))
        return TokenResponseDTO(
            access_token=new_token,
            token_type="bearer",
            user_id=user.id,
            email=user.email,
            roles=user_roles,
        )

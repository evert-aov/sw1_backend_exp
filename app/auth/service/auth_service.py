from sqlalchemy.orm import Session
from app.auth.dto.auth_dto import RegisterDTO, LoginDTO, TokenResponseDTO
from app.auth.dto.auth_dto import ProfileDTO


# Servicio de Autenticación: únicamente firmas de métodos (CU-01)
class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def register(self, dto: RegisterDTO) -> ProfileDTO:
        # Registrar nuevo usuario, encriptar contraseña y asignar rol
        pass

    def login(self, dto: LoginDTO) -> TokenResponseDTO:
        # Validar credenciales y retornar token JWT firmado
        pass

    def refresh_token(self, token: str) -> TokenResponseDTO:
        # Renovar token de acceso
        pass

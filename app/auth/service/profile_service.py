from sqlalchemy.orm import Session
from app.auth.dto.auth_dto import ProfileDTO, ProfileUpdateDTO


# Servicio de Perfiles y Preferencias de Usuario: únicamente firmas de métodos (CU-02)
class ProfileService:
    def __init__(self, db: Session):
        self.db = db

    def get_profile(self, user_id: int) -> ProfileDTO:
        # Obtener información del perfil, biografía, avatar e intereses del usuario
        pass

    def update_profile(self, user_id: int, dto: ProfileUpdateDTO) -> ProfileDTO:
        # Actualizar datos personales, imagen de perfil y etiquetas de interés
        pass

from __future__ import annotations

from app.experience.dto.experience_dto import VenueCreateDTO, VenueDTO
from app.experience.entity.venue import Venue


class VenueMapper:
    """
    Componente Mapper para transformar entre la entidad ORM `Venue`
    y sus contratos de transferencia `VenueDTO` / `VenueCreateDTO`.
    """

    @staticmethod
    def to_entity(dto: VenueCreateDTO, owner_id: str | None) -> Venue:
        """
        Convierte un `VenueCreateDTO` en una entidad relacional `Venue` con valores normalizados.

        Args:
            dto (VenueCreateDTO): Datos del establecimiento a registrar.
            owner_id (str | None): ID del usuario propietario que registra el local.

        Returns:
            Venue: Instancia ORM `Venue` lista para persistir.
        """
        return Venue(
            owner_id=owner_id,
            name=dto.name.strip(),
            address=dto.address,
            city=dto.city or "Santa Cruz de la Sierra",
            zone=dto.zone,
            latitude=dto.latitude,
            longitude=dto.longitude,
            max_capacity=dto.max_capacity or 50,
            phone=dto.phone,
        )

    @staticmethod
    def to_dto(venue: Venue) -> VenueDTO:
        """
        Convierte una entidad relacional `Venue` en un `VenueDTO`.

        Args:
            venue (Venue): Entidad ORM `Venue`.

        Returns:
            VenueDTO: Contrato de respuesta validado.
        """
        return VenueDTO.model_validate(venue)

from app.experience.dto.experience_dto import VenueDTO, VenueCreateDTO
from app.experience.entity.venue import Venue


class VenueMapper:

    @staticmethod
    def to_entity(dto: VenueCreateDTO, owner_id: int) -> Venue:
        """Convierte un VenueCreateDTO en una entidad relacional Venue con valores normalizados."""
        return Venue(
            owner_id=owner_id,
            name=dto.name.strip(),
            address=dto.address,
            city=dto.city,
            zone=dto.zone,
            latitude=dto.latitude,
            longitude=dto.longitude,
            max_capacity=dto.max_capacity or 50,
            phone=dto.phone,
        )

    @staticmethod
    def to_dto(venue: Venue) -> VenueDTO:
        """Convierte una entidad relacional Venue en un VenueDTO."""
        return VenueDTO.model_validate(venue)

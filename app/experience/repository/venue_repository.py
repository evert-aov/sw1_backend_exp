from typing import Optional, List
from sqlalchemy.orm import Session
from app.experience.entity.venue import Venue


# Repositorio para la entidad Venue: únicamente firmas de métodos
class VenueRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, venue_id: int) -> Optional[Venue]:
        return self.db.query(Venue).filter(Venue.id == venue_id).first()

    def create(self, venue: Venue) -> Venue:
        self.db.add(venue)
        self.db.commit()
        self.db.refresh(venue)
        return venue

    def get_by_zone(self, zone: str) -> List[Venue]:
        return self.db.query(Venue).filter(Venue.zone.ilike(f"%{zone.strip()}%")).all()

    def get_all(self) -> List[Venue]:
        return self.db.query(Venue).order_by(Venue.name.asc()).all()

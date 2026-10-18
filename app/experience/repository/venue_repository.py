from __future__ import annotations

from sqlalchemy.orm import Session
from app.experience.entity.venue import Venue


class VenueRepository:
    """
    Repositorio de acceso a datos para la entidad `Venue` (establecimientos y locales físicos).
    Soporta consultas por ID, listado general y filtrado por zona urbana (CU-04, CU-05).
    """

    def __init__(self, db: Session) -> None:
        """
        Inicializa el repositorio con la sesión activa de SQLAlchemy.

        Args:
            db (Session): Sesión de base de datos inyectada.
        """
        self.db = db

    def get_by_id(self, venue_id: str) -> Venue | None:
        """
        Recupera un establecimiento físico por su identificador único (UUID).

        Args:
            venue_id (str): ID (UUID) del establecimiento.

        Returns:
            Venue | None: Entidad `Venue` encontrada o `None`.
        """
        return self.db.query(Venue).filter(Venue.id == str(venue_id)).first()

    def create(self, venue: Venue) -> Venue:
        """
        Registra y persiste un nuevo establecimiento físico en la base de datos.

        Args:
            venue (Venue): Entidad `Venue` a guardar.

        Returns:
            Venue: Entidad `Venue` persistida con su ID asignado.
        """
        self.db.add(venue)
        self.db.commit()
        self.db.refresh(venue)
        return venue

    def get_by_zone(self, zone: str) -> list[Venue]:
        """
        Filtra establecimientos cuya zona urbana coincida parcialmente con el texto buscado.

        Args:
            zone (str): Nombre o fragmento de la zona urbana (ej. 'Equipetrol').

        Returns:
            list[Venue]: Lista de establecimientos ubicados en dicha zona.
        """
        return (
            self.db.query(Venue)
            .filter(Venue.zone.ilike(f"%{zone.strip()}%"))
            .order_by(Venue.name.asc())
            .all()
        )

    def get_all(self) -> list[Venue]:
        """
        Lista todos los establecimientos físicos registrados ordenados alfabéticamente.

        Returns:
            list[Venue]: Lista de entidades `Venue`.
        """
        return self.db.query(Venue).order_by(Venue.name.asc()).all()

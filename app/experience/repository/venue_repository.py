from __future__ import annotations

from sqlalchemy import func
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

    def get_canonical_zone(self, zone: str) -> str | None:
        """Busca la grafía almacenada de una zona sin distinguir mayúsculas.

        Args:
            zone (str): Nombre de la zona consultada.

        Returns:
            str | None: Nombre almacenado o None si la zona no existe.
        """
        row = (
            self.db.query(Venue.zone)
            .filter(
                Venue.zone.isnot(None),
                func.lower(func.trim(Venue.zone)) == zone.strip().lower(),
            )
            .order_by(Venue.zone.asc())
            .first()
        )
        return row[0] if row else None

    def owns_venue_in_zone(self, owner_id: str, zone: str) -> bool:
        """Comprueba si un usuario posee un venue en la zona exacta.

        Args:
            owner_id (str): Identificador del propietario consultado.
            zone (str): Zona del establecimiento.

        Returns:
            bool: True si el usuario posee al menos un venue en esa zona.
        """
        return (
            self.db.query(Venue.id)
            .filter(
                Venue.owner_id == str(owner_id),
                Venue.zone.isnot(None),
                func.lower(func.trim(Venue.zone)) == zone.strip().lower(),
            )
            .first()
            is not None
        )

    def get_all(self) -> list[Venue]:
        """
        Lista todos los establecimientos físicos registrados ordenados alfabéticamente.

        Returns:
            list[Venue]: Lista de entidades `Venue`.
        """
        return self.db.query(Venue).order_by(Venue.name.asc()).all()

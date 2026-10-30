"""Libera estados de retenciones vencidas usando la conexión PostgreSQL del backend."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal, load_all_entities
from app.booking.service.booking_service import BookingService


def main() -> None:
    """Ejecuta una pasada idempotente para un planificador externo, sin crear esquema."""
    load_all_entities()
    with SessionLocal() as session:
        count = BookingService(session).release_expired_holds()
    print(f"Reservas vencidas liberadas: {count}")


if __name__ == "__main__":
    main()

"""Actualiza PostgreSQL con Alembic y reconoce una instalación inicial no versionada."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
from app.core.migrations import (
    MigrationDependencyError, migrate_connection, migration_config, unversioned_baseline,
)
from app.core.schema import DatabaseSchemaError, validate_database_schema


def main(argv: list[str] | None = None) -> int:
    """Comprueba o migra en una transacción, sin recrear tablas ni sembrar datos."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Inspecciona versiones/estructura sin escribir")
    arguments = parser.parse_args(argv)
    if sys.version_info[:3] != (3, 14, 6):
        print("Usa Python 3.14.6.", file=sys.stderr)
        return 2
    try:
        config, head = migration_config()
    except MigrationDependencyError as error:
        print(str(error), file=sys.stderr)
        return 2
    from alembic.runtime.migration import MigrationContext
    from alembic.util import CommandError

    database = sa.create_engine(settings.database_url, pool_pre_ping=True, hide_parameters=True,
                                connect_args={"connect_timeout": 5})
    try:
        with database.begin() as connection:
            current = MigrationContext.configure(connection).get_current_heads()
            print("Revisión actual:", ", ".join(current) if current else "sin versión")
            print("Revisión objetivo:", head)
            if arguments.check:
                if not current:
                    baseline = unversioned_baseline(connection)
                    print("Base reconocida:", baseline or "instalación nueva")
                validate_database_schema(connection)
                return 0 if current == (head,) else 1
            migrate_connection(connection, config)
        print("Migraciones aplicadas y esquema validado. Ya puedes reiniciar la API.")
        return 0
    except DatabaseSchemaError as error:
        for difference in error.differences:
            print(difference, file=sys.stderr)
        print("No se aplicaron cambios. Revisa las diferencias de esquema sin usar reset ni stamp manual.", file=sys.stderr)
        return 1
    except CommandError:
        print("La revisión registrada no coincide con las migraciones disponibles. "
              "No se aplicaron cambios; revisa el historial Alembic antes de continuar.", file=sys.stderr)
        return 1
    except SQLAlchemyError as error:
        print(f"PostgreSQL no pudo completar la operación ({type(error).__name__}). "
              "La transacción se revirtió; verifica conexión y datos previos.", file=sys.stderr)
        return 1
    finally:
        database.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

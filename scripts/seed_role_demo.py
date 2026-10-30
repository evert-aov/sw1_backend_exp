"""Carga datos ficticios para probar vistas y permisos del sprint 2 sin vaciar la base."""

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from app.core.database import engine
from app.core.demo_seed import (
    DEFAULT_DATASET,
    DEFAULT_DEMO_PASSWORD,
    build_demo_plan,
    seed_demo_connection,
    DemoSeedConflict,
)
from app.core.schema import DatabaseSchemaError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
        help="Nombre del conjunto; cambia el valor para crear otro lote independiente",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Muestra lo que se creará sin conectarse ni modificar PostgreSQL",
    )
    args = parser.parse_args()
    try:
        plan = build_demo_plan(args.dataset)
        if args.plan:
            print(json.dumps(plan, ensure_ascii=False, indent=2, default=str))
            return 0
        password = os.environ.get("DEMO_SEED_PASSWORD", DEFAULT_DEMO_PASSWORD)
        with engine.begin() as connection:
            report = seed_demo_connection(connection, plan, password)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(
            "Seed confirmado en PostgreSQL. Se conservaron los registros ajenos al dataset."
        )
        return 0
    except DatabaseSchemaError as error:
        print(error, file=sys.stderr)
    except (DemoSeedConflict, ValueError) as error:
        print(error, file=sys.stderr)
    except HTTPException as error:
        print(f"No se pudo completar el dataset: {error.detail}", file=sys.stderr)
    except SQLAlchemyError as error:
        print(
            f"No se pudo cargar el seed en PostgreSQL ({type(error).__name__}). Revisa la conexión del .env y ejecuta scripts/check_database.py.",
            file=sys.stderr,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

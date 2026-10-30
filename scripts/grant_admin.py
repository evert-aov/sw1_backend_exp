"""Asigna ADMIN a una cuenta existente usando acceso del operador a PostgreSQL."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.core.database import SessionLocal, load_all_entities
from app.auth.repository.role_repository import RoleRepository
from app.auth.repository.user_repository import UserRepository


def grant_admin(db, email: str) -> None:
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(2026102601)"))
        users = UserRepository(db)
        user = users.get_by_email(email.strip().lower())
        if not user or not user.is_active:
            raise ValueError(
                "Debe existir una cuenta activa con ese correo. No se creó ni reactivó ninguna cuenta."
            )
        role = RoleRepository(db).get_or_create_pending("ADMIN")
        users.assign_role(user.id, role.id, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "email", help="Correo de la cuenta activa del propietario de la plataforma"
    )
    args = parser.parse_args()
    load_all_entities()
    try:
        with SessionLocal() as db:
            grant_admin(db, args.email)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    print("ADMIN asignado. Los demás roles y datos de la cuenta se conservaron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

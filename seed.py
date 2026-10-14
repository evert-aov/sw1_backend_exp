"""
Script independiente de Seeding para la base de datos de EXPERIENCIA.
Crea roles por defecto y usuarios de demostración,
Contraseña estándar para todos los usuarios semilla: Password123!
"""

import sys
from app.core.database import (
    reset_and_seed_database,
    seed_database,
    SessionLocal,
)
from app.auth.entity.user import User
from app.auth.entity.role import Role
from app.auth.entity.user_role import UserRole


def run_seeder(clean: bool = False):
    if clean:
        print("[Seeder] Limpiando tablas en cascada y poblando datos desde cero...")
        reset_and_seed_database()
    else:
        print("[Seeder] Verificando e insertando datos semilla...")
        seed_database()

    print("[Seeder] Usuarios presentes en la base de datos:")
    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.id).all()
        for u in users:
            roles = (
                db.query(Role.name)
                .join(UserRole, Role.id == UserRole.role_id)
                .filter(UserRole.user_id == u.id)
                .all()
            )
            role_names = [r[0] for r in roles]
            print(f"  • ID: {u.id:<2} | Email: {u.email:<32} | Nombre: {u.first_name} {u.last_name or ''} | Roles: {role_names}")
    finally:
        db.close()
    print("\n[Seeder] Proceso finalizado con éxito. Contraseña para todos los usuarios: Password123!\n")


if __name__ == "__main__":
    clean_flag = "--clean" in sys.argv or "-c" in sys.argv
    run_seeder(clean=clean_flag)

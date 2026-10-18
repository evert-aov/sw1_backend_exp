"""
Script independiente de Seeding para la base de datos de EXPERIENCIA (Sprint 1).
Crea roles por defecto, usuarios de demostración/equipo, categorías temáticas,
establecimientos geolocalizados y experiencias publicadas.
Contraseña estándar para todos los usuarios semilla: Password123!
"""

from __future__ import annotations

import sys
from app.auth.entity.role import Role
from app.auth.entity.user import User
from app.auth.entity.user_role import UserRole
from app.core.database import Base, SessionLocal, engine, load_all_entities
from app.core.seeder import reset_and_seed_database, seed_database
from app.experience.entity.category import Category
from app.experience.entity.experience import Experience
from app.experience.entity.venue import Venue


def run_seeder(clean: bool = False) -> None:
    """
    Ejecuta el proceso de poblamiento de datos semilla en la base de datos activa
    e imprime un resumen detallado por consola de los registros creados para pruebas.

    Args:
        clean (bool): Si es `True`, vacía primero todas las tablas en cascada antes de poblar.
    """
    load_all_entities()
    Base.metadata.create_all(bind=engine)

    if clean:
        print("[Seeder] Limpiando tablas en cascada y poblando datos desde cero...")
        reset_and_seed_database()
    else:
        print("[Seeder] Verificando e insertando datos semilla del Sprint 1...")
        seed_database()

    db = SessionLocal()
    try:
        print("\n[Seeder] 1. Usuarios presentes en la base de datos (CU-01, CU-02, CU-03):")
        users = db.query(User).order_by(User.id.asc()).all()
        for u in users:
            roles = (
                db.query(Role.name)
                .join(UserRole, Role.id == UserRole.role_id)
                .filter(UserRole.user_id == u.id)
                .all()
            )
            role_names = [r[0] for r in roles]
            print(
                f"  • ID: {u.id} | Email: {u.email:<35} | "
                f"Nombre: {u.first_name} {u.last_name or '':<16} | Roles: {role_names}"
            )

        print("\n[Seeder] 2. Categorías temáticas registradas (CU-04, CU-05):")
        categories = db.query(Category).order_by(Category.id.asc()).all()
        for c in categories:
            print(f"  • ID: {c.id} | Categoría: {c.name:<25} | Ícono: {c.icon_name}")

        print("\n[Seeder] 3. Establecimientos físicos geolocalizados (CU-04, CU-05):")
        venues = db.query(Venue).order_by(Venue.id.asc()).all()
        for v in venues:
            print(
                f"  • ID: {v.id} | Local: {v.name:<30} | Zona: {v.zone or '-':<12} | "
                f"GPS: ({v.latitude}, {v.longitude}) | Aforo máx: {v.max_capacity}"
            )

        print("\n[Seeder] 4. Experiencias publicadas en el catálogo (CU-04, CU-05):")
        experiences = db.query(Experience).order_by(Experience.id.asc()).all()
        for e in experiences:
            print(
                f"  • ID: {e.id} | [{e.modality.value:<9}] [{e.status.value:<9}] "
                f"Bs/$ {e.price:<6.1f} | Cupos: {e.reserved_slots}/{e.max_capacity} (Quórum: {e.min_capacity}) | {e.title}"
            )
    finally:
        db.close()
    print("\n[Seeder] Proceso finalizado con éxito. Contraseña para todos los usuarios: Password123!\n")


if __name__ == "__main__":
    clean_flag = "--clean" in sys.argv or "-c" in sys.argv
    run_seeder(clean=clean_flag)

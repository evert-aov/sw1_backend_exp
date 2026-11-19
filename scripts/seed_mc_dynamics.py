"""
Seed del catálogo de dinámicas del Asistente de Maestro de Ceremonias (HU-19) sin vaciar la base.

Inserta o actualiza por código las dinámicas iniciales (preguntas al público, pausas activas y
descansos cortos). Puede ejecutarse varias veces sin duplicar registros.

Ejemplo:
    venv/Scripts/python scripts/seed_mc_dynamics.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal, load_all_entities  # noqa: E402
from app.live.service.mc_dynamics_seed import seed_mc_dynamics  # noqa: E402


def main() -> int:
    """
    Siembra el catálogo de dinámicas e imprime un resumen.

    Returns:
        int: Código de salida del proceso.
    """
    load_all_entities()
    with SessionLocal() as db:
        seeded = seed_mc_dynamics(db)
    print(f"[Asistente MC] Dinámicas en el catálogo: {len(seeded)}")
    for item in seeded:
        print(f"  • {item['code']:<28} {item['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

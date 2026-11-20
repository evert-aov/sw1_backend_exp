"""
Seed de demostración de la consola en vivo (HU-17) sin vaciar la base.

Crea o reutiliza una sesión en vivo ACTIVE para una experiencia del anfitrión indicado e inserta
métricas agregadas de audiencia en `audience_metrics`, igual que lo haría el pipeline de visión
(HU-13 a HU-16). Con `--stream` sigue insertando una métrica cada 2.5 s para ver el semáforo y el
pulso moverse en tiempo real. Solo escribe números agregados: nunca imágenes ni datos personales.

Ejemplos:
    venv/Scripts/python scripts/seed_live_telemetry_demo.py
    venv/Scripts/python scripts/seed_live_telemetry_demo.py --stream --duration 300
    venv/Scripts/python scripts/seed_live_telemetry_demo.py --host-email evert.rodriguez@experiencia.com --stream
    venv/Scripts/python scripts/seed_live_telemetry_demo.py --scenario caida --stream   # HU-18: atención baja sostenida
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth.entity.user import User  # noqa: E402
from app.core.database import SessionLocal, load_all_entities  # noqa: E402
from app.experience.entity.experience import Experience  # noqa: E402
from app.live.entity.audience_metric import AgeGroupEnum, AudienceMetric  # noqa: E402
from app.live.entity.live_session import LiveSession, LiveSessionStatusEnum  # noqa: E402
from app.live.service.mc_dynamics_seed import seed_mc_dynamics  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

DEFAULT_HOST_EMAIL = "host@experiencia.com"
SAMPLE_INTERVAL_SECONDS = 2.5

# Ciclo completo de energía de la demo: alta, caída sostenida y recuperación (unos 3 minutos)
ENERGY_CYCLE_SECONDS = 180.0


def utc_naive_now() -> datetime:
    """
    Devuelve el instante actual en UTC sin zona horaria, formato de las columnas de la BD.

    Returns:
        datetime: Fecha y hora UTC sin zona horaria.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def build_sample(
    elapsed_seconds: float, rng: random.Random, scenario: str = "ciclo"
) -> dict[str, float | int | AgeGroupEnum]:
    """
    Genera una métrica agregada plausible en un instante del ciclo de demostración.

    Escenario `ciclo`: la atención sigue una onda lenta que recorre los tres colores del semáforo.
    Escenario `caida`: la atención se mantiene baja (cerca de 0.28) para disparar la alerta del
    Asistente MC (HU-18), con ruido leve y repuntes breves que no deben cortar la racha.

    Args:
        elapsed_seconds (float): Segundos transcurridos desde el inicio de la serie.
        rng (random.Random): Generador pseudoaleatorio con semilla fija para resultados repetibles.
        scenario (str): `ciclo` o `caida`.

    Returns:
        dict: Valores de atención, alegría, neutralidad, desatención, rostros y rango etario.
    """
    phase = 2 * math.pi * (elapsed_seconds % ENERGY_CYCLE_SECONDS) / ENERGY_CYCLE_SECONDS
    if scenario == "caida":
        attention = 0.28 + 0.05 * math.sin(phase * 3) + rng.uniform(-0.04, 0.04)
    else:
        attention = 0.58 + 0.32 * math.cos(phase) + rng.uniform(-0.04, 0.04)
    attention = max(0.05, min(0.98, attention))
    joy = max(0.0, min(1.0, attention * 0.85 + rng.uniform(-0.05, 0.05)))
    inattention = max(0.0, min(1.0, 1.0 - attention))
    neutral = max(0.0, min(1.0, 1.0 - (attention + joy) / 2))
    faces = max(1, int(18 + 4 * math.cos(phase / 2) + rng.randint(-1, 1)))
    return {
        "attention_score": round(attention, 3),
        "joy_score": round(joy, 3),
        "neutral_score": round(neutral, 3),
        "inattention_score": round(inattention, 3),
        "detected_faces_count": faces,
        "dominant_age_group": AgeGroupEnum.YOUNG_ADULT,
    }


def resolve_live_session(db: Session, host_email: str, experience_id: str | None) -> LiveSession:
    """
    Reutiliza la sesión ACTIVE de la experiencia o crea una nueva para el anfitrión.

    Args:
        db (Session): Sesión de base de datos.
        host_email (str): Correo del anfitrión dueño de la experiencia.
        experience_id (str | None): Experiencia concreta; si es None se usa la primera del anfitrión.

    Returns:
        LiveSession: Sesión en vivo activa lista para recibir métricas.

    Raises:
        SystemExit: Si el anfitrión o la experiencia no existen.
    """
    host = db.query(User).filter(User.email == host_email).first()
    if host is None:
        raise SystemExit(f"No existe el usuario {host_email}. Ejecuta primero: python seed.py")

    query = db.query(Experience).filter(Experience.host_id == host.id)
    if experience_id:
        query = query.filter(Experience.id == experience_id)
    experience = query.order_by(Experience.event_date.asc()).first()
    if experience is None:
        raise SystemExit(
            f"{host_email} no tiene experiencias publicadas para iniciar una sesión en vivo."
        )

    session = (
        db.query(LiveSession)
        .filter(
            LiveSession.experience_id == experience.id,
            LiveSession.status == LiveSessionStatusEnum.ACTIVE,
        )
        .first()
    )
    if session is None:
        session = LiveSession(
            experience_id=experience.id,
            host_id=host.id,
            status=LiveSessionStatusEnum.ACTIVE,
            started_at=utc_naive_now(),
        )
        db.add(session)
        db.commit()
        db.refresh(session)
    print(f"[Telemetría] Experiencia: {experience.title}")
    return session


def insert_metric(db: Session, session_id: str, recorded_at: datetime, values: dict) -> None:
    """
    Inserta una métrica agregada de audiencia para la sesión.

    Args:
        db (Session): Sesión de base de datos.
        session_id (str): UUID de la sesión en vivo.
        recorded_at (datetime): Instante UTC con zona horaria de la métrica.
        values (dict): Valores generados por `build_sample`.
    """
    db.add(AudienceMetric(live_session_id=session_id, recorded_at=recorded_at, **values))
    db.commit()


def main() -> int:
    """
    Punto de entrada del seed de telemetría en vivo.

    Returns:
        int: Código de salida del proceso (0 si terminó correctamente).
    """
    parser = argparse.ArgumentParser(
        description="Seed de demostración de la consola en vivo (HU-17)"
    )
    parser.add_argument(
        "--host-email", default=DEFAULT_HOST_EMAIL, help="Anfitrión dueño de la experiencia"
    )
    parser.add_argument(
        "--experience-id", default=None, help="Experiencia concreta del anfitrión (opcional)"
    )
    parser.add_argument(
        "--history", type=int, default=24, help="Métricas previas a insertar (24 = 60 s)"
    )
    parser.add_argument(
        "--stream", action="store_true", help="Seguir insertando una métrica cada 2.5 s"
    )
    parser.add_argument(
        "--duration", type=float, default=0, help="Segundos de --stream; 0 = hasta Ctrl+C"
    )
    parser.add_argument(
        "--seed", type=int, default=17, help="Semilla del generador para series repetibles"
    )
    parser.add_argument(
        "--scenario",
        choices=("ciclo", "caida"),
        default="ciclo",
        help="ciclo: recorre los tres colores; caida: atención baja sostenida para la alerta MC (HU-18)",
    )
    args = parser.parse_args()

    load_all_entities()
    rng = random.Random(args.seed)
    with SessionLocal() as db:
        seed_mc_dynamics(db)
        session = resolve_live_session(db, args.host_email, args.experience_id)
        session_id = str(session.id)
        # Fecha UTC con zona: PostgreSQL la guarda igual que las métricas reales de la cámara
        now = datetime.now(timezone.utc)
        history = max(0, args.history)
        for index in range(history):
            offset = (history - index) * SAMPLE_INTERVAL_SECONDS
            insert_metric(
                db,
                session_id,
                now - timedelta(seconds=offset),
                build_sample(index * SAMPLE_INTERVAL_SECONDS, rng, args.scenario),
            )

        print(f"[Telemetría] Sesión en vivo: {session_id}")
        print(f"[Telemetría] Métricas históricas insertadas: {history}")
        print(f"[Telemetría] Inicia sesión como {args.host_email} (Password123!) y abre:")
        print(f"             http://localhost:3000/live/{session_id}/console")

        if not args.stream:
            return 0

        print("[Telemetría] Transmitiendo una métrica cada 2.5 s. Ctrl+C para detener.")
        started = time.monotonic()
        elapsed_series = history * SAMPLE_INTERVAL_SECONDS
        try:
            while args.duration <= 0 or time.monotonic() - started < args.duration:
                values = build_sample(elapsed_series, rng, args.scenario)
                insert_metric(db, session_id, datetime.now(timezone.utc), values)
                print(
                    f"  atención={values['attention_score']:.2f} alegría={values['joy_score']:.2f} rostros={values['detected_faces_count']}"
                )
                elapsed_series += SAMPLE_INTERVAL_SECONDS
                time.sleep(SAMPLE_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\n[Telemetría] Transmisión detenida.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

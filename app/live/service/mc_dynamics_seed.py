"""
Seed del catálogo de dinámicas del Asistente de Maestro de Ceremonias (CU-11 / HU-19).

Las dinámicas viven en la tabla `mc_dynamics`; este módulo solo define el conjunto inicial y lo
inserta o actualiza de forma idempotente por `code`, sin borrar dinámicas creadas por otros medios.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.live.entity.mc_dynamic import McDynamic, McDynamicModalityEnum, McDynamicTypeEnum

Q = McDynamicTypeEnum.AUDIENCE_QUESTION
ACTIVE = McDynamicTypeEnum.ACTIVE_BREAK
SHORT = McDynamicTypeEnum.SHORT_BREAK
ANY = McDynamicModalityEnum.ANY
IN_PERSON = McDynamicModalityEnum.IN_PERSON
VIRTUAL = McDynamicModalityEnum.VIRTUAL

DEFAULT_MC_DYNAMICS: list[dict[str, Any]] = [
    {
        "code": "QUESTION_SHOW_OF_HANDS",
        "dynamic_type": Q,
        "modality": IN_PERSON,
        "intensity": 1,
        "duration_minutes": 1,
        "title_es": "Pregunta a mano alzada",
        "title_en": "Show-of-hands question",
        "instructions_es": "Haz una pregunta de sí o no sobre el tema y pide levantar la mano. Comenta el resultado en voz alta.",
        "instructions_en": "Ask a yes-or-no question about the topic and ask people to raise their hands. Comment on the result out loud.",
    },
    {
        "code": "QUESTION_TURN_TO_NEIGHBOR",
        "dynamic_type": Q,
        "modality": IN_PERSON,
        "intensity": 2,
        "duration_minutes": 2,
        "title_es": "Comenta con tu vecino",
        "title_en": "Turn to your neighbor",
        "instructions_es": "Plantea una pregunta abierta y da 60 segundos para que cada persona la comente con quien tiene al lado. Pide dos respuestas al azar.",
        "instructions_en": "Pose an open question and give 60 seconds for everyone to discuss it with the person next to them. Ask for two random answers.",
    },
    {
        "code": "QUESTION_CHAT_ONE_WORD",
        "dynamic_type": Q,
        "modality": VIRTUAL,
        "intensity": 1,
        "duration_minutes": 1,
        "title_es": "Una palabra en el chat",
        "title_en": "One word in the chat",
        "instructions_es": "Pide que todos escriban en el chat una palabra que resuma lo visto hasta ahora. Lee algunas en voz alta.",
        "instructions_en": "Ask everyone to type one word in the chat that sums up what they have seen so far. Read a few out loud.",
    },
    {
        "code": "QUESTION_QUICK_POLL",
        "dynamic_type": Q,
        "modality": ANY,
        "intensity": 2,
        "duration_minutes": 2,
        "title_es": "Encuesta relámpago",
        "title_en": "Lightning poll",
        "instructions_es": "Propón dos opciones relacionadas con el tema y pide votar (mano alzada o chat). Explica qué opción elegirías tú y por qué.",
        "instructions_en": "Offer two options related to the topic and ask people to vote (hands or chat). Explain which one you would pick and why.",
    },
    {
        "code": "QUESTION_REAL_EXAMPLE",
        "dynamic_type": Q,
        "modality": ANY,
        "intensity": 1,
        "duration_minutes": 2,
        "title_es": "Pide un ejemplo real",
        "title_en": "Ask for a real example",
        "instructions_es": "Pregunta si alguien vivió una situación parecida a lo que estás explicando e invita a compartirla en 30 segundos.",
        "instructions_en": "Ask whether anyone has lived a situation similar to what you are explaining and invite them to share it in 30 seconds.",
    },
    {
        "code": "ACTIVE_STAND_AND_STRETCH",
        "dynamic_type": ACTIVE,
        "modality": IN_PERSON,
        "intensity": 2,
        "duration_minutes": 2,
        "title_es": "De pie y a estirar",
        "title_en": "Stand up and stretch",
        "instructions_es": "Pide a todos ponerse de pie, estirar brazos y cuello durante un minuto y volver a sentarse.",
        "instructions_en": "Ask everyone to stand up, stretch their arms and neck for one minute and sit back down.",
    },
    {
        "code": "ACTIVE_CHANGE_SEATS",
        "dynamic_type": ACTIVE,
        "modality": IN_PERSON,
        "intensity": 3,
        "duration_minutes": 3,
        "title_es": "Cambio de lugar",
        "title_en": "Switch seats",
        "instructions_es": "Pide que cada persona cambie de lugar y se presente con alguien nuevo en una frase.",
        "instructions_en": "Ask everyone to change seats and introduce themselves to someone new in one sentence.",
    },
    {
        "code": "ACTIVE_CAMERA_ON_STRETCH",
        "dynamic_type": ACTIVE,
        "modality": VIRTUAL,
        "intensity": 2,
        "duration_minutes": 2,
        "title_es": "Estiramiento con cámara",
        "title_en": "Camera-on stretch",
        "instructions_es": "Invita a encender la cámara y hacer juntos un estiramiento de hombros de un minuto.",
        "instructions_en": "Invite people to turn their cameras on and do a one-minute shoulder stretch together.",
    },
    {
        "code": "ACTIVE_BREATHING",
        "dynamic_type": ACTIVE,
        "modality": ANY,
        "intensity": 1,
        "duration_minutes": 1,
        "title_es": "Tres respiraciones profundas",
        "title_en": "Three deep breaths",
        "instructions_es": "Guía tres respiraciones lentas: inhalar en 4 tiempos, sostener 2 y exhalar en 6.",
        "instructions_en": "Lead three slow breaths: inhale for 4 counts, hold for 2 and exhale for 6.",
    },
    {
        "code": "BREAK_FIVE_MINUTES",
        "dynamic_type": SHORT,
        "modality": ANY,
        "intensity": 3,
        "duration_minutes": 5,
        "title_es": "Pausa de 5 minutos",
        "title_en": "Five-minute break",
        "instructions_es": "Anuncia una pausa de 5 minutos para hidratarse. Indica la hora exacta de regreso.",
        "instructions_en": "Announce a 5-minute break to get some water. Give the exact time to come back.",
    },
    {
        "code": "BREAK_THREE_MINUTES_MUSIC",
        "dynamic_type": SHORT,
        "modality": IN_PERSON,
        "intensity": 2,
        "duration_minutes": 3,
        "title_es": "Pausa musical de 3 minutos",
        "title_en": "Three-minute music break",
        "instructions_es": "Haz una pausa corta con música de fondo y retoma con un resumen de 30 segundos de lo visto.",
        "instructions_en": "Take a short break with background music and resume with a 30-second recap of what you covered.",
    },
]


def seed_mc_dynamics(db: Session) -> list[dict[str, str]]:
    """
    Inserta o actualiza el catálogo inicial de dinámicas del Asistente MC de forma idempotente.

    Args:
        db (Session): Sesión de base de datos; el método confirma la transacción.

    Returns:
        list[dict[str, str]]: Código y título en español de cada dinámica del catálogo inicial.
    """
    seeded: list[dict[str, str]] = []
    for data in DEFAULT_MC_DYNAMICS:
        dynamic = db.query(McDynamic).filter(McDynamic.code == data["code"]).first()
        if dynamic is None:
            dynamic = McDynamic(code=data["code"], is_active=True)
            db.add(dynamic)
        for field, value in data.items():
            setattr(dynamic, field, value)
        seeded.append({"code": data["code"], "title": data["title_es"]})
    db.commit()
    return seeded

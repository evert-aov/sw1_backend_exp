"""
Seed del catálogo de dinámicas del Asistente de Maestro de Ceremonias (CU-11 / HU-19).

Incluye dinámicas generales (sin categoría) y dinámicas específicas por categoría de experiencia.

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


# Nombres de las categorías sembradas por app/core/seeder.py (CU-04)
GASTRONOMY = "Gastronomía"
ART = "Arte y Pintura"
MUSIC = "Música y Conciertos"
WORKSHOPS = "Talleres y Educación"
NETWORKING = "Networking y Negocios"
WELLNESS = "Bienestar y Outdoors"

# Dinámicas específicas por tipo de experiencia: se prefieren sobre las generales (HU-19)
CATEGORY_MC_DYNAMICS: list[dict[str, Any]] = [
    {
        "code": "GASTRO_GUESS_THE_AROMA",
        "category_names": [GASTRONOMY],
        "dynamic_type": Q,
        "modality": IN_PERSON,
        "intensity": 2,
        "duration_minutes": 2,
        "title_es": "Adivina el aroma",
        "title_en": "Guess the aroma",
        "instructions_es": "Pide que el público adivine una nota de aroma o sabor del producto que presentas. Revela la respuesta y explica de dónde viene.",
        "instructions_en": "Ask the audience to guess an aroma or flavor note of the product you are presenting. Reveal the answer and explain where it comes from.",
    },
    {
        "code": "GASTRO_SWEET_SOUR_BITTER",
        "category_names": [GASTRONOMY],
        "dynamic_type": Q,
        "modality": ANY,
        "intensity": 1,
        "duration_minutes": 1,
        "title_es": "¿Dulce, ácido o amargo?",
        "title_en": "Sweet, sour or bitter?",
        "instructions_es": "Pide que voten qué sabor domina en la última preparación. Comenta por qué se percibe así.",
        "instructions_en": "Ask people to vote which flavor dominates the last preparation. Explain why it is perceived that way.",
    },
    {
        "code": "GASTRO_GUIDED_TASTING",
        "category_names": [GASTRONOMY],
        "dynamic_type": ACTIVE,
        "modality": IN_PERSON,
        "intensity": 3,
        "duration_minutes": 3,
        "title_es": "Degustación guiada en grupo",
        "title_en": "Guided group tasting",
        "instructions_es": "Invita a todos a probar juntos una muestra siguiendo tus pasos: oler, probar y describir en una palabra.",
        "instructions_en": "Invite everyone to taste a sample together following your steps: smell, taste and describe it in one word.",
    },
    {
        "code": "GASTRO_TASTING_BREAK",
        "category_names": [GASTRONOMY],
        "dynamic_type": SHORT,
        "modality": IN_PERSON,
        "intensity": 2,
        "duration_minutes": 3,
        "title_es": "Pausa para probar y conversar",
        "title_en": "Tasting and chatting break",
        "instructions_es": "Da 3 minutos para probar lo preparado y conversar entre mesas. Retoma preguntando qué les sorprendió.",
        "instructions_en": "Give 3 minutes to taste what was prepared and chat between tables. Resume by asking what surprised them.",
    },
    {
        "code": "MUSIC_CROWD_PICKS_SONG",
        "category_names": [MUSIC],
        "dynamic_type": Q,
        "modality": ANY,
        "intensity": 2,
        "duration_minutes": 1,
        "title_es": "El público elige la canción",
        "title_en": "The crowd picks the song",
        "instructions_es": "Ofrece dos canciones y deja que el público elija con aplausos (o en el chat si es virtual).",
        "instructions_en": "Offer two songs and let the crowd choose with applause (or in the chat if virtual).",
    },
    {
        "code": "MUSIC_CLAP_THE_BEAT",
        "category_names": [MUSIC],
        "dynamic_type": ACTIVE,
        "modality": IN_PERSON,
        "intensity": 2,
        "duration_minutes": 1,
        "title_es": "Palmas al ritmo",
        "title_en": "Clap to the beat",
        "instructions_es": "Invita al público a marcar el ritmo con palmas durante el próximo estribillo.",
        "instructions_en": "Invite the audience to clap along to the beat during the next chorus.",
    },
    {
        "code": "MUSIC_SING_ALONG",
        "category_names": [MUSIC],
        "dynamic_type": ACTIVE,
        "modality": IN_PERSON,
        "intensity": 3,
        "duration_minutes": 2,
        "title_es": "Coro del público",
        "title_en": "Audience sing-along",
        "instructions_es": "Enseña una frase corta del coro y pide que la canten contigo en la siguiente vuelta.",
        "instructions_en": "Teach a short line of the chorus and ask everyone to sing it with you next time.",
    },
    {
        "code": "MUSIC_DEDICATION",
        "category_names": [MUSIC],
        "dynamic_type": Q,
        "modality": ANY,
        "intensity": 1,
        "duration_minutes": 1,
        "title_es": "Dedica la siguiente canción",
        "title_en": "Dedicate the next song",
        "instructions_es": "Pregunta si alguien quiere dedicar la siguiente canción y menciona la dedicatoria antes de tocar.",
        "instructions_en": "Ask whether someone wants to dedicate the next song and read the dedication before playing.",
    },
    {
        "code": "ART_WHAT_DO_YOU_SEE",
        "category_names": [ART],
        "dynamic_type": Q,
        "modality": ANY,
        "intensity": 1,
        "duration_minutes": 1,
        "title_es": "¿Qué te transmite esta obra?",
        "title_en": "What does this piece convey?",
        "instructions_es": "Muestra una obra o un avance y pide una palabra que describa lo que transmite.",
        "instructions_en": "Show a piece or a work in progress and ask for one word describing what it conveys.",
    },
    {
        "code": "ART_GALLERY_WALK",
        "category_names": [ART],
        "dynamic_type": ACTIVE,
        "modality": IN_PERSON,
        "intensity": 2,
        "duration_minutes": 2,
        "title_es": "Recorrido por los lienzos",
        "title_en": "Canvas gallery walk",
        "instructions_es": "Pide que todos se levanten y observen el trabajo de otra persona durante un minuto.",
        "instructions_en": "Ask everyone to stand up and look at someone else's work for one minute.",
    },
    {
        "code": "ART_BLIND_SKETCH",
        "category_names": [ART],
        "dynamic_type": ACTIVE,
        "modality": ANY,
        "intensity": 3,
        "duration_minutes": 2,
        "title_es": "Trazo a ciegas de 60 segundos",
        "title_en": "60-second blind sketch",
        "instructions_es": "Propón dibujar algo con los ojos cerrados durante un minuto y mostrar el resultado al grupo.",
        "instructions_en": "Ask everyone to draw something with their eyes closed for one minute and show the result.",
    },
    {
        "code": "EDU_QUICK_REVIEW",
        "category_names": [WORKSHOPS],
        "dynamic_type": Q,
        "modality": ANY,
        "intensity": 1,
        "duration_minutes": 1,
        "title_es": "Pregunta de repaso",
        "title_en": "Quick review question",
        "instructions_es": "Haz una pregunta rápida sobre lo explicado y reconoce la primera respuesta correcta.",
        "instructions_en": "Ask a quick question about what you explained and acknowledge the first correct answer.",
    },
    {
        "code": "EDU_ONE_LINE_DOUBT",
        "category_names": [WORKSHOPS],
        "dynamic_type": Q,
        "modality": ANY,
        "intensity": 2,
        "duration_minutes": 2,
        "title_es": "Tu duda en una frase",
        "title_en": "Your question in one line",
        "instructions_es": "Pide que cada persona escriba su principal duda en una frase y responde dos al azar.",
        "instructions_en": "Ask everyone to write their main question in one line and answer two at random.",
    },
    {
        "code": "EDU_PAIR_CHALLENGE",
        "category_names": [WORKSHOPS],
        "dynamic_type": ACTIVE,
        "modality": ANY,
        "intensity": 3,
        "duration_minutes": 3,
        "title_es": "Reto práctico en parejas",
        "title_en": "Hands-on pair challenge",
        "instructions_es": "Propón un ejercicio de 3 minutos en parejas aplicando el último concepto y comenta una solución.",
        "instructions_en": "Set a 3-minute pair exercise applying the last concept and review one solution.",
    },
    {
        "code": "NET_LIGHTNING_INTRO",
        "category_names": [NETWORKING],
        "dynamic_type": Q,
        "modality": ANY,
        "intensity": 2,
        "duration_minutes": 2,
        "title_es": "Presentación relámpago",
        "title_en": "Lightning introductions",
        "instructions_es": "Pide a tres personas que se presenten en 15 segundos: nombre, empresa y qué buscan hoy.",
        "instructions_en": "Ask three people to introduce themselves in 15 seconds: name, company and what they are looking for.",
    },
    {
        "code": "NET_CARD_SWAP",
        "category_names": [NETWORKING],
        "dynamic_type": ACTIVE,
        "modality": IN_PERSON,
        "intensity": 3,
        "duration_minutes": 3,
        "title_es": "Intercambio de contactos",
        "title_en": "Contact swap",
        "instructions_es": "Da 2 minutos para que cada persona intercambie contacto con alguien que no conoce.",
        "instructions_en": "Give 2 minutes for everyone to exchange contacts with someone they do not know.",
    },
    {
        "code": "NET_CHALLENGE_POLL",
        "category_names": [NETWORKING],
        "dynamic_type": Q,
        "modality": ANY,
        "intensity": 1,
        "duration_minutes": 1,
        "title_es": "Encuesta de desafíos",
        "title_en": "Business challenge poll",
        "instructions_es": "Pregunta cuál es el mayor desafío de su negocio entre tres opciones y comenta el resultado.",
        "instructions_en": "Ask which is their biggest business challenge among three options and comment on the result.",
    },
    {
        "code": "WELL_CHECK_IN",
        "category_names": [WELLNESS],
        "dynamic_type": Q,
        "modality": ANY,
        "intensity": 1,
        "duration_minutes": 1,
        "title_es": "¿Cómo llegas ahora?",
        "title_en": "How are you arriving now?",
        "instructions_es": "Pide que cada persona describa con una palabra cómo se siente en este momento.",
        "instructions_en": "Ask everyone to describe in one word how they feel right now.",
    },
    {
        "code": "WELL_MINDFUL_STRETCH",
        "category_names": [WELLNESS],
        "dynamic_type": ACTIVE,
        "modality": ANY,
        "intensity": 2,
        "duration_minutes": 2,
        "title_es": "Estiramiento consciente",
        "title_en": "Mindful stretch",
        "instructions_es": "Guía un estiramiento lento de cuello y hombros coordinado con la respiración.",
        "instructions_en": "Lead a slow neck and shoulder stretch coordinated with breathing.",
    },
    {
        "code": "WELL_OUTDOOR_HYDRATION",
        "category_names": [WELLNESS],
        "dynamic_type": SHORT,
        "modality": IN_PERSON,
        "intensity": 2,
        "duration_minutes": 3,
        "title_es": "Pausa de hidratación al aire libre",
        "title_en": "Outdoor hydration break",
        "instructions_es": "Anuncia una pausa de 3 minutos para hidratarse y respirar aire fresco. Indica la hora de regreso.",
        "instructions_en": "Announce a 3-minute break to hydrate and get some fresh air. Give the time to come back.",
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
    for data in DEFAULT_MC_DYNAMICS + CATEGORY_MC_DYNAMICS:
        dynamic = db.query(McDynamic).filter(McDynamic.code == data["code"]).first()
        if dynamic is None:
            dynamic = McDynamic(code=data["code"], is_active=True)
            db.add(dynamic)
        for field, value in {"category_names": [], **data}.items():
            setattr(dynamic, field, value)
        seeded.append({"code": data["code"], "title": data["title_es"]})
    db.commit()
    return seeded

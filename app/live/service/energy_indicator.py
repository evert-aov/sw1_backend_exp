"""
Cálculo del indicador discreto de energía de la audiencia (HU-17).

Funciones puras, sin estado ni dependencias de red o base de datos, para que el semáforo
sea predecible y fácil de probar. El servicio de telemetría las combina por cada sesión.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.live.dto.live_telemetry_dto import EnergyTrafficLightEnum, EnergyTrendEnum

# Ponderación del índice de energía: la atención pesa más que la alegría expresada
ATTENTION_WEIGHT = 0.6
JOY_WEIGHT = 0.4

# Umbrales del semáforo sobre el índice de energía suavizado (0.0 a 1.0)
GREEN_THRESHOLD = 0.65
YELLOW_THRESHOLD = 0.40

# Margen de histéresis: para bajar de nivel el puntaje debe caer este valor bajo el umbral,
# evitando que el semáforo parpadee cuando la energía oscila justo sobre un límite
HYSTERESIS_MARGIN = 0.05

# Cantidad de muestras promediadas (4 muestras x 2.5 s = 10 s de ventana)
SMOOTHING_WINDOW = 4

# Variación mínima entre promedios recientes para considerar que la energía sube o baja
TREND_DELTA = 0.03

_LEVEL_ORDER = {
    EnergyTrafficLightEnum.RED: 0,
    EnergyTrafficLightEnum.YELLOW: 1,
    EnergyTrafficLightEnum.GREEN: 2,
}


def _clamp(value: float) -> float:
    """
    Restringe un valor al rango normalizado [0.0, 1.0].

    Args:
        value (float): Valor a restringir.

    Returns:
        float: Valor dentro del rango [0.0, 1.0].
    """
    return max(0.0, min(1.0, float(value)))


def compute_energy_score(attention_score: float, joy_score: float) -> float:
    """
    Combina atención y alegría en un único índice de energía de la audiencia.

    Args:
        attention_score (float): Índice de atención promedio (0.0 a 1.0) calculado por HU-15.
        joy_score (float): Índice de alegría o entusiasmo promedio (0.0 a 1.0).

    Returns:
        float: Índice de energía normalizado entre 0.0 y 1.0, redondeado a 3 decimales.
    """
    energy = ATTENTION_WEIGHT * _clamp(attention_score) + JOY_WEIGHT * _clamp(joy_score)
    return round(_clamp(energy), 3)


def smooth_energy(raw_scores: Sequence[float], window: int = SMOOTHING_WINDOW) -> float:
    """
    Suaviza el índice de energía con la media de las últimas muestras.

    Args:
        raw_scores (Sequence[float]): Índices de energía en orden cronológico.
        window (int): Cantidad de muestras finales a promediar.

    Returns:
        float: Media de las últimas `window` muestras, o 0.0 si no hay muestras.
    """
    if not raw_scores:
        return 0.0
    recent = list(raw_scores)[-max(1, window):]
    return round(sum(recent) / len(recent), 3)


def classify_energy(score: float) -> EnergyTrafficLightEnum:
    """
    Clasifica un índice de energía en un nivel del semáforo sin considerar el estado previo.

    Args:
        score (float): Índice de energía suavizado (0.0 a 1.0).

    Returns:
        EnergyTrafficLightEnum: GREEN si >= 0.65, YELLOW si >= 0.40, RED en otro caso.
    """
    if score >= GREEN_THRESHOLD:
        return EnergyTrafficLightEnum.GREEN
    if score >= YELLOW_THRESHOLD:
        return EnergyTrafficLightEnum.YELLOW
    return EnergyTrafficLightEnum.RED


def resolve_traffic_light(
    score: float,
    previous: EnergyTrafficLightEnum | None,
    margin: float = HYSTERESIS_MARGIN,
) -> EnergyTrafficLightEnum:
    """
    Determina el color del semáforo aplicando histéresis respecto al color anterior.

    Subir de nivel ocurre al alcanzar el umbral; bajar de nivel exige caer `margin` por debajo
    del umbral correspondiente. Así el indicador solo cambia ante variaciones sostenidas.

    Args:
        score (float): Índice de energía suavizado (0.0 a 1.0).
        previous (EnergyTrafficLightEnum | None): Color mostrado en la emisión anterior.
        margin (float): Margen de histéresis aplicado al bajar de nivel.

    Returns:
        EnergyTrafficLightEnum: Color del semáforo a mostrar.
    """
    candidate = classify_energy(score)
    if previous is None or _LEVEL_ORDER[candidate] >= _LEVEL_ORDER[previous]:
        return candidate

    # Bajada de nivel: solo se acepta si el puntaje supera el margen de histéresis
    lowered = classify_energy(score + margin)
    if _LEVEL_ORDER[lowered] >= _LEVEL_ORDER[previous]:
        return previous
    return lowered


def compute_trend(smoothed_scores: Sequence[float], delta: float = TREND_DELTA) -> EnergyTrendEnum:
    """
    Calcula la tendencia de la energía comparando las dos mitades de las últimas cuatro muestras.

    Args:
        smoothed_scores (Sequence[float]): Índices de energía suavizados en orden cronológico.
        delta (float): Diferencia mínima para considerar subida o bajada.

    Returns:
        EnergyTrendEnum: RISING, FALLING o STABLE (también STABLE si hay menos de 4 muestras).
    """
    recent = list(smoothed_scores)[-4:]
    if len(recent) < 4:
        return EnergyTrendEnum.STABLE
    earlier = (recent[0] + recent[1]) / 2
    latest = (recent[2] + recent[3]) / 2
    if latest - earlier > delta:
        return EnergyTrendEnum.RISING
    if earlier - latest > delta:
        return EnergyTrendEnum.FALLING
    return EnergyTrendEnum.STABLE

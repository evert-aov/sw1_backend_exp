"""Estimador de edad real con OpenCV: detector YuNet y clasificador Caffe de edad (HU-16).

Privacidad: el fotograma se decodifica en RAM, los rostros se recortan en memoria y todas las
referencias a la imagen se liberan al terminar cada llamada. No se escribe nada en disco ni en logs;
los únicos mensajes de log se refieren a la configuración de los modelos, nunca a fotogramas.
"""

from __future__ import annotations

import importlib
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import BACKEND_ROOT, Settings, settings
from app.live.entity.audience_metric import AgeGroupEnum

logger = logging.getLogger(__name__)

# Clases de salida de la red Caffe de edad (Levi y Hassner, 2015), en el orden exacto de sus 8 neuronas.
# Cada rango se asigna a AgeGroupEnum por su punto medio, con los cortes de age_group_for_age:
# YOUTH < 18, YOUNG_ADULT 18-30, ADULT 31-50, SENIOR > 50.
CAFFE_AGE_BUCKETS: tuple[tuple[str, float, AgeGroupEnum], ...] = (
    ("0-2", 1.0, AgeGroupEnum.YOUTH),
    ("4-6", 5.0, AgeGroupEnum.YOUTH),
    ("8-12", 10.0, AgeGroupEnum.YOUTH),
    ("15-20", 17.5, AgeGroupEnum.YOUTH),  # Cruza el corte de 18: punto medio 17.5 -> YOUTH.
    ("25-32", 28.5, AgeGroupEnum.YOUNG_ADULT),  # Cruza el corte de 30/31: punto medio 28.5 -> YOUNG_ADULT.
    ("38-43", 40.5, AgeGroupEnum.ADULT),
    ("48-53", 50.5, AgeGroupEnum.SENIOR),  # Cruza el corte de 50: punto medio 50.5 (> 50) -> SENIOR.
    ("60-100", 80.0, AgeGroupEnum.SENIOR),
)

# Preprocesamiento con el que se entrenó la red de edad: entrada 227x227 BGR y media por canal.
AGE_NET_INPUT_SIZE: tuple[int, int] = (227, 227)
AGE_NET_MEAN_BGR: tuple[float, float, float] = (78.4263377603, 87.7689143744, 114.895847746)

# Margen alrededor de cada rostro detectado, relativo a su lado mayor, para incluir contorno y cabello.
FACE_CROP_MARGIN = 0.2
# Confianza mínima de YuNet para aceptar un rostro.
DEFAULT_FACE_SCORE_THRESHOLD = 0.8

# Variables de entorno con las rutas de los tres archivos de modelo.
MODEL_PATH_SETTINGS: tuple[str, str, str] = (
    "AGE_FACE_DETECTOR_PATH",
    "AGE_CLASSIFIER_PROTOTXT_PATH",
    "AGE_CLASSIFIER_MODEL_PATH",
)


def age_group_for_bucket(index: int) -> AgeGroupEnum:
    """
    Devuelve el rango etario correspondiente a una clase de la red Caffe de edad.

    Args:
        index (int): Posición de la clase con mayor probabilidad (0 a 7).

    Returns:
        AgeGroupEnum: Rango etario según `CAFFE_AGE_BUCKETS`.

    Raises:
        ValueError: Si el índice está fuera de las 8 clases del modelo.
    """
    if not 0 <= index < len(CAFFE_AGE_BUCKETS):
        raise ValueError("La red de edad devolvió una clase fuera de los 8 rangos esperados.")
    return CAFFE_AGE_BUCKETS[index][2]


class OpenCvAgeEstimator:
    """
    Implementación de `AgeEstimator` basada solo en OpenCV (HU-16).

    Detecta rostros con YuNet (`cv2.FaceDetectorYN`), recorta cada uno en memoria y clasifica su edad
    con la red Caffe de 8 rangos (`cv2.dnn.readNetFromCaffe`). Las redes de OpenCV no son seguras entre
    hilos, por lo que la inferencia se serializa con un candado.
    """

    def __init__(
        self,
        face_detector_path: str | Path,
        age_prototxt_path: str | Path,
        age_model_path: str | Path,
        *,
        score_threshold: float = DEFAULT_FACE_SCORE_THRESHOLD,
        cv_module: Any | None = None,
    ) -> None:
        """
        Carga ambos modelos una sola vez para reutilizarlos en cada fotograma.

        Args:
            face_detector_path (str | Path): Archivo ONNX de YuNet (por ejemplo, face_detection_yunet_2023mar.onnx).
            age_prototxt_path (str | Path): Definición Caffe de la red de edad (.prototxt).
            age_model_path (str | Path): Pesos Caffe de la red de edad (.caffemodel).
            score_threshold (float): Confianza mínima de YuNet para aceptar un rostro (0 a 1).
            cv_module (Any | None): Módulo compatible con cv2; solo se sustituye en pruebas.

        Raises:
            ValueError: Si el umbral de confianza está fuera del rango 0 a 1.
            cv2.error: Si OpenCV no puede leer alguno de los modelos.
        """
        if not 0.0 < float(score_threshold) <= 1.0:
            raise ValueError("El umbral de confianza de rostros debe estar entre 0 y 1.")
        self._cv = cv_module if cv_module is not None else importlib.import_module("cv2")
        # El tamaño inicial se reemplaza en cada fotograma con setInputSize.
        self._detector = self._cv.FaceDetectorYN.create(
            str(face_detector_path), "", (320, 320), float(score_threshold)
        )
        self._age_net = self._cv.dnn.readNetFromCaffe(str(age_prototxt_path), str(age_model_path))
        self._lock = threading.Lock()

    def estimate(self, frame: bytes) -> list[AgeGroupEnum]:
        """
        Clasifica en rangos etarios los rostros de un fotograma JPEG/PNG, solo en memoria.

        Args:
            frame (bytes): Fotograma ya decodificado de Base64. No se guarda ni se registra.

        Returns:
            list[AgeGroupEnum]: Un rango por rostro detectado con recorte válido; vacía si no hay rostros.

        Raises:
            ValueError: Si los bytes no son una imagen decodificable o la red no devuelve 8 clases.
        """
        buffer = image = faces = crops = blob = predictions = None
        try:
            buffer = np.frombuffer(frame, dtype=np.uint8)
            image = self._cv.imdecode(buffer, self._cv.IMREAD_COLOR)
            if image is None:
                raise ValueError("El fotograma no es una imagen JPEG/PNG decodificable.")
            height, width = image.shape[:2]
            with self._lock:
                self._detector.setInputSize((width, height))
                _, faces = self._detector.detect(image)
                if faces is None or len(faces) == 0:
                    return []
                crops = [crop for crop in (self._crop_face(image, face) for face in faces) if crop is not None]
                if not crops:
                    return []
                blob = self._cv.dnn.blobFromImages(
                    crops, 1.0, AGE_NET_INPUT_SIZE, AGE_NET_MEAN_BGR, swapRB=False, crop=False
                )
                self._age_net.setInput(blob)
                predictions = np.asarray(self._age_net.forward()).reshape(len(crops), -1)
            if predictions.shape[1] != len(CAFFE_AGE_BUCKETS):
                raise ValueError("La red configurada no corresponde al clasificador de edad de 8 rangos.")
            return [age_group_for_bucket(int(np.argmax(row))) for row in predictions]
        finally:
            # Suelta la imagen decodificada, los recortes y los tensores intermedios.
            del buffer, image, faces, crops, blob, predictions

    @staticmethod
    def _crop_face(image: np.ndarray, face: np.ndarray) -> np.ndarray | None:
        """
        Recorta un rostro con margen, limitado a los bordes de la imagen, sin salir de la RAM.

        Args:
            image (np.ndarray): Fotograma decodificado en formato BGR.
            face (np.ndarray): Fila de YuNet: x, y, ancho, alto, 10 coordenadas de puntos y confianza.

        Returns:
            np.ndarray | None: Copia contigua del recorte, o None si la caja no tiene área útil.
        """
        height, width = image.shape[:2]
        x, y, box_width, box_height = (float(value) for value in face[:4])
        if box_width <= 0 or box_height <= 0:
            return None
        margin = FACE_CROP_MARGIN * max(box_width, box_height)
        left, top = max(int(x - margin), 0), max(int(y - margin), 0)
        right = min(int(x + box_width + margin), width)
        bottom = min(int(y + box_height + margin), height)
        if right <= left or bottom <= top:
            return None
        return np.ascontiguousarray(image[top:bottom, left:right])


def resolve_model_path(value: str | None) -> Path | None:
    """
    Convierte una ruta configurada en un archivo existente.

    Las rutas relativas se resuelven desde la carpeta del backend, igual que el archivo .env.

    Args:
        value (str | None): Ruta tomada de la configuración.

    Returns:
        Path | None: Ruta absoluta del archivo, o None si está vacía o el archivo no existe.
    """
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path if path.is_file() else None


def build_age_estimator_from_settings(
    config: Settings | Any | None = None,
    estimator_class: Callable[..., OpenCvAgeEstimator] = OpenCvAgeEstimator,
) -> OpenCvAgeEstimator | None:
    """
    Construye el estimador OpenCV solo si los tres archivos de modelo están configurados y existen.

    Args:
        config (Settings | Any | None): Configuración con las tres rutas; por defecto, la global.
        estimator_class (Callable[..., OpenCvAgeEstimator]): Clase a instanciar; se sustituye en pruebas.

    Returns:
        OpenCvAgeEstimator | None: Estimador listo para registrar, o None si falta algún modelo o
        OpenCV no puede cargarlo. Con None, el servicio responde `estimator_configured: false`.
    """
    config = config if config is not None else settings
    configured = {name: str(getattr(config, name, "") or "").strip() for name in MODEL_PATH_SETTINGS}
    if not any(configured.values()):
        return None
    paths = {name: resolve_model_path(value) for name, value in configured.items()}
    missing = [name for name, path in paths.items() if path is None]
    if missing:
        logger.warning(
            "Estimación de edad deshabilitada: falta configurar o no existe el archivo de %s.",
            ", ".join(missing),
        )
        return None
    try:
        return estimator_class(
            paths["AGE_FACE_DETECTOR_PATH"],
            paths["AGE_CLASSIFIER_PROTOTXT_PATH"],
            paths["AGE_CLASSIFIER_MODEL_PATH"],
        )
    except Exception:
        logger.warning("Estimación de edad deshabilitada: OpenCV no pudo cargar los modelos configurados.")
        return None

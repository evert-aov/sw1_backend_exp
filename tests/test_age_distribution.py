"""Pruebas de HU-16: ventana etaria en memoria y consulta protegida; sin PostgreSQL ni modelos descargados."""

import asyncio
import logging
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import numpy as np
import pytest
from fastapi import HTTPException

from app.core.config import BACKEND_ROOT
from app.live.entity.audience_metric import AgeGroupEnum
from app.live.entity.live_session import LiveSession
from app.live.service.age_estimation_service import (
    AGE_GROUP_ORDER,
    AgeDistributionService,
    AgeEstimationError,
    age_group_for_age,
)
from app.live.service.opencv_age_estimator import (
    CAFFE_AGE_BUCKETS,
    OpenCvAgeEstimator,
    age_group_for_bucket,
    build_age_estimator_from_settings,
    resolve_model_path,
)

SESSION_ID = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"
OTHER_SESSION_ID = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5c"
WALL_TIME = datetime(2026, 11, 8, 20, 0, tzinfo=timezone.utc)


class FakeClock:
    """Reloj monotónico controlable para mover la ventana sin esperar."""

    def __init__(self, now: float = 1000.0):
        """Fija el instante inicial de la prueba."""
        self.now = now

    def __call__(self) -> float:
        """Devuelve el instante actual simulado."""
        return self.now


class FixedEstimator:
    """Doble de prueba: devuelve rangos predefinidos y solo anota el tamaño del fotograma."""

    def __init__(self, groups):
        """Guarda los rangos que devolverá en cada llamada."""
        self.groups = list(groups)
        self.sizes = []

    def estimate(self, frame: bytes):
        """Simula la salida del contrato sin conservar la imagen."""
        self.sizes.append(len(frame))
        return list(self.groups)


class FailingEstimator:
    """Doble de prueba cuyo modelo falla con un mensaje interno."""

    def estimate(self, frame: bytes):
        """Lanza un error que no debe llegar al llamador."""
        raise RuntimeError("detalle interno del modelo")


def make_service(estimator=None, clock=None, **options) -> AgeDistributionService:
    """Crea un agregador aislado con relojes deterministas."""
    return AgeDistributionService(
        estimator, clock=clock or FakeClock(), wall_clock=lambda: WALL_TIME, **options
    )


def shares(result) -> dict:
    """Resume la distribución como {rango: porcentaje} para comparar."""
    return {item.age_group: item.percentage for item in result.distribution}


def test_distribution_percentages_counts_and_dominant_group():
    """Los porcentajes se calculan sobre todos los rostros de la ventana."""
    service = make_service()
    service.record_groups(SESSION_ID, [AgeGroupEnum.YOUNG_ADULT, AgeGroupEnum.YOUNG_ADULT, AgeGroupEnum.ADULT])
    result = service.record_groups(SESSION_ID, ["YOUNG_ADULT", "SENIOR"])

    assert [item.age_group for item in result.distribution] == list(AGE_GROUP_ORDER)
    assert shares(result) == {
        AgeGroupEnum.YOUTH: 0.0,
        AgeGroupEnum.YOUNG_ADULT: 60.0,
        AgeGroupEnum.ADULT: 20.0,
        AgeGroupEnum.SENIOR: 20.0,
    }
    assert [item.count for item in result.distribution] == [0, 3, 1, 1]
    assert result.sample_count == 2
    assert result.detections_count == 5
    assert result.dominant_age_group == AgeGroupEnum.YOUNG_ADULT
    assert result.updated_at == WALL_TIME
    assert result.window_seconds == 60


def test_tied_groups_resolve_to_the_first_in_fixed_order():
    """Un empate devuelve siempre el mismo rango dominante."""
    service = make_service()
    result = service.record_groups(SESSION_ID, [AgeGroupEnum.SENIOR, AgeGroupEnum.ADULT])
    assert result.dominant_age_group == AgeGroupEnum.ADULT


def test_sliding_window_discards_expired_samples_and_idle_sessions():
    """Las muestras vencidas salen de la ventana y la sesión vacía se libera de memoria."""
    clock = FakeClock(1000.0)
    service = make_service(clock=clock, window_seconds=60)
    service.record_groups(SESSION_ID, [AgeGroupEnum.YOUTH])
    clock.now = 1030.0
    service.record_groups(SESSION_ID, [AgeGroupEnum.SENIOR])

    clock.now = 1061.0
    result = service.latest(SESSION_ID)
    assert result.sample_count == 1
    assert shares(result)[AgeGroupEnum.SENIOR] == 100.0
    assert shares(result)[AgeGroupEnum.YOUTH] == 0.0

    clock.now = 1091.0
    empty = service.latest(SESSION_ID)
    assert empty.sample_count == 0
    assert empty.detections_count == 0
    assert empty.dominant_age_group is None
    assert empty.updated_at is None
    assert all(item.percentage == 0.0 for item in empty.distribution)
    assert SESSION_ID not in service._sessions


def test_sessions_are_isolated_normalized_and_clearable():
    """Cada sesión tiene su ventana; el UUID se normaliza entre ingesta y consulta."""
    service = make_service()
    service.record_groups(SESSION_ID.upper(), [AgeGroupEnum.ADULT])
    service.record_groups(OTHER_SESSION_ID, [AgeGroupEnum.YOUTH, AgeGroupEnum.YOUTH])

    first = service.latest(SESSION_ID)
    assert first.session_id == SESSION_ID
    assert first.detections_count == 1
    assert service.latest(OTHER_SESSION_ID).dominant_age_group == AgeGroupEnum.YOUTH

    service.clear(SESSION_ID)
    assert service.latest(SESSION_ID).sample_count == 0
    assert service.latest(OTHER_SESSION_ID).sample_count == 1


def test_frames_without_faces_count_as_samples_only():
    """Un fotograma sin rostros cuenta como muestra, pero no altera porcentajes."""
    service = make_service()
    result = service.record_groups(SESSION_ID, [])
    assert result.sample_count == 1
    assert result.detections_count == 0
    assert result.dominant_age_group is None
    assert result.updated_at == WALL_TIME


def test_max_samples_bounds_memory_per_session():
    """El límite por sesión evita crecer sin control con fotogramas muy frecuentes."""
    service = make_service(max_samples_per_session=3)
    for _ in range(5):
        result = service.record_groups(SESSION_ID, [AgeGroupEnum.YOUTH])
    assert result.sample_count == 3
    assert result.detections_count == 3


def test_invalid_configuration_and_inputs_are_rejected():
    """Configuración, IDs y rangos inválidos fallan de forma explícita."""
    with pytest.raises(ValueError):
        AgeDistributionService(window_seconds=0)
    with pytest.raises(ValueError):
        AgeDistributionService(max_samples_per_session=0)
    with pytest.raises(TypeError):
        AgeDistributionService(estimator=object())
    service = make_service()
    with pytest.raises(ValueError):
        service.latest("  ")
    with pytest.raises(ValueError):
        service.record_groups(SESSION_ID, ["TEEN"])


def test_process_frame_classifies_without_retaining_the_frame():
    """El servicio entrega el fotograma al modelo y no conserva ninguna referencia."""
    estimator = FixedEstimator([AgeGroupEnum.ADULT, AgeGroupEnum.SENIOR])
    service = make_service(estimator)
    frame = bytes(range(256)) * 4
    references_before = sys.getrefcount(frame)

    result = service.process_frame(SESSION_ID, frame)
    references_after = sys.getrefcount(frame)

    assert references_after == references_before
    assert estimator.sizes == [len(frame)]
    assert result.estimator_configured is True
    assert result.detections_count == 2
    assert shares(result)[AgeGroupEnum.ADULT] == 50.0
    stored = [value for sample in service._sessions[SESSION_ID] for value in (sample.monotonic_at, sample.recorded_at, *sample.counts)]
    assert not any(isinstance(value, (bytes, bytearray, memoryview)) for value in stored)


def test_process_frame_without_estimator_does_not_invent_data():
    """Sin modelo registrado se informa la ausencia y no se agregan muestras."""
    service = make_service()
    result = service.process_frame(SESSION_ID, b"frame")
    assert result.estimator_configured is False
    assert result.sample_count == 0
    assert all(item.percentage == 0.0 for item in result.distribution)


def test_estimator_errors_do_not_expose_internal_context():
    """Un fallo del modelo no se encadena ni registra muestras parciales."""
    service = make_service(FailingEstimator())
    with pytest.raises(AgeEstimationError) as error:
        service.process_frame(SESSION_ID, b"frame")
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert "detalle interno" not in str(error.value)
    assert service.latest(SESSION_ID).sample_count == 0

    service.set_estimator(FixedEstimator(["TEEN"]))
    with pytest.raises(AgeEstimationError):
        service.process_frame(SESSION_ID, b"frame")
    assert service.latest(SESSION_ID).sample_count == 0


def test_processing_frames_writes_no_log_records(caplog):
    """La ingesta no deja rastros del fotograma ni de su contenido en los logs."""
    caplog.set_level(logging.DEBUG)
    service = make_service(FixedEstimator([AgeGroupEnum.YOUTH]))
    service.process_frame(SESSION_ID, b"\xff\xd8sensitive")
    service.latest(SESSION_ID)
    assert caplog.records == []


def test_age_group_for_age_uses_documented_ranges():
    """La conversión de edad numérica respeta los rangos de AgeGroupEnum."""
    cases = {
        0: AgeGroupEnum.YOUTH,
        17.9: AgeGroupEnum.YOUTH,
        18: AgeGroupEnum.YOUNG_ADULT,
        30.5: AgeGroupEnum.YOUNG_ADULT,
        31: AgeGroupEnum.ADULT,
        50: AgeGroupEnum.ADULT,
        50.1: AgeGroupEnum.SENIOR,
    }
    for age, expected in cases.items():
        assert age_group_for_age(age) == expected
    for invalid in (-1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            age_group_for_age(invalid)


def test_distribution_for_host_checks_session_ownership():
    """Solo el anfitrión propietario consulta su sesión; el resto recibe 403, 404 o 422."""
    host_id = str(uuid4())
    service = make_service()
    service.record_groups(SESSION_ID, [AgeGroupEnum.YOUTH])
    db = MagicMock()

    db.get.return_value = SimpleNamespace(host_id=host_id)
    result = service.distribution_for_host(db, SESSION_ID.upper(), host_id)
    assert result.session_id == SESSION_ID
    db.get.assert_called_with(LiveSession, SESSION_ID)

    with pytest.raises(HTTPException) as forbidden:
        service.distribution_for_host(db, SESSION_ID, str(uuid4()))
    assert forbidden.value.status_code == 403

    db.get.return_value = None
    with pytest.raises(HTTPException) as missing:
        service.distribution_for_host(db, SESSION_ID, host_id)
    assert missing.value.status_code == 404

    db.get.reset_mock()
    with pytest.raises(HTTPException) as invalid:
        service.distribution_for_host(db, "not-a-uuid", host_id)
    assert invalid.value.status_code == 422
    db.get.assert_not_called()


class FakeFaceDetector:
    """Doble de YuNet: devuelve cajas fijas y anota el tamaño de entrada recibido."""

    def __init__(self, faces):
        """Guarda las filas que devolverá detect."""
        self.faces = faces
        self.input_sizes = []

    def setInputSize(self, size):
        """Registra el tamaño del fotograma."""
        self.input_sizes.append(size)

    def detect(self, image):
        """Simula la salida (retval, faces) de cv2.FaceDetectorYN."""
        return 1, self.faces


class FakeAgeNet:
    """Doble de la red Caffe: devuelve probabilidades fijas y anota lo que recibe."""

    def __init__(self, predictions):
        """Guarda las probabilidades que devolverá forward."""
        self.predictions = predictions
        self.inputs = []

    def setInput(self, blob):
        """Registra el lote de recortes preparado por el estimador."""
        self.inputs.append(blob)

    def forward(self):
        """Simula la inferencia de la red."""
        return self.predictions


def fake_cv_module(image, faces=None, predictions=None):
    """Construye un módulo compatible con cv2 que no lee archivos ni carga modelos."""
    detector = FakeFaceDetector(faces)
    net = FakeAgeNet(predictions)
    module = SimpleNamespace(
        IMREAD_COLOR=1,
        imdecode=lambda buffer, flags: image,
        FaceDetectorYN=SimpleNamespace(create=lambda *args: detector),
        dnn=SimpleNamespace(
            readNetFromCaffe=lambda prototxt, model: net,
            # El lote de prueba conserva solo la forma de cada recorte.
            blobFromImages=lambda crops, *args, **kwargs: [crop.shape for crop in crops],
        ),
    )
    return module, detector, net


def yunet_row(x, y, width, height, score=0.95):
    """Fila de YuNet: caja, 10 coordenadas de puntos faciales y confianza."""
    return [x, y, width, height, *([0.0] * 10), score]


def one_hot(*indexes):
    """Probabilidades de la red Caffe con certeza total en las clases indicadas."""
    rows = np.zeros((len(indexes), len(CAFFE_AGE_BUCKETS)), dtype=np.float32)
    for row, index in enumerate(indexes):
        rows[row, index] = 1.0
    return rows


def make_opencv_estimator(image, faces=None, predictions=None):
    """Crea el estimador real con OpenCV sustituido por dobles."""
    module, detector, net = fake_cv_module(image, faces, predictions)
    estimator = OpenCvAgeEstimator("yunet.onnx", "age.prototxt", "age.caffemodel", cv_module=module)
    return estimator, detector, net


def test_caffe_age_buckets_map_to_groups_by_midpoint():
    """Los 8 rangos de la red Caffe se asignan por punto medio a los cuatro grupos de HU-16."""
    assert [label for label, _, _ in CAFFE_AGE_BUCKETS] == [
        "0-2", "4-6", "8-12", "15-20", "25-32", "38-43", "48-53", "60-100",
    ]
    assert [group for _, _, group in CAFFE_AGE_BUCKETS] == [
        AgeGroupEnum.YOUTH,
        AgeGroupEnum.YOUTH,
        AgeGroupEnum.YOUTH,
        AgeGroupEnum.YOUTH,
        AgeGroupEnum.YOUNG_ADULT,
        AgeGroupEnum.ADULT,
        AgeGroupEnum.SENIOR,
        AgeGroupEnum.SENIOR,
    ]
    for label, midpoint, group in CAFFE_AGE_BUCKETS:
        low, high = (float(value) for value in label.split("-"))
        assert midpoint == (low + high) / 2
        assert age_group_for_age(midpoint) == group
    assert age_group_for_bucket(3) == AgeGroupEnum.YOUTH
    assert age_group_for_bucket(6) == AgeGroupEnum.SENIOR
    for invalid in (-1, len(CAFFE_AGE_BUCKETS)):
        with pytest.raises(ValueError):
            age_group_for_bucket(invalid)


def test_opencv_estimator_returns_one_group_per_detected_face():
    """Cada rostro se recorta con margen dentro de la imagen y recibe un rango."""
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    faces = np.array(
        [yunet_row(10, 10, 40, 40), yunet_row(100, 60, 30, 36), yunet_row(-5, -5, 20, 20)],
        dtype=np.float32,
    )
    estimator, detector, net = make_opencv_estimator(image, faces, one_hot(4, 7, 0))

    groups = estimator.estimate(b"jpeg")

    assert groups == [AgeGroupEnum.YOUNG_ADULT, AgeGroupEnum.SENIOR, AgeGroupEnum.YOUTH]
    assert detector.input_sizes == [(160, 120)]
    assert net.inputs == [[(56, 56, 3), (51, 45, 3), (19, 19, 3)]]


def test_opencv_estimator_without_faces_returns_an_empty_list():
    """Sin rostros no se ejecuta la red de edad y no se informa ningún rango."""
    image = np.zeros((48, 64, 3), dtype=np.uint8)
    for faces in (None, np.zeros((0, 15), dtype=np.float32)):
        estimator, _, net = make_opencv_estimator(image, faces, one_hot(0))
        assert estimator.estimate(b"jpeg") == []
        assert net.inputs == []


def test_opencv_estimator_rejects_invalid_frames_and_models():
    """Una imagen ilegible o una red distinta de la de 8 rangos no generan datos."""
    estimator, _, _ = make_opencv_estimator(None)
    with pytest.raises(ValueError):
        estimator.estimate(b"no-es-imagen")
    service = make_service(estimator)
    with pytest.raises(AgeEstimationError):
        service.process_frame(SESSION_ID, b"no-es-imagen")
    assert service.latest(SESSION_ID).sample_count == 0

    image = np.zeros((48, 64, 3), dtype=np.uint8)
    faces = np.array([yunet_row(10, 10, 20, 20)], dtype=np.float32)
    gender_like, _, _ = make_opencv_estimator(image, faces, np.array([[0.4, 0.6]], dtype=np.float32))
    with pytest.raises(ValueError):
        gender_like.estimate(b"jpeg")
    with pytest.raises(ValueError):
        OpenCvAgeEstimator("a", "b", "c", score_threshold=0, cv_module=fake_cv_module(image)[0])


def test_missing_model_files_leave_the_estimator_unregistered(tmp_path):
    """Si alguna ruta falta o no existe, no se carga OpenCV y el servicio sigue sin modelo."""
    estimator_class = MagicMock()
    empty = SimpleNamespace(AGE_FACE_DETECTOR_PATH="", AGE_CLASSIFIER_PROTOTXT_PATH="", AGE_CLASSIFIER_MODEL_PATH="")
    assert build_age_estimator_from_settings(empty, estimator_class) is None

    detector_file = tmp_path / "yunet.onnx"
    detector_file.write_bytes(b"relleno")
    partial = SimpleNamespace(
        AGE_FACE_DETECTOR_PATH=str(detector_file),
        AGE_CLASSIFIER_PROTOTXT_PATH=str(tmp_path / "no-existe.prototxt"),
        AGE_CLASSIFIER_MODEL_PATH="",
    )
    assert build_age_estimator_from_settings(partial, estimator_class) is None
    estimator_class.assert_not_called()

    service = make_service(estimator_factory=lambda: build_age_estimator_from_settings(partial, estimator_class))
    result = service.process_frame(SESSION_ID, b"frame")
    assert result.estimator_configured is False
    assert result.sample_count == 0


def test_configured_model_files_build_the_estimator_once(tmp_path):
    """Con los tres archivos presentes se instancia el estimador con rutas resueltas."""
    files = [tmp_path / name for name in ("yunet.onnx", "age.prototxt", "age.caffemodel")]
    for path in files:
        path.write_bytes(b"relleno")
    config = SimpleNamespace(
        AGE_FACE_DETECTOR_PATH=str(files[0]),
        AGE_CLASSIFIER_PROTOTXT_PATH=str(files[1]),
        AGE_CLASSIFIER_MODEL_PATH=f"  {files[2]}  ",
    )
    estimator_class = MagicMock(return_value="estimador")
    assert build_age_estimator_from_settings(config, estimator_class) == "estimador"
    estimator_class.assert_called_once_with(*files)

    failing_class = MagicMock(side_effect=RuntimeError("cv2.error: modelo corrupto"))
    assert build_age_estimator_from_settings(config, failing_class) is None


def test_relative_model_paths_resolve_from_backend_root():
    """Las rutas relativas del .env se interpretan desde la carpeta del backend."""
    assert resolve_model_path("tests/test_age_distribution.py") == BACKEND_ROOT / "tests" / "test_age_distribution.py"
    assert resolve_model_path("tests/no-existe.onnx") is None
    assert resolve_model_path("   ") is None


def test_service_builds_the_estimator_lazily_once():
    """El estimador se construye en el primer uso, una sola vez, sin editar main.py."""
    factory = MagicMock(return_value=None)
    service = make_service(estimator_factory=factory)
    factory.assert_not_called()
    assert service.latest(SESSION_ID).estimator_configured is False
    service.process_frame(SESSION_ID, b"frame")
    assert factory.call_count == 1

    lazy = make_service(estimator_factory=lambda: FixedEstimator([AgeGroupEnum.ADULT]))
    result = lazy.process_frame(SESSION_ID, b"frame")
    assert result.estimator_configured is True
    assert result.dominant_age_group == AgeGroupEnum.ADULT


def test_explicit_estimator_takes_priority_over_lazy_factory():
    """set_age_estimator, incluso con None, prevalece sobre el estimador por defecto."""
    factory = MagicMock(return_value=FixedEstimator([AgeGroupEnum.YOUTH]))
    service = make_service(estimator_factory=factory)
    service.set_estimator(FixedEstimator([AgeGroupEnum.SENIOR]))
    assert service.process_frame(SESSION_ID, b"frame").dominant_age_group == AgeGroupEnum.SENIOR

    disabled = make_service(estimator_factory=factory)
    disabled.set_estimator(None)
    assert disabled.estimator_configured is False
    factory.assert_not_called()


def test_lazy_factory_failure_keeps_the_service_available():
    """Un fallo al cargar modelos no interrumpe la ingesta ni la consulta."""
    service = make_service(estimator_factory=MagicMock(side_effect=RuntimeError("modelo corrupto")))
    result = service.process_frame(SESSION_ID, b"frame")
    assert result.estimator_configured is False
    assert service.latest(SESSION_ID).sample_count == 0


class AgeDistributionHttpTests(unittest.IsolatedAsyncioTestCase):
    """Comprueba la ruta real por ASGI sin iniciar el lifespan ni abrir PostgreSQL."""

    async def asyncSetUp(self):
        """Prepara el cliente ASGI y dependencias aisladas."""
        from main import app
        from app.auth.entity.user import User

        async def pulse():
            """Despierta el bucle cuando el sandbox limita señalización entre hilos."""
            while True:
                await asyncio.sleep(0.01)

        self.app = app
        self.pulse = asyncio.create_task(pulse())
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        self.previous = dict(app.dependency_overrides)
        self.user = User(id=str(uuid4()), first_name="Host", email="host@example.com", is_active=True)
        self.db = MagicMock()
        self.service = make_service()
        self.path = f"/api/live/sessions/{SESSION_ID}/age-distribution"

    async def asyncTearDown(self):
        """Restaura dependencias y cierra el transporte."""
        self.app.dependency_overrides.clear()
        self.app.dependency_overrides.update(self.previous)
        await self.client.aclose()
        self.pulse.cancel()
        await asyncio.gather(self.pulse, return_exceptions=True)

    def authenticate(self):
        """Sustituye base, usuario y agregador por dobles de prueba."""
        from app.core.database import get_db
        from app.core.security import get_current_active_user
        from app.live.service.age_estimation_service import get_age_distribution_service

        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[get_current_active_user] = lambda: self.user
        self.app.dependency_overrides[get_age_distribution_service] = lambda: self.service

    async def test_requires_authentication(self):
        """Sin JWT no se revela la distribución de ninguna sesión."""
        response = await asyncio.wait_for(self.client.get(self.path), 5)
        self.assertEqual(response.status_code, 401)

    async def test_requires_host_role(self):
        """Un asistente autenticado no puede consultar la consola del anfitrión."""
        self.authenticate()
        with patch("app.auth.repository.user_repository.UserRepository.get_user_roles", return_value=["ATTENDEE"]):
            response = await asyncio.wait_for(self.client.get(self.path), 5)
        self.assertEqual(response.status_code, 403, response.text)
        self.db.get.assert_not_called()

    async def test_host_owner_receives_latest_distribution(self):
        """El anfitrión propietario recibe porcentajes agregados sin datos de imagen."""
        self.authenticate()
        self.service.record_groups(SESSION_ID, [AgeGroupEnum.YOUNG_ADULT, AgeGroupEnum.YOUNG_ADULT, AgeGroupEnum.ADULT, AgeGroupEnum.SENIOR])
        self.db.get.return_value = SimpleNamespace(host_id=self.user.id)
        with patch("app.auth.repository.user_repository.UserRepository.get_user_roles", return_value=["HOST"]):
            response = await asyncio.wait_for(self.client.get(self.path), 5)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["session_id"], SESSION_ID)
        self.assertEqual(body["dominant_age_group"], "YOUNG_ADULT")
        self.assertEqual(
            [(item["age_group"], item["percentage"]) for item in body["distribution"]],
            [("YOUTH", 0.0), ("YOUNG_ADULT", 50.0), ("ADULT", 25.0), ("SENIOR", 25.0)],
        )
        self.assertFalse(body["estimator_configured"])
        self.db.commit.assert_not_called()

    async def test_host_cannot_read_another_hosts_session(self):
        """Tener rol HOST no basta: la sesión debe pertenecer al usuario."""
        self.authenticate()
        self.db.get.return_value = SimpleNamespace(host_id=str(uuid4()))
        with patch("app.auth.repository.user_repository.UserRepository.get_user_roles", return_value=["HOST"]):
            response = await asyncio.wait_for(self.client.get(self.path), 5)
        self.assertEqual(response.status_code, 403, response.text)

    async def test_endpoint_is_documented_in_openapi(self):
        """Swagger publica resumen y descripción del endpoint."""
        operation = self.app.openapi()["paths"]["/api/live/sessions/{session_id}/age-distribution"]["get"]
        self.assertIn("HU-16", operation["summary"])
        self.assertTrue(operation["description"])

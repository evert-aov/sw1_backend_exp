# Telemetría en vivo y semáforo de energía (CU-09 / HU-17)

[Índice](README.md) · [Servicio](../app/live/service/live_telemetry_service.py) · [Controlador](../app/live/control/live_telemetry_controller.py) · [Pruebas](../tests/test_live_telemetry.py)

> **HU-17 — Dashboard en vivo con indicadores discretos.** Como moderador o DJ, quiero una vista con semáforos de energía y pulso visual sin saturación de datos, para tomar decisiones ágiles sin distraerme del evento.

## Flujo

```text
Cámara (HU-13/14) → análisis de rostros (HU-15/16) → audience_metrics → LiveTelemetryHub → WebSocket cada 2.5 s → web y móvil
```

La HU-17 no analiza imágenes. Consume las métricas agregadas que el pipeline de visión guarda en `audience_metrics` y las convierte en un indicador que se entiende de un vistazo. Solo maneja números anónimos (GDPR).

## Archivos

| Archivo | Responsabilidad |
| --- | --- |
| `app/live/service/energy_indicator.py` | Funciones puras: índice de energía, suavizado, semáforo con histéresis y tendencia |
| `app/live/service/live_telemetry_service.py` | `LiveTelemetryHub`: estado por sesión y emisión sincronizada cada 2.5 s |
| `app/live/service/live_telemetry_access.py` | Quién puede observar una sesión (anfitrión dueño, ADMIN o monitor vinculado) |
| `app/live/service/live_monitor_pairing.py` | Códigos de vinculación y token de monitor para tablets y celulares |
| `app/live/repository/live_telemetry_repository.py` | Lectura de `audience_metrics` y `live_sessions` |
| `app/live/dto/live_telemetry_dto.py` | Contratos de la instantánea y de la vinculación |
| `app/live/control/live_telemetry_controller.py` | Endpoints REST y WebSocket |
| `scripts/seed_live_telemetry_demo.py` | Seed de demostración (métricas simuladas) |

Los archivos compartidos del módulo `live` (`live_websocket_controller.py`, `computer_vision_service.py`, `live_repositories.py`) no se modifican, para no interferir con HU-13 a HU-16.

## Reglas del semáforo

| Concepto | Regla |
| --- | --- |
| Índice de energía | `0.6 × atención + 0.4 × alegría` (0 a 1) |
| Suavizado | Media de las últimas 4 muestras (10 s) |
| Umbrales | Verde ≥ 0.65 · Amarillo ≥ 0.40 · Rojo < 0.40 |
| Histéresis | Subir de nivel es inmediato; bajar exige caer 0.05 bajo el umbral, así un instante aislado no cambia el color |
| Tendencia | `RISING`/`FALLING` si la media de las 2 últimas muestras difiere más de 0.03 de las 2 anteriores |
| Señal | `LIVE` ≤ 7.5 s · `STALE` ≤ 30 s · `NO_SIGNAL` sin métricas recientes |
| Pulso | Últimos 24 puntos (60 s) |

## Endpoints

| Método | Ruta | Acceso | Uso |
| --- | --- | --- | --- |
| WS | `/api/live/telemetry/ws/{session_id}?token=` | Anfitrión dueño, ADMIN o token de monitor | Instantánea al conectar y luego cada 2.5 s. `{"type":"ping"}` responde `pong` |
| GET | `/api/live/telemetry/sessions/{session_id}` | Anfitrión dueño o ADMIN | Misma instantánea por REST (carga inicial o respaldo) |
| POST | `/api/live/telemetry/sessions/{session_id}/monitor-code` | Anfitrión dueño o ADMIN | Código de 6 caracteres, un solo uso, 15 min |
| POST | `/api/live/telemetry/monitor/redeem` | Público | Canjea el código por un token de monitor de 8 h |

Cierres del WebSocket: `4401` token inválido, `4403` sin permiso, `4404` sesión inexistente. Los navegadores no admiten cabeceras en WebSocket, por eso el token viaja en la query.

## Vinculación de tablets y celulares

La app móvil solo admite cuentas ATTENDEE. Para que el anfitrión vea el semáforo en su celular sin romper esa regla, genera un código en la consola web y lo ingresa en la app. El token de monitor:

- se firma con una clave derivada de `JWT_SECRET` y otra audiencia, de modo que el resto de la API lo rechaza (401);
- solo abre el WebSocket de la sesión vinculada y se invalida si la sesión cambia de anfitrión o la cuenta se desactiva;
- el canje admite 10 intentos fallidos por IP cada 5 minutos (luego responde 429).

Los códigos pendientes viven en memoria del proceso: si la API se reinicia, se genera uno nuevo.

## Integración con el pipeline de visión

El hub lee `audience_metrics` en cada ciclo, así que basta con que HU-13 a HU-16 persistan sus métricas allí. Opcionalmente, quien calcule una métrica puede notificarla de inmediato:

```python
from app.live.service.live_telemetry_service import live_telemetry_hub

live_telemetry_hub.publish(session_id, metrics_dto)  # LiveMetricsDTO
```

Las métricas repetidas (misma fecha) se descartan, así que publicar y persistir a la vez no duplica puntos.

## Demostración

```sh
# Crea o reutiliza una sesión ACTIVE de host@experiencia.com e imprime la URL de la consola
venv/Scripts/python scripts/seed_live_telemetry_demo.py

# Inserta una métrica cada 2.5 s (ciclo de unos 3 min que recorre los tres colores)
venv/Scripts/python scripts/seed_live_telemetry_demo.py --stream --duration 600
```

Opciones: `--host-email`, `--experience-id`, `--history N`, `--seed`.

## Pruebas

```sh
venv/Scripts/python -m pytest -q tests/test_live_telemetry.py
```

Son 38 pruebas sin PostgreSQL: umbrales, histéresis, tendencia, estado de señal, emisión periódica, clientes caídos, permisos, cierres del WebSocket, códigos de un solo uso, límite de intentos y aislamiento del token de monitor.

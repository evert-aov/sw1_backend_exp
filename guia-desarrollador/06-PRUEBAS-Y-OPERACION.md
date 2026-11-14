# Pruebas y operación

[Índice](README.md) · [Suite](../tests/test_security_pricing_bookings.py) · [Integración PostgreSQL](../tests/test_postgres_integration.py)

Desde experiencia_back/, con Python 3.14.6 y dependencias instaladas:

```sh
python -m ruff check app tests scripts
python -m ruff format --check app tests scripts
pyright app
python -m pytest tests/test_security_pricing_bookings.py tests/test_age_distribution.py tests/test_database_configuration.py tests/test_stripe_configuration.py -q

# Suite completa; la integración con PostgreSQL depende del entorno configurado.
venv/bin/python -B -m pytest -q -p no:cacheprovider -rs
venv/bin/python scripts/check_database.py
```

Con el entorno virtual activo, instalá las herramientas de desarrollo con `python -m pip install -r requirements-dev.txt`. CI ejecuta Ruff (lint y formato) y Pyright solo sobre archivos Python modificados respecto de la rama base, además de los cuatro módulos de prueba indicados arriba. Esto no equivale a ejecutar la suite completa ni sus pruebas PostgreSQL.

La suite cubre configuración, rechazo de privilegios, mantenimiento deshabilitado, HTTP sin autenticación, JWT revocado, cotización, límites monetarios, pertenencia de reservas y reglas de retención. Las pruebas unitarias usan dobles y no demuestran bloqueos reales.

La integración intenta abrir PostgreSQL configurado. Si el sistema devuelve PermissionError por sockets, omite explícitamente los casos: no los cuenta como aprobados ni cambia a SQLite. Si hay acceso, crea un esquema de nombre único experiencia_test_*, verifica current_schema(), crea el modelo ORM y al terminar elimina solo ese esquema. Los casos usan sesiones reales, incluyendo dos solicitudes concurrentes por el último cupo. Esto tampoco sustituye probar las migraciones Alembic desde el esquema de trabajo.

Pytest y Alembic están instalados. El SQL de toda la cadena se genera con `venv/bin/python -m alembic upgrade head --sql`; esto no ejecuta DDL en PostgreSQL. La dependencia qrcode está declarada, pero su instalación en este entorno sigue bloqueada por DNS; instalar requirements para renderizar SVG en web. El archivo histórico test_auth_endpoints.py no existe y no es la suite vigente.

El [avance](../../docs/AVANCE_SPRINT_2.md) registra resultados concretos y pendientes. El entorno actual bloquea tanto TCP como socket Unix PostgreSQL; la solicitud de ejecución fuera del aislamiento fue rechazada por política en el paso anterior. No se ejecutaron migraciones ni operaciones de reset/seed sobre esa base.

## Diagnóstico

| Síntoma | Revisar |
| --- | --- |
| Operation not permitted | Acceso a red/socket de la sesión de ejecución |
| Error de contraseña/base inexistente | Destino y permisos del .env, sin imprimir secretos |
| Tabla revoked_tokens ausente | Migración 20261025_01 antes de usar JWT de esta versión |
| Columnas de reservas ausentes | Migración 20261025_02 y reconciliación del esquema previo |
| `bookings.unit_price` no existe | Instalar requirements y migrar con `python scripts/migrate_database.py`, o arrancar con `DB_SYNCHRONIZE=true` |
| Faltan todas las tablas tras recrear la base | Con `DB_SYNCHRONIZE=true`, el arranque aplica la cadena Alembic completa; con `false`, ejecutar el migrador antes de iniciar |
| No existe alembic.__main__ | Dependencia Alembic no instalada |
| Checkout devuelve 503 | Configurar claves Stripe y URL de retorno; no se simulan cobros |
| Checkout devolvía 502 sin detalle | Revisar la nueva línea Stripe checkout failed; distingue autenticación, red, importe y configuración |
| QR devuelve 503 | Instalar qrcode desde requirements en el mismo entorno Python |
| Devolución queda pendiente | Ejecutar conciliador; failed/canceled requiere revisión operativa |
| Mantenimiento HTTP devuelve 404 | Deshabilitado por defecto, incluso con ADMIN |

La conexión exitosa, la revisión del esquema y las pruebas de transacciones constituyen evidencias diferentes. El endpoint / solo publica metadatos; no demuestra que todo el sprint esté operativo.

## Escaneo de seguridad automatizado

CI ejecuta Trivy `v0.70.0` sobre el checkout para detectar vulnerabilidades de dependencias y secretos; la acción está fijada a una revisión inmutable y tiene un límite de diez minutos. El JSON original permanece en el directorio temporal del runner y se elimina al terminar; solo el reporte sanitizado se conserva como artefacto de GitHub Actions durante 14 días. El reporte `security-report/v1` comparte los campos comunes (`service`, `version`, `phase`, `status`, `code`, `cause_status`, `evidence`, `possible_causes` y `recommended_actions`) e incluye `evidence.output_validation`, un código seguro para diagnosticar la validación del JSON. Incluye conteos y metadatos validados de vulnerabilidades. Para secretos expone identificadores de regla y rutas relativas validadas, agrupados por par con su conteo y limitados a 20 entradas; las rutas inseguras se redactan y `secret_findings_truncated` indica si hubo más. Nunca incluye valores detectados ni números de línea.

El gate bloquea cualquier hallazgo de secreto y vulnerabilidades `HIGH` o `CRITICAL`. `MEDIUM`, `LOW` y `UNKNOWN` quedan como avisos para revisión. No hay reglas de exclusión de rutas ni allowlists de secretos. Un escaneo omitido, fallido o con salida ausente/malformada no puede aprobar; el parser exige `SchemaVersion: 2`, acepta `ArtifactType: filesystem` y `ArtifactType: repository`, y admite `Results: null` para un escaneo limpio. Trivy cambia automáticamente a `repository` al escanear un directorio que contiene metadatos Git.

Para validar el generador del reporte: `PYTHONPATH=. python tests/test_security_report.py`. La prueba cubre secretos, severidades bloqueantes, avisos de severidad inferior y salidas malformadas/no ejecutadas, y comprueba que el reporte no filtre coincidencias ni números de línea.

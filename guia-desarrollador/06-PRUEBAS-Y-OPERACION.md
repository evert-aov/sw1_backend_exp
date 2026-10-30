# Pruebas y operación

[Índice](README.md) · [Suite](../tests/test_security_pricing_bookings.py) · [Integración PostgreSQL](../tests/test_postgres_integration.py)

Desde experiencia_back/, con Python 3.14.6 y dependencias instaladas:

```sh
venv/bin/python -B -m pytest -q -p no:cacheprovider -rs
venv/bin/python scripts/check_database.py
```

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

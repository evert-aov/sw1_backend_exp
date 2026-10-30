# PostgreSQL, psql y migraciones

[Índice](README.md) · [Motor](../app/core/database.py) · [Alembic](../alembic/env.py)

## Conexión real

La aplicación usa SQLAlchemy con `psycopg2`; `psql` es la herramienta de inspección. Ambos consumen la misma configuración del backend. El motor no abre conexiones al importarse, no comprueba un host alternativo y no cambia a SQLite ante fallos.

Desde `experiencia_back/`:

```sh
venv/bin/python scripts/check_database.py
```

El [comprobador](../scripts/check_database.py) requiere Python 3.14.6 y el cliente `psql`. Lee el `.env` por `Settings`, pasa credenciales por variables libpq, fuerza sesión de solo lectura y consulta base actual, rol, versión y tablas públicas. No imprime contraseña, URI completa ni valores del `.env`; no crea tablas ni ejecuta semillas. Retorna el código de salida de `psql`.

Un usuario distinto, base distinta o lista de tablas inesperada exige revisar el destino antes de migrar. `Operation not permitted` desde TCP/socket indica una restricción del entorno; `password authentication failed` o `database does not exist` tienen otro origen. No diagnosticar credenciales incorrectas solo porque el sandbox impida abrir un socket.

## Esquema

### Base borrada y creada nuevamente

Una base PostgreSQL nueva no contiene las tablas del proyecto. Con `DB_SYNCHRONIZE=true` en `.env`, `uv run fastapi dev` ejecuta todas las migraciones antes de aceptar solicitudes. El arranque guarda la revisión en `alembic_version`, valida el resultado y no inserta datos de demostración. En el siguiente arranque, conserva el esquema y sus datos y aplica únicamente revisiones pendientes.

Alembic debe estar instalado en el mismo entorno: `uv pip install --python venv/bin/python -r requirements.txt`. El arranque no instala dependencias. Si `DB_SYNCHRONIZE=false`, primero ejecutar `venv/bin/python scripts/migrate_database.py`. No es necesario borrar la base para inicializarla o actualizarla.

### Error `column bookings.unit_price does not exist`

El modelo incorpora campos de reservas de `20261025_02`, pero la base todavía conserva una estructura anterior. La carga de reservas pendientes desde el detalle/catálogo también consulta esas columnas, aunque no haya reservas que mostrar. Reiniciar Uvicorn o ejecutar `create_all()` no añade columnas a tablas ya existentes.

Desde `experiencia_back/`, con Python 3.14.6:

```sh
venv/bin/python -m pip install -r requirements.txt
venv/bin/python scripts/migrate_database.py
```

Después de completar el comando, reiniciar la API. El script usa el mismo `.env`, verifica la revisión y aplica Alembic hasta head dentro de una transacción compartida. `--check` inspecciona sin escribir y puede devolver diferencias cuando aún falta migrar.

Si la instalación antigua creó tablas mediante `create_all()` sin historial Alembic, el script reconoce la revisión inicial solo después de comparar sus columnas, tipos, nulabilidad, claves e índices con la declaración histórica. Si coincide, registra esa base y aplica las revisiones siguientes. Si hay modificaciones parciales o diferencias, aborta y muestra su detalle; no hace un `stamp` arbitrario ni ejecuta reset/seed. Las tablas ajenas al modelo no se eliminan.

Con `DB_SYNCHRONIZE=true`, el arranque usa el mismo [migrador compartido](../app/core/migrations.py) que el comando manual, con bloqueo PostgreSQL y transacción. Con `false`, detecta esquemas incompatibles antes de atender peticiones e indica el comando de migración; esa modalidad no ejecuta DDL.

Las entidades se registran mediante `load_all_entities()`: usuarios/roles, categorías/locales/experiencias, reservas/pagos/entradas/SaaS, grupos/búsquedas/demanda y entidades de live. Los IDs usan UUID SQL; se generan como UUIDv7 con Python 3.14.6. Relaciones y restricciones deben existir también en migraciones, no solo en el ORM.

La revisión inicial es `7cfb6d153b7e`, en [alembic/versions](../alembic/versions/7cfb6d153b7e_initial_schema.py). Inspeccionar primero:

```sh
venv/bin/python -m alembic current
venv/bin/python -m alembic heads
venv/bin/python -m alembic history
```

Para una base nueva verificada: `venv/bin/python -m alembic upgrade head`. Si ya existen tablas sin revisión, comparar el esquema antes de decidir una reconciliación. No usar `stamp head` para ocultar diferencias ni reiniciar datos existentes.

Para cambios: modificar entidades, generar `python -m alembic revision --autogenerate -m "describe_change"`, revisar el SQL y probar avance/retroceso en una base de integración independiente. `python -m alembic check` detecta diferencias con metadatos cuando la herramienta está instalada.

Las revisiones nuevas incluyen [20261025_01](../alembic/versions/20261025_01_persistent_logout.py) (logout), [20261025_02](../alembic/versions/20261025_02_booking_holds.py) (reservas), [20261025_03](../alembic/versions/20261025_03_stripe_events.py) (eventos Stripe), [20261025_04](../alembic/versions/20261025_04_matching_notifications.py) (matching/avisos) y [20261025_05](../alembic/versions/20261025_05_search_evidence.py) (búsquedas). No se aplicaron en esta sesión. Revisar balances, moneda y membresías duplicadas históricas; las restricciones pueden detectar datos inconsistentes. Ver el [avance](../../docs/AVANCE_SPRINT_2.md).

## Semillas y operaciones administrativas

`seed.py` y `app/core/seeder.py` contienen altas de demostración. `seed.py` aún llama a `create_all()` y puede imprimir información de usuarios; no sustituye migraciones. `--clean` y los métodos `reset_*` eliminan datos. Ninguno se ejecuta como parte de comprobar conexión.

Las rutas HTTP `/api/system/*` exigen ADMIN y ENABLE_MAINTENANCE_ENDPOINTS=true. Están deshabilitadas por defecto; no se invocan al comprobar conexión.

# Guía del desarrollador — FastAPI, Python 3.14.6 y PostgreSQL

El backend de EXPERIENCIA usa módulos por dominio con controladores, DTO, servicios, repositorios y entidades SQLAlchemy. PostgreSQL es la persistencia del proyecto. Incluye reservas, adaptador Stripe, devolución/conciliación, QR, matching, avisos persistentes y demanda observada. La aceptación real depende de las verificaciones externas registradas en el [avance](../../docs/AVANCE_SPRINT_2.md).

| Capítulo | Contenido |
| --- | --- |
| [00 — Arquitectura y configuración](00-ARQUITECTURA-Y-CONFIGURACION.md) | Python, entorno, arranque y propiedad de configuración |
| [01 — PostgreSQL y migraciones](01-POSTGRESQL-Y-MIGRACIONES.md) | psql, conexión, entidades y Alembic |
| [02 — Autenticación y perfiles](02-AUTENTICACION-Y-PERFILES.md) | CU-01/CU-02, JWT y permisos |
| [03 — Experiencias y catálogo](03-EXPERIENCIAS-Y-CATALOGO.md) | Publicación, aforos, filtros y contratos |
| [04 — Reservas, pagos y entradas](04-RESERVAS-PAGOS-Y-ENTRADAS.md) | Estado actual y desarrollo de CU-05 |
| [05 — Matching y demanda](05-MATCHING-Y-DEMANDA.md) | CU-06/CU-07 y fronteras de sprint 2 |
| [06 — Pruebas y operación](06-PRUEBAS-Y-OPERACION.md) | Comandos, diagnóstico y evidencia |
| [07 — Directorios y flujos](07-MAPA-DE-DIRECTORIOS-Y-FLUJOS.md) | Dónde extender y cómo fluye una solicitud |
| [08 — Roles y administración](08-ROLES-Y-ADMINISTRACION.md) | Permisos, propiedad, asignaciones y primera cuenta ADMIN |
| [09 — Seed de prueba](09-SEED-DE-ROLES-Y-ESCENARIOS.md) | Cuentas ficticias, lugares propios, reservas, entradas y grupos |

Desde `experiencia_back/`, con Python 3.14.6 y PostgreSQL preparado:

```sh
python --version
python -m venv venv
venv/bin/python -m pip install -r requirements.txt
# Crear .env desde .env.example solo si aún no existe; completar valores locales.
venv/bin/python scripts/check_database.py
# Comprueba y actualiza sin recrear tablas existentes:
venv/bin/python scripts/migrate_database.py
venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

API: `http://localhost:8000/api`. Swagger: `/docs`. También se puede iniciar con `uv run fastapi dev` si la CLI de FastAPI está instalada en el entorno activo. El arranque espera PostgreSQL. Con `DB_SYNCHRONIZE=true`, aplica Alembic hasta `head`, incluso en una base recién creada. Con `false`, exige migrar previamente mediante el comando anterior y solo valida la estructura. Las semillas se ejecutan por separado.

Ver [guía del equipo](../../docs/GUIAS_DESARROLLADORES.md), [web](../../experiencia_front/guia-desarrollador/README.md) y [móvil](../../experiencia_movil/guia-desarrollador/README.md). Código nuevo e identificadores en inglés; documentación de métodos y guías en español. No crear commits por documentar o ejecutar una comprobación.

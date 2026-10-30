# Arquitectura y configuración

[Índice](README.md) · [Configuración](../app/core/config.py) · [Arranque](../main.py)

## Responsabilidades

`main.py` compone routers, CORS, OpenAPI y lifespan. `app/core/` contiene configuración, sesión SQL y seguridad. Cada dominio organiza `control/`, `dto/`, `service/`, `repository/` y `entity/`; `experience/mapper/` transforma entre DTO y entidad.

Un controlador obtiene identidad y valida entrada; un servicio decide reglas; un repositorio accede a SQL. Para operaciones transaccionales nuevas, el servicio controla el commit global: no componer repositorios que confirmen pasos parciales de un pago.

## Entorno

Usar Python **3.14.6**, declarado en [`.python-version`](../.python-version). Dependencias en [requirements.txt](../requirements.txt). El entorno virtual existente no garantiza que todas estén instaladas: comprobar instalación antes de atribuir un error al código.

`Settings` lee siempre el `.env` de la raíz del backend, incluso al lanzar desde otro directorio. Las variables del proceso tienen prioridad. `DATABASE_URL` PostgreSQL prevalece sobre `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME`. Los campos separados codifican correctamente símbolos de contraseña; una contraseña dentro de una URL debe estar codificada como URL.

`JWT_SECRET` es requerido y no tiene secreto de respaldo en el código. Stripe pertenece al backend; ningún cliente debe recibir sus claves. El [ejemplo de entorno](../.env.example) contiene valores ilustrativos, no credenciales reales.

## Arranque

Usar `python -m uvicorn main:app --port 8000` para el desarrollo con ambos clientes. `python main.py` conserva el puerto histórico 3000 si no se define `PORT`, que colisiona con la web; no mezclar ambos comandos.

Lifespan espera `init_db()` antes de servir y libera el pool al salir, incluso si falla el arranque. Se comprueban conexión, tablas, columnas y tipos contra el modelo vigente, evitando un `UndefinedColumn` durante el catálogo.

`DB_SYNCHRONIZE=true` habilita migraciones Alembic al arrancar: crea el esquema versionado en una base vacía y actualiza instalaciones reconocidas. Usa la misma transacción y bloqueo PostgreSQL que el comando manual. Una migración fallida impide arrancar y revierte la transacción. `false` mantiene el arranque de solo validación para despliegues con migraciones separadas. El valor predeterminado del código es `false`; el ejemplo de desarrollo usa `true`. Semillas y reinicios permanecen como operaciones explícitas separadas, descritas en [PostgreSQL](01-POSTGRESQL-Y-MIGRACIONES.md).

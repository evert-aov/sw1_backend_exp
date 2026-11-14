# Fases y reportes del despliegue AWS

El pipeline emite reportes JSON `diagnostic-report/v1` para distinguir la preparación, la compilación, la publicación y las comprobaciones locales de runtime. Un reporte `passed` solo confirma su propia fase; no demuestra que fases posteriores funcionen.

## Fases reportadas

| Fase | Evidencia observada | Límite |
|---|---|---|
| `preparation` | Checkout, configuración AWS/ECR/Buildx, configuración requerida y migraciones previas al arranque | La preparación no demuestra que la imagen se haya compilado o publicado. |
| `build` | `docker buildx build --load` terminó exitosamente | La compilación local no demuestra que ECR tenga la imagen. |
| `publication` | `docker push` terminó exitosamente | La publicación no demuestra que el servicio haya iniciado o esté disponible. |
| `startup` | `docker compose up` terminó exitosamente | No verifica dependencias ni respuesta HTTP. |
| `readiness` | El endpoint local `http://127.0.0.1:8000/health/ready` respondió exitosamente | Es una comprobación desde la instancia; no prueba acceso público. |
| `postdeploy` | `http://127.0.0.1:8000/` devolvió JSON con `status=online` y campos no vacíos `project` y `version` | Conserva la ruta raíz actual y no acepta como éxito una página HTML ajena con HTTP 200. |

El script en EC2 emite el reporte de la fase que falla antes de ejecutar el rollback existente. El rollback restaura el release anterior igual que antes. Ninguna comprobación de despliegue se ejecuta como parte de los tests locales.

## Campos y seguridad

Cada evento incluye `schema`, `service`, `version`, `phase`, `status`, `code`, `cause_status`, `evidence`, `possible_causes` y `recommended_actions`. Los estados comunes son `passed`, `failed`, `not_verified` y `not_applicable`; los estados de causa son `confirmed`, `hypothesis` y `unknown`. Una fase exitosa usa `unknown` porque no requiere explicar una causa; un fallo usa `hypothesis` salvo que la evidencia confirme una causa concreta. `evidence` solo admite campos estructurados y valores allowlisted; el helper ignora texto libre, comandos, tokens, cuerpos, credenciales y otros campos desconocidos.

El helper (`infra/aws/deploy-report.py`) utiliza únicamente la biblioteca estándar de Python y consume un evento JSON sintético por stdin. Para validarlo localmente se ejecutan `python -m pytest tests/test_deploy_report.py`; no se invoca el workflow, el script de despliegue ni servicios externos.

## Preflight local

Desde la raíz del backend, `python -m scripts.preflight` valida configuración y formato de `DATABASE_URL` sin abrir conexiones. `python -m scripts.preflight --check-db` agrega únicamente `SELECT 1`; ejecutalo solo con una base local o de pruebas autorizada. Los reportes identifican campos por nombre y no imprimen sus valores. Las comprobaciones de arranque y readiness se separan: el arranque valida dependencias antes de aceptar tráfico, `/health/live` solo confirma proceso y `/health/ready` comprueba PostgreSQL.

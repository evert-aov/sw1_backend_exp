# Despliegue de EXPERIENCIA Backend en AWS

Esta guía describe el flujo que existe en este repositorio y lo que debe configurar una persona con acceso a AWS y GitHub. **No hay Terraform, CloudFormation, CDK ni scripts de bootstrap/provisión versionados**: los recursos indicados abajo se crean y protegen fuera del repositorio. El backend usa EC2, ECR y SSM; PostgreSQL sigue en Google Cloud SQL, no en AWS.

## Recorrido rápido

1. Cree el proveedor OIDC y el rol de GitHub Actions, ECR, la instancia EC2 y su perfil de instancia SSM/ECR.
2. Configure DNS, puertos, Docker Compose y los archivos privados de runtime en EC2.
3. Configure el environment `aws-production` y las cuatro variables de repositorio indicadas abajo.
4. Valide configuración y conectividad con los comandos de solo lectura.
5. Después de integrar esta rama en `main` y configurar las protecciones, ejecute manualmente `Deploy AWS (Backend)` con `confirm_deployment=true`.
6. Inspeccione el resumen, el artefacto de preflight y el reporte de Actions/SSM; luego ejecute el smoke test externo.

**Precaución antes de integrar:** mientras este PR no esté fusionado, `main` todavía contiene la versión anterior del workflow, que escuchaba `workflow_run` y podía desplegar tras un push exitoso a `main` si estaba configurada AWS. No habilite todavía el role ARN/variables de despliegue ni permita OIDC al workflow viejo. Después de integrar este guard, el workflow solo acepta `workflow_dispatch` en `main`; primero ejecuta un preflight sin permisos AWS y solo el job posterior puede solicitar OIDC. El environment también debe restringirse a `main` y requerir aprobación humana.

## Recursos y estado conocido

| Recurso                                      | Qué necesita el flujo                                                                                                                 | Estado verificable desde el repositorio                                                  |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| GitHub OIDC provider y rol IAM de despliegue | Trust limitado al repositorio y environment; permisos ECR push y SSM SendCommand/GetCommandInvocation                                 | No hay IaC; existencia y configuración externas no verificadas.                          |
| ECR privado                                  | Repositorio para la imagen backend, tags únicos por SHA/run/attempt                                                                   | El workflow construye y publica; no aprovisiona ECR.                                     |
| EC2                                          | Linux x86_64 compatible con la imagen, Docker Engine/Compose plugin, AWS CLI, rutas `/opt/experiencia-aws/{bin,secrets,state,models}` | El script espera la instancia y las rutas; no hay bootstrap versionado.                  |
| Perfil IAM de EC2                            | Systems Manager managed-node permissions y ECR pull solo del repositorio usado                                                        | No hay configuración de perfil en el repo; no verificado.                                |
| Systems Manager                              | SSM Agent conectado y `AWS-RunShellScript` permitido para esa instancia                                                               | El workflow manda shell remoto como root mediante `sudo`; no hay documento SSM propio.   |
| Red/DNS/ACME                                 | IP pública estable, DNS de `AWS_API_HOST`, TCP 80/443 hacia EC2, salida HTTPS                                                         | No hay recursos de red/DNS como código.                                                  |
| Google Cloud SQL                             | Instancia, cuenta de servicio con Cloud SQL Client y JSON de credencial en EC2                                                        | Compose requiere Cloud SQL Auth Proxy; recursos y conectividad GCP no verificables aquí. |
| Stripe/modelos                               | Secretos Stripe si se habilitan pagos; archivos de modelo si se habilita esa funcionalidad                                            | Referenciados como configuración de runtime, no provisionados por este repo.             |

No se observó AWS RDS: no migre la base por asumir que la base vive en AWS. No existe ni se requiere S3/CloudFront para el backend.

## 1. AWS OIDC, GitHub Environment y variables

### Configurar confianza OIDC

En IAM, use el proveedor OIDC `https://token.actions.githubusercontent.com` con audiencia `sts.amazonaws.com` (si ya existe en la cuenta, reutilícelo). Cree un rol dedicado al backend. Su trust policy debe permitir únicamente ese repositorio y el environment `aws-production`, no `*` ni cualquier rama. Para repositorios con el subject clásico de GitHub, la condición central es:

```json
"Condition": {
  "StringEquals": {
    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
    "token.actions.githubusercontent.com:sub": "repo:evert-aov/sw1_backend_exp:environment:aws-production"
  }
}
```

GitHub cambió el formato predeterminado del `sub` para repositorios creados después del 15 de julio de 2026 y para repositorios renombrados/transferidos después de esa fecha. Antes de guardar la policy, confirme el formato exacto que emite este repositorio en la referencia OIDC de GitHub; si usa el formato inmutable, el subject incluye los IDs de owner y repo. No amplíe el patrón para hacer que una asunción falle “funcione”.

En **Settings → Environments**, cree `aws-production` y restrinja ramas/tags de despliegue a `main`. Configure revisores requeridos, evite autoaprobación cuando esté disponible y mantenga separada la aprobación de Actions de la autorización de cambios en AWS. El job con `id-token: write` está ligado a este environment. No se requieren secretos de Actions ni claves AWS estáticas.

### Permisos mínimos del rol de GitHub Actions

Conceda solo los permisos usados por el workflow:

- ECR global: `ecr:GetAuthorizationToken` sobre `*`.
- Repositorio ECR específico: `ecr:BatchCheckLayerAvailability`, `ecr:CompleteLayerUpload`, `ecr:InitiateLayerUpload`, `ecr:PutImage`, `ecr:UploadLayerPart` y `ecr:BatchGetImage` sobre `arn:aws:ecr:<REGION>:<ACCOUNT_ID>:repository/<ECR_REPOSITORY>`.
- SSM `SendCommand` limitado al documento AWS administrado `AWS-RunShellScript` y al ARN de esta única instancia EC2. `ssm:GetCommandInvocation` requiere `Resource: "*"` para consultar el resultado del comando.

**Riesgo operativo importante:** `AWS-RunShellScript` más `sudo` permite ejecutar comandos privilegiados en la instancia. Mitigue con el trust OIDC exacto, environment `main` + aprobación, una sola instancia y revisiones protegidas. Una mejora posterior es un documento SSM propio que admita solo el procedimiento de release, en lugar de shell arbitrario.

### Variables de GitHub

Configure estas **repository variables** en `evert-aov/sw1_backend_exp` (no son secretos). El preflight las valida antes de que el job OIDC empiece:

| Variable                     | Ejemplo de formato, no valor real                      | Finalidad                                       |
| ---------------------------- | ------------------------------------------------------ | ----------------------------------------------- |
| `AWS_DEPLOY_ROLE_ARN`        | `arn:aws:iam::123456789012:role/github-backend-deploy` | Rol OIDC dedicado.                              |
| `AWS_REGION`                 | `us-west-2`                                            | Región de ECR y EC2/SSM.                        |
| `AWS_ECR_REPOSITORY_BACKEND` | `experiencia-backend`                                  | Nombre del repositorio ECR, no el URI completo. |
| `AWS_EC2_INSTANCE_ID`        | `i-0123456789abcdef0`                                  | ID de la instancia destino.                     |

No configure `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` ni contraseñas de nube en GitHub. El workflow no lee GitHub secrets.

## 2. Crear y preparar AWS

### ECR

1. Cree un repositorio ECR privado llamado exactamente como `AWS_ECR_REPOSITORY_BACKEND`, en `AWS_REGION`.
2. Active escaneo al publicar, cifrado y retención de imágenes suficiente para volver al tag anterior. Considere inmutabilidad de tags; el workflow usa `<40-char-SHA>-<run_id>-<run_attempt>`.
3. El rol de EC2 solo necesita `ecr:GetAuthorizationToken` y `ecr:BatchGetImage`, `ecr:BatchCheckLayerAvailability`, `ecr:GetDownloadUrlForLayer` para ese repositorio.

### EC2 y SSM

1. Cree una instancia Ubuntu 24.04 LTS x86_64 en la región elegida y asigne un perfil IAM dedicado. El perfil necesita `AmazonSSMManagedInstanceCore` (o política equivalente acotada) y permisos de pull ECR anteriores.
2. Instale Docker Engine con el plugin `docker compose` y AWS CLI v2. Asegúrese de que el servicio Docker arranque automáticamente. Este repositorio no incluye `bootstrap-ec2.sh`, aunque versiones previas de esta guía lo mencionaban.
3. Cree los directorios que el workflow usa: `/opt/experiencia-aws/bin`, `/opt/experiencia-aws/secrets`, `/opt/experiencia-aws/state` y `/opt/experiencia-aws/models`. El directorio `bin` debe existir antes del primer deploy.
4. Mantenga el SSM Agent registrado como managed node `Online`. Use salida HTTPS a SSM y ECR; agregue VPC endpoints si la instancia no tiene salida pública/NAT. No exponga SSH; use Session Manager para intervención autorizada.
5. Asigne IP pública estática (Elastic IP, recomendable) y permita inbound TCP 80 y 443 desde Internet para API/Let's Encrypt HTTP-01. No abra el puerto 8000: la API se sirve por Traefik. Limite egress según las dependencias requeridas: ECR/SSM, Cloud SQL Proxy y servicios externos.

### DNS, certificados y Cloud SQL

1. Cree un registro DNS `A` para el hostname de API apuntando a la IP estable de EC2. Use exactamente el hostname (sin `https://`) en `AWS_API_HOST` de `runtime.env` en EC2.
2. `compose.yml` ejecuta Traefik v3 con Let's Encrypt HTTP-01 y requiere `ACME_EMAIL`; el DNS debe resolver antes del primer arranque y los puertos 80/443 deben llegar a EC2.
3. Cree/preconfigure Google Cloud SQL PostgreSQL, habilite Cloud SQL Admin API, conectividad y cuenta de servicio con `roles/cloudsql.client`. Copie su clave JSON directamente a `/opt/experiencia-aws/secrets/cloud-sql-service-account.json` mediante un canal seguro (nunca al repo ni a GitHub Actions). Restringa permisos del archivo al usuario esperado por el contenedor del proxy.
4. Defina `CLOUD_SQL_INSTANCE_CONNECTION_NAME` como `PROJECT_ID:REGION:INSTANCE`, y `DATABASE_URL` apuntando al proxy dentro de Compose: `postgresql+psycopg2://<usuario-url-encoded>:<password-url-encoded>@cloud-sql-proxy:5432/<base>`. Ese dialecto coincide con `psycopg2-binary`, instalado por `requirements.txt`.

### Runtime privado de EC2

El workflow no copia ni administra `runtime.env`; prepare `/opt/experiencia-aws/runtime.env` antes del deploy y aplique permisos `0600`. Edítelo mediante un editor privilegiado, no lo pase como argumento de shell ni lo imprima:

```bash
sudo install -o root -g root -m 0600 /dev/null /opt/experiencia-aws/runtime.env
sudoedit /opt/experiencia-aws/runtime.env
sudo chmod 0600 /opt/experiencia-aws/runtime.env
```

No lo imprima en terminales o logs. El runtime env y el JSON de Cloud SQL quedan solo en EC2, fuera de GitHub Actions.

**Requeridas por `compose.yml`:**

| Nombre                               | Formato/uso                                                                                                       |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| `AWS_REGION`                         | Región ECR igual a la de despliegue.                                                                              |
| `ECR_REGISTRY`                       | `<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com`.                                                                    |
| `ECR_REPOSITORY_BACKEND`             | Igual que `AWS_ECR_REPOSITORY_BACKEND`.                                                                           |
| `AWS_API_HOST`                       | Host DNS de API, sin esquema.                                                                                     |
| `ACME_EMAIL`                         | Email operativo para Let's Encrypt.                                                                               |
| `CLOUD_SQL_INSTANCE_CONNECTION_NAME` | `PROJECT_ID:REGION:INSTANCE`.                                                                                     |
| `CLOUD_SQL_CREDENTIALS_FILE`         | Ruta dentro de EC2; por defecto `/opt/experiencia-aws/secrets/cloud-sql-service-account.json`.                    |
| `DATABASE_URL`                       | DSN PostgreSQL de SQLAlchemy hacia `cloud-sql-proxy:5432`; codifique caracteres reservados en usuario/contraseña. |
| `JWT_SECRET`                         | Secreto aleatorio largo, único de producción.                                                                     |

`IMAGE_TAG` se genera en el deploy y se escribe en `release.env`; no lo fije manualmente en `runtime.env`.

**Opcionales con defaults en Compose/app (algunos habilitan funciones):** `JWT_EXPIRES_IN`, `BOOKING_HOLD_MINUTES`, `PAYMENT_CURRENCY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `FRONTEND_URL`, `CORS_ORIGINS`, `EXPERIENCIA_AWS_STATE_DIR`, `EXPERIENCIA_AWS_MODELS_DIR`, `AGE_FACE_DETECTOR_PATH`, `AGE_CLASSIFIER_PROTOTXT_PATH` y `AGE_CLASSIFIER_MODEL_PATH`. Para pagos configure los tres valores Stripe y el endpoint webhook correspondiente como secretos runtime privados. Para CORS, use la lista exacta de orígenes frontend, por ejemplo `CORS_ORIGINS=["https://<frontend-domain>"]`, nunca el default `*` en producción. Revise que las rutas de los modelos existan si se habilitan esas funciones.

**Diferencia entre plantilla y Compose:** `.env.example` también menciona `DB_SYNCHRONIZE` y `ENABLE_MAINTENANCE_ENDPOINTS`, pero `compose.yml` fija `DB_SYNCHRONIZE=false` y no pasa `ENABLE_MAINTENANCE_ENDPOINTS` al contenedor; editar esos dos valores en `runtime.env` no cambia el comportamiento del servicio actual. No habilite sincronización de esquema en producción. Compose pasa `AGE_CLASSIFIER_PROTOTXT_PATH` con el mismo nombre que espera la aplicación; una discrepancia previa en la clave destino impedía que el path configurado llegara a FastAPI.

## 3. Validaciones antes de lanzar

Estas comprobaciones son de consulta; no envían comandos ni cambian recursos:

```bash
aws sts get-caller-identity
aws ecr describe-repositories --region "$AWS_REGION" --repository-names "$AWS_ECR_REPOSITORY_BACKEND"
aws ssm describe-instance-information --region "$AWS_REGION" \
  --filters "Key=InstanceIds,Values=$AWS_EC2_INSTANCE_ID"
```

Confirme ECR/EC2 en la cuenta y región esperadas, y estado SSM `Online`. Antes del primer workflow, ejecute desde una sesión administrativa autorizada en EC2 una validación local que no contacta AWS ni levanta servicios:

```bash
sudo env IMAGE_TAG=preflight docker compose \
  --project-name experiencia-aws \
  --env-file /opt/experiencia-aws/runtime.env \
  --file /opt/experiencia-aws/compose.yml config --quiet
test -r /opt/experiencia-aws/secrets/cloud-sql-service-account.json
```

Si `CLOUD_SQL_CREDENTIALS_FILE` apunta a otra ruta, valide esa ruta en lugar de la predeterminada. `config --quiet` debe terminar con código 0; si faltan valores obligatorios de Compose, debe fallar antes de que una release se ejecute. No quite `--quiet`: el render completo podría revelar valores del archivo. Además valide `docker --version`, `docker compose version`, existencia de `runtime.env`, DNS de API, puertos y permisos de directorios. El comando de prueba de Cloud SQL debe usar el procedimiento aprobado por el DBA; no ejecute migraciones como prueba.

En GitHub, confirme: PR revisado e integrado; `main` con CI verde; variables configuradas; environment `aws-production` restringido a `main` con revisor; trust policy/policy IAM revisadas; runtime de EC2 listo; backup de Cloud SQL reciente y plan de migración aceptado. La existencia de estos recursos no puede verificarse desde el código.

## 4. Ejecutar y diagnosticar un deploy

Después de integrar y habilitar la configuración externa, abra **Actions → Deploy AWS (Backend) → Run workflow**, seleccione `main` y marque `confirm_deployment=true`. Un input falso/missing variable bloquea antes de OIDC. No reintente hasta clasificar la primera fase fallida.

El workflow crea reportes JSON/Markdown y artefacto de preflight por 14 días. Las fases se reportan por separado: `preparation`, `authentication`, `build`, `publication`, `deployment`, `remote_preparation`, `startup`, `readiness`, `postdeploy`. Los errores de configuración se identifican como `DEPLOY.CONFIG_NOT_CONFIGURED`/`DEPLOY.CONFIG_INVALID`; autenticación, push y SSM tienen códigos de etapa distintos. Las causas no confirmadas se marcan como hipótesis.

Para un fallo SSM, use el `CommandId` que imprime el paso de deploy y consulte solo esa instancia:

```bash
aws ssm get-command-invocation --region "$AWS_REGION" \
  --command-id "<COMMAND_ID>" --instance-id "$AWS_EC2_INSTANCE_ID"
```

No comparta stdout/stderr sin revisarlos: pueden contener detalles operativos. El preflight no llama a AWS y no incluye valores de variables en el reporte.

## 5. Smoke tests después del deploy

El script remoto verifica `/health/ready` (hasta 12 intentos, intervalo de 5 s) y el contrato de `GET /` desde dentro del contenedor backend antes de reportar éxito de SSM. Compose no publica el puerto 8000 al host, por lo que esos probes usan `docker compose exec` hacia `127.0.0.1:8000` dentro del contenedor. Después, desde un host con DNS público, compruebe el camino DNS/TLS/proxy completo sin imprimir body:

```bash
curl --fail --silent --show-error --max-time 15 \
  --output /dev/null --write-out 'HTTP %{http_code}\n' \
  "https://<AWS_API_HOST>/health/ready"
```

Debe responder 2xx. Luego verifique login/consulta API con una cuenta de prueba no productiva, origen CORS desde el dominio frontend y el flujo WebSocket autenticado con cliente de prueba si la versión usa esa funcionalidad. No use tokens de usuarios reales para smoke tests. `readiness` dentro de EC2 no reemplaza esta comprobación externa; no hay probe externo automático.

## 6. Recuperación y rollback

`deploy-ec2.sh` guarda el tag anterior en `previous-release.env`; al fallar una fase bajo su trap, restaura ese tag y vuelve a levantar `backend` y `cron-worker` si existe release anterior. En el primer deploy no hay rollback de aplicación. El workflow también guarda copias de `compose.yml` y helper previo, pero el script actual **no las restaura automáticamente ni verifica la salud del rollback**. Una migración Alembic ya aplicada tampoco se revierte automáticamente. Por eso el rollback de aplicación es parcial, no un rollback transaccional.

Procedimiento operativo ante fallo:

1. Detenga nuevos dispatches; capture URL/run ID, SHA, primer step fallido, reporte JSON, SSM CommandId y estado de servicios. Redacte secretos antes de compartir.
2. Si falló antes de SSM, no hubo deploy remoto; corrija configuración/build/IAM indicado por fase.
3. Si SSM falló, inspeccione la invocación; confirme si `deploy-ec2.sh` reportó rollback y ejecute el smoke externo antes de reintentar.
4. Si el rollback automático no dejó saludable la versión anterior, use Session Manager con operador autorizado. Verifique `previous-release.env`, `previous-compose.yml`, `previous-deploy-ec2.sh` y disponibilidad del tag ECR anterior antes de actuar. Con valores `AWS_REGION` y `ECR_REGISTRY` previamente confirmados desde runtime.env, el procedimiento manual es:

   ```bash
   sudo cp /opt/experiencia-aws/previous-compose.yml /opt/experiencia-aws/compose.yml
   sudo install -m 0750 /opt/experiencia-aws/bin/previous-deploy-ec2.sh /opt/experiencia-aws/bin/deploy-ec2.sh
   sudo cp /opt/experiencia-aws/previous-release.env /opt/experiencia-aws/release.env
   aws ecr get-login-password --region "$AWS_REGION" | \
     sudo docker login --username AWS --password-stdin "$ECR_REGISTRY"
   sudo env IMAGE_TAG=preflight docker compose --project-name experiencia-aws \
     --env-file /opt/experiencia-aws/runtime.env \
     --env-file /opt/experiencia-aws/release.env \
     --file /opt/experiencia-aws/compose.yml config --quiet
   sudo docker compose --project-name experiencia-aws \
     --env-file /opt/experiencia-aws/runtime.env \
     --env-file /opt/experiencia-aws/release.env \
     --file /opt/experiencia-aws/compose.yml pull backend
   sudo docker compose --project-name experiencia-aws \
     --env-file /opt/experiencia-aws/runtime.env \
     --env-file /opt/experiencia-aws/release.env \
     --file /opt/experiencia-aws/compose.yml up -d --remove-orphans reverse-proxy backend cron-worker
   ```

   Luego compruebe logs, `/health/ready` local y el smoke externo. Estos comandos cambian servicios y son únicamente para una recuperación aprobada; no los ejecute sin confirmar qué release/config se está restaurando.

5. Si la migración modificó esquema/datos, no revierta el contenedor a ciegas: consulte al responsable de base y restaure desde backup solo bajo su proceso de recuperación aprobado. Use migraciones expand/contract compatibles con la versión anterior.

El estado de backups de Cloud SQL, retención ECR y disponibilidad del release anterior no puede comprobarse en este repositorio y debe verificarse antes de habilitar producción.

## Qué tiene que proporcionar la persona operadora

- AWS account ID/region; nombre ECR y ARN del rol OIDC; ID de EC2; estado del OIDC provider, rol y políticas.
- Dominio/hostname de API y email ACME; proveedor DNS/IP estable y reglas de red.
- GitHub environment `aws-production`, branch rule `main`, aprobación y cuatro repository variables listadas.
- GCP project/region/instance Cloud SQL, cuenta con Cloud SQL Client, credencial runtime segura, DSN y backup/retención.
- Valores runtime privados de JWT y, si aplica, Stripe; URL frontend, CORS exacto y artefactos de modelos cuando la función esté habilitada.

## Archivos realmente versionados

- `compose.yml` — Traefik, Cloud SQL Proxy, FastAPI y cron worker.
- `deploy-ec2.sh` — release, migración, readiness y rollback de tag.
- `deploy-report.py`, `deploy_preflight.py` — contratos de diagnóstico y gate sin AWS.
- `deploy_workflow_report.py` — reporte por fase del workflow.
- `.env.example` y `secrets/.gitignore` — nombres de configuración/runtime; no contienen valores que deban copiarse como credenciales.

No existen `bootstrap-ec2.sh`, `check-cloud-sql.sh` ni `provision-aws-resources.sh` en esta rama. No ejecute pasos de documentación antigua que dependan de esos nombres.

## Referencias oficiales

- [GitHub: configurar OIDC con AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws), [claims OIDC](https://docs.github.com/en/actions/reference/security/oidc) y [environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).
- [AWS: permisos de push a ECR](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-push-iam.html), [permisos de Run Command/SSM](https://docs.aws.amazon.com/en_en/systems-manager/latest/userguide/run-command-setting-up.html) y [permisos de instancia administrada](https://docs.aws.amazon.com/systems-manager/latest/userguide/setup-instance-permissions.html).

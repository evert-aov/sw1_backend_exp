# Guía Operativa de Despliegue en EC2 (EXPERIENCIA)

Esta carpeta contiene los archivos de infraestructura y orquestación necesarios para ejecutar el backend, el proxy seguro de Google Cloud SQL, Traefik v3 y los cron workers en una instancia AWS EC2.

---

## 📁 Estructura de Archivos

| Archivo | Rol |
| :--- | :--- |
| `compose.yml` | Orquestación Docker Compose de producción (Traefik, Cloud SQL Proxy, FastAPI Backend y Cron Worker). |
| `bootstrap-ec2.sh` | Inicializa el árbol de directorios en `/opt/experiencia-aws`, permisos y copia de binarios. |
| `deploy-ec2.sh` | Ejecutado de forma automática por AWS SSM en cada release con rollback automático. |
| `check-cloud-sql.sh` | Validador de configuración y permisos del Cloud SQL Auth Proxy. |
| `provision-aws-resources.sh` | Aprovisiona los recursos base en AWS por CLI (con modo `--dry-run`). |
| `.env.example` | Plantilla de variables para `/opt/experiencia-aws/runtime.env`. |
| `secrets/.gitignore` | Protege el directorio de credenciales para no versionar secretos. |

---

## 🚀 Paso a Paso de Inicialización en EC2 (Fase 4)

### 1. Preparación del Sistema Operativo
En la instancia EC2 (Ubuntu 24.04 LTS):
```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 awscli
sudo usermod -aG docker ubuntu
```

### 2. Ejecutar Bootstrap
Copiar el contenido de `infra/aws/` a la instancia y ejecutar:
```bash
sudo ./bootstrap-ec2.sh
```
Esto creará el árbol seguro en `/opt/experiencia-aws/` (`bin/`, `secrets/`, `state/`, `models/`).

### 3. Configurar Credenciales y Entorno
1. Copiar la clave JSON de la Service Account de Google Cloud:
   ```bash
   sudo cp cloud-sql-service-account.json /opt/experiencia-aws/secrets/cloud-sql-service-account.json
   sudo chown 65532:65532 /opt/experiencia-aws/secrets/cloud-sql-service-account.json
   sudo chmod 0600 /opt/experiencia-aws/secrets/cloud-sql-service-account.json
   ```
2. Completar los valores de producción en `/opt/experiencia-aws/runtime.env`:
   ```bash
   sudo nano /opt/experiencia-aws/runtime.env
   sudo chmod 0600 /opt/experiencia-aws/runtime.env
   ```

### 4. Validar Conexión con Google Cloud SQL
Ejecutar el comprobador:
```bash
sudo /opt/experiencia-aws/bin/check-cloud-sql.sh
```
Levantar el conector para comprobar que el túnel mTLS con GCP se establece:
```bash
cd /opt/experiencia-aws
docker compose --env-file runtime.env up -d cloud-sql-proxy
docker compose logs cloud-sql-proxy
```
Debe indicar: `Ready for new connections`.

### 5. Aplicar la Primera Migración de Base de Datos
Aplicar la cadena versionada de Alembic hasta `head`:
```bash
docker compose --env-file runtime.env run --rm --no-deps backend python scripts/migrate_database.py
```

### 6. Otorgar Rol ADMIN a la Cuenta Propietaria
Tras registrar la cuenta inicial en la plataforma:
```bash
docker compose --env-file runtime.env run --rm --no-deps backend python scripts/grant_admin.py tu_correo@dominio.com
```

### 7. Levantar Todos los Servicios
```bash
docker compose --env-file runtime.env up -d
```
Verificar que la API responde localmente:
```bash
curl -I http://127.0.0.1:8000/
```
Traefik v3 gestionará de manera automática los certificados SSL con Let's Encrypt para `api.<dominio>`.

## Preflight de despliegue desde GitHub Actions

`Deploy AWS (Backend)` solo admite `workflow_dispatch` sobre `main`; no tiene trigger `workflow_run`, por lo que fusionar un PR o completar CI no inicia un despliegue. El dispatch requiere el input booleano `confirm_deployment=true`, cuyo valor predeterminado es `false`. `infra/aws/deploy_preflight.py` valida la revisión, los nombres de variables y esa confirmación antes de que el job de despliegue obtenga OIDC o ejecute comandos AWS. El preflight no llama a AWS. Si faltan variables, reporta `status: not_configured` y `gate_status: blocked`; si no se confirma la acción, reporta `DEPLOY.CONFIRMATION_REQUIRED`. En ambos casos el job con permisos AWS queda omitido. La publicación de una imagen no equivale a verificar el arranque ni la disponibilidad del servicio.

El preflight emite el contrato independiente `deployment-report/v1`, distinto del contrato de diagnóstico de la aplicación. Sus campos requeridos incluyen `project`, `revision`, `environment`, `phase`, `status`, `duration_ms`, `gate_status`, `code`, `cause_status`, `evidence`, `possible_causes` y `recommended_actions`. Los reportes describen únicamente evidencia observada; las causas no confirmadas se mantienen como hipótesis y no incluyen valores de configuración.

Configure estas **GitHub Actions repository variables** en el repositorio de destino autorizado para el despliegue, no como secretos ni en archivos versionados:

| Variable | Uso y formato validado |
| --- | --- |
| `AWS_DEPLOY_ROLE_ARN` | Rol asumido mediante OIDC; ARN `arn:aws:iam::<12 dígitos>:role/<nombre>`, sin espacios periféricos. |
| `AWS_REGION` | Región AWS, por ejemplo `us-west-2`, sin espacios periféricos. |
| `AWS_ECR_REPOSITORY_BACKEND` | Nombre/ruta de repositorio ECR en minúsculas, sin espacios periféricos. |
| `AWS_EC2_INSTANCE_ID` | ID de instancia, formato `i-` seguido por 8 o 17 caracteres hexadecimales, sin espacios periféricos. |

No se requieren claves estáticas `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`. La confianza del rol OIDC debe limitarse al repositorio de destino autorizado, al entorno `aws-production` y a `refs/heads/main`; revisar/configurar esa política, el entorno y sus aprobaciones es una tarea externa y no queda verificada por este repositorio. El preflight guarda JSON como artefacto de Actions y expone únicamente nombres de variables faltantes o inválidas, nunca sus valores.

Prueba local sin acceso cloud:

```bash
python infra/aws/deploy_preflight.py
```

Sin el contexto de evento y revisión de GitHub, la ejecución local se bloquea por trigger no permitido; en CI, un trigger autorizado pero con variables ausentes se marca como `not_configured`. Para comprobar ambos casos y el caso permitido use las pruebas aisladas `tests/test_deploy_preflight.py`, que solo usan entradas ficticias. No introduzca credenciales reales en una terminal compartida o en logs.

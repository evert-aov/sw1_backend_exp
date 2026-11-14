#!/usr/bin/env bash
set -euo pipefail

readonly PROJECT_DIR="${EXPERIENCIA_AWS_PROJECT_DIR:-/opt/experiencia-aws}"
readonly COMPOSE_FILE="${PROJECT_DIR}/compose.yml"
readonly RUNTIME_ENV_FILE="${EXPERIENCIA_AWS_RUNTIME_ENV_FILE:-${PROJECT_DIR}/runtime.env}"

if [[ $# -ne 1 || -z "$1" ]]; then
  echo "Uso: $0 <immutable-image-tag>" >&2
  exit 64
fi

readonly REPORT_HELPER="${PROJECT_DIR}/bin/deploy-report.py"
readonly IMAGE_TAG="$1"
if [[ ! "$IMAGE_TAG" =~ ^[A-Za-z0-9._-]{1,120}$ ]]; then
  if [[ -f "$REPORT_HELPER" ]]; then
    python3 "$REPORT_HELPER" <<'EOF'
{"service":"experiencia-backend","version":"unknown","phase":"preparation","status":"failed","code":"CONFIG.INVALID","cause_status":"confirmed","evidence":{"probe":"configuration","source":"ec2"}}
EOF
  fi
  echo "El tag de imagen no tiene un formato permitido." >&2
  exit 64
fi

readonly RELEASE_ENV_FILE="${PROJECT_DIR}/release.env"
readonly PREVIOUS_RELEASE_FILE="${PROJECT_DIR}/previous-release.env"

compose() {
  docker compose \
    --project-name experiencia-aws \
    --env-file "$RUNTIME_ENV_FILE" \
    --env-file "$RELEASE_ENV_FILE" \
    --file "$COMPOSE_FILE" "$@"
}

phase=preparation
failure_probe=preparation_operation
failure_cause_status=hypothesis

report() {
  local phase_name="$1" status="$2" probe="$3" attempt="${4:-0}" exit_code="${5:-0}" cause_status="${6:-unknown}" error_code="${7:-}"
  local code_json="null"
  if [[ -n "$error_code" ]]; then
    code_json="\"${error_code}\""
  fi
  python3 "$REPORT_HELPER" <<EOF
{"service":"experiencia-backend","version":"${IMAGE_TAG}","phase":"${phase_name}","status":"${status}","cause_status":"${cause_status}","code":${code_json},"evidence":{"probe":"${probe}","source":"ec2","attempt":${attempt},"exit_code":${exit_code}}}
EOF
}

rollback() {
  local failure_status=$?
  trap - ERR
  report "$phase" failed "$failure_probe" 0 "$failure_status" "$failure_cause_status" || true
  echo "Despliegue fallido. Ejecutando rollback..." >&2
  if [[ -f "$PREVIOUS_RELEASE_FILE" ]]; then
    cp "$PREVIOUS_RELEASE_FILE" "$RELEASE_ENV_FILE"
    compose up -d --remove-orphans backend cron-worker
    echo "Rollback completado al tag anterior: $(cat "$RELEASE_ENV_FILE")" >&2
  else
    echo "No existe release previo para rollback." >&2
  fi
  exit 1
}

trap rollback ERR

readonly ECR_REGISTRY="$(sed -n 's/^ECR_REGISTRY=//p' "$RUNTIME_ENV_FILE" | tail -n 1)"
readonly AWS_REGION="$(sed -n 's/^AWS_REGION=//p' "$RUNTIME_ENV_FILE" | tail -n 1)"
if [[ -z "$ECR_REGISTRY" || -z "$AWS_REGION" ]]; then
  report preparation failed configuration 0 1 confirmed CONFIG.MISSING || true
  echo "runtime.env debe definir los nombres de configuración ECR_REGISTRY y AWS_REGION." >&2
  exit 1
fi

if [[ -f "$RELEASE_ENV_FILE" ]]; then
  cp "$RELEASE_ENV_FILE" "$PREVIOUS_RELEASE_FILE"
fi
printf 'IMAGE_TAG=%s\n' "$IMAGE_TAG" > "$RELEASE_ENV_FILE"

echo "Autenticando contra AWS ECR..."
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$ECR_REGISTRY"

echo "Descargando imagen ${IMAGE_TAG}..."
compose pull backend

echo "Verificando servicio de Cloud SQL Auth Proxy..."
compose up -d cloud-sql-proxy

echo "Aplicando migraciones versionadas de Alembic..."
compose run --rm --no-deps backend python scripts/migrate_database.py
report preparation passed configuration

phase=startup
failure_probe=startup_operation
echo "Levantando servicios actualizados..."
compose up -d --remove-orphans reverse-proxy backend cron-worker
report startup passed compose_up

phase=readiness
failure_probe=readiness_operation
echo "Comprobando readiness local..."
for i in $(seq 1 12); do
  if curl -sS -f -o /dev/null http://127.0.0.1:8000/health/ready; then
    report readiness passed health_ready "$i"
    break
  fi
  if [[ "$i" -eq 12 ]]; then
    echo "Timeout esperando que FastAPI responda." >&2
    false
  fi
  sleep 5
done

phase=postdeploy
failure_probe=root_contract
echo "Comprobando contrato local postdeploy..."
if ! root_response="$(curl -sS -f --max-time 10 http://127.0.0.1:8000/)"; then
  failure_cause_status=hypothesis
  false
elif ! printf '%s' "$root_response" | python3 "$REPORT_HELPER" --validate-root-contract; then
  failure_cause_status=confirmed
  false
else
  report postdeploy passed root_contract
fi
unset root_response

echo "Despliegue de ${IMAGE_TAG} finalizado exitosamente."

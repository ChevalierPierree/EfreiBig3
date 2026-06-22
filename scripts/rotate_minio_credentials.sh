#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

TARGET="${1:-all}"
if [[ ! "${TARGET}" =~ ^(all|bronze|silver|gold)$ ]]; then
  echo "Usage: $0 [all|bronze|silver|gold]" >&2
  exit 1
fi

MINIO_SCHEME="${MINIO_SCHEME:-http}"
MINIO_ENDPOINT_HOST="${MINIO_ENDPOINT_HOST:-minio:9000}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-minio}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-minio123}"
MINIO_TLS_INSECURE="${MINIO_TLS_INSECURE:-false}"

if [[ "${MINIO_TLS_INSECURE}" == "true" ]]; then
  MC_INSECURE="--insecure"
else
  MC_INSECURE=""
fi

update_env_value() {
  local key="$1"
  local value="$2"

  if [[ ! -f "${ENV_FILE}" ]]; then
    touch "${ENV_FILE}"
  fi

  if grep -q "^${key}=" "${ENV_FILE}"; then
    sed -i.bak "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
  else
    printf "\n%s=%s\n" "${key}" "${value}" >> "${ENV_FILE}"
  fi
}

generate_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
  else
    date +%s | shasum -a 256 | awk '{print substr($1,1,48)}'
  fi
}

rotate_one() {
  local alias_name="$1"
  local access_var="$2"
  local secret_var="$3"
  local policy_name="$4"
  local default_access="$5"

  local access_key="${!access_var:-$default_access}"
  local secret_key
  secret_key="$(generate_secret)"

  docker compose exec -T minio /bin/sh -c \
    "set -e; mc ${MC_INSECURE} alias set ${alias_name} ${MINIO_SCHEME}://${MINIO_ENDPOINT_HOST} ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD} >/dev/null; \
     mc ${MC_INSECURE} admin user add ${alias_name} ${access_key} ${secret_key} >/dev/null; \
     mc ${MC_INSECURE} admin policy attach ${alias_name} ${policy_name} --user ${access_key} >/dev/null"

  update_env_value "${access_var}" "${access_key}"
  update_env_value "${secret_var}" "${secret_key}"
  echo "Rotation OK: ${access_var}/${secret_var} (policy=${policy_name})"
}

if [[ "${TARGET}" == "all" || "${TARGET}" == "bronze" ]]; then
  rotate_one "local" "MINIO_BRONZE_WRITER_ACCESS_KEY" "MINIO_BRONZE_WRITER_SECRET_KEY" "bronze-writer" "bronze-writer"
fi

if [[ "${TARGET}" == "all" || "${TARGET}" == "silver" ]]; then
  rotate_one "local" "MINIO_SILVER_READER_ACCESS_KEY" "MINIO_SILVER_READER_SECRET_KEY" "silver-reader" "silver-reader"
fi

if [[ "${TARGET}" == "all" || "${TARGET}" == "gold" ]]; then
  rotate_one "local" "MINIO_GOLD_READER_ACCESS_KEY" "MINIO_GOLD_READER_SECRET_KEY" "gold-reader" "gold-reader"
fi

if [[ -f "${ENV_FILE}.bak" ]]; then
  rm -f "${ENV_FILE}.bak"
fi

echo "Fichier mis à jour: ${ENV_FILE}"

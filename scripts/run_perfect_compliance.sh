#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
LOG_DIR="${ROOT_DIR}/logs"
API_PID_FILE="${LOG_DIR}/fraud_dashboard_api.pid"
LOCAL_API_PID=""

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "ERREUR: python virtuel introuvable: ${PYTHON_BIN}" >&2
  exit 1
fi

RUN_FAILOVER="${RUN_FAILOVER:-false}"

wait_url() {
  local url="$1"
  local attempts="${2:-30}"
  local i=1
  while [ "$i" -le "$attempts" ]; do
    if curl -fsS -m 5 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  return 1
}

ensure_api_up() {
  mkdir -p "${LOG_DIR}"
  if wait_url "http://localhost:8000/health" 3; then
    echo "API          : already up"
    return 0
  fi

  echo "API          : démarrage..."
  "${PYTHON_BIN}" "${ROOT_DIR}/api/fraud_dashboard_api.py" > "${LOG_DIR}/fraud_dashboard_api.log" 2>&1 &
  LOCAL_API_PID=$!
  echo "${LOCAL_API_PID}" > "${API_PID_FILE}"

  if wait_url "http://localhost:8000/health" 30; then
    echo "API          : started"
    return 0
  fi

  echo "ERREUR: API non disponible sur http://localhost:8000/health" >&2
  return 1
}

cleanup() {
  if [[ -n "${LOCAL_API_PID}" ]] && kill -0 "${LOCAL_API_PID}" >/dev/null 2>&1; then
    kill "${LOCAL_API_PID}" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

echo "=== RUN PERFECT COMPLIANCE ==="
echo "Root         : ${ROOT_DIR}"
echo "Python       : ${PYTHON_BIN}"
echo "Run failover : ${RUN_FAILOVER}"
echo

ensure_api_up
echo

echo "[1/10] RBAC + quotas API"
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/test_api_rbac_rate_limit.py"

echo "[2/10] Génération cert TLS MinIO"
bash "${ROOT_DIR}/scripts/generate_minio_tls_certs.sh"

echo "[3/10] Snapshot Data Lake (compte bronze-writer)"
bash "${ROOT_DIR}/scripts/snapshot_raw_data_to_minio.sh"

echo "[4/10] Promotion bronze -> silver -> gold"
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/promote_data_lake_layers.py"

echo "[5/10] Warehouse analytics + datamarts"
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/build_analytics_warehouse.py"

echo "[6/10] Flux micro-batch (1 fenêtre)"
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/micro_batch_events_to_postgres.py" --run-once --window-seconds 30

echo "[7/10] Tests charge DB"
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/test_db_load.py" --pg-requests 120 --mongo-requests 120 --concurrency 12

echo "[8/10] Tests résilience"
if [[ "${RUN_FAILOVER}" == "true" ]]; then
  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/test_resilience_failover.py" --service postgres
else
  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/test_resilience_failover.py" --service postgres --dry-run
fi

echo "[9/10] Validation sujet 1"
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/validate_sujet1.py"

echo "[10/10] Validation conformité parfaite"
if [[ "${RUN_FAILOVER}" == "true" ]]; then
  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/validate_perfect_compliance.py" --run-failover
else
  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/validate_perfect_compliance.py"
fi

echo
echo "Terminé. Rapports:"
echo " - logs/sujet1_validation_report.json"
echo " - logs/perfect_compliance_report.json"
echo " - logs/api_rbac_rate_limit_report.json"
echo " - logs/db_load_test_report.json"
echo " - logs/resilience_failover_report.json"
echo " - logs/transfer_kpi_history.jsonl"
echo " - logs/data_lake_promotion_*.json"
echo " - logs/analytics_warehouse_report.json"

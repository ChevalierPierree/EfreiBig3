#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-${ROOT_DIR}/delivery_pack}"

DOCS=(
  README.md
  INSTALLATION.md
  QUICKSTART.md
  DEMO_PROJET.md
  SUJET1_CHECKLIST.md
  SOMMAIRE_MEMOIRE_TECHNIQUE.md
  AUDIT_CONSIGNE_INITIALE.md
  AUDIT_RENDU_PROJET.md
  AUDIT_FONCTIONNEL_FINAL.md
  AUDIT_ARCHITECTURE_DATA.md
  AUDIT_RNCP40875_BLOC1.md
  RNCP_BLOC1_TRACEABILITE.md
  ARCHITECTURE_DECISIONS.md
  GOUVERNANCE_ET_PARTIES_PRENANTES.md
  VEILLE_TECHNOLOGIQUE_BLOC1.md
  PACK_RENDU.md
  PATATOR_GUIDE.md
)

PROOFS=(
  logs/sujet1_validation_report.json
  logs/perfect_compliance_report.json
  logs/data_quality_report.json
  logs/api_rbac_rate_limit_report.json
  logs/db_load_test_report.json
  logs/resilience_failover_report.json
  logs/analytics_warehouse_report.json
  logs/data_platform_pipeline_report.json
  logs/id_card_model_report.json
  logs/transfer_kpi_history.jsonl
)

APP_ITEMS=(
  docker-compose.yml
  .env.example
  requirements.txt
  requirements-minimal.txt
  requirements.patator.txt
  patator
  api
  config
  dashboard
  database
  flink
  kivendtout_dataset
  models
  monitoring
  scripts
)

require_path() {
  local path="$1"
  if [[ ! -e "${ROOT_DIR}/${path}" ]]; then
    echo "ERREUR: element manquant: ${path}" >&2
    exit 1
  fi
}

echo "=== BUILD DELIVERY PACK ==="
echo "Source : ${ROOT_DIR}"
echo "Output : ${OUT_DIR}"

for doc in "${DOCS[@]}"; do
  require_path "$doc"
done
for item in "${APP_ITEMS[@]}"; do
  require_path "$item"
done

rm -rf "${OUT_DIR}"
mkdir -p "${OUT_DIR}/docs" "${OUT_DIR}/proofs" "${OUT_DIR}/app"

for doc in "${DOCS[@]}"; do
  cp "${ROOT_DIR}/${doc}" "${OUT_DIR}/docs/"
done
cp "${ROOT_DIR}/PACK_RENDU.md" "${OUT_DIR}/README_PACK.md"

for proof in "${PROOFS[@]}"; do
  if [[ -f "${ROOT_DIR}/${proof}" ]]; then
    cp "${ROOT_DIR}/${proof}" "${OUT_DIR}/proofs/"
  fi
done

while IFS= read -r snapshot; do
  [[ -n "${snapshot}" ]] || continue
  cp "${snapshot}" "${OUT_DIR}/proofs/"
done < <(ls -1t "${ROOT_DIR}"/logs/data_lake_snapshot_*.json 2>/dev/null | head -n 3)

for item in "${APP_ITEMS[@]}"; do
  cp -R "${ROOT_DIR}/${item}" "${OUT_DIR}/app/"
done

mkdir -p "${OUT_DIR}/app/security/minio"
cp -R "${ROOT_DIR}/security/minio/policies" "${OUT_DIR}/app/security/minio/"

find "${OUT_DIR}" -name '.DS_Store' -delete
find "${OUT_DIR}" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "${OUT_DIR}" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
rm -rf "${OUT_DIR}/app/data/external" 2>/dev/null || true
rm -rf "${OUT_DIR}/app/delivery_pack" 2>/dev/null || true
rm -rf "${OUT_DIR}/app/logs/alert_email_preview" 2>/dev/null || true
rm -f "${OUT_DIR}/app/logs/alert_notification_history.jsonl" 2>/dev/null || true
rm -f "${OUT_DIR}/app/logs/use_case_history.jsonl" 2>/dev/null || true
rm -f "${OUT_DIR}/app/logs/"*.log "${OUT_DIR}/app/logs/"*.pid 2>/dev/null || true
rm -f "${OUT_DIR}/app/security/minio/certs/"* 2>/dev/null || true
rm -rf "${OUT_DIR}/app/security/minio/certs" 2>/dev/null || true

(
  cd "${OUT_DIR}"
  {
    find docs -type f | sort
    find proofs -type f | sort
    find app -type f | sort
  } > MANIFEST.txt
  shasum -a 256 README_PACK.md MANIFEST.txt docs/* proofs/* >/dev/null 2>&1 && \
    shasum -a 256 README_PACK.md MANIFEST.txt docs/* proofs/* > SHA256SUMS.txt || true
)

echo "Pack de livraison genere dans ${OUT_DIR}"

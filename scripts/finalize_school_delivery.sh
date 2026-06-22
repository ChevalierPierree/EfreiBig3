#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "ERREUR: python virtuel introuvable: ${PYTHON_BIN}" >&2
  exit 1
fi

echo "=== FINALIZE SCHOOL DELIVERY ==="
echo "Root   : ${ROOT_DIR}"
echo "Python : ${PYTHON_BIN}"
echo

echo "[1/5] Checklist plateforme"
bash "${ROOT_DIR}/scripts/checklist_and_launch.sh"

echo
echo "[2/5] Validation complete"
bash "${ROOT_DIR}/scripts/run_perfect_compliance.sh"

echo
echo "[3/5] Pipeline data consolide"
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/run_data_platform_pipeline.py"

echo
echo "[4/5] Nettoyage artefacts"
bash "${ROOT_DIR}/scripts/clean_project_artifacts.sh"

echo
echo "[5/5] Generation du pack"
bash "${ROOT_DIR}/scripts/build_delivery_pack.sh"

echo
echo "Projet pret a rendre."
echo "Pack          : ${ROOT_DIR}/delivery_pack"
echo "Rapports clefs:"
echo " - logs/sujet1_validation_report.json"
echo " - logs/perfect_compliance_report.json"
echo " - logs/data_quality_report.json"
echo " - logs/analytics_warehouse_report.json"
echo " - logs/data_platform_pipeline_report.json"

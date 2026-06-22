#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
API_URL="${API_URL:-http://localhost:8000}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "ERREUR: python virtuel introuvable: ${PYTHON_BIN}" >&2
  exit 1
fi

bash "${PROJECT_DIR}/scripts/checklist_and_launch.sh" >/tmp/checklist_use_cases.txt

curl -sS "${API_URL}/api/use-cases?limit_history=8" >/tmp/use_cases_index.json

for key in minor-adult-checkout adult-adult-checkout identity-verification high-risk-alert; do
  curl -sS -X POST "${API_URL}/api/use-cases/${key}/run" >/tmp/use_case_${key}.json
done

"${PYTHON_BIN}" - <<'PY'
import json
from pathlib import Path

keys = [
    "minor-adult-checkout",
    "adult-adult-checkout",
    "identity-verification",
    "high-risk-alert",
]
expected_available = set(keys + ["massive-fraud-orders-episode"])

index_payload = json.load(open("/tmp/use_cases_index.json"))
available = {item.get("key") for item in (index_payload.get("items") or [])}
print("=== USE CASE TESTS ===")
print(f"available={len(index_payload.get('items') or [])}")
print(f"notification_mode={index_payload.get('notification_mode')}")
print(f"expected_available={expected_available.issubset(available)}")

all_passed = True
for key in keys:
    payload = json.load(open(f"/tmp/use_case_{key}.json"))
    passed = bool(payload.get("passed"))
    all_passed = all_passed and passed
    print(f"{key}: passed={passed} outcome={payload.get('outcome')} http={payload.get('http_status')}")
    resources = payload.get("resources") or {}
    if resources.get("id_card", {}).get("file"):
        print(f"  id_card={resources['id_card']['file']} age={resources['id_card'].get('age')}")
    if resources.get("product", {}).get("name"):
        print(f"  product={resources['product']['name']} stock={resources['product'].get('stock_quantity')}")
    if resources.get("alert_id"):
        print(f"  alert_id={resources['alert_id']}")

print(f"all_passed={all_passed}")
PY

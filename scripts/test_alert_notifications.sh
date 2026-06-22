#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
EMAIL="${1:-ops@kivendtout.fr}"
API_URL="${API_URL:-http://localhost:8000}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "ERREUR: python virtuel introuvable: ${PYTHON_BIN}" >&2
  exit 1
fi

bash "${PROJECT_DIR}/scripts/checklist_and_launch.sh" >/tmp/checklist_notifications.txt

cat >/tmp/notif_config.json <<JSON
{"enabled":true,"recipient_email":"${EMAIL}","min_severity":"HIGH","notify_on_new_alert":true,"notify_on_decision":true,"updated_by":"${EMAIL}"}
JSON

curl -sS -X PUT "${API_URL}/api/alert-notifications/config" \
  -H "Content-Type: application/json" \
  --data @/tmp/notif_config.json \
  >/tmp/notif_config_response.json

cat >/tmp/notif_alert.json <<JSON
{"severity":"HIGH","risk_score":92,"status":"PENDING_REVIEW","fraud_reasons":["VELOCITY_HIGH","NEW_DEVICE"],"customer_id":"C00999","customer_country":"FR","device":"desktop"}
JSON

curl -sS -X POST "${API_URL}/api/alerts/simulate" \
  -H "Content-Type: application/json" \
  --data @/tmp/notif_alert.json \
  >/tmp/notif_alert_response.json

ALERT_ID="$("${PYTHON_BIN}" -c "import json; print(json.load(open('/tmp/notif_alert_response.json'))['alert_id'])")"

cat >/tmp/notif_manual.json <<JSON
{"recipient_email":"${EMAIL}","message":"Escalade manuelle de validation","updated_by":"${EMAIL}"}
JSON

curl -sS -X POST "${API_URL}/api/alerts/${ALERT_ID}/notify" \
  -H "Content-Type: application/json" \
  --data @/tmp/notif_manual.json \
  >/tmp/notif_manual_response.json

cat >/tmp/notif_decision.json <<JSON
{"decision":"INVESTIGATE","decided_by":"${EMAIL}","notes":"Escalade automatique pour revue analyste"}
JSON

curl -sS -X POST "${API_URL}/api/alerts/${ALERT_ID}/decide" \
  -H "Content-Type: application/json" \
  --data @/tmp/notif_decision.json \
  >/tmp/notif_decision_response.json

curl -sS "${API_URL}/api/alert-notifications/history?limit=6" >/tmp/notif_history_response.json

"${PYTHON_BIN}" - <<'PY'
import json

cfg = json.load(open('/tmp/notif_config_response.json'))
alert = json.load(open('/tmp/notif_alert_response.json'))
manual = json.load(open('/tmp/notif_manual_response.json'))
decision = json.load(open('/tmp/notif_decision_response.json'))
history = json.load(open('/tmp/notif_history_response.json'))

print("=== ALERT NOTIFICATION TEST ===")
print(f"delivery_mode={cfg.get('delivery_mode')}")
print(f"alert_id={alert.get('alert_id')}")
print(f"alert_severity={alert.get('severity')}")
print(f"manual_notify_status={manual.get('status')}")
print(f"manual_notify_mode={manual.get('delivery_mode')}")
print(f"decision_status={decision.get('decision')}")
print(f"history_count={history.get('count')}")

items = history.get('items') or []
for idx, item in enumerate(items[:4], start=1):
    print(f"history_{idx}_event={item.get('event_type')}")
    print(f"history_{idx}_status={item.get('status')}")
    print(f"history_{idx}_mode={item.get('delivery_mode')}")
    print(f"history_{idx}_alert={item.get('alert_id')}")
    print(f"history_{idx}_preview={item.get('preview_file')}")
PY

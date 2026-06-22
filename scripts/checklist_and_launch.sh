#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
API_PORT=8000
DASHBOARD_PORT=7600

CHECKS_TOTAL=0
CHECKS_OK=0
CHECKS_KO=0

print_ok() {
  echo "✅ $1"
  CHECKS_OK=$((CHECKS_OK + 1))
}

print_ko() {
  echo "❌ $1"
  CHECKS_KO=$((CHECKS_KO + 1))
}

run_check() {
  CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
  if eval "$2" >/dev/null 2>&1; then
    print_ok "$1"
    return 0
  else
    print_ko "$1"
    return 1
  fi
}

select_python_bin() {
  if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
    echo "$VIRTUAL_ENV/bin/python"
    return
  fi
  if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
    echo "$PROJECT_DIR/.venv/bin/python"
    return
  fi
  echo "python3"
}

wait_url() {
  local url="$1"
  local attempts="${2:-20}"
  local i=1
  while [ "$i" -le "$attempts" ]; do
    if curl -fsS -m 3 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  return 1
}

wait_compose_service() {
  local service="$1"
  local attempts="${2:-20}"
  local i=1
  while [ "$i" -le "$attempts" ]; do
    if (cd "$PROJECT_DIR" && docker compose ps --status running "$service" | grep -q "$service") >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  return 1
}

start_api_if_needed() {
  local python_bin="$1"
  local api_pid_file="$LOG_DIR/fraud_dashboard_api.pid"
  if wait_url "http://localhost:${API_PORT}/health" 2; then
    print_ok "API active sur ${API_PORT}"
    return 0
  fi

  echo "ℹ️ API inactive, démarrage..."
  nohup "$python_bin" "$PROJECT_DIR/api/fraud_dashboard_api.py" > "$LOG_DIR/fraud_dashboard_api.log" 2>&1 < /dev/null &
  echo $! > "$api_pid_file"
  if wait_url "http://localhost:${API_PORT}/health" 30; then
    print_ok "API démarrée sur ${API_PORT}"
    return 0
  fi
  print_ko "API non disponible après démarrage"
  return 1
}

start_dashboard_if_needed() {
  local python_bin="$1"
  local dashboard_pid_file="$LOG_DIR/http_server.pid"
  if wait_url "http://localhost:${DASHBOARD_PORT}/index.html" 2; then
    print_ok "Dashboard web actif sur ${DASHBOARD_PORT}"
    return 0
  fi

  echo "ℹ️ Dashboard inactif, démarrage..."
  (
    cd "$PROJECT_DIR/dashboard"
    nohup "$python_bin" -m http.server "$DASHBOARD_PORT" > "$LOG_DIR/http_server.log" 2>&1 < /dev/null &
    echo $! > "$dashboard_pid_file"
  )

  if wait_url "http://localhost:${DASHBOARD_PORT}/index.html" 20; then
    print_ok "Dashboard web démarré sur ${DASHBOARD_PORT}"
    return 0
  fi
  print_ko "Dashboard non disponible après démarrage"
  return 1
}

main() {
  local python_bin
  python_bin="$(select_python_bin)"

  mkdir -p "$LOG_DIR"
  touch "$LOG_DIR/runtime_refresh.log"

  echo "=== CHECKLIST BLOC 1 + DASHBOARDS ==="
  echo "Projet: $PROJECT_DIR"
  echo "Python: $python_bin"
  echo

  run_check "docker installé" "command -v docker"
  run_check "docker compose installé" "docker compose version"
  run_check "python disponible" "command -v \"$python_bin\""
  run_check "curl disponible" "command -v curl"
  run_check "Docker daemon actif" "docker info"

  if ! run_check "docker compose accessible" "cd \"$PROJECT_DIR\" && docker compose ps"; then
    local total_now
    total_now=$((CHECKS_OK + CHECKS_KO))
    echo
    echo "Résumé: $CHECKS_OK/$total_now checks OK, $CHECKS_KO KO"
    echo "Action: démarre Docker Desktop puis relance ce script."
    exit 1
  fi

  run_check "Service postgres up" "wait_compose_service postgres 15"
  run_check "Service mongodb up" "wait_compose_service mongodb 10"
  run_check "Service kafka-1 up" "wait_compose_service kafka-1 10"

  start_api_if_needed "$python_bin"
  start_dashboard_if_needed "$python_bin"

  run_check "Page index dashboard accessible" "curl -fsS -m 5 http://localhost:${DASHBOARD_PORT}/index.html"
  run_check "Page fraude globale accessible" "curl -fsS -m 5 http://localhost:${DASHBOARD_PORT}/fraud_dashboard.html"
  run_check "Page types fraude accessible" "curl -fsS -m 5 http://localhost:${DASHBOARD_PORT}/fraud_types_dashboard.html"
  run_check "Page ID cards accessible" "curl -fsS -m 5 http://localhost:${DASHBOARD_PORT}/id_cards_dashboard.html"
  run_check "Page KPI transfert accessible" "curl -fsS -m 5 http://localhost:${DASHBOARD_PORT}/transfer_kpi_dashboard.html"
  run_check "API /health accessible" "curl -fsS -m 5 http://localhost:${API_PORT}/health"
  run_check "API /stats accessible" "curl -fsS -m 5 http://localhost:${API_PORT}/api/stats"
  run_check "API /checkout/stats accessible" "curl -fsS -m 5 \"http://localhost:${API_PORT}/api/checkout/stats?window_hours=24\""
  run_check "API /payments/stats accessible" "curl -fsS -m 5 \"http://localhost:${API_PORT}/api/payments/stats?window_hours=24\""
  run_check "API /micro-batch/stats accessible" "curl -fsS -m 5 \"http://localhost:${API_PORT}/api/micro-batch/stats?window_hours=24\""
  run_check "API /transfer/kpis accessible" "curl -fsS -m 5 \"http://localhost:${API_PORT}/api/transfer/kpis?limit=20\""
  run_check "API /data-lake/status accessible" "curl -fsS -m 5 \"http://localhost:${API_PORT}/api/data-lake/status\""
  run_check "API /data-platform/status accessible" "curl -fsS -m 5 \"http://localhost:${API_PORT}/api/data-platform/status\""
  run_check "API /analytics/status accessible" "curl -fsS -m 5 \"http://localhost:${API_PORT}/api/analytics/status\""
  run_check "API /kpis/readable accessible" "curl -fsS -m 5 \"http://localhost:${API_PORT}/api/kpis/readable?limit=20&micro_batch_window_hours=24\""
  run_check "API /live/state accessible" "curl -fsS -m 5 \"http://localhost:${API_PORT}/api/live/state\""

  echo
  echo "=== RÉSUMÉ ==="
  local total_final
  total_final=$((CHECKS_OK + CHECKS_KO))
  echo "Checks OK: $CHECKS_OK/$total_final"
  echo "Checks KO: $CHECKS_KO"
  echo
  echo "URLs:"
  echo "- Hub:       http://localhost:${DASHBOARD_PORT}/index.html"
  echo "- Fraude:    http://localhost:${DASHBOARD_PORT}/fraud_dashboard.html"
  echo "- Types:     http://localhost:${DASHBOARD_PORT}/fraud_types_dashboard.html"
  echo "- ID Cards:  http://localhost:${DASHBOARD_PORT}/id_cards_dashboard.html"
  echo "- KPI Xfer:  http://localhost:${DASHBOARD_PORT}/transfer_kpi_dashboard.html"
  echo "- API Health:http://localhost:${API_PORT}/health"
  echo
  echo "Commandes:"
  echo "- Micro-batch: bash scripts/run_micro_batch.sh once"
  echo "- Pack de livraison:   bash scripts/build_delivery_pack.sh"
  echo
  echo "Logs:"
  echo "- API:       tail -f $LOG_DIR/fraud_dashboard_api.log"
  echo "- Dashboard: tail -f $LOG_DIR/http_server.log"
  echo "- Runtime:   tail -f $LOG_DIR/runtime_refresh.log"

  if [ "$CHECKS_KO" -gt 0 ]; then
    exit 1
  fi
}

main "$@"

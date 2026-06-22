#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "ERREUR: python virtuel introuvable: ${PYTHON_BIN}" >&2
  exit 1
fi

MODE="${1:-once}"
if [[ -n "${WINDOW_SECONDS:-}" ]]; then
  WINDOW_SECONDS="${WINDOW_SECONDS}"
elif [[ "${MODE}" == "once" ]]; then
  WINDOW_SECONDS="300"
else
  WINDOW_SECONDS="30"
fi
BOOTSTRAP_MINUTES="${BOOTSTRAP_MINUTES:-10}"
POLL_INTERVAL="${POLL_INTERVAL:-1}"
DURATION_SECONDS="${DURATION_SECONDS:-120}"
if [[ -n "${MICRO_BATCH_ANCHOR_MODE:-}" ]]; then
  ANCHOR_MODE="${MICRO_BATCH_ANCHOR_MODE}"
elif [[ "${MODE}" == "once" ]]; then
  ANCHOR_MODE="latest-data"
else
  ANCHOR_MODE="auto"
fi

ARGS=(
  "${ROOT_DIR}/scripts/micro_batch_events_to_postgres.py"
  "--window-seconds" "${WINDOW_SECONDS}"
  "--bootstrap-minutes" "${BOOTSTRAP_MINUTES}"
  "--poll-interval" "${POLL_INTERVAL}"
  "--anchor-mode" "${ANCHOR_MODE}"
)

case "${MODE}" in
  once)
    ARGS+=("--run-once")
    ;;
  live)
    ARGS+=("--duration-seconds" "${DURATION_SECONDS}")
    ;;
  daemon)
    ;;
  *)
    echo "Usage: bash scripts/run_micro_batch.sh [once|live|daemon]" >&2
    echo "  once   : exécute une seule fenêtre" >&2
    echo "  live   : exécute pendant DURATION_SECONDS" >&2
    echo "  daemon : boucle sans limite" >&2
    exit 1
    ;;
esac

echo "=== RUN MICRO-BATCH ==="
echo "Mode              : ${MODE}"
echo "Window seconds    : ${WINDOW_SECONDS}"
echo "Bootstrap minutes : ${BOOTSTRAP_MINUTES}"
echo "Poll interval     : ${POLL_INTERVAL}"
echo "Anchor mode       : ${ANCHOR_MODE}"
if [[ "${MODE}" == "live" ]]; then
  echo "Duration seconds  : ${DURATION_SECONDS}"
fi
echo

exec "${PYTHON_BIN}" "${ARGS[@]}"

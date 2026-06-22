#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEEP_SNAPSHOTS="${KEEP_SNAPSHOTS:-5}"
KEEP_PROMOTION_REPORTS="${KEEP_PROMOTION_REPORTS:-5}"

removed_count=0

remove_path() {
  local target="$1"
  if [[ -e "$target" ]]; then
    rm -rf "$target"
    echo "removed: ${target#${ROOT_DIR}/}"
    removed_count=$((removed_count + 1))
  fi
}

echo "=== CLEAN PROJECT ARTIFACTS ==="
echo "root            : $ROOT_DIR"
echo "keep_snapshots  : $KEEP_SNAPSHOTS"

# Python caches from source tree (exclude virtualenvs on purpose).
while IFS= read -r -d '' cache_dir; do
  remove_path "$cache_dir"
done < <(find "$ROOT_DIR/api" "$ROOT_DIR/scripts" -type d -name "__pycache__" -print0 2>/dev/null || true)

while IFS= read -r -d '' pyc_file; do
  remove_path "$pyc_file"
done < <(find "$ROOT_DIR/api" "$ROOT_DIR/scripts" -type f \( -name "*.pyc" -o -name "*.pyo" \) -print0 2>/dev/null || true)

# Temporary office lock files at repository root.
while IFS= read -r -d '' lock_file; do
  remove_path "$lock_file"
done < <(find "$ROOT_DIR" -maxdepth 1 -type f -name '~$*.xlsx' -print0 2>/dev/null || true)

# Runtime logs/pids.
while IFS= read -r -d '' runtime_file; do
  remove_path "$runtime_file"
done < <(find "$ROOT_DIR/logs" -maxdepth 1 -type f \( -name "*.log" -o -name "*.pid" \) -print0 2>/dev/null || true)

# Runtime histories and previews.
remove_path "$ROOT_DIR/logs/alert_notification_history.jsonl"
remove_path "$ROOT_DIR/logs/use_case_history.jsonl"
remove_path "$ROOT_DIR/logs/data_factory_history.jsonl"
remove_path "$ROOT_DIR/logs/presentation_test_history.jsonl"
remove_path "$ROOT_DIR/logs/alert_email_preview"
remove_path "$ROOT_DIR/logs/micro_batch_state.json"
remove_path "$ROOT_DIR/data/external"

# Finder-style duplicate files/folders created during copies.
while IFS= read -r -d '' duplicate_path; do
  remove_path "$duplicate_path"
done < <(find "$ROOT_DIR/logs" "$ROOT_DIR/delivery_pack" -maxdepth 1 \
  \( -name '* [2-9].jsonl' -o -name '* [2-9].log' -o -name '* [2-9].txt' -o -name '* [2-9].md' -o -name '* [2-9]' \) \
  -print0 2>/dev/null || true)

# Keep only the newest N data lake snapshots.
snapshots=()
while IFS= read -r snapshot_path; do
  [[ -n "$snapshot_path" ]] || continue
  snapshots+=("$snapshot_path")
done < <(ls -1t "$ROOT_DIR"/logs/data_lake_snapshot_*.json 2>/dev/null || true)
if (( ${#snapshots[@]} > KEEP_SNAPSHOTS )); then
  for snapshot_path in "${snapshots[@]:KEEP_SNAPSHOTS}"; do
    remove_path "$snapshot_path"
  done
fi

# Keep only the newest N data lake promotion reports.
promotion_reports=()
while IFS= read -r report_path; do
  [[ -n "$report_path" ]] || continue
  promotion_reports+=("$report_path")
done < <(ls -1t "$ROOT_DIR"/logs/data_lake_promotion_*.json 2>/dev/null || true)
if (( ${#promotion_reports[@]} > KEEP_PROMOTION_REPORTS )); then
  for report_path in "${promotion_reports[@]:KEEP_PROMOTION_REPORTS}"; do
    remove_path "$report_path"
  done
fi

echo "done: removed_items=$removed_count"

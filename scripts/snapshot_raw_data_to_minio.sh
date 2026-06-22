#!/usr/bin/env bash

set -euo pipefail
export LC_ALL=C
export LANG=C

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATASET_DIR="${ROOT_DIR}/kivendtout_dataset"
TIMESTAMP_UTC="$(date -u +"%Y%m%dT%H%M%SZ")"
SNAPSHOT_PREFIX="bronze/raw_snapshot/${TIMESTAMP_UTC}"
LOG_DIR="${ROOT_DIR}/logs"
MANIFEST_TSV="$(mktemp)"
MANIFEST_JSON="${LOG_DIR}/data_lake_snapshot_${TIMESTAMP_UTC}.json"
TRANSFER_KPI_HISTORY="${LOG_DIR}/transfer_kpi_history.jsonl"
START_EPOCH="$(date +%s)"

MINIO_ENDPOINT="${MINIO_ENDPOINT:-localhost:9000}"
MINIO_SCHEME="${MINIO_SCHEME:-}"
if [[ -z "${MINIO_SCHEME}" ]]; then
  if [[ -f "${ROOT_DIR}/security/minio/certs/public.crt" ]]; then
    MINIO_SCHEME="https"
  else
    MINIO_SCHEME="http"
  fi
fi
MINIO_TLS_INSECURE="${MINIO_TLS_INSECURE:-}"
if [[ -z "${MINIO_TLS_INSECURE}" ]]; then
  if [[ "${MINIO_SCHEME}" == "https" ]]; then
    MINIO_TLS_INSECURE="true"
  else
    MINIO_TLS_INSECURE="false"
  fi
fi
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-${MINIO_BRONZE_WRITER_ACCESS_KEY:-bronze-writer}}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-${MINIO_BRONZE_WRITER_SECRET_KEY:-bronze-writer-change-me}}"

if [[ "${MINIO_ENDPOINT}" =~ ^https?:// ]]; then
  MINIO_TARGET="${MINIO_ENDPOINT}"
else
  MINIO_TARGET="${MINIO_SCHEME}://${MINIO_ENDPOINT}"
fi

if [[ "${MINIO_TLS_INSECURE}" == "true" ]]; then
  MC_INSECURE="--insecure"
else
  MC_INSECURE=""
fi
ACTIVE_MINIO_TARGET="${MINIO_TARGET}"
ACTIVE_MC_INSECURE="${MC_INSECURE}"

build_fallback_target() {
  local target="$1"
  if [[ "${target}" =~ ^http:// ]]; then
    echo "${target/http:\/\//https://}"
    return 0
  fi
  if [[ "${target}" =~ ^https:// ]]; then
    echo "${target/https:\/\//http://}"
    return 0
  fi
  echo "${target}"
}

ensure_minio_alias() {
  if docker compose exec -T minio /bin/sh -c \
    "set -e; export LC_ALL=C LANG=C; mc ${ACTIVE_MC_INSECURE} alias set local ${ACTIVE_MINIO_TARGET} ${MINIO_ACCESS_KEY} ${MINIO_SECRET_KEY} >/dev/null"; then
    return 0
  fi

  local fallback_target
  fallback_target="$(build_fallback_target "${ACTIVE_MINIO_TARGET}")"
  local fallback_insecure="${ACTIVE_MC_INSECURE}"
  if [[ "${fallback_target}" =~ ^https:// ]]; then
    fallback_insecure="--insecure"
  fi

  echo "⚠️ Alias MinIO en échec sur ${ACTIVE_MINIO_TARGET}, tentative fallback: ${fallback_target}"
  if docker compose exec -T minio /bin/sh -c \
    "set -e; export LC_ALL=C LANG=C; mc ${fallback_insecure} alias set local ${fallback_target} ${MINIO_ACCESS_KEY} ${MINIO_SECRET_KEY} >/dev/null"; then
    ACTIVE_MINIO_TARGET="${fallback_target}"
    ACTIVE_MC_INSECURE="${fallback_insecure}"
    return 0
  fi
  return 1
}

mkdir -p "${LOG_DIR}"

echo "=== SNAPSHOT RAW DATA -> MINIO ==="
echo "Dataset dir   : ${DATASET_DIR}"
echo "Snapshot UTC  : ${TIMESTAMP_UTC}"
echo "MinIO endpoint: ${MINIO_TARGET}"
echo "MinIO user    : ${MINIO_ACCESS_KEY}"

if [[ ! -d "${DATASET_DIR}" ]]; then
  echo "ERREUR: dataset introuvable: ${DATASET_DIR}" >&2
  exit 1
fi

# Prépare l'alias et le bucket cible.
ensure_minio_alias
docker compose exec -T minio /bin/sh -c \
  "set -e; export LC_ALL=C LANG=C; mc ${ACTIVE_MC_INSECURE} ls local/bronze >/dev/null"

FILES=()
while IFS= read -r file; do
  FILES+=("${file}")
done < <(
  {
    find "${DATASET_DIR}" -maxdepth 1 -type f \( -name "*.csv" -o -name "*.parquet" -o -name "*.jsonl" \)
    find "${DATASET_DIR}/synthetic_id_cards" -maxdepth 1 -type f -name "*.png"
  } | sort
)

if [[ "${#FILES[@]}" -eq 0 ]]; then
  echo "ERREUR: aucun fichier à uploader" >&2
  exit 1
fi

uploaded=0
for file in "${FILES[@]}"; do
  rel_path="${file#${ROOT_DIR}/}"
  object_path="${SNAPSHOT_PREFIX}/${rel_path}"
  sha256="$(shasum -a 256 "${file}" | awk '{print $1}')"
  size_bytes="$(wc -c < "${file}" | tr -d ' ')"

  cat "${file}" | docker compose exec -T minio /bin/sh -c \
    "set -e; export LC_ALL=C LANG=C; mc ${ACTIVE_MC_INSECURE} alias set local ${ACTIVE_MINIO_TARGET} ${MINIO_ACCESS_KEY} ${MINIO_SECRET_KEY} >/dev/null; mc ${ACTIVE_MC_INSECURE} pipe \"local/${object_path}\" >/dev/null"

  printf "%s\t%s\t%s\t%s\n" "${rel_path}" "${object_path}" "${sha256}" "${size_bytes}" >> "${MANIFEST_TSV}"
  uploaded=$((uploaded + 1))
done

python3 - "${MANIFEST_TSV}" "${MANIFEST_JSON}" "${TIMESTAMP_UTC}" "${uploaded}" <<'PY'
import json
import sys
from pathlib import Path

manifest_tsv = Path(sys.argv[1])
manifest_json = Path(sys.argv[2])
timestamp_utc = sys.argv[3]
uploaded = int(sys.argv[4])

files = []
total_bytes = 0
for line in manifest_tsv.read_text(encoding="utf-8").splitlines():
    rel_path, object_path, sha256, size_bytes = line.split("\t")
    size_int = int(size_bytes)
    total_bytes += size_int
    files.append(
        {
            "relative_path": rel_path,
            "object_path": object_path,
            "sha256": sha256,
            "size_bytes": size_int,
        }
    )

payload = {
    "snapshot_utc": timestamp_utc,
    "uploaded_files": uploaded,
    "total_bytes": total_bytes,
    "files": files,
}
manifest_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(str(manifest_json))
PY

rm -f "${MANIFEST_TSV}"

END_EPOCH="$(date +%s)"
DURATION_SEC=$((END_EPOCH - START_EPOCH))
if [[ "${DURATION_SEC}" -le 0 ]]; then
  DURATION_SEC=1
fi

python3 - "${MANIFEST_JSON}" "${TRANSFER_KPI_HISTORY}" "${TIMESTAMP_UTC}" "${DURATION_SEC}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

manifest_path = Path(sys.argv[1])
history_path = Path(sys.argv[2])
snapshot_utc = sys.argv[3]
duration_sec = max(1, int(sys.argv[4]))

payload = json.loads(manifest_path.read_text(encoding="utf-8"))
total_bytes = int(payload.get("total_bytes", 0))
uploaded_files = int(payload.get("uploaded_files", 0))

kpi = {
    "metric": "data_lake_snapshot",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "snapshot_utc": snapshot_utc,
    "latency_seconds": duration_sec,
    "capacity_bytes": total_bytes,
    "capacity_files": uploaded_files,
    "speed_bytes_per_second": round(total_bytes / duration_sec, 2),
    "speed_files_per_second": round(uploaded_files / duration_sec, 4),
}
history_path.parent.mkdir(parents=True, exist_ok=True)
with history_path.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(kpi) + "\n")
PY

echo "Upload terminé: ${uploaded} fichiers"
echo "Manifest       : ${MANIFEST_JSON}"
echo "Durée          : ${DURATION_SEC}s"
echo "KPI history    : ${TRANSFER_KPI_HISTORY}"

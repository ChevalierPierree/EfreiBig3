#!/usr/bin/env python3
"""Promotion minimale bronze -> silver -> gold dans MinIO."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import psycopg2
from pymongo import MongoClient


ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT_DIR / "logs"
TRANSFER_KPI_HISTORY_FILE = LOG_DIR / "transfer_kpi_history.jsonl"
PROMOTION_REPORT_PATTERN = "data_lake_promotion_{timestamp}.json"


@dataclass
class MinioConfig:
    target: str
    insecure: bool
    root_user: str
    root_password: str


def pg_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "kivendtout"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )


def mongo_client():
    return MongoClient(
        host=os.getenv("MONGODB_HOST", "localhost"),
        port=int(os.getenv("MONGODB_PORT", "27017")),
        username=os.getenv("MONGODB_USER", "admin"),
        password=os.getenv("MONGODB_PASSWORD", "admin"),
        authSource=os.getenv("MONGODB_AUTH_SOURCE", "admin"),
        serverSelectionTimeoutMS=5000,
    )


def resolve_snapshot_manifest(explicit_path: Optional[str]) -> Path:
    if explicit_path:
        candidate = Path(explicit_path)
        if not candidate.is_absolute():
            candidate = ROOT_DIR / candidate
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"Manifest introuvable: {candidate}")

    manifests = sorted(LOG_DIR.glob("data_lake_snapshot_*.json"), reverse=True)
    if manifests:
        return manifests[0]

    subprocess.run(["bash", "scripts/snapshot_raw_data_to_minio.sh"], cwd=ROOT_DIR, check=True)
    manifests = sorted(LOG_DIR.glob("data_lake_snapshot_*.json"), reverse=True)
    if not manifests:
        raise FileNotFoundError("Aucun manifest bronze disponible apres snapshot")
    return manifests[0]


def detect_minio_config() -> MinioConfig:
    endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    scheme_env = os.getenv("MINIO_SCHEME", "").strip().lower()
    cert_exists = (ROOT_DIR / "security" / "minio" / "certs" / "public.crt").exists()
    scheme = "https" if cert_exists else (scheme_env or "http")
    insecure = os.getenv("MINIO_TLS_INSECURE", "").strip().lower() in {"1", "true", "yes", "on"}
    if scheme == "https" and os.getenv("MINIO_TLS_INSECURE", "") == "":
        insecure = True
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        endpoint = endpoint.split("://", 1)[1]
    target = f"{scheme}://{endpoint}"
    return MinioConfig(
        target=target,
        insecure=insecure,
        root_user=os.getenv("MINIO_ROOT_USER", "minio"),
        root_password=os.getenv("MINIO_ROOT_PASSWORD", "minio123"),
    )


def build_fallback_target(target: str) -> str:
    if target.startswith("http://"):
        return target.replace("http://", "https://", 1)
    if target.startswith("https://"):
        return target.replace("https://", "http://", 1)
    return target


def run_minio_command(script: str, *, input_bytes: Optional[bytes] = None, config: Optional[MinioConfig] = None) -> subprocess.CompletedProcess:
    config = config or detect_minio_config()
    insecure_flag = "--insecure" if config.insecure else ""
    alias_cmd = (
        f"mc {insecure_flag} alias set local {shlex.quote(config.target)} "
        f"{shlex.quote(config.root_user)} {shlex.quote(config.root_password)} >/dev/null"
    ).strip()
    full_script = f"set -e; {alias_cmd}; {script}"
    cmd = ["docker", "compose", "exec", "-T", "minio", "/bin/sh", "-c", full_script]
    return subprocess.run(cmd, cwd=ROOT_DIR, input=input_bytes, capture_output=True)


def ensure_minio_connection() -> MinioConfig:
    primary = detect_minio_config()
    primary_flag = "--insecure" if primary.insecure else ""
    probe = run_minio_command(f"mc {primary_flag} ls local >/dev/null".strip(), config=primary)
    if probe.returncode == 0:
        return primary

    fallback = MinioConfig(
        target=build_fallback_target(primary.target),
        insecure=True if build_fallback_target(primary.target).startswith("https://") else False,
        root_user=primary.root_user,
        root_password=primary.root_password,
    )
    fallback_flag = "--insecure" if fallback.insecure else ""
    probe = run_minio_command(f"mc {fallback_flag} ls local >/dev/null".strip(), config=fallback)
    if probe.returncode == 0:
        return fallback
    raise RuntimeError((probe.stderr or b"MinIO indisponible").decode("utf-8", errors="ignore"))


def upload_json_to_minio(object_path: str, payload: dict, config: MinioConfig) -> Dict:
    content = json.dumps(payload, indent=2, ensure_ascii=True).encode("utf-8")
    insecure_flag = "--insecure" if config.insecure else ""
    quoted_target = shlex.quote(f"local/{object_path}")
    script = f"mc {insecure_flag} pipe {quoted_target} >/dev/null".strip()
    started = time.perf_counter()
    result = run_minio_command(script, input_bytes=content, config=config)
    duration = max(time.perf_counter() - started, 0.001)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(f"Echec upload {object_path}: {stderr}")
    return {
        "object_path": object_path,
        "size_bytes": len(content),
        "latency_seconds": round(duration, 3),
        "speed_bytes_per_second": round(len(content) / duration, 2),
    }


def detect_dataset_domain(relative_path: str) -> str:
    path = relative_path.lower()
    if "synthetic_id_cards" in path:
        return "identity"
    if "events" in path:
        return "events"
    if "payments" in path:
        return "payments"
    if "orders" in path:
        return "orders"
    if "customers" in path:
        return "customers"
    if "products" in path:
        return "catalog"
    return "raw"


def estimate_rows(relative_path: str) -> Optional[int]:
    local_file = ROOT_DIR / relative_path
    if not local_file.exists():
        return None
    suffix = local_file.suffix.lower()
    try:
        if suffix == ".csv":
            with local_file.open("r", encoding="utf-8") as handle:
                return max(sum(1 for _ in handle) - 1, 0)
        if suffix == ".jsonl":
            with local_file.open("r", encoding="utf-8") as handle:
                return sum(1 for _ in handle)
        if suffix == ".png":
            return 1
    except Exception:
        return None
    return None


def build_silver_payload(manifest: dict) -> dict:
    files = []
    domains = Counter()
    extensions = Counter()
    datasets = Counter()

    for item in manifest.get("files", []):
        relative_path = item.get("relative_path") or ""
        extension = Path(relative_path).suffix.lower() or "<none>"
        domain = detect_dataset_domain(relative_path)
        dataset_name = Path(relative_path).stem
        normalized = {
            "relative_path": relative_path,
            "object_path": item.get("object_path"),
            "sha256": item.get("sha256"),
            "size_bytes": int(item.get("size_bytes", 0) or 0),
            "extension": extension,
            "domain": domain,
            "dataset_name": dataset_name,
            "estimated_rows": estimate_rows(relative_path),
        }
        files.append(normalized)
        domains[domain] += 1
        extensions[extension] += 1
        datasets[dataset_name] += 1

    return {
        "layer": "silver",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_snapshot_utc": manifest.get("snapshot_utc"),
        "source_uploaded_files": int(manifest.get("uploaded_files", 0) or 0),
        "source_total_bytes": int(manifest.get("total_bytes", 0) or 0),
        "summary": {
            "files_total": len(files),
            "total_bytes": int(manifest.get("total_bytes", 0) or 0),
            "domains": dict(domains),
            "extensions": dict(extensions),
            "datasets": dict(datasets),
        },
        "files": files,
    }


def build_gold_payload(manifest: dict, silver_payload: dict) -> dict:
    with pg_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM payments WHERE COALESCE(payment_status, 'success') = 'success'")
            successful_payments = int(cursor.fetchone()[0] or 0)
            cursor.execute("SELECT COUNT(*) FROM payments WHERE COALESCE(payment_status, 'success') = 'success' AND is_fraudulent = true")
            fraudulent_payments = int(cursor.fetchone()[0] or 0)
            cursor.execute("SELECT COUNT(*) FROM fraud_alerts")
            total_alerts = int(cursor.fetchone()[0] or 0)
            cursor.execute("SELECT COUNT(*) FROM checkout_attempts")
            checkout_attempts = int(cursor.fetchone()[0] or 0)
            cursor.execute("SELECT COUNT(*) FROM checkout_attempts WHERE blocked_underage = true")
            blocked_underage = int(cursor.fetchone()[0] or 0)
            cursor.execute("SELECT COUNT(*) FROM identity_verifications")
            identity_verifications = int(cursor.fetchone()[0] or 0)
            cursor.execute("SELECT COUNT(*) FROM orders")
            total_orders = int(cursor.fetchone()[0] or 0)
            cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'manual_review'")
            manual_review_orders = int(cursor.fetchone()[0] or 0)

    mongo = mongo_client()
    events_total = int(mongo[os.getenv("MONGODB_DB", "kivendtout")][os.getenv("MONGODB_COLLECTION", "events")].count_documents({}))
    mongo.close()

    fraud_rate = round((fraudulent_payments / successful_payments) * 100, 2) if successful_payments else 0.0
    blocked_rate = round((blocked_underage / checkout_attempts) * 100, 2) if checkout_attempts else 0.0

    return {
        "layer": "gold",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_snapshot_utc": manifest.get("snapshot_utc"),
        "business_kpis": {
            "successful_payments": successful_payments,
            "fraudulent_payments": fraudulent_payments,
            "fraud_rate_percent": fraud_rate,
            "total_alerts": total_alerts,
            "checkout_attempts": checkout_attempts,
            "blocked_underage_orders": blocked_underage,
            "blocked_underage_rate_percent": blocked_rate,
            "identity_verifications": identity_verifications,
            "orders_total": total_orders,
            "orders_manual_review": manual_review_orders,
            "events_total": events_total,
        },
        "lake_summary": silver_payload.get("summary", {}),
        "consumption_views": {
            "fraud_dashboard": "gold/business_kpis/latest.json",
            "snapshot_summary": "silver/normalized_snapshot/latest.json",
        },
    }


def append_transfer_metric(metric: str, payload_size_bytes: int, duration_seconds: float, snapshot_utc: str, object_count: int) -> None:
    entry = {
        "metric": metric,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_utc": snapshot_utc,
        "latency_seconds": round(duration_seconds, 3),
        "capacity_bytes": int(payload_size_bytes),
        "capacity_files": int(object_count),
        "speed_bytes_per_second": round(payload_size_bytes / max(duration_seconds, 0.001), 2),
        "speed_files_per_second": round(object_count / max(duration_seconds, 0.001), 4),
    }
    TRANSFER_KPI_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with TRANSFER_KPI_HISTORY_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Promotion bronze -> silver -> gold dans MinIO")
    parser.add_argument("--manifest", help="Manifest bronze local a promouvoir")
    parser.add_argument("--output", help="Rapport JSON de promotion")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = resolve_snapshot_manifest(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot_utc = manifest.get("snapshot_utc")
    if not snapshot_utc:
        raise RuntimeError(f"snapshot_utc absent dans {manifest_path}")

    config = ensure_minio_connection()
    silver_payload = build_silver_payload(manifest)
    gold_payload = build_gold_payload(manifest, silver_payload)

    silver_objects = []
    silver_started = time.perf_counter()
    silver_objects.append(upload_json_to_minio(f"silver/normalized_snapshot/{snapshot_utc}/normalized_manifest.json", silver_payload, config))
    silver_objects.append(upload_json_to_minio("silver/normalized_snapshot/latest.json", silver_payload, config))
    silver_duration = max(time.perf_counter() - silver_started, 0.001)

    gold_objects = []
    gold_started = time.perf_counter()
    gold_objects.append(upload_json_to_minio(f"gold/business_kpis/{snapshot_utc}/fraud_operational_kpis.json", gold_payload, config))
    gold_objects.append(upload_json_to_minio("gold/business_kpis/latest.json", gold_payload, config))
    gold_duration = max(time.perf_counter() - gold_started, 0.001)

    silver_bytes = sum(item["size_bytes"] for item in silver_objects)
    gold_bytes = sum(item["size_bytes"] for item in gold_objects)
    append_transfer_metric("data_lake_silver", silver_bytes, silver_duration, snapshot_utc, len(silver_objects))
    append_transfer_metric("data_lake_gold", gold_bytes, gold_duration, snapshot_utc, len(gold_objects))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_manifest_file": str(manifest_path),
        "source_snapshot_utc": snapshot_utc,
        "minio_target": config.target,
        "layers": {
            "bronze": {
                "bucket": "bronze",
                "snapshot_prefix": f"bronze/raw_snapshot/{snapshot_utc}",
                "uploaded_files": int(manifest.get("uploaded_files", 0) or 0),
                "total_bytes": int(manifest.get("total_bytes", 0) or 0),
            },
            "silver": {
                "bucket": "silver",
                "status": "published",
                "objects": silver_objects,
                "summary": silver_payload.get("summary", {}),
            },
            "gold": {
                "bucket": "gold",
                "status": "published",
                "objects": gold_objects,
                "business_kpis": gold_payload.get("business_kpis", {}),
            },
        },
    }

    report_path = Path(args.output) if args.output else LOG_DIR / PROMOTION_REPORT_PATTERN.format(timestamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    if not report_path.is_absolute():
        report_path = ROOT_DIR / report_path
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")

    print("=== DATA LAKE PROMOTION ===")
    print(f"Bronze manifest : {manifest_path}")
    print(f"Snapshot UTC    : {snapshot_utc}")
    print(f"Silver objects  : {len(silver_objects)} | {silver_bytes} bytes")
    print(f"Gold objects    : {len(gold_objects)} | {gold_bytes} bytes")
    print(f"Report          : {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

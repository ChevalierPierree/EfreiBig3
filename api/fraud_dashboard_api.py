#!/usr/bin/env python3
"""
API FastAPI pour le dashboard de détection de fraude
Permet de:
- Lister les alertes
- Approuver/Bloquer/Investiguer
- Statistiques fraud rate
- Historique décisions
"""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Tuple
from datetime import datetime, timedelta, date, timezone
import asyncio
import importlib.util
import json
import csv
import fnmatch
import subprocess
import threading
import time
import os
import signal
import random
import hashlib
import hmac
import re
import smtplib
import ssl
import psycopg2
import site
import sys
from pathlib import Path
from collections import defaultdict, Counter, deque
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from uuid import uuid4
from email.message import EmailMessage


def patch_kafka_vendor_six():
    """
    Compatibilité Python 3.13 pour kafka-python 2.0.2.
    """
    candidates = []
    try:
        candidates.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        candidates.append(site.getusersitepackages())
    except Exception:
        pass

    for base in candidates:
        six_path = Path(base) / "kafka" / "vendor" / "six.py"
        if not six_path.exists():
            continue
        spec = importlib.util.spec_from_file_location("kafka.vendor.six", six_path)
        if not spec or not spec.loader:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules.setdefault("kafka.vendor.six", module)
        sys.modules.setdefault("kafka.vendor.six.moves", module.moves)
        return


patch_kafka_vendor_six()
try:
    from kafka import KafkaConsumer
except Exception as e:
    KafkaConsumer = None
    KAFKA_IMPORT_ERROR = e
else:
    KAFKA_IMPORT_ERROR = None

app = FastAPI(
    title="KiVendTout Fraud Detection API",
    description="API pour la gestion des alertes de fraude",
    version="1.0.0"
)

CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")
    if origin.strip()
] or ["*"]
CORS_ALLOW_CREDENTIALS = False if CORS_ALLOW_ORIGINS == ["*"] else True

# CORS pour permettre l'accès depuis le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# MODELS
# ============================================================================

class FraudAlert(BaseModel):
    alert_id: str
    alert_timestamp: str
    event_timestamp: Optional[str] = None
    customer_id: str
    session_id: str
    event_type: str
    device: str
    utm_source: str
    customer_country: str
    previous_payments: int
    is_new_customer: bool
    fraud_reasons: List[str]
    risk_score: int
    status: str
    severity: str
    decision: Optional[str] = None
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None

class AlertDecision(BaseModel):
    decision: str  # APPROVE, BLOCK, INVESTIGATE
    decided_by: str  # User ID/email
    notes: Optional[str] = None

class AlertNotificationConfigPayload(BaseModel):
    enabled: bool = False
    recipient_email: Optional[str] = None
    min_severity: str = Field(default="HIGH", pattern="^(LOW|MEDIUM|HIGH)$")
    notify_on_new_alert: bool = True
    notify_on_decision: bool = False
    updated_by: Optional[str] = None

class AlertNotificationTestRequest(BaseModel):
    recipient_email: Optional[str] = None
    message: Optional[str] = None
    updated_by: Optional[str] = None

class FraudStats(BaseModel):
    total_alerts: int
    alerts_by_severity: dict
    alerts_by_status: dict
    fraud_rate: float
    total_payments: int
    fraudulent_payments: int
    alerted_customers: int
    total_customers: int
    customer_alert_coverage: float
    top_fraud_reasons: List[dict]
    alerts_by_hour: List[dict]
    alerts_by_day: List[dict]

class IdentityVerificationRecord(BaseModel):
    verification_id: int
    customer_id: str
    verification_date: str
    document_type: Optional[str] = None
    document_number: Optional[str] = None
    verification_status: Optional[str] = None
    verification_method: Optional[str] = None
    id_card_image_path: Optional[str] = None
    created_at: Optional[str] = None

class IdentityVerificationRequest(BaseModel):
    customer_id: str
    document_number: str
    document_type: str = "national_id"
    verification_method: str = "manual"
    is_adult: Optional[bool] = None
    id_card_image_path: Optional[str] = None

class IdentityStats(BaseModel):
    total_verifications: int
    by_status: dict
    by_method: dict

class ProductCatalogItem(BaseModel):
    product_id: int
    name: str
    category: Optional[str] = None
    price: float
    stock_quantity: int
    is_adult_restricted: bool

class IdCardPreview(BaseModel):
    file: str
    birthdate: str
    age: int
    is_adult: bool

class IdCardAnalysis(BaseModel):
    file: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    sex: Optional[str] = None
    birthdate: str
    age: int
    is_adult: bool
    doc_number: Optional[str] = None
    expiry: Optional[str] = None
    expired: bool
    image_url: str
    image_sha256: str
    backend_analysis_source: str
    fingerprint_birthdate: Optional[str] = None
    fingerprint_match: bool
    model_enabled: bool
    model_version: Optional[str] = None

class OrderItemRequest(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1)

class CheckoutRequest(BaseModel):
    customer_id: str
    id_card_file: str
    items: List[OrderItemRequest]
    payment_method: str = "card"
    risk_profile: str = Field(default="standard", pattern="^(standard|elevated)$")

class CheckoutResponse(BaseModel):
    accepted: bool
    order_id: Optional[int] = None
    payment_id: Optional[int] = None
    payment_status: Optional[str] = None
    payment_is_fraudulent: Optional[bool] = None
    payment_risk_score: Optional[int] = None
    customer_id: str
    id_card_file: str
    customer_age: int
    total_amount: float
    blocked_reason: Optional[str] = None
    blocked_products: List[int] = []
    created_at: str

class CheckoutStats(BaseModel):
    window_hours: int
    total_attempts: int
    accepted_orders: int
    blocked_underage_orders: int
    rejection_rate: float
    adult_product_attempts: int
    adult_product_rejected: int
    adult_rejection_rate: float
    avg_customer_age: float
    last_attempt_at: Optional[str] = None

class CheckoutAttemptRecord(BaseModel):
    attempt_id: int
    attempted_at: str
    customer_id: Optional[str] = None
    id_card_file: Optional[str] = None
    customer_age: Optional[int] = None
    contains_adult_product: bool
    blocked_underage: bool
    accepted: bool
    blocked_products: Optional[str] = None
    total_amount: Optional[float] = None
    order_id: Optional[int] = None
    notes: Optional[str] = None


class PaymentStats(BaseModel):
    window_hours: int
    total_payments: int
    successful_payments: int
    failed_payments: int
    fraudulent_payments: int
    fraud_rate: float
    payment_methods: dict
    payment_statuses: dict
    last_payment_at: Optional[str] = None

class FraudReasonStat(BaseModel):
    reason: str
    total: int
    high: int
    medium: int
    low: int

class AlertSimulationRequest(BaseModel):
    customer_id: Optional[str] = None
    session_id: Optional[str] = None
    event_type: Optional[str] = None
    device: Optional[str] = None
    utm_source: Optional[str] = None
    customer_country: Optional[str] = None
    previous_payments: Optional[int] = Field(default=None, ge=0, le=200)
    is_new_customer: Optional[bool] = None
    fraud_reasons: Optional[List[str]] = None
    risk_score: Optional[int] = Field(default=None, ge=0, le=100)
    severity: Optional[str] = Field(default=None, pattern="^(LOW|MEDIUM|HIGH)$")
    status: str = Field(default="PENDING_REVIEW", pattern="^(PENDING_REVIEW|APPROVED|BLOCKED|INVESTIGATING)$")

class RuntimeRefreshRequest(BaseModel):
    sync_kafka: bool = True
    run_scaling: bool = True
    run_alert_scaling: bool = True
    restart_api: bool = True
    max_sync_messages: int = Field(default=2000, ge=0, le=50000)
    requests: int = Field(default=80, ge=1, le=5000)
    concurrency: int = Field(default=16, ge=1, le=200)
    adult_order_ratio: float = Field(default=0.6, ge=0.0, le=1.0)
    minor_ratio: float = Field(default=0.4, ge=0.0, le=1.0)
    scaling_mode: str = Field(default="realtime", pattern="^(burst|realtime)$")
    duration_seconds: int = Field(default=30, ge=1, le=3600)
    rps: int = Field(default=8, ge=1, le=200)
    alerts_mode: str = Field(default="realtime", pattern="^(burst|realtime)$")
    alerts_requests: int = Field(default=120, ge=1, le=20000)
    alerts_concurrency: int = Field(default=10, ge=1, le=200)
    alerts_duration_seconds: int = Field(default=30, ge=1, le=3600)
    alerts_rps: int = Field(default=6, ge=1, le=500)
    high_severity_ratio: float = Field(default=0.35, ge=0.0, le=1.0)

class RuntimeRefreshResponse(BaseModel):
    started_orders: bool
    orders_pid: Optional[int] = None
    started_alerts: bool
    alerts_pid: Optional[int] = None
    synced_alerts: int
    scaling_mode: str
    requests: int
    concurrency: int
    duration_seconds: int
    rps: int
    alerts_mode: str
    alerts_requests: int
    alerts_concurrency: int
    alerts_duration_seconds: int
    alerts_rps: int
    log_file: str
    message: str

class DataFactoryActionResponse(BaseModel):
    action_key: str
    status: str
    title: str
    domain: str
    timestamp: str
    message: str
    async_job: bool = False
    passed: Optional[bool] = None
    resources: Optional[dict] = None
    response: Optional[dict] = None
    process: Optional[dict] = None

class PresentationTestRequest(BaseModel):
    recipient_email: Optional[str] = None

class PresentationTestResponse(BaseModel):
    test_key: str
    status: str
    title: str
    category: str
    timestamp: str
    message: str
    async_job: bool = False
    passed: Optional[bool] = None
    duration_ms: Optional[float] = None
    highlights: List[str] = Field(default_factory=list)
    resources: Optional[dict] = None
    response: Optional[dict] = None
    process: Optional[dict] = None

class MicroBatchRunRequest(BaseModel):
    mode: str = Field(default="once", pattern="^(once|live|daemon)$")
    window_seconds: int = Field(default=300, ge=1, le=3600)
    bootstrap_minutes: int = Field(default=10, ge=0, le=10080)
    poll_interval: float = Field(default=1.0, gt=0.0, le=60.0)
    duration_seconds: int = Field(default=120, ge=1, le=86400)

class MicroBatchRunResponse(BaseModel):
    running: bool
    mode: str
    returncode: Optional[int] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    log_file: str
    message: str
    output_lines: List[str] = []

class DataResetRequest(BaseModel):
    confirm: bool = True
    clear_runtime_artifacts: bool = True
    stop_live_jobs: bool = True

class DataResetResponse(BaseModel):
    running: bool
    status: str
    requested_at: Optional[str] = None
    requested_by: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    step: Optional[str] = None
    message: str
    log_file: str
    output_lines: List[str] = []
    summary: Optional[dict] = None

# ============================================================================
# DATABASE
# ============================================================================

DATASET_DIR = Path(__file__).resolve().parent.parent / "kivendtout_dataset"
ID_CARDS_DIR = DATASET_DIR / "synthetic_id_cards"
ID_LABELS_FILE = DATASET_DIR / "synthetic_id_labels.csv"
ID_LABELS_CACHE = None
ID_LABEL_RECORDS_CACHE = None
BASE_DIR = Path(__file__).resolve().parent.parent
ID_FINGERPRINT_MODEL_FILE = BASE_DIR / "models" / "id_card_fingerprint_model.json"
ID_FINGERPRINT_MODEL_CACHE = None
RUNTIME_LOG_FILE = BASE_DIR / "logs" / "runtime_refresh.log"
MICRO_BATCH_RUN_LOG_FILE = BASE_DIR / "logs" / "micro_batch_run.log"
TRANSFER_KPI_HISTORY_FILE = BASE_DIR / "logs" / "transfer_kpi_history.jsonl"
ANALYTICS_WAREHOUSE_REPORT_FILE = BASE_DIR / "logs" / "analytics_warehouse_report.json"
DATA_PLATFORM_PIPELINE_REPORT_FILE = BASE_DIR / "logs" / "data_platform_pipeline_report.json"
ALERT_NOTIFICATION_CONFIG_FILE = BASE_DIR / "config" / "alert_notification_settings.json"
ALERT_NOTIFICATION_HISTORY_FILE = BASE_DIR / "logs" / "alert_notification_history.jsonl"
ALERT_NOTIFICATION_PREVIEW_DIR = BASE_DIR / "logs" / "alert_email_preview"
USE_CASE_HISTORY_FILE = BASE_DIR / "logs" / "use_case_history.jsonl"
DATA_FACTORY_HISTORY_FILE = BASE_DIR / "logs" / "data_factory_history.jsonl"
PRESENTATION_TEST_HISTORY_FILE = BASE_DIR / "logs" / "presentation_test_history.jsonl"
DATA_RESET_LOG_FILE = BASE_DIR / "logs" / "data_reset.log"
RESET_SCHEMA_SQL_FILE = BASE_DIR / "database" / "postgres" / "init" / "00_reset_schema.sql"
DATA_LAKE_PROMOTION_REPORT_GLOB = "data_lake_promotion_*.json"
DATA_LAKE_SNAPSHOT_REPORT_GLOB = "data_lake_snapshot_*.json"
LIVE_STREAM_HEARTBEAT_SECONDS = float(os.getenv("LIVE_STREAM_HEARTBEAT_SECONDS", "1.0"))
RUNTIME_REFRESH_LOCK = threading.Lock()
RUNTIME_SCALING_PROCESS = None
RUNTIME_ALERTS_PROCESS = None
MICRO_BATCH_RUN_LOCK = threading.Lock()
ALERT_NOTIFICATION_LOCK = threading.Lock()
DATA_RESET_LOCK = threading.Lock()
DATA_RESET_STATE_LOCK = threading.Lock()
PRESENTATION_TEST_LOCK = threading.Lock()
LIVE_EVENT_LOOP = None
LIVE_EVENT_SUBSCRIBERS = []
LIVE_EVENT_LOCK = threading.Lock()
MICRO_BATCH_LAST_RESULT = {
    "running": False,
    "mode": "once",
    "returncode": None,
    "started_at": None,
    "finished_at": None,
    "duration_seconds": None,
    "log_file": str(MICRO_BATCH_RUN_LOG_FILE),
    "message": "Aucune execution declenchee",
    "output_lines": [],
}
DATA_RESET_STATE = {
    "running": False,
    "status": "idle",
    "requested_at": None,
    "requested_by": None,
    "started_at": None,
    "finished_at": None,
    "duration_seconds": None,
    "step": None,
    "message": "Jeu de donnees initial disponible",
    "log_file": str(DATA_RESET_LOG_FILE),
    "output_lines": [],
    "summary": {},
}
RUNTIME_SCALING_STATE = {
    "kind": "orders",
    "running": False,
    "pid": None,
    "mode": None,
    "started_at": None,
    "finished_at": None,
    "expected_end_at": None,
    "duration_seconds": None,
    "requests": None,
    "concurrency": None,
    "rps": None,
    "returncode": None,
    "message": "Aucun flux commandes en cours",
}
RUNTIME_ALERTS_STATE = {
    "kind": "alerts",
    "running": False,
    "pid": None,
    "mode": None,
    "started_at": None,
    "finished_at": None,
    "expected_end_at": None,
    "duration_seconds": None,
    "requests": None,
    "concurrency": None,
    "rps": None,
    "returncode": None,
    "message": "Aucun flux alertes en cours",
}
API_ACCESS_CONTROL_FILE = Path(
    os.getenv("API_ACCESS_CONTROL_FILE", str(BASE_DIR / "config" / "api_access_control.json"))
)
API_ACCESS_CONTROL_CACHE = None
API_ACCESS_CONTROL_MTIME = None
API_RATE_LIMIT_LOCK = threading.Lock()
API_RATE_LIMIT_STATE = defaultdict(deque)

API_KEY_REQUIRED = os.getenv("API_KEY_REQUIRED", "false").strip().lower() in {"1", "true", "yes", "on"}
API_KEY_HEADER = os.getenv("API_KEY_HEADER", "X-API-Key")
API_KEY_VALUE = os.getenv("API_KEY_VALUE", "")
API_KEY_EXEMPT_PATH_PREFIXES = ("/docs", "/redoc", "/openapi.json", "/health")
DOCUMENT_HASH_SALT = os.getenv("DOCUMENT_HASH_SALT", "kivendtout-dev-salt")
API_RBAC_ENABLED = os.getenv("API_RBAC_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
API_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("API_RATE_LIMIT_WINDOW_SECONDS", "60"))
API_RATE_LIMIT_MAX_REQUESTS = int(os.getenv("API_RATE_LIMIT_MAX_REQUESTS", "120"))

FRAUD_REASON_POOL = [
    "FIRST_PAYMENT",
    "NEW_CUSTOMER",
    "UNUSUAL_HOUR",
    "MOBILE_DEVICE",
    "DIRECT_TRAFFIC",
    "PAYMENT_FAILED",
    "VELOCITY_HIGH",
    "NEW_DEVICE",
    "UNUSUAL_AMOUNT",
    "FAST_CHECKOUT",
    "GEO_MISMATCH"
]


def _serialize_live_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _serialize_live_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_live_value(item) for item in value]
    return value


def publish_live_event(topic: str, payload: Optional[dict] = None):
    """
    Publie un evenement temps reel vers les dashboards via SSE.
    Les producteurs sont synchrones; la diffusion est re-routee vers la boucle asyncio FastAPI.
    """
    loop = LIVE_EVENT_LOOP
    if loop is None:
        return

    event = {
        "event_id": uuid4().hex[:12],
        "topic": topic,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "payload": _serialize_live_value(payload or {}),
    }

    def _dispatch():
        stale = []
        with LIVE_EVENT_LOCK:
            subscribers = list(LIVE_EVENT_SUBSCRIBERS)
        for queue in subscribers:
            try:
                if queue.full():
                    try:
                        queue.get_nowait()
                    except Exception:
                        pass
                queue.put_nowait(event)
            except Exception:
                stale.append(queue)
        if stale:
            with LIVE_EVENT_LOCK:
                for queue in stale:
                    if queue in LIVE_EVENT_SUBSCRIBERS:
                        LIVE_EVENT_SUBSCRIBERS.remove(queue)

    try:
        loop.call_soon_threadsafe(_dispatch)
    except RuntimeError:
        pass


def snapshot_data_reset_state() -> dict:
    with DATA_RESET_STATE_LOCK:
        return _serialize_live_value(dict(DATA_RESET_STATE))


def _set_data_reset_state(**updates) -> dict:
    serialized = {key: _serialize_live_value(value) for key, value in updates.items()}
    with DATA_RESET_STATE_LOCK:
        DATA_RESET_STATE.update(serialized)
        state = dict(DATA_RESET_STATE)
    publish_live_event("data_reset", state)
    return _serialize_live_value(state)


def _append_data_reset_log(message: str, *, step: Optional[str] = None) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    line = f"[{timestamp}] {message}"
    DATA_RESET_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_RESET_LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")

    with DATA_RESET_STATE_LOCK:
        lines = list(DATA_RESET_STATE.get("output_lines") or [])
        lines.append(line)
        DATA_RESET_STATE["output_lines"] = lines[-40:]
        DATA_RESET_STATE["message"] = message
        if step is not None:
            DATA_RESET_STATE["step"] = step
        state = dict(DATA_RESET_STATE)
    publish_live_event("data_reset", state)
    return _serialize_live_value(state)


def _reset_micro_batch_runtime_state():
    MICRO_BATCH_LAST_RESULT.update({
        "running": False,
        "mode": "once",
        "returncode": None,
        "started_at": None,
        "finished_at": None,
        "duration_seconds": None,
        "log_file": str(MICRO_BATCH_RUN_LOG_FILE),
        "message": "Aucune execution declenchee",
        "output_lines": [],
    })


def _stop_process_group(process: subprocess.Popen, timeout_seconds: float = 5.0) -> Optional[int]:
    if process is None or process.poll() is not None:
        return None
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=timeout_seconds)
    except ProcessLookupError:
        return process.poll()
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=timeout_seconds)
    return process.returncode


def _stop_runtime_process_for_reset(kind: str):
    global RUNTIME_SCALING_PROCESS, RUNTIME_ALERTS_PROCESS

    process = RUNTIME_SCALING_PROCESS if kind == "orders" else RUNTIME_ALERTS_PROCESS
    if process is None or process.poll() is not None:
        return

    returncode = _stop_process_group(process)
    finished_at = datetime.now(timezone.utc).isoformat()
    message = f"Flux {kind} arrete pour reset"
    _set_runtime_process_state(
        kind,
        running=False,
        finished_at=finished_at,
        expected_end_at=None,
        returncode=returncode,
        message=message,
    )
    publish_live_event("runtime_state", {
        "kind": kind,
        "running": False,
        "finished_at": finished_at,
        "returncode": returncode,
        "message": message,
    })
    append_runtime_log(f"{message} (pid={process.pid}, rc={returncode})")
    if kind == "orders":
        RUNTIME_SCALING_PROCESS = None
    else:
        RUNTIME_ALERTS_PROCESS = None


def _clear_generated_demo_artifacts():
    files_to_clear = [
        DATA_FACTORY_HISTORY_FILE,
        USE_CASE_HISTORY_FILE,
        PRESENTATION_TEST_HISTORY_FILE,
        ALERT_NOTIFICATION_HISTORY_FILE,
        TRANSFER_KPI_HISTORY_FILE,
        MICRO_BATCH_RUN_LOG_FILE,
        RUNTIME_LOG_FILE,
    ]
    for file_path in files_to_clear:
        try:
            file_path.unlink(missing_ok=True)
        except Exception as exc:
            _append_data_reset_log(f"Impossible de supprimer {file_path.name}: {exc}")

    preview_dir = ALERT_NOTIFICATION_PREVIEW_DIR
    if preview_dir.exists():
        for child in preview_dir.iterdir():
            try:
                if child.is_file():
                    child.unlink()
            except Exception as exc:
                _append_data_reset_log(f"Impossible de supprimer {child.name}: {exc}")


def _collect_reset_summary() -> dict:
    summary = {}
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        for table in ("customers", "products", "orders", "payments", "identity_verifications", "fraud_alerts"):
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            summary[f"postgres_{table}"] = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT(*) FROM checkout_attempts")
        summary["postgres_checkout_attempts"] = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT(*) FROM micro_batch_event_metrics")
        summary["postgres_micro_batch_metrics"] = int(cursor.fetchone()[0])
    finally:
        cursor.close()
        conn.close()
    return summary


def _run_subprocess_or_raise(cmd: List[str], *, step: str) -> List[str]:
    _append_data_reset_log(f"Execution {step}: {' '.join(cmd)}", step=step)
    result = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    output_lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
    error_lines = [line for line in (result.stderr or "").splitlines() if line.strip()]
    for line in (output_lines + error_lines)[-20:]:
        _append_data_reset_log(line, step=step)
    if result.returncode != 0:
        raise RuntimeError(f"Echec {step} (rc={result.returncode})")
    return (output_lines + error_lines)[-20:]


def _execute_initial_schema_reset():
    if not RESET_SCHEMA_SQL_FILE.exists():
        raise FileNotFoundError(f"Schema reset introuvable: {RESET_SCHEMA_SQL_FILE}")
    sql = RESET_SCHEMA_SQL_FILE.read_text(encoding="utf-8")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DROP TABLE IF EXISTS checkout_attempts CASCADE;
            DROP TABLE IF EXISTS micro_batch_event_metrics CASCADE;
        """)
        cursor.execute(sql)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _run_initial_data_reset(requested_by: str, clear_runtime_artifacts: bool, stop_live_jobs: bool):
    requested_at = datetime.now(timezone.utc).isoformat()
    started_at = datetime.now(timezone.utc)
    DATA_RESET_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_RESET_LOG_FILE.write_text("", encoding="utf-8")
    _set_data_reset_state(
        running=True,
        status="running",
        requested_at=requested_at,
        requested_by=requested_by,
        started_at=started_at.isoformat(),
        finished_at=None,
        duration_seconds=None,
        step="prepare",
        message="Preparation du reset",
        output_lines=[],
        summary={},
    )
    _append_data_reset_log("Reset demande depuis le dashboard", step="prepare")

    try:
        if MICRO_BATCH_RUN_LOCK.locked():
            raise RuntimeError("Micro-batch en cours. Attendre la fin avant reset.")

        if stop_live_jobs:
            _append_data_reset_log("Arret des flux temps reel", step="prepare")
            _stop_runtime_process_for_reset("orders")
            _stop_runtime_process_for_reset("alerts")

        if clear_runtime_artifacts:
            _append_data_reset_log("Purge des historiques generes", step="cleanup")
            _clear_generated_demo_artifacts()

        _append_data_reset_log("Application du schema initial PostgreSQL", step="postgres_schema")
        _execute_initial_schema_reset()

        _run_subprocess_or_raise(
            [sys.executable, str(BASE_DIR / "scripts" / "load_complete_data_to_postgres.py")],
            step="postgres_reload",
        )
        _run_subprocess_or_raise(
            [sys.executable, str(BASE_DIR / "scripts" / "load_events_to_mongodb.py")],
            step="mongo_reload",
        )

        _append_data_reset_log("Recreation des tables techniques", step="technical_tables")
        init_fraud_alerts_table()
        init_identity_verifications_table()
        init_checkout_attempts_table()
        init_micro_batch_metrics_table()
        _reset_micro_batch_runtime_state()
        _set_runtime_process_state(
            "orders",
            running=False,
            pid=None,
            mode=None,
            started_at=None,
            finished_at=None,
            expected_end_at=None,
            duration_seconds=None,
            requests=None,
            concurrency=None,
            rps=None,
            returncode=None,
            message="Aucun flux commandes en cours",
        )
        _set_runtime_process_state(
            "alerts",
            running=False,
            pid=None,
            mode=None,
            started_at=None,
            finished_at=None,
            expected_end_at=None,
            duration_seconds=None,
            requests=None,
            concurrency=None,
            rps=None,
            returncode=None,
            message="Aucun flux alertes en cours",
        )

        summary = _collect_reset_summary()
        finished_at = datetime.now(timezone.utc)
        duration_seconds = round((finished_at - started_at).total_seconds(), 2)
        success_message = "Reset termine. Base et evenements revenus a l etat initial."
        _append_data_reset_log(success_message, step="done")
        _set_data_reset_state(
            running=False,
            status="success",
            finished_at=finished_at.isoformat(),
            duration_seconds=duration_seconds,
            step="done",
            message=success_message,
            summary=summary,
        )
        append_runtime_log("Reset plateforme termine")
        publish_live_event("runtime_state", snapshot_live_runtime_state())
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        duration_seconds = round((finished_at - started_at).total_seconds(), 2)
        failure_message = f"Reset en erreur: {exc}"
        _append_data_reset_log(failure_message, step="error")
        _set_data_reset_state(
            running=False,
            status="error",
            finished_at=finished_at.isoformat(),
            duration_seconds=duration_seconds,
            step="error",
            message=failure_message,
        )
        append_runtime_log(failure_message)
    finally:
        publish_live_event("runtime_state", snapshot_live_runtime_state())

USE_CASE_DEFINITIONS = {
    "minor-adult-checkout": {
        "key": "minor-adult-checkout",
        "title": "Simulation commande mineur",
        "domain": "checkout",
        "expected_outcome": "Commande bloquee",
        "description": "Un mineur tente de commander un produit 18+.",
        "proof": "Le garde-fou de majorite doit retourner un refus 403 et tracer le blocage.",
    },
    "adult-adult-checkout": {
        "key": "adult-adult-checkout",
        "title": "Simulation commande majeur",
        "domain": "checkout",
        "expected_outcome": "Commande acceptee",
        "description": "Un majeur commande un produit 18+ avec une carte valide.",
        "proof": "La commande doit etre creee et journalisee comme acceptee.",
    },
    "identity-verification": {
        "key": "identity-verification",
        "title": "Simulation verification identite",
        "domain": "identity",
        "expected_outcome": "Verification enregistree",
        "description": "Un controle d'identite est enregistre avec hash SHA-256 du document.",
        "proof": "Le document n'est jamais stocke en clair dans la table d'audit.",
    },
    "high-risk-alert": {
        "key": "high-risk-alert",
        "title": "Simulation alerte haute severite",
        "domain": "fraud",
        "expected_outcome": "Alerte creee",
        "description": "Une alerte HIGH est generee avec notification si le canal est actif.",
        "proof": "L'alerte apparait dans le backlog et peut etre notifiee vers l'email configure.",
    },
    "massive-fraud-orders-episode": {
        "key": "massive-fraud-orders-episode",
        "title": "Episode fraude commandes",
        "domain": "fraud",
        "expected_outcome": "Episode lance",
        "description": "Declenche 3 minutes de commandes a risque eleve avec paiements frauduleux, blocages mineurs et alertes HIGH.",
        "proof": "Les dashboards fraude, identite et paiements doivent evoluer en temps reel pendant l'episode.",
    },
}

DATA_FACTORY_ACTIONS = {
    "single-high-alert": {
        "key": "single-high-alert",
        "title": "Alerte haute severite",
        "domain": "fraud",
        "description": "Ajoute une alerte HIGH directement dans le backlog fraude.",
        "impact": "Visible dans la file d'alertes et les KPI fraude.",
        "mode": "sync",
    },
    "alerts-live-3m": {
        "key": "alerts-live-3m",
        "title": "Flux alertes 3 min",
        "domain": "fraud",
        "description": "Genere un flux continu d'alertes synthetiques pendant 3 minutes.",
        "impact": "Alimente les typologies, la severite et la supervision fraude en temps reel.",
        "mode": "live",
    },
    "minor-blocked-checkout": {
        "key": "minor-blocked-checkout",
        "title": "Commande mineur bloquee",
        "domain": "identity",
        "description": "Cree une tentative 18+ refusee pour un mineur.",
        "impact": "Ajoute un blocage dans les stats checkout et la vue identite.",
        "mode": "sync",
    },
    "adult-approved-checkout": {
        "key": "adult-approved-checkout",
        "title": "Commande majeur acceptee",
        "domain": "identity",
        "description": "Cree une commande valide sur produit 18+ avec carte majeure.",
        "impact": "Fait evoluer les stats checkout et l'historique des commandes.",
        "mode": "sync",
    },
    "identity-verification": {
        "key": "identity-verification",
        "title": "Verification d'identite",
        "domain": "identity",
        "description": "Enregistre une verification avec hash SHA-256 du document.",
        "impact": "Alimente la table d'audit et les KPI de verification.",
        "mode": "sync",
    },
    "orders-live-3m": {
        "key": "orders-live-3m",
        "title": "Flux commandes 3 min",
        "domain": "checkout",
        "description": "Declenche un flux continu de checkouts avec verification d'identite, paiements et alertes associees pendant 3 minutes.",
        "impact": "Alimente les volumes checkout, les traces identite, les paiements et les alertes garde-fou en temps reel.",
        "mode": "live",
    },
    "payments-live-3m": {
        "key": "payments-live-3m",
        "title": "Flux paiements 3 min",
        "domain": "checkout",
        "description": "Genere des checkouts majoritairement acceptes pour faire varier proprement les paiements et le fraud_rate.",
        "impact": "Fait evoluer le volume de paiements, le taux de fraude et les alertes de revue paiement en temps reel.",
        "mode": "live",
    },
    "massive-fraud-orders-3m": {
        "key": "massive-fraud-orders-3m",
        "title": "Episode fraude commandes 3 min",
        "domain": "fraud",
        "description": "Declenche un episode massif de commandes a risque, paiements frauduleux et alertes haute severite pendant 3 minutes.",
        "impact": "Fait monter rapidement les paiements frauduleux, les blocages mineurs et la pression d'alertes sur les dashboards.",
        "mode": "live",
    },
    "data-lake-pipeline": {
        "key": "data-lake-pipeline",
        "title": "Pipeline Data Lake",
        "domain": "data",
        "description": "Promouvoit le dernier snapshot bronze en jeux silver et gold exploitables dans MinIO.",
        "impact": "Materialise un lake minimal bronze -> silver -> gold avec objets de synthese et KPI de transfert.",
        "mode": "sync",
    },
    "analytics-warehouse": {
        "key": "analytics-warehouse",
        "title": "Warehouse et datamarts",
        "domain": "data",
        "description": "Construit un schema analytics separe avec dimensions, faits et datamarts dans PostgreSQL.",
        "impact": "Rend l'analyse multidimensionnelle explicite et separee du store operationnel.",
        "mode": "sync",
    },
    "data-platform-pipeline": {
        "key": "data-platform-pipeline",
        "title": "Plateforme data consolidee",
        "domain": "data",
        "description": "Orchestre snapshot bronze, promotion lake, reconstruction analytics et controles de qualite dans une seule execution.",
        "impact": "Produit un etat de sante consolide de la chaine data pour pilotage et livraison.",
        "mode": "sync",
    },
}

PRESENTATION_TEST_DEFINITIONS = {
    "platform-readiness": {
        "key": "platform-readiness",
        "title": "Disponibilite plateforme",
        "category": "precheck",
        "order": 1,
        "action_label": "Verifier",
        "description": "Verifie que l'API, les dashboards et les services data sont accessibles.",
        "expected_outcome": "Checklist complete au vert.",
        "impact": "Donne une base stable avant de lancer les cas metier et les episodes live.",
        "dashboards": ["index.html"],
    },
    "global-validation": {
        "key": "global-validation",
        "title": "Validation complete",
        "category": "validation",
        "order": 2,
        "action_label": "Executer",
        "description": "Rejoue les validations globales: RBAC, lake, micro-batch, charge, resilience et conformite.",
        "expected_outcome": "Sujet 1 PASS et conformite complete PASS.",
        "impact": "Prouve que la plateforme tient au-dela du seul front.",
        "dashboards": ["index.html"],
    },
    "core-use-cases": {
        "key": "core-use-cases",
        "title": "Cas metiers clefs",
        "category": "functional",
        "order": 3,
        "action_label": "Rejouer",
        "description": "Relance le blocage mineur, le checkout majeur, la verification d'identite et l'alerte HIGH.",
        "expected_outcome": "Les 4 cas passent sans erreur.",
        "impact": "Montre que checkout, identite et fraude sont relies dans le meme systeme.",
        "dashboards": ["fraud_dashboard.html", "id_cards_dashboard.html", "use_cases_dashboard.html"],
    },
    "notifications-workflow": {
        "key": "notifications-workflow",
        "title": "Workflow notifications",
        "category": "functional",
        "order": 4,
        "action_label": "Notifier",
        "description": "Configure un destinataire, cree une alerte, envoie une notification manuelle puis une decision.",
        "expected_outcome": "Historique new_alert, manual et decision present.",
        "impact": "Rend le projet concret pour un operateur fraude.",
        "dashboards": ["fraud_dashboard.html"],
    },
    "micro-batch-once": {
        "key": "micro-batch-once",
        "title": "Micro-batch 1 fenetre",
        "category": "data",
        "order": 5,
        "action_label": "Traiter",
        "description": "Traite une fenetre MongoDB -> PostgreSQL et remonte des KPI exploitables.",
        "expected_outcome": "Evenements, latence et debit non nuls.",
        "impact": "Montre la consolidation batch en plus du streaming.",
        "dashboards": ["transfer_kpi_dashboard.html"],
    },
    "data-lake-pipeline": {
        "key": "data-lake-pipeline",
        "title": "Pipeline bronze -> silver -> gold",
        "category": "data",
        "order": 6,
        "action_label": "Promouvoir",
        "description": "Capture un snapshot brut puis publie les couches silver et gold dans MinIO.",
        "expected_outcome": "Rapport MinIO avec couches publiees.",
        "impact": "Montre un lake minimal exploitable par les KPI.",
        "dashboards": ["transfer_kpi_dashboard.html"],
    },
    "analytics-warehouse": {
        "key": "analytics-warehouse",
        "title": "Warehouse et datamarts",
        "category": "data",
        "order": 7,
        "action_label": "Construire",
        "description": "Materialise un schema analytics separe avec dimensions, faits et marts metier.",
        "expected_outcome": "Schema analytics peuple et datamarts requetables.",
        "impact": "Couvre l'axe analytique multidimensionnel du projet.",
        "dashboards": ["index.html", "transfer_kpi_dashboard.html"],
    },
    "payments-live-3m": {
        "key": "payments-live-3m",
        "title": "Flux paiements 3 min",
        "category": "live",
        "order": 8,
        "action_label": "Lancer 3 min",
        "description": "Injecte des paiements a risque eleve pour faire varier proprement le fraud_rate.",
        "expected_outcome": "Le fraud_rate et le volume paiements evoluent en direct.",
        "impact": "Donne un signal live lisible sur fraude et paiements.",
        "dashboards": ["fraud_dashboard.html", "transfer_kpi_dashboard.html"],
    },
    "massive-fraud-orders-episode": {
        "key": "massive-fraud-orders-episode",
        "title": "Episode fraude commandes",
        "category": "live",
        "order": 9,
        "action_label": "Lancer 3 min",
        "description": "Declenche un episode massif de commandes a risque, blocages mineurs et alertes HIGH.",
        "expected_outcome": "Les vues fraude, identite et paiements montent ensemble.",
        "impact": "Simule un episode de crise realiste.",
        "dashboards": ["fraud_dashboard.html", "id_cards_dashboard.html", "fraud_types_dashboard.html"],
    },
}


def _runtime_state_ref(kind: str) -> dict:
    return RUNTIME_SCALING_STATE if kind == "orders" else RUNTIME_ALERTS_STATE


def _set_runtime_process_state(kind: str, **updates) -> dict:
    state = _runtime_state_ref(kind)
    state.update(updates)
    return dict(state)


def _monitor_runtime_process(kind: str, process: subprocess.Popen):
    returncode = process.wait()
    state = _runtime_state_ref(kind)
    if state.get("pid") != process.pid:
        return
    finished_at = datetime.now(timezone.utc).isoformat()
    message = "Flux termine" if returncode == 0 else "Flux termine avec erreur"
    _set_runtime_process_state(
        kind,
        running=False,
        finished_at=finished_at,
        returncode=returncode,
        message=message,
    )
    publish_live_event("runtime_state", {
        "kind": kind,
        "running": False,
        "finished_at": finished_at,
        "returncode": returncode,
        "message": message,
    })
    append_runtime_log(f"Flux {kind} termine (pid={process.pid}, rc={returncode})")


def snapshot_live_runtime_state() -> dict:
    orders_state = dict(RUNTIME_SCALING_STATE)
    alerts_state = dict(RUNTIME_ALERTS_STATE)
    if RUNTIME_SCALING_PROCESS is not None and RUNTIME_SCALING_PROCESS.poll() is not None and orders_state.get("running"):
        orders_state = _set_runtime_process_state(
            "orders",
            running=False,
            finished_at=orders_state.get("finished_at") or datetime.now(timezone.utc).isoformat(),
            returncode=RUNTIME_SCALING_PROCESS.returncode,
            message="Flux commandes termine",
        )
    if RUNTIME_ALERTS_PROCESS is not None and RUNTIME_ALERTS_PROCESS.poll() is not None and alerts_state.get("running"):
        alerts_state = _set_runtime_process_state(
            "alerts",
            running=False,
            finished_at=alerts_state.get("finished_at") or datetime.now(timezone.utc).isoformat(),
            returncode=RUNTIME_ALERTS_PROCESS.returncode,
            message="Flux alertes termine",
        )
    data_reset_state = snapshot_data_reset_state()
    jobs_active = bool(
        orders_state.get("running")
        or alerts_state.get("running")
        or MICRO_BATCH_LAST_RESULT.get("running")
        or data_reset_state.get("running")
    )
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "heartbeat_seconds": LIVE_STREAM_HEARTBEAT_SECONDS,
        "jobs_active": jobs_active,
        "orders": orders_state,
        "alerts": alerts_state,
        "data_reset": data_reset_state,
        "micro_batch": {
            "running": bool(MICRO_BATCH_LAST_RESULT.get("running")),
            "mode": MICRO_BATCH_LAST_RESULT.get("mode"),
            "started_at": MICRO_BATCH_LAST_RESULT.get("started_at"),
            "finished_at": MICRO_BATCH_LAST_RESULT.get("finished_at"),
            "message": MICRO_BATCH_LAST_RESULT.get("message"),
        },
    }


def _normalize_quota(quota_payload: Optional[dict]) -> dict:
    quota_payload = quota_payload or {}
    window_seconds = int(quota_payload.get("window_seconds", API_RATE_LIMIT_WINDOW_SECONDS))
    max_requests = int(quota_payload.get("max_requests", API_RATE_LIMIT_MAX_REQUESTS))
    return {
        "window_seconds": max(1, window_seconds),
        "max_requests": max(1, max_requests),
    }


def _default_api_access_control() -> dict:
    role_permissions = {
        "admin": ["*"],
        "analyst": [
            "GET:/api/alerts*",
            "POST:/api/alerts/*",
            "GET:/api/stats*",
            "GET:/api/fraud/*",
            "GET:/api/alert-notifications*",
            "POST:/api/alert-notifications*",
            "PUT:/api/alert-notifications*",
            "GET:/api/use-cases*",
            "POST:/api/use-cases*",
            "GET:/api/presentation/tests*",
            "POST:/api/presentation/tests*",
            "GET:/api/identity/*",
            "GET:/api/checkout/*",
            "GET:/api/products*",
            "GET:/api/id-cards*",
            "GET:/api/micro-batch/*",
            "POST:/api/micro-batch/*",
            "GET:/api/transfer/*",
            "GET:/api/kpis/*",
            "GET:/api/system/*",
        ],
        "partner": [
            "GET:/api/products*",
            "POST:/api/orders/checkout",
            "GET:/api/checkout/stats*",
        ],
    }
    keys = []
    if API_KEY_VALUE:
        keys.append(
            {
                "key_id": "legacy-admin",
                "user": "legacy",
                "role": "admin",
                "key": API_KEY_VALUE,
            }
        )
    return {
        "default_quota": _normalize_quota({}),
        "role_permissions": role_permissions,
        "keys": keys,
    }


def load_api_access_control() -> dict:
    global API_ACCESS_CONTROL_CACHE, API_ACCESS_CONTROL_MTIME

    try:
        mtime = API_ACCESS_CONTROL_FILE.stat().st_mtime
    except FileNotFoundError:
        API_ACCESS_CONTROL_CACHE = _default_api_access_control()
        API_ACCESS_CONTROL_MTIME = None
        return API_ACCESS_CONTROL_CACHE

    if API_ACCESS_CONTROL_CACHE is not None and API_ACCESS_CONTROL_MTIME == mtime:
        return API_ACCESS_CONTROL_CACHE

    try:
        payload = json.loads(API_ACCESS_CONTROL_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Erreur lecture API access control, fallback defaults: {e}")
        payload = _default_api_access_control()

    role_permissions = payload.get("role_permissions") or {}
    keys = payload.get("keys") or []
    default_quota = _normalize_quota(payload.get("default_quota"))

    normalized_keys = []
    for row in keys:
        if not isinstance(row, dict):
            continue
        key_id = (row.get("key_id") or row.get("user") or f"key-{len(normalized_keys)+1}").strip()
        if not key_id:
            continue

        raw_key = (row.get("key") or "").strip()
        key_sha256 = (row.get("key_sha256") or "").strip().lower()
        if not raw_key and not key_sha256:
            continue
        if raw_key and not key_sha256:
            key_sha256 = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

        normalized_keys.append(
            {
                "key_id": key_id,
                "user": (row.get("user") or key_id).strip(),
                "role": (row.get("role") or "partner").strip(),
                "key": raw_key,
                "key_sha256": key_sha256,
                "quota": _normalize_quota(row.get("quota")),
                "permissions": row.get("permissions") or [],
            }
        )

    API_ACCESS_CONTROL_CACHE = {
        "default_quota": default_quota,
        "role_permissions": role_permissions,
        "keys": normalized_keys,
    }
    API_ACCESS_CONTROL_MTIME = mtime
    return API_ACCESS_CONTROL_CACHE


def _permission_match(permission: str, method: str, path: str) -> bool:
    permission = (permission or "").strip()
    if not permission:
        return False
    if permission == "*":
        return True

    if ":" in permission:
        perm_method, perm_path = permission.split(":", 1)
    else:
        perm_method, perm_path = "*", permission

    perm_method = perm_method.strip().upper() or "*"
    perm_path = perm_path.strip() or "*"

    if perm_method != "*" and perm_method != method.upper():
        return False
    return fnmatch.fnmatch(path, perm_path)


def _principal_permissions(principal: dict, access_control: dict) -> List[str]:
    direct_permissions = principal.get("permissions") or []
    if direct_permissions:
        return [str(p) for p in direct_permissions]

    role = principal.get("role", "partner")
    role_permissions = access_control.get("role_permissions", {})
    return [str(p) for p in role_permissions.get(role, [])]


def resolve_api_principal(provided_key: str) -> Optional[dict]:
    if not provided_key:
        return None

    access_control = load_api_access_control()
    provided_hash = hashlib.sha256(provided_key.encode("utf-8")).hexdigest()

    for row in access_control.get("keys", []):
        stored_raw = (row.get("key") or "").strip()
        stored_hash = (row.get("key_sha256") or "").strip().lower()
        if stored_raw and hmac.compare_digest(stored_raw, provided_key):
            return row
        if stored_hash and hmac.compare_digest(stored_hash, provided_hash):
            return row
    return None


def enforce_rate_limit(principal: dict, default_quota: dict) -> Tuple[bool, int, int]:
    quota = _normalize_quota(principal.get("quota") or default_quota)
    window_seconds = quota["window_seconds"]
    max_requests = quota["max_requests"]
    state_key = f"{principal.get('user', 'unknown')}::{principal.get('key_id', 'unknown')}"
    now = time.time()

    with API_RATE_LIMIT_LOCK:
        bucket = API_RATE_LIMIT_STATE[state_key]
        while bucket and (now - bucket[0]) >= window_seconds:
            bucket.popleft()

        if len(bucket) >= max_requests:
            retry_after = max(1, int(window_seconds - (now - bucket[0])) + 1)
            return False, retry_after, 0

        bucket.append(now)
        remaining = max(0, max_requests - len(bucket))
        return True, 0, remaining


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """
    Contrôle d'accès API:
    - API key legacy (optionnelle)
    - RBAC (rôle + permissions par endpoint)
    - Quotas glissants (rate limit par clé/utilisateur)
    """
    path = request.url.path
    if path.startswith(API_KEY_EXEMPT_PATH_PREFIXES):
        return await call_next(request)
    if not path.startswith("/api/"):
        return await call_next(request)
    if snapshot_data_reset_state().get("running") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not path.startswith("/api/system/reset"):
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "Data reset in progress",
                    "reset_state": snapshot_data_reset_state(),
                },
            )

    provided_key = request.headers.get(API_KEY_HEADER, "").strip()
    access_control = load_api_access_control() if API_RBAC_ENABLED else {}
    principal = None
    remaining = None
    quota_window = None
    quota_limit = None

    if API_RBAC_ENABLED:
        if provided_key:
            principal = resolve_api_principal(provided_key)
            if not principal:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Unauthorized: invalid API key", "required_header": API_KEY_HEADER},
                )

            permissions = _principal_permissions(principal, access_control)
            if not any(_permission_match(p, request.method, path) for p in permissions):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Forbidden: insufficient role permissions",
                        "role": principal.get("role", "unknown"),
                        "method": request.method,
                        "path": path,
                    },
                )

            default_quota = access_control.get("default_quota", {})
            allowed, retry_after, remaining = enforce_rate_limit(principal, default_quota)
            quota = _normalize_quota(principal.get("quota") or default_quota)
            quota_window = quota["window_seconds"]
            quota_limit = quota["max_requests"]
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Rate limit exceeded",
                        "retry_after_seconds": retry_after,
                        "window_seconds": quota_window,
                        "max_requests": quota_limit,
                        "key_id": principal.get("key_id"),
                        "user": principal.get("user"),
                    },
                    headers={"Retry-After": str(retry_after)},
                )
        elif API_KEY_REQUIRED:
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: missing API key", "required_header": API_KEY_HEADER},
            )
    else:
        if API_KEY_REQUIRED:
            if not API_KEY_VALUE or not hmac.compare_digest(provided_key, API_KEY_VALUE):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Unauthorized: invalid or missing API key", "required_header": API_KEY_HEADER},
                )

    if principal:
        request.state.api_principal = {
            "key_id": principal.get("key_id"),
            "user": principal.get("user"),
            "role": principal.get("role"),
        }

    response = await call_next(request)

    if principal and remaining is not None and quota_window is not None and quota_limit is not None:
        response.headers["X-RateLimit-Limit"] = str(quota_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window-Seconds"] = str(quota_window)
        response.headers["X-API-Key-Id"] = str(principal.get("key_id", "unknown"))
        response.headers["X-API-Role"] = str(principal.get("role", "unknown"))

    return response


def hash_document_number(document_number: str) -> str:
    raw = f"{DOCUMENT_HASH_SALT}:{document_number}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def _severity_rank(severity: Optional[str]) -> int:
    return {"LOW": 1, "MEDIUM": 2, "HIGH": 3}.get(str(severity or "").upper(), 0)


def _validate_email(email: Optional[str]) -> bool:
    if not email:
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(email).strip()))


def default_alert_notification_settings() -> dict:
    recipient = os.getenv("ALERT_NOTIFICATION_EMAIL", "").strip() or None
    return {
        "enabled": False,
        "recipient_email": recipient,
        "min_severity": os.getenv("ALERT_NOTIFICATION_MIN_SEVERITY", "HIGH").strip().upper() or "HIGH",
        "notify_on_new_alert": True,
        "notify_on_decision": False,
        "updated_at": None,
        "updated_by": None,
    }


def smtp_notification_settings() -> dict:
    host = os.getenv("ALERT_SMTP_HOST", "").strip()
    username = os.getenv("ALERT_SMTP_USERNAME", "").strip()
    return {
        "host": host,
        "port": int(os.getenv("ALERT_SMTP_PORT", "587")),
        "username": username,
        "password": os.getenv("ALERT_SMTP_PASSWORD", ""),
        "from_email": os.getenv("ALERT_SMTP_FROM", username or "alerts@kivendtout.local").strip(),
        "use_ssl": os.getenv("ALERT_SMTP_USE_SSL", "false").strip().lower() in {"1", "true", "yes", "on"},
        "use_starttls": os.getenv("ALERT_SMTP_USE_STARTTLS", "true").strip().lower() in {"1", "true", "yes", "on"},
    }


def alert_notification_delivery_mode(config: Optional[dict] = None) -> str:
    config = config or load_alert_notification_settings()
    if not config.get("enabled"):
        return "disabled"
    if smtp_notification_settings().get("host"):
        return "smtp"
    return "preview"


def load_alert_notification_settings() -> dict:
    defaults = default_alert_notification_settings()
    try:
        with ALERT_NOTIFICATION_CONFIG_FILE.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError:
        return defaults
    except Exception:
        return defaults

    if not isinstance(payload, dict):
        return defaults

    merged = {**defaults, **payload}
    merged["min_severity"] = str(merged.get("min_severity", "HIGH")).upper()
    if merged["recipient_email"]:
        merged["recipient_email"] = str(merged["recipient_email"]).strip()
    return merged


def save_alert_notification_settings(payload: dict) -> dict:
    ALERT_NOTIFICATION_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ALERT_NOTIFICATION_LOCK:
        with ALERT_NOTIFICATION_CONFIG_FILE.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=True)
    return payload


def list_alert_notification_history(limit: int = 20) -> List[dict]:
    if not ALERT_NOTIFICATION_HISTORY_FILE.exists():
        return []
    rows = []
    with ALERT_NOTIFICATION_HISTORY_FILE.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:][::-1]


def append_alert_notification_history(entry: dict) -> dict:
    ALERT_NOTIFICATION_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ALERT_NOTIFICATION_HISTORY_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=True) + "\n")
    return entry


def list_use_case_history(limit: int = 20) -> List[dict]:
    if not USE_CASE_HISTORY_FILE.exists():
        return []
    rows = []
    with USE_CASE_HISTORY_FILE.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:][::-1]


def append_use_case_history(entry: dict) -> dict:
    USE_CASE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with USE_CASE_HISTORY_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=True) + "\n")
    return entry


def list_data_factory_history(limit: int = 20) -> List[dict]:
    if not DATA_FACTORY_HISTORY_FILE.exists():
        return []
    rows = []
    with DATA_FACTORY_HISTORY_FILE.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:][::-1]


def append_data_factory_history(entry: dict) -> dict:
    DATA_FACTORY_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FACTORY_HISTORY_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=True) + "\n")
    return entry


def list_presentation_test_history(limit: int = 20) -> List[dict]:
    if not PRESENTATION_TEST_HISTORY_FILE.exists():
        return []
    rows = []
    with PRESENTATION_TEST_HISTORY_FILE.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:][::-1]


def append_presentation_test_history(entry: dict) -> dict:
    PRESENTATION_TEST_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PRESENTATION_TEST_HISTORY_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=True) + "\n")
    return entry


def run_command_capture(cmd: List[str], timeout: Optional[int] = None) -> dict:
    started_at = datetime.now(timezone.utc)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        return {
            "returncode": result.returncode,
            "timed_out": False,
            "duration_seconds": round((datetime.now(timezone.utc) - started_at).total_seconds(), 2),
            "stdout": stdout,
            "stderr": stderr,
            "stdout_tail": stdout.splitlines()[-30:],
            "stderr_tail": stderr.splitlines()[-30:],
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return {
            "returncode": 124,
            "timed_out": True,
            "duration_seconds": round((datetime.now(timezone.utc) - started_at).total_seconds(), 2),
            "stdout": stdout,
            "stderr": stderr,
            "stdout_tail": stdout.splitlines()[-30:],
            "stderr_tail": stderr.splitlines()[-30:],
        }


def _load_json_file(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_data_lake_promotion_reports(limit: int = 10) -> List[dict]:
    reports = []
    for report_path in sorted((BASE_DIR / "logs").glob(DATA_LAKE_PROMOTION_REPORT_GLOB), reverse=True):
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        payload["report_file"] = str(report_path)
        reports.append(payload)
        if len(reports) >= limit:
            break
    return reports


def list_data_lake_snapshot_reports(limit: int = 10) -> List[dict]:
    reports = []
    for report_path in sorted((BASE_DIR / "logs").glob(DATA_LAKE_SNAPSHOT_REPORT_GLOB), reverse=True):
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        payload["report_file"] = str(report_path)
        reports.append(payload)
        if len(reports) >= limit:
            break
    return reports


def latest_data_lake_snapshot_report() -> Optional[dict]:
    reports = list_data_lake_snapshot_reports(limit=1)
    return reports[0] if reports else None


def latest_data_lake_promotion_report() -> Optional[dict]:
    reports = list_data_lake_promotion_reports(limit=1)
    return reports[0] if reports else None


def run_data_lake_promotion_pipeline() -> dict:
    cmd = [sys.executable, str(BASE_DIR / "scripts" / "promote_data_lake_layers.py")]
    result = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    report = latest_data_lake_promotion_report()
    return {
        "returncode": result.returncode,
        "stdout_tail": (result.stdout or "").splitlines()[-20:],
        "stderr_tail": (result.stderr or "").splitlines()[-20:],
        "report": report,
    }


def run_analytics_warehouse_pipeline() -> dict:
    cmd = [sys.executable, str(BASE_DIR / "scripts" / "build_analytics_warehouse.py")]
    result = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    report = _load_json_file(ANALYTICS_WAREHOUSE_REPORT_FILE)
    return {
        "returncode": result.returncode,
        "stdout_tail": (result.stdout or "").splitlines()[-20:],
        "stderr_tail": (result.stderr or "").splitlines()[-20:],
        "report": report,
    }


def run_data_platform_pipeline() -> dict:
    cmd = [sys.executable, str(BASE_DIR / "scripts" / "run_data_platform_pipeline.py")]
    result = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    report = _load_json_file(DATA_PLATFORM_PIPELINE_REPORT_FILE)
    return {
        "returncode": result.returncode,
        "stdout_tail": (result.stdout or "").splitlines()[-20:],
        "stderr_tail": (result.stderr or "").splitlines()[-20:],
        "report": report,
    }


def get_analytics_warehouse_status() -> dict:
    report = _load_json_file(ANALYTICS_WAREHOUSE_REPORT_FILE) or {}
    live = {}
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT to_regnamespace('analytics') IS NOT NULL")
        schema_exists = bool(cursor.fetchone()[0])
        live["schema_exists"] = schema_exists
        if schema_exists:
            objects = {}
            for object_name in [
                "dim_date",
                "dim_customer",
                "dim_product",
                "fact_order",
                "fact_payment",
                "fact_identity_verification",
                "fact_checkout_attempt",
                "fact_fraud_alert",
                "mart_fraud_daily",
                "mart_identity_controls_daily",
                "mart_checkout_risk_daily",
                "mart_product_sales_daily",
            ]:
                cursor.execute(f"SELECT COUNT(*) FROM analytics.{object_name}")
                objects[object_name] = int(cursor.fetchone()[0] or 0)
            cursor.execute("SELECT MAX(refreshed_at) FROM analytics.refresh_log")
            latest_refresh = cursor.fetchone()[0]
            live["objects"] = objects
            live["latest_refresh_at"] = latest_refresh.isoformat() if latest_refresh else None
        cursor.close()
        conn.close()
    except Exception as exc:
        live["error"] = str(exc)
    return {
        "configured": True,
        "schema": "analytics",
        "report_file": str(ANALYTICS_WAREHOUSE_REPORT_FILE),
        "latest_report": report,
        "live": live,
    }


def get_data_platform_status() -> dict:
    snapshot = latest_data_lake_snapshot_report()
    promotion = latest_data_lake_promotion_report()
    analytics = get_analytics_warehouse_status()
    quality = _load_json_file(BASE_DIR / "logs" / "data_quality_report.json") or {}
    pipeline = _load_json_file(DATA_PLATFORM_PIPELINE_REPORT_FILE) or {}

    promotion_layers = (promotion or {}).get("layers") or {}
    lake_ready = (
        bool(snapshot)
        and (promotion_layers.get("silver") or {}).get("status") == "published"
        and (promotion_layers.get("gold") or {}).get("status") == "published"
    )
    analytics_ready = (analytics.get("latest_report") or {}).get("status") == "PASS"
    quality_ready = bool(quality) and int(((quality.get("summary") or {}).get("failed")) or 0) == 0
    pipeline_ready = pipeline.get("status") == "PASS"

    return {
        "configured": True,
        "status": "ready" if all([lake_ready, analytics_ready, quality_ready, pipeline_ready]) else "attention",
        "readiness": {
            "lake_ready": lake_ready,
            "analytics_ready": analytics_ready,
            "quality_ready": quality_ready,
            "pipeline_ready": pipeline_ready,
        },
        "latest_snapshot": snapshot,
        "latest_promotion": promotion,
        "analytics": analytics,
        "quality": {
            "report_file": str(BASE_DIR / "logs" / "data_quality_report.json"),
            "latest_report": quality,
        },
        "pipeline": {
            "report_file": str(DATA_PLATFORM_PIPELINE_REPORT_FILE),
            "latest_report": pipeline,
        },
    }


def _model_to_dict(payload):
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    if hasattr(payload, "dict"):
        return payload.dict()
    return dict(payload)


def _parse_checklist_summary(output: str) -> dict:
    summary = {"checks_ok": None, "checks_total": None, "checks_ko": None}
    ok_match = re.search(r"Checks OK:\s*(\d+)/(\d+)", output)
    ko_match = re.search(r"Checks KO:\s*(\d+)", output)
    if ok_match:
        summary["checks_ok"] = int(ok_match.group(1))
        summary["checks_total"] = int(ok_match.group(2))
    if ko_match:
        summary["checks_ko"] = int(ko_match.group(1))
    return summary


async def _run_platform_readiness_presentation_test() -> dict:
    script = BASE_DIR / "scripts" / "checklist_and_launch.sh"
    process = await asyncio.to_thread(run_command_capture, ["bash", str(script)], 240)
    response = _parse_checklist_summary(process.get("stdout", ""))
    passed = process.get("returncode") == 0 and int(response.get("checks_ko") or 0) == 0
    highlights = []
    if response.get("checks_ok") is not None and response.get("checks_total") is not None:
        highlights.append(f"{response['checks_ok']}/{response['checks_total']} checks OK")
    if response.get("checks_ko") is not None:
        highlights.append(f"{response['checks_ko']} KO")
    highlights.append("API 8000 + dashboards 7600 verifies")
    return {
        "status": "ok" if passed else "error",
        "message": "La plateforme locale est disponible." if passed else "La checklist plateforme remonte des ecarts.",
        "async_job": False,
        "passed": passed,
        "highlights": highlights,
        "resources": response,
        "response": response,
        "process": {
            "returncode": process.get("returncode"),
            "timed_out": process.get("timed_out"),
            "duration_seconds": process.get("duration_seconds"),
            "stdout_tail": process.get("stdout_tail"),
            "stderr_tail": process.get("stderr_tail"),
        },
    }


async def _run_global_validation_presentation_test() -> dict:
    script = BASE_DIR / "scripts" / "run_perfect_compliance.sh"
    process = await asyncio.to_thread(run_command_capture, ["bash", str(script)], 1200)
    sujet1_report = _load_json_file(BASE_DIR / "logs" / "sujet1_validation_report.json") or {}
    perfect_report = _load_json_file(BASE_DIR / "logs" / "perfect_compliance_report.json") or {}
    db_load_report = _load_json_file(BASE_DIR / "logs" / "db_load_test_report.json") or {}
    resilience_report = _load_json_file(BASE_DIR / "logs" / "resilience_failover_report.json") or {}

    sujet1_summary = sujet1_report.get("summary") or {}
    perfect_summary = perfect_report.get("summary") or {}
    passed = (
        process.get("returncode") == 0
        and sujet1_summary.get("global_status") == "PASS"
        and perfect_summary.get("global_status") == "PASS"
    )
    highlights = [
        f"Sujet 1: {sujet1_summary.get('global_status', 'n/a')} {sujet1_summary.get('passed', 0)}/{sujet1_summary.get('requirements_total', 0)}",
        f"Conformite: {perfect_summary.get('global_status', 'n/a')} {perfect_summary.get('passed', 0)}/{perfect_summary.get('total', 0)}",
        f"Charge DB: {db_load_report.get('status', 'n/a')}",
        f"Resilience: {resilience_report.get('status', 'n/a')}",
    ]
    return {
        "status": "ok" if passed else "error",
        "message": "La validation complete est au vert." if passed else "La validation complete remonte au moins un ecart.",
        "async_job": False,
        "passed": passed,
        "highlights": highlights,
        "resources": {
            "sujet1_summary": sujet1_summary,
            "perfect_summary": perfect_summary,
            "db_load_status": db_load_report.get("status"),
            "resilience_status": resilience_report.get("status"),
        },
        "response": {
            "sujet1_report": sujet1_report,
            "perfect_report": perfect_report,
            "db_load_report": db_load_report,
            "resilience_report": resilience_report,
        },
        "process": {
            "returncode": process.get("returncode"),
            "timed_out": process.get("timed_out"),
            "duration_seconds": process.get("duration_seconds"),
            "stdout_tail": process.get("stdout_tail"),
            "stderr_tail": process.get("stderr_tail"),
        },
    }


async def _run_core_use_cases_presentation_test() -> dict:
    use_case_keys = [
        "minor-adult-checkout",
        "adult-adult-checkout",
        "identity-verification",
        "high-risk-alert",
    ]
    results = []
    for key in use_case_keys:
        results.append(await execute_use_case(key))
    passed = all(bool(item.get("passed")) for item in results)
    highlights = [
        f"{item.get('title')}: {'OK' if item.get('passed') else 'KO'}"
        for item in results
    ]
    return {
        "status": "ok" if passed else "error",
        "message": "Les cas metier critiques ont ete rejoues." if passed else "Au moins un cas metier n'a pas passe.",
        "async_job": False,
        "passed": passed,
        "highlights": highlights,
        "resources": {
            "cases": [
                {
                    "key": item.get("use_case_key"),
                    "title": item.get("title"),
                    "passed": item.get("passed"),
                    "outcome": item.get("outcome"),
                    "http_status": item.get("http_status"),
                }
                for item in results
            ]
        },
        "response": {"results": results},
        "process": None,
    }


async def _run_notifications_workflow_presentation_test(recipient_email: Optional[str]) -> dict:
    recipient = (
        (recipient_email or "").strip()
        or (load_alert_notification_settings().get("recipient_email") or "").strip()
        or "ops@kivendtout.fr"
    )
    if not _validate_email(recipient):
        raise HTTPException(status_code=400, detail="recipient_email invalide")

    config = load_alert_notification_settings()
    config.update({
        "enabled": True,
        "recipient_email": recipient,
        "min_severity": "HIGH",
        "notify_on_new_alert": True,
        "notify_on_decision": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": recipient,
    })
    save_alert_notification_settings(config)

    alert = await simulate_alert(AlertSimulationRequest(
        severity="HIGH",
        risk_score=92,
        status="PENDING_REVIEW",
        fraud_reasons=["VELOCITY_HIGH", "NEW_DEVICE"],
        customer_id="C00999",
        customer_country="FR",
        device="desktop",
    ))
    manual = await notify_alert(
        alert.alert_id,
        AlertNotificationTestRequest(
            recipient_email=recipient,
            message="Escalade manuelle de validation",
            updated_by=recipient,
        ),
    )
    decision = await decide_alert(
        alert.alert_id,
        AlertDecision(
            decision="INVESTIGATE",
            decided_by=recipient,
            notes="Escalade automatique pour revue analyste",
        ),
    )
    history = [
        item for item in list_alert_notification_history(limit=12)
        if item.get("alert_id") == alert.alert_id
    ]
    seen_events = [item.get("event_type") for item in history]
    passed = {"new_alert", "manual", "decision"}.issubset(set(seen_events))
    delivery_mode = alert_notification_delivery_mode(config)
    return {
        "status": "ok" if passed else "error",
        "message": "Le workflow de notification est trace de bout en bout." if passed else "Le workflow de notification est incomplet.",
        "async_job": False,
        "passed": passed,
        "highlights": [
            f"Destinataire: {recipient}",
            f"Mode: {delivery_mode}",
            f"Evenements: {', '.join(seen_events) if seen_events else 'aucun'}",
        ],
        "resources": {
            "alert_id": alert.alert_id,
            "recipient_email": recipient,
            "delivery_mode": delivery_mode,
        },
        "response": {
            "config": config,
            "alert": json.loads(alert.model_dump_json()),
            "manual": manual,
            "decision": decision,
            "history": history,
        },
        "process": None,
    }


async def _run_micro_batch_presentation_test() -> dict:
    runtime = await asyncio.to_thread(
        _run_micro_batch_job,
        MicroBatchRunRequest(mode="once", window_seconds=30, bootstrap_minutes=10, poll_interval=1.0, duration_seconds=120),
    )
    stats = await get_micro_batch_stats(window_hours=24, limit=20)
    latest_window = (stats.get("recent_windows") or [None])[0] or {}
    total_events = int(latest_window.get("total_events") or 0)
    speed = float(latest_window.get("speed_events_per_sec") or 0.0)
    latency = float(latest_window.get("latency_ms") or 0.0)
    passed = runtime.get("returncode") in (0, None) and total_events > 0 and speed > 0
    return {
        "status": "ok" if passed else "error",
        "message": "Une fenetre micro-batch a ete traitee." if passed else "Le micro-batch n'a pas produit de fenetre exploitable.",
        "async_job": False,
        "passed": passed,
        "highlights": [
            f"Events: {total_events}",
            f"Latence: {round(latency, 2)} ms",
            f"Debit: {round(speed, 2)} evt/s",
        ],
        "resources": {
            "total_events": total_events,
            "latency_ms": round(latency, 2),
            "speed_events_per_sec": round(speed, 2),
            "latest_batch_ended_at": latest_window.get("batch_ended_at"),
        },
        "response": {
            "runtime": runtime,
            "stats": stats,
        },
        "process": {
            "returncode": runtime.get("returncode"),
            "duration_seconds": runtime.get("duration_seconds"),
            "output_lines": runtime.get("output_lines"),
        },
    }


async def _run_data_lake_pipeline_presentation_test() -> dict:
    snapshot = await asyncio.to_thread(
        run_command_capture,
        ["bash", str(BASE_DIR / "scripts" / "snapshot_raw_data_to_minio.sh")],
        300,
    )
    pipeline = await asyncio.to_thread(run_data_lake_promotion_pipeline)
    status_payload = await get_data_lake_status(limit_reports=3)
    latest_report = status_payload.get("latest_report") or {}
    layers = latest_report.get("layers") or {}
    passed = (
        snapshot.get("returncode") == 0
        and pipeline.get("returncode") == 0
        and bool(layers)
    )
    highlights = [
        f"Bronze snapshot: {'OK' if snapshot.get('returncode') == 0 else 'KO'}",
        f"Silver objets: {((layers.get('silver') or {}).get('objects_count') or 0)}",
        f"Gold objets: {((layers.get('gold') or {}).get('objects_count') or 0)}",
    ]
    return {
        "status": "ok" if passed else "error",
        "message": "Le pipeline Data Lake a publie les couches silver et gold." if passed else "Le pipeline Data Lake n'a pas abouti.",
        "async_job": False,
        "passed": passed,
        "highlights": highlights,
        "resources": {
            "layers": layers,
            "report_file": latest_report.get("report_file"),
        },
        "response": {
            "snapshot": snapshot,
            "promotion": pipeline,
            "status": status_payload,
        },
        "process": {
            "snapshot_returncode": snapshot.get("returncode"),
            "promotion_returncode": pipeline.get("returncode"),
            "snapshot_stdout_tail": snapshot.get("stdout_tail"),
            "promotion_stdout_tail": pipeline.get("stdout_tail"),
            "promotion_stderr_tail": pipeline.get("stderr_tail"),
        },
    }


async def _run_analytics_warehouse_presentation_test() -> dict:
    pipeline = await asyncio.to_thread(run_analytics_warehouse_pipeline)
    status_payload = get_analytics_warehouse_status()
    report = pipeline.get("report") or {}
    datamarts = report.get("datamarts") or {}
    passed = pipeline.get("returncode") == 0 and bool(datamarts)
    return {
        "status": "ok" if passed else "error",
        "message": "Le schema analytics et les datamarts ont ete construits." if passed else "Le schema analytics n'a pas pu etre construit.",
        "async_job": False,
        "passed": passed,
        "highlights": [
            f"Dimensions: {sum((report.get('dimensions') or {}).values()) if report.get('dimensions') else 0}",
            f"Facts: {sum((report.get('facts') or {}).values()) if report.get('facts') else 0}",
            f"Datamarts: {sum(datamarts.values()) if datamarts else 0}",
        ],
        "resources": status_payload,
        "response": {
            "build": pipeline,
            "status": status_payload,
        },
        "process": {
            "returncode": pipeline.get("returncode"),
            "stdout_tail": pipeline.get("stdout_tail"),
            "stderr_tail": pipeline.get("stderr_tail"),
        },
    }


async def _run_live_payments_presentation_test() -> dict:
    before = _model_to_dict(await get_payment_stats(window_hours=24))
    result = await execute_data_factory_action("payments-live-3m")
    runtime_state = snapshot_live_runtime_state().get("orders") or {}
    passed = result.get("status") == "started" and bool(result.get("passed"))
    return {
        "status": result.get("status"),
        "message": result.get("message"),
        "async_job": True,
        "passed": passed,
        "highlights": [
            f"Fraud rate avant: {before.get('fraud_rate', 0)}%",
            f"Paiements 24h avant: {before.get('total_payments', 0)}",
            "Observer Fraude + Transferts pendant 3 min",
        ],
        "resources": {
            "baseline_payments": before,
            "expected_end_at": runtime_state.get("expected_end_at"),
            "risk_profile": runtime_state.get("risk_profile"),
        },
        "response": result,
        "process": result.get("process"),
    }


async def _run_massive_fraud_orders_presentation_test() -> dict:
    payments_before = _model_to_dict(await get_payment_stats(window_hours=24))
    checkout_before = _model_to_dict(await get_checkout_stats(window_hours=24))
    result = await execute_data_factory_action("massive-fraud-orders-3m")
    runtime_state = result.get("response") or {}
    passed = result.get("status") == "started" and bool(result.get("passed"))
    return {
        "status": result.get("status"),
        "message": result.get("message"),
        "async_job": True,
        "passed": passed,
        "highlights": [
            f"Fraud rate avant: {payments_before.get('fraud_rate', 0)}%",
            f"Blocages mineurs avant: {checkout_before.get('blocked_underage_orders', 0)}",
            "Observer Fraude + Identite + Typologies pendant 3 min",
        ],
        "resources": {
            "baseline_payments": payments_before,
            "baseline_checkout": checkout_before,
            "runtime_state": runtime_state.get("runtime_state"),
        },
        "response": result,
        "process": result.get("process"),
    }


async def execute_presentation_test(test_key: str, recipient_email: Optional[str] = None) -> dict:
    started_at = datetime.now(timezone.utc)
    if not PRESENTATION_TEST_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Un autre test de presentation est deja en cours.")
    try:
        if test_key == "platform-readiness":
            result = await _run_platform_readiness_presentation_test()
        elif test_key == "global-validation":
            result = await _run_global_validation_presentation_test()
        elif test_key == "core-use-cases":
            result = await _run_core_use_cases_presentation_test()
        elif test_key == "notifications-workflow":
            result = await _run_notifications_workflow_presentation_test(recipient_email)
        elif test_key == "micro-batch-once":
            result = await _run_micro_batch_presentation_test()
        elif test_key == "data-lake-pipeline":
            result = await _run_data_lake_pipeline_presentation_test()
        elif test_key == "analytics-warehouse":
            result = await _run_analytics_warehouse_presentation_test()
        elif test_key == "payments-live-3m":
            result = await _run_live_payments_presentation_test()
        elif test_key == "massive-fraud-orders-episode":
            result = await _run_massive_fraud_orders_presentation_test()
        else:
            raise HTTPException(status_code=404, detail=f"Unknown presentation test: {test_key}")
    finally:
        PRESENTATION_TEST_LOCK.release()

    completed_at = datetime.now(timezone.utc)
    definition = PRESENTATION_TEST_DEFINITIONS[test_key]
    history_entry = {
        "test_key": test_key,
        "title": definition["title"],
        "category": definition["category"],
        "timestamp": completed_at.isoformat(),
        "duration_ms": round((completed_at - started_at).total_seconds() * 1000.0, 2),
        "status": result.get("status"),
        "message": result.get("message"),
        "async_job": bool(result.get("async_job")),
        "passed": result.get("passed"),
        "highlights": result.get("highlights") or [],
        "resources": result.get("resources"),
        "response": result.get("response"),
        "process": result.get("process"),
    }
    append_presentation_test_history(history_entry)
    return {
        "definition": definition,
        **history_entry,
    }


def build_alert_notification_payload(event_type: str, alert: dict, actor: Optional[str] = None, message: Optional[str] = None) -> Tuple[str, str]:
    event_label = {
        "new_alert": "Nouvelle alerte",
        "decision": "Decision alerte",
        "test": "Test notification",
        "manual": "Notification manuelle",
    }.get(event_type, "Notification alerte")
    reasons = ", ".join(alert.get("fraud_reasons") or []) or "n/a"
    subject = f"[KiVendTout] {event_label} {alert.get('severity', 'INFO')} {alert.get('alert_id', 'ALERTE')}"
    body_lines = [
        f"Type: {event_label}",
        f"Alerte: {alert.get('alert_id', '-')}",
        f"Severite: {alert.get('severity', '-')}",
        f"Score de risque: {alert.get('risk_score', '-')}",
        f"Statut: {alert.get('status', '-')}",
        f"Client: {alert.get('customer_id', '-')}",
        f"Session: {alert.get('session_id', '-')}",
        f"Pays: {alert.get('customer_country', '-')}",
        f"Appareil: {alert.get('device', '-')}",
        f"Motifs: {reasons}",
        f"Date alerte: {alert.get('alert_timestamp', '-')}",
    ]
    if actor:
        body_lines.append(f"Acteur: {actor}")
    if message:
        body_lines.append(f"Message: {message}")
    body_lines.extend(
        [
            "",
            "Action recommandee:",
            "- Ouvrir le dashboard fraude pour confirmer la decision",
            "- Verifier le contexte client et la recurrence des motifs",
            "- Bloquer ou investiguer si le score et la severite sont eleves",
        ]
    )
    return subject, "\n".join(body_lines)


def deliver_alert_notification(recipient_email: str, subject: str, body: str) -> dict:
    ALERT_NOTIFICATION_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    preview_file = ALERT_NOTIFICATION_PREVIEW_DIR / f"notification_{timestamp}_{uuid4().hex[:8]}.txt"
    preview_file.write_text(f"To: {recipient_email}\nSubject: {subject}\n\n{body}\n", encoding="utf-8")

    smtp = smtp_notification_settings()
    if not smtp.get("host"):
        return {
            "status": "preview",
            "delivery_mode": "preview",
            "preview_file": str(preview_file),
            "sender_email": smtp.get("from_email"),
        }

    message = EmailMessage()
    message["From"] = smtp["from_email"]
    message["To"] = recipient_email
    message["Subject"] = subject
    message.set_content(body)

    if smtp.get("use_ssl"):
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp["host"], smtp["port"], context=context, timeout=10) as server:
            if smtp.get("username"):
                server.login(smtp["username"], smtp.get("password") or "")
            server.send_message(message)
    else:
        with smtplib.SMTP(smtp["host"], smtp["port"], timeout=10) as server:
            if smtp.get("use_starttls"):
                context = ssl.create_default_context()
                server.starttls(context=context)
            if smtp.get("username"):
                server.login(smtp["username"], smtp.get("password") or "")
            server.send_message(message)

    return {
        "status": "sent",
        "delivery_mode": "smtp",
        "preview_file": str(preview_file),
        "sender_email": smtp.get("from_email"),
    }


def notify_alert_event(event_type: str, alert: dict, actor: Optional[str] = None, message: Optional[str] = None, recipient_override: Optional[str] = None) -> dict:
    config = load_alert_notification_settings()
    recipient_email = (recipient_override or config.get("recipient_email") or "").strip()
    if not _validate_email(recipient_email):
        raise ValueError("recipient_email invalide")

    if event_type == "new_alert":
        if not config.get("notify_on_new_alert", True):
            raise ValueError("notifications nouvelles alertes desactivees")
        if _severity_rank(alert.get("severity")) < _severity_rank(config.get("min_severity")):
            raise ValueError("alerte sous le seuil de severite")
    elif event_type == "decision":
        if not config.get("notify_on_decision", False):
            raise ValueError("notifications de decision desactivees")

    subject, body = build_alert_notification_payload(event_type, alert, actor=actor, message=message)
    delivery = deliver_alert_notification(recipient_email, subject, body)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "recipient_email": recipient_email,
        "alert_id": alert.get("alert_id"),
        "severity": alert.get("severity"),
        "risk_score": int(alert.get("risk_score", 0) or 0),
        "status": delivery.get("status"),
        "delivery_mode": delivery.get("delivery_mode"),
        "sender_email": delivery.get("sender_email"),
        "preview_file": delivery.get("preview_file"),
        "subject": subject,
        "actor": actor,
        "message": message,
    }
    append_alert_notification_history(entry)
    return entry


def get_db_connection():
    """Connexion PostgreSQL"""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "kivendtout"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres")
    )

def load_id_labels():
    """
    Charge le mapping fichier ID -> date de naissance.
    Source: synthetic_id_labels.csv associé aux synthetic_id_cards/*.png.
    """
    global ID_LABELS_CACHE
    if ID_LABELS_CACHE is not None:
        return ID_LABELS_CACHE

    records = load_id_label_records()
    ID_LABELS_CACHE = {file_name: row["birthdate"] for file_name, row in records.items()}
    return ID_LABELS_CACHE


def load_id_label_records():
    """
    Charge les métadonnées complètes des CNI synthétiques.
    Source: synthetic_id_labels.csv associé aux synthetic_id_cards/*.png.
    """
    global ID_LABEL_RECORDS_CACHE
    if ID_LABEL_RECORDS_CACHE is not None:
        return ID_LABEL_RECORDS_CACHE

    if not ID_LABELS_FILE.exists():
        raise RuntimeError(f"Fichier labels introuvable: {ID_LABELS_FILE}")

    cache = {}
    with ID_LABELS_FILE.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            file_name = (row.get("file") or "").strip()
            birthdate = (row.get("birthdate") or "").strip()
            if not file_name or not birthdate:
                continue
            cache[file_name] = {
                "file": file_name,
                "first_name": (row.get("first_name") or "").strip() or None,
                "last_name": (row.get("last_name") or "").strip() or None,
                "sex": (row.get("sex") or "").strip() or None,
                "birthdate": birthdate,
                "doc_number": (row.get("doc_number") or "").strip() or None,
                "expiry": (row.get("expiry") or "").strip() or None,
                "is_adult": (row.get("is_adult") or "").strip() in {"1", "true", "True"},
            }

    ID_LABEL_RECORDS_CACHE = cache
    return ID_LABEL_RECORDS_CACHE


def load_id_fingerprint_model():
    """
    Charge le modèle de reconnaissance d'image basé empreinte SHA-256.
    Format attendu:
    {
      "model_type": "sha256_fingerprint_lookup",
      "hash_to_birthdate": {"<sha256>": "YYYY-MM-DD", ...}
    }
    """
    global ID_FINGERPRINT_MODEL_CACHE
    if ID_FINGERPRINT_MODEL_CACHE is not None:
        return ID_FINGERPRINT_MODEL_CACHE

    if not ID_FINGERPRINT_MODEL_FILE.exists():
        ID_FINGERPRINT_MODEL_CACHE = {}
        return ID_FINGERPRINT_MODEL_CACHE

    try:
        with ID_FINGERPRINT_MODEL_FILE.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        hash_to_birthdate = payload.get("hash_to_birthdate", {})
        if not isinstance(hash_to_birthdate, dict):
            hash_to_birthdate = {}
        ID_FINGERPRINT_MODEL_CACHE = {
            "model_type": payload.get("model_type", "sha256_fingerprint_lookup"),
            "version": payload.get("version", "unknown"),
            "trained_at": payload.get("trained_at"),
            "hash_to_birthdate": hash_to_birthdate,
            "records": len(hash_to_birthdate),
        }
        return ID_FINGERPRINT_MODEL_CACHE
    except Exception as e:
        print(f"Erreur chargement modèle empreinte CNI: {e}")
        ID_FINGERPRINT_MODEL_CACHE = {}
        return ID_FINGERPRINT_MODEL_CACHE


def predict_birthdate_from_id_fingerprint(card_path: Path) -> Optional[str]:
    model = load_id_fingerprint_model()
    if not model:
        return None
    hash_to_birthdate = model.get("hash_to_birthdate", {})
    if not hash_to_birthdate:
        return None

    digest = hashlib.sha256(card_path.read_bytes()).hexdigest()
    return hash_to_birthdate.get(digest)

def compute_age(birthdate_str: str) -> int:
    birth = datetime.strptime(birthdate_str, "%Y-%m-%d").date()
    today = date.today()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def is_expired_document(expiry_str: Optional[str]) -> bool:
    if not expiry_str:
        return False
    try:
        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    except ValueError:
        return False
    return expiry_date < date.today()

def extract_age_from_id_card(id_card_file: str):
    """
    Retourne (file_name, birthdate_str, age) pour une carte d'identité synthétique.
    """
    safe_name = Path(id_card_file).name
    card_path = ID_CARDS_DIR / safe_name
    if not card_path.exists():
        raise HTTPException(status_code=404, detail=f"ID card not found: {safe_name}")

    birthdate_str = None
    model_enabled = os.getenv("ID_CARD_MODEL_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    if model_enabled:
        try:
            birthdate_str = predict_birthdate_from_id_fingerprint(card_path)
        except Exception as e:
            print(f"Erreur reconnaissance image CNI (fallback labels): {e}")

    if not birthdate_str:
        labels = load_id_labels()
        birthdate_str = labels.get(safe_name)

    if not birthdate_str:
        raise HTTPException(
            status_code=400,
            detail=f"No birthdate found via model or labels for card: {safe_name}"
        )

    age = compute_age(birthdate_str)
    return safe_name, birthdate_str, age

def is_adult_restricted(category: Optional[str]) -> bool:
    return (category or "").strip().lower() == "adult"


def select_demo_id_card(adult_required: bool) -> dict:
    labels = load_id_labels()
    candidates = []
    for file_name, birthdate in labels.items():
        age = compute_age(birthdate)
        is_adult = age >= 18
        if is_adult != adult_required:
            continue
        candidates.append({
            "file": file_name,
            "birthdate": birthdate,
            "age": age,
            "is_adult": is_adult,
            "image_url": f"/api/id-cards/image/{Path(file_name).name}",
        })
    if not candidates:
        raise HTTPException(status_code=404, detail="No matching synthetic ID card found")
    candidates.sort(key=lambda item: (item["age"], item["file"]))
    return candidates[-1] if adult_required else candidates[0]


def select_demo_customer_id(cursor) -> str:
    cursor.execute("SELECT customer_id FROM customers ORDER BY customer_id LIMIT 1")
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No customer found")
    return row[0]


def ensure_demo_catalog_stock(
    cursor,
    min_adult_products: int = 3,
    min_non_adult_products: int = 20,
    adult_floor_stock: int = 60,
    non_adult_floor_stock: int = 25,
) -> dict:
    """
    Reconstitue un stock minimum pour les scenarios de demo et de streaming.
    Evite qu'un run precedent epuise completement le catalogue Adult.
    """
    cursor.execute("""
        SELECT
            COUNT(*) FILTER (WHERE LOWER(category) = 'adult' AND stock_quantity > 0)::INT,
            COUNT(*) FILTER (WHERE (category IS NULL OR LOWER(category) <> 'adult') AND stock_quantity > 0)::INT
        FROM products
    """)
    adult_in_stock, non_adult_in_stock = cursor.fetchone()
    restocked = {
        "adult_in_stock": int(adult_in_stock or 0),
        "non_adult_in_stock": int(non_adult_in_stock or 0),
        "adult_restocked": False,
        "non_adult_restocked": False,
    }

    if restocked["adult_in_stock"] < min_adult_products:
        cursor.execute("""
            UPDATE products
            SET stock_quantity = GREATEST(stock_quantity, %s)
            WHERE LOWER(category) = 'adult'
        """, (adult_floor_stock,))
        restocked["adult_restocked"] = cursor.rowcount > 0

    if restocked["non_adult_in_stock"] < min_non_adult_products:
        cursor.execute("""
            UPDATE products
            SET stock_quantity = GREATEST(stock_quantity, %s)
            WHERE category IS NULL OR LOWER(category) <> 'adult'
        """, (non_adult_floor_stock,))
        restocked["non_adult_restocked"] = cursor.rowcount > 0

    cursor.execute("""
        SELECT
            COUNT(*) FILTER (WHERE LOWER(category) = 'adult' AND stock_quantity > 0)::INT,
            COUNT(*) FILTER (WHERE (category IS NULL OR LOWER(category) <> 'adult') AND stock_quantity > 0)::INT
        FROM products
    """)
    adult_after, non_adult_after = cursor.fetchone()
    restocked["adult_in_stock_after"] = int(adult_after or 0)
    restocked["non_adult_in_stock_after"] = int(non_adult_after or 0)
    return restocked


def select_demo_product(cursor, adult_required: bool, only_in_stock: bool = True) -> dict:
    if only_in_stock:
        stock_state = ensure_demo_catalog_stock(cursor)
        if stock_state.get("adult_restocked") or stock_state.get("non_adult_restocked"):
            cursor.connection.commit()

    query = """
        SELECT product_id, name, category, price, stock_quantity
        FROM products
        WHERE 1=1
    """
    params = []
    if adult_required:
        query += " AND LOWER(category) = 'adult'"
    else:
        query += " AND (category IS NULL OR LOWER(category) <> 'adult')"
    if only_in_stock:
        query += " AND stock_quantity > 0"
    query += " ORDER BY stock_quantity DESC, product_id ASC LIMIT 1"
    cursor.execute(query, params)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No matching product found")
    return {
        "product_id": int(row[0]),
        "name": row[1],
        "category": row[2],
        "price": float(row[3]),
        "stock_quantity": int(row[4]),
        "is_adult_restricted": is_adult_restricted(row[2]),
    }

def get_or_create_customer_address(cursor, customer_id: str) -> int:
    cursor.execute("""
        SELECT address_id
        FROM addresses
        WHERE customer_id = %s
        ORDER BY address_id
        LIMIT 1
    """, (customer_id,))
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute("SELECT country FROM customers WHERE customer_id = %s", (customer_id,))
    customer = cursor.fetchone()
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer not found: {customer_id}")

    country = customer[0] or "FR"
    cursor.execute("""
        INSERT INTO addresses (customer_id, street, city, postal_code, country, address_type, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING address_id
    """, (
        customer_id,
        "1 Rue du Commerce",
        "Paris",
        "75001",
        country,
        "both",
        datetime.now()
    ))
    return cursor.fetchone()[0]

def init_fraud_alerts_table():
    """
    Crée la table fraud_alerts si elle n'existe pas
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Migration défensive: si une ancienne table fraud_alerts existe avec
    # le schéma dataset (sans alert_timestamp), on la renomme.
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'fraud_alerts'
    """)
    existing_columns = {row[0] for row in cursor.fetchall()}
    if existing_columns and 'alert_timestamp' not in existing_columns:
        cursor.execute("SELECT to_regclass('public.fraud_alerts_legacy')")
        if cursor.fetchone()[0] is not None:
            cursor.execute("DROP TABLE fraud_alerts_legacy")
        cursor.execute("ALTER TABLE fraud_alerts RENAME TO fraud_alerts_legacy")
        print("⚠️ Ancienne table fraud_alerts renommée en fraud_alerts_legacy")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fraud_alerts (
            alert_id VARCHAR(100) PRIMARY KEY,
            alert_timestamp TIMESTAMP NOT NULL,
            event_timestamp TIMESTAMP,
            customer_id VARCHAR(20),
            session_id VARCHAR(50),
            event_type VARCHAR(50),
            device VARCHAR(50),
            utm_source VARCHAR(50),
            customer_country VARCHAR(10),
            previous_payments INT,
            is_new_customer BOOLEAN,
            fraud_reasons TEXT,
            risk_score INT,
            status VARCHAR(20) DEFAULT 'PENDING_REVIEW',
            severity VARCHAR(10),
            decision VARCHAR(20),
            decided_at TIMESTAMP,
            decided_by VARCHAR(100),
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_fraud_alerts_status ON fraud_alerts(status);
        CREATE INDEX IF NOT EXISTS idx_fraud_alerts_severity ON fraud_alerts(severity);
        CREATE INDEX IF NOT EXISTS idx_fraud_alerts_customer ON fraud_alerts(customer_id);
        CREATE INDEX IF NOT EXISTS idx_fraud_alerts_timestamp ON fraud_alerts(alert_timestamp);
    """)
    
    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Table fraud_alerts initialisée")

def init_identity_verifications_table():
    """Crée la table identity_verifications si elle n'existe pas."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS identity_verifications (
            verification_id SERIAL PRIMARY KEY,
            customer_id VARCHAR(50) NOT NULL,
            verification_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            document_type VARCHAR(50),
            document_number VARCHAR(100),
            verification_status VARCHAR(50),
            verification_method VARCHAR(50),
            id_card_image_path VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_identity_verif_customer ON identity_verifications(customer_id);
        CREATE INDEX IF NOT EXISTS idx_identity_verif_status ON identity_verifications(verification_status);
        CREATE INDEX IF NOT EXISTS idx_identity_verif_created_at ON identity_verifications(created_at);
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Table identity_verifications initialisée")

def init_checkout_attempts_table():
    """Crée la table d'audit des tentatives de checkout API."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS checkout_attempts (
            attempt_id BIGSERIAL PRIMARY KEY,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            customer_id VARCHAR(50),
            id_card_file VARCHAR(100),
            customer_age INT,
            contains_adult_product BOOLEAN DEFAULT FALSE,
            blocked_underage BOOLEAN DEFAULT FALSE,
            accepted BOOLEAN DEFAULT FALSE,
            blocked_products TEXT,
            total_amount NUMERIC(10, 2),
            order_id INTEGER,
            notes TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_checkout_attempts_ts ON checkout_attempts(attempted_at);
        CREATE INDEX IF NOT EXISTS idx_checkout_attempts_blocked ON checkout_attempts(blocked_underage);
        CREATE INDEX IF NOT EXISTS idx_checkout_attempts_accepted ON checkout_attempts(accepted);
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Table checkout_attempts initialisée")

def init_micro_batch_metrics_table():
    """Crée la table des métriques micro-batch MongoDB -> PostgreSQL."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS micro_batch_event_metrics (
            batch_metric_id BIGSERIAL PRIMARY KEY,
            batch_started_at TIMESTAMP NOT NULL,
            batch_ended_at TIMESTAMP NOT NULL,
            event_type VARCHAR(80) NOT NULL,
            events_count INT NOT NULL,
            latency_ms DOUBLE PRECISION NOT NULL,
            speed_events_per_sec DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (batch_started_at, batch_ended_at, event_type)
        );

        CREATE INDEX IF NOT EXISTS idx_micro_batch_metrics_end ON micro_batch_event_metrics(batch_ended_at DESC);
        CREATE INDEX IF NOT EXISTS idx_micro_batch_metrics_event_type ON micro_batch_event_metrics(event_type);
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Table micro_batch_event_metrics initialisée")


def ensure_orders_manual_review_status():
    """Autorise le statut manual_review pour les commandes payées à risque."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conname = 'orders_status_check'
              AND conrelid = 'orders'::regclass
            """
        )
        row = cursor.fetchone()
        constraint_def = (row[0] or "") if row else ""
        if "manual_review" in constraint_def:
            return

        cursor.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_status_check")
        cursor.execute(
            """
            ALTER TABLE orders
            ADD CONSTRAINT orders_status_check
            CHECK (status IN ('pending', 'paid', 'cancelled', 'processing', 'shipped', 'manual_review'))
            """
        )
        conn.commit()
        print("✅ Contrainte orders_status_check alignée")
    finally:
        cursor.close()
        conn.close()

def load_transfer_kpi_history(limit: int = 200) -> List[dict]:
    """
    Charge l'historique JSONL des KPI transfert normalisés.
    Ex: snapshot Data Lake et micro-batch Mongo->Postgres.
    """
    if not TRANSFER_KPI_HISTORY_FILE.exists():
        return []

    rows = []
    try:
        with TRANSFER_KPI_HISTORY_FILE.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows.append(row)
    except Exception as e:
        print(f"Erreur lecture historique KPI transfert: {e}")
        return []

    if limit <= 0:
        return rows
    return rows[-limit:]


def _parse_transfer_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _metric_family(metric: str) -> str:
    if metric == "data_lake_snapshot":
        return "snapshot"
    if metric in {"data_lake_silver", "data_lake_gold"}:
        return "lake_promotion"
    if metric == "micro_batch_events":
        return "micro_batch"
    return "other"


def _metric_rank(metric: str) -> int:
    family = _metric_family(metric)
    return {"snapshot": 1, "lake_promotion": 2, "micro_batch": 3}.get(family, 99)


def _metric_label(metric: str) -> str:
    return {
        "data_lake_snapshot": "Snapshot bronze",
        "data_lake_silver": "Promotion silver",
        "data_lake_gold": "Publication gold",
        "micro_batch_events": "Micro-batch",
    }.get(metric, metric)

def normalize_transfer_metric(row: dict) -> dict:
    """
    Uniformise les KPI transfert en triplet:
    - latency_value + latency_unit
    - capacity_value + capacity_unit
    - speed_value + speed_unit
    """
    metric = str(row.get("metric", "unknown"))
    timestamp_utc = row.get("timestamp_utc")
    metric_family = _metric_family(metric)
    metric_rank = _metric_rank(metric)

    latency_value = None
    latency_unit = None
    latency_ms_normalized = None
    if row.get("latency_ms") is not None:
        latency_value = float(row.get("latency_ms"))
        latency_unit = "ms"
        latency_ms_normalized = float(row.get("latency_ms"))
    elif row.get("latency_seconds") is not None:
        latency_value = float(row.get("latency_seconds"))
        latency_unit = "s"
        latency_ms_normalized = float(row.get("latency_seconds")) * 1000.0

    capacity_value = None
    capacity_unit = None
    if row.get("capacity_bytes") is not None:
        capacity_value = float(row.get("capacity_bytes"))
        capacity_unit = "bytes"
    elif row.get("capacity_events") is not None:
        capacity_value = float(row.get("capacity_events"))
        capacity_unit = "events"
    elif row.get("capacity_files") is not None:
        capacity_value = float(row.get("capacity_files"))
        capacity_unit = "files"

    speed_value = None
    speed_unit = None
    if row.get("speed_bytes_per_second") is not None:
        speed_value = float(row.get("speed_bytes_per_second"))
        speed_unit = "bytes/s"
    elif row.get("speed_events_per_second") is not None:
        speed_value = float(row.get("speed_events_per_second"))
        speed_unit = "events/s"
    elif row.get("speed_files_per_second") is not None:
        speed_value = float(row.get("speed_files_per_second"))
        speed_unit = "files/s"

    return {
        "metric": metric,
        "metric_label": _metric_label(metric),
        "metric_family": metric_family,
        "metric_rank": metric_rank,
        "timestamp_utc": timestamp_utc,
        "latency_value": latency_value,
        "latency_unit": latency_unit,
        "latency_ms_normalized": latency_ms_normalized,
        "capacity_value": capacity_value,
        "capacity_unit": capacity_unit,
        "speed_value": speed_value,
        "speed_unit": speed_unit,
        "raw": row,
    }


def _safe_float(value, digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except Exception:
        return None


def _format_bytes_human(bytes_value: Optional[float]) -> Optional[str]:
    if bytes_value is None:
        return None
    try:
        value = float(bytes_value)
    except Exception:
        return None

    units = ["B", "KB", "MB", "GB", "TB"]
    unit_idx = 0
    while value >= 1024 and unit_idx < len(units) - 1:
        value /= 1024.0
        unit_idx += 1
    return f"{value:.2f} {units[unit_idx]}"


def _format_rate_human(value: Optional[float], unit: Optional[str]) -> Optional[str]:
    if value is None or not unit:
        return None
    if unit == "bytes/s":
        return f"{_format_bytes_human(value)}/s"
    if unit == "events/s":
        return f"{float(value):.2f} evt/s"
    if unit == "files/s":
        return f"{float(value):.2f} fichiers/s"
    return f"{float(value):.2f} {unit}"


def _format_capacity_human(value: Optional[float], unit: Optional[str], raw: Optional[dict] = None) -> Optional[str]:
    if value is None or not unit:
        return None
    if unit == "bytes":
        files = None if raw is None else raw.get("capacity_files")
        bytes_text = _format_bytes_human(value)
        if files is not None:
            return f"{int(files)} fichiers | {bytes_text}"
        return bytes_text
    if unit == "events":
        event_types = None if raw is None else raw.get("event_types_count")
        if event_types:
            return f"{int(value)} evt | {int(event_types)} type(s)"
        return f"{int(value)} evt"
    if unit == "files":
        return f"{int(value)} fichiers"
    return f"{float(value):.2f} {unit}"


def _transfer_status_from_thresholds(value: Optional[float], warning_threshold: float, danger_threshold: float, inverse: bool = False) -> str:
    if value is None:
        return "warning"
    if inverse:
        if value <= warning_threshold:
            return "success"
        if value <= danger_threshold:
            return "warning"
        return "danger"
    if value >= danger_threshold:
        return "success"
    if value >= warning_threshold:
        return "warning"
    return "danger"


def build_transfer_metric_summaries(normalized_rows: List[dict]) -> dict:
    grouped = defaultdict(list)
    for row in normalized_rows:
        grouped[row.get("metric", "unknown")].append(row)

    summaries = {}
    for metric, rows in grouped.items():
        rows_sorted = sorted(rows, key=lambda item: _parse_transfer_timestamp(item.get("timestamp_utc")) or datetime.min.replace(tzinfo=timezone.utc))
        latest = rows_sorted[-1]
        non_zero_rows = [
            row for row in rows_sorted
            if (row.get("capacity_value") or 0) > 0
        ]
        latest_active = non_zero_rows[-1] if non_zero_rows else latest

        latencies_ms = [row.get("latency_ms_normalized") for row in rows_sorted if row.get("latency_ms_normalized") is not None]
        speeds = [row.get("speed_value") for row in rows_sorted if row.get("speed_value") is not None]
        capacities = [row.get("capacity_value") for row in rows_sorted if row.get("capacity_value") is not None]

        raw_latest = latest.get("raw") or {}
        summaries[metric] = {
            "metric": metric,
            "label": latest.get("metric_label") or _metric_label(metric),
            "family": latest.get("metric_family") or _metric_family(metric),
            "rank": latest.get("metric_rank") or _metric_rank(metric),
            "points": len(rows_sorted),
            "latest_timestamp_utc": latest.get("timestamp_utc"),
            "latest_latency_ms": _safe_float(latest.get("latency_ms_normalized")),
            "latest_speed_value": _safe_float(latest.get("speed_value")),
            "latest_speed_unit": latest.get("speed_unit"),
            "latest_speed_human": _format_rate_human(latest.get("speed_value"), latest.get("speed_unit")),
            "latest_capacity_value": _safe_float(latest.get("capacity_value")),
            "latest_capacity_unit": latest.get("capacity_unit"),
            "latest_capacity_human": _format_capacity_human(latest.get("capacity_value"), latest.get("capacity_unit"), raw_latest),
            "latest_active_timestamp_utc": latest_active.get("timestamp_utc"),
            "latest_active_capacity_value": _safe_float(latest_active.get("capacity_value")),
            "latest_active_capacity_human": _format_capacity_human(
                latest_active.get("capacity_value"),
                latest_active.get("capacity_unit"),
                latest_active.get("raw") or {},
            ),
            "latest_active_speed_human": _format_rate_human(latest_active.get("speed_value"), latest_active.get("speed_unit")),
            "avg_latency_ms": _safe_float(sum(latencies_ms) / len(latencies_ms), 2) if latencies_ms else None,
            "avg_speed_value": _safe_float(sum(speeds) / len(speeds), 2) if speeds else None,
            "avg_capacity_value": _safe_float(sum(capacities) / len(capacities), 2) if capacities else None,
            "raw": raw_latest,
        }
    return dict(sorted(summaries.items(), key=lambda item: item[1]["rank"]))


def build_transfer_kpi_index(transfer_summaries: dict, micro_batch_data: dict, points: int) -> List[dict]:
    snapshot = transfer_summaries.get("data_lake_snapshot") or {}
    micro = transfer_summaries.get("micro_batch_events") or {}
    micro_summary = (micro_batch_data or {}).get("summary") or {}

    monitored_flows = int(bool(snapshot)) + int(bool(micro))
    active_windows = int(micro_summary.get("active_windows", 0) or 0)
    health_status = "success" if monitored_flows >= 2 and points > 0 else ("warning" if points > 0 else "danger")

    freshness_snapshot = snapshot.get("latest_latency_ms")
    freshness_micro = micro.get("latest_latency_ms")
    freshness_status = "success"
    if freshness_snapshot is None and freshness_micro is None:
        freshness_status = "warning"
    elif (freshness_snapshot is not None and freshness_snapshot > 60000) or (freshness_micro is not None and freshness_micro > 3000):
        freshness_status = "warning"

    throughput_snapshot = snapshot.get("latest_speed_human") or "-"
    throughput_micro = micro.get("latest_active_speed_human") or micro.get("latest_speed_human") or "-"
    throughput_status = "success" if (micro.get("latest_active_capacity_value") or 0) > 0 else "warning"

    volume_snapshot = snapshot.get("latest_capacity_human") or "-"
    volume_micro = micro.get("latest_active_capacity_human") or micro.get("latest_capacity_human") or "-"
    volume_status = "success" if (micro.get("latest_active_capacity_value") or 0) > 0 else "warning"

    return [
        {
            "index": 1,
            "key": "health",
            "label": "Sante pipeline",
            "status": health_status,
            "headline": f"{monitored_flows} flux observes",
            "support": (
                f"Snapshot {snapshot.get('points', 0)} point(s) | Micro-batch {micro.get('points', 0)} point(s) | "
                f"{active_windows} fenetre(s) active(s)"
            ),
        },
        {
            "index": 2,
            "key": "freshness",
            "label": "Fraicheur de traitement",
            "status": freshness_status,
            "headline": (
                f"Snapshot {snapshot.get('latest_latency_ms') / 1000:.2f}s | Micro-batch {micro.get('latest_latency_ms'):.0f}ms"
                if snapshot.get("latest_latency_ms") is not None and micro.get("latest_latency_ms") is not None
                else snapshot.get("latest_capacity_human") or micro.get("latest_capacity_human") or "-"
            ),
            "support": "Temps de traitement des deux briques de transfert.",
        },
        {
            "index": 3,
            "key": "throughput",
            "label": "Debit de transfert",
            "status": throughput_status,
            "headline": throughput_micro if throughput_micro != "-" else throughput_snapshot,
            "support": f"Snapshot {throughput_snapshot} | Micro-batch {throughput_micro}",
        },
        {
            "index": 4,
            "key": "volume",
            "label": "Volume traite",
            "status": volume_status,
            "headline": volume_micro if volume_micro != "-" else volume_snapshot,
            "support": f"Snapshot {volume_snapshot} | Micro-batch {volume_micro}",
        },
    ]


def _fraud_rate_label(fraud_rate_percent: float) -> str:
    if fraud_rate_percent < 2.0:
        return "faible"
    if fraud_rate_percent < 5.0:
        return "modere"
    return "eleve"


def _coverage_label(coverage_percent: float) -> str:
    if coverage_percent < 20.0:
        return "faible"
    if coverage_percent < 50.0:
        return "moyenne"
    return "large"


def build_readable_fraud_kpis(stats: dict) -> dict:
    total_alerts = int(stats.get("total_alerts", 0) or 0)
    total_payments = int(stats.get("total_payments", 0) or 0)
    fraudulent_payments = int(stats.get("fraudulent_payments", 0) or 0)
    fraud_rate = float(stats.get("fraud_rate", 0.0) or 0.0)
    alerted_customers = int(stats.get("alerted_customers", 0) or 0)
    total_customers = int(stats.get("total_customers", 0) or 0)
    customer_alert_coverage = float(stats.get("customer_alert_coverage", 0.0) or 0.0)

    alert_to_payment_ratio = round((total_alerts / total_payments), 2) if total_payments > 0 else None
    alert_per_fraud_payment = round((total_alerts / fraudulent_payments), 2) if fraudulent_payments > 0 else None

    top_reasons = stats.get("top_fraud_reasons") or []
    top_reason = top_reasons[0] if top_reasons else None
    top_reason_text = (
        f"{top_reason.get('reason')} ({top_reason.get('count')})"
        if isinstance(top_reason, dict) and top_reason.get("reason")
        else "non disponible"
    )

    return {
        "headline": f"{fraud_rate:.2f}% de paiements frauduleux ({fraudulent_payments}/{total_payments})",
        "risk_level": _fraud_rate_label(fraud_rate),
        "coverage_level": _coverage_label(customer_alert_coverage),
        "kpis": {
            "total_alerts": total_alerts,
            "fraud_rate_percent": round(fraud_rate, 2),
            "fraudulent_payments": fraudulent_payments,
            "total_payments": total_payments,
            "alerted_customers": alerted_customers,
            "total_customers": total_customers,
            "customer_alert_coverage_percent": round(customer_alert_coverage, 2),
            "alert_to_payment_ratio": alert_to_payment_ratio,
            "alert_per_fraud_payment": alert_per_fraud_payment,
            "top_reason": top_reason_text,
        },
        "formulas": {
            "fraud_rate_percent": "fraudulent_successful_payments / successful_payments * 100",
            "customer_alert_coverage_percent": "alerted_customers / total_customers * 100",
            "alert_to_payment_ratio": "total_alerts / total_payments",
        },
        "interpretation": [
            "Le taux de fraude est mesure sur les paiements reussis, il ne peut donc pas depasser 100%.",
            "Le volume d'alertes peut etre superieur aux paiements frauduleux, car plusieurs regles peuvent se declencher sur un meme paiement.",
            f"Raison la plus frequente: {top_reason_text}.",
        ],
    }


def build_readable_transfer_kpis(transfer_data: dict, micro_batch_data: dict) -> dict:
    metrics_count = transfer_data.get("metrics_count") or {}
    points = int(transfer_data.get("points", 0) or 0)
    summary = transfer_data.get("summary") or {}
    normalized_rows = transfer_data.get("kpis") or []
    summary_by_metric = transfer_data.get("summary_by_metric") or {}
    kpi_index = transfer_data.get("kpi_index") or []

    latest_snapshot = None
    latest_micro_batch_metric = None
    for row in reversed(normalized_rows):
        metric_name = row.get("metric")
        if metric_name == "data_lake_snapshot" and latest_snapshot is None:
            latest_snapshot = row
        if metric_name == "micro_batch_events" and latest_micro_batch_metric is None:
            latest_micro_batch_metric = row
        if latest_snapshot and latest_micro_batch_metric:
            break

    latest_snapshot_raw = latest_snapshot.get("raw", {}) if latest_snapshot else {}
    latest_micro_raw = latest_micro_batch_metric.get("raw", {}) if latest_micro_batch_metric else {}

    snapshot_files = latest_snapshot_raw.get("capacity_files")
    snapshot_bytes = latest_snapshot_raw.get("capacity_bytes")
    snapshot_latency_seconds = _safe_float(latest_snapshot_raw.get("latency_seconds"))
    snapshot_speed_bytes = _safe_float(latest_snapshot_raw.get("speed_bytes_per_second"))

    micro_summary = (micro_batch_data or {}).get("summary") or {}
    micro_total_events = int(micro_summary.get("total_events", 0) or 0)
    micro_avg_latency_ms = _safe_float(micro_summary.get("avg_latency_ms"))
    micro_avg_speed_events = _safe_float(micro_summary.get("avg_speed_events_per_sec"))
    micro_active_windows = int(micro_summary.get("active_windows", 0) or 0)
    micro_metric_summary = summary_by_metric.get("micro_batch_events") or {}
    silver_metric_summary = summary_by_metric.get("data_lake_silver") or {}
    gold_metric_summary = summary_by_metric.get("data_lake_gold") or {}
    micro_latest_latency_ms = _safe_float(micro_metric_summary.get("latest_latency_ms"))
    micro_latest_speed_human = (
        micro_metric_summary.get("latest_active_speed_human")
        or micro_metric_summary.get("latest_speed_human")
    )
    micro_latest_volume_human = (
        micro_metric_summary.get("latest_active_capacity_human")
        or micro_metric_summary.get("latest_capacity_human")
    )

    micro_status = "actif" if micro_active_windows > 0 else ("present" if points > 0 else "inactif")
    availability = "ok" if points > 0 else "aucune_donnee"

    interpretation = []
    if points == 0:
        interpretation.append("Aucun KPI de transfert n'est encore disponible.")
    else:
        interpretation.append(
            f"Historique transfert disponible: {points} points ({', '.join(f'{k}:{v}' for k, v in metrics_count.items())})."
        )

    if latest_snapshot:
        interpretation.append(
            "Dernier snapshot Data Lake: "
            f"{snapshot_files if snapshot_files is not None else '-'} fichiers, "
            f"{_format_bytes_human(snapshot_bytes) or '-'} transfere(s) en "
            f"{snapshot_latency_seconds if snapshot_latency_seconds is not None else '-'} s."
        )

    if silver_metric_summary:
        interpretation.append(
            f"Silver: {silver_metric_summary.get('latest_capacity_human') or '-'} publie(s) "
            f"a {silver_metric_summary.get('latest_speed_human') or '-'}."
        )

    if gold_metric_summary:
        interpretation.append(
            f"Gold: {gold_metric_summary.get('latest_capacity_human') or '-'} publie(s) "
            f"a {gold_metric_summary.get('latest_speed_human') or '-'}."
        )

    if micro_total_events == 0:
        interpretation.append(
            "Flux micro-batch: 0 evenement sur la fenetre observee. "
            "Le pipeline est probablement au repos ou sans nouvelle alimentation."
        )
    else:
        interpretation.append(
            "Derniere fenetre micro-batch utile: "
            f"{micro_latest_volume_human or f'{micro_total_events} evenement(s)'} "
            f"traite(s) en {micro_latest_latency_ms if micro_latest_latency_ms is not None else '-'} ms "
            f"a {micro_latest_speed_human or '-'}."
        )

    for item in kpi_index:
        label = item.get("label")
        headline = item.get("headline")
        if label and headline:
            interpretation.append(f"{label}: {headline}.")

    return {
        "headline": (
            f"Pipeline {availability}; micro-batch {micro_status}"
            if points > 0
            else "Transfert sans donnees recentes"
        ),
        "availability": availability,
        "micro_batch_status": micro_status,
        "kpis": {
            "points": points,
            "metrics_count": metrics_count,
            "health_score": summary.get("health_score"),
            "latest_snapshot_files": snapshot_files,
            "latest_snapshot_size_bytes": _safe_float(snapshot_bytes, 0),
            "latest_snapshot_size_human": _format_bytes_human(snapshot_bytes),
            "latest_snapshot_latency_seconds": snapshot_latency_seconds,
            "latest_snapshot_speed_bytes_per_second": snapshot_speed_bytes,
            "latest_micro_batch_events": int(latest_micro_raw.get("capacity_events", 0) or 0)
            if latest_micro_raw
            else 0,
            "micro_batch_total_events_window": micro_total_events,
            "micro_batch_active_windows_window": micro_active_windows,
            "micro_batch_avg_latency_ms_window": micro_avg_latency_ms,
            "micro_batch_avg_speed_events_per_sec_window": micro_avg_speed_events,
            "micro_batch_latest_latency_ms": micro_latest_latency_ms,
            "micro_batch_latest_speed_human": micro_latest_speed_human,
            "micro_batch_latest_volume_human": micro_latest_volume_human,
            "summary_by_metric": summary_by_metric,
            "kpi_index": kpi_index,
        },
        "interpretation": interpretation,
    }

def log_checkout_attempt(
    customer_id: str,
    id_card_file: str,
    customer_age: int,
    contains_adult_product: bool,
    blocked_underage: bool,
    accepted: bool,
    blocked_products: List[int],
    total_amount: float,
    order_id: Optional[int] = None,
    notes: Optional[str] = None
) -> Optional[int]:
    """
    Audit technique/métier des tentatives de commande API.
    Utilise une connexion dédiée pour conserver les logs même en cas de rollback checkout.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO checkout_attempts (
                attempted_at, customer_id, id_card_file, customer_age,
                contains_adult_product, blocked_underage, accepted,
                blocked_products, total_amount, order_id, notes
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING attempt_id
        """, (
            datetime.now(),
            customer_id,
            id_card_file,
            customer_age,
            contains_adult_product,
            blocked_underage,
            accepted,
            ",".join(str(p) for p in sorted(blocked_products)) if blocked_products else None,
            round(total_amount, 2),
            order_id,
            notes
        ))
        attempt_id = cursor.fetchone()[0]
        conn.commit()
        publish_live_event("checkout_attempt", {
            "attempt_id": attempt_id,
            "customer_id": customer_id,
            "id_card_file": id_card_file,
            "customer_age": customer_age,
            "contains_adult_product": contains_adult_product,
            "blocked_underage": blocked_underage,
            "accepted": accepted,
            "blocked_products": blocked_products,
            "total_amount": round(total_amount, 2),
            "order_id": order_id,
            "notes": notes,
        })
        return attempt_id
    finally:
        cursor.close()
        conn.close()


def build_checkout_document_number(id_card_file: str, birthdate_str: str) -> str:
    safe_name = Path(id_card_file).name
    return f"SYNTH-ID::{safe_name}::{birthdate_str}"


def insert_identity_verification_record(
    customer_id: str,
    document_number: str,
    document_type: str,
    verification_status: str,
    verification_method: str,
    id_card_image_path: Optional[str] = None,
    verification_date: Optional[datetime] = None,
) -> int:
    """
    Enregistre une verification d'identite avec hash SHA-256 du document.
    Utilise une connexion dediee pour tracer les checkouts acceptes et bloques.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO identity_verifications (
                customer_id, verification_date, document_type, document_number,
                verification_status, verification_method, id_card_image_path, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING verification_id
        """, (
            customer_id,
            verification_date or datetime.now(),
            document_type,
            hash_document_number(document_number),
            verification_status,
            verification_method,
            id_card_image_path,
            datetime.now()
        ))
        verification_id = cursor.fetchone()[0]
        conn.commit()
        publish_live_event("identity_verification", {
            "verification_id": verification_id,
            "customer_id": customer_id,
            "document_type": document_type,
            "verification_status": verification_status,
            "verification_method": verification_method,
            "id_card_image_path": id_card_image_path,
            "verification_date": verification_date or datetime.now(),
        })
        return verification_id
    finally:
        cursor.close()
        conn.close()


def record_checkout_identity_verification(
    customer_id: str,
    id_card_file: str,
    birthdate_str: str,
    blocked_underage: bool,
) -> int:
    verification_status = "rejected" if blocked_underage else "verified"
    document_number = build_checkout_document_number(id_card_file, birthdate_str)
    return insert_identity_verification_record(
        customer_id=customer_id,
        document_number=document_number,
        document_type="synthetic_id_card",
        verification_status=verification_status,
        verification_method="checkout_guardrail",
        id_card_image_path=Path(id_card_file).name,
        verification_date=datetime.now(),
    )


def build_checkout_fraud_alert(
    customer_id: str,
    customer_country: Optional[str],
    previous_orders: int,
    blocked_underage: bool,
    contains_adult_product: bool,
) -> Optional[dict]:
    if not blocked_underage or not contains_adult_product:
        return None

    now = datetime.now()
    return {
        "alert_id": f"FRD_CHK_{int(time.time() * 1000)}_{uuid4().hex[:6].upper()}",
        "alert_timestamp": now,
        "event_timestamp": now,
        "customer_id": customer_id,
        "session_id": f"CHK_{uuid4().hex[:12].upper()}",
        "event_type": "checkout_blocked_underage",
        "device": "api",
        "utm_source": "checkout_guardrail",
        "customer_country": customer_country or "FR",
        "previous_payments": max(int(previous_orders or 0), 0),
        "is_new_customer": int(previous_orders or 0) == 0,
        "fraud_reasons": ["AGE_RESTRICTED_ATTEMPT", "IDENTITY_CHECK_REQUIRED"],
        "risk_score": 93,
        "status": "PENDING_REVIEW",
        "severity": "HIGH",
    }


def normalize_payment_method(payment_method: Optional[str]) -> str:
    method = (payment_method or "card").strip().lower()
    aliases = {
        "credit_card": "card",
        "debit_card": "card",
        "cb": "card",
        "transfer": "bank_transfer",
        "wire": "bank_transfer",
    }
    method = aliases.get(method, method)
    if method not in {"card", "paypal", "bank_transfer"}:
        return "card"
    return method


def build_checkout_payment_profile(
    customer_id: str,
    customer_age: int,
    total_amount: float,
    payment_method: str,
    customer_country: Optional[str],
    previous_orders: int,
    contains_adult_product: bool,
    risk_profile: str = "standard",
) -> dict:
    method = normalize_payment_method(payment_method)
    risk_profile = (risk_profile or "standard").strip().lower()
    risk_score = 9
    alert_reasons: List[str] = []

    if previous_orders == 0:
        risk_score += 15
        alert_reasons.append("FIRST_PAYMENT")
    elif previous_orders <= 2:
        risk_score += 8

    if total_amount >= 150:
        risk_score += 14
        alert_reasons.append("UNUSUAL_AMOUNT")
    elif total_amount >= 80:
        risk_score += 6

    if contains_adult_product:
        risk_score += 7
        alert_reasons.append("ADULT_CATALOG")

    if customer_age <= 21:
        risk_score += 5
        alert_reasons.append("YOUNG_ADULT")

    if (customer_country or "FR") not in {"FR", "BE", "CH", "LU"}:
        risk_score += 8
        alert_reasons.append("GEO_MISMATCH")

    if method == "paypal":
        risk_score += 4
        alert_reasons.append("ALT_PAYMENT_METHOD")
    elif method == "bank_transfer":
        risk_score += 2
        alert_reasons.append("MANUAL_SETTLEMENT")
    if risk_profile == "elevated":
        risk_score += 12
        alert_reasons.append("PAYMENT_RISK_REVIEW")

    risk_score += random.randint(0, 8)
    fraud_probability = 0.02
    if previous_orders == 0:
        fraud_probability += 0.04
    elif previous_orders <= 2:
        fraud_probability += 0.015
    if total_amount >= 150:
        fraud_probability += 0.05
    elif total_amount >= 80:
        fraud_probability += 0.02
    if contains_adult_product:
        fraud_probability += 0.03
    if customer_age <= 21:
        fraud_probability += 0.02
    if (customer_country or "FR") not in {"FR", "BE", "CH", "LU"}:
        fraud_probability += 0.04
    if method == "paypal":
        fraud_probability += 0.015
    elif method == "bank_transfer":
        fraud_probability += 0.025
    if risk_profile == "elevated":
        fraud_probability += 0.10
    fraud_probability += min(max(risk_score - 20, 0) / 1000.0, 0.06)
    fraud_probability = min(max(fraud_probability, 0.02), 0.32)

    is_fraudulent = random.random() < fraud_probability
    review_required = bool(is_fraudulent or risk_score >= 52)
    browser = random.choice(["chrome", "safari", "firefox", "edge"])
    ip_address = f"198.51.100.{random.randint(10, 220)}"
    card_last4 = f"{random.randint(0, 9999):04d}" if method == "card" else None

    return {
        "payment_method": method,
        "payment_status": "success",
        "card_last4": card_last4,
        "transaction_id": f"PAYCHK_{uuid4().hex[:14].upper()}",
        "ip_address": ip_address,
        "device_id": f"chk_{customer_id.lower()}_{uuid4().hex[:8]}",
        "browser": browser,
        "is_fraudulent": is_fraudulent,
        "risk_score": int(risk_score),
        "risk_profile": risk_profile,
        "fraud_probability": round(fraud_probability, 4),
        "review_required": review_required,
        "alert_reasons": list(dict.fromkeys(alert_reasons or ["PAYMENT_RISK_REVIEW"])),
    }


def insert_checkout_payment(
    cursor,
    *,
    order_id: int,
    customer_id: str,
    customer_age: int,
    total_amount: float,
    payment_method: str,
    customer_country: Optional[str],
    previous_orders: int,
    contains_adult_product: bool,
    created_at: datetime,
    risk_profile: str = "standard",
) -> dict:
    profile = build_checkout_payment_profile(
        customer_id=customer_id,
        customer_age=customer_age,
        total_amount=total_amount,
        payment_method=payment_method,
        customer_country=customer_country,
        previous_orders=previous_orders,
        contains_adult_product=contains_adult_product,
        risk_profile=risk_profile,
    )

    cursor.execute("LOCK TABLE payments IN EXCLUSIVE MODE")
    cursor.execute("SELECT COALESCE(MAX(payment_id), 0) + 1 FROM payments")
    payment_id = int(cursor.fetchone()[0])

    cursor.execute(
        """
        INSERT INTO payments (
            payment_id, order_id, payment_date, amount, payment_method,
            card_last4, payment_status, transaction_id, ip_address,
            device_id, browser, is_fraudulent, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            payment_id,
            order_id,
            created_at,
            round(total_amount, 2),
            profile["payment_method"],
            profile["card_last4"],
            profile["payment_status"],
            profile["transaction_id"],
            profile["ip_address"],
            profile["device_id"],
            profile["browser"],
            profile["is_fraudulent"],
            created_at,
        ),
    )

    order_status = "manual_review" if profile["review_required"] else "paid"
    cursor.execute(
        "UPDATE orders SET status = %s WHERE order_id = %s",
        (order_status, order_id),
    )

    profile.update({
        "payment_id": payment_id,
        "amount": round(total_amount, 2),
        "customer_id": customer_id,
        "order_id": order_id,
        "customer_age": customer_age,
        "customer_country": customer_country or "FR",
        "contains_adult_product": contains_adult_product,
        "payment_date": created_at,
        "order_status": order_status,
    })
    return profile


def build_checkout_payment_alert(payment_profile: dict, previous_orders: int) -> Optional[dict]:
    if not payment_profile.get("review_required"):
        return None

    now = datetime.now()
    risk_score = int(payment_profile.get("risk_score", 0) or 0)
    severity = "HIGH" if payment_profile.get("is_fraudulent") else infer_severity_from_score(risk_score)
    event_type = "payment_flagged_review" if not payment_profile.get("is_fraudulent") else "payment_flagged_fraud"

    return {
        "alert_id": f"FRD_PAY_{payment_profile.get('payment_id')}_{uuid4().hex[:6].upper()}",
        "alert_timestamp": now,
        "event_timestamp": now,
        "customer_id": payment_profile.get("customer_id"),
        "session_id": payment_profile.get("transaction_id"),
        "event_type": event_type,
        "device": "api",
        "utm_source": payment_profile.get("payment_method", "card"),
        "customer_country": payment_profile.get("customer_country", "FR"),
        "previous_payments": max(int(previous_orders or 0), 0),
        "is_new_customer": int(previous_orders or 0) == 0,
        "fraud_reasons": payment_profile.get("alert_reasons") or ["PAYMENT_RISK_REVIEW"],
        "risk_score": risk_score,
        "status": "PENDING_REVIEW",
        "severity": severity,
    }


def emit_checkout_security_events(
    customer_id: str,
    id_card_file: str,
    birthdate_str: str,
    customer_country: Optional[str],
    previous_orders: int,
    blocked_underage: bool,
    contains_adult_product: bool,
) -> dict:
    result = {
        "identity_verification_id": None,
        "fraud_alert_id": None,
    }

    result["identity_verification_id"] = record_checkout_identity_verification(
        customer_id=customer_id,
        id_card_file=id_card_file,
        birthdate_str=birthdate_str,
        blocked_underage=blocked_underage,
    )

    alert = build_checkout_fraud_alert(
        customer_id=customer_id,
        customer_country=customer_country,
        previous_orders=previous_orders,
        blocked_underage=blocked_underage,
        contains_adult_product=contains_adult_product,
    )
    if alert and insert_fraud_alert(alert, send_notification=True):
        result["fraud_alert_id"] = alert["alert_id"]

    return result

def infer_severity_from_score(risk_score: int) -> str:
    if risk_score >= 80:
        return "HIGH"
    if risk_score >= 60:
        return "MEDIUM"
    return "LOW"

def build_simulated_alert(payload: AlertSimulationRequest) -> dict:
    """
    Construit une alerte synthétique (fraude) pour alimenter le dashboard en temps réel.
    """
    now = datetime.now()
    customer_id = payload.customer_id or f"C{random.randint(1, 2500):05d}"
    session_id = payload.session_id or f"SIM_{uuid4().hex[:12]}"
    event_type = payload.event_type or random.choice(["payment_attempt", "checkout", "order_completed"])
    device = payload.device or random.choice(["ios", "android", "desktop"])
    utm_source = payload.utm_source or random.choice(["direct", "google", "instagram", "facebook", "email"])
    customer_country = payload.customer_country or random.choice(["FR", "ES", "PT", "DE", "IT", "GB"])
    previous_payments = payload.previous_payments if payload.previous_payments is not None else random.randint(0, 12)
    is_new_customer = payload.is_new_customer if payload.is_new_customer is not None else (previous_payments == 0)

    reasons = payload.fraud_reasons
    if not reasons:
        count = random.randint(1, 3)
        reasons = random.sample(FRAUD_REASON_POOL, k=count)

    risk_score = payload.risk_score
    if risk_score is None:
        risk_score = random.randint(60, 96) if random.random() < 0.35 else random.randint(45, 79)

    severity = payload.severity or infer_severity_from_score(risk_score)
    status = payload.status
    alert_id = f"FRD_SIM_{int(time.time() * 1000)}_{uuid4().hex[:6].upper()}"

    return {
        "alert_id": alert_id,
        "alert_timestamp": now,
        "event_timestamp": now - timedelta(seconds=random.randint(0, 8)),
        "customer_id": customer_id,
        "session_id": session_id,
        "event_type": event_type,
        "device": device,
        "utm_source": utm_source,
        "customer_country": customer_country,
        "previous_payments": previous_payments,
        "is_new_customer": bool(is_new_customer),
        "fraud_reasons": reasons,
        "risk_score": int(risk_score),
        "status": status,
        "severity": severity
    }

def insert_fraud_alert(alert: dict, send_notification: bool = True) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    inserted = False
    try:
        cursor.execute("""
            INSERT INTO fraud_alerts (
                alert_id, alert_timestamp, event_timestamp, customer_id,
                session_id, event_type, device, utm_source, customer_country,
                previous_payments, is_new_customer, fraud_reasons,
                risk_score, status, severity
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (alert_id) DO NOTHING
        """, (
            alert["alert_id"],
            alert["alert_timestamp"],
            alert["event_timestamp"],
            alert["customer_id"],
            alert["session_id"],
            alert["event_type"],
            alert["device"],
            alert["utm_source"],
            alert["customer_country"],
            alert["previous_payments"],
            alert["is_new_customer"],
            ",".join(alert["fraud_reasons"]),
            alert["risk_score"],
            alert["status"],
            alert["severity"]
        ))
        inserted = cursor.rowcount > 0
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    if inserted:
        publish_live_event("fraud_alert", {
            "alert_id": alert.get("alert_id"),
            "customer_id": alert.get("customer_id"),
            "event_type": alert.get("event_type"),
            "severity": alert.get("severity"),
            "status": alert.get("status"),
            "risk_score": alert.get("risk_score"),
            "fraud_reasons": alert.get("fraud_reasons", []),
            "alert_timestamp": alert.get("alert_timestamp"),
        })

    if inserted and send_notification:
        settings = load_alert_notification_settings()
        if settings.get("enabled") and settings.get("recipient_email"):
            try:
                notify_alert_event("new_alert", alert)
            except ValueError:
                pass
            except Exception as exc:
                append_alert_notification_history({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event_type": "new_alert",
                    "recipient_email": settings.get("recipient_email"),
                    "alert_id": alert.get("alert_id"),
                    "severity": alert.get("severity"),
                    "risk_score": int(alert.get("risk_score", 0) or 0),
                    "status": "failed",
                    "delivery_mode": alert_notification_delivery_mode(settings),
                    "sender_email": smtp_notification_settings().get("from_email"),
                    "preview_file": None,
                    "subject": f"[KiVendTout] Nouvelle alerte {alert.get('severity', 'INFO')} {alert.get('alert_id', 'ALERTE')}",
                    "actor": None,
                    "message": str(exc),
                })

    return inserted

def append_runtime_log(message: str):
    """Écrit une ligne horodatée dans le log runtime refresh."""
    try:
        RUNTIME_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with RUNTIME_LOG_FILE.open("a", encoding="utf-8") as log_file:
            timestamp = datetime.now().isoformat(timespec="seconds")
            log_file.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        print(f"Erreur écriture runtime log: {e}")


def append_micro_batch_run_log(lines: List[str]):
    """Conserve un journal dédié aux déclenchements micro-batch depuis l'API."""
    try:
        MICRO_BATCH_RUN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with MICRO_BATCH_RUN_LOG_FILE.open("a", encoding="utf-8") as log_file:
            timestamp = datetime.now().isoformat(timespec="seconds")
            log_file.write(f"\n[{timestamp}] micro-batch run\n")
            for line in lines:
                log_file.write(f"{line}\n")
    except Exception as e:
        print(f"Erreur écriture micro batch log: {e}")


def _set_micro_batch_last_result(payload: dict):
    global MICRO_BATCH_LAST_RESULT
    MICRO_BATCH_LAST_RESULT = {
        "running": bool(payload.get("running", False)),
        "mode": str(payload.get("mode", "once")),
        "returncode": payload.get("returncode"),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "duration_seconds": payload.get("duration_seconds"),
        "log_file": str(payload.get("log_file") or MICRO_BATCH_RUN_LOG_FILE),
        "message": str(payload.get("message") or ""),
        "output_lines": list(payload.get("output_lines") or []),
    }


def _run_micro_batch_job(payload: MicroBatchRunRequest) -> dict:
    script_path = BASE_DIR / "scripts" / "run_micro_batch.sh"
    if not script_path.exists():
        raise FileNotFoundError(f"Script micro-batch introuvable: {script_path}")

    if not MICRO_BATCH_RUN_LOCK.acquire(blocking=False):
        raise RuntimeError("Un micro-batch est deja en cours d'execution")

    started_at = datetime.utcnow().isoformat() + "Z"
    start_monotonic = time.monotonic()
    env = os.environ.copy()
    env.update({
        "WINDOW_SECONDS": str(payload.window_seconds),
        "BOOTSTRAP_MINUTES": str(payload.bootstrap_minutes),
        "POLL_INTERVAL": str(payload.poll_interval),
        "DURATION_SECONDS": str(payload.duration_seconds),
        "MICRO_BATCH_ANCHOR_MODE": env.get(
            "MICRO_BATCH_ANCHOR_MODE",
            "latest-data" if payload.mode == "once" else "auto",
        ),
        "PYTHONUNBUFFERED": "1",
    })

    _set_micro_batch_last_result({
        "running": True,
        "mode": payload.mode,
        "returncode": None,
        "started_at": started_at,
        "finished_at": None,
        "duration_seconds": None,
        "log_file": str(MICRO_BATCH_RUN_LOG_FILE),
        "message": "Execution en cours",
        "output_lines": [],
    })
    append_runtime_log(
        "Lancement micro-batch via API "
        f"(mode={payload.mode}, window_seconds={payload.window_seconds}, bootstrap_minutes={payload.bootstrap_minutes}, "
        f"poll_interval={payload.poll_interval}, duration_seconds={payload.duration_seconds})"
    )

    try:
        timeout_seconds = max(180, payload.duration_seconds + 60) if payload.mode == "live" else 180
        completed = subprocess.run(
            ["bash", str(script_path), payload.mode],
            cwd=str(BASE_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        combined_output = []
        if completed.stdout:
            combined_output.extend(line for line in completed.stdout.splitlines() if line.strip())
        if completed.stderr:
            combined_output.extend(line for line in completed.stderr.splitlines() if line.strip())
        output_tail = combined_output[-20:]
        duration_seconds = round(time.monotonic() - start_monotonic, 2)
        finished_at = datetime.utcnow().isoformat() + "Z"
        append_micro_batch_run_log(output_tail or ["(aucune sortie)"])

        result = {
            "running": False,
            "mode": payload.mode,
            "returncode": completed.returncode,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": duration_seconds,
            "log_file": str(MICRO_BATCH_RUN_LOG_FILE),
            "message": "Micro-batch termine" if completed.returncode == 0 else "Micro-batch termine avec erreur",
            "output_lines": output_tail,
        }
        _set_micro_batch_last_result(result)
        append_runtime_log(
            f"Micro-batch termine (rc={completed.returncode}, duration={duration_seconds:.2f}s, mode={payload.mode})"
        )
        return result
    except subprocess.TimeoutExpired as exc:
        output_tail = []
        if exc.stdout:
            output_tail.extend(line for line in str(exc.stdout).splitlines() if line.strip())
        if exc.stderr:
            output_tail.extend(line for line in str(exc.stderr).splitlines() if line.strip())
        output_tail = output_tail[-20:]
        duration_seconds = round(time.monotonic() - start_monotonic, 2)
        finished_at = datetime.utcnow().isoformat() + "Z"
        append_micro_batch_run_log(output_tail or ["Execution interrompue par timeout"])
        result = {
            "running": False,
            "mode": payload.mode,
            "returncode": None,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": duration_seconds,
            "log_file": str(MICRO_BATCH_RUN_LOG_FILE),
            "message": "Execution micro-batch interrompue par timeout",
            "output_lines": output_tail,
        }
        _set_micro_batch_last_result(result)
        append_runtime_log(f"Micro-batch timeout (mode={payload.mode}, duration={duration_seconds:.2f}s)")
        raise TimeoutError("Execution micro-batch interrompue par timeout")
    finally:
        MICRO_BATCH_RUN_LOCK.release()

def start_scaling_process(
    scaling_mode: str,
    requests: int,
    concurrency: int,
    adult_order_ratio: float,
    minor_ratio: float,
    duration_seconds: int,
    rps: int,
    risk_profile: str = "standard",
) -> Tuple[bool, Optional[int], str]:
    """Lance scripts/scale_order_api.py en arrière-plan si aucun run n'est actif."""
    global RUNTIME_SCALING_PROCESS

    script_path = BASE_DIR / "scripts" / "scale_order_api.py"
    if not script_path.exists():
        message = f"Script scaling introuvable: {script_path}"
        append_runtime_log(message)
        return False, None, message

    stock_message = None
    stock_conn = get_db_connection()
    stock_cursor = stock_conn.cursor()
    try:
        stock_state = ensure_demo_catalog_stock(stock_cursor)
        stock_conn.commit()
        if stock_state.get("adult_restocked") or stock_state.get("non_adult_restocked"):
            stock_message = (
                "Reconstitution stock demo "
                f"(adult={stock_state['adult_in_stock_after']}, non_adult={stock_state['non_adult_in_stock_after']})"
            )
    finally:
        stock_cursor.close()
        stock_conn.close()

    with RUNTIME_REFRESH_LOCK:
        if RUNTIME_SCALING_PROCESS is not None and RUNTIME_SCALING_PROCESS.poll() is None:
            pid = RUNTIME_SCALING_PROCESS.pid
            message = f"Scaling déjà en cours (pid={pid})"
            append_runtime_log(message)
            return False, pid, message

        cmd = [
            sys.executable,
            str(script_path),
            "--api-url", "http://localhost:8000",
            "--mode", str(scaling_mode),
            "--requests", str(requests),
            "--concurrency", str(concurrency),
            "--adult-order-ratio", str(adult_order_ratio),
            "--minor-ratio", str(minor_ratio),
            "--duration-seconds", str(duration_seconds),
            "--rps", str(rps),
            "--risk-profile", str(risk_profile),
        ]

        # Le log runtime consolide les déclenchements et sorties du scaling.
        log_handle = RUNTIME_LOG_FILE.open("a", encoding="utf-8")
        if stock_message:
            append_runtime_log(stock_message)
        append_runtime_log(f"Lancement scaling: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
        log_handle.close()

        RUNTIME_SCALING_PROCESS = process
        message = f"Scaling lancé (pid={process.pid})"
        started_at = datetime.now(timezone.utc)
        expected_end_at = (
            started_at + timedelta(seconds=duration_seconds)
            if scaling_mode == "realtime" and duration_seconds > 0
            else None
        )
        _set_runtime_process_state(
            "orders",
            running=True,
            pid=process.pid,
            mode=scaling_mode,
            started_at=started_at.isoformat(),
            finished_at=None,
            expected_end_at=expected_end_at.isoformat() if expected_end_at else None,
            duration_seconds=duration_seconds if scaling_mode == "realtime" else None,
            requests=requests,
            concurrency=concurrency,
            rps=rps if scaling_mode == "realtime" else None,
            risk_profile=risk_profile,
            returncode=None,
            message=message,
        )
        publish_live_event("runtime_state", {
            "kind": "orders",
            "running": True,
            "pid": process.pid,
            "mode": scaling_mode,
            "started_at": started_at.isoformat(),
            "expected_end_at": expected_end_at.isoformat() if expected_end_at else None,
            "risk_profile": risk_profile,
            "message": message,
        })
        threading.Thread(target=_monitor_runtime_process, args=("orders", process), daemon=True).start()
        append_runtime_log(message)
        return True, process.pid, message

def start_alert_scaling_process(
    alerts_mode: str,
    alerts_requests: int,
    alerts_concurrency: int,
    alerts_duration_seconds: int,
    alerts_rps: int,
    high_severity_ratio: float
) -> Tuple[bool, Optional[int], str]:
    """Lance scripts/scale_alerts_api.py en arrière-plan si aucun run n'est actif."""
    global RUNTIME_ALERTS_PROCESS

    script_path = BASE_DIR / "scripts" / "scale_alerts_api.py"
    if not script_path.exists():
        message = f"Script alert scaling introuvable: {script_path}"
        append_runtime_log(message)
        return False, None, message

    with RUNTIME_REFRESH_LOCK:
        if RUNTIME_ALERTS_PROCESS is not None and RUNTIME_ALERTS_PROCESS.poll() is None:
            pid = RUNTIME_ALERTS_PROCESS.pid
            message = f"Alert scaling déjà en cours (pid={pid})"
            append_runtime_log(message)
            return False, pid, message

        cmd = [
            sys.executable,
            str(script_path),
            "--api-url", "http://localhost:8000",
            "--mode", str(alerts_mode),
            "--requests", str(alerts_requests),
            "--concurrency", str(alerts_concurrency),
            "--duration-seconds", str(alerts_duration_seconds),
            "--rps", str(alerts_rps),
            "--high-severity-ratio", str(high_severity_ratio),
        ]

        log_handle = RUNTIME_LOG_FILE.open("a", encoding="utf-8")
        append_runtime_log(f"Lancement alert scaling: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
        log_handle.close()

        RUNTIME_ALERTS_PROCESS = process
        message = f"Alert scaling lancé (pid={process.pid})"
        started_at = datetime.now(timezone.utc)
        expected_end_at = (
            started_at + timedelta(seconds=alerts_duration_seconds)
            if alerts_mode == "realtime" and alerts_duration_seconds > 0
            else None
        )
        _set_runtime_process_state(
            "alerts",
            running=True,
            pid=process.pid,
            mode=alerts_mode,
            started_at=started_at.isoformat(),
            finished_at=None,
            expected_end_at=expected_end_at.isoformat() if expected_end_at else None,
            duration_seconds=alerts_duration_seconds if alerts_mode == "realtime" else None,
            requests=alerts_requests,
            concurrency=alerts_concurrency,
            rps=alerts_rps if alerts_mode == "realtime" else None,
            returncode=None,
            message=message,
        )
        publish_live_event("runtime_state", {
            "kind": "alerts",
            "running": True,
            "pid": process.pid,
            "mode": alerts_mode,
            "started_at": started_at.isoformat(),
            "expected_end_at": expected_end_at.isoformat() if expected_end_at else None,
            "message": message,
        })
        threading.Thread(target=_monitor_runtime_process, args=("alerts", process), daemon=True).start()
        append_runtime_log(message)
        return True, process.pid, message


def start_massive_fraud_orders_episode() -> dict:
    """Orchestre un episode de fraude visible sur les flux commandes, paiements et alertes."""
    started_orders, orders_pid, orders_message = start_scaling_process(
        scaling_mode="realtime",
        requests=1260,
        concurrency=14,
        adult_order_ratio=0.78,
        minor_ratio=0.34,
        duration_seconds=180,
        rps=7,
        risk_profile="elevated",
    )
    started_alerts, alerts_pid, alerts_message = start_alert_scaling_process(
        alerts_mode="realtime",
        alerts_requests=1260,
        alerts_concurrency=12,
        alerts_duration_seconds=180,
        alerts_rps=7,
        high_severity_ratio=0.78,
    )

    if started_orders and started_alerts:
        status = "started"
        passed = True
        message = "Episode fraude commandes lance pour 3 minutes."
    elif started_orders or started_alerts:
        status = "partial"
        passed = False
        message = "Episode fraude lance partiellement. Un des flux etait deja occupe."
    else:
        status = "busy"
        passed = False
        message = "Episode fraude non lance. Les flux commandes et alertes sont deja en cours."

    runtime_state = snapshot_live_runtime_state()
    return {
        "status": status,
        "passed": passed,
        "message": message,
        "resources": {
            "requests": 1260,
            "concurrency": 14,
            "adult_order_ratio": 0.78,
            "minor_ratio": 0.34,
            "rps": 7,
            "duration_seconds": 180,
            "risk_profile": "elevated",
            "alerts_requests": 1260,
            "alerts_concurrency": 12,
            "alerts_rps": 7,
            "high_severity_ratio": 0.78,
            "goal": "simuler une vague de fraude massive sur les commandes",
        },
        "process": {
            "orders_pid": orders_pid,
            "alerts_pid": alerts_pid,
            "orders_message": orders_message,
            "alerts_message": alerts_message,
        },
        "response": {
            "runtime_state": runtime_state,
            "orders_started": started_orders,
            "alerts_started": started_alerts,
        },
    }

def schedule_api_restart(delay_seconds: float = 1.2):
    """
    Planifie un redémarrage du process API après la réponse HTTP.
    Utilise execv pour relancer le script courant sur le même port.
    """
    def _restart():
        time.sleep(delay_seconds)
        append_runtime_log("Redémarrage API demandé via runtime refresh")
        script_path = Path(__file__).resolve()
        try:
            os.execv(sys.executable, [sys.executable, str(script_path)])
        except Exception as e:
            append_runtime_log(f"Erreur redémarrage API: {e}")

    threading.Thread(target=_restart, daemon=True).start()

# ============================================================================
# KAFKA CONSUMER (Background sync)
# ============================================================================

def sync_alerts_from_kafka(max_messages=1000):
    """
    Synchronise les alertes depuis Kafka vers PostgreSQL
    """
    if KafkaConsumer is None:
        print(f"Kafka indisponible: {KAFKA_IMPORT_ERROR}")
        return 0

    try:
        consumer = KafkaConsumer(
            'fraud-alerts',
            bootstrap_servers=['localhost:9092', 'localhost:9093', 'localhost:9094'],
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            group_id='fraud-dashboard-api',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            consumer_timeout_ms=5000
        )
        
        count = 0
        for message in consumer:
            alert = message.value

            try:
                if insert_fraud_alert(alert, send_notification=True):
                    count += 1
            except Exception as e:
                print(f"Erreur insertion: {e}")
            
            if count >= max_messages:
                break

        consumer.close()
        
        return count
    
    except Exception as e:
        print(f"Erreur sync Kafka: {e}")
        return 0

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialisation au démarrage"""
    global LIVE_EVENT_LOOP
    LIVE_EVENT_LOOP = asyncio.get_running_loop()
    print("🚀 Démarrage API Fraud Detection...")
    # Garantit la présence du fichier pour `tail -f logs/runtime_refresh.log`
    append_runtime_log("API startup")
    init_fraud_alerts_table()
    init_identity_verifications_table()
    init_checkout_attempts_table()
    init_micro_batch_metrics_table()
    ensure_orders_manual_review_status()
    print("✅ Initialisation API terminée")

@app.get("/")
async def root():
    """Page d'accueil API"""
    return {
        "message": "KiVendTout Fraud Detection API",
        "version": "1.0.0",
        "endpoints": {
            "alerts": "/api/alerts",
            "alert_detail": "/api/alerts/{alert_id}",
            "alert_notify": "/api/alerts/{alert_id}/notify",
            "simulate_alert": "/api/alerts/simulate",
            "alert_notification_config": "/api/alert-notifications/config",
            "alert_notification_history": "/api/alert-notifications/history",
            "alert_notification_test": "/api/alert-notifications/test",
            "use_cases": "/api/use-cases",
            "use_case_run": "/api/use-cases/{use_case_key}/run",
            "data_factory": "/api/data-factory",
            "data_factory_run": "/api/data-factory/{action_key}/run",
            "presentation_tests": "/api/presentation/tests",
            "presentation_test_run": "/api/presentation/tests/{test_key}/run",
            "identity_verify": "/api/verify-id",
            "identity_stats": "/api/identity/stats",
            "products": "/api/products",
            "id_cards": "/api/id-cards",
            "id_card_image": "/api/id-cards/image/{file_name}",
            "checkout": "/api/orders/checkout",
            "checkout_stats": "/api/checkout/stats",
            "checkout_attempts": "/api/checkout/attempts",
            "payments_stats": "/api/payments/stats",
            "fraud_reason_stats": "/api/fraud/reasons/stats",
            "fraud_reason_alerts": "/api/fraud/reasons/{reason}/alerts",
            "runtime_refresh": "/api/runtime/refresh",
            "runtime_logs": "/api/runtime/logs",
            "runtime_security": "/api/runtime/security",
            "runtime_live_state": "/api/live/state",
            "runtime_live_stream": "/api/live/stream",
            "system_reset_status": "/api/system/reset-status",
            "system_reset_data": "/api/system/reset-data",
            "id_model_status": "/api/id-model/status",
            "micro_batch_stats": "/api/micro-batch/stats",
            "transfer_kpis": "/api/transfer/kpis",
            "data_lake_status": "/api/data-lake/status",
            "data_platform_status": "/api/data-platform/status",
            "analytics_status": "/api/analytics/status",
            "kpis_readable": "/api/kpis/readable",
            "stats": "/api/stats",
            "sync": "/api/sync"
        }
    }


@app.get("/api/runtime/security")
async def get_runtime_security():
    access_control = load_api_access_control() if API_RBAC_ENABLED else {}
    keys = access_control.get("keys", [])
    role_permissions = access_control.get("role_permissions", {})
    return {
        "api_key_required": API_KEY_REQUIRED,
        "api_key_header": API_KEY_HEADER,
        "rbac_enabled": API_RBAC_ENABLED,
        "cors_allow_origins": CORS_ALLOW_ORIGINS,
        "cors_allow_credentials": CORS_ALLOW_CREDENTIALS,
        "configured_keys": len(keys),
        "roles": sorted(role_permissions.keys()),
        "default_quota": access_control.get("default_quota", _normalize_quota({})) if API_RBAC_ENABLED else None,
        "active_rate_limit_buckets": len(API_RATE_LIMIT_STATE),
        "access_control_file": str(API_ACCESS_CONTROL_FILE),
        "access_control_file_exists": API_ACCESS_CONTROL_FILE.exists(),
        "transfer_kpi_history_file": str(TRANSFER_KPI_HISTORY_FILE),
        "transfer_kpi_history_exists": TRANSFER_KPI_HISTORY_FILE.exists(),
    }


@app.get("/api/system/reset-status", response_model=DataResetResponse)
async def get_system_reset_status():
    return DataResetResponse(**snapshot_data_reset_state())


@app.post("/api/system/reset-data", response_model=DataResetResponse)
async def trigger_system_reset(payload: DataResetRequest, request: Request):
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Confirmation requise")
    current = snapshot_data_reset_state()
    if current.get("running"):
        raise HTTPException(status_code=409, detail=current)

    acquired = DATA_RESET_LOCK.acquire(blocking=False)
    if not acquired:
        raise HTTPException(status_code=409, detail=snapshot_data_reset_state())

    principal = getattr(request.state, "api_principal", None) or {}
    requested_by = principal.get("user") or "local-operator"
    queued_at = datetime.now(timezone.utc).isoformat()
    _set_data_reset_state(
        running=True,
        status="queued",
        requested_at=queued_at,
        requested_by=requested_by,
        started_at=None,
        finished_at=None,
        duration_seconds=None,
        step="queued",
        message="Reset planifie",
        output_lines=[],
        summary={},
    )

    def runner():
        try:
            _run_initial_data_reset(
                requested_by=requested_by,
                clear_runtime_artifacts=payload.clear_runtime_artifacts,
                stop_live_jobs=payload.stop_live_jobs,
            )
        finally:
            if DATA_RESET_LOCK.locked():
                DATA_RESET_LOCK.release()

    threading.Thread(target=runner, daemon=True).start()
    return DataResetResponse(**snapshot_data_reset_state())


@app.get("/api/live/state")
async def get_live_state():
    return snapshot_live_runtime_state()


@app.get("/api/live/stream")
async def stream_live_state(request: Request):
    queue: asyncio.Queue = asyncio.Queue(maxsize=256)
    with LIVE_EVENT_LOCK:
        LIVE_EVENT_SUBSCRIBERS.append(queue)

    async def event_generator():
        try:
            initial_payload = snapshot_live_runtime_state()
            initial_payload["_stream_kind"] = "init"
            yield f"event: runtime\ndata: {json.dumps(initial_payload, ensure_ascii=True)}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    live_event = await asyncio.wait_for(queue.get(), timeout=LIVE_STREAM_HEARTBEAT_SECONDS)
                    payload = snapshot_live_runtime_state()
                    payload["_stream_kind"] = "event"
                    payload["_event"] = live_event
                    yield f"event: runtime\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"
                except asyncio.TimeoutError:
                    payload = snapshot_live_runtime_state()
                    payload["_stream_kind"] = "heartbeat"
                    yield f"event: runtime\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"
        finally:
            with LIVE_EVENT_LOCK:
                if queue in LIVE_EVENT_SUBSCRIBERS:
                    LIVE_EVENT_SUBSCRIBERS.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/id-model/status")
async def get_id_model_status():
    model = load_id_fingerprint_model()
    return {
        "enabled": os.getenv("ID_CARD_MODEL_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"},
        "model_file": str(ID_FINGERPRINT_MODEL_FILE),
        "model_found": ID_FINGERPRINT_MODEL_FILE.exists(),
        "model_loaded": bool(model),
        "records": int(model.get("records", 0)) if model else 0,
        "model_type": model.get("model_type") if model else None,
        "version": model.get("version") if model else None,
        "trained_at": model.get("trained_at") if model else None,
    }

@app.get("/api/micro-batch/stats")
async def get_micro_batch_stats(
    window_hours: int = Query(24, ge=1, le=720, description="Fenêtre d'observation en heures"),
    limit: int = Query(200, ge=1, le=2000),
):
    """
    KPI du flux micro-batch MongoDB -> PostgreSQL.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            batch_started_at,
            batch_ended_at,
            event_type,
            events_count,
            latency_ms,
            speed_events_per_sec,
            created_at
        FROM micro_batch_event_metrics
        WHERE created_at >= NOW() - (%s || ' hours')::INTERVAL
        ORDER BY created_at DESC, batch_ended_at DESC, event_type ASC
        LIMIT %s
    """, (window_hours, limit))
    rows = cursor.fetchall()

    cursor.execute("""
        SELECT
            event_type,
            COALESCE(SUM(events_count), 0)::INT AS total_events,
            COUNT(*)::INT AS batches
        FROM micro_batch_event_metrics
        WHERE created_at >= NOW() - (%s || ' hours')::INTERVAL
        GROUP BY event_type
        ORDER BY total_events DESC, event_type ASC
    """, (window_hours,))
    by_type = cursor.fetchall()

    cursor.close()
    conn.close()

    window_map = {}
    for row in rows:
        batch_started_at, batch_ended_at, event_type, events_count, latency_ms, speed_events_per_sec, created_at = row
        key = (
            batch_started_at.isoformat() if batch_started_at else None,
            batch_ended_at.isoformat() if batch_ended_at else None,
        )
        entry = window_map.setdefault(key, {
            "batch_started_at": key[0],
            "batch_ended_at": key[1],
            "processed_at": created_at.isoformat() if created_at else None,
            "total_events": 0,
            "event_types_count": 0,
            "latency_ms": round(float(latency_ms or 0.0), 2),
            "speed_events_per_sec": round(float(speed_events_per_sec or 0.0), 2),
            "event_breakdown": [],
        })
        entry["total_events"] += int(events_count or 0)
        if event_type and event_type != "NO_EVENTS" and int(events_count or 0) > 0:
            entry["event_types_count"] += 1
            entry["event_breakdown"].append({
                "event_type": event_type,
                "events_count": int(events_count or 0),
            })
    recent_windows = sorted(
        window_map.values(),
        key=lambda item: (
            _parse_transfer_timestamp(item.get("processed_at")) or datetime.min.replace(tzinfo=timezone.utc),
            _parse_transfer_timestamp(item.get("batch_ended_at")) or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    for item in recent_windows:
        item["event_breakdown"] = sorted(item["event_breakdown"], key=lambda row: row["events_count"], reverse=True)

    active_windows = [item for item in recent_windows if int(item.get("total_events", 0) or 0) > 0]
    latency_windows = [float(item.get("latency_ms", 0.0) or 0.0) for item in recent_windows]
    speed_windows = [float(item.get("speed_events_per_sec", 0.0) or 0.0) for item in active_windows]
    latest_batch_ended_at = next(
        (
            item.get("batch_ended_at")
            for item in recent_windows
            if item.get("batch_ended_at")
        ),
        None,
    )
    latest_processed_at = next(
        (
            item.get("processed_at")
            for item in recent_windows
            if item.get("processed_at")
        ),
        None,
    )

    return {
        "window_hours": window_hours,
        "summary": {
            "rows": len(rows),
            "windows": len(recent_windows),
            "active_windows": len(active_windows),
            "total_events": sum(int(item.get("total_events", 0) or 0) for item in recent_windows),
            "avg_latency_ms": round(sum(latency_windows) / len(latency_windows), 2) if latency_windows else 0.0,
            "avg_speed_events_per_sec": round(sum(speed_windows) / len(speed_windows), 2) if speed_windows else 0.0,
            "latest_batch_ended_at": latest_batch_ended_at,
            "latest_processed_at": latest_processed_at,
        },
        "by_event_type": [
            {"event_type": item[0], "total_events": int(item[1]), "batches": int(item[2])}
            for item in by_type
        ],
        "recent_batches": [
            {
                "batch_started_at": row[0].isoformat() if row[0] else None,
                "batch_ended_at": row[1].isoformat() if row[1] else None,
                "event_type": row[2],
                "events_count": int(row[3] or 0),
                "latency_ms": round(float(row[4] or 0.0), 2),
                "speed_events_per_sec": round(float(row[5] or 0.0), 2),
                "created_at": row[6].isoformat() if row[6] else None,
            }
            for row in rows
        ],
        "recent_windows": recent_windows[: min(limit, 50)],
    }

@app.get("/api/micro-batch/runtime", response_model=MicroBatchRunResponse)
async def get_micro_batch_runtime():
    payload = dict(MICRO_BATCH_LAST_RESULT)
    payload["running"] = bool(payload.get("running")) and MICRO_BATCH_RUN_LOCK.locked()
    return MicroBatchRunResponse(**payload)


@app.post("/api/micro-batch/run", response_model=MicroBatchRunResponse)
async def run_micro_batch(payload: MicroBatchRunRequest):
    try:
        result = await asyncio.to_thread(_run_micro_batch_job, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail={
                "message": str(exc),
                "runtime": MICRO_BATCH_LAST_RESULT,
            },
        )

    if result.get("returncode") not in (0, None):
        raise HTTPException(
            status_code=500,
            detail={
                "message": result.get("message", "Erreur execution micro-batch"),
                "runtime": result,
            },
        )
    return MicroBatchRunResponse(**result)

@app.get("/api/transfer/kpis")
async def get_transfer_kpis(
    limit: int = Query(200, ge=1, le=5000)
):
    """
    KPI standardisés de transfert (latence/capacité/vitesse).
    Source: historique JSONL alimenté par snapshots et micro-batch.
    """
    history = load_transfer_kpi_history(limit=limit)
    normalized = [normalize_transfer_metric(row) for row in history]

    metrics_count = Counter(row["metric"] for row in normalized)
    transfer_summaries = build_transfer_metric_summaries(normalized)
    micro_batch_rows = [row for row in normalized if row.get("metric") == "micro_batch_events"]
    active_micro_batch_rows = [row for row in micro_batch_rows if (row.get("capacity_value") or 0) > 0]
    active_windows = len(active_micro_batch_rows)
    health_score = 0
    if normalized:
        health_score += 40
    if transfer_summaries.get("data_lake_snapshot"):
        health_score += 30
    if transfer_summaries.get("micro_batch_events"):
        health_score += 20
    if active_windows > 0:
        health_score += 10

    micro_batch_view = {
        "summary": {
            "active_windows": active_windows,
            "total_events": int(sum((row.get("capacity_value") or 0) for row in micro_batch_rows)),
            "avg_latency_ms": _safe_float(
                sum((row.get("latency_ms_normalized") or 0) for row in micro_batch_rows) / len(micro_batch_rows),
                2,
            ) if micro_batch_rows else None,
        }
    }
    kpi_index = build_transfer_kpi_index(transfer_summaries, micro_batch_view, len(normalized))

    return {
        "history_file": str(TRANSFER_KPI_HISTORY_FILE),
        "history_exists": TRANSFER_KPI_HISTORY_FILE.exists(),
        "points": len(normalized),
        "metrics_count": dict(metrics_count),
        "summary": {
            "health_score": health_score,
            "monitored_flows": len(transfer_summaries),
            "active_micro_batch_windows": active_windows,
            "latest_snapshot_size_human": (transfer_summaries.get("data_lake_snapshot") or {}).get("latest_capacity_human"),
            "latest_micro_batch_volume_human": (transfer_summaries.get("micro_batch_events") or {}).get("latest_active_capacity_human")
                or (transfer_summaries.get("micro_batch_events") or {}).get("latest_capacity_human"),
        },
        "summary_by_metric": transfer_summaries,
        "kpi_index": kpi_index,
        "kpis": normalized,
    }


@app.get("/api/data-lake/status")
async def get_data_lake_status(limit_reports: int = Query(5, ge=1, le=20)):
    reports = list_data_lake_promotion_reports(limit=limit_reports)
    latest = reports[0] if reports else None
    return {
        "configured": True,
        "provider": "minio",
        "layers": ["bronze", "silver", "gold"],
        "latest_report": latest,
        "reports": reports,
        "reports_count": len(reports),
    }


@app.get("/api/data-platform/status")
async def get_data_platform_status_endpoint():
    return get_data_platform_status()


@app.get("/api/analytics/status")
async def get_analytics_status():
    return get_analytics_warehouse_status()


@app.get("/api/kpis/readable")
async def get_readable_kpis(
    limit: int = Query(200, ge=1, le=5000),
    micro_batch_window_hours: int = Query(24, ge=1, le=720),
):
    """
    Vue lisible des KPI pour exploitation:
    - indicateurs bruts
    - formules de calcul
    - interpretation en langage simple
    """
    fraud_stats_model = await get_stats()
    transfer_data = await get_transfer_kpis(limit=limit)
    micro_batch_data = await get_micro_batch_stats(window_hours=micro_batch_window_hours, limit=min(limit, 500))

    if hasattr(fraud_stats_model, "model_dump"):
        fraud_stats = fraud_stats_model.model_dump()
    elif hasattr(fraud_stats_model, "dict"):
        fraud_stats = fraud_stats_model.dict()
    else:
        fraud_stats = dict(fraud_stats_model)

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "window": {
            "transfer_points_limit": limit,
            "micro_batch_window_hours": micro_batch_window_hours,
        },
        "fraud": build_readable_fraud_kpis(fraud_stats),
        "transfer": build_readable_transfer_kpis(transfer_data, micro_batch_data),
    }


async def run_minor_adult_checkout_use_case() -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        customer_id = select_demo_customer_id(cursor)
        product = select_demo_product(cursor, adult_required=True, only_in_stock=True)
    finally:
        cursor.close()
        conn.close()

    id_card = select_demo_id_card(adult_required=False)
    payload = CheckoutRequest(
        customer_id=customer_id,
        id_card_file=id_card["file"],
        items=[OrderItemRequest(product_id=product["product_id"], quantity=1)],
    )

    try:
        response = await create_checkout_order(payload)
        return {
            "passed": False,
            "outcome": "accepted_unexpectedly",
            "expected_outcome": "blocked_underage",
            "http_status": 200,
            "business_message": "La commande mineur a ete acceptee alors qu'un produit 18+ etait present.",
            "resources": {
                "customer_id": customer_id,
                "id_card": id_card,
                "product": product,
            },
            "response": json.loads(response.model_dump_json()),
        }
    except HTTPException as exc:
        passed = exc.status_code == 403
        return {
            "passed": passed,
            "outcome": "blocked_underage" if passed else "unexpected_http_error",
            "expected_outcome": "blocked_underage",
            "http_status": exc.status_code,
            "business_message": "Le garde-fou 18+ bloque bien la commande mineur." if passed else "La simulation a retourne une erreur inattendue.",
            "resources": {
                "customer_id": customer_id,
                "id_card": id_card,
                "product": product,
            },
            "response": exc.detail,
        }


async def run_adult_adult_checkout_use_case() -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        customer_id = select_demo_customer_id(cursor)
        product = select_demo_product(cursor, adult_required=True, only_in_stock=True)
    finally:
        cursor.close()
        conn.close()

    id_card = select_demo_id_card(adult_required=True)
    payload = CheckoutRequest(
        customer_id=customer_id,
        id_card_file=id_card["file"],
        items=[OrderItemRequest(product_id=product["product_id"], quantity=1)],
    )
    response = await create_checkout_order(payload)
    return {
        "passed": bool(response.accepted),
        "outcome": "accepted" if response.accepted else "rejected",
        "expected_outcome": "accepted",
        "http_status": 200,
        "business_message": "La commande majeur sur produit 18+ est acceptee et cree une commande.",
        "resources": {
            "customer_id": customer_id,
            "id_card": id_card,
            "product": product,
        },
        "response": json.loads(response.model_dump_json()),
    }


async def run_identity_verification_use_case() -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        customer_id = select_demo_customer_id(cursor)
    finally:
        cursor.close()
        conn.close()

    id_card = select_demo_id_card(adult_required=True)
    document_number = f"USECASE-{uuid4().hex[:12].upper()}"
    payload = IdentityVerificationRequest(
        customer_id=customer_id,
        document_number=document_number,
        document_type="national_id",
        verification_method="use_case",
        is_adult=True,
        id_card_image_path=id_card["file"],
    )
    response = await verify_identity(payload)
    return {
        "passed": response.get("document_number_stored_as") == "sha256",
        "outcome": response.get("verification_status"),
        "expected_outcome": "verified",
        "http_status": 200,
        "business_message": "La verification enregistre un hash SHA-256 du document et une preuve d'audit.",
        "resources": {
            "customer_id": customer_id,
            "id_card": id_card,
            "document_number_sample": document_number,
        },
        "response": response,
    }


async def run_high_risk_alert_use_case() -> dict:
    payload = AlertSimulationRequest(
        severity="HIGH",
        risk_score=95,
        status="PENDING_REVIEW",
        fraud_reasons=["VELOCITY_HIGH", "NEW_DEVICE", "UNUSUAL_AMOUNT"],
        customer_country="FR",
        device="desktop",
    )
    alert = await simulate_alert(payload)
    history_matches = [
        item for item in list_alert_notification_history(limit=20)
        if item.get("alert_id") == alert.alert_id
    ]
    return {
        "passed": alert.severity == "HIGH",
        "outcome": alert.severity,
        "expected_outcome": "HIGH",
        "http_status": 200,
        "business_message": "Une alerte haute severite est generee et peut etre notifiee si le canal email est actif.",
        "resources": {
            "customer_id": alert.customer_id,
            "alert_id": alert.alert_id,
            "notification_mode": alert_notification_delivery_mode(),
        },
        "response": json.loads(alert.model_dump_json()),
        "notification_history": history_matches[:3],
    }


async def run_massive_fraud_orders_use_case() -> dict:
    episode = start_massive_fraud_orders_episode()
    runtime_state = (episode.get("response") or {}).get("runtime_state") or {}
    order_state = runtime_state.get("orders") or {}
    alert_state = runtime_state.get("alerts") or {}
    return {
        "passed": bool(episode.get("passed")),
        "outcome": episode.get("status"),
        "expected_outcome": "started",
        "http_status": 200,
        "business_message": episode.get("message"),
        "resources": {
            "orders_pid": (episode.get("process") or {}).get("orders_pid"),
            "alerts_pid": (episode.get("process") or {}).get("alerts_pid"),
            "orders_expected_end_at": order_state.get("expected_end_at"),
            "alerts_expected_end_at": alert_state.get("expected_end_at"),
            "orders_risk_profile": order_state.get("risk_profile"),
            **(episode.get("resources") or {}),
        },
        "response": episode.get("response"),
    }


async def execute_use_case(use_case_key: str) -> dict:
    started_at = datetime.now(timezone.utc)
    if use_case_key == "minor-adult-checkout":
        result = await run_minor_adult_checkout_use_case()
    elif use_case_key == "adult-adult-checkout":
        result = await run_adult_adult_checkout_use_case()
    elif use_case_key == "identity-verification":
        result = await run_identity_verification_use_case()
    elif use_case_key == "high-risk-alert":
        result = await run_high_risk_alert_use_case()
    elif use_case_key == "massive-fraud-orders-episode":
        result = await run_massive_fraud_orders_use_case()
    else:
        raise HTTPException(status_code=404, detail=f"Unknown use case: {use_case_key}")

    completed_at = datetime.now(timezone.utc)
    definition = USE_CASE_DEFINITIONS[use_case_key]
    history_entry = {
        "use_case_key": use_case_key,
        "title": definition["title"],
        "domain": definition["domain"],
        "timestamp": completed_at.isoformat(),
        "duration_ms": round((completed_at - started_at).total_seconds() * 1000.0, 2),
        "passed": bool(result.get("passed")),
        "outcome": result.get("outcome"),
        "expected_outcome": result.get("expected_outcome"),
        "http_status": result.get("http_status"),
        "business_message": result.get("business_message"),
        "resources": result.get("resources"),
        "response": result.get("response"),
    }
    append_use_case_history(history_entry)
    return {
        "definition": definition,
        **history_entry,
        "notification_history": result.get("notification_history", []),
    }


async def execute_data_factory_action(action_key: str) -> dict:
    started_at = datetime.now(timezone.utc)
    if action_key == "single-high-alert":
        alert = await simulate_alert(AlertSimulationRequest(
            severity="HIGH",
            risk_score=94,
            status="PENDING_REVIEW",
            fraud_reasons=["VELOCITY_HIGH", "NEW_DEVICE", "UNUSUAL_AMOUNT"],
            customer_country="FR",
            device="desktop",
        ))
        result = {
            "status": "ok",
            "message": "Une alerte HIGH a ete ajoutee au backlog fraude.",
            "async_job": False,
            "passed": True,
            "resources": {
                "alert_id": alert.alert_id,
                "customer_id": alert.customer_id,
                "severity": alert.severity,
            },
            "response": json.loads(alert.model_dump_json()),
            "process": None,
        }
    elif action_key == "alerts-live-3m":
        started, pid, message = start_alert_scaling_process(
            alerts_mode="realtime",
            alerts_requests=1080,
            alerts_concurrency=8,
            alerts_duration_seconds=180,
            alerts_rps=6,
            high_severity_ratio=0.45,
        )
        result = {
            "status": "started" if started else "busy",
            "message": message if started else "Un flux d'alertes est deja en cours de generation.",
            "async_job": True,
            "passed": started,
            "resources": {
                "alerts_requests": 1080,
                "alerts_concurrency": 8,
                "alerts_rps": 6,
                "duration_seconds": 180,
                "high_severity_ratio": 0.45,
            },
            "response": None,
            "process": {"pid": pid, "type": "alert-scaling"} if pid else None,
        }
    elif action_key == "minor-blocked-checkout":
        use_case = await run_minor_adult_checkout_use_case()
        result = {
            "status": "ok" if use_case.get("passed") else "error",
            "message": "Une tentative mineur 18+ a ete rejouee." if use_case.get("passed") else "La tentative mineur n'a pas produit le blocage attendu.",
            "async_job": False,
            "passed": bool(use_case.get("passed")),
            "resources": use_case.get("resources"),
            "response": use_case.get("response"),
            "process": None,
        }
    elif action_key == "adult-approved-checkout":
        use_case = await run_adult_adult_checkout_use_case()
        result = {
            "status": "ok" if use_case.get("passed") else "error",
            "message": "Une commande majeure 18+ a ete ajoutee." if use_case.get("passed") else "La commande majeure n'a pas ete creee comme attendu.",
            "async_job": False,
            "passed": bool(use_case.get("passed")),
            "resources": use_case.get("resources"),
            "response": use_case.get("response"),
            "process": None,
        }
    elif action_key == "identity-verification":
        use_case = await run_identity_verification_use_case()
        result = {
            "status": "ok" if use_case.get("passed") else "error",
            "message": "Une verification d'identite a ete enregistree." if use_case.get("passed") else "La verification d'identite n'a pas produit le resultat attendu.",
            "async_job": False,
            "passed": bool(use_case.get("passed")),
            "resources": use_case.get("resources"),
            "response": use_case.get("response"),
            "process": None,
        }
    elif action_key == "orders-live-3m":
        started, pid, message = start_scaling_process(
            scaling_mode="realtime",
            requests=720,
            concurrency=8,
            adult_order_ratio=0.6,
            minor_ratio=0.4,
            duration_seconds=180,
            rps=4,
            risk_profile="standard",
        )
        result = {
            "status": "started" if started else "busy",
            "message": message if started else "Un flux de commandes est deja en cours de generation.",
            "async_job": True,
            "passed": started,
            "resources": {
                "requests": 720,
                "concurrency": 8,
                "adult_order_ratio": 0.6,
                "minor_ratio": 0.4,
                "rps": 4,
                "duration_seconds": 180,
                "risk_profile": "standard",
            },
            "response": None,
            "process": {"pid": pid, "type": "order-scaling"} if pid else None,
        }
    elif action_key == "payments-live-3m":
        started, pid, message = start_scaling_process(
            scaling_mode="realtime",
            requests=900,
            concurrency=10,
            adult_order_ratio=0.45,
            minor_ratio=0.12,
            duration_seconds=180,
            rps=5,
            risk_profile="elevated",
        )
        result = {
            "status": "started" if started else "busy",
            "message": (
                message
                if started
                else "Un flux de commandes/paiements est deja en cours de generation."
            ),
            "async_job": True,
            "passed": started,
            "resources": {
                "requests": 900,
                "concurrency": 10,
                "adult_order_ratio": 0.45,
                "minor_ratio": 0.12,
                "rps": 5,
                "duration_seconds": 180,
                "risk_profile": "elevated",
                "goal": "faire varier proprement les paiements et le fraud_rate",
            },
            "response": None,
            "process": {"pid": pid, "type": "payment-scaling"} if pid else None,
        }
    elif action_key == "massive-fraud-orders-3m":
        episode = start_massive_fraud_orders_episode()
        result = {
            "status": episode["status"],
            "message": episode["message"],
            "async_job": True,
            "passed": episode["passed"],
            "resources": episode["resources"],
            "response": episode["response"],
            "process": episode["process"],
        }
    elif action_key == "data-lake-pipeline":
        pipeline = run_data_lake_promotion_pipeline()
        passed = pipeline.get("returncode") == 0 and bool((pipeline.get("report") or {}).get("layers"))
        latest_report = pipeline.get("report") or {}
        result = {
            "status": "ok" if passed else "error",
            "message": (
                "Le pipeline bronze -> silver -> gold a ete publie dans MinIO."
                if passed
                else "La promotion Data Lake a echoue."
            ),
            "async_job": False,
            "passed": passed,
            "resources": latest_report.get("layers"),
            "response": latest_report,
            "process": {
                "returncode": pipeline.get("returncode"),
                "stdout_tail": pipeline.get("stdout_tail"),
                "stderr_tail": pipeline.get("stderr_tail"),
            },
        }
    elif action_key == "analytics-warehouse":
        pipeline = run_analytics_warehouse_pipeline()
        report = pipeline.get("report") or {}
        datamarts = report.get("datamarts") or {}
        passed = pipeline.get("returncode") == 0 and bool(datamarts)
        result = {
            "status": "ok" if passed else "error",
            "message": (
                "Le schema analytics et les datamarts ont ete construits."
                if passed
                else "La construction du schema analytics a echoue."
            ),
            "async_job": False,
            "passed": passed,
            "resources": report,
            "response": report,
            "process": {
                "returncode": pipeline.get("returncode"),
                "stdout_tail": pipeline.get("stdout_tail"),
                "stderr_tail": pipeline.get("stderr_tail"),
            },
        }
    elif action_key == "data-platform-pipeline":
        pipeline = run_data_platform_pipeline()
        report = pipeline.get("report") or {}
        passed = pipeline.get("returncode") == 0 and report.get("status") == "PASS"
        result = {
            "status": "ok" if passed else "error",
            "message": (
                "La chaine data complete a ete rejouee avec succes."
                if passed
                else "Le pipeline consolide de la plateforme data a echoue."
            ),
            "async_job": False,
            "passed": passed,
            "resources": report.get("summary") or {},
            "response": report,
            "process": {
                "returncode": pipeline.get("returncode"),
                "stdout_tail": pipeline.get("stdout_tail"),
                "stderr_tail": pipeline.get("stderr_tail"),
            },
        }
    else:
        raise HTTPException(status_code=404, detail=f"Unknown data factory action: {action_key}")

    completed_at = datetime.now(timezone.utc)
    definition = DATA_FACTORY_ACTIONS[action_key]
    history_entry = {
        "action_key": action_key,
        "title": definition["title"],
        "domain": definition["domain"],
        "mode": definition["mode"],
        "timestamp": completed_at.isoformat(),
        "duration_ms": round((completed_at - started_at).total_seconds() * 1000.0, 2),
        "status": result["status"],
        "message": result["message"],
        "async_job": bool(result.get("async_job")),
        "passed": result.get("passed"),
        "resources": result.get("resources"),
        "response": result.get("response"),
        "process": result.get("process"),
    }
    append_data_factory_history(history_entry)
    return {
        "definition": definition,
        **history_entry,
    }


@app.get("/api/use-cases")
async def get_use_cases(limit_history: int = Query(12, ge=1, le=50)):
    history = list_use_case_history(limit=limit_history)
    last_by_key = {}
    for item in history:
        key = item.get("use_case_key")
        if key and key not in last_by_key:
            last_by_key[key] = item
    items = []
    for key, definition in USE_CASE_DEFINITIONS.items():
        items.append({
            **definition,
            "last_run": last_by_key.get(key),
        })
    return {
        "items": items,
        "history": history,
        "notification_mode": alert_notification_delivery_mode(),
        "history_file": str(USE_CASE_HISTORY_FILE),
    }


@app.post("/api/use-cases/{use_case_key}/run")
async def run_use_case(use_case_key: str):
    return await execute_use_case(use_case_key)


@app.get("/api/data-factory")
async def get_data_factory(limit_history: int = Query(20, ge=1, le=50)):
    history = list_data_factory_history(limit=limit_history)
    last_by_key = {}
    for item in history:
        key = item.get("action_key")
        if key and key not in last_by_key:
            last_by_key[key] = item
    items = []
    for key, definition in DATA_FACTORY_ACTIONS.items():
        items.append({
            **definition,
            "last_run": last_by_key.get(key),
        })
    return {
        "items": items,
        "history": history,
        "history_file": str(DATA_FACTORY_HISTORY_FILE),
    }


@app.post("/api/data-factory/{action_key}/run", response_model=DataFactoryActionResponse)
async def run_data_factory_action(action_key: str):
    result = await execute_data_factory_action(action_key)
    return DataFactoryActionResponse(
        action_key=result["action_key"],
        status=result["status"],
        title=result["title"],
        domain=result["domain"],
        timestamp=result["timestamp"],
        message=result["message"],
        async_job=result["async_job"],
        passed=result.get("passed"),
        resources=result.get("resources"),
        response=result.get("response"),
        process=result.get("process"),
    )


@app.get("/api/presentation/tests")
async def get_presentation_tests(limit_history: int = Query(20, ge=1, le=50)):
    history = list_presentation_test_history(limit=limit_history)
    last_by_key = {}
    for item in history:
        key = item.get("test_key")
        if key and key not in last_by_key:
            last_by_key[key] = item
    items = []
    for key, definition in sorted(PRESENTATION_TEST_DEFINITIONS.items(), key=lambda row: row[1]["order"]):
        items.append({
            **definition,
            "last_run": last_by_key.get(key),
        })
    return {
        "items": items,
        "history": history,
        "history_file": str(PRESENTATION_TEST_HISTORY_FILE),
        "notification_delivery_mode": alert_notification_delivery_mode(),
    }


@app.post("/api/presentation/tests/{test_key}/run", response_model=PresentationTestResponse)
async def run_presentation_test(test_key: str, payload: PresentationTestRequest):
    result = await execute_presentation_test(test_key, recipient_email=payload.recipient_email)
    return PresentationTestResponse(
        test_key=result["test_key"],
        status=result["status"],
        title=result["title"],
        category=result["category"],
        timestamp=result["timestamp"],
        message=result["message"],
        async_job=result["async_job"],
        passed=result.get("passed"),
        duration_ms=result.get("duration_ms"),
        highlights=result.get("highlights") or [],
        resources=result.get("resources"),
        response=result.get("response"),
        process=result.get("process"),
    )


def fetch_alert_record(alert_id: str) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM fraud_alerts WHERE alert_id = %s", (alert_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Alert not found")
        columns = [desc[0] for desc in cursor.description]
        alert_dict = dict(zip(columns, row))
        alert_dict["fraud_reasons"] = alert_dict["fraud_reasons"].split(",") if alert_dict["fraud_reasons"] else []
        alert_dict["alert_timestamp"] = str(alert_dict["alert_timestamp"])
        alert_dict["event_timestamp"] = str(alert_dict["event_timestamp"]) if alert_dict["event_timestamp"] else None
        alert_dict["decided_at"] = str(alert_dict["decided_at"]) if alert_dict["decided_at"] else None
        return alert_dict
    finally:
        cursor.close()
        conn.close()


@app.get("/api/alert-notifications/config")
async def get_alert_notification_config():
    config = load_alert_notification_settings()
    smtp = smtp_notification_settings()
    return {
        **config,
        "delivery_mode": alert_notification_delivery_mode(config),
        "smtp_configured": bool(smtp.get("host")),
        "sender_email": smtp.get("from_email"),
        "history_file": str(ALERT_NOTIFICATION_HISTORY_FILE),
        "preview_directory": str(ALERT_NOTIFICATION_PREVIEW_DIR),
    }


@app.put("/api/alert-notifications/config")
async def update_alert_notification_config(payload: AlertNotificationConfigPayload):
    recipient = (payload.recipient_email or "").strip() or None
    if payload.enabled and not _validate_email(recipient):
        raise HTTPException(status_code=400, detail="recipient_email invalide ou manquant")
    if recipient and not _validate_email(recipient):
        raise HTTPException(status_code=400, detail="recipient_email invalide")

    config = load_alert_notification_settings()
    config.update({
        "enabled": bool(payload.enabled),
        "recipient_email": recipient,
        "min_severity": payload.min_severity,
        "notify_on_new_alert": bool(payload.notify_on_new_alert),
        "notify_on_decision": bool(payload.notify_on_decision),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": (payload.updated_by or "dashboard").strip() or "dashboard",
    })
    save_alert_notification_settings(config)
    return {
        **config,
        "delivery_mode": alert_notification_delivery_mode(config),
        "smtp_configured": bool(smtp_notification_settings().get("host")),
        "sender_email": smtp_notification_settings().get("from_email"),
    }


@app.get("/api/alert-notifications/history")
async def get_alert_notification_history(limit: int = Query(20, ge=1, le=100)):
    items = list_alert_notification_history(limit=limit)
    return {
        "items": items,
        "count": len(items),
        "history_file": str(ALERT_NOTIFICATION_HISTORY_FILE),
    }


@app.post("/api/alert-notifications/test")
async def send_test_alert_notification(payload: AlertNotificationTestRequest):
    config = load_alert_notification_settings()
    recipient = (payload.recipient_email or config.get("recipient_email") or "").strip()
    if not _validate_email(recipient):
        raise HTTPException(status_code=400, detail="recipient_email invalide ou non configure")

    synthetic_alert = {
        "alert_id": f"TEST_{uuid4().hex[:8].upper()}",
        "severity": config.get("min_severity", "HIGH"),
        "risk_score": 88,
        "status": "PENDING_REVIEW",
        "customer_id": "C00125",
        "session_id": "TEST_SESSION",
        "customer_country": "FR",
        "device": "desktop",
        "fraud_reasons": ["VELOCITY_HIGH", "NEW_DEVICE"],
        "alert_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        entry = notify_alert_event(
            "test",
            synthetic_alert,
            actor=(payload.updated_by or "dashboard").strip() or "dashboard",
            message=payload.message or "Notification de validation depuis le dashboard fraude.",
            recipient_override=recipient,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return entry

@app.get("/api/alerts", response_model=List[FraudAlert])
async def get_alerts(
    status: Optional[str] = Query(None, description="Filter by status: PENDING_REVIEW, APPROVED, BLOCKED, INVESTIGATING"),
    severity: Optional[str] = Query(None, description="Filter by severity: LOW, MEDIUM, HIGH"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """
    Liste les alertes de fraude avec filtres
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Construction de la requête
    query = "SELECT * FROM fraud_alerts WHERE 1=1"
    params = []
    
    if status:
        query += " AND status = %s"
        params.append(status)
    
    if severity:
        query += " AND severity = %s"
        params.append(severity)
    
    query += " ORDER BY alert_timestamp DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    
    columns = [desc[0] for desc in cursor.description]
    results = []
    
    for row in cursor.fetchall():
        alert_dict = dict(zip(columns, row))
        alert_dict['fraud_reasons'] = alert_dict['fraud_reasons'].split(',') if alert_dict['fraud_reasons'] else []
        alert_dict['alert_timestamp'] = str(alert_dict['alert_timestamp'])
        alert_dict['event_timestamp'] = str(alert_dict['event_timestamp']) if alert_dict['event_timestamp'] else None
        alert_dict['decided_at'] = str(alert_dict['decided_at']) if alert_dict['decided_at'] else None
        results.append(alert_dict)
    
    cursor.close()
    conn.close()
    
    return results

@app.get("/api/alerts/{alert_id}", response_model=FraudAlert)
async def get_alert(alert_id: str):
    """
    Détails d'une alerte spécifique
    """
    return fetch_alert_record(alert_id)


@app.post("/api/alerts/{alert_id}/notify")
async def notify_alert(alert_id: str, payload: AlertNotificationTestRequest):
    alert = fetch_alert_record(alert_id)
    recipient = (payload.recipient_email or load_alert_notification_settings().get("recipient_email") or "").strip()
    if not _validate_email(recipient):
        raise HTTPException(status_code=400, detail="recipient_email invalide ou non configure")

    try:
        entry = notify_alert_event(
            "manual",
            alert,
            actor=(payload.updated_by or "dashboard").strip() or "dashboard",
            message=payload.message or "Notification manuelle depuis le dashboard fraude.",
            recipient_override=recipient,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return entry

@app.post("/api/alerts/simulate", response_model=FraudAlert)
async def simulate_alert(payload: AlertSimulationRequest):
    """
    Génère une alerte synthétique et l'insère dans fraud_alerts.
    Utilisé par le simulateur temps réel pour rendre le dashboard dynamique.
    """
    alert = build_simulated_alert(payload)
    insert_fraud_alert(alert)

    return FraudAlert(
        alert_id=alert["alert_id"],
        alert_timestamp=str(alert["alert_timestamp"]),
        event_timestamp=str(alert["event_timestamp"]) if alert["event_timestamp"] else None,
        customer_id=alert["customer_id"],
        session_id=alert["session_id"],
        event_type=alert["event_type"],
        device=alert["device"],
        utm_source=alert["utm_source"],
        customer_country=alert["customer_country"],
        previous_payments=int(alert["previous_payments"]),
        is_new_customer=bool(alert["is_new_customer"]),
        fraud_reasons=list(alert["fraud_reasons"]),
        risk_score=int(alert["risk_score"]),
        status=alert["status"],
        severity=alert["severity"],
        decision=None,
        decided_at=None,
        decided_by=None
    )

@app.post("/api/alerts/{alert_id}/decide")
async def decide_alert(alert_id: str, decision: AlertDecision):
    """
    Prend une décision sur une alerte (APPROVE, BLOCK, INVESTIGATE)
    """
    if decision.decision not in ['APPROVE', 'BLOCK', 'INVESTIGATE']:
        raise HTTPException(status_code=400, detail="Invalid decision. Must be APPROVE, BLOCK, or INVESTIGATE")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Vérifier que l'alerte existe
    cursor.execute("SELECT status FROM fraud_alerts WHERE alert_id = %s", (alert_id,))
    result = cursor.fetchone()
    
    if not result:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Alert not found")
    
    # Mettre à jour la décision
    new_status = 'INVESTIGATING' if decision.decision == 'INVESTIGATE' else decision.decision + 'D'
    
    cursor.execute("""
        UPDATE fraud_alerts
        SET decision = %s,
            status = %s,
            decided_at = %s,
            decided_by = %s,
            notes = %s
        WHERE alert_id = %s
    """, (
        decision.decision,
        new_status,
        datetime.now(),
        decision.decided_by,
        decision.notes,
        alert_id
    ))
    
    conn.commit()
    cursor.close()
    conn.close()

    settings = load_alert_notification_settings()
    if settings.get("enabled") and settings.get("recipient_email") and settings.get("notify_on_decision"):
        try:
            alert = fetch_alert_record(alert_id)
            notify_alert_event("decision", alert, actor=decision.decided_by, message=decision.notes)
        except ValueError:
            pass
        except Exception as exc:
            append_alert_notification_history({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": "decision",
                "recipient_email": settings.get("recipient_email"),
                "alert_id": alert_id,
                "severity": None,
                "risk_score": 0,
                "status": "failed",
                "delivery_mode": alert_notification_delivery_mode(settings),
                "sender_email": smtp_notification_settings().get("from_email"),
                "preview_file": None,
                "subject": f"[KiVendTout] Decision alerte {alert_id}",
                "actor": decision.decided_by,
                "message": str(exc),
            })

    return {"message": "Decision recorded", "alert_id": alert_id, "decision": decision.decision}

@app.get("/api/stats", response_model=FraudStats)
async def get_stats():
    """
    Statistiques globales de fraude
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Total alertes
    cursor.execute("SELECT COUNT(*) FROM fraud_alerts")
    total_alerts = cursor.fetchone()[0]
    
    # Par sévérité
    cursor.execute("SELECT severity, COUNT(*) FROM fraud_alerts GROUP BY severity")
    alerts_by_severity = dict(cursor.fetchall())
    
    # Par status
    cursor.execute("SELECT status, COUNT(*) FROM fraud_alerts GROUP BY status")
    alerts_by_status = dict(cursor.fetchall())
    
    # Volume de paiements: on suit les paiements successfully autorises/settled.
    cursor.execute("SELECT COUNT(*) FROM payments WHERE COALESCE(payment_status, 'success') = 'success'")
    total_payments = cursor.fetchone()[0]
    cursor.execute("""
        SELECT COUNT(*)
        FROM payments
        WHERE COALESCE(payment_status, 'success') = 'success'
          AND is_fraudulent = true
    """)
    fraudulent_payments = cursor.fetchone()[0]

    # Taux de fraude metier: paiements fraude confirmes / paiements reussis.
    fraud_rate = round((fraudulent_payments / total_payments) * 100, 2) if total_payments > 0 else 0.0

    # Couverture client des alertes (utile pour contextualiser le volume d'alertes)
    cursor.execute("SELECT COUNT(*) FROM customers")
    total_customers = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT customer_id) FROM fraud_alerts WHERE customer_id IS NOT NULL")
    alerted_customers = cursor.fetchone()[0]
    customer_alert_coverage = round((alerted_customers / total_customers) * 100, 2) if total_customers > 0 else 0.0
    
    # Top fraud reasons
    cursor.execute("SELECT fraud_reasons FROM fraud_alerts")
    all_reasons = []
    for row in cursor.fetchall():
        if row[0]:
            all_reasons.extend(row[0].split(','))
    
    reason_counts = Counter(all_reasons)
    top_fraud_reasons = [{"reason": r, "count": c} for r, c in reason_counts.most_common(10)]
    
    # Alertes par heure (dernières 24h)
    cursor.execute("""
        SELECT 
            EXTRACT(HOUR FROM alert_timestamp) as hour,
            COUNT(*)
        FROM fraud_alerts
        WHERE alert_timestamp >= NOW() - INTERVAL '24 hours'
        GROUP BY hour
        ORDER BY hour
    """)
    alerts_by_hour = [{"hour": int(h), "count": c} for h, c in cursor.fetchall()]
    
    # Alertes par jour (derniers 7 jours)
    cursor.execute("""
        SELECT 
            DATE(alert_timestamp) as day,
            COUNT(*)
        FROM fraud_alerts
        WHERE alert_timestamp >= NOW() - INTERVAL '7 days'
        GROUP BY day
        ORDER BY day
    """)
    alerts_by_day = [{"day": str(d), "count": c} for d, c in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    
    return FraudStats(
        total_alerts=total_alerts,
        alerts_by_severity=alerts_by_severity,
        alerts_by_status=alerts_by_status,
        fraud_rate=fraud_rate,
        total_payments=total_payments,
        fraudulent_payments=fraudulent_payments,
        alerted_customers=alerted_customers,
        total_customers=total_customers,
        customer_alert_coverage=customer_alert_coverage,
        top_fraud_reasons=top_fraud_reasons,
        alerts_by_hour=alerts_by_hour,
        alerts_by_day=alerts_by_day
    )

@app.get("/api/payments/stats", response_model=PaymentStats)
async def get_payment_stats(
    window_hours: int = Query(24, ge=1, le=720, description="Fenetre d'observation en heures")
):
    """KPIs paiements pour piloter le volume, les statuts et la fraude confirmee."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            COUNT(*)::INT AS total_payments,
            COALESCE(SUM(CASE WHEN COALESCE(payment_status, 'success') = 'success' THEN 1 ELSE 0 END), 0)::INT AS successful_payments,
            COALESCE(SUM(CASE WHEN COALESCE(payment_status, 'success') <> 'success' THEN 1 ELSE 0 END), 0)::INT AS failed_payments,
            COALESCE(SUM(CASE WHEN COALESCE(payment_status, 'success') = 'success' AND is_fraudulent THEN 1 ELSE 0 END), 0)::INT AS fraudulent_payments,
            MAX(payment_date) AS last_payment_at
        FROM payments
        WHERE payment_date >= NOW() - (%s || ' hours')::INTERVAL
        """,
        (window_hours,),
    )
    total_payments, successful_payments, failed_payments, fraudulent_payments, last_payment_at = cursor.fetchone()

    cursor.execute(
        """
        SELECT COALESCE(payment_method, 'unknown'), COUNT(*)
        FROM payments
        WHERE payment_date >= NOW() - (%s || ' hours')::INTERVAL
        GROUP BY payment_method
        ORDER BY COUNT(*) DESC, payment_method ASC
        """,
        (window_hours,),
    )
    payment_methods = dict(cursor.fetchall())

    cursor.execute(
        """
        SELECT COALESCE(payment_status, 'unknown'), COUNT(*)
        FROM payments
        WHERE payment_date >= NOW() - (%s || ' hours')::INTERVAL
        GROUP BY payment_status
        ORDER BY COUNT(*) DESC, payment_status ASC
        """,
        (window_hours,),
    )
    payment_statuses = dict(cursor.fetchall())

    cursor.close()
    conn.close()

    fraud_rate = round((fraudulent_payments / successful_payments) * 100, 2) if successful_payments else 0.0
    return PaymentStats(
        window_hours=window_hours,
        total_payments=int(total_payments or 0),
        successful_payments=int(successful_payments or 0),
        failed_payments=int(failed_payments or 0),
        fraudulent_payments=int(fraudulent_payments or 0),
        fraud_rate=fraud_rate,
        payment_methods=payment_methods,
        payment_statuses=payment_statuses,
        last_payment_at=str(last_payment_at) if last_payment_at else None,
    )

@app.get("/api/identity/verifications", response_model=List[IdentityVerificationRecord])
async def get_identity_verifications(
    status: Optional[str] = Query(None, description="Filter by status: pending, verified, rejected"),
    customer_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """Liste les vérifications d'identité avec filtres."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM identity_verifications WHERE 1=1"
    params = []

    if status:
        query += " AND verification_status = %s"
        params.append(status)

    if customer_id:
        query += " AND customer_id = %s"
        params.append(customer_id)

    query += " ORDER BY verification_date DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    cursor.execute(query, params)
    columns = [desc[0] for desc in cursor.description]
    results = []
    for row in cursor.fetchall():
        item = dict(zip(columns, row))
        item['verification_date'] = str(item['verification_date']) if item['verification_date'] else None
        item['created_at'] = str(item['created_at']) if item['created_at'] else None
        results.append(item)

    cursor.close()
    conn.close()
    return results

@app.post("/api/verify-id")
async def verify_identity(payload: IdentityVerificationRequest):
    """Enregistre une vérification d'identité manuelle/API (document hashé)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM customers WHERE customer_id = %s", (payload.customer_id,))
    if not cursor.fetchone():
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Customer not found")

    if payload.is_adult is True:
        verification_status = "verified"
    elif payload.is_adult is False:
        verification_status = "rejected"
    else:
        verification_status = "pending"
    cursor.close()
    conn.close()

    verification_id = insert_identity_verification_record(
        customer_id=payload.customer_id,
        document_number=payload.document_number,
        document_type=payload.document_type,
        verification_status=verification_status,
        verification_method=payload.verification_method,
        id_card_image_path=payload.id_card_image_path,
        verification_date=datetime.now(),
    )

    return {
        "message": "Identity verification saved",
        "verification_id": verification_id,
        "customer_id": payload.customer_id,
        "verification_status": verification_status,
        "document_number_stored_as": "sha256"
    }

@app.get("/api/identity/stats", response_model=IdentityStats)
async def get_identity_stats():
    """Statistiques des vérifications d'identité."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM identity_verifications")
    total_verifications = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COALESCE(verification_status, 'unknown'), COUNT(*)
        FROM identity_verifications
        GROUP BY verification_status
    """)
    by_status = dict(cursor.fetchall())

    cursor.execute("""
        SELECT COALESCE(verification_method, 'unknown'), COUNT(*)
        FROM identity_verifications
        GROUP BY verification_method
    """)
    by_method = dict(cursor.fetchall())

    cursor.close()
    conn.close()

    return IdentityStats(
        total_verifications=total_verifications,
        by_status=by_status,
        by_method=by_method
    )

@app.get("/api/products", response_model=List[ProductCatalogItem])
async def get_products(
    adult_only: bool = Query(False, description="Retourne uniquement les produits catégorie Adult"),
    only_in_stock: bool = Query(False, description="Retourne uniquement les produits avec stock > 0"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """Catalogue produits pour pilotage des commandes API."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT product_id, name, category, price, stock_quantity
        FROM products
        WHERE 1=1
    """
    params = []

    if adult_only:
        query += " AND LOWER(category) = 'adult'"
    if only_in_stock:
        query += " AND stock_quantity > 0"

    query += " ORDER BY product_id LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    cursor.execute(query, params)

    items = []
    for row in cursor.fetchall():
        category = row[2]
        items.append(ProductCatalogItem(
            product_id=row[0],
            name=row[1],
            category=category,
            price=float(row[3]),
            stock_quantity=int(row[4]),
            is_adult_restricted=is_adult_restricted(category)
        ))

    cursor.close()
    conn.close()
    return items

@app.get("/api/id-cards", response_model=List[IdCardPreview])
async def get_id_cards(
    adult: Optional[bool] = Query(None, description="true=18+, false=<18"),
    limit: int = Query(60, ge=1, le=500)
):
    """
    Retourne un aperçu des cartes d'identité synthétiques.
    La date de naissance est extraite du dataset des cartes (labels associés aux PNG).
    """
    labels = load_id_labels()
    rows = []
    for file_name, birthdate in sorted(labels.items()):
        age = compute_age(birthdate)
        is_adult = age >= 18
        if adult is not None and is_adult != adult:
            continue
        rows.append(IdCardPreview(
            file=file_name,
            birthdate=birthdate,
            age=age,
            is_adult=is_adult
        ))
        if len(rows) >= limit:
            break
    return rows


@app.get("/api/id-cards/{file_name}/analysis", response_model=IdCardAnalysis)
async def get_id_card_analysis(file_name: str):
    """
    Retourne une lecture détaillée d'une CNI synthétique.
    Cette vue sert à la démonstration détaillée côté dashboard identité.
    """
    safe_name = Path(file_name).name
    records = load_id_label_records()
    record = records.get(safe_name)
    if not record:
        raise HTTPException(status_code=404, detail=f"ID card metadata not found: {safe_name}")

    card_path = ID_CARDS_DIR / safe_name
    if not card_path.exists():
        raise HTTPException(status_code=404, detail=f"ID card image not found: {safe_name}")

    image_sha256 = hashlib.sha256(card_path.read_bytes()).hexdigest()
    model_enabled = os.getenv("ID_CARD_MODEL_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    fingerprint_birthdate = None
    if model_enabled:
        try:
            fingerprint_birthdate = predict_birthdate_from_id_fingerprint(card_path)
        except Exception:
            fingerprint_birthdate = None
    model = load_id_fingerprint_model() if model_enabled else {}
    birthdate = record["birthdate"]
    age = compute_age(birthdate)

    return IdCardAnalysis(
        file=safe_name,
        first_name=record.get("first_name"),
        last_name=record.get("last_name"),
        sex=record.get("sex"),
        birthdate=birthdate,
        age=age,
        is_adult=age >= 18,
        doc_number=record.get("doc_number"),
        expiry=record.get("expiry"),
        expired=is_expired_document(record.get("expiry")),
        image_url=f"/api/id-cards/image/{safe_name}",
        image_sha256=image_sha256,
        backend_analysis_source="fingerprint_model" if fingerprint_birthdate else "labels_fallback",
        fingerprint_birthdate=fingerprint_birthdate,
        fingerprint_match=bool(fingerprint_birthdate and fingerprint_birthdate == birthdate),
        model_enabled=model_enabled,
        model_version=model.get("version") if model else None,
    )

@app.get("/api/id-cards/image/{file_name}")
async def get_id_card_image(file_name: str):
    """Expose une image synthetic_id_card pour affichage dashboard."""
    safe_name = Path(file_name).name
    card_path = ID_CARDS_DIR / safe_name
    if not card_path.exists():
        raise HTTPException(status_code=404, detail=f"ID card image not found: {safe_name}")
    return FileResponse(card_path)

@app.get("/api/fraud/reasons/stats", response_model=List[FraudReasonStat])
async def get_fraud_reason_stats(
    window_hours: int = Query(24, ge=1, le=720, description="Fenêtre d'observation en heures")
):
    """
    Distribution des types de fraude (raisons) pour dashboard typologies.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        WITH reason_rows AS (
            SELECT
                TRIM(UNNEST(string_to_array(fraud_reasons, ','))) AS reason,
                severity
            FROM fraud_alerts
            WHERE fraud_reasons IS NOT NULL
              AND fraud_reasons <> ''
              AND alert_timestamp >= NOW() - (%s || ' hours')::INTERVAL
        )
        SELECT
            reason,
            COUNT(*)::INT AS total,
            COALESCE(SUM(CASE WHEN severity = 'HIGH' THEN 1 ELSE 0 END), 0)::INT AS high,
            COALESCE(SUM(CASE WHEN severity = 'MEDIUM' THEN 1 ELSE 0 END), 0)::INT AS medium,
            COALESCE(SUM(CASE WHEN severity = 'LOW' THEN 1 ELSE 0 END), 0)::INT AS low
        FROM reason_rows
        GROUP BY reason
        ORDER BY total DESC, reason ASC
    """, (window_hours,))

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    return [
        FraudReasonStat(
            reason=row[0],
            total=row[1],
            high=row[2],
            medium=row[3],
            low=row[4]
        )
        for row in rows
    ]

@app.get("/api/fraud/reasons/{reason}/alerts", response_model=List[FraudAlert])
async def get_alerts_by_reason(
    reason: str,
    limit: int = Query(100, ge=1, le=1000)
):
    """
    Alertes associées à une raison précise (ex: FIRST_PAYMENT, VELOCITY_HIGH).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM fraud_alerts
        WHERE %s = ANY(string_to_array(fraud_reasons, ','))
        ORDER BY alert_timestamp DESC
        LIMIT %s
    """, (reason, limit))

    columns = [desc[0] for desc in cursor.description]
    results = []

    for row in cursor.fetchall():
        alert_dict = dict(zip(columns, row))
        alert_dict['fraud_reasons'] = alert_dict['fraud_reasons'].split(',') if alert_dict['fraud_reasons'] else []
        alert_dict['alert_timestamp'] = str(alert_dict['alert_timestamp'])
        alert_dict['event_timestamp'] = str(alert_dict['event_timestamp']) if alert_dict['event_timestamp'] else None
        alert_dict['decided_at'] = str(alert_dict['decided_at']) if alert_dict['decided_at'] else None
        results.append(alert_dict)

    cursor.close()
    conn.close()
    return results

@app.post("/api/orders/checkout", response_model=CheckoutResponse)
async def create_checkout_order(payload: CheckoutRequest):
    """
    Création d'une commande client via API avec garde-fou majorité:
    - Lit la date de naissance via la carte d'identité synthétique (id.png + labels)
    - Refuse les produits catégorie Adult si âge < 18 ans
    """
    if not payload.items:
        raise HTTPException(status_code=400, detail="At least one item is required")

    safe_card_name, birthdate_str, age = extract_age_from_id_card(payload.id_card_file)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT country FROM customers WHERE customer_id = %s", (payload.customer_id,))
        customer_row = cursor.fetchone()
        if not customer_row:
            raise HTTPException(status_code=404, detail=f"Customer not found: {payload.customer_id}")
        customer_country = customer_row[0] or "FR"

        cursor.execute("SELECT COUNT(*) FROM orders WHERE customer_id = %s", (payload.customer_id,))
        previous_orders = int(cursor.fetchone()[0] or 0)

        quantities_by_product = defaultdict(int)
        for item in payload.items:
            quantities_by_product[item.product_id] += item.quantity

        product_ids = list(quantities_by_product.keys())
        placeholders = ",".join(["%s"] * len(product_ids))
        cursor.execute(f"""
            SELECT product_id, name, category, price, stock_quantity
            FROM products
            WHERE product_id IN ({placeholders})
            FOR UPDATE
        """, product_ids)
        products = {row[0]: row for row in cursor.fetchall()}

        missing = [pid for pid in product_ids if pid not in products]
        if missing:
            raise HTTPException(status_code=400, detail=f"Unknown product_id(s): {missing}")

        blocked_adult_products = []
        contains_adult_product = False
        total_amount = 0.0
        for product_id, qty in quantities_by_product.items():
            _, _, category, unit_price, stock_qty = products[product_id]
            product_is_adult = is_adult_restricted(category)
            if product_is_adult:
                contains_adult_product = True
            if age < 18 and product_is_adult:
                blocked_adult_products.append(product_id)
            if qty > int(stock_qty):
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient stock for product {product_id}: requested={qty}, stock={stock_qty}"
                )
            total_amount += float(unit_price) * qty

        if blocked_adult_products:
            # Matérialise le contrôle 18+ sur le dashboard via table d'audit dédiée.
            try:
                log_checkout_attempt(
                    customer_id=payload.customer_id,
                    id_card_file=safe_card_name,
                    customer_age=age,
                    contains_adult_product=contains_adult_product,
                    blocked_underage=True,
                    accepted=False,
                    blocked_products=blocked_adult_products,
                    total_amount=total_amount,
                    notes="Blocked underage for adult products"
                )
            except Exception as log_error:
                print(f"Erreur log checkout (blocked): {log_error}")

            try:
                emit_checkout_security_events(
                    customer_id=payload.customer_id,
                    id_card_file=safe_card_name,
                    birthdate_str=birthdate_str,
                    customer_country=customer_country,
                    previous_orders=previous_orders,
                    blocked_underage=True,
                    contains_adult_product=contains_adult_product,
                )
            except Exception as security_error:
                print(f"Erreur events checkout (blocked): {security_error}")

            raise HTTPException(
                status_code=403,
                detail={
                    "message": "Adult products are restricted to 18+ customers",
                    "customer_age": age,
                    "id_card_file": safe_card_name,
                    "birthdate": birthdate_str,
                    "blocked_products": sorted(blocked_adult_products)
                }
            )

        address_id = get_or_create_customer_address(cursor, payload.customer_id)

        # Génération robuste d'identifiant de commande sous concurrence
        cursor.execute("LOCK TABLE orders IN EXCLUSIVE MODE")
        cursor.execute("SELECT COALESCE(MAX(order_id), 0) + 1 FROM orders")
        next_order_id = cursor.fetchone()[0]

        now = datetime.now()
        cursor.execute("""
            INSERT INTO orders (
                order_id, customer_id, order_date, total_amount, status,
                shipping_address_id, billing_address_id, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            next_order_id,
            payload.customer_id,
            now,
            round(total_amount, 2),
            "pending",
            address_id,
            address_id,
            now
        ))

        for product_id, qty in quantities_by_product.items():
            unit_price = float(products[product_id][3])
            cursor.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, unit_price, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (next_order_id, product_id, qty, unit_price, now))

            cursor.execute("""
                UPDATE products
                SET stock_quantity = stock_quantity - %s
                WHERE product_id = %s
            """, (qty, product_id))

        payment_profile = insert_checkout_payment(
            cursor,
            order_id=next_order_id,
            customer_id=payload.customer_id,
            customer_age=age,
            total_amount=total_amount,
            payment_method=payload.payment_method,
            customer_country=customer_country,
            previous_orders=previous_orders,
            contains_adult_product=contains_adult_product,
            created_at=now,
            risk_profile=payload.risk_profile,
        )

        conn.commit()

        publish_live_event("payment_event", {
            "payment_id": payment_profile["payment_id"],
            "order_id": next_order_id,
            "customer_id": payload.customer_id,
            "amount": payment_profile["amount"],
            "payment_method": payment_profile["payment_method"],
            "payment_status": payment_profile["payment_status"],
            "is_fraudulent": payment_profile["is_fraudulent"],
            "risk_score": payment_profile["risk_score"],
            "review_required": payment_profile["review_required"],
            "payment_date": payment_profile["payment_date"],
        })

        try:
            log_checkout_attempt(
                customer_id=payload.customer_id,
                id_card_file=safe_card_name,
                customer_age=age,
                contains_adult_product=contains_adult_product,
                blocked_underage=False,
                accepted=True,
                blocked_products=[],
                total_amount=total_amount,
                order_id=next_order_id,
                notes=(
                    f"Checkout accepted; payment_id={payment_profile['payment_id']} "
                    f"method={payment_profile['payment_method']} "
                    f"risk_score={payment_profile['risk_score']} "
                    f"fraud={str(payment_profile['is_fraudulent']).lower()}"
                ),
            )
        except Exception as log_error:
            print(f"Erreur log checkout (accepted): {log_error}")

        try:
            emit_checkout_security_events(
                customer_id=payload.customer_id,
                id_card_file=safe_card_name,
                birthdate_str=birthdate_str,
                customer_country=customer_country,
                previous_orders=previous_orders,
                blocked_underage=False,
                contains_adult_product=contains_adult_product,
            )
        except Exception as security_error:
            print(f"Erreur events checkout (accepted): {security_error}")

        try:
            payment_alert = build_checkout_payment_alert(payment_profile, previous_orders)
            if payment_alert:
                insert_fraud_alert(payment_alert, send_notification=True)
        except Exception as payment_alert_error:
            print(f"Erreur alerting paiement checkout: {payment_alert_error}")

        return CheckoutResponse(
            accepted=True,
            order_id=next_order_id,
            payment_id=payment_profile["payment_id"],
            payment_status=payment_profile["payment_status"],
            payment_is_fraudulent=payment_profile["is_fraudulent"],
            payment_risk_score=payment_profile["risk_score"],
            customer_id=payload.customer_id,
            id_card_file=safe_card_name,
            customer_age=age,
            total_amount=round(total_amount, 2),
            created_at=now.isoformat()
        )

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Checkout failed: {e}")
    finally:
        cursor.close()
        conn.close()

@app.get("/api/checkout/stats", response_model=CheckoutStats)
async def get_checkout_stats(
    window_hours: int = Query(24, ge=1, le=720, description="Fenêtre d'observation en heures")
):
    """
    KPIs checkout API pour matérialiser le contrôle de majorité sur dashboard.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*)::INT AS total_attempts,
            COALESCE(SUM(CASE WHEN accepted THEN 1 ELSE 0 END), 0)::INT AS accepted_orders,
            COALESCE(SUM(CASE WHEN blocked_underage THEN 1 ELSE 0 END), 0)::INT AS blocked_underage_orders,
            COALESCE(SUM(CASE WHEN contains_adult_product THEN 1 ELSE 0 END), 0)::INT AS adult_product_attempts,
            COALESCE(SUM(CASE WHEN contains_adult_product AND blocked_underage THEN 1 ELSE 0 END), 0)::INT AS adult_product_rejected,
            COALESCE(AVG(customer_age), 0)::FLOAT AS avg_customer_age,
            MAX(attempted_at) AS last_attempt_at
        FROM checkout_attempts
        WHERE attempted_at >= NOW() - (%s || ' hours')::INTERVAL
    """, (window_hours,))

    row = cursor.fetchone()
    cursor.close()
    conn.close()

    total_attempts = int(row[0] or 0)
    accepted_orders = int(row[1] or 0)
    blocked_underage_orders = int(row[2] or 0)
    adult_product_attempts = int(row[3] or 0)
    adult_product_rejected = int(row[4] or 0)
    avg_customer_age = float(row[5] or 0.0)
    last_attempt_at = row[6]

    rejection_rate = round((blocked_underage_orders / total_attempts) * 100, 2) if total_attempts > 0 else 0.0
    adult_rejection_rate = round((adult_product_rejected / adult_product_attempts) * 100, 2) if adult_product_attempts > 0 else 0.0

    return CheckoutStats(
        window_hours=window_hours,
        total_attempts=total_attempts,
        accepted_orders=accepted_orders,
        blocked_underage_orders=blocked_underage_orders,
        rejection_rate=rejection_rate,
        adult_product_attempts=adult_product_attempts,
        adult_product_rejected=adult_product_rejected,
        adult_rejection_rate=adult_rejection_rate,
        avg_customer_age=round(avg_customer_age, 2),
        last_attempt_at=last_attempt_at.isoformat() if last_attempt_at else None
    )

@app.get("/api/checkout/attempts", response_model=List[CheckoutAttemptRecord])
async def get_checkout_attempts(
    blocked_underage: Optional[bool] = Query(None),
    accepted: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """
    Historique des tentatives checkout API (support dashboard mineurs/ID cards).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            attempt_id, attempted_at, customer_id, id_card_file, customer_age,
            contains_adult_product, blocked_underage, accepted, blocked_products,
            total_amount, order_id, notes
        FROM checkout_attempts
        WHERE 1=1
    """
    params = []

    if blocked_underage is not None:
        query += " AND blocked_underage = %s"
        params.append(blocked_underage)

    if accepted is not None:
        query += " AND accepted = %s"
        params.append(accepted)

    query += " ORDER BY attempted_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    cursor.execute(query, params)

    records = []
    for row in cursor.fetchall():
        records.append(CheckoutAttemptRecord(
            attempt_id=row[0],
            attempted_at=str(row[1]) if row[1] else "",
            customer_id=row[2],
            id_card_file=row[3],
            customer_age=row[4],
            contains_adult_product=bool(row[5]),
            blocked_underage=bool(row[6]),
            accepted=bool(row[7]),
            blocked_products=row[8],
            total_amount=float(row[9]) if row[9] is not None else None,
            order_id=row[10],
            notes=row[11]
        ))

    cursor.close()
    conn.close()
    return records

@app.post("/api/runtime/refresh", response_model=RuntimeRefreshResponse)
async def runtime_refresh(payload: RuntimeRefreshRequest):
    """
    Refresh runtime unifié:
    - sync Kafka -> PostgreSQL
    - lancement scaling commandes API
    - redémarrage API (optionnel)
    """
    synced_alerts = 0
    started_orders = False
    orders_pid = None
    started_alerts = False
    alerts_pid = None
    messages = []

    append_runtime_log(
        "Runtime refresh demandé "
        f"(sync={payload.sync_kafka}, scaling_orders={payload.run_scaling}, scaling_alerts={payload.run_alert_scaling}, "
        f"restart_api={payload.restart_api}, order_mode={payload.scaling_mode}, order_requests={payload.requests}, "
        f"order_concurrency={payload.concurrency}, order_duration={payload.duration_seconds}, order_rps={payload.rps}, "
        f"alerts_mode={payload.alerts_mode}, alerts_requests={payload.alerts_requests}, "
        f"alerts_concurrency={payload.alerts_concurrency}, alerts_duration={payload.alerts_duration_seconds}, "
        f"alerts_rps={payload.alerts_rps})"
    )

    if payload.sync_kafka:
        synced_alerts = sync_alerts_from_kafka(max_messages=payload.max_sync_messages)
        messages.append(f"sync={synced_alerts}")
    else:
        messages.append("sync=skipped")

    if payload.run_scaling:
        started_orders, orders_pid, scaling_message = start_scaling_process(
            scaling_mode=payload.scaling_mode,
            requests=payload.requests,
            concurrency=payload.concurrency,
            adult_order_ratio=payload.adult_order_ratio,
            minor_ratio=payload.minor_ratio,
            duration_seconds=payload.duration_seconds,
            rps=payload.rps
        )
        messages.append(scaling_message)
    else:
        messages.append("order scaling skipped")

    if payload.run_alert_scaling:
        started_alerts, alerts_pid, alert_scaling_message = start_alert_scaling_process(
            alerts_mode=payload.alerts_mode,
            alerts_requests=payload.alerts_requests,
            alerts_concurrency=payload.alerts_concurrency,
            alerts_duration_seconds=payload.alerts_duration_seconds,
            alerts_rps=payload.alerts_rps,
            high_severity_ratio=payload.high_severity_ratio
        )
        messages.append(alert_scaling_message)
    else:
        messages.append("alert scaling skipped")

    if payload.restart_api:
        restart_delay = 1.2
        if payload.run_scaling and payload.scaling_mode == "realtime":
            restart_delay = max(restart_delay, min(float(payload.duration_seconds) + 2.0, 120.0))
        elif payload.run_scaling:
            restart_delay = max(restart_delay, 3.0)

        if payload.run_alert_scaling and payload.alerts_mode == "realtime":
            restart_delay = max(restart_delay, min(float(payload.alerts_duration_seconds) + 2.0, 120.0))
        elif payload.run_alert_scaling:
            restart_delay = max(restart_delay, 3.0)

        schedule_api_restart(delay_seconds=restart_delay)
        messages.append(f"API restart planifié (+{restart_delay:.1f}s)")
    else:
        messages.append("API restart désactivé")

    return RuntimeRefreshResponse(
        started_orders=started_orders,
        orders_pid=orders_pid,
        started_alerts=started_alerts,
        alerts_pid=alerts_pid,
        synced_alerts=synced_alerts,
        scaling_mode=payload.scaling_mode,
        requests=payload.requests,
        concurrency=payload.concurrency,
        duration_seconds=payload.duration_seconds,
        rps=payload.rps,
        alerts_mode=payload.alerts_mode,
        alerts_requests=payload.alerts_requests,
        alerts_concurrency=payload.alerts_concurrency,
        alerts_duration_seconds=payload.alerts_duration_seconds,
        alerts_rps=payload.alerts_rps,
        log_file=str(RUNTIME_LOG_FILE),
        message=" | ".join(messages)
    )

@app.get("/api/runtime/logs")
async def runtime_logs(
    lines: int = Query(80, ge=1, le=500)
):
    """Retourne les dernières lignes du log runtime refresh."""
    if not RUNTIME_LOG_FILE.exists():
        return {"log_file": str(RUNTIME_LOG_FILE), "lines": []}

    with RUNTIME_LOG_FILE.open("r", encoding="utf-8") as f:
        rows = f.read().splitlines()
    return {"log_file": str(RUNTIME_LOG_FILE), "lines": rows[-lines:]}

@app.post("/api/sync")
async def sync_from_kafka():
    """
    Force une synchronisation depuis Kafka
    """
    count = sync_alerts_from_kafka(max_messages=5000)
    return {"message": f"Synchronized {count} alerts from Kafka"}

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

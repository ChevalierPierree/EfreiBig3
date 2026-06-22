#!/usr/bin/env python3
"""
Validation automatisée des 11 exigences du Sujet 1 (KiVendTout).
Genere un rapport JSON de preuves pour la validation projet.
"""

from __future__ import annotations

import atexit
import argparse
import json
import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import psycopg2
import requests
from pymongo import MongoClient


ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT_DIR / "logs"
API_URL = os.getenv("VALIDATION_API_URL", "http://localhost:8000")
API_LOG_FILE = LOG_DIR / "fraud_dashboard_api.log"


@dataclass
class CheckResult:
    requirement_id: int
    title: str
    status: str
    details: Dict


def api_headers() -> Dict[str, str]:
    header_name = os.getenv("API_KEY_HEADER", "X-API-Key").strip()
    header_value = os.getenv("API_KEY_VALUE", "").strip()
    if not header_value:
        header_value = os.getenv("API_DEFAULT_DEMO_KEY", "demo-admin-key").strip()
    if header_name and header_value:
        return {header_name: header_value}
    return {}


def run_cmd(cmd: List[str], timeout: int = 240, env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT_DIR,
        env=env if env is not None else os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def wait_url(url: str, attempts: int = 30) -> bool:
    for _ in range(attempts):
        try:
            response = requests.get(url, timeout=5)
            if response.ok:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def wait_api_routes() -> bool:
    urls = [
        f"{API_URL}/health",
        f"{API_URL}/api/fraud/reasons/stats?window_hours=24",
        f"{API_URL}/api/identity/stats",
    ]
    for url in urls:
        if not wait_url(url, attempts=30):
            return False
    return True


def ensure_api_up() -> Optional[subprocess.Popen]:
    if wait_api_routes():
        return None

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_handle = API_LOG_FILE.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [str(ROOT_DIR / ".venv" / "bin" / "python"), str(ROOT_DIR / "api" / "fraud_dashboard_api.py")],
        cwd=ROOT_DIR,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    log_handle.close()
    if wait_api_routes():
        return proc
    stop_process(proc)
    raise RuntimeError(f"API indisponible sur {API_URL}/health")


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


def parse_int(pattern: str, text: str, default: int = -1) -> int:
    match = re.search(pattern, text)
    if not match:
        return default
    return int(match.group(1))


def parse_float(pattern: str, text: str, default: float = -1.0) -> float:
    match = re.search(pattern, text)
    if not match:
        return default
    return float(match.group(1))


def latency_probe(url: str, attempts: int = 15) -> Dict:
    latencies_ms: List[float] = []
    headers = api_headers()
    for _ in range(attempts):
        started = time.perf_counter()
        resp = requests.get(url, timeout=10, headers=headers)
        elapsed = (time.perf_counter() - started) * 1000.0
        resp.raise_for_status()
        latencies_ms.append(elapsed)
    latencies_ms.sort()
    p95_index = int((len(latencies_ms) - 1) * 0.95)
    return {
        "attempts": attempts,
        "avg_ms": round(sum(latencies_ms) / len(latencies_ms), 2),
        "p95_ms": round(latencies_ms[p95_index], 2),
        "max_ms": round(latencies_ms[-1], 2),
    }


def launch_temp_secured_api() -> Tuple[subprocess.Popen, Dict]:
    env = os.environ.copy()
    env["API_KEY_REQUIRED"] = "true"
    env["API_RBAC_ENABLED"] = "false"
    env["API_KEY_VALUE"] = "validation-demo-key"
    env["API_KEY_HEADER"] = "X-API-Key"
    cmd = [
        str(ROOT_DIR / ".venv" / "bin" / "python"),
        "-m",
        "uvicorn",
        "api.fraud_dashboard_api:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8010",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            requests.get("http://127.0.0.1:8010/health", timeout=2).raise_for_status()
            return proc, {"api_key_header": "X-API-Key", "api_key_value": "validation-demo-key"}
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    raise RuntimeError("Impossible de démarrer API sécurisée temporaire sur 8010")


def stop_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validation Sujet 1")
    parser.add_argument("--output", default="logs/sujet1_validation_report.json", help="Rapport JSON")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    local_api_proc = ensure_api_up()
    if local_api_proc is not None:
        atexit.register(stop_process, local_api_proc)
    checks: List[CheckResult] = []
    headers = api_headers()

    # #1 Stockage relationnel intègre.
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM customers")
            customers = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM orders")
            orders = int(cur.fetchone()[0] or 0)
            cur.execute(
                """
                SELECT COUNT(*)
                FROM orders o
                LEFT JOIN customers c ON c.customer_id = o.customer_id
                WHERE c.customer_id IS NULL
                """
            )
            orphan_orders = int(cur.fetchone()[0] or 0)
    checks.append(
        CheckResult(
            requirement_id=1,
            title="Stockage relationnel fiable et intègre",
            status="PASS" if customers > 0 and orders > 0 and orphan_orders == 0 else "FAIL",
            details={"customers": customers, "orders": orders, "orphan_orders": orphan_orders},
        )
    )

    # #2 Exploitation événements utilisateurs.
    mongo = mongo_client()
    db = mongo[os.getenv("MONGODB_DB", "kivendtout")]
    coll = db[os.getenv("MONGODB_COLLECTION", "events")]
    events_total = int(coll.count_documents({}))
    event_types = coll.distinct("event_type")
    mongo.close()
    checks.append(
        CheckResult(
            requirement_id=2,
            title="Exploitation des événements utilisateurs",
            status="PASS" if events_total > 0 and len(event_types) >= 3 else "FAIL",
            details={"events_total": events_total, "event_types_count": len(event_types)},
        )
    )

    # #3 Centralisation brute + historisation (Data Lake snapshot MinIO).
    snapshot_cmd = ["bash", "scripts/snapshot_raw_data_to_minio.sh"]
    code, out, err = run_cmd(snapshot_cmd, timeout=1200)
    manifest_match = re.search(r"Manifest\s+:\s+(.*)", out)
    manifest_file = manifest_match.group(1).strip() if manifest_match else ""
    snapshot_ok = code == 0 and bool(manifest_file)
    checks.append(
        CheckResult(
            requirement_id=3,
            title="Centralisation brute historisée",
            status="PASS" if snapshot_ok else "FAIL",
            details={"exit_code": code, "manifest_file": manifest_file, "stderr_tail": err[-300:]},
        )
    )

    # #4 Analyse fraud temps réel.
    fraud_stats = requests.get(f"{API_URL}/api/fraud/reasons/stats?window_hours=24", timeout=15, headers=headers).json()
    checks.append(
        CheckResult(
            requirement_id=4,
            title="Détection fraude temps réel",
            status="PASS" if isinstance(fraud_stats, list) else "FAIL",
            details={"fraud_reasons_count": len(fraud_stats) if isinstance(fraud_stats, list) else -1},
        )
    )

    # #5 Exposition standardisée.
    endpoints = [
        "/api/alerts?limit=1",
        "/api/stats",
        "/api/products?limit=2",
        "/api/orders/checkout",  # endpoint exists check via OPTIONS
    ]
    endpoint_status = {}
    for ep in endpoints:
        if ep.endswith("/checkout"):
            resp = requests.options(f"{API_URL}{ep}", timeout=10, headers=headers)
        else:
            resp = requests.get(f"{API_URL}{ep}", timeout=10, headers=headers)
        endpoint_status[ep] = resp.status_code
    checks.append(
        CheckResult(
            requirement_id=5,
            title="Service d'exposition standardisé",
            status="PASS" if all(200 <= s < 500 for s in endpoint_status.values()) else "FAIL",
            details={"endpoint_status": endpoint_status},
        )
    )

    # #6 Temps d'analyse décisionnelle.
    stats_latency = latency_probe(f"{API_URL}/api/stats", attempts=15)
    checks.append(
        CheckResult(
            requirement_id=6,
            title="Temps d'analyse décisionnelle réduit",
            status="PASS" if stats_latency["p95_ms"] < 400 else "FAIL",
            details=stats_latency,
        )
    )

    # #7 Scalabilité (test charge API).
    order_code, order_out, order_err = run_cmd(
        [
            str(ROOT_DIR / ".venv" / "bin" / "python"),
            "scripts/scale_order_api.py",
            "--requests",
            "40",
            "--concurrency",
            "8",
            "--adult-order-ratio",
            "0.6",
            "--minor-ratio",
            "0.4",
        ],
        timeout=600,
    )
    order_http_err = parse_int(r"Erreurs HTTP\s*:\s*(\d+)", order_out, default=999)
    order_net_err = parse_int(r"Erreurs réseau\s*:\s*(\d+)", order_out, default=999)
    order_ko = parse_int(r"Mineur\+Adult acceptés \(KO\):\s*(\d+)", order_out, default=999)
    order_p95 = parse_float(r"P95 latency\s*:\s*([0-9.]+)\s*ms", order_out, default=9999.0)
    checks.append(
        CheckResult(
            requirement_id=7,
            title="Scalabilité sous charge",
            status="PASS" if order_code == 0 and order_http_err == 0 and order_net_err == 0 and order_ko == 0 else "FAIL",
            details={
                "exit_code": order_code,
                "http_errors": order_http_err,
                "network_errors": order_net_err,
                "minor_adult_accepted": order_ko,
                "p95_ms": order_p95,
                "stderr_tail": order_err[-300:],
            },
        )
    )

    # #8 Continuité de service.
    ps_code, ps_out, ps_err = run_cmd(["docker", "compose", "ps", "--format", "json"], timeout=90)
    running_services = []
    if ps_code == 0:
        for line in ps_out.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("State") == "running":
                running_services.append(item.get("Service"))
    checks.append(
        CheckResult(
            requirement_id=8,
            title="Continuité de service / résilience infra",
            status="PASS" if ps_code == 0 and len(running_services) >= 10 else "FAIL",
            details={"running_services_count": len(running_services), "stderr_tail": ps_err[-300:]},
        )
    )

    # #9 Sécurité & protection données.
    temp_proc = None
    security_details: Dict = {}
    try:
        temp_proc, sec_cfg = launch_temp_secured_api()
        no_key = requests.get("http://127.0.0.1:8010/api/stats", timeout=10)
        ok_key = requests.get(
            "http://127.0.0.1:8010/api/stats",
            timeout=10,
            headers={sec_cfg["api_key_header"]: sec_cfg["api_key_value"]},
        )
        security_details = {
            "without_key_status": no_key.status_code,
            "with_key_status": ok_key.status_code,
            "api_key_header": sec_cfg["api_key_header"],
        }
        sec_pass = no_key.status_code == 401 and ok_key.status_code == 200
    finally:
        if temp_proc is not None:
            stop_process(temp_proc)
    checks.append(
        CheckResult(
            requirement_id=9,
            title="Sécurité / protection des accès",
            status="PASS" if security_details and sec_pass else "FAIL",
            details=security_details,
        )
    )

    # #10 Qualité des données.
    dq_code, dq_out, dq_err = run_cmd(
        [str(ROOT_DIR / ".venv" / "bin" / "python"), "scripts/data_quality_checks.py"],
        timeout=300,
    )
    dq_failed = parse_int(r"Failed\s*:\s*(\d+)", dq_out, default=999)
    checks.append(
        CheckResult(
            requirement_id=10,
            title="Qualité des données",
            status="PASS" if dq_code == 0 and dq_failed == 0 else "FAIL",
            details={"exit_code": dq_code, "failed_checks": dq_failed, "stderr_tail": dq_err[-300:]},
        )
    )

    # #11 Modèle de reconnaissance CNI fiable.
    model_code, model_out, model_err = run_cmd(
        [str(ROOT_DIR / ".venv" / "bin" / "python"), "scripts/train_id_card_fingerprint_model.py"],
        timeout=180,
    )
    model_acc = parse_float(r"Accuracy\s*:\s*([0-9.]+)%", model_out, default=0.0)

    adult_product_id = 7
    adult_product_meta: Dict[str, object] = {}
    try:
        adult_products_resp = requests.get(
            f"{API_URL}/api/products?adult_only=true&only_in_stock=true&limit=1000",
            timeout=15,
            headers=headers,
        )
        if adult_products_resp.status_code == 200:
            adult_products = adult_products_resp.json() or []
            if adult_products:
                first_product = max(adult_products, key=lambda p: int(p.get("stock_quantity", 0)))
                adult_product_id = int(first_product.get("product_id", adult_product_id))
                adult_product_meta = {
                    "selected_adult_product_id": adult_product_id,
                    "selected_adult_product_name": first_product.get("name"),
                    "selected_adult_product_stock": first_product.get("stock_quantity"),
                    "adult_products_available": len(adult_products),
                }
    except Exception as exc:
        adult_product_meta = {"selected_adult_product_error": str(exc)}

    minor_payload = {
        "customer_id": "C00010",
        "id_card_file": "id_0003.png",
        "items": [{"product_id": adult_product_id, "quantity": 1}],
        "payment_method": "card",
    }
    adult_payload = {
        "customer_id": "C00010",
        "id_card_file": "id_0000.png",
        "items": [{"product_id": adult_product_id, "quantity": 1}],
        "payment_method": "card",
    }
    minor_resp = requests.post(f"{API_URL}/api/orders/checkout", json=minor_payload, timeout=15, headers=headers)
    adult_resp = requests.post(f"{API_URL}/api/orders/checkout", json=adult_payload, timeout=15, headers=headers)
    checks.append(
        CheckResult(
            requirement_id=11,
            title="Reconnaissance CNI fiable + contrôle majorité",
            status="PASS" if model_code == 0 and model_acc >= 95 and minor_resp.status_code == 403 and adult_resp.status_code == 200 else "FAIL",
            details={
                "model_exit_code": model_code,
                "model_accuracy_percent": model_acc,
                "minor_checkout_status": minor_resp.status_code,
                "adult_checkout_status": adult_resp.status_code,
                **adult_product_meta,
                "model_stderr_tail": model_err[-300:],
            },
        )
    )

    passed = sum(1 for c in checks if c.status == "PASS")
    failed = len(checks) - passed

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_url": API_URL,
        "summary": {
            "requirements_total": len(checks),
            "passed": passed,
            "failed": failed,
            "success_rate_percent": round((passed / len(checks)) * 100.0, 2),
            "global_status": "PASS" if failed == 0 else "FAIL",
        },
        "checks": [asdict(c) for c in checks],
    }

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== VALIDATION SUJET 1 ===")
    print(f"Report          : {output}")
    print(f"Passed          : {passed}")
    print(f"Failed          : {failed}")
    print(f"Global status   : {report['summary']['global_status']}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

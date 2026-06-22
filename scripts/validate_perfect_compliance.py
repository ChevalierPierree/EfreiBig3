#!/usr/bin/env python3
"""
Validation ciblée des points de conformité "parfaite":
1) RBAC + rate limit
2) Sécurité Data Lake + promotion bronze/silver/gold
3) Flux micro-batch
4) Tests charge DB + résilience
5) KPI de transfert standardisés
"""

from __future__ import annotations

import atexit
import argparse
import json
import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests


ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT_DIR / "logs"
API_URL = os.getenv("VALIDATION_API_URL", "http://localhost:8000")
API_LOG_FILE = LOG_DIR / "fraud_dashboard_api.log"


@dataclass
class Check:
    item: str
    status: str
    details: Dict


def run_cmd(cmd: List[str], timeout: int = 300) -> Tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def stop_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


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


def ensure_api_up() -> Optional[subprocess.Popen]:
    if wait_url(f"{API_URL}/health", attempts=3):
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
    if wait_url(f"{API_URL}/health", attempts=30):
        return proc
    stop_process(proc)
    raise RuntimeError(f"API indisponible sur {API_URL}/health")


def load_json(path: Path) -> Optional[Dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def latest_promotion_report() -> Optional[Dict]:
    reports = sorted((LOG_DIR).glob("data_lake_promotion_*.json"), reverse=True)
    for report in reports:
        payload = load_json(report)
        if payload:
            payload["report_file"] = str(report)
            return payload
    return None


def analytics_report() -> Optional[Dict]:
    report_path = LOG_DIR / "analytics_warehouse_report.json"
    report = load_json(report_path)
    if report:
        report["report_file"] = str(report_path)
    return report


def api_headers() -> Dict[str, str]:
    header_name = os.getenv("API_KEY_HEADER", "X-API-Key").strip()
    header_value = os.getenv("API_KEY_VALUE", "").strip()
    if not header_value:
        header_value = os.getenv("API_DEFAULT_DEMO_KEY", "demo-admin-key").strip()
    if header_name and header_value:
        return {header_name: header_value}
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validation conformité parfaite")
    parser.add_argument("--output", default="logs/perfect_compliance_report.json")
    parser.add_argument("--run-failover", action="store_true", help="Exécute réellement stop/start docker")
    args = parser.parse_args()

    local_api_proc = ensure_api_up()
    if local_api_proc is not None:
        atexit.register(stop_process, local_api_proc)

    checks: List[Check] = []
    headers = api_headers()

    # 1) RBAC + rate limit
    rbac_code, _, rbac_err = run_cmd([str(ROOT_DIR / ".venv" / "bin" / "python"), "scripts/test_api_rbac_rate_limit.py"])
    rbac_report = load_json(LOG_DIR / "api_rbac_rate_limit_report.json")
    checks.append(
        Check(
            item="rbac_rate_limit",
            status="PASS" if rbac_code == 0 else "FAIL",
            details={
                "exit_code": rbac_code,
                "summary": (rbac_report or {}).get("summary", {}),
                "stderr_tail": rbac_err[-300:],
            },
        )
    )

    # 2) Data Lake security + bronze/silver/gold promotion
    policy_files = [
        ROOT_DIR / "security" / "minio" / "policies" / "bronze-writer.json",
        ROOT_DIR / "security" / "minio" / "policies" / "silver-reader.json",
        ROOT_DIR / "security" / "minio" / "policies" / "gold-reader.json",
    ]
    policies_ok = all(path.exists() for path in policy_files)
    cert_public = ROOT_DIR / "security" / "minio" / "certs" / "public.crt"
    cert_private = ROOT_DIR / "security" / "minio" / "certs" / "private.key"
    tls_ok = cert_public.exists() and cert_private.exists()
    tls_generated = False
    tls_generate_exit = None
    tls_generate_stderr = ""
    if not tls_ok:
        tls_generate_exit, _, tls_generate_stderr = run_cmd(["bash", "scripts/generate_minio_tls_certs.sh"], timeout=120)
        tls_generated = tls_generate_exit == 0
        tls_ok = cert_public.exists() and cert_private.exists()
    compose_text = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    compose_security_ok = all(
        token in compose_text
        for token in [
            "MINIO_BRONZE_WRITER_ACCESS_KEY",
            "MINIO_SILVER_READER_ACCESS_KEY",
            "MINIO_GOLD_READER_ACCESS_KEY",
            "./security/minio/certs:/root/.minio/certs",
            "./security/minio/policies:/policies:ro",
        ]
    )
    promotion_report = latest_promotion_report()
    promotion_code = None
    promotion_out = ""
    promotion_err = ""
    if not promotion_report:
        promotion_code, promotion_out, promotion_err = run_cmd(
            [str(ROOT_DIR / ".venv" / "bin" / "python"), "scripts/promote_data_lake_layers.py"],
            timeout=240,
        )
        promotion_report = latest_promotion_report()
    layers = (promotion_report or {}).get("layers") or {}
    silver_ok = (layers.get("silver") or {}).get("status") == "published"
    gold_ok = (layers.get("gold") or {}).get("status") == "published"
    promotion_ok = bool(promotion_report) and silver_ok and gold_ok
    checks.append(
        Check(
            item="data_lake_security",
            status="PASS" if policies_ok and tls_ok and compose_security_ok and promotion_ok else "FAIL",
            details={
                "policies_ok": policies_ok,
                "tls_certs_present": tls_ok,
                "tls_generated_during_validation": tls_generated,
                "tls_generate_exit_code": tls_generate_exit,
                "tls_generate_stderr_tail": tls_generate_stderr[-300:],
                "compose_security_ok": compose_security_ok,
                "promotion_ok": promotion_ok,
                "promotion_exit_code": promotion_code,
                "promotion_stdout_tail": promotion_out[-300:],
                "promotion_stderr_tail": promotion_err[-300:],
                "promotion_report": promotion_report,
                "policy_files": [str(p) for p in policy_files],
            },
        )
    )

    # 3) Micro-batch
    micro_code, micro_out, micro_err = run_cmd(
        [
            str(ROOT_DIR / ".venv" / "bin" / "python"),
            "scripts/micro_batch_events_to_postgres.py",
            "--run-once",
            "--window-seconds",
            "30",
            "--bootstrap-minutes",
            "10",
        ],
        timeout=360,
    )
    micro_stats_ok = False
    micro_details = {}
    try:
        resp = requests.get(f"{API_URL}/api/micro-batch/stats?window_hours=24&limit=20", timeout=20, headers=headers)
        if resp.status_code == 200:
            payload = resp.json()
            micro_details = payload.get("summary", {})
            micro_stats_ok = True
    except Exception:
        micro_stats_ok = False
    checks.append(
        Check(
            item="micro_batch_flow",
            status="PASS" if micro_code == 0 and micro_stats_ok else "FAIL",
            details={
                "exit_code": micro_code,
                "api_summary": micro_details,
                "stdout_tail": micro_out[-300:],
                "stderr_tail": micro_err[-300:],
            },
        )
    )

    # 3b) Analytics warehouse + datamarts
    analytics_code, analytics_out, analytics_err = run_cmd(
        [
            str(ROOT_DIR / ".venv" / "bin" / "python"),
            "scripts/build_analytics_warehouse.py",
        ],
        timeout=360,
    )
    analytics_payload = analytics_report() or {}
    datamarts = analytics_payload.get("datamarts") or {}
    checks.append(
        Check(
            item="analytics_warehouse",
            status="PASS" if analytics_code == 0 and bool(datamarts) else "FAIL",
            details={
                "exit_code": analytics_code,
                "schema": analytics_payload.get("schema"),
                "dimensions": analytics_payload.get("dimensions"),
                "facts": analytics_payload.get("facts"),
                "datamarts": datamarts,
                "report_file": analytics_payload.get("report_file"),
                "stdout_tail": analytics_out[-300:],
                "stderr_tail": analytics_err[-300:],
            },
        )
    )

    # 4) DB load + resilience
    db_code, _, db_err = run_cmd(
        [
            str(ROOT_DIR / ".venv" / "bin" / "python"),
            "scripts/test_db_load.py",
            "--pg-requests",
            "120",
            "--mongo-requests",
            "120",
            "--concurrency",
            "12",
        ],
        timeout=420,
    )
    db_report = load_json(LOG_DIR / "db_load_test_report.json")
    checks.append(
        Check(
            item="db_load_test",
            status="PASS" if db_code == 0 else "FAIL",
            details={
                "exit_code": db_code,
                "status": (db_report or {}).get("status"),
                "stderr_tail": db_err[-300:],
            },
        )
    )

    failover_cmd = [
        str(ROOT_DIR / ".venv" / "bin" / "python"),
        "scripts/test_resilience_failover.py",
        "--service",
        "postgres",
    ]
    if not args.run_failover:
        failover_cmd.append("--dry-run")
    failover_code, _, failover_err = run_cmd(failover_cmd, timeout=600)
    failover_report = load_json(LOG_DIR / "resilience_failover_report.json")
    checks.append(
        Check(
            item="resilience_failover",
            status="PASS" if failover_code == 0 else "FAIL",
            details={
                "exit_code": failover_code,
                "status": (failover_report or {}).get("status"),
                "dry_run": not args.run_failover,
                "stderr_tail": failover_err[-300:],
            },
        )
    )

    # 5) KPI transfert standardisés
    kpi_ok = False
    kpi_details = {}
    try:
        resp = requests.get(f"{API_URL}/api/transfer/kpis?limit=200", timeout=20, headers=headers)
        if resp.status_code == 200:
            payload = resp.json()
            metrics_count = payload.get("metrics_count") or {}
            kpi_details = {
                "points": payload.get("points"),
                "metrics_count": metrics_count,
                "summary": payload.get("summary"),
            }
            kpi_ok = (
                int(payload.get("points", 0) or 0) > 0
                and int(metrics_count.get("data_lake_snapshot", 0) or 0) > 0
                and int(metrics_count.get("data_lake_silver", 0) or 0) > 0
                and int(metrics_count.get("data_lake_gold", 0) or 0) > 0
            )
    except Exception:
        kpi_ok = False
    checks.append(
        Check(
            item="transfer_kpi_dashboard_data",
            status="PASS" if kpi_ok else "FAIL",
            details=kpi_details,
        )
    )

    passed = sum(1 for c in checks if c.status == "PASS")
    failed = len(checks) - passed
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_url": API_URL,
        "summary": {
            "total": len(checks),
            "passed": passed,
            "failed": failed,
            "success_rate_percent": round((passed / len(checks)) * 100.0, 2) if checks else 0.0,
            "global_status": "PASS" if failed == 0 else "FAIL",
        },
        "checks": [asdict(c) for c in checks],
    }

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== PERFECT COMPLIANCE VALIDATION ===")
    print(f"Report         : {output}")
    print(f"Passed         : {passed}")
    print(f"Failed         : {failed}")
    print(f"Global status  : {report['summary']['global_status']}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

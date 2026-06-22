#!/usr/bin/env python3
"""
Tests formalisés RBAC + rate limit API.
Lance une instance API isolée sur 8011 et valide:
- auth obligatoire
- autorisations par rôle
- quotas par clé/utilisateur (429)
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import requests


ROOT_DIR = Path(__file__).resolve().parent.parent
BASE_CONFIG_FILE = ROOT_DIR / "config" / "api_access_control.json"

ADMIN_KEY = "demo-admin-key"
ANALYST_KEY = "demo-analyst-key"
PARTNER_KEY = "demo-partner-key"


def wait_http(url: str, timeout_s: int = 20) -> None:
    end_time = time.time() + timeout_s
    while time.time() < end_time:
        try:
            requests.get(url, timeout=2).raise_for_status()
            return
        except Exception:
            time.sleep(0.4)
    raise RuntimeError(f"Timeout waiting endpoint: {url}")


def start_api_with_config(config_file: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["API_KEY_REQUIRED"] = "true"
    env["API_RBAC_ENABLED"] = "true"
    env["API_KEY_HEADER"] = "X-API-Key"
    env["API_ACCESS_CONTROL_FILE"] = str(config_file)

    cmd = [
        str(ROOT_DIR / ".venv" / "bin" / "python"),
        "-m",
        "uvicorn",
        "api.fraud_dashboard_api:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8011",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wait_http("http://127.0.0.1:8011/health", timeout_s=30)
    return proc


def stop_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


def write_test_config() -> Path:
    payload = json.loads(BASE_CONFIG_FILE.read_text(encoding="utf-8"))
    for key in payload.get("keys", []):
        if key.get("key_id") == "partner-demo":
            key["quota"] = {"window_seconds": 60, "max_requests": 5}
    fd, temp_path = tempfile.mkstemp(prefix="api_access_control_test_", suffix=".json")
    os.close(fd)
    out = Path(temp_path)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def check_status(url: str, expected: int, headers: Dict[str, str] | None = None, method: str = "GET") -> Dict:
    if method == "GET":
        response = requests.get(url, headers=headers or {}, timeout=10)
    elif method == "POST":
        response = requests.post(url, headers=headers or {}, json={}, timeout=10)
    else:
        raise ValueError(f"Unsupported method: {method}")
    return {
        "url": url,
        "method": method,
        "expected": expected,
        "actual": response.status_code,
        "ok": response.status_code == expected,
    }


def run_tests() -> Dict:
    checks: List[Dict] = []
    cfg_file = write_test_config()
    proc = None
    try:
        proc = start_api_with_config(cfg_file)
        base = "http://127.0.0.1:8011"

        checks.append(check_status(f"{base}/api/stats", expected=401))
        checks.append(check_status(f"{base}/api/stats", expected=401, headers={"X-API-Key": "invalid"}))
        checks.append(check_status(f"{base}/api/stats", expected=200, headers={"X-API-Key": ADMIN_KEY}))
        checks.append(
            check_status(
                f"{base}/api/orders/checkout",
                expected=403,
                headers={"X-API-Key": ANALYST_KEY},
                method="POST",
            )
        )
        checks.append(check_status(f"{base}/api/products?limit=1", expected=200, headers={"X-API-Key": PARTNER_KEY}))
        checks.append(check_status(f"{base}/api/stats", expected=403, headers={"X-API-Key": PARTNER_KEY}))

        # Quota partner-demo: 5 req/min -> la 6e doit tomber en 429.
        quota_hits = []
        for _ in range(6):
            resp = requests.get(f"{base}/api/products?limit=1", headers={"X-API-Key": PARTNER_KEY}, timeout=10)
            quota_hits.append(resp.status_code)
        checks.append(
            {
                "url": f"{base}/api/products?limit=1",
                "method": "GET[x6]",
                "expected": "contains 429",
                "actual": quota_hits,
                "ok": 429 in quota_hits,
            }
        )

    finally:
        if proc is not None:
            stop_process(proc)
        if cfg_file.exists():
            cfg_file.unlink(missing_ok=True)

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_checks": len(checks),
            "passed": passed,
            "failed": failed,
            "success_rate_percent": round((passed / len(checks)) * 100.0, 2) if checks else 0.0,
        },
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Test RBAC + quotas API")
    parser.add_argument("--output", default="logs/api_rbac_rate_limit_report.json", help="Rapport JSON")
    args = parser.parse_args()

    report = run_tests()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    summary = report["summary"]
    print("=== API RBAC + RATE LIMIT TESTS ===")
    print(f"Output     : {output}")
    print(f"Checks     : {summary['total_checks']}")
    print(f"Passed     : {summary['passed']}")
    print(f"Failed     : {summary['failed']}")
    print(f"Success %  : {summary['success_rate_percent']}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

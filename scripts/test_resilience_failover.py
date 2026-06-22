#!/usr/bin/env python3
"""
Test formalisé de résilience/failover:
- Coupe un service Docker (postgres ou kafka-1)
- Vérifie la dégradation attendue
- Relance le service et mesure la récupération
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

import requests


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_API_URL = "http://localhost:8000"


def run_cmd(cmd, timeout=90) -> Tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def service_running(service: str) -> bool:
    code, out, _ = run_cmd(["docker", "compose", "ps", "--format", "json"], timeout=120)
    if code != 0:
        return False
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("Service") == service and item.get("State") == "running":
            return True
    return False


def wait_http(url: str, timeout_s: int) -> bool:
    end = time.time() + timeout_s
    while time.time() < end:
        try:
            response = requests.get(url, timeout=3)
            if response.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def measure_recovery(api_url: str, timeout_s: int) -> float:
    start = time.perf_counter()
    ok = wait_http(f"{api_url}/api/stats", timeout_s=timeout_s)
    return (time.perf_counter() - start) if ok else -1.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Test résilience failover service Docker")
    parser.add_argument("--service", choices=["postgres", "kafka-1"], default="postgres")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--downtime-seconds", type=int, default=6)
    parser.add_argument("--recovery-timeout", type=int, default=120)
    parser.add_argument("--output", default="logs/resilience_failover_report.json")
    parser.add_argument("--dry-run", action="store_true", help="Affiche les actions sans exécuter stop/start")
    args = parser.parse_args()

    report: Dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "service": args.service,
        "api_url": args.api_url,
        "dry_run": bool(args.dry_run),
        "steps": [],
        "status": "FAIL",
    }

    api_health_before = False
    try:
        requests.get(f"{args.api_url}/health", timeout=5).raise_for_status()
        api_health_before = True
    except Exception:
        api_health_before = False
    report["steps"].append({"step": "api_health_before", "ok": api_health_before})

    running_before = service_running(args.service)
    report["steps"].append({"step": "service_running_before", "ok": running_before})

    if not running_before:
        report["status"] = "FAIL"
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Service non actif avant test, abandon.")
        print(f"Report: {output}")
        return 1

    if args.dry_run:
        report["steps"].append({"step": "dry_run_no_stop_start", "ok": True})
        report["status"] = "PASS"
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("=== RESILIENCE FAILOVER TEST (DRY RUN) ===")
        print(f"Service         : {args.service}")
        print(f"Output          : {output}")
        print("Global status   : PASS")
        return 0

    stop_code, _, stop_err = run_cmd(["docker", "compose", "stop", args.service], timeout=120)
    report["steps"].append({"step": "stop_service", "ok": stop_code == 0, "stderr_tail": stop_err[-300:]})
    time.sleep(max(1, args.downtime_seconds))

    degraded_observed = False
    try:
        resp = requests.get(f"{args.api_url}/api/stats", timeout=5)
        degraded_observed = resp.status_code >= 500
    except Exception:
        degraded_observed = True
    report["steps"].append({"step": "degradation_observed", "ok": degraded_observed})

    start_code, _, start_err = run_cmd(["docker", "compose", "start", args.service], timeout=120)
    report["steps"].append({"step": "start_service", "ok": start_code == 0, "stderr_tail": start_err[-300:]})

    service_back = False
    for _ in range(30):
        if service_running(args.service):
            service_back = True
            break
        time.sleep(1)
    report["steps"].append({"step": "service_running_after", "ok": service_back})

    recovery_seconds = measure_recovery(args.api_url, timeout_s=max(10, args.recovery_timeout))
    recovered = recovery_seconds >= 0
    report["steps"].append(
        {
            "step": "api_recovered",
            "ok": recovered,
            "recovery_seconds": round(recovery_seconds, 3) if recovered else None,
        }
    )

    all_ok = all(step.get("ok") for step in report["steps"])
    report["status"] = "PASS" if all_ok else "FAIL"

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== RESILIENCE FAILOVER TEST ===")
    print(f"Service         : {args.service}")
    print(f"Output          : {output}")
    print(f"Recovered       : {recovered}")
    if recovered:
        print(f"Recovery time   : {round(recovery_seconds, 3)} s")
    print(f"Global status   : {report['status']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

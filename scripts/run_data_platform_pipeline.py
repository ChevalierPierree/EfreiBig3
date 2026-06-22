#!/usr/bin/env python3
"""Orchestre la chaine data Bloc 1 et publie un rapport consolide."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT_DIR / "logs"
DEFAULT_OUTPUT = LOG_DIR / "data_platform_pipeline_report.json"


def run_cmd(cmd: List[str], timeout: int = 600) -> Tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def load_json(path: Path) -> Optional[Dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def latest_file(pattern: str) -> Optional[Path]:
    files = sorted(LOG_DIR.glob(pattern), reverse=True)
    return files[0] if files else None


def summarize_step(name: str, returncode: int, stdout: str, stderr: str, details: Optional[Dict] = None) -> Dict:
    status = "PASS" if returncode == 0 else "FAIL"
    return {
        "step": name,
        "status": status,
        "returncode": returncode,
        "stdout_tail": (stdout or "").splitlines()[-20:],
        "stderr_tail": (stderr or "").splitlines()[-20:],
        "details": details or {},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Execution consolidee de la plateforme data")
    parser.add_argument("--skip-snapshot", action="store_true", help="Reutilise le dernier snapshot bronze disponible")
    parser.add_argument("--skip-quality", action="store_true", help="Ignore les controles de qualite")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT_DIR / output
    output.parent.mkdir(parents=True, exist_ok=True)

    steps: List[Dict] = []

    if args.skip_snapshot:
        snapshot_path = latest_file("data_lake_snapshot_*.json")
        snapshot_payload = load_json(snapshot_path) if snapshot_path else None
        snapshot_step = {
            "step": "snapshot_bronze",
            "status": "PASS" if snapshot_payload else "FAIL",
            "returncode": 0 if snapshot_payload else 1,
            "stdout_tail": [],
            "stderr_tail": [],
            "details": {
                "reused": True,
                "report_file": str(snapshot_path) if snapshot_path else None,
                "snapshot_utc": (snapshot_payload or {}).get("snapshot_utc"),
                "uploaded_files": (snapshot_payload or {}).get("uploaded_files"),
                "total_bytes": (snapshot_payload or {}).get("total_bytes"),
            },
        }
    else:
        code, stdout, stderr = run_cmd(["bash", "scripts/snapshot_raw_data_to_minio.sh"], timeout=600)
        snapshot_path = latest_file("data_lake_snapshot_*.json")
        snapshot_payload = load_json(snapshot_path) if snapshot_path else None
        snapshot_step = summarize_step(
            "snapshot_bronze",
            code if snapshot_payload else 1,
            stdout,
            stderr,
            {
                "report_file": str(snapshot_path) if snapshot_path else None,
                "snapshot_utc": (snapshot_payload or {}).get("snapshot_utc"),
                "uploaded_files": (snapshot_payload or {}).get("uploaded_files"),
                "total_bytes": (snapshot_payload or {}).get("total_bytes"),
            },
        )
    steps.append(snapshot_step)

    code, stdout, stderr = run_cmd(
        [str(ROOT_DIR / ".venv" / "bin" / "python"), "scripts/promote_data_lake_layers.py"],
        timeout=600,
    )
    promotion_path = latest_file("data_lake_promotion_*.json")
    promotion_payload = load_json(promotion_path) if promotion_path else None
    promotion_layers = (promotion_payload or {}).get("layers") or {}
    promotion_ok = (
        code == 0
        and bool(promotion_payload)
        and (promotion_layers.get("silver") or {}).get("status") == "published"
        and (promotion_layers.get("gold") or {}).get("status") == "published"
    )
    steps.append(
        summarize_step(
            "lake_promotion",
            0 if promotion_ok else 1,
            stdout,
            stderr,
            {
                "report_file": str(promotion_path) if promotion_path else None,
                "source_snapshot_utc": (promotion_payload or {}).get("source_snapshot_utc"),
                "silver_status": (promotion_layers.get("silver") or {}).get("status"),
                "gold_status": (promotion_layers.get("gold") or {}).get("status"),
            },
        )
    )

    code, stdout, stderr = run_cmd(
        [str(ROOT_DIR / ".venv" / "bin" / "python"), "scripts/build_analytics_warehouse.py"],
        timeout=600,
    )
    analytics_path = LOG_DIR / "analytics_warehouse_report.json"
    analytics_payload = load_json(analytics_path) or {}
    analytics_ok = code == 0 and analytics_payload.get("status") == "PASS"
    steps.append(
        summarize_step(
            "analytics_warehouse",
            0 if analytics_ok else 1,
            stdout,
            stderr,
            {
                "report_file": str(analytics_path),
                "status": analytics_payload.get("status"),
                "summary": analytics_payload.get("summary"),
                "refresh_log": analytics_payload.get("refresh_log"),
            },
        )
    )

    if args.skip_quality:
        quality_payload = load_json(LOG_DIR / "data_quality_report.json") or {}
        quality_step = {
            "step": "data_quality",
            "status": "PASS" if quality_payload else "FAIL",
            "returncode": 0 if quality_payload else 1,
            "stdout_tail": [],
            "stderr_tail": [],
            "details": {
                "reused": True,
                "report_file": str(LOG_DIR / "data_quality_report.json"),
                "summary": quality_payload.get("summary"),
            },
        }
    else:
        code, stdout, stderr = run_cmd(
            [str(ROOT_DIR / ".venv" / "bin" / "python"), "scripts/data_quality_checks.py"],
            timeout=600,
        )
        quality_payload = load_json(LOG_DIR / "data_quality_report.json") or {}
        quality_summary = quality_payload.get("summary") or {}
        quality_ok = code == 0 and int(quality_summary.get("failed", 1)) == 0
        quality_step = summarize_step(
            "data_quality",
            0 if quality_ok else 1,
            stdout,
            stderr,
            {
                "report_file": str(LOG_DIR / "data_quality_report.json"),
                "summary": quality_summary,
            },
        )
    steps.append(quality_step)

    passed = sum(1 for step in steps if step["status"] == "PASS")
    total = len(steps)
    failed = total - passed
    status = "PASS" if failed == 0 else "FAIL"

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "summary": {
            "total_steps": total,
            "passed": passed,
            "failed": failed,
            "success_rate_percent": round((passed / total) * 100, 2) if total else 100.0,
        },
        "lineage": {
            "snapshot_report_file": str(snapshot_path) if snapshot_path else None,
            "snapshot_utc": (snapshot_payload or {}).get("snapshot_utc"),
            "promotion_report_file": str(promotion_path) if promotion_path else None,
            "promotion_source_snapshot_utc": (promotion_payload or {}).get("source_snapshot_utc"),
            "analytics_report_file": str(analytics_path),
            "analytics_refresh_at": (analytics_payload.get("refresh_log") or {}).get("refreshed_at"),
            "quality_report_file": str(LOG_DIR / "data_quality_report.json"),
            "quality_generated_at": quality_payload.get("generated_at"),
        },
        "steps": steps,
    }

    output.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    print("=== DATA PLATFORM PIPELINE ===")
    print(f"Status       : {status}")
    print(f"Steps        : {passed}/{total}")
    print(f"Snapshot     : {(snapshot_payload or {}).get('snapshot_utc')}")
    print(f"Promotion    : {(promotion_payload or {}).get('source_snapshot_utc')}")
    print(f"Analytics    : {(analytics_payload.get('refresh_log') or {}).get('refreshed_at')}")
    print(f"Report       : {output}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

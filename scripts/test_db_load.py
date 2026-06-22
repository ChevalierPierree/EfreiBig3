#!/usr/bin/env python3
"""
Test formalisé de charge base de données (PostgreSQL + MongoDB).
Produit un rapport JSON avec latence, débit et taux d'erreur.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import psycopg2
from pymongo import MongoClient


ROOT_DIR = Path(__file__).resolve().parent.parent


def postgres_conn():
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


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = int((len(values) - 1) * p)
    return float(values[idx])


def run_postgres_query() -> Tuple[bool, float]:
    queries = [
        "SELECT COUNT(*) FROM orders",
        "SELECT COUNT(*) FROM payments WHERE is_fraudulent = true",
        "SELECT AVG(total_amount) FROM orders",
        "SELECT COUNT(*) FROM fraud_alerts",
        "SELECT COUNT(*) FROM checkout_attempts",
    ]
    started = time.perf_counter()
    try:
        with postgres_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(random.choice(queries))
                cur.fetchone()
        latency_ms = (time.perf_counter() - started) * 1000.0
        return True, latency_ms
    except Exception:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return False, latency_ms


def run_mongo_query() -> Tuple[bool, float]:
    started = time.perf_counter()
    try:
        client = mongo_client()
        db = client[os.getenv("MONGODB_DB", "kivendtout")]
        coll = db[os.getenv("MONGODB_COLLECTION", "events")]
        mode = random.choice(["count", "distinct", "recent"])
        if mode == "count":
            coll.count_documents({})
        elif mode == "distinct":
            coll.distinct("event_type")
        else:
            list(coll.find({}, {"_id": 0, "event_type": 1, "ts": 1}).sort("ts", -1).limit(20))
        client.close()
        latency_ms = (time.perf_counter() - started) * 1000.0
        return True, latency_ms
    except Exception:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return False, latency_ms


def run_load(name: str, requests_count: int, concurrency: int, worker):
    latencies: List[float] = []
    errors = 0
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker) for _ in range(requests_count)]
        for future in as_completed(futures):
            ok, latency_ms = future.result()
            latencies.append(latency_ms)
            if not ok:
                errors += 1
    duration = time.perf_counter() - start
    throughput = (requests_count / duration) if duration > 0 else 0.0
    return {
        "name": name,
        "requests": requests_count,
        "concurrency": concurrency,
        "duration_seconds": round(duration, 3),
        "throughput_qps": round(throughput, 2),
        "errors": errors,
        "error_rate_percent": round((errors / requests_count) * 100.0, 2) if requests_count > 0 else 0.0,
        "latency_ms": {
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(percentile(latencies, 0.95), 2),
            "p99": round(percentile(latencies, 0.99), 2),
            "max": round(max(latencies), 2) if latencies else 0.0,
            "avg": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Test charge PostgreSQL/MongoDB")
    parser.add_argument("--pg-requests", type=int, default=300, help="Nombre de requêtes Postgres")
    parser.add_argument("--mongo-requests", type=int, default=300, help="Nombre de requêtes MongoDB")
    parser.add_argument("--concurrency", type=int, default=20, help="Concurrence")
    parser.add_argument("--output", default="logs/db_load_test_report.json", help="Rapport JSON")
    args = parser.parse_args()

    pg = run_load("postgres", max(1, args.pg_requests), max(1, args.concurrency), run_postgres_query)
    mongo = run_load("mongodb", max(1, args.mongo_requests), max(1, args.concurrency), run_mongo_query)

    global_status = "PASS"
    if pg["errors"] > 0 or mongo["errors"] > 0:
        global_status = "FAIL"
    if pg["latency_ms"]["p95"] > 400 or mongo["latency_ms"]["p95"] > 400:
        global_status = "FAIL"

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": global_status,
        "criteria": {
            "max_errors": 0,
            "max_p95_ms": 400,
        },
        "results": {
            "postgres": pg,
            "mongodb": mongo,
        },
    }

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== DB LOAD TEST ===")
    print(f"Output           : {output}")
    print(f"Postgres errors  : {pg['errors']} | p95={pg['latency_ms']['p95']} ms | qps={pg['throughput_qps']}")
    print(f"MongoDB errors   : {mongo['errors']} | p95={mongo['latency_ms']['p95']} ms | qps={mongo['throughput_qps']}")
    print(f"Global status    : {global_status}")

    return 0 if global_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

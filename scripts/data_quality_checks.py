#!/usr/bin/env python3
"""
Controles qualite de donnees pour le sujet 1.
Produit un rapport JSON exploitable comme preuve.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import psycopg2
from pymongo import MongoClient


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


def run_checks() -> Dict:
    checks: List[Dict] = []

    with postgres_conn() as pg_conn:
        with pg_conn.cursor() as cur:
            # Complétude tables coeur métier.
            for table in ["customers", "products", "sessions", "orders", "order_items", "payments"]:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = int(cur.fetchone()[0] or 0)
                checks.append(
                    {
                        "name": f"postgres_non_empty_{table}",
                        "status": "PASS" if count > 0 else "FAIL",
                        "value": count,
                        "expected": "> 0",
                    }
                )

            # Intégrité référentielle.
            referential_queries = {
                "orders_to_customers": """
                    SELECT COUNT(*) FROM orders o
                    LEFT JOIN customers c ON c.customer_id = o.customer_id
                    WHERE c.customer_id IS NULL
                """,
                "order_items_to_orders": """
                    SELECT COUNT(*) FROM order_items oi
                    LEFT JOIN orders o ON o.order_id = oi.order_id
                    WHERE o.order_id IS NULL
                """,
                "order_items_to_products": """
                    SELECT COUNT(*) FROM order_items oi
                    LEFT JOIN products p ON p.product_id = oi.product_id
                    WHERE p.product_id IS NULL
                """,
                "payments_to_orders": """
                    SELECT COUNT(*) FROM payments p
                    LEFT JOIN orders o ON o.order_id = p.order_id
                    WHERE o.order_id IS NULL
                """,
            }
            for name, query in referential_queries.items():
                cur.execute(query)
                orphans = int(cur.fetchone()[0] or 0)
                checks.append(
                    {
                        "name": f"postgres_fk_{name}",
                        "status": "PASS" if orphans == 0 else "FAIL",
                        "value": orphans,
                        "expected": "0",
                    }
                )

            # Champs critiques non null.
            non_null_queries = {
                "customers.email": "SELECT COUNT(*) FROM customers WHERE email IS NULL OR email = ''",
                "products.price": "SELECT COUNT(*) FROM products WHERE price IS NULL OR price < 0",
                "orders.total_amount": "SELECT COUNT(*) FROM orders WHERE total_amount IS NULL OR total_amount < 0",
            }
            for name, query in non_null_queries.items():
                cur.execute(query)
                bad_count = int(cur.fetchone()[0] or 0)
                checks.append(
                    {
                        "name": f"postgres_not_null_{name}",
                        "status": "PASS" if bad_count == 0 else "FAIL",
                        "value": bad_count,
                        "expected": "0",
                    }
                )

    mongo = mongo_client()
    db = mongo[os.getenv("MONGODB_DB", "kivendtout")]
    coll = db[os.getenv("MONGODB_COLLECTION", "events")]
    total_events = int(coll.count_documents({}))
    checks.append(
        {
            "name": "mongo_events_non_empty",
            "status": "PASS" if total_events > 0 else "FAIL",
            "value": total_events,
            "expected": "> 0",
        }
    )

    required_fields = ["customer_id", "session_id", "event_type", "ts"]
    for field in required_fields:
        missing = int(coll.count_documents({"$or": [{field: {"$exists": False}}, {field: None}, {field: ""}]}))
        checks.append(
            {
                "name": f"mongo_required_{field}",
                "status": "PASS" if missing == 0 else "FAIL",
                "value": missing,
                "expected": "0",
            }
        )
    mongo.close()

    passed = sum(1 for c in checks if c["status"] == "PASS")
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
    parser = argparse.ArgumentParser(description="Contrôles qualité de données")
    parser.add_argument("--output", default="logs/data_quality_report.json", help="Fichier rapport JSON")
    args = parser.parse_args()

    report = run_checks()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    summary = report["summary"]
    print("=== DATA QUALITY CHECKS ===")
    print(f"Output     : {output}")
    print(f"Checks     : {summary['total_checks']}")
    print(f"Passed     : {summary['passed']}")
    print(f"Failed     : {summary['failed']}")
    print(f"Success %  : {summary['success_rate_percent']}")

    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

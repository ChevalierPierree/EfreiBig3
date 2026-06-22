#!/usr/bin/env python3
"""
Simulation d'alertes de fraude via API:
- Crée des alertes synthétiques via /api/alerts/simulate
- Supporte mode burst et mode realtime (flux continu)
"""

import argparse
import os
import random
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


REASON_POOL = [
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
    "GEO_MISMATCH",
]


def build_api_headers():
    header_name = os.getenv("API_KEY_HEADER", "X-API-Key").strip()
    header_value = os.getenv("API_KEY_VALUE", "").strip()
    if not header_value:
        header_value = os.getenv("API_DEFAULT_DEMO_KEY", "demo-admin-key").strip()
    if header_name and header_value:
        return {header_name: header_value}
    return {}


def post_alert(api_url, payload, timeout=15, headers=None):
    return requests.post(f"{api_url}/api/alerts/simulate", json=payload, timeout=timeout, headers=headers or {})


def build_payload(high_severity_ratio):
    if random.random() < high_severity_ratio:
        severity = "HIGH"
        risk_score = random.randint(80, 97)
    else:
        if random.random() < 0.25:
            severity = "LOW"
            risk_score = random.randint(40, 59)
        else:
            severity = "MEDIUM"
            risk_score = random.randint(60, 79)

    reason_count = random.randint(1, 3)
    reasons = random.sample(REASON_POOL, k=reason_count)

    payload = {
        "customer_id": f"C{random.randint(1, 2500):05d}",
        "event_type": random.choice(["payment_attempt", "checkout", "order_completed"]),
        "device": random.choice(["ios", "android", "desktop"]),
        "utm_source": random.choice(["direct", "google", "instagram", "facebook", "email"]),
        "customer_country": random.choice(["FR", "ES", "PT", "DE", "IT", "GB"]),
        "previous_payments": random.randint(0, 14),
        "is_new_customer": random.random() < 0.2,
        "fraud_reasons": reasons,
        "risk_score": risk_score,
        "severity": severity,
        "status": "PENDING_REVIEW",
    }
    return payload


def run_request(api_url, high_severity_ratio, headers):
    payload = build_payload(high_severity_ratio)
    started = time.perf_counter()

    try:
        response = post_alert(api_url, payload, headers=headers)
        latency_ms = (time.perf_counter() - started) * 1000

        if response.status_code == 200:
            data = response.json()
            return {
                "outcome": "created",
                "latency_ms": latency_ms,
                "severity": data.get("severity", "UNKNOWN"),
            }

        return {
            "outcome": "error_http",
            "latency_ms": latency_ms,
            "severity": "UNKNOWN",
        }
    except Exception:
        latency_ms = (time.perf_counter() - started) * 1000
        return {
            "outcome": "error_network",
            "latency_ms": latency_ms,
            "severity": "UNKNOWN",
        }


def percentile(sorted_values, p):
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = int((len(sorted_values) - 1) * p)
    return sorted_values[idx]


def print_summary(results, total_requests, concurrency, duration):
    outcomes = Counter(r["outcome"] for r in results)
    severities = Counter(r["severity"] for r in results if r["outcome"] == "created")
    latencies = sorted(r["latency_ms"] for r in results)
    throughput = (total_requests / duration) if duration > 0 else 0.0

    print("\n=== Résultat scaling alertes API ===")
    print(f"Requêtes totales          : {total_requests}")
    print(f"Concurrence               : {concurrency}")
    print(f"Durée totale              : {duration:.2f}s")
    print(f"Débit moyen               : {throughput:.2f} req/s")
    print(f"Alertes créées            : {outcomes['created']}")
    print(f"Erreurs HTTP              : {outcomes['error_http']}")
    print(f"Erreurs réseau            : {outcomes['error_network']}")
    print(
        f"Sévérité (HIGH/MEDIUM/LOW): "
        f"{severities['HIGH']}/{severities['MEDIUM']}/{severities['LOW']}"
    )
    print(f"P50 latency               : {percentile(latencies, 0.50):.1f} ms")
    print(f"P95 latency               : {percentile(latencies, 0.95):.1f} ms")
    print(f"P99 latency               : {percentile(latencies, 0.99):.1f} ms")

    if outcomes["created"] <= 0:
        raise SystemExit("ECHEC: aucune alerte créée")

    print("OK: alertes de fraude générées pour dashboard temps réel.")


def run_burst_mode(args, headers):
    start = time.perf_counter()
    results = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(run_request, args.api_url, args.high_severity_ratio, headers)
            for _ in range(args.requests)
        ]
        for fut in as_completed(futures):
            results.append(fut.result())

    duration = time.perf_counter() - start
    print_summary(results, args.requests, args.concurrency, duration)


def run_realtime_mode(args, headers):
    duration_seconds = max(1, int(args.duration_seconds))
    rps = max(1, int(args.rps))

    print(
        f"Mode temps réel alertes: durée={duration_seconds}s, cible={rps} req/s, "
        f"concurrence={args.concurrency}"
    )

    overall_start = time.perf_counter()
    all_results = []
    total_sent = 0

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        for second_idx in range(duration_seconds):
            tick_start = time.perf_counter()
            futures = [
                executor.submit(run_request, args.api_url, args.high_severity_ratio, headers)
                for _ in range(rps)
            ]
            tick_results = []
            for fut in as_completed(futures):
                result = fut.result()
                tick_results.append(result)
                all_results.append(result)

            total_sent += len(tick_results)
            tick_counts = Counter(r["outcome"] for r in tick_results)
            tick_sev = Counter(r["severity"] for r in tick_results if r["outcome"] == "created")
            print(
                f"[alerts t+{second_idx + 1:03d}s] sent={len(tick_results)} "
                f"created={tick_counts['created']} "
                f"H/M/L={tick_sev['HIGH']}/{tick_sev['MEDIUM']}/{tick_sev['LOW']} "
                f"http_err={tick_counts['error_http']} "
                f"net_err={tick_counts['error_network']}"
            )

            elapsed_tick = time.perf_counter() - tick_start
            to_sleep = max(0.0, 1.0 - elapsed_tick)
            if to_sleep > 0:
                time.sleep(to_sleep)

    total_duration = time.perf_counter() - overall_start
    print_summary(all_results, total_sent, args.concurrency, total_duration)


def main():
    parser = argparse.ArgumentParser(description="Scaling d'alertes fraude via API")
    parser.add_argument("--api-url", default="http://localhost:8000", help="URL API")
    parser.add_argument("--requests", type=int, default=120, help="Nombre total de requêtes")
    parser.add_argument("--concurrency", type=int, default=10, help="Niveau de concurrence")
    parser.add_argument(
        "--mode",
        choices=["burst", "realtime"],
        default="realtime",
        help="burst=rafale immédiate | realtime=flux continu par seconde"
    )
    parser.add_argument("--duration-seconds", type=int, default=30, help="Durée en secondes en mode realtime")
    parser.add_argument("--rps", type=int, default=6, help="Requêtes/seconde en mode realtime")
    parser.add_argument("--high-severity-ratio", type=float, default=0.35, help="Part d'alertes HIGH [0..1]")
    args = parser.parse_args()

    headers = build_api_headers()
    if args.mode == "realtime":
        run_realtime_mode(args, headers)
    else:
        run_burst_mode(args, headers)


if __name__ == "__main__":
    main()

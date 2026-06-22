#!/usr/bin/env python3
"""
Vérifie que le dataset est dynamique:
- Déclenche un refresh runtime en mode realtime
- Attend la fin de la simulation
- Compare les stats checkout avant/après
"""

import argparse
import time
import requests


def wait_for_health(api_url: str, timeout_seconds: int = 40) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            resp = requests.get(f"{api_url}/health", timeout=3)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


def get_checkout_stats(api_url: str) -> dict:
    response = requests.get(
        f"{api_url}/api/checkout/stats",
        params={"window_hours": 24},
        timeout=10
    )
    response.raise_for_status()
    return response.json()

def get_fraud_stats(api_url: str) -> dict:
    response = requests.get(f"{api_url}/api/stats", timeout=10)
    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser(description="Validation dynamique dataset checkout/fraude")
    parser.add_argument("--api-url", default="http://localhost:8000", help="URL API")
    parser.add_argument("--duration-seconds", type=int, default=10, help="Durée simulation realtime")
    parser.add_argument("--rps", type=int, default=6, help="Requêtes par seconde")
    parser.add_argument("--concurrency", type=int, default=12, help="Concurrence côté simulateur")
    parser.add_argument("--requests", type=int, default=120, help="Cap max de requêtes pour le run")
    parser.add_argument("--restart-api", action="store_true", help="Demande aussi le redémarrage API")
    parser.add_argument("--wait-buffer", type=int, default=3, help="Buffer d'attente après simulation")
    args = parser.parse_args()

    if not wait_for_health(args.api_url, timeout_seconds=20):
        raise SystemExit("API indisponible avant test")

    before = get_checkout_stats(args.api_url)
    before_fraud = get_fraud_stats(args.api_url)
    print(
        f"BEFORE attempts={before['total_attempts']} "
        f"blocked={before['blocked_underage_orders']} "
        f"accepted={before['accepted_orders']}"
    )
    print(f"BEFORE alerts={before_fraud['total_alerts']}")

    runtime_payload = {
        "sync_kafka": True,
        "run_scaling": True,
        "restart_api": bool(args.restart_api),
        "scaling_mode": "realtime",
        "requests": max(args.requests, args.duration_seconds * args.rps),
        "concurrency": args.concurrency,
        "duration_seconds": args.duration_seconds,
        "rps": args.rps,
        "run_alert_scaling": True,
        "alerts_mode": "realtime",
        "alerts_requests": max(args.requests, args.duration_seconds * args.rps),
        "alerts_concurrency": max(6, min(args.concurrency, 20)),
        "alerts_duration_seconds": args.duration_seconds,
        "alerts_rps": args.rps,
        "high_severity_ratio": 0.35,
        "adult_order_ratio": 0.6,
        "minor_ratio": 0.4
    }

    refresh_response = requests.post(
        f"{args.api_url}/api/runtime/refresh",
        json=runtime_payload,
        timeout=20
    )
    refresh_response.raise_for_status()
    refresh_json = refresh_response.json()
    print(f"REFRESH response={refresh_json}")

    expected_wait = args.duration_seconds + args.wait_buffer
    time.sleep(expected_wait)

    if args.restart_api and not wait_for_health(args.api_url, timeout_seconds=40):
        raise SystemExit("API indisponible après redémarrage demandé")

    after = get_checkout_stats(args.api_url)
    after_fraud = get_fraud_stats(args.api_url)
    attempts_delta = after["total_attempts"] - before["total_attempts"]
    blocked_delta = after["blocked_underage_orders"] - before["blocked_underage_orders"]
    accepted_delta = after["accepted_orders"] - before["accepted_orders"]
    alerts_delta = after_fraud["total_alerts"] - before_fraud["total_alerts"]

    print(
        f"AFTER  attempts={after['total_attempts']} "
        f"blocked={after['blocked_underage_orders']} "
        f"accepted={after['accepted_orders']}"
    )
    print(
        f"DELTA attempts={attempts_delta} blocked={blocked_delta} accepted={accepted_delta}"
    )
    print(f"DELTA alerts={alerts_delta}")

    if attempts_delta <= 0:
        raise SystemExit("ECHEC: aucune nouvelle donnée checkout détectée")
    if alerts_delta <= 0:
        raise SystemExit("ECHEC: aucune nouvelle alerte fraude détectée")

    print("OK: dataset dynamique confirmé (commandes + alertes générées en temps réel).")


if __name__ == "__main__":
    main()

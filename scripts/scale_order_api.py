#!/usr/bin/env python3
"""
Test de charge pour l'API de commandes:
- Crée des commandes en parallèle via /api/orders/checkout
- Vérifie le blocage des produits Adult pour les mineurs
"""

import argparse
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter

import requests


def build_api_headers():
    header_name = os.getenv("API_KEY_HEADER", "X-API-Key").strip()
    header_value = os.getenv("API_KEY_VALUE", "").strip()
    if not header_value:
        header_value = os.getenv("API_DEFAULT_DEMO_KEY", "demo-admin-key").strip()
    if header_name and header_value:
        return {header_name: header_value}
    return {}


def fetch_json(url, timeout=10, headers=None):
    response = requests.get(url, timeout=timeout, headers=headers or {})
    response.raise_for_status()
    return response.json()


def post_checkout(api_url, payload, timeout=15, headers=None):
    return requests.post(f"{api_url}/api/orders/checkout", json=payload, timeout=timeout, headers=headers or {})


def build_payload(
    adult_products,
    non_adult_products,
    adult_cards,
    minor_cards,
    adult_order_ratio,
    minor_ratio,
    risk_profile,
):
    is_minor = random.random() < minor_ratio and len(minor_cards) > 0
    card = random.choice(minor_cards if is_minor else adult_cards)

    wants_adult = random.random() < adult_order_ratio and len(adult_products) > 0
    selected_product = random.choice(adult_products if wants_adult else non_adult_products)

    customer_id = f"C{random.randint(1, 2500):05d}"
    # Quantité fixée à 1 pour limiter les faux négatifs de charge liés aux ruptures de stock.
    quantity = 1
    if risk_profile == "elevated":
        payment_weights = [0.45, 0.3, 0.25]
    else:
        payment_weights = [0.72, 0.2, 0.08]
    payment_method = random.choices(
        ["card", "paypal", "bank_transfer"],
        weights=payment_weights,
        k=1,
    )[0]

    payload = {
        "customer_id": customer_id,
        "id_card_file": card["file"],
        "items": [
            {
                "product_id": selected_product["product_id"],
                "quantity": quantity
            }
        ],
        "payment_method": payment_method,
        "risk_profile": risk_profile,
    }
    return payload, is_minor, wants_adult


def run_request(
    api_url,
    adult_products,
    non_adult_products,
    adult_cards,
    minor_cards,
    adult_order_ratio,
    minor_ratio,
    risk_profile,
    headers,
):
    payload, is_minor, wants_adult = build_payload(
        adult_products,
        non_adult_products,
        adult_cards,
        minor_cards,
        adult_order_ratio,
        minor_ratio,
        risk_profile,
    )
    started = time.perf_counter()
    try:
        response = post_checkout(api_url, payload, headers=headers)
        latency_ms = (time.perf_counter() - started) * 1000

        if response.status_code == 200:
            return {
                "outcome": "accepted",
                "status_code": 200,
                "latency_ms": latency_ms,
                "minor": is_minor,
                "adult_item": wants_adult
            }
        if response.status_code == 403:
            return {
                "outcome": "blocked_underage",
                "status_code": 403,
                "latency_ms": latency_ms,
                "minor": is_minor,
                "adult_item": wants_adult
            }
        if response.status_code == 400:
            try:
                detail = response.json().get("detail")
            except Exception:
                detail = None
            if isinstance(detail, str) and "Insufficient stock" in detail:
                return {
                    "outcome": "rejected_stock",
                    "status_code": 400,
                    "latency_ms": latency_ms,
                    "minor": is_minor,
                    "adult_item": wants_adult
                }
        return {
            "outcome": "error_http",
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "minor": is_minor,
            "adult_item": wants_adult
        }
    except Exception:
        latency_ms = (time.perf_counter() - started) * 1000
        return {
            "outcome": "error_network",
            "status_code": 0,
            "latency_ms": latency_ms,
            "minor": is_minor,
            "adult_item": wants_adult
        }


def percentile(sorted_values, p):
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = int((len(sorted_values) - 1) * p)
    return sorted_values[idx]


def print_summary(results, total_requests, concurrency, duration):
    counts = Counter(r["outcome"] for r in results)
    latencies = sorted(r["latency_ms"] for r in results)

    forbidden_not_blocked = sum(
        1
        for r in results
        if r["minor"] and r["adult_item"] and r["outcome"] == "accepted"
    )

    throughput = (total_requests / duration) if duration > 0 else 0.0

    print("\n=== Résultat scaling commandes API ===")
    print(f"Requêtes totales          : {total_requests}")
    print(f"Concurrence               : {concurrency}")
    print(f"Durée totale              : {duration:.2f}s")
    print(f"Débit moyen               : {throughput:.2f} req/s")
    print(f"Acceptées                 : {counts['accepted']}")
    print(f"Bloquées mineur/adult     : {counts['blocked_underage']}")
    print(f"Rejets stock              : {counts['rejected_stock']}")
    print(f"Erreurs HTTP              : {counts['error_http']}")
    print(f"Erreurs réseau            : {counts['error_network']}")
    print(f"P50 latency               : {percentile(latencies, 0.50):.1f} ms")
    print(f"P95 latency               : {percentile(latencies, 0.95):.1f} ms")
    print(f"P99 latency               : {percentile(latencies, 0.99):.1f} ms")
    print(f"Mineur+Adult acceptés (KO): {forbidden_not_blocked}")

    if forbidden_not_blocked > 0:
        raise SystemExit("ECHEC: certains mineurs ont pu acheter des produits Adult")

    print("OK: garde-fou 18+ appliqué correctement sous charge.")


def run_burst_mode(args, adult_products, non_adult_products, adult_cards, minor_cards, headers):
    start = time.perf_counter()
    results = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(
                run_request,
                args.api_url,
                adult_products,
                non_adult_products,
                adult_cards,
                minor_cards,
                args.adult_order_ratio,
                args.minor_ratio,
                args.risk_profile,
                headers
            )
            for _ in range(args.requests)
        ]
        for fut in as_completed(futures):
            results.append(fut.result())

    duration = time.perf_counter() - start
    print_summary(results, args.requests, args.concurrency, duration)


def run_realtime_mode(args, adult_products, non_adult_products, adult_cards, minor_cards, headers):
    duration_seconds = max(1, int(args.duration_seconds))
    rps = max(1, int(args.rps))

    print(
        f"Mode temps réel: durée={duration_seconds}s, cible={rps} req/s, "
        f"concurrence={args.concurrency}"
    )

    overall_start = time.perf_counter()
    all_results = []
    total_sent = 0

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        for second_idx in range(duration_seconds):
            tick_start = time.perf_counter()
            futures = [
                executor.submit(
                    run_request,
                    args.api_url,
                    adult_products,
                    non_adult_products,
                    adult_cards,
                    minor_cards,
                    args.adult_order_ratio,
                    args.minor_ratio,
                    args.risk_profile,
                    headers
                )
                for _ in range(rps)
            ]

            tick_results = []
            for fut in as_completed(futures):
                result = fut.result()
                tick_results.append(result)
                all_results.append(result)

            total_sent += len(tick_results)
            tick_counts = Counter(r["outcome"] for r in tick_results)
            print(
                f"[t+{second_idx + 1:03d}s] sent={len(tick_results)} "
                f"accepted={tick_counts['accepted']} "
                f"blocked={tick_counts['blocked_underage']} "
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
    parser = argparse.ArgumentParser(description="Scaling de commandes client via API")
    parser.add_argument("--api-url", default="http://localhost:8000", help="URL API")
    parser.add_argument("--requests", type=int, default=200, help="Nombre total de requêtes")
    parser.add_argument("--concurrency", type=int, default=20, help="Niveau de concurrence")
    parser.add_argument("--adult-order-ratio", type=float, default=0.5, help="Part de commandes ciblant un produit Adult")
    parser.add_argument("--minor-ratio", type=float, default=0.3, help="Part de cartes mineures utilisées")
    parser.add_argument(
        "--mode",
        choices=["burst", "realtime"],
        default="burst",
        help="burst=rafale immédiate | realtime=flux continu par seconde"
    )
    parser.add_argument("--duration-seconds", type=int, default=30, help="Durée en secondes en mode realtime")
    parser.add_argument("--rps", type=int, default=8, help="Requêtes par seconde en mode realtime")
    parser.add_argument(
        "--risk-profile",
        choices=["standard", "elevated"],
        default="standard",
        help="Profil de risque paiements injecte dans le checkout",
    )
    args = parser.parse_args()

    headers = build_api_headers()
    print("Chargement du catalogue et des cartes ID...")
    products = fetch_json(f"{args.api_url}/api/products?limit=1000&only_in_stock=true", headers=headers)
    id_cards_all = fetch_json(f"{args.api_url}/api/id-cards?limit=500", headers=headers)

    adult_products = [p for p in products if p.get("is_adult_restricted") and int(p.get("stock_quantity", 0)) > 0]
    non_adult_products = [p for p in products if not p.get("is_adult_restricted") and int(p.get("stock_quantity", 0)) > 0]
    adult_cards = [c for c in id_cards_all if c.get("is_adult")]
    minor_cards = [c for c in id_cards_all if not c.get("is_adult")]

    if not adult_products or not non_adult_products:
        raise RuntimeError("Catalogue incomplet: besoin de produits Adult et non-Adult")
    if not adult_cards or not minor_cards:
        raise RuntimeError("Dataset cartes incomplet: besoin de cartes adultes et mineures")

    print(
        f"Produits: total={len(products)} adult={len(adult_products)} non_adult={len(non_adult_products)} | "
        f"ID cards: adultes={len(adult_cards)} mineurs={len(minor_cards)}"
    )

    if args.mode == "realtime":
        run_realtime_mode(args, adult_products, non_adult_products, adult_cards, minor_cards, headers)
    else:
        run_burst_mode(args, adult_products, non_adult_products, adult_cards, minor_cards, headers)


if __name__ == "__main__":
    main()

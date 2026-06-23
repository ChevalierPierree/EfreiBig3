#!/usr/bin/env python3
"""Vérifie les invariants de cohérence des données KiVendTout (API :8000).

Recoupe /api/stats, /api/kpis/readable, /api/fraud/reasons/stats,
/api/checkout/stats, /api/identity/stats, /api/analytics/status.
Sortie : un OK/XX par invariant + l'analyse live-vs-warehouse.

Usage : python3 docs/genai/tests/check_coherence.py
"""
import sys
import requests

B = "http://localhost:8000"
g = lambda p: requests.get(B + p, timeout=10).json()

fails = 0


def chk(name, a, b, tol=0.02):
    global fails
    if a is None or b is None:
        ok = a == b
    else:
        ok = abs(a - b) <= tol * max(1, abs(b))
    print(f"  [{'OK ' if ok else 'XX '}] {name}: {a} vs {b}")
    fails += 0 if ok else 1
    return ok


def main():
    stats = g("/api/stats")
    rd = g("/api/kpis/readable?limit=100&micro_batch_window_hours=24")
    reasons = g("/api/fraud/reasons/stats")
    chko = g("/api/checkout/stats?window_hours=24")
    idn = g("/api/identity/stats")
    an = g("/api/analytics/status")

    print("== FRAUDE (interne /api/stats) ==")
    sev = stats["alerts_by_severity"]
    chk("Σ sévérités == total_alerts", sev["HIGH"] + sev["MEDIUM"] + sev["LOW"], stats["total_alerts"])
    chk("taux == frauduleux/paiements*100", round(stats["fraudulent_payments"] / stats["total_payments"] * 100, 2), stats["fraud_rate"])
    chk("couverture == alerted/total*100", round(stats["alerted_customers"] / stats["total_customers"] * 100, 2), stats["customer_alert_coverage"])
    chk("Σ alerts_by_day == total", sum(d["count"] for d in stats["alerts_by_day"]), stats["total_alerts"])
    chk("Σ alerts_by_hour == total", sum(d["count"] for d in stats["alerts_by_hour"]), stats["total_alerts"])

    print("== FRAUDE (readable cohérent avec stats) ==")
    f = rd["fraud"]["kpis"]
    chk("readable.total == stats.total", f["total_alerts"], stats["total_alerts"])
    chk("alert_per_fraud == total/frauduleux", f["alert_per_fraud_payment"], round(stats["total_alerts"] / stats["fraudulent_payments"], 2), 0.05)
    chk("alert_to_payment == total/paiements", f["alert_to_payment_ratio"], round(stats["total_alerts"] / stats["total_payments"], 2), 0.05)

    print("== MOTIFS (non exclusifs) ==")
    sr = sum(r["total"] for r in reasons)
    print(f"  Σ motifs={sr} vs total={stats['total_alerts']} -> {'non-exclusifs (attendu)' if sr > stats['total_alerts'] else 'exclusifs'}")
    bad = [r["reason"] for r in reasons if r["high"] + r["medium"] + r["low"] != r["total"]]
    print(f"  high+med+low != total : {bad or 'aucun (OK)'}")
    fails_local = len(bad)

    print("== IDENTITÉ / CHECKOUT ==")
    bs, bm = idn["by_status"], idn["by_method"]
    chk("Σ statut == total_verifications", bs["rejected"] + bs["verified"], idn["total_verifications"])
    chk("Σ méthode == total_verifications", bm["checkout_guardrail"] + bm["ai"], idn["total_verifications"])
    chk("attempts == checkout_guardrail", chko["total_attempts"], bm["checkout_guardrail"])
    chk("acceptées+bloquées == attempts", chko["accepted_orders"] + chko["blocked_underage_orders"], chko["total_attempts"])
    chk("adult_rejected == blocked_underage", chko["adult_product_rejected"], chko["blocked_underage_orders"])

    print("== LIVE vs WAREHOUSE (temporel) ==")
    lr = an["latest_report"]
    print(f"  warehouse fraud_alert={lr['facts']['fact_fraud_alert']} (gelé {lr['generated_at'][:10]}, {lr['status']})")
    print(f"  live total_alerts={stats['total_alerts']} ({stats['alerts_by_day'][-1]['day']})")
    print("  -> 2 instantanés à 2 dates : à dater à l'écran, pas une contradiction.")

    total_fails = fails + fails_local
    print(f"\n{'TOUS LES INVARIANTS OK' if total_fails == 0 else str(total_fails) + ' INVARIANT(S) EN ÉCHEC'}")
    sys.exit(1 if total_fails else 0)


if __name__ == "__main__":
    main()

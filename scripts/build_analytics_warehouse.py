#!/usr/bin/env python3
"""
Construit un entrepôt analytique minimal dans PostgreSQL.

Objectifs:
- matérialiser une couche analytique séparée du store opérationnel
- créer dimensions, faits et datamarts métier
- produire un rapport exploitable pour l'audit RNCP
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg2


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT_DIR / "logs" / "analytics_warehouse_report.json"


def pg_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "kivendtout"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )


DDL = """
CREATE SCHEMA IF NOT EXISTS analytics;

DROP MATERIALIZED VIEW IF EXISTS analytics.mart_product_sales_daily CASCADE;
DROP MATERIALIZED VIEW IF EXISTS analytics.mart_checkout_risk_daily CASCADE;
DROP MATERIALIZED VIEW IF EXISTS analytics.mart_identity_controls_daily CASCADE;
DROP MATERIALIZED VIEW IF EXISTS analytics.mart_fraud_daily CASCADE;

DROP TABLE IF EXISTS analytics.fact_fraud_alert CASCADE;
DROP TABLE IF EXISTS analytics.fact_checkout_attempt CASCADE;
DROP TABLE IF EXISTS analytics.fact_identity_verification CASCADE;
DROP TABLE IF EXISTS analytics.fact_payment CASCADE;
DROP TABLE IF EXISTS analytics.fact_order CASCADE;
DROP TABLE IF EXISTS analytics.dim_product CASCADE;
DROP TABLE IF EXISTS analytics.dim_customer CASCADE;
DROP TABLE IF EXISTS analytics.dim_date CASCADE;
DROP TABLE IF EXISTS analytics.refresh_log CASCADE;

CREATE TABLE analytics.refresh_log (
    refresh_id BIGSERIAL PRIMARY KEY,
    refreshed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_scope TEXT NOT NULL,
    dimensions_count INT NOT NULL,
    facts_count INT NOT NULL,
    marts_count INT NOT NULL,
    notes TEXT
);

CREATE TABLE analytics.dim_date AS
WITH source_dates AS (
    SELECT DATE(order_date) AS d FROM orders
    UNION
    SELECT DATE(payment_date) AS d FROM payments
    UNION
    SELECT DATE(verification_date) AS d FROM identity_verifications
    UNION
    SELECT DATE(alert_timestamp) AS d FROM fraud_alerts
    UNION
    SELECT DATE(attempted_at) AS d FROM checkout_attempts
)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INT AS date_key,
    d AS calendar_date,
    EXTRACT(YEAR FROM d)::INT AS year,
    EXTRACT(MONTH FROM d)::INT AS month,
    EXTRACT(DAY FROM d)::INT AS day,
    EXTRACT(ISODOW FROM d)::INT AS iso_weekday,
    EXTRACT(WEEK FROM d)::INT AS iso_week,
    TO_CHAR(d, 'YYYY-MM') AS year_month
FROM source_dates
WHERE d IS NOT NULL
ORDER BY d;
ALTER TABLE analytics.dim_date ADD PRIMARY KEY (date_key);

CREATE TABLE analytics.dim_customer AS
SELECT
    c.customer_id,
    c.email,
    c.first_name,
    c.last_name,
    c.country,
    c.created_at,
    c.date_of_birth,
    CASE
        WHEN c.date_of_birth IS NULL THEN NULL
        ELSE EXTRACT(YEAR FROM AGE(CURRENT_DATE, c.date_of_birth))::INT
    END AS age_years,
    CASE
        WHEN c.date_of_birth IS NULL THEN 'unknown'
        WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, c.date_of_birth)) < 18 THEN 'minor'
        WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, c.date_of_birth)) < 25 THEN '18_24'
        WHEN EXTRACT(YEAR FROM AGE(CURRENT_DATE, c.date_of_birth)) < 40 THEN '25_39'
        ELSE '40_plus'
    END AS age_bucket
FROM customers c;
ALTER TABLE analytics.dim_customer ADD PRIMARY KEY (customer_id);

CREATE TABLE analytics.dim_product AS
SELECT
    p.product_id,
    p.name,
    p.category,
    p.subcategory,
    p.brand,
    p.price,
    p.stock_quantity,
    CASE WHEN LOWER(COALESCE(p.category, '')) = 'adult' THEN TRUE ELSE FALSE END AS is_adult_restricted
FROM products p;
ALTER TABLE analytics.dim_product ADD PRIMARY KEY (product_id);

CREATE TABLE analytics.fact_order AS
SELECT
    o.order_id,
    o.customer_id,
    TO_CHAR(DATE(o.order_date), 'YYYYMMDD')::INT AS order_date_key,
    o.order_date,
    o.total_amount,
    o.status,
    COUNT(oi.order_item_id)::INT AS items_count,
    COALESCE(SUM(oi.quantity), 0)::INT AS units_count
FROM orders o
LEFT JOIN order_items oi ON oi.order_id = o.order_id
GROUP BY o.order_id, o.customer_id, DATE(o.order_date), o.order_date, o.total_amount, o.status;
ALTER TABLE analytics.fact_order ADD PRIMARY KEY (order_id);

CREATE TABLE analytics.fact_payment AS
SELECT
    p.payment_id,
    p.order_id,
    o.customer_id,
    TO_CHAR(DATE(p.payment_date), 'YYYYMMDD')::INT AS payment_date_key,
    p.payment_date,
    p.amount,
    COALESCE(p.payment_method, 'unknown') AS payment_method,
    COALESCE(p.payment_status, 'unknown') AS payment_status,
    COALESCE(p.is_fraudulent, FALSE) AS is_fraudulent,
    p.browser,
    p.device_id
FROM payments p
LEFT JOIN orders o ON o.order_id = p.order_id;
ALTER TABLE analytics.fact_payment ADD PRIMARY KEY (payment_id);

CREATE TABLE analytics.fact_identity_verification AS
SELECT
    verification_id,
    customer_id,
    TO_CHAR(DATE(verification_date), 'YYYYMMDD')::INT AS verification_date_key,
    verification_date,
    COALESCE(document_type, 'unknown') AS document_type,
    COALESCE(verification_status, 'unknown') AS verification_status,
    COALESCE(verification_method, 'unknown') AS verification_method,
    id_card_image_path
FROM identity_verifications;
ALTER TABLE analytics.fact_identity_verification ADD PRIMARY KEY (verification_id);

CREATE TABLE analytics.fact_checkout_attempt AS
SELECT
    attempt_id,
    customer_id,
    order_id,
    TO_CHAR(DATE(attempted_at), 'YYYYMMDD')::INT AS attempted_date_key,
    attempted_at,
    id_card_file,
    customer_age,
    contains_adult_product,
    blocked_underage,
    accepted,
    total_amount,
    blocked_products
FROM checkout_attempts;
ALTER TABLE analytics.fact_checkout_attempt ADD PRIMARY KEY (attempt_id);

CREATE TABLE analytics.fact_fraud_alert AS
SELECT
    alert_id,
    customer_id,
    session_id,
    TO_CHAR(DATE(alert_timestamp), 'YYYYMMDD')::INT AS alert_date_key,
    alert_timestamp,
    COALESCE(event_type, 'unknown') AS event_type,
    COALESCE(severity, 'unknown') AS severity,
    COALESCE(status, 'unknown') AS status,
    COALESCE(risk_score, 0) AS risk_score
FROM fraud_alerts;
ALTER TABLE analytics.fact_fraud_alert ADD PRIMARY KEY (alert_id);

CREATE MATERIALIZED VIEW analytics.mart_fraud_daily AS
SELECT
    d.date_key,
    d.calendar_date,
    COUNT(fp.payment_id)::INT AS payments_total,
    COALESCE(SUM(CASE WHEN fp.payment_status = 'success' THEN 1 ELSE 0 END), 0)::INT AS payments_success,
    COALESCE(SUM(CASE WHEN fp.payment_status <> 'success' THEN 1 ELSE 0 END), 0)::INT AS payments_failed,
    COALESCE(SUM(CASE WHEN fp.payment_status = 'success' AND fp.is_fraudulent THEN 1 ELSE 0 END), 0)::INT AS fraudulent_payments,
    COALESCE(COUNT(fa.alert_id), 0)::INT AS alerts_total,
    COALESCE(SUM(CASE WHEN fa.severity = 'HIGH' THEN 1 ELSE 0 END), 0)::INT AS high_severity_alerts,
    ROUND(
        COALESCE(
            SUM(CASE WHEN fp.payment_status = 'success' AND fp.is_fraudulent THEN 1 ELSE 0 END)::NUMERIC
            / NULLIF(SUM(CASE WHEN fp.payment_status = 'success' THEN 1 ELSE 0 END), 0) * 100,
            0
        ),
        2
    ) AS fraud_rate_percent
FROM analytics.dim_date d
LEFT JOIN analytics.fact_payment fp ON fp.payment_date_key = d.date_key
LEFT JOIN analytics.fact_fraud_alert fa ON fa.alert_date_key = d.date_key
GROUP BY d.date_key, d.calendar_date
ORDER BY d.calendar_date DESC;

CREATE MATERIALIZED VIEW analytics.mart_identity_controls_daily AS
SELECT
    d.date_key,
    d.calendar_date,
    COUNT(iv.verification_id)::INT AS verifications_total,
    COALESCE(SUM(CASE WHEN iv.verification_status IN ('rejected', 'rejected_underage') THEN 1 ELSE 0 END), 0)::INT AS verifications_rejected,
    COALESCE(SUM(CASE WHEN iv.verification_status = 'verified' THEN 1 ELSE 0 END), 0)::INT AS verifications_verified,
    COALESCE(SUM(CASE WHEN iv.verification_method = 'checkout_guardrail' THEN 1 ELSE 0 END), 0)::INT AS checkout_guardrail_verifications
FROM analytics.dim_date d
LEFT JOIN analytics.fact_identity_verification iv ON iv.verification_date_key = d.date_key
GROUP BY d.date_key, d.calendar_date
ORDER BY d.calendar_date DESC;

CREATE MATERIALIZED VIEW analytics.mart_checkout_risk_daily AS
SELECT
    d.date_key,
    d.calendar_date,
    COUNT(ca.attempt_id)::INT AS checkout_attempts,
    COALESCE(SUM(CASE WHEN ca.accepted THEN 1 ELSE 0 END), 0)::INT AS accepted_orders,
    COALESCE(SUM(CASE WHEN ca.blocked_underage THEN 1 ELSE 0 END), 0)::INT AS blocked_underage_orders,
    COALESCE(SUM(CASE WHEN ca.contains_adult_product THEN 1 ELSE 0 END), 0)::INT AS adult_product_attempts,
    ROUND(
        COALESCE(
            SUM(CASE WHEN ca.blocked_underage THEN 1 ELSE 0 END)::NUMERIC
            / NULLIF(COUNT(ca.attempt_id), 0) * 100,
            0
        ),
        2
    ) AS blocked_underage_rate_percent,
    ROUND(COALESCE(AVG(ca.customer_age), 0), 2) AS avg_customer_age
FROM analytics.dim_date d
LEFT JOIN analytics.fact_checkout_attempt ca ON ca.attempted_date_key = d.date_key
GROUP BY d.date_key, d.calendar_date
ORDER BY d.calendar_date DESC;

CREATE MATERIALIZED VIEW analytics.mart_product_sales_daily AS
SELECT
    TO_CHAR(DATE(o.order_date), 'YYYYMMDD')::INT AS date_key,
    DATE(o.order_date) AS calendar_date,
    oi.product_id,
    p.name AS product_name,
    p.category,
    SUM(oi.quantity)::INT AS units_sold,
    ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
JOIN products p ON p.product_id = oi.product_id
GROUP BY DATE(o.order_date), oi.product_id, p.name, p.category
ORDER BY calendar_date DESC, revenue DESC;
"""


REPORT_SQL = """
SELECT
    (SELECT COUNT(*) FROM analytics.dim_date) AS dim_date_count,
    (SELECT COUNT(*) FROM analytics.dim_customer) AS dim_customer_count,
    (SELECT COUNT(*) FROM analytics.dim_product) AS dim_product_count,
    (SELECT COUNT(*) FROM analytics.fact_order) AS fact_order_count,
    (SELECT COUNT(*) FROM analytics.fact_payment) AS fact_payment_count,
    (SELECT COUNT(*) FROM analytics.fact_identity_verification) AS fact_identity_verification_count,
    (SELECT COUNT(*) FROM analytics.fact_checkout_attempt) AS fact_checkout_attempt_count,
    (SELECT COUNT(*) FROM analytics.fact_fraud_alert) AS fact_fraud_alert_count,
    (SELECT COUNT(*) FROM analytics.mart_fraud_daily) AS mart_fraud_daily_count,
    (SELECT COUNT(*) FROM analytics.mart_identity_controls_daily) AS mart_identity_controls_daily_count,
    (SELECT COUNT(*) FROM analytics.mart_checkout_risk_daily) AS mart_checkout_risk_daily_count,
    (SELECT COUNT(*) FROM analytics.mart_product_sales_daily) AS mart_product_sales_daily_count
"""


SOURCE_REPORT_SQL = """
SELECT
    (SELECT COUNT(*) FROM orders) AS src_orders_count,
    (SELECT COUNT(*) FROM payments) AS src_payments_count,
    (SELECT COUNT(*) FROM identity_verifications) AS src_identity_verifications_count,
    (SELECT COUNT(*) FROM checkout_attempts) AS src_checkout_attempts_count,
    (SELECT COUNT(*) FROM fraud_alerts) AS src_fraud_alerts_count,
    (SELECT MAX(DATE(order_date)) FROM orders) AS src_orders_latest_date,
    (SELECT MAX(DATE(payment_date)) FROM payments) AS src_payments_latest_date,
    (SELECT MAX(DATE(verification_date)) FROM identity_verifications) AS src_identity_latest_date,
    (SELECT MAX(DATE(attempted_at)) FROM checkout_attempts) AS src_checkout_latest_date,
    (SELECT MAX(DATE(alert_timestamp)) FROM fraud_alerts) AS src_alerts_latest_date
"""


def _as_iso(value):
    return str(value) if value is not None else None


def _max_date(*values):
    dates = [value for value in values if value is not None]
    return max(dates) if dates else None


def build_report(conn) -> dict:
    with conn.cursor() as cursor:
        cursor.execute(REPORT_SQL)
        row = cursor.fetchone()
        columns = [desc[0] for desc in cursor.description]
        counts = dict(zip(columns, row))

        cursor.execute(SOURCE_REPORT_SQL)
        source_row = cursor.fetchone()
        source_columns = [desc[0] for desc in cursor.description]
        source_counts = dict(zip(source_columns, source_row))

        cursor.execute(
            """
            SELECT
                MAX(calendar_date) AS mart_fraud_latest,
                (SELECT MAX(calendar_date) FROM analytics.mart_identity_controls_daily) AS mart_identity_latest,
                (SELECT MAX(calendar_date) FROM analytics.mart_checkout_risk_daily) AS mart_checkout_latest,
                (SELECT MAX(calendar_date) FROM analytics.mart_product_sales_daily) AS mart_product_latest
            FROM analytics.mart_fraud_daily
            """
        )
        latest = cursor.fetchone()
        latest_columns = [desc[0] for desc in cursor.description]
        latest_dates = {k: _as_iso(v) for k, v in zip(latest_columns, latest)}

        dimensions_count = sum(counts[k] for k in counts if k.startswith("dim_"))
        facts_count = sum(counts[k] for k in counts if k.startswith("fact_"))
        marts_count = sum(counts[k] for k in counts if k.startswith("mart_"))

        consistency_checks = {
            "fact_order_vs_orders": {
                "expected": int(source_counts["src_orders_count"] or 0),
                "actual": int(counts["fact_order_count"] or 0),
            },
            "fact_payment_vs_payments": {
                "expected": int(source_counts["src_payments_count"] or 0),
                "actual": int(counts["fact_payment_count"] or 0),
            },
            "fact_identity_verification_vs_identity_verifications": {
                "expected": int(source_counts["src_identity_verifications_count"] or 0),
                "actual": int(counts["fact_identity_verification_count"] or 0),
            },
            "fact_checkout_attempt_vs_checkout_attempts": {
                "expected": int(source_counts["src_checkout_attempts_count"] or 0),
                "actual": int(counts["fact_checkout_attempt_count"] or 0),
            },
            "fact_fraud_alert_vs_fraud_alerts": {
                "expected": int(source_counts["src_fraud_alerts_count"] or 0),
                "actual": int(counts["fact_fraud_alert_count"] or 0),
            },
        }
        for payload in consistency_checks.values():
            payload["status"] = "PASS" if payload["expected"] == payload["actual"] else "FAIL"

        fraud_source_latest = _max_date(
            source_counts["src_payments_latest_date"],
            source_counts["src_alerts_latest_date"],
        )
        freshness_checks = {
            "mart_fraud_daily": {
                "expected_latest_date": _as_iso(fraud_source_latest),
                "actual_latest_date": latest_dates["mart_fraud_latest"],
            },
            "mart_identity_controls_daily": {
                "expected_latest_date": _as_iso(source_counts["src_identity_latest_date"]),
                "actual_latest_date": latest_dates["mart_identity_latest"],
            },
            "mart_checkout_risk_daily": {
                "expected_latest_date": _as_iso(source_counts["src_checkout_latest_date"]),
                "actual_latest_date": latest_dates["mart_checkout_latest"],
            },
            "mart_product_sales_daily": {
                "expected_latest_date": _as_iso(source_counts["src_orders_latest_date"]),
                "actual_latest_date": latest_dates["mart_product_latest"],
            },
        }
        for payload in freshness_checks.values():
            payload["status"] = "PASS" if payload["expected_latest_date"] == payload["actual_latest_date"] else "FAIL"

        all_checks = list(consistency_checks.values()) + list(freshness_checks.values())
        checks_passed = sum(1 for item in all_checks if item["status"] == "PASS")
        checks_total = len(all_checks)
        checks_failed = checks_total - checks_passed
        status = "PASS" if checks_failed == 0 else "FAIL"

        cursor.execute(
            """
            INSERT INTO analytics.refresh_log(source_scope, dimensions_count, facts_count, marts_count, notes)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING refresh_id, refreshed_at
            """,
            (
                "postgres_operational_to_analytics",
                dimensions_count,
                facts_count,
                marts_count,
                f"Warehouse rebuilt from operational store | consistency={checks_passed}/{checks_total}",
            ),
        )
        refresh_id, refreshed_at = cursor.fetchone()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "schema": "analytics",
        "dimensions": {
            "dim_date": counts["dim_date_count"],
            "dim_customer": counts["dim_customer_count"],
            "dim_product": counts["dim_product_count"],
        },
        "facts": {
            "fact_order": counts["fact_order_count"],
            "fact_payment": counts["fact_payment_count"],
            "fact_identity_verification": counts["fact_identity_verification_count"],
            "fact_checkout_attempt": counts["fact_checkout_attempt_count"],
            "fact_fraud_alert": counts["fact_fraud_alert_count"],
        },
        "datamarts": {
            "mart_fraud_daily": counts["mart_fraud_daily_count"],
            "mart_identity_controls_daily": counts["mart_identity_controls_daily_count"],
            "mart_checkout_risk_daily": counts["mart_checkout_risk_daily_count"],
            "mart_product_sales_daily": counts["mart_product_sales_daily_count"],
        },
        "operational_source": {
            "orders": int(source_counts["src_orders_count"] or 0),
            "payments": int(source_counts["src_payments_count"] or 0),
            "identity_verifications": int(source_counts["src_identity_verifications_count"] or 0),
            "checkout_attempts": int(source_counts["src_checkout_attempts_count"] or 0),
            "fraud_alerts": int(source_counts["src_fraud_alerts_count"] or 0),
        },
        "consistency_checks": consistency_checks,
        "freshness_checks": freshness_checks,
        "summary": {
            "total_checks": checks_total,
            "passed": checks_passed,
            "failed": checks_failed,
            "success_rate_percent": round((checks_passed / checks_total) * 100, 2) if checks_total else 100.0,
        },
        "latest_dates": latest_dates,
        "refresh_log": {
            "refresh_id": refresh_id,
            "refreshed_at": refreshed_at.isoformat() if refreshed_at else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Construit le warehouse analytique minimal et les datamarts")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT_DIR / output
    output.parent.mkdir(parents=True, exist_ok=True)

    with pg_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(DDL)
        conn.commit()
        report = build_report(conn)
        conn.commit()

    output.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    print("=== ANALYTICS WAREHOUSE BUILD ===")
    print(f"Schema       : {report['schema']}")
    print(f"Dimensions   : {sum(report['dimensions'].values())}")
    print(f"Facts        : {sum(report['facts'].values())}")
    print(f"Datamarts    : {sum(report['datamarts'].values())}")
    print(f"Checks       : {report['summary']['passed']}/{report['summary']['total_checks']} {report['status']}")
    print(f"Report       : {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

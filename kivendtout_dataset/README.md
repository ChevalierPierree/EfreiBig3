# KiVendTout — Dataset synthétique (projet de cours)

Dataset 100% synthétique (aucune donnée réelle). Conçu pour votre stack :
PostgreSQL, Kafka, MongoDB, MinIO+Parquet, Flink, Airflow, dbt, Superset, FastAPI, Great Expectations, Prometheus/Grafana, TensorFlow+OpenCV.

## Fichiers principaux
- customers.csv (2500)
- products.csv (200)
- sessions.csv (6000)
- events.jsonl (71694)
- payments.csv (1583)
- orders.csv (1289)
- order_items.csv (2651)
- fraud_alerts.csv (20)
- synthetic_id_cards/ (60 images) + synthetic_id_labels.csv
- Parquet généré: False

## Schéma event (extrait)
event_id, ts, event_type, customer_id, session_id, device, ip_hash, utm_source, utm_campaign, product_id?, cart_value?, payment_id?, order_id?

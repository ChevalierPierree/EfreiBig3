# Checklist Sujet 1

## Objectif

Valider les exigences du sujet 1 et les controles complementaires avec des preuves executables.

## Sujet 1

1. Securiser l'API
   - cle API optionnelle,
   - hash `SHA-256` du `document_number` sur `POST /api/verify-id`.
2. Activer la reconnaissance CNI
   - entrainement: `scripts/train_id_card_fingerprint_model.py`,
   - inference dans l'API avec fallback labels.
3. Centraliser les donnees brutes avec historisation
   - snapshot MinIO bronze: `scripts/snapshot_raw_data_to_minio.sh`.
   - promotion exploitable vers `silver` et `gold`: `scripts/promote_data_lake_layers.py`.
4. Mesurer la qualite des donnees
   - `scripts/data_quality_checks.py`.
5. Valider le parcours complet
   - `scripts/validate_sujet1.py`,
   - rapport: `logs/sujet1_validation_report.json`.

## Controles complementaires

1. RBAC et quotas API
   - `scripts/test_api_rbac_rate_limit.py`
2. Securite MinIO
   - `scripts/generate_minio_tls_certs.sh`
   - `scripts/rotate_minio_credentials.sh all`
3. Flux micro-batch
   - `scripts/micro_batch_events_to_postgres.py`
   - `GET /api/micro-batch/stats`
4. Charge DB et resilience
   - `scripts/test_db_load.py`
   - `scripts/test_resilience_failover.py`
5. KPI transfert standardises
   - `GET /api/transfer/kpis`
   - `GET /api/kpis/readable`
   - `GET /api/data-lake/status`
   - `GET /api/payments/stats`
   - `dashboard/transfer_kpi_dashboard.html`
6. Validation globale
   - `scripts/validate_perfect_compliance.py`
   - rapport: `logs/perfect_compliance_report.json`

## Commandes

```bash
bash scripts/finalize_school_delivery.sh
./.venv/bin/python scripts/train_id_card_fingerprint_model.py
bash scripts/snapshot_raw_data_to_minio.sh
./.venv/bin/python scripts/promote_data_lake_layers.py
./.venv/bin/python scripts/data_quality_checks.py
./.venv/bin/python scripts/validate_sujet1.py
./.venv/bin/python scripts/test_api_rbac_rate_limit.py
./.venv/bin/python scripts/run_data_platform_pipeline.py
bash scripts/generate_minio_tls_certs.sh
bash scripts/rotate_minio_credentials.sh all
bash scripts/run_micro_batch.sh once
./.venv/bin/python scripts/test_db_load.py --pg-requests 120 --mongo-requests 120 --concurrency 12
./.venv/bin/python scripts/test_resilience_failover.py --service postgres
./.venv/bin/python scripts/validate_perfect_compliance.py
bash scripts/clean_project_artifacts.sh
bash scripts/build_delivery_pack.sh
```

## Preuves attendues

- `models/id_card_fingerprint_model.json`
- `logs/id_card_model_report.json`
- `logs/data_lake_snapshot_*.json`
- `logs/data_lake_promotion_*.json`
- `logs/data_quality_report.json`
- `logs/data_platform_pipeline_report.json`
- `logs/sujet1_validation_report.json`
- `logs/api_rbac_rate_limit_report.json`
- `logs/db_load_test_report.json`
- `logs/resilience_failover_report.json`
- `logs/transfer_kpi_history.jsonl`
- `logs/perfect_compliance_report.json`

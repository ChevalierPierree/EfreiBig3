# RNCP Bloc 1 - Traceabilite Des Preuves

Date: 2026-03-18

## Usage

Cette matrice relie chaque competence du Bloc 1 a:
- sa mise en oeuvre dans le projet
- ses preuves techniques
- ses pieces documentaires

## C1.1 Base de donnees relationnelle

Implementation:
- PostgreSQL pour clients, produits, commandes, paiements, verifications d'identite, tentatives de checkout

Preuves:
- `database/postgres/init/`
- `logs/data_quality_report.json`
- `logs/db_load_test_report.json`
- `ARCHITECTURE_DECISIONS.md`
- `GOUVERNANCE_ET_PARTIES_PRENANTES.md`

## C1.2 Base de donnees non relationnelle

Implementation:
- MongoDB pour les evenements semi-structures et la source du micro-batch

Preuves:
- `scripts/load_complete_data_to_mongodb.py`
- `scripts/micro_batch_events_to_postgres.py`
- `VEILLE_TECHNOLOGIQUE_BLOC1.md`
- `ARCHITECTURE_DECISIONS.md`

## C1.3 Data Lake

Implementation:
- MinIO avec `bronze`, `silver`, `gold`, `models`
- snapshot brut et promotion de couches

Preuves:
- `scripts/snapshot_raw_data_to_minio.sh`
- `scripts/promote_data_lake_layers.py`
- `security/minio/policies/`
- `logs/data_lake_promotion_*.json`
- `logs/transfer_kpi_history.jsonl`
- `GOUVERNANCE_ET_PARTIES_PRENANTES.md`

## C1.4 Infrastructures scalables et resilientes

Implementation:
- stack conteneurisee, tests de charge DB, test de failover PostgreSQL

Preuves:
- `docker-compose.yml`
- `scripts/test_db_load.py`
- `scripts/test_resilience_failover.py`
- `logs/db_load_test_report.json`
- `logs/resilience_failover_report.json`
- `VEILLE_TECHNOLOGIQUE_BLOC1.md`

## C2.1 API d'acces aux donnees

Implementation:
- FastAPI pour les endpoints metier, de supervision, de demonstration et d'administration

Preuves:
- `api/fraud_dashboard_api.py`
- `logs/api_rbac_rate_limit_report.json`
- `README.md`
- `ARCHITECTURE_DECISIONS.md`

## C2.2 Systeme distribue et streaming

Implementation:
- Kafka pour les flux, SSE pour les dashboards, micro-batch MongoDB -> PostgreSQL

Preuves:
- `dashboard/live_sync.js`
- `scripts/run_micro_batch.sh`
- `scripts/micro_batch_events_to_postgres.py`
- `VEILLE_TECHNOLOGIQUE_BLOC1.md`
- `logs/transfer_kpi_history.jsonl`

## C2.3 Transformation multi-sources

Implementation:
- sources CSV/JSONL/PNG + PostgreSQL + MongoDB + MinIO
- schema `analytics` avec dimensions, faits et datamarts

Preuves:
- `scripts/build_analytics_warehouse.py`
- `logs/analytics_warehouse_report.json`
- `api/fraud_dashboard_api.py` (`/api/analytics/status`)
- `AUDIT_ARCHITECTURE_DATA.md`
- `ARCHITECTURE_DECISIONS.md`

## C2.4 Performance des pipelines

Implementation:
- KPI transfert, mesures de micro-batch, tests de charge, qualite de donnees

Preuves:
- `logs/db_load_test_report.json`
- `logs/data_quality_report.json`
- `logs/perfect_compliance_report.json`
- `dashboard/transfer_kpi_dashboard.html`

## Conclusion

Pour un rendu scolaire, cette matrice permet d'appuyer chaque competence par:
- du code
- des scripts de validation
- des rapports techniques
- des documents de justification

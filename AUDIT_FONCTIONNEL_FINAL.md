# Audit Fonctionnel Final

Date: 2026-03-18

## Referentiels controles

- `README.md`
- `AUDIT_CONSIGNE_INITIALE.md`
- `SUJET1_CHECKLIST.md`
- `DEMO_PROJET.md`
- `BATTERIE_TESTS_JURY.md`
- `PACK_RENDU.md`

## Conclusion

Le projet est fonctionnel et coherent avec les features annoncees dans les briefs lus.

Statut global:
- plateforme: `OK`
- sujet 1: `PASS 11/11`
- conformite complementaire: `PASS 6/6`
- qualite des donnees: `PASS 18/18`
- checklist plateforme: `33/33 OK`

Point non bloquant:
- les notifications email fonctionnent en mode `preview` tant qu'aucun SMTP reel n'est configure.

## Validations executees

1. `bash scripts/checklist_and_launch.sh`
   - resultat: `33/33 OK`
2. `bash scripts/run_perfect_compliance.sh`
   - resultat: `Sujet 1 PASS 11/11`
   - resultat: `Perfect compliance PASS 6/6`
3. `bash scripts/test_use_cases.sh`
   - resultat: `all_passed=True`
4. `bash scripts/test_alert_notifications.sh`
   - resultat: workflow `new_alert`, `manual`, `decision` present
5. `./.venv/bin/python scripts/data_quality_checks.py`
   - resultat: `18/18 PASS`
6. `POST /api/presentation/tests/platform-readiness/run`
   - resultat: `passed=true`
7. `POST /api/presentation/tests/core-use-cases/run`
   - resultat: `passed=true`
8. `POST /api/presentation/tests/notifications-workflow/run`
   - resultat: `passed=true`
9. `POST /api/presentation/tests/payments-live-3m/run`
   - verification delta OK
10. `POST /api/presentation/tests/massive-fraud-orders-episode/run`
   - verification delta OK
11. `POST /api/system/reset-data`
   - resultat: reset termine avec succes

## Controle par feature

### 1. API checkout scalable + controle d'age

Statut: `OK`

Preuves:
- endpoint `POST /api/orders/checkout`
- use case `minor-adult-checkout`: `HTTP 403`
- use case `adult-adult-checkout`: `HTTP 200`
- script `scripts/scale_order_api.py`

Observation:
- la regle metier `mineur + produit Adult = refus` est bien appliquee et rejouable.

### 2. Verification d'identite + hash SHA-256

Statut: `OK`

Preuves:
- use case `identity-verification`: `passed=True`
- stockage `document_number_stored_as=sha256`
- endpoint `POST /api/verify-id`

Observation:
- la preuve d'audit est bien presente et le document n'est pas stocke en clair.

### 3. Alertes fraude + backlog analyste

Statut: `OK`

Preuves:
- use case `high-risk-alert`: `passed=True`
- dashboard `fraud_dashboard.html`
- dashboard `fraud_types_dashboard.html`
- endpoint `GET /api/alerts`

Observation:
- l'alerte HIGH est bien creee, visible et exploitable.

### 4. Notifications d'alertes

Statut: `OK avec reserve mineure`

Preuves:
- `bash scripts/test_alert_notifications.sh`
- `POST /api/presentation/tests/notifications-workflow/run`
- evenements observes: `new_alert`, `manual`, `decision`

Reserve:
- mode courant `preview`
- pour un envoi reel, il faut configurer `ALERT_SMTP_*`

### 5. Dashboards live + SSE + refresh 1 seconde

Statut: `OK`

Preuves:
- checklist `33/33 OK`
- `GET /api/live/state` retourne `heartbeat_seconds=1.0`
- dashboards accessibles:
  - `index.html`
  - `fraud_dashboard.html`
  - `fraud_types_dashboard.html`
  - `id_cards_dashboard.html`
  - `transfer_kpi_dashboard.html`
  - `use_cases_dashboard.html`

Observation:
- les vues sont servies et raccordees au flux live.

### 6. Console de demonstration sur l'overview

Statut: `OK`

Preuves:
- section `Parcours de demonstration` sur `dashboard/index.html`
- `GET /api/presentation/tests`
- lancement direct des tests depuis `/api/presentation/tests/{test_key}/run`

Observation:
- la page principale permet maintenant de piloter la demo sans repasser par le terminal.

### 7. Micro-batch exploitable

Statut: `OK`

Preuves:
- `run_perfect_compliance.sh` a traite une fenetre
- batch observe:
  - `events=1`
  - `types=1`
  - `processing_latency_ms=7.22`
  - `speed_events_per_sec=138.59`

Observation:
- le micro-batch est fonctionnel et remonte des KPI lisibles.

### 8. Data Lake bronze -> silver -> gold

Statut: `OK`

Preuves:
- snapshot MinIO bronze
- promotion observee dans `run_perfect_compliance.sh`
  - `silver objects: 2`
  - `gold objects: 2`
- endpoint `GET /api/data-lake/status`

Observation:
- le lake est bien present et exploitable au minimum sur 3 couches.

### 9. RBAC + quotas API

Statut: `OK`

Preuves:
- `scripts/test_api_rbac_rate_limit.py`
- rapport `logs/api_rbac_rate_limit_report.json`
- resultat `7/7 PASS`

### 10. Charge DB + resilience

Statut: `OK`

Preuves:
- `scripts/test_db_load.py`
- `scripts/test_resilience_failover.py --dry-run`
- rapport charge:
  - PostgreSQL `p95=64.61 ms`
  - MongoDB `p95=55.98 ms`
- resilience: `PASS`

### 11. Flux paiements realiste faisant varier le fraud_rate

Statut: `OK`

Preuves:
- `POST /api/presentation/tests/payments-live-3m/run`
- mesure avant/apres sur 8 secondes:
  - paiements `2966 -> 3020`
  - paiements frauduleux `288 -> 299`
  - `fraud_rate 9.71% -> 9.9%`

Observation:
- la variation du `fraud_rate` n'est pas factice; elle depend bien des paiements inseres.

### 12. Episode fraude massive sur les commandes

Statut: `OK`

Preuves:
- reset plateforme avant test
- `POST /api/presentation/tests/massive-fraud-orders-episode/run`
- mesure apres 8 secondes:
  - paiements 24h: `0 -> 62`
  - paiements frauduleux 24h: `0 -> 8`
  - `fraud_rate 24h: 0.0% -> 12.9%`
  - tentatives checkout: `0 -> 84`
  - blocages mineurs: `0 -> 22`
  - alertes: `0 -> 161`
  - alertes HIGH: `118`

Observation:
- le scenario de crise est coherent: fraude, identite et alertes montent ensemble.

### 13. Reset vers la base initiale

Statut: `OK`

Preuves:
- `POST /api/system/reset-data`
- fin observee dans `GET /api/live/state`
- resume reset:
  - `postgres_orders=1289`
  - `postgres_payments=1293`
  - `postgres_identity_verifications=60`
  - `postgres_fraud_alerts=0`
  - `postgres_checkout_attempts=0`
  - `postgres_micro_batch_metrics=0`

Observation:
- la demo est rejouable proprement.

## Coherence documentaire

Corrections apportees pendant l'audit:
- `README.md`: `32/32 OK` -> `33/33 OK`
- `BATTERIE_TESTS_JURY.md`: `32/32 OK` -> `33/33 OK`
- `PROMPT_PRESENTATION_IA.md`: `32/32 OK` -> `33/33 OK`

## Ecarts restants

1. Notifications email reelles non branchees
   - impact: faible pour la demo, moyen pour un usage production
   - action: configurer `ALERT_SMTP_HOST`, `ALERT_SMTP_PORT`, `ALERT_SMTP_USERNAME`, `ALERT_SMTP_PASSWORD`, `ALERT_SMTP_FROM`

2. Le pack `delivery_pack/` doit etre regenere apres correction documentaire
   - impact: mineur
   - action: `bash scripts/build_delivery_pack.sh`

## Verdict

Le projet est:
- fonctionnel,
- coherent avec les briefs controles,
- presentable immediatement,
- exploitable dans un contexte de demonstration professionnelle.

Le seul point qui reste en mode demo est l'email reel, actuellement en `preview`.

# Audit Rendu Projet - Sujet 1 (KiVendTout)

Date audit: 2026-03-16

## 1) Référentiels utilisés
- Périmètre Sujet 1: `Sujets M1 Data.pdf` (vérification indirecte via scripts/rapports de validation du sujet).
- Critères Bloc 1 RNCP: extraction `logs/rncp_bloc1_extract.txt` (lignes R17 à R45).
- Preuves d'exécution:
  - `logs/sujet1_validation_report.json` (11/11 PASS)
  - `logs/perfect_compliance_report.json` (6/6 PASS)
  - `logs/data_quality_report.json` (18/18 PASS)

## 2) Synthèse exécutive
- Conformité Sujet 1: **PASS (11/11)**.
- Conformité "parfaite" (compléments): **PASS (6/6)**.
- Qualité des données: **PASS (18/18)**.
- Projet fonctionnel pour une presentation immediate.
- Point de vigilance principal: contamination des volumes OLTP par les tests de charge/simulation (normal en environnement de test, a reinitialiser avant une demonstration si tu veux des chiffres dataset purs).

## 3) Vérification des données

### 3.1 Volumétrie dataset source
- `kivendtout_dataset/customers.csv`: 2,501 lignes (2,500 données + header)
- `kivendtout_dataset/products.csv`: 201 lignes (200 données + header)
- `kivendtout_dataset/orders.csv`: 1,290 lignes (1,289 données + header)
- `kivendtout_dataset/order_items.csv`: 2,652 lignes (2,651 données + header)
- `kivendtout_dataset/payments.csv`: 1,584 lignes (1,583 données + header)
- `kivendtout_dataset/events.jsonl`: 71,694 événements

### 3.2 Volumétrie bases (état courant)
- PostgreSQL:
  - `customers`: 2,500
  - `products`: 200
  - `orders`: 3,947
  - `order_items`: 5,309
  - `payments`: 1,293
  - `fraud_alerts`: 5,407
  - `identity_verifications`: 60
  - `checkout_attempts`: 2,785
  - `micro_batch_event_metrics`: 24
- MongoDB:
  - `events`: 71,694
  - `fraud_events`: 0

### 3.3 Conclusion data
- Sources brutes cohérentes avec le périmètre.
- Les écarts OLTP (orders/order_items/payments) sont expliqués par les runs de tests API/charge.
- La qualité logique est validée (`logs/data_quality_report.json`, 18/18).

### 3.4 Écarts techniques relevés
- `micro_batch_event_metrics`: plusieurs fenêtres récentes à `0` événement (pipeline valide mais démonstration faible sur la fenêtre observée).
- `config/api_access_control.json`: le rôle `analyst` ne contient pas `GET:/api/kpis/*` alors que l'endpoint lisible KPI existe (`/api/kpis/readable`), ce qui peut bloquer cet endpoint si la sécurité API est strictement activée.

## 4) Conformité aux critères / périmètre

### 4.1 Sujet 1 (11 exigences)
Statut global: **PASS 11/11** (`logs/sujet1_validation_report.json`).

Exigences validées:
1. Stockage relationnel fiable/intègre
2. Exploitation des événements utilisateurs
3. Centralisation brute historisée
4. Détection fraude temps réel
5. API standardisée
6. Temps d'analyse décisionnelle réduit
7. Scalabilité sous charge
8. Continuité de service/résilience infra
9. Sécurité/protection des accès
10. Qualité des données
11. Reconnaissance CNI + contrôle majorité

### 4.2 RNCP Bloc 1 (extrait R17-R45)
- C1.1 relationnel + intégrité + normalisation: **Conforme** (FK, checks, tests charge DB).
- C1.2 non-relationnel (semi/non structurées): **Conforme** (MongoDB événements).
- C1.3 data lake + KPI latence/capacité/vitesse + sécurité: **Conforme** (MinIO + snapshots + `/api/transfer/kpis` + policies/TLS).
- C1.4 scalabilité/résilience: **Conforme** (infra distribuée + test de résilience dry-run).
- C2.1 API + authentification + autorisations + quotas: **Conforme** (API key + RBAC + rate limit).
- C2.2 streaming realtime + micro-batch: **Conforme avec réserve mineure** (micro-batch en place mais fenêtres récentes parfois sans événements, donc KPI micro-batch peu démonstratifs selon moment du run).
- C2.3 intégration/transformation multi-sources: **Conforme** (PostgreSQL + MongoDB + lake + API).
- C2.4 performance pipelines + indicateurs + qualité: **Conforme** (charge DB, KPI transfert, data quality checks).

## 5) Recensement des éléments en trop pour un rendu projet

## Priorité P1 (à retirer du dépôt de rendu)
Ces éléments sont du bruit technique ou peuvent dégrader l'image du rendu:
- Fichiers système Apple trackés:
  - `.DS_Store`
  - `data/.DS_Store`
  - `database/.DS_Store`
  - `kivendtout_dataset/.DS_Store`
  - `monitoring/.DS_Store`
- Cache Python tracké:
  - `api/__pycache__/fraud_dashboard_api.cpython-313.pyc`
- Logs runtime trackés:
  - `logs/fraud_dashboard_api.log`
  - `logs/fraud_detection.log`
  - `logs/fraud_detection_advanced.log`
  - `logs/http_server.log`
- Secret sensible (si commit accidentel):
  - `security/minio/certs/private.key` (à exclure strictement du rendu)

## Priorite P2 (a archiver hors racine ou exclure du rendu)
Documentation redondante ou contextuelle non nécessaire au périmètre Sujet 1:
- Docs "personnelles/setup":
  - `FIX_VENV_JEAN.md`
  - `SOLUTION_JEAN_VENV.md`
  - `MESSAGE_POUR_JEAN.md`
  - `FIX_PYTHON_313.md`
- Doublons racine vs `markdowns/`:
  - `README.md` et `markdowns/README.md`
  - `INSTALLATION.md` et `markdowns/INSTALLATION.md`
  - `QUICKSTART.md` et `markdowns/QUICKSTART.md`
  - `RECAP_COMPLET_PROJET.md` et `markdowns/RECAP_COMPLET_PROJET.md`

## Priorité P3 (à garder en annexe ou épurer)
- Multiples manifests de snapshot:
  - `logs/data_lake_snapshot_*.json` (garder 1 à 3 max pour preuve)
- Historiques techniques volumineux:
  - `logs/transfer_kpi_history.jsonl` (garder version courte si rendu académique)

## 6) Incohérences documentaires à corriger avant rendu
- `RECAP_COMPLET_PROJET.md` (racine + markdowns) contient des métriques obsolètes/contradictoires:
  - fraude à `143.55%` (non cohérent avec la définition actuelle)
  - port Grafana `4000` (actuel: `3000`)
  - score "estimé" ancien

Recommandation: retirer ce document du pack de rendu ou le réécrire complètement.

## 7) Pack de rendu recommandé (minimal, propre)
- `README.md`
- `INSTALLATION.md`
- `DEMO_PROJET.md`
- `SUJET1_CHECKLIST.md`
- `AUDIT_CONSIGNE_INITIALE.md`
- `api/`, `scripts/`, `dashboard/`, `database/`, `docker-compose.yml`, `kivendtout_dataset/`
- preuves ciblées dans `logs/`:
  - `sujet1_validation_report.json`
  - `perfect_compliance_report.json`
  - `data_quality_report.json`
  - `api_rbac_rate_limit_report.json`
  - `db_load_test_report.json`
  - `resilience_failover_report.json`
  - 1 à 3 `data_lake_snapshot_*.json`

## 8) Commandes utiles avant rendu final
```bash
# 1) Vérifier conformité
./.venv/bin/python scripts/validate_sujet1.py
./.venv/bin/python scripts/validate_perfect_compliance.py

# 2) Nettoyage artefacts runtime
bash scripts/clean_project_artifacts.sh

# 3) Vérifier l'état git avant commit/rendu
git status --short
```

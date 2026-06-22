# KiVendTout

Plateforme data pour e-commerce centree sur le Bloc 1 RNCP40875: stockage, traitement, accessibilite, streaming et supervision des donnees.

## Vue d'ensemble

Le projet couvre les attendus techniques du Bloc 1:
- base relationnelle pour le transactionnel,
- base non relationnelle pour les evenements,
- Data Lake `bronze -> silver -> gold`,
- systeme distribue et micro-batch,
- API d'acces aux donnees,
- mesures de qualite, charge et resilience.

Le socle technique repose sur PostgreSQL, MongoDB, Kafka, MinIO, FastAPI et un front de supervision sur `7600`.

## Demarrage rapide

### Methode automatisee

```bash
cd /Users/jeanmacario/Documents/GitHub/ProjetDataM1JeanPierre
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.patator.txt
./patator
```

### Methode de verification recommandee

```bash
cd /Users/jeanmacario/Documents/GitHub/ProjetDataM1JeanPierre
source .venv/bin/activate
bash scripts/checklist_and_launch.sh
```

## Commandes utiles

### Validation globale

```bash
bash scripts/finalize_school_delivery.sh
./.venv/bin/python scripts/validate_sujet1.py
./.venv/bin/python scripts/validate_perfect_compliance.py
./.venv/bin/python scripts/data_quality_checks.py
```

### Demonstrations Bloc 1

```bash
bash scripts/run_micro_batch.sh once
curl -X POST http://localhost:8000/api/data-factory/payments-live-3m/run -H 'Content-Type: application/json'
./.venv/bin/python scripts/promote_data_lake_layers.py
./.venv/bin/python scripts/build_analytics_warehouse.py
./.venv/bin/python scripts/run_data_platform_pipeline.py
```

### Retour a l'etat initial

```bash
curl -X POST http://localhost:8000/api/system/reset-data \
  -H 'Content-Type: application/json' \
  --data-binary '{"confirm":true,"clear_runtime_artifacts":true,"stop_live_jobs":true}'
```

### Generer le pack de livraison

```bash
bash scripts/build_delivery_pack.sh
```

## Dashboards

- Overview: `http://localhost:7600/index.html`
- Fraude: `http://localhost:7600/fraud_dashboard.html`
- Typologies: `http://localhost:7600/fraud_types_dashboard.html`
- Identite: `http://localhost:7600/id_cards_dashboard.html`
- Transferts: `http://localhost:7600/transfer_kpi_dashboard.html`

La page `Identite` inclut une section `Analyse CNI cote navigateur` qui recalcule age, empreinte image et decision checkout depuis le front.

## Indicateurs importants

- `fraud_rate` = `fraudulent_payments / successful_payments`
- `total_alerts` = volume d'alertes regles, distinct du volume de paiements
- `customer_alert_coverage` = part des clients couverts par au moins une alerte
- KPI transfert = latence, debit, volume traite, sante pipeline

## Endpoints utiles

- `GET /api/stats`: KPI fraude globaux
- `GET /api/checkout/stats?window_hours=24`: pression checkout sur la fenetre recente
- `GET /api/payments/stats?window_hours=24`: KPI paiements recentes et `fraud_rate` live
- `GET /api/micro-batch/stats?window_hours=24`: fenetres micro-batch traitees
- `GET /api/data-lake/status`: etat bronze -> silver -> gold publie dans MinIO
- `GET /api/data-platform/status`: etat consolide de la chaine data
- `GET /api/analytics/status`: etat du schema analytics et des datamarts PostgreSQL
- `POST /api/data-factory/payments-live-3m/run`: flux paiements temps reel
- `POST /api/data-factory/data-lake-pipeline/run`: promotion MinIO bronze -> silver -> gold
- `POST /api/data-factory/analytics-warehouse/run`: reconstruction du warehouse analytics et des datamarts
- `POST /api/data-factory/data-platform-pipeline/run`: orchestration complete snapshot -> lake -> analytics -> qualite

## Documentation racine

- [PATATOR_GUIDE.md](./PATATOR_GUIDE.md): demarrage automatise
- [INSTALLATION.md](./INSTALLATION.md): installation detaillee
- [QUICKSTART.md](./QUICKSTART.md): sequence courte de lancement
- [DEMO_PROJET.md](./DEMO_PROJET.md): runbook Bloc 1
- [SUJET1_CHECKLIST.md](./SUJET1_CHECKLIST.md): checklist de validation
- [AUDIT_CONSIGNE_INITIALE.md](./AUDIT_CONSIGNE_INITIALE.md): cadrage initial et regles metier
- [AUDIT_RENDU_PROJET.md](./AUDIT_RENDU_PROJET.md): audit de conformite et hygiene de depot
- [AUDIT_FONCTIONNEL_FINAL.md](./AUDIT_FONCTIONNEL_FINAL.md): verification finale des features annoncees et de leur etat reel
- [AUDIT_ARCHITECTURE_DATA.md](./AUDIT_ARCHITECTURE_DATA.md): audit factuel de la partie lake, warehouse, datamarts et demo CNI
- [AUDIT_RNCP40875_BLOC1.md](./AUDIT_RNCP40875_BLOC1.md): lecture factuelle du projet face a la grille RNCP Bloc 1
- [RNCP_BLOC1_TRACEABILITE.md](./RNCP_BLOC1_TRACEABILITE.md): matrice de preuves point par point pour la grille RNCP
- [ARCHITECTURE_DECISIONS.md](./ARCHITECTURE_DECISIONS.md): justification des choix techniques et du modele de donnees
- [GOUVERNANCE_ET_PARTIES_PRENANTES.md](./GOUVERNANCE_ET_PARTIES_PRENANTES.md): roles, besoins, arbitrages et contraintes du projet
- [VEILLE_TECHNOLOGIQUE_BLOC1.md](./VEILLE_TECHNOLOGIQUE_BLOC1.md): veille ciblee sur API, lake, streaming et analytics
- [PACK_RENDU.md](./PACK_RENDU.md): contenu et generation du pack de livraison

## Annexes de presentation

- [SOMMAIRE_MEMOIRE_TECHNIQUE.md](./SOMMAIRE_MEMOIRE_TECHNIQUE.md)
- [docs/presentation/PROMPT_PRESENTATION_IA.md](./docs/presentation/PROMPT_PRESENTATION_IA.md)
- [docs/presentation/DISCOURS_ORAL_PROJET.md](./docs/presentation/DISCOURS_ORAL_PROJET.md)
- [docs/presentation/BATTERIE_TESTS_JURY.md](./docs/presentation/BATTERIE_TESTS_JURY.md)

## Services exposes

- API FastAPI: `http://localhost:8000`
- Dashboard web: `http://localhost:7600`
- Kafka UI: `http://localhost:8082`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`
- MinIO console: `http://localhost:9001`

## Resultat attendu avant presentation

- `bash scripts/checklist_and_launch.sh` retourne `34/34 OK`
- `scripts/validate_sujet1.py` retourne `PASS 11/11`
- `scripts/validate_perfect_compliance.py` retourne `PASS 7/7`
- `scripts/data_quality_checks.py` retourne `18/18 PASS`

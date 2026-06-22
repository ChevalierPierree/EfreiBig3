# Batterie De Tests Jury

Ce document regroupe une sequence de tests demonstratifs pour presenter KiVendTout de maniere convaincante.

## 1. Objectif

Montrer que le projet est:
- fonctionnel de bout en bout,
- conforme aux exigences du sujet,
- exploitable dans un contexte professionnel,
- capable de demontrer des cas simples et des cas de charge plus impressionnants.

## 2. Pre-check obligatoire

```bash
cd /Users/jeanmacario/Documents/GitHub/ProjetDataM1JeanPierre
source .venv/bin/activate
bash scripts/checklist_and_launch.sh
```

Resultat attendu:
- `33/33 OK`

Message a dire:
- la stack est disponible,
- l'API, les dashboards et les services data sont accessibles.

## 3. Test 1 - Validation globale du projet

```bash
bash scripts/run_perfect_compliance.sh
```

Resultats attendus:
- `Sujet 1 PASS 11/11`
- `Perfect compliance PASS 6/6`

Message a dire:
- le projet ne repose pas uniquement sur une demo visuelle,
- il dispose d'une validation automatisee couvrant conformite, data lake, micro-batch, charge et resilience.

## 4. Test 2 - Cas metiers unitaires

```bash
bash scripts/test_use_cases.sh
```

Resultats attendus:
- `minor-adult-checkout: passed=True`
- `adult-adult-checkout: passed=True`
- `identity-verification: passed=True`
- `high-risk-alert: passed=True`
- `all_passed=True`

Message a dire:
- les cas metier de base sont rejouables a la demande,
- le controle de majorite, l'identite et la fraude sont relies dans le meme systeme.

## 5. Test 3 - Notifications d'alertes

```bash
bash scripts/test_alert_notifications.sh
```

Resultats attendus:
- `delivery_mode=preview` ou `smtp`
- presence des evenements `new_alert`, `manual`, `decision`

Message a dire:
- le projet sait notifier un operateur,
- en environnement de demo le mode `preview` suffit,
- en environnement reel il suffit de brancher un SMTP.

## 6. Test 4 - Micro-batch exploitable

```bash
bash scripts/run_micro_batch.sh once
```

Resultats attendus:
- une fenetre traitee
- `events > 0`
- `processing_latency_ms` non nul
- `speed_events_per_sec` non nul

Message a dire:
- le systeme ne se limite pas au temps reel,
- il sait aussi consolider des evenements en micro-batch.

## 7. Test 5 - Pipeline Data Lake bronze -> silver -> gold

```bash
bash scripts/snapshot_raw_data_to_minio.sh
./.venv/bin/python scripts/promote_data_lake_layers.py
```

Verification:

```bash
curl -s http://localhost:8000/api/data-lake/status
```

Resultats attendus:
- snapshot bronze present
- `silver` publie
- `gold` publie
- rapport `logs/data_lake_promotion_*.json`

Message a dire:
- les donnees brutes sont historisees,
- le lake produit une couche exploitable pour les indicateurs metier.

## 8. Test 6 - Flux paiements realiste

Commande:

```bash
curl -X POST http://localhost:8000/api/data-factory/payments-live-3m/run \
  -H 'Content-Type: application/json'
```

Verification pendant le run:

```bash
curl -s 'http://localhost:8000/api/payments/stats?window_hours=24'
curl -s http://localhost:8000/api/stats
```

Resultats attendus:
- hausse de `total_payments`
- hausse de `fraudulent_payments`
- variation du `fraud_rate`

Message a dire:
- la fraude n'est pas simulee par un compteur factice,
- elle varie au fil d'un flux de paiements insere dans la base.

## 9. Test 7 - Episode fraude massive sur les commandes

Commande:

```bash
curl -X POST http://localhost:8000/api/data-factory/massive-fraud-orders-3m/run \
  -H 'Content-Type: application/json'
```

Verification pendant 10 secondes:

```bash
curl -s 'http://localhost:8000/api/payments/stats?window_hours=24'
curl -s http://localhost:8000/api/stats
curl -s 'http://localhost:8000/api/checkout/stats?window_hours=24'
```

Ce que l'on doit voir:
- hausse des paiements
- hausse des paiements frauduleux
- hausse des alertes HIGH
- hausse des blocages mineurs 18+

Message a dire:
- ce test montre un vrai comportement de crise,
- les dashboards fraude, paiements et identite convergent sur le meme episode.

## 10. Test 8 - Dashboard live

Pages a ouvrir:
- `http://localhost:7600/index.html`
- `http://localhost:7600/fraud_dashboard.html`
- `http://localhost:7600/fraud_types_dashboard.html`
- `http://localhost:7600/id_cards_dashboard.html`
- `http://localhost:7600/transfer_kpi_dashboard.html`
- `http://localhost:7600/use_cases_dashboard.html`

Ce qu'il faut montrer:
- refresh 1 seconde
- streaming SSE
- evolution des KPI pendant les flux
- bouton reset data
- bouton micro-batch
- use cases pilotables

Message a dire:
- le front n'est pas une maquette statique,
- il est connecte a des flux metier vivants.

## 11. Test 9 - Retour a l'etat initial

```bash
curl -X POST http://localhost:8000/api/system/reset-data \
  -H 'Content-Type: application/json' \
  --data-binary '{"confirm":true,"clear_runtime_artifacts":true,"stop_live_jobs":true}'
```

Verification:

```bash
curl -s http://localhost:8000/api/stats
curl -s 'http://localhost:8000/api/payments/stats?window_hours=24'
```

Resultat attendu:
- retour a une base propre et stable
- fin des jobs live

Message a dire:
- le projet sait revenir a un etat de reference,
- la demonstration est donc rejouable sans pollution cumulative.

## 12. Enchainement recommande pour impressionner

Ordre ideal:
1. `bash scripts/checklist_and_launch.sh`
2. `bash scripts/test_use_cases.sh`
3. `bash scripts/run_micro_batch.sh once`
4. `./.venv/bin/python scripts/promote_data_lake_layers.py`
5. `curl -X POST http://localhost:8000/api/data-factory/payments-live-3m/run -H 'Content-Type: application/json'`
6. ouvrir les dashboards
7. `curl -X POST http://localhost:8000/api/data-factory/massive-fraud-orders-3m/run -H 'Content-Type: application/json'`
8. montrer les KPI qui montent en direct
9. `bash scripts/test_alert_notifications.sh`
10. reset final

## 13. Angle oral recommande

- commencer par le besoin metier, pas par la technique,
- montrer d'abord le cas simple,
- ensuite montrer le cas systemique en temps reel,
- finir par les preuves de validation automatees.

## 14. Points les plus impressionnants

- blocage mineur + produit Adult en temps reel
- verification d'identite hash SHA-256
- variation reelle du `fraud_rate`
- episode fraude massive sur les commandes
- Data Lake bronze -> silver -> gold
- dashboards unifies et live
- batterie de tests automatisee

# Audit Architecture Data

Date: 2026-03-18

## Verdict court

- Data Lake: `oui`
- Data Warehouse: `oui, minimal et exploitable`
- Datamarts: `oui, par domaine`
- Correspondance au sujet: `oui`

## 1. Data Lake

Statut: `present et exploitable`

Preuves:
- MinIO expose dans `docker-compose.yml`
- snapshots bruts via `scripts/snapshot_raw_data_to_minio.sh`
- promotion `bronze -> silver -> gold` via `scripts/promote_data_lake_layers.py`
- endpoint `GET /api/data-lake/status`

Lecture factuelle:
- `bronze` porte l'historisation brute
- `silver` porte une normalisation et un inventaire de jeu de donnees
- `gold` porte des artefacts de consommation et KPI

Conclusion:
- le projet dispose bien d'un Data Lake avec couches exploitees techniquement.

## 2. Data Warehouse

Statut: `present, volontairement minimal`

Preuves:
- script `scripts/build_analytics_warehouse.py`
- schema `analytics` reconstruit dans PostgreSQL
- endpoint `GET /api/analytics/status`
- rapport `logs/analytics_warehouse_report.json`

Modele materialise:
- dimensions:
  - `analytics.dim_date`
  - `analytics.dim_customer`
  - `analytics.dim_product`
- faits:
  - `analytics.fact_order`
  - `analytics.fact_payment`
  - `analytics.fact_identity_verification`
  - `analytics.fact_checkout_attempt`
  - `analytics.fact_fraud_alert`

Conclusion:
- le projet possede maintenant une couche warehouse separee du transactionnel.
- elle n'est pas industrielle au sens grand compte, mais elle existe reellement et reste proportionnee au sujet.

## 3. Datamarts

Statut: `presents et requetables`

Preuves:
- materialized views creees par `scripts/build_analytics_warehouse.py`
- exposees par le statut analytics et le rapport de build

Datamarts presents:
- `analytics.mart_fraud_daily`
- `analytics.mart_identity_controls_daily`
- `analytics.mart_checkout_risk_daily`
- `analytics.mart_product_sales_daily`

Conclusion:
- le projet dispose de datamarts metier lisibles par domaine.

## 4. Correspondance au sujet

### Ce qui correspond bien

- stockage relationnel et exploitation operationnelle
- verification d'identite et controle de majorite
- historisation brute des donnees
- supervision temps reel
- transformation multi-sources
- analytique par faits, dimensions et marts

### Ce qu'il ne faut pas sur-vendre

- un MPP warehouse a grande echelle
- une BI industrielle avec orchestration lourde et gouvernance d'entreprise complete

Conclusion:
- pour le sujet, l'architecture est maintenant coherente de bout en bout:
  - operationnel
  - evenementiel
  - lake
  - analytique
  - supervision

## 5. Section CNI cote client

Statut: `presente`

Preuves:
- page `dashboard/id_cards_dashboard.html`
- endpoint `GET /api/id-cards/{file_name}/analysis`

Contenu de la demonstration:
- lecture de la carte selectionnee
- metadonnees document
- recalcul local de l'age dans le navigateur
- empreinte SHA-256 de l'image cote client
- comparaison avec l'analyse backend
- decision checkout cote client et cote backend

Conclusion:
- la demonstration CNI est concrete et directement montrable en front.

## Conclusion finale

Le projet peut etre presente factuellement comme:
- une plateforme operationnelle de prevention fraude et controle d'identite
- appuyee par un Data Lake MinIO
- completee par un warehouse analytics minimal dans PostgreSQL
- exposee par des datamarts metier et des dashboards temps reel

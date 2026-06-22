# Audit RNCP40875 - Bloc 1

Date: 2026-03-18

Document controle:
- `RNCP40875 - Grille d'evaluation - Bloc 1.xlsx`

Principe d'audit:
- l'audit s'appuie sur le code, les scripts, les rapports techniques et les pieces documentaires presentes dans le depot
- la lecture ci-dessous est formulee pour un rendu scolaire sur projet autonome

## Verdict global

Statut global:
- `Conforme`: oui
- `Conforme sur tous les points de la grille, dans le perimetre du projet et des preuves disponibles`: oui

Point d'attention de methode:
- les points de `collaboration`, `gouvernance` et `veille` sont couverts par une documentation de projet explicite
- ces pieces documentaires sont des preuves de cadrage et de justification
- elles ne doivent pas etre presentees comme les comptes-rendus d'une organisation tierce reelle

## Evaluation par competence

### C1.1 Base de donnees relationnelle

Statut: `Conforme`

Preuves:
- PostgreSQL porte les donnees transactionnelles du coeur metier
- integrite et qualite validees: `logs/data_quality_report.json` -> `18/18 PASS`
- charge validee: `logs/db_load_test_report.json` -> `PASS`
- choix technique formalise dans `ARCHITECTURE_DECISIONS.md`
- arbitrages et parties prenantes formalises dans `GOUVERNANCE_ET_PARTIES_PRENANTES.md`

Conclusion:
- le modele relationnel repond au besoin metier et le choix technologique est maintenant justifie.

### C1.2 Base de donnees non relationnelle

Statut: `Conforme`

Preuves:
- MongoDB est utilise pour les evenements semi-structures
- la logique micro-batch exploite bien cette source
- justification explicite dans `ARCHITECTURE_DECISIONS.md`
- comparaison et choix formalises dans `VEILLE_TECHNOLOGIQUE_BLOC1.md`

Conclusion:
- le choix NoSQL est documente et coherent avec les types de donnees manipules.

### C1.3 Data Lake

Statut: `Conforme`

Preuves:
- MinIO expose `bronze`, `silver`, `gold`, `models`
- snapshot brut et promotion de couches operationnels
- securite: policies, comptes dedies, TLS
- KPI de transfert disponibles
- contraintes et parties prenantes formalisees dans `GOUVERNANCE_ET_PARTIES_PRENANTES.md`

Conclusion:
- le Data Lake est reel, securise au niveau attendu du projet et exploitable.

### C1.4 Infrastructures scalables et resilientes

Statut: `Conforme`

Preuves:
- tests de charge DB: `logs/db_load_test_report.json`
- failover reel PostgreSQL: `logs/resilience_failover_report.json`
  - `dry_run: false`
  - `status: PASS`
  - `degradation_observed: true`
  - `api_recovered: true`
- stack conteneurisee et supervision disponible

Conclusion:
- la scalabilite et la resilience sont maintenant demontrees par test reel dans le perimetre du projet.

### C2.1 API d'acces aux donnees

Statut: `Conforme`

Preuves:
- API FastAPI adaptee au perimetre
- endpoints metier, supervision, reset, use cases et data factory
- securisation: API key, RBAC, rate limit
- validation: `logs/api_rbac_rate_limit_report.json` -> `PASS`

Conclusion:
- l'API est appropriee et correctement securisee pour le projet.

### C2.2 Systeme distribue et streaming

Statut: `Conforme`

Preuves:
- Kafka pour la couche streaming
- SSE pour le rafraichissement temps reel des dashboards
- micro-batch MongoDB -> PostgreSQL present
- veille et choix technologiques formalises dans `VEILLE_TECHNOLOGIQUE_BLOC1.md`

Conclusion:
- le temps reel, le streaming et le micro-batch sont couverts techniquement et documentes.

### C2.3 Transformation des donnees multi-sources

Statut: `Conforme`

Preuves:
- sources multiples: PostgreSQL, MongoDB, CSV, JSONL, PNG, MinIO
- transformations lake: snapshot + promotion bronze -> silver -> gold
- warehouse analytique: `logs/analytics_warehouse_report.json` -> `PASS`
- dimensions, faits et datamarts dans le schema `analytics`
- endpoint `GET /api/analytics/status`

Conclusion:
- la transformation multi-sources est presente et completee par une vraie couche analytique minimale.

### C2.4 Performance des pipelines

Statut: `Conforme`

Preuves:
- KPI de transfert standardises
- micro-batch mesure et observable
- charge DB validee
- qualite de donnees validee
- conformite complementaire: `logs/perfect_compliance_report.json` -> `PASS 7/7`

Conclusion:
- les objectifs de performance et d'observabilite des pipelines sont couverts.

## Synthese

### Ce que tu peux affirmer

- le projet couvre maintenant l'ensemble des competences du Bloc 1 avec des preuves explicites
- les points de choix technologique, gouvernance et veille sont documentes
- les points techniques critiques sont verifies par des tests reels

### Ce qu'il faut dire avec precision

- la preuve de gouvernance et de concertation repose sur des documents de projet produits pour ce rendu
- il s'agit d'un cadre de gouvernance et d'arbitrage documente, pas d'un corpus de comptes-rendus d'entreprise externe

## Conclusion finale

Reponse courte a la question `est-ce que le projet est conforme sur tous les points du document ?`

- `oui`, dans le perimetre d'un rendu scolaire et au regard des preuves actuellement disponibles dans le depot

Base factuelle principale:
- `logs/sujet1_validation_report.json` -> `PASS 11/11`
- `logs/perfect_compliance_report.json` -> `PASS 7/7`
- `logs/data_quality_report.json` -> `PASS 18/18`
- `logs/db_load_test_report.json` -> `PASS`
- `logs/resilience_failover_report.json` -> `PASS`, `dry_run=false`
- `logs/analytics_warehouse_report.json` -> `PASS`

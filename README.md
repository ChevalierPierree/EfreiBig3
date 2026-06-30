# KiVendTout

Plateforme data pour un site e-commerce, construite pour le **Bloc 1 du RNCP40875** (Expert en ingénierie des données).

Le point de départ est un besoin métier simple : **empêcher un mineur d'acheter un produit réservé aux adultes** et **repérer les paiements frauduleux**. Autour de ce besoin, on a monté une chaîne data complète — du stockage transactionnel jusqu'à la supervision en temps réel.

Projet réalisé en binôme : **Pierre Chevalier** et **Jean Macario**.

## Ce que contient le projet

| Brique | Outil | Rôle |
|---|---|---|
| Base relationnelle | PostgreSQL | commandes, paiements, clients, vérifications d'identité |
| Base NoSQL | MongoDB | événements web et traces applicatives (schéma souple) |
| Data Lake | MinIO (S3) | historisation `bronze → silver → gold` |
| Streaming | Kafka + SSE | flux d'événements et d'alertes en direct |
| Traitement temps réel | Flink + micro-batch | détection de fraude au fil de l'eau |
| API | FastAPI | accès aux données, KPI et actions (API key, RBAC, rate limiting) |
| Entrepôt analytique | schéma `analytics` PostgreSQL | dimensions + faits + datamarts |
| Supervision | dashboards web | fraude, typologies, identité, transferts |

Les choix techniques et leurs justifications sont détaillés dans [ARCHITECTURE_DECISIONS.md](./ARCHITECTURE_DECISIONS.md).

## Démarrage rapide

Pré-requis : Docker, Python 3.11+.

```bash
# 1. Environnement Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Lancer toute la stack (Docker + API + dashboards)
./run.sh
```

Le script `run.sh` démarre les services, attend qu'ils répondent et ouvre les dashboards.

Sur Mac M1/M2, utiliser plutôt `requirements-minimal.txt` (versions souples).

## Accès

- Vue d'ensemble : http://localhost:7600/index.html
- Fraude : http://localhost:7600/fraud_dashboard.html
- Typologies de fraude : http://localhost:7600/fraud_types_dashboard.html
- Identité / vérification CNI : http://localhost:7600/id_cards_dashboard.html
- Transferts : http://localhost:7600/transfer_kpi_dashboard.html
- API : http://localhost:8000

## Quelques endpoints utiles

| Endpoint | Donne |
|---|---|
| `GET /api/stats` | KPI fraude globaux |
| `GET /api/payments/stats?window_hours=24` | paiements récents et `fraud_rate` live |
| `GET /api/data-lake/status` | état des couches bronze / silver / gold |
| `GET /api/analytics/status` | état du schéma analytics et des datamarts |
| `GET /api/data-platform/status` | état consolidé de la chaîne data |
| `POST /api/data-factory/payments-live-3m/run` | génère un flux de paiements temps réel |
| `POST /api/data-factory/data-platform-pipeline/run` | rejoue toute la chaîne snapshot → lake → analytics → qualité |

## Indicateurs

- `fraud_rate` = paiements frauduleux / paiements réussis
- `total_alerts` = volume d'alertes (distinct du volume de paiements)
- `customer_alert_coverage` = part des clients couverts par au moins une alerte

## Organisation du dépôt

```
api/         API FastAPI et logique métier
dashboard/   front de supervision (HTML/JS)
database/    schémas SQL PostgreSQL
flink/       jobs de traitement temps réel
scripts/     chargement, pipelines, tests, qualité
config/      contrôle d'accès et notifications
data/        données brutes / transformées (montées localement)
kivendtout_dataset/  jeu de données du projet (CSV / Parquet / JSONL)
```

## Documentation

- [INSTALLATION.md](./INSTALLATION.md) — installation détaillée
- [ARCHITECTURE_DECISIONS.md](./ARCHITECTURE_DECISIONS.md) — justification des choix techniques

---
Données et code à usage pédagogique (RNCP40875 — Efrei).

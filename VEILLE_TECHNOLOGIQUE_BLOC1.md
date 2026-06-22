# Veille Technologique Bloc 1

Date: 2026-03-18

## Objectif

Cette veille ciblee sert a justifier les technologies retenues pour couvrir les besoins du Bloc 1: stockage, API, streaming, Data Lake, transformation et supervision.

## 1. API de donnees

Options comparees:
- FastAPI
- Flask
- Django REST Framework

Critere de choix:
- rapidite de mise en oeuvre
- typage des schemas
- lisibilite pour un projet data
- exposition simple d'endpoints nombreux

Decision:
- FastAPI

Justification:
- schemas Pydantic clairs
- bonne lisibilite pour des endpoints metier et techniques
- adaptation naturelle a une API de demonstration data

## 2. Base relationnelle

Options comparees:
- PostgreSQL
- MySQL
- SQLite

Critere de choix:
- integrite relationnelle
- richesse SQL
- capacite d'agregation
- execution locale fiable

Decision:
- PostgreSQL

Justification:
- SQL riche pour KPI, marts et qualite de donnees
- bon compromis entre realisme professionnel et simplicite locale

## 3. Base non relationnelle

Options comparees:
- MongoDB
- PostgreSQL JSONB uniquement
- Elasticsearch

Critere de choix:
- souplesse de schema
- ingestion d'evenements JSON
- separation claire des usages

Decision:
- MongoDB

Justification:
- modele adapte aux evenements semi-structures
- reduit le couplage avec le transactionnel

## 4. Streaming et temps reel

Options comparees:
- Kafka + SSE
- Kafka + WebSocket
- RabbitMQ + polling

Critere de choix:
- fidelite a un usage data/streaming
- simplicite front
- faible latence observable
- maintenance raisonnable

Decision:
- Kafka pour le backbone streaming
- SSE pour la diffusion vers les dashboards

Justification:
- Kafka repond au besoin de systeme distribue
- SSE reste plus simple qu'un WebSocket pour des dashboards majoritairement en lecture

## 5. Data Lake

Options comparees:
- MinIO
- stockage local sur filesystem
- S3 cloud

Critere de choix:
- compatibilite S3
- execution locale
- securisation minimale possible
- cout et dependances nulles en soutenance locale

Decision:
- MinIO

Justification:
- bucketisation simple `bronze`, `silver`, `gold`, `models`
- bonne demonstration des concepts lake sans dependance externe

## 6. Entrepot analytique

Options comparees:
- schema analytics dans PostgreSQL
- DuckDB
- ClickHouse

Critere de choix:
- limiter la complexite de la stack
- materialiser rapidement dimensions, faits et datamarts
- garder une execution locale reproductible

Decision:
- schema `analytics` dans PostgreSQL

Justification:
- solution la plus proportionnee au sujet
- permet de prouver un vrai modele analytique minimal sans brique supplementaire lourde

## 7. Monitoring et observabilite

Options comparees:
- Prometheus + Grafana
- logs seuls
- outils SaaS externes

Critere de choix:
- visibilite locale
- standard de marche
- independance externe

Decision:
- Prometheus + Grafana

Justification:
- combinaison standard et lisible pour un projet data technique

## Conclusion

La veille ne vise pas a montrer une etude exhaustive du marche, mais une selection argumentee des briques les plus adaptees au perimetre du projet.

Le principe retenu a ete constant:
- choisir des outils suffisamment professionnels pour etre credibles
- rester proportionne au sujet
- garder une execution locale simple et demonstrable

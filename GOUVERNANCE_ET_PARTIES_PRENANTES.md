# Gouvernance Et Parties Prenantes

Date: 2026-03-18

## Portee du document

Ce document formalise la gouvernance de projet utilisee pour cadrer les choix techniques et fonctionnels de KiVendTout.

Il s'agit d'une gouvernance de projet et d'un cadre de decision documente pour un rendu scolaire. Ce document ne pretend pas etre le compte-rendu d'un comite de gouvernance externe reel.

## Parties prenantes retenues

### Responsable e-commerce

Attentes:
- vendre sans friction excessive
- bloquer les paniers non conformes
- conserver une experience fluide pour les majeurs

Impacts sur le projet:
- blocage explicite des paniers `Adult` si client mineur
- acceptation rapide des paniers legitimes
- dashboards lisibles par un profil operationnel

### Analyste fraude

Attentes:
- disposer d'alertes priorisees
- comprendre pourquoi une alerte remonte
- notifier une decision ou une escalation

Impacts sur le projet:
- backlog fraude
- typologies interpretees
- actions `APPROVE`, `BLOCK`, `INVESTIGATE`
- notifications email et historique

### Architecte data

Attentes:
- separer transactionnel, evenementiel, lake et analytique
- garantir la qualite minimale et la tracabilite
- rendre les flux explicables

Impacts sur le projet:
- PostgreSQL pour le transactionnel
- MongoDB pour les evenements
- MinIO pour le lake
- schema `analytics` et datamarts pour l'analytique
- rapports de qualite de donnees

### Architecte infrastructures

Attentes:
- stack executable et maintenable localement
- capacite de supervision et tests de recuperation
- services isoles par conteneur

Impacts sur le projet:
- `docker compose`
- tests de charge et de resilience
- monitoring Prometheus/Grafana

### Gouvernance de la donnee / conformite

Attentes:
- limiter l'exposition des donnees sensibles
- historiser sans exposer inutilement les donnees personnelles
- securiser les acces au lake

Impacts sur le projet:
- hash `SHA-256` du `document_number`
- API key, RBAC, quotas
- policies MinIO et TLS
- CNI synthetiques au lieu de documents reels

## Arbitrages documentes

### Arbitrage 1: experience utilisateur vs controle fort

Decision:
- controler l'age au checkout seulement quand un produit `Adult` est present
- ne pas complexifier inutilement les paniers standards

### Arbitrage 2: temps reel visible vs complexite front

Decision:
- SSE cote dashboards plutot que WebSocket
- objectif: lecture simple, latence faible, maintenance limitee

### Arbitrage 3: architecture analytique vs lourdeur de stack

Decision:
- ajouter un schema `analytics` et des datamarts dans PostgreSQL
- ne pas introduire un moteur warehouse supplementaire pour un perimetre scolaire

### Arbitrage 4: demonstration concrete vs donnees reelles sensibles

Decision:
- utiliser des CNI synthetiques et des donnees de demo
- permettre des episodes live et reset complet pour rejouabilite

## Traceabilite besoin -> implementation

- Besoin `bloquer un mineur sur Adult` -> `POST /api/orders/checkout` + `checkout_attempts` + `identity_verifications`
- Besoin `analyser la fraude` -> `fraud_alerts`, dashboards fraude et typologies
- Besoin `historiser` -> MinIO `bronze -> silver -> gold`
- Besoin `industrialiser l'analyse` -> schema `analytics` et datamarts
- Besoin `superviser` -> dashboards live, KPI transfert, tests de presentation

## Conclusion

La gouvernance du projet est suffisamment explicite pour relier:
- les besoins metier
- les contraintes de securite
- les choix techniques
- les arbitrages de conception

Dans le cadre d'un rendu scolaire, ce document fournit une trace defendable de la concertation fonctionnelle et technique qui a guide l'architecture.

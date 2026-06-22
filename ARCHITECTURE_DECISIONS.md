# Architecture Decisions

Date: 2026-03-18

## Objectif

Ce document formalise les choix techniques retenus pour le projet KiVendTout, au regard du besoin metier initial: empecher un mineur d'acheter un produit reserve aux adultes, tout en rendant les donnees accessibles, tracables et exploitables.

## Contraintes de depart

- exposer une API de checkout simple a tester et suffisamment scalable pour une demonstration
- gerer des donnees transactionnelles coherentes
- absorber des evenements semi-structures et du temps reel
- historiser des donnees brutes
- produire des indicateurs de supervision et de fraude
- rester executable localement sur une machine de developpement

## Choix 1: PostgreSQL pour le store relationnel

Besoin couvert:
- commandes, lignes de commande, paiements, clients, verifications d'identite, tentatives de checkout

Pourquoi PostgreSQL:
- integrite relationnelle forte et SQL riche
- bon support des jointures et agregations pour les KPI metier
- technologie stable, portable et adaptee au sujet
- permet de porter a la fois l'operationnel et une couche analytique minimale via un schema dedie

Alternatives ecartees:
- SQLite: trop limite pour la charge, la concurrence et l'integration multi-services
- MySQL: viable, mais PostgreSQL offre ici plus de confort analytique et de souplesse SQL

## Choix 2: MongoDB pour les evenements semi-structures

Besoin couvert:
- sessions, evenements web, traces applicatives et donnees event-driven a schema plus souple

Pourquoi MongoDB:
- flexible sur les structures d'evenements
- bonne adequation a l'ingestion rapide de donnees JSON
- permet de separer le transactionnel strict du flux evenementiel

Alternatives ecartees:
- stocker tous les evenements dans PostgreSQL aurait augmente le couplage et la complexite du schema
- Elasticsearch seul n'etait pas necessaire pour le perimetre du projet

## Choix 3: MinIO comme Data Lake

Besoin couvert:
- historiser les donnees brutes et publier des couches de consommation

Pourquoi MinIO:
- compatibilite S3, simple a executer localement
- buckets distincts `bronze`, `silver`, `gold`, `models`
- policies de securite et TLS possibles sans dependance cloud externe

Usage retenu:
- `bronze`: snapshots bruts horodates
- `silver`: artefacts normalises et manifestes de jeu de donnees
- `gold`: KPI et artefacts de consommation

## Choix 4: Kafka + SSE pour le temps reel

Besoin couvert:
- demonstrer un streaming visible dans les dashboards et un flux d'alertes/commandes en direct

Pourquoi cette combinaison:
- Kafka porte la logique distribuee et les evenements
- SSE permet un front web simple, lisible et peu couplant pour des dashboards de supervision
- le micro-batch complete le temps reel avec une logique de fenetre exploitable

Alternatives ecartees:
- WebSocket: plus complexe a maintenir ici pour un besoin surtout unidirectionnel
- polling pur: plus simple mais moins fidele a un usage temps reel professionnel

## Choix 5: Schema analytics et datamarts dans PostgreSQL

Besoin couvert:
- transformer les donnees multi-sources en vues analytiques exploitables
- repondre a l'attente de structuration analytique au-dela du seul Data Lake

Decision:
- creation d'un schema `analytics` separe du transactionnel
- dimensions `date`, `customer`, `product`
- faits `order`, `payment`, `identity_verification`, `checkout_attempt`, `fraud_alert`
- datamarts materialises par domaine

Pourquoi ce choix:
- reponse rapide et robuste au besoin d'entrepot analytique minimal
- limite le nombre de briques a exploiter localement
- permet de prouver un modele analytique lisible sans introduire une stack warehouse lourde

Compromis:
- ce n'est pas un SI BI industriel complet
- c'est un entrepot analytique minimal, centre sur les besoins du sujet

## Choix 6: FastAPI pour l'API

Besoin couvert:
- exposer simplement les donnees, les use cases, les KPI et les actions de demonstration

Pourquoi FastAPI:
- typage et schemas clairs
- rapidite de mise en oeuvre
- documentation et structure adaptees aux API data
- bonne lisibilite du code pour un rendu scolaire

## Choix 7: securite pragmatique du perimetre

Mesures retenues:
- API key optionnelle mais supportee
- RBAC
- rate limiting
- hash `SHA-256` du `document_number`
- policies MinIO et TLS

Justification:
- le projet doit montrer des pratiques de securisation concretes, sans pretendre a un systeme IAM complet d'entreprise

## Choix 8: orchestration consolidee de la plateforme data

Besoin couvert:
- disposer d'un point de controle unique pour la chaine `bronze -> silver -> gold -> analytics`
- verifier qu'un jeu de donnees publie reste coherent entre le store operationnel, le lake et le schema analytique

Decision:
- ajout d'un pipeline consolide `scripts/run_data_platform_pipeline.py`
- ajout d'un statut agrégé `GET /api/data-platform/status`
- renforcement du rapport warehouse avec controles de coherence et de fraicheur

Pourquoi ce choix:
- un projet data solide ne doit pas seulement "avoir" un lake et un warehouse
- il doit aussi exposer leur etat, leur ordre d'execution et la coherence des couches
- ce niveau de pilotage renforce la valeur technique du projet sans introduire un orchestrateur externe lourd

## Decision globale

L'architecture retenue privilegie:
- la lisibilite
- la tracabilite
- la separation des usages operationnels, evenementiels, lake et analytiques
- une execution locale reproductible

Cette architecture est volontairement plus simple qu'une plateforme industrielle complete, mais elle couvre de maniere coherente le perimetre technique attendu par le sujet.

# Discours Oral Projet

## Objectif

Ce document propose un discours oral de 8 a 10 minutes, directement aligné avec l'etat final du projet KiVendTout.

Le ton vise un rendu:
- professionnel,
- clair,
- sobre,
- oriente besoin metier, architecture, preuve et maitrise.

## Version 8 a 10 minutes

### 1. Introduction

Bonjour.

Je vais vous presenter KiVendTout, une plateforme data appliquee a un contexte e-commerce, avec un objectif simple: reduire le risque de fraude, renforcer le controle d'identite, et fournir une supervision exploitable en temps reel.

Le projet a ete pense comme un dispositif operationnel, pas seulement comme une demonstration technique.

L'idee est de traiter un probleme concret:
- un site e-commerce recoit des commandes, des paiements, des evenements utilisateurs,
- certaines commandes doivent etre bloquees, par exemple lorsqu'un mineur tente d'acheter un produit reserve aux adultes,
- certaines situations doivent faire remonter une alerte fraude,
- et les equipes doivent pouvoir suivre cela dans des dashboards lisibles, avec des flux live et des indicateurs fiables.

### 2. Besoin metier

Le besoin de depart etait double.

D'abord, il fallait disposer d'une API de commande scalable, capable de verifier l'age d'un client a partir d'une piece d'identite synthetique, et de bloquer automatiquement les achats de produits `Adult` pour les mineurs.

Ensuite, il fallait aller plus loin que ce seul garde-fou et proposer une vraie chaine data:
- collecte d'evenements,
- stockage multi-sources,
- detection de fraude,
- historisation des donnees brutes,
- consolidation en micro-batch,
- et visualisation temps reel.

Autrement dit, le projet ne devait pas seulement “faire un blocage”.
Il devait montrer comment une plateforme data peut relier:
- l'operationnel,
- la gouvernance de la donnee,
- la supervision,
- et la conformite.

### 3. Perimetre de la solution

La solution que j'ai realisee s'articule autour de plusieurs briques.

Premiere brique: une API FastAPI qui expose les cas metier principaux:
- consultation du catalogue,
- verification d'identite,
- checkout,
- consultation des alertes,
- KPI fraude, paiements, identite et transferts.

Deuxieme brique: une couche de stockage hybride:
- PostgreSQL pour les donnees relationnelles et transactionnelles,
- MongoDB pour les evenements semi-structures,
- MinIO comme Data Lake, organise en `bronze`, `silver` et `gold`.

Troisieme brique: la supervision:
- plusieurs dashboards web,
- un flux SSE en temps reel,
- une mise a jour chaque seconde,
- et une vue principale qui permet de piloter la demonstration.

Quatrieme brique: les preuves et la validation:
- tests de conformite,
- tests de qualite des donnees,
- tests RBAC et quotas,
- tests de charge base,
- tests de resilience,
- use cases rejouables,
- et un reset pour revenir a l'etat initial.

### 4. Fonctionnement metier cle

Le premier point fort du projet est le controle d'age sur le checkout.

Le principe est le suivant:
- un client soumet une commande,
- l'API recupere la date de naissance a partir de la carte d'identite synthetique,
- l'age est calcule a la date du jour,
- si le panier contient un produit categorie `Adult` et que le client a moins de 18 ans, la commande est refusee en HTTP 403.

Ce point est important parce qu'il traduit une regle metier tres concrete en garde-fou applicatif.

Le deuxieme point fort est la verification d'identite.

Lorsqu'une verification est enregistree, le numero de document n'est pas stocke en clair.
Il est hache en `SHA-256`.

Cela permet de conserver une preuve exploitable tout en respectant un principe minimal de protection de la donnee sensible.

Le troisieme point fort est la fraude.

Le projet genere et centralise des alertes avec:
- niveau de severite,
- motifs de fraude,
- file d'attente,
- decisions analyste,
- et circuit de notification.

Il y a donc une vraie logique de traitement et pas seulement un score opaque.

### 5. Architecture data

Sur le plan technique, j'ai retenu une architecture simple mais representative d'un environnement professionnel.

PostgreSQL porte les donnees structurées:
- clients,
- produits,
- commandes,
- paiements,
- traces de verification,
- alertes,
- tentatives de checkout,
- metriques micro-batch.

MongoDB stocke les evenements utilisateurs, qui servent a alimenter les traitements plus orientés usage et comportement.

MinIO joue le role de Data Lake.

La logique est la suivante:
- `bronze`: conservation brute et historisee des donnees,
- `silver`: donnees normalisees,
- `gold`: jeux de donnees directement exploitables pour les KPI et la lecture metier.

Ce point est important car il montre que le projet ne se limite pas a une API transactionnelle.
Il inclut aussi une logique de centralisation et de transformation des donnees.

### 6. Temps reel et exploitation

Le projet embarque egalement une dimension temps reel.

Les dashboards sont relies a l'API via un flux SSE.
Ils se rafraichissent toutes les secondes.

Cela permet de suivre:
- l'evolution des alertes,
- les checkouts bloques,
- les verifications d'identite,
- les paiements,
- les KPI de transfert.

J'ai aussi ajoute une fabrique de donnees et une console de demonstration directement sur le dashboard principal.

En pratique, cela permet de lancer:
- des cas metier simples,
- des flux paiements,
- un episode de fraude massive sur les commandes,
- et des tests de presentation,
directement depuis l'interface.

L'interet est de rendre la demonstration concrete, fluide et pilotable sans dependre uniquement du terminal.

### 7. Micro-batch et Data Lake

Au-dela du live, le projet integre un flux micro-batch.

L'objectif est de montrer que la plateforme sait aussi consolider des evenements par fenetre de traitement, avec des metriques exploitables comme:
- le nombre d'evenements traites,
- la latence,
- le debit.

Le Data Lake est egalement verifie de bout en bout:
- snapshot brut dans `bronze`,
- promotion vers `silver`,
- publication de jeux `gold`.

Cette partie repond a une attente importante du sujet: montrer la maitrise des transferts, de l'historisation et de l'exploitation de la donnee, et pas seulement de l'interface.

### 8. Resultats et preuves

J'ai valide le projet par plusieurs niveaux de controle.

La checklist plateforme est au vert.

Le sujet 1 est valide a `11 sur 11`.

La conformite complementaire est validee a `6 sur 6`.

La qualite des donnees est validee a `18 sur 18`.

Les tests metier rejouent correctement:
- le blocage mineur sur produit `Adult`,
- la commande majeur acceptee,
- la verification d'identite,
- l'alerte haute severite.

J'ai egalement verifie les flux live.

Par exemple, lors d'un flux paiements, les paiements augmentent, les paiements frauduleux augmentent, et le `fraud_rate` varie reellement.

Lors d'un episode de fraude massive, on observe en meme temps:
- une hausse des paiements,
- une hausse des paiements frauduleux,
- une hausse des alertes HIGH,
- une hausse des blocages mineurs sur produits restreints.

Ce point est important, parce qu'il montre une convergence entre plusieurs vues du systeme:
- fraude,
- paiements,
- identite,
- typologies.

### 9. Qualite, securite et robustesse

Le projet integre aussi des mecanismes de securisation et de robustesse.

On retrouve notamment:
- cle API optionnelle,
- RBAC,
- quotas et rate limiting,
- policies MinIO,
- generation de certificats TLS,
- tests de charge base,
- tests de resilience en mode dry-run,
- et un mecanisme de reset complet.

Le reset est important pour un usage de demonstration et de recette.
Il permet de revenir a un etat initial propre, sans pollution cumulative entre deux passages.

### 10. Limites et suite logique

Le projet est fonctionnel et coherent avec le sujet, mais il existe naturellement des pistes d'amelioration.

La principale limite actuelle est que la notification email est en mode `preview` tant qu'un SMTP reel n'est pas branche.

En contexte production, les suites naturelles seraient:
- brancher un SMTP reel,
- renforcer encore le case management analyste,
- ajouter un cycle paiement complet avec chargeback,
- et aller plus loin sur le monitoring des modeles et la gouvernance.

### 11. Conclusion

Pour conclure, KiVendTout repond au sujet avec une logique complete:
- une API metier,
- un controle d'identite,
- une detection de fraude,
- une supervision temps reel,
- un Data Lake exploitable,
- des pipelines batch et live,
- et des preuves de validation automatisées.

Le projet est donc a la fois:
- demonstrable,
- verifiable,
- et structure comme une vraie plateforme data orientee usage.

Merci.

## Version courte 4 a 5 minutes

Bonjour.

Je vais vous presenter KiVendTout, une plateforme data pour e-commerce qui combine controle d'identite, prevention de fraude, supervision temps reel et historisation de donnees.

Le besoin initial etait tres concret: empecher un mineur d'acheter un produit reserve aux adultes, via une API de checkout scalable capable de calculer l'age a partir d'une carte d'identite synthetique.

J'ai etendu ce besoin vers une plateforme plus complete.

Aujourd'hui, le projet inclut:
- FastAPI pour l'API,
- PostgreSQL pour les donnees transactionnelles,
- MongoDB pour les evenements,
- MinIO comme Data Lake `bronze -> silver -> gold`,
- et plusieurs dashboards relies a un flux SSE mis a jour chaque seconde.

Sur le plan metier, on peut demonstrer:
- un checkout mineur bloque en `403`,
- un checkout majeur accepte,
- une verification d'identite avec hash `SHA-256`,
- une alerte fraude haute severite,
- un flux paiements qui fait varier reellement le `fraud_rate`,
- et un episode de fraude massive qui fait monter en meme temps paiements, alertes et blocages mineurs.

Le projet ne repose pas seulement sur une belle interface.
Il est aussi valide par des preuves techniques:
- checklist plateforme au vert,
- sujet 1 valide a `11 sur 11`,
- conformite complementaire validee,
- qualite des donnees validee,
- tests de charge et de resilience.

Enfin, un reset complet permet de revenir a un etat initial propre, ce qui rend la demonstration rejouable.

En synthese, le projet repond au besoin metier initial tout en montrant une vraie chaine data, du checkout jusqu'a la supervision et a l'historisation.

Merci.

## Conseils d'usage

- parler lentement sur les trois premiers blocs: besoin, perimetre, architecture
- accelerer legerement sur la partie stack technique
- ralentir a nouveau sur les preuves et les resultats
- terminer avec une conclusion simple, sans sur-vendre

## Formulation a privilegier

- "voici la regle metier appliquee"
- "voici la preuve observable"
- "voici ce que cela change pour l'exploitation"
- "le point important ici est..."

## Formulation a eviter

- "j'ai tout fait"
- "c'est revolutionnaire"
- "c'est parfait"
- "l'IA a..."


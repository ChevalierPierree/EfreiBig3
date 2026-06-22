# Prompt Presentation IA

Le texte ci-dessous est prevu pour etre copie tel quel dans une IA generative de presentation.

```text
Tu es un expert en storytelling technique et en creation de presentations PowerPoint professionnelles.

Je veux que tu me construises une presentation complete, en francais, a partir du projet suivant:

Nom du projet:
KiVendTout

Nature du projet:
Plateforme data pour e-commerce combinant:
- detection de fraude,
- verification d'identite,
- blocage des commandes de produits Adult pour les mineurs,
- supervision temps reel,
- pipeline Data Lake bronze -> silver -> gold,
- flux micro-batch et dashboards de pilotage.

Contexte:
Le projet vise a rendre concret un dispositif de lutte contre la fraude dans un environnement e-commerce. Il doit etre presente comme un vrai projet professionnel, pas comme un prototype scolaire. Le ton doit etre sobre, corporate, clair, rigoureux et credible.

Stack technique:
- FastAPI
- PostgreSQL
- MongoDB
- Kafka
- MinIO
- Dashboards web
- scripts de test, validation, charge et resilience

Fonctionnalites clefs:
- API de checkout avec controle d'age
- verification d'identite avec hash SHA-256 du document
- generation d'alertes fraude
- notifications d'alertes
- streaming temps reel vers les dashboards
- flux paiements realiste faisant varier le fraud_rate
- episode de fraude massive sur les commandes pendant 3 minutes
- pipeline Data Lake minimal exploitable dans MinIO:
  - bronze: donnees brutes historisees
  - silver: donnees normalisees
  - gold: KPI metier exploitables

Preuves de validation disponibles:
- checklist globale: 33/33 OK
- validation sujet 1: PASS 11/11
- validation conformite complementaire: PASS 6/6
- qualite des donnees: PASS 18/18

Je veux une presentation PowerPoint de 12 a 15 slides maximum.

Contraintes de forme:
- style tres professionnel, type grand groupe / defense / industrie critique
- design sobre, premium, lisible
- peu de texte par slide
- pas de ton marketing excessif
- pas de vocabulaire scolaire
- pas de formulations qui sonnent "IA"
- titres courts et impactants
- chaque slide doit servir un message clair

Je veux que tu produises la presentation au format suivant:

Pour chaque slide:
1. Numero de slide
2. Titre
3. Objectif de la slide
4. Contenu exact a afficher sur la slide
5. Suggestion de visuel ou schema
6. Message oral a dire pendant la presentation

Structure attendue:
- slide 1: titre du projet et promesse
- slide 2: contexte et probleme metier
- slide 3: objectifs et perimetre
- slide 4: architecture globale
- slide 5: parcours checkout + verification d'identite
- slide 6: detection de fraude et alertes
- slide 7: streaming temps reel et dashboards
- slide 8: Data Lake bronze -> silver -> gold
- slide 9: KPI et resultats mesurables
- slide 10: use cases concrets, dont commande mineur et fraude massive
- slide 11: securite, conformite et robustesse
- slide 12: conclusion et perspectives

Si necessaire, ajoute 1 a 3 slides supplementaires maximum pour:
- pipeline micro-batch,
- episode fraude commandes 3 minutes,
- feuille de route.

Contenus qui doivent absolument apparaitre:
- blocage mineur + produit Adult
- verification d'identite
- fraud_rate calcule sur les paiements reussis
- flux paiements temps reel
- episode fraude commandes massif
- Data Lake MinIO bronze/silver/gold
- dashboards de supervision
- validation technique du projet

Je veux aussi:
- une recommandation de palette de couleurs corporate
- une recommandation de police
- une recommandation de disposition generale
- une derniere section "conseils de presentation orale"

Important:
- n'invente pas des technologies non presentes
- reste coherent avec un projet data et fraude
- fais une presentation utilisable directement pour realiser un PowerPoint
- privilegie des formulations simples, solides et professionnelles
```

## Variante plus courte

Si l'outil est limite en taille de prompt, utiliser cette version:

```text
Construis une presentation PowerPoint professionnelle en francais sur le projet KiVendTout, plateforme data e-commerce de detection de fraude et verification d'identite.

Le projet comprend:
- FastAPI, PostgreSQL, MongoDB, Kafka, MinIO
- checkout avec blocage mineur + produit Adult
- verification d'identite avec hash SHA-256
- alertes fraude
- dashboards temps reel
- flux paiements realiste faisant varier le fraud_rate
- episode fraude commandes massif pendant 3 minutes
- Data Lake bronze -> silver -> gold

Je veux 12 a 15 slides maximum, ton corporate, sobre, credibilite projet reel.

Pour chaque slide, donne:
1. titre
2. objectif
3. contenu exact
4. visuel conseille
5. notes orales

Fais apparaitre:
- probleme metier
- architecture
- logique fraude
- streaming temps reel
- Data Lake
- KPI
- use cases
- securite et conformite
- conclusion et perspectives

Preuves:
- checklist 33/33 OK
- sujet 1 PASS 11/11
- conformite PASS 6/6
- qualite des donnees PASS 18/18
```

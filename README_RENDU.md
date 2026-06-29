# Projet Data Science - Retards de vols US

Livrable final prêt à rendre pour le syllabus **RNCP40875 - Projet Data Science**.

Ce dossier a été construit à partir de `CONSIGNEDSS.ipynb`, du syllabus RNCP40875 et des données `flights.csv`, `airlines.csv`, `airports.csv`.

## Fichiers principaux

- `CONSIGNEDSS.ipynb` : notebook guidé initial rempli, exécuté et finalisé.
- `flights_delay.ipynb` : même notebook final sous le nom métier du projet.
- `CONSIGNEDSS_original_guidé.ipynb` : version consigne initiale conservée comme référence.
- `RNCP40875 - Syllabus - Projet Data Science.pdf` : syllabus utilisé pour contrôler les attendus.
- `dashboard.py` : dashboard Streamlit professionnel structuré en 3 pages métier.
- `rapport.md` : rapport projet aligné avec les compétences C3.1 à C4.3.
- `requirements.txt` : dépendances Python.
- `launch_dashboard.sh` / `stop_dashboard.sh` : scripts de lancement et arrêt du dashboard.
- `dashboard_preview.html` : aperçu HTML de secours.

## Données et sorties

- `flights_delay/` : données brutes nécessaires pour relancer le notebook :
  - `flights.csv`
  - `airlines.csv`
  - `airports.csv`
- `outputs/flights_dashboard.csv` : données préparées pour Streamlit.
- `outputs/aggregates/` : agrégats mois, heure, compagnie, aéroport.
- `outputs/model_comparison.csv` : comparaison des modèles.
- `outputs/model_artifacts/` : matrices de confusion, métriques multi-seuils, classification reports et modèles `.joblib`.
- `outputs/consolidated_dashboards/` : consolidation des dashboards issus des différents notebooks disponibles.
- `scripts/` : scripts reproductibles pour régénérer les matrices modèles et les consolidations dashboard.

## Lancer le dashboard

Depuis ce dossier :

```bash
./launch_dashboard.sh
```

URL locale :

```text
http://127.0.0.1:8501
```

Arrêt :

```bash
./stop_dashboard.sh
```

Le script crée automatiquement un environnement `.dashboard_env` local si Streamlit n'est pas encore installé.

## Structure du dashboard

Le front Streamlit est organisé en trois pages :

- **Page 1 - Vue exécutive** : KPI globaux, jauge de ponctualité, donut retards/vols à l'heure, tendance mensuelle, mois critiques, compagnies/aéroports/routes à risque et synthèse modèle.
- **Page 2 - Analyse opérationnelle** : diagnostic par temporalité, mois les plus en retard, compagnie, ville, aéroport, route et table de contrôle filtrable.
- **Page 3 - Recommandations** : simulateur prédictif de départ, playbooks métier, recommandations priorisées, matrice impact/effort, feuille de route 30/60/90 jours, décisions permises, modèles, matrices de confusion et dashboards consolidés des notebooks.

### Visuels consolidés ajoutés

- **Page 1** : jauge du taux de retard avec seuil de vigilance, donut `à l'heure / retardé`, graphique des métriques modèles, bar chart des mois les plus critiques, contribution des compagnies et routes au volume de retards.
- **Page 3** : simulateur mois + compagnie + aéroport de départ + aéroport d'arrivée, score du modèle fine-tuné, scénarios sans vacances vs vacances, actions recommandées pour le départ simulé, matrice impact/effort, timeline de déploiement IA, comparaison modèle par métrique et mesures par filtres métier.

### Simulateur de départ

La Page 3 permet d'imaginer un départ en choisissant :

- un mois ;
- une compagnie ;
- un aéroport de départ ;
- un aéroport d'arrivée ;
- une heure de départ optionnelle ;
- un type de jour optionnel : semaine ou week-end.

Le dashboard compare ensuite le scénario avec plusieurs références historiques : scénario complet, mois + compagnie + route, compagnie + route, mois + route, route, compagnie, départ, arrivée, mois et historique global. Il affiche aussi un **score de prédiction fine-tuné**, un seuil d'alerte, une décision modèle et une comparaison **mois sans vacances** vs **mois vacances / forte demande**.

La mesure du modèle sur le filtre exact utilise uniquement le jeu de test holdout. Elle calcule, quand le volume est suffisant : accuracy, balanced accuracy, precision, recall, F1 et ROC-AUC sur le sous-ensemble `mois + compagnie + aéroport départ + aéroport arrivée`.

### KPIs retenus

- **Vols analysés** : contrôle le volume et la fiabilité des comparaisons.
- **Taux de retard** : mesure centrale de ponctualité, seuil métier `ARRIVAL_DELAY > 15`.
- **Vols retardés** : quantifie le volume d'incidents dans la sélection.
- **Retard moyen arrivée** : mesure l'impact client.
- **Retard médian arrivée** : limite l'effet des retards extrêmes.
- **Retard moyen départ** : indicateur actionnable côté opérations sol et rotation.
- **Recall du modèle retard** : limite les faux négatifs dans une logique d'alerte.

### Modèles réentraînés

Le modèle a été réentraîné sur `outputs/flights_dashboard.csv` avec **800 000 vols** :

- train : **480 000 vols**
- validation : **160 000 vols**
- test : **160 000 vols**
- taux de retard : **17,9 %**

Deux contextes sont livrés :

| Contexte | Usage | Meilleur modèle | ROC-AUC | Precision | Recall | F1 |
|---|---|---|---:|---:|---:|---:|
| `preflight` | prédiction avant départ, sans fuite de données | HistGradientBoosting | 0,707 | 0,311 | 0,578 | 0,404 |
| `operational_live` | prédiction après observation du retard au départ | HistGradientBoosting | 0,941 | 0,865 | 0,752 | 0,805 |
| `segment_finetuned_preflight` | prédiction filtrable mois/compagnie/départ/arrivée | HistGradientBoosting fine-tuné | 0,711 | 0,310 | 0,587 | 0,405 |

Conclusion : le modèle `operational_live` est le plus précis, mais il ne doit pas être présenté comme un modèle avant départ car il utilise `DEPARTURE_DELAY`. Le modèle `preflight` est le modèle correct pour une alerte avant départ programmé.
Le modèle `segment_finetuned_preflight` est celui utilisé dans le simulateur : il est entraîné et évalué pour les filtres mois, compagnie, aéroport de départ et aéroport d'arrivée, avec une mesure spécifique des scénarios `normal_sans_vacances` et `incident_vacances`.

Artefacts associés :

- `outputs/model_artifacts/segment_finetuned_preflight_model.joblib`
- `outputs/model_artifacts/segment_finetuned_metadata.json`
- `outputs/model_artifacts/segment_finetuned_tuning_results.csv`
- `outputs/model_artifacts/segment_finetuned_test_predictions.csv`
- `outputs/model_artifacts/segment_finetuned_filter_metrics.csv`
- `outputs/model_artifacts/segment_finetuned_scenario_metrics.csv`

### Filtres ajoutés

- Page de navigation.
- Mois.
- Jour de semaine.
- Compagnie.
- Heure de départ programmée.
- Ville de départ.
- Aéroport de départ.
- Ville d'arrivée.
- Aéroport d'arrivée.
- Vols retardés uniquement.
- Volume minimum des segments en analyse opérationnelle.
- Recherche texte, tri et choix des colonnes dans la table de contrôle.

Les filtres **Aéroport de départ** et **Aéroport d'arrivée** sont dépendants des filtres ville : sélectionner une ville réduit automatiquement la liste des aéroports rattachés.

### Décisions permises

- Renforcer les équipes sol sur les périodes et heures à risque.
- Identifier les mois les plus critiques et exposer les compagnies, villes, aéroports et destinations associées.
- Prioriser les hubs, routes et compagnies à auditer.
- Ajuster les marges de rotation en fin de journée.
- Déclencher des communications passagers sur les segments à risque.
- Simuler un départ et décider s'il faut activer pré-alerte, renfort escale, surveillance active ou traitement nominal.
- Choisir le modèle et le seuil d'alerte en fonction du recall, du F1 et des faux négatifs.

## Ouvrir ou relancer le notebook

Installation manuelle :

```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
jupyter notebook CONSIGNEDSS.ipynb
```

Relance complète :

```bash
jupyter nbconvert --to notebook --execute --inplace CONSIGNEDSS.ipynb --ExecutePreprocessor.timeout=1800
```

## Régénérer les sorties complémentaires

```bash
python scripts/build_model_matrices.py
python scripts/train_segment_finetuned_model.py
python scripts/consolidate_dashboard_sources.py
```

## Validation réalisée

- `CONSIGNEDSS.ipynb` exécuté entièrement avec `nbconvert`.
- `CONSIGNEDSS.ipynb` et `flights_delay.ipynb` : 24 cellules code exécutées, 0 cellule en erreur.
- Dashboard Streamlit testé sans exception avec `streamlit.testing`.
- Dashboard Streamlit démarré en test HTTP : réponse `HTTP 200 OK`.
- Scripts Python contrôlés avec `py_compile`.
- Modèle segmenté fine-tuné entraîné sur 800 000 vols, avec métriques par filtres et scénarios.
- Sorties dashboard et matrices modèles disponibles.
- Le script peut créer `.dashboard_env` au premier lancement Streamlit. Ce dossier est un environnement local d'exécution, pas un fichier métier à rendre.

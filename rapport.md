# Rapport détaillé - Projet Data Science : retards de vols US

**Référentiel** : RNCP40875 - Projet Data Science  
**Compétences couvertes** : C3.1, C3.2, C3.3, C4.1, C4.2, C4.3  
**Livrable final** : dossier `Pilé` + notebook exécuté + dashboard Streamlit + rapport  
**Données** : `flights.csv`, `airlines.csv`, `airports.csv`

---

## 1. Synthèse exécutive

Le projet vise à aider les équipes opérationnelles aériennes à comprendre, visualiser et anticiper les retards de vols domestiques américains de 2015. Le livrable final consolide les meilleurs éléments des trois dossiers de travail :

- `DATA S` : notebook complet, robuste et exécuté pour le nettoyage, l'EDA, les exports dashboard et les modèles baseline.
- `DATA S 2` : version validée et exécutée du notebook principal, utilisée comme socle de contrôle.
- `DATA S 3` : version enrichie avec dashboard Streamlit, rapport, sorties agrégées et dossier final `Pilé`.

Le résultat est un pipeline complet :

1. préparation et qualité des données ;
2. analyse exploratoire orientée métier ;
3. dashboard interactif ;
4. modèles prédictifs comparés ;
5. stratégie d'intégration IA alignée métier, gouvernance et écoresponsabilité.

---

## 2. Données et cadrage métier

### 2.1 Contexte

Les retards de vols ont un impact direct sur :

- la satisfaction passager ;
- les correspondances manquées ;
- les coûts de compensation ;
- la désorganisation des équipes sol ;
- les rotations d'appareils et d'équipages ;
- la performance d'image de la compagnie aérienne.

La question centrale du dashboard et de l'analyse est :

> Où, quand et pourquoi les vols sont-ils en retard, et comment anticiper ces retards ?

### 2.2 Sources utilisées

| Fichier | Rôle | Utilisation |
|---|---|---|
| `flights.csv` | vols, horaires, retards, annulations, déroutements | dataset principal |
| `airlines.csv` | codes IATA compagnies | enrichissement lisible des compagnies |
| `airports.csv` | codes IATA aéroports, villes, états | enrichissement des analyses aéroportuaires |

Le jeu de données brut contient environ 5,8 millions de vols.

---

## 3. Préparation et nettoyage des données (C3.1)

### 3.1 Choix de nettoyage

Le notebook applique les décisions suivantes :

- suppression des vols annulés (`CANCELLED=1`), car aucun retard à l'arrivée n'est observable ;
- suppression des vols déroutés (`DIVERTED=1`), car l'arrivée ne correspond plus au plan initial ;
- suppression des lignes sans `ARRIVAL_DELAY`, afin de ne pas fabriquer artificiellement la cible ;
- typage optimisé des colonnes pour limiter la mémoire ;
- conversion des variables catégorielles en chaînes/catégories ;
- correction BTS vers IATA lorsque le mapping `outputs/bts_to_iata.json` est disponible.

Après nettoyage, le dataset exploitable contient **5 714 008 vols**.

### 3.2 Variable cible

La cible `IS_DELAYED` est définie ainsi :

```python
IS_DELAYED = 1 si ARRIVAL_DELAY > 15 minutes, sinon 0
```

Le seuil de 15 minutes est cohérent avec les usages de ponctualité aérienne. Il pourrait être adapté :

- à 5 minutes pour du pilotage qualité interne ;
- à 30 minutes pour une logique de compensation passager ;
- à un seuil variable selon les correspondances ou les contraintes réglementaires.

Le taux global observé est d'environ **17,9 % de vols retardés**.

### 3.3 Feature engineering

Les variables créées incluent :

- `SCHEDULED_DEP_HOUR` : heure de départ programmée extraite du format HHMM ;
- `DEP_PERIOD` : période de la journée ;
- `IS_WEEKEND` : indicateur samedi/dimanche ;
- variables enrichies par référentiels compagnies et aéroports.

---

## 4. Analyse exploratoire orientée métier (C3.3)

### 4.1 KPI globaux

Les KPI suivis dans le notebook et le dashboard sont :

- nombre total de vols ;
- taux de retard supérieur à 15 minutes ;
- retard moyen à l'arrivée ;
- retard médian à l'arrivée ;
- retard moyen au départ ;
- volumes par compagnie, aéroport, mois, jour et heure.

### 4.2 Enseignements principaux

1. **Saisonnalité**  
   Les retards varient nettement selon les mois. Les périodes hivernales, estivales et de fêtes sont plus exposées. Cela permet d'anticiper les ressources avant les pics.

2. **Effet horaire**  
   Les retards augmentent souvent au fil de la journée. Cela suggère un effet cascade lié aux rotations d'appareils et aux retards accumulés.

3. **Disparités compagnie/aéroport**  
   Certaines compagnies et certains hubs concentrent davantage de retards. Le dashboard filtre les segments à volume suffisant pour éviter des conclusions statistiquement fragiles.

4. **Volume et taux doivent être lus ensemble**  
   Un fort taux de retard sur quelques vols n'a pas la même priorité opérationnelle qu'un taux modéré sur un hub majeur.

---

## 5. Dashboard interactif (C3.2)

### 5.1 Choix technique

Le dashboard est développé avec **Streamlit + Plotly** :

- stack 100 % Python ;
- interactivité native ;
- filtres rapides ;
- visualisations exportables ;
- lancement local simple ;
- pas de coût de licence.

### 5.2 Dashboard enrichi

Le fichier `dashboard.py` a été réécrit comme un front Streamlit en **3 pages métier** :

| Page | Objectif | Contenu principal |
|---|---|---|
| Page 1 - Vue exécutive | Donner une lecture direction en moins d'une minute | KPI globaux, jauge de ponctualité, donut retards/à l'heure, évolution mensuelle, mois critiques, compagnies/aéroports/routes à risque, synthèse modèle |
| Page 2 - Analyse opérationnelle | Diagnostiquer les causes et segments d'intervention | temporalité, mois les plus en retard, compagnies, villes, aéroports, routes, table filtrable/exportable |
| Page 3 - Recommandations | Transformer l'analyse en décisions | simulateur prédictif de départ, playbooks métier, recommandations priorisées, matrice impact/effort, feuille de route 30/60/90 jours, décisions permises, matrices modèle et dashboards consolidés |

Cette structure rend le livrable plus lisible pour l'évaluation : la première page répond au pilotage, la deuxième à l'analyse opérationnelle, la troisième à la stratégie d'action.

La page exécutive a été consolidée avec des visuels de lecture rapide : une jauge compare le taux de retard au seuil de vigilance, un donut sépare vols à l'heure et vols retardés, un graphique compare les métriques des modèles, et des bar charts isolent les mois, compagnies et routes qui contribuent le plus aux retards. La page recommandations a été renforcée avec un simulateur de départ, des playbooks métier déclenchables, une matrice impact/effort, une timeline de déploiement IA, des matrices de confusion visuelles et une comparaison des dashboards issus des notebooks disponibles.

Le simulateur de départ permet de choisir un mois, une compagnie, un aéroport de départ et un aéroport d'arrivée, avec heure et type de jour optionnels. Le dashboard compare le scénario à plusieurs références historiques et utilise aussi un modèle pré-départ fine-tuné pour produire un score, un seuil d'alerte et une décision. La sortie est directement opérationnelle : niveau de risque, fiabilité statistique, retard moyen attendu et actions recommandées pour l'escale, le centre opérations ou l'expérience client.

La Page 3 mesure aussi le modèle sur le filtre exact `mois + compagnie + aéroport de départ + aéroport d'arrivée` à partir du jeu de test holdout. Lorsque le volume est suffisant, elle affiche accuracy, balanced accuracy, precision, recall, F1 et ROC-AUC sur ce segment précis.

### 5.3 KPIs choisis et justification

| KPI | Pourquoi ce choix | Décision associée |
|---|---|---|
| Vols analysés | Vérifie le volume de la sélection et la fiabilité statistique des comparaisons | Éviter d'agir sur des segments trop faibles |
| Taux de retard | Mesure centrale de ponctualité, seuil métier `ARRIVAL_DELAY > 15` | Identifier périodes, compagnies, routes et aéroports prioritaires |
| Vols retardés | Quantifie le volume d'incidents, pas seulement leur proportion | Dimensionner l'impact opérationnel |
| Retard moyen arrivée | Traduit l'impact client et correspondances | Prioriser communication passagers et plans de correspondance |
| Retard médian arrivée | Limite l'effet des retards extrêmes | Distinguer problème structurel et incidents isolés |
| Retard moyen départ | Mesure plus actionnable côté opérations sol et rotation | Ajuster portes, équipes, embarquement et marges |
| Recall du modèle retard | Réduit le risque de faux négatifs dans une logique d'alerte | Choisir le seuil de déclenchement opérationnel |

### 5.4 Injection des dashboards multi-notebooks

Les dashboards et exports présents dans les différents dossiers ont été consolidés dans `outputs/consolidated_dashboards/`.
Cette consolidation évite de dupliquer plusieurs fichiers complets d'environ 1 Go chacun dans le rendu, tout en gardant :

- un manifeste des sources : `dashboard_sources_manifest.csv` ;
- les KPI comparables par notebook : `dashboard_kpi_summary.csv` ;
- les agrégats mensuels, compagnies, aéroports et destinations ;
- un échantillon contrôlé des dashboards complets : `all_flights_dashboard_samples.csv`.

Ces fichiers alimentent l'onglet **Dashboards consolidés** de Streamlit, ce qui permet de comparer les résultats des notebooks sans ouvrir chaque fichier séparément.

### 5.5 Filtres disponibles

- mois ;
- jour de semaine ;
- compagnie ;
- plage horaire ;
- ville de départ ;
- aéroport de départ ;
- ville d'arrivée ;
- aéroport d'arrivée ;
- option "vols retardés uniquement".
- volume minimum des segments dans la page opérationnelle ;
- recherche texte, tri et choix de colonnes dans la table de contrôle.

Les filtres d'aéroports sont dépendants des villes : lorsque l'utilisateur sélectionne une ville de départ ou d'arrivée, la liste des aéroports disponibles est réduite aux aéroports rattachés à cette ville. Cela évite les listes trop longues et rend l'analyse plus proche des usages opérationnels.

L'onglet **Données** ajoute un niveau d'exploration plus fin :

- recherche texte sur les compagnies, villes et aéroports ;
- filtres locaux sur statut, période de départ, retards et distance ;
- choix des colonnes affichées ;
- tri ascendant ou descendant sur n'importe quelle colonne ;
- pagination contrôlée pour garder l'interface fluide ;
- profil qualité des colonnes avec types, valeurs manquantes et cardinalité ;
- constructeur d'agrégations métier par compagnie, aéroport, heure, mois ou route ;
- export CSV limité ou complet selon le besoin d'analyse.

### 5.6 Décisions permises par le dashboard

Le dashboard permet de prendre les décisions suivantes :

- renforcer les équipes sol sur les mois, jours et heures à risque ;
- identifier les mois les plus critiques et exposer les compagnies, villes, aéroports de départ et destinations associés ;
- prioriser les hubs, routes ou compagnies à auditer quand le volume est suffisant ;
- ajuster les marges de rotation sur les créneaux exposés à l'effet cascade ;
- déclencher des notifications passagers ou correspondances sur les segments à risque ;
- simuler un départ mois + compagnie + destination pour décider entre traitement nominal, surveillance active, pré-alerte passager ou renfort escale ;
- choisir un modèle et un seuil d'alerte en fonction du recall, du F1-score et des faux négatifs ;
- suivre la dérive opérationnelle via les KPI mensuels et les matrices modèle.

### 5.7 Version de secours

En plus de Streamlit, une version HTML autonome est générée :

- `dashboard_preview.html`

Elle permet de consulter les KPI et graphiques principaux même si le serveur Streamlit n'est pas lancé.

---

## 6. Modélisation prédictive (C4.2)

### 6.1 Scénario de prédiction

Le scénario retenu est une prédiction **avant le départ programmé**. Les variables connues après le vol sont exclues afin d'éviter le data leakage :

- `ARRIVAL_DELAY` n'est pas utilisée comme feature ;
- `DEPARTURE_DELAY` est utilisée en EDA/dashboard, mais exclue du modèle prédictif avant départ ;
- les causes détaillées de retard sont post-vol et donc exclues.

### 6.2 Features retenues

Variables catégorielles :

- `AIRLINE` ;
- `ORIGIN_AIRPORT` ;
- `DESTINATION_AIRPORT` ;
- `DEP_PERIOD`.

Variables numériques :

- `MONTH` ;
- `DAY` ;
- `DAY_OF_WEEK` ;
- `IS_WEEKEND` ;
- `SCHEDULED_DEP_HOUR` ;
- `SCHEDULED_TIME` ;
- `DISTANCE`.

### 6.3 Prétraitement

Le pipeline respecte les consignes du syllabus :

- `SimpleImputer(strategy="median")` pour les variables numériques ;
- `StandardScaler()` pour les variables numériques ;
- `SimpleImputer(strategy="most_frequent")` pour les catégorielles ;
- `OneHotEncoder(handle_unknown="ignore")` pour les catégorielles.

### 6.4 Modèles comparés

Le modèle a été réentraîné sur **800 000 vols** issus de `outputs/flights_dashboard.csv`.
Le split est stratifié :

- train : 480 000 vols ;
- validation : 160 000 vols ;
- test : 160 000 vols ;
- taux de retard dans l'échantillon : 17,9 %.

Deux contextes métier sont distingués :

| Contexte | Usage | Variables sensibles |
|---|---|---|
| `preflight` | prédiction avant le départ programmé | exclut `DEPARTURE_DELAY` pour éviter une fuite de données |
| `operational_live` | prédiction après observation du retard au départ | inclut `DEPARTURE_DELAY`, plus précis mais utilisable plus tard |

La version finale compare plusieurs familles de modèles pour couvrir une baseline naïve, un modèle linéaire interprétable et des modèles non linéaires :

| Modèle | Rôle |
|---|---|
| Baseline majoritaire | point de comparaison minimal, prédit la classe majoritaire |
| Logistic Regression | baseline simple, rapide, interprétable |
| Random Forest | modèle non linéaire testé sur le contexte pré-vol |
| HistGradientBoosting | boosting efficace sur données tabulaires, meilleur potentiel de discrimination |

Les classes sont pondérées avec `class_weight="balanced"` pour tenir compte du déséquilibre entre vols retardés et non retardés.
Le seuil de décision est optimisé sur validation afin d'améliorer le F1-score, indicateur plus adapté que l'accuracy brute dans ce problème déséquilibré.

---

## 7. Évaluation et comparaison des modèles (C4.3)

Les modèles sont comparés avec :

- `classification_report` ;
- accuracy ;
- balanced accuracy ;
- F1-score ;
- ROC-AUC ;
- courbe ROC ;
- matrice de confusion ;
- seuil de décision optimisé ;
- estimation simple du coût d'entraînement.

Résultats sauvegardés dans `outputs/model_comparison.csv` :

| Contexte | Modèle | Seuil | Accuracy | Balanced accuracy | Precision | Recall retard | F1 | ROC-AUC |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `preflight` | HistGradientBoosting | 0,200 | 0,695 | 0,650 | 0,311 | 0,578 | 0,404 | 0,707 |
| `operational_live` | HistGradientBoosting | 0,385 | 0,935 | 0,863 | 0,865 | 0,752 | 0,805 | 0,941 |

Un modèle complémentaire a été fine-tuné pour la simulation métier par filtres `MONTH`, `AIRLINE`, `ORIGIN_AIRPORT` et `DESTINATION_AIRPORT`. Le split reste strictement séparé : 480 000 lignes train, 160 000 validation et 160 000 test. Le seuil final est choisi sur validation avec contrainte de précision et de rappel, puis mesuré sur test holdout.

| Modèle | Usage | Seuil | Accuracy | Balanced accuracy | Precision | Recall retard | F1 | ROC-AUC |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `segment_finetuned_preflight` | simulation mois/compagnie/départ/arrivée | 0,525 | 0,692 | 0,651 | 0,310 | 0,587 | 0,405 | 0,711 |

Les sorties associées sont :

- `outputs/model_artifacts/segment_finetuned_preflight_model.joblib` ;
- `outputs/model_artifacts/segment_finetuned_overall_metrics.csv` ;
- `outputs/model_artifacts/segment_finetuned_filter_metrics.csv` ;
- `outputs/model_artifacts/segment_finetuned_scenario_metrics.csv` ;
- `outputs/model_artifacts/segment_finetuned_scenario_month_metrics.csv` ;
- `outputs/model_artifacts/segment_finetuned_test_predictions.csv` ;
- `outputs/model_artifacts/segment_finetuned_sample_distribution.csv`.

Les scénarios utilisés sont :

- `normal_sans_vacances` : mars, avril, mai, septembre, octobre ;
- `incident_vacances` : juin, juillet, août, novembre, décembre ;
- `intermediaire` : autres mois conservés dans l'apprentissage.

Le meilleur modèle dans les deux contextes est **HistGradientBoosting**.
Le contexte `operational_live` est beaucoup plus précis car il utilise le retard au départ. Cette variable est légitime pour une alerte après départ ou pendant le suivi opérationnel, mais elle ne doit pas être utilisée pour une prédiction strictement avant départ.

Les artefacts sauvegardés sont :

- `outputs/model_artifacts/best_preflight_model.joblib` ;
- `outputs/model_artifacts/best_operational_live_model.joblib` ;
- `outputs/model_artifacts/best_models_metadata.json`.

Les matrices de confusion sont exportées dans :

- `outputs/model_artifacts/model_confusion_matrix_wide.csv` : matrice synthétique TN/FP/FN/TP par modèle ;
- `outputs/model_artifacts/model_confusion_matrices.csv` : matrice longue exploitable dans Streamlit ;
- `outputs/model_artifacts/model_metrics_all_thresholds.csv` : comparaison seuil 0,50 vs seuil optimisé ;
- `outputs/model_artifacts/model_classification_report.csv` : precision/recall/F1 par classe.

La métrique métier prioritaire reste le **rappel de la classe retard** : rater un vrai retard peut empêcher les équipes d'agir à temps, alors qu'une fausse alerte reste généralement moins coûteuse. Le dashboard affiche donc les faux négatifs explicitement pour aider au choix du modèle.

---

## 8. Stratégie d'intégration IA (C4.1)

### 8.1 Cas d'usage

- notification proactive des passagers ;
- allocation dynamique des portes ;
- ajustement des équipes sol ;
- identification des correspondances à risque ;
- aide à la décision pour superviseurs opérations ;
- score de risque intégré au dashboard quotidien.

### 8.2 Gouvernance

- versionner les jeux de données, features et modèles ;
- documenter les variables exclues pour éviter le data leakage ;
- suivre les performances par hub, compagnie, saison et jour ;
- définir un seuil d'alerte validé avec les métiers ;
- conserver une validation humaine pour les décisions sensibles.

### 8.3 Écoresponsabilité

- entraîner sur un échantillon représentatif ;
- éviter les modèles trop lourds si le gain marginal est faible ;
- limiter la fréquence de réentraînement ;
- suivre temps d'entraînement, énergie estimée et CO2 équivalent ;
- privilégier la sobriété de calcul en phase pilote.

### 8.4 Feuille de route

| Phase | Objectif | Livrable |
|---|---|---|
| M0-M1 | cadrage et POC | notebook + dashboard |
| M1-M2 | pilote métier | score de risque sur un hub ou un périmètre réduit |
| M2-M3 | intégration SI | API ou batch alimentant le dashboard |
| M3+ | monitoring | suivi drift, performance, feedback terrain |

---

## 9. Contenu du livrable final

Le dossier `Pilé` contient :

- `flights_delay.ipynb` : notebook complété, exécuté, corrigé ;
- `dashboard.py` : dashboard Streamlit enrichi ;
- `dashboard_preview.html` : aperçu autonome sans serveur ;
- `rapport.md` : présent rapport détaillé ;
- `README_RENDU.md` : instructions ;
- `requirements.txt` : dépendances ;
- `outputs/` : données dashboard, agrégats, dashboards consolidés et comparaison modèles ;
- `outputs/model_artifacts/` : matrices de confusion, classification reports et métriques multi-seuils ;
- `outputs/consolidated_dashboards/` : exports fusionnés des notebooks `DATA S`, `DATA S 2` et `DATA S 3` ;
- `scripts/` : scripts reproductibles pour régénérer les matrices modèles et la consolidation dashboard ;
- `flights_delay/` : fichiers sources ;
- `RNCP40875 - Syllabus - Projet Data Science.pdf`.

---

## 10. Conclusion

Le projet final est cohérent avec les attendus RNCP40875 :

- **C3.1** : données nettoyées, typées, documentées ;
- **C3.2** : dashboard interactif enrichi, filtrable et orienté décision ;
- **C3.3** : EDA métier avec KPI, saisonnalité, heures, compagnies, aéroports et routes ;
- **C4.1** : stratégie IA, gouvernance, éthique et déploiement ;
- **C4.2** : pipelines ML reproductibles avec preprocessing ;
- **C4.3** : comparaison de modèles avec métriques adaptées et dimension écoresponsable.

Le dashboard Streamlit est maintenant fonctionnel et plus complet. La version HTML autonome garantit aussi une consultation immédiate même sans serveur.

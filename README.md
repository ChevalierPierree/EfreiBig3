# Projet Data Science — Prédiction des retards de vols (RNCP40875)

Branche `data-science` du dépôt EfreiBig3. Analyse exploratoire, modélisation et
dashboard de prédiction des retards de vols (jeu de données *flights*).

## ⚠️ Cloner avec Git LFS (obligatoire)
Les données et modèles volumineux (dont `flights_delay/flights.csv`, ~565 Mo) sont
versionnés via **Git LFS**. Sans LFS, vous ne récupérerez que des fichiers « pointeurs ».

```bash
# 1. Installer Git LFS une fois (macOS : brew install git-lfs)
git lfs install
# 2. Cloner la bonne branche
git clone -b data-science https://github.com/ChevalierPierree/EfreiBig3.git
# (si déjà cloné sans LFS : git lfs pull)
```

## Installation de l'environnement
Le venv n'est pas versionné (il se recrée à l'identique) :
```bash
python3 -m venv .dashboard_env
source .dashboard_env/bin/activate
pip install -r requirements.txt
```

## Lancer
- **Notebook** : ouvrir `flights_delay.ipynb` (analyse + modélisation).
- **Dashboard** : `./launch_dashboard.sh` (Streamlit) — ou `streamlit run dashboard.py`.

## Contenu
| Élément | Rôle |
|---|---|
| `flights_delay.ipynb` | Notebook principal (EDA, modèles) |
| `dashboard.py` · `launch_dashboard.sh` | Dashboard Streamlit |
| `scripts/` | Scripts de traitement |
| `outputs/` | Sorties (agrégats, prédictions, modèles `.joblib`) — via LFS |
| `flights_delay/` | Données brutes (`flights.csv`, `airlines.csv`, `airports.csv`) — via LFS |
| `dashboard_preview.html` | Version HTML autonome du dashboard (si Streamlit n'est pas lancé) |
| `requirements.txt` | Dépendances Python |
| `rapport.md` | Rapport détaillé (compétences C3.1 à C4.3) |

> Méthodologie, choix et résultats complets : voir `rapport.md`.

Projet réalisé en binôme : **Pierre Chevalier** et **Jean Macario**.

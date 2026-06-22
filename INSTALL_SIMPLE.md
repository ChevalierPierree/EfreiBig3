# 🚀 Installation PATATOR - Guide Simple

## Pré-requis

1. **Docker Desktop** (obligatoire)
   - Mac : https://www.docker.com/products/docker-desktop
   - Windows : https://www.docker.com/products/docker-desktop
   - Linux : `sudo apt install docker.io docker-compose`

2. **Python 3.11+** (obligatoire)
   - Vérifier : `python3 --version`
   - Mac : `brew install python@3.11`
   - Windows : https://www.python.org/downloads/

---

## Installation en 4 étapes

### 1️⃣ Cloner le projet
```bash
git clone https://github.com/ChevalierPierree/ProjetDataM1JeanPierre.git
cd ProjetDataM1JeanPierre
git checkout PierreDump
```

### 2️⃣ Installer les dépendances Python
```bash
pip3 install -r requirements.txt
```

**Si erreur sur Mac M1/M2** (pandas ou numpy) :
```bash
pip3 install --upgrade pip
pip3 install -r requirements.txt --no-cache-dir
```

**Si toujours des erreurs** :
```bash
# Installation une par une
pip3 install psycopg2-binary pymongo kafka-python
pip3 install fastapi uvicorn pydantic
pip3 install pandas numpy python-dotenv requests
```

### 3️⃣ Démarrer Docker Desktop
- Ouvrir l'application Docker Desktop
- Attendre que le logo soit vert (Docker démarré)

### 4️⃣ Lancer PATATOR
```bash
chmod +x patator
./patator
```

🎉 **C'est tout !** Attendre 3-5 minutes que tout se lance.

---

## Vérification

### Dashboard accessible ?
Ouvrir : http://localhost:7600/fraud_dashboard.html

### API fonctionne ?
```bash
curl http://localhost:8000/health
```

### Services Docker actifs ?
```bash
docker compose ps
```

---

## Problèmes courants

### ❌ "docker: command not found"
➡️ Docker Desktop n'est pas installé ou pas démarré

### ❌ "pip3: command not found"  
➡️ Python 3 n'est pas installé

### ❌ "Port already in use"
```bash
# Libérer les ports
lsof -ti:8000 | xargs kill -9
lsof -ti:7600 | xargs kill -9
```

### ❌ Erreur pandas/numpy sur Mac M1/M2
```bash
# Solution 1 : Forcer la recompilation
pip3 install pandas numpy --no-binary :all:

# Solution 2 : Utiliser les wheels pré-compilés
pip3 install pandas numpy --only-binary :all:

# Solution 3 : Version minimale
pip3 install pandas>=2.0.0 numpy>=1.24.0
```

### ❌ "PostgreSQL n'a pas démarré"
```bash
# Redémarrer les services Docker
docker compose down
docker compose up -d
```

---

## Arrêter tout

```bash
cd /chemin/vers/ProjetDataM1JeanPierre
docker compose down
```

---

## Support

- 📖 Documentation complète : `PATATOR_GUIDE.md`
- 🚀 Démarrage rapide : `QUICKSTART.md`
- 📊 Vue d'ensemble : `AUDIT_RENDU_PROJET.md`

---

**Version** : 1.0.0  
**Date** : Février 2026  
**Projet** : M1 Data Engineering - EFREI

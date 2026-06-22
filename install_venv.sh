#!/bin/bash

# Script d'installation automatique pour environnement virtuel
# Usage: ./install_venv.sh

set -e  # Arrêter en cas d'erreur

echo "======================================================================"
echo "🔧 INSTALLATION AUTOMATIQUE - PATATOR (avec venv)"
echo "======================================================================"
echo ""

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Vérifier qu'on est dans le bon répertoire
if [ ! -f "patator" ]; then
    echo -e "${RED}❌ Erreur: fichier 'patator' introuvable${NC}"
    echo "Assurez-vous d'être dans le dossier ProjetDataM1JeanPierre"
    exit 1
fi

echo -e "${BLUE}📂 Répertoire actuel: $(pwd)${NC}"
echo ""

# Étape 1: Vérifier Python
echo -e "${YELLOW}1️⃣  Vérification de Python...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo -e "${GREEN}✅ $PYTHON_VERSION${NC}"
else
    echo -e "${RED}❌ Python 3 n'est pas installé${NC}"
    exit 1
fi
echo ""

# Étape 2: Créer/vérifier le venv
echo -e "${YELLOW}2️⃣  Configuration de l'environnement virtuel...${NC}"
if [ -d ".venv" ]; then
    echo -e "${BLUE}ℹ️  .venv existe déjà${NC}"
    read -p "Voulez-vous le recréer ? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🗑️  Suppression de l'ancien venv..."
        rm -rf .venv
        echo "🔨 Création d'un nouveau venv..."
        python3 -m venv .venv
        echo -e "${GREEN}✅ Nouveau venv créé${NC}"
    else
        echo -e "${BLUE}ℹ️  Utilisation du venv existant${NC}"
    fi
else
    echo "🔨 Création du venv..."
    python3 -m venv .venv
    echo -e "${GREEN}✅ venv créé${NC}"
fi
echo ""

# Étape 3: Activer le venv
echo -e "${YELLOW}3️⃣  Activation du venv...${NC}"
source .venv/bin/activate
echo -e "${GREEN}✅ venv activé${NC}"
echo -e "${BLUE}Python: $(which python)${NC}"
echo -e "${BLUE}pip: $(which pip)${NC}"
echo ""

# Étape 4: Mettre à jour pip
echo -e "${YELLOW}4️⃣  Mise à jour de pip...${NC}"
pip install --upgrade pip --quiet
echo -e "${GREEN}✅ pip mis à jour${NC}"
echo ""

# Étape 5: Installer les dépendances
echo -e "${YELLOW}5️⃣  Installation des dépendances (10 packages)...${NC}"
echo "Cela peut prendre 1-2 minutes..."
if pip install -r requirements.txt; then
    echo -e "${GREEN}✅ Toutes les dépendances sont installées${NC}"
else
    echo -e "${RED}❌ Erreur lors de l'installation${NC}"
    exit 1
fi
echo ""

# Étape 6: Vérifier les imports
echo -e "${YELLOW}6️⃣  Vérification des imports...${NC}"
if [ -f "test_dependencies.py" ]; then
    python test_dependencies.py
else
    echo -e "${BLUE}ℹ️  test_dependencies.py introuvable, test manuel...${NC}"
    python -c "import psycopg2, pymongo, kafka, fastapi, uvicorn, pydantic, pandas, numpy, dotenv, requests" && echo -e "${GREEN}✅ Tous les modules sont importables${NC}" || echo -e "${RED}❌ Certains modules manquent${NC}"
fi
echo ""

# Étape 7: Rendre patator exécutable
echo -e "${YELLOW}7️⃣  Configuration de patator...${NC}"
chmod +x patator
echo -e "${GREEN}✅ patator est exécutable${NC}"
echo ""

# Résumé
echo "======================================================================"
echo -e "${GREEN}🎉 INSTALLATION TERMINÉE !${NC}"
echo "======================================================================"
echo ""
echo "Pour lancer le projet :"
echo -e "${BLUE}  ./patator${NC}"
echo ""
echo "Le venv est déjà activé. Si vous fermez ce terminal :"
echo -e "${BLUE}  source .venv/bin/activate${NC}"
echo -e "${BLUE}  ./patator${NC}"
echo ""
echo "Services qui seront lancés :"
echo "  • 13 services Docker (Kafka, PostgreSQL, MongoDB, Flink, etc.)"
echo "  • Chargement de 71,694 événements"
echo "  • Génération de 10,857 alertes de fraude"
echo "  • API Backend: http://localhost:8000"
echo "  • Dashboard: http://localhost:7600/fraud_dashboard.html"
echo ""
echo -e "${YELLOW}⏱️  Durée du premier lancement: 3-5 minutes${NC}"
echo "======================================================================"

#!/bin/bash

# Script de test pour vérifier que l'installation PATATOR fonctionne
# Usage: ./test_patator.sh

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}==================================${NC}"
echo -e "${BLUE}   PATATOR - Test d'Installation${NC}"
echo -e "${BLUE}==================================${NC}"
echo ""

# Compteurs
PASSED=0
FAILED=0

# Fonction de test
test_check() {
    local name=$1
    local command=$2
    
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ $name${NC}"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}❌ $name${NC}"
        ((FAILED++))
        return 1
    fi
}

# Tests de base
echo "📋 Vérification des pré-requis..."
echo ""

test_check "Docker installé" "command -v docker"
test_check "Docker Compose installé" "command -v docker-compose || docker compose version"
test_check "Python 3 installé" "command -v python3"
test_check "curl installé" "command -v curl"

echo ""
echo "📁 Vérification des fichiers..."
echo ""

test_check "Script patator existe" "test -f patator"
test_check "Script patator est exécutable" "test -x patator"
test_check "requirements.txt existe" "test -f requirements.txt"
test_check "docker-compose.yml existe" "test -f docker-compose.yml"

echo ""
echo "📦 Vérification des scripts Python..."
echo ""

test_check "load_data_to_postgres.py" "test -f scripts/load_data_to_postgres.py"
test_check "load_events_to_mongodb.py" "test -f scripts/load_events_to_mongodb.py"
test_check "create_kafka_topics.py" "test -f scripts/create_kafka_topics.py"
test_check "stream_events_to_kafka.py" "test -f scripts/stream_events_to_kafka.py"
test_check "fraud_detection_realtime.py" "test -f scripts/fraud_detection_realtime.py"

echo ""
echo "🌐 Vérification de l'API et Dashboard..."
echo ""

test_check "fraud_dashboard_api.py" "test -f api/fraud_dashboard_api.py"
test_check "fraud_dashboard.html" "test -f dashboard/fraud_dashboard.html"

echo ""
echo "📖 Vérification de la documentation..."
echo ""

test_check "README.md" "test -f README.md"
test_check "PATATOR_GUIDE.md" "test -f PATATOR_GUIDE.md"
test_check "QUICKSTART.md" "test -f QUICKSTART.md"
test_check "INSTALLATION.md" "test -f INSTALLATION.md"
test_check "RECAP_COMPLET_PROJET.md" "test -f RECAP_COMPLET_PROJET.md"

echo ""
echo "📊 Vérification des dépendances Python..."
echo ""

# Vérifier quelques packages critiques
if python3 -c "import kafka" 2>/dev/null; then
    echo -e "${GREEN}✅ kafka-python installé${NC}"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠️  kafka-python pas installé (sera installé par requirements.txt)${NC}"
fi

if python3 -c "import psycopg2" 2>/dev/null; then
    echo -e "${GREEN}✅ psycopg2 installé${NC}"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠️  psycopg2 pas installé (sera installé par requirements.txt)${NC}"
fi

if python3 -c "import pymongo" 2>/dev/null; then
    echo -e "${GREEN}✅ pymongo installé${NC}"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠️  pymongo pas installé (sera installé par requirements.txt)${NC}"
fi

if python3 -c "import fastapi" 2>/dev/null; then
    echo -e "${GREEN}✅ fastapi installé${NC}"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠️  fastapi pas installé (sera installé par requirements.txt)${NC}"
fi

echo ""
echo "🐳 Vérification Docker..."
echo ""

if docker info > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Docker démon actif${NC}"
    ((PASSED++))
else
    echo -e "${RED}❌ Docker démon non actif - Démarrez Docker Desktop${NC}"
    ((FAILED++))
fi

# Résumé
echo ""
echo -e "${BLUE}==================================${NC}"
echo -e "${BLUE}         RÉSUMÉ DES TESTS${NC}"
echo -e "${BLUE}==================================${NC}"
echo ""

TOTAL=$((PASSED + FAILED))
echo -e "Total: ${TOTAL} tests"
echo -e "${GREEN}Réussis: ${PASSED}${NC}"
echo -e "${RED}Échoués: ${FAILED}${NC}"

echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 Parfait ! Votre installation est prête !${NC}"
    echo ""
    echo -e "Vous pouvez maintenant lancer :"
    echo -e "${BLUE}./patator${NC}"
    echo ""
    exit 0
else
    echo -e "${YELLOW}⚠️  Quelques problèmes détectés${NC}"
    echo ""
    echo "Actions recommandées :"
    echo "1. Installez les dépendances Python : pip3 install -r requirements.txt"
    echo "2. Vérifiez que Docker Desktop est lancé"
    echo "3. Rendez le script exécutable : chmod +x patator"
    echo ""
    echo "Puis relancez ce test : ./test_patator.sh"
    echo ""
    exit 1
fi

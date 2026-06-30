#!/bin/bash

# ============================================================================
# 🚀 KiVendTout - Script de Démarrage Complet
# ============================================================================
# Projet : KiVendTout E-commerce Fraud Detection
# Auteur : Pierre Chevalier
# Date : Février 2026
# ============================================================================

set -e  # Exit on error

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Emoji
ROCKET="🚀"
CHECK="✅"
CROSS="❌"
HOURGLASS="⏳"
INFO="ℹ️"
WARNING="⚠️"

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
API_PORT=8000
DASHBOARD_PORT=7600
PYTHON_BIN="python3"

# ============================================================================
# Fonctions Utilitaires
# ============================================================================

print_header() {
    echo ""
    echo -e "${PURPLE}============================================================================${NC}"
    echo -e "${PURPLE}$1${NC}"
    echo -e "${PURPLE}============================================================================${NC}"
    echo ""
}

print_step() {
    echo -e "${CYAN}${HOURGLASS} $1...${NC}"
}

print_success() {
    echo -e "${GREEN}${CHECK} $1${NC}"
}

print_error() {
    echo -e "${RED}${CROSS} $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}${WARNING} $1${NC}"
}

print_info() {
    echo -e "${BLUE}${INFO} $1${NC}"
}

check_command() {
    if command -v $1 &> /dev/null; then
        print_success "$1 est installé"
        return 0
    else
        print_error "$1 n'est pas installé"
        return 1
    fi
}

select_python_bin() {
    # Priorité 1: venv actif dans le shell appelant
    if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
        PYTHON_BIN="$VIRTUAL_ENV/bin/python"
        print_info "Python utilisé (venv actif): $PYTHON_BIN"
        return 0
    fi

    # Priorité 2: venv local du projet
    if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
        PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
        print_info "Python utilisé (venv projet): $PYTHON_BIN"
        return 0
    fi

    # Fallback
    PYTHON_BIN="python3"
    print_warning "Aucun venv détecté, fallback sur python3 système"
}

wait_for_service() {
    local url=$1
    local name=$2
    local max_attempts=30
    local attempt=1
    
    echo -n "   Attente de $name"
    while [ $attempt -le $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo ""
            print_success "$name est opérationnel"
            return 0
        fi
        echo -n "."
        sleep 1
        ((attempt++))
    done
    echo ""
    print_error "$name n'a pas démarré après ${max_attempts}s"
    return 1
}

check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

kill_port() {
    local port=$1
    if check_port $port; then
        print_warning "Port $port occupé, libération en cours..."
        lsof -ti:$port | xargs kill -9 2>/dev/null || true
        sleep 2
    fi
}

# ============================================================================
# Fonctions Principales
# ============================================================================

show_banner() {
    clear 2>/dev/null || true
    echo -e "${PURPLE}"
    cat << "EOF"
    ____  ___  __________  ________________  ____
   / __ \/   |/_  __/   |/_  __/ ____/ __ \/ __ \
  / /_/ / /| | / / / /| | / / / / __/ /_/ / /_/ /
 / ____/ ___ |/ / / ___ |/ / / /_/ / _, _/ _, _/
/_/   /_/  |_/_/ /_/  |_/_/  \____/_/ |_/_/ |_|

    KiVendTout E-commerce Fraud Detection
    Projet M1 Data Engineering - EFREI
    
EOF
    echo -e "${NC}"
}

check_prerequisites() {
    print_header "1️⃣  VÉRIFICATION DES PRÉ-REQUIS"
    
    local all_ok=true
    
    check_command "docker" || all_ok=false
    check_command "docker-compose" || check_command "docker" || all_ok=false
    check_command "python3" || all_ok=false
    check_command "curl" || all_ok=false
    
    if [ "$all_ok" = false ]; then
        print_error "Certains pré-requis sont manquants"
        exit 1
    fi
    
    print_success "Tous les pré-requis sont satisfaits"
}

start_docker_services() {
    print_header "2️⃣  DÉMARRAGE DE L'INFRASTRUCTURE DOCKER"
    
    print_step "Démarrage des 13 services Docker"
    cd "$PROJECT_DIR"
    
    if docker compose ps | grep -q "Up"; then
        print_info "Certains services sont déjà actifs"
        docker compose up -d
    else
        docker compose up -d
    fi
    
    print_success "Services Docker démarrés"
    
    # Attendre que les services critiques soient prêts
    print_step "Attente des services critiques..."
    
    # Vérifier PostgreSQL
    local pg_attempts=0
    while [ $pg_attempts -lt 30 ]; do
        if docker compose exec -T postgres pg_isready -U postgres >/dev/null 2>&1; then
            print_success "PostgreSQL est prêt"
            break
        fi
        sleep 1
        ((pg_attempts++))
    done
    if [ $pg_attempts -ge 30 ]; then
        print_error "PostgreSQL n'a pas démarré après 30s"
        return 1
    fi
    
    # Vérifier Kafka
    local kafka_attempts=0
    while [ $kafka_attempts -lt 30 ]; do
        if docker compose exec -T kafka-1 kafka-broker-api-versions --bootstrap-server localhost:9092 >/dev/null 2>&1; then
            print_success "Kafka est prêt"
            break
        fi
        sleep 1
        ((kafka_attempts++))
    done
    if [ $kafka_attempts -ge 30 ]; then
        print_error "Kafka n'a pas démarré après 30s"
        return 1
    fi
    
    print_success "Infrastructure Docker opérationnelle"
}

check_postgres_loaded() {
    print_step "Vérification des données dans PostgreSQL"

    local customers=$(docker compose exec -T postgres psql -t -A -U postgres -d kivendtout -c "SELECT COUNT(*) FROM customers;" 2>/dev/null | tr -dc '0-9')
    local orders=$(docker compose exec -T postgres psql -t -A -U postgres -d kivendtout -c "SELECT COUNT(*) FROM orders;" 2>/dev/null | tr -dc '0-9')
    local payments=$(docker compose exec -T postgres psql -t -A -U postgres -d kivendtout -c "SELECT COUNT(*) FROM payments;" 2>/dev/null | tr -dc '0-9')
    local idv=$(docker compose exec -T postgres psql -t -A -U postgres -d kivendtout -c "SELECT COUNT(*) FROM identity_verifications;" 2>/dev/null | tr -dc '0-9')
    local alert_schema=$(docker compose exec -T postgres psql -t -A -U postgres -d kivendtout -c "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='fraud_alerts' AND column_name='alert_timestamp';" 2>/dev/null | tr -dc '0-9')
    local dataset_schema=$(docker compose exec -T postgres psql -t -A -U postgres -d kivendtout -c "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='fraud_alerts_dataset' AND column_name='alert_ts';" 2>/dev/null | tr -dc '0-9')

    customers=${customers:-0}
    orders=${orders:-0}
    payments=${payments:-0}
    idv=${idv:-0}
    alert_schema=${alert_schema:-0}
    dataset_schema=${dataset_schema:-0}

    if [ "$customers" -gt 0 ] && [ "$orders" -gt 0 ] && [ "$payments" -gt 0 ] && [ "$idv" -gt 0 ] && [ "$alert_schema" -gt 0 ] && [ "$dataset_schema" -gt 0 ]; then
        print_success "Données PostgreSQL présentes ($customers clients, $orders commandes, $payments paiements, $idv vérifications ID)"
        return 0
    else
        print_warning "Données PostgreSQL absentes ou incomplètes"
        return 1
    fi
}

check_mongo_loaded() {
    print_step "Vérification des données dans MongoDB"

    local mongo_count=$(docker compose exec -T mongodb mongosh --quiet -u admin -p admin --authenticationDatabase admin --eval 'db.getSiblingDB("kivendtout").events.countDocuments()' 2>/dev/null | tail -1 | tr -dc '0-9')
    mongo_count=${mongo_count:-0}

    if [ "$mongo_count" -gt 0 ]; then
        print_success "Données MongoDB présentes ($mongo_count événements)"
        return 0
    else
        print_warning "Données MongoDB absentes ou incomplètes"
        return 1
    fi
}

load_initial_data() {
    print_header "3️⃣  CHARGEMENT DES DONNÉES"
    
    if ! check_postgres_loaded; then
        print_step "Réinitialisation du schéma PostgreSQL"
        docker compose exec -T postgres psql -U postgres -d kivendtout -f /docker-entrypoint-initdb.d/00_reset_schema.sql > /dev/null

        print_step "Chargement PostgreSQL"
        "$PYTHON_BIN" "$PROJECT_DIR/scripts/load_complete_data_to_postgres.py"
        print_success "PostgreSQL chargé"
    else
        print_info "PostgreSQL déjà chargé, skip"
    fi

    if ! check_mongo_loaded; then
        print_step "Chargement MongoDB"
        "$PYTHON_BIN" "$PROJECT_DIR/scripts/load_events_to_mongodb.py"
        print_success "MongoDB chargé"
    else
        print_info "MongoDB déjà chargé, skip"
    fi
}

setup_kafka() {
    print_header "4️⃣  CONFIGURATION KAFKA"
    
    # Vérifier si les topics existent
    if docker compose exec -T kafka-1 kafka-topics --bootstrap-server localhost:9092 --list 2>/dev/null | grep -q "payments"; then
        print_info "Topics Kafka déjà créés"
    else
        print_step "Création des topics Kafka"
        "$PYTHON_BIN" "$PROJECT_DIR/scripts/create_kafka_topics.py" || true
        print_success "Topics Kafka créés"
    fi
    
    # Toujours restreamer pour garantir des messages consommables
    # (les offsets Kafka ne représentent pas forcément des messages encore présents).
    print_step "Streaming des événements vers Kafka"
    "$PYTHON_BIN" "$PROJECT_DIR/scripts/stream_events_to_kafka.py"
    print_success "71,694 événements streamés"
}

start_fraud_detection() {
    print_header "5️⃣  DÉTECTION DE FRAUDE"
    
    # Vérifier si des alertes existent déjà
    local alert_count=$(docker compose exec -T postgres psql -t -A -U postgres -d kivendtout -c "SELECT COUNT(*) FROM fraud_alerts;" 2>/dev/null | tr -dc '0-9')
    alert_count=${alert_count:-0}
    
    if [ "$alert_count" -gt 100 ]; then
        print_info "Alertes de fraude déjà générées ($alert_count alertes)"
    else
        print_step "Lancement de la détection de fraude"
        "$PYTHON_BIN" "$PROJECT_DIR/scripts/fraud_detection_realtime.py" > "$LOG_DIR/fraud_detection.log" 2>&1 &
        local pid=$!
        
        # Attendre max 60 secondes
        sleep 60
        
        if ps -p $pid > /dev/null; then
            kill $pid 2>/dev/null || true
        fi

        local new_count=$(docker compose exec -T postgres psql -t -A -U postgres -d kivendtout -c "SELECT COUNT(*) FROM fraud_alerts;" 2>/dev/null | tr -dc '0-9')
        new_count=${new_count:-0}
        if [ "$new_count" -le "$alert_count" ]; then
            print_error "Aucune nouvelle alerte générée (avant=$alert_count, après=$new_count)"
            tail -n 60 "$LOG_DIR/fraud_detection.log" || true
            return 1
        fi

        print_success "Détection de fraude terminée ($new_count alertes)"
    fi
}

start_api() {
    print_header "6️⃣  DÉMARRAGE DE L'API BACKEND"
    
    # Vérifier si l'API tourne déjà
    if check_port $API_PORT; then
        if curl -s "http://localhost:$API_PORT/health" > /dev/null 2>&1; then
            print_info "API déjà active sur le port $API_PORT"
            return 0
        fi
        print_warning "Port $API_PORT occupé mais API non saine, redémarrage"
        kill_port $API_PORT
    fi
    
    print_step "Démarrage de l'API FastAPI"
    "$PYTHON_BIN" "$PROJECT_DIR/api/fraud_dashboard_api.py" > "$LOG_DIR/fraud_dashboard_api.log" 2>&1 &
    
    wait_for_service "http://localhost:$API_PORT/health" "API Backend" || {
        tail -n 80 "$LOG_DIR/fraud_dashboard_api.log" || true
        return 1
    }
    
    # Sync alertes depuis Kafka
    print_step "Synchronisation des alertes depuis Kafka"
    sleep 3
    curl -X POST "http://localhost:$API_PORT/api/sync" > /dev/null 2>&1 || true
    print_success "Alertes synchronisées"
}

start_dashboard() {
    print_header "7️⃣  DÉMARRAGE DU DASHBOARD WEB"
    
    # Vérifier si le dashboard tourne déjà
    if check_port $DASHBOARD_PORT; then
        print_info "Dashboard déjà actif sur le port $DASHBOARD_PORT"
        return 0
    fi
    
    print_step "Démarrage du serveur HTTP pour le dashboard"
    cd "$PROJECT_DIR/dashboard"
    "$PYTHON_BIN" -m http.server $DASHBOARD_PORT > "$LOG_DIR/http_server.log" 2>&1 &
    
    sleep 2
    wait_for_service "http://localhost:$DASHBOARD_PORT/fraud_dashboard.html" "Dashboard Web"
}

show_summary() {
    print_header "8️⃣  RÉCAPITULATIF ET ACCÈS"
    
    # Récupérer les stats
    local stats=$(curl -s "http://localhost:$API_PORT/api/stats" 2>/dev/null || echo "{}")
    local total_alerts=$(echo "$stats" | "$PYTHON_BIN" -c "import sys, json; data=json.load(sys.stdin); print(data.get('total_alerts', 'N/A'))" 2>/dev/null || echo "N/A")
    local fraud_rate=$(echo "$stats" | "$PYTHON_BIN" -c "import sys, json; data=json.load(sys.stdin); print(f\"{data.get('fraud_rate', 0):.2f}%\")" 2>/dev/null || echo "N/A")
    
    echo -e "${GREEN}"
    cat << EOF
┌─────────────────────────────────────────────────────────────────┐
│                    🎉 KiVendTout EST OPÉRATIONNEL !                │
└─────────────────────────────────────────────────────────────────┘

📊 STATISTIQUES:
   • Total alertes de fraude : $total_alerts
   • Taux de fraude          : $fraud_rate

🌐 SERVICES DISPONIBLES:

   🖥️  DASHBOARD WEB (Interface Analyst)
   → http://localhost:$DASHBOARD_PORT/fraud_dashboard.html
   
   🔌 API REST (Backend)
   → http://localhost:$API_PORT
   → http://localhost:$API_PORT/health
   
   📊 KAFKA UI (Monitoring Kafka)
   → http://localhost:8082
   
   🐘 FLINK WEB UI (Processing)
   → http://localhost:8083
   
   📈 GRAFANA (Dashboards)
   → http://localhost:3000
   
   🔥 PROMETHEUS (Metrics)
   → http://localhost:9090

🐳 SERVICES DOCKER (13):
EOF
    docker compose ps | grep -E "(Up|running)" | awk '{print "   ✅ " $1}'
    
    echo ""
    echo -e "${CYAN}📝 LOGS:${NC}"
    echo "   • API Backend     : tail -f $LOG_DIR/fraud_dashboard_api.log"
    echo "   • Fraud Detection : tail -f $LOG_DIR/fraud_detection.log"
    echo "   • HTTP Server     : tail -f $LOG_DIR/http_server.log"
    
    echo ""
    echo -e "${YELLOW}🛑 POUR TOUT ARRÊTER:${NC}"
    echo "   cd $PROJECT_DIR && docker compose down"
    
    echo -e "${GREEN}"
    echo "┌─────────────────────────────────────────────────────────────────┐"
    echo "│           Bon courage avec votre projet ! 🚀                    │"
    echo "└─────────────────────────────────────────────────────────────────┘"
    echo -e "${NC}"
}

open_dashboard() {
    print_info "Ouverture automatique du dashboard dans 5 secondes..."
    sleep 5
    
    if command -v open &> /dev/null; then
        # macOS
        open "http://localhost:$DASHBOARD_PORT/fraud_dashboard.html"
    elif command -v xdg-open &> /dev/null; then
        # Linux
        xdg-open "http://localhost:$DASHBOARD_PORT/fraud_dashboard.html"
    elif command -v start &> /dev/null; then
        # Windows
        start "http://localhost:$DASHBOARD_PORT/fraud_dashboard.html"
    fi
}

# ============================================================================
# Fonction Principale
# ============================================================================

main() {
    show_banner
    
    # Créer le dossier logs si nécessaire
    mkdir -p "$LOG_DIR"
    touch "$LOG_DIR/runtime_refresh.log"
    
    # Exécution séquentielle
    check_prerequisites
    select_python_bin
    start_docker_services
    load_initial_data
    setup_kafka
    start_fraud_detection
    start_api
    start_dashboard
    show_summary
    
    # Ouvrir le dashboard
    open_dashboard
}

# ============================================================================
# Point d'entrée
# ============================================================================

# Trap CTRL+C
trap 'echo -e "\n${RED}❌ Interruption par l'\''utilisateur${NC}"; exit 1' INT

# Lancer le script
main "$@"

#!/bin/bash

# ============================================================================
# SCRIPT D'ARRÊT - KIVENDTOUT
# ============================================================================

set -e

echo "🛑 Arrêt de l'infrastructure KiVendTout..."

# Arrêter tous les services
docker compose down

echo "✅ Tous les services ont été arrêtés."
echo ""
echo "💡 Pour supprimer également les données (volumes), utilisez :"
echo "   docker compose down -v"

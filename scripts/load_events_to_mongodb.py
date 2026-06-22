#!/usr/bin/env python3
"""
Script d'ingestion des événements utilisateurs vers MongoDB
Charge events.jsonl (71,694 événements) dans la collection events
"""

import json
from pathlib import Path
from datetime import datetime
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import BulkWriteError
import sys

# Configuration MongoDB
MONGO_CONFIG = {
    'host': 'localhost',
    'port': 27017,
    'username': 'admin',
    'password': 'admin',
    'auth_source': 'admin',
    'database': 'kivendtout',
    'collection': 'events'
}

DATASET_PATH = Path(__file__).parent.parent / 'kivendtout_dataset' / 'events.jsonl'

# Couleurs pour output
class Color:
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_success(msg):
    print(f"{Color.GREEN}✓{Color.END} {msg}")

def print_info(msg):
    print(f"{Color.BLUE}ℹ{Color.END} {msg}")

def print_warning(msg):
    print(f"{Color.YELLOW}⚠{Color.END} {msg}")

def print_error(msg):
    print(f"{Color.RED}✗{Color.END} {msg}")

def get_mongo_client():
    """Connexion à MongoDB"""
    try:
        client = MongoClient(
            host=MONGO_CONFIG['host'],
            port=MONGO_CONFIG['port'],
            username=MONGO_CONFIG['username'],
            password=MONGO_CONFIG['password'],
            authSource=MONGO_CONFIG['auth_source'],
            serverSelectionTimeoutMS=5000
        )
        # Test connexion
        client.server_info()
        print_success(f"Connecté à MongoDB: {MONGO_CONFIG['host']}:{MONGO_CONFIG['port']}")
        return client
    except Exception as e:
        print_error(f"Erreur connexion MongoDB: {e}")
        sys.exit(1)

def create_indexes(collection):
    """Crée les indexes pour optimiser les requêtes"""
    print_info("Création des indexes...")
    
    indexes = [
        ('customer_id', ASCENDING),
        ('session_id', ASCENDING),
        ('event_type', ASCENDING),
        ('ts', DESCENDING),  # Pour trier par date
        ([('customer_id', ASCENDING), ('ts', DESCENDING)], None),  # Index composé
        ([('event_type', ASCENDING), ('ts', DESCENDING)], None)
    ]
    
    for idx in indexes:
        if isinstance(idx[0], list):
            collection.create_index(idx[0])
            print_success(f"  Index composé créé: {idx[0]}")
        else:
            collection.create_index(idx[0], background=True)
            print_success(f"  Index créé: {idx[0]}")

def load_events(client):
    """Charge les événements depuis events.jsonl vers MongoDB"""
    print_info("Chargement des événements...")
    
    db = client[MONGO_CONFIG['database']]
    collection = db[MONGO_CONFIG['collection']]
    
    # Drop collection si existe (fresh start)
    collection.drop()
    print_info(f"  Collection '{MONGO_CONFIG['collection']}' nettoyée")
    
    # Lire et parser le fichier JSONL
    events = []
    line_count = 0
    
    print_info(f"  Lecture du fichier: {DATASET_PATH}")
    
    with open(DATASET_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line_count += 1
            try:
                event = json.loads(line.strip())
                
                # Conversion timestamp string → datetime pour MongoDB
                if 'ts' in event:
                    event['ts'] = datetime.fromisoformat(event['ts'])
                
                events.append(event)
                
                # Insertion par batch de 5000 pour performance
                if len(events) >= 5000:
                    collection.insert_many(events, ordered=False)
                    print_info(f"  {line_count:,} événements lus, {len(events):,} insérés...")
                    events = []
                    
            except json.JSONDecodeError as e:
                print_warning(f"  Ligne {line_count} ignorée (JSON invalide): {e}")
            except Exception as e:
                print_warning(f"  Erreur ligne {line_count}: {e}")
    
    # Insérer le dernier batch
    if events:
        try:
            collection.insert_many(events, ordered=False)
        except BulkWriteError as e:
            print_warning(f"  Quelques doublons ignorés: {e.details['nInserted']} insérés")
    
    print_success(f"  {line_count:,} lignes lues depuis le fichier")
    
    # Vérifier le nombre total inséré
    total_inserted = collection.count_documents({})
    print_success(f"  {total_inserted:,} événements insérés dans MongoDB")
    
    return total_inserted

def validate_data(client):
    """Valide les données insérées avec des statistiques"""
    print_info("\n" + "="*60)
    print_info("VALIDATION DES DONNÉES")
    print_info("="*60 + "\n")
    
    db = client[MONGO_CONFIG['database']]
    collection = db[MONGO_CONFIG['collection']]
    
    # 1. Comptage total
    total = collection.count_documents({})
    print_info(f"📊 Total événements: {total:,}")
    
    # 2. Types d'événements
    print_info("\n📋 Types d'événements:")
    pipeline = [
        {'$group': {'_id': '$event_type', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ]
    for doc in collection.aggregate(pipeline):
        event_type = doc['_id']
        count = doc['count']
        percentage = (count / total) * 100
        print_info(f"  {event_type:.<30} {count:>6,} ({percentage:>5.1f}%)")
    
    # 3. Top 5 clients les plus actifs
    print_info("\n👥 Top 5 clients les plus actifs:")
    pipeline = [
        {'$group': {'_id': '$customer_id', 'nb_events': {'$sum': 1}}},
        {'$sort': {'nb_events': -1}},
        {'$limit': 5}
    ]
    for idx, doc in enumerate(collection.aggregate(pipeline), 1):
        print_info(f"  {idx}. {doc['_id']:.<20} {doc['nb_events']:>4} événements")
    
    # 4. Période temporelle
    print_info("\n📅 Période des événements:")
    pipeline = [
        {'$group': {
            '_id': None,
            'first_event': {'$min': '$ts'},
            'last_event': {'$max': '$ts'}
        }}
    ]
    result = list(collection.aggregate(pipeline))
    if result:
        first = result[0]['first_event']
        last = result[0]['last_event']
        duration = (last - first).days
        print_info(f"  Premier événement: {first.strftime('%Y-%m-%d %H:%M:%S')}")
        print_info(f"  Dernier événement: {last.strftime('%Y-%m-%d %H:%M:%S')}")
        print_info(f"  Durée totale: {duration} jours")
    
    # 5. Événements par device
    print_info("\n📱 Événements par device:")
    pipeline = [
        {'$group': {'_id': '$device', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ]
    for doc in collection.aggregate(pipeline):
        if doc['_id']:
            device = doc['_id']
            count = doc['count']
            percentage = (count / total) * 100
            print_info(f"  {device:.<20} {count:>6,} ({percentage:>5.1f}%)")
    
    # 6. Sources UTM
    print_info("\n🎯 Sources UTM:")
    pipeline = [
        {'$group': {'_id': '$utm_source', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 5}
    ]
    for doc in collection.aggregate(pipeline):
        if doc['_id']:
            source = doc['_id']
            count = doc['count']
            percentage = (count / total) * 100
            print_info(f"  {source:.<20} {count:>6,} ({percentage:>5.1f}%)")
    
    # 7. Exemples d'événements
    print_info("\n📝 Exemples d'événements (3 premiers):")
    for idx, event in enumerate(collection.find().limit(3), 1):
        event.pop('_id')  # Retirer l'ObjectId MongoDB
        print_info(f"\n  Événement {idx}:")
        for key, value in event.items():
            print_info(f"    {key}: {value}")

def main():
    """Fonction principale d'orchestration"""
    print("\n" + "="*70)
    print(f"{Color.BOLD}      INGESTION ÉVÉNEMENTS KIVENDTOUT VERS MONGODB{Color.END}")
    print("="*70 + "\n")
    
    print_info(f"Fichier source: {DATASET_PATH}")
    
    start_time = datetime.now()
    
    try:
        # Connexion
        client = get_mongo_client()
        
        # Chargement
        total_inserted = load_events(client)
        
        # Création indexes
        db = client[MONGO_CONFIG['database']]
        collection = db[MONGO_CONFIG['collection']]
        create_indexes(collection)
        
        # Validation
        validate_data(client)
        
        # Fermeture
        client.close()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print("\n" + "="*70)
        print(f"{Color.GREEN}{Color.BOLD}✓ INGESTION TERMINÉE AVEC SUCCÈS{Color.END}")
        print("="*70)
        print_info(f"Durée totale: {duration:.2f} secondes")
        print_info(f"Vitesse: {total_inserted / duration:,.0f} événements/seconde")
        print_info(f"Base: {MONGO_CONFIG['database']}")
        print_info(f"Collection: {MONGO_CONFIG['collection']}")
        
    except Exception as e:
        print_error(f"\nERREUR CRITIQUE: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

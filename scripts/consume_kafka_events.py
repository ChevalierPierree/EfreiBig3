#!/usr/bin/env python3
"""
Consumer Kafka - Consommation et analyse des événements en temps réel
"""

import importlib.util
import json
import site
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


def patch_kafka_vendor_six():
    candidates = []
    try:
        candidates.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        candidates.append(site.getusersitepackages())
    except Exception:
        pass

    for base in candidates:
        six_path = Path(base) / "kafka" / "vendor" / "six.py"
        if not six_path.exists():
            continue
        spec = importlib.util.spec_from_file_location("kafka.vendor.six", six_path)
        if not spec or not spec.loader:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules.setdefault("kafka.vendor.six", module)
        sys.modules.setdefault("kafka.vendor.six.moves", module.moves)
        return


patch_kafka_vendor_six()
from kafka import KafkaConsumer

def consume_events(topic='user-events', max_messages=100):
    """
    Consomme des événements depuis un topic Kafka
    
    Args:
        topic: Nom du topic à consommer
        max_messages: Nombre maximum de messages à lire (None = illimité)
    """
    
    print(f"🔌 Connexion au cluster Kafka...")
    
    try:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=['localhost:9092', 'localhost:9093', 'localhost:9094'],
            auto_offset_reset='earliest',  # Lire depuis le début
            enable_auto_commit=True,
            group_id='kivendtout-consumer-group',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            consumer_timeout_ms=5000  # Stop après 5s sans message
        )
        
        print(f"✅ Consumer initialisé sur le topic '{topic}'")
        
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        sys.exit(1)
    
    # Statistiques
    count = 0
    event_types = Counter()
    devices = Counter()
    customers = set()
    timestamps = []
    
    print(f"\n📥 Consommation des messages (max: {max_messages or 'illimité'})...\n")
    
    try:
        for message in consumer:
            event = message.value
            count += 1
            
            # Collecte de statistiques
            event_types[event.get('event_type', 'unknown')] += 1
            devices[event.get('device', 'unknown')] += 1
            
            if 'customer_id' in event:
                customers.add(event['customer_id'])
            
            if 'ts' in event:
                timestamps.append(event['ts'])
            
            # Affichage du message
            if count <= 10 or count % 1000 == 0:
                print(f"📨 Message #{count} | Partition: {message.partition} | Offset: {message.offset}")
                print(f"   └─ Type: {event.get('event_type')} | Customer: {event.get('customer_id', 'N/A')} | "
                      f"Device: {event.get('device', 'N/A')}")
            
            # Limite optionnelle
            if max_messages and count >= max_messages:
                print(f"\n⚠️  Limite de {max_messages} messages atteinte")
                break
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interruption utilisateur")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
    finally:
        consumer.close()
    
    # Affichage des statistiques
    print(f"\n{'='*70}")
    print(f"📊 STATISTIQUES DE CONSOMMATION")
    print(f"{'='*70}")
    print(f"Messages consommés: {count:,}")
    print(f"Clients uniques: {len(customers):,}")
    
    if timestamps:
        print(f"Période: {min(timestamps)} → {max(timestamps)}")
    
    print(f"\n📈 Top 10 types d'événements:")
    for event_type, count_val in event_types.most_common(10):
        percentage = (count_val / count * 100) if count > 0 else 0
        print(f"  • {event_type:<25} : {count_val:>6,} ({percentage:>5.1f}%)")
    
    print(f"\n📱 Distribution par device:")
    for device, count_val in devices.most_common():
        percentage = (count_val / count * 100) if count > 0 else 0
        print(f"  • {device:<15} : {count_val:>6,} ({percentage:>5.1f}%)")
    
    print(f"{'='*70}\n")

def list_topics():
    """
    Liste tous les topics disponibles dans Kafka
    """
    print("🔌 Connexion au cluster Kafka...")
    
    try:
        consumer = KafkaConsumer(
            bootstrap_servers=['localhost:9092', 'localhost:9093', 'localhost:9094'],
            consumer_timeout_ms=5000
        )
        
        topics = consumer.topics()
        print(f"\n📋 Topics disponibles ({len(topics)}):")
        for topic in sorted(topics):
            print(f"  • {topic}")
        
        consumer.close()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        sys.exit(1)

if __name__ == '__main__':
    print("="*70)
    print("🎧 KAFKA EVENT CONSUMER - KiVendTout")
    print("="*70)
    
    # Choix du mode
    if len(sys.argv) > 1:
        if sys.argv[1] == 'list':
            list_topics()
        else:
            topic = sys.argv[1]
            max_msg = int(sys.argv[2]) if len(sys.argv) > 2 else 100
            consume_events(topic=topic, max_messages=max_msg)
    else:
        # Par défaut: consommer user-events
        print("\nMode par défaut: user-events (100 premiers messages)")
        print("Usage: python3 consume_kafka_events.py [topic] [max_messages]")
        print("       python3 consume_kafka_events.py list  (pour lister les topics)\n")
        consume_events(topic='user-events', max_messages=100)

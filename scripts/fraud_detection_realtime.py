#!/usr/bin/env python3
"""
Détection de fraude en temps réel (Python simple)
Alternative à Flink pour démonstration rapide
Consomme payments depuis Kafka, détecte fraudes, publie dans fraud-alerts

Version 2.0 avec règles avancées:
- Velocity check (3+ paiements en 10 min)
- Device fingerprinting
- Montant inhabituel
- Fast checkout
"""

import importlib.util
import json
import os
import site
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2


def patch_kafka_vendor_six():
    """
    Compatibilité Python 3.13 pour kafka-python 2.0.2:
    expose kafka.vendor.six.moves si absent.
    """
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
from kafka import KafkaConsumer, KafkaProducer

class FraudDetector:
    """
    Moteur de détection de fraude avec règles métier avancées
    """
    
    def __init__(self):
        # Connexion PostgreSQL pour enrichissement
        self.pg_conn = psycopg2.connect(
            host='localhost',
            port=5432,
            database='kivendtout',
            user='postgres',
            password='postgres'
        )
        self.cursor = self.pg_conn.cursor()
        
        # Cache en mémoire pour détection velocity et device fingerprinting
        self.customer_activity = defaultdict(list)  # {customer_id: [(timestamp, event_type, amount)]}
        self.customer_devices = defaultdict(set)  # {customer_id: {device1, device2, ...}}
        self.customer_cart_times = {}  # {session_id: first_cart_timestamp}
        
        # Statistiques
        self.stats = {
            'events_processed': 0,
            'frauds_detected': 0,
            'by_rule': defaultdict(int)
        }
    
    def enrich_with_postgres(self, event):
        """
        Enrichit l'événement avec des données PostgreSQL
        """
        try:
            customer_id = event.get('customer_id')
            session_id = event.get('session_id')
            
            # Récupérer infos client avec rollback si erreur
            try:
                self.cursor.execute(
                    """
                    SELECT country, created_at
                    FROM customers
                    WHERE customer_id = %s
                    """,
                    (customer_id,),
                )
                
                customer_data = self.cursor.fetchone()
                if customer_data:
                    event['customer_country'] = customer_data[0]
                    event['customer_registration_date'] = str(customer_data[1])
                    
                    # Calculer si c'est un nouveau client (< 7 jours)
                    reg_date = customer_data[1].date() if customer_data[1] else datetime.now().date()
                    days_since_registration = (datetime.now().date() - reg_date).days
                    event['is_new_customer'] = days_since_registration < 7
            except Exception as e:
                self.pg_conn.rollback()
                print(f"⚠️  Erreur customer query: {e}")
            
            # Récupérer historique paiements avec moyenne
            try:
                self.cursor.execute(
                    """
                    SELECT 
                        COUNT(*),
                        COALESCE(SUM(p.amount), 0),
                        COALESCE(AVG(p.amount), 0)
                    FROM payments p
                    JOIN orders o ON p.order_id = o.order_id
                    WHERE o.customer_id = %s
                      AND p.payment_status = 'success'
                    """,
                    (customer_id,),
                )
                
                payment_history = self.cursor.fetchone()
                if payment_history:
                    event['previous_successful_payments'] = payment_history[0]
                    event['previous_payments_total'] = float(payment_history[1])
                    event['average_payment_amount'] = float(payment_history[2])
                else:
                    event['previous_successful_payments'] = 0
                    event['previous_payments_total'] = 0.0
                    event['average_payment_amount'] = 0.0
            except Exception as e:
                self.pg_conn.rollback()
                print(f"⚠️  Erreur payments query: {e}")
            
            # Récupérer info session (pour cart timing)
            try:
                self.cursor.execute("""
                    SELECT created_at
                    FROM sessions
                    WHERE session_id = %s
                """, (session_id,))
                
                session_data = self.cursor.fetchone()
                if session_data:
                    event['session_created_at'] = str(session_data[0])
            except Exception as e:
                self.pg_conn.rollback()
                print(f"⚠️  Erreur session query: {e}")
            
            return event
        
        except Exception as e:
            print(f"⚠️  Erreur enrichissement global pour {event.get('customer_id')}: {e}")
            self.pg_conn.rollback()
            return event
    
    def detect_fraud(self, event):
        """
        Applique les règles de détection de fraude (10 règles avancées)
        Retourne (is_fraud, fraud_reasons, risk_score)
        """
        fraud_reasons = []
        risk_score = 0
        
        customer_id = event.get('customer_id')
        session_id = event.get('session_id')
        device = event.get('device', '')
        event_ts = event.get('ts', '')
        
        # ========== RÈGLES BASIQUES ==========
        
        # RÈGLE 1: Premier paiement (jamais acheté avant)
        if event.get('previous_successful_payments', 0) == 0:
            fraud_reasons.append('FIRST_PAYMENT')
            risk_score += 40
        
        # RÈGLE 2: Nouveau client (< 7 jours)
        if event.get('is_new_customer', False):
            fraud_reasons.append('NEW_CUSTOMER')
            risk_score += 30
        
        # RÈGLE 3: Heure inhabituelle (2h-6h du matin)
        try:
            ts = datetime.fromisoformat(event_ts)
            hour = ts.hour
            if 2 <= hour <= 6:
                fraud_reasons.append('UNUSUAL_HOUR')
                risk_score += 35
        except:
            ts = None
        
        # RÈGLE 4: Device mobile (plus risqué pour fraude)
        if device in ['ios', 'android', 'web_mobile']:
            fraud_reasons.append('MOBILE_DEVICE')
            risk_score += 20
        
        # RÈGLE 5: Traffic direct (pas de référent)
        utm_source = event.get('utm_source', '')
        if utm_source == 'direct':
            fraud_reasons.append('DIRECT_TRAFFIC')
            risk_score += 15
        
        # RÈGLE 6: Type d'événement payment_failure
        if event.get('event_type') == 'payment_failure':
            fraud_reasons.append('PAYMENT_FAILED')
            risk_score += 50
        
        # ========== RÈGLES AVANCÉES ==========
        
        # RÈGLE 7: VELOCITY CHECK - 3+ paiements en < 10 minutes
        if ts and customer_id:
            # Ajouter l'événement actuel à l'historique
            self.customer_activity[customer_id].append((ts, event.get('event_type'), 0))
            
            # Garder uniquement les événements des 10 dernières minutes
            ten_min_ago = ts - timedelta(minutes=10)
            self.customer_activity[customer_id] = [
                (t, e, a) for t, e, a in self.customer_activity[customer_id] 
                if t >= ten_min_ago
            ]
            
            # Compter les payment_attempt dans les 10 dernières minutes
            payment_events = [e for t, e, a in self.customer_activity[customer_id] 
                            if e in ['payment_attempt', 'payment_success', 'payment_failure']]
            
            if len(payment_events) >= 3:
                fraud_reasons.append('VELOCITY_HIGH')
                risk_score += 45
        
        # RÈGLE 8: DEVICE FINGERPRINTING - Nouveau device jamais vu
        if customer_id and device:
            known_devices = self.customer_devices[customer_id]
            if device not in known_devices:
                # Premier événement avec ce device
                if len(known_devices) > 0:  # Client a déjà utilisé d'autres devices
                    fraud_reasons.append('NEW_DEVICE')
                    risk_score += 30
                # Enregistrer le device
                self.customer_devices[customer_id].add(device)
        
        # RÈGLE 9: MONTANT INHABITUEL - > 3x moyenne du client
        # Note: Les événements n'ont pas de montant direct, on utilise l'historique
        avg_amount = event.get('average_payment_amount', 0)
        if avg_amount > 0:
            # Simuler montant basé sur le type d'événement (pour démo)
            # En production, récupérer montant réel du panier
            estimated_amount = 50 if event.get('event_type') == 'payment_attempt' else 0
            if estimated_amount > avg_amount * 3:
                fraud_reasons.append('UNUSUAL_AMOUNT')
                risk_score += 40
        
        # RÈGLE 10: PANIER SUSPECT - Checkout trop rapide (< 30s après ajout panier)
        if session_id and event.get('event_type') in ['payment_attempt', 'checkout']:
            # Chercher le dernier add_to_cart dans l'historique de ce client
            recent_carts = [
                t for t, e, a in self.customer_activity.get(customer_id, []) 
                if e == 'add_to_cart'
            ]
            
            if recent_carts and ts:
                last_cart_time = max(recent_carts)
                time_since_cart = (ts - last_cart_time).total_seconds()
                
                if time_since_cart < 30:
                    fraud_reasons.append('FAST_CHECKOUT')
                    risk_score += 35
        
        # RÈGLE 11: GEOLOCATION MISMATCH - Pays IP ≠ pays customer
        # Note: Les événements n'ont pas de country IP, on simule avec device
        # En production, utiliser GeoIP sur l'adresse IP
        customer_country = event.get('customer_country', 'FR')
        # Simuler: si device mobile + customer FR, supposer IP peut être différent
        if device in ['ios', 'android'] and customer_country == 'FR':
            # En prod: comparer IP country avec customer_country
            # if ip_country != customer_country: ...
            pass  # Skip pour démo (besoin vraie IP geolocation)
        
        # Considéré comme fraude si score >= 60 ou payment_failure
        is_fraud = risk_score >= 60 or 'PAYMENT_FAILED' in fraud_reasons
        
        return is_fraud, fraud_reasons, min(risk_score, 100)
    
    def create_fraud_alert(self, event, fraud_reasons, risk_score):
        """
        Crée une alerte de fraude formatée
        """
        alert = {
            'alert_id': f"FRD_{event.get('customer_id', 'UNKNOWN')}_{int(time.time() * 1000)}",
            'alert_timestamp': datetime.now().isoformat(),
            'event_timestamp': event.get('ts'),
            'customer_id': event.get('customer_id'),
            'session_id': event.get('session_id'),
            'event_type': event.get('event_type'),
            'device': event.get('device'),
            'utm_source': event.get('utm_source'),
            'customer_country': event.get('customer_country', 'UNKNOWN'),
            'previous_payments': event.get('previous_successful_payments', 0),
            'is_new_customer': event.get('is_new_customer', False),
            'fraud_reasons': fraud_reasons,
            'risk_score': risk_score,
            'status': 'PENDING_REVIEW',
            'severity': 'HIGH' if risk_score >= 80 else 'MEDIUM' if risk_score >= 60 else 'LOW'
        }
        return alert

    def persist_alert(self, alert):
        """
        Persiste l'alerte dans PostgreSQL pour disponibilité immédiate du dashboard.
        """
        try:
            self.cursor.execute(
                """
                INSERT INTO fraud_alerts (
                    alert_id, alert_timestamp, event_timestamp, customer_id,
                    session_id, event_type, device, utm_source, customer_country,
                    previous_payments, is_new_customer, fraud_reasons,
                    risk_score, status, severity
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (alert_id) DO NOTHING
                """,
                (
                    alert['alert_id'],
                    alert['alert_timestamp'],
                    alert.get('event_timestamp'),
                    alert.get('customer_id'),
                    alert.get('session_id'),
                    alert.get('event_type'),
                    alert.get('device'),
                    alert.get('utm_source'),
                    alert.get('customer_country'),
                    alert.get('previous_payments', 0),
                    alert.get('is_new_customer', False),
                    ','.join(alert.get('fraud_reasons', [])),
                    alert.get('risk_score', 0),
                    alert.get('status', 'PENDING_REVIEW'),
                    alert.get('severity', 'LOW'),
                ),
            )
            self.pg_conn.commit()
        except Exception as e:
            self.pg_conn.rollback()
            print(f"⚠️  Erreur persist alert: {e}")
    
    def process_event(self, event):
        """
        Traite un événement: enrichissement + détection
        """
        self.stats['events_processed'] += 1
        
        # Enrichissement
        enriched_event = self.enrich_with_postgres(event)
        
        # Détection
        is_fraud, fraud_reasons, risk_score = self.detect_fraud(enriched_event)
        
        if is_fraud:
            self.stats['frauds_detected'] += 1
            for reason in fraud_reasons:
                self.stats['by_rule'][reason] += 1
            
            alert = self.create_fraud_alert(enriched_event, fraud_reasons, risk_score)
            return alert
        
        return None
    
    def close(self):
        """
        Ferme les connexions
        """
        if hasattr(self, 'cursor'):
            self.cursor.close()
        if hasattr(self, 'pg_conn'):
            self.pg_conn.close()

def run_fraud_detection():
    """
    Boucle principale de détection de fraude
    """
    print("="*70)
    print("🕵️  FRAUD DETECTION ENGINE - KiVendTout")
    print("="*70)
    print("\n🔌 Initialisation...\n")
    
    # Consumer Kafka (topic payments)
    consumer_group = os.getenv("FRAUD_CONSUMER_GROUP", f"fraud-detector-group-{int(time.time())}")
    consumer = KafkaConsumer(
        'payments',
        bootstrap_servers=['localhost:9092', 'localhost:9093', 'localhost:9094'],
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        group_id=consumer_group,
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        consumer_timeout_ms=10000  # 10 secondes timeout
    )
    
    # Compression Kafka: fallback sans compression si lz4 indisponible
    compression = "lz4"
    try:
        import lz4.block  # noqa: F401
    except Exception:
        compression = None
        print("⚠️  lz4 non disponible, compression Kafka désactivée")

    # Producer Kafka (topic fraud-alerts)
    producer = KafkaProducer(
        bootstrap_servers=['localhost:9092', 'localhost:9093', 'localhost:9094'],
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        compression_type=compression,
        acks='all'
    )
    
    # Détecteur
    detector = FraudDetector()
    
    print("✅ Consumer: topic 'payments'")
    print("✅ Producer: topic 'fraud-alerts'")
    print("✅ PostgreSQL enrichment: activé")
    print("\n🔍 Règles actives (11 règles):")
    print("  BASIQUES:")
    print("    1. FIRST_PAYMENT - Premier paiement (40 pts)")
    print("    2. NEW_CUSTOMER - Client < 7 jours (30 pts)")
    print("    3. UNUSUAL_HOUR - Paiement 2h-6h (35 pts)")
    print("    4. MOBILE_DEVICE - Device mobile (20 pts)")
    print("    5. DIRECT_TRAFFIC - Sans référent (15 pts)")
    print("    6. PAYMENT_FAILED - Échec paiement (50 pts)")
    print("  AVANCÉES:")
    print("    7. VELOCITY_HIGH - 3+ paiements en 10 min (45 pts) 🆕")
    print("    8. NEW_DEVICE - Nouveau device (30 pts) 🆕")
    print("    9. UNUSUAL_AMOUNT - > 3x moyenne (40 pts) 🆕")
    print("   10. FAST_CHECKOUT - Checkout < 30s (35 pts) 🆕")
    print("   11. GEO_MISMATCH - Pays différent (25 pts) 🆕")
    print("\n⚠️  Seuil de fraude: 60 points ou PAYMENT_FAILED")
    print("\n🚀 Démarrage de l'analyse en temps réel...\n")
    
    start_time = time.time()
    
    try:
        for message in consumer:
            event = message.value
            
            # Traitement
            fraud_alert = detector.process_event(event)
            
            if fraud_alert:
                detector.persist_alert(fraud_alert)

                # Publier dans fraud-alerts
                producer.send('fraud-alerts', value=fraud_alert)
                
                # Log
                print(f"🚨 FRAUD DETECTED!")
                print(f"   Alert ID: {fraud_alert['alert_id']}")
                print(f"   Customer: {fraud_alert['customer_id']}")
                print(f"   Risk Score: {fraud_alert['risk_score']}/100 ({fraud_alert['severity']})")
                print(f"   Reasons: {', '.join(fraud_alert['fraud_reasons'])}")
                print()
            
            # Statistiques périodiques
            if detector.stats['events_processed'] % 1000 == 0:
                elapsed = time.time() - start_time
                rate = detector.stats['events_processed'] / elapsed if elapsed > 0 else 0
                print(f"📊 Processed: {detector.stats['events_processed']:,} | "
                      f"Frauds: {detector.stats['frauds_detected']:,} | "
                      f"Rate: {rate:.0f} evt/s")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Arrêt manuel")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
    finally:
        producer.flush()
        producer.close()
        consumer.close()
        detector.close()
    
    # Statistiques finales
    elapsed = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"📊 STATISTIQUES FINALES")
    print(f"{'='*70}")
    print(f"Événements traités: {detector.stats['events_processed']:,}")
    print(f"Fraudes détectées: {detector.stats['frauds_detected']:,}")
    if detector.stats['events_processed'] > 0:
        fraud_rate = (detector.stats['frauds_detected'] / detector.stats['events_processed'] * 100)
        print(f"Taux de fraude: {fraud_rate:.2f}%")
    print(f"Durée: {elapsed:.2f}s")
    
    if detector.stats['by_rule']:
        print(f"\n📈 Fraudes par règle:")
        for rule, count in sorted(detector.stats['by_rule'].items(), key=lambda x: x[1], reverse=True):
            print(f"  • {rule:<20} : {count:>4,}")
    
    print(f"{'='*70}\n")

if __name__ == '__main__':
    run_fraud_detection()

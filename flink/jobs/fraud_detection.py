#!/usr/bin/env python3
"""
Job Flink - Détection de fraude en temps réel
Analyse les paiements depuis Kafka et détecte les patterns suspects
"""

import json
import importlib.util
import site
import sys
from datetime import datetime
from pathlib import Path
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaOffsetsInitializer, KafkaSink, KafkaRecordSerializationSchema
from pyflink.common import WatermarkStrategy, Types
from pyflink.common.serialization import SimpleStringSchema
from pyflink.datastream.functions import MapFunction, FilterFunction
import psycopg2


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

class PaymentEvent:
    """Classe représentant un événement de paiement"""
    def __init__(self, data):
        self.customer_id = data.get('customer_id')
        self.event_type = data.get('event_type')
        self.session_id = data.get('session_id')
        self.ts = data.get('ts')
        self.device = data.get('device')
        self.page_url = data.get('page_url')
        self.utm_source = data.get('utm_source')
        self.amount = data.get('amount', 0)  # Pourrait être enrichi
        self.country = data.get('country')  # Pourrait être enrichi

class EnrichWithPostgres(MapFunction):
    """
    Enrichit les événements avec des données PostgreSQL
    - Montant du panier (depuis orders/order_items)
    - Pays du client (depuis customers)
    - Historique paiements (depuis payments)
    """
    
    def open(self, runtime_context):
        # Connexion PostgreSQL
        self.conn = psycopg2.connect(
            host='localhost',
            port=5432,
            database='kivendtout',
            user='postgres',
            password='postgres'
        )
        self.cursor = self.conn.cursor()
    
    def map(self, value):
        try:
            event = json.loads(value)
            customer_id = event.get('customer_id')
            
            # Récupérer infos client
            self.cursor.execute("""
                SELECT country, created_at
                FROM customers
                WHERE customer_id = %s
            """, (customer_id,))
            
            customer_data = self.cursor.fetchone()
            if customer_data:
                event['customer_country'] = customer_data[0]
                event['customer_registration_date'] = str(customer_data[1])
            
            # Récupérer historique paiements
            self.cursor.execute("""
                SELECT COUNT(*), SUM(p.amount)
                FROM payments p
                JOIN orders o ON p.order_id = o.order_id
                WHERE o.customer_id = %s
            """, (customer_id,))
            
            payment_history = self.cursor.fetchone()
            if payment_history:
                event['previous_payments_count'] = payment_history[0] or 0
                event['previous_payments_total'] = float(payment_history[1] or 0)
            
            return json.dumps(event)
        
        except Exception as e:
            print(f"Erreur enrichissement: {e}")
            return value
    
    def close(self):
        if hasattr(self, 'cursor'):
            self.cursor.close()
        if hasattr(self, 'conn'):
            self.conn.close()

class FraudDetector(FilterFunction):
    """
    Détecte les patterns de fraude
    """
    
    def filter(self, value):
        try:
            event = json.loads(value)
            
            # RÈGLE 1: Premier paiement (customer nouveau)
            if event.get('previous_payments_count', 0) == 0:
                event['fraud_reason'] = 'FIRST_PAYMENT'
                event['risk_score'] = 50
                return True
            
            # RÈGLE 2: Heure inhabituelle (entre 2h et 5h du matin)
            try:
                ts = datetime.fromisoformat(event.get('ts', ''))
                hour = ts.hour
                if 2 <= hour <= 5:
                    event['fraud_reason'] = 'UNUSUAL_HOUR'
                    event['risk_score'] = 40
                    return True
            except:
                pass
            
            # RÈGLE 3: Device mobile + payment (plus risqué)
            device = event.get('device', '')
            if 'mobile' in device.lower() or device in ['ios', 'android']:
                if event.get('event_type') == 'payment_attempt':
                    event['fraud_reason'] = 'MOBILE_PAYMENT'
                    event['risk_score'] = 30
                    return True
            
            # RÈGLE 4: UTM source suspicious (direct sans referrer)
            utm_source = event.get('utm_source', '')
            if utm_source == 'direct' and event.get('event_type') == 'payment_attempt':
                event['fraud_reason'] = 'DIRECT_TRAFFIC'
                event['risk_score'] = 25
                return True
            
            return False
        
        except Exception as e:
            print(f"Erreur détection: {e}")
            return False

class AddAlertMetadata(MapFunction):
    """
    Ajoute des métadonnées aux alertes de fraude
    """
    
    def map(self, value):
        try:
            alert = json.loads(value)
            alert['alert_timestamp'] = datetime.now().isoformat()
            alert['alert_id'] = f"FRD_{alert.get('customer_id', 'UNKNOWN')}_{int(datetime.now().timestamp())}"
            alert['status'] = 'PENDING_REVIEW'
            return json.dumps(alert)
        except Exception as e:
            print(f"Erreur métadonnées: {e}")
            return value

def create_fraud_detection_job():
    """
    Crée le job Flink de détection de fraude
    """
    
    # Environment Flink
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(2)
    
    # Source Kafka - Topic payments
    kafka_source = KafkaSource.builder() \
        .set_bootstrap_servers('localhost:9092,localhost:9093,localhost:9094') \
        .set_topics('payments') \
        .set_group_id('flink-fraud-detector') \
        .set_starting_offsets(KafkaOffsetsInitializer.earliest()) \
        .set_value_only_deserializer(SimpleStringSchema()) \
        .build()
    
    # Stream principal
    payment_stream = env.from_source(
        kafka_source,
        WatermarkStrategy.no_watermarks(),
        "Kafka Payments Source"
    )
    
    # Pipeline de traitement
    fraud_alerts = payment_stream \
        .map(EnrichWithPostgres(), output_type=Types.STRING()) \
        .filter(FraudDetector()) \
        .map(AddAlertMetadata(), output_type=Types.STRING())
    
    # Sink Kafka - Topic fraud-alerts
    kafka_sink = KafkaSink.builder() \
        .set_bootstrap_servers('localhost:9092,localhost:9093,localhost:9094') \
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
                .set_topic('fraud-alerts')
                .set_value_serialization_schema(SimpleStringSchema())
                .build()
        ) \
        .build()
    
    fraud_alerts.sink_to(kafka_sink)
    
    # Affichage console (debug)
    fraud_alerts.print()
    
    # Exécution
    print("🚀 Démarrage du job de détection de fraude...")
    print("📊 Source: Kafka topic 'payments'")
    print("📤 Destination: Kafka topic 'fraud-alerts'")
    print("🔍 Règles actives: FIRST_PAYMENT, UNUSUAL_HOUR, MOBILE_PAYMENT, DIRECT_TRAFFIC")
    
    env.execute("KiVendTout - Fraud Detection")

if __name__ == '__main__':
    create_fraud_detection_job()

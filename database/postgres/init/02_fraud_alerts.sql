-- Script d'initialisation pour la table fraud_alerts

CREATE TABLE IF NOT EXISTS fraud_alerts (
    alert_id VARCHAR(100) PRIMARY KEY,
    alert_timestamp TIMESTAMP NOT NULL,
    event_timestamp TIMESTAMP,
    customer_id VARCHAR(20),
    session_id VARCHAR(50),
    event_type VARCHAR(50),
    device VARCHAR(50),
    utm_source VARCHAR(50),
    customer_country VARCHAR(10),
    previous_payments INT,
    is_new_customer BOOLEAN,
    fraud_reasons TEXT,
    risk_score INT,
    status VARCHAR(20) DEFAULT 'PENDING_REVIEW',
    severity VARCHAR(10),
    decision VARCHAR(20),
    decided_at TIMESTAMP,
    decided_by VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fraud_alerts_status ON fraud_alerts(status);
CREATE INDEX IF NOT EXISTS idx_fraud_alerts_severity ON fraud_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_fraud_alerts_customer ON fraud_alerts(customer_id);
CREATE INDEX IF NOT EXISTS idx_fraud_alerts_timestamp ON fraud_alerts(alert_timestamp);

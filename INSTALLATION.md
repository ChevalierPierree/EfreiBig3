# Installation

## Prerequis

- Docker Desktop ou Docker Engine avec `docker compose`
- Python `3.10+`
- `curl`
- `git`

Verification rapide:

```bash
docker --version
docker compose version
python3 --version
curl --version
git --version
```

## Installation locale

```bash
git clone -b V2 https://github.com/ChevalierPierree/EfreiBig3.git && cd EfreiBig3
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
chmod +x run.sh
```

## Demarrage recommande

### Option 1: bootstrap complet

```bash
./run.sh
```

Le script:
- demarre l'infrastructure Docker,
- charge les donnees de reference,
- lance l'API sur `8000`,
- lance le front sur `7600`.

### Option 2: verification et relance controles

```bash
bash scripts/checklist_and_launch.sh
```

## Services exposes

- API: `http://localhost:8000`
- Dashboard: `http://localhost:7600/index.html`
- Kafka UI: `http://localhost:8082`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`
- MinIO console: `http://localhost:9001`

## Verification apres installation

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/api/stats | jq '{total_alerts,fraud_rate,fraudulent_payments,total_payments}'
bash scripts/checklist_and_launch.sh
```

Resultat attendu:
- API `healthy`
- dashboards accessibles
- checklist `30/30 OK`

## Arret des services

```bash
docker compose down
```

Arret avec suppression des volumes locaux:

```bash
docker compose down -v
```

## Reinitialisation des donnees

Depuis l'API:

```bash
curl -X POST http://localhost:8000/api/system/reset-data \
  -H 'Content-Type: application/json' \
  --data-binary '{"confirm":true,"clear_runtime_artifacts":true,"stop_live_jobs":true}'
```

## Diagnostic rapide

```bash
tail -f logs/fraud_dashboard_api.log
tail -f logs/http_server.log
docker compose ps
```

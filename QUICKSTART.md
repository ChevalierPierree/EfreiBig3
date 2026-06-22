# Quickstart

## Sequence minimale

```bash
cd /Users/jeanmacario/Documents/GitHub/ProjetDataM1JeanPierre
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.patator.txt
./patator
```

## Verification

```bash
bash scripts/checklist_and_launch.sh
```

## Actions utiles

```bash
bash scripts/run_micro_batch.sh once
bash scripts/test_use_cases.sh
bash scripts/test_alert_notifications.sh
bash scripts/build_delivery_pack.sh
```

## URLs

- Overview: `http://localhost:7600/index.html`
- Fraude: `http://localhost:7600/fraud_dashboard.html`
- Typologies: `http://localhost:7600/fraud_types_dashboard.html`
- Identite: `http://localhost:7600/id_cards_dashboard.html`
- Transferts: `http://localhost:7600/transfer_kpi_dashboard.html`
- API health: `http://localhost:8000/health`

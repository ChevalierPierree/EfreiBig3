# Guide Patator

## Role du script

`patator` est le point d'entree shell pour lancer rapidement la plateforme complete.

Il prend en charge:
- le controle des prerequis,
- le demarrage de l'infrastructure Docker,
- le chargement des donnees,
- le lancement de l'API et du front,
- l'ouverture des URLs utiles.

## Utilisation

```bash
./patator
```

## Ce qu'il faut verifier apres execution

```bash
docker compose ps
curl -s http://localhost:8000/health
curl -I http://localhost:7600/index.html
```

## Suite recommandee

```bash
bash scripts/checklist_and_launch.sh
bash scripts/run_micro_batch.sh once
bash scripts/test_use_cases.sh
```

## Arret

```bash
docker compose down
```

## Logs utiles

```bash
tail -f logs/fraud_dashboard_api.log
tail -f logs/http_server.log
docker compose logs -f postgres
docker compose logs -f mongodb
```

## Cas de reprise rapide

Ports deja occupes:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:7600 -sTCP:LISTEN
kill <PID>
```

Redemarrage controle:

```bash
pkill -f 'api/fraud_dashboard_api.py' || true
bash scripts/checklist_and_launch.sh
```

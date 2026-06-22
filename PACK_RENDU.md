# Pack De Rendu Bloc 1

Le projet peut etre exporte dans un dossier de livraison autonome contenant:
- la documentation racine utile,
- les preuves d'execution,
- le code et la configuration necessaires au lancement.

Le pack est volontairement centre sur le Bloc 1:
- architecture de stockage et de traitement,
- API et streaming,
- Data Lake et analytics,
- preuves de qualite, charge et resilience.

## Commandes testees

### Demarrage

```bash
cd /Users/jeanmacario/Documents/GitHub/ProjetDataM1JeanPierre
source .venv/bin/activate
bash scripts/start.sh
```

### Verification complete

```bash
bash scripts/finalize_school_delivery.sh
bash scripts/checklist_and_launch.sh
```

### Validation

```bash
./.venv/bin/python scripts/validate_sujet1.py
./.venv/bin/python scripts/validate_perfect_compliance.py
```

### Generation du pack

```bash
bash scripts/build_delivery_pack.sh
```

## Contenu du dossier `delivery_pack/`

- `README_PACK.md`
- `MANIFEST.txt`
- `SHA256SUMS.txt` si `shasum` est disponible
- `docs/`
- `proofs/`
- `app/`

## Parcours recommande

1. `docs/README.md`
2. `docs/DEMO_PROJET.md`
3. `proofs/sujet1_validation_report.json`
4. `proofs/perfect_compliance_report.json`
5. `app/dashboard/index.html`

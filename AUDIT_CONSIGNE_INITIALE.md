# Audit Consigne Initiale - KiVendTout

Date audit: 25/02/2026

## 1) Demande auditée

Objectif demandé:
- disposer d'une API de commandes client "scalable",
- utiliser les `synthetic_id_cards` pour récupérer la date de naissance,
- bloquer les commandes de produits catégorie `Adult` pour les mineurs (< 18 ans),
- calculer l'âge à la date du jour.

## 2) Constat avant correction

Etat avant:
- API existante orientée fraude (`/api/alerts`, `/api/stats`) mais pas de checkout API.
- Pas de garde-fou majorité côté commande.
- Pas d'outil de charge pour simuler des commandes à volume.

Risque:
- non-conformité métier (mineur pouvant commander Adult),
- difficulte a demontrer la scalabilite API en presentation projet.

## 3) Correctifs livrés

### API commandes + contrôle d'âge

Fichier: `api/fraud_dashboard_api.py`

Nouveaux endpoints:
- `GET /api/products`
- `GET /api/id-cards`
- `POST /api/orders/checkout`

Règle appliquée:
- extraction de la date de naissance depuis les cartes synthétiques via le mapping `synthetic_id_labels.csv` associé aux `id.png`,
- calcul de l'âge avec `date.today()`,
- rejet HTTP 403 si `age < 18` et panier contenant un produit de catégorie `Adult`.

### Script de scaling API

Fichier: `scripts/scale_order_api.py`

Capacités:
- envoi concurrent de commandes vers `/api/orders/checkout`,
- mélange de profils majeurs/mineurs,
- mélange de produits Adult/non-Adult,
- vérification automatique qu'aucun cas `mineur + produit Adult` n'est accepté.

## 4) Validation technique effectuée

Tests réalisés:
- mineur + produit Adult -> HTTP 403 (bloqué),
- majeur + produit Adult -> commande acceptée,
- test de charge API:
  - `40` requêtes, concurrence `8`,
  - `27` acceptées, `13` bloquées mineur/adult,
  - `0` erreur HTTP/réseau,
  - `mineur+adult acceptés = 0`.

## 5) Ecart résiduel (mis à jour)

Etat actuel:
- une reconnaissance CNI basée empreinte image (SHA-256) est maintenant intégrée,
- fallback labels conservé pour robustesse.

Ecart restant:
- ce n'est pas un OCR texte "in-image" (MRZ/zone imprimée), mais une reconnaissance de carte sur dataset contrôlé.

Amélioration proposée (optionnelle):
- ajouter une brique OCR (Tesseract/OpenCV) en complément, avec fallback modèle+labels.

## 6) Commandes d'utilisation

Lancer l'API:

```bash
source .venv/bin/activate
python api/fraud_dashboard_api.py
```

Tester une commande bloquée (mineur + Adult):

```bash
curl -X POST 'http://localhost:8000/api/orders/checkout' \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"C00010","id_card_file":"id_0003.png","items":[{"product_id":7,"quantity":1}]}'
```

Tester la charge:

```bash
python scripts/scale_order_api.py --requests 200 --concurrency 20 --adult-order-ratio 0.6 --minor-ratio 0.4
```

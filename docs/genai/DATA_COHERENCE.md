# Audit de cohérence des données — KiVendTout

> Vérification programmatique des invariants entre endpoints, le 2026-06-23.
> Reproductible : `python3 docs/genai/tests/check_coherence.py`.
> **Conclusion : les données opérationnelles live sont cohérentes.** La seule
> divergence (audit V1, défaut #6) est une **juxtaposition temporelle**, pas une
> corruption — corrigée par un affichage daté.

## 1. Invariants internes — tous ✅

| Invariant vérifié | Résultat |
|---|---|
| Σ sévérités (Haute+Moyenne+Basse) == total_alerts | ✅ 5764 |
| taux_fraude == frauduleux / paiements × 100 | ✅ 12,27 % |
| couverture == clients_alertés / clients × 100 | ✅ 76,88 % |
| Σ alerts_by_day == total_alerts | ✅ 5764 |
| Σ alerts_by_hour == total_alerts | ✅ 5764 |
| `readable.alert_per_fraud_payment` == total / frauduleux | ✅ 23,62 |
| `readable.alert_to_payment_ratio` == total / paiements | ✅ 2,9 |
| Σ vérifications par statut == total_verifications | ✅ 1323 |
| Σ vérifications par méthode == total_verifications | ✅ 1323 |
| checkout total_attempts == méthode `checkout_guardrail` | ✅ 1263 |
| checkout acceptées + bloquées == tentatives | ✅ 1263 |
| produits adultes rejetés == commandes bloquées (âge) | ✅ 327 |
| par motif : haute + moyenne + basse == total | ✅ (aucun écart) |

`/api/kpis/readable` est **cohérent** avec `/api/stats` (mêmes totaux, ratios recalculés identiques).

## 2. Points qui *semblent* incohérents mais sont normaux

### a) Σ des motifs (13 669) > total alertes (5 764)
**Attendu.** Les motifs sont **non exclusifs** : un même paiement peut déclencher
plusieurs règles (FIRST_PAYMENT + MOBILE_DEVICE + …). L'API le documente
explicitement (`readable.fraud.interpretation`). → À l'écran : libellé « motifs non
exclusifs » (déjà fait en V2, page Typologies) et **jamais** présenter ces parts comme
un % du total qui sommerait à 100 %.

### b) Live (5 764 alertes) vs entrepôt analytics (2 211 alertes)
**Pas une contradiction : deux instantanés à deux dates.**

| Source | Alertes | Daté du | Nature |
|---|---|---|---|
| `/api/stats` (live) | **5 764** | 2026-06-23 | Flux opérationnel courant |
| `/api/analytics/status` (warehouse) | **2 211** | **2026-03-18** | Snapshot d'entrepôt figé |

L'entrepôt passe par ailleurs **ses propres** contrôles de cohérence : rapport
**PASS 9/9** (fact_fraud_alert 2211 == source opérationnelle 2211, etc.). Chaque source
est donc **interne­ment valide** ; elles ne sont simplement pas datées du même jour.
→ Correctif **présentation** : afficher la date de chaque source et ne pas comparer un
live à un snapshot gelé sans légende (l'écran Vue d'ensemble V2 lit désormais le statut
du rapport, plus `schema_exists`).

### c) Micro-batch : « 14 fenêtres actives » vs « 0 événement sur 24 h »
**Cohérent une fois daté.** « 14 fenêtres actives » est un **cumul historique**
(`/api/transfer/kpis`), tandis que `/api/micro-batch/stats?window_hours=24` ne regarde
que les **dernières 24 h** (où le dernier batch est `NO_EVENTS`). → V2 page Transferts
distingue déjà « historique » et « 24 h ».

### d) Vues « 24 h » vides quand l'horloge dépasse le jeu de démo
**Cause.** Plusieurs endpoints filtrent sur `alert_timestamp >= NOW() - 24h`
(`/api/fraud/reasons/stats`, `/api/checkout/stats`, `/api/payments/stats`…). Le jeu
de démo étant **figé** (22-23/06), dès que la date système dépasse +24 h, la fenêtre
24 h ne capte **plus rien** → motifs/blocages affichés à 0, alors que les données
existent (visibles en fenêtre large ou via `/api/stats`, non fenêtré).
**Correctif (frontend, juin 2025).** Les pages Typologies, Vue d'ensemble et Identité
demandent désormais `window_hours=720` (30 j, le maximum) et libellent « 30 j » au lieu
de « 24 h ». La page Transferts reste en l'état (micro-batch réellement vide, même en 720 h).

## 3. Verdict

- **Aucune donnée corrompue ni invariant violé.** Les chiffres sont fiables.
- Les « incohérences » de l'audit V1 étaient **temporelles / sémantiques** :
  sources figées à des dates différentes, motifs non exclusifs, fenêtres de temps
  implicites. **Toutes se règlent par l'affichage** (dater les sources, légender les
  fenêtres) — ce que la V2 a entamé.
- Impact sur l'assistant vocal : la narration s'ancre désormais sur
  `/api/kpis/readable` (chiffres + ratios **déjà** calculés et cohérents) → le modèle
  **reformule** sans recalculer, ce qui supprime les écarts (ex. l'ancien « 9 % »).

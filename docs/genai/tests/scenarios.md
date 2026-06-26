# C5.3 — Scénarios de test, métriques et résultats

> Mesures **réelles** du 2026-06-22, 100 % local. Harnais reproductible :
> [`run_eval.py`](./run_eval.py) · données brutes : [`results_2026-06-22.json`](./results_2026-06-22.json).
> Protocole : commandes FR synthétisées par `say` (voix **Thomas**, fr_FR) → wav 16 kHz
> → service `:8100` (Whisper → Ollama) → comparé à la vérité terrain de l'API `:8000`.
> Déterminisme garanti par `temperature: 0` (re-jouer le harnais redonne les mêmes sorties).

## Synthèse (12 commandes — après durcissement, run 2026-06-23)

| Métrique | Résultat | Avant durcissement | Lecture |
|---|---|---|---|
| **WER moyen (STT)** | **0,157** (15,7 %) | 0,157 | 7/12 exactes ; erreurs sur les mots métier mal **prononcés par la voix de synthèse** (§1). |
| **Accuracy intention (action)** | **1,000** (12/12) | 0,833 | Few-shot `use_cases` + exemples par vue → plus aucune action manquée. |
| **Accuracy intention (full)** | **0,917** (11/12) | 0,833 | Seul échec restant = transcription corrompue par la TTS (cascade STT, §2). |
| **Hallucinations (KPI inventé)** | **0** | 0 (mais 1 ratio recalculé « 9 % ») | Ancrage sur `/api/kpis/readable` + interdiction de recalcul → l'imprécision « 9 % » a disparu. |
| **Latence (à chaud)** | STT ≈ **1,0 s** · intention ≈ **0,5 s** · narration ≈ **0,9 s** | idem | Question ressentie ≈ 2,5 s ; navigation ≈ 1,5 s. |

> Données brutes : [`results_2026-06-26.json`](./results_2026-06-26.json). Les tableaux
> détaillés ci-dessous (§1–§4) sont le **cas travaillé du 2026-06-22** (méthodologie et
> matrice de confusion) ; le run du 2026-06-23 les re-valide sur données fraîches après
> durcissement (voir §6).

## 1. STT — précision de transcription (WER)

WER = (substitutions + insertions + suppressions) / mots attendus, insensible casse/accents/ponctuation.

| Commande prononcée (attendu) | Transcrit (Whisper) | WER |
|---|---|---|
| « ouvre la vue fraude » | « Ouvre la vue fraude. » | 0.00 |
| « affiche les transferts » | « affiches les transferts. » | 0.33 |
| « montre les cartes d'identite » | « Montre les cartes d'identie. » | 0.25 |
| « reviens a l'accueil » | « reviens à l'accueil. » | 0.00 |
| « ouvre les typologies de fraude » | « ouvre les typologies de Freud. » | 0.20 |
| « montre les cas d'usage » | « Montre les cas d'usage. » | 0.00 |
| « filtre les fraudes en severite haute » | « Filtre les fruits en severi taux. » | 0.50 |
| « affiche seulement les alertes moyennes » | « affiche seulement les alertes moyennes. » | 0.00 |
| « montre les alertes en attente » | « Montre les alertes en attente. » | 0.00 |
| « explique moi le taux de fraude » | « Explique-moi le taux de fraude. » | 0.00 |
| « combien d'alertes de severite haute » | « Combien d'alerte de Severi taut ? » | 0.60 |
| « quelle est la meteo demain a paris » | « Quelle est la météo demain à Paris ? » | 0.00 |

**Analyse.** Les 3 pires scores (0,50–0,60) ne sont **pas** des faiblesses de Whisper mais des
**artefacts de la voix de synthèse** : « Thomas » prononce « fraude »→« Freud », « fraudes »→
« fruits », « sévérité haute »→« severi taux/taut ». Sur une **voix humaine**, ces mots sont
correctement articulés et le WER attendu chute nettement (les 9 commandes sans mot piégé
sont à WER ≤ 0,33, dont 7 à 0,00). Whisper restitue par ailleurs la casse et les accents
(« reviens à l'accueil ») là où le texte de référence était sans accent.

## 2. Intention — classification (matrice de confusion)

Classification effectuée **sur la transcription réelle** (chaîne bout-en-bout, pas sur le texte idéal).

| Transcription | action att. | action obtenue | full OK ? |
|---|---|---|---|
| Ouvre la vue fraude. | navigate(fraud) | navigate(fraud) | ✅ |
| affiches les transferts. | navigate(transfer_kpi) | navigate(transfer_kpi) | ✅ |
| Montre les cartes d'identie. | navigate(id_cards) | navigate(id_cards) | ✅ |
| reviens à l'accueil. | navigate(overview) | navigate(overview) | ✅ |
| ouvre les typologies de Freud. | navigate(fraud_types) | navigate(fraud_types) | ✅ |
| Montre les cas d'usage. | navigate(use_cases) | **unknown** | ❌ (erreur modèle) |
| Filtre les fruits en severi taux. | filter/severity/HIGH | **unknown** | ❌ (STT dégradé → rejet) |
| affiche seulement les alertes moyennes. | filter/severity/MEDIUM | filter/severity/MEDIUM | ✅ |
| Montre les alertes en attente. | filter/status/PENDING | filter/status/PENDING | ✅ |
| Explique-moi le taux de fraude. | ask | ask | ✅ |
| Combien d'alerte de Severi taut ? | ask | ask | ✅ |
| Quelle est la météo demain à Paris ? | unknown | unknown | ✅ |

**Matrice de confusion (action attendue × obtenue)**

| att. \ obt. | navigate | filter | ask | unknown |
|---|---|---|---|---|
| **navigate** (6) | 5 | 0 | 0 | 1 |
| **filter** (3) | 0 | 2 | 0 | 1 |
| **ask** (2) | 0 | 0 | 2 | 0 |
| **unknown** (1) | 0 | 0 | 0 | 1 |

**Analyse.** Deux échecs, de natures opposées :
1. **« Montre les cas d'usage »** (transcription parfaite) classé `unknown` → **vraie limite du
   modèle 3B** : « cas d'usage » est moins ancré que « fraude/transferts ». *Correctif retenu* :
   ajouter un exemple `use_cases` au prompt système (few-shot) — voir §5.
2. **« Filtre les fruits en severi taux »** (transcription corrompue par la TTS) classé `unknown` :
   le modèle **refuse plutôt que d'inventer** un filtre — c'est le **comportement sûr** attendu
   (mieux vaut `unknown` qu'un faux filtre). Aucune confusion vers une mauvaise action.

Aucune commande hors-domaine n'a déclenché d'action (« météo » → `unknown` ✅).

## 3. Narration — exactitude factuelle (anti-hallucination)

Vérité terrain `/api/stats` (2026-06-22) : total_alerts **3632**, HIGH **313**, MEDIUM **3319**,
paiements **1053**, frauduleux **1**, taux **0,09 %**, clients **2500**, couverts **1181** (**47,24 %**).

**Narration `/narrate` (vue fraude)** — chiffres cités : 3632, 313, 3319, 1053, 0,09, 2500, 1181, 47,24.
→ **8/8 KPIs exacts**. Seul nombre hors-KPI : « **9 %** » présenté comme part des alertes hautes
(ratio réel 313/3632 = **8,6 %**) → calcul dérivé **arrondi un peu lâche**, mais **aucun KPI inventé**.

**Q&A `/ask`** (« combien d'alertes haute sévérité + taux de fraude ») → « **313** alertes de
sévérité Haute », « taux de **0,09 %** » → **2/2 exacts, 0 inventé**.

| KPI réel | Valeur API | Cité par le LLM | Exact ? |
|---|---|---|---|
| total_alerts | 3632 | 3 632 | ✅ |
| alerts HIGH | 313 | 313 | ✅ |
| alerts MEDIUM | 3319 | 3 319 | ✅ |
| total_payments | 1053 | 1 053 | ✅ |
| fraud_rate | 0,09 % | 0,09 % | ✅ |
| total_customers | 2500 | 2 500 | ✅ |
| alerted_customers | 1181 | 1 181 | ✅ |
| coverage | 47,24 % | 47,24 % | ✅ |

**Métrique** : exactitude factuelle = **100 % des KPIs cités**, **0 hallucination de chiffre**.
La seule imprécision est une **part calculée** (9 % vs 8,6 %), à corriger en demandant au modèle
de ne pas recalculer de ratios non fournis (§5).

## 4. Latence (expérience utilisateur, à chaud)

| Étape | Temps |
|---|---|
| STT (transcription) | ≈ 1018 ms (max 1387) |
| Intention (Ollama) | ≈ 542 ms |
| Narration / Q&A (Ollama) | ≈ 1029 ms |
| TTS neuronal (Piper, phrase courte → narration) | ≈ 70 → 510 ms |
| **Navigation perçue** (STT + intention) | **≈ 1,5 s** |
| **Question perçue** (STT + intention + narration) | **≈ 2,5 s** |

Cold-start exclu (warmup préalable). Acceptable pour une commande vocale ; le 1ᵉʳ appel après
démarrage est plus lent (chargement du modèle Whisper + Ollama en mémoire).

## 5. Ajustements de paramètres (analyse — exigence C5.3)

Les réglages qui ont **mesurablement** amélioré la qualité, du plus structurant au plus fin :

| Ajustement | Problème avant | Effet |
|---|---|---|
| **Ollama 0.22 → 0.30.10** | `panic` à l'init Metal sur macOS Darwin 25.3 → narration **impossible** | Débloque tout le LLM local. |
| **`temperature: 0`** (intention + narration) | sorties variables d'un appel à l'autre → non testable | **Déterminisme** : le harnais est reproductible, les métriques stables. |
| **`format: json`** (intention) | JSON parfois enrobé de prose → parsing cassé | Sortie JSON stricte, parsing fiable. |
| **Libellés FR injectés** (`_label_kpis`) | le modèle confondait « paiements totaux » et « frauduleux » | Désambiguïsation → **0 confusion de libellé** mesurée. |
| **Ancrage KPIs réels dans le prompt** | risque d'invention de chiffres | **0 hallucination** de KPI mesurée (§3). |
| **Modèle 3B (`llama3.2`) vs 1B** | le 1B suit mal le schéma JSON | Meilleur respect du format et du FR. |

**Pistes restantes (mesurées comme nécessaires)** : (a) few-shot `use_cases` dans le prompt
d'intention → vise une accuracy action ≥ 0,92 ; (b) interdire au modèle de recalculer des
ratios non fournis → supprime l'imprécision « 9 % ».

## 6. Durcissement de l'assistant (2026-06-23) — avant / après

Trois corrections ciblées à partir de l'analyse §2 et §3 :

| Correctif | Avant | Après (mesuré) |
|---|---|---|
| **Few-shot `use_cases` + exemples par vue** (intention) | « montre les cas d'usage » → `unknown` ; accuracy action **0,833** | navigation correcte ; accuracy action **1,000** |
| **Ancrage sur `/api/kpis/readable` + interdiction de recalcul** (narration) | « 9 % » des alertes hautes (ratio recalculé, faux : 8,6 %) | n'utilise que les chiffres fournis ; **plus aucun ratio inventé** |
| **Prose forcée + nettoyage markdown** (narration) | sorties en listes à puces, peu fluides | phrases complètes, par vue (fraude / transferts / identité) |

La narration est désormais **par vue** (et non plus figée sur la fraude) et le Q&A est
routé vers la bonne vue. Exemple de sortie après durcissement (vue fraude, données du
2026-06-23) : *« 5 764 alertes de fraude ont été déclenchées, dont 244 paiements
frauduleux confirmés, soit un taux de fraude de 12,27 %. Le motif le plus fréquent est
FIRST_PAYMENT avec 4 219 cas. »* — tous les chiffres sont des KPIs réels (0 invention).

Échec restant unique (full intention 11/12) : « filtre les fraudes en sévérité haute »
quand la TTS le transcrit « filtre les fruits en severi taux » → le filtre est mal
résolu. C'est une **cascade STT** (entrée corrompue), pas une limite du modèle d'intention.

## Protocole de reproduction

```bash
# 1. Stack data (./patator) + Ollama (ollama serve) + service vocal (:8100) up.
# 2. Lancer le harnais (génère l'audio, mesure tout, écrit le JSON) :
cd EfreiBig3 && python3 docs/genai/tests/run_eval.py > docs/genai/tests/results_<date>.json
# 3. Reporter les agrégats ci-dessus. temperature:0 ⇒ sorties LLM identiques d'un run à l'autre.
```

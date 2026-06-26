# Rapport atelier IA générative — KiVendTout (Bloc C5)

> Livrable : rapport écrit détaillant **étapes réalisées**, **choix
> méthodologiques** et **résultats obtenus**. À compléter au fil du projet.

## C5.1 — Cas d'usage de l'IA générative

### Les 3 axes envisagés (B2B + B2C)

1. **Navigation & action vocales (STT)** — piloter ET agir sur le dashboard à la voix.
   *Minimum imposé* (accessibilité du VP). B2C : mains-libres, inclusion. Au-delà de la
   navigation/filtrage, l'assistant **exécute des décisions** sur les alertes de fraude
   (approuver / bloquer / investiguer) avec **confirmation humaine obligatoire** avant
   chaque action.
2. **Narration générative des KPIs** — résumé en langage naturel des chiffres de
   fraude. B2B : rapports exécutifs. B2C : vulgarisation.
3. **Q&A en langage naturel** — questions libres sur les données. B2B : self-service.

### Adapter le front à la voix (accessibilité universelle + concertation IT/UX)

Un enseignement clé : **une UI pensée pour la souris n'est pas pilotable à la voix**.
Les identifiants techniques d'alerte (`FRD_PAY_2229_50D1BD`) sont imprononçables et
inaudibles. On a donc introduit un **identifiant court `#N`** (numéro de position dans la
file), **visible à l'écran** : il sert de repère commun à l'œil et à la voix
(« approuve l'alerte numéro 3 »), l'identifiant long restant affiché pour la traçabilité.
C'est l'illustration concrète de l'« accessibilité universelle » et de la « concertation
IT » du référentiel : le design de l'interface est revu pour que **souris et voix pilotent
exactement les mêmes objets** (contrat `window.KVFraud`), avec un **garde-fou de
confirmation** (le bot décrit la cible — client, sévérité — et attend « oui »/« non »).

### Convergence

Les 3 axes partagent **la couche de compréhension d'intention (NLU)**. La voix
alimente la narration et le Q&A : `audio → texte → intention → action | génération`.

### Axes écartés (et pourquoi)

- Génération d'images / données synthétiques : aucune valeur pour un dashboard de
  fraude (le dataset est déjà fourni).
- Chatbot généraliste : risque d'hallucination sur des chiffres réglementaires.

## C5.2 — Solution développée

Voir [ARGUMENTAIRE_LOCAL_VS_API.md](./ARGUMENTAIRE_LOCAL_VS_API.md).

- **Foundation model / LLM** : Llama 3.2 via Ollama (local ; modèle interchangeable
  via `OLLAMA_MODEL`, repli `llama3.2` 3B plus rapide).
- **Accessibilité universelle** : navigation et narration vocales (VP sans bras).
- **Architecture** : voir [README.md](./README.md). Service découplé sur :8100.

### Étapes réalisées
- [x] Architecture découplée (STT / NLU / narration / TTS)
- [x] Services Python + service FastAPI :8100
- [x] Widget vocal navigateur (micro + TTS, push-to-talk `P`)
- [x] Test end-to-end mesuré (Whisper + Ollama) — voir [tests/scenarios.md](./tests/scenarios.md)
- [x] Ajustement des paramètres (temperature 0, format JSON, ancrage KPIs, Ollama ≥ 0.30)

### Choix méthodologiques
- STT local (faster-whisper) pour la confidentialité et l'exigence du VP.
- Sortie d'intention contrainte en JSON (fiabilité du parsing).
- KPIs réels injectés dans le prompt de narration (garde-fou anti-hallucination).

## C5.3 — Évaluation de la qualité

Voir [tests/scenarios.md](./tests/scenarios.md) pour le détail, la matrice de
confusion et le protocole reproductible. Métriques : WER (STT), accuracy
d'intention, exactitude factuelle de la narration (chiffre cité == KPI réel),
latence.

### Résultats obtenus (12 commandes, 100 % local — après durcissement 2026-06-23)

| Métrique | Résultat | Avant durcissement |
|---|---|---|
| WER moyen (STT) | **0,157** — 7/12 exactes | 0,157 |
| Accuracy intention (action) | **1,000** (12/12) | 0,833 |
| Accuracy intention (full `{action,view,field,value}`) | **0,917** (11/12) | 0,833 |
| **Hallucinations (KPI inventé)** | **0** sur narration + Q&A | 0 (mais 1 ratio recalculé) |
| Latence à chaud (STT / intention / narration) | ≈ **1,0 / 0,5 / 0,9 s** | idem |

**Analyse.** L'exactitude factuelle est l'objectif clé (données de fraude
réglementaires) et il est **atteint : 0 chiffre inventé** — l'ancrage des KPIs
réels dans le prompt fonctionne. Les erreurs de WER élevées sont des **artefacts
de la voix de synthèse** (mots métier mal prononcés), pas des faiblesses de
Whisper ; une voix humaine réduit le WER. Après **durcissement** (few-shot
`use_cases`, ancrage sur `/api/kpis/readable`, interdiction de recalcul, prose
forcée), l'accuracy d'intention passe à **100 % en action** et le ratio recalculé
erroné (« 9 % ») disparaît ; le seul échec restant est une **cascade STT** (entrée
corrompue par la voix de synthèse), pas une limite du modèle. Ajustements décisifs :
`temperature: 0` (déterminisme/testabilité), `format: json` (parsing fiable),
libellés FR + KPIs réels injectés (0 hallucination), upgrade Ollama ≥ 0.30
(débloque le LLM local sur macOS).

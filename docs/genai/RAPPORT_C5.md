# Rapport atelier IA générative — KiVendTout (Bloc C5)

> Livrable : rapport écrit détaillant **étapes réalisées**, **choix
> méthodologiques** et **résultats obtenus**. À compléter au fil du projet.

## C5.1 — Cas d'usage de l'IA générative

### Les 3 axes envisagés (B2B + B2C)

1. **Navigation vocale (STT)** — piloter le dashboard à la voix. *Minimum imposé*
   (accessibilité du VP). B2C : mains-libres, inclusion.
2. **Narration générative des KPIs** — résumé en langage naturel des chiffres de
   fraude. B2B : rapports exécutifs. B2C : vulgarisation.
3. **Q&A en langage naturel** — questions libres sur les données. B2B : self-service.

### Convergence

Les 3 axes partagent **la couche de compréhension d'intention (NLU)**. La voix
alimente la narration et le Q&A : `audio → texte → intention → action | génération`.

### Axes écartés (et pourquoi)

- Génération d'images / données synthétiques : aucune valeur pour un dashboard de
  fraude (le dataset est déjà fourni).
- Chatbot généraliste : risque d'hallucination sur des chiffres réglementaires.

## C5.2 — Solution développée

Voir [ARGUMENTAIRE_LOCAL_VS_API.md](./ARGUMENTAIRE_LOCAL_VS_API.md).

- **Foundation model / LLM** : llama3.2 via Ollama (local).
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

### Résultats obtenus (mesure du 2026-06-22, 12 commandes, 100 % local)

| Métrique | Résultat |
|---|---|
| WER moyen (STT) | **0,157** — 7/12 transcriptions exactes |
| Accuracy intention (action) | **0,833** (10/12) |
| Accuracy intention (full `{action,view,field,value}`) | **0,833** (10/12) |
| **Hallucinations (KPI inventé)** | **0** sur narration + Q&A |
| Latence à chaud (STT / intention / narration) | ≈ **1,0 / 0,5 / 1,0 s** |

**Analyse.** L'exactitude factuelle est l'objectif clé (données de fraude
réglementaires) et il est **atteint : 0 chiffre inventé** — l'ancrage des KPIs
réels dans le prompt fonctionne. Les erreurs de WER élevées sont des **artefacts
de la voix de synthèse** (mots métier mal prononcés), pas des faiblesses de
Whisper ; une voix humaine réduit le WER. Une seule **vraie** erreur d'intention
(« cas d'usage » classé `unknown`), corrigeable par un exemple few-shot ;
l'autre échec est un **rejet sûr** (`unknown`) sur une transcription corrompue —
le modèle refuse plutôt que d'inventer un filtre. Ajustements décisifs :
`temperature: 0` (déterminisme/testabilité), `format: json` (parsing fiable),
libellés FR + KPIs réels injectés (0 hallucination), upgrade Ollama ≥ 0.30
(débloque le LLM local sur macOS).

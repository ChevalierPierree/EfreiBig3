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
- [x] Widget vocal navigateur (micro + TTS)
- [ ] Test end-to-end (Whisper + Ollama lancés)
- [ ] Ajustement du modèle de narration

### Choix méthodologiques
- STT local (faster-whisper) pour la confidentialité et l'exigence du VP.
- Sortie d'intention contrainte en JSON (fiabilité du parsing).
- KPIs réels injectés dans le prompt de narration (garde-fou anti-hallucination).

## C5.3 — Évaluation de la qualité

Voir [tests/scenarios.md](./tests/scenarios.md). Métriques : WER (STT),
accuracy d'intention (matrice de confusion), exactitude factuelle de la narration
(chiffre cité == KPI réel de l'API), latence.

### Résultats obtenus
*(à remplir après les tests)*

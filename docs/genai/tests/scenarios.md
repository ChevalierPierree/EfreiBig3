# C5.3 — Scénarios de test et métriques

## 1. STT — précision de transcription (WER)

Enregistrer N commandes vocales, comparer la transcription au texte attendu.

| # | Commande prononcée (attendu) | Transcrit | Correct ? |
|---|---|---|---|
| 1 | « ouvre la vue fraude » | | |
| 2 | « affiche les transferts » | | |
| 3 | « explique-moi le taux de fraude » | | |
| 4 | « montre les cartes d'identité » | | |
| 5 | « reviens à l'accueil » | | |

**Métrique** : WER = (substitutions + insertions + suppressions) / mots attendus.

## 2. Intention — classification (matrice de confusion)

Pour chaque transcription, vérifier `{action, view}` renvoyé par Ollama.

| Commande | action attendue | view attendue | action obtenue | view obtenue | OK ? |
|---|---|---|---|---|---|
| « ouvre la fraude » | navigate | fraud | | | |
| « explique le taux de fraude » | explain | fraud | | | |
| « affiche les transferts » | navigate | transfer_kpi | | | |
| « blabla incompréhensible » | unknown | null | | | |

**Métrique** : accuracy = bonnes classifications / total. Matrice de confusion
action × action et view × view.

## 3. Narration — exactitude factuelle (anti-hallucination)

Comparer chaque chiffre cité dans la narration au KPI réel de l'API.

| KPI réel (API :8000) | Valeur API | Valeur citée par le LLM | Exact ? |
|---|---|---|---|
| total_alerts | | | |
| fraud_rate | | | |
| total_customers | | | |

**Métriques** : taux d'exactitude factuelle ; nombre de chiffres inventés
(hallucinations) — objectif **0**.

## 4. Latence (expérience utilisateur)

| Étape | Temps (ms) |
|---|---|
| STT (transcription) | |
| Intention (Ollama) | |
| Narration (Ollama) | |
| **Total perçu** | |

## Protocole

1. Lancer la stack data (`./patator`), Ollama (`ollama serve`), le service vocal.
2. Rejouer les commandes ci-dessus via le bouton 🎙️ (ou en POST direct sur :8100).
3. Remplir les tableaux, calculer les métriques, consigner dans RAPPORT_C5.md (C5.3).

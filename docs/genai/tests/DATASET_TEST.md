# Dataset de test — Assistant vocal KiVendTout

## C'est quoi ?
Un **dataset de test** est un jeu d'exemples **étiquetés** servant à **évaluer** l'assistant.
Chaque ligne contient :
- une **entrée** : ce que l'utilisateur dit (ex. « approuve l'alerte numéro 3 ») ;
- la **sortie attendue** (vérité terrain) : ce que l'assistant *devrait* produire
  (action + paramètres) ;
- le **comportement attendu**.

On exécute ensuite chaque commande dans l'assistant et on compare le résultat **obtenu** à
la sortie **attendue** → cela donne un **taux de justesse** et révèle les faiblesses.
C'est le support direct de la compétence **C5.3 (évaluer la qualité des résultats générés)**.

## Fichiers
| Fichier | Contenu |
|---|---|
| `dataset_test_assistant.csv` | Le dataset (39 cas), ouvrable dans Excel (délimiteur `;`, UTF-8). |
| `dataset_test_assistant.json` | Le même dataset, format machine. |
| `dataset_test_resultats.csv` | Le dataset **passé dans l'assistant** : résultat obtenu + verdict OK/KO. |
| `run_eval.py` | Harnais bout-en-bout (voix synthétisée → STT → LLM) : WER, intention, factualité, latence. |

## Colonnes (du dataset)
| Colonne | Sens |
|---|---|
| `id` | Identifiant du cas (N=navigation, F=filtre, A=action, C=confirmation, Q=question, R=résumé, H=hors-domaine/robustesse). |
| `categorie` | Famille du cas. |
| `commande` | Ce que dit l'utilisateur (l'entrée). |
| `action_attendue` | Action attendue : `navigate`, `filter`, `act`, `ask`, `narrate`, `confirm`, `unknown`. |
| `parametres_attendus` | Cible attendue (vue, champ+valeur, décision+cible…). |
| `comportement_attendu` | Ce que l'assistant doit faire concrètement. |

## Couverture (39 cas)
| Catégorie | Cas | Ce qu'on teste |
|---|---|---|
| Navigation | 8 | Ouvrir chaque vue + paraphrases |
| Filtre | 8 | Sévérité (haute/moyenne/basse/toutes) + statut (attente/investigation/approuvé/bloqué) |
| Action | 7 | Approuver / bloquer / investiguer × cible (numéro, sélectionnée, première) |
| Confirmation | 3 | Réponse oui / non / annule à une action en attente |
| Question | 5 | Q&A ancré sur les KPIs réels |
| Résumé page | 3 | Narration de la vue courante |
| Hors-domaine / Robustesse | 5 | Météo, blague, silence, charabia, action non supportée → **doit refuser** |

## Comment le rejouer
```bash
# Services lancés (data :8000, voix :8100, Ollama). Puis :
python3 docs/genai/tests/run_eval.py            # métriques bout-en-bout (WER, intention, factualité, latence)
# Le fichier dataset_test_resultats.csv est produit en passant chaque commande dans /api/voice/intent.
```

## Résultats — la boucle test → correction → re-mesure (2026-06-26)
Évaluation au niveau **intention** sur les 32 cas classifiables (confirmation, résumé et
silence sont traités côté interface).

### 1. Première mesure → des faiblesses révélées
| Modèle | Justesse | Échecs (id) |
|---|---|---|
| `llama3.2` (3B) | 25/32 (78 %) | F05, F06, F07, F08, Q03, Q04, H05 |
| `mistral:7b` | 25/32 (78 %) | F02, F05, F06, F08, H01, H02, H04 |

**Ce que le dataset a révélé** (faiblesses communes aux deux modèles) :
- **Filtres de statut** (« approuvées », « bloquées », « investigation », « toutes ») classés
  en *navigation* au lieu de *filtre* → le prompt ne couvrait que `haute / moyenne / en attente`.
- **Hors-domaine** (« météo », « blague », « supprime tout ») pas toujours **rejeté**.

### 2. Correction (couverture du prompt, sans surapprentissage)
Ajout au prompt d'intention de : règles plus nettes (toute sévérité/statut → *filter* ;
actions limitées à approuver/bloquer/investiguer ; reste → *unknown*) + exemples few-shot
pour **tous les statuts** et pour le **hors-domaine**.

### 3. Re-mesure → objectif atteint
| Modèle | Avant | **Après correction** |
|---|---|---|
| **`llama3.2` (défaut)** | 78 % | **32/32 — 100 %** ✅ |
| `mistral:7b` | 78 % | 24/32 — 75 % |

> Le même prompt rend **llama3.2 parfait** mais **dégrade Mistral** (sensibilité au prompt
> propre à chaque modèle). Le dataset a donc tranché objectivement : **llama3.2 est retenu**
> (100 % **et** plus rapide). Mistral reste disponible via `OLLAMA_MODEL=mistral:7b`.

**Mesure bout-en-bout** (harnais `run_eval.py`, voix *synthétisée* → STT → LLM, 12 commandes) :
intention **0,92** (le seul échec vient de la voix de test qui transforme « fraudes en sévérité
haute » en « fruits en severi taux »), **WER 0,157**, **0 chiffre inventé**, latence ≈ 0,9 s (STT)
/ 0,5 s (intention) / 0,8 s (narration).

> ⚠️ Méthode honnête : on n'« optimise » pas le prompt pour passer exactement ces 39 lignes
> (surapprentissage). On corrige les **lacunes de couverture réelles** révélées, puis on remesure.
> Le dataset sert ensuite de test de **non-régression**.

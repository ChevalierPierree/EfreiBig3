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

## Résultats observés (2026-06-26)
Évaluation au niveau **intention** sur les 32 cas classifiables (les cas de confirmation,
de résumé et de silence sont traités côté interface) :

| Modèle | Justesse | Échecs (id) |
|---|---|---|
| `mistral:7b` (défaut) | **25/32 (78 %)** | F02, F05, F06, F08, H01, H02, H04 |
| `llama3.2` (3B) | **25/32 (78 %)** | F05, F06, F07, F08, Q03, Q04, H05 |

> À comparer au sous-ensemble « commandes claires » (les 7 cas de base), où les deux modèles
> font **7/7**. Le dataset élargi est volontairement **plus discriminant**.

### Analyse — ce que le dataset a révélé
1. **Filtres de statut** (« approuvées », « bloquées », « investigation », « toutes ») :
   souvent classés en *navigation* au lieu de *filtre*. **Cause** : le prompt d'intention ne
   contient des exemples que pour `haute / moyenne / en attente` → couverture incomplète.
   **Faiblesse systématique** (présente sur les deux modèles).
2. **Hors-domaine** (« météo », « blague », charabia) : parfois routé en *question* ou
   *navigation* au lieu d'être **rejeté** (`unknown`). **Cause** : manque d'un exemple
   explicite « hors périmètre → unknown ».
3. Les **navigations, actions et questions principales** passent de façon fiable.

### Pistes d'amélioration (identifiées PAR le dataset)
- Ajouter au prompt d'intention des **exemples few-shot** pour chaque statut et un exemple
  **hors-domaine → unknown** → objectif > 90 %.
- Re-mesurer après correction (le dataset sert alors de **non-régression**).

> ⚠️ Important : on n'« optimise » pas le prompt pour passer exactement ces lignes (ce serait
> du surapprentissage). On corrige les **lacunes de couverture réelles** que le dataset met en
> évidence, puis on remesure.

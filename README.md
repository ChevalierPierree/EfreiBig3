# KiVendTout V2 — plateforme data + assistant vocal IA

Cette branche reprend la plateforme data **KiVendTout** (détection de fraude e-commerce, Bloc 1) et lui ajoute une **couche d'IA générative** : un assistant vocal **100 % local** pour piloter le dashboard de fraude à la voix.

C'est le support du **projet IA générative (Bloc 2, compétences C5.1 à C5.3)** du RNCP40875.

Projet réalisé en binôme : **Pierre Chevalier** et **Jean Macario**.

## Pourquoi un assistant vocal

Le besoin de départ est concret : un responsable privé de l'usage de ses bras ne peut plus se servir d'une souris ni d'un clavier. La voix rouvre l'outil à toute personne empêchée d'utiliser souris et clavier. Et comme on manipule des données de fraude sensibles, **tout tourne en local** — rien ne sort de la machine.

## Comment ça marche

```
🎙️  Micro (navigateur)
      │  POST /api/voice/command
      ▼
   STT local        faster-whisper            (api/voice/stt_service.py)
      ▼
   Intention        Llama 3.2 via Ollama (JSON, température 0)   (intent_service.py)
      ├─ naviguer / filtrer → le dashboard change de vue
      └─ raconter           → narration des KPIs réels lus sur l'API :8000
      ▼                                        (narrate_service.py)
   TTS local        Piper (voix neuronale)     (tts_service.py)
```

- Le service vocal est **autonome sur le port 8100**, découplé du cœur data (`:8000`) et du dashboard (`:7600`) — on ne touche pas à l'existant.
- Les actions sensibles (approuver / bloquer une alerte) demandent une **confirmation humaine** avant exécution.
- La narration est **ancrée sur les vrais KPIs** de l'API : le modèle n'invente aucun chiffre.

Le choix de **Llama 3.2** (et non Mistral 7B) a été décidé **par la mesure**, pas par intuition — voir l'évaluation ci-dessous.

## Lancer

### 1. La plateforme data (comme en Bloc 1)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./run.sh          # Docker + API :8000 + dashboards :7600
```

### 2. La couche vocale

```bash
pip install -r requirements.voice.txt

# Ollama (LLM local)
ollama serve
ollama pull llama3.2

# Modèle de voix Piper (~60 Mo, non versionné) — voir api/voice/tts_service.py
# puis on lance le service vocal :
uvicorn api.voice.voice_app:app --host 0.0.0.0 --port 8100
```

Ouvrir ensuite le dashboard de fraude (`:7600`) et maintenir la touche **P** pour parler.
Exemple : *« approuve l'alerte numéro 1 »*, *« montre-moi les alertes critiques »*, *« fais-moi un résumé »*.

## Évaluation (C5.3)

Le projet est évalué sur un **jeu de test de 32 commandes** étiquetées (navigation, filtres, actions, questions, hors-domaine) :

| Indicateur | Résultat |
|---|---|
| Compréhension d'intention (dataset 32 cas) | **100 %** |
| WER (transcription vocale) | **0,157** |
| Chiffres inventés par la narration | **0** |
| Latence bout-en-bout | **≈ 2,5 s** |

Llama 3.2 : 32/32 · Mistral 7B : 24/32 → Llama 3.2 retenu (meilleur **et** plus rapide).
Le protocole est reproductible : `docs/genai/tests/run_eval.py`.

## Les livrables IA générative

Tout est dans [docs/genai/](./docs/genai/) :

- [RAPPORT_FINAL.pdf](./docs/genai/RAPPORT_FINAL.pdf) — rapport complet (cas d'usage, méthode, résultats, perspectives)
- [RENDU_C5.pdf](./docs/genai/RENDU_C5.pdf) — preuves mappées sur les compétences C5.1 / C5.2 / C5.3
- [PRESENTATION.pdf](./docs/genai/PRESENTATION.pdf) — support de présentation
- [tests/](./docs/genai/tests/) — jeu de test, harnais d'évaluation, résultats

## Le reste de la plateforme

La partie data (PostgreSQL, MongoDB, MinIO, Kafka, Flink, FastAPI) est documentée dans :

- [INSTALLATION.md](./INSTALLATION.md) — installation détaillée
- [ARCHITECTURE_DECISIONS.md](./ARCHITECTURE_DECISIONS.md) — choix techniques de la plateforme

---
Code et données à usage pédagogique (RNCP40875 — Efrei).

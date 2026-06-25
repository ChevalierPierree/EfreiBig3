# Couche IA generative vocale — KiVendTout

Greffe une couche d'IA generative **100% locale** sur la plateforme data KiVendTout,
sans modifier le coeur data. Branche : `genai-voice`.

## Objectif (atelier IA generative)

Permettre de **piloter le dashboard a la voix** (navigation, narration des KPIs,
reponse vocale) — feature d'accessibilite demandee par le VP, et 100% locale pour
respecter la sensibilite RGPD des donnees de fraude.

## Architecture

```
🎙️ Micro (navigateur, MediaRecorder)
   │  POST /api/voice/command
   ▼
🧠 STT local : faster-whisper            (api/voice/stt_service.py)
   ▼
🎯 Intention : Ollama / llama3.2 (JSON)  (api/voice/intent_service.py)
   ├─ navigate → le dashboard change de vue (voice_control.js)
   └─ explain  → narration des KPIs
                 🗣️ Ollama lit les chiffres reels de l'API :8000
                                          (api/voice/narrate_service.py)
                 🔊 TTS : Piper, voix NEURONALE locale (repli SpeechSynthesis)
```

Service vocal autonome sur le port **8100** (decouple du data API :8000 et du
dashboard :7600).

## Pre-requis

- La stack data KiVendTout lancee (`./patator`) — fournit l'API :8000 et le dashboard :7600.
- **Ollama** avec le modele `llama3.2` :
  ```bash
  ollama serve            # demarre le serveur (port 11434)
  ollama pull llama3.2    # si pas deja present
  ```
- Python 3.9+ et les dependances vocales.

## Installation

```bash
source .venv/bin/activate          # le venv du projet data
pip install -r requirements.voice.txt
```

## Lancement

```bash
# 1. La stack data doit tourner (./patator)
# 2. Ollama doit tourner (ollama serve)
# 3. Service vocal :
python -m api.voice.voice_app
#   ou : uvicorn api.voice.voice_app:app --host 0.0.0.0 --port 8100
```

Ouvrir http://localhost:7600/index.html. **Maintenir la touche `P`** pour parler,
relacher pour envoyer (push-to-talk ; l'orbe en bas a droite reagit a la voix).
L'assistant repond dans un panneau type chatbot et a voix haute.

### Commandes reconnues (langage naturel)
- **Navigation** : « ouvre la vue fraude », « affiche les transferts »,
  « montre l'identite », « reviens a l'accueil ».
- **Filtre** (pilote les vrais `<select>` de la file d'alertes, puis `loadAlerts()`) :
  « filtre les fraudes en severite haute », « montre seulement les alertes moyennes »,
  « affiche les alertes en attente ». Depuis une autre page, l'assistant ouvre
  d'abord la vue fraude puis applique le filtre.
- **Questions / resume** : « combien d'alertes de severite haute », « quel est le
  taux de fraude », « explique-moi les chiffres ». Reponse basee sur les KPIs reels.
- **Actions** (page Fraude) : « approuve l'alerte numero 3 », « bloque la 2 »,
  « investigue l'alerte selectionnee ». Chaque alerte porte un **numero court #N**
  visible (repere partage oeil + voix ; l'identifiant long type `FRD_PAY_...` reste
  affiche pour la tracabilite). **Confirmation obligatoire** : l'assistant decrit la
  cible (client, severite) et attend « oui » / « non » avant d'appeler
  `POST /api/alerts/{id}/decide`. Souris et voix pilotent la meme chose
  (contrat `window.KVFraud`).

## Endpoints du service vocal

- `GET  /health`
- `POST /api/voice/transcribe` (fichier audio) → texte
- `POST /api/voice/intent` `{text}` → `{action, view, ...}`
- `POST /api/voice/narrate` `{view}` → `{kpis, narration}`
- `POST /api/voice/command` (fichier audio) → pipeline complet
- `POST /api/voice/tts` `{text}` → audio WAV (voix neuronale locale Piper)
- `GET  /api/voice/tts/health` → `{available}` (le front retombe sur la voix
  navigateur si `false`)

### Voix neuronale (Piper) — modèle à télécharger une fois (~60 Mo, non versionné)
```bash
BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium
mkdir -p api/voice/tts_models
curl -L -o api/voice/tts_models/fr_FR-siwis-medium.onnx      "$BASE/fr_FR-siwis-medium.onnx"
curl -L -o api/voice/tts_models/fr_FR-siwis-medium.onnx.json "$BASE/fr_FR-siwis-medium.onnx.json"
```

## Configuration (variables d'env)

| Variable | Defaut | Role |
|---|---|---|
| `WHISPER_MODEL` | `small` | Taille du modele STT |
| `OLLAMA_MODEL` | `llama3.2` | Modele LLM local |
| `OLLAMA_URL` | `http://localhost:11434/api/chat` | Endpoint Ollama |
| `DATA_API_URL` | `http://localhost:8000` | API data KiVendTout |

## Etat

✅ **Pipeline valide de bout en bout** (audio -> transcription -> intention ->
navigation / narration). Mesure du 2026-06-22 (12 commandes, 100 % local —
detail dans [tests/scenarios.md](./tests/scenarios.md)) :
- STT faster-whisper : WER moyen **0,157** (~1 s a chaud) ; erreurs concentrees
  sur les mots metier mal prononces par la voix de synthese de test.
- Intention (llama3.2 3B, sortie JSON, temperature 0) : accuracy **0,833**
  (10/12) ; les echecs sont 1 limite modele + 1 rejet sur transcription corrompue.
- Narration / Q&A : **0 chiffre invente** (cite les KPIs reels avec les bons
  libelles ; ancrage anti-hallucination valide).

### ⚠️ Pre-requis Ollama : version >= 0.30
Sur macOS recent (Darwin 25.x), Ollama 0.22 plante a l'init Metal
(`static_assert half/bfloat` -> `panic: unable to create llama context`) sans
fallback CPU. **Mettre a jour** : `brew upgrade ollama` (>= 0.30.10 OK).

### Pistes d'amelioration
- Narration : le 3B est parfois verbeux/format libre. Affiner le prompt (prose,
  2-3 phrases) ou tester `ollama pull qwen2.5:3b` pour un FR plus soigne.

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
                 🔊 TTS : SpeechSynthesis (voix macOS, local)
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

Ouvrir http://localhost:7600/index.html : un bouton 🎙️ flottant apparait.
Cliquer, parler (« ouvre la vue fraude », « explique-moi le taux de fraude »),
re-cliquer pour envoyer.

## Endpoints du service vocal

- `GET  /health`
- `POST /api/voice/transcribe` (fichier audio) → texte
- `POST /api/voice/intent` `{text}` → `{action, view, ...}`
- `POST /api/voice/narrate` `{view}` → `{kpis, narration}`
- `POST /api/voice/command` (fichier audio) → pipeline complet

## Configuration (variables d'env)

| Variable | Defaut | Role |
|---|---|---|
| `WHISPER_MODEL` | `small` | Taille du modele STT |
| `OLLAMA_MODEL` | `llama3.2` | Modele LLM local |
| `OLLAMA_URL` | `http://localhost:11434/api/chat` | Endpoint Ollama |
| `DATA_API_URL` | `http://localhost:8000` | API data KiVendTout |

## Etat

✅ **Pipeline valide de bout en bout** (audio -> transcription -> intention ->
navigation / narration) :
- STT faster-whisper : transcription FR correcte (~1 s a chaud).
- Intention (llama3.2 3B, sortie JSON) : 5/5 sur le jeu de commandes de test.
- Narration : cite les KPIs reels avec les bons libelles (anti-hallucination).

### ⚠️ Pre-requis Ollama : version >= 0.30
Sur macOS recent (Darwin 25.x), Ollama 0.22 plante a l'init Metal
(`static_assert half/bfloat` -> `panic: unable to create llama context`) sans
fallback CPU. **Mettre a jour** : `brew upgrade ollama` (>= 0.30.10 OK).

### Pistes d'amelioration
- Narration : le 3B est parfois verbeux/format libre. Affiner le prompt (prose,
  2-3 phrases) ou tester `ollama pull qwen2.5:3b` pour un FR plus soigne.

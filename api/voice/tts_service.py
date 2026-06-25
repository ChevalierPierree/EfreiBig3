"""Synthese vocale NEURONALE locale via Piper (TTS).

Remplace la voix de synthese classique du navigateur (SpeechSynthesis) par une
voix generee par reseau de neurones, **100% locale et hors-ligne** : le modele
ONNX est charge une fois puis sert toutes les requetes. Aucune donnee ne quitte
la machine (coherent avec le choix local du projet, cf. C5.2).

Le modele (~60 Mo) n'est pas versionne. Telecharger une fois :
    BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium
    curl -L -o api/voice/tts_models/fr_FR-siwis-medium.onnx      "$BASE/fr_FR-siwis-medium.onnx"
    curl -L -o api/voice/tts_models/fr_FR-siwis-medium.onnx.json "$BASE/fr_FR-siwis-medium.onnx.json"
"""
from __future__ import annotations

import io
import os
import wave

_DEFAULT = os.path.join(os.path.dirname(__file__), "tts_models", "fr_FR-siwis-medium.onnx")
MODEL_PATH = os.environ.get("PIPER_MODEL", _DEFAULT)

_voice = None  # chargement paresseux (evite de bloquer le demarrage du service)


def available() -> bool:
    """Le modele neuronal est-il present ? (sinon le front retombe sur la voix navigateur)."""
    return os.path.exists(MODEL_PATH)


def _get_voice():
    global _voice
    if _voice is None:
        from piper import PiperVoice  # import tardif : pas de cout si TTS inutilise
        _voice = PiperVoice.load(MODEL_PATH)
    return _voice


def synthesize(text: str) -> bytes:
    """Texte -> WAV (PCM 16 bits, mono). Leve si le modele est absent/illisible."""
    if not available():
        raise FileNotFoundError(f"Modele Piper introuvable : {MODEL_PATH}")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        _get_voice().synthesize_wav((text or "").strip() or "Aucun texte.", wf)
    return buf.getvalue()

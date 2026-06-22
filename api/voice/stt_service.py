"""Transcription vocale locale via faster-whisper.

Aucune donnee audio ne quitte la machine : le modele tourne en local
(exigence d'accessibilite du VP + sensibilite RGPD des donnees de fraude).
"""
from __future__ import annotations

import os

# Taille du modele Whisper. "small" = bon compromis qualite/latence en FR.
# "base" plus rapide, "medium" plus precis (plus lourd).
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
# int8 sur CPU = rapide et leger. Sur Mac on peut tenter device="auto".
DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE", "int8")

_model = None


def get_model():
    """Charge le modele paresseusement (premier appel uniquement)."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    return _model


def transcribe(audio_path: str, language: str = "fr") -> dict:
    """Transcrit un fichier audio en texte.

    Retourne {text, language, duration} pour permettre le calcul de metriques
    (WER, latence) cote evaluation C5.3.
    """
    segments, info = get_model().transcribe(audio_path, language=language, vad_filter=True)
    text = " ".join(seg.text for seg in segments).strip()
    return {
        "text": text,
        "language": info.language,
        "duration": round(info.duration, 2),
    }

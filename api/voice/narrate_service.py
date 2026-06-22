"""Narration generative des KPIs via Ollama (llama3.2, local).

On recupere les vrais chiffres depuis l'API data de KiVendTout (port 8000),
puis on demande au LLM de les resumer en francais clair. Les chiffres sont
injectes dans le prompt -> le LLM REFORMULE mais n'INVENTE pas (garde-fou
anti-hallucination, verifiable en C5.3 : chiffre cite == KPI reel).
"""
from __future__ import annotations

import os

import requests

DATA_API = os.environ.get("DATA_API_URL", "http://localhost:8000")
OLLAMA_URL = os.environ.get("OLLAMA_GEN_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")

# Map vue -> endpoint(s) KPI a recuperer pour la narration.
KPI_SOURCES = {
    "fraud": ["/api/stats"],
    "fraud_types": ["/api/stats"],
    "transfer_kpi": ["/api/payments/stats?window_hours=24"],
    "overview": ["/api/stats"],
    "id_cards": ["/api/stats"],
}


def _fetch_kpis(view: str) -> dict:
    data = {}
    for path in KPI_SOURCES.get(view, ["/api/stats"]):
        try:
            r = requests.get(f"{DATA_API}{path}", timeout=10)
            r.raise_for_status()
            data[path] = r.json()
        except requests.RequestException as exc:
            data[path] = {"error": str(exc)}
    return data


def narrate(view: str = "fraud") -> dict:
    """Renvoie {kpis, narration}. La narration cite uniquement les KPIs fournis."""
    kpis = _fetch_kpis(view)
    system = (
        "Tu es un analyste fraude. On te donne des KPIs JSON reels. "
        "Resume-les en francais en 2 a 3 phrases claires pour un dirigeant. "
        "Cite UNIQUEMENT les chiffres presents dans les donnees, n'invente rien, "
        "ne donne pas de conseils non demandes."
    )
    user = f"KPIs de la vue '{view}' :\n{kpis}"
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
        resp.raise_for_status()
        narration = resp.json()["message"]["content"].strip()
    except (requests.RequestException, KeyError) as exc:
        narration = f"Narration indisponible ({exc})."
    return {"kpis": kpis, "narration": narration}

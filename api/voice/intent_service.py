"""Classification d'intention via Ollama (llama3.2, local).

Transforme une phrase libre en une action structuree exploitable par le
dashboard. On contraint la sortie en JSON via le parametre `format: json`
d'Ollama pour fiabiliser le parsing.
"""
from __future__ import annotations

import json
import os

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")

# Vues disponibles dans le dashboard (cibles de navigation).
VIEWS = {
    "overview": "index.html",
    "fraud": "fraud_dashboard.html",
    "fraud_types": "fraud_types_dashboard.html",
    "id_cards": "id_cards_dashboard.html",
    "transfer_kpi": "transfer_kpi_dashboard.html",
    "use_cases": "use_cases_dashboard.html",
}

SYSTEM_PROMPT = f"""Tu es le routeur d'intentions d'un dashboard de detection de fraude.
Tu recois une commande vocale transcrite (en francais) et tu renvoies UNIQUEMENT
un objet JSON, sans texte autour.

Schema attendu :
{{
  "action": "navigate" | "explain" | "unknown",
  "view": un identifiant parmi {list(VIEWS.keys())} ou null,
  "raw": la commande reformulee brievement
}}

Regles :
- "action": "navigate" si l'utilisateur veut afficher/ouvrir une vue.
- "action": "explain" s'il veut une explication/un resume des chiffres.
- "action": "unknown" si la commande n'est pas comprise.
- "view": la vue concernee (fraud = fraude, id_cards = identite/CNI,
  transfer_kpi = transferts/latence, overview = accueil), ou null.
Reponds en JSON strict."""


def classify(text: str) -> dict:
    """Renvoie {action, view, raw}. En cas d'echec LLM, action=unknown."""
    payload = {
        "model": OLLAMA_MODEL,
        "format": "json",
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=30)
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        intent = json.loads(content)
    except (requests.RequestException, KeyError, json.JSONDecodeError) as exc:
        return {"action": "unknown", "view": None, "raw": text, "error": str(exc)}

    action = intent.get("action", "unknown")
    view = intent.get("view")
    if view not in VIEWS:
        view = None
    return {
        "action": action if action in ("navigate", "explain", "unknown") else "unknown",
        "view": view,
        "view_file": VIEWS.get(view),
        "raw": intent.get("raw", text),
    }

"""Classification d'intention via Ollama (llama3.2, local).

Transforme une commande vocale libre en action structuree :
- navigate : afficher une vue
- filter   : filtrer la file d'alertes (severite / statut)
- ask      : repondre a une question sur les chiffres (ou resumer)
- unknown  : incompris

Sortie contrainte en JSON (parametre `format: json` d'Ollama).
"""
from __future__ import annotations

import json
import os
import unicodedata

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")

# Vues du dashboard (cibles de navigation).
VIEWS = {
    "overview": "index.html",
    "fraud": "fraud_dashboard.html",
    "fraud_types": "fraud_types_dashboard.html",
    "id_cards": "id_cards_dashboard.html",
    "transfer_kpi": "transfer_kpi_dashboard.html",
    "use_cases": "use_cases_dashboard.html",
}

# Normalisation valeur FR -> (code du <select>, libelle affiche).
SEVERITY_MAP = {
    "haute": ("HIGH", "Haute"), "elevee": ("HIGH", "Haute"), "forte": ("HIGH", "Haute"),
    "critique": ("HIGH", "Haute"), "grave": ("HIGH", "Haute"),
    "moyenne": ("MEDIUM", "Moyenne"), "moderee": ("MEDIUM", "Moyenne"),
    "basse": ("LOW", "Basse"), "faible": ("LOW", "Basse"),
    "toutes": ("", "Toutes"), "tout": ("", "Toutes"), "toute": ("", "Toutes"),
}
STATUS_MAP = {
    "attente": ("PENDING_REVIEW", "En attente"), "pending": ("PENDING_REVIEW", "En attente"),
    "investigation": ("INVESTIGATING", "En investigation"),
    "enquete": ("INVESTIGATING", "En investigation"),
    "approuve": ("APPROVED", "Approuve"), "valide": ("APPROVED", "Approuve"),
    "bloque": ("BLOCKED", "Bloque"),
    "tous": ("", "Tous"), "tout": ("", "Tous"),
}

SYSTEM_PROMPT = f"""Tu es le routeur d'un dashboard de detection de fraude.
Tu recois une commande vocale en francais et tu renvoies UNIQUEMENT un objet JSON.

Schema:
{{"action":"navigate"|"filter"|"ask"|"unknown",
  "view": un id parmi {list(VIEWS.keys())} ou null,
  "field":"severity"|"status"|null,
  "value": le mot du filtre (ex "haute","moyenne","en attente") ou null}}

Regles:
- navigate : afficher/ouvrir une vue (fraud=fraude, id_cards=identite/CNI,
  transfer_kpi=transferts, fraud_types=typologies, overview=accueil).
- filter : filtrer la file d'alertes. field=severity (haute/moyenne/basse) ou
  status (en attente/investigation/approuve/bloque). value = le mot du filtre.
- ask : question sur les chiffres OU demande de resume/explication.
- unknown : incompris.

Exemples:
"ouvre la vue fraude" -> {{"action":"navigate","view":"fraud","field":null,"value":null}}
"filtre les fraudes en severite haute" -> {{"action":"filter","view":"fraud","field":"severity","value":"haute"}}
"affiche seulement les alertes moyennes" -> {{"action":"filter","view":"fraud","field":"severity","value":"moyenne"}}
"montre les alertes en attente" -> {{"action":"filter","view":"fraud","field":"status","value":"en attente"}}
"combien d'alertes haute severite" -> {{"action":"ask","view":"fraud","field":null,"value":null}}
"explique-moi le taux de fraude" -> {{"action":"ask","view":"fraud","field":null,"value":null}}
Reponds en JSON strict."""


def _strip(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _resolve_filter(field: str, value: str) -> tuple:
    """(field, code_select, libelle) ou (None, None, None) si non resolu."""
    table = SEVERITY_MAP if field == "severity" else STATUS_MAP if field == "status" else None
    if table is None:
        return None, None, None
    v = _strip(value)
    for key, (code, label) in table.items():
        if key in v:
            return field, code, label
    return field, None, None


def classify(text: str) -> dict:
    payload = {
        "model": OLLAMA_MODEL, "format": "json", "stream": False, "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=30)
        resp.raise_for_status()
        intent = json.loads(resp.json()["message"]["content"])
    except (requests.RequestException, KeyError, json.JSONDecodeError) as exc:
        return {"action": "unknown", "raw": text, "error": str(exc)}

    action = intent.get("action")
    if action not in ("navigate", "filter", "ask", "unknown"):
        action = "unknown"
    view = intent.get("view") if intent.get("view") in VIEWS else None

    out = {
        "action": action,
        "view": view,
        "view_file": VIEWS.get(view),
        "field": None,
        "value_code": None,
        "value_label": None,
        "raw": text,
    }
    if action == "filter":
        field, code, label = _resolve_filter(intent.get("field"), intent.get("value", ""))
        if field is None or code is None:
            out["action"] = "unknown"  # filtre non resolu
        else:
            out.update(field=field, value_code=code, value_label=label, view="fraud",
                       view_file=VIEWS["fraud"])
    return out

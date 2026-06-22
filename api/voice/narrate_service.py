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


def _label_kpis(kpis: dict) -> str:
    """Reformate les champs cles de /api/stats en libelles FR explicites.

    Evite que le LLM confonde 'paiements totaux' et 'paiements frauduleux'
    (ancrage anti-hallucination, verifiable en C5.3).
    """
    stats = kpis.get("/api/stats", {})
    if not isinstance(stats, dict) or "error" in stats:
        return f"Donnees brutes : {kpis}"
    sev = stats.get("alerts_by_severity", {})
    lignes = [
        f"- Alertes de fraude (total) : {stats.get('total_alerts')}",
        f"- Alertes de severite Haute : {sev.get('HIGH')}",
        f"- Alertes de severite Moyenne : {sev.get('MEDIUM')}",
        f"- Paiements totaux : {stats.get('total_payments')}",
        f"- Paiements frauduleux : {stats.get('fraudulent_payments')}",
        f"- Taux de fraude : {stats.get('fraud_rate')} %",
        f"- Clients totaux : {stats.get('total_customers')}",
        f"- Clients couverts par au moins une alerte : {stats.get('alerted_customers')} "
        f"({stats.get('customer_alert_coverage')} %)",
    ]
    return "\n".join(l for l in lignes if "None" not in l)


def narrate(view: str = "fraud") -> dict:
    """Renvoie {kpis, narration}. La narration cite uniquement les KPIs fournis."""
    kpis = _fetch_kpis(view)
    system = (
        "Tu es un analyste fraude. On te donne une liste de KPIs etiquetes. "
        "Resume-les en francais en 2 a 3 phrases claires pour un dirigeant. "
        "Cite chaque chiffre avec le BON libelle (ne confonds pas 'paiements totaux' "
        "et 'paiements frauduleux'). N'invente aucun chiffre absent de la liste, "
        "et ne donne pas de conseils non demandes."
    )
    user = f"KPIs de la vue '{view}' :\n{_label_kpis(kpis)}"
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False, "options": {"temperature": 0},
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


def answer_question(question: str, view: str = "fraud") -> dict:
    """Repond a une question libre en s'appuyant sur les KPIs reels (anti-hallucination)."""
    kpis = _fetch_kpis(view)
    system = (
        "Tu es un analyste fraude. Reponds en francais, en 1 a 2 phrases courtes, "
        "a la question posee, en t'appuyant UNIQUEMENT sur les KPIs etiquetes fournis. "
        "Cite le bon chiffre avec le bon libelle. Si l'information demandee n'est pas "
        "dans les KPIs, dis-le simplement."
    )
    user = f"KPIs disponibles :\n{_label_kpis(kpis)}\n\nQuestion : {question}"
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False, "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
        resp.raise_for_status()
        answer = resp.json()["message"]["content"].strip()
    except (requests.RequestException, KeyError) as exc:
        answer = f"Reponse indisponible ({exc})."
    return {"kpis": kpis, "answer": answer}

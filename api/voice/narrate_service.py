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
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral:7b")

import re

# Vues regroupees par "domaine" de KPIs a raconter.
FRAUD_VIEWS = {"fraud", "fraud_types", "overview"}


def _get(path: str) -> dict:
    try:
        r = requests.get(f"{DATA_API}{path}", timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        return {"error": str(exc)}


def _fmt(n) -> str:
    """Formate un nombre a la francaise (3 632, 12,27) — le modele recopie tel quel."""
    if isinstance(n, float):
        return (f"{n:.2f}".rstrip("0").rstrip(".")).replace(".", ",")
    if isinstance(n, int):
        return f"{n:,}".replace(",", " ")
    return str(n)


def _context(view: str) -> tuple:
    """Construit (bloc_KPIs_FR, dict_brut) pour la vue.

    On s'appuie sur /api/kpis/readable (deja interprete en francais, avec les
    ratios REELS) + /api/stats. Le modele n'a ainsi qu'a REFORMULER des chiffres
    deja etiquetes : il ne recalcule rien (anti-hallucination, verifiable C5.3).
    """
    if view in FRAUD_VIEWS or view not in {"transfer_kpi", "id_cards"}:
        stats = _get("/api/stats")
        readable = _get("/api/kpis/readable?limit=100&micro_batch_window_hours=24")
        f = (readable.get("fraud") or {}).get("kpis", {}) if isinstance(readable, dict) else {}
        sev = stats.get("alerts_by_severity", {}) if isinstance(stats, dict) else {}
        lignes = [
            f"- Alertes de fraude au total : {_fmt(f.get('total_alerts') or stats.get('total_alerts'))}",
            f"- dont severite Haute : {_fmt(sev.get('HIGH'))}",
            f"- dont severite Moyenne : {_fmt(sev.get('MEDIUM'))}",
            f"- dont severite Basse : {_fmt(sev.get('LOW'))}",
            f"- Paiements analyses au total : {_fmt(f.get('total_payments') or stats.get('total_payments'))}",
            f"- Paiements frauduleux confirmes : {_fmt(f.get('fraudulent_payments') or stats.get('fraudulent_payments'))}",
            f"- Taux de fraude : {_fmt(f.get('fraud_rate_percent') or stats.get('fraud_rate'))} %",
            f"- Nombre d'alertes par paiement frauduleux : {_fmt(f.get('alert_per_fraud_payment'))}",
            f"- Clients couverts par au moins une alerte : {_fmt(f.get('alerted_customers') or stats.get('alerted_customers'))} "
            f"sur {_fmt(f.get('total_customers') or stats.get('total_customers'))} "
            f"({_fmt(f.get('customer_alert_coverage_percent') or stats.get('customer_alert_coverage'))} %)",
            f"- Motif le plus frequent : {f.get('top_reason') or '—'}",
        ]
        raw = {"stats": stats, "readable_fraud": f}
    elif view == "transfer_kpi":
        t = _get("/api/transfer/kpis")
        s = t.get("summary", {}) if isinstance(t, dict) else {}
        lignes = [
            f"- Etat du pipeline de transfert : {'operationnel' if s.get('health_score') == 100 else 'a verifier'} "
            f"(score {_fmt(s.get('health_score'))}/100)",
            f"- Flux surveilles : {_fmt(s.get('monitored_flows'))}",
            f"- Fenetres micro-batch actives (historique) : {_fmt(s.get('active_micro_batch_windows'))}",
            f"- Dernier snapshot : {s.get('latest_snapshot_size_human') or '—'}",
            f"- Dernier volume micro-batch : {s.get('latest_micro_batch_volume_human') or '—'}",
        ]
        raw = {"transfer": s}
    else:  # id_cards
        c = _get("/api/checkout/stats?window_hours=24")
        idn = _get("/api/identity/stats")
        by = idn.get("by_status", {}) if isinstance(idn, dict) else {}
        lignes = [
            f"- Verifications d'identite au total : {_fmt(idn.get('total_verifications'))}",
            f"- dont verifiees : {_fmt(by.get('verified'))}",
            f"- dont rejetees : {_fmt(by.get('rejected'))}",
            f"- Commandes bloquees pour age (24 h) : {_fmt(c.get('blocked_underage_orders'))}",
            f"- Commandes acceptees (24 h) : {_fmt(c.get('accepted_orders'))}",
            f"- Age moyen des clients : {_fmt(c.get('avg_customer_age'))} ans",
        ]
        raw = {"checkout": c, "identity": idn}
    def _has_value(line: str) -> bool:
        val = line.split(":", 1)[-1].strip()
        return val not in ("None", "—", "") and "None" not in val
    bloc = "\n".join(l for l in lignes if _has_value(l))
    return bloc, raw


# Regles communes : prose, pas de puces, pas de recalcul. C'est ce qui rend la
# narration fluide ET fiable (le 3B avait tendance a lister et a inventer des %).
_STYLE = (
    "Reponds en francais, en PROSE FLUIDE (phrases completes, AUCUNE liste a puces, "
    "aucun tiret, aucun symbole markdown). N'utilise QUE les chiffres fournis ci-dessous : "
    "ne recalcule JAMAIS un pourcentage ou un ratio qui n'est pas deja donne, n'invente aucun "
    "chiffre. Cite chaque nombre avec le bon libelle et garde son format exact. "
    "Commence DIRECTEMENT par l'information, sans formule d'introduction du type "
    "'Voici un resume' ou 'Le tableau de bord indique'."
)


def _clean(text: str) -> str:
    """Filet de securite : retire puces/markdown residuels, recompacte en prose."""
    text = re.sub(r"^\s*[-*•]\s*", "", text, flags=re.MULTILINE)  # puces
    text = re.sub(r"[*#`]+", "", text)                            # markdown (sans '_' : codes type FIRST_PAYMENT)
    text = re.sub(r"\n{2,}", " ", text)                            # paragraphes -> espace
    text = re.sub(r"\n", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _chat(system: str, user: str, timeout: int = 60) -> str:
    payload = {
        "model": OLLAMA_MODEL, "stream": False, "options": {"temperature": 0},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def narrate(view: str = "fraud") -> dict:
    """Renvoie {kpis, narration}. Resume fluide cite uniquement les KPIs fournis."""
    bloc, raw = _context(view)
    system = (
        "Tu es un analyste qui resume un tableau de bord pour un dirigeant. "
        "Fais un resume clair en 2 a 3 phrases. " + _STYLE +
        " Ne donne pas de conseils non demandes."
    )
    user = f"Chiffres de la vue '{view}' :\n{bloc}"
    try:
        narration = _clean(_chat(system, user))
    except (requests.RequestException, KeyError) as exc:
        narration = f"Narration indisponible ({exc})."
    return {"kpis": raw, "narration": narration}


def answer_question(question: str, view: str = "fraud") -> dict:
    """Repond a une question libre en s'appuyant sur les KPIs reels de la bonne vue."""
    bloc, raw = _context(view)
    system = (
        "Tu es un analyste. Reponds precisement a la question en 1 a 2 phrases. "
        + _STYLE +
        " Si l'information demandee n'est pas dans les chiffres fournis, dis-le simplement."
    )
    user = f"Chiffres disponibles :\n{bloc}\n\nQuestion : {question}"
    try:
        answer = _clean(_chat(system, user))
    except (requests.RequestException, KeyError) as exc:
        answer = f"Reponse indisponible ({exc})."
    return {"kpis": raw, "answer": answer}

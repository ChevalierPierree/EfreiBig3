#!/usr/bin/env python3
"""Harnais d'evaluation C5.3 — KiVendTout voix.

Mesure, de bout en bout et 100% local :
  1. STT  : WER (Word Error Rate) sur des commandes FR synthetisees (say) puis
            transcrites par le service (:8100 /api/voice/transcribe).
  2. Intention : accuracy {action, view, field, value} via /api/voice/intent.
  3. Narration : exactitude factuelle (tout chiffre cite == KPI reel de :8000).
  4. Latence : ms par etape (apres warmup).

Sortie : un blob JSON sur stdout, consomme pour remplir le rapport C5.3.

Usage : python3 docs/genai/tests/run_eval.py
Prerequis : services :8000 (data) et :8100 (voix) up, Ollama up, macOS `say`.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata

import requests

VOICE = "http://localhost:8100"
DATA = "http://localhost:8000"
SAY_VOICE = os.environ.get("SAY_VOICE", "Thomas")  # fr_FR

# Jeu de test : (texte prononce, action attendue, view, field, value_code).
CASES = [
    # --- navigation ---
    ("ouvre la vue fraude",                    "navigate", "fraud",        None,       None),
    ("affiche les transferts",                 "navigate", "transfer_kpi", None,       None),
    ("montre les cartes d'identite",           "navigate", "id_cards",     None,       None),
    ("reviens a l'accueil",                    "navigate", "overview",     None,       None),
    ("ouvre les typologies de fraude",         "navigate", "fraud_types",  None,       None),
    ("montre les cas d'usage",                 "navigate", "use_cases",    None,       None),
    # --- filtres ---
    ("filtre les fraudes en severite haute",   "filter",   "fraud",        "severity", "HIGH"),
    ("affiche seulement les alertes moyennes", "filter",   "fraud",        "severity", "MEDIUM"),
    ("montre les alertes en attente",          "filter",   "fraud",        "status",   "PENDING_REVIEW"),
    # --- questions / narration ---
    ("explique moi le taux de fraude",         "ask",      "fraud",        None,       None),
    ("combien d'alertes de severite haute",    "ask",      "fraud",        None,       None),
    # --- hors-domaine (doit etre rejete proprement) ---
    ("quelle est la meteo demain a paris",     "unknown",  None,           None,       None),
]


def strip_accents(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c))


def norm_words(s):
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9' ]", " ", s)
    return [w for w in s.split() if w]


def wer(ref, hyp):
    """Word Error Rate par distance de Levenshtein sur les mots (insensible accents/casse/ponct)."""
    r, h = norm_words(ref), norm_words(hyp)
    n, m = len(r), len(h)
    if n == 0:
        return 0.0 if m == 0 else 1.0
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
    return d[n][m] / n


def synth(text, path):
    """Genere un wav 16kHz mono via `say` puis ffmpeg (format whisper-friendly)."""
    aiff = path + ".aiff"
    subprocess.run(["say", "-v", SAY_VOICE, "-o", aiff, text], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", aiff,
                    "-ar", "16000", "-ac", "1", path], check=True)
    os.remove(aiff)


def transcribe(path):
    with open(path, "rb") as f:
        t0 = time.time()
        r = requests.post(f"{VOICE}/api/voice/transcribe",
                          files={"audio": ("cmd.wav", f, "audio/wav")}, timeout=120)
        dt = (time.time() - t0) * 1000
    r.raise_for_status()
    return r.json().get("text", ""), dt


def classify(text):
    t0 = time.time()
    r = requests.post(f"{VOICE}/api/voice/intent", json={"text": text}, timeout=60)
    dt = (time.time() - t0) * 1000
    r.raise_for_status()
    return r.json(), dt


def numbers_in(s):
    """Nombres cites, en recollant les milliers a la francaise (5 764 -> 5764)."""
    s = s or ""
    prev = None
    while prev != s:  # '5 764' / '5 764' -> '5764'
        prev = s
        s = re.sub(r"(\d)[   ](\d)", r"\1\2", s)
    return set(re.findall(r"\d+(?:[.,]\d+)?", s))


def main():
    results = {"stt": [], "intent": [], "narration": {}, "latency": {}, "meta": {}}

    # Ground-truth KPIs (source de verite pour la factualite).
    stats = requests.get(f"{DATA}/api/stats", timeout=15).json()
    sev = stats.get("alerts_by_severity", {})
    truth = {
        "total_alerts": stats.get("total_alerts"),
        "HIGH": sev.get("HIGH"), "MEDIUM": sev.get("MEDIUM"), "LOW": sev.get("LOW"),
        "total_payments": stats.get("total_payments"),
        "fraudulent_payments": stats.get("fraudulent_payments"),
        "fraud_rate": stats.get("fraud_rate"),
        "total_customers": stats.get("total_customers"),
        "alerted_customers": stats.get("alerted_customers"),
        "customer_alert_coverage": stats.get("customer_alert_coverage"),
    }
    results["meta"]["truth"] = truth
    # Les comptes de motifs sont aussi des KPIs reels citables (ex. top_reason).
    for r in stats.get("top_fraud_reasons", []):
        truth[f"reason_{r.get('reason')}"] = r.get("count")
    # Toutes les valeurs reelles, en str normalisees, pour la verif anti-hallucination.
    truth_strs = set()
    for v in truth.values():
        if v is None:
            continue
        truth_strs.add(str(v))
        truth_strs.add(str(v).replace(".", ","))
        if isinstance(v, float) and v.is_integer():
            truth_strs.add(str(int(v)))
        if isinstance(v, (int, float)):
            truth_strs.add(f"{v:.2f}")
            truth_strs.add(f"{v:.1f}")

    tmp = tempfile.mkdtemp(prefix="kvx_eval_")

    # Warmup (exclut le cold-start des moyennes de latence).
    sys.stderr.write("warmup...\n")
    classify("ouvre la vue fraude")
    wpath = os.path.join(tmp, "warm.wav")
    synth("ouvre la vue fraude", wpath)
    transcribe(wpath)

    stt_lat, int_lat = [], []
    for i, (text, eaction, eview, efield, ecode) in enumerate(CASES):
        sys.stderr.write(f"[{i+1}/{len(CASES)}] {text}\n")
        wav = os.path.join(tmp, f"c{i}.wav")
        synth(text, wav)
        hyp, dt_stt = transcribe(wav)
        stt_lat.append(dt_stt)
        w = wer(text, hyp)
        results["stt"].append({"ref": text, "hyp": hyp, "wer": round(w, 3)})

        # Intention : on classe sur la TRANSCRIPTION (chaine reelle bout-en-bout).
        intent, dt_int = classify(hyp)
        int_lat.append(dt_int)
        ok_action = intent.get("action") == eaction
        ok_view = (intent.get("view") or None) == eview
        ok_field = (intent.get("field") or None) == efield
        ok_code = (intent.get("value_code") or None) == ecode
        full_ok = ok_action and ok_view and ok_field and ok_code
        results["intent"].append({
            "ref": text, "hyp": hyp,
            "expected": {"action": eaction, "view": eview, "field": efield, "code": ecode},
            "got": {"action": intent.get("action"), "view": intent.get("view"),
                    "field": intent.get("field"), "code": intent.get("value_code")},
            "ok_action": ok_action, "full_ok": full_ok,
        })

    # --- Narration / factualite ---
    narr = requests.post(f"{VOICE}/api/voice/narrate", json={"view": "fraud"}, timeout=120).json()
    t0 = time.time()
    ask = requests.post(f"{VOICE}/api/voice/ask",
                        json={"text": "combien d'alertes de severite haute et quel est le taux de fraude"},
                        timeout=120).json()
    narr_lat = (time.time() - t0) * 1000

    def check_factual(text):
        nums = numbers_in(text)
        invented = sorted(n for n in nums if n not in truth_strs
                          and n.replace(",", ".") not in truth_strs)
        return {"text": text, "numbers_cited": sorted(nums), "invented": invented}

    results["narration"] = {
        "narrate": check_factual(narr.get("narration", "")),
        "ask": check_factual(ask.get("answer", "")),
    }

    avg = lambda xs: round(sum(xs) / len(xs)) if xs else None
    results["latency"] = {
        "stt_ms_avg": avg(stt_lat), "stt_ms_max": round(max(stt_lat)) if stt_lat else None,
        "intent_ms_avg": avg(int_lat),
        "narrate_ask_ms": round(narr_lat),
    }

    # --- Agregats ---
    wers = [r["wer"] for r in results["stt"]]
    results["meta"]["wer_avg"] = round(sum(wers) / len(wers), 3)
    results["meta"]["wer_exact"] = sum(1 for w in wers if w == 0)
    results["meta"]["n"] = len(CASES)
    results["meta"]["intent_action_acc"] = round(
        sum(1 for r in results["intent"] if r["ok_action"]) / len(CASES), 3)
    results["meta"]["intent_full_acc"] = round(
        sum(1 for r in results["intent"] if r["full_ok"]) / len(CASES), 3)
    results["meta"]["invented_numbers_total"] = (
        len(results["narration"]["narrate"]["invented"])
        + len(results["narration"]["ask"]["invented"]))

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

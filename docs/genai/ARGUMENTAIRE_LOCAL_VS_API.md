# C5.2 — Argumentaire Local vs API

> « Soyez sûr d'argumenter vos choix correctement, aussi bien sur le choix des
> solutions envisagées que sur les technologies utilisées (Local VS API). »

## Décision : tout en local

| Brique | Choix | Alternative API écartée |
|---|---|---|
| STT (transcription) | **faster-whisper (local)** | Cloud STT (Google/Whisper API) |
| LLM (intention + narration) | **Ollama / llama3.2 (local)** | Claude API (Haiku 4.5 / Opus 4.8) |
| TTS (synthèse vocale) | **SpeechSynthesis navigateur (voix macOS, local)** | Cloud TTS (ElevenLabs, etc.) |

## Pourquoi le local l'emporte ici

1. **Exigence métier explicite** — le VP doit naviguer « pour un usage au moins
   local ». Le local n'est pas une option, c'est le cahier des charges.
2. **Sensibilité des données (RGPD)** — on manipule des paiements, des alertes de
   fraude, des vérifications d'identité (CNI). Envoyer ces données à un tiers est
   un risque réglementaire. En local, **aucune donnée ne quitte la machine**.
3. **Coût** — zéro coût par requête. Une solution API facture chaque appel.
4. **Hors-ligne et latence** — fonctionne sans réseau, latence maîtrisée.

## Mais on a pesé le choix (le local a un prix)

| Critère | Local (notre choix) | API (Claude) |
|---|---|---|
| Confidentialité | ✅ Données locales | ⚠️ Envoi cloud (KPIs agrégés, pas de PII brute) |
| Coût | ✅ Gratuit | ✅ Très bas : Haiku 4.5 ≈ 1 $ / 5 $ par M tokens ; Opus 4.8 ≈ 5 $ / 25 $ |
| Qualité narration FR | ⚠️ Correcte (llama3.2 3B) | ✅ Supérieure |
| Ressources machine | ⚠️ RAM/CPU locaux | ✅ Déporté |
| Hors-ligne | ✅ Oui | ❌ Non |

**Conclusion argumentée** : pour ce cas d'usage (données sensibles + exigence
locale du VP), le local domine malgré une qualité de rédaction inférieure. Si le
besoin évoluait vers des narrations grand public (B2C) sans données sensibles,
une bascule vers l'API (Claude Haiku, très bon marché) serait défendable — d'où
l'architecture découplée qui permettrait de remplacer la brique LLM sans toucher
au reste.

## Opportunité B2C (demandée par le sujet)

La navigation vocale dépasse l'accessibilité du VP : mains-libres en mobilité,
inclusion (déficiences motrices/visuelles), vulgarisation de statistiques pour le
grand public via la narration. Le même socle NLU sert le B2B (self-service
analytics) et le B2C (accessibilité) — c'est le point de convergence des 3 axes.

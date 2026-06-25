/*
 * Assistant vocal KiVendTout — intégré à l'UI (branche V2).
 *
 * Double usage SOURIS + VOIX :
 *  - Voix : maintenir P, OU cliquer le micro de la barre de commande ([data-voice-trigger]).
 *  - Souris : taper une commande dans la barre, ou cliquer une suggestion ([data-cmd]).
 * 100% local : faster-whisper (STT) + Ollama/llama3.2 (intention + réponses).
 * Expose window.KVVoice = { toggle, start, stop, runText }.
 */
(function () {
  "use strict";

  const BASE = (window.VOICE_API_URL || "http://localhost:8100") + "/api/voice";
  const MIN_REC_MS = 300;

  const VIEW_LABELS = {
    overview: "la vue d'ensemble", fraud: "la vue fraude",
    fraud_types: "les typologies de fraude", id_cards: "la vue identité",
    transfer_kpi: "les transferts", use_cases: "les cas d'usage",
  };
  const LOADING = {
    transcribe: ["Je transcris votre demande…", "J'écoute attentivement…"],
    interpret: ["J'interprète votre intention…", "Je comprends votre demande…"],
    answer: ["J'analyse les indicateurs de fraude…", "Je consulte les chiffres en temps réel…", "Je prépare votre réponse…"],
  };
  const pick = (a) => a[Math.floor(Math.random() * a.length)];
  const DECISION_VERB = { APPROVE: "approuver", BLOCK: "bloquer", INVESTIGATE: "investiguer" };

  let stream, audioCtx, analyser, dataBuf, recorder, chunks = [], recStart = 0;
  let recording = false, state = "idle", history = [];
  let pendingAction = null; // { id, decision, label } — action en attente de confirmation orale

  // --- Styles (panneau de conversation) -------------------------------------
  const css = `
  #kvx { position:fixed; bottom:22px; right:22px; z-index:100000; font-family:"Roboto",system-ui,sans-serif; }
  #kvx-panel { width:360px; max-height:64vh; margin-bottom:14px; background:#fff;
    border:1px solid #e8eaed; border-radius:16px; color:#1f1f1f;
    box-shadow:0 4px 8px 3px rgba(60,64,67,.15),0 1px 3px rgba(60,64,67,.3);
    overflow:hidden; display:flex; flex-direction:column; opacity:0; transform:translateY(12px) scale(.98);
    transition:opacity .25s, transform .25s; pointer-events:none; }
  #kvx-panel.show { opacity:1; transform:none; pointer-events:auto; }
  #kvx-head { padding:13px 16px; font-weight:500; font-size:14px; display:flex; align-items:center; gap:9px;
    border-bottom:1px solid #e8eaed; }
  #kvx-head .glow { width:8px; height:8px; border-radius:50%; background:#1a73e8; box-shadow:0 0 8px #1a73e8; }
  #kvx-close { margin-left:auto; background:none; border:none; color:#5f6368; font-size:16px; line-height:1;
    cursor:pointer; padding:3px 6px; border-radius:8px; }
  #kvx-close:hover { background:#f1f3f4; color:#1f1f1f; }
  #kvx-msgs { flex:1; overflow-y:auto; padding:14px; display:flex; flex-direction:column; gap:9px; }
  .kvx-b { padding:9px 13px; border-radius:14px; max-width:84%; font-size:13.5px; line-height:1.45;
    white-space:pre-wrap; animation:kvxin .28s ease both; }
  @keyframes kvxin { from{opacity:0; transform:translateY(8px)} to{opacity:1; transform:none} }
  .kvx-u { align-self:flex-end; background:#1a73e8; color:#fff; border-bottom-right-radius:5px; }
  .kvx-a { align-self:flex-start; background:#f1f3f4; border-bottom-left-radius:5px; }
  .kvx-dots span { display:inline-block; width:6px; height:6px; margin:0 1.5px; background:#9aa0a6;
    border-radius:50%; animation:kvxbounce 1.2s infinite; }
  .kvx-dots span:nth-child(2){animation-delay:.2s} .kvx-dots span:nth-child(3){animation-delay:.4s}
  @keyframes kvxbounce { 0%,60%,100%{transform:translateY(0);opacity:.4} 30%{transform:translateY(-5px);opacity:1} }
  #kvx-status { padding:9px 16px; font-size:12px; color:#5f6368; border-top:1px solid #e8eaed; min-height:18px; }
  #kvx-orb { width:56px; height:56px; border-radius:50%; cursor:pointer; margin-left:auto;
    background:radial-gradient(circle at 32% 30%,#8ab4f8,#1a73e8 60%); color:#fff;
    box-shadow:0 6px 22px rgba(26,115,232,.5); border:none; font-size:22px; }
  #kvx.listening #kvx-orb { box-shadow:0 0 0 8px rgba(26,115,232,.18),0 6px 26px rgba(26,115,232,.7); }`;

  const root = document.createElement("div");
  root.id = "kvx";
  root.innerHTML =
    '<div id="kvx-panel"><div id="kvx-head"><span class="glow"></span>Assistant KiVendTout' +
    '<button id="kvx-close" title="Fermer" aria-label="Fermer">✕</button></div>' +
    '<div id="kvx-msgs"></div><div id="kvx-status">Maintenez P ou cliquez le micro.</div></div>' +
    '<button id="kvx-orb" data-voice-trigger title="Parler (ou maintenir P)">🎙️</button>';

  const $ = (id) => document.getElementById(id);
  function ready(fn) { if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }

  ready(() => {
    const style = document.createElement("style"); style.textContent = css;
    document.head.appendChild(style); document.body.appendChild(root);
    rehydrate();
    // Si l'app a déjà un micro intégré (barre de commande), on masque l'orbe flottante.
    if (document.querySelector(".appbar [data-voice-trigger]")) $("kvx-orb").style.display = "none";
    // Fermer le panneau (il se rouvre automatiquement à la prochaine commande vocale).
    $("kvx-close").addEventListener("click", (e) => {
      e.stopPropagation(); $("kvx-panel").classList.remove("show");
    });
    // Liaisons souris : micro(s) + suggestions cliquables
    document.addEventListener("click", (e) => {
      const trig = e.target.closest("[data-voice-trigger]");
      if (trig) { e.preventDefault(); toggle(); return; }
      const cmd = e.target.closest("[data-cmd]");
      if (cmd) { e.preventDefault(); runText(cmd.getAttribute("data-cmd")); }
    });
  });

  function setState(s) { state = s; root.className = s === "idle" ? "" : s; if (s !== "idle") $("kvx-panel").classList.add("show"); }
  function setStatus(t) { const e = $("kvx-status"); if (e) e.textContent = t; }
  function setTriggerLive(on) { document.querySelectorAll("[data-voice-trigger]").forEach((b) => b.classList.toggle("live", on)); }
  function scroll() { const m = $("kvx-msgs"); if (m) m.scrollTop = m.scrollHeight; }
  function addMsg(role, text, persist = true) {
    $("kvx-panel").classList.add("show");
    const d = document.createElement("div");
    d.className = "kvx-b " + (role === "user" ? "kvx-u" : "kvx-a");
    d.textContent = text; $("kvx-msgs").appendChild(d); scroll();
    if (persist) { history.push({ role, text }); saveHistory(); }
  }
  function thinkingBubble() {
    const d = document.createElement("div"); d.className = "kvx-b kvx-a kvx-dots";
    d.innerHTML = "<span></span><span></span><span></span>"; $("kvx-msgs").appendChild(d); scroll(); return d;
  }
  function saveHistory() { try { sessionStorage.setItem("kvxChat", JSON.stringify(history.slice(-20))); } catch (e) {} }
  function rehydrate() {
    try { history = JSON.parse(sessionStorage.getItem("kvxChat") || "[]"); } catch (e) { history = []; }
    history.forEach((m) => addMsg(m.role, m.text, false));
    if (history.length) $("kvx-panel").classList.add("show");
  }
  // Voix : on privilegie le TTS NEURONAL local (Piper, /api/voice/tts) ; si le
  // service est indisponible, on retombe sur la voix de synthese du navigateur.
  let ttsMode = null; // null = inconnu, true = Piper OK, false = repli navigateur

  async function piperSpeak(text) {
    const r = await fetch(BASE + "/tts", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!r.ok) throw new Error("tts " + r.status);
    const blob = await r.blob();
    if (!blob || blob.size < 1000) throw new Error("tts vide");
    const url = URL.createObjectURL(blob);
    setState("speaking");
    await new Promise((res) => {
      const a = new Audio(url);
      a.onended = res; a.onerror = res;
      a.play().catch(res);
    });
    URL.revokeObjectURL(url);
  }

  function browserSpeak(text) {
    return new Promise((res) => {
      if (!("speechSynthesis" in window) || !text) return res();
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text); u.lang = "fr-FR"; u.rate = 1.04;
      u.onend = res; u.onerror = res; setState("speaking"); window.speechSynthesis.speak(u);
    });
  }

  async function speak(text) {
    if (!text) return;
    if (ttsMode === false) return browserSpeak(text);   // repli definitif si service KO
    try { await piperSpeak(text); ttsMode = true; }       // voix neuronale
    catch (e) { if (ttsMode === null) ttsMode = false; await browserSpeak(text); }
  }
  async function respond(text) { addMsg("asst", text); await speak(text); }

  async function ensureAudio() {
    if (stream) return;
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const src = audioCtx.createMediaStreamSource(stream);
    analyser = audioCtx.createAnalyser(); analyser.fftSize = 512;
    dataBuf = new Uint8Array(analyser.fftSize); src.connect(analyser);
  }
  async function startListen() {
    if (recording || state !== "idle") return;
    try { await ensureAudio(); } catch (e) { setStatus("❌ Micro refusé."); $("kvx-panel").classList.add("show"); return; }
    if (audioCtx.state === "suspended") await audioCtx.resume();
    chunks = []; recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = process;
    recorder.start(); recording = true; recStart = performance.now();
    setState("listening"); setTriggerLive(true); setStatus("🎧 Je vous écoute…");
  }
  function stopListen() {
    if (!recording) return;
    recording = false; setTriggerLive(false);
    if (recorder && recorder.state === "recording") recorder.stop();
  }
  function toggle() { if (recording) stopListen(); else startListen(); }

  async function postAudio(path, blob) {
    const fd = new FormData(); fd.append("audio", blob, "cmd.webm");
    const r = await fetch(BASE + path, { method: "POST", body: fd }); return r.json();
  }
  async function postJson(path, body) {
    const r = await fetch(BASE + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return r.json();
  }

  async function process() {
    const blob = new Blob(chunks, { type: "audio/webm" });
    if (performance.now() - recStart < MIN_REC_MS || blob.size < 1200) { setState("idle"); setStatus("Maintenez P ou cliquez le micro."); return; }
    setState("thinking"); const dots = thinkingBubble();
    try {
      setStatus(pick(LOADING.transcribe));
      const stt = await postAudio("/transcribe", blob);
      const text = (stt.text || "").trim();
      if (!text) { dots.remove(); setState("idle"); setStatus("Je n'ai rien entendu."); return; }
      dots.remove();
      if (await confirmIfPending(text)) { setState("idle"); setStatus("Maintenez P ou cliquez le micro."); return; }
      addMsg("user", text);
      const dots2 = thinkingBubble(); setStatus(pick(LOADING.interpret));
      const intent = await postJson("/intent", { text }); dots2.remove();
      await dispatch(intent, text);
    } catch (e) { dots.remove(); addMsg("asst", "❌ Service vocal injoignable (port 8100 ?)"); }
    setState("idle"); setStatus("Maintenez P ou cliquez le micro.");
  }

  // Commande texte (barre de commande / suggestion cliquée) = même pipeline, sans audio.
  async function runText(text) {
    text = (text || "").trim(); if (!text) return;
    $("kvx-panel").classList.add("show");
    setState("thinking");
    if (await confirmIfPending(text)) { setState("idle"); setStatus("Maintenez P ou cliquez le micro."); return; }
    addMsg("user", text);
    const dots = thinkingBubble(); setStatus(pick(LOADING.interpret));
    try { const intent = await postJson("/intent", { text }); dots.remove(); await dispatch(intent, text); }
    catch (e) { dots.remove(); addMsg("asst", "❌ Service vocal injoignable (port 8100 ?)"); }
    setState("idle"); setStatus("Maintenez P ou cliquez le micro.");
  }

  async function dispatch(intent, text) {
    if (intent.action === "navigate" && intent.view_file) {
      await respond("J'ouvre " + (VIEW_LABELS[intent.view] || "la vue demandée") + ".");
      navigate(intent.view_file);
    } else if (intent.action === "filter") {
      await applyFilter(intent);
    } else if (intent.action === "act") {
      await handleAction(intent);
    } else if (intent.action === "ask") {
      const dots = thinkingBubble(); setStatus(pick(LOADING.answer));
      const a = await postJson("/ask", { text }); dots.remove();
      await respond(a.answer || "Je n'ai pas trouvé l'information dans les indicateurs.");
    } else {
      await respond("Je n'ai pas compris : « " + text + " ».");
    }
  }

  function applyOnPage(field, code) {
    // Contrat V2 : la page expose applyVoiceFilter(field, code) (chips Material).
    if (typeof window.applyVoiceFilter === "function") return !!window.applyVoiceFilter(field, code);
    // Repli V1 : <select id="filter-...">.
    const sel = document.getElementById("filter-" + field);
    if (!sel) return false;
    sel.value = code;
    if (typeof window.loadAlerts === "function") window.loadAlerts();
    else sel.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }
  async function applyFilter(intent) {
    const verb = intent.field === "severity" ? "sévérité " : "statut ";
    if (applyOnPage(intent.field, intent.value_code)) {
      await respond("Je filtre les alertes : " + verb + (intent.value_label || "").toLowerCase() + ".");
    } else {
      try { sessionStorage.setItem("kvxPendingFilter", JSON.stringify({ field: intent.field, code: intent.value_code, label: intent.value_label })); } catch (e) {}
      await respond("J'ouvre la fraude et j'applique le filtre " + verb + (intent.value_label || "").toLowerCase() + ".");
      navigate("fraud_dashboard.html");
    }
  }
  // ===== Actions sur les alertes (avec confirmation humaine obligatoire) =====
  async function handleAction(intent) {
    // Les actions n'existent que sur la page Fraude (qui expose window.KVFraud).
    if (!window.KVFraud) {
      await respond("J'ouvre la vue fraude : redites votre action une fois la page affichée.");
      return navigate("fraud_dashboard.html");
    }
    const al = window.KVFraud.resolveRef(intent.target);
    if (!al) {
      await respond("Je ne trouve pas cette alerte. Dites par exemple : « approuve l'alerte numéro 2 ».");
      return;
    }
    if (!al.pending) {
      await respond("L'alerte numéro " + al.n + " est déjà traitée (" + al.statusLabel + "). Aucune action possible.");
      return;
    }
    const verb = DECISION_VERB[intent.decision] || (intent.decision_label || "").toLowerCase() || "traiter";
    pendingAction = {
      id: al.id, decision: intent.decision,
      label: verb + " l'alerte numéro " + al.n + " (client " + al.customer + ", sévérité " + al.severityLabel.toLowerCase() + ")",
    };
    await respond("Vous voulez " + pendingAction.label + ". Je confirme ? Dites oui ou non.");
  }

  // Intercepte la réponse oui/non quand une action est en attente. Renvoie true si consommé.
  async function confirmIfPending(text) {
    if (!pendingAction) return false;
    const t = " " + (text || "").toLowerCase()
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "") + " ";
    const yes = /\b(oui|ouais|ok|okay|confirme|confirmer|valide|valider|vas[- ]?y|d ?accord|c ?est bon|go|parfait)\b/.test(t);
    const no = /\b(non|annule|annuler|laisse|laisser|stop|abandonne|negatif|surtout pas|pas ca)\b/.test(t);
    addMsg("user", text);
    if (!yes && !no) {
      await respond("Je n'ai pas compris. Confirmez-vous : " + pendingAction.label + " ? Dites oui ou non.");
      return true;
    }
    const act = pendingAction; pendingAction = null;
    if (no) { await respond("Très bien, j'annule. Rien n'a été modifié."); return true; }
    const dots = thinkingBubble();
    try {
      const res = await window.KVFraud.decide(act.id, act.decision);
      dots.remove();
      await respond(res && res.ok
        ? "C'est fait : " + act.label + "."
        : "Échec de la décision (" + ((res && res.reason) || "refusée") + "). Rien n'a été modifié.");
    } catch (e) { dots.remove(); await respond("La décision n'a pas pu être enregistrée. Rien n'a été modifié."); }
    return true;
  }

  function applyPendingFilter() {
    let pf; try { pf = JSON.parse(sessionStorage.getItem("kvxPendingFilter") || "null"); } catch (e) {}
    if (!pf || !document.getElementById("filter-" + pf.field)) return;
    sessionStorage.removeItem("kvxPendingFilter");
    setTimeout(() => applyOnPage(pf.field, pf.code), 900);
  }
  ready(applyPendingFilter);

  function navigate(file) { setTimeout(() => { window.location.href = file; }, 500); }

  // Push-to-talk P
  function typing(el) { return el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable); }
  document.addEventListener("keydown", (e) => {
    if (e.repeat || (e.key || "").toLowerCase() !== "p" || typing(e.target)) return;
    e.preventDefault(); startListen();
  });
  document.addEventListener("keyup", (e) => { if ((e.key || "").toLowerCase() === "p") stopListen(); });

  window.KVVoice = { toggle, start: startListen, stop: stopListen, runText };
})();

/*
 * Assistant vocal KiVendTout (branche genai-voice) — mode live mains-libres.
 *
 * On lance une fois -> ecoute en continu. Detection de silence (VAD) pour
 * decouper les phrases. Chaque phrase part au service vocal LOCAL (:8100,
 * faster-whisper + Ollama), s'affiche dans un panneau type chatbot, et la
 * reponse est lue a voix haute (TTS macOS). Reste 100% local (pas l'API
 * Google du navigateur) -> argument RGPD/local preserve.
 *
 * Inclure dans chaque page : <script src="voice_control.js"></script>
 */
(function () {
  "use strict";

  const VOICE_API = (window.VOICE_API_URL || "http://localhost:8100") + "/api/voice/command";
  const SILENCE_MS = 1100;   // silence apres parole -> fin de phrase
  const THRESHOLD = 0.018;   // seuil RMS de detection de voix
  const MIN_UTTER_MS = 350;  // duree mini d'un segment

  const VIEW_LABELS = {
    overview: "la vue d'ensemble", fraud: "la vue fraude",
    fraud_types: "les typologies de fraude", id_cards: "la vue identite",
    transfer_kpi: "les transferts", use_cases: "les cas d'usage",
  };

  // --- Etat ------------------------------------------------------------------
  let stream, audioCtx, analyser, recorder, dataBuf;
  let chunks = [];
  let running = false;      // assistant actif
  let busy = false;         // en train de traiter/parler -> on n'ecoute pas
  let hadSpeech = false;
  let silenceStart = null;
  let segStart = 0;

  // --- UI ---------------------------------------------------------------------
  const css = `
    #kv-asst { position:fixed; bottom:24px; right:24px; z-index:99999;
      width:340px; max-height:70vh; display:none; flex-direction:column;
      background:#0d1117; color:#e6edf3; border:1px solid #30363d;
      border-radius:14px; box-shadow:0 10px 40px rgba(0,0,0,.45);
      font-family:-apple-system,system-ui,sans-serif; overflow:hidden; }
    #kv-asst.open { display:flex; }
    #kv-asst-head { display:flex; align-items:center; gap:8px; padding:12px 14px;
      background:#161b22; border-bottom:1px solid #30363d; font-weight:600; }
    #kv-dot { width:10px; height:10px; border-radius:50%; background:#6e7681; }
    #kv-dot.live { background:#2ea043; animation:kvpulse 1.2s infinite; }
    @keyframes kvpulse { 0%,100%{opacity:1} 50%{opacity:.3} }
    #kv-asst-msgs { flex:1; overflow-y:auto; padding:12px; display:flex;
      flex-direction:column; gap:8px; }
    .kv-msg { padding:8px 12px; border-radius:12px; max-width:85%; font-size:14px;
      line-height:1.4; white-space:pre-wrap; }
    .kv-user { align-self:flex-end; background:#1f6feb; color:#fff;
      border-bottom-right-radius:4px; }
    .kv-asst { align-self:flex-start; background:#21262d;
      border-bottom-left-radius:4px; }
    #kv-asst-status { padding:8px 14px; font-size:12px; color:#8b949e;
      border-top:1px solid #30363d; }
    #kv-btn { position:fixed; bottom:24px; right:24px; z-index:100000;
      width:56px; height:56px; border-radius:50%; border:none; font-size:24px;
      cursor:pointer; background:#1f6feb; color:#fff;
      box-shadow:0 4px 14px rgba(0,0,0,.3); transition:transform .1s; }
    #kv-btn:active { transform:scale(.94); }
    #kv-btn.live { background:#d62828; }`;
  const style = document.createElement("style");
  style.textContent = css;

  const panel = document.createElement("div");
  panel.id = "kv-asst";
  panel.innerHTML =
    '<div id="kv-asst-head"><span id="kv-dot"></span>' +
    "<span>Assistant KiVendTout</span></div>" +
    '<div id="kv-asst-msgs"></div>' +
    '<div id="kv-asst-status">Cliquez le micro pour demarrer.</div>';

  const btn = document.createElement("button");
  btn.id = "kv-btn";
  btn.textContent = "🎙️";
  btn.title = "Assistant vocal (cliquer pour activer/couper)";

  document.addEventListener("DOMContentLoaded", () => {
    document.head.appendChild(style);
    document.body.appendChild(panel);
    document.body.appendChild(btn);
    // Reprise auto apres navigation vocale
    if (sessionStorage.getItem("kvAsstOn") === "1") {
      panel.classList.add("open");
      start().catch(() => setStatus("▶︎ Cliquez le micro pour reprendre l'ecoute."));
    }
  });

  const msgs = () => document.getElementById("kv-asst-msgs");
  const dot = () => document.getElementById("kv-dot");
  function setStatus(t) {
    const s = document.getElementById("kv-asst-status");
    if (s) s.textContent = t;
  }
  function addMsg(role, text) {
    const d = document.createElement("div");
    d.className = "kv-msg " + (role === "user" ? "kv-user" : "kv-asst");
    d.textContent = text;
    msgs().appendChild(d);
    msgs().scrollTop = msgs().scrollHeight;
  }

  function speak(text) {
    return new Promise((res) => {
      if (!("speechSynthesis" in window) || !text) return res();
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = "fr-FR";
      u.onend = res;
      u.onerror = res;
      window.speechSynthesis.speak(u);
    });
  }

  // --- Boucle d'ecoute --------------------------------------------------------
  async function start() {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") await audioCtx.resume();
    const src = audioCtx.createMediaStreamSource(stream);
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 512;
    dataBuf = new Uint8Array(analyser.fftSize);
    src.connect(analyser);

    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = onSegmentEnd;

    running = true;
    sessionStorage.setItem("kvAsstOn", "1");
    btn.classList.add("live");
    btn.textContent = "⏹";
    dot().classList.add("live");
    panel.classList.add("open");
    setStatus("🎧 J'ecoute… parlez naturellement.");
    startSegment();
    requestAnimationFrame(monitor);
  }

  function startSegment() {
    chunks = [];
    hadSpeech = false;
    silenceStart = null;
    segStart = performance.now();
    if (recorder && recorder.state === "inactive") recorder.start();
  }

  function monitor() {
    if (!running) return;
    if (!busy && recorder && recorder.state === "recording") {
      analyser.getByteTimeDomainData(dataBuf);
      let sum = 0;
      for (let i = 0; i < dataBuf.length; i++) {
        const x = (dataBuf[i] - 128) / 128;
        sum += x * x;
      }
      const rms = Math.sqrt(sum / dataBuf.length);
      if (rms > THRESHOLD) {
        hadSpeech = true;
        silenceStart = null;
      } else if (hadSpeech) {
        if (silenceStart === null) silenceStart = performance.now();
        else if (
          performance.now() - silenceStart > SILENCE_MS &&
          performance.now() - segStart > MIN_UTTER_MS
        ) {
          busy = true;
          setStatus("⏳ Transcription…");
          recorder.stop(); // -> onSegmentEnd
        }
      }
    }
    requestAnimationFrame(monitor);
  }

  async function onSegmentEnd() {
    const blob = new Blob(chunks, { type: "audio/webm" });
    if (hadSpeech) await handle(blob);
    busy = false;
    if (running) {
      setStatus("🎧 J'ecoute…");
      startSegment();
    }
  }

  async function handle(blob) {
    const fd = new FormData();
    fd.append("audio", blob, "cmd.webm");
    let data;
    try {
      const r = await fetch(VOICE_API, { method: "POST", body: fd });
      data = await r.json();
    } catch (e) {
      addMsg("asst", "❌ Service vocal injoignable (port 8100 lance ?)");
      return;
    }
    const t = (data.transcript || "").trim();
    if (!t) return; // segment sans parole exploitable
    addMsg("user", t);

    const intent = data.intent || {};
    if (intent.action === "navigate" && intent.view_file) {
      const reply = "J'ouvre " + (VIEW_LABELS[intent.view] || "la vue demandee") + ".";
      addMsg("asst", reply);
      await speak(reply);
      window.location.href = intent.view_file; // l'assistant reprend au reload
    } else if (intent.action === "explain" && data.narration) {
      addMsg("asst", data.narration);
      await speak(data.narration);
    } else {
      const reply = "Je n'ai pas compris : « " + t + " »";
      addMsg("asst", reply);
      await speak(reply);
    }
  }

  function stop() {
    running = false;
    sessionStorage.removeItem("kvAsstOn");
    btn.classList.remove("live");
    btn.textContent = "🎙️";
    dot().classList.remove("live");
    setStatus("⏸ Assistant en pause.");
    try {
      if (recorder && recorder.state === "recording") recorder.stop();
      if (stream) stream.getTracks().forEach((t) => t.stop());
      if (audioCtx) audioCtx.close();
    } catch (e) {}
    window.speechSynthesis.cancel();
  }

  btn.addEventListener("click", () => {
    if (running) stop();
    else start().catch((e) => setStatus("❌ Micro refuse : " + e.message));
  });
})();

/*
 * Controle vocal de KiVendTout (branche genai-voice).
 *
 * - Capture micro via MediaRecorder
 * - Envoie l'audio au service vocal local (port 8100)
 * - Navigue dans le dashboard OU lit la narration a voix haute (SpeechSynthesis)
 *
 * Inclure dans une page : <script src="voice_control.js"></script>
 * Le bouton micro flottant est injecte automatiquement.
 */
(function () {
  "use strict";

  const VOICE_API = (window.VOICE_API_URL || "http://localhost:8100") + "/api/voice/command";

  let mediaRecorder = null;
  let chunks = [];
  let recording = false;

  // --- UI : bouton micro flottant + zone de statut --------------------------
  const btn = document.createElement("button");
  btn.id = "kv-voice-btn";
  btn.textContent = "🎙️";
  btn.title = "Commande vocale (cliquer pour parler)";
  Object.assign(btn.style, {
    position: "fixed", bottom: "24px", right: "24px", zIndex: 9999,
    width: "56px", height: "56px", borderRadius: "50%", border: "none",
    fontSize: "24px", cursor: "pointer", background: "#1f6feb", color: "#fff",
    boxShadow: "0 4px 14px rgba(0,0,0,.3)",
  });
  const status = document.createElement("div");
  Object.assign(status.style, {
    position: "fixed", bottom: "90px", right: "24px", zIndex: 9999,
    maxWidth: "320px", padding: "8px 12px", borderRadius: "8px",
    background: "rgba(0,0,0,.8)", color: "#fff", fontSize: "13px",
    display: "none",
  });
  document.addEventListener("DOMContentLoaded", () => {
    document.body.appendChild(btn);
    document.body.appendChild(status);
  });

  function setStatus(msg) {
    status.textContent = msg;
    status.style.display = msg ? "block" : "none";
  }

  function speak(text) {
    if (!("speechSynthesis" in window) || !text) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "fr-FR";
    window.speechSynthesis.speak(u);
  }

  // --- Enregistrement --------------------------------------------------------
  async function startRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    chunks = [];
    mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
    mediaRecorder.onstop = sendAudio;
    mediaRecorder.start();
    recording = true;
    btn.style.background = "#d62828";
    setStatus("🔴 Parlez… (re-cliquez pour envoyer)");
  }

  function stopRecording() {
    if (mediaRecorder) mediaRecorder.stop();
    recording = false;
    btn.style.background = "#1f6feb";
    setStatus("⏳ Transcription…");
  }

  async function sendAudio() {
    const blob = new Blob(chunks, { type: "audio/webm" });
    const fd = new FormData();
    fd.append("audio", blob, "command.webm");
    try {
      const res = await fetch(VOICE_API, { method: "POST", body: fd });
      const data = await res.json();
      handleResult(data);
    } catch (err) {
      setStatus("❌ Service vocal injoignable (port 8100 lance ?)");
    }
  }

  // --- Application de l'intention --------------------------------------------
  function handleResult(data) {
    const intent = data.intent || {};
    setStatus("🗣️ « " + (data.transcript || "") + " »");

    if (intent.action === "navigate" && intent.view_file) {
      speak("J'ouvre la vue demandée.");
      setTimeout(() => (window.location.href = intent.view_file), 600);
    } else if (intent.action === "explain" && data.narration) {
      setStatus("📊 " + data.narration);
      speak(data.narration);
    } else {
      speak("Je n'ai pas compris la commande.");
      setStatus("🤔 Commande non reconnue : « " + (data.transcript || "") + " »");
    }
  }

  btn.addEventListener("click", () => (recording ? stopRecording() : startRecording()));
})();

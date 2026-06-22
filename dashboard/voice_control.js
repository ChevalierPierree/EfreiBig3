/*
 * Assistant vocal KiVendTout — "Jarvis" (branche genai-voice).
 *
 * - Push-to-talk : MAINTENIR la touche P pour parler, relacher pour envoyer.
 * - 100% local : faster-whisper (STT) + Ollama/llama3.2 (intention + reponses).
 * - Sait : naviguer, FILTRER les alertes (severite / statut), repondre a des
 *   questions sur les chiffres, le tout dans un panneau type chatbot avec
 *   orbe reactive a la voix, chargements personnalises et reponse parlee (TTS).
 *
 * Inclure dans chaque page : <script src="voice_control.js"></script>
 */
(function () {
  "use strict";

  const BASE = (window.VOICE_API_URL || "http://localhost:8100") + "/api/voice";
  const MIN_REC_MS = 300;

  const VIEW_LABELS = {
    overview: "la vue d'ensemble", fraud: "la vue fraude",
    fraud_types: "les typologies de fraude", id_cards: "la vue identite",
    transfer_kpi: "les transferts", use_cases: "les cas d'usage",
  };
  // Chargements "personnalises" par etape (fait partie de l'experience).
  const LOADING = {
    transcribe: ["Je transcris votre demande…", "J'ecoute attentivement…"],
    interpret: ["J'interprete votre intention…", "Je comprends ce que vous voulez…"],
    answer: ["J'analyse les indicateurs de fraude…", "Je consulte les chiffres en temps reel…",
             "Je prepare votre reponse…"],
    act: ["J'execute…", "Tout de suite…"],
  };
  const pick = (a) => a[Math.floor(Math.random() * a.length)];

  // --- Etat ------------------------------------------------------------------
  let stream, audioCtx, analyser, dataBuf, recorder, chunks = [], recStart = 0;
  let recording = false, state = "idle"; // idle|listening|thinking|speaking
  let history = [];

  // --- Styles ----------------------------------------------------------------
  const css = `
  #kvx { position:fixed; bottom:22px; right:22px; z-index:100000;
    font-family:-apple-system,system-ui,'Segoe UI',sans-serif; }
  #kvx-panel { width:360px; max-height:64vh; margin-bottom:14px;
    background:rgba(13,17,23,.72); backdrop-filter:blur(18px) saturate(140%);
    -webkit-backdrop-filter:blur(18px) saturate(140%);
    border:1px solid rgba(255,255,255,.10); border-radius:18px; color:#e6edf3;
    box-shadow:0 20px 60px rgba(0,0,0,.5); overflow:hidden; display:flex;
    flex-direction:column; opacity:0; transform:translateY(12px) scale(.98);
    transition:opacity .25s, transform .25s; pointer-events:none; }
  #kvx-panel.show { opacity:1; transform:none; pointer-events:auto; }
  #kvx-head { padding:13px 16px; font-weight:600; font-size:14px;
    display:flex; align-items:center; gap:9px;
    border-bottom:1px solid rgba(255,255,255,.08);
    background:linear-gradient(90deg,rgba(56,139,253,.18),transparent); }
  #kvx-head .glow { width:8px; height:8px; border-radius:50%; background:#388bfd;
    box-shadow:0 0 10px #388bfd; }
  #kvx-msgs { flex:1; overflow-y:auto; padding:14px; display:flex;
    flex-direction:column; gap:9px; scroll-behavior:smooth; }
  #kvx-msgs::-webkit-scrollbar { width:6px; }
  #kvx-msgs::-webkit-scrollbar-thumb { background:rgba(255,255,255,.15); border-radius:3px; }
  .kvx-b { padding:9px 13px; border-radius:14px; max-width:84%; font-size:13.5px;
    line-height:1.45; white-space:pre-wrap; animation:kvxin .28s ease both; }
  @keyframes kvxin { from{opacity:0; transform:translateY(8px)} to{opacity:1; transform:none} }
  .kvx-u { align-self:flex-end; background:linear-gradient(135deg,#1f6feb,#388bfd);
    color:#fff; border-bottom-right-radius:5px; }
  .kvx-a { align-self:flex-start; background:rgba(255,255,255,.07);
    border:1px solid rgba(255,255,255,.06); border-bottom-left-radius:5px; }
  .kvx-dots span { display:inline-block; width:6px; height:6px; margin:0 1.5px;
    background:#8b949e; border-radius:50%; animation:kvxbounce 1.2s infinite; }
  .kvx-dots span:nth-child(2){animation-delay:.2s} .kvx-dots span:nth-child(3){animation-delay:.4s}
  @keyframes kvxbounce { 0%,60%,100%{transform:translateY(0);opacity:.4} 30%{transform:translateY(-5px);opacity:1} }
  #kvx-status { padding:9px 16px; font-size:12px; color:#8b949e;
    border-top:1px solid rgba(255,255,255,.08); min-height:18px; transition:color .2s; }
  #kvx-orbwrap { display:flex; align-items:center; gap:12px; justify-content:flex-end; }
  #kvx-hint { font-size:12px; color:#8b949e; background:rgba(13,17,23,.7);
    padding:7px 12px; border-radius:20px; border:1px solid rgba(255,255,255,.08);
    backdrop-filter:blur(8px); white-space:nowrap; }
  #kvx-hint b { color:#e6edf3; background:rgba(255,255,255,.12); padding:1px 7px;
    border-radius:6px; }
  #kvx-orb { position:relative; width:62px; height:62px; border-radius:50%;
    cursor:pointer; flex:none;
    background:radial-gradient(circle at 32% 30%,#5fb3ff,#1f6feb 55%,#0d3b8c);
    box-shadow:0 0 0 0 rgba(56,139,253,.5),0 6px 22px rgba(31,111,235,.5);
    transition:transform .08s, box-shadow .25s; }
  #kvx-orb::after { content:''; position:absolute; inset:-6px; border-radius:50%;
    border:2px solid transparent; }
  #kvx.listening #kvx-orb { box-shadow:0 0 0 8px rgba(56,139,253,.18),0 6px 26px rgba(56,139,253,.7); }
  #kvx.thinking #kvx-orb::after { border-top-color:#5fb3ff; border-right-color:#5fb3ff;
    animation:kvxspin .8s linear infinite; }
  #kvx.speaking #kvx-orb { animation:kvxpulse 1s ease-in-out infinite; }
  @keyframes kvxspin { to{transform:rotate(360deg)} }
  @keyframes kvxpulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.08)} }`;

  const root = document.createElement("div");
  root.id = "kvx";
  root.innerHTML =
    '<div id="kvx-panel">' +
      '<div id="kvx-head"><span class="glow"></span>Assistant KiVendTout</div>' +
      '<div id="kvx-msgs"></div>' +
      '<div id="kvx-status">Maintenez P pour parler.</div>' +
    "</div>" +
    '<div id="kvx-orbwrap">' +
      '<div id="kvx-hint">Maintenez <b>P</b> pour parler</div>' +
      '<div id="kvx-orb" title="Maintenir P (ou ce cercle) pour parler"></div>' +
    "</div>";

  const $ = (id) => document.getElementById(id);
  function ready(fn){ if(document.readyState!=="loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }

  ready(() => {
    const style = document.createElement("style"); style.textContent = css;
    document.head.appendChild(style); document.body.appendChild(root);
    rehydrate();
    applyPendingFilter();
  });

  // --- UI helpers ------------------------------------------------------------
  function setState(s){ state=s; root.className = s==="idle" ? "" : s;
    if(s!=="idle") $("kvx-panel").classList.add("show"); }
  function setStatus(t){ const e=$("kvx-status"); if(e) e.textContent=t; }
  function scroll(){ const m=$("kvx-msgs"); if(m) m.scrollTop=m.scrollHeight; }

  function addMsg(role, text, persist=true){
    $("kvx-panel").classList.add("show");
    const d=document.createElement("div");
    d.className="kvx-b "+(role==="user"?"kvx-u":"kvx-a");
    d.textContent=text; $("kvx-msgs").appendChild(d); scroll();
    if(persist){ history.push({role,text}); saveHistory(); }
    return d;
  }
  function thinkingBubble(){
    const d=document.createElement("div"); d.className="kvx-b kvx-a kvx-dots";
    d.innerHTML="<span></span><span></span><span></span>";
    $("kvx-msgs").appendChild(d); scroll(); return d;
  }
  function saveHistory(){ try{ sessionStorage.setItem("kvxChat", JSON.stringify(history.slice(-20))); }catch(e){} }
  function rehydrate(){
    try{ history=JSON.parse(sessionStorage.getItem("kvxChat")||"[]"); }catch(e){ history=[]; }
    history.forEach(m=>addMsg(m.role,m.text,false));
    if(history.length) $("kvx-panel").classList.add("show");
  }

  function speak(text){
    return new Promise((res)=>{
      if(!("speechSynthesis" in window)||!text) return res();
      window.speechSynthesis.cancel();
      const u=new SpeechSynthesisUtterance(text); u.lang="fr-FR"; u.rate=1.04;
      u.onend=res; u.onerror=res; setState("speaking");
      window.speechSynthesis.speak(u);
    });
  }
  async function respond(text){ addMsg("asst", text); await speak(text); }

  // --- Audio / enregistrement ------------------------------------------------
  async function ensureAudio(){
    if(stream) return;
    stream=await navigator.mediaDevices.getUserMedia({audio:true});
    audioCtx=new (window.AudioContext||window.webkitAudioContext)();
    const src=audioCtx.createMediaStreamSource(stream);
    analyser=audioCtx.createAnalyser(); analyser.fftSize=512;
    dataBuf=new Uint8Array(analyser.fftSize); src.connect(analyser);
  }
  function reactLoop(){
    if(!recording) return;
    analyser.getByteTimeDomainData(dataBuf);
    let sum=0; for(let i=0;i<dataBuf.length;i++){const x=(dataBuf[i]-128)/128; sum+=x*x;}
    const rms=Math.sqrt(sum/dataBuf.length);
    const orb=$("kvx-orb"); if(orb) orb.style.transform="scale("+(1+Math.min(rms*4,.6))+")";
    requestAnimationFrame(reactLoop);
  }
  async function startListen(){
    if(recording || state!=="idle") return;
    try{ await ensureAudio(); }catch(e){ setStatus("❌ Micro refuse."); $("kvx-panel").classList.add("show"); return; }
    if(audioCtx.state==="suspended") await audioCtx.resume();
    chunks=[]; recorder=new MediaRecorder(stream);
    recorder.ondataavailable=e=>chunks.push(e.data);
    recorder.onstop=process;
    recorder.start(); recording=true; recStart=performance.now();
    setState("listening"); setStatus("🎧 Je vous ecoute… (relachez P pour envoyer)");
    reactLoop();
  }
  function stopListen(){
    if(!recording) return;
    recording=false; const orb=$("kvx-orb"); if(orb) orb.style.transform="";
    if(recorder && recorder.state==="recording") recorder.stop();
  }

  // --- Pipeline (etapes -> chargements personnalises) ------------------------
  async function postAudio(path, blob){
    const fd=new FormData(); fd.append("audio", blob, "cmd.webm");
    const r=await fetch(BASE+path,{method:"POST",body:fd}); return r.json();
  }
  async function postJson(path, body){
    const r=await fetch(BASE+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    return r.json();
  }

  async function process(){
    const blob=new Blob(chunks,{type:"audio/webm"});
    if(performance.now()-recStart < MIN_REC_MS || blob.size<1200){ setState("idle"); setStatus("Maintenez P pour parler."); return; }
    setState("thinking");
    const dots=thinkingBubble();
    try{
      setStatus(pick(LOADING.transcribe));
      const stt=await postAudio("/transcribe", blob);
      const text=(stt.text||"").trim();
      if(!text){ dots.remove(); setState("idle"); setStatus("Je n'ai rien entendu."); return; }
      dots.remove(); addMsg("user", text);

      const dots2=thinkingBubble();
      setStatus(pick(LOADING.interpret));
      const intent=await postJson("/intent", {text});
      dots2.remove();
      await dispatch(intent, text);
    }catch(e){
      dots.remove(); addMsg("asst","❌ Service vocal injoignable (port 8100 lance ?)");
    }
    setState("idle"); setStatus("Maintenez P pour parler.");
  }

  async function dispatch(intent, text){
    if(intent.action==="navigate" && intent.view_file){
      await respond("J'ouvre "+(VIEW_LABELS[intent.view]||"la vue demandee")+".");
      navigate(intent.view_file);
    } else if(intent.action==="filter"){
      await applyFilter(intent);
    } else if(intent.action==="ask"){
      const dots=thinkingBubble(); setStatus(pick(LOADING.answer));
      const a=await postJson("/ask", {text}); dots.remove();
      await respond(a.answer || "Je n'ai pas trouve l'information dans les indicateurs.");
    } else {
      await respond("Je n'ai pas compris : « "+text+" ».");
    }
  }

  // --- Actions : filtre reel sur la page fraude ------------------------------
  function applyOnPage(field, code){
    const sel=document.getElementById("filter-"+field);
    if(!sel) return false;
    sel.value=code;
    if(typeof window.loadAlerts==="function") window.loadAlerts();
    else sel.dispatchEvent(new Event("change",{bubbles:true}));
    return true;
  }
  async function applyFilter(intent){
    const verb = intent.field==="severity" ? "severite " : "statut ";
    if(applyOnPage(intent.field, intent.value_code)){
      await respond("Je filtre les alertes : "+verb+intent.value_label.toLowerCase()+".");
    } else {
      // pas sur la vue fraude -> on memorise et on y va
      try{ sessionStorage.setItem("kvxPendingFilter", JSON.stringify(
        {field:intent.field, code:intent.value_code, label:intent.value_label})); }catch(e){}
      await respond("J'ouvre la fraude et j'applique le filtre "+verb+intent.value_label.toLowerCase()+".");
      navigate("fraud_dashboard.html");
    }
  }
  function applyPendingFilter(){
    let pf; try{ pf=JSON.parse(sessionStorage.getItem("kvxPendingFilter")||"null"); }catch(e){}
    if(!pf || !document.getElementById("filter-"+pf.field)) return;
    sessionStorage.removeItem("kvxPendingFilter");
    setTimeout(()=>applyOnPage(pf.field, pf.code), 900); // apres le 1er rendu de la page
  }

  function navigate(file){ setTimeout(()=>{ window.location.href=file; }, 500); }

  // --- Push-to-talk : touche P -----------------------------------------------
  function typing(el){ return el && (el.tagName==="INPUT"||el.tagName==="TEXTAREA"||
    el.tagName==="SELECT"||el.isContentEditable); }
  document.addEventListener("keydown",(e)=>{
    if(e.repeat || (e.key||"").toLowerCase()!=="p" || typing(e.target)) return;
    e.preventDefault(); startListen();
  });
  document.addEventListener("keyup",(e)=>{
    if((e.key||"").toLowerCase()!=="p") return; stopListen();
  });
  // Alternative tactile/souris : maintenir l'orbe
  ready(()=>{
    const orb=$("kvx-orb");
    orb.addEventListener("mousedown",(e)=>{e.preventDefault();startListen();});
    document.addEventListener("mouseup",()=>{ if(recording) stopListen(); });
    orb.addEventListener("touchstart",(e)=>{e.preventDefault();startListen();},{passive:false});
    orb.addEventListener("touchend",(e)=>{e.preventDefault();stopListen();});
  });
})();

/* ============================================================================
   KiVendTout V2 — Socle commun partagé par toutes les pages.
   Corrige : nav dupliquée/incohérente, JS copié-collé, polling x3 à 1s,
   prompt() natifs. À inclure AVANT le script de page.
   ============================================================================ */
(function (global) {
  "use strict";

  // — Config API (un seul endroit, fini les 6 copies) —
  const host = global.location.hostname || "localhost";
  const apiHost = ["127.0.0.1", "0.0.0.0", "::1", "[::1]"].includes(host) ? "localhost" : host;
  const API_URL = `${global.location.protocol}//${apiHost}:8000`;

  // — Navigation unique (inclut Use cases, identique partout) —
  const NAV = [
    { href: "index.html", label: "Overview" },
    { href: "fraud_dashboard.html", label: "Fraude" },
    { href: "fraud_types_dashboard.html", label: "Typologies" },
    { href: "id_cards_dashboard.html", label: "Identité" },
    { href: "transfer_kpi_dashboard.html", label: "Transferts" },
    { href: "use_cases_dashboard.html", label: "Cas d'usage" },
  ];

  function renderNav(targetId) {
    const el = document.getElementById(targetId || "nav");
    if (!el) return;
    const current = (global.location.pathname.split("/").pop() || "index.html");
    el.className = "nav";
    el.innerHTML = NAV.map((n) =>
      `<a href="${n.href}"${n.href === current ? ' class="active"' : ""}>${n.label}</a>`
    ).join("");
  }

  // — Utils (factorisés, fini les copies divergentes) —
  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function fmtNumber(n) {
    const v = Number(n);
    return Number.isFinite(v) ? v.toLocaleString("fr-FR") : "—";
  }
  function fmtPercent(n, digits = 2) {
    const v = Number(n);
    return Number.isFinite(v) ? `${v.toFixed(digits)} %` : "—";
  }
  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? "—"
      : d.toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  }
  async function getJSON(path) {
    const r = await fetch(`${API_URL}${path}`, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status} sur ${path}`);
    return r.json();
  }

  // — Polling intelligent : une source, intervalle raisonnable, pause si onglet masqué —
  function createPoller(fn, intervalMs = 15000) {
    let timer = null, running = false;
    async function tick() {
      if (running) return;
      running = true;
      try { await fn(); } catch (e) { console.error(e); } finally { running = false; }
    }
    function start() { stop(); tick(); timer = setInterval(() => { if (!document.hidden) tick(); }, intervalMs); }
    function stop() { if (timer) clearInterval(timer); timer = null; }
    document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });
    global.addEventListener("pagehide", stop);
    return { start, stop, tick };
  }

  // — Modale stylée (remplace prompt/confirm) -> Promise —
  function modal({ title, message = "", fields = [], confirmLabel = "Valider", cancelLabel = "Annuler", danger = false }) {
    return new Promise((resolve) => {
      const back = document.createElement("div");
      back.className = "kv-modal-backdrop";
      const fieldsHtml = fields.map((f) =>
        `<label class="field"><span>${escapeHtml(f.label)}</span>` +
        (f.type === "textarea"
          ? `<textarea data-k="${escapeHtml(f.key)}" rows="3" placeholder="${escapeHtml(f.placeholder || "")}">${escapeHtml(f.value || "")}</textarea>`
          : `<input data-k="${escapeHtml(f.key)}" type="${escapeHtml(f.type || "text")}" placeholder="${escapeHtml(f.placeholder || "")}" value="${escapeHtml(f.value || "")}">`) +
        `</label>`).join("");
      back.innerHTML =
        `<div class="kv-modal" role="dialog" aria-modal="true">` +
        `<h3>${escapeHtml(title)}</h3>` +
        (message ? `<p>${escapeHtml(message)}</p>` : "") +
        fieldsHtml +
        `<div class="kv-modal__actions">` +
        `<button class="btn btn--ghost" data-act="cancel">${escapeHtml(cancelLabel)}</button>` +
        `<button class="btn ${danger ? "btn--danger" : "btn--primary"}" data-act="ok">${escapeHtml(confirmLabel)}</button>` +
        `</div></div>`;
      document.body.appendChild(back);
      requestAnimationFrame(() => back.classList.add("show"));
      const close = (val) => { back.classList.remove("show"); setTimeout(() => back.remove(), 200); resolve(val); };
      back.addEventListener("click", (e) => {
        if (e.target === back || e.target.dataset.act === "cancel") return close(null);
        if (e.target.dataset.act === "ok") {
          const out = {};
          back.querySelectorAll("[data-k]").forEach((i) => { out[i.dataset.k] = i.value.trim(); });
          close(fields.length ? out : true);
        }
      });
      const first = back.querySelector("[data-k]"); if (first) first.focus();
      document.addEventListener("keydown", function esc(ev) {
        if (ev.key === "Escape") { document.removeEventListener("keydown", esc); close(null); }
      });
    });
  }
  function confirmModal(title, message, danger = true) {
    return modal({ title, message, confirmLabel: "Confirmer", danger }).then(Boolean);
  }

  global.KV = { API_URL, NAV, renderNav, escapeHtml, fmtNumber, fmtPercent, fmtDate, getJSON, createPoller, modal, confirmModal };
})(window);

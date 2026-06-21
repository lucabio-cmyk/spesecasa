/* ============================================================
   Spese Familiari — SPA (vanilla JS, zero dipendenze)
   ============================================================ */
"use strict";

/* ---------- Stato globale ---------- */
const State = {
  token: localStorage.getItem("token") || null,
  user: null,
  members: [],
  membersById: {},
  units: [],
  view: "dashboard",
  year: localStorage.getItem("year") || "",
  theme: localStorage.getItem("theme") || "light",
};

const FISCAL_LABELS = {
  detraibile: "Detraibile",
  deducibile: "Deducibile",
  non_rilevante: "Non rilevante",
  da_verificare: "Da verificare",
};
const STATUS_LABELS = {
  pending: "In coda", processing: "In elaborazione", complete: "Completo",
  needs_review: "Da rivedere", failed: "Errore",
};
const SCOPE_LABELS = { personale: "Personale", familiare: "Familiare" };
const DOCTYPE_LABELS = {
  scontrino: "Scontrino", fattura: "Fattura", ricevuta: "Ricevuta",
  ricevuta_sanitaria: "Ricevuta sanitaria", bolletta: "Bolletta",
  verbale_assemblea: "Verbale assemblea", f24: "F24", bonifico: "Bonifico",
  contratto: "Contratto", polizza: "Polizza", altro: "Altro",
};
const DOCTYPE_ICONS = {
  scontrino: "🧾", fattura: "📄", ricevuta: "🧾", ricevuta_sanitaria: "💊", bolletta: "💡",
  verbale_assemblea: "🏢", f24: "🏛️", bonifico: "🏦", contratto: "📑", polizza: "🛡️", altro: "📎",
};
const UTILITY_LABELS = {
  energia_elettrica: "Energia elettrica", gas: "Gas", acqua: "Acqua",
  rifiuti: "Rifiuti (TARI)", internet_telefono: "Internet / Telefono",
  riscaldamento: "Riscaldamento", condominio: "Condominio",
  assicurazione_casa: "Assicurazione casa", manutenzione: "Manutenzione", altro: "Altro",
};
const UTILITY_ICONS = {
  energia_elettrica: "💡", gas: "🔥", acqua: "💧", rifiuti: "🗑️",
  internet_telefono: "🌐", riscaldamento: "🌡️", condominio: "🏢",
  assicurazione_casa: "🛡️", manutenzione: "🔧", altro: "🏠",
};
const BILL_STATUS_LABELS = {
  da_pagare: "Da pagare", pagata: "Pagata", scaduta: "Scaduta", rateizzata: "Rateizzata",
};
const CATEGORIES = [
  "frutta e verdura","carne e pesce","latticini e uova","pane, forno e colazione",
  "pasta, riso e dispensa","bevande","surgelati","infanzia","igiene personale",
  "pulizia casa","animali","parafarmacia da supermercato","casa e cucina","altre spese supermercato",
];
const PALETTE = ["#0d9488","#3b82f6","#f59e0b","#8b5cf6","#ec4899","#22c55e","#ef4444","#06b6d4","#eab308","#6366f1","#14b8a6","#f97316","#a855f7","#64748b"];

/* ---------- Helpers ---------- */
const $ = (sel, root = document) => root.querySelector(sel);
const app = () => $("#app");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
const eur = (n) => (Number(n) || 0).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
const fmtDate = (d) => d ? new Date(d).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" }) : "—";
const initials = (name) => (name || "?").trim().split(/\s+/).map(w => w[0]).slice(0, 2).join("").toUpperCase();
const memberName = (id) => id ? (State.membersById[id]?.full_name || "—") : "—";
const unitName = (id) => id ? (State.units.find(u => u.id === id)?.name || "—") : "—";
const debounce = (fn, ms = 300) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

/* ---------- API ---------- */
async function api(path, { method = "GET", body, raw = false, isForm = false } = {}) {
  const headers = {};
  if (State.token) headers["Authorization"] = `Bearer ${State.token}`;
  if (body && !isForm) headers["Content-Type"] = "application/json";
  const res = await fetch(path, {
    method, headers,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) { logout(true); throw new Error("Sessione scaduta. Accedi di nuovo."); }
  if (!res.ok) {
    let msg = `Errore ${res.status}`;
    try { const j = await res.json(); msg = j.detail ? (typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail)) : msg; } catch {}
    throw new Error(msg);
  }
  if (raw) return res;
  if (res.status === 204) return null;
  return res.json();
}

/* ---------- Toast ---------- */
function toast(title, { desc = "", type = "ok", timeout = 3800 } = {}) {
  const stack = $("#toast-stack");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  const icon = { ok: "✅", err: "⚠️", warn: "⏳", info: "ℹ️" }[type] || "ℹ️";
  el.innerHTML = `<span>${icon}</span><div><b>${esc(title)}</b>${desc ? `<p>${esc(desc)}</p>` : ""}</div>`;
  stack.appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transform = "translateX(20px)"; el.style.transition = ".3s"; setTimeout(() => el.remove(), 300); }, timeout);
}

/* ---------- Modal / Drawer ---------- */
function openModal(html, { drawer = false } = {}) {
  if (_modalBlobUrl) { URL.revokeObjectURL(_modalBlobUrl); _modalBlobUrl = null; }
  const root = $("#modal-root");
  root.innerHTML = `<div class="overlay">${drawer ? `<div class="drawer">${html}</div>` : `<div class="modal">${html}</div>`}</div>`;
  const overlay = $(".overlay", root);
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) closeModal(); });
  const onKey = (e) => { if (e.key === "Escape") { closeModal(); document.removeEventListener("keydown", onKey); } };
  document.addEventListener("keydown", onKey);
  return root;
}
function closeModal() {
  if (_modalBlobUrl) { URL.revokeObjectURL(_modalBlobUrl); _modalBlobUrl = null; }
  $("#modal-root").innerHTML = "";
}

// URL oggetto del file attualmente in anteprima: va revocato alla chiusura
// per non perdere memoria (i blob restano allocati finché non si revoca).
let _modalBlobUrl = null;

function confirmDialog(title, message, { danger = true, okText = "Conferma" } = {}) {
  return new Promise((resolve) => {
    openModal(`
      <div class="modal-head"><h3>${esc(title)}</h3></div>
      <p style="color:var(--text-soft);margin-bottom:22px">${esc(message)}</p>
      <div class="row between">
        <button class="btn btn-ghost" data-act="cancel">Annulla</button>
        <button class="btn ${danger ? "btn-danger" : "btn-primary"}" data-act="ok">${esc(okText)}</button>
      </div>`);
    $("#modal-root").addEventListener("click", (e) => {
      const act = e.target.dataset.act;
      if (act === "ok") { closeModal(); resolve(true); }
      else if (act === "cancel") { closeModal(); resolve(false); }
    });
  });
}

/* ---------- Auth views ---------- */
function renderAuth(mode = "login") {
  document.documentElement.dataset.theme = State.theme;
  const tabs = mode === "recover" ? "" : `
    <div class="auth-tabs">
      <button class="${mode === "login" ? "active" : ""}" data-mode="login">Accedi</button>
      <button class="${mode === "register" ? "active" : ""}" data-mode="register">Nuovo nucleo</button>
      <button class="${mode === "join" ? "active" : ""}" data-mode="join">Unisciti</button>
    </div>`;

  let form = "";
  if (mode === "login") {
    form = `
      <div class="field"><label>Email</label><input class="input" type="email" name="email" autocomplete="email" required></div>
      <div class="field"><label>Password</label><input class="input" type="password" name="password" autocomplete="current-password" required></div>
      <button class="btn btn-primary btn-block" type="submit">Accedi</button>
      <p class="hint" style="text-align:center;margin-top:14px"><a href="#" data-mode-link="recover">Password dimenticata?</a></p>`;
  } else if (mode === "recover") {
    form = `
      <p class="hint" style="margin-bottom:14px">Per recuperare la password inserisci l'email e il <b>codice fiscale</b> associato al tuo account, poi scegli una nuova password. Se non hai un codice fiscale impostato, chiedi all'amministratore del nucleo di reimpostartela.</p>
      <div class="field"><label>Email</label><input class="input" type="email" name="email" autocomplete="email" required></div>
      <div class="field"><label>Codice fiscale</label><input class="input" name="codice_fiscale" maxlength="16" style="text-transform:uppercase" required></div>
      <div class="field"><label>Nuova password <span class="hint">(min 8 caratteri)</span></label><input class="input" type="password" name="new_password" minlength="8" autocomplete="new-password" required></div>
      <button class="btn btn-primary btn-block" type="submit">Reimposta password</button>
      <p class="hint" style="text-align:center;margin-top:14px"><a href="#" data-mode-link="login">← Torna all'accesso</a></p>`;
  } else if (mode === "register") {
    form = `
      <div class="field"><label>Nome del nucleo familiare</label><input class="input" name="household_name" placeholder="es. Famiglia Rossi" required></div>
      <div class="field"><label>Il tuo nome</label><input class="input" name="full_name" required></div>
      <div class="field"><label>Email</label><input class="input" type="email" name="email" autocomplete="email" required></div>
      <div class="field"><label>Codice fiscale <span class="hint">(opzionale)</span></label><input class="input" name="codice_fiscale" maxlength="16" style="text-transform:uppercase"></div>
      <div class="field"><label>Password <span class="hint">(min 8 caratteri)</span></label><input class="input" type="password" name="password" minlength="8" autocomplete="new-password" required></div>
      <button class="btn btn-primary btn-block" type="submit">Crea nucleo e account</button>`;
  } else {
    form = `
      <div class="field"><label>ID del nucleo</label><input class="input" name="household_id" placeholder="UUID fornito dall'amministratore" required></div>
      <div class="field"><label>Il tuo nome</label><input class="input" name="full_name" required></div>
      <div class="field"><label>Email</label><input class="input" type="email" name="email" required></div>
      <div class="field"><label>Codice fiscale <span class="hint">(opzionale)</span></label><input class="input" name="codice_fiscale" maxlength="16" style="text-transform:uppercase"></div>
      <div class="field"><label>Password</label><input class="input" type="password" name="password" minlength="8" required></div>
      <button class="btn btn-primary btn-block" type="submit">Unisciti al nucleo</button>`;
  }

  app().innerHTML = `
    <div class="auth-wrap">
      <div class="auth-card">
        <div class="brand-mark"><span class="logo">🧾</span><h1>Spese Familiari</h1></div>
        <p class="auth-sub">Archivio documenti e spese del nucleo, in ottica fiscale italiana (730 / Redditi PF).</p>
        ${tabs}
        <form id="auth-form">${form}</form>
      </div>
    </div>`;

  $("#app").querySelectorAll(".auth-tabs button").forEach(b =>
    b.addEventListener("click", () => renderAuth(b.dataset.mode)));
  $("#app").querySelectorAll("[data-mode-link]").forEach(a =>
    a.addEventListener("click", (e) => { e.preventDefault(); renderAuth(a.dataset.modeLink); }));

  const ENDPOINTS = {
    login: "/auth/login",
    register: "/auth/register",
    join: "/auth/join",
    recover: "/auth/password-reset",
  };

  $("#auth-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector("button[type=submit]");
    btn.disabled = true; const orig = btn.textContent; btn.textContent = "Attendere…";
    const data = Object.fromEntries(new FormData(e.target).entries());
    if (data.codice_fiscale) data.codice_fiscale = data.codice_fiscale.trim().toUpperCase();
    try {
      const res = await api(ENDPOINTS[mode], { method: "POST", body: data });
      State.token = res.access_token;
      localStorage.setItem("token", State.token);
      toast(mode === "recover" ? "Password reimpostata" : "Accesso effettuato", { type: "ok" });
      await boot();
    } catch (err) {
      toast("Operazione non riuscita", { desc: err.message, type: "err" });
      btn.disabled = false; btn.textContent = orig;
    }
  });
}

/* ---------- App shell ---------- */
const NAV = [
  { id: "dashboard", icon: "📊", label: "Dashboard" },
  { id: "upload", icon: "⬆️", label: "Carica documento" },
  { id: "documents", icon: "🗂️", label: "Archivio" },
  { id: "expenses", icon: "💶", label: "Spese" },
  { id: "bills", icon: "🏠", label: "Casa & Bollette" },
  { id: "chat", icon: "💬", label: "Assistente" },
  { id: "settings", icon: "⚙️", label: "Impostazioni" },
];

function renderShell() {
  document.documentElement.dataset.theme = State.theme;
  const reviewCount = State._reviewCount || 0;
  app().innerHTML = `
    <div class="shell">
      <aside class="sidebar" id="sidebar">
        <div class="brand"><span class="logo">🧾</span><div><b>Spese Familiari</b><small>${esc(State.user?.household_name || "Archivio fiscale")}</small></div></div>
        ${NAV.map(n => `
          <button class="nav-item ${State.view === n.id ? "active" : ""}" data-nav="${n.id}">
            <span class="ico">${n.icon}</span><span>${n.label}</span>
            ${n.id === "documents" && reviewCount ? `<span class="badge-dot">${reviewCount}</span>` : ""}
          </button>`).join("")}
        <div class="spacer"></div>
        <button class="nav-item" id="theme-toggle"><span class="ico">${State.theme === "dark" ? "☀️" : "🌙"}</span><span>Tema ${State.theme === "dark" ? "chiaro" : "scuro"}</span></button>
        <div class="user-chip">
          <div class="avatar">${initials(State.user?.full_name)}</div>
          <div class="meta"><b>${esc(State.user?.full_name || "")}</b><small>${esc(State.user?.email || "")}</small></div>
          <button class="btn-icon" id="logout" title="Esci">⏻</button>
        </div>
      </aside>
      <div class="main">
        <header class="topbar">
          <button class="btn-icon menu-toggle" id="menu-toggle">☰</button>
          <div><h2 id="page-title"></h2><div class="sub" id="page-sub"></div></div>
          <div class="grow"></div>
          <div id="topbar-actions" class="row"></div>
        </header>
        <main class="content" id="content"></main>
      </div>
    </div>`;

  app().querySelectorAll("[data-nav]").forEach(b => b.addEventListener("click", () => navigate(b.dataset.nav)));
  $("#logout").addEventListener("click", () => logout());
  $("#theme-toggle").addEventListener("click", toggleTheme);
  $("#menu-toggle").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
}

function toggleTheme() {
  State.theme = State.theme === "dark" ? "light" : "dark";
  localStorage.setItem("theme", State.theme);
  document.documentElement.dataset.theme = State.theme;
  renderShell(); navigate(State.view);
}

function navigate(view) {
  State.view = view;
  $("#sidebar")?.classList.remove("open");
  app().querySelectorAll("[data-nav]").forEach(b => b.classList.toggle("active", b.dataset.nav === view));
  const titles = {
    dashboard: ["Dashboard", "Panoramica delle spese e dei documenti del nucleo"],
    upload: ["Carica documento", "Scontrini, fatture, ricevute: l'assistente AI li legge e li archivia"],
    documents: ["Archivio documenti", "Tutti i documenti caricati, con stato ed estrazione"],
    expenses: ["Spese", "Movimenti e righe di dettaglio, correggibili al volo"],
    bills: ["Casa & Bollette", "Riconoscimento bollette, valutazione costi e scadenze di pagamento"],
    chat: ["Assistente", "Registra spese descrivendole e interroga lo storico in linguaggio naturale"],
    settings: ["Impostazioni", "Nucleo, membri, immobili e addestramento dell'assistente"],
  };
  $("#page-title").textContent = titles[view][0];
  $("#page-sub").textContent = titles[view][1];
  $("#topbar-actions").innerHTML = "";
  const views = { dashboard: viewDashboard, upload: viewUpload, documents: viewDocuments, expenses: viewExpenses, bills: viewBills, chat: viewChat, settings: viewSettings };
  views[view]();
}

/* ---------- Year selector (shared topbar control) ---------- */
async function yearSelector(onChange) {
  const years = await api("/stats/yearly").catch(() => []);
  const opts = years.filter(y => y.year).map(y => y.year).sort((a, b) => b - a);
  const cur = new Date().getFullYear();
  if (!opts.includes(cur)) opts.unshift(cur);
  const sel = document.createElement("select");
  sel.className = "select";
  sel.style.width = "auto";
  sel.innerHTML = `<option value="">Tutti gli anni</option>` + opts.map(y => `<option value="${y}" ${String(y) === String(State.year) ? "selected" : ""}>${y}</option>`).join("");
  sel.addEventListener("change", () => { State.year = sel.value; localStorage.setItem("year", State.year); onChange(); });
  return sel;
}

/* ---------- Drill-down (dashboard interattiva) ----------
   I grafici e le KPI possono portare a una vista filtrata: ogni elemento
   cliccabile porta con sé una "drill spec" (JSON) che descrive dove andare e
   quali filtri applicare. bindDrills() la collega dopo il render. */
function drillAttr(spec) { return spec ? ` data-drill='${esc(JSON.stringify(spec))}' role="button" tabindex="0"` : ""; }

function applyDrill(spec) {
  if (!spec) return;
  if ("year" in spec) {
    State.year = spec.year ? String(spec.year) : "";
    localStorage.setItem("year", State.year);
  }
  if (spec.expenses) { expFilters = { ...defaultExpFilters(), ...spec.expenses }; }
  if (spec.documents) { docFilters = { ...defaultDocFilters(), ...spec.documents }; }
  if (spec.bills) { billFilters = { ...defaultBillFilters(), ...spec.bills }; }
  navigate(spec.view || State.view);
}

function bindDrills(root) {
  root.querySelectorAll("[data-drill]").forEach(el => {
    el.classList.add("clickable");
    const fire = () => { try { applyDrill(JSON.parse(el.dataset.drill)); } catch {} };
    el.addEventListener("click", fire);
    el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fire(); } });
  });
}

/* ---------- Charts ----------
   I `rows` possono includere una proprietà `drill` (drill spec): la barra o la
   voce di legenda diventa cliccabile e porta alla vista filtrata. */
function barChart(rows, { labelKey, valueKey, max }) {
  if (!rows.length) return `<div class="empty"><div class="big">📭</div><p>Nessun dato per il periodo selezionato.</p></div>`;
  const m = max || Math.max(...rows.map(r => r[valueKey]), 1);
  return rows.map((r, i) => `
    <div class="bar-row${r.drill ? " bar-clickable" : ""}"${drillAttr(r.drill)}${r.drill ? ` title="Apri: ${esc(r[labelKey])}"` : ` title="${esc(r[labelKey])}"`}>
      <span class="lbl">${esc(r[labelKey])}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2, (r[valueKey] / m) * 100)}%;background:${PALETTE[i % PALETTE.length]}"></div></div>
      <span class="amt">${eur(r[valueKey])}</span>
    </div>`).join("");
}

function donut(rows, { labelKey, valueKey }) {
  const total = rows.reduce((s, r) => s + r[valueKey], 0);
  if (!total) return `<div class="empty"><div class="big">📭</div><p>Nessun dato.</p></div>`;
  const R = 70, C = 2 * Math.PI * R; let off = 0;
  const segs = rows.map((r, i) => {
    const frac = r[valueKey] / total;
    const dash = `${frac * C} ${C - frac * C}`;
    const seg = `<circle class="${r.drill ? "seg-clickable" : ""}" r="${R}" cx="90" cy="90" fill="none" stroke="${PALETTE[i % PALETTE.length]}" stroke-width="24" stroke-dasharray="${dash}" stroke-dashoffset="${-off * C}" transform="rotate(-90 90 90)"${drillAttr(r.drill)}></circle>`;
    off += frac; return seg;
  }).join("");
  const legend = rows.map((r, i) => `<span class="${r.drill ? "leg-clickable" : ""}"${drillAttr(r.drill)}><i class="dot" style="background:${PALETTE[i % PALETTE.length]}"></i>${esc(r[labelKey])} · <b>${eur(r[valueKey])}</b></span>`).join("");
  return `<div class="donut-wrap">
    <svg viewBox="0 0 180 180" width="180" height="180" style="flex-shrink:0">${segs}
      <text x="90" y="84" text-anchor="middle" font-size="13" fill="var(--text-faint)">Totale</text>
      <text x="90" y="104" text-anchor="middle" font-size="17" font-weight="800" fill="var(--text)">${eur(total)}</text>
    </svg>
    <div class="legend" style="flex-direction:column;gap:8px">${legend}</div></div>`;
}

/* ---------- KPI / card helpers (factoring estetico) ---------- */
function kpiCard(k) {
  return `<div class="card kpi${k.drill ? " kpi-clickable" : ""}"${drillAttr(k.drill)}${k.drill ? ` title="Apri dettaglio"` : ""}>
      <div class="row between"><span class="label">${esc(k.label)}</span><span class="ico-box" style="background:${k.bg};color:${k.fg}">${k.icon}</span></div>
      <span class="value">${k.value}</span><span class="delta">${esc(k.delta)}</span>
      ${k.drill ? `<span class="kpi-go" aria-hidden="true">↗</span>` : ""}
    </div>`;
}
function kpiGrid(kpis) { return `<div class="grid cols-4">${kpis.map(kpiCard).join("")}</div>`; }

// Card "grafico" con intestazione coerente (titolo + azione opzionale).
function chartCard(title, body, { action = "", sub = "", style = "" } = {}) {
  return `<div class="card card-pad"${style ? ` style="${style}"` : ""}>
      <div class="row between" style="margin-bottom:${sub ? "4" : "16"}px"><h3>${title}</h3>${action}</div>
      ${sub ? `<p class="hint" style="margin-bottom:16px">${sub}</p>` : ""}
      ${body}
    </div>`;
}

/* ---------- View: Dashboard ---------- */
async function viewDashboard() {
  const c = $("#content");
  c.innerHTML = skeletonGrid();
  $("#topbar-actions").appendChild(await yearSelector(viewDashboard));
  const yq = State.year ? `?year=${State.year}` : "";
  try {
    const [ov, byCat, byMember, byScope, fiscal, yearly] = await Promise.all([
      api(`/stats/overview${yq}`), api(`/stats/by-category${yq}`), api(`/stats/by-member${yq}`),
      api(`/stats/by-scope${yq}`), api(`/stats/fiscal-summary${yq}`), api(`/stats/yearly`),
    ]);
    State._reviewCount = ov.to_review;
    updateReviewBadge(ov.to_review);

    // Filtri di base condivisi dai drill-down: l'anno selezionato nella
    // dashboard si propaga alle viste filtrate.
    const yBase = State.year ? { fiscal_year: State.year } : {};
    const kpis = [
      { label: "Totale spese", value: eur(ov.total), icon: "💶", bg: "var(--teal-100)", fg: "var(--teal-800)", delta: `${ov.lines} moviment${ov.lines === 1 ? "o" : "i"} · ${ov.bills} bollett${ov.bills === 1 ? "a" : "e"}`, drill: { view: "expenses", expenses: { ...yBase } } },
      { label: "Potenz. agevolabile", value: eur(ov.deductible_total), icon: "🏷️", bg: "var(--green-100)", fg: "#15803d", delta: "detraibile + deducibile", drill: { view: "expenses", expenses: { ...yBase, fiscal_classification: "detraibile" } } },
      { label: "Documenti", value: ov.documents, icon: "🗂️", bg: "var(--blue-100)", fg: "#1d4ed8", delta: "in archivio", drill: { view: "documents", documents: { ...yBase } } },
      { label: "Da rivedere", value: ov.to_review, icon: "🔎", bg: "var(--amber-100)", fg: "#b45309", delta: "richiedono verifica", drill: ov.to_review ? { view: "documents", documents: { ...yBase, status: "needs_review" } } : null },
    ];

    // Righe dei grafici, ciascuna con la propria drill spec verso la vista filtrata.
    // Le categorie aggregate (bollette/condominio) provengono dal backend e
    // portano alla vista bollette; le altre categorie valide filtrano le spese.
    const catRows = byCat.slice(0, 8).map(r => {
      let drill = null;
      if (r.category === "Bollette / utenze") drill = { view: "bills" };
      else if (r.category === "Spese condominiali") drill = { view: "bills", bills: { utility_type: "condominio" } };
      else if (r.category && r.category !== "n/d") drill = { view: "expenses", expenses: { ...yBase, category: r.category } };
      return { label: r.category, total: r.total, drill };
    });
    const fiscalRows = fiscal.filter(r => r.total > 0).map(r => ({ label: FISCAL_LABELS[r.classification] || r.classification, total: r.total, drill: { view: "expenses", expenses: { ...yBase, fiscal_classification: r.classification } } }));
    const memberRows = byMember.map(r => {
      const m = State.members.find(x => x.full_name === r.member);
      return { label: r.member, total: r.total, drill: m ? { view: "expenses", expenses: { ...yBase, payer_user_id: m.id } } : null };
    });
    const scopeRows = byScope.map(r => ({ label: SCOPE_LABELS[r.scope] || r.scope, total: r.total, drill: { view: "expenses", expenses: { ...yBase, scope: r.scope } } })).filter(r => r.total > 0);
    const yearRows = yearly.filter(y => y.year).map(r => ({ label: String(r.year), total: r.total, drill: { view: "dashboard", year: r.year } }));

    c.innerHTML = `
      ${kpiGrid(kpis)}

      ${ov.to_review ? `<div class="card card-pad alert-bar" style="margin-top:16px;border-left:4px solid var(--amber-500)">
        <span style="font-size:22px">🔎</span>
        <div style="flex:1"><b>${ov.to_review} document${ov.to_review === 1 ? "o" : "i"} da rivedere</b><div class="sub" style="color:var(--text-soft);font-size:13px">Verifica attribuzione e classificazione fiscale prima dell'uso col commercialista.</div></div>
        <button class="btn btn-primary btn-sm" data-go="documents">Apri archivio</button>
      </div>` : ""}

      <div class="grid cols-2" style="margin-top:20px">
        ${chartCard("Spesa per categoria", barChart(catRows, { labelKey: "label", valueKey: "total" }))}
        ${chartCard("Classificazione fiscale", donut(fiscalRows, { labelKey: "label", valueKey: "total" }))}
      </div>

      <div class="grid cols-2" style="margin-top:16px">
        ${chartCard("Spesa per membro (pagante)", barChart(memberRows, { labelKey: "label", valueKey: "total" }))}
        ${chartCard("Personale vs familiare", donut(scopeRows, { labelKey: "label", valueKey: "total" }))}
      </div>

      ${chartCard("Andamento per anno", barChart(yearRows, { labelKey: "label", valueKey: "total" }), { action: `<span class="hint">Clicca un anno per filtrare</span>`, style: "margin-top:16px" })}`;

    c.querySelectorAll("[data-go]").forEach(b => b.addEventListener("click", () => navigate(b.dataset.go)));
    bindDrills(c);
  } catch (err) {
    c.innerHTML = errorBox(err.message);
  }
}

/* ---------- View: Upload ---------- */
function viewUpload() {
  const c = $("#content");
  c.innerHTML = `
    <div class="grid cols-2" style="align-items:start">
      <div>
        <div class="dropzone" id="dropzone">
          <div class="big">📤</div>
          <h3>Trascina qui i documenti</h3>
          <p>oppure <u>clicca per selezionare</u> · scontrini, fatture, ricevute</p>
          <p class="hint">Immagini (JPG, PNG, HEIC), PDF o fogli Excel (XLS, XLSX) · più file insieme</p>
          <input type="file" id="file-input" multiple accept="image/*,application/pdf,.xls,.xlsx,.xlsm,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden>
        </div>
        <div id="upload-list"></div>
      </div>
      <div class="card card-pad">
        <h3 style="margin-bottom:10px">Come funziona</h3>
        <ol style="color:var(--text-soft);font-size:14px;padding-left:18px;line-height:1.8;margin:0">
          <li>Carichi il documento (foto, PDF o foglio Excel).</li>
          <li>L'assistente AI lo <b>legge</b>, estrae data, importo ed emittente.</li>
          <li>Classifica fiscalmente e <b>attribuisce</b> pagante e beneficiario.</li>
          <li>Per gli scontrini analizza le righe e le <b>categorizza</b>.</li>
          <li>Trovi tutto in <b>Archivio</b> e <b>Spese</b>, pronto da verificare.</li>
        </ol>
        <div class="divider"></div>
        <p class="hint">💡 L'elaborazione avviene in background: puoi continuare a usare l'app. Lo stato si aggiorna da solo.</p>
      </div>
    </div>`;

  const dz = $("#dropzone"), input = $("#file-input");
  dz.addEventListener("click", () => input.click());
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drag"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
  dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("drag"); handleFiles(e.dataTransfer.files); });
  input.addEventListener("change", () => handleFiles(input.files));
}

async function handleFiles(files) {
  const list = $("#upload-list");
  for (const file of files) {
    const row = document.createElement("div");
    row.className = "upload-item";
    const isSheet = /\.(xlsx?|xlsm)$/i.test(file.name) || /excel|spreadsheet|ms-excel/i.test(file.type || "");
    row.innerHTML = `<span class="fi">${isSheet ? "📊" : file.type.includes("pdf") ? "📄" : "🖼️"}</span>
      <div class="meta"><b>${esc(file.name)}</b><div class="progress"><i style="width:30%"></i></div></div>
      <span class="status"><span class="spin"></span></span>`;
    list.prepend(row);
    try {
      const fd = new FormData(); fd.append("file", file);
      const res = await api("/documents", { method: "POST", body: fd, isForm: true, raw: true });
      const doc = await res.json();
      row.querySelector(".progress i").style.width = "100%";
      // Verifica anti-duplicazione: il server risponde 200 (+ header) se il
      // file è identico a uno già in archivio.
      const isDuplicate = res.status === 200 || res.headers.get("X-Document-Duplicate") === "1";
      if (isDuplicate) {
        row.querySelector(".progress i").style.background = "var(--amber-500)";
        row.querySelector(".status").innerHTML = `<span class="badge b-da_verificare">Già presente</span>`;
        const m = row.querySelector(".meta");
        m.insertAdjacentHTML("beforeend", `<div class="hint" style="margin-top:5px">📎 Documento già in archivio (${esc(DOCTYPE_LABELS[doc.doc_type] || doc.doc_type)}${doc.issuer ? " · " + esc(doc.issuer) : ""}). Non è stato ricaricato.</div>`);
        toast("Documento già presente", { desc: "Questo file è già nell'archivio: caricamento ignorato.", type: "warn" });
        continue;
      }
      row.querySelector(".status").innerHTML = badge(doc.status, STATUS_LABELS);
      pollDocument(doc.id, row);
    } catch (err) {
      row.querySelector(".progress i").style.background = "var(--rose-500)";
      row.querySelector(".status").innerHTML = `<span class="badge b-failed">Errore</span>`;
      toast("Caricamento non riuscito", { desc: err.message, type: "err" });
    }
  }
}

async function pollDocument(id, row, tries = 0) {
  if (tries > 40) return;
  await new Promise(r => setTimeout(r, 2500));
  try {
    const doc = await api(`/documents/${id}`);
    row.querySelector(".status").innerHTML = badge(doc.status, STATUS_LABELS);
    if (["complete", "needs_review", "failed"].includes(doc.status)) {
      const m = row.querySelector(".meta");
      if (!m.querySelector(".done-line")) {
        const extra = document.createElement("div");
        extra.className = "done-line hint";
        extra.style.marginTop = "5px";
        extra.innerHTML = doc.status === "failed"
          ? `❌ ${esc(doc.reliability_note || "Elaborazione fallita")}`
          : `${DOCTYPE_ICONS[doc.doc_type] || "📎"} ${esc(DOCTYPE_LABELS[doc.doc_type] || doc.doc_type)} · ${doc.total_amount ? eur(doc.total_amount) : "importo n/d"} · ${esc(doc.issuer || "emittente n/d")}`;
        m.appendChild(extra);
      }
      if (doc.status === "complete") toast("Documento elaborato", { desc: doc.issuer || doc.original_filename, type: "ok" });
      if (doc.status === "needs_review") toast("Documento da rivedere", { desc: "Controlla attribuzione e classifica.", type: "warn" });
      return;
    }
    pollDocument(id, row, tries + 1);
  } catch { /* stop polling silently */ }
}

/* ---------- View: Documents ---------- */
const defaultDocFilters = () => ({ fiscal_year: "", doc_type: "", status: "", q: "" });
let docFilters = defaultDocFilters();
async function viewDocuments() {
  const c = $("#content");
  c.innerHTML = `
    <div class="filters">
      <div class="search-box"><span class="s-ico">🔍</span><input class="input" id="doc-q" placeholder="Cerca per emittente, file…" value="${esc(docFilters.q)}"></div>
      <select class="select" id="f-status">${optList({ "": "Tutti gli stati", ...STATUS_LABELS }, docFilters.status)}</select>
      <select class="select" id="f-type">${optList({ "": "Tutti i tipi", ...DOCTYPE_LABELS }, docFilters.doc_type)}</select>
      <input class="input" id="f-year" type="number" placeholder="Anno" style="width:110px" value="${esc(docFilters.fiscal_year)}">
      <button class="btn btn-ghost btn-sm" id="reset-f">Azzera</button>
    </div>
    <div id="doc-list">${skeletonRows()}</div>`;

  const reload = debounce(loadDocuments, 250);
  $("#doc-q").addEventListener("input", (e) => { docFilters.q = e.target.value; reload(); });
  $("#f-status").addEventListener("change", (e) => { docFilters.status = e.target.value; loadDocuments(); });
  $("#f-type").addEventListener("change", (e) => { docFilters.doc_type = e.target.value; loadDocuments(); });
  $("#f-year").addEventListener("input", (e) => { docFilters.fiscal_year = e.target.value; reload(); });
  $("#reset-f").addEventListener("click", () => { docFilters = defaultDocFilters(); viewDocuments(); });
  loadDocuments();
}

async function loadDocuments() {
  const wrap = $("#doc-list"); if (!wrap) return;
  const p = new URLSearchParams();
  if (docFilters.fiscal_year) p.set("fiscal_year", docFilters.fiscal_year);
  if (docFilters.doc_type) p.set("doc_type", docFilters.doc_type);
  if (docFilters.status) p.set("status", docFilters.status);
  try {
    let docs = await api(`/documents?${p.toString()}`);
    if (docFilters.q) {
      const q = docFilters.q.toLowerCase();
      docs = docs.filter(d => `${d.issuer || ""} ${d.original_filename || ""} ${d.document_number || ""}`.toLowerCase().includes(q));
    }
    if (!docs.length) { wrap.innerHTML = emptyBox("🗂️", "Nessun documento", "Carica il primo documento dalla sezione “Carica documento”.", "Carica ora", "upload"); bindEmpty(wrap); return; }
    wrap.innerHTML = `<div class="card table-wrap"><table class="data">
      <thead><tr><th>Documento</th><th>Tipo</th><th>Data</th><th class="num">Importo</th><th>Fiscale</th><th>Pagante</th><th>Stato</th><th></th></tr></thead>
      <tbody>${docs.map(d => `
        <tr data-id="${d.id}" style="cursor:pointer">
          <td><b>${esc(d.issuer || d.original_filename)}</b>${d.document_number ? `<div class="hint">N. ${esc(d.document_number)}</div>` : ""}</td>
          <td>${DOCTYPE_ICONS[d.doc_type] || "📎"} ${esc(DOCTYPE_LABELS[d.doc_type] || d.doc_type)}</td>
          <td>${fmtDate(d.doc_date)}</td>
          <td class="num">${d.total_amount != null ? eur(d.total_amount) : "—"}</td>
          <td>${badge(d.fiscal_classification, FISCAL_LABELS)}</td>
          <td>${esc(memberName(d.payer_user_id))}</td>
          <td>${badge(d.status, STATUS_LABELS)}</td>
          <td class="num"><button class="btn-icon" data-open="${d.id}" title="Dettagli">›</button></td>
        </tr>`).join("")}
      </tbody></table></div>`;
    wrap.querySelectorAll("tr[data-id]").forEach(tr => tr.addEventListener("click", () => openDocument(tr.dataset.id)));
  } catch (err) { wrap.innerHTML = errorBox(err.message); }
}

async function openDocument(id) {
  openModal(`<div class="drawer-body"><div class="skeleton" style="height:300px"></div></div>`, { drawer: true });
  try {
    const [doc, lines] = await Promise.all([api(`/documents/${id}`), api(`/documents/${id}/expenses`)]);
    const isImg = (doc.mime_type || "").startsWith("image/");
    const isSheet = /excel|spreadsheet|ms-excel/i.test(doc.mime_type || "") || /\.(xlsx?|xlsm)$/i.test(doc.original_filename || "");
    // Il file originale è protetto da JWT in header: img/iframe/link nativi non
    // lo inviano. Scarichiamo il file via api() (che allega il token) e usiamo
    // un blob URL come sorgente. Il blob viene revocato in closeModal().
    let fileUrl = "";
    try {
      const res = await api(`/documents/${id}/file`, { raw: true });
      _modalBlobUrl = fileUrl = URL.createObjectURL(await res.blob());
    } catch { /* file non disponibile: i riquadri di anteprima restano vuoti */ }
    const body = $("#modal-root .drawer");
    body.innerHTML = `
      <div class="drawer-head">
        <span style="font-size:22px">${DOCTYPE_ICONS[doc.doc_type] || "📎"}</span>
        <div style="flex:1"><h3>${esc(doc.issuer || doc.original_filename)}</h3><div class="hint">${esc(DOCTYPE_LABELS[doc.doc_type] || doc.doc_type)} · ${fmtDate(doc.doc_date)}</div></div>
        <button class="btn-icon" data-close>✕</button>
      </div>
      <div class="drawer-body">
        <div class="row" style="margin-bottom:16px">${badge(doc.status, STATUS_LABELS)} ${badge(doc.fiscal_classification, FISCAL_LABELS)} ${badge(doc.scope, SCOPE_LABELS)}</div>
        ${doc.summary ? `<div class="card card-pad" style="background:var(--surface-2);margin-bottom:16px"><b>Sintesi</b><p style="margin:6px 0 0;color:var(--text-soft);font-size:14px;white-space:pre-wrap">${esc(doc.summary)}</p></div>` : ""}
        ${doc.reliability_note ? `<p class="hint" style="margin-bottom:14px">⚠️ ${esc(doc.reliability_note)}</p>` : ""}
        <dl class="kv" style="margin-bottom:18px">
          <dt>Emittente</dt><dd>${esc(doc.issuer || "—")}</dd>
          <dt>Importo totale</dt><dd><b>${doc.total_amount != null ? eur(doc.total_amount) : "—"}</b></dd>
          <dt>Data documento</dt><dd>${fmtDate(doc.doc_date)}</dd>
          <dt>Anno fiscale</dt><dd>${doc.fiscal_year || "—"}</dd>
          <dt>Pagamento</dt><dd>${esc(doc.payment_method || "—")}</dd>
          <dt>N. documento</dt><dd>${esc(doc.document_number || "—")}</dd>
          <dt>Pagante</dt><dd>${esc(memberName(doc.payer_user_id))}</dd>
          <dt>Beneficiario</dt><dd>${esc(memberName(doc.beneficiary_user_id))}</dd>
          ${doc.retention_note ? `<dt>Conservazione</dt><dd>${esc(doc.retention_note)}</dd>` : ""}
        </dl>
        ${lines.length ? `<h4 style="margin-bottom:8px">Righe (${lines.length})</h4>
          <div class="card table-wrap" style="margin-bottom:18px"><table class="data"><thead><tr><th>Descrizione</th><th>Categoria</th><th class="num">Importo</th></tr></thead>
          <tbody>${lines.map(l => `<tr><td>${esc(l.description_normalized || l.description_original || "—")}</td><td>${esc(l.merch_category || "—")}</td><td class="num">${eur(l.line_amount)}</td></tr>`).join("")}</tbody></table></div>` : ""}
        <h4 style="margin-bottom:8px">File originale</h4>
        ${isImg
          ? `<img class="preview-img" src="${fileUrl}" alt="anteprima">`
          : isSheet
            ? `<div class="card card-pad empty" style="background:var(--surface-2)"><div class="big">📊</div><p>Foglio di calcolo Excel${doc.original_filename ? ` · ${esc(doc.original_filename)}` : ""}.<br>Usa “Apri file” qui sotto per scaricarlo.</p></div>`
            : `<iframe class="preview-frame" src="${fileUrl}"></iframe>`}
        <div class="row" style="margin-top:18px">
          <a class="btn btn-ghost" href="${fileUrl}" target="_blank" rel="noopener">⬇️ Apri file</a>
          <button class="btn btn-ghost" data-reprocess="${id}">🔄 Rielabora</button>
          <div class="grow" style="flex:1"></div>
          <button class="btn btn-danger" data-delete="${id}">🗑️ Elimina</button>
        </div>
      </div>`;
    body.querySelector("[data-close]").addEventListener("click", closeModal);
    body.querySelector("[data-reprocess]").addEventListener("click", async () => {
      try { await api(`/documents/${id}/reprocess`, { method: "POST" }); toast("Rielaborazione avviata", { type: "warn" }); closeModal(); loadDocuments(); }
      catch (e) { toast("Errore", { desc: e.message, type: "err" }); }
    });
    body.querySelector("[data-delete]").addEventListener("click", async () => {
      if (!(await confirmDialog("Eliminare il documento?", "Verranno rimossi anche le righe collegate e il file originale. L'operazione non è reversibile."))) return;
      try { await api(`/documents/${id}`, { method: "DELETE" }); toast("Documento eliminato", { type: "ok" }); closeModal(); loadDocuments(); }
      catch (e) { toast("Errore", { desc: e.message, type: "err" }); }
    });
  } catch (err) { toast("Errore", { desc: err.message, type: "err" }); closeModal(); }
}

/* ---------- View: Expenses ---------- */
const defaultExpFilters = () => ({ fiscal_year: "", category: "", scope: "", fiscal_classification: "", payer_user_id: "", q: "" });
let expFilters = defaultExpFilters();
async function viewExpenses() {
  const c = $("#content");
  const memberOpts = Object.fromEntries(State.members.map(m => [m.id, m.full_name]));
  c.innerHTML = `
    <div class="filters">
      <div class="search-box"><span class="s-ico">🔍</span><input class="input" id="exp-q" placeholder="Cerca descrizione, negozio…" value="${esc(expFilters.q)}"></div>
      <select class="select" id="ef-cat">${optList({ "": "Tutte le categorie", ...Object.fromEntries(CATEGORIES.map(c => [c, c])) }, expFilters.category)}</select>
      <select class="select" id="ef-fiscal">${optList({ "": "Tutte le classifiche", ...FISCAL_LABELS }, expFilters.fiscal_classification)}</select>
      <select class="select" id="ef-scope">${optList({ "": "Tutti gli ambiti", ...SCOPE_LABELS }, expFilters.scope)}</select>
      <select class="select" id="ef-payer">${optList({ "": "Tutti i paganti", ...memberOpts }, expFilters.payer_user_id)}</select>
      <input class="input" id="ef-year" type="number" placeholder="Anno" style="width:110px" value="${esc(expFilters.fiscal_year)}">
      <button class="btn btn-ghost btn-sm" id="exp-reset">Azzera</button>
    </div>
    <div id="exp-list">${skeletonRows()}</div>`;
  const reload = debounce(loadExpenses, 250);
  $("#exp-q").addEventListener("input", (e) => { expFilters.q = e.target.value; reload(); });
  $("#ef-cat").addEventListener("change", (e) => { expFilters.category = e.target.value; loadExpenses(); });
  $("#ef-fiscal").addEventListener("change", (e) => { expFilters.fiscal_classification = e.target.value; loadExpenses(); });
  $("#ef-scope").addEventListener("change", (e) => { expFilters.scope = e.target.value; loadExpenses(); });
  $("#ef-payer").addEventListener("change", (e) => { expFilters.payer_user_id = e.target.value; loadExpenses(); });
  $("#ef-year").addEventListener("input", (e) => { expFilters.fiscal_year = e.target.value; reload(); });
  $("#exp-reset").addEventListener("click", () => { expFilters = defaultExpFilters(); viewExpenses(); });
  loadExpenses();
}

async function loadExpenses() {
  const wrap = $("#exp-list"); if (!wrap) return;
  const p = new URLSearchParams();
  if (expFilters.fiscal_year) p.set("fiscal_year", expFilters.fiscal_year);
  if (expFilters.category) p.set("category", expFilters.category);
  if (expFilters.scope) p.set("scope", expFilters.scope);
  if (expFilters.fiscal_classification) p.set("fiscal_classification", expFilters.fiscal_classification);
  if (expFilters.payer_user_id) p.set("payer_user_id", expFilters.payer_user_id);
  try {
    let rows = await api(`/expenses?${p.toString()}`);
    if (expFilters.q) {
      const q = expFilters.q.toLowerCase();
      rows = rows.filter(r => `${r.description_normalized || ""} ${r.description_original || ""} ${r.merchant || ""}`.toLowerCase().includes(q));
    }
    const total = rows.reduce((s, r) => s + Number(r.line_amount || 0), 0);
    if (!rows.length) { wrap.innerHTML = emptyBox("💶", "Nessuna spesa", "Le spese compaiono qui dopo aver caricato e processato i documenti.", "Carica documento", "upload"); bindEmpty(wrap); return; }
    const fiscalOpts = Object.entries(FISCAL_LABELS);
    const scopeOpts = Object.entries(SCOPE_LABELS);
    const memberOpts = State.members.map(m => [m.id, m.full_name]);
    wrap.innerHTML = `
      <div class="row between" style="margin-bottom:12px"><span class="hint">${rows.length} movimenti</span><b>Totale: ${eur(total)}</b></div>
      <div class="card table-wrap"><table class="data">
        <thead><tr><th>Data</th><th>Descrizione</th><th>Categoria</th><th class="num">Importo</th><th>Fiscale</th><th>Ambito</th><th>Pagante</th><th></th></tr></thead>
        <tbody>${rows.map(r => `
          <tr data-id="${r.id}">
            <td class="mono">${fmtDate(r.purchase_date)}</td>
            <td><b>${esc(r.description_normalized || r.description_original || "—")}</b>${r.merchant ? `<div class="hint">${esc(r.merchant)}</div>` : ""}</td>
            <td><select class="inline-select" data-field="merch_category">${optList({ "": "—", ...Object.fromEntries(CATEGORIES.map(c => [c, c])) }, r.merch_category || "")}</select></td>
            <td class="num">${eur(r.line_amount)}</td>
            <td><select class="inline-select" data-field="fiscal_classification">${optList(Object.fromEntries(fiscalOpts), r.fiscal_classification)}</select></td>
            <td><select class="inline-select" data-field="scope">${optList(Object.fromEntries(scopeOpts), r.scope)}</select></td>
            <td><select class="inline-select" data-field="payer_user_id">${optList({ "": "—", ...Object.fromEntries(memberOpts) }, r.payer_user_id || "")}</select></td>
            <td class="num"><button class="btn-icon" data-del="${r.id}" title="Elimina">🗑️</button></td>
          </tr>`).join("")}
        </tbody></table></div>`;

    wrap.querySelectorAll("tr[data-id]").forEach(tr => {
      const id = tr.dataset.id;
      tr.querySelectorAll("select[data-field]").forEach(sel => {
        sel.addEventListener("change", async () => {
          const field = sel.dataset.field;
          let val = sel.value || null;
          try {
            await api(`/expenses/${id}`, { method: "PATCH", body: { [field]: val } });
            toast("Aggiornato", { type: "ok", timeout: 1500 });
          } catch (e) { toast("Errore", { desc: e.message, type: "err" }); }
        });
      });
      tr.querySelector("[data-del]").addEventListener("click", async () => {
        if (!(await confirmDialog("Eliminare la spesa?", "La riga verrà rimossa definitivamente."))) return;
        try { await api(`/expenses/${id}`, { method: "DELETE" }); toast("Spesa eliminata", { type: "ok" }); loadExpenses(); }
        catch (e) { toast("Errore", { desc: e.message, type: "err" }); }
      });
    });
  } catch (err) { wrap.innerHTML = errorBox(err.message); }
}

/* ---------- View: Casa & Bollette ---------- */
const defaultBillFilters = () => ({ utility_type: "", status: "" });
let billFilters = defaultBillFilters();
async function viewBills() {
  const c = $("#content");
  c.innerHTML = skeletonGrid();
  $("#topbar-actions").appendChild(await yearSelector(viewBills));
  const addBtn = document.createElement("button");
  addBtn.className = "btn btn-primary btn-sm";
  addBtn.innerHTML = "➕ Aggiungi bolletta";
  addBtn.addEventListener("click", () => openBillForm());
  $("#topbar-actions").appendChild(addBtn);
  const exp = document.createElement("button");
  exp.className = "btn btn-ghost btn-sm";
  exp.innerHTML = "⬇️ CSV";
  exp.addEventListener("click", () => downloadAuthed(`/bills/export.csv${State.year ? `?year=${State.year}` : ""}`, `bollette${State.year ? "_" + State.year : ""}.csv`));
  $("#topbar-actions").appendChild(exp);

  const yq = State.year ? `?year=${State.year}` : "";
  try {
    const [ov, analysis, up] = await Promise.all([
      api(`/bills/overview${yq}`), api(`/bills/analysis${yq}`), api(`/bills/upcoming`),
    ]);
    // Bollette delle utenze e spese condominiali sono distinte (categoria
    // diversa): i totali separati arrivano da /bills/overview.
    const utilTotal = ov.utilities_total != null ? ov.utilities_total : ov.total;
    const utilCount = ov.utilities_count != null ? ov.utilities_count : ov.count;
    const kpis = [
      { label: "Bollette (utenze)", value: eur(utilTotal), icon: "💡", bg: "var(--teal-100)", fg: "var(--teal-800)", delta: `${utilCount} bollett${utilCount === 1 ? "a" : "e"} · luce, gas, acqua…` },
      { label: "Spese condominiali", value: eur(ov.condo_total || 0), icon: "🏢", bg: "var(--blue-100)", fg: "#1d4ed8", delta: `${ov.condo_count || 0} voc${(ov.condo_count || 0) === 1 ? "e" : "i"} di condominio`, drill: (ov.condo_count || 0) ? { view: "bills", bills: { utility_type: "condominio" } } : null },
      { label: "Da pagare", value: eur(ov.open_total), icon: "📨", bg: "var(--amber-100)", fg: "#b45309", delta: `${ov.open_count} apert${ov.open_count === 1 ? "a" : "e"}`, drill: ov.open_count ? { view: "bills", bills: { status: "da_pagare" } } : null },
      { label: "Scadute", value: ov.overdue_count, icon: "⏰", bg: ov.overdue_count ? "var(--red-100, #fee2e2)" : "var(--blue-100)", fg: ov.overdue_count ? "#b91c1c" : "#1d4ed8", delta: "non pagate oltre scadenza", drill: ov.overdue_count ? { view: "bills", bills: { status: "scaduta" } } : null },
    ];

    const sched = renderSchedule(up);
    // Nel grafico per tipo, distinguiamo visivamente le utenze dal condominio;
    // ogni barra filtra la lista bollette per quel tipo.
    const costRows = analysis.filter(r => r.total > 0).map(r => ({
      label: (r.utility_type === "condominio" ? "🏢 " : "") + (UTILITY_LABELS[r.utility_type] || r.utility_type),
      total: r.total,
      drill: { view: "bills", bills: { utility_type: r.utility_type } },
    }));

    c.innerHTML = `
      ${kpiGrid(kpis)}

      ${sched}

      <div class="grid cols-2" style="margin-top:16px">
        ${chartCard("Costo per tipo di utenza", barChart(costRows, { labelKey: "label", valueKey: "total" }))}
        <div class="card card-pad">
          <h3 style="margin-bottom:16px">Valutazione costi e consumi</h3>
          ${analysis.length ? `<div class="table-wrap"><table class="data">
            <thead><tr><th>Utenza</th><th class="num">Totale</th><th class="num">Media</th><th class="num">Consumo</th><th class="num">€/unità</th></tr></thead>
            <tbody>${analysis.map(r => `<tr>
              <td>${UTILITY_ICONS[r.utility_type] || "🏠"} ${esc(UTILITY_LABELS[r.utility_type] || r.utility_type)}</td>
              <td class="num">${eur(r.total)}</td>
              <td class="num">${eur(r.avg_amount)}</td>
              <td class="num">${r.consumption ? `${r.consumption.toLocaleString("it-IT")} ${esc(r.consumption_unit || "")}` : "—"}</td>
              <td class="num">${r.unit_cost != null ? `${r.unit_cost.toLocaleString("it-IT", { minimumFractionDigits: 4, maximumFractionDigits: 4 })} €` : "—"}</td>
            </tr>`).join("")}</tbody></table></div>` : `<div class="empty"><div class="big">💡</div><p>Nessuna bolletta registrata per il periodo.</p></div>`}
        </div>
      </div>

      <div class="filters" style="margin-top:18px">
        <select class="select" id="bf-utility">${optList({ "": "Tutte le utenze", ...UTILITY_LABELS }, billFilters.utility_type)}</select>
        <select class="select" id="bf-status">${optList({ "": "Tutti gli stati", ...BILL_STATUS_LABELS }, billFilters.status)}</select>
        <button class="btn btn-ghost btn-sm" id="bf-reset">Azzera</button>
      </div>
      <div id="bill-list">${skeletonRows()}</div>`;

    $("#bf-utility").addEventListener("change", (e) => { billFilters.utility_type = e.target.value; loadBills(); });
    $("#bf-status").addEventListener("change", (e) => { billFilters.status = e.target.value; loadBills(); });
    $("#bf-reset").addEventListener("click", () => { billFilters = defaultBillFilters(); viewBills(); });
    c.querySelectorAll("[data-pay]").forEach(b => b.addEventListener("click", () => payBill(b.dataset.pay)));
    bindDrills(c);
    loadBills();
  } catch (err) {
    c.innerHTML = errorBox(err.message);
  }
}

function renderSchedule(up) {
  if (!up.overdue.length && !up.due_soon.length) {
    return `<div class="card card-pad" style="margin-top:16px;border-left:4px solid var(--green-500, #22c55e);display:flex;gap:12px;align-items:center">
      <span style="font-size:22px">✅</span>
      <div><b>Nessuna bolletta in scadenza</b><div class="sub" style="color:var(--text-soft);font-size:13px">Tutte le bollette registrate risultano pagate.</div></div></div>`;
  }
  const row = (b, late) => `<div class="row between" style="padding:10px 0;border-bottom:1px solid var(--border, #e5e7eb)">
    <div><b>${UTILITY_ICONS[b.utility_type] || "🏠"} ${esc(UTILITY_LABELS[b.utility_type] || b.utility_type)}</b>${b.supplier ? `<div class="hint">${esc(b.supplier)}</div>` : ""}</div>
    <div style="text-align:right">
      <b>${eur(b.total_amount)}</b>
      <div class="hint" style="color:${late ? "#b91c1c" : "var(--text-soft)"}">${b.due_date ? fmtDate(b.due_date) : "senza scadenza"}${late ? ` · ${b.days_overdue}g di ritardo` : (b.days_left != null ? ` · tra ${b.days_left}g` : "")}</div>
    </div>
    <button class="btn btn-ghost btn-sm" data-pay="${b.id}" style="margin-left:12px">Segna pagata</button>
  </div>`;
  return `<div class="card card-pad" style="margin-top:16px">
    <div class="row between" style="margin-bottom:8px"><h3>📅 Scadenzario</h3><span class="hint">Totale aperto: <b>${eur(up.open_total)}</b></span></div>
    ${up.overdue.length ? `<div style="margin-bottom:8px"><span class="badge b-scaduta" style="background:#fee2e2;color:#b91c1c">${up.overdue.length} scadut${up.overdue.length === 1 ? "a" : "e"}</span></div>${up.overdue.map(b => row(b, true)).join("")}` : ""}
    ${up.due_soon.length ? `<div style="margin:12px 0 8px"><span class="hint">In arrivo</span></div>${up.due_soon.map(b => row(b, false)).join("")}` : ""}
  </div>`;
}

async function loadBills() {
  const wrap = $("#bill-list"); if (!wrap) return;
  const p = new URLSearchParams();
  if (State.year) p.set("fiscal_year", State.year);
  if (billFilters.utility_type) p.set("utility_type", billFilters.utility_type);
  if (billFilters.status) p.set("status", billFilters.status);
  try {
    const rows = await api(`/bills?${p.toString()}`);
    if (!rows.length) { wrap.innerHTML = emptyBox("💡", "Nessuna bolletta", "Carica una bolletta dall'Archivio o aggiungila a mano: l'assistente riconosce luce, gas, acqua, rifiuti e altro.", "Carica documento", "upload"); bindEmpty(wrap); return; }
    const total = rows.reduce((s, r) => s + Number(r.total_amount || 0), 0);
    wrap.innerHTML = `
      <div class="row between" style="margin-bottom:12px"><span class="hint">${rows.length} bollette</span><b>Totale: ${eur(total)}</b></div>
      <div class="card table-wrap"><table class="data">
        <thead><tr><th>Utenza</th><th>Fornitore</th><th>Periodo</th><th>Scadenza</th><th class="num">Importo</th><th>Stato</th><th></th></tr></thead>
        <tbody>${rows.map(r => `
          <tr data-id="${r.id}">
            <td><b>${UTILITY_ICONS[r.utility_type] || "🏠"} ${esc(UTILITY_LABELS[r.utility_type] || r.utility_type)}</b>${r.property_unit_id ? `<div class="hint">🏠 ${esc(unitName(r.property_unit_id))}</div>` : ""}</td>
            <td>${esc(r.supplier || "—")}${r.consumption_quantity ? `<div class="hint">${Number(r.consumption_quantity).toLocaleString("it-IT")} ${esc(r.consumption_unit || "")}</div>` : ""}</td>
            <td class="mono">${r.period_start ? fmtDate(r.period_start) : "—"}${r.period_end ? ` → ${fmtDate(r.period_end)}` : ""}</td>
            <td class="mono">${fmtDate(r.due_date)}</td>
            <td class="num">${eur(r.total_amount)}</td>
            <td>${badge(r.status, BILL_STATUS_LABELS)}</td>
            <td class="num row" style="gap:4px;justify-content:flex-end">
              ${r.status !== "pagata" ? `<button class="btn-icon" data-pay="${r.id}" title="Segna pagata">✅</button>` : ""}
              <button class="btn-icon" data-edit="${r.id}" title="Modifica">✏️</button>
              <button class="btn-icon" data-del="${r.id}" title="Elimina">🗑️</button>
            </td>
          </tr>`).join("")}
        </tbody></table></div>`;

    wrap.querySelectorAll("[data-pay]").forEach(b => b.addEventListener("click", () => payBill(b.dataset.pay)));
    wrap.querySelectorAll("[data-edit]").forEach(b => b.addEventListener("click", () => openBillForm(rows.find(r => r.id === b.dataset.edit))));
    wrap.querySelectorAll("[data-del]").forEach(b => b.addEventListener("click", async () => {
      if (!(await confirmDialog("Eliminare la bolletta?", "La bolletta verrà rimossa definitivamente."))) return;
      try { await api(`/bills/${b.dataset.del}`, { method: "DELETE" }); toast("Bolletta eliminata", { type: "ok" }); viewBills(); }
      catch (e) { toast("Errore", { desc: e.message, type: "err" }); }
    }));
  } catch (err) { wrap.innerHTML = errorBox(err.message); }
}

async function payBill(id) {
  try { await api(`/bills/${id}/pay`, { method: "POST" }); toast("Bolletta segnata come pagata", { type: "ok" }); viewBills(); }
  catch (e) { toast("Errore", { desc: e.message, type: "err" }); }
}

function openBillForm(bill = null) {
  const b = bill || {};
  const memberOpts = State.members.map(m => [m.id, m.full_name]);
  openModal(`
    <div class="modal-head"><h3>${bill ? "Modifica bolletta" : "Aggiungi bolletta"}</h3><button class="btn-icon" data-close>✕</button></div>
    <form id="bill-form" class="grid cols-2" style="gap:12px">
      <div class="field"><label>Tipo utenza</label><select class="select" name="utility_type">${optList(UTILITY_LABELS, b.utility_type || "altro")}</select></div>
      <div class="field"><label>Fornitore</label><input class="input" name="supplier" value="${esc(b.supplier || "")}"></div>
      <div class="field"><label>Importo totale (€)</label><input class="input" type="number" step="0.01" name="total_amount" value="${esc(b.total_amount ?? "")}"></div>
      <div class="field"><label>Scadenza</label><input class="input" type="date" name="due_date" value="${esc(b.due_date || "")}"></div>
      <div class="field"><label>Periodo dal</label><input class="input" type="date" name="period_start" value="${esc(b.period_start || "")}"></div>
      <div class="field"><label>Periodo al</label><input class="input" type="date" name="period_end" value="${esc(b.period_end || "")}"></div>
      <div class="field"><label>Consumo</label><input class="input" type="number" step="0.001" name="consumption_quantity" value="${esc(b.consumption_quantity ?? "")}"></div>
      <div class="field"><label>Unità</label><input class="input" name="consumption_unit" placeholder="kWh, Smc, m³" value="${esc(b.consumption_unit || "")}"></div>
      <div class="field"><label>Stato</label><select class="select" name="status">${optList(BILL_STATUS_LABELS, b.status || "da_pagare")}</select></div>
      <div class="field"><label>Intestatario</label><select class="select" name="payer_user_id">${optList({ "": "—", ...Object.fromEntries(memberOpts) }, b.payer_user_id || "")}</select></div>
      ${State.units.length ? `<div class="field"><label>Unità immobiliare</label><select class="select" name="property_unit_id">${optList({ "": "—", ...Object.fromEntries(State.units.map(u => [u.id, u.name])) }, b.property_unit_id || "")}</select></div>` : ""}
      <div class="field" style="grid-column:1/-1"><label>Note</label><input class="input" name="notes" value="${esc(b.notes || "")}"></div>
      <div class="row between" style="grid-column:1/-1;margin-top:6px">
        <button type="button" class="btn btn-ghost" data-close>Annulla</button>
        <button type="submit" class="btn btn-primary">${bill ? "Salva" : "Aggiungi"}</button>
      </div>
    </form>`);
  $("#modal-root").querySelectorAll("[data-close]").forEach(el => el.addEventListener("click", closeModal));
  $("#bill-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target).entries());
    const body = {};
    // I campi svuotati vanno inviati come null: così il PATCH (exclude_unset)
    // li azzera nel DB. In creazione i null vengono scartati da exclude_none.
    for (const [k, v] of Object.entries(fd)) { body[k] = v === "" ? null : v; }
    try {
      if (bill) await api(`/bills/${bill.id}`, { method: "PATCH", body });
      else await api("/bills", { method: "POST", body });
      toast(bill ? "Bolletta aggiornata" : "Bolletta aggiunta", { type: "ok" });
      closeModal(); viewBills();
    } catch (err) { toast("Errore", { desc: err.message, type: "err" }); }
  });
}

/* ---------- View: Chat ---------- */
let chatHistory = [];
function viewChat() {
  const c = $("#content");
  const suggestions = [
    "Registra una spesa: 45€ in farmacia oggi",
    "Ieri 60€ di benzina pagati da me",
    "Cancella la spesa di benzina di ieri",
    "Quanto ho speso in farmaci nel 2025?",
    "Quanto spendo di luce e gas? È aumentato?",
    "Quali bollette devo ancora pagare?",
  ];
  c.innerHTML = `
    <div class="card card-pad chat-wrap">
      ${chatHistory.length ? "" : `<div class="suggest">${suggestions.map(s => `<button data-sg="${esc(s)}">${esc(s)}</button>`).join("")}</div>`}
      <div class="chat-scroll" id="chat-scroll">
        ${chatHistory.length ? chatHistory.map(renderMsg).join("") : `<div class="empty"><div class="big">💬</div><h3>Ciao! Sono il tuo assistente spese.</h3><p>Puoi <b>registrare una spesa</b> descrivendola a parole (es. “ho speso 30€ al supermercato oggi”): se manca qualcosa te lo chiedo. Oppure chiedimi un riepilogo, un totale per categoria o cosa è detraibile.</p></div>`}
      </div>
      <div class="chat-input">
        <textarea class="input" id="chat-text" rows="1" placeholder="Registra una spesa o fai una domanda…"></textarea>
        <button class="btn btn-primary" id="chat-send">Invia</button>
      </div>
    </div>`;
  const ta = $("#chat-text");
  ta.addEventListener("input", () => { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 140) + "px"; });
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } });
  $("#chat-send").addEventListener("click", sendChat);
  c.querySelectorAll("[data-sg]").forEach(b => b.addEventListener("click", () => { ta.value = b.dataset.sg; sendChat(); }));
  scrollChat();
}
function renderMsg(m) {
  return `<div class="msg ${m.role === "user" ? "user" : "bot"}">
    <div class="ava">${m.role === "user" ? initials(State.user?.full_name) : "🤖"}</div>
    <div class="bubble">${esc(m.content)}</div></div>`;
}
function scrollChat() { const s = $("#chat-scroll"); if (s) s.scrollTop = s.scrollHeight; }
async function sendChat() {
  const ta = $("#chat-text"); const msg = ta.value.trim(); if (!msg) return;
  const history = chatHistory.slice();
  chatHistory.push({ role: "user", content: msg });
  const scroll = $("#chat-scroll");
  if (scroll.querySelector(".empty")) scroll.innerHTML = "";
  const suggest = $(".suggest"); if (suggest) suggest.remove();
  scroll.insertAdjacentHTML("beforeend", renderMsg({ role: "user", content: msg }));
  ta.value = ""; ta.style.height = "auto";
  scroll.insertAdjacentHTML("beforeend", `<div class="msg bot" id="typing"><div class="ava">🤖</div><div class="bubble"><span class="spin"></span></div></div>`);
  scrollChat();
  try {
    const res = await api("/chat", { method: "POST", body: { message: msg, history } });
    $("#typing")?.remove();
    chatHistory.push({ role: "assistant", content: res.answer });
    scroll.insertAdjacentHTML("beforeend", renderMsg({ role: "assistant", content: res.answer }));
  } catch (err) {
    $("#typing")?.remove();
    scroll.insertAdjacentHTML("beforeend", renderMsg({ role: "assistant", content: "⚠️ " + err.message }));
  }
  scrollChat();
}

/* ---------- View: Settings ---------- */
async function viewSettings() {
  const c = $("#content");
  c.innerHTML = skeletonRows();
  try {
    const [hh, members, units] = await Promise.all([
      api("/household"), api("/household/members"), api("/household/units").catch(() => []),
    ]);
    State.members = members; indexMembers();
    State.units = units || [];
    const isAdmin = State.user?.role === "admin";
    $("#topbar-actions").innerHTML = "";
    const exportBtn = document.createElement("a");
    exportBtn.className = "btn btn-ghost btn-sm";
    exportBtn.href = "/stats/export.csv" + (State.year ? `?year=${State.year}` : "");
    exportBtn.textContent = "⬇️ Export CSV commercialista";
    exportBtn.addEventListener("click", (e) => { e.preventDefault(); downloadAuthed(exportBtn.href, "riepilogo_fiscale.csv"); });
    $("#topbar-actions").appendChild(exportBtn);

    c.innerHTML = `
      <div class="grid cols-2" style="align-items:start">
        <div class="card card-pad">
          <h3 style="margin-bottom:6px">Nucleo familiare</h3>
          <p class="hint" style="margin-bottom:16px">${members.length} membr${members.length === 1 ? "o" : "i"}</p>
          <dl class="kv">
            <dt>Nome nucleo</dt><dd><b>${esc(hh.name)}</b></dd>
            <dt>ID nucleo</dt><dd><code style="font-size:12px">${esc(hh.id)}</code> <button class="btn-icon" id="copy-id" title="Copia">📋</button></dd>
          </dl>
          <p class="hint" style="margin-top:12px">Condividi l'ID nucleo con un familiare per farlo unire dalla schermata “Unisciti”.</p>
        </div>
        <div class="card card-pad">
          <div class="row between" style="margin-bottom:14px"><h3>Membri</h3>${isAdmin ? `<button class="btn btn-primary btn-sm" id="add-member">+ Aggiungi</button>` : ""}</div>
          <div class="table-wrap"><table class="data"><thead><tr><th>Nome</th><th>Ruolo</th><th>Cod. fiscale</th><th></th></tr></thead>
          <tbody>${members.map(m => `<tr>
            <td><div class="row" style="gap:9px"><span class="avatar" style="width:28px;height:28px;font-size:11px">${initials(m.full_name)}</span><div><b>${esc(m.full_name)}</b><div class="hint">${esc(m.email)}</div></div></div></td>
            <td>${m.role === "admin" ? `<span class="badge b-familiare">Admin</span>` : `<span class="badge b-non_rilevante">Membro</span>`}</td>
            <td class="mono">${esc(m.codice_fiscale || "—")}</td>
            <td class="num row" style="gap:4px;justify-content:flex-end">${(isAdmin || m.id === State.user.id) ? `<button class="btn-icon" data-edit-member="${m.id}" title="Modifica">✏️</button>` : ""}${isAdmin && m.id !== State.user.id ? `<button class="btn-icon" data-rm="${m.id}" title="Rimuovi">🗑️</button>` : ""}${m.id === State.user.id ? `<span class="hint">tu</span>` : ""}</td>
          </tr>`).join("")}</tbody></table></div>
        </div>
      </div>

      <div class="card card-pad" style="margin-top:16px">
        <div class="row between" style="margin-bottom:6px">
          <h3>🏢 Immobili / Unità immobiliari</h3>
          ${isAdmin ? `<button class="btn btn-primary btn-sm" id="add-unit">+ Aggiungi unità</button>` : ""}
        </div>
        <p class="hint" style="margin-bottom:14px">Configura le unità del nucleo (casa, appartamenti, box). Servono a gestire le spese di condominio e ad <b>addestrare l'assistente</b>: indicando gli <i>alias</i> (come l'unità compare nei verbali/riparti — interno, scala, subalterno, nome intestatario) l'assistente attribuisce la spesa all'unità giusta senza dover chiedere.</p>
        ${units.length ? `<div class="table-wrap"><table class="data">
          <thead><tr><th>Unità</th><th>Condominio</th><th>Alias / riconoscimento</th><th class="num">Millesimi</th>${isAdmin ? "<th></th>" : ""}</tr></thead>
          <tbody>${units.map(u => `<tr>
            <td><b>${esc(u.name)}</b>${u.is_primary ? ` <span class="badge b-familiare">principale</span>` : ""}${u.address ? `<div class="hint">${esc(u.address)}</div>` : ""}</td>
            <td>${esc(u.condominium_name || "—")}${u.owner_name ? `<div class="hint">int. ${esc(u.owner_name)}</div>` : ""}</td>
            <td class="hint">${esc(u.aliases || "—")}</td>
            <td class="num mono">${u.millesimi != null ? esc(u.millesimi) : "—"}</td>
            ${isAdmin ? `<td class="num row" style="gap:4px;justify-content:flex-end"><button class="btn-icon" data-edit-unit="${u.id}" title="Modifica">✏️</button><button class="btn-icon" data-del-unit="${u.id}" title="Elimina">🗑️</button></td>` : ""}
          </tr>`).join("")}</tbody></table></div>` : `<div class="empty"><div class="big">🏢</div><p>Nessuna unità configurata.${isAdmin ? " Aggiungi la prima per gestire al meglio le spese di condominio." : ""}</p></div>`}
      </div>

      <div class="card card-pad" style="margin-top:16px">
        <h3 style="margin-bottom:6px">🧠 Addestramento assistente</h3>
        <p class="hint" style="margin-bottom:14px">Istruzioni libere che l'assistente seguirà per questo nucleo: convenzioni, come trattare casi ricorrenti, quale unità considerare di default per il condominio, preferenze di classificazione. Vengono aggiunte al suo contesto.</p>
        <textarea class="input" id="agent-instructions" rows="6" placeholder="Es. La nostra unità nel condominio Aurora è l'interno 5, intestata a Mario Rossi. Per le bollette del gas considerare la seconda casa solo se citato 'Via Verdi'." ${isAdmin ? "" : "disabled"}>${esc(hh.agent_instructions || "")}</textarea>
        ${isAdmin ? `<div class="row" style="margin-top:12px;justify-content:flex-end"><button class="btn btn-primary btn-sm" id="save-instructions">Salva istruzioni</button></div>` : `<p class="hint" style="margin-top:10px">Solo l'amministratore può modificare l'addestramento.</p>`}
      </div>`;

    $("#copy-id")?.addEventListener("click", () => { navigator.clipboard.writeText(hh.id); toast("ID copiato", { type: "ok", timeout: 1500 }); });
    $("#add-member")?.addEventListener("click", addMemberDialog);
    c.querySelectorAll("[data-edit-member]").forEach(b => b.addEventListener("click", () => editMemberDialog(members.find(m => m.id === b.dataset.editMember), isAdmin)));
    c.querySelectorAll("[data-rm]").forEach(b => b.addEventListener("click", async () => {
      if (!(await confirmDialog("Rimuovere il membro?", "Perderà l'accesso al nucleo. Le spese già attribuite restano nello storico."))) return;
      try { await api(`/household/members/${b.dataset.rm}`, { method: "DELETE" }); toast("Membro rimosso", { type: "ok" }); viewSettings(); }
      catch (e) { toast("Errore", { desc: e.message, type: "err" }); }
    }));
    $("#add-unit")?.addEventListener("click", () => openUnitForm());
    c.querySelectorAll("[data-edit-unit]").forEach(b => b.addEventListener("click", () => openUnitForm(units.find(u => u.id === b.dataset.editUnit))));
    c.querySelectorAll("[data-del-unit]").forEach(b => b.addEventListener("click", async () => {
      if (!(await confirmDialog("Eliminare l'unità?", "Le bollette collegate resteranno, ma senza associazione all'unità."))) return;
      try { await api(`/household/units/${b.dataset.delUnit}`, { method: "DELETE" }); toast("Unità eliminata", { type: "ok" }); viewSettings(); }
      catch (e) { toast("Errore", { desc: e.message, type: "err" }); }
    }));
    $("#save-instructions")?.addEventListener("click", async () => {
      const val = $("#agent-instructions").value;
      try { await api("/household", { method: "PATCH", body: { agent_instructions: val } }); toast("Addestramento salvato", { type: "ok" }); }
      catch (e) { toast("Errore", { desc: e.message, type: "err" }); }
    });
  } catch (err) { c.innerHTML = errorBox(err.message); }
}

function openUnitForm(unit = null) {
  const u = unit || {};
  openModal(`
    <div class="modal-head"><h3>${unit ? "Modifica unità" : "Aggiungi unità immobiliare"}</h3><button class="btn-icon" data-close>✕</button></div>
    <form id="unit-form" class="grid cols-2" style="gap:12px">
      <div class="field" style="grid-column:1/-1"><label>Nome unità</label><input class="input" name="name" placeholder="es. Casa Via Roma 10, int. 5" value="${esc(u.name || "")}" required></div>
      <div class="field"><label>Indirizzo</label><input class="input" name="address" value="${esc(u.address || "")}"></div>
      <div class="field"><label>Condominio</label><input class="input" name="condominium_name" placeholder="es. Condominio Aurora" value="${esc(u.condominium_name || "")}"></div>
      <div class="field"><label>Intestatario (nei verbali)</label><input class="input" name="owner_name" value="${esc(u.owner_name || "")}"></div>
      <div class="field"><label>Millesimi</label><input class="input" type="number" step="0.001" name="millesimi" value="${esc(u.millesimi ?? "")}"></div>
      <div class="field" style="grid-column:1/-1"><label>Alias / come compare nei documenti <span class="hint">(separati da virgola)</span></label><input class="input" name="aliases" placeholder="es. interno 5, scala B, sub 12, Rossi Mario" value="${esc(u.aliases || "")}"></div>
      <div class="field" style="grid-column:1/-1"><label>Note <span class="hint">(addestramento)</span></label><input class="input" name="notes" value="${esc(u.notes || "")}"></div>
      <label class="field" style="grid-column:1/-1;flex-direction:row;align-items:center;gap:8px"><input type="checkbox" name="is_primary" ${u.is_primary ? "checked" : ""}><span>Unità principale (default quando l'attribuzione è incerta)</span></label>
      <div class="row between" style="grid-column:1/-1;margin-top:6px">
        <button type="button" class="btn btn-ghost" data-close>Annulla</button>
        <button type="submit" class="btn btn-primary">${unit ? "Salva" : "Aggiungi"}</button>
      </div>
    </form>`);
  $("#modal-root").querySelectorAll("[data-close]").forEach(el => el.addEventListener("click", closeModal));
  $("#unit-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const fd = Object.fromEntries(new FormData(form).entries());
    const body = {
      name: fd.name,
      address: fd.address || null,
      condominium_name: fd.condominium_name || null,
      owner_name: fd.owner_name || null,
      millesimi: fd.millesimi === "" ? null : fd.millesimi,
      aliases: fd.aliases || null,
      notes: fd.notes || null,
      is_primary: form.querySelector("[name=is_primary]").checked,
    };
    try {
      if (unit) await api(`/household/units/${unit.id}`, { method: "PATCH", body });
      else await api("/household/units", { method: "POST", body });
      toast(unit ? "Unità aggiornata" : "Unità aggiunta", { type: "ok" });
      closeModal(); viewSettings();
    } catch (err) { toast("Errore", { desc: err.message, type: "err" }); }
  });
}

function addMemberDialog() {
  openModal(`
    <div class="modal-head"><h3>Aggiungi un membro</h3><button class="btn-icon" data-close>✕</button></div>
    <form id="member-form">
      <div class="field"><label>Nome completo</label><input class="input" name="full_name" required></div>
      <div class="field"><label>Email</label><input class="input" type="email" name="email" required></div>
      <div class="field"><label>Codice fiscale <span class="hint">(opzionale)</span></label><input class="input" name="codice_fiscale" maxlength="16" style="text-transform:uppercase"></div>
      <div class="field"><label>Password provvisoria <span class="hint">(min 8)</span></label><input class="input" type="password" name="password" minlength="8" required></div>
      <p class="hint" style="margin-bottom:16px">Comunica email e password al familiare: potrà accedere e cambiare i dati.</p>
      <button class="btn btn-primary btn-block" type="submit">Crea accesso</button>
    </form>`);
  $("#modal-root [data-close]").addEventListener("click", closeModal);
  $("#member-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target).entries());
    try { await api("/household/members", { method: "POST", body: data }); toast("Membro aggiunto", { type: "ok" }); closeModal(); viewSettings(); }
    catch (err) { toast("Errore", { desc: err.message, type: "err" }); }
  });
}

function editMemberDialog(member, isAdmin) {
  if (!member) return;
  const isSelf = member.id === State.user.id;
  openModal(`
    <div class="modal-head"><h3>Modifica membro</h3><button class="btn-icon" data-close>✕</button></div>
    <form id="member-edit-form">
      <div class="field"><label>Nome completo</label><input class="input" name="full_name" value="${esc(member.full_name || "")}" required></div>
      <div class="field"><label>Email</label><input class="input" type="email" name="email" value="${esc(member.email || "")}" required></div>
      <div class="field"><label>Codice fiscale <span class="hint">(opzionale)</span></label><input class="input" name="codice_fiscale" maxlength="16" style="text-transform:uppercase" value="${esc(member.codice_fiscale || "")}"></div>
      ${isAdmin ? `<div class="field"><label>Ruolo</label><select class="select" name="role">${optList({ member: "Membro", admin: "Admin" }, member.role)}</select></div>` : ""}
      <div class="field"><label>Nuova password <span class="hint">(lascia vuoto per non cambiarla, min 8)</span></label><input class="input" type="password" name="password" minlength="8" autocomplete="new-password"></div>
      <button class="btn btn-primary btn-block" type="submit">Salva modifiche</button>
    </form>`);
  $("#modal-root [data-close]").addEventListener("click", closeModal);
  $("#member-edit-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target).entries());
    if (!data.password) delete data.password;
    data.codice_fiscale = (data.codice_fiscale || "").trim().toUpperCase() || null;
    try {
      await api(`/household/members/${member.id}`, { method: "PATCH", body: data });
      toast("Membro aggiornato", { type: "ok" });
      closeModal();
      if (isSelf) { State.user = await api("/auth/me").catch(() => State.user); }
      viewSettings();
    }
    catch (err) { toast("Errore", { desc: err.message, type: "err" }); }
  });
}

async function downloadAuthed(url, filename) {
  try {
    const res = await api(url, { raw: true });
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(a.href);
  } catch (e) { toast("Export non riuscito", { desc: e.message, type: "err" }); }
}

/* ---------- Shared render helpers ---------- */
function badge(value, labels) { return `<span class="badge b-${value}">${esc(labels[value] || value)}</span>`; }
function optList(map, selected) { return Object.entries(map).map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(selected) ? "selected" : ""}>${esc(l)}</option>`).join(""); }
function skeletonGrid() { return `<div class="grid cols-4">${Array(4).fill(`<div class="card skeleton" style="height:108px"></div>`).join("")}</div><div class="grid cols-2" style="margin-top:20px">${Array(2).fill(`<div class="card skeleton" style="height:280px"></div>`).join("")}</div>`; }
function skeletonRows() { return `<div class="card skeleton" style="height:340px"></div>`; }
function emptyBox(icon, title, text, cta, go) { return `<div class="card card-pad empty"><div class="big">${icon}</div><h3>${esc(title)}</h3><p>${esc(text)}</p>${cta ? `<button class="btn btn-primary" data-go="${go}" style="margin-top:14px">${esc(cta)}</button>` : ""}</div>`; }
function bindEmpty(wrap) { wrap.querySelectorAll("[data-go]").forEach(b => b.addEventListener("click", () => navigate(b.dataset.go))); }
function errorBox(msg) { return `<div class="card card-pad empty"><div class="big">⚠️</div><h3>Qualcosa è andato storto</h3><p>${esc(msg)}</p></div>`; }

function indexMembers() { State.membersById = Object.fromEntries(State.members.map(m => [m.id, m])); }

function updateReviewBadge(count) {
  const item = $(".nav-item[data-nav=documents]");
  if (!item) return;
  let dot = item.querySelector(".badge-dot");
  if (count > 0) {
    if (!dot) { dot = document.createElement("span"); dot.className = "badge-dot"; item.appendChild(dot); }
    dot.textContent = count;
  } else if (dot) { dot.remove(); }
}

/* ---------- Boot ---------- */
function logout(silent = false) {
  State.token = null; State.user = null; localStorage.removeItem("token");
  if (!silent) toast("Disconnesso", { type: "info", timeout: 1500 });
  renderAuth("login");
}

async function boot() {
  if (!State.token) { renderAuth("login"); return; }
  try {
    State.user = await api("/auth/me");
    const [members, hh, units] = await Promise.all([
      api("/household/members"),
      api("/household").catch(() => null),
      api("/household/units").catch(() => []),
    ]);
    State.members = members; indexMembers();
    State.units = units || [];
    if (hh) State.user.household_name = hh.name;
    renderShell();
    navigate(State.view || "dashboard");
  } catch (err) {
    logout(true);
    renderAuth("login");
  }
}

document.addEventListener("DOMContentLoaded", boot);

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
  paymentMethods: [],
  paymentMethodsById: {},
  categories: [],
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
const PAYMENT_TYPE_LABELS = {
  carta_credito: "Carta di credito", carta_debito: "Carta di debito",
  bancomat: "Bancomat", prepagata: "Prepagata", contanti: "Contanti",
  bonifico: "Bonifico", addebito_diretto: "Addebito diretto (RID)",
  assegno: "Assegno", paypal: "PayPal / wallet", altro: "Altro",
};
const PAYMENT_TYPE_ICONS = {
  carta_credito: "💳", carta_debito: "💳", bancomat: "🏧", prepagata: "💳",
  contanti: "💶", bonifico: "🏦", addebito_diretto: "🔁", assegno: "🧾",
  paypal: "🅿️", altro: "💼",
};
// Categorie di base (foglie), con il gruppo (macro-categoria) di appartenenza:
// le voci di reparto stanno sotto «spesa supermercato», "farmaci" è di primo
// livello. Fallback usato finché /household/categories non è caricato in State.
const SUPERMARKET_GROUP = "spesa supermercato";
const BUILTIN_CATEGORIES = [
  { name: "frutta e verdura", parent: SUPERMARKET_GROUP },
  { name: "carne e pesce", parent: SUPERMARKET_GROUP },
  { name: "latticini e uova", parent: SUPERMARKET_GROUP },
  { name: "pane, forno e colazione", parent: SUPERMARKET_GROUP },
  { name: "pasta, riso e dispensa", parent: SUPERMARKET_GROUP },
  { name: "bevande", parent: SUPERMARKET_GROUP },
  { name: "surgelati", parent: SUPERMARKET_GROUP },
  { name: "infanzia", parent: SUPERMARKET_GROUP },
  { name: "igiene personale", parent: SUPERMARKET_GROUP },
  { name: "pulizia casa", parent: SUPERMARKET_GROUP },
  { name: "animali", parent: SUPERMARKET_GROUP },
  { name: "farmaci", parent: null },
  { name: "parafarmacia da supermercato", parent: SUPERMARKET_GROUP },
  { name: "casa e cucina", parent: SUPERMARKET_GROUP },
  { name: "altre spese supermercato", parent: SUPERMARKET_GROUP },
];

// Opzioni <select> per la categoria merceologica, raggruppate per macro-categoria
// (le sottocategorie del supermercato in un <optgroup>). Usa le categorie note
// caricate in State (di base + personalizzate); ricade su BUILTIN_CATEGORIES.
function categoryOptionsHtml(selected, emptyLabel = "—") {
  const cats = (State.categories && State.categories.length) ? State.categories : BUILTIN_CATEGORIES;
  const sel = selected || "";
  const opt = (v, label) => `<option value="${esc(v)}"${v === sel ? " selected" : ""}>${esc(label)}</option>`;
  let html = `<option value=""${sel === "" ? " selected" : ""}>${esc(emptyLabel)}</option>`;
  const tops = cats.filter(c => !c.parent);
  const groups = {};
  for (const c of cats) if (c.parent) (groups[c.parent] = groups[c.parent] || []).push(c);
  for (const c of tops) html += opt(c.name, c.name);
  for (const g of Object.keys(groups)) {
    html += `<optgroup label="${esc(g)}">` + groups[g].map(c => opt(c.name, c.name)).join("") + `</optgroup>`;
  }
  // Se il valore selezionato non è tra le categorie note (es. storico/eliminata),
  // mostralo comunque come opzione così non si perde la selezione.
  if (sel && !cats.some(c => c.name === sel)) html += opt(sel, sel + " (storico)");
  return html;
}
const PALETTE = ["#0d9488","#3b82f6","#f59e0b","#8b5cf6","#ec4899","#22c55e","#ef4444","#06b6d4","#eab308","#6366f1","#14b8a6","#f97316","#a855f7","#64748b"];

/* ---------- Helpers ---------- */
const $ = (sel, root = document) => root.querySelector(sel);
const app = () => $("#app");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
const eur = (n) => (Number(n) || 0).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
// Importo compatto per le etichette fitte (es. cime delle colonne mensili): "€1,2k".
const eurShort = (n) => {
  const v = Number(n) || 0;
  if (!v) return "";
  if (Math.abs(v) >= 1000) return "€" + (v / 1000).toLocaleString("it-IT", { maximumFractionDigits: 1 }) + "k";
  return "€" + v.toLocaleString("it-IT", { maximumFractionDigits: 0 });
};
const MONTHS_FULL = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"];
const fmtDate = (d) => d ? new Date(d).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" }) : "—";
const initials = (name) => (name || "?").trim().split(/\s+/).map(w => w[0]).slice(0, 2).join("").toUpperCase();
const memberName = (id) => id ? (State.membersById[id]?.full_name || "—") : "—";
const unitName = (id) => id ? (State.units.find(u => u.id === id)?.name || "—") : "—";
const paymentMethodLabel = (id) => {
  if (!id) return "—";
  const pm = State.paymentMethodsById[id];
  if (!pm) return "—";
  return pm.label + (pm.last4 ? ` ••${pm.last4}` : "");
};
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

// Dialog con area di testo libera (es. istruzioni per la rielaborazione).
// Risolve con la stringa inserita (anche vuota) o null se si annulla.
function promptDialog(title, message, { placeholder = "", okText = "Conferma", value = "" } = {}) {
  return new Promise((resolve) => {
    openModal(`
      <div class="modal-head"><h3>${esc(title)}</h3></div>
      ${message ? `<p style="color:var(--text-soft);margin-bottom:14px">${esc(message)}</p>` : ""}
      <textarea class="input" id="prompt-text" rows="4" placeholder="${esc(placeholder)}" style="margin-bottom:22px">${esc(value)}</textarea>
      <div class="row between">
        <button class="btn btn-ghost" id="prompt-cancel">Annulla</button>
        <button class="btn btn-primary" id="prompt-ok">${esc(okText)}</button>
      </div>`);
    const root = $("#modal-root");
    const ta = $("#prompt-text"); if (ta) ta.focus();
    // I listener sono legati ai pulsanti interni (rimossi col modale, niente
    // leak) e gestiamo anche chiusura via overlay/ESC, così la Promise si
    // risolve sempre (niente promise sospese). 'done' evita doppie risoluzioni.
    let done = false;
    const finish = (val) => {
      if (done) return; done = true;
      document.removeEventListener("keydown", onEsc);
      closeModal();
      resolve(val);
    };
    const onEsc = (e) => { if (e.key === "Escape") finish(null); };
    document.addEventListener("keydown", onEsc);
    $("#prompt-ok").addEventListener("click", () => finish(ta ? ta.value : ""));
    $("#prompt-cancel").addEventListener("click", () => finish(null));
    const overlay = $(".overlay", root);
    if (overlay) overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) finish(null); });
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
      <p class="hint" style="margin-bottom:14px">Inserisci l'email del tuo account e verifica la tua identità, poi scegli una nuova password.</p>
      <div class="field"><label>Email</label><input class="input" type="email" name="email" autocomplete="email" required></div>
      <div class="field"><label>Metodo di verifica</label>
        <select class="select" id="recover-method">
          <option value="codice_fiscale">Codice fiscale dell'account</option>
          <option value="recovery_key">Codice di recupero (amministratore)</option>
        </select>
      </div>
      <div class="field" data-recover-field="codice_fiscale"><label>Codice fiscale</label><input class="input" name="codice_fiscale" maxlength="16" style="text-transform:uppercase"></div>
      <div class="field" data-recover-field="recovery_key" hidden><label>Codice di recupero</label><input class="input" name="recovery_key" autocomplete="off"><span class="hint">Il valore di <code>ADMIN_RECOVERY_KEY</code> configurato nel deploy. Usalo se sei l'amministratore e non hai un codice fiscale.</span></div>
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

  const recoverMethod = $("#recover-method");
  if (recoverMethod) {
    const syncRecoverFields = () => {
      $("#app").querySelectorAll("[data-recover-field]").forEach(f => {
        const active = f.dataset.recoverField === recoverMethod.value;
        f.hidden = !active;
        const input = f.querySelector("input");
        if (input) { input.disabled = !active; if (!active) input.value = ""; }
      });
    };
    recoverMethod.addEventListener("change", syncRecoverFields);
    syncRecoverFields();
  }

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
    // Non inviare i campi di verifica lasciati vuoti (recupero password).
    if (mode === "recover") {
      if (!data.codice_fiscale) delete data.codice_fiscale;
      if (!data.recovery_key) delete data.recovery_key;
    }
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
  { id: "analisi", icon: "📈", label: "Analisi" },
  { id: "esplora", icon: "🧭", label: "Esplora" },
  { id: "upload", icon: "⬆️", label: "Carica documento" },
  { id: "documents", icon: "🗂️", label: "Archivio" },
  { id: "revisione", icon: "🔍", label: "Revisione" },
  { id: "expenses", icon: "💶", label: "Spese" },
  { id: "bills", icon: "🏠", label: "Casa & Bollette" },
  { id: "chat", icon: "💬", label: "Assistente" },
  { id: "settings", icon: "⚙️", label: "Impostazioni" },
];

// La sezione "Farmaci" (dati sanitari sensibili) è riservata agli admin e
// compare nel menu solo per loro.
function navItems() {
  const items = [...NAV];
  if (State.user?.role === "admin") {
    const i = items.findIndex(n => n.id === "expenses");
    items.splice(i + 1, 0, { id: "farmaci", icon: "💊", label: "Farmaci" });
  }
  return items;
}

function renderShell() {
  document.documentElement.dataset.theme = State.theme;
  const reviewCount = State._reviewCount || 0;
  app().innerHTML = `
    <div class="shell">
      <aside class="sidebar" id="sidebar">
        <div class="brand"><span class="logo">🧾</span><div><b>Spese Familiari</b><small>${esc(State.user?.household_name || "Archivio fiscale")}</small></div></div>
        ${navItems().map(n => `
          <button class="nav-item ${State.view === n.id ? "active" : ""}" data-nav="${n.id}">
            <span class="ico">${n.icon}</span><span>${n.label}</span>
            ${n.id === "revisione" && reviewCount ? `<span class="badge-dot">${reviewCount}</span>` : ""}
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
    analisi: ["Analisi", "Andamento mensile, esercenti, confronto tra anni e osservazioni automatiche"],
    esplora: ["Esplora", "Analisi interattiva delle spese: clicca i grafici per filtrare tutta la pagina (stile BI)"],
    upload: ["Carica documento", "Scontrini, fatture, ricevute: l'assistente AI li legge e li archivia"],
    documents: ["Archivio documenti", "Tutti i documenti caricati, con stato ed estrazione"],
    revisione: ["Revisione", "Avvisi su dati incompleti e proposte di miglioramento da approvare"],
    expenses: ["Spese", "Movimenti e righe di dettaglio, correggibili al volo"],
    farmaci: ["Farmaci", "Catalogo dei medicinali acquistati · riservato all'amministratore"],
    bills: ["Casa & Bollette", "Riconoscimento bollette, valutazione costi e scadenze di pagamento"],
    chat: ["Assistente", "Registra spese descrivendole e interroga lo storico in linguaggio naturale"],
    settings: ["Impostazioni", "Nucleo, membri, immobili e addestramento dell'assistente"],
  };
  // Difesa: la vista farmaci è solo per admin (il menu non la mostra agli altri).
  if (view === "farmaci" && State.user?.role !== "admin") view = State.view = "dashboard";
  $("#page-title").textContent = titles[view][0];
  $("#page-sub").textContent = titles[view][1];
  $("#topbar-actions").innerHTML = "";
  const views = { dashboard: viewDashboard, analisi: viewAnalisi, esplora: viewEsplora, upload: viewUpload, documents: viewDocuments, revisione: viewRevisione, expenses: viewExpenses, farmaci: viewFarmaci, bills: viewBills, chat: viewChat, settings: viewSettings };
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

// Grafico a colonne verticali per l'andamento mensile: ogni colonna è impilata
// (spese in basso + bollette in alto) e, se ha una drill spec, è cliccabile.
const COL_EXP_COLOR = "#0d9488", COL_BILL_COLOR = "#f59e0b";
function columnChart(rows) {
  if (!rows.some(r => r.total > 0)) return `<div class="empty"><div class="big">📭</div><p>Nessun movimento per il periodo selezionato.</p></div>`;
  const max = Math.max(...rows.map(r => r.total), 1);
  const cols = rows.map(r => {
    const eH = Math.max(0, (r.expenses / max) * 100), bH = Math.max(0, (r.bills / max) * 100);
    const tip = `${esc(r.full || r.label)}: ${eur(r.total)}` + (r.bills ? ` · spese ${eur(r.expenses)}, bollette ${eur(r.bills)}` : "");
    return `<div class="col-item${r.drill ? " col-clickable" : ""}"${drillAttr(r.drill)} title="${tip}">
        <div class="col-bars">
          <div class="col-amt">${eurShort(r.total)}</div>
          <div class="col-stack">
            <div class="col-seg" style="height:${bH}%;background:${COL_BILL_COLOR}"></div>
            <div class="col-seg" style="height:${eH}%;background:${COL_EXP_COLOR}"></div>
          </div>
        </div>
        <div class="col-lbl">${esc(r.label)}</div>
      </div>`;
  }).join("");
  const legend = `<div class="legend" style="margin-top:16px">
      <span><i class="dot" style="background:${COL_EXP_COLOR}"></i>Spese</span>
      <span><i class="dot" style="background:${COL_BILL_COLOR}"></i>Bollette</span>
    </div>`;
  return `<div class="col-chart">${cols}</div>${legend}`;
}

// Card "Andamento mensile" con mini-statistiche (totale, media, picco) + colonne.
function monthlyCard(monthly, year, { drillYear = true, style = "" } = {}) {
  const active = monthly.filter(m => m.total > 0);
  const total = monthly.reduce((s, m) => s + m.total, 0);
  const avg = active.length ? total / active.length : 0;
  const peak = active.reduce((a, m) => (m.total > (a?.total || 0) ? m : a), null);
  const yBase = year ? { fiscal_year: String(year) } : {};
  const rows = monthly.map(m => ({
    label: m.label, full: MONTHS_FULL[m.month], total: m.total,
    expenses: m.expenses_total, bills: m.bills_total,
    drill: drillYear && m.total > 0 ? { view: "expenses", expenses: { ...yBase, month: String(m.month) } } : null,
  }));
  const stats = `<div class="mini-stats">
      <div><span class="hint">Totale</span><b>${eur(total)}</b></div>
      <div><span class="hint">Media mensile</span><b>${eur(avg)}</b><span class="hint">${active.length} mes${active.length === 1 ? "e" : "i"} con spesa</span></div>
      <div><span class="hint">Mese di picco</span><b>${peak ? MONTHS_FULL[peak.month] : "—"}</b>${peak ? `<span class="hint">${eur(peak.total)}</span>` : ""}</div>
    </div>`;
  return chartCard(`Andamento mensile ${year}`, stats + columnChart(rows), {
    sub: "Spese e bollette mese per mese · clicca una colonna per i movimenti", style,
  });
}

/* ---------- View: Dashboard ---------- */
async function viewDashboard() {
  const c = $("#content");
  c.innerHTML = skeletonGrid();
  $("#topbar-actions").appendChild(await yearSelector(viewDashboard));
  const yq = State.year ? `?year=${State.year}` : "";
  // L'andamento mensile è per anno: senza anno selezionato usiamo quello corrente.
  const dashYear = State.year || new Date().getFullYear();
  try {
    const [ov, byCat, byMember, byScope, fiscal, yearly, monthly] = await Promise.all([
      api(`/stats/overview${yq}`), api(`/stats/by-category${yq}`), api(`/stats/by-member${yq}`),
      api(`/stats/by-scope${yq}`), api(`/stats/fiscal-summary${yq}`), api(`/stats/yearly`),
      api(`/stats/monthly?year=${dashYear}`),
    ]);
    refreshReviewBadge();

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
    // Le righe sono MACRO-categorie: «spesa supermercato» (con sottocategorie),
    // farmaci, personalizzate, più le bollette. Il drill su una macro-categoria
    // con sottocategorie filtra le spese per gruppo (tutti i reparti); su una
    // foglia di primo livello filtra per singola categoria.
    const catRows = byCat.slice(0, 8).map(r => {
      let drill = null;
      if (r.category === "Bollette / utenze") drill = { view: "bills" };
      else if (r.category === "Spese condominiali") drill = { view: "bills", bills: { utility_type: "condominio" } };
      else if (r.subcategories && r.subcategories.length) drill = { view: "expenses", expenses: { ...yBase, group: r.category } };
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

      ${monthlyCard(monthly, dashYear, { style: "margin-top:16px" })}

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

/* ---------- View: Analisi (analisi avanzate) ---------- */
function pctBadge(pct, { invert = false } = {}) {
  // invert=false: per la SPESA un aumento (pct>0) è "negativo" (rosso),
  // un calo è "positivo" (verde).
  if (pct === null || pct === undefined) return `<span class="hint">—</span>`;
  const up = pct > 0;
  const good = invert ? up : !up;
  const color = pct === 0 ? "var(--text-faint)" : good ? "#15803d" : "#dc2626";
  const arrow = pct === 0 ? "→" : up ? "▲" : "▼";
  return `<span style="color:${color};font-weight:700;white-space:nowrap">${arrow} ${Math.abs(pct).toFixed(1)}%</span>`;
}

function insightCard(i) {
  const bg = { positive: "var(--green-100)", warning: "var(--amber-100)", info: "var(--blue-100)" }[i.severity] || "var(--blue-100)";
  const fg = { positive: "#15803d", warning: "#b45309", info: "#1d4ed8" }[i.severity] || "#1d4ed8";
  return `<div class="card card-pad" style="display:flex;gap:12px;align-items:flex-start">
      <span class="ico-box" style="background:${bg};color:${fg};flex-shrink:0">${i.icon || "💡"}</span>
      <div><b>${esc(i.title)}</b><div class="sub" style="color:var(--text-soft);font-size:13px;margin-top:2px">${esc(i.detail || "")}</div></div>
    </div>`;
}

async function viewAnalisi() {
  const c = $("#content");
  c.innerHTML = skeletonGrid();
  $("#topbar-actions").appendChild(await yearSelector(viewAnalisi));
  // Le analisi mensili/confronto/insight sono per anno: se "Tutti gli anni" è
  // selezionato, usiamo l'anno corrente come riferimento.
  const year = State.year || new Date().getFullYear();
  const yq = `?year=${year}`;
  try {
    const [insights, monthly, top, cmp] = await Promise.all([
      api(`/stats/insights${yq}`),
      api(`/stats/monthly${yq}`),
      api(`/stats/top-merchants${yq}&limit=10`),
      api(`/stats/compare${yq}`),
    ]);

    const merchRows = top.map(m => ({ label: m.merchant, total: m.total }));
    const cmpRows = cmp.by_category.filter(r => r.current > 0 || r.previous > 0).slice(0, 12);

    const kpis = [
      { label: `Totale ${year}`, value: eur(cmp.current_total), icon: "💶", bg: "var(--teal-100)", fg: "var(--teal-800)", delta: `${cmp.by_category.length} categori${cmp.by_category.length === 1 ? "a" : "e"}` },
      { label: `Totale ${cmp.previous_year}`, value: eur(cmp.previous_total), icon: "🗓️", bg: "var(--blue-100)", fg: "#1d4ed8", delta: "anno precedente" },
      { label: "Variazione", value: cmp.delta_pct === null ? "—" : `${cmp.delta_pct > 0 ? "+" : ""}${cmp.delta_pct.toFixed(1)}%`, icon: cmp.delta >= 0 ? "📈" : "📉", bg: cmp.delta >= 0 ? "var(--amber-100)" : "var(--green-100)", fg: cmp.delta >= 0 ? "#b45309" : "#15803d", delta: `${cmp.delta >= 0 ? "+" : ""}${eur(cmp.delta)} sul ${cmp.previous_year}` },
      { label: "Osservazioni", value: insights.length, icon: "💡", bg: "var(--blue-100)", fg: "#1d4ed8", delta: "rilevate per il periodo" },
    ];

    const cmpTable = cmpRows.length ? `<div class="table-wrap"><table class="data">
        <thead><tr><th>Categoria</th><th class="num">${year}</th><th class="num">${cmp.previous_year}</th><th class="num">Var.</th></tr></thead>
        <tbody>${cmpRows.map(r => `<tr>
            <td>${esc(r.category)}</td>
            <td class="num">${eur(r.current)}</td>
            <td class="num" style="color:var(--text-soft)">${eur(r.previous)}</td>
            <td class="num">${pctBadge(r.delta_pct)}</td>
          </tr>`).join("")}</tbody>
      </table></div>` : `<div class="empty"><div class="big">📭</div><p>Nessun dato da confrontare.</p></div>`;

    c.innerHTML = `
      ${kpiGrid(kpis)}

      <div class="card card-pad" style="margin-top:16px">
        <div class="row between" style="margin-bottom:16px"><h3>Osservazioni automatiche</h3><span class="hint">Anno ${year}</span></div>
        <div class="grid cols-2" style="gap:12px">${insights.map(insightCard).join("")}</div>
      </div>

      ${monthlyCard(monthly, year, { style: "margin-top:16px" })}

      <div class="grid cols-2" style="margin-top:16px">
        ${chartCard("Dove spendi di più", barChart(merchRows, { labelKey: "label", valueKey: "total" }), { sub: "Esercenti/fornitori per importo totale" })}
        ${chartCard(`Confronto ${cmp.previous_year} → ${year}`, cmpTable, { action: `<span class="hint">Variazione per categoria</span>` })}
      </div>`;

    bindDrills(c);
  } catch (err) {
    c.innerHTML = errorBox(err.message);
  }
}

/* ---------- View: Esplora (analisi interattiva, cross-filtering BI) ----------
   Pagina in stile "business intelligence": carica una volta i movimenti di
   spesa dell'anno e ricava lato client tutti gli aggregati. Cliccando un
   elemento di QUALSIASI grafico (mese, categoria, pagante, ambito, classifica
   fiscale) si attiva un filtro a livello di pagina che ricalcola tutti gli
   altri grafici, i KPI e la tabella (cross-filtering). I filtri attivi
   compaiono come "slicer" rimovibili. Nessun ricaricamento dal server al
   variare dei filtri: l'interazione è immediata. */
let biData = [];          // dataset (movimenti) dell'anno corrente
let biYear = null;        // anno di riferimento del dataset caricato
let biFilters = {};       // { month, group, payer, scope, fiscal } → valore (stringa)

// Mappa foglia→macro-categoria (gruppo) costruita dalle categorie note: serve
// per aggregare i reparti del supermercato sotto la macro-categoria.
function biGroupMap() {
  const cats = (State.categories && State.categories.length) ? State.categories : BUILTIN_CATEGORIES;
  const m = {};
  for (const c of cats) m[c.name] = c.parent || c.name;
  return m;
}

// Dimensioni del cubo: ognuna sa estrarre la chiave da una riga e darne
// l'etichetta leggibile. La chiave è confrontata (come stringa) col filtro.
const BI_DIMS = {
  month: {
    label: "Mese",
    key: (r) => r.purchase_date ? (new Date(r.purchase_date).getMonth() + 1) : 0,
    text: (k) => (Number(k) ? MONTHS_FULL[Number(k)] : "Senza data"),
  },
  group: {
    label: "Categoria",
    key: (r, g) => r.merch_category ? (g[r.merch_category] || r.merch_category) : "n/d",
    text: (k) => (k === "n/d" ? "Senza categoria" : k),
  },
  payer: {
    label: "Pagante",
    key: (r) => r.payer_user_id || "",
    text: (k) => (k ? memberName(k) : "Non attribuito"),
  },
  scope: {
    label: "Ambito",
    key: (r) => r.scope || "",
    text: (k) => (SCOPE_LABELS[k] || k || "—"),
  },
  fiscal: {
    label: "Fiscale",
    key: (r) => r.fiscal_classification || "",
    text: (k) => (FISCAL_LABELS[k] || k || "—"),
  },
};

// Una riga supera i filtri attivi tranne quello sulla dimensione `except`
// (cross-filtering "escludi te stesso": il grafico cliccato continua a
// mostrare tutte le voci, evidenziando quella selezionata).
function biMatches(row, gmap, except) {
  for (const dim of Object.keys(biFilters)) {
    if (dim === except) continue;
    if (String(BI_DIMS[dim].key(row, gmap)) !== String(biFilters[dim])) return false;
  }
  return true;
}

// Aggrega per la dimensione `dim` le righe filtrate (escludendo il filtro su
// `dim`), restituendo righe {key,label,value,count} ordinate.
function biAggregate(dim, gmap) {
  const D = BI_DIMS[dim];
  const map = new Map();
  for (const r of biData) {
    if (!biMatches(r, gmap, dim)) continue;
    const k = String(D.key(r, gmap));
    let e = map.get(k);
    if (!e) { e = { key: k, label: D.text(k), value: 0, count: 0 }; map.set(k, e); }
    e.value += Number(r.line_amount || 0);
    e.count++;
  }
  const out = [...map.values()];
  if (dim === "month") out.sort((a, b) => Number(a.key) - Number(b.key));
  else out.sort((a, b) => b.value - a.value);
  return out;
}

function biToggle(dim, val) {
  if (String(biFilters[dim]) === String(val)) delete biFilters[dim];
  else biFilters[dim] = String(val);
  biRender();
}

// Porta i filtri attivi nella vista Spese (per modificare i movimenti).
function biOpenInExpenses() {
  const f = defaultExpFilters();
  f.fiscal_year = String(biYear);
  if (biFilters.month) f.month = String(biFilters.month);
  if (biFilters.group) f.group = biFilters.group;
  if (biFilters.payer) f.payer_user_id = biFilters.payer;
  if (biFilters.scope) f.scope = biFilters.scope;
  if (biFilters.fiscal) f.fiscal_classification = biFilters.fiscal;
  expFilters = f;
  navigate("expenses");
}

// Barre orizzontali selezionabili (toggle del filtro, non navigazione).
function biBars(dim, gmap, { limit = 0 } = {}) {
  let rows = biAggregate(dim, gmap);
  if (limit && rows.length > limit) rows = rows.slice(0, limit);
  if (!rows.length) return `<div class="empty"><div class="big">📭</div><p>Nessun dato.</p></div>`;
  const sel = biFilters[dim];
  const max = Math.max(...rows.map(r => r.value), 1);
  return rows.map((r, i) => {
    const isSel = sel !== undefined && String(sel) === r.key;
    const cls = sel === undefined ? "" : (isSel ? " sel" : " dim");
    return `<div class="bar-row bar-clickable bi-bar${cls}" data-bi-dim="${dim}" data-bi-val="${esc(r.key)}" role="button" tabindex="0" title="${esc(r.label)} · ${eur(r.value)}">
        <span class="lbl">${esc(r.label)}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2, (r.value / max) * 100)}%;background:${PALETTE[i % PALETTE.length]}"></div></div>
        <span class="amt">${eur(r.value)}</span>
      </div>`;
  }).join("");
}

// Ciambella selezionabile (per le dimensioni a poche voci: ambito/fiscale).
function biDonutChart(dim, gmap) {
  const rows = biAggregate(dim, gmap);
  const total = rows.reduce((s, r) => s + r.value, 0);
  if (!total) return `<div class="empty"><div class="big">📭</div><p>Nessun dato.</p></div>`;
  const sel = biFilters[dim];
  const R = 70, C = 2 * Math.PI * R; let off = 0;
  const segs = rows.map((r, i) => {
    const frac = r.value / total;
    const dash = `${frac * C} ${C - frac * C}`;
    const isSel = sel !== undefined && String(sel) === r.key;
    const cls = sel === undefined ? "" : (isSel ? " sel" : " dim");
    const seg = `<circle class="seg-clickable bi-seg${cls}" data-bi-dim="${dim}" data-bi-val="${esc(r.key)}" r="${R}" cx="90" cy="90" fill="none" stroke="${PALETTE[i % PALETTE.length]}" stroke-width="24" stroke-dasharray="${dash}" stroke-dashoffset="${-off * C}" transform="rotate(-90 90 90)"></circle>`;
    off += frac; return seg;
  }).join("");
  const legend = rows.map((r, i) => {
    const isSel = sel !== undefined && String(sel) === r.key;
    const cls = sel === undefined ? "" : (isSel ? " sel" : " dim");
    return `<span class="leg-clickable bi-leg${cls}" data-bi-dim="${dim}" data-bi-val="${esc(r.key)}" role="button" tabindex="0"><i class="dot" style="background:${PALETTE[i % PALETTE.length]}"></i>${esc(r.label)} · <b>${eur(r.value)}</b></span>`;
  }).join("");
  return `<div class="donut-wrap">
    <svg viewBox="0 0 180 180" width="180" height="180" style="flex-shrink:0">${segs}
      <text x="90" y="84" text-anchor="middle" font-size="13" fill="var(--text-faint)">Totale</text>
      <text x="90" y="104" text-anchor="middle" font-size="17" font-weight="800" fill="var(--text)">${eur(total)}</text>
    </svg>
    <div class="legend" style="flex-direction:column;gap:8px">${legend}</div></div>`;
}

// Colonne mensili selezionabili (gen→dic), con i mesi assenti mostrati a zero.
function biMonthChart(gmap) {
  const agg = biAggregate("month", gmap);
  const byKey = Object.fromEntries(agg.map(r => [r.key, r]));
  const sel = biFilters.month;
  const months = Array.from({ length: 12 }, (_, i) => byKey[String(i + 1)] || { key: String(i + 1), value: 0, count: 0 });
  const max = Math.max(...months.map(m => m.value), 1);
  const cols = months.map((m, i) => {
    const h = Math.max(0, (m.value / max) * 100);
    const isSel = sel !== undefined && String(sel) === m.key;
    const cls = sel === undefined ? "" : (isSel ? " sel" : " dim");
    return `<div class="col-item col-clickable bi-col${cls}" data-bi-dim="month" data-bi-val="${m.key}" role="button" tabindex="0" title="${MONTHS_FULL[i + 1]}: ${eur(m.value)}">
        <div class="col-bars">
          <div class="col-amt">${eurShort(m.value)}</div>
          <div class="col-stack"><div class="col-seg" style="height:${h}%;background:${COL_EXP_COLOR}"></div></div>
        </div>
        <div class="col-lbl">${MONTHS_FULL[i + 1].slice(0, 3)}</div>
      </div>`;
  }).join("");
  return `<div class="col-chart">${cols}</div>`;
}

// Barra degli slicer: filtri attivi come chip rimovibili + azzera tutto.
function biSlicers() {
  const keys = Object.keys(biFilters);
  if (!keys.length) {
    return `<div class="slicers"><span class="hint">💡 Clicca su una barra, una colonna o uno spicchio per filtrare tutta la pagina. I filtri si combinano.</span></div>`;
  }
  const chips = keys.map(dim => {
    const D = BI_DIMS[dim];
    return `<span class="slicer-chip"><span class="dim-lbl">${esc(D.label)}</span>${esc(D.text(biFilters[dim]))}<span class="x" data-bi-remove="${dim}" role="button" tabindex="0" title="Rimuovi filtro">✕</span></span>`;
  }).join("");
  return `<div class="slicers">${chips}
      <button class="btn btn-ghost btn-sm" data-bi-clear>Azzera filtri</button>
      <button class="btn btn-ghost btn-sm" data-bi-open>Apri nelle Spese ↗</button>
    </div>`;
}

function biBindClicks(root) {
  root.querySelectorAll("[data-bi-dim][data-bi-val]").forEach(el => {
    const fire = () => biToggle(el.dataset.biDim, el.dataset.biVal);
    el.addEventListener("click", fire);
    el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fire(); } });
  });
  root.querySelectorAll("[data-bi-remove]").forEach(el => {
    const fire = () => { delete biFilters[el.dataset.biRemove]; biRender(); };
    el.addEventListener("click", fire);
    el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fire(); } });
  });
  root.querySelector("[data-bi-clear]")?.addEventListener("click", () => { biFilters = {}; biRender(); });
  root.querySelector("[data-bi-open]")?.addEventListener("click", biOpenInExpenses);
}

// Ricalcola e ridisegna l'intera pagina dai dati in cache (nessun fetch).
function biRender() {
  const c = $("#content");
  if (!c) return;
  const gmap = biGroupMap();
  // Righe che passano TUTTI i filtri attivi: alimentano KPI e tabella.
  const filtered = biData.filter(r => biMatches(r, gmap, null));
  const total = filtered.reduce((s, r) => s + Number(r.line_amount || 0), 0);
  const cats = new Set(filtered.map(r => BI_DIMS.group.key(r, gmap))).size;
  const avg = filtered.length ? total / filtered.length : 0;
  const nFilters = Object.keys(biFilters).length;

  const kpis = [
    { label: nFilters ? "Spesa filtrata" : `Spesa ${biYear}`, value: eur(total), icon: "💶", bg: "var(--teal-100)", fg: "var(--teal-800)", delta: nFilters ? `${nFilters} filtr${nFilters === 1 ? "o" : "i"} attiv${nFilters === 1 ? "o" : "i"}` : "tutte le spese dell'anno" },
    { label: "Movimenti", value: filtered.length, icon: "🧾", bg: "var(--blue-100)", fg: "#1d4ed8", delta: `${biData.length} in totale nell'anno` },
    { label: "Categorie", value: cats, icon: "🗂️", bg: "var(--amber-100)", fg: "#b45309", delta: "categorie distinte nel filtro" },
    { label: "Media a movimento", value: eur(avg), icon: "📐", bg: "var(--green-100)", fg: "#15803d", delta: "importo medio per riga" },
  ];

  // Tabella dei movimenti filtrati (sola lettura: per modificarli c'è "Spese").
  const rows = filtered.slice().sort((a, b) => (b.purchase_date || "").localeCompare(a.purchase_date || ""));
  const tableRows = rows.slice(0, 200);
  const table = filtered.length ? `<div class="table-wrap"><table class="data">
      <thead><tr><th>Data</th><th>Descrizione</th><th>Categoria</th><th>Pagante</th><th class="num">Importo</th></tr></thead>
      <tbody>${tableRows.map(r => `<tr>
          <td class="mono">${fmtDate(r.purchase_date)}</td>
          <td><b>${esc(r.description_normalized || r.description_original || "—")}</b>${r.merchant ? `<div class="hint">${esc(r.merchant)}</div>` : ""}</td>
          <td>${esc(r.merch_category || "—")}</td>
          <td>${esc(r.payer_user_id ? memberName(r.payer_user_id) : "Non attribuito")}</td>
          <td class="num">${eur(r.line_amount)}</td>
        </tr>`).join("")}</tbody>
    </table></div>${rows.length > tableRows.length ? `<p class="hint" style="margin-top:10px">Mostrati i primi ${tableRows.length} di ${rows.length} movimenti. Restringi i filtri o apri la vista Spese.</p>` : ""}`
    : `<div class="empty"><div class="big">📭</div><p>Nessun movimento per i filtri selezionati.</p></div>`;

  c.innerHTML = `
    ${biSlicers()}
    ${kpiGrid(kpis)}
    ${chartCard("Andamento mensile", biMonthChart(gmap), { sub: "Spesa per mese · clicca una colonna per filtrare", style: "margin-top:16px" })}
    <div class="grid cols-2" style="margin-top:16px">
      ${chartCard("Spesa per categoria", biBars("group", gmap, { limit: 12 }), { sub: "Clicca una barra per filtrare la pagina" })}
      ${chartCard("Spesa per pagante", biBars("payer", gmap), { sub: "Clicca un pagante per filtrare la pagina" })}
    </div>
    <div class="grid cols-2" style="margin-top:16px">
      ${chartCard("Personale vs familiare", biDonutChart("scope", gmap))}
      ${chartCard("Classificazione fiscale", biDonutChart("fiscal", gmap))}
    </div>
    ${chartCard(`Movimenti ${nFilters ? "filtrati" : biYear}`, table, { action: `<b>${eur(total)}</b>`, style: "margin-top:16px" })}`;

  biBindClicks(c);
}

async function viewEsplora() {
  const c = $("#content");
  c.innerHTML = skeletonGrid();
  // Il selettore anno richiama viewEsplora() direttamente (non via navigate):
  // svuota la topbar per non accumulare selettori duplicati al cambio anno.
  $("#topbar-actions").innerHTML = "";
  $("#topbar-actions").appendChild(await yearSelector(viewEsplora));
  // L'esplorazione è per anno: senza anno selezionato usiamo quello corrente.
  biYear = State.year || new Date().getFullYear();
  try {
    biData = await api(`/expenses?fiscal_year=${biYear}`);
    if (!biData.length) {
      c.innerHTML = emptyBox("🧭", "Nessuna spesa da esplorare", `Non ci sono movimenti per il ${biYear}. Carica documenti o registra spese, poi torna qui per l'analisi interattiva.`, "Carica documento", "upload");
      bindEmpty(c);
      return;
    }
    biRender();
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
        <div class="row" style="margin-bottom:16px">${badge(doc.status, STATUS_LABELS)}<span class="hint" style="margin-left:auto">✏️ I campi sono modificabili: le correzioni si salvano da sole.</span></div>
        ${doc.reliability_note ? `<p class="hint" style="margin-bottom:14px">⚠️ ${esc(doc.reliability_note)}</p>` : ""}
        <div class="card card-pad" style="background:var(--surface-2);margin-bottom:16px"><b>Sintesi</b><textarea class="input" data-doc-field="summary" rows="3" style="margin-top:6px;width:100%" placeholder="Sintesi del documento…">${esc(doc.summary || "")}</textarea></div>
        <dl class="kv kv-edit" style="margin-bottom:18px">
          <dt>Tipo</dt><dd><select class="select" data-doc-field="doc_type" style="width:100%">${optList(DOCTYPE_LABELS, doc.doc_type)}</select></dd>
          <dt>Emittente</dt><dd><input class="input" data-doc-field="issuer" value="${esc(doc.issuer || "")}" placeholder="—"></dd>
          <dt>Importo totale</dt><dd><input class="input" type="number" step="0.01" data-doc-field="total_amount" data-type="number" value="${doc.total_amount ?? ""}" placeholder="0,00"></dd>
          <dt>Data documento</dt><dd><input class="input" type="date" data-doc-field="doc_date" value="${doc.doc_date || ""}"></dd>
          <dt>Anno fiscale</dt><dd><input class="input" type="number" data-doc-field="fiscal_year" data-type="number" value="${doc.fiscal_year ?? ""}" placeholder="—"></dd>
          <dt>Pagamento</dt><dd><input class="input" data-doc-field="payment_method" value="${esc(doc.payment_method || "")}" placeholder="—"></dd>
          ${State.paymentMethods.length ? `<dt>Metodo</dt><dd><select class="select" data-doc-field="payment_method_id" style="width:100%">${optList({ "": "—", ...Object.fromEntries(State.paymentMethods.filter(pm => pm.active || pm.id === doc.payment_method_id).map(pm => [pm.id, `${pm.label}${pm.last4 ? " ••" + pm.last4 : ""} (${memberName(pm.user_id)})`])) }, doc.payment_method_id || "")}</select></dd>` : ""}
          <dt>N. documento</dt><dd><input class="input" data-doc-field="document_number" value="${esc(doc.document_number || "")}" placeholder="—"></dd>
          <dt>Classificazione</dt><dd><select class="select" data-doc-field="fiscal_classification" style="width:100%">${optList(FISCAL_LABELS, doc.fiscal_classification)}</select></dd>
          <dt>Ambito</dt><dd><select class="select" data-doc-field="scope" style="width:100%">${optList(SCOPE_LABELS, doc.scope)}</select></dd>
          <dt>Pagante</dt><dd><select class="select" data-doc-field="payer_user_id" style="width:100%">${optList({ "": "—", ...Object.fromEntries(State.members.map(m => [m.id, m.full_name])) }, doc.payer_user_id || "")}</select></dd>
          <dt>Beneficiario</dt><dd><select class="select" data-doc-field="beneficiary_user_id" style="width:100%">${optList({ "": "—", ...Object.fromEntries(State.members.map(m => [m.id, m.full_name])) }, doc.beneficiary_user_id || "")}</select></dd>
          <dt>Conservazione</dt><dd><input class="input" data-doc-field="retention_note" value="${esc(doc.retention_note || "")}" placeholder="—"></dd>
        </dl>
        ${lines.length ? `<h4 style="margin-bottom:8px">Righe e ripartizione (${lines.length})</h4>
          <div class="card table-wrap" style="margin-bottom:18px"><table class="data"><thead><tr><th>Descrizione</th><th>Categoria</th><th>Pagante</th><th>Beneficiario</th><th class="num">Importo</th></tr></thead>
          <tbody>${lines.map(l => `<tr data-line="${l.id}">
            <td><input class="input" data-exp-field="description_normalized" value="${esc(l.description_normalized || l.description_original || "")}" style="min-width:150px"></td>
            <td><select class="inline-select" data-exp-field="merch_category">${categoryOptionsHtml(l.merch_category || "")}</select></td>
            <td><select class="inline-select" data-exp-field="payer_user_id">${optList({ "": "—", ...Object.fromEntries(State.members.map(m => [m.id, m.full_name])) }, l.payer_user_id || "")}</select></td>
            <td><select class="inline-select" data-exp-field="beneficiary_user_id">${optList({ "": "—", ...Object.fromEntries(State.members.map(m => [m.id, m.full_name])) }, l.beneficiary_user_id || "")}</select></td>
            <td class="num"><input class="input" type="number" step="0.01" data-exp-field="line_amount" data-type="number" value="${l.line_amount ?? ""}" style="width:100px;text-align:right"></td>
          </tr>`).join("")}</tbody></table></div>` : ""}
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
    // Modifica manuale dei campi del documento (diciture/attribuzioni): ogni
    // campo si salva al blur/change. Aggiorniamo anche la lista sottostante così
    // emittente/importo/pagante restano allineati alla chiusura del drawer.
    const parseVal = (el) => {
      let val = el.value;
      if (el.dataset.type === "number") return val === "" ? null : Number(val);
      return val === "" ? null : val;
    };
    body.querySelectorAll("[data-doc-field]").forEach(el => {
      el.addEventListener("change", async () => {
        const field = el.dataset.docField;
        const val = parseVal(el);
        if (el.dataset.type === "number" && val !== null && Number.isNaN(val)) { toast("Valore non valido", { type: "err" }); return; }
        try {
          await api(`/documents/${id}`, { method: "PATCH", body: { [field]: val } });
          toast("Aggiornato", { type: "ok", timeout: 1500 });
          loadDocuments();
        } catch (e) { toast("Errore", { desc: e.message, type: "err" }); }
      });
    });
    // Modifica delle righe e della ripartizione (descrizione, categoria,
    // pagante/beneficiario, importo): salvataggio automatico per riga.
    body.querySelectorAll("tr[data-line]").forEach(tr => {
      const lid = tr.dataset.line;
      tr.querySelectorAll("[data-exp-field]").forEach(el => {
        el.addEventListener("change", async () => {
          const field = el.dataset.expField;
          const val = parseVal(el);
          if (field === "line_amount" && (val === null || Number.isNaN(val))) { toast("Importo obbligatorio", { type: "err" }); return; }
          try {
            await api(`/expenses/${lid}`, { method: "PATCH", body: { [field]: val } });
            toast("Aggiornato", { type: "ok", timeout: 1500 });
          } catch (e) { toast("Errore", { desc: e.message, type: "err" }); }
        });
      });
    });
    body.querySelector("[data-close]").addEventListener("click", closeModal);
    body.querySelector("[data-reprocess]").addEventListener("click", async () => {
      const instruction = await promptDialog(
        "Rielabora documento",
        "Aggiungi indicazioni per l'assistente (facoltativo). Le righe già estratte verranno rifatte da capo.",
        { placeholder: "Es. È una bolletta del gas della seconda casa; attribuisci tutto a Mario e ignora la riga del sacchetto.", okText: "Rielabora" }
      );
      if (instruction === null) return;  // annullato
      try {
        await api(`/documents/${id}/reprocess`, { method: "POST", body: { instruction: instruction.trim() || null } });
        toast("Rielaborazione avviata", { type: "warn" });
        closeModal(); loadDocuments();
      } catch (e) { toast("Errore", { desc: e.message, type: "err" }); }
    });
    body.querySelector("[data-delete]").addEventListener("click", async () => {
      if (!(await confirmDialog("Eliminare il documento?", "Verranno rimossi anche le righe collegate e il file originale. L'operazione non è reversibile."))) return;
      try { await api(`/documents/${id}`, { method: "DELETE" }); toast("Documento eliminato", { type: "ok" }); closeModal(); loadDocuments(); }
      catch (e) { toast("Errore", { desc: e.message, type: "err" }); }
    });
  } catch (err) { toast("Errore", { desc: err.message, type: "err" }); closeModal(); }
}

/* ---------- View: Revisione (agente di orchestrazione) ---------- */
const REVIEW_KIND_META = {
  reconciliation:        { icon: "⚖️", label: "Righe ↔ totale", proposal: false },
  missing_lines:         { icon: "🧮", label: "Righe mancanti", proposal: false },
  skipped_line:          { icon: "❓", label: "Riga non calcolata", proposal: false },
  missing_classification:{ icon: "🏷️", label: "Classificazione", proposal: false },
  missing_attribution:   { icon: "👤", label: "Attribuzione", proposal: false },
  possible_duplicate:    { icon: "📑", label: "Possibile duplicato", proposal: false },
  processing_failed:     { icon: "🚫", label: "Elaborazione fallita", proposal: false },
  reliability:           { icon: "🔎", label: "Da verificare", proposal: false },
  category_proposal:     { icon: "🗂️", label: "Proposta categoria", proposal: true },
  reclassification:      { icon: "🔁", label: "Riclassificazione", proposal: true },
  attribution:          { icon: "🧑", label: "Attribuzione", proposal: true },
  insight:               { icon: "💡", label: "Osservazione", proposal: false },
};
const SEV_META = {
  critical: { color: "#b91c1c", bg: "var(--red-100, #fee2e2)", label: "Critico" },
  warning:  { color: "#b45309", bg: "var(--amber-100)", label: "Avviso" },
  info:     { color: "#1d4ed8", bg: "var(--blue-100)", label: "Info" },
};
let reviewStatusTab = "pending";

async function viewRevisione() {
  const c = $("#content");
  c.innerHTML = skeletonRows();
  // I cambi di tab richiamano viewRevisione() direttamente (non via navigate):
  // svuota la topbar per non accumulare pulsanti "Verifica ora" duplicati.
  $("#topbar-actions").innerHTML = "";
  // Pulsante "Verifica ora" nella topbar.
  const runBtn = document.createElement("button");
  runBtn.className = "btn btn-primary";
  runBtn.innerHTML = "🔍 Verifica ora";
  runBtn.addEventListener("click", () => runReview(runBtn));
  $("#topbar-actions").appendChild(runBtn);

  try {
    const [summary, items] = await Promise.all([
      api("/review/summary"),
      api(`/review?status_filter=${reviewStatusTab}`),
    ]);
    updateReviewBadge(summary.pending || 0);

    const intro = `<div class="card card-pad" style="border-left:4px solid var(--teal-600,#0d9488);margin-bottom:16px">
        <div class="row" style="gap:12px;align-items:flex-start">
          <span style="font-size:22px">🤖</span>
          <div><b>Agente di revisione</b>
            <div class="sub" style="color:var(--text-soft);font-size:13px">Controlla automaticamente che le righe quadrino con i totali, segnala ciò che non è stato calcolato o gestito correttamente e propone categorie/riclassificazioni migliori, applicate solo col tuo consenso. Gira dopo ogni caricamento; puoi anche avviarlo a mano.</div>
          </div>
        </div>
        <div class="row" style="gap:8px;flex-wrap:wrap;margin-top:12px">
          ${reviewChip("🚫", summary.critical, "critici", "#b91c1c")}
          ${reviewChip("⚠️", summary.warning, "avvisi", "#b45309")}
          ${reviewChip("ℹ️", summary.info, "info", "#1d4ed8")}
          ${reviewChip("💡", summary.proposals, "proposte", "#0d9488")}
        </div>
      </div>`;

    const tabs = `<div class="filters" style="margin-bottom:12px">
        ${["pending", "applied", "dismissed"].map(s => `
          <button class="btn ${reviewStatusTab === s ? "btn-primary" : ""}" data-tab="${s}">
            ${ {pending:"Da gestire", applied:"Applicate", dismissed:"Archiviate"}[s] }
          </button>`).join("")}
      </div>`;

    let body;
    if (!items.length) {
      body = reviewStatusTab === "pending"
        ? `<div class="card card-pad empty"><div class="big">✅</div><h3>Tutto in ordine</h3><p>Nessun avviso o proposta in sospeso. L'agente segnalerà qui eventuali righe non calcolate, totali che non quadrano o miglioramenti possibili.</p><button class="btn btn-primary" id="rev-run-empty" style="margin-top:14px">🔍 Verifica ora</button></div>`
        : `<div class="card card-pad empty"><div class="big">📭</div><h3>Nessuna voce</h3><p>Non ci sono voci in questo stato.</p></div>`;
    } else {
      body = `<div class="review-list" style="display:flex;flex-direction:column;gap:10px">
        ${items.map(reviewCard).join("")}</div>`;
    }

    c.innerHTML = intro + tabs + body;

    c.querySelectorAll("[data-tab]").forEach(b => b.addEventListener("click", () => {
      reviewStatusTab = b.dataset.tab; viewRevisione();
    }));
    $("#rev-run-empty")?.addEventListener("click", () => runReview($("#rev-run-empty")));
    bindReviewActions(c);
  } catch (err) {
    c.innerHTML = errorBox(err.message);
  }
}

function reviewChip(icon, n, label, color) {
  if (!n) return "";
  return `<span class="badge" style="background:${color}1a;color:${color};border:1px solid ${color}33">${icon} ${n} ${label}</span>`;
}

function reviewCard(it) {
  const meta = REVIEW_KIND_META[it.kind] || { icon: "•", label: it.kind, proposal: false };
  const sev = SEV_META[it.severity] || SEV_META.info;
  const isProposal = meta.proposal;
  const open = it.status === "pending";
  // Link al documento/spesa di riferimento.
  let goBtn = "";
  if (it.target_type === "document" && it.target_id) {
    goBtn = `<button class="btn" data-rev-open="document" data-rev-target="${it.target_id}">Apri documento</button>`;
  } else if (it.target_type === "expense" && it.target_id) {
    goBtn = `<button class="btn" data-rev-open="expense" data-rev-target="${it.target_id}">Vai alle spese</button>`;
  }
  let actions = "";
  if (open) {
    if (isProposal) {
      actions = `
        <button class="btn btn-primary" data-rev-act="approve" data-rev-id="${it.id}">✓ Approva e applica</button>
        <button class="btn" data-rev-act="reject" data-rev-id="${it.id}">Rifiuta</button>`;
    } else {
      actions = `
        ${goBtn}
        <button class="btn btn-primary" data-rev-act="approve" data-rev-id="${it.id}">Segna come gestito</button>
        <button class="btn" data-rev-act="dismiss" data-rev-id="${it.id}">Archivia</button>`;
    }
  } else {
    actions = `${goBtn}<span class="hint">${it.resolution_note ? esc(it.resolution_note) : (it.status === "rejected" ? "Rifiutata" : it.status === "dismissed" ? "Archiviata" : "Applicata")}</span>`;
  }
  return `<div class="card card-pad" style="border-left:4px solid ${sev.color}">
      <div class="row between" style="align-items:flex-start;gap:12px">
        <div style="flex:1">
          <div class="row" style="gap:8px;align-items:center;flex-wrap:wrap">
            <span style="font-size:18px">${meta.icon}</span>
            <b>${esc(it.title)}</b>
            <span class="badge" style="background:${sev.bg};color:${sev.color}">${meta.label}</span>
            ${isProposal ? `<span class="badge" style="background:#0d948815;color:#0d9488">richiede consenso</span>` : ""}
            ${it.fiscal_year ? `<span class="hint">${it.fiscal_year}</span>` : ""}
          </div>
          ${it.detail ? `<div class="sub" style="color:var(--text-soft);font-size:13px;margin-top:6px;white-space:pre-wrap">${esc(it.detail)}</div>` : ""}
        </div>
      </div>
      <div class="row" style="gap:8px;margin-top:12px;flex-wrap:wrap">${actions}</div>
    </div>`;
}

function bindReviewActions(wrap) {
  wrap.querySelectorAll("[data-rev-act]").forEach(b => b.addEventListener("click", async () => {
    const id = b.dataset.revId, act = b.dataset.revAct;
    b.disabled = true;
    try {
      await api(`/review/${id}/${act}`, { method: "POST" });
      const msg = { approve: "Applicato", reject: "Proposta rifiutata", dismiss: "Avviso archiviato" }[act];
      toast(msg, { type: "ok", timeout: 1800 });
      refreshReviewBadge();
      viewRevisione();
    } catch (err) {
      b.disabled = false;
      toast("Errore", { desc: err.message, type: "err" });
    }
  }));
  wrap.querySelectorAll("[data-rev-open]").forEach(b => b.addEventListener("click", () => {
    const type = b.dataset.revOpen;
    if (type === "document") { openDocument(b.dataset.revTarget); }
    else { navigate("expenses"); }
  }));
}

async function runReview(btn) {
  if (btn) { btn.disabled = true; btn.innerHTML = "⏳ Analisi in corso…"; }
  try {
    const res = await api("/review/run", { method: "POST" });
    const found = (res.checks_findings || 0) + (res.proposals || 0);
    toast("Revisione completata", {
      desc: found ? `${res.pending_total} voci da gestire` : "Nessun nuovo problema rilevato",
      type: "ok",
    });
    reviewStatusTab = "pending";
    refreshReviewBadge();
    viewRevisione();
  } catch (err) {
    toast("Errore", { desc: err.message, type: "err" });
    if (btn) { btn.disabled = false; btn.innerHTML = "🔍 Verifica ora"; }
  }
}

/* ---------- View: Expenses ---------- */
const defaultExpFilters = () => ({ fiscal_year: "", month: "", category: "", group: "", scope: "", fiscal_classification: "", payer_user_id: "", q: "" });
const MONTH_OPTS = { "": "Tutti i mesi", ...Object.fromEntries(Array.from({ length: 12 }, (_, i) => [String(i + 1), MONTHS_FULL[i + 1]])) };
let expFilters = defaultExpFilters();
async function viewExpenses() {
  const c = $("#content");
  const memberOpts = Object.fromEntries(State.members.map(m => [m.id, m.full_name]));
  c.innerHTML = `
    <div class="filters">
      <div class="search-box"><span class="s-ico">🔍</span><input class="input" id="exp-q" placeholder="Cerca descrizione, negozio…" value="${esc(expFilters.q)}"></div>
      <select class="select" id="ef-cat">${categoryOptionsHtml(expFilters.category, "Tutte le categorie")}</select>
      <select class="select" id="ef-fiscal">${optList({ "": "Tutte le classifiche", ...FISCAL_LABELS }, expFilters.fiscal_classification)}</select>
      <select class="select" id="ef-scope">${optList({ "": "Tutti gli ambiti", ...SCOPE_LABELS }, expFilters.scope)}</select>
      <select class="select" id="ef-payer">${optList({ "": "Tutti i paganti", ...memberOpts }, expFilters.payer_user_id)}</select>
      <input class="input" id="ef-year" type="number" placeholder="Anno" style="width:110px" value="${esc(expFilters.fiscal_year)}">
      <select class="select" id="ef-month">${optList(MONTH_OPTS, expFilters.month)}</select>
      <button class="btn btn-ghost btn-sm" id="exp-reset">Azzera</button>
    </div>
    <div id="exp-list">${skeletonRows()}</div>`;
  const reload = debounce(loadExpenses, 250);
  $("#exp-q").addEventListener("input", (e) => { expFilters.q = e.target.value; reload(); });
  $("#ef-cat").addEventListener("change", (e) => { expFilters.category = e.target.value; expFilters.group = ""; loadExpenses(); });
  $("#ef-fiscal").addEventListener("change", (e) => { expFilters.fiscal_classification = e.target.value; loadExpenses(); });
  $("#ef-scope").addEventListener("change", (e) => { expFilters.scope = e.target.value; loadExpenses(); });
  $("#ef-payer").addEventListener("change", (e) => { expFilters.payer_user_id = e.target.value; loadExpenses(); });
  $("#ef-year").addEventListener("input", (e) => { expFilters.fiscal_year = e.target.value; reload(); });
  $("#ef-month").addEventListener("change", (e) => { expFilters.month = e.target.value; loadExpenses(); });
  $("#exp-reset").addEventListener("click", () => { expFilters = defaultExpFilters(); viewExpenses(); });
  loadExpenses();
}

async function loadExpenses() {
  const wrap = $("#exp-list"); if (!wrap) return;
  const p = new URLSearchParams();
  if (expFilters.fiscal_year) p.set("fiscal_year", expFilters.fiscal_year);
  if (expFilters.month) p.set("month", expFilters.month);
  if (expFilters.category) p.set("category", expFilters.category);
  if (expFilters.group) p.set("group", expFilters.group);
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
            <td><select class="inline-select" data-field="merch_category">${categoryOptionsHtml(r.merch_category || "")}</select></td>
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

/* ---------- View: Farmaci (riservata admin) ----------
   Catalogo dei medicinali acquistati: categoria "farmaci". Mostra i dati del
   farmaco riconosciuti dallo scontrino parlante e arricchiti dalla ricerca
   online del codice AIC/minsan (salvati in details dall'assistente). */
const dget = (d, keys) => { if (!d || typeof d !== "object") return ""; for (const k of keys) { if (d[k] != null && d[k] !== "") return String(d[k]); } return ""; };

async function viewFarmaci() {
  if (State.user?.role !== "admin") { navigate("dashboard"); return; }
  const c = $("#content");
  c.innerHTML = skeletonRows();
  $("#topbar-actions").appendChild(await yearSelector(viewFarmaci));
  const privacy = `<div class="card card-pad" style="border-left:4px solid var(--teal-600, #0d9488);display:flex;gap:12px;align-items:center;margin-bottom:16px">
      <span style="font-size:22px">🔒</span>
      <div><b>Sezione riservata</b><div class="sub" style="color:var(--text-soft);font-size:13px">I farmaci sono dati sanitari sensibili: visibili solo agli amministratori del nucleo. Il codice AIC/minsan dello scontrino parlante viene cercato online dall'assistente per identificare il medicinale.</div></div>
    </div>`;
  try {
    const rows = await api(`/expenses/farmaci${State.year ? `?fiscal_year=${State.year}` : ""}`);
    if (!rows.length) {
      c.innerHTML = privacy + emptyBox("💊", "Nessun farmaco registrato", "Carica lo scontrino della farmacia (scontrino parlante) o registra la spesa: l'assistente riconosce i medicinali, ne cerca il codice online e li classifica come “farmaci”.", "Carica documento", "upload");
      bindEmpty(c); return;
    }
    const total = rows.reduce((s, r) => s + Number(r.line_amount || 0), 0);
    c.innerHTML = privacy + `
      <div class="row between" style="margin-bottom:12px"><span class="hint">${rows.length} acquist${rows.length === 1 ? "o" : "i"} di medicinali</span><b>Totale: ${eur(total)}</b></div>
      <div class="card table-wrap"><table class="data">
        <thead><tr><th>Data</th><th>Farmaco</th><th>Principio attivo</th><th>Codice (AIC/MINSAN)</th><th>Beneficiario</th><th>Fiscale</th><th class="num">Importo</th></tr></thead>
        <tbody>${rows.map(r => {
          const d = r.details || {};
          const farmaco = dget(d, ["farmaco", "nome_commerciale", "nome"]) || r.description_normalized || r.description_original || "—";
          // Principio attivo e codice ATC: mostrali entrambi se disponibili
          // (es. "Ibuprofene (M01AE01)"), altrimenti quello presente.
          const activeIngredient = dget(d, ["principio_attivo"]);
          const atc = dget(d, ["atc"]);
          const pa = activeIngredient && atc ? `${activeIngredient} (${atc})` : (activeIngredient || atc);
          const code = dget(d, ["codice_aic", "aic"]) || dget(d, ["minsan", "codice_ministeriale"]);
          return `<tr>
            <td class="mono">${fmtDate(r.purchase_date)}</td>
            <td><b>${esc(farmaco)}</b>${r.merchant ? `<div class="hint">${esc(r.merchant)}</div>` : ""}</td>
            <td>${esc(pa || "—")}</td>
            <td class="mono">${esc(code || "—")}</td>
            <td>${esc(memberName(r.beneficiary_user_id))}</td>
            <td>${badge(r.fiscal_classification, FISCAL_LABELS)}</td>
            <td class="num">${eur(r.line_amount)}</td>
          </tr>`;
        }).join("")}</tbody></table></div>`;
  } catch (err) { c.innerHTML = privacy + errorBox(err.message); }
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
      ${State.paymentMethods.length ? `<div class="field"><label>Metodo di pagamento</label><select class="select" name="payment_method_id">${optList({ "": "—", ...Object.fromEntries(State.paymentMethods.filter(pm => pm.active || pm.id === b.payment_method_id).map(pm => [pm.id, `${pm.label}${pm.last4 ? " ••" + pm.last4 : ""} (${memberName(pm.user_id)})`])) }, b.payment_method_id || "")}</select></div>` : ""}
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
    const [hh, members, units, categories, methods] = await Promise.all([
      api("/household"), api("/household/members"), api("/household/units").catch(() => []),
      api("/household/categories").catch(() => []),
      api("/household/payment-methods").catch(() => []),
    ]);
    State.members = members; indexMembers();
    State.units = units || [];
    State.paymentMethods = methods || []; indexPaymentMethods();
    State.categories = categories || [];
    const customCats = (categories || []).filter(c => !c.builtin);
    const builtinCats = (categories || []).filter(c => c.builtin);
    const builtinGroups = [...new Set(builtinCats.map(c => c.parent).filter(Boolean))];
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
            <td><div class="row" style="gap:9px"><span class="avatar" style="width:28px;height:28px;font-size:11px">${initials(m.full_name)}</span><div><b>${esc(m.full_name)}</b><div class="hint">${m.email ? esc(m.email) : "senza accesso"}</div></div></div></td>
            <td>${m.role === "admin" ? `<span class="badge b-familiare">Admin</span>` : (m.email ? `<span class="badge b-non_rilevante">Membro</span>` : `<span class="badge b-non_rilevante">Soggetto</span>`)}</td>
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
        <div class="row between" style="margin-bottom:6px">
          <h3>💳 Metodi di pagamento</h3>
          <button class="btn btn-primary btn-sm" id="add-payment">+ Aggiungi metodo</button>
        </div>
        <p class="hint" style="margin-bottom:14px">Censisci le carte, i bancomat e gli altri strumenti con cui i membri del nucleo pagano (carta di credito/debito, prepagata, contanti, bonifico, addebito diretto/RID, PayPal). Ogni metodo è <b>intestato a un membro</b>: collegandolo a spese e bollette ricostruisci con quale strumento (e da chi) è stata pagata una spesa. ${isAdmin ? "Come amministratore puoi gestire i metodi di tutti i membri." : "Puoi gestire i tuoi metodi di pagamento."}</p>
        ${methods.length ? `<div class="table-wrap"><table class="data">
          <thead><tr><th>Metodo</th><th>Tipo</th><th>Intestatario</th><th>Ultime 4</th><th></th></tr></thead>
          <tbody>${methods.map(pm => `<tr>
            <td><b>${PAYMENT_TYPE_ICONS[pm.method_type] || "💼"} ${esc(pm.label)}</b>${pm.is_default ? ` <span class="badge b-familiare">predefinito</span>` : ""}${pm.active ? "" : ` <span class="badge b-non_rilevante">disattivo</span>`}${pm.provider ? `<div class="hint">${esc(pm.provider)}</div>` : ""}</td>
            <td>${esc(PAYMENT_TYPE_LABELS[pm.method_type] || pm.method_type)}</td>
            <td>${esc(memberName(pm.user_id))}</td>
            <td class="mono">${pm.last4 ? "••" + esc(pm.last4) : "—"}</td>
            ${(isAdmin || pm.user_id === State.user.id) ? `<td class="num row" style="gap:4px;justify-content:flex-end"><button class="btn-icon" data-edit-pay="${pm.id}" title="Modifica">✏️</button><button class="btn-icon" data-del-pay="${pm.id}" title="Elimina">🗑️</button></td>` : "<td></td>"}
          </tr>`).join("")}</tbody></table></div>` : `<div class="empty" style="padding:18px"><p class="hint">Nessun metodo di pagamento configurato. Aggiungi le carte/bancomat del nucleo per tracciare con cosa vengono pagate le spese.</p></div>`}
      </div>

      <div class="card card-pad" style="margin-top:16px">
        <div class="row between" style="margin-bottom:6px">
          <h3>🏷️ Categorie merceologiche</h3>
          <button class="btn btn-primary btn-sm" id="add-category">+ Aggiungi categoria</button>
        </div>
        <p class="hint" style="margin-bottom:14px">Le categorie sono organizzate in <b>due livelli</b>: la spesa al supermercato è la macro-categoria «spesa supermercato» suddivisa per reparto, le altre (es. farmaci) sono di primo livello. L'assistente può <b>creare nuove categorie</b> quando nessuna è adatta (es. abbigliamento, trasporti, ristorazione), come macro-categoria o come sottocategoria di un gruppo; qui le puoi rivedere, modificare o eliminare. Le spese già classificate restano nello storico anche se elimini una categoria.</p>
        ${customCats.length ? `<div class="table-wrap"><table class="data">
          <thead><tr><th>Categoria</th><th>Gruppo</th><th>Descrizione</th><th>Esempi</th><th>Origine</th><th></th></tr></thead>
          <tbody>${customCats.map(c => `<tr>
            <td><b>${esc(c.name)}</b></td>
            <td class="hint">${c.parent ? esc(c.parent) : "<i>primo livello</i>"}</td>
            <td class="hint">${esc(c.description || "—")}</td>
            <td class="hint">${esc((c.examples || []).join(", ") || "—")}</td>
            <td>${c.source === "agent" ? `<span class="badge b-non_rilevante">assistente</span>` : `<span class="badge b-familiare">manuale</span>`}</td>
            <td class="num row" style="gap:4px;justify-content:flex-end"><button class="btn-icon" data-edit-cat="${c.id}" title="Modifica">✏️</button><button class="btn-icon" data-del-cat="${c.id}" title="Elimina">🗑️</button></td>
          </tr>`).join("")}</tbody></table></div>` : `<div class="empty" style="padding:18px"><p class="hint">Nessuna categoria personalizzata: per ora si usano le ${builtinCats.length} categorie di base.</p></div>`}
        <details style="margin-top:12px"><summary class="hint" style="cursor:pointer">Mostra le ${builtinCats.length} categorie di base</summary>
          <div style="margin-top:10px">
            <div class="row" style="flex-wrap:wrap;gap:6px">${builtinCats.filter(c => !c.parent).map(c => `<span class="badge b-non_rilevante" title="${esc(c.description || "")}">${esc(c.name)}</span>`).join("")}</div>
            ${builtinGroups.map(g => `<div style="margin-top:10px"><div class="hint" style="font-weight:600;margin-bottom:4px">${esc(g)}</div><div class="row" style="flex-wrap:wrap;gap:6px">${builtinCats.filter(c => c.parent === g).map(c => `<span class="badge b-familiare" title="${esc(c.description || "")}">${esc(c.name)}</span>`).join("")}</div></div>`).join("")}
          </div>
        </details>
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
    $("#add-payment")?.addEventListener("click", () => openPaymentMethodForm(null, isAdmin));
    c.querySelectorAll("[data-edit-pay]").forEach(b => b.addEventListener("click", () => openPaymentMethodForm(methods.find(x => x.id === b.dataset.editPay), isAdmin)));
    c.querySelectorAll("[data-del-pay]").forEach(b => b.addEventListener("click", async () => {
      if (!(await confirmDialog("Eliminare il metodo di pagamento?", "Le spese/bollette collegate restano, ma senza l'associazione al metodo."))) return;
      try { await api(`/household/payment-methods/${b.dataset.delPay}`, { method: "DELETE" }); toast("Metodo eliminato", { type: "ok" }); viewSettings(); }
      catch (e) { toast("Errore", { desc: e.message, type: "err" }); }
    }));
    $("#add-category")?.addEventListener("click", () => openCategoryForm());
    c.querySelectorAll("[data-edit-cat]").forEach(b => b.addEventListener("click", () => openCategoryForm(customCats.find(x => x.id === b.dataset.editCat))));
    c.querySelectorAll("[data-del-cat]").forEach(b => b.addEventListener("click", async () => {
      if (!(await confirmDialog("Eliminare la categoria?", "Le spese già classificate con questo nome restano nello storico. L'assistente non la proporrà più."))) return;
      try { await api(`/household/categories/${b.dataset.delCat}`, { method: "DELETE" }); toast("Categoria eliminata", { type: "ok" }); viewSettings(); }
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

function openCategoryForm(category = null) {
  const cat = category || {};
  // Gruppi (macro-categorie) disponibili: solo quelli di BASE — le categorie
  // personalizzate sono macro-categorie di primo livello (niente gruppi custom).
  const baseCats = (State.categories || []).filter(c => c.builtin).length ? State.categories.filter(c => c.builtin) : BUILTIN_CATEGORIES;
  const groupNames = [...new Set(baseCats.map(c => c.parent).filter(Boolean))];
  if (!groupNames.length) groupNames.push(SUPERMARKET_GROUP);
  const groupOpts = { "": "Nessuno (categoria di primo livello)", ...Object.fromEntries(groupNames.map(g => [g, g])) };
  openModal(`
    <div class="modal-head"><h3>${category ? "Modifica categoria" : "Nuova categoria merceologica"}</h3><button class="btn-icon" data-close>✕</button></div>
    <form id="category-form">
      <div class="field"><label>Nome <span class="hint">(breve, minuscolo)</span></label><input class="input" name="name" placeholder="es. abbigliamento" value="${esc(cat.name || "")}" required></div>
      <div class="field"><label>Gruppo <span class="hint">(macro-categoria)</span></label><select class="select" name="parent">${optList(groupOpts, cat.parent || "")}</select></div>
      <div class="field"><label>Descrizione <span class="hint">(cosa include)</span></label><input class="input" name="description" placeholder="es. vestiti e calzature" value="${esc(cat.description || "")}"></div>
      <div class="field"><label>Esempi <span class="hint">(separati da virgola)</span></label><input class="input" name="examples" placeholder="es. scarpe, giacca, jeans" value="${esc((cat.examples || []).join(", "))}"></div>
      <p class="hint" style="margin-bottom:16px">Lascia il gruppo vuoto per una categoria di primo livello; scegli «spesa supermercato» per un nuovo reparto. Non creare categorie per i medicinali: usa quella di base “farmaci”.</p>
      <button class="btn btn-primary btn-block" type="submit">${category ? "Salva" : "Crea categoria"}</button>
    </form>`);
  $("#modal-root [data-close]").addEventListener("click", closeModal);
  $("#category-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target).entries());
    const examples = (fd.examples || "").split(",").map(s => s.trim()).filter(Boolean);
    const body = { name: fd.name, parent: fd.parent || null, description: fd.description || null, examples: examples.length ? examples : null };
    try {
      if (category) await api(`/household/categories/${category.id}`, { method: "PATCH", body });
      else await api("/household/categories", { method: "POST", body });
      toast(category ? "Categoria aggiornata" : "Categoria creata", { type: "ok" });
      closeModal(); viewSettings();
    } catch (err) { toast("Errore", { desc: err.message, type: "err" }); }
  });
}

function openPaymentMethodForm(method = null, isAdmin = false) {
  const pm = method || {};
  // L'intestatario è selezionabile solo dagli admin; un membro crea per sé.
  const ownerId = pm.user_id || State.user.id;
  const ownerField = isAdmin
    ? `<div class="field"><label>Intestatario</label><select class="select" name="user_id">${optList(Object.fromEntries(State.members.map(m => [m.id, m.full_name])), ownerId)}</select></div>`
    : "";
  openModal(`
    <div class="modal-head"><h3>${method ? "Modifica metodo di pagamento" : "Nuovo metodo di pagamento"}</h3><button class="btn-icon" data-close>✕</button></div>
    <form id="payment-form" class="grid cols-2" style="gap:12px">
      <div class="field" style="grid-column:1/-1"><label>Nome / etichetta</label><input class="input" name="label" placeholder="es. Carta Visa personale, Bancomat conto cointestato" value="${esc(pm.label || "")}" required></div>
      <div class="field"><label>Tipo</label><select class="select" name="method_type">${optList(PAYMENT_TYPE_LABELS, pm.method_type || "carta_credito")}</select></div>
      ${ownerField}
      <div class="field"><label>Circuito / emittente <span class="hint">(opzionale)</span></label><input class="input" name="provider" placeholder="es. Visa, Mastercard, Intesa" value="${esc(pm.provider || "")}"></div>
      <div class="field"><label>Ultime 4 cifre <span class="hint">(opzionale)</span></label><input class="input" name="last4" maxlength="8" placeholder="1234" value="${esc(pm.last4 || "")}"></div>
      <div class="field" style="grid-column:1/-1"><label>Note <span class="hint">(opzionale)</span></label><input class="input" name="notes" value="${esc(pm.notes || "")}"></div>
      <label class="field" style="grid-column:1/-1;flex-direction:row;align-items:center;gap:8px"><input type="checkbox" name="is_default" ${pm.is_default ? "checked" : ""}><span>Metodo predefinito di questo intestatario</span></label>
      ${method ? `<label class="field" style="grid-column:1/-1;flex-direction:row;align-items:center;gap:8px"><input type="checkbox" name="active" ${pm.active === false ? "" : "checked"}><span>Attivo</span></label>` : ""}
      <p class="hint" style="grid-column:1/-1;margin:0">Non inserire mai il numero completo della carta: bastano le ultime 4 cifre per riconoscerla.</p>
      <div class="row between" style="grid-column:1/-1;margin-top:6px">
        <button type="button" class="btn btn-ghost" data-close>Annulla</button>
        <button type="submit" class="btn btn-primary">${method ? "Salva" : "Aggiungi"}</button>
      </div>
    </form>`);
  $("#modal-root").querySelectorAll("[data-close]").forEach(el => el.addEventListener("click", closeModal));
  $("#payment-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const fd = Object.fromEntries(new FormData(form).entries());
    const body = {
      label: fd.label,
      method_type: fd.method_type,
      provider: fd.provider || null,
      last4: fd.last4 || null,
      notes: fd.notes || null,
      is_default: form.querySelector("[name=is_default]").checked,
    };
    if (isAdmin && fd.user_id) body.user_id = fd.user_id;
    if (method) body.active = form.querySelector("[name=active]")?.checked ?? true;
    try {
      if (method) await api(`/household/payment-methods/${method.id}`, { method: "PATCH", body });
      else await api("/household/payment-methods", { method: "POST", body });
      toast(method ? "Metodo aggiornato" : "Metodo aggiunto", { type: "ok" });
      closeModal(); viewSettings();
    } catch (err) { toast("Errore", { desc: err.message, type: "err" }); }
  });
}

function addMemberDialog() {
  openModal(`
    <div class="modal-head"><h3>Aggiungi un membro</h3><button class="btn-icon" data-close>✕</button></div>
    <form id="member-form">
      <div class="field"><label>Nome completo</label><input class="input" name="full_name" required></div>
      <div class="field"><label>Codice fiscale <span class="hint">(opzionale)</span></label><input class="input" name="codice_fiscale" maxlength="16" style="text-transform:uppercase"></div>
      <label class="row" style="gap:8px;margin-bottom:14px;cursor:pointer"><input type="checkbox" id="member-has-access" checked> <span>Crea anche un accesso all'app (login)</span></label>
      <div id="member-access-fields">
        <div class="field"><label>Email</label><input class="input" type="email" name="email"></div>
        <div class="field"><label>Password provvisoria <span class="hint">(min 8)</span></label><input class="input" type="password" name="password" minlength="8"></div>
        <p class="hint" style="margin-bottom:16px">Comunica email e password al familiare: potrà accedere e cambiare i dati.</p>
      </div>
      <p class="hint" id="member-noaccess-hint" style="margin-bottom:16px;display:none">Il familiare sarà un semplice soggetto: potrai attribuirgli spese, documenti e bollette, ma non potrà accedere all'app. Potrai dargli l'accesso in seguito.</p>
      <button class="btn btn-primary btn-block" type="submit">Aggiungi membro</button>
    </form>`);
  $("#modal-root [data-close]").addEventListener("click", closeModal);
  const accessFields = $("#member-access-fields");
  const noAccessHint = $("#member-noaccess-hint");
  const emailEl = accessFields.querySelector("[name=email]");
  const pwEl = accessFields.querySelector("[name=password]");
  const toggle = $("#member-has-access");
  const syncAccess = () => {
    const on = toggle.checked;
    accessFields.style.display = on ? "" : "none";
    noAccessHint.style.display = on ? "none" : "";
    emailEl.required = on; pwEl.required = on;
  };
  toggle.addEventListener("change", syncAccess); syncAccess();
  $("#member-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target).entries());
    if (!toggle.checked) { delete data.email; delete data.password; }
    if (!data.codice_fiscale) delete data.codice_fiscale;
    try { await api("/household/members", { method: "POST", body: data }); toast("Membro aggiunto", { type: "ok" }); closeModal(); viewSettings(); }
    catch (err) { toast("Errore", { desc: err.message, type: "err" }); }
  });
}

function editMemberDialog(member, isAdmin) {
  if (!member) return;
  const isSelf = member.id === State.user.id;
  const hasAccess = !!member.email;
  openModal(`
    <div class="modal-head"><h3>Modifica membro</h3><button class="btn-icon" data-close>✕</button></div>
    <form id="member-edit-form">
      <div class="field"><label>Nome completo</label><input class="input" name="full_name" value="${esc(member.full_name || "")}" required></div>
      <div class="field"><label>Email ${hasAccess ? "" : `<span class="hint">(lascia vuoto per un soggetto senza accesso)</span>`}</label><input class="input" type="email" name="email" value="${esc(member.email || "")}" ${hasAccess ? "required" : ""}></div>
      <div class="field"><label>Codice fiscale <span class="hint">(opzionale)</span></label><input class="input" name="codice_fiscale" maxlength="16" style="text-transform:uppercase" value="${esc(member.codice_fiscale || "")}"></div>
      ${isAdmin ? `<div class="field"><label>Ruolo</label><select class="select" name="role">${optList({ member: "Membro", admin: "Admin" }, member.role)}</select></div>` : ""}
      <div class="field"><label>${hasAccess ? "Nuova password" : "Password"} <span class="hint">${hasAccess ? "(lascia vuoto per non cambiarla, min 8)" : "(impostala per dare l'accesso, min 8)"}</span></label><input class="input" type="password" name="password" minlength="8" autocomplete="new-password"></div>
      ${hasAccess ? "" : `<p class="hint" style="margin-bottom:14px">Questo familiare non ha accesso all'app. Inserisci email e password per dargli un accesso (login).</p>`}
      <button class="btn btn-primary btn-block" type="submit">Salva modifiche</button>
    </form>`);
  $("#modal-root [data-close]").addEventListener("click", closeModal);
  $("#member-edit-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target).entries());
    if (!data.password) delete data.password;
    if (!data.email) delete data.email;
    // Per dare l'accesso a un soggetto servono email e password insieme.
    if (data.email && !hasAccess && !data.password) {
      toast("Per dare l'accesso serve anche una password", { type: "err" }); return;
    }
    if (data.password && !hasAccess && !data.email) {
      toast("Per dare l'accesso serve anche un'email", { type: "err" }); return;
    }
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
function indexPaymentMethods() { State.paymentMethodsById = Object.fromEntries(State.paymentMethods.map(m => [m.id, m])); }

function updateReviewBadge(count) {
  State._reviewCount = count;
  const item = $(".nav-item[data-nav=revisione]");
  if (!item) return;
  let dot = item.querySelector(".badge-dot");
  if (count > 0) {
    if (!dot) { dot = document.createElement("span"); dot.className = "badge-dot"; item.appendChild(dot); }
    dot.textContent = count;
  } else if (dot) { dot.remove(); }
}

// Aggiorna il badge "Revisione" col numero di voci ancora aperte (pending).
async function refreshReviewBadge() {
  try {
    const s = await api("/review/summary");
    updateReviewBadge(s.pending || 0);
  } catch { /* il badge non è critico */ }
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
    const [members, hh, units, methods, categories] = await Promise.all([
      api("/household/members"),
      api("/household").catch(() => null),
      api("/household/units").catch(() => []),
      api("/household/payment-methods").catch(() => []),
      api("/household/categories").catch(() => []),
    ]);
    State.members = members; indexMembers();
    State.units = units || [];
    State.paymentMethods = methods || []; indexPaymentMethods();
    State.categories = categories || [];
    if (hh) State.user.household_name = hh.name;
    renderShell();
    refreshReviewBadge();
    navigate(State.view || "dashboard");
  } catch (err) {
    logout(true);
    renderAuth("login");
  }
}

document.addEventListener("DOMContentLoaded", boot);

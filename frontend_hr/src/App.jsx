/**
 * Dipendenti in Cloud - Modulo HR completo con sidebar dedicata
 * Layout originale con sidebar blu scuro e navigazione tramite URL
 */
import React, { useState, useEffect, useCallback, useRef, Fragment } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import axios from "axios";
import Sortable from "sortablejs";
import { 
  Users, Calendar, Clock, FileText, Briefcase, Home, 
  ChevronRight, Plus, Check, X, Edit2, Trash2, 
  MapPin, Euro, Download, RefreshCw, ChevronLeft, Grid3X3,
  User, FolderOpen, Settings, LogOut, ArrowLeft, AlertTriangle,
  Wallet, Receipt, Building2, Inbox, CheckCircle2, Link2, Activity, Send
} from "lucide-react";
import "./App.css";

const API = '/hr/api/dipendenti-cloud';

// --- Autenticazione: allega il JWT a ogni chiamata e gestisce la scadenza ---
// L'area gestione è protetta lato server (require_admin/require_staff): senza
// token valido le API rispondono 401/403 e qui riportiamo l'utente al PIN.
axios.interceptors.request.use((cfg) => {
  const t = localStorage.getItem("pt_token");
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});
axios.interceptors.response.use(
  (r) => r,
  (err) => {
    const s = err?.response?.status;
    if (s === 401 || s === 403) {
      localStorage.removeItem("pt_token");
      localStorage.removeItem("pt_role");
      localStorage.removeItem("pt_name");
      if (!location.pathname.startsWith("/hr/portale")) location.replace("/hr/portale");
    }
    return Promise.reject(err);
  }
);

// Helper functions
const formatDate = (dateStr) => {
  if (!dateStr) return "-";
  const s = String(dateStr);
  // ISO con ora (2026-08-28T07:02:14+00:00) -> 28/08/2026 09:02 (ora locale)
  if (s.length > 10 && s[10] === "T") {
    const d = new Date(s);
    if (!isNaN(d)) return d.toLocaleDateString("it-IT") + " " + d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  }
  const parts = s.slice(0, 10).split("-");
  if (parts.length !== 3) return s;
  return `${parts[2]}/${parts[1]}/${parts[0]}`;
};

const getInitials = (nome, cognome) => `${nome?.[0] || ""}${cognome?.[0] || ""}`.toUpperCase();

// Palette on-brand (sage/cream/terracotta/oliva): niente blu/indigo/viola (regola titolare).
const AVATAR_COLORS = ["#5b7a6b", "#3d8168", "#7d5526", "#a6724a", "#8a9a5b", "#b08968", "#4f6f5e", "#9c6b4a"];
const getAvatarColor = (str) => {
  let hash = 0;
  for (let i = 0; i < (str || "").length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
};

// Badge component
const Badge = ({ children, variant = "default" }) => {
  const variants = {
    default: "dc-badge-default",
    success: "dc-badge-success",
    warning: "dc-badge-warning",
    danger: "dc-badge-danger",
    info: "dc-badge-info",
  };
  return <span className={`dc-badge ${variants[variant]}`}>{children}</span>;
};

/* ---------- Toast: conferme/errori non bloccanti (al posto degli alert) ---------- */
let _pushToast = null;
const toast = (msg, tipo = "ok") => { if (_pushToast) _pushToast(msg, tipo); else if (tipo === "err") window.alert(msg); };
function Toaster() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    let n = 0;
    _pushToast = (msg, tipo) => {
      const id = `${++n}_${Date.now()}`;
      setItems(x => [...x, { id, msg, tipo }]);
      setTimeout(() => setItems(x => x.filter(i => i.id !== id)), 3200);
    };
    return () => { _pushToast = null; };
  }, []);
  const col = { ok: "#3d8168", err: "#b04a3a", info: "#5b7a6b" };
  return (
    <div style={{ position: "fixed", top: 16, left: "50%", transform: "translateX(-50%)", zIndex: 9999, display: "flex", flexDirection: "column", gap: 8, alignItems: "center", pointerEvents: "none" }}>
      {items.map(i => (
        <div key={i.id} style={{ background: col[i.tipo] || col.info, color: "#fff", padding: "10px 18px", borderRadius: 10, fontSize: 14, fontWeight: 600, boxShadow: "0 6px 20px rgba(0,0,0,.18)", maxWidth: "92vw" }}>
          {i.tipo === "ok" ? "✓ " : i.tipo === "err" ? "⚠ " : ""}{i.msg}
        </div>
      ))}
    </div>
  );
}

// Avatar component
const Avatar = ({ nome, cognome, size = "md" }) => {
  const sizes = { sm: "dc-avatar-sm", md: "dc-avatar-md", lg: "dc-avatar-lg" };
  return (
    <div className={`dc-avatar ${sizes[size]}`} style={{ backgroundColor: getAvatarColor(`${nome}${cognome}`) }}>
      {getInitials(nome, cognome)}
    </div>
  );
};

// Main App Component with Router
export default function DipendentiCloudApp({ page: pageProp }) {
  const { page: pageParam } = useParams();
  const navigate = useNavigate();
  const role = typeof window !== "undefined" ? localStorage.getItem("pt_role") : null;
  // Il responsabile turni entra in azienda ma può stare SOLO sulla pagina Turni.
  const soloTurni = role === "responsabile_turni";
  const currentPage = soloTurni ? "turni" : (pageProp || pageParam || "dashboard");

  const [dipendenti, setDipendenti] = useState([]);
  const [presenze, setPresenze] = useState([]);
  const [ferie, setFerie] = useState([]);
  const [turni, setTurni] = useState([]);
  const [bustePaga, setBustePaga] = useState([]);
  const [missioni, setMissioni] = useState([]);
  const [documenti, setDocumenti] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [ordineDip, setOrdineDip] = useState([]);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [dipRes, ferRes, turRes, missRes, docRes, statsRes, ordRes] = await Promise.all([
        axios.get(`${API}/dipendenti`),
        axios.get(`${API}/ferie`),
        axios.get(`${API}/turni`),
        axios.get(`${API}/missioni`),
        axios.get(`${API}/documenti`),
        axios.get(`${API}/dashboard/stats`),
        axios.get(`${API}/ordine-dipendenti`).catch(() => ({ data: { ordine: [] } })),
      ]);
      setDipendenti(dipRes.data || []);
      setFerie(ferRes.data || []);
      setTurni(turRes.data || []);
      setMissioni(missRes.data || []);
      setDocumenti(docRes.data || []);
      setStats(statsRes.data || {});
      setOrdineDip((ordRes.data || {}).ordine || []);
    } catch (error) {
      console.error("Error loading data:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // Aggiorna una sola riga dell'anagrafica senza ricaricare tutta l'app
  // (prima ogni salvataggio mostrava "Caricamento…" per secondi e perdeva lo scroll).
  const aggiornaDipendente = useCallback((dip, { rimosso = false } = {}) => {
    setDipendenti((lista) => {
      if (rimosso) return lista.filter((d) => d.id !== dip.id);
      const c = lista.some((d) => d.id === dip.id);
      return c ? lista.map((d) => (d.id === dip.id ? { ...d, ...dip } : d)) : [...lista, dip];
    });
  }, []);

  const getDipendente = (id) => dipendenti.find(d => d.id === id);
  const activeDipendenti = (() => {
    const attivi = dipendenti.filter(d => d.stato === "attivo");
    if (!ordineDip.length) return attivi;
    const pos = (id) => { const i = ordineDip.indexOf(id); return i === -1 ? 9999 : i; };
    return [...attivi].sort((a, b) => pos(a.id) - pos(b.id));
  })();

  // Menu items
  const menuItems = soloTurni ? [
    { id: "turni", label: "Turni", icon: Grid3X3, section: "TURNI" },
  ] : [
    { id: "dashboard", label: "Pannello di controllo", icon: Home, section: "GESTIONE" },
    { id: "diagnostica", label: "Diagnostica", icon: Activity, section: "GESTIONE" },
    { id: "anagrafica", label: "Anagrafica", icon: User, section: "DIPENDENTI" },
    { id: "presenze", label: "Presenze", icon: Calendar, section: "DIPENDENTI" },
    { id: "ferie-permessi", label: "Ferie & Permessi", icon: Calendar, section: "DIPENDENTI" },
    { id: "turni", label: "Turni", icon: Grid3X3, section: "DIPENDENTI" },
    { id: "timbrature", label: "Timbrature", icon: Clock, section: "DIPENDENTI" },
    { id: "paghe-bonifici", label: "Archivio paghe", icon: Link2, section: "DIPENDENTI" },
    { id: "bonifici-da-associare", label: "Bonifici da associare", icon: Inbox, section: "DIPENDENTI" },
    { id: "tfr", label: "TFR", icon: Wallet, section: "DIPENDENTI" },
    { id: "documenti", label: "Documenti", icon: FolderOpen, section: "DIPENDENTI" },
    { id: "assunzione", label: "Assunzione & Contratti", icon: Briefcase, section: "DIPENDENTI" },
    { id: "bonifici-banca", label: "Bonifici effettuati", icon: Euro, section: "PAGAMENTI" },
  ];

  const pageLabels = {
    dashboard: "Pannello di controllo",
    diagnostica: "Diagnostica",
    anagrafica: "Anagrafica",
    presenze: "Presenze",
    "ferie-permessi": "Ferie & Permessi",
    turni: "Turni",
    timbrature: "Timbrature",
    "paghe-bonifici": "Archivio paghe",
    "bonifici-da-associare": "Bonifici da associare",
    tfr: "TFR",
    missioni: "Missioni",
    documenti: "Documenti",
    assunzione: "Assunzione & Contratti",
    "bonifici-banca": "Bonifici effettuati",
  };

  if (loading) {
    return (
      <div className="dc-loading">
        <div className="dc-spinner" />
        <p>Caricamento Dipendenti in Cloud...</p>
      </div>
    );
  }

  const renderPage = () => {
    switch (currentPage) {
      case "dashboard":
        return <DashboardPage stats={stats} dipendenti={dipendenti} ferie={ferie} missioni={missioni} getDipendente={getDipendente} />;
      case "diagnostica":
        return <DiagnosticaPage />;
      case "anagrafica":
        return <AnagraficaPage dipendenti={dipendenti} reload={loadData} onDipendente={aggiornaDipendente} />;
      case "presenze":
        return <PresenzePage dipendenti={activeDipendenti} reload={loadData} />;
      case "ferie-permessi":
        return <FeriePage dipendenti={activeDipendenti} ferie={ferie} reload={loadData} getDipendente={getDipendente} />;
      case "turni":
        return <TurniPage dipendenti={activeDipendenti} turni={turni} reload={loadData} />;
      case "timbrature":
        return <TimbraturePage dipendenti={dipendenti} getDipendente={getDipendente} />;
      case "buste-paga":  // vecchio indirizzo (pagina unificata il 14/09/2026)
      case "paghe-bonifici":
        return <PagheBonificiPage dipendenti={activeDipendenti} />;
      case "bonifici-da-associare":
        return <BonificiDaAssociarePage dipendenti={dipendenti} />;
      case "tfr":
        return <TfrPage dipendenti={activeDipendenti} getDipendente={getDipendente} />;
      case "missioni":
        return <MissioniPage dipendenti={activeDipendenti} missioni={missioni} reload={loadData} getDipendente={getDipendente} />;
      case "documenti":
        return <DocumentiPage dipendenti={dipendenti} documenti={documenti} reload={loadData} getDipendente={getDipendente} />;
      case "assunzione":
        return <AssunzionePage dipendenti={dipendenti} reload={loadData} />;
      case "bonifici-banca":
        return <BonificiContabPage />;
      default:
        return <DashboardPage stats={stats} dipendenti={dipendenti} ferie={ferie} missioni={missioni} getDipendente={getDipendente} />;
    }
  };

  // Group menu items by section
  const sections = {};
  menuItems.forEach(item => {
    if (!sections[item.section]) sections[item.section] = [];
    sections[item.section].push(item);
  });

  return (
    <div className="dc-app">
      <Toaster />
      {/* Barra mobile con menu a tendina */}
      <div className="dc-mobile-topbar">
        <button className="dc-hamburger" onClick={() => setMobileMenuOpen(true)} aria-label="Apri menu">
          <span></span><span></span><span></span>
        </button>
        <span className="dc-mobile-title">{menuItems.find(m => m.id === currentPage)?.label || "Dipendenti"}</span>
      </div>
      {mobileMenuOpen && <div className="dc-mobile-overlay" onClick={() => setMobileMenuOpen(false)} />}
      {/* Sidebar */}
      <aside className={`dc-sidebar ${mobileMenuOpen ? 'open' : ''}`}>
        <div className="dc-sidebar-header">
          <div className="dc-sidebar-logo">
            <Users size={28} />
            <div>
              <span className="dc-logo-title">Dipendenti</span>
              <span className="dc-logo-subtitle">nella nuvola</span>
            </div>
          </div>
        </div>

        <nav className="dc-sidebar-nav">
          {Object.entries(sections).map(([section, items]) => (
            <div key={section} className="dc-sidebar-section">
              <div className="dc-sidebar-section-title">{section}</div>
              {items.map(item => (
                <Link
                  key={item.id}
                  to={`/dipendenti/${item.id}`}
                  className={`dc-sidebar-item ${currentPage === item.id ? 'active' : ''}`}
                  data-testid={`sidebar-${item.id}`}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  <item.icon size={18} />
                  <span>{item.label}</span>
                </Link>
              ))}
            </div>
          ))}
        </nav>

        <div className="dc-sidebar-footer">
          <div className="dc-sidebar-user">
            <div className="dc-avatar dc-avatar-sm" style={{ backgroundColor: "#10b981" }}>VC</div>
            <div className="dc-user-info">
              <span className="dc-user-name">Vincenzo C.</span>
              <span className="dc-user-role">Proprietario</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="dc-main">
        {/* Breadcrumb */}
        <div className="dc-breadcrumb">
          <span>Gestione</span>
          <ChevronRight size={14} />
          <span className="dc-breadcrumb-current">{pageLabels[currentPage] || currentPage}</span>
          <div className="dc-breadcrumb-company">Ceraldi Group SRL</div>
        </div>

        {/* Page Content */}
        <div className="dc-content">
          {renderPage()}
        </div>
      </main>
    </div>
  );
}

// ==================== PAGES ====================

// Diagnostica Page — autotest dal vivo di backend e pagine
// Finestra modale accessibile (audit WCAG 14/09/2026): un solo componente per
// tutte le modali dell'app. role=dialog + aria-modal, titolo collegato con
// aria-labelledby, focus portato dentro all'apertura, Tab che gira solo fra i
// controlli della finestra, Esc che chiude, focus restituito al bottone che
// l'ha aperta. Clic sullo sfondo = chiudi (come prima).
let _modalSeq = 0;
function Modal({ title, onClose, large, wide, maxWidth, children }) {
  const boxRef = useRef(null);
  const [titleId] = useState(() => `dc-modal-title-${++_modalSeq}`);
  useEffect(() => {
    const opener = document.activeElement;
    const box = boxRef.current;
    if (!box) return undefined;
    const focusables = () => Array.from(box.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )).filter(el => el.offsetParent !== null);
    const primo = focusables().find(el => !el.classList.contains("dc-modal-close")) || box;
    primo.focus();
    const onKey = (e) => {
      if (e.key === "Escape") { e.stopPropagation(); onClose?.(); return; }
      if (e.key !== "Tab") return;
      const lista = focusables();
      if (!lista.length) { e.preventDefault(); box.focus(); return; }
      const a = lista[0], z = lista[lista.length - 1];
      if (e.shiftKey && (document.activeElement === a || document.activeElement === box)) { e.preventDefault(); z.focus(); }
      else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
    };
    box.addEventListener("keydown", onKey);
    return () => {
      box.removeEventListener("keydown", onKey);
      if (opener && typeof opener.focus === "function" && document.contains(opener)) opener.focus();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="dc-modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div ref={boxRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={titleId}
        className={`dc-modal${large ? " dc-modal-lg" : ""}${wide ? " dc-modal-wide" : ""}`} style={maxWidth ? { maxWidth } : undefined}>
        <div className="dc-modal-header">
          <h3 id={titleId}>{title}</h3>
          <button type="button" onClick={onClose} className="dc-modal-close" aria-label="Chiudi finestra"><X size={20} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

function DiagnosticaPage() {
  const [checks, setChecks] = useState(null);
  const [riepilogo, setRiepilogo] = useState(null);
  const [pagine, setPagine] = useState(null);
  const [loading, setLoading] = useState(false);
  const [erroreBE, setErroreBE] = useState(null);
  const oggi = new Date();
  const Y = oggi.getFullYear(), M = oggi.getMonth() + 1;
  const lun = (() => { const o = new Date(); const off = (o.getDay() + 6) % 7; const m = new Date(o); m.setDate(o.getDate() - off); return `${m.getFullYear()}-${String(m.getMonth() + 1).padStart(2, '0')}-${String(m.getDate()).padStart(2, '0')}`; })();

  // Ping dal vivo dell'endpoint principale di ogni pagina (testa HTTP + auth + wiring)
  const PAGINE = [
    { pagina: "Pannello di controllo", url: `${API}/dashboard/stats` },
    { pagina: "Anagrafica", url: `${API}/dipendenti` },
    { pagina: "Presenze", url: `${API}/presenze?anno=${Y}&mese=${M}` },
    { pagina: "Ferie & Permessi", url: `${API}/ferie` },
    { pagina: "Turni (tipi)", url: `${API}/turni` },
    { pagina: "Turni (settimana)", url: `${API}/assegnazioni-turni?settimana=${lun}` },
    { pagina: "Cedolini & Bonifici", url: `${API}/paghe/associazioni-bonifici?anno=${Y}` },
    { pagina: "Documenti", url: `${API}/documenti` },
    { pagina: "Missioni", url: `${API}/missioni` },
    { pagina: "Avvisi & Scadenze", url: `${API}/alerts` },
    { pagina: "Buste in attesa", url: `${API}/paghe/in-attesa` },
    { pagina: "Contabilità (fatture)", url: `/hr/api/contabilita/fatture` },
  ];

  const run = async () => {
    setLoading(true); setErroreBE(null);
    // 1) Diagnostica backend
    try {
      const r = await axios.get(`/hr/api/diagnostica`);
      setChecks(r.data.checks || []);
      setRiepilogo(r.data.riepilogo || null);
    } catch (e) {
      setErroreBE(e?.response?.data?.detail || e.message || "Diagnostica backend non raggiungibile");
      setChecks([]); setRiepilogo(null);
    }
    // 2) Ping pagine (in parallelo)
    const res = await Promise.all(PAGINE.map(async p => {
      const t0 = performance.now();
      try {
        await axios.get(p.url);
        return { ...p, stato: "ok", ms: Math.round(performance.now() - t0) };
      } catch (e) {
        const s = e?.response?.status;
        return { ...p, stato: "err", dettaglio: s ? `HTTP ${s}` : (e.message || "errore"), ms: Math.round(performance.now() - t0) };
      }
    }));
    setPagine(res);
    setLoading(false);
  };
  useEffect(() => { run(); }, []);

  const COL = { ok: "#3d8168", warn: "#a6724a", err: "#b04a3a" };
  const ICON = { ok: "✓", warn: "▲", err: "✗" };
  const pill = (stato) => (
    <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 22, height: 22, borderRadius: "50%", background: COL[stato] || "#9aa593", color: "#fff", fontWeight: 800, fontSize: 13, flexShrink: 0 }}>{ICON[stato] || "?"}</span>
  );

  const aree = {};
  (checks || []).forEach(c => { (aree[c.area] = aree[c.area] || []).push(c); });
  const pagineErr = (pagine || []).filter(p => p.stato === "err").length;

  return (
    <div className="dc-page">
      <div className="dc-page-header">
        <div>
          <h1>Diagnostica</h1>
          <p>Controlli dal vivo dell'app: se qualcosa è rosso, segnalalo e si sistema.</p>
        </div>
        <div className="dc-page-actions">
          <button onClick={run} disabled={loading} className="dc-btn dc-btn-primary">
            <RefreshCw size={16} /> {loading ? "Controllo…" : "Rilancia controlli"}
          </button>
        </div>
      </div>

      {/* Riepilogo */}
      <div className="dc-stats-grid" style={{ marginBottom: 16 }}>
        <div className="dc-stat-card" style={{ borderLeft: "4px solid #3d8168" }}>
          <div className="dc-stat-content"><span className="dc-stat-label">OK</span><span className="dc-stat-value" style={{ color: "#3d8168" }}>{(riepilogo?.ok || 0) + (pagine || []).filter(p => p.stato === "ok").length}</span></div>
        </div>
        <div className="dc-stat-card" style={{ borderLeft: "4px solid #a6724a" }}>
          <div className="dc-stat-content"><span className="dc-stat-label">DA CONTROLLARE</span><span className="dc-stat-value" style={{ color: "#a6724a" }}>{riepilogo?.warn || 0}</span></div>
        </div>
        <div className="dc-stat-card" style={{ borderLeft: "4px solid #b04a3a" }}>
          <div className="dc-stat-content"><span className="dc-stat-label">ERRORI</span><span className="dc-stat-value" style={{ color: "#b04a3a" }}>{(riepilogo?.err || 0) + pagineErr}</span></div>
        </div>
      </div>

      {/* Pagine (ping dal vivo) */}
      <div className="dc-card" style={{ marginBottom: 16 }}>
        <h3>Pagine dell'app</h3>
        {!pagine ? <p className="dc-muted">Controllo…</p> : (
          <div className="dc-list">
            {pagine.map((p, i) => (
              <div key={i} className="dc-list-item" style={{ display: "flex", alignItems: "center", gap: 12 }}>
                {pill(p.stato)}
                <span style={{ flex: 1, fontWeight: 600 }}>{p.pagina}</span>
                <span className="dc-muted" style={{ fontSize: 12 }}>{p.stato === "ok" ? `${p.ms} ms` : (p.dettaglio || "errore")}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Diagnostica backend per area */}
      {erroreBE && <div className="dc-card" style={{ borderLeft: "4px solid #b04a3a", marginBottom: 16, color: "#b04a3a" }}>⚠ {erroreBE}</div>}
      {Object.entries(aree).map(([area, lista]) => (
        <div key={area} className="dc-card" style={{ marginBottom: 16 }}>
          <h3>{area}</h3>
          <div className="dc-list">
            {lista.map((c, i) => (
              <div key={i} className="dc-list-item" style={{ display: "flex", alignItems: "center", gap: 12 }}>
                {pill(c.stato)}
                <span style={{ flex: 1, fontWeight: 600 }}>{c.nome}</span>
                <span className="dc-muted" style={{ fontSize: 12 }}>{c.dettaglio}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// Dashboard Page
function DashboardPage({ stats, dipendenti, ferie, missioni, getDipendente }) {
  const attivi = dipendenti.filter(d => d.stato === "attivo").length;
  const pendingFerie = ferie.filter(f => f.stato === "in_attesa");
  const pendingMissioni = missioni.filter(m => m.stato === "in_attesa");
  const [alerts, setAlerts] = useState([]);
  const [pendenze, setPendenze] = useState(null);
  const loadAlerts = () => axios.get(`${API}/alerts`).then(r => setAlerts(r.data.alerts || [])).catch(() => {});
  useEffect(() => { loadAlerts(); axios.get(`${API}/paghe/in-attesa`).then(r => setPendenze(r.data)).catch(() => {}); }, []);
  const mesiIt = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];
  const risolviAlert = async (id) => {
    try { await axios.post(`${API}/alerts/${id}/risolvi`); loadAlerts(); } catch {}
  };
  const sevColor = (s) => ({ critico: "danger", alto: "danger", warning: "warning", media: "warning" }[s] || "default");

  return (
    <div className="dc-page">
      <div className="dc-page-header">
        <h1>Pannello di Controllo</h1>
        <p>{dipendenti.length} dipendenti totali</p>
      </div>

      <div className="dc-stats-grid">
        <div className="dc-stat-card dc-stat-blue">
          <div className="dc-stat-icon"><Users size={24} /></div>
          <div className="dc-stat-content">
            <span className="dc-stat-label">DIPENDENTI</span>
            <span className="dc-stat-value">{dipendenti.length}</span>
            <span className="dc-stat-sub">{attivi} attivi</span>
          </div>
        </div>
        <div className="dc-stat-card dc-stat-green">
          <div className="dc-stat-icon"><Clock size={24} /></div>
          <div className="dc-stat-content">
            <span className="dc-stat-label">PRESENTI OGGI</span>
            <span className="dc-stat-value">{stats.presenze_oggi || 0}</span>
          </div>
        </div>
        <div className="dc-stat-card dc-stat-yellow">
          <div className="dc-stat-icon"><Calendar size={24} /></div>
          <div className="dc-stat-content">
            <span className="dc-stat-label">FERIE IN ATTESA</span>
            <span className="dc-stat-value">{pendingFerie.length}</span>
          </div>
        </div>
        <div className="dc-stat-card dc-stat-purple">
          <div className="dc-stat-icon"><MapPin size={24} /></div>
          <div className="dc-stat-content">
            <span className="dc-stat-label">MISSIONI IN ATTESA</span>
            <span className="dc-stat-value">{pendingMissioni.length}</span>
          </div>
        </div>
        <div className="dc-stat-card dc-stat-yellow">
          <div className="dc-stat-icon"><AlertTriangle size={24} /></div>
          <div className="dc-stat-content">
            <span className="dc-stat-label">AVVISI &amp; SCADENZE</span>
            <span className="dc-stat-value">{stats.alert_aperti ?? alerts.length}</span>
          </div>
        </div>
        <div className="dc-stat-card" style={{ borderLeft: "4px solid #d35f4e" }}>
          <div className="dc-stat-icon"><FileText size={24} /></div>
          <div className="dc-stat-content">
            <span className="dc-stat-label">BUSTE DA PAGARE ({new Date().getFullYear()})</span>
            <span className="dc-stat-value">{stats.buste_in_attesa ?? 0}</span>
            <span className="dc-stat-sub">€ {(stats.importo_in_attesa || 0).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} da erogare
              {stats.buste_storiche_non_agganciate ? ` · ${stats.buste_storiche_non_agganciate} storiche senza bonifico agganciato` : ""}</span>
          </div>
        </div>
      </div>

      <div className="dc-card" style={{ marginBottom: 16 }}>
        <h3><AlertTriangle size={18} /> Avvisi &amp; Scadenze</h3>
        {alerts.length === 0 ? (
          <p className="dc-empty">Nessun avviso aperto</p>
        ) : (
          <div className="dc-list">
            {alerts.slice(0, 12).map((a) => (
              <div key={a.id} className="dc-list-item">
                <Badge variant={sevColor(a.severita)}>{a.severita}</Badge>
                <div className="dc-list-info" style={{ flex: 1 }}>
                  <span className="dc-list-name">{a.titolo}</span>
                  <span className="dc-list-sub">{a.dettaglio}</span>
                </div>
                <button className="dc-btn" onClick={() => risolviAlert(a.id)}>Risolvi</button>
              </div>
            ))}
          </div>
        )}
      </div>

      {pendenze && pendenze.totale > 0 && (() => {
        const eur = (v) => (v || 0).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        const correnti = pendenze.righe.filter(x => !x.storico);
        const storiche = pendenze.righe.filter(x => x.storico);
        const Tabella = ({ righe, storico }) => (
          <div style={{ overflowX: "auto" }}>
            <table className="dc-table" style={{ minWidth: 480 }}>
              <thead><tr><th>Dipendente</th><th>Periodo</th><th style={{ textAlign: "right" }}>Busta €</th><th style={{ textAlign: "right" }}>{storico ? "Non agganciato €" : "Manca €"}</th><th>Stato</th></tr></thead>
              <tbody>
                {righe.slice(0, 30).map((x, i) => (
                  <tr key={i}>
                    <td>{x.dipendente}</td>
                    <td>{mesiIt[(x.mese || 1) - 1]} {x.anno}</td>
                    <td style={{ textAlign: "right" }}>{x.busta ? eur(x.busta) : "—"}</td>
                    <td style={{ textAlign: "right", color: storico ? "#7d5526" : "#d35f4e", fontWeight: 700 }}>{eur(x.saldo)}</td>
                    <td><Badge variant={storico ? "default" : x.stato === "parziale" ? "warning" : "danger"}>{storico ? "bonifico non agganciato" : x.stato === "parziale" ? "parziale" : "da pagare"}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {righe.length > 30 && <p className="dc-muted" style={{ fontSize: 12 }}>… e altre {righe.length - 30} righe in Cedolini &amp; Bonifici.</p>}
          </div>
        );
        return (
          <div className="dc-card" style={{ marginBottom: 16, borderLeft: "4px solid #d35f4e" }}>
            <h3><FileText size={18} /> Buste da pagare {pendenze.anno_corrente} <span className="dc-muted" style={{ fontWeight: 400 }}>· {pendenze.da_pagare?.totale ?? correnti.length} · € {eur(pendenze.da_pagare?.importo)}</span></h3>
            {correnti.length === 0 ? <p className="dc-empty">Nessuna busta dell'anno in attesa di pagamento.</p> : <Tabella righe={correnti} storico={false} />}
            {storiche.length > 0 && (
              <details style={{ marginTop: 12 }}>
                <summary style={{ cursor: "pointer", fontWeight: 600 }}>Anni precedenti: {pendenze.non_agganciate?.totale ?? storiche.length} buste con pagamento non ancora agganciato · € {eur(pendenze.non_agganciate?.importo)}</summary>
                <p className="dc-muted" style={{ fontSize: 12 }}>Cedolini storici quasi sempre già pagati: manca solo l'aggancio del bonifico (coda «Bonifici da associare» o estratto conto non ancora importato). Non sono soldi da erogare.</p>
                <Tabella righe={storiche} storico={true} />
              </details>
            )}
            <p className="dc-muted" style={{ fontSize: 12, marginTop: 8 }}>Aggancio automatico: appena arriva il bonifico (PDF, estratto conto, CSV) la riga sparisce. Dettaglio in Cedolini &amp; Bonifici.</p>
          </div>
        );
      })()}

      <div className="dc-dashboard-grid">
        <div className="dc-card">
          <h3><Calendar size={18} /> Ferie/Permessi da Approvare</h3>
          {pendingFerie.length === 0 ? (
            <p className="dc-empty">Nessuna richiesta in attesa</p>
          ) : (
            <div className="dc-list">
              {pendingFerie.slice(0, 5).map((f, i) => {
                const dip = getDipendente(f.dipendente_id);
                return (
                  <div key={f.id || i} className="dc-list-item">
                    <Avatar nome={dip?.nome} cognome={dip?.cognome} size="sm" />
                    <div className="dc-list-info">
                      <span className="dc-list-name">{dip?.nome} {dip?.cognome}</span>
                      <span className="dc-list-sub">{f.tipo} - {f.giorni}gg dal {formatDate(f.data_inizio)}</span>
                    </div>
                    <Badge variant="warning">In attesa</Badge>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="dc-card">
          <h3><MapPin size={18} /> Missioni da Approvare</h3>
          {pendingMissioni.length === 0 ? (
            <p className="dc-empty">Nessuna missione in attesa</p>
          ) : (
            <div className="dc-list">
              {pendingMissioni.slice(0, 5).map((m, i) => {
                const dip = getDipendente(m.dipendente_id);
                return (
                  <div key={m.id || i} className="dc-list-item">
                    <Avatar nome={dip?.nome} cognome={dip?.cognome} size="sm" />
                    <div className="dc-list-info">
                      <span className="dc-list-name">{dip?.nome} {dip?.cognome}</span>
                      <span className="dc-list-sub">{m.destinazione} - {formatDate(m.data_inizio)}</span>
                    </div>
                    <Badge variant="warning">In attesa</Badge>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Anagrafica Page — fonte unica di chi lavora in azienda (anche per Lotti).
// 14/09/2026: un solo stato del rapporto (attivo / cessato dal gg/mm/aaaa con
// motivo e riferimento), cessazione con modale dell'app, PIN personale nella
// scheda (vale per portale e tablet Lotti), salvataggio in linea.
const MOTIVI_CESSAZIONE = [
  ["dimissioni", "Dimissioni"], ["licenziamento", "Licenziamento"], ["fine_contratto", "Fine contratto"],
  ["risoluzione_consensuale", "Risoluzione consensuale"], ["altro", "Altro"],
];
const FORM_DIP_VUOTO = {
  nome: "", cognome: "", ruolo: "", email: "", telefono: "", codice_fiscale: "", matricola: "",
  data_nascita: "", indirizzo: "", contratto: "", data_assunzione: "", iban: "", livello: "",
  ore_settimanali: "", lotti_operatore: true,
};
const CAMPI_FORM_DIP = Object.keys(FORM_DIP_VUOTO);

function AnagraficaPage({ dipendenti, reload, onDipendente }) {
  const [showModal, setShowModal] = useState(false);
  const [editingDip, setEditingDip] = useState(null);
  const [formData, setFormData] = useState(FORM_DIP_VUOTO);
  const [salvando, setSalvando] = useState(false);
  const [pinNuovo, setPinNuovo] = useState("");
  const [pinBusy, setPinBusy] = useState(false);
  const [cessa, setCessa] = useState(null); // {dip, data, motivo, riferimento, note}
  const [cessaBusy, setCessaBusy] = useState(false);
  // Default "attivi": i cessati restano cercabili dal filtro ma non
  // affollano la vista di apertura, che e' quella che si guarda ogni giorno.
  const [filter, setFilter] = useState("attivi");
  const anagRef = useRef(null);
  const [anagBusy, setAnagBusy] = useState(false);
  const oggiISO = new Date().toISOString().slice(0, 10);

  const handleImportAnagrafica = async (e) => {
    const fl = (e.target.files || [])[0];
    if (!fl) return;
    setAnagBusy(true);
    try {
      const fd = new FormData(); fd.append("file", fl);
      const r = await axios.post(`${API}/dipendenti/importa-anagrafica`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast(`Anagrafica importata: ${r.data.creati} creati, ${r.data.aggiornati} aggiornati.`);
      reload && reload();
    } catch (err) { toast(err?.response?.data?.detail || "Errore import anagrafica", "err"); }
    finally { setAnagBusy(false); if (anagRef.current) anagRef.current.value = ""; }
  };
  const [showRid, setShowRid] = useState(false);
  const [ridRows, setRidRows] = useState([]);
  const apriRid = () => {
    setRidRows(dipendenti.map(d => { const r = d.riduzione_orario || {}; return {
      dipendente_id: d.id, nome: `${d.cognome || ''} ${d.nome || ''}`.trim() || d.nome,
      attiva: !!r.attiva, era_attiva: !!r.attiva, ore_giorno: r.ore_giorno ?? "", paga_oraria: r.paga_oraria ?? "",
      data_inizio: r.data_inizio || "", data_fine: r.data_fine || "" }; }));
    setShowRid(true);
  };
  const setRidRow = (i, k, v) => setRidRows(rs => rs.map((r, j) => j === i ? { ...r, [k]: v } : r));
  const salvaRid = async () => {
    await axios.post(`${API}/riduzioni-orario`, { voci: ridRows.map(r => ({ dipendente_id: r.dipendente_id, attiva: r.attiva, ore_giorno: r.ore_giorno, paga_oraria: r.paga_oraria, data_inizio: r.data_inizio || null, data_fine: r.data_fine || null })) });
    // Per chi viene ATTIVATO ora: genera il contratto di solidarietà → entra nell'iter firma
    const daGenerare = ridRows.filter(r => r.attiva && !r.era_attiva);
    let generati = 0; const falliti = [];
    for (const r of daGenerare) {
      try {
        await axios.post(`/hr/api/contracts/generate/${r.dipendente_id}`, { contract_type: "riduzione_orario",
          additional_data: { ore_giorno: r.ore_giorno, stipendio_orario: r.paga_oraria, ore_settimanali: r.ore_giorno ? String(Number(r.ore_giorno) * 6) : "", data_inizio: r.data_inizio, data_fine: r.data_fine } });
        generati++;
      } catch (e) { falliti.push(r.nome + (e?.response?.status === 400 ? " (manca il modello)" : "")); }
    }
    setShowRid(false); reload && reload();
    if (daGenerare.length) {
      toast(`Riduzione salvata. Contratti di solidarietà generati: ${generati}` +
        (falliti.length ? ` · non generati: ${falliti.join(", ")} → carica il modello "Accordo Riduzione Orario" in Assunzione → Modelli.` : ` · li trovi in Assunzione & Contratti.`));
    }
  };

  // Un solo elenco per contatori e filtri (prima "16 attivi" e "15 attivi" sulla stessa pagina).
  const attiviLista = dipendenti.filter(d => d.stato === "attivo");
  const cessatiLista = dipendenti.filter(d => d.stato !== "attivo");
  const filteredDipendenti = filter === "attivi" ? attiviLista : filter === "cessati" ? cessatiLista : dipendenti;

  const openModal = useCallback((dip = null) => {
    setPinNuovo("");
    if (dip) {
      setEditingDip(dip);
      const f = {};
      for (const k of CAMPI_FORM_DIP) f[k] = dip[k] ?? FORM_DIP_VUOTO[k];
      f.lotti_operatore = dip.lotti_operatore !== false;
      setFormData(f);
    } else {
      setEditingDip(null);
      setFormData(FORM_DIP_VUOTO);
    }
    setShowModal(true);
  }, []);

  // Link diretto dalla pagina Personale di Lotti: /hr/dipendenti/anagrafica?dip=<id>
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("dip");
    if (!id) return;
    const dip = dipendenti.find(d => d.id === id);
    if (dip) { openModal(dip); window.history.replaceState(null, "", window.location.pathname); }
  }, [dipendenti, openModal]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSalvando(true);
    try {
      const payload = { ...formData };
      if (payload.ore_settimanali === "" || payload.ore_settimanali === null) delete payload.ore_settimanali;
      if (editingDip) {
        const r = await axios.put(`${API}/dipendenti/${editingDip.id}`, payload);
        onDipendente ? onDipendente(r.data.dipendente) : reload();
        setEditingDip(r.data.dipendente);
        toast("Scheda salvata");
      } else {
        const r = await axios.post(`${API}/dipendenti`, payload);
        onDipendente ? onDipendente(r.data) : reload();
        toast("Dipendente creato");
      }
      setShowModal(false);
    } catch (error) {
      toast(error?.response?.data?.detail || "Errore nel salvataggio", "err");
    } finally { setSalvando(false); }
  };

  const handleDelete = async (dip) => {
    if (!window.confirm(`Eliminare definitivamente la scheda di ${dip.cognome} ${dip.nome}? Per una cessazione usa "Cessa rapporto".`)) return;
    try {
      await axios.delete(`${API}/dipendenti/${dip.id}`);
      onDipendente ? onDipendente(dip, { rimosso: true }) : reload();
    } catch (e) { toast(e?.response?.data?.detail || "Errore eliminazione", "err"); }
  };

  const apriCessazione = (dip) => setCessa({ dip, data: oggiISO, motivo: "dimissioni", riferimento: dip?.dimissioni?.codice_modulo || "", note: "" });
  const confermaCessazione = async () => {
    if (!cessa?.data) { toast("Inserisci la data di fine rapporto", "err"); return; }
    setCessaBusy(true);
    try {
      const r = await axios.post(`${API}/dipendenti/${cessa.dip.id}/cessa`, {
        data_cessazione: cessa.data, motivo: cessa.motivo, riferimento: cessa.riferimento, note: cessa.note,
      });
      onDipendente ? onDipendente(r.data.dipendente) : reload();
      const az = (r.data.automazioni || []).map(a => a.handler || a.error).filter(Boolean);
      toast(`Rapporto cessato dal ${formatDate(cessa.data)}${az.length ? ` · automazioni: ${az.join(", ")}` : ""}. Lotti si aggiorna da solo.`);
      setCessa(null);
    } catch (e) { toast(e?.response?.data?.detail || "Errore cessazione", "err"); }
    finally { setCessaBusy(false); }
  };

  const riattiva = async (dip) => {
    if (!window.confirm(`Rimettere in forza ${dip.cognome} ${dip.nome}? La cessazione del ${formatDate(dip.data_fine_rapporto)} resta nello storico.`)) return;
    try {
      const r = await axios.post(`${API}/dipendenti/${dip.id}/riattiva`);
      onDipendente ? onDipendente(r.data.dipendente) : reload();
      toast("Rapporto riattivato");
    } catch (e) { toast(e?.response?.data?.detail || "Errore riattivazione", "err"); }
  };

  const salvaPin = async () => {
    const pin = pinNuovo.trim();
    if (!/^\d{4,8}$/.test(pin)) { toast("PIN di 4-8 cifre", "err"); return; }
    setPinBusy(true);
    try {
      await axios.post(`${API}/dipendenti/${editingDip.id}/pin`, { pin });
      const agg = { ...editingDip, pin_impostato: true };
      setEditingDip(agg); onDipendente && onDipendente(agg); setPinNuovo("");
      toast("PIN impostato: vale per il portale e per firmare in Lotti");
    } catch (e) { toast(e?.response?.data?.detail || "PIN non salvato", "err"); }
    finally { setPinBusy(false); }
  };
  const togliPin = async () => {
    if (!window.confirm("Togliere il PIN? La persona non potrà più entrare nel portale né firmare in Lotti finché non ne riceve uno nuovo.")) return;
    setPinBusy(true);
    try {
      await axios.delete(`${API}/dipendenti/${editingDip.id}/pin`);
      const agg = { ...editingDip, pin_impostato: false };
      setEditingDip(agg); onDipendente && onDipendente(agg);
      toast("PIN rimosso");
    } catch (e) { toast(e?.response?.data?.detail || "Errore", "err"); }
    finally { setPinBusy(false); }
  };

  const StatoCell = ({ dip }) => dip.stato === "attivo"
    ? <Badge variant="success">attivo</Badge>
    : <span>
        <Badge variant="default">cessato{dip.data_fine_rapporto ? ` dal ${formatDate(dip.data_fine_rapporto)}` : ""}</Badge>
        <div className="dc-muted" style={{ fontSize: 11, marginTop: 3 }}>
          {dip.motivo_cessazione_etichetta || (dip.data_fine_rapporto ? "" : "data da inserire")}
          {dip.riferimento_cessazione ? ` · rif. ${dip.riferimento_cessazione}` : ""}
        </div>
      </span>;

  return (
    <div className="dc-page">
      <div className="dc-page-header">
        <div>
          <h1>Anagrafica Dipendenti</h1>
          <p>{attiviLista.length} in forza · {cessatiLista.length} cessati · fonte unica anche per Lotti</p>
        </div>
        <div className="dc-page-actions">
          <select value={filter} onChange={(e) => setFilter(e.target.value)} className="dc-select">
            <option value="attivi">In forza ({attiviLista.length})</option>
            <option value="cessati">Cessati ({cessatiLista.length})</option>
            <option value="tutti">Tutti ({dipendenti.length})</option>
          </select>
          <input ref={anagRef} type="file" accept=".xlsx" onChange={handleImportAnagrafica} style={{ display: "none" }} />
          <button onClick={() => anagRef.current?.click()} disabled={anagBusy} className="dc-btn" title="Importa/aggiorna l'anagrafica da Excel (Cognome, Nome, CF, …)">
            {anagBusy ? "Importo…" : "📥 Importa anagrafica (Excel)"}
          </button>
          <button onClick={apriRid} className="dc-btn" title="Riduzione oraria collettiva: ore/giorno, paga oraria e scadenza sorvegliata">
            ⏱️ Riduzione orario
          </button>
          <button onClick={() => openModal()} className="dc-btn dc-btn-primary" data-testid="add-dipendente">
            <Plus size={18} /> Nuovo Dipendente
          </button>
        </div>
      </div>

      <div className="dc-card">
        <table className="dc-table dc-table--cards">
          <thead>
            <tr>
              <th>DIPENDENTE</th>
              <th>RUOLO</th>
              <th>CONTRATTO</th>
              <th>STATO</th>
              <th>PIN · LOTTI</th>
              <th>AZIONI</th>
            </tr>
          </thead>
          <tbody>
            {filteredDipendenti.map((dip) => (
              <tr key={dip.id}>
                <td>
                  <div className="dc-table-user">
                    <Avatar nome={dip.nome} cognome={dip.cognome} size="sm" />
                    <div>
                      <span className="dc-table-name">{dip.cognome} {dip.nome}</span>
                      <span className="dc-table-email">{dip.email || dip.codice_fiscale || "—"}</span>
                    </div>
                  </div>
                </td>
                <td data-label="Ruolo">{dip.ruolo || "-"}</td>
                <td data-label="Contratto">{dip.contratto || "-"}{dip.data_assunzione ? <div className="dc-muted" style={{ fontSize: 11 }}>dal {formatDate(dip.data_assunzione)}</div> : null}</td>
                <td data-label="Stato"><StatoCell dip={dip} /></td>
                <td data-label="PIN · Lotti" style={{ fontSize: 12 }}>
                  {dip.stato !== "attivo" ? <span className="dc-muted">PIN disattivato</span>
                    : dip.pin_impostato ? <Badge variant="success">PIN ok</Badge> : <Badge variant="warning">PIN da impostare</Badge>}
                  <div className="dc-muted" style={{ fontSize: 11, marginTop: 3 }}>{dip.lotti_operatore === false ? "non firma in Lotti" : "operatore Lotti"}</div>
                </td>
                <td data-label="Azioni" className="dc-table-actions">
                  <button onClick={() => openModal(dip)} className="dc-btn-icon" title="Modifica scheda" aria-label={`Modifica scheda di ${dip.cognome} ${dip.nome}`}><Edit2 size={16} /></button>
                  {dip.stato === "attivo"
                    ? <button onClick={() => apriCessazione(dip)} className="dc-btn-icon" title="Cessa rapporto (chiede data e motivo)" aria-label={`Cessa rapporto di ${dip.cognome} ${dip.nome}`}><LogOut size={16} /></button>
                    : <button onClick={() => riattiva(dip)} className="dc-btn-icon" title="Riattiva rapporto" aria-label={`Riattiva rapporto di ${dip.cognome} ${dip.nome}`}><RefreshCw size={16} /></button>}
                  <button onClick={() => handleDelete(dip)} className="dc-btn-icon dc-btn-danger" title="Elimina scheda (non e' una cessazione)" aria-label={`Elimina scheda di ${dip.cognome} ${dip.nome}`}><Trash2 size={16} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Modale scheda */}
      {showModal && (
        <Modal large title={editingDip ? "Modifica Dipendente" : "Nuovo Dipendente"} onClose={() => setShowModal(false)}>
            <form onSubmit={handleSubmit} className="dc-modal-body">
              {editingDip && (
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
                  <span className="dc-muted" style={{ fontSize: 13 }}>Stato:</span>
                  <StatoCell dip={editingDip} />
                  {editingDip.stato === "attivo"
                    ? <button type="button" className="dc-btn" onClick={() => { setShowModal(false); apriCessazione(editingDip); }}><LogOut size={14} /> Cessa rapporto…</button>
                    : <button type="button" className="dc-btn" onClick={() => { setShowModal(false); riattiva(editingDip); }}><RefreshCw size={14} /> Riattiva</button>}
                  <span className="dc-muted" style={{ fontSize: 11 }}>Lo stato cambia solo da qui, con data e motivo: il salvataggio della scheda non lo tocca.</span>
                </div>
              )}
              <div className="dc-form-grid">
                <label className="dc-form-group">
                  <span className="dc-label">Nome *</span>
                  <input required value={formData.nome} onChange={(e) => setFormData({...formData, nome: e.target.value})} />
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">Cognome *</span>
                  <input required value={formData.cognome} onChange={(e) => setFormData({...formData, cognome: e.target.value})} />
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">Codice Fiscale</span>
                  <input value={formData.codice_fiscale} onChange={(e) => setFormData({...formData, codice_fiscale: e.target.value.toUpperCase()})} />
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">Matricola</span>
                  <input value={formData.matricola} onChange={(e) => setFormData({...formData, matricola: e.target.value})} />
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">Data di nascita</span>
                  <input type="date" value={formData.data_nascita} onChange={(e) => setFormData({...formData, data_nascita: e.target.value})} />
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">Data assunzione</span>
                  <input type="date" value={formData.data_assunzione} onChange={(e) => setFormData({...formData, data_assunzione: e.target.value})} />
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">Email</span>
                  <input type="email" value={formData.email} onChange={(e) => setFormData({...formData, email: e.target.value})} />
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">Telefono</span>
                  <input value={formData.telefono} onChange={(e) => setFormData({...formData, telefono: e.target.value})} />
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">Indirizzo</span>
                  <input value={formData.indirizzo} onChange={(e) => setFormData({...formData, indirizzo: e.target.value})} />
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">Ruolo / qualifica</span>
                  <input value={formData.ruolo} onChange={(e) => setFormData({...formData, ruolo: e.target.value})} placeholder="es. barista, cameriere di bar, pasticciere" />
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">Livello</span>
                  <input value={formData.livello} onChange={(e) => setFormData({...formData, livello: e.target.value})} />
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">Ore settimanali</span>
                  <input type="number" min="0" max="60" step="0.5" value={formData.ore_settimanali ?? ""} onChange={(e) => setFormData({...formData, ore_settimanali: e.target.value})} />
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">Contratto</span>
                  <select value={formData.contratto || ""} onChange={(e) => setFormData({...formData, contratto: e.target.value})}>
                    <option value="">— non indicato —</option>
                    <option>Indeterminato</option>
                    <option>Determinato</option>
                    <option>Part-time</option>
                    <option>Apprendistato</option>
                  </select>
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">IBAN</span>
                  <input value={formData.iban} onChange={(e) => setFormData({...formData, iban: e.target.value.toUpperCase()})} />
                </label>
                <div className="dc-form-group">
                  <span className="dc-label">Lotti (HACCP)</span>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 400 }}>
                    <input type="checkbox" checked={formData.lotti_operatore !== false} onChange={(e) => setFormData({...formData, lotti_operatore: e.target.checked})} />
                    Operatore in Lotti (firma lotti, sanificazioni, temperature)
                  </label>
                </div>
              </div>

              {editingDip && (
                <div className="dc-card" style={{ marginTop: 12, background: "#faf7f0" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <b>PIN personale</b>
                    {editingDip.pin_impostato ? <Badge variant="success">impostato</Badge> : <Badge variant="warning">da impostare</Badge>}
                    <span className="dc-muted" style={{ fontSize: 12 }}>Uno per persona: portale dipendente e tablet Lotti. Non e' mai visibile; qui si puo' solo reimpostare.</span>
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 8 }}>
                    <input className="dc-input" inputMode="numeric" placeholder="nuovo PIN (4-8 cifre)" value={pinNuovo}
                      onChange={(e) => setPinNuovo(e.target.value.replace(/\D/g, ""))} style={{ width: 200 }} />
                    <button type="button" className="dc-btn dc-btn-primary" onClick={salvaPin} disabled={pinBusy || editingDip.stato !== "attivo"}>
                      {pinBusy ? "…" : editingDip.pin_impostato ? "Reimposta PIN" : "Imposta PIN"}
                    </button>
                    {editingDip.pin_impostato && <button type="button" className="dc-btn" onClick={togliPin} disabled={pinBusy}>Togli PIN</button>}
                    {editingDip.stato !== "attivo" && <span className="dc-muted" style={{ fontSize: 12 }}>rapporto cessato: PIN disattivato</span>}
                  </div>
                </div>
              )}

              <div className="dc-modal-footer">
                <button type="button" onClick={() => setShowModal(false)} className="dc-btn">Annulla</button>
                <button type="submit" className="dc-btn dc-btn-primary" disabled={salvando}>{salvando ? "Salvo…" : editingDip ? "Salva scheda" : "Crea"}</button>
              </div>
            </form>
        </Modal>
      )}

      {/* Modale cessazione */}
      {cessa && (
        <Modal title={`Cessa rapporto · ${cessa.dip.cognome} ${cessa.dip.nome}`} onClose={() => !cessaBusy && setCessa(null)}>
            <div className="dc-modal-body">
              <div className="dc-form-grid">
                <label className="dc-form-group">
                  <span className="dc-label">Data di fine rapporto *</span>
                  <input type="date" value={cessa.data} onChange={(e) => setCessa({ ...cessa, data: e.target.value })} />
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">Motivo *</span>
                  <select value={cessa.motivo} onChange={(e) => setCessa({ ...cessa, motivo: e.target.value })}>
                    {MOTIVI_CESSAZIONE.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">Riferimento (numero modulo dimissioni / protocollo UNILAV)</span>
                  <input value={cessa.riferimento} onChange={(e) => setCessa({ ...cessa, riferimento: e.target.value })} />
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">Note</span>
                  <input value={cessa.note} onChange={(e) => setCessa({ ...cessa, note: e.target.value })} />
                </label>
              </div>
              <p className="dc-muted" style={{ fontSize: 12 }}>
                Effetti: PIN disattivato, contratti terminati, richieste future rifiutate, partite aperte chiuse; su Lotti la persona passa in «Non più in carico» entro 10 minuti.
              </p>
              <div className="dc-modal-footer">
                <button type="button" onClick={() => setCessa(null)} className="dc-btn" disabled={cessaBusy}>Annulla</button>
                <button type="button" onClick={confermaCessazione} className="dc-btn dc-btn-primary" disabled={cessaBusy}>{cessaBusy ? "…" : "Conferma cessazione"}</button>
              </div>
            </div>
        </Modal>
      )}

      {showRid && (
        <Modal wide title="Riduzione oraria collettiva" onClose={() => setShowRid(false)}>
          <div className="dc-modal-body">
            <p className="dc-muted" style={{ fontSize: 13, marginTop: 0 }}>Per ogni dipendente: spunta <b>Attiva</b>, imposta le <b>ore/giorno</b> ridotte, l'eventuale <b>paga oraria</b> e le date <b>dal/al</b>. <b>All'attivazione il sistema genera il contratto di solidarietà</b> che entra nell'iter firma (lo trovi in Assunzione &amp; Contratti → firma/invio → archiviazione nel fascicolo e nei documenti del dipendente). Il sistema sorveglia la <b>scadenza</b>: rossa se scaduta, arancione entro 30 giorni.</p>
            <div style={{ maxHeight: "62vh", overflow: "auto" }}>
              <table className="dc-table" style={{ minWidth: 800, whiteSpace: "nowrap" }}>
                <thead><tr><th>Dipendente</th><th>Attiva</th><th>Ore/giorno</th><th>Paga oraria €</th><th>Dal</th><th>Al (scadenza)</th><th>Stato</th></tr></thead>
                <tbody>
                  {ridRows.map((r, i) => {
                    const scaduta = r.attiva && r.data_fine && r.data_fine < oggiISO;
                    const vicina = r.attiva && r.data_fine && r.data_fine >= oggiISO && (new Date(r.data_fine) - new Date(oggiISO)) / 86400000 <= 30;
                    return (
                      <tr key={r.dipendente_id}>
                        <td>{r.nome}</td>
                        <td style={{ textAlign: "center" }}><input type="checkbox" checked={r.attiva} aria-label={`Attiva riduzione per ${r.nome}`} onChange={e => setRidRow(i, "attiva", e.target.checked)} /></td>
                        <td><input className="dc-input" style={{ width: 70 }} type="number" min="0" max="24" step="0.5" aria-label={`Ore al giorno di ${r.nome}`} value={r.ore_giorno} onChange={e => setRidRow(i, "ore_giorno", e.target.value)} /></td>
                        <td><input className="dc-input" style={{ width: 84 }} type="number" min="0" step="0.01" aria-label={`Paga oraria di ${r.nome}`} value={r.paga_oraria} onChange={e => setRidRow(i, "paga_oraria", e.target.value)} /></td>
                        <td><input className="dc-input" type="date" aria-label={`Riduzione dal, ${r.nome}`} value={r.data_inizio} onChange={e => setRidRow(i, "data_inizio", e.target.value)} /></td>
                        <td><input className="dc-input" type="date" aria-label={`Riduzione fino al, ${r.nome}`} value={r.data_fine} onChange={e => setRidRow(i, "data_fine", e.target.value)} /></td>
                        <td>{!r.attiva ? <span className="dc-muted">—</span> : scaduta ? <Badge variant="danger">scaduta</Badge> : vicina ? <Badge variant="warning">in scadenza</Badge> : <Badge variant="success">attiva</Badge>}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
              <button className="dc-btn" onClick={() => setShowRid(false)}>Chiudi</button>
              <button className="dc-btn-primary" onClick={salvaRid}>Salva</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

// Presenze Page - Calendario Mensile
function PresenzePage({ dipendenti, reload }) {
  const [anno, setAnno] = useState(new Date().getFullYear());
  const [mese, setMese] = useState(new Date().getMonth() + 1);
  const [presenze, setPresenze] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState({
    dipendente_id: "", tipo: "P", data_inizio: "", data_fine: "", nota: "", protocollo: ""
  });
  const [penna, setPenna] = useState(null);
  const [tuttiMode, setTuttiMode] = useState(false);
  const paintingRef = useRef(false);
  const selRef = useRef(new Set());
  const [, setSelVer] = useState(0);
  const [invii, setInvii] = useState([]);
  const [ferieList, setFerieList] = useState([]);
  const [turniMese, setTurniMese] = useState([]);
  const [tipiTurno, setTipiTurno] = useState([]);

  const mesi = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno","Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"];
  const daysInMonth = new Date(anno, mese, 0).getDate();
  const firstDayOfWeek = new Date(anno, mese - 1, 1).getDay();

  const loadPresenze = async () => {
    try {
      const res = await axios.get(`${API}/presenze?anno=${anno}&mese=${mese}`);
      setPresenze(res.data || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { loadPresenze(); }, [anno, mese]);

  // Carica ferie, tipi turno e i turni delle settimane che toccano il mese (per derivare le presenze)
  useEffect(() => {
    axios.get(`${API}/ferie`).then(r => setFerieList(r.data || [])).catch(() => {});
    axios.get(`${API}/turni`).then(r => setTipiTurno(r.data || [])).catch(() => {});
    const isoD = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const lunSet = new Set();
    for (let g = 1; g <= daysInMonth; g++) {
      const dt = new Date(anno, mese - 1, g); const off = (dt.getDay() + 6) % 7;
      const lun = new Date(dt); lun.setDate(dt.getDate() - off); lunSet.add(isoD(lun));
    }
    Promise.all([...lunSet].map(s => axios.get(`${API}/assegnazioni-turni?settimana=${s}`).then(r => r.data || []).catch(() => [])))
      .then(arrs => setTurniMese(arrs.flat()));
  }, [anno, mese]);

  const isoD = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const NOMI_G = ["Domenica", "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato"];
  const lunISOdi = (date) => { const off = (date.getDay() + 6) % 7; const l = new Date(date); l.setDate(date.getDate() - off); return isoD(l); };
  const ferieDi = (dipId, dateStr) => ferieList.find(f => f.dipendente_id === dipId && f.data_inizio <= dateStr && (f.data_fine || f.data_inizio) >= dateStr);
  const turnoDi = (dipId, date) => turniMese.find(a => a.dipendente_id === dipId && a.settimana === lunISOdi(date) && a.giorno === NOMI_G[date.getDay()]);
  const nomeTurnoId = (id) => (tipiTurno.find(t => t.id === id) || {}).nome;

  // Codice giustificativo derivato per una cella: presenza salvata > ferie/permesso > turno.
  // Regola: NON si può essere "presenti" in un giorno futuro (oggi compreso = ok).
  const codiceDerivato = (dipId, day) => {
    const date = new Date(anno, mese - 1, day);
    const dStr = isoD(date);
    const futuro = dStr > isoD(new Date());
    const pres = getPresenza(dipId, day);
    if (pres) {
      const g = pres.giustificativo;
      if (g === 'P' || (!g && pres.stato === 'presente')) return futuro ? null : 'P';
      if (g) return g;
      if (pres.stato === 'assente') return 'AS';
      return null;
    }
    const fer = ferieDi(dipId, dStr);
    if (fer) return fer.tipo === 'Permesso' ? 'PE' : fer.tipo === 'Malattia' ? 'M' : fer.tipo === 'ROL' ? 'R' : 'F';
    const t = turnoDi(dipId, date);
    if (t) { const n = nomeTurnoId(t.turno_id); if (n === 'Riposo') return 'RS'; if (n === 'Ferie') return 'F'; return (n && !futuro) ? 'P' : null; }
    return null;
  };

  const getPresenza = (dipId, day) => {
    const dataStr = `${anno}-${String(mese).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
    return presenze.find(p => p.dipendente_id === dipId && p.data === dataStr);
  };

  // Nota della cella (es. malattia → numero di protocollo del certificato medico).
  const notaDi = (dipId, day) => {
    const p = getPresenza(dipId, day);
    if (p && (p.note || p.nota)) return p.note || p.nota;
    const date = new Date(anno, mese - 1, day);
    const fer = ferieDi(dipId, isoD(date));
    return (fer && (fer.note || fer.protocollo)) || "";
  };

  // Riposi attesi nel mese = numero di domeniche (≈ una settimana di riposo a testa per settimana).
  const domenicheMese = (() => { let n = 0; for (let d = 1; d <= daysInMonth; d++) if (new Date(anno, mese - 1, d).getDay() === 0) n++; return n; })();
  // Conta solo i giorni di Riposo settimanale (RS): ferie e permessi NON contano.
  const contaRiposi = (dipId) => { let n = 0; for (let d = 1; d <= daysInMonth; d++) if (codiceDerivato(dipId, d) === 'RS') n++; return n; };

  // Pennello: applica il giustificativo selezionato a uno o tutti i dipendenti, in qualsiasi giorno.
  const applica = async (dipIds, day) => {
    if (!penna) return;
    const data = `${anno}-${String(mese).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
    const stato = penna === 'P' ? 'presente' : penna === 'AS' ? 'assente' : 'giustificato';
    const batch = dipIds.map(id => ({ dipendente_id: id, data, stato, giustificativo: penna }));
    try { await axios.post(`${API}/presenze/batch`, batch); await loadPresenze(); } catch (e) { console.error(e); }
  };

  const handleTuttiPresenti = async () => {
    if (!window.confirm("Segnare tutti come presenti per oggi?")) return;
    const oggi = isoD(new Date());  // data LOCALE (non UTC: evita l'errore di un giorno)
    const batch = dipendenti.map(d => ({
      dipendente_id: d.id,
      data: oggi,
      stato: "presente",
      entrata: "09:00",
      uscita: "18:00"
    }));
    await axios.post(`${API}/presenze/batch`, batch);
    loadPresenze();
  };

  const consolidaDaTurni = async () => {
    if (!window.confirm(`Consolidare le presenze di ${mesi[mese - 1]} ${anno} dai turni assegnati?\nVengono creati solo i giorni fino a oggi e non si tocca ciò che hai inserito a mano.`)) return;
    try {
      const r = await axios.post(`${API}/presenze/consolida-da-turni`, { anno, mese });
      await loadPresenze();
      toast(`Consolidate ${r.data.creati} presenze dai turni (${r.data.saltati} già presenti)`);
    } catch (e) { toast(e?.response?.data?.detail || "Errore consolidamento", "err"); }
  };

  // ---- Pennello con SELEZIONE A RETTANGOLO ----
  // Si sceglie un tipo, si preme su una casella e si trascina: la selezione e' il
  // rettangolo fra la casella di partenza e quella sotto il mouse, quindi copre
  // insieme piu' giorni E piu' dipendenti. Prima il trascinamento seguiva il
  // percorso del mouse: in diagonale lasciava buchi e per coprire un blocco
  // bisognava ripassare riga per riga.
  const keyCell = (dipId, day) => `${dipId}|${day}`;
  const ancoraRef = useRef(null);   // { riga, giorno } da cui parte il rettangolo

  // Celle del rettangolo fra l'ancora e la casella corrente.
  // Con "Applica a tutti" le righe non contano: si prendono tutti i dipendenti.
  const cellsForRect = (a, b) => {
    if (!a || !b) return [];
    const g1 = Math.min(a.giorno, b.giorno), g2 = Math.max(a.giorno, b.giorno);
    const righe = tuttiMode
      ? dipendenti
      : dipendenti.slice(Math.min(a.riga, b.riga), Math.max(a.riga, b.riga) + 1);
    const out = [];
    righe.forEach(d => { for (let g = g1; g <= g2; g++) out.push(keyCell(d.id, g)); });
    return out;
  };
  const cellsForDay = (dipId, day) => (tuttiMode ? dipendenti.map(d => keyCell(d.id, day)) : [keyCell(dipId, day)]);

  const startPaint = (riga, day, estendi = false) => {
    if (!penna) return;
    // shift+clic: chiude il rettangolo sull'ancora precedente senza trascinare.
    // Serve sui mesi lunghi, dove trascinare obbligherebbe a scorrere la tabella.
    if (estendi && ancoraRef.current) {
      const cells = cellsForRect(ancoraRef.current, { riga, giorno: day });
      applicaCelle(cells);
      return;
    }
    paintingRef.current = true;
    ancoraRef.current = { riga, giorno: day };
    selRef.current = new Set(cellsForRect(ancoraRef.current, ancoraRef.current));
    setSelVer(v => v + 1);
  };
  const extendPaint = (riga, day) => {
    if (!paintingRef.current || !ancoraRef.current) return;
    selRef.current = new Set(cellsForRect(ancoraRef.current, { riga, giorno: day }));
    setSelVer(v => v + 1);
  };
  const applicaCelle = async (cells) => {
    if (!penna || !cells.length) return;
    let note;
    if (penna === 'M') {
      const p = window.prompt("Numero di protocollo del certificato medico (facoltativo):", "");
      if (p && p.trim()) note = `Malattia · Protocollo INPS: ${p.trim()}`;
    }
    const stato = penna === 'P' ? 'presente' : penna === 'AS' ? 'assente' : 'giustificato';
    const batch = cells.map(k => { const [dipId, d] = k.split("|"); return { dipendente_id: dipId, data: `${anno}-${String(mese).padStart(2, '0')}-${String(d).padStart(2, '0')}`, stato, giustificativo: penna, ...(note ? { note } : {}) }; });
    try { await axios.post(`${API}/presenze/batch`, batch); await loadPresenze(); toast(`Applicato "${penna}" a ${cells.length} ${cells.length === 1 ? 'casella' : 'caselle'}`); }
    catch (e) { console.error(e); toast("Errore applicazione", "err"); }
  };
  const endPaint = () => {
    if (!paintingRef.current) return;
    paintingRef.current = false;
    const cells = Array.from(selRef.current);
    selRef.current = new Set();
    setSelVer(v => v + 1);
    if (cells.length) applicaCelle(cells);
  };
  const endPaintRef = useRef(endPaint);
  endPaintRef.current = endPaint;
  useEffect(() => {
    const h = () => endPaintRef.current && endPaintRef.current();
    window.addEventListener("mouseup", h);
    window.addEventListener("touchend", h);
    return () => { window.removeEventListener("mouseup", h); window.removeEventListener("touchend", h); };
  }, []);

  // ---- Esporta / stampa / invia il foglio del mese ----
  const buildRighe = () => ({
    giorni: daysInMonth,
    righe: dipendenti.map(dip => ({
      nome: `${dip.cognome || ''} ${dip.nome || ''}`.trim(),
      celle: Array.from({ length: daysInMonth }, (_, i) => codiceDerivato(dip.id, i + 1) || ""),
      // Nota di ogni giorno (es. protocollo INPS malattia): usata nel documento
      // "per il commercialista" (Opzione C) per annotare i periodi.
      note: Array.from({ length: daysInMonth }, (_, i) => notaDi(dip.id, i + 1) || ""),
    })),
  });
  const buildCSV = () => {
    const sep = ";";
    const { giorni, righe } = buildRighe();
    const intest = ["Dipendente", ...Array.from({ length: giorni }, (_, i) => String(i + 1))].join(sep);
    const body = righe.map(r => [r.nome, ...r.celle].join(sep));
    const legenda = "Legenda: P=Presente · AS=Assente · F=Ferie · PE=Permesso · M=Malattia · R=ROL · RS=Riposo · CH=Chiuso · FNL=Festivita non lav.";
    return [`Presenze ${mesi[mese - 1]} ${anno} - Ceraldi Group S.r.l.`, "", intest, ...body, "", legenda].join("\n");
  };
  const scaricaPresenze = () => {
    const csv = "﻿" + buildCSV();
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `presenze_${anno}_${String(mese).padStart(2, '0')}.csv`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
    toast("Foglio presenze scaricato (CSV)");
  };
  const scaricaPDF = async () => {
    try {
      const r = await axios.post(`${API}/presenze/pdf`, { anno, mese, ...buildRighe() }, { responseType: "blob" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(r.data);
      a.download = `presenze_${anno}_${String(mese).padStart(2, '0')}.pdf`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 10000);
      toast("PDF presenze scaricato");
    } catch (e) { toast("Errore generazione PDF", "err"); }
  };
  // Opzione C: documento "per il commercialista" — riepilogo totali + dettaglio periodi,
  // molto più leggero della griglia giorno-per-giorno (che resta per l'uso interno).
  const scaricaRiepilogoCommercialista = async () => {
    try {
      const r = await axios.post(`${API}/presenze/pdf-riepilogo`, { anno, mese, ...buildRighe() }, { responseType: "blob" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(r.data);
      a.download = `presenze_riepilogo_${anno}_${String(mese).padStart(2, '0')}.pdf`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 10000);
      toast("Riepilogo per il commercialista scaricato");
    } catch (e) { toast("Errore generazione riepilogo", "err"); }
  };
  // Anteprima Opzione C direttamente in pagina (stessi dati del PDF, senza scaricare nulla)
  const [previewC, setPreviewC] = useState(null);
  const [previewCBusy, setPreviewCBusy] = useState(false);
  const toggleAnteprimaC = async () => {
    if (previewC) { setPreviewC(null); return; }
    setPreviewCBusy(true);
    try {
      const r = await axios.post(`${API}/presenze/riepilogo-dati`, { anno, mese, ...buildRighe() });
      setPreviewC(r.data);
    } catch (e) { toast("Errore nel calcolo del riepilogo", "err"); }
    finally { setPreviewCBusy(false); }
  };
  const COLST = { P: "#3d8168", AS: "#d35f4e", F: "#5b7a6b", PE: "#7d5526", M: "#f59e0b", R: "#8a9a5b", RS: "#9aa593", CH: "#6b7669", FNL: "#a6724a", X: "#495247" };
  const stampaPresenze = () => {
    const { giorni, righe } = buildRighe();
    const th = Array.from({ length: giorni }, (_, i) => `<th>${i + 1}</th>`).join("");
    const rows = righe.map(r => `<tr><td class="nm">${r.nome}</td>${r.celle.map(c => `<td style="background:${COLST[c] || '#fff'};color:${c ? '#fff' : '#000'}">${c || ''}</td>`).join("")}</tr>`).join("");
    const html = `<!doctype html><html><head><meta charset="utf-8"><title>Presenze ${mesi[mese - 1]} ${anno}</title>
      <style>@page{size:A4 landscape;margin:8mm} body{font-family:Arial,sans-serif;margin:0}
      h2{margin:0 0 6px;font-size:14px} table{border-collapse:collapse;width:100%;table-layout:fixed}
      th,td{border:1px solid #ccc;text-align:center;font-size:8px;padding:1px;overflow:hidden}
      td.nm,th.nm{text-align:left;width:110px;font-size:8px;padding:2px 4px;overflow:hidden;white-space:nowrap}
      thead th{background:#eee}</style></head>
      <body onload="setTimeout(function(){window.print()},250)"><h2>Presenze ${mesi[mese - 1]} ${anno} — Ceraldi Group S.r.l.</h2>
      <table><thead><tr><th class="nm">Dipendente</th>${th}</tr></thead><tbody>${rows}</tbody></table>
      <p style="font-size:8px;color:#555;margin-top:6px">Legenda: P=Presente · AS=Assente · F=Ferie · PE=Permesso · M=Malattia · R=ROL · RS=Riposo · CH=Chiuso · FNL=Festività non lav.</p>
      </body></html>`;
    const w = window.open("", "_blank");
    if (w) { w.document.write(html); w.document.close(); } else toast("Consenti i popup per stampare", "err");
  };
  // Email del commercialista: salvata in app (non nel browser) — "Invia" la
  // usa sempre in automatico, senza richiederla ogni volta.
  const [emailCommercialista, setEmailCommercialista] = useState(null); // null = non ancora caricata
  const caricaEmailCommercialista = async () => {
    try { const r = await axios.get(`${API}/presenze/email-commercialista`); setEmailCommercialista(r.data.email || ""); }
    catch { setEmailCommercialista(""); }
  };
  useEffect(() => { caricaEmailCommercialista(); }, []);
  const cambiaEmailCommercialista = async () => {
    const email = window.prompt("Email del commercialista (usata per tutti i prossimi invii):", emailCommercialista || "");
    if (email === null) return;
    try {
      await axios.post(`${API}/presenze/email-commercialista`, { email: email.trim() || null });
      setEmailCommercialista(email.trim());
      toast(email.trim() ? "Email commercialista salvata" : "Email commercialista rimossa");
    } catch { toast("Errore nel salvataggio dell'email", "err"); }
  };
  const inviaCommercialista = async () => {
    if (!emailCommercialista) {
      toast("Imposta prima l'email del commercialista (✎ accanto a Invia)", "err");
      return;
    }
    try {
      const r = await axios.post(`${API}/presenze/invia-commercialista`, { anno, mese, ...buildRighe() });
      toast(`Presenze inviate a ${r.data.destinatario}`);
      loadInvii();
    } catch (e) { toast(e?.response?.data?.detail || "Invio non riuscito (SMTP da configurare su Render)", "err"); }
  };
  const loadInvii = async () => {
    try { const r = await axios.get(`${API}/presenze/invii?anno=${anno}&mese=${mese}`); setInvii(r.data.invii || []); } catch { setInvii([]); }
  };
  useEffect(() => { loadInvii(); }, [anno, mese]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    // Create presenze for date range
    const start = new Date(formData.data_inizio);
    const end = new Date(formData.data_fine);
    const batch = [];
    
    // Per la malattia il numero di protocollo del certificato medico finisce nella nota.
    const notaFinale = (formData.tipo === 'M' && formData.protocollo)
      ? `Malattia · Protocollo INPS: ${formData.protocollo}${formData.nota ? ' · ' + formData.nota : ''}`
      : formData.nota;
    for (let d = start; d <= end; d.setDate(d.getDate() + 1)) {
      batch.push({
        dipendente_id: formData.dipendente_id,
        data: isoD(d),  // data LOCALE (non UTC)
        stato: formData.tipo === 'P' ? 'presente' : formData.tipo === 'AS' ? 'assente' : 'giustificato',
        giustificativo: formData.tipo,
        note: notaFinale
      });
    }
    
    await axios.post(`${API}/presenze/batch`, batch);
    setShowModal(false);
    loadPresenze();
  };

  const tipiGiustificativo = [
    { code: "P", label: "Presente", color: "#10b981" },
    { code: "AS", label: "Assente", color: "#ef4444" },
    { code: "F", label: "Ferie", color: "#5b7a6b" },
    { code: "PE", label: "Permesso", color: "#7d5526" },
    { code: "M", label: "Malattia", color: "#f59e0b" },
    { code: "R", label: "ROL", color: "#8a9a5b" },
    { code: "CH", label: "Chiuso", color: "#6b7669" },
    { code: "RS", label: "Riposo Sett.", color: "#9aa593" },
    { code: "X", label: "Cessato", color: "#495247" },
    { code: "FNL", label: "Festività Non Lav.", color: "#a6724a" },
  ];

  // Calcola statistiche
  const totalePresenti = presenze.filter(p => p.stato === 'presente').length;
  const totaleAssenti = presenze.filter(p => p.stato === 'assente').length;

  // Malattie del mese: raggruppa i giorni 'M' per dipendente in periodi, con protocollo.
  const estraiProtocollo = (note) => {
    if (!note) return "";
    const m = String(note).match(/protocollo[^0-9A-Za-z]*([0-9A-Za-z.\/-]{5,})/i);
    return m ? m[1] : "";
  };
  const malattieMese = (() => {
    const pref = `${anno}-${String(mese).padStart(2, '0')}`;
    const perDip = {};
    presenze.forEach(p => {
      if (p.giustificativo === 'M' && typeof p.data === 'string' && p.data.startsWith(pref))
        (perDip[p.dipendente_id] = perDip[p.dipendente_id] || []).push({ day: Number(p.data.slice(8, 10)), note: p.note || p.nota || "" });
    });
    const out = [];
    Object.entries(perDip).forEach(([dipId, arr]) => {
      arr.sort((a, b) => a.day - b.day);
      let start = null, prev = null, nota = "";
      arr.forEach((x, i) => {
        if (start === null) { start = x.day; nota = x.note; }
        else if (x.day !== prev + 1) { out.push({ dipId, dal: start, al: prev, nota }); start = x.day; nota = x.note; }
        if (x.note && !nota) nota = x.note;
        prev = x.day;
        if (i === arr.length - 1) out.push({ dipId, dal: start, al: prev, nota });
      });
    });
    return out.sort((a, b) => a.dal - b.dal);
  })();
  const nomeDip = (id) => { const d = dipendenti.find(x => x.id === id); return d ? `${d.cognome || ''} ${d.nome || ''}`.trim() : id; };

  const prevMonth = () => {
    if (mese === 1) { setMese(12); setAnno(anno - 1); }
    else setMese(mese - 1);
  };
  const nextMonth = () => {
    if (mese === 12) { setMese(1); setAnno(anno + 1); }
    else setMese(mese + 1);
  };

  return (
    <div className="dc-page">
      <div className="dc-page-header">
        <div>
          <h1>Presenze Mensili</h1>
          <p>{dipendenti.length} dipendenti attivi</p>
        </div>
      </div>

      {/* Stats Row */}
      <div className="dc-presenze-stats">
        <div className="dc-presenze-stat">
          <span className="dc-presenze-stat-label">PRESENTI</span>
          <span className="dc-presenze-stat-value dc-text-green">{totalePresenti}</span>
        </div>
        <div className="dc-presenze-stat">
          <span className="dc-presenze-stat-label">ASSENTI</span>
          <span className="dc-presenze-stat-value dc-text-red">{totaleAssenti}</span>
        </div>
        <div className="dc-presenze-stat">
          <span className="dc-presenze-stat-label">ROL</span>
          <span className="dc-presenze-stat-value dc-text-red">0</span>
        </div>
        <div className="dc-presenze-stat">
          <span className="dc-presenze-stat-label">ALTRI</span>
          <span className="dc-presenze-stat-value">0</span>
        </div>

        {/* Month Navigation */}
        <div className="dc-month-nav">
          <button onClick={prevMonth} className="dc-btn-icon" aria-label="Mese precedente"><ChevronLeft size={20} /></button>
          <span className="dc-month-label">{mesi[mese - 1]} {anno}</span>
          <button onClick={nextMonth} className="dc-btn-icon" aria-label="Mese successivo"><ChevronRight size={20} /></button>
        </div>

        {/* Action Buttons */}
        <button onClick={handleTuttiPresenti} className="dc-btn dc-btn-success">
          <Check size={16} /> Tutti Presenti
        </button>
        <button onClick={consolidaDaTurni} className="dc-btn" title="Crea le presenze dei giorni passati a partire dai turni assegnati (non sovrascrive il manuale)">
          <RefreshCw size={16} /> Consolida da turni
        </button>
        <button onClick={scaricaPDF} className="dc-btn" title="Scarica il PDF del mese (una pagina, pulito e stampabile)">
          <Download size={16} /> PDF
        </button>
        <button onClick={scaricaPresenze} className="dc-btn" title="Scarica in Excel/CSV">
          <Download size={16} /> CSV
        </button>
        <button onClick={stampaPresenze} className="dc-btn" title="Stampa su una sola pagina (o salva come PDF dalla finestra di stampa)">
          🖨 Stampa
        </button>
        <button onClick={toggleAnteprimaC} disabled={previewCBusy} className="dc-btn" title="Vedi qui il riepilogo per il commercialista, senza scaricare nulla">
          👁 {previewC ? "Nascondi" : "Vedi"} Opzione C
        </button>
        <button onClick={scaricaRiepilogoCommercialista} className="dc-btn" title="Documento leggero per il commercialista: riepilogo totali per dipendente + dettaglio dei periodi di assenza con le date (niente griglia giorno-per-giorno)">
          📄 Riepilogo per commercialista
        </button>
        <button onClick={inviaCommercialista} className="dc-btn dc-btn-primary"
          title={emailCommercialista ? `Invia a ${emailCommercialista}` : "Imposta prima l'email del commercialista"}>
          <Send size={16} /> Invia
        </button>
        <button onClick={cambiaEmailCommercialista} className="dc-btn" style={{ padding: "9px 10px" }}
          title={emailCommercialista ? `Destinatario: ${emailCommercialista} — clicca per cambiarlo` : "Imposta l'email del commercialista"}>
          ✎ {emailCommercialista || "imposta email"}
        </button>
      </div>

      {previewC && (
        <div className="dc-card" style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
            <h3 style={{ margin: 0 }}>Opzione C — riepilogo per il commercialista ({mesi[mese - 1]} {anno})</h3>
            <button onClick={scaricaRiepilogoCommercialista} className="dc-btn dc-btn-primary" style={{ padding: "8px 14px" }}>
              <Download size={15} /> Scarica PDF
            </button>
          </div>
          <div className="dc-scroll-x" style={{ marginTop: 12 }}>
            <table className="dc-table" style={{ fontSize: 13 }}>
              <thead><tr>
                <th>Dipendente</th><th style={{ textAlign: "right" }}>Lav.</th><th style={{ textAlign: "right" }}>Ferie</th>
                <th style={{ textAlign: "right" }}>Perm.</th><th style={{ textAlign: "right" }}>Malat.</th>
                <th style={{ textAlign: "right" }}>ROL</th><th style={{ textAlign: "right" }}>Riposi</th>
                <th style={{ textAlign: "right" }}>Altro</th><th style={{ textAlign: "right" }}>Tot.</th>
              </tr></thead>
              <tbody>
                {previewC.righe.map(r => (
                  <tr key={r.nome}>
                    <td style={{ fontWeight: 600 }}>{r.nome}</td>
                    <td style={{ textAlign: "right" }}>{r.lav}</td><td style={{ textAlign: "right" }}>{r.ferie}</td>
                    <td style={{ textAlign: "right" }}>{r.perm}</td><td style={{ textAlign: "right" }}>{r.malat}</td>
                    <td style={{ textAlign: "right" }}>{r.rol}</td><td style={{ textAlign: "right" }}>{r.riposi}</td>
                    <td style={{ textAlign: "right" }}>{r.altro}</td><td style={{ textAlign: "right", fontWeight: 700 }}>{r.tot}</td>
                  </tr>
                ))}
                <tr style={{ fontWeight: 700, borderTop: "2px solid #e6e0d4", background: "#eef1ea" }}>
                  <td>Totale azienda</td>
                  <td style={{ textAlign: "right" }}>{previewC.totali.lav}</td><td style={{ textAlign: "right" }}>{previewC.totali.ferie}</td>
                  <td style={{ textAlign: "right" }}>{previewC.totali.perm}</td><td style={{ textAlign: "right" }}>{previewC.totali.malat}</td>
                  <td style={{ textAlign: "right" }}>{previewC.totali.rol}</td><td style={{ textAlign: "right" }}>{previewC.totali.riposi}</td>
                  <td style={{ textAlign: "right" }}>{previewC.totali.altro}</td><td style={{ textAlign: "right" }}>{previewC.totali.tot}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <h4 style={{ marginTop: 18, marginBottom: 4 }}>Dettaglio dei periodi</h4>
          <p className="dc-muted" style={{ fontSize: 12, marginTop: 0 }}>Il riposo settimanale non compare: è regolare e non richiede annotazione.</p>
          {previewC.periodi.length === 0 ? (
            <p className="dc-muted">Nessuna assenza da segnalare questo mese.</p>
          ) : previewC.periodi.map(p => (
            <div key={p.nome} style={{ marginBottom: 10 }}>
              <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>{p.nome}</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {p.eventi.map((e, i) => {
                  const tipo = tipiGiustificativo.find(t => t.code === e.tipo);
                  const periodo = e.dal === e.al ? `${String(e.dal).padStart(2, "0")}` : `${String(e.dal).padStart(2, "0")}-${String(e.al).padStart(2, "0")}`;
                  return (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, padding: "5px 9px", borderRadius: 8, background: "#f6f3ea" }}>
                      <span style={{ width: 8, height: 8, borderRadius: "50%", background: tipo?.color || "#999", flex: "none" }} />
                      <b>{e.label}:</b> {periodo}/{String(mese).padStart(2, "0")} ({e.giorni} gg)
                      {e.nota && <span className="dc-muted" style={{ marginLeft: "auto" }}>{e.nota}</span>}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Barra pennello */}
      <div className="dc-card" style={{ marginBottom: 12, padding: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, color: "#6b7669", marginRight: 4 }}>Pennello:</span>
          {tipiGiustificativo.map(t => (
            <button key={t.code} type="button" onClick={() => setPenna(t.code)} title={t.label}
              style={{ border: penna === t.code ? "3px solid #5b7a6b" : "1px solid #e6e0d4", background: penna === t.code ? t.color : "#fff", color: penna === t.code ? "#fff" : "#495247", borderRadius: 8, padding: "6px 10px", fontWeight: 700, cursor: "pointer", fontSize: 13 }}>
              {t.code} <span style={{ fontWeight: 400, fontSize: 11 }}>{t.label}</span>
            </button>
          ))}
          <label style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, fontSize: 13, cursor: "pointer" }}>
            <input type="checkbox" checked={tuttiMode} onChange={e => setTuttiMode(e.target.checked)} />
            Applica a tutti i dipendenti
          </label>
        </div>
        <div style={{ fontSize: 12, color: "#9aa593", marginTop: 8 }}>
          Scegli un tipo, poi <b>tieni premuto e trascina</b>: si seleziona il <b>rettangolo</b> fra la casella di partenza e quella sotto il mouse, quindi più giorni e più dipendenti in una volta sola. In alternativa clicca la prima casella e fai <b>shift+clic</b> sull&apos;ultima. Un clic singolo applica una casella; il <b>numero del giorno</b> in cima lo applica a tutti. Per la Malattia chiede il numero di protocollo.
        </div>
        {selRef.current.size > 0 && (
          <div style={{ marginTop: 8, fontSize: 13, fontWeight: 700, color: "#3d8168" }}>
            {selRef.current.size} {selRef.current.size === 1 ? "casella selezionata" : "caselle selezionate"} — rilascia per applicare «{penna}»
          </div>
        )}
      </div>

      {/* Attendance Grid */}
      {/* Col pennello attivo il testo non si seleziona: trascinando sulle caselle
          il browser evidenziava i nomi dei dipendenti invece di disegnare. */}
      <div className="dc-card dc-presenze-grid-container"
        style={penna ? { userSelect: "none", WebkitUserSelect: "none" } : undefined}>
        <table className="dc-presenze-table">
          <thead>
            <tr>
              <th className="dc-presenze-th-name">Dipendente</th>
              {Array.from({length: daysInMonth}, (_, i) => {
                const date = new Date(anno, mese - 1, i + 1);
                const dayNames = ['D', 'L', 'M', 'M', 'G', 'V', 'S'];
                const isWeekend = date.getDay() === 0 || date.getDay() === 6;
                return (
                  <th key={i} className={`dc-presenze-th-day ${isWeekend ? 'weekend' : ''}`} onClick={() => applica(dipendenti.map(d => d.id), i + 1)} style={{ cursor: "pointer" }} title="Applica a tutti per questo giorno">
                    <span className="dc-day-name">{dayNames[date.getDay()]}</span>
                    <span className="dc-day-num">{i + 1}</span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {dipendenti.map((dip, rowIdx) => (
              <tr key={dip.id}>
                <td className="dc-presenze-td-name">
                  <div className="dc-table-user">
                    <Avatar nome={dip.nome} cognome={dip.cognome} size="sm" />
                    <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.25 }}>
                      <span>{dip.cognome ? `${dip.cognome} ${dip.nome?.[0] || ''}.` : dip.nome}</span>
                      {(() => { const r = contaRiposi(dip.id); const ok = r >= domenicheMese; return (
                        <span style={{ fontSize: 10, fontWeight: 700, color: ok ? "#3d8168" : "#d35f4e" }} title="Riposi del mese rispetto agli attesi">
                          {ok ? "✓" : "⚠"} {r}/{domenicheMese} riposi
                        </span>); })()}
                    </div>
                  </div>
                </td>
                {Array.from({length: daysInMonth}, (_, i) => {
                  const day = i + 1;
                  const date = new Date(anno, mese - 1, day);
                  const isWeekend = date.getDay() === 0 || date.getDay() === 6;
                  const salvata = getPresenza(dip.id, day);
                  const code = codiceDerivato(dip.id, day);
                  const tipo = tipiGiustificativo.find(t => t.code === code);
                  const dimmed = penna && code !== penna;
                  const nota = notaDi(dip.id, day);
                  const titolo = `${tipo?.label || code || ""}${nota ? ` — ${nota}` : ""}`.trim();
                  const inSel = selRef.current.has(keyCell(dip.id, day));
                  return (
                    <td key={i} className={`dc-presenze-td-day ${isWeekend ? 'weekend' : ''}`}
                      onMouseDown={(e) => { if (penna) { e.preventDefault(); startPaint(rowIdx, day, e.shiftKey); } }}
                      onMouseEnter={() => extendPaint(rowIdx, day)}
                      onTouchStart={() => { if (penna) applicaCelle(cellsForDay(dip.id, day)); }}
                      style={{ cursor: penna ? "cell" : "default", position: "relative", userSelect: "none",
                        outline: inSel ? "2px solid #5b7a6b" : "none", background: inSel ? "#e8efe9" : undefined }}
                      title={titolo || undefined}>
                      <button type="button" className="dc-cell-btn dc-cell-btn-presenza"
                        aria-label={`${dip.cognome} ${dip.nome || ""}, ${day}/${mese}: ${titolo || "nessuna presenza"}${penna ? ` — Invio applica ${penna}` : ""}`}
                        onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && penna) { e.preventDefault(); applicaCelle(cellsForDay(dip.id, day)); } }}>
                        {code ? (
                          <span className={`dc-presenza-badge${dimmed ? " dc-dimmed" : ""}`} style={{ backgroundColor: tipo?.color || '#3d8168', opacity: salvata ? 1 : 0.55 }}>
                            {code}
                            {nota ? <span title={nota} style={{ position: "absolute", top: 1, right: 2, width: 6, height: 6, borderRadius: "50%", background: "#b91c1c", border: "1px solid #fff" }} /> : null}
                          </span>
                        ) : (
                          <span className="dc-presenza-empty">-</span>
                        )}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 16px", marginTop: 12, paddingTop: 10, borderTop: "1px solid #e6e0d4" }}>
          <span className="dc-muted" style={{ fontSize: 12, fontWeight: 700 }}>Legenda:</span>
          {tipiGiustificativo.map(t => (
            <span key={t.code} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12 }}>
              <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 20, height: 18, borderRadius: 4, background: t.color, color: "#fff", fontWeight: 700, fontSize: 10.5 }}>{t.code}</span>
              <span className="dc-muted">{t.label}</span>
            </span>
          ))}
        </div>
      </div>

      {/* Malattie del mese */}
      <div className="dc-card" style={{ marginTop: 12 }}>
        <h3 style={{ margin: "0 0 10px" }}>🤒 Malattie del mese — {mesi[mese - 1]} {anno}</h3>
        {malattieMese.length === 0 ? (
          <p style={{ color: "#9aa593", margin: 0, fontSize: 14 }}>Nessuna malattia registrata in questo mese.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr style={{ textAlign: "left", color: "#6b7669", fontSize: 12, textTransform: "uppercase" }}>
                  <th style={{ padding: "6px 8px", borderBottom: "2px solid #e6e0d4" }}>Dipendente</th>
                  <th style={{ padding: "6px 8px", borderBottom: "2px solid #e6e0d4" }}>Periodo</th>
                  <th style={{ padding: "6px 8px", borderBottom: "2px solid #e6e0d4" }}>Giorni</th>
                  <th style={{ padding: "6px 8px", borderBottom: "2px solid #e6e0d4" }}>Protocollo</th>
                </tr>
              </thead>
              <tbody>
                {malattieMese.map((m, i) => {
                  const prot = estraiProtocollo(m.nota);
                  const gg = m.al - m.dal + 1;
                  const periodo = m.dal === m.al ? `${m.dal} ${mesi[mese - 1].slice(0, 3)}` : `${m.dal}–${m.al} ${mesi[mese - 1].slice(0, 3)}`;
                  return (
                    <tr key={i}>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #efe9dd", fontWeight: 600 }}>{nomeDip(m.dipId)}</td>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #efe9dd" }}>{periodo}</td>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #efe9dd" }}>{gg}</td>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #efe9dd" }}>
                        {prot ? <span style={{ fontFamily: "monospace", background: "#fdf6ec", border: "1px solid #f0e0c4", borderRadius: 6, padding: "2px 8px" }}>{prot}</span>
                          : <span style={{ color: "#d35f4e", fontSize: 12 }}>protocollo mancante</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Storico invii al commercialista */}
      <div className="dc-card" style={{ marginTop: 12 }}>
        <h3 style={{ margin: "0 0 10px" }}>📧 Invii al commercialista — {mesi[mese - 1]} {anno}</h3>
        {invii.length === 0 ? (
          <p style={{ color: "#9aa593", margin: 0, fontSize: 14 }}>Ancora nessun invio per questo mese.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr style={{ textAlign: "left", color: "#6b7669", fontSize: 12, textTransform: "uppercase" }}>
                  <th style={{ padding: "6px 8px", borderBottom: "2px solid #e6e0d4" }}>Data invio</th>
                  <th style={{ padding: "6px 8px", borderBottom: "2px solid #e6e0d4" }}>Destinatario</th>
                  <th style={{ padding: "6px 8px", borderBottom: "2px solid #e6e0d4" }}>Allegati</th>
                </tr>
              </thead>
              <tbody>
                {invii.map((v, i) => {
                  const d = v.data_invio ? new Date(v.data_invio) : null;
                  const dstr = d ? `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` : "—";
                  return (
                    <tr key={i}>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #efe9dd" }}>{dstr}</td>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #efe9dd", fontWeight: 600 }}>{v.destinatario}</td>
                      <td style={{ padding: "6px 8px", borderBottom: "1px solid #efe9dd", color: "#6b7669" }}>{v.con_pdf ? "PDF + CSV" : "CSV"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  );
}

// Ferie Page
function FeriePage({ dipendenti, ferie, reload, getDipendente }) {
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState({
    dipendente_id: "", tipo: "Ferie", data_inizio: "", data_fine: "", giorni: 1, nota: ""
  });
  const [mese, setMese] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });

  const TIPI = [
    { tipo: "Ferie", code: "F", color: "#5b7a6b" },
    { tipo: "Permesso", code: "PE", color: "#7d5526" },
  ];
  const ymd = (y, m, d) => `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  const giorniMese = new Date(mese.getFullYear(), mese.getMonth() + 1, 0).getDate();
  const meseLabel = mese.toLocaleDateString('it-IT', { month: 'long', year: 'numeric' });
  const assenzaDi = (dipId, dateStr) => ferie.find(f =>
    f.dipendente_id === dipId && f.data_inizio <= dateStr && (f.data_fine || f.data_inizio) >= dateStr);

  const ciclaCella = async (dipId, dateStr) => {
    const att = assenzaDi(dipId, dateStr);
    const next = !att ? "Ferie" : att.tipo === "Ferie" ? "Permesso" : null;
    await axios.post(`${API}/ferie-giorno`, { dipendente_id: dipId, data: dateStr, tipo: next });
    reload();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    await axios.post(`${API}/ferie`, formData);
    setShowModal(false);
    reload();
  };

  const handleApprova = async (id) => {
    await axios.put(`${API}/ferie/${id}/approva`);
    reload();
  };

  const handleRifiuta = async (id) => {
    await axios.put(`${API}/ferie/${id}/rifiuta`);
    reload();
  };

  return (
    <div className="dc-page">
      <div className="dc-page-header">
        <div>
          <h1>Ferie & Permessi</h1>
          <p>Gestione richieste ferie e permessi</p>
        </div>
        <button onClick={() => setShowModal(true)} className="dc-btn dc-btn-primary">
          <Plus size={18} /> Nuova Richiesta
        </button>
      </div>

      <div className="dc-card dc-scroll-x" style={{ overflowX: "auto", marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
          <button onClick={() => setMese(new Date(mese.getFullYear(), mese.getMonth() - 1, 1))} className="dc-btn" aria-label="Mese precedente">‹</button>
          <strong style={{ textTransform: "capitalize", minWidth: 150, textAlign: "center" }}>{meseLabel}</strong>
          <button onClick={() => setMese(new Date(mese.getFullYear(), mese.getMonth() + 1, 1))} className="dc-btn" aria-label="Mese successivo">›</button>
          <span style={{ marginLeft: 12, fontSize: 13, color: "#6b7669" }}>
            Clicca una cella: vuoto → <b style={{ color: "#5b7a6b" }}>Ferie</b> → <b style={{ color: "#7d5526" }}>Permesso</b> → vuoto
          </span>
        </div>
        <table className="dc-table" style={{ fontSize: 12, borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ position: "sticky", left: 0, background: "#fff", minWidth: 130, zIndex: 1 }}>DIPENDENTE</th>
              {Array.from({ length: giorniMese }, (_, i) => i + 1).map(d => {
                const dow = new Date(mese.getFullYear(), mese.getMonth(), d).getDay();
                const we = dow === 0 || dow === 6;
                return <th key={d} style={{ padding: "4px 3px", textAlign: "center", background: we ? "#faf7f0" : undefined, color: we ? "#9aa593" : undefined }}>{d}</th>;
              })}
            </tr>
          </thead>
          <tbody>
            {dipendenti.map(dip => (
              <tr key={dip.id}>
                <td style={{ position: "sticky", left: 0, background: "#fff", whiteSpace: "nowrap" }}>{dip.cognome} {dip.nome?.[0]}.</td>
                {Array.from({ length: giorniMese }, (_, i) => i + 1).map(d => {
                  const dateStr = ymd(mese.getFullYear(), mese.getMonth(), d);
                  const att = assenzaDi(dip.id, dateStr);
                  const meta = att ? TIPI.find(t => t.tipo === att.tipo) : null;
                  return (
                    <td key={d} title={att ? att.tipo : ""}
                      style={{ textAlign: "center", padding: 0, border: "1px solid #faf7f0", background: meta ? meta.color : "transparent" }}>
                      <button type="button" className="dc-cell-btn" onClick={() => ciclaCella(dip.id, dateStr)}
                        aria-label={`${dip.cognome} ${dip.nome || ""}, ${d}/${mese.getMonth() + 1}: ${att ? att.tipo : "nessuna assenza"} — cambia`}
                        style={{ color: meta ? "#fff" : "#6b7669", fontWeight: 600 }}>
                        {meta ? meta.code : "·"}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="dc-card">
        <table className="dc-table dc-table--cards">
          <thead>
            <tr>
              <th>DIPENDENTE</th>
              <th>TIPO</th>
              <th>PERIODO</th>
              <th>GIORNI</th>
              <th>STATO</th>
              <th>AZIONI</th>
            </tr>
          </thead>
          <tbody>
            {ferie.map((f) => {
              const dip = getDipendente(f.dipendente_id);
              return (
                <tr key={f.id}>
                  <td>
                    <div className="dc-table-user">
                      <Avatar nome={dip?.nome} cognome={dip?.cognome} size="sm" />
                      <span>{dip?.nome} {dip?.cognome}</span>
                    </div>
                  </td>
                  <td data-label="Tipo">{f.tipo}</td>
                  <td data-label="Periodo">{formatDate(f.data_inizio)} - {formatDate(f.data_fine)}</td>
                  <td data-label="Giorni">{f.giorni}</td>
                  <td data-label="Stato"><Badge variant={f.stato === 'approvata' ? 'success' : f.stato === 'rifiutata' ? 'danger' : 'warning'}>{f.stato}</Badge></td>
                  <td data-label="Azioni" className="dc-table-actions">
                    {f.stato === 'in_attesa' && (
                      <>
                        <button onClick={() => handleApprova(f.id)} className="dc-btn-icon dc-btn-success" title="Approva" aria-label={`Approva richiesta di ${dip?.nome || ""} ${dip?.cognome || ""}`}><Check size={16} /></button>
                        <button onClick={() => handleRifiuta(f.id)} className="dc-btn-icon dc-btn-danger" title="Rifiuta" aria-label={`Rifiuta richiesta di ${dip?.nome || ""} ${dip?.cognome || ""}`}><X size={16} /></button>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {showModal && (
        <Modal title="Nuova Richiesta Ferie/Permesso" onClose={() => setShowModal(false)}>
            <form onSubmit={handleSubmit} className="dc-modal-body">
              <label className="dc-form-group">
                <span className="dc-label">Dipendente *</span>
                <select required value={formData.dipendente_id} onChange={e => setFormData({...formData, dipendente_id: e.target.value})}>
                  <option value="">Seleziona...</option>
                  {dipendenti.map(d => <option key={d.id} value={d.id}>{d.nome} {d.cognome}</option>)}
                </select>
              </label>
              <label className="dc-form-group">
                <span className="dc-label">Tipo</span>
                <select value={formData.tipo} onChange={e => setFormData({...formData, tipo: e.target.value})}>
                  <option>Ferie</option>
                  <option>Permesso</option>
                  <option>ROL</option>
                  <option>Malattia</option>
                </select>
              </label>
              <div className="dc-form-row">
                <label className="dc-form-group">
                  <span className="dc-label">Data Inizio</span>
                  <input type="date" required value={formData.data_inizio} onChange={e => setFormData({...formData, data_inizio: e.target.value})} />
                </label>
                <label className="dc-form-group">
                  <span className="dc-label">Data Fine</span>
                  <input type="date" required value={formData.data_fine} onChange={e => setFormData({...formData, data_fine: e.target.value})} />
                </label>
              </div>
              <label className="dc-form-group">
                <span className="dc-label">Giorni</span>
                <input type="number" min="1" value={formData.giorni} onChange={e => setFormData({...formData, giorni: +e.target.value})} />
              </label>
              <div className="dc-modal-footer">
                <button type="button" onClick={() => setShowModal(false)} className="dc-btn">Annulla</button>
                <button type="submit" className="dc-btn dc-btn-primary">Crea Richiesta</button>
              </div>
            </form>
        </Modal>
      )}
    </div>
  );
}

// Turni Page
function TurniPage({ dipendenti, turni, reload }) {
  const [assegnazioni, setAssegnazioni] = useState([]);
  const [busy, setBusy] = useState(false);
  const [evid, setEvid] = useState(null);
  const [showSost, setShowSost] = useState(false);
  const [sost, setSost] = useState({ assente: "", giorno: "", motivo: "malattia", sostituto: "", turnoSost: "", protocollo: "", dal: "", al: "" });
  const [paint, setPaint] = useState(false);     // modalità pennello turni
  const [penTurno, setPenTurno] = useState("");  // turno selezionato per il pennello ("" = vuoto)
  const [vista, setVista] = useState("semplice"); // "semplice" (bollini con sponde) | "tabella" (griglia completa)
  const tbodyRef = useRef(null);
  const giorni = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"];
  const lunOggi = (() => { const o = new Date(); const off = (o.getDay() + 6) % 7; const m = new Date(o); m.setDate(o.getDate() - off); m.setHours(0, 0, 0, 0); return m; })();
  const [lunedi, setLunedi] = useState(lunOggi);
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const settimana = iso(lunedi);
  const dataDi = (i) => { const d = new Date(lunedi); d.setDate(lunedi.getDate() + i); return d.getDate(); };
  const meseLabel = (() => { const f = new Date(lunedi); const l = new Date(lunedi); l.setDate(l.getDate() + 6); return `${f.getDate()} ${f.toLocaleDateString('it-IT', { month: 'short' })} – ${l.getDate()} ${l.toLocaleDateString('it-IT', { month: 'short' })}`; })();
  const BASE_BAR = new Date(2026, 5, 15);
  const settimanaPari = ((Math.round((lunedi - BASE_BAR) / (7 * 86400000)) % 2) + 2) % 2 === 0;
  const caricaSettimana = (s) => axios.get(`${API}/assegnazioni-turni?settimana=${s}`).then(res => setAssegnazioni(res.data || [])).catch(() => {});
  useEffect(() => { caricaSettimana(settimana); }, [settimana]);
  useEffect(() => {
    // Il riordino a trascinamento esiste solo nella vista griglia.
    if (!tbodyRef.current) return;
    const s = Sortable.create(tbodyRef.current, {
      handle: ".dc-drag-handle", animation: 150,
      onEnd: () => {
        const ids = Array.from(tbodyRef.current.children).map(tr => tr.getAttribute("data-id")).filter(Boolean);
        axios.post(`${API}/ordine-dipendenti`, { ordine: ids }).then(() => reload && reload());
      },
    });
    return () => s.destroy();
  }, [vista]);

  const getAssegnazione = (dipId, giorno) => assegnazioni.find(a => a.dipendente_id === dipId && a.giorno === giorno);
  const getTurno = (turnoId) => turni.find(t => t.id === turnoId);
  const idTurno = (nome) => (turni.find(t => t.nome === nome) || {}).id;
  const nomeTurno = (id) => (turni.find(t => t.id === id) || {}).nome;

  // Squadra produzione (per nome di battesimo): su questi agisce il motore.
  const TEAM = ["luigi", "angela", "giuliano", "liliana", "carmine", "mario"];
  const isTeam = (dip) => TEAM.includes((dip.nome || "").trim().toLowerCase());
  const UNICI = ["Lunga", "Riposo"]; // un solo turno di questo tipo per giorno
  // Dipendenti da NON mostrare nei turni (richiesta titolare: Ceraldi Vincenzo,
  // Valerio e Antonella non fanno turni). Il confronto include anche nome_completo,
  // così vale pure per i record anagrafici con solo quel campo compilato.
  const NASCOSTI = [["antonella","ceraldi"],["vincenzo","ceraldi"],["valerio","ceraldi"]];
  const isNascosto = (d) => { const f = `${d.nome||""} ${d.cognome||""} ${d.nome_completo||""}`.toLowerCase(); return NASCOSTI.some(([a,b]) => f.includes(a) && f.includes(b)); };
  // Sempre presente tutti i giorni (amministratrice)
  const isSemprePresente = (d) => { const f = `${d.nome||""} ${d.cognome||""} ${d.nome_completo||""}`.toLowerCase(); return f.includes("antonietta") && f.includes("ceraldi"); };
  const dipTurni = dipendenti.filter(d => !isNascosto(d));

  const salva = async (updates) => {
    setBusy(true);
    try {
      for (const u of updates) await axios.post(`${API}/assegnazioni-turni`, { ...u, settimana });
      await caricaSettimana(settimana);
    } finally { setBusy(false); }
  };

  // Onomastici (gestiti nel modale unico "Configura turni"); qui solo il riepilogo settimanale.
  const [onomSett, setOnomSett] = useState([]);
  useEffect(() => { axios.get(`${API}/onomastici/settimana?settimana=${settimana}`).then(r => setOnomSett(r.data || [])).catch(() => setOnomSett([])); }, [settimana]);
  const mettiRiposoOnom = async (o) => {
    const idR = idTurno("Riposo");
    if (!idR) { toast("Manca il turno 'Riposo' tra i tipi di turno.", "err"); return; }
    await salva([{ dipendente_id: o.dipendente_id, giorno: o.giorno_nome, turno_id: idR, motivo: "onomastico" }]);
  };
  // Precompilazione automatica: nel giorno dell'onomastico → Riposo (se la cella è
  // libera; un'assegnazione manuale dell'admin ha la precedenza = copertura).
  useEffect(() => {
    if (!onomSett.length) return;
    const idR = idTurno("Riposo");
    if (!idR) return;
    const mancanti = onomSett.filter(o => !assegnazioni.some(a => a.dipendente_id === o.dipendente_id && a.giorno === o.giorno_nome));
    if (!mancanti.length) return;
    (async () => {
      for (const o of mancanti) await axios.post(`${API}/assegnazioni-turni`, { dipendente_id: o.dipendente_id, giorno: o.giorno_nome, turno_id: idR, settimana, motivo: "onomastico" });
      caricaSettimana(settimana);
    })();
  }, [onomSett, assegnazioni, turni, settimana]);

  // Config turni per dipendente (turno abituale + giorno di riposo fisso) + ferie
  const [turniCfg, setTurniCfg] = useState([]);     // [{dipendente_id, turno_id, riposo_giorno}]
  const [ferieTurni, setFerieTurni] = useState([]); // ferie/permessi per overlay
  const [showCfg, setShowCfg] = useState(false);
  const [cfgRows, setCfgRows] = useState([]);
  const isoT = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const caricaCfg = () => axios.get(`${API}/turni-config`).then(r => setTurniCfg(r.data || [])).catch(() => {});
  // Periodo di chiusura pomeridiana del bar (es. estate): impostato nel modale Configura turni.
  const [chiusuraPom, setChiusuraPom] = useState({ attiva: false, dal: "", al: "" });
  useEffect(() => {
    caricaCfg();
    axios.get(`${API}/ferie`).then(r => setFerieTurni(r.data || [])).catch(() => {});
    axios.get(`${API}/turni-chiusura-pomeridiana`)
      .then(r => setChiusuraPom({ attiva: !!r.data.attiva, dal: r.data.dal || "", al: r.data.al || "" }))
      .catch(() => {});
  }, []);
  const cfgDi = (dipId) => turniCfg.find(c => c.dipendente_id === dipId) || {};
  // Preferenze del giorno di riposo inviate dai dipendenti dal portale (per settimana)
  const [prefRiposo, setPrefRiposo] = useState([]);
  useEffect(() => {
    axios.get(`${API}/turni-preferenze?settimana=${settimana}`)
      .then(r => setPrefRiposo(r.data || [])).catch(() => setPrefRiposo([]));
  }, [settimana]);
  const prefDi = (dipId) => (prefRiposo.find(p => p.dipendente_id === dipId) || {}).giorno || null;
  // Disponibilità a coprire il bar (dal portale, per chi ha il flag 🆘 in Configura turni)
  const [dispBar, setDispBar] = useState([]);
  useEffect(() => {
    axios.get(`${API}/turni-disponibilita-bar?settimana=${settimana}`)
      .then(r => setDispBar(r.data || [])).catch(() => setDispBar([]));
  }, [settimana]);
  const ferieDataT = (dipId, dStr) => ferieTurni.find(f => f.dipendente_id === dipId
    && (f.stato === 'approvata' || !f.stato)
    && f.data_inizio <= dStr && (f.data_fine || f.data_inizio) >= dStr);
  const LUNGA_GIORNI = ["Venerdì", "Sabato", "Domenica"];  // giorni in cui si può fissare la Lunga
  const apriCfg = async () => {
    let onom = [];
    try { onom = (await axios.get(`${API}/onomastici`)).data || []; } catch {}
    const om = {}; onom.forEach(o => { om[o.dipendente_id] = o; });
    // Etichetta senza doppioni (alcuni record hanno lo stesso valore in nome e cognome)
    const etich = (d) => {
      const cg = (d.cognome || '').trim(), nm = (d.nome || '').trim();
      if (cg && nm && cg.toLowerCase() === nm.toLowerCase()) return cg;
      return `${cg} ${nm}`.trim() || d.nome_completo || d.nome || '';
    };
    setCfgRows(dipTurni.map(d => { const c = cfgDi(d.id); const o = om[d.id] || {}; const lg = c.lunga_giorni || []; return {
      dipendente_id: d.id, nome: etich(d),
      turno_id: c.turno_id || '', riposo_giorno: c.riposo_giorno || '', rotazione: c.rotazione || '', sala: !!c.sala,
      rotazione_ancora: c.rotazione_ancora || '', sostituto_bar: !!c.sostituto_bar,
      lunga1: lg[0] || '', lunga2: lg[1] || '', doppia: lg.length > 1,
      onom_mese: o.mese ?? '', onom_giorno: o.giorno ?? '', onom_attivo: o.attivo ?? false, straniero: o.straniero || false }; }));
    setShowCfg(true);
  };
  const patchCfgRow = (i, patch) => setCfgRows(rows => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const toggleLungaCfg = (i, g) => setCfgRows(rows => rows.map((r, j) => {
    if (j !== i) return r;
    const sel = [r.lunga1, r.doppia ? r.lunga2 : ""].filter(Boolean);
    const next = sel.includes(g) ? sel.filter(x => x !== g) : [...sel, g].slice(-2);
    return { ...r, lunga1: next[0] || "", lunga2: next[1] || "", doppia: next.length === 2 };
  }));
  const setCfgRow = (i, k, v) => setCfgRows(rows => rows.map((r, j) => {
    if (j !== i) return r;
    const nr = { ...r, [k]: v };
    if (k === "doppia" && !v) nr.lunga2 = "";   // tolgo il 2° giorno se disattivo la doppia
    return nr;
  }));
  // Da lunga1/lunga2/doppia costruisco l'array lunga_giorni (1 di default, 2 solo se doppia spuntata)
  const lungaGiorniDi = (r) => {
    const out = [];
    if (r.lunga1) out.push(r.lunga1);
    if (r.doppia && r.lunga2 && r.lunga2 !== r.lunga1) out.push(r.lunga2);
    return out;
  };
  const salvaCfg = async () => {
    await axios.post(`${API}/turni-config`, { voci: cfgRows.map(r => ({ dipendente_id: r.dipendente_id, turno_id: r.turno_id || null, riposo_giorno: r.riposo_giorno || null, lunga_giorni: lungaGiorniDi(r), rotazione: r.rotazione || null, rotazione_ancora: (r.rotazione && r.rotazione_ancora) || null, sala: !!r.sala, sostituto_bar: !!r.sostituto_bar })) });
    await axios.post(`${API}/onomastici`, { voci: cfgRows.map(r => ({ dipendente_id: r.dipendente_id, mese: r.onom_mese ? Number(r.onom_mese) : null, giorno: r.onom_giorno ? Number(r.onom_giorno) : null, attivo: r.onom_attivo })) });
    await axios.post(`${API}/turni-chiusura-pomeridiana`, chiusuraPom).catch(() => {});
    await caricaCfg();
    axios.get(`${API}/onomastici/settimana?settimana=${settimana}`).then(r => setOnomSett(r.data || []));
    setShowCfg(false);
  };

  // Riequilibrio automatico: se assegno una Lunga o un Riposo a una persona della
  // produzione, chi aveva quel turno quel giorno si scambia il turno con lei,
  // così il giorno resta sempre con una sola lunga e un solo riposo.
  const handleAssegna = async (dip, giorno, nuovoId) => {
    const updates = [{ dipendente_id: dip.id, giorno, turno_id: nuovoId || null }];
    const nuovoNome = nomeTurno(nuovoId);
    if (isTeam(dip) && UNICI.includes(nuovoNome)) {
      const vecchioId = (getAssegnazione(dip.id, giorno) || {}).turno_id || null;
      const altro = dipendenti.find(d =>
        d.id !== dip.id && isTeam(d) && (getAssegnazione(d.id, giorno) || {}).turno_id === nuovoId);
      if (altro) updates.push({ dipendente_id: altro.id, giorno, turno_id: vecchioId });
    }
    await salva(updates);
  };

  // ===== VISTA SEMPLICE — "sponde" per dipendente =====
  // Ogni dipendente può fare solo i SUOI turni (dalla sua configurazione): un click
  // sulla casella passa al turno successivo tra quelli, poi Riposo, Ferie e vuoto.
  const spondeDi = (dip) => {
    const c = cfgDi(dip.id);
    const ids = [];
    const add = (id) => { if (id && !ids.includes(id)) ids.push(id); };
    if (c.sala) { add(idTurno("Lunga")); add(idTurno("Mattina 8-16") || idTurno("Mattina 7-15")); add(idTurno("Pomeriggio")); }
    else if (c.rotazione) { add(idTurno("Bar 6:30-15")); add(idTurno("Bar 15-21")); }
    else if (c.turno_id) { add(c.turno_id); if ((c.lunga_giorni || []).length) add(idTurno("Lunga")); }
    else turni.forEach(t => { if (!/riposo|ferie/i.test(t.nome || "")) add(t.id); });
    add(idTurno("Riposo")); add(idTurno("Ferie"));
    return ids;
  };
  const ciclaTurno = async (dip, giorno) => {
    const cur = (getAssegnazione(dip.id, giorno) || {}).turno_id || null;
    const opzioni = [...spondeDi(dip), null];   // dopo l'ultima sponda si torna a vuoto
    const next = opzioni[(opzioni.indexOf(cur) + 1) % opzioni.length];
    const updates = [{ dipendente_id: dip.id, giorno, turno_id: next }];
    // stessa regola della griglia: Lunga/Riposo unici nella squadra sala → scambio col collega
    if (isTeam(dip) && UNICI.includes(nomeTurno(next))) {
      const altro = dipendenti.find(d => d.id !== dip.id && isTeam(d)
        && (getAssegnazione(d.id, giorno) || {}).turno_id === next);
      if (altro) updates.push({ dipendente_id: altro.id, giorno, turno_id: cur });
    }
    // aggiornamento ottimistico: il bollino cambia subito, il salvataggio parte dietro
    setAssegnazioni(prev => {
      const resto = prev.filter(a => !(a.giorno === giorno && updates.some(u => a.dipendente_id === u.dipendente_id)));
      return [...resto, ...updates.map(u => ({ ...u, settimana }))];
    });
    try { for (const u of updates) await axios.post(`${API}/assegnazioni-turni`, { ...u, settimana }); }
    catch { caricaSettimana(settimana); toast("Salvataggio non riuscito, riprova", "err"); }
  };
  // Copertura del giorno: persone al mattino e al pomeriggio (la Lunga conta per entrambi)
  const coperturaDi = (giorno) => {
    let mattina = 0, pomeriggio = 0;
    dipTurni.forEach(d => {
      const n = (nomeTurno((getAssegnazione(d.id, giorno) || {}).turno_id) || "").toLowerCase();
      if (!n || /riposo|ferie/.test(n)) return;
      if (/lunga/.test(n)) { mattina++; pomeriggio++; }
      else if (/pomerig|15-21|sera/.test(n)) pomeriggio++;
      else mattina++;
    });
    return { mattina, pomeriggio };
  };

  // Genera la settimana della squadra produzione secondo le regole.
  // Genera la settimana dai DATI: per ogni dipendente configurato usa il suo turno
  // abituale, mette Riposo nel giorno di riposo fisso e nell'onomastico, e mette
  // Ferie nei giorni di ferie/permesso approvati. Niente più nomi cablati.
  const generaProduzione = async () => {
    const idRiposo = idTurno("Riposo");
    const idFerie = idTurno("Ferie");
    const updates = [];
    const idLunga = idTurno("Lunga");
    // Rotazione bar: una settimana mattina, una pomeriggio. settimanaPari decide la fase.
    const idBarMattina = idTurno("Bar 6:30-15"), idBarPom = idTurno("Bar 15-21");
    // Ricarica le ferie fresche: una ferie appena approvata viene subito considerata.
    let ferieFresh = ferieTurni;
    try { ferieFresh = (await axios.get(`${API}/ferie`)).data || []; setFerieTurni(ferieFresh); } catch { /* uso lo stato attuale */ }
    const ferieIn = (dipId, dStr) => ferieFresh.find(f => f.dipendente_id === dipId
      && (f.stato === 'approvata' || !f.stato)
      && (((f.data_inizio || f.data) <= dStr && (f.data_fine || f.data_inizio || f.data) >= dStr)));
    // Turni "sala" per la rotazione camerieri
    const idSalaMatt = idTurno("Mattina 8-16") || idTurno("Mattina 7-15");
    const idSalaPom = idTurno("Pomeriggio");
    // Chiusura pomeridiana del bar (periodo impostato nel modale Configura turni)
    const chiusuraAttiva = chiusuraPom.attiva && chiusuraPom.dal && chiusuraPom.al;
    const inChiusuraPom = (dStr) => chiusuraAttiva && dStr >= chiusuraPom.dal && dStr <= chiusuraPom.al;
    const lun7 = new Date(lunedi); lun7.setDate(lunedi.getDate() + 7);
    const lun14 = new Date(lunedi); lun14.setDate(lunedi.getDate() + 14);
    // La settimana che stiamo generando è quella immediatamente precedente all'inizio
    // della chiusura se la data di inizio cade nella settimana successiva.
    const settimanaPreChiusura = chiusuraAttiva && chiusuraPom.dal >= isoT(lun7) && chiusuraPom.dal < isoT(lun14);
    // Camerieri in rotazione bilanciata: 2 Lunga, 2 Mattina, 2 Pomeriggio, 1 Riposo.
    // Riposo nei giorni feriali (Lun-Gio) → ven/sab/dom restano pieni (più copertura weekend).
    const camerieri = dipTurni.filter(d => cfgDi(d.id).sala).map(d => d.id);
    const FERIALI_RIPOSO = [0, 1, 2, 3]; // Lun,Mar,Mer,Gio
    let tocco = 0;
    dipTurni.forEach(dip => {
      const c = cfgDi(dip.id);

      // ===== CAMERIERE (rotazione sala) =====
      if (c.sala) {
        const k = Math.max(0, camerieri.indexOf(dip.id));
        // giorno di riposo: la preferenza dal portale (per QUESTA settimana) vince sul
        // fisso; poi il fisso se feriale; altrimenti distribuito Lun-Gio per il weekend
        const riposoScelto = prefDi(dip.id) || c.riposo_giorno;
        let riposoIdx = riposoScelto ? giorni.indexOf(riposoScelto) : -1;
        if (riposoIdx < 0 || riposoIdx > 4) riposoIdx = FERIALI_RIPOSO[k % 4];
        // sequenza interlacciata (2 Lunga, 2 Mattina, 2 Pomeriggio) ruotata per persona → fasce sfalsate
        const base = [idTurno("Lunga"), idSalaMatt, idSalaPom, idTurno("Lunga"), idSalaMatt, idSalaPom];
        const off = k % 6;
        const seq = base.slice(off).concat(base.slice(0, off));
        let si = 0;
        for (let gi = 0; gi < 7; gi++) {
          const date = new Date(lunedi); date.setDate(lunedi.getDate() + gi);
          const dStr = isoT(date); const giorno = giorni[gi];
          let target;
          if (ferieIn(dip.id, dStr)) target = idFerie || idRiposo;
          else if (onomSett.some(o => o.dipendente_id === dip.id && o.giorno_nome === giorno)) target = idRiposo;
          else if (gi === riposoIdx) target = idRiposo;
          else { target = seq[si % 6] || null; si++; }
          updates.push({ dipendente_id: dip.id, giorno, turno_id: target || null }); tocco++;
        }
        return;
      }

      // ===== ALTRI (turno fisso / rotazione bar) =====
      // La preferenza di riposo dal portale (per QUESTA settimana) vince sul giorno fisso.
      const giornoRiposo = prefDi(dip.id) || c.riposo_giorno;
      const configurato = !!(c.turno_id || giornoRiposo || (c.lunga_giorni || []).length || c.rotazione);
      // turno "di lavoro" della settimana: se in rotazione bar, alterna mattina/pomeriggio
      let turnoLavoro = c.turno_id || null;
      if (c.rotazione) {
        const iniziaMattina = c.rotazione === "mattina";
        let mattinaQuestaSett;
        if (c.rotazione_ancora) {
          // Fase ancorata alla settimana in cui è stata impostata: "ora mattina"
          // = mattina in QUELLA settimana, poi inversione automatica ogni lunedì.
          const ancora = new Date(c.rotazione_ancora + "T00:00:00");
          const diffSett = Math.round((lunedi - ancora) / (7 * 86400000));
          const stessaParita = ((diffSett % 2) + 2) % 2 === 0;
          mattinaQuestaSett = stessaParita ? iniziaMattina : !iniziaMattina;
        } else {
          // configurazioni vecchie senza ancora: parità globale come prima
          mattinaQuestaSett = settimanaPari ? iniziaMattina : !iniziaMattina;
        }
        turnoLavoro = mattinaQuestaSett ? idBarMattina : idBarPom;
      }
      // Regole baristi legate alla chiusura pomeridiana (vedi modale Configura turni):
      // - la domenica il bar è chiuso di pomeriggio → il gruppo di pomeriggio riposa
      //   la domenica (1 gruppo lavora 7 giorni, l'altro 6);
      // - nel periodo di chiusura pomeridiana la rotazione resta regolare
      //   (2 di mattina, 2 di pomeriggio) ma la domenica riposano tutti;
      // - la settimana precedente all'inizio della chiusura salta il riposo
      //   infrasettimanale (il riposo arriva con la domenica di chiusura).
      const saltaRiposoInfra = c.rotazione && settimanaPreChiusura;
      for (let gi = 0; gi < 7; gi++) {
        const date = new Date(lunedi); date.setDate(lunedi.getDate() + gi);
        const dStr = isoT(date);
        const giorno = giorni[gi];
        let target;  // undefined = nessuna opinione (lascio la cella com'è)
        if (ferieIn(dip.id, dStr)) target = idFerie || idRiposo;                       // ferie approvata (vale per TUTTI)
        else if (onomSett.some(o => o.dipendente_id === dip.id && o.giorno_nome === giorno)) target = idRiposo; // onomastico
        else if (c.rotazione && inChiusuraPom(dStr)) target = gi === 6 ? idRiposo : (turnoLavoro || null); // chiusura pom.: rotazione regolare + riposo domenica per tutti
        else if (c.rotazione && gi === 6 && idBarPom && turnoLavoro === idBarPom) target = idRiposo; // domenica pomeriggio chiusi: il gruppo pomeriggio riposa
        else if (configurato) {
          if (giornoRiposo && giornoRiposo === giorno && !saltaRiposoInfra) target = idRiposo; // riposo (preferenza portale o fisso)
          else if ((c.lunga_giorni || []).includes(giorno)) target = idLunga || turnoLavoro || null; // Lunga (ven/sab/dom)
          else target = turnoLavoro || null;                                            // turno abituale / rotazione bar (o giorno di riposo saltato pre-chiusura)
        }
        if (target !== undefined) {
          updates.push({ dipendente_id: dip.id, giorno, turno_id: target || null }); tocco++;
        } else {
          // non configurato e nessuna ferie/onomastico: pulisco solo una "Ferie" rimasta
          // (così se cancello la ferie e rigenero, il turno non resta bloccato su Ferie).
          const cur = getAssegnazione(dip.id, giorno);
          if (cur && nomeTurno(cur.turno_id) === "Ferie") { updates.push({ dipendente_id: dip.id, giorno, turno_id: null }); tocco++; }
        }
      }
    });
    // === SOSTITUZIONE BAR (disponibilità dal portale) ===
    // Chi si è offerto va al bar nella fascia che ha scelto, nei giorni coperti;
    // se era in squadra sala, il suo posto è coperto da una Lunga (giornata doppia)
    // assegnata al cameriere con meno Lunghe in settimana. Se l'unico disponibile
    // è a riposo, si chiede conferma prima di annullarglielo.
    const pianoDi = (dipId, gi) => {
      const u = [...updates].reverse().find(x => x.dipendente_id === dipId && x.giorno === giorni[gi]);
      if (u) return u.turno_id;
      return (getAssegnazione(dipId, giorni[gi]) || {}).turno_id || null;
    };
    const setPiano = (dipId, gi, turnoId) => {
      const idx = updates.findIndex(x => x.dipendente_id === dipId && x.giorno === giorni[gi]);
      if (idx >= 0) updates[idx] = { dipendente_id: dipId, giorno: giorni[gi], turno_id: turnoId };
      else { updates.push({ dipendente_id: dipId, giorno: giorni[gi], turno_id: turnoId }); tocco++; }
    };
    const salaIds = dipTurni.filter(d => cfgDi(d.id).sala).map(d => d.id);
    const cognomeDip = (id) => { const d = dipendenti.find(x => x.id === id) || {}; return d.cognome || d.nome_completo || d.nome || "?"; };
    for (let gi = 0; gi < 7; gi++) {
      const dt = new Date(lunedi); dt.setDate(lunedi.getDate() + gi);
      const dStr = isoT(dt);
      for (const disp of dispBar) {
        if (!(disp.dal <= dStr && dStr <= disp.al)) continue;
        const S = dipTurni.find(d => d.id === disp.dipendente_id);
        if (!S || cfgDi(S.id).rotazione) continue;   // un barista non sostituisce sé stesso
        const turnoBar = disp.fascia === "pomeriggio" ? idBarPom : idBarMattina;
        if (!turnoBar) continue;
        const copriSala = salaIds.includes(S.id);
        setPiano(S.id, gi, turnoBar);
        // Il barista assente esce dal calendario nei giorni coperti: la coppia
        // diventa es. Vespa+Taiano, non più Vespa+Capezzuto.
        if (disp.sostituisce_id && dipTurni.some(d => d.id === disp.sostituisce_id)) {
          setPiano(disp.sostituisce_id, gi, null);
        }
        if (!copriSala) continue;
        // sala: candidato alla doppia = cameriere (non S) non in Ferie e non già Lunga
        const cand = salaIds.filter(id => id !== S.id)
          .map(id => ({ id, turno: pianoDi(id, gi) }))
          .filter(c => { const n = nomeTurno(c.turno) || ""; return n !== "Ferie" && n !== "Lunga"; });
        const lungheDi = (id) => { let n = 0; for (let g2 = 0; g2 < 7; g2++) if (nomeTurno(pianoDi(id, g2)) === "Lunga") n++; return n; };
        const lavorano = cand.filter(c => c.turno && nomeTurno(c.turno) !== "Riposo").sort((a, b) => lungheDi(a.id) - lungheDi(b.id));
        const aRiposo = cand.filter(c => nomeTurno(c.turno) === "Riposo").sort((a, b) => lungheDi(a.id) - lungheDi(b.id));
        let scelto = lavorano[0] || null;
        if (!scelto && aRiposo.length) {
          const c0 = aRiposo[0];
          if (window.confirm(`${giorni[gi]}: ${cognomeDip(S.id)} copre il bar e in sala manca una persona. `
            + `L'unico disponibile è ${cognomeDip(c0.id)}, che però è a riposo. Annullo il suo riposo e gli do la Lunga?`)) scelto = c0;
        }
        if (scelto && idLunga) setPiano(scelto.id, gi, idLunga);
        else if (!scelto) toast(`⚠️ ${giorni[gi]}: sala scoperta (nessun cameriere disponibile per la doppia)`, "err");
      }
    }

    // === REGOLA: chi fa la sera non fa la mattina successiva (forzata) ===
    // Ricostruisco l'orario effettivo della settimana (esistente + modifiche appena calcolate)
    // e, se trovo "mattina" subito dopo una "sera/pomeriggio", sposto la mattina al pomeriggio.
    const isSera = (id) => { const n = nomeTurno(id) || ""; return /pomerig|15-21|sera/i.test(n); };
    const isMattina = (id) => { const n = nomeTurno(id) || ""; return /mattin|6:30|7-15|8-16/i.test(n); };
    const pomeriggioPer = (id) => {
      const n = nomeTurno(id) || "";
      if (/bar|6:30|15/i.test(n)) return idTurno("Bar 15-21") || idTurno("Pomeriggio");
      return idTurno("Pomeriggio") || idTurno("Bar 15-21");
    };
    const sched = {};
    dipTurni.forEach(d => { sched[d.id] = giorni.map(g => (getAssegnazione(d.id, g) || {}).turno_id || null); });
    updates.forEach(u => { const gi = giorni.indexOf(u.giorno); if (sched[u.dipendente_id] && gi >= 0) sched[u.dipendente_id][gi] = u.turno_id; });
    dipTurni.forEach(d => {
      for (let gi = 1; gi < 7; gi++) {
        const ieri = sched[d.id][gi - 1], oggi = sched[d.id][gi];
        if (isSera(ieri) && isMattina(oggi)) {
          const nuovo = pomeriggioPer(oggi);
          if (nuovo && nuovo !== oggi) {
            sched[d.id][gi] = nuovo;
            updates.push({ dipendente_id: d.id, giorno: giorni[gi], turno_id: nuovo, motivo: "regola sera→mattina" });
            tocco++;
          }
        }
      }
    });
    if (!tocco) { toast("Niente da generare: apri \"Configura turni\" e imposta turno/riposo (o spunta Sala), oppure verifica le ferie approvate.", "info"); return; }
    if (updates.length) { await salva(updates); toast("Settimana generata"); }
  };

  // === SOSTITUZIONE D'EMERGENZA (malattia/assenza) ===
  // Data (ISO) del giorno (nome) nella settimana visualizzata.
  const dataGiorno = (g) => { const gi = giorni.indexOf(g); if (gi < 0) return ""; const d = new Date(lunedi); d.setDate(lunedi.getDate() + gi); return iso(d); };
  // Assicura l'esistenza di un tipo turno (es. "Malattia") e ne ritorna l'id.
  const ensureTurno = async (nome, colore) => {
    let id = idTurno(nome);
    if (id) return id;
    try {
      await axios.post(`${API}/turni`, { nome, orario_inizio: "", orario_fine: "", colore });
      const fresh = (await axios.get(`${API}/turni`)).data || [];
      if (reload) reload();
      return (fresh.find(t => t.nome === nome) || {}).id || null;
    } catch { return null; }
  };
  const apriSost = () => {
    const g = giorni[(new Date().getDay() + 6) % 7];
    const ds = dataGiorno(g);
    setSost({ assente: "", giorno: g, motivo: "malattia", sostituto: "", turnoSost: idTurno("Lunga") || "", protocollo: "", dal: ds, al: ds });
    setShowSost(true);
  };
  const setSostGiorno = (g) => { const ds = dataGiorno(g); setSost(s => ({ ...s, giorno: g, dal: ds, al: ds })); };
  const GIUST_MOTIVO = { malattia: "M", ferie: "F", permesso: "PE", assenza: "AS" };
  const confermaSost = async () => {
    if (!sost.assente || !sost.giorno) { toast("Scegli il dipendente assente e il giorno.", "err"); return; }
    if (sost.sostituto && sost.sostituto === sost.assente) { toast("Il sostituto deve essere un'altra persona.", "err"); return; }
    const ups = [];
    const giust = GIUST_MOTIVO[sost.motivo] || "AS";

    if (sost.motivo === "malattia") {
      // MALATTIA: stato di presenza (NON Riposo), con numero di protocollo del certificato medico.
      const dal = sost.dal || dataGiorno(sost.giorno);
      const al = sost.al || dal;
      const nota = sost.protocollo ? `Malattia · Protocollo INPS: ${sost.protocollo}` : "Malattia";
      const batch = [];
      for (let d = new Date(dal); isoT(d) <= al; d.setDate(d.getDate() + 1))
        batch.push({ dipendente_id: sost.assente, data: isoT(d), stato: "giustificato", giustificativo: "M", note: nota });
      if (batch.length) { try { await axios.post(`${API}/presenze/batch`, batch); } catch (e) { console.error(e); } }
      // Nella griglia turni della settimana: cella "Malattia" (non Riposo) nei giorni del range.
      const idMal = await ensureTurno("Malattia", "#f59e0b");
      for (let gi = 0; gi < 7; gi++) { const d = new Date(lunedi); d.setDate(lunedi.getDate() + gi); const ds = iso(d);
        if (ds >= dal && ds <= al) ups.push({ dipendente_id: sost.assente, giorno: giorni[gi], turno_id: idMal || null, motivo: "malattia" }); }
    } else {
      // Ferie/Permesso/Assenza: registro la presenza del giorno e libero il turno (Riposo).
      const ds = dataGiorno(sost.giorno);
      try { await axios.post(`${API}/presenze/batch`, [{ dipendente_id: sost.assente, data: ds, stato: sost.motivo === "assenza" ? "assente" : "giustificato", giustificativo: giust, note: sost.motivo }]); } catch (e) { console.error(e); }
      const idAlt = sost.motivo === "ferie" ? (idTurno("Ferie") || idTurno("Riposo")) : idTurno("Riposo");
      ups.push({ dipendente_id: sost.assente, giorno: sost.giorno, turno_id: idAlt || null, motivo: sost.motivo });
    }

    if (sost.sostituto && sost.turnoSost)
      ups.push({ dipendente_id: sost.sostituto, giorno: sost.giorno, turno_id: sost.turnoSost, motivo: "sostituzione" });

    if (ups.length) await salva(ups); else await caricaSettimana(settimana);
    setShowSost(false);
    toast(sost.motivo === "malattia" ? "Malattia registrata nelle presenze" : "Sostituzione salvata");
  };

  return (
    <div className="dc-page">
      <div className="dc-page-header">
        <div>
          <h1>Gestione Turni</h1>
          <p>Assegnazione turni settimanali · la squadra produzione si riequilibra da sola</p>
        </div>
        <div className="dc-turni-legend">
          {turni.map(t => {
            const haOrario = /\d/.test(t.nome);
            const sel = evid === t.id;
            return (
              <span key={t.id} onClick={() => setEvid(sel ? null : t.id)}
                className="dc-turno-badge"
                title="Clicca per evidenziare chi fa questo turno"
                style={{ backgroundColor: t.colore, cursor: "pointer", outline: sel ? "3px solid #5b7a6b" : "none", opacity: evid && !sel ? 0.45 : 1 }}>
                {t.nome}{!haOrario && t.orario_inizio ? `: ${t.orario_inizio}-${t.orario_fine}` : ""}
              </span>
            );
          })}
        </div>
      </div>

      <details className="dc-card" style={{ marginBottom: 12, padding: "12px 16px" }}>
        <summary style={{ cursor: "pointer", fontWeight: 700, fontSize: 14 }}>📖 Guida — come funziona questa pagina</summary>
        <div style={{ fontSize: 13, lineHeight: 1.65, marginTop: 10 }}>
          <p style={{ margin: "0 0 8px" }}><b>✨ Vista semplice</b> (quella che vedi): una riga per dipendente, 7 caselle.
            <b> Un click sulla casella = turno successivo</b> tra le sue "sponde" (i soli turni che può fare, poi Riposo, Ferie, vuoto).
            Si salva da solo a ogni click. In alto la <b>copertura</b>: ☀️ persone al mattino e 🌆 al pomeriggio (la Lunga conta per entrambi); <span style={{ color: "#b3261e", fontWeight: 700 }}>rosso</span> = fascia scoperta.</p>
          <p style={{ margin: "0 0 8px" }}><b>Simboli</b>: 🎂 riposo per onomastico · 💤 giorno di riposo chiesto dal dipendente dal portale.</p>
          <p style={{ margin: "0 0 8px" }}><b>⚙️ Configura turni</b>: le sponde di ogni dipendente — modalità (Sala / Bar in rotazione / turno fisso),
            riposo fisso, giorni di Lunga, onomastico e il periodo di chiusura pomeridiana del bar.</p>
          <p style={{ margin: "0 0 8px" }}><b>Genera settimana</b> compila tutto da solo: Ferie nei giorni approvati, Riposo per onomastici e
            preferenze 💤 (vincono sul riposo fisso), rotazione baristi mattina↔pomeriggio ("☀️ ora mattina" vale per la settimana in cui
            la imposti, poi si inverte da sola ogni lunedì) con riposo domenicale del gruppo di pomeriggio,
            rotazione sala 2 Lunga / 2 Mattina / 2 Pomeriggio / 1 Riposo. Ogni casella resta modificabile a mano dopo.</p>
          <p style={{ margin: "0 0 8px" }}><b>🆘 Sostituzioni bar</b>: se manca un barista, chi ha la spunta "può coprire il bar" (in Configura turni)
            manda la disponibilità dal portale scegliendo giorni e fascia; "Genera settimana" lo mette al bar e copre il suo posto in sala
            con una Lunga a chi ne ha meno (se serve annullare un riposo, te lo chiede prima).</p>
          <p style={{ margin: 0 }}><b>📋 Vista griglia</b>: menu a tendina con tutti i turni, 🖌 pennello per compilare veloce e trascinamento ⠿ per riordinare le righe.
            I dipendenti vedono questa stessa settimana dal portale (sola lettura) e da lì mandano le preferenze di riposo.</p>
        </div>
      </details>

      <div style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <button onClick={() => setLunedi(d => { const n = new Date(d); n.setDate(d.getDate() - 7); return n; })} className="dc-btn" aria-label="Settimana precedente">‹</button>
        <strong style={{ minWidth: 150, textAlign: "center" }}>{meseLabel}</strong>
        <button onClick={() => setLunedi(d => { const n = new Date(d); n.setDate(d.getDate() + 7); return n; })} className="dc-btn" aria-label="Settimana successiva">›</button>
        <button onClick={() => setLunedi(lunOggi)} className="dc-btn" style={{ fontSize: 12 }}>Oggi</button>
        <button onClick={() => setVista(v => (v === "semplice" ? "tabella" : "semplice"))} className="dc-btn"
          style={{ marginLeft: "auto", padding: "10px 16px", borderRadius: 10, fontWeight: 600 }}
          title="Passa tra la vista semplice a caselle e la griglia completa con i menu">
          {vista === "semplice" ? "📋 Vista griglia" : "✨ Vista semplice"}
        </button>
        <button onClick={apriCfg} className="dc-btn"
          style={{ padding: "10px 16px", borderRadius: 10, fontWeight: 600 }}>
          ⚙️ Configura turni
        </button>
        <button onClick={apriSost} disabled={busy} className="dc-btn"
          style={{ padding: "10px 16px", borderRadius: 10, fontWeight: 600 }} title="Sostituzione d'emergenza: malattia/assenza e chi copre">
          🚨 Sostituzione
        </button>
        {vista === "tabella" && (
        <button onClick={() => { setPaint(p => !p); if (!paint && !penTurno && turni[0]) setPenTurno(turni[0].id); }} className="dc-btn"
          style={{ padding: "10px 16px", borderRadius: 10, fontWeight: 600, background: paint ? "#5b7a6b" : undefined, color: paint ? "#fff" : undefined }}
          title="Pennello: scegli un turno e clicca le celle per compilarle veloce">
          🖌 Pennello {paint ? "ON" : ""}
        </button>
        )}
        <button onClick={generaProduzione} disabled={busy}
          style={{ background: "#5b7a6b", color: "#fff", border: "none", padding: "10px 18px", borderRadius: 10, fontWeight: 600, cursor: busy ? "default" : "pointer", opacity: busy ? 0.6 : 1 }}>
          {busy ? "Attendi…" : "Genera settimana"}
        </button>
      </div>

      {vista === "tabella" && paint && (
        <div className="dc-card" style={{ marginBottom: 12, padding: 12, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, color: "#6b7669", fontWeight: 600 }}>Pennello — scegli il turno, poi clicca le celle:</span>
          <button type="button" onClick={() => setPenTurno("")}
            style={{ border: penTurno === "" ? "3px solid #5b7a6b" : "1px solid #e6e0d4", background: "#fff", color: "#495247", borderRadius: 8, padding: "5px 10px", fontWeight: 700, cursor: "pointer", fontSize: 13 }}>
            – (vuoto)
          </button>
          {turni.map(t => (
            <button key={t.id} type="button" onClick={() => setPenTurno(t.id)}
              style={{ border: penTurno === t.id ? "3px solid #5b7a6b" : "1px solid #e6e0d4", background: penTurno === t.id ? t.colore : t.colore + "30", color: penTurno === t.id ? "#fff" : "#495247", borderRadius: 8, padding: "5px 10px", fontWeight: 700, cursor: "pointer", fontSize: 13 }}>
              {t.nome}
            </button>
          ))}
        </div>
      )}

      {showCfg && (
        <Modal title="Configura turni dipendenti" onClose={() => setShowCfg(false)} maxWidth={1080}>
          <div className="dc-modal-body">
            <p className="dc-muted" style={{ fontSize: 13, marginTop: 0 }}>
              Una card per dipendente: scegli la <b>modalità</b> (Sala, Bar in rotazione o Turno fisso),
              poi tocca i giorni per <b>riposo fisso</b> e <b>Lunga</b>. Queste sono le "sponde" usate
              da "Genera settimana" e dalla vista semplice.
            </p>
            <div style={{ background: "#eef1ea", border: "1px solid #d7e0d3", borderRadius: 10, padding: "10px 14px", marginBottom: 12 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700, fontSize: 14 }}>
                <input type="checkbox" checked={chiusuraPom.attiva} onChange={e => setChiusuraPom(cp => ({ ...cp, attiva: e.target.checked }))} />
                🌙 Bar chiuso di pomeriggio nel periodo
              </label>
              <p className="dc-muted" style={{ fontSize: 12.5, margin: "4px 0 8px" }}>
                Nel periodo scelto i baristi in rotazione mantengono i turni regolari (2 di mattina
                Bar 6:30-15 e 2 di pomeriggio Bar 15-21) ma la domenica riposano tutti;
                la settimana precedente all'inizio salta il riposo infrasettimanale (il riposo arriva con
                la domenica di chiusura). Fuori dal periodo vale la regola normale: il gruppo di pomeriggio
                riposa la domenica (un gruppo lavora 7 giorni, l'altro 6).
              </p>
              {chiusuraPom.attiva && (
                <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
                  <div style={{ minWidth: 150 }}>
                    <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>Dal</label>
                    <MiniCalendario value={chiusuraPom.dal} onChange={v => setChiusuraPom(cp => ({ ...cp, dal: v }))} />
                  </div>
                  <div style={{ minWidth: 150 }}>
                    <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>Al</label>
                    <MiniCalendario value={chiusuraPom.al} onChange={v => setChiusuraPom(cp => ({ ...cp, al: v }))} />
                  </div>
                </div>
              )}
            </div>
            <div style={{ maxHeight: "58vh", overflow: "auto", padding: 2 }}>
              {[["rot", "☕ Baristi — rotazione mattina↔pomeriggio"], ["sala", "🍽 Camerieri — sala"], ["fisso", "🕐 Turno fisso / altro"]].map(([gruppoModo, titoloGruppo]) => {
                const gruppo = cfgRows.map((r, i) => ({ r, i }))
                  .filter(({ r }) => (r.sala ? "sala" : (r.rotazione ? "rot" : "fisso")) === gruppoModo);
                if (!gruppo.length) return null;
                return (
              <div key={gruppoModo}>
                <div style={{ fontWeight: 800, fontSize: 13, color: "#3f5a4e", margin: "14px 2px 8px", textTransform: "uppercase", letterSpacing: ".5px" }}>{titoloGruppo}</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(310px, 1fr))", gap: 12 }}>
                {gruppo.map(({ r, i }) => {
                  const modo = r.sala ? "sala" : (r.rotazione ? "rot" : "fisso");
                  const pill = (on) => ({ border: on ? "2px solid #3f5a4e" : "1px solid #e6e0d4", background: on ? "#3f5a4e" : "#fff",
                    color: on ? "#fff" : "#2a3329", borderRadius: 999, padding: "5px 11px", fontSize: 12, fontWeight: 700, cursor: "pointer" });
                  const chipG = (on) => ({ border: on ? "2px solid #5b7a6b" : "1px solid #e6e0d4", background: on ? "#5b7a6b" : "#fff",
                    color: on ? "#fff" : "#2a3329", borderRadius: 8, padding: "4px 8px", fontSize: 11.5, fontWeight: 700, cursor: "pointer" });
                  const cap = { fontSize: 11, color: "#6b7669", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".4px", margin: "10px 0 5px" };
                  return (
                    <div key={r.dipendente_id} style={{ border: "1px solid #e6e0d4", background: "#fffefb", borderRadius: 14, padding: 12, boxShadow: "0 2px 8px rgba(63,90,78,.06)" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Avatar nome={r.nome} size="sm" />
                        <b style={{ fontSize: 14, flex: 1 }}>{r.nome}</b>
                        <span style={{ fontSize: 11, fontWeight: 700, color: "#3f5a4e", background: "#eef1ea", border: "1px solid #d7e0d3", borderRadius: 999, padding: "3px 9px" }}>
                          {modo === "sala" ? "🍽 Sala" : modo === "rot" ? "☕ Barista" : "🕐 Fisso"}
                        </span>
                      </div>
                      <details style={{ marginTop: 8 }}>
                        <summary className="dc-muted" style={{ cursor: "pointer", fontSize: 12 }}>cambia modalità</summary>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                          <button type="button" style={pill(modo === "sala")} title="Cameriere: rotazione automatica 2 Lunga / 2 Mattina / 2 Pomeriggio / 1 Riposo"
                            onClick={() => patchCfgRow(i, { sala: true, rotazione: "" })}>🍽 Sala</button>
                          <button type="button" style={pill(modo === "rot")} title="Barista: alterna ogni settimana mattina e pomeriggio"
                            onClick={() => patchCfgRow(i, { sala: false, rotazione: r.rotazione || "mattina", turno_id: "", rotazione_ancora: r.rotazione_ancora || settimana })}>☕ Bar mattina↔pom</button>
                          <button type="button" style={pill(modo === "fisso")} title="Sempre lo stesso turno"
                            onClick={() => patchCfgRow(i, { sala: false, rotazione: "" })}>🕐 Turno fisso</button>
                        </div>
                      </details>
                      {modo === "rot" && (
                        <div style={{ marginTop: 8 }}>
                          <div style={{ display: "flex", gap: 6 }}>
                            <button type="button" style={chipG(r.rotazione === "mattina")}
                              onClick={() => patchCfgRow(i, { rotazione: "mattina", rotazione_ancora: settimana })}>☀️ ora mattina</button>
                            <button type="button" style={chipG(r.rotazione === "pomeriggio")}
                              onClick={() => patchCfgRow(i, { rotazione: "pomeriggio", rotazione_ancora: settimana })}>🌆 ora pomeriggio</button>
                          </div>
                          <div className="dc-muted" style={{ fontSize: 11, marginTop: 4 }}>
                            Vale per la settimana che stai guardando ({settimana.split("-").reverse().join("/")}):
                            dal lunedì dopo il sistema inverte da solo, ogni settimana.
                          </div>
                        </div>
                      )}
                      {modo === "fisso" && (
                        <select className="dc-input" style={{ marginTop: 8 }} value={r.turno_id} onChange={e => setCfgRow(i, "turno_id", e.target.value)}>
                          <option value="">— nessun turno —</option>
                          {turni.map(t => <option key={t.id} value={t.id}>{t.nome}</option>)}
                        </select>
                      )}
                      <div style={cap}>Riposo fisso <span style={{ fontWeight: 400, textTransform: "none" }}>(tocca per scegliere)</span></div>
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {giorni.map(g => (
                          <button key={g} type="button" style={chipG(r.riposo_giorno === g)}
                            onClick={() => setCfgRow(i, "riposo_giorno", r.riposo_giorno === g ? "" : g)}>{g.slice(0, 3)}</button>
                        ))}
                      </div>
                      {modo !== "rot" && (<>
                        <div style={cap}>Lunga <span style={{ fontWeight: 400, textTransform: "none" }}>(fino a 2 giorni tra Ven/Sab/Dom)</span></div>
                        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                          {LUNGA_GIORNI.map(g => {
                            const on = r.lunga1 === g || (r.doppia && r.lunga2 === g);
                            return <button key={g} type="button" style={chipG(on)} onClick={() => toggleLungaCfg(i, g)}>{g.slice(0, 3)}</button>;
                          })}
                        </div>
                        <label style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 10, fontSize: 12.5, fontWeight: 600 }}
                          title="Se assente un barista, questo dipendente può offrirsi dal portale per coprire il bar (dal-al + fascia)">
                          <input type="checkbox" checked={!!r.sostituto_bar} onChange={e => setCfgRow(i, "sostituto_bar", e.target.checked)} />
                          🆘 Può coprire il bar (sostituzioni)
                        </label>
                      </>)}
                      <div style={cap}>Onomastico 🎂</div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                        <input className="dc-input" style={{ width: 52, display: "inline-block" }} type="number" min="1" max="31" placeholder="gg" value={r.onom_giorno ?? ""} onChange={e => setCfgRow(i, "onom_giorno", e.target.value)} />
                        <span>/</span>
                        <input className="dc-input" style={{ width: 52, display: "inline-block" }} type="number" min="1" max="12" placeholder="mm" value={r.onom_mese ?? ""} onChange={e => setCfgRow(i, "onom_mese", e.target.value)} />
                        <label style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 4 }} title="Nel giorno dell'onomastico il dipendente è a riposo">
                          <input type="checkbox" checked={!!r.onom_attivo} onChange={e => setCfgRow(i, "onom_attivo", e.target.checked)} /> riposo attivo
                        </label>
                      </div>
                    </div>
                  );
                })}
                </div>
              </div>
                );
              })}
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
              <button className="dc-btn" onClick={() => setShowCfg(false)}>Chiudi</button>
              <button className="dc-btn-primary" onClick={salvaCfg}>Salva</button>
            </div>
          </div>
        </Modal>
      )}

      {showSost && (
        <Modal title="Sostituzione d'emergenza" onClose={() => setShowSost(false)} maxWidth={520}>
          <div className="dc-modal-body">
            <p className="dc-muted" style={{ fontSize: 13, marginTop: 0 }}>
              Segna chi è assente e il motivo: la <b>malattia</b> viene registrata nelle Presenze (con protocollo), ferie/permesso/assenza liberano il turno. Poi scegli chi lo copre: gli assegno il turno scelto (di default la <b>Lunga</b> = doppia) in quel giorno.
            </p>
            <div style={{ display: "grid", gap: 12 }}>
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: "#3b4a40" }}>Dipendente assente</label>
                <select className="dc-input" style={{ width: "100%" }} value={sost.assente} onChange={e => setSost(s => ({ ...s, assente: e.target.value }))}>
                  <option value="">— scegli —</option>
                  {dipTurni.map(d => <option key={d.id} value={d.id}>{`${d.cognome || ''} ${d.nome || ''}`.trim() || d.nome}</option>)}
                </select>
              </div>
              <div style={{ display: "flex", gap: 10 }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "#3b4a40" }}>Giorno</label>
                  <select className="dc-input" style={{ width: "100%" }} value={sost.giorno} onChange={e => setSostGiorno(e.target.value)}>
                    {giorni.map(g => <option key={g} value={g}>{g}</option>)}
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "#3b4a40" }}>Motivo</label>
                  <select className="dc-input" style={{ width: "100%" }} value={sost.motivo} onChange={e => setSost(s => ({ ...s, motivo: e.target.value }))}>
                    <option value="malattia">Malattia</option>
                    <option value="assenza">Assenza</option>
                    <option value="ferie">Ferie</option>
                    <option value="permesso">Permesso</option>
                  </select>
                </div>
              </div>
              {sost.assente && sost.giorno && (() => {
                const cur = getAssegnazione(sost.assente, sost.giorno);
                const n = cur && nomeTurno(cur.turno_id);
                return <div className="dc-muted" style={{ fontSize: 12 }}>Turno attuale di quel giorno: <b>{n || "—"}</b></div>;
              })()}
              {sost.motivo === "malattia" && (
                <div style={{ background: "#fdf6ec", border: "1px solid #f0e0c4", borderRadius: 10, padding: 12, display: "grid", gap: 10 }}>
                  <div className="dc-muted" style={{ fontSize: 12 }}>
                    La malattia <b>non è un riposo</b>: viene segnata come <b>Malattia (M)</b> nelle Presenze mensili. Inserisci il <b>numero di protocollo</b> del certificato medico telematico (PUC) che dà il medico.
                  </div>
                  <div>
                    <label style={{ fontSize: 12, fontWeight: 600, color: "#3b4a40" }}>Numero di protocollo (certificato medico)</label>
                    <input className="dc-input" style={{ width: "100%" }} value={sost.protocollo} onChange={e => setSost(s => ({ ...s, protocollo: e.target.value }))} placeholder="es. 1234567890123" />
                  </div>
                  <div style={{ display: "flex", gap: 10 }}>
                    <div style={{ flex: 1 }}>
                      <label style={{ fontSize: 12, fontWeight: 600, color: "#3b4a40" }}>Dal</label>
                      <input type="date" className="dc-input" style={{ width: "100%" }} value={sost.dal} onChange={e => setSost(s => ({ ...s, dal: e.target.value }))} />
                    </div>
                    <div style={{ flex: 1 }}>
                      <label style={{ fontSize: 12, fontWeight: 600, color: "#3b4a40" }}>Al (fine prognosi)</label>
                      <input type="date" className="dc-input" style={{ width: "100%" }} value={sost.al} onChange={e => setSost(s => ({ ...s, al: e.target.value }))} />
                    </div>
                  </div>
                </div>
              )}
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: "#3b4a40" }}>Chi lo copre (sostituto)</label>
                <select className="dc-input" style={{ width: "100%" }} value={sost.sostituto} onChange={e => setSost(s => ({ ...s, sostituto: e.target.value }))}>
                  <option value="">— nessuno (lascio scoperto) —</option>
                  {dipTurni.filter(d => d.id !== sost.assente).map(d => <option key={d.id} value={d.id}>{`${d.cognome || ''} ${d.nome || ''}`.trim() || d.nome}</option>)}
                </select>
              </div>
              {sost.sostituto && (
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "#3b4a40" }}>Turno del sostituto</label>
                  <select className="dc-input" style={{ width: "100%" }} value={sost.turnoSost} onChange={e => setSost(s => ({ ...s, turnoSost: e.target.value }))}>
                    {turni.map(t => <option key={t.id} value={t.id}>{t.nome}</option>)}
                  </select>
                </div>
              )}
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
              <button className="dc-btn" onClick={() => setShowSost(false)}>Annulla</button>
              <button className="dc-btn-primary" onClick={confermaSost} disabled={busy}>Conferma sostituzione</button>
            </div>
          </div>
        </Modal>
      )}

      <div className="dc-card" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <h3 style={{ margin: 0 }}>🎂 Onomastici di questa settimana</h3>
          <button className="dc-btn" onClick={apriCfg}>Gestisci (turni & onomastici)</button>
        </div>
        {onomSett.length === 0
          ? <p className="dc-muted" style={{ marginBottom: 0, marginTop: 8 }}>Nessun onomastico nei giorni lavorativi di questa settimana.</p>
          : (
            <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
              {onomSett.map((o, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, borderTop: "1px solid #eee", paddingTop: 8, flexWrap: "wrap" }}>
                  <span>🎂 <b>{o.nome}</b> · {o.giorno_nome} {o.data_label} — a riposo</span>
                  <button className="dc-btn" disabled={busy} onClick={() => mettiRiposoOnom(o)}>Rimetti a riposo</button>
                </div>
              ))}
            </div>
          )}
        <p className="dc-muted" style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}>Il riposo è impostato automaticamente nel giorno dell'onomastico (marcato 🎂 nella griglia). Se ti serve copertura, basta riassegnare un turno in quella cella: la tua scelta ha la precedenza.</p>
      </div>

      {prefRiposo.length > 0 && (
        <div className="dc-card" style={{ marginBottom: 12 }}>
          <h3 style={{ marginTop: 0 }}>💤 Preferenze di riposo ricevute dal portale</h3>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {prefRiposo.map((p, i) => (
              <span key={i} style={{ background: "#eef1ea", border: "1px solid #d7e0d3", borderRadius: 999, padding: "5px 12px", fontSize: 13, fontWeight: 600 }}>
                {p.nome || "Dipendente"} → {p.giorno}
              </span>
            ))}
          </div>
          <p className="dc-muted" style={{ fontSize: 12, margin: "8px 0 0" }}>
            "Genera settimana" mette il Riposo nel giorno preferito (segnato 💤 nelle caselle); la tua modifica a mano ha sempre la precedenza.
          </p>
        </div>
      )}

      {dispBar.length > 0 && (
        <div className="dc-card" style={{ marginBottom: 12 }}>
          <h3 style={{ marginTop: 0 }}>🆘 Disponibili a coprire il bar</h3>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {dispBar.map((d, i) => (
              <span key={i} style={{ background: "#f6efe2", border: "1px solid #e6d9bd", borderRadius: 999, padding: "5px 12px", fontSize: 13, fontWeight: 600 }}>
                {d.nome || "Dipendente"} → bar {d.fascia === "pomeriggio" ? "🌆 pomeriggio" : "☀️ mattina"}{d.sostituisce_nome ? ` · al posto di ${d.sostituisce_nome}` : ""} · dal {d.dal.split("-").reverse().join("/")} al {d.al.split("-").reverse().join("/")}
              </span>
            ))}
          </div>
          <p className="dc-muted" style={{ fontSize: 12, margin: "8px 0 0" }}>
            "Genera settimana" li mette al bar nella fascia scelta e copre il loro posto in sala con una
            Lunga (a chi ne ha meno); se serve annullare un riposo te lo chiede prima.
          </p>
        </div>
      )}

      {vista === "semplice" ? (
      <div className="dc-card dc-scroll-x" style={{ paddingBottom: 8 }}>
        <div style={{ display: "grid", gridTemplateColumns: "180px repeat(7, minmax(88px, 1fr))", gap: 6, minWidth: 860, alignItems: "stretch" }}>
          <div style={{ alignSelf: "end", fontSize: 12, color: "#6b7669", fontWeight: 700, padding: "0 4px 6px" }}>Copertura ☀️ / 🌆 →</div>
          {giorni.map((g, i) => { const c = coperturaDi(g); return (
            <div key={g} style={{ textAlign: "center", paddingBottom: 6 }}>
              <div style={{ fontWeight: 700, fontSize: 13 }}>{g.slice(0, 3)} {dataDi(i)}</div>
              <div style={{ fontSize: 12, display: "flex", gap: 8, justifyContent: "center" }}>
                <span style={{ fontWeight: 700, color: c.mattina ? "#3f5a4e" : "#b3261e" }}>☀️ {c.mattina}</span>
                <span style={{ fontWeight: 700, color: c.pomeriggio ? "#8a6d3b" : "#b3261e" }}>🌆 {c.pomeriggio}</span>
              </div>
            </div>); })}
          {dipTurni.map(dip => (
            <Fragment key={dip.id}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 4px 0", borderTop: "1px solid #f0ece1" }}>
                <Avatar nome={dip.nome} cognome={dip.cognome} size="sm" />
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {dip.cognome ? `${dip.cognome} ${dip.nome?.[0] || ""}.` : dip.nome}
                  </div>
                  <div style={{ fontSize: 10.5, color: "#6b7669", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                    title={`Sponde: ${spondeDi(dip).map(id => nomeTurno(id)).join(" · ")}`}>
                    {(() => { const c = cfgDi(dip.id); return c.sala ? "Sala (rotazione)" : c.rotazione ? "Bar (rotazione)" : nomeTurno(c.turno_id) || "senza sponde"; })()}
                  </div>
                </div>
              </div>
              {giorni.map(g => { const ass = getAssegnazione(dip.id, g); const t = ass ? getTurno(ass.turno_id) : null; return (
                <button key={g} type="button" onClick={() => ciclaTurno(dip, g)}
                  title={`${dip.cognome || dip.nome} · ${g}: clicca per il turno successivo (${spondeDi(dip).map(id => nomeTurno(id)).join(" · ")} · vuoto)`}
                  style={{ position: "relative", border: `2px solid ${t ? t.colore : "#e6e0d4"}`,
                    background: t ? t.colore + "30" : "#fffefb", color: "#2a3329", borderRadius: 10,
                    fontWeight: 700, fontSize: 12, padding: "10px 2px", cursor: "pointer", minHeight: 46 }}>
                  {ass?.motivo === "onomastico" && <span style={{ position: "absolute", top: 0, right: 3, fontSize: 10 }}>🎂</span>}
                  {prefDi(dip.id) === g && <span title="Giorno di riposo preferito (dal portale)" style={{ position: "absolute", top: 0, left: 3, fontSize: 10 }}>💤</span>}
                  {t ? t.nome : "—"}
                </button>); })}
            </Fragment>
          ))}
        </div>
        <p className="dc-muted" style={{ fontSize: 12, margin: "10px 4px 0" }}>
          Un click sulla casella = turno successivo tra le <b>sponde</b> del dipendente (i suoi turni possibili, poi Riposo, Ferie, vuoto) — impostale in "⚙️ Configura turni".
          In alto la <b>copertura</b>: persone al mattino ☀️ e al pomeriggio 🌆 (la Lunga conta per entrambi); rosso = fascia scoperta.
        </p>
      </div>
      ) : (
      <div className="dc-card dc-scroll-x">
        <table className="dc-table dc-turni-table">
          <thead>
            <tr>
              <th style={{ width: 24 }}></th>
              <th>DIPENDENTE</th>
              {giorni.map((g, i) => <th key={g}>{g} {dataDi(i)}</th>)}
            </tr>
          </thead>
          <tbody ref={tbodyRef}>
            {dipTurni.map(dip => (
              <tr key={dip.id} data-id={dip.id}>
                <td className="dc-drag-handle" style={{ cursor: "grab", color: "#9aa593", textAlign: "center", userSelect: "none", touchAction: "none" }} title="Trascina per riordinare">⠿</td>
                <td>
                  <div className="dc-table-user">
                    <Avatar nome={dip.nome} cognome={dip.cognome} size="sm" />
                    <span>{dip.cognome ? `${dip.cognome} ${dip.nome?.[0] || ''}.` : dip.nome}</span>
                  </div>
                </td>
                {giorni.map(g => {
                  const ass = getAssegnazione(dip.id, g);
                  const turno = ass ? getTurno(ass.turno_id) : null;
                  return (
                    <td key={g} style={{ position: "relative" }}>
                      {ass?.motivo === "onomastico" && <span title="Riposo per onomastico" style={{ position: "absolute", top: 0, right: 2, fontSize: 11, zIndex: 1 }}>🎂</span>}
                      {paint ? (
                        <button type="button" onClick={() => handleAssegna(dip, g, penTurno)} title="Clicca per applicare il turno del pennello"
                          className="dc-turno-select"
                          style={{ cursor: "pointer", textAlign: "center", width: "100%",
                            backgroundColor: turno ? turno.colore + '30' : "#fff",
                            borderColor: turno ? turno.colore : "#e6e0d4" }}>
                          {turno ? turno.nome : "-"}
                        </button>
                      ) : (
                        <select
                          value={ass?.turno_id || ""}
                          onChange={e => handleAssegna(dip, g, e.target.value)}
                          className="dc-turno-select"
                          style={{
                            ...(turno ? { backgroundColor: turno.colore + '30', borderColor: turno.colore } : {}),
                            ...(evid ? (ass?.turno_id === evid
                              ? { outline: "3px solid " + ((getTurno(evid) || {}).colore || "#5b7a6b"), opacity: 1 }
                              : { opacity: 0.2 }) : {})
                          }}
                        >
                          <option value="">-</option>
                          {turni.map(t => <option key={t.id} value={t.id}>{t.nome}</option>)}
                        </select>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
    </div>
  );
}

// Buste Paga Page
function MiniCalendario({ value, onChange }) {
  const [aperto, setAperto] = useState(false);
  const base = value ? new Date(value + "T00:00:00") : new Date();
  const [vista, setVista] = useState({ anno: base.getFullYear(), mese: base.getMonth() });
  const ref = useRef(null);

  useEffect(() => {
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setAperto(false); };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const meseNomi = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"];
  const giorniSett = ["L", "M", "M", "G", "V", "S", "D"];
  const primoDelMese = new Date(vista.anno, vista.mese, 1);
  const ultimoGiorno = new Date(vista.anno, vista.mese + 1, 0).getDate();
  const offset = (primoDelMese.getDay() + 6) % 7; // lunedì = 0
  const celle = [...Array(offset).fill(null), ...Array.from({ length: ultimoGiorno }, (_, i) => i + 1)];

  const isoGiorno = (g) => `${vista.anno}-${String(vista.mese + 1).padStart(2, "0")}-${String(g).padStart(2, "0")}`;
  const scegli = (g) => { onChange(isoGiorno(g)); setAperto(false); };
  const cambiaMese = (delta) => setVista(v => {
    const m = v.mese + delta;
    if (m < 0) return { anno: v.anno - 1, mese: 11 };
    if (m > 11) return { anno: v.anno + 1, mese: 0 };
    return { ...v, mese: m };
  });

  const btnStyle = { border: "1px solid #c7cfc2", borderRadius: 8, padding: "7px 9px", fontSize: 14, width: "100%", boxSizing: "border-box", textAlign: "left", cursor: "pointer", background: "#fff", color: value ? "#2a3329" : "#9aa39a" };

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button type="button" onClick={() => setAperto(a => !a)} style={btnStyle}>
        {value ? formatDate(value) : "Scegli data"}
      </button>
      {aperto && (
        <div style={{ position: "absolute", top: "100%", left: 0, marginTop: 4, background: "#fffefb", border: "1px solid #e6e0d4", borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,.18)", padding: 10, zIndex: 60, width: 232 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <button type="button" className="dc-btn" style={{ padding: "2px 8px" }} onClick={() => cambiaMese(-1)} aria-label="Mese precedente">‹</button>
            <b style={{ fontSize: 13 }}>{meseNomi[vista.mese]} {vista.anno}</b>
            <button type="button" className="dc-btn" style={{ padding: "2px 8px" }} onClick={() => cambiaMese(1)} aria-label="Mese successivo">›</button>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", gap: 2, fontSize: 11, textAlign: "center" }}>
            {giorniSett.map((g, i) => <div key={i} className="dc-muted" style={{ fontWeight: 700 }}>{g}</div>)}
            {celle.map((g, i) => {
              const attivo = g && isoGiorno(g) === value;
              return (
                <button type="button" key={i} disabled={!g} onClick={() => g && scegli(g)} style={{
                  padding: "5px 0", border: "none", borderRadius: 6, cursor: g ? "pointer" : "default",
                  background: attivo ? "#5b7a6b" : "transparent", color: attivo ? "#fff" : g ? "#2a3329" : "transparent",
                  fontWeight: attivo ? 700 : 400, fontSize: 12.5,
                }}>{g || "·"}</button>
              );
            })}
          </div>
          {value && (
            <button type="button" className="dc-btn" style={{ width: "100%", marginTop: 8, fontSize: 12 }}
              onClick={() => { onChange(""); setAperto(false); }}>Pulisci</button>
          )}
        </div>
      )}
    </div>
  );
}

// Minimi tabellari CCNL Pubblici Esercizi/Turismo (Confcommercio-FIPE, rinnovo
// 5/6/2024 — terza tranche dal 1/6/2026, fonte Confcommercio Milano; mansioni
// dalle declaratorie di classificazione del personale).
// [livello, paga base, contingenza, totale mensile, mansioni tipiche] — da
// ricontrollare a ogni rinnovo.
const CCNL_LIVELLI_2026 = [
  ["Quadro A", 1920.26, 542.70, 2462.96, "quadri direttivi"],
  ["Quadro B", 1734.02, 537.59, 2271.61, "quadri"],
  ["1º", 1570.97, 536.71, 2107.68, "direttore, capo servizi"],
  ["2º", 1384.76, 531.59, 1916.35, "capo cuoco, capo barista"],
  ["3º", 1272.47, 528.26, 1800.73, "cuoco unico, primo pasticciere, barman unico"],
  ["4º", 1167.75, 524.94, 1692.69, "cuoco tavola calda/capo partita, secondo pasticciere, rosticciere, barman"],
  ["5º", 1057.72, 522.37, 1580.09, "barista, cameriere (anche tavola calda), banconiere pasticceria/gelateria"],
  ["6º S", 994.19, 520.64, 1514.83, "operai qualificati super"],
  ["6º", 971.06, 520.51, 1491.57, "commis cucina/sala/bar, secondo banconiere pasticceria"],
  ["7º", 871.75, 518.45, 1390.20, "personale di fatica / primo ingresso"],
];

// TFR — situazione ufficiale (calcolo automatico dai cedolini) + simulatore
// storico periodo per periodo, per ricostruire il TFR maturato prima dell'app.
function TfrPage({ dipendenti, getDipendente }) {
  const API_TFR = "/hr/api/tfr";
  const eur = (n) => (Number(n) || 0).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const [dipId, setDipId] = useState(dipendenti[0]?.id || "");
  const [situazione, setSituazione] = useState(null);
  const [sim, setSim] = useState(null);
  const [loading, setLoading] = useState(false);
  const [errore, setErrore] = useState("");

  const [formPeriodo, setFormPeriodo] = useState({ data_inizio: "", data_fine: "", importo_settimanale: "" });
  const [salvandoPeriodo, setSalvandoPeriodo] = useState(false);
  const [comeChiuso, setComeChiuso] = useState(false); // avanzato: inserisci uno storico già chiuso

  const [numeroRate, setNumeroRate] = useState(3);
  const [dataPrimaRata, setDataPrimaRata] = useState("");
  const [rate, setRate] = useState(null);

  const [liquidazione, setLiquidazione] = useState(null);
  const [acconti, setAcconti] = useState(null);          // acconti TFR già erogati (sistema unico acconti_dipendenti)
  const [formAcconto, setFormAcconto] = useState({ data: "", importo: "", note: "" });
  const [scalaGiorni, setScalaGiorni] = useState("");

  const [nlForm, setNlForm] = useState({ importo: "", superminimo: "", settimane: "52", mesi: "12" });
  const [nlEsito, setNlEsito] = useState(null);
  const [nlLivello, setNlLivello] = useState("");
  // Superminimo: si somma al lordo tabellare e paga contributi e IRPEF come il resto.
  // È espresso in €/MESE e viene convertito in settimanale (× 12 ÷ 52).
  const smSettimanale = (f) => {
    const sm = Number(String(f.superminimo || "0").replace(",", "."));
    return isNaN(sm) ? 0 : Math.round((sm * 12 / 52) * 100) / 100;
  };
  const calcolaNetto = async (form = nlForm) => {
    if (!form.importo || !form.settimane || !form.mesi) return;
    setNlEsito(null);
    try {
      const lordoSett = Math.round((Number(String(form.importo).replace(",", ".")) + smSettimanale(form)) * 100) / 100;
      const r = await axios.post(`${API_TFR}/calcolo-netto-da-lordo`, {
        importo_settimanale_lordo: lordoSett,
        settimane_lavorate: Number(form.settimane),
        mesi_lavorati: Number(form.mesi),
      });
      setNlEsito({ ...r.data, superminimo_mese: Number(String(form.superminimo || "0").replace(",", ".")) || 0, lordo_settimanale_totale: lordoSett });
    } catch (e) { setNlEsito({ errore: e?.response?.data?.detail || "Errore nel calcolo" }); }
  };
  // Calcolo inverso: dal NETTO mensile desiderato → lordo settimanale e tutto il resto
  const [lnForm, setLnForm] = useState({ netto: "", settimane: "52", mesi: "12" });
  const [lnEsito, setLnEsito] = useState(null);
  const calcolaLordo = async () => {
    const netto = Number(String(lnForm.netto).replace(",", "."));
    if (!netto) return;
    setLnEsito(null);
    try {
      const r = await axios.post(`${API_TFR}/calcolo-lordo-da-netto`, {
        netto_mensile_desiderato: netto,
        settimane_lavorate: Number(lnForm.settimane) || 52,
        mesi_lavorati: Number(lnForm.mesi) || 12,
      });
      setLnEsito(r.data);
    } catch (e) { setLnEsito({ errore: e?.response?.data?.detail || "Errore nel calcolo" }); }
  };

  // Scegli la tariffa CCNL → il resto si calcola da solo (lordo settimanale + superminimo + netto)
  const usaLivelloCcnl = async (liv) => {
    setNlLivello(liv);
    const row = CCNL_LIVELLI_2026.find(r => r[0] === liv);
    if (!row) return;
    const sett = Math.round((row[3] * 12 / 52) * 100) / 100;
    const form = { ...nlForm, importo: String(sett) };
    setNlForm(form);
    await calcolaNetto(form);
  };

  const carica = useCallback(async (id) => {
    if (!id) return;
    setLoading(true); setErrore(""); setRate(null);
    try {
      const [s, sm] = await Promise.all([
        axios.get(`${API_TFR}/situazione/${id}`),
        axios.get(`${API_TFR}/simulazione/${id}`),
      ]);
      setSituazione(s.data);
      setSim(sm.data);
      setFormPeriodo({ data_inizio: sm.data.prossimo_data_inizio || "", data_fine: "", importo_settimanale: "" });
      setComeChiuso(false);
      try {
        const l = await axios.get(`${API_TFR}/simulazione/${id}/liquidazione`);
        setLiquidazione(l.data);
      } catch { setLiquidazione(null); }
      try {
        const a = await axios.get(`${API_TFR}/acconti/${id}`);
        setAcconti(a.data);
      } catch { setAcconti(null); }
    } catch (e) {
      setErrore(e?.response?.data?.detail || "Errore nel caricamento");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { carica(dipId); }, [dipId, carica]);

  const aggiungiPeriodo = async () => {
    if (!formPeriodo.importo_settimanale || (comeChiuso && !formPeriodo.data_fine)) return;
    setSalvandoPeriodo(true); setErrore("");
    try {
      await axios.post(`${API_TFR}/simulazione/${dipId}/periodi`, {
        data_inizio: formPeriodo.data_inizio || undefined,
        data_fine: comeChiuso ? formPeriodo.data_fine : undefined,
        importo_settimanale: Number(formPeriodo.importo_settimanale),
      });
      await carica(dipId);
    } catch (e) { setErrore(e?.response?.data?.detail || "Errore nel salvataggio del periodo"); }
    finally { setSalvandoPeriodo(false); }
  };

  // Valori manuali della liquidazione (13ª, 14ª, giorni ferie): null = torna al calcolo automatico
  const salvaOverride = async (campo, valore) => {
    try {
      await axios.put(`${API_TFR}/simulazione/${dipId}/liquidazione-override`, { [campo]: valore });
      const l = await axios.get(`${API_TFR}/simulazione/${dipId}/liquidazione`);
      setLiquidazione(l.data);
    } catch (e) { setErrore(e?.response?.data?.detail || "Errore nel salvataggio"); }
  };

  const ricaricaAcconti = async () => {
    try { const a = await axios.get(`${API_TFR}/acconti/${dipId}`); setAcconti(a.data); } catch { /* niente */ }
  };
  const registraAcconto = async () => {
    const importo = Number(String(formAcconto.importo).replace(",", "."));
    if (!importo) return;
    try {
      await axios.post(`${API_TFR}/acconti`, {
        dipendente_id: dipId, tipo: "tfr", importo,
        data: formAcconto.data || new Date().toISOString().slice(0, 10),
        note: formAcconto.note || "Acconto TFR (dal simulatore)",
      });
      setFormAcconto({ data: "", importo: "", note: "" });
      await ricaricaAcconti();
    } catch (e) { setErrore(e?.response?.data?.detail || "Errore nel salvataggio dell'acconto"); }
  };
  const eliminaAcconto = async (accId) => {
    if (!window.confirm("Eliminare questo acconto TFR?")) return;
    try { await axios.delete(`${API_TFR}/acconti/${accId}`); await ricaricaAcconti(); }
    catch (e) { setErrore(e?.response?.data?.detail || "Errore nell'eliminazione dell'acconto"); }
  };

  // Report stampabile: periodi, totali, liquidazione, acconti e netto residuo
  const stampaReport = () => {
    const dip = dipendenti.find(d => d.id === dipId) || {};
    const nome = dip.nome_completo || `${dip.cognome || ""} ${dip.nome || ""}`.trim() || "Dipendente";
    const oggi = new Date().toLocaleDateString("it-IT");
    const righe = (sim?.periodi || []).map(p =>
      `<tr><td>${formatDate(p.data_inizio)}</td><td>${p.data_fine ? formatDate(p.data_fine) : "in corso"}</td>` +
      `<td class="n">€ ${eur(p.importo_settimanale)}</td><td class="n">${p.settimane}</td>` +
      `<td class="n">€ ${eur(p.retribuzione_utile)}</td><td class="n">€ ${eur(p.lordo)}</td>` +
      `<td class="n"><b>€ ${eur(p.netto)}</b></td></tr>`).join("");
    const accTfr = acconti?.acconti?.tfr || [];
    const totAcc = acconti?.tfr_acconti || 0;
    const residuo = (sim?.totale_netto || 0) - totAcc;
    const accRighe = accTfr.map(a => `<tr><td>${formatDate(a.data)}</td><td class="n">€ ${eur(a.importo)}</td><td>${a.note || ""}</td></tr>`).join("");
    const liq = liquidazione;
    const w = window.open("", "_blank");
    if (!w) { setErrore("Sblocca i popup per stampare il report"); return; }
    w.document.write(`<!DOCTYPE html><html lang="it"><head><meta charset="utf-8"><title>Report TFR — ${nome}</title>
<style>body{font-family:Georgia,'Times New Roman',serif;color:#2a3329;padding:28px;max-width:900px;margin:auto}
h1{font-size:20px;border-bottom:2px solid #5b7a6b;padding-bottom:6px;margin-bottom:4px}
h2{font-size:15px;color:#3f5a4e;margin:18px 0 6px}
table{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:4px}
th,td{border:1px solid #cbd5c9;padding:4px 6px;text-align:left}.n{text-align:right}
tfoot td{font-weight:bold;background:#eef1ea}.mini{font-size:11px;color:#6b7669}</style></head><body>
<h1>Report TFR — ${nome}</h1>
<div class="mini">Ceraldi Group S.r.l. · generato il ${oggi}${liq ? ` · calcolo fino al ${formatDate(liq.calcolato_fino_a)}` : ""}${liq?.cessato ? " · rapporto cessato" : ""}</div>
<h2>Periodi retributivi</h2>
<table><thead><tr><th>Dal</th><th>Al</th><th class="n">€/sett.</th><th class="n">Sett.</th><th class="n">Retrib. utile</th><th class="n">Lordo</th><th class="n">Netto</th></tr></thead>
<tbody>${righe}</tbody>
<tfoot><tr><td colspan="5">Totale (incluso il periodo in corso)</td><td class="n">€ ${eur(sim?.totale_lordo)}</td><td class="n">€ ${eur(sim?.totale_netto)}</td></tr></tfoot></table>
${liq ? `<h2>Liquidazione finale</h2><table>
<tr><td>Tredicesima maturata (${formatDate(liq.tredicesima.dal)} → ${formatDate(liq.tredicesima.al)})${liq.tredicesima.manuale ? " — inserita a mano" : ""}</td><td class="n">€ ${eur(liq.tredicesima.netto)}</td></tr>
<tr><td>Quattordicesima maturata (${formatDate(liq.quattordicesima.dal)} → ${formatDate(liq.quattordicesima.al)})${liq.quattordicesima.manuale ? " — inserita a mano" : ""}</td><td class="n">€ ${eur(liq.quattordicesima.netto)}</td></tr>
${liq.ferie ? `<tr><td>Ferie residue: ${liq.ferie.giorni_residui} gg × € ${eur(liq.ferie.paga_giornaliera)}/giorno${liq.ferie.manuale ? " — inserite a mano" : ""}</td><td class="n">€ ${eur(liq.ferie.controvalore)}</td></tr>` : ""}
</table>` : ""}
${accTfr.length ? `<h2>Acconti TFR già erogati</h2><table><thead><tr><th>Data</th><th class="n">Importo</th><th>Note</th></tr></thead><tbody>${accRighe}</tbody>
<tfoot><tr><td>Totale acconti</td><td class="n">€ ${eur(totAcc)}</td><td></td></tr></tfoot></table>` : ""}
<h2>Riepilogo</h2><table>
<tr><td>TFR lordo maturato</td><td class="n">€ ${eur(sim?.totale_lordo)}</td></tr>
<tr><td>= TFR netto simulato</td><td class="n">€ ${eur(sim?.totale_netto)}</td></tr>
<tr><td>− Acconti TFR erogati</td><td class="n">€ ${eur(totAcc)}</td></tr>
<tr><td><b>= TFR netto residuo</b></td><td class="n"><b>€ ${eur(residuo)}</b></td></tr>
${liq ? `<tr><td>+ Tredicesima maturata</td><td class="n">€ ${eur(liq.tredicesima.netto)}</td></tr>
<tr><td>+ Quattordicesima maturata</td><td class="n">€ ${eur(liq.quattordicesima.netto)}</td></tr>
${liq.ferie ? `<tr><td>${(liq.ferie.controvalore || 0) < 0 ? "−" : "+"} Ferie (${liq.ferie.giorni_residui} gg)</td><td class="n">€ ${eur(Math.abs(liq.ferie.controvalore || 0))}</td></tr>` : ""}
<tr><td><b>TOTALE COMPLESSIVO DA LIQUIDARE</b></td><td class="n"><b>€ ${eur(Math.round((residuo + liq.tredicesima.netto + liq.quattordicesima.netto + (liq.ferie?.controvalore || 0)) * 100) / 100)}</b></td></tr>` : ""}
${rate?.rate?.length ? `<tr><td>Pagamento concordato</td><td class="n"><b>${rate.numero_rate} rate</b></td></tr>` : ""}</table>
${rate?.rate?.length ? `<h2>Piano di pagamento in ${rate.numero_rate} rate</h2>
<table><thead><tr><th>Rata</th><th>Data</th><th class="n">Importo</th></tr></thead>
<tbody>${rate.rate.map(r => `<tr><td>${r.numero}/${rate.numero_rate}</td><td>${r.data ? formatDate(r.data) : "da concordare"}</td><td class="n">€ ${eur(r.importo)}</td></tr>`).join("")}</tbody>
<tfoot><tr><td colspan="2">Totale complessivo da pagare</td><td class="n">€ ${eur(rate.totale_complessivo ?? rate.netto_residuo ?? rate.totale_netto)}</td></tr></tfoot></table>
<div class="mini">Firma per accettazione del piano: dipendente ______________________ · titolare ______________________</div>` : ""}
<script>window.print()<\\/script></body></html>`);
    w.document.close();
  };

  const eliminaUltimoPeriodo = async (periodoId) => {
    if (!window.confirm("Eliminare l'ultimo periodo inserito?")) return;
    try {
      await axios.delete(`${API_TFR}/simulazione/${dipId}/periodi/${periodoId}`);
      await carica(dipId);
    } catch (e) { setErrore(e?.response?.data?.detail || "Errore nell'eliminazione"); }
  };

  const [modificaPeriodo, setModificaPeriodo] = useState(null);
  const [salvandoModifica, setSalvandoModifica] = useState(false);
  const apriModificaPeriodo = (p) => setModificaPeriodo({
    id: p.id, data_inizio: p.data_inizio, data_fine: p.data_fine || "",
    importo_settimanale: p.importo_settimanale, aperto: p.aperto,
  });
  const salvaModificaPeriodo = async () => {
    if (!modificaPeriodo.importo_settimanale) return;
    setSalvandoModifica(true); setErrore("");
    try {
      await axios.put(`${API_TFR}/simulazione/${dipId}/periodi/${modificaPeriodo.id}`, {
        importo_settimanale: Number(modificaPeriodo.importo_settimanale),
        data_inizio: modificaPeriodo.data_inizio || undefined,
        data_fine: modificaPeriodo.data_fine || undefined,
      });
      setModificaPeriodo(null);
      await carica(dipId);
    } catch (e) { setErrore(e?.response?.data?.detail || "Errore nel salvataggio della modifica"); }
    finally { setSalvandoModifica(false); }
  };

  // Ricalcola: rilegge i dati dal server e li ricalcola (il periodo in corso è sempre
  // live), senza mai cancellare nulla. Per correggere un valore sbagliato si usa la
  // matita (✎) su ogni riga, non un azzeramento.
  const ricalcolaSimulazione = async () => { await carica(dipId); };

  // Modifica diretta in tabella (importo settimanale): salva su Invio o
  // quando esci dalla cella, poi ricarica per ricalcolare tutto.
  const salvaCella = async (periodoId, campo, valore, valorePrecedente) => {
    const v = Number(valore);
    if (valore === "" || isNaN(v) || v === Number(valorePrecedente)) return;
    setErrore("");
    try {
      await axios.put(`${API_TFR}/simulazione/${dipId}/periodi/${periodoId}`, { [campo]: v });
      await carica(dipId);
    } catch (e) { setErrore(e?.response?.data?.detail || "Errore nel salvataggio"); }
  };
  const cellaInput = { border: "1px solid #c7cfc2", borderRadius: 6, padding: "3px 6px", fontSize: 13.5, width: 84, textAlign: "right", boxSizing: "border-box" };

  // Parametro di calcolo globale (divisore 12/13,5), modificabile qui.
  const [parametri, setParametri] = useState({ divisore: "12" });
  const [salvandoParametri, setSalvandoParametri] = useState(false);
  useEffect(() => {
    axios.get(`${API_TFR}/simulazione-parametri`)
      .then(r => setParametri({ divisore: String(r.data.divisore) }))
      .catch(() => {});
  }, []);
  const salvaParametri = async () => {
    setSalvandoParametri(true); setErrore("");
    try {
      await axios.put(`${API_TFR}/simulazione-parametri`, {
        divisore: Number(parametri.divisore),
      });
      await carica(dipId);
    } catch (e) { setErrore(e?.response?.data?.detail || "Errore nel salvataggio dei parametri"); }
    finally { setSalvandoParametri(false); }
  };

  const calcolaRate = async () => {
    try {
      const r = await axios.post(`${API_TFR}/simulazione/${dipId}/rate`, {
        numero_rate: Number(numeroRate),
        data_prima_rata: dataPrimaRata || undefined,
      });
      setRate(r.data);
    } catch (e) { setErrore(e?.response?.data?.detail || "Errore nel calcolo delle rate"); }
  };

  const inp = { border: "1px solid #c7cfc2", borderRadius: 8, padding: "7px 9px", fontSize: 14, width: "100%", boxSizing: "border-box" };

  return (
    <div className="dc-page">
      <div className="dc-page-header">
        <div>
          <h1>TFR</h1>
          <p>Situazione ufficiale e simulazione storica periodo per periodo</p>
        </div>
        <div className="dc-page-actions">
          <select className="dc-select" value={dipId} onChange={e => setDipId(e.target.value)}>
            {dipendenti.map(d => <option key={d.id} value={d.id}>{d.cognome ? `${d.cognome} ${d.nome || ""}`.trim() : d.nome}</option>)}
          </select>
        </div>
      </div>

      {errore && (
        <div className="dc-card" style={{ marginBottom: 16, borderLeft: "4px solid #d35f4e", color: "#d35f4e", fontWeight: 600 }}>⚠ {errore}</div>
      )}

      {loading ? <p className="dc-muted">Carico…</p> : (
        <>
          {situazione && (
            <div className="dc-card" style={{ marginBottom: 16 }}>
              <h3 style={{ marginTop: 0 }}>Situazione ufficiale (calcolo automatico dai cedolini)</h3>
              <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                <div><div className="dc-muted" style={{ fontSize: 12.5 }}>TFR accantonato</div><div style={{ fontWeight: 700, fontSize: 20 }}>€ {eur(situazione.tfr_accantonato)}</div></div>
                <div><div className="dc-muted" style={{ fontSize: 12.5 }}>Già liquidato</div><div style={{ fontWeight: 700, fontSize: 20 }}>€ {eur(situazione.totale_liquidato)}</div></div>
                <div><div className="dc-muted" style={{ fontSize: 12.5 }}>Disponibile</div><div style={{ fontWeight: 700, fontSize: 20, color: "#3d8168" }}>€ {eur(situazione.tfr_disponibile)}</div></div>
              </div>
            </div>
          )}

          <div className="dc-card" style={{ marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>⚙️ Parametri di calcolo</h3>
            <p className="dc-muted" style={{ fontSize: 13, marginTop: -6 }}>
              Valgono per tutti i dipendenti e ricalcolano subito tutto lo storico. Divisore 12: 11.440 ÷ 12 =
              953,33 · divisore 13,5: 11.440 ÷ 13,5 = 847,41.
            </p>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
              <div>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>Divisore</label>
                <select className="dc-select" value={parametri.divisore}
                  onChange={e => setParametri(pr => ({ ...pr, divisore: e.target.value }))}>
                  <option value="12">12 (mensilità)</option>
                  <option value="13.5">13,5 (art. 2120 c.c.)</option>
                </select>
              </div>
              <button className="dc-btn dc-btn-primary" disabled={salvandoParametri} onClick={salvaParametri}>
                {salvandoParametri ? "Salvo…" : "Salva e ricalcola"}
              </button>
            </div>
          </div>

          <div className="dc-card" style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
              <h3 style={{ marginTop: 0, marginBottom: 0 }}>Simulazione storica TFR</h3>
              <button className="dc-btn" onClick={stampaReport} disabled={!sim?.periodi?.length}
                title="Apre il report completo (periodi, liquidazione, acconti, netto residuo) pronto da stampare o salvare in PDF">
                🖨 Stampa report
              </button>
            </div>
            <p className="dc-muted" style={{ fontSize: 13, marginTop: -6 }}>
              Formula: importo settimanale × settimane = retribuzione utile → ÷ divisore = quota lorda = netto
              (nessuna trattenuta: l'accantonamento non è tassato anno per anno). L'ultimo periodo è sempre
              "in corso" e matura fino ad oggi da solo. Non modifica il TFR ufficiale qui sopra.
            </p>

            {sim?.paga_attuale != null && (
              <div style={{ background: "#eef1ea", border: "1px solid #d7e0d3", borderRadius: 10, padding: "10px 14px", marginBottom: 14, display: "flex", gap: 20, alignItems: "center", flexWrap: "wrap" }}>
                <div><span className="dc-muted" style={{ fontSize: 12.5 }}>Paga attuale (in corso)</span><br /><b style={{ fontSize: 16 }}>€ {eur(sim.paga_attuale)}/settimana</b></div>
                <div><span className="dc-muted" style={{ fontSize: 12.5 }}>Dal</span><br /><b>{formatDate(sim.paga_attuale_dal)}</b></div>
              </div>
            )}

            {sim?.periodi?.length > 0 && (
              <div style={{ overflowX: "auto", marginBottom: 14 }}>
                <table className="dc-table" style={{ minWidth: 860, whiteSpace: "nowrap" }}>
                  <thead>
                    <tr>
                      <th>Dal</th><th>Al</th>
                      <th style={{ textAlign: "right" }}>€/sett.</th>
                      <th style={{ textAlign: "right" }}>Settimane</th>
                      <th style={{ textAlign: "right" }}>Mensile €</th>
                      <th style={{ textAlign: "right" }}>Retrib. utile €</th>
                      <th style={{ textAlign: "right" }}>Lordo €</th>
                      <th style={{ textAlign: "right" }}>Netto €</th><th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {sim.periodi.map((p, i) => (
                      <tr key={p.id}>
                        <td>{formatDate(p.data_inizio)}</td>
                        <td>{p.aperto ? <span style={{ color: "#3d8168", fontWeight: 700 }}>in corso</span> : formatDate(p.data_fine)}</td>
                        <td style={{ textAlign: "right" }}>
                          <input type="number" step="0.01" style={cellaInput} key={`s-${p.id}-${p.importo_settimanale}`}
                            defaultValue={p.importo_settimanale}
                            title="Modifica e premi Invio (o esci dalla casella) per salvare"
                            onBlur={e => salvaCella(p.id, "importo_settimanale", e.target.value, p.importo_settimanale)}
                            onKeyDown={e => e.key === "Enter" && e.target.blur()} />
                        </td>
                        <td style={{ textAlign: "right" }}>{p.settimane}</td>
                        <td style={{ textAlign: "right" }}>{eur(p.mensile)}</td>
                        <td style={{ textAlign: "right" }}>{eur(p.retribuzione_utile)}</td>
                        <td style={{ textAlign: "right" }}>{eur(p.lordo)}</td>
                        <td style={{ textAlign: "right", fontWeight: 700 }}>{eur(p.netto)}</td>
                        <td style={{ display: "flex", gap: 4 }}>
                          <button className="dc-btn" style={{ padding: "2px 8px", fontSize: 12 }} onClick={() => apriModificaPeriodo(p)} title="Correggi le date" aria-label="Correggi le date del periodo">✎</button>
                          {i === sim.periodi.length - 1 && (
                            <button className="dc-btn" style={{ padding: "2px 8px", fontSize: 12 }} onClick={() => eliminaUltimoPeriodo(p.id)} aria-label="Elimina l'ultimo periodo">✕</button>
                          )}
                        </td>
                      </tr>
                    ))}
                    <tr style={{ fontWeight: 700, borderTop: "2px solid #e6e0d4" }}>
                      <td colSpan={6}>Totale (incluso il periodo in corso, ad oggi)</td>
                      <td style={{ textAlign: "right" }}>{eur(sim.totale_lordo)}</td>
                      <td style={{ textAlign: "right" }}>{eur(sim.totale_netto)}</td>
                      <td></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}

            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
              <div>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>
                  {sim?.paga_attuale != null ? "Nuova paga da" : "Dal"}
                </label>
                <MiniCalendario value={formPeriodo.data_inizio} onChange={v => setFormPeriodo(f => ({ ...f, data_inizio: v }))} />
              </div>
              <div>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>€ a settimana</label>
                <input type="number" step="0.01" style={{ ...inp, width: 120 }} value={formPeriodo.importo_settimanale}
                  onChange={e => setFormPeriodo(f => ({ ...f, importo_settimanale: e.target.value }))} />
              </div>
              {comeChiuso && (
                <div>
                  <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>Al (periodo storico chiuso)</label>
                  <MiniCalendario value={formPeriodo.data_fine} onChange={v => setFormPeriodo(f => ({ ...f, data_fine: v }))} />
                </div>
              )}
              <button className="dc-btn dc-btn-primary" disabled={salvandoPeriodo} onClick={aggiungiPeriodo}>
                {salvandoPeriodo ? "Salvo…" : sim?.paga_attuale != null ? "📈 Registra aumento" : "+ Inserisci paga iniziale"}
              </button>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5 }}>
                <input type="checkbox" checked={comeChiuso} onChange={e => setComeChiuso(e.target.checked)} />
                Periodo storico già chiuso (ha una data di fine)
              </label>
              {sim?.periodi?.length > 0 && (
                <button className="dc-btn" onClick={ricalcolaSimulazione} style={{ marginLeft: "auto" }}>🔄 Ricalcola</button>
              )}
            </div>
          </div>

          {liquidazione && (
            <div className="dc-card" style={{ marginBottom: 16 }}>
              <h3 style={{ marginTop: 0 }}>
                Liquidazione finale{liquidazione.cessato ? " — rapporto cessato" : " (simulata ad oggi)"}
              </h3>
              <p className="dc-muted" style={{ fontSize: 13, marginTop: -6 }}>
                {liquidazione.cessato
                  ? `Calcolata fino alla data di cessazione (${formatDate(liquidazione.data_cessazione)}): il rapporto non matura più nulla dopo.`
                  : `Il dipendente è ancora in forza: questa è una simulazione "se finisse oggi" (${formatDate(liquidazione.calcolato_fino_a)}).`}
                {" "}Tredicesima e quattordicesima = importo settimanale × settimane del ciclo ÷ 12
                (una mensilità piena per un ciclo intero).
              </p>
              <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                <div>
                  <div className="dc-muted" style={{ fontSize: 12.5 }}>
                    Tredicesima maturata (rateo){liquidazione.tredicesima.manuale && <> · <b>manuale</b> <button className="dc-btn" style={{ padding: "0 6px", fontSize: 11 }} title="Torna al calcolo automatico" onClick={() => salvaOverride("tredicesima", null)}>↺ auto</button></>}
                  </div>
                  <div style={{ fontWeight: 700, fontSize: 18, display: "flex", alignItems: "center", gap: 4 }}>
                    € <input key={`t13-${liquidazione.tredicesima.netto}`} type="text" inputMode="decimal"
                      defaultValue={liquidazione.tredicesima.netto}
                      style={{ width: 100, fontWeight: 700, fontSize: 17, border: "1px solid #e6e0d4", borderRadius: 8, padding: "3px 6px" }}
                      onBlur={e => { const v = Number(String(e.target.value).replace(",", ".")); if (!isNaN(v) && v !== liquidazione.tredicesima.netto) salvaOverride("tredicesima", v); }}
                      onKeyDown={e => { if (e.key === "Enter") e.target.blur(); }} />
                  </div>
                  <div className="dc-muted" style={{ fontSize: 11.5 }}>{formatDate(liquidazione.tredicesima.dal)} → {formatDate(liquidazione.tredicesima.al)}</div>
                </div>
                <div>
                  <div className="dc-muted" style={{ fontSize: 12.5 }}>
                    Quattordicesima maturata (totale){liquidazione.quattordicesima.manuale && <> · <b>manuale</b> <button className="dc-btn" style={{ padding: "0 6px", fontSize: 11 }} title="Torna al calcolo automatico" onClick={() => salvaOverride("quattordicesima", null)}>↺ auto</button></>}
                  </div>
                  <div style={{ fontWeight: 700, fontSize: 18, display: "flex", alignItems: "center", gap: 4 }}>
                    € <input key={`t14-${liquidazione.quattordicesima.netto}`} type="text" inputMode="decimal"
                      defaultValue={liquidazione.quattordicesima.netto}
                      style={{ width: 100, fontWeight: 700, fontSize: 17, border: "1px solid #e6e0d4", borderRadius: 8, padding: "3px 6px" }}
                      onBlur={e => { const v = Number(String(e.target.value).replace(",", ".")); if (!isNaN(v) && v !== liquidazione.quattordicesima.netto) salvaOverride("quattordicesima", v); }}
                      onKeyDown={e => { if (e.key === "Enter") e.target.blur(); }} />
                  </div>
                  <div className="dc-muted" style={{ fontSize: 11.5 }}>{formatDate(liquidazione.quattordicesima.dal)} → {formatDate(liquidazione.quattordicesima.al)}</div>
                </div>
                <div>
                  <div className="dc-muted" style={{ fontSize: 12.5 }}>
                    Ferie residue (giorni){liquidazione.ferie?.manuale && <> · <b>manuale</b> <button className="dc-btn" style={{ padding: "0 6px", fontSize: 11 }} title="Torna al residuo tracciato dall'app" onClick={() => salvaOverride("ferie_giorni", null)}>↺ auto</button></>}
                  </div>
                  <div style={{ fontWeight: 700, fontSize: 18, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                    <input key={`fg-${liquidazione.ferie?.giorni_residui ?? ""}`} type="text" inputMode="decimal"
                      defaultValue={liquidazione.ferie?.giorni_residui ?? ""}
                      placeholder="gg"
                      style={{ width: 64, fontWeight: 700, fontSize: 17, border: "1px solid #e6e0d4", borderRadius: 8, padding: "3px 6px" }}
                      onBlur={e => { const v = Number(String(e.target.value).replace(",", ".")); if (e.target.value !== "" && !isNaN(v) && v !== liquidazione.ferie?.giorni_residui) salvaOverride("ferie_giorni", v); }}
                      onKeyDown={e => { if (e.key === "Enter") e.target.blur(); }} />
                    gg{liquidazione.ferie && <> — € {eur(liquidazione.ferie.controvalore)}</>}
                  </div>
                  {liquidazione.ferie && <div className="dc-muted" style={{ fontSize: 11.5 }}>€ {eur(liquidazione.ferie.paga_giornaliera)}/giorno · {liquidazione.ferie.fonte}</div>}
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6 }}>
                    <span className="dc-muted" style={{ fontSize: 12 }}>Scala</span>
                    <input type="text" inputMode="decimal" value={scalaGiorni} onChange={e => setScalaGiorni(e.target.value)}
                      placeholder="es. 26" style={{ width: 56, border: "1px solid #e6e0d4", borderRadius: 8, padding: "3px 6px", fontSize: 13 }} />
                    <span className="dc-muted" style={{ fontSize: 12 }}>gg</span>
                    <button className="dc-btn" style={{ padding: "3px 10px", fontSize: 12 }}
                      disabled={!scalaGiorni || !liquidazione.ferie}
                      title="Sottrae i giorni indicati dal residuo e salva la differenza"
                      onClick={() => {
                        const sc = Number(String(scalaGiorni).replace(",", "."));
                        const cur = liquidazione.ferie?.giorni_residui || 0;
                        if (isNaN(sc) || !sc) return;
                        const diff = Math.round((cur - sc) * 100) / 100;
                        if (diff < 0 && !window.confirm(`Il residuo diventerebbe negativo (${cur} − ${sc} = ${diff}). Salvo lo stesso?`)) return;
                        salvaOverride("ferie_giorni", diff);
                        toast(`Ferie: ${cur} − ${sc} = ${diff} gg`, "ok");
                        setScalaGiorni("");
                      }}>− Scala e salva differenza</button>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="dc-card" style={{ marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>Acconti sul TFR (anticipi già dati)</h3>
            <p className="dc-muted" style={{ fontSize: 13, marginTop: -6 }}>
              Gli acconti si scalano dal totale netto della simulazione. Stesso registro degli
              acconti dell'app (niente doppioni): compaiono anche in Cedolini &amp; Bonifici.
            </p>
            {(acconti?.acconti?.tfr || []).length > 0 && (
              <table className="dc-table" style={{ marginBottom: 10 }}>
                <thead><tr><th>Data</th><th style={{ textAlign: "right" }}>Importo</th><th>Note</th><th></th></tr></thead>
                <tbody>
                  {(acconti.acconti.tfr).map(a => (
                    <tr key={a.id}>
                      <td>{formatDate(a.data)}</td>
                      <td style={{ textAlign: "right" }}>€ {eur(a.importo)}</td>
                      <td className="dc-muted">{a.note || ""}{a.stato === "annullato" ? " · annullato" : ""}</td>
                      <td style={{ textAlign: "right" }}>
                        <button className="dc-btn" style={{ padding: "2px 8px", fontSize: 12 }} title="Elimina acconto" onClick={() => eliminaAcconto(a.id)}>✕</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
              <div>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>Data</label>
                <MiniCalendario value={formAcconto.data} onChange={v => setFormAcconto(f => ({ ...f, data: v }))} />
              </div>
              <div>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>Importo €</label>
                <input type="text" inputMode="decimal" value={formAcconto.importo} onChange={e => setFormAcconto(f => ({ ...f, importo: e.target.value }))}
                  placeholder="es. 500" style={{ width: 110, border: "1px solid #e6e0d4", borderRadius: 8, padding: "8px 10px" }} />
              </div>
              <div style={{ flex: 1, minWidth: 160 }}>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>Nota (facoltativa)</label>
                <input type="text" value={formAcconto.note} onChange={e => setFormAcconto(f => ({ ...f, note: e.target.value }))}
                  placeholder="es. anticipo richiesto a voce" style={{ width: "100%", border: "1px solid #e6e0d4", borderRadius: 8, padding: "8px 10px" }} />
              </div>
              <button className="dc-btn-primary" disabled={!formAcconto.importo} onClick={registraAcconto}>+ Registra acconto</button>
            </div>
            <div style={{ marginTop: 12, background: "#eef1ea", border: "1px solid #d7e0d3", borderRadius: 10, padding: "10px 14px", display: "flex", gap: 24, flexWrap: "wrap", fontSize: 14 }}>
              <span>TFR netto simulato: <b>€ {eur(sim?.totale_netto || 0)}</b></span>
              <span>− Acconti erogati: <b>€ {eur(acconti?.tfr_acconti || 0)}</b></span>
              <span>= <b style={{ fontSize: 16 }}>Netto residuo € {eur((sim?.totale_netto || 0) - (acconti?.tfr_acconti || 0))}</b></span>
            </div>
          </div>

          {liquidazione && (() => {
            const tfrResiduo = (sim?.totale_netto || 0) - (acconti?.tfr_acconti || 0);
            const t13 = liquidazione.tredicesima?.netto || 0;
            const t14 = liquidazione.quattordicesima?.netto || 0;
            const fer = liquidazione.ferie?.controvalore || 0;
            const totale = Math.round((tfrResiduo + t13 + t14 + fer) * 100) / 100;
            const riga = { display: "flex", justifyContent: "space-between", padding: "6px 4px", borderBottom: "1px solid #f0ece1", fontSize: 14 };
            return (
              <div className="dc-card" style={{ marginBottom: 16, border: "2px solid #5b7a6b" }}>
                <h3 style={{ marginTop: 0 }}>💰 Totale complessivo da liquidare</h3>
                <p className="dc-muted" style={{ fontSize: 13, marginTop: -6 }}>
                  TFR residuo (dopo gli acconti) più tredicesima, quattordicesima e ferie della
                  liquidazione qui sopra. Le ferie negative si sottraggono.
                </p>
                <div style={{ maxWidth: 460 }}>
                  <div style={riga}><span>TFR lordo maturato (dalla tabella)</span><b>€ {eur(sim?.totale_lordo || 0)}</b></div>
                  <div style={riga}><span>= TFR netto</span><b>€ {eur(sim?.totale_netto || 0)}</b></div>
                  <div style={riga}><span>− Acconti già erogati</span><b>€ {eur(acconti?.tfr_acconti || 0)}</b></div>
                  <div style={riga}><span>= TFR netto residuo</span><b>€ {eur(tfrResiduo)}</b></div>
                  <div style={riga}><span>+ Tredicesima maturata{liquidazione.tredicesima?.manuale ? " (manuale)" : ""}</span><b>€ {eur(t13)}</b></div>
                  <div style={riga}><span>+ Quattordicesima maturata{liquidazione.quattordicesima?.manuale ? " (manuale)" : ""}</span><b>€ {eur(t14)}</b></div>
                  <div style={riga}><span>{fer < 0 ? "−" : "+"} Ferie ({liquidazione.ferie ? `${liquidazione.ferie.giorni_residui} gg` : "—"}{liquidazione.ferie?.manuale ? ", manuale" : ""})</span><b style={fer < 0 ? { color: "#b3261e" } : {}}>€ {eur(Math.abs(fer))}</b></div>
                  <div style={{ ...riga, borderBottom: "none", background: "#eef1ea", borderRadius: 10, padding: "10px 12px", marginTop: 6, fontSize: 16 }}>
                    <span><b>TOTALE COMPLESSIVO</b></span><b>€ {eur(totale)}</b>
                  </div>
                </div>
              </div>
            );
          })()}

          {sim?.periodi?.length > 0 && (
            <div className="dc-card">
              <h3 style={{ marginTop: 0 }}>Dividi il totale complessivo in rate</h3>
              <p className="dc-muted" style={{ fontSize: 13, marginTop: -6 }}>
                Le rate si calcolano sul <b>totale complessivo da liquidare</b> (TFR residuo dopo gli
                acconti + tredicesima + quattordicesima ± ferie), lo stesso della card qui sopra.
              </p>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
                <div>
                  <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>Numero rate</label>
                  <input type="number" min={1} style={{ ...inp, width: 100 }} value={numeroRate} onChange={e => setNumeroRate(e.target.value)} />
                </div>
                <div>
                  <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>Data 1ª rata (opzionale)</label>
                  <input type="date" style={inp} value={dataPrimaRata} onChange={e => setDataPrimaRata(e.target.value)} />
                </div>
                <button className="dc-btn dc-btn-primary" onClick={calcolaRate}>Calcola rate</button>
              </div>
              {rate && (
                <div style={{ overflowX: "auto", marginTop: 14 }}>
                  <table className="dc-table" style={{ minWidth: 320 }}>
                    <thead><tr><th>Rata</th>{rate.rate[0]?.data && <th>Data</th>}<th style={{ textAlign: "right" }}>Importo €</th></tr></thead>
                    <tbody>
                      {rate.rate.map(r => (
                        <tr key={r.numero}>
                          <td>{r.numero}/{rate.numero_rate}</td>
                          {r.data && <td>{formatDate(r.data)}</td>}
                          <td style={{ textAlign: "right" }}>{eur(r.importo)}</td>
                        </tr>
                      ))}
                      <tr style={{ fontWeight: 700, borderTop: "2px solid #e6e0d4" }}>
                        <td colSpan={rate.rate[0]?.data ? 2 : 1}>Totale complessivo da pagare</td>
                        <td style={{ textAlign: "right" }}>{eur(rate.totale_complessivo ?? rate.netto_residuo ?? rate.totale_netto)}</td>
                      </tr>
                      {rate.totale_complessivo !== undefined && (
                        <tr className="dc-muted" style={{ fontSize: 12.5 }}>
                          <td colSpan={rate.rate[0]?.data ? 2 : 1}>
                            TFR residuo € {eur(rate.netto_residuo)} + 13ª € {eur(rate.tredicesima || 0)} + 14ª € {eur(rate.quattordicesima || 0)}
                            {rate.ferie < 0 ? ` − ferie € ${eur(Math.abs(rate.ferie))}` : ` + ferie € ${eur(rate.ferie || 0)}`}
                          </td>
                          <td></td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          <div className="dc-card" style={{ marginTop: 16 }}>
            <h3 style={{ marginTop: 0 }}>Calcolo netto da lordo (IRPEF 2026)</h3>
            <p className="dc-muted" style={{ fontSize: 13, marginTop: -6 }}>
              Strumento separato dal simulatore: da un importo settimanale LORDO calcola il mensile lordo
              (settimane × importo ÷ mesi), toglie INPS 9,19% e IRPEF a scaglioni 2026 (con detrazione lavoro
              dipendente) e restituisce il netto da ricevere. Non include addizionali regionali/comunali né bonus.
            </p>
            <details style={{ marginBottom: 12 }}>
              <summary style={{ cursor: "pointer", fontWeight: 700, fontSize: 14 }}>
                📊 Tabelle CCNL Turismo — Pubblici Esercizi (minimi dal 1/6/2026)
              </summary>
              <p className="dc-muted" style={{ fontSize: 12.5, margin: "8px 0" }}>
                Minimi tabellari del CCNL Pubblici Esercizi, Ristorazione e Turismo (Confcommercio-FIPE,
                rinnovo 5/6/2024 — terza tranche dal 1° giugno 2026; fonte: Confcommercio Milano).
                "Usa" compila il lordo settimanale (mensile × 12 ÷ 52) nel calcolo qui sotto.
                Da ricontrollare a ogni rinnovo contrattuale.
              </p>
              <div className="dc-scroll-x">
                <table className="dc-table" style={{ fontSize: 13 }}>
                  <thead><tr><th>Livello</th><th>Mansioni tipiche</th><th style={{ textAlign: "right" }}>Paga base €</th><th style={{ textAlign: "right" }}>Contingenza €</th><th style={{ textAlign: "right" }}>Totale mensile €</th><th style={{ textAlign: "right" }}>≈ €/settimana</th><th></th></tr></thead>
                  <tbody>
                    {CCNL_LIVELLI_2026.map(([liv, base, cont, tot, mansioni]) => {
                      const sett = Math.round((tot * 12 / 52) * 100) / 100;
                      return (
                        <tr key={liv} style={nlLivello === liv ? { background: "#eef1ea" } : undefined}>
                          <td style={{ fontWeight: 700 }}>{liv}</td>
                          <td className="dc-muted" style={{ fontSize: 12 }}>{mansioni}</td>
                          <td style={{ textAlign: "right" }}>{eur(base)}</td>
                          <td style={{ textAlign: "right" }}>{eur(cont)}</td>
                          <td style={{ textAlign: "right", fontWeight: 700 }}>{eur(tot)}</td>
                          <td style={{ textAlign: "right" }}>{eur(sett)}</td>
                          <td style={{ textAlign: "right" }}>
                            <button className="dc-btn" style={{ padding: "3px 10px", fontSize: 12 }}
                              title={`Calcola tutto con la tariffa del livello ${liv}`}
                              onClick={() => usaLivelloCcnl(liv)}>
                              Usa
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </details>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
              <div>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>Tariffa CCNL (livello)</label>
                <select style={{ ...inp, width: 220 }} value={nlLivello} onChange={e => usaLivelloCcnl(e.target.value)}>
                  <option value="">— scegli e calcolo tutto io —</option>
                  {CCNL_LIVELLI_2026.map(([liv, , , tot, mansioni]) => (
                    <option key={liv} value={liv}>{liv} — € {eur(tot)}/mese ({mansioni})</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>€/settimana (lordo)</label>
                <input type="number" step="0.01" style={{ ...inp, width: 130 }} value={nlForm.importo}
                  onChange={e => { setNlForm(f => ({ ...f, importo: e.target.value })); setNlLivello(""); }} />
              </div>
              <div>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }} title="Si somma al minimo tabellare e paga INPS e IRPEF come il resto della retribuzione">Superminimo €/mese</label>
                <input type="number" step="0.01" placeholder="0" style={{ ...inp, width: 130 }} value={nlForm.superminimo}
                  onChange={e => setNlForm(f => ({ ...f, superminimo: e.target.value }))}
                  onBlur={() => { if (nlForm.importo) calcolaNetto(); }} />
              </div>
              <div>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>Settimane lavorate</label>
                <input type="number" step="0.01" style={{ ...inp, width: 120 }} value={nlForm.settimane}
                  onChange={e => setNlForm(f => ({ ...f, settimane: e.target.value }))} />
              </div>
              <div>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>Mesi lavorati</label>
                <input type="number" step="0.01" style={{ ...inp, width: 110 }} value={nlForm.mesi}
                  onChange={e => setNlForm(f => ({ ...f, mesi: e.target.value }))} />
              </div>
              <button className="dc-btn dc-btn-primary" onClick={() => calcolaNetto()}>Calcola netto</button>
            </div>
            {nlEsito && !nlEsito.errore && (
              <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginTop: 14 }}>
                {nlEsito.superminimo_mese > 0 && (
                  <div style={{ flexBasis: "100%", fontSize: 12.5 }} className="dc-muted">
                    Calcolato su lordo settimanale totale € {eur(nlEsito.lordo_settimanale_totale)} = tabellare + superminimo
                    € {eur(nlEsito.superminimo_mese)}/mese (il superminimo paga INPS e IRPEF come il resto).
                  </div>
                )}
                <div><div className="dc-muted" style={{ fontSize: 12.5 }}>Lordo mensile medio</div><div style={{ fontWeight: 700, fontSize: 17 }}>€ {eur(nlEsito.lordo_mensile_medio)}</div></div>
                <div><div className="dc-muted" style={{ fontSize: 12.5 }}>INPS (anno)</div><div style={{ fontWeight: 700, fontSize: 17 }}>€ {eur(nlEsito.contributi_inps)}</div></div>
                <div><div className="dc-muted" style={{ fontSize: 12.5 }}>IRPEF netta (anno)</div><div style={{ fontWeight: 700, fontSize: 17 }}>€ {eur(nlEsito.irpef_netta)}</div></div>
                <div><div className="dc-muted" style={{ fontSize: 12.5 }}>Aliquota media</div><div style={{ fontWeight: 700, fontSize: 17 }}>{nlEsito.aliquota_media_effettiva}%</div></div>
                <div><div className="dc-muted" style={{ fontSize: 12.5 }}>Netto mensile da ricevere</div><div style={{ fontWeight: 700, fontSize: 20, color: "#3d8168" }}>€ {eur(nlEsito.netto_mensile)}</div></div>
                <div><div className="dc-muted" style={{ fontSize: 12.5 }}>Netto del periodo</div><div style={{ fontWeight: 700, fontSize: 17 }}>€ {eur(nlEsito.netto_periodo)}</div></div>
              </div>
            )}
            {nlEsito?.errore && <div style={{ color: "#d35f4e", fontWeight: 600, marginTop: 10 }}>⚠ {nlEsito.errore}</div>}
          </div>

          <div className="dc-card" style={{ marginTop: 16 }}>
            <h3 style={{ marginTop: 0 }}>Calcolo lordo da netto (inverso)</h3>
            <p className="dc-muted" style={{ fontSize: 13, marginTop: -6 }}>
              Scrivi il NETTO mensile che vuoi dare al dipendente e calcolo io tutto il resto:
              lordo settimanale e mensile, INPS 9,19%, IRPEF 2026 e costo del periodo.
              Stesse regole del calcolo qui sopra (niente addizionali né bonus).
            </p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
              <div>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>Netto €/mese desiderato</label>
                <input type="number" step="0.01" style={{ ...inp, width: 150 }} value={lnForm.netto}
                  onChange={e => setLnForm(f => ({ ...f, netto: e.target.value }))}
                  onKeyDown={e => { if (e.key === "Enter") calcolaLordo(); }} />
              </div>
              <div>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>Settimane lavorate</label>
                <input type="number" step="0.01" style={{ ...inp, width: 120 }} value={lnForm.settimane}
                  onChange={e => setLnForm(f => ({ ...f, settimane: e.target.value }))} />
              </div>
              <div>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>Mesi lavorati</label>
                <input type="number" step="0.01" style={{ ...inp, width: 110 }} value={lnForm.mesi}
                  onChange={e => setLnForm(f => ({ ...f, mesi: e.target.value }))} />
              </div>
              <button className="dc-btn dc-btn-primary" onClick={calcolaLordo}>Calcola lordo</button>
            </div>
            {lnEsito && !lnEsito.errore && (
              <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginTop: 14 }}>
                <div><div className="dc-muted" style={{ fontSize: 12.5 }}>Lordo €/settimana</div><div style={{ fontWeight: 700, fontSize: 20, color: "#3f5a4e" }}>€ {eur(lnEsito.importo_settimanale_lordo)}</div></div>
                <div><div className="dc-muted" style={{ fontSize: 12.5 }}>Lordo mensile medio</div><div style={{ fontWeight: 700, fontSize: 17 }}>€ {eur(lnEsito.lordo_mensile_medio)}</div></div>
                <div><div className="dc-muted" style={{ fontSize: 12.5 }}>INPS (anno)</div><div style={{ fontWeight: 700, fontSize: 17 }}>€ {eur(lnEsito.contributi_inps)}</div></div>
                <div><div className="dc-muted" style={{ fontSize: 12.5 }}>IRPEF netta (anno)</div><div style={{ fontWeight: 700, fontSize: 17 }}>€ {eur(lnEsito.irpef_netta)}</div></div>
                <div><div className="dc-muted" style={{ fontSize: 12.5 }}>Aliquota media</div><div style={{ fontWeight: 700, fontSize: 17 }}>{lnEsito.aliquota_media_effettiva}%</div></div>
                <div><div className="dc-muted" style={{ fontSize: 12.5 }}>Netto mensile verificato</div><div style={{ fontWeight: 700, fontSize: 17, color: "#3d8168" }}>€ {eur(lnEsito.netto_mensile)}</div></div>
                <div><div className="dc-muted" style={{ fontSize: 12.5 }}>Lordo del periodo</div><div style={{ fontWeight: 700, fontSize: 17 }}>€ {eur(lnEsito.lordo_periodo)}</div></div>
                {(() => {
                  const vicino = [...CCNL_LIVELLI_2026].map(([liv, , , tot]) => ({ liv, tot, diff: Math.abs(tot - lnEsito.lordo_mensile_medio) }))
                    .sort((a, b) => a.diff - b.diff)[0];
                  return vicino ? (
                    <div style={{ flexBasis: "100%" }} className="dc-muted">
                      Livello CCNL più vicino per lordo mensile: <b>{vicino.liv}</b> (minimo € {eur(vicino.tot)}/mese
                      {lnEsito.lordo_mensile_medio > vicino.tot ? `, differenza € ${eur(lnEsito.lordo_mensile_medio - vicino.tot)} da coprire come superminimo` : ""}).
                    </div>
                  ) : null;
                })()}
              </div>
            )}
            {lnEsito?.errore && <div style={{ color: "#d35f4e", fontWeight: 600, marginTop: 10 }}>⚠ {lnEsito.errore}</div>}
          </div>
        </>
      )}

      {modificaPeriodo && (
        <Modal title="Correggi periodo" onClose={() => setModificaPeriodo(null)} maxWidth={420}>
          <div className="dc-modal-body">
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>Dal</label>
                <MiniCalendario value={modificaPeriodo.data_inizio} onChange={v => setModificaPeriodo(m => ({ ...m, data_inizio: v }))} />
              </div>
              <div>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>
                  Al{modificaPeriodo.aperto ? " (vuoto = resta in corso; scegli una data per chiuderlo)" : ""}
                </label>
                <MiniCalendario value={modificaPeriodo.data_fine} onChange={v => setModificaPeriodo(m => ({ ...m, data_fine: v }))} />
              </div>
              <div>
                <label className="dc-muted" style={{ fontSize: 12, display: "block" }}>€ a settimana</label>
                <input type="number" step="0.01" style={inp} value={modificaPeriodo.importo_settimanale}
                  onChange={e => setModificaPeriodo(m => ({ ...m, importo_settimanale: e.target.value }))} />
              </div>
              <button className="dc-btn dc-btn-primary" disabled={salvandoModifica} onClick={salvaModificaPeriodo}>
                {salvandoModifica ? "Salvo…" : "Salva correzione"}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

// Bonifici bancari "BENEFICIARI DIVERSI": la banca li emette come un unico
// addebito cumulativo su piu' persone, senza nominarne nessuna nel PDF —
// nessun algoritmo puo' indovinare a chi vanno. Qui si guarda il documento
// (importo, data, causale) e si assegna a mano dipendente + mese.
function BonificiDaAssociarePage({ dipendenti }) {
  const mesi = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno","Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"];
  const [righe, setRighe] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scelte, setScelte] = useState({});   // id -> { dipendente_id, mese, anno }
  const [busy, setBusy] = useState(null);

  const eur = (n) => (Number(n) || 0).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const dipOrdinati = [...(dipendenti || [])].sort((a, b) => (a.nome_completo || "").localeCompare(b.nome_completo || ""));

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/bonifici-da-associare`);
      setRighe(r.data || []);
      // precompila mese/anno col mese del pagamento stesso: e' la scelta di
      // default, l'utente puo' cambiarla prima di confermare
      const iniziale = {};
      for (const b of (r.data || [])) {
        const [a, m] = (b.data || "").split("-");
        iniziale[b.id] = { dipendente_id: "", anno: a ? Number(a) : new Date().getFullYear(),
                           mese: m ? Number(m) : new Date().getMonth() + 1 };
      }
      setScelte(iniziale);
    } catch (e) { console.error(e); setRighe([]); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const setScelta = (id, campo, valore) =>
    setScelte(s => ({ ...s, [id]: { ...s[id], [campo]: valore } }));

  const associa = async (id) => {
    const sc = scelte[id];
    if (!sc?.dipendente_id) { toast("Scegli prima il dipendente", "err"); return; }
    setBusy(id);
    try {
      await axios.post(`${API}/bonifici-da-associare/${id}/associa`, {
        dipendente_id: sc.dipendente_id, mese: sc.mese, anno: sc.anno,
      });
      toast("Associato: salvato nella scheda del dipendente con il PDF allegato");
      setRighe(r => r.filter(x => x.id !== id));
    } catch (e) { console.error(e); toast(e?.response?.data?.detail || "Errore nell'associazione", "err"); }
    finally { setBusy(null); }
  };

  const ignora = async (id) => {
    if (!window.confirm("Non e' un pagamento a un dipendente? Esce dalla coda senza creare nulla.")) return;
    setBusy(id);
    try {
      await axios.post(`${API}/bonifici-da-associare/${id}/ignora`);
      setRighe(r => r.filter(x => x.id !== id));
    } catch (e) { console.error(e); toast("Errore", "err"); }
    finally { setBusy(null); }
  };

  return (
    <div className="dc-page">
      <div className="dc-page-header">
        <div>
          <h1>Bonifici da associare</h1>
          <p>{righe.length} bonifici cumulativi ("beneficiari diversi") in attesa di essere assegnati a un dipendente. L'import dalla cartella Drive si fa da "Cedolini &amp; Bonifici" — arrivano qui solo quelli che non si possono assegnare da soli.</p>
        </div>
      </div>

      <div className="dc-card" style={{ marginBottom: 12, padding: 12, fontSize: 13, color: "#6b7669" }}>
        Questi bonifici la banca li emette come un unico addebito su piu' persone insieme:
        il PDF non nomina nessuno, quindi non si possono assegnare da soli. Guarda importo e data
        (apri il PDF se serve), scegli il dipendente e il mese di competenza, poi conferma:
        il bonifico entra nella scheda del dipendente con il documento allegato, come tutti gli altri.
      </div>

      {loading ? <div className="dc-card" style={{ padding: 20 }}>Carico…</div> :
       righe.length === 0 ? <div className="dc-card" style={{ padding: 20 }}>Nessun bonifico in attesa.</div> :
      <div className="dc-card" style={{ padding: 0 }}>
        <table className="dc-table">
          <thead>
            <tr>
              <th>Data</th><th>Importo</th><th>Causale</th><th>PDF</th>
              <th>Dipendente</th><th>Periodo</th><th></th>
            </tr>
          </thead>
          <tbody>
            {righe.map(b => {
              const sc = scelte[b.id] || {};
              return (
                <tr key={b.id}>
                  <td>{b.data ? b.data.split("-").reverse().join("/") : "—"}</td>
                  <td>€ {eur(b.importo)}</td>
                  <td className="dc-muted" style={{ fontSize: 12, maxWidth: 220 }}>{b.causale || "—"}</td>
                  <td>
                    <a href={`${API}/bonifici-da-associare/${b.id}/pdf`} target="_blank" rel="noreferrer" className="dc-btn dc-btn-ghost" style={{ fontSize: 12, padding: "3px 8px" }}>
                      Apri
                    </a>
                  </td>
                  <td>
                    <select className="dc-input" aria-label={`Dipendente per il bonifico del ${b.data ? b.data.split("-").reverse().join("/") : "?"} di € ${eur(b.importo)}`} value={sc.dipendente_id || ""} onChange={e => setScelta(b.id, "dipendente_id", e.target.value)} style={{ minWidth: 160 }}>
                      <option value="">— scegli —</option>
                      {dipOrdinati.map(d => <option key={d.id} value={d.id}>{d.nome_completo}</option>)}
                    </select>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 4 }}>
                      <select className="dc-input" aria-label={`Mese di competenza del bonifico di € ${eur(b.importo)}`} value={sc.mese || 1} onChange={e => setScelta(b.id, "mese", Number(e.target.value))} style={{ width: 100 }}>
                        {mesi.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
                      </select>
                      <input type="number" className="dc-input" aria-label={`Anno di competenza del bonifico di € ${eur(b.importo)}`} value={sc.anno || new Date().getFullYear()}
                        onChange={e => setScelta(b.id, "anno", Number(e.target.value))} style={{ width: 70 }} />
                    </div>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 6 }}>
                      <button className="dc-btn" disabled={busy === b.id} onClick={() => associa(b.id)}>
                        {busy === b.id ? "…" : "Associa"}
                      </button>
                      <button className="dc-btn dc-btn-ghost" disabled={busy === b.id} onClick={() => ignora(b.id)} title="Non e' un pagamento a un dipendente">
                        Ignora
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>}
    </div>
  );
}

function PagheBonificiPage({ dipendenti = [] }) {
  // 14/09/2026 (titolare): «Buste Paga» e «Cedolini & Bonifici» erano due
  // pagine sulla stessa tabella (paghe_mensili) con numeri diversi: la prima
  // riscriveva a mano busta e bonifico, la seconda leggeva i pagamenti reali
  // della banca col motore unico. Resta questa, con dentro tutte le funzioni
  // dell'altra: import (Libro Unico, email, Prima Nota, CSV banca, archivio
  // storico, Drive), acconti in contanti, prima nota per dipendente, ricerca
  // voci di busta, simulazione F24, griglia annuale.
  const mesi = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno","Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"];
  const annoCorr = new Date().getFullYear();
  const [anno, setAnno] = useState(annoCorr);
  const [mese, setMese] = useState(0); // 0 = tutto l'anno
  const [filtroStato, setFiltroStato] = useState("");
  const [data, setData] = useState({ righe: [], totali: {}, count: 0 });
  const [loading, setLoading] = useState(false);
  const [aperta, setAperta] = useState(null); // chiave riga espansa
  const [busy, setBusy] = useState(null);
  const [editPag, setEditPag] = useState(null);   // { key, mese, anno, importo, nota }
  const [editBusta, setEditBusta] = useState(null); // { k, dipendente_id, anno, mese, importo, nota }
  const [editAcc, setEditAcc] = useState(null);   // { k, dipendente_id, anno, mese, acconti: [{importo,data}] }
  const [exportBusy, setExportBusy] = useState(false);
  const [syncBusy, setSyncBusy] = useState(false);
  const [cedSyncBusy, setCedSyncBusy] = useState(false);
  const [driveBonificiUrl, setDriveBonificiUrl] = useState(null);
  const [griglia, setGriglia] = useState(false);
  // Import (ex pagina Buste Paga)
  const [showImport, setShowImport] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState(null);
  const [pnMsg, setPnMsg] = useState(null);
  const [csvMsg, setCsvMsg] = useState(null);
  const [storicoMsg, setStoricoMsg] = useState(null);
  const [driveMsg, setDriveMsg] = useState(null);
  const fileRef = useRef(null); const excelRef = useRef(null); const csvRef = useRef(null); const storicoRef = useRef(null);
  // Strumenti
  const [showStrumenti, setShowStrumenti] = useState(false);
  const [cercaQ, setCercaQ] = useState(""); const [cercaRes, setCercaRes] = useState(null); const [cercaBusy, setCercaBusy] = useState(false);
  const [rescanMsg, setRescanMsg] = useState("");
  const [f24, setF24] = useState(null); const [f24Busy, setF24Busy] = useState(false);
  const [pnDett, setPnDett] = useState(null);

  const eur = (n) => (Number(n) || 0).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const keyOf = (r) => `${r.dipendente_id}_${r.anno}_${r.mese}`;

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (anno) params.set("anno", anno);
      if (mese) params.set("mese", mese);
      if (filtroStato) params.set("stato", filtroStato);
      const r = await axios.get(`${API}/paghe/associazioni-bonifici?${params.toString()}`);
      setData(r.data || { righe: [], totali: {}, count: 0 });
    } catch (e) {
      console.error(e);
      setData({ righe: [], totali: {}, count: 0 });
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [anno, mese, filtroStato]);
  useEffect(() => {
    axios.get(`${API}/paghe/bonifici-drive-config`)
      .then((r) => setDriveBonificiUrl(r.data?.drive_url || null))
      .catch(() => setDriveBonificiUrl(null));
  }, []);

  const conferma = async (r, val) => {
    setBusy(keyOf(r));
    try {
      await axios.post(`${API}/paghe/conferma-associazione`, {
        dipendente_id: r.dipendente_id, anno: r.anno, mese: r.mese, riconciliato: val,
      });
      await load();
    } catch (e) { toast(e?.response?.data?.detail || "Errore conferma", "err"); }
    finally { setBusy(null); }
  };

  const salvaPagamento = async () => {
    if (!editPag) return;
    setBusy(editPag.key);
    try {
      const r = await axios.put(`${API}/paghe/pagamento-esito/${encodeURIComponent(editPag.key)}`, {
        mese: Number(editPag.mese), anno: Number(editPag.anno),
        importo: editPag.importo === "" ? null : Number(String(editPag.importo).replace(",", ".")),
        nota: editPag.nota || "",
      });
      const st = r.data?.stati || {};
      toast(`Pagamento spostato a ${mesi[Number(editPag.mese) - 1] || editPag.mese} ${editPag.anno}` +
        (Object.keys(st).length ? ` — stati: ${Object.entries(st).map(([p, s]) => `${p}: ${s}`).join(", ")}` : ""));
      setEditPag(null);
      await load();
    } catch (e) { toast(e?.response?.data?.detail || "Errore nello spostamento del pagamento", "err"); }
    finally { setBusy(null); }
  };

  const salvaBusta = async () => {
    if (!editBusta) return;
    setBusy(editBusta.k);
    try {
      const r = await axios.put(`${API}/paghe/importo-busta`, {
        dipendente_id: editBusta.dipendente_id, anno: editBusta.anno, mese: editBusta.mese,
        importo_busta: Number(String(editBusta.importo).replace(",", ".")), nota: editBusta.nota || "",
      });
      toast(`Importo busta aggiornato: € ${eur(r.data?.importo_busta)} (stato ${r.data?.stato})`);
      setEditBusta(null);
      await load();
    } catch (e) { toast(e?.response?.data?.detail || "Errore nella modifica della busta", "err"); }
    finally { setBusy(null); }
  };

  const salvaAcconti = async () => {
    if (!editAcc) return;
    setBusy(editAcc.k);
    try {
      const r = await axios.put(`${API}/paghe/acconti`, {
        dipendente_id: editAcc.dipendente_id, anno: editAcc.anno, mese: editAcc.mese,
        acconti: editAcc.acconti.filter(a => a.importo !== "" && a.importo != null),
      });
      toast(`Acconti salvati (${r.data?.acconti?.length || 0}) · stato ${r.data?.stato}`);
      setEditAcc(null);
      await load();
    } catch (e) { toast(e?.response?.data?.detail || "Errore nel salvataggio degli acconti", "err"); }
    finally { setBusy(null); }
  };

  const recuperaStorici = async () => {
    setSyncBusy(true);
    try {
      const r = await axios.post(`${API}/paghe/sincronizza-bonifici-storici`, {});
      const d = r.data || {};
      toast(`Bonifici storici collegati: ${d.importati_in_pagamenti_esiti || 0} su ${d.mesi_aggiornati || 0} mesi aggiornati`);
      await load();
    } catch (e) { toast(e?.response?.data?.detail || "Errore sincronizzazione", "err"); }
    finally { setSyncBusy(false); }
  };

  const sincronizzaDaCedolini = async () => {
    setCedSyncBusy(true);
    try {
      const r = await axios.post(`${API}/paghe/sincronizza`, {});
      const d = r.data || {};
      toast(`Registro paghe popolato dai cedolini: ${d.creati || 0} nuovi, ${d.aggiornati || 0} aggiornati, ${d.saltati_manuali || 0} lasciati (già modificati a mano)`);
      await load();
    } catch (e) { toast(e?.response?.data?.detail || "Errore sincronizzazione dai cedolini", "err"); }
    finally { setCedSyncBusy(false); }
  };

  const esportaExcel = async () => {
    setExportBusy(true);
    try {
      const params = new URLSearchParams();
      if (anno) params.set("anno", anno);
      if (mese) params.set("mese", mese);
      if (filtroStato) params.set("stato", filtroStato);
      const r = await axios.get(`${API}/paghe/associazioni-bonifici/export-excel?${params.toString()}`, { responseType: "blob" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(r.data);
      a.download = `cedolini_bonifici${anno ? `_${anno}` : ""}${mese ? `_${String(mese).padStart(2, '0')}` : ""}.xlsx`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 10000);
    } catch (e) { toast("Errore generazione Excel", "err"); }
    finally { setExportBusy(false); }
  };

  const apriCedolino = async (riga) => {
    if (!riga?.cedolino_id) return;
    const chiaveBusy = `cedolino_${keyOf(riga)}`;
    const nuovaFinestra = window.open("", "_blank");
    setBusy(chiaveBusy);
    try {
      const risposta = await axios.get(
        `/hr/api/cedolini/${encodeURIComponent(riga.cedolino_id)}/download`,
        { responseType: "blob", timeout: 60000 },
      );
      const url = URL.createObjectURL(risposta.data);
      if (nuovaFinestra) {
        nuovaFinestra.location = url;
      } else {
        const link = document.createElement("a");
        link.href = url;
        link.download = `cedolino_${riga.dipendente}_${riga.anno}_${String(riga.mese).padStart(2, "0")}.pdf`;
        link.click();
      }
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) {
      if (nuovaFinestra) nuovaFinestra.close();
      toast(e?.response?.data?.detail || "PDF del cedolino non disponibile", "err");
    } finally {
      setBusy(null);
    }
  };

  // ── Import (dalla vecchia pagina Buste Paga) ──
  const vaiAlMese = (r) => { if (r?.mesi?.length) { const u = r.mesi[r.mesi.length - 1]; setAnno(u.anno); setMese(u.mese); } };
  const handleImportLul = async (e) => {
    const fs = Array.from(e.target.files || []);
    if (!fs.length) return;
    setImporting(true); setImportMsg(null);
    try {
      const fd = new FormData(); fs.forEach(f => fd.append("files", f));
      const res = await axios.post(`${API}/paghe/importa-lul`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setImportMsg(res.data); vaiAlMese(res.data); await load();
    } catch (err) { setImportMsg({ errore: err.response?.data?.detail || "Errore durante l'import" }); }
    finally { setImporting(false); if (fileRef.current) fileRef.current.value = ""; }
  };
  const handleImportEmail = async () => {
    setImporting(true); setImportMsg(null);
    try {
      const res = await axios.post(`${API}/paghe/importa-email`);
      setImportMsg(res.data); vaiAlMese(res.data); await load();
    } catch (err) { setImportMsg({ errore: err.response?.data?.detail || "Errore durante l'import da email" }); }
    finally { setImporting(false); }
  };
  const handleImportPrimaNota = async (e) => {
    const fl = (e.target.files || [])[0];
    if (!fl) return;
    setImporting(true); setPnMsg(null);
    try {
      const fd = new FormData(); fd.append("file", fl);
      const r = await axios.post(`${API}/paghe/importa-prima-nota`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setPnMsg(r.data); await load();
    } catch (err) { setPnMsg({ errore: err?.response?.data?.detail || "Errore import Prima Nota" }); }
    finally { setImporting(false); if (excelRef.current) excelRef.current.value = ""; }
  };
  const handleImportPagamenti = async (e) => {
    const fl = (e.target.files || [])[0];
    if (!fl) return;
    setImporting(true); setCsvMsg(null);
    try {
      const fd = new FormData(); fd.append("file", fl);
      const r = await axios.post(`${API}/paghe/importa-pagamenti`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setCsvMsg(r.data); await load();
    } catch (err) { setCsvMsg({ errore: err?.response?.data?.detail || "Errore import pagamenti" }); }
    finally { setImporting(false); if (csvRef.current) csvRef.current.value = ""; }
  };
  const handleImportStorico = async (e) => {
    const fl = (e.target.files || [])[0];
    if (!fl) return;
    setImporting(true); setStoricoMsg(null);
    try {
      const fd = new FormData(); fd.append("file", fl);
      const r = await axios.post(`${API}/paghe/importa-storico-pagamenti`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setStoricoMsg(r.data);
    } catch (err) { setStoricoMsg({ errore: err?.response?.data?.detail || "Errore import archivio storico" }); }
    finally { setImporting(false); if (storicoRef.current) storicoRef.current.value = ""; }
  };
  const importaDaDrive = async () => {
    if (!window.confirm("Importo i PDF delle buste paga dai fascicoli Google Drive dei dipendenti?")) return;
    setImporting(true); setDriveMsg(null);
    try { const r = await axios.post(`/hr/api/cedolini/import-drive`, {}); setDriveMsg(r.data); await load(); }
    catch (e) { setDriveMsg({ errore: e?.response?.data?.detail || "Errore import da Drive" }); }
    finally { setImporting(false); }
  };

  // ── Strumenti ──
  const cercaVoce = async () => {
    const q = cercaQ.trim();
    if (!q) return;
    setCercaBusy(true); setCercaRes(null);
    const isCode = /^[A-Za-z]\d{3,5}$/.test(q);
    const params = isCode ? `codice=${encodeURIComponent(q.toUpperCase())}` : `testo=${encodeURIComponent(q)}`;
    try { const r = await axios.get(`${API}/cedolini/cerca-voce?${params}`); setCercaRes(r.data); }
    catch (e) { setCercaRes({ risultati: [], totale: 0, errore: e?.response?.data?.detail || "Errore ricerca" }); }
    finally { setCercaBusy(false); }
  };
  const riscansiona = async () => {
    if (!window.confirm("Riscansiona i cedolini storici con PDF salvato? Può richiedere fino a un minuto.")) return;
    setRescanMsg("Riscansione in corso…");
    try { const r = await axios.post(`${API}/cedolini/riscansiona`); setRescanMsg(`✓ Riscansione completata: ${r.data.aggiornati} cedolini aggiornati, ${r.data.errori} senza PDF/errore.`); }
    catch (e) { setRescanMsg("⚠ " + (e?.response?.data?.detail || "Errore riscansione")); }
  };
  const correggiAcconti = async () => {
    if (!window.confirm("Togliere gli 'acconto dal cedolino' implausibili (poche decine di euro, probabile errore di lettura) e ricalcolare il saldo? Non tocca gli acconti registrati a mano.")) return;
    setRescanMsg("Correzione acconti in corso…");
    try { const r = await axios.post(`${API}/paghe/correggi-acconti-cedolino`); setRescanMsg(`✓ Corretti ${r.data.corretti} acconti implausibili (rimossi, saldo ricalcolato sul netto pieno).`); await load(); }
    catch (e) { setRescanMsg("⚠ " + (e?.response?.data?.detail || "Errore correzione acconti")); }
  };
  const calcolaF24 = async () => {
    if (!mese) { toast("Scegli un mese per la simulazione F24", "err"); return; }
    setF24Busy(true); setF24(null);
    try { const r = await axios.get(`/hr/api/cedolini/simulazione-f24?anno=${anno}&mese=${mese}`); setF24(r.data); }
    catch (e) { setF24({ errore: e?.response?.data?.detail || "Errore nel calcolo" }); }
    finally { setF24Busy(false); }
  };
  const apriPrimaNota = async (dipId, nome) => {
    setPnDett({ nome, loading: true });
    try {
      const [r, st] = await Promise.all([
        axios.get(`${API}/paghe/prima-nota?dipendente_id=${dipId}`),
        axios.get(`${API}/paghe/storico-pagamenti?dipendente_id=${dipId}`).catch(() => ({ data: { righe: [] } })),
      ]);
      setPnDett({ nome, righe: r.data.righe || [], saldo_finale: r.data.saldo_finale, storico: st.data.righe || [] });
    } catch { setPnDett({ nome, righe: [], errore: true }); }
  };

  const t = data.totali || {};
  const STATI = {
    pagato: { label: "✓ Pagato", variant: "success" },
    parziale: { label: "Parziale", variant: "warning" },
    da_verificare: { label: "Da verificare", variant: "warning" },
    da_pagare: { label: "Da pagare", variant: "danger" },
    bonifico_senza_busta: { label: "Bonifico senza busta", variant: "info" },
  };
  const QUALITA = {
    esatto: { txt: "Confermato · importo coerente", col: "#234d3d", bg: "#e2efe8", bd: "#c2ddd0" },
    per_importo: { txt: "Confermato · ripartizione coerente", col: "#234d3d", bg: "#e2efe8", bd: "#c2ddd0" },
    aggregato: { txt: "Più bonifici", col: "#56442d", bg: "#f3ead9", bd: "#e7d6b9" },
    da_verificare: { txt: "Da verificare", col: "#7a3b32", bg: "#f6e4e1", bd: "#e8c5bf" },
  };
  const FONTI = { banca: "Estratto/CSV banca", prima_nota: "Prima nota", manuale: "Inserito a mano" };

  const cardWrap = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginBottom: 18 };
  const card = { background: "#fffefb", border: "1px solid #e6e0d4", borderRadius: 12, padding: "12px 14px" };
  const lbl = { fontSize: 11, color: "#7a8576", textTransform: "uppercase", letterSpacing: 0.4, fontWeight: 700 };
  const val = { fontSize: 20, fontWeight: 800, color: "#2a3329", marginTop: 4 };
  const sel = { border: "1px solid #e6e0d4", borderRadius: 8, padding: "7px 10px", fontSize: 14, background: "#fffefb", color: "#2a3329" };
  const th = { textAlign: "left", padding: "10px 12px", fontSize: 11, color: "#7a8576", textTransform: "uppercase", letterSpacing: 0.4, fontWeight: 700, borderBottom: "2px solid #e6e0d4", whiteSpace: "nowrap" };
  const td = { padding: "10px 12px", fontSize: 14, color: "#2a3329", borderBottom: "1px solid #efe9dd", verticalAlign: "top" };
  const msgCard = (m, ok) => ({ marginBottom: 16, borderLeft: `4px solid ${m?.errore ? '#d35f4e' : '#3d8168'}` });
  const nomeBtn = { background: "none", border: "none", color: "#5b7a6b", cursor: "pointer", textDecoration: "underline", padding: 0, font: "inherit", fontWeight: 600 };

  // Griglia annuale (dipendente × mese) calcolata dalle stesse righe
  const grigliaRighe = (() => {
    if (!griglia) return [];
    const perDip = {};
    for (const r of data.righe) {
      const g = perDip[r.dipendente_id] || (perDip[r.dipendente_id] = { dipendente: r.dipendente, id: r.dipendente_id, mesi: {}, busta: 0, erogato: 0 });
      if (r.mese >= 1 && r.mese <= 12) g.mesi[r.mese] = r;
      g.busta += r.busta; g.erogato += r.erogato;
    }
    return Object.values(perDip).sort((a, b) => a.dipendente.localeCompare(b.dipendente));
  })();

  return (
    <div style={{ maxWidth: 1280 }}>
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0, color: "#2a3329" }}>Archivio paghe</h2>
          <p className="dc-muted" style={{ marginTop: 4 }}>
            Per ogni busta: importo dal cedolino, <b>bonifici realmente pagati</b> (banca), acconti in contanti e saldo.
            Una sola pagina, un solo motore: i bonifici arrivano da soli dal gestionale (fascicoli Drive ed estratto conto),
            quelli da decidere a mano stanno in «Bonifici da associare». Clicca il nome per la prima nota del dipendente.
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }} aria-label="Archivi collegati">
            <a href="/hr/portale" className="dc-btn" title="Apre il minisito mobile con PIN usato dai collaboratori">
              📱 Portale collaboratori
            </a>
            <a href="/riconciliazione/movimenti-banca" className="dc-btn" title="Apre tutti i movimenti dell'estratto conto nel registro contabile autorevole">
              🏦 Estratto conto completo
            </a>
            <a href="/riconciliazione/archivio-bonifici" className="dc-btn" title="Apre l'archivio completo dei bonifici nel gestionale">
              ↔ Tutti i bonifici
            </a>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", position: "relative" }}>
          <input ref={fileRef} type="file" accept=".pdf,.zip,application/pdf,application/zip,application/x-zip-compressed" multiple onChange={handleImportLul} style={{ display: "none" }} />
          <input ref={excelRef} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={handleImportPrimaNota} style={{ display: "none" }} />
          <input ref={csvRef} type="file" accept=".csv,text/csv" onChange={handleImportPagamenti} style={{ display: "none" }} />
          <input ref={storicoRef} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={handleImportStorico} style={{ display: "none" }} />
          <div style={{ position: "relative" }}>
            <button className="dc-btn dc-btn-primary" onClick={() => setShowImport(s => !s)} disabled={importing}>
              {importing ? "Importo…" : "⤵ Importa ▾"}
            </button>
            {showImport && (
              <div style={{ position: "absolute", top: "100%", left: 0, marginTop: 6, background: "#fffefb", border: "1px solid #e6e0d4", borderRadius: 10, boxShadow: "0 6px 20px rgba(0,0,0,.12)", zIndex: 30, minWidth: 300, overflow: "hidden" }}>
                {[["Libro Unico (PDF/ZIP)", () => fileRef.current?.click()],
                  ["Buste da email", handleImportEmail],
                  ["Buste dai fascicoli Drive", importaDaDrive],
                  ["Prima Nota (Excel)", () => excelRef.current?.click()],
                  ["Pagamenti banca (CSV)", () => csvRef.current?.click()],
                  ["Archivio storico pagamenti ante-app (Excel)", () => storicoRef.current?.click()]].map(([label, fn], i, arr) => (
                  <button key={i} onClick={() => { setShowImport(false); fn(); }}
                    style={{ display: "block", width: "100%", textAlign: "left", background: "none", border: "none", borderBottom: i < arr.length - 1 ? "1px solid #f0ebe0" : "none", padding: "11px 14px", fontSize: 14, cursor: "pointer", color: "#2a3329" }}>{label}</button>
                ))}
              </div>
            )}
          </div>
          <button className="dc-btn" disabled={cedSyncBusy} onClick={sincronizzaDaCedolini} title="Popola questo registro dai cedolini in archivio">
            {cedSyncBusy ? "Sincronizzo…" : "🔄 Sincronizza da cedolini"}
          </button>
          <button className="dc-btn" disabled={syncBusy} onClick={recuperaStorici} title="Collega alla busta i bonifici storici già archiviati ma non ancora agganciati qui">
            {syncBusy ? "Collego…" : "🔗 Recupera bonifici storici"}
          </button>
          <button className="dc-btn" disabled={exportBusy} onClick={esportaExcel}>
            {exportBusy ? "Esporto…" : "📊 Esporta Excel"}
          </button>
          <button className="dc-btn" onClick={() => setShowStrumenti(s => !s)}>🔎 Strumenti {showStrumenti ? "▲" : "▼"}</button>
          {driveBonificiUrl && <a href={driveBonificiUrl} target="_blank" rel="noreferrer" className="dc-btn" title="Fascicoli dei dipendenti su Drive: un PDF messo in <persona>/BONIFICI/DA ELABORARE entra qui da solo entro 15 minuti">
            📁 Fascicoli Drive
          </a>}
        </div>
      </div>

      {importMsg && (
        <div className="dc-card" style={msgCard(importMsg)}>
          {importMsg.errore ? <div style={{ color: "#d35f4e", fontWeight: 600 }}>⚠ {importMsg.errore}</div> : (
            <div>
              <div style={{ fontWeight: 700, marginBottom: 6 }}>
                ✓ Elaborati {importMsg.file_pdf} documenti · {importMsg.totale_associati} buste{importMsg.bonifici?.length ? ` · ${importMsg.bonifici.length} bonifici` : ""}{importMsg.prestiti?.length ? ` · ${importMsg.prestiti.length} prestiti` : ""}{importMsg.presenze?.length ? ` · ${importMsg.presenze.length} presenze` : ""}
              </div>
              {importMsg.mesi?.length > 0 && <div style={{ fontSize: 13, marginBottom: 6 }}>Mesi importati: {importMsg.mesi.map(mm => `${mesi[mm.mese - 1]} ${mm.anno} (${mm.n})`).join(" · ")}</div>}
              <div style={{ fontSize: 13, color: "#6b7669", display: "flex", flexWrap: "wrap", gap: "2px 14px" }}>
                {importMsg.associati?.map((a, i) => <span key={i}>{a.dipendente}: € {eur(a.netto)}{importMsg.mesi?.length > 1 ? ` (${a.mese}/${a.anno})` : ""}{a.metodo !== "codice fiscale" ? " ⚠" : ""}</span>)}
              </div>
              {importMsg.bonifici?.length > 0 && (
                <div style={{ marginTop: 10, fontSize: 13 }}>
                  <div style={{ fontWeight: 700, marginBottom: 4, color: "#234d3d" }}>Bonifici associati ({importMsg.bonifici.length})</div>
                  {importMsg.bonifici.map((b, i) => <div key={i}>{b.dipendente}: € {eur(b.importo)} → {mesi[b.mese - 1]} {b.anno} <span style={{ color: "#6b7669" }}>[{b.fonte}]</span>{b.discrepanza != null && <span style={{ color: "#7d5526" }}> (Excel attendeva € {eur(b.discrepanza)})</span>}</div>)}
                </div>
              )}
              {importMsg.tfr?.length > 0 && (
                <div style={{ marginTop: 10, fontSize: 13 }}>
                  <div style={{ fontWeight: 700, marginBottom: 4, color: "#56442d" }}>Anticipi TFR ({importMsg.tfr.length}) — fuori dal saldo stipendi</div>
                  {importMsg.tfr.map((x, i) => <div key={i}>{x.dipendente}: € {eur(x.importo)} → {mesi[x.mese - 1]} {x.anno}</div>)}
                </div>
              )}
              {importMsg.non_associati?.length > 0 && <div style={{ marginTop: 8, fontSize: 13, color: "#7d5526" }}>⚠ Non associati: {importMsg.non_associati.map(x => x.file || x).join(", ")}</div>}
            </div>
          )}
        </div>
      )}
      {driveMsg && (
        <div className="dc-card" style={msgCard(driveMsg)}>
          {driveMsg.errore ? <div style={{ color: "#d35f4e", fontWeight: 600 }}>⚠ {driveMsg.errore}</div>
            : <div style={{ fontWeight: 700 }}>✓ Drive: {driveMsg.trovati_pdf} PDF trovati · {driveMsg.archiviati} archiviati · {driveMsg.duplicati} duplicati saltati{(driveMsg.non_assegnati || []).length ? ` · da controllare: ${driveMsg.non_assegnati.join(", ")}` : ""}</div>}
        </div>
      )}
      {pnMsg && (
        <div className="dc-card" style={msgCard(pnMsg)}>
          {pnMsg.errore ? <div style={{ color: "#d35f4e", fontWeight: 600 }}>⚠ {pnMsg.errore}</div> : (
            <div>
              <div style={{ fontWeight: 700 }}>✓ Prima Nota importata: {pnMsg.aggiornati} mesi/dipendente aggiornati su {pnMsg.righe_aggregate} totali.</div>
              {pnMsg.non_trovati > 0 && <div style={{ marginTop: 6, fontSize: 13, color: "#7d5526" }}>⚠ {pnMsg.non_trovati} voci con dipendente non in anagrafica (non importate): {(pnMsg.nomi_non_trovati || []).join(", ")}</div>}
              {pnMsg.discrepanze?.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 13 }}>
                  <div style={{ fontWeight: 700, color: "#7d5526" }}>Differenze importo busta (app vs Excel) — {pnMsg.discrepanze.length}:</div>
                  {pnMsg.discrepanze.slice(0, 60).map((x, i) => <div key={i}>{x.dipendente} · {mesi[x.mese - 1]} {x.anno}: app € {eur(x.busta_app)} · Excel € {eur(x.busta_excel)}</div>)}
                </div>
              )}
            </div>
          )}
        </div>
      )}
      {csvMsg && (
        <div className="dc-card" style={msgCard(csvMsg)}>
          {csvMsg.errore ? <div style={{ color: "#d35f4e", fontWeight: 600 }}>⚠ {csvMsg.errore}</div> : (
            <div style={{ fontSize: 14 }}>
              <div style={{ fontWeight: 700 }}>✓ Pagamenti importati: {csvMsg.importati} · {csvMsg.mesi_aggiornati} mesi aggiornati.</div>
              {csvMsg.non_trovati?.length > 0 && <div style={{ marginTop: 6, fontSize: 13, color: "#7d5526" }}>⚠ Beneficiari non trovati in anagrafica: {csvMsg.non_trovati.join(", ")}</div>}
            </div>
          )}
        </div>
      )}
      {storicoMsg && (
        <div className="dc-card" style={msgCard(storicoMsg)}>
          {storicoMsg.errore ? <div style={{ color: "#d35f4e", fontWeight: 600 }}>⚠ {storicoMsg.errore}</div> : (
            <div style={{ fontSize: 14 }}>
              <div style={{ fontWeight: 700 }}>✓ Archivio storico: {storicoMsg.importati} righe nuove, {storicoMsg.gia_presenti} già presenti (su {storicoMsg.righe_lette} lette).</div>
              {storicoMsg.dipendenti_non_in_anagrafica?.length > 0 && <div style={{ marginTop: 6, fontSize: 13, color: "#7d5526" }}>⚠ Nomi non trovati in anagrafica (non importati): {storicoMsg.dipendenti_non_in_anagrafica.map(x => `${x.nome} (${x.righe})`).join(", ")}</div>}
            </div>
          )}
        </div>
      )}

      {showStrumenti && (
        <div className="dc-card" style={{ marginBottom: 16 }}>
          <h3 style={{ marginTop: 0 }}>🔎 Cerca nelle buste (qualsiasi voce)</h3>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <input className="dc-input" style={{ flex: "1 1 240px" }} placeholder="Codice (es. F09081) o testo (es. 730, 13ma, L.207)"
              value={cercaQ} onChange={e => setCercaQ(e.target.value)} onKeyDown={e => e.key === "Enter" && cercaVoce()} />
            <button className="dc-btn-primary" disabled={cercaBusy} onClick={cercaVoce}>{cercaBusy ? "Cerco…" : "Cerca"}</button>
            <button className="dc-btn" onClick={riscansiona} title="Rilegge i PDF dei cedolini già caricati per popolare la ricerca sullo storico">Riscansiona storico</button>
            <button className="dc-btn" onClick={correggiAcconti} title="Toglie gli 'acconto dal cedolino' di poche decine di euro (probabile errore del parser) e ricalcola il saldo">🔧 Correggi acconti cedolino</button>
          </div>
          {rescanMsg && <div className="dc-muted" style={{ marginTop: 8 }}>{rescanMsg}</div>}
          {cercaRes && (
            <div style={{ marginTop: 10, overflowX: "auto" }}>
              {cercaRes.errore ? <div className="dc-muted">⚠ {cercaRes.errore}</div>
                : cercaRes.totale === 0 ? <div className="dc-muted">Nessun risultato. Per lo storico premi prima “Riscansiona storico”.</div>
                : <table className="dc-table" style={{ minWidth: 560, whiteSpace: "nowrap" }}>
                    <thead><tr><th>Dipendente</th><th>Periodo</th><th>Codice</th><th>Descrizione</th><th style={{ textAlign: "right" }}>Importo</th></tr></thead>
                    <tbody>{cercaRes.risultati.map((x, i) => <tr key={i}><td>{x.dipendente}</td><td>{mesi[(x.mese || 1) - 1]} {x.anno}</td><td>{x.codice}</td><td>{x.descrizione}</td><td style={{ textAlign: "right" }}>{x.importo || "—"}</td></tr>)}</tbody>
                  </table>}
              {cercaRes.totale > 0 && <p className="dc-muted" style={{ fontSize: 12, marginTop: 6 }}>{cercaRes.totale} risultati.</p>}
            </div>
          )}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap", marginTop: 18 }}>
            <h3 style={{ margin: 0 }}>🧾 Simulazione F24 e costo mensile — {mese ? `${mesi[mese - 1]} ${anno}` : "scegli un mese nel filtro"}</h3>
            <button className="dc-btn-primary" disabled={f24Busy || !mese} onClick={calcolaF24}>{f24Busy ? "Calcolo…" : "Calcola F24 del mese"}</button>
          </div>
          <p className="dc-muted" style={{ fontSize: 12.5, margin: "6px 0 0" }}>
            Per ogni dipendente legge il cedolino del mese: IRPEF e INPS reali dalle voci quando ci sono, altrimenti stimati dal netto con le regole CCNL.
            INPS azienda 30%, quota TFR = lordo ÷ 13,5. È una simulazione: fa fede l'F24 del consulente.
          </p>
          {f24?.errore && <div style={{ marginTop: 8, color: "#d35f4e", fontWeight: 600 }}>⚠ {f24.errore}</div>}
          {f24 && !f24.errore && (f24.righe.length === 0
            ? <p className="dc-muted" style={{ marginTop: 10 }}>Nessun cedolino trovato per {mesi[mese - 1]} {anno}: importa prima le buste.</p>
            : <div className="dc-scroll-x" style={{ marginTop: 10 }}>
                <table className="dc-table" style={{ fontSize: 13 }}>
                  <thead><tr><th>Dipendente</th><th style={{ textAlign: "right" }}>Lordo €</th><th style={{ textAlign: "right" }}>Netto €</th><th style={{ textAlign: "right" }}>IRPEF €</th><th style={{ textAlign: "right" }}>INPS dip. €</th><th style={{ textAlign: "right" }}>INPS azienda €</th><th style={{ textAlign: "right" }}>TFR mese €</th><th style={{ textAlign: "right" }}>F24 €</th><th style={{ textAlign: "right" }}>Costo azienda €</th><th>Fonte</th></tr></thead>
                  <tbody>
                    {f24.righe.map(r => (
                      <tr key={r.dipendente_id || r.dipendente_nome}>
                        <td style={{ fontWeight: 600 }}>{r.dipendente_nome}</td>
                        <td style={{ textAlign: "right" }}>{eur(r.lordo)}</td><td style={{ textAlign: "right" }}>{eur(r.netto)}</td><td style={{ textAlign: "right" }}>{eur(r.irpef)}</td>
                        <td style={{ textAlign: "right" }}>{eur(r.inps_dipendente)}</td><td style={{ textAlign: "right" }}>{eur(r.inps_azienda)}</td><td style={{ textAlign: "right" }}>{eur(r.tfr_mese)}</td>
                        <td style={{ textAlign: "right", fontWeight: 700 }}>{eur(r.totale_f24)}</td><td style={{ textAlign: "right", fontWeight: 700 }}>{eur(r.costo_azienda)}</td>
                        <td className="dc-muted" style={{ fontSize: 11.5 }}>{r.fonte}</td>
                      </tr>
                    ))}
                    <tr style={{ fontWeight: 700, borderTop: "2px solid #e6e0d4", background: "#eef1ea" }}>
                      <td>TOTALE ({f24.dipendenti} dipendenti)</td>
                      <td style={{ textAlign: "right" }}>{eur(f24.totali.lordo)}</td><td style={{ textAlign: "right" }}>{eur(f24.totali.netto)}</td><td style={{ textAlign: "right" }}>{eur(f24.totali.irpef)}</td>
                      <td style={{ textAlign: "right" }}>{eur(f24.totali.inps_dipendente)}</td><td style={{ textAlign: "right" }}>{eur(f24.totali.inps_azienda)}</td><td style={{ textAlign: "right" }}>{eur(f24.totali.tfr_mese)}</td>
                      <td style={{ textAlign: "right", fontSize: 15 }}>{eur(f24.totali.totale_f24)}</td><td style={{ textAlign: "right", fontSize: 15 }}>{eur(f24.totali.costo_azienda)}</td><td></td>
                    </tr>
                  </tbody>
                </table>
              </div>)}
        </div>
      )}

      {/* Filtri */}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 16 }}>
        <select style={sel} aria-label="Anno" value={anno} onChange={e => setAnno(Number(e.target.value))}>
          {Array.from({ length: 9 }, (_, i) => annoCorr + 1 - i).map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <select style={sel} aria-label="Mese" value={mese} onChange={e => setMese(Number(e.target.value))}>
          <option value={0}>Tutto l'anno</option>
          {mesi.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
          <option value={13}>Tredicesima</option>
          <option value={14}>Quattordicesima</option>
        </select>
        <select style={sel} aria-label="Stato pagamento" value={filtroStato} onChange={e => setFiltroStato(e.target.value)}>
          <option value="">Tutti gli stati</option>
          <option value="pagato">Pagati</option>
          <option value="parziale">Parziali</option>
          <option value="da_verificare">Da verificare</option>
          <option value="da_pagare">Da pagare</option>
          <option value="bonifico_senza_busta">Bonifico senza busta</option>
        </select>
        <label style={{ display: "flex", alignItems: "center", gap: 5, cursor: "pointer", fontSize: 13 }}><input type="checkbox" checked={griglia} onChange={e => setGriglia(e.target.checked)} /> Griglia annuale</label>
        <button className="dc-btn" onClick={load} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <RefreshCw size={15} /> Aggiorna
        </button>
      </div>

      {/* Riepilogo */}
      <div style={cardWrap}>
        <div style={card}><div style={lbl}>Totale buste</div><div style={val}>€ {eur(t.buste)}</div></div>
        <div style={card}><div style={lbl}>Bonifici</div><div style={{ ...val, color: "#3d8168" }}>€ {eur(t.bonifici)}</div></div>
        <div style={card}><div style={lbl}>Acconti</div><div style={val}>€ {eur(t.acconti)}</div></div>
        <div style={card}><div style={lbl}>Saldo da pagare</div><div style={{ ...val, color: (t.saldo > 0.5 ? "#b04a3a" : "#3d8168") }}>€ {eur(t.saldo)}</div></div>
        <div style={card}><div style={lbl}>Pagati</div><div style={{ ...val, color: "#3d8168" }}>{t.pagati || 0}</div></div>
        <div style={card}><div style={lbl}>Da pagare</div><div style={{ ...val, color: "#b04a3a" }}>{t.da_pagare || 0}</div></div>
        <div style={card}><div style={lbl}>Da verificare</div><div style={{ ...val, color: "#7a3b32" }}>{t.da_verificare || 0}</div></div>
      </div>

      {griglia && (
        <div style={{ background: "#fffefb", border: "1px solid #e6e0d4", borderRadius: 12, overflow: "hidden", marginBottom: 16 }}>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead><tr><th style={th}>Dipendente</th>{mesi.map((m, i) => <th key={i} style={{ ...th, textAlign: "center" }} title={m}>{m.slice(0, 3)}</th>)}<th style={{ ...th, textAlign: "right" }}>Buste</th><th style={{ ...th, textAlign: "right" }}>Erogato</th><th style={{ ...th, textAlign: "right" }}>Differenza</th></tr></thead>
              <tbody>
                {grigliaRighe.length === 0 && <tr><td style={td} colSpan={16}>Nessuna busta nell'anno.</td></tr>}
                {grigliaRighe.map(g => (
                  <tr key={g.id}>
                    <td style={{ ...td, fontWeight: 600 }}><button style={nomeBtn} onClick={() => apriPrimaNota(g.id, g.dipendente)}>{g.dipendente}</button></td>
                    {mesi.map((m, i) => {
                      const r = g.mesi[i + 1];
                      let txt = "·", col = "#cbd2c9", title = `${m}: nessun dato`;
                      if (r) {
                        if (r.stato === "pagato") { txt = "✓"; col = "#3d8168"; title = `${m}: pagato (busta € ${eur(r.busta)})`; }
                        else if (r.stato === "bonifico_senza_busta") { txt = "+" + eur(r.erogato); col = "#7d5526"; title = `${m}: erogato € ${eur(r.erogato)} senza busta`; }
                        else if (r.stato === "da_verificare") { txt = "?"; col = "#7a3b32"; title = `${m}: da verificare (erogato € ${eur(r.erogato)} su busta € ${eur(r.busta)})`; }
                        else if (r.saldo > 0.5) { txt = eur(r.saldo); col = "#d35f4e"; title = `${m}: manca € ${eur(r.saldo)} (busta € ${eur(r.busta)}, erogato € ${eur(r.erogato)})`; }
                        else { txt = "+" + eur(-r.saldo); col = "#7d5526"; title = `${m}: eccedenza € ${eur(-r.saldo)}`; }
                      }
                      return <td key={i} style={{ ...td, textAlign: "right", color: col, fontWeight: 700 }} title={title}>{txt}</td>;
                    })}
                    <td style={{ ...td, textAlign: "right" }}>{eur(g.busta)}</td>
                    <td style={{ ...td, textAlign: "right" }}>{eur(g.erogato)}</td>
                    <td style={{ ...td, textAlign: "right", fontWeight: 700, color: g.busta - g.erogato > 0.5 ? "#d35f4e" : "#3d8168" }}>{eur(g.erogato - g.busta)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="dc-muted" style={{ fontSize: 12, margin: "8px 12px" }}>✓ pagato · importo rosso = manca · + = eccedenza · ? = pagamento da confermare. Fa fede l'elenco qui sotto.</p>
        </div>
      )}

      {/* Tabella */}
      <div style={{ background: "#fffefb", border: "1px solid #e6e0d4", borderRadius: 12, overflow: "hidden" }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={th}>Dipendente</th>
                <th style={th}>Periodo</th>
                <th style={{ ...th, textAlign: "right" }}>Busta</th>
                <th style={{ ...th, textAlign: "right" }}>Bonifico</th>
                <th style={{ ...th, textAlign: "right" }}>Acconti</th>
                <th style={{ ...th, textAlign: "right" }}>Saldo</th>
                <th style={th}>Stato</th>
                <th style={th}>Associazione</th>
                <th style={th}>Cedolino</th>
                <th style={th}></th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td style={td} colSpan={10}>Caricamento…</td></tr>}
              {!loading && data.righe.length === 0 && <tr><td style={td} colSpan={10}>Nessuna busta per il periodo selezionato. Se le buste sono in archivio premi «Sincronizza da cedolini».</td></tr>}
              {!loading && data.righe.map(r => {
                const k = keyOf(r);
                const exp = aperta === k;
                const stInfo = STATI[r.stato] || { label: r.stato, variant: "default" };
                const qInfo = r.qualita ? QUALITA[r.qualita] : null;
                const periodoLbl = (r.mese >= 1 && r.mese <= 12) ? `${mesi[r.mese - 1]} ${r.anno}` : r.mese === 13 ? `13ª ${r.anno}` : r.mese === 14 ? `14ª ${r.anno}` : `${r.mese}/${r.anno}`;
                return (
                  <Fragment key={k}>
                    <tr style={{ background: exp ? "#f7f4ec" : "transparent" }}>
                      <td style={{ ...td, fontWeight: 600 }}><button style={nomeBtn} title="Prima nota / saldo progressivo" onClick={() => apriPrimaNota(r.dipendente_id, r.dipendente)}>{r.dipendente}</button></td>
                      <td style={td}>{periodoLbl}</td>
                      <td style={{ ...td, textAlign: "right" }}>
                        {editBusta && editBusta.k === k ? (
                          <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-end" }}>
                            <input type="number" step="0.01" min="0" value={editBusta.importo} onChange={e => setEditBusta({ ...editBusta, importo: e.target.value })} style={{ ...sel, width: 110, textAlign: "right", padding: "4px 6px" }} />
                            <input type="text" placeholder="nota (perché)" value={editBusta.nota} onChange={e => setEditBusta({ ...editBusta, nota: e.target.value })} style={{ ...sel, width: 150, padding: "4px 6px", fontSize: 12 }} />
                            <div style={{ display: "flex", gap: 4 }}>
                              <button className="dc-btn" disabled={busy === k} onClick={salvaBusta} style={{ fontSize: 12, padding: "3px 8px" }}>Salva</button>
                              <button className="dc-btn" onClick={() => setEditBusta(null)} style={{ fontSize: 12, padding: "3px 8px" }}>Annulla</button>
                            </div>
                          </div>
                        ) : (
                          <span>
                            {r.busta > 0 ? `€ ${eur(r.busta)}` : "—"}
                            <button className="dc-btn" title={r.busta_manuale ? `Importo corretto a mano (prima: € ${eur(r.busta_originale)})${r.busta_nota ? " — " + r.busta_nota : ""}` : "Correggi l'importo della busta se non torna col cedolino"}
                              onClick={() => setEditBusta({ k, dipendente_id: r.dipendente_id, anno: r.anno, mese: r.mese, importo: r.busta || "", nota: r.busta_nota || "" })}
                              aria-label={`Correggi importo busta ${r.mese}/${r.anno} di ${r.dipendente_nome || ""}`}
                              style={{ fontSize: 11, padding: "1px 6px", marginLeft: 6, color: r.busta_manuale ? "#8a6f47" : undefined }}>✎</button>
                            {r.busta_manuale && <div style={{ fontSize: 10, color: "#8a6f47" }}>corretto a mano</div>}
                          </span>
                        )}
                      </td>
                      <td style={{ ...td, textAlign: "right", color: r.bonifico > 0 ? "#3d8168" : "#9aa295", fontWeight: 600 }}>
                        {r.bonifico > 0 ? `€ ${eur(r.bonifico)}` : "—"}
                        {r.fonte && <div style={{ fontSize: 10, color: "#9aa295", fontWeight: 400 }}>{FONTI[r.fonte] || r.fonte}</div>}
                      </td>
                      <td style={{ ...td, textAlign: "right" }}>{r.acconti > 0 ? `€ ${eur(r.acconti)}` : "—"}</td>
                      <td style={{ ...td, textAlign: "right", color: r.saldo > 0.5 ? "#b04a3a" : "#3d8168" }}>
                        {Math.abs(r.saldo) > 0.5 ? `€ ${eur(r.saldo)}` : "✓"}
                      </td>
                      <td style={td}><Badge variant={stInfo.variant}>{stInfo.label}</Badge></td>
                      <td style={td}>
                        {r.riconciliato
                          ? <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "#234d3d", fontWeight: 700, fontSize: 12 }}><CheckCircle2 size={14} /> Confermata</span>
                          : qInfo
                            ? <span style={{ background: qInfo.bg, color: qInfo.col, border: `1px solid ${qInfo.bd}`, borderRadius: 6, padding: "2px 7px", fontSize: 11, fontWeight: 700 }}>{qInfo.txt}</span>
                            : <span style={{ color: "#9aa295", fontSize: 12 }}>—</span>}
                      </td>
                      <td style={td}>
                        {r.cedolino_pdf && r.cedolino_id
                          ? <button className="dc-btn" disabled={busy === `cedolino_${k}`} onClick={() => apriCedolino(r)} style={{ fontSize: 12, padding: "4px 8px", color: "#234d3d", fontWeight: 600 }}>
                              {busy === `cedolino_${k}` ? "Apro…" : "📄 Apri PDF"}
                            </button>
                          : r.cedolino_pdf
                            ? <span style={{ color: "#234d3d", fontSize: 12, fontWeight: 600 }}>PDF presente</span>
                          : <span style={{ color: "#9aa295", fontSize: 12 }}>no PDF</span>}
                      </td>
                      <td style={{ ...td, whiteSpace: "nowrap" }}>
                        <button className="dc-btn" onClick={() => setAperta(exp ? null : k)} style={{ fontSize: 12, padding: "4px 8px" }}>
                          {exp ? "Nascondi" : `Dettagli${r.n_bonifici ? ` (${r.n_bonifici})` : ""}`}
                        </button>
                        {(r.bonifico > 0 || r.stato === "bonifico_senza_busta") && (
                          r.riconciliato
                            ? <button className="dc-btn" disabled={busy === k} onClick={() => conferma(r, false)} style={{ fontSize: 12, padding: "4px 8px", marginLeft: 6 }}>Annulla</button>
                            : <button className="dc-btn" disabled={busy === k} onClick={() => conferma(r, true)} style={{ fontSize: 12, padding: "4px 8px", marginLeft: 6 }}>Conferma</button>
                        )}
                      </td>
                    </tr>
                    {exp && (
                      <tr>
                        <td style={{ ...td, background: "#f7f4ec" }} colSpan={10}>
                          {r.bonifici.length > 0 && (<>
                            <div style={{ fontSize: 12, color: "#7a8576", marginBottom: 6 }}>
                              Un bonifico arrivato nel mese sbagliato (es. il 1° gennaio per la busta di dicembre) si sposta con <b>Sposta / modifica</b>: il sistema ricalcola entrambi i mesi.
                            </div>
                            <div style={{ fontSize: 11, color: "#7a8576", fontWeight: 700, textTransform: "uppercase", marginBottom: 6 }}>Bonifici realmente pagati</div>
                            <table style={{ width: "100%", borderCollapse: "collapse" }}>
                              <thead>
                                <tr>
                                  <th style={{ ...th, borderBottom: "1px solid #e6e0d4" }}>Data</th>
                                  <th style={{ ...th, borderBottom: "1px solid #e6e0d4", textAlign: "right" }}>Importo</th>
                                  <th style={{ ...th, borderBottom: "1px solid #e6e0d4" }}>Causale</th>
                                  <th style={{ ...th, borderBottom: "1px solid #e6e0d4" }}>Beneficiario</th>
                                  <th style={{ ...th, borderBottom: "1px solid #e6e0d4" }}>Riferimento</th>
                                  <th style={{ ...th, borderBottom: "1px solid #e6e0d4" }}>PDF</th>
                                  <th style={{ ...th, borderBottom: "1px solid #e6e0d4" }}>Periodo / importo</th>
                                </tr>
                              </thead>
                              <tbody>
                                {r.bonifici.map((b, i) => (
                                  <tr key={i}>
                                    <td style={{ ...td, borderBottom: "none" }}>{b.data || "—"}</td>
                                    <td style={{ ...td, borderBottom: "none", textAlign: "right", color: "#3d8168", fontWeight: 600 }}>
                                      € {eur(b.importo)}
                                      {b.modificato && <div style={{ fontSize: 10, color: "#8a6f47", fontWeight: 400 }}>modificato a mano</div>}
                                    </td>
                                    <td style={{ ...td, borderBottom: "none", fontSize: 13 }}>{b.causale || "—"}</td>
                                    <td style={{ ...td, borderBottom: "none", fontSize: 13 }}>{b.beneficiario || "—"}</td>
                                    <td style={{ ...td, borderBottom: "none", fontSize: 12, color: "#7a8576" }}>{b.riferimento || "—"}</td>
                                    <td style={{ ...td, borderBottom: "none", fontSize: 12 }}>
                                      {b.pdf_key
                                        ? <a href={`${API}/paghe/pagamento-esito/${b.pdf_key}/pdf`} target="_blank" rel="noreferrer" style={{ color: "#3d8168", fontWeight: 600 }}>📄 Apri PDF</a>
                                        : <span style={{ color: "#9aa295" }}>no PDF</span>}
                                    </td>
                                    <td style={{ ...td, borderBottom: "none", fontSize: 12, whiteSpace: "nowrap" }}>
                                      {editPag && editPag.key === b.key ? (
                                        <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
                                          <select value={editPag.mese} onChange={e => setEditPag({ ...editPag, mese: e.target.value })} style={{ ...sel, padding: "4px 6px", fontSize: 12 }}>
                                            {mesi.map((m, idx) => <option key={idx + 1} value={idx + 1}>{m}</option>)}
                                            <option value={13}>Tredicesima</option>
                                            <option value={14}>Quattordicesima</option>
                                          </select>
                                          <input type="number" value={editPag.anno} onChange={e => setEditPag({ ...editPag, anno: e.target.value })} style={{ ...sel, width: 70, padding: "4px 6px", fontSize: 12 }} />
                                          <input type="number" step="0.01" min="0" value={editPag.importo} onChange={e => setEditPag({ ...editPag, importo: e.target.value })} style={{ ...sel, width: 100, padding: "4px 6px", fontSize: 12, textAlign: "right" }} />
                                          <input type="text" placeholder="nota" value={editPag.nota} onChange={e => setEditPag({ ...editPag, nota: e.target.value })} style={{ ...sel, width: 140, padding: "4px 6px", fontSize: 12 }} />
                                          <button className="dc-btn" disabled={busy === b.key} onClick={salvaPagamento} style={{ fontSize: 12, padding: "3px 8px" }}>Salva</button>
                                          <button className="dc-btn" onClick={() => setEditPag(null)} style={{ fontSize: 12, padding: "3px 8px" }}>Annulla</button>
                                        </div>
                                      ) : (
                                        b.key
                                          ? <button className="dc-btn" title="Sposta questo pagamento a un altro mese (es. bonifico del 1° gennaio → dicembre) o correggi l'importo"
                                              onClick={() => setEditPag({ key: b.key, mese: r.mese, anno: r.anno, importo: b.importo, nota: "" })}
                                              style={{ fontSize: 12, padding: "3px 8px" }}>Sposta / modifica</button>
                                          : <span style={{ color: "#9aa295" }}>—</span>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </>)}
                          <div style={{ marginTop: r.bonifici.length ? 12 : 0 }}>
                            <div style={{ fontSize: 11, color: "#7a8576", fontWeight: 700, textTransform: "uppercase", marginBottom: 6 }}>Acconti in contanti (massimo 3)</div>
                            {editAcc && editAcc.k === k ? (
                              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                {editAcc.acconti.map((a, i) => (
                                  <div key={i} style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                                    <input type="number" step="0.01" min="0" placeholder="importo" value={a.importo} onChange={e => setEditAcc({ ...editAcc, acconti: editAcc.acconti.map((x, j) => j === i ? { ...x, importo: e.target.value } : x) })} style={{ ...sel, width: 110, padding: "4px 6px", textAlign: "right" }} />
                                    <input type="date" value={a.data || ""} onChange={e => setEditAcc({ ...editAcc, acconti: editAcc.acconti.map((x, j) => j === i ? { ...x, data: e.target.value } : x) })} style={{ ...sel, padding: "4px 6px" }} />
                                    <button className="dc-btn" onClick={() => setEditAcc({ ...editAcc, acconti: editAcc.acconti.filter((_, j) => j !== i) })} style={{ fontSize: 12, padding: "3px 8px" }}>Togli</button>
                                  </div>
                                ))}
                                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                                  {editAcc.acconti.length < 3 && <button className="dc-btn" onClick={() => setEditAcc({ ...editAcc, acconti: [...editAcc.acconti, { importo: "", data: "" }] })} style={{ fontSize: 12, padding: "3px 8px" }}>+ Acconto</button>}
                                  <button className="dc-btn dc-btn-primary" disabled={busy === k} onClick={salvaAcconti} style={{ fontSize: 12, padding: "3px 8px" }}>Salva acconti</button>
                                  <button className="dc-btn" onClick={() => setEditAcc(null)} style={{ fontSize: 12, padding: "3px 8px" }}>Annulla</button>
                                </div>
                              </div>
                            ) : (
                              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", fontSize: 13 }}>
                                <span>{r.acconti > 0 ? `€ ${eur(r.acconti)} già registrati` : "nessun acconto"}</span>
                                <button className="dc-btn" onClick={() => setEditAcc({ k, dipendente_id: r.dipendente_id, anno: r.anno, mese: r.mese, acconti: (r.acconti_dettaglio || []).map(a => ({ importo: a.importo ?? "", data: a.data || "" })) })} style={{ fontSize: 12, padding: "3px 8px" }}>Modifica acconti</button>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {pnDett && (
        <Modal title={`Prima nota — ${pnDett.nome}`} onClose={() => setPnDett(null)} maxWidth={640}>
          <div className="dc-modal-body">
            {pnDett.loading ? <p className="dc-muted">Carico…</p> : !pnDett.righe?.length ? <p className="dc-muted" style={{ marginTop: 12 }}>Nessun dato.</p> : (
              <div style={{ overflowX: "auto", marginTop: 12 }}>
                <table className="dc-table" style={{ minWidth: 520, whiteSpace: "nowrap" }}>
                  <thead><tr><th>Periodo</th><th style={{ textAlign: "right" }}>Busta €</th><th style={{ textAlign: "right" }}>Erogato €</th><th style={{ textAlign: "right" }}>Saldo progressivo €</th></tr></thead>
                  <tbody>
                    {pnDett.righe.map((x, i) => (
                      <tr key={i}>
                        <td>{x.mese >= 1 && x.mese <= 12 ? mesi[x.mese - 1] : x.mese} {x.anno}</td>
                        <td style={{ textAlign: "right" }}>{x.busta ? eur(x.busta) : "—"}</td>
                        <td style={{ textAlign: "right" }}>{x.erogato ? eur(x.erogato) : "—"}</td>
                        <td style={{ textAlign: "right", fontWeight: 700, color: x.saldo_progressivo > 0.5 ? "#d35f4e" : x.saldo_progressivo < -0.5 ? "#7d5526" : "#3d8168" }}>{eur(x.saldo_progressivo)}</td>
                      </tr>
                    ))}
                    <tr style={{ fontWeight: 700, borderTop: "2px solid #e6e0d4" }}>
                      <td colSpan={3}>Saldo finale (positivo = ancora da pagare)</td>
                      <td style={{ textAlign: "right", color: pnDett.saldo_finale > 0.5 ? "#d35f4e" : "#3d8168" }}>{eur(pnDett.saldo_finale)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
            {pnDett.storico?.length > 0 && (
              <div style={{ marginTop: 18 }}>
                <h4 style={{ margin: "0 0 4px" }}>Storico ante-app (da Excel)</h4>
                <p className="dc-muted" style={{ fontSize: 12.5, margin: "0 0 8px" }}>Sola consultazione: registro dei pagamenti effettuati prima di questa app, per data del bonifico.</p>
                <div style={{ overflowX: "auto", maxHeight: 260, overflowY: "auto" }}>
                  <table className="dc-table" style={{ minWidth: 420, whiteSpace: "nowrap" }}>
                    <thead><tr><th>Data</th><th style={{ textAlign: "right" }}>Busta €</th><th style={{ textAlign: "right" }}>Pagato €</th></tr></thead>
                    <tbody>{pnDett.storico.map((x, i) => <tr key={i}><td>{formatDate(x.data)}</td><td style={{ textAlign: "right" }}>{x.busta ? eur(x.busta) : "—"}</td><td style={{ textAlign: "right" }}>{x.pagato ? eur(x.pagato) : "—"}</td></tr>)}</tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}

function DocumentiPage({ dipendenti, documenti, reload, getDipendente }) {
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState({
    dipendente_id: "", titolo: "", tipo: "Contratto", scadenza: ""
  });
  const [nuovoFile, setNuovoFile] = useState(null);
  const [nuovoBusy, setNuovoBusy] = useState(false);
  const massRef = useRef(null);
  const [massBusy, setMassBusy] = useState(false);
  const [massMsg, setMassMsg] = useState(null);
  const ETICHETTA = { UNILAV: "Unilav", CERTIFICAZIONE_UNICA: "Certificazione Unica (CU)", CONTRATTO: "Contratti", DIMISSIONI: "Dimissioni / cessazione", LICENZIAMENTO: "Lettere di licenziamento", RIDUZIONE_ORARIO: "Riduzione orario", BONIFICO: "Bonifici", CODICE_FISCALE: "Codice fiscale / Tessera sanitaria", CARTA_IDENTITA: "Carta d'identità", BUSTA_PAGA: "Buste paga", CERTIFICATO: "Certificati", ALTRO: "Da classificare" };
  const TIPI_NUOVO = ["Contratto", "UNILAV", "Dimissioni / cessazione", "Lettera di licenziamento", "CUD", "Certificato", "Altro"];

  const handleSubmit = async (e) => {
    e.preventDefault();
    setNuovoBusy(true);
    try {
      const fd = new FormData();
      fd.append("dipendente_id", formData.dipendente_id);
      fd.append("titolo", formData.titolo);
      fd.append("tipo", formData.tipo);
      if (formData.scadenza) fd.append("scadenza", formData.scadenza);
      if (nuovoFile) fd.append("file", nuovoFile);
      const r = await axios.post(`${API}/documenti`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      const ad = r.data?.adempimenti_dimissioni;
      if (ad?.alert) toast(`Documento salvato. Dimissioni registrate: UNILAV entro il ${formatDate(ad.scadenza_unilav)} (alert nel Pannello di controllo).`);
      else toast("Documento salvato");
      setShowModal(false); setNuovoFile(null);
      setFormData({ dipendente_id: "", titolo: "", tipo: "Contratto", scadenza: "" });
      reload();
    } catch (err) {
      toast(err?.response?.data?.detail || "Errore nel salvataggio del documento", "err");
    } finally { setNuovoBusy(false); }
  };

  const handleMassUpload = async (e) => {
    const fs = Array.from(e.target.files || []);
    if (!fs.length) return;
    setMassBusy(true); setMassMsg(null);
    try {
      const fd = new FormData();
      fs.forEach(f => fd.append("files", f));
      const r = await axios.post(`${API}/documenti/upload-massivo`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setMassMsg(r.data);
      reload();
    } catch (err) {
      setMassMsg({ errore: err?.response?.data?.detail || "Errore upload" });
    } finally {
      setMassBusy(false);
      if (massRef.current) massRef.current.value = "";
    }
  };

  const importaGmail = async () => {
    if (!window.confirm("Cercare i documenti negli allegati della posta (Gmail) e archiviarli nelle cartelle dei dipendenti?")) return;
    setMassBusy(true); setMassMsg(null);
    try {
      const r = await axios.post(`${API}/paghe/importa-email`);
      const doc = r.data.documenti || { caricati: 0, non_assegnati: 0, duplicati: 0 };
      setMassMsg({ caricati: doc.caricati, duplicati: Array(doc.duplicati || 0).fill(0), non_assegnati: Array(doc.non_assegnati || 0).fill(0), dettaglio: [], _gmail: true });
      reload();
      toast(`Da Gmail: ${doc.caricati} documenti archiviati`);
    } catch (err) {
      setMassMsg({ errore: err?.response?.data?.detail || "Errore import Gmail (controlla IMAP_HOST/USER/PASSWORD su Render)" });
    } finally { setMassBusy(false); }
  };

  const apriDoc = async (doc) => {
    try {
      const r = await axios.get(`${API}/documenti/${doc.id}/file`, { responseType: "blob" });
      window.open(URL.createObjectURL(r.data), "_blank");
    } catch { toast("Impossibile aprire il documento (file non disponibile).", "err"); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Eliminare questo documento?")) return;
    await axios.delete(`${API}/documenti/${id}`);
    reload();
  };

  // Raggruppa i documenti in cartelle per tipo (categoria)
  const cartelle = {};
  (documenti || []).forEach(d => { const k = d.categoria || d.tipo || "ALTRO"; (cartelle[k] = cartelle[k] || []).push(d); });

  return (
    <div className="dc-page">
      <div className="dc-page-header">
        <div>
          <h1>Documenti Dipendenti</h1>
          <p>Archivio documenti e certificati</p>
        </div>
        <div className="dc-page-actions">
          <input ref={massRef} type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.zip,.docx" onChange={handleMassUpload} style={{ display: "none" }} />
          <button onClick={() => massRef.current?.click()} disabled={massBusy} className="dc-btn dc-btn-primary" title="Carica più documenti: l'app riconosce il tipo e li mette nella cartella del dipendente">
            {massBusy ? "Carico…" : "📂 Carica documenti (auto)"}
          </button>
          <button onClick={importaGmail} disabled={massBusy} className="dc-btn" title="Cerca i documenti negli allegati Gmail e li archivia nelle cartelle dei dipendenti">
            {massBusy ? "Attendi…" : "📧 Importa da Gmail"}
          </button>
          <button onClick={() => setShowModal(true)} className="dc-btn">
            <Plus size={18} /> Nuovo Documento
          </button>
        </div>
      </div>

      {massMsg && (
        <div className="dc-card" style={{ marginBottom: 16, borderLeft: `4px solid ${massMsg.errore ? '#d35f4e' : '#3d8168'}` }}>
          {massMsg.errore ? <div style={{ color: "#d35f4e", fontWeight: 600 }}>⚠ {massMsg.errore}</div> : (
            <div style={{ fontSize: 14 }}>
              <div style={{ fontWeight: 700 }}>✓ Caricati {massMsg.caricati} documenti{massMsg.duplicati?.length ? ` · ${massMsg.duplicati.length} duplicati saltati` : ""}{massMsg.non_assegnati?.length ? ` · ${massMsg.non_assegnati.length} senza dipendente` : ""}</div>
              <div style={{ marginTop: 6, color: "#6b7669" }}>Per tipo: {Object.entries(massMsg.per_categoria || {}).map(([k, v]) => `${ETICHETTA[k] || k} (${v})`).join(" · ")}</div>
              {massMsg.non_assegnati?.length > 0 && (
                <div style={{ marginTop: 6, fontSize: 13, color: "#7d5526" }}>⚠ Da assegnare a mano (nessun codice fiscale/nome riconosciuto): {massMsg.non_assegnati.map(x => x.file).join(", ")}</div>
              )}
            </div>
          )}
        </div>
      )}

      {Object.keys(cartelle).length === 0 && (
        <div className="dc-card dc-muted">Nessun documento. Usa “📂 Carica documenti (auto)” per caricarne in blocco: l'app riconosce il tipo e li smista nelle cartelle dei dipendenti.</div>
      )}
      {Object.keys(cartelle).sort((a, b) => (a === "ALTRO" ? 1 : b === "ALTRO" ? -1 : a.localeCompare(b))).map(cat => (
        <div key={cat} className="dc-card" style={{ marginBottom: 12 }}>
          <h3 style={{ marginTop: 0 }}>📁 {ETICHETTA[cat] || cat} <span className="dc-muted" style={{ fontWeight: 400 }}>· {cartelle[cat].length}</span></h3>
          <div style={{ overflowX: "auto" }}>
            <table className="dc-table" style={{ minWidth: 520 }}>
              <thead><tr><th>Documento</th><th>Dipendente</th><th>Caricato</th><th></th></tr></thead>
              <tbody>
                {cartelle[cat].map(doc => {
                  const dip = getDipendente(doc.dipendente_id);
                  const nome = doc.dipendente_nome || (dip ? `${dip.cognome || ''} ${dip.nome || ''}`.trim() : null);
                  return (
                    <tr key={doc.id}>
                      <td>{doc.titolo || doc.filename}</td>
                      <td>{nome || <span className="dc-muted">⚠ non assegnato</span>}</td>
                      <td className="dc-muted">{doc.data_caricamento ? formatDate(doc.data_caricamento) : "—"}</td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        {doc.ha_file || doc.file_data || doc.hash ? <button onClick={() => apriDoc(doc)} className="dc-btn" style={{ padding: "4px 10px" }}>Apri</button> : null}
                        <button onClick={() => handleDelete(doc.id)} className="dc-btn-icon dc-btn-danger" style={{ marginLeft: 6 }} title="Elimina" aria-label={`Elimina documento ${doc.titolo || doc.filename || ""}`}><Trash2 size={16} /></button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {showModal && (
        <Modal title="Nuovo Documento" onClose={() => setShowModal(false)}>
            <form onSubmit={handleSubmit} className="dc-modal-body">
              <label className="dc-form-group">
                <span className="dc-label">Dipendente *</span>
                <select required value={formData.dipendente_id} onChange={e => setFormData({...formData, dipendente_id: e.target.value})}>
                  <option value="">Seleziona...</option>
                  {dipendenti.map(d => <option key={d.id} value={d.id}>{d.nome} {d.cognome}</option>)}
                </select>
              </label>
              <label className="dc-form-group">
                <span className="dc-label">Titolo *</span>
                <input required value={formData.titolo} onChange={e => setFormData({...formData, titolo: e.target.value})} />
              </label>
              <label className="dc-form-group">
                <span className="dc-label">Tipo</span>
                <select value={formData.tipo} onChange={e => setFormData({...formData, tipo: e.target.value})}>
                  {TIPI_NUOVO.map(t => <option key={t}>{t}</option>)}
                </select>
              </label>
              <label className="dc-form-group">
                <span className="dc-label">{formData.tipo === "Dimissioni / cessazione" ? "Data di decorrenza / scadenza" : "Scadenza"}</span>
                <input type="date" value={formData.scadenza} onChange={e => setFormData({...formData, scadenza: e.target.value})} />
              </label>
              <label className="dc-form-group">
                <span className="dc-label">File (PDF, immagine)</span>
                <input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={e => setNuovoFile((e.target.files || [])[0] || null)} />
                {formData.tipo === "Dimissioni / cessazione" && <span className="dc-muted" style={{ fontSize: 12 }}>Il modulo del Ministero (recesso rapporto di lavoro) viene letto: alert + scadenza UNILAV a 5 giorni.</span>}
              </label>
              <div className="dc-modal-footer">
                <button type="button" onClick={() => setShowModal(false)} className="dc-btn">Annulla</button>
                <button type="submit" className="dc-btn dc-btn-primary" disabled={nuovoBusy}>{nuovoBusy ? "Salvo…" : "Salva Documento"}</button>
              </div>
            </form>
        </Modal>
      )}
    </div>
  );
}

// ===== Assunzione & Contratti =====
function AssunzionePage({ dipendenti, reload }) {
  const C = "/hr/api/contracts";
  const [tipi, setTipi] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [dipId, setDipId] = useState("");
  const [tipo, setTipo] = useState("");
  const [extra, setExtra] = useState({
    indirizzo: "", luogo_nascita: "", data_nascita: "", codice_fiscale: "",
    mansione: "", livello: "", qualifica: "", stipendio_orario: "", data_inizio: "", data_fine: "",
    ore_settimanali: "40", periodo_prova: "", ferie_giorni: "26",
    tredicesima: true, quattordicesima: true, ticket_buono: false, ticket_importo: "",
  });
  const MANSIONI = ["Barista", "Banconista", "Cameriere", "Aiuto Cameriere", "Cassiere",
    "Pasticciere", "Aiuto Pasticciere", "Rosticciere", "Cuoco", "Aiuto Cuoco",
    "Lavapiatti", "Addetto alle pulizie", "Magazziniere", "Operaio"];
  const [contratti, setContratti] = useState([]);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [bulkRes, setBulkRes] = useState(null);
  const [showAssumi, setShowAssumi] = useState(false);
  const NUOVO0 = {
    nome: "", cognome: "", codice_fiscale: "", data_nascita: "", luogo_nascita: "",
    indirizzo: "", email: "", telefono: "", data_assunzione: "", contract_type: "indeterminato",
    mansione: "", qualifica: "", livello: "", stipendio_orario: "", ore_settimanali: "40",
    periodo_prova: "", ferie_giorni: "26", data_fine: "",
  };
  const [nuovo, setNuovo] = useState(NUOVO0);
  const setN = (k, v) => setNuovo(n => ({ ...n, [k]: v }));

  // --- Assistente CCNL: il livello e la paga si ricavano a vicenda ---------
  // Le tabelle stanno nel backend (services/ccnl.py) e non qui: erano gia'
  // duplicate nel frontend, e due copie di un minimo retributivo si
  // disallineano al primo rinnovo.
  const [ccnlElenco, setCcnlElenco] = useState([]);
  const [ccnlSel, setCcnlSel] = useState("turismo_pubblici_esercizi");
  const [ccnlCalc, setCcnlCalc] = useState(null);      // esito livello -> paga
  const [ccnlTarget, setCcnlTarget] = useState("");    // lordo mensile desiderato
  const [ccnlSugg, setCcnlSugg] = useState(null);      // esito paga -> livello
  const [ccnlErr, setCcnlErr] = useState("");

  const loadTemplates = () => axios.get(`${C}/templates`).then(r => setTemplates(r.data || [])).catch(() => {});
  useEffect(() => {
    axios.get(`${C}/types`).then(r => { setTipi(r.data || []); if (r.data?.[0]) setTipo(r.data[0].id); }).catch(() => {});
    axios.get(`${C}/ccnl`).then(r => {
      const l = (r.data || []).filter(c => c.tabelle_caricate);
      setCcnlElenco(l);
      if (l.length && !l.some(c => c.id === ccnlSel)) setCcnlSel(l[0].id);
    }).catch(() => {});
    loadTemplates();
  }, []);
  // Livello -> paga: compila i campi economici con i minimi del CCNL scelto.
  const applicaLivello = async (livello) => {
    setCcnlErr(""); setCcnlSugg(null);
    if (!livello) { setCcnlCalc(null); return; }
    try {
      const ore = extra.ore_settimanali || 40;
      const r = await axios.get(`${C}/ccnl/${ccnlSel}/livello/${encodeURIComponent(livello)}`,
        { params: { ore_settimanali: ore } });
      setCcnlCalc(r.data);
      set("livello", r.data.livello);
      set("stipendio_orario", String(r.data.oraria).replace(".", ","));
      if (r.data.periodo_prova) set("periodo_prova", r.data.periodo_prova);
      if (r.data.ferie_giorni) set("ferie_giorni", String(r.data.ferie_giorni));
    } catch (e) {
      setCcnlCalc(null);
      setCcnlErr(e?.response?.data?.detail || "Livello non calcolabile");
    }
  };

  // Paga -> livello: dall'importo che si vuole riconoscere, il livello coerente.
  const suggerisciLivello = async () => {
    setCcnlErr(""); setCcnlCalc(null);
    try {
      const r = await axios.post(`${C}/ccnl/suggerisci`, {
        importo_mensile: String(ccnlTarget).replace(",", "."),
        ccnl: ccnlSel,
        ore_settimanali: extra.ore_settimanali || 40,
      });
      setCcnlSugg(r.data);
    } catch (e) {
      setCcnlSugg(null);
      setCcnlErr(e?.response?.data?.detail || "Importo non valutabile");
    }
  };

  const loadContratti = (id) => { if (id) axios.get(`${C}/employee/${id}`).then(r => setContratti(r.data || [])).catch(() => setContratti([])); else setContratti([]); };
  useEffect(() => {
    loadContratti(dipId);
    // Precompila i dati anagrafici dal dipendente selezionato (così l'indirizzo
    // o la data di nascita già presenti compaiono e i campi mancanti si vedono).
    const d = dipendenti.find(x => x.id === dipId);
    if (d) setExtra(e => ({
      ...e,
      indirizzo: d.indirizzo || d.residenza || "",
      luogo_nascita: d.luogo_nascita || d.comune_nascita || d.citta_nascita || "",
      data_nascita: (d.data_nascita || "").slice(0, 10),
      codice_fiscale: d.codice_fiscale || d.cf || "",
      mansione: d.mansione || d.qualifica || "",
      qualifica: d.qualifica || d.mansione || "",
      livello: d.livello || e.livello,
      stipendio_orario: d.stipendio_orario || d.salary || e.stipendio_orario,
    }));
  }, [dipId]);

  const dispTemplate = (id) => (templates.find(t => t.id === id) || {}).available;

  const uploadTemplate = async (tid, ev) => {
    const file = ev.target.files?.[0]; if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    setBusy("tpl-" + tid);
    try { await axios.post(`${C}/template/${tid}`, fd, { headers: { "Content-Type": "multipart/form-data" } }); await loadTemplates(); setMsg("Template caricato."); }
    catch (e) { setMsg(e?.response?.data?.detail || "Errore caricamento template"); }
    setBusy(""); ev.target.value = "";
  };
  const genera = async () => {
    if (!dipId || !tipo) { setMsg("Seleziona dipendente e tipo contratto."); return; }
    if (!dispTemplate(tipo)) { setMsg("Carica prima il template di questo tipo."); return; }
    setBusy("gen"); setMsg("");
    try {
      const r = await axios.post(`${C}/generate/${dipId}`, { contract_type: tipo, additional_data: extra });
      const m = r.data?.stipendio_mensile;
      setMsg(m != null ? `Contratto generato. Lordo mensile teorico: € ${Number(m).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}.` : "Contratto generato.");
      const acc = (r.data?.accessori_mancanti || []);
      const note = m != null ? ` Lordo mensile: € ${Number(m).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}.` : "";
      const warn = acc.length ? ` ⚠ Template accessori mancanti: ${acc.join(", ")}.` : " Generati anche regolamento, privacy e informativa.";
      setMsg(`Contratto generato.${note}${warn}`);
      loadContratti(dipId);
    } catch (e) { setMsg(e?.response?.data?.detail || "Errore generazione"); }
    setBusy("");
  };
  const generaMassivo = async () => {
    if (!window.confirm("Genero i contratti (bozze) per tutti i dipendenti in forza, deducendo tipo e dati dalle buste paga? Chi ha già un contratto viene saltato. Nessun invio.")) return;
    setBusy("bulk"); setMsg(""); setBulkRes(null);
    try {
      const r = await axios.post(`${C}/genera-massivo`, {});
      setBulkRes(r.data);
      setMsg(`Generati ${r.data.generati}, saltati ${r.data.saltati}.`);
      reload && reload();
    } catch (e) { setMsg(e?.response?.data?.detail || "Errore generazione massiva"); }
    setBusy("");
  };
  const creaAssumi = async () => {
    if (!nuovo.nome || !nuovo.cognome) { setMsg("Nome e cognome sono obbligatori."); return; }
    if (!dispTemplate(nuovo.contract_type)) { setMsg("Carica prima il template di questo tipo di contratto."); return; }
    setBusy("assumi"); setMsg("");
    try {
      const dipPayload = {
        nome: nuovo.nome, cognome: nuovo.cognome, codice_fiscale: nuovo.codice_fiscale || null,
        data_nascita: nuovo.data_nascita || null, indirizzo: nuovo.indirizzo || null,
        email: nuovo.email || null, telefono: nuovo.telefono || null,
        data_assunzione: nuovo.data_assunzione || null, ruolo: nuovo.mansione || null,
        contratto: nuovo.contract_type.includes("determinato") && !nuovo.contract_type.includes("ind") ? "Determinato" : "Indeterminato",
        data_fine_contratto: nuovo.data_fine || null,
      };
      const cr = await axios.post(`${API}/dipendenti`, dipPayload);
      const newId = cr.data?.id || cr.data?.dipendente?.id || cr.data?._id;
      if (!newId) throw new Error("ID nuovo dipendente non disponibile");
      const additional = {
        indirizzo: nuovo.indirizzo, luogo_nascita: nuovo.luogo_nascita, data_nascita: nuovo.data_nascita,
        codice_fiscale: nuovo.codice_fiscale, mansione: nuovo.mansione, qualifica: nuovo.qualifica || nuovo.mansione,
        livello: nuovo.livello, stipendio_orario: nuovo.stipendio_orario, ore_settimanali: nuovo.ore_settimanali,
        periodo_prova: nuovo.periodo_prova, ferie_giorni: nuovo.ferie_giorni,
        data_inizio: nuovo.data_assunzione, data_fine: nuovo.data_fine,
      };
      const gr = await axios.post(`${C}/generate/${newId}`, { contract_type: nuovo.contract_type, additional_data: additional });
      const acc = (gr.data?.accessori_mancanti || []);
      setShowAssumi(false); setNuovo(NUOVO0);
      setMsg(`Dipendente assunto e contratto generato.${acc.length ? ` ⚠ Template accessori mancanti: ${acc.join(", ")}.` : " Con regolamento, privacy e informativa."}`);
      reload && reload();
    } catch (e) { setMsg(e?.response?.data?.detail || e.message || "Errore in fase di assunzione"); }
    setBusy("");
  };
  const scarica = async (cid, fname) => {
    try { const r = await axios.get(`${C}/download/${cid}`, { responseType: "blob" });
      const url = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = url; a.download = fname || "contratto.docx"; a.click(); URL.revokeObjectURL(url);
    } catch { setMsg("Download non disponibile"); }
  };
  const invia = async (cid) => {
    setBusy("send-" + cid); setMsg("");
    try { const r = await axios.post(`${C}/send/${cid}`, {});
      const miss = (r.data.accessori_mancanti || []);
      const avviso = miss.length ? ` ⚠ Non ancora generati per questo dipendente: ${miss.join(", ")}.` : "";
      setMsg(`Inviato a ${r.data.inviato_a}: ${(r.data.documenti || []).join(", ")}.${avviso}`); loadContratti(dipId);
    } catch (e) { setMsg(e?.response?.data?.detail || "Errore invio email"); }
    setBusy("");
  };
  const caricaFirmato = async (cid, ev) => {
    const file = ev.target.files?.[0]; if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    setBusy("cf-" + cid); setMsg("");
    try { await axios.post(`${C}/carica-firmato/${cid}`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setMsg("Contratto firmato dal dipendente caricato. Ora controfirma e invia il definitivo."); loadContratti(dipId);
    } catch (e) { setMsg(e?.response?.data?.detail || "Errore caricamento firmato"); }
    setBusy(""); ev.target.value = "";
  };
  const finalizza = async (cid, ev) => {
    const file = ev?.target?.files?.[0];
    if (!file && !window.confirm("Finalizzare usando il PDF firmato dal dipendente come definitivo (senza un file controfirmato separato)?")) return;
    const fd = new FormData(); if (file) fd.append("file", file);
    setBusy("fz-" + cid); setMsg("");
    try { const r = await axios.post(`${C}/finalizza/${cid}`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      const dest = (r.data.inviato_a || []).join(", ");
      setMsg(`Contratto definitivo archiviato nel fascicolo${dest ? ` e inviato a ${dest}` : ""}.`); loadContratti(dipId); reload && reload();
    } catch (e) { setMsg(e?.response?.data?.detail || "Errore finalizzazione"); }
    setBusy(""); if (ev?.target) ev.target.value = "";
  };
  const scaricaPdf = async (cid, versione) => {
    try { const r = await axios.get(`${C}/pdf/${cid}/${versione}`, { responseType: "blob" });
      const url = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = url; a.download = `contratto_${versione}.pdf`; a.click(); URL.revokeObjectURL(url);
    } catch { setMsg("PDF non disponibile"); }
  };
  const ITER = {
    bozza: ["Bozza", "#6b7669", "#eef1ec"],
    inviata: ["Inviata al dipendente", "#c4894a", "#fdf0dd"],
    firmato_dipendente: ["Firmata dal dipendente", "#3d8168", "#e7f6ec"],
    definitivo: ["Definitivo · in fascicolo", "#2a3329", "#dfeede"],
  };

  const dip = dipendenti.find(d => d.id === dipId);
  const num = (v) => { const n = parseFloat(String(v).replace(",", ".")); return isNaN(n) ? null : n; };
  const orario = num(extra.stipendio_orario), ore = num(extra.ore_settimanali);
  const mensile = (orario != null && ore != null) ? (orario * ore * 52 / 12) : null;
  const mensileFmt = mensile != null ? mensile.toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—";
  const set = (k, v) => setExtra(e => ({ ...e, [k]: v }));
  const grid = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 14, alignItems: "end" };
  const lbl = { display: "flex", flexDirection: "column", gap: 5, fontSize: 13, fontWeight: 600, color: "#2a3329" };
  const secTitle = { gridColumn: "1 / -1", margin: "12px 0 -2px", fontSize: 12, fontWeight: 800, color: "#5b7a6b", textTransform: "uppercase", letterSpacing: ".05em" };
  const full = { ...lbl, gridColumn: "1 / -1" };
  return (
    <div className="dc-page">
      <div className="dc-page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div><h1>Assunzione & Contratti</h1>
          <p>Carica i modelli, genera il contratto (con regolamento, privacy e informativa) e invialo</p></div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="dc-btn-primary" onClick={() => { setNuovo(NUOVO0); setShowAssumi(true); }}>+ Assumi dipendente</button>
          <button className="dc-btn" disabled={busy === "bulk"} onClick={generaMassivo}>{busy === "bulk" ? "Genero…" : "Genera per i dipendenti in forza"}</button>
        </div>
      </div>

      {msg && <div style={{ background: "#eef3ef", border: "1px solid #d9e4dc", borderRadius: 10, padding: "10px 14px", marginBottom: 14 }}>{msg}</div>}

      {bulkRes && (
        <div className="dc-card" style={{ marginBottom: 16 }}>
          <h3 style={{ marginTop: 0 }}>Generazione massiva — generati {bulkRes.generati}, saltati {bulkRes.saltati}</h3>
          {(bulkRes.dettaglio || []).length > 0 && (
            <div style={{ fontSize: 13 }}>{bulkRes.dettaglio.map((d, i) => (
              <div key={i} style={{ borderTop: "1px solid #eee", padding: "4px 0" }}>✓ <b>{d.dipendente}</b> · {d.tipo}{d.dati_da_busta ? " · dati da busta" : " · dati anagrafica"}{(d.accessori_mancanti || []).length ? ` · ⚠ accessori mancanti: ${d.accessori_mancanti.join(", ")}` : ""}</div>
            ))}</div>
          )}
          {(bulkRes.non_generati || []).length > 0 && (
            <div style={{ fontSize: 13, marginTop: 8 }}>{bulkRes.non_generati.map((d, i) => (
              <div key={i} style={{ borderTop: "1px solid #eee", padding: "4px 0", color: "#9a6b4a" }}>— {d.dipendente}: {d.motivo}</div>
            ))}</div>
          )}
        </div>
      )}

      {showAssumi && (
        <Modal title="Assumi dipendente" onClose={() => setShowAssumi(false)} maxWidth={720}>
          <div className="dc-modal-body">
            <p className="dc-muted" style={{ fontSize: 13, marginTop: 0 }}>Crea l'anagrafica e genera subito contratto + regolamento + privacy + informativa (nessun invio automatico).</p>
            <div style={grid}>
              <label style={lbl}>Nome *<input className="dc-input" value={nuovo.nome} onChange={e => setN("nome", e.target.value)} /></label>
              <label style={lbl}>Cognome *<input className="dc-input" value={nuovo.cognome} onChange={e => setN("cognome", e.target.value)} /></label>
              <label style={lbl}>Codice fiscale<input className="dc-input" value={nuovo.codice_fiscale} onChange={e => setN("codice_fiscale", e.target.value.toUpperCase())} /></label>
              <label style={lbl}>Luogo di nascita<input className="dc-input" value={nuovo.luogo_nascita} onChange={e => setN("luogo_nascita", e.target.value)} /></label>
              <label style={lbl}>Data di nascita<input type="date" className="dc-input" value={nuovo.data_nascita} onChange={e => setN("data_nascita", e.target.value)} /></label>
              <label style={full}>Indirizzo di residenza<input className="dc-input" value={nuovo.indirizzo} onChange={e => setN("indirizzo", e.target.value)} placeholder="Via/Piazza, n., CAP, Comune" /></label>
              <label style={lbl}>Email<input className="dc-input" value={nuovo.email} onChange={e => setN("email", e.target.value)} /></label>
              <label style={lbl}>Telefono<input className="dc-input" value={nuovo.telefono} onChange={e => setN("telefono", e.target.value)} /></label>

              <div style={secTitle}>Contratto</div>
              <label style={lbl}>Tipo contratto
                <select className="dc-input" value={nuovo.contract_type} onChange={e => setN("contract_type", e.target.value)}>
                  {tipi.filter(t => ["indeterminato", "determinato", "part_time_det", "part_time_ind"].includes(t.id)).map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select></label>
              <label style={lbl}>Mansione<input list="mansioni-list" className="dc-input" value={nuovo.mansione} onChange={e => setN("mansione", e.target.value)} placeholder="scegli o scrivi" /></label>
              <label style={lbl}>Qualifica<input className="dc-input" value={nuovo.qualifica} onChange={e => setN("qualifica", e.target.value)} /></label>
              <label style={lbl}>Livello CCNL<input className="dc-input" value={nuovo.livello} onChange={e => setN("livello", e.target.value)} /></label>
              <label style={lbl}>Paga oraria (€)<input className="dc-input" value={nuovo.stipendio_orario} onChange={e => setN("stipendio_orario", e.target.value)} placeholder="es. 8,50" /></label>
              <label style={lbl}>Ore settimanali<input type="number" min="1" max="48" className="dc-input" value={nuovo.ore_settimanali} onChange={e => setN("ore_settimanali", e.target.value)} /></label>
              <label style={lbl}>Periodo di prova (giorni)<input className="dc-input" value={nuovo.periodo_prova} onChange={e => setN("periodo_prova", e.target.value)} /></label>
              <label style={lbl}>Data assunzione<input type="date" className="dc-input" value={nuovo.data_assunzione} onChange={e => setN("data_assunzione", e.target.value)} /></label>
              <label style={lbl}>Data fine (se determinato)<input type="date" className="dc-input" value={nuovo.data_fine} onChange={e => setN("data_fine", e.target.value)} /></label>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 14, justifyContent: "flex-end" }}>
              <button className="dc-btn" onClick={() => setShowAssumi(false)}>Annulla</button>
              <button className="dc-btn-primary" disabled={busy === "assumi"} onClick={creaAssumi}>{busy === "assumi" ? "Assumo…" : "Crea e genera contratto"}</button>
            </div>
          </div>
        </Modal>
      )}

      <div className="dc-card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Modelli contratto (.docx)</h3>
        <p className="dc-muted" style={{ fontSize: 13 }}>Caricali una volta: restano salvati. I segnaposto (…) vengono compilati con i dati del dipendente.</p>
        <div style={{ display: "grid", gap: 8 }}>
          {tipi.map(t => (
            <div key={t.id} style={{ display: "flex", alignItems: "center", gap: 10, justifyContent: "space-between", borderTop: "1px solid #eee", paddingTop: 8 }}>
              <span>{dispTemplate(t.id) ? "✓" : "—"} {t.name}</span>
              <label className="dc-btn" style={{ cursor: "pointer", fontSize: 13 }}>
                {busy === "tpl-" + t.id ? "Carico…" : (dispTemplate(t.id) ? "Sostituisci" : "Carica")}
                <input type="file" accept=".docx" style={{ display: "none" }} onChange={(e) => uploadTemplate(t.id, e)} />
              </label>
            </div>
          ))}
        </div>
      </div>

      <div className="dc-card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Genera contratto</h3>
        <datalist id="mansioni-list">{MANSIONI.map(m => <option key={m} value={m} />)}</datalist>
        <div style={grid}>
          <label style={lbl}>Dipendente
            <select value={dipId} onChange={(e) => setDipId(e.target.value)} className="dc-input">
              <option value="">— seleziona —</option>
              {dipendenti.map(d => <option key={d.id} value={d.id}>{d.cognome} {d.nome}</option>)}
            </select></label>
          <label style={lbl}>Tipo contratto
            <select value={tipo} onChange={(e) => setTipo(e.target.value)} className="dc-input">
              {tipi.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select></label>

          <div style={secTitle}>Dati anagrafici</div>
          <label style={lbl}>Codice fiscale<input className="dc-input" value={extra.codice_fiscale} onChange={(e) => set("codice_fiscale", e.target.value.toUpperCase())} /></label>
          <label style={lbl}>Luogo di nascita<input className="dc-input" value={extra.luogo_nascita} onChange={(e) => set("luogo_nascita", e.target.value)} placeholder="Comune" /></label>
          <label style={lbl}>Data di nascita<input type="date" className="dc-input" value={extra.data_nascita} onChange={(e) => set("data_nascita", e.target.value)} /></label>
          <label style={full}>Indirizzo di residenza<input className="dc-input" value={extra.indirizzo} onChange={(e) => set("indirizzo", e.target.value)} placeholder="Via/Piazza, n. civico, CAP, Comune" /></label>

          <div style={secTitle}>Inquadramento</div>
          <div style={{ ...full, background: "#f4f1ea", border: "1px solid #e6e0d4", borderRadius: 8, padding: 12 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>
              Assistente CCNL <span className="dc-muted" style={{ fontWeight: 400, fontSize: 11 }}>
                — scegli il livello e la paga si compila, oppure scrivi quanto vuoi
                riconoscere e ti dico che livello e&apos;
              </span>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
              <label style={{ fontSize: 12, fontWeight: 600 }}>Contratto collettivo
                <select className="dc-input" value={ccnlSel}
                  onChange={(e) => { setCcnlSel(e.target.value); setCcnlCalc(null); setCcnlSugg(null); }}>
                  {ccnlElenco.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}
                </select>
              </label>
              <label style={{ fontSize: 12, fontWeight: 600 }}>Livello
                <select className="dc-input" value={extra.livello || ""}
                  onChange={(e) => applicaLivello(e.target.value)}>
                  <option value="">— scegli —</option>
                  {(ccnlElenco.find(c => c.id === ccnlSel)?.livelli || []).map(l =>
                    <option key={l} value={l}>{l}</option>)}
                </select>
              </label>
              <span className="dc-muted" style={{ fontSize: 12, paddingBottom: 8 }}>oppure</span>
              <label style={{ fontSize: 12, fontWeight: 600 }}>Lordo mensile che vuoi riconoscere (€)
                <input className="dc-input" value={ccnlTarget} placeholder="es. 1600"
                  onChange={(e) => setCcnlTarget(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); suggerisciLivello(); } }} />
              </label>
              <button type="button" className="dc-btn" onClick={suggerisciLivello}
                disabled={!ccnlTarget} style={{ marginBottom: 2 }}>Suggerisci livello</button>
            </div>

            {ccnlErr && <div style={{ marginTop: 8, fontSize: 12, color: "#d35f4e" }}>{ccnlErr}</div>}

            {ccnlCalc && (
              <div style={{ marginTop: 10, fontSize: 13 }}>
                <b>Livello {ccnlCalc.livello}</b> · {ccnlCalc.mensile_lordo.toLocaleString("it-IT",
                  { minimumFractionDigits: 2 })} €/mese ·{" "}
                {ccnlCalc.giornaliera.toLocaleString("it-IT", { minimumFractionDigits: 2 })} €/giorno ·{" "}
                {ccnlCalc.oraria.toLocaleString("it-IT", { minimumFractionDigits: 2 })} €/ora
                {ccnlCalc.part_time && <span className="dc-muted"> (part-time {ccnlCalc.percentuale_part_time}%)</span>}
                {ccnlCalc.descrizione && <div className="dc-muted" style={{ fontSize: 12, marginTop: 3 }}>{ccnlCalc.descrizione}</div>}
              </div>
            )}

            {ccnlSugg && (
              <div style={{ marginTop: 10, fontSize: 13 }}>
                {ccnlSugg.sotto_minimo ? (
                  <div style={{ color: "#d35f4e", fontWeight: 700 }}>
                    {ccnlSugg.importo_richiesto.toLocaleString("it-IT", { minimumFractionDigits: 2 })} € è sotto
                    il livello più basso del contratto ({ccnlSugg.minimo_assoluto.toLocaleString("it-IT",
                      { minimumFractionDigits: 2 })} €). Non è inquadrabile così.
                  </div>
                ) : (
                  <div>
                    Livello suggerito: <b>{ccnlSugg.livello_suggerito}</b> ·{" "}
                    {ccnlSugg.giornaliera.toLocaleString("it-IT", { minimumFractionDigits: 2 })} €/giorno ·{" "}
                    {ccnlSugg.oraria.toLocaleString("it-IT", { minimumFractionDigits: 2 })} €/ora
                    <span style={{ color: ccnlSugg.copre_il_minimo ? "#3d8168" : "#d35f4e", marginLeft: 8 }}>
                      ({ccnlSugg.scarto >= 0 ? "+" : ""}{ccnlSugg.scarto.toLocaleString("it-IT",
                        { minimumFractionDigits: 2 })} € sul tabellare)
                    </span>
                  </div>
                )}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                  {ccnlSugg.classifica.slice(0, 4).map(c => (
                    <button key={c.livello} type="button" className="dc-btn dc-btn-ghost"
                      onClick={() => applicaLivello(c.livello)}
                      title={c.descrizione || `Applica il livello ${c.livello}`}
                      style={{ fontSize: 12, padding: "3px 8px" }}>
                      {c.livello}: {c.mensile_lordo.toLocaleString("it-IT", { minimumFractionDigits: 2 })} €
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          <label style={lbl}>Mansione<input list="mansioni-list" className="dc-input" value={extra.mansione} onChange={(e) => set("mansione", e.target.value)} placeholder="scegli o scrivi" /></label>
          <label style={lbl}>Qualifica<input className="dc-input" value={extra.qualifica} onChange={(e) => set("qualifica", e.target.value)} placeholder="se diversa dalla mansione" /></label>
          <label style={lbl}>Livello CCNL<input className="dc-input" value={extra.livello} onChange={(e) => set("livello", e.target.value)} /></label>
          <label style={lbl}>Periodo di prova (giorni)
            <input className="dc-input" value={extra.periodo_prova} onChange={(e) => set("periodo_prova", e.target.value)} placeholder="per livello CCNL" />
            <span className="dc-muted" style={{ fontSize: 11, fontWeight: 400 }}>varia per livello — conferma col consulente</span>
          </label>

          <div style={secTitle}>Trattamento economico</div>
          <label style={lbl}>Paga oraria (€)<input className="dc-input" value={extra.stipendio_orario} onChange={(e) => set("stipendio_orario", e.target.value)} placeholder="es. 8,50" /></label>
          <label style={lbl}>Ore settimanali<input type="number" min="1" max="48" className="dc-input" value={extra.ore_settimanali} onChange={(e) => set("ore_settimanali", e.target.value)} /></label>
          <label style={lbl}>Lordo mensile (calcolato)<input className="dc-input" value={mensile != null ? `€ ${mensileFmt}` : ""} readOnly placeholder="oraria × ore × 52 / 12" style={{ background: "#f4f1ea" }} /></label>
          <label style={lbl}>Giorni di ferie / anno<input className="dc-input" value={extra.ferie_giorni} onChange={(e) => set("ferie_giorni", e.target.value)} placeholder="26" /></label>

          <div style={secTitle}>Decorrenza</div>
          <label style={lbl}>Data inizio<input type="date" className="dc-input" value={extra.data_inizio} onChange={(e) => set("data_inizio", e.target.value)} /></label>
          <label style={lbl}>Data fine (solo se determinato)<input type="date" className="dc-input" value={extra.data_fine} onChange={(e) => set("data_fine", e.target.value)} /></label>
        </div>

        <div style={secTitle}>Istituti contrattuali</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 18, marginTop: 8, alignItems: "center" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6, margin: 0, fontWeight: 600 }}>
            <input type="checkbox" checked={extra.tredicesima} onChange={(e) => set("tredicesima", e.target.checked)} /> 13ª (dicembre)
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6, margin: 0, fontWeight: 600 }}>
            <input type="checkbox" checked={extra.quattordicesima} onChange={(e) => set("quattordicesima", e.target.checked)} /> 14ª (luglio)
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6, margin: 0, fontWeight: 600 }}>
            <input type="checkbox" checked={extra.ticket_buono} onChange={(e) => set("ticket_buono", e.target.checked)} /> Buono pasto (dopo 1 anno)
          </label>
          {extra.ticket_buono && (
            <label style={{ display: "flex", alignItems: "center", gap: 6, margin: 0, fontWeight: 600 }}>
              Importo €/giorno
              <input className="dc-input" style={{ width: 90 }} value={extra.ticket_importo} onChange={(e) => set("ticket_importo", e.target.value)} />
            </label>
          )}
        </div>
        {dip && !dip.email && <p className="dc-muted" style={{ fontSize: 12, marginTop: 8 }}>⚠ Questo dipendente non ha email in anagrafica: non potrai inviare il contratto.</p>}
        <button onClick={genera} disabled={busy === "gen"} className="dc-btn-primary" style={{ marginTop: 12 }}>
          {busy === "gen" ? "Genero…" : "Genera contratto"}
        </button>
      </div>

      {dipId && (
        <div className="dc-card">
          <h3 style={{ marginTop: 0 }}>Contratti di {dip?.cognome} {dip?.nome}</h3>
          {contratti.length === 0 ? <p className="dc-muted">Nessun contratto generato.</p> :
            contratti.map(c => {
              const st = c.iter_stato || "bozza";
              const badge = ITER[st] || ITER.bozza;
              return (
              <div key={c.id} style={{ display: "flex", alignItems: "center", gap: 10, justifyContent: "space-between", borderTop: "1px solid #eee", padding: "8px 0", flexWrap: "wrap" }}>
                <div>
                  <b>{c.contract_name}</b>
                  <span style={{ marginLeft: 8, fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 999, color: badge[1], background: badge[2] }}>{badge[0]}</span>
                  <div className="dc-muted" style={{ fontSize: 12 }}>{c.filename}{c.inviato_a ? ` · inviato a ${c.inviato_a}` : ""}{c.stipendio_mensile != null ? ` · €/mese ${Number(c.stipendio_mensile).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : ""}</div>
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <button className="dc-btn" onClick={() => scarica(c.id, c.filename)}>Scarica bozza</button>
                  {(st === "bozza") && (
                    <button className="dc-btn-primary" disabled={busy === "send-" + c.id} onClick={() => invia(c.id)}>{busy === "send-" + c.id ? "Invio…" : "Invia bozza per firma"}</button>
                  )}
                  {st === "inviata" && (
                    <label className="dc-btn-primary" style={{ cursor: "pointer" }}>
                      {busy === "cf-" + c.id ? "Carico…" : "Carica firmato dal dipendente"}
                      <input type="file" accept=".pdf" style={{ display: "none" }} onChange={(e) => caricaFirmato(c.id, e)} />
                    </label>
                  )}
                  {st === "firmato_dipendente" && (<>
                    <button className="dc-btn" onClick={() => scaricaPdf(c.id, "firmato")}>Scarica firmato</button>
                    <label className="dc-btn-primary" style={{ cursor: "pointer" }}>
                      {busy === "fz-" + c.id ? "Finalizzo…" : "Controfirma e invia definitivo"}
                      <input type="file" accept=".pdf" style={{ display: "none" }} onChange={(e) => finalizza(c.id, e)} />
                    </label>
                  </>)}
                  {st === "definitivo" && (
                    <button className="dc-btn" onClick={() => scaricaPdf(c.id, "definitivo")}>Scarica definitivo</button>
                  )}
                  {st !== "bozza" && st !== "definitivo" && st !== "inviata" && st !== "firmato_dipendente" && (
                    <button className="dc-btn-primary" disabled={busy === "send-" + c.id} onClick={() => invia(c.id)}>{busy === "send-" + c.id ? "Invio…" : "Invia bozza per firma"}</button>
                  )}
                </div>
              </div>
              );
            })}
        </div>
      )}
    </div>
  );
}

// ===== Timbrature & Sede =====
function TimbraturePage({ dipendenti, getDipendente }) {
  const T = "/hr/api/timbrature";
  const [sede, setSede] = useState({ nome: "Ceraldi Caffè", indirizzo: "Piazza Carità, 14 — 80134 Napoli", lat: 40.842949, lng: 14.2489, raggio_m: 200, blocca_fuori_sede: true });
  const [data, setData] = useState(new Date().toISOString().slice(0, 10));
  const [timb, setTimb] = useState([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState("");
  const [sedeOk, setSedeOk] = useState(null); // true = sede salvata sul server (geofencing attivo)

  useEffect(() => { axios.get(`${T}/sede`).then(r => { const ok = !!(r.data && r.data.lat != null); setSedeOk(ok); if (ok) setSede(s => ({ ...s, ...r.data })); }).catch(() => setSedeOk(false)); }, []);
  const loadTimb = () => axios.get(`${T}?data=${data}`).then(r => setTimb(r.data.timbrature || [])).catch(() => setTimb([]));
  useEffect(() => { loadTimb(); }, [data]);

  // Turni pianificati per il giorno selezionato (stessi endpoint della pagina Presenze)
  const [tipiTurno, setTipiTurno] = useState([]);
  const [assegn, setAssegn] = useState([]);
  const NOMI_G = ["Domenica", "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato"];
  const lunISOdi = (ymd) => { const d = new Date(ymd + "T12:00:00"); const off = (d.getDay() + 6) % 7; d.setDate(d.getDate() - off); return d.toISOString().slice(0, 10); };
  const giornoNomeDi = (ymd) => NOMI_G[new Date(ymd + "T12:00:00").getDay()];
  useEffect(() => { axios.get("/hr/api/dipendenti-cloud/turni").then(r => setTipiTurno(r.data || [])).catch(() => {}); }, []);
  useEffect(() => { axios.get(`/hr/api/dipendenti-cloud/assegnazioni-turni?settimana=${lunISOdi(data)}`).then(r => setAssegn(r.data || [])).catch(() => setAssegn([])); }, [data]);
  const [riepilogo, setRiepilogo] = useState([]);
  useEffect(() => {
    const [a, m] = data.split("-");
    axios.get(`${T}/riepilogo?anno=${a}&mese=${parseInt(m)}`).then(r => setRiepilogo(r.data.riepilogo || [])).catch(() => setRiepilogo([]));
  }, [data]);
  const nomeTurno = (id) => (tipiTurno.find(t => t.id === id) || {}).nome;
  const pianificatoDi = (dipId) => {
    const a = assegn.find(x => x.dipendente_id === dipId && x.settimana === lunISOdi(data) && x.giorno === giornoNomeDi(data));
    return a ? (nomeTurno(a.turno_id) || null) : null;
  };
  const lavorativo = (n) => n && !["Riposo", "Ferie"].includes(n);

  const salvaSede = async () => {
    setBusy("sede"); setMsg("");
    try { await axios.post(`${T}/sede`, { ...sede, lat: parseFloat(sede.lat), lng: parseFloat(sede.lng), raggio_m: parseInt(sede.raggio_m) || 200 });
      setSedeOk(true); setMsg("Sede salvata."); } catch (e) { setMsg(e?.response?.data?.detail || "Errore salvataggio sede"); }
    setBusy("");
  };
  const usaPosizione = () => {
    if (!navigator.geolocation) { setMsg("Geolocalizzazione non disponibile."); return; }
    navigator.geolocation.getCurrentPosition(
      p => { setSede(s => ({ ...s, lat: p.coords.latitude.toFixed(6), lng: p.coords.longitude.toFixed(6) })); setMsg("Posizione attuale inserita: salva per confermare."); },
      () => setMsg("Impossibile ottenere la posizione."), { enableHighAccuracy: true, timeout: 10000 });
  };

  // Confronto atteso vs effettivo: unione di chi ha timbrato e di chi era
  // pianificato a lavorare quel giorno (così emergono anche le assenze).
  const perDip = (() => {
    const m = {};
    const ensure = (k, nome) => { if (!m[k]) m[k] = { dipId: k, nome: nome || "", entrata: null, uscita: null, fuori: false }; return m[k]; };
    for (const t of timb) {
      const g = ensure(t.dipendente_id, t.dipendente_nome);
      if (t.tipo === "entrata" && !g.entrata) g.entrata = t;
      if (t.tipo === "uscita") g.uscita = t;
      if (t.fuori_sede) g.fuori = true;
    }
    // aggiungi i pianificati a lavorare che non hanno (ancora) timbrato
    for (const a of assegn) {
      if (a.settimana !== lunISOdi(data) || a.giorno !== giornoNomeDi(data)) continue;
      if (!lavorativo(nomeTurno(a.turno_id))) continue;
      const d = getDipendente ? getDipendente(a.dipendente_id) : null;
      ensure(a.dipendente_id, d ? `${d.cognome || ""} ${d.nome || ""}`.trim() : a.dipendente_id);
    }
    return Object.values(m).map(g => {
      let ore = null;
      if (g.entrata && g.uscita) {
        const [h1, mi1] = g.entrata.ora.split(":").map(Number); const [h2, mi2] = g.uscita.ora.split(":").map(Number);
        ore = Math.round(((h2 * 60 + mi2) - (h1 * 60 + mi1)) / 6) / 10;
      }
      const pian = pianificatoDi(g.dipId);
      let stato = ["—", "default"];
      if (lavorativo(pian) && !g.entrata) stato = ["Assente", "danger"];
      else if (!lavorativo(pian) && g.entrata) stato = [pian ? `Extra (${pian})` : "Extra (non in turno)", "warning"];
      else if (g.entrata && g.uscita) stato = ["OK", "success"];
      else if (g.entrata) stato = ["In corso", "info"];
      // Presenza validata: entrata+uscita in sede e permanenza ≥ 1 ora
      const validata = !!(g.entrata && g.uscita && !g.fuori && ore != null && ore >= 1);
      return { ...g, ore, pian, stato, validata };
    }).sort((a, b) => (a.nome || "").localeCompare(b.nome || ""));
  })();

  const set = (k, v) => setSede(s => ({ ...s, [k]: v }));
  const lbl = { display: "flex", flexDirection: "column", gap: 5, fontSize: 13, fontWeight: 600 };

  return (
    <div className="dc-page">
      <div className="dc-page-header"><div><h1>Timbrature</h1>
        <p>Timbratura dei dipendenti dal portale (solo in sede) e confronto con i turni</p></div></div>

      {msg && <div style={{ background: "#eef3ef", border: "1px solid #d9e4dc", borderRadius: 10, padding: "10px 14px", marginBottom: 14 }}>{msg}</div>}

      {sedeOk === false && (
        <div className="dc-card" style={{ marginBottom: 14, borderLeft: "4px solid #d35f4e" }}>
          <b>⚠ Sede non impostata — controllo “fuori sede” DISATTIVO.</b> Finché non salvi la sede, le timbrature non vengono verificate (nessuna risulta “fuori sede”). Nel pannello qui sotto, <b>stando al bar</b>, premi “Usa la mia posizione attuale” e poi “Salva sede”.
        </div>
      )}

      <div className="dc-card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Sede di lavoro (geofencing)</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14, alignItems: "end" }}>
          <label style={lbl}>Nome sede<input className="dc-input" value={sede.nome || ""} onChange={e => set("nome", e.target.value)} /></label>
          <label style={{ ...lbl, gridColumn: "span 2" }}>Indirizzo<input className="dc-input" value={sede.indirizzo || ""} onChange={e => set("indirizzo", e.target.value)} /></label>
          <label style={lbl}>Latitudine<input className="dc-input" value={sede.lat ?? ""} onChange={e => set("lat", e.target.value)} /></label>
          <label style={lbl}>Longitudine<input className="dc-input" value={sede.lng ?? ""} onChange={e => set("lng", e.target.value)} /></label>
          <label style={lbl}>Raggio ammesso (m)<input type="number" className="dc-input" value={sede.raggio_m ?? 200} onChange={e => set("raggio_m", e.target.value)} /></label>
        </div>
        <div style={{ display: "flex", gap: 14, alignItems: "center", marginTop: 12, flexWrap: "wrap" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 600, margin: 0 }}>
            <input type="checkbox" checked={!!sede.blocca_fuori_sede} onChange={e => set("blocca_fuori_sede", e.target.checked)} /> Consenti la timbratura solo in sede
          </label>
          <button className="dc-btn" onClick={usaPosizione}>Usa la mia posizione attuale</button>
          <button className="dc-btn-primary" disabled={busy === "sede"} onClick={salvaSede}>{busy === "sede" ? "Salvo…" : "Salva sede"}</button>
        </div>
      </div>

      <div className="dc-card">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <h3 style={{ margin: 0 }}>Timbrature del giorno</h3>
          <input type="date" className="dc-input" style={{ width: "auto" }} value={data} onChange={e => setData(e.target.value)} />
        </div>
        {perDip.length === 0 ? <p className="dc-muted" style={{ marginTop: 12 }}>Nessuna timbratura per questa data.</p> : (
          <div style={{ overflowX: "auto", marginTop: 12, WebkitOverflowScrolling: "touch" }}>
          <table className="dc-table" style={{ minWidth: 720, whiteSpace: "nowrap" }}>
            <thead><tr><th>Dipendente</th><th>Turno pianificato</th><th>Entrata</th><th>Uscita</th><th>Ore</th><th>Sede</th><th>Validata</th><th>Esito</th></tr></thead>
            <tbody>
              {perDip.map((g, i) => (
                <tr key={i}>
                  <td>{g.nome}</td>
                  <td>{g.pian || "—"}</td>
                  <td>{g.entrata?.ora || "—"}</td>
                  <td>{g.uscita?.ora || (g.entrata ? "in corso" : "—")}</td>
                  <td>{g.ore != null ? `${g.ore} h` : "—"}</td>
                  <td>{(() => {
                    const recs = [g.entrata, g.uscita].filter(Boolean);
                    if (!recs.length) return "—";
                    if (recs.some(r => r.fuori_sede)) { const ds = recs.map(r => r.distanza_m).filter(x => x != null); return <Badge variant="danger">fuori sede{ds.length ? ` · ${Math.max(...ds)} m` : ""}</Badge>; }
                    if (recs.every(r => r.lat == null)) return <Badge variant="warning">no GPS</Badge>;
                    if (sedeOk === false) return <Badge variant="warning">n/d · sede non impostata</Badge>;
                    return <Badge variant="success">in sede</Badge>;
                  })()}</td>
                  <td>{!g.entrata ? "—" : (g.uscita ? (g.validata ? <Badge variant="success">✓ valida</Badge> : <Badge variant="warning">da verificare</Badge>) : <Badge variant="info">in corso</Badge>)}</td>
                  <td><Badge variant={g.stato[1]}>{g.stato[0]}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
        <p className="dc-muted" style={{ fontSize: 12, marginTop: 10 }}>Confronta queste presenze reali con i turni pianificati nella pagina Presenze (il calendario sovrappone già i turni).</p>
      </div>

      <div className="dc-card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>Riepilogo ore del mese ({data.slice(5, 7)}/{data.slice(0, 4)})</h3>
        {riepilogo.length === 0 ? <p className="dc-muted">Nessuna ora timbrata in questo mese.</p> : (
          <table className="dc-table">
            <thead><tr><th>Dipendente</th><th>Giorni</th><th>Ore totali</th></tr></thead>
            <tbody>
              {riepilogo.map((r, i) => (
                <tr key={i}><td>{r.nome}</td><td>{r.giorni}</td><td><b>{r.ore} h</b></td></tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="dc-muted" style={{ fontSize: 12, marginTop: 10 }}>Ore calcolate dalle timbrature (entrata→uscita). Utile per il controllo delle buste paga.</p>
      </div>
    </div>
  );
}

// ==================== CONTABILITÀ / GESTIONE PAGAMENTI ====================
// Fase 1: viste in sola lettura su fatture passive, fornitori e documenti
// fiscali (PEC). Dati recuperati dall'app esterna Gestione Pagamenti e
// importati nelle collezioni invoices / fornitori / documents_inbox.
const CONTAB = "/hr/api/contabilita";
const eurFmt = (n) => (Number(n) || 0).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
function BonificiContabPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [categoria, setCategoria] = useState("");
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const params = {};
      if (categoria) params.categoria = categoria;
      if (search) params.search = search;
      const r = await axios.get(`${CONTAB}/bonifici`, { params });
      setItems(r.data?.items || []);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, [categoria, search]);
  useEffect(() => { const t = setTimeout(load, 300); return () => clearTimeout(t); }, [load]);

  const catBadge = (c) => ({ DIPENDENTE: "info", FORNITORE: "warning", SOCIO: "default", ENTE_PUBBLICO: "danger" }[c] || "default");

  return (
    <div className="dc-page">
      <div className="dc-page-header">
        <h1>Bonifici</h1>
        <p>Movimenti bancari in uscita. {items.length} risultati.</p>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "0 0 16px" }}>
        <select className="dc-select" value={categoria} onChange={(e) => setCategoria(e.target.value)}>
          <option value="">Tutte le categorie</option>
          {["DIPENDENTE", "FORNITORE", "SOCIO", "ENTE_PUBBLICO"].map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}
        </select>
        <input className="dc-select" style={{ flex: 1, minWidth: 200 }} placeholder="Cerca beneficiario o causale…"
          value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      {loading ? <div className="dc-empty">Caricamento…</div> :
        items.length === 0 ? <div className="dc-empty">Nessun bonifico.</div> : (
          <div className="dc-card">
            <table className="dc-table dc-table--cards">
              <thead><tr><th>Data</th><th>Competenza</th><th>Beneficiario</th><th>Causale</th><th>Categoria</th><th>Importo</th><th>Stato</th></tr></thead>
              <tbody>
                {items.map((b) => (
                  <tr key={b._id}>
                    <td data-label="Data">{formatDate(b.data)}</td>
                    <td data-label="Competenza" className="dc-muted">{b.mese_competenza || "—"}</td>
                    <td data-label="Beneficiario">{b.beneficiario}</td>
                    <td data-label="Causale" className="dc-muted">{b.causale}</td>
                    <td data-label="Categoria"><Badge variant={catBadge(b.categoria)}>{(b.categoria || "").replace(/_/g, " ").toLowerCase()}</Badge></td>
                    <td data-label="Importo"><b>€ {eurFmt(b.importo)}</b></td>
                    <td data-label="Stato">{b.fattura_id ? <Badge variant="success">riconciliato</Badge> : <Badge variant="default">—</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  );
}


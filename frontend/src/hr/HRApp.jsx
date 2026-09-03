/**
 * Dipendenti in Cloud - Modulo HR completo con sidebar dedicata
 * Modulo HR di GestionaleCloud (ex AppDipendenti): sidebar dedicata, rotte /hr/:page
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
  Wallet, Receipt, Building2, Inbox, CheckCircle2, Link2, Activity, Send, KeyRound, Printer
} from "lucide-react";
import "./hr.css";

// Prefisso del modulo HR: composto e non letterale perche' la guardia
// tests/test_frontend_api_contracts.py confronta ogni URL statico con la
// route table reale, e un prefisso non e' un endpoint.
const HR_API = "/api" + "/hr";
const API = `${HR_API}/dipendenti-cloud`;

// --- Autenticazione: sessione unica del gestionale ---
// L'area gestione HR vive dentro GestionaleCloud: il token e' quello del login
// unico (auth_token, PIN + MFA). Il responsabile turni arriva dal portale con
// il proprio token (pt_token) e puo' vedere SOLO la pagina Turni.
const hrApi = axios.create({ baseURL: "", timeout: 120000 });
hrApi.interceptors.request.use((cfg) => {
  const t = localStorage.getItem("auth_token") || localStorage.getItem("pt_token");
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});
hrApi.interceptors.response.use(
  (r) => r,
  (err) => {
    const s = err?.response?.status;
    if (s === 401) {
      if (localStorage.getItem("auth_token")) {
        localStorage.removeItem("auth_token");
        if (!location.pathname.startsWith("/login")) location.replace("/login");
      } else {
        localStorage.removeItem("pt_token");
        localStorage.removeItem("pt_role");
        localStorage.removeItem("pt_name");
        if (!location.pathname.startsWith("/portale")) location.replace("/portale");
      }
    }
    return Promise.reject(err);
  }
);
// Ruolo HR corrente: chi ha la sessione del gestionale e' l'amministratore
// (il router mostra /hr solo agli admin); altrimenti vale il ruolo del portale.
const hrRole = () => (typeof window === "undefined" ? null
  : (localStorage.getItem("auth_token") ? "admin" : localStorage.getItem("pt_role")));

// Helper functions
const formatDate = (dateStr) => {
  if (!dateStr) return "-";
  const parts = dateStr.split("-");
  if (parts.length !== 3) return dateStr;
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
  const role = hrRole();
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
        hrApi.get(`${API}/dipendenti`),
        hrApi.get(`${API}/ferie`),
        hrApi.get(`${API}/turni`),
        hrApi.get(`${API}/missioni`),
        hrApi.get(`${API}/documenti`),
        hrApi.get(`${API}/dashboard/stats`),
        hrApi.get(`${API}/ordine-dipendenti`).catch(() => ({ data: { ordine: [] } })),
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
    { id: "accessi", label: "Accessi portale & PIN", icon: KeyRound, section: "DIPENDENTI" },
    { id: "presenze", label: "Presenze", icon: Calendar, section: "DIPENDENTI" },
    { id: "ferie-permessi", label: "Ferie & Permessi", icon: Calendar, section: "DIPENDENTI" },
    { id: "turni", label: "Turni", icon: Grid3X3, section: "DIPENDENTI" },
    { id: "timbrature", label: "Timbrature", icon: Clock, section: "DIPENDENTI" },
    { id: "buste-paga", label: "Buste Paga", icon: Euro, section: "DIPENDENTI" },
    { id: "paghe-bonifici", label: "Cedolini & Bonifici", icon: Link2, section: "DIPENDENTI" },
    { id: "bonifici-da-associare", label: "Bonifici da associare", icon: Inbox, section: "DIPENDENTI" },
    { id: "tfr", label: "TFR", icon: Wallet, section: "DIPENDENTI" },
    { id: "documenti", label: "Documenti", icon: FolderOpen, section: "DIPENDENTI" },
    { id: "assunzione", label: "Assunzione & Contratti", icon: Briefcase, section: "DIPENDENTI" },
  ];

  const pageLabels = {
    dashboard: "Pannello di controllo",
    diagnostica: "Diagnostica",
    anagrafica: "Anagrafica",
    accessi: "Accessi portale & PIN",
    presenze: "Presenze",
    "ferie-permessi": "Ferie & Permessi",
    turni: "Turni",
    timbrature: "Timbrature",
    "buste-paga": "Buste Paga",
    "paghe-bonifici": "Cedolini & Bonifici",
    "bonifici-da-associare": "Bonifici da associare",
    tfr: "TFR",
    missioni: "Missioni",
    documenti: "Documenti",
    assunzione: "Assunzione & Contratti",
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
        return <AnagraficaPage dipendenti={dipendenti} reload={loadData} />;
      case "accessi":
        return <AccessiPage />;
      case "presenze":
        return <PresenzePage dipendenti={activeDipendenti} reload={loadData} />;
      case "ferie-permessi":
        return <FeriePage dipendenti={activeDipendenti} ferie={ferie} reload={loadData} getDipendente={getDipendente} />;
      case "turni":
        return <TurniPage dipendenti={activeDipendenti} turni={turni} reload={loadData} />;
      case "timbrature":
        return <TimbraturePage dipendenti={dipendenti} getDipendente={getDipendente} />;
      case "buste-paga":
        return <BustePagaPage dipendenti={activeDipendenti} reload={loadData} getDipendente={getDipendente} />;
      case "paghe-bonifici":
        return <PagheBonificiPage />;
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
                  to={`/hr/${item.id}`}
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
    { pagina: "Buste Paga", url: `${API}/paghe?anno=${Y}&mese=${M}` },
    { pagina: "Cedolini & Bonifici", url: `${API}/paghe/associazioni-bonifici?anno=${Y}` },
    { pagina: "Documenti", url: `${API}/documenti` },
    { pagina: "Missioni", url: `${API}/missioni` },
    { pagina: "Avvisi & Scadenze", url: `${API}/alerts` },
    { pagina: "Buste in attesa", url: `${API}/paghe/in-attesa` },
  ];

  const run = async () => {
    setLoading(true); setErroreBE(null);
    // 1) Diagnostica backend
    try {
      const r = await hrApi.get(`/api/hr/diagnostica`);
      setChecks(r.data.checks || []);
      setRiepilogo(r.data.riepilogo || null);
    } catch (e) {
      setErroreBE(e?.response?.data?.message || e.message || "Diagnostica backend non raggiungibile");
      setChecks([]); setRiepilogo(null);
    }
    // 2) Ping pagine (in parallelo)
    const res = await Promise.all(PAGINE.map(async p => {
      const t0 = performance.now();
      try {
        await hrApi.get(p.url);
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
    <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 22, height: 22, borderRadius: "50%", background: COL[stato] || "#9ca3af", color: "#fff", fontWeight: 800, fontSize: 13, flexShrink: 0 }}>{ICON[stato] || "?"}</span>
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
  const loadAlerts = () => hrApi.get(`${API}/alerts`).then(r => setAlerts(r.data.alerts || [])).catch(() => {});
  useEffect(() => { loadAlerts(); hrApi.get(`${API}/paghe/in-attesa`).then(r => setPendenze(r.data)).catch(() => {}); }, []);
  const mesiIt = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];
  const risolviAlert = async (id) => {
    try { await hrApi.post(`${API}/alerts/${id}/risolvi`); loadAlerts(); } catch {}
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
            <span className="dc-stat-label">BUSTE DA PAGARE</span>
            <span className="dc-stat-value">{stats.buste_in_attesa ?? 0}</span>
            <span className="dc-stat-sub">€ {(stats.importo_in_attesa || 0).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} da erogare</span>
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

      {pendenze && pendenze.totale > 0 && (
        <div className="dc-card" style={{ marginBottom: 16, borderLeft: "4px solid #d35f4e" }}>
          <h3><FileText size={18} /> Buste in attesa di pagamento <span className="dc-muted" style={{ fontWeight: 400 }}>· {pendenze.totale} · € {(pendenze.importo || 0).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span></h3>
          <div style={{ overflowX: "auto" }}>
            <table className="dc-table" style={{ minWidth: 480 }}>
              <thead><tr><th>Dipendente</th><th>Periodo</th><th style={{ textAlign: "right" }}>Busta €</th><th style={{ textAlign: "right" }}>Manca €</th><th>Stato</th></tr></thead>
              <tbody>
                {pendenze.righe.slice(0, 30).map((x, i) => (
                  <tr key={i}>
                    <td>{x.dipendente}</td>
                    <td>{mesiIt[(x.mese || 1) - 1]} {x.anno}</td>
                    <td style={{ textAlign: "right" }}>{x.busta ? x.busta.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—"}</td>
                    <td style={{ textAlign: "right", color: "#d35f4e", fontWeight: 700 }}>{x.saldo.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td><Badge variant={x.stato === "parziale" ? "warning" : "danger"}>{x.stato === "parziale" ? "parziale" : "in attesa"}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="dc-muted" style={{ fontSize: 12, marginTop: 8 }}>Aggancio automatico: appena arriva il bonifico (PDF/Excel/CSV) la riga sparisce. Dettaglio in Buste Paga.</p>
        </div>
      )}

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

// Anagrafica Page
/* ---------------- ACCESSI PORTALE & PIN ----------------
   PIN unificato: l'amministratore entra dal login del gestionale; ogni
   dipendente ha un PIN personale per il portale. Il PIN viene generato qui
   (casuale, 6 cifre), mostrato UNA sola volta e salvato solo come hash. */
function AccessiPage() {
  const [accessi, setAccessi] = useState([]);
  const [generati, setGenerati] = useState([]);   // PIN appena creati: visibili solo ora
  const [busy, setBusy] = useState("");
  const load = useCallback(() => hrApi.get("/api/hr/accessi").then(r => setAccessi(r.data || [])).catch(() => setAccessi([])), []);
  useEffect(() => { load(); }, [load]);

  const genera = async (d) => {
    if (d.pin_impostato && !window.confirm(`Rigenerare il PIN di ${d.nome_completo}? Quello attuale smette di funzionare.`)) return;
    setBusy(d.id);
    try {
      const r = await hrApi.post(`/api/hr/accessi/${d.id}/pin/genera`);
      setGenerati(g => [{ id: d.id, nome_completo: d.nome_completo, pin: r.data.pin }, ...g.filter(x => x.id !== d.id)]);
      toast(`PIN generato per ${d.nome_completo}`);
      load();
    } catch (e) { toast(e?.response?.data?.message || "Errore nella generazione del PIN", "err"); }
    finally { setBusy(""); }
  };
  const generaMancanti = async () => {
    if (!window.confirm("Generare un PIN a tutti i dipendenti attivi che non ne hanno uno?")) return;
    setBusy("tutti");
    try {
      const r = await hrApi.post("/api/hr/accessi/genera-mancanti");
      setGenerati(g => [...(r.data.generati || []), ...g.filter(x => !(r.data.generati || []).some(n => n.id === x.id))]);
      toast(`${r.data.totale} PIN generati`);
      load();
    } catch (e) { toast(e?.response?.data?.message || "Errore nella generazione dei PIN", "err"); }
    finally { setBusy(""); }
  };
  const rimuovi = async (d) => {
    if (!window.confirm(`Togliere il PIN a ${d.nome_completo}? Non potrà più entrare nel portale.`)) return;
    try { await hrApi.delete(`/api/hr/accessi/${d.id}/pin`); setGenerati(g => g.filter(x => x.id !== d.id)); toast("PIN rimosso"); load(); }
    catch { toast("Errore nella rimozione del PIN", "err"); }
  };
  const salvaRuolo = async (d, ruolo_app) => {
    try { await hrApi.post(`/api/hr/accessi/${d.id}/ruolo`, { ruolo_app }); toast("Ruolo aggiornato"); load(); }
    catch (e) { toast(e?.response?.data?.message || "Errore nel salvataggio del ruolo", "err"); }
  };
  const stampa = () => window.print();
  const attivi = accessi.filter(a => a.attivo !== false);
  const senzaPin = attivi.filter(a => !a.pin_impostato).length;

  return (
    <div className="dc-page">
      <div className="dc-page-header">
        <h1 className="dc-page-title">Accessi portale & PIN</h1>
        <p className="dc-page-subtitle">L'amministratore entra dal login del gestionale (PIN unico). Ogni dipendente entra nel portale toccando il proprio nome e digitando il suo PIN personale.</p>
      </div>
      {generati.length > 0 && (
        <div className="dc-card" style={{ borderLeft: "4px solid #c4894a" }}>
          <div className="dc-card-header">
            <h3 className="dc-card-title">PIN appena generati — consegnali adesso</h3>
            <div className="dc-table-actions">
              <button className="dc-btn" onClick={stampa}><Printer size={14} /> Stampa</button>
              <button className="dc-btn" onClick={() => setGenerati([])}><X size={14} /> Ho consegnato tutto</button>
            </div>
          </div>
          <p className="dc-muted" style={{ marginTop: 0 }}>Questi PIN non vengono salvati in chiaro: chiusa questa pagina non si possono più rileggere, si può solo generarne di nuovi.</p>
          <table className="dc-table">
            <thead><tr><th>Dipendente</th><th>PIN</th></tr></thead>
            <tbody>{generati.map(g => (
              <tr key={g.id}><td>{g.nome_completo}</td><td style={{ fontFamily: "monospace", fontSize: 18, fontWeight: 700, letterSpacing: 3 }}>{g.pin}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
      <div className="dc-card">
        <div className="dc-card-header">
          <h3 className="dc-card-title">Dipendenti attivi ({attivi.length}) · senza PIN: {senzaPin}</h3>
          <div className="dc-table-actions">
            <button className="dc-btn dc-btn-primary" disabled={busy === "tutti" || senzaPin === 0} onClick={generaMancanti}>
              <KeyRound size={14} /> Genera PIN a chi non ce l'ha
            </button>
          </div>
        </div>
        {attivi.length === 0 ? <div className="dc-empty">Nessun dipendente attivo in anagrafica.</div> : (
          <table className="dc-table dc-table--cards">
            <thead><tr><th>Dipendente</th><th>Mansione</th><th>Ruolo portale</th><th>PIN</th><th></th></tr></thead>
            <tbody>{attivi.map(d => (
              <tr key={d.id}>
                <td className="dc-table-name">{d.nome_completo}</td>
                <td>{d.mansione || "—"}</td>
                <td>
                  <select className="dc-select" value={d.ruolo_app === "responsabile_turni" ? "responsabile_turni" : "dipendente"} onChange={e => salvaRuolo(d, e.target.value)}>
                    <option value="dipendente">dipendente</option>
                    <option value="responsabile_turni">responsabile turni</option>
                  </select>
                </td>
                <td>{d.pin_impostato ? <Badge variant="success">PIN attivo</Badge> : <Badge variant="warning">nessun PIN</Badge>}</td>
                <td className="dc-table-actions">
                  <button className="dc-btn" disabled={busy === d.id} onClick={() => genera(d)}><KeyRound size={14} /> {d.pin_impostato ? "Rigenera" : "Genera PIN"}</button>
                  {d.pin_impostato && <button className="dc-btn-icon" title="Rimuovi PIN" onClick={() => rimuovi(d)}><Trash2 size={14} /></button>}
                </td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function AnagraficaPage({ dipendenti, reload }) {
  const [showModal, setShowModal] = useState(false);
  const [editingDip, setEditingDip] = useState(null);
  const [formData, setFormData] = useState({
    nome: "", cognome: "", ruolo: "", email: "", telefono: "",
    codice_fiscale: "", contratto: "Indeterminato", iban: "", stato: "attivo"
  });
  // Default "attivi": i cessati restano cercabili dal filtro ma non
  // affollano la vista di apertura, che e' quella che si guarda ogni giorno.
  const [filter, setFilter] = useState("attivi");
  const anagRef = useRef(null);
  const [anagBusy, setAnagBusy] = useState(false);
  const handleImportAnagrafica = async (e) => {
    const fl = (e.target.files || [])[0];
    if (!fl) return;
    setAnagBusy(true);
    try {
      const fd = new FormData(); fd.append("file", fl);
      const r = await hrApi.post(`${API}/dipendenti/importa-anagrafica`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast(`Anagrafica importata: ${r.data.creati} creati, ${r.data.aggiornati} aggiornati.`);
      reload && reload();
    } catch (err) { toast(err?.response?.data?.message || "Errore import anagrafica", "err"); }
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
    await hrApi.post(`${API}/riduzioni-orario`, { voci: ridRows.map(r => ({ dipendente_id: r.dipendente_id, attiva: r.attiva, ore_giorno: r.ore_giorno, paga_oraria: r.paga_oraria, data_inizio: r.data_inizio || null, data_fine: r.data_fine || null })) });
    // Per chi viene ATTIVATO ora: genera il contratto di solidarietà → entra nell'iter firma
    const daGenerare = ridRows.filter(r => r.attiva && !r.era_attiva);
    let generati = 0; const falliti = [];
    for (const r of daGenerare) {
      try {
        await hrApi.post(`/api/hr/contracts/generate/${r.dipendente_id}`, { contract_type: "riduzione_orario",
          additional_data: { ore_giorno: r.ore_giorno, stipendio_orario: r.paga_oraria, ore_settimanali: r.ore_giorno ? String(Number(r.ore_giorno) * 6) : "", data_inizio: r.data_inizio, data_fine: r.data_fine } });
        generati++;
      } catch (e) { falliti.push(r.nome + (e?.response?.status === 400 ? " (manca il modello)" : "")); }
    }
    setShowRid(false); reload && reload();
    if (daGenerare.length) {
      alert(`Riduzione salvata.\nContratti di solidarietà generati: ${generati}` +
        (falliti.length ? `\nNon generati: ${falliti.join(", ")}\n→ carica il modello "Accordo Riduzione Orario" in Assunzione → Modelli.` : `\nLi trovi in Assunzione & Contratti per firma/invio e archiviazione nel fascicolo.`));
    }
  };
  const oggiISO = new Date().toISOString().slice(0, 10);

  const filteredDipendenti = dipendenti.filter(d => {
    if (filter === "attivi") return d.stato === "attivo";
    if (filter === "inattivi") return d.stato !== "attivo";
    return true;
  });

  const openModal = (dip = null) => {
    if (dip) {
      setEditingDip(dip);
      setFormData({ ...dip });
    } else {
      setEditingDip(null);
      setFormData({
        nome: "", cognome: "", ruolo: "", email: "", telefono: "",
        codice_fiscale: "", contratto: "Indeterminato", iban: "", stato: "attivo"
      });
    }
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      if (editingDip) {
        await hrApi.put(`${API}/dipendenti/${editingDip.id}`, formData);
      } else {
        await hrApi.post(`${API}/dipendenti`, formData);
      }
      setShowModal(false);
      reload();
      toast("Dipendente salvato");
    } catch (error) {
      console.error("Error saving:", error);
      toast("Errore nel salvataggio", "err");
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Eliminare questo dipendente?")) return;
    await hrApi.delete(`${API}/dipendenti/${id}`);
    reload();
  };

  const handleCessa = async (dip) => {
    const nome = `${dip.cognome || ""} ${dip.nome || ""}`.trim();
    const data = window.prompt(`Cessare il rapporto con ${nome}?\nData cessazione (AAAA-MM-GG):`, new Date().toISOString().slice(0, 10));
    if (!data) return;
    try {
      const r = await hrApi.post(`${API}/dipendenti/${dip.id}/cessa`, { data_cessazione: data });
      const az = (r.data.automazioni || []).map(a => a.handler || a.error).filter(Boolean);
      window.alert(`Rapporto cessato.\nAutomazioni eseguite: ${az.length ? az.join(", ") : "nessuna"}.`);
      reload();
    } catch (e) { window.alert(e?.response?.data?.message || "Errore cessazione"); }
  };

  const attivi = dipendenti.filter(d => d.stato === "attivo").length;

  return (
    <div className="dc-page">
      <div className="dc-page-header">
        <div>
          <h1>Anagrafica Dipendenti</h1>
          <p>{dipendenti.length} dipendenti totali, {attivi} attivi</p>
        </div>
        <div className="dc-page-actions">
          <select value={filter} onChange={(e) => setFilter(e.target.value)} className="dc-select">
            <option value="tutti">Tutti ({dipendenti.length})</option>
            <option value="attivi">Attivi ({attivi})</option>
            <option value="inattivi">Inattivi ({dipendenti.length - attivi})</option>
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
                      <span className="dc-table-name">{dip.nome} {dip.cognome}</span>
                      <span className="dc-table-email">{dip.email || "No email"}</span>
                    </div>
                  </div>
                </td>
                <td data-label="Ruolo">{dip.ruolo || "-"}</td>
                <td data-label="Contratto">{dip.contratto}</td>
                <td data-label="Stato"><Badge variant={dip.stato === "attivo" ? "success" : "default"}>{dip.stato}</Badge></td>
                <td data-label="Azioni" className="dc-table-actions">
                  <button onClick={() => openModal(dip)} className="dc-btn-icon"><Edit2 size={16} /></button>
                  {dip.stato === "attivo" && <button onClick={() => handleCessa(dip)} className="dc-btn-icon" title="Cessa rapporto"><LogOut size={16} /></button>}
                  <button onClick={() => handleDelete(dip.id)} className="dc-btn-icon dc-btn-danger"><Trash2 size={16} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Modal */}
      {showModal && (
        <div className="dc-modal-overlay" onClick={() => setShowModal(false)}>
          <div className="dc-modal" onClick={e => e.stopPropagation()}>
            <div className="dc-modal-header">
              <h3>{editingDip ? "Modifica Dipendente" : "Nuovo Dipendente"}</h3>
              <button onClick={() => setShowModal(false)} className="dc-modal-close"><X size={20} /></button>
            </div>
            <form onSubmit={handleSubmit} className="dc-modal-body">
              <div className="dc-form-grid">
                <div className="dc-form-group">
                  <label>Nome *</label>
                  <input required value={formData.nome} onChange={(e) => setFormData({...formData, nome: e.target.value})} />
                </div>
                <div className="dc-form-group">
                  <label>Cognome *</label>
                  <input required value={formData.cognome} onChange={(e) => setFormData({...formData, cognome: e.target.value})} />
                </div>
                <div className="dc-form-group">
                  <label>Email</label>
                  <input type="email" value={formData.email} onChange={(e) => setFormData({...formData, email: e.target.value})} />
                </div>
                <div className="dc-form-group">
                  <label>Telefono</label>
                  <input value={formData.telefono} onChange={(e) => setFormData({...formData, telefono: e.target.value})} />
                </div>
                <div className="dc-form-group">
                  <label>Ruolo</label>
                  <input value={formData.ruolo} onChange={(e) => setFormData({...formData, ruolo: e.target.value})} />
                </div>
                <div className="dc-form-group">
                  <label>Codice Fiscale</label>
                  <input value={formData.codice_fiscale} onChange={(e) => setFormData({...formData, codice_fiscale: e.target.value.toUpperCase()})} />
                </div>
                <div className="dc-form-group">
                  <label>Contratto</label>
                  <select value={formData.contratto} onChange={(e) => setFormData({...formData, contratto: e.target.value})}>
                    <option>Indeterminato</option>
                    <option>Determinato</option>
                    <option>Part-time</option>
                    <option>Apprendistato</option>
                  </select>
                </div>
                <div className="dc-form-group">
                  <label>Stato</label>
                  <select value={formData.stato} onChange={(e) => setFormData({...formData, stato: e.target.value})}>
                    <option value="attivo">Attivo</option>
                    <option value="inattivo">Inattivo</option>
                  </select>
                </div>
              </div>
              <div className="dc-modal-footer">
                <button type="button" onClick={() => setShowModal(false)} className="dc-btn">Annulla</button>
                <button type="submit" className="dc-btn dc-btn-primary">{editingDip ? "Salva" : "Crea"}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showRid && (
        <div onClick={() => setShowRid(false)} style={{ position: "fixed", inset: 0, background: "rgba(42,51,41,.45)", display: "flex", alignItems: "flex-start", justifyContent: "center", padding: 20, zIndex: 50, overflow: "auto" }}>
          <div onClick={e => e.stopPropagation()} className="dc-card" style={{ maxWidth: 880, width: "100%", marginTop: 20 }}>
            <h3 style={{ marginTop: 0 }}>⏱️ Riduzione oraria collettiva</h3>
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
                        <td style={{ textAlign: "center" }}><input type="checkbox" checked={r.attiva} onChange={e => setRidRow(i, "attiva", e.target.checked)} /></td>
                        <td><input className="dc-input" style={{ width: 70 }} type="number" min="0" max="24" step="0.5" value={r.ore_giorno} onChange={e => setRidRow(i, "ore_giorno", e.target.value)} /></td>
                        <td><input className="dc-input" style={{ width: 84 }} type="number" min="0" step="0.01" value={r.paga_oraria} onChange={e => setRidRow(i, "paga_oraria", e.target.value)} /></td>
                        <td><input className="dc-input" type="date" value={r.data_inizio} onChange={e => setRidRow(i, "data_inizio", e.target.value)} /></td>
                        <td><input className="dc-input" type="date" value={r.data_fine} onChange={e => setRidRow(i, "data_fine", e.target.value)} /></td>
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
        </div>
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
      const res = await hrApi.get(`${API}/presenze?anno=${anno}&mese=${mese}`);
      setPresenze(res.data || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { loadPresenze(); }, [anno, mese]);

  // Carica ferie, tipi turno e i turni delle settimane che toccano il mese (per derivare le presenze)
  useEffect(() => {
    hrApi.get(`${API}/ferie`).then(r => setFerieList(r.data || [])).catch(() => {});
    hrApi.get(`${API}/turni`).then(r => setTipiTurno(r.data || [])).catch(() => {});
    const isoD = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const lunSet = new Set();
    for (let g = 1; g <= daysInMonth; g++) {
      const dt = new Date(anno, mese - 1, g); const off = (dt.getDay() + 6) % 7;
      const lun = new Date(dt); lun.setDate(dt.getDate() - off); lunSet.add(isoD(lun));
    }
    Promise.all([...lunSet].map(s => hrApi.get(`${API}/assegnazioni-turni?settimana=${s}`).then(r => r.data || []).catch(() => [])))
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
    try { await hrApi.post(`${API}/presenze/batch`, batch); await loadPresenze(); } catch (e) { console.error(e); }
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
    await hrApi.post(`${API}/presenze/batch`, batch);
    loadPresenze();
  };

  const consolidaDaTurni = async () => {
    if (!window.confirm(`Consolidare le presenze di ${mesi[mese - 1]} ${anno} dai turni assegnati?\nVengono creati solo i giorni fino a oggi e non si tocca ciò che hai inserito a mano.`)) return;
    try {
      const r = await hrApi.post(`${API}/presenze/consolida-da-turni`, { anno, mese });
      await loadPresenze();
      toast(`Consolidate ${r.data.creati} presenze dai turni (${r.data.saltati} già presenti)`);
    } catch (e) { toast(e?.response?.data?.message || "Errore consolidamento", "err"); }
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
    try { await hrApi.post(`${API}/presenze/batch`, batch); await loadPresenze(); toast(`Applicato "${penna}" a ${cells.length} ${cells.length === 1 ? 'casella' : 'caselle'}`); }
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
      const r = await hrApi.post(`${API}/presenze/pdf`, { anno, mese, ...buildRighe() }, { responseType: "blob" });
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
      const r = await hrApi.post(`${API}/presenze/pdf-riepilogo`, { anno, mese, ...buildRighe() }, { responseType: "blob" });
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
      const r = await hrApi.post(`${API}/presenze/riepilogo-dati`, { anno, mese, ...buildRighe() });
      setPreviewC(r.data);
    } catch (e) { toast("Errore nel calcolo del riepilogo", "err"); }
    finally { setPreviewCBusy(false); }
  };
  const COLST = { P: "#3d8168", AS: "#d35f4e", F: "#5b7a6b", PE: "#7d5526", M: "#f59e0b", R: "#8a9a5b", RS: "#9ca3af", CH: "#6b7280", FNL: "#a6724a", X: "#374151" };
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
    try { const r = await hrApi.get(`${API}/presenze/email-commercialista`); setEmailCommercialista(r.data.email || ""); }
    catch { setEmailCommercialista(""); }
  };
  useEffect(() => { caricaEmailCommercialista(); }, []);
  const cambiaEmailCommercialista = async () => {
    const email = window.prompt("Email del commercialista (usata per tutti i prossimi invii):", emailCommercialista || "");
    if (email === null) return;
    try {
      await hrApi.post(`${API}/presenze/email-commercialista`, { email: email.trim() || null });
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
      const r = await hrApi.post(`${API}/presenze/invia-commercialista`, { anno, mese, ...buildRighe() });
      toast(`Presenze inviate a ${r.data.destinatario}`);
      loadInvii();
    } catch (e) { toast(e?.response?.data?.message || "Invio non riuscito (SMTP da configurare su Render)", "err"); }
  };
  const loadInvii = async () => {
    try { const r = await hrApi.get(`${API}/presenze/invii?anno=${anno}&mese=${mese}`); setInvii(r.data.invii || []); } catch { setInvii([]); }
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
    
    await hrApi.post(`${API}/presenze/batch`, batch);
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
    { code: "CH", label: "Chiuso", color: "#6b7280" },
    { code: "RS", label: "Riposo Sett.", color: "#9ca3af" },
    { code: "X", label: "Cessato", color: "#374151" },
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
          <button onClick={prevMonth} className="dc-btn-icon"><ChevronLeft size={20} /></button>
          <span className="dc-month-label">{mesi[mese - 1]} {anno}</span>
          <button onClick={nextMonth} className="dc-btn-icon"><ChevronRight size={20} /></button>
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
              style={{ border: penna === t.code ? "3px solid #5b7a6b" : "1px solid #e5e7eb", background: penna === t.code ? t.color : "#fff", color: penna === t.code ? "#fff" : "#374151", borderRadius: 8, padding: "6px 10px", fontWeight: 700, cursor: "pointer", fontSize: 13 }}>
              {t.code} <span style={{ fontWeight: 400, fontSize: 11 }}>{t.label}</span>
            </button>
          ))}
          <label style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, fontSize: 13, cursor: "pointer" }}>
            <input type="checkbox" checked={tuttiMode} onChange={e => setTuttiMode(e.target.checked)} />
            Applica a tutti i dipendenti
          </label>
        </div>
        <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 8 }}>
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
                      {code ? (
                        <span className="dc-presenza-badge" style={{ backgroundColor: tipo?.color || '#10b981', opacity: dimmed ? 0.12 : (salvata ? 1 : 0.55) }}>
                          {code}
                          {nota ? <span title={nota} style={{ position: "absolute", top: 1, right: 2, width: 6, height: 6, borderRadius: "50%", background: "#b91c1c", border: "1px solid #fff" }} /> : null}
                        </span>
                      ) : (
                        <span className="dc-presenza-empty">-</span>
                      )}
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
          <p style={{ color: "#94a3b8", margin: 0, fontSize: 14 }}>Nessuna malattia registrata in questo mese.</p>
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
          <p style={{ color: "#94a3b8", margin: 0, fontSize: 14 }}>Ancora nessun invio per questo mese.</p>
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
    await hrApi.post(`${API}/ferie-giorno`, { dipendente_id: dipId, data: dateStr, tipo: next });
    reload();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    await hrApi.post(`${API}/ferie`, formData);
    setShowModal(false);
    reload();
  };

  const handleApprova = async (id) => {
    await hrApi.put(`${API}/ferie/${id}/approva`);
    reload();
  };

  const handleRifiuta = async (id) => {
    await hrApi.put(`${API}/ferie/${id}/rifiuta`);
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
          <button onClick={() => setMese(new Date(mese.getFullYear(), mese.getMonth() - 1, 1))} className="dc-btn">‹</button>
          <strong style={{ textTransform: "capitalize", minWidth: 150, textAlign: "center" }}>{meseLabel}</strong>
          <button onClick={() => setMese(new Date(mese.getFullYear(), mese.getMonth() + 1, 1))} className="dc-btn">›</button>
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
                return <th key={d} style={{ padding: "4px 3px", textAlign: "center", background: we ? "#f1f5f9" : undefined, color: we ? "#94a3b8" : undefined }}>{d}</th>;
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
                    <td key={d} onClick={() => ciclaCella(dip.id, dateStr)} title={att ? att.tipo : ""}
                      style={{ cursor: "pointer", textAlign: "center", padding: "5px 3px", border: "1px solid #f1f5f9",
                        background: meta ? meta.color : "transparent", color: meta ? "#fff" : "#cbd5e1", fontWeight: 600 }}>
                      {meta ? meta.code : "·"}
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
                        <button onClick={() => handleApprova(f.id)} className="dc-btn-icon dc-btn-success"><Check size={16} /></button>
                        <button onClick={() => handleRifiuta(f.id)} className="dc-btn-icon dc-btn-danger"><X size={16} /></button>
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
        <div className="dc-modal-overlay" onClick={() => setShowModal(false)}>
          <div className="dc-modal" onClick={e => e.stopPropagation()}>
            <div className="dc-modal-header">
              <h3>Nuova Richiesta Ferie/Permesso</h3>
              <button onClick={() => setShowModal(false)} className="dc-modal-close"><X size={20} /></button>
            </div>
            <form onSubmit={handleSubmit} className="dc-modal-body">
              <div className="dc-form-group">
                <label>Dipendente *</label>
                <select required value={formData.dipendente_id} onChange={e => setFormData({...formData, dipendente_id: e.target.value})}>
                  <option value="">Seleziona...</option>
                  {dipendenti.map(d => <option key={d.id} value={d.id}>{d.nome} {d.cognome}</option>)}
                </select>
              </div>
              <div className="dc-form-group">
                <label>Tipo</label>
                <select value={formData.tipo} onChange={e => setFormData({...formData, tipo: e.target.value})}>
                  <option>Ferie</option>
                  <option>Permesso</option>
                  <option>ROL</option>
                  <option>Malattia</option>
                </select>
              </div>
              <div className="dc-form-row">
                <div className="dc-form-group">
                  <label>Data Inizio</label>
                  <input type="date" required value={formData.data_inizio} onChange={e => setFormData({...formData, data_inizio: e.target.value})} />
                </div>
                <div className="dc-form-group">
                  <label>Data Fine</label>
                  <input type="date" required value={formData.data_fine} onChange={e => setFormData({...formData, data_fine: e.target.value})} />
                </div>
              </div>
              <div className="dc-form-group">
                <label>Giorni</label>
                <input type="number" min="1" value={formData.giorni} onChange={e => setFormData({...formData, giorni: +e.target.value})} />
              </div>
              <div className="dc-modal-footer">
                <button type="button" onClick={() => setShowModal(false)} className="dc-btn">Annulla</button>
                <button type="submit" className="dc-btn dc-btn-primary">Crea Richiesta</button>
              </div>
            </form>
          </div>
        </div>
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
  const caricaSettimana = (s) => hrApi.get(`${API}/assegnazioni-turni?settimana=${s}`).then(res => setAssegnazioni(res.data || [])).catch(() => {});
  useEffect(() => { caricaSettimana(settimana); }, [settimana]);
  useEffect(() => {
    // Il riordino a trascinamento esiste solo nella vista griglia.
    if (!tbodyRef.current) return;
    const s = Sortable.create(tbodyRef.current, {
      handle: ".dc-drag-handle", animation: 150,
      onEnd: () => {
        const ids = Array.from(tbodyRef.current.children).map(tr => tr.getAttribute("data-id")).filter(Boolean);
        hrApi.post(`${API}/ordine-dipendenti`, { ordine: ids }).then(() => reload && reload());
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
      for (const u of updates) await hrApi.post(`${API}/assegnazioni-turni`, { ...u, settimana });
      await caricaSettimana(settimana);
    } finally { setBusy(false); }
  };

  // Onomastici (gestiti nel modale unico "Configura turni"); qui solo il riepilogo settimanale.
  const [onomSett, setOnomSett] = useState([]);
  useEffect(() => { hrApi.get(`${API}/onomastici/settimana?settimana=${settimana}`).then(r => setOnomSett(r.data || [])).catch(() => setOnomSett([])); }, [settimana]);
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
      for (const o of mancanti) await hrApi.post(`${API}/assegnazioni-turni`, { dipendente_id: o.dipendente_id, giorno: o.giorno_nome, turno_id: idR, settimana, motivo: "onomastico" });
      caricaSettimana(settimana);
    })();
  }, [onomSett, assegnazioni, turni, settimana]);

  // Config turni per dipendente (turno abituale + giorno di riposo fisso) + ferie
  const [turniCfg, setTurniCfg] = useState([]);     // [{dipendente_id, turno_id, riposo_giorno}]
  const [ferieTurni, setFerieTurni] = useState([]); // ferie/permessi per overlay
  const [showCfg, setShowCfg] = useState(false);
  const [cfgRows, setCfgRows] = useState([]);
  const isoT = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const caricaCfg = () => hrApi.get(`${API}/turni-config`).then(r => setTurniCfg(r.data || [])).catch(() => {});
  // Periodo di chiusura pomeridiana del bar (es. estate): impostato nel modale Configura turni.
  const [chiusuraPom, setChiusuraPom] = useState({ attiva: false, dal: "", al: "" });
  useEffect(() => {
    caricaCfg();
    hrApi.get(`${API}/ferie`).then(r => setFerieTurni(r.data || [])).catch(() => {});
    hrApi.get(`${API}/turni-chiusura-pomeridiana`)
      .then(r => setChiusuraPom({ attiva: !!r.data.attiva, dal: r.data.dal || "", al: r.data.al || "" }))
      .catch(() => {});
  }, []);
  const cfgDi = (dipId) => turniCfg.find(c => c.dipendente_id === dipId) || {};
  // Preferenze del giorno di riposo inviate dai dipendenti dal portale (per settimana)
  const [prefRiposo, setPrefRiposo] = useState([]);
  useEffect(() => {
    hrApi.get(`${API}/turni-preferenze?settimana=${settimana}`)
      .then(r => setPrefRiposo(r.data || [])).catch(() => setPrefRiposo([]));
  }, [settimana]);
  const prefDi = (dipId) => (prefRiposo.find(p => p.dipendente_id === dipId) || {}).giorno || null;
  // Disponibilità a coprire il bar (dal portale, per chi ha il flag 🆘 in Configura turni)
  const [dispBar, setDispBar] = useState([]);
  useEffect(() => {
    hrApi.get(`${API}/turni-disponibilita-bar?settimana=${settimana}`)
      .then(r => setDispBar(r.data || [])).catch(() => setDispBar([]));
  }, [settimana]);
  const ferieDataT = (dipId, dStr) => ferieTurni.find(f => f.dipendente_id === dipId
    && (f.stato === 'approvata' || !f.stato)
    && f.data_inizio <= dStr && (f.data_fine || f.data_inizio) >= dStr);
  const LUNGA_GIORNI = ["Venerdì", "Sabato", "Domenica"];  // giorni in cui si può fissare la Lunga
  const apriCfg = async () => {
    let onom = [];
    try { onom = (await hrApi.get(`${API}/onomastici`)).data || []; } catch {}
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
    await hrApi.post(`${API}/turni-config`, { voci: cfgRows.map(r => ({ dipendente_id: r.dipendente_id, turno_id: r.turno_id || null, riposo_giorno: r.riposo_giorno || null, lunga_giorni: lungaGiorniDi(r), rotazione: r.rotazione || null, rotazione_ancora: (r.rotazione && r.rotazione_ancora) || null, sala: !!r.sala, sostituto_bar: !!r.sostituto_bar })) });
    await hrApi.post(`${API}/onomastici`, { voci: cfgRows.map(r => ({ dipendente_id: r.dipendente_id, mese: r.onom_mese ? Number(r.onom_mese) : null, giorno: r.onom_giorno ? Number(r.onom_giorno) : null, attivo: r.onom_attivo })) });
    await hrApi.post(`${API}/turni-chiusura-pomeridiana`, chiusuraPom).catch(() => {});
    await caricaCfg();
    hrApi.get(`${API}/onomastici/settimana?settimana=${settimana}`).then(r => setOnomSett(r.data || []));
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
    try { for (const u of updates) await hrApi.post(`${API}/assegnazioni-turni`, { ...u, settimana }); }
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
    try { ferieFresh = (await hrApi.get(`${API}/ferie`)).data || []; setFerieTurni(ferieFresh); } catch { /* uso lo stato attuale */ }
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
      await hrApi.post(`${API}/turni`, { nome, orario_inizio: "", orario_fine: "", colore });
      const fresh = (await hrApi.get(`${API}/turni`)).data || [];
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
      if (batch.length) { try { await hrApi.post(`${API}/presenze/batch`, batch); } catch (e) { console.error(e); } }
      // Nella griglia turni della settimana: cella "Malattia" (non Riposo) nei giorni del range.
      const idMal = await ensureTurno("Malattia", "#f59e0b");
      for (let gi = 0; gi < 7; gi++) { const d = new Date(lunedi); d.setDate(lunedi.getDate() + gi); const ds = iso(d);
        if (ds >= dal && ds <= al) ups.push({ dipendente_id: sost.assente, giorno: giorni[gi], turno_id: idMal || null, motivo: "malattia" }); }
    } else {
      // Ferie/Permesso/Assenza: registro la presenza del giorno e libero il turno (Riposo).
      const ds = dataGiorno(sost.giorno);
      try { await hrApi.post(`${API}/presenze/batch`, [{ dipendente_id: sost.assente, data: ds, stato: sost.motivo === "assenza" ? "assente" : "giustificato", giustificativo: giust, note: sost.motivo }]); } catch (e) { console.error(e); }
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
        <button onClick={() => setLunedi(d => { const n = new Date(d); n.setDate(d.getDate() - 7); return n; })} className="dc-btn">‹</button>
        <strong style={{ minWidth: 150, textAlign: "center" }}>{meseLabel}</strong>
        <button onClick={() => setLunedi(d => { const n = new Date(d); n.setDate(d.getDate() + 7); return n; })} className="dc-btn">›</button>
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
            style={{ border: penTurno === "" ? "3px solid #5b7a6b" : "1px solid #e6e0d4", background: "#fff", color: "#374151", borderRadius: 8, padding: "5px 10px", fontWeight: 700, cursor: "pointer", fontSize: 13 }}>
            – (vuoto)
          </button>
          {turni.map(t => (
            <button key={t.id} type="button" onClick={() => setPenTurno(t.id)}
              style={{ border: penTurno === t.id ? "3px solid #5b7a6b" : "1px solid #e6e0d4", background: penTurno === t.id ? t.colore : t.colore + "30", color: penTurno === t.id ? "#fff" : "#374151", borderRadius: 8, padding: "5px 10px", fontWeight: 700, cursor: "pointer", fontSize: 13 }}>
              {t.nome}
            </button>
          ))}
        </div>
      )}

      {showCfg && (
        <div onClick={() => setShowCfg(false)} style={{ position: "fixed", inset: 0, background: "rgba(42,51,41,.45)", display: "flex", alignItems: "flex-start", justifyContent: "center", padding: 20, zIndex: 50, overflow: "auto" }}>
          <div onClick={e => e.stopPropagation()} className="dc-card" style={{ maxWidth: 1080, width: "100%", marginTop: 20 }}>
            <h3 style={{ marginTop: 0 }}>⚙️ Configura turni dipendenti</h3>
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
        </div>
      )}

      {showSost && (
        <div onClick={() => setShowSost(false)} style={{ position: "fixed", inset: 0, background: "rgba(42,51,41,.45)", display: "flex", alignItems: "flex-start", justifyContent: "center", padding: 20, zIndex: 50, overflow: "auto" }}>
          <div onClick={e => e.stopPropagation()} className="dc-card" style={{ maxWidth: 520, width: "100%", marginTop: 40 }}>
            <h3 style={{ marginTop: 0 }}>🚨 Sostituzione d'emergenza</h3>
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
        </div>
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
                <td className="dc-drag-handle" style={{ cursor: "grab", color: "#94a3b8", textAlign: "center", userSelect: "none", touchAction: "none" }} title="Trascina per riordinare">⠿</td>
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
function BustePagaPage({ dipendenti, reload, getDipendente }) {
  const [anno, setAnno] = useState(new Date().getFullYear());
  const [mese, setMese] = useState(new Date().getMonth() + 1);
  const [righe, setRighe] = useState({});
  const [salvato, setSalvato] = useState({});
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState(null);
  const fileRef = useRef(null);
  const excelRef = useRef(null);
  const [pnMsg, setPnMsg] = useState(null);
  const [soloMancanti, setSoloMancanti] = useState(false);
  const [vistaAnno, setVistaAnno] = useState(false);
  const [annoMatrix, setAnnoMatrix] = useState(null);
  const [cercaQ, setCercaQ] = useState("");
  const [cercaRes, setCercaRes] = useState(null);
  const [cercaBusy, setCercaBusy] = useState(false);
  const [rescanMsg, setRescanMsg] = useState("");
  const mesi = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno","Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"];

  const vuota = () => ({ importo_busta: "", bonifico_ricevuto: false, bonifico_importo: "", bonifico_data: "", acconti: [] });

  const load = async () => {
    const res = await hrApi.get(`${API}/paghe?anno=${anno}&mese=${mese}`);
    const map = {};
    (res.data || []).forEach(p => { map[p.dipendente_id] = {
      importo_busta: p.importo_busta ?? "",
      bonifico_ricevuto: !!p.bonifico_ricevuto,
      bonifico_importo: p.bonifico_importo ?? "",
      bonifico_data: p.bonifico_data ?? "",
      acconti: (p.acconti || []).map(a => ({ importo: a.importo ?? "", data: a.data ?? "" })),
      busta_riconciliata: !!p.busta_riconciliata,
      bonifico_riconciliato: !!p.bonifico_riconciliato,
      bonifico_pdf: p.bonifico_pdf || "",
      bonifico_causale: p.bonifico_causale || "",
      busta_da_lul: !!p.busta_da_lul,
      prestito_importo: p.prestito_importo ?? "",
      prestito_saldo: p.prestito_saldo ?? "",
      tfr_anticipo_importo: p.tfr_anticipo_importo ?? "",
      acconto_cedolino: p.acconto_cedolino ?? "",
      saldo_residuo: p.saldo_residuo ?? "",
    }; });
    setRighe(map);
  };
  useEffect(() => { load(); }, [anno, mese]);

  const get = (id) => righe[id] || vuota();
  const upd = (id, patch) => setRighe(r => ({ ...r, [id]: { ...get(id), ...patch } }));
  const setAcc = (id, idx, patch) => { const acc = [...(get(id).acconti || [])]; acc[idx] = { ...(acc[idx] || { importo: "", data: "" }), ...patch }; upd(id, { acconti: acc }); };
  const addAcc = (id) => { const acc = [...(get(id).acconti || [])]; if (acc.length < 3) { acc.push({ importo: "", data: "" }); upd(id, { acconti: acc }); } };
  const delAcc = (id, idx) => { const acc = [...(get(id).acconti || [])]; acc.splice(idx, 1); upd(id, { acconti: acc }); };

  const salva = async (id) => {
    const d = get(id);
    const payload = {
      dipendente_id: id, anno, mese,
      importo_busta: d.importo_busta === "" ? null : parseFloat(d.importo_busta),
      bonifico_ricevuto: d.bonifico_ricevuto,
      bonifico_importo: d.bonifico_importo === "" ? null : parseFloat(d.bonifico_importo),
      bonifico_data: d.bonifico_data || null,
      acconti: (d.acconti || []).filter(a => a.importo !== "" && a.importo != null).map(a => ({ importo: parseFloat(a.importo), data: a.data || null })),
    };
    try { await hrApi.post(`${API}/paghe`, payload); setSalvato(s => ({ ...s, [id]: true })); setTimeout(() => setSalvato(s => ({ ...s, [id]: false })), 1500); toast("Busta salvata"); } catch (e) { console.error(e); toast("Errore salvataggio", "err"); }
  };

  const eur = (n) => (n || 0).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  // Stato pagamento di una paga: ok / parziale / manca / bonifico-senza-busta / null
  const statoPaga = (p) => {
    if (!p) return null;
    const busta = parseFloat(p.importo_busta) || 0;
    const bon = parseFloat(p.bonifico_importo) || 0;
    const acc = (p.acconti || []).reduce((a, x) => a + (parseFloat(x.importo) || 0), 0);
    if (busta <= 0 && bon <= 0 && acc <= 0) return null;
    const pagato = bon + acc;
    if (busta <= 0 && bon > 0) return "bonifico";
    if (pagato + 0.5 >= busta) return "ok";
    if (pagato > 0) return "parziale";
    return "manca";
  };

  // Vista annuale: carica i 12 mesi dell'anno selezionato
  useEffect(() => {
    if (!vistaAnno) return;
    let vivo = true;
    (async () => {
      const res = await Promise.all([1,2,3,4,5,6,7,8,9,10,11,12].map(m =>
        hrApi.get(`${API}/paghe?anno=${anno}&mese=${m}`).then(r => [m, r.data || []]).catch(() => [m, []])));
      if (!vivo) return;
      const mtx = {};
      res.forEach(([m, rows]) => { mtx[m] = {}; rows.forEach(p => { mtx[m][p.dipendente_id] = p; }); });
      setAnnoMatrix(mtx);
    })();
    return () => { vivo = false; };
  }, [vistaAnno, anno]);

  const cercaVoce = async () => {
    const q = cercaQ.trim();
    if (!q) return;
    setCercaBusy(true); setCercaRes(null);
    const isCode = /^[A-Za-z]\d{3,5}$/.test(q);
    const params = isCode ? `codice=${encodeURIComponent(q.toUpperCase())}` : `testo=${encodeURIComponent(q)}`;
    try {
      const r = await hrApi.get(`${API}/cedolini/cerca-voce?${params}`);
      setCercaRes(r.data);
    } catch (e) {
      setCercaRes({ risultati: [], totale: 0, errore: e?.response?.data?.message || "Errore ricerca" });
    } finally { setCercaBusy(false); }
  };

  const riscansiona = async () => {
    if (!window.confirm("Riscansiona i cedolini storici con PDF salvato? Può richiedere fino a un minuto.")) return;
    setRescanMsg("Riscansione in corso…");
    try {
      const r = await hrApi.post(`${API}/cedolini/riscansiona`);
      setRescanMsg(`✓ Riscansione completata: ${r.data.aggiornati} cedolini aggiornati, ${r.data.errori} senza PDF/errore.`);
    } catch (e) { setRescanMsg("⚠ " + (e?.response?.data?.message || "Errore riscansione")); }
  };

  const correggiAcconti = async () => {
    if (!window.confirm("Togliere gli 'acconto dal cedolino' implausibili (poche decine di euro, probabile errore di lettura) e ricalcolare il saldo? Non tocca gli acconti registrati a mano.")) return;
    setRescanMsg("Correzione acconti in corso…");
    try {
      const r = await hrApi.post(`${API}/paghe/correggi-acconti-cedolino`);
      setRescanMsg(`✓ Corretti ${r.data.corretti} acconti implausibili (rimossi, saldo ricalcolato sul netto pieno).`);
      await load();
    } catch (e) { setRescanMsg("⚠ " + (e?.response?.data?.message || "Errore correzione acconti")); }
  };

  const handleImportLul = async (e) => {
    const fs = Array.from(e.target.files || []);
    if (!fs.length) return;
    setImporting(true); setImportMsg(null);
    try {
      const fd = new FormData();
      fs.forEach(f => fd.append("files", f));
      const res = await hrApi.post(`${API}/paghe/importa-lul`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      const r = res.data;
      setImportMsg(r);
      if (r.mesi?.length) { const u = r.mesi[r.mesi.length - 1]; setMese(u.mese); setAnno(u.anno); }
      await load();
    } catch (err) {
      setImportMsg({ errore: err.response?.data?.message || "Errore durante l'import" });
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };
  const handleImportEmail = async () => {
    setImporting(true); setImportMsg(null);
    try {
      const res = await hrApi.post(`${API}/paghe/importa-email`);
      const r = res.data;
      setImportMsg(r);
      if (r.mesi?.length) { const u = r.mesi[r.mesi.length - 1]; setMese(u.mese); setAnno(u.anno); }
      await load();
    } catch (err) {
      setImportMsg({ errore: err.response?.data?.message || "Errore durante l'import da email" });
    } finally {
      setImporting(false);
    }
  };
  const handleImportPrimaNota = async (e) => {
    const fl = (e.target.files || [])[0];
    if (!fl) return;
    setImporting(true); setPnMsg(null);
    try {
      const fd = new FormData(); fd.append("file", fl);
      const r = await hrApi.post(`${API}/paghe/importa-prima-nota`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setPnMsg(r.data);
      await load();
      if (vistaAnno) { setVistaAnno(false); setTimeout(() => setVistaAnno(true), 50); }
    } catch (err) {
      setPnMsg({ errore: err?.response?.data?.message || "Errore import Prima Nota" });
    } finally {
      setImporting(false);
      if (excelRef.current) excelRef.current.value = "";
    }
  };
  const csvRef = useRef(null);
  const [csvMsg, setCsvMsg] = useState(null);
  const [pnDett, setPnDett] = useState(null);
  const handleImportPagamenti = async (e) => {
    const fl = (e.target.files || [])[0];
    if (!fl) return;
    setImporting(true); setCsvMsg(null);
    try {
      const fd = new FormData(); fd.append("file", fl);
      const r = await hrApi.post(`${API}/paghe/importa-pagamenti`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setCsvMsg(r.data); await load();
      if (vistaAnno) { setVistaAnno(false); setTimeout(() => setVistaAnno(true), 50); }
    } catch (err) { setCsvMsg({ errore: err?.response?.data?.message || "Errore import pagamenti" }); }
    finally { setImporting(false); if (csvRef.current) csvRef.current.value = ""; }
  };
  const apriPrimaNota = async (dipId, nome) => {
    setPnDett({ nome, loading: true });
    try {
      const [r, s] = await Promise.all([
        hrApi.get(`${API}/paghe/prima-nota?dipendente_id=${dipId}`),
        hrApi.get(`${API}/paghe/storico-pagamenti?dipendente_id=${dipId}`).catch(() => ({ data: { righe: [] } })),
      ]);
      setPnDett({ nome, righe: r.data.righe || [], saldo_finale: r.data.saldo_finale, storico: s.data.righe || [] });
    } catch { setPnDett({ nome, righe: [], errore: true }); }
  };
  const storicoRef = useRef(null);
  const [storicoMsg, setStoricoMsg] = useState(null);
  const handleImportStorico = async (e) => {
    const fl = (e.target.files || [])[0];
    if (!fl) return;
    setImporting(true); setStoricoMsg(null);
    try {
      const fd = new FormData(); fd.append("file", fl);
      const r = await hrApi.post(`${API}/paghe/importa-storico-pagamenti`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setStoricoMsg(r.data);
    } catch (err) { setStoricoMsg({ errore: err?.response?.data?.message || "Errore import archivio storico" }); }
    finally { setImporting(false); if (storicoRef.current) storicoRef.current.value = ""; }
  };
  const totBuste = dipendenti.reduce((s, d) => s + (parseFloat(get(d.id).importo_busta) || 0), 0);
  const totBonifici = dipendenti.reduce((s, d) => s + (parseFloat(get(d.id).bonifico_importo) || 0), 0);
  const totAcconti = dipendenti.reduce((s, d) => s + (get(d.id).acconti || []).reduce((a, x) => a + (parseFloat(x.importo) || 0), 0), 0);
  const inp = { border: "1px solid #d1d5db", borderRadius: 8, padding: "7px 9px", fontSize: 14, width: "100%", boxSizing: "border-box" };

  const [showImport, setShowImport] = useState(false);
  const [showCerca, setShowCerca] = useState(false);

  // Simulazione F24 + costo mensile (dai cedolini del mese) e import da Google Drive
  const [f24, setF24] = useState(null);
  const [f24Busy, setF24Busy] = useState(false);
  const [driveMsg, setDriveMsg] = useState(null);
  const calcolaF24 = async () => {
    setF24Busy(true); setF24(null);
    try { const r = await hrApi.get(`/api/hr/cedolini/simulazione-f24?anno=${anno}&mese=${mese}`); setF24(r.data); }
    catch (e) { setF24({ errore: e?.response?.data?.message || "Errore nel calcolo" }); }
    finally { setF24Busy(false); }
  };
  const importaDaDrive = async () => {
    if (!window.confirm("Importo i PDF (buste paga e documenti) dalla cartella Google Drive dei cedolini?")) return;
    setImporting(true); setDriveMsg(null);
    try { const r = await hrApi.post(`/api/hr/cedolini/import-drive`, {}); setDriveMsg(r.data); }
    catch (e) { setDriveMsg({ errore: e?.response?.data?.message || "Errore import da Drive" }); }
    finally { setImporting(false); }
  };

  return (
    <div className="dc-page">
      <div className="dc-page-header">
        <div>
          <h1>Buste Paga</h1>
          <p>Importo busta, bonifico ricevuto e acconti · tutto salvato sul database</p>
        </div>
        <div className="dc-page-actions" style={{ position: "relative" }}>
          <input ref={fileRef} type="file" accept=".pdf,.zip,application/pdf,application/zip,application/x-zip-compressed" multiple onChange={handleImportLul} style={{ display: "none" }} />
          <input ref={excelRef} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={handleImportPrimaNota} style={{ display: "none" }} />
          <input ref={csvRef} type="file" accept=".csv,text/csv" onChange={handleImportPagamenti} style={{ display: "none" }} />
          <input ref={storicoRef} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={handleImportStorico} style={{ display: "none" }} />
          <button onClick={() => setShowImport(s => !s)} disabled={importing}
            style={{ background: "#5b7a6b", color: "#fff", border: "none", borderRadius: 10, padding: "9px 16px", fontWeight: 700, cursor: importing ? "default" : "pointer", opacity: importing ? 0.6 : 1 }}>
            {importing ? "Importo…" : "⤵ Importa  ▾"}
          </button>
          {showImport && (
            <div style={{ position: "absolute", top: "100%", left: 0, marginTop: 6, background: "#fffefb", border: "1px solid #e6e0d4", borderRadius: 10, boxShadow: "0 6px 20px rgba(0,0,0,.12)", zIndex: 30, minWidth: 280, overflow: "hidden" }}>
              {[["Libro Unico (PDF/ZIP)", () => fileRef.current?.click()],
                ["Buste da email", handleImportEmail],
                ["Prima Nota (Excel)", () => excelRef.current?.click()],
                ["Pagamenti banca (CSV)", () => csvRef.current?.click()],
                ["Archivio storico pagamenti ante-app (Excel)", () => storicoRef.current?.click()]].map(([label, fn], i, arr) => (
                <button key={i} onClick={() => { setShowImport(false); fn(); }}
                  style={{ display: "block", width: "100%", textAlign: "left", background: "none", border: "none", borderBottom: i < arr.length - 1 ? "1px solid #f0ebe0" : "none", padding: "11px 14px", fontSize: 14, cursor: "pointer", color: "#2a3329" }}>{label}</button>
              ))}
            </div>
          )}
          <select value={mese} onChange={e => setMese(+e.target.value)} className="dc-select">
            {mesi.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
          </select>
          <select value={anno} onChange={e => setAnno(+e.target.value)} className="dc-select">
            {[2022, 2023, 2024, 2025, 2026, 2027].map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
      </div>

      <div className="dc-card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <h3 style={{ margin: 0 }}>🧾 Simulazione F24 e costo mensile — {mesi[mese - 1]} {anno}</h3>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="dc-btn" disabled={importing} onClick={importaDaDrive}
              title="Scarica i PDF delle buste dalla cartella Drive dei cedolini (service account) e li archivia con la stessa pipeline dell'upload massivo">
              📥 Importa cedolini da Drive
            </button>
            <button className="dc-btn-primary" disabled={f24Busy} onClick={calcolaF24}>{f24Busy ? "Calcolo…" : "Calcola F24 del mese"}</button>
          </div>
        </div>
        <p className="dc-muted" style={{ fontSize: 12.5, margin: "6px 0 0" }}>
          Per ogni dipendente legge il cedolino del mese (contratto e livello applicati in busta): IRPEF e INPS
          reali dalle voci quando ci sono, altrimenti stimati dal netto con le regole CCNL. INPS azienda 30%,
          quota TFR = lordo ÷ 13,5. È una simulazione: fa fede l'F24 del consulente.
        </p>
        {driveMsg && (
          <div style={{ marginTop: 8, fontSize: 13, color: driveMsg.errore ? "#b3261e" : "#3f5a4e" }}>
            {driveMsg.errore
              ? `⚠ ${driveMsg.errore}`
              : `✓ Drive: ${driveMsg.trovati_pdf} PDF trovati · ${driveMsg.archiviati} archiviati · ${driveMsg.duplicati} duplicati saltati${(driveMsg.non_assegnati || []).length ? ` · da controllare: ${driveMsg.non_assegnati.join(", ")}` : ""}`}
          </div>
        )}
        {f24?.errore && <div style={{ marginTop: 8, color: "#b3261e", fontWeight: 600 }}>⚠ {f24.errore}</div>}
        {f24 && !f24.errore && (
          f24.righe.length === 0
            ? <p className="dc-muted" style={{ marginTop: 10 }}>Nessun cedolino trovato per {mesi[mese - 1]} {anno}: importa prima le buste (Libro Unico, upload o Drive).</p>
            : (
              <div className="dc-scroll-x" style={{ marginTop: 10 }}>
                <table className="dc-table" style={{ fontSize: 13 }}>
                  <thead><tr>
                    <th>Dipendente</th><th style={{ textAlign: "right" }}>Lordo €</th><th style={{ textAlign: "right" }}>Netto €</th>
                    <th style={{ textAlign: "right" }}>IRPEF €</th><th style={{ textAlign: "right" }}>INPS dip. €</th>
                    <th style={{ textAlign: "right" }}>INPS azienda €</th><th style={{ textAlign: "right" }}>TFR mese €</th>
                    <th style={{ textAlign: "right" }}>F24 €</th><th style={{ textAlign: "right" }}>Costo azienda €</th><th>Fonte</th>
                  </tr></thead>
                  <tbody>
                    {f24.righe.map(r => (
                      <tr key={r.dipendente_id || r.dipendente_nome}>
                        <td style={{ fontWeight: 600 }}>{r.dipendente_nome}</td>
                        <td style={{ textAlign: "right" }}>{eur(r.lordo)}</td>
                        <td style={{ textAlign: "right" }}>{eur(r.netto)}</td>
                        <td style={{ textAlign: "right" }}>{eur(r.irpef)}</td>
                        <td style={{ textAlign: "right" }}>{eur(r.inps_dipendente)}</td>
                        <td style={{ textAlign: "right" }}>{eur(r.inps_azienda)}</td>
                        <td style={{ textAlign: "right" }}>{eur(r.tfr_mese)}</td>
                        <td style={{ textAlign: "right", fontWeight: 700 }}>{eur(r.totale_f24)}</td>
                        <td style={{ textAlign: "right", fontWeight: 700 }}>{eur(r.costo_azienda)}</td>
                        <td className="dc-muted" style={{ fontSize: 11.5 }}>{r.fonte}</td>
                      </tr>
                    ))}
                    <tr style={{ fontWeight: 700, borderTop: "2px solid #e6e0d4", background: "#eef1ea" }}>
                      <td>TOTALE ({f24.dipendenti} dipendenti)</td>
                      <td style={{ textAlign: "right" }}>{eur(f24.totali.lordo)}</td>
                      <td style={{ textAlign: "right" }}>{eur(f24.totali.netto)}</td>
                      <td style={{ textAlign: "right" }}>{eur(f24.totali.irpef)}</td>
                      <td style={{ textAlign: "right" }}>{eur(f24.totali.inps_dipendente)}</td>
                      <td style={{ textAlign: "right" }}>{eur(f24.totali.inps_azienda)}</td>
                      <td style={{ textAlign: "right" }}>{eur(f24.totali.tfr_mese)}</td>
                      <td style={{ textAlign: "right", fontSize: 15 }}>{eur(f24.totali.totale_f24)}</td>
                      <td style={{ textAlign: "right", fontSize: 15 }}>{eur(f24.totali.costo_azienda)}</td>
                      <td></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )
        )}
      </div>

      {pnMsg && (
        <div className="dc-card" style={{ marginBottom: 16, borderLeft: `4px solid ${pnMsg.errore ? '#d35f4e' : '#3d8168'}` }}>
          {pnMsg.errore ? <div style={{ color: "#d35f4e", fontWeight: 600 }}>⚠ {pnMsg.errore}</div> : (
            <div>
              <div style={{ fontWeight: 700 }}>✓ Prima Nota importata: {pnMsg.aggiornati} mesi/dipendente aggiornati su {pnMsg.righe_aggregate} totali.</div>
              {pnMsg.non_trovati > 0 && (
                <div style={{ marginTop: 6, fontSize: 13, color: "#7d5526" }}>
                  ⚠ {pnMsg.non_trovati} voci con dipendente non in anagrafica (non importate): {(pnMsg.nomi_non_trovati || []).join(", ")}
                </div>
              )}
              {pnMsg.discrepanze?.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontWeight: 700, fontSize: 13, color: "#7d5526" }}>Differenze importo busta (app vs Excel) — {pnMsg.discrepanze.length}:</div>
                  <div style={{ fontSize: 13, display: "flex", flexDirection: "column", gap: 2, marginTop: 2 }}>
                    {pnMsg.discrepanze.slice(0, 60).map((x, i) => (
                      <span key={i}>{x.dipendente} · {mesi[x.mese - 1]} {x.anno}: app € {eur(x.busta_app)} · Excel € {eur(x.busta_excel)}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {csvMsg && (
        <div className="dc-card" style={{ marginBottom: 16, borderLeft: `4px solid ${csvMsg.errore ? '#d35f4e' : '#3d8168'}` }}>
          {csvMsg.errore ? <div style={{ color: "#d35f4e", fontWeight: 600 }}>⚠ {csvMsg.errore}</div> : (
            <div style={{ fontSize: 14 }}>
              <div style={{ fontWeight: 700 }}>✓ Pagamenti importati: {csvMsg.importati} · {csvMsg.mesi_aggiornati} mesi aggiornati.</div>
              {csvMsg.non_trovati?.length > 0 && <div style={{ marginTop: 6, fontSize: 13, color: "#7d5526" }}>⚠ Beneficiari non trovati in anagrafica: {csvMsg.non_trovati.join(", ")}</div>}
            </div>
          )}
        </div>
      )}

      {storicoMsg && (
        <div className="dc-card" style={{ marginBottom: 16, borderLeft: `4px solid ${storicoMsg.errore ? '#d35f4e' : '#3d8168'}` }}>
          {storicoMsg.errore ? <div style={{ color: "#d35f4e", fontWeight: 600 }}>⚠ {storicoMsg.errore}</div> : (
            <div style={{ fontSize: 14 }}>
              <div style={{ fontWeight: 700 }}>✓ Archivio storico: {storicoMsg.importati} righe nuove, {storicoMsg.gia_presenti} già presenti (su {storicoMsg.righe_lette} lette).</div>
              {storicoMsg.dipendenti_non_in_anagrafica?.length > 0 && (
                <div style={{ marginTop: 6, fontSize: 13, color: "#7d5526" }}>
                  ⚠ Nomi non trovati in anagrafica (non importati): {storicoMsg.dipendenti_non_in_anagrafica.map(x => `${x.nome} (${x.righe})`).join(", ")}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {pnDett && (
        <div onClick={() => setPnDett(null)} style={{ position: "fixed", inset: 0, background: "rgba(42,51,41,.45)", display: "flex", alignItems: "flex-start", justifyContent: "center", padding: 20, zIndex: 50, overflow: "auto" }}>
          <div onClick={e => e.stopPropagation()} className="dc-card" style={{ maxWidth: 640, width: "100%", marginTop: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ margin: 0 }}>Prima nota — {pnDett.nome}</h3>
              <button className="dc-btn" onClick={() => setPnDett(null)}>Chiudi</button>
            </div>
            {pnDett.loading ? <p className="dc-muted">Carico…</p> : !pnDett.righe?.length ? <p className="dc-muted" style={{ marginTop: 12 }}>Nessun dato.</p> : (
              <div style={{ overflowX: "auto", marginTop: 12 }}>
                <table className="dc-table" style={{ minWidth: 520, whiteSpace: "nowrap" }}>
                  <thead><tr><th>Periodo</th><th style={{ textAlign: "right" }}>Busta €</th><th style={{ textAlign: "right" }}>Erogato €</th><th style={{ textAlign: "right" }}>Saldo progressivo €</th></tr></thead>
                  <tbody>
                    {pnDett.righe.map((x, i) => (
                      <tr key={i}>
                        <td>{mesi[x.mese - 1]} {x.anno}</td>
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
                <p className="dc-muted" style={{ fontSize: 12.5, margin: "0 0 8px" }}>
                  Sola consultazione: registro dei pagamenti effettuati prima di questa app, per data del bonifico.
                </p>
                <div style={{ overflowX: "auto", maxHeight: 260, overflowY: "auto" }}>
                  <table className="dc-table" style={{ minWidth: 420, whiteSpace: "nowrap" }}>
                    <thead><tr><th>Data</th><th style={{ textAlign: "right" }}>Busta €</th><th style={{ textAlign: "right" }}>Pagato €</th></tr></thead>
                    <tbody>
                      {pnDett.storico.map((x, i) => (
                        <tr key={i}>
                          <td>{formatDate(x.data)}</td>
                          <td style={{ textAlign: "right" }}>{x.busta ? eur(x.busta) : "—"}</td>
                          <td style={{ textAlign: "right" }}>{x.pagato ? eur(x.pagato) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Motore di ricerca voci cedolino + riscansione storico (a scomparsa) */}
      <div className="dc-card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0, marginBottom: showCerca ? undefined : 0, cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }} onClick={() => setShowCerca(s => !s)}>
          <span>🔎 Cerca nelle buste (qualsiasi voce)</span>
          <span className="dc-muted" style={{ fontSize: 14 }}>{showCerca ? "▲" : "▼"}</span>
        </h3>
        {showCerca && (<>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input className="dc-input" style={{ flex: "1 1 240px" }} placeholder="Codice (es. F09081) o testo (es. 730, 13ma, L.207)"
            value={cercaQ} onChange={e => setCercaQ(e.target.value)} onKeyDown={e => e.key === "Enter" && cercaVoce()} />
          <button className="dc-btn-primary" disabled={cercaBusy} onClick={cercaVoce}>{cercaBusy ? "Cerco…" : "Cerca"}</button>
          <button className="dc-btn" onClick={riscansiona} title="Rilegge i PDF dei cedolini già caricati per popolare la ricerca sullo storico">Riscansiona storico</button>
          <button className="dc-btn" onClick={correggiAcconti} title="Toglie gli 'acconto dal cedolino' di poche decine di euro (probabile errore del parser) già salvati e ricalcola il saldo">🔧 Correggi acconti cedolino</button>
        </div>
        {rescanMsg && <div className="dc-muted" style={{ marginTop: 8 }}>{rescanMsg}</div>}
        {cercaRes && (
          <div style={{ marginTop: 10, overflowX: "auto" }}>
            {cercaRes.errore ? <div className="dc-muted">⚠ {cercaRes.errore}</div>
              : cercaRes.totale === 0 ? <div className="dc-muted">Nessun risultato. Per lo storico premi prima “Riscansiona storico”.</div>
              : <table className="dc-table" style={{ minWidth: 560, whiteSpace: "nowrap" }}>
                  <thead><tr><th>Dipendente</th><th>Periodo</th><th>Codice</th><th>Descrizione</th><th style={{ textAlign: "right" }}>Importo</th></tr></thead>
                  <tbody>
                    {cercaRes.risultati.map((x, i) => (
                      <tr key={i}><td>{x.dipendente}</td><td>{mesi[(x.mese || 1) - 1]} {x.anno}</td><td>{x.codice}</td><td>{x.descrizione}</td><td style={{ textAlign: "right" }}>{x.importo || "—"}</td></tr>
                    ))}
                  </tbody>
                </table>}
            {cercaRes.totale > 0 && <p className="dc-muted" style={{ fontSize: 12, marginTop: 6 }}>{cercaRes.totale} risultati.</p>}
          </div>
        )}
        </>)}
      </div>

      {/* Riepilogo busta vs bonifico — mensile o annuale */}
      <div className="dc-card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <h3 style={{ margin: 0 }}>{vistaAnno ? `Riepilogo anno ${anno}` : `Riepilogo ${mesi[mese - 1]} ${anno}`} — busta vs bonifico</h3>
          <div style={{ display: "flex", gap: 14, fontSize: 13 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 5, cursor: "pointer" }}><input type="checkbox" checked={soloMancanti} onChange={e => setSoloMancanti(e.target.checked)} /> Solo chi manca</label>
            <label style={{ display: "flex", alignItems: "center", gap: 5, cursor: "pointer" }}><input type="checkbox" checked={vistaAnno} onChange={e => setVistaAnno(e.target.checked)} /> Vista annuale</label>
          </div>
        </div>

        {!vistaAnno && (
          <div style={{ overflowX: "auto", marginTop: 10 }}>
            <table className="dc-table" style={{ minWidth: 580, whiteSpace: "nowrap" }}>
              <thead><tr><th>Dipendente</th><th style={{ textAlign: "right" }}>Busta €</th><th style={{ textAlign: "right" }}>Acconti €</th><th style={{ textAlign: "right" }}>Bonifico €</th><th style={{ textAlign: "right" }}>Differenza</th><th>Stato</th></tr></thead>
              <tbody>
                {dipendenti.map(d => {
                  const r = get(d.id);
                  const busta = parseFloat(r.importo_busta) || 0;
                  const bon = parseFloat(r.bonifico_importo) || 0;
                  const acc = (r.acconti || []).reduce((a, x) => a + (parseFloat(x.importo) || 0), 0);
                  const cat = statoPaga(r);
                  if (!cat) return null;
                  if (soloMancanti && cat === "ok") return null;
                  const pagato = bon + acc;
                  const diff = pagato - busta;  // <0 manca, >0 eccedenza
                  const diffCell = busta <= 0 ? <span className="dc-muted">—</span>
                    : diff < -0.5 ? <span style={{ color: "#d35f4e", fontWeight: 700 }}>manca € {eur(-diff)}</span>
                    : diff > 0.5 ? <span style={{ color: "#7d5526", fontWeight: 700 }}>+€ {eur(diff)}</span>
                    : <span style={{ color: "#3d8168", fontWeight: 700 }}>0,00</span>;
                  const stato = cat === "bonifico" ? <Badge variant="warning">bonifico senza busta</Badge>
                    : cat === "ok" ? <Badge variant="success">✓ pagato</Badge>
                    : cat === "parziale" ? <Badge variant="warning">parziale</Badge>
                    : <Badge variant="danger">⚠ da pagare</Badge>;
                  return (
                    <tr key={d.id}>
                      <td><button onClick={() => apriPrimaNota(d.id, d.cognome ? `${d.cognome} ${d.nome || ''}`.trim() : d.nome)} title="Apri prima nota / saldo progressivo" style={{ background: "none", border: "none", color: "#5b7a6b", cursor: "pointer", textDecoration: "underline", padding: 0, font: "inherit" }}>{d.cognome ? `${d.cognome} ${d.nome?.[0] || ''}.` : d.nome}</button></td>
                      <td style={{ textAlign: "right" }}>{busta ? eur(busta) : "—"}</td>
                      <td style={{ textAlign: "right" }}>{acc ? eur(acc) : "—"}</td>
                      <td style={{ textAlign: "right" }}>{bon ? eur(bon) : "—"}</td>
                      <td style={{ textAlign: "right" }}>{diffCell}</td>
                      <td>{stato}</td>
                    </tr>
                  );
                })}
                {!soloMancanti && (
                  <tr style={{ fontWeight: 700, borderTop: "2px solid #e6e0d4" }}>
                    <td>Totale</td>
                    <td style={{ textAlign: "right" }}>{eur(totBuste)}</td>
                    <td style={{ textAlign: "right" }}>{eur(totAcconti)}</td>
                    <td style={{ textAlign: "right" }}>{eur(totBonifici)}</td>
                    <td style={{ textAlign: "right" }}>{eur(totBonifici + totAcconti - totBuste)}</td>
                    <td></td>
                  </tr>
                )}
              </tbody>
            </table>
            <p className="dc-muted" style={{ fontSize: 12, marginTop: 8 }}>“Pagato” = bonifico emesso + acconti ≥ importo busta.</p>
          </div>
        )}

        {vistaAnno && (
          <div style={{ overflowX: "auto", marginTop: 10 }}>
            {!annoMatrix ? <div className="dc-muted">Carico l'anno…</div> : (
              <table className="dc-table" style={{ minWidth: 1280, whiteSpace: "nowrap", fontSize: 12 }}>
                <thead><tr><th>Dipendente</th>{mesi.map((m, i) => <th key={i} title={m} style={{ textAlign: "center" }}>{m.slice(0, 3)}</th>)}<th style={{ textAlign: "right" }}>Tot Busta</th><th style={{ textAlign: "right" }}>Tot Bonifici</th><th style={{ textAlign: "right" }}>Differenza</th></tr></thead>
                <tbody>
                  {dipendenti.map(d => {
                    const paghe = mesi.map((_, i) => (annoMatrix[i + 1] || {})[d.id]);
                    const celle = paghe.map(p => statoPaga(p));
                    if (soloMancanti && !celle.some(c => c && c !== "ok")) return null;
                    if (!soloMancanti && celle.every(c => !c)) return null;
                    const tb = paghe.reduce((s, p) => s + (parseFloat(p?.importo_busta) || 0), 0);
                    const tbon = paghe.reduce((s, p) => s + (parseFloat(p?.bonifico_importo) || 0), 0);
                    const tacc = paghe.reduce((s, p) => s + ((p?.acconti || []).reduce((a, x) => a + (parseFloat(x.importo) || 0), 0)), 0);
                    const tdiff = (tbon + tacc) - tb;
                    return (
                      <tr key={d.id}>
                        <td><button onClick={() => apriPrimaNota(d.id, d.cognome ? `${d.cognome} ${d.nome || ''}`.trim() : d.nome)} title="Apri prima nota / saldo progressivo" style={{ background: "none", border: "none", color: "#5b7a6b", cursor: "pointer", textDecoration: "underline", padding: 0, font: "inherit" }}>{d.cognome ? `${d.cognome} ${d.nome?.[0] || ''}.` : d.nome}</button></td>
                        {celle.map((c, i) => {
                          const p = paghe[i];
                          const bm = parseFloat(p?.importo_busta) || 0;
                          const em = (parseFloat(p?.bonifico_importo) || 0) + ((p?.acconti || []).reduce((a, x) => a + (parseFloat(x.importo) || 0), 0));
                          const manca = bm - em;
                          let txt, col, title;
                          if (!c) { txt = "·"; col = "#cbd2c9"; title = `${mesi[i]}: nessun dato`; }
                          else if (c === "ok") { txt = "✓"; col = "#3d8168"; title = `${mesi[i]}: pagato (busta € ${eur(bm)})`; }
                          else if (c === "bonifico") { txt = "+" + eur(em); col = "#7d5526"; title = `${mesi[i]}: bonifico € ${eur(em)} senza busta`; }
                          else if (manca > 0.5) { txt = eur(manca); col = "#d35f4e"; title = `${mesi[i]}: manca € ${eur(manca)} (busta € ${eur(bm)}, erogato € ${eur(em)})`; }
                          else { txt = "+" + eur(-manca); col = "#7d5526"; title = `${mesi[i]}: eccedenza € ${eur(-manca)}`; }
                          return <td key={i} style={{ textAlign: "right", color: col, fontWeight: 700, fontSize: 12 }} title={title}>{txt}</td>;
                        })}
                        <td style={{ textAlign: "right" }}>{tb ? eur(tb) : "—"}</td>
                        <td style={{ textAlign: "right" }}>{tbon ? eur(tbon) : "—"}</td>
                        <td style={{ textAlign: "right", fontWeight: 700, color: tb <= 0 ? "#94a3b8" : tdiff < -0.5 ? "#d35f4e" : tdiff > 0.5 ? "#7d5526" : "#3d8168" }}>
                          {tb <= 0 ? "—" : tdiff < -0.5 ? `manca € ${eur(-tdiff)}` : tdiff > 0.5 ? `+€ ${eur(tdiff)}` : "0,00"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
            <p className="dc-muted" style={{ fontSize: 12, marginTop: 8 }}>In ogni mese: <b style={{ color: "#d35f4e" }}>importo rosso</b> = quanto manca · <b style={{ color: "#7d5526" }}>+importo</b> = eccedenza · <b style={{ color: "#3d8168" }}>✓</b> = pagato · · = nessun dato. Importi in euro (es. 1.000,00). Scorri in orizzontale per vedere tutti i mesi.</p>
          </div>
        )}
      </div>

      {importMsg && (
        <div className="dc-card" style={{ marginBottom: 16, padding: 14, borderLeft: `4px solid ${importMsg.errore ? '#d35f4e' : '#3d8168'}` }}>
          {importMsg.errore ? (
            <div style={{ color: "#d35f4e", fontWeight: 600 }}>⚠ {importMsg.errore}</div>
          ) : (
            <div>
              <div style={{ fontWeight: 700, marginBottom: 6 }}>
                ✓ Elaborati {importMsg.file_pdf} documenti · {importMsg.totale_associati} buste{importMsg.bonifici?.length ? ` · ${importMsg.bonifici.length} bonifici` : ""}{importMsg.prestiti?.length ? ` · ${importMsg.prestiti.length} prestiti` : ""}{importMsg.presenze?.length ? ` · ${importMsg.presenze.length} presenze` : ""}
              </div>
              {importMsg.mesi?.length > 0 && (
                <div style={{ fontSize: 13, marginBottom: 6, color: "#2a3329" }}>
                  Mesi importati: {importMsg.mesi.map(mm => `${mesi[mm.mese - 1]} ${mm.anno} (${mm.n})`).join(" · ")}
                </div>
              )}
              <div style={{ fontSize: 13, color: "#6b7669", display: "flex", flexWrap: "wrap", gap: "2px 14px" }}>
                {importMsg.associati?.map((a, i) => (
                  <span key={i}>{a.dipendente}: € {eur(a.netto)}{importMsg.mesi?.length > 1 ? ` (${a.mese}/${a.anno})` : ""}{a.metodo !== "codice fiscale" ? " ⚠" : ""}</span>
                ))}
              </div>
              {importMsg.bonifici?.length > 0 && (
                <div style={{ marginTop: 10 }}>
                  <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4, color: "#234d3d" }}>Bonifici associati ({importMsg.bonifici.length})</div>
                  <div style={{ fontSize: 13, color: "#2a3329", display: "flex", flexDirection: "column", gap: 2 }}>
                    {importMsg.bonifici.map((b, i) => (
                      <span key={i}>
                        {b.dipendente}: € {eur(b.importo)} → {mesi[b.mese - 1]} {b.anno}
                        <span style={{ color: "#6b7669" }}> [{b.fonte}]</span>
                        <span style={{ color: "#234d3d", fontWeight: 700 }}> · ✓ riconciliato PDF</span>
                        {b.discrepanza != null && <span style={{ color: "#7d5526" }}> (Excel attendeva € {eur(b.discrepanza)})</span>}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {importMsg.tfr?.length > 0 && (
                <div style={{ marginTop: 10 }}>
                  <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4, color: "#56442d" }}>Anticipi TFR ({importMsg.tfr.length}) — fuori dal saldo stipendi</div>
                  <div style={{ fontSize: 13, color: "#2a3329", display: "flex", flexDirection: "column", gap: 2 }}>
                    {importMsg.tfr.map((t, i) => (
                      <span key={i}>{t.dipendente}: € {eur(t.importo)} → {mesi[t.mese - 1]} {t.anno}</span>
                    ))}
                  </div>
                </div>
              )}
              {importMsg.prestiti?.length > 0 && (
                <div style={{ marginTop: 10 }}>
                  <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4, color: "#6a4a86" }}>Prestiti ({importMsg.prestiti.length}) — mastrino separato dalle buste</div>
                  <div style={{ fontSize: 13, color: "#2a3329", display: "flex", flexDirection: "column", gap: 2 }}>
                    {importMsg.prestiti.map((p, i) => (
                      <span key={i}>{p.dipendente}: € {eur(p.importo)} → {mesi[p.mese - 1]} {p.anno} · <strong>saldo prestito € {eur(p.saldo)}</strong></span>
                    ))}
                  </div>
                </div>
              )}
              {importMsg.cartelle_lette?.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 12, color: "#6b7669" }}>
                  Cartelle email lette: {importMsg.cartelle_lette.map(c => `${c.cartella} (${c.messaggi})`).join(" · ")}
                </div>
              )}
              {importMsg.presenze?.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 13, color: "#56442d" }}>
                  Fogli presenze riconosciuti (non sono buste): {importMsg.presenze.map(p => `${p.dipendente}${p.mese ? ` ${mesi[p.mese - 1]} ${p.anno}` : ""}`).join("; ")}
                </div>
              )}
              {importMsg.duplicati?.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 13, color: "#8a6f47", background: "#f3ead9", border: "1px solid #e7d6b9", borderRadius: 8, padding: "6px 10px" }}>
                  🔁 Duplicati scartati automaticamente ({importMsg.duplicati.length}): {importMsg.duplicati.map(x => `${x.file} — ${x.motivo}`).join("; ")}
                </div>
              )}
              {importMsg.da_controllare?.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 13, color: "#7d5526" }}>
                  Da controllare: {importMsg.da_controllare.map(x => `${x.nome || x.cf} (${x.motivo})`).join("; ")}
                </div>
              )}
              {importMsg.errori?.length > 0 && (
                <div style={{ marginTop: 6, fontSize: 12, color: "#8f3829" }}>
                  Avvisi: {importMsg.errori.join("; ")}
                </div>
              )}
              <button onClick={() => setImportMsg(null)} style={{ marginTop: 8, border: "none", background: "transparent", color: "#6b7669", textDecoration: "underline", cursor: "pointer", fontSize: 12 }}>chiudi</button>
            </div>
          )}
        </div>
      )}

      <div className="dc-buste-stats" style={{ marginBottom: 16 }}>
        <div className="dc-buste-stat dc-buste-stat-blue"><span className="dc-buste-stat-label">TOTALE BUSTE</span><span className="dc-buste-stat-value">€ {eur(totBuste)}</span></div>
        <div className="dc-buste-stat dc-buste-stat-green"><span className="dc-buste-stat-label">BONIFICI</span><span className="dc-buste-stat-value">€ {eur(totBonifici)}</span></div>
        <div className="dc-buste-stat dc-buste-stat-cyan"><span className="dc-buste-stat-label">ACCONTI</span><span className="dc-buste-stat-value">€ {eur(totAcconti)}</span></div>
        <div className="dc-buste-stat"><span className="dc-buste-stat-label">DIPENDENTI</span><span className="dc-buste-stat-value">{dipendenti.length}</span></div>
      </div>

      <h3 style={{ margin: "4px 0 10px" }}>✏️ Inserimento / modifica per dipendente <span className="dc-muted" style={{ fontWeight: 400, fontSize: 14 }}>· {mesi[mese - 1]} {anno}</span></h3>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {dipendenti.map(dip => {
          const d = get(dip.id);
          const acc = d.acconti || [];
          return (
            <div key={dip.id} className="dc-card" style={{ padding: 14 }}>
              <div className="dc-busta-row">
                <div className="dc-table-user dc-busta-user">
                  <Avatar nome={dip.nome} cognome={dip.cognome} size="sm" />
                  <span style={{ fontWeight: 600 }}>{dip.cognome ? `${dip.cognome} ${dip.nome || ''}` : dip.nome}</span>
                </div>

                <div className="dc-busta-field">
                  <label style={{ fontSize: 11, color: "#6b7669", fontWeight: 600, display: "flex", gap: 6, alignItems: "center" }}>
                    IMPORTO BUSTA €
                    {d.busta_riconciliata && <span style={{ background: "#e2efe8", color: "#234d3d", border: "1px solid #c2ddd0", borderRadius: 6, padding: "1px 6px", fontSize: 10, fontWeight: 700 }}>✓ riconciliata PDF</span>}
                  </label>
                  <input type="number" step="0.01" value={d.importo_busta} onChange={e => upd(dip.id, { importo_busta: e.target.value })} placeholder="0,00" style={{ ...inp, width: 120 }} />
                </div>

                <div className="dc-busta-field">
                  <label style={{ fontSize: 11, color: "#6b7669", fontWeight: 600, display: "flex", gap: 6, alignItems: "center" }}>
                    BONIFICO
                    {d.bonifico_riconciliato
                      ? <span title={d.bonifico_causale} style={{ background: "#e2efe8", color: "#234d3d", border: "1px solid #c2ddd0", borderRadius: 6, padding: "1px 6px", fontSize: 10, fontWeight: 700 }}>✓ riconciliato PDF</span>
                      : (d.bonifico_pdf ? <span title={d.bonifico_causale} style={{ background: "#f3ead9", color: "#56442d", border: "1px solid #e7d6b9", borderRadius: 6, padding: "1px 6px", fontSize: 10, fontWeight: 700 }}>PDF allegato</span> : null)}
                  </label>
                  <div className="dc-busta-inputs" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 13, cursor: "pointer", whiteSpace: "nowrap" }}>
                      <input type="checkbox" checked={d.bonifico_ricevuto} onChange={e => upd(dip.id, { bonifico_ricevuto: e.target.checked })} />
                      ricevuto
                    </label>
                    <input type="number" step="0.01" value={d.bonifico_importo} onChange={e => upd(dip.id, { bonifico_importo: e.target.value })} placeholder="€" style={{ ...inp, width: 100 }} />
                    <input type="date" value={d.bonifico_data || ""} onChange={e => upd(dip.id, { bonifico_data: e.target.value })} style={{ ...inp, width: 150 }} />
                  </div>
                </div>

                <div className="dc-busta-field dc-busta-acconti">
                  <label style={{ fontSize: 11, color: "#6b7669", fontWeight: 600 }}>ACCONTI (max 3)</label>
                  <div className="dc-busta-inputs" style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                    {acc.map((a, i) => (
                      <div key={i} className="dc-busta-acconto" style={{ display: "flex", alignItems: "center", gap: 4, background: "#f8fafc", border: "1px solid #e5e7eb", borderRadius: 8, padding: "4px 6px" }}>
                        <input type="number" step="0.01" value={a.importo} onChange={e => setAcc(dip.id, i, { importo: e.target.value })} placeholder="€" style={{ ...inp, width: 80, padding: "5px 7px" }} />
                        <input type="date" value={a.data || ""} onChange={e => setAcc(dip.id, i, { data: e.target.value })} style={{ ...inp, width: 140, padding: "5px 7px" }} />
                        <button type="button" onClick={() => delAcc(dip.id, i)} title="Rimuovi acconto" style={{ border: "none", background: "transparent", color: "#d35f4e", cursor: "pointer", fontWeight: 700, fontSize: 16 }}>×</button>
                      </div>
                    ))}
                    {acc.length < 3 && <button type="button" onClick={() => addAcc(dip.id)} style={{ border: "1px dashed #9ca3af", background: "#fff", color: "#5b7a6b", borderRadius: 8, padding: "6px 10px", cursor: "pointer", fontWeight: 600, fontSize: 13 }}>+ acconto</button>}
                  </div>
                </div>

                <button type="button" onClick={() => salva(dip.id)} className="dc-busta-salva" style={{ background: salvato[dip.id] ? "#3d8168" : "#5b7a6b", color: "#fff", border: "none", borderRadius: 10, padding: "10px 16px", fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap" }}>
                  {salvato[dip.id] ? "✓ Salvato" : "Salva"}
                </button>
              </div>
              {(Number(d.acconto_cedolino) > 0 || Number(d.prestito_importo) > 0 || Number(d.tfr_anticipo_importo) > 0) && (
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8, paddingTop: 8, borderTop: "1px dashed #e6e0d4" }}>
                  {Number(d.acconto_cedolino) > 0 && (
                    <span style={{ background: "#e8efe9", color: "#2a4d3a", border: "1px solid #cfe0d4", borderRadius: 8, padding: "3px 10px", fontSize: 12, fontWeight: 700 }}>
                      Acconto dal cedolino: € {eur(d.acconto_cedolino)}{Number(d.saldo_residuo) ? ` · saldo da pagare € ${eur(d.saldo_residuo)}` : ""}
                    </span>
                  )}
                  {Number(d.prestito_importo) > 0 && (
                    <span style={{ background: "#f3ead9", color: "#56442d", border: "1px solid #e7d6b9", borderRadius: 8, padding: "3px 10px", fontSize: 12, fontWeight: 700 }}>
                      Prestito {mesi[mese - 1]}: € {eur(d.prestito_importo)} · saldo € {eur(d.prestito_saldo)}
                    </span>
                  )}
                  {Number(d.tfr_anticipo_importo) > 0 && (
                    <span style={{ background: "#f3ead9", color: "#56442d", border: "1px solid #e7d6b9", borderRadius: 8, padding: "3px 10px", fontSize: 12, fontWeight: 700 }}>
                      Anticipo TFR: € {eur(d.tfr_anticipo_importo)} (fuori dal saldo)
                    </span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Mini-calendario a griglia (mese/anno navigabili) al posto del semplice input data
// nativo del browser — usato nel simulatore TFR per scegliere le date dei periodi.
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

  const btnStyle = { border: "1px solid #d1d5db", borderRadius: 8, padding: "7px 9px", fontSize: 14, width: "100%", boxSizing: "border-box", textAlign: "left", cursor: "pointer", background: "#fff", color: value ? "#2a3329" : "#9aa39a" };

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button type="button" onClick={() => setAperto(a => !a)} style={btnStyle}>
        {value ? formatDate(value) : "Scegli data"}
      </button>
      {aperto && (
        <div style={{ position: "absolute", top: "100%", left: 0, marginTop: 4, background: "#fffefb", border: "1px solid #e6e0d4", borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,.18)", padding: 10, zIndex: 60, width: 232 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <button type="button" className="dc-btn" style={{ padding: "2px 8px" }} onClick={() => cambiaMese(-1)}>‹</button>
            <b style={{ fontSize: 13 }}>{meseNomi[vista.mese]} {vista.anno}</b>
            <button type="button" className="dc-btn" style={{ padding: "2px 8px" }} onClick={() => cambiaMese(1)}>›</button>
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
  const API_TFR = `${HR_API}/tfr`;
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
      const r = await hrApi.post(`${API_TFR}/calcolo-netto-da-lordo`, {
        importo_settimanale_lordo: lordoSett,
        settimane_lavorate: Number(form.settimane),
        mesi_lavorati: Number(form.mesi),
      });
      setNlEsito({ ...r.data, superminimo_mese: Number(String(form.superminimo || "0").replace(",", ".")) || 0, lordo_settimanale_totale: lordoSett });
    } catch (e) { setNlEsito({ errore: e?.response?.data?.message || "Errore nel calcolo" }); }
  };
  // Calcolo inverso: dal NETTO mensile desiderato → lordo settimanale e tutto il resto
  const [lnForm, setLnForm] = useState({ netto: "", settimane: "52", mesi: "12" });
  const [lnEsito, setLnEsito] = useState(null);
  const calcolaLordo = async () => {
    const netto = Number(String(lnForm.netto).replace(",", "."));
    if (!netto) return;
    setLnEsito(null);
    try {
      const r = await hrApi.post(`${API_TFR}/calcolo-lordo-da-netto`, {
        netto_mensile_desiderato: netto,
        settimane_lavorate: Number(lnForm.settimane) || 52,
        mesi_lavorati: Number(lnForm.mesi) || 12,
      });
      setLnEsito(r.data);
    } catch (e) { setLnEsito({ errore: e?.response?.data?.message || "Errore nel calcolo" }); }
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
        hrApi.get(`${API_TFR}/situazione/${id}`),
        hrApi.get(`${API_TFR}/simulazione/${id}`),
      ]);
      setSituazione(s.data);
      setSim(sm.data);
      setFormPeriodo({ data_inizio: sm.data.prossimo_data_inizio || "", data_fine: "", importo_settimanale: "" });
      setComeChiuso(false);
      try {
        const l = await hrApi.get(`${API_TFR}/simulazione/${id}/liquidazione`);
        setLiquidazione(l.data);
      } catch { setLiquidazione(null); }
      try {
        const a = await hrApi.get(`${API_TFR}/acconti/${id}`);
        setAcconti(a.data);
      } catch { setAcconti(null); }
    } catch (e) {
      setErrore(e?.response?.data?.message || "Errore nel caricamento");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { carica(dipId); }, [dipId, carica]);

  const aggiungiPeriodo = async () => {
    if (!formPeriodo.importo_settimanale || (comeChiuso && !formPeriodo.data_fine)) return;
    setSalvandoPeriodo(true); setErrore("");
    try {
      await hrApi.post(`${API_TFR}/simulazione/${dipId}/periodi`, {
        data_inizio: formPeriodo.data_inizio || undefined,
        data_fine: comeChiuso ? formPeriodo.data_fine : undefined,
        importo_settimanale: Number(formPeriodo.importo_settimanale),
      });
      await carica(dipId);
    } catch (e) { setErrore(e?.response?.data?.message || "Errore nel salvataggio del periodo"); }
    finally { setSalvandoPeriodo(false); }
  };

  // Valori manuali della liquidazione (13ª, 14ª, giorni ferie): null = torna al calcolo automatico
  const salvaOverride = async (campo, valore) => {
    try {
      await hrApi.put(`${API_TFR}/simulazione/${dipId}/liquidazione-override`, { [campo]: valore });
      const l = await hrApi.get(`${API_TFR}/simulazione/${dipId}/liquidazione`);
      setLiquidazione(l.data);
    } catch (e) { setErrore(e?.response?.data?.message || "Errore nel salvataggio"); }
  };

  const ricaricaAcconti = async () => {
    try { const a = await hrApi.get(`${API_TFR}/acconti/${dipId}`); setAcconti(a.data); } catch { /* niente */ }
  };
  const registraAcconto = async () => {
    const importo = Number(String(formAcconto.importo).replace(",", "."));
    if (!importo) return;
    try {
      await hrApi.post(`${API_TFR}/acconti`, {
        dipendente_id: dipId, tipo: "tfr", importo,
        data: formAcconto.data || new Date().toISOString().slice(0, 10),
        note: formAcconto.note || "Acconto TFR (dal simulatore)",
      });
      setFormAcconto({ data: "", importo: "", note: "" });
      await ricaricaAcconti();
    } catch (e) { setErrore(e?.response?.data?.message || "Errore nel salvataggio dell'acconto"); }
  };
  const eliminaAcconto = async (accId) => {
    if (!window.confirm("Eliminare questo acconto TFR?")) return;
    try { await hrApi.delete(`${API_TFR}/acconti/${accId}`); await ricaricaAcconti(); }
    catch (e) { setErrore(e?.response?.data?.message || "Errore nell'eliminazione dell'acconto"); }
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
      await hrApi.delete(`${API_TFR}/simulazione/${dipId}/periodi/${periodoId}`);
      await carica(dipId);
    } catch (e) { setErrore(e?.response?.data?.message || "Errore nell'eliminazione"); }
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
      await hrApi.put(`${API_TFR}/simulazione/${dipId}/periodi/${modificaPeriodo.id}`, {
        importo_settimanale: Number(modificaPeriodo.importo_settimanale),
        data_inizio: modificaPeriodo.data_inizio || undefined,
        data_fine: modificaPeriodo.data_fine || undefined,
      });
      setModificaPeriodo(null);
      await carica(dipId);
    } catch (e) { setErrore(e?.response?.data?.message || "Errore nel salvataggio della modifica"); }
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
      await hrApi.put(`${API_TFR}/simulazione/${dipId}/periodi/${periodoId}`, { [campo]: v });
      await carica(dipId);
    } catch (e) { setErrore(e?.response?.data?.message || "Errore nel salvataggio"); }
  };
  const cellaInput = { border: "1px solid #d1d5db", borderRadius: 6, padding: "3px 6px", fontSize: 13.5, width: 84, textAlign: "right", boxSizing: "border-box" };

  // Parametro di calcolo globale (divisore 12/13,5), modificabile qui.
  const [parametri, setParametri] = useState({ divisore: "12" });
  const [salvandoParametri, setSalvandoParametri] = useState(false);
  useEffect(() => {
    hrApi.get(`${API_TFR}/simulazione-parametri`)
      .then(r => setParametri({ divisore: String(r.data.divisore) }))
      .catch(() => {});
  }, []);
  const salvaParametri = async () => {
    setSalvandoParametri(true); setErrore("");
    try {
      await hrApi.put(`${API_TFR}/simulazione-parametri`, {
        divisore: Number(parametri.divisore),
      });
      await carica(dipId);
    } catch (e) { setErrore(e?.response?.data?.message || "Errore nel salvataggio dei parametri"); }
    finally { setSalvandoParametri(false); }
  };

  const calcolaRate = async () => {
    try {
      const r = await hrApi.post(`${API_TFR}/simulazione/${dipId}/rate`, {
        numero_rate: Number(numeroRate),
        data_prima_rata: dataPrimaRata || undefined,
      });
      setRate(r.data);
    } catch (e) { setErrore(e?.response?.data?.message || "Errore nel calcolo delle rate"); }
  };

  const inp = { border: "1px solid #d1d5db", borderRadius: 8, padding: "7px 9px", fontSize: 14, width: "100%", boxSizing: "border-box" };

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
                          <button className="dc-btn" style={{ padding: "2px 8px", fontSize: 12 }} onClick={() => apriModificaPeriodo(p)} title="Correggi le date">✎</button>
                          {i === sim.periodi.length - 1 && (
                            <button className="dc-btn" style={{ padding: "2px 8px", fontSize: 12 }} onClick={() => eliminaUltimoPeriodo(p.id)}>✕</button>
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
        <div onClick={() => setModificaPeriodo(null)} style={{ position: "fixed", inset: 0, background: "rgba(42,51,41,.45)", display: "flex", alignItems: "flex-start", justifyContent: "center", padding: 20, zIndex: 50, overflow: "auto" }}>
          <div onClick={e => e.stopPropagation()} className="dc-card" style={{ maxWidth: 420, width: "100%", marginTop: 60 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>Correggi periodo</h3>
              <button className="dc-btn" onClick={() => setModificaPeriodo(null)}>Chiudi</button>
            </div>
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
        </div>
      )}
    </div>
  );
}

// Cedolini & Bonifici — vista unica associazione busta ↔ bonifico pagato
// URL della cartella Drive con gli originali dei bonifici: da qui si prende
// il documento se durante un controllo serve l'originale, non solo il PDF
// gia' allegato al bonifico in app.
const DRIVE_BONIFICI_URL = "https://drive.google.com/drive/u/1/folders/1yl55742cu9i-AFLxu2s0QnMvXG6kVkJC";

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
      const r = await hrApi.get(`${API}/bonifici-da-associare`);
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
      await hrApi.post(`${API}/bonifici-da-associare/${id}/associa`, {
        dipendente_id: sc.dipendente_id, mese: sc.mese, anno: sc.anno,
      });
      toast("Associato: salvato nella scheda del dipendente con il PDF allegato");
      setRighe(r => r.filter(x => x.id !== id));
    } catch (e) { console.error(e); toast(e?.response?.data?.message || "Errore nell'associazione", "err"); }
    finally { setBusy(null); }
  };

  const ignora = async (id) => {
    if (!window.confirm("Non e' un pagamento a un dipendente? Esce dalla coda senza creare nulla.")) return;
    setBusy(id);
    try {
      await hrApi.post(`${API}/bonifici-da-associare/${id}/ignora`);
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
                    <select className="dc-input" value={sc.dipendente_id || ""} onChange={e => setScelta(b.id, "dipendente_id", e.target.value)} style={{ minWidth: 160 }}>
                      <option value="">— scegli —</option>
                      {dipOrdinati.map(d => <option key={d.id} value={d.id}>{d.nome_completo}</option>)}
                    </select>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 4 }}>
                      <select className="dc-input" value={sc.mese || 1} onChange={e => setScelta(b.id, "mese", Number(e.target.value))} style={{ width: 100 }}>
                        {mesi.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
                      </select>
                      <input type="number" className="dc-input" value={sc.anno || new Date().getFullYear()}
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

function PagheBonificiPage() {
  const mesi = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno","Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"];
  const annoCorr = new Date().getFullYear();
  const [anno, setAnno] = useState(annoCorr);
  const [mese, setMese] = useState(0); // 0 = tutto l'anno
  const [filtroStato, setFiltroStato] = useState("");
  const [data, setData] = useState({ righe: [], totali: {}, count: 0 });
  const [loading, setLoading] = useState(false);
  const [aperta, setAperta] = useState(null); // chiave riga espansa
  const [busy, setBusy] = useState(null);
  const [importBusy, setImportBusy] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [syncBusy, setSyncBusy] = useState(false);
  const [cedSyncBusy, setCedSyncBusy] = useState(false);

  const eur = (n) => (Number(n) || 0).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const keyOf = (r) => `${r.dipendente_id}_${r.anno}_${r.mese}`;

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (anno) params.set("anno", anno);
      if (mese) params.set("mese", mese);
      if (filtroStato) params.set("stato", filtroStato);
      const r = await hrApi.get(`${API}/paghe/associazioni-bonifici?${params.toString()}`);
      setData(r.data || { righe: [], totali: {}, count: 0 });
    } catch (e) {
      console.error(e);
      setData({ righe: [], totali: {}, count: 0 });
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [anno, mese, filtroStato]);

  const conferma = async (r, val) => {
    setBusy(keyOf(r));
    try {
      await hrApi.post(`${API}/paghe/conferma-associazione`, {
        dipendente_id: r.dipendente_id, anno: r.anno, mese: r.mese, riconciliato: val,
      });
      await load();
    } catch (e) { toast(e?.response?.data?.message || "Errore conferma", "err"); }
    finally { setBusy(null); }
  };

  const [importProgress, setImportProgress] = useState(null);
  const importaDaDrive = async () => {
    setImportBusy(true);
    setImportProgress(null);
    // La cartella Drive può avere centinaia di PDF (non solo stipendi): il
    // backend processa un lotto per chiamata (mai visti prima, tracciati per
    // id Drive) e dice quanti ne restano. Si richiama in automatico finché
    // non ne restano più, con un tetto di sicurezza sui giri.
    const tot = { importati: 0, in_coda_da_associare: 0, duplicati: 0, esclusi_non_stipendio: 0 };
    try {
      for (let giro = 0; giro < 30; giro++) {
        const r = await hrApi.post(`${API}/paghe/importa-bonifici-drive`, {});
        const d = r.data || {};
        for (const k of Object.keys(tot)) tot[k] += d[k] || 0;
        setImportProgress({ lavorati: (d.trovati_totale || 0) - (d.restanti || 0), totale: d.trovati_totale || 0 });
        if (!d.restanti) break;
      }
      toast(`Bonifici Drive: ${tot.importati} associati, ${tot.in_coda_da_associare} da associare a mano, ${tot.esclusi_non_stipendio} esclusi (non stipendio), ${tot.duplicati} già importati`);
      await load();
    } catch (e) { toast(e?.response?.data?.message || "Errore import da Drive", "err"); }
    finally { setImportBusy(false); setImportProgress(null); }
  };

  const recuperaStorici = async () => {
    setSyncBusy(true);
    try {
      const r = await hrApi.post(`${API}/paghe/sincronizza-bonifici-storici`, {});
      const d = r.data || {};
      toast(`Bonifici storici collegati: ${d.importati_in_pagamenti_esiti || 0} su ${d.mesi_aggiornati || 0} mesi aggiornati`);
      await load();
    } catch (e) { toast(e?.response?.data?.message || "Errore sincronizzazione", "err"); }
    finally { setSyncBusy(false); }
  };

  const sincronizzaDaCedolini = async () => {
    setCedSyncBusy(true);
    try {
      const r = await hrApi.post(`${API}/paghe/sincronizza`, {});
      const d = r.data || {};
      toast(`Registro paghe popolato dai cedolini: ${d.creati || 0} nuovi, ${d.aggiornati || 0} aggiornati, ${d.saltati_manuali || 0} lasciati (già modificati a mano)`);
      await load();
    } catch (e) { toast(e?.response?.data?.message || "Errore sincronizzazione dai cedolini", "err"); }
    finally { setCedSyncBusy(false); }
  };

  const esportaExcel = async () => {
    setExportBusy(true);
    try {
      const params = new URLSearchParams();
      if (anno) params.set("anno", anno);
      if (mese) params.set("mese", mese);
      if (filtroStato) params.set("stato", filtroStato);
      const r = await hrApi.get(`${API}/paghe/associazioni-bonifici/export-excel?${params.toString()}`, { responseType: "blob" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(r.data);
      a.download = `cedolini_bonifici${anno ? `_${anno}` : ""}${mese ? `_${String(mese).padStart(2, '0')}` : ""}.xlsx`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 10000);
    } catch (e) { toast("Errore generazione Excel", "err"); }
    finally { setExportBusy(false); }
  };

  const t = data.totali || {};
  const STATI = {
    pagato: { label: "✓ Pagato", variant: "success" },
    parziale: { label: "Parziale", variant: "warning" },
    da_pagare: { label: "Da pagare", variant: "danger" },
    bonifico_senza_busta: { label: "Bonifico senza busta", variant: "info" },
  };
  const QUALITA = {
    esatto: { txt: "Match esatto", col: "#234d3d", bg: "#e2efe8", bd: "#c2ddd0" },
    per_importo: { txt: "Match per importo", col: "#234d3d", bg: "#e2efe8", bd: "#c2ddd0" },
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

  return (
    <div style={{ maxWidth: 1280 }}>
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0, color: "#2a3329" }}>Cedolini &amp; Bonifici</h2>
          <p className="dc-muted" style={{ marginTop: 4 }}>
            Per ogni busta vedi se il <b>bonifico è stato effettuato</b> e a quale cedolino è associato.
            Dati dal sistema unico paghe (busta) + pagamenti reali della banca (bonifici).
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="dc-btn" disabled={cedSyncBusy} onClick={sincronizzaDaCedolini} title="Popola questo registro dai cedolini in archivio (senza questo passo la tabella resta vuota anche con le buste già caricate)">
            {cedSyncBusy ? "Sincronizzo…" : "🔄 Sincronizza da cedolini"}
          </button>
          <button className="dc-btn" disabled={syncBusy} onClick={recuperaStorici} title="Collega alla busta i bonifici storici già archiviati (PDF già letti in passato) ma non ancora agganciati qui">
            {syncBusy ? "Collego…" : "🔗 Recupera bonifici storici"}
          </button>
          <button className="dc-btn" disabled={importBusy} onClick={importaDaDrive} title="Legge i PDF nuovi dalla cartella Drive bonifici e li abbina ai cedolini">
            {importBusy
              ? (importProgress ? `Importo… ${importProgress.lavorati}/${importProgress.totale}` : "Importo…")
              : "📥 Importa bonifici da Drive"}
          </button>
          <button className="dc-btn" disabled={exportBusy} onClick={esportaExcel}>
            {exportBusy ? "Esporto…" : "📊 Esporta Excel"}
          </button>
          <a href={DRIVE_BONIFICI_URL} target="_blank" rel="noreferrer" className="dc-btn" title="Cartella Drive con gli originali dei bonifici">
            📁 Cartella Drive bonifici
          </a>
        </div>
      </div>

      {/* Filtri */}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 16 }}>
        <select style={sel} value={anno} onChange={e => setAnno(Number(e.target.value))}>
          {Array.from({ length: 8 }, (_, i) => annoCorr - i).map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <select style={sel} value={mese} onChange={e => setMese(Number(e.target.value))}>
          <option value={0}>Tutto l'anno</option>
          {mesi.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
        </select>
        <select style={sel} value={filtroStato} onChange={e => setFiltroStato(e.target.value)}>
          <option value="">Tutti gli stati</option>
          <option value="pagato">Pagati</option>
          <option value="parziale">Parziali</option>
          <option value="da_pagare">Da pagare</option>
          <option value="bonifico_senza_busta">Bonifico senza busta</option>
        </select>
        <button className="dc-btn" onClick={load} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <RefreshCw size={15} /> Aggiorna
        </button>
      </div>

      {/* Riepilogo */}
      <div style={cardWrap}>
        <div style={card}><div style={lbl}>Totale buste</div><div style={val}>€ {eur(t.buste)}</div></div>
        <div style={card}><div style={lbl}>Bonifici</div><div style={{ ...val, color: "#3d8168" }}>€ {eur(t.bonifici)}</div></div>
        <div style={card}><div style={lbl}>Saldo da pagare</div><div style={{ ...val, color: (t.saldo > 0.5 ? "#b04a3a" : "#3d8168") }}>€ {eur(t.saldo)}</div></div>
        <div style={card}><div style={lbl}>Pagati</div><div style={{ ...val, color: "#3d8168" }}>{t.pagati || 0}</div></div>
        <div style={card}><div style={lbl}>Da pagare</div><div style={{ ...val, color: "#b04a3a" }}>{t.da_pagare || 0}</div></div>
        <div style={card}><div style={lbl}>Da verificare</div><div style={{ ...val, color: "#7a3b32" }}>{t.da_verificare || 0}</div></div>
      </div>

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
                <th style={{ ...th, textAlign: "right" }}>Saldo</th>
                <th style={th}>Stato</th>
                <th style={th}>Associazione</th>
                <th style={th}>Cedolino</th>
                <th style={th}></th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td style={td} colSpan={9}>Caricamento…</td></tr>}
              {!loading && data.righe.length === 0 && <tr><td style={td} colSpan={9}>Nessuna busta per il periodo selezionato.</td></tr>}
              {!loading && data.righe.map(r => {
                const k = keyOf(r);
                const exp = aperta === k;
                const stInfo = STATI[r.stato] || { label: r.stato, variant: "default" };
                const qInfo = r.qualita ? QUALITA[r.qualita] : null;
                const periodoLbl = (r.mese >= 1 && r.mese <= 12) ? `${mesi[r.mese - 1]} ${r.anno}` : `${r.mese}/${r.anno}`;
                return (
                  <Fragment key={k}>
                    <tr style={{ background: exp ? "#f7f4ec" : "transparent" }}>
                      <td style={{ ...td, fontWeight: 600 }}>{r.dipendente}</td>
                      <td style={td}>{periodoLbl}</td>
                      <td style={{ ...td, textAlign: "right" }}>{r.busta > 0 ? `€ ${eur(r.busta)}` : "—"}</td>
                      <td style={{ ...td, textAlign: "right", color: r.bonifico > 0 ? "#3d8168" : "#9aa295", fontWeight: 600 }}>
                        {r.bonifico > 0 ? `€ ${eur(r.bonifico)}` : "—"}
                        {r.fonte && <div style={{ fontSize: 10, color: "#9aa295", fontWeight: 400 }}>{FONTI[r.fonte] || r.fonte}</div>}
                      </td>
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
                        {r.cedolino_pdf
                          ? <span style={{ color: "#234d3d", fontSize: 12, fontWeight: 600 }}>PDF ✓</span>
                          : <span style={{ color: "#9aa295", fontSize: 12 }}>no PDF</span>}
                      </td>
                      <td style={{ ...td, whiteSpace: "nowrap" }}>
                        {(r.n_bonifici > 0) && (
                          <button className="dc-btn" onClick={() => setAperta(exp ? null : k)} style={{ fontSize: 12, padding: "4px 8px" }}>
                            {exp ? "Nascondi" : `Dettagli (${r.n_bonifici})`}
                          </button>
                        )}
                        {(r.bonifico > 0 || r.stato === "bonifico_senza_busta") && (
                          r.riconciliato
                            ? <button className="dc-btn" disabled={busy === k} onClick={() => conferma(r, false)} style={{ fontSize: 12, padding: "4px 8px", marginLeft: 6 }}>Annulla</button>
                            : <button className="dc-btn" disabled={busy === k} onClick={() => conferma(r, true)} style={{ fontSize: 12, padding: "4px 8px", marginLeft: 6 }}>Conferma</button>
                        )}
                      </td>
                    </tr>
                    {exp && r.bonifici.length > 0 && (
                      <tr>
                        <td style={{ ...td, background: "#f7f4ec" }} colSpan={9}>
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
                              </tr>
                            </thead>
                            <tbody>
                              {r.bonifici.map((b, i) => (
                                <tr key={i}>
                                  <td style={{ ...td, borderBottom: "none" }}>{b.data || "—"}</td>
                                  <td style={{ ...td, borderBottom: "none", textAlign: "right", color: "#3d8168", fontWeight: 600 }}>€ {eur(b.importo)}</td>
                                  <td style={{ ...td, borderBottom: "none", fontSize: 13 }}>{b.causale || "—"}</td>
                                  <td style={{ ...td, borderBottom: "none", fontSize: 13 }}>{b.beneficiario || "—"}</td>
                                  <td style={{ ...td, borderBottom: "none", fontSize: 12, color: "#7a8576" }}>{b.riferimento || "—"}</td>
                                  <td style={{ ...td, borderBottom: "none", fontSize: 12 }}>
                                    {b.pdf_key
                                      ? <a href={`${API}/paghe/pagamento-esito/${b.pdf_key}/pdf`} target="_blank" rel="noreferrer" style={{ color: "#3d8168", fontWeight: 600 }}>📄 Apri PDF</a>
                                      : <span style={{ color: "#9aa295" }}>no PDF</span>}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
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
      <p className="dc-muted" style={{ fontSize: 12, marginTop: 10 }}>
        <b>Match esatto/per importo</b> = il bonifico combacia con la busta. <b>Da verificare</b> = importo presente senza prova bancaria (inserito a mano o da prima nota): controlla e premi <b>Conferma</b> per associarlo definitivamente al cedolino.
      </p>
    </div>
  );
}

// Missioni Page
function MissioniPage({ dipendenti, missioni, reload, getDipendente }) {
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState({
    dipendente_id: "", destinazione: "", data_inizio: "", data_fine: "", scopo: "", rimborso: 0
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    await hrApi.post(`${API}/missioni`, formData);
    setShowModal(false);
    reload();
  };

  const handleApprova = async (id) => {
    await hrApi.put(`${API}/missioni/${id}/approva`);
    reload();
  };

  return (
    <div className="dc-page">
      <div className="dc-page-header">
        <div>
          <h1>Missioni & Trasferte</h1>
          <p>Gestione missioni e trasferte dipendenti</p>
        </div>
        <button onClick={() => setShowModal(true)} className="dc-btn dc-btn-primary">
          <Plus size={18} /> Nuova Missione
        </button>
      </div>

      <div className="dc-card">
        <table className="dc-table dc-table--cards">
          <thead>
            <tr>
              <th>DIPENDENTE</th>
              <th>DESTINAZIONE</th>
              <th>PERIODO</th>
              <th>RIMBORSO</th>
              <th>STATO</th>
              <th>AZIONI</th>
            </tr>
          </thead>
          <tbody>
            {missioni.map((m) => {
              const dip = getDipendente(m.dipendente_id);
              return (
                <tr key={m.id}>
                  <td>
                    <div className="dc-table-user">
                      <Avatar nome={dip?.nome} cognome={dip?.cognome} size="sm" />
                      <span>{dip?.nome} {dip?.cognome}</span>
                    </div>
                  </td>
                  <td data-label="Destinazione">{m.destinazione}</td>
                  <td data-label="Periodo">{formatDate(m.data_inizio)} - {formatDate(m.data_fine)}</td>
                  <td data-label="Rimborso">€ {m.rimborso?.toFixed(2)}</td>
                  <td data-label="Stato"><Badge variant={m.stato === 'approvata' ? 'success' : 'warning'}>{m.stato}</Badge></td>
                  <td data-label="Azioni" className="dc-table-actions">
                    {m.stato === 'in_attesa' && (
                      <button onClick={() => handleApprova(m.id)} className="dc-btn-icon dc-btn-success"><Check size={16} /></button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {showModal && (
        <div className="dc-modal-overlay" onClick={() => setShowModal(false)}>
          <div className="dc-modal" onClick={e => e.stopPropagation()}>
            <div className="dc-modal-header">
              <h3>Nuova Missione</h3>
              <button onClick={() => setShowModal(false)} className="dc-modal-close"><X size={20} /></button>
            </div>
            <form onSubmit={handleSubmit} className="dc-modal-body">
              <div className="dc-form-group">
                <label>Dipendente *</label>
                <select required value={formData.dipendente_id} onChange={e => setFormData({...formData, dipendente_id: e.target.value})}>
                  <option value="">Seleziona...</option>
                  {dipendenti.map(d => <option key={d.id} value={d.id}>{d.nome} {d.cognome}</option>)}
                </select>
              </div>
              <div className="dc-form-group">
                <label>Destinazione *</label>
                <input required value={formData.destinazione} onChange={e => setFormData({...formData, destinazione: e.target.value})} />
              </div>
              <div className="dc-form-row">
                <div className="dc-form-group">
                  <label>Data Inizio</label>
                  <input type="date" required value={formData.data_inizio} onChange={e => setFormData({...formData, data_inizio: e.target.value})} />
                </div>
                <div className="dc-form-group">
                  <label>Data Fine</label>
                  <input type="date" required value={formData.data_fine} onChange={e => setFormData({...formData, data_fine: e.target.value})} />
                </div>
              </div>
              <div className="dc-form-group">
                <label>Scopo</label>
                <input value={formData.scopo} onChange={e => setFormData({...formData, scopo: e.target.value})} />
              </div>
              <div className="dc-form-group">
                <label>Rimborso €</label>
                <input type="number" min="0" value={formData.rimborso} onChange={e => setFormData({...formData, rimborso: +e.target.value})} />
              </div>
              <div className="dc-modal-footer">
                <button type="button" onClick={() => setShowModal(false)} className="dc-btn">Annulla</button>
                <button type="submit" className="dc-btn dc-btn-primary">Crea Missione</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

// Documenti Page
function DocumentiPage({ dipendenti, documenti, reload, getDipendente }) {
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState({
    dipendente_id: "", titolo: "", tipo: "Contratto", scadenza: ""
  });
  const massRef = useRef(null);
  const [massBusy, setMassBusy] = useState(false);
  const [massMsg, setMassMsg] = useState(null);
  const ETICHETTA = { UNILAV: "Unilav", CERTIFICAZIONE_UNICA: "Certificazione Unica (CU)", CONTRATTO: "Contratti", BONIFICO: "Bonifici", CODICE_FISCALE: "Codice fiscale / Tessera sanitaria", CARTA_IDENTITA: "Carta d'identità", BUSTA_PAGA: "Buste paga", ALTRO: "Da classificare" };

  const handleSubmit = async (e) => {
    e.preventDefault();
    await hrApi.post(`${API}/documenti`, formData);
    setShowModal(false);
    reload();
  };

  const handleMassUpload = async (e) => {
    const fs = Array.from(e.target.files || []);
    if (!fs.length) return;
    setMassBusy(true); setMassMsg(null);
    try {
      const fd = new FormData();
      fs.forEach(f => fd.append("files", f));
      const r = await hrApi.post(`${API}/documenti/upload-massivo`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setMassMsg(r.data);
      reload();
    } catch (err) {
      setMassMsg({ errore: err?.response?.data?.message || "Errore upload" });
    } finally {
      setMassBusy(false);
      if (massRef.current) massRef.current.value = "";
    }
  };

  const importaGmail = async () => {
    if (!window.confirm("Cercare i documenti negli allegati della posta (Gmail) e archiviarli nelle cartelle dei dipendenti?")) return;
    setMassBusy(true); setMassMsg(null);
    try {
      const r = await hrApi.post(`${API}/paghe/importa-email`);
      const doc = r.data.documenti || { caricati: 0, non_assegnati: 0, duplicati: 0 };
      setMassMsg({ caricati: doc.caricati, duplicati: Array(doc.duplicati || 0).fill(0), non_assegnati: Array(doc.non_assegnati || 0).fill(0), dettaglio: [], _gmail: true });
      reload();
      toast(`Da Gmail: ${doc.caricati} documenti archiviati`);
    } catch (err) {
      setMassMsg({ errore: err?.response?.data?.message || "Errore import Gmail (controlla IMAP_HOST/USER/PASSWORD su Render)" });
    } finally { setMassBusy(false); }
  };

  const apriDoc = async (doc) => {
    try {
      const r = await hrApi.get(`${API}/documenti/${doc.id}/file`, { responseType: "blob" });
      window.open(URL.createObjectURL(r.data), "_blank");
    } catch { toast("Impossibile aprire il documento (file non disponibile).", "err"); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Eliminare questo documento?")) return;
    await hrApi.delete(`${API}/documenti/${id}`);
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
                        {doc.file_data || doc.hash ? <button onClick={() => apriDoc(doc)} className="dc-btn" style={{ padding: "4px 10px" }}>Apri</button> : null}
                        <button onClick={() => handleDelete(doc.id)} className="dc-btn-icon dc-btn-danger" style={{ marginLeft: 6 }}><Trash2 size={16} /></button>
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
        <div className="dc-modal-overlay" onClick={() => setShowModal(false)}>
          <div className="dc-modal" onClick={e => e.stopPropagation()}>
            <div className="dc-modal-header">
              <h3>Nuovo Documento</h3>
              <button onClick={() => setShowModal(false)} className="dc-modal-close"><X size={20} /></button>
            </div>
            <form onSubmit={handleSubmit} className="dc-modal-body">
              <div className="dc-form-group">
                <label>Dipendente *</label>
                <select required value={formData.dipendente_id} onChange={e => setFormData({...formData, dipendente_id: e.target.value})}>
                  <option value="">Seleziona...</option>
                  {dipendenti.map(d => <option key={d.id} value={d.id}>{d.nome} {d.cognome}</option>)}
                </select>
              </div>
              <div className="dc-form-group">
                <label>Titolo *</label>
                <input required value={formData.titolo} onChange={e => setFormData({...formData, titolo: e.target.value})} />
              </div>
              <div className="dc-form-group">
                <label>Tipo</label>
                <select value={formData.tipo} onChange={e => setFormData({...formData, tipo: e.target.value})}>
                  <option>Contratto</option>
                  <option>CUD</option>
                  <option>Certificato</option>
                  <option>Altro</option>
                </select>
              </div>
              <div className="dc-form-group">
                <label>Scadenza</label>
                <input type="date" value={formData.scadenza} onChange={e => setFormData({...formData, scadenza: e.target.value})} />
              </div>
              <div className="dc-modal-footer">
                <button type="button" onClick={() => setShowModal(false)} className="dc-btn">Annulla</button>
                <button type="submit" className="dc-btn dc-btn-primary">Salva Documento</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

// ===== Assunzione & Contratti =====
function AssunzionePage({ dipendenti, reload }) {
  const C = `${HR_API}/contracts`;
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

  const loadTemplates = () => hrApi.get(`${C}/templates`).then(r => setTemplates(r.data || [])).catch(() => {});
  useEffect(() => {
    hrApi.get(`${C}/types`).then(r => { setTipi(r.data || []); if (r.data?.[0]) setTipo(r.data[0].id); }).catch(() => {});
    hrApi.get(`${C}/ccnl`).then(r => {
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
      const r = await hrApi.get(`${C}/ccnl/${ccnlSel}/livello/${encodeURIComponent(livello)}`,
        { params: { ore_settimanali: ore } });
      setCcnlCalc(r.data);
      set("livello", r.data.livello);
      set("stipendio_orario", String(r.data.oraria).replace(".", ","));
      if (r.data.periodo_prova) set("periodo_prova", r.data.periodo_prova);
      if (r.data.ferie_giorni) set("ferie_giorni", String(r.data.ferie_giorni));
    } catch (e) {
      setCcnlCalc(null);
      setCcnlErr(e?.response?.data?.message || "Livello non calcolabile");
    }
  };

  // Paga -> livello: dall'importo che si vuole riconoscere, il livello coerente.
  const suggerisciLivello = async () => {
    setCcnlErr(""); setCcnlCalc(null);
    try {
      const r = await hrApi.post(`${C}/ccnl/suggerisci`, {
        importo_mensile: String(ccnlTarget).replace(",", "."),
        ccnl: ccnlSel,
        ore_settimanali: extra.ore_settimanali || 40,
      });
      setCcnlSugg(r.data);
    } catch (e) {
      setCcnlSugg(null);
      setCcnlErr(e?.response?.data?.message || "Importo non valutabile");
    }
  };

  const loadContratti = (id) => { if (id) hrApi.get(`${C}/employee/${id}`).then(r => setContratti(r.data || [])).catch(() => setContratti([])); else setContratti([]); };
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
    try { await hrApi.post(`${C}/template/${tid}`, fd, { headers: { "Content-Type": "multipart/form-data" } }); await loadTemplates(); setMsg("Template caricato."); }
    catch (e) { setMsg(e?.response?.data?.message || "Errore caricamento template"); }
    setBusy(""); ev.target.value = "";
  };
  const genera = async () => {
    if (!dipId || !tipo) { setMsg("Seleziona dipendente e tipo contratto."); return; }
    if (!dispTemplate(tipo)) { setMsg("Carica prima il template di questo tipo."); return; }
    setBusy("gen"); setMsg("");
    try {
      const r = await hrApi.post(`${C}/generate/${dipId}`, { contract_type: tipo, additional_data: extra });
      const m = r.data?.stipendio_mensile;
      setMsg(m != null ? `Contratto generato. Lordo mensile teorico: € ${Number(m).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}.` : "Contratto generato.");
      const acc = (r.data?.accessori_mancanti || []);
      const note = m != null ? ` Lordo mensile: € ${Number(m).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}.` : "";
      const warn = acc.length ? ` ⚠ Template accessori mancanti: ${acc.join(", ")}.` : " Generati anche regolamento, privacy e informativa.";
      setMsg(`Contratto generato.${note}${warn}`);
      loadContratti(dipId);
    } catch (e) { setMsg(e?.response?.data?.message || "Errore generazione"); }
    setBusy("");
  };
  const generaMassivo = async () => {
    if (!window.confirm("Genero i contratti (bozze) per tutti i dipendenti in forza, deducendo tipo e dati dalle buste paga? Chi ha già un contratto viene saltato. Nessun invio.")) return;
    setBusy("bulk"); setMsg(""); setBulkRes(null);
    try {
      const r = await hrApi.post(`${C}/genera-massivo`, {});
      setBulkRes(r.data);
      setMsg(`Generati ${r.data.generati}, saltati ${r.data.saltati}.`);
      reload && reload();
    } catch (e) { setMsg(e?.response?.data?.message || "Errore generazione massiva"); }
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
      const cr = await hrApi.post(`${API}/dipendenti`, dipPayload);
      const newId = cr.data?.id || cr.data?.dipendente?.id || cr.data?._id;
      if (!newId) throw new Error("ID nuovo dipendente non disponibile");
      const additional = {
        indirizzo: nuovo.indirizzo, luogo_nascita: nuovo.luogo_nascita, data_nascita: nuovo.data_nascita,
        codice_fiscale: nuovo.codice_fiscale, mansione: nuovo.mansione, qualifica: nuovo.qualifica || nuovo.mansione,
        livello: nuovo.livello, stipendio_orario: nuovo.stipendio_orario, ore_settimanali: nuovo.ore_settimanali,
        periodo_prova: nuovo.periodo_prova, ferie_giorni: nuovo.ferie_giorni,
        data_inizio: nuovo.data_assunzione, data_fine: nuovo.data_fine,
      };
      const gr = await hrApi.post(`${C}/generate/${newId}`, { contract_type: nuovo.contract_type, additional_data: additional });
      const acc = (gr.data?.accessori_mancanti || []);
      setShowAssumi(false); setNuovo(NUOVO0);
      setMsg(`Dipendente assunto e contratto generato.${acc.length ? ` ⚠ Template accessori mancanti: ${acc.join(", ")}.` : " Con regolamento, privacy e informativa."}`);
      reload && reload();
    } catch (e) { setMsg(e?.response?.data?.message || e.message || "Errore in fase di assunzione"); }
    setBusy("");
  };
  const scarica = async (cid, fname) => {
    try { const r = await hrApi.get(`${C}/download/${cid}`, { responseType: "blob" });
      const url = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = url; a.download = fname || "contratto.docx"; a.click(); URL.revokeObjectURL(url);
    } catch { setMsg("Download non disponibile"); }
  };
  const invia = async (cid) => {
    setBusy("send-" + cid); setMsg("");
    try { const r = await hrApi.post(`${C}/send/${cid}`, {});
      const miss = (r.data.accessori_mancanti || []);
      const avviso = miss.length ? ` ⚠ Non ancora generati per questo dipendente: ${miss.join(", ")}.` : "";
      setMsg(`Inviato a ${r.data.inviato_a}: ${(r.data.documenti || []).join(", ")}.${avviso}`); loadContratti(dipId);
    } catch (e) { setMsg(e?.response?.data?.message || "Errore invio email"); }
    setBusy("");
  };
  const caricaFirmato = async (cid, ev) => {
    const file = ev.target.files?.[0]; if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    setBusy("cf-" + cid); setMsg("");
    try { await hrApi.post(`${C}/carica-firmato/${cid}`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setMsg("Contratto firmato dal dipendente caricato. Ora controfirma e invia il definitivo."); loadContratti(dipId);
    } catch (e) { setMsg(e?.response?.data?.message || "Errore caricamento firmato"); }
    setBusy(""); ev.target.value = "";
  };
  const finalizza = async (cid, ev) => {
    const file = ev?.target?.files?.[0];
    if (!file && !window.confirm("Finalizzare usando il PDF firmato dal dipendente come definitivo (senza un file controfirmato separato)?")) return;
    const fd = new FormData(); if (file) fd.append("file", file);
    setBusy("fz-" + cid); setMsg("");
    try { const r = await hrApi.post(`${C}/finalizza/${cid}`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      const dest = (r.data.inviato_a || []).join(", ");
      setMsg(`Contratto definitivo archiviato nel fascicolo${dest ? ` e inviato a ${dest}` : ""}.`); loadContratti(dipId); reload && reload();
    } catch (e) { setMsg(e?.response?.data?.message || "Errore finalizzazione"); }
    setBusy(""); if (ev?.target) ev.target.value = "";
  };
  const scaricaPdf = async (cid, versione) => {
    try { const r = await hrApi.get(`${C}/pdf/${cid}/${versione}`, { responseType: "blob" });
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
        <div onClick={() => setShowAssumi(false)} style={{ position: "fixed", inset: 0, background: "rgba(42,51,41,.45)", display: "flex", alignItems: "flex-start", justifyContent: "center", padding: 20, zIndex: 50, overflow: "auto" }}>
          <div onClick={e => e.stopPropagation()} className="dc-card" style={{ maxWidth: 720, width: "100%", marginTop: 20 }}>
            <h3 style={{ marginTop: 0 }}>Assumi dipendente</h3>
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
        </div>
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
  const T = `${HR_API}/timbrature`;
  const [sede, setSede] = useState({ nome: "Ceraldi Caffè", indirizzo: "Piazza Carità, 14 — 80134 Napoli", lat: 40.842949, lng: 14.2489, raggio_m: 200, blocca_fuori_sede: true });
  const [data, setData] = useState(new Date().toISOString().slice(0, 10));
  const [timb, setTimb] = useState([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState("");
  const [sedeOk, setSedeOk] = useState(null); // true = sede salvata sul server (geofencing attivo)

  useEffect(() => { hrApi.get(`${T}/sede`).then(r => { const ok = !!(r.data && r.data.lat != null); setSedeOk(ok); if (ok) setSede(s => ({ ...s, ...r.data })); }).catch(() => setSedeOk(false)); }, []);
  const loadTimb = () => hrApi.get(`${T}?data=${data}`).then(r => setTimb(r.data.timbrature || [])).catch(() => setTimb([]));
  useEffect(() => { loadTimb(); }, [data]);

  // Turni pianificati per il giorno selezionato (stessi endpoint della pagina Presenze)
  const [tipiTurno, setTipiTurno] = useState([]);
  const [assegn, setAssegn] = useState([]);
  const NOMI_G = ["Domenica", "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato"];
  const lunISOdi = (ymd) => { const d = new Date(ymd + "T12:00:00"); const off = (d.getDay() + 6) % 7; d.setDate(d.getDate() - off); return d.toISOString().slice(0, 10); };
  const giornoNomeDi = (ymd) => NOMI_G[new Date(ymd + "T12:00:00").getDay()];
  useEffect(() => { hrApi.get("/api/hr/dipendenti-cloud/turni").then(r => setTipiTurno(r.data || [])).catch(() => {}); }, []);
  useEffect(() => { hrApi.get(`/api/hr/dipendenti-cloud/assegnazioni-turni?settimana=${lunISOdi(data)}`).then(r => setAssegn(r.data || [])).catch(() => setAssegn([])); }, [data]);
  const [riepilogo, setRiepilogo] = useState([]);
  useEffect(() => {
    const [a, m] = data.split("-");
    hrApi.get(`${T}/riepilogo?anno=${a}&mese=${parseInt(m)}`).then(r => setRiepilogo(r.data.riepilogo || [])).catch(() => setRiepilogo([]));
  }, [data]);
  const nomeTurno = (id) => (tipiTurno.find(t => t.id === id) || {}).nome;
  const pianificatoDi = (dipId) => {
    const a = assegn.find(x => x.dipendente_id === dipId && x.settimana === lunISOdi(data) && x.giorno === giornoNomeDi(data));
    return a ? (nomeTurno(a.turno_id) || null) : null;
  };
  const lavorativo = (n) => n && !["Riposo", "Ferie"].includes(n);

  const salvaSede = async () => {
    setBusy("sede"); setMsg("");
    try { await hrApi.post(`${T}/sede`, { ...sede, lat: parseFloat(sede.lat), lng: parseFloat(sede.lng), raggio_m: parseInt(sede.raggio_m) || 200 });
      setSedeOk(true); setMsg("Sede salvata."); } catch (e) { setMsg(e?.response?.data?.message || "Errore salvataggio sede"); }
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


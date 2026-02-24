/**
 * HR Gestionale - Modulo Risorse Umane
 * 
 * Funzionalità:
 * - Dashboard HR con KPI
 * - Anagrafica dipendenti (da database)
 * - Presenze (usa Attendance.jsx esistente)
 * - Ferie & Permessi
 * - Missioni & Trasferte
 */

import { useState, useEffect, useCallback, lazy, Suspense } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { PageLayout } from "../components/PageLayout";
import { Users, Calendar, Plane, Clock, FileText, DollarSign, UserPlus, LayoutGrid, RefreshCw, Plus, Search, Edit2, Trash2, Check, X, ChevronLeft, ChevronRight, Loader2, ExternalLink, Car, Wallet } from "lucide-react";
import api from "../api";
import { toast } from 'sonner';
import { formatEuro, formatDateIT } from '../lib/utils';

// Lazy load del componente Attendance esistente
const Attendance = lazy(() => import("./Attendance"));

// ── HELPERS ──────────────────────────────────────────────────────────────────
const fmt = d => {
  if (!d) return "-";
  try {
    const [y, m, g] = d.split("-");
    return `${g}/${m}/${y}`;
  } catch {
    return d;
  }
};

const COLORS_AVATAR = ["#6366f1","#10b981","#f59e0b","#ef4444","#3b82f6","#8b5cf6","#ec4899"];
const avatarColor = (id) => COLORS_AVATAR[Math.abs(hashCode(id || '')) % COLORS_AVATAR.length];
const hashCode = (s) => s.split('').reduce((a,b) => { a = ((a << 5) - a) + b.charCodeAt(0); return a & a }, 0);
const initials = (n, c) => {
  const nome = n || '';
  const cognome = c || '';
  return `${nome[0] || '?'}${cognome[0] || '?'}`.toUpperCase();
};

const BADGE_STYLES = {
  approvata: { bg: "rgba(16,185,129,0.12)", color: "#10b981" },
  "in attesa": { bg: "rgba(245,158,11,0.12)", color: "#f59e0b" },
  rifiutato: { bg: "rgba(239,68,68,0.12)", color: "#ef4444" },
  presente: { bg: "rgba(16,185,129,0.12)", color: "#10b981" },
  assente: { bg: "rgba(239,68,68,0.12)", color: "#ef4444" },
  attivo: { bg: "rgba(16,185,129,0.12)", color: "#10b981" },
  cessato: { bg: "rgba(239,68,68,0.12)", color: "#ef4444" },
};

// ── COMPONENTS ──────────────────────────────────────────────────────────────
function Badge({ stato }) {
  const style = BADGE_STYLES[stato?.toLowerCase()] || { bg: "rgba(100,116,139,0.15)", color: "#64748b" };
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 4,
      padding: "3px 10px",
      borderRadius: 20,
      fontSize: 11,
      fontWeight: 600,
      background: style.bg,
      color: style.color,
    }}>
      {stato || 'N/D'}
    </span>
  );
}

function Avatar({ nome, cognome, id, size = 32 }) {
  return (
    <div style={{
      width: size,
      height: size,
      borderRadius: "50%",
      background: avatarColor(id),
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: size * 0.38,
      fontWeight: 700,
      color: "white",
      flexShrink: 0
    }}>
      {initials(nome, cognome)}
    </div>
  );
}

function StatCard({ label, value, sub, color, icon: Icon }) {
  return (
    <div style={{
      background: "white",
      border: "1px solid #e5e7eb",
      borderRadius: 12,
      padding: "18px 20px",
      position: "relative",
      overflow: "hidden",
      borderTop: `3px solid ${color || "#6366f1"}`
    }}>
      <div style={{ fontSize: 11, color: "#6b7280", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 800, color: color || "#1e293b", marginTop: 6 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>{sub}</div>}
      {Icon && <Icon size={32} style={{ position: "absolute", top: 18, right: 18, opacity: 0.1 }} />}
    </div>
  );
}

function TableWrap({ title, children, actions }) {
  return (
    <div style={{ background: "white", border: "1px solid #e5e7eb", borderRadius: 12, overflow: "hidden" }}>
      {title && (
        <div style={{ padding: "14px 20px", borderBottom: "1px solid #e5e7eb", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontWeight: 700, fontSize: 15 }}>{title}</span>
          {actions}
        </div>
      )}
      {children}
    </div>
  );
}

function Modal({ isOpen, onClose, title, children, footer }) {
  if (!isOpen) return null;
  return (
    <div style={{
      position: "fixed",
      inset: 0,
      background: "rgba(0,0,0,0.5)",
      zIndex: 200,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: 20
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        background: "white",
        borderRadius: 14,
        width: "100%",
        maxWidth: 600,
        maxHeight: "90vh",
        overflow: "auto"
      }}>
        <div style={{ padding: "18px 24px", borderBottom: "1px solid #e5e7eb", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontWeight: 700, fontSize: 16 }}>{title}</span>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: "#6b7280" }}>×</button>
        </div>
        <div style={{ padding: 24 }}>{children}</div>
        {footer && (
          <div style={{ padding: "14px 24px", borderTop: "1px solid #e5e7eb", display: "flex", justifyContent: "flex-end", gap: 10 }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

function FormField({ label, children }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <label style={{ fontSize: 12, fontWeight: 600, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</label>
      {children}
    </div>
  );
}

const inputStyle = {
  background: "#f9fafb",
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  padding: "9px 12px",
  fontSize: 13,
  width: "100%",
  outline: "none"
};

const btnPrimary = {
  padding: "8px 18px",
  background: "#3b82f6",
  color: "white",
  border: "none",
  borderRadius: 8,
  fontWeight: 600,
  fontSize: 13,
  cursor: "pointer",
  display: "inline-flex",
  alignItems: "center",
  gap: 6
};

const btnOutline = {
  padding: "8px 16px",
  background: "transparent",
  color: "#6b7280",
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  fontWeight: 600,
  fontSize: 13,
  cursor: "pointer"
};

// ══════════════════════════════════════════════════════════════════════════════
// PAGES
// ══════════════════════════════════════════════════════════════════════════════

// ── DASHBOARD ────────────────────────────────────────────────────────────────
function DashboardHR({ dips, loading }) {
  const attivi = dips.filter(d => d.status === 'attivo' || d.in_carico).length;
  const cessati = dips.filter(d => d.status === 'cessato' || !d.in_carico).length;

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 24 }}>
        <StatCard label="Dipendenti totali" value={dips.length} sub="in anagrafica" color="#6366f1" icon={Users} />
        <StatCard label="Attivi" value={attivi} sub="in carico" color="#10b981" icon={Check} />
        <StatCard label="Cessati" value={cessati} sub="non in carico" color="#ef4444" icon={X} />
        <StatCard label="Costo totale" value={formatEuro(dips.reduce((s, d) => s + (d.salary || d.netto || 0), 0))} sub="stipendi mensili" color="#3b82f6" icon={DollarSign} />
      </div>

      <TableWrap title="Dipendenti in organico">
        {loading ? (
          <div style={{ padding: 40, textAlign: "center" }}><Loader2 className="animate-spin" /></div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f9fafb" }}>
                <th style={{ padding: "10px 16px", textAlign: "left", fontWeight: 600, fontSize: 11, color: "#6b7280" }}>Nome</th>
                <th style={{ padding: "10px 16px", textAlign: "left", fontWeight: 600, fontSize: 11, color: "#6b7280" }}>Mansione</th>
                <th style={{ padding: "10px 16px", textAlign: "left", fontWeight: 600, fontSize: 11, color: "#6b7280" }}>Contratto</th>
                <th style={{ padding: "10px 16px", textAlign: "left", fontWeight: 600, fontSize: 11, color: "#6b7280" }}>Stato</th>
              </tr>
            </thead>
            <tbody>
              {dips.filter(d => d.in_carico !== false).slice(0, 10).map((d, idx) => (
                <tr key={d.id || `dip-row-${idx}`} style={{ borderTop: "1px solid #e5e7eb" }}>
                  <td style={{ padding: "12px 16px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <Avatar nome={d.nome} cognome={d.cognome} id={d.id} />
                      <div>
                        <span style={{ fontWeight: 600 }}>{d.nome} {d.cognome}</span>
                        <div style={{ fontSize: 11, color: "#6b7280" }}>{d.codice_fiscale}</div>
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: "12px 16px", color: "#6b7280" }}>{d.mansione || d.role || '-'}</td>
                  <td style={{ padding: "12px 16px", color: "#6b7280" }}>{d.contract_type || 'dipendente'}</td>
                  <td style={{ padding: "12px 16px" }}><Badge stato={d.in_carico !== false ? 'attivo' : 'cessato'} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </TableWrap>

      {/* === WIDGET HR === */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 20, marginTop: 24 }}>
        
        {/* Gestione Turni */}
        <WidgetCard 
          title="Gestione Turni" 
          icon="👥" 
          color="#8b5cf6"
          description="Pianifica i turni di lavoro dei dipendenti"
          linkTo="/dipendenti/presenze"
        />
        
        {/* Richieste */}
        <WidgetCard 
          title="Richieste Ferie/Permessi" 
          icon="📋" 
          color="#f59e0b"
          description="Gestisci le richieste di ferie e permessi"
          linkTo="/dipendenti/ferie"
        />
        
        {/* Storico Ore */}
        <WidgetCard 
          title="Storico Ore Lavorate" 
          icon="⏱️" 
          color="#3b82f6"
          description="Visualizza le ore lavorate per dipendente"
          linkTo="/dipendenti/presenze"
        />
        
        {/* Saldo Ferie */}
        <WidgetCard 
          title="Saldo Ferie" 
          icon="🏖️" 
          color="#10b981"
          description="Monitora i saldi ferie e permessi disponibili"
          linkTo="/dipendenti/ferie"
        />
      </div>
    </div>
  );
}

// Widget Card per Dashboard
function WidgetCard({ title, icon, color, description, linkTo }) {
  const navigate = useNavigate();
  return (
    <div 
      onClick={() => navigate(linkTo)}
      style={{
        background: "white",
        border: "1px solid #e5e7eb",
        borderRadius: 12,
        padding: 20,
        cursor: "pointer",
        transition: "all 0.2s",
        borderLeft: `4px solid ${color}`
      }}
      onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
      onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.transform = 'none'; }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ 
          width: 44, 
          height: 44, 
          borderRadius: 10, 
          background: `${color}15`, 
          display: "flex", 
          alignItems: "center", 
          justifyContent: "center",
          fontSize: 20
        }}>
          {icon}
        </div>
        <div>
          <div style={{ fontWeight: 700, fontSize: 15, color: "#1e293b" }}>{title}</div>
          <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>{description}</div>
        </div>
      </div>
    </div>
  );
}

// ── ANAGRAFICA ───────────────────────────────────────────────────────────────
function Anagrafica({ dips, setDips, loading, reload }) {
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({});
  const [editId, setEditId] = useState(null);
  const [saving, setSaving] = useState(false);

  const filtered = dips.filter(d => {
    const searchStr = `${d.nome || ''} ${d.cognome || ''} ${d.mansione || ''} ${d.codice_fiscale || ''}`.toLowerCase();
    return searchStr.includes(search.toLowerCase());
  });

  const openAdd = () => { 
    setForm({ nome: "", cognome: "", codice_fiscale: "", mansione: "", contract_type: "dipendente", email: "", telefono: "", in_carico: true, giorni_lavoro: ["lun", "mar", "mer", "gio", "ven", "sab"] }); 
    setEditId(null); 
    setModal(true); 
  };
  
  const openEdit = d => { 
    setForm({ ...d }); 
    setEditId(d.id); 
    setModal(true); 
  };

  const save = async () => {
    if (!form.nome || !form.cognome) {
      toast.error("Nome e cognome sono obbligatori");
      return;
    }
    setSaving(true);
    try {
      if (editId) {
        await api.put(`/api/employees/${editId}`, form);
        toast.success("Dipendente aggiornato");
      } else {
        await api.post('/api/employees', form);
        toast.success("Dipendente creato");
      }
      setModal(false);
      reload();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore salvataggio");
    }
    setSaving(false);
  };

  const del = async (id) => { 
    if (!confirm("Eliminare questo dipendente?")) return;
    try {
      await api.delete(`/api/employees/${id}`);
      toast.success("Dipendente eliminato");
      reload();
    } catch (e) {
      toast.error("Errore eliminazione");
    }
  };

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20, flexWrap: "wrap", gap: 12 }}>
        <div style={{ position: "relative" }}>
          <Search size={16} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "#9ca3af" }} />
          <input 
            placeholder="Cerca dipendente..." 
            value={search} 
            onChange={e => setSearch(e.target.value)} 
            style={{ ...inputStyle, paddingLeft: 36, width: 280 }} 
          />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button style={btnOutline} onClick={reload}><RefreshCw size={14} /></button>
          <button style={btnPrimary} onClick={openAdd}><Plus size={16} /> Nuovo dipendente</button>
        </div>
      </div>

      <TableWrap>
        {loading ? (
          <div style={{ padding: 40, textAlign: "center" }}><Loader2 className="animate-spin" /></div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f9fafb" }}>
                {["Nominativo", "Codice Fiscale", "Mansione", "Contratto", "Stato", "Azioni"].map(h => (
                  <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontWeight: 600, fontSize: 11, color: "#6b7280", textTransform: "uppercase" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((d, idx) => (
                <tr key={d.id || `filtered-${idx}`} style={{ borderTop: "1px solid #e5e7eb" }}>
                  <td style={{ padding: "12px 16px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <Avatar nome={d.nome} cognome={d.cognome} id={d.id} />
                      <div>
                        <div style={{ fontWeight: 600 }}>{d.nome} {d.cognome}</div>
                        <div style={{ fontSize: 11, color: "#6b7280" }}>{d.email || '-'}</div>
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: "12px 16px", fontFamily: "monospace", fontSize: 12 }}>{d.codice_fiscale}</td>
                  <td style={{ padding: "12px 16px", color: "#6b7280" }}>{d.mansione || d.role || '-'}</td>
                  <td style={{ padding: "12px 16px", color: "#6b7280" }}>{d.contract_type || 'dipendente'}</td>
                  <td style={{ padding: "12px 16px" }}><Badge stato={d.in_carico !== false ? 'attivo' : 'cessato'} /></td>
                  <td style={{ padding: "12px 16px" }}>
                    <div style={{ display: "flex", gap: 6 }}>
                      <button onClick={() => openEdit(d)} style={{ ...btnOutline, padding: "5px 10px" }}><Edit2 size={14} /></button>
                      <button onClick={() => del(d.id)} style={{ ...btnOutline, padding: "5px 10px", color: "#ef4444", borderColor: "#fecaca" }}><Trash2 size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {!loading && filtered.length === 0 && <div style={{ padding: 40, textAlign: "center", color: "#9ca3af" }}>Nessun dipendente trovato</div>}
      </TableWrap>

      <Modal isOpen={modal} onClose={() => setModal(false)} title={editId ? "Modifica dipendente" : "Nuovo dipendente"} footer={
        <>
          <button style={btnOutline} onClick={() => setModal(false)}>Annulla</button>
          <button style={btnPrimary} onClick={save} disabled={saving}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : null} Salva
          </button>
        </>
      }>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <FormField label="Nome"><input style={inputStyle} value={form.nome || ''} onChange={e => setForm(f => ({ ...f, nome: e.target.value }))} /></FormField>
          <FormField label="Cognome"><input style={inputStyle} value={form.cognome || ''} onChange={e => setForm(f => ({ ...f, cognome: e.target.value }))} /></FormField>
          <FormField label="Codice Fiscale"><input style={inputStyle} value={form.codice_fiscale || ''} onChange={e => setForm(f => ({ ...f, codice_fiscale: e.target.value.toUpperCase() }))} /></FormField>
          <FormField label="Email"><input type="email" style={inputStyle} value={form.email || ''} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} /></FormField>
          <FormField label="Telefono"><input style={inputStyle} value={form.telefono || ''} onChange={e => setForm(f => ({ ...f, telefono: e.target.value }))} /></FormField>
          <FormField label="Mansione"><input style={inputStyle} value={form.mansione || ''} onChange={e => setForm(f => ({ ...f, mansione: e.target.value }))} /></FormField>
          <FormField label="Contratto">
            <select style={inputStyle} value={form.contract_type || 'dipendente'} onChange={e => setForm(f => ({ ...f, contract_type: e.target.value }))}>
              <option value="dipendente">Dipendente</option>
              <option value="determinato">Determinato</option>
              <option value="stage">Stage</option>
              <option value="consulenza">Consulenza</option>
            </select>
          </FormField>
          <FormField label="IBAN"><input style={inputStyle} value={form.iban || ''} onChange={e => setForm(f => ({ ...f, iban: e.target.value.toUpperCase() }))} /></FormField>
          
          {/* Giorni Lavorativi */}
          <div style={{ gridColumn: "1 / -1", marginTop: 10 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.5, display: "block", marginBottom: 8 }}>Giorni Lavorativi</label>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {[
                { key: "lun", label: "Lun" },
                { key: "mar", label: "Mar" },
                { key: "mer", label: "Mer" },
                { key: "gio", label: "Gio" },
                { key: "ven", label: "Ven" },
                { key: "sab", label: "Sab" },
                { key: "dom", label: "Dom" }
              ].map(g => {
                const isActive = (form.giorni_lavoro || ["lun", "mar", "mer", "gio", "ven", "sab"]).includes(g.key);
                return (
                  <button
                    key={g.key}
                    type="button"
                    onClick={() => {
                      const current = form.giorni_lavoro || ["lun", "mar", "mer", "gio", "ven", "sab"];
                      const newGiorni = isActive 
                        ? current.filter(d => d !== g.key)
                        : [...current, g.key];
                      setForm(f => ({ ...f, giorni_lavoro: newGiorni }));
                    }}
                    style={{
                      padding: "8px 14px",
                      borderRadius: 8,
                      border: isActive ? "2px solid #3b82f6" : "1px solid #e5e7eb",
                      background: isActive ? "#dbeafe" : "#f9fafb",
                      color: isActive ? "#1e40af" : "#6b7280",
                      fontWeight: 600,
                      fontSize: 12,
                      cursor: "pointer",
                      transition: "all 0.15s ease"
                    }}
                  >
                    {g.label}
                  </button>
                );
              })}
            </div>
            <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 6 }}>
              Seleziona i giorni in cui il dipendente lavora. Default: Lun-Sab
            </div>
          </div>

          <div style={{ gridColumn: "1 / -1", display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
            <input 
              type="checkbox" 
              id="in_carico"
              checked={form.in_carico !== false} 
              onChange={e => setForm(f => ({ ...f, in_carico: e.target.checked }))} 
              style={{ width: 18, height: 18 }}
            />
            <label htmlFor="in_carico" style={{ fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Dipendente in carico (attivo)</label>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// ── FERIE ────────────────────────────────────────────────────────────────────
function Ferie({ dips }) {
  const [ferie, setFerie] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({ dipendente_id: '', tipo: "Ferie", dal: "", al: "", nota: "" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Prova a caricare richieste ferie dal backend
      const res = await api.get('/api/ferie-permessi');
      setFerie(res.data?.data || res.data || []);
    } catch {
      // Se non esiste l'endpoint, usa dati vuoti
      setFerie([]);
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!form.dipendente_id || !form.dal || !form.al) {
      toast.error("Compila tutti i campi obbligatori");
      return;
    }
    const dal = new Date(form.dal);
    const al = new Date(form.al);
    const giorni = Math.ceil((al - dal) / (1000 * 60 * 60 * 24)) + 1;
    
    const nuovaRichiesta = {
      ...form,
      giorni,
      stato: "in attesa",
      created_at: new Date().toISOString()
    };
    
    try {
      await api.post('/api/ferie-permessi', nuovaRichiesta);
      toast.success("Richiesta inviata");
      setModal(false);
      load();
    } catch {
      // Fallback locale
      setFerie(prev => [...prev, { ...nuovaRichiesta, id: Date.now() }]);
      setModal(false);
      toast.success("Richiesta salvata");
    }
  };

  const approva = async (id) => {
    try {
      await api.patch(`/api/ferie-permessi/${id}`, { stato: "approvata" });
      load();
    } catch {
      setFerie(prev => prev.map(f => f.id === id ? { ...f, stato: "approvata" } : f));
    }
    toast.success("Richiesta approvata");
  };

  const rifiuta = async (id) => {
    try {
      await api.patch(`/api/ferie-permessi/${id}`, { stato: "rifiutato" });
      load();
    } catch {
      setFerie(prev => prev.map(f => f.id === id ? { ...f, stato: "rifiutato" } : f));
    }
    toast.success("Richiesta rifiutata");
  };

  const getNomeDip = (id) => {
    const d = dips.find(x => x.id === id);
    return d ? `${d.nome} ${d.cognome}` : id;
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 20 }}>
        <button style={btnPrimary} onClick={() => { setForm({ dipendente_id: dips[0]?.id || '', tipo: "Ferie", dal: "", al: "", nota: "" }); setModal(true); }}>
          <Plus size={16} /> Nuova richiesta
        </button>
      </div>

      <TableWrap>
        {loading ? (
          <div style={{ padding: 40, textAlign: "center" }}><Loader2 className="animate-spin" /></div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f9fafb" }}>
                {["Dipendente", "Tipo", "Dal", "Al", "Giorni", "Stato", "Azioni"].map(h => (
                  <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontWeight: 600, fontSize: 11, color: "#6b7280" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ferie.map((f, idx) => (
                <tr key={f.id || `ferie-${idx}`} style={{ borderTop: "1px solid #e5e7eb" }}>
                  <td style={{ padding: "12px 16px", fontWeight: 600 }}>{getNomeDip(f.dipendente_id)}</td>
                  <td style={{ padding: "12px 16px", color: "#6b7280" }}>{f.tipo}</td>
                  <td style={{ padding: "12px 16px" }}>{fmt(f.dal)}</td>
                  <td style={{ padding: "12px 16px" }}>{fmt(f.al)}</td>
                  <td style={{ padding: "12px 16px", fontWeight: 600, color: "#6366f1" }}>{f.giorni}</td>
                  <td style={{ padding: "12px 16px" }}><Badge stato={f.stato} /></td>
                  <td style={{ padding: "12px 16px" }}>
                    <div style={{ display: "flex", gap: 5 }}>
                      {f.stato === "in attesa" && (
                        <>
                          <button onClick={() => approva(f.id)} style={{ ...btnOutline, padding: "5px 10px", color: "#10b981", borderColor: "#a7f3d0" }}><Check size={14} /></button>
                          <button onClick={() => rifiuta(f.id)} style={{ ...btnOutline, padding: "5px 10px", color: "#ef4444", borderColor: "#fecaca" }}><X size={14} /></button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {!loading && ferie.length === 0 && (
          <div style={{ padding: 40, textAlign: "center", color: "#9ca3af" }}>Nessuna richiesta ferie</div>
        )}
      </TableWrap>

      <Modal isOpen={modal} onClose={() => setModal(false)} title="Nuova richiesta ferie/permesso" footer={
        <>
          <button style={btnOutline} onClick={() => setModal(false)}>Annulla</button>
          <button style={btnPrimary} onClick={add}>Invia</button>
        </>
      }>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <div style={{ gridColumn: "1 / -1" }}>
            <FormField label="Dipendente">
              <select style={inputStyle} value={form.dipendente_id} onChange={e => setForm(f => ({ ...f, dipendente_id: e.target.value }))}>
                <option value="">-- Seleziona --</option>
                {dips.filter(d => d.in_carico !== false).map((d, idx) => <option key={d.id || `dip-${idx}`} value={d.id}>{d.nome} {d.cognome}</option>)}
              </select>
            </FormField>
          </div>
          <FormField label="Tipo">
            <select style={inputStyle} value={form.tipo} onChange={e => setForm(f => ({ ...f, tipo: e.target.value }))}>
              <option>Ferie</option><option>Permesso</option><option>Malattia</option><option>ROL</option>
            </select>
          </FormField>
          <FormField label="Nota"><input style={inputStyle} value={form.nota} onChange={e => setForm(f => ({ ...f, nota: e.target.value }))} /></FormField>
          <FormField label="Dal"><input type="date" style={inputStyle} value={form.dal} onChange={e => setForm(f => ({ ...f, dal: e.target.value }))} /></FormField>
          <FormField label="Al"><input type="date" style={inputStyle} value={form.al} onChange={e => setForm(f => ({ ...f, al: e.target.value }))} /></FormField>
        </div>
      </Modal>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ══════════════════════════════════════════════════════════════════════════════
const TABS = [
  { id: "dashboard", label: "Dashboard", icon: LayoutGrid },
  { id: "anagrafica", label: "Anagrafica", icon: Users },
  { id: "presenze", label: "Presenze", icon: Clock },
  { id: "ferie", label: "Ferie", icon: Calendar },
  { id: "paghe", label: "Paghe", icon: Wallet },
  { id: "veicoli", label: "Veicoli", icon: Car },
];

export default function HRGestionale() {
  const { tab } = useParams();
  const navigate = useNavigate();
  const currentTab = tab || "dashboard";

  const [dips, setDips] = useState([]);
  const [loading, setLoading] = useState(true);

  // Carica dipendenti dal database
  const loadDipendenti = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/employees');
      const data = res.data?.data || res.data || [];
      // Ordina per nome
      data.sort((a, b) => `${a.cognome} ${a.nome}`.localeCompare(`${b.cognome} ${b.nome}`));
      setDips(data);
    } catch (e) {
      console.error('Errore caricamento dipendenti:', e);
      toast.error("Errore caricamento dipendenti");
    }
    setLoading(false);
  }, []);

  // Per la tab presenze, usa il componente Attendance esistente (senza caricare dipendenti qui)
  if (currentTab === 'presenze') {
    return (
      <Suspense fallback={<div style={{ padding: 40, textAlign: "center" }}><Loader2 className="animate-spin" /></div>}>
        <Attendance />
      </Suspense>
    );
  }

  // Carica dipendenti solo per le altre tab
  useEffect(() => { 
    if (currentTab !== 'presenze') {
      loadDipendenti(); 
    }
  }, [currentTab]);

  const handleTabChange = (tabId) => {
    navigate(`/dipendenti/${tabId}`);
  };

  return (
    <PageLayout
      title="HR Gestionale"
      icon={<Users size={22} />}
      description="Gestione risorse umane, anagrafica e ferie"
    >
      {/* Tabs */}
      <div style={{ display: "flex", gap: 4, background: "#f3f4f6", borderRadius: 10, padding: 4, marginBottom: 24, overflowX: "auto" }}>
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => handleTabChange(t.id)}
            style={{
              padding: "8px 18px",
              borderRadius: 7,
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
              border: "none",
              background: currentTab === t.id ? "white" : "transparent",
              color: currentTab === t.id ? "#1e293b" : "#6b7280",
              boxShadow: currentTab === t.id ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
              display: "flex",
              alignItems: "center",
              gap: 6,
              whiteSpace: "nowrap"
            }}
          >
            <t.icon size={16} />
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {currentTab === "dashboard" && <DashboardHR dips={dips} loading={loading} />}
      {currentTab === "anagrafica" && <Anagrafica dips={dips} setDips={setDips} loading={loading} reload={loadDipendenti} />}
      {currentTab === "ferie" && <Ferie dips={dips} />}
      {currentTab === "paghe" && <TabPaghe />}
      {currentTab === "veicoli" && <TabVeicoli />}
    </PageLayout>
  );
}


// ══════════════════════════════════════════════════════════════════════════════
// TAB PAGHE - Buste Paga & F24
// ══════════════════════════════════════════════════════════════════════════════
function TabPaghe() {
  const [bustePaga, setBustePaga] = useState([]);
  const [f24List, setF24List] = useState([]);
  const [loadingBuste, setLoadingBuste] = useState(false);
  const [loadingF24, setLoadingF24] = useState(false);
  const [anno] = useState(new Date().getFullYear());

  const loadBustePaga = async () => {
    setLoadingBuste(true);
    try {
      const res = await api.get('/api/paghe/buste-paga', { params: { anno } });
      setBustePaga(res.data?.data || []);
    } catch (e) {
      console.error('Errore caricamento buste paga:', e);
    }
    setLoadingBuste(false);
  };

  const loadF24 = async () => {
    setLoadingF24(true);
    try {
      const res = await api.get('/api/paghe/distinte-f24', { params: { anno } });
      setF24List(res.data?.data || []);
    } catch (e) {
      console.error('Errore caricamento F24:', e);
    }
    setLoadingF24(false);
  };

  useEffect(() => {
    loadBustePaga();
    loadF24();
  }, [anno]);

  const totDaPagare = bustePaga.filter(b => b.stato_pagamento !== 'PAGATO').reduce((s, b) => s + (b.netto_mese || 0), 0);
  const totPagato = bustePaga.filter(b => b.stato_pagamento === 'PAGATO').reduce((s, b) => s + (b.netto_mese || 0), 0);
  const totF24DaPagare = f24List.filter(f => f.stato_pagamento !== 'PAGATO').reduce((s, f) => s + (f.totale || 0), 0);
  const totF24Pagato = f24List.filter(f => f.stato_pagamento === 'PAGATO').reduce((s, f) => s + (f.totale || 0), 0);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: '#1e3a5f', margin: 0 }}>💼 Paghe — Buste Paga & F24</h2>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 20 }}>
        {/* Sezione Buste Paga */}
        <div style={{ background: 'white', borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 36, height: 36, borderRadius: 8, background: '#ede9fe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Users size={18} color="#7c3aed" />
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14, color: '#374151' }}>Buste Paga</div>
                <div style={{ fontSize: 12, color: '#6b7280' }}>{bustePaga.length} cedolini</div>
              </div>
            </div>
            <button onClick={loadBustePaga} disabled={loadingBuste} style={{ padding: '6px 12px', background: '#f3f4f6', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
              <RefreshCw size={14} className={loadingBuste ? 'animate-spin' : ''} />
            </button>
          </div>
          
          <div style={{ padding: '12px 16px', background: '#fafafa', borderBottom: '1px solid #e5e7eb', display: 'flex', gap: 12 }}>
            <div style={{ flex: 1, background: 'white', border: '1px solid #e5e7eb', borderRadius: 8, padding: '10px 14px' }}>
              <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 600, textTransform: 'uppercase' }}>Da Pagare</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: '#f59e0b' }}>{formatEuro(totDaPagare)}</div>
            </div>
            <div style={{ flex: 1, background: 'white', border: '1px solid #e5e7eb', borderRadius: 8, padding: '10px 14px' }}>
              <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 600, textTransform: 'uppercase' }}>Pagati</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: '#10b981' }}>{formatEuro(totPagato)}</div>
            </div>
          </div>

          <div style={{ maxHeight: 350, overflowY: 'auto' }}>
            {bustePaga.length === 0 ? (
              <div style={{ padding: 30, textAlign: 'center', color: '#6b7280' }}>Nessuna busta paga</div>
            ) : bustePaga.map((b, i) => {
              // Formatta periodo in italiano (es. "2026-01" -> "Gennaio 2026")
              const formatPeriodo = (p) => {
                if (!p) return 'N/D';
                const mesi = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre'];
                const [anno, mese] = p.split('-');
                const meseIdx = parseInt(mese, 10) - 1;
                return mesi[meseIdx] ? `${mesi[meseIdx]} ${anno}` : p;
              };
              return (
                <div key={i} style={{ padding: '12px 16px', borderBottom: '1px solid #f3f4f6', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13, color: '#1f2937' }}>{b.dipendente_nome || b.nome_dipendente || 'N/D'}</div>
                    <div style={{ fontSize: 11, color: '#6b7280' }}>{formatPeriodo(b.periodo)}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontWeight: 700, fontSize: 14, color: '#1e3a5f' }}>{formatEuro(b.netto_mese || 0)}</div>
                    <Badge stato={b.stato_pagamento || 'DA_PAGARE'} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Sezione F24 */}
        <div style={{ background: 'white', borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 36, height: 36, borderRadius: 8, background: '#fef3c7', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <FileText size={18} color="#d97706" />
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14, color: '#374151' }}>F24</div>
                <div style={{ fontSize: 12, color: '#6b7280' }}>{f24List.length} modelli</div>
              </div>
            </div>
            <button onClick={loadF24} disabled={loadingF24} style={{ padding: '6px 12px', background: '#f3f4f6', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
              <RefreshCw size={14} className={loadingF24 ? 'animate-spin' : ''} />
            </button>
          </div>
          
          <div style={{ padding: '12px 16px', background: '#fafafa', borderBottom: '1px solid #e5e7eb', display: 'flex', gap: 12 }}>
            <div style={{ flex: 1, background: 'white', border: '1px solid #e5e7eb', borderRadius: 8, padding: '10px 14px' }}>
              <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 600, textTransform: 'uppercase' }}>Da Pagare</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: '#f59e0b' }}>{formatEuro(totF24DaPagare)}</div>
            </div>
            <div style={{ flex: 1, background: 'white', border: '1px solid #e5e7eb', borderRadius: 8, padding: '10px 14px' }}>
              <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 600, textTransform: 'uppercase' }}>Pagati</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: '#10b981' }}>{formatEuro(totF24Pagato)}</div>
            </div>
          </div>

          <div style={{ maxHeight: 350, overflowY: 'auto' }}>
            {f24List.length === 0 ? (
              <div style={{ padding: 30, textAlign: 'center', color: '#6b7280' }}>Nessun F24</div>
            ) : f24List.map((f, i) => {
              // Formatta periodo F24 in italiano
              const formatPeriodoF24 = (p) => {
                if (!p) return 'F24';
                const mesi = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre'];
                const [anno, mese] = p.split('-');
                const meseIdx = parseInt(mese, 10) - 1;
                return mesi[meseIdx] ? `F24 ${mesi[meseIdx]} ${anno}` : `F24 ${p}`;
              };
              return (
                <div key={i} style={{ padding: '12px 16px', borderBottom: '1px solid #f3f4f6', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13, color: '#1f2937' }}>{formatPeriodoF24(f.periodo)}</div>
                    <div style={{ fontSize: 11, color: '#6b7280' }}>Scadenza: {fmt(f.data_scadenza)}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontWeight: 700, fontSize: 14, color: '#1e3a5f' }}>{formatEuro(f.totale || 0)}</div>
                    <Badge stato={f.stato_pagamento || 'DA_PAGARE'} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB VEICOLI - Noleggio Auto - VISTA LINEARE ESPANSA
// ══════════════════════════════════════════════════════════════════════════════
function TabVeicoli() {
  const [veicoli, setVeicoli] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadVeicoli = async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/noleggio-auto/veicoli');
      setVeicoli(res.data?.veicoli || res.data || []);
    } catch (e) {
      console.error('Errore caricamento veicoli:', e);
    }
    setLoading(false);
  };

  useEffect(() => { loadVeicoli(); }, []);

  // Calcola totali generali
  const totGenerale = veicoli.reduce((s, v) => s + (v.totale_generale || 0), 0);
  const totCanoni = veicoli.reduce((s, v) => s + (v.totale_canoni || 0), 0);
  const totBolli = veicoli.reduce((s, v) => s + (v.totale_bollo || 0), 0);
  const totVerbali = veicoli.reduce((s, v) => s + (v.totale_verbali || 0), 0);

  return (
    <div>
      {/* Header con totali */}
      <div style={{ background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)', borderRadius: 12, padding: 20, marginBottom: 24, color: 'white' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>🚗 Flotta Veicoli Noleggio</h2>
          <button onClick={loadVeicoli} disabled={loading} style={{ padding: '8px 16px', background: 'rgba(255,255,255,0.2)', border: 'none', borderRadius: 8, color: 'white', cursor: 'pointer', fontSize: 13 }}>
            {loading ? 'Caricamento...' : '🔄 Aggiorna'}
          </button>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 16 }}>
          <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: 12, textAlign: 'center' }}>
            <div style={{ fontSize: 11, opacity: 0.8, marginBottom: 4 }}>VEICOLI</div>
            <div style={{ fontSize: 24, fontWeight: 800 }}>{veicoli.length}</div>
          </div>
          <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: 12, textAlign: 'center' }}>
            <div style={{ fontSize: 11, opacity: 0.8, marginBottom: 4 }}>CANONI</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{formatEuro(totCanoni)}</div>
          </div>
          <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: 12, textAlign: 'center' }}>
            <div style={{ fontSize: 11, opacity: 0.8, marginBottom: 4 }}>BOLLI</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#fcd34d' }}>{formatEuro(totBolli)}</div>
          </div>
          <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: 12, textAlign: 'center' }}>
            <div style={{ fontSize: 11, opacity: 0.8, marginBottom: 4 }}>VERBALI</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#fca5a5' }}>{formatEuro(totVerbali)}</div>
          </div>
          <div style={{ background: 'rgba(16,185,129,0.3)', borderRadius: 8, padding: 12, textAlign: 'center' }}>
            <div style={{ fontSize: 11, opacity: 0.8, marginBottom: 4 }}>TOTALE</div>
            <div style={{ fontSize: 22, fontWeight: 800 }}>{formatEuro(totGenerale)}</div>
          </div>
        </div>
      </div>

      {/* Lista veicoli espansa */}
      {veicoli.map((v, idx) => (
        <div key={idx} style={{ background: 'white', borderRadius: 12, border: '1px solid #e5e7eb', marginBottom: 20, overflow: 'hidden' }}>
          
          {/* Header veicolo */}
          <div style={{ background: '#f8fafc', padding: '16px 20px', borderBottom: '2px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <div style={{ width: 50, height: 50, borderRadius: 10, background: '#1e3a5f', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 11 }}>
                {v.targa?.substring(0, 4)}
              </div>
              <div>
                <div style={{ fontSize: 20, fontWeight: 800, color: '#1e3a5f', letterSpacing: 1 }}>{v.targa}</div>
                <div style={{ fontSize: 13, color: '#6b7280' }}>{v.marca} {v.modello}</div>
                {v.driver && <div style={{ fontSize: 12, color: '#3b82f6', fontWeight: 600, marginTop: 2 }}>👤 {v.driver}</div>}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 12, color: '#6b7280' }}>{v.fornitore_noleggio}</div>
              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>{fmt(v.data_inizio)} → {fmt(v.data_fine)}</div>
              <div style={{ fontSize: 22, fontWeight: 800, color: '#10b981', marginTop: 4 }}>{formatEuro(v.totale_generale || 0)}</div>
            </div>
          </div>

          {/* Riepilogo costi */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 1, background: '#e5e7eb' }}>
            {[
              { label: 'Canoni', value: v.totale_canoni, color: '#1e3a5f', count: v.canoni?.length },
              { label: 'Bolli', value: v.totale_bollo, color: '#f59e0b', count: v.bollo?.length },
              { label: 'Verbali', value: v.totale_verbali, color: '#dc2626', count: v.verbali?.length },
              { label: 'Pedaggi', value: v.totale_pedaggio, color: '#8b5cf6', count: v.pedaggio?.length },
              { label: 'Riparazioni', value: v.totale_riparazioni, color: '#ef4444', count: v.riparazioni?.length },
            ].map((t, i) => (
              <div key={i} style={{ background: 'white', padding: '12px 16px', textAlign: 'center' }}>
                <div style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', marginBottom: 4 }}>{t.label} {t.count > 0 ? `(${t.count})` : ''}</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: t.value > 0 ? t.color : '#d1d5db' }}>{formatEuro(t.value || 0)}</div>
              </div>
            ))}
          </div>

          {/* VERBALI - sempre visibili se presenti */}
          {v.verbali && v.verbali.length > 0 && (
            <div style={{ borderTop: '3px solid #dc2626', background: '#fef2f2' }}>
              <div style={{ padding: '12px 20px', fontWeight: 700, color: '#dc2626', fontSize: 13, borderBottom: '1px solid #fecaca' }}>
                🚨 VERBALI ({v.verbali.length})
              </div>
              {v.verbali.map((verb, i) => (
                <div key={i} style={{ padding: '12px 20px', borderBottom: '1px solid #fecaca', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'white' }}>
                  <div>
                    <div style={{ fontWeight: 700, color: '#dc2626' }}>N° {verb.numero_verbale}</div>
                    <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                      📅 {verb.data_verbale || fmt(verb.data)} | 📄 {verb.numero_fattura} | {verb.fornitore}
                    </div>
                    <div style={{ fontSize: 12, color: '#374151', marginTop: 4 }}>{verb.descrizione}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 18, fontWeight: 800, color: '#dc2626' }}>{formatEuro(verb.totale)}</div>
                    <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 4, background: verb.pagato ? '#dcfce7' : '#fee2e2', color: verb.pagato ? '#16a34a' : '#dc2626' }}>
                      {verb.pagato ? '✓ Pagato' : 'Da pagare'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* CANONI - tabella compatta */}
          {v.canoni && v.canoni.length > 0 && (
            <div style={{ borderTop: '1px solid #e5e7eb' }}>
              <div style={{ padding: '12px 20px', fontWeight: 700, color: '#1e3a5f', fontSize: 13, background: '#f8fafc', borderBottom: '1px solid #e5e7eb' }}>
                📋 CANONI NOLEGGIO ({v.canoni.length})
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: '#f3f4f6' }}>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#6b7280' }}>Fattura</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#6b7280' }}>Data</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#6b7280' }}>Descrizione</th>
                    <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#6b7280' }}>Importo</th>
                    <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600, color: '#6b7280' }}>Stato</th>
                  </tr>
                </thead>
                <tbody>
                  {v.canoni.map((c, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                      <td style={{ padding: '10px 12px', fontWeight: 600 }}>{c.numero_fattura}</td>
                      <td style={{ padding: '10px 12px', color: '#6b7280' }}>{fmt(c.data)}</td>
                      <td style={{ padding: '10px 12px', color: '#374151', maxWidth: 300 }}>
                        {c.voci?.[0]?.descrizione?.substring(0, 60) || c.fornitore}
                      </td>
                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: '#1e3a5f' }}>{formatEuro(c.totale)}</td>
                      <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                        <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 4, background: c.pagato ? '#dcfce7' : '#fef3c7', color: c.pagato ? '#16a34a' : '#d97706' }}>
                          {c.pagato ? '✓ Pagato' : 'Da pagare'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* BOLLI - tabella compatta */}
          {v.bollo && v.bollo.length > 0 && (
            <div style={{ borderTop: '1px solid #e5e7eb' }}>
              <div style={{ padding: '12px 20px', fontWeight: 700, color: '#f59e0b', fontSize: 13, background: '#fffbeb', borderBottom: '1px solid #fde68a' }}>
                🏷️ BOLLI ({v.bollo.length})
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: '#f3f4f6' }}>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#6b7280' }}>Fattura</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#6b7280' }}>Data</th>
                    <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#6b7280' }}>Importo</th>
                    <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600, color: '#6b7280' }}>Stato</th>
                  </tr>
                </thead>
                <tbody>
                  {v.bollo.map((b, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                      <td style={{ padding: '10px 12px', fontWeight: 600 }}>{b.numero_fattura}</td>
                      <td style={{ padding: '10px 12px', color: '#6b7280' }}>{fmt(b.data)}</td>
                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: '#f59e0b' }}>{formatEuro(b.totale)}</td>
                      <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                        <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 4, background: b.pagato ? '#dcfce7' : '#fef3c7', color: b.pagato ? '#16a34a' : '#d97706' }}>
                          {b.pagato ? '✓ Pagato' : 'Da pagare'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* PEDAGGI */}
          {v.pedaggio && v.pedaggio.length > 0 && (
            <div style={{ borderTop: '1px solid #e5e7eb' }}>
              <div style={{ padding: '12px 20px', fontWeight: 700, color: '#8b5cf6', fontSize: 13, background: '#f5f3ff', borderBottom: '1px solid #ddd6fe' }}>
                🛣️ PEDAGGI/TELEPASS ({v.pedaggio.length})
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: '#f3f4f6' }}>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#6b7280' }}>Fattura</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#6b7280' }}>Data</th>
                    <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#6b7280' }}>Importo</th>
                  </tr>
                </thead>
                <tbody>
                  {v.pedaggio.map((p, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                      <td style={{ padding: '10px 12px', fontWeight: 600 }}>{p.numero_fattura}</td>
                      <td style={{ padding: '10px 12px', color: '#6b7280' }}>{fmt(p.data)}</td>
                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: '#8b5cf6' }}>{formatEuro(p.totale)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* RIPARAZIONI */}
          {v.riparazioni && v.riparazioni.length > 0 && (
            <div style={{ borderTop: '1px solid #e5e7eb' }}>
              <div style={{ padding: '12px 20px', fontWeight: 700, color: '#ef4444', fontSize: 13, background: '#fef2f2', borderBottom: '1px solid #fecaca' }}>
                🔧 RIPARAZIONI ({v.riparazioni.length})
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: '#f3f4f6' }}>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#6b7280' }}>Fattura</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#6b7280' }}>Data</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#6b7280' }}>Descrizione</th>
                    <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#6b7280' }}>Importo</th>
                  </tr>
                </thead>
                <tbody>
                  {v.riparazioni.map((r, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                      <td style={{ padding: '10px 12px', fontWeight: 600 }}>{r.numero_fattura}</td>
                      <td style={{ padding: '10px 12px', color: '#6b7280' }}>{fmt(r.data)}</td>
                      <td style={{ padding: '10px 12px', color: '#374151' }}>{r.voci?.[0]?.descrizione?.substring(0, 60) || '-'}</td>
                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: '#ef4444' }}>{formatEuro(r.totale)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

        </div>
      ))}
    </div>
  );
}


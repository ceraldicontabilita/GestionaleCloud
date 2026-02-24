import React, { useState, useEffect } from "react";
import api from "../api";
import { useAnnoGlobale } from "../contexts/AnnoContext";
import { STYLES, COLORS, button, badge, formatEuro, formatDateIT } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { 
  Lock, Plus, Trash2, Edit2, Save, X, 
  TrendingUp, TrendingDown, DollarSign, Eye, EyeOff,
  AlertTriangle, CheckCircle
} from "lucide-react";


// Login Component
function LoginGestioneRiservata({ onLogin }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    
    try {
      const res = await api.post("/api/gestione-riservata/login", { code });
      if (res.data.success) {
        localStorage.setItem("gestione_riservata_session", "active");
        onLogin();
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Codice non valido");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh",
      background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: 20
    }}>
      <div style={{
        background: "rgba(255,255,255,0.95)",
        borderRadius: 16,
        padding: 40,
        width: "100%",
        maxWidth: 400,
        boxShadow: "0 25px 50px rgba(0,0,0,0.4)"
      }}>
        <div style={{ textAlign: "center", marginBottom: 30 }}>
          <div style={{
            width: 80,
            height: 80,
            borderRadius: "50%",
            background: "linear-gradient(135deg, #e94560 0%, #0f3460 100%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            margin: "0 auto 20px"
          }}>
            <Lock size={40} color="white" />
          </div>
          <h1 style={{ margin: 0, fontSize: 24, color: "#1a1a2e" }}>Gestione Riservata</h1>
          <p style={{ color: "#718096", marginTop: 8 }}>Area ad accesso limitato</p>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 20 }}>
            <label style={{ display: "block", marginBottom: 8, color: "#4a5568", fontWeight: 500 }}>
              Codice di Accesso
            </label>
            <input
              type="password"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="••••••"
              data-testid="riservata-code-input"
              style={{
                width: "100%",
                padding: "14px 16px",
                fontSize: 20,
                border: "2px solid #e2e8f0",
                borderRadius: 8,
                textAlign: "center",
                letterSpacing: 6,
                fontFamily: "monospace"
              }}
              autoFocus
            />
          </div>

          {error && (
            <div style={{
              background: "#fed7d7",
              color: "#c53030",
              padding: 12,
              borderRadius: 8,
              marginBottom: 20,
              display: "flex",
              alignItems: "center",
              gap: 8
            }}>
              <AlertTriangle size={18} />
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !code}
            data-testid="riservata-login-btn"
            style={{
              width: "100%",
              padding: 14,
              background: loading || !code ? "#cbd5e0" : "linear-gradient(135deg, #e94560 0%, #0f3460 100%)",
              color: "white",
              border: "none",
              borderRadius: 8,
              fontSize: 16,
              fontWeight: 600,
              cursor: loading || !code ? "not-allowed" : "pointer"
            }}
          >
            {loading ? "Verifica..." : "Accedi"}
          </button>
        </form>
      </div>
    </div>
  );
}

// Main Dashboard
function DashboardGestioneRiservata({ onLogout }) {
  const [movimenti, setMovimenti] = useState([]);
  const [riepilogo, setRiepilogo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [formData, setFormData] = useState({
    data: new Date().toISOString().split('T')[0],
    tipo: "incasso",
    descrizione: "",
    importo: "",
    categoria: "altro",
    note: ""
  });
  const { anno } = useAnnoGlobale(); // Anno dal contesto globale
  const [mese, setMese] = useState(null);

  useEffect(() => {
    loadData();
  }, [anno, mese]);

  async function loadData() {
    setLoading(true);
    try {
      let url = `/api/gestione-riservata/movimenti?`;
      if (anno) url += `anno=${anno}&`;
      if (mese) url += `mese=${mese}`;
      
      const [movRes, riepRes] = await Promise.all([
        api.get(url),
        api.get(`/api/gestione-riservata/riepilogo?anno=${anno}${mese ? `&mese=${mese}` : ''}`)
      ]);
      
      setMovimenti(movRes.data || []);
      setRiepilogo(riepRes.data);
    } catch (e) {
      console.error("Errore caricamento:", e);
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    try {
      if (editingId) {
        await api.put(`/api/gestione-riservata/movimenti/${editingId}`, formData);
      } else {
        await api.post("/api/gestione-riservata/movimenti", formData);
      }
      setShowForm(false);
      setEditingId(null);
      setFormData({
        data: new Date().toISOString().split('T')[0],
        tipo: "incasso",
        descrizione: "",
        importo: "",
        categoria: "altro",
        note: ""
      });
      loadData();
    } catch (e) {
      alert("Errore: " + (e.response?.data?.detail || e.message));
    }
  }

  async function handleDelete(id) {
    
    try {
      await api.delete(`/api/gestione-riservata/movimenti/${id}`);
      loadData();
    } catch (e) {
      alert("Errore: " + (e.response?.data?.detail || e.message));
    }
  }

  function handleEdit(mov) {
    setFormData({
      data: mov.data,
      tipo: mov.tipo,
      descrizione: mov.descrizione,
      importo: mov.importo,
      categoria: mov.categoria || "altro",
      note: mov.note || ""
    });
    setEditingId(mov.id);
    setShowForm(true);
  }

  function handleLogout() {
    localStorage.removeItem("gestione_riservata_session");
    onLogout();
  }

  const mesiNomi = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", 
                   "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"];

  return (
    <PageLayout title="Gestione Riservata" subtitle="Incassi e spese non fatturati">
    <div style={{ minHeight: "100vh", background: "#f7fafc" }}>
      {/* Header */}
      <div style={{ 
        display: "flex", 
        justifyContent: "space-between", 
        alignItems: "center", 
        marginBottom: 30 
      }}>
        <div>
          <h1 style={{ margin: 0, color: "#1a1a2e", display: "flex", alignItems: "center", gap: 12 }}>
            <Lock size={28} /> Gestione Riservata
          </h1>
          <p style={{ color: "#718096", marginTop: 4 }}>Incassi e spese non fatturati</p>
        </div>
        <button
          onClick={handleLogout}
          style={{
            padding: "10px 20px",
            background: "#e2e8f0",
            border: "none",
            borderRadius: 8,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: 8
          }}
        >
          <EyeOff size={16} /> Esci
        </button>
      </div>

      {/* Filtri */}
      <div style={{ 
        display: "flex", 
        gap: 15, 
        marginBottom: 25,
        flexWrap: "wrap",
        alignItems: "center"
      }}>
        <div
          style={{ padding: "10px 16px", borderRadius: 8, border: "1px solid #e2e8f0", background: '#f1f5f9', color: '#64748b', fontWeight: 600 }}
          data-testid="anno-display"
        >
          {anno} <span style={{ fontSize: 10, opacity: 0.7 }}>(globale)</span>
        </div>
        <select
          value={mese || ""}
          onChange={(e) => setMese(e.target.value ? parseInt(e.target.value) : null)}
          style={{ padding: "10px 16px", borderRadius: 8, border: "1px solid #e2e8f0" }}
        >
          <option value="">Tutti i mesi</option>
          {mesiNomi.slice(1).map((m, i) => (
            <option key={i+1} value={i+1}>{m}</option>
          ))}
        </select>
        <button
          onClick={() => { setShowForm(true); setEditingId(null); }}
          style={{
            padding: "10px 20px",
            background: "linear-gradient(135deg, #e94560 0%, #0f3460 100%)",
            color: "white",
            border: "none",
            borderRadius: 8,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: 8,
            fontWeight: 600
          }}
          data-testid="add-movimento-btn"
        >
          <Plus size={18} /> Nuovo Movimento
        </button>
      </div>

      {/* Riepilogo Cards */}
      {riepilogo && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 20, marginBottom: 30 }}>
          <div style={{
            background: "linear-gradient(135deg, #10b981 0%, #059669 100%)",
            borderRadius: 12,
            padding: 24,
            color: "white"
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <TrendingUp size={24} />
              <span style={{ opacity: 0.9 }}>Incassi Non Fatturati</span>
            </div>
            <div style={{ fontSize: 32, fontWeight: 700 }}>{formatEuro(riepilogo.incassi?.totale || 0)}</div>
            <div style={{ opacity: 0.8, marginTop: 4 }}>{riepilogo.incassi?.count || 0} movimenti</div>
          </div>
          
          <div style={{
            background: "linear-gradient(135deg, #ef4444 0%, #dc2626 100%)",
            borderRadius: 12,
            padding: 24,
            color: "white"
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <TrendingDown size={24} />
              <span style={{ opacity: 0.9 }}>Spese Non Fatturate</span>
            </div>
            <div style={{ fontSize: 32, fontWeight: 700 }}>{formatEuro(riepilogo.spese?.totale || 0)}</div>
            <div style={{ opacity: 0.8, marginTop: 4 }}>{riepilogo.spese?.count || 0} movimenti</div>
          </div>
          
          <div style={{
            background: "linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%)",
            borderRadius: 12,
            padding: 24,
            color: "white"
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <DollarSign size={24} />
              <span style={{ opacity: 0.9 }}>Saldo Netto Extra</span>
            </div>
            <div style={{ fontSize: 32, fontWeight: 700 }}>{formatEuro(riepilogo.saldo_netto || 0)}</div>
            <div style={{ opacity: 0.8, marginTop: 4 }}>Da aggiungere al fatturato</div>
          </div>
        </div>
      )}

      {/* Form Nuovo/Modifica */}
      {showForm && (
        <div style={{
          background: "white",
          borderRadius: 12,
          padding: 24,
          marginBottom: 25,
          boxShadow: "0 4px 15px rgba(0,0,0,0.1)"
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
            <h3 style={{ margin: 0 }}>{editingId ? "Modifica Movimento" : "Nuovo Movimento"}</h3>
            <button onClick={() => { setShowForm(false); setEditingId(null); }} style={{ background: "none", border: "none", cursor: "pointer" }}>
              <X size={24} color="#718096" />
            </button>
          </div>
          
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 16 }}>
            <div>
              <label style={{ display: "block", marginBottom: 6, fontWeight: 500 }}>Data</label>
              <input
                type="date"
                value={formData.data}
                onChange={(e) => setFormData({...formData, data: e.target.value})}
                style={{ width: "100%", padding: 10, border: "1px solid #e2e8f0", borderRadius: 6 }}
              />
            </div>
            <div>
              <label style={{ display: "block", marginBottom: 6, fontWeight: 500 }}>Tipo</label>
              <select
                value={formData.tipo}
                onChange={(e) => setFormData({...formData, tipo: e.target.value})}
                style={{ width: "100%", padding: 10, border: "1px solid #e2e8f0", borderRadius: 6 }}
              >
                <option value="incasso">💰 Incasso</option>
                <option value="spesa">💸 Spesa</option>
              </select>
            </div>
            <div>
              <label style={{ display: "block", marginBottom: 6, fontWeight: 500 }}>Importo (€)</label>
              <input
                type="number"
                step="0.01"
                value={formData.importo}
                onChange={(e) => setFormData({...formData, importo: e.target.value})}
                placeholder="0.00"
                style={{ width: "100%", padding: 10, border: "1px solid #e2e8f0", borderRadius: 6 }}
                data-testid="importo-input"
              />
            </div>
          </div>
          
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", marginBottom: 6, fontWeight: 500 }}>Descrizione</label>
            <input
              type="text"
              value={formData.descrizione}
              onChange={(e) => setFormData({...formData, descrizione: e.target.value})}
              placeholder="es. Mance giornaliere, Vendita extra..."
              style={{ width: "100%", padding: 10, border: "1px solid #e2e8f0", borderRadius: 6 }}
              data-testid="descrizione-input"
            />
          </div>
          
          <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 16, marginBottom: 20 }}>
            <div>
              <label style={{ display: "block", marginBottom: 6, fontWeight: 500 }}>Categoria</label>
              <select
                value={formData.categoria}
                onChange={(e) => setFormData({...formData, categoria: e.target.value})}
                style={{ width: "100%", padding: 10, border: "1px solid #e2e8f0", borderRadius: 6 }}
              >
                <option value="mance">Mance</option>
                <option value="vendita_extra">Vendita Extra</option>
                <option value="catering">Catering</option>
                <option value="acquisti">Acquisti</option>
                <option value="altro">Altro</option>
              </select>
            </div>
            <div>
              <label style={{ display: "block", marginBottom: 6, fontWeight: 500 }}>Note</label>
              <input
                type="text"
                value={formData.note}
                onChange={(e) => setFormData({...formData, note: e.target.value})}
                placeholder="Note aggiuntive..."
                style={{ width: "100%", padding: 10, border: "1px solid #e2e8f0", borderRadius: 6 }}
              />
            </div>
          </div>
          
          <button
            onClick={handleSave}
            style={{
              padding: "12px 24px",
              background: "linear-gradient(135deg, #e94560 0%, #0f3460 100%)",
              color: "white",
              border: "none",
              borderRadius: 8,
              cursor: "pointer",
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: 8
            }}
            data-testid="save-movimento-btn"
          >
            <Save size={18} /> {editingId ? "Aggiorna" : "Salva"}
          </button>
        </div>
      )}

      {/* Lista Movimenti */}
      <div style={{ background: "white", borderRadius: 12, boxShadow: "0 2px 8px rgba(0,0,0,0.08)" }}>
        <div style={{ padding: "20px 24px", borderBottom: "1px solid #e2e8f0" }}>
          <h3 style={{ margin: 0 }}>📋 Movimenti ({movimenti.length})</h3>
        </div>
        
        {loading ? (
          <div style={{ padding: 40, textAlign: "center", color: "#718096" }}>Caricamento...</div>
        ) : movimenti.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: "#718096" }}>
            Nessun movimento registrato per questo periodo
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#f7fafc" }}>
                <th style={{ padding: "12px 16px", textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>Data</th>
                <th style={{ padding: "12px 16px", textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>Tipo</th>
                <th style={{ padding: "12px 16px", textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>Descrizione</th>
                <th style={{ padding: "12px 16px", textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>Categoria</th>
                <th style={{ padding: "12px 16px", textAlign: "right", borderBottom: "1px solid #e2e8f0" }}>Importo</th>
                <th style={{ padding: "12px 16px", textAlign: "center", borderBottom: "1px solid #e2e8f0" }}>Azioni</th>
              </tr>
            </thead>
            <tbody>
              {movimenti.map(mov => (
                <tr key={mov.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                  <td style={{ padding: "12px 16px" }}>{mov.data}</td>
                  <td style={{ padding: "12px 16px" }}>
                    <span style={{
                      padding: "4px 10px",
                      borderRadius: 12,
                      fontSize: 12,
                      fontWeight: 600,
                      background: mov.tipo === "incasso" ? "#d1fae5" : "#fee2e2",
                      color: mov.tipo === "incasso" ? "#065f46" : "#991b1b"
                    }}>
                      {mov.tipo === "incasso" ? "💰 Incasso" : "💸 Spesa"}
                    </span>
                  </td>
                  <td style={{ padding: "12px 16px" }}>{mov.descrizione}</td>
                  <td style={{ padding: "12px 16px", color: "#718096" }}>{mov.categoria}</td>
                  <td style={{ 
                    padding: "12px 16px", 
                    textAlign: "right",
                    fontWeight: 600,
                    color: mov.tipo === "incasso" ? "#059669" : "#dc2626"
                  }}>
                    {mov.tipo === "incasso" ? "+" : "-"}{formatEuro(mov.importo)}
                  </td>
                  <td style={{ padding: "12px 16px", textAlign: "center" }}>
                    <button
                      onClick={() => handleEdit(mov)}
                      style={{ padding: 6, background: "#f0f9ff", border: "none", borderRadius: 4, cursor: "pointer", marginRight: 6 }}
                    >
                      <Edit2 size={14} color="#0369a1" />
                    </button>
                    <button
                      onClick={() => handleDelete(mov.id)}
                      style={{ padding: 6, background: "#fef2f2", border: "none", borderRadius: 4, cursor: "pointer" }}
                    >
                      <Trash2 size={14} color="#dc2626" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
    </PageLayout>
  );
}

// Main Component
export default function GestioneRiservata() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    const session = localStorage.getItem("gestione_riservata_session");
    if (session === "active") {
      setIsLoggedIn(true);
    }
  }, []);

  if (!isLoggedIn) {
    return <LoginGestioneRiservata onLogin={() => setIsLoggedIn(true)} />;
  }

  return <DashboardGestioneRiservata onLogout={() => setIsLoggedIn(false)} />;
}

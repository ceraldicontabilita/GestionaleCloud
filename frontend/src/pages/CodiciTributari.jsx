import React, { useState, useEffect } from "react";
import api from "../api";
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';
import { useAnnoGlobale } from "../contexts/AnnoContext";
import { PageLayout } from '../components/PageLayout';

const cardStyle = { background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)', border: '1px solid #dce8f4' };

export default function CodiciTributari() {
  const { anno } = useAnnoGlobale();
  const [loading, setLoading] = useState(true);
  const [codici, setCodici] = useState([]);
  const [selectedCodice, setSelectedCodice] = useState(null);
  const [dettaglioCodice, setDettaglioCodice] = useState(null);
  const [riepilogoAnnuale, setRiepilogoAnnuale] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [viewMode, setViewMode] = useState("lista");
  const [err, setErr] = useState("");

  useEffect(() => {
    loadCodici();
    loadRiepilogo();
  }, [anno]);

  async function loadCodici() {
    setLoading(true);
    setErr("");
    try {
      const res = await api.get("/api/codici-tributari/codici-tributo/lista");
      setCodici(res.data.codici || []);
    } catch (e) {
      console.error("Error loading codici:", e);
      setErr("Errore caricamento codici tributo");
    } finally {
      setLoading(false);
    }
  }

  async function loadRiepilogo() {
    try {
      const res = await api.get(`/api/codici-tributari/codici-tributo/riepilogo-annuale/${anno}`);
      setRiepilogoAnnuale(res.data);
    } catch (e) {
      console.error("Error loading riepilogo:", e);
    }
  }

  async function loadDettaglioCodice(codice) {
    setSelectedCodice(codice);
    try {
      const res = await api.get(`/api/codici-tributari/codici-tributo/stato/${codice}?anno=${anno}`);
      setDettaglioCodice(res.data);
    } catch (e) {
      console.error("Error loading dettaglio:", e);
      setDettaglioCodice(null);
    }
  }

  async function handleSearch(e) {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    try {
      const res = await api.get(`/api/codici-tributari/codici-tributo/cerca?query=${searchQuery}&anno=${anno}`);
      setSearchResults(res.data.risultati || []);
      setViewMode("ricerca");
    } catch (e) {
      console.error("Error searching:", e);
    }
  }

  const getCategoriaColor = (cat) => {
    const colors = {
      "IRPEF": { bg: "#fee2e2", color: "#dc2626" },
      "INPS": { bg: "#dbeafe", color: "#1535a8" },
      "INAIL": { bg: "#fef3c7", color: "#d97706" },
      "Addizionali": { bg: "#f3e8ff", color: "#7c3aed" },
      "TFR": { bg: "#dcfce7", color: "#16a34a" },
      "Credito": { bg: "#d1fae5", color: "#059669" },
      "Ravvedimento": { bg: "#fce7f3", color: "#db2777" },
      "Sanzioni": { bg: "#fee2e2", color: "#dc2626" },
      "Altro": { bg: "#f3f4f6", color: "#6080a0" }
    };
    return colors[cat] || colors["Altro"];
  };

  const getButtonStyle = (active) => ({
    padding: '8px 16px',
    background: active ? '#1535a8' : '#dce8f4',
    color: active ? 'white' : '#374151',
    border: 'none',
    borderRadius: 8,
    cursor: 'pointer',
    fontWeight: '600',
    fontSize: 13
  });

  return (
    <PageLayout 
      title="Gestione Codici Tributari" 
      icon="💰" 
      subtitle={`Traccia e verifica i pagamenti F24 – Anno ${anno}`}
    >
      {err && (
        <div style={{ padding: 16, background: "#fee2e2", border: "1px solid #fecaca", borderRadius: 8, color: "#dc2626", marginBottom: 20 }}>
          ❌ {err}
        </div>
      )}

      {/* Controlli */}
      <div style={{ ...cardStyle, marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 15, flexWrap: 'wrap' }}>
          {/* Ricerca */}
          <form onSubmit={handleSearch} style={{ display: 'flex', gap: 8 }}>
            <input
              type="text"
              placeholder="Cerca codice o descrizione (es: 1001, IRPEF)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ padding: '8px 12px', borderRadius: 8, border: '2px solid #dce8f4', fontSize: 14, width: 280 }}
              data-testid="search-codice-input"
            />
            <button 
              type="submit" 
              style={{ padding: '8px 16px', background: '#10b981', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: '600' }}
              data-testid="search-codice-btn"
            >
              🔍 Cerca
            </button>
          </form>

          <div style={{ marginLeft: "auto", display: 'flex', gap: 8 }}>
            <button style={getButtonStyle(viewMode === "lista")} onClick={() => setViewMode("lista")} data-testid="view-lista">
              📋 Lista Codici
            </button>
            <button style={getButtonStyle(viewMode === "riepilogo")} onClick={() => setViewMode("riepilogo")} data-testid="view-riepilogo">
              📊 Riepilogo {anno}
            </button>
          </div>
        </div>
      </div>

      {/* Riepilogo Cards */}
      {riepilogoAnnuale && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 20 }}>
          <div style={{ ...cardStyle, background: "#e0f2fe", textAlign: 'center' }}>
            <div style={{ fontSize: 13, color: '#6080a0', marginBottom: 4 }}>Quietanze {anno}</div>
            <div style={{ fontSize: 28, fontWeight: 'bold', color: '#0369a1' }}>{riepilogoAnnuale.totale_quietanze}</div>
          </div>
          <div style={{ ...cardStyle, background: "#fee2e2", textAlign: 'center' }}>
            <div style={{ fontSize: 13, color: '#6080a0', marginBottom: 4 }}>Totale Debito</div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#dc2626' }}>{formatEuro(riepilogoAnnuale.riepilogo?.totale_debito)}</div>
          </div>
          <div style={{ ...cardStyle, background: "#dcfce7", textAlign: 'center' }}>
            <div style={{ fontSize: 13, color: '#6080a0', marginBottom: 4 }}>Totale Credito</div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#16a34a' }}>{formatEuro(riepilogoAnnuale.riepilogo?.totale_credito)}</div>
          </div>
          <div style={{ ...cardStyle, background: "#fff7ed", textAlign: 'center' }}>
            <div style={{ fontSize: 13, color: '#6080a0', marginBottom: 4 }}>Saldo Netto</div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#ea580c' }}>{formatEuro(riepilogoAnnuale.riepilogo?.saldo_netto)}</div>
          </div>
        </div>
      )}

      {loading ? (
        <div style={{ ...cardStyle, textAlign: 'center', padding: 40 }}>
          <p style={{ color: '#6080a0' }}>⏳ Caricamento codici tributo...</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: dettaglioCodice ? '1fr 1fr' : '1fr', gap: 20 }}>
          
          {/* Lista Codici */}
          {viewMode === "lista" && (
            <div style={cardStyle}>
              <h2 style={{ margin: '0 0 16px 0', fontSize: 18, fontWeight: 'bold', color: '#1535a8' }}>
                📋 Codici Tributo ({codici.length})
              </h2>
              <div style={{ maxHeight: 500, overflowY: 'auto' }}>
                {codici.map((c, idx) => (
                  <div 
                    key={c.codice}
                    onClick={() => loadDettaglioCodice(c.codice)}
                    style={{ 
                      padding: '12px 16px', 
                      borderBottom: '1px solid #f3f4f6',
                      cursor: 'pointer',
                      background: selectedCodice === c.codice ? '#f0f9ff' : 'white',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      transition: 'background 0.2s'
                    }}
                    data-testid={`codice-row-${c.codice}`}
                  >
                    <div>
                      <div style={{ fontWeight: 'bold', fontSize: 15 }}>{c.codice}</div>
                      <div style={{ fontSize: 13, color: '#6080a0' }}>{c.nome}</div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <span style={{ 
                        ...getCategoriaColor(c.categoria), 
                        padding: '3px 8px', 
                        borderRadius: 6, 
                        fontSize: 11, 
                        fontWeight: '600' 
                      }}>
                        {c.categoria}
                      </span>
                      <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>
                        {c.occorrenze} pagamenti
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Vista Riepilogo per Categoria */}
          {viewMode === "riepilogo" && riepilogoAnnuale && (
            <div style={cardStyle}>
              <h2 style={{ margin: '0 0 16px 0', fontSize: 18, fontWeight: 'bold', color: '#1535a8' }}>
                📊 Riepilogo {anno} per Categoria
              </h2>
              {riepilogoAnnuale.per_categoria?.map((cat, idx) => (
                <div key={cat.categoria} style={{ 
                  marginBottom: 16, 
                  padding: 16, 
                  borderRadius: 8,
                  background: getCategoriaColor(cat.categoria).bg
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <span style={{ fontWeight: 'bold', fontSize: 16, color: getCategoriaColor(cat.categoria).color }}>
                      {cat.categoria}
                    </span>
                    <span style={{ fontWeight: 'bold', fontSize: 18 }}>
                      {formatEuro(cat.saldo)}
                    </span>
                  </div>
                  <div style={{ fontSize: 13, color: '#6080a0' }}>
                    Debito: {formatEuro(cat.totale_debito)} | Credito: {formatEuro(cat.totale_credito)}
                  </div>
                  <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>
                    Codici: {cat.codici_tributo?.map(ct => ct.codice).join(', ')}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Vista Risultati Ricerca */}
          {viewMode === "ricerca" && (
            <div style={cardStyle}>
              <h2 style={{ margin: '0 0 16px 0', fontSize: 18, fontWeight: 'bold', color: '#1535a8' }}>
                🔍 Risultati ricerca: "{searchQuery}" ({searchResults.length})
              </h2>
              {searchResults.length === 0 ? (
                <p style={{ color: '#6080a0', textAlign: 'center', padding: 20 }}>Nessun risultato trovato</p>
              ) : (
                searchResults.map((r, idx) => (
                  <div 
                    key={r.codice}
                    onClick={() => { loadDettaglioCodice(r.codice); setViewMode("lista"); }}
                    style={{ 
                      padding: '12px 16px', 
                      borderBottom: '1px solid #f3f4f6',
                      cursor: 'pointer',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 'bold', fontSize: 15 }}>{r.codice}</div>
                      <div style={{ fontSize: 13, color: '#6080a0' }}>{r.nome}</div>
                    </div>
                    <span style={{ 
                      ...getCategoriaColor(r.categoria), 
                      padding: '3px 8px', 
                      borderRadius: 6, 
                      fontSize: 11, 
                      fontWeight: '600' 
                    }}>
                      {r.categoria}
                    </span>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Dettaglio Codice Selezionato */}
          {dettaglioCodice && (
            <div style={cardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h2 style={{ margin: 0, fontSize: 18, fontWeight: 'bold', color: '#1535a8' }}>
                  📌 Dettaglio: {dettaglioCodice.codice}
                </h2>
                <button 
                  onClick={() => { setSelectedCodice(null); setDettaglioCodice(null); }}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, color: '#6080a0' }}
                >
                  ✕
                </button>
              </div>

              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 14, color: '#6080a0' }}>{dettaglioCodice.nome}</div>
                <span style={{ 
                  ...getCategoriaColor(dettaglioCodice.categoria), 
                  padding: '4px 10px', 
                  borderRadius: 6, 
                  fontSize: 12, 
                  fontWeight: '600',
                  display: 'inline-block',
                  marginTop: 8
                }}>
                  {dettaglioCodice.categoria}
                </span>
              </div>

              {/* Riepilogo */}
              <div style={{ background: '#f2f6fd', borderRadius: 8, padding: 16, marginBottom: 16 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div>
                    <div style={{ fontSize: 12, color: '#6080a0' }}>Pagamenti {anno}</div>
                    <div style={{ fontSize: 20, fontWeight: 'bold', color: '#0369a1' }}>{dettaglioCodice.riepilogo?.totale_pagamenti}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 12, color: '#6080a0' }}>Totale Debito</div>
                    <div style={{ fontSize: 20, fontWeight: 'bold', color: '#dc2626' }}>{formatEuro(dettaglioCodice.riepilogo?.totale_debito)}</div>
                  </div>
                </div>
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontSize: 12, color: '#6080a0' }}>Periodi coperti:</div>
                  <div style={{ fontSize: 13, fontWeight: '500', marginTop: 4 }}>
                    {dettaglioCodice.riepilogo?.periodi_coperti?.join(', ') || 'Nessuno'}
                  </div>
                </div>
              </div>

              {/* Lista Pagamenti */}
              <h3 style={{ fontSize: 14, fontWeight: '600', marginBottom: 8, color: '#374151' }}>📜 Storico Pagamenti</h3>
              <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                {dettaglioCodice.pagamenti?.length === 0 ? (
                  <p style={{ color: '#6080a0', textAlign: 'center', padding: 20 }}>
                    Nessun pagamento trovato per l'anno {anno}
                  </p>
                ) : (
                  dettaglioCodice.pagamenti?.map((p, idx) => (
                    <div key={idx} style={{ 
                      padding: '10px 12px', 
                      borderBottom: '1px solid #f3f4f6',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: '500' }}>
                          {p.periodo_riferimento}
                        </div>
                        <div style={{ fontSize: 11, color: '#9ca3af' }}>
                          Pagato: {formatDateIT(p.data_pagamento)}
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        {p.importo_debito > 0 && (
                          <div style={{ fontSize: 14, fontWeight: 'bold', color: '#dc2626' }}>
                            {formatEuro(p.importo_debito)}
                          </div>
                        )}
                        {p.importo_credito > 0 && (
                          <div style={{ fontSize: 14, fontWeight: 'bold', color: '#16a34a' }}>
                            -{formatEuro(p.importo_credito)}
                          </div>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Info Box */}
      <div style={{ marginTop: 20, padding: 16, background: '#f0f9ff', borderRadius: 8, fontSize: 13, color: '#1535a8' }}>
        <strong>ℹ️ Riconciliazione a 3 Vie:</strong>
        <ul style={{ margin: '8px 0 0 16px', padding: 0 }}>
          <li><strong>Livello 1</strong>: F24 ricevuto dal commercialista (email)</li>
          <li><strong>Livello 2</strong>: Pagamento effettuato in banca</li>
          <li><strong>Livello 3</strong>: Quietanza dal cassetto fiscale (PDF)</li>
        </ul>
        <p style={{ marginTop: 8, color: '#6080a0' }}>
          💡 Clicca su un codice per vedere lo storico completo dei pagamenti
        </p>
      </div>
    </PageLayout>
  );
}

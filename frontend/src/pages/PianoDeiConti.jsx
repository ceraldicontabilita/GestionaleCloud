import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { formatEuro, STYLES, COLORS, button, badge } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { useAnnoGlobale } from '../contexts/AnnoContext';

const CATEGORIE = {
  attivo: { nome: "ATTIVO", color: "#2196f3", icon: "📊" },
  passivo: { nome: "PASSIVO", color: "#f44336", icon: "📉" },
  patrimonio_netto: { nome: "PATRIMONIO NETTO", color: "#9c27b0", icon: "💎" },
  ricavi: { nome: "RICAVI", color: "#4caf50", icon: "📈" },
  costi: { nome: "COSTI", color: "#ff9800", icon: "💸" }
};

export default function PianoDeiConti() {
  const [_conti, setConti] = useState([]);
  const [grouped, setGrouped] = useState({});
  const [regole, setRegole] = useState([]);
  const [bilancio, setBilancio] = useState(null);
  const [loading, setLoading] = useState(true);

  // Drawer dettaglio conto
  const [selectedConto, setSelectedConto] = useState(null);
  const [contoDetail, setContoDetail]     = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const openContoDetail = useCallback(async (conto) => {
    setSelectedConto(conto);
    setContoDetail(null);
    setLoadingDetail(true);
    const annoCorrente = new Date().getFullYear();
    try {
      const res = await api.get(`/api/piano-conti/conto/${conto.codice}/movimenti?limit=40&anno=${annoCorrente}`);
      setContoDetail(res.data);
    } catch { /* mostra solo info base */ } finally { setLoadingDetail(false); }
  }, []);

  const closeDrawer = () => { setSelectedConto(null); setContoDetail(null); };
  // URL Tab Support
  const navigate = useNavigate();
  const location = useLocation();
  
  const getTabFromPath = () => {
    const path = location.pathname;
    const match = path.match(/\/piano-dei-conti\/([\w-]+)/);
    return match ? match[1] : 'conti';
  };
  
  const [activeTab, setActiveTab] = useState(getTabFromPath());
  
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    navigate(`/piano-dei-conti/${tabId}`);
  };
  
  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setActiveTab(tab);
  }, [location.pathname]);
  const [expandedCategories, setExpandedCategories] = useState(['attivo', 'passivo', 'costi']);
  
  // Modal nuovo conto
  const [showNewConto, setShowNewConto] = useState(false);
  const [newConto, setNewConto] = useState({ codice: '', nome: '', categoria: 'costi', natura: 'economico' });
  
  // Modal nuova regola
  const [showNewRegola, setShowNewRegola] = useState(false);
  const [newRegola, setNewRegola] = useState({ tipo: 'fornitore', pattern: '', conto_dare: '', conto_avere: '', descrizione: '' });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [contiRes, regoleRes, bilancioRes] = await Promise.all([
        api.get('/api/piano-conti/'),
        api.get('/api/piano-conti/regole'),
        api.get('/api/piano-conti/bilancio')
      ]);
      
      setConti(contiRes.data.conti || []);
      setGrouped(contiRes.data.grouped || {});
      setRegole(regoleRes.data.regole || []);
      setBilancio(bilancioRes.data);
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
    }
  };

  const toggleCategory = (cat) => {
    setExpandedCategories(prev => 
      prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]
    );
  };

  const handleCreateConto = async () => {
    if (!newConto.codice || !newConto.nome) {
      alert('Codice e nome sono obbligatori');
      return;
    }
    try {
      await api.post('/api/piano-conti/', newConto);
      setShowNewConto(false);
      setNewConto({ codice: '', nome: '', categoria: 'costi', natura: 'economico' });
      loadData();
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleCreateRegola = async () => {
    if (!newRegola.pattern || !newRegola.conto_dare) {
      alert('Pattern e conto DARE sono obbligatori');
      return;
    }
    try {
      await api.post('/api/piano-conti/regole', newRegola);
      setShowNewRegola(false);
      setNewRegola({ tipo: 'fornitore', pattern: '', conto_dare: '', conto_avere: '', descrizione: '' });
      loadData();
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center' }}>Caricamento Piano dei Conti...</div>;
  }

  return (
    <PageLayout title="Piano dei Conti" subtitle="Contabilità Generale - Sistema di Partita Doppia">
    <div style={{ maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 'clamp(20px, 5vw, 28px)', color: '#1e3a5f' }}>
          📒 Piano dei Conti
        </h1>
        <p style={{ color: '#666', margin: '5px 0 0 0' }}>
          Contabilità Generale - Sistema di Partita Doppia
        </p>
      </div>

      {/* Bilancio Summary Cards */}
      {bilancio && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 15, marginBottom: 25 }}>
          <div style={{ background: '#e3f2fd', borderRadius: 12, padding: 15, borderLeft: '4px solid #2196f3' }}>
            <div style={{ fontSize: 12, color: '#1565c0', marginBottom: 5 }}>Totale Attivo</div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#0d47a1' }}>
              {formatEuro(bilancio.stato_patrimoniale.attivo.totale)}
            </div>
          </div>
          <div style={{ background: '#ffebee', borderRadius: 12, padding: 15, borderLeft: '4px solid #f44336' }}>
            <div style={{ fontSize: 12, color: '#c62828', marginBottom: 5 }}>Totale Passivo</div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#b71c1c' }}>
              {formatEuro(bilancio.stato_patrimoniale.passivo.totale)}
            </div>
          </div>
          <div style={{ background: '#e8f5e9', borderRadius: 12, padding: 15, borderLeft: '4px solid #4caf50' }}>
            <div style={{ fontSize: 12, color: '#2e7d32', marginBottom: 5 }}>Totale Ricavi</div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#1b5e20' }}>
              {formatEuro(bilancio.conto_economico.ricavi.totale)}
            </div>
          </div>
          <div style={{ background: '#fff3e0', borderRadius: 12, padding: 15, borderLeft: '4px solid #ff9800' }}>
            <div style={{ fontSize: 12, color: '#e65100', marginBottom: 5 }}>Totale Costi</div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#bf360c' }}>
              {formatEuro(bilancio.conto_economico.costi.totale)}
            </div>
          </div>
          <div style={{ 
            background: bilancio.conto_economico.risultato >= 0 ? '#e8f5e9' : '#ffebee', 
            borderRadius: 12, 
            padding: 15, 
            borderLeft: `4px solid ${bilancio.conto_economico.risultato >= 0 ? '#4caf50' : '#f44336'}`
          }}>
            <div style={{ fontSize: 12, color: bilancio.conto_economico.risultato >= 0 ? '#2e7d32' : '#c62828', marginBottom: 5 }}>
              {bilancio.conto_economico.risultato >= 0 ? 'Utile' : 'Perdita'}
            </div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: bilancio.conto_economico.risultato >= 0 ? '#1b5e20' : '#b71c1c' }}>
              {formatEuro(Math.abs(bilancio.conto_economico.risultato))}
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        {['conti', 'regole'].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '12px 24px',
              background: activeTab === tab ? '#1e3a5f' : '#e5e7eb',
              color: activeTab === tab ? 'white' : '#374151',
              border: 'none',
              borderRadius: 8,
              fontWeight: 'bold',
              cursor: 'pointer'
            }}
          >
            {tab === 'conti' ? '📊 Piano dei Conti' : '⚙️ Regole Categorizzazione'}
          </button>
        ))}
      </div>

      {/* Piano dei Conti */}
      {activeTab === 'conti' && (
        <>
          <div style={{ marginBottom: 15 }}>
            <button
              onClick={() => setShowNewConto(true)}
              data-testid="new-conto-btn"
              style={{
                padding: '10px 20px',
                background: '#4caf50',
                color: 'white',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer',
                fontWeight: 'bold'
              }}
            >
              ➕ Nuovo Conto
            </button>
          </div>

          <div style={{ display: 'grid', gap: 15 }}>
            {Object.entries(CATEGORIE).map(([key, cat]) => (
              <div key={key} style={{ 
                background: 'white', 
                borderRadius: 12, 
                overflow: 'hidden',
                border: '1px solid #e5e7eb'
              }}>
                {/* Category Header */}
                <div 
                  onClick={() => toggleCategory(key)}
                  style={{ 
                    padding: 15, 
                    background: cat.color + '15',
                    borderLeft: `4px solid ${cat.color}`,
                    cursor: 'pointer',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 24 }}>{cat.icon}</span>
                    <div>
                      <div style={{ fontWeight: 'bold', color: cat.color }}>{cat.nome}</div>
                      <div style={{ fontSize: 12, color: '#666' }}>
                        {grouped[key]?.length || 0} conti
                      </div>
                    </div>
                  </div>
                  <span style={{ fontSize: 20 }}>
                    {expandedCategories.includes(key) ? '▼' : '▶'}
                  </span>
                </div>

                {/* Category Conti */}
                {expandedCategories.includes(key) && (
                  <div style={{ padding: 15 }}>
                    {(grouped[key] || []).length === 0 ? (
                      <div style={{ color: '#999', textAlign: 'center', padding: 20 }}>
                        Nessun conto in questa categoria
                      </div>
                    ) : (
                      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                          <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                            <th style={{ padding: 10, textAlign: 'left', fontWeight: 600 }}>Codice</th>
                            <th style={{ padding: 10, textAlign: 'left', fontWeight: 600 }}>Nome Conto</th>
                            <th style={{ padding: 10, textAlign: 'center', fontWeight: 600 }}>Natura</th>
                            <th style={{ padding: 10, textAlign: 'right', fontWeight: 600 }}>Saldo</th>
                          </tr>
                        </thead>
                        <tbody>
                          {grouped[key].map((conto, idx) => (
                            <tr
                              key={conto.id}
                              data-testid={`conto-row-${conto.codice}`}
                              onClick={() => openContoDetail(conto)}
                              style={{ 
                                borderBottom: '1px solid #eee',
                                background: selectedConto?.codice === conto.codice
                                  ? cat.color + '18'
                                  : idx % 2 === 0 ? 'white' : '#fafafa',
                                cursor: 'pointer',
                                transition: 'background 0.15s',
                              }}
                              onMouseEnter={e => { e.currentTarget.style.background = cat.color + '22'; }}
                              onMouseLeave={e => { e.currentTarget.style.background = selectedConto?.codice === conto.codice ? cat.color + '18' : idx % 2 === 0 ? 'white' : '#fafafa'; }}
                            >
                              <td style={{ padding: 10, fontFamily: 'monospace', fontWeight: 'bold' }}>
                                <span style={{ color: cat.color }}>{conto.codice}</span>
                                <span style={{ color: '#bbb', marginLeft: 6, fontSize: 11 }}>›</span>
                              </td>
                              <td style={{ padding: 10 }}>{conto.nome}</td>
                              <td style={{ padding: 10, textAlign: 'center' }}>
                                <span style={{
                                  padding: '2px 8px',
                                  borderRadius: 4,
                                  fontSize: 11,
                                  background: conto.natura === 'finanziario' ? '#e3f2fd' : '#f3e5f5',
                                  color: conto.natura === 'finanziario' ? '#1565c0' : '#7b1fa2'
                                }}>
                                  {conto.natura}
                                </span>
                              </td>
                              <td style={{ 
                                padding: 10, 
                                textAlign: 'right', 
                                fontWeight: 'bold',
                                color: conto.saldo >= 0 ? '#2e7d32' : '#c62828'
                              }}>
                                {formatEuro(conto.saldo)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {/* Regole Categorizzazione */}
      {activeTab === 'regole' && (
        <>
          <div style={{ marginBottom: 15 }}>
            <button
              onClick={() => setShowNewRegola(true)}
              data-testid="new-regola-btn"
              style={{
                padding: '10px 20px',
                background: '#ff9800',
                color: 'white',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer',
                fontWeight: 'bold'
              }}
            >
              ➕ Nuova Regola
            </button>
          </div>

          <div style={{ background: '#fff3e0', padding: 15, borderRadius: 8, marginBottom: 20, fontSize: 13 }}>
            <strong>Come funzionano le regole:</strong>
            <ul style={{ margin: '10px 0 0 0', paddingLeft: 20 }}>
              <li>Le regole determinano automaticamente quali conti usare per registrare le fatture</li>
              <li><strong>Pattern</strong>: parola chiave da cercare (es. "ENEL" per bollette elettricità)</li>
              <li><strong>Conto DARE</strong>: conto che aumenta (es. costo utenze)</li>
              <li><strong>Conto AVERE</strong>: conto che diminuisce (es. debito fornitore)</li>
            </ul>
          </div>

          <div style={{ background: 'white', borderRadius: 12, overflow: 'hidden', border: '1px solid #e5e7eb' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e5e7eb' }}>
                  <th style={{ padding: 12, textAlign: 'left' }}>Tipo</th>
                  <th style={{ padding: 12, textAlign: 'left' }}>Pattern</th>
                  <th style={{ padding: 12, textAlign: 'left' }}>Conto DARE</th>
                  <th style={{ padding: 12, textAlign: 'left' }}>Conto AVERE</th>
                  <th style={{ padding: 12, textAlign: 'left' }}>Descrizione</th>
                  <th style={{ padding: 12, textAlign: 'center' }}>Stato</th>
                </tr>
              </thead>
              <tbody>
                {regole.map((regola, idx) => (
                  <tr key={regola.id} style={{ 
                    borderBottom: '1px solid #eee',
                    background: idx % 2 === 0 ? 'white' : '#fafafa'
                  }}>
                    <td style={{ padding: 12 }}>
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: 4,
                        fontSize: 11,
                        background: regola.tipo === 'fornitore' ? '#e8f5e9' : '#e3f2fd',
                        color: regola.tipo === 'fornitore' ? '#2e7d32' : '#1565c0'
                      }}>
                        {regola.tipo}
                      </span>
                    </td>
                    <td style={{ padding: 12, fontFamily: 'monospace', fontWeight: 'bold' }}>
                      {regola.pattern}
                    </td>
                    <td style={{ padding: 12, fontFamily: 'monospace' }}>{regola.conto_dare}</td>
                    <td style={{ padding: 12, fontFamily: 'monospace' }}>{regola.conto_avere}</td>
                    <td style={{ padding: 12, fontSize: 13 }}>{regola.descrizione}</td>
                    <td style={{ padding: 12, textAlign: 'center' }}>
                      <span style={{
                        width: 10,
                        height: 10,
                        borderRadius: '50%',
                        background: regola.attiva ? '#4caf50' : '#9e9e9e',
                        display: 'inline-block'
                      }} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Modal Nuovo Conto */}
      {showNewConto && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }} onClick={() => setShowNewConto(false)}>
          <div style={{
            background: 'white', borderRadius: 12, padding: 24, maxWidth: 450, width: '90%'
          }} onClick={e => e.stopPropagation()}>
            <h2 style={{ marginTop: 0 }}>➕ Nuovo Conto</h2>
            
            <div style={{ display: 'grid', gap: 15 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 5, fontWeight: 'bold', fontSize: 13 }}>
                  Codice (es. 05.02.03) *
                </label>
                <input
                  type="text"
                  value={newConto.codice}
                  onChange={(e) => setNewConto({ ...newConto, codice: e.target.value })}
                  placeholder="05.02.03"
                  style={{ padding: 12, width: '100%', borderRadius: 8, border: '1px solid #ddd', fontFamily: 'monospace' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 5, fontWeight: 'bold', fontSize: 13 }}>
                  Nome Conto *
                </label>
                <input
                  type="text"
                  value={newConto.nome}
                  onChange={(e) => setNewConto({ ...newConto, nome: e.target.value })}
                  placeholder="Spese telefoniche"
                  style={{ padding: 12, width: '100%', borderRadius: 8, border: '1px solid #ddd' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 5, fontWeight: 'bold', fontSize: 13 }}>
                  Categoria *
                </label>
                <select
                  value={newConto.categoria}
                  onChange={(e) => setNewConto({ ...newConto, categoria: e.target.value })}
                  style={{ padding: 12, width: '100%', borderRadius: 8, border: '1px solid #ddd' }}
                >
                  {Object.entries(CATEGORIE).map(([key, cat]) => (
                    <option key={key} value={key}>{cat.icon} {cat.nome}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 5, fontWeight: 'bold', fontSize: 13 }}>
                  Natura
                </label>
                <select
                  value={newConto.natura}
                  onChange={(e) => setNewConto({ ...newConto, natura: e.target.value })}
                  style={{ padding: 12, width: '100%', borderRadius: 8, border: '1px solid #ddd' }}
                >
                  <option value="economico">Economico</option>
                  <option value="finanziario">Finanziario</option>
                </select>
              </div>
            </div>
            
            <div style={{ display: 'flex', gap: 10, marginTop: 20, justifyContent: 'flex-end' }}>
              <button onClick={() => setShowNewConto(false)} style={{ padding: '10px 20px', background: '#9e9e9e', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer' }}>
                Annulla
              </button>
              <button onClick={handleCreateConto} style={{ padding: '10px 20px', background: '#4caf50', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 'bold' }}>
                ➕ Crea Conto
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Nuova Regola */}
      {showNewRegola && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }} onClick={() => setShowNewRegola(false)}>
          <div style={{
            background: 'white', borderRadius: 12, padding: 24, maxWidth: 500, width: '90%'
          }} onClick={e => e.stopPropagation()}>
            <h2 style={{ marginTop: 0 }}>⚙️ Nuova Regola Categorizzazione</h2>
            
            <div style={{ display: 'grid', gap: 15 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 5, fontWeight: 'bold', fontSize: 13 }}>
                  Tipo Regola
                </label>
                <select
                  value={newRegola.tipo}
                  onChange={(e) => setNewRegola({ ...newRegola, tipo: e.target.value })}
                  style={{ padding: 12, width: '100%', borderRadius: 8, border: '1px solid #ddd' }}
                >
                  <option value="fornitore">Per Fornitore (nome)</option>
                  <option value="tipo_documento">Per Tipo Documento</option>
                  <option value="pagamento">Per Metodo Pagamento</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 5, fontWeight: 'bold', fontSize: 13 }}>
                  Pattern (Regex) *
                </label>
                <input
                  type="text"
                  value={newRegola.pattern}
                  onChange={(e) => setNewRegola({ ...newRegola, pattern: e.target.value })}
                  placeholder="ENEL|EDISON"
                  style={{ padding: 12, width: '100%', borderRadius: 8, border: '1px solid #ddd', fontFamily: 'monospace' }}
                />
                <div style={{ fontSize: 11, color: '#666', marginTop: 3 }}>
                  Usa | per alternative (es. ENEL|EDISON per luce o gas)
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div>
                  <label style={{ display: 'block', marginBottom: 5, fontWeight: 'bold', fontSize: 13 }}>
                    Conto DARE *
                  </label>
                  <input
                    type="text"
                    value={newRegola.conto_dare}
                    onChange={(e) => setNewRegola({ ...newRegola, conto_dare: e.target.value })}
                    placeholder="05.02.02"
                    style={{ padding: 12, width: '100%', borderRadius: 8, border: '1px solid #ddd', fontFamily: 'monospace' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: 5, fontWeight: 'bold', fontSize: 13 }}>
                    Conto AVERE
                  </label>
                  <input
                    type="text"
                    value={newRegola.conto_avere}
                    onChange={(e) => setNewRegola({ ...newRegola, conto_avere: e.target.value })}
                    placeholder="02.01.01"
                    style={{ padding: 12, width: '100%', borderRadius: 8, border: '1px solid #ddd', fontFamily: 'monospace' }}
                  />
                </div>
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 5, fontWeight: 'bold', fontSize: 13 }}>
                  Descrizione
                </label>
                <input
                  type="text"
                  value={newRegola.descrizione}
                  onChange={(e) => setNewRegola({ ...newRegola, descrizione: e.target.value })}
                  placeholder="Utenze elettricità"
                  style={{ padding: 12, width: '100%', borderRadius: 8, border: '1px solid #ddd' }}
                />
              </div>
            </div>
            
            <div style={{ display: 'flex', gap: 10, marginTop: 20, justifyContent: 'flex-end' }}>
              <button onClick={() => setShowNewRegola(false)} style={{ padding: '10px 20px', background: '#9e9e9e', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer' }}>
                Annulla
              </button>
              <button onClick={handleCreateRegola} style={{ padding: '10px 20px', background: '#ff9800', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 'bold' }}>
                ⚙️ Crea Regola
              </button>
            </div>
          </div>
        </div>
      )}
    </div>

    {/* ─── DRAWER DETTAGLIO CONTO ─── */}
    {selectedConto && (
      <>
        {/* Overlay semi-trasparente */}
        <div
          onClick={closeDrawer}
          style={{
            position: 'fixed', inset: 0,
            background: 'rgba(0,0,0,0.35)',
            zIndex: 1000,
          }}
        />

        {/* Pannello laterale destro */}
        <div
          data-testid="conto-detail-drawer"
          style={{
            position: 'fixed', top: 0, right: 0,
            width: 580, height: '100vh',
            background: 'white',
            boxShadow: '-4px 0 30px rgba(0,0,0,0.18)',
            zIndex: 1001,
            display: 'flex', flexDirection: 'column',
            overflowY: 'auto',
          }}
        >
          {/* Header */}
          {(() => {
            const catKey  = selectedConto.categoria?.toLowerCase().replace(' ', '_') || 'costi';
            const catInfo = CATEGORIE[catKey] || { nome: selectedConto.categoria, color: '#607d8b', icon: '📄' };
            return (
              <>
                <div style={{
                  background: catInfo.color,
                  padding: '20px 24px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                }}>
                  <div>
                    <div style={{ color: 'rgba(255,255,255,0.75)', fontSize: 12, marginBottom: 4 }}>
                      {catInfo.icon} {catInfo.nome}
                    </div>
                    <div style={{ color: 'white', fontFamily: 'monospace', fontSize: 22, fontWeight: 'bold' }}>
                      {selectedConto.codice}
                    </div>
                    <div style={{ color: 'rgba(255,255,255,0.9)', fontSize: 16, marginTop: 4 }}>
                      {selectedConto.nome}
                    </div>
                  </div>
                  <button
                    onClick={closeDrawer}
                    data-testid="close-conto-drawer"
                    style={{ background: 'rgba(255,255,255,0.2)', border: 'none', borderRadius: 8, cursor: 'pointer', color: 'white', fontSize: 20, padding: '4px 12px' }}
                  >
                    ✕
                  </button>
                </div>

                {/* Saldo + info */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 1, background: '#f0f0f0' }}>
                  {[
                    { label: 'Saldo', val: formatEuro(selectedConto.saldo || 0), color: (selectedConto.saldo || 0) >= 0 ? '#4caf50' : '#f44336' },
                    { label: 'Natura', val: selectedConto.natura || '—', color: '#607d8b' },
                    { label: 'Stato', val: selectedConto.attivo ? 'Attivo' : 'Inattivo', color: selectedConto.attivo ? '#4caf50' : '#999' },
                  ].map(({ label, val, color }) => (
                    <div key={label} style={{ background: 'white', padding: '14px 18px' }}>
                      <div style={{ fontSize: 11, color: '#999', marginBottom: 4 }}>{label}</div>
                      <div style={{ fontWeight: 'bold', color, fontSize: 16 }}>{val}</div>
                    </div>
                  ))}
                </div>
              </>
            );
          })()}

          {/* Corpo drawer: movimenti */}
          <div style={{ flex: 1, padding: '18px 24px', overflowY: 'auto' }}>
            {loadingDetail ? (
              <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
                Caricamento movimenti…
              </div>
            ) : contoDetail ? (
              <>
                {/* Riepilogo */}
                <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
                  {[
                    { label: 'Movimenti', val: contoDetail.totale_movimenti },
                    { label: 'Totale periodo', val: formatEuro(contoDetail.totale_importo) },
                  ].map(({ label, val }) => (
                    <div key={label} style={{ flex: 1, background: '#f8fafc', borderRadius: 8, padding: 12, textAlign: 'center' }}>
                      <div style={{ fontSize: 11, color: '#999' }}>{label}</div>
                      <div style={{ fontWeight: 'bold', fontSize: 18, marginTop: 4 }}>{val}</div>
                    </div>
                  ))}
                </div>

                {/* Fonte dati */}
                {contoDetail.fonte && contoDetail.fonte !== 'nessuna' && (
                  <div style={{ fontSize: 11, color: '#888', background: '#f0f4ff', borderRadius: 6, padding: '6px 10px', marginBottom: 12 }}>
                    Fonte: <strong>{contoDetail.fonte}</strong>
                  </div>
                )}

                {/* Tabella movimenti */}
                {contoDetail.movimenti?.length > 0 ? (
                  <>
                    <div style={{ fontWeight: 600, fontSize: 13, color: '#444', marginBottom: 8 }}>
                      Movimenti ({new Date().getFullYear()})
                    </div>
                    <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                        <thead>
                          <tr style={{ background: '#f8fafc' }}>
                            <th style={{ padding: '8px 12px', textAlign: 'left', color: '#666', fontWeight: 600 }}>Data</th>
                            <th style={{ padding: '8px 12px', textAlign: 'left', color: '#666', fontWeight: 600 }}>Descrizione</th>
                            <th style={{ padding: '8px 12px', textAlign: 'right', color: '#666', fontWeight: 600 }}>Importo</th>
                          </tr>
                        </thead>
                        <tbody>
                          {contoDetail.movimenti.map((mov, i) => (
                            <tr key={i} style={{ borderTop: '1px solid #f0f0f0', background: i % 2 === 0 ? 'white' : '#fafafa' }}>
                              <td style={{ padding: '8px 12px', fontFamily: 'monospace', fontSize: 12, whiteSpace: 'nowrap' }}>
                                {String(mov.data || '—').slice(0, 10)}
                              </td>
                              <td style={{ padding: '8px 12px', color: '#333', maxWidth: 260 }}>
                                <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                                     title={mov.descrizione}>
                                  {(mov.descrizione || '—').slice(0, 65)}
                                </div>
                                {mov.categoria && (
                                  <div style={{ fontSize: 10, color: '#aaa', marginTop: 2 }}>{mov.categoria}</div>
                                )}
                              </td>
                              <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 'bold',
                                color: mov.tipo === 'entrata' ? '#4caf50' : '#f44336' }}>
                                {mov.tipo === 'entrata' ? '+' : '-'}{formatEuro(mov.importo)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                ) : (
                  <div style={{ textAlign: 'center', padding: 28, color: '#bbb', fontSize: 13,
                    background: '#f8fafc', borderRadius: 8 }}>
                    {contoDetail.nota || 'Nessun movimento disponibile per questo conto.'}
                  </div>
                )}
              </>
            ) : (
              <div style={{ textAlign: 'center', padding: 40, color: '#bbb' }}>
                Nessun dettaglio disponibile
              </div>
            )}
          </div>
        </div>
      </>
    )}

    </PageLayout>
  );
}

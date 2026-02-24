import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { formatEuro, STYLES, COLORS, button, badge } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { useAnnoGlobale } from '../contexts/AnnoContext';

const CATEGORIE = {
  attivo: { nome: "ATTIVO", color: "#2196f3", icon: "📊" },
  passivo: { nome: "PASSIVO", color: "#f44336", icon: "📉" },
  patrimonio_netto: { nome: "PATRIMONIO NETTO", color: "#9c27b0", icon: "💎" },
  ricavi: { nome: "RICAVI", color: "#15803d", icon: "📈" },
  costi: { nome: "COSTI", color: "#d97706", icon: "💸" }
};

export default function PianoDeiConti() {
  const [_conti, setConti] = useState([]);
  const [grouped, setGrouped] = useState({});
  const [regole, setRegole] = useState([]);
  const [bilancio, setBilancio] = useState(null);
  const [loading, setLoading] = useState(true);
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
        <h1 style={{ margin: 0, fontSize: 'clamp(20px, 5vw, 28px)', color: '#1535a8' }}>
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
          <div style={{ background: '#e8f5e9', borderRadius: 12, padding: 15, borderLeft: '4px solid #15803d' }}>
            <div style={{ fontSize: 12, color: '#2e7d32', marginBottom: 5 }}>Totale Ricavi</div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#1b5e20' }}>
              {formatEuro(bilancio.conto_economico.ricavi.totale)}
            </div>
          </div>
          <div style={{ background: '#fff3e0', borderRadius: 12, padding: 15, borderLeft: '4px solid #d97706' }}>
            <div style={{ fontSize: 12, color: '#e65100', marginBottom: 5 }}>Totale Costi</div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#bf360c' }}>
              {formatEuro(bilancio.conto_economico.costi.totale)}
            </div>
          </div>
          <div style={{ 
            background: bilancio.conto_economico.risultato >= 0 ? '#e8f5e9' : '#ffebee', 
            borderRadius: 12, 
            padding: 15, 
            borderLeft: `4px solid ${bilancio.conto_economico.risultato >= 0 ? '#15803d' : '#f44336'}`
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
              background: activeTab === tab ? '#1535a8' : '#e5e7eb',
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
                background: '#15803d',
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
                            <tr key={conto.id} style={{ 
                              borderBottom: '1px solid #eee',
                              background: idx % 2 === 0 ? 'white' : '#fafafa'
                            }}>
                              <td style={{ padding: 10, fontFamily: 'monospace', fontWeight: 'bold' }}>
                                {conto.codice}
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
                background: '#d97706',
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
                        background: regola.attiva ? '#15803d' : '#9e9e9e',
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
              <button onClick={handleCreateConto} style={{ padding: '10px 20px', background: '#15803d', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 'bold' }}>
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
              <button onClick={handleCreateRegola} style={{ padding: '10px 20px', background: '#d97706', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 'bold' }}>
                ⚙️ Crea Regola
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
    </PageLayout>
  );
}

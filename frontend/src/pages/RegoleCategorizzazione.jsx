import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { STYLES, COLORS, button, badge, formatEuro, formatDateIT } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';

const CATEGORIA_COLORS = {
  acquisti_merci: { bg: '#dbeafe', text: '#1535a8', label: 'Acquisti Merci' },
  acquisti_servizi: { bg: '#fef3c7', text: '#92400e', label: 'Servizi' },
  utenze: { bg: '#fce7f3', text: '#9d174d', label: 'Utenze' },
  affitti: { bg: '#d1fae5', text: '#065f46', label: 'Affitti' },
  assicurazioni: { bg: '#e0e7ff', text: '#3730a3', label: 'Assicurazioni' },
  manutenzioni: { bg: '#fed7aa', text: '#9a3412', label: 'Manutenzioni' },
  consulenze: { bg: '#f5d0fe', text: '#86198f', label: 'Consulenze' },
  trasporti: { bg: '#a5f3fc', text: '#0e7490', label: 'Trasporti' },
  noleggi: { bg: '#fda4af', text: '#9f1239', label: 'Noleggi' },
  telefonia: { bg: '#c4b5fd', text: '#5b21b6', label: 'Telefonia' },
  pubblicita: { bg: '#fde68a', text: '#92400e', label: 'Pubblicità' },
  non_categorizzato: { bg: '#e5e7eb', text: '#374151', label: 'Non Categorizzato' }
};

// Stat Card Component
const StatCard = ({ label, value, color, icon }) => (
  <div style={{
    background: 'white',
    borderRadius: 12,
    padding: 16,
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    border: '1px solid #e5e7eb'
  }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
      {icon && <span style={{ fontSize: 18 }}>{icon}</span>}
      <span style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase', fontWeight: 500 }}>{label}</span>
    </div>
    <div style={{ fontSize: 28, fontWeight: 700, color: color }}>{value}</div>
  </div>
);

export default function RegoleCategorizzazione() {
  const [regole, setRegole] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState(null);
  const [activeTab, setActiveTab] = useState('associazioni');
  const [searchTerm, setSearchTerm] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [newRule, setNewRule] = useState({ pattern: '', categoria: '', note: '' });
  const [editingCategoria, setEditingCategoria] = useState(null);
  const [ricategorizzando, setRicategorizzando] = useState(false);

  const fetchRegole = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/regole/regole');
      setRegole(res.data);
    } catch (err) {
      console.error('Errore caricamento regole:', err);
      setMessage({ type: 'error', text: 'Errore nel caricamento delle regole' });
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchRegole();
  }, [fetchRegole]);

  const handleDownloadExcel = async () => {
    try {
      const res = await api.get('/api/regole/download-regole', { responseType: 'blob' });
      const url = window.URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'regole_categorizzazione.xlsx';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setMessage({ type: 'success', text: '✅ File Excel scaricato!' });
    } catch (err) {
      setMessage({ type: 'error', text: '❌ Errore nel download' });
    }
  };

  const handleUploadExcel = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await api.post('/api/regole/upload-regole', formData);
      if (res.data.success) {
        setMessage({ type: 'success', text: `✅ Caricate: ${res.data.regole_fornitori_caricate} fornitori, ${res.data.regole_descrizioni_caricate} descrizioni` });
        fetchRegole();
      }
    } catch (err) {
      setMessage({ type: 'error', text: '❌ Errore nel caricamento' });
    }
    setUploading(false);
    event.target.value = '';
  };

  const handleAddRule = async () => {
    if (!newRule.pattern || !newRule.categoria) {
      setMessage({ type: 'error', text: '⚠️ Pattern e categoria sono obbligatori' });
      return;
    }
    try {
      const res = await api.post('/api/regole/regole/fornitore', newRule);
      if (res.data.success) {
        setMessage({ type: 'success', text: '✅ Regola aggiunta!' });
        setShowAddForm(false);
        setNewRule({ pattern: '', categoria: '', note: '' });
        fetchRegole();
      }
    } catch (err) {
      setMessage({ type: 'error', text: '❌ Errore nell\'aggiunta della regola' });
    }
  };

  const handleDeleteRule = async (tipo, pattern) => {
    
    try {
      await api.delete(`/api/regole/regole/${tipo}/${encodeURIComponent(pattern)}`);
      setMessage({ type: 'success', text: '✅ Regola eliminata!' });
      fetchRegole();
    } catch (err) {
      setMessage({ type: 'error', text: '❌ Errore nell\'eliminazione' });
    }
  };

  const handleRicategorizza = async () => {
    
    setRicategorizzando(true);
    try {
      const res = await api.post('/api/contabilita/ricategorizza-fatture');
      if (res.data.success) {
        setMessage({ type: 'success', text: `✅ Ricategorizzate ${res.data.fatture_processate} fatture!` });
      }
    } catch (err) {
      setMessage({ type: 'error', text: '❌ Errore nella ricategorizzazione' });
    }
    setRicategorizzando(false);
  };

  const filteredRules = (rules) => {
    if (!searchTerm) return rules || [];
    const term = searchTerm.toLowerCase();
    return (rules || []).filter(r => 
      r.pattern?.toLowerCase().includes(term) || 
      r.categoria?.toLowerCase().includes(term)
    );
  };

  const getAssociazioni = () => {
    const assoc = {};
    (regole?.regole_fornitori || []).forEach(r => {
      const cat = r.categoria || 'non_categorizzato';
      if (!assoc[cat]) assoc[cat] = { fornitori: [], descrizioni: [] };
      assoc[cat].fornitori.push(r);
    });
    (regole?.regole_descrizioni || []).forEach(r => {
      const cat = r.categoria || 'non_categorizzato';
      if (!assoc[cat]) assoc[cat] = { fornitori: [], descrizioni: [] };
      assoc[cat].descrizioni.push(r);
    });
    return assoc;
  };

  const getCategoryStyle = (catName) => {
    return CATEGORIA_COLORS[catName] || CATEGORIA_COLORS.non_categorizzato;
  };

  const formatCategoryName = (name) => {
    return (name || '').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  };

  if (loading) {
    return (
      <div style={{ padding: 24, textAlign: 'center', paddingTop: 100 }}>
        <div style={{ fontSize: 32, marginBottom: 16 }}>⏳</div>
        <div style={{ color: '#6b7280' }}>Caricamento regole...</div>
      </div>
    );
  }

  const associazioni = getAssociazioni();
  const totaleRegole = (regole?.regole_fornitori?.length || 0) + (regole?.regole_descrizioni?.length || 0);
  const totaleCategorie = Object.keys(associazioni).length;

  return (
    <PageLayout title="Regole di Categorizzazione" subtitle="Associazioni Fornitore/Descrizione → Categoria Contabile">
    <div data-testid="regole-categorizzazione-page">
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: '#1535a8', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 10 }}>
          <span>⚙️</span> Regole di Categorizzazione
        </h1>
        <p style={{ color: '#64748b' }}>
          Associazioni Fornitore/Descrizione → Categoria Contabile
        </p>
      </div>

      {/* Messaggio */}
      {message && (
        <div style={{
          padding: 16,
          borderRadius: 8,
          marginBottom: 20,
          background: message.type === 'success' ? '#dcfce7' : message.type === 'error' ? '#fee2e2' : '#dbeafe',
          color: message.type === 'success' ? '#166534' : message.type === 'error' ? '#991b1b' : '#1535a8',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          {message.text}
          <button onClick={() => setMessage(null)} style={{ cursor: 'pointer', background: 'none', border: 'none', fontSize: 18 }}>✕</button>
        </div>
      )}

      {/* Statistiche */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 24 }}>
        <StatCard label="Regole Fornitori" value={regole?.regole_fornitori?.length || 0} color="#1535a8" icon="🏢" />
        <StatCard label="Regole Descrizioni" value={regole?.regole_descrizioni?.length || 0} color="#8b5cf6" icon="📝" />
        <StatCard label="Categorie" value={totaleCategorie} color="#15803d" icon="📁" />
        <StatCard label="Totale Regole" value={totaleRegole} color="#d97706" icon="📊" />
      </div>

      {/* Azioni */}
      <div style={{ 
        display: 'flex', 
        gap: 12, 
        marginBottom: 20, 
        flexWrap: 'wrap',
        padding: 16,
        background: '#f8fafc',
        borderRadius: 12
      }}>
        <button
          onClick={handleDownloadExcel}
          style={{
            padding: '10px 20px',
            background: 'linear-gradient(135deg, #15803d, #059669)',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}
        >
          📥 Scarica Excel
        </button>
        
        <label style={{
          padding: '10px 20px',
          background: uploading ? '#9ca3af' : 'linear-gradient(135deg, #1535a8, #1d4ed8)',
          color: 'white',
          borderRadius: 8,
          cursor: uploading ? 'wait' : 'pointer',
          fontWeight: 600,
          display: 'flex',
          alignItems: 'center',
          gap: 8
        }}>
          📤 {uploading ? 'Caricamento...' : 'Carica Excel'}
          <input type="file" accept=".xlsx,.xls" onChange={handleUploadExcel} style={{ display: 'none' }} disabled={uploading} />
        </label>
        
        <button
          onClick={handleRicategorizza}
          disabled={ricategorizzando}
          style={{
            padding: '10px 20px',
            background: ricategorizzando ? '#9ca3af' : 'linear-gradient(135deg, #8b5cf6, #6d28d9)',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: ricategorizzando ? 'wait' : 'pointer',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}
        >
          🔄 {ricategorizzando ? 'Elaborazione...' : 'Applica alle Fatture'}
        </button>

        <button
          onClick={() => setShowAddForm(!showAddForm)}
          style={{
            padding: '10px 20px',
            background: 'linear-gradient(135deg, #d97706, #d97706)',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}
        >
          ➕ Nuova Regola
        </button>
      </div>

      {/* Form Nuova Regola */}
      {showAddForm && (
        <div style={{
          background: 'white',
          border: '1px solid #e5e7eb',
          borderRadius: 12,
          padding: 20,
          marginBottom: 20
        }}>
          <h3 style={{ marginTop: 0, marginBottom: 16 }}>➕ Aggiungi Nuova Regola</h3>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <input
              type="text"
              placeholder="Pattern fornitore (es. ENEL)"
              value={newRule.pattern}
              onChange={(e) => setNewRule({...newRule, pattern: e.target.value})}
              style={{ flex: 1, minWidth: 200, padding: '10px 14px', borderRadius: 8, border: '1px solid #d1d5db' }}
            />
            <select
              value={newRule.categoria}
              onChange={(e) => setNewRule({...newRule, categoria: e.target.value})}
              style={{ padding: '10px 14px', borderRadius: 8, border: '1px solid #d1d5db', minWidth: 180 }}
            >
              <option value="">-- Seleziona Categoria --</option>
              {Object.keys(CATEGORIA_COLORS).map(cat => (
                <option key={cat} value={cat}>{formatCategoryName(cat)}</option>
              ))}
            </select>
            <button
              onClick={handleAddRule}
              style={{
                padding: '10px 20px',
                background: '#15803d',
                color: 'white',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer'
              }}
            >
              ✅ Salva
            </button>
            <button
              onClick={() => setShowAddForm(false)}
              style={{
                padding: '10px 20px',
                background: '#6b7280',
                color: 'white',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer'
              }}
            >
              ✕ Annulla
            </button>
          </div>
        </div>
      )}

      {/* Filtri e Ricerca */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          type="text"
          placeholder="🔍 Cerca regola..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{ padding: '10px 14px', borderRadius: 8, border: '1px solid #e2e8f0', minWidth: 250 }}
        />
        
        <div style={{ display: 'flex', gap: 4, background: '#f1f5f9', padding: 4, borderRadius: 8 }}>
          {['associazioni', 'fornitori', 'descrizioni', 'categorie'].map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                padding: '8px 16px',
                background: activeTab === tab ? 'white' : 'transparent',
                border: 'none',
                borderRadius: 6,
                cursor: 'pointer',
                fontWeight: activeTab === tab ? 600 : 400,
                color: activeTab === tab ? '#1535a8' : '#64748b',
                boxShadow: activeTab === tab ? '0 1px 2px rgba(0,0,0,0.05)' : 'none',
                textTransform: 'capitalize'
              }}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div style={{ background: 'white', borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden' }}>
        
        {/* Tab Associazioni */}
        {activeTab === 'associazioni' && (
          <div style={{ padding: 20 }}>
            <div style={{ display: 'grid', gap: 16 }}>
              {Object.entries(associazioni).map(([categoria, data]) => {
                const style = getCategoryStyle(categoria);
                return (
                  <div key={categoria} style={{ border: '1px solid #e5e7eb', borderRadius: 12, overflow: 'hidden' }}>
                    <div style={{ 
                      padding: '12px 16px', 
                      background: style.bg, 
                      borderBottom: '1px solid #e5e7eb',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}>
                      <span style={{ fontWeight: 600, color: style.text }}>{formatCategoryName(categoria)}</span>
                      <span style={{ fontSize: 12, color: style.text }}>
                        {data.fornitori.length} fornitori, {data.descrizioni.length} descrizioni
                      </span>
                    </div>
                    <div style={{ padding: 12 }}>
                      {data.fornitori.length > 0 && (
                        <div style={{ marginBottom: 8 }}>
                          <span style={{ fontSize: 11, color: '#6b7280', textTransform: 'uppercase' }}>Fornitori:</span>
                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                            {data.fornitori.map((r, i) => (
                              <span key={i} style={{
                                padding: '4px 10px',
                                background: '#f1f5f9',
                                borderRadius: 6,
                                fontSize: 13,
                                display: 'flex',
                                alignItems: 'center',
                                gap: 6
                              }}>
                                {r.pattern}
                                <button
                                  onClick={() => handleDeleteRule('fornitore', r.pattern)}
                                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: 0 }}
                                >
                                  ✕
                                </button>
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {data.descrizioni.length > 0 && (
                        <div>
                          <span style={{ fontSize: 11, color: '#6b7280', textTransform: 'uppercase' }}>Descrizioni:</span>
                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                            {data.descrizioni.map((r, i) => (
                              <span key={i} style={{
                                padding: '4px 10px',
                                background: '#e0f2fe',
                                borderRadius: 6,
                                fontSize: 13,
                                display: 'flex',
                                alignItems: 'center',
                                gap: 6
                              }}>
                                {r.pattern}
                                <button
                                  onClick={() => handleDeleteRule('descrizione', r.pattern)}
                                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: 0 }}
                                >
                                  ✕
                                </button>
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Tab Fornitori */}
        {activeTab === 'fornitori' && (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f9fafb' }}>
                <th style={{ padding: 14, textAlign: 'left', fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb' }}>Pattern</th>
                <th style={{ padding: 14, textAlign: 'left', fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb' }}>Categoria</th>
                <th style={{ padding: 14, textAlign: 'center', fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb' }}>Azioni</th>
              </tr>
            </thead>
            <tbody>
              {filteredRules(regole?.regole_fornitori).map((r, i) => {
                const style = getCategoryStyle(r.categoria);
                return (
                  <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: 14, fontWeight: 500 }}>{r.pattern}</td>
                    <td style={{ padding: 14 }}>
                      <span style={{
                        padding: '4px 12px',
                        borderRadius: 9999,
                        fontSize: 12,
                        fontWeight: 500,
                        background: style.bg,
                        color: style.text
                      }}>
                        {formatCategoryName(r.categoria)}
                      </span>
                    </td>
                    <td style={{ padding: 14, textAlign: 'center' }}>
                      <button
                        onClick={() => handleDeleteRule('fornitore', r.pattern)}
                        style={{ padding: '6px 12px', background: '#fee2e2', color: '#991b1b', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12 }}
                      >
                        🗑️ Elimina
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {/* Tab Descrizioni */}
        {activeTab === 'descrizioni' && (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f9fafb' }}>
                <th style={{ padding: 14, textAlign: 'left', fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb' }}>Pattern</th>
                <th style={{ padding: 14, textAlign: 'left', fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb' }}>Categoria</th>
                <th style={{ padding: 14, textAlign: 'center', fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', borderBottom: '1px solid #e5e7eb' }}>Azioni</th>
              </tr>
            </thead>
            <tbody>
              {filteredRules(regole?.regole_descrizioni).map((r, i) => {
                const style = getCategoryStyle(r.categoria);
                return (
                  <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: 14, fontWeight: 500 }}>{r.pattern}</td>
                    <td style={{ padding: 14 }}>
                      <span style={{
                        padding: '4px 12px',
                        borderRadius: 9999,
                        fontSize: 12,
                        fontWeight: 500,
                        background: style.bg,
                        color: style.text
                      }}>
                        {formatCategoryName(r.categoria)}
                      </span>
                    </td>
                    <td style={{ padding: 14, textAlign: 'center' }}>
                      <button
                        onClick={() => handleDeleteRule('descrizione', r.pattern)}
                        style={{ padding: '6px 12px', background: '#fee2e2', color: '#991b1b', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12 }}
                      >
                        🗑️ Elimina
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {/* Tab Categorie */}
        {activeTab === 'categorie' && (
          <div style={{ padding: 20 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
              {(regole?.categorie || []).map((cat, i) => {
                const style = getCategoryStyle(cat.categoria);
                return (
                  <div key={i} style={{
                    background: style.bg,
                    borderRadius: 12,
                    padding: 16,
                    border: `1px solid ${style.text}20`
                  }}>
                    <div style={{ fontWeight: 600, color: style.text, marginBottom: 8 }}>
                      {formatCategoryName(cat.categoria)}
                    </div>
                    <div style={{ fontSize: 12, color: style.text, opacity: 0.8 }}>
                      <div>Conto: {cat.conto || '-'}</div>
                      <div>Ded. IRES: {cat.deducibilita_ires || 100}%</div>
                      <div>Ded. IRAP: {cat.deducibilita_irap || 100}%</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Info Box */}
      <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 12, padding: 16, marginTop: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <span>ℹ️</span>
          <strong style={{ color: '#1535a8' }}>Come funziona</strong>
        </div>
        <ul style={{ margin: 0, paddingLeft: 20, color: '#1535a8', fontSize: 13 }}>
          <li><strong>Regole Fornitori:</strong> Associa un fornitore ad una categoria (es. "ENEL" → "utenze")</li>
          <li><strong>Regole Descrizioni:</strong> Associa una descrizione prodotto ad una categoria</li>
          <li><strong>Applica alle Fatture:</strong> Ricategorizza tutte le fatture esistenti con le nuove regole</li>
        </ul>
      </div>
    </div>
    </PageLayout>
  );
}

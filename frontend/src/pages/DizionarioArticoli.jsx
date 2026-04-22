import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { formatEuro, STYLES, COLORS, button, badge } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';

const CATEGORIE_HACCP_COLORS = {
  carni_fresche: { bg: '#fecaca', text: '#991b1b', label: 'Carni Fresche' },
  pesce_fresco: { bg: '#bae6fd', text: '#0369a1', label: 'Pesce Fresco' },
  latticini: { bg: '#fef3c7', text: '#92400e', label: 'Latticini' },
  uova: { bg: '#fef9c3', text: '#854d0e', label: 'Uova' },
  frutta_verdura: { bg: '#bbf7d0', text: '#166534', label: 'Frutta/Verdura' },
  surgelati: { bg: '#e0e7ff', text: '#3730a3', label: 'Surgelati' },
  prodotti_forno: { bg: '#fed7aa', text: '#9a3412', label: 'Prodotti da Forno' },
  farine_cereali: { bg: '#f5d0fe', text: '#86198f', label: 'Farine/Cereali' },
  conserve_scatolame: { bg: '#d4d4d4', text: '#404040', label: 'Conserve' },
  bevande_analcoliche: { bg: '#a5f3fc', text: '#0e7490', label: 'Bevande Analcoliche' },
  bevande_alcoliche: { bg: '#fda4af', text: '#9f1239', label: 'Bevande Alcoliche' },
  spezie_condimenti: { bg: '#fde68a', text: '#92400e', label: 'Spezie/Condimenti' },
  salumi_insaccati: { bg: '#f9a8d4', text: '#9d174d', label: 'Salumi' },
  dolciumi_snack: { bg: '#c4b5fd', text: '#5b21b6', label: 'Dolciumi/Snack' },
  additivi_ingredienti: { bg: '#99f6e4', text: '#0f766e', label: 'Additivi' },
  non_alimentare: { bg: '#e5e7eb', text: '#374151', label: 'Non Alimentare' }
};

const CONTI_PIANO = {
  "05.01.01": "Acquisto merci",
  "05.01.02": "Acquisto materie prime",
  "05.01.03": "Acquisto bevande alcoliche",
  "05.01.04": "Acquisto bevande analcoliche",
  "05.01.05": "Acquisto prodotti alimentari",
  "05.01.06": "Acquisto piccola utensileria",
  "05.01.07": "Materiali di consumo e imballaggio",
  "05.01.08": "Prodotti per pulizia e igiene",
  "05.01.09": "Acquisto caffè e affini",
  "05.01.10": "Acquisto surgelati",
  "05.01.11": "Acquisto prodotti da forno",
  "05.01.12": "Materiale edile e costruzioni",
  "05.01.13": "Additivi e ingredienti alimentari",
  "05.02.01": "Costi per servizi",
  "05.02.05": "Utenze - Energia elettrica",
  "05.02.07": "Telefonia e comunicazioni",
  "05.02.16": "Trasporti su acquisti",
  "05.02.22": "Noleggio automezzi"
};

export default function DizionarioArticoli() {
  const [articoli, setArticoli] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [categorieHaccp, setCategorieHaccp] = useState({});
  
  // Filtri
  const [search, setSearch] = useState('');
  const [filterCategoria, setFilterCategoria] = useState('');
  const [filterNonMappati, setFilterNonMappati] = useState(false);
  const [page, setPage] = useState(0);
  const limit = 50;
  
  // Modal modifica
  const [editingArticolo, setEditingArticolo] = useState(null);
  const [editForm, setEditForm] = useState({
    categoria_haccp: '',
    conto: '',
    note: ''
  });
  
  // Stato operazioni
  const [generating, setGenerating] = useState(false);
  const [applying, setApplying] = useState(false);
  const [categorizingAI, setCategorizingAI] = useState(false);
  const [message, setMessage] = useState(null);
  const [total, setTotal] = useState(0);

  const loadArticoli = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        skip: page * limit,
        limit: limit
      });
      if (filterCategoria) params.append('categoria_haccp', filterCategoria);
      if (filterNonMappati) params.append('non_mappati', 'true');
      
      const res = await api.get(`/api/dizionario-articoli/dizionario?${params}`);
      setArticoli(res.data.items || []);
      setTotal(res.data.total || 0);
    } catch (err) {
      console.error('Errore caricamento articoli:', err);
    } finally {
      setLoading(false);
    }
  }, [page, filterCategoria, filterNonMappati]);

  const loadStats = async () => {
    try {
      const res = await api.get('/api/dizionario-articoli/statistiche');
      setStats(res.data);
    } catch (err) {
      console.error('Errore caricamento statistiche:', err);
    }
  };

  const loadCategorieHaccp = async () => {
    try {
      const res = await api.get('/api/dizionario-articoli/categorie-haccp');
      setCategorieHaccp(res.data.categorie || {});
    } catch (err) {
      console.error('Errore caricamento categorie:', err);
    }
  };

  useEffect(() => {
    loadCategorieHaccp();
    loadStats();
  }, []);

  useEffect(() => {
    loadArticoli();
  }, [loadArticoli]);

  const handleSearch = async () => {
    if (!search || search.length < 2) {
      loadArticoli();
      return;
    }
    try {
      setLoading(true);
      const res = await api.get(`/api/dizionario-articoli/cerca?q=${encodeURIComponent(search)}&limit=100`);
      setArticoli(res.data || []);
    } catch (err) {
      console.error('Errore ricerca:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleGeneraDizionario = async () => {
    if (!confirm('Vuoi generare/aggiornare il dizionario articoli dalle fatture?')) return;
    try {
      setGenerating(true);
      setMessage(null);
      const res = await api.post('/api/dizionario-articoli/genera-dizionario');
      setMessage({
        type: 'success',
        text: `✅ Dizionario generato: ${res.data.created} nuovi, ${res.data.updated} aggiornati`
      });
      loadArticoli();
      loadStats();
    } catch (err) {
      setMessage({ type: 'error', text: '❌ Errore nella generazione del dizionario' });
    } finally {
      setGenerating(false);
    }
  };

  const handleApplicaFatture = async () => {
    if (!confirm('Vuoi applicare le categorie del dizionario a tutte le fatture?')) return;
    try {
      setApplying(true);
      setMessage(null);
      const res = await api.post('/api/dizionario-articoli/ricategorizza-fatture');
      setMessage({
        type: 'success',
        text: `✅ Categorie applicate a ${res.data.fatture_aggiornate} fatture`
      });
    } catch (err) {
      setMessage({ type: 'error', text: '❌ Errore nell\'applicazione delle categorie' });
    } finally {
      setApplying(false);
    }
  };

  const handleCategorizzaAI = async () => {
    if (!confirm('Vuoi usare Claude AI per categorizzare gli articoli non classificati? (max 50 alla volta)')) return;
    try {
      setCategorizingAI(true);
      setMessage(null);
      const res = await api.post('/api/dizionario-articoli/categorizza-ai?limite=50');
      setMessage({
        type: 'success',
        text: `🤖 AI ha categorizzato ${res.data.updated} articoli su ${res.data.processed} processati`
      });
      loadArticoli();
      loadStats();
    } catch (err) {
      setMessage({ type: 'error', text: '❌ Errore nella categorizzazione AI' });
    } finally {
      setCategorizingAI(false);
    }
  };

  const openEditModal = (articolo) => {
    setEditingArticolo(articolo);
    setEditForm({
      categoria_haccp: articolo.categoria_haccp || '',
      conto: articolo.conto || '',
      note: articolo.note || ''
    });
  };

  const handleSaveEdit = async () => {
    try {
      const encoded = encodeURIComponent(editingArticolo.descrizione);
      await api.put(`/api/dizionario-articoli/articolo/${encoded}`, editForm);
      setMessage({ type: 'success', text: '✅ Articolo aggiornato' });
      setEditingArticolo(null);
      loadArticoli();
      loadStats();
    } catch (err) {
      setMessage({ type: 'error', text: '❌ Errore nel salvataggio' });
    }
  };

  const getCategoriaStyle = (cat) => {
    return CATEGORIE_HACCP_COLORS[cat] || CATEGORIE_HACCP_COLORS.non_alimentare;
  };

  return (
    <PageLayout title="Dizionario Articoli" subtitle="Mappatura automatica prodotti fatture → Piano dei Conti e Categorie HACCP">
    <div>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: '#1e3a5f', marginBottom: 8 }}>
          📦 Dizionario Articoli
        </h1>
        <p style={{ color: '#64748b' }}>
          Mappatura automatica prodotti fatture → Piano dei Conti e Categorie HACCP
        </p>
      </div>

      {/* Messaggio */}
      {message && (
        <div style={{
          padding: 16,
          borderRadius: 8,
          marginBottom: 20,
          background: message.type === 'success' ? '#dcfce7' : '#fee2e2',
          color: message.type === 'success' ? '#166534' : '#991b1b'
        }}>
          {message.text}
          <button onClick={() => setMessage(null)} style={{ marginLeft: 16, cursor: 'pointer' }}>✕</button>
        </div>
      )}

      {/* Statistiche */}
      {stats && (
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', 
          gap: 12, 
          marginBottom: 24 
        }}>
          <StatCard label="Totale Articoli" value={stats.totale_articoli} color="#3b82f6" />
          <StatCard label="Mappati Manualmente" value={stats.mappature_manuali} color="#10b981" />
          <StatCard label="Alta Confidenza" value={stats.confidenza?.alta || 0} color="#22c55e" />
          <StatCard label="Media Confidenza" value={stats.confidenza?.media || 0} color="#f59e0b" />
          <StatCard label="Non Classificati" value={stats.confidenza?.non_classificati || 0} color="#ef4444" />
        </div>
      )}

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
          onClick={handleGeneraDizionario}
          disabled={generating}
          style={{
            padding: '10px 20px',
            background: generating ? '#9ca3af' : 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: generating ? 'wait' : 'pointer',
            fontWeight: 600
          }}
        >
          {generating ? '⏳ Generazione...' : '🔄 Genera/Aggiorna Dizionario'}
        </button>
        
        <button
          onClick={handleApplicaFatture}
          disabled={applying}
          style={{
            padding: '10px 20px',
            background: applying ? '#9ca3af' : 'linear-gradient(135deg, #10b981, #059669)',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: applying ? 'wait' : 'pointer',
            fontWeight: 600
          }}
        >
          {applying ? '⏳ Applicazione...' : '✅ Applica alle Fatture'}
        </button>
        
        <button
          onClick={handleCategorizzaAI}
          disabled={categorizingAI}
          style={{
            padding: '10px 20px',
            background: categorizingAI ? '#9ca3af' : 'linear-gradient(135deg, #8b5cf6, #6d28d9)',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: categorizingAI ? 'wait' : 'pointer',
            fontWeight: 600
          }}
        >
          {categorizingAI ? '⏳ AI in corso...' : '🤖 Categorizza con AI'}
        </button>
      </div>

      {/* Filtri */}
      <div style={{ 
        display: 'flex', 
        gap: 12, 
        marginBottom: 20, 
        flexWrap: 'wrap',
        alignItems: 'center'
      }}>
        <input
          type="text"
          placeholder="🔍 Cerca articolo..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          style={{
            padding: '10px 14px',
            borderRadius: 8,
            border: '1px solid #e2e8f0',
            minWidth: 250
          }}
        />
        <button
          onClick={handleSearch}
          style={{
            padding: '10px 16px',
            background: '#3b82f6',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer'
          }}
        >
          Cerca
        </button>
        
        <select
          value={filterCategoria}
          onChange={(e) => { setFilterCategoria(e.target.value); setPage(0); }}
          style={{ padding: '10px 14px', borderRadius: 8, border: '1px solid #e2e8f0' }}
        >
          <option value="">Tutte le categorie HACCP</option>
          {Object.entries(CATEGORIE_HACCP_COLORS).map(([key, val]) => (
            <option key={key} value={key}>{val.label}</option>
          ))}
        </select>
        
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <input
            type="checkbox"
            checked={filterNonMappati}
            onChange={(e) => { setFilterNonMappati(e.target.checked); setPage(0); }}
          />
          Solo non mappati
        </label>
      </div>

      {/* Tabella Articoli */}
      <div style={{ 
        background: 'white', 
        borderRadius: 12, 
        overflow: 'hidden', 
        border: '1px solid #e2e8f0' 
      }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
            ⏳ Caricamento...
          </div>
        ) : articoli.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>📦</div>
            <div>Nessun articolo trovato</div>
            <div style={{ fontSize: 13, marginTop: 8 }}>
              Clicca "Genera/Aggiorna Dizionario" per estrarre gli articoli dalle fatture
            </div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', }}>
              <thead>
                <tr style={{ background: '#1e3a5f', color: 'white' }}>
                  <th style={{ padding: 12, textAlign: 'left', width: '35%' }}>Descrizione</th>
                  <th style={{ padding: 12, textAlign: 'center' }}>Occorrenze</th>
                  <th style={{ padding: 12, textAlign: 'left' }}>Categoria HACCP</th>
                  <th style={{ padding: 12, textAlign: 'left' }}>Conto</th>
                  <th style={{ padding: 12, textAlign: 'center' }}>Confidenza</th>
                  <th style={{ padding: 12, textAlign: 'center', width: 80 }}>Azioni</th>
                </tr>
              </thead>
              <tbody>
                {articoli.map((art, idx) => {
                  const catStyle = getCategoriaStyle(art.categoria_haccp);
                  return (
                    <tr key={idx} style={{ 
                      borderBottom: '1px solid #f1f5f9',
                      background: art.mappatura_manuale ? '#f0fdf4' : 'white'
                    }}>
                      <td style={{ padding: 12 }}>
                        <div style={{ fontWeight: 500, fontSize: 13 }}>
                          {art.descrizione?.substring(0, 60)}
                          {art.descrizione?.length > 60 && '...'}
                        </div>
                        <div style={{ fontSize: 11, color: '#64748b' }}>
                          {art.n_fornitori} fornitore/i • {formatEuro(art.totale_importo || 0)}
                        </div>
                      </td>
                      <td style={{ padding: 12, textAlign: 'center', fontWeight: 600 }}>
                        {art.occorrenze}
                      </td>
                      <td style={{ padding: 12 }}>
                        <span style={{
                          background: catStyle.bg,
                          color: catStyle.text,
                          padding: '4px 10px',
                          borderRadius: 20,
                          fontSize: 11,
                          fontWeight: 600
                        }}>
                          {catStyle.label}
                        </span>
                        {art.rischio_haccp && art.rischio_haccp !== 'N/A' && (
                          <span style={{
                            marginLeft: 6,
                            fontSize: 10,
                            color: art.rischio_haccp === 'alto' ? '#dc2626' : 
                                   art.rischio_haccp === 'medio' ? '#f59e0b' : '#22c55e'
                          }}>
                            ({art.rischio_haccp})
                          </span>
                        )}
                      </td>
                      <td style={{ padding: 12 }}>
                        <div style={{ fontSize: 12, fontWeight: 500 }}>{art.conto}</div>
                        <div style={{ fontSize: 11, color: '#64748b' }}>{art.conto_nome}</div>
                      </td>
                      <td style={{ padding: 12, textAlign: 'center' }}>
                        <div style={{
                          width: 40,
                          height: 40,
                          borderRadius: '50%',
                          background: art.confidenza >= 0.5 ? '#dcfce7' : 
                                     art.confidenza > 0 ? '#fef3c7' : '#fee2e2',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          margin: '0 auto',
                          fontSize: 11,
                          fontWeight: 600,
                          color: art.confidenza >= 0.5 ? '#166534' : 
                                 art.confidenza > 0 ? '#92400e' : '#991b1b'
                        }}>
                          {Math.round(art.confidenza * 100)}%
                        </div>
                      </td>
                      <td style={{ padding: 12, textAlign: 'center' }}>
                        <button
                          onClick={() => openEditModal(art)}
                          style={{
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            fontSize: 18,
                            opacity: 0.7
                          }}
                          title="Modifica mappatura"
                        >
                          ✏️
                        </button>
                        {art.mappatura_manuale && (
                          <span title="Mappato manualmente" style={{ marginLeft: 4 }}>✅</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Paginazione */}
        {articoli.length > 0 && (
          <div style={{ 
            padding: 16, 
            borderTop: '1px solid #e2e8f0',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            gap: 12
          }}>
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              style={{
                padding: '8px 16px',
                borderRadius: 6,
                border: '1px solid #e2e8f0',
                background: page === 0 ? '#f1f5f9' : 'white',
                cursor: page === 0 ? 'not-allowed' : 'pointer'
              }}
              data-testid="btn-pagina-precedente"
            >
              ← Precedente
            </button>
            <span style={{ padding: '8px 16px', color: '#64748b' }}>
              Pagina {page + 1} di {Math.max(1, Math.ceil(total / limit))} ({total} articoli)
            </span>
            <button
              onClick={() => setPage(page + 1)}
              disabled={(page + 1) * limit >= total}
              style={{
                padding: '8px 16px',
                borderRadius: 6,
                border: '1px solid #e2e8f0',
                background: (page + 1) * limit >= total ? '#f1f5f9' : 'white',
                cursor: (page + 1) * limit >= total ? 'not-allowed' : 'pointer'
              }}
              data-testid="btn-pagina-successiva"
            >
              Successiva →
            </button>
          </div>
        )}
      </div>

      {/* Modal Modifica */}
      {editingArticolo && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }} onClick={() => setEditingArticolo(null)}>
          <div style={{
            background: 'white',
            borderRadius: 12,
            padding: 24,
            width: '90%',
            maxWidth: 600,
            maxHeight: '90vh',
            overflow: 'auto'
          }} onClick={e => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 20px 0', color: '#1e3a5f' }}>
              ✏️ Modifica Mappatura Articolo
            </h3>
            
            <div style={{ 
              padding: 12, 
              background: '#f8fafc', 
              borderRadius: 8, 
              marginBottom: 20 
            }}>
              <div style={{ fontSize: 13, color: '#64748b' }}>Descrizione:</div>
              <div style={{ fontWeight: 500 }}>{editingArticolo.descrizione}</div>
            </div>
            
            <div style={{ display: 'grid', gap: 16 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>
                  Categoria HACCP
                </label>
                <select
                  value={editForm.categoria_haccp}
                  onChange={(e) => setEditForm({...editForm, categoria_haccp: e.target.value})}
                  style={{ 
                    width: '100%', 
                    padding: '10px 12px', 
                    borderRadius: 8, 
                    border: '1px solid #e2e8f0' 
                  }}
                >
                  <option value="">-- Seleziona --</option>
                  {Object.entries(CATEGORIE_HACCP_COLORS).map(([key, val]) => (
                    <option key={key} value={key}>{val.label}</option>
                  ))}
                </select>
              </div>
              
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>
                  Conto Piano dei Conti
                </label>
                <select
                  value={editForm.conto}
                  onChange={(e) => setEditForm({...editForm, conto: e.target.value})}
                  style={{ 
                    width: '100%', 
                    padding: '10px 12px', 
                    borderRadius: 8, 
                    border: '1px solid #e2e8f0' 
                  }}
                >
                  <option value="">-- Seleziona --</option>
                  {Object.entries(CONTI_PIANO).map(([codice, nome]) => (
                    <option key={codice} value={codice}>{codice} - {nome}</option>
                  ))}
                </select>
              </div>
              
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>
                  Note
                </label>
                <textarea
                  value={editForm.note}
                  onChange={(e) => setEditForm({...editForm, note: e.target.value})}
                  rows={3}
                  style={{ 
                    width: '100%', 
                    padding: '10px 12px', 
                    borderRadius: 8, 
                    border: '1px solid #e2e8f0',
                    resize: 'vertical'
                  }}
                />
              </div>
            </div>
            
            <div style={{ display: 'flex', gap: 12, marginTop: 24, justifyContent: 'flex-end' }}>
              <button
                onClick={() => setEditingArticolo(null)}
                style={{
                  padding: '10px 20px',
                  borderRadius: 8,
                  border: '1px solid #e2e8f0',
                  background: 'white',
                  cursor: 'pointer'
                }}
              >
                Annulla
              </button>
              <button
                onClick={handleSaveEdit}
                style={{
                  padding: '10px 20px',
                  borderRadius: 8,
                  border: 'none',
                  background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
                  color: 'white',
                  cursor: 'pointer',
                  fontWeight: 600
                }}
              >
                💾 Salva Modifiche
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
    </PageLayout>
  );
}

function StatCard({ label, value, color }) {
  return (
    <div style={{
      background: 'white',
      borderRadius: 12,
      padding: 16,
      borderLeft: `4px solid ${color}`,
      boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
    }}>
      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color }}>{value?.toLocaleString('it-IT')}</div>
    </div>
  );
}

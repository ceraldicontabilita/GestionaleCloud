import React, { useState, useEffect, useCallback } from 'react';
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { Package, Search, AlertTriangle, Check, RefreshCw, Edit2, Save, X, ChevronDown, Database, Filter } from 'lucide-react';
import { PageLayout } from '../components/PageLayout';

export default function DizionarioProdotti() {
  const { anno } = useAnnoGlobale();
  const [prodotti, setProdotti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [search, setSearch] = useState('');
  const [soloSenzaPrezzo, setSoloSenzaPrezzo] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState(null);
  
  // Filtro fornitore
  const [fornitori, setFornitori] = useState([]);
  const [fornitoreFilter, setFornitoreFilter] = useState('');
  
  // Stato per modifica prodotto
  const [editingProdotto, setEditingProdotto] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [saving, setSaving] = useState(false);
  
  // Paginazione
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [totale, setTotale] = useState(0);

  const loadStats = useCallback(async () => {
    try {
      const res = await api.get('/api/dizionario-prodotti/stats');
      setStats(res.data);
    } catch (e) {
      console.error('Errore caricamento stats:', e);
    }
  }, []);

  const loadFornitori = useCallback(async () => {
    try {
      const res = await api.get('/api/dizionario-prodotti/fornitori');
      setFornitori(res.data.fornitori || []);
    } catch (e) {
      console.error('Errore caricamento fornitori:', e);
    }
  }, []);

  const loadProdotti = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.append('search', search);
      if (soloSenzaPrezzo) params.append('solo_senza_prezzo', 'true');
      if (fornitoreFilter) params.append('fornitore_nome', fornitoreFilter);
      params.append('limit', limit.toString());
      params.append('offset', offset.toString());
      
      const res = await api.get(`/api/dizionario-prodotti/prodotti?${params.toString()}`);
      setProdotti(res.data.prodotti || []);
      setTotale(res.data.totale || 0);
    } catch (e) {
      console.error('Errore caricamento prodotti:', e);
    }
    setLoading(false);
  }, [search, soloSenzaPrezzo, fornitoreFilter, limit, offset]);

  useEffect(() => {
    loadStats();
    loadFornitori();
  }, [loadStats, loadFornitori]);

  useEffect(() => {
    loadProdotti();
  }, [loadProdotti]);

  async function scanFatture() {
    setScanning(true);
    setScanResult(null);
    try {
      const res = await api.post(`/api/dizionario-prodotti/prodotti/scan-fatture?anno=${anno}`);
      setScanResult(res.data);
      loadStats();
      loadProdotti();
    } catch (e) {
      console.error('Errore scan:', e);
      setScanResult({ error: e.message });
    }
    setScanning(false);
  }

  function openEditModal(prodotto) {
    setEditingProdotto(prodotto);
    setEditForm({
      descrizione: prodotto.descrizione || '',
      quantita: prodotto.ultima_quantita || '',
      prezzo_unitario: prodotto.ultimo_prezzo_unitario || '',
      prezzo_totale: prodotto.ultimo_prezzo_totale || '',
      prezzo_per_kg: prodotto.prezzo_per_kg || '',
      unita_misura: prodotto.unita_misura_fattura || '',
      fornitore_nome: prodotto.fornitore_nome || ''
    });
  }

  async function saveEdit() {
    if (!editingProdotto) return;
    setSaving(true);
    try {
      await api.put(`/api/dizionario-prodotti/prodotti/${editingProdotto.id}`, {
        prezzo_per_kg: parseFloat(editForm.prezzo_per_kg) || null,
        prezzo_unitario_manuale: parseFloat(editForm.prezzo_unitario) || null
      });
      setEditingProdotto(null);
      loadProdotti();
      loadStats();
    } catch (e) {
      alert('Errore salvataggio: ' + (e.response?.data?.detail || e.message));
    }
    setSaving(false);
  }

  function formatPrezzo(val) {
    if (val === null || val === undefined || val === '') return '-';
    const num = parseFloat(val);
    return isNaN(num) ? '-' : `€${num.toFixed(4)}`;
  }

  const totalPages = Math.ceil(totale / limit);
  const currentPage = Math.floor(offset / limit) + 1;

  return (
    <PageLayout title="Dizionario Prodotti" subtitle="Tutti i prodotti estratti dalle fatture - Modifica il prezzo/kg per calcoli food cost accurati">
    <div style={{ maxWidth: '1600px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '28px', fontWeight: 700, color: '#1f2937', margin: '0 0 8px 0', display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Database size={32} />
          Dizionario Prodotti
        </h1>
        <p style={{ color: '#6080a0', margin: 0 }}>
          Tutti i prodotti estratti dalle fatture - Modifica il prezzo/kg per calcoli food cost accurati
        </p>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px', marginBottom: '20px' }}>
          <div style={{ background: 'white', padding: '16px', borderRadius: '10px', border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px' }}>TOTALE</div>
            <div style={{ fontSize: '24px', fontWeight: 700, color: '#1e293b' }}>{stats.totale_prodotti?.toLocaleString()}</div>
          </div>
          <div style={{ background: 'white', padding: '16px', borderRadius: '10px', border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px' }}>CON PREZZO/KG</div>
            <div style={{ fontSize: '24px', fontWeight: 700, color: '#10b981' }}>{stats.con_prezzo_al_kg?.toLocaleString()}</div>
          </div>
          <div style={{ background: 'white', padding: '16px', borderRadius: '10px', border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px' }}>SENZA PREZZO</div>
            <div style={{ fontSize: '24px', fontWeight: 700, color: '#f59e0b' }}>{(stats.totale_prodotti - stats.con_prezzo_al_kg)?.toLocaleString()}</div>
          </div>
          <div style={{ background: 'white', padding: '16px', borderRadius: '10px', border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px' }}>COMPLETEZZA</div>
            <div style={{ fontSize: '24px', fontWeight: 700, color: stats.completezza_percentuale > 50 ? '#10b981' : '#f59e0b' }}>
              {stats.completezza_percentuale?.toFixed(1)}%
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div style={{ marginBottom: '16px', display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
        <button
          onClick={scanFatture}
          disabled={scanning}
          style={{
            padding: '10px 20px',
            background: scanning ? '#9ca3af' : '#1535a8',
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            cursor: scanning ? 'not-allowed' : 'pointer',
            fontSize: '13px',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          <RefreshCw size={16} style={scanning ? { animation: 'spin 1s linear infinite' } : {}} />
          {scanning ? 'Scansione...' : `Aggiorna da Fatture ${anno}`}
        </button>
        
        <div style={{ flex: 1 }} />
        
        {/* Filtro Fornitore */}
        <select
          value={fornitoreFilter}
          onChange={(e) => { setFornitoreFilter(e.target.value); setOffset(0); }}
          style={{
            padding: '8px 12px',
            border: '1px solid #dce8f4',
            borderRadius: '6px',
            fontSize: '13px',
            minWidth: '200px',
            background: 'white'
          }}
        >
          <option value="">Tutti i fornitori</option>
          {fornitori.map((f, idx) => (
            <option key={idx} value={f.nome}>
              {f.nome} ({f.senza_prezzo} senza prezzo)
            </option>
          ))}
        </select>
        
        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
          <input
            type="checkbox"
            checked={soloSenzaPrezzo}
            onChange={(e) => { setSoloSenzaPrezzo(e.target.checked); setOffset(0); }}
            style={{ width: '16px', height: '16px' }}
          />
          Solo senza prezzo/kg
        </label>
      </div>

      {/* Scan Result */}
      {scanResult && (
        <div style={{
          marginBottom: '16px',
          padding: '12px 16px',
          borderRadius: '10px',
          background: scanResult.error ? '#fef2f2' : '#f0fdf4',
          border: `1px solid ${scanResult.error ? '#fecaca' : '#86efac'}`,
          fontSize: '13px'
        }}>
          {scanResult.error ? (
            <span style={{ color: '#dc2626' }}>Errore: {scanResult.error}</span>
          ) : (
            <span style={{ color: '#15803d' }}>
              <Check size={16} style={{ display: 'inline', marginRight: '6px' }} />
              Analizzate {scanResult.fatture_analizzate} fatture • Nuovi: {scanResult.prodotti_aggiunti} • Aggiornati: {scanResult.prodotti_aggiornati}
            </span>
          )}
        </div>
      )}

      {/* Search */}
      <div style={{ marginBottom: '16px' }}>
        <div style={{ position: 'relative', maxWidth: '400px' }}>
          <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#9ca3af' }} />
          <input
            type="text"
            placeholder="Cerca prodotto..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setOffset(0); }}
            style={{
              width: '100%',
              padding: '10px 12px 10px 40px',
              border: '1px solid #dce8f4',
              borderRadius: '8px',
              fontSize: '14px'
            }}
          />
        </div>
      </div>

      {/* Lista Prodotti - Tabella Dettagliata */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px', color: '#6080a0' }}>Caricamento...</div>
      ) : prodotti.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px', background: '#f8fafc', borderRadius: '12px' }}>
          <Package size={48} style={{ color: '#cbd5e1', marginBottom: '16px' }} />
          <h3 style={{ color: '#64748b', margin: '0 0 8px 0' }}>Nessun prodotto trovato</h3>
        </div>
      ) : (
        <>
          <div style={{ background: 'white', borderRadius: '12px', border: '1px solid #e2e8f0', overflow: 'hidden' }}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '1000px' }}>
                <thead>
                  <tr style={{ background: '#f8fafc' }}>
                    <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: '11px', fontWeight: 600, color: '#64748b', borderBottom: '1px solid #e2e8f0' }}>DESCRIZIONE</th>
                    <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: '11px', fontWeight: 600, color: '#64748b', borderBottom: '1px solid #e2e8f0' }}>FORNITORE</th>
                    <th style={{ padding: '10px 12px', textAlign: 'center', fontSize: '11px', fontWeight: 600, color: '#64748b', borderBottom: '1px solid #e2e8f0' }}>U.M.</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right', fontSize: '11px', fontWeight: 600, color: '#64748b', borderBottom: '1px solid #e2e8f0' }}>QUANTITÀ</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right', fontSize: '11px', fontWeight: 600, color: '#64748b', borderBottom: '1px solid #e2e8f0' }}>P.UNITARIO</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right', fontSize: '11px', fontWeight: 600, color: '#64748b', borderBottom: '1px solid #e2e8f0' }}>P.TOTALE</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right', fontSize: '11px', fontWeight: 600, color: '#64748b', borderBottom: '1px solid #e2e8f0', background: '#fef3c7' }}>PREZZO/KG</th>
                    <th style={{ padding: '10px 12px', textAlign: 'center', fontSize: '11px', fontWeight: 600, color: '#64748b', borderBottom: '1px solid #e2e8f0' }}>AZIONI</th>
                  </tr>
                </thead>
                <tbody>
                  {prodotti.map((prod, idx) => (
                    <tr key={prod.id} style={{ borderBottom: idx < prodotti.length - 1 ? '1px solid #f1f5f9' : 'none' }}>
                      <td style={{ padding: '12px', maxWidth: '300px' }}>
                        <div style={{ fontWeight: 500, color: '#1e293b', fontSize: '13px', wordBreak: 'break-word' }}>{prod.descrizione}</div>
                        <div style={{ fontSize: '10px', color: '#94a3b8', marginTop: '2px' }}>
                          Acquisti: {prod.conteggio_acquisti || 1} • {prod.ultima_fattura_data || ''}
                        </div>
                      </td>
                      <td style={{ padding: '12px' }}>
                        <div style={{ fontSize: '12px', color: '#64748b' }}>{prod.fornitore_nome || '-'}</div>
                      </td>
                      <td style={{ padding: '12px', textAlign: 'center' }}>
                        <span style={{ 
                          padding: '2px 8px', 
                          background: '#f1f5f9', 
                          borderRadius: '4px', 
                          fontSize: '11px',
                          color: '#475569'
                        }}>
                          {prod.unita_misura_fattura || '-'}
                        </span>
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right', fontSize: '13px', color: '#374151' }}>
                        {prod.ultima_quantita?.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '-'}
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right', fontSize: '13px', color: '#374151' }}>
                        {formatPrezzo(prod.ultimo_prezzo_unitario)}
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right', fontSize: '13px', color: '#374151' }}>
                        {formatPrezzo(prod.ultimo_prezzo_totale)}
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right', background: '#fffbeb' }}>
                        {prod.prezzo_per_kg ? (
                          <span style={{ 
                            fontWeight: 600, 
                            color: '#15803d',
                            fontSize: '13px'
                          }}>
                            €{prod.prezzo_per_kg.toFixed(2)}/kg
                          </span>
                        ) : (
                          <span style={{ 
                            padding: '2px 8px', 
                            background: '#fef3c7', 
                            borderRadius: '4px', 
                            fontSize: '11px', 
                            color: '#92400e' 
                          }}>
                            <AlertTriangle size={10} style={{ display: 'inline', marginRight: '4px' }} />
                            N/D
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '12px', textAlign: 'center' }}>
                        <button
                          onClick={() => openEditModal(prod)}
                          style={{
                            padding: '6px 12px',
                            background: '#f0f9ff',
                            color: '#0369a1',
                            border: '1px solid #bae6fd',
                            borderRadius: '6px',
                            cursor: 'pointer',
                            fontSize: '11px',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px'
                          }}
                        >
                          <Edit2 size={12} />
                          Modifica
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination */}
          <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ fontSize: '13px', color: '#64748b' }}>
              Mostrati {offset + 1}-{Math.min(offset + limit, totale)} di {totale.toLocaleString()}
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={() => setOffset(Math.max(0, offset - limit))}
                disabled={offset === 0}
                style={{
                  padding: '8px 16px',
                  background: offset === 0 ? '#f3f4f6' : 'white',
                  border: '1px solid #dce8f4',
                  borderRadius: '6px',
                  cursor: offset === 0 ? 'not-allowed' : 'pointer',
                  fontSize: '13px',
                  color: offset === 0 ? '#9ca3af' : '#374151'
                }}
              >
                ← Precedenti
              </button>
              <span style={{ padding: '8px 16px', fontSize: '13px', color: '#64748b' }}>
                Pagina {currentPage} di {totalPages}
              </span>
              <button
                onClick={() => setOffset(offset + limit)}
                disabled={offset + limit >= totale}
                style={{
                  padding: '8px 16px',
                  background: offset + limit >= totale ? '#f3f4f6' : 'white',
                  border: '1px solid #dce8f4',
                  borderRadius: '6px',
                  cursor: offset + limit >= totale ? 'not-allowed' : 'pointer',
                  fontSize: '13px',
                  color: offset + limit >= totale ? '#9ca3af' : '#374151'
                }}
              >
                Successivi →
              </button>
            </div>
          </div>
        </>
      )}

      {/* Modal Modifica Prodotto */}
      {editingProdotto && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '20px'
        }} onClick={() => setEditingProdotto(null)}>
          <div 
            style={{
              background: 'white',
              borderRadius: '16px',
              width: '100%',
              maxWidth: '600px',
              overflow: 'hidden',
              boxShadow: '0 25px 50px rgba(0,0,0,0.25)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div style={{ padding: '20px 24px', borderBottom: '1px solid #dce8f4', background: '#f8fafc' }}>
              <h2 style={{ fontSize: '18px', fontWeight: 700, color: '#1e293b', margin: 0 }}>
                Modifica Prodotto
              </h2>
            </div>

            {/* Form */}
            <div style={{ padding: '24px' }}>
              {/* Descrizione (readonly) */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#64748b', marginBottom: '6px' }}>DESCRIZIONE</label>
                <div style={{ padding: '10px 12px', background: '#f8fafc', borderRadius: '8px', fontSize: '14px', color: '#1e293b' }}>
                  {editForm.descrizione}
                </div>
              </div>

              {/* Fornitore (readonly) */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#64748b', marginBottom: '6px' }}>FORNITORE</label>
                <div style={{ padding: '10px 12px', background: '#f8fafc', borderRadius: '8px', fontSize: '14px', color: '#1e293b' }}>
                  {editForm.fornitore_nome || '-'}
                </div>
              </div>

              {/* Grid dati fattura */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '20px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#64748b', marginBottom: '4px' }}>U.M.</label>
                  <div style={{ padding: '8px 10px', background: '#f8fafc', borderRadius: '6px', fontSize: '13px' }}>
                    {editForm.unita_misura || '-'}
                  </div>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#64748b', marginBottom: '4px' }}>QUANTITÀ</label>
                  <div style={{ padding: '8px 10px', background: '#f8fafc', borderRadius: '6px', fontSize: '13px' }}>
                    {parseFloat(editForm.quantita)?.toLocaleString('it-IT', { minimumFractionDigits: 2 }) || '-'}
                  </div>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#64748b', marginBottom: '4px' }}>P.UNITARIO</label>
                  <div style={{ padding: '8px 10px', background: '#f8fafc', borderRadius: '6px', fontSize: '13px' }}>
                    €{parseFloat(editForm.prezzo_unitario)?.toFixed(4) || '-'}
                  </div>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#64748b', marginBottom: '4px' }}>P.TOTALE</label>
                  <div style={{ padding: '8px 10px', background: '#f8fafc', borderRadius: '6px', fontSize: '13px' }}>
                    €{parseFloat(editForm.prezzo_totale)?.toFixed(2) || '-'}
                  </div>
                </div>
              </div>

              {/* PREZZO AL KG - Modificabile */}
              <div style={{ 
                padding: '20px', 
                background: 'linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)', 
                borderRadius: '12px',
                border: '2px solid #f59e0b'
              }}>
                <label style={{ display: 'block', fontSize: '14px', fontWeight: 700, color: '#92400e', marginBottom: '8px' }}>
                  💰 PREZZO AL KG (€/kg)
                </label>
                <p style={{ fontSize: '12px', color: '#78350f', marginBottom: '12px' }}>
                  Questo valore viene usato per calcolare il food cost delle ricette
                </p>
                <input
                  type="number"
                  step="0.01"
                  value={editForm.prezzo_per_kg}
                  onChange={(e) => setEditForm({ ...editForm, prezzo_per_kg: e.target.value })}
                  placeholder="Es: 0.85"
                  style={{
                    width: '100%',
                    padding: '14px',
                    border: '2px solid #f59e0b',
                    borderRadius: '8px',
                    fontSize: '18px',
                    fontWeight: 600,
                    textAlign: 'center',
                    background: 'white'
                  }}
                />
                <div style={{ marginTop: '8px', fontSize: '11px', color: '#78350f' }}>
                  Se U.M. = KG, il prezzo unitario della fattura è già €/kg
                </div>
              </div>
            </div>

            {/* Footer */}
            <div style={{ padding: '16px 24px', borderTop: '1px solid #dce8f4', display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setEditingProdotto(null)}
                style={{ padding: '10px 20px', background: '#f3f4f6', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px' }}
              >
                Annulla
              </button>
              <button
                onClick={saveEdit}
                disabled={saving}
                style={{
                  padding: '10px 24px',
                  background: saving ? '#9ca3af' : '#10b981',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  cursor: saving ? 'not-allowed' : 'pointer',
                  fontSize: '14px',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}
              >
                <Save size={16} />
                {saving ? 'Salvataggio...' : 'Salva Prezzo/Kg'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* CSS */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
    </PageLayout>
  );
}

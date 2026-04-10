import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge , useIsMobile, RG, pagePad } from '../lib/utils';
import { useHashState } from '../hooks/useHashState';
import { CopyLinkButton } from '../components/CopyLinkButton';

const MESI = [
  { value: '', label: 'Tutti i mesi' },
  { value: '1', label: 'Gennaio' },
  { value: '2', label: 'Febbraio' },
  { value: '3', label: 'Marzo' },
  { value: '4', label: 'Aprile' },
  { value: '5', label: 'Maggio' },
  { value: '6', label: 'Giugno' },
  { value: '7', label: 'Luglio' },
  { value: '8', label: 'Agosto' },
  { value: '9', label: 'Settembre' },
  { value: '10', label: 'Ottobre' },
  { value: '11', label: 'Novembre' },
  { value: '12', label: 'Dicembre' }
];


// Stili inline (come da DESIGN_SYSTEM.md)
const cardStyle = { background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)', border: '1px solid #e5e7eb' };
const btnPrimary = { padding: '10px 20px', background: '#4caf50', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 'bold', fontSize: 14 };
const btnSecondary = { padding: '10px 20px', background: '#e5e7eb', color: '#374151', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: '600', fontSize: 14 };
const inputStyle = { padding: '10px 12px', borderRadius: 8, border: '2px solid #e5e7eb', fontSize: 14, boxSizing: 'border-box' };
const selectStyle = { padding: '10px 12px', borderRadius: 8, border: '2px solid #e5e7eb', fontSize: 14, background: 'white' };

// Stili aggiuntivi per riconciliazione
const styles = {
  badge: (color) => ({
    display: 'inline-flex',
    alignItems: 'center',
    padding: '4px 10px',
    borderRadius: 20,
    fontSize: 12,
    fontWeight: 600,
    background: `${color}15`,
    color: color
  }),
  button: (variant = 'primary') => ({
    padding: '8px 14px',
    borderRadius: 8,
    border: 'none',
    cursor: 'pointer',
    fontWeight: 500,
    fontSize: 13,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    transition: 'all 0.2s',
    ...(variant === 'primary' ? { background: '#3b82f6', color: 'white' } 
      : variant === 'success' ? { background: '#10b981', color: 'white' }
      : variant === 'danger' ? { background: '#ef4444', color: 'white' }
      : { background: '#f1f5f9', color: '#475569', border: '1px solid #e2e8f0' })
  }),
  uploadZone: {
    border: '2px dashed #cbd5e1',
    borderRadius: 12,
    padding: '40px 20px',
    textAlign: 'center',
    cursor: 'pointer',
    transition: 'all 0.2s',
    background: '#f8fafc'
  },
  uploadZoneActive: {
    borderColor: '#3b82f6',
    background: '#eff6ff'
  },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 14 },
  th: { padding: '12px 16px', textAlign: 'left', fontWeight: 600, color: '#475569', borderBottom: '2px solid #e2e8f0', background: '#f8fafc' },
  td: { padding: '12px 16px', borderBottom: '1px solid #f1f5f9', color: '#334155' },
  emptyState: { textAlign: 'center', padding: '60px 20px', color: '#64748b' },
  splitView: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 24 },
  rowHighlight: { background: '#fef3c7', cursor: 'pointer' },
  rowSelected: { background: '#dbeafe' }
};

export default function ArchivioFatture() {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const { anno } = useAnnoGlobale();

  // Deep link: filtri sincronizzati con URL hash
  // es: /archivio-fatture-ricevute#mese=3&stato=da_pagare&search=rossi
  const [hs, setHs, setHsMany] = useHashState({
    mese: '',
    fornitore: '',
    stato: '',
    search: '',
  });
  const mese     = hs.mese;
  const fornitore = hs.fornitore;
  const stato    = hs.stato;
  const search   = hs.search;

  // Dati
  const [fatture, setFatture] = useState([]);
  const [fornitori, setFornitori] = useState([]);
  const [statistiche, setStatistiche] = useState(null);
  const [loading, setLoading] = useState(true);

  // ==================== FETCH FUNCTIONS ====================
  
  const fetchFatture = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (anno) params.append('anno', anno);
      if (mese) params.append('mese', mese);
      if (fornitore) params.append('fornitore_piva', fornitore);
      if (stato) params.append('stato', stato);
      if (search) params.append('search', search);
      params.append('limit', '500');
      
      const res = await api.get(`/api/fatture-ricevute/archivio?${params.toString()}`);
      setFatture(res.data.fatture || res.data.items || []);
    } catch (err) {
      console.error('Errore caricamento fatture:', err);
    }
    setLoading(false);
  }, [anno, mese, fornitore, stato, search]);

  const fetchFornitori = async () => {
    try {
      const res = await api.get('/api/fatture-ricevute/fornitori?con_fatture=true&limit=500');
      setFornitori(res.data.items || []);
    } catch (err) {
      console.error('Errore caricamento fornitori:', err);
    }
  };

  const fetchStatistiche = async () => {
    try {
      const params = anno ? `?anno=${anno}` : '';
      const res = await api.get(`/api/fatture-ricevute/statistiche${params}`);
      setStatistiche(res.data);
    } catch (err) {
      console.error('Errore caricamento statistiche:', err);
    }
  };

  // ==================== EFFECTS ====================

  useEffect(() => {
    fetchFatture();
    fetchStatistiche();
  }, [fetchFatture, anno]);

  useEffect(() => {
    fetchFornitori();
  }, []);

  // ==================== HELPERS ====================

  // Usa formatEuro da utils.js (già importato)
  const formatCurrency = formatEuro;
  
  // Usa formatDateIT da utils.js
  const formatDate = formatDateIT;

  const getStatoBadge = (fattura) => {
    if (fattura.pagato) {
      let metodo = fattura.metodo_pagamento || '';
      let icon = '✅';
      let label = 'Pagata';
      
      if (fattura.prima_nota_cassa_id || metodo.toLowerCase().includes('cassa') || metodo.toLowerCase().includes('contanti')) {
        icon = '💵'; label = 'Cassa';
      } else if (fattura.prima_nota_banca_id || metodo.toLowerCase().includes('banca') || metodo.toLowerCase().includes('bonifico')) {
        icon = '🏦'; label = 'Banca';
      } else if (metodo.toLowerCase().includes('assegno')) {
        icon = '📝'; label = 'Assegno';
      } else if (metodo.toLowerCase().includes('rid') || metodo.toLowerCase().includes('sdd')) {
        icon = '🔄'; label = 'RID/SDD';
      }
      
      return (
        <span style={{ padding: '4px 10px', background: '#dcfce7', color: '#16a34a', borderRadius: 6, fontSize: 11, fontWeight: '600', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          {icon} {label}
        </span>
      );
    }
    if (fattura.stato === 'anomala') {
      return <span style={{ padding: '4px 10px', background: '#fee2e2', color: '#dc2626', borderRadius: 6, fontSize: 12, fontWeight: '600' }}>Anomala</span>;
    }
    return <span style={{ padding: '4px 10px', background: '#fef3c7', color: '#d97706', borderRadius: 6, fontSize: 12, fontWeight: '600' }}>Da pagare</span>;
  };

  // ==================== RENDER ====================

  return (
    <div style={{ maxWidth: 1600, margin: '0 auto', position: 'relative', padding: '16px 0' }} data-testid="archivio-fatture-ricevute">

      {/* Statistiche */}
      {statistiche && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 12, marginBottom: 20 }}>
          <div style={{ ...cardStyle, textAlign: 'center', padding: 14 }}>
            <div style={{ fontSize: 22, fontWeight: 'bold', color: '#1e3a5f' }}>{statistiche.totale_fatture}</div>
            <div style={{ fontSize: 12, color: '#6b7280' }}>Fatture Totali</div>
          </div>
          <div style={{ ...cardStyle, textAlign: 'center', padding: 14 }}>
            <div style={{ fontSize: 18, fontWeight: 'bold', color: '#16a34a' }}>{formatCurrency(statistiche.totale_importo)}</div>
            <div style={{ fontSize: 12, color: '#6b7280' }}>Importo Totale</div>
          </div>
          <div style={{ ...cardStyle, textAlign: 'center', padding: 14 }}>
            <div style={{ fontSize: 22, fontWeight: 'bold', color: '#2196f3' }}>{statistiche.fornitori_unici}</div>
            <div style={{ fontSize: 12, color: '#6b7280' }}>Fornitori</div>
          </div>
          <div style={{ ...cardStyle, textAlign: 'center', padding: 14 }}>
            <div style={{ fontSize: 22, fontWeight: 'bold', color: statistiche.fatture_anomale > 0 ? '#dc2626' : '#16a34a' }}>{statistiche.fatture_anomale}</div>
            <div style={{ fontSize: 12, color: '#6b7280' }}>Anomale</div>
          </div>
        </div>
      )}

      {/* Filtri */}
      <div style={{ ...cardStyle, marginBottom: 20 }}>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <div>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>Anno</label>
                <div style={{ ...selectStyle, minWidth: 80, background: '#f1f5f9', color: '#64748b', fontWeight: 600, fontSize: 13 }}>
                  {anno} <span style={{ fontSize: 9, opacity: 0.7 }}>(globale)</span>
                </div>
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>Mese</label>
                <select value={mese} onChange={(e) => setHs('mese', e.target.value)} style={{ ...selectStyle, minWidth: 110, fontSize: 13 }}>
                  {MESI.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>Fornitore</label>
                <select value={fornitore} onChange={(e) => setHs('fornitore', e.target.value)} style={{ ...selectStyle, minWidth: 180, fontSize: 13 }}>
                  <option value="">Tutti i fornitori</option>
                  {fornitori.map(f => (
                    <option key={f.partita_iva} value={f.partita_iva}>
                      {f.ragione_sociale} ({f.partita_iva})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>Stato</label>
                <select value={stato} onChange={(e) => setHs('stato', e.target.value)} style={{ ...selectStyle, minWidth: 100, fontSize: 13 }}>
                  <option value="">Tutti</option>
                  <option value="importata">Importate</option>
                  <option value="anomala">Anomale</option>
                  <option value="pagata">Pagate</option>
                </select>
              </div>
              <div style={{ flex: 1, minWidth: 180 }}>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>Ricerca</label>
                <input
                  type="text"
                  placeholder="Numero fattura, fornitore..."
                  value={search}
                  onChange={(e) => setHs('search', e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && fetchFatture()}
                  style={{ ...inputStyle, width: '100%', fontSize: 13 }}
                />
              </div>
              <div style={{ alignSelf: 'flex-end', display: 'flex', gap: 8 }}>
                <button onClick={fetchFatture} style={{ ...btnPrimary, fontSize: 13 }}>Cerca</button>
                <CopyLinkButton />
              </div>
            </div>
          </div>

          {/* Tabella Fatture */}
          <div style={cardStyle}>
            {loading ? (
              <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>⏳ Caricamento...</div>
            ) : fatture.length === 0 ? (
              <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
                <div style={{ fontSize: 48, marginBottom: 16 }}>📭</div>
                <p style={{ margin: 0 }}>Nessuna fattura trovata</p>
                <p style={{ margin: '8px 0 0 0', fontSize: 14 }}>Vai a Import Unificato per importare fatture</p>
              </div>
            ) : isMobile ? (
              // VISTA MOBILE: card per ogni fattura
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {fatture.map((f, idx) => {
                      const isPaid = f.pagato || f.status === 'paid' || f.stato_pagamento === 'pagata';
                      // Determina metodo EFFETTIVO del pagamento guardando:
                      // 1. prima_nota_cassa_id / prima_nota_banca_id (fonte primaria)
                      // 2. metodo_pagamento / metodo_pagamento_effettivo (fallback per dati legacy)
                      const hasCassaId = !!f.prima_nota_cassa_id;
                      const hasBancaId = !!f.prima_nota_banca_id;
                      const metodoSalvato = (f.metodo_pagamento_effettivo || f.metodo_pagamento || '').toLowerCase();
                      const isCassaByMetodo = metodoSalvato.includes('contant') || metodoSalvato === 'cassa' || metodoSalvato.includes('cash');
                      const isBancaByMetodo = metodoSalvato.includes('bonifico') || metodoSalvato === 'banca' || metodoSalvato.includes('bank') || metodoSalvato.includes('sepa') || metodoSalvato.includes('rid');
                      
                      // Priorità: ID prima nota > metodo salvato > null
                      const metodoPagEffettivo = hasCassaId ? 'cassa' 
                        : hasBancaId ? 'banca' 
                        : isCassaByMetodo ? 'cassa'
                        : isBancaByMetodo ? 'banca'
                        : null;
                      
                      // Metodo configurato nel fornitore (per default quando non pagato)
                      const metodoFornitore = (f.fornitore_metodo_pagamento || f.metodo_pagamento || '').toLowerCase();
                      const isFornitoreCassa = metodoFornitore.includes('contant') || metodoFornitore === 'cassa';
                      
                      // BLOCCO: Se riconciliata, non permettere modifica
                      const isRiconciliata = f.riconciliato === true;
                      
                      const isPaid = f.pagato || f.status === 'paid' || f.stato_pagamento === 'pagata';
                      const hasCassaId = !!f.prima_nota_cassa_id;
                      const hasBancaId = !!f.prima_nota_banca_id;
                      const metodoSalvato = (f.metodo_pagamento_effettivo || f.metodo_pagamento || '').toLowerCase();
                      const isCassaByMetodo = metodoSalvato.includes('contant') || metodoSalvato === 'cassa' || metodoSalvato.includes('cash');
                      const isBancaByMetodo = metodoSalvato.includes('bonifico') || metodoSalvato === 'banca' || metodoSalvato.includes('bank') || metodoSalvato.includes('sepa') || metodoSalvato.includes('rid');
                      const metodoPagEffettivo = hasCassaId ? 'cassa' : hasBancaId ? 'banca' : isCassaByMetodo ? 'cassa' : isBancaByMetodo ? 'banca' : null;
                      const metodoFornitore = (f.fornitore_metodo_pagamento || f.metodo_pagamento || '').toLowerCase();
                      const isRiconciliata = f.riconciliato === true;

                      const azioniButtons = (
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                          {isRiconciliata && (
                            <span style={{ padding: '5px 8px', background: '#10b981', color: 'white', borderRadius: 6, fontSize: 11, fontWeight: 'bold' }}>✓ RICONC.</span>
                          )}
                          <a
                            href={`/api/fatture-ricevute/fattura/${f.id}/view-assoinvoice`}
                            target="_blank" rel="noopener noreferrer"
                            style={{ padding: '7px 11px', background: '#3b82f6', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontWeight: '600', textDecoration: 'none' }}
                          >📄 Vedi</a>
                          {!(isPaid && metodoPagEffettivo === 'banca') && (
                            <button
                              disabled={isRiconciliata}
                              onClick={async () => {
                                if (isRiconciliata || (isPaid && metodoPagEffettivo === 'cassa')) return;
                                try {
                                  const scrollPos = window.scrollY;
                                  await api.post('/api/fatture-ricevute/paga-manuale', { fattura_id: f.id, importo: f.importo_totale || 0, metodo: 'cassa', data_pagamento: f.data_documento || f.invoice_date, fornitore: f.fornitore_ragione_sociale || f.supplier_name || 'Fornitore', numero_fattura: f.numero_documento || f.invoice_number || '' });
                                  await fetchFatture();
                                  setTimeout(() => window.scrollTo(0, scrollPos), 100);
                                } catch (err) { alert(`❌ Errore Cassa: ${err.response?.data?.detail || err.message}`); }
                              }}
                              style={{ padding: '7px 11px', background: isRiconciliata ? '#e5e7eb' : (isPaid && metodoPagEffettivo === 'cassa') ? '#10b981' : '#f0fdf4', color: isRiconciliata ? '#9ca3af' : (isPaid && metodoPagEffettivo === 'cassa') ? 'white' : '#16a34a', border: isRiconciliata ? 'none' : (isPaid && metodoPagEffettivo === 'cassa') ? 'none' : '2px solid #16a34a', borderRadius: 6, cursor: isRiconciliata ? 'not-allowed' : 'pointer', fontSize: 12, fontWeight: '600', opacity: isRiconciliata ? 0.5 : 1 }}
                            >💵 {(isPaid && metodoPagEffettivo === 'cassa') ? '✓ Cassa' : 'Cassa'}</button>
                          )}
                          {!(isPaid && metodoPagEffettivo === 'cassa') && (
                            <button
                              disabled={isRiconciliata}
                              onClick={async () => {
                                if (isRiconciliata || (isPaid && metodoPagEffettivo === 'banca')) return;
                                try {
                                  const scrollPos = window.scrollY;
                                  await api.post('/api/fatture-ricevute/paga-manuale', { fattura_id: f.id, importo: f.importo_totale || 0, metodo: 'banca', data_pagamento: f.data_documento || f.invoice_date, fornitore: f.fornitore_ragione_sociale || f.supplier_name || 'Fornitore', numero_fattura: f.numero_documento || f.invoice_number || '' });
                                  await fetchFatture();
                                  setTimeout(() => window.scrollTo(0, scrollPos), 100);
                                } catch (err) { alert(`❌ Errore Banca: ${err.response?.data?.detail || err.message}`); }
                              }}
                              style={{ padding: '7px 11px', background: isRiconciliata ? '#e5e7eb' : (isPaid && metodoPagEffettivo === 'banca') ? '#3b82f6' : '#eff6ff', color: isRiconciliata ? '#9ca3af' : (isPaid && metodoPagEffettivo === 'banca') ? 'white' : '#2563eb', border: isRiconciliata ? 'none' : (isPaid && metodoPagEffettivo === 'banca') ? 'none' : '2px solid #2563eb', borderRadius: 6, cursor: isRiconciliata ? 'not-allowed' : 'pointer', fontSize: 12, fontWeight: '600', opacity: isRiconciliata ? 0.5 : 1 }}
                            >🏦 {(isPaid && metodoPagEffettivo === 'banca') ? '✓ Banca' : 'Banca'}</button>
                          )}
                        </div>
                      );

                      return (
                        <div key={f.id || `fattura-${idx}`} style={{ background: 'white', borderRadius: 10, padding: '14px 16px', boxShadow: '0 1px 4px rgba(0,0,0,0.08)', border: '1px solid #e5e7eb' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                            <div>
                              <div style={{ fontWeight: 700, color: '#1e3a5f', fontSize: 14 }}>{f.supplier_name || f.fornitore_ragione_sociale || '—'}</div>
                              <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>{f.supplier_vat || f.fornitore_partita_iva}</div>
                            </div>
                            <div style={{ fontWeight: 700, fontSize: 15, color: '#1e3a5f', whiteSpace: 'nowrap', marginLeft: 8 }}>{formatCurrency(f.total_amount || f.importo_totale)}</div>
                          </div>
                          <div style={{ display: 'flex', gap: 16, fontSize: 12, color: '#64748b', marginBottom: 10 }}>
                            <span>📅 {formatDateIT(f.invoice_date || f.data_documento)}</span>
                            <span>#{f.invoice_number || f.numero_documento || '—'}</span>
                            <span>IVA {formatCurrency(f.iva)}</span>
                          </div>
                          {azioniButtons}
                        </div>
                      );
                    })}
              </div>
            ) : (
              // VISTA DESKTOP: tabella classica
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 4px', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#f1f5f9' }}>
                      <th style={{ padding: '14px 16px', textAlign: 'left', fontWeight: '600', color: '#1e293b', borderRadius: '8px 0 0 8px' }}>Data</th>
                      <th style={{ padding: '14px 16px', textAlign: 'left', fontWeight: '600', color: '#1e293b' }}>Numero</th>
                      <th style={{ padding: '14px 16px', textAlign: 'left', fontWeight: '600', color: '#1e293b' }}>Fornitore</th>
                      <th style={{ padding: '14px 16px', textAlign: 'right', fontWeight: '600', color: '#1e293b' }}>Imponibile</th>
                      <th style={{ padding: '14px 16px', textAlign: 'right', fontWeight: '600', color: '#1e293b' }}>IVA</th>
                      <th style={{ padding: '14px 16px', textAlign: 'right', fontWeight: '600', color: '#1e293b' }}>Totale</th>
                      <th style={{ padding: '14px 16px', textAlign: 'center', fontWeight: '600', color: '#1e293b', borderRadius: '0 8px 8px 0', minWidth: 220 }}>Azioni</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fatture.map((f, idx) => {
                      const isPaid = f.pagato || f.status === 'paid' || f.stato_pagamento === 'pagata';
                      const hasCassaId = !!f.prima_nota_cassa_id;
                      const hasBancaId = !!f.prima_nota_banca_id;
                      const metodoSalvato = (f.metodo_pagamento_effettivo || f.metodo_pagamento || '').toLowerCase();
                      const isCassaByMetodo = metodoSalvato.includes('contant') || metodoSalvato === 'cassa' || metodoSalvato.includes('cash');
                      const isBancaByMetodo = metodoSalvato.includes('bonifico') || metodoSalvato === 'banca' || metodoSalvato.includes('bank') || metodoSalvato.includes('sepa') || metodoSalvato.includes('rid');
                      const metodoPagEffettivo = hasCassaId ? 'cassa' : hasBancaId ? 'banca' : isCassaByMetodo ? 'cassa' : isBancaByMetodo ? 'banca' : null;
                      const isRiconciliata = f.riconciliato === true;
                      return (
                      <tr key={f.id || `fattura-${idx}`} style={{ background: idx % 2 === 0 ? 'white' : '#f8fafc', boxShadow: '0 1px 3px rgba(0,0,0,0.05)', transition: 'background 0.2s' }}>
                        <td style={{ padding: '14px 16px', borderRadius: '8px 0 0 8px' }}>{formatDateIT(f.invoice_date || f.data_documento)}</td>
                        <td style={{ padding: '14px 16px', fontWeight: '600', color: '#1e3a5f' }}>{f.invoice_number || f.numero_documento}</td>
                        <td style={{ padding: '14px 16px' }}>
                          <div style={{ fontWeight: '500', fontSize: 13, color: '#374151' }}>{f.supplier_name || f.fornitore_ragione_sociale}</div>
                          <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>{f.supplier_vat || f.fornitore_partita_iva}</div>
                        </td>
                        <td style={{ padding: '14px 16px', textAlign: 'right', fontFamily: 'monospace' }}>{formatCurrency(f.imponibile)}</td>
                        <td style={{ padding: '14px 16px', textAlign: 'right', fontFamily: 'monospace', color: '#6b7280' }}>{formatCurrency(f.iva)}</td>
                        <td style={{ padding: '14px 16px', textAlign: 'right', fontWeight: 'bold', fontFamily: 'monospace', color: '#1e3a5f' }}>{formatCurrency(f.total_amount || f.importo_totale)}</td>
                        <td style={{ padding: '14px 16px', textAlign: 'center', borderRadius: '0 8px 8px 0' }}>
                          <div style={{ display: 'flex', gap: 8, justifyContent: 'center', alignItems: 'center', flexWrap: 'wrap' }}>
                            {isRiconciliata && (<span style={{ padding: '6px 10px', background: '#10b981', color: 'white', borderRadius: 6, fontSize: 11, fontWeight: 'bold' }}>✓ RICONC.</span>)}
                            <a href={`/api/fatture-ricevute/fattura/${f.id}/view-assoinvoice`} target="_blank" rel="noopener noreferrer" style={{ padding: '8px 12px', background: '#3b82f6', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontWeight: '600', textDecoration: 'none' }}>📄 Vedi</a>
                            {!(isPaid && metodoPagEffettivo === 'banca') && (
                              <button disabled={isRiconciliata} onClick={async () => { if (isRiconciliata || (isPaid && metodoPagEffettivo === 'cassa')) return; try { const scrollPos = window.scrollY; await api.post('/api/fatture-ricevute/paga-manuale', { fattura_id: f.id, importo: f.importo_totale || 0, metodo: 'cassa', data_pagamento: f.data_documento || f.invoice_date, fornitore: f.fornitore_ragione_sociale || f.supplier_name || 'Fornitore', numero_fattura: f.numero_documento || f.invoice_number || '' }); await fetchFatture(); setTimeout(() => window.scrollTo(0, scrollPos), 100); } catch (err) { alert(`❌ Errore Cassa: ${err.response?.data?.detail || err.message}`); } }}
                                style={{ padding: '8px 14px', background: isRiconciliata ? '#e5e7eb' : (isPaid && metodoPagEffettivo === 'cassa') ? '#10b981' : '#f0fdf4', color: isRiconciliata ? '#9ca3af' : (isPaid && metodoPagEffettivo === 'cassa') ? 'white' : '#16a34a', border: isRiconciliata ? 'none' : (isPaid && metodoPagEffettivo === 'cassa') ? 'none' : '2px solid #16a34a', borderRadius: 6, cursor: isRiconciliata ? 'not-allowed' : 'pointer', fontSize: 12, fontWeight: '600', minWidth: 70, opacity: isRiconciliata ? 0.5 : 1 }}
                              >💵 {(isPaid && metodoPagEffettivo === 'cassa') ? '✓ Cassa' : 'Cassa'}</button>
                            )}
                            {!(isPaid && metodoPagEffettivo === 'cassa') && (
                              <button disabled={isRiconciliata} onClick={async () => { if (isRiconciliata || (isPaid && metodoPagEffettivo === 'banca')) return; try { const scrollPos = window.scrollY; await api.post('/api/fatture-ricevute/paga-manuale', { fattura_id: f.id, importo: f.importo_totale || 0, metodo: 'banca', data_pagamento: f.data_documento || f.invoice_date, fornitore: f.fornitore_ragione_sociale || f.supplier_name || 'Fornitore', numero_fattura: f.numero_documento || f.invoice_number || '' }); await fetchFatture(); setTimeout(() => window.scrollTo(0, scrollPos), 100); } catch (err) { alert(`❌ Errore Banca: ${err.response?.data?.detail || err.message}`); } }}
                                style={{ padding: '8px 14px', background: isRiconciliata ? '#e5e7eb' : (isPaid && metodoPagEffettivo === 'banca') ? '#3b82f6' : '#eff6ff', color: isRiconciliata ? '#9ca3af' : (isPaid && metodoPagEffettivo === 'banca') ? 'white' : '#2563eb', border: isRiconciliata ? 'none' : (isPaid && metodoPagEffettivo === 'banca') ? 'none' : '2px solid #2563eb', borderRadius: 6, cursor: isRiconciliata ? 'not-allowed' : 'pointer', fontSize: 12, fontWeight: '600', minWidth: 70, opacity: isRiconciliata ? 0.5 : 1 }}
                              >🏦 {(isPaid && metodoPagEffettivo === 'banca') ? '✓ Banca' : 'Banca'}</button>
                            )}
                          </div>
                        </td>
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


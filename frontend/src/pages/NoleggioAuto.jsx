import React, { useState, useEffect, useCallback } from "react";
import api from "../api";
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';
import { toast } from 'sonner';

export default function NoleggioAuto() {
  // Usa anno globale come default, null = tutti gli anni
  const { anno } = useAnnoGlobale();
  const [annoFiltro, setAnnoFiltro] = useState(anno);
  const [veicoli, setVeicoli] = useState([]);
  const [statistiche, setStatistiche] = useState({});
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [selectedVeicolo, setSelectedVeicolo] = useState(null);
  const [drivers, setDrivers] = useState([]);
  const [editingVeicolo, setEditingVeicolo] = useState(null);
  const [expandedSection, setExpandedSection] = useState({});
  const [fornitori, setFornitori] = useState([]);
  const [showAddVeicolo, setShowAddVeicolo] = useState(false);
  const [nuovoVeicolo, setNuovoVeicolo] = useState({ targa: '', marca: '', modello: '', fornitore_piva: '', contratto: '' });
  const [fattureNonAssociate, setFattureNonAssociate] = useState(0);
  // Stato per lookup OpenAPI
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupResult, setLookupResult] = useState(null);
  const [bulkUpdateLoading, setBulkUpdateLoading] = useState(false);

  const categorie = [
    { key: 'canoni', label: 'Canoni', icon: '📋', color: '#15803d' },
    { key: 'pedaggio', label: 'Pedaggio', icon: '🛣️', color: '#2196f3' },
    { key: 'verbali', label: 'Verbali', icon: '⚠️', color: '#f44336' },
    { key: 'bollo', label: 'Bollo', icon: '📄', color: '#9c27b0' },
    { key: 'costi_extra', label: 'Costi Extra', icon: '💳', color: '#d97706' },
    { key: 'riparazioni', label: 'Riparazioni', icon: '🔧', color: '#795548' }
  ];

  const fetchVeicoli = useCallback(async () => {
    setLoading(true);
    setErr("");
    try {
      // Se annoFiltro è null, carica TUTTI gli anni
      const annoParam = annoFiltro ? `anno=${annoFiltro}` : '';
      const [vRes, dRes, fRes] = await Promise.all([
        api.get(`/api/noleggio/veicoli?${annoParam}`),
        api.get('/api/noleggio/drivers'),
        api.get('/api/noleggio/fornitori')
      ]);
      setVeicoli(vRes.data.veicoli || []);
      setStatistiche(vRes.data.statistiche || {});
      setFattureNonAssociate(vRes.data.fatture_non_associate || 0);
      setDrivers(dRes.data.drivers || []);
      setFornitori(fRes.data.fornitori || []);
    } catch (e) {
      console.error('Errore:', e);
      setErr("Errore caricamento dati: " + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }, [annoFiltro]);

  useEffect(() => { 
    fetchVeicoli(); 
  }, [fetchVeicoli]);

  const handleSaveVeicolo = async () => {
    if (!editingVeicolo) return;
    try {
      await api.put(`/api/noleggio/veicoli/${editingVeicolo.targa}`, editingVeicolo);
      setEditingVeicolo(null);
      fetchVeicoli();
    } catch (e) {
      setErr('Errore salvataggio: ' + (e.response?.data?.detail || e.message));
    }
  };

  const handleDelete = async (targa) => {
    
    try {
      await api.delete(`/api/noleggio/veicoli/${targa}`);
      setSelectedVeicolo(null);
      fetchVeicoli();
    } catch (e) {
      setErr('Errore eliminazione: ' + (e.response?.data?.detail || e.message));
    }
  };

  const handleAddVeicolo = async () => {
    if (!nuovoVeicolo.targa || !nuovoVeicolo.fornitore_piva) {
      setErr('Targa e Fornitore sono obbligatori');
      return;
    }
    try {
      await api.post('/api/noleggio/associa-fornitore', nuovoVeicolo);
      setShowAddVeicolo(false);
      setNuovoVeicolo({ targa: '', marca: '', modello: '', fornitore_piva: '', contratto: '' });
      fetchVeicoli();
    } catch (e) {
      setErr('Errore: ' + (e.response?.data?.detail || e.message));
    }
  };

  const toggleSection = (section) => {
    setExpandedSection(prev => ({ ...prev, [section]: !prev[section] }));
  };

  // Funzione per lookup dati veicolo da OpenAPI Automotive
  const handleLookupVeicolo = async (targa) => {
    if (!targa) return;
    setLookupLoading(true);
    setLookupResult(null);
    try {
      const res = await api.get(`/api/openapi-automotive/info/${targa}`);
      if (res.data?.success) {
        setLookupResult(res.data);
        toast.success(`Dati trovati per ${targa}`);
      }
    } catch (e) {
      const errMsg = e.response?.data?.detail || e.message;
      toast.error(`Errore lookup: ${errMsg}`);
      setLookupResult({ error: errMsg });
    } finally {
      setLookupLoading(false);
    }
  };

  // Funzione per aggiornare veicolo con dati OpenAPI
  const handleUpdateFromOpenAPI = async (targa) => {
    if (!targa) return;
    setLookupLoading(true);
    try {
      const res = await api.post('/api/openapi-automotive/aggiorna-veicolo', { targa });
      if (res.data?.success) {
        toast.success(`${res.data.action === 'created' ? 'Creato' : 'Aggiornato'} veicolo ${targa}`);
        fetchVeicoli();
        setLookupResult(null);
        // Se stiamo modificando, aggiorna i campi
        if (editingVeicolo && editingVeicolo.targa === targa) {
          const updatedData = res.data.automotive_data;
          setEditingVeicolo(prev => ({ ...prev, ...updatedData }));
        }
      }
    } catch (e) {
      toast.error(`Errore aggiornamento: ${e.response?.data?.detail || e.message}`);
    } finally {
      setLookupLoading(false);
    }
  };

  // Funzione per aggiornamento massivo di tutti i veicoli
  const handleBulkUpdateFromOpenAPI = async () => {
    const targhe = veicoli.map(v => v.targa).filter(Boolean);
    if (targhe.length === 0) {
      toast.error('Nessun veicolo con targa');
      return;
    }
    
    if (!window.confirm(`Aggiornare dati da OpenAPI per ${targhe.length} veicoli?\nQuesta operazione può richiedere alcuni minuti.`)) {
      return;
    }
    
    setBulkUpdateLoading(true);
    try {
      const res = await api.post('/api/openapi-automotive/aggiorna-bulk', { targhe });
      const { aggiornati, creati, errori, dettagli } = res.data;
      toast.success(`Completato: ${aggiornati} aggiornati, ${creati} creati, ${errori} errori`);
      
      if (errori > 0) {
        const erroriList = dettagli.filter(d => d.status === 'error').map(d => `${d.targa}: ${d.error}`).join('\n');
        console.warn('Errori aggiornamento:', erroriList);
      }
      
      fetchVeicoli();
    } catch (e) {
      toast.error(`Errore bulk update: ${e.response?.data?.detail || e.message}`);
    } finally {
      setBulkUpdateLoading(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    try {
      return formatDateIT(dateStr);
    } catch {
      return dateStr;
    }
  };

  return (
    <PageLayout title="Noleggio Auto" subtitle="Gestione flotta veicoli noleggio">
    <div style={{ maxWidth: 1400, margin: '0 auto' }}>
      
      {/* Header */}
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        marginBottom: 20,
        padding: '15px 20px',
        background: 'linear-gradient(135deg, #1535a8 0%, #2050e8 100%)',
        borderRadius: 12,
        color: 'white',
        flexWrap: 'wrap',
        gap: 10
      }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 'bold' }}>🚗 Gestione Noleggio Auto</h1>
          <p style={{ margin: '4px 0 0 0', fontSize: 13, opacity: 0.9 }}>
            Flotta aziendale • Dati estratti da fatture XML
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <select
            value={annoFiltro || ''}
            onChange={(e) => setAnnoFiltro(e.target.value ? parseInt(e.target.value) : null)}
            style={{
              padding: '10px 15px',
              fontSize: 14,
              fontWeight: 'bold',
              borderRadius: 8,
              border: 'none',
              background: 'rgba(255,255,255,0.95)',
              color: '#1535a8',
              cursor: 'pointer'
            }}
          >
            <option value="">📊 Tutti gli anni</option>
            {[...Array(5)].map((_, i) => {
              const y = new Date().getFullYear() - i;
              return <option key={y} value={y}>📅 {y}</option>;
            })}
          </select>
          <span style={{ 
            padding: '10px 20px',
            fontSize: 16,
            fontWeight: 'bold',
            borderRadius: 8,
            background: 'rgba(255,255,255,0.9)',
            color: '#1535a8',
          }}>
            {annoFiltro ? `Anno: ${annoFiltro}` : 'Storico completo'}
          </span>
        </div>
      </div>

      {/* Azioni */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20, flexWrap: 'wrap', alignItems: 'center' }}>
        <button 
          onClick={fetchVeicoli}
          style={{ 
            padding: '10px 20px',
            background: '#e5e7eb',
            color: '#374151',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: '600'
          }}
          data-testid="noleggio-refresh-btn"
        >
          🔄 Aggiorna
        </button>
        <button 
          onClick={() => setShowAddVeicolo(true)}
          style={{ 
            padding: '10px 20px',
            background: '#1535a8',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: '600'
          }}
          data-testid="noleggio-add-btn"
        >
          ➕ Aggiungi Veicolo
        </button>
        <button 
          onClick={handleBulkUpdateFromOpenAPI}
          disabled={bulkUpdateLoading || veicoli.length === 0}
          style={{ 
            padding: '10px 20px',
            background: bulkUpdateLoading ? '#9ca3af' : '#059669',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: bulkUpdateLoading ? 'wait' : 'pointer',
            fontWeight: '600',
            opacity: veicoli.length === 0 ? 0.5 : 1
          }}
          data-testid="noleggio-bulk-update-btn"
          title="Aggiorna marca, modello e altri dati da OpenAPI Automotive"
        >
          {bulkUpdateLoading ? '⏳ Aggiornamento...' : '🚗 Aggiorna Dati Veicoli'}
        </button>
        {fattureNonAssociate > 0 && (
          <span style={{ 
            padding: '8px 16px', 
            background: '#fef3c7', 
            color: '#92400e', 
            borderRadius: 8,
            fontSize: 13,
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}>
            ⚠️ {fattureNonAssociate} fatture non associate
            <button
              onClick={async () => {
                try {
                  const res = await api.get('/api/noleggio/fatture-non-associate');
                  const fatture = res.data.fatture || [];
                  if (fatture.length === 0) {
                    alert('Nessuna fattura non associata');
                    return;
                  }
                  // Mostra modal con lista fatture
                  const dettagli = fatture.map(f => 
                    `• ${f.fornitore || 'N/D'} - Fatt. ${f.numero || 'N/D'} del ${f.data || 'N/D'}\n  ${formatEuro(Number(f.importo || 0))} - ${f.descrizione || ''}`
                  ).join('\n\n');
                  alert(`📋 FATTURE NON ASSOCIATE (${fatture.length}):\n\n${dettagli}`);
                } catch (e) {
                  alert('Errore: ' + e.message);
                }
              }}
              style={{
                padding: '4px 10px',
                background: '#d97706',
                color: 'white',
                border: 'none',
                borderRadius: 4,
                cursor: 'pointer',
                fontSize: 11,
                fontWeight: 600
              }}
            >
              👁️ Visualizza
            </button>
          </span>
        )}
      </div>

      {err && (
        <div style={{ padding: 12, background: '#fee2e2', border: '1px solid #fecaca', borderRadius: 8, color: '#dc2626', marginBottom: 20 }} data-testid="noleggio-error">
          ❌ {err}
        </div>
      )}

      {/* Riepilogo Totali - Se veicolo selezionato mostra i suoi dati, altrimenti totale generale */}
      {veicoli.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          {selectedVeicolo && (
            <div style={{ 
              padding: '8px 16px', 
              background: '#dbeafe', 
              borderRadius: '8px 8px 0 0',
              color: '#1535a8',
              fontWeight: 'bold',
              fontSize: 14
            }}>
              📊 Riepilogo: {selectedVeicolo.marca} {selectedVeicolo.modello || ''} - {selectedVeicolo.targa}
            </div>
          )}
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', 
            gap: 16,
            padding: selectedVeicolo ? '16px' : 0,
            background: selectedVeicolo ? '#f8fafc' : 'transparent',
            borderRadius: selectedVeicolo ? '0 0 8px 8px' : 0
          }}>
            {categorie.map(cat => {
              // Se c'è un veicolo selezionato, mostra i suoi totali, altrimenti il totale generale
              const valore = selectedVeicolo 
                ? (selectedVeicolo[`totale_${cat.key}`] || (selectedVeicolo[cat.key] || []).reduce((a, s) => a + (s.totale || 0), 0))
                : (statistiche[`totale_${cat.key}`] || 0);
              
              return (
                <div key={cat.key} style={{ 
                  background: 'white', 
                  borderRadius: 8, 
                  padding: '10px 12px', 
                  boxShadow: '0 1px 4px rgba(0,0,0,0.06)', 
                  borderLeft: `3px solid ${cat.color}` 
                }}>
                  <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>{cat.icon} {cat.label}</div>
                  <div style={{ fontSize: 16, fontWeight: 'bold', color: cat.color }}>{formatEuro(valore)}</div>
                </div>
              );
            })}
            <div style={{ background: '#1535a8', borderRadius: 8, padding: '10px 12px', boxShadow: '0 1px 4px rgba(0,0,0,0.06)', color: 'white' }}>
              <div style={{ fontSize: 11, opacity: 0.9, marginBottom: 4 }}>🚗 TOTALE</div>
              <div style={{ fontSize: 16, fontWeight: 'bold' }}>
                {formatEuro(selectedVeicolo ? selectedVeicolo.totale_generale : (statistiche.totale_generale || 0))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Dettaglio Veicolo Selezionato */}
      {selectedVeicolo && (
        <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)', marginBottom: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h2 style={{ margin: 0, fontSize: 18 }}>
              🚗 {selectedVeicolo.marca} {selectedVeicolo.modello || 'Modello da definire'} - <span style={{ color: '#1535a8', fontFamily: 'monospace' }}>{selectedVeicolo.targa}</span>
            </h2>
            <div style={{ display: 'flex', gap: 8 }}>
              <button 
                onClick={() => handleUpdateFromOpenAPI(selectedVeicolo.targa)}
                disabled={lookupLoading}
                style={{ padding: '6px 12px', background: lookupLoading ? '#9ca3af' : '#059669', color: 'white', border: 'none', borderRadius: 6, cursor: lookupLoading ? 'wait' : 'pointer' }}
                title="Aggiorna dati veicolo da OpenAPI Automotive"
                data-testid="veicolo-update-openapi-btn"
              >
                {lookupLoading ? '⏳' : '🔄'} Aggiorna da Targa
              </button>
              <button 
                onClick={() => setEditingVeicolo({...selectedVeicolo})}
                style={{ padding: '6px 12px', background: '#dbeafe', color: '#1535a8', border: 'none', borderRadius: 6, cursor: 'pointer' }}
              >
                ✏️ Modifica
              </button>
              <button 
                onClick={() => handleDelete(selectedVeicolo.targa)}
                style={{ padding: '6px 12px', background: '#fee2e2', color: '#dc2626', border: 'none', borderRadius: 6, cursor: 'pointer' }}
              >
                🗑️ Elimina
              </button>
              <button onClick={() => setSelectedVeicolo(null)} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer' }}>✕</button>
            </div>
          </div>
          
          {/* Info generali veicolo */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16, marginBottom: 20 }}>
            <div>
              <h3 style={{ margin: '0 0 8px 0', fontSize: 14, color: '#6b7280' }}>Dati Veicolo</h3>
              <div style={{ fontSize: 13, lineHeight: 1.8 }}>
                <div>Targa: <strong>{selectedVeicolo.targa}</strong></div>
                <div>Fornitore: {selectedVeicolo.fornitore_noleggio || "-"}</div>
                <div>P.IVA: <span style={{ fontFamily: 'monospace', color: '#6b7280' }}>{selectedVeicolo.fornitore_piva || "-"}</span></div>
              </div>
            </div>
            <div>
              <h3 style={{ margin: '0 0 8px 0', fontSize: 14, color: '#6b7280' }}>Contratto</h3>
              <div style={{ fontSize: 13, lineHeight: 1.8 }}>
                <div>N° Contratto: <strong>{selectedVeicolo.contratto || "-"}</strong></div>
                <div>Cod. Cliente: {selectedVeicolo.codice_cliente || "-"}</div>
                <div>Centro Fatt.: {selectedVeicolo.centro_fatturazione || "-"}</div>
              </div>
            </div>
            <div>
              <h3 style={{ margin: '0 0 8px 0', fontSize: 14, color: '#6b7280' }}>Assegnazione</h3>
              <div style={{ fontSize: 13, lineHeight: 1.8 }}>
                <div>Driver: <strong>{selectedVeicolo.driver || "Non assegnato"}</strong></div>
                <div>Inizio: {formatDate(selectedVeicolo.data_inizio)}</div>
                <div>Fine: {formatDate(selectedVeicolo.data_fine)}</div>
              </div>
            </div>
            <div>
              <h3 style={{ margin: '0 0 8px 0', fontSize: 14, color: '#6b7280' }}>Totale {annoFiltro}</h3>
              <div style={{ fontSize: 24, fontWeight: 'bold', color: '#1535a8' }}>
                {formatEuro(selectedVeicolo.totale_generale)}
              </div>
            </div>
          </div>

          {/* Sezioni spese per categoria */}
          {categorie.map(cat => {
            // Ordina le spese per data (dalla più recente alla più vecchia)
            const spese = [...(selectedVeicolo[cat.key] || [])].sort((a, b) => {
              const dateA = new Date(a.data || '1900-01-01');
              const dateB = new Date(b.data || '1900-01-01');
              return dateB - dateA; // Ordine decrescente (più recenti prima)
            });
            if (spese.length === 0) return null;
            const isOpen = expandedSection[cat.key];
            const totaleSezione = spese.reduce((a, s) => a + (s.totale || 0), 0);

            return (
              <div key={cat.key} style={{ marginBottom: 12 }}>
                <div 
                  onClick={() => toggleSection(cat.key)}
                  style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between', 
                    alignItems: 'center',
                    padding: '12px 16px',
                    background: `${cat.color}15`,
                    borderRadius: 8,
                    cursor: 'pointer',
                    borderLeft: `4px solid ${cat.color}`
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span>{cat.icon}</span>
                    <span style={{ fontWeight: '600', color: cat.color }}>{cat.label}</span>
                    <span style={{ fontSize: 13, color: '#6b7280' }}>({spese.length} fatture)</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{ fontWeight: 'bold', fontSize: 16, color: cat.color }}>{formatEuro(totaleSezione)}</span>
                    <span>{isOpen ? '▲' : '▼'}</span>
                  </div>
                </div>

                {isOpen && (
                  <div style={{ marginTop: 8, overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                      <thead>
                        <tr style={{ background: '#f9fafb', borderBottom: '2px solid #e5e7eb' }}>
                          <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: '600' }}>Data</th>
                          <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: '600' }}>Fattura</th>
                          {cat.key === 'verbali' && (
                            <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: '600' }}>N° Verbale</th>
                          )}
                          <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: '600' }}>Descrizione</th>
                          <th style={{ padding: '8px 10px', textAlign: 'right', fontWeight: '600' }}>Imponibile</th>
                          <th style={{ padding: '8px 10px', textAlign: 'right', fontWeight: '600' }}>IVA</th>
                          <th style={{ padding: '8px 10px', textAlign: 'right', fontWeight: '600' }}>Totale</th>
                          <th style={{ padding: '8px 10px', textAlign: 'center', fontWeight: '600' }}>Stato</th>
                          <th style={{ padding: '8px 10px', textAlign: 'center', fontWeight: '600' }}>Vedi</th>
                        </tr>
                      </thead>
                      <tbody>
                        {spese.map((s, idx) => (
                          <tr key={idx} style={{ borderBottom: '1px solid #f3f4f6', background: s.imponibile < 0 ? '#fff7ed' : 'white' }}>
                            <td style={{ padding: '8px 10px', fontSize: 12 }}>{formatDate(s.data)}</td>
                            <td style={{ padding: '8px 10px', color: '#6b7280', fontSize: 11, fontFamily: 'monospace' }}>{s.numero_fattura || "-"}</td>
                            {cat.key === 'verbali' && (
                              <td style={{ padding: '8px 10px', fontSize: 11, fontFamily: 'monospace', color: s.numero_verbale ? '#dc2626' : '#9ca3af' }}>
                                {s.numero_verbale || "-"}
                                {s.data_verbale && <div style={{ fontSize: 10, color: '#6b7280' }}>{formatDate(s.data_verbale)}</div>}
                              </td>
                            )}
                            <td style={{ padding: '8px 10px' }}>
                              {s.voci?.map((v, vi) => (
                                <div key={vi} style={{ fontSize: 11, color: '#4b5563', paddingBottom: 2 }}>
                                  {v.descrizione?.replace(selectedVeicolo.targa, '').trim().slice(0, 70) || '-'}
                                </div>
                              ))}
                            </td>
                            <td style={{ padding: '8px 10px', textAlign: 'right', color: s.imponibile < 0 ? '#ea580c' : 'inherit', fontSize: 12 }}>
                              {formatEuro(s.imponibile)}
                            </td>
                            <td style={{ padding: '8px 10px', textAlign: 'right', color: '#6b7280', fontSize: 12 }}>{formatEuro(s.iva)}</td>
                            <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 'bold', color: s.totale < 0 ? '#ea580c' : 'inherit', fontSize: 12 }}>
                              {formatEuro(s.totale)}
                            </td>
                            <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                              {s.pagato ? (
                                <span style={{ color: '#16a34a', fontWeight: 'bold', fontSize: 10 }}>✓ Pagato</span>
                              ) : (
                                <span style={{ color: '#dc2626', fontSize: 10 }}>Da pagare</span>
                              )}
                            </td>
                            <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                              {s.fattura_id ? (
                                <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                                  <a 
                                    href={`/api/fatture-ricevute/fattura/${s.fattura_id}/view-assoinvoice`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{ 
                                      padding: '4px 8px', 
                                      background: '#dbeafe', 
                                      color: '#1535a8', 
                                      borderRadius: 4, 
                                      textDecoration: 'none',
                                      fontSize: 11
                                    }}
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    📄 Fattura
                                  </a>
                                  {cat.key === 'verbali' && s.numero_verbale && (
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        // Apri modale dettaglio verbale
                                        window.open(`/verbali-noleggio/${s.numero_verbale}`, '_blank');
                                      }}
                                      style={{ 
                                        padding: '4px 8px', 
                                        background: '#fef3c7', 
                                        color: '#92400e', 
                                        borderRadius: 4, 
                                        border: 'none',
                                        cursor: 'pointer',
                                        fontSize: 11
                                      }}
                                    >
                                      ⚠️ PDF
                                    </button>
                                  )}
                                </div>
                              ) : (
                                <span style={{ color: '#9ca3af', fontSize: 11 }}>-</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                      <tfoot>
                        <tr style={{ background: `${cat.color}10`, borderTop: '2px solid #e5e7eb' }}>
                          <td colSpan={cat.key === 'verbali' ? 4 : 3} style={{ padding: '8px 10px', textAlign: 'right', fontWeight: '600' }}>Totale {cat.label}:</td>
                          <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 'bold', fontSize: 12 }}>{formatEuro(spese.reduce((a, s) => a + (s.imponibile || 0), 0))}</td>
                          <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 'bold', fontSize: 12 }}>{formatEuro(spese.reduce((a, s) => a + (s.iva || 0), 0))}</td>
                          <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 'bold', color: cat.color, fontSize: 12 }}>{formatEuro(totaleSezione)}</td>
                          <td></td>
                          <td></td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                )}
              </div>
            );
          })}

          {categorie.every(cat => (selectedVeicolo[cat.key] || []).length === 0) && (
            <div style={{ textAlign: 'center', padding: 40, color: '#6b7280' }}>
              Nessuna spesa registrata per {annoFiltro}
            </div>
          )}
        </div>
      )}

      {/* Lista Veicoli */}
      <div style={{ background: 'white', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.08)', overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb' }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>🚗 Elenco Veicoli ({veicoli.length})</h2>
        </div>
        
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
            ⏳ Caricamento...
          </div>
        ) : veicoli.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🚗</div>
            <div style={{ color: '#6b7280' }}>Nessun veicolo trovato per {annoFiltro}</div>
            <div style={{ color: '#9ca3af', fontSize: 14, marginTop: 8 }}>
              I veicoli vengono rilevati automaticamente dalle fatture dei fornitori di noleggio
            </div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }} data-testid="noleggio-table">
              <thead>
                <tr style={{ background: '#f9fafb', borderBottom: '2px solid #e5e7eb' }}>
                  <th style={{ padding: '12px 10px', textAlign: 'left', fontWeight: '600', fontSize: 12 }}>Targa</th>
                  <th style={{ padding: '12px 10px', textAlign: 'left', fontWeight: '600', fontSize: 12 }}>Veicolo</th>
                  <th style={{ padding: '12px 10px', textAlign: 'left', fontWeight: '600', fontSize: 12 }}>Fornitore</th>
                  <th style={{ padding: '12px 10px', textAlign: 'left', fontWeight: '600', fontSize: 12 }}>Contratto</th>
                  <th style={{ padding: '12px 10px', textAlign: 'left', fontWeight: '600', fontSize: 12 }}>Driver</th>
                  <th style={{ padding: '12px 10px', textAlign: 'right', fontWeight: '600', fontSize: 12 }}>📋 Canoni</th>
                  <th style={{ padding: '12px 10px', textAlign: 'right', fontWeight: '600', fontSize: 12 }}>⚠️ Verbali</th>
                  <th style={{ padding: '12px 10px', textAlign: 'right', fontWeight: '600', fontSize: 12 }}>📄 Bollo</th>
                  <th style={{ padding: '12px 10px', textAlign: 'right', fontWeight: '600', fontSize: 12 }}>🔧 Ripar.</th>
                  <th style={{ padding: '12px 10px', textAlign: 'right', fontWeight: '600', fontSize: 12 }}>TOTALE</th>
                  <th style={{ padding: '12px 10px', textAlign: 'center', fontWeight: '600', fontSize: 12 }}>Azioni</th>
                </tr>
              </thead>
              <tbody>
                {veicoli.map((v, i) => (
                  <tr 
                    key={v.targa || i} 
                    style={{ 
                      borderBottom: '1px solid #f3f4f6',
                      background: selectedVeicolo?.targa === v.targa ? '#dbeafe' : 'white',
                      cursor: 'pointer'
                    }}
                    onClick={() => setSelectedVeicolo(v)}
                    data-testid={`veicolo-row-${v.targa}`}
                  >
                    <td style={{ padding: '10px', fontWeight: '600', fontFamily: 'monospace', color: '#1535a8', fontSize: 13 }}>{v.targa}</td>
                    <td style={{ padding: '10px' }}>
                      <div style={{ fontWeight: '500', fontSize: 12 }}>{v.marca} {(v.modello || '-').slice(0, 25)}</div>
                    </td>
                    <td style={{ padding: '10px', fontSize: 12 }}>{v.fornitore_noleggio?.split(' ')[0] || '-'}</td>
                    <td style={{ padding: '10px', fontSize: 11, fontFamily: 'monospace', color: '#6b7280' }}>
                      {v.contratto || v.codice_cliente || '-'}
                    </td>
                    <td style={{ padding: '10px', fontSize: 12, color: v.driver ? 'inherit' : '#9ca3af' }}>
                      {v.driver || "-"}
                    </td>
                    <td style={{ padding: '10px', textAlign: 'right', color: '#15803d', fontSize: 12 }}>{formatEuro(v.totale_canoni)}</td>
                    <td style={{ padding: '10px', textAlign: 'right', color: '#f44336', fontSize: 12 }}>{formatEuro(v.totale_verbali)}</td>
                    <td style={{ padding: '10px', textAlign: 'right', color: '#9c27b0', fontSize: 12 }}>{formatEuro(v.totale_bollo)}</td>
                    <td style={{ padding: '10px', textAlign: 'right', color: '#795548', fontSize: 12 }}>{formatEuro(v.totale_riparazioni)}</td>
                    <td style={{ padding: '10px', textAlign: 'right', fontWeight: 'bold', color: '#1535a8', fontSize: 13 }}>{formatEuro(v.totale_generale)}</td>
                    <td style={{ padding: '10px', textAlign: 'center' }}>
                      <button 
                        onClick={(e) => { e.stopPropagation(); setSelectedVeicolo(v); }}
                        style={{ padding: '4px 8px', background: '#dbeafe', color: '#1535a8', border: 'none', borderRadius: 4, cursor: 'pointer', marginRight: 2, fontSize: 12 }}
                        title="Vedi dettaglio"
                      >
                        👁️
                      </button>
                      <button 
                        onClick={(e) => { e.stopPropagation(); setEditingVeicolo({...v}); }}
                        style={{ padding: '4px 8px', background: '#f3f4f6', color: '#374151', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 12 }}
                        title="Modifica"
                      >
                        ✏️
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal Modifica Veicolo */}
      {editingVeicolo && (
        <div style={{ 
          position: 'fixed', 
          inset: 0, 
          background: 'rgba(0,0,0,0.5)', 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div style={{ 
            background: 'white', 
            borderRadius: 12, 
            padding: 24, 
            width: '100%', 
            maxWidth: 550,
            maxHeight: '90vh',
            overflowY: 'auto'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h2 style={{ margin: 0, fontSize: 18 }}>✏️ Modifica {editingVeicolo.targa}</h2>
              <button onClick={() => setEditingVeicolo(null)} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer' }}>✕</button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Sezione OpenAPI Automotive */}
              <div style={{ 
                padding: 12, 
                background: '#f0fdf4', 
                borderRadius: 8, 
                border: '1px solid #86efac'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontWeight: '600', color: '#166534', fontSize: 13 }}>🚗 Dati da OpenAPI Automotive</span>
                  <button
                    onClick={() => handleLookupVeicolo(editingVeicolo.targa)}
                    disabled={lookupLoading || !editingVeicolo.targa}
                    style={{
                      padding: '6px 14px',
                      background: lookupLoading ? '#9ca3af' : '#059669',
                      color: 'white',
                      border: 'none',
                      borderRadius: 6,
                      cursor: lookupLoading ? 'wait' : 'pointer',
                      fontSize: 12,
                      fontWeight: '600'
                    }}
                  >
                    {lookupLoading ? '⏳ Cercando...' : '🔍 Cerca Dati'}
                  </button>
                </div>
                
                {lookupResult && !lookupResult.error && (
                  <div style={{ fontSize: 12, marginTop: 8 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                      <div><strong>Marca:</strong> {lookupResult.campi_mappati?.marca || '-'}</div>
                      <div><strong>Modello:</strong> {lookupResult.campi_mappati?.modello || '-'}</div>
                      <div><strong>Anno:</strong> {lookupResult.campi_mappati?.anno_immatricolazione || '-'}</div>
                      <div><strong>Alimentazione:</strong> {lookupResult.campi_mappati?.alimentazione || '-'}</div>
                      <div><strong>Potenza:</strong> {lookupResult.campi_mappati?.potenza_kw ? `${lookupResult.campi_mappati.potenza_kw} kW` : '-'}</div>
                      <div><strong>Cilindrata:</strong> {lookupResult.campi_mappati?.cilindrata ? `${lookupResult.campi_mappati.cilindrata} cc` : '-'}</div>
                    </div>
                    <button
                      onClick={() => {
                        // Applica i dati trovati
                        setEditingVeicolo(prev => ({
                          ...prev,
                          marca: lookupResult.campi_mappati?.marca || prev.marca,
                          modello: lookupResult.campi_mappati?.modello || prev.modello,
                          anno_immatricolazione: lookupResult.campi_mappati?.anno_immatricolazione || prev.anno_immatricolazione,
                          alimentazione: lookupResult.campi_mappati?.alimentazione || prev.alimentazione,
                          potenza_kw: lookupResult.campi_mappati?.potenza_kw || prev.potenza_kw,
                          cilindrata: lookupResult.campi_mappati?.cilindrata || prev.cilindrata,
                        }));
                        setLookupResult(null);
                        toast.success('Dati applicati!');
                      }}
                      style={{
                        marginTop: 10,
                        padding: '8px 16px',
                        background: '#1535a8',
                        color: 'white',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'pointer',
                        fontWeight: '600',
                        width: '100%'
                      }}
                    >
                      ✓ Applica questi dati
                    </button>
                  </div>
                )}
                
                {lookupResult?.error && (
                  <div style={{ fontSize: 12, color: '#dc2626', marginTop: 8 }}>
                    ❌ {lookupResult.error}
                  </div>
                )}
                
                {!lookupResult && (
                  <p style={{ fontSize: 11, color: '#6b7280', margin: '8px 0 0 0' }}>
                    Clicca "Cerca Dati" per recuperare marca, modello e altri dati dalla targa.
                  </p>
                )}
              </div>

              {/* Marca e Modello */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}>Marca</label>
                  <input 
                    type="text"
                    value={editingVeicolo.marca || ''}
                    onChange={(e) => setEditingVeicolo({...editingVeicolo, marca: e.target.value})}
                    placeholder="Es: BMW"
                    style={{ width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13 }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}>Modello</label>
                  <input 
                    type="text"
                    value={editingVeicolo.modello || ''}
                    onChange={(e) => setEditingVeicolo({...editingVeicolo, modello: e.target.value})}
                    placeholder="Es: X3 xDrive 20d M Sport"
                    style={{ width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13 }}
                  />
                </div>
              </div>

              {/* Driver */}
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}>Driver (Assegnatario)</label>
                {drivers.length > 0 ? (
                  <select
                    value={editingVeicolo.driver_id || ''}
                    onChange={(e) => {
                      const d = drivers.find(x => x.id === e.target.value);
                      setEditingVeicolo({...editingVeicolo, driver_id: e.target.value, driver: d?.nome_completo || ''});
                    }}
                    style={{ width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13 }}
                  >
                    <option value="">-- Seleziona Driver --</option>
                    {drivers.map(d => (
                      <option key={d.id} value={d.id}>{d.nome_completo}</option>
                    ))}
                  </select>
                ) : (
                  <input 
                    type="text"
                    value={editingVeicolo.driver || ''}
                    onChange={(e) => setEditingVeicolo({...editingVeicolo, driver: e.target.value})}
                    placeholder="Nome e Cognome"
                    style={{ width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13 }}
                  />
                )}
              </div>

              {/* Contratto e Codice Cliente */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}>N° Contratto</label>
                  <input 
                    type="text"
                    value={editingVeicolo.contratto || ''}
                    onChange={(e) => setEditingVeicolo({...editingVeicolo, contratto: e.target.value})}
                    placeholder="Numero contratto"
                    style={{ width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13 }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}>Codice Cliente</label>
                  <input 
                    type="text"
                    value={editingVeicolo.codice_cliente || ''}
                    onChange={(e) => setEditingVeicolo({...editingVeicolo, codice_cliente: e.target.value})}
                    placeholder="Codice cliente fornitore"
                    style={{ width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13 }}
                  />
                </div>
              </div>

              {/* Centro Fatturazione */}
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}>Centro Fatturazione</label>
                <input 
                  type="text"
                  value={editingVeicolo.centro_fatturazione || ''}
                  onChange={(e) => setEditingVeicolo({...editingVeicolo, centro_fatturazione: e.target.value})}
                  placeholder="Centro di fatturazione (es: K26858)"
                  style={{ width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13 }}
                />
              </div>

              {/* Date Noleggio */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}>Inizio Noleggio</label>
                  <input 
                    type="date"
                    value={editingVeicolo.data_inizio || ''}
                    onChange={(e) => setEditingVeicolo({...editingVeicolo, data_inizio: e.target.value})}
                    style={{ width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13 }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}>Fine Noleggio</label>
                  <input 
                    type="date"
                    value={editingVeicolo.data_fine || ''}
                    onChange={(e) => setEditingVeicolo({...editingVeicolo, data_fine: e.target.value})}
                    style={{ width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13 }}
                  />
                </div>
              </div>

              {/* Note */}
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}>Note</label>
                <input 
                  type="text"
                  value={editingVeicolo.note || ''}
                  onChange={(e) => setEditingVeicolo({...editingVeicolo, note: e.target.value})}
                  placeholder="Note aggiuntive"
                  style={{ width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13 }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 20 }}>
              <button 
                onClick={() => { handleDelete(editingVeicolo.targa); setEditingVeicolo(null); }}
                style={{ padding: '10px 16px', background: '#fee2e2', color: '#dc2626', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: '600' }}
              >
                🗑️ Elimina
              </button>
              <div style={{ display: 'flex', gap: 10 }}>
                <button 
                  onClick={() => setEditingVeicolo(null)}
                  style={{ padding: '10px 16px', background: '#f3f4f6', color: '#374151', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: '600' }}
                >
                  Annulla
                </button>
                <button 
                  onClick={handleSaveVeicolo}
                  style={{ padding: '10px 16px', background: '#1535a8', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: '600' }}
                >
                  💾 Salva
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal Aggiungi Veicolo (per LeasePlan o altri senza targa in fattura) */}
      {showAddVeicolo && (
        <div style={{ 
          position: 'fixed', 
          inset: 0, 
          background: 'rgba(0,0,0,0.5)', 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div style={{ 
            background: 'white', 
            borderRadius: 12, 
            padding: 24, 
            width: '100%', 
            maxWidth: 500
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h2 style={{ margin: 0, fontSize: 18 }}>➕ Aggiungi Veicolo</h2>
              <button onClick={() => setShowAddVeicolo(false)} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer' }}>✕</button>
            </div>

            <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>
              Usa questo form per aggiungere veicoli di fornitori che non includono la targa nelle fatture (es: LeasePlan).
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: '500', marginBottom: 4 }}>Targa *</label>
                <input 
                  type="text"
                  value={nuovoVeicolo.targa}
                  onChange={(e) => setNuovoVeicolo({...nuovoVeicolo, targa: e.target.value.toUpperCase()})}
                  placeholder="Es: AB123CD"
                  maxLength={7}
                  style={{ width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 14, fontFamily: 'monospace' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: '500', marginBottom: 4 }}>Fornitore *</label>
                <select
                  value={nuovoVeicolo.fornitore_piva}
                  onChange={(e) => setNuovoVeicolo({...nuovoVeicolo, fornitore_piva: e.target.value})}
                  style={{ width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 14 }}
                >
                  <option value="">-- Seleziona Fornitore --</option>
                  {fornitori.map(f => (
                    <option key={f.piva} value={f.piva}>
                      {f.nome} {!f.targa_in_fattura ? '⚠️' : ''}
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: '500', marginBottom: 4 }}>Marca</label>
                  <input 
                    type="text"
                    value={nuovoVeicolo.marca}
                    onChange={(e) => setNuovoVeicolo({...nuovoVeicolo, marca: e.target.value})}
                    placeholder="Es: BMW"
                    style={{ width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 14 }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: '500', marginBottom: 4 }}>Modello</label>
                  <input 
                    type="text"
                    value={nuovoVeicolo.modello}
                    onChange={(e) => setNuovoVeicolo({...nuovoVeicolo, modello: e.target.value})}
                    placeholder="Es: X3 xDrive"
                    style={{ width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 14 }}
                  />
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: '500', marginBottom: 4 }}>Numero Contratto</label>
                <input 
                  type="text"
                  value={nuovoVeicolo.contratto}
                  onChange={(e) => setNuovoVeicolo({...nuovoVeicolo, contratto: e.target.value})}
                  placeholder="Numero contratto noleggio"
                  style={{ width: '100%', padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 14 }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 24 }}>
              <button 
                onClick={() => setShowAddVeicolo(false)}
                style={{ padding: '10px 16px', background: '#f3f4f6', color: '#374151', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: '600' }}
              >
                Annulla
              </button>
              <button 
                onClick={handleAddVeicolo}
                style={{ padding: '10px 16px', background: '#1535a8', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: '600' }}
              >
                ➕ Aggiungi
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
    </PageLayout>
  );
}

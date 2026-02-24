import React, { useState, useEffect, useCallback } from "react";
import api from "../api";
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge } from "../lib/utils";
import { PageLayout } from '../components/PageLayout';
import { useAnnoGlobale } from '../contexts/AnnoContext';

const cardStyle = STYLES.card;

const STATI_VERBALE = {
  'da_scaricare': { label: 'Da Scaricare', color: COLORS.warning, bg: '#fef3c7', icon: '📧' },
  'salvato': { label: 'Salvato', color: '#6366f1', bg: '#e0e7ff', icon: '💾' },
  'fattura_ricevuta': { label: 'Fattura Ricevuta', color: COLORS.info, bg: '#dbeafe', icon: '📄' },
  'pagato': { label: 'Pagato', color: '#10b981', bg: '#d1fae5', icon: '💳' },
  'pagato_attesa_fattura': { label: 'Pagato (att. fattura)', color: '#f59e0b', bg: '#fef3c7', icon: '⏳' },
  'riconciliato': { label: 'Riconciliato', color: COLORS.success, bg: '#a7f3d0', icon: '✅' },
  'sconosciuto': { label: 'Sconosciuto', color: COLORS.gray, bg: '#f3f4f6', icon: '❓' }
};

export default function VerbaliRiconciliazione() {
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState(null);
  const [verbali, setVerbali] = useState([]);
  const [filtroStato, setFiltroStato] = useState('');
  const [filtroTarga, setFiltroTarga] = useState('');
  const [soloRiconciliare, setSoloRiconciliare] = useState(false);
  const [ordinamento, setOrdinamento] = useState('data_verbale');
  const [selectedVerbale, setSelectedVerbale] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [collegandoDriver, setCollegandoDriver] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  
  // Nuovi state per associazione manuale
  const [dipendenti, setDipendenti] = useState([]);
  const [showAssociaModal, setShowAssociaModal] = useState(false);
  const [selectedTargaForAssoc, setSelectedTargaForAssoc] = useState('');
  const [selectedDriverId, setSelectedDriverId] = useState('');
  const [associating, setAssociating] = useState(false);

  const loadDashboard = useCallback(async () => {
    try {
      const res = await api.get('/api/verbali-riconciliazione/dashboard');
      setDashboard(res.data);
    } catch (e) {
      console.error('Error loading dashboard:', e);
    }
  }, []);

  const loadDipendenti = useCallback(async () => {
    try {
      const res = await api.get('/api/dipendenti');
      // Filtra solo dipendenti con nome valido
      const filtered = (res.data || []).filter(d => d.name || d.nome);
      setDipendenti(filtered);
    } catch (e) {
      console.error('Error loading dipendenti:', e);
    }
  }, []);

  const loadVerbali = useCallback(async () => {
    setLoading(true);
    try {
      let url = '/api/verbali-riconciliazione/lista?';
      if (filtroStato) url += `stato=${filtroStato}&`;
      if (filtroTarga) url += `targa=${filtroTarga}&`;
      if (soloRiconciliare) url += `da_riconciliare=true&`;
      url += `ordinamento=${ordinamento}&`;
      
      const res = await api.get(url);
      setVerbali(res.data.verbali || []);
    } catch (e) {
      console.error('Error loading verbali:', e);
      setError('Errore caricamento verbali');
    } finally {
      setLoading(false);
    }
  }, [filtroStato, filtroTarga, soloRiconciliare, ordinamento]);

  useEffect(() => {
    loadDashboard();
    loadVerbali();
    loadDipendenti();
  }, [loadDashboard, loadVerbali, loadDipendenti]);

  const handleScanFatture = async () => {
    setScanning(true);
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.post('/api/verbali-riconciliazione/scan-fatture-verbali');
      setSuccessMsg(`Scan completato: ${res.data.fatture_analizzate} fatture, ${res.data.verbali_trovati} verbali trovati, ${res.data.associazioni_create} nuove associazioni`);
      loadDashboard();
      loadVerbali();
    } catch (e) {
      setError('Errore durante scan fatture');
    } finally {
      setScanning(false);
    }
  };

  const handleCollegaDriver = async () => {
    setCollegandoDriver(true);
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.post('/api/verbali-riconciliazione/collega-driver-massivo');
      setSuccessMsg(`Driver collegati: ${res.data.collegati_a_driver} verbali associati su ${res.data.verbali_analizzati} analizzati`);
      loadDashboard();
      loadVerbali();
    } catch (e) {
      setError('Errore durante collegamento driver');
    } finally {
      setCollegandoDriver(false);
    }
  };

  const handleRiconcilia = async (numeroVerbale) => {
    try {
      const res = await api.post(`/api/verbali-riconciliazione/riconcilia/${numeroVerbale}`);
      setSuccessMsg(`Verbale ${numeroVerbale}: ${res.data.azioni?.join(', ') || 'Nessuna azione'}`);
      loadDashboard();
      loadVerbali();
      if (selectedVerbale?.numero_verbale === numeroVerbale) {
        setSelectedVerbale(res.data.verbale);
      }
    } catch (e) {
      setError(`Errore riconciliazione ${numeroVerbale}`);
    }
  };

  // Funzione per associare manualmente targa a driver
  const handleAssociaTargaDriver = async () => {
    if (!selectedTargaForAssoc || !selectedDriverId) {
      setError('Seleziona sia la targa che il driver');
      return;
    }
    
    setAssociating(true);
    setError('');
    try {
      const res = await api.post(`/api/auto-repair/collega-targa-driver?targa=${selectedTargaForAssoc}&driver_id=${selectedDriverId}`);
      setSuccessMsg(`Targa ${selectedTargaForAssoc} associata a ${res.data.driver}. ${res.data.verbali_aggiornati} verbali aggiornati.`);
      setShowAssociaModal(false);
      setSelectedTargaForAssoc('');
      setSelectedDriverId('');
      loadDashboard();
      loadVerbali();
    } catch (e) {
      setError(`Errore associazione: ${e.response?.data?.detail || e.message}`);
    } finally {
      setAssociating(false);
    }
  };

  // Ottieni targhe uniche senza driver dai verbali
  const getTargheSenzaDriver = () => {
    const targheSet = new Set();
    verbali.forEach(v => {
      if (v.targa && !v.driver_id) {
        targheSet.add(v.targa);
      }
    });
    return Array.from(targheSet).sort();
  };

  const getStatoInfo = (stato) => STATI_VERBALE[stato] || STATI_VERBALE['sconosciuto'];

  return (
    <PageLayout title="Riconciliazione Verbali Noleggio" subtitle="Gestione completa: Verbale → Fattura → Veicolo → Driver">
    <div style={{ maxWidth: 1600, margin: '0 auto' }}>
      {/* Header con azioni */}
      <div style={{ 
        display: 'flex', 
        justifyContent: 'flex-end', 
        alignItems: 'center', 
        marginBottom: 20,
        gap: 12,
        flexWrap: 'wrap'
      }}>
        <button
          onClick={handleScanFatture}
          disabled={scanning}
          style={{
            padding: '12px 24px',
            background: '#dc2626',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: scanning ? 'wait' : 'pointer',
            fontWeight: 'bold',
            fontSize: 14,
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}
          data-testid="btn-scan-fatture"
        >
          {scanning ? '⏳ Scanning...' : '🔍 Scan Fatture Noleggiatori'}
        </button>
        <button
          onClick={handleCollegaDriver}
          disabled={collegandoDriver}
          style={{
            padding: '12px 24px',
            background: '#6366f1',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: collegandoDriver ? 'wait' : 'pointer',
            fontWeight: 'bold',
            fontSize: 14,
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}
          data-testid="btn-collega-driver"
        >
          {collegandoDriver ? '⏳ Collegando...' : '👤 Associa Driver'}
        </button>
        <button
          onClick={() => setShowAssociaModal(true)}
          style={{
            padding: '12px 24px',
            background: '#16a34a',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: 'bold',
            fontSize: 14,
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}
          data-testid="btn-associa-manuale"
        >
          🔗 Associazione Manuale
        </button>
        </div>

      {/* Modal Associazione Manuale */}
      {showAssociaModal && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div style={{
            background: 'white',
            borderRadius: 16,
            padding: 24,
            width: '90%',
            maxWidth: 500,
            boxShadow: '0 25px 50px rgba(0,0,0,0.25)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h2 style={{ margin: 0, fontSize: 20, fontWeight: 'bold', color: '#1535a8' }}>
                🔗 Associa Targa a Driver
              </h2>
              <button
                onClick={() => setShowAssociaModal(false)}
                style={{ background: 'none', border: 'none', fontSize: 24, cursor: 'pointer', color: '#6080a0' }}
              >×</button>
            </div>
            
            <p style={{ fontSize: 14, color: '#6080a0', marginBottom: 20 }}>
              Seleziona una targa e un driver per creare l'associazione. Tutti i verbali con questa targa verranno automaticamente collegati al driver.
            </p>

            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 14, fontWeight: '600', color: '#374151', marginBottom: 6 }}>
                Targa Veicolo
              </label>
              <select
                value={selectedTargaForAssoc}
                onChange={(e) => setSelectedTargaForAssoc(e.target.value)}
                style={{
                  width: '100%',
                  padding: '12px 14px',
                  borderRadius: 8,
                  border: '2px solid #dce8f4',
                  fontSize: 14
                }}
                data-testid="select-targa-assoc"
              >
                <option value="">-- Seleziona Targa --</option>
                {getTargheSenzaDriver().map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>

            <div style={{ marginBottom: 24 }}>
              <label style={{ display: 'block', fontSize: 14, fontWeight: '600', color: '#374151', marginBottom: 6 }}>
                Driver (Dipendente)
              </label>
              <select
                value={selectedDriverId}
                onChange={(e) => setSelectedDriverId(e.target.value)}
                style={{
                  width: '100%',
                  padding: '12px 14px',
                  borderRadius: 8,
                  border: '2px solid #dce8f4',
                  fontSize: 14
                }}
                data-testid="select-driver-assoc"
              >
                <option value="">-- Seleziona Driver --</option>
                {dipendenti.map(d => (
                  <option key={d.id} value={d.id}>
                    {d.name || `${d.nome || ''} ${d.cognome || ''}`.trim()}
                  </option>
                ))}
              </select>
            </div>

            <div style={{ display: 'flex', gap: 12 }}>
              <button
                onClick={() => setShowAssociaModal(false)}
                style={{
                  flex: 1,
                  padding: '12px',
                  background: '#f3f4f6',
                  color: '#374151',
                  border: 'none',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontWeight: '600'
                }}
              >
                Annulla
              </button>
              <button
                onClick={handleAssociaTargaDriver}
                disabled={associating || !selectedTargaForAssoc || !selectedDriverId}
                style={{
                  flex: 1,
                  padding: '12px',
                  background: (!selectedTargaForAssoc || !selectedDriverId) ? '#dce8f4' : '#16a34a',
                  color: (!selectedTargaForAssoc || !selectedDriverId) ? '#9ca3af' : 'white',
                  border: 'none',
                  borderRadius: 8,
                  cursor: (!selectedTargaForAssoc || !selectedDriverId) ? 'default' : 'pointer',
                  fontWeight: '600'
                }}
                data-testid="btn-conferma-associazione"
              >
                {associating ? '⏳ Associando...' : '✅ Associa'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Messaggi */}
      {error && (
        <div style={{ padding: 16, background: '#fee2e2', border: '1px solid #fecaca', borderRadius: 8, color: '#dc2626', marginBottom: 16 }}>
          ❌ {error}
          <button onClick={() => setError('')} style={{ float: 'right', background: 'none', border: 'none', cursor: 'pointer' }}>✕</button>
        </div>
      )}
      {successMsg && (
        <div style={{ padding: 16, background: '#d1fae5', border: '1px solid #a7f3d0', borderRadius: 8, color: '#059669', marginBottom: 16 }}>
          ✅ {successMsg}
          <button onClick={() => setSuccessMsg('')} style={{ float: 'right', background: 'none', border: 'none', cursor: 'pointer' }}>✕</button>
        </div>
      )}

      {/* Dashboard Cards */}
      {dashboard && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16, marginBottom: 24 }}>
          <div style={{ ...cardStyle, background: '#fef2f2', textAlign: 'center' }}>
            <div style={{ fontSize: 13, color: '#6080a0', marginBottom: 4 }}>Totale Verbali</div>
            <div style={{ fontSize: 32, fontWeight: 'bold', color: '#dc2626' }}>{dashboard.riepilogo?.totale_verbali || 0}</div>
          </div>
          <div style={{ ...cardStyle, background: '#fff7ed', textAlign: 'center' }}>
            <div style={{ fontSize: 13, color: '#6080a0', marginBottom: 4 }}>Da Riconciliare</div>
            <div style={{ fontSize: 32, fontWeight: 'bold', color: '#f59e0b' }}>{dashboard.riepilogo?.da_riconciliare || 0}</div>
          </div>
          <div style={{ ...cardStyle, background: '#f0fdf4', textAlign: 'center' }}>
            <div style={{ fontSize: 13, color: '#6080a0', marginBottom: 4 }}>Riconciliati</div>
            <div style={{ fontSize: 32, fontWeight: 'bold', color: '#16a34a' }}>{dashboard.riepilogo?.per_stato?.riconciliato?.count || 0}</div>
          </div>
          <div style={{ ...cardStyle, background: '#eff6ff', textAlign: 'center' }}>
            <div style={{ fontSize: 13, color: '#6080a0', marginBottom: 4 }}>Totale Importo</div>
            <div style={{ fontSize: 24, fontWeight: 'bold', color: '#1535a8' }}>{formatEuro(dashboard.riepilogo?.totale_importo)}</div>
          </div>
        </div>
      )}

      {/* Filtri */}
      <div style={{ ...cardStyle, marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          <div>
            <label style={{ fontSize: 12, color: '#6080a0', display: 'block', marginBottom: 4 }}>Stato</label>
            <select
              value={filtroStato}
              onChange={(e) => setFiltroStato(e.target.value)}
              style={{ padding: '10px 14px', borderRadius: 8, border: '2px solid #dce8f4', fontSize: 14, minWidth: 180 }}
              data-testid="filtro-stato"
            >
              <option value="">Tutti gli stati</option>
              {Object.entries(STATI_VERBALE).map(([key, val]) => (
                <option key={key} value={key}>{val.icon} {val.label}</option>
              ))}
            </select>
          </div>
          
          <div>
            <label style={{ fontSize: 12, color: '#6080a0', display: 'block', marginBottom: 4 }}>Targa</label>
            <input
              type="text"
              placeholder="es: GE911SC"
              value={filtroTarga}
              onChange={(e) => setFiltroTarga(e.target.value.toUpperCase())}
              style={{ padding: '10px 14px', borderRadius: 8, border: '2px solid #dce8f4', fontSize: 14, width: 140 }}
              data-testid="filtro-targa"
            />
          </div>

          <div style={{ marginTop: 20 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={soloRiconciliare}
                onChange={(e) => setSoloRiconciliare(e.target.checked)}
                style={{ width: 18, height: 18 }}
              />
              <span style={{ fontSize: 14, fontWeight: '500' }}>Solo da riconciliare</span>
            </label>
          </div>

          <div>
            <label style={{ fontSize: 12, color: '#6080a0', display: 'block', marginBottom: 4 }}>Ordina per</label>
            <div style={{ display: 'flex', gap: 4 }}>
              {[
                { key: 'numero_verbale', label: 'N. Verbale' },
                { key: 'data_verbale', label: 'Data Verbale' },
                { key: 'created_at', label: 'Inserimento' },
              ].map(opt => (
                <button
                  key={opt.key}
                  onClick={() => setOrdinamento(opt.key)}
                  data-testid={`sort-${opt.key}`}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 6,
                    border: ordinamento === opt.key ? '2px solid #1535a8' : '2px solid #dce8f4',
                    background: ordinamento === opt.key ? '#1535a8' : 'white',
                    color: ordinamento === opt.key ? 'white' : '#374151',
                    fontSize: 13,
                    fontWeight: ordinamento === opt.key ? '600' : '400',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap'
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={loadVerbali}
            style={{ padding: '10px 20px', background: '#1535a8', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: '600', marginTop: 20, marginLeft: 'auto' }}
          >
            🔄 Aggiorna
          </button>
        </div>
      </div>

      {/* Content */}
      <div style={{ display: 'grid', gridTemplateColumns: selectedVerbale ? '1fr 400px' : '1fr', gap: 20 }}>
        
        {/* Lista Verbali */}
        <div style={cardStyle}>
          <h2 style={{ margin: '0 0 16px 0', fontSize: 18, fontWeight: 'bold', color: '#1535a8' }}>
            📋 Verbali ({verbali.length})
          </h2>
          
          {loading ? (
            <div style={{ textAlign: 'center', padding: 40, color: '#6080a0' }}>⏳ Caricamento...</div>
          ) : verbali.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40, color: '#6080a0' }}>
              Nessun verbale trovato con i filtri selezionati
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 6px', fontSize: 13 }}>
                <thead>
                  <tr style={{ background: '#f8fafc' }}>
                    <th style={{ padding: '12px 14px', textAlign: 'left', fontWeight: '600', color: '#475569' }}>Verbale</th>
                    <th style={{ padding: '12px 14px', textAlign: 'left', fontWeight: '600', color: '#475569' }}>Data</th>
                    <th style={{ padding: '12px 14px', textAlign: 'left', fontWeight: '600', color: '#475569' }}>Targa</th>
                    <th style={{ padding: '12px 14px', textAlign: 'left', fontWeight: '600', color: '#475569' }}>Driver</th>
                    <th style={{ padding: '12px 14px', textAlign: 'left', fontWeight: '600', color: '#475569' }}>Fattura</th>
                    <th style={{ padding: '12px 14px', textAlign: 'right', fontWeight: '600', color: '#475569' }}>Importo</th>
                    <th style={{ padding: '12px 14px', textAlign: 'center', fontWeight: '600', color: '#475569' }}>Stato</th>
                    <th style={{ padding: '12px 14px', textAlign: 'center', fontWeight: '600', color: '#475569' }}>Azioni</th>
                  </tr>
                </thead>
                <tbody>
                  {verbali.map((v) => {
                    const statoInfo = getStatoInfo(v.stato);
                    return (
                      <tr 
                        key={v.id || v.numero_verbale} 
                        style={{ 
                          background: selectedVerbale?.numero_verbale === v.numero_verbale ? '#fef3c7' : 'white',
                          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                          cursor: 'pointer'
                        }}
                        onClick={() => setSelectedVerbale(v)}
                        data-testid={`verbale-row-${v.numero_verbale}`}
                      >
                        <td style={{ padding: '14px', borderRadius: '8px 0 0 8px' }}>
                          <div style={{ fontWeight: 'bold', color: '#dc2626', fontFamily: 'monospace' }}>{v.numero_verbale}</div>
                        </td>
                        <td style={{ padding: '14px' }}>
                          <span style={{ fontSize: 12, color: '#475569' }}>{v.data_verbale ? formatDateIT(v.data_verbale) : '-'}</span>
                        </td>
                        <td style={{ padding: '14px' }}>
                          <span style={{ fontWeight: '600', color: '#1535a8' }}>{v.targa || '-'}</span>
                        </td>
                        <td style={{ padding: '14px' }}>
                          {v.driver_nome || v.driver ? (
                            <span style={{ 
                              fontWeight: '500', 
                              color: '#059669',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 4
                            }}>
                              👤 {v.driver_nome || v.driver}
                            </span>
                          ) : (
                            <span style={{ color: '#f59e0b', fontStyle: 'italic', fontSize: 12 }}>Da associare</span>
                          )}
                        </td>
                        <td style={{ padding: '14px' }}>
                          {v.fattura_numero ? (
                            <div>
                              <div style={{ fontWeight: '500' }}>{v.fattura_numero}</div>
                              <div style={{ fontSize: 11, color: '#9ca3af' }}>{v.fornitore}</div>
                            </div>
                          ) : (
                            <span style={{ color: '#9ca3af' }}>-</span>
                          )}
                        </td>
                        <td style={{ padding: '14px', textAlign: 'right', fontFamily: 'monospace', fontWeight: '600' }}>
                          {v.importo ? formatEuro(v.importo) : '-'}
                        </td>
                        <td style={{ padding: '14px', textAlign: 'center' }}>
                          <span style={{ 
                            padding: '6px 12px', 
                            background: statoInfo.bg, 
                            color: statoInfo.color, 
                            borderRadius: 20, 
                            fontSize: 11, 
                            fontWeight: '600',
                            whiteSpace: 'nowrap'
                          }}>
                            {statoInfo.icon} {statoInfo.label}
                          </span>
                        </td>
                        <td style={{ padding: '14px', textAlign: 'center', borderRadius: '0 8px 8px 0' }}>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleRiconcilia(v.numero_verbale); }}
                            style={{
                              padding: '8px 14px',
                              background: v.stato === 'riconciliato' ? '#dce8f4' : '#1535a8',
                              color: v.stato === 'riconciliato' ? '#9ca3af' : 'white',
                              border: 'none',
                              borderRadius: 6,
                              cursor: v.stato === 'riconciliato' ? 'default' : 'pointer',
                              fontSize: 12,
                              fontWeight: '600'
                            }}
                            disabled={v.stato === 'riconciliato'}
                            data-testid={`btn-riconcilia-${v.numero_verbale}`}
                          >
                            🔄 Riconcilia
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Dettaglio Verbale */}
        {selectedVerbale && (
          <div style={cardStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h2 style={{ margin: 0, fontSize: 16, fontWeight: 'bold', color: '#1535a8' }}>
                📌 Dettaglio Verbale
              </h2>
              <button 
                onClick={() => setSelectedVerbale(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, color: '#6080a0' }}
              >
                ✕
              </button>
            </div>

            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 20, fontWeight: 'bold', color: '#dc2626', fontFamily: 'monospace' }}>
                {selectedVerbale.numero_verbale}
              </div>
              <span style={{ 
                ...(() => { const s = getStatoInfo(selectedVerbale.stato); return { background: s.bg, color: s.color }; })(),
                padding: '6px 12px', 
                borderRadius: 20, 
                fontSize: 12, 
                fontWeight: '600',
                display: 'inline-block',
                marginTop: 8
              }}>
                {getStatoInfo(selectedVerbale.stato).icon} {getStatoInfo(selectedVerbale.stato).label}
              </span>
            </div>

            <div style={{ background: '#f8fafc', borderRadius: 8, padding: 16 }}>
              <div style={{ display: 'grid', gap: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6080a0' }}>Targa:</span>
                  <strong>{selectedVerbale.targa || '-'}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6080a0' }}>Importo Verbale:</span>
                  <strong style={{ color: '#dc2626' }}>{selectedVerbale.importo ? formatEuro(selectedVerbale.importo) : '-'}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6080a0' }}>Importo Notifica:</span>
                  <strong>{selectedVerbale.importo_notifica ? formatEuro(selectedVerbale.importo_notifica) : '-'}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6080a0' }}>Data Verbale:</span>
                  <strong>{formatDateIT(selectedVerbale.data_verbale) || '-'}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6080a0' }}>Data Pagamento:</span>
                  <strong>{formatDateIT(selectedVerbale.data_pagamento) || '-'}</strong>
                </div>
              </div>
            </div>

            {/* Fattura associata */}
            {selectedVerbale.fattura_numero && (
              <div style={{ marginTop: 16 }}>
                <h4 style={{ margin: '0 0 8px 0', fontSize: 14, fontWeight: '600', color: '#1535a8' }}>📄 Fattura Associata</h4>
                <div style={{ background: '#dbeafe', borderRadius: 8, padding: 12 }}>
                  <div style={{ fontWeight: 'bold' }}>{selectedVerbale.fattura_numero}</div>
                  <div style={{ fontSize: 12, color: '#1535a8' }}>{selectedVerbale.fornitore}</div>
                </div>
              </div>
            )}

            {/* Driver associato */}
            {selectedVerbale.driver_nome && (
              <div style={{ marginTop: 16 }}>
                <h4 style={{ margin: '0 0 8px 0', fontSize: 14, fontWeight: '600', color: '#1535a8' }}>👤 Driver Associato</h4>
                <div style={{ background: '#f0fdf4', borderRadius: 8, padding: 12 }}>
                  <div style={{ fontWeight: 'bold', color: '#16a34a' }}>{selectedVerbale.driver_nome}</div>
                </div>
              </div>
            )}

            {/* Azioni */}
            <div style={{ marginTop: 20, display: 'flex', gap: 10 }}>
              <button
                onClick={() => handleRiconcilia(selectedVerbale.numero_verbale)}
                disabled={selectedVerbale.stato === 'riconciliato'}
                style={{
                  flex: 1,
                  padding: '12px',
                  background: selectedVerbale.stato === 'riconciliato' ? '#dce8f4' : '#1535a8',
                  color: selectedVerbale.stato === 'riconciliato' ? '#9ca3af' : 'white',
                  border: 'none',
                  borderRadius: 8,
                  cursor: selectedVerbale.stato === 'riconciliato' ? 'default' : 'pointer',
                  fontWeight: '600'
                }}
              >
                🔄 Riconcilia Automatico
              </button>
              <button
                onClick={() => window.open(`/verbali-noleggio/${selectedVerbale.numero_verbale}`, '_blank')}
                style={{
                  padding: '12px 16px',
                  background: '#f3f4f6',
                  color: '#374151',
                  border: 'none',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontWeight: '600'
                }}
              >
                📄 Dettaglio
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Info Box */}
      <div style={{ marginTop: 24, padding: 20, background: '#fef3c7', borderRadius: 12, fontSize: 14 }}>
        <h3 style={{ margin: '0 0 12px 0', fontSize: 16, color: '#92400e' }}>ℹ️ Flusso Riconciliazione Verbali</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 16 }}>
          <div>
            <strong>📧 Scenario A - Pago Prima:</strong>
            <ol style={{ margin: '8px 0 0 16px', padding: 0, color: '#78350f' }}>
              <li>Driver trova verbale sul parabrezza</li>
              <li>Pago subito (prima della fattura)</li>
              <li>Scarico da posta → Salvo verbale</li>
              <li>Arriva fattura → La associo</li>
              <li>Riconcilio: Verbale + Fattura + Pagamento</li>
            </ol>
          </div>
          <div>
            <strong>📄 Scenario B - Fattura Prima:</strong>
            <ol style={{ margin: '8px 0 0 16px', padding: 0, color: '#78350f' }}>
              <li>Arriva fattura dal noleggiatore</li>
              <li>Estraggo numero verbale dalla descrizione</li>
              <li>Pago il verbale</li>
              <li>Riconcilio: Fattura + Verbale + Pagamento</li>
            </ol>
          </div>
        </div>
        <div style={{ marginTop: 12, fontSize: 13, color: '#92400e' }}>
          <strong>Catena:</strong> Verbale → Fattura (spese notifica) → Veicolo (targa) → Driver (dipendente)
        </div>
      </div>
    </div>
    </PageLayout>
  );
}

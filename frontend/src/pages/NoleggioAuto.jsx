import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import {
  formatEuro,
  formatDateIT,
  STYLES,
  COLORS,
  SHADOWS,
  BORDER_RADIUS,
  button,
  badge,
  useIsMobile,
  RG,
  pagePad,
} from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';
import ModalFattura from '../components/ModalFattura';
import { toast } from 'sonner';

export default function NoleggioAuto() {
  const isMobile = useIsMobile();
  // Anno unico e globale (barra di navigazione in alto) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â nessun selettore
  // locale duplicato: una pagina con un filtro anno proprio, indipendente
  // da quello globale, dava l'impressione che cambiare l'anno in alto non
  // avesse alcun effetto sulla pagina.
  const { anno } = useAnnoGlobale();
  const annoFiltro = anno;
  const [veicoli, setVeicoli] = useState([]);
  const [statistiche, setStatistiche] = useState({});
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [selectedVeicolo, setSelectedVeicolo] = useState(null);
  const [fatturaView, setFatturaView] = useState(null);
  const [drivers, setDrivers] = useState([]);
  const [editingVeicolo, setEditingVeicolo] = useState(null);
  const [expandedSection, setExpandedSection] = useState({});
  const [fornitori, setFornitori] = useState([]);
  const [showAddVeicolo, setShowAddVeicolo] = useState(false);
  const [nuovoVeicolo, setNuovoVeicolo] = useState({
    targa: '',
    marca: '',
    modello: '',
    fornitore_piva: '',
    contratto: '',
  });
  const [fattureNonAssociate, setFattureNonAssociate] = useState(0);
  const [modalFattureNonAssociate, setModalFattureNonAssociate] = useState({
    open: false,
    loading: false,
    fatture: [],
    errore: '',
  });
  // Stato per lookup OpenAPI
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupResult, setLookupResult] = useState(null);
  const [bulkUpdateLoading, setBulkUpdateLoading] = useState(false);

  const categorie = [
    { key: 'canoni', label: 'Canoni', icon: 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¹', color: '#4caf50' },
    { key: 'pedaggio', label: 'Pedaggio', icon: 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂºÃƒâ€šÃ‚Â£ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â', color: '#2196f3' },
    { key: 'verbali', label: 'Verbali', icon: 'ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â', color: '#f44336' },
    { key: 'bollo', label: 'Bollo', icon: 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾', color: '#9c27b0' },
    { key: 'costi_extra', label: 'Costi Extra', icon: 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢Ãƒâ€šÃ‚Â³', color: '#ff9800' },
    { key: 'riparazioni', label: 'Riparazioni', icon: 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒâ€šÃ‚Â§', color: '#795548' },
  ];

  const fetchVeicoli = useCallback(async () => {
    setLoading(true);
    setErr('');
    try {
      // Se annoFiltro ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¨ null, carica TUTTI gli anni
      const annoParam = annoFiltro ? `anno=${annoFiltro}` : '';
      const [vRes, dRes, fRes] = await Promise.all([
        api.get(`/api/noleggio/veicoli?${annoParam}`),
        api.get('/api/noleggio/drivers'),
        api.get('/api/noleggio/fornitori'),
      ]);
      setVeicoli(vRes.data.veicoli || []);
      setStatistiche(vRes.data.statistiche || {});
      setFattureNonAssociate(vRes.data.fatture_non_associate || 0);
      setDrivers(dRes.data.drivers || []);
      setFornitori(fRes.data.fornitori || []);
    } catch (e) {
      console.error('Errore:', e);
      setErr('Errore caricamento dati: ' + (e.response?.data?.detail || e.message));
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

  const handleDelete = async targa => {
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

  const toggleSection = section => {
    setExpandedSection(prev => ({ ...prev, [section]: !prev[section] }));
  };

  // Funzione per lookup dati veicolo da OpenAPI Automotive
  const handleLookupVeicolo = async targa => {
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
  const handleUpdateFromOpenAPI = async targa => {
    if (!targa) return;
    setLookupLoading(true);
    try {
      const res = await api.post('/api/openapi-automotive/aggiorna-veicolo', { targa });
      if (res.data?.success) {
        toast.success(
          `${res.data.action === 'created' ? 'Creato' : 'Aggiornato'} veicolo ${targa}`
        );
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

    if (
      !window.confirm(
        `Aggiornare dati da OpenAPI per ${targhe.length} veicoli?\nQuesta operazione puÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â² richiedere alcuni minuti.`
      )
    ) {
      return;
    }

    setBulkUpdateLoading(true);
    try {
      const res = await api.post('/api/openapi-automotive/aggiorna-bulk', { targhe });
      const { aggiornati, creati, errori, dettagli } = res.data;
      toast.success(`Completato: ${aggiornati} aggiornati, ${creati} creati, ${errori} errori`);

      if (errori > 0) {
        const erroriList = dettagli
          .filter(d => d.status === 'error')
          .map(d => `${d.targa}: ${d.error}`)
          .join('\n');
        console.warn('Errori aggiornamento:', erroriList);
      }

      fetchVeicoli();
    } catch (e) {
      toast.error(`Errore bulk update: ${e.response?.data?.detail || e.message}`);
    } finally {
      setBulkUpdateLoading(false);
    }
  };

  const formatDate = dateStr => {
    if (!dateStr) return '-';
    try {
      return formatDateIT(dateStr);
    } catch {
      return dateStr;
    }
  };

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto' }}>
      {/* Header ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â stile uniforme al resto delle pagine (STYLES.header) */}
      <div style={STYLES.header}>
        <div>
          <h1 style={STYLES.pageTitle}>ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸Ãƒâ€¦Ã‚Â¡ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Gestione Noleggio Auto</h1>
          <p style={{ ...STYLES.pageSubtitle, marginTop: 4 }}>
            Flotta aziendale ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ Dati estratti da fatture XML
          </p>
        </div>
      </div>

      {/* Azioni */}
      <div
        style={{
          display: 'flex',
          gap: 10,
          marginBottom: 20,
          flexWrap: 'wrap',
          alignItems: 'center',
        }}
      >
        <button
          onClick={fetchVeicoli}
          style={button('secondary')}
          data-testid="noleggio-refresh-btn"
        >
          ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾ Aggiorna
        </button>
        <button
          onClick={() => setShowAddVeicolo(true)}
          style={button('primary')}
          data-testid="noleggio-add-btn"
        >
          ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¾ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¢ Aggiungi Veicolo
        </button>
        <button
          onClick={handleBulkUpdateFromOpenAPI}
          disabled={bulkUpdateLoading || veicoli.length === 0}
          style={{
            padding: '9px 16px',
            background: 'transparent',
            color: bulkUpdateLoading ? '#9ca3af' : '#059669',
            border: `1px solid ${bulkUpdateLoading ? '#e5e7eb' : '#a7f3d0'}`,
            borderRadius: 8,
            cursor: bulkUpdateLoading ? 'wait' : 'pointer',
            fontWeight: '500',
            fontSize: 13,
            opacity: veicoli.length === 0 ? 0.5 : 1,
          }}
          data-testid="noleggio-bulk-update-btn"
          title="Azione di manutenzione occasionale: recupera marca, modello, alimentazione, potenza e cilindrata da OpenAPI Automotive per tutti i veicoli in elenco"
        >
          {bulkUpdateLoading ? 'ÃƒÆ’Ã‚Â¢Ãƒâ€šÃ‚ÂÃƒâ€šÃ‚Â³ Aggiornamento...' : 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸Ãƒâ€¦Ã‚Â¡ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Aggiorna dati da targa (tutti)'}
        </button>
        {fattureNonAssociate > 0 && (
          <span
            style={{
              padding: '8px 16px',
              background: '#fef3c7',
              color: '#92400e',
              borderRadius: 8,
              fontSize: 13,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â {fattureNonAssociate} fatture non associate
            <button
              onClick={async () => {
                setModalFattureNonAssociate({ open: true, loading: true, fatture: [], errore: '' });
                try {
                  const annoParam = annoFiltro ? `?anno=${annoFiltro}` : '';
                  const res = await api.get(`/api/noleggio/fatture-non-associate${annoParam}`);
                  setModalFattureNonAssociate({
                    open: true,
                    loading: false,
                    fatture: res.data.fatture || [],
                    errore: '',
                  });
                } catch (e) {
                  setModalFattureNonAssociate({
                    open: true,
                    loading: false,
                    fatture: [],
                    errore: e.response?.data?.detail || e.message,
                  });
                }
              }}
              style={{
                padding: '4px 10px',
                background: '#f59e0b',
                color: 'white',
                border: 'none',
                borderRadius: 4,
                cursor: 'pointer',
                fontSize: 11,
                fontWeight: 600,
              }}
            >
              ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã‹Å“Ãƒâ€šÃ‚ÂÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â Visualizza
            </button>
          </span>
        )}
      </div>

      {err && (
        <div
          style={{
            padding: 12,
            background: '#fee2e2',
            border: '1px solid #fecaca',
            borderRadius: 8,
            color: '#dc2626',
            marginBottom: 20,
          }}
          data-testid="noleggio-error"
        >
          ÃƒÆ’Ã‚Â¢Ãƒâ€šÃ‚ÂÃƒâ€¦Ã¢â‚¬â„¢ {err}
        </div>
      )}

      {/* Riepilogo Totali - Se veicolo selezionato mostra i suoi dati, altrimenti totale generale */}
      {veicoli.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          {selectedVeicolo && (
            <div
              style={{
                padding: '8px 16px',
                background: '#dbeafe',
                borderRadius: '8px 8px 0 0',
                color: '#1e40af',
                fontWeight: 'bold',
                fontSize: 14,
              }}
            >
              ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒâ€¦Ã‚Â  Riepilogo: {selectedVeicolo.marca} {selectedVeicolo.modello || ''} -{' '}
              {selectedVeicolo.targa}
            </div>
          )}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
              gap: 16,
              padding: selectedVeicolo ? '16px' : 0,
              background: selectedVeicolo ? '#f8fafc' : 'transparent',
              borderRadius: selectedVeicolo ? '0 0 8px 8px' : 0,
            }}
          >
            {categorie.map(cat => {
              // Se c'ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¨ un veicolo selezionato, mostra i suoi totali, altrimenti il totale generale
              const valore = selectedVeicolo
                ? selectedVeicolo[`totale_${cat.key}`] ||
                  (selectedVeicolo[cat.key] || []).reduce((a, s) => a + (s.totale || 0), 0)
                : statistiche[`totale_${cat.key}`] || 0;

              return (
                <div
                  key={cat.key}
                  style={{
                    background: 'white',
                    borderRadius: 8,
                    padding: '10px 12px',
                    boxShadow: SHADOWS.sm,
                    borderLeft: `3px solid ${cat.color}`,
                  }}
                >
                  <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>
                    {cat.icon} {cat.label}
                  </div>
                  <div style={{ fontSize: 16, fontWeight: 'bold', color: cat.color }}>
                    {formatEuro(valore)}
                  </div>
                </div>
              );
            })}
            <div
              style={{
                background: '#1e3a5f',
                borderRadius: 8,
                padding: '10px 12px',
                boxShadow: SHADOWS.sm,
                color: 'white',
              }}
            >
              <div style={{ fontSize: 11, opacity: 0.9, marginBottom: 4 }}>ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸Ãƒâ€¦Ã‚Â¡ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â TOTALE</div>
              <div style={{ fontSize: 16, fontWeight: 'bold' }}>
                {formatEuro(
                  selectedVeicolo
                    ? selectedVeicolo.totale_generale
                    : statistiche.totale_generale || 0
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Dettaglio Veicolo Selezionato */}
      {selectedVeicolo && (
        <div
          style={{
            ...STYLES.card,
            marginBottom: 20,
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 16,
            }}
          >
            <h2 style={{ margin: 0, fontSize: 18 }}>
              ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸Ãƒâ€¦Ã‚Â¡ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â {selectedVeicolo.marca} {selectedVeicolo.modello || 'Modello da definire'} -{' '}
              <span style={{ color: '#2563eb', fontFamily: 'monospace' }}>
                {selectedVeicolo.targa}
              </span>
            </h2>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => handleUpdateFromOpenAPI(selectedVeicolo.targa)}
                disabled={lookupLoading}
                style={{
                  padding: '6px 12px',
                  background: lookupLoading ? '#9ca3af' : '#059669',
                  color: 'white',
                  border: 'none',
                  borderRadius: 6,
                  cursor: lookupLoading ? 'wait' : 'pointer',
                }}
                title="Aggiorna dati veicolo da OpenAPI Automotive"
                data-testid="veicolo-update-openapi-btn"
              >
                {lookupLoading ? 'ÃƒÆ’Ã‚Â¢Ãƒâ€šÃ‚ÂÃƒâ€šÃ‚Â³' : 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾'} Aggiorna da Targa
              </button>
              <button
                onClick={() => setEditingVeicolo({ ...selectedVeicolo })}
                style={{
                  padding: '6px 12px',
                  background: '#dbeafe',
                  color: '#2563eb',
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer',
                }}
              >
                ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã¢â‚¬Å“Ãƒâ€šÃ‚ÂÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â Modifica
              </button>
              <button
                onClick={() => handleDelete(selectedVeicolo.targa)}
                style={{
                  padding: '6px 12px',
                  background: '#fee2e2',
                  color: '#dc2626',
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer',
                }}
              >
                ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬ÂÃƒÂ¢Ã¢â€šÂ¬Ã‹Å“ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â Elimina
              </button>
              <button
                onClick={() => setSelectedVeicolo(null)}
                style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer' }}
              >
                ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã¢â‚¬Å“ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¢
              </button>
            </div>
          </div>

          {/* Info generali veicolo */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: 16,
              marginBottom: 20,
            }}
          >
            <div>
              <h3 style={{ margin: '0 0 8px 0', fontSize: 14, color: '#6b7280' }}>Veicolo</h3>
              <div style={{ fontSize: 13, lineHeight: 1.8 }}>
                <div>
                  Targa: <strong>{selectedVeicolo.targa}</strong>
                </div>
                <div>Fornitore: {selectedVeicolo.fornitore_noleggio || '-'}</div>
                <div>
                  P.IVA:{' '}
                  <span style={{ fontFamily: 'monospace', color: '#6b7280' }}>
                    {selectedVeicolo.fornitore_piva || '-'}
                  </span>
                </div>
                <div>
                  {selectedVeicolo.alimentazione || '-'}
                  {selectedVeicolo.potenza_kw ? ` ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ ${selectedVeicolo.potenza_kw} kW` : ''}
                  {selectedVeicolo.potenza_cv ? ` ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ ${selectedVeicolo.potenza_cv} CV` : ''}
                  {selectedVeicolo.cilindrata ? ` ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ ${selectedVeicolo.cilindrata} cc` : ''}
                </div>
                {selectedVeicolo.telaio && (
                  <div style={{ fontSize: 12, color: '#9ca3af' }}>
                    Telaio: <span style={{ fontFamily: 'monospace' }}>{selectedVeicolo.telaio}</span>
                  </div>
                )}
              </div>
            </div>
            <div>
              <h3 style={{ margin: '0 0 8px 0', fontSize: 14, color: '#6b7280' }}>Contratto</h3>
              <div style={{ fontSize: 13, lineHeight: 1.8 }}>
                <div>
                  NÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â° Contratto: <strong>{selectedVeicolo.contratto || '-'}</strong>
                </div>
                <div>Cod. Cliente: {selectedVeicolo.codice_cliente || '-'}</div>
                <div>Centro Fatt.: {selectedVeicolo.centro_fatturazione || '-'}</div>
                <div>
                  Canone mensile:{' '}
                  <strong>
                    {selectedVeicolo.canone_mensile ? formatEuro(selectedVeicolo.canone_mensile) : '-'}
                  </strong>
                  {selectedVeicolo.canone_mensile_stimato && (
                    <span
                      style={{ color: '#9ca3af', fontSize: 11, marginLeft: 4 }}
                      title="Stimato dall'ultimo canone fatturato, non configurato manualmente"
                    >
                      (stimato)
                    </span>
                  )}
                </div>
              </div>
            </div>
            <div>
              <h3 style={{ margin: '0 0 8px 0', fontSize: 14, color: '#6b7280' }}>Assegnazione</h3>
              <div style={{ fontSize: 13, lineHeight: 1.8 }}>
                <div>
                  Driver: <strong>{selectedVeicolo.driver || 'Non assegnato'}</strong>
                </div>
                <div>Inizio: {formatDate(selectedVeicolo.data_inizio)}</div>
                <div>Fine: {formatDate(selectedVeicolo.data_fine)}</div>
              </div>
            </div>
            <div>
              <h3 style={{ margin: '0 0 8px 0', fontSize: 14, color: '#6b7280' }}>
                Totale {annoFiltro || 'tutti gli anni'}
              </h3>
              <div style={{ fontSize: 24, fontWeight: 'bold', color: '#1e3a5f' }}>
                {formatEuro(selectedVeicolo.totale_generale)}
              </div>
            </div>
          </div>

          {/* Sezioni spese per categoria */}
          {categorie.map(cat => {
            // Ordina le spese per data (dalla piÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¹ recente alla piÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¹ vecchia)
            const spese = [...(selectedVeicolo[cat.key] || [])].sort((a, b) => {
              const dateA = new Date(a.data || '1900-01-01');
              const dateB = new Date(b.data || '1900-01-01');
              return dateB - dateA; // Ordine decrescente (piÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¹ recenti prima)
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
                    borderLeft: `4px solid ${cat.color}`,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span>{cat.icon}</span>
                    <span style={{ fontWeight: '600', color: cat.color }}>{cat.label}</span>
                    <span style={{ fontSize: 13, color: '#6b7280' }}>({spese.length} fatture)</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{ fontWeight: 'bold', fontSize: 16, color: cat.color }}>
                      {formatEuro(totaleSezione)}
                    </span>
                    <span>{isOpen ? 'ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€šÃ‚Â²' : 'ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€šÃ‚Â¼'}</span>
                  </div>
                </div>

                {isOpen && (
                  <div style={{ marginTop: 8, overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                      <thead>
                        <tr style={{ background: '#f9fafb', borderBottom: '2px solid #e5e7eb' }}>
                          <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: '600' }}>
                            Data
                          </th>
                          <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: '600' }}>
                            Fattura
                          </th>
                          {cat.key === 'verbali' && (
                            <th
                              style={{ padding: '8px 10px', textAlign: 'left', fontWeight: '600' }}
                            >
                              NÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â° Verbale
                            </th>
                          )}
                          <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: '600' }}>
                            Descrizione
                          </th>
                          <th
                            style={{ padding: '8px 10px', textAlign: 'right', fontWeight: '600' }}
                          >
                            Imponibile
                          </th>
                          <th
                            style={{ padding: '8px 10px', textAlign: 'right', fontWeight: '600' }}
                          >
                            IVA
                          </th>
                          <th
                            style={{ padding: '8px 10px', textAlign: 'right', fontWeight: '600' }}
                          >
                            Totale
                          </th>
                          <th
                            style={{ padding: '8px 10px', textAlign: 'center', fontWeight: '600' }}
                          >
                            Stato
                          </th>
                          <th
                            style={{ padding: '8px 10px', textAlign: 'center', fontWeight: '600' }}
                          >
                            Vedi
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {spese.map((s, idx) => (
                          <tr
                            key={idx}
                            style={{
                              borderBottom: '1px solid #f3f4f6',
                              background: s.imponibile < 0 ? '#fff7ed' : 'white',
                            }}
                          >
                            <td style={{ padding: '8px 10px', fontSize: 12 }}>
                              {formatDate(s.data)}
                            </td>
                            <td
                              style={{
                                padding: '8px 10px',
                                color: '#6b7280',
                                fontSize: 11,
                                fontFamily: 'monospace',
                              }}
                            >
                              {s.numero_fattura || '-'}
                            </td>
                            {cat.key === 'verbali' && (
                              <td
                                style={{
                                  padding: '8px 10px',
                                  fontSize: 11,
                                  fontFamily: 'monospace',
                                  color: s.numero_verbale ? '#dc2626' : '#9ca3af',
                                }}
                              >
                                {s.numero_verbale || '-'}
                                {s.data_verbale && (
                                  <div style={{ fontSize: 10, color: '#6b7280' }}>
                                    {formatDate(s.data_verbale)}
                                  </div>
                                )}
                              </td>
                            )}
                            <td style={{ padding: '8px 10px' }}>
                              {s.voci?.map((v, vi) => (
                                <div key={vi} style={{ paddingBottom: 4 }}>
                                  <div style={{ fontSize: 11, color: '#4b5563' }}>
                                    {v.descrizione
                                      ?.replace(selectedVeicolo.targa, '')
                                      .trim()
                                      .slice(0, 70) || '-'}
                                  </div>
                                  {(v.noleggio_imponibile != null || v.servizio_imponibile != null) && (
                                    <div style={{ fontSize: 10, color: '#9ca3af' }}>
                                      {v.noleggio_imponibile != null &&
                                        `Locazione: ${formatEuro(v.noleggio_imponibile)}`}
                                      {v.noleggio_imponibile != null && v.servizio_imponibile != null && ' ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ '}
                                      {v.servizio_imponibile != null &&
                                        `Servizi: ${formatEuro(v.servizio_imponibile)}`}
                                    </div>
                                  )}
                                  {v.causale && (
                                    <div
                                      style={{ fontSize: 10, color: '#9ca3af', fontStyle: 'italic' }}
                                      title={v.causale}
                                    >
                                      {v.causale.split(' | ').find(p => p.toUpperCase().includes('CAUSALE')) ||
                                        v.causale.slice(0, 60)}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </td>
                            <td
                              style={{
                                padding: '8px 10px',
                                textAlign: 'right',
                                color: s.imponibile < 0 ? '#ea580c' : 'inherit',
                                fontSize: 12,
                              }}
                            >
                              {formatEuro(s.imponibile)}
                            </td>
                            <td
                              style={{
                                padding: '8px 10px',
                                textAlign: 'right',
                                color: '#6b7280',
                                fontSize: 12,
                              }}
                            >
                              {formatEuro(s.iva)}
                            </td>
                            <td
                              style={{
                                padding: '8px 10px',
                                textAlign: 'right',
                                fontWeight: 'bold',
                                color: s.totale < 0 ? '#ea580c' : 'inherit',
                                fontSize: 12,
                              }}
                            >
                              {formatEuro(s.totale)}
                            </td>
                            <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                              {s.pagato ? (
                                s.pagato_confermato_banca ? (
                                  <span
                                    style={{ color: '#16a34a', fontWeight: 'bold', fontSize: 10 }}
                                    title="Collegato a un movimento reale in estratto conto"
                                  >
                                    ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã¢â‚¬Å“ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ Pagato
                                  </span>
                                ) : (
                                  <span
                                    style={{ color: '#b45309', fontWeight: 'bold', fontSize: 10 }}
                                    title="Il fornitore ha un metodo di pagamento bancario configurato, ma nessun movimento corrispondente ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¨ stato trovato in estratto conto ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â il pagamento non ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¨ verificato"
                                  >
                                    ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã¢â‚¬Å“ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ Pagato (presunto)
                                  </span>
                                )
                              ) : (
                                <span style={{ color: '#dc2626', fontSize: 10 }}>Da pagare</span>
                              )}
                              {cat.key === 'verbali' && s.ha_ricevuta && (
                                <div style={{ color: '#2563eb', fontSize: 9, marginTop: 2 }}>
                                  ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒâ€¦Ã‚Â½ bollettino
                                </div>
                              )}
                              {cat.key === 'verbali' && s.fonte === 'posta+fattura' && (
                                <div style={{ color: '#9ca3af', fontSize: 9, marginTop: 2 }}>
                                  posta + fattura
                                </div>
                              )}
                            </td>
                            <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                              {s.fattura_id ? (
                              <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                                  <button
                                    onClick={e => {
                                      e.stopPropagation();
                                      setFatturaView({
                                        id: s.fattura_id,
                                        numero: s.numero_fattura || s.numero || s.descrizione,
                                      });
                                    }}
                                    style={{
                                      padding: '4px 8px',
                                      background: '#dbeafe',
                                      color: '#2563eb',
                                      border: 'none',
                                      borderRadius: 4,
                                      cursor: 'pointer',
                                      fontSize: 11,
                                    }}
                                  >
                                    Vedi fattura
                                  </button>
                                  {cat.key === 'verbali' && s.numero_verbale && (
                                    <button
                                      onClick={e => {
                                        e.stopPropagation();
                                        // Apri modale dettaglio verbale
                                        window.open(
                                          `/verbali-noleggio/${s.numero_verbale}`,
                                          '_blank'
                                        );
                                      }}
                                      style={{
                                        padding: '4px 8px',
                                        background: '#fef3c7',
                                        color: '#92400e',
                                        borderRadius: 4,
                                        border: 'none',
                                        cursor: 'pointer',
                                        fontSize: 11,
                                      }}
                                    >
                                      ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â PDF
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
                        <tr
                          style={{ background: `${cat.color}10`, borderTop: '2px solid #e5e7eb' }}
                        >
                          <td
                            colSpan={cat.key === 'verbali' ? 4 : 3}
                            style={{ padding: '8px 10px', textAlign: 'right', fontWeight: '600' }}
                          >
                            Totale {cat.label}:
                          </td>
                          <td
                            style={{
                              padding: '8px 10px',
                              textAlign: 'right',
                              fontWeight: 'bold',
                              fontSize: 12,
                            }}
                          >
                            {formatEuro(spese.reduce((a, s) => a + (s.imponibile || 0), 0))}
                          </td>
                          <td
                            style={{
                              padding: '8px 10px',
                              textAlign: 'right',
                              fontWeight: 'bold',
                              fontSize: 12,
                            }}
                          >
                            {formatEuro(spese.reduce((a, s) => a + (s.iva || 0), 0))}
                          </td>
                          <td
                            style={{
                              padding: '8px 10px',
                              textAlign: 'right',
                              fontWeight: 'bold',
                              color: cat.color,
                              fontSize: 12,
                            }}
                          >
                            {formatEuro(totaleSezione)}
                          </td>
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
      <div
        style={{
          background: COLORS.card,
          borderRadius: BORDER_RADIUS.md,
          boxShadow: SHADOWS.sm,
          border: `1px solid ${COLORS.border}`,
          overflow: 'hidden',
        }}
      >
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb' }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸Ãƒâ€¦Ã‚Â¡ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Elenco Veicoli ({veicoli.length})</h2>
        </div>

        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
            ÃƒÆ’Ã‚Â¢Ãƒâ€šÃ‚ÂÃƒâ€šÃ‚Â³ Caricamento...
          </div>
        ) : veicoli.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸Ãƒâ€¦Ã‚Â¡ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â</div>
            <div style={{ color: '#6b7280' }}>Nessun veicolo trovato per {annoFiltro}</div>
            <div style={{ color: '#9ca3af', fontSize: 14, marginTop: 8 }}>
              I veicoli vengono rilevati automaticamente dalle fatture dei fornitori di noleggio
            </div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table
              style={{ width: '100%', borderCollapse: 'collapse' }}
              data-testid="noleggio-table"
            >
              <thead>
                <tr style={{ background: '#f9fafb', borderBottom: '2px solid #e5e7eb' }}>
                  <th
                    style={{
                      padding: '12px 10px',
                      textAlign: 'left',
                      fontWeight: '600',
                      fontSize: 12,
                    }}
                  >
                    Targa
                  </th>
                  <th
                    style={{
                      padding: '12px 10px',
                      textAlign: 'left',
                      fontWeight: '600',
                      fontSize: 12,
                    }}
                  >
                    Veicolo
                  </th>
                  <th
                    style={{
                      padding: '12px 10px',
                      textAlign: 'left',
                      fontWeight: '600',
                      fontSize: 12,
                    }}
                  >
                    Fornitore
                  </th>
                  <th
                    style={{
                      padding: '12px 10px',
                      textAlign: 'left',
                      fontWeight: '600',
                      fontSize: 12,
                    }}
                  >
                    Contratto
                  </th>
                  <th
                    style={{
                      padding: '12px 10px',
                      textAlign: 'left',
                      fontWeight: '600',
                      fontSize: 12,
                    }}
                  >
                    Driver
                  </th>
                  <th
                    style={{
                      padding: '12px 10px',
                      textAlign: 'right',
                      fontWeight: '600',
                      fontSize: 12,
                    }}
                  >
                    ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¹ Canoni
                  </th>
                  <th
                    style={{
                      padding: '12px 10px',
                      textAlign: 'right',
                      fontWeight: '600',
                      fontSize: 12,
                    }}
                  >
                    ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â Verbali
                  </th>
                  <th
                    style={{
                      padding: '12px 10px',
                      textAlign: 'right',
                      fontWeight: '600',
                      fontSize: 12,
                    }}
                  >
                    ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾ Bollo
                  </th>
                  <th
                    style={{
                      padding: '12px 10px',
                      textAlign: 'right',
                      fontWeight: '600',
                      fontSize: 12,
                    }}
                  >
                    ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒâ€šÃ‚Â§ Ripar.
                  </th>
                  <th
                    style={{
                      padding: '12px 10px',
                      textAlign: 'right',
                      fontWeight: '600',
                      fontSize: 12,
                    }}
                  >
                    TOTALE
                  </th>
                  <th
                    style={{
                      padding: '12px 10px',
                      textAlign: 'center',
                      fontWeight: '600',
                      fontSize: 12,
                    }}
                  >
                    Azioni
                  </th>
                </tr>
              </thead>
              <tbody>
                {veicoli.map((v, i) => (
                  <tr
                    key={v.targa || i}
                    style={{
                      borderBottom: '1px solid #f3f4f6',
                      background: selectedVeicolo?.targa === v.targa ? '#dbeafe' : 'white',
                      cursor: 'pointer',
                    }}
                    onClick={() => setSelectedVeicolo(v)}
                    data-testid={`veicolo-row-${v.targa}`}
                  >
                    <td
                      style={{
                        padding: '10px',
                        fontWeight: '600',
                        fontFamily: 'monospace',
                        color: '#2563eb',
                        fontSize: 13,
                      }}
                    >
                      {v.targa}
                    </td>
                    <td style={{ padding: '10px' }}>
                      <div style={{ fontWeight: '500', fontSize: 12 }}>
                        {v.marca} {(v.modello || '-').slice(0, 25)}
                      </div>
                    </td>
                    <td style={{ padding: '10px', fontSize: 12 }}>
                      {v.fornitore_noleggio?.split(' ')[0] || '-'}
                    </td>
                    <td
                      style={{
                        padding: '10px',
                        fontSize: 11,
                        fontFamily: 'monospace',
                        color: '#6b7280',
                      }}
                    >
                      {v.contratto || v.codice_cliente || '-'}
                    </td>
                    <td
                      style={{
                        padding: '10px',
                        fontSize: 12,
                        color: v.driver ? 'inherit' : '#9ca3af',
                      }}
                    >
                      {v.driver || '-'}
                    </td>
                    <td
                      style={{
                        padding: '10px',
                        textAlign: 'right',
                        color: '#4caf50',
                        fontSize: 12,
                      }}
                    >
                      {formatEuro(v.totale_canoni)}
                    </td>
                    <td
                      style={{
                        padding: '10px',
                        textAlign: 'right',
                        color: '#f44336',
                        fontSize: 12,
                      }}
                    >
                      {formatEuro(v.totale_verbali)}
                    </td>
                    <td
                      style={{
                        padding: '10px',
                        textAlign: 'right',
                        color: '#9c27b0',
                        fontSize: 12,
                      }}
                    >
                      {formatEuro(v.totale_bollo)}
                    </td>
                    <td
                      style={{
                        padding: '10px',
                        textAlign: 'right',
                        color: '#795548',
                        fontSize: 12,
                      }}
                    >
                      {formatEuro(v.totale_riparazioni)}
                    </td>
                    <td
                      style={{
                        padding: '10px',
                        textAlign: 'right',
                        fontWeight: 'bold',
                        color: '#1e3a5f',
                        fontSize: 13,
                      }}
                    >
                      {formatEuro(v.totale_generale)}
                    </td>
                    <td style={{ padding: '10px', textAlign: 'center' }}>
                      <button
                        onClick={e => {
                          e.stopPropagation();
                          setSelectedVeicolo(v);
                        }}
                        style={{
                          padding: '4px 8px',
                          background: '#dbeafe',
                          color: '#2563eb',
                          border: 'none',
                          borderRadius: 4,
                          cursor: 'pointer',
                          marginRight: 2,
                          fontSize: 12,
                        }}
                        title="Vedi dettaglio"
                      >
                        ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã‹Å“Ãƒâ€šÃ‚ÂÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â
                      </button>
                      <button
                        onClick={e => {
                          e.stopPropagation();
                          setEditingVeicolo({ ...v });
                        }}
                        style={{
                          padding: '4px 8px',
                          background: '#f3f4f6',
                          color: '#374151',
                          border: 'none',
                          borderRadius: 4,
                          cursor: 'pointer',
                          fontSize: 12,
                        }}
                        title="Modifica"
                      >
                        ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã¢â‚¬Å“Ãƒâ€šÃ‚ÂÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â
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
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setEditingVeicolo(null)}
        >
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              padding: 24,
              width: '100%',
              maxWidth: 550,
              maxHeight: '90vh',
              overflowY: 'auto',
            }}
            onClick={e => e.stopPropagation()}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 20,
              }}
            >
              <h2 style={{ margin: 0, fontSize: 18 }}>ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã¢â‚¬Å“Ãƒâ€šÃ‚ÂÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â Modifica {editingVeicolo.targa}</h2>
              <button
                onClick={() => setEditingVeicolo(null)}
                style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer' }}
              >
                ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã¢â‚¬Å“ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¢
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Sezione OpenAPI Automotive */}
              <div
                style={{
                  padding: 12,
                  background: '#f0fdf4',
                  borderRadius: 8,
                  border: '1px solid #86efac',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 8,
                  }}
                >
                  <span style={{ fontWeight: '600', color: '#166534', fontSize: 13 }}>
                    ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸Ãƒâ€¦Ã‚Â¡ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Dati da OpenAPI Automotive
                  </span>
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
                      fontWeight: '600',
                    }}
                  >
                    {lookupLoading ? 'ÃƒÆ’Ã‚Â¢Ãƒâ€šÃ‚ÂÃƒâ€šÃ‚Â³ Cercando...' : 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒâ€šÃ‚Â Cerca Dati'}
                  </button>
                </div>

                {lookupResult && !lookupResult.error && (
                  <div style={{ fontSize: 12, marginTop: 8 }}>
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                        gap: 6,
                      }}
                    >
                      <div>
                        <strong>Marca:</strong> {lookupResult.campi_mappati?.marca || '-'}
                      </div>
                      <div>
                        <strong>Modello:</strong> {lookupResult.campi_mappati?.modello || '-'}
                      </div>
                      <div>
                        <strong>Anno:</strong>{' '}
                        {lookupResult.campi_mappati?.anno_immatricolazione || '-'}
                      </div>
                      <div>
                        <strong>Alimentazione:</strong>{' '}
                        {lookupResult.campi_mappati?.alimentazione || '-'}
                      </div>
                      <div>
                        <strong>Potenza:</strong>{' '}
                        {lookupResult.campi_mappati?.potenza_kw
                          ? `${lookupResult.campi_mappati.potenza_kw} kW`
                          : '-'}
                      </div>
                      <div>
                        <strong>Cilindrata:</strong>{' '}
                        {lookupResult.campi_mappati?.cilindrata
                          ? `${lookupResult.campi_mappati.cilindrata} cc`
                          : '-'}
                      </div>
                    </div>
                    <button
                      onClick={() => {
                        // Applica i dati trovati
                        setEditingVeicolo(prev => ({
                          ...prev,
                          marca: lookupResult.campi_mappati?.marca || prev.marca,
                          modello: lookupResult.campi_mappati?.modello || prev.modello,
                          anno_immatricolazione:
                            lookupResult.campi_mappati?.anno_immatricolazione ||
                            prev.anno_immatricolazione,
                          alimentazione:
                            lookupResult.campi_mappati?.alimentazione || prev.alimentazione,
                          potenza_kw: lookupResult.campi_mappati?.potenza_kw || prev.potenza_kw,
                          cilindrata: lookupResult.campi_mappati?.cilindrata || prev.cilindrata,
                        }));
                        setLookupResult(null);
                        toast.success('Dati applicati!');
                      }}
                      style={{
                        marginTop: 10,
                        padding: '8px 16px',
                        background: '#2563eb',
                        color: 'white',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'pointer',
                        fontWeight: '600',
                        width: '100%',
                      }}
                    >
                      ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã¢â‚¬Å“ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ Applica questi dati
                    </button>
                  </div>
                )}

                {lookupResult?.error && (
                  <div style={{ fontSize: 12, color: '#dc2626', marginTop: 8 }}>
                    ÃƒÆ’Ã‚Â¢Ãƒâ€šÃ‚ÂÃƒâ€¦Ã¢â‚¬â„¢ {lookupResult.error}
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
                  <label
                    style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                  >
                    Marca
                  </label>
                  <input
                    type="text"
                    value={editingVeicolo.marca || ''}
                    onChange={e => setEditingVeicolo({ ...editingVeicolo, marca: e.target.value })}
                    placeholder="Es: BMW"
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                      fontSize: 13,
                    }}
                  />
                </div>
                <div>
                  <label
                    style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                  >
                    Modello
                  </label>
                  <input
                    type="text"
                    value={editingVeicolo.modello || ''}
                    onChange={e =>
                      setEditingVeicolo({ ...editingVeicolo, modello: e.target.value })
                    }
                    placeholder="Es: X3 xDrive 20d M Sport"
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                      fontSize: 13,
                    }}
                  />
                </div>
              </div>

              {/* Driver */}
              <div>
                <label
                  style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                >
                  Driver (Assegnatario)
                </label>
                {drivers.length > 0 ? (
                  <select
                    value={editingVeicolo.driver_id || ''}
                    onChange={e => {
                      const d = drivers.find(x => x.id === e.target.value);
                      setEditingVeicolo({
                        ...editingVeicolo,
                        driver_id: e.target.value,
                        driver: d?.nome_completo || '',
                      });
                    }}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                      fontSize: 13,
                    }}
                  >
                    <option value="">-- Seleziona Driver --</option>
                    {drivers.map(d => (
                      <option key={d.id} value={d.id}>
                        {d.nome_completo}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    value={editingVeicolo.driver || ''}
                    onChange={e => setEditingVeicolo({ ...editingVeicolo, driver: e.target.value })}
                    placeholder="Nome e Cognome"
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                      fontSize: 13,
                    }}
                  />
                )}
              </div>

              {/* Contratto e Codice Cliente */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                  gap: 12,
                }}
              >
                <div>
                  <label
                    style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                  >
                    NÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â° Contratto
                  </label>
                  <input
                    type="text"
                    value={editingVeicolo.contratto || ''}
                    onChange={e =>
                      setEditingVeicolo({ ...editingVeicolo, contratto: e.target.value })
                    }
                    placeholder="Numero contratto"
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                      fontSize: 13,
                    }}
                  />
                </div>
                <div>
                  <label
                    style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                  >
                    Codice Cliente
                  </label>
                  <input
                    type="text"
                    value={editingVeicolo.codice_cliente || ''}
                    onChange={e =>
                      setEditingVeicolo({ ...editingVeicolo, codice_cliente: e.target.value })
                    }
                    placeholder="Codice cliente fornitore"
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                      fontSize: 13,
                    }}
                  />
                </div>
              </div>

              {/* Canone mensile e specifiche veicolo */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr 1fr' : '1fr 1fr 1fr 1fr',
                  gap: 12,
                }}
              >
                <div>
                  <label
                    style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                  >
                    Canone mensile
                  </label>
                  <input
                    type="number"
                    value={editingVeicolo.canone_mensile ?? ''}
                    onChange={e =>
                      setEditingVeicolo({ ...editingVeicolo, canone_mensile: e.target.value })
                    }
                    placeholder="ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬"
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                      fontSize: 13,
                    }}
                  />
                </div>
                <div>
                  <label
                    style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                  >
                    Anno immatr.
                  </label>
                  <input
                    type="number"
                    value={editingVeicolo.anno_immatricolazione ?? ''}
                    onChange={e =>
                      setEditingVeicolo({
                        ...editingVeicolo,
                        anno_immatricolazione: e.target.value,
                      })
                    }
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                      fontSize: 13,
                    }}
                  />
                </div>
                <div>
                  <label
                    style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                  >
                    Alimentazione
                  </label>
                  <input
                    type="text"
                    value={editingVeicolo.alimentazione || ''}
                    onChange={e =>
                      setEditingVeicolo({ ...editingVeicolo, alimentazione: e.target.value })
                    }
                    placeholder="Diesel, Benzina..."
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                      fontSize: 13,
                    }}
                  />
                </div>
                <div>
                  <label
                    style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                  >
                    Potenza / Cilindrata
                  </label>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <input
                      type="number"
                      value={editingVeicolo.potenza_kw ?? ''}
                      onChange={e =>
                        setEditingVeicolo({ ...editingVeicolo, potenza_kw: e.target.value })
                      }
                      placeholder="kW"
                      style={{
                        width: '100%',
                        padding: '8px 10px',
                        border: '1px solid #e5e7eb',
                        borderRadius: 6,
                        fontSize: 13,
                      }}
                    />
                    <input
                      type="number"
                      value={editingVeicolo.cilindrata ?? ''}
                      onChange={e =>
                        setEditingVeicolo({ ...editingVeicolo, cilindrata: e.target.value })
                      }
                      placeholder="cc"
                      style={{
                        width: '100%',
                        padding: '8px 10px',
                        border: '1px solid #e5e7eb',
                        borderRadius: 6,
                        fontSize: 13,
                      }}
                    />
                  </div>
                </div>
              </div>

              {/* Centro Fatturazione */}
              <div>
                <label
                  style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                >
                  Centro Fatturazione
                </label>
                <input
                  type="text"
                  value={editingVeicolo.centro_fatturazione || ''}
                  onChange={e =>
                    setEditingVeicolo({ ...editingVeicolo, centro_fatturazione: e.target.value })
                  }
                  placeholder="Centro di fatturazione (es: K26858)"
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    border: '1px solid #e5e7eb',
                    borderRadius: 6,
                    fontSize: 13,
                  }}
                />
              </div>

              {/* Date Noleggio */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                  gap: 12,
                }}
              >
                <div>
                  <label
                    style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                  >
                    Inizio Noleggio
                  </label>
                  <input
                    type="date"
                    value={editingVeicolo.data_inizio || ''}
                    onChange={e =>
                      setEditingVeicolo({ ...editingVeicolo, data_inizio: e.target.value })
                    }
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                      fontSize: 13,
                    }}
                  />
                </div>
                <div>
                  <label
                    style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                  >
                    Fine Noleggio
                  </label>
                  <input
                    type="date"
                    value={editingVeicolo.data_fine || ''}
                    onChange={e =>
                      setEditingVeicolo({ ...editingVeicolo, data_fine: e.target.value })
                    }
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                      fontSize: 13,
                    }}
                  />
                </div>
              </div>

              {/* Note */}
              <div>
                <label
                  style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                >
                  Note
                </label>
                <input
                  type="text"
                  value={editingVeicolo.note || ''}
                  onChange={e => setEditingVeicolo({ ...editingVeicolo, note: e.target.value })}
                  placeholder="Note aggiuntive"
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    border: '1px solid #e5e7eb',
                    borderRadius: 6,
                    fontSize: 13,
                  }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 20 }}>
              <button
                onClick={() => {
                  handleDelete(editingVeicolo.targa);
                  setEditingVeicolo(null);
                }}
                style={{
                  padding: '10px 16px',
                  background: '#fee2e2',
                  color: '#dc2626',
                  border: 'none',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontWeight: '600',
                }}
              >
                ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬ÂÃƒÂ¢Ã¢â€šÂ¬Ã‹Å“ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â Elimina
              </button>
              <div style={{ display: 'flex', gap: 10 }}>
                <button
                  onClick={() => setEditingVeicolo(null)}
                  style={{
                    padding: '10px 16px',
                    background: '#f3f4f6',
                    color: '#374151',
                    border: 'none',
                    borderRadius: 8,
                    cursor: 'pointer',
                    fontWeight: '600',
                  }}
                >
                  Annulla
                </button>
                <button
                  onClick={handleSaveVeicolo}
                  style={{
                    padding: '10px 16px',
                    background: '#2563eb',
                    color: 'white',
                    border: 'none',
                    borderRadius: 8,
                    cursor: 'pointer',
                    fontWeight: '600',
                  }}
                >
                  ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢Ãƒâ€šÃ‚Â¾ Salva
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal Aggiungi Veicolo (per LeasePlan o altri senza targa in fattura) */}
      {showAddVeicolo && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setShowAddVeicolo(false)}
        >
          <div
            style={{
              background: 'white',
              borderRadius: 12,
              padding: 24,
              width: '100%',
              maxWidth: 500,
            }}
            onClick={e => e.stopPropagation()}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 20,
              }}
            >
              <h2 style={{ margin: 0, fontSize: 18 }}>ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¾ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¢ Aggiungi Veicolo</h2>
              <button
                onClick={() => setShowAddVeicolo(false)}
                style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer' }}
              >
                ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã¢â‚¬Å“ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¢
              </button>
            </div>

            <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>
              Usa questo form per aggiungere veicoli di fornitori che non includono la targa nelle
              fatture (es: LeasePlan).
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <label
                  style={{ display: 'block', fontSize: 13, fontWeight: '500', marginBottom: 4 }}
                >
                  Targa *
                </label>
                <input
                  type="text"
                  value={nuovoVeicolo.targa}
                  onChange={e =>
                    setNuovoVeicolo({ ...nuovoVeicolo, targa: e.target.value.toUpperCase() })
                  }
                  placeholder="Es: AB123CD"
                  maxLength={7}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    border: '1px solid #e5e7eb',
                    borderRadius: 6,
                    fontSize: 14,
                    fontFamily: 'monospace',
                  }}
                />
              </div>

              <div>
                <label
                  style={{ display: 'block', fontSize: 13, fontWeight: '500', marginBottom: 4 }}
                >
                  Fornitore *
                </label>
                <select
                  value={nuovoVeicolo.fornitore_piva}
                  onChange={e =>
                    setNuovoVeicolo({ ...nuovoVeicolo, fornitore_piva: e.target.value })
                  }
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    border: '1px solid #e5e7eb',
                    borderRadius: 6,
                    fontSize: 14,
                  }}
                >
                  <option value="">-- Seleziona Fornitore --</option>
                  {fornitori.map(f => (
                    <option key={f.piva} value={f.piva}>
                      {f.nome} {!f.targa_in_fattura ? 'ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¯Ãƒâ€šÃ‚Â¸Ãƒâ€šÃ‚Â' : ''}
                    </option>
                  ))}
                </select>
              </div>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                  gap: 12,
                }}
              >
                <div>
                  <label
                    style={{ display: 'block', fontSize: 13, fontWeight: '500', marginBottom: 4 }}
                  >
                    Marca
                  </label>
                  <input
                    type="text"
                    value={nuovoVeicolo.marca}
                    onChange={e => setNuovoVeicolo({ ...nuovoVeicolo, marca: e.target.value })}
                    placeholder="Es: BMW"
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                      fontSize: 14,
                    }}
                  />
                </div>
                <div>
                  <label
                    style={{ display: 'block', fontSize: 13, fontWeight: '500', marginBottom: 4 }}
                  >
                    Modello
                  </label>
                  <input
                    type="text"
                    value={nuovoVeicolo.modello}
                    onChange={e => setNuovoVeicolo({ ...nuovoVeicolo, modello: e.target.value })}
                    placeholder="Es: X3 xDrive"
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                      fontSize: 14,
                    }}
                  />
                </div>
              </div>

              <div>
                <label
                  style={{ display: 'block', fontSize: 13, fontWeight: '500', marginBottom: 4 }}
                >
                  Numero Contratto
                </label>
                <input
                  type="text"
                  value={nuovoVeicolo.contratto}
                  onChange={e => setNuovoVeicolo({ ...nuovoVeicolo, contratto: e.target.value })}
                  placeholder="Numero contratto noleggio"
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    border: '1px solid #e5e7eb',
                    borderRadius: 6,
                    fontSize: 14,
                  }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 24 }}>
              <button
                onClick={() => setShowAddVeicolo(false)}
                style={{
                  padding: '10px 16px',
                  background: '#f3f4f6',
                  color: '#374151',
                  border: 'none',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontWeight: '600',
                }}
              >
                Annulla
              </button>
              <button
                onClick={handleAddVeicolo}
                style={{
                  padding: '10px 16px',
                  background: '#2563eb',
                  color: 'white',
                  border: 'none',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontWeight: '600',
                }}
              >
                ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¾ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¢ Aggiungi
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Fatture Non Associate ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â sostituisce il vecchio alert() nativo
          (illeggibile, senza scroll utile, testo non selezionabile) */}
      {modalFattureNonAssociate.open && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setModalFattureNonAssociate(m => ({ ...m, open: false }))}
        >
          <div
            style={{
              background: COLORS.card,
              borderRadius: BORDER_RADIUS.lg,
              padding: 24,
              width: '100%',
              maxWidth: 640,
              maxHeight: '80vh',
              display: 'flex',
              flexDirection: 'column',
            }}
            onClick={e => e.stopPropagation()}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <h2 style={{ margin: 0, fontSize: 18, color: COLORS.primary }}>
                ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¹ Fatture Non Associate ({modalFattureNonAssociate.fatture.length})
              </h2>
              <button
                onClick={() => setModalFattureNonAssociate(m => ({ ...m, open: false }))}
                style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer' }}
              >
                ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã¢â‚¬Å“ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¢
              </button>
            </div>
            <p style={{ fontSize: 13, color: COLORS.textMuted, marginBottom: 16 }}>
              Il sistema non ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¨ riuscito a estrarre la targa da queste fatture: vanno associate
              manualmente a un veicolo (bottone "ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¾ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¢ Aggiungi Veicolo").
            </p>

            {modalFattureNonAssociate.loading && (
              <div style={{ padding: 24, textAlign: 'center', color: COLORS.textMuted }}>
                Caricamento...
              </div>
            )}

            {modalFattureNonAssociate.errore && (
              <div
                style={{
                  padding: 16,
                  background: COLORS.dangerLight,
                  color: COLORS.danger,
                  borderRadius: BORDER_RADIUS.sm,
                }}
              >
                Errore: {modalFattureNonAssociate.errore}
              </div>
            )}

            {!modalFattureNonAssociate.loading &&
              !modalFattureNonAssociate.errore &&
              modalFattureNonAssociate.fatture.length === 0 && (
                <div style={{ padding: 24, textAlign: 'center', color: COLORS.textMuted }}>
                  ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã¢â‚¬Å“ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦ Nessuna fattura non associata
                </div>
              )}

            {!modalFattureNonAssociate.loading && modalFattureNonAssociate.fatture.length > 0 && (
              <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
                {modalFattureNonAssociate.fatture.map((f, i) => (
                  <div
                    key={f.id || i}
                    style={{
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.sm,
                      padding: 12,
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      gap: 12,
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13, color: COLORS.text }}>
                        {f.fornitore || 'N/D'} ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â Fatt. {f.numero || 'N/D'} del {f.data || 'N/D'}
                      </div>
                      <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 2 }}>
                        {formatEuro(Number(f.importo || 0))}
                        {f.descrizione ? ` ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· ${f.descrizione}` : ''}
                      </div>
                      {(f.contratto || f.codice_cliente) && (
                        <div style={{ fontSize: 11, color: COLORS.textSubtle, marginTop: 2 }}>
                          {f.contratto ? `Contratto: ${f.contratto}` : ''}
                          {f.contratto && f.codice_cliente ? ' ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· ' : ''}
                          {f.codice_cliente ? `Cod. cliente: ${f.codice_cliente}` : ''}
                        </div>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                      {f.id && (
                        <button
                          onClick={e => {
                            e.stopPropagation();
                            setFatturaView({ id: f.id, numero: f.numero_fattura || f.numero || f.fornitore });
                          }}
                          style={{
                            ...button('outline'),
                            fontSize: 12,
                            padding: '6px 10px',
                            display: 'inline-flex',
                            alignItems: 'center',
                          }}
                        >
                          Vedi
                        </button>
                      )}
                      <button
                        onClick={() => {
                          setNuovoVeicolo(v => ({ ...v, fornitore_piva: f.piva || '' }));
                          setModalFattureNonAssociate(m => ({ ...m, open: false }));
                          setShowAddVeicolo(true);
                        }}
                        style={{ ...button('outline'), fontSize: 12, padding: '6px 10px' }}
                      >
                        ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¾ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¢ Associa
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
      {fatturaView && (
        <ModalFattura
          fatturaId={fatturaView.id}
          numero={fatturaView.numero}
          onClose={() => setFatturaView(null)}
        />
      )}
    </div>
  );
}

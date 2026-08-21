import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';
import {
  formatEuro,
  formatDateIT,
  STYLES,
  COLORS,
  SHADOWS,
  BORDER_RADIUS,
  FONT,
  useIsMobile,
  RG,
  pagePad,
} from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';
import ModalFattura from '../components/ModalFattura';
import AssociaMovimentoBanca from '../components/AssociaMovimentoBanca';
import { toast } from 'sonner';
import { useConfirm } from '../components/ui/ConfirmDialog';
import {
  Button,
  Badge,
  StatCard,
  Input,
  Select,
  TableWrap,
  Table,
  Th,
  Td,
  RowActions,
  RowActionButton,
} from '../components/ds';

export default function NoleggioAuto() {
  const isMobile = useIsMobile();
  const confirm = useConfirm();
  const navigate = useNavigate();
  // Anno unico e globale (barra di navigazione in alto) → nessun selettore
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
  const [modalFattureNonAssociate, setModalFattureNonAssociate] = useState({
    open: false,
    loading: false,
    fatture: [],
    errore: '',
  });
  const [veicoloSceltoPerFattura, setVeicoloSceltoPerFattura] = useState({});
  const [fatturaInAssociazione, setFatturaInAssociazione] = useState(null);
  // Cruscotto "Controlli": conteggi + prime voci di ciò che richiede
  // attenzione (verbali aperti, trattenute, driver mancanti, ...).
  // Se l'API fallisce o è vuota il pannello semplicemente non appare.
  const [controlli, setControlli] = useState(null);
  const [controlloAperto, setControlloAperto] = useState(null);
  const [fatturaPagamento, setFatturaPagamento] = useState(null);
  // Stato per lookup OpenAPI
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupResult, setLookupResult] = useState(null);

  const categorie = [
    { key: 'canoni', label: 'Canoni', icon: '💰', color: '#4caf50' },
    { key: 'pedaggio', label: 'Pedaggio', icon: '🛣️', color: '#2196f3' },
    { key: 'verbali', label: 'Verbali', icon: '📋', color: '#f44336' },
    { key: 'bollo', label: 'Bollo', icon: '🏷️', color: '#9c27b0' },
    { key: 'costi_extra', label: 'Costi Extra', icon: '➕', color: '#ff9800' },
    { key: 'riparazioni', label: 'Riparazioni', icon: '🔧', color: '#795548' },
  ];

  const fetchVeicoli = useCallback(async () => {
    setLoading(true);
    setErr('');
    try {
      // Se annoFiltro è null, carica TUTTI gli anni
      const annoParam = annoFiltro ? `anno=${annoFiltro}` : '';
      const [vRes, dRes, fRes] = await Promise.all([
        api.get(`/api/noleggio/veicoli?${annoParam}`),
        api.get('/api/noleggio/drivers'),
        api.get('/api/noleggio/fornitori'),
      ]);
      setVeicoli(vRes.data.veicoli || []);
      setStatistiche(vRes.data.statistiche || {});
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

  const fetchControlli = useCallback(async () => {
    try {
      const annoParam = annoFiltro ? `?anno=${annoFiltro}` : '';
      const res = await api.get(`/api/noleggio/riepilogo-controlli${annoParam}`);
      setControlli(res.data || null);
    } catch {
      // Degrado silenzioso: senza dati il pannello Controlli non si mostra
      setControlli(null);
    }
  }, [annoFiltro]);

  useEffect(() => {
    fetchControlli();
  }, [fetchControlli]);

  const openFattureNonAssociate = async () => {
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
  };

  const handleAssociaFatturaVeicolo = async fattura => {
    const targa = veicoloSceltoPerFattura[fattura.id];
    if (!fattura.id || !targa) {
      toast.error('Seleziona il veicolo da collegare');
      return;
    }
    setFatturaInAssociazione(fattura.id);
    try {
      await api.post(`/api/noleggio/fatture/${fattura.id}/associa-veicolo`, { targa });
      setModalFattureNonAssociate(current => ({
        ...current,
        fatture: current.fatture.filter(item => item.id !== fattura.id),
      }));
      setVeicoloSceltoPerFattura(current => {
        const next = { ...current };
        delete next[fattura.id];
        return next;
      });
      toast.success(`Fattura associata al veicolo ${targa}`);
      await Promise.all([fetchVeicoli(), fetchControlli()]);
    } catch (e) {
      toast.error('Associazione non riuscita', {
        description: e.response?.data?.detail || e.message,
      });
    } finally {
      setFatturaInAssociazione(null);
    }
  };

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
  const formatDate = dateStr => {
    if (!dateStr) return '-';
    try {
      return formatDateIT(dateStr);
    } catch {
      return dateStr;
    }
  };

  // Chip del pannello Controlli: solo colori del design system.
  // "Verbali aperti" naviga al tab Verbali (sezione già esistente),
  // "Fatture da associare" apre il modal già presente in pagina,
  // gli altri espandono una piccola lista sotto i chip.
  const controlliChips = [
    {
      key: 'verbali_aperti',
      label: 'Verbali aperti',
      color: COLORS.danger,
      bg: COLORS.dangerLight,
      onClick: () => navigate('/noleggio/verbali'),
    },
    {
      key: 'trattenute_da_confermare',
      label: 'Trattenute da confermare',
      color: COLORS.warning,
      bg: COLORS.warningLight,
    },
    {
      key: 'auto_senza_driver',
      label: 'Auto senza driver',
      color: COLORS.info,
      bg: COLORS.infoLight,
    },
    {
      key: 'fatture_non_associate',
      label: 'Fatture da associare',
      color: COLORS.warning,
      bg: COLORS.warningLight,
      onClick: openFattureNonAssociate,
    },
    {
      key: 'pagamenti_non_riconciliati',
      label: 'Pagamenti noleggio da verificare',
      color: COLORS.danger,
      bg: COLORS.dangerLight,
    },
    {
      key: 'alert_aperti',
      label: 'Avvisi',
      color: COLORS.primary,
      bg: COLORS.primarySoft,
    },
  ];
  const totaleControlli = controlliChips.reduce(
    (acc, c) => acc + (controlli?.[c.key]?.count || 0),
    0
  );

  const descriviVoceControllo = (key, item) => {
    switch (key) {
      case 'trattenute_da_confermare':
        return `${item?.dipendente_nome || 'Dipendente N/D'} • ${formatEuro(Number(item?.importo || 0))}${
          item?.numero_verbale ? ` • Verbale ${item.numero_verbale}` : ''
        }${item?.targa ? ` • ${item.targa}` : ''}`;
      case 'auto_senza_driver':
        return `${item?.targa || '-'} • ${
          [item?.marca, item?.modello].filter(Boolean).join(' ') || 'Modello N/D'
        }${item?.fornitore_noleggio ? ` • ${item.fornitore_noleggio.split(' ')[0]}` : ''}`;
      case 'pagamenti_non_riconciliati':
        return `${item?.supplier_name || 'Fornitore N/D'} • Fatt. ${item?.invoice_number || 'N/D'} del ${formatDate(
          item?.invoice_date
        )} • ${formatEuro(Number(item?.total_amount || 0))}`;
      case 'alert_aperti':
        return `${item?.titolo || item?.codice || 'Avviso'}${item?.dettaglio ? ` — ${item.dettaglio}` : ''}`;
      case 'verbali_aperti':
        return `Verbale ${item?.numero_verbale || 'N/D'} • ${item?.targa || '-'} • ${formatDate(
          item?.data_verbale
        )} • ${formatEuro(Number(item?.importo || 0))}`;
      default:
        return '';
    }
  };

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto' }}>
      {/* Header — stile uniforme al resto delle pagine (STYLES.header) */}
      <div style={STYLES.header}>
        <div>
          <h1 style={STYLES.pageTitle}>🚗 Gestione Noleggio Auto</h1>
          <p style={{ ...STYLES.pageSubtitle, marginTop: 4 }}>
            Flotta aziendale • Dati estratti da fatture XML
          </p>
        </div>
      </div>

      {/* Pannello Controlli — cruscotto "cosa richiede attenzione".
          Compare solo se c'è almeno una segnalazione; API in errore o
          vuota → nessun render (optional chaining ovunque). */}
      {totaleControlli > 0 && (
        <div
          style={{
            background: COLORS.card,
            border: `1px solid ${COLORS.border}`,
            borderLeft: `4px solid ${COLORS.primary}`,
            borderRadius: BORDER_RADIUS.md,
            boxShadow: SHADOWS.sm,
            padding: '12px 16px',
            marginBottom: 20,
          }}
          data-testid="noleggio-controlli"
        >
          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: COLORS.primary,
              marginBottom: 8,
            }}
          >
            🔎 Controlli — {totaleControlli} da verificare
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {controlliChips.map(chip => {
              const count = controlli?.[chip.key]?.count || 0;
              if (count <= 0) return null;
              const attivo = controlloAperto === chip.key;
              return (
                <button
                  key={chip.key}
                  onClick={() =>
                    chip.onClick
                      ? chip.onClick()
                      : setControlloAperto(attivo ? null : chip.key)
                  }
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '6px 12px',
                    borderRadius: 999,
                    border: `1px solid ${chip.color}`,
                    background: attivo ? chip.color : chip.bg,
                    color: attivo ? '#fff' : chip.color,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                    fontFamily: FONT.family,
                  }}
                  data-testid={`controllo-chip-${chip.key}`}
                >
                  {chip.label}
                  <span
                    style={{
                      background: attivo ? 'rgba(255,255,255,0.25)' : chip.color,
                      color: '#fff',
                      borderRadius: 999,
                      padding: '1px 7px',
                      fontSize: 11,
                      fontWeight: 700,
                    }}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
          {controlloAperto && (controlli?.[controlloAperto]?.items || []).length > 0 && (
            <div
              style={{
                marginTop: 10,
                borderTop: `1px solid ${COLORS.border}`,
                paddingTop: 8,
              }}
            >
              {controlloAperto === 'pagamenti_non_riconciliati' && (
                <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 8 }}>
                  Scegli una fattura: vedrai gli addebiti reali trovati nell’estratto conto e
                  le prove che coincidono. La conferma resta sempre manuale.
                </div>
              )}
              {(controlli?.[controlloAperto]?.items || []).map((item, i) => (
                <div
                  key={item?.id || i}
                  style={{
                    fontSize: 12,
                    color: COLORS.text,
                    padding: '4px 0',
                    borderBottom: `1px solid ${COLORS.gray[100]}`,
                  }}
                >
                  <span>{descriviVoceControllo(controlloAperto, item)}</span>
                  {controlloAperto === 'pagamenti_non_riconciliati' && item?.id && (
                    <button
                      type="button"
                      onClick={() => setFatturaPagamento({
                        fattura_id: item.id,
                        fattura_numero: item.invoice_number,
                        fornitore: item.supplier_name,
                        importo: item.total_amount,
                      })}
                      style={{
                        marginLeft: 10, padding: '5px 9px', borderRadius: 7,
                        border: `1px solid ${COLORS.primary}`, background: '#fff',
                        color: COLORS.primary, fontWeight: 700, cursor: 'pointer',
                      }}
                    >
                      Verifica pagamento
                    </button>
                  )}
                </div>
              ))}
              {(controlli?.[controlloAperto]?.count || 0) >
                (controlli?.[controlloAperto]?.items || []).length && (
                <div style={{ fontSize: 11, color: COLORS.textSubtle, marginTop: 6 }}>
                  … e altre{' '}
                  {(controlli?.[controlloAperto]?.count || 0) -
                    (controlli?.[controlloAperto]?.items || []).length}{' '}
                  voci
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {fatturaPagamento && (
        <AssociaMovimentoBanca
          fattura={fatturaPagamento}
          onChiudi={() => setFatturaPagamento(null)}
          onAssociato={async () => {
            setFatturaPagamento(null);
            await Promise.all([fetchVeicoli(), fetchControlli()]);
          }}
        />
      )}

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
        <Button
          onClick={fetchVeicoli}
          variant="secondary"
          data-testid="noleggio-refresh-btn"
        >
          🔄 Aggiorna
        </Button>
        <span style={{ fontSize: 13, color: COLORS.textMuted }}>
          I veicoli vengono compilati automaticamente dalle fatture di noleggio.
        </span>
      </div>

      {err && (
        <div
          style={{
            padding: 12,
            background: COLORS.dangerLight,
            border: `1px solid ${COLORS.dangerLight}`,
            borderRadius: BORDER_RADIUS.md,
            color: COLORS.danger,
            marginBottom: 20,
          }}
          data-testid="noleggio-error"
        >
          ❌ {err}
        </div>
      )}

      {/* Riepilogo Totali - Se veicolo selezionato mostra i suoi dati, altrimenti totale generale */}
      {veicoli.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          {selectedVeicolo && (
            <div
              style={{
                padding: '8px 16px',
                background: COLORS.infoLight,
                borderRadius: `${BORDER_RADIUS.md}px ${BORDER_RADIUS.md}px 0 0`,
                color: COLORS.info,
                fontWeight: 'bold',
                fontSize: 14,
              }}
            >
              📊 Riepilogo: {selectedVeicolo.marca} {selectedVeicolo.modello || ''} -{' '}
              {selectedVeicolo.targa}
            </div>
          )}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
              gap: 16,
              padding: selectedVeicolo ? '16px' : 0,
              background: selectedVeicolo ? COLORS.bgAlt : 'transparent',
              borderRadius: selectedVeicolo ? `0 0 ${BORDER_RADIUS.md}px ${BORDER_RADIUS.md}px` : 0,
            }}
          >
            {categorie.map(cat => {
              // Se c'è un veicolo selezionato, mostra i suoi totali, altrimenti il totale generale
              const valore = selectedVeicolo
                ? selectedVeicolo[`totale_${cat.key}`] ||
                  (selectedVeicolo[cat.key] || []).reduce((a, s) => a + (s.totale || 0), 0)
                : statistiche[`totale_${cat.key}`] || 0;

              return (
                <StatCard
                  key={cat.key}
                  accent="none"
                  style={{ padding: '10px 12px', borderLeft: `3px solid ${cat.color}` }}
                  label={<span style={{ color: COLORS.textMuted }}>{cat.icon} {cat.label}</span>}
                  value={<span style={{ fontSize: 16, color: cat.color }}>{formatEuro(valore)}</span>}
                />
              );
            })}
            <div
              style={{
                background: COLORS.primary,
                borderRadius: BORDER_RADIUS.md,
                padding: '10px 12px',
                boxShadow: SHADOWS.sm,
                color: 'white',
              }}
            >
              <div style={{ fontSize: 11, opacity: 0.9, marginBottom: 4 }}>💰 TOTALE</div>
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
              🚗 {selectedVeicolo.marca} {selectedVeicolo.modello || 'Modello da definire'} -{' '}
              <span style={{ color: COLORS.info, fontFamily: 'monospace' }}>
                {selectedVeicolo.targa}
              </span>
            </h2>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button
                onClick={() => handleUpdateFromOpenAPI(selectedVeicolo.targa)}
                disabled={lookupLoading}
                variant="success"
                size="sm"
                title="Aggiorna dati veicolo da OpenAPI Automotive"
                data-testid="veicolo-update-openapi-btn"
              >
                {lookupLoading ? '⏳' : '🔍'} Aggiorna da Targa
              </Button>
              <Button
                onClick={() => setEditingVeicolo({ ...selectedVeicolo })}
                variant="info"
                size="sm"
              >
                ✏️ Modifica
              </Button>
              <Button
                onClick={() => handleDelete(selectedVeicolo.targa)}
                variant="danger"
                size="sm"
              >
                🗑️ Elimina
              </Button>
              <Button
                onClick={() => setSelectedVeicolo(null)}
                variant="ghost"
                style={{ fontSize: 20, border: 'none', padding: 0 }}
              >
                ✕
              </Button>
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
              <h3 style={{ margin: '0 0 8px 0', fontSize: 14, color: COLORS.textMuted }}>Veicolo</h3>
              <div style={{ fontSize: 13, lineHeight: 1.8 }}>
                <div>
                  Targa: <strong>{selectedVeicolo.targa}</strong>
                </div>
                <div>Fornitore: {selectedVeicolo.fornitore_noleggio || '-'}</div>
                <div>
                  P.IVA:{' '}
                  <span style={{ fontFamily: 'monospace', color: COLORS.textMuted }}>
                    {selectedVeicolo.fornitore_piva || '-'}
                  </span>
                </div>
                <div>
                  {selectedVeicolo.alimentazione || '-'}
                  {selectedVeicolo.potenza_kw ? ` • ${selectedVeicolo.potenza_kw} kW` : ''}
                  {selectedVeicolo.potenza_cv ? ` • ${selectedVeicolo.potenza_cv} CV` : ''}
                  {selectedVeicolo.cilindrata ? ` • ${selectedVeicolo.cilindrata} cc` : ''}
                </div>
                {selectedVeicolo.telaio && (
                  <div style={{ fontSize: 12, color: COLORS.textSubtle }}>
                    Telaio: <span style={{ fontFamily: 'monospace' }}>{selectedVeicolo.telaio}</span>
                  </div>
                )}
              </div>
            </div>
            <div>
              <h3 style={{ margin: '0 0 8px 0', fontSize: 14, color: COLORS.textMuted }}>Contratto</h3>
              <div style={{ fontSize: 13, lineHeight: 1.8 }}>
                <div>
                  N° Contratto: <strong>{selectedVeicolo.contratto || '-'}</strong>
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
                      style={{ color: COLORS.textSubtle, fontSize: 11, marginLeft: 4 }}
                      title="Stimato dall'ultimo canone fatturato, non configurato manualmente"
                    >
                      (stimato)
                    </span>
                  )}
                </div>
              </div>
            </div>
            <div>
              <h3 style={{ margin: '0 0 8px 0', fontSize: 14, color: COLORS.textMuted }}>Assegnazione</h3>
              <div style={{ fontSize: 13, lineHeight: 1.8 }}>
                <div>
                  Driver: <strong>{selectedVeicolo.driver || 'Non assegnato'}</strong>
                </div>
                <div>Inizio: {formatDate(selectedVeicolo.data_inizio)}</div>
                <div>Fine: {formatDate(selectedVeicolo.data_fine)}</div>
              </div>
            </div>
            <div>
              <h3 style={{ margin: '0 0 8px 0', fontSize: 14, color: COLORS.textMuted }}>
                Totale {annoFiltro || 'tutti gli anni'}
              </h3>
              <div style={{ fontSize: 24, fontWeight: 'bold', color: COLORS.primary }}>
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
                    borderRadius: BORDER_RADIUS.md,
                    cursor: 'pointer',
                    borderLeft: `4px solid ${cat.color}`,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span>{cat.icon}</span>
                    <span style={{ fontWeight: '600', color: cat.color }}>{cat.label}</span>
                    <span style={{ fontSize: 13, color: COLORS.textMuted }}>({spese.length} fatture)</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{ fontWeight: 'bold', fontSize: 16, color: cat.color }}>
                      {formatEuro(totaleSezione)}
                    </span>
                    <span>{isOpen ? '▲' : '▼'}</span>
                  </div>
                </div>

                {isOpen && (
                  <TableWrap style={{ marginTop: 8, border: 'none' }}>
                    <Table>
                      <thead>
                        <tr>
                          <Th>
                            Data
                          </Th>
                          <Th>
                            Fattura
                          </Th>
                          {cat.key === 'verbali' && (
                            <Th>
                              N° Verbale
                            </Th>
                          )}
                          <Th>
                            Descrizione
                          </Th>
                          <Th align="right">
                            Imponibile
                          </Th>
                          <Th align="right">
                            IVA
                          </Th>
                          <Th align="right">
                            Totale
                          </Th>
                          <Th align="center">
                            Stato
                          </Th>
                          <Th align="center">
                            Vedi
                          </Th>
                        </tr>
                      </thead>
                      <tbody>
                        {spese.map((s, idx) => (
                          <tr
                            key={idx}
                            style={{
                              background: s.imponibile < 0 ? COLORS.warningLight : 'transparent',
                            }}
                          >
                            <Td style={{ fontSize: 12 }}>
                              {formatDate(s.data)}
                            </Td>
                            <Td
                              mono
                              style={{
                                color: COLORS.textMuted,
                                fontSize: 11,
                              }}
                            >
                              {s.numero_fattura || '-'}
                            </Td>
                            {cat.key === 'verbali' && (
                              <Td
                                mono
                                style={{
                                  fontSize: 11,
                                  color: s.numero_verbale ? COLORS.danger : COLORS.textSubtle,
                                }}
                              >
                                {s.numero_verbale || '-'}
                                {s.data_verbale && (
                                  <div style={{ fontSize: 10, color: COLORS.textMuted }}>
                                    {formatDate(s.data_verbale)}
                                  </div>
                                )}
                              </Td>
                            )}
                            <Td>
                              {s.voci?.map((v, vi) => (
                                <div key={vi} style={{ paddingBottom: 4 }}>
                                  <div style={{ fontSize: 11, color: COLORS.gray[600] }}>
                                    {v.descrizione
                                      ?.replace(selectedVeicolo.targa, '')
                                      .trim()
                                      .slice(0, 70) || '-'}
                                  </div>
                                  {(v.noleggio_imponibile != null || v.servizio_imponibile != null) && (
                                    <div style={{ fontSize: 10, color: COLORS.textSubtle }}>
                                      {v.noleggio_imponibile != null &&
                                        `Locazione: ${formatEuro(v.noleggio_imponibile)}`}
                                      {v.noleggio_imponibile != null && v.servizio_imponibile != null && ' • '}
                                      {v.servizio_imponibile != null &&
                                        `Servizi: ${formatEuro(v.servizio_imponibile)}`}
                                    </div>
                                  )}
                                  {v.causale && (
                                    <div
                                      style={{ fontSize: 10, color: COLORS.textSubtle, fontStyle: 'italic' }}
                                      title={v.causale}
                                    >
                                      {v.causale.split(' | ').find(p => p.toUpperCase().includes('CAUSALE')) ||
                                        v.causale.slice(0, 60)}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </Td>
                            <Td
                              align="right"
                              style={{
                                color: s.imponibile < 0 ? COLORS.warning : 'inherit',
                                fontSize: 12,
                              }}
                            >
                              {formatEuro(s.imponibile)}
                            </Td>
                            <Td
                              align="right"
                              style={{
                                color: COLORS.textMuted,
                                fontSize: 12,
                              }}
                            >
                              {formatEuro(s.iva)}
                            </Td>
                            <Td
                              align="right"
                              style={{
                                fontWeight: 'bold',
                                color: s.totale < 0 ? COLORS.warning : 'inherit',
                                fontSize: 12,
                              }}
                            >
                              {formatEuro(s.totale)}
                            </Td>
                            <Td align="center">
                              {s.pagato ? (
                                s.pagato_confermato_banca ? (
                                  <Badge
                                    variant="success"
                                    style={{ fontSize: 10 }}
                                    title="Collegato a un movimento reale in estratto conto"
                                  >
                                    Pagato
                                  </Badge>
                                ) : (
                                  <Badge
                                    variant="warning"
                                    style={{ fontSize: 10 }}
                                    title="Il fornitore ha un metodo di pagamento bancario configurato, ma nessun movimento corrispondente e` stato trovato in estratto conto: il pagamento non e` verificato"
                                  >
                                    Pagato (presunto)
                                  </Badge>
                                )
                              ) : (
                                <Badge variant="danger" style={{ fontSize: 10 }}>Da pagare</Badge>
                              )}
                              {cat.key === 'verbali' && s.ha_ricevuta && (
                                <div style={{ color: COLORS.info, fontSize: 9, marginTop: 2 }}>
                                  Bollettino
                                </div>
                              )}
                              {cat.key === 'verbali' && s.fonte === 'posta+fattura' && (
                                <div style={{ color: COLORS.textSubtle, fontSize: 9, marginTop: 2 }}>
                                  posta + fattura
                                </div>
                              )}
                            </Td>
                          </tr>
                        ))}
                      </tbody>
                      <tfoot>
                        <tr
                          style={{ background: `${cat.color}10`, borderTop: `2px solid ${COLORS.border}` }}
                        >
                          <Td
                            colSpan={cat.key === 'verbali' ? 4 : 3}
                            align="right"
                            style={{ fontWeight: '600' }}
                          >
                            Totale {cat.label}:
                          </Td>
                          <Td
                            align="right"
                            style={{
                              fontWeight: 'bold',
                              fontSize: 12,
                            }}
                          >
                            {formatEuro(spese.reduce((a, s) => a + (s.imponibile || 0), 0))}
                          </Td>
                          <Td
                            align="right"
                            style={{
                              fontWeight: 'bold',
                              fontSize: 12,
                            }}
                          >
                            {formatEuro(spese.reduce((a, s) => a + (s.iva || 0), 0))}
                          </Td>
                          <Td
                            align="right"
                            style={{
                              fontWeight: 'bold',
                              color: cat.color,
                              fontSize: 12,
                            }}
                          >
                            {formatEuro(totaleSezione)}
                          </Td>
                          <Td></Td>
                          <Td></Td>
                        </tr>
                      </tfoot>
                    </Table>
                  </TableWrap>
                )}
              </div>
            );
          })}

          {categorie.every(cat => (selectedVeicolo[cat.key] || []).length === 0) && (
            <div style={{ textAlign: 'center', padding: 40, color: COLORS.textMuted }}>
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
        <div style={{ padding: '16px 20px', borderBottom: `1px solid ${COLORS.border}` }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>🚗 Elenco Veicoli ({veicoli.length})</h2>
        </div>

        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>
            ⏳ Caricamento...
          </div>
        ) : veicoli.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🚗</div>
            <div style={{ color: COLORS.textMuted }}>Nessun veicolo trovato per {annoFiltro}</div>
            <div style={{ color: COLORS.textSubtle, fontSize: 14, marginTop: 8 }}>
              I veicoli vengono rilevati automaticamente dalle fatture dei fornitori di noleggio
            </div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                fontSize: 13,
                background: COLORS.card,
                fontFamily: FONT.family,
              }}
              data-testid="noleggio-table"
            >
              <thead>
                <tr style={{ background: COLORS.bgAlt, borderBottom: `2px solid ${COLORS.border}` }}>
                  <Th>
                    Targa
                  </Th>
                  <Th>
                    Veicolo
                  </Th>
                  <Th>
                    Fornitore
                  </Th>
                  <Th>
                    Contratto
                  </Th>
                  <Th>
                    Driver
                  </Th>
                  <Th align="right">
                    Canoni
                  </Th>
                  <Th align="right">
                    Verbali
                  </Th>
                  <Th align="right">
                    Bollo
                  </Th>
                  <Th align="right">
                    Riparazioni
                  </Th>
                  <Th align="right">
                    TOTALE
                  </Th>
                  <Th align="center">
                    Azioni
                  </Th>
                </tr>
              </thead>
              <tbody>
                {veicoli.map((v, i) => (
                  <tr
                    key={v.targa || i}
                    style={{
                      borderBottom: `1px solid ${COLORS.gray[100]}`,
                      background: selectedVeicolo?.targa === v.targa ? COLORS.infoLight : 'transparent',
                      cursor: 'pointer',
                    }}
                    onClick={() => setSelectedVeicolo(v)}
                    data-testid={`veicolo-row-${v.targa}`}
                  >
                    <Td mono style={{ fontWeight: '600', color: COLORS.info, fontSize: 13 }}>
                      {v.targa}
                    </Td>
                    <Td>
                      <div style={{ fontWeight: '500', fontSize: 12 }}>
                        {v.marca} {(v.modello || '-').slice(0, 25)}
                      </div>
                    </Td>
                    <Td style={{ fontSize: 12 }}>
                      {v.fornitore_noleggio?.split(' ')[0] || '-'}
                    </Td>
                    <Td mono style={{ fontSize: 11, color: COLORS.textMuted }}>
                      {v.contratto || v.codice_cliente || '-'}
                    </Td>
                    <Td style={{ fontSize: 12, color: v.driver ? 'inherit' : COLORS.textSubtle }}>
                      {v.driver || '-'}
                    </Td>
                    <Td align="right" style={{ color: categorie.find(c => c.key === 'canoni').color, fontSize: 12 }}>
                      {formatEuro(v.totale_canoni)}
                    </Td>
                    <Td align="right" style={{ color: categorie.find(c => c.key === 'verbali').color, fontSize: 12 }}>
                      {formatEuro(v.totale_verbali)}
                    </Td>
                    <Td align="right" style={{ color: categorie.find(c => c.key === 'bollo').color, fontSize: 12 }}>
                      {formatEuro(v.totale_bollo)}
                    </Td>
                    <Td align="right" style={{ color: categorie.find(c => c.key === 'riparazioni').color, fontSize: 12 }}>
                      {formatEuro(v.totale_riparazioni)}
                    </Td>
                    <Td align="right" style={{ fontWeight: 'bold', color: COLORS.primary, fontSize: 13 }}>
                      {formatEuro(v.totale_generale)}
                    </Td>
                    <Td align="center">
                      <RowActions style={{ justifyContent: 'center' }}>
                        <RowActionButton
                          variant="info"
                          onClick={e => {
                            e.stopPropagation();
                            setSelectedVeicolo(v);
                          }}
                          title="Vedi dettaglio"
                        >
                        👁️
                      </RowActionButton>
                        <RowActionButton
                          variant="neutral"
                          onClick={e => {
                            e.stopPropagation();
                            setEditingVeicolo({ ...v });
                          }}
                          title="Modifica"
                        >
                        ✏️
                      </RowActionButton>
                      </RowActions>
                    </Td>
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
              background: COLORS.card,
              borderRadius: BORDER_RADIUS.lg,
              padding: 24,
              width: '100%',
              maxWidth: 550,
              maxHeight: '90vh',
              overflowY: 'auto',
              boxShadow: SHADOWS.modal,
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
              <h2 style={{ margin: 0, fontSize: 18 }}>✏️ Modifica {editingVeicolo.targa}</h2>
              <Button
                onClick={() => setEditingVeicolo(null)}
                variant="ghost"
                style={{ fontSize: 20, border: 'none', padding: 0 }}
              >
                ✕
              </Button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Sezione OpenAPI Automotive */}
              <div
                style={{
                  padding: 12,
                  background: COLORS.successLight,
                  borderRadius: BORDER_RADIUS.md,
                  border: `1px solid ${COLORS.success}`,
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
                  <span style={{ fontWeight: '600', color: COLORS.success, fontSize: 13 }}>
                    🚗 Dati da OpenAPI Automotive
                  </span>
                  <Button
                    onClick={() => handleLookupVeicolo(editingVeicolo.targa)}
                    disabled={lookupLoading || !editingVeicolo.targa}
                    variant="success"
                    size="sm"
                  >
                    {lookupLoading ? '⏳ Cercando...' : '🔍 Cerca Dati'}
                  </Button>
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
                    <Button
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
                      variant="info"
                      style={{
                        marginTop: 10,
                        width: '100%',
                      }}
                    >
                      📥 Applica questi dati
                    </Button>
                  </div>
                )}

                {lookupResult?.error && (
                  <div style={{ fontSize: 12, color: COLORS.danger, marginTop: 8 }}>
                    ❌ {lookupResult.error}
                  </div>
                )}

                {!lookupResult && (
                  <p style={{ fontSize: 11, color: COLORS.textMuted, margin: '8px 0 0 0' }}>
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
                  <Input
                    type="text"
                    value={editingVeicolo.marca || ''}
                    onChange={e => setEditingVeicolo({ ...editingVeicolo, marca: e.target.value })}
                    placeholder="Es: BMW"
                  />
                </div>
                <div>
                  <label
                    style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                  >
                    Modello
                  </label>
                  <Input
                    type="text"
                    value={editingVeicolo.modello || ''}
                    onChange={e =>
                      setEditingVeicolo({ ...editingVeicolo, modello: e.target.value })
                    }
                    placeholder="Es: X3 xDrive 20d M Sport"
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
                  <Select
                    value={editingVeicolo.driver_id || ''}
                    onChange={e => {
                      const d = drivers.find(x => x.id === e.target.value);
                      setEditingVeicolo({
                        ...editingVeicolo,
                        driver_id: e.target.value,
                        driver: d?.nome_completo || '',
                      });
                    }}
                    style={{ width: '100%' }}
                  >
                    <option value="">-- Seleziona Driver --</option>
                    {drivers.map(d => (
                      <option key={d.id} value={d.id}>
                        {d.nome_completo}
                      </option>
                    ))}
                  </Select>
                ) : (
                  <Input
                    type="text"
                    value={editingVeicolo.driver || ''}
                    onChange={e => setEditingVeicolo({ ...editingVeicolo, driver: e.target.value })}
                    placeholder="Nome e Cognome"
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
                    N° Contratto
                  </label>
                  <Input
                    type="text"
                    value={editingVeicolo.contratto || ''}
                    onChange={e =>
                      setEditingVeicolo({ ...editingVeicolo, contratto: e.target.value })
                    }
                    placeholder="Numero contratto"
                  />
                </div>
                <div>
                  <label
                    style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                  >
                    Codice Cliente
                  </label>
                  <Input
                    type="text"
                    value={editingVeicolo.codice_cliente || ''}
                    onChange={e =>
                      setEditingVeicolo({ ...editingVeicolo, codice_cliente: e.target.value })
                    }
                    placeholder="Codice cliente fornitore"
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
                  <Input
                    type="number"
                    value={editingVeicolo.canone_mensile ?? ''}
                    onChange={e =>
                      setEditingVeicolo({ ...editingVeicolo, canone_mensile: e.target.value })
                    }
                    placeholder="€"
                  />
                </div>
                <div>
                  <label
                    style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                  >
                    Anno immatr.
                  </label>
                  <Input
                    type="number"
                    value={editingVeicolo.anno_immatricolazione ?? ''}
                    onChange={e =>
                      setEditingVeicolo({
                        ...editingVeicolo,
                        anno_immatricolazione: e.target.value,
                      })
                    }
                  />
                </div>
                <div>
                  <label
                    style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                  >
                    Alimentazione
                  </label>
                  <Input
                    type="text"
                    value={editingVeicolo.alimentazione || ''}
                    onChange={e =>
                      setEditingVeicolo({ ...editingVeicolo, alimentazione: e.target.value })
                    }
                    placeholder="Diesel, Benzina..."
                  />
                </div>
                <div>
                  <label
                    style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                  >
                    Potenza / Cilindrata
                  </label>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <Input
                      type="number"
                      value={editingVeicolo.potenza_kw ?? ''}
                      onChange={e =>
                        setEditingVeicolo({ ...editingVeicolo, potenza_kw: e.target.value })
                      }
                      placeholder="kW"
                    />
                    <Input
                      type="number"
                      value={editingVeicolo.cilindrata ?? ''}
                      onChange={e =>
                        setEditingVeicolo({ ...editingVeicolo, cilindrata: e.target.value })
                      }
                      placeholder="cc"
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
                <Input
                  type="text"
                  value={editingVeicolo.centro_fatturazione || ''}
                  onChange={e =>
                    setEditingVeicolo({ ...editingVeicolo, centro_fatturazione: e.target.value })
                  }
                  placeholder="Centro di fatturazione (es: K26858)"
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
                  <Input
                    type="date"
                    value={editingVeicolo.data_inizio || ''}
                    onChange={e =>
                      setEditingVeicolo({ ...editingVeicolo, data_inizio: e.target.value })
                    }
                  />
                </div>
                <div>
                  <label
                    style={{ display: 'block', fontSize: 12, fontWeight: '500', marginBottom: 4 }}
                  >
                    Fine Noleggio
                  </label>
                  <Input
                    type="date"
                    value={editingVeicolo.data_fine || ''}
                    onChange={e =>
                      setEditingVeicolo({ ...editingVeicolo, data_fine: e.target.value })
                    }
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
                <Input
                  type="text"
                  value={editingVeicolo.note || ''}
                  onChange={e => setEditingVeicolo({ ...editingVeicolo, note: e.target.value })}
                  placeholder="Note aggiuntive"
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 20 }}>
              <Button
                onClick={() => {
                  handleDelete(editingVeicolo.targa);
                  setEditingVeicolo(null);
                }}
                variant="danger"
              >
                🗑️ Elimina
              </Button>
              <div style={{ display: 'flex', gap: 10 }}>
                <Button
                  onClick={() => setEditingVeicolo(null)}
                  variant="secondary"
                >
                  Annulla
                </Button>
                <Button
                  onClick={handleSaveVeicolo}
                  variant="primary"
                >
                  💾 Salva
                </Button>
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
              background: COLORS.card,
              borderRadius: BORDER_RADIUS.lg,
              padding: 24,
              width: '100%',
              maxWidth: 500,
              boxShadow: SHADOWS.modal,
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
              <h2 style={{ margin: 0, fontSize: 18 }}>➕ Aggiungi Veicolo</h2>
              <Button
                onClick={() => setShowAddVeicolo(false)}
                variant="ghost"
                style={{ fontSize: 20, border: 'none', padding: 0 }}
              >
                ✕
              </Button>
            </div>

            <p style={{ fontSize: 13, color: COLORS.textMuted, marginBottom: 16 }}>
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
                <Input
                  type="text"
                  value={nuovoVeicolo.targa}
                  onChange={e =>
                    setNuovoVeicolo({ ...nuovoVeicolo, targa: e.target.value.toUpperCase() })
                  }
                  placeholder="Es: AB123CD"
                  maxLength={7}
                  style={{ fontFamily: FONT.mono }}
                />
              </div>

              <div>
                <label
                  style={{ display: 'block', fontSize: 13, fontWeight: '500', marginBottom: 4 }}
                >
                  Fornitore *
                </label>
                <Select
                  value={nuovoVeicolo.fornitore_piva}
                  onChange={e =>
                    setNuovoVeicolo({ ...nuovoVeicolo, fornitore_piva: e.target.value })
                  }
                  style={{ width: '100%' }}
                >
                  <option value="">-- Seleziona Fornitore --</option>
                  {fornitori.map(f => (
                    <option key={f.piva} value={f.piva}>
                      {f.nome} {!f.targa_in_fattura ? '⚠️' : ''}
                    </option>
                  ))}
                </Select>
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
                  <Input
                    type="text"
                    value={nuovoVeicolo.marca}
                    onChange={e => setNuovoVeicolo({ ...nuovoVeicolo, marca: e.target.value })}
                    placeholder="Es: BMW"
                  />
                </div>
                <div>
                  <label
                    style={{ display: 'block', fontSize: 13, fontWeight: '500', marginBottom: 4 }}
                  >
                    Modello
                  </label>
                  <Input
                    type="text"
                    value={nuovoVeicolo.modello}
                    onChange={e => setNuovoVeicolo({ ...nuovoVeicolo, modello: e.target.value })}
                    placeholder="Es: X3 xDrive"
                  />
                </div>
              </div>

              <div>
                <label
                  style={{ display: 'block', fontSize: 13, fontWeight: '500', marginBottom: 4 }}
                >
                  Numero Contratto
                </label>
                <Input
                  type="text"
                  value={nuovoVeicolo.contratto}
                  onChange={e => setNuovoVeicolo({ ...nuovoVeicolo, contratto: e.target.value })}
                  placeholder="Numero contratto noleggio"
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 24 }}>
              <Button
                onClick={() => setShowAddVeicolo(false)}
                variant="secondary"
              >
                Annulla
              </Button>
              <Button
                onClick={handleAddVeicolo}
                variant="primary"
              >
                ➕ Aggiungi
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Fatture Non Associate — sostituisce il vecchio alert() nativo
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
                📋 Fatture Non Associate ({modalFattureNonAssociate.fatture.length})
              </h2>
              <Button
                onClick={() => setModalFattureNonAssociate(m => ({ ...m, open: false }))}
                variant="ghost"
                style={{ fontSize: 20, border: 'none', padding: 0 }}
              >
                ✕
              </Button>
            </div>
            <p style={{ fontSize: 13, color: COLORS.textMuted, marginBottom: 16 }}>
              Queste fatture non indicano una targa certa. Seleziona il veicolo o il contratto
              corretto: questa relazione non modifica lo stato del pagamento.
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
                  ✅ Nessuna fattura non associata
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
                        {f.fornitore || 'N/D'} • Fatt. {f.numero || 'N/D'} del {f.data || 'N/D'}
                      </div>
                      <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 2 }}>
                        {formatEuro(Number(f.importo || 0))}
                        {f.descrizione ? ` • ${f.descrizione}` : ''}
                      </div>
                      {(f.contratto || f.codice_cliente) && (
                        <div style={{ fontSize: 11, color: COLORS.textSubtle, marginTop: 2 }}>
                          {f.contratto ? `Contratto: ${f.contratto}` : ''}
                          {f.contratto && f.codice_cliente ? ' • ' : ''}
                          {f.codice_cliente ? `Cod. cliente: ${f.codice_cliente}` : ''}
                        </div>
                      )}
                    </div>
                    <div
                      style={{
                        display: 'flex',
                        gap: 6,
                        flexShrink: 0,
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        justifyContent: 'flex-end',
                      }}
                    >
                      {f.id && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={e => {
                            e.stopPropagation();
                            setFatturaView({ id: f.id, numero: f.numero_fattura || f.numero || f.fornitore });
                          }}
                        >
                          Vedi
                        </Button>
                      )}
                      {(f.veicoli_candidati || []).length > 0 ? (
                        <>
                          <Select
                            aria-label={`Veicolo per fattura ${f.numero || ''}`}
                            value={veicoloSceltoPerFattura[f.id] || ''}
                            onChange={event =>
                              setVeicoloSceltoPerFattura(current => ({
                                ...current,
                                [f.id]: event.target.value,
                              }))
                            }
                            style={{ minWidth: 190, padding: '7px 9px' }}
                          >
                            <option value="">Scegli veicolo</option>
                            {(f.veicoli_candidati || []).map(veicolo => (
                              <option key={veicolo.targa} value={veicolo.targa}>
                                {veicolo.targa}
                                {veicolo.contratto ? ` · contratto ${veicolo.contratto}` : ''}
                                {veicolo.modello ? ` · ${veicolo.modello}` : ''}
                              </option>
                            ))}
                          </Select>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={
                              !veicoloSceltoPerFattura[f.id] || fatturaInAssociazione === f.id
                            }
                            onClick={() => handleAssociaFatturaVeicolo(f)}
                          >
                            {fatturaInAssociazione === f.id
                              ? 'Associazione...'
                              : 'Associa al veicolo'}
                          </Button>
                        </>
                      ) : (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setNuovoVeicolo(v => ({ ...v, fornitore_piva: f.piva || '' }));
                            setModalFattureNonAssociate(m => ({ ...m, open: false }));
                            setShowAddVeicolo(true);
                          }}
                        >
                          Nuovo veicolo
                        </Button>
                      )}
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

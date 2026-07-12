import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, formatDateIT, formatDateGGMM, COLORS, SHADOWS, BORDER_RADIUS, useIsMobile } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import ModalFattura from '../components/ModalFattura';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { Button, Badge, StatCard, Input, Select, RowActions, RowActionButton, ListaAdattiva } from '../components/ds';

export default function Scadenze() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [scadenze, setScadenze] = useState([]);
  const [scadenzeIva, setScadenzeIva] = useState(null);
  const [scadenzeIvaMensili, setScadenzeIvaMensili] = useState(null);
  const [vistaIva, setVistaIva] = useState('trimestrale'); // 'trimestrale' o 'mensile'
  const [alertWidget, setAlertWidget] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filtroTipo, setFiltroTipo] = useState('');
  const [includePassate, setIncludePassate] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [viewingInvoice, setViewingInvoice] = useState(null);
  const [documentiRiconciliare, setDocumentiRiconciliare] = useState(null);
  const [pagaModal, setPagaModal] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [paidIds, setPaidIds] = useState(new Set());
  const [nuovaScadenza, setNuovaScadenza] = useState({
    data_scadenza: '',
    descrizione: '',
    tipo: 'CUSTOM',
    importo: '',
    priorita: 'media',
    note: '',
  });

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anno, filtroTipo, includePassate]);

  const loadData = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      params.append('anno', anno);
      if (filtroTipo) params.append('tipo', filtroTipo);
      params.append('include_passate', includePassate);
      params.append('limit', '50');

      const [scadenzeRes, ivaRes, ivaMensileRes, alertRes, docRiconcRes] = await Promise.all([
        api.get(`/api/scadenze/tutte?${params}`),
        api.get(`/api/scadenze/iva/${anno}`),
        api.get(`/api/scadenze/iva-mensile/${anno}`),
        api.get('/api/scadenze/dashboard-widget').catch(() => ({ data: null })),
        api.get('/api/email-scanner/statistiche').catch(() => ({ data: null })),
      ]);

      setScadenze(scadenzeRes.data.scadenze || []);
      setScadenzeIva(ivaRes.data);
      setScadenzeIvaMensili(ivaMensileRes.data);
      setAlertWidget(alertRes.data);
      setDocumentiRiconciliare(docRiconcRes.data);
    } catch (error) {
      console.error('Error loading scadenze:', error);
    } finally {
      setLoading(false);
    }
  };

  const handlePagaScadenza = async (scadenza, metodo) => {
    setProcessing(true);
    try {
      await api.post('/api/fatture-ricevute/paga-manuale', {
        fattura_id: scadenza.fattura_id || scadenza.id,
        scadenza_id: scadenza.id,
        importo: Math.abs(scadenza.importo),
        metodo: metodo,
        data_pagamento: new Date().toISOString().split('T')[0],
        fornitore: scadenza.fornitore || '',
        numero_fattura: scadenza.numero_fattura || '',
      });
      setPagaModal(null);
      setPaidIds(prev => new Set([...prev, scadenza.id]));
      loadData();
    } catch (e) {
      toast.error('Errore pagamento: ' + (e.response?.data?.detail || e.message));
    } finally {
      setProcessing(false);
    }
  };

  const handleCreaScadenza = async () => {
    if (!nuovaScadenza.data_scadenza || !nuovaScadenza.descrizione) {
      toast.error('Compila data e descrizione');
      return;
    }

    try {
      await api.post('/api/scadenze/crea', {
        ...nuovaScadenza,
        importo: parseFloat(nuovaScadenza.importo) || 0,
      });
      setShowModal(false);
      setNuovaScadenza({
        data_scadenza: '',
        descrizione: '',
        tipo: 'CUSTOM',
        importo: '',
        priorita: 'media',
        note: '',
      });
      loadData();
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleCompleta = async id => {
    try {
      await api.put(`/api/scadenze/completa/${id}`);
      loadData();
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleElimina = async id => {
    const confirmed = await confirm({
      title: 'Elimina scadenza',
      message: 'Eliminare questa scadenza?',
      confirmText: 'Elimina',
      cancelText: 'Annulla',
      variant: 'danger',
    });
    if (!confirmed) return;
    try {
      await api.delete(`/api/scadenze/${id}`);
      loadData();
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
    }
  };

  const formatDate = dateStr => (dateStr ? formatDateIT(dateStr) : '-');

  const getPriorityStyle = (priorita, urgente) => {
    if (urgente || priorita === 'critica')
      return { variant: 'danger', bg: COLORS.dangerLight, border: COLORS.danger, text: COLORS.danger };
    switch (priorita) {
      case 'alta':
      case 'media':
        return { variant: 'warning', bg: COLORS.warningLight, border: COLORS.warning, text: COLORS.warning };
      default:
        return { variant: 'success', bg: COLORS.successLight, border: COLORS.success, text: COLORS.success };
    }
  };

  // Semaforo di urgenza per riga (desktop): sfondo colorato, bordo sinistro
  // e attenuazione delle scadenze passate — replicato via tdStyle per cella.
  const isScadenzaPassata = s => s.giorni_mancanti !== undefined && s.giorni_mancanti < 0;
  const tdStyleScadenza = (s, extra = {}) => {
    const st = getPriorityStyle(s.priorita, s.urgente);
    const passata = isScadenzaPassata(s);
    return {
      background: passata ? COLORS.gray[50] : st.bg,
      opacity: passata ? 0.6 : 1,
      ...extra,
    };
  };

  const testoGiorni = s =>
    s.giorni_mancanti === undefined
      ? ''
      : s.giorni_mancanti === 0
        ? 'OGGI'
        : s.giorni_mancanti === 1
          ? '1g'
          : s.giorni_mancanti < 0
            ? `-${Math.abs(s.giorni_mancanti)}g`
            : `${s.giorni_mancanti}g`;

  const getTipoIcon = tipo => {
    switch (tipo) {
      case 'IVA':
        return '🧾';
      case 'F24':
        return '📋';
      case 'FATTURA':
        return '📄';
      case 'INPS':
        return '🏛️';
      case 'IRPEF':
        return '📋';
      default:
        return '📌';
    }
  };

  return (
    <PageLayout
      title="Scadenze e Notifiche"
      icon="📅"
      subtitle="Gestione scadenze fiscali, pagamenti e promemoria"
      actions={
        <Button variant="info" size="lg" iconLeft="➕" onClick={() => setShowModal(true)}>
          Nuova Scadenza
        </Button>
      }
    >
      <div style={{ position: 'relative' }}>
        {/* Page Info Card */}
        {/* Alert Widget - Notifiche Urgenti */}
        {alertWidget && alertWidget.totale_alert > 0 && (
          <div
            style={{
              background: COLORS.danger,
              borderRadius: BORDER_RADIUS.xl,
              padding: 20,
              marginBottom: 20,
              color: 'white',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 15 }}>
              <span style={{ fontSize: 24 }}>⚠️</span>
              <h3 style={{ margin: 0 }}>{alertWidget.totale_alert} Alert Attivi</h3>
            </div>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: 12,
              }}
            >
              {alertWidget.f24?.da_pagare_30gg > 0 && (
                <StatCard
                  icon="📋"
                  label="F24 da Pagare"
                  value={alertWidget?.f24?.da_pagare_30gg}
                  accent="danger"
                  onClick={() => navigate('/contabilita/calendario')}
                />
              )}
              {alertWidget.fiscali?.prossime > 0 && (
                <StatCard
                  icon="📅"
                  label="Scadenze Fiscali"
                  value={alertWidget?.fiscali?.prossime}
                  accent="warning"
                />
              )}
            </div>
          </div>
        )}

        {/* Sezione Documenti da Riconciliare */}
        {documentiRiconciliare &&
          (documentiRiconciliare.verbali?.in_attesa_fattura > 0 ||
            documentiRiconciliare.verbali?.estratti_da_fatture -
              documentiRiconciliare.verbali?.con_pdf_scaricato >
              0) && (
            <div
              style={{
                background: COLORS.info,
                borderRadius: BORDER_RADIUS.xl,
                padding: 20,
                marginBottom: 20,
                color: 'white',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 15 }}>
                <span style={{ fontSize: 24 }}>🔄</span>
                <h3 style={{ margin: 0 }}>Documenti da Riconciliare</h3>
              </div>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                  gap: 12,
                }}
              >
                {/* Verbali in attesa di fattura */}
                {documentiRiconciliare.verbali?.in_attesa_fattura > 0 && (
                  <div
                    onClick={() => navigate('/noleggio')}
                    style={{
                      background: 'rgba(255,255,255,0.15)',
                      padding: 15,
                      borderRadius: BORDER_RADIUS.md,
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      borderLeft: `4px solid ${COLORS.warning}`,
                    }}
                    onMouseEnter={e =>
                      (e.currentTarget.style.background = 'rgba(255,255,255,0.25)')
                    }
                    onMouseLeave={e =>
                      (e.currentTarget.style.background = 'rgba(255,255,255,0.15)')
                    }
                    data-testid="verbali-attesa-fattura-card"
                  >
                    <div style={{ fontSize: 32, fontWeight: 700 }}>
                      {documentiRiconciliare?.verbali?.in_attesa_fattura}
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                      📧 Verbali in Attesa Fattura
                    </div>
                    <div style={{ fontSize: 11, opacity: 0.8 }}>
                      PDF arrivati via email, fattura non ancora ricevuta
                    </div>
                  </div>
                )}

                {/* Fatture in attesa di verbale (PDF) */}
                {documentiRiconciliare.verbali?.estratti_da_fatture -
                  documentiRiconciliare.verbali?.con_pdf_scaricato >
                  0 && (
                  <div
                    onClick={() => navigate('/noleggio')}
                    style={{
                      background: 'rgba(255,255,255,0.15)',
                      padding: 15,
                      borderRadius: BORDER_RADIUS.md,
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      borderLeft: `4px solid ${COLORS.success}`,
                    }}
                    onMouseEnter={e =>
                      (e.currentTarget.style.background = 'rgba(255,255,255,0.25)')
                    }
                    onMouseLeave={e =>
                      (e.currentTarget.style.background = 'rgba(255,255,255,0.15)')
                    }
                    data-testid="fatture-attesa-verbale-card"
                  >
                    <div style={{ fontSize: 32, fontWeight: 700 }}>
                      {documentiRiconciliare?.verbali?.estratti_da_fatture -
                        documentiRiconciliare.verbali.con_pdf_scaricato}
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                      📄 Fatture in Attesa Verbale
                    </div>
                    <div style={{ fontSize: 11, opacity: 0.8 }}>
                      Fattura ricevuta, PDF verbale non ancora scaricato
                    </div>
                  </div>
                )}

                {/* Esattoriali da processare */}
                {documentiRiconciliare.esattoriali > 0 && (
                  <StatCard
                    label="Cartelle Esattoriali"
                    value={documentiRiconciliare.esattoriali}
                    subtext="Da verificare e processare"
                    accent="danger"
                  />
                )}

                {/* F24/Tributi */}
                {documentiRiconciliare.f24_tributi > 0 && (
                  <StatCard
                    icon="📋"
                    label="F24/Tributi"
                    value={documentiRiconciliare.f24_tributi}
                    subtext="Documenti da posta"
                    accent="info"
                  />
                )}
              </div>

              {/* Riepilogo totale */}
              <div
                style={{
                  marginTop: 15,
                  paddingTop: 15,
                  borderTop: '1px solid rgba(255,255,255,0.2)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div style={{ fontSize: 13, opacity: 0.9 }}>
                  Totale documenti scaricati dalla posta:{' '}
                  <strong>{documentiRiconciliare.totale_documenti_email}</strong>
                </div>
                <Button
                  variant="secondary"
                  onClick={async () => {
                    try {
                      await api.post('/api/email-scanner/associa');
                      loadData();
                      toast.success('Associazione completata!');
                    } catch (err) {
                      toast.error('Errore: ' + (err.response?.data?.detail || err.message));
                    }
                  }}
                  style={{
                    background: 'rgba(255,255,255,0.2)',
                    color: '#fff',
                    borderColor: 'rgba(255,255,255,0.3)',
                  }}
                  data-testid="btn-riconci-automatica"
                >
                  🔄 Riconcilia Automaticamente
                </Button>
              </div>
            </div>
          )}

        {/* Riepilogo IVA - Trimestrale e Mensile */}
        {(scadenzeIva || scadenzeIvaMensili) && (
          <div
            style={{
              background: COLORS.info,
              borderRadius: BORDER_RADIUS.xl,
              padding: 20,
              marginBottom: 20,
              color: 'white',
            }}
          >
            {/* Header con bottoni toggle */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 15,
              }}
            >
              <h3 style={{ margin: 0 }}>🧾 Scadenze IVA {anno}</h3>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button
                  variant={vistaIva === 'trimestrale' ? 'warning' : 'secondary'}
                  onClick={() => setVistaIva('trimestrale')}
                  style={
                    vistaIva === 'trimestrale'
                      ? {}
                      : { background: 'rgba(255,255,255,0.2)', color: '#fff', borderColor: 'rgba(255,255,255,0.3)' }
                  }
                  data-testid="btn-vista-trimestrale"
                >
                  📊 Trimestrale
                </Button>
                <Button
                  variant={vistaIva === 'mensile' ? 'success' : 'secondary'}
                  onClick={() => setVistaIva('mensile')}
                  style={
                    vistaIva === 'mensile'
                      ? {}
                      : { background: 'rgba(255,255,255,0.2)', color: '#fff', borderColor: 'rgba(255,255,255,0.3)' }
                  }
                  data-testid="btn-vista-mensile"
                >
                  📅 Mensile
                </Button>
              </div>
            </div>

            {/* Vista Trimestrale */}
            {vistaIva === 'trimestrale' && scadenzeIva && (
              <>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: 15,
                  }}
                >
                  {scadenzeIva.scadenze?.map((s, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: 'rgba(255,255,255,0.1)',
                        padding: 15,
                        borderRadius: BORDER_RADIUS.md,
                        borderLeft: `4px solid ${s.da_versare ? COLORS.warning : COLORS.success}`,
                      }}
                    >
                      <div style={{ fontWeight: 'bold', marginBottom: 8 }}>{s.periodo}</div>
                      <div style={{ fontSize: 13, opacity: 0.9 }}>
                        <div>Debito: {formatEuro(s.iva_debito)}</div>
                        <div>Credito: {formatEuro(s.iva_credito)}</div>
                      </div>
                      <div
                        style={{
                          marginTop: 10,
                          padding: '6px 10px',
                          background: s.da_versare ? COLORS.warningLight : COLORS.successLight,
                          borderRadius: BORDER_RADIUS.sm,
                          color: s.da_versare ? COLORS.warning : COLORS.success,
                          fontWeight: 'bold',
                          fontSize: 14,
                          textAlign: 'center',
                        }}
                      >
                        {s.da_versare
                          ? `Versare ${formatEuro(s.importo_versamento)}`
                          : `A credito ${formatEuro(s.a_credito || Math.abs(s.saldo || 0))}`}
                      </div>
                      <div style={{ fontSize: 11, marginTop: 8, opacity: 0.8 }}>
                        Scadenza: {formatDate(s.data_scadenza)}
                        {s.giorni_mancanti !== null && s.giorni_mancanti >= 0 && (
                          <span style={{ marginLeft: 8 }}>
                            ({s.giorni_mancanti === 0 ? 'OGGI' : `tra ${s.giorni_mancanti}g`})
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                {scadenzeIva.totale_da_versare > 0 && (
                  <div style={{ marginTop: 15, textAlign: 'right', fontSize: 18 }}>
                    Totale da versare: <strong>{formatEuro(scadenzeIva.totale_da_versare)}</strong>
                  </div>
                )}
              </>
            )}

            {/* Vista Mensile */}
            {vistaIva === 'mensile' && scadenzeIvaMensili && (
              <>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                    gap: 10,
                  }}
                >
                  {scadenzeIvaMensili.scadenze?.map((s, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: 'rgba(255,255,255,0.1)',
                        padding: 12,
                        borderRadius: BORDER_RADIUS.md,
                        borderLeft: `3px solid ${s.da_versare ? COLORS.warning : COLORS.success}`,
                      }}
                    >
                      <div style={{ fontWeight: 'bold', marginBottom: 6, fontSize: 13 }}>
                        {s.mese_nome}
                      </div>
                      <div style={{ fontSize: 11, opacity: 0.9 }}>
                        <div>D: {formatEuro(s.iva_debito)}</div>
                        <div>C: {formatEuro(s.iva_credito)}</div>
                      </div>
                      <div
                        style={{
                          marginTop: 8,
                          padding: '4px 8px',
                          background: s.da_versare ? COLORS.warningLight : COLORS.successLight,
                          borderRadius: BORDER_RADIUS.sm,
                          color: s.da_versare ? COLORS.warning : COLORS.success,
                          fontWeight: 'bold',
                          fontSize: 12,
                          textAlign: 'center',
                        }}
                      >
                        {s.da_versare
                          ? formatEuro(s.importo_versamento)
                          : `- ${formatEuro(s.a_credito || Math.abs(s.saldo || 0))}`}
                      </div>
                    </div>
                  ))}
                </div>
                <div
                  style={{
                    marginTop: 15,
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: 14,
                  }}
                >
                  <div>
                    Totale a credito:{' '}
                    <strong style={{ color: COLORS.successLight }}>
                      {formatEuro(scadenzeIvaMensili.totale_a_credito)}
                    </strong>
                  </div>
                  <div>
                    Totale da versare:{' '}
                    <strong style={{ color: COLORS.warningLight }}>
                      {formatEuro(scadenzeIvaMensili.totale_da_versare)}
                    </strong>
                  </div>
                  <div>
                    Saldo annuale:{' '}
                    <strong
                      style={{
                        color:
                          scadenzeIvaMensili.saldo_annuale > 0
                            ? COLORS.warningLight
                            : COLORS.successLight,
                      }}
                    >
                      {scadenzeIvaMensili.saldo_annuale > 0
                        ? `Da versare ${formatEuro(scadenzeIvaMensili.saldo_annuale)}`
                        : `A credito ${formatEuro(Math.abs(scadenzeIvaMensili.saldo_annuale))}`}
                    </strong>
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* Filtri */}
        <div
          style={{
            display: 'flex',
            gap: 12,
            marginBottom: 20,
            flexWrap: 'wrap',
            alignItems: 'center',
            background: COLORS.bgAlt,
            padding: 15,
            borderRadius: BORDER_RADIUS.lg,
          }}
        >
          <Select value={filtroTipo} onChange={e => setFiltroTipo(e.target.value)} style={{ width: 'auto' }}>
            <option value="">Tutti i tipi</option>
            <option value="IVA">IVA</option>
            <option value="F24">F24</option>
            <option value="FATTURA">Fatture</option>
            <option value="INPS">INPS</option>
            <option value="CUSTOM">Personalizzate</option>
          </Select>

          <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={includePassate}
              onChange={e => setIncludePassate(e.target.checked)}
            />
            <span>Mostra scadenze passate</span>
          </label>

          <Button variant="secondary" onClick={loadData}>
            🔄 Aggiorna
          </Button>
        </div>

        {/* Lista Scadenze */}
        <div
          style={{
            background: COLORS.card,
            borderRadius: BORDER_RADIUS.md,
            overflow: 'hidden',
            border: `1px solid ${COLORS.border}`,
          }}
        >
          <div
            style={{
              padding: '16px 20px',
              background: COLORS.bgAlt,
              borderBottom: `1px solid ${COLORS.border}`,
              fontWeight: 'bold',
            }}
          >
            📋 Tutte le Scadenze ({scadenze.length})
          </div>

          {loading ? (
            <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>
              ⏳ Caricamento...
            </div>
          ) : scadenze.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>
              Nessuna scadenza trovata per i filtri selezionati.
            </div>
          ) : (
            <div
              style={{
                maxHeight: '60vh',
                overflow: 'auto',
                padding: isMobile ? '10px' : 0,
              }}
            >
              <ListaAdattiva
                testId="scadenze-table"
                dati={scadenze}
                pageSize={50}
                chiave={(s, idx) => s.id || `scad-${idx}`}
                colonne={[
                  {
                    // Su mobile il badge Tipo (semaforo urgenza) è riportato
                    // nel titolo della card, quindi qui è 'omesso'.
                    key: 'tipo',
                    label: 'Tipo',
                    align: 'center',
                    ruoloCard: 'omesso',
                    render: s => (
                      <Badge variant={getPriorityStyle(s.priorita, s.urgente).variant}>
                        {s.tipo}
                      </Badge>
                    ),
                    tdStyle: s =>
                      tdStyleScadenza(s, {
                        borderLeft: `4px solid ${getPriorityStyle(s.priorita, s.urgente).border}`,
                      }),
                  },
                  {
                    key: 'importo',
                    label: 'Importo',
                    align: 'right',
                    mono: true,
                    ruoloCard: 'importo',
                    render: s => (s.importo > 0 ? formatEuro(s.importo) : '-'),
                    tdStyle: s =>
                      tdStyleScadenza(s, {
                        fontWeight: 'bold',
                        color: getPriorityStyle(s.priorita, s.urgente).text,
                      }),
                  },
                  {
                    key: 'data',
                    label: 'Data',
                    align: 'center',
                    ruoloCard: 'dettaglio',
                    iconaCard: '📅',
                    // Su mobile solo gg/mm: l'anno è nel selettore globale
                    render: s => (isMobile ? formatDateGGMM(s.data) || '-' : formatDate(s.data)),
                    tdStyle: s => tdStyleScadenza(s, { color: COLORS.textMuted }),
                  },
                  {
                    key: 'giorni_mancanti',
                    label: 'Giorni',
                    align: 'center',
                    ruoloCard: 'dettaglio',
                    iconaCard: '⏳',
                    render: s => (
                      <span
                        style={{
                          fontWeight: 'bold',
                          color:
                            isScadenzaPassata(s) || s.urgente ? COLORS.danger : COLORS.textMuted,
                        }}
                      >
                        {testoGiorni(s)}
                      </span>
                    ),
                    tdStyle: s => tdStyleScadenza(s),
                  },
                  {
                    key: 'descrizione',
                    label: 'Descrizione',
                    align: 'left',
                    ruoloCard: 'titolo',
                    render: s => (
                      <>
                        {/* Badge urgenza visibile anche nella card mobile */}
                        {isMobile && (
                          <Badge variant={getPriorityStyle(s.priorita, s.urgente).variant}>
                            {s.tipo}
                          </Badge>
                        )}
                        {isMobile ? ' ' : null}
                        {s.descrizione}
                        {s.fornitore && (
                          <span style={{ color: COLORS.textSubtle, marginLeft: 8 }}>
                            • {s.fornitore}
                          </span>
                        )}
                      </>
                    ),
                    tdStyle: s =>
                      tdStyleScadenza(s, {
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        maxWidth: 250,
                      }),
                  },
                  {
                    key: 'azioni',
                    label: 'Azioni',
                    align: 'center',
                    ruoloCard: 'azioni',
                    tdStyle: s => tdStyleScadenza(s),
                    render: s => (
                      <>
                        {s.source === 'custom' && (
                          <RowActions style={{ justifyContent: isMobile ? 'flex-end' : 'center' }}>
                            <RowActionButton
                              variant="success"
                              onClick={() => handleCompleta(s.id)}
                              title="Segna come completata"
                            >
                              ✓
                            </RowActionButton>
                            <RowActionButton
                              variant="danger"
                              onClick={() => handleElimina(s.id)}
                              title="Elimina"
                            >
                              🗑️
                            </RowActionButton>
                          </RowActions>
                        )}

                        {/* Pulsanti Visualizza Fattura per scadenze tipo FATTURA */}
                        {(s.tipo === 'FATTURA' || s.source === 'fattura') &&
                          (s.fattura_id || s.id) && (
                            <RowActions
                              style={{
                                justifyContent: isMobile ? 'flex-end' : 'center',
                                marginTop: s.source === 'custom' ? 6 : 0,
                              }}
                            >
                              <RowActionButton
                                variant="info"
                                onClick={() => {
                                  setViewingInvoice({
                                    id: s.fattura_id || s.id,
                                    numero: s.numero_fattura || s.numero || s.descrizione,
                                  });
                                }}
                                title="Visualizza Dettagli Fattura"
                                data-testid={`view-invoice-${s.fattura_id || s.id}`}
                              >
                                👁️
                              </RowActionButton>
                              <a
                                href={`/api/fatture-ricevute/fattura/${s.fattura_id || s.id}/view-assoinvoice`}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  width: 28,
                                  height: 28,
                                  borderRadius: BORDER_RADIUS.sm,
                                  background: COLORS.successLight,
                                  color: COLORS.success,
                                  fontSize: 12,
                                  textDecoration: 'none',
                                }}
                                title="Visualizza PDF Fattura"
                                data-testid={`pdf-invoice-${s.fattura_id || s.id}`}
                              >
                                📄
                              </a>
                            </RowActions>
                          )}

                        {/* Bottone Paga: SOLO per le fatture. L'endpoint di
                            pagamento è /api/fatture-ricevute/paga-manuale e vuole
                            una fattura vera; su scadenze fiscali (IVA/F24/INPS,
                            senza fattura_id) passava un id inesistente e falliva. */}
                        {!paidIds.has(s.id) &&
                          (s.tipo === 'FATTURA' || s.source === 'fattura') &&
                          (s.fattura_id || s.id) && (
                            <Button
                              variant="warning"
                              size="sm"
                              onClick={() => setPagaModal(s)}
                              title="Registra Pagamento"
                              style={{ marginTop: 4, fontSize: 11, padding: '4px 10px' }}
                            >
                              💰 Paga
                            </Button>
                          )}
                        {paidIds.has(s.id) && <Badge variant="success">✓ Pagato</Badge>}
                      </>
                    ),
                  },
                ]}
              />
            </div>
          )}
        </div>

        {/* Modal Nuova Scadenza */}
        {showModal && (
          <div
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: 'rgba(0,0,0,0.5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 1000,
            }}
            onClick={() => setShowModal(false)}
          >
            <div
              style={{
                background: COLORS.card,
                borderRadius: BORDER_RADIUS.xl,
                padding: 24,
                width: '90%',
                maxWidth: 500,
                boxShadow: SHADOWS.modal,
              }}
              onClick={e => e.stopPropagation()}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: 20,
                }}
              >
                <h3 style={{ margin: 0 }}>➕ Nuova Scadenza</h3>
                <Button
                  variant="ghost"
                  onClick={() => setShowModal(false)}
                  aria-label="Chiudi"
                  style={{
                    width: 32,
                    height: 32,
                    padding: 0,
                    background: COLORS.bgAlt,
                    color: COLORS.textMuted,
                    fontSize: 16,
                  }}
                >
                  ✕
                </Button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 15 }}>
                <div>
                  <label
                    style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: '500' }}
                  >
                    Data Scadenza *
                  </label>
                  <Input
                    type="date"
                    value={nuovaScadenza.data_scadenza}
                    onChange={e =>
                      setNuovaScadenza({ ...nuovaScadenza, data_scadenza: e.target.value })
                    }
                  />
                </div>

                <div>
                  <label
                    style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: '500' }}
                  >
                    Descrizione *
                  </label>
                  <Input
                    type="text"
                    value={nuovaScadenza.descrizione}
                    onChange={e =>
                      setNuovaScadenza({ ...nuovaScadenza, descrizione: e.target.value })
                    }
                    placeholder="Es: Pagamento fornitore XYZ"
                  />
                </div>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                    gap: 15,
                  }}
                >
                  <div>
                    <label
                      style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: '500' }}
                    >
                      Tipo
                    </label>
                    <Select
                      value={nuovaScadenza.tipo}
                      onChange={e => setNuovaScadenza({ ...nuovaScadenza, tipo: e.target.value })}
                      style={{ width: '100%' }}
                    >
                      <option value="CUSTOM">Personalizzata</option>
                      <option value="FATTURA">Fattura</option>
                      <option value="F24">F24</option>
                      <option value="IVA">IVA</option>
                      <option value="INPS">INPS</option>
                    </Select>
                  </div>

                  <div>
                    <label
                      style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: '500' }}
                    >
                      Priorità
                    </label>
                    <Select
                      value={nuovaScadenza.priorita}
                      onChange={e =>
                        setNuovaScadenza({ ...nuovaScadenza, priorita: e.target.value })
                      }
                      style={{ width: '100%' }}
                    >
                      <option value="bassa">Bassa</option>
                      <option value="media">Media</option>
                      <option value="alta">Alta</option>
                      <option value="critica">Critica</option>
                    </Select>
                  </div>
                </div>

                <div>
                  <label
                    style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: '500' }}
                  >
                    Importo (opzionale)
                  </label>
                  <Input
                    type="number"
                    step="0.01"
                    value={nuovaScadenza.importo}
                    onChange={e => setNuovaScadenza({ ...nuovaScadenza, importo: e.target.value })}
                    placeholder="0.00"
                  />
                </div>

                <div>
                  <label
                    style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: '500' }}
                  >
                    Note (opzionale)
                  </label>
                  <textarea
                    value={nuovaScadenza.note}
                    onChange={e => setNuovaScadenza({ ...nuovaScadenza, note: e.target.value })}
                    rows={2}
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      borderRadius: BORDER_RADIUS.sm,
                      border: `1px solid ${COLORS.border}`,
                      resize: 'vertical',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', gap: 10, marginTop: 20, justifyContent: 'flex-end' }}>
                <Button variant="secondary" onClick={() => setShowModal(false)}>
                  Annulla
                </Button>
                <Button variant="info" onClick={handleCreaScadenza}>
                  Salva Scadenza
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Modal Visualizzazione Fattura AssoInvoice */}
        {viewingInvoice && (
          <ModalFattura
            fatturaId={viewingInvoice.id}
            numero={viewingInvoice.numero}
            onClose={() => {
              setViewingInvoice(null);
            }}
          />
        )}

        {/* Modal Pagamento Cassa/Banca */}
        {pagaModal && (
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
            onClick={() => setPagaModal(null)}
          >
            <div
              style={{
                background: COLORS.card,
                borderRadius: BORDER_RADIUS.xl,
                padding: 24,
                maxWidth: 420,
                width: '90%',
                boxShadow: SHADOWS.modal,
              }}
              onClick={e => e.stopPropagation()}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  justifyContent: 'space-between',
                  gap: 12,
                }}
              >
                <h3 style={{ margin: '0 0 8px', fontSize: 18, color: COLORS.primaryLight }}>
                  💰 Registra Pagamento
                </h3>
                <Button
                  variant="ghost"
                  onClick={() => setPagaModal(null)}
                  aria-label="Chiudi"
                  style={{
                    width: 32,
                    height: 32,
                    padding: 0,
                    background: COLORS.bgAlt,
                    color: COLORS.textMuted,
                    fontSize: 16,
                  }}
                >
                  ✕
                </Button>
              </div>
              <div
                style={{
                  fontSize: 13,
                  color: COLORS.textMuted,
                  marginBottom: 16,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <span>{pagaModal.fornitore || pagaModal.descrizione}</span>
                {(pagaModal.tipo === 'FATTURA' || pagaModal.source === 'fattura') &&
                  (pagaModal.fattura_id || pagaModal.id) && (
                    <a
                      href={`/api/fatture-ricevute/fattura/${pagaModal.fattura_id || pagaModal.id}/view-assoinvoice`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        padding: '2px 8px',
                        background: COLORS.success,
                        color: 'white',
                        borderRadius: BORDER_RADIUS.sm,
                        fontSize: 10,
                        textDecoration: 'none',
                      }}
                      title="Visualizza PDF Fattura"
                    >
                      📄 Vedi
                    </a>
                  )}
              </div>
              <div
                style={{
                  fontSize: 24,
                  fontWeight: 700,
                  color: COLORS.primaryLight,
                  marginBottom: 20,
                  textAlign: 'center',
                }}
              >
                {pagaModal.importo > 0 ? `€ ${pagaModal.importo.toFixed(2)}` : '—'}
              </div>
              <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
                <Button
                  variant="warning"
                  size="lg"
                  disabled={processing}
                  onClick={() => handlePagaScadenza(pagaModal, 'cassa')}
                  style={{ flex: 1 }}
                >
                  🏪 Paga in CASSA
                </Button>
                <Button
                  variant="info"
                  size="lg"
                  disabled={processing}
                  onClick={() => handlePagaScadenza(pagaModal, 'banca')}
                  style={{ flex: 1 }}
                >
                  🏦 Paga in BANCA
                </Button>
              </div>
              <Button
                variant="secondary"
                onClick={() => setPagaModal(null)}
                style={{ width: '100%' }}
              >
                Annulla
              </Button>
            </div>
          </div>
        )}
      </div>
    </PageLayout>
  );
}

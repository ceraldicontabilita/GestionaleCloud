import React, { useEffect, useState } from 'react';
import { dashboardSummary, health } from '../api';
import api from '../api';
import { Link } from 'react-router-dom';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, STYLES, COLORS, SHADOWS, BORDER_RADIUS, useIsMobile } from '../lib/utils';
import { Button, Badge, StatCard, TableWrap, Table, Th, Td } from '../components/ds';
import { PageLayout } from '../components/PageLayout';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Legend,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { Eye, EyeOff, TrendingUp, Lock, AlertTriangle, Users } from 'lucide-react';
import WidgetVerificaCoerenza from '../components/WidgetVerificaCoerenza';
import WidgetAgenti from '../components/WidgetAgenti';

export default function Dashboard() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const [h, setH] = useState(null);
  const [sum, setSum] = useState(null);
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(true);
  const [trendData, setTrendData] = useState(null);
  const [posCalendario, setPosCalendario] = useState(null);
  const [scadenzeData, setScadenzeData] = useState(null);
  // Nuovi stati per grafici avanzati
  const [speseCategoria, setSpeseCategoria] = useState(null);
  const [confrontoAnnuale, setConfrontoAnnuale] = useState(null);
  const [statoRiconciliazione, setStatoRiconciliazione] = useState(null);
  // Stato per widget IRES/IRAP
  const [imposteData, setImposteData] = useState(null);
  // Volume Affari Reale
  const [showVolumeReale, setShowVolumeReale] = useState(false);
  const [volumeRealeData, setVolumeRealeData] = useState(null);
  const [volumeRealeLoading, setVolumeRealeLoading] = useState(false);
  // Bilancio Istantaneo
  const [bilancioIstantaneo, setBilancioIstantaneo] = useState(null);
  const [scadenzeF24, setScadenzeF24] = useState(null);

  // Alert Limiti Giustificativi

  // Alert Pagamenti (Stipendi + F24 DA_PAGARE)
  const [alertPagamenti, setAlertPagamenti] = useState(null);

  // Verbali e Trattenute
  const [verbaliStats, setVerbaliStats] = useState(null);

  // Stato per auto-riparazione
  const [autoRepairStatus, setAutoRepairStatus] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  // Stato per Learning Machine
  const [learningStats, setLearningStats] = useState(null);

  /**
   * LOGICA INTELLIGENTE: Esegue auto-riparazione dei dati.
   * Ora avviabile manualmente con pulsante.
   */
  const eseguiAutoRiparazione = async () => {
    setAutoRepairStatus('running');
    try {
      // Esegue riparazioni
      const [fatRes, ricRes] = await Promise.all([
        api.post('/api/fatture-ricevute/auto-ricostruisci-dati').catch(() => ({ data: {} })),
        api.post('/api/batch/auto-riconcilia-tutto').catch(() => ({ data: {} })),
      ]);

      const totaleCorrezioni =
        (fatRes.data.campi_corretti || 0) +
        (fatRes.data.fornitori_associati || 0) +
        (ricRes.data.riconciliazioni_auto || 0);

      
      setAutoRepairStatus({
        fatture: fatRes.data,
        riconciliazione: ricRes.data,
        totale: totaleCorrezioni,
      });

      // Ricarica dati dopo riparazione (senza reload pagina)
      setReloadKey(k => k + 1);
    } catch (error) {
      console.warn('Auto-riparazione non riuscita:', error);
      setAutoRepairStatus({ error: true, totale: 0 });
    }
  };

  // Auto-riparazione DISABILITATA per performance (eseguire manualmente se necessario)
  // useEffect(() => {
  //   eseguiAutoRiparazione();
  // }, []);

  useEffect(() => {
    // Timeout per evitare blocchi
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000); // 15s timeout

    (async () => {
      try {
        setLoading(true);
        const [healthData, summaryData] = await Promise.all([health(), dashboardSummary(anno)]);
        setH(healthData);
        setSum(summaryData);

        // Load trend mensile, calendario POS e scadenze - con timeout individuale
        const [trendRes, posRes, scadenzeRes, bilancioRes] = await Promise.all([
          api.get(`/api/dashboard/trend-mensile?anno=${anno}`).catch(() => ({ data: null })),
          api
            .get(`/api/pos-accredito/calendario-mensile/${anno}/${new Date().getMonth() + 1}`)
            .catch(() => ({ data: null })),
          api.get('/api/scadenze/prossime?giorni=30&limit=8').catch(() => ({ data: null })),
          api.get(`/api/dashboard/bilancio-istantaneo?anno=${anno}`).catch(() => ({ data: null })),
        ]);

        // Imposta dati primari immediatamente
        setTrendData(trendRes.data);
        setPosCalendario(posRes.data);
        setScadenzeData(scadenzeRes.data);
        setBilancioIstantaneo(bilancioRes.data);

        // Carica dati secondari DOPO i primari (non bloccanti)
        setLoading(false);

        // Grafici avanzati caricati in background (senza alert-limiti che è lento)
        Promise.all([
          api.get(`/api/dashboard/spese-per-categoria?anno=${anno}`).catch(() => ({ data: null })),
          api.get(`/api/dashboard/confronto-annuale?anno=${anno}`).catch(() => ({ data: null })),
          api
            .get(`/api/dashboard/stato-riconciliazione?anno=${anno}`)
            .catch(() => ({ data: null })),
          api
            .get(`/api/contabilita/calcolo-imposte?regione=campania&anno=${anno}`)
            .catch(() => ({ data: null })),
          api
            .get(`/api/f24-public/scadenze-prossime?giorni=60&limit=5`)
            .catch(() => ({ data: null })),
          api.get(`/api/fornitori-learning/stats`).catch(() => ({ data: null })),
          Promise.all([
            api
              .get('/api/paghe/buste-paga?stato=DA_PAGARE')
              .catch(() => ({ data: { data: [], count: 0 } })),
            api
              .get('/api/paghe/distinte-f24?stato=DA_PAGARE')
              .catch(() => ({ data: { data: [], count: 0 } })),
          ]).catch(() => null),
        ])
          .then(
            ([
              speseRes,
              confrontoRes,
              riconcRes,
              imposteRes,
              f24Res,
              learningRes,
              pagheResults,
            ]) => {
              setSpeseCategoria(speseRes.data);
              // Difesa sulla FORMA dei dati: se il backend risponde con un
              // payload vuoto/inatteso (riavvio, deploy in corso) i blocchi
              // che leggono i sotto-oggetti non devono mandare in crash la
              // pagina — meglio nascondere la card che mostrare l'errore rosso.
              const confronto = confrontoRes.data;
              setConfrontoAnnuale(
                confronto?.anno_corrente && confronto?.variazioni_percentuali ? confronto : null
              );
              const riconc = riconcRes.data;
              setStatoRiconciliazione(
                riconc && !Array.isArray(riconc) && (riconc.riepilogo || riconc.fatture)
                  ? riconc
                  : null
              );
              setImposteData(imposteRes.data);
              setScadenzeF24(f24Res.data);
              setLearningStats(learningRes.data);
              if (pagheResults) {
                const [busteRes, f24AlertRes] = pagheResults;
                const buste = busteRes.data?.data || [];
                const f24list = f24AlertRes.data?.data || [];
                const totStip = buste.reduce((s, b) => s + (b.netto_mese || 0), 0);
                const totF24 = f24list.reduce((s, f) => s + (f.riepilogo?.totale_generale || 0), 0);
                if (buste.length > 0 || f24list.length > 0) {
                  setAlertPagamenti({ buste, f24list, totStip, totF24 });
                }
              }
            }
          )
          .catch(e => console.warn('Errore grafici secondari:', e));

        // Carica stats verbali/trattenute
        api
          .get('/api/noleggio/veicoli?anno=' + anno)
          .then(r => {
            const veicoli = r.data?.veicoli || [];
            const stats = r.data?.statistiche || {};
            // Conta verbali totali dai veicoli
            const verbaliTot = veicoli.reduce((s, v) => s + (v.verbali?.length || 0), 0);
            // Carica trattenute
            api
              .get('/api/email-download/statistiche')
              .then(statRes => {
                const verbaliEmail = statRes.data?.verbale?.totale || 0;
                setVerbaliStats({
                  veicoli: veicoli.length,
                  canoni: stats.totale_canoni || 0,
                  verbali_costo: stats.totale_verbali || 0,
                  totale_noleggio: stats.totale_generale || 0,
                });
              })
              .catch(() => {});
          })
          .catch(() => {});

      } catch (e) {
        console.error('Dashboard error:', e);
        setErr('Backend non raggiungibile. Verifica che il server sia attivo.');
        setLoading(false);
      }
    })();

    return () => {
      clearTimeout(timeoutId);
      controller.abort();
    };
  }, [anno, reloadKey]);

  // Carica Volume Affari Reale quando toggle attivato
  async function loadVolumeReale() {
    if (volumeRealeData && volumeRealeData.anno === anno) return;
    setVolumeRealeLoading(true);
    try {
      const res = await api.get(`/api/gestione-riservata/volume-affari-reale?anno=${anno}`);
      setVolumeRealeData(res.data);
    } catch (e) {
      console.error('Errore caricamento volume reale:', e);
      setVolumeRealeData(null);
    } finally {
      setVolumeRealeLoading(false);
    }
  }

  function handleToggleVolumeReale() {
    const newValue = !showVolumeReale;
    setShowVolumeReale(newValue);
    if (newValue) {
      loadVolumeReale();
    }
  }

  if (loading) {
    return (
      <PageLayout title="Dashboard" icon="\u25A1" subtitle="Panoramica">
        <div style={STYLES.card}>
          <p style={{ color: COLORS.textMuted }}>Caricamento in corso...</p>
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout title={`Dashboard ${anno}`} icon="\u25A1" subtitle="Panoramica generale">
      <div style={{ ...STYLES.card, marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {/* Pulsante Auto-Riparazione */}
            <Button
              variant="primary"
              size="sm"
              onClick={eseguiAutoRiparazione}
              disabled={autoRepairStatus === 'running'}
              data-testid="btn-auto-repair"
            >
              {autoRepairStatus === 'running' ? <>Riparazione...</> : <>Auto-ripara dati</>}
            </Button>
            {autoRepairStatus && autoRepairStatus !== 'running' && autoRepairStatus.totale > 0 && (
              <Badge variant="success">{autoRepairStatus.totale} correzioni</Badge>
            )}
            {err ? (
              <span style={{ color: COLORS.danger, fontSize: 14 }}>{err}</span>
            ) : (
              <Badge variant="success">Backend connesso</Badge>
            )}
          </div>
        </div>
      </div>

      {/* Widget Verifica Coerenza Dati */}
      <WidgetVerificaCoerenza anno={anno} />
      <WidgetAgenti />

      {/* Alert Limiti Giustificativi */}

      {/* Alert Pagamenti DA_PAGARE (Stipendi + F24) */}
      {alertPagamenti && <AlertPagamentiWidget data={alertPagamenti} />}

      {/* Widget Scadenze */}
      {scadenzeData && scadenzeData.scadenze && scadenzeData.scadenze.length > 0 && (
        <ScadenzeWidget scadenze={scadenzeData} />
      )}

      {/* Toggle Volume Affari Reale - Compatto */}
      <div
        style={{
          background: showVolumeReale
            ? COLORS.primary
            : COLORS.bgAlt,
          borderRadius: BORDER_RADIUS.sm,
          padding: 8,
          marginBottom: 10,
          border: showVolumeReale ? 'none' : `1px dashed ${COLORS.border}`,
          transition: 'all 0.3s ease',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: showVolumeReale && volumeRealeData ? 8 : 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Lock size={12} color={showVolumeReale ? 'white' : COLORS.textMuted} />
            <span
              style={{
                fontWeight: 600,
                color: showVolumeReale ? 'white' : COLORS.gray[700],
                fontSize: 11,
              }}
            >
              Volume Affari
            </span>
          </div>
          <Button
            variant="primary"
            size="sm"
            onClick={handleToggleVolumeReale}
            data-testid="toggle-volume-reale"
            iconLeft={showVolumeReale ? <EyeOff size={10} /> : <Eye size={10} />}
            style={{
              padding: '3px 8px',
              fontSize: 10,
              gap: 3,
              background: showVolumeReale ? 'rgba(255,255,255,0.2)' : COLORS.primaryLight,
              borderColor: showVolumeReale ? 'rgba(255,255,255,0.2)' : COLORS.primaryLight,
            }}
          >
            {showVolumeReale ? 'Nascondi' : 'Mostra'}
          </Button>
        </div>

        {showVolumeReale && (
          <div>
            {volumeRealeLoading ? (
              <div style={{ color: 'rgba(255,255,255,0.7)', textAlign: 'center', padding: 20 }}>
                Caricamento...
              </div>
            ) : volumeRealeData ? (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)',
                  gap: 15,
                }}
              >
                <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: BORDER_RADIUS.md, padding: 16 }}>
                  <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12, marginBottom: 4 }}>
                    Fatturato Ufficiale
                  </div>
                  <div style={{ color: 'white', fontSize: 20, fontWeight: 700 }}>
                    {formatEuro(volumeRealeData.fatturato_ufficiale)}
                  </div>
                </div>
                <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: BORDER_RADIUS.md, padding: 16 }}>
                  <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12, marginBottom: 4 }}>
                    Corrispettivi
                  </div>
                  <div style={{ color: 'white', fontSize: 20, fontWeight: 700 }}>
                    {formatEuro(volumeRealeData.corrispettivi)}
                  </div>
                </div>
                <div style={{ background: 'rgba(16,185,129,0.3)', borderRadius: BORDER_RADIUS.md, padding: 16 }}>
                  <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12, marginBottom: 4 }}>
                    + Incassi Extra
                  </div>
                  <div style={{ color: '#34d399', fontSize: 20, fontWeight: 700 }}>
                    +{formatEuro(volumeRealeData.incassi_non_fatturati)}
                  </div>
                </div>
                <div style={{ background: 'rgba(239,68,68,0.3)', borderRadius: BORDER_RADIUS.md, padding: 16 }}>
                  <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12, marginBottom: 4 }}>
                    - Spese Extra
                  </div>
                  <div style={{ color: '#f87171', fontSize: 20, fontWeight: 700 }}>
                    -{formatEuro(volumeRealeData.spese_non_fatturate)}
                  </div>
                </div>
                <div
                  style={{
                    gridColumn: 'span 4',
                    background: COLORS.danger,
                    borderRadius: BORDER_RADIUS.md,
                    padding: 20,
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <div>
                    <div style={{ color: 'rgba(255,255,255,0.8)', fontSize: 14 }}>
                      VOLUME AFFARI REALE {anno}
                    </div>
                    <div
                      style={{
                        color: 'white',
                        fontSize: 32,
                        fontWeight: 700,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 10,
                      }}
                    >
                      <TrendingUp size={28} />
                      {formatEuro(volumeRealeData.volume_affari_reale)}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>
                      Ufficiale: {formatEuro(volumeRealeData.totale_ufficiale)}
                    </div>
                    <div
                      style={{
                        color: volumeRealeData.saldo_extra >= 0 ? '#34d399' : '#f87171',
                        fontSize: 14,
                        fontWeight: 600,
                      }}
                    >
                      {volumeRealeData.saldo_extra >= 0 ? '+' : ''}
                      {formatEuro(volumeRealeData.saldo_extra)} extra
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ color: 'rgba(255,255,255,0.7)', textAlign: 'center', padding: 20 }}>
                Nessun dato disponibile.{' '}
                <Link to="/gestione-riservata" style={{ color: '#e94560' }}>
                  Aggiungi movimenti
                </Link>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Widget Bilancio Istantaneo - COMPATTO */}
      {bilancioIstantaneo && (
        <div
          style={{
            background: COLORS.primary,
            borderRadius: BORDER_RADIUS.lg,
            padding: 14,
            marginTop: 12,
            color: 'white',
          }}
          data-testid="widget-bilancio-istantaneo"
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 10,
            }}
          >
            <h3
              style={{
                margin: 0,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                fontSize: 14,
                fontWeight: 600,
              }}
            >
              <TrendingUp size={18} /> Bilancio Istantaneo {anno}
            </h3>
            <span style={{ fontSize: 11, opacity: 0.7 }}>
              {bilancioIstantaneo.documenti?.fatture_ricevute || 0} fatt. •{' '}
              {bilancioIstantaneo.documenti?.corrispettivi || 0} corr.
            </span>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)',
              gap: 10,
            }}
          >
            <div
              style={{
                background: 'rgba(16,185,129,0.2)',
                borderRadius: BORDER_RADIUS.sm,
                padding: 10,
                borderLeft: `3px solid ${COLORS.success}`,
              }}
            >
              <div style={{ fontSize: 10, opacity: 0.8 }}>RICAVI</div>
              <div style={{ fontSize: 16, fontWeight: 700 }}>
                {formatEuro(bilancioIstantaneo.ricavi?.totale || 0)}
              </div>
            </div>
            <div
              style={{
                background: 'rgba(239,68,68,0.2)',
                borderRadius: BORDER_RADIUS.sm,
                padding: 10,
                borderLeft: `3px solid ${COLORS.danger}`,
              }}
            >
              <div style={{ fontSize: 10, opacity: 0.8 }}>COSTI</div>
              <div style={{ fontSize: 16, fontWeight: 700 }}>
                {formatEuro(bilancioIstantaneo.costi?.totale || 0)}
              </div>
            </div>
            <div
              style={{
                background: 'rgba(59,130,246,0.2)',
                borderRadius: BORDER_RADIUS.sm,
                padding: 10,
                borderLeft: `3px solid ${COLORS.info}`,
              }}
            >
              <div style={{ fontSize: 10, opacity: 0.8 }}>SALDO IVA</div>
              <div
                style={{
                  fontSize: 16,
                  fontWeight: 700,
                  color: (bilancioIstantaneo.iva?.saldo || 0) >= 0 ? '#f87171' : '#34d399',
                }}
              >
                {formatEuro(bilancioIstantaneo.iva?.saldo || 0)}
              </div>
            </div>
            <div
              style={{
                background:
                  (bilancioIstantaneo.bilancio?.utile_lordo || 0) >= 0
                    ? 'rgba(16,185,129,0.3)'
                    : 'rgba(239,68,68,0.3)',
                borderRadius: BORDER_RADIUS.sm,
                padding: 10,
                borderLeft: `3px solid ${(bilancioIstantaneo.bilancio?.utile_lordo || 0) >= 0 ? COLORS.success : COLORS.danger}`,
              }}
            >
              <div style={{ fontSize: 10, opacity: 0.8 }}>UTILE LORDO</div>
              <div
                style={{
                  fontSize: 16,
                  fontWeight: 700,
                  color:
                    (bilancioIstantaneo.bilancio?.utile_lordo || 0) >= 0 ? '#34d399' : '#f87171',
                }}
              >
                {formatEuro(bilancioIstantaneo.bilancio?.utile_lordo || 0)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Widget IRES/IRAP - COMPATTO */}
      {imposteData && (
        <div
          style={{
            borderRadius: BORDER_RADIUS.lg,
            padding: 14,
            boxShadow: SHADOWS.sm,
            marginTop: 12,
            background: COLORS.primary,
            color: 'white',
          }}
          data-testid="widget-calcolo-imposte"
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 10,
            }}
          >
            <div
              style={{
                fontSize: 14,
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              Imposte {anno}{' '}
              <span style={{ fontSize: 10, opacity: 0.7, fontWeight: 400 }}>
                IRAP {imposteData.irap?.aliquota}%
              </span>
            </div>
            <Link
              to="/contabilita"
              style={{
                padding: '4px 10px',
                background: 'rgba(255,255,255,0.2)',
                color: 'white',
                borderRadius: BORDER_RADIUS.sm,
                textDecoration: 'none',
                fontSize: 11,
              }}
            >
              Dettaglio
            </Link>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)',
              gap: 10,
            }}
          >
            <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: BORDER_RADIUS.sm, padding: 10 }}>
              <div style={{ fontSize: 10, opacity: 0.8 }}>Utile</div>
              <div style={{ fontSize: 16, fontWeight: 'bold' }}>
                {formatEuro(imposteData.utile_civilistico)}
              </div>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: BORDER_RADIUS.sm, padding: 10 }}>
              <div style={{ fontSize: 10, opacity: 0.8 }}>IRES (24%)</div>
              <div style={{ fontSize: 16, fontWeight: 'bold', color: '#fbbf24' }}>
                {formatEuro(imposteData.ires?.imposta_dovuta)}
              </div>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: BORDER_RADIUS.sm, padding: 10 }}>
              <div style={{ fontSize: 10, opacity: 0.8 }}>IRAP</div>
              <div style={{ fontSize: 16, fontWeight: 'bold', color: '#a78bfa' }}>
                {formatEuro(imposteData.irap?.imposta_dovuta)}
              </div>
            </div>
            <div style={{ background: 'rgba(239,68,68,0.3)', borderRadius: BORDER_RADIUS.sm, padding: 10 }}>
              <div style={{ fontSize: 10, opacity: 0.8 }}>TOTALE</div>
              <div style={{ fontSize: 16, fontWeight: 'bold' }}>
                {formatEuro(imposteData.totale_imposte)}
              </div>
            </div>
          </div>

          {/* Variazioni fiscali sintesi */}
          {(imposteData.ires?.totale_variazioni_aumento > 0 ||
            imposteData.ires?.totale_variazioni_diminuzione > 0) && (
            <div
              style={{
                marginTop: 15,
                padding: 12,
                background: 'rgba(255,255,255,0.05)',
                borderRadius: BORDER_RADIUS.md,
                display: 'flex',
                gap: 20,
                fontSize: 13,
              }}
            >
              <div>
                <span style={{ opacity: 0.7 }}>Variazioni aumento: </span>
                <span style={{ color: '#fca5a5' }}>
                  {formatEuro(imposteData.ires?.totale_variazioni_aumento)}
                </span>
              </div>
              <div>
                <span style={{ opacity: 0.7 }}>Variazioni diminuzione: </span>
                <span style={{ color: '#86efac' }}>
                  {formatEuro(imposteData.ires?.totale_variazioni_diminuzione)}
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      {scadenzeF24 && scadenzeF24.scadenze && scadenzeF24.scadenze.length > 0 && (
        <div
          style={{
            background: COLORS.card,
            borderRadius: BORDER_RADIUS.lg,
            padding: 14,
            marginTop: 12,
            border: `1px solid ${COLORS.border}`,
            boxShadow: SHADOWS.sm,
          }}
          data-testid="widget-scadenze-f24"
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 10,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 16 }}>📋</span>
              <span style={{ fontSize: 16 }}>F24</span>
              <Badge variant="danger" style={{ fontSize: 10, padding: '2px 6px', borderRadius: BORDER_RADIUS.sm }}>
                {scadenzeF24.totale || scadenzeF24.scadenze.length}
              </Badge>
            </div>
            <Link to="/riconciliazione/f24" style={{ fontSize: 11, color: COLORS.info, textDecoration: 'none' }}>
              Vedi tutti
            </Link>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {(scadenzeF24?.scadenze ?? []).slice(0, 4).map((f24, idx) => {
              const isUrgente = f24.giorni_mancanti <= 7;
              const isScaduto = f24.giorni_mancanti < 0;
              return (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 10px',
                    background: isScaduto ? COLORS.dangerLight : isUrgente ? COLORS.warningLight : COLORS.bgAlt,
                    borderRadius: BORDER_RADIUS.sm,
                    borderLeft: `3px solid ${isScaduto ? COLORS.danger : isUrgente ? COLORS.warning : COLORS.info}`,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
                    <span style={{ fontSize: 14 }}>{f24.tipo === 'IVA' ? '🧾' : '📋'}</span>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: COLORS.text }}>
                        {f24.descrizione || f24.tipo || 'F24'}
                      </div>
                      <div style={{ fontSize: 10, color: COLORS.textMuted }}>
                        {f24.tributo || f24.codice_tributo || ''}
                      </div>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: COLORS.danger }}>
                      {formatEuro(f24.importo)}
                    </div>
                    <div
                      style={{
                        fontSize: 10,
                        color: isScaduto ? COLORS.danger : isUrgente ? COLORS.warning : COLORS.textMuted,
                      }}
                    >
                      {isScaduto
                        ? 'Scaduto'
                        : f24.giorni_mancanti === 0
                          ? 'Oggi'
                          : f24.giorni_mancanti === 1
                            ? 'Domani'
                            : `${f24.giorni_mancanti}g`}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {scadenzeF24.totale_importo > 0 && (
            <div
              style={{
                marginTop: 10,
                paddingTop: 10,
                borderTop: `1px solid ${COLORS.border}`,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <span style={{ fontSize: 11, color: COLORS.textMuted }}>Totale da versare</span>
              <span style={{ fontSize: 14, fontWeight: 700, color: COLORS.danger }}>
                {formatEuro(scadenzeF24.totale_importo)}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Widget Noleggio Auto & Verbali */}
      {verbaliStats && (
        <div
          style={{
            background: COLORS.card,
            borderRadius: BORDER_RADIUS.xl,
            padding: 20,
            boxShadow: SHADOWS.md,
            marginTop: 20,
            border: `1px solid ${COLORS.border}`,
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 24 }}>🚗</span>
              <div>
                <div style={{ fontWeight: 'bold', fontSize: 16, color: COLORS.primaryLight }}>
                  Noleggio Auto
                </div>
                <div style={{ fontSize: 12, color: COLORS.textMuted }}>
                  {verbaliStats.veicoli} veicoli in flotta
                </div>
              </div>
            </div>
            <Link to="/noleggio" style={{ fontSize: 13, color: COLORS.info, textDecoration: 'none' }}>
              Gestisci →
            </Link>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: 10,
            }}
          >
            <StatCard label="Canoni" value={formatEuro(verbaliStats.canoni)} accent="info" />
            <StatCard label="Verbali/Multe" value={formatEuro(verbaliStats.verbali_costo)} accent="danger" />
            <StatCard label="Totale Noleggio" value={formatEuro(verbaliStats.totale_noleggio)} accent="success" />
          </div>
        </div>
      )}

      {trendData && (
        <div
          style={{
            background: COLORS.card,
            borderRadius: BORDER_RADIUS.xl,
            padding: 20,
            boxShadow: SHADOWS.md,
            marginTop: 20,
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 20,
            }}
          >
            <div>
              <h2 style={{ fontSize: 18, margin: 0, fontWeight: 'bold', color: COLORS.primaryLight }}>
                Trend Mensile {anno}
              </h2>
              <span style={{ fontSize: 13, color: COLORS.textMuted }}>Entrate vs Uscite</span>
            </div>
            <div style={{ display: 'flex', gap: 20, fontSize: 14 }}>
              <div>
                <span style={{ color: COLORS.success }}>Entrate:</span>{' '}
                <strong>{formatEuro(trendData.totali?.entrate)}</strong>
              </div>
              <div>
                <span style={{ color: COLORS.danger }}>Uscite:</span>{' '}
                <strong>{formatEuro(trendData.totali?.uscite)}</strong>
              </div>
              <div>
                <span style={{ color: trendData.totali?.saldo >= 0 ? COLORS.success : COLORS.danger }}>
                  Saldo:
                </span>{' '}
                <strong style={{ color: trendData.totali?.saldo >= 0 ? COLORS.success : COLORS.danger }}>
                  {formatEuro(trendData.totali?.saldo)}
                </strong>
              </div>
            </div>
          </div>

          <div style={{ height: 300, width: '100%', minHeight: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={trendData.trend_mensile}
                margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                <XAxis dataKey="mese_nome" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={v => `€${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11 }} />
                <Tooltip
                  formatter={value => formatEuro(value)}
                  labelStyle={{ fontWeight: 'bold' }}
                  contentStyle={{ borderRadius: BORDER_RADIUS.md, border: `1px solid ${COLORS.border}` }}
                />
                <Legend />
                <Bar dataKey="entrate" fill={COLORS.success} name="Entrate" radius={[4, 4, 0, 0]} />
                <Bar dataKey="uscite" fill={COLORS.danger} name="Uscite" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Statistiche */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
              gap: 15,
              marginTop: 20,
              padding: 15,
              background: COLORS.bgAlt,
              borderRadius: BORDER_RADIUS.md,
            }}
          >
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: COLORS.textMuted }}>Media Entrate</div>
              <div style={{ fontSize: 18, fontWeight: 'bold', color: COLORS.success }}>
                {formatEuro(trendData.statistiche?.media_entrate_mensile)}
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: COLORS.textMuted }}>Media Uscite</div>
              <div style={{ fontSize: 18, fontWeight: 'bold', color: COLORS.danger }}>
                {formatEuro(trendData.statistiche?.media_uscite_mensile)}
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: COLORS.textMuted }}>Picco Entrate</div>
              <div style={{ fontSize: 18, fontWeight: 'bold' }}>
                {trendData.statistiche?.mese_picco_entrate}
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: COLORS.textMuted }}>Picco Uscite</div>
              <div style={{ fontSize: 18, fontWeight: 'bold' }}>
                {trendData.statistiche?.mese_picco_uscite}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* IVA Trend Chart */}
      {trendData && (
        <div
          style={{
            background: COLORS.card,
            borderRadius: BORDER_RADIUS.xl,
            padding: 20,
            boxShadow: SHADOWS.md,
            marginTop: 20,
          }}
        >
          <h2 style={{ fontSize: 18, margin: '0 0 15px 0', fontWeight: 'bold', color: COLORS.primaryLight }}>
            Trend IVA {anno}
          </h2>
          <div style={{ height: 200, width: '100%', minHeight: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={trendData.trend_mensile}
                margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                <XAxis dataKey="mese_nome" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={v => `€${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11 }} />
                <Tooltip
                  formatter={value => formatEuro(value)}
                  contentStyle={{ borderRadius: BORDER_RADIUS.md }}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="iva_debito"
                  stroke={COLORS.warning}
                  strokeWidth={2}
                  name="IVA Debito"
                  dot={{ r: 3 }}
                />
                <Line
                  type="monotone"
                  dataKey="iva_credito"
                  stroke={COLORS.info}
                  strokeWidth={2}
                  name="IVA Credito"
                  dot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'center',
              gap: 30,
              marginTop: 15,
              fontSize: 14,
            }}
          >
            <div>
              IVA Debito Totale:{' '}
              <strong style={{ color: COLORS.warning }}>
                {formatEuro(trendData.totali?.iva_debito)}
              </strong>
            </div>
            <div>
              IVA Credito Totale:{' '}
              <strong style={{ color: COLORS.info }}>
                {formatEuro(trendData.totali?.iva_credito)}
              </strong>
            </div>
            <div>
              Saldo IVA:{' '}
              <strong style={{ color: trendData.totali?.saldo_iva >= 0 ? COLORS.danger : COLORS.success }}>
                {formatEuro(Math.abs(trendData.totali?.saldo_iva))}{' '}
                {trendData.totali?.saldo_iva >= 0 ? '(da versare)' : '(a credito)'}
              </strong>
            </div>
          </div>
        </div>
      )}

      {/* Nuova sezione: Grafici Avanzati */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 400px), 1fr))',
          gap: 20,
          marginTop: 20,
        }}
      >
        {/* Grafico a Torta - Spese per Categoria */}
        {speseCategoria && speseCategoria.categorie && speseCategoria.categorie.length > 0 && (
          <div
            style={{
              background: COLORS.card,
              borderRadius: BORDER_RADIUS.xl,
              padding: 20,
              boxShadow: SHADOWS.md,
            }}
          >
            <h2
              style={{ fontSize: 18, margin: '0 0 15px 0', fontWeight: 'bold', color: COLORS.primaryLight }}
            >
              Distribuzione Spese {anno}
            </h2>
            <div style={{ height: 280, display: 'flex', alignItems: 'center', minHeight: 280 }}>
              <ResponsiveContainer width="60%" height="100%">
                <PieChart>
                  <Pie
                    data={speseCategoria.categorie}
                    dataKey="valore"
                    nameKey="nome"
                    cx="50%"
                    cy="50%"
                    outerRadius={90}
                    label={({ percentuale }) => `${percentuale}%`}
                    labelLine={false}
                  >
                    {(speseCategoria?.categorie ?? []).map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={value => formatEuro(value)} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ width: '40%', fontSize: 11, maxHeight: 250, overflow: 'auto' }}>
                {(speseCategoria?.categorie ?? []).slice(0, 6).map((cat, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      marginBottom: 8,
                      padding: '4px 8px',
                      background: COLORS.bgAlt,
                      borderRadius: BORDER_RADIUS.sm,
                    }}
                  >
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: 2,
                        background: PIE_COLORS[idx % PIE_COLORS.length],
                        flexShrink: 0,
                      }}
                    ></span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div
                        style={{
                          fontWeight: 500,
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {cat.nome}
                      </div>
                      <div style={{ color: COLORS.textMuted }}>{formatEuro(cat.valore)}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div
              style={{
                textAlign: 'center',
                marginTop: 10,
                padding: 10,
                background: COLORS.successLight,
                borderRadius: BORDER_RADIUS.md,
              }}
            >
              <span style={{ color: COLORS.textMuted }}>Totale Spese: </span>
              <strong style={{ color: COLORS.danger }}>
                {formatEuro(speseCategoria.totale_spese)}
              </strong>
            </div>
          </div>
        )}

        {statoRiconciliazione && (
          <div
            style={{
              background: COLORS.card,
              borderRadius: BORDER_RADIUS.xl,
              padding: 20,
              boxShadow: SHADOWS.md,
            }}
          >
            <h2
              style={{ fontSize: 18, margin: '0 0 15px 0', fontWeight: 'bold', color: COLORS.primaryLight }}
            >
              Stato Riconciliazione {anno}
            </h2>

            {/* Barra progresso globale */}
            <div style={{ marginBottom: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <span style={{ fontSize: 13, color: COLORS.textMuted }}>Progresso Globale</span>
                <span
                  style={{
                    fontWeight: 'bold',
                    color:
                      (statoRiconciliazione?.riepilogo?.percentuale_globale ?? 0) >= 80
                        ? COLORS.success
                        : COLORS.warning,
                  }}
                >
                  {(statoRiconciliazione?.riepilogo?.percentuale_globale ?? 0)}%
                </span>
              </div>
              <div
                style={{ height: 12, background: COLORS.border, borderRadius: BORDER_RADIUS.sm, overflow: 'hidden' }}
              >
                <div
                  style={{
                    height: '100%',
                    width: `${(statoRiconciliazione?.riepilogo?.percentuale_globale ?? 0)}%`,
                    background:
                      (statoRiconciliazione?.riepilogo?.percentuale_globale ?? 0) >= 80
                        ? COLORS.success
                        : COLORS.warning,
                    borderRadius: BORDER_RADIUS.sm,
                    transition: 'width 0.5s ease',
                  }}
                ></div>
              </div>
            </div>

            <div style={{ background: COLORS.bgAlt, borderRadius: BORDER_RADIUS.md, padding: 12, marginBottom: 12 }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 8,
                }}
              >
                Fatture Fornitori
                <Badge variant={(statoRiconciliazione?.fatture?.percentuale_pagate ?? 0) >= 80 ? 'success' : 'warning'}>
                  {(statoRiconciliazione?.fatture?.percentuale_pagate ?? 0)}%
                </Badge>
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                  gap: 10,
                  fontSize: 13,
                }}
              >
                <div>
                  <div style={{ color: COLORS.textMuted }}>Pagate</div>
                  <div style={{ fontWeight: 'bold', color: COLORS.success }}>
                    {(statoRiconciliazione?.fatture?.pagate ?? 0)} / {(statoRiconciliazione?.fatture?.totali ?? 0)}
                  </div>
                </div>
                <div>
                  <div style={{ color: COLORS.textMuted }}>Da pagare</div>
                  <div style={{ fontWeight: 'bold', color: COLORS.danger }}>
                    {formatEuro(statoRiconciliazione?.fatture?.importo_da_pagare ?? 0)}
                  </div>
                </div>
              </div>
            </div>

            <div style={{ background: COLORS.bgAlt, borderRadius: BORDER_RADIUS.md, padding: 12 }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 8,
                }}
              >
                <span style={{ fontWeight: 600 }}>Salari Dipendenti</span>
                <Badge variant={(statoRiconciliazione?.salari?.percentuale_riconciliati ?? 0) >= 80 ? 'success' : 'warning'}>
                  {(statoRiconciliazione?.salari?.percentuale_riconciliati ?? 0)}%
                </Badge>
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                  gap: 10,
                  fontSize: 13,
                }}
              >
                <div>
                  <div style={{ color: COLORS.textMuted }}>Riconciliati</div>
                  <div style={{ fontWeight: 'bold', color: COLORS.success }}>
                    {(statoRiconciliazione?.salari?.riconciliati ?? 0)} /{' '}
                    {(statoRiconciliazione?.salari?.totali ?? 0)}
                  </div>
                </div>
                <div>
                  <div style={{ color: COLORS.textMuted }}>Da verificare</div>
                  <div style={{ fontWeight: 'bold', color: COLORS.warning }}>
                    {statoRiconciliazione?.salari?.da_riconciliare ?? 0}
                  </div>
                </div>
              </div>
            </div>

            <Link
              to="/riconciliazione"
              style={{
                display: 'block',
                marginTop: 15,
                padding: '10px 16px',
                background: COLORS.info,
                color: 'white',
                borderRadius: BORDER_RADIUS.md,
                textAlign: 'center',
                textDecoration: 'none',
                fontWeight: 'bold',
                fontSize: 13,
              }}
            >
              Vai a Riconciliazione
            </Link>
          </div>
        )}

        {/* Widget Learning Machine */}
        {learningStats && (
          <div
            style={{
              background: COLORS.bgAlt,
              borderRadius: BORDER_RADIUS.xl,
              padding: 20,
              boxShadow: SHADOWS.md,
              border: `1px solid ${COLORS.successLight}`,
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: 15,
              }}
            >
              <h3 style={{ fontSize: 16, margin: 0, fontWeight: 'bold', color: COLORS.success }}>
                🧠 Learning Machine
              </h3>
              <Badge variant="success">ATTIVA</Badge>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)',
                gap: 12,
              }}
            >
              <StatCard
                label="Fornitori"
                value={learningStats.fornitori_con_keywords || 0}
                subtext={`${learningStats.copertura_fornitori || 0}% copertura`}
                accent="success"
              />
              <StatCard
                label="Fatture"
                value={`${learningStats.percentuale_fatture || 0}%`}
                subtext={`${learningStats.fatture_classificate || 0}/${learningStats.totale_fatture || 0}`}
                accent="success"
              />
              <StatCard
                label="F24"
                value={`${learningStats.percentuale_f24 || 0}%`}
                subtext={`${learningStats.f24_classificati || 0}/${learningStats.totale_f24 || 0}`}
                accent="success"
              />
            </div>

            <Link
              to="/learning-machine"
              style={{
                display: 'block',
                marginTop: 12,
                padding: '8px 14px',
                background: COLORS.success,
                color: 'white',
                borderRadius: BORDER_RADIUS.md,
                textAlign: 'center',
                textDecoration: 'none',
                fontWeight: 'bold',
                fontSize: 12,
              }}
            >
              Gestisci Learning Machine
            </Link>
          </div>
        )}
      </div>

      {/* Confronto Anno Precedente */}
      {confrontoAnnuale && (
        <div
          style={{
            background: COLORS.card,
            borderRadius: BORDER_RADIUS.xl,
            padding: 20,
            boxShadow: SHADOWS.md,
            marginTop: 20,
          }}
        >
          <h2 style={{ fontSize: 18, margin: '0 0 15px 0', fontWeight: 'bold', color: COLORS.primaryLight }}>
            Confronto {anno} vs {anno - 1}
          </h2>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: 15,
            }}
          >
            <StatCard
              label="Entrate"
              value={formatEuro(confrontoAnnuale.anno_corrente.entrate)}
              accent="success"
              subtext={
                <>
                  <span
                    style={{
                      color: confrontoAnnuale.variazioni_percentuali.entrate >= 0 ? COLORS.success : COLORS.danger,
                      fontWeight: 'bold',
                    }}
                  >
                    {confrontoAnnuale.variazioni_percentuali.entrate >= 0 ? '↑' : '↓'}
                    {Math.abs(confrontoAnnuale.variazioni_percentuali.entrate)}%
                  </span>{' '}
                  vs {anno - 1}
                </>
              }
            />

            <StatCard
              label="Uscite"
              value={formatEuro(confrontoAnnuale.anno_corrente.uscite)}
              accent="danger"
              subtext={
                <>
                  <span
                    style={{
                      color: confrontoAnnuale.variazioni_percentuali.uscite <= 0 ? COLORS.success : COLORS.danger,
                      fontWeight: 'bold',
                    }}
                  >
                    {confrontoAnnuale.variazioni_percentuali.uscite >= 0 ? '↑' : '↓'}
                    {Math.abs(confrontoAnnuale.variazioni_percentuali.uscite)}%
                  </span>{' '}
                  vs {anno - 1}
                </>
              }
            />

            <StatCard
              label="Saldo"
              value={formatEuro(confrontoAnnuale.anno_corrente.saldo)}
              accent={confrontoAnnuale.anno_corrente.saldo >= 0 ? 'success' : 'danger'}
              subtext={
                <>
                  <span
                    style={{
                      color: confrontoAnnuale.variazioni_percentuali.saldo >= 0 ? COLORS.success : COLORS.danger,
                      fontWeight: 'bold',
                    }}
                  >
                    {confrontoAnnuale.variazioni_percentuali.saldo >= 0 ? '↑' : '↓'}
                    {Math.abs(confrontoAnnuale.variazioni_percentuali.saldo)}%
                  </span>{' '}
                  vs {anno - 1}
                </>
              }
            />

            <StatCard
              label="N. Fatture"
              value={confrontoAnnuale.anno_corrente.num_fatture}
              accent="info"
              subtext={
                <>
                  <span style={{ color: COLORS.textMuted, fontWeight: 'bold' }}>
                    {confrontoAnnuale.variazioni_percentuali.num_fatture >= 0 ? '↑' : '↓'}
                    {Math.abs(confrontoAnnuale.variazioni_percentuali.num_fatture)}%
                  </span>{' '}
                  vs {anno - 1}
                </>
              }
            />
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div
        style={{
          background: COLORS.card,
          borderRadius: BORDER_RADIUS.xl,
          padding: 20,
          boxShadow: SHADOWS.md,
          marginTop: 20,
        }}
      >
        <h2 style={{ fontSize: 18, margin: '0 0 4px 0', fontWeight: 'bold', color: COLORS.primaryLight }}>
          Azioni Rapide
        </h2>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 15,
            marginTop: 15,
          }}
        >
          <Link to="/contabilita" style={quickActionStyle('#e0f2fe', '#0369a1')}>
            <span style={{ fontSize: 20 }}>🧮</span>
            <span>IRES/IRAP</span>
          </Link>
          <Link to="/regole-categorizzazione" style={quickActionStyle('#fef3c7', '#b45309')}>
            <span style={{ fontSize: 20 }}>⚙️</span>
            <span>Regole Categorie</span>
          </Link>
          <Link to="/import-export" style={quickActionStyle('#e3f2fd', '#1565c0')}>
            <span style={{ fontSize: 20 }}>📤</span>
            <span>Import/Export</span>
          </Link>
          <Link to="/bilancio" style={quickActionStyle('#f3e5f5', '#7b1fa2')}>
            <span style={{ fontSize: 20 }}>📊</span>
            <span>Bilancio</span>
          </Link>
          <Link to="/controllo-mensile" style={quickActionStyle('#e8f5e9', '#2e7d32')}>
            <span style={{ fontSize: 20 }}>📈</span>
            <span>Controllo Mensile</span>
          </Link>
          <Link to="/riconciliazione/f24" style={quickActionStyle('#fff3e0', '#e65100')}>
            <span style={{ fontSize: 20 }}>📋</span>
            <span>F24 / Tributi</span>
          </Link>
          <Link to="/commercialista" style={quickActionStyle('#fce4ec', '#c2185b')}>
            <span style={{ fontSize: 20 }}>📁</span>
            <span>Commercialista</span>
          </Link>
        </div>

        {/* Report PDF Section */}
        <div style={{ marginTop: 20, paddingTop: 20, borderTop: `1px solid ${COLORS.border}` }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: COLORS.gray[600] }}>
            📄 Scarica Report PDF
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <a
              href={`/api/contabilita/export/pdf-dichiarazione?anno=${anno}&regione=campania`}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                padding: '8px 14px',
                background: COLORS.danger,
                color: 'white',
                borderRadius: BORDER_RADIUS.sm,
                textDecoration: 'none',
                fontSize: 13,
                fontWeight: 500,
              }}
            >
            Dichiarazione IRES/IRAP
            </a>
            <a
              href={`/api/report-pdf/mensile?anno=${anno}&mese=${new Date().getMonth() + 1}`}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                padding: '8px 14px',
                background: COLORS.info,
                color: 'white',
                borderRadius: BORDER_RADIUS.sm,
                textDecoration: 'none',
                fontSize: 13,
                fontWeight: 500,
              }}
            >
            Report Mensile
            </a>
            <a
              href="/api/report-pdf/scadenze?giorni=30"
              target="_blank"
              rel="noopener noreferrer"
              style={{
                padding: '8px 14px',
                background: COLORS.danger,
                color: 'white',
                borderRadius: BORDER_RADIUS.sm,
                textDecoration: 'none',
                fontSize: 13,
                fontWeight: 500,
              }}
            >
            Report Scadenze
            </a>
            <a
              href="/api/report-pdf/magazzino"
              target="_blank"
              rel="noopener noreferrer"
              style={{
                padding: '8px 14px',
                background: COLORS.success,
                color: 'white',
                borderRadius: BORDER_RADIUS.sm,
                textDecoration: 'none',
                fontSize: 13,
                fontWeight: 500,
              }}
            >
            Report Magazzino
            </a>
          </div>
        </div>
      </div>
    </PageLayout>
  );
}

// Style helper
const quickActionStyle = (bg, color) => ({
  padding: 15,
  background: bg,
  borderRadius: BORDER_RADIUS.md,
  textDecoration: 'none',
  color: color,
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  transition: 'transform 0.2s',
});

// Colori per grafico a torta
const PIE_COLORS = [
  '#3b82f6',
  '#10b981',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#ec4899',
  '#06b6d4',
  '#84cc16',
  '#f97316',
  '#6366f1',
];

// POS Calendar Widget Component
function POSCalendarWidget({ data }) {
  if (!data || !data.giorni) return null;

  const mesiNomi = [
    '',
    'Gennaio',
    'Febbraio',
    'Marzo',
    'Aprile',
    'Maggio',
    'Giugno',
    'Luglio',
    'Agosto',
    'Settembre',
    'Ottobre',
    'Novembre',
    'Dicembre',
  ];
  const giorniSettimana = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom'];

  // Trova il primo giorno del mese
  const primoGiorno = new Date(data.giorni[0].data_pagamento);
  const offsetInizio = (primoGiorno.getDay() + 6) % 7; // Lunedì = 0

  // Prepara griglia calendario
  const settimane = [];
  let settimanaCorrente = new Array(offsetInizio).fill(null);

  data.giorni.forEach((g, idx) => {
    const sfasamento = g.giorni_sfasamento;
    const isFestivo = data.festivi?.includes(g.data_pagamento);

    settimanaCorrente.push({
      ...g,
      giorno: idx + 1,
      sfasamento,
      isFestivo,
    });

    if (settimanaCorrente.length === 7) {
      settimane.push(settimanaCorrente);
      settimanaCorrente = [];
    }
  });

  if (settimanaCorrente.length > 0) {
    while (settimanaCorrente.length < 7) settimanaCorrente.push(null);
    settimane.push(settimanaCorrente);
  }

  const getColor = (sfasamento, isFestivo) => {
    if (isFestivo) return COLORS.dangerLight;
    if (sfasamento === 1) return COLORS.successLight;
    if (sfasamento === 2) return COLORS.warningLight;
    if (sfasamento >= 3) return COLORS.dangerLight;
    return COLORS.bgAlt;
  };

  return (
    <div>
      <div style={{ textAlign: 'center', fontWeight: 'bold', marginBottom: 10 }}>
        {mesiNomi[data.mese]} {data.anno}
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(7, 1fr)',
          gap: 4,
          fontSize: 12,
        }}
      >
        {/* Header */}
        {giorniSettimana.map(g => (
          <div
            key={g}
            style={{
              textAlign: 'center',
              fontWeight: 'bold',
              padding: 6,
              color: g === 'Sab' || g === 'Dom' ? COLORS.danger : COLORS.gray[700],
            }}
          >
            {g}
          </div>
        ))}

        {/* Giorni */}
        {settimane.flat().map((g, idx) => (
          <div
            key={idx}
            style={{
              textAlign: 'center',
              padding: '8px 4px',
              background: g ? getColor(g.sfasamento, g.isFestivo) : 'transparent',
              borderRadius: BORDER_RADIUS.sm,
              cursor: g ? 'pointer' : 'default',
              position: 'relative',
            }}
            title={
              g
                ? `${g.giorno_settimana_pagamento}: Accredito in ${g.giorni_sfasamento} giorni\n${g.note}`
                : ''
            }
          >
            {g && (
              <>
                <div style={{ fontWeight: '500' }}>{g.giorno}</div>
                <div style={{ fontSize: 9, color: COLORS.textMuted }}>+{g.sfasamento}g</div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// Widget Alert Limiti Giustificativi
// Widget Scadenze Component
function ScadenzeWidget({ scadenze }) {
  const [pagaModal, setPagaModal] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [paidIds, setPaidIds] = useState(new Set()); // Track locally paid items

  if (!scadenze || !scadenze.scadenze || scadenze.scadenze.length === 0) return null;

  // Filter out locally paid items immediately
  const visibleScadenze = scadenze.scadenze.filter(s => !paidIds.has(s.id));
  const urgenti = visibleScadenze.filter(s => s.urgente);

  const getPriorityColor = (priorita, urgente) => {
    if (urgente) return { bg: COLORS.dangerLight, border: COLORS.danger, text: COLORS.danger };
    switch (priorita) {
      case 'critica':
        return { bg: COLORS.dangerLight, border: COLORS.danger, text: COLORS.danger };
      case 'alta':
        return { bg: COLORS.accentSoft, border: COLORS.accent, text: COLORS.accent };
      case 'media':
        return { bg: COLORS.warningLight, border: COLORS.warning, text: COLORS.warning };
      default:
        return { bg: COLORS.successLight, border: COLORS.success, text: COLORS.success };
    }
  };

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
      default:
        return '📌';
    }
  };

  const formatDate = dateStr => {
    if (!dateStr) return '-';
    const d = new Date(dateStr);
    return d.toLocaleDateString('it-IT', { day: '2-digit', month: 'short' });
  };

  const handlePaga = async (scadenza, metodo) => {
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
      // Rimuovi immediatamente dalla lista locale — nessun reload
      setPaidIds(prev => new Set([...prev, scadenza.id]));
    } catch (e) {
      alert('Errore pagamento: ' + (e.response?.data?.detail || e.message));
    } finally {
      setProcessing(false);
    }
  };

  if (visibleScadenze.length === 0) return null;

  return (
    <div
      style={{
        background: COLORS.card,
        borderRadius: BORDER_RADIUS.xl,
        padding: 20,
        marginBottom: 20,
        border: urgenti.length > 0 ? `2px solid ${COLORS.danger}` : `1px solid ${COLORS.border}`,
        boxShadow: SHADOWS.sm,
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 15,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 24 }}>📅</span>
          <div>
            <div style={{ fontWeight: 'bold', fontSize: 16 }}>Prossime Scadenze</div>
            <div style={{ fontSize: 12, color: COLORS.textMuted }}>
              {scadenze.totale} scadenze nei prossimi 30 giorni
              {urgenti.length > 0 && (
                <span style={{ color: COLORS.danger, fontWeight: 'bold', marginLeft: 8 }}>
                  ⚠️ {urgenti.length} urgenti
                </span>
              )}
            </div>
          </div>
        </div>
        {scadenze.prossima_scadenza && (
          <div
            style={{
              textAlign: 'right',
              background: getPriorityColor(
                scadenze.prossima_scadenza.priorita,
                scadenze.prossima_scadenza.urgente
              ).bg,
              padding: '8px 12px',
              borderRadius: BORDER_RADIUS.md,
            }}
          >
            <div style={{ fontSize: 11, color: COLORS.textMuted }}>Prossima</div>
            <div
              style={{
                fontWeight: 'bold',
                color: getPriorityColor(
                  scadenze.prossima_scadenza.priorita,
                  scadenze.prossima_scadenza.urgente
                ).text,
              }}
            >
              {scadenze.prossima_scadenza.giorni_mancanti === 0
                ? 'OGGI'
                : scadenze.prossima_scadenza.giorni_mancanti === 1
                  ? 'DOMANI'
                  : `tra ${scadenze.prossima_scadenza.giorni_mancanti} giorni`}
            </div>
          </div>
        )}
      </div>

      {/* Tabella scadenze */}
      <TableWrap>
        <Table style={{ fontSize: 11 }}>
          <thead>
            <tr style={{ borderBottom: `2px solid ${COLORS.border}`, background: COLORS.bgAlt }}>
              <Th align="center" style={{ padding: '6px 8px', fontSize: 10, width: 60 }}>Tipo</Th>
              <Th align="center" style={{ padding: '6px 8px', fontSize: 10, width: 80 }}>Importo</Th>
              <Th align="center" style={{ padding: '6px 8px', fontSize: 10, width: 60 }}>Data</Th>
              <Th align="center" style={{ padding: '6px 8px', fontSize: 10, width: 50 }}>Giorni</Th>
              <Th align="center" style={{ padding: '6px 8px', fontSize: 10 }}>Descrizione</Th>
              <Th align="center" style={{ padding: '6px 8px', fontSize: 10, width: 50 }}>Azioni</Th>
            </tr>
          </thead>
          <tbody>
            {visibleScadenze.slice(0, 6).map((s, idx) => {
              const colors = getPriorityColor(s.priorita, s.urgente);
              return (
                <tr
                  key={s.id || `scad-${idx}`}
                  style={{
                    background: colors.bg,
                    borderLeft: `3px solid ${colors.border}`,
                    borderBottom: `1px solid ${COLORS.gray[100]}`,
                  }}
                >
                  <Td align="center" style={{ padding: '6px 8px' }}>
                    <span
                      style={{
                        padding: '2px 6px',
                        background: colors.border + '30',
                        borderRadius: BORDER_RADIUS.sm,
                        color: colors.text,
                        fontWeight: '600',
                        fontSize: 10,
                      }}
                    >
                      {s.tipo}
                    </span>
                  </Td>
                  <Td
                    align="center"
                    mono
                    style={{ padding: '6px 8px', fontWeight: 'bold', color: colors.text }}
                  >
                    {s.importo > 0 ? formatEuro(s.importo) : '-'}
                  </Td>
                  <Td align="center" style={{ padding: '6px 8px', color: COLORS.textMuted }}>
                    {formatDate(s.data)}
                  </Td>
                  <Td
                    align="center"
                    style={{
                      padding: '6px 8px',
                      fontWeight: 'bold',
                      color: s.giorni_mancanti <= 3 ? COLORS.danger : COLORS.textMuted,
                    }}
                  >
                    {s.giorni_mancanti === 0
                      ? 'OGGI'
                      : s.giorni_mancanti === 1
                        ? '1g'
                        : s.giorni_mancanti < 0
                          ? `${s.giorni_mancanti}g`
                          : `${s.giorni_mancanti}g`}
                  </Td>
                  <Td
                    align="center"
                    style={{
                      padding: '6px 8px',
                      color: COLORS.textMuted,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      maxWidth: 180,
                    }}
                  >
                    {s.fornitore || s.descrizione || s.numero_fattura || ''}
                  </Td>
                  <Td align="center" style={{ padding: '6px 8px' }}>
                    <RowActions style={{ justifyContent: 'center' }}>
                      {(s.fattura_id || s.source === 'fattura') && (
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
                            background: COLORS.infoLight,
                            color: COLORS.info,
                            borderRadius: BORDER_RADIUS.sm,
                            fontSize: 10,
                            textDecoration: 'none',
                          }}
                          title="Vedi"
                        >
                          📄
                        </a>
                      )}
                      <RowActionButton
                        variant="success"
                        onClick={() => setPagaModal(s)}
                        title="Paga"
                      >
                        ✓
                      </RowActionButton>
                    </RowActions>
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </TableWrap>

      {scadenze.totale > 6 && (
        <div style={{ textAlign: 'center', marginTop: 12 }}>
          <Link
            to="/scadenze"
            style={{
              fontSize: 13,
              color: COLORS.info,
              textDecoration: 'none',
            }}
          >
            Vedi tutte le {scadenze.totale} scadenze →
          </Link>
        </div>
      )}

      {/* Modal Pagamento */}
      {pagaModal && (
        <div
          onClick={() => setPagaModal(null)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: COLORS.card,
              borderRadius: BORDER_RADIUS.xl,
              padding: 24,
              maxWidth: 400,
              width: '90%',
              boxShadow: SHADOWS.modal,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: COLORS.text }}>
                Registra Pagamento
              </h3>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPagaModal(null)}
                aria-label="Chiudi"
                style={{
                  width: 32,
                  height: 32,
                  flexShrink: 0,
                  padding: 0,
                  background: COLORS.bgAlt,
                  color: COLORS.gray[600],
                  fontSize: 16,
                }}
              >
                ✕
              </Button>
            </div>

            <div
              style={{
                background: COLORS.bgAlt,
                borderRadius: BORDER_RADIUS.md,
                padding: 16,
                marginBottom: 20,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ color: COLORS.textMuted, fontSize: 13 }}>Tipo:</span>
                <span style={{ fontWeight: 600 }}>
                  {pagaModal.tipo} {pagaModal.numero_fattura || ''}
                </span>
              </div>
              {pagaModal.fornitore && (
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span style={{ color: COLORS.textMuted, fontSize: 13 }}>Fornitore:</span>
                  <span
                    style={{
                      fontWeight: 500,
                      maxWidth: 200,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {pagaModal.fornitore}
                  </span>
                </div>
              )}
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ color: COLORS.textMuted, fontSize: 13 }}>Scadenza:</span>
                <span style={{ fontWeight: 500 }}>{formatDate(pagaModal.data)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: COLORS.textMuted, fontSize: 13 }}>Importo:</span>
                <span style={{ fontWeight: 700, color: COLORS.danger, fontSize: 16 }}>
                  {formatEuro(pagaModal.importo)}
                </span>
              </div>
            </div>

            <p style={{ fontSize: 14, color: COLORS.textMuted, marginBottom: 16 }}>
              Scegli il metodo di pagamento. Il movimento verrà registrato in Prima Nota.
            </p>

            <div style={{ display: 'flex', gap: 12, marginBottom: 16, justifyContent: 'center' }}>
              <Button
                variant="warning"
                size="lg"
                onClick={() => handlePaga(pagaModal, 'cassa')}
                disabled={processing}
                style={{
                  flexDirection: 'column',
                  gap: 4,
                  minWidth: 140,
                  padding: '14px 24px',
                }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>💵 CASSA</span>
                <span style={{ fontSize: 10, opacity: 0.9 }}>(pagato subito)</span>
              </Button>
              <Button
                variant="info"
                size="lg"
                onClick={() => handlePaga(pagaModal, 'banca')}
                disabled={processing}
                style={{
                  flexDirection: 'column',
                  gap: 4,
                  minWidth: 140,
                  padding: '14px 24px',
                }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>🏦 BANCA</span>
                <span style={{ fontSize: 10, opacity: 0.9 }}>(da riconciliare)</span>
              </Button>
            </div>

            <p style={{ fontSize: 12, color: COLORS.textSubtle, marginBottom: 12, textAlign: 'center' }}>
              💡 Se paghi in <strong>CASSA</strong> la scadenza viene saldata immediatamente.
              <br />
              Se paghi in <strong>BANCA</strong> verrà riconciliata quando troveremo il movimento
              nell&apos;estratto conto.
            </p>

            <Button
              variant="secondary"
              onClick={() => setPagaModal(null)}
              style={{
                width: '100%',
                background: COLORS.bgAlt,
                color: COLORS.textMuted,
                border: 'none',
              }}
            >
              Annulla
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ===================================================
// WIDGET: Alert Pagamenti DA_PAGARE (Stipendi + F24)
// ===================================================
function AlertPagamentiWidget({ data }) {
  const { buste = [], f24list = [], totStip = 0, totF24 = 0 } = data;
  const totale = totStip + totF24;

  return (
    <div
      data-testid="widget-alert-pagamenti"
      style={{
        background: COLORS.dangerLight,
        border: `1px solid ${COLORS.warning}`,
        borderLeft: `4px solid ${COLORS.warning}`,
        borderRadius: BORDER_RADIUS.lg,
        padding: '14px 18px',
        marginBottom: 12,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 12,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: '1 1 300px' }}>
        <span style={{ fontSize: 22 }}>📋</span>
        <div>
          <div style={{ fontWeight: 700, fontSize: 14, color: COLORS.warning }}>
            Pagamenti in attesa di riconciliazione bancaria
          </div>
          <div
            style={{
              fontSize: 12,
              color: COLORS.warning,
              marginTop: 2,
              display: 'flex',
              gap: 16,
              flexWrap: 'wrap',
            }}
          >
            {buste.length > 0 && (
              <span>
                <strong>{buste.length}</strong> {buste.length === 1 ? 'stipendio' : 'stipendi'} —{' '}
                {formatEuro(totStip)}
              </span>
            )}
            {f24list.length > 0 && (
              <span>
                <strong>{f24list.length}</strong> {f24list.length === 1 ? 'F24' : 'F24'} —{' '}
                {formatEuro(totF24)}
              </span>
            )}
            <span style={{ color: COLORS.warning, fontWeight: 700 }}>Totale: {formatEuro(totale)}</span>
          </div>
          <div style={{ fontSize: 11, color: COLORS.warning, marginTop: 4 }}>
            Carica l'estratto conto in "Import Documenti" per riconciliare automaticamente
          </div>
        </div>
      </div>
      <Link
        to="/riconciliazione/stipendi"
        data-testid="link-vai-paghe"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '8px 16px',
          background: COLORS.warning,
          color: 'white',
          borderRadius: BORDER_RADIUS.md,
          textDecoration: 'none',
          fontSize: 13,
          fontWeight: 700,
          whiteSpace: 'nowrap',
          boxShadow: SHADOWS.sm,
        }}
      >
            Vai a Paghe
      </Link>
    </div>
  );
}

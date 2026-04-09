import React, { useEffect, useState } from "react";
import { dashboardSummary, health } from "../api";
import api from "../api";
import { Link } from "react-router-dom";
import { useAnnoGlobale } from "../contexts/AnnoContext";
import { formatEuro, STYLES, COLORS, button, badge } from "../lib/utils";
import { PageLayout } from '../components/PageLayout';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend, PieChart, Pie, Cell } from 'recharts';
import { Eye, EyeOff, TrendingUp, Lock, AlertTriangle, Users } from "lucide-react";
import WidgetVerificaCoerenza from "../components/WidgetVerificaCoerenza";
import WidgetAgenti from "../components/WidgetAgenti";

export default function Dashboard() {
  const { anno } = useAnnoGlobale();
  const [h, setH] = useState(null);
  const [sum, setSum] = useState(null);
  const [err, setErr] = useState("");
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
  // Scadenze F24
  const [scadenzeF24, setScadenzeF24] = useState(null);
  
  // Alert Limiti Giustificativi
  const [alertGiustificativi, setAlertGiustificativi] = useState(null);
  
  // Alert Pagamenti (Stipendi + F24 DA_PAGARE)
  const [alertPagamenti, setAlertPagamenti] = useState(null);
  
  // Stato per auto-riparazione
  const [autoRepairStatus, setAutoRepairStatus] = useState(null);
  
  // Stato per Learning Machine
  const [learningStats, setLearningStats] = useState(null);

  // Widget Cucina
  const [ordiniCount, setOrdiniCount] = useState(0);
  const [ricetteCount, setRicetteCount] = useState(0);
  const [ricetteTotali, setRicetteTotali] = useState(0);

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
        api.post('/api/batch/auto-riconcilia-tutto').catch(() => ({ data: {} }))
      ]);
      
      const totaleCorrezioni = 
        (fatRes.data.campi_corretti || 0) + 
        (fatRes.data.fornitori_associati || 0) + 
        (ricRes.data.riconciliazioni_auto || 0);
      
      console.log('🔧 Auto-riparazione completata:', { fatture: fatRes.data, riconciliazione: ricRes.data });
      setAutoRepairStatus({ fatture: fatRes.data, riconciliazione: ricRes.data, totale: totaleCorrezioni });
      
      // Ricarica dati dopo riparazione (senza reload pagina)
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
        const [healthData, summaryData] = await Promise.all([
          health(),
          dashboardSummary(anno)
        ]);
        setH(healthData);
        setSum(summaryData);
        
        // Load trend mensile, calendario POS e scadenze - con timeout individuale
        const [trendRes, posRes, scadenzeRes, bilancioRes] = await Promise.all([
          api.get(`/api/dashboard/trend-mensile?anno=${anno}`).catch(() => ({ data: null })),
          api.get(`/api/pos-accredito/calendario-mensile/${anno}/${new Date().getMonth() + 1}`).catch(() => ({ data: null })),
          api.get('/api/scadenze/prossime?giorni=30&limit=8').catch(() => ({ data: null })),
          api.get(`/api/dashboard/bilancio-istantaneo?anno=${anno}`).catch(() => ({ data: null }))
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
          api.get(`/api/dashboard/stato-riconciliazione?anno=${anno}`).catch(() => ({ data: null })),
          api.get(`/api/contabilita/calcolo-imposte?regione=campania&anno=${anno}`).catch(() => ({ data: null })),
          api.get(`/api/f24-public/scadenze-prossime?giorni=60&limit=5`).catch(() => ({ data: null })),
          api.get(`/api/fornitori-learning/stats`).catch(() => ({ data: null })),
          Promise.all([
            api.get('/api/paghe/buste-paga?stato=DA_PAGARE').catch(() => ({ data: { data: [], count: 0 } })),
            api.get('/api/paghe/distinte-f24?stato=DA_PAGARE').catch(() => ({ data: { data: [], count: 0 } }))
          ]).catch(() => null)
        ]).then(([speseRes, confrontoRes, riconcRes, imposteRes, f24Res, learningRes, pagheResults]) => {
          setSpeseCategoria(speseRes.data);
          setConfrontoAnnuale(confrontoRes.data);
          setStatoRiconciliazione(riconcRes.data);
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
        }).catch(e => console.warn('Errore grafici secondari:', e));
        
        // alert-limiti caricato SEPARATAMENTE perché può essere lento (non blocca gli altri)
        api.get(`/api/giustificativi/alert-limiti?soglia_percentuale=80&anno=${anno}`)
          .then(res => setAlertGiustificativi(res.data))
          .catch(() => {});
        
      } catch (e) {
        console.error("Dashboard error:", e);
        setErr("Backend non raggiungibile. Verifica che il server sia attivo.");
        setLoading(false);
      }
    })();
    
    return () => {
      clearTimeout(timeoutId);
      controller.abort();
    };
  }, [anno]);

  // Carica dati widget cucina
  useEffect(() => {
    // Ordini in attesa (bozze cucina)
    api.get('/api/cucina/ordini-fornitori/bozze/count')
       .then(r => setOrdiniCount(r.data.count || 0)).catch(() => {});

    // Ricette: usa l'endpoint stats che ritorna totale e da_approvare
    api.get('/api/cucina/ricette/stats')
       .then(r => {
         setRicetteCount(r.data.da_approvare || 0);
         setRicetteTotali(r.data.totale || 0);
       }).catch(() => {});
  }, []);

  // Carica Volume Affari Reale quando toggle attivato
  async function loadVolumeReale() {
    if (volumeRealeData && volumeRealeData.anno === anno) return;
    setVolumeRealeLoading(true);
    try {
      const res = await api.get(`/api/gestione-riservata/volume-affari-reale?anno=${anno}`);
      setVolumeRealeData(res.data);
    } catch (e) {
      console.error("Errore caricamento volume reale:", e);
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
      <PageLayout title="Dashboard" icon="📊" subtitle="Panoramica">
        <div style={STYLES.card}>
          <p style={{ color: COLORS.gray }}>⏳ Caricamento in corso...</p>
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout title={`Dashboard ${anno}`} icon="📊" subtitle="Panoramica generale">
      <div style={{ ...STYLES.card, marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {/* Pulsante Auto-Riparazione */}
            <button
              onClick={eseguiAutoRiparazione}
              disabled={autoRepairStatus === 'running'}
              data-testid="btn-auto-repair"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '6px 12px',
                background: autoRepairStatus === 'running' ? '#9ca3af' : 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)',
                color: 'white',
                border: 'none',
                borderRadius: 6,
                cursor: autoRepairStatus === 'running' ? 'wait' : 'pointer',
                fontWeight: 500,
                fontSize: 12,
                boxShadow: '0 2px 4px rgba(102,126,234,0.3)'
              }}
            >
              {autoRepairStatus === 'running' ? (
                <>⏳ Riparazione...</>
              ) : (
                <>🔧 Auto-Ripara Dati</>
              )}
            </button>
            {autoRepairStatus && autoRepairStatus !== 'running' && autoRepairStatus.totale > 0 && (
              <span style={badge('success')}>
                ✓ {autoRepairStatus.totale} correzioni
              </span>
            )}
            {err ? (
              <span style={{ color: COLORS.danger, fontSize: 14 }}>{err}</span>
            ) : (
              <span style={badge('success')}>
                ✓ Backend connesso
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Widget Verifica Coerenza Dati */}
      <WidgetVerificaCoerenza anno={anno} />
      <WidgetAgenti />

      {/* Alert Limiti Giustificativi */}
      {alertGiustificativi && alertGiustificativi.totale_alerts > 0 && (
        <AlertGiustificativiWidget data={alertGiustificativi} />
      )}

      {/* Alert Pagamenti DA_PAGARE (Stipendi + F24) */}
      {alertPagamenti && (
        <AlertPagamentiWidget data={alertPagamenti} />
      )}

      {/* Widget Scadenze */}
      {scadenzeData && scadenzeData.scadenze && scadenzeData.scadenze.length > 0 && (
        <ScadenzeWidget scadenze={scadenzeData} />
      )}

      {/* Toggle Volume Affari Reale - Compatto */}
      <div style={{ 
        background: showVolumeReale ? 'linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%)' : '#f7fafc',
        borderRadius: 6,
        padding: 8,
        marginBottom: 10,
        border: showVolumeReale ? 'none' : '1px dashed #e2e8f0',
        transition: 'all 0.3s ease'
      }}>
        <div style={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center',
          marginBottom: showVolumeReale && volumeRealeData ? 8 : 0
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Lock size={12} color={showVolumeReale ? 'white' : '#718096'} />
            <span style={{ fontWeight: 600, color: showVolumeReale ? 'white' : '#4a5568', fontSize: 11 }}>
              Volume Affari
            </span>
          </div>
          <button
            onClick={handleToggleVolumeReale}
            data-testid="toggle-volume-reale"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 3,
              padding: '3px 8px',
              background: showVolumeReale ? 'rgba(255,255,255,0.2)' : '#1e3a5f',
              color: 'white',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: 10
            }}
          >
            {showVolumeReale ? <EyeOff size={10} /> : <Eye size={10} />}
            {showVolumeReale ? 'Nascondi' : 'Mostra'}
          </button>
        </div>

        {showVolumeReale && (
          <div>
            {volumeRealeLoading ? (
              <div style={{ color: 'rgba(255,255,255,0.7)', textAlign: 'center', padding: 20 }}>
                Caricamento...
              </div>
            ) : volumeRealeData ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 15 }}>
                <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: 16 }}>
                  <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12, marginBottom: 4 }}>Fatturato Ufficiale</div>
                  <div style={{ color: 'white', fontSize: 20, fontWeight: 700 }}>{formatEuro(volumeRealeData.fatturato_ufficiale)}</div>
                </div>
                <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 8, padding: 16 }}>
                  <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12, marginBottom: 4 }}>Corrispettivi</div>
                  <div style={{ color: 'white', fontSize: 20, fontWeight: 700 }}>{formatEuro(volumeRealeData.corrispettivi)}</div>
                </div>
                <div style={{ background: 'rgba(16,185,129,0.3)', borderRadius: 8, padding: 16 }}>
                  <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12, marginBottom: 4 }}>+ Incassi Extra</div>
                  <div style={{ color: '#34d399', fontSize: 20, fontWeight: 700 }}>+{formatEuro(volumeRealeData.incassi_non_fatturati)}</div>
                </div>
                <div style={{ background: 'rgba(239,68,68,0.3)', borderRadius: 8, padding: 16 }}>
                  <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12, marginBottom: 4 }}>- Spese Extra</div>
                  <div style={{ color: '#f87171', fontSize: 20, fontWeight: 700 }}>-{formatEuro(volumeRealeData.spese_non_fatturate)}</div>
                </div>
                <div style={{ 
                  gridColumn: 'span 4', 
                  background: 'linear-gradient(135deg, #e94560 0%, #0f3460 100%)', 
                  borderRadius: 8, 
                  padding: 20,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}>
                  <div>
                    <div style={{ color: 'rgba(255,255,255,0.8)', fontSize: 14 }}>VOLUME AFFARI REALE {anno}</div>
                    <div style={{ color: 'white', fontSize: 32, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 10 }}>
                      <TrendingUp size={28} />
                      {formatEuro(volumeRealeData.volume_affari_reale)}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>Ufficiale: {formatEuro(volumeRealeData.totale_ufficiale)}</div>
                    <div style={{ 
                      color: volumeRealeData.saldo_extra >= 0 ? '#34d399' : '#f87171', 
                      fontSize: 14, 
                      fontWeight: 600 
                    }}>
                      {volumeRealeData.saldo_extra >= 0 ? '+' : ''}{formatEuro(volumeRealeData.saldo_extra)} extra
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ color: 'rgba(255,255,255,0.7)', textAlign: 'center', padding: 20 }}>
                Nessun dato disponibile. <Link to="/gestione-riservata" style={{ color: '#e94560' }}>Aggiungi movimenti</Link>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Widget Bilancio Istantaneo - COMPATTO */}
      {bilancioIstantaneo && (
        <div style={{
          background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)',
          borderRadius: 10,
          padding: 14,
          marginTop: 12,
          color: 'white'
        }} data-testid="widget-bilancio-istantaneo">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, fontWeight: 600 }}>
              <TrendingUp size={18} /> Bilancio Istantaneo {anno}
            </h3>
            <span style={{ fontSize: 11, opacity: 0.7 }}>
              {bilancioIstantaneo.documenti?.fatture_ricevute || 0} fatt. • {bilancioIstantaneo.documenti?.corrispettivi || 0} corr.
            </span>
          </div>
          
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
            <div style={{ background: 'rgba(16,185,129,0.2)', borderRadius: 6, padding: 10, borderLeft: '3px solid #10b981' }}>
              <div style={{ fontSize: 10, opacity: 0.8 }}>RICAVI</div>
              <div style={{ fontSize: 16, fontWeight: 700 }}>{formatEuro(bilancioIstantaneo.ricavi?.totale || 0)}</div>
            </div>
            <div style={{ background: 'rgba(239,68,68,0.2)', borderRadius: 6, padding: 10, borderLeft: '3px solid #ef4444' }}>
              <div style={{ fontSize: 10, opacity: 0.8 }}>COSTI</div>
              <div style={{ fontSize: 16, fontWeight: 700 }}>{formatEuro(bilancioIstantaneo.costi?.totale || 0)}</div>
            </div>
            <div style={{ background: 'rgba(59,130,246,0.2)', borderRadius: 6, padding: 10, borderLeft: '3px solid #3b82f6' }}>
              <div style={{ fontSize: 10, opacity: 0.8 }}>SALDO IVA</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: (bilancioIstantaneo.iva?.saldo || 0) >= 0 ? '#f87171' : '#34d399' }}>
                {formatEuro(bilancioIstantaneo.iva?.saldo || 0)}
              </div>
            </div>
            <div style={{ 
              background: (bilancioIstantaneo.bilancio?.utile_lordo || 0) >= 0 ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)', 
              borderRadius: 6, padding: 10, 
              borderLeft: `3px solid ${(bilancioIstantaneo.bilancio?.utile_lordo || 0) >= 0 ? '#10b981' : '#ef4444'}`
            }}>
              <div style={{ fontSize: 10, opacity: 0.8 }}>UTILE LORDO</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: (bilancioIstantaneo.bilancio?.utile_lordo || 0) >= 0 ? '#34d399' : '#f87171' }}>
                {formatEuro(bilancioIstantaneo.bilancio?.utile_lordo || 0)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Widget IRES/IRAP - COMPATTO */}
      {imposteData && (
        <div style={{ borderRadius: 10, padding: 14, boxShadow: '0 1px 4px rgba(0,0,0,0.06)', marginTop: 12, background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)', color: 'white' }} data-testid="widget-calcolo-imposte">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <div style={{ fontSize: 14, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              🧮 Imposte {anno} <span style={{ fontSize: 10, opacity: 0.7, fontWeight: 400 }}>IRAP {imposteData.irap?.aliquota}%</span>
            </div>
            <Link to="/contabilita" style={{ padding: '4px 10px', background: 'rgba(255,255,255,0.2)', color: 'white', borderRadius: 4, textDecoration: 'none', fontSize: 11 }}>
              Dettaglio →
            </Link>
          </div>
          
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
            <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 6, padding: 10 }}>
              <div style={{ fontSize: 10, opacity: 0.8 }}>Utile</div>
              <div style={{ fontSize: 16, fontWeight: 'bold' }}>{formatEuro(imposteData.utile_civilistico)}</div>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 6, padding: 10 }}>
              <div style={{ fontSize: 10, opacity: 0.8 }}>IRES (24%)</div>
              <div style={{ fontSize: 16, fontWeight: 'bold', color: '#fbbf24' }}>{formatEuro(imposteData.ires?.imposta_dovuta)}</div>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.1)', borderRadius: 6, padding: 10 }}>
              <div style={{ fontSize: 10, opacity: 0.8 }}>IRAP</div>
              <div style={{ fontSize: 16, fontWeight: 'bold', color: '#a78bfa' }}>{formatEuro(imposteData.irap?.imposta_dovuta)}</div>
            </div>
            <div style={{ background: 'rgba(239,68,68,0.3)', borderRadius: 6, padding: 10 }}>
              <div style={{ fontSize: 10, opacity: 0.8 }}>TOTALE</div>
              <div style={{ fontSize: 16, fontWeight: 'bold' }}>{formatEuro(imposteData.totale_imposte)}</div>
            </div>
          </div>
          
          {/* Variazioni fiscali sintesi */}
          {(imposteData.ires?.totale_variazioni_aumento > 0 || imposteData.ires?.totale_variazioni_diminuzione > 0) && (
            <div style={{ marginTop: 15, padding: 12, background: 'rgba(255,255,255,0.05)', borderRadius: 8, display: 'flex', gap: 20, fontSize: 13 }}>
              <div>
                <span style={{ opacity: 0.7 }}>↑ Variazioni aumento: </span>
                <span style={{ color: '#fca5a5' }}>{formatEuro(imposteData.ires?.totale_variazioni_aumento)}</span>
              </div>
              <div>
                <span style={{ opacity: 0.7 }}>↓ Variazioni diminuzione: </span>
                <span style={{ color: '#86efac' }}>{formatEuro(imposteData.ires?.totale_variazioni_diminuzione)}</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Widget Scadenze F24 - COMPATTO */}
      {scadenzeF24 && scadenzeF24.scadenze && scadenzeF24.scadenze.length > 0 && (
        <div style={{ 
          background: 'white', 
          borderRadius: 10, 
          padding: 14, 
          marginTop: 12,
          border: '1px solid #e5e7eb',
          boxShadow: '0 1px 3px rgba(0,0,0,0.06)'
        }} data-testid="widget-scadenze-f24">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 16 }}>📋</span>
              <span style={{ fontWeight: 600, fontSize: 14, color: '#1e3a5f' }}>Scadenze F24</span>
              <span style={{ 
                background: '#fee2e2', 
                color: '#dc2626', 
                fontSize: 10, 
                padding: '2px 6px', 
                borderRadius: 4,
                fontWeight: 600
              }}>
                {scadenzeF24.totale || scadenzeF24.scadenze.length}
              </span>
            </div>
            <Link to="/f24" style={{ fontSize: 11, color: '#3b82f6', textDecoration: 'none' }}>
              Vedi tutti →
            </Link>
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {scadenzeF24.scadenze.slice(0, 4).map((f24, idx) => {
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
                    background: isScaduto ? '#fef2f2' : isUrgente ? '#fef3c7' : '#f8fafc',
                    borderRadius: 6,
                    borderLeft: `3px solid ${isScaduto ? '#dc2626' : isUrgente ? '#f59e0b' : '#3b82f6'}`
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
                    <span style={{ fontSize: 14 }}>{f24.tipo === 'IVA' ? '🧾' : '📋'}</span>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: '#1e293b' }}>
                        {f24.descrizione || f24.tipo || 'F24'}
                      </div>
                      <div style={{ fontSize: 10, color: '#64748b' }}>
                        {f24.tributo || f24.codice_tributo || ''}
                      </div>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#dc2626' }}>
                      {formatEuro(f24.importo)}
                    </div>
                    <div style={{ fontSize: 10, color: isScaduto ? '#dc2626' : isUrgente ? '#f59e0b' : '#64748b' }}>
                      {isScaduto ? 'Scaduto' : f24.giorni_mancanti === 0 ? 'Oggi' : f24.giorni_mancanti === 1 ? 'Domani' : `${f24.giorni_mancanti}g`}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          
          {scadenzeF24.totale_importo > 0 && (
            <div style={{ 
              marginTop: 10, 
              paddingTop: 10, 
              borderTop: '1px solid #e5e7eb',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <span style={{ fontSize: 11, color: '#64748b' }}>Totale da versare</span>
              <span style={{ fontSize: 14, fontWeight: 700, color: '#dc2626' }}>
                {formatEuro(scadenzeF24.totale_importo)}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Trend Mensile Chart */}
      {trendData && (
        <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)', marginTop: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <div>
              <h2 style={{ fontSize: 18, margin: 0, fontWeight: 'bold', color: '#1e3a5f' }}>📈 Trend Mensile {anno}</h2>
              <span style={{ fontSize: 13, color: '#6b7280' }}>Entrate vs Uscite</span>
            </div>
            <div style={{ display: 'flex', gap: 20, fontSize: 14 }}>
              <div>
                <span style={{ color: '#10b981' }}>● Entrate:</span>{' '}
                <strong>{formatEuro(trendData.totali?.entrate)}</strong>
              </div>
              <div>
                <span style={{ color: '#ef4444' }}>● Uscite:</span>{' '}
                <strong>{formatEuro(trendData.totali?.uscite)}</strong>
              </div>
              <div>
                <span style={{ color: trendData.totali?.saldo >= 0 ? '#10b981' : '#ef4444' }}>● Saldo:</span>{' '}
                <strong style={{ color: trendData.totali?.saldo >= 0 ? '#10b981' : '#ef4444' }}>
                  {formatEuro(trendData.totali?.saldo)}
                </strong>
              </div>
            </div>
          </div>
          
          <div style={{ height: 300, width: '100%', minHeight: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={trendData.trend_mensile} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="mese_nome" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={(v) => `€${(v/1000).toFixed(0)}k`} tick={{ fontSize: 11 }} />
                <Tooltip 
                  formatter={(value) => formatEuro(value)}
                  labelStyle={{ fontWeight: 'bold' }}
                  contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb' }}
                />
                <Legend />
                <Bar dataKey="entrate" fill="#10b981" name="Entrate" radius={[4, 4, 0, 0]} />
                <Bar dataKey="uscite" fill="#ef4444" name="Uscite" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Statistiche */}
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', 
            gap: 15, 
            marginTop: 20,
            padding: 15,
            background: '#f8fafc',
            borderRadius: 8
          }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: '#6b7280' }}>Media Entrate</div>
              <div style={{ fontSize: 18, fontWeight: 'bold', color: '#10b981' }}>
                {formatEuro(trendData.statistiche?.media_entrate_mensile)}
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: '#6b7280' }}>Media Uscite</div>
              <div style={{ fontSize: 18, fontWeight: 'bold', color: '#ef4444' }}>
                {formatEuro(trendData.statistiche?.media_uscite_mensile)}
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: '#6b7280' }}>Picco Entrate</div>
              <div style={{ fontSize: 18, fontWeight: 'bold' }}>{trendData.statistiche?.mese_picco_entrate}</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 12, color: '#6b7280' }}>Picco Uscite</div>
              <div style={{ fontSize: 18, fontWeight: 'bold' }}>{trendData.statistiche?.mese_picco_uscite}</div>
            </div>
          </div>
        </div>
      )}

      {/* IVA Trend Chart */}
      {trendData && (
        <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)', marginTop: 20 }}>
          <h2 style={{ fontSize: 18, margin: '0 0 15px 0', fontWeight: 'bold', color: '#1e3a5f' }}>📊 Trend IVA {anno}</h2>
          <div style={{ height: 200, width: '100%', minHeight: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trendData.trend_mensile} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="mese_nome" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={(v) => `€${(v/1000).toFixed(0)}k`} tick={{ fontSize: 11 }} />
                <Tooltip 
                  formatter={(value) => formatEuro(value)}
                  contentStyle={{ borderRadius: 8 }}
                />
                <Legend />
                <Line type="monotone" dataKey="iva_debito" stroke="#f59e0b" strokeWidth={2} name="IVA Debito" dot={{ r: 3 }} />
                <Line type="monotone" dataKey="iva_credito" stroke="#3b82f6" strokeWidth={2} name="IVA Credito" dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div style={{ 
            display: 'flex', 
            justifyContent: 'center', 
            gap: 30, 
            marginTop: 15,
            fontSize: 14 
          }}>
            <div>
              IVA Debito Totale: <strong style={{ color: '#f59e0b' }}>{formatEuro(trendData.totali?.iva_debito)}</strong>
            </div>
            <div>
              IVA Credito Totale: <strong style={{ color: '#3b82f6' }}>{formatEuro(trendData.totali?.iva_credito)}</strong>
            </div>
            <div>
              Saldo IVA: <strong style={{ color: trendData.totali?.saldo_iva >= 0 ? '#ef4444' : '#10b981' }}>
                {formatEuro(Math.abs(trendData.totali?.saldo_iva))} {trendData.totali?.saldo_iva >= 0 ? '(da versare)' : '(a credito)'}
              </strong>
            </div>
          </div>
        </div>
      )}


      {/* Nuova sezione: Grafici Avanzati */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', 
        gap: 20, 
        marginTop: 20 
      }}>
        {/* Grafico a Torta - Spese per Categoria */}
        {speseCategoria && speseCategoria.categorie && speseCategoria.categorie.length > 0 && (
          <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}>
            <h2 style={{ fontSize: 18, margin: '0 0 15px 0', fontWeight: 'bold', color: '#1e3a5f' }}>🥧 Distribuzione Spese {anno}</h2>
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
                    {speseCategoria.categorie.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => formatEuro(value)} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ width: '40%', fontSize: 11, maxHeight: 250, overflow: 'auto' }}>
                {speseCategoria.categorie.slice(0, 6).map((cat, idx) => (
                  <div key={idx} style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: 6, 
                    marginBottom: 8,
                    padding: '4px 8px',
                    background: '#f8fafc',
                    borderRadius: 4
                  }}>
                    <span style={{ 
                      width: 10, 
                      height: 10, 
                      borderRadius: 2, 
                      background: PIE_COLORS[idx % PIE_COLORS.length],
                      flexShrink: 0
                    }}></span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {cat.nome}
                      </div>
                      <div style={{ color: '#6b7280' }}>{formatEuro(cat.valore)}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div style={{ 
              textAlign: 'center', 
              marginTop: 10, 
              padding: 10, 
              background: '#f0fdf4', 
              borderRadius: 8 
            }}>
              <span style={{ color: '#6b7280' }}>Totale Spese: </span>
              <strong style={{ color: '#dc2626' }}>{formatEuro(speseCategoria.totale_spese)}</strong>
            </div>
          </div>
        )}

        {/* Widget Stato Riconciliazione */}
        {statoRiconciliazione && (
          <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}>
            <h2 style={{ fontSize: 18, margin: '0 0 15px 0', fontWeight: 'bold', color: '#1e3a5f' }}>✅ Stato Riconciliazione {anno}</h2>
            
            {/* Barra progresso globale */}
            <div style={{ marginBottom: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <span style={{ fontSize: 13, color: '#6b7280' }}>Progresso Globale</span>
                <span style={{ fontWeight: 'bold', color: statoRiconciliazione.riepilogo.percentuale_globale >= 80 ? '#16a34a' : '#f59e0b' }}>
                  {statoRiconciliazione.riepilogo.percentuale_globale}%
                </span>
              </div>
              <div style={{ height: 12, background: '#e5e7eb', borderRadius: 6, overflow: 'hidden' }}>
                <div style={{ 
                  height: '100%', 
                  width: `${statoRiconciliazione.riepilogo.percentuale_globale}%`,
                  background: statoRiconciliazione.riepilogo.percentuale_globale >= 80 
                    ? 'linear-gradient(90deg, #10b981, #34d399)' 
                    : 'linear-gradient(90deg, #f59e0b, #fbbf24)',
                  borderRadius: 6,
                  transition: 'width 0.5s ease'
                }}></div>
              </div>
            </div>

            {/* Dettaglio Fatture */}
            <div style={{ background: '#f8fafc', borderRadius: 8, padding: 12, marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontWeight: 600 }}>📄 Fatture Fornitori</span>
                <span style={{ 
                  padding: '2px 8px', 
                  borderRadius: 10, 
                  fontSize: 12,
                  background: statoRiconciliazione.fatture.percentuale_pagate >= 80 ? '#dcfce7' : '#fef3c7',
                  color: statoRiconciliazione.fatture.percentuale_pagate >= 80 ? '#16a34a' : '#d97706'
                }}>
                  {statoRiconciliazione.fatture.percentuale_pagate}%
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, fontSize: 13 }}>
                <div>
                  <div style={{ color: '#6b7280' }}>Pagate</div>
                  <div style={{ fontWeight: 'bold', color: '#16a34a' }}>
                    {statoRiconciliazione.fatture.pagate} / {statoRiconciliazione.fatture.totali}
                  </div>
                </div>
                <div>
                  <div style={{ color: '#6b7280' }}>Da pagare</div>
                  <div style={{ fontWeight: 'bold', color: '#dc2626' }}>
                    {formatEuro(statoRiconciliazione.fatture.importo_da_pagare)}
                  </div>
                </div>
              </div>
            </div>

            {/* Dettaglio Salari */}
            <div style={{ background: '#f8fafc', borderRadius: 8, padding: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontWeight: 600 }}>Salari Dipendenti</span>
                <span style={{ 
                  padding: '2px 8px', 
                  borderRadius: 10, 
                  fontSize: 12,
                  background: statoRiconciliazione.salari.percentuale_riconciliati >= 80 ? '#dcfce7' : '#fef3c7',
                  color: statoRiconciliazione.salari.percentuale_riconciliati >= 80 ? '#16a34a' : '#d97706'
                }}>
                  {statoRiconciliazione.salari.percentuale_riconciliati}%
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, fontSize: 13 }}>
                <div>
                  <div style={{ color: '#6b7280' }}>Riconciliati</div>
                  <div style={{ fontWeight: 'bold', color: '#16a34a' }}>
                    {statoRiconciliazione.salari.riconciliati} / {statoRiconciliazione.salari.totali}
                  </div>
                </div>
                <div>
                  <div style={{ color: '#6b7280' }}>Da verificare</div>
                  <div style={{ fontWeight: 'bold', color: '#f59e0b' }}>
                    {statoRiconciliazione.salari.da_riconciliare}
                  </div>
                </div>
              </div>
            </div>

            <Link to="/riconciliazione" style={{
              display: 'block',
              marginTop: 15,
              padding: '10px 16px',
              background: '#3b82f6',
              color: 'white',
              borderRadius: 8,
              textAlign: 'center',
              textDecoration: 'none',
              fontWeight: 'bold',
              fontSize: 13
            }}>
              Vai a Riconciliazione →
            </Link>
          </div>
        )}

        {/* Widget Learning Machine */}
        {learningStats && (
          <div style={{ 
            background: 'linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%)', 
            borderRadius: 12, 
            padding: 20, 
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
            border: '1px solid #86efac'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 15 }}>
              <h3 style={{ fontSize: 16, margin: 0, fontWeight: 'bold', color: '#166534' }}>
                🧠 Learning Machine
              </h3>
              <span style={{ 
                background: '#16a34a', 
                color: 'white', 
                padding: '4px 10px', 
                borderRadius: 20, 
                fontSize: 11, 
                fontWeight: 'bold' 
              }}>
                ATTIVA
              </span>
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
              {/* Fornitori */}
              <div style={{ background: 'white', borderRadius: 10, padding: 12, textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>Fornitori</div>
                <div style={{ fontSize: 22, fontWeight: 'bold', color: '#166534' }}>
                  {learningStats.fornitori_con_keywords || 0}
                </div>
                <div style={{ fontSize: 10, color: '#16a34a' }}>
                  {learningStats.copertura_fornitori || 0}% copertura
                </div>
              </div>
              
              {/* Fatture */}
              <div style={{ background: 'white', borderRadius: 10, padding: 12, textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>Fatture</div>
                <div style={{ fontSize: 22, fontWeight: 'bold', color: '#166534' }}>
                  {learningStats.percentuale_fatture || 0}%
                </div>
                <div style={{ fontSize: 10, color: '#16a34a' }}>
                  {learningStats.fatture_classificate || 0}/{learningStats.totale_fatture || 0}
                </div>
              </div>
              
              {/* F24 */}
              <div style={{ background: 'white', borderRadius: 10, padding: 12, textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>F24</div>
                <div style={{ fontSize: 22, fontWeight: 'bold', color: '#166534' }}>
                  {learningStats.percentuale_f24 || 0}%
                </div>
                <div style={{ fontSize: 10, color: '#16a34a' }}>
                  {learningStats.f24_classificati || 0}/{learningStats.totale_f24 || 0}
                </div>
              </div>
            </div>
            
            <Link to="/learning-machine" style={{
              display: 'block',
              marginTop: 12,
              padding: '8px 14px',
              background: '#16a34a',
              color: 'white',
              borderRadius: 8,
              textAlign: 'center',
              textDecoration: 'none',
              fontWeight: 'bold',
              fontSize: 12
            }}>
              Gestisci Learning Machine →
            </Link>
          </div>
        )}
      </div>

      {/* Confronto Anno Precedente */}
      {confrontoAnnuale && (
        <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)', marginTop: 20 }}>
          <h2 style={{ fontSize: 18, margin: '0 0 15px 0', fontWeight: 'bold', color: '#1e3a5f' }}>
            📊 Confronto {anno} vs {anno - 1}
          </h2>
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', 
            gap: 15 
          }}>
            {/* Entrate */}
            <div style={{ background: '#f0fdf4', borderRadius: 12, padding: 15 }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 5 }}>Entrate</div>
              <div style={{ fontSize: 24, fontWeight: 'bold', color: '#16a34a' }}>
                {formatEuro(confrontoAnnuale.anno_corrente.entrate)}
              </div>
              <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: 4, 
                marginTop: 5,
                fontSize: 13
              }}>
                <span style={{ 
                  color: confrontoAnnuale.variazioni_percentuali.entrate >= 0 ? '#16a34a' : '#dc2626',
                  fontWeight: 'bold'
                }}>
                  {confrontoAnnuale.variazioni_percentuali.entrate >= 0 ? '↑' : '↓'} 
                  {Math.abs(confrontoAnnuale.variazioni_percentuali.entrate)}%
                </span>
                <span style={{ color: '#6b7280' }}>vs {anno - 1}</span>
              </div>
            </div>

            {/* Uscite */}
            <div style={{ background: '#fef2f2', borderRadius: 12, padding: 15 }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 5 }}>Uscite</div>
              <div style={{ fontSize: 24, fontWeight: 'bold', color: '#dc2626' }}>
                {formatEuro(confrontoAnnuale.anno_corrente.uscite)}
              </div>
              <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: 4, 
                marginTop: 5,
                fontSize: 13
              }}>
                <span style={{ 
                  color: confrontoAnnuale.variazioni_percentuali.uscite <= 0 ? '#16a34a' : '#dc2626',
                  fontWeight: 'bold'
                }}>
                  {confrontoAnnuale.variazioni_percentuali.uscite >= 0 ? '↑' : '↓'} 
                  {Math.abs(confrontoAnnuale.variazioni_percentuali.uscite)}%
                </span>
                <span style={{ color: '#6b7280' }}>vs {anno - 1}</span>
              </div>
            </div>

            {/* Saldo */}
            <div style={{ 
              background: confrontoAnnuale.anno_corrente.saldo >= 0 ? '#f0fdf4' : '#fef2f2', 
              borderRadius: 12, 
              padding: 15 
            }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 5 }}>Saldo</div>
              <div style={{ 
                fontSize: 24, 
                fontWeight: 'bold', 
                color: confrontoAnnuale.anno_corrente.saldo >= 0 ? '#16a34a' : '#dc2626' 
              }}>
                {formatEuro(confrontoAnnuale.anno_corrente.saldo)}
              </div>
              <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: 4, 
                marginTop: 5,
                fontSize: 13
              }}>
                <span style={{ 
                  color: confrontoAnnuale.variazioni_percentuali.saldo >= 0 ? '#16a34a' : '#dc2626',
                  fontWeight: 'bold'
                }}>
                  {confrontoAnnuale.variazioni_percentuali.saldo >= 0 ? '↑' : '↓'} 
                  {Math.abs(confrontoAnnuale.variazioni_percentuali.saldo)}%
                </span>
                <span style={{ color: '#6b7280' }}>vs {anno - 1}</span>
              </div>
            </div>

            {/* Numero Fatture */}
            <div style={{ background: '#f0f9ff', borderRadius: 12, padding: 15 }}>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 5 }}>N. Fatture</div>
              <div style={{ fontSize: 24, fontWeight: 'bold', color: '#0284c7' }}>
                {confrontoAnnuale.anno_corrente.num_fatture}
              </div>
              <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: 4, 
                marginTop: 5,
                fontSize: 13
              }}>
                <span style={{ 
                  color: '#6b7280',
                  fontWeight: 'bold'
                }}>
                  {confrontoAnnuale.variazioni_percentuali.num_fatture >= 0 ? '↑' : '↓'} 
                  {Math.abs(confrontoAnnuale.variazioni_percentuali.num_fatture)}%
                </span>
                <span style={{ color: '#6b7280' }}>vs {anno - 1}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,0.08)', marginTop: 20 }}>
        <h2 style={{ fontSize: 18, fontWeight: 'bold', color: '#1e3a5f' }}>🚀 Azioni Rapide</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 15, marginTop: 15 }}>
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
          <Link to="/f24" style={quickActionStyle('#fff3e0', '#e65100')}>
            <span style={{ fontSize: 20 }}>📋</span>
            <span>F24 / Tributi</span>
          </Link>
          <Link to="/iva" style={quickActionStyle('#e0f2f1', '#00695c')}>
            <span style={{ fontSize: 20 }}>🧾</span>
            <span>Calcolo IVA</span>
          </Link>
          <Link to="/commercialista" style={quickActionStyle('#fce4ec', '#c2185b')}>
            <span style={{ fontSize: 20 }}>📁</span>
            <span>Commercialista</span>
          </Link>
        </div>

        {/* Report PDF Section */}
        <div style={{ marginTop: 20, paddingTop: 20, borderTop: '1px solid #e2e8f0' }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: '#475569' }}>📄 Scarica Report PDF</div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <a 
              href={`/api/contabilita/export/pdf-dichiarazione?anno=${anno}&regione=campania`}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                padding: '8px 14px',
                background: '#dc2626',
                color: 'white',
                borderRadius: 6,
                textDecoration: 'none',
                fontSize: 13,
                fontWeight: 500
              }}
            >
              🧮 Dichiarazione IRES/IRAP
            </a>
            <a 
              href={`/api/report-pdf/mensile?anno=${anno}&mese=${new Date().getMonth() + 1}`}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                padding: '8px 14px',
                background: '#3b82f6',
                color: 'white',
                borderRadius: 6,
                textDecoration: 'none',
                fontSize: 13,
                fontWeight: 500
              }}
            >
              📊 Report Mensile
            </a>
            <a 
              href="/api/report-pdf/scadenze?giorni=30"
              target="_blank"
              rel="noopener noreferrer"
              style={{
                padding: '8px 14px',
                background: '#ef4444',
                color: 'white',
                borderRadius: 6,
                textDecoration: 'none',
                fontSize: 13,
                fontWeight: 500
              }}
            >
              ⏰ Report Scadenze
            </a>
            <a 
              href="/api/report-pdf/dipendenti"
              target="_blank"
              rel="noopener noreferrer"
              style={{
                padding: '8px 14px',
                background: '#8b5cf6',
                color: 'white',
                borderRadius: 6,
                textDecoration: 'none',
                fontSize: 13,
                fontWeight: 500
              }}
            >
              👥 Report Dipendenti
            </a>
            <a 
              href="/api/report-pdf/magazzino"
              target="_blank"
              rel="noopener noreferrer"
              style={{
                padding: '8px 14px',
                background: '#10b981',
                color: 'white',
                borderRadius: 6,
                textDecoration: 'none',
                fontSize: 13,
                fontWeight: 500
              }}
            >
              📦 Report Magazzino
            </a>
          </div>
        </div>
      </div>

      {/* ========================== */}
      {/* WIDGET CUCINA & ORDINI     */}
      {/* ========================== */}
      <div
        data-testid="widget-cucina"
        style={{ ...STYLES.card, marginTop: 16, marginBottom: 8 }}
      >
        <h3 style={{ margin: '0 0 14px', fontSize: 15, fontWeight: 700, color: COLORS.primary }}>
          Cucina &amp; Ordini
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
          {/* Ordini in attesa */}
          <Link
            to="/cucina"
            data-testid="stat-ordini-attesa"
            style={{ textDecoration: 'none' }}
          >
            <div style={{
              background: ordiniCount > 0 ? '#fff7ed' : COLORS.grayBg,
              border: `1px solid ${ordiniCount > 0 ? '#fcd34d' : COLORS.grayLight}`,
              borderLeft: `4px solid ${ordiniCount > 0 ? COLORS.warning : COLORS.grayLight}`,
              borderRadius: 10,
              padding: '14px 16px',
              cursor: 'pointer',
              transition: 'box-shadow 0.2s'
            }}>
              <div style={{ fontSize: 22 }}>🛒</div>
              <div style={{ fontSize: 26, fontWeight: 800, color: ordiniCount > 0 ? COLORS.warning : COLORS.gray, marginTop: 4 }}>
                {ordiniCount}
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.primary, marginTop: 2 }}>Ordini in attesa</div>
              <div style={{ fontSize: 11, color: COLORS.gray, marginTop: 2 }}>Bozze cucina</div>
            </div>
          </Link>

          {/* Ricette da approvare */}
          <Link
            to="/ricettario"
            data-testid="stat-ricette-approvare"
            style={{ textDecoration: 'none' }}
          >
            <div style={{
              background: ricetteCount > 0 ? '#eff6ff' : COLORS.grayBg,
              border: `1px solid ${ricetteCount > 0 ? '#bfdbfe' : COLORS.grayLight}`,
              borderLeft: `4px solid ${ricetteCount > 0 ? COLORS.info : COLORS.grayLight}`,
              borderRadius: 10,
              padding: '14px 16px',
              cursor: 'pointer'
            }}>
              <div style={{ fontSize: 22 }}>📖</div>
              <div style={{ fontSize: 26, fontWeight: 800, color: ricetteCount > 0 ? COLORS.info : COLORS.gray, marginTop: 4 }}>
                {ricetteCount}
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.primary, marginTop: 2 }}>Ricette da approvare</div>
              <div style={{ fontSize: 11, color: COLORS.gray, marginTop: 2 }}>In attesa di revisione</div>
            </div>
          </Link>

          {/* Ricette totali */}
          <Link
            to="/ricettario"
            data-testid="stat-ricette-totali"
            style={{ textDecoration: 'none' }}
          >
            <div style={{
              background: COLORS.grayBg,
              border: `1px solid ${COLORS.grayLight}`,
              borderLeft: `4px solid ${COLORS.primary}`,
              borderRadius: 10,
              padding: '14px 16px',
              cursor: 'pointer'
            }}>
              <div style={{ fontSize: 22 }}>🍽️</div>
              <div style={{ fontSize: 26, fontWeight: 800, color: COLORS.primary, marginTop: 4 }}>
                {ricetteTotali}
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.primary, marginTop: 2 }}>Ricette totali</div>
              <div style={{ fontSize: 11, color: COLORS.gray, marginTop: 2 }}>Nel ricettario</div>
            </div>
          </Link>
        </div>
      </div>

    </PageLayout>
  );
}

// Style helper
const quickActionStyle = (bg, color) => ({
  padding: 15,
  background: bg,
  borderRadius: 8,
  textDecoration: 'none',
  color: color,
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  transition: 'transform 0.2s',
});

// Colori per grafico a torta
const PIE_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1'];

// POS Calendar Widget Component
function POSCalendarWidget({ data }) {
  if (!data || !data.giorni) return null;
  
  const mesiNomi = ['', 'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre'];
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
      isFestivo
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
    if (isFestivo) return '#fecaca';
    if (sfasamento === 1) return '#dcfce7';
    if (sfasamento === 2) return '#fef3c7';
    if (sfasamento >= 3) return '#fee2e2';
    return '#f9fafb';
  };
  
  return (
    <div>
      <div style={{ textAlign: 'center', fontWeight: 'bold', marginBottom: 10 }}>
        {mesiNomi[data.mese]} {data.anno}
      </div>
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(7, 1fr)', 
        gap: 4,
        fontSize: 12
      }}>
        {/* Header */}
        {giorniSettimana.map(g => (
          <div key={g} style={{ 
            textAlign: 'center', 
            fontWeight: 'bold', 
            padding: 6,
            color: g === 'Sab' || g === 'Dom' ? '#ef4444' : '#374151'
          }}>
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
              borderRadius: 4,
              cursor: g ? 'pointer' : 'default',
              position: 'relative'
            }}
            title={g ? `${g.giorno_settimana_pagamento}: Accredito in ${g.giorni_sfasamento} giorni\n${g.note}` : ''}
          >
            {g && (
              <>
                <div style={{ fontWeight: '500' }}>{g.giorno}</div>
                <div style={{ fontSize: 9, color: '#6b7280' }}>+{g.sfasamento}g</div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}


// Widget Alert Limiti Giustificativi
function AlertGiustificativiWidget({ data }) {
  if (!data || !data.alerts || data.alerts.length === 0) return null;
  
  const criticalCount = data.alerts.filter(a => a.livello === 'critical').length;
  const warningCount = data.alerts.filter(a => a.livello === 'warning').length;
  
  // Mostra solo i primi 5 alert
  const displayAlerts = data.alerts.slice(0, 5);
  
  const getLevelStyle = (livello) => {
    if (livello === 'critical') {
      return { bg: '#fef2f2', border: '#fecaca', text: '#dc2626', badge: '#dc2626' };
    }
    return { bg: '#fffbeb', border: '#fde68a', text: '#d97706', badge: '#f59e0b' };
  };
  
  return (
    <div style={{ 
      background: 'white',
      border: '1px solid #e5e7eb',
      borderRadius: 10, 
      padding: 16, 
      marginBottom: 12,
      boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
    }} data-testid="widget-alert-giustificativi">
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ 
            width: 32, 
            height: 32, 
            borderRadius: '50%', 
            background: criticalCount > 0 ? '#fef2f2' : '#fffbeb',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <AlertTriangle size={18} color={criticalCount > 0 ? '#dc2626' : '#f59e0b'} />
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: '#1f2937' }}>
              Alert Ferie e Permessi
            </h3>
            <span style={{ fontSize: 11, color: '#6b7280' }}>
              {data.dipendenti_coinvolti} dipendenti vicini al limite
            </span>
          </div>
        </div>
        
        <div style={{ display: 'flex', gap: 8 }}>
          {criticalCount > 0 && (
            <span style={{ 
              padding: '4px 10px', 
              background: '#fef2f2', 
              color: '#dc2626', 
              borderRadius: 12, 
              fontSize: 11,
              fontWeight: 600
            }}>
              {criticalCount} superati
            </span>
          )}
          {warningCount > 0 && (
            <span style={{ 
              padding: '4px 10px', 
              background: '#fffbeb', 
              color: '#d97706', 
              borderRadius: 12, 
              fontSize: 11,
              fontWeight: 600
            }}>
              {warningCount} in esaurimento
            </span>
          )}
        </div>
      </div>
      
      {/* Lista Alert */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {displayAlerts.map((alert, idx) => {
          const style = getLevelStyle(alert.livello);
          return (
            <div 
              key={idx}
              style={{ 
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 12px',
                background: style.bg,
                borderRadius: 8,
                borderLeft: `3px solid ${style.badge}`
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Users size={14} color={style.text} />
                <div>
                  <div style={{ fontWeight: 500, fontSize: 13, color: '#1f2937' }}>
                    {alert.employee_nome}
                  </div>
                  <div style={{ fontSize: 11, color: '#6b7280' }}>
                    {alert.descrizione} ({alert.codice})
                  </div>
                </div>
              </div>
              
              <div style={{ textAlign: 'right' }}>
                <div style={{ 
                  fontWeight: 600, 
                  fontSize: 13,
                  color: style.text
                }}>
                  {alert.percentuale}%
                </div>
                <div style={{ fontSize: 10, color: '#6b7280' }}>
                  {alert.ore_usate}h / {alert.limite}h
                </div>
              </div>
            </div>
          );
        })}
      </div>
      
      {/* Footer */}
      {data.totale_alerts > 5 && (
        <div style={{ marginTop: 10, textAlign: 'center' }}>
          <Link 
            to="/presenze?tab=giustificativi"
            style={{ 
              fontSize: 12, 
              color: '#3b82f6', 
              textDecoration: 'none',
              fontWeight: 500
            }}
          >
            Vedi tutti ({data.totale_alerts} alert) →
          </Link>
        </div>
      )}
    </div>
  );
}


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
    if (urgente) return { bg: '#fef2f2', border: '#fecaca', text: '#dc2626' };
    switch (priorita) {
      case 'critica': return { bg: '#fef2f2', border: '#fecaca', text: '#dc2626' };
      case 'alta': return { bg: '#fff7ed', border: '#fed7aa', text: '#ea580c' };
      case 'media': return { bg: '#fefce8', border: '#fef08a', text: '#ca8a04' };
      default: return { bg: '#f0fdf4', border: '#bbf7d0', text: '#16a34a' };
    }
  };
  
  const getTipoIcon = (tipo) => {
    switch (tipo) {
      case 'IVA': return '🧾';
      case 'F24': return '📋';
      case 'FATTURA': return '📄';
      case 'INPS': return '🏛️';
      default: return '📌';
    }
  };
  
  const formatDate = (dateStr) => {
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
        numero_fattura: scadenza.numero_fattura || ''
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
    <div style={{ 
      background: 'white', 
      borderRadius: 12, 
      padding: 20,
      marginBottom: 20,
      border: urgenti.length > 0 ? '2px solid #fecaca' : '1px solid #e5e7eb',
      boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
    }}>
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        marginBottom: 15
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 24 }}>📅</span>
          <div>
            <div style={{ fontWeight: 'bold', fontSize: 16 }}>Prossime Scadenze</div>
            <div style={{ fontSize: 12, color: '#6b7280' }}>
              {scadenze.totale} scadenze nei prossimi 30 giorni
              {urgenti.length > 0 && (
                <span style={{ color: '#dc2626', fontWeight: 'bold', marginLeft: 8 }}>
                  ⚠️ {urgenti.length} urgenti
                </span>
              )}
            </div>
          </div>
        </div>
        {scadenze.prossima_scadenza && (
          <div style={{ 
            textAlign: 'right',
            background: getPriorityColor(scadenze.prossima_scadenza.priorita, scadenze.prossima_scadenza.urgente).bg,
            padding: '8px 12px',
            borderRadius: 8
          }}>
            <div style={{ fontSize: 11, color: '#6b7280' }}>Prossima</div>
            <div style={{ fontWeight: 'bold', color: getPriorityColor(scadenze.prossima_scadenza.priorita, scadenze.prossima_scadenza.urgente).text }}>
              {scadenze.prossima_scadenza.giorni_mancanti === 0 ? 'OGGI' : 
               scadenze.prossima_scadenza.giorni_mancanti === 1 ? 'DOMANI' :
               `tra ${scadenze.prossima_scadenza.giorni_mancanti} giorni`}
            </div>
          </div>
        )}
      </div>
      
      {/* Tabella scadenze */}
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #e2e8f0', background: '#f8fafc' }}>
            <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, fontSize: 10, color: '#64748b', textTransform: 'uppercase', width: 60 }}>Tipo</th>
            <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, fontSize: 10, color: '#64748b', textTransform: 'uppercase', width: 80 }}>Importo</th>
            <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, fontSize: 10, color: '#64748b', textTransform: 'uppercase', width: 60 }}>Data</th>
            <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, fontSize: 10, color: '#64748b', textTransform: 'uppercase', width: 50 }}>Giorni</th>
            <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, fontSize: 10, color: '#64748b', textTransform: 'uppercase' }}>Descrizione</th>
            <th style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 600, fontSize: 10, color: '#64748b', textTransform: 'uppercase', width: 50 }}>Azioni</th>
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
                  borderBottom: '1px solid #f1f5f9'
                }}
              >
                <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                  <span style={{ 
                    padding: '2px 6px', 
                    background: colors.border + '30', 
                    borderRadius: 4,
                    color: colors.text,
                    fontWeight: '600',
                    fontSize: 10
                  }}>
                    {s.tipo}
                  </span>
                </td>
                <td style={{ padding: '6px 8px', textAlign: 'center', fontWeight: 'bold', color: colors.text }}>
                  {s.importo > 0 ? formatEuro(s.importo) : '-'}
                </td>
                <td style={{ padding: '6px 8px', textAlign: 'center', color: '#6b7280' }}>
                  {formatDate(s.data)}
                </td>
                <td style={{ 
                  padding: '6px 8px', 
                  textAlign: 'center',
                  fontWeight: 'bold',
                  color: s.giorni_mancanti <= 3 ? '#dc2626' : '#6b7280'
                }}>
                  {s.giorni_mancanti === 0 ? 'OGGI' :
                   s.giorni_mancanti === 1 ? '1g' :
                   s.giorni_mancanti < 0 ? `${s.giorni_mancanti}g` :
                   `${s.giorni_mancanti}g`}
                </td>
                <td style={{ padding: '6px 8px', textAlign: 'center', color: '#64748b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 180 }}>
                  {s.fornitore || s.descrizione || s.numero_fattura || ''}
                </td>
                <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                  <div style={{ display: 'flex', gap: 3, justifyContent: 'center' }}>
                    {(s.fattura_id || s.source === 'fattura') && (
                      <a
                        href={`/api/fatture-ricevute/fattura/${s.fattura_id || s.id}/view-assoinvoice`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          padding: '3px 6px',
                          background: '#3b82f6',
                          color: 'white',
                          borderRadius: 4,
                          fontSize: 10,
                          textDecoration: 'none'
                        }}
                        title="Vedi"
                      >
                        📄
                      </a>
                    )}
                    <button
                      onClick={() => setPagaModal(s)}
                      style={{
                        padding: '3px 6px',
                        background: '#10b981',
                        color: 'white',
                        border: 'none',
                        borderRadius: 4,
                        fontSize: 10,
                        cursor: 'pointer'
                      }}
                      title="Paga"
                    >
                      ✓
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      
      {scadenze.totale > 6 && (
        <div style={{ textAlign: 'center', marginTop: 12 }}>
          <Link 
            to="/scadenze" 
            style={{ 
              fontSize: 13, 
              color: '#3b82f6',
              textDecoration: 'none'
            }}
          >
            Vedi tutte le {scadenze.totale} scadenze →
          </Link>
        </div>
      )}

      {/* Modal Pagamento */}
      {pagaModal && (
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
            borderRadius: 16,
            padding: 24,
            maxWidth: 400,
            width: '90%',
            boxShadow: '0 25px 50px rgba(0,0,0,0.25)'
          }}>
            <h3 style={{ margin: '0 0 16px', fontSize: 18, fontWeight: 700, color: '#1e293b' }}>
              Registra Pagamento
            </h3>
            
            <div style={{ 
              background: '#f8fafc', 
              borderRadius: 8, 
              padding: 16, 
              marginBottom: 20 
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ color: '#64748b', fontSize: 13 }}>Tipo:</span>
                <span style={{ fontWeight: 600 }}>{pagaModal.tipo} {pagaModal.numero_fattura || ''}</span>
              </div>
              {pagaModal.fornitore && (
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span style={{ color: '#64748b', fontSize: 13 }}>Fornitore:</span>
                  <span style={{ fontWeight: 500, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{pagaModal.fornitore}</span>
                </div>
              )}
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ color: '#64748b', fontSize: 13 }}>Scadenza:</span>
                <span style={{ fontWeight: 500 }}>{formatDate(pagaModal.data)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b', fontSize: 13 }}>Importo:</span>
                <span style={{ fontWeight: 700, color: '#dc2626', fontSize: 16 }}>{formatEuro(pagaModal.importo)}</span>
              </div>
            </div>

            <p style={{ fontSize: 14, color: '#64748b', marginBottom: 16 }}>
              Scegli il metodo di pagamento. Il movimento verrà registrato in Prima Nota.
            </p>

            <div style={{ display: 'flex', gap: 12, marginBottom: 16, justifyContent: 'center' }}>
              <button
                onClick={() => handlePaga(pagaModal, 'cassa')}
                disabled={processing}
                style={{
                  padding: '14px 24px',
                  background: processing ? '#94a3b8' : '#f59e0b',
                  color: 'white',
                  border: 'none',
                  borderRadius: 10,
                  fontSize: 14,
                  fontWeight: 700,
                  cursor: processing ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 4,
                  minWidth: 140
                }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>💵 CASSA</span>
                <span style={{ fontSize: 10, opacity: 0.9 }}>(pagato subito)</span>
              </button>
              <button
                onClick={() => handlePaga(pagaModal, 'banca')}
                disabled={processing}
                style={{
                  padding: '14px 24px',
                  background: processing ? '#94a3b8' : '#3b82f6',
                  color: 'white',
                  border: 'none',
                  borderRadius: 10,
                  fontSize: 14,
                  fontWeight: 700,
                  cursor: processing ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 4,
                  minWidth: 140
                }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>🏦 BANCA</span>
                <span style={{ fontSize: 10, opacity: 0.9 }}>(da riconciliare)</span>
              </button>
            </div>

            <p style={{ fontSize: 12, color: '#94a3b8', marginBottom: 12, textAlign: 'center' }}>
              💡 Se paghi in <strong>CASSA</strong> la scadenza viene saldata immediatamente.<br/>
              Se paghi in <strong>BANCA</strong> verrà riconciliata quando troveremo il movimento nell&apos;estratto conto.
            </p>

            <button
              onClick={() => setPagaModal(null)}
              style={{
                width: '100%',
                padding: '10px',
                background: '#f1f5f9',
                color: '#64748b',
                border: 'none',
                borderRadius: 8,
                fontSize: 13,
                cursor: 'pointer'
              }}
            >
              Annulla
            </button>
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
        background: 'linear-gradient(135deg, #fff7ed 0%, #fef3c7 100%)',
        border: '1px solid #fcd34d',
        borderLeft: '4px solid #f59e0b',
        borderRadius: 10,
        padding: '14px 18px',
        marginBottom: 12,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 12
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: '1 1 300px' }}>
        <span style={{ fontSize: 22 }}>📋</span>
        <div>
          <div style={{ fontWeight: 700, fontSize: 14, color: '#92400e' }}>
            Pagamenti in attesa di riconciliazione bancaria
          </div>
          <div style={{ fontSize: 12, color: '#78350f', marginTop: 2, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            {buste.length > 0 && (
              <span>
                <strong>{buste.length}</strong> {buste.length === 1 ? 'stipendio' : 'stipendi'} — {formatEuro(totStip)}
              </span>
            )}
            {f24list.length > 0 && (
              <span>
                <strong>{f24list.length}</strong> {f24list.length === 1 ? 'F24' : 'F24'} — {formatEuro(totF24)}
              </span>
            )}
            <span style={{ color: '#92400e', fontWeight: 700 }}>
              Totale: {formatEuro(totale)}
            </span>
          </div>
          <div style={{ fontSize: 11, color: '#a16207', marginTop: 4 }}>
            Carica l'estratto conto in "Import Documenti" per riconciliare automaticamente
          </div>
        </div>
      </div>
      <Link
        to="/paghe"
        data-testid="link-vai-paghe"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '8px 16px',
          background: '#f59e0b',
          color: 'white',
          borderRadius: 8,
          textDecoration: 'none',
          fontSize: 13,
          fontWeight: 700,
          whiteSpace: 'nowrap',
          boxShadow: '0 2px 4px rgba(245,158,11,0.3)'
        }}
      >
        Vai a Paghe →
      </Link>
    </div>
  );
}

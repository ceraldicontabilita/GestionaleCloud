import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { formatEuro, STYLES, COLORS, button, badge } from '../lib/utils';
import { FileText } from 'lucide-react';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';

const styles = {
  page: { minHeight: '100vh', background: '#0f172a', padding: 24 },
  loading: { minHeight: '100vh', background: '#0f172a', padding: 24, display: 'flex', alignItems: 'center', justifyContent: 'center' },
  loadingText: { color: 'white', fontSize: 20 },
  header: { marginBottom: 24, display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 },
  title: { fontSize: 28, fontWeight: 'bold', color: 'white', marginBottom: 8 },
  subtitle: { color: '#94a3b8', fontSize: 14 },
  headerRight: { display: 'flex', alignItems: 'center', gap: 12 },
  badge: { background: 'rgba(30, 64, 175, 0.5)', color: '#93c5fd', padding: '4px 12px', borderRadius: 8, fontSize: 14 },
  btnPrimary: { display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px', background: '#dc2626', color: 'white', borderRadius: 8, border: 'none', cursor: 'pointer', fontWeight: '500' },
  btnBlue: { padding: '8px 16px', background: '#1535a8', color: 'white', borderRadius: 8, border: 'none', cursor: 'pointer', fontWeight: '500' },
  btnPurple: { padding: '8px 16px', background: '#9333ea', color: 'white', borderRadius: 8, border: 'none', cursor: 'pointer', fontWeight: '500' },
  messageSuccess: { marginBottom: 16, padding: 16, borderRadius: 8, background: 'rgba(22, 101, 52, 0.5)', color: '#86efac' },
  messageError: { marginBottom: 16, padding: 16, borderRadius: 8, background: 'rgba(153, 27, 27, 0.5)', color: '#fca5a5' },
  tabs: { display: 'flex', gap: 8, marginBottom: 24 },
  tab: (active) => ({
    padding: '8px 16px', borderRadius: 8, fontWeight: '500', border: 'none', cursor: 'pointer',
    background: active ? '#1535a8' : '#1e293b', color: active ? 'white' : '#cbd5e1'
  }),
  card: { background: '#1e293b', borderRadius: 12, padding: 20, marginBottom: 16 },
  cardDark: { background: 'rgba(30, 41, 59, 0.5)', borderRadius: 12, padding: 16, marginBottom: 16 },
  cardGradient: (from, to) => ({
    background: `linear-gradient(to bottom right, ${from}, ${to})`, borderRadius: 12, padding: 20
  }),
  row: { display: 'flex', alignItems: 'center', gap: 16 },
  grid4: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 },
  grid3: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 },
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 },
  label: { color: 'white', fontWeight: '500' },
  select: { background: '#334155', color: 'white', padding: '8px 16px', borderRadius: 8, border: '1px solid #475569' },
  statLabel: (color) => ({ color: color, fontSize: 14, marginBottom: 4 }),
  statValue: { color: 'white', fontSize: 24, fontWeight: 'bold' },
  statValueLg: { color: 'white', fontSize: 28, fontWeight: 'bold' },
  sectionTitle: { fontSize: 18, fontWeight: 'bold', color: 'white', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 },
  table: { width: '100%', fontSize: 14, borderCollapse: 'collapse' },
  th: { textAlign: 'left', padding: '12px 8px', color: '#94a3b8', borderBottom: '1px solid #334155' },
  thRight: { textAlign: 'right', padding: '12px 8px', color: '#94a3b8', borderBottom: '1px solid #334155' },
  td: { padding: '8px', color: '#cbd5e1', borderBottom: '1px solid #334155' },
  tdRight: { padding: '8px', textAlign: 'right', color: 'white', fontWeight: '500', borderBottom: '1px solid #334155' },
  sectionHeader: (color) => ({ color: color, fontWeight: '500', marginBottom: 12, paddingBottom: 8, borderBottom: '1px solid #334155' }),
  resultBox: { marginTop: 24, padding: 16, background: '#334155', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  icon: { width: 16, height: 16 },
  spaceY: { display: 'flex', flexDirection: 'column', gap: 8 },
  note: { background: 'rgba(30, 41, 59, 0.5)', borderRadius: 12, padding: 16 },
  noteTitle: { fontSize: 14, fontWeight: '500', color: '#cbd5e1', marginBottom: 8 },
  noteList: { fontSize: 12, color: '#94a3b8' }
};

export default function ContabilitaAvanzata() {
  const { anno: selectedYear } = useAnnoGlobale();
  const [imposte, setImposte] = useState(null);
  const [statistiche, setStatistiche] = useState(null);
  const [bilancio, setBilancio] = useState(null);
  const [regione, setRegione] = useState('campania');
  const [aliquoteIrap, setAliquoteIrap] = useState({});
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  // URL Tab Support
  const navigate = useNavigate();
  const location = useLocation();
  
  const getTabFromPath = () => {
    const path = location.pathname;
    const match = path.match(/\/contabilita\/?([\w-]*)/);
    return match && match[1] ? match[1] : 'imposte';
  };
  
  const [activeTab, setActiveTab] = useState(getTabFromPath());
  
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    navigate(`/contabilita/${tabId}`);
  };
  
  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setActiveTab(tab);
  }, [location.pathname]);
  const [message, setMessage] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [impRes, statRes, bilRes, aliqRes] = await Promise.all([
        api.get(`/api/contabilita/calcolo-imposte?regione=${regione}&anno=${selectedYear}`).catch(() => null),
        api.get(`/api/contabilita/statistiche-categorizzazione?anno=${selectedYear}`).catch(() => null),
        api.get(`/api/contabilita/bilancio-dettagliato?anno=${selectedYear}`).catch(() => null),
        api.get(`/api/contabilita/aliquote-irap`).catch(() => null)
      ]);
      if (impRes?.data) setImposte(impRes.data);
      if (statRes?.data) setStatistiche(statRes.data);
      if (bilRes?.data) setBilancio(bilRes.data);
      if (aliqRes?.data) { setAliquoteIrap(aliqRes.data.aliquote || {}); }
    } catch (err) { console.error('Errore caricamento dati:', err); }
    setLoading(false);
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchData(); }, [regione, selectedYear]);

  const handleRicategorizza = async () => {
    
    setProcessing(true); setMessage(null);
    try {
      const res = await api.post('/api/contabilita/ricategorizza-fatture');
      const data = res.data;
      if (data.success) { setMessage({ type: 'success', text: `Ricategorizzate ${data.fatture_processate} fatture. ${data.movimenti_creati} movimenti creati.` }); fetchData(); }
      else { setMessage({ type: 'error', text: 'Errore nella ricategorizzazione' }); }
    } catch (err) { setMessage({ type: 'error', text: err.message }); }
    setProcessing(false);
  };

  const handleInizializzaPiano = async () => {
    setProcessing(true);
    try {
      const res = await api.post('/api/contabilita/inizializza-piano-esteso');
      const data = res.data;
      if (data.success) { setMessage({ type: 'success', text: `Piano dei Conti aggiornato: ${data.conti_aggiunti} nuovi conti aggiunti.` }); }
    } catch (err) { setMessage({ type: 'error', text: err.message }); }
    setProcessing(false);
  };

  const handleDownloadPDF = async () => {
    try {
      const res = await api.get(`/api/contabilita/export/pdf-dichiarazione?anno=${selectedYear}&regione=${regione}`, { responseType: 'blob' });
      if (res.data) {
        const blob = res.data;
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = `dichiarazione_redditi_${selectedYear}.pdf`;
        document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url);
        setMessage({ type: 'success', text: `PDF dichiarazione ${selectedYear} scaricato!` });
      }
    } catch (err) { setMessage({ type: 'error', text: 'Errore download PDF' }); }
  };

  if (loading) {
    return (
      <PageLayout title="Contabilità Avanzata" icon="📈" subtitle="Caricamento...">
        <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>Caricamento dati contabili...</div>
      </PageLayout>
    );
  }

  return (
    <PageLayout title={`Contabilità Avanzata - ${selectedYear}`} icon="📈" subtitle="Calcolo IRES/IRAP e categorizzazione intelligente">
      <div style={{ background: '#0f172a', borderRadius: 12, padding: 20 }} data-testid="contabilita-avanzata-page">
        {/* Header Actions */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginBottom: 20 }}>
          <div style={styles.badge}>📅 Anno: {selectedYear}</div>
          <button onClick={handleDownloadPDF} style={styles.btnPrimary} data-testid="btn-download-pdf">
            <FileText style={styles.icon} /> Scarica PDF
          </button>
        </div>

        {/* Message */}
        {message && <div style={message.type === 'success' ? styles.messageSuccess : styles.messageError}>{message.text}</div>}

        {/* Tabs */}
        <div style={styles.tabs}>
          {['imposte', 'statistiche', 'bilancio'].map((tab) => (
            <button key={tab} onClick={() => setActiveTab(tab)} style={styles.tab(activeTab === tab)} data-testid={`tab-${tab}`}>
              {tab === 'imposte' ? '💰 Calcolo Imposte' : tab === 'statistiche' ? '📊 Statistiche' : '📋 Bilancio Dettagliato'}
            </button>
          ))}
        </div>

        {/* Tab: Imposte */}
        {activeTab === 'imposte' && imposte && (
          <div style={styles.spaceY}>
            {/* Selettore Regione */}
            <div style={{ ...styles.card, ...styles.row }}>
              <label style={styles.label}>Regione IRAP:</label>
              <select value={regione} onChange={(e) => setRegione(e.target.value)} style={styles.select} data-testid="select-regione">
                {Object.keys(aliquoteIrap).sort().map((reg) => (
                  <option key={reg} value={reg}>{reg.charAt(0).toUpperCase() + reg.slice(1).replace(/_/g, ' ')} ({aliquoteIrap[reg]}%)</option>
                ))}
              </select>
              <button onClick={handleRicategorizza} disabled={processing} style={{ ...styles.btnPurple, marginLeft: 'auto', opacity: processing ? 0.5 : 1 }} data-testid="btn-ricategorizza">
                {processing ? '⏳ Elaborazione...' : '🔄 Ricategorizza Fatture'}
              </button>
            </div>

            {/* Cards Riepilogo */}
            <div style={styles.grid4}>
              <div style={styles.cardGradient('#1535a8', '#1535a8')}><p style={styles.statLabel('#bfdbfe')}>Utile Civilistico</p><p style={styles.statValue} data-testid="utile-civilistico">{formatEuro(imposte.utile_civilistico)}</p></div>
              <div style={styles.cardGradient('#ea580c', '#c2410c')}><p style={styles.statLabel('#fed7aa')}>IRES (24%)</p><p style={styles.statValue} data-testid="ires-dovuta">{formatEuro(imposte.ires.imposta_dovuta)}</p></div>
              <div style={styles.cardGradient('#9333ea', '#7c3aed')}><p style={styles.statLabel('#e9d5ff')}>IRAP ({imposte.irap.aliquota}%)</p><p style={styles.statValue} data-testid="irap-dovuta">{formatEuro(imposte.irap.imposta_dovuta)}</p></div>
              <div style={styles.cardGradient('#dc2626', '#b91c1c')}><p style={styles.statLabel('#fecaca')}>Totale Imposte</p><p style={styles.statValue} data-testid="totale-imposte">{formatEuro(imposte.totale_imposte)}</p><p style={{ color: '#fecaca', fontSize: 12, marginTop: 4 }}>Aliquota effettiva: {imposte.aliquota_effettiva}%</p></div>
            </div>

            {/* Dettaglio IRES/IRAP */}
            <div style={styles.grid2}>
              <div style={styles.card}>
                <h3 style={styles.sectionTitle}>📊 Calcolo IRES</h3>
                <table style={styles.table}>
                  <tbody>
                    <tr><td style={styles.td}>Utile civilistico</td><td style={styles.tdRight}>{formatEuro(imposte.utile_civilistico)}</td></tr>
                    {imposte.ires.variazioni_aumento.map((v, i) => (<tr key={i}><td style={{ ...styles.td, color: '#fb923c', paddingLeft: 16 }}>+ {v.descrizione}</td><td style={{ ...styles.tdRight, color: '#fb923c' }}>+{formatEuro(v.importo)}</td></tr>))}
                    {imposte.ires.variazioni_diminuzione.map((v, i) => (<tr key={i}><td style={{ ...styles.td, color: '#4ade80', paddingLeft: 16 }}>- {v.descrizione}</td><td style={{ ...styles.tdRight, color: '#4ade80' }}>-{formatEuro(v.importo)}</td></tr>))}
                    <tr style={{ borderTop: '2px solid #475569' }}><td style={{ ...styles.td, color: 'white', fontWeight: '500' }}>Reddito imponibile</td><td style={{ ...styles.tdRight, fontWeight: 'bold' }}>{formatEuro(imposte.ires.reddito_imponibile)}</td></tr>
                  <tr style={{ background: 'rgba(51, 65, 85, 0.5)' }}><td style={{ ...styles.td, color: 'white', fontWeight: 'bold', padding: 12 }}>IRES DOVUTA (24%)</td><td style={{ ...styles.tdRight, color: '#fb923c', fontWeight: 'bold', fontSize: 18, padding: 12 }}>{formatEuro(imposte.ires.imposta_dovuta)}</td></tr>
                </tbody>
              </table>
            </div>
            <div style={styles.card}>
              <h3 style={styles.sectionTitle}>🏛️ Calcolo IRAP - {regione.charAt(0).toUpperCase() + regione.slice(1).replace(/_/g, ' ')}</h3>
              <table style={styles.table}>
                <tbody>
                  <tr><td style={styles.td}>Valore della produzione</td><td style={styles.tdRight}>{formatEuro(imposte.irap.valore_produzione)}</td></tr>
                  <tr><td style={{ ...styles.td, color: '#4ade80', paddingLeft: 16 }}>- Deduzioni</td><td style={{ ...styles.tdRight, color: '#4ade80' }}>-{formatEuro(imposte.irap.deduzioni)}</td></tr>
                  <tr style={{ borderTop: '2px solid #475569' }}><td style={{ ...styles.td, color: 'white', fontWeight: '500' }}>Base imponibile</td><td style={{ ...styles.tdRight, fontWeight: 'bold' }}>{formatEuro(imposte.irap.base_imponibile)}</td></tr>
                  <tr style={{ background: 'rgba(51, 65, 85, 0.5)' }}><td style={{ ...styles.td, color: 'white', fontWeight: 'bold', padding: 12 }}>IRAP DOVUTA ({imposte.irap.aliquota}%)</td><td style={{ ...styles.tdRight, color: '#c084fc', fontWeight: 'bold', fontSize: 18, padding: 12 }}>{formatEuro(imposte.irap.imposta_dovuta)}</td></tr>
                </tbody>
              </table>
              <div style={{ marginTop: 16, padding: 12, background: 'rgba(51, 65, 85, 0.5)', borderRadius: 8 }}>
                <p style={{ fontSize: 12, color: '#94a3b8' }}>Aliquota IRAP regione {regione}: <strong style={{ color: 'white' }}>{imposte.irap.aliquota}%</strong></p>
              </div>
            </div>
          </div>

          {/* Note */}
          <div style={styles.note}>
            <h4 style={styles.noteTitle}>Note sul calcolo:</h4>
            <ul style={styles.noteList}>{imposte.note.map((nota, i) => (<li key={i} style={{ marginBottom: 4 }}>• {nota}</li>))}</ul>
          </div>
        </div>
      )}

      {/* Tab: Statistiche */}
      {activeTab === 'statistiche' && statistiche && (
        <div style={styles.spaceY}>
          <div style={styles.grid3}>
            <div style={styles.card}><p style={{ color: '#94a3b8', fontSize: 14 }}>Fatture Categorizzate</p><p style={{ fontSize: 28, fontWeight: 'bold', color: '#4ade80' }}>{statistiche.totale_categorizzate}</p></div>
            <div style={styles.card}><p style={{ color: '#94a3b8', fontSize: 14 }}>Non Categorizzate</p><p style={{ fontSize: 28, fontWeight: 'bold', color: '#fb923c' }}>{statistiche.totale_non_categorizzate}</p></div>
            <div style={styles.card}><p style={{ color: '#94a3b8', fontSize: 14 }}>Copertura</p><p style={{ fontSize: 28, fontWeight: 'bold', color: '#60a5fa' }}>{statistiche.percentuale_copertura}%</p></div>
          </div>
          <div style={styles.card}>
            <h3 style={styles.sectionTitle}>📊 Distribuzione per Categoria</h3>
            <div style={{ overflowX: 'auto' }}>
              <table style={styles.table}>
                <thead><tr><th style={styles.th}>Categoria</th><th style={styles.thRight}>Fatture</th><th style={styles.thRight}>Importo Totale</th><th style={styles.thRight}>Ded. IRES</th><th style={styles.thRight}>Ded. IRAP</th></tr></thead>
                <tbody>
                  {statistiche.distribuzione_categorie.map((cat, i) => (
                    <tr key={i} style={{ background: i % 2 === 0 ? 'transparent' : 'rgba(51, 65, 85, 0.3)' }}>
                      <td style={{ ...styles.td, color: 'white', fontWeight: '500', textTransform: 'capitalize' }}>{cat.categoria.replace(/_/g, ' ')}</td>
                      <td style={{ ...styles.td, textAlign: 'right' }}>{cat.numero_fatture}</td>
                      <td style={styles.tdRight}>{formatEuro(cat.importo_totale)}</td>
                      <td style={{ ...styles.td, textAlign: 'right', color: cat.deducibilita_media_ires < 100 ? '#fb923c' : '#4ade80' }}>{cat.deducibilita_media_ires}%</td>
                      <td style={{ ...styles.td, textAlign: 'right', color: cat.deducibilita_media_irap < 100 ? '#fb923c' : '#4ade80' }}>{cat.deducibilita_media_irap}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 16 }}>
            <button onClick={handleInizializzaPiano} disabled={processing} style={{ ...styles.btnBlue, opacity: processing ? 0.5 : 1 }}>📋 Aggiorna Piano dei Conti</button>
            <button onClick={handleRicategorizza} disabled={processing} style={{ ...styles.btnPurple, opacity: processing ? 0.5 : 1 }}>🔄 Ricategorizza Tutte le Fatture</button>
          </div>
        </div>
      )}

      {/* Tab: Bilancio */}
      {activeTab === 'bilancio' && bilancio && (
        <div style={styles.spaceY}>
          <div style={styles.card}>
            <h3 style={styles.sectionTitle}>📈 Conto Economico</h3>
            <div style={styles.grid2}>
              <div>
                <h4 style={styles.sectionHeader('#4ade80')}>RICAVI</h4>
                <div style={styles.spaceY}>
                  {bilancio.conto_economico.ricavi.voci.filter(v => v.saldo > 0).map((voce, i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}><span style={{ color: '#cbd5e1' }}>{voce.codice} - {voce.nome}</span><span style={{ color: '#4ade80', fontWeight: '500' }}>{formatEuro(voce.saldo)}</span></div>
                  ))}
                  <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 8, borderTop: '1px solid #475569' }}><span style={{ color: 'white', fontWeight: 'bold' }}>TOTALE RICAVI</span><span style={{ color: '#4ade80', fontWeight: 'bold' }}>{formatEuro(bilancio.conto_economico.ricavi.totale)}</span></div>
                </div>
              </div>
              <div>
                <h4 style={styles.sectionHeader('#f87171')}>COSTI</h4>
                <div style={{ ...styles.spaceY, maxHeight: 400, overflowY: 'auto' }}>
                  {bilancio.conto_economico.costi.voci.filter(v => v.saldo > 0).slice(0, 15).map((voce, i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
                      <span style={{ color: '#cbd5e1', flex: 1 }}>{voce.codice} - {voce.nome}</span>
                      <span style={{ color: '#f87171', fontWeight: '500', marginLeft: 8 }}>{formatEuro(voce.saldo)}</span>
                      {voce.deducibilita_ires < 100 && <span style={{ color: '#fb923c', fontSize: 12, marginLeft: 8 }}>({voce.deducibilita_ires}%)</span>}
                    </div>
                  ))}
                  <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 8, borderTop: '1px solid #475569' }}><span style={{ color: 'white', fontWeight: 'bold' }}>TOTALE COSTI</span><span style={{ color: '#f87171', fontWeight: 'bold' }}>{formatEuro(bilancio.conto_economico.costi.totale)}</span></div>
                </div>
              </div>
            </div>
            <div style={styles.resultBox}>
              <span style={{ fontSize: 20, fontWeight: 'bold', color: 'white' }}>UTILE/PERDITA DI ESERCIZIO</span>
              <span style={{ fontSize: 24, fontWeight: 'bold', color: bilancio.conto_economico.utile_ante_imposte >= 0 ? '#4ade80' : '#f87171' }}>{formatEuro(bilancio.conto_economico.utile_ante_imposte)}</span>
            </div>
            <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div style={{ padding: 12, background: 'rgba(51, 65, 85, 0.5)', borderRadius: 8 }}><p style={{ color: '#94a3b8', fontSize: 12 }}>Costi deducibili IRES</p><p style={{ color: 'white', fontWeight: 'bold' }}>{formatEuro(bilancio.conto_economico.costi.totale_deducibile_ires)}</p></div>
              <div style={{ padding: 12, background: 'rgba(51, 65, 85, 0.5)', borderRadius: 8 }}><p style={{ color: '#94a3b8', fontSize: 12 }}>Costi deducibili IRAP</p><p style={{ color: 'white', fontWeight: 'bold' }}>{formatEuro(bilancio.conto_economico.costi.totale_deducibile_irap)}</p></div>
            </div>
          </div>
          <div style={styles.card}>
            <h3 style={styles.sectionTitle}>🏦 Stato Patrimoniale</h3>
            <div style={styles.grid2}>
              <div>
                <h4 style={styles.sectionHeader('#60a5fa')}>ATTIVO</h4>
                <div style={styles.spaceY}>
                  {bilancio.stato_patrimoniale.attivo.voci.filter(v => v.saldo !== 0).map((voce, i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}><span style={{ color: '#cbd5e1' }}>{voce.codice} - {voce.nome}</span><span style={{ color: '#60a5fa', fontWeight: '500' }}>{formatEuro(voce.saldo)}</span></div>
                  ))}
                  <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 8, borderTop: '1px solid #475569' }}><span style={{ color: 'white', fontWeight: 'bold' }}>TOTALE ATTIVO</span><span style={{ color: '#60a5fa', fontWeight: 'bold' }}>{formatEuro(bilancio.stato_patrimoniale.attivo.totale)}</span></div>
                </div>
              </div>
              <div>
                <h4 style={styles.sectionHeader('#c084fc')}>PASSIVO + PN</h4>
                <div style={styles.spaceY}>
                  {bilancio.stato_patrimoniale.passivo.voci.filter(v => v.saldo !== 0).map((voce, i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}><span style={{ color: '#cbd5e1' }}>{voce.codice} - {voce.nome}</span><span style={{ color: '#c084fc', fontWeight: '500' }}>{formatEuro(voce.saldo)}</span></div>
                  ))}
                  <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 8, borderTop: '1px solid #475569' }}><span style={{ color: 'white', fontWeight: 'bold' }}>TOTALE PASSIVO</span><span style={{ color: '#c084fc', fontWeight: 'bold' }}>{formatEuro(bilancio.stato_patrimoniale.passivo.totale)}</span></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
      </div>
    </PageLayout>
  );
}

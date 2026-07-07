import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { formatEuro, STYLES, COLORS, button, badge, useIsMobile, RG, pagePad } from '../lib/utils';
import { FileText } from 'lucide-react';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';

const MONO = 'ui-monospace, SFMono-Regular, Menlo, monospace';

const styles = {
  page: { minHeight: '100vh', background: '#f1f5f9', padding: 24 },
  loading: {
    minHeight: '100vh',
    background: '#f1f5f9',
    padding: 24,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  loadingText: { color: '#1e293b', fontSize: 20 },
  header: {
    marginBottom: 24,
    display: 'flex',
    flexWrap: 'wrap',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 16,
  },
  title: { fontSize: 28, fontWeight: 'bold', color: '#1e293b', marginBottom: 8 },
  subtitle: { color: '#64748b', fontSize: 14 },
  headerRight: { display: 'flex', alignItems: 'center', gap: 12 },
  badge: {
    background: 'white',
    border: '1px solid #e2e8f0',
    color: '#0f2744',
    padding: '8px 12px',
    borderRadius: 6,
    fontSize: 13,
    fontWeight: 600,
    display: 'flex',
    alignItems: 'center',
  },
  btnPrimary: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 16px',
    minHeight: 40,
    background: '#0f2744',
    color: 'white',
    borderRadius: 6,
    border: 'none',
    cursor: 'pointer',
    fontWeight: '500',
    fontSize: 13,
  },
  btnBlue: {
    padding: '8px 16px',
    minHeight: 40,
    background: '#0f2744',
    color: 'white',
    borderRadius: 6,
    border: 'none',
    cursor: 'pointer',
    fontWeight: '500',
    fontSize: 13,
  },
  btnPurple: {
    padding: '8px 16px',
    minHeight: 40,
    background: 'white',
    color: '#0f2744',
    borderRadius: 6,
    border: '1px solid #e2e8f0',
    cursor: 'pointer',
    fontWeight: '500',
    fontSize: 13,
  },
  messageSuccess: {
    marginBottom: 16,
    padding: 16,
    borderRadius: 8,
    background: '#f0fdf4',
    border: '1px solid #86efac',
    color: '#166534',
  },
  messageError: {
    marginBottom: 16,
    padding: 16,
    borderRadius: 8,
    background: '#fef2f2',
    border: '1px solid #fca5a5',
    color: '#dc2626',
  },
  tabs: { display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' },
  tab: active => ({
    padding: '8px 16px',
    minHeight: 40,
    borderRadius: 6,
    fontWeight: '600',
    fontSize: 13,
    border: active ? 'none' : '1px solid #e2e8f0',
    cursor: 'pointer',
    background: active ? '#0f2744' : 'white',
    color: active ? 'white' : '#64748b',
  }),
  card: {
    background: 'white',
    border: '1px solid #e2e8f0',
    borderRadius: 8,
    padding: 20,
    marginBottom: 16,
  },
  cardDark: {
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: 8,
    padding: 16,
    marginBottom: 16,
  },
  cardGradient: (from, to) => ({
    background: 'white',
    border: '1px solid #e2e8f0',
    borderLeft: '4px solid #0f2744',
    borderRadius: 8,
    padding: 20,
  }),
  row: { display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' },
  grid4: isMobile => ({
    display: 'grid',
    gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)',
    gap: 16,
  }),
  grid3: isMobile => ({
    display: 'grid',
    gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)',
    gap: 16,
  }),
  grid2: isMobile => ({
    display: 'grid',
    gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
    gap: 24,
  }),
  label: { color: '#1e293b', fontWeight: '500', fontSize: 13 },
  select: {
    background: 'white',
    color: '#1e293b',
    padding: '8px 16px',
    minHeight: 40,
    borderRadius: 6,
    border: '1px solid #e2e8f0',
    fontSize: 13,
  },
  statLabel: color => ({
    color: '#64748b',
    fontSize: 11,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 4,
  }),
  statValue: { color: '#0f2744', fontSize: 22, fontWeight: 700, fontFamily: MONO },
  statValueLg: { color: '#0f2744', fontSize: 24, fontWeight: 700, fontFamily: MONO },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1e293b',
    marginBottom: 16,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  table: { width: '100%', fontSize: 13, borderCollapse: 'collapse' },
  th: {
    textAlign: 'left',
    padding: '10px 8px',
    color: '#64748b',
    fontSize: 11,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    background: '#f8fafc',
    borderBottom: '1px solid #e2e8f0',
  },
  thRight: {
    textAlign: 'right',
    padding: '10px 8px',
    color: '#64748b',
    fontSize: 11,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    background: '#f8fafc',
    borderBottom: '1px solid #e2e8f0',
  },
  td: { padding: '8px', color: '#1e293b', borderBottom: '1px solid #f1f5f9' },
  tdRight: {
    padding: '8px',
    textAlign: 'right',
    color: '#1e293b',
    fontWeight: '500',
    fontFamily: MONO,
    borderBottom: '1px solid #f1f5f9',
  },
  sectionHeader: color => ({
    color: color,
    fontWeight: '600',
    marginBottom: 12,
    paddingBottom: 8,
    borderBottom: '1px solid #e2e8f0',
  }),
  resultBox: {
    marginTop: 24,
    padding: 16,
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderLeft: '4px solid #0f2744',
    borderRadius: 8,
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 8,
  },
  icon: { width: 16, height: 16 },
  spaceY: { display: 'flex', flexDirection: 'column', gap: 8 },
  note: {
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: 8,
    padding: 16,
  },
  noteTitle: { fontSize: 14, fontWeight: '500', color: '#1e293b', marginBottom: 8 },
  noteList: { fontSize: 12, color: '#64748b' },
};

export default function ContabilitaAvanzata() {
  const isMobile = useIsMobile();
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

  const handleTabChange = tabId => {
    setActiveTab(tabId);
    navigate(`/contabilita/${tabId}`);
  };

  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setActiveTab(tab);
  }, [location.pathname]);
  const [message, setMessage] = useState(null);
  const [disponibilita, setDisponibilita] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [impRes, statRes, bilRes, aliqRes, dispRes] = await Promise.all([
        api
          .get(`/api/contabilita/calcolo-imposte?regione=${regione}&anno=${selectedYear}`)
          .catch(() => null),
        api
          .get(`/api/contabilita/statistiche-categorizzazione?anno=${selectedYear}`)
          .catch(() => null),
        api.get(`/api/contabilita/bilancio-dettagliato?anno=${selectedYear}`).catch(() => null),
        api.get(`/api/contabilita/aliquote-irap`).catch(() => null),
        api.get(`/api/contabilita/disponibilita-liquide?anno=${selectedYear}`).catch(() => null),
      ]);
      if (impRes?.data) setImposte(impRes.data);
      if (statRes?.data) setStatistiche(statRes.data);
      if (bilRes?.data) setBilancio(bilRes.data);
      if (aliqRes?.data) {
        setAliquoteIrap(aliqRes.data.aliquote || {});
      }
      if (dispRes?.data) setDisponibilita(dispRes.data);
    } catch (err) {
      console.error('Errore caricamento dati:', err);
    }
    setLoading(false);
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    fetchData();
  }, [regione, selectedYear]);

  const handleRicategorizza = async () => {
    setProcessing(true);
    setMessage(null);
    try {
      const res = await api.post('/api/contabilita/ricategorizza-fatture');
      const data = res.data;
      if (data.success) {
        setMessage({
          type: 'success',
          text: `Ricategorizzate ${data.fatture_processate} fatture. ${data.movimenti_creati} movimenti creati.`,
        });
        fetchData();
      } else {
        setMessage({ type: 'error', text: 'Errore nella ricategorizzazione' });
      }
    } catch (err) {
      setMessage({ type: 'error', text: err.message });
    }
    setProcessing(false);
  };

  const handleInizializzaPiano = async () => {
    setProcessing(true);
    try {
      const res = await api.post('/api/contabilita/inizializza-piano-esteso');
      const data = res.data;
      if (data.success) {
        setMessage({
          type: 'success',
          text: `Piano dei Conti aggiornato: ${data.conti_aggiunti} nuovi conti aggiunti.`,
        });
      }
    } catch (err) {
      setMessage({ type: 'error', text: err.message });
    }
    setProcessing(false);
  };

  const handleDownloadPDF = async () => {
    try {
      const res = await api.get(
        `/api/contabilita/export/pdf-dichiarazione?anno=${selectedYear}&regione=${regione}`,
        { responseType: 'blob' }
      );
      if (res.data) {
        const blob = res.data;
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `dichiarazione_redditi_${selectedYear}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        setMessage({ type: 'success', text: `PDF dichiarazione ${selectedYear} scaricato!` });
      }
    } catch (err) {
      setMessage({ type: 'error', text: 'Errore download PDF' });
    }
  };

  if (loading) {
    return (
      <PageLayout title="Contabilità Avanzata" icon="📈" subtitle="Caricamento...">
        <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>
          Caricamento dati contabili...
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout
      title={`Contabilità Avanzata - ${selectedYear}`}
      icon="📈"
      subtitle="Calcolo IRES/IRAP e categorizzazione intelligente"
    >
      <div data-testid="contabilita-avanzata-page">
        {/* Header Actions */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 12,
            marginBottom: 20,
            flexWrap: 'wrap',
          }}
        >
          <div style={styles.badge}>📅 Anno: {selectedYear}</div>
          <button
            onClick={handleDownloadPDF}
            style={styles.btnPrimary}
            data-testid="btn-download-pdf"
          >
            <FileText style={styles.icon} /> Scarica PDF
          </button>
        </div>

        {/* Message */}
        {message && (
          <div style={message.type === 'success' ? styles.messageSuccess : styles.messageError}>
            {message.text}
          </div>
        )}

        {/* Card Disponibilità Liquide */}
        {disponibilita && (
          <div
            data-testid="disponibilita-liquide-card"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: 16,
              marginBottom: 24,
            }}
          >
            <div
              style={{
                background: 'white',
                borderRadius: 8,
                border: '1px solid #e2e8f0',
                borderLeft: '4px solid #0f2744',
                padding: 16,
                color: '#1e293b',
              }}
            >
              <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
                💶 Disponibilità Liquide (Cassa + Banca)
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#16a34a', fontFamily: MONO }}>
                {formatEuro(disponibilita.totale_disponibilita_liquide || 0)}
              </div>
              <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
                al {disponibilita.data_riferimento}
              </div>
            </div>
            <div
              style={{
                background: 'white',
                borderRadius: 8,
                border: '1px solid #e2e8f0',
                borderLeft: '4px solid #0f2744',
                padding: 16,
                color: '#1e293b',
              }}
            >
              <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>💵 Cassa</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: '#0f2744', fontFamily: MONO }}>
                {formatEuro(disponibilita.cassa?.saldo || 0)}
              </div>
              <div style={{ fontSize: 11, color: '#64748b', marginTop: 4, fontFamily: MONO }}>
                E: {formatEuro(disponibilita.cassa?.entrate || 0)} · U:{' '}
                {formatEuro(disponibilita.cassa?.uscite || 0)}
              </div>
            </div>
            <div
              style={{
                background: 'white',
                borderRadius: 8,
                border: '1px solid #e2e8f0',
                borderLeft: '4px solid #0f2744',
                padding: 16,
                color: '#1e293b',
              }}
            >
              <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>🏦 Banca</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: '#0f2744', fontFamily: MONO }}>
                {formatEuro(disponibilita.banca?.saldo || 0)}
              </div>
              <div style={{ fontSize: 11, color: '#64748b', marginTop: 4, fontFamily: MONO }}>
                E: {formatEuro(disponibilita.banca?.entrate || 0)} · U:{' '}
                {formatEuro(disponibilita.banca?.uscite || 0)}
              </div>
            </div>
            <div
              style={{
                background: 'white',
                borderRadius: 8,
                border: '1px solid #e2e8f0',
                borderLeft: '4px solid #0f2744',
                padding: 16,
                color: '#1e293b',
              }}
            >
              <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
                ⇄ Versamenti (Cassa → Banca)
              </div>
              <div style={{ fontSize: 22, fontWeight: 700, color: '#0f2744', fontFamily: MONO }}>
                {formatEuro(disponibilita.versamenti_cassa_to_banca?.totale || 0)}
              </div>
              <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
                {disponibilita.versamenti_cassa_to_banca?.operazioni || 0} operazioni nel{' '}
                {disponibilita.anno}
              </div>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div style={styles.tabs}>
          {['imposte', 'statistiche', 'bilancio'].map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={styles.tab(activeTab === tab)}
              data-testid={`tab-${tab}`}
            >
              {tab === 'imposte'
                ? 'Calcolo Imposte'
                : tab === 'statistiche'
                  ? 'Statistiche'
                  : 'Bilancio Dettagliato'}
            </button>
          ))}
        </div>

        {/* Tab: Imposte */}
        {activeTab === 'imposte' && imposte && (
          <div style={styles.spaceY}>
            {/* Selettore Regione */}
            <div style={{ ...styles.card, ...styles.row }}>
              <label style={styles.label}>Regione IRAP:</label>
              <select
                value={regione}
                onChange={e => setRegione(e.target.value)}
                style={styles.select}
                data-testid="select-regione"
              >
                {Object.keys(aliquoteIrap)
                  .sort()
                  .map(reg => (
                    <option key={reg} value={reg}>
                      {reg.charAt(0).toUpperCase() + reg.slice(1).replace(/_/g, ' ')} (
                      {aliquoteIrap[reg]}%)
                    </option>
                  ))}
              </select>
              <button
                onClick={handleRicategorizza}
                disabled={processing}
                style={{ ...styles.btnPurple, marginLeft: 'auto', opacity: processing ? 0.5 : 1 }}
                data-testid="btn-ricategorizza"
              >
                {processing ? '⏳ Elaborazione...' : '🔄 Ricategorizza Fatture'}
              </button>
            </div>

            {/* Cards Riepilogo */}
            <div style={styles.grid4(isMobile)}>
              <div style={styles.cardGradient()}>
                <p style={styles.statLabel('#64748b')}>Utile Civilistico</p>
                <p style={styles.statValue} data-testid="utile-civilistico">
                  {formatEuro(imposte.utile_civilistico)}
                </p>
              </div>
              <div style={styles.cardGradient()}>
                <p style={styles.statLabel('#64748b')}>IRES (24%)</p>
                <p style={styles.statValue} data-testid="ires-dovuta">
                  {formatEuro(imposte.ires.imposta_dovuta)}
                </p>
              </div>
              <div style={styles.cardGradient()}>
                <p style={styles.statLabel('#64748b')}>IRAP ({imposte.irap.aliquota}%)</p>
                <p style={styles.statValue} data-testid="irap-dovuta">
                  {formatEuro(imposte.irap.imposta_dovuta)}
                </p>
              </div>
              <div style={styles.cardGradient()}>
                <p style={styles.statLabel('#64748b')}>Totale Imposte</p>
                <p style={styles.statValue} data-testid="totale-imposte">
                  {formatEuro(imposte.totale_imposte)}
                </p>
                <p style={{ color: '#64748b', fontSize: 12, marginTop: 4 }}>
                  Aliquota effettiva: {imposte.aliquota_effettiva}%
                </p>
              </div>
            </div>

            {/* Dettaglio IRES/IRAP */}
            <div style={styles.grid2(isMobile)}>
              <div style={styles.card}>
                <h3 style={styles.sectionTitle}>📊 Calcolo IRES</h3>
                <div style={{ overflowX: 'auto' }}>
                <table style={styles.table}>
                  <tbody>
                    <tr>
                      <td style={styles.td}>Utile civilistico</td>
                      <td style={styles.tdRight}>{formatEuro(imposte.utile_civilistico)}</td>
                    </tr>
                    {imposte.ires.variazioni_aumento.map((v, i) => (
                      <tr key={i}>
                        <td style={{ ...styles.td, color: '#d97706', paddingLeft: 16 }}>
                          + {v.descrizione}
                        </td>
                        <td style={{ ...styles.tdRight, color: '#d97706' }}>
                          +{formatEuro(v.importo)}
                        </td>
                      </tr>
                    ))}
                    {imposte.ires.variazioni_diminuzione.map((v, i) => (
                      <tr key={i}>
                        <td style={{ ...styles.td, color: '#16a34a', paddingLeft: 16 }}>
                          - {v.descrizione}
                        </td>
                        <td style={{ ...styles.tdRight, color: '#16a34a' }}>
                          -{formatEuro(v.importo)}
                        </td>
                      </tr>
                    ))}
                    <tr style={{ borderTop: '2px solid #e2e8f0' }}>
                      <td style={{ ...styles.td, color: '#1e293b', fontWeight: '500' }}>
                        Reddito imponibile
                      </td>
                      <td style={{ ...styles.tdRight, fontWeight: 'bold' }}>
                        {formatEuro(imposte.ires.reddito_imponibile)}
                      </td>
                    </tr>
                    <tr style={{ background: '#f8fafc' }}>
                      <td style={{ ...styles.td, color: '#1e293b', fontWeight: 'bold', padding: 12 }}>
                        IRES DOVUTA (24%)
                      </td>
                      <td
                        style={{
                          ...styles.tdRight,
                          color: '#b8860b',
                          fontWeight: 'bold',
                          fontSize: 18,
                          padding: 12,
                        }}
                      >
                        {formatEuro(imposte.ires.imposta_dovuta)}
                      </td>
                    </tr>
                  </tbody>
                </table>
                </div>
              </div>
              <div style={styles.card}>
                <h3 style={styles.sectionTitle}>
                  🏛️ Calcolo IRAP -{' '}
                  {regione.charAt(0).toUpperCase() + regione.slice(1).replace(/_/g, ' ')}
                </h3>
                <div style={{ overflowX: 'auto' }}>
                <table style={styles.table}>
                  <tbody>
                    <tr>
                      <td style={styles.td}>Valore della produzione</td>
                      <td style={styles.tdRight}>{formatEuro(imposte.irap.valore_produzione)}</td>
                    </tr>
                    <tr>
                      <td style={{ ...styles.td, color: '#16a34a', paddingLeft: 16 }}>
                        - Deduzioni
                      </td>
                      <td style={{ ...styles.tdRight, color: '#16a34a' }}>
                        -{formatEuro(imposte.irap.deduzioni)}
                      </td>
                    </tr>
                    <tr style={{ borderTop: '2px solid #e2e8f0' }}>
                      <td style={{ ...styles.td, color: '#1e293b', fontWeight: '500' }}>
                        Base imponibile
                      </td>
                      <td style={{ ...styles.tdRight, fontWeight: 'bold' }}>
                        {formatEuro(imposte.irap.base_imponibile)}
                      </td>
                    </tr>
                    <tr style={{ background: '#f8fafc' }}>
                      <td style={{ ...styles.td, color: '#1e293b', fontWeight: 'bold', padding: 12 }}>
                        IRAP DOVUTA ({imposte.irap.aliquota}%)
                      </td>
                      <td
                        style={{
                          ...styles.tdRight,
                          color: '#b8860b',
                          fontWeight: 'bold',
                          fontSize: 18,
                          padding: 12,
                        }}
                      >
                        {formatEuro(imposte.irap.imposta_dovuta)}
                      </td>
                    </tr>
                  </tbody>
                </table>
                </div>
                <div
                  style={{
                    marginTop: 16,
                    padding: 12,
                    background: '#f8fafc',
                    borderRadius: 8,
                  }}
                >
                  <p style={{ fontSize: 12, color: '#64748b' }}>
                    Aliquota IRAP regione {regione}:{' '}
                    <strong style={{ color: '#1e293b' }}>{imposte.irap.aliquota}%</strong>
                  </p>
                </div>
              </div>
            </div>

            {/* Note */}
            <div style={styles.note}>
              <h4 style={styles.noteTitle}>Note sul calcolo:</h4>
              <ul style={styles.noteList}>
                {imposte.note.map((nota, i) => (
                  <li key={i} style={{ marginBottom: 4 }}>
                    • {nota}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {/* Tab: Statistiche */}
        {activeTab === 'statistiche' && statistiche && (
          <div style={styles.spaceY}>
            <div style={styles.grid3(isMobile)}>
              <div style={styles.card}>
                <p style={{ color: '#64748b', fontSize: 14 }}>Fatture Categorizzate</p>
                <p style={{ fontSize: 24, fontWeight: 700, color: '#16a34a', fontFamily: MONO }}>
                  {statistiche.totale_categorizzate}
                </p>
              </div>
              <div style={styles.card}>
                <p style={{ color: '#64748b', fontSize: 14 }}>Non Categorizzate</p>
                <p style={{ fontSize: 24, fontWeight: 700, color: '#d97706', fontFamily: MONO }}>
                  {statistiche.totale_non_categorizzate}
                </p>
              </div>
              <div style={styles.card}>
                <p style={{ color: '#64748b', fontSize: 14 }}>Copertura</p>
                <p style={{ fontSize: 24, fontWeight: 700, color: '#3b82f6', fontFamily: MONO }}>
                  {statistiche.percentuale_copertura}%
                </p>
              </div>
            </div>
            <div style={styles.card}>
              <h3 style={styles.sectionTitle}>📊 Distribuzione per Categoria</h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={styles.th}>Categoria</th>
                      <th style={styles.thRight}>Fatture</th>
                      <th style={styles.thRight}>Importo Totale</th>
                      <th style={styles.thRight}>Ded. IRES</th>
                      <th style={styles.thRight}>Ded. IRAP</th>
                    </tr>
                  </thead>
                  <tbody>
                    {statistiche.distribuzione_categorie.map((cat, i) => (
                      <tr
                        key={i}
                        style={{
                          background: i % 2 === 0 ? 'transparent' : '#f8fafc',
                        }}
                      >
                        <td
                          style={{
                            ...styles.td,
                            color: '#1e293b',
                            fontWeight: '500',
                            textTransform: 'capitalize',
                          }}
                        >
                          {cat.categoria.replace(/_/g, ' ')}
                        </td>
                        <td style={{ ...styles.td, textAlign: 'right' }}>{cat.numero_fatture}</td>
                        <td style={styles.tdRight}>{formatEuro(cat.importo_totale)}</td>
                        <td
                          style={{
                            ...styles.td,
                            textAlign: 'right',
                            color: cat.deducibilita_media_ires < 100 ? '#d97706' : '#16a34a',
                          }}
                        >
                          {cat.deducibilita_media_ires}%
                        </td>
                        <td
                          style={{
                            ...styles.td,
                            textAlign: 'right',
                            color: cat.deducibilita_media_irap < 100 ? '#d97706' : '#16a34a',
                          }}
                        >
                          {cat.deducibilita_media_irap}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              <button
                onClick={handleInizializzaPiano}
                disabled={processing}
                style={{ ...styles.btnBlue, opacity: processing ? 0.5 : 1 }}
              >
                📋 Aggiorna Piano dei Conti
              </button>
              <button
                onClick={handleRicategorizza}
                disabled={processing}
                style={{ ...styles.btnPurple, opacity: processing ? 0.5 : 1 }}
              >
                🔄 Ricategorizza Tutte le Fatture
              </button>
            </div>
          </div>
        )}

        {/* Tab: Bilancio */}
        {activeTab === 'bilancio' && bilancio && (
          <div style={styles.spaceY}>
            <div style={styles.card}>
              <h3 style={styles.sectionTitle}>📈 Conto Economico</h3>
              <div style={styles.grid2(isMobile)}>
                <div>
                  <h4 style={styles.sectionHeader('#16a34a')}>RICAVI</h4>
                  <div style={styles.spaceY}>
                    {bilancio.conto_economico.ricavi.voci
                      .filter(v => v.saldo > 0)
                      .map((voce, i) => (
                        <div
                          key={i}
                          style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}
                        >
                          <span style={{ color: '#1e293b' }}>
                            {voce.codice} - {voce.nome}
                          </span>
                          <span style={{ color: '#16a34a', fontWeight: '500', fontFamily: MONO }}>
                            {formatEuro(voce.saldo)}
                          </span>
                        </div>
                      ))}
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        paddingTop: 8,
                        borderTop: '1px solid #e2e8f0',
                      }}
                    >
                      <span style={{ color: '#1e293b', fontWeight: 'bold' }}>TOTALE RICAVI</span>
                      <span style={{ color: '#16a34a', fontWeight: 'bold', fontFamily: MONO }}>
                        {formatEuro(bilancio.conto_economico.ricavi.totale)}
                      </span>
                    </div>
                  </div>
                </div>
                <div>
                  <h4 style={styles.sectionHeader('#dc2626')}>COSTI</h4>
                  <div style={{ ...styles.spaceY, maxHeight: 400, overflowY: 'auto' }}>
                    {bilancio.conto_economico.costi.voci
                      .filter(v => v.saldo > 0)
                      .slice(0, 15)
                      .map((voce, i) => (
                        <div
                          key={i}
                          style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}
                        >
                          <span style={{ color: '#1e293b', flex: 1 }}>
                            {voce.codice} - {voce.nome}
                          </span>
                          <span
                            style={{
                              color: '#dc2626',
                              fontWeight: '500',
                              marginLeft: 8,
                              fontFamily: MONO,
                            }}
                          >
                            {formatEuro(voce.saldo)}
                          </span>
                          {voce.deducibilita_ires < 100 && (
                            <span style={{ color: '#d97706', fontSize: 12, marginLeft: 8 }}>
                              ({voce.deducibilita_ires}%)
                            </span>
                          )}
                        </div>
                      ))}
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        paddingTop: 8,
                        borderTop: '1px solid #e2e8f0',
                      }}
                    >
                      <span style={{ color: '#1e293b', fontWeight: 'bold' }}>TOTALE COSTI</span>
                      <span style={{ color: '#dc2626', fontWeight: 'bold', fontFamily: MONO }}>
                        {formatEuro(bilancio.conto_economico.costi.totale)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
              <div style={styles.resultBox}>
                <span style={{ fontSize: 20, fontWeight: 'bold', color: '#1e293b' }}>
                  UTILE/PERDITA DI ESERCIZIO
                </span>
                <span
                  style={{
                    fontSize: 24,
                    fontWeight: 'bold',
                    fontFamily: MONO,
                    color: bilancio.conto_economico.utile_ante_imposte >= 0 ? '#16a34a' : '#dc2626',
                  }}
                >
                  {formatEuro(bilancio.conto_economico.utile_ante_imposte)}
                </span>
              </div>
              <div
                style={{
                  marginTop: 16,
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                  gap: 16,
                }}
              >
                <div style={{ padding: 12, background: '#f8fafc', borderRadius: 8 }}>
                  <p style={{ color: '#64748b', fontSize: 12 }}>Costi deducibili IRES</p>
                  <p style={{ color: '#0f2744', fontWeight: 'bold', fontFamily: MONO }}>
                    {formatEuro(bilancio.conto_economico.costi.totale_deducibile_ires)}
                  </p>
                </div>
                <div style={{ padding: 12, background: '#f8fafc', borderRadius: 8 }}>
                  <p style={{ color: '#64748b', fontSize: 12 }}>Costi deducibili IRAP</p>
                  <p style={{ color: '#0f2744', fontWeight: 'bold', fontFamily: MONO }}>
                    {formatEuro(bilancio.conto_economico.costi.totale_deducibile_irap)}
                  </p>
                </div>
              </div>
            </div>
            <div style={styles.card}>
              <h3 style={styles.sectionTitle}>🏦 Stato Patrimoniale</h3>
              <div style={styles.grid2(isMobile)}>
                <div>
                  <h4 style={styles.sectionHeader('#3b82f6')}>ATTIVO</h4>
                  <div style={styles.spaceY}>
                    {bilancio.stato_patrimoniale.attivo.voci
                      .filter(v => v.saldo !== 0)
                      .map((voce, i) => (
                        <div
                          key={i}
                          style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}
                        >
                          <span style={{ color: '#1e293b' }}>
                            {voce.codice} - {voce.nome}
                          </span>
                          <span style={{ color: '#3b82f6', fontWeight: '500', fontFamily: MONO }}>
                            {formatEuro(voce.saldo)}
                          </span>
                        </div>
                      ))}
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        paddingTop: 8,
                        borderTop: '1px solid #e2e8f0',
                      }}
                    >
                      <span style={{ color: '#1e293b', fontWeight: 'bold' }}>TOTALE ATTIVO</span>
                      <span style={{ color: '#3b82f6', fontWeight: 'bold', fontFamily: MONO }}>
                        {formatEuro(bilancio.stato_patrimoniale.attivo.totale)}
                      </span>
                    </div>
                  </div>
                </div>
                <div>
                  <h4 style={styles.sectionHeader('#0f2744')}>PASSIVO + PN</h4>
                  <div style={styles.spaceY}>
                    {bilancio.stato_patrimoniale.passivo.voci
                      .filter(v => v.saldo !== 0)
                      .map((voce, i) => (
                        <div
                          key={i}
                          style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}
                        >
                          <span style={{ color: '#1e293b' }}>
                            {voce.codice} - {voce.nome}
                          </span>
                          <span style={{ color: '#0f2744', fontWeight: '500', fontFamily: MONO }}>
                            {formatEuro(voce.saldo)}
                          </span>
                        </div>
                      ))}
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        paddingTop: 8,
                        borderTop: '1px solid #e2e8f0',
                      }}
                    >
                      <span style={{ color: '#1e293b', fontWeight: 'bold' }}>TOTALE PASSIVO</span>
                      <span style={{ color: '#0f2744', fontWeight: 'bold', fontFamily: MONO }}>
                        {formatEuro(bilancio.stato_patrimoniale.passivo.totale)}
                      </span>
                    </div>
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

import { useState, useEffect } from 'react';
import api from '../api';
import { formatEuro, COLORS, SHADOWS, BORDER_RADIUS, FONT, useIsMobile } from '../lib/utils';
import { FileText } from 'lucide-react';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';
import { Button, Badge, StatCard, Card, Select, TableWrap, Table, Th, Td } from '../components/ds';

const styles = {
  loading: { textAlign: 'center', padding: 40, color: COLORS.textMuted },
  headerActions: {
    display: 'flex',
    justifyContent: 'flex-end',
    gap: 12,
    marginBottom: 20,
    flexWrap: 'wrap',
  },
  messageSuccess: {
    marginBottom: 16,
    padding: 16,
    borderRadius: BORDER_RADIUS.md,
    background: COLORS.successLight,
    border: `1px solid ${COLORS.success}`,
    color: COLORS.success,
  },
  messageError: {
    marginBottom: 16,
    padding: 16,
    borderRadius: BORDER_RADIUS.md,
    background: COLORS.dangerLight,
    border: `1px solid ${COLORS.danger}`,
    color: COLORS.danger,
  },
  tabsRow: { display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' },
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
  label: { color: COLORS.text, fontWeight: 500, fontSize: 13 },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: COLORS.text,
    marginBottom: 16,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  sectionHeader: color => ({
    color,
    fontWeight: 600,
    marginBottom: 12,
    paddingBottom: 8,
    borderBottom: `1px solid ${COLORS.border}`,
  }),
  spaceY: { display: 'flex', flexDirection: 'column', gap: 8 },
  note: {
    background: COLORS.bgAlt,
    border: `1px solid ${COLORS.border}`,
    borderRadius: BORDER_RADIUS.md,
    padding: 16,
  },
  noteTitle: { fontSize: 14, fontWeight: 500, color: COLORS.text, marginBottom: 8 },
  noteList: { fontSize: 12, color: COLORS.textMuted },
  miniBox: { padding: 12, background: COLORS.bgAlt, borderRadius: BORDER_RADIUS.md },
  // Stat-box "manuale" usata SOLO dove serve preservare un data-testid sul
  // valore (StatCard non inoltra prop arbitrarie fino al nodo del valore).
  statBox: {
    background: COLORS.card,
    border: `1px solid ${COLORS.border}`,
    borderLeft: `3px solid ${COLORS.primary}`,
    borderRadius: BORDER_RADIUS.md,
    padding: '16px 18px',
    boxShadow: SHADOWS.sm,
  },
  statBoxLabel: {
    fontSize: 11,
    color: COLORS.textMuted,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.4px',
    marginBottom: 6,
  },
  statBoxValue: { fontSize: 22, fontWeight: 700, color: COLORS.primary, fontFamily: FONT.mono },
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
  // Questo componente è montato SOLO come contenuto nested del tab "avanzata"
  // di ContabilitaHub.jsx (nessuna route standalone) — l'URL /contabilita/avanzata
  // è già interamente di competenza dell'Hub. I 3 sotto-tab qui sotto
  // (imposte/statistiche/bilancio) sono stato puramente interno: prima
  // provavano a leggere l'ultimo segmento della stessa URL usata dall'Hub,
  // che vale sempre "avanzata" e non combacia con nessuno dei 3 → la pagina
  // risultava vuota. E un click su un sotto-tab chiamava navigate() verso
  // /contabilita/imposte, un path che l'Hub non riconosce, facendolo
  // ripiegare sul tab "Piano dei Conti" e facendo uscire l'utente da qui.
  const [activeTab, setActiveTab] = useState('imposte');

  const handleTabChange = tabId => {
    setActiveTab(tabId);
  };

  const [message, setMessage] = useState(null);
  const [disponibilita, setDisponibilita] = useState(null);
  // Blocchi il cui endpoint ha risposto con errore: distinti da "nessun dato".
  // Prima ogni errore diventava null in silenzio e la pagina si caricava
  // vuota senza spiegare quale endpoint fosse rotto.
  const [erroriBlocchi, setErroriBlocchi] = useState([]);

  const fetchData = async () => {
    setLoading(true);
    setImposte(null);
    setStatistiche(null);
    setBilancio(null);
    setDisponibilita(null);
    const errori = [];
    const conErrore = nome => e => {
      errori.push(`${nome} (${e?.response?.status || e?.message || 'endpoint non raggiungibile'})`);
      return null;
    };
    const [impRes, statRes, bilRes, aliqRes, dispRes] = await Promise.all([
      api
        .get(`/api/contabilita/calcolo-imposte?regione=${regione}&anno=${selectedYear}`)
        .catch(conErrore('Calcolo imposte')),
      api
        .get(`/api/contabilita/statistiche-categorizzazione?anno=${selectedYear}`)
        .catch(conErrore('Statistiche categorizzazione')),
      api
        .get(`/api/contabilita/bilancio-dettagliato?anno=${selectedYear}`)
        .catch(conErrore('Bilancio dettagliato')),
      api.get(`/api/contabilita/aliquote-irap`).catch(conErrore('Aliquote IRAP')),
      api
        .get(`/api/contabilita/disponibilita-liquide?anno=${selectedYear}`)
        .catch(conErrore('Disponibilità liquide')),
    ]);
    setImposte(impRes?.data ?? null);
    setStatistiche(statRes?.data ?? null);
    setBilancio(bilRes?.data ?? null);
    if (aliqRes?.data) {
      setAliquoteIrap(aliqRes.data.aliquote || {});
    }
    setDisponibilita(dispRes?.data ?? null);
    setErroriBlocchi(errori);
    if (errori.length) console.warn('Contabilità Avanzata, blocchi in errore:', errori);
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
      } else {
        setMessage({ type: 'error', text: 'Aggiornamento Piano dei Conti non riuscito' });
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
        <div style={styles.loading}>Caricamento dati contabili...</div>
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
        <div style={styles.headerActions}>
          <Badge variant="primary">📅 Anno: {selectedYear}</Badge>
          <Button
            variant="primary"
            onClick={handleDownloadPDF}
            iconLeft={<FileText size={16} />}
            data-testid="btn-download-pdf"
          >
            Scarica PDF
          </Button>
        </div>

        {/* Message */}
        {message && (
          <div style={message.type === 'success' ? styles.messageSuccess : styles.messageError}>
            {message.text}
          </div>
        )}

        {/* Blocchi in errore: distinti da "nessun dato" */}
        {erroriBlocchi.length > 0 && (
          <div
            style={{
              padding: '10px 14px',
              background: '#fffbeb',
              border: '1px solid #fcd34d',
              borderRadius: 8,
              color: '#92400e',
              fontSize: 13,
              marginBottom: 14,
            }}
            data-testid="contabilita-avanzata-errori"
          >
            ⚠️ Questi blocchi non sono disponibili per un errore del server (non è
            mancanza di dati): {erroriBlocchi.join(' · ')}
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
            <StatCard
              label="💶 Disponibilità Liquide (Cassa + Banca)"
              value={
                <span style={{ fontFamily: FONT.mono, color: COLORS.success }}>
                  {formatEuro(disponibilita.totale_disponibilita_liquide || 0)}
                </span>
              }
              subtext={`al ${disponibilita.data_riferimento}`}
              accent="primary"
            />
            <StatCard
              label="💵 Cassa"
              value={
                <span style={{ fontFamily: FONT.mono }}>
                  {formatEuro(disponibilita.cassa?.saldo || 0)}
                </span>
              }
              subtext={
                <span style={{ fontFamily: FONT.mono }}>
                  E: {formatEuro(disponibilita.cassa?.entrate || 0)} · U:{' '}
                  {formatEuro(disponibilita.cassa?.uscite || 0)}
                </span>
              }
              accent="primary"
            />
            <StatCard
              label="🏦 Banca"
              value={
                <span style={{ fontFamily: FONT.mono }}>
                  {formatEuro(disponibilita.banca?.saldo || 0)}
                </span>
              }
              subtext={
                <span style={{ fontFamily: FONT.mono }}>
                  E: {formatEuro(disponibilita.banca?.entrate || 0)} · U:{' '}
                  {formatEuro(disponibilita.banca?.uscite || 0)}
                </span>
              }
              accent="primary"
            />
            <StatCard
              label="⇄ Versamenti (Cassa → Banca)"
              value={
                <span style={{ fontFamily: FONT.mono }}>
                  {formatEuro(disponibilita.versamenti_cassa_to_banca?.totale || 0)}
                </span>
              }
              subtext={`${disponibilita.versamenti_cassa_to_banca?.operazioni || 0} operazioni nel ${disponibilita.anno}`}
              accent="primary"
            />
          </div>
        )}

        {/* Tabs */}
        <div style={styles.tabsRow}>
          {['imposte', 'statistiche', 'bilancio'].map(tab => (
            <Button
              key={tab}
              variant={activeTab === tab ? 'primary' : 'secondary'}
              onClick={() => setActiveTab(tab)}
              data-testid={`tab-${tab}`}
            >
              {tab === 'imposte'
                ? 'Calcolo Imposte'
                : tab === 'statistiche'
                  ? 'Statistiche'
                  : 'Bilancio Dettagliato'}
            </Button>
          ))}
        </div>

        {/* Tab: Imposte */}
        {activeTab === 'imposte' && imposte && (
          <div style={styles.spaceY}>
            {/* Selettore Regione */}
            <Card style={{ marginBottom: 8 }}>
              <div style={styles.row}>
                <label style={styles.label}>Regione IRAP:</label>
                <Select
                  value={regione}
                  onChange={e => setRegione(e.target.value)}
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
                </Select>
                <Button
                  variant="secondary"
                  onClick={handleRicategorizza}
                  disabled={processing}
                  style={{ marginLeft: 'auto' }}
                  data-testid="btn-ricategorizza"
                >
                  {processing ? '⏳ Elaborazione...' : '🔄 Ricategorizza Fatture'}
                </Button>
              </div>
            </Card>

            {/* Cards Riepilogo */}
            <div style={styles.grid4(isMobile)}>
              <div style={styles.statBox}>
                <p style={styles.statBoxLabel}>Utile Civilistico</p>
                <p style={styles.statBoxValue} data-testid="utile-civilistico">
                  {formatEuro(imposte.utile_civilistico)}
                </p>
              </div>
              <div style={styles.statBox}>
                <p style={styles.statBoxLabel}>IRES (24%)</p>
                <p style={styles.statBoxValue} data-testid="ires-dovuta">
                  {formatEuro(imposte.ires.imposta_dovuta)}
                </p>
              </div>
              <div style={styles.statBox}>
                <p style={styles.statBoxLabel}>IRAP ({imposte.irap.aliquota}%)</p>
                <p style={styles.statBoxValue} data-testid="irap-dovuta">
                  {formatEuro(imposte.irap.imposta_dovuta)}
                </p>
              </div>
              <div style={styles.statBox}>
                <p style={styles.statBoxLabel}>Totale Imposte</p>
                <p style={styles.statBoxValue} data-testid="totale-imposte">
                  {formatEuro(imposte.totale_imposte)}
                </p>
                <p style={{ color: COLORS.textMuted, fontSize: 12, marginTop: 4 }}>
                  Aliquota effettiva: {imposte.aliquota_effettiva}%
                </p>
              </div>
            </div>

            {/* Dettaglio IRES/IRAP */}
            <div style={styles.grid2(isMobile)}>
              <Card>
                <h3 style={styles.sectionTitle}>📊 Calcolo IRES</h3>
                <TableWrap>
                  <Table>
                    <tbody>
                      <tr>
                        <Td>Utile civilistico</Td>
                        <Td align="right" mono>
                          {formatEuro(imposte.utile_civilistico)}
                        </Td>
                      </tr>
                      {imposte.ires.variazioni_aumento.map((v, i) => (
                        <tr key={i}>
                          <Td style={{ color: COLORS.warning, paddingLeft: 16 }}>
                            + {v.descrizione}
                          </Td>
                          <Td align="right" mono style={{ color: COLORS.warning }}>
                            +{formatEuro(v.importo)}
                          </Td>
                        </tr>
                      ))}
                      {imposte.ires.variazioni_diminuzione.map((v, i) => (
                        <tr key={i}>
                          <Td style={{ color: COLORS.success, paddingLeft: 16 }}>
                            - {v.descrizione}
                          </Td>
                          <Td align="right" mono style={{ color: COLORS.success }}>
                            -{formatEuro(v.importo)}
                          </Td>
                        </tr>
                      ))}
                      <tr style={{ borderTop: `2px solid ${COLORS.border}` }}>
                        <Td style={{ fontWeight: 500 }}>Reddito imponibile</Td>
                        <Td align="right" mono style={{ fontWeight: 'bold' }}>
                          {formatEuro(imposte.ires.reddito_imponibile)}
                        </Td>
                      </tr>
                      <tr style={{ background: COLORS.bgAlt }}>
                        <Td style={{ fontWeight: 'bold', padding: 12 }}>IRES DOVUTA (24%)</Td>
                        <Td
                          align="right"
                          mono
                          style={{
                            color: COLORS.accent,
                            fontWeight: 'bold',
                            fontSize: 18,
                            padding: 12,
                          }}
                        >
                          {formatEuro(imposte.ires.imposta_dovuta)}
                        </Td>
                      </tr>
                    </tbody>
                  </Table>
                </TableWrap>
              </Card>
              <Card>
                <h3 style={styles.sectionTitle}>
                  🏛️ Calcolo IRAP -{' '}
                  {regione.charAt(0).toUpperCase() + regione.slice(1).replace(/_/g, ' ')}
                </h3>
                <TableWrap>
                  <Table>
                    <tbody>
                      <tr>
                        <Td>Valore della produzione</Td>
                        <Td align="right" mono>
                          {formatEuro(imposte.irap.valore_produzione)}
                        </Td>
                      </tr>
                      <tr>
                        <Td style={{ color: COLORS.success, paddingLeft: 16 }}>- Deduzioni</Td>
                        <Td align="right" mono style={{ color: COLORS.success }}>
                          -{formatEuro(imposte.irap.deduzioni)}
                        </Td>
                      </tr>
                      <tr style={{ borderTop: `2px solid ${COLORS.border}` }}>
                        <Td style={{ fontWeight: 500 }}>Base imponibile</Td>
                        <Td align="right" mono style={{ fontWeight: 'bold' }}>
                          {formatEuro(imposte.irap.base_imponibile)}
                        </Td>
                      </tr>
                      <tr style={{ background: COLORS.bgAlt }}>
                        <Td style={{ fontWeight: 'bold', padding: 12 }}>
                          IRAP DOVUTA ({imposte.irap.aliquota}%)
                        </Td>
                        <Td
                          align="right"
                          mono
                          style={{
                            color: COLORS.accent,
                            fontWeight: 'bold',
                            fontSize: 18,
                            padding: 12,
                          }}
                        >
                          {formatEuro(imposte.irap.imposta_dovuta)}
                        </Td>
                      </tr>
                    </tbody>
                  </Table>
                </TableWrap>
                <div style={{ ...styles.miniBox, marginTop: 16 }}>
                  <p style={{ fontSize: 12, color: COLORS.textMuted }}>
                    Aliquota IRAP regione {regione}:{' '}
                    <strong style={{ color: COLORS.text }}>{imposte.irap.aliquota}%</strong>
                  </p>
                </div>
              </Card>
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
        {activeTab === 'imposte' && !imposte && (
          <div style={styles.note}>Nessun dato fiscale disponibile per l'anno {selectedYear}.</div>
        )}

        {/* Tab: Statistiche */}
        {activeTab === 'statistiche' && statistiche && (
          <div style={styles.spaceY}>
            <div style={styles.grid3(isMobile)}>
              <StatCard
                label="Fatture Categorizzate"
                value={statistiche.totale_categorizzate}
                accent="success"
              />
              <StatCard
                label="Non Categorizzate"
                value={statistiche.totale_non_categorizzate}
                accent="warning"
              />
              <StatCard
                label="Copertura"
                value={`${statistiche.percentuale_copertura}%`}
                accent="info"
              />
            </div>
            <Card>
              <h3 style={styles.sectionTitle}>📊 Distribuzione per Categoria</h3>
              <TableWrap>
                <Table>
                  <thead>
                    <tr>
                      <Th>Categoria</Th>
                      <Th align="right">Fatture</Th>
                      <Th align="right">Importo Totale</Th>
                      <Th align="right">Ded. IRES</Th>
                      <Th align="right">Ded. IRAP</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {statistiche.distribuzione_categorie.map((cat, i) => (
                      <tr
                        key={i}
                        style={{
                          background: i % 2 === 0 ? 'transparent' : COLORS.bgAlt,
                        }}
                      >
                        <Td style={{ fontWeight: 500, textTransform: 'capitalize' }}>
                          {cat.categoria.replace(/_/g, ' ')}
                        </Td>
                        <Td align="right">{cat.numero_fatture}</Td>
                        <Td align="right" mono>
                          {formatEuro(cat.importo_totale)}
                        </Td>
                        <Td
                          align="right"
                          style={{
                            color:
                              cat.deducibilita_media_ires < 100 ? COLORS.warning : COLORS.success,
                          }}
                        >
                          {cat.deducibilita_media_ires}%
                        </Td>
                        <Td
                          align="right"
                          style={{
                            color:
                              cat.deducibilita_media_irap < 100 ? COLORS.warning : COLORS.success,
                          }}
                        >
                          {cat.deducibilita_media_irap}%
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </TableWrap>
            </Card>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              <Button variant="primary" onClick={handleInizializzaPiano} disabled={processing}>
                📋 Aggiorna Piano dei Conti
              </Button>
              <Button variant="secondary" onClick={handleRicategorizza} disabled={processing}>
                🔄 Ricategorizza Tutte le Fatture
              </Button>
            </div>
          </div>
        )}
        {activeTab === 'statistiche' && !statistiche && (
          <div style={styles.note}>
            Nessuna statistica di categorizzazione disponibile per l'anno {selectedYear}.
          </div>
        )}

        {/* Tab: Bilancio */}
        {activeTab === 'bilancio' && bilancio && (
          <div style={styles.spaceY}>
            <Card>
              <h3 style={styles.sectionTitle}>📈 Conto Economico</h3>
              <div style={styles.grid2(isMobile)}>
                <div>
                  <h4 style={styles.sectionHeader(COLORS.success)}>RICAVI</h4>
                  <div style={styles.spaceY}>
                    {bilancio.conto_economico.ricavi.voci
                      .filter(v => v.saldo > 0)
                      .map((voce, i) => (
                        <div
                          key={i}
                          style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}
                        >
                          <span style={{ color: COLORS.text }}>
                            {voce.codice} - {voce.nome}
                          </span>
                          <span style={{ color: COLORS.success, fontWeight: 500, fontFamily: FONT.mono }}>
                            {formatEuro(voce.saldo)}
                          </span>
                        </div>
                      ))}
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        paddingTop: 8,
                        borderTop: `1px solid ${COLORS.border}`,
                      }}
                    >
                      <span style={{ color: COLORS.text, fontWeight: 'bold' }}>TOTALE RICAVI</span>
                      <span style={{ color: COLORS.success, fontWeight: 'bold', fontFamily: FONT.mono }}>
                        {formatEuro(bilancio.conto_economico.ricavi.totale)}
                      </span>
                    </div>
                  </div>
                </div>
                <div>
                  <h4 style={styles.sectionHeader(COLORS.danger)}>COSTI</h4>
                  <div style={{ ...styles.spaceY, maxHeight: 400, overflowY: 'auto' }}>
                    {bilancio.conto_economico.costi.voci
                      .filter(v => v.saldo > 0)
                      .slice(0, 15)
                      .map((voce, i) => (
                        <div
                          key={i}
                          style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}
                        >
                          <span style={{ color: COLORS.text, flex: 1 }}>
                            {voce.codice} - {voce.nome}
                          </span>
                          <span
                            style={{
                              color: COLORS.danger,
                              fontWeight: 500,
                              marginLeft: 8,
                              fontFamily: FONT.mono,
                            }}
                          >
                            {formatEuro(voce.saldo)}
                          </span>
                          {voce.deducibilita_ires < 100 && (
                            <span style={{ color: COLORS.warning, fontSize: 12, marginLeft: 8 }}>
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
                        borderTop: `1px solid ${COLORS.border}`,
                      }}
                    >
                      <span style={{ color: COLORS.text, fontWeight: 'bold' }}>TOTALE COSTI</span>
                      <span style={{ color: COLORS.danger, fontWeight: 'bold', fontFamily: FONT.mono }}>
                        {formatEuro(bilancio.conto_economico.costi.totale)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
              <div
                style={{
                  marginTop: 24,
                  padding: 16,
                  background: COLORS.bgAlt,
                  border: `1px solid ${COLORS.border}`,
                  borderLeft: `4px solid ${COLORS.primary}`,
                  borderRadius: BORDER_RADIUS.md,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: 8,
                }}
              >
                <span style={{ fontSize: 20, fontWeight: 'bold', color: COLORS.text }}>
                  UTILE/PERDITA DI ESERCIZIO
                </span>
                <span
                  style={{
                    fontSize: 24,
                    fontWeight: 'bold',
                    fontFamily: FONT.mono,
                    color:
                      bilancio.conto_economico.utile_ante_imposte >= 0
                        ? COLORS.success
                        : COLORS.danger,
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
                <StatCard
                  label="Costi deducibili IRES"
                  value={
                    <span style={{ fontFamily: FONT.mono }}>
                      {formatEuro(bilancio.conto_economico.costi.totale_deducibile_ires)}
                    </span>
                  }
                  accent="none"
                />
                <StatCard
                  label="Costi deducibili IRAP"
                  value={
                    <span style={{ fontFamily: FONT.mono }}>
                      {formatEuro(bilancio.conto_economico.costi.totale_deducibile_irap)}
                    </span>
                  }
                  accent="none"
                />
              </div>
            </Card>
            <Card>
              <h3 style={styles.sectionTitle}>🏦 Stato Patrimoniale</h3>
              <div style={styles.grid2(isMobile)}>
                <div>
                  <h4 style={styles.sectionHeader(COLORS.info)}>ATTIVO</h4>
                  <div style={styles.spaceY}>
                    {bilancio.stato_patrimoniale.attivo.voci
                      .filter(v => v.saldo !== 0)
                      .map((voce, i) => (
                        <div
                          key={i}
                          style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}
                        >
                          <span style={{ color: COLORS.text }}>
                            {voce.codice} - {voce.nome}
                          </span>
                          <span style={{ color: COLORS.info, fontWeight: 500, fontFamily: FONT.mono }}>
                            {formatEuro(voce.saldo)}
                          </span>
                        </div>
                      ))}
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        paddingTop: 8,
                        borderTop: `1px solid ${COLORS.border}`,
                      }}
                    >
                      <span style={{ color: COLORS.text, fontWeight: 'bold' }}>TOTALE ATTIVO</span>
                      <span style={{ color: COLORS.info, fontWeight: 'bold', fontFamily: FONT.mono }}>
                        {formatEuro(bilancio.stato_patrimoniale.attivo.totale)}
                      </span>
                    </div>
                  </div>
                </div>
                <div>
                  <h4 style={styles.sectionHeader(COLORS.primary)}>PASSIVO + PN</h4>
                  <div style={styles.spaceY}>
                    {bilancio.stato_patrimoniale.passivo.voci
                      .filter(v => v.saldo !== 0)
                      .map((voce, i) => (
                        <div
                          key={i}
                          style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}
                        >
                          <span style={{ color: COLORS.text }}>
                            {voce.codice} - {voce.nome}
                          </span>
                          <span style={{ color: COLORS.primary, fontWeight: 500, fontFamily: FONT.mono }}>
                            {formatEuro(voce.saldo)}
                          </span>
                        </div>
                      ))}
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        paddingTop: 8,
                        borderTop: `1px solid ${COLORS.border}`,
                      }}
                    >
                      <span style={{ color: COLORS.text, fontWeight: 'bold' }}>TOTALE PASSIVO</span>
                      <span style={{ color: COLORS.primary, fontWeight: 'bold', fontFamily: FONT.mono }}>
                        {formatEuro(bilancio.stato_patrimoniale.passivo.totale)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </Card>
          </div>
        )}
        {activeTab === 'bilancio' && !bilancio && (
          <div style={styles.note}>
            Nessun bilancio dettagliato disponibile per l'anno {selectedYear}.
          </div>
        )}
      </div>
    </PageLayout>
  );
}

import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import api from '../api';
import { formatEuro, formatDateIT, COLORS, SHADOWS, BORDER_RADIUS, FONT, useIsMobile } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { PageHeader } from '../components/ds/PageHeader';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { Button, Badge, StatCard, Input, Select, Table, TableWrap, Th, Td } from '../components/ds';
import { euroOppure } from '../lib/vista';
import { ChartColumn, TrendingDown, TrendingUp, Gem, Banknote, FileText, ChevronDown, ChevronRight, X } from 'lucide-react';

const MONO = FONT.mono;

/**
 * Un saldo negativo su un conto del passivo non e' un debito: e' un saldo in DARE.
 * Per l'Erario (35.*) vuol dire credito (IVA a credito sugli acquisti), che il bilancio
 * mostrava tra parentesi in rosso come se fosse un debito.
 */
export function lato_saldo(conto = {}) {
  const saldo = Number(conto.saldo || 0);
  if (saldo >= 0) return null;
  const categoria = String(conto.categoria || '').toLowerCase();
  if (categoria === 'passivo' && String(conto.codice || '').startsWith('35.')) {
    return { testo: 'credito verso Erario', favorevole: true };
  }
  return { testo: categoria === 'passivo' || categoria === 'patrimonio netto' ? 'saldo in dare' : 'saldo in avere', favorevole: false };
}

export function buildBalanceSummary(grouped = {}) {
  const totale = categoria =>
    (grouped[categoria] || []).reduce((somma, conto) => somma + Number(conto.saldo || 0), 0);
  const ricavi = totale('ricavi');
  const costi = totale('costi');

  return {
    stato_patrimoniale: {
      attivo: { totale: totale('attivo') },
      passivo: { totale: totale('passivo') },
      patrimonio_netto: { totale: totale('patrimonio_netto') },
    },
    conto_economico: {
      ricavi: { totale: ricavi },
      costi: { totale: costi },
      risultato: ricavi - costi,
    },
  };
}

const CATEGORIE = {
  attivo: { nome: 'ATTIVO', color: COLORS.info, icon: ChartColumn },
  passivo: { nome: 'PASSIVO', color: COLORS.danger, icon: TrendingDown },
  patrimonio_netto: { nome: 'PATRIMONIO NETTO', color: COLORS.primary, icon: Gem },
  ricavi: { nome: 'RICAVI', color: COLORS.success, icon: TrendingUp },
  costi: { nome: 'COSTI', color: COLORS.warning, icon: Banknote },
};

export default function PianoDeiConti() {
  const isMobile = useIsMobile();
  const confirm = useConfirm();
  const { anno: annoGlobale } = useAnnoGlobale();
  const [_conti, setConti] = useState([]);
  const [movVisibili, setMovVisibili] = useState(200);
  const [pianoInfo, setPianoInfo] = useState({ totale: 0, nonMappati: [] });
  const [grouped, setGrouped] = useState({});
  const [bilancio, setBilancio] = useState(null);
  const [loading, setLoading] = useState(true);
  const [riclassificando, setRiclassificando] = useState(false);
  const [riclassificaResult, setRiclassificaResult] = useState(null);

  // Drawer dettaglio conto
  const [selectedConto, setSelectedConto] = useState(null);
  const [contoDetail, setContoDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const openContoDetail = useCallback(
    async conto => {
      setSelectedConto(conto);
      setContoDetail(null);
      setLoadingDetail(true);
      try {
        const res = await api.get(
          `/api/piano-conti/conto/${conto.codice}/movimenti?limit=40&anno=${annoGlobale}&schema=cee`
        );
        setContoDetail(res.data);
      } catch (e) {
        // Errore del servizio ≠ "conto senza movimenti": segnalalo.
        toast.error('Movimenti del conto non caricati: ' + (e.response?.data?.detail || e.message));
      } finally {
        setLoadingDetail(false);
      }
    },
    [annoGlobale]
  );

  const closeDrawer = () => {
    setSelectedConto(null);
    setContoDetail(null);
  };

  // Riclassificazione riga: sposta un articolo (dizionario_articoli) su un
  // altro conto costi quando l'associazione automatica è sbagliata —
  // richiesto dall'utente 18/07/2026. La modifica è sull'ARTICOLO (vale per
  // tutte le fatture future con la stessa descrizione riga), non sulla
  // singola fattura: coerente con come il saldo viene calcolato.
  const [spostandoRiga, setSpostandoRiga] = useState(null);
  const contiCosti = _conti
    .filter(c => (c.categoria || '').toLowerCase() === 'costi')
    .sort((a, b) => (a.codice || '').localeCompare(b.codice || ''));

  const handleSpostaRigaConto = async (lineaDescrizione, nuovoConto) => {
    if (!nuovoConto || !lineaDescrizione) return;
    setSpostandoRiga(lineaDescrizione);
    try {
      await api.put(`/api/dizionario-articoli/articolo/${encodeURIComponent(lineaDescrizione)}`, {
        conto: nuovoConto,
      });
      const nuovoContoInfo = contiCosti.find(c => c.codice === nuovoConto);
      toast.success('Categoria aggiornata', {
        description: `"${lineaDescrizione}" ora è in ${nuovoConto}${nuovoContoInfo ? ' — ' + nuovoContoInfo.nome : ''}`,
      });
      await loadData();
      if (selectedConto) await openContoDetail(selectedConto);
    } catch (error) {
      toast.error('Errore', { description: error.response?.data?.detail || error.message });
    } finally {
      setSpostandoRiga(null);
    }
  };
  // URL Tab Support
  const navigate = useNavigate();
  const location = useLocation();

  const getTabFromPath = () => {
    const path = location.pathname;
    const match = path.match(/\/contabilita\/piano-conti\/([\w-]+)/);
    return match ? match[1] : 'conti';
  };

  const activeTab = getTabFromPath();

  // Le «Regole categorizzazione» di questa pagina erano un secondo sistema che il motore di
  // registrazione non leggeva piu': l'unico e' Learning Machine > Regole categorizzazione.
  useEffect(() => {
    if (activeTab === 'regole') navigate('/learning-machine/regole', { replace: true });
  }, [activeTab, navigate]);
  const [expandedCategories, setExpandedCategories] = useState(['attivo', 'passivo', 'costi']);

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [annoGlobale]);

  const loadData = async () => {
    setLoading(true);
    try {
      const contiRes = await api.get(`/api/piano-conti/?anno=${annoGlobale}`);

      const groupedConti = contiRes.data?.grouped || {};
      setConti(contiRes.data?.conti || []);
      setPianoInfo({
        totale: contiRes.data?.totale || (contiRes.data?.conti || []).length,
        nonMappati: contiRes.data?.conti_operativi_non_mappati || [],
      });
      setGrouped(groupedConti);
      // Difesa sulla forma: se il backend risponde con payload vuoto/inatteso
      // (riavvio in corso) le card bilancio leggono i sotto-oggetti e
      // manderebbero in crash la pagina — meglio nasconderle.
      setBilancio(buildBalanceSummary(groupedConti));
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
    }
  };

  const toggleCategory = cat => {
    setExpandedCategories(prev =>
      prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]
    );
  };

  const handleRiclassificaAI = async () => {
    const conferma = await confirm({
      title: 'Ricategorizzazione con AI',
      message:
        'Analizzerà tutte le righe delle fatture XML e le assegnerà ai conti corretti del piano dei conti ' +
        '(es. Coca-Cola → Bevande analcoliche, Caffè Lavazza → Caffè e affini).\n\n' +
        "L'operazione dura da 30 secondi a qualche minuto in base al numero di fatture. " +
        'Costa qualche centesimo in chiamate AI.\n\n' +
        'Procedere?',
      confirmText: 'Procedi',
    });
    if (!conferma) return;

    setRiclassificando(true);
    setRiclassificaResult(null);
    try {
      const r = await api.post('/api/dizionario-articoli/riclassifica-completo?limite_ai=500');
      setRiclassificaResult(r.data);
      // ricarica i saldi
      await loadData();
    } catch (error) {
      setRiclassificaResult({
        success: false,
        error: error.response?.data?.detail || error.message,
      });
    } finally {
      setRiclassificando(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>
        Caricamento Piano dei Conti...
      </div>
    );
  }

  return (
    <PageLayout>
      <div style={{ maxWidth: 1400, margin: '0 auto' }}>
        <PageHeader title="Piano dei conti" style={{ marginBottom: 14 }} />

        {/* Bilancio Summary Cards */}
        {bilancio && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
              gap: 12,
              marginBottom: 25,
            }}
          >
            {[
              {
                label: 'Totale Attivo',
                val: bilancio.stato_patrimoniale.attivo.totale,
                accent: 'primary',
              },
              {
                label: 'Totale Passivo',
                val: bilancio.stato_patrimoniale.passivo.totale,
                accent: 'primary',
              },
              { label: 'Totale Ricavi', val: bilancio.conto_economico.ricavi.totale, accent: 'success' },
              { label: 'Totale Costi', val: bilancio.conto_economico.costi.totale, accent: 'primary' },
              {
                label: bilancio.conto_economico.risultato >= 0 ? 'Utile' : 'Perdita',
                val: Math.abs(bilancio.conto_economico.risultato),
                accent: bilancio.conto_economico.risultato >= 0 ? 'success' : 'danger',
              },
            ].map(({ label, val, accent }) => (
              <StatCard
                key={label}
                label={label}
                value={<span style={{ fontFamily: MONO }}>{euroOppure(val)}</span>}
                accent={accent}
              />
            ))}
          </div>
        )}

        {/* Piano dei Conti */}
        {activeTab === 'conti' && (
          <>
            <div style={{ marginBottom: 15, display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              <div
                data-testid="piano-cee-nota"
                style={{
                  padding: '8px 12px',
                  fontSize: 13,
                  borderRadius: BORDER_RADIUS.sm,
                  background: COLORS.bgAlt,
                  border: `1px solid ${COLORS.border}`,
                  color: COLORS.textMuted,
                }}
              >
                Piano dei conti <strong>CEE ufficiale</strong> del bilancio del commercialista
                ({pianoInfo.totale} conti): i conti non si creano a mano; il vecchio codice
                operativo compare come <em>alias</em>.
                {pianoInfo.nonMappati.length > 0 && (
                  <span style={{ color: COLORS.danger }}>
                    {' '}Conti operativi senza alias CEE: {pianoInfo.nonMappati.map(c => c.codice).join(', ')}.
                  </span>
                )}
              </div>

              <Button
                variant="warning"
                onClick={handleRiclassificaAI}
                disabled={riclassificando}
                title="Analizza le righe delle fatture XML con AI e le assegna ai conti del piano corretti (es. Coca-Cola → Bevande analcoliche)"
              >
                {riclassificando ? 'Classificazione in corso…' : 'Ricategorizza con AI'}
              </Button>

              {riclassificaResult && (
                <div style={{
                  padding: '8px 12px',
                  fontSize: 13,
                  borderRadius: BORDER_RADIUS.sm,
                  background: riclassificaResult.success ? COLORS.successLight : COLORS.dangerLight,
                  color: riclassificaResult.success ? COLORS.success : COLORS.danger,
                  border: `1px solid ${riclassificaResult.success ? COLORS.success : COLORS.danger}`,
                }}>
                  {riclassificaResult.success
                    ? `Articoli elaborati: ${riclassificaResult.step1_genera_dizionario?.total || 0} · Riclassificati AI: ${riclassificaResult.step2_categorizzazione_ai?.categorizzati || 0}`
                    : `Errore: ${riclassificaResult.error || 'operazione fallita'}`}
                </div>
              )}
            </div>

            <div style={{ display: 'grid', gap: 15 }}>
              {Object.entries(CATEGORIE).map(([key, cat]) => (
                <div
                  key={key}
                  style={{
                    background: COLORS.card,
                    borderRadius: BORDER_RADIUS.md,
                    overflow: 'hidden',
                    border: `1px solid ${COLORS.border}`,
                  }}
                >
                  {/* Category Header */}
                  <div
                    onClick={() => toggleCategory(key)}
                    style={{
                      padding: 15,
                      background: cat.color + '15',
                      borderLeft: `4px solid ${cat.color}`,
                      cursor: 'pointer',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <cat.icon size={24} aria-hidden color={cat.color} />
                      <div>
                        <div style={{ fontWeight: 'bold', color: cat.color }}>{cat.nome}</div>
                        <div style={{ fontSize: 12, color: COLORS.textMuted }}>
                          {grouped[key]?.length || 0} conti
                        </div>
                      </div>
                    </div>
                    <span style={{ fontSize: 20 }}>
                      {expandedCategories.includes(key) ? <ChevronDown size={20} aria-hidden /> : <ChevronRight size={20} aria-hidden />}
                    </span>
                  </div>

                  {/* Category Conti */}
                  {expandedCategories.includes(key) && (
                    <div style={{ padding: 15 }}>
                      {(grouped[key] || []).length === 0 ? (
                        <div style={{ color: COLORS.textSubtle, textAlign: 'center', padding: 20 }}>
                          Nessun conto in questa categoria
                        </div>
                      ) : (
                        <TableWrap>
                          <Table>
                            <thead>
                              <tr>
                                <Th>Codice CEE</Th>
                                <Th>Nome Conto</Th>
                                <Th>Alias operativo</Th>
                                <Th align="center">Natura</Th>
                                <Th align="right">Saldo</Th>
                              </tr>
                            </thead>
                            <tbody>
                              {grouped[key].map((conto, idx) => (
                                <tr
                                  key={conto.id}
                                  data-testid={`conto-row-${conto.codice}`}
                                  onClick={() => openContoDetail(conto)}
                                  style={{
                                    background:
                                      selectedConto?.codice === conto.codice
                                        ? cat.color + '18'
                                        : idx % 2 === 0
                                          ? COLORS.card
                                          : COLORS.bgAlt,
                                    cursor: 'pointer',
                                    transition: 'background 0.15s',
                                  }}
                                  onMouseEnter={e => {
                                    e.currentTarget.style.background = cat.color + '22';
                                  }}
                                  onMouseLeave={e => {
                                    e.currentTarget.style.background =
                                      selectedConto?.codice === conto.codice
                                        ? cat.color + '18'
                                        : idx % 2 === 0
                                          ? COLORS.card
                                          : COLORS.bgAlt;
                                  }}
                                >
                                  <Td mono style={{ fontWeight: 'bold' }}>
                                    <span style={{ color: cat.color }}>{conto.codice}</span>
                                    <span style={{ color: COLORS.textSubtle, marginLeft: 6, fontSize: 11 }}>
                                      ›
                                    </span>
                                  </Td>
                                  <Td>{conto.nome}</Td>
                                  <Td mono style={{ fontSize: 12, color: COLORS.textMuted }}>
                                    {(conto.alias_operativi || []).join(', ') || '—'}
                                  </Td>
                                  <Td align="center">
                                    <Badge variant={conto.natura === 'finanziario' ? 'info' : 'neutral'}>
                                      {conto.natura}
                                    </Badge>
                                  </Td>
                                  <Td
                                    align="right"
                                    mono
                                    style={{
                                      fontWeight: 'bold',
                                      color: conto.saldo >= 0 || lato_saldo(conto)?.favorevole ? COLORS.success : COLORS.danger,
                                    }}
                                  >
                                    {lato_saldo(conto) ? formatEuro(Math.abs(conto.saldo)) : euroOppure(conto.saldo)}
                                    {lato_saldo(conto) && (
                                      <span style={{ display: 'block', fontSize: 11, fontWeight: 'normal' }}>
                                        {lato_saldo(conto).testo}
                                      </span>
                                    )}
                                  </Td>
                                </tr>
                              ))}
                            </tbody>
                          </Table>
                        </TableWrap>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}

      </div>

      {/* ─── DRAWER DETTAGLIO CONTO ─── */}
      {selectedConto && (
        <>
          {/* Overlay semi-trasparente */}
          <div
            onClick={closeDrawer}
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0,0,0,0.35)',
              zIndex: 1000,
            }}
          />

          {/* Pannello laterale destro */}
          <div
            data-testid="conto-detail-drawer"
            style={{
              position: 'fixed',
              top: 0,
              right: 0,
              width: 'min(580px, 100%)',
              height: '100vh',
              background: COLORS.card,
              boxShadow: SHADOWS.xl,
              zIndex: 1001,
              display: 'flex',
              flexDirection: 'column',
              overflowY: 'auto',
            }}
          >
            {/* Header */}
            {(() => {
              const catKey = selectedConto.categoria?.toLowerCase().replace(' ', '_') || 'costi';
              const catInfo = CATEGORIE[catKey] || {
                nome: selectedConto.categoria,
                color: COLORS.primary,
                icon: FileText,
              };
              return (
                <>
                  <div
                    style={{
                      background: catInfo.color,
                      padding: '20px 24px',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                    }}
                  >
                    <div>
                      <div
                        style={{ color: 'rgba(255,255,255,0.75)', fontSize: 12, marginBottom: 4 }}
                      >
                        <catInfo.icon size={18} aria-hidden style={{ verticalAlign: '-3px' }} /> {catInfo.nome}
                      </div>
                      <div
                        style={{
                          color: 'white',
                          fontFamily: MONO,
                          fontSize: 22,
                          fontWeight: 'bold',
                        }}
                      >
                        {selectedConto.codice}
                      </div>
                      <div style={{ color: 'rgba(255,255,255,0.9)', fontSize: 16, marginTop: 4 }}>
                        {selectedConto.nome}
                      </div>
                      {(selectedConto.alias_operativi || []).length > 0 && (
                        <div style={{ color: 'rgba(255,255,255,0.75)', fontSize: 12, marginTop: 4, fontFamily: MONO }}>
                          alias operativo: {selectedConto.alias_operativi.join(', ')}
                        </div>
                      )}
                    </div>
                    <button
                      onClick={closeDrawer}
                      data-testid="close-conto-drawer"
                      style={{
                        background: 'rgba(255,255,255,0.2)',
                        border: 'none',
                        borderRadius: BORDER_RADIUS.sm,
                        cursor: 'pointer',
                        color: 'white',
                        fontSize: 20,
                        padding: '4px 12px',
                      }}
                    >
                      <X size={18} aria-hidden />
                    </button>
                  </div>

                  {/* Saldo + info */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr 1fr',
                      gap: 1,
                      background: COLORS.border,
                    }}
                  >
                    {[
                      {
                        label: 'Saldo',
                        val: lato_saldo(selectedConto)
                          ? `${formatEuro(Math.abs(selectedConto.saldo))} · ${lato_saldo(selectedConto).testo}`
                          : euroOppure(selectedConto.saldo),
                        color: (selectedConto.saldo || 0) >= 0 || lato_saldo(selectedConto)?.favorevole ? COLORS.success : COLORS.danger,
                      },
                      { label: 'Natura', val: selectedConto.natura || '—', color: COLORS.textMuted },
                      {
                        label: 'Stato',
                        val: selectedConto.attivo ? 'Attivo' : 'Inattivo',
                        color: selectedConto.attivo ? COLORS.success : COLORS.textSubtle,
                      },
                    ].map(({ label, val, color }) => (
                      <div key={label} style={{ background: COLORS.card, padding: '14px 18px' }}>
                        <div style={{ fontSize: 11, color: COLORS.textSubtle, marginBottom: 4 }}>{label}</div>
                        <div style={{ fontWeight: 'bold', color, fontSize: 16 }}>{val}</div>
                      </div>
                    ))}
                  </div>
                </>
              );
            })()}

            {/* Corpo drawer: movimenti */}
            <div style={{ flex: 1, padding: '18px 24px', overflowY: 'auto' }}>
              {loadingDetail ? (
                <div style={{ textAlign: 'center', padding: 40, color: COLORS.textSubtle }}>
                  Caricamento movimenti…
                </div>
              ) : contoDetail ? (
                <>
                  {/* Riepilogo */}
                  <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
                    {[
                      { label: 'Movimenti', val: contoDetail.totale_movimenti },
                      { label: 'Totale periodo', val: euroOppure(contoDetail.totale_importo) },
                    ].map(({ label, val }) => (
                      <div
                        key={label}
                        style={{
                          flex: 1,
                          background: COLORS.bgAlt,
                          borderRadius: BORDER_RADIUS.md,
                          padding: 12,
                          textAlign: 'center',
                        }}
                      >
                        <div style={{ fontSize: 11, color: COLORS.textSubtle }}>{label}</div>
                        <div style={{ fontWeight: 'bold', fontSize: 18, marginTop: 4 }}>{val}</div>
                      </div>
                    ))}
                  </div>

                  {/* Fonte dati */}
                  {contoDetail.fonte && contoDetail.fonte !== 'nessuna' && (
                    <div
                      style={{
                        fontSize: 11,
                        color: COLORS.textMuted,
                        background: COLORS.infoLight,
                        borderRadius: BORDER_RADIUS.sm,
                        padding: '6px 10px',
                        marginBottom: 12,
                      }}
                    >
                      Fonte: <strong>{contoDetail.fonte}</strong>
                    </div>
                  )}

                  {/* Tabella movimenti */}
                  {contoDetail.movimenti?.length > 0 ? (
                    <>
                      <div
                        style={{ fontWeight: 600, fontSize: 13, color: COLORS.text, marginBottom: 8 }}
                      >
                        Movimenti ({annoGlobale})
                      </div>
                      <TableWrap>
                        <Table>
                          <thead>
                            <tr>
                              <Th>Data</Th>
                              <Th>Descrizione</Th>
                              <Th align="right">Importo</Th>
                              {contoDetail.movimenti.some(m => m.linea_descrizione) && (
                                <Th>Sposta</Th>
                              )}
                            </tr>
                          </thead>
                          <tbody>
                            {contoDetail.movimenti.slice(0, movVisibili).map((mov, i) => (
                              <tr key={i}>
                                <Td mono style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                                  {mov.data ? formatDateIT(mov.data) : '—'}
                                </Td>
                                <Td style={{ maxWidth: 260 }}>
                                  <div
                                    style={{
                                      overflow: 'hidden',
                                      textOverflow: 'ellipsis',
                                      whiteSpace: 'nowrap',
                                    }}
                                    title={mov.descrizione}
                                  >
                                    {(mov.descrizione || '—').slice(0, 65)}
                                  </div>
                                  {mov.categoria && (
                                    <div style={{ fontSize: 10, color: COLORS.textSubtle, marginTop: 2 }}>
                                      {mov.categoria}
                                    </div>
                                  )}
                                </Td>
                                <Td
                                  align="right"
                                  mono
                                  style={{
                                    fontWeight: 'bold',
                                    color: mov.tipo === 'entrata' ? COLORS.success : COLORS.danger,
                                  }}
                                >
                                  {mov.tipo === 'entrata' ? '+' : '-'}
                                  {euroOppure(mov.importo)}
                                </Td>
                                {contoDetail.movimenti.some(m => m.linea_descrizione) && (
                                  <Td>
                                    {mov.linea_descrizione && (
                                      <Select
                                        title="Sposta questo articolo su un altro conto costi (vale per tutte le fatture future con la stessa descrizione)"
                                        disabled={spostandoRiga === mov.linea_descrizione}
                                        onChange={e => {
                                          const nuovo = e.target.value;
                                          e.target.value = '';
                                          if (nuovo) handleSpostaRigaConto(mov.linea_descrizione, nuovo);
                                        }}
                                        style={{ padding: '3px 6px', fontSize: 11 }}
                                        defaultValue=""
                                      >
                                        <option value="">
                                          {spostandoRiga === mov.linea_descrizione ? '…' : 'Sposta'}
                                        </option>
                                        {contiCosti
                                          .filter(c => c.codice !== selectedConto?.codice)
                                          .map(c => (
                                            <option key={c.codice} value={c.codice}>
                                              {c.codice} — {c.nome}
                                            </option>
                                          ))}
                                      </Select>
                                    )}
                                  </Td>
                                )}
                              </tr>
                            ))}
                          </tbody>
                        </Table>
                      </TableWrap>
                      {contoDetail.movimenti.length > movVisibili && (
                        <div style={{ textAlign: 'center', padding: 12 }}>
                          <Button type="button" variant="secondary" onClick={() => setMovVisibili(v => v + 200)}>
                            Mostra altre ({contoDetail.movimenti.length - movVisibili})
                          </Button>
                        </div>
                      )}
                    </>
                  ) : (
                    <div
                      style={{
                        textAlign: 'center',
                        padding: 28,
                        color: COLORS.textSubtle,
                        fontSize: 13,
                        background: COLORS.bgAlt,
                        borderRadius: BORDER_RADIUS.md,
                      }}
                    >
                      {contoDetail.nota || 'Nessun movimento disponibile per questo conto.'}
                    </div>
                  )}
                </>
              ) : (
                <div style={{ textAlign: 'center', padding: 40, color: COLORS.textSubtle }}>
                  Nessun dettaglio disponibile
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </PageLayout>
  );
}

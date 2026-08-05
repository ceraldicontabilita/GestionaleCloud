import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import api from '../api';
import { formatEuro, COLORS, SHADOWS, BORDER_RADIUS, FONT, useIsMobile } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { Button, Badge, StatCard, Tabs, Input, Select, Table, TableWrap, Th, Td } from '../components/ds';

const MONO = FONT.mono;

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
  attivo: { nome: 'ATTIVO', color: COLORS.info, icon: '📊' },
  passivo: { nome: 'PASSIVO', color: COLORS.danger, icon: '📉' },
  patrimonio_netto: { nome: 'PATRIMONIO NETTO', color: COLORS.primary, icon: '💎' },
  ricavi: { nome: 'RICAVI', color: COLORS.success, icon: '📈' },
  costi: { nome: 'COSTI', color: COLORS.warning, icon: '💸' },
};

export default function PianoDeiConti() {
  const isMobile = useIsMobile();
  const confirm = useConfirm();
  const { anno: annoGlobale } = useAnnoGlobale();
  const [_conti, setConti] = useState([]);
  const [grouped, setGrouped] = useState({});
  const [regole, setRegole] = useState([]);
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
          `/api/piano-conti/conto/${conto.codice}/movimenti?limit=40&anno=${annoGlobale}`
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

  const [activeTab, setActiveTab] = useState(getTabFromPath());

  const handleTabChange = tabId => {
    setActiveTab(tabId);
    navigate(`/contabilita/piano-conti/${tabId}`);
  };

  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setActiveTab(tab);
  }, [location.pathname]);
  const [expandedCategories, setExpandedCategories] = useState(['attivo', 'passivo', 'costi']);

  // Modal nuovo conto
  const [showNewConto, setShowNewConto] = useState(false);
  const [newConto, setNewConto] = useState({
    codice: '',
    nome: '',
    categoria: 'costi',
    natura: 'economico',
  });

  // Modal nuova regola
  const [showNewRegola, setShowNewRegola] = useState(false);
  const [newRegola, setNewRegola] = useState({
    tipo: 'fornitore',
    pattern: '',
    conto_dare: '',
    conto_avere: '',
    descrizione: '',
  });

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [annoGlobale]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [contiRes, regoleRes] = await Promise.all([
        api.get(`/api/piano-conti/?anno=${annoGlobale}`),
        api.get('/api/piano-conti/regole'),
      ]);

      const groupedConti = contiRes.data?.grouped || {};
      setConti(contiRes.data?.conti || []);
      setGrouped(groupedConti);
      setRegole(regoleRes.data?.regole || []);
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

  const handleCreateConto = async () => {
    if (!newConto.codice || !newConto.nome) {
      toast.error('Codice e nome sono obbligatori');
      return;
    }
    try {
      await api.post('/api/piano-conti/', newConto);
      setShowNewConto(false);
      setNewConto({ codice: '', nome: '', categoria: 'costi', natura: 'economico' });
      loadData();
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
    }
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

  const handleCreateRegola = async () => {
    if (!newRegola.pattern || !newRegola.conto_dare) {
      toast.error('Pattern e conto DARE sono obbligatori');
      return;
    }
    try {
      await api.post('/api/piano-conti/regole', newRegola);
      setShowNewRegola(false);
      setNewRegola({
        tipo: 'fornitore',
        pattern: '',
        conto_dare: '',
        conto_avere: '',
        descrizione: '',
      });
      loadData();
    } catch (error) {
      toast.error('Errore: ' + (error.response?.data?.detail || error.message));
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
        {/* Header */}
        <div style={{ marginBottom: 20, borderLeft: `4px solid ${COLORS.primary}`, paddingLeft: 14 }}>
          <h1 style={{ margin: 0, fontSize: 'clamp(20px, 5vw, 28px)', color: COLORS.primary }}>
            📒 Piano dei Conti
          </h1>
          <p style={{ color: COLORS.textMuted, margin: '5px 0 0 0' }}>
            Contabilità Generale - Sistema di Partita Doppia
          </p>
        </div>

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
                value={<span style={{ fontFamily: MONO }}>{formatEuro(val)}</span>}
                accent={accent}
              />
            ))}
          </div>
        )}

        {/* Tabs */}
        <div style={{ marginBottom: 20 }}>
          <Tabs
            items={[
              { key: 'conti', label: '📊 Piano dei Conti' },
              { key: 'regole', label: '⚙️ Regole Categorizzazione' },
            ]}
            value={activeTab}
            onChange={handleTabChange}
          />
        </div>

        {/* Piano dei Conti */}
        {activeTab === 'conti' && (
          <>
            <div style={{ marginBottom: 15, display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              <Button
                variant="primary"
                onClick={() => setShowNewConto(true)}
                data-testid="new-conto-btn"
              >
                ➕ Nuovo Conto
              </Button>

              <Button
                variant="warning"
                onClick={handleRiclassificaAI}
                disabled={riclassificando}
                title="Analizza le righe delle fatture XML con AI e le assegna ai conti del piano corretti (es. Coca-Cola → Bevande analcoliche)"
              >
                {riclassificando ? '⏳ Classificazione in corso…' : '🤖 Ricategorizza con AI'}
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
                    ? `✅ Articoli elaborati: ${riclassificaResult.step1_genera_dizionario?.total || 0} · Riclassificati AI: ${riclassificaResult.step2_categorizzazione_ai?.categorizzati || 0}`
                    : `❌ Errore: ${riclassificaResult.error || 'operazione fallita'}`}
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
                      <span style={{ fontSize: 24 }}>{cat.icon}</span>
                      <div>
                        <div style={{ fontWeight: 'bold', color: cat.color }}>{cat.nome}</div>
                        <div style={{ fontSize: 12, color: COLORS.textMuted }}>
                          {grouped[key]?.length || 0} conti
                        </div>
                      </div>
                    </div>
                    <span style={{ fontSize: 20 }}>
                      {expandedCategories.includes(key) ? '▼' : '▶'}
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
                                <Th>Codice</Th>
                                <Th>Nome Conto</Th>
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
                                      color: conto.saldo >= 0 ? COLORS.success : COLORS.danger,
                                    }}
                                  >
                                    {formatEuro(conto.saldo)}
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

        {/* Regole Categorizzazione */}
        {activeTab === 'regole' && (
          <>
            <div style={{ marginBottom: 15 }}>
              <Button
                variant="primary"
                onClick={() => setShowNewRegola(true)}
                data-testid="new-regola-btn"
              >
                ➕ Nuova Regola
              </Button>
            </div>

            <div
              style={{
                background: COLORS.warningLight,
                border: `1px solid ${COLORS.warning}`,
                padding: 15,
                borderRadius: BORDER_RADIUS.md,
                marginBottom: 20,
                fontSize: 13,
                color: COLORS.text,
              }}
            >
              <strong>Come funzionano le regole:</strong>
              <ul style={{ margin: '10px 0 0 0', paddingLeft: 20 }}>
                <li>
                  Le regole determinano automaticamente quali conti usare per registrare le fatture
                </li>
                <li>
                  <strong>Pattern</strong>: parola chiave da cercare (es. "ENEL" per bollette
                  elettricità)
                </li>
                <li>
                  <strong>Conto DARE</strong>: conto che aumenta (es. costo utenze)
                </li>
                <li>
                  <strong>Conto AVERE</strong>: conto che diminuisce (es. debito fornitore)
                </li>
              </ul>
            </div>

            <TableWrap>
              <Table>
                <thead>
                  <tr>
                    <Th>Tipo</Th>
                    <Th>Pattern</Th>
                    <Th>Conto DARE</Th>
                    <Th>Conto AVERE</Th>
                    <Th>Descrizione</Th>
                    <Th align="center">Stato</Th>
                  </tr>
                </thead>
                <tbody>
                  {regole.map(regola => (
                    <tr key={regola.id}>
                      <Td>
                        <Badge variant={regola.tipo === 'fornitore' ? 'success' : 'info'}>
                          {regola.tipo}
                        </Badge>
                      </Td>
                      <Td mono style={{ fontWeight: 'bold' }}>
                        {regola.pattern}
                      </Td>
                      <Td mono>{regola.conto_dare}</Td>
                      <Td mono>{regola.conto_avere}</Td>
                      <Td>{regola.descrizione}</Td>
                      <Td align="center">
                        <span
                          style={{
                            width: 10,
                            height: 10,
                            borderRadius: BORDER_RADIUS.full,
                            background: regola.attiva ? COLORS.success : COLORS.textSubtle,
                            display: 'inline-block',
                          }}
                        />
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableWrap>
          </>
        )}

        {/* Modal Nuovo Conto */}
        {showNewConto && (
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
            onClick={() => setShowNewConto(false)}
          >
            <div
              style={{
                background: COLORS.card,
                borderRadius: BORDER_RADIUS.md,
                padding: 24,
                maxWidth: 450,
                width: '90%',
                boxShadow: SHADOWS.modal,
              }}
              onClick={e => e.stopPropagation()}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <h2 style={{ marginTop: 0 }}>➕ Nuovo Conto</h2>
                <button
                  onClick={() => setShowNewConto(false)}
                  aria-label="Chiudi"
                  style={{
                    width: 32,
                    height: 32,
                    flexShrink: 0,
                    background: COLORS.gray[100],
                    border: 'none',
                    borderRadius: BORDER_RADIUS.md,
                    color: COLORS.gray[600],
                    fontSize: 16,
                    lineHeight: 1,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  ✕
                </button>
              </div>

              <div style={{ display: 'grid', gap: 15 }}>
                <div>
                  <label
                    style={{ display: 'block', marginBottom: 5, fontWeight: 'bold', fontSize: 13 }}
                  >
                    Codice (es. 05.02.03) *
                  </label>
                  <Input
                    type="text"
                    value={newConto.codice}
                    onChange={e => setNewConto({ ...newConto, codice: e.target.value })}
                    placeholder="05.02.03"
                    style={{ fontFamily: MONO }}
                  />
                </div>
                <div>
                  <label
                    style={{ display: 'block', marginBottom: 5, fontWeight: 'bold', fontSize: 13 }}
                  >
                    Nome Conto *
                  </label>
                  <Input
                    type="text"
                    value={newConto.nome}
                    onChange={e => setNewConto({ ...newConto, nome: e.target.value })}
                    placeholder="Spese telefoniche"
                  />
                </div>
                <div>
                  <label
                    style={{ display: 'block', marginBottom: 5, fontWeight: 'bold', fontSize: 13 }}
                  >
                    Categoria *
                  </label>
                  <Select
                    value={newConto.categoria}
                    onChange={e => setNewConto({ ...newConto, categoria: e.target.value })}
                  >
                    {Object.entries(CATEGORIE).map(([key, cat]) => (
                      <option key={key} value={key}>
                        {cat.icon} {cat.nome}
                      </option>
                    ))}
                  </Select>
                </div>
                <div>
                  <label
                    style={{ display: 'block', marginBottom: 5, fontWeight: 'bold', fontSize: 13 }}
                  >
                    Natura
                  </label>
                  <Select
                    value={newConto.natura}
                    onChange={e => setNewConto({ ...newConto, natura: e.target.value })}
                  >
                    <option value="economico">Economico</option>
                    <option value="finanziario">Finanziario</option>
                  </Select>
                </div>
              </div>

              <div style={{ display: 'flex', gap: 10, marginTop: 20, justifyContent: 'flex-end' }}>
                <Button variant="secondary" onClick={() => setShowNewConto(false)}>
                  Annulla
                </Button>
                <Button variant="primary" onClick={handleCreateConto}>
                  ➕ Crea Conto
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Modal Nuova Regola */}
        {showNewRegola && (
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
            onClick={() => setShowNewRegola(false)}
          >
            <div
              style={{
                background: COLORS.card,
                borderRadius: BORDER_RADIUS.md,
                padding: 24,
                maxWidth: 500,
                width: '90%',
                boxShadow: SHADOWS.modal,
              }}
              onClick={e => e.stopPropagation()}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <h2 style={{ marginTop: 0 }}>⚙️ Nuova Regola Categorizzazione</h2>
                <button
                  onClick={() => setShowNewRegola(false)}
                  aria-label="Chiudi"
                  style={{
                    width: 32,
                    height: 32,
                    flexShrink: 0,
                    background: COLORS.gray[100],
                    border: 'none',
                    borderRadius: BORDER_RADIUS.md,
                    color: COLORS.gray[600],
                    fontSize: 16,
                    lineHeight: 1,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  ✕
                </button>
              </div>

              <div style={{ display: 'grid', gap: 15 }}>
                <div>
                  <label
                    style={{ display: 'block', marginBottom: 5, fontWeight: 'bold', fontSize: 13 }}
                  >
                    Tipo Regola
                  </label>
                  <Select
                    value={newRegola.tipo}
                    onChange={e => setNewRegola({ ...newRegola, tipo: e.target.value })}
                  >
                    <option value="fornitore">Per Fornitore (nome)</option>
                    <option value="tipo_documento">Per Tipo Documento</option>
                    <option value="pagamento">Per Metodo Pagamento</option>
                  </Select>
                </div>
                <div>
                  <label
                    style={{ display: 'block', marginBottom: 5, fontWeight: 'bold', fontSize: 13 }}
                  >
                    Pattern (Regex) *
                  </label>
                  <Input
                    type="text"
                    value={newRegola.pattern}
                    onChange={e => setNewRegola({ ...newRegola, pattern: e.target.value })}
                    placeholder="ENEL|EDISON"
                    style={{ fontFamily: MONO }}
                  />
                  <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 3 }}>
                    Usa | per alternative (es. ENEL|EDISON per luce o gas)
                  </div>
                </div>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                    gap: 10,
                  }}
                >
                  <div>
                    <label
                      style={{
                        display: 'block',
                        marginBottom: 5,
                        fontWeight: 'bold',
                        fontSize: 13,
                      }}
                    >
                      Conto DARE *
                    </label>
                    <Input
                      type="text"
                      value={newRegola.conto_dare}
                      onChange={e => setNewRegola({ ...newRegola, conto_dare: e.target.value })}
                      placeholder="05.02.02"
                      style={{ fontFamily: MONO }}
                    />
                  </div>
                  <div>
                    <label
                      style={{
                        display: 'block',
                        marginBottom: 5,
                        fontWeight: 'bold',
                        fontSize: 13,
                      }}
                    >
                      Conto AVERE
                    </label>
                    <Input
                      type="text"
                      value={newRegola.conto_avere}
                      onChange={e => setNewRegola({ ...newRegola, conto_avere: e.target.value })}
                      placeholder="02.01.01"
                      style={{ fontFamily: MONO }}
                    />
                  </div>
                </div>
                <div>
                  <label
                    style={{ display: 'block', marginBottom: 5, fontWeight: 'bold', fontSize: 13 }}
                  >
                    Descrizione
                  </label>
                  <Input
                    type="text"
                    value={newRegola.descrizione}
                    onChange={e => setNewRegola({ ...newRegola, descrizione: e.target.value })}
                    placeholder="Utenze elettricità"
                  />
                </div>
              </div>

              <div style={{ display: 'flex', gap: 10, marginTop: 20, justifyContent: 'flex-end' }}>
                <Button variant="secondary" onClick={() => setShowNewRegola(false)}>
                  Annulla
                </Button>
                <Button variant="primary" onClick={handleCreateRegola}>
                  ⚙️ Crea Regola
                </Button>
              </div>
            </div>
          </div>
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
                icon: '📄',
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
                        {catInfo.icon} {catInfo.nome}
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
                      ✕
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
                        val: formatEuro(selectedConto.saldo || 0),
                        color: (selectedConto.saldo || 0) >= 0 ? COLORS.success : COLORS.danger,
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
                      { label: 'Totale periodo', val: formatEuro(contoDetail.totale_importo) },
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
                            {contoDetail.movimenti.map((mov, i) => (
                              <tr key={i}>
                                <Td mono style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                                  {String(mov.data || '—').slice(0, 10)}
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
                                  {formatEuro(mov.importo)}
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
                                          {spostandoRiga === mov.linea_descrizione ? '…' : '↔️'}
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

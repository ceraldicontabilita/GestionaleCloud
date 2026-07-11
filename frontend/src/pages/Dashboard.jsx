import React, { useEffect, useMemo, useState } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import {
  Wallet,
  ShoppingCart,
  Banknote,
  Landmark,
  Receipt,
  CalendarClock,
  TrendingUp,
  TrendingDown,
  HelpCircle,
} from 'lucide-react';
import api from '../api';
import { useAnnoGlobale, AnnoSelector } from '../contexts/AnnoContext';
import { formatEuro, COLORS } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';

/**
 * DASHBOARD — ricostruita da zero (11/07/2026, richiesta utente).
 *
 * Filosofia: la scegli TU. In cima selezioni Anno e Mese (o "Tutto l'anno")
 * e OGNI numero della pagina si riferisce al periodo che hai scelto. Non c'è
 * più una parata di sezioni fisse che decide cosa devi leggere: ci sono card
 * separate, una per domanda, e delle scorciatoie-domanda che portano la
 * risposta in evidenza in cima.
 *
 * Tutti i dati sono filtrabili per mese lato backend:
 *  - Fatturato/Costi/Margine → /api/controllo-gestione/costi-ricavi?anno&mese
 *  - Cassa/Banca            → /api/prima-nota/stats?data_da&data_a
 *  - IVA                    → /api/verifica-coerenza/iva/{anno}/{mese}
 *                             (tutto l'anno: /confronto-iva-completo/{anno})
 *  - Scadenze/F24           → /api/scadenze?anno&mese
 *  - Grafico 12 mesi        → /api/dashboard/trend-mensile?anno
 */

const MESI = [
  'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
  'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre',
];

const ultimoGiorno = (anno, mese) => new Date(anno, mese, 0).getDate();

export default function Dashboard() {
  const { anno } = useAnnoGlobale();
  // 0 = tutto l'anno; 1..12 = mese singolo. È lo stato che comanda tutto.
  const [mese, setMese] = useState(0);

  const [costiRicavi, setCostiRicavi] = useState(null);
  const [primaNota, setPrimaNota] = useState(null);
  const [iva, setIva] = useState(null);
  const [scadenze, setScadenze] = useState(null);
  const [trend, setTrend] = useState(null);

  const [loading, setLoading] = useState(true);
  const [erroriApi, setErroriApi] = useState([]);
  // Scorciatoia-domanda selezionata (mostra la risposta grande in cima).
  const [domanda, setDomanda] = useState(null);

  const etichettaPeriodo = mese ? `${MESI[mese - 1]} ${anno}` : `tutto il ${anno}`;

  useEffect(() => {
    const controller = new AbortController();
    const signal = controller.signal;
    const vivo = () => !signal.aborted;
    const falliti = [];
    const conErrore = nome => e => {
      if (vivo()) {
        falliti.push(nome);
        console.warn(`Dashboard: "${nome}" non disponibile:`, e?.message || e);
      }
      return { data: null };
    };

    // Range date del periodo scelto (mese singolo o intero anno).
    const dataDa = mese ? `${anno}-${String(mese).padStart(2, '0')}-01` : `${anno}-01-01`;
    const dataA = mese
      ? `${anno}-${String(mese).padStart(2, '0')}-${String(ultimoGiorno(anno, mese)).padStart(2, '0')}`
      : `${anno}-12-31`;

    // IVA e scadenze cambiano endpoint a seconda che ci sia il mese o no.
    const ivaReq = mese
      ? api.get(`/api/verifica-coerenza/iva/${anno}/${mese}`, { signal }).catch(conErrore('IVA'))
      : api
          .get(`/api/verifica-coerenza/confronto-iva-completo/${anno}`, { signal })
          .catch(conErrore('IVA'));
    const scadReq = mese
      ? api
          .get(`/api/scadenze?anno=${anno}&mese=${mese}&include_passate=true&limit=30`, { signal })
          .catch(conErrore('scadenze'))
      : api
          .get(`/api/scadenze/prossime?giorni=120&limit=12`, { signal })
          .catch(conErrore('scadenze'));

    (async () => {
      setLoading(true);
      const [crRes, pnRes, ivaRes, scadRes, trendRes] = await Promise.all([
        api
          .get(`/api/controllo-gestione/costi-ricavi?anno=${anno}${mese ? `&mese=${mese}` : ''}`, {
            signal,
          })
          .catch(conErrore('fatturato e costi')),
        api
          .get(`/api/prima-nota/stats?data_da=${dataDa}&data_a=${dataA}`, { signal })
          .catch(conErrore('cassa e banca')),
        ivaReq,
        scadReq,
        api
          .get(`/api/dashboard/trend-mensile?anno=${anno}`, { signal })
          .catch(conErrore('grafico annuale')),
      ]);
      if (!vivo()) return;
      setCostiRicavi(crRes.data);
      setPrimaNota(pnRes.data);
      setIva(ivaRes.data);
      setScadenze(scadRes.data);
      setTrend(trendRes.data);
      setErroriApi(falliti);
      setLoading(false);
    })();

    return () => controller.abort();
  }, [anno, mese]);

  // ── Valori normalizzati per le card (difensivi sulla forma dei dati) ──
  const ricavi = costiRicavi?.ricavi?.totale ?? null;
  const costi = costiRicavi?.costi ?? null;
  const margine = costiRicavi?.margine ?? null;
  const cassa = primaNota?.cassa ?? null;
  const banca = primaNota?.banca ?? null;

  // IVA: forma diversa fra mese (verifica) e anno (confronto completo).
  const ivaDaVersare = mese
    ? iva?.saldo?.iva_da_versare ?? null
    : iva?.totali?.saldo_annuale != null
      ? Math.max(iva.totali.saldo_annuale, 0)
      : null;
  const ivaACredito = mese
    ? iva?.saldo?.iva_a_credito ?? null
    : iva?.totali?.saldo_annuale != null
      ? Math.max(-iva.totali.saldo_annuale, 0)
      : null;

  // ── Scorciatoie-domanda: la risposta grande in cima al periodo scelto ──
  const RISPOSTE = useMemo(
    () => [
      {
        id: 'incassato',
        label: 'Quanto ho incassato?',
        Icon: Wallet,
        colore: COLORS.success,
        valore: ricavi,
        testo: v => `Hai incassato ${formatEuro(v)} (${etichettaPeriodo}).`,
      },
      {
        id: 'speso',
        label: 'Quanto ho speso?',
        Icon: ShoppingCart,
        colore: COLORS.danger,
        valore: costi?.totale ?? null,
        testo: v => `Hai speso ${formatEuro(v)} (${etichettaPeriodo}).`,
      },
      {
        id: 'utile',
        label: 'Quanto mi è rimasto?',
        Icon: TrendingUp,
        colore: COLORS.primary,
        valore: margine?.importo ?? null,
        testo: v =>
          `${v >= 0 ? 'Utile' : 'Perdita'} di ${formatEuro(Math.abs(v))} (${etichettaPeriodo}${
            margine?.percentuale != null ? `, margine ${margine.percentuale}%` : ''
          }).`,
      },
      {
        id: 'cassa',
        label: 'Quanto ho in cassa?',
        Icon: Banknote,
        colore: COLORS.success,
        valore: cassa?.saldo ?? null,
        testo: v => `Saldo di cassa ${formatEuro(v)} nel periodo (${etichettaPeriodo}).`,
      },
      {
        id: 'banca',
        label: 'Quanto ho in banca?',
        Icon: Landmark,
        colore: COLORS.info,
        valore: banca?.saldo ?? null,
        testo: v => `Saldo di banca ${formatEuro(v)} nel periodo (${etichettaPeriodo}).`,
      },
      {
        id: 'iva',
        label: 'Quanta IVA devo?',
        Icon: Receipt,
        colore: COLORS.warning,
        valore: ivaDaVersare,
        testo: v =>
          v > 0
            ? `IVA da versare ${formatEuro(v)} (${etichettaPeriodo}).`
            : `Nessuna IVA da versare${
                ivaACredito ? `, a credito ${formatEuro(ivaACredito)}` : ''
              } (${etichettaPeriodo}).`,
      },
    ],
    [ricavi, costi, margine, cassa, banca, ivaDaVersare, ivaACredito, etichettaPeriodo]
  );

  const rispostaAttiva = RISPOSTE.find(r => r.id === domanda);

  return (
    <PageLayout title="Dashboard" icon="📊" subtitle={`Numeri di ${etichettaPeriodo}`}>
      {/* ── BARRA FILTRI: Anno (globale) + Mese ── */}
      <div style={STILI.barraFiltri} data-testid="dashboard-filtri">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={STILI.etichetta}>Anno</span>
          <AnnoSelector />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={STILI.etichetta}>Mese</span>
          <select
            value={mese}
            onChange={e => {
              setMese(Number(e.target.value));
              setDomanda(null);
            }}
            data-testid="dashboard-mese"
            style={STILI.selectMese}
          >
            <option value={0}>Tutto l'anno</option>
            {MESI.map((m, i) => (
              <option key={m} value={i + 1}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <span style={STILI.periodoAttivo}>
          Stai guardando: <strong>{etichettaPeriodo}</strong>
        </span>
      </div>

      {/* ── SCORCIATOIE-DOMANDA ── */}
      <div style={STILI.domandeWrap} data-testid="dashboard-domande">
        <span style={{ ...STILI.etichetta, display: 'flex', alignItems: 'center', gap: 5 }}>
          <HelpCircle size={14} /> Chiedi:
        </span>
        {RISPOSTE.map(r => {
          const attiva = domanda === r.id;
          return (
            <button
              key={r.id}
              onClick={() => setDomanda(attiva ? null : r.id)}
              data-testid={`domanda-${r.id}`}
              style={{
                ...STILI.bottoneDomanda,
                background: attiva ? r.colore : '#fff',
                color: attiva ? '#fff' : COLORS.text,
                borderColor: attiva ? r.colore : COLORS.border,
              }}
            >
              <r.Icon size={14} />
              {r.label}
            </button>
          );
        })}
      </div>

      {/* Risposta grande alla domanda scelta */}
      {rispostaAttiva && (
        <div
          style={{ ...STILI.rispostaBox, borderLeft: `5px solid ${rispostaAttiva.colore}` }}
          data-testid="dashboard-risposta"
        >
          <rispostaAttiva.Icon size={26} style={{ color: rispostaAttiva.colore, flexShrink: 0 }} />
          <div>
            <div style={{ fontSize: 13, color: COLORS.textMuted }}>{rispostaAttiva.label}</div>
            <div style={{ fontSize: 22, fontWeight: 800, color: COLORS.text }}>
              {rispostaAttiva.valore == null
                ? 'Dato non disponibile'
                : rispostaAttiva.testo(rispostaAttiva.valore)}
            </div>
          </div>
        </div>
      )}

      {/* Avviso endpoint in errore (distinto da "nessun dato") */}
      {erroriApi.length > 0 && (
        <div style={STILI.avvisoErrori} data-testid="dashboard-api-errors">
          ⚠️ Sezioni non disponibili in questo momento (errore, non «nessun dato»):{' '}
          {erroriApi.join(', ')}.
        </div>
      )}

      {loading ? (
        <div style={STILI.loading}>Caricamento di {etichettaPeriodo}…</div>
      ) : (
        <div style={STILI.griglia}>
          {/* FATTURATO / RICAVI */}
          <CardBox titolo="Fatturato / Ricavi" Icon={Wallet} colore={COLORS.success}>
            <ValoreGrande valore={ricavi} colore={COLORS.success} />
            {costiRicavi?.ricavi && (
              <Riga label="di cui corrispettivi" valore={costiRicavi.ricavi.corrispettivi} />
            )}
            <Nota>Ricavi del periodo selezionato (corrispettivi incassati).</Nota>
          </CardBox>

          {/* ACQUISTI / COSTI */}
          <CardBox titolo="Acquisti / Costi" Icon={ShoppingCart} colore={COLORS.danger}>
            <ValoreGrande valore={costi?.totale} colore={COLORS.danger} />
            {costi && (
              <>
                <Riga label="Personale" valore={costi.personale} />
                <Riga label="Acquisti merce" valore={costi.acquisti_merce} />
                <Riga label="Altre uscite" valore={costi.altre_uscite} />
              </>
            )}
          </CardBox>

          {/* MARGINE */}
          <CardBox
            titolo={margine?.tipo === 'perdita' ? 'Perdita' : 'Utile / Margine'}
            Icon={margine?.tipo === 'perdita' ? TrendingDown : TrendingUp}
            colore={margine?.tipo === 'perdita' ? COLORS.danger : COLORS.primary}
          >
            <ValoreGrande
              valore={margine?.importo}
              colore={margine?.tipo === 'perdita' ? COLORS.danger : COLORS.primary}
            />
            {margine?.percentuale != null && (
              <Riga label="Margine %" valore={`${margine.percentuale}%`} raw />
            )}
            <Nota>Ricavi meno costi del periodo.</Nota>
          </CardBox>

          {/* CASSA */}
          <CardBox titolo="Cassa" Icon={Banknote} colore={COLORS.success}>
            <ValoreGrande valore={cassa?.saldo} colore={COLORS.success} />
            {cassa && (
              <>
                <Riga label="Entrate" valore={cassa.entrate} />
                <Riga label="Uscite" valore={cassa.uscite} />
                <Riga label="Movimenti" valore={cassa.movimenti} raw />
              </>
            )}
            <Nota>Saldo dei movimenti di cassa nel periodo.</Nota>
          </CardBox>

          {/* BANCA */}
          <CardBox titolo="Banca" Icon={Landmark} colore={COLORS.info}>
            <ValoreGrande valore={banca?.saldo} colore={COLORS.info} />
            {banca && (
              <>
                <Riga label="Entrate" valore={banca.entrate} />
                <Riga label="Uscite" valore={banca.uscite} />
                <Riga label="Movimenti" valore={banca.movimenti} raw />
              </>
            )}
            <Nota>Saldo dei movimenti di banca nel periodo.</Nota>
          </CardBox>

          {/* IVA */}
          <CardBox titolo="IVA" Icon={Receipt} colore={COLORS.warning}>
            {ivaDaVersare != null && ivaDaVersare > 0 ? (
              <>
                <ValoreGrande valore={ivaDaVersare} colore={COLORS.warning} />
                <Nota>IVA da versare nel periodo.</Nota>
              </>
            ) : ivaACredito != null && ivaACredito > 0 ? (
              <>
                <ValoreGrande valore={ivaACredito} colore={COLORS.info} />
                <Nota>IVA a credito nel periodo.</Nota>
              </>
            ) : (
              <>
                <ValoreGrande valore={0} colore={COLORS.textMuted} />
                <Nota>Nessuna IVA da versare nel periodo.</Nota>
              </>
            )}
          </CardBox>

          {/* SCADENZE / F24 */}
          <CardBox
            titolo="Scadenze / F24"
            Icon={CalendarClock}
            colore={COLORS.warning}
            fullWidth
          >
            {scadenze?.scadenze?.length ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {scadenze.scadenze.slice(0, 8).map((s, i) => (
                  <div key={s.id || i} style={STILI.rigaScadenza}>
                    <span style={{ fontWeight: 700, minWidth: 92 }}>{s.data}</span>
                    <span style={STILI.tagTipo}>{s.tipo}</span>
                    <span style={{ flex: 1, color: COLORS.text }}>{s.descrizione}</span>
                    {s.importo ? (
                      <span style={{ fontWeight: 700 }}>{formatEuro(s.importo)}</span>
                    ) : null}
                    {s.urgente && <span style={STILI.tagUrgente}>urgente</span>}
                  </div>
                ))}
              </div>
            ) : (
              <Nota>Nessuna scadenza {mese ? `in ${MESI[mese - 1]}` : 'nei prossimi mesi'}.</Nota>
            )}
          </CardBox>

          {/* GRAFICO ANNO — con il mese selezionato evidenziato */}
          {trend?.chart_data?.labels?.length > 0 && (
            <CardBox
              titolo={`Andamento ${anno} — entrate per mese`}
              Icon={TrendingUp}
              colore={COLORS.primary}
              fullWidth
            >
              <ResponsiveContainer width="100%" height={240}>
                <BarChart
                  data={trend.chart_data.labels.map((l, i) => ({
                    mese: l,
                    entrate: trend.chart_data.entrate?.[i] ?? 0,
                    uscite: trend.chart_data.uscite?.[i] ?? 0,
                  }))}
                  onClick={e => {
                    if (e?.activeTooltipIndex != null) {
                      setMese(e.activeTooltipIndex + 1);
                      setDomanda(null);
                    }
                  }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                  <XAxis dataKey="mese" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} width={70} tickFormatter={v => formatEuro(v)} />
                  <Tooltip formatter={v => formatEuro(v)} />
                  <Bar dataKey="entrate" name="Entrate" radius={[4, 4, 0, 0]}>
                    {trend.chart_data.labels.map((l, i) => (
                      <Cell
                        key={l}
                        fill={mese === i + 1 ? COLORS.primary : '#93b4d8'}
                        cursor="pointer"
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <Nota>Tocca una barra per filtrare le card su quel mese.</Nota>
            </CardBox>
          )}
        </div>
      )}
    </PageLayout>
  );
}

/* ────────────────────────── Componenti card ────────────────────────── */

function CardBox({ titolo, Icon, colore, children, fullWidth = false }) {
  return (
    <div style={{ ...STILI.card, ...(fullWidth ? { gridColumn: '1 / -1' } : {}) }}>
      <div style={STILI.cardHeader}>
        <span style={{ ...STILI.cardIcona, background: colore }}>
          <Icon size={16} color="#fff" />
        </span>
        <h3 style={STILI.cardTitolo}>{titolo}</h3>
      </div>
      {children}
    </div>
  );
}

function ValoreGrande({ valore, colore }) {
  return (
    <div style={{ fontSize: 28, fontWeight: 800, color: valore == null ? COLORS.textMuted : colore }}>
      {valore == null ? '—' : formatEuro(valore)}
    </div>
  );
}

function Riga({ label, valore, raw = false }) {
  return (
    <div style={STILI.riga}>
      <span style={{ color: COLORS.textMuted }}>{label}</span>
      <span style={{ fontWeight: 600, color: COLORS.text }}>
        {valore == null ? '—' : raw ? valore : formatEuro(valore)}
      </span>
    </div>
  );
}

function Nota({ children }) {
  return <div style={STILI.nota}>{children}</div>;
}

/* ────────────────────────────── Stili ────────────────────────────── */

const STILI = {
  barraFiltri: {
    display: 'flex',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 16,
    background: COLORS.card,
    border: `1px solid ${COLORS.border}`,
    borderRadius: 10,
    padding: '12px 16px',
    marginBottom: 12,
  },
  etichetta: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    color: COLORS.textMuted,
  },
  selectMese: {
    padding: '7px 10px',
    borderRadius: 8,
    border: `1px solid ${COLORS.border}`,
    background: '#fff',
    color: COLORS.text,
    fontWeight: 700,
    fontSize: 14,
    minWidth: 140,
  },
  periodoAttivo: {
    marginLeft: 'auto',
    fontSize: 13,
    color: COLORS.textMuted,
  },
  domandeWrap: {
    display: 'flex',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
  },
  bottoneDomanda: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '7px 12px',
    borderRadius: 20,
    border: `1px solid ${COLORS.border}`,
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 140ms ease',
  },
  rispostaBox: {
    display: 'flex',
    alignItems: 'center',
    gap: 14,
    background: COLORS.card,
    border: `1px solid ${COLORS.border}`,
    borderRadius: 10,
    padding: '14px 18px',
    marginBottom: 14,
  },
  avvisoErrori: {
    padding: '8px 12px',
    background: '#fffbeb',
    border: '1px solid #fcd34d',
    borderRadius: 8,
    color: '#92400e',
    fontSize: 13,
    marginBottom: 12,
  },
  loading: {
    padding: 40,
    textAlign: 'center',
    color: COLORS.textMuted,
  },
  griglia: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
    gap: 14,
  },
  card: {
    background: COLORS.card,
    border: `1px solid ${COLORS.border}`,
    borderRadius: 12,
    padding: 16,
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    marginBottom: 4,
  },
  cardIcona: {
    width: 30,
    height: 30,
    borderRadius: 8,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  cardTitolo: {
    margin: 0,
    fontSize: 15,
    fontWeight: 700,
    color: COLORS.text,
  },
  riga: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: 13,
    paddingTop: 2,
  },
  nota: {
    fontSize: 12,
    color: COLORS.textMuted,
    marginTop: 4,
  },
  rigaScadenza: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    fontSize: 13,
    padding: '6px 8px',
    borderRadius: 6,
    background: COLORS.bgAlt,
    flexWrap: 'wrap',
  },
  tagTipo: {
    fontSize: 11,
    fontWeight: 700,
    padding: '2px 7px',
    borderRadius: 12,
    background: COLORS.primarySoft,
    color: COLORS.primary,
  },
  tagUrgente: {
    fontSize: 11,
    fontWeight: 700,
    padding: '2px 7px',
    borderRadius: 12,
    background: COLORS.dangerLight,
    color: COLORS.danger,
  },
};

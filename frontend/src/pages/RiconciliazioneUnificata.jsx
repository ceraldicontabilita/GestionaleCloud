import React, { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import { tabUnificataDaPath } from './hub/segmentiHub';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import api from '../api';
import {
  formatEuro,
  formatDateIT,
  formatDateGGMM,
  STYLES,
  COLORS,
  button,
  badge,
  useIsMobile,
  RG,
  pagePad,
} from '../lib/utils';
import { ListaAdattiva } from '../components/ds';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { toast } from 'sonner';
import { PageLayout } from '../components/PageLayout';
import { VisoreOriginale } from '../components/ApriOriginale';
import { urlOriginale, euroOppure } from '../lib/vista';
import AvvisoBonarioF24 from '../components/AvvisoBonarioF24';
import RiscontroQuietanzeBanca from '../components/RiscontroQuietanzeBanca';
import LinkContropartita, {
  ROTTE_CONTROPARTITA, PALETTE_CONTROPARTITA,
} from '../components/LinkContropartita';
import { useScegliOpzione } from '../components/ScegliOpzione';
import { Calendar, ChevronDown, ChevronRight, ChevronUp, Hourglass, ChartColumn, Check, ClipboardList, Eye, FileText, Info, Landmark, Lightbulb, Link2, Paperclip, RefreshCw, Search, Trash2, TriangleAlert, User, X } from 'lucide-react';

const ICO = { verticalAlign: '-2px', flexShrink: 0 };
const eurAbs = v => (v === null || v === undefined || v === '' ? euroOppure(v) : euroOppure(Math.abs(Number(v))));

const RiconciliazionePaypalLazy = lazy(() => import('./RiconciliazionePaypal.jsx'));

/**
 * RICONCILIAZIONE UNIFICATA
 *
 * Una sola pagina smart con:
 * - Dashboard riepilogo
 * - Tab: Banca | Assegni | F24 | Stipendi
 * - Auto-matching intelligente
 * - Flussi a cascata automatici
 * - URL con tab: /riconciliazione/banca, /riconciliazione/assegni, etc.
 */

const RENTAL_RECONCILIATION_TERMS = [
  'leasys',
  'ald automotive',
  'arval',
  'leaseplan',
];

const BANK_ANOMALY_LABELS = {
  riconciliato_senza_target:
    'Segnato come riconciliato, ma senza una fattura, un F24, uno stipendio o un altro destinatario collegato.',
  fingerprint_duplicato:
    'Possibile duplicato: esiste un altro movimento con la stessa impronta bancaria.',
  allocazione_non_quadrata:
    'Le quote collegate non coincidono al centesimo con l\'importo del movimento.',
};

/**
 * Movimento di estratto conto → contropartite (audit 03/09/2026 §6, PR 16):
 * il backend espone `collegamenti` (fattura_id, prima_nota_banca_id,
 * stipendio_id, f24_ids…) letti dai campi reali del movimento; per un
 * movimento ancora da confermare la fattura PROPOSTA dall'analisi ha il suo
 * link, etichettato come proposta (mai spacciata per collegamento certo).
 */
export function linksContropartitaMovimento(m = {}) {
  const c = m.collegamenti || {};
  const links = [];
  const tipoFattura = ['fattura', 'fattura_sdd', 'fattura_bonifico'].includes(m.tipo);
  const fatturaProposta = tipoFattura ? m.suggerimenti?.[0]?.id : null;
  const fatturaId = c.fattura_id || fatturaProposta;
  if (fatturaId) {
    links.push({
      key: 'fattura',
      to: ROTTE_CONTROPARTITA.fattura(fatturaId),
      etichetta: c.fattura_id ? 'Vai alla fattura' : 'Fattura proposta',
      title: `Fattura ${m.numero_fattura || m.suggerimenti?.[0]?.numero || fatturaId} · ${c.fattura_id ? 'collegata al movimento' : 'proposta dall\'analisi, da confermare'}`,
    });
  }
  if (c.prima_nota_banca_id) {
    links.push({
      key: 'prima-nota',
      to: ROTTE_CONTROPARTITA.primaNotaBanca(c.prima_nota_banca_id),
      etichetta: 'Prima Nota Banca',
      title: `Riga di Prima Nota Banca ${c.prima_nota_banca_id} · ${formatDateIT(m.data || '')} · ${eurAbs(m.importo)}`,
    });
  }
  return links;
}

function LinksContropartita({ m }) {
  const links = linksContropartitaMovimento(m);
  if (!links.length) return null;
  const id = m.movimento_id || m.id;
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }} onClick={e => e.stopPropagation()}>
      {links.map(l => (
        <LinkContropartita key={l.key} to={l.to} compatto testId={`link-${l.key}-${id}`} title={l.title}>
          {l.etichetta}
        </LinkContropartita>
      ))}
    </div>
  );
}

/**
 * Pannello del movimento richiesto via deep-link
 * `/riconciliazione/banca?movimento=<id estratto conto>` (da Prima Nota,
 * Scadenze, F24): il record viene caricato e mostrato in evidenza con le
 * sue contropartite, anche se non è nella coda "da confermare".
 */
export function PannelloMovimentoRichiesto({ id, richiesta, onChiudi }) {
  if (!id) return null;
  const dati = richiesta?.dati || {};
  const links = linksContropartitaMovimento(dati);
  const c = dati.collegamenti || {};
  return (
    <div
      data-testid="movimento-richiesto"
      style={{
        padding: 14, borderBottom: '1px solid #e6e3d9',
        background: PALETTE_CONTROPARTITA.evidenza,
        borderLeft: `4px solid ${PALETTE_CONTROPARTITA.salvia}`,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <strong style={{ color: PALETTE_CONTROPARTITA.salviaScura, fontSize: 14 }}>
          Movimento estratto conto {id}
        </strong>
        <button
          type="button"
          onClick={onChiudi}
          style={{ background: 'white', border: `1px solid ${PALETTE_CONTROPARTITA.bordo}`, borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 12, color: PALETTE_CONTROPARTITA.salviaScura, fontWeight: 700 }}
        >
          Chiudi
        </button>
      </div>
      {richiesta?.stato === 'caricamento' && (
        <div style={{ fontSize: 12.5, color: '#7a776e', marginTop: 4 }}>Caricamento del movimento…</div>
      )}
      {richiesta?.stato === 'errore' && (
        <div style={{ fontSize: 12.5, color: '#b0362b', marginTop: 4 }}>
          Movimento non trovato nell'estratto conto: {richiesta.errore}
        </div>
      )}
      {richiesta?.stato === 'ok' && (
        <>
          <div style={{ fontSize: 13, marginTop: 4, color: '#141413' }}>
            {formatDateIT(dati.data || '')} · {eurAbs(dati.importo)} · {dati.descrizione || '—'}
          </div>
          <div style={{ fontSize: 12, color: '#5f5c55', marginTop: 2 }}>
            Tipo: {dati.tipo || 'non riconosciuto'} · {c.riconciliato ? 'riconciliato' : 'non riconciliato'}
            {c.tipo_riconciliazione ? ` (${c.tipo_riconciliazione})` : ''}
            {c.stipendio_id ? ` · stipendio ${c.stipendio_id}` : ''}
            {c.assegno_id ? ` · assegno ${c.assegno_id}` : ''}
            {(c.f24_ids || []).length ? ` · F24 ${c.f24_ids.join(', ')}` : ''}
          </div>
          {links.length ? (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
              {links.map(l => (
                <LinkContropartita key={l.key} to={l.to} testId={`link-${l.key}-richiesto`} title={l.title}>
                  {l.etichetta}
                </LinkContropartita>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: 12, color: '#7a776e', marginTop: 6 }}>
              Nessuna contropartita collegata a questo movimento.
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function descriviAnomaliaBanca(motivo = {}) {
  const descrizione = BANK_ANOMALY_LABELS[motivo.codice]
    || 'Anomalia bancaria da verificare nel dettaglio.';
  if (motivo.codice === 'allocazione_non_quadrata' && motivo.differenza_cents) {
    return `${descrizione} Differenza: ${formatEuro(motivo.differenza_cents / 100)}.`;
  }
  if (motivo.codice === 'fingerprint_duplicato' && motivo.record_conservato_id) {
    return `${descrizione} Movimento conservato: ${motivo.record_conservato_id}.`;
  }
  return descrizione;
}

export function isRentalReconciliationMovement(movement) {
  const haystack = [
    movement?.descrizione,
    movement?.causale,
    movement?.tipo,
    movement?.fornitore,
    movement?.supplier_name,
    movement?.beneficiario,
    movement?.nome,
    movement?.controparte,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  return RENTAL_RECONCILIATION_TERMS.some(term => haystack.includes(term));
}

export default function RiconciliazioneUnificata() {
  const isMobile = useIsMobile();
  const [scegli, dialogoScelta] = useScegliOpzione();
  const { anno } = useAnnoGlobale();
  const navigate = useNavigate();
  const location = useLocation();
  const ambitoNoleggio = new URLSearchParams(location.search).get('ambito') === 'noleggio';

  // Deep-link "?movimento=<id estratto conto>" (audit 03/09/2026 §6, PR 16):
  // carica il singolo movimento dall'endpoint esistente e lo mostra in
  // evidenza nel tab Banca con le contropartite collegate.
  const movimentoRichiestoId = new URLSearchParams(location.search).get('movimento') || '';
  const [movimentoRichiesto, setMovimentoRichiesto] = useState(null);
  useEffect(() => {
    if (!movimentoRichiestoId) {
      setMovimentoRichiesto(null);
      return undefined;
    }
    let attivo = true;
    setMovimentoRichiesto({ stato: 'caricamento' });
    api
      .get(`/api/operazioni-da-confermare/smart/movimento/${encodeURIComponent(movimentoRichiestoId)}`)
      .then(r => { if (attivo) setMovimentoRichiesto({ stato: 'ok', dati: r.data || {} }); })
      .catch(e => {
        if (attivo) setMovimentoRichiesto({ stato: 'errore', errore: e.response?.data?.detail || e.message });
      });
    return () => { attivo = false; };
  }, [movimentoRichiestoId]);

  // Tab dall'URL (/riconciliazione/banca -> banca): un segmento intero,
  // mai un pezzo di «movimenti-banca».
  const getTabFromPath = () => tabUnificataDaPath(location.pathname);

  const [activeTab, setActiveTab] = useState(getTabFromPath());
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [processing, setProcessing] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [anomalyReport, setAnomalyReport] = useState(null);

  // Aggiorna URL quando cambia tab. Usa sempre il prefisso "/riconciliazione":
  // è l'unico effettivamente instradato in main.jsx — "/riconciliazione-unificata"
  // esiste solo come redirect legacy verso "/riconciliazione" SENZA sotto-tab,
  // quindi navigare a "/riconciliazione-unificata/<tab>" cadeva sul catch-all e
  // rimandava l'utente alla Dashboard invece di cambiare tab.
  const handleTabChange = tabId => {
    setActiveTab(tabId);
    if (tabId === 'dashboard') {
      navigate('/riconciliazione');
    } else {
      navigate(`/riconciliazione/${tabId}`);
    }
  };

  // Sincronizza tab con URL al mount e quando cambia URL
  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) {
      setActiveTab(tab);
    }
  }, [location.pathname]);

  // Dati per ogni sezione
  const [stats, setStats] = useState({});
  const [movimentiBanca, setMovimentiBanca] = useState([]);
  const [assegni, setAssegni] = useState([]);
  const [f24Pendenti, setF24Pendenti] = useState([]);
  const [stipendiPendenti, setStipendiPendenti] = useState([]);
  const [documentiNonAssociati, setDocumentiNonAssociati] = useState([]);
  const [documentiStats, setDocumentiStats] = useState(null);

  // Paginazione
  const [currentLimit, setCurrentLimit] = useState(25);
  const [hasMore, setHasMore] = useState(true);

  // Filtri avanzati
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState({
    dataFrom: '',
    dataTo: '',
    importoMin: '',
    importoMax: '',
    search: '',
  });

  // Riepilogo dei collegamenti già presenti: è informativo e non avvia
  // correzioni o riconciliazioni automatiche.
  const [reconciliationStats, setReconciliationStats] = useState({ matched: 0, pending: 0 });
  const loadAbortRef = useRef(null);
  const loadSequenceRef = useRef(0);

  // Applica filtri ai movimenti
  const applyFilters = movimenti => {
    return movimenti.filter(m => {
      if (ambitoNoleggio && !isRentalReconciliationMovement(m)) return false;

      // Usa data o data_emissione
      const dataMovimento = m.data || m.data_emissione;

      // Filtro data
      if (filters.dataFrom && dataMovimento < filters.dataFrom) return false;
      if (filters.dataTo && dataMovimento > filters.dataTo) return false;

      // Filtro importo
      const importo = Math.abs(parseFloat(m.importo) || 0);
      if (filters.importoMin && importo < parseFloat(filters.importoMin)) return false;
      if (filters.importoMax && importo > parseFloat(filters.importoMax)) return false;

      // Filtro ricerca testo
      if (filters.search) {
        const search = filters.search.toLowerCase();
        const desc = (m.descrizione || '').toLowerCase();
        const tipo = (m.tipo || '').toLowerCase();
        if (!desc.includes(search) && !tipo.includes(search)) return false;
      }

      return true;
    });
  };

  // Movimenti filtrati
  const movimentiBancaFiltrati = applyFilters(movimentiBanca);
  const assegniFiltrati = applyFilters(assegni);
  const stipendiFiltrati = applyFilters(stipendiPendenti);

  useEffect(() => {
    loadAllData();
    return () => loadAbortRef.current?.abort();
  }, [anno]);

  const loadAllData = async (limit = 50) => {
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    loadAbortRef.current = controller;
    const sequence = ++loadSequenceRef.current;
    const isCurrent = () => sequence === loadSequenceRef.current && !controller.signal.aborted;
    setLoading(true);
    setLoadError(null);
    try {
      // I movimenti sono la parte necessaria per usare la pagina: arrivano dal
      // percorso veloce e vengono mostrati subito. I suggerimenti, piu' costosi,
      // si innestano dopo senza tenere bloccata tutta la schermata.
      const erroriCaricamento = [];
      const [bancaRes, stipendiRes] = await Promise.all([
        api
          .get(`/api/operazioni-da-confermare/smart/banca-veloce?limit=${limit}&anno=${anno}`, {
            signal: controller.signal,
          })
          .catch(e => {
            if (controller.signal.aborted) throw e;
            erroriCaricamento.push(e.response?.data?.detail || e.message);
            return { data: { movimenti: [], stats: {}, assegni: [] } };
          }),
        api
          .get('/api/operazioni-da-confermare/smart/cerca-stipendi', {
            signal: controller.signal,
          })
          .catch(e => {
            if (controller.signal.aborted) throw e;
            erroriCaricamento.push(e.response?.data?.detail || e.message);
            return { data: { stipendi: [] } };
          }),
      ]);
      if (!isCurrent()) return;
      if (erroriCaricamento.length > 0) {
        setLoadError(
          `Alcuni dati non si sono caricati correttamente (${erroriCaricamento.length}/2 sorgenti in errore): ${erroriCaricamento[0]}`
        );
      }

      const movimentiBase = (bancaRes.data?.movimenti || []).map(m => ({
        ...m,
        movimento_id: m.movimento_id || m.id,
        descrizione: m.descrizione || m.descrizione_originale || m.causale || '-',
        suggerimenti: m.suggerimenti || [],
        analisi_in_corso: true,
      }));
      const assegniDaApi = (bancaRes.data?.assegni || []).map(a => ({
        ...a,
        numero_assegno: a.numero_assegno || a.numero,
        data: a.data || a.data_emissione,
        descrizione:
          a.descrizione ||
          a.causale ||
          a.beneficiario ||
          `Assegno ${a.numero || a.numero_assegno || ''}`,
      }));

      const totalRows = Number(
        bancaRes.data?.stats?.totale_righe ?? movimentiBase.length
      );
      setHasMore(movimentiBase.length < totalRows);
      setCurrentLimit(limit);

      // Movimenti banca (escludi prelievi assegno)
      setMovimentiBanca(
        movimentiBase.filter(m => !m.descrizione?.toUpperCase()?.includes('PRELIEVO ASSEGNO'))
      );

      // Assegni da riconciliare (già filtrati dal backend)
      setAssegni(assegniDaApi);

      const stipendi = stipendiRes.data?.stipendi || [];

      setStipendiPendenti(stipendi);

      // Aggiorna stats iniziali (F24 caricato su richiesta)
      setStats({
        ...(bancaRes.data?.stats || {}),
        totale: totalRows,
        totale_righe: totalRows,
        righe_caricate: movimentiBase.length,
        banca: totalRows,
        assegni: assegniDaApi.length,
        f24: 0, // Caricato su richiesta manuale
        stipendi: stipendi.length,
        documenti: 0, // Caricato dopo
        fatture_da_pagare: bancaRes.data?.stats?.fatture_da_pagare || 0,
      });

      // Conteggio read-only dei collegamenti già registrati.
      setReconciliationStats({
        matched: bancaRes.data?.stats?.riconciliati || 0,
        pending: bancaRes.data?.stats?.non_riconciliati || totalRows,
      });

      setLoading(false);

      api
        .get(`/api/operazioni-da-confermare/smart/analizza?limit=${limit}&anno=${anno}`, {
          signal: controller.signal,
        })
        .then(analizzaRes => {
          if (!isCurrent()) return;
          const analizzati = analizzaRes.data?.movimenti || [];
          if (analizzati.length) {
            setMovimentiBanca(
              analizzati
                .map(m => ({
                  ...m,
                  analisi_in_corso: false,
                  analisi_non_disponibile: Boolean(analizzaRes.data?.analisi_non_disponibile),
                }))
                .filter(m => !m.descrizione?.toUpperCase()?.includes('PRELIEVO ASSEGNO'))
            );
          }
          if (analizzaRes.data?.analisi_non_disponibile) {
            setLoadError('Movimenti caricati; i suggerimenti hanno superato il tempo massimo. Usa Rileggi per riprovare.');
          }
          setStats(prev => ({ ...prev, ...(analizzaRes.data?.stats || {}) }));
          setReconciliationStats(prev => ({
            matched: analizzaRes.data?.stats?.riconciliati ?? prev.matched,
            pending: analizzaRes.data?.stats?.totale_righe ?? prev.pending,
          }));
        })
        .catch(e => {
          if (!controller.signal.aborted && isCurrent()) {
            setLoadError(`Movimenti caricati; suggerimenti temporaneamente non disponibili: ${e.response?.data?.detail || e.message}`);
          }
        });

      // F24: RIMOSSO dal caricamento automatico (prendeva ~35s e causava un "reload visivo")
      // Caricato solo quando l'utente apre il tab F24 — vedi loadF24OnDemand()

      // Carica Documenti Non Associati in background
      api
        .get('/api/documenti-non-associati/lista?limit=100')
        .then(docsRes => {
          const docs = docsRes.data?.documenti || [];
          setDocumentiNonAssociati(docs);
          setStats(prev => ({ ...prev, documenti: docs.length }));
        })
        .catch(() => {
          console.warn('Documenti non caricati');
        });

      // Carica statistiche documenti
      api
        .get('/api/documenti-non-associati/statistiche')
        .then(statsRes => {
          setDocumentiStats(statsRes.data);
        })
        .catch(() => {});
    } catch (e) {
      if (controller.signal.aborted) return;
      console.error('Errore caricamento:', e);
      setLoading(false);
    }
  };

  // Carica altri movimenti
  const loadMore = async () => {
    const newLimit = currentLimit + 25;
    setLoadingMore(true);
    try {
      const bancaRes = await api.get(
        `/api/operazioni-da-confermare/smart/banca-veloce?limit=${newLimit}&anno=${anno}`
      );
      const movimenti = (bancaRes.data?.movimenti || []).map(m => ({
        ...m,
        movimento_id: m.movimento_id || m.id,
        descrizione: m.descrizione || m.descrizione_originale || m.causale || '-',
        suggerimenti: m.suggerimenti || [],
        analisi_in_corso: true,
      }));
      const totalRows = Number(bancaRes.data?.stats?.totale_righe ?? movimenti.length);
      setHasMore(movimenti.length < totalRows);
      setCurrentLimit(newLimit);

      setMovimentiBanca(
        movimenti.filter(m => !m.descrizione?.toUpperCase()?.includes('PRELIEVO ASSEGNO'))
      );
      setStats(prev => ({
        ...prev,
        ...(bancaRes.data?.stats || {}),
        banca: totalRows,
        righe_caricate: movimenti.length,
      }));
    } catch (e) {
      toast.error('Caricamento non riuscito: ' + (e.response?.data?.detail || e.message));
    } finally {
      setLoadingMore(false);
    }
  };

  const [f24Loading, setF24Loading] = useState(false);

  // Carica F24 solo su richiesta esplicita (evita il "reload visivo" da ~35s)
  const loadF24OnDemand = async () => {
    setF24Loading(true);
    try {
      const f24Res = await api.get(`/api/operazioni-da-confermare/smart/cerca-f24?anno=${anno}`);
      const f24 = f24Res.data?.f24 || [];
      setF24Pendenti(f24);
      setStats(prev => ({ ...prev, f24: f24.length }));
    } catch (e) {
      toast.error('F24 non caricati: ' + (e.response?.data?.detail || e.message));
    } finally {
      setF24Loading(false);
    }
  };

  // Conferma singolo movimento
  const handleConferma = async (movimento, tipo, associazioni, modalita) => {
    setProcessing(movimento.movimento_id || movimento.id);
    try {
      const tipoEff = tipo || movimento.tipo;
      if (tipoEff === 'stipendio' && !movimento.movimento_id) {
        // Riga stipendio pendente (prima_nota_salari): cerca in estratto
        // conto il bonifico "FAVORE <nome dipendente>" e associa (18/07/2026)
        const atteso = Number(movimento.importo_busta ?? movimento.importo ?? 0);
        const giaPagato = Number(movimento.importo_bonifico ?? 0);
        const mismatch = atteso > 0 && giaPagato > 0 && Math.abs(atteso - giaPagato) > 0.01;
        const modalitaEff = modalita || (mismatch
          ? (await scegli({
            titolo: 'Importo stipendio e bonifici non coincidono',
            descrizione: 'Scegli come trattare il bonifico; «Annulla» lascia il dato sospeso.',
            opzioni: [
              { valore: 'acconto', etichetta: 'Acconto' },
              { valore: 'saldo', etichetta: 'Saldo' },
              { valore: 'multiplo', etichetta: 'Più bonifici (multiplo)' },
            ],
          }))?.valore
          : 'saldo');
        if (!modalitaEff || modalitaEff === 'errore') {
          toast.error('Conferma stipendio bloccata', {
            description: 'Seleziona acconto, saldo o multiplo; un dato incoerente resta sospeso.',
          });
          return;
        }
        const res = await api.post('/api/operazioni-da-confermare/smart/riconcilia-stipendio', {
          stipendio_id: movimento.id,
          modalita: modalitaEff,
        });
        if (res.data?.success) {
          const d = res.data.dettaglio?.[0];
          toast.success('Bonifico associato', {
            description: d ? `${d.dipendente}: € ${d.importo} del ${d.data_bonifico}` : undefined,
          });
        } else {
          toast.error('Nessun bonifico trovato', {
            description: res.data?.message,
          });
        }
        loadAllData();
        return;
      }
      const suggerimenti = Array.isArray(movimento.suggerimenti) ? movimento.suggerimenti : [];
      let scelte = Array.isArray(associazioni)
        ? associazioni
        : suggerimenti.length === 1
          ? [suggerimenti[0]]
          : [];
      const tipoFattura = ['fattura', 'fattura_sdd', 'fattura_bonifico'].includes(tipoEff);
      if (!scelte.length && tipoFattura && suggerimenti.length > 1) {
        if (movimento.quadratura?.stato === 'verificata') {
          scelte = suggerimenti.map(s => ({
            ...s,
            quota_cents: Number.isInteger(s.quota_cents)
              ? s.quota_cents : Math.round(Number(s.importo || 0) * 100),
          }));
        } else {
          const risposta = await scegli({
            titolo: 'Seleziona le fatture da pagare con questo movimento',
            descrizione: 'Ogni fattura porta la quota proposta; per cambiarla usa «Altro (scrivi tu)».',
            multipla: true,
            opzioni: suggerimenti.map((s, indice) => {
              const quota = Number.isInteger(s.quota_cents) ? s.quota_cents / 100 : Number(s.importo || 0);
              return { valore: String(indice), etichetta: `${s.numero || s.id}`, dettaglio: `fattura ${euroOppure(s.importo)} · quota ${formatEuro(quota)}`, quota: quota.toFixed(2) };
            }),
            altro: 'Quota in euro',
            conferma: 'Riconcilia',
          });
          scelte = (risposta?.valori || []).map(valore => {
            const item = suggerimenti[Number(valore)];
            return { ...item, quota_cents: Math.round(Number(risposta.quote[valore]) * 100) };
          }).filter(item => Number.isInteger(item.quota_cents) && item.quota_cents > 0);
        }
      }
      if (!scelte.length && suggerimenti.length > 1 && !tipoFattura) {
        const risposta = await scegli({
          titolo: 'Seleziona il candidato corretto',
          opzioni: suggerimenti.map((s, indice) => ({
            valore: String(indice),
            etichetta: `${s.fornitore || s.nome || s.dipendente || 'candidato'} - ${euroOppure(s.importo)}`,
          })),
        });
        if (risposta?.valore !== undefined && suggerimenti[Number(risposta.valore)]) {
          scelte = [suggerimenti[Number(risposta.valore)]];
        }
      }
      if (!scelte.length || (!tipoFattura && scelte.length !== 1)) {
        toast.error('Selezione obbligatoria', {
          description: 'Con più candidati devi selezionare esplicitamente quello corretto.',
        });
        return;
      }
      await api.post('/api/operazioni-da-confermare/smart/riconcilia-manuale', {
        movimento_id: movimento.movimento_id,
        tipo: tipoEff,
        associazioni: scelte,
        categoria: movimento.categoria,
      });
      toast.success('Movimento riconciliato');
      loadAllData();
    } catch (e) {
      toast.error('Riconciliazione non riuscita', {
        description: e.response?.data?.detail || e.message,
      });
    } finally {
      setProcessing(null);
    }
  };

  // Ignora movimento
  const handleIgnora = async movimento => {
    const risposta = await scegli({
      titolo: 'Perché escludi questo movimento dalla coda?',
      opzioni: [
        { valore: 'duplicato', etichetta: 'Duplicato', richiedeCampo: 'ID del movimento originale da conservare' },
        { valore: 'gia_pagato', etichetta: 'Già pagato' },
        { valore: 'non_pertinente', etichetta: 'Non pertinente' },
        { valore: 'movimento_non_bancario', etichetta: 'Movimento non bancario' },
        { valore: 'da_verificare', etichetta: 'Da verificare' },
      ],
      altro: 'Scrivi il motivo',
      conferma: 'Escludi',
    });
    if (!risposta) return;
    const codice = risposta.valore;
    const motivo = risposta.testo;
    if (!motivo?.trim()) return;
    const recordConservatoId = codice === 'duplicato' ? risposta.campo : null;
    if (codice === 'duplicato' && !recordConservatoId) return;
    setProcessing(movimento.movimento_id || movimento.id);
    try {
      await api.post('/api/operazioni-da-confermare/smart/ignora', {
        movimento_id: movimento.movimento_id || movimento.id,
        codice_motivo: codice,
        motivo: motivo.trim(),
        record_conservato_id: recordConservatoId,
        fingerprint: movimento.fingerprint,
      });
      toast.success('Movimento escluso dalla coda; la fonte bancaria resta conservata');
      loadAllData();
    } catch (e) {
      console.error('Errore ignora:', e);
      toast.error('Operazione non riuscita', {
        description: e.response?.data?.detail || e.message,
      });
    } finally {
      setProcessing(null);
    }
  };

  const handleAnalizzaAnomalie = async () => {
    setProcessing('analizza-anomalie');
    try {
      const response = await api.get(
        `/api/operazioni-da-confermare/smart/analizza-anomalie?anno=${anno}`
      );
      setAnomalyReport(response.data || {});
    } catch (e) {
      toast.error('Analisi anomalie non riuscita', {
        description: e.response?.data?.detail || e.message,
      });
    } finally {
      setProcessing(null);
    }
  };

  const handleVediProva = movimento => {
    const rule = movimento.regola?.id || 'regola non disponibile';
    const evidence = (movimento.evidenze || [])
      .map(item => item.testo || item.valore || item.id)
      .filter(Boolean)
      .join('\n');
    window.alert(`Regola: ${rule}\nDecisione: ${movimento.decisione || 'ambigua'}\n${evidence}`);
  };

  // Incassa assegno. Il backend collega l'evidenza bancaria esistente: questa
  // pagina non deve creare una seconda riga di Prima Nota.
  const handleIncassaAssegno = async assegno => {
    setProcessing(assegno.id);
    try {
      await api.post(`/api/assegni/${assegno.id}/incassa`);

      toast.success('Assegno incassato');
      loadAllData();
    } catch (e) {
      toast.error('Incasso assegno non riuscito', {
        description: e.response?.data?.detail || e.message,
      });
    } finally {
      setProcessing(null);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 'clamp(12px, 3vw, 20px)' }}>
        {/* La testata la mette l'hub, sopra: qui solo l'attesa. */}
        <div style={{ padding: 40, textAlign: 'center', background: 'white', borderRadius: 8, border: '1px solid #e6e3d9' }}>
          <div style={{ color: COLORS.textMuted }}>Caricamento della riconciliazione…</div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ position: 'relative', padding: '16px' }}>
      {dialogoScelta}
      {loadError && (
        <div
          style={{
            marginBottom: 16,
            padding: '12px 16px',
            background: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: 8,
            color: '#991b1b',
            fontSize: 13,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <span><TriangleAlert size={14} aria-hidden="true" style={ICO} /> {loadError}</span>
          <button
            onClick={() => loadAllData(currentLimit)}
            style={{
              padding: '6px 12px',
              background: '#991b1b',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            Riprova
          </button>
        </div>
      )}
      {ambitoNoleggio && (
        <div
          style={{
            marginBottom: 16,
            padding: '10px 14px',
            background: '#eef3ef',
            border: '1px solid #c2ddd0',
            borderRadius: 8,
            color: '#4c4a44',
            fontSize: 13,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
          }}
          data-testid="rental-reconciliation-scope"
        >
          <span>
            <strong>Filtro attivo:</strong> movimenti dei fornitori di noleggio. Il collegamento
            al veicolo resta nella pagina Noleggio.
          </span>
          <button
            type="button"
            onClick={() => navigate('/riconciliazione/banca')}
            style={{
              padding: '6px 10px',
              background: '#fff',
              color: '#4c4a44',
              border: '1px solid #a9cbbb',
              borderRadius: 6,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              fontWeight: 600,
            }}
          >
            Mostra tutti
          </button>
        </div>
      )}
      {/* Action Bar - senza cornice blu */}
      <div
        style={{
          marginBottom: 16,
          display: 'flex',
          justifyContent: 'flex-end',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 8,
        }}
      >
        <button
          type="button"
          onClick={handleAnalizzaAnomalie}
          disabled={processing === 'analizza-anomalie'}
          style={{
            padding: '8px 14px', minHeight: 40, background: '#fff', color: '#141413',
            border: '1px solid #c15f3c', borderRadius: 6, cursor: 'pointer',
            fontWeight: 700, whiteSpace: 'nowrap',
          }}
        >
          {processing === 'analizza-anomalie' ? 'Analisi...' : 'Analizza anomalie'}
        </button>
        <button
          onClick={() => loadAllData(currentLimit)}
          disabled={processing}
          style={{
            padding: '8px 14px',
            minHeight: 40,
            flex: isMobile ? '1 1 auto' : '0 1 auto',
            background: 'white',
            color: '#141413',
            border: '1px solid #e6e3d9',
            borderRadius: 6,
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: 13,
            whiteSpace: 'nowrap',
          }}
        >
          <RefreshCw size={14} aria-hidden="true" style={ICO} /> Aggiorna
        </button>

        {/* Bottone Filtri */}
        <button
          onClick={() => setShowFilters(!showFilters)}
          style={{
            padding: '8px 14px',
            minHeight: 40,
            flex: isMobile ? '1 1 auto' : '0 1 auto',
            background: showFilters ? '#c15f3c' : 'white',
            color: showFilters ? 'white' : '#c15f3c',
            border: `1px solid ${showFilters ? '#c15f3c' : '#e6e3d9'}`,
            borderRadius: 6,
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: 13,
            whiteSpace: 'nowrap',
          }}
        >
          <Search size={14} aria-hidden="true" style={ICO} /> Filtri {showFilters ? <ChevronUp size={14} aria-hidden="true" style={ICO} /> : <ChevronDown size={14} aria-hidden="true" style={ICO} />}
        </button>
      </div>

      {anomalyReport && (
        <section
          aria-label="Risultato analisi anomalie bancarie"
          data-testid="bank-anomaly-report"
          style={{
            marginBottom: 16,
            padding: 14,
            background: '#fff7ed',
            border: '1px solid #fed7aa',
            borderRadius: 8,
            color: '#7c2d12',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <div>
              <strong>
                {anomalyReport.totale_anomalie || 0} movimenti da verificare su{' '}
                {anomalyReport.righe_esaminate || 0} esaminati
              </strong>
              <div style={{ marginTop: 3, fontSize: 12 }}>
                Analisi in sola lettura: nessun movimento e nessun collegamento sono stati modificati.
              </div>
            </div>
            <button
              type="button"
              onClick={() => setAnomalyReport(null)}
              aria-label="Chiudi risultato analisi"
              style={{ border: 0, background: 'transparent', color: '#7c2d12', cursor: 'pointer' }}
            >
              Chiudi
            </button>
          </div>
          {(anomalyReport.anomalie || []).length > 0 ? (
            <div style={{ display: 'grid', gap: 8, marginTop: 12 }}>
              {(anomalyReport.anomalie || []).slice(0, 20).map(item => (
                <div
                  key={item.movimento_id}
                  style={{ padding: 10, background: '#fff', border: '1px solid #ffedd5', borderRadius: 6 }}
                >
                  <div style={{ fontWeight: 700, fontSize: 12 }}>
                    {formatDateIT(item.data) || 'Data non disponibile'} · {item.movimento_id}
                  </div>
                  {(item.motivi || []).map((motivo, index) => (
                    <div key={`${motivo.codice}-${index}`} style={{ marginTop: 4, fontSize: 12 }}>
                      {descriviAnomaliaBanca(motivo)}
                    </div>
                  ))}
                </div>
              ))}
              {(anomalyReport.anomalie || []).length > 20 && (
                <div style={{ fontSize: 12 }}>
                  Sono mostrate le prime 20 anomalie. Cerca il movimento nell'indice operazioni.
                </div>
              )}
              <button
                type="button"
                onClick={() => navigate('/riconciliazione/movimenti-banca')}
                style={{
                  justifySelf: 'start', padding: '7px 11px', borderRadius: 6,
                  background: '#c15f3c', color: '#fff', border: 0, cursor: 'pointer', fontWeight: 700,
                }}
              >
                Apri indice operazioni
              </button>
            </div>
          ) : (
            <div style={{ marginTop: 10, fontSize: 12 }}>Nessuna anomalia rilevata nel campione esaminato.</div>
          )}
        </section>
      )}

      {/* Pannello Filtri Avanzati */}
      {showFilters && (
        <div
          style={{
            background: 'white',
            borderRadius: 8,
            padding: 16,
            marginBottom: 16,
            border: '1px solid #e6e3d9',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 12,
          }}
        >
          <div>
            <label style={{ display: 'block', fontSize: 12, color: '#7a776e', marginBottom: 4 }}>
              <Calendar size={14} aria-hidden="true" style={ICO} /> Data Da
            </label>
            <input
              type="date"
              value={filters.dataFrom}
              onChange={e => setFilters({ ...filters, dataFrom: e.target.value })}
              style={{
                width: '100%',
                padding: 8,
                border: '1px solid #e6e3d9',
                borderRadius: 6,
                fontSize: 13,
              }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: '#7a776e', marginBottom: 4 }}>
              <Calendar size={14} aria-hidden="true" style={ICO} /> Data A
            </label>
            <input
              type="date"
              value={filters.dataTo}
              onChange={e => setFilters({ ...filters, dataTo: e.target.value })}
              style={{
                width: '100%',
                padding: 8,
                border: '1px solid #e6e3d9',
                borderRadius: 6,
                fontSize: 13,
              }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: '#7a776e', marginBottom: 4 }}>
              Importo Min (€)
            </label>
            <input
              type="number"
              placeholder="0"
              value={filters.importoMin}
              onChange={e => setFilters({ ...filters, importoMin: e.target.value })}
              style={{
                width: '100%',
                padding: 8,
                border: '1px solid #e6e3d9',
                borderRadius: 6,
                fontSize: 13,
              }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: '#7a776e', marginBottom: 4 }}>
              Importo Max (€)
            </label>
            <input
              type="number"
              placeholder="999999"
              value={filters.importoMax}
              onChange={e => setFilters({ ...filters, importoMax: e.target.value })}
              style={{
                width: '100%',
                padding: 8,
                border: '1px solid #e6e3d9',
                borderRadius: 6,
                fontSize: 13,
              }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: '#7a776e', marginBottom: 4 }}>
              <Search size={14} aria-hidden="true" style={ICO} /> Cerca
            </label>
            <input
              type="text"
              placeholder="Descrizione, tipo..."
              value={filters.search}
              onChange={e => setFilters({ ...filters, search: e.target.value })}
              style={{
                width: '100%',
                padding: 8,
                border: '1px solid #e6e3d9',
                borderRadius: 6,
                fontSize: 13,
              }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button
              onClick={() =>
                setFilters({ dataFrom: '', dataTo: '', importoMin: '', importoMax: '', search: '' })
              }
              style={{
                padding: '8px 16px',
                minHeight: 40,
                background: '#f8e5e2',
                color: '#dc2626',
                border: 'none',
                borderRadius: 6,
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: 13,
              }}
            >
              <X size={14} aria-hidden="true" style={ICO} /> Reset
            </button>
          </div>
        </div>
      )}

      {/* Le schede stanno una volta sola, nella barra dell'hub sopra questa
          pagina (Riepilogo, Banca, Stipendi, Documenti, …). La seconda barra
          che stava qui portava agli stessi indirizzi: era un doppione. I suoi
          conteggi sono nel Riepilogo. */}
      {/* Tab Content */}
      <div
        style={{
          background: 'white',
          borderRadius: 8,
          border: '1px solid #e6e3d9',
          overflow: 'hidden',
        }}
      >
        {activeTab === 'dashboard' && (
          <DashboardTab
            stats={stats}
            reconciliationStats={reconciliationStats}
            loading={loading}
            onApri={tabId => handleTabChange(tabId)}
          />
        )}
        {activeTab === 'banca' && movimentoRichiestoId && (
          <PannelloMovimentoRichiesto
            id={movimentoRichiestoId}
            richiesta={movimentoRichiesto}
            onChiudi={() => navigate('/riconciliazione/banca')}
          />
        )}
        {activeTab === 'banca' && (
          <MovimentiTab
            movimenti={movimentiBancaFiltrati}
            onConferma={handleConferma}
            onIgnora={handleIgnora}
            onVediProva={handleVediProva}
            processing={processing}
            title={ambitoNoleggio ? 'Movimenti Bancari · Noleggio' : 'Movimenti Bancari'}
            totalRows={ambitoNoleggio ? movimentiBancaFiltrati.length : stats.banca}
            emptyText="Tutti i movimenti sono stati riconciliati"
            tipo="banca"
            vistaLista
          />
        )}
        {activeTab === 'assegni' && (
          <MovimentiTab
            movimenti={assegniFiltrati}
            onConferma={handleIncassaAssegno}
            onIgnora={handleIgnora}
            processing={processing}
            title="Prelievi Assegno"
            emptyText="Nessun assegno da riconciliare"
            tipo="assegno"
            showFattura
          />
        )}
        {activeTab === 'f24' && (
          <F24Tab
            f24={f24Pendenti}
            processing={processing}
            onLoadF24={loadF24OnDemand}
            f24Loading={f24Loading}
            onRefresh={loadAllData}
            anno={anno}
          />
        )}
        {activeTab === 'stipendi' && (
          <MovimentiTab
            movimenti={stipendiFiltrati}
            onConferma={handleConferma}
            onIgnora={handleIgnora}
            processing={processing}
            title="Stipendi"
            emptyText="Nessuno stipendio da riconciliare"
            tipo="stipendio"
          />
        )}
        {activeTab === 'documenti' && (
          <DocumentiTab
            documenti={documentiNonAssociati}
            stats={documentiStats}
            onRefresh={loadAllData}
            processing={processing}
          />
        )}
        {activeTab === 'paypal' && (
          <Suspense
            fallback={
              <div style={{ padding: 40, textAlign: 'center', color: '#7a776e' }}>
                <div
                  style={{
                    width: 36,
                    height: 36,
                    border: '3px solid #e6e3d9',
                    borderTop: '3px solid #c15f3c',
                    borderRadius: '50%',
                    animation: 'spin 1s linear infinite',
                    margin: '0 auto 12px',
                  }}
                />
                Caricamento PayPal...
              </div>
            }
          >
            <div style={{ padding: 20 }}>
              <RiconciliazionePaypalLazy />
            </div>
          </Suspense>
        )}
      </div>

      {/* Bottone Carica Altri */}
      {hasMore && activeTab === 'banca' && (
        <div style={{ textAlign: 'center', marginTop: 20 }}>
          <button
            onClick={loadMore}
            disabled={loadingMore}
            style={{
              padding: '12px 28px',
              minHeight: 40,
              background: loadingMore ? '#a19d92' : '#c15f3c',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              fontWeight: 600,
              fontSize: 13,
              cursor: loadingMore ? 'wait' : 'pointer',
              transition: 'all 0.2s',
            }}
          >
            {loadingMore
              ? 'Caricamento...'
              : `Carica altri (${movimentiBanca.length} di ${stats.banca || movimentiBanca.length})`}
          </button>
        </div>
      )}
    </div>
  );
}

// ============================================
// TAB COMPONENTS
// ============================================

/* Il Riepilogo non e' piu' un menu travestito da pagina («Seleziona una
   sezione dal menu»): come il cruscotto dell'artefatto elenca le cose da
   sistemare, ognuna col suo numero e un «Apri» che porta alle righe. I numeri
   sono quelli che la pagina gia' carica: qui non si calcola niente. */
function DashboardTab({ stats, reconciliationStats, loading, onApri }) {
  const numero = v => (loading ? '…' : Number(v || 0).toLocaleString('it-IT'));
  const voci = [
    {
      id: 'banca',
      titolo: 'Movimenti della banca da abbinare',
      nota: 'Righe dell\'estratto conto ancora senza il documento che le giustifica.',
      valore: stats.totale_righe,
    },
    {
      id: 'stipendi',
      titolo: 'Stipendi da abbinare',
      nota: 'Bonifici di stipendio in attesa del cedolino o della conferma.',
      valore: stats.stipendi,
    },
    {
      id: 'documenti',
      titolo: 'Documenti senza movimento',
      nota: 'Ricevute e documenti di pagamento che non hanno ancora trovato la riga di banca.',
      valore: stats.documenti,
    },
    {
      id: 'f24',
      titolo: 'F24 da abbinare',
      nota: 'Si contano quando si apre la sezione: la ricerca è lunga.',
      valore: null,
    },
  ];
  return (
    <div data-testid="riepilogo-riconciliazione">
      <div
        style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8,
          padding: '14px 18px', borderBottom: `1px solid ${COLORS.border}`,
        }}
      >
        <strong style={{ fontSize: 14, color: COLORS.text }}>Da sistemare</strong>
        <span style={{ fontSize: 12.5, color: COLORS.textMuted }}>
          Collegamenti già registrati: <b style={{ color: COLORS.success }}>{numero(reconciliationStats.matched)}</b>
        </span>
      </div>
      {voci.map(v => (
        <div
          key={v.id}
          style={{
            display: 'flex', alignItems: 'center', gap: 12, padding: '14px 18px',
            borderBottom: `1px solid ${COLORS.border}`,
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 14, color: COLORS.text }}>{v.titolo}</div>
            <div style={{ fontSize: 12.5, color: COLORS.textMuted, marginTop: 2 }}>{v.nota}</div>
          </div>
          {v.valore !== null && (
            <span style={{ fontWeight: 800, fontSize: 15, fontVariantNumeric: 'tabular-nums', color: COLORS.text }}>
              {numero(v.valore)}
            </span>
          )}
          <button
            type="button"
            onClick={() => onApri(v.id)}
            data-testid={`riepilogo-apri-${v.id}`}
            style={{
              minHeight: 44, padding: '8px 12px', border: 'none', background: 'transparent',
              color: COLORS.primary, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap',
            }}
          >
            Apri →
          </button>
        </div>
      ))}
    </div>
  );
}

function MovimentiTab({
  movimenti,
  onConferma,
  onIgnora,
  onVediProva,
  processing,
  title,
  emptyText,
  showFattura,
  totalRows,
  // vistaLista: solo la tab Banca usa ListaAdattiva (tabella su desktop,
  // card compatte su mobile); le altre tab restano su MovimentoCard.
  vistaLista = false,
}) {
  const isMobile = useIsMobile();
  const [limite, setLimite] = useState(200);

  if (movimenti.length === 0) {
    return (
      <div style={{ padding: 60, textAlign: 'center', color: '#a19d92' }}>
        <div style={{ fontSize: 48, marginBottom: 12, opacity: 0.5 }}><Check size={40} aria-hidden="true" style={ICO} /></div>
        <div>{emptyText}</div>
      </div>
    );
  }

  // Azioni per riga: stessi bottoni (e stili) di MovimentoCard
  const renderAzioni = m => {
    const inCorso = processing === m.movimento_id || processing === m.id;
    const analisiInCorso = Boolean(m.analisi_in_corso);
    const analisiNonDisponibile = Boolean(m.analisi_non_disponibile);
    const automatic = m.decisione === 'automatica';
    const primaryLabel = automatic
      ? 'Vedi prova'
      : m.decisione === 'proposta'
        ? 'Scegli candidato'
        : m.decisione === 'ambigua'
          ? 'Risolvi differenza'
          : 'Conferma';
    return (
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
        <button
          onClick={() => automatic && onVediProva ? onVediProva(m) : onConferma(m)}
          disabled={inCorso || analisiInCorso || analisiNonDisponibile}
          style={{
            padding: '8px 16px',
            minHeight: 40,
            background: '#c15f3c',
            color: 'white',
            border: 'none',
            borderRadius: 6,
            fontWeight: 600,
            cursor: 'pointer',
            fontSize: 13,
          }}
        >
          {inCorso ? 'Attendi...' : analisiInCorso ? 'Analisi…' : analisiNonDisponibile ? 'Analisi non disponibile' : primaryLabel}
        </button>
        <button
          onClick={() => onIgnora(m)}
          disabled={inCorso}
          style={{
            padding: '8px 12px',
            minHeight: 40,
            minWidth: 40,
            background: 'white',
            color: '#7a776e',
            border: '1px solid #e6e3d9',
            borderRadius: 6,
            cursor: 'pointer',
            fontSize: 13,
          }}
        >
          Escludi dalla coda
        </button>
      </div>
    );
  };

  const nominativoDi = m =>
    m.ragione_sociale ||
    m.fornitore ||
    m.dipendente?.nome_completo ||
    m.dipendente ||
    m.nome_estratto;

  return (
    <div>
      <div style={{ padding: 16, background: '#f6f4ee', borderBottom: '1px solid #e6e3d9' }}>
        <h3 style={{ margin: 0, fontSize: 16, color: '#141413' }}>
          {title} ({movimenti.length}{Number(totalRows) > movimenti.length ? ` di ${totalRows}` : ''})
        </h3>
      </div>
      {vistaLista ? (
        <div style={{ padding: isMobile ? '0 10px 10px' : 0 }}>
          {/* pageSize alto (200): la paginazione vera resta quella lato server
              ("Carica altri" sotto il tab, currentLimit/hasMore) — così la barra
              interna di ListaAdattiva non si sovrappone finché non superiamo
              200 righe caricate. */}
          <ListaAdattiva
            testId="movimenti-banca-lista"
            dati={movimenti}
            pageSize={200}
            chiave={(m, i) => m.movimento_id || m.id || i}
            colonne={[
              {
                key: 'data',
                label: 'Data',
                ruoloCard: 'dettaglio',
                // Su mobile solo giorno/mese (l'anno è nel selettore globale)
                render: m => {
                  const d = m.data || m.data_emissione;
                  if (!d) return 'Data N/D';
                  return isMobile ? formatDateGGMM(d) : formatDateIT(d);
                },
                tdStyle: { whiteSpace: 'nowrap', fontSize: 13 },
              },
              {
                key: 'nominativo',
                label: 'Nominativo',
                ruoloCard: 'sottotitolo',
                render: m => nominativoDi(m) || '-',
                tdStyle: { fontWeight: 700, color: '#2c2b28', fontSize: 13 },
              },
              {
                key: 'descrizione',
                label: 'Descrizione',
                ruoloCard: 'titolo',
                render: m => {
                  const desc =
                    m.descrizione?.substring(0, 100) ||
                    m.descrizione_originale?.substring(0, 100) ||
                    '-';
                  if (isMobile) return desc.substring(0, 60);
                  const numeroFattura = m.numero_fattura || m.fattura_collegata;
                  return (
                    <div>
                      <div style={{ fontSize: 12, color: '#a19d92', fontWeight: 400 }}>{desc}</div>
                      {m.periodo && (
                        <div style={{ fontSize: 11, color: '#7a776e', marginTop: 2 }}>
                          Periodo: {m.periodo || m.mese_riferimento}
                        </div>
                      )}
                      {numeroFattura && (
                        <div style={{ fontSize: 11, color: '#5b7a6b', marginTop: 2 }}>
                          <FileText size={14} aria-hidden="true" style={ICO} /> Fattura: {numeroFattura}
                        </div>
                      )}
                      <LinksContropartita m={m} />
                      {(m.suggerimenti || []).length > 1 && (
                        <div style={{ marginTop: 4, fontSize: 11, color: '#4c4a44' }}>
                          {m.suggerimenti.map(item => (
                            <div key={item.id}>
                              {item.numero || item.id}: fattura {euroOppure(item.importo)}, quota{' '}
                              {euroOppure(Number.isInteger(item.quota_cents) ? item.quota_cents / 100 : item.importo)}, residuo dopo{' '}
                              {formatEuro(Number.isInteger(item.residuo_successivo_cents) ? item.residuo_successivo_cents / 100 : 0)}
                            </div>
                          ))}
                        </div>
                      )}
                      {m.beneficiario && (
                        <div style={{ fontSize: 11, color: '#d97706', marginTop: 2 }}>
                          <User size={14} aria-hidden="true" style={ICO} /> Beneficiario: {m.beneficiario}
                        </div>
                      )}
                    </div>
                  );
                },
              },
              {
                key: 'stato',
                label: 'Stato',
                ruoloCard: 'dettaglio',
                render: m => {
                  const sugg = m.suggerimenti?.[0];
                  const hasMatch = m.associazione_automatica && sugg;
                  const datiIncompleti = m.dati_incompleti || m.stato === 'vuoto';
                  if (m.decisione) {
                    const labels = {
                      automatica: ['Registrata automaticamente', '#e2f0e7', '#166534'],
                      proposta: ['Proposta da verificare', '#f7ebe4', '#a94f30'],
                      ambigua: ['Da decidere', '#f7eeda', '#92400e'],
                    };
                    const [label, background, color] = labels[m.decisione] || labels.ambigua;
                    return (
                      <span style={{ padding: '2px 8px', background, color, borderRadius: 6, fontSize: 11, fontWeight: 700 }}>
                        {label}
                      </span>
                    );
                  }
                  if (hasMatch) {
                    return (
                      <span
                        style={{
                          padding: '2px 8px',
                          background: '#e2f0e7',
                          color: '#16a34a',
                          borderRadius: 6,
                          fontSize: 11,
                          fontWeight: 600,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        <Check size={14} aria-hidden="true" style={ICO} /> Match:{' '}
                        {sugg.fornitore || sugg.nome || sugg.dipendente || 'Match'}{' '}
                        {euroOppure(sugg.importo)}
                      </span>
                    );
                  }
                  if (datiIncompleti) {
                    return (
                      <span
                        style={{
                          padding: '2px 8px',
                          background: '#f7eeda',
                          color: '#92400e',
                          borderRadius: 6,
                          fontSize: 11,
                          fontWeight: 600,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        <TriangleAlert size={14} aria-hidden="true" style={ICO} /> Dati incompleti
                      </span>
                    );
                  }
                  return (
                    <span
                      style={{
                        padding: '2px 8px',
                        background: '#f2f0e9',
                        color: '#7a776e',
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 600,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Da riconciliare
                    </span>
                  );
                },
              },
              {
                key: 'importo',
                label: 'Importo',
                align: 'right',
                mono: true,
                ruoloCard: 'importo',
                render: m => (
                  <span
                    style={{
                      color: m.importo < 0 ? '#dc2626' : '#16a34a',
                      fontWeight: 700,
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {/* Su mobile il segno rende esplicito entrata/uscita;
                        su desktop resta il valore assoluto come prima */}
                    {isMobile
                      ? `${m.importo < 0 ? '-' : '+'}${eurAbs(m.importo)}`
                      : m.importo
                        ? formatEuro(Math.abs(m.importo))
                        : '€ 0,00'}
                  </span>
                ),
              },
              {
                key: 'movimento_id',
                label: 'ID',
                mono: true,
                ruoloCard: 'omesso',
                render: m => m.movimento_id || m.id || '-',
                tdStyle: { fontSize: 11, color: '#a19d92' },
              },
              {
                key: 'azioni',
                label: 'Azioni',
                align: 'center',
                ruoloCard: 'azioni',
                render: renderAzioni,
              },
            ]}
          />
        </div>
      ) : (
        <div>
          {movimenti.slice(0, limite).map((m, idx) => (
            <MovimentoCard
              key={m.movimento_id || m.id || idx}
              movimento={m}
              onConferma={onConferma}
              onIgnora={onIgnora}
              onVediProva={onVediProva}
              processing={processing === m.movimento_id || processing === m.id}
              showFattura={showFattura}
            />
          ))}
          {movimenti.length > limite && (
            <button type="button" onClick={() => setLimite(x => x + 200)} style={{ minHeight: 44, padding: '8px 16px', margin: '10px 0', borderRadius: 6, border: '1px solid #e6e3d9', background: '#fff', color: '#141413', fontWeight: 600, cursor: 'pointer' }}>
              Mostra altre ({movimenti.length - limite})
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function MovimentoCard({ movimento, onConferma, onIgnora, onVediProva, processing, showFattura }) {
  const suggerimento = movimento.suggerimenti?.[0];
  const hasMatch = movimento.associazione_automatica && suggerimento;
  const automatic = movimento.decisione === 'automatica';
  const analisiInCorso = Boolean(movimento.analisi_in_corso);
  const analisiNonDisponibile = Boolean(movimento.analisi_non_disponibile);
  const primaryLabel = automatic
    ? 'Vedi prova'
    : movimento.decisione === 'proposta'
      ? 'Scegli candidato'
      : movimento.decisione === 'ambigua'
        ? 'Risolvi differenza'
        : 'Conferma';

  // Estrai info extra dal movimento
  const ragioneSociale =
    movimento.ragione_sociale ||
    movimento.fornitore ||
    movimento.dipendente?.nome_completo ||
    movimento.dipendente ||
    movimento.nome_estratto;
  const numeroFattura = movimento.numero_fattura || movimento.fattura_collegata;
  const datiIncompleti = movimento.dati_incompleti || movimento.stato === 'vuoto';

  return (
    <div
      style={{
        padding: 16,
        borderBottom: '1px solid #f2f0e9',
        opacity: processing ? 0.5 : 1,
        background: hasMatch ? '#f0fdf4' : datiIncompleti ? '#f7eeda' : 'white',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <div
          style={{
            width: 44,
            height: 44,
            borderRadius: 10,
            background: hasMatch
              ? '#e2f0e7'
              : datiIncompleti
                ? '#f7eeda'
                : ragioneSociale
                  ? '#eef3ef'
                  : '#f2f0e9',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 20,
          }}
        >
          {hasMatch ? <Check size={20} aria-hidden="true" /> : datiIncompleti ? <TriangleAlert size={20} aria-hidden="true" /> : ragioneSociale ? <User size={20} aria-hidden="true" /> : <FileText size={20} aria-hidden="true" />}
        </div>

        <div style={{ flex: 1 }}>
          {/* NOME DIPENDENTE/FORNITORE - In evidenza */}
          {ragioneSociale && (
            <div
              style={{
                fontWeight: 700,
                fontSize: 15,
                color: '#2c2b28',
                marginBottom: 4,
              }}
            >
              {ragioneSociale}
            </div>
          )}

          <div
            style={{
              fontWeight: 500,
              fontSize: 13,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              color: '#7a776e',
            }}
          >
            <span>
              {movimento.data || movimento.data_emissione
                ? formatDateIT(movimento.data || movimento.data_emissione)
                : 'Data N/D'}
            </span>
            <span>•</span>
            <span
              style={{
                color: movimento.importo < 0 ? '#dc2626' : '#16a34a',
                fontWeight: 700,
                fontSize: 15,
                fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
              }}
            >
              {movimento.importo ? formatEuro(Math.abs(movimento.importo)) : '€ 0,00'}
            </span>
            {movimento.periodo && (
              <>
                <span>•</span>
                <span style={{ fontSize: 11, color: '#7a776e' }}>
                  Periodo: {movimento.periodo || movimento.mese_riferimento}
                </span>
              </>
            )}
            {datiIncompleti && (
              <span
                style={{
                  fontSize: 10,
                  padding: '2px 6px',
                  background: '#f7eeda',
                  color: '#92400e',
                  borderRadius: 4,
                  fontWeight: 500,
                }}
              >
                DATI INCOMPLETI
              </span>
            )}
          </div>

          {/* Descrizione */}
          <div style={{ fontSize: 12, color: '#a19d92', marginTop: 2 }}>
            {movimento.descrizione?.substring(0, 100) ||
              movimento.descrizione_originale?.substring(0, 100) ||
              '-'}
          </div>

          {/* Numero Fattura */}
          {numeroFattura && (
            <div
              style={{
                marginTop: 2,
                fontSize: 11,
                color: '#5b7a6b',
              }}
            >
              <FileText size={14} aria-hidden="true" style={ICO} /> Fattura: {numeroFattura}
            </div>
          )}
          <LinksContropartita m={movimento} />

          {/* Info assegno se presente */}
          {movimento.numero_assegno && (
            <div
              style={{
                marginTop: 4,
                fontSize: 11,
                color: '#d97706',
                display: 'flex',
                flexWrap: 'wrap',
                gap: 8,
                alignItems: 'center',
              }}
            >
              <span><FileText size={14} aria-hidden="true" style={ICO} /> Assegno N. {movimento.numero_assegno}</span>
              <span>• Stato: {movimento.stato || 'N/D'}</span>
              {movimento.beneficiario && (
                <span style={{ color: '#5b7a6b', fontWeight: 600 }}>
                  • <User size={14} aria-hidden="true" style={ICO} /> {movimento.beneficiario}
                </span>
              )}
              {movimento.fornitore && !movimento.beneficiario && (
                <span style={{ color: '#5b7a6b', fontWeight: 600 }}>
                  • <User size={14} aria-hidden="true" style={ICO} /> {movimento.fornitore}
                </span>
              )}
            </div>
          )}

          {/* Confronto importi per assegni con fattura */}
          {movimento.numero_assegno && movimento.numero_fattura && (
            <div
              style={{
                marginTop: 6,
                padding: '6px 10px',
                background: '#f7eeda',
                borderRadius: 6,
                fontSize: 11,
                display: 'inline-flex',
                flexWrap: 'wrap',
                gap: 12,
                alignItems: 'center',
              }}
            >
              <span>
                <b>Assegno:</b> {eurAbs(movimento.importo)}
              </span>
              {movimento.importo_fattura !== undefined && (
                <>
                  <span>•</span>
                  <span>
                    <FileText size={14} aria-hidden="true" style={ICO} /> <b>Fattura:</b> {eurAbs(movimento.importo_fattura)}
                  </span>
                  {Math.abs((movimento.importo || 0) - (movimento.importo_fattura || 0)) > 0.01 && (
                    <>
                      <span>•</span>
                      <span style={{ color: '#dc2626', fontWeight: 600 }}>
                        <TriangleAlert size={14} aria-hidden="true" style={ICO} /> Diff:{' '}
                        {formatEuro(
                          Math.abs((movimento.importo || 0) - (movimento.importo_fattura || 0))
                        )}
                      </span>
                    </>
                  )}
                </>
              )}
              {/* Info pagamento rateale */}
              {movimento.info_rate && movimento?.info_rate?.numero_rate > 1 && (
                <div
                  style={{
                    width: '100%',
                    marginTop: 4,
                    padding: '4px 8px',
                    background: '#f7ebe4',
                    borderRadius: 4,
                    color: '#4c4a44',
                  }}
                >
                  <ChartColumn size={14} aria-hidden="true" style={ICO} /> <b>Pagamento in {movimento?.info_rate?.numero_rate} rate</b>: Totale rate{' '}
                  {formatEuro(movimento.info_rate.totale_rate)}
                  {movimento.importo_fattura > 0 && (
                    <span> su fattura di {formatEuro(movimento.importo_fattura)}</span>
                  )}
                </div>
              )}
              {/* Nota TD24 */}
              {movimento.nota_td24 && (
                <div
                  style={{
                    width: '100%',
                    marginTop: 4,
                    padding: '4px 8px',
                    background: '#f7ebe4',
                    borderRadius: 4,
                    color: '#4c4a44',
                  }}
                >
                  <Info size={14} aria-hidden="true" style={ICO} /> {movimento.nota_td24}
                </div>
              )}
            </div>
          )}

          {/* Info beneficiario per assegni senza numero */}
          {!movimento.numero_assegno && movimento.beneficiario && (
            <div
              style={{
                marginTop: 2,
                fontSize: 11,
                color: '#d97706',
              }}
            >
              <User size={14} aria-hidden="true" style={ICO} /> Beneficiario: {movimento.beneficiario}
            </div>
          )}

          {movimento.decisione && (
            <div style={{ marginTop: 8, fontSize: 12, fontWeight: 700, color: '#141413' }}>
              {movimento.decisione === 'automatica'
                ? 'Registrata automaticamente'
                : movimento.decisione === 'proposta'
                  ? 'Proposta da verificare'
                  : 'Da decidere'}
              {movimento.motivo_blocco ? ` - ${movimento.motivo_blocco}` : ''}
            </div>
          )}

          {(movimento.suggerimenti || []).length > 1 && (
            <div style={{ marginTop: 8, padding: 8, background: '#f6f4ee', borderRadius: 6, fontSize: 11 }}>
              {movimento.suggerimenti.map(item => (
                <div key={item.id} style={{ marginBottom: 3 }}>
                  <b>{item.numero || item.id}</b>: fattura {euroOppure(item.importo)}; quota{' '}
                  {euroOppure(Number.isInteger(item.quota_cents) ? item.quota_cents / 100 : item.importo)}; residuo dopo{' '}
                  {formatEuro(Number.isInteger(item.residuo_successivo_cents) ? item.residuo_successivo_cents / 100 : 0)}
                </div>
              ))}
            </div>
          )}

          {hasMatch && suggerimento && (
            <div
              style={{
                marginTop: 8,
                padding: '6px 10px',
                background: '#e2f0e7',
                borderRadius: 6,
                fontSize: 12,
                display: 'inline-block',
              }}
            >
              <Link2 size={14} aria-hidden="true" style={ICO} /> {suggerimento.fornitore || suggerimento.nome || suggerimento.dipendente || 'Match'}
              : {euroOppure(suggerimento.importo)}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button
            onClick={() => automatic && onVediProva ? onVediProva(movimento) : onConferma(movimento)}
            disabled={processing || analisiInCorso || analisiNonDisponibile}
            style={{
              padding: '8px 16px',
              minHeight: 40,
              background: '#c15f3c',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              fontWeight: 600,
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            {processing ? 'Attendi...' : analisiInCorso ? 'Analisi…' : analisiNonDisponibile ? 'Analisi non disponibile' : primaryLabel}
          </button>
          <button
            onClick={() => onIgnora(movimento)}
            disabled={processing}
            style={{
              padding: '8px 12px',
              minHeight: 40,
              minWidth: 40,
              background: 'white',
              color: '#7a776e',
              border: '1px solid #e6e3d9',
              borderRadius: 6,
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            Escludi dalla coda
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Tabella §20 della specifica F24 (memoria/SPECIFICA_F24_CEDOLINI_...) ──
// Periodo di competenza, scadenza naturale, data pagamento, giorni di
// ritardo, stato, tipo versamento, causale INPS, documento collegato,
// possibile duplicazione e motivazione automatica. Il "pagato in ritardo"
// è evidenziato con scadenza naturale e data effettiva, come da specifica.
const STILI_STATO_F24 = {
  pagato_nei_termini: { label: 'Pagato nei termini', bg: '#e2f0e7', color: '#166534' },
  pagato_in_ritardo: { label: 'PAGATO IN RITARDO', bg: '#f8e5e2', color: '#991b1b' },
  non_pagato: { label: 'Non pagato', bg: '#ffedd5', color: '#9a3412' },
  in_scadenza: { label: 'In scadenza', bg: '#f7ebe4', color: '#4c4a44' },
  periodo_ignoto: { label: 'Periodo ignoto', bg: '#f2f0e9', color: '#7a776e' },
  // F24 del commercialista pagato con un ravvedimento (f24_ravvedimento.py).
  ravveduto: { label: 'Ravveduto', bg: '#f7ebe4', color: '#8a6f47' },
};

const etichettaRavvedimento = {
  display: 'inline-block', padding: '2px 8px', borderRadius: 6, fontSize: 11, fontWeight: 700,
  background: '#f7ebe4', color: '#8a6f47', whiteSpace: 'nowrap',
};

const bottoneFile = {
  minHeight: 32, padding: '4px 10px', borderRadius: 6, border: '1px solid #c15f3c',
  background: '#fff', color: '#c15f3c', fontSize: 12, fontWeight: 700, cursor: 'pointer',
};

const STILI_DUP_F24 = {
  da_verificare: { label: 'Da verificare', bg: '#f8e5e2', color: '#991b1b' },
  collegato_no_duplicato: { label: 'Collegato (no doppio)', bg: '#f7ebe4', color: '#4c4a44' },
  no: { label: 'No', bg: '#f2f0e9', color: '#7a776e' },
};

export function TabellaAnalisiF24({ anno }) {
  const [righe, setRighe] = useState(null);
  const [loading, setLoading] = useState(false);
  const [errore, setErrore] = useState(null);
  const [soloAnno, setSoloAnno] = useState(true);
  const [limite, setLimite] = useState(200);
  const isMobile = useIsMobile();
  const [ricercaTributo, setRicercaTributo] = useState('');
  const [pdfViewer, setPdfViewer] = useState(null); // {title, fetchUrl}

  const carica = async filtraAnno => {
    setLoading(true);
    setErrore(null);
    try {
      const qs = filtraAnno && anno ? `?anno=${anno}` : '';
      const res = await api.get(`/api/f24-analisi/tabella${qs}`);
      setRighe(res.data.righe || []);
    } catch (e) {
      setErrore(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    carica(true);
  }, [anno]);

  const righeFiltrate = (righe || []).filter(r => {
    const cerca = ricercaTributo.trim().toLowerCase();
    if (!cerca) return true;
    return `${(r.codici_tributo || []).join(' ')} ${(r.causali_inps || []).join(' ')} ${r.periodo_competenza || ''} ${r.file || ''}`
      .toLowerCase().includes(cerca);
  });

  const cellaTh = {
    padding: '8px 8px', textAlign: 'left', fontWeight: 600, fontSize: 11,
    color: '#7a776e', textTransform: 'uppercase', whiteSpace: 'nowrap',
  };
  const cella = { padding: '6px 8px', fontSize: 12, verticalAlign: 'top', ...(isMobile ? { display: 'block' } : {}) };
  const etichettaM = testo => (isMobile ? (
    <span style={{ display: 'block', fontSize: 10.5, fontWeight: 700, color: '#7a776e', textTransform: 'uppercase' }}>{testo}</span>
  ) : null);

  return (
    <div style={{ padding: 16, borderBottom: '1px solid #e6e3d9', background: 'white' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0, fontSize: 15, color: '#141413' }}>
          <ClipboardList size={14} aria-hidden="true" style={ICO} /> Analisi F24 — scadenze, ravvedimenti e duplicazioni
        </h3>
        <button
          data-testid="btn-carica-analisi-f24"
          onClick={() => carica(soloAnno)}
          disabled={loading}
          style={{
            padding: '8px 14px', minHeight: 38, background: '#c15f3c', color: 'white',
            border: 'none', borderRadius: 6, cursor: loading ? 'wait' : 'pointer',
            fontWeight: 600, fontSize: 12.5,
          }}
        >
          {loading ? 'Analizzo…' : righe ? 'Ricarica' : 'Carica analisi'}
        </button>
        <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12.5, color: '#4c4a44', cursor: 'pointer' }}>
          <input type="checkbox" checked={soloAnno} onChange={e => setSoloAnno(e.target.checked)} />
          Solo anno {anno}
        </label>
        <input
          aria-label="Cerca codice tributo F24"
          value={ricercaTributo}
          onChange={e => setRicercaTributo(e.target.value)}
          placeholder="Cerca codice tributo, periodo o file"
          style={{ minWidth: 260, minHeight: 38, padding: '7px 10px', border: '1px solid #d0ccbe', borderRadius: 6 }}
        />
        {righe && (
          <span style={{ fontSize: 12, color: '#7a776e' }}>
            {righe.length} modelli · in ritardo:{' '}
            {righe.filter(r => r.stato_pagamento === 'pagato_in_ritardo').length} · possibili
            duplicazioni: {righe.filter(r => r.possibile_duplicazione === 'da_verificare').length}
          </span>
        )}
      </div>

      {errore && (
        <div style={{ marginTop: 10, fontSize: 13, color: '#dc2626', fontWeight: 600 }}>
          <TriangleAlert size={14} aria-hidden="true" style={ICO} /> {errore}
        </div>
      )}

      {righe && righe.length === 0 && (
        <div style={{ marginTop: 12, fontSize: 13, color: '#7a776e' }}>
          Nessun F24 trovato{soloAnno ? ` per l'anno ${anno}` : ''}.
        </div>
      )}

      {righe && righe.length > 0 && (
        <div style={{ overflowX: 'auto', marginTop: 12 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: isMobile ? 0 : 980, display: isMobile ? 'block' : 'table' }}>
            <thead style={isMobile ? { display: 'none' } : undefined}>
              <tr style={{ background: '#f6f4ee', borderBottom: '2px solid #e6e3d9' }}>
                <th style={cellaTh}>Periodo competenza</th>
                <th style={cellaTh}>Scadenza naturale</th>
                <th style={cellaTh}>Pagamento effettivo</th>
                <th style={{ ...cellaTh, textAlign: 'center' }}>Giorni ritardo</th>
                <th style={cellaTh}>Stato pagamento</th>
                <th style={cellaTh}>Tipo versamento</th>
                <th style={cellaTh}>Causale INPS</th>
                <th style={cellaTh}>Documento collegato</th>
                <th style={cellaTh}>Possibile duplicazione</th>
                <th style={cellaTh}>Motivazione</th>
              </tr>
            </thead>
            <tbody style={isMobile ? { display: 'block' } : undefined}>
              {righeFiltrate.slice(0, limite).map((r, idx) => {
                const stato = STILI_STATO_F24[r.stato_pagamento] || STILI_STATO_F24.periodo_ignoto;
                const dup = STILI_DUP_F24[r.possibile_duplicazione] || STILI_DUP_F24.no;
                const inRitardo = r.stato_pagamento === 'pagato_in_ritardo';
                return (
                  <tr
                    key={r.f24_id || idx}
                    data-testid={`riga-analisi-f24-${r.f24_id || idx}`}
                    style={{
                      borderBottom: '1px solid #f2f0e9',
                      background: inRitardo ? '#fff7f7' : idx % 2 ? '#f6f4ee' : 'white',
                      ...(isMobile ? { display: 'block', border: '1px solid #e6e3d9', borderRadius: 8, marginBottom: 10, padding: 6 } : {}),
                    }}
                  >
                    <td style={{ ...cella, fontWeight: 700, whiteSpace: 'nowrap' }}>{etichettaM('Periodo competenza')}
                      {r.periodo_competenza || '—'}
                      {(r.codici_tributo || []).length > 0 && (
                        <div style={{ fontSize: 10.5, color: '#5b7a6b', fontFamily: 'monospace', marginTop: 2 }}>
                          Codici: {r.codici_tributo.join(', ')}
                        </div>
                      )}
                      {r.file && (
                        <div style={{ fontSize: 10.5, color: '#a19d92', fontWeight: 400, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {r.file}
                        </div>
                      )}
                    </td>
                    <td style={{ ...cella, whiteSpace: 'nowrap', fontFamily: 'monospace' }}>{etichettaM('Scadenza naturale')}
                      {r.scadenza_naturale ? formatDateIT(r.scadenza_naturale) : '—'}
                    </td>
                    <td style={{ ...cella, whiteSpace: 'nowrap', fontFamily: 'monospace', fontWeight: inRitardo ? 700 : 400, color: inRitardo ? '#991b1b' : '#141413' }}>{etichettaM('Pagamento effettivo')}
                      {r.data_pagamento ? formatDateIT(r.data_pagamento) : '—'}
                    </td>
                    <td style={{ ...cella, textAlign: 'center', fontWeight: 700, color: r.giorni_ritardo > 0 ? '#dc2626' : '#16a34a' }}>{etichettaM('Giorni ritardo')}
                      {r.giorni_ritardo ?? '—'}
                    </td>
                    <td style={cella}>{etichettaM('Stato pagamento')}
                      <span style={{ padding: '3px 8px', borderRadius: 6, fontSize: 11, fontWeight: 700, background: stato.bg, color: stato.color, whiteSpace: 'nowrap' }}>
                        {stato.label}
                      </span>
                    </td>
                    <td style={{ ...cella, whiteSpace: 'nowrap' }}>{etichettaM('Tipo versamento')}
                      {r.tipo_versamento === 'ordinario' ? 'Ordinario'
                        : r.tipo_versamento === 'regolarizzazione' ? 'Regolarizzazione'
                          : 'Ravvedimento'}
                      {/* Originale del commercialista e ravvedimento affiancati:
                          dall'uno si apre l'altro, nessuno dei due si cancella. */}
                      {r.etichetta === 'RAVVEDIMENTO' && (r.ravvedimento_di || []).length > 0 && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 4 }}>
                          <span style={etichettaRavvedimento} data-testid={`etichetta-ravvedimento-${r.f24_id}`}>
                            RAVVEDIMENTO
                          </span>
                          {r.ravvedimento_di.map(o => (
                            <button
                              key={o.f24_id}
                              type="button"
                              style={bottoneFile}
                              data-testid={`apri-originale-${o.f24_id}`}
                              onClick={() => setPdfViewer({ title: 'F24 originale del commercialista', fetchUrl: o.pdf_url })}
                            >
                              F24 originale
                            </button>
                          ))}
                        </div>
                      )}
                      {r.ravvedimento && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 4 }}>
                          <span style={etichettaRavvedimento} data-testid={`etichetta-ravveduto-${r.f24_id}`}>
                            Originale · pagato con ravvedimento
                          </span>
                          {r.ravvedimento.f24_ravvedimento_pdf_url && (
                            <button
                              type="button"
                              style={bottoneFile}
                              data-testid={`apri-ravvedimento-${r.f24_id}`}
                              onClick={() => setPdfViewer({ title: 'F24 di ravvedimento', fetchUrl: r.ravvedimento.f24_ravvedimento_pdf_url })}
                            >
                              F24 ravvedimento
                            </button>
                          )}
                          {r.ravvedimento.quietanza_pdf_url && (
                            <button
                              type="button"
                              style={bottoneFile}
                              data-testid={`apri-quietanza-ravvedimento-${r.f24_id}`}
                              onClick={() => setPdfViewer({ title: 'Quietanza AdE del ravvedimento', fetchUrl: r.ravvedimento.quietanza_pdf_url })}
                            >
                              Quietanza ravvedimento
                            </button>
                          )}
                        </div>
                      )}
                    </td>
                    <td style={{ ...cella, fontFamily: 'monospace', whiteSpace: 'nowrap' }}>{etichettaM('Causale INPS')}
                      {(r.causali_inps || []).join(', ') || '—'}
                    </td>
                    <td style={{ ...cella, whiteSpace: 'nowrap' }}>{etichettaM('Documento collegato')}
                      {/* I file veri: il modello F24 e la sua quietanza, aperti
                          nel lettore PDF. Niente rimando all'estratto conto:
                          li' bisognava cercare l'operazione a mano. */}
                      <span style={{ display: 'inline-flex', gap: 4, flexWrap: 'wrap' }}>
                        {r.documento_collegato?.f24_pdf_url && (
                          <button
                            type="button"
                            onClick={() => setPdfViewer({
                              title: `F24 ${r.periodo_competenza || ''} · ${r.file || ''}`,
                              fetchUrl: r.documento_collegato.f24_pdf_url,
                            })}
                            data-testid={`apri-f24-${r.f24_id}`}
                            style={bottoneFile}
                          >
                            F24
                          </button>
                        )}
                        {r.documento_collegato?.quietanza_url ? (
                          <button
                            type="button"
                            onClick={() => setPdfViewer({
                              title: `Quietanza F24 ${r.periodo_competenza || ''}${r.documento_collegato.protocollo_quietanza ? ` · protocollo ${r.documento_collegato.protocollo_quietanza}` : ''}`,
                              fetchUrl: r.documento_collegato.quietanza_url,
                            })}
                            data-testid={`link-quietanza-${r.f24_id}`}
                            style={bottoneFile}
                          >
                            Quietanza
                          </button>
                        ) : (
                          <span style={{ fontSize: 11, color: '#7a776e' }}>
                            {r.documento_collegato?.quietanza_id
                              ? 'Quietanza non trovata in archivio'
                              : 'Quietanza non ancora arrivata'}
                          </span>
                        )}
                      </span>
                    </td>
                    <td style={cella}>{etichettaM('Possibile duplicazione')}
                      <span style={{ padding: '3px 8px', borderRadius: 6, fontSize: 11, fontWeight: 700, background: dup.bg, color: dup.color, whiteSpace: 'nowrap' }}>
                        {dup.label}
                      </span>
                    </td>
                    <td style={{ ...cella, minWidth: 220, color: '#5f5c55' }}>{etichettaM('Motivazione')}{r.motivazione}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {righeFiltrate.length > limite && (
            <button type="button" onClick={() => setLimite(x => x + 200)} style={{ ...bottoneFile, minHeight: 44, margin: '10px 0' }}>
              Mostra altre ({righeFiltrate.length - limite})
            </button>
          )}
        </div>
      )}
      {pdfViewer && (
        <VisoreOriginale
          title={pdfViewer.title}
          url={pdfViewer.fetchUrl}
          documentType="f24"
          onClose={() => setPdfViewer(null)}
        />
      )}
    </div>
  );
}

function F24Tab({ f24, onConfermaF24, processing, onLoadF24, f24Loading, onRefresh, anno }) {
  const [limite, setLimite] = useState(200);
  const [selezionati, setSelezionati] = useState(new Set());
  const [pdfViewer, setPdfViewer] = useState(null); // {title, src} — viewer canonico §8
  const [metodoBatch] = useState('banca');
  const [salvandoBatch, setSalvandoBatch] = useState(false);
  const confirm = useConfirm();

  // Filtra F24 con importo > 0
  const f24Validi = f24.filter(f => (f.importo_totale || f.importo || 0) > 0);

  if (f24Validi.length === 0) {
    return (
      <div>
      <AvvisoBonarioF24 />
      <RiscontroQuietanzeBanca anno={anno} />
      <TabellaAnalisiF24 anno={anno} />
      <div style={{ padding: 60, textAlign: 'center', color: '#a19d92' }}>
        <div style={{ fontSize: 48, marginBottom: 12, opacity: 0.5 }}><FileText size={40} aria-hidden="true" style={ICO} /></div>
        <div>Nessun F24 pendente da pagare</div>
        {onLoadF24 && (
          <button
            data-testid="btn-carica-f24"
            onClick={onLoadF24}
            disabled={f24Loading}
            style={{
              marginTop: 16,
              padding: '10px 20px',
              minHeight: 40,
              background: '#c15f3c',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              cursor: f24Loading ? 'wait' : 'pointer',
              fontWeight: 600,
              fontSize: 13,
            }}
          >
            {f24Loading ? 'Caricamento F24...' : 'Carica F24 pendenti'}
          </button>
        )}
      </div>
      </div>
    );
  }

  const totale = f24Validi.reduce((sum, f) => sum + (f.importo_totale || f.importo || 0), 0);
  const totaleSelezionati = f24Validi
    .filter(f => selezionati.has(f.id))
    .reduce((sum, f) => sum + (f.importo_totale || f.importo || 0), 0);

  const toggleSelezione = id => {
    setSelezionati(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  const toggleTutti = () => {
    if (selezionati.size === f24Validi.length) {
      setSelezionati(new Set());
    } else {
      setSelezionati(new Set(f24Validi.map(f => f.id)));
    }
  };

  const confermaBatch = async () => {
    if (selezionati.size === 0) {
      toast.error('Seleziona almeno un F24');
      return;
    }

    setSalvandoBatch(true);
    try {
      const operazioni = f24Validi
        .filter(f => selezionati.has(f.id))
        .map(f => ({
          operazione_id: f.id,
          metodo_pagamento: metodoBatch,
          tipo: 'f24',
        }));

      await api.post('/api/operazioni-da-confermare/smart/conferma-f24', { operazioni });
      toast.success(`Confermati ${selezionati.size} F24`);
      setSelezionati(new Set());
      // Ricarica dati senza reload pagina
      onRefresh?.();
    } catch (e) {
      toast.error('Conferma F24 non riuscita', {
        description: e.response?.data?.detail || e.message,
      });
    } finally {
      setSalvandoBatch(false);
    }
  };

  const confermaF24Singolo = async (f24Item, metodo) => {
    try {
      await api.post('/api/operazioni-da-confermare/smart/conferma-f24', {
        operazioni: [
          {
            operazione_id: f24Item.id,
            metodo_pagamento: metodo,
            tipo: 'f24',
          },
        ],
      });
      toast.success('F24 confermato');
      onRefresh?.();
    } catch (e) {
      toast.error('Conferma F24 non riuscita', {
        description: e.response?.data?.detail || e.message,
      });
    }
  };

  return (
    <div>
      <AvvisoBonarioF24 />
      <RiscontroQuietanzeBanca anno={anno} />
      <TabellaAnalisiF24 anno={anno} />
      <div style={{ padding: 16, background: '#f6f4ee', borderBottom: '1px solid #e6e3d9' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          <h3 style={{ margin: 0, fontSize: 16, color: '#141413' }}>
            <FileText size={14} aria-hidden="true" style={ICO} /> F24 Pendenti ({f24Validi.length})
          </h3>
          <div
            style={{
              fontWeight: 700,
              color: '#dc2626',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            }}
          >
            Totale: {formatEuro(totale)}
          </div>
        </div>

        {/* Azioni batch */}
        <div
          style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}
        >
          <button
            onClick={toggleTutti}
            style={{
              padding: '8px 12px',
              minHeight: 40,
              background: 'white',
              color: '#2c2b28',
              border: '1px solid #e6e3d9',
              borderRadius: 6,
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            {selezionati.size === f24Validi.length ? 'Deseleziona' : 'Seleziona tutti'}
          </button>

          {selezionati.size > 0 && (
            <>
              <span
                style={{
                  padding: '8px 12px',
                  border: '1px solid #dc2626',
                  borderRadius: 6,
                  fontSize: 13,
                  background: '#f8e5e2',
                  fontWeight: 600,
                  color: '#991b1b',
                }}
              >
                <Landmark size={14} aria-hidden="true" style={ICO} /> Pagamento Banca
              </span>

              <button
                onClick={confermaBatch}
                disabled
                title="Disattivato: Fase 0 — serve il movimento bancario"
                style={{
                  padding: '8px 16px',
                  minHeight: 40,
                  background: '#c15f3c',
                  color: 'white',
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'not-allowed',
                  opacity: 0.5,
                  fontWeight: 600,
                  fontSize: 13,
                }}
              >
                {salvandoBatch ? <Hourglass size={14} aria-hidden="true" style={ICO} /> : <Check size={14} aria-hidden="true" style={ICO} />} Conferma {selezionati.size} (
                {formatEuro(totaleSelezionati)})
              </button>
            </>
          )}
        </div>
      </div>

      <div>
        {f24Validi.slice(0, limite).map((f, idx) => {
          const importo = f.importo_totale || f.importo || 0;
          const scadenzaStr = formatDateIT(f.data_scadenza);

          return (
            <div
              key={f.id || idx}
              style={{
                padding: 16,
                borderBottom: '1px solid #f2f0e9',
                background: selezionati.has(f.id) ? '#fef2f2' : 'white',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  gap: 12,
                }}
              >
                {/* Checkbox */}
                <input
                  type="checkbox"
                  checked={selezionati.has(f.id)}
                  onChange={() => toggleSelezione(f.id)}
                  style={{ marginTop: 4, width: 18, height: 18, cursor: 'pointer' }}
                />

                {/* Info F24 */}
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600 }}>
                    {f.contribuente || 'F24'}
                    {f.codici_tributo?.length > 0 && (
                      <span style={{ fontSize: 12, color: '#7a776e', marginLeft: 8 }}>
                        Tributi: {f.codici_tributo.join(', ')}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 12, color: '#7a776e', marginTop: 4 }}>
                    Periodo: {f.periodo || '-'} • Scadenza: {scadenzaStr}
                  </div>
                </div>

                {/* Importo e azioni */}
                <div style={{ textAlign: 'right' }}>
                  <div
                    style={{
                      fontWeight: 700,
                      fontSize: 18,
                      color: '#dc2626',
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                    }}
                  >
                    {formatEuro(importo)}
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      gap: 4,
                      marginTop: 8,
                      justifyContent: 'flex-end',
                      flexWrap: 'wrap',
                    }}
                  >
                    <button
                      onClick={() => confermaF24Singolo(f, 'banca')}
                      disabled
                      style={{
                        padding: '4px 10px',
                        minHeight: 40,
                        background: '#16a34a',
                        color: 'white',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'not-allowed',
                        opacity: 0.5,
                        fontSize: 12,
                      }}
                      title="Disattivato: Fase 0 — serve il movimento bancario"
                    >
                      <Landmark size={14} aria-hidden="true" style={ICO} /> Paga con Banca
                    </button>
                    <button
                      onClick={async () => {
                        if (f.pdf_url) {
                          setPdfViewer({ title: `F24 ${f.descrizione || f.numero || ''}`, url: f.pdf_url });
                        } else {
                          await confirm({
                            title: 'PDF non disponibile',
                            message: 'Carica il PDF F24 dalla sezione Import per poterlo visualizzare.',
                            confirmText: 'Ho capito',
                            cancelText: null,
                          });
                        }
                      }}
                      style={{
                        padding: '4px 10px',
                        minHeight: 40,
                        background: f.pdf_url ? '#c15f3c' : '#a19d92',
                        color: 'white',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'pointer',
                        fontSize: 12,
                      }}
                      title={
                        f.pdf_url ? 'Visualizza PDF F24' : 'PDF non disponibile'
                      }
                    >
                      <Eye size={14} aria-hidden="true" style={ICO} /> Vedi PDF
                    </button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
        {f24Validi.length > limite && (
          <button type="button" onClick={() => setLimite(x => x + 200)} style={{ minHeight: 44, padding: '8px 16px', margin: '10px 0', borderRadius: 6, border: '1px solid #e6e3d9', background: '#fff', color: '#141413', fontWeight: 600, cursor: 'pointer' }}>
            Mostra altre ({f24Validi.length - limite})
          </button>
        )}
      </div>

      {pdfViewer && (
        <VisoreOriginale
          title={pdfViewer.title}
          url={pdfViewer.url}
          documentType="f24"
          onClose={() => setPdfViewer(null)}
        />
      )}
    </div>
  );
}

function DocumentiTab({ documenti, stats, onRefresh, processing }) {
  const [limite, setLimite] = useState(200);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [pdfViewer, setPdfViewer] = useState(null); // {title, src} — viewer canonico §8
  const [collezioni, setCollezioni] = useState([]);
  const [associazioneForm, setAssociazioneForm] = useState({ collezione: '', campiJson: '' });
  const [message, setMessage] = useState(null);
  const [loadingCollezioni, setLoadingCollezioni] = useState(false);
  const confirm = useConfirm();

  // Documenti associati di recente (per poter annullare un'associazione
  // sbagliata — richiesta utente 18/07/2026: "ho cliccato F24 ed ho
  // sbagliato, come riclassifico?" prima non c'era modo di tornare
  // indietro).
  const [recenti, setRecenti] = useState([]);
  const [mostraRecenti, setMostraRecenti] = useState(false);
  const [annullando, setAnnullando] = useState(null);

  const caricaRecenti = async () => {
    try {
      const res = await api.get('/api/documenti-non-associati/associati-di-recente?limit=20');
      setRecenti(res.data?.documenti || []);
    } catch (e) {
      console.warn('Errore caricamento documenti associati di recente:', e);
    }
  };

  const annullaAssociazione = async doc => {
    const ok = await confirm({
      title: 'Annullare questa associazione?',
      message: `${doc.filename || 'Documento'} — collegato a "${doc.associato_a || '—'}". Verrà rimosso il record creato per errore e il documento tornerà tra quelli da associare.`,
      confirmText: 'Annulla associazione', danger: true,
    });
    if (!ok) return;
    setAnnullando(doc.id);
    try {
      await api.post('/api/documenti-non-associati/de-associa', { documento_id: doc.id });
      setMessage({ type: 'success', text: 'Associazione annullata: il documento è tornato tra quelli da associare.' });
      await caricaRecenti();
      onRefresh?.();
    } catch (e) {
      setMessage({ type: 'error', text: 'Errore: ' + (e.response?.data?.detail || e.message) });
    } finally {
      setAnnullando(null);
    }
  };

  // Carica collezioni disponibili
  useEffect(() => {
    const loadCollezioni = async () => {
      setLoadingCollezioni(true);
      try {
        const res = await api.get('/api/documenti-non-associati/collezioni-disponibili');
        setCollezioni(res.data || []);
      } catch (e) {
        console.warn('Errore caricamento collezioni:', e);
      }
      setLoadingCollezioni(false);
    };
    loadCollezioni();
  }, []);

  const handleViewPdf = doc => {
    // fetchUrl (non src): l'endpoint richiede il Bearer token, un <iframe
    // src> diretto non lo allega e la richiesta viene rifiutata (401) senza
    // nessun errore visibile — il PDF restava sempre vuoto (segnalato
    // dall'utente 18/07/2026). Il viewer scarica il blob via axios (stesso
    // pattern di Documenti.jsx/FattureEstereVerifica.jsx).
    setPdfViewer({
      title: `${doc.filename || doc.nome || 'Documento'}`,
      fetchUrl: urlOriginale({ tipo: 'documento', id: doc.id }),
    });
  };

  const handleAssocia = async () => {
    if (!selectedDoc || !associazioneForm.collezione) {
      setMessage({ type: 'error', text: 'Seleziona una collezione' });
      return;
    }

    try {
      let campi = {};
      if (associazioneForm.campiJson) {
        try {
          campi = JSON.parse(associazioneForm.campiJson);
        } catch {
          setMessage({ type: 'error', text: 'JSON campi non valido' });
          return;
        }
      }

      // Aggiungi campi dalla proposta
      if (selectedDoc.proposta) {
        if (selectedDoc?.proposta?.anno_suggerito) campi.anno = selectedDoc?.proposta?.anno_suggerito;
        if (selectedDoc?.proposta?.mese_suggerito) campi.mese = selectedDoc?.proposta?.mese_suggerito;
      }

      await api.post('/api/documenti-non-associati/associa', {
        documento_id: selectedDoc.id,
        collezione_target: associazioneForm.collezione,
        crea_nuovo: true,
        campi_associazione: campi,
      });

      setMessage({ type: 'success', text: 'Documento associato!' });
      setSelectedDoc(null);
      setAssociazioneForm({ collezione: '', campiJson: '' });
      if (onRefresh) onRefresh();
    } catch (e) {
      setMessage({ type: 'error', text: e.response?.data?.detail || 'Errore associazione' });
    }
  };

  const handleDelete = async docId => {
    const confirmed = await confirm({
      title: 'Elimina documento',
      message: 'Eliminare questo documento?',
      confirmText: 'Elimina',
      cancelText: 'Annulla',
      variant: 'danger',
    });
    if (!confirmed) return;

    try {
      await api.delete(`/api/documenti-non-associati/${docId}`);
      setMessage({ type: 'success', text: 'Documento eliminato' });
      setSelectedDoc(null);
      if (onRefresh) onRefresh();
    } catch (e) {
      setMessage({ type: 'error', text: 'Errore eliminazione' });
    }
  };

  const getCategoryColor = category => {
    const colors = {
      fattura: '#5b7a6b',
      f24: '#dc2626',
      busta_paga: '#16a34a',
      verbale: '#d97706',
      cartella: '#c15f3c',
    };
    return colors[category] || '#7a776e';
  };

  if (documenti.length === 0) {
    return (
      <div style={{ padding: 60, textAlign: 'center', color: '#a19d92' }}>
        <div style={{ fontSize: 48, marginBottom: 12, opacity: 0.5 }}><Paperclip size={40} aria-hidden="true" style={ICO} /></div>
        <div>Nessun documento da associare</div>
        <div style={{ fontSize: 12, marginTop: 8 }}>
          Tutti i documenti scaricati sono stati associati
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header con stats */}
      <div style={{ padding: 16, background: '#f6f4ee', borderBottom: '1px solid #e6e3d9' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          <h3 style={{ margin: 0, fontSize: 16, color: '#141413' }}>
            <Paperclip size={14} aria-hidden="true" style={ICO} /> Documenti Non Associati ({documenti.length})
          </h3>
          {stats && (
            <div style={{ display: 'flex', gap: 16, fontSize: 13 }}>
              <span style={{ color: '#7a776e' }}>
                Totali: <strong>{stats.totale || 0}</strong>
              </span>
              <span style={{ color: '#16a34a' }}>
                Associati: <strong>{stats.associati || 0}</strong>
              </span>
              <span style={{ color: '#dc2626' }}>
                Da fare: <strong>{stats.da_associare || 0}</strong>
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Message */}
      {message && (
        <div
          style={{
            padding: 12,
            margin: 12,
            borderRadius: 8,
            background: message.type === 'success' ? '#e2f0e7' : '#f8e5e2',
            color: message.type === 'success' ? '#2f7a4f' : '#dc2626',
            fontSize: 13,
          }}
        >
          {message.text}
        </div>
      )}

      {/* Layout a due colonne */}
      <div
        style={{ display: 'grid', gridTemplateColumns: selectedDoc ? '1fr 1fr' : '1fr', gap: 0 }}
      >
        {/* Lista documenti */}
        <div
          style={{
            maxHeight: 600,
            overflow: 'auto',
            borderRight: selectedDoc ? '1px solid #e6e3d9' : 'none',
          }}
        >
          {documenti.slice(0, limite).map(doc => (
            <div
              key={doc.id}
              onClick={() => setSelectedDoc(doc)}
              style={{
                padding: 14,
                borderBottom: '1px solid #f2f0e9',
                cursor: 'pointer',
                background: selectedDoc?.id === doc.id ? '#f6f4ee' : 'white',
                borderLeft:
                  selectedDoc?.id === doc.id ? '3px solid #c15f3c' : '3px solid transparent',
              }}
            >
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 500,
                  color: '#2c2b28',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  marginBottom: 4,
                }}
              >
                {doc.filename}
              </div>
              <div style={{ fontSize: 12, color: '#7a776e', marginBottom: 6 }}>
                {doc.email_subject?.substring(0, 60) || 'Nessun oggetto'}
              </div>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <span
                  style={{
                    padding: '2px 8px',
                    fontSize: 11,
                    borderRadius: 4,
                    background: getCategoryColor(doc.category) + '20',
                    color: getCategoryColor(doc.category),
                  }}
                >
                  {doc.category || 'altro'}
                </span>
                {doc.proposta?.anno_suggerito && (
                  <span
                    style={{
                      padding: '2px 8px',
                      fontSize: 11,
                      borderRadius: 4,
                      background: '#f7ebe4',
                      color: '#4c4a44',
                    }}
                  >
                    {doc?.proposta?.anno_suggerito}
                  </span>
                )}
              </div>
            </div>
          ))}
          {documenti.length > limite && (
            <button type="button" onClick={() => setLimite(x => x + 200)} style={{ minHeight: 44, padding: '8px 16px', margin: '10px 0', borderRadius: 6, border: '1px solid #e6e3d9', background: '#fff', color: '#141413', fontWeight: 600, cursor: 'pointer' }}>
              Mostra altre ({documenti.length - limite})
            </button>
          )}
        </div>

        {/* Pannello dettaglio */}
        {selectedDoc && (
          <div style={{ padding: 16, background: '#fafafa' }}>
            <div style={{ marginBottom: 16 }}>
              <button
                onClick={() => handleViewPdf(selectedDoc)}
                data-testid="documenti-tab-view-pdf"
                style={{
                  width: '100%',
                  padding: 14,
                  minHeight: 40,
                  background: '#c15f3c',
                  color: 'white',
                  border: 'none',
                  borderRadius: 6,
                  fontWeight: 600,
                  cursor: 'pointer',
                  fontSize: 13,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                }}
              >
                <Eye size={14} aria-hidden="true" style={ICO} /> Apri PDF
              </button>
            </div>

            {/* Info file */}
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#7a776e', marginBottom: 2 }}>File</div>
              <div style={{ fontSize: 14, fontWeight: 500, wordBreak: 'break-all' }}>
                {selectedDoc.filename}
              </div>
            </div>

            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#7a776e', marginBottom: 2 }}>Categoria</div>
              <div style={{ fontSize: 14 }}>{selectedDoc.category || 'Non classificato'}</div>
            </div>

            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#7a776e', marginBottom: 2 }}>Dimensione</div>
              <div style={{ fontSize: 14 }}>
                {Math.round((selectedDoc.size_bytes || selectedDoc.pdf_size || 0) / 1024)} KB
              </div>
            </div>

            {/* Proposta AI */}
            {selectedDoc.proposta &&
              (selectedDoc?.proposta?.anno_suggerito || selectedDoc?.proposta?.tipo_suggerito) && (
                <div
                  style={{
                    background: '#eef3ef',
                    border: '1px solid #c2ddd0',
                    borderRadius: 8,
                    padding: 12,
                    marginBottom: 16,
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#4c4a44', marginBottom: 8 }}>
                    <Lightbulb size={14} aria-hidden="true" style={ICO} /> Proposta Intelligente
                  </div>
                  {selectedDoc?.proposta?.tipo_suggerito && (
                    <div style={{ fontSize: 12, color: '#5f5c55', marginBottom: 4 }}>
                      Tipo: <strong>{selectedDoc?.proposta?.tipo_suggerito}</strong>
                    </div>
                  )}
                  {selectedDoc?.proposta?.anno_suggerito && (
                    <div style={{ fontSize: 12, color: '#5f5c55', marginBottom: 4 }}>
                      Anno: <strong>{selectedDoc?.proposta?.anno_suggerito}</strong>
                    </div>
                  )}
                  {selectedDoc?.proposta?.mese_suggerito && (
                    <div style={{ fontSize: 12, color: '#5f5c55' }}>
                      Mese: <strong>{selectedDoc?.proposta?.mese_suggerito}</strong>
                    </div>
                  )}
                </div>
              )}

            {/* Form associazione */}
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: '#7a776e', marginBottom: 4 }}>
                Associa a collezione
              </div>
              <select
                value={associazioneForm.collezione}
                onChange={e =>
                  setAssociazioneForm({ ...associazioneForm, collezione: e.target.value })
                }
                style={{
                  width: '100%',
                  padding: 10,
                  fontSize: 14,
                  border: '1px solid #e6e3d9',
                  borderRadius: 6,
                  marginBottom: 12,
                }}
              >
                <option value="">-- Seleziona --</option>
                {collezioni.map(c => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>

              <div style={{ fontSize: 12, color: '#7a776e', marginBottom: 4 }}>
                Campi aggiuntivi (JSON)
              </div>
              <textarea
                value={associazioneForm.campiJson}
                onChange={e =>
                  setAssociazioneForm({ ...associazioneForm, campiJson: e.target.value })
                }
                placeholder='{"anno": 2024, "importo": 150.00}'
                style={{
                  width: '100%',
                  padding: 10,
                  fontSize: 13,
                  fontFamily: 'monospace',
                  border: '1px solid #e6e3d9',
                  borderRadius: 6,
                  minHeight: 60,
                  resize: 'vertical',
                }}
              />
            </div>

            {/* Bottoni azione */}
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button
                onClick={handleAssocia}
                disabled={!associazioneForm.collezione}
                style={{
                  flex: 1,
                  padding: 12,
                  minHeight: 40,
                  background: associazioneForm.collezione ? '#16a34a' : '#a19d92',
                  color: 'white',
                  border: 'none',
                  borderRadius: 6,
                  fontWeight: 600,
                  cursor: associazioneForm.collezione ? 'pointer' : 'not-allowed',
                  fontSize: 13,
                }}
              >
                <Check size={14} aria-hidden="true" style={ICO} /> Associa
              </button>
              <button
                onClick={() => handleDelete(selectedDoc.id)}
                style={{
                  padding: '12px 16px',
                  minHeight: 40,
                  minWidth: 40,
                  background: '#f8e5e2',
                  color: '#dc2626',
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontSize: 13,
                }}
              >
                <Trash2 size={14} aria-hidden="true" style={ICO} />
              </button>
            </div>
          </div>
        )}
      </div>

      <div style={{ marginTop: 16, padding: 16, background: '#fafafa', borderRadius: 8 }}>
        <button
          onClick={() => { setMostraRecenti(m => !m); if (!mostraRecenti && recenti.length === 0) caricaRecenti(); }}
          style={{
            background: 'none', border: 'none', cursor: 'pointer', padding: 0,
            fontSize: 13, fontWeight: 600, color: '#141413', display: 'flex', alignItems: 'center', gap: 6,
          }}
        >
          {mostraRecenti ? <ChevronDown size={14} aria-hidden="true" style={ICO} /> : <ChevronRight size={14} aria-hidden="true" style={ICO} />} Documenti associati di recente — sbagliato collezione? Annulla qui
        </button>
        {mostraRecenti && (
          <div style={{ marginTop: 10, display: 'grid', gap: 6 }}>
            {recenti.length === 0 && (
              <div style={{ fontSize: 12.5, color: '#7a776e' }}>Nessun documento associato di recente.</div>
            )}
            {recenti.map(doc => (
              <div
                key={doc.id}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10,
                  padding: '8px 12px', background: 'white', borderRadius: 6, border: '1px solid #e6e3d9', fontSize: 12.5,
                }}
              >
                <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {doc.filename || 'Documento'} → <strong>{doc.associato_a || '—'}</strong>
                </span>
                <button
                  onClick={() => annullaAssociazione(doc)}
                  disabled={annullando === doc.id}
                  style={{
                    flexShrink: 0, padding: '5px 10px', background: '#fef2f2', color: '#dc2626',
                    border: '1px solid #fecaca', borderRadius: 6, fontSize: 12, cursor: 'pointer',
                    opacity: annullando === doc.id ? 0.5 : 1,
                  }}
                >
                  {annullando === doc.id ? '…' : 'Annulla'}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {pdfViewer && (
        <VisoreOriginale
          title={pdfViewer.title}
          url={pdfViewer.fetchUrl}
          documentType="documento_fiscale"
          onClose={() => setPdfViewer(null)}
        />
      )}
    </div>
  );
}

import React, { useEffect, useState } from 'react';
import { RefreshCw, Wallet, Calculator, CheckCircle2, Unlock } from 'lucide-react';
import { Link } from 'react-router-dom';
import api from '../api';
import { getConCopia } from '../lib/cacheGuscio';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, formatDateIT, COLORS, MESI_FULL } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { Button, Badge } from '../components/ds';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { ConfrontoIvaCommercialista, ScadenzeIvaMensili, giornoIT } from './iva/IvaAuditSections';
import './GestioneIVA.css';
import { euroOppure } from '../lib/vista';

/**
 * Gestione IVA — Fase 1: "IVA disponibile non ancora utilizzata"
 * (SPECIFICA_IVA.md §14). Mostra le fatture di acquisto la cui IVA è stata
 * attribuita per competenza ma non ancora inserita in una liquidazione, con
 * il periodo attribuito e la regola applicata. Le liquidazioni mensili
 * persistite arrivano nelle fasi successive.
 */
// Come nell'artefatto: 200 righe per tabella, poi «Mostra altre». Conteggi e
// totali arrivano dal server sull'intero periodo, non sulle righe caricate.
const RIGHE_PER_PAGINA = 200;

/** Primo e ultimo giorno del periodo IVA mostrato (anno intero o un mese). */
export function intervalloPeriodo(anno, mese, vistaAnnuale) {
  if (vistaAnnuale) return { start: `${anno}-01-01`, end: `${anno}-12-31` };
  const mm = String(mese).padStart(2, '0');
  const ultimo = String(new Date(anno, mese, 0).getDate()).padStart(2, '0');
  return { start: `${anno}-${mm}-01`, end: `${anno}-${mm}-${ultimo}` };
}

const STATO_LABEL = {
  DA_INSERIRE: { label: 'Da inserire', variant: 'warning' },
  INSERITA_IN_LIQUIDAZIONE: { label: 'In liquidazione', variant: 'success' },
  DA_VERIFICARE: { label: 'Da verificare', variant: 'danger' },
  ESCLUSA: { label: 'Esclusa', variant: 'neutral' },
  RINVIATA: { label: 'Rinviata', variant: 'info' },
};

const REGOLA_LABEL = {
  STESSO_MESE: 'Stesso mese',
  ENTRO_15_MESE_SUCCESSIVO: 'Entro il 15',
  RICEVUTA_DOPO_IL_15: 'Dopo il 15',
  OPERAZIONE_ANNO_PRECEDENTE: 'Anno precedente',
  DA_VERIFICARE: '—',
};

const STATO_LIQ = {
  BOZZA: { label: 'Bozza', variant: 'neutral' },
  CALCOLATA: { label: 'Calcolata', variant: 'info' },
  DA_VERIFICARE: { label: 'Da verificare', variant: 'warning' },
  CONFERMATA: { label: 'Confermata', variant: 'success' },
  TRASMESSA: { label: 'Trasmessa', variant: 'success' },
  RIAPERTA: { label: 'Riaperta', variant: 'warning' },
  RETTIFICATA: { label: 'Rettificata', variant: 'danger' },
};

export default function GestioneIVA() {
  const { anno } = useAnnoGlobale();
  const confirm = useConfirm();
  const [dati, setDati] = useState(null);
  const [corrispettivi, setCorrispettivi] = useState([]);
  // Giornate XML uniche, copie escluse e totali del periodo intero (server).
  const [riepilogoCorrispettivi, setRiepilogoCorrispettivi] = useState(null);
  const [caricaAltreFatture, setCaricaAltreFatture] = useState(false);
  const [caricaAltriCorrispettivi, setCaricaAltriCorrispettivi] = useState(false);
  const [loading, setLoading] = useState(true);
  const [errorePeriodo, setErrorePeriodo] = useState('');
  const [ricalcolo, setRicalcolo] = useState(false);
  const [msg, setMsg] = useState(null);

  // Liquidazione mensile (Fase 3)
  const [mese, setMese] = useState(() => new Date().getMonth() + 1);
  const [vistaAnnuale, setVistaAnnuale] = useState(false);
  const [liquidazione, setLiquidazione] = useState(null);
  const [busyLiq, setBusyLiq] = useState(false);
  const periodo = `${anno}-${String(mese).padStart(2, '0')}`;

  // Riepilogo annuale + anomalie (Fase 4)
  const [riepilogo, setRiepilogo] = useState(null);
  const [anomalie, setAnomalie] = useState(null);

  // Dashboard IVA del mese (Fase 5)
  const [dashboard, setDashboard] = useState(null);

  // Pagina IVA unica: confronto F24 commercialista e scadenze mensili.
  const [confrontoCommercialista, setConfrontoCommercialista] = useState(null);
  const [scadenzeMensili, setScadenzeMensili] = useState(null);
  const [controlliLoading, setControlliLoading] = useState(true);
  const [controlliError, setControlliError] = useState({ confronto: null, scadenze: null });

  const caricaControlliIva = async () => {
    setControlliLoading(true);
    const [confronto, scadenze] = await Promise.allSettled([
      api.get(`/api/verifica-coerenza/confronto-iva-completo/${anno}`),
      api.get(`/api/scadenze/iva-mensile/${anno}`),
    ]);

    setConfrontoCommercialista(confronto.status === 'fulfilled' ? confronto.value.data : null);
    setScadenzeMensili(scadenze.status === 'fulfilled' ? scadenze.value.data : null);
    setControlliError({
      confronto: confronto.status === 'rejected'
        ? `Confronto F24 non disponibile: ${confronto.reason?.response?.data?.detail || confronto.reason?.message || 'errore sconosciuto'}`
        : null,
      scadenze: scadenze.status === 'rejected'
        ? `Scadenze IVA non disponibili: ${scadenze.reason?.response?.data?.detail || scadenze.reason?.message || 'errore sconosciuto'}`
        : null,
    });
    setControlliLoading(false);
  };

  const caricaRiepilogo = async () => {
    try {
      // La copia di questa sessione si vede subito; la risposta fresca la sostituisce.
      const [r, a] = await Promise.all([
        getConCopia(`/api/iva/riepilogo-annuale/${anno}`, undefined, copia => copia && setRiepilogo(copia)),
        getConCopia(`/api/iva/anomalie?anno=${anno}`, undefined, copia => copia && setAnomalie(copia)),
      ]);
      setRiepilogo(r.data);
      setAnomalie(a.data);
    } catch (e) {
      setRiepilogo(null);
      setAnomalie(null);
      setMsg({ tipo: 'errore', testo: 'Impossibile caricare riepilogo e anomalie IVA: ' + (e.response?.data?.detail || e.message) });
    }
  };

  const caricaLiquidazione = async (p = periodo) => {
    getConCopia(`/api/iva/dashboard/${anno}/${mese}`, undefined, copia => copia && setDashboard(copia))
      .then((d) => setDashboard(d.data))
      .catch((e) => {
        setDashboard(null);
        setMsg({ tipo: 'errore', testo: 'Impossibile caricare il cruscotto IVA mensile: ' + (e.response?.data?.detail || e.message) });
      });
    try {
      const res = await api.get(`/api/iva/liquidazioni/${p}`);
      setLiquidazione(res.data?.corrente || null);
    } catch (e) {
      setLiquidazione(null);
      setMsg({ tipo: 'errore', testo: 'Impossibile caricare la liquidazione IVA: ' + (e.response?.data?.detail || e.message) });
    }
  };

  const calcolaLiq = async () => {
    setBusyLiq(true);
    setMsg(null);
    try {
      const res = await api.post(`/api/iva/liquidazioni/calcola?periodo=${periodo}`);
      setLiquidazione(res.data?.liquidazione || null);
    } catch (e) {
      setMsg({ tipo: 'errore', testo: 'Errore calcolo: ' + (e.response?.data?.detail || e.message) });
    } finally {
      setBusyLiq(false);
    }
  };

  const confermaLiq = async () => {
    if (!liquidazione?.id) return;
    const ok = await confirm({
      title: `Conferma liquidazione ${periodo}`,
      message: `Confermare IVA vendite ${euroOppure(liquidazione.iva_vendite)}, IVA acquisti ${euroOppure(liquidazione.iva_acquisti)} e ${liquidazione.fatture_incluse?.length || 0} fatture? Dopo la conferma l'IVA viene marcata come utilizzata.`,
      variant: 'warning',
    });
    if (!ok) return;
    setBusyLiq(true);
    setMsg(null);
    try {
      await api.post(`/api/iva/liquidazioni/${liquidazione.id}/conferma`);
      setMsg({ tipo: 'ok', testo: `Liquidazione ${periodo} confermata: IVA marcata come utilizzata.` });
      await caricaLiquidazione();
      await carica();
    } catch (e) {
      const dettaglio = e.response?.data?.detail;
      const testo = typeof dettaglio === 'object' && dettaglio
        ? dettaglio.message || JSON.stringify(dettaglio)
        : dettaglio || e.message;
      setMsg({ tipo: 'errore', testo: 'Errore conferma: ' + testo });
    } finally {
      setBusyLiq(false);
    }
  };

  const riapriLiq = async () => {
    if (!liquidazione?.id) return;
    const ok = await confirm({
      title: `Riapri liquidazione ${periodo}`,
      message: `Riaprire la liquidazione confermata? L'IVA delle ${liquidazione.fatture_incluse?.length || 0} fatture tornera disponibile e l'operazione sara registrata nell'audit.`,
      variant: 'danger',
    });
    if (!ok) return;
    setBusyLiq(true);
    setMsg(null);
    try {
      await api.post(`/api/iva/liquidazioni/${liquidazione.id}/riapri?motivo=Riapertura+manuale+confermata`);
      setMsg({ tipo: 'ok', testo: `Liquidazione ${periodo} riaperta: IVA di nuovo disponibile.` });
      await caricaLiquidazione();
      await carica();
    } catch (e) {
      setMsg({ tipo: 'errore', testo: 'Errore riapertura: ' + (e.response?.data?.detail || e.message) });
    } finally {
      setBusyLiq(false);
    }
  };

  const urlFatture = () => (vistaAnnuale
    ? `/api/iva/fatture?anno=${anno}`
    : `/api/iva/fatture?periodo=${periodo}`);

  // «Mostra altre»: la pagina successiva si accoda, i totali restano quelli
  // del server sull'intero periodo.
  const mostraAltreFatture = async () => {
    setCaricaAltreFatture(true);
    try {
      const gia = dati?.fatture?.length || 0;
      const res = await api.get(`${urlFatture()}&limit=${RIGHE_PER_PAGINA}&skip=${gia}`);
      setDati(prev => ({ ...prev, fatture: [...(prev?.fatture || []), ...(res.data?.fatture || [])] }));
    } catch (e) {
      setMsg({ tipo: 'errore', testo: 'Altre fatture non caricate: ' + (e.response?.data?.detail || e.message) });
    } finally {
      setCaricaAltreFatture(false);
    }
  };

  const mostraAltriCorrispettivi = async () => {
    setCaricaAltriCorrispettivi(true);
    try {
      const { start, end } = intervalloPeriodo(anno, mese, vistaAnnuale);
      const res = await api.get(
        `/api/corrispettivi/periodo?data_da=${start}&data_a=${end}&limit=${RIGHE_PER_PAGINA}&skip=${corrispettivi.length}`,
      );
      setCorrispettivi(prev => [...prev, ...(res.data?.corrispettivi || [])]);
    } catch (e) {
      setMsg({ tipo: 'errore', testo: 'Altri corrispettivi non caricati: ' + (e.response?.data?.detail || e.message) });
    } finally {
      setCaricaAltriCorrispettivi(false);
    }
  };

  const carica = async () => {
    setLoading(true);
    setErrorePeriodo('');
    // Un cambio di mese/anno non deve lasciare visibili i valori del periodo
    // precedente sotto la nuova intestazione mentre la richiesta e' in corso
    // o se una delle due fonti fallisce.
    setDati(null);
    setCorrispettivi([]);
    setRiepilogoCorrispettivi(null);
    try {
      const { start, end } = intervalloPeriodo(anno, mese, vistaAnnuale);
      const [fattureRes, corrispettiviRes] = await Promise.all([
        api.get(`${urlFatture()}&limit=${RIGHE_PER_PAGINA}`),
        api.get(`/api/corrispettivi/periodo?data_da=${start}&data_a=${end}&limit=${RIGHE_PER_PAGINA}`),
      ]);
      setDati(fattureRes.data);
      setCorrispettivi(corrispettiviRes.data?.corrispettivi || []);
      setRiepilogoCorrispettivi(corrispettiviRes.data || null);
    } catch (e) {
      const dettaglio = e.response?.data?.detail || e.message || 'errore sconosciuto';
      setErrorePeriodo(dettaglio);
      setMsg({ tipo: 'errore', testo: 'Dati IVA del periodo non disponibili: ' + dettaglio });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    carica();
  }, [anno, mese, vistaAnnuale]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    caricaLiquidazione();
  }, [anno, mese]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    caricaRiepilogo();
    caricaControlliIva();
  }, [anno]); // eslint-disable-line react-hooks/exhaustive-deps

  // Calcola pregresso: rilegge DAVVERO le fatture (tutte, o solo l'anno) e
  // ricalcola l'IVA. tuttoIlPregresso=true → nessun filtro anno.
  const ricalcolaAttribuzione = async (tuttoIlPregresso = true) => {
    const ambito = tuttoIlPregresso ? 'tutto il pregresso' : `il solo anno ${anno}`;
    const ok = await confirm({
      title: 'Ricalcola attribuzione IVA',
      message: `Ricalcolare ${ambito}? Le liquidazioni confermate non saranno modificate, ma i campi IVA delle fatture disponibili verranno aggiornati.`,
      variant: 'warning',
    });
    if (!ok) return;
    setRicalcolo(true);
    setMsg(null);
    try {
      const q = tuttoIlPregresso ? '' : `?anno=${anno}`;
      const res = await api.post(`/api/iva/ricalcola-attribuzione${q}`);
      const r = res.data?.report || {};
      setMsg({
        tipo: 'ok',
        testo: `Lette ${r.lette || 0} fatture: ${r.modificate || 0} aggiornate, `
          + `${r.con_periodo || 0} attribuite, ${r.da_verificare || 0} da verificare.`,
      });
      await carica();
      await caricaRiepilogo();
    } catch (e) {
      setMsg({ tipo: 'errore', testo: 'Errore ricalcolo: ' + (e.response?.data?.detail || e.message) });
    } finally {
      setRicalcolo(false);
    }
  };

  const fatture = dati?.fatture || [];
  // Le copie della stessa giornata le toglie il server (chiave_giornata_xml):
  // qui arrivano solo giornate uniche, una pagina alla volta.
  const corrispettiviUnici = corrispettivi;
  const giornateXml = riepilogoCorrispettivi?.totale ?? corrispettiviUnici.length;
  const duplicatiCorrispettiviEsclusi = riepilogoCorrispettivi?.copie_escluse || 0;
  const totaliCorrispettivi = riepilogoCorrispettivi?.totali
    || { totale: 0, imponibile: 0, iva: 0, contanti: 0, elettronico: 0 };
  const fattureTotali = dati?.totale ?? fatture.length;
  const fattureRimanenti = Math.max(0, fattureTotali - fatture.length);
  const corrispettiviRimanenti = Math.max(0, giornateXml - corrispettiviUnici.length);
  const etichettaPercentuale = fattura => {
    if (!fattura.detraibilita_valutata || fattura.percentuale_detraibilita_iva == null) {
      return 'Da classificare';
    }
    return `${Number(fattura.percentuale_detraibilita_iva).toLocaleString('it-IT', {
      maximumFractionDigits: 2,
    })}%`;
  };
  const riepilogoAliquote = corrispettivo => {
    const righe = corrispettivo.riepilogo_iva || corrispettivo.riepiloghi_iva || [];
    if (Array.isArray(righe)) {
      return righe
        .map(r => {
          const aliquota = r.aliquota_iva ?? r.aliquota;
          const iva = r.imposta ?? r.iva;
          return aliquota == null ? null : `${aliquota}%: ${euroOppure(iva)}`;
        })
        .filter(Boolean)
        .join(' · ');
    }
    if (righe && typeof righe === 'object') {
      return Object.entries(righe)
        .map(([aliquota, valore]) => `${aliquota}%: ${formatEuro(valore?.iva ?? valore?.imposta ?? valore)}`)
        .join(' · ');
    }
    return '—';
  };

  const aggiornaTutto = () => Promise.all([
    carica(),
    caricaLiquidazione(),
    caricaRiepilogo(),
    caricaControlliIva(),
  ]);

  return (
    <PageLayout title="Gestione IVA" subtitle={`Attribuzione, liquidazione, F24 e scadenze — ${anno}`}>
      <nav className="iva-period-tabs" role="tablist" aria-label="Periodo IVA">
        <button
          type="button"
          role="tab"
          aria-selected={vistaAnnuale}
          className={vistaAnnuale ? 'is-active' : ''}
          onClick={() => setVistaAnnuale(true)}
          data-testid="iva-tab-annuale"
        >
          Annuale
        </button>
        {MESI_FULL.slice(1).map((nome, indice) => {
          const numeroMese = indice + 1;
          const attivo = !vistaAnnuale && mese === numeroMese;
          return (
            <button
              key={numeroMese}
              type="button"
              role="tab"
              aria-selected={attivo}
              className={attivo ? 'is-active' : ''}
              onClick={() => {
                setMese(numeroMese);
                setVistaAnnuale(false);
              }}
              data-testid={`iva-tab-mese-${numeroMese}`}
            >
              {nome.slice(0, 3)}
            </button>
          );
        })}
      </nav>

      <div className="iva-command-bar" data-testid="iva-command-bar">
        <div>
          <strong>{vistaAnnuale ? `Tutto il ${anno}` : `${MESI_FULL[mese]} ${anno}`}</strong>
          <span>
            {loading
              ? 'Caricamento dati del periodo…'
              : errorePeriodo
                ? 'Dati del periodo non disponibili'
              : `${fattureTotali} fatture · ${giornateXml} giornate XML`}
          </span>
        </div>
        <div className="iva-command-actions">
          <Button variant="secondary" size="sm" onClick={aggiornaTutto} disabled={loading || controlliLoading}>
            <RefreshCw size={15} className={loading || controlliLoading ? 'spin' : ''} /> Aggiorna
          </Button>
          <Link to={`/situazione-fiscale/dichiarazioni?year=${anno}&type=DICHIARAZIONE_IVA`} style={{ textDecoration: 'none' }}>
            <Button variant="secondary" size="sm">Dichiarazioni IVA, F24 e quietanze</Button>
          </Link>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => ricalcolaAttribuzione(false)}
            disabled={ricalcolo}
            data-testid="iva-ricalcola-anno"
          >
            <Calculator size={15} /> {ricalcolo ? 'Ricalcolo...' : `Ricalcola ${anno}`}
          </Button>
          {!vistaAnnuale && (
            <Button variant="primary" size="sm" onClick={calcolaLiq} disabled={busyLiq} data-testid="liq-calcola">
              <Calculator size={15} /> Calcola mese
            </Button>
          )}
          {!vistaAnnuale && liquidazione && !['CONFERMATA', 'TRASMESSA'].includes(liquidazione.stato) && (
            <Button variant="success" size="sm" onClick={confermaLiq} disabled={busyLiq} data-testid="liq-conferma">
              <CheckCircle2 size={15} /> Conferma
            </Button>
          )}
          {!vistaAnnuale && liquidazione && ['CONFERMATA', 'TRASMESSA'].includes(liquidazione.stato) && (
            <Button variant="secondary" size="sm" onClick={riapriLiq} disabled={busyLiq} data-testid="liq-riapri">
              <Unlock size={15} /> Riapri
            </Button>
          )}
        </div>
      </div>

      {loading ? (
        <div role="status" style={STILI.vuoto}>Caricamento conteggi IVA del periodo…</div>
      ) : errorePeriodo ? (
        <div data-testid="iva-periodo-non-disponibile" style={STILI.vuoto}>
          Conteggi IVA non disponibili: non vengono mostrati valori zero né dati del periodo precedente.
        </div>
      ) : (
        <div className="iva-kpi-grid">
          <div><span>Fatture nel periodo</span><strong>{fattureTotali}</strong></div>
          <div><span>IVA esposta</span><strong>{euroOppure(dati?.totale_iva_esposta)}</strong></div>
          <div><span>IVA detraibile</span><strong>{euroOppure(dati?.totale_iva_detraibile)}</strong></div>
          <div data-testid="iva-totale-disponibile"><span>Ancora disponibile</span><strong>{euroOppure(dati?.totale_iva_disponibile)}</strong></div>
          <div><span>IVA corrispettivi</span><strong>{euroOppure(totaliCorrispettivi.iva)}</strong></div>
          <div><span>Da verificare</span><strong>{dati?.totale_da_verificare || 0}</strong></div>
        </div>
      )}

      {/* ── Calcola pregresso (persistente) ───────────────────────────── */}
      {msg && (
        <div
          role={msg.tipo === 'ok' ? 'status' : 'alert'}
          aria-live="polite"
          style={{ ...STILI.msg, ...(msg.tipo === 'ok' ? STILI.msgOk : STILI.msgErr) }}
        >
          {msg.testo}
        </div>
      )}

      <section className="iva-detail-section" aria-labelledby="iva-fatture-periodo">
        <div className="iva-section-heading">
          <div>
            <h3 id="iva-fatture-periodo">Fatture di acquisto del periodo</h3>
            <p>IVA esposta, percentuale di detraibilità e IVA effettivamente detraibile.</p>
          </div>
          <Badge variant={errorePeriodo ? 'danger' : 'info'}>
            {errorePeriodo ? 'Non disponibile' : `${fattureTotali} fatture`}
          </Badge>
        </div>
        {loading ? (
          <div style={STILI.vuoto}>Caricamento…</div>
        ) : errorePeriodo ? (
          <div style={STILI.vuoto}>Elenco fatture non disponibile per il periodo selezionato.</div>
        ) : fatture.length === 0 ? (
          <div style={STILI.vuoto}>
            Nessuna fattura attribuita a {vistaAnnuale ? `tutto il ${anno}` : `${MESI_FULL[mese]} ${anno}`}.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="iva-responsive-table" style={STILI.tabella} data-testid="iva-tabella">
              <thead>
                <tr>
                  <th style={STILI.th}>Fornitore</th>
                  <th style={STILI.th}>N. fattura</th>
                  <th style={STILI.th}>Data doc.</th>
                  <th style={STILI.th}>Periodo IVA</th>
                  <th style={STILI.th}>Regola</th>
                  <th style={{ ...STILI.th, textAlign: 'right' }}>IVA esposta</th>
                  <th style={{ ...STILI.th, textAlign: 'right' }}>Detraibilità</th>
                  <th style={{ ...STILI.th, textAlign: 'right' }}>IVA detraibile</th>
                  <th style={STILI.th}>Stato</th>
                </tr>
              </thead>
              <tbody>
                {fatture.map((f, i) => {
                  const st = STATO_LABEL[f.stato_detrazione_iva] || STATO_LABEL.DA_INSERIRE;
                  return (
                    <tr key={f.id || i} style={{ borderTop: `1px solid ${COLORS.border}` }}>
                      <td data-label="Fornitore" style={STILI.td}>{f.supplier_name || '—'}</td>
                      <td data-label="N. fattura" style={STILI.td}>{f.invoice_number || '—'}</td>
                      <td data-label="Data documento" style={STILI.td}>{formatDateIT(f.data_documento)}</td>
                      <td data-label="Periodo IVA" style={STILI.td}>
                        <strong>{f.periodo_iva_attribuito || '—'}</strong>
                      </td>
                      <td data-label="Regola" style={{ ...STILI.td, fontSize: 12, color: COLORS.textMuted }}>
                        {REGOLA_LABEL[f.regola_iva_applicata] || f.regola_iva_applicata || '—'}
                      </td>
                      <td data-label="IVA esposta" style={{ ...STILI.td, textAlign: 'right' }}>
                        {euroOppure(f.iva_esposta)}
                      </td>
                      <td data-label="Detraibilità IVA" style={{ ...STILI.td, textAlign: 'right', fontWeight: 700 }}>
                        {etichettaPercentuale(f)}
                      </td>
                      <td data-label="IVA detraibile" style={{ ...STILI.td, textAlign: 'right', fontWeight: 700 }}>
                        {euroOppure(f.iva_detraibile)}
                      </td>
                      <td data-label="Stato" style={STILI.td}>
                        <Badge variant={st.variant}>{st.label}</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {fattureRimanenti > 0 && (
              <MostraAltre
                testId="iva-mostra-altre-fatture"
                rimanenti={fattureRimanenti}
                inCorso={caricaAltreFatture}
                onClick={mostraAltreFatture}
              />
            )}
          </div>
        )}
      </section>

      <section className="iva-detail-section" aria-labelledby="iva-corrispettivi-periodo">
        <div className="iva-section-heading">
          <div>
            <h3 id="iva-corrispettivi-periodo">Corrispettivi del periodo</h3>
            <p>
              Una riga per giornata XML. La matricola RT identifica il registratore e può ripetersi
              correttamente in giorni diversi.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <Badge variant={errorePeriodo ? 'danger' : 'info'}>
              {errorePeriodo ? 'Non disponibile' : `${giornateXml} giornate`}
            </Badge>
            {duplicatiCorrispettiviEsclusi > 0 && (
              <Badge variant="neutral">{duplicatiCorrispettiviEsclusi} copie escluse</Badge>
            )}
          </div>
        </div>
        {loading ? (
          <div style={STILI.vuoto}>Caricamento…</div>
        ) : errorePeriodo ? (
          <div style={STILI.vuoto}>Corrispettivi non disponibili per il periodo selezionato.</div>
        ) : corrispettiviUnici.length === 0 ? (
          <div style={STILI.vuoto}>Nessun corrispettivo XML nel periodo selezionato.</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="iva-responsive-table" style={STILI.tabella} data-testid="iva-corrispettivi-tabella">
              <thead>
                <tr>
                  <th style={STILI.th}>Data</th>
                  <th style={STILI.th}>Matricola RT</th>
                  <th style={{ ...STILI.th, textAlign: 'right' }}>Imponibile</th>
                  <th style={{ ...STILI.th, textAlign: 'right' }}>IVA</th>
                  <th style={{ ...STILI.th, textAlign: 'right' }}>Totale</th>
                  <th style={{ ...STILI.th, textAlign: 'right' }}>Contanti</th>
                  <th style={{ ...STILI.th, textAlign: 'right' }}>Elettronico</th>
                  <th style={STILI.th}>Aliquote IVA</th>
                </tr>
              </thead>
              <tbody>
                {corrispettiviUnici.map((c, i) => (
                  <tr key={c.id || c.id_invio || i} style={{ borderTop: `1px solid ${COLORS.border}` }}>
                    <td data-label="Data" style={STILI.td}>{formatDateIT(c.data || c.data_rilevazione)}</td>
                    <td data-label="Matricola RT" style={STILI.td}>{c.matricola_rt || c.matricola || c.id_dispositivo || '—'}</td>
                    <td data-label="Imponibile" style={{ ...STILI.td, textAlign: 'right' }}>{euroOppure(c.totale_imponibile ?? c.imponibile)}</td>
                    <td data-label="IVA" style={{ ...STILI.td, textAlign: 'right', fontWeight: 700 }}>{euroOppure(c.totale_iva ?? c.iva)}</td>
                    <td data-label="Totale" style={{ ...STILI.td, textAlign: 'right', fontWeight: 700 }}>{euroOppure(c.totale ?? c.totale_complessivo)}</td>
                    <td data-label="Contanti" style={{ ...STILI.td, textAlign: 'right' }}>{euroOppure(c.pagato_contanti ?? c.contanti)}</td>
                    <td data-label="Elettronico" style={{ ...STILI.td, textAlign: 'right' }}>{euroOppure(c.pagato_elettronico ?? c.elettronico ?? c.pagato_pos)}</td>
                    <td data-label="Aliquote IVA" style={{ ...STILI.td, fontSize: 12, color: COLORS.textMuted }}>{riepilogoAliquote(c)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan="2" style={STILI.th}>Totale periodo</td>
                  <td style={{ ...STILI.th, textAlign: 'right' }}>{euroOppure(totaliCorrispettivi.imponibile)}</td>
                  <td style={{ ...STILI.th, textAlign: 'right' }}>{euroOppure(totaliCorrispettivi.iva)}</td>
                  <td style={{ ...STILI.th, textAlign: 'right' }}>{euroOppure(totaliCorrispettivi.totale)}</td>
                  <td style={{ ...STILI.th, textAlign: 'right' }}>{euroOppure(totaliCorrispettivi.contanti)}</td>
                  <td style={{ ...STILI.th, textAlign: 'right' }}>{euroOppure(totaliCorrispettivi.elettronico)}</td>
                  <td />
                </tr>
              </tfoot>
            </table>
            {corrispettiviRimanenti > 0 && (
              <MostraAltre
                testId="iva-mostra-altri-corrispettivi"
                rimanenti={corrispettiviRimanenti}
                inCorso={caricaAltriCorrispettivi}
                onClick={mostraAltriCorrispettivi}
              />
            )}
          </div>
        )}
      </section>

      {/* ── Liquidazione mensile (Fase 3) ─────────────────────────────── */}
      {!vistaAnnuale && <div id="iva-liquidazione" style={STILI.sezione} data-testid="liquidazione-mensile">
        <h3 style={STILI.sezioneTitolo}>
          <Calculator size={18} style={{ color: COLORS.primary }} /> Liquidazione {MESI_FULL[mese]} {anno}
        </h3>

        {dashboard && (
          <div style={{ ...STILI.riepilogo, borderBottom: 'none' }} data-testid="iva-dashboard-mese">
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Attribuita al mese</span>
              <strong>{euroOppure(dashboard.iva_acquisti_attribuita)}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Ricevuta ma competenza mese prec.</span>
              <strong>{euroOppure(dashboard.iva_ricevuta_attribuita_mese_precedente)}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Utilizzata</span>
              <strong>{euroOppure(dashboard.iva_utilizzata)}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Non utilizzata</span>
              <strong>{euroOppure(dashboard.iva_non_utilizzata)}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Rinviata</span>
              <strong>{euroOppure(dashboard.iva_rinviata)}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Indetraibile</span>
              <strong>{euroOppure(dashboard.iva_indetraibile)}</strong>
            </div>
          </div>
        )}

        {dashboard?.stato_liquidazione === 'DATI_MANCANTI' && (
          <div
            role="alert"
            data-testid="iva-dati-mancanti"
            style={{ marginTop: 8, padding: 12, borderRadius: 8, background: '#fdf3e7', border: '1px solid #c4894a', color: '#6f583a', fontSize: 13 }}
          >
            <strong>Liquidazione non calcolabile: dati mancanti.</strong>{' '}
            Un mese senza chiusure RT o senza fatture in archivio non è «IVA 0 €», è un mese non caricato.
            <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
              {(dashboard.motivi || []).includes('archivio_fatture_vuoto') && (
                <li>Archivio fatture vuoto: IVA acquisti non determinabile.</li>
              )}
              {(dashboard.motivi || []).includes('archivio_fatture_non_verificabile') && (
                <li>Archivio fatture non verificabile: IVA acquisti non determinabile.</li>
              )}
              {(dashboard.motivi || []).includes('nessun_corrispettivo_nel_mese') && (
                <li>Nessun corrispettivo del mese in archivio.</li>
              )}
              {(dashboard.motivi || []).includes('detraibilita_da_verificare') && (
                <li>
                  Detraibilità IVA da verificare su{' '}
                  {dashboard.conteggi_iva?.detraibilita_da_decidere_con_iva ?? 'alcune'} fatture:
                  IVA acquisti non calcolabile finché non si decide.
                </li>
              )}
              {(dashboard.giorni_senza_corrispettivo || []).length > 0 && (
                <li>
                  Giorni senza chiusura RT: {dashboard.giorni_senza_corrispettivo.length}
                  {dashboard.giorni_mese ? ` su ${dashboard.giorni_mese}` : ''} —{' '}
                  {dashboard.giorni_senza_corrispettivo.map(giornoIT).join(', ')}
                </li>
              )}
            </ul>
          </div>
        )}

        {dashboard?.versamento_iva && (
          <div
            style={{
              ...STILI.sezione,
              marginTop: 8,
              borderColor: dashboard.versamento_iva.f24_trovati === 1
                ? COLORS.success
                : COLORS.warning,
            }}
            data-testid="iva-f24-documento"
          >
            <div style={STILI.bloccoTitolo}>Documento F24 del commercialista</div>
            <div style={{ ...STILI.riepilogo, borderBottom: 'none' }}>
              <div style={STILI.voce}>
                <span style={STILI.voceLabel}>Codice tributo</span>
                <strong>{dashboard.versamento_iva.codice_tributo}</strong>
              </div>
              <div style={STILI.voce}>
                <span style={STILI.voceLabel}>Scadenza</span>
                <strong>{formatDateIT(dashboard.versamento_iva.scadenza)}</strong>
              </div>
              <div style={STILI.voce}>
                <span style={STILI.voceLabel}>F24 trovato</span>
                <strong>{dashboard.versamento_iva.f24_trovati || 0}</strong>
              </div>
              <div style={STILI.voce}>
                <span style={STILI.voceLabel}>Importo IVA nel F24</span>
                <strong>
                  {dashboard.versamento_iva.f24?.importo_iva == null
                    ? '—'
                    : euroOppure(dashboard.versamento_iva.f24.importo_iva)}
                </strong>
              </div>
              <div style={STILI.voce}>
                <span style={STILI.voceLabel}>Stato documento</span>
                <Badge variant={dashboard.versamento_iva.f24_trovati === 1 ? 'success' : 'warning'}>
                  {dashboard.versamento_iva.f24_trovati === 1
                    ? 'F24 acquisito'
                    : dashboard.versamento_iva.f24_trovati > 1
                      ? 'Associazione ambigua'
                      : 'In attesa dalla posta'}
                </Badge>
              </div>
            </div>
            {dashboard.versamento_iva.f24_trovati > 1 && (
              <div style={STILI.msgErr} role="alert">
                Più F24 trovati per lo stesso codice e anno: associazione ambigua, non sommare automaticamente.
              </div>
            )}
          </div>
        )}

        {!liquidazione ? (
          <div style={STILI.vuoto}>
            Nessuna liquidazione per {MESI_FULL[mese]} {anno}. Premi «Calcola» per crearla.
          </div>
        ) : (
          <div>
            <div style={STILI.riepilogo}>
              <div style={STILI.voce}>
                <span style={STILI.voceLabel}>Stato</span>
                <Badge variant={(STATO_LIQ[liquidazione.stato] || STATO_LIQ.BOZZA).variant}>
                  {(STATO_LIQ[liquidazione.stato] || {}).label || liquidazione.stato}
                </Badge>
              </div>
              <div style={STILI.voce}>
                <span style={STILI.voceLabel}>IVA vendite</span>
                <strong>{euroOppure(liquidazione.iva_vendite)}</strong>
              </div>
              <div style={STILI.voce}>
                <span style={STILI.voceLabel}>IVA acquisti</span>
                <strong>{euroOppure(liquidazione.iva_acquisti)}</strong>
              </div>
              <div style={STILI.voce}>
                <span style={STILI.voceLabel}>Credito precedente</span>
                <strong>{euroOppure(liquidazione.credito_precedente)}</strong>
              </div>
              <div style={STILI.voce}>
                <span style={STILI.voceLabel}>
                  {liquidazione.saldo >= 0 ? 'IVA a debito' : 'IVA a credito'}
                </span>
                <strong style={{ color: liquidazione.saldo >= 0 ? COLORS.danger : COLORS.success }}>
                  {formatEuro(Math.abs(liquidazione.saldo))}
                </strong>
              </div>
              <div style={STILI.voce}>
                <span style={STILI.voceLabel}>Versione</span>
                <strong>#{liquidazione.versione}</strong>
              </div>
            </div>

            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 8 }}>
              <div style={{ flex: '1 1 280px' }}>
                <div style={STILI.bloccoTitolo}>
                  Fatture incluse ({(liquidazione.fatture_incluse || []).length})
                </div>
                {(liquidazione.fatture_incluse || []).length === 0 ? (
                  <div style={STILI.miniVuoto}>Nessuna fattura inclusa.</div>
                ) : (
                  (liquidazione.fatture_incluse || []).map((f, i) => (
                    <div key={f.id || i} style={STILI.rigaMini}>
                      <span>{f.supplier_name || '—'} · {f.invoice_number || '—'}</span>
                      <strong>{euroOppure(f.iva)}</strong>
                    </div>
                  ))
                )}
              </div>
              <div style={{ flex: '1 1 280px' }}>
                <div style={STILI.bloccoTitolo}>
                  Fatture escluse ({(liquidazione.fatture_escluse || []).length})
                </div>
                {(liquidazione.fatture_escluse || []).length === 0 ? (
                  <div style={STILI.miniVuoto}>Nessuna esclusione.</div>
                ) : (
                  (liquidazione.fatture_escluse || []).map((f, i) => (
                    <div key={f.id || i} style={STILI.rigaMini}>
                      <span>{f.supplier_name || f.invoice_number || '—'}</span>
                      <em style={{ fontSize: 11, color: COLORS.textMuted }}>{f.motivo_esclusione}</em>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </div>}

      {/* ── Riepilogo annuale + anomalie (Fase 4) ─────────────────────── */}
      {vistaAnnuale && riepilogo && (
        <div style={STILI.sezione} data-testid="riepilogo-annuale">
          <h3 style={STILI.sezioneTitolo}>
            <Wallet size={18} style={{ color: COLORS.primary }} /> Riepilogo annuale {anno}
          </h3>
          <div style={STILI.riepilogo}>
            {[
              ['Utilizzata', 'utilizzata'],
              ['Non utilizzata', 'non_utilizzata'],
              ['Rinviata', 'rinviata'],
              ['Indetraibile', 'indetraibile'],
              ['Rettificata', 'rettificata'],
              ['Recuperata annuale', 'recuperata_annualmente'],
              ['Da verificare', 'da_verificare'],
            ].map(([label, key]) => (
              <div key={key} style={STILI.voce}>
                <span style={STILI.voceLabel}>{label}</span>
                <strong>{euroOppure(riepilogo.categorie?.[key]?.iva)}</strong>
                <span style={{ fontSize: 11, color: COLORS.textMuted }}>
                  {riepilogo.categorie?.[key]?.conteggio || 0} fatt.
                </span>
              </div>
            ))}
          </div>
          <div style={{ ...STILI.riepilogo, borderTop: 'none' }}>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>IVA vendite</span>
              <strong>{euroOppure(riepilogo.calcolo_annuale?.iva_vendite)}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>IVA detraibile annuale</span>
              <strong>{euroOppure(riepilogo.calcolo_annuale?.iva_detraibile_annuale)}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Debito finale</span>
              <strong style={{ color: COLORS.danger }}>
                {euroOppure(riepilogo.calcolo_annuale?.debito_finale)}
              </strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Credito finale</span>
              <strong style={{ color: COLORS.success }}>
                {euroOppure(riepilogo.calcolo_annuale?.credito_finale)}
              </strong>
            </div>
          </div>
          {anomalie && (anomalie.totale_bloccanti > 0 || anomalie.totale_avvisi > 0) && (
            <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
              {anomalie.totale_bloccanti > 0 && (
                <Badge variant="danger">{anomalie.totale_bloccanti} anomalie bloccanti</Badge>
              )}
              {anomalie.totale_avvisi > 0 && (
                <Badge variant="warning">{anomalie.totale_avvisi} avvisi</Badge>
              )}
            </div>
          )}
        </div>
      )}

      <ConfrontoIvaCommercialista
        anno={anno}
        dati={confrontoCommercialista}
        loading={controlliLoading}
        error={controlliError.confronto}
      />
      <ScadenzeIvaMensili
        anno={anno}
        dati={scadenzeMensili}
        loading={controlliLoading}
        error={controlliError.scadenze}
      />
    </PageLayout>
  );
}

function MostraAltre({ testId, rimanenti, inCorso, onClick }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', marginTop: 12 }}>
      <Button
        variant="secondary"
        data-testid={testId}
        onClick={onClick}
        disabled={inCorso}
        style={{ minHeight: 44 }}
      >
        {inCorso
          ? 'Caricamento…'
          : `Mostra altre ${Math.min(RIGHE_PER_PAGINA, rimanenti)} · ${rimanenti.toLocaleString('it-IT')} rimanenti`}
      </Button>
    </div>
  );
}

const STILI = {
  barra: {
    display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center',
    background: COLORS.card, border: `1px solid ${COLORS.border}`,
    borderRadius: 10, padding: 14, marginBottom: 12,
  },
  percorso: {
    display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12,
    padding: 10, background: COLORS.bgAlt, border: `1px solid ${COLORS.border}`,
    borderRadius: 10,
  },
  percorsoLink: {
    color: COLORS.primary, textDecoration: 'none', fontSize: 12, fontWeight: 700,
    padding: '6px 9px', background: COLORS.card, border: `1px solid ${COLORS.border}`,
    borderRadius: 7,
  },
  totale: { display: 'flex', alignItems: 'center', gap: 10 },
  msg: { padding: '8px 12px', borderRadius: 8, fontSize: 13, marginBottom: 12 },
  msgOk: { background: '#e2f0e7', color: '#166534', border: '1px solid #86efac' },
  msgErr: { background: '#f8e5e2', color: '#b0362b', border: '1px solid #fca5a5' },
  vuoto: { padding: 32, textAlign: 'center', color: COLORS.textMuted },
  tabella: { width: '100%', borderCollapse: 'collapse', background: COLORS.card, fontSize: 13 },
  th: {
    textAlign: 'left', padding: '10px 12px', background: COLORS.bgAlt,
    color: COLORS.textMuted, fontSize: 11, textTransform: 'uppercase',
    fontWeight: 700, whiteSpace: 'nowrap',
  },
  td: { padding: '10px 12px', color: COLORS.text, whiteSpace: 'nowrap' },
  sezione: {
    background: COLORS.card, border: `1px solid ${COLORS.border}`,
    borderRadius: 10, padding: 14, marginTop: 16,
  },
  sezioneTitolo: {
    display: 'flex', alignItems: 'center', gap: 8, margin: '0 0 12px',
    fontSize: 16, fontWeight: 700, color: COLORS.text,
  },
  campo: { display: 'flex', flexDirection: 'column', gap: 4 },
  campoLabel: { fontSize: 11, color: COLORS.textMuted, textTransform: 'uppercase', fontWeight: 700 },
  select: {
    padding: '8px 10px', borderRadius: 8, border: `1px solid ${COLORS.border}`,
    background: COLORS.card, color: COLORS.text, fontSize: 14, minWidth: 120,
  },
  input: {
    padding: '8px 10px', borderRadius: 8, border: `1px solid ${COLORS.border}`,
    background: COLORS.card, color: COLORS.text, fontSize: 14, width: 140,
  },
  riepilogo: {
    display: 'flex', flexWrap: 'wrap', gap: 16, padding: '12px 0',
    borderTop: `1px solid ${COLORS.border}`, borderBottom: `1px solid ${COLORS.border}`,
  },
  voce: { display: 'flex', flexDirection: 'column', gap: 4, minWidth: 110 },
  voceLabel: { fontSize: 11, color: COLORS.textMuted },
  bloccoTitolo: {
    fontSize: 12, fontWeight: 700, color: COLORS.textMuted,
    textTransform: 'uppercase', margin: '10px 0 6px',
  },
  rigaMini: {
    display: 'flex', justifyContent: 'space-between', gap: 8, padding: '6px 0',
    borderTop: `1px solid ${COLORS.border}`, fontSize: 13, color: COLORS.text,
  },
  miniVuoto: { fontSize: 13, color: COLORS.textMuted, padding: '6px 0' },
};

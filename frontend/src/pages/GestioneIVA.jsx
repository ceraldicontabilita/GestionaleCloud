import React, { useEffect, useMemo, useState } from 'react';
import { RefreshCw, Wallet, Calculator, CheckCircle2, Unlock } from 'lucide-react';
import { Link } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, formatDateIT, COLORS, MESI_FULL } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { Button, Badge } from '../components/ds';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { ConfrontoIvaCommercialista, ScadenzeIvaMensili, giornoIT } from './iva/IvaAuditSections';
import './GestioneIVA.css';

/**
 * Gestione IVA — Fase 1: "IVA disponibile non ancora utilizzata"
 * (SPECIFICA_IVA.md §14). Mostra le fatture di acquisto la cui IVA è stata
 * attribuita per competenza ma non ancora inserita in una liquidazione, con
 * il periodo attribuito e la regola applicata. Le liquidazioni mensili
 * persistite arrivano nelle fasi successive.
 */
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
      const [r, a] = await Promise.all([
        api.get(`/api/iva/riepilogo-annuale/${anno}`),
        api.get(`/api/iva/anomalie?anno=${anno}`),
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
    api.get(`/api/iva/dashboard/${anno}/${mese}`)
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
      message: `Confermare IVA vendite ${formatEuro(liquidazione.iva_vendite)}, IVA acquisti ${formatEuro(liquidazione.iva_acquisti)} e ${liquidazione.fatture_incluse?.length || 0} fatture? Dopo la conferma l'IVA viene marcata come utilizzata.`,
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
      setMsg({ tipo: 'errore', testo: 'Errore conferma: ' + (e.response?.data?.detail || e.message) });
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

  const carica = async () => {
    setLoading(true);
    setErrorePeriodo('');
    // Un cambio di mese/anno non deve lasciare visibili i valori del periodo
    // precedente sotto la nuova intestazione mentre la richiesta e' in corso
    // o se una delle due fonti fallisce.
    setDati(null);
    setCorrispettivi([]);
    try {
      const start = vistaAnnuale
        ? `${anno}-01-01`
        : `${anno}-${String(mese).padStart(2, '0')}-01`;
      const end = vistaAnnuale
        ? `${anno}-12-31`
        : `${anno}-${String(mese).padStart(2, '0')}-${String(new Date(anno, mese, 0).getDate()).padStart(2, '0')}`;
      const fattureUrl = vistaAnnuale
        ? `/api/iva/fatture?anno=${anno}&limit=5000`
        : `/api/iva/fatture?periodo=${periodo}&limit=5000`;
      const [fattureRes, corrispettiviRes] = await Promise.all([
        api.get(fattureUrl),
        api.get(`/api/corrispettivi?data_da=${start}&data_a=${end}&limit=5000`),
      ]);
      setDati(fattureRes.data);
      setCorrispettivi(Array.isArray(corrispettiviRes.data) ? corrispettiviRes.data : []);
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
  const numero = valore => Number(valore || 0);
  const corrispettiviUnici = useMemo(() => {
    const visti = new Set();
    return corrispettivi.filter((c) => {
      const totaleCents = Math.round(numero(c.totale ?? c.totale_complessivo) * 100);
      const chiave = String(c.corrispettivo_key || '').trim() || [
        c.data || c.data_rilevazione || '',
        c.matricola_rt || c.id_dispositivo || c.matricola || '',
        totaleCents,
      ].join('|');
      if (visti.has(chiave)) return false;
      visti.add(chiave);
      return true;
    });
  }, [corrispettivi]);
  const duplicatiCorrispettiviEsclusi = corrispettivi.length - corrispettiviUnici.length;
  const totaliCorrispettivi = corrispettiviUnici.reduce(
    (acc, c) => {
      const totale = numero(c.totale ?? c.totale_complessivo);
      const iva = numero(c.totale_iva ?? c.iva);
      acc.totale += totale;
      acc.iva += iva;
      acc.imponibile += numero(c.totale_imponibile ?? c.imponibile ?? (totale - iva));
      acc.contanti += numero(c.pagato_contanti);
      acc.elettronico += numero(c.pagato_elettronico ?? c.pagato_pos);
      return acc;
    },
    { totale: 0, imponibile: 0, iva: 0, contanti: 0, elettronico: 0 }
  );
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
          return aliquota == null ? null : `${aliquota}%: ${formatEuro(iva || 0)}`;
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
    <PageLayout title="Gestione IVA" icon="📊" subtitle={`Attribuzione, liquidazione, F24 e scadenze — ${anno}`}>
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
              : `${fatture.length} fatture · ${corrispettiviUnici.length} giornate XML`}
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
          <div><span>Fatture nel periodo</span><strong>{dati?.totale ?? fatture.length}</strong></div>
          <div><span>IVA esposta</span><strong>{formatEuro(dati?.totale_iva_esposta || 0)}</strong></div>
          <div><span>IVA detraibile</span><strong>{formatEuro(dati?.totale_iva_detraibile || 0)}</strong></div>
          <div data-testid="iva-totale-disponibile"><span>Ancora disponibile</span><strong>{formatEuro(dati?.totale_iva_disponibile || 0)}</strong></div>
          <div><span>IVA corrispettivi</span><strong>{formatEuro(totaliCorrispettivi.iva)}</strong></div>
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
            {errorePeriodo ? 'Non disponibile' : `${dati?.totale ?? fatture.length} fatture`}
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
                        {formatEuro(f.iva_esposta ?? 0)}
                      </td>
                      <td data-label="Detraibilità IVA" style={{ ...STILI.td, textAlign: 'right', fontWeight: 700 }}>
                        {etichettaPercentuale(f)}
                      </td>
                      <td data-label="IVA detraibile" style={{ ...STILI.td, textAlign: 'right', fontWeight: 700 }}>
                        {formatEuro(f.iva_detraibile ?? 0)}
                      </td>
                      <td data-label="Stato" style={STILI.td}>
                        <Badge variant={st.variant}>{st.label}</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
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
              {errorePeriodo ? 'Non disponibile' : `${corrispettiviUnici.length} giornate`}
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
                    <td data-label="Imponibile" style={{ ...STILI.td, textAlign: 'right' }}>{formatEuro(c.totale_imponibile ?? c.imponibile ?? 0)}</td>
                    <td data-label="IVA" style={{ ...STILI.td, textAlign: 'right', fontWeight: 700 }}>{formatEuro(c.totale_iva ?? c.iva ?? 0)}</td>
                    <td data-label="Totale" style={{ ...STILI.td, textAlign: 'right', fontWeight: 700 }}>{formatEuro(c.totale ?? c.totale_complessivo ?? 0)}</td>
                    <td data-label="Contanti" style={{ ...STILI.td, textAlign: 'right' }}>{formatEuro(c.pagato_contanti ?? c.contanti ?? 0)}</td>
                    <td data-label="Elettronico" style={{ ...STILI.td, textAlign: 'right' }}>{formatEuro(c.pagato_elettronico ?? c.elettronico ?? c.pagato_pos ?? 0)}</td>
                    <td data-label="Aliquote IVA" style={{ ...STILI.td, fontSize: 12, color: COLORS.textMuted }}>{riepilogoAliquote(c)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan="2" style={STILI.th}>Totale periodo</td>
                  <td style={{ ...STILI.th, textAlign: 'right' }}>{formatEuro(totaliCorrispettivi.imponibile)}</td>
                  <td style={{ ...STILI.th, textAlign: 'right' }}>{formatEuro(totaliCorrispettivi.iva)}</td>
                  <td style={{ ...STILI.th, textAlign: 'right' }}>{formatEuro(totaliCorrispettivi.totale)}</td>
                  <td style={{ ...STILI.th, textAlign: 'right' }}>{formatEuro(totaliCorrispettivi.contanti)}</td>
                  <td style={{ ...STILI.th, textAlign: 'right' }}>{formatEuro(totaliCorrispettivi.elettronico)}</td>
                  <td />
                </tr>
              </tfoot>
            </table>
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
              <strong>{formatEuro(dashboard.iva_acquisti_attribuita || 0)}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Ricevuta ma competenza mese prec.</span>
              <strong>{formatEuro(dashboard.iva_ricevuta_attribuita_mese_precedente || 0)}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Utilizzata</span>
              <strong>{formatEuro(dashboard.iva_utilizzata || 0)}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Non utilizzata</span>
              <strong>{formatEuro(dashboard.iva_non_utilizzata || 0)}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Rinviata</span>
              <strong>{formatEuro(dashboard.iva_rinviata || 0)}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Indetraibile</span>
              <strong>{formatEuro(dashboard.iva_indetraibile || 0)}</strong>
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
                    : formatEuro(dashboard.versamento_iva.f24.importo_iva)}
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
                <strong>{formatEuro(liquidazione.iva_vendite)}</strong>
              </div>
              <div style={STILI.voce}>
                <span style={STILI.voceLabel}>IVA acquisti</span>
                <strong>{formatEuro(liquidazione.iva_acquisti)}</strong>
              </div>
              <div style={STILI.voce}>
                <span style={STILI.voceLabel}>Credito precedente</span>
                <strong>{formatEuro(liquidazione.credito_precedente)}</strong>
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
                      <strong>{formatEuro(f.iva)}</strong>
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
                <strong>{formatEuro(riepilogo.categorie?.[key]?.iva || 0)}</strong>
                <span style={{ fontSize: 11, color: COLORS.textMuted }}>
                  {riepilogo.categorie?.[key]?.conteggio || 0} fatt.
                </span>
              </div>
            ))}
          </div>
          <div style={{ ...STILI.riepilogo, borderTop: 'none' }}>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>IVA vendite</span>
              <strong>{formatEuro(riepilogo.calcolo_annuale?.iva_vendite || 0)}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>IVA detraibile annuale</span>
              <strong>{formatEuro(riepilogo.calcolo_annuale?.iva_detraibile_annuale || 0)}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Debito finale</span>
              <strong style={{ color: COLORS.danger }}>
                {formatEuro(riepilogo.calcolo_annuale?.debito_finale || 0)}
              </strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Credito finale</span>
              <strong style={{ color: COLORS.success }}>
                {formatEuro(riepilogo.calcolo_annuale?.credito_finale || 0)}
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
  msgOk: { background: '#dcfce7', color: '#166534', border: '1px solid #86efac' },
  msgErr: { background: '#fee2e2', color: '#b91c1c', border: '1px solid #fca5a5' },
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

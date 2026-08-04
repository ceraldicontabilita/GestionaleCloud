import React, { useEffect, useState } from 'react';
import { RefreshCw, Wallet, Calculator, CheckCircle2, Unlock } from 'lucide-react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, formatDateIT, COLORS, MESI_FULL } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { Button, Badge } from '../components/ds';
import { useConfirm } from '../components/ui/ConfirmDialog';
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
  const [loading, setLoading] = useState(true);
  const [ricalcolo, setRicalcolo] = useState(false);
  const [msg, setMsg] = useState(null);

  // Liquidazione mensile (Fase 3)
  const [mese, setMese] = useState(1);
  const [liquidazione, setLiquidazione] = useState(null);
  const [busyLiq, setBusyLiq] = useState(false);
  const periodo = `${anno}-${String(mese).padStart(2, '0')}`;

  // Riepilogo annuale + anomalie (Fase 4)
  const [riepilogo, setRiepilogo] = useState(null);
  const [anomalie, setAnomalie] = useState(null);

  // Dashboard IVA del mese (Fase 5)
  const [dashboard, setDashboard] = useState(null);

  // Calcola pregresso: esito persistente dell'ultimo ricalcolo
  const [ultimoRic, setUltimoRic] = useState(null);

  const caricaUltimoRic = async () => {
    try {
      const res = await api.get('/api/iva/ricalcola-attribuzione/ultimo');
      setUltimoRic(res.data?.ultimo || null);
    } catch (e) {
      setUltimoRic(null);
      setMsg({ tipo: 'errore', testo: 'Impossibile caricare l\'ultimo ricalcolo IVA: ' + (e.response?.data?.detail || e.message) });
    }
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
    try {
      const res = await api.get(`/api/iva/fatture/non-utilizzate?anno=${anno}`);
      setDati(res.data);
    } catch (e) {
      setMsg({ tipo: 'errore', testo: 'Errore: ' + (e.response?.data?.detail || e.message) });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    carica();
  }, [anno]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    caricaLiquidazione();
  }, [anno, mese]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    caricaRiepilogo();
    caricaUltimoRic();
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
      setUltimoRic(r);
      await carica();
      await caricaRiepilogo();
    } catch (e) {
      setMsg({ tipo: 'errore', testo: 'Errore ricalcolo: ' + (e.response?.data?.detail || e.message) });
    } finally {
      setRicalcolo(false);
    }
  };

  const fatture = dati?.fatture || [];

  return (
    <PageLayout title="Gestione IVA" icon="📊" subtitle={`IVA disponibile non utilizzata — ${anno}`}>
      <div style={STILI.barra}>
        <div style={STILI.totale} data-testid="iva-totale-disponibile">
          <Wallet size={20} style={{ color: COLORS.primary }} />
          <div>
            <div style={{ fontSize: 12, color: COLORS.textMuted }}>IVA disponibile non utilizzata</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: COLORS.primary }}>
              {formatEuro(dati?.totale_iva_disponibile || 0)}
            </div>
          </div>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <Button variant="secondary" onClick={carica} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} /> Aggiorna
          </Button>
        </div>
      </div>

      {/* ── Calcola pregresso (persistente) ───────────────────────────── */}
      <div style={STILI.sezione} data-testid="calcola-pregresso">
        <h3 style={STILI.sezioneTitolo}>
          <Calculator size={18} style={{ color: COLORS.primary }} /> Calcola pregresso
        </h3>
        <p style={{ fontSize: 13, color: COLORS.textMuted, margin: '0 0 10px' }}>
          Rilegge tutte le fatture di acquisto e ricalcola l'IVA per competenza
          (periodo, regola, stato). Non tocca l'IVA già usata in una liquidazione
          confermata. L'esito qui sotto resta memorizzato: sai sempre quante
          fatture sono state lette e attribuite.
        </p>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
          <Button
            variant="primary"
            onClick={() => ricalcolaAttribuzione(true)}
            disabled={ricalcolo}
            data-testid="iva-ricalcola-tutto"
          >
            {ricalcolo ? 'Calcolo in corso…' : 'Calcola tutto il pregresso'}
          </Button>
          <Button
            variant="secondary"
            onClick={() => ricalcolaAttribuzione(false)}
            disabled={ricalcolo}
            data-testid="iva-ricalcola-anno"
          >
            Solo {anno}
          </Button>
        </div>
        {ultimoRic ? (
          <div style={STILI.riepilogo} data-testid="ultimo-ricalcolo">
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Fatture lette</span>
              <strong>{ultimoRic.lette ?? 0}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Attribuite</span>
              <strong>{ultimoRic.con_periodo ?? 0}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Da verificare</span>
              <strong style={{ color: (ultimoRic.da_verificare || 0) > 0 ? COLORS.danger : COLORS.text }}>
                {ultimoRic.da_verificare ?? 0}
              </strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Aggiornate</span>
              <strong>{ultimoRic.modificate ?? 0}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Già utilizzate</span>
              <strong>{ultimoRic.gia_utilizzate ?? 0}</strong>
            </div>
            <div style={STILI.voce}>
              <span style={STILI.voceLabel}>Ultimo calcolo</span>
              <strong style={{ fontSize: 12 }}>{formatDateIT(ultimoRic.eseguito_il)}</strong>
            </div>
          </div>
        ) : (
          <div style={STILI.miniVuoto}>
            Nessun ricalcolo eseguito finora. Premi «Calcola tutto il pregresso».
          </div>
        )}
        {ultimoRic?.per_anno && Object.keys(ultimoRic.per_anno).length > 0 && (
          <div style={{ marginTop: 8, fontSize: 12, color: COLORS.textMuted }}>
            Attribuite per anno:{' '}
            {Object.entries(ultimoRic.per_anno)
              .sort()
              .map(([a, n]) => `${a}: ${n}`)
              .join(' · ')}
          </div>
        )}
      </div>

      {msg && (
        <div
          role={msg.tipo === 'ok' ? 'status' : 'alert'}
          aria-live="polite"
          style={{ ...STILI.msg, ...(msg.tipo === 'ok' ? STILI.msgOk : STILI.msgErr) }}
        >
          {msg.testo}
        </div>
      )}

      {loading ? (
        <div style={STILI.vuoto}>Caricamento…</div>
      ) : fatture.length === 0 ? (
        <div style={STILI.vuoto}>
          Nessuna IVA disponibile non utilizzata per il {anno}. Se hai appena importato
          fatture vecchie, premi «Ricalcola attribuzione».
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="iva-responsive-table" style={STILI.tabella} data-testid="iva-tabella">
            <thead>
              <tr>
                <th style={STILI.th}>Fornitore</th>
                <th style={STILI.th}>N. fattura</th>
                <th style={STILI.th}>Data doc.</th>
                <th style={STILI.th}>Ricezione</th>
                <th style={STILI.th}>Periodo IVA</th>
                <th style={STILI.th}>Regola</th>
                <th style={{ ...STILI.th, textAlign: 'right' }}>IVA</th>
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
                    <td data-label="Ricezione" style={STILI.td}>{formatDateIT(f.data_ricezione)}</td>
                    <td data-label="Periodo IVA" style={STILI.td}>
                      <strong>{f.periodo_iva_attribuito || '—'}</strong>
                    </td>
                    <td data-label="Regola" style={{ ...STILI.td, fontSize: 12, color: COLORS.textMuted }}>
                      {REGOLA_LABEL[f.regola_iva_applicata] || f.regola_iva_applicata || '—'}
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

      {/* ── Liquidazione mensile (Fase 3) ─────────────────────────────── */}
      <div style={STILI.sezione} data-testid="liquidazione-mensile">
        <h3 style={STILI.sezioneTitolo}>
          <Calculator size={18} style={{ color: COLORS.primary }} /> Liquidazione mensile
        </h3>
        <div style={STILI.barra}>
          <label style={STILI.campo}>
            <span style={STILI.campoLabel}>Mese</span>
            <select
              value={mese}
              onChange={(e) => setMese(Number(e.target.value))}
              style={STILI.select}
              data-testid="liq-mese"
            >
              {MESI_FULL.slice(1).map((m, i) => (
                <option key={i + 1} value={i + 1}>{m}</option>
              ))}
            </select>
          </label>
          <label style={STILI.campo}>
            <span style={STILI.campoLabel}>IVA vendite da corrispettivi XML</span>
            <strong
              style={{ ...STILI.input, display: 'flex', alignItems: 'center' }}
              data-testid="liq-iva-vendite-auto"
            >
              {formatEuro(dashboard?.iva_vendite_corrispettivi || 0)}
            </strong>
          </label>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'flex-end' }}>
            <Button variant="primary" onClick={calcolaLiq} disabled={busyLiq} data-testid="liq-calcola">
              <Calculator size={16} /> Calcola
            </Button>
            {liquidazione && !['CONFERMATA', 'TRASMESSA'].includes(liquidazione.stato) && (
              <Button variant="success" onClick={confermaLiq} disabled={busyLiq} data-testid="liq-conferma">
                <CheckCircle2 size={16} /> Conferma
              </Button>
            )}
            {liquidazione && ['CONFERMATA', 'TRASMESSA'].includes(liquidazione.stato) && (
              <Button variant="secondary" onClick={riapriLiq} disabled={busyLiq} data-testid="liq-riapri">
                <Unlock size={16} /> Riapri
              </Button>
            )}
          </div>
        </div>

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
      </div>

      {/* ── Riepilogo annuale + anomalie (Fase 4) ─────────────────────── */}
      {riepilogo && (
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
    </PageLayout>
  );
}

const STILI = {
  barra: {
    display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center',
    background: COLORS.card, border: `1px solid ${COLORS.border}`,
    borderRadius: 10, padding: 14, marginBottom: 12,
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

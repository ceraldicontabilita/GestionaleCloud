import React, { useState } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout, PageSection } from '../components/PageLayout';
import { AlertTriangle, CheckCircle, Search, Eye, Trash2, RefreshCw, Loader2 } from 'lucide-react';

/**
 * Pagina di manutenzione Prima Nota.
 * Permette di:
 *  1. Diagnosticare lo stato dei corrispettivi rispetto alla Prima Nota Cassa
 *  2. Vedere in anteprima quali fatture risultano duplicate in Cassa/Banca
 *  3. Eseguire il cleanup (soft-delete, reversibile) dei duplicati
 *  4. Risincronizzare i corrispettivi mancanti
 *
 * Tutte le operazioni usano gli endpoint creati con PR #1:
 *  - GET  /api/prima-nota/diagnostica-corrispettivi?anno=N
 *  - POST /api/prima-nota/dedup-fatture?applica=<bool>&anno=N
 *  - POST /api/prima-nota/cassa/sync-corrispettivi?anno=N
 */
export default function PuliziaPrimaNota() {
  const { anno } = useAnnoGlobale();

  const [loading, setLoading] = useState(null); // 'diagnosi' | 'anteprima' | 'pulisci' | 'risincronizza' | 'auto-conferma'
  const [diagnosi, setDiagnosi] = useState(null);
  const [anteprima, setAnteprima] = useState(null);
  const [risultatoPulizia, setRisultatoPulizia] = useState(null);
  const [risultatoSync, setRisultatoSync] = useState(null);
  const [risultatoAutoConferma, setRisultatoAutoConferma] = useState(null);
  const [errore, setErrore] = useState(null);

  const azzeraErrori = () => setErrore(null);

  const lanciaDiagnosi = async () => {
    azzeraErrori();
    setLoading('diagnosi');
    try {
      const res = await api.get(`/api/prima-nota/diagnostica-corrispettivi?anno=${anno}`);
      setDiagnosi(res.data);
    } catch (e) {
      setErrore(e?.response?.data?.detail || e?.message || 'Errore durante la diagnosi');
    } finally {
      setLoading(null);
    }
  };

  const lanciaAnteprima = async () => {
    azzeraErrori();
    setLoading('anteprima');
    try {
      const res = await api.post(`/api/prima-nota/dedup-fatture?applica=false&anno=${anno}`);
      setAnteprima(res.data);
    } catch (e) {
      setErrore(e?.response?.data?.detail || e?.message || 'Errore durante l\'anteprima');
    } finally {
      setLoading(null);
    }
  };

  const lanciaPulizia = async () => {
    const totaleDaEliminare =
      (anteprima?.cassa?.movimenti_da_eliminare || 0) +
      (anteprima?.banca?.movimenti_da_eliminare || 0);

    const conferma = window.confirm(
      `Stai per marcare come eliminati ${totaleDaEliminare} movimenti duplicati ` +
      `(${anteprima?.cassa?.movimenti_da_eliminare || 0} in Cassa, ${anteprima?.banca?.movimenti_da_eliminare || 0} in Banca).\n\n` +
      `Verranno contrassegnati come "deleted" (soft-delete). Non vengono cancellati fisicamente: ` +
      `resteranno nel database e potranno essere ripristinati da un tecnico se qualcosa andasse storto.\n\n` +
      `Procedere?`
    );
    if (!conferma) return;

    azzeraErrori();
    setLoading('pulisci');
    try {
      const res = await api.post(`/api/prima-nota/dedup-fatture?applica=true&anno=${anno}`);
      setRisultatoPulizia(res.data);
      // dopo la pulizia, azzero l'anteprima così l'utente non clicca di nuovo per sbaglio
      setAnteprima(null);
    } catch (e) {
      setErrore(e?.response?.data?.detail || e?.message || 'Errore durante la pulizia');
    } finally {
      setLoading(null);
    }
  };

  const lanciaRisincronizzazione = async () => {
    azzeraErrori();
    setLoading('risincronizza');
    try {
      const res = await api.post(`/api/prima-nota/cassa/sync-corrispettivi?anno=${anno}`);
      setRisultatoSync(res.data);
    } catch (e) {
      setErrore(e?.response?.data?.detail || e?.message || 'Errore durante la risincronizzazione');
    } finally {
      setLoading(null);
    }
  };

  const lanciaAutoConferma = async () => {
    const conferma = window.confirm(
      `Smistamento provvisorie per metodo fornitore — anno ${anno}\n\n` +
      `Verranno spostate dalla Provvisoria a Prima Nota Cassa/Banca le fatture in base al metodo pagamento del fornitore:\n` +
      `• Fornitore CASSA → tutte le fatture in Prima Nota Cassa\n` +
      `• Fornitore BANCA → solo fatture PAGATE in Prima Nota Banca\n` +
      `• Fornitore PAYPAL/CARTA/senza metodo → restano in Provvisoria\n\n` +
      `Ogni movimento creato è annullabile con un solo comando se qualcosa non torna.\n\n` +
      `Procedere?`
    );
    if (!conferma) return;
    azzeraErrori();
    setLoading('auto-conferma');
    setRisultatoAutoConferma(null);
    try {
      const res = await api.post(`/api/prima-nota/provvisori/auto-conferma-per-metodo?anno=${anno}`);
      setRisultatoAutoConferma(res.data);
    } catch (e) {
      setErrore(e?.response?.data?.detail || e?.message || 'Errore durante lo smistamento');
    } finally {
      setLoading(null);
    }
  };

  const isBusy = loading !== null;

  return (
    <PageLayout>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: '#0f2744' }}>
          🧹 Pulizia Prima Nota
        </h2>
        <div style={{ fontSize: 13, color: '#6b7280', marginTop: 2 }}>
          Manutenzione dati Prima Nota Cassa e Banca · Anno {anno}
        </div>
      </div>
      <PageSection>
        <div style={{
          background: '#fffbeb', border: '1px solid #fbbf24', borderRadius: 8,
          padding: 16, marginBottom: 20, display: 'flex', gap: 12,
        }}>
          <AlertTriangle size={20} color="#d97706" style={{ flexShrink: 0, marginTop: 2 }} />
          <div style={{ fontSize: 14, color: '#78350f', lineHeight: 1.5 }}>
            <strong>Come si usa questa pagina.</strong>
            <br />
            I pulsanti vanno premuti <em>nell'ordine in cui appaiono</em>. Prima controlli
            cosa c'è da sistemare (1 e 2), poi esegui la pulizia (3), infine risincronizzi
            eventuali corrispettivi mancanti (4). Nessun dato viene cancellato davvero:
            i duplicati vengono solo <em>nascosti</em> e restano recuperabili dal database.
          </div>
        </div>

        {errore && (
          <div style={{
            background: '#fef2f2', border: '1px solid #dc2626', borderRadius: 8,
            padding: 12, marginBottom: 16, color: '#991b1b', fontSize: 14,
          }}>
            <strong>Errore:</strong> {typeof errore === 'string' ? errore : JSON.stringify(errore)}
          </div>
        )}

        {/* STEP 1 - DIAGNOSI CORRISPETTIVI */}
        <StepCard
          numero={1}
          titolo="Diagnosi corrispettivi"
          descrizione="Controlla quanti corrispettivi mancano in Prima Nota Cassa e perché."
        >
          <button
            onClick={lanciaDiagnosi}
            disabled={isBusy}
            style={btnStyle('primary', isBusy)}
          >
            {loading === 'diagnosi' ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
            Esegui diagnosi
          </button>

          {diagnosi && (
            <div style={resultBoxStyle}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, marginBottom: 12 }}>
                <Stat label="Corrispettivi sorgente" value={diagnosi.corrispettivi_sorgente} />
                <Stat label="Già in Prima Nota" value={diagnosi.corrispettivi_in_cassa} color="#059669" />
                <Stat label="Mancanti in Cassa" value={diagnosi.mancanti_in_cassa} color={diagnosi.mancanti_in_cassa > 0 ? '#d97706' : '#059669'} />
                <Stat label="Non sincronizzabili (importo 0)" value={diagnosi.non_sincronizzabili_importo_zero} color={diagnosi.non_sincronizzabili_importo_zero > 0 ? '#dc2626' : '#6b7280'} />
                <Stat label="Duplicati in Cassa" value={diagnosi.duplicati_in_cassa} color={diagnosi.duplicati_in_cassa > 0 ? '#dc2626' : '#059669'} />
              </div>
              {diagnosi.mancanti_in_cassa > 0 && (
                <div style={{ fontSize: 13, color: '#78350f', background: '#fffbeb', padding: 8, borderRadius: 6 }}>
                  Ci sono <strong>{diagnosi.mancanti_in_cassa}</strong> corrispettivi non ancora in Prima Nota Cassa.
                  Puoi recuperarli con il pulsante al passo 4.
                </div>
              )}
              {diagnosi.non_sincronizzabili_importo_zero > 0 && (
                <div style={{ fontSize: 13, color: '#991b1b', background: '#fef2f2', padding: 8, borderRadius: 6, marginTop: 6 }}>
                  Attenzione: <strong>{diagnosi.non_sincronizzabili_importo_zero}</strong> corrispettivi
                  hanno importo 0 su tutti i campi noti e non possono essere sincronizzati automaticamente.
                  Vanno corretti a mano nella sezione Corrispettivi.
                </div>
              )}
            </div>
          )}
        </StepCard>

        {/* STEP 2 - ANTEPRIMA DUPLICATI */}
        <StepCard
          numero={2}
          titolo="Anteprima duplicati fatture"
          descrizione="Mostra quali fatture risultano duplicate in Prima Nota Cassa e Banca. Non modifica niente."
        >
          <button
            onClick={lanciaAnteprima}
            disabled={isBusy}
            style={btnStyle('primary', isBusy)}
          >
            {loading === 'anteprima' ? <Loader2 size={16} className="animate-spin" /> : <Eye size={16} />}
            Mostra anteprima
          </button>

          {anteprima && (
            <div style={resultBoxStyle}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Prima Nota Cassa</div>
                  <Stat label="Gruppi duplicati" value={anteprima.cassa?.gruppi_duplicati || 0} />
                  <Stat label="Movimenti da rimuovere" value={anteprima.cassa?.movimenti_da_eliminare || 0} color="#dc2626" />
                </div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Prima Nota Banca</div>
                  <Stat label="Gruppi duplicati" value={anteprima.banca?.gruppi_duplicati || 0} />
                  <Stat label="Movimenti da rimuovere" value={anteprima.banca?.movimenti_da_eliminare || 0} color="#dc2626" />
                </div>
              </div>
              <div style={{ marginTop: 12, fontSize: 12, color: '#6b7280', fontStyle: 'italic' }}>
                {anteprima.nota}
              </div>
            </div>
          )}
        </StepCard>

        {/* STEP 3 - ESEGUI PULIZIA */}
        <StepCard
          numero={3}
          titolo="Esegui pulizia duplicati"
          descrizione="Marca come eliminati i duplicati trovati al passo 2. Esegui prima il passo 2!"
          disabledReason={!anteprima ? 'Esegui prima l\'anteprima (passo 2)' : null}
        >
          <button
            onClick={lanciaPulizia}
            disabled={isBusy || !anteprima || (anteprima?.cassa?.movimenti_da_eliminare || 0) + (anteprima?.banca?.movimenti_da_eliminare || 0) === 0}
            style={btnStyle('danger', isBusy || !anteprima)}
          >
            {loading === 'pulisci' ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
            Elimina duplicati
          </button>

          {risultatoPulizia && (
            <div style={{ ...resultBoxStyle, background: '#f0fdf4', borderColor: '#22c55e' }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                <CheckCircle size={18} color="#059669" />
                <strong style={{ color: '#065f46' }}>Pulizia completata</strong>
              </div>
              <div style={{ fontSize: 13, color: '#065f46' }}>
                Eliminati <strong>{risultatoPulizia.cassa?.eliminati_effettivi || 0}</strong> movimenti duplicati da Cassa e{' '}
                <strong>{risultatoPulizia.banca?.eliminati_effettivi || 0}</strong> da Banca.
              </div>
            </div>
          )}
        </StepCard>

        {/* STEP 4 - RISINCRONIZZA CORRISPETTIVI */}
        <StepCard
          numero={4}
          titolo="Risincronizza corrispettivi mancanti"
          descrizione="Recupera i corrispettivi che la diagnosi ha rilevato come mancanti in Prima Nota Cassa."
        >
          <button
            onClick={lanciaRisincronizzazione}
            disabled={isBusy}
            style={btnStyle('primary', isBusy)}
          >
            {loading === 'risincronizza' ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            Risincronizza
          </button>

          {risultatoSync && (
            <div style={{ ...resultBoxStyle, background: '#f0fdf4', borderColor: '#22c55e' }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                <CheckCircle size={18} color="#059669" />
                <strong style={{ color: '#065f46' }}>Sincronizzazione completata</strong>
              </div>
              <div style={{ fontSize: 13, color: '#065f46' }}>
                Inseriti <strong>{risultatoSync.inseriti}</strong> nuovi corrispettivi in Prima Nota Cassa.
                {risultatoSync.duplicati > 0 && <> Già presenti: {risultatoSync.duplicati}.</>}
                {risultatoSync.saltati > 0 && (
                  <div style={{ marginTop: 6, color: '#991b1b' }}>
                    {risultatoSync.saltati} corrispettivi saltati (importo 0 su tutti i campi) — vanno corretti a mano nella sezione Corrispettivi.
                  </div>
                )}
              </div>
            </div>
          )}
        </StepCard>

        {/* STEP 5 - AUTO-CONFERMA PROVVISORI PER METODO PAGAMENTO FORNITORE */}
        <StepCard
          numero={5}
          titolo="Smista fatture provvisorie per metodo fornitore"
          descrizione="Sposta automaticamente le fatture dalla Provvisoria alla Prima Nota Cassa o Banca, in base al metodo pagamento dell'anagrafica fornitore. Le fatture di fornitori senza metodo definito, o con metodo PayPal/Carta, oppure fatture non pagate di fornitori 'banca', restano in Provvisoria."
        >
          <button
            onClick={lanciaAutoConferma}
            disabled={isBusy}
            style={btnStyle('primary', isBusy)}
          >
            {loading === 'auto-conferma' ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            Smista provvisorie
          </button>

          {risultatoAutoConferma && (
            <div style={{ ...resultBoxStyle, background: '#f0fdf4', borderColor: '#22c55e' }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                <CheckCircle size={18} color="#059669" />
                <strong style={{ color: '#065f46' }}>Smistamento completato</strong>
              </div>
              <div style={{ fontSize: 13, color: '#065f46', lineHeight: 1.6 }}>
                Fatture analizzate: <strong>{risultatoAutoConferma.totali_provvisorie_analizzate}</strong>
                <br />
                <span style={{ color: '#15803d' }}>✓ Spostate in Cassa: <strong>{risultatoAutoConferma.mosse_cassa}</strong></span>
                <br />
                <span style={{ color: '#15803d' }}>✓ Spostate in Banca: <strong>{risultatoAutoConferma.mosse_banca}</strong></span>
                <br />
                <span style={{ color: '#78350f' }}>
                  Restate in Provvisoria:{' '}
                  {risultatoAutoConferma.restate_in_provvisoria_banca_non_pagata} (banca non pagate) +{' '}
                  {risultatoAutoConferma.restate_in_provvisoria_paypal_o_carta} (paypal/carta) +{' '}
                  {risultatoAutoConferma.restate_in_provvisoria_fornitore_senza_metodo} (fornitore senza metodo)
                </span>
                {risultatoAutoConferma.skipped_gia_in_prima_nota > 0 && (
                  <>
                    <br />
                    <span style={{ color: '#64748b' }}>
                      Saltate perché già registrate: {risultatoAutoConferma.skipped_gia_in_prima_nota}
                    </span>
                  </>
                )}
                {risultatoAutoConferma.skipped_errori?.length > 0 && (
                  <>
                    <br />
                    <span style={{ color: '#991b1b' }}>
                      ⚠ Errori: {risultatoAutoConferma.skipped_errori.length}
                    </span>
                  </>
                )}
              </div>
            </div>
          )}
        </StepCard>
      </PageSection>
    </PageLayout>
  );
}

// ---------- helper components ----------

function StepCard({ numero, titolo, descrizione, disabledReason, children }) {
  return (
    <div style={{
      border: '1px solid #e5e7eb', borderRadius: 10, padding: 18, marginBottom: 14,
      background: '#fff',
    }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', marginBottom: 12 }}>
        <div style={{
          width: 32, height: 32, borderRadius: '50%', background: '#0f2744',
          color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontWeight: 700, fontSize: 15, flexShrink: 0,
        }}>
          {numero}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 16, fontWeight: 600, color: '#0f2744' }}>{titolo}</div>
          <div style={{ fontSize: 13, color: '#6b7280', marginTop: 2 }}>{descrizione}</div>
          {disabledReason && (
            <div style={{ fontSize: 12, color: '#d97706', marginTop: 4, fontStyle: 'italic' }}>
              {disabledReason}
            </div>
          )}
        </div>
      </div>
      <div style={{ paddingLeft: 44 }}>{children}</div>
    </div>
  );
}

function Stat({ label, value, color = '#0f2744' }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.3 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color }}>{value ?? '—'}</div>
    </div>
  );
}

const resultBoxStyle = {
  marginTop: 12, padding: 12, background: '#f9fafb',
  border: '1px solid #e5e7eb', borderRadius: 8,
};

function btnStyle(variant, disabled) {
  const base = {
    display: 'inline-flex', alignItems: 'center', gap: 8,
    padding: '9px 16px', borderRadius: 8, fontSize: 14, fontWeight: 600,
    border: 'none', cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1, transition: 'all .15s',
  };
  if (variant === 'danger') return { ...base, background: '#dc2626', color: '#fff' };
  return { ...base, background: '#0f2744', color: '#fff' };
}

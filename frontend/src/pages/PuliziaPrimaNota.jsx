import React, { useState } from 'react';
import api from '../api';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout, PageSection } from '../components/PageLayout';
import { formatEuroD } from '../lib/utils';
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
  const confirm = useConfirm();
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

    const conferma = await confirm({
      title: 'Pulizia duplicati Prima Nota',
      message:
        `Stai per marcare come eliminati ${totaleDaEliminare} movimenti duplicati ` +
        `(${anteprima?.cassa?.movimenti_da_eliminare || 0} in Cassa, ${anteprima?.banca?.movimenti_da_eliminare || 0} in Banca). ` +
        `Verranno contrassegnati come "deleted" (soft-delete): restano nel database e sono ripristinabili.`,
      confirmText: 'Procedi',
      variant: 'warning',
    });
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

  // Quadratura corrispettivi da Drive: ripassa TUTTI gli XML archiviati e
  // recupera quelli che risultano mancanti nel gestionale. Bug segnalato
  // dall'utente 15/07/2026 (saldo Prima Nota sballato di decine di
  // migliaia di euro): il controllo duplicati di CorrispettiviService
  // guardava SOLO la data, non il dispositivo/PDV che ha emesso il
  // corrispettivo — con più casse nello stesso negozio, il corrispettivo
  // della seconda cassa veniva scartato come "duplicato" della prima ogni
  // giorno, sparendo del tutto da Prima Nota invece di sommarsi. Corretto
  // nel codice: questo pulsante recupera lo storico ripassando gli XML
  // originali già su Drive (nessun dato perso, si riparte dalla fonte
  // fiscale invece che da un'importazione derivata).
  const [risultatoQuadratura, setRisultatoQuadratura] = useState(null);

  const lanciaQuadraturaCorrispettivi = async () => {
    const conferma = await confirm({
      title: 'Quadratura corrispettivi da Drive',
      message:
        'Ripassa tutti gli XML dei corrispettivi archiviati su Drive e recupera quelli mancanti ' +
        'nel gestionale (es. corrispettivi di una seconda cassa scartati per errore come duplicati). ' +
        'Operazione sicura: non tocca né duplica i corrispettivi già presenti.',
      confirmText: 'Avvia quadratura',
      variant: 'warning',
    });
    if (!conferma) return;
    azzeraErrori();
    setLoading('quadratura');
    setRisultatoQuadratura(null);
    try {
      const res = await api.post('/api/corrispettivi/drive/quadratura');
      setRisultatoQuadratura(res.data);
    } catch (e) {
      setErrore(e?.response?.data?.detail || e?.message || 'Errore durante la quadratura');
    } finally {
      setLoading(null);
    }
  };

  // Ricostruzione completa Cassa+Banca dai corrispettivi archiviati: a
  // differenza del passo 4 (che inserisce solo quelli mai sincronizzati),
  // questo cancella e ricrea TUTTI i movimenti con source=corrispettivo_*
  // dell'anno selezionato — serve quando l'importo totale corrispettivi o
  // la quota "pagamento elettronico" in Prima Nota Cassa risultano diversi
  // dal corrispettivo originale (es. dati importati prima della correzione
  // della logica unificata).
  const [risultatoRicostruzione, setRisultatoRicostruzione] = useState(null);

  const lanciaRicostruzione = async () => {
    const conferma = await confirm({
      title: `Ricostruisci Prima Nota da Corrispettivi — anno ${anno}`,
      message:
        `Elimina e ricrea tutti i movimenti di Prima Nota Cassa e Banca generati dai ` +
        `corrispettivi dell'anno ${anno} (categoria "Corrispettivi", "POS Verso Banca", ` +
        `"Corrispettivi POS"), usando i dati oggi presenti nell'archivio corrispettivi. ` +
        `Non tocca fatture, versamenti o altri movimenti manuali.`,
      confirmText: 'Ricostruisci',
      variant: 'warning',
    });
    if (!conferma) return;
    azzeraErrori();
    setLoading('ricostruisci');
    setRisultatoRicostruzione(null);
    try {
      const res = await api.post(`/api/corrispettivi/rebuild-prima-nota?anno=${anno}`);
      setRisultatoRicostruzione(res.data);
    } catch (e) {
      setErrore(e?.response?.data?.detail || e?.message || 'Errore durante la ricostruzione');
    } finally {
      setLoading(null);
    }
  };

  const lanciaAutoConferma = async () => {
    const conferma = await confirm({
      title: `Smistamento provvisorie — anno ${anno}`,
      message:
        `Le fatture in Provvisoria verranno spostate in Prima Nota Cassa/Banca in base al metodo ` +
        `pagamento del fornitore (CASSA → tutte in Cassa; BANCA → solo le PAGATE in Banca; ` +
        `PayPal/carta/senza metodo restano in Provvisoria). Ogni movimento creato è annullabile con un comando.`,
      confirmText: 'Procedi',
      variant: 'warning',
    });
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

  // Metodi discordanti: fatture registrate in un registro diverso dal metodo
  // ATTUALE del fornitore (es. Varriale = Cassa in anagrafica ma fatture in
  // Banca perché confermate prima della correzione). Diagnosi + spostamento
  // per singola voce, sempre azione dell'utente.
  const [discordanti, setDiscordanti] = useState(null);
  const [spostandoId, setSpostandoId] = useState(null);

  const lanciaDiagnosiMetodi = async () => {
    azzeraErrori();
    setLoading('metodi');
    try {
      const res = await api.get(`/api/prima-nota/diagnostica-metodi?anno=${anno}`);
      setDiscordanti(res.data);
    } catch (e) {
      setErrore(e?.response?.data?.detail || e?.message || 'Errore durante la diagnosi metodi');
    } finally {
      setLoading(null);
    }
  };

  const spostaDiscordante = async voce => {
    const conferma = await confirm({
      title: 'Sposta movimento',
      message:
        `Spostare il movimento del ${voce.data} (${voce.numero_fattura || voce.descrizione}, ` +
        `${formatEuroD(voce.importo || 0)}) da ${voce.registro_attuale.toUpperCase()} ` +
        `a ${voce.registro_atteso.toUpperCase()}? La fattura collegata viene aggiornata di conseguenza.`,
      confirmText: 'Sposta',
    });
    if (!conferma) return;
    setSpostandoId(voce.movimento_id);
    try {
      await api.post('/api/prima-nota/sposta-scrittura', {
        movimento_id: voce.movimento_id,
        destinazione: voce.registro_atteso,
      });
      setDiscordanti(d => ({
        ...d,
        totale_discordanti: (d?.totale_discordanti || 1) - 1,
        discordanti: (d?.discordanti || []).filter(x => x.movimento_id !== voce.movimento_id),
      }));
    } catch (e) {
      setErrore(e?.response?.data?.detail || e?.message || 'Errore durante lo spostamento');
    } finally {
      setSpostandoId(null);
    }
  };

  // Riparazione versamenti storici: la causale reale della banca ("VERS.
  // CONTANTI") non veniva riconosciuta dall'import (cercava "VERSAMENTO"
  // per intero) — l'entrata in Prima Nota Banca c'era sempre, ma l'uscita
  // corrispondente in Prima Nota Cassa non veniva mai creata. Il controllo
  // è stato corretto per i nuovi import; questo pulsante ripara lo storico.
  const [risultatoVersamenti, setRisultatoVersamenti] = useState(null);

  const lanciaRiparaVersamenti = async () => {
    const conferma = await confirm({
      title: `Ripara versamenti mancanti in Cassa — anno ${anno}`,
      message:
        'Cerca nell\'estratto conto le causali di versamento contanti (es. "VERS. CONTANTI") ' +
        'e crea in Prima Nota Cassa l\'uscita mancante per quelle che non l\'hanno mai avuta. ' +
        'Non tocca le entrate già presenti in Prima Nota Banca.',
      confirmText: 'Ripara',
      variant: 'warning',
    });
    if (!conferma) return;
    azzeraErrori();
    setLoading('ripara-versamenti');
    setRisultatoVersamenti(null);
    try {
      const res = await api.post(`/api/estratto-conto-movimenti/ripara-versamenti-cassa?anno=${anno}`);
      setRisultatoVersamenti(res.data);
    } catch (e) {
      setErrore(e?.response?.data?.detail || e?.message || 'Errore durante la riparazione');
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

        {/* STEP 4a - QUADRATURA CORRISPETTIVI DA DRIVE (recupera i buchi) */}
        <StepCard
          numero="4a"
          titolo="Quadratura corrispettivi da Drive (recupera i mancanti)"
          descrizione={
            'Da eseguire PRIMA del passo 4b se sospetti corrispettivi interi mai arrivati in Prima Nota ' +
            '(es. una cassa/PDV su due). Ripassa gli XML originali già archiviati su Drive e ricrea solo ' +
            "quelli che risultano mancanti nel gestionale — non tocca quelli già presenti."
          }
        >
          <button
            onClick={lanciaQuadraturaCorrispettivi}
            disabled={isBusy}
            style={btnStyle('primary', isBusy)}
          >
            {loading === 'quadratura' ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            Avvia quadratura Drive
          </button>

          {risultatoQuadratura && (
            <div style={{ ...resultBoxStyle, background: '#f0fdf4', borderColor: '#22c55e' }}>
              {risultatoQuadratura.status === 'not_configured' ? (
                <div style={{ fontSize: 13, color: '#78350f' }}>
                  Integrazione Google Drive corrispettivi non configurata su questo ambiente.
                </div>
              ) : (
                <>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                    <CheckCircle size={18} color="#059669" />
                    <strong style={{ color: '#065f46' }}>Quadratura completata</strong>
                  </div>
                  <div style={{ fontSize: 13, color: '#065f46', lineHeight: 1.6 }}>
                    File controllati: <strong>{risultatoQuadratura.controllati}</strong>
                    <br />
                    Già presenti (quadrati): {risultatoQuadratura.quadrati}
                    <br />
                    <span style={{ color: risultatoQuadratura.recuperati > 0 ? '#b91c1c' : '#065f46', fontWeight: 700 }}>
                      Recuperati (mancanti nel gestionale): {risultatoQuadratura.recuperati}
                    </span>
                    {risultatoQuadratura.errori > 0 && (
                      <>
                        <br />
                        <span style={{ color: '#991b1b' }}>Errori: {risultatoQuadratura.errori}</span>
                      </>
                    )}
                  </div>
                  {risultatoQuadratura.recuperati > 0 && (
                    <div style={{ fontSize: 12, color: '#78350f', background: '#fffbeb', padding: 8, borderRadius: 6, marginTop: 8 }}>
                      Corrispettivi recuperati: esegui ora il passo 4b ("Ricostruisci da corrispettivi")
                      per rigenerare correttamente Prima Nota Cassa e Banca con i dati completi.
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </StepCard>

        {/* STEP 4bis - RICOSTRUZIONE COMPLETA DA CORRISPETTIVI */}
        <StepCard
          numero="4b"
          titolo="Ricostruisci importi corrispettivi e pagamento elettronico"
          descrizione={
            'Se in Prima Nota Cassa il totale corrispettivi o la quota "pagamento elettronico" ' +
            'non tornano (es. dati importati prima della correzione), usa questo pulsante: cancella ' +
            "e ricrea da zero i movimenti generati dai corrispettivi dell'anno selezionato."
          }
        >
          <button
            onClick={lanciaRicostruzione}
            disabled={isBusy}
            style={btnStyle('primary', isBusy)}
          >
            {loading === 'ricostruisci' ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            Ricostruisci da corrispettivi ({anno})
          </button>

          {risultatoRicostruzione && (
            <div style={{ ...resultBoxStyle, background: '#f0fdf4', borderColor: '#22c55e' }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                <CheckCircle size={18} color="#059669" />
                <strong style={{ color: '#065f46' }}>Ricostruzione completata</strong>
              </div>
              <div style={{ fontSize: 13, color: '#065f46', lineHeight: 1.6 }}>
                Corrispettivi processati: <strong>{risultatoRicostruzione.corrispettivi_processati}</strong>
                {risultatoRicostruzione.corrispettivi_saltati > 0 && (
                  <> (saltati: {risultatoRicostruzione.corrispettivi_saltati})</>
                )}
                <br />
                Movimenti Cassa ricreati: <strong>{risultatoRicostruzione.prima_nota_cassa_creati}</strong>{' '}
                (eliminati prima: {risultatoRicostruzione.prima_nota_cassa_eliminati})
                <br />
                Movimenti Banca ricreati: <strong>{risultatoRicostruzione.prima_nota_banca_creati}</strong>{' '}
                (eliminati prima: {risultatoRicostruzione.prima_nota_banca_eliminati})
              </div>
            </div>
          )}
        </StepCard>

        {/* STEP 4c - RIPARA VERSAMENTI MANCANTI IN CASSA */}
        <StepCard
          numero="4c"
          titolo="Ripara versamenti mancanti in Cassa"
          descrizione={
            'Se un versamento di contanti in banca risulta in Prima Nota Banca ma non ha ' +
            'la corrispondente uscita in Prima Nota Cassa (causale bancaria "VERS. CONTANTI" ' +
            "non riconosciuta prima della correzione), usa questo pulsante per l'anno selezionato."
          }
        >
          <button
            onClick={lanciaRiparaVersamenti}
            disabled={isBusy}
            style={btnStyle('primary', isBusy)}
          >
            {loading === 'ripara-versamenti' ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            Ripara versamenti ({anno})
          </button>

          {risultatoVersamenti && (
            <div style={{ ...resultBoxStyle, background: '#f0fdf4', borderColor: '#22c55e' }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                <CheckCircle size={18} color="#059669" />
                <strong style={{ color: '#065f46' }}>Riparazione completata</strong>
              </div>
              <div style={{ fontSize: 13, color: '#065f46', lineHeight: 1.6 }}>
                Versamenti trovati nell'estratto conto: <strong>{risultatoVersamenti.movimenti_versamento_trovati}</strong>
                <br />
                Uscite create in Cassa: <strong>{risultatoVersamenti.riparati}</strong>
                <br />
                Già presenti (nessuna azione): {risultatoVersamenti.gia_presenti}
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

        {/* ── REGISTRO PAGAMENTI: coerenza metodo fornitore ↔ registrazioni ── */}
        <StepCard
          numero={6}
          titolo="Metodi discordanti (registro pagamenti ↔ anagrafica)"
          descrizione={
            'Confronta OGNI fattura registrata in Cassa/Banca con il metodo ATTUALE del fornitore ' +
            '(es. fornitore Cassa con fatture finite in Banca perché confermate prima della correzione). ' +
            'Ogni voce mostra data operazione e registro; lo spostamento è sempre una tua scelta, voce per voce.'
          }
        >
          <button
            onClick={lanciaDiagnosiMetodi}
            disabled={isBusy}
            style={{
              padding: '10px 18px', background: '#0f2744', color: 'white',
              border: 'none', borderRadius: 8, fontWeight: 700, fontSize: 13,
              cursor: isBusy ? 'wait' : 'pointer', display: 'inline-flex',
              alignItems: 'center', gap: 8,
            }}
          >
            {loading === 'metodi' ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
            Controlla coerenza {anno}
          </button>

          {discordanti && (
            <div style={{ marginTop: 14 }}>
              {discordanti.totale_discordanti === 0 ? (
                <div style={{
                  padding: 12, background: '#f0fdf4', border: '1px solid #16a34a',
                  borderRadius: 8, color: '#166534', fontSize: 13, fontWeight: 600,
                  display: 'flex', alignItems: 'center', gap: 8,
                }}>
                  <CheckCircle size={16} /> Tutto coerente: ogni fattura registrata è nel registro
                  previsto dal metodo del suo fornitore.
                </div>
              ) : (
                <>
                  <div style={{
                    padding: 12, background: '#fffbeb', border: '1px solid #d97706',
                    borderRadius: 8, color: '#92400e', fontSize: 13, fontWeight: 700, marginBottom: 10,
                    display: 'flex', alignItems: 'center', gap: 8,
                  }}>
                    <AlertTriangle size={16} />
                    {discordanti.totale_discordanti} registrazioni in contrasto con il metodo
                    attuale del fornitore
                  </div>
                  {(discordanti.discordanti || []).map(v => (
                    <div
                      key={v.movimento_id}
                      style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        gap: 8, flexWrap: 'wrap', padding: '10px 12px', marginBottom: 6,
                        background: 'white', border: '1px solid #fde68a', borderRadius: 8,
                      }}
                    >
                      <div style={{ flex: 1, minWidth: 180, fontSize: 13 }}>
                        <strong>{v.numero_fattura || v.descrizione}</strong>
                        <div style={{ fontSize: 11.5, color: '#64748b', marginTop: 2 }}>
                          Operazione del {v.data} · {formatEuroD(v.importo || 0)} · oggi in{' '}
                          <strong style={{ color: '#dc2626' }}>{v.registro_attuale.toUpperCase()}</strong>,
                          {' '}il fornitore è{' '}
                          <strong style={{ color: '#16a34a' }}>{v.registro_atteso.toUpperCase()}</strong>
                        </div>
                      </div>
                      <button
                        onClick={() => spostaDiscordante(v)}
                        disabled={spostandoId === v.movimento_id}
                        style={{
                          padding: '7px 14px', background: '#0f2744', color: 'white',
                          border: 'none', borderRadius: 6, fontWeight: 700, fontSize: 12,
                          cursor: spostandoId === v.movimento_id ? 'wait' : 'pointer',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {spostandoId === v.movimento_id
                          ? 'Sposto…'
                          : `→ Sposta in ${v.registro_atteso}`}
                      </button>
                    </div>
                  ))}
                </>
              )}
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

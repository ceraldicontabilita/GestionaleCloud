/**
 * Riparazioni una tantum: i lavori di recupero che finora esistevano solo
 * come chiamate API, quindi il titolare non poteva lanciarli.
 *
 * Ognuno si esegue in due tempi, e il primo e' obbligatorio: **Conta** non
 * scrive niente e dice quante righe toccherebbe; **Esegui** chiede conferma e
 * scrive. Sono lavori che girano in background (§4: oltre i 5 minuti il proxy
 * Render taglia la richiesta), quindi la risposta e' «avviato» e lo stato si
 * rilegge con Aggiorna.
 */
import React, { useState, useCallback } from 'react';
import api, { messaggioErrore } from '../api';
import { toast } from 'sonner';
import { Button, Card, Badge } from './ds';
import { useConfirm } from './ui/ConfirmDialog';

/** I lavori, nell'ordine in cui vanno fatti: il pregresso prima di tutto. */
export const RIPARAZIONI = [
  {
    id: 'pregresso',
    titolo: 'Fatture mai registrate in Prima Nota',
    spiega:
      'Le fatture entrate senza che scattasse il loro evento non hanno partita ' +
      'aperta verso il fornitore ne\' riga nel libro giornale: sono i giorni che ' +
      'in Prima Nota risultano vuoti. Ripubblica lo stesso evento sugli stessi ' +
      'handler, che sono idempotenti: non crea doppioni.',
    poi: 'Dopo questo, lancia «Registra il pregresso».',
    esegui: '/api/admin/fatture/ripubblica-evento-created',
    stato: '/api/admin/fatture/ripubblica-evento-created/stato',
  },
  {
    id: 'registra-pregresso',
    titolo: 'Registra il pregresso nel libro giornale',
    spiega:
      'Porta nel libro giornale i documenti gia\' in archivio che non hanno una ' +
      'registrazione contabile. Va lanciato DOPO la ripubblicazione, altrimenti ' +
      'registra fatture a cui manca ancora la partita.',
    esegui: '/api/piano-conti/registra-pregresso',
    stato: null,
  },
  {
    id: 'numia',
    titolo: 'Incassi POS NUMIA dagli estratti conto',
    spiega:
      'NUMIA non ha API e nessuno digita la chiusura serale, quindi il ' +
      'trasferimento POS del giorno non nasce e gli accrediti in banca non hanno ' +
      'niente da agganciare. Ricostruisce la chiusura sommando gli accrediti per ' +
      'giorno operativo (DEL gg/mm/aa), come da regola del titolare.',
    esegui: '/api/pos-corrispettivi/chiusure-giornaliere/ricostruisci-numia',
    stato: null,
  },
  {
    id: 'scadenze',
    titolo: 'Togliere le scadenze inventate dalle fatture fornitore',
    spiega:
      'Le fatture fornitore non hanno scadenza: decide il titolare quando pagare. ' +
      'Quelle in archivio le ha scritte il vecchio import leggendo l\'XML, ed e\' ' +
      'quel numero a far comparire «scaduto» dove non c\'e\' nessun impegno.',
    esegui: '/api/admin/fatture/azzera-scadenze',
    stato: '/api/admin/fatture/azzera-scadenze/stato',
  },
  {
    id: 'lipe',
    titolo: 'Importare le LIPE del commercialista',
    spiega:
      'La LIPE e\' il documento canonico dell\'IVA mensile. Senza, al confronto ' +
      'con il commercialista manca la colonna di mezzo. Un periodo la cui ' +
      'aritmetica del quadro VP non quadra non viene depositato.',
    esegui: '/api/iva/lipe/importa',
    stato: null,
  },
  {
    id: 'doppioni',
    titolo: 'Doppioni di cedolini, quietanze F24, bonifici e F24',
    spiega:
      'La stessa busta, quietanza o bonifico entrata da piu\' PDF (Libro Unico, ' +
      'file singolo, copie «(2)») conta gli stipendi e i pagamenti piu\' volte. ' +
      'Le copie vanno nella cartella «da eliminare» (quarantena, recuperabile); ' +
      'resta quella pagata o abbinata alla banca, e i collegamenti passano su di lei. ' +
      'Anche le righe doppie della Prima Nota salari.',
    esegui: '/api/doppioni/ripulisci',
    stato: '/api/doppioni/stato',
  },
];

/** Un job in corso scrive: legge `fase` (doppioni_archivio) o `stato`
 * (recupero_fatture_pregresso) — gli unici due nomi usati in `sistema_stato`
 * dai lavori di questo pannello. */
function jobInCorso(data) {
  return Boolean(data) && (data.fase === 'in_corso' || data.stato === 'in_corso');
}

function Riga({ lavoro, confirm, attivo, setAttivo }) {
  const [esito, setEsito] = useState(null);
  const [inCorso, setInCorso] = useState(null);
  const bloccatoDaAltro = attivo !== null && attivo.id !== lavoro.id;

  const chiama = useCallback(async (dryRun) => {
    setInCorso(dryRun ? 'conta' : 'esegui');
    try {
      const { data } = await api.post(`${lavoro.esegui}?dry_run=${dryRun}`);
      setEsito({ dryRun, data });
      toast.success(dryRun ? 'Conteggio eseguito, niente scritto' : 'Avviato');
      if (!dryRun) setAttivo({ id: lavoro.id, titolo: lavoro.titolo });
    } catch (e) {
      const msg = messaggioErrore(e);
      setEsito({ dryRun, errore: msg });
      toast.error(`Non riuscito: ${msg}`);
    } finally {
      setInCorso(null);
    }
  }, [lavoro.esegui, lavoro.id, lavoro.titolo, setAttivo]);

  const aggiorna = useCallback(async () => {
    if (!lavoro.stato) return;
    setInCorso('stato');
    try {
      const { data } = await api.get(lavoro.stato);
      setEsito({ stato: true, data });
      // Se questo era il lavoro segnato attivo e non e' piu' in corso, si sblocca da solo.
      if (attivo?.id === lavoro.id && !jobInCorso(data)) setAttivo(null);
    } catch (e) {
      toast.error(messaggioErrore(e));
    } finally {
      setInCorso(null);
    }
  }, [lavoro.stato, lavoro.id, attivo, setAttivo]);

  const eseguiDavvero = useCallback(async () => {
    const ok = await confirm({
      title: lavoro.titolo,
      description:
        'Questa volta scrive davvero. Hai gia\' guardato i numeri del conteggio?',
      confirmText: 'Sì, esegui',
      variant: 'danger',
    });
    if (ok) chiama(false);
  }, [confirm, chiama, lavoro.titolo]);

  return (
    <Card style={{ padding: 16, marginBottom: 12, opacity: bloccatoDaAltro ? 0.6 : 1 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{lavoro.titolo}</div>
      <p style={{ margin: '0 0 8px', fontSize: 14, lineHeight: 1.5, opacity: 0.85 }}>
        {lavoro.spiega}
      </p>
      {lavoro.poi && (
        <p style={{ margin: '0 0 8px', fontSize: 13 }}>
          <Badge variant="warning">Ordine</Badge> {lavoro.poi}
        </p>
      )}
      {bloccatoDaAltro && (
        <p style={{ margin: '0 0 8px', fontSize: 13, fontWeight: 600 }}>
          In attesa: «{attivo.titolo}» e' in corso, aspetta che finisca.
        </p>
      )}

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Button
          variant="secondary"
          size="sm"
          disabled={inCorso !== null || bloccatoDaAltro}
          onClick={() => chiama(true)}
        >
          {inCorso === 'conta' ? 'Conto…' : 'Conta (non scrive)'}
        </Button>
        <Button
          variant="danger"
          size="sm"
          disabled={inCorso !== null || !esito || esito.errore || bloccatoDaAltro}
          onClick={eseguiDavvero}
        >
          {inCorso === 'esegui' ? 'Avvio…' : 'Esegui'}
        </Button>
        {lavoro.stato && (
          <Button
            variant="ghost"
            size="sm"
            disabled={inCorso !== null}
            onClick={aggiorna}
          >
            {inCorso === 'stato' ? 'Leggo…' : 'Aggiorna stato'}
          </Button>
        )}
      </div>

      {esito && (
        <pre
          data-testid={`esito-${lavoro.id}`}
          style={{
            marginTop: 10, marginBottom: 0, padding: 10, fontSize: 12,
            overflowX: 'auto', borderRadius: 8,
            background: 'rgba(0,0,0,0.04)',
          }}
        >
          {esito.errore ? esito.errore : JSON.stringify(esito.data, null, 2)}
        </pre>
      )}
    </Card>
  );
}

export default function PannelloRiparazioni() {
  const confirm = useConfirm();
  const [attivo, setAttivo] = useState(null);
  return (
    <div>
      <p style={{ fontSize: 14, lineHeight: 1.6, marginTop: 0 }}>
        Lavori di recupero da lanciare <strong>una volta sola</strong>. Ognuno
        conta prima e scrive dopo: il bottone «Esegui» si accende solo quando hai
        visto i numeri. Girano in background, quindi rispondono «avviato»: per
        vedere com'e' finita, riapri la pagina interessata.
      </p>
      {attivo && (
        <div data-testid="lavoro-attivo">
          <Card style={{ padding: 12, marginBottom: 12, display: 'flex', alignItems: 'center',
                         justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>
              In corso: «{attivo.titolo}». Gli altri «Esegui» restano spenti finche' non finisce.
            </span>
            <Button variant="ghost" size="sm" onClick={() => setAttivo(null)}>
              Ho controllato, e' finita: sblocca
            </Button>
          </Card>
        </div>
      )}
      {RIPARAZIONI.map((l) => (
        <Riga key={l.id} lavoro={l} confirm={confirm} attivo={attivo} setAttivo={setAttivo} />
      ))}
    </div>
  );
}

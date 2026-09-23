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
];

function Riga({ lavoro, confirm }) {
  const [esito, setEsito] = useState(null);
  const [inCorso, setInCorso] = useState(null);

  const chiama = useCallback(async (dryRun) => {
    setInCorso(dryRun ? 'conta' : 'esegui');
    try {
      const { data } = await api.post(`${lavoro.esegui}?dry_run=${dryRun}`);
      setEsito({ dryRun, data });
      toast.success(dryRun ? 'Conteggio eseguito, niente scritto' : 'Avviato');
    } catch (e) {
      const msg = messaggioErrore(e);
      setEsito({ dryRun, errore: msg });
      toast.error(`Non riuscito: ${msg}`);
    } finally {
      setInCorso(null);
    }
  }, [lavoro.esegui]);

  const aggiorna = useCallback(async () => {
    if (!lavoro.stato) return;
    setInCorso('stato');
    try {
      const { data } = await api.get(lavoro.stato);
      setEsito({ stato: true, data });
    } catch (e) {
      toast.error(messaggioErrore(e));
    } finally {
      setInCorso(null);
    }
  }, [lavoro.stato]);

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
    <Card style={{ padding: 16, marginBottom: 12 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{lavoro.titolo}</div>
      <p style={{ margin: '0 0 8px', fontSize: 14, lineHeight: 1.5, opacity: 0.85 }}>
        {lavoro.spiega}
      </p>
      {lavoro.poi && (
        <p style={{ margin: '0 0 8px', fontSize: 13 }}>
          <Badge variant="warning">Ordine</Badge> {lavoro.poi}
        </p>
      )}

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Button
          variant="secondary"
          size="sm"
          disabled={inCorso !== null}
          onClick={() => chiama(true)}
        >
          {inCorso === 'conta' ? 'Conto…' : 'Conta (non scrive)'}
        </Button>
        <Button
          variant="danger"
          size="sm"
          disabled={inCorso !== null || !esito || esito.errore}
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
  return (
    <div>
      <p style={{ fontSize: 14, lineHeight: 1.6, marginTop: 0 }}>
        Lavori di recupero da lanciare <strong>una volta sola</strong>. Ognuno
        conta prima e scrive dopo: il bottone «Esegui» si accende solo quando hai
        visto i numeri. Girano in background, quindi rispondono «avviato»: per
        vedere com'e' finita, riapri la pagina interessata.
      </p>
      {RIPARAZIONI.map((l) => (
        <Riga key={l.id} lavoro={l} confirm={confirm} />
      ))}
    </div>
  );
}

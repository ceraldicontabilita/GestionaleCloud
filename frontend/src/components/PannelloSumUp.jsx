import React, { useState } from 'react';
import api from '../api';
import { toast } from 'sonner';
import { Button, Badge, Card } from './ds';
import { COLORS } from '../lib/utils';

/**
 * Pannello SumUp: stato delle credenziali, sincronizzazione incassi e
 * analisi delle righe POS storiche ricavate dall'XML.
 *
 * Esiste perché aprire gli endpoint a mano in una scheda nuova non porta
 * sempre con sé la sessione: da qui le chiamate partono dalla pagina già
 * autenticata e il problema non si pone.
 */
const euro = (v) =>
  new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' })
    .format(Number(v || 0));

const dataIT = (iso) => {
  const parti = String(iso || '').slice(0, 10).split('-');
  return parti.length === 3 ? `${parti[2]}/${parti[1]}/${parti[0]}` : iso;
};

export default function PannelloSumUp() {
  const [stato, setStato] = useState(null);
  const [sync, setSync] = useState(null);
  const [bonifica, setBonifica] = useState(null);
  const [inCorso, setInCorso] = useState('');

  const esegui = async (azione, chiamata, dopo) => {
    setInCorso(azione);
    try {
      const { data } = await chiamata();
      dopo(data);
      return data;
    } catch (e) {
      const dettaglio = e?.response?.data?.detail || e?.message || 'errore';
      toast.error(`SumUp: ${dettaglio}`);
      return null;
    } finally {
      setInCorso('');
    }
  };

  const verifica = () =>
    esegui('stato', () => api.get('/sumup/stato'), (d) => {
      setStato(d);
      if (d.connessione_ok) toast.success(`SumUp collegato: ${d.esercente || ''}`);
      else toast.warning(d.messaggio || 'SumUp non collegato');
    });

  const sincronizza = (giorni) => {
    const oggi = new Date();
    const dal = new Date(oggi);
    dal.setDate(dal.getDate() - (giorni - 1));
    const iso = (d) => d.toISOString().slice(0, 10);
    return esegui('sync', () => api.post('/sumup/sincronizza',
      { dal: iso(dal), al: iso(oggi) }), (d) => {
      setSync(d);
      toast.success(d.message || 'Sincronizzazione completata');
    });
  };

  const analizza = () =>
    esegui('bonifica', () => api.get('/sumup/bonifica-pos-xml'), (d) => {
      setBonifica(d);
      toast.info(`${d.giornate_totali} giornate con POS ricavato dall'XML`);
    });

  const occupato = Boolean(inCorso);

  return (
    <Card title="💳 SumUp — incassi POS da API">
      <p style={{ color: COLORS.textSubtle, fontSize: 13, marginTop: 0 }}>
        Le transazioni SumUp non creano ricavi: il ricavo è già quello del
        corrispettivo. Qui si stabilisce quanta parte dell'incasso è passata
        dal terminale SumUp.
      </p>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, margin: '12px 0' }}>
        <Button onClick={verifica} disabled={occupato}>
          {inCorso === 'stato' ? 'Verifico…' : 'Verifica connessione'}
        </Button>
        <Button variant="secondary" onClick={() => sincronizza(2)} disabled={occupato}>
          {inCorso === 'sync' ? 'Sincronizzo…' : 'Sincronizza ieri e oggi'}
        </Button>
        <Button variant="secondary" onClick={() => sincronizza(30)} disabled={occupato}>
          Sincronizza ultimi 30 giorni
        </Button>
        <Button variant="ghost" onClick={analizza} disabled={occupato}>
          {inCorso === 'bonifica' ? 'Analizzo…' : 'Analizza POS da XML (sola lettura)'}
        </Button>
      </div>

      {stato && (
        <div style={{ marginBottom: 16 }}>
          <Badge variant={stato.connessione_ok ? 'success' : 'danger'}>
            {stato.connessione_ok ? 'Collegato' : 'Non collegato'}
          </Badge>
          <div style={{ fontSize: 13, marginTop: 6 }}>
            {stato.esercente && <div>Esercente: <b>{stato.esercente}</b></div>}
            <div>Chiave: {stato.chiave_visibile || '—'} · Merchant: {stato.merchant_code || '—'}</div>
            {stato.messaggio && (
              <div style={{ color: stato.connessione_ok ? COLORS.success : COLORS.danger }}>
                {stato.messaggio}
              </div>
            )}
          </div>
        </div>
      )}

      {sync && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>
            Incassi SumUp — {euro(sync.totale_netto)} netti
          </div>
          {(sync.giornate || []).length === 0 ? (
            <div style={{ fontSize: 13, color: COLORS.textSubtle }}>
              Nessuna transazione nell'intervallo.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: 'left' }}>Giorno</th>
                    <th style={{ textAlign: 'right' }}>Vendite</th>
                    <th style={{ textAlign: 'right' }}>Rimborsi</th>
                    <th style={{ textAlign: 'right' }}>Netto</th>
                    <th style={{ textAlign: 'right' }}>N.</th>
                  </tr>
                </thead>
                <tbody>
                  {sync.giornate.map((g) => (
                    <tr key={g.data}>
                      <td>{dataIT(g.data)}</td>
                      <td style={{ textAlign: 'right' }}>{euro(g.vendite)}</td>
                      <td style={{ textAlign: 'right' }}>{euro(g.rimborsi)}</td>
                      <td style={{ textAlign: 'right', fontWeight: 600 }}>{euro(g.netto)}</td>
                      <td style={{ textAlign: 'right' }}>{g.transazioni}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {bonifica && (
        <div>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>
            POS ricavato dall'XML: {bonifica.giornate_totali} giornate,{' '}
            {euro(bonifica.importo_totale)}
          </div>
          <div style={{ fontSize: 13, color: COLORS.textSubtle }}>
            Già coperte dal dato reale: {(bonifica.gia_coperte_dal_pos_reale || []).length}
            {' · '}
            Senza POS reale: {(bonifica.senza_pos_reale || []).length}
          </div>
        </div>
      )}
    </Card>
  );
}

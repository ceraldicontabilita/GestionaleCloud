import React, { useEffect, useState } from 'react';
import api from '../api';
import { toast } from 'sonner';
import { Button, Badge, Card } from './ds';
import { COLORS } from '../lib/utils';

/**
 * Pannello SumUp: stato delle credenziali, sincronizzazione incassi e
 * analisi delle righe POS storiche ricavate dall'XML.
 *
 * La sincronizzazione ordinaria è automatica all'apertura. Restano manuali
 * soltanto le operazioni diagnostiche/correttive che possono modificare dati.
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

  const esegui = async (azione, chiamata, dopo, { silenzioso = false } = {}) => {
    setInCorso(azione);
    try {
      const { data } = await chiamata();
      dopo(data);
      return data;
    } catch (e) {
      const dettaglio = e?.response?.data?.detail || e?.message || 'errore';
      if (!silenzioso) toast.error(`SumUp: ${dettaglio}`);
      return null;
    } finally {
      setInCorso('');
    }
  };

  const verifica = (silenzioso = false) =>
    esegui('stato', () => api.get('/api/sumup/stato'), (d) => {
      setStato(d);
      if (!silenzioso) {
        if (d.connessione_ok) toast.success(`SumUp collegato: ${d.esercente || ''}`);
        else toast.warning(d.messaggio || 'SumUp non collegato');
      }
    }, { silenzioso });

  const sincronizza = (giorni, silenzioso = false) => {
    const oggi = new Date();
    const dal = new Date(oggi);
    dal.setDate(dal.getDate() - (giorni - 1));
    const iso = (d) => d.toISOString().slice(0, 10);
    return esegui('sync', () => api.post('/api/sumup/sincronizza',
      { dal: iso(dal), al: iso(oggi) }), (d) => {
      setSync(d);
      if (!silenzioso) toast.success(d.message || 'Sincronizzazione completata');
    }, { silenzioso });
  };

  useEffect(() => {
    let attivo = true;
    const inizializza = async () => {
      const statoCorrente = await verifica(true);
      if (attivo && statoCorrente?.connessione_ok) {
        await sincronizza(2, true);
      }
    };
    inizializza();
    return () => { attivo = false; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const analizza = () =>
    esegui('bonifica', () => api.get('/api/sumup/bonifica-pos-xml'), (d) => {
      setBonifica(d);
      toast.info(`${d.giornate_totali} giornate con POS ricavato dall'XML`);
    });

  const correggiXml = () =>
    esegui('correggi-xml', () => api.post('/api/sumup/bonifica-pos-xml',
      { conferma: true }), (d) => {
      setBonifica(d);
      toast.success(
        `${d.righe_archiviate || 0} righe XML escluse dai saldi; ` +
        `${d.trasferimenti_reali_ricostruiti || 0} trasferimenti reali ricostruiti`
      );
    });

  const occupato = Boolean(inCorso);

  return (
    <Card title="💳 SumUp — incassi POS da API">
      <p style={{ color: COLORS.textSubtle, fontSize: 13, marginTop: 0 }}>
        Le transazioni SumUp non creano ricavi: il ricavo è già quello del
        corrispettivo. Qui si stabilisce quanta parte dell'incasso è passata
        dal terminale SumUp. Stato e incassi recenti si aggiornano automaticamente all'apertura.
      </p>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, margin: '12px 0' }}>
        <Button variant="ghost" onClick={analizza} disabled={occupato}>
          {inCorso === 'bonifica' ? 'Analizzo…' : 'Analizza POS da XML (sola lettura)'}
        </Button>
        {bonifica?.giornate_totali > 0 && (
          <Button variant="danger" onClick={correggiXml} disabled={occupato}>
            {inCorso === 'correggi-xml' ? 'Correggo…' : 'Escludi POS errati da XML'}
          </Button>
        )}
      </div>

      {inCorso === 'stato' || inCorso === 'sync' ? (
        <div style={{ fontSize: 13, color: COLORS.textSubtle, marginBottom: 12 }}>
          Aggiornamento SumUp in corso…
        </div>
      ) : null}

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
          {sync.payouts?.success === false && (
            <div style={{ marginTop: 10, color: COLORS.warning || '#92400e', fontSize: 13 }}>
              Vendite acquisite, ma accrediti non disponibili: {sync.payouts.errore || 'verifica autorizzazione payouts.read'}.
            </div>
          )}
          {(sync.payouts?.accrediti_per_giorno || []).length > 0 && (
            <div style={{ marginTop: 14, overflowX: 'auto' }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>
                Accrediti SumUp unificati per giorno effettivo
              </div>
              <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: 'left' }}>Data accredito</th>
                    <th style={{ textAlign: 'right' }}>Mastercard</th>
                    <th style={{ textAlign: 'right' }}>Commissioni</th>
                    <th style={{ textAlign: 'right' }}>Gruppi</th>
                    <th style={{ textAlign: 'right' }}>Da verificare</th>
                  </tr>
                </thead>
                <tbody>
                  {sync.payouts.accrediti_per_giorno.map((g) => (
                    <tr key={g.data}>
                      <td>{dataIT(g.data)}</td>
                      <td style={{ textAlign: 'right', fontWeight: 600 }}>{euro(g.accredito_mastercard)}</td>
                      <td style={{ textAlign: 'right' }}>{euro(g.commissioni)}</td>
                      <td style={{ textAlign: 'right' }}>{g.gruppi}</td>
                      <td style={{ textAlign: 'right' }}>{g.da_verificare || 0}</td>
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

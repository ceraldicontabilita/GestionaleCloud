import React, { useEffect, useState } from 'react';
import api from '../api';
import { VisoreOriginale } from '../components/ApriOriginale';
import { Badge, Button, Card, PageHeader, PageLoader, StatCard } from '../components/ds';
import { urlOriginale } from '../lib/vista';

const euro = cents => cents == null ? 'Importo non letto' : new Intl.NumberFormat('it-IT', {
  style: 'currency', currency: 'EUR',
}).format(Number(cents) / 100);

const dataIt = value => {
  if (!value) return 'data non disponibile';
  const [anno, mese, giorno] = String(value).slice(0, 10).split('-');
  return giorno && mese && anno ? `${giorno}/${mese}/${anno}` : value;
};

const stato = value => ({
  ACCOLTA: ['Istanza accolta', 'success'],
  PRESENTATA_DA_VERIFICARE: ['Istanza presentata · accoglimento da verificare', 'warning'],
  ACCOLTA_ISTANZA_ORIGINALE_NON_TROVATA: ['Piano accolto · istanza originale non trovata', 'warning'],
}[value] || [value || 'Da verificare', 'neutral']);

export default function DilazioniInps() {
  const [dati, setDati] = useState(null);
  const [errore, setErrore] = useState('');
  const [originale, setOriginale] = useState(null);
  useEffect(() => {
    let attivo = true;
    api.get('/api/fiscal/dilazioni-inps')
      .then(r => { if (attivo) setDati(r.data); })
      .catch(e => { if (attivo) setErrore(e.response?.data?.detail || e.message); });
    return () => { attivo = false; };
  }, []);
  if (!dati && !errore) return <PageLoader />;
  const items = dati?.items || [];
  return <div style={{ width: '100%', paddingBottom: 24 }}>
    <PageHeader title="Dilazioni INPS" subtitle="Domande, accoglimenti, rate e prove di pagamento" />
    <Card style={{ marginBottom: 16 }}>
      <strong>Regola di lettura</strong>
      <div style={{ marginTop: 4 }}>{dati?.regola || "L'istanza non prova l'accoglimento e non prova il pagamento."}</div>
    </Card>
    {errore && <div role="alert">Errore: {errore}</div>}
    {dati && <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 10, marginBottom: 16 }}>
      <StatCard label="Istanze" value={dati.sources?.istanze_dilazioni_inps || 0} />
      <StatCard label="Piani accolti" value={dati.sources?.dilazioni_inps || 0} accent="success" />
      <StatCard label="Da verificare" value={items.filter(i => i.stato_richiesta === 'PRESENTATA_DA_VERIFICARE').length} accent="warning" />
    </div>}
    <div style={{ display: 'grid', gap: 12 }}>
      {items.map(item => {
        const [label, variant] = stato(item.stato_richiesta);
        return <Card key={item.id}>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: 8 }}>
            <div>
              <strong>{item.rif || 'Riferimento non letto'}</strong>
              <div style={{ marginTop: 4 }}>Matricola INPS {item.matricola || 'non letta'}</div>
            </div>
            <Badge variant={variant}>{label}</Badge>
          </div>
          <div style={{ marginTop: 10 }}>
            {item.data_domanda && <>Domanda del {dataIt(item.data_domanda)} · </>}
            periodi {item.periodo_da || '?'} - {item.periodo_a || '?'}
            {item.totale_richiesto_cents != null && <> · totale richiesto {euro(item.totale_richiesto_cents)}</>}
          </div>
          {item.stato_richiesta === 'PRESENTATA_DA_VERIFICARE' && <div role="status" style={{ marginTop: 8 }}>
            I periodi non sono marcati come pagati: manca il provvedimento INPS di accoglimento con il piano di ammortamento.
          </div>}
          {(item.periodi || []).length > 0 && <div style={{ overflowX: 'auto', marginTop: 10 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead><tr><th align="left">Periodo</th><th align="right">Contributi</th><th align="right">Sanzioni</th></tr></thead>
              <tbody>{item.periodi.map(p => <tr key={p.periodo}>
                <td>{p.periodo}</td><td align="right">{euro(p.contributi_cents)}</td><td align="right">{euro(p.sanzioni_cents)}</td>
              </tr>)}</tbody>
            </table>
          </div>}
          {item.data_accoglimento && <div style={{ marginTop: 8 }}>Accoglimento documentato il {dataIt(item.data_accoglimento)} · piano {item.stato_piano || 'da verificare'}</div>}
          {(item.rate || []).length > 0 && <div style={{ overflowX: 'auto', marginTop: 10 }}>
            <strong>Rate del piano accolto</strong>
            <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 6 }}>
              <thead><tr><th align="left">Rata</th><th align="left">Scadenza</th><th align="right">Importo</th><th align="left">Esito</th></tr></thead>
              <tbody>{item.rate.map(rata => <tr key={rata.numero}>
                <td>{rata.numero}/{item.rate.length}</td>
                <td>{dataIt(rata.scadenza)}</td>
                <td align="right">{euro(rata.importo_cents)}</td>
                <td>{rata.stato === 'PAGATA' ? `Pagata con quietanza${rata.data_pagamento ? ` il ${dataIt(rata.data_pagamento)}` : ''}` :
                  rata.stato === 'SCADUTA_NON_PAGATA' ? 'Scaduta · quietanza non trovata' :
                  rata.stato === 'VERSATA_IMPORTO_DIVERSO' ? 'Versamento diverso · rata ancora aperta' : 'Da pagare'}</td>
              </tr>)}</tbody>
            </table>
          </div>}
          {item.documento_id && <Button size="sm" variant="secondary" style={{ marginTop: 10 }} onClick={() => setOriginale({
            url: urlOriginale({ tipo: 'documento', id: item.documento_id }), titolo: 'Documento INPS',
          })}>Apri documento</Button>}
        </Card>;
      })}
      {!items.length && <Card>Nessuna istanza o dilazione INPS importata.</Card>}
    </div>
    {originale && <VisoreOriginale url={originale.url} titolo={originale.titolo} onClose={() => setOriginale(null)} />}
  </div>;
}

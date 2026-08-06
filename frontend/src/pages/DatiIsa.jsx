import React, { useEffect, useState } from 'react';
import { Badge, Card, PageHeader, StatCard, Table, TableWrap, Th, Td } from '../components/ds';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { COLORS, formatEuro } from '../lib/utils';
import api from '../api';

const MESI = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];

export default function DatiIsa() {
  const { anno } = useAnnoGlobale();
  const [data, setData] = useState(null);
  const [fasce, setFasce] = useState(null);
  const [errore, setErrore] = useState('');

  useEffect(() => {
    let attivo = true;
    Promise.all([
      api.get(`/api/dati-isa/riepilogo?anno=${anno}`),
      api.get('/api/dashboard/fascia-energia'),
    ]).then(([d, f]) => {
      if (attivo) { setData(d.data); setFasce(f.data); setErrore(''); }
    }).catch(e => attivo && setErrore(e.response?.data?.detail || e.message));
    return () => { attivo = false; };
  }, [anno]);

  const indicatori = data?.indicatori_acquisti || {};
  const energia = data?.energia || { mensili: [], totali: {} };

  return (
    <div style={{ padding: '0 16px 24px' }}>
      <PageHeader
        title="Dati ISA (ex studi di settore)"
        subtitle={`Riepilogo documentale ${anno}: acquisti, energia e dati da verificare con il commercialista`}
      />
      {errore && <div style={{ padding: 12, color: COLORS.danger }}>Errore: {errore}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(210px,1fr))', gap: 12, marginBottom: 16 }}>
        <StatCard label="Vino - acquisti netti" value={formatEuro(indicatori.vino_costo_netto)} />
        <StatCard label="Materie prime pasticceria/gelateria" value={formatEuro(indicatori.materie_prime_costo_netto)} />
        <StatCard label="Prodotti pronti/semilavorati" value={formatEuro(indicatori.semilavorati_costo_netto)} />
        <StatCard label="Caffe acquistato" value={`${Number(indicatori.caffe_kg || 0).toLocaleString('it-IT')} kg`} />
        <StatCard label="Costo netto caffe" value={formatEuro(indicatori.caffe_costo_netto)} />
        <StatCard label="Energia elettrica" value={`${Number(energia.totali?.totale_kwh || 0).toLocaleString('it-IT')} kWh`} />
      </div>

      <Card title="Consumi elettrici mensili per fascia" style={{ marginBottom: 16 }}>
        <TableWrap>
          <Table>
            <thead><tr><Th>Mese</Th><Th>F1 kWh</Th><Th>F2 kWh</Th><Th>F3 kWh</Th><Th>Totale</Th><Th>Picco kW</Th></tr></thead>
            <tbody>
              {energia.mensili?.map(r => (
                <tr key={`${r.anno}-${r.mese}`}>
                  <Td><strong>{MESI[r.mese - 1]} {r.anno}</strong></Td>
                  <Td>{Number(r.f1_kwh || 0).toLocaleString('it-IT')}</Td>
                  <Td>{Number(r.f2_kwh || 0).toLocaleString('it-IT')}</Td>
                  <Td>{Number(r.f3_kwh || 0).toLocaleString('it-IT')}</Td>
                  <Td><strong>{Number(r.totale_kwh || 0).toLocaleString('it-IT')}</strong></Td>
                  <Td>{r.potenza_massima_kw ?? '-'}</Td>
                </tr>
              ))}
              {!energia.mensili?.length && <tr><Td colSpan={6}>Nessuna bolletta elaborata per l'anno selezionato.</Td></tr>}
            </tbody>
          </Table>
        </TableWrap>
      </Card>

      <Card title="Quando conviene produrre" style={{ marginBottom: 16 }}>
        <div style={{ marginBottom: 10 }}>
          Fascia attuale: <Badge variant={fasce?.fascia_attuale === 'F2' ? 'danger' : 'success'}>{fasce?.fascia_attuale || '-'}</Badge>{' '}
          <strong>{fasce?.azione}</strong>
        </div>
        {fasce?.regole?.map(r => (
          <div key={r.giorni} style={{ padding: '7px 0', borderBottom: `1px solid ${COLORS.border}` }}>
            <strong>{r.giorni}</strong>: F1 {r.F1}; F2 {r.F2}; F3 {r.F3}
          </div>
        ))}
        <p style={{ color: COLORS.textMuted, fontSize: 13 }}>
          Nel contratto attuale F3 e la fascia piu economica, F1 intermedia e F2 la piu costosa.
        </p>
      </Card>

      <Card title="Controlli e limiti del dato">
        <ul style={{ margin: 0, paddingLeft: 20 }}>
          {data?.avvertenze?.map(a => <li key={a} style={{ marginBottom: 6 }}>{a}</li>)}
        </ul>
      </Card>
    </div>
  );
}

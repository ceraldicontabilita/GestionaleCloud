/**
 * InAttesaDocumento — i movimenti bancari che aspettano il documento.
 *
 * In Prima Nota Banca entra un pagamento solo quando si sa a cosa si
 * riferisce. Quello che non si e' ancora agganciato resta fuori, e questa e'
 * l'unica differenza legittima fra il saldo qui e quello del conto corrente.
 *
 * Per questo il riquadro c'e' anche quando non c'e' niente da fare: una
 * differenza che nessuno spiega diventa un errore che nessuno cerca.
 */
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api';

const euro = (v) =>
  new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' })
    .format(Number(v || 0));

export default function InAttesaDocumento({ anno }) {
  const [dati, setDati] = useState(null);
  const [aperto, setAperto] = useState(false);

  useEffect(() => {
    let vivo = true;
    api.get(`/api/prima-nota/banca/in-attesa-documento?anno=${anno}`)
      .then(({ data }) => { if (vivo) setDati(data); })
      .catch(() => { if (vivo) setDati(null); });
    return () => { vivo = false; };
  }, [anno]);

  if (!dati) return null;

  const quanti = dati.totale || 0;
  const tutto_a_posto = quanti === 0;

  return (
    <div
      data-testid="banca-in-attesa-documento"
      style={{
        margin: '12px 0',
        padding: '12px 14px',
        borderRadius: 10,
        border: `1px solid ${tutto_a_posto ? '#bbf7d0' : '#fde68a'}`,
        background: tutto_a_posto ? '#f0fdf4' : '#fffbeb',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <strong style={{ color: tutto_a_posto ? '#15803d' : '#92400e' }}>
          {tutto_a_posto
            ? 'Nessun movimento in attesa: la Prima Nota copre tutto l’estratto conto.'
            : `${quanti} movimenti dell’estratto conto aspettano il documento`}
        </strong>
        {!tutto_a_posto && (
          <>
            <span style={{ color: '#92400e', fontSize: 13 }}>
              effetto sul saldo {euro(dati.effetto_sul_saldo)}
            </span>
            <button
              onClick={() => setAperto(v => !v)}
              style={{
                marginLeft: 'auto', padding: '5px 10px', borderRadius: 7,
                border: '1px solid #fcd34d', background: '#fff',
                color: '#92400e', fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
              }}
            >
              {aperto ? 'Nascondi' : 'Vedi quali'}
            </button>
            <Link
              to="/riconciliazione"
              style={{
                padding: '5px 10px', borderRadius: 7, background: '#92400e',
                color: '#fff', fontSize: 12.5, fontWeight: 600, textDecoration: 'none',
              }}
            >
              Agganciali
            </Link>
          </>
        )}
      </div>

      {!tutto_a_posto && (
        <p style={{ margin: '8px 0 0', fontSize: 12.5, color: '#78350f' }}>
          Non sono un errore: sono pagamenti di cui non si sa ancora la causale.
          Entrano in Prima Nota quando li colleghi alla fattura, al cedolino o
          all’F24 a cui appartengono.
        </p>
      )}

      {aperto && (
        <div style={{ marginTop: 10, overflowX: 'auto' }}>
          <table style={{ width: '100%', fontSize: 12.5, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ textAlign: 'left', color: '#78350f' }}>
                <th style={{ padding: '4px 6px' }}>Data</th>
                <th style={{ padding: '4px 6px' }}>Descrizione</th>
                <th style={{ padding: '4px 6px' }}>Categoria</th>
                <th style={{ padding: '4px 6px', textAlign: 'right' }}>Importo</th>
              </tr>
            </thead>
            <tbody>
              {(dati.movimenti || []).slice(0, 100).map((m) => (
                <tr key={m.id} style={{ borderTop: '1px solid #fde68a' }}>
                  <td style={{ padding: '4px 6px', whiteSpace: 'nowrap' }}>
                    {String(m.data || '').slice(0, 10).split('-').reverse().join('/')}
                  </td>
                  <td style={{ padding: '4px 6px' }}>
                    {(m.descrizione || m.descrizione_originale || '').slice(0, 90)}
                  </td>
                  <td style={{ padding: '4px 6px' }}>{m.categoria || '—'}</td>
                  <td style={{
                    padding: '4px 6px', textAlign: 'right', whiteSpace: 'nowrap',
                    color: m.tipo === 'entrata' ? '#15803d' : '#b91c1c', fontWeight: 600,
                  }}>
                    {m.tipo === 'entrata' ? '+' : '−'} {euro(m.importo)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {quanti > 100 && (
            <p style={{ fontSize: 12, color: '#78350f', margin: '6px 0 0' }}>
              Mostrati i primi 100 di {quanti}.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

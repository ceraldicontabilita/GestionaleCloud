/**
 * AssociaMovimentoBanca — collega a mano una fattura al suo addebito in banca.
 *
 * Il matching automatico e' severo apposta: senza importo al centesimo, numero
 * fattura e nome fornitore non associa. Giusto, ma lasciava l'utente davanti a
 * un elenco che poteva solo guardare — e la causale della banca spesso quel
 * numero non ce l'ha proprio.
 *
 * Qui le prove si mostrano invece di pretenderle: per ogni movimento e' scritto
 * cosa combacia. Chi conferma e' una persona, e la sua conferma vale come
 * prova — passa dallo stesso `riconcilia-manuale` della pagina Riconciliazione,
 * quindi la fattura risulta pagata e il movimento entra in Prima Nota da un
 * percorso solo.
 */
import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import api from '../api';

const euro = (v) =>
  new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' })
    .format(Number(v || 0));

const dataIT = (iso) => {
  const p = String(iso || '').slice(0, 10).split('-');
  return p.length === 3 ? `${p[2]}-${p[1]}-${p[0]}` : (iso || '—');
};

export default function AssociaMovimentoBanca({ fattura, onChiudi, onAssociato }) {
  const [dati, setDati] = useState(null);
  const [errore, setErrore] = useState('');
  const [inCorso, setInCorso] = useState('');

  useEffect(() => {
    let vivo = true;
    api.get(`/api/prima-nota/banca/candidati-per-fattura?fattura_id=${fattura.fattura_id}`)
      .then(({ data }) => { if (vivo) setDati(data); })
      .catch((e) => {
        if (vivo) setErrore(e?.response?.data?.detail || 'Ricerca non riuscita.');
      });
    return () => { vivo = false; };
  }, [fattura.fattura_id]);

  const associa = async (movimento) => {
    setInCorso(movimento.id);
    try {
      await api.post('/api/operazioni-da-confermare/smart/riconcilia-manuale', {
        movimento_id: movimento.id,
        tipo: 'fattura',
        associazioni: [{ id: fattura.fattura_id }],
        note: 'Associazione confermata a mano da Prima Nota',
      });
      toast.success('Fattura associata al movimento bancario.');
      onAssociato?.();
      onChiudi();
    } catch (e) {
      const dettaglio = e?.response?.data?.detail || 'Associazione non riuscita.';
      toast.error(dettaglio);
      setInCorso('');
    }
  };

  const candidati = dati?.candidati || [];

  return (
    <div
      onClick={onChiudi}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,39,68,0.55)', zIndex: 1100,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 14,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        data-testid="associa-movimento-banca"
        style={{
          background: 'white', borderRadius: 14, padding: 18,
          width: '100%', maxWidth: 720, maxHeight: '85vh', overflowY: 'auto',
        }}
      >
        <h3 style={{ margin: '0 0 4px' }}>Associa il pagamento in banca</h3>
        <p style={{ margin: '0 0 14px', color: '#64748b', fontSize: 13 }}>
          {fattura.fornitore || '—'} — Fatt. {fattura.fattura_numero || '—'} ·{' '}
          <b>{euro(fattura.importo)}</b>
        </p>

        {errore && <p style={{ color: '#b91c1c' }}>{errore}</p>}
        {!dati && !errore && <p style={{ color: '#64748b' }}>Cerco nell’estratto conto…</p>}

        {dati && candidati.length === 0 && (
          <p style={{ color: '#92400e', background: '#fffbeb', padding: 12, borderRadius: 8 }}>
            Nessun movimento compatibile in estratto conto. Se l’addebito non è
            ancora arrivato è normale: comparirà al prossimo import.
          </p>
        )}

        {candidati.map((m) => (
          <div
            key={m.id}
            style={{
              display: 'flex', justifyContent: 'space-between', gap: 10,
              alignItems: 'center', flexWrap: 'wrap',
              border: '1px solid #e2e8f0', borderRadius: 10,
              padding: '10px 12px', marginBottom: 8,
            }}
          >
            <div style={{ minWidth: 0, flex: '1 1 320px' }}>
              <div style={{ fontWeight: 700, fontSize: 13 }}>
                {dataIT(m.data)} · {euro(Math.abs(m.importo))}
              </div>
              <div style={{ fontSize: 12.5, color: '#475569' }}>
                {(m.descrizione || m.descrizione_originale || '').slice(0, 110)}
              </div>
              <div style={{ fontSize: 11.5, marginTop: 4 }}>
                {m.prove.length === 0 ? (
                  <span style={{ color: '#92400e' }}>
                    solo importo vicino — controlla bene prima di confermare
                  </span>
                ) : (
                  m.prove.map((p) => (
                    <span
                      key={p}
                      style={{
                        display: 'inline-block', marginRight: 6, padding: '2px 7px',
                        borderRadius: 6, background: '#dcfce7', color: '#15803d',
                        fontWeight: 600,
                      }}
                    >
                      {p}
                    </span>
                  ))
                )}
              </div>
            </div>
            <button
              onClick={() => associa(m)}
              disabled={Boolean(inCorso)}
              style={{
                padding: '8px 14px', borderRadius: 8, border: 'none',
                background: '#0f2a4a', color: '#fff', fontWeight: 700,
                fontSize: 12.5, cursor: inCorso ? 'wait' : 'pointer',
                opacity: inCorso && inCorso !== m.id ? 0.5 : 1,
              }}
            >
              {inCorso === m.id ? 'Associo…' : 'È questo'}
            </button>
          </div>
        ))}

        <div style={{ textAlign: 'right', marginTop: 12 }}>
          <button
            onClick={onChiudi}
            style={{
              padding: '8px 14px', borderRadius: 8, border: '1px solid #cbd5e1',
              background: '#fff', color: '#334155', fontWeight: 600, cursor: 'pointer',
            }}
          >
            Chiudi
          </button>
        </div>
      </div>
    </div>
  );
}

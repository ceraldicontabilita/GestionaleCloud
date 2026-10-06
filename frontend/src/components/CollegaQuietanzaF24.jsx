import React, { useCallback, useEffect, useState } from 'react';
import { Check } from 'lucide-react';
import api from '../api';
import ApriOriginale from './ApriOriginale';
import { PageLoader } from './ds';
import { COLORS, FONT, formatDateIT, formatEuro } from '../lib/utils';

/**
 * «Quietanza trovata per tributo e periodo» di un modello F24 senza prova.
 *
 * Il motore (`f24_proposte_quietanza`) cerca in tutte le quietanze le righe con lo stesso codice
 * tributo e lo stesso periodo di riferimento, anche con importo diverso (ravvedimento, pagamento
 * spezzato). Qui si vedono **il modello e la quietanza uno accanto all'altro** (due bottoni sugli
 * originali), riga per riga con la differenza, e il titolare conferma scegliendo un motivo a chip.
 * Il collegamento non prova la banca. Sola proposta: niente si scrive senza la conferma.
 */

const euro = cents => (cents == null ? '—' : formatEuro(cents / 100));
const euroConSegno = cents => (cents == null ? '—' : `${cents > 0 ? '+' : ''}${formatEuro(cents / 100)}`);

const stileChip = attivo => ({
  minHeight: 44, padding: '8px 14px', borderRadius: 999, textAlign: 'left', cursor: 'pointer',
  border: `1px solid ${attivo ? COLORS.primary : COLORS.border}`,
  background: attivo ? COLORS.primarySoft : COLORS.card, color: attivo ? COLORS.primary : COLORS.text,
  fontWeight: 600, fontSize: 13,
});

function Candidata({ f24Id, nomeModello, candidata, motivi, onCollegata }) {
  const [aperto, setAperto] = useState(false);
  const [motivo, setMotivo] = useState('');
  const [testo, setTesto] = useState('');
  const [errore, setErrore] = useState('');
  const [inCorso, setInCorso] = useState(false);
  const pronto = motivo && (motivo !== 'altro' || testo.trim().length >= 3);
  const bloccata = (candidata.collegata_ad_altro_modello || []).length > 0;

  const conferma = async () => {
    setInCorso(true);
    setErrore('');
    try {
      await api.post(`/api/f24-riconciliazione/modello/${encodeURIComponent(f24Id)}/quietanze-candidate/conferma`, {
        quietanza_id: candidata.quietanza_id, motivo, motivo_testo: motivo === 'altro' ? testo.trim() : undefined,
      });
      if (onCollegata) onCollegata();
    } catch (e) {
      const corpo = e.response?.data || {};
      setErrore(corpo.message || corpo.detail || e.message || 'Collegamento non riuscito');
    } finally {
      setInCorso(false);
    }
  };

  return (
    <div data-testid="quietanza-candidata" style={{ border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: '10px 12px', display: 'grid', gap: 8 }}>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <strong>
          Quietanza del {formatDateIT(candidata.data)}{candidata.protocollo ? ` · protocollo ${candidata.protocollo}` : ''}
        </strong>
        <span style={{ fontSize: 13, color: COLORS.textMuted }}>
          righe in comune {candidata.copertura} · saldo {euro(candidata.saldo_cents)}
        </span>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 420 }} data-testid="righe-candidata">
          <thead>
            <tr style={{ background: COLORS.bgAlt, textAlign: 'left' }}>
              {['Tributo', 'Periodo', 'Nel modello', 'Nella quietanza', 'Differenza'].map((h, i) => (
                <th key={h} style={{ padding: '6px 8px', fontSize: 11, textTransform: 'uppercase', color: COLORS.textMuted, textAlign: i >= 2 ? 'right' : 'left' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {candidata.righe_corrispondenti.map(r => (
              <tr key={`${r.codice}-${r.periodo}`} style={{ borderTop: `1px solid ${COLORS.border}` }}>
                <td style={{ padding: '6px 8px', fontWeight: 700 }}>{r.codice}</td>
                <td style={{ padding: '6px 8px' }}>{r.periodo}</td>
                <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: FONT.mono }}>{euro(r.importo_modello_cents)}</td>
                <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: FONT.mono }}>{euro(r.importo_quietanza_cents)}</td>
                <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: FONT.mono, color: r.differenza_cents ? COLORS.warning : COLORS.success }}>
                  {r.differenza_cents ? euroConSegno(r.differenza_cents) : 'uguale'}
                </td>
              </tr>
            ))}
            {candidata.righe_non_trovate.map(r => (
              <tr key={`nt-${r.codice}-${r.periodo}`} style={{ borderTop: `1px solid ${COLORS.border}`, color: COLORS.textMuted }}>
                <td style={{ padding: '6px 8px' }}>{r.codice}</td>
                <td style={{ padding: '6px 8px' }}>{r.periodo}</td>
                <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: FONT.mono }}>{euro(r.importo_modello_cents)}</td>
                <td style={{ padding: '6px 8px', textAlign: 'right' }} colSpan={2}>non nella quietanza</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ fontSize: 13 }}>
        Differenza sulle righe in comune: <strong>{euroConSegno(candidata.differenza_totale_cents)}</strong>
        {candidata.differenza_totale_cents ? ' (sanzioni e interessi, oppure importo versato diverso)' : ''}
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <ApriOriginale tipo="f24" id={f24Id} titolo={nomeModello || 'Modello F24'} testId={`apri-modello-${candidata.quietanza_id}`}>
          Apri il modello F24
        </ApriOriginale>
        <ApriOriginale url={candidata.pdf_url} titolo={`Quietanza ${candidata.protocollo || ''}`.trim()} testId={`apri-quietanza-${candidata.quietanza_id}`}>
          Apri la quietanza trovata
        </ApriOriginale>
      </div>

      {bloccata && (
        <div role="note" style={{ fontSize: 13, color: COLORS.warning }}>
          Questa quietanza è già collegata a un altro modello: non si può collegare di nuovo.
        </div>
      )}
      {!bloccata && !aperto && (
        <div>
          <button
            type="button" onClick={() => setAperto(true)} data-testid={`collega-${candidata.quietanza_id}`}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minHeight: 44, padding: '8px 14px', borderRadius: 10, border: `1px solid ${COLORS.primary}`, background: COLORS.card, color: COLORS.primary, fontWeight: 700, fontSize: 13, cursor: 'pointer' }}
          >
            <Check size={14} aria-hidden="true" /> Collega questa quietanza
          </button>
        </div>
      )}
      {!bloccata && aperto && (
        <div style={{ display: 'grid', gap: 8 }} data-testid={`collega-form-${candidata.quietanza_id}`}>
          <span style={{ fontSize: 12.5, color: COLORS.textMuted }}>Perché è la quietanza di questo modello?</span>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {Object.keys(motivi).map(k => (
              <button key={k} type="button" style={stileChip(motivo === k)} onClick={() => setMotivo(k)} data-testid={`motivo-collegamento-${k}`}>
                {motivi[k]}
              </button>
            ))}
          </div>
          {motivo === 'altro' && (
            <label style={{ display: 'grid', gap: 4, fontSize: 12.5 }}>
              Scrivi il motivo
              <input
                value={testo} onChange={e => setTesto(e.target.value)} maxLength={200}
                style={{ minHeight: 44, padding: '8px 10px', borderRadius: 8, border: `1px solid ${COLORS.border}`, fontSize: 14 }}
              />
            </label>
          )}
          {errore && <div role="alert" style={{ color: COLORS.danger, fontSize: 13 }}>{errore}</div>}
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button" disabled={!pronto || inCorso} onClick={conferma} data-testid={`conferma-collegamento-${candidata.quietanza_id}`}
              style={{ minHeight: 44, padding: '8px 14px', borderRadius: 10, border: `1px solid ${COLORS.primary}`, background: COLORS.primary, color: '#fff', fontWeight: 700, fontSize: 13, opacity: !pronto || inCorso ? 0.6 : 1, cursor: 'pointer' }}
            >
              {inCorso ? 'Collego…' : 'Conferma il collegamento'}
            </button>
            <button type="button" onClick={() => setAperto(false)} style={{ minHeight: 44, padding: '8px 14px', borderRadius: 10, border: `1px solid ${COLORS.border}`, background: COLORS.card, cursor: 'pointer' }}>
              Annulla
            </button>
          </div>
          <div style={{ fontSize: 12, color: COLORS.textMuted }}>Il collegamento non prova la banca: l'addebito resta da verificare.</div>
        </div>
      )}
    </div>
  );
}

export default function CollegaQuietanzaF24({ f24Id, onCollegata }) {
  const [stato, setStato] = useState({ dati: null, errore: '' });
  const carica = useCallback(() => {
    let attivo = true;
    setStato({ dati: null, errore: '' });
    api.get(`/api/f24-riconciliazione/modello/${encodeURIComponent(f24Id)}/quietanze-candidate`)
      .then(r => { if (attivo) setStato({ dati: r.data, errore: '' }); })
      .catch(e => { if (attivo) setStato({ dati: null, errore: e.response?.data?.message || e.response?.data?.detail || e.message || 'lettura non riuscita' }); });
    return () => { attivo = false; };
  }, [f24Id]);
  useEffect(() => carica(), [carica]);

  if (stato.errore) return <div role="alert" style={{ color: COLORS.danger, fontSize: 14 }}>Ricerca delle quietanze non riuscita: {stato.errore}</div>;
  if (!stato.dati) return <PageLoader />;
  const { candidati = [], motivi = {}, gia_collegato: giaCollegato, file_name: nomeModello } = stato.dati;
  if (giaCollegato) return null;
  if (candidati.length === 0) {
    return (
      <p data-testid="candidate-vuote" style={{ margin: 0, color: COLORS.textMuted, fontSize: 14 }}>
        Nessuna quietanza con lo stesso tributo e periodo di questo modello. Se è stato pagato, la quietanza non è ancora in archivio.
      </p>
    );
  }
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <p style={{ margin: 0, color: COLORS.textMuted, fontSize: 13.5 }}>
        Trovate per stesso codice tributo e stesso periodo, anche con importo diverso. Sono proposte: il collegamento lo confermi tu.
      </p>
      {candidati.map(c => (
        <Candidata
          key={c.quietanza_id} f24Id={f24Id} nomeModello={nomeModello} candidata={c} motivi={motivi}
          onCollegata={() => { carica(); if (onCollegata) onCollegata(); }}
        />
      ))}
    </div>
  );
}

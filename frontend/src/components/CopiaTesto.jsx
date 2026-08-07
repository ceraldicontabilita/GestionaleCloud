/**
 * CopiaTesto — copia negli appunti un testo qualsiasi.
 *
 * Nasce per la chiave MFA: e' una stringa lunga e senza spazi, e selezionarla
 * a mano — soprattutto da telefono — e' un esercizio di pazienza. Vale per
 * ogni valore che si deve trascrivere altrove: chiavi, codici di recupero,
 * identificativi.
 *
 * Il ripiego con `execCommand` serve ai browser che non espongono
 * `navigator.clipboard`: senza, il pulsante non farebbe niente e l'utente non
 * saprebbe perche'.
 */
import React, { useState } from 'react';

const SPUNTA = 'M20 6 9 17l-5-5';
const FOGLI = 'M4 16V4a2 2 0 0 1 2-2h10M8 6h10a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z';

export default function CopiaTesto({
  testo,
  label = 'Copia',
  labelCopiato = 'Copiato',
  style = {},
  'data-testid': testId = 'copia-testo',
}) {
  const [copiato, setCopiato] = useState(false);
  const [errore, setErrore] = useState('');

  const copia = async () => {
    const valore = String(testo || '');
    if (!valore) return;
    setErrore('');
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(valore);
      } else {
        const appoggio = document.createElement('textarea');
        appoggio.value = valore;
        appoggio.style.position = 'fixed';
        appoggio.style.opacity = '0';
        document.body.appendChild(appoggio);
        appoggio.select();
        document.execCommand('copy');
        document.body.removeChild(appoggio);
      }
      setCopiato(true);
      setTimeout(() => setCopiato(false), 2000);
    } catch {
      // Meglio dirlo che lasciare un pulsante che sembra non funzionare.
      setErrore('Copia non riuscita: selezionala a mano.');
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={copia}
        data-testid={testId}
        aria-label={`${label} negli appunti`}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '6px 12px',
          background: copiato ? '#dcfce7' : '#f1f5f9',
          color: copiato ? '#15803d' : '#475569',
          border: `1px solid ${copiato ? '#86efac' : '#cbd5e1'}`,
          borderRadius: 8,
          fontSize: 12,
          fontWeight: 600,
          cursor: 'pointer',
          whiteSpace: 'nowrap',
          ...style,
        }}
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" strokeWidth="2" strokeLinecap="round"
             strokeLinejoin="round">
          <path d={copiato ? SPUNTA : FOGLI} />
        </svg>
        {copiato ? labelCopiato : label}
      </button>
      {errore && (
        <span style={{ color: '#9a3412', fontSize: 12, marginLeft: 8 }}>{errore}</span>
      )}
    </>
  );
}

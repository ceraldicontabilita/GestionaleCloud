import React, { useCallback, useState } from 'react';
import { Button } from './ds';
import { COLORS, BORDER_RADIUS, FONT } from '../lib/utils';

/**
 * Scelta a opzioni predefinite al posto di `window.prompt` (le mani sporche del
 * banco: si tocca, non si scrive). Il testo libero resta solo come eccezione,
 * dietro «Altro (scrivi tu)».
 *
 *   const [scegli, dialogo] = useScegliOpzione();
 *   const r = await scegli({ titolo, opzioni: [{ valore, etichetta, dettaglio, quota, richiedeCampo }], multipla, altro });
 *   // r = null se annullato; altrimenti { valore, testo, campo } (scelta singola)
 *   // oppure { valori: [valore], quote: { valore: numero } } (scelta multipla)
 *
 * `altro`: etichetta del campo libero (es. «Scrivi il motivo»); `richiedeCampo` su
 * un'opzione apre un campo obbligatorio con quell'etichetta (es. un ID).
 * `quota` su un'opzione multipla propone un importo, modificabile solo da «Altro».
 */
export function useScegliOpzione() {
  const [stato, setStato] = useState(null);
  const scegli = useCallback(cfg => new Promise(risolvi => setStato({ cfg, risolvi })), []);
  const fine = valore => {
    stato?.risolvi(valore);
    setStato(null);
  };
  const dialogo = stato ? <DialogoScelta cfg={stato.cfg} onFine={fine} /> : null;
  return [scegli, dialogo];
}

const chip = (attivo, extra = {}) => ({
  minHeight: 44, padding: '8px 14px', borderRadius: BORDER_RADIUS.md,
  border: `1px solid ${attivo ? COLORS.primary : COLORS.border}`,
  background: attivo ? COLORS.primary : COLORS.card,
  color: attivo ? '#fff' : COLORS.text,
  fontSize: 13.5, fontWeight: 600, fontFamily: FONT.family, cursor: 'pointer',
  textAlign: 'left', ...extra,
});

function DialogoScelta({ cfg, onFine }) {
  const { titolo, descrizione, opzioni = [], multipla = false, altro = null, conferma = 'Conferma' } = cfg;
  const [scelte, setScelte] = useState([]);
  const [usaAltro, setUsaAltro] = useState(false);
  const [testo, setTesto] = useState('');
  const [campo, setCampo] = useState('');
  const [quote, setQuote] = useState({});

  const selezionata = opzioni.find(o => o.valore === scelte[0]);
  const richiedeCampo = !multipla && selezionata?.richiedeCampo;
  const pronto = multipla
    ? scelte.length > 0 && (!usaAltro || scelte.every(v => Number(String(quote[v] ?? '').replace(',', '.')) > 0))
    : usaAltro
      ? testo.trim().length > 0
      : scelte.length === 1 && (!richiedeCampo || campo.trim().length > 0);

  const tocca = valore => {
    setUsaAltro(false);
    setScelte(prev => (multipla
      ? (prev.includes(valore) ? prev.filter(v => v !== valore) : [...prev, valore])
      : [valore]));
  };

  const invia = () => {
    if (!pronto) return;
    if (multipla) {
      const q = {};
      scelte.forEach(v => {
        const o = opzioni.find(x => x.valore === v);
        q[v] = usaAltro ? Number(String(quote[v] ?? '').replace(',', '.')) : o?.quota;
      });
      onFine({ valori: scelte, quote: q });
      return;
    }
    onFine({ valore: usaAltro ? 'altro' : scelte[0], testo: usaAltro ? testo.trim() : (selezionata?.etichetta || ''), campo: campo.trim() });
  };

  return (
    <div
      style={{ position: 'fixed', inset: 0, zIndex: 1300, background: 'rgba(20,20,19,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}
      onClick={() => onFine(null)}
      data-testid="dialogo-scelta"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={titolo}
        onClick={e => e.stopPropagation()}
        style={{ background: COLORS.card, borderRadius: BORDER_RADIUS.md, border: `1px solid ${COLORS.border}`, padding: 18, width: 'min(520px, 100%)', maxHeight: '90vh', overflowY: 'auto', fontFamily: FONT.family }}
      >
        <h3 style={{ margin: 0, fontSize: 16, color: COLORS.text }}>{titolo}</h3>
        {descrizione && <p style={{ margin: '6px 0 0', fontSize: 13, color: COLORS.textMuted }}>{descrizione}</p>}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 14 }}>
          {opzioni.map(o => (
            <button
              key={o.valore}
              type="button"
              aria-pressed={scelte.includes(o.valore)}
              onClick={() => tocca(o.valore)}
              style={chip(scelte.includes(o.valore), multipla ? { flex: '1 1 100%' } : {})}
            >
              {o.etichetta}
              {o.dettaglio && <div style={{ fontSize: 11.5, fontWeight: 400, opacity: 0.85 }}>{o.dettaglio}</div>}
            </button>
          ))}
          {altro && (
            <button
              type="button"
              aria-pressed={usaAltro}
              onClick={() => { setUsaAltro(v => !v); if (!multipla) setScelte([]); }}
              style={chip(usaAltro, { borderStyle: 'dashed' })}
            >
              Altro (scrivi tu)
            </button>
          )}
        </div>
        {usaAltro && !multipla && (
          <input
            autoFocus
            value={testo}
            onChange={e => setTesto(e.target.value)}
            aria-label={altro}
            placeholder={altro}
            style={{ marginTop: 12, width: '100%', minHeight: 44, padding: '8px 12px', boxSizing: 'border-box', borderRadius: BORDER_RADIUS.sm, border: `1px solid ${COLORS.border}`, fontSize: 14, fontFamily: FONT.family }}
          />
        )}
        {usaAltro && multipla && scelte.map(v => {
          const o = opzioni.find(x => x.valore === v);
          return (
            <label key={v} style={{ display: 'block', marginTop: 10, fontSize: 12.5, color: COLORS.textMuted }}>
              {altro} — {o?.etichetta}
              <input
                inputMode="decimal"
                value={quote[v] ?? (o?.quota ?? '')}
                onChange={e => setQuote(prev => ({ ...prev, [v]: e.target.value }))}
                style={{ display: 'block', marginTop: 4, width: '100%', minHeight: 44, padding: '8px 12px', boxSizing: 'border-box', borderRadius: BORDER_RADIUS.sm, border: `1px solid ${COLORS.border}`, fontSize: 14, fontFamily: FONT.family }}
              />
            </label>
          );
        })}
        {richiedeCampo && (
          <label style={{ display: 'block', marginTop: 12, fontSize: 12.5, color: COLORS.textMuted }}>
            {selezionata.richiedeCampo}
            <input
              autoFocus
              value={campo}
              onChange={e => setCampo(e.target.value)}
              style={{ display: 'block', marginTop: 4, width: '100%', minHeight: 44, padding: '8px 12px', boxSizing: 'border-box', borderRadius: BORDER_RADIUS.sm, border: `1px solid ${COLORS.border}`, fontSize: 14, fontFamily: FONT.family }}
            />
          </label>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
          <Button variant="secondary" style={{ minHeight: 44 }} onClick={() => onFine(null)}>Annulla</Button>
          <Button style={{ minHeight: 44 }} disabled={!pronto} onClick={invia}>{conferma}</Button>
        </div>
      </div>
    </div>
  );
}

export default useScegliOpzione;

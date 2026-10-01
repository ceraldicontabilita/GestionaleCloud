import React, { useEffect, useRef, useState } from 'react';
import api from '../../api';
import { formatEuro } from '../../lib/utils';

const TERRACOTTA = '#c15f3c';
const ROSSO = '#b4452f';

const METODI = [
  { id: 'cassa', titolo: 'Contanti', dettaglio: 'La registro in Prima Nota Cassa' },
  { id: 'banca', titolo: 'Banca', dettaglio: 'La sposto fra i pagamenti attesi in banca' },
];

/**
 * Scheda di conferma di una fattura provvisoria. Una fattura sta fra i provvisori perche' il
 * metodo di pagamento del fornitore non e' impostato: qui lo si sceglie, una volta sola. Il
 * metodo va sull'anagrafica del fornitore e questa fattura, insieme alle altre dello stesso
 * fornitore nella pagina (se si vuole), passa nella Prima Nota corrispondente.
 *
 * Mani sporche: due bottoni grandi, niente testo da scrivere.
 */
export default function ScegliMetodoFornitore({ fattura, altre = [], onClose, onFatto }) {
  const [metodo, setMetodo] = useState('cassa');
  const [conAltre, setConAltre] = useState(true);
  const [busy, setBusy] = useState(false);
  const [errore, setErrore] = useState('');
  const [conflitto, setConflitto] = useState('');
  const primo = useRef(null);

  useEffect(() => {
    primo.current?.focus();
    const esc = e => { if (e.key === 'Escape' && !busy) onClose(); };
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [busy, onClose]);

  const fornitore = fattura.fornitore || fattura.supplier_name || 'Fornitore';
  const numero = fattura.fattura_numero || fattura.numero_fattura || fattura.invoice_number || 'senza numero';
  const totaleAltre = altre.reduce((s, p) => s + Number(p.importo || 0), 0);

  const conferma = async (cambia = false) => {
    setBusy(true);
    setErrore('');
    try {
      const { data } = await api.post('/api/prima-nota/provvisori/imposta-metodo-fornitore', {
        fattura_id: fattura.fattura_id,
        metodo,
        altre_fattura_ids: conAltre ? altre.map(p => p.fattura_id) : [],
        ...(cambia ? { cambia_metodo: true } : {}),
      });
      onFatto(data);
    } catch (e) {
      const stato = e.response?.status;
      const dettaglio = e.response?.data?.detail || e.response?.data?.message || e.message;
      if (stato === 409 && /gia' il metodo/.test(String(dettaglio))) setConflitto(String(dettaglio));
      else setErrore(String(dettaglio));
      setBusy(false);
    }
  };

  return (
    <div
      onClick={() => { if (!busy) onClose(); }}
      style={{ position: 'fixed', inset: 0, background: 'rgba(20, 20, 19, 0.55)', zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 14 }}
    >
      <div
        role="dialog" aria-modal="true" aria-labelledby="metodo-fornitore-titolo"
        onClick={e => e.stopPropagation()}
        style={{ background: 'white', borderRadius: 14, padding: 20, width: '100%', maxWidth: 460, maxHeight: '90vh', overflowY: 'auto' }}
      >
        <h3 id="metodo-fornitore-titolo" style={{ margin: '0 0 6px', fontSize: 16, color: TERRACOTTA }}>
          Come hai pagato {fornitore}?
        </h3>
        <div style={{ fontSize: 13, color: '#5f5c55', marginBottom: 12 }}>
          Fattura {numero} · {formatEuro(Number(fattura.importo || 0))}. Il fornitore non ha ancora un metodo di pagamento:
          lo scegli ora e resta salvato, cosi' le prossime fatture seguono da sole.
        </div>

        <div role="radiogroup" aria-label="Metodo di pagamento" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
          {METODI.map((m, i) => (
            <button
              key={m.id} type="button" role="radio" aria-checked={metodo === m.id}
              ref={i === 0 ? primo : null}
              onClick={() => { setMetodo(m.id); setConflitto(''); }}
              style={{
                minHeight: 64, padding: '10px 12px', borderRadius: 10, cursor: 'pointer', textAlign: 'left',
                border: `2px solid ${metodo === m.id ? TERRACOTTA : '#d0ccbe'}`,
                background: metodo === m.id ? '#f7ebe4' : 'white', color: '#141413', fontFamily: 'inherit',
              }}
            >
              <div style={{ fontWeight: 800, fontSize: 15 }}>{metodo === m.id ? '✓ ' : ''}{m.titolo}</div>
              <div style={{ fontSize: 11.5, color: '#5f5c55', marginTop: 2 }}>{m.dettaglio}</div>
            </button>
          ))}
        </div>

        {altre.length > 0 && (
          <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', minHeight: 44, padding: '8px 10px', borderRadius: 8, background: '#f6f4ee', marginBottom: 12, cursor: 'pointer' }}>
            <input type="checkbox" checked={conAltre} onChange={e => setConAltre(e.target.checked)} style={{ width: 22, height: 22, marginTop: 1 }} />
            <span style={{ fontSize: 13 }}>
              Sposta anche le altre <b>{altre.length}</b> {altre.length === 1 ? 'fattura' : 'fatture'} di {fornitore} in questa pagina
              ({formatEuro(totaleAltre)}) nella stessa Prima Nota
            </span>
          </label>
        )}

        {conflitto && (
          <div role="alert" style={{ color: ROSSO, fontSize: 13, marginBottom: 10 }}>
            {conflitto}
            <div style={{ marginTop: 8 }}>
              <button
                type="button" onClick={() => conferma(true)} disabled={busy}
                style={{ minHeight: 44, padding: '8px 14px', borderRadius: 8, border: `1px solid ${ROSSO}`, background: 'white', color: ROSSO, fontWeight: 700, cursor: 'pointer' }}
              >
                Cambia il metodo del fornitore
              </button>
            </div>
          </div>
        )}
        {errore && <div role="alert" style={{ color: ROSSO, fontSize: 13, marginBottom: 10 }}>{errore}</div>}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <button
            type="button" onClick={onClose} disabled={busy}
            style={{ minHeight: 44, padding: '9px 16px', borderRadius: 8, border: '1px solid #d0ccbe', background: 'white', cursor: 'pointer', fontFamily: 'inherit' }}
          >
            Annulla
          </button>
          <button
            type="button" onClick={() => conferma(false)} disabled={busy}
            style={{ minHeight: 44, padding: '9px 18px', borderRadius: 8, border: 'none', background: TERRACOTTA, color: 'white', fontWeight: 700, cursor: 'pointer', opacity: busy ? 0.6 : 1, fontFamily: 'inherit' }}
          >
            {busy ? 'Registro…' : (metodo === 'cassa' ? 'Registra in Cassa' : 'Attendi banca')}
            {!busy && conAltre && altre.length > 0 ? ` (${altre.length + 1})` : ''}
          </button>
        </div>
      </div>
    </div>
  );
}

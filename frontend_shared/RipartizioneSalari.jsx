import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

const euro = n => n == null ? 'non disponibile' : Number(n).toLocaleString('it-IT', { style: 'currency', currency: 'EUR' });
const periodo = r => `${r.mese === 13 ? '13ª' : r.mese === 14 ? '14ª' : String(r.mese).padStart(2, '0')}/${r.anno}`;
const btn = { padding: '10px 14px', minHeight: 44, border: '1px solid #ccc', borderRadius: 7, background: '#fff', cursor: 'pointer' };
const input = { ...btn, width: '100%', minWidth: 0, boxSizing: 'border-box' };
const td = { padding: '9px 8px', borderBottom: '1px solid #e8e6df', textAlign: 'right' };

export default function RipartizioneSalari({ request, onClose, onSaved }) {
  const [piano, setPiano] = useState(null);
  const [scelte, setScelte] = useState([]);
  const [cedolino, setCedolino] = useState('');
  const [quota, setQuota] = useState('');
  const [collega, setCollega] = useState('');
  const [busy, setBusy] = useState(true);
  const [errore, setErrore] = useState('');
  const closeRef = useRef(null);
  const refresh = async (destinazioni = scelte, key = collega) => {
    setBusy(true); setErrore('');
    try {
      const p = await request({ destinazioni, collega_key: key && key !== 'distinto' ? key : null });
      setPiano(p); setScelte(p.destinazioni || []); setCollega(key);
    } catch (e) {
      const d = e?.response?.data?.detail;
      setErrore(typeof d === 'string' ? d : d?.message || e.message || 'Anteprima non disponibile');
    } finally { setBusy(false); }
  };
  useEffect(() => {
    const previous = document.activeElement;
    closeRef.current?.focus();
    refresh(null, '');
    return () => previous?.focus?.();
  }, []);
  const scelto = scelte.reduce((s, r) => s + Math.round(r.importo * 100), 0) / 100;
  const restante = Math.max(0, Math.round(((piano?.importo || 0) - scelto) * 100) / 100);
  const scegli = value => {
    setCedolino(value);
    const b = piano.cedolini.find(r => `${r.anno}-${r.mese}` === value);
    const assegnato = piano.quote.filter(r => `${r.anno}-${r.mese}` === value).reduce((s, r) => s + r.importo, 0);
    setQuota(b ? String(Math.min(restante, b.residuo == null ? restante : b.residuo + assegnato).toFixed(2)) : '');
  };
  const aggiungi = async () => {
    const b = piano.cedolini.find(r => `${r.anno}-${r.mese}` === cedolino);
    const n = Number(String(quota).replace(',', '.'));
    if (!b || !Number.isFinite(n) || n <= 0 || n > restante) { setErrore('Indica una quota positiva entro il restante del bonifico.'); return; }
    await refresh([...scelte, { anno: b.anno, mese: b.mese, importo: n }]);
    setCedolino(''); setQuota('');
  };
  const salva = async () => {
    setBusy(true); setErrore('');
    try {
      const r = await request({ conferma: true, versione: piano.versione, destinazioni: scelte,
        collega_key: collega && collega !== 'distinto' ? collega : null, conferma_distinto: collega === 'distinto' });
      onSaved(r);
    } catch (e) {
      const d = e?.response?.data?.detail;
      setErrore(typeof d === 'string' ? d : d?.message || 'Associazione non salvata');
    } finally { setBusy(false); }
  };
  const duplicato = piano?.possibili_duplicati?.length > 0 && !piano?.pagamento_esistente && collega !== 'distinto';
  return createPortal(<div style={{ position: 'fixed', inset: 0, background: '#0008', zIndex: 10000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 12 }}>
    <section role="dialog" aria-modal="true" aria-labelledby="ripartizione-title" style={{ background: '#fff', color: '#263b32', width: 'min(880px, 100%)', maxHeight: '92vh', overflowY: 'auto', borderRadius: 12, padding: 20, boxSizing: 'border-box' }}
      onKeyDown={e => { if (e.key === 'Escape' && !busy) onClose(); }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
        <h2 id="ripartizione-title" style={{ margin: 0 }}>Associa pagamento ai cedolini</h2>
        <button ref={closeRef} type="button" style={btn} disabled={busy} onClick={onClose} aria-label="Chiudi ripartizione">✕</button>
      </div>
      {errore && <div role="alert" style={{ color: '#aa3026', marginTop: 12 }}>{errore} <button type="button" style={btn} onClick={() => refresh()} disabled={busy}>Aggiorna anteprima</button></div>}
      {busy && <p role="status">Calcolo la ripartizione…</p>}
      {piano && <>
        <p><strong>{piano.dipendente}</strong> · Pagamento del {piano.data.split('-').reverse().join('/')} · <strong>{euro(piano.importo)}</strong></p>
        {piano.pagamento_esistente && <p style={{ color: '#35684f' }}>Pagamento già registrato: aggiorno il collegamento, senza contarlo di nuovo.</p>}
        {!!piano.possibili_duplicati?.length && <label style={{ display: 'block', marginBottom: 14 }}>Stesso dipendente, data e importo già in archivio: indica se è la stessa operazione.
          <select style={input} disabled={busy} value={collega} onChange={e => refresh(scelte, e.target.value)}>
            <option value="">Scegli come trattare la ricevuta</option>
            {piano.possibili_duplicati.map(r => <option key={r.key} value={r.key}>Collega a {r.causale || periodo(r)}</option>)}
            <option value="distinto">Confermo che è un altro pagamento distinto</option>
          </select>
        </label>}
        <p>Prima il cedolino scelto o indicato nella causale; poi i residui più vecchi. L'eccedenza resta un acconto sul prossimo cedolino.</p>
        <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', background: '#f2f5f1', padding: 12, borderRadius: 8 }}>
          <span>Scelto da te: <b>{euro(scelto)}</b></span>
          <span>Restante da ripartire: <b>{euro(restante)}</b></span>
        </div>
        {scelte.map((r, i) => <div key={`${r.anno}-${r.mese}`} style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 8 }}>
          <span>{i + 1}. Cedolino {periodo(r)} · {euro(r.importo)}</span>
          <button type="button" style={btn} disabled={busy} onClick={() => refresh(scelte.filter((_, j) => i !== j))}>Rimuovi</button>
        </div>)}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '14px 0' }}>
          <label style={{ flex: '1 1 230px' }}>Scegli il cedolino
            <select style={input} value={cedolino} onChange={e => scegli(e.target.value)} disabled={busy || restante <= 0}>
              <option value="">Automatico dai residui più vecchi</option>
              {piano.cedolini.filter(b => !scelte.some(r => r.anno === b.anno && r.mese === b.mese)).map(b => <option key={`${b.anno}-${b.mese}`} value={`${b.anno}-${b.mese}`}>
                {b.descrizione} · dovuto {euro(b.dovuto)} · residuo dopo ripartizione {euro(b.residuo)}
              </option>)}
            </select>
          </label>
          <label style={{ flex: '0 1 145px' }}>Quota €<input aria-label="Quota da assegnare" type="number" min="0.01" step="0.01" max={restante} style={input} value={quota} onChange={e => setQuota(e.target.value)} disabled={busy || !cedolino} /></label>
          <button type="button" style={{ ...btn, alignSelf: 'end' }} disabled={busy || !cedolino || restante <= 0} onClick={aggiungi}>Aggiungi cedolino</button>
        </div>
        <h3 style={{ marginBottom: 8 }}>Ripartizione risultante</h3>
        <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
          <thead><tr><th style={{ ...td, textAlign: 'left' }}>Cedolino</th><th style={td}>Quota del pagamento</th><th style={td}>Residuo cedolino</th></tr></thead>
          <tbody>{piano.quote.map(r => <tr key={`${r.anno}-${r.mese}`}><td style={{ ...td, textAlign: 'left' }}>{periodo(r)}<small style={{ display: 'block', color: '#66766e' }}>{r.criterio}</small></td><td style={td}>{euro(r.importo)}</td><td style={td}>{euro(r.residuo_cedolino)}</td></tr>)}</tbody>
        </table></div>
        <p><b>Acconto disponibile: {euro(piano.acconto)}</b></p>
        <p style={{ fontSize: 13 }}>Il bonifico viene scalato dal saldo progressivo una sola volta, alla data del pagamento.</p>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" style={btn} disabled={busy} onClick={onClose}>Annulla</button>
          <button type="button" style={{ ...btn, background: '#476957', color: '#fff' }} disabled={busy || !!errore || duplicato} onClick={salva}>Conferma ripartizione</button>
        </div>
      </>}
    </section>
  </div>, document.body);
}

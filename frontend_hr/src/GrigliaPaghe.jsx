import React from 'react';

const MESI = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic', '13ª', '14ª'];
const denaro = n => n == null ? 'Da leggere' : Number(n).toLocaleString('it-IT', { style: 'currency', currency: 'EUR' });
const chiave = r => `${r.dipendente_id || r.dipendente}:${r.anno}:${r.mese}`;

export function statoPeriodo(r) {
  if (r.avvisi_importo?.length || r.acconto_da_verificare || r.netto_pdf_da_verificare || r.busta == null) return 'Da verificare';
  if (!r.cedolino_pdf) return 'PDF mancante';
  if (r.riconciliato && r.stato === 'pagato' && r.erogato > 0 && r.fonte === 'banca') return 'Riconciliato';
  if (r.erogato > 0) return r.riconciliato && r.fonte === 'banca' ? 'Pagamento parziale / eccedenza' : 'Pagamento da verificare';
  return r.busta === 0 ? 'Saldo zero' : 'Pagamento non associato';
}

// Gli anni e le mensilità aggiuntive fanno parte della chiave. I PDF ancora
// da leggere integrano la cella esistente senza raddoppiare il dovuto.
export function righeGriglia(righe, daLeggere = []) {
  const periodi = new Map();
  for (const r of righe) {
    const key = chiave(r);
    const existing = periodi.get(key);
    periodi.set(key, existing ? { ...existing, ambiguo: true } : { ...r });
  }
  for (const r of daLeggere) {
    const key = chiave(r);
    if (!periodi.has(key)) periodi.set(key, { ...r, cedolino_pdf: true, busta: null, erogato: null, saldo: null });
    periodi.get(key).netto_pdf_da_verificare = true;
  }
  const gruppi = new Map();
  for (const r of periodi.values()) {
    const key = `${r.dipendente_id || r.dipendente}:${r.anno}`;
    if (!gruppi.has(key)) gruppi.set(key, { key, id: r.dipendente_id, nome: r.dipendente, anno: r.anno, mesi: {} });
    gruppi.get(key).mesi[r.mese] = r;
  }
  return [...gruppi.values()].sort((a, b) => b.anno - a.anno || a.nome.localeCompare(b.nome, 'it'));
}

export default function GrigliaPaghe({ righe, daLeggere, loading, onDipendente }) {
  const gruppi = righeGriglia(righe, daLeggere);
  const euro = n => n == null ? '—' : Number(n).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return <section aria-label="Griglia annuale paghe" className="paghe-grid-wrap">
    <div style={{ overflowX: 'auto' }}><table className="paghe-grid">
      <thead><tr><th>Dipendente / anno</th>{MESI.map(m => <th key={m}>{m}</th>)}<th>Buste</th><th>Erogato</th><th>Differenza</th></tr></thead>
      <tbody>{loading ? <tr><td colSpan={18}>Caricamento…</td></tr> : !gruppi.length ? <tr><td colSpan={18}>Nessuna busta con questi filtri.</td></tr> : gruppi.map(g => {
        const valori = Object.values(g.mesi);
        const totale = campo => valori.some(r => r.ambiguo || r[campo] == null) ? null : valori.reduce((s, r) => s + Number(r[campo]), 0);
        const buste = totale('busta'), erogato = totale('erogato');
        return <tr key={g.key}>
          <th scope="row"><button className="paghe-grid-name" onClick={() => onDipendente(g.id, g.nome)}>{g.nome}</button><span className="dc-muted"> · {g.anno}</span></th>
          {MESI.map((m, i) => {
            const r = g.mesi[i + 1];
            let txt = '·', color = '#9ba499', title = `${m} ${g.anno}: nessun dato`;
            if (r) {
              title = `${m} ${g.anno}: ${statoPeriodo(r)}; dovuto ${denaro(r.busta)}; erogato ${denaro(r.erogato)}`;
              if (r.ambiguo || r.netto_pdf_da_verificare || r.avvisi_importo?.length || r.acconto_da_verificare) { txt = '?'; color = '#7a3b32'; }
              else if (r.stato === 'pagato' && r.riconciliato && r.fonte === 'banca') { txt = '✓'; color = '#3d8168'; }
              else if (r.stato === 'in_attesa_busta') { txt = '+' + euro(r.erogato); color = '#7d5526'; }
              else if (r.stato === 'da_verificare' || r.busta == null) { txt = '?'; color = '#7a3b32'; }
              else if (r.saldo > 0) { txt = euro(r.saldo); color = '#b04a3a'; }
              else { txt = r.saldo < 0 ? '+' + euro(-r.saldo) : euro(r.saldo); color = '#3d8168'; }
            }
            return <td key={m} title={title} style={{ color, fontWeight: 600 }}>{txt}</td>;
          })}
          <td>{euro(buste)}</td><td>{euro(erogato)}</td><td>{buste == null || erogato == null ? '—' : euro(erogato - buste)}</td>
        </tr>;
      })}</tbody>
    </table></div>
    <p className="dc-muted" style={{ fontSize: 12, margin: '6px 10px' }}>✓ riconciliato · rosso = residuo · + = eccedenza o busta attesa · ? = da verificare · — = totale incompleto.</p>
  </section>;
}

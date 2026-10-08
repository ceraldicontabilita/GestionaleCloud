import React, { useState } from 'react';

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

export default function GrigliaPaghe({ righe, daLeggere, loading, misura, onMisura, onElenco, onPdf, onDipendente }) {
  const [periodo, setPeriodo] = useState(null);
  const gruppi = righeGriglia(righe, daLeggere);
  const campo = { dovuto: 'busta', pagamenti: 'erogato', saldo: 'saldo' }[misura];
  const titolo = { dovuto: 'Dovuto cedolini', pagamenti: 'Pagamenti attribuiti', saldo: 'Residuo da pagare', stato: 'Documenti e riconciliazione' }[misura];
  return <section className="dc-card" aria-label="Griglia annuale paghe">
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
      <strong>Griglia annuale</strong>
      <label>Mostra <select aria-label="Dati della griglia" value={misura} onChange={e => onMisura(e.target.value)}>
        <option value="dovuto">Importi cedolini</option><option value="pagamenti">Pagamenti recuperati / attribuiti</option>
        <option value="saldo">Residuo da pagare</option><option value="stato">Documenti e riconciliazione</option>
      </select></label>
    </div>
    <p className="dc-muted">{titolo}. Premi un mese per vedere netto, recupero acconto, fonte e pagamenti. “—” significa nessun dato per quel periodo. Scorri orizzontalmente per gli altri mesi.</p>
    {loading ? <p role="status">Aggiornamento griglia…</p> : <div style={{ overflowX: 'auto', maxHeight: '65vh' }}>
      <table className="paghe-grid">
        <thead><tr><th scope="col">Dipendente / anno</th>{MESI.map(m => <th scope="col" key={m}>{m}</th>)}{campo && <th scope="col">Totale noto</th>}</tr></thead>
        <tbody>{!gruppi.length && <tr><td colSpan={campo ? 16 : 15}>Nessun dato con questi filtri.</td></tr>}
          {gruppi.map(g => {
            const values = Object.values(g.mesi);
            const noti = campo ? values.filter(r => !r.ambiguo && r[campo] != null) : [];
            const parziale = campo && noti.length !== values.length;
            return <tr key={g.key}>
              <th scope="row"><button className="paghe-grid-name" disabled={!g.id} onClick={() => onDipendente(g.id, g.nome)}>{g.nome}</button><br />{g.anno}</th>
              {MESI.map((m, i) => {
                const r = g.mesi[i + 1];
                if (!r) return <td key={m} title={`${m} ${g.anno}: nessun dato`}>—</td>;
                const stato = r.ambiguo ? 'Più righe: verificare' : statoPeriodo(r);
                const label = r.ambiguo ? 'Da verificare' : campo ? denaro(r[campo]) : stato;
                return <td key={m}><button className={`paghe-grid-cell ${stato === 'Riconciliato' ? 'is-reconciled' : stato.includes('verificare') || stato === 'PDF mancante' ? 'is-warning' : ''}`}
                  aria-label={`${g.nome}, ${m} ${g.anno}: ${label}, ${stato}`} onClick={() => setPeriodo(r)}
                  title={`Netto PDF: ${denaro(r.netto_stampato)}\nNetto confermato: ${denaro(r.netto_confermato)}\nRecupero acconto: ${denaro(r.acconto_recuperato)}\nDovuto: ${denaro(r.busta)}\nPagamenti: ${denaro(r.erogato)}\n${stato}`}>
                  <span>{label}</span>{campo && <small>{stato}</small>}
                </button></td>;
              })}
              {campo && <td><strong>{noti.length ? denaro(noti.reduce((a, r) => a + Number(r[campo]), 0)) : '—'}</strong>{parziale && <small>Parziale: importi da verificare</small>}</td>}
            </tr>;
          })}
        </tbody>
      </table>
    </div>}
    <p className="dc-muted" style={{ fontSize: 12 }}>PDF mancante = esiste un importo o un pagamento, ma manca il documento. Un importo uguale al pagamento non basta per riconciliare. Il recupero acconto è una trattenuta in busta, non prova di pagamento.</p>
    {periodo && <div className="paghe-grid-overlay" onClick={() => setPeriodo(null)}>
      <section className="paghe-grid-dialog" role="dialog" aria-modal="true" aria-label="Dettaglio mese" onClick={e => e.stopPropagation()} onKeyDown={e => { if (e.key === 'Escape') setPeriodo(null); }}>
        <h3>{periodo.dipendente} · {MESI[periodo.mese - 1]} {periodo.anno}</h3>
        <p>{periodo.ambiguo ? 'Più righe per questo periodo: verifica i documenti prima di usare gli importi.' : statoPeriodo(periodo)}</p>
        <dl className="paghe-grid-values">
          <dt>Netto estratto dal PDF</dt><dd>{denaro(periodo.netto_stampato)}</dd>
          <dt>Netto confermato da elenco</dt><dd>{periodo.netto_confermato == null ? 'Non presente' : denaro(periodo.netto_confermato)}</dd>
          <dt>Recupero acconto in busta</dt><dd>{denaro(periodo.acconto_recuperato)}</dd>
          <dt>Dovuto del periodo</dt><dd>{denaro(periodo.busta)}</dd>
          <dt>Pagamenti attribuiti</dt><dd>{denaro(periodo.erogato)}</dd>
          <dt>Residuo da pagare</dt><dd>{denaro(periodo.saldo)}</dd>
        </dl>
        {periodo.avvisi_importo?.length > 0 && <p role="alert">Importi discordanti: apri la riga nell'elenco per confrontare le fonti.</p>}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {periodo.cedolino_pdf && <button className="dc-btn" onClick={() => onPdf(periodo)}>Apri PDF</button>}
          <button className="dc-btn" onClick={() => { onElenco(periodo); setPeriodo(null); }}>Mostra nell'elenco</button>
          <button autoFocus className="dc-btn" onClick={() => setPeriodo(null)}>Chiudi</button>
        </div>
      </section>
    </div>}
  </section>;
}

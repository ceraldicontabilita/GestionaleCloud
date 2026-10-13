import React from 'react';

const euro = n => n == null ? '—' : Number(n).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const data = value => value ? value.slice(0, 10).split('-').reverse().join('/') : '—';
const destra = { textAlign: 'right', whiteSpace: 'nowrap' };
const MESI = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre'];
const periodo = r => r.mese === 13 ? `13ª ${r.anno}` : r.mese === 14 ? `14ª ${r.anno}` : `${MESI[r.mese - 1] || r.mese} ${r.anno}`;

export default function PrimaNotaPaghe({ prospetto }) {
  if (prospetto.loading) return <p className="dc-muted">Carico…</p>;
  if (prospetto.errore) return <p role="alert">Impossibile caricare il prospetto. Chiudi e riapri la scheda per riprovare.</p>;
  const mensili = prospetto.mensili || [];
  const competenze = prospetto.competenze || [];
  if (!mensili.length && !competenze.length) return <p className="dc-muted">Nessun dato.</p>;
  return <>
    {prospetto.perDipendente?.length > 0 && <>
      <h3>Totali per dipendente</h3>
      <div style={{ overflowX: 'auto' }}>
        <table className="dc-table" aria-label="Totali per dipendente" style={{ minWidth: 560 }}>
          <thead><tr><th>Dipendente</th><th style={destra}>Dovuto €</th><th style={destra}>Pagato €</th><th style={destra}>Saldo €</th></tr></thead>
          <tbody>{prospetto.perDipendente.map(r => <tr key={r.dipendente_id}>
            <td><strong>{r.dipendente}</strong></td><td style={destra}>{euro(r.dovuto)}</td><td style={destra}>{euro(r.pagato)}</td>
            <td style={{ ...destra, color: r.saldo > 0 ? '#b04a3a' : '#3d8168', fontWeight: 700 }}>{euro(r.saldo)}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </>}
    {mensili.length > 0 && <>
      <h3>Totali mensili e saldo progressivo</h3>
      <p className="dc-muted">I cedolini maturano nel mese di competenza; bonifici e acconti incidono nel mese della data effettiva del pagamento.</p>
      <div style={{ overflowX: 'auto' }} tabIndex={0} aria-label="Totali mensili paghe">
        <table className="dc-table" aria-label="Totali mensili e saldo progressivo" style={{ minWidth: 760 }}>
          <thead><tr><th>Mese</th><th style={destra}>Cedolini €</th><th style={destra}>Altri dovuti €</th><th style={destra}>Bonifici €</th><th style={destra}>Acconti €</th><th style={destra}>Pagato totale €</th><th style={destra}>Saldo progressivo €</th></tr></thead>
          <tbody>{mensili.map(r => <tr key={`${r.anno}-${r.mese}`}>
            <td><strong>{periodo(r)}</strong></td><td style={destra}>{euro(r.cedolini ?? r.busta)}</td><td style={destra}>{euro(r.altri_dovuti)}</td>
            <td style={destra}>{euro(r.bonifico)}</td><td style={destra}>{euro(r.acconti)}</td><td style={destra}>{euro(r.erogato)}</td>
            <td style={{ ...destra, color: r.saldo_progressivo > 0 ? '#b04a3a' : '#3d8168', fontWeight: 700 }}>{euro(r.saldo_progressivo)}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </>}
    {competenze.length > 0 && <>
    <h3>Collegamenti per mensilità</h3>
    <p className="dc-muted">Una riga per mensilità, con tutti i pagamenti attribuiti e le loro date effettive.</p>
    <div style={{ overflowX: 'auto' }} tabIndex={0} aria-label="Prospetto per competenza">
      <table className="dc-table" aria-label="Cedolini e pagamenti per mensilità" style={{ minWidth: 680 }}>
        <thead><tr><th>Mensilità / movimento</th><th style={destra}>Dovuto €</th><th>Pagamenti collegati</th><th style={destra}>Totale pagato €</th><th style={destra}>Differenza €</th></tr></thead>
        <tbody>{competenze.map(r => <tr key={r.key}>
          <td style={{ minWidth: 170, verticalAlign: 'top' }}>
            <strong>{r.descrizione}</strong>
            {r.buste.map((b, i) => <div key={i} className="dc-muted" style={{ fontSize: 12 }}>
              {data(b.data)} · {b.descrizione}{b.avviso && <div>{b.avviso}</div>}
            </div>)}
            {!!r.mese && !r.buste.length && <div className="dc-muted">Cedolino non disponibile</div>}
          </td>
          <td style={{ ...destra, verticalAlign: 'top' }}>{euro(r.dovuto)}</td>
          <td style={{ minWidth: 200, verticalAlign: 'top' }}>
            {r.pagamenti.map((p, i) => <div key={i} style={{ marginBottom: 5 }} title={p.descrizione}>
              <span>{data(p.data)}</span> · <strong>{euro(p.avere)} €</strong>
              {p.avviso && <div className="dc-muted" style={{ fontSize: 12 }}>{p.avviso}</div>}
            </div>)}
            {r.coperture.map((p, i) => <div key={`copertura-${i}`} style={{ marginBottom: 5 }}>
              Pagato con bonifico del {data(p.data)} · <a href={`#pn-${p.riferimento}`}>più mensilità</a>
            </div>)}
            {!r.pagamenti.length && !r.coperture.length && <span className="dc-muted">Nessun pagamento collegato</span>}
          </td>
          <td id={`pn-${r.key}`} style={{ ...destra, verticalAlign: 'top' }}>{r.pagamenti.length ? euro(r.pagato) : r.coperture.length ? 'Cumulativo' : '—'}</td>
          <td style={{ ...destra, verticalAlign: 'top', color: r.differenza > 0 ? '#b04a3a' : '#3d8168' }}>
            {euro(r.differenza)}{r.differenza < 0 && <div style={{ fontSize: 12 }}>Eccedenza attribuita</div>}
          </td>
        </tr>)}</tbody>
      </table>
    </div>
    </>}
    <p style={{ fontWeight: 700 }}>Saldo complessivo: {euro(prospetto.saldo_finale)} € <span className="dc-muted">(positivo = ancora da pagare; importi sconosciuti esclusi)</span></p>
    {prospetto.righe?.length > 0 && <details style={{ marginTop: 14 }}>
      <summary style={{ cursor: 'pointer' }}>Movimenti per data e saldo progressivo</summary>
      <div style={{ overflowX: 'auto', marginTop: 8 }}><table className="dc-table" aria-label="Movimenti cronologici" style={{ minWidth: 560 }}>
        <thead><tr><th>Data / movimento</th><th style={destra}>Dovuto €</th><th style={destra}>Pagamenti €</th><th style={destra}>Saldo progressivo €</th></tr></thead>
        <tbody>{prospetto.righe.map((r, i) => <tr key={i}>
          <td>{data(r.data)}<div>{r.descrizione}</div>{r.avviso && <small className="dc-muted">{r.avviso}</small>}</td>
          <td style={destra}>{euro(r.dare)}</td><td style={destra}>{euro(r.avere)}</td><td style={destra}>{euro(r.saldo)}</td>
        </tr>)}</tbody>
      </table></div>
    </details>}
  </>;
}

import React from 'react';
import { Button } from './ds';

const labels = { MODELLO_770: '770', DICHIARAZIONE_IVA: 'IVA', REDDITI_SC: 'Redditi SC', DICHIARAZIONE_IRAP: 'IRAP', LIPE: 'LIPE', ELENCO_PERCIPIENTI: 'Percipienti' };
const euros = cents => cents == null ? 'Non disponibile' : new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(cents / 100);

export default function DeclarationDossier({ dossier, onOpen }) {
  const submissions = new Map();
  for (const original of dossier.originals || []) {
    const key = original.declaration_identifier || `file:${original.id}`;
    if (!submissions.has(key)) submissions.set(key, []);
    submissions.get(key).push(original);
  }
  const openFile = file => onOpen({ url: file.pdf_url, titolo: file.filename || 'Originale' });
  const checks = dossier.withholding_check?.groups || [];
  const paymentStates = { PAGATO: 'Pagati', PAGATO_RAVVEDIMENTO: 'Pagati con ravvedimento',
    QUIETANZA_MANCANTE: 'Quietanza mancante', IMPORTO_DIVERSO: 'Importi diversi', DA_VERIFICARE: 'Da verificare', NESSUN_VERSAMENTO: 'Nessun versamento dichiarato' };
  const uniqueFiles = files => [...new Map(files.map(file => [file.pdf_url, file])).values()];
  const fileRow = file => <div className="declaration-dossier-file" key={file.id}>
    <div><strong>{file.role || 'Quietanza di pagamento'}</strong>
      <div className="fiscal-muted">{file.filename}</div>
      {file.page_count != null && <small>{file.page_count} pagine</small>}
    </div>
    <Button size="sm" variant="secondary" disabled={!file.pdf_url} onClick={() => openFile(file)} aria-label={`Apri PDF ${file.filename}`}>Apri PDF originale</Button>
    {!!file.copies?.length && <details className="declaration-dossier-copies"><summary>{file.copies.length} copie identiche</summary>
      {file.copies.map(copy => <div key={copy.id}><span>{copy.filename}</span>{' '}
        <Button size="sm" variant="secondary" onClick={() => openFile(copy)}>Apri copia</Button></div>)}
    </details>}
  </div>;
  return <article className="fiscal-record declaration-dossier" data-testid="declaration-dossier">
    <h3>{labels[dossier.document_type] || dossier.document_type} · Anno d’imposta {dossier.tax_year || 'da verificare'}</h3>
    <p className="fiscal-muted">{dossier.taxpayer_name || 'Contribuente'} · {dossier.taxpayer_id || 'Codice fiscale da verificare'}
      {!!dossier.model_years?.length && <> · Modello {dossier.model_years.join(', ')}</>}</p>
    <p>{dossier.original_count} PDF originali · {dossier.receipt_count || 0} quietanze di pagamento</p>
    <details>
      <summary className="declaration-dossier-toggle">Apri fascicolo</summary>
      {checks.length > 0 && <section aria-label="Riscontro ritenute dichiarate" className="declaration-withholdings">
        <h4>Tributi dichiarati e quietanze</h4>
        <p>{dossier.withholding_check.declared_rows} righe ST/SV · {Object.entries(dossier.withholding_check.counts).map(([state, n]) => `${paymentStates[state] || state}: ${n}`).join(' · ')}</p>
        <p className="fiscal-muted">Il pagamento è provato dalla quietanza. La casella di ravvedimento e gli interessi sono letti dal 770; le sanzioni sono mostrate separatamente. Se manca la quietanza, il pagamento resta da documentare.</p>
        {checks.map(check => <details key={check.id} className={`declaration-withholding declaration-withholding-${check.stato.toLowerCase()}`}>
          <summary>
            <strong>{check.codice || 'Codice da verificare'} · {check.mese ? `${String(check.mese).padStart(2, '0')}/` : ''}{check.anno}</strong>
            <span>{check.stato_label}</span>
            {check.warnings.length > 0 && <small>Note da leggere: {check.warnings.length}</small>}
            <span>Dichiarato versato: {euros(check.dichiarato_cents)} · Quietanzato: {check.payments.length ? euros(check.quietanzato_cents) : 'Non documentato'}</span>
          </summary>
          <p>Invio {check.submission} · Data di versamento nel 770: {check.data_dichiarata || 'Non indicata'}</p>
          {check.rows.map((row, i) => <div key={i} className="declaration-withholding-source">
            <strong>{row.rigo}{row.modulo && <> · modulo {row.modulo}</>}</strong>
            <p>Ritenute: {euros(row.ritenute_operate_cents)} · Versato: {euros(row.importo_versato_cents)}
              {row.interessi_cents != null && <> · Interessi inclusi: {euros(row.interessi_cents)}</>}
              {row.crediti_scomputo_cents != null && <> · Crediti a scomputo: {euros(row.crediti_scomputo_cents)}</>}
              {' · '}Ravvedimento nel 770: {row.ravvedimento ? 'Sì (X)' : 'Casella non marcata'}</p>
            {uniqueFiles(row.sources).map(file => <Button key={file.pdf_url} size="sm" variant="secondary" onClick={() => openFile(file)}>Apri 770 · pagina {file.page}</Button>)}
          </div>)}
          {check.payments.map((payment, i) => <div key={i}>
            <p><strong>Quietanza del {payment.data}: {euros(payment.importo_cents)}</strong>{payment.protocollo && <> · Protocollo {payment.protocollo}</>}</p>
            <p className="fiscal-muted">Riferimento in quietanza: {payment.receipt_row?.periodo_riferimento || `${payment.receipt_row?.mese || '—'}/${payment.receipt_row?.anno || '—'}`}{payment.receipt_row?.ente && <> · Ente {payment.receipt_row.ente}</>}</p>
            {uniqueFiles(payment.quietanze).map(file => <Button key={file.pdf_url} size="sm" variant="secondary" onClick={() => openFile(file)}>Apri quietanza del tributo</Button>)}
          </div>)}
          {check.sanzioni.map((sanction, i) => <div key={i}>
            <p>Sanzione {sanction.row.codice}: {euros(sanction.row.importo_debito_cents)} · {sanction.data}</p>
            {uniqueFiles(sanction.quietanze).map(file => <Button key={file.pdf_url} size="sm" variant="secondary" onClick={() => openFile(file)}>Apri quietanza sanzione</Button>)}
          </div>)}
          {check.differenza_cents != null && check.differenza_cents !== 0 && <p>Differenza rispetto al versato dichiarato: {euros(check.differenza_cents)}</p>}
          {check.warnings.map((warning, i) => <p className="declaration-withholding-warning" key={i}>{warning}</p>)}
          {check.candidates.length > 0 && <details><summary>Altre quietanze dello stesso codice e periodo</summary>
            {check.candidates.map((candidate, i) => <div key={i}><p>{candidate.data} · {euros(candidate.importo_cents)}{candidate.anni_riferimento && <> · Anno di riferimento {candidate.anni_riferimento.join(', ')}</>}</p>
              {uniqueFiles(candidate.quietanze).map(file => <Button key={file.pdf_url} size="sm" variant="secondary" onClick={() => openFile(file)}>Apri quietanza da confrontare</Button>)}
            </div>)}
          </details>}
        </details>)}
      </section>}
      <h4>PDF della dichiarazione</h4>
      {[...submissions.entries()].map(([id, files]) => <section className="declaration-dossier-submission" key={id}>
        <h5>{id.startsWith('file:') ? 'Documento da identificare' : `Invio ${id}`}</h5>
        {files[0].filed_at && <p className="fiscal-muted">Presentato il {files[0].filed_at}</p>}
        {files.map(fileRow)}
      </section>)}
      <h4>Quietanze dei tributi dell’anno</h4>
      <p className="fiscal-muted">Collegate per contribuente e tributo dell’anno, oppure tramite il riscontro ST/SV. Il riferimento stampato sulla quietanza resta visibile. Consultabili anche senza modello F24.</p>
      {(dossier.quietanze || []).map(payment => <section key={payment.chiave} className="declaration-dossier-submission">
        <strong>{payment.data || 'Data non indicata'} · Saldo della quietanza {euros(payment.importo_cents)}</strong>
        {payment.protocollo && <p className="fiscal-muted">Protocollo {payment.protocollo}</p>}
        <ul>{(payment.tax_rows || []).map((row, i) => <li key={i}>
          <strong>{row.codice}</strong> · {row.mese ? `${String(row.mese).padStart(2, '0')}/` : ''}{row.anno}
          {' · '}Debito {euros(row.importo_debito_cents)}{row.importo_credito_cents > 0 && <> · Credito {euros(row.importo_credito_cents)}</>}
        </li>)}</ul>
        {(payment.quietanze || []).map(fileRow)}
      </section>)}
      {!dossier.quietanze?.length && <p>Nessuna quietanza pertinente presente in archivio.</p>}
    </details>
  </article>;
}

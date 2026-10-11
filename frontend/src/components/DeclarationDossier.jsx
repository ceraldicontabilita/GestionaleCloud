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
      <h4>PDF della dichiarazione</h4>
      {[...submissions.entries()].map(([id, files]) => <section className="declaration-dossier-submission" key={id}>
        <h5>{id.startsWith('file:') ? 'Documento da identificare' : `Invio ${id}`}</h5>
        {files[0].filed_at && <p className="fiscal-muted">Presentato il {files[0].filed_at}</p>}
        {files.map(fileRow)}
      </section>)}
      <h4>Quietanze dei tributi dell’anno</h4>
      <p className="fiscal-muted">Collegate per contribuente, codice tributo e anno di riferimento. Le quietanze sono consultabili anche senza modello F24.</p>
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

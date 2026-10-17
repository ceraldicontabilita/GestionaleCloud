import React, { useEffect, useState } from 'react';
import api from '../../api';
import { Badge, Button } from '../ds';
import { formatDateIT } from '../../lib/utils';

const evidenceLabels = {
  MODEL_ONLY: 'Modello: non prova il pagamento',
  DOCUMENTARY: 'Prova documentale',
  BANK: 'Movimento bancario',
  PORTAL: 'Fotografia del portale',
  EVENT: 'Evento del fascicolo',
};
const stageLabels = {
  DOCUMENTED: 'Documento presente',
  NOT_DOCUMENTED: 'Documento non presente nel fascicolo',
  NOT_APPLICABLE: 'Passaggio non previsto per questo percorso',
};
const dateLabels = {
  DOCUMENT_DATE: 'Data del documento', ISSUE_DATE: 'Emissione',
  PREPARATION_DATE: 'Data di predisposizione', EXPLICIT_DUE_DATE: 'Scadenza riportata',
  NOTIFICATION_DATE: 'Notifica', PAYMENT_DATE: 'Data del pagamento',
  DUE_DATE: 'Scadenza', ROLE_DATE: 'Data del ruolo',
  ROLE_FORMATION_DATE: 'Formazione del ruolo', ROLE_EXECUTIVITY_DATE: 'Esecutività del ruolo',
  ROLE_DELIVERY_DATE: 'Consegna del ruolo', BANK_BOOKING_DATE: 'Data contabile bancaria',
  SNAPSHOT_DATE: 'Data della consultazione', PORTAL_DATE: 'Data della consultazione',
  PORTAL_CAPTURE_DATE: 'Data della consultazione', PLAN_APPLICATION_DATE: 'Data della domanda',
  EVENT_EFFECTIVE_DATE: 'Data dell’evento',
  EVENT_DATE: 'Data dell’evento',
};
const money = cents => new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(cents / 100);

// Il visualizzatore usa il client autenticato: accettiamo soltanto indirizzi
// interni restituiti dal server, mai URL esterni o schemi eseguibili.
const internalUrl = url => typeof url === 'string' && /^\/api\/[^/]/.test(url)
  && !/[\\\s\u0000-\u001f\u007f]/.test(url) ? url : null;

function DossierEvent({ event, dated, onOpen, onOpenUrl }) {
  const url = internalUrl(event.url);
  const title = event.filename || event.label || 'Documento del fascicolo';
  const canOpenUrl = url && onOpenUrl;
  const canOpenDocument = event.document_id && onOpen;
  const evidenceLabel = event.evidence_level === 'DOCUMENTARY'
    && ['QUIETANZA_F24', 'PAYMENT_RECEIPT'].includes(event.event_type)
    ? 'Quietanza documentale' : evidenceLabels[event.evidence_level] || 'Tipo di prova da verificare';
  const open = () => {
    if (canOpenUrl) onOpenUrl(url, title);
    else if (canOpenDocument) onOpen(event.document_id, title);
  };
  return <li style={{ marginBottom: 14 }}>
    <div>
      {dated && <><time dateTime={event.date}>{formatDateIT(event.date)}</time>{' · '}</>}
      <strong>{event.label || 'Documento del fascicolo'}</strong>
      {event.amount_cents != null && <> · {money(event.amount_cents)}</>}
    </div>
    <div className="fiscal-muted" style={{ marginTop: 4 }}>
      {dated && <>{dateLabels[String(event.date_kind || '').toUpperCase()] || 'Data documentata'} · </>}
      <Badge variant={event.evidence_level === 'MODEL_ONLY' ? 'warning' : 'info'}>
        {evidenceLabel}
      </Badge>
    </div>
    {event.filename && <div className="fiscal-muted" style={{ marginTop: 4 }}>{event.filename}</div>}
    {(event.notes || []).map((note, index) => <div key={index} className="fiscal-muted" style={{ marginTop: 4 }}>{note}</div>)}
    {(canOpenUrl || canOpenDocument) && <Button size="sm" variant="secondary" style={{ marginTop: 6 }}
      onClick={open} aria-label={`Apri ${title}`}>Apri documento</Button>}
  </li>;
}

export default function CollectionDossier({ claimId, onOpen, onOpenUrl }) {
  const [opened, setOpened] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const dossier = result?.claimId === claimId ? result.data : null;

  useEffect(() => {
    if (!opened || !claimId || dossier) return undefined;
    let active = true;
    setLoading(true);
    setError(false);
    api.get(`/api/fiscal/collections/${encodeURIComponent(claimId)}/dossier`)
      .then(response => {
        if (active) {
          setLoading(false);
          setResult({ claimId, data: response.data });
        }
      })
      .catch(() => {
        if (active) {
          setLoading(false);
          setError(true);
        }
      });
    return () => { active = false; };
  }, [opened, claimId, dossier, attempt]);

  return <details className="fiscal-collection-details" style={{ marginTop: 10 }}
    onToggle={event => setOpened(event.currentTarget.open)}>
    <summary>Cronologia del fascicolo</summary>
    {opened && <div style={{ marginTop: 10 }}>
      <p className="fiscal-muted">La cronologia raccoglie i documenti già collegati. La quietanza ufficiale con esito positivo prova il versamento attribuito anche senza riscontro bancario disponibile. Il modello F24 da pagare e la ricevuta di invio restano distinti. Il collegamento non invia richieste di sgravio.</p>
      {loading && <p role="status">Caricamento della cronologia…</p>}
      {error && <div role="alert">
        <p>Non è stato possibile caricare la cronologia del fascicolo.</p>
        <Button size="sm" variant="secondary" onClick={() => setAttempt(value => value + 1)}>Riprova</Button>
      </div>}
      {dossier && <>
        <Button size="sm" variant="secondary" onClick={() => {
          setResult(null);
          setAttempt(value => value + 1);
        }}>Aggiorna cronologia</Button>
        {dossier.path && <section aria-label="Percorso della posizione">
          <h4>{dossier.path.label || 'Percorso della posizione'}</h4>
          <ul>{(dossier.path.steps || []).map((step, index) => <li key={`${step.code}-${index}`}>
            <strong>{step.label}</strong>{' · '}{stageLabels[step.status] || 'Da verificare'}
          </li>)}</ul>
          <p className="fiscal-muted">Un documento non presente nel fascicolo non dimostra che il passaggio non sia avvenuto.</p>
        </section>}
        {!!dossier.findings?.length && <section aria-label="Verifiche del fascicolo">
          <h4>Verifiche da leggere</h4>
          {dossier.findings.map((finding, index) => <p key={`${finding.code}-${index}`}
            style={{ color: finding.severity === 'warning' ? '#92400e' : undefined }}>{finding.message}</p>)}
        </section>}
        <section aria-label="Documenti in ordine di data">
          <h4>Documenti in ordine di data</h4>
          {dossier.timeline?.length ? <ol>{dossier.timeline.map(event => <DossierEvent
            key={event.id} event={event} dated onOpen={onOpen} onOpenUrl={onOpenUrl} />)}</ol>
            : <p>Nessun documento con data documentata presente nel fascicolo.</p>}
        </section>
        {!!dossier.undated?.length && <section aria-label="Documenti senza data documentata">
          <h4>Documenti senza data documentata</h4>
          <p className="fiscal-muted">Questi documenti restano collegati; la loro posizione nella cronologia è da verificare.</p>
          <ul>{dossier.undated.map(event => <DossierEvent key={event.id} event={event}
            onOpen={onOpen} onOpenUrl={onOpenUrl} />)}</ul>
        </section>}
      </>}
    </div>}
  </details>;
}

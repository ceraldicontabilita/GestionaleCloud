import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import api from '../api';
import { PageLayout } from '../components/PageLayout';
import LinkedEvidencePanel from '../components/LinkedEvidencePanel';
import { Badge, Button, Card, StatCard } from '../components/ds';

const TABS = [
  ['tributi', 'Tributi'],
  ['tributi-pagati', 'Tributi pagati'],
  ['f24', 'F24 e crediti'],
  ['codici-tributo', 'Codici tributo'],
  ['crosswalk-riscossione', 'Crosswalk riscossione'],
  ['riscossione', 'Riscossione'],
  ['ader', 'Snapshot AdeR'],
];

const endpointFor = (tab, f24Filters = {}) => {
  if (tab === 'f24') {
    const params = new URLSearchParams();
    if (f24Filters.year) params.set('year', f24Filters.year);
    if (f24Filters.taxCode) params.set('tax_code', f24Filters.taxCode);
    if (f24Filters.creditsOnly) params.set('credits_only', 'true');
    params.set('limit', '1000');
    return `/api/fiscal/f24-rows?${params.toString()}`;
  }
  return ({
    tributi: '/api/fiscal/obligations',
    'tributi-pagati': '/api/fiscal/obligations?status=PAID_ON_TIME',
    'codici-tributo': '/api/documenti/tax-codes/status',
    'crosswalk-riscossione': '/api/fiscal/crosswalk',
    riscossione: '/api/fiscal/collections',
    ader: '/api/fiscal/ader-snapshots',
  }[tab]);
};

const labelForClaim = item => item.document_number || item.collection_number || item.cartella_number_original || item.id;
const euro = value => value == null ? 'Non disponibile' : new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(value);

export default function SituazioneFiscale() {
  const location = useLocation();
  const tab = TABS.find(([id]) => location.pathname.endsWith(`/${id}`))?.[0] || 'tributi';
  const [summary, setSummary] = useState(null);
  const [items, setItems] = useState([]);
  const [review, setReview] = useState({ findings: [] });
  const [selected, setSelected] = useState(null);
  const [tabMeta, setTabMeta] = useState(null);
  const [aderRelated, setAderRelated] = useState({ ratePlans: [], settlements: [] });
  const [loading, setLoading] = useState(true);
  const [f24Year, setF24Year] = useState('');
  const [f24TaxCode, setF24TaxCode] = useState('');
  const [f24CreditsOnly, setF24CreditsOnly] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [summaryResponse, dataResponse, reviewResponse] = await Promise.all([
        api.get('/api/fiscal/summary'), api.get(endpointFor(tab, {
          year: f24Year, taxCode: f24TaxCode, creditsOnly: f24CreditsOnly,
        })), api.get('/api/fiscal/review'),
      ]);
      setSummary(summaryResponse.data);
      const payload = dataResponse.data || {};
      setItems(payload.items || (tab === 'codici-tributo' ? [payload] : []));
      setTabMeta(payload.latest_import || null);
      setAderRelated({ ratePlans: payload.rate_plans || [], settlements: payload.settlements || [] });
      setReview(reviewResponse.data || { findings: [] });
    } catch (error) {
      setItems([]);
      toast.error('Situazione fiscale non disponibile', { description: error.response?.data?.detail || error.message });
    } finally { setLoading(false); }
  }, [tab, f24Year, f24TaxCode, f24CreditsOnly]);

  useEffect(() => { load(); }, [load]);

  const download = async (path, filename) => {
    try {
      const response = await api.get(path, { responseType: 'blob' });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a'); link.href = url; link.download = filename;
      document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
    } catch (error) {
      toast.error('Download non riuscito', { description: error.response?.data?.detail || error.message });
    }
  };

  const openDocument = async documentId => {
    try {
      const response = await api.get(`/api/fiscal/documents/${encodeURIComponent(documentId)}/content`, { responseType: 'blob' });
      const url = URL.createObjectURL(response.data);
      window.open(url, '_blank', 'noopener,noreferrer');
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      toast.error('Prova documentale non disponibile', { description: error.response?.data?.detail || error.message });
    }
  };

  const counts = summary?.counts || {};
  const activeLabel = useMemo(() => TABS.find(([id]) => id === tab)?.[1], [tab]);
  return (
    <PageLayout title="Situazione fiscale" icon="⚖️"
      subtitle="Obblighi, pagamenti, cartelle e prove restano distinti e verificabili"
      actions={<><Button variant="secondary" onClick={load} disabled={loading}>Aggiorna</Button>
        <Button variant="secondary" onClick={() => download('/api/fiscal/dossier.pdf', 'dossier_fiscale.pdf')}>Dossier PDF</Button>
        <Button onClick={() => download('/api/fiscal/evidence-package.zip', 'evidence_fiscale.zip')}>Pacchetto prove</Button></>}>
      <nav aria-label="Sezioni situazione fiscale" style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
        {TABS.map(([id, label]) => <Link key={id} to={`/situazione-fiscale/${id}`}
          style={{ padding: '8px 12px', borderRadius: 8, textDecoration: 'none', fontWeight: 700,
            background: tab === id ? '#0f2744' : '#e2e8f0', color: tab === id ? '#fff' : '#0f2744' }}>{label}</Link>)}
      </nav>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: 12, marginBottom: 18 }}>
        <StatCard label="Documenti" value={counts.documents || 0} accent="primary" />
        <StatCard label="Obblighi" value={counts.obligations || 0} accent="primary" />
        <StatCard label="Pagamenti" value={counts.payments || 0} accent="success" />
        <StatCard label="Cartelle" value={counts.collection_claims || 0} accent="warning" />
        <StatCard label="Snapshot AdeR" value={counts.ader_snapshots || 0} accent="primary" />
        <StatCard label="Da verificare" value={summary?.requires_review || 0} accent="danger" />
      </div>
      {(review.findings || []).length > 0 && <Card style={{ marginBottom: 18 }} bodyStyle={{ padding: 16 }}>
        <h3 style={{ marginTop: 0 }}>Controlli deterministici</h3>
        {review.findings.slice(0, 10).map((item, index) => <div key={`${item.code}-${index}`} style={{ padding: '8px 0', borderTop: '1px solid #e2e8f0' }}>
          <Badge variant="warning">{item.code}</Badge> {item.message}
        </div>)}
      </Card>}
      <Card bodyStyle={{ padding: 16 }}>
        <h3 style={{ marginTop: 0 }}>{activeLabel}</h3>
        {tab === 'f24' && <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'end', marginBottom: 14 }}>
          <label>Anno<br /><select value={f24Year} onChange={event => setF24Year(event.target.value)} style={{ padding: 8 }}>
            <option value="">Tutti</option>{[2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019].map(year => <option key={year}>{year}</option>)}
          </select></label>
          <label>Codice tributo<br /><input value={f24TaxCode} onChange={event => setF24TaxCode(event.target.value.trim())} placeholder="es. 1704" style={{ padding: 8, width: 130 }} /></label>
          <label style={{ paddingBottom: 8 }}><input type="checkbox" checked={f24CreditsOnly} onChange={event => setF24CreditsOnly(event.target.checked)} /> Solo righe a credito</label>
        </div>}
        {tab === 'ader' && tabMeta && <div style={{ margin: '0 0 14px', padding: '12px 14px', borderRadius: 10, background: '#eef6ff', border: '1px solid #bfdbfe' }}>
          <strong>Ultimo archivio verificato:</strong> snapshot {tabMeta.snapshot_date || 'data non disponibile'} · {tabMeta.analytic_count || 0} posizioni · SHA-256 {String(tabMeta.dataset_sha256 || '').slice(0, 16)}…
        </div>}
        {tab === 'ader' && (aderRelated.ratePlans.length > 0 || aderRelated.settlements.length > 0) && <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', gap: 12, marginBottom: 16 }}>
          <section aria-labelledby="ader-rate-plans" style={{ padding: 14, borderRadius: 10, border: '1px solid #cbd5e1', background: '#f8fafc' }}>
            <h4 id="ader-rate-plans" style={{ margin: '0 0 10px' }}>Piani rateali</h4>
            {aderRelated.ratePlans.length === 0 && <p style={{ margin: 0 }}>Nessun piano importato.</p>}
            {aderRelated.ratePlans.map(plan => <div key={plan.id} style={{ padding: '10px 0', borderTop: '1px solid #e2e8f0' }}>
              <strong>{plan.plan_reference}</strong>{' '}
              {plan.requires_review && <Badge variant="warning">Riferimenti da verificare</Badge>}
              <div style={{ marginTop: 5, color: '#475569' }}>
                {plan.installment_count ?? 'N.'} rate · totale {euro(plan.total_plan_amount)} · prima rata {euro(plan.first_installment_amount)} il {plan.first_installment_due_date || 'data non disponibile'}
              </div>
              {(plan.payment_modules || []).map(module => <div key={module.id} style={{ marginTop: 5, color: '#475569' }}>
                Modulo {module.document_number || module.source_filename}: {(module.installments || []).map(rate => `${rate.number}ª ${rate.due_date} ${euro(rate.amount)}`).join(' · ') || 'rate non leggibili'}
              </div>)}
              {(plan.reconciled_installments || []).map(rate => <div key={rate.id} style={{ marginTop: 7, padding: '7px 9px', borderRadius: 7, background: '#ecfdf5', color: '#166534' }}>
                <strong>Rata {rate.installment_number}: pagamento documentato</strong> · {euro(rate.amount)} · {rate.due_date || 'scadenza non disponibile'} · {rate.bank_verified ? 'banca verificata' : 'banca da verificare'}
              </div>)}
              {plan.source_document_id && <Button size="sm" variant="secondary" style={{ marginTop: 8 }} onClick={() => openDocument(plan.source_document_id)}>Apri accoglimento</Button>}
            </div>)}
          </section>
          <section aria-labelledby="ader-settlements" style={{ padding: 14, borderRadius: 10, border: '1px solid #fcd34d', background: '#fffbeb' }}>
            <h4 id="ader-settlements" style={{ margin: '0 0 10px' }}>Definizioni agevolate</h4>
            {aderRelated.settlements.length === 0 && <p style={{ margin: 0 }}>Nessuna definizione importata.</p>}
            {aderRelated.settlements.map(item => <div key={item.id} style={{ padding: '10px 0', borderTop: '1px solid #fde68a' }}>
              <strong>{item.communication_number || item.source_filename}</strong>{' '}
              <Badge variant="warning">{item.status || 'Da verificare'}</Badge>
              <div style={{ marginTop: 5, color: '#78350f' }}>
                Cartella {item.collection_document_number || 'non risolta'} · importo definizione {euro(item.amount_due)}.
                <strong> La comunicazione non prova il pagamento.</strong>
              </div>
              {item.source_document_id && <Button size="sm" variant="secondary" style={{ marginTop: 8 }} onClick={() => openDocument(item.source_document_id)}>Apri comunicazione</Button>}
            </div>)}
          </section>
        </div>}
        {loading && <p>Caricamento…</p>}
        {!loading && items.length === 0 && <p>Nessun dato importato. La presenza di Excel, ZIP o PDF non equivale a record nel database.</p>}
        {items.map((item, index) => {
          const entityId = item.id || item.collection_number || item.code || `row-${index}`;
          return <div key={entityId} style={{ padding: '12px 0', borderTop: '1px solid #e2e8f0' }}>
            <strong>{tab === 'f24' ? `${item.tax_code || item.section || 'Riga F24'} · ${item.reference_period || 'periodo non indicato'}` : (labelForClaim(item) || item.code || item.version_id || 'Record fiscale')}</strong>{' '}
            {(item.calculated_business_status || item.business_status || item.payment_status || item.status) && <Badge variant={item.requires_review ? 'warning' : 'info'}>{item.calculated_business_status || item.business_status || item.payment_status || item.status}</Badge>}
            {item.official_description && <span style={{ marginLeft: 8 }}>{item.official_description}</span>}
            {tab === 'f24' && <div style={{ marginTop: 6, color: '#475569' }}>
              Debito {euro(item.debit_amount)} · Credito {euro(item.credit_amount)} · {item.payment_date || 'data non indicata'}
              {item.protocol && <> · protocollo {item.protocol}</>}
              {item.filename && <div style={{ marginTop: 4 }}>{item.filename}</div>}
            </div>}
            {tab === 'ader' && <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(170px,1fr))', gap: 8, marginTop: 10, color: '#334155' }}>
              <span><small>Stato portale</small><br /><strong>{item.portal_status || 'Non indicato'}</strong></span>
              <span><small>Residuo totale</small><br /><strong>{euro(item.total_residual)}</strong></span>
              <span><small>Sospeso</small><br /><strong>{euro(item.suspended_amount)}</strong></span>
              <span><small>Netto da pagare</small><br /><strong>{euro(item.net_payable_amount)}</strong></span>
              <span><small>Notifica</small><br /><strong>{item.notification_date || 'Non disponibile'}</strong></span>
              <span><small>Fonte</small><br /><strong>{item.source_filename || 'PDF AdeR'}</strong></span>
            </div>}
            {tab === 'ader' && item.source_document_id && <Button size="sm" variant="secondary" style={{ marginTop: 10 }} onClick={() => openDocument(item.source_document_id)}>Apri PDF sorgente</Button>}
            {tab === 'riscossione' && <Button size="sm" variant="secondary" style={{ marginLeft: 10 }} onClick={() => setSelected(selected === entityId ? null : entityId)}>Perché? / prove</Button>}
            {tab === 'riscossione' && (item.payment_evidence_ids || []).length > 0 && <div style={{ marginTop: 8, color: '#166534', fontWeight: 700 }}>
              Pagamento documentato collegato · prove: {item.payment_evidence_ids.length}
            </div>}
            {tab === 'f24' && <Button size="sm" variant="secondary" style={{ marginTop: 8 }} onClick={() => setSelected(selected === entityId ? null : entityId)}>Apri PDF / prove</Button>}
            {selected === entityId && <div style={{ marginTop: 12 }}><LinkedEvidencePanel entityType={tab === 'f24' ? 'tax_allocation' : 'tax_collection_claim'} entityId={entityId} /></div>}
          </div>;
        })}
      </Card>
    </PageLayout>
  );
}

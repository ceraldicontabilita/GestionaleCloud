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
  ['codici-tributo', 'Codici tributo'],
  ['crosswalk-riscossione', 'Crosswalk riscossione'],
  ['riscossione', 'Riscossione'],
];

const endpointFor = tab => ({
  tributi: '/api/fiscal/obligations',
  'tributi-pagati': '/api/fiscal/obligations?status=PAID_ON_TIME',
  'codici-tributo': '/api/documenti/tax-codes/status',
  'crosswalk-riscossione': '/api/fiscal/crosswalk',
  riscossione: '/api/fiscal/collections',
}[tab]);

const labelForClaim = item => item.collection_number || item.cartella_number_original || item.id;

export default function SituazioneFiscale() {
  const location = useLocation();
  const tab = TABS.find(([id]) => location.pathname.endsWith(`/${id}`))?.[0] || 'tributi';
  const [summary, setSummary] = useState(null);
  const [items, setItems] = useState([]);
  const [review, setReview] = useState({ findings: [] });
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [summaryResponse, dataResponse, reviewResponse] = await Promise.all([
        api.get('/api/fiscal/summary'), api.get(endpointFor(tab)), api.get('/api/fiscal/review'),
      ]);
      setSummary(summaryResponse.data);
      const payload = dataResponse.data || {};
      setItems(payload.items || (tab === 'codici-tributo' ? [payload] : []));
      setReview(reviewResponse.data || { findings: [] });
    } catch (error) {
      setItems([]);
      toast.error('Situazione fiscale non disponibile', { description: error.response?.data?.detail || error.message });
    } finally { setLoading(false); }
  }, [tab]);

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
        {loading && <p>Caricamento…</p>}
        {!loading && items.length === 0 && <p>Nessun dato importato. La presenza di Excel, ZIP o PDF non equivale a record nel database.</p>}
        {items.map((item, index) => {
          const entityId = item.id || item.collection_number || item.code || `row-${index}`;
          return <div key={entityId} style={{ padding: '12px 0', borderTop: '1px solid #e2e8f0' }}>
            <strong>{labelForClaim(item) || item.code || item.version_id || 'Record fiscale'}</strong>{' '}
            {(item.business_status || item.payment_status || item.status) && <Badge variant={item.requires_review ? 'warning' : 'info'}>{item.business_status || item.payment_status || item.status}</Badge>}
            {item.official_description && <span style={{ marginLeft: 8 }}>{item.official_description}</span>}
            {tab === 'riscossione' && <Button size="sm" variant="secondary" style={{ marginLeft: 10 }} onClick={() => setSelected(selected === entityId ? null : entityId)}>Perché? / prove</Button>}
            {selected === entityId && <div style={{ marginTop: 12 }}><LinkedEvidencePanel entityType="tax_collection_claim" entityId={entityId} /></div>}
          </div>;
        })}
      </Card>
    </PageLayout>
  );
}

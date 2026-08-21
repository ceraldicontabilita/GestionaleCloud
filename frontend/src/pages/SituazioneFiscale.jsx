import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import api from '../api';
import { PageLayout } from '../components/PageLayout';
import LinkedEvidencePanel from '../components/LinkedEvidencePanel';
import { Badge, Button, Card, StatCard } from '../components/ds';

const TABS = [
  ['tributi', 'Tributi'],
  ['tributi-pagati', 'Tributi pagati'],
  ['dichiarazioni', 'Dichiarazioni'],
  ['f24', 'F24 e crediti'],
  ['codici-tributo', 'Codici tributo'],
  ['crosswalk-riscossione', 'Crosswalk riscossione'],
  ['riscossione', 'Riscossione'],
  ['ader', 'Snapshot AdeR'],
];

const endpointFor = (tab, f24Filters = {}, taxCodeFilters = {}) => {
  if (tab === 'dichiarazioni') {
    const params = new URLSearchParams();
    if (f24Filters.year) params.set('year', f24Filters.year);
    if (f24Filters.declarationType) params.set('declaration_type', f24Filters.declarationType);
    return `/api/fiscal/declarations?${params.toString()}`;
  }
  if (tab === 'f24') {
    const params = new URLSearchParams();
    if (f24Filters.year) params.set('year', f24Filters.year);
    if (f24Filters.taxCode) params.set('tax_code', f24Filters.taxCode);
    if (f24Filters.creditsOnly) params.set('credits_only', 'true');
    params.set('limit', '1000');
    return `/api/fiscal/f24-rows?${params.toString()}`;
  }
  if (tab === 'codici-tributo') {
    const params = new URLSearchParams();
    if (taxCodeFilters.query) params.set('q', taxCodeFilters.query);
    if (taxCodeFilters.taxType) params.set('tipo_imposta', taxCodeFilters.taxType);
    if (taxCodeFilters.context) params.set('contesto_uso', taxCodeFilters.context);
    params.set('limit', '100');
    return `/api/documenti/tax-codes?${params.toString()}`;
  }
  return ({
    tributi: '/api/fiscal/obligations',
    'tributi-pagati': '/api/fiscal/obligations?status=PAID_ON_TIME',
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
  const query = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const [declarationYear, setDeclarationYear] = useState(() => query.get('year') || '');
  const [declarationType, setDeclarationType] = useState(() => query.get('type') || '');
  const [uploadCategory, setUploadCategory] = useState('automatica');
  const [uploading, setUploading] = useState(false);
  const declarationInput = useRef(null);
  const [taxCodeQuery, setTaxCodeQuery] = useState('');
  const [taxCodeType, setTaxCodeType] = useState('');
  const [taxCodeContext, setTaxCodeContext] = useState('');
  const [taxCodeFilters, setTaxCodeFilters] = useState({ query: '', taxType: '', context: '' });
  const [taxCodeMeta, setTaxCodeMeta] = useState(null);
  const [taxCodeOptions, setTaxCodeOptions] = useState({ tax_types: [], contexts: [] });
  const [tabSources, setTabSources] = useState(null);
  const [loadWarnings, setLoadWarnings] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    const warnings = [];
    try {
      const [summaryResult, dataResult, reviewResult] = await Promise.allSettled([
        api.get('/api/fiscal/summary'), api.get(endpointFor(tab, {
          year: tab === 'dichiarazioni' ? declarationYear : f24Year,
          declarationType, taxCode: f24TaxCode, creditsOnly: f24CreditsOnly,
        }, taxCodeFilters)), api.get('/api/fiscal/review'),
      ]);
      if (summaryResult.status === 'fulfilled') {
        setSummary(summaryResult.value.data);
      } else {
        warnings.push('Riepilogo temporaneamente non disponibile; i dati della sezione restano consultabili.');
      }
      if (dataResult.status === 'fulfilled') {
        const payload = dataResult.value.data || {};
        setItems(payload.items || []);
        setTaxCodeMeta(payload.catalog || null);
        setTaxCodeOptions(payload.filters || { tax_types: [], contexts: [] });
        setTabSources(payload.sources || null);
        setTabMeta(payload.latest_import || null);
        setAderRelated({ ratePlans: payload.rate_plans || [], settlements: payload.settlements || [] });
      } else {
        const error = dataResult.reason;
        setItems([]);
        setTabSources(null);
        toast.error(`${TABS.find(([id]) => id === tab)?.[1] || 'Sezione fiscale'} non disponibile`, {
          description: error.response?.data?.detail || error.message,
        });
      }
      if (reviewResult.status === 'fulfilled') {
        setReview(reviewResult.value.data || { findings: [] });
      } else {
        setReview({ findings: [] });
        warnings.push('Controlli di revisione temporaneamente non disponibili.');
      }
      setLoadWarnings(warnings);
    } catch (error) {
      setLoadWarnings(['Caricamento fiscale non completato.']);
      toast.error('Situazione fiscale non disponibile', { description: error.message });
    } finally { setLoading(false); }
  }, [tab, f24Year, f24TaxCode, f24CreditsOnly, declarationYear, declarationType, taxCodeFilters]);

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

  const openDriveDocument = async documentId => {
    try {
      const response = await api.get(`/api/documenti/drive/index/document/${encodeURIComponent(documentId)}`);
      const url = response.data?.drive_url;
      if (!url) throw new Error('Link Drive non disponibile');
      window.open(url, '_blank', 'noopener,noreferrer');
    } catch (error) {
      toast.error('Originale Drive non disponibile', { description: error.response?.data?.detail || error.message });
    }
  };

  const uploadDeclaration = async event => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    const data = new FormData();
    data.append('file', file);
    data.append('categoria', uploadCategory);
    data.append('periodo', declarationYear || String(new Date().getFullYear()));
    setUploading(true);
    try {
      const response = await api.post('/api/documenti-fiscali/upload', data, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success(response.data?.duplicate ? 'Dichiarazione già presente' : 'Dichiarazione acquisita');
      await load();
    } catch (error) {
      toast.error('Caricamento non riuscito', { description: error.response?.data?.detail || error.message });
    } finally { setUploading(false); }
  };

  const counts = summary?.counts || {};
  const driveCounts = summary?.drive_index?.counts || {};
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
        <StatCard label="Record fiscali DB" value={counts.documents || 0} accent="primary" />
        <StatCard label="F24 in Drive" value={driveCounts.f24_documents || 0} accent="primary" />
        <StatCard label="Righe tributo Drive" value={driveCounts.f24_rows || 0} accent="primary" />
        <StatCard label="Dichiarazioni Drive" value={driveCounts.declarations || 0} accent="primary" />
        <StatCard label="Obblighi" value={counts.obligations || 0} accent="primary" />
        <StatCard label="Pagamenti" value={counts.payments || 0} accent="success" />
        <StatCard label="Cartelle" value={counts.collection_claims || 0} accent="warning" />
        <StatCard label="Snapshot AdeR" value={counts.ader_snapshots || 0} accent="primary" />
        <StatCard label="Da verificare" value={summary?.requires_review || 0} accent="danger" />
      </div>
      {summary?.drive_index?.available === false && <Card style={{ marginBottom: 18 }} bodyStyle={{ padding: 14, color: '#92400e', background: '#fffbeb' }}>
        <strong>Indice Drive non disponibile:</strong> {summary.drive_index.warning}. I record transitori del database restano consultabili.
      </Card>}
      {loadWarnings.length > 0 && <Card style={{ marginBottom: 18 }} bodyStyle={{ padding: 14, color: '#92400e', background: '#fffbeb' }}>
        {loadWarnings.map(message => <div key={message}>{message}</div>)}
      </Card>}
      {(review.findings || []).length > 0 && <Card style={{ marginBottom: 18 }} bodyStyle={{ padding: 16 }}>
        <h3 style={{ marginTop: 0 }}>Controlli deterministici</h3>
        {review.findings.slice(0, 10).map((item, index) => <div key={`${item.code}-${index}`} style={{ padding: '8px 0', borderTop: '1px solid #e2e8f0' }}>
          <Badge variant="warning">{item.code}</Badge> {item.message}
        </div>)}
      </Card>}
      <Card bodyStyle={{ padding: 16 }}>
        <h3 style={{ marginTop: 0 }}>{activeLabel}</h3>
        {tabSources && (tab === 'f24' || tab === 'dichiarazioni') && <div style={{ margin: '0 0 14px', padding: '10px 12px', borderRadius: 8, background: '#ecfdf5', color: '#166534' }}>
          <strong>Archivio canonico:</strong> Google Drive · indice {tabSources.drive_excel_index || 0}
          {tabSources.drive_warning && <div style={{ color: '#92400e', marginTop: 4 }}>Drive non disponibile: {tabSources.drive_warning}</div>}
        </div>}
        {tab === 'f24' && <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'end', marginBottom: 14 }}>
          <label>Anno<br /><select value={f24Year} onChange={event => setF24Year(event.target.value)} style={{ padding: 8 }}>
            <option value="">Tutti</option>{[2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019].map(year => <option key={year}>{year}</option>)}
          </select></label>
          <label>Codice tributo<br /><input value={f24TaxCode} onChange={event => setF24TaxCode(event.target.value.trim())} placeholder="es. 1704" style={{ padding: 8, width: 130 }} /></label>
          <label style={{ paddingBottom: 8 }}><input type="checkbox" checked={f24CreditsOnly} onChange={event => setF24CreditsOnly(event.target.checked)} /> Solo righe a credito</label>
        </div>}
        {tab === 'dichiarazioni' && <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'end', marginBottom: 14 }}>
          <label>Anno<br /><select value={declarationYear} onChange={event => setDeclarationYear(event.target.value)} style={{ padding: 8 }}>
            <option value="">Tutti</option>{[2026, 2025, 2024, 2023, 2022, 2021, 2020].map(year => <option key={year}>{year}</option>)}
          </select></label>
          <label>Tipo<br /><select value={declarationType} onChange={event => setDeclarationType(event.target.value)} style={{ padding: 8 }}>
            <option value="">Tutte</option><option value="MODELLO_770">770</option><option value="DICHIARAZIONE_IVA">IVA</option>
            <option value="LIPE">LIPE</option><option value="REDDITI_SC">Redditi SC</option><option value="DICHIARAZIONE_IRAP">IRAP</option><option value="ELENCO_PERCIPIENTI">Percipienti</option>
          </select></label>
          <label>Classificazione nuovo PDF<br /><select value={uploadCategory} onChange={event => setUploadCategory(event.target.value)} style={{ padding: 8 }}>
            <option value="automatica">Automatica</option><option value="modello_770">770 manuale</option><option value="dichiarazione_iva">IVA manuale</option>
            <option value="lipe">LIPE manuale</option><option value="redditi_sc">Redditi SC manuale</option><option value="dichiarazione_irap">IRAP manuale</option><option value="elenco_percipienti">Percipienti manuale</option>
          </select></label>
          <input ref={declarationInput} type="file" accept="application/pdf,.pdf" hidden onChange={uploadDeclaration} disabled={uploading} />
          <Button variant="primary" disabled={uploading} onClick={() => declarationInput.current?.click()}>{uploading ? 'Caricamento…' : 'Inserisci dichiarazione'}</Button>
          <a href="/archivio-fiscale-drive.html" target="_blank" rel="noreferrer" style={{ padding: '9px 14px', borderRadius: 8, background: '#0f2744', color: '#fff', textDecoration: 'none', fontWeight: 700 }}>Apri pagina HTML Drive</a>
        </div>}
        {tab === 'codici-tributo' && <>
          {taxCodeMeta && <div style={{ margin: '0 0 14px', padding: '12px 14px', borderRadius: 10, background: '#eef6ff', border: '1px solid #bfdbfe' }}>
            <strong>Catalogo Agenzia delle Entrate:</strong> {taxCodeMeta.record_count} classificazioni · {taxCodeMeta.distinct_codes} codici distinti · acquisito il {taxCodeMeta.acquired_at || 'dato non disponibile'}
          </div>}
          <form onSubmit={event => { event.preventDefault(); setTaxCodeFilters({ query: taxCodeQuery, taxType: taxCodeType, context: taxCodeContext }); }}
            style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'end', marginBottom: 14 }}>
            <label>Cerca codice o descrizione<br /><input value={taxCodeQuery} onChange={event => setTaxCodeQuery(event.target.value)} placeholder="es. 6001 o IVA mensile" style={{ padding: 8, width: 240 }} /></label>
            <label>Tipo imposta<br /><select value={taxCodeType} onChange={event => setTaxCodeType(event.target.value)} style={{ padding: 8, maxWidth: 260 }}>
              <option value="">Tutti</option>{taxCodeOptions.tax_types.map(value => <option key={value}>{value}</option>)}
            </select></label>
            <label>Contesto<br /><select value={taxCodeContext} onChange={event => setTaxCodeContext(event.target.value)} style={{ padding: 8, maxWidth: 260 }}>
              <option value="">Tutti</option>{taxCodeOptions.contexts.map(value => <option key={value}>{value}</option>)}
            </select></label>
            <Button type="submit">Cerca</Button>
          </form>
        </>}
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
        {!loading && items.length === 0 && <p>Nessun record disponibile nelle fonti collegate.</p>}
        {items.map((item, index) => {
          const entityId = item.id || item.collection_number || item.code || `row-${index}`;
          return <div key={entityId} style={{ padding: '12px 0', borderTop: '1px solid #e2e8f0' }}>
            <strong>{tab === 'f24' ? `${item.tax_code || item.section || 'Riga F24'} · ${item.reference_period || 'periodo non indicato'}` : tab === 'dichiarazioni' ? `${item.document_type} · ${item.filing_year || 'anno da verificare'}` : (labelForClaim(item) || item.code || item.version_id || 'Record fiscale')}</strong>{' '}
            {(item.calculated_business_status || item.business_status || item.payment_status || item.status) && <Badge variant={item.requires_review ? 'warning' : 'info'}>{item.calculated_business_status || item.business_status || item.payment_status || item.status}</Badge>}
            {item.official_description && <span style={{ marginLeft: 8 }}>{item.official_description}</span>}
            {tab === 'codici-tributo' && <div style={{ marginTop: 6 }}>
              <strong>{item.codice_tributo}</strong> · {item.descrizione}
              <div style={{ marginTop: 4, color: '#475569' }}>
                {item.tipo_imposta || 'Tipo non indicato'} · {item.tipo_contribuente || 'Contribuente non indicato'} · {item.contesto_uso || 'Contesto non indicato'}
              </div>
              {item.url_esempio_compilazione && <a href={item.url_esempio_compilazione} target="_blank" rel="noreferrer" style={{ display: 'inline-block', marginTop: 5 }}>Esempio ufficiale di compilazione</a>}
            </div>}
            {tab === 'f24' && <div style={{ marginTop: 6, color: '#475569' }}>
              Debito {euro(item.debit_amount)} · Credito {euro(item.credit_amount)} · {item.payment_date || 'data non indicata'}
              {item.protocol && <> · protocollo {item.protocol}</>}
              {item.filename && <div style={{ marginTop: 4 }}>{item.filename}</div>}
              {item.evidence_state && <div style={{ marginTop: 4 }}><strong>{item.evidence_state === 'MODELLO_F24_NON_PROVA_BANCARIA' ? 'Modello F24: pagamento bancario da verificare' : 'Quietanza documentale: banca da verificare'}</strong></div>}
            </div>}
            {tab === 'dichiarazioni' && <div style={{ marginTop: 8, color: '#475569' }}>
              <div>Anno d'imposta {item.tax_year || 'da verificare'}{item.protocol && <> · protocollo {item.protocol}</>}</div>
              <div>{item.filename}</div>
              {item.source_kind === 'DRIVE_EXCEL_INDEX_DECLARATION'
                ? <Button size="sm" variant="secondary" style={{ marginTop: 8 }} disabled={!item.document_id} onClick={() => openDriveDocument(item.document_id)}>Apri originale Drive</Button>
                : <Button size="sm" variant="secondary" style={{ marginTop: 8 }} onClick={() => openDocument(item.id)}>Apri dichiarazione</Button>}
              {(item.f24_links || []).map(link => <div key={link.f24_id} style={{ marginTop: 10, padding: 10, border: '1px solid #cbd5e1', borderRadius: 8 }}>
                <strong>F24 {link.filename || link.f24_id}</strong>{' '}<Badge variant={link.link_status === 'CONFIRMED' ? 'success' : 'warning'}>{link.link_status === 'CONFIRMED' ? 'Collegato' : 'Candidato da verificare'}</Badge>
                <div>{(link.tax_rows || []).map(row => `${row.tax_code} ${row.reference_period || ''}`).join(' · ')}</div>
                <div>Quietanza: {link.documentary_payment_status} · Banca: {link.bank_status}</div>
                {link.quietanza && <div>Protocollo quietanza: {link.quietanza.protocol || link.quietanza.id}</div>}
              </div>)}
              {(item.f24_links || []).length === 0 && <div style={{ marginTop: 8 }}>Nessun F24 compatibile trovato. Non viene creato alcun pagamento per inferenza.</div>}
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

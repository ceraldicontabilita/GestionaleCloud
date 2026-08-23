import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import api from '../api';
import { PageLayout } from '../components/PageLayout';
import { Badge, Button, Card, StatCard } from '../components/ds';
import './SituazioneFiscale.css';

const TABS = [
  ['tributi', 'Tributi'],
  ['tributi-pagati', 'Tributi pagati'],
  ['dichiarazioni', 'Dichiarazioni'],
  ['confronto-fonti', 'Confronto fonti'],
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
    params.set('limit', '5000');
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
    tributi: '/api/fiscal/obligations?limit=5000',
    'tributi-pagati': '/api/fiscal/obligations?status=PAID_ON_TIME&limit=5000',
    'confronto-fonti': '/api/fiscal/source-certainty',
    'crosswalk-riscossione': '/api/fiscal/crosswalk',
    riscossione: '/api/fiscal/collections',
    ader: '/api/fiscal/ader-snapshots',
  }[tab]);
};

const labelForClaim = item => item.document_number || item.collection_number || item.cartella_number_original || item.id;
const euro = value => value == null ? 'Non disponibile' : new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(value);
const searchableText = item => Object.values(item || {}).filter(value => ['string', 'number'].includes(typeof value)).join(' ').toLocaleLowerCase('it');
const itemYear = item => String(item.payment_year || item.filing_year || item.tax_year || item.year || item.notification_date || item.payment_date || '').slice(0, 4);
const itemStatus = item => item.documentary_payment_status || item.evidence_state || item.calculated_business_status || item.business_status || item.payment_status || item.status || '';
const PAGE_SIZES = [25, 50, 100];
const F24_GROUPED_TABS = new Set(['tributi', 'tributi-pagati', 'f24']);
const groupF24Rows = rows => {
  const groups = new Map();
  rows.forEach(row => {
    const key = row.document_id || row.protocol || row.filename || row.id;
    if (!groups.has(key)) groups.set(key, {
      ...row, id: `f24-group-${key}`, is_f24_group: true, rows: [],
      debit_amount: 0, credit_amount: 0,
    });
    const group = groups.get(key);
    group.rows.push(row);
    group.debit_amount += Number(row.debit_amount || 0);
    group.credit_amount += Number(row.credit_amount || 0);
  });
  return [...groups.values()].map(group => ({
    ...group,
    debit_amount: Math.round(group.debit_amount * 100) / 100,
    credit_amount: Math.round(group.credit_amount * 100) / 100,
    net_amount: Math.round((group.debit_amount - group.credit_amount) * 100) / 100,
    search_blob: group.rows.map(searchableText).join(' '),
  }));
};

export default function SituazioneFiscale() {
  const location = useLocation();
  const tab = TABS.find(([id]) => location.pathname.endsWith(`/${id}`))?.[0] || 'tributi';
  const [summary, setSummary] = useState(null);
  const [items, setItems] = useState([]);
  const [tabMeta, setTabMeta] = useState(null);
  const [certaintyMeta, setCertaintyMeta] = useState(null);
  const [declarationChecks, setDeclarationChecks] = useState({});
  const [checkingDeclaration, setCheckingDeclaration] = useState(null);
  const [checkingAllDeclarations, setCheckingAllDeclarations] = useState(false);
  const [declarationCheckProgress, setDeclarationCheckProgress] = useState({ completed: 0, total: 0, failed: 0 });
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
  const [listQuery, setListQuery] = useState('');
  const [listYear, setListYear] = useState('');
  const [listStatus, setListStatus] = useState('');
  const [pageSize, setPageSize] = useState(25);
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    setLoading(true);
    const warnings = [];
    try {
      const [summaryResult, dataResult] = await Promise.allSettled([
        api.get('/api/fiscal/summary'), api.get(endpointFor(tab, {
          year: tab === 'dichiarazioni' ? declarationYear : f24Year,
          declarationType, taxCode: f24TaxCode, creditsOnly: f24CreditsOnly,
        }, taxCodeFilters)),
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
        setCertaintyMeta(tab === 'confronto-fonti' ? payload : null);
        setAderRelated({ ratePlans: payload.rate_plans || [], settlements: payload.settlements || [] });
      } else {
        const error = dataResult.reason;
        setItems([]);
        setTabSources(null);
        setCertaintyMeta(null);
        toast.error(`${TABS.find(([id]) => id === tab)?.[1] || 'Sezione fiscale'} non disponibile`, {
          description: error.response?.data?.detail || error.message,
        });
      }
      setLoadWarnings(warnings);
    } catch (error) {
      setLoadWarnings(['Caricamento fiscale non completato.']);
      toast.error('Situazione fiscale non disponibile', { description: error.message });
    } finally { setLoading(false); }
  }, [tab, f24Year, f24TaxCode, f24CreditsOnly, declarationYear, declarationType, taxCodeFilters]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    setListQuery(''); setListYear(''); setListStatus(''); setPage(1);
  }, [tab]);

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

  const checkDeclarationFields = async documentId => {
    setCheckingDeclaration(documentId);
    try {
      const response = await api.get(`/api/fiscal/declarations/${encodeURIComponent(documentId)}/field-certainty`);
      setDeclarationChecks(current => ({ ...current, [documentId]: response.data }));
    } catch (error) {
      toast.error('Verifica campi dichiarazione non riuscita', { description: error.response?.data?.detail || error.message });
    } finally { setCheckingDeclaration(null); }
  };

  const checkAllDeclarations = async () => {
    const declarations = (certaintyMeta?.declaration_items || []).filter(item =>
      item.document_id && item.field_check_status === 'PRONTO_PER_VERIFICA_CAMPI');
    if (!declarations.length) return;
    setCheckingAllDeclarations(true);
    setDeclarationCheckProgress({ completed: 0, total: declarations.length, failed: 0 });
    let cursor = 0;
    let failed = 0;
    const worker = async () => {
      while (cursor < declarations.length) {
        const declaration = declarations[cursor++];
        try {
          const response = await api.get(`/api/fiscal/declarations/${encodeURIComponent(declaration.document_id)}/field-certainty`);
          setDeclarationChecks(current => ({ ...current, [declaration.document_id]: response.data }));
        } catch (error) {
          failed += 1;
          setDeclarationChecks(current => ({ ...current, [declaration.document_id]: {
            error: error.response?.data?.detail || error.message || 'Verifica non riuscita',
          } }));
        } finally {
          setDeclarationCheckProgress(current => ({ ...current, completed: current.completed + 1, failed }));
        }
      }
    };
    await Promise.all([worker(), worker()]);
    setCheckingAllDeclarations(false);
    if (failed) toast.warning(`Verifica completata con ${failed} documenti da riprovare`);
    else toast.success('Registro dichiarazioni aggiornato da Drive');
  };

  const driveCounts = summary?.drive_index?.counts || {};
  const activeLabel = useMemo(() => TABS.find(([id]) => id === tab)?.[1], [tab]);
  const displayItems = useMemo(() => {
    if (!F24_GROUPED_TABS.has(tab)) return items;
    const driveRows = items.filter(item => item.source_kind === 'DRIVE_EXCEL_INDEX_F24_ROW');
    const otherItems = items.filter(item => item.source_kind !== 'DRIVE_EXCEL_INDEX_F24_ROW');
    return [...groupF24Rows(driveRows), ...otherItems];
  }, [items, tab]);
  const listYears = useMemo(() => [...new Set(displayItems.map(itemYear).filter(year => /^20\d{2}$/.test(year)))].sort().reverse(), [displayItems]);
  const listStatuses = useMemo(() => [...new Set(displayItems.map(itemStatus).filter(Boolean))].sort(), [displayItems]);
  const filteredItems = useMemo(() => {
    const needle = listQuery.trim().toLocaleLowerCase('it');
    return displayItems.filter(item => (!needle || `${searchableText(item)} ${item.search_blob || ''}`.includes(needle))
      && (!listYear || itemYear(item) === listYear)
      && (!listStatus || itemStatus(item) === listStatus));
  }, [displayItems, listQuery, listYear, listStatus]);
  const pageCount = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const visibleItems = filteredItems.slice((Math.min(page, pageCount) - 1) * pageSize, Math.min(page, pageCount) * pageSize);
  const resetListFilters = () => { setListQuery(''); setListYear(''); setListStatus(''); setPage(1); };
  const obligationRegister = useMemo(() => {
    const declarations = certaintyMeta?.declaration_items || [];
    const obligations = [];
    let processed = 0;
    let noDebit = 0;
    let failed = 0;
    declarations.forEach(declaration => {
      const check = declarationChecks[declaration.document_id];
      if (!check) return;
      if (check.error) { failed += 1; return; }
      processed += 1;
      const rows = check.reconciliation?.items || [];
      if (!rows.length) noDebit += 1;
      const management = check.management_reconciliation;
      rows.forEach(row => {
        const amount = Number(row.declaration_row?.debit_amount ?? row.declaration_row?.paid_amount ?? 0);
        const managementItem = management?.items?.find(item =>
          item.declaration_tax_row_id === row.declaration_row?.id);
        const managementStatus = managementItem?.status;
        const managementState = managementItem
          ? managementStatus === 'CONCORDANTE'
            ? 'CONCORDANTE_CON_GESTIONALE'
            : managementStatus === 'DISCORDANTE'
              ? 'DISCORDANTE_DAL_GESTIONALE'
              : 'GESTIONALE_NON_VERIFICABILE'
          : management?.all_certain
            ? 'CONCORDANTE_CON_GESTIONALE'
            : management?.items?.some(item => item.status === 'DISCORDANTE')
              ? 'DISCORDANTE_DAL_GESTIONALE'
              : management ? 'GESTIONALE_NON_VERIFICABILE' : 'CONFRONTO_GESTIONALE_NON_DISPONIBILE';
        obligations.push({
          id: row.id, declaration, row, amount, managementState, managementItem,
          paid: row.erario_state === 'NULLA_DOVUTO_ERARIO_DOCUMENTATO',
          review: row.erario_state === 'IMPORTO_DICHIARAZIONE_DA_VERIFICARE'
            || row.erario_state === 'IN_ATTESA_VERIFICA_F24_AMBIGUO',
        });
      });
    });
    const paid = obligations.filter(item => item.paid);
    const review = obligations.filter(item => item.review);
    const due = obligations.filter(item => !item.paid && !item.review);
    return {
      obligations, processed, noDebit, failed,
      unprocessed: Math.max(0, declarations.length - processed - failed),
      paid: paid.length, due: due.length, review: review.length,
      expectedAmount: obligations.reduce((sum, item) => sum + item.amount, 0),
      paidAmount: paid.reduce((sum, item) => sum + item.amount, 0),
      dueAmount: due.reduce((sum, item) => sum + item.amount, 0),
    };
  }, [certaintyMeta, declarationChecks]);
  return (
    <PageLayout title="Situazione fiscale" icon="⚖️"
      subtitle="Obblighi, pagamenti, cartelle e prove restano distinti e verificabili"
      actions={<Button variant="secondary" onClick={load} disabled={loading}>Aggiorna da Drive</Button>}>
      <nav aria-label="Sezioni situazione fiscale" className="fiscal-tabs">
        {TABS.map(([id, label]) => <Link key={id} to={`/situazione-fiscale/${id}`}
          style={{ padding: '8px 12px', borderRadius: 8, textDecoration: 'none', fontWeight: 700,
            background: tab === id ? '#0f2744' : '#e2e8f0', color: tab === id ? '#fff' : '#0f2744' }}>{label}</Link>)}
      </nav>
      <div className="fiscal-stats">
        <StatCard label="F24 in Drive" value={driveCounts.f24_documents || 0} accent="primary" />
        <StatCard label="Righe tributo Drive" value={driveCounts.f24_rows || 0} accent="primary" />
        <StatCard label="Dichiarazioni Drive" value={driveCounts.declarations || 0} accent="primary" />
        <StatCard label="Tributi a debito Drive" value={driveCounts.tax_debit_rows || 0} accent="primary" />
        <StatCard label="Quietanze Drive" value={driveCounts.documentary_payment_documents || 0} accent="success" />
      </div>
      {summary?.drive_index?.available === false && <Card style={{ marginBottom: 18 }} bodyStyle={{ padding: 14, color: '#92400e', background: '#fffbeb' }}>
        <strong>Indice Drive non disponibile:</strong> {summary.drive_index.warning}.
      </Card>}
      {loadWarnings.length > 0 && <Card style={{ marginBottom: 18 }} bodyStyle={{ padding: 14, color: '#92400e', background: '#fffbeb' }}>
        {loadWarnings.map(message => <div key={message}>{message}</div>)}
      </Card>}
      <Card bodyStyle={{ padding: 16 }}>
        <div className="fiscal-section-heading"><div><h3>{activeLabel}</h3><p>{filteredItems.length} {F24_GROUPED_TABS.has(tab) ? 'documenti' : 'risultati'} su {displayItems.length}{F24_GROUPED_TABS.has(tab) && ` · ${items.length} righe tributo`}</p></div></div>
        {tabSources && (tab === 'tributi' || tab === 'f24' || tab === 'dichiarazioni' || tab === 'tributi-pagati') && <div style={{ margin: '0 0 14px', padding: '10px 12px', borderRadius: 8, background: '#ecfdf5', color: '#166534' }}>
          <strong>Archivio canonico:</strong> Google Drive · indice {tabSources.drive_excel_index || 0}
          {tabSources.drive_warning && <div style={{ color: '#92400e', marginTop: 4 }}>Drive non disponibile: {tabSources.drive_warning}</div>}
        </div>}
        {tab === 'confronto-fonti' && certaintyMeta && <div className="fiscal-stats" style={{ marginBottom: 16 }}>
          <StatCard label="Concordanti" value={certaintyMeta.certain || 0} accent="success" />
          <StatCard label="Da verificare" value={certaintyMeta.requires_review || 0} accent="warning" />
          <StatCard label="F24 commercialista" value={certaintyMeta.sources?.commercialista_f24_documents || 0} accent="primary" />
          <StatCard label="Quietanze Drive" value={certaintyMeta.sources?.quietanza_drive_rows || 0} accent="primary" />
          <StatCard label="Dichiarazioni" value={certaintyMeta.declarations?.documents || 0} accent="primary" />
        </div>}
        {tab === 'confronto-fonti' && certaintyMeta?.declarations?.requires_review && <div style={{ margin: '0 0 14px', padding: '10px 12px', borderRadius: 8, background: '#fffbeb', color: '#92400e' }}>
          <strong>Verifica dichiarazioni disponibile per i modelli supportati.</strong> Ogni valore conserva pagina e testo sorgente; le righe non univoche restano da verificare e non vengono collegate per il solo importo.
        </div>}
        {tab === 'confronto-fonti' && (certaintyMeta?.declaration_items || []).length > 0 && <section aria-labelledby="obligation-register-heading" className="fiscal-record" style={{ marginBottom: 18 }}>
          <div className="fiscal-record-header">
            <div><h4 id="obligation-register-heading" style={{ margin: 0 }}>Registro automatico dovuto / pagato</h4><div className="fiscal-muted">Dichiarazioni → F24 commercialista → quietanze Drive → dati gestionali disponibili</div></div>
            <Button variant="primary" onClick={checkAllDeclarations} disabled={checkingAllDeclarations}>
              {checkingAllDeclarations ? `Verifica ${declarationCheckProgress.completed}/${declarationCheckProgress.total}` : 'Verifica tutte le dichiarazioni'}
            </Button>
          </div>
          <div className="fiscal-data-grid" style={{ marginTop: 12 }}>
            <span><small>Pagati con quietanza</small><strong>{obligationRegister.paid} · {euro(obligationRegister.paidAmount)}</strong></span>
            <span><small>Ancora dovuti</small><strong>{obligationRegister.due} · {euro(obligationRegister.dueAmount)}</strong></span>
            <span><small>Da verificare</small><strong>{obligationRegister.review}</strong></span>
            <span><small>Dichiarazioni elaborate</small><strong>{obligationRegister.processed}/{certaintyMeta.declaration_items.length}</strong></span>
            <span><small>Senza debiti estratti</small><strong>{obligationRegister.noDebit}</strong></span>
            <span><small>Non elaborate / errore</small><strong>{obligationRegister.unprocessed + obligationRegister.failed}</strong></span>
          </div>
          {obligationRegister.obligations.length > 0 && <div className="fiscal-f24-table-wrap" style={{ marginTop: 12 }}><table className="fiscal-f24-table">
            <thead><tr><th>Dichiarazione</th><th>Tributo / periodo</th><th>Importo dovuto</th><th>F24 commercialista</th><th>Stato Erario</th><th>Confronto gestionale</th></tr></thead>
            <tbody>{obligationRegister.obligations.map(item => <tr key={item.id}>
              <td><strong>{item.declaration.document_type}</strong><div className="fiscal-muted">{item.declaration.filename}</div></td>
              <td><strong>{item.row.declaration_row?.tax_code || '—'}</strong><div>{item.row.declaration_row?.reference_period || '—'}</div></td>
              <td>{euro(item.amount)}</td>
              <td><Badge variant={item.row.accountant_f24_present ? 'info' : 'warning'}>{item.row.accountant_f24_present ? 'PRESENTE' : 'NON TROVATO'}</Badge></td>
              <td><Badge variant={item.paid ? 'success' : 'warning'}>{String(item.row.erario_state || item.row.status).replaceAll('_', ' ')}</Badge></td>
              <td><Badge variant={item.managementState === 'CONCORDANTE_CON_GESTIONALE' ? 'success' : 'warning'}>{item.managementState.replaceAll('_', ' ')}</Badge></td>
            </tr>)}</tbody>
            <tfoot><tr><th colSpan="2">Totale debiti dichiarati elaborati</th><th>{euro(obligationRegister.expectedAmount)}</th><th colSpan="3">Calcolo al centesimo; nessun collegamento per solo importo</th></tr></tfoot>
          </table></div>}
          {declarationCheckProgress.failed > 0 && <div className="fiscal-muted" style={{ marginTop: 8 }}>{declarationCheckProgress.failed} documenti non elaborati: restano esplicitamente da verificare.</div>}
        </section>}
        {tab === 'confronto-fonti' && (certaintyMeta?.declaration_items || []).length > 0 && <section aria-labelledby="declaration-certainty-heading" style={{ marginBottom: 18 }}>
          <h4 id="declaration-certainty-heading" style={{ margin: '0 0 10px' }}>Dichiarazioni → F24 Drive</h4>
          <div style={{ display: 'grid', gap: 12 }}>
            {certaintyMeta.declaration_items.map(declaration => {
              const check = declarationChecks[declaration.document_id];
              const rows = check?.reconciliation?.items || [];
              const declaredFields = check?.extraction?.declared_fields || [];
              const managementRows = check?.management_reconciliation?.items || [];
              return <article key={declaration.document_id || declaration.filename} className="fiscal-record">
                <div className="fiscal-record-header">
                  <div><strong>{declaration.document_type} · {declaration.filing_year || 'anno da verificare'}</strong><div className="fiscal-muted">{declaration.filename}</div></div>
                  <Badge variant={check?.extraction?.field_level_status === 'ESTRATTO_CON_CERTEZZA' ? 'success' : 'warning'}>{check?.extraction?.field_level_status || String(declaration.field_check_status || 'DA_VERIFICARE').replaceAll('_', ' ')}</Badge>
                </div>
                <div className="fiscal-actions" style={{ marginTop: 10 }}>
                  <Button size="sm" variant="primary" disabled={!declaration.document_id || declaration.field_check_status !== 'PRONTO_PER_VERIFICA_CAMPI' || checkingDeclaration === declaration.document_id} onClick={() => checkDeclarationFields(declaration.document_id)}>
                    {checkingDeclaration === declaration.document_id ? 'Verifica…' : 'Verifica campi e F24'}
                  </Button>
                  <Button size="sm" variant="secondary" disabled={!declaration.document_id} onClick={() => openDriveDocument(declaration.document_id)}>Apri originale Drive</Button>
                </div>
                {check && <div style={{ marginTop: 12 }}>
                  <div className="fiscal-data-grid">
                    <span><small>Righe estratte con certezza</small><strong>{check.extraction?.extracted_with_certainty || 0}</strong></span>
                    <span><small>Pagati con quietanza</small><strong>{check.reconciliation?.erario_counts?.NULLA_DOVUTO_ERARIO_DOCUMENTATO || 0}</strong></span>
                    <span><small>Ancora dovuti / da verificare</small><strong>{check.reconciliation?.requires_review || 0}</strong></span>
                    <span><small>Hash originale</small><strong title={check.source?.sha256}>{String(check.source?.sha256 || '').slice(0, 12)}…</strong></span>
                  </div>
                  {rows.length > 0 && <div className="fiscal-f24-table-wrap" style={{ marginTop: 10 }}><table className="fiscal-f24-table">
                    <thead><tr><th>Pagina / sorgente</th><th>Codice</th><th>Periodo</th><th>Debito dichiarato</th><th>Credito dichiarato</th><th>Interessi</th><th>Stato verso Erario</th></tr></thead>
                    <tbody>{rows.map(row => <tr key={row.id}>
                      <td><strong>Pag. {row.declaration_row?.page_number || '—'}</strong><div className="fiscal-muted" title={row.declaration_row?.source_text}>{row.declaration_row?.certainty_reason?.replaceAll('_', ' ')}</div></td>
                      <td>{row.declaration_row?.tax_code || '—'}</td><td>{row.declaration_row?.reference_period || '—'}</td>
                      <td>{euro(row.declaration_row?.paid_amount ?? row.declaration_row?.debit_amount)}</td><td>{euro(row.declaration_row?.credit_amount ?? 0)}</td><td>{euro(row.declaration_row?.interest_amount ?? 0)}</td>
                      <td><Badge variant={row.erario_state === 'NULLA_DOVUTO_ERARIO_DOCUMENTATO' ? 'success' : 'warning'}>{String(row.erario_state || row.status).replaceAll('_', ' ')}</Badge>{row.aggregate_match && <div>{row.f24_rows?.length || 0} quietanze/F24 sommati</div>}{row.candidate_count > 1 && !row.aggregate_match && <div>{row.candidate_count} candidati esatti</div>}{row.related_candidate_count > 0 && row.erario_state !== 'NULLA_DOVUTO_ERARIO_DOCUMENTATO' && <div>{row.related_candidate_count} righe stesso codice/anno · debiti {euro(row.related_debit_amount)} · crediti {euro(row.related_credit_amount)}</div>}</td>
                    </tr>)}</tbody>
                  </table></div>}
                  {check.extraction?.document_type === 'LIPE' && declaredFields.length > 0 && <div className="fiscal-f24-table-wrap" style={{ marginTop: 10 }}><table className="fiscal-f24-table">
                    <thead><tr><th>Periodo / pagina</th><th>VP4 IVA esigibile</th><th>VP5 IVA detratta</th><th>VP6 saldo mese</th><th>VP14 saldo finale</th><th>Attesa F24</th></tr></thead>
                    <tbody>{declaredFields.map(module => <tr key={module.id}>
                      <td><strong>{module.reference_period || '—'}</strong><div className="fiscal-muted">Pag. {module.page_number}</div></td>
                      <td>{euro((module.values?.vp4_cents || 0) / 100)}</td><td>{euro((module.values?.vp5_cents || 0) / 100)}</td>
                      <td>{module.values?.vp6_side || '—'} {euro((module.values?.vp6_cents || 0) / 100)}</td>
                      <td>{module.values?.vp14_side || '—'} {euro((module.values?.vp14_cents || 0) / 100)}</td>
                      <td><Badge variant={module.f24_expectation === 'F24_MENSILE_ATTESO' ? 'warning' : 'success'}>{String(module.f24_expectation || 'DA VERIFICARE').replaceAll('_', ' ')}</Badge></td>
                    </tr>)}</tbody>
                  </table></div>}
                  {['DICHIARAZIONE_IVA', 'REDDITI_SC', 'DICHIARAZIONE_IRAP'].includes(check.extraction?.document_type) && declaredFields.length > 0 && <div className="fiscal-f24-table-wrap" style={{ marginTop: 10 }}><table className="fiscal-f24-table">
                    <thead><tr><th>Campo</th><th>Valore</th><th>Pagina</th><th>Prova</th></tr></thead>
                    <tbody>{declaredFields.map(field => <tr key={field.id}><td><strong>{field.field}</strong></td><td>{euro(field.value)}</td><td>{field.page_number}</td><td>{field.source_text}</td></tr>)}</tbody>
                  </table></div>}
                  {check.extraction?.f24_expectation && <div style={{ marginTop: 10, padding: '9px 12px', borderRadius: 8, background: check.extraction.field_level_status === 'ESTRATTO_CON_CERTEZZA' ? '#ecfdf5' : '#fffbeb', color: check.extraction.field_level_status === 'ESTRATTO_CON_CERTEZZA' ? '#166534' : '#92400e' }}>
                    <strong>Esito dichiarazione:</strong> {String(check.extraction.f24_expectation).replaceAll('_', ' ')}
                    {check.extraction.version_warning && <div style={{ marginTop: 4 }}>{check.extraction.version_warning}</div>}
                  </div>}
                  {managementRows.length > 0 && <div className="fiscal-f24-table-wrap" style={{ marginTop: 10 }}><table className="fiscal-f24-table">
                    <thead><tr><th>Periodo</th><th>Campo</th><th>Dichiarazione</th><th>Gestionale</th><th>Esito</th></tr></thead>
                    <tbody>{managementRows.map(row => <tr key={row.id}><td>{row.period}</td><td>{row.field || row.tax_code || '—'}</td><td>{euro(row.declared_cents == null ? null : row.declared_cents / 100)}</td><td>{euro(row.management_cents == null ? null : row.management_cents / 100)}</td><td><Badge variant={row.status === 'CONCORDANTE' ? 'success' : 'warning'}>{row.status.replaceAll('_', ' ')}</Badge></td></tr>)}</tbody>
                  </table></div>}
                  {check.management_warning && <div className="fiscal-muted" style={{ marginTop: 8 }}>Dati gestionali non confrontabili: {check.management_warning}</div>}
                </div>}
              </article>;
            })}
          </div>
        </section>}
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
        <section className="fiscal-list-filters" aria-label={`Filtri ${activeLabel}`}>
          <label className="fiscal-search">Cerca nella sezione
            <input value={listQuery} onChange={event => { setListQuery(event.target.value); setPage(1); }} placeholder="Codice, descrizione, periodo, protocollo o file…" />
          </label>
          <label>Anno
            <select value={listYear} onChange={event => { setListYear(event.target.value); setPage(1); }}>
              <option value="">Tutti</option>{listYears.map(year => <option key={year}>{year}</option>)}
            </select>
          </label>
          <label>Stato
            <select value={listStatus} onChange={event => { setListStatus(event.target.value); setPage(1); }}>
              <option value="">Tutti</option>{listStatuses.map(status => <option key={status} value={status}>{status.replaceAll('_', ' ')}</option>)}
            </select>
          </label>
          <label>Righe per pagina
            <select value={pageSize} onChange={event => { setPageSize(Number(event.target.value)); setPage(1); }}>
              {PAGE_SIZES.map(size => <option key={size}>{size}</option>)}
            </select>
          </label>
          <Button variant="secondary" onClick={resetListFilters} disabled={!listQuery && !listYear && !listStatus}>Azzera filtri</Button>
        </section>
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
        {!loading && items.length === 0 && <p>{({
          'crosswalk-riscossione': 'Nessun collegamento di riscossione presente nell’indice Drive.',
          riscossione: 'Nessuna cartella o posizione di riscossione presente nell’indice Drive.',
          ader: 'Nessuno snapshot AdeR presente nell’indice Drive.',
        }[tab] || 'Nessun documento presente nella sezione Drive corrispondente.')}</p>}
        {!loading && items.length > 0 && filteredItems.length === 0 && <div className="fiscal-empty"><strong>Nessun risultato con questi filtri.</strong><Button variant="secondary" onClick={resetListFilters}>Mostra tutti</Button></div>}
        <div className="fiscal-records">
        {visibleItems.map((item, index) => {
          const entityId = item.id || item.collection_number || item.code || `row-${index}`;
          if (tab === 'confronto-fonti') return <article key={entityId} className="fiscal-record">
            <div className="fiscal-record-header"><strong>{item.accountant_document?.filename || item.official_document?.filename || 'Documento fiscale'}</strong><Badge variant={item.requires_review ? 'warning' : 'success'}>{String(item.status || '').replaceAll('_', ' ')}</Badge></div>
            <div className="fiscal-data-grid">
              <span><small>Fonte commercialista</small><strong>{item.accountant_document?.document_id || 'Mancante'}</strong></span>
              <span><small>Quietanza Drive</small><strong>{item.official_document?.document_id || 'Mancante'}</strong></span>
              <span><small>Righe fiscali</small><strong>{item.accountant_document?.row_count ?? item.official_document?.row_count ?? 0}</strong></span>
              <span><small>Candidati esatti</small><strong>{item.candidate_count || 0}</strong></span>
            </div>
            <div style={{ marginTop: 8 }}><Badge variant={item.erario_state === 'NULLA_DOVUTO_ERARIO_DOCUMENTATO' ? 'success' : 'warning'}>{String(item.erario_state || 'PROVE F24 DA VERIFICARE').replaceAll('_', ' ')}</Badge></div>
            <div className="fiscal-muted" style={{ marginTop: 8 }}>Regola: codice tributo + periodo + sezione + ente + debito/credito in centesimi. Il solo importo non conferma mai un collegamento.</div>
          </article>;
          if (item.is_f24_group) return <article key={entityId} className="fiscal-record fiscal-f24-record">
            <details>
              <summary className="fiscal-f24-summary">
                <div className="fiscal-f24-mark" aria-hidden="true">F24</div>
                <div className="fiscal-f24-identity">
                  <small>{item.documentary_payment_status === 'QUIETANZA_PRESENTE' ? 'Quietanza F24' : 'Modello F24'}</small>
                  <strong>Protocollo {item.protocol || 'non indicato'}</strong>
                  <span>{item.payment_date || 'Data non indicata'} · {item.rows.length} righe tributo</span>
                </div>
                <div className="fiscal-f24-totals"><span><small>Totale debiti</small><strong>{euro(item.debit_amount)}</strong></span><span><small>Totale crediti</small><strong>{euro(item.credit_amount)}</strong></span><span><small>Saldo delega</small><strong>{euro(item.net_amount)}</strong></span></div>
                <Badge variant="info">{String(item.payment_status || item.evidence_state || 'DOCUMENTO F24').replaceAll('_', ' ')}</Badge>
              </summary>
              <div className="fiscal-f24-sheet">
                <div className="fiscal-f24-watermark" aria-hidden="true">F24</div>
                <div className="fiscal-f24-file" title={item.filename}>{item.filename || 'Nome file non disponibile'}</div>
                <div className="fiscal-f24-table-wrap"><table className="fiscal-f24-table">
                  <thead><tr><th>Codice</th><th>Descrizione</th><th>Periodo</th><th>Debito</th><th>Credito</th></tr></thead>
                  <tbody>{item.rows.map((row, rowIndex) => <tr key={row.id || `${entityId}-${rowIndex}`}><td><strong>{row.tax_code || '—'}</strong></td><td>{row.description || row.section || 'Tributo F24'}</td><td>{row.reference_period || '—'}</td><td>{euro(row.debit_amount)}</td><td>{euro(row.credit_amount)}</td></tr>)}</tbody>
                  <tfoot><tr><th colSpan="3">Totali documento</th><th>{euro(item.debit_amount)}</th><th>{euro(item.credit_amount)}</th></tr><tr><th colSpan="3">Saldo delega (debiti − crediti)</th><th colSpan="2">{euro(item.net_amount)}</th></tr></tfoot>
                </table></div>
                <div className="fiscal-evidence"><strong>{item.documentary_payment_status === 'QUIETANZA_PRESENTE' ? 'Quietanza documentale presente' : 'Modello F24 presente'} · riscontro bancario da verificare</strong></div>
                <div className="fiscal-actions"><Button size="sm" variant="secondary" disabled={!item.document_id} onClick={() => openDriveDocument(item.document_id)}>Apri PDF Drive</Button></div>
              </div>
            </details>
          </article>;
          const technicalLabel = String(labelForClaim(item) || '');
          const title = tab === 'f24' ? `${item.tax_code || item.section || 'Riga F24'} · ${item.reference_period || 'periodo non indicato'}`
            : tab === 'dichiarazioni' ? `${item.document_type} · ${item.filing_year || 'anno da verificare'}`
              : ((tab === 'tributi' || tab === 'tributi-pagati') && item.source_kind === 'DRIVE_EXCEL_INDEX_F24_ROW') ? `${item.tax_code || 'Codice non indicato'} · ${item.description || item.section || 'Tributo F24'}`
                : (technicalLabel.startsWith('drive-f24-row:') ? (item.description || item.tax_code || 'Tributo F24') : (technicalLabel || item.code || item.version_id || 'Record fiscale'));
          return <article key={entityId} className="fiscal-record">
            <div className="fiscal-record-header"><strong>{title}</strong>
            {(item.calculated_business_status || item.business_status || item.payment_status || item.status) && <Badge variant={item.requires_review ? 'warning' : 'info'}>{item.calculated_business_status || item.business_status || item.payment_status || item.status}</Badge>}
            </div>
            {item.official_description && <div className="fiscal-muted">{item.official_description}</div>}
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
            {(tab === 'tributi' || tab === 'tributi-pagati') && item.source_kind === 'DRIVE_EXCEL_INDEX_F24_ROW' && <div className="fiscal-record-body">
              <div className="fiscal-data-grid"><span><small>Periodo</small><strong>{item.reference_period || 'Non indicato'}</strong></span><span><small>Debito</small><strong>{euro(item.debit_amount)}</strong></span><span><small>Credito</small><strong>{euro(item.credit_amount)}</strong></span><span><small>Data</small><strong>{item.payment_date || 'Non indicata'}</strong></span></div>
              <div className="fiscal-file" title={item.filename}>{item.filename || 'Nome file non disponibile'}{item.protocol && <> · protocollo {item.protocol}</>}</div>
              <div className="fiscal-evidence"><strong>{item.documentary_payment_status === 'QUIETANZA_PRESENTE' ? 'Quietanza documentale presente' : 'Modello F24 presente'} · riscontro bancario da verificare</strong></div>
              <div className="fiscal-actions"><Button size="sm" variant="secondary" disabled={!item.document_id} onClick={() => openDriveDocument(item.document_id)}>Apri PDF Drive</Button></div>
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
            {tab === 'riscossione' && (item.payment_evidence_ids || []).length > 0 && <div style={{ marginTop: 8, color: '#166534', fontWeight: 700 }}>
              Pagamento documentato collegato · prove: {item.payment_evidence_ids.length}
            </div>}
            {tab === 'f24' && <Button size="sm" variant="secondary" style={{ marginTop: 8 }} disabled={!item.document_id} onClick={() => openDriveDocument(item.document_id)}>Apri PDF Drive</Button>}
          </article>;
        })}
        </div>
        {!loading && filteredItems.length > pageSize && <nav className="fiscal-pagination" aria-label="Paginazione risultati">
          <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(value => Math.max(1, value - 1))}>Precedente</Button>
          <span>Pagina <strong>{Math.min(page, pageCount)}</strong> di <strong>{pageCount}</strong></span>
          <Button variant="secondary" disabled={page >= pageCount} onClick={() => setPage(value => Math.min(pageCount, value + 1))}>Successiva</Button>
        </nav>}
      </Card>
    </PageLayout>
  );
}

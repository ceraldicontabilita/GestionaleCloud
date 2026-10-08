import React, { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import api from '../api';
import { PageLayout } from '../components/PageLayout';
import { VisoreOriginale } from '../components/ApriOriginale';
import { urlOriginale } from '../lib/vista';
import { Badge, Button, Card, HubTabs, PageLoader, StatCard } from '../components/ds';
import './SituazioneFiscale.css';

// Le schede che erano pagine a se' (Piano tributi, Tributi per codice, Ritenute): qui si
// mostrano con la loro stessa vista, senza una seconda copia. I vecchi indirizzi
// Le sottosezioni fiscali vivono esclusivamente sotto /situazione-fiscale/.
const PianoTributi = lazy(() => import('./PianoTributi'));
const Tributi = lazy(() => import('./Tributi'));
const Ritenute = lazy(() => import('./Ritenute'));
const SCHEDE_INCORPORATE = [
  ['piano', 'Piano tributi', PianoTributi],
  ['tributi-per-codice', 'Tributi', Tributi],
  ['ritenute', 'Ritenute', Ritenute],
];

const TABS = [
  ['tributi', 'Tributi F24'],
  ['dichiarazioni', 'Dichiarazioni'],
  ['confronto-fonti', 'Confronto fonti'],
  ['f24', 'F24 e crediti'],
  ['codici-tributo', 'Codici tributo'],
  ['crosswalk-riscossione', 'Crosswalk riscossione'],
  ['riscossione', 'Riscossione'],
  ['ader', 'Snapshot AdeR'],
];

// Documenti F24 interi (righe tributo raggruppate per modello o quietanza):
// raggruppamento, filtri, conteggi e totali li fa il server
// (registro_fiscale_f24.pagina_documenti_f24), che rende 200 documenti alla
// volta. Le altre schede restano piccole e si filtrano qui.
const SERVER_TABS = new Set(['tributi', 'f24']);
const RIGHE_PER_PAGINA = 200;

export const parametriElenco = ({ cerca = '', anno = '', stato = '', offset = 0 } = {}) => {
  const params = new URLSearchParams({
    raggruppa: 'true', limit: String(RIGHE_PER_PAGINA), offset: String(offset),
  });
  if (String(cerca).trim()) params.set('cerca', String(cerca).trim());
  if (anno) params.set('anno_documento', anno);
  if (stato) params.set('stato_documento', stato);
  return params.toString();
};

export const endpointFor = (tab, f24Filters = {}, taxCodeFilters = {}, elenco = {}) => {
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
    const base = params.toString();
    return `/api/fiscal/f24-rows?${base ? `${base}&` : ''}${parametriElenco(elenco)}`;
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
    // Una lista sola: «da pagare», «pagati con quietanza» e il resto sono valori del filtro Stato.
    tributi: `/api/fiscal/obligations?${parametriElenco(elenco)}`,
    'confronto-fonti': '/api/fiscal/source-certainty',
    'crosswalk-riscossione': '/api/fiscal/crosswalk',
    riscossione: '/api/fiscal/collections',
    ader: '/api/fiscal/ader-snapshots',
  }[tab]);
};

const TUTTE_LE_SCHEDE = [...SCHEDE_INCORPORATE.map(([id, label]) => [id, label]), ...TABS];

function SchedeFiscali({ tab }) {
  const navigate = useNavigate();
  return (
    <HubTabs
      testIdPrefix="tab-fiscale"
      activeId={tab}
      onSelect={t => navigate(`/situazione-fiscale/${t.id}`)}
      tabs={TUTTE_LE_SCHEDE.map(([id, label]) => ({ id, label }))}
    />
  );
}

const labelForClaim = item => item.document_number || item.collection_number || item.cartella_number_original || item.id;
const euro = value => value == null ? 'Non disponibile' : new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(value);
const searchableText = item => Object.values(item || {}).filter(value => ['string', 'number'].includes(typeof value)).join(' ').toLocaleLowerCase('it');
const itemYear = item => String(item.payment_year || item.filing_year || item.tax_year || item.year || item.notification_date || item.payment_date || '').slice(0, 4);
const itemStatus = item => item.documentary_payment_status || item.evidence_state || item.calculated_business_status || item.business_status || item.payment_status || item.status || '';
const F24_ROW = 'F24_REGISTRO_ROW';

export const resolveDeclarationVersions = (declarations = [], checks = {}) => {
  const groups = new Map();
  declarations.forEach(item => {
    const key = item.document_type === 'LIPE' || !item.tax_year
      ? `${item.document_type || 'UNKNOWN'}:${item.document_id}`
      : `${item.document_type || ''}:${item.tax_year || ''}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  });
  const selectedIds = new Set();
  const states = {};
  let resolvedGroups = 0;
  let unresolvedGroups = 0;
  groups.forEach(group => {
    if (group.length === 1) {
      selectedIds.add(group[0].document_id);
      states[group[0].document_id] = 'VERSIONE_UNICA';
      return;
    }
    const evidence = group.map(item => ({ item, extraction: checks[item.document_id]?.extraction }));
    const complete = evidence.every(({ item, extraction }) => extraction && !checks[item.document_id]?.error
      && extraction.declaration_identity_proven && extraction.taxpayer_tax_code
      && extraction.declaration_filing_date && extraction.declaration_identifier);
    const taxpayerCodes = new Set(evidence.map(({ extraction }) => extraction?.taxpayer_tax_code).filter(Boolean));
    const ordered = [...evidence].sort((a, b) =>
      String(b.extraction?.declaration_filing_date || '').localeCompare(String(a.extraction?.declaration_filing_date || '')));
    const latest = ordered[0];
    const latestDateUnique = ordered.length > 1
      && latest.extraction?.declaration_filing_date > ordered[1].extraction?.declaration_filing_date;
    const latestIsExplicitIntegration = String(latest.extraction?.submission_kind || '').startsWith('DICHIARAZIONE_INTEGRATIVA_CODICE_');
    if (complete && taxpayerCodes.size === 1 && latestDateUnique && latestIsExplicitIntegration) {
      selectedIds.add(latest.item.document_id);
      group.forEach(item => { states[item.document_id] = item.document_id === latest.item.document_id
        ? 'VERSIONE_INTEGRATIVA_PIU_RECENTE_SELEZIONATA' : 'SOSTITUITA_DA_INTEGRATIVA_PIU_RECENTE'; });
      resolvedGroups += 1;
    } else {
      group.forEach(item => { states[item.document_id] = 'IDENTITA_O_VERSIONE_NON_PROVATA'; });
      unresolvedGroups += 1;
    }
  });
  return { selectedIds, states, resolvedGroups, unresolvedGroups };
};

function ElenchiFiscali() {
  const location = useLocation();
  const tab = TABS.find(([id]) => location.pathname.endsWith(`/${id}`))?.[0] || 'tributi';
  const [summary, setSummary] = useState(null);
  const [obblighiVisibili, setObblighiVisibili] = useState(200);
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
  const [uploadingF24Model, setUploadingF24Model] = useState(false);
  const accountantF24Input = useRef(null);
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
  // Testo cercato, applicato dopo una pausa: ogni tasto non e' una richiesta.
  const [listQueryApplicata, setListQueryApplicata] = useState('');
  const [mostrati, setMostrati] = useState(RIGHE_PER_PAGINA);
  const [elencoMeta, setElencoMeta] = useState(null);
  const [caricaAltri, setCaricaAltri] = useState(false);
  const elencoServer = SERVER_TABS.has(tab);
  const chiaveElenco = elencoServer ? `${listQueryApplicata}|${listYear}|${listStatus}` : '';
  const filtriEndpoint = () => ({
    year: tab === 'dichiarazioni' ? declarationYear : f24Year,
    declarationType, taxCode: f24TaxCode, creditsOnly: f24CreditsOnly,
  });

  const load = useCallback(async () => {
    setLoading(true);
    const warnings = [];
    try {
      const [summaryResult, dataResult] = await Promise.allSettled([
        api.get('/api/fiscal/summary'), api.get(endpointFor(tab, filtriEndpoint(), taxCodeFilters,
          elencoServer ? { cerca: listQueryApplicata, anno: listYear, stato: listStatus } : {})),
      ]);
      if (summaryResult.status === 'fulfilled') {
        setSummary(summaryResult.value.data);
      } else {
        warnings.push('Riepilogo temporaneamente non disponibile; i dati della sezione restano consultabili.');
      }
      if (dataResult.status === 'fulfilled') {
        const payload = dataResult.value.data || {};
        setItems(payload.items || []);
        setElencoMeta(SERVER_TABS.has(tab) ? payload : null);
        setMostrati(RIGHE_PER_PAGINA);
        setTaxCodeMeta(payload.catalog || null);
        setTaxCodeOptions(payload.filters || { tax_types: [], contexts: [] });
        setTabSources(payload.sources || null);
        setTabMeta(payload.latest_import || null);
        setCertaintyMeta(tab === 'confronto-fonti' ? payload : null);
        setAderRelated({ ratePlans: payload.rate_plans || [], settlements: payload.settlements || [] });
      } else {
        const error = dataResult.reason;
        setItems([]);
        setElencoMeta(null);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, f24Year, f24TaxCode, f24CreditsOnly, declarationYear, declarationType, taxCodeFilters, chiaveElenco]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    setListQuery(''); setListQueryApplicata(''); setListYear(''); setListStatus('');
    setMostrati(RIGHE_PER_PAGINA);
  }, [tab]);
  useEffect(() => {
    const timer = setTimeout(() => setListQueryApplicata(listQuery), 300);
    return () => clearTimeout(timer);
  }, [listQuery]);

  // «Mostra altre»: i documenti successivi si chiedono al server e si
  // accodano; conteggi e totali restano quelli dell'intero elenco.
  const caricaAltriDocumenti = async () => {
    setCaricaAltri(true);
    try {
      const response = await api.get(endpointFor(tab, filtriEndpoint(), taxCodeFilters, {
        cerca: listQueryApplicata, anno: listYear, stato: listStatus, offset: items.length,
      }));
      setItems(current => [...current, ...(response.data?.items || [])]);
    } catch (error) {
      toast.error('Altri documenti non caricati', { description: error.response?.data?.detail || error.message });
    } finally { setCaricaAltri(false); }
  };

  // Un solo modo di aprire un originale (DRV-04): il visualizzatore dell'endpoint unico.
  const [originaleAperto, setOriginaleAperto] = useState(null);
  const openDocument = documentId => setOriginaleAperto({
    url: urlOriginale({ tipo: 'documento_fiscale', id: documentId }), titolo: 'Documento fiscale',
  });
  const openF24Pdf = pdfUrl => setOriginaleAperto({ url: pdfUrl, titolo: 'Modello F24' });

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

  const uploadAccountantF24 = async event => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    const data = new FormData();
    data.append('file', file);
    data.append('anno', f24Year || declarationYear || String(new Date().getFullYear()));
    data.append('note', 'Caricato manualmente come modello F24 ricevuto dal commercialista');
    setUploadingF24Model(true);
    try {
      const response = await api.post('/api/documenti-fiscali/upload-f24-commercialista', data, { headers: { 'Content-Type': 'multipart/form-data' } });
      toast.success(response.data?.duplicate ? 'Modello F24 già presente' : 'Modello F24 del commercialista acquisito', {
        description: 'Il modello è registrato come importo atteso. Il pagamento sarà provato solo dalla quietanza AdE.',
      });
      await load();
    } catch (error) {
      toast.error('Caricamento F24 non riuscito', { description: error.response?.data?.detail || error.message });
    } finally { setUploadingF24Model(false); }
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
      item.document_id && ['PRONTO_PER_VERIFICA_CAMPI', 'PRONTO_PER_VERIFICA_IDENTITA_VERSIONE'].includes(item.field_check_status));
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
    else toast.success('Registro dichiarazioni aggiornato');
  };

  const counts = summary?.counts || {};
  const activeLabel = useMemo(() => TABS.find(([id]) => id === tab)?.[1], [tab]);
  const listYears = useMemo(() => (elencoServer
    ? elencoMeta?.facets?.anni || []
    : [...new Set(items.map(itemYear).filter(year => /^20\d{2}$/.test(year)))].sort().reverse()),
  [elencoServer, elencoMeta, items]);
  const listStatuses = useMemo(() => (elencoServer
    ? elencoMeta?.facets?.stati || []
    : [...new Set(items.map(itemStatus).filter(Boolean))].sort()),
  [elencoServer, elencoMeta, items]);
  const filteredItems = useMemo(() => {
    if (elencoServer) return items;
    const needle = listQuery.trim().toLocaleLowerCase('it');
    return items.filter(item => (!needle || searchableText(item).includes(needle))
      && (!listYear || itemYear(item) === listYear)
      && (!listStatus || itemStatus(item) === listStatus));
  }, [elencoServer, items, listQuery, listYear, listStatus]);
  const totaleFiltrato = elencoServer ? (elencoMeta?.total ?? items.length) : filteredItems.length;
  const totaleSezione = elencoServer ? (elencoMeta?.total_groups ?? items.length) : items.length;
  const visibleItems = elencoServer ? items : filteredItems.slice(0, mostrati);
  const rimanenti = Math.max(0, totaleFiltrato - visibleItems.length);
  const mostraAltri = () => (elencoServer
    ? caricaAltriDocumenti()
    : setMostrati(value => value + RIGHE_PER_PAGINA));
  const resetListFilters = () => { setListQuery(''); setListYear(''); setListStatus(''); };
  const obligationRegister = useMemo(() => {
    const declarations = certaintyMeta?.declaration_items || [];
    const versionResolution = resolveDeclarationVersions(declarations, declarationChecks);
    const obligations = [];
    let processed = 0;
    let noDebit = 0;
    let failed = 0;
    declarations.forEach(declaration => {
      const check = declarationChecks[declaration.document_id];
      if (!check) return;
      if (check.error) { failed += 1; return; }
      processed += 1;
      if (!versionResolution.selectedIds.has(declaration.document_id)) return;
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
      obligations, processed, noDebit, failed, versionResolution,
      unprocessed: Math.max(0, declarations.length - processed - failed),
      paid: paid.length, due: due.length, review: review.length,
      expectedAmount: obligations.reduce((sum, item) => sum + item.amount, 0),
      paidAmount: paid.reduce((sum, item) => sum + item.amount, 0),
      dueAmount: due.reduce((sum, item) => sum + item.amount, 0),
    };
  }, [certaintyMeta, declarationChecks]);
  return (
    <PageLayout title="Situazione fiscale"
      subtitle="Obblighi, pagamenti, cartelle e prove restano distinti e verificabili"
      actions={<Button variant="secondary" onClick={load} disabled={loading}>Aggiorna</Button>}>
      <SchedeFiscali tab={tab} />
      <div className="fiscal-stats">
        <StatCard label="Modelli F24" value={counts.f24_documents || 0} accent="primary" />
        <StatCard label="Righe tributo" value={counts.f24_rows || 0} accent="primary" />
        <StatCard label="Dichiarazioni" value={counts.declarations || 0} accent="primary" />
        <StatCard label="Tributi a debito" value={counts.tax_debit_rows || 0} accent="primary" />
        <StatCard label="Quietanze con righe" value={counts.documentary_payment_documents || 0} accent="success" />
      </div>
      {loadWarnings.length > 0 && <Card style={{ marginBottom: 18 }} bodyStyle={{ padding: 14, color: '#92400e', background: '#fffbeb' }}>
        {loadWarnings.map(message => <div key={message}>{message}</div>)}
      </Card>}
      <Card bodyStyle={{ padding: 16 }}>
        <div className="fiscal-section-heading"><div><h3>{activeLabel}</h3><p data-testid="fiscal-conteggio">{totaleFiltrato} {elencoServer ? 'documenti' : 'risultati'} su {totaleSezione}{elencoServer && ` · ${elencoMeta?.total_rows ?? 0} righe tributo`}{elencoServer && elencoMeta?.totali && ` · debiti ${euro(elencoMeta.totali.debit_amount)} · crediti ${euro(elencoMeta.totali.credit_amount)}`}</p></div></div>
        {tab === 'confronto-fonti' && certaintyMeta && <div className="fiscal-stats" style={{ marginBottom: 16 }}>
          <StatCard label="Concordanti" value={certaintyMeta.certain || 0} accent="success" />
          <StatCard label="Da verificare" value={certaintyMeta.requires_review || 0} accent="warning" />
          <StatCard label="F24 commercialista" value={certaintyMeta.sources?.commercialista_f24_documents || 0} accent="primary" />
          <StatCard label="Modelli F24 senza provenienza" value={certaintyMeta.sources?.unattributed_f24_model_documents || 0} accent="warning" />
          <StatCard label="Righe da quietanza" value={certaintyMeta.sources?.quietanza_drive_rows || 0} accent="primary" />
          <StatCard label="Dichiarazioni" value={certaintyMeta.declarations?.documents || 0} accent="primary" />
          <StatCard label="Identità/versione da verificare" value={certaintyMeta.declarations?.identity_or_version_review || 0} accent="warning" />
        </div>}
        {tab === 'confronto-fonti' && certaintyMeta?.declarations?.requires_review && <div style={{ margin: '0 0 14px', padding: '10px 12px', borderRadius: 8, background: '#fffbeb', color: '#92400e' }}>
          <strong>Verifica dichiarazioni disponibile per i modelli supportati.</strong> Ogni valore conserva pagina e testo sorgente; le righe non univoche restano da verificare e non vengono collegate per il solo importo.
          {(certaintyMeta.declarations?.identity_or_version_review || 0) > 0 && <div style={{ marginTop: 4 }}><strong>{certaintyMeta.declarations.identity_or_version_review} dichiarazioni escluse dal totale automatico:</strong> esistono più PDF dello stesso tipo e anno d’imposta; occorre provare dal documento il dichiarante e quale versione sia valida.</div>}
        </div>}
        {tab === 'confronto-fonti' && (certaintyMeta?.declaration_items || []).length > 0 && <section aria-labelledby="obligation-register-heading" className="fiscal-record" style={{ marginBottom: 18 }}>
          <div className="fiscal-record-header">
            <div><h4 id="obligation-register-heading" style={{ margin: 0 }}>Registro automatico dovuto / pagato</h4><div className="fiscal-muted">Dichiarazioni → F24 commercialista → quietanze → dati gestionali disponibili</div></div>
            <div className="fiscal-actions">
              <input ref={accountantF24Input} type="file" accept="application/pdf,.pdf" hidden onChange={uploadAccountantF24} disabled={uploadingF24Model} />
              <Button variant="secondary" onClick={() => accountantF24Input.current?.click()} disabled={uploadingF24Model}>
                {uploadingF24Model ? 'Caricamento F24…' : 'Inserisci F24 commercialista'}
              </Button>
              <Button variant="primary" onClick={checkAllDeclarations} disabled={checkingAllDeclarations}>
                {checkingAllDeclarations ? `Verifica ${declarationCheckProgress.completed}/${declarationCheckProgress.total}` : 'Verifica tutte le dichiarazioni'}
              </Button>
            </div>
          </div>
          <div className="fiscal-data-grid" style={{ marginTop: 12 }}>
            <span><small>Pagati con quietanza</small><strong>{obligationRegister.paid} · {euro(obligationRegister.paidAmount)}</strong></span>
            <span><small>Ancora dovuti</small><strong>{obligationRegister.due} · {euro(obligationRegister.dueAmount)}</strong></span>
            <span><small>Da verificare</small><strong>{obligationRegister.review}</strong></span>
            <span><small>Dichiarazioni elaborate</small><strong>{obligationRegister.processed}/{certaintyMeta.declaration_items.length}</strong></span>
            <span><small>Senza debiti estratti</small><strong>{obligationRegister.noDebit}</strong></span>
            <span><small>Non elaborate / errore</small><strong>{obligationRegister.unprocessed + obligationRegister.failed}</strong></span>
            <span><small>Gruppi versione risolti</small><strong>{obligationRegister.versionResolution.resolvedGroups}</strong></span>
            <span><small>Gruppi versione non risolti</small><strong>{obligationRegister.versionResolution.unresolvedGroups}</strong></span>
          </div>
          {obligationRegister.obligations.length > 0 && <div className="fiscal-f24-table-wrap" style={{ marginTop: 12 }}><table className="fiscal-f24-table">
            <thead><tr><th>Dichiarazione</th><th>Tributo / periodo</th><th>Importo dovuto</th><th>F24 commercialista</th><th>Stato Erario</th><th>Confronto gestionale</th></tr></thead>
            <tbody>{obligationRegister.obligations.slice(0, obblighiVisibili).map(item => <tr key={item.id}>
              <td><strong>{item.declaration.document_type}</strong><div className="fiscal-muted">{item.declaration.filename}</div></td>
              <td><strong>{item.row.declaration_row?.tax_code || '—'}</strong><div>{item.row.declaration_row?.reference_period || '—'}</div></td>
              <td>{euro(item.amount)}</td>
              <td><Badge variant={item.row.accountant_f24_present ? 'info' : 'warning'}>{item.row.accountant_f24_present ? 'PRESENTE' : 'NON TROVATO'}</Badge>{item.row.unattributed_f24_model_present && <div className="fiscal-muted">Modello simile presente, ma provenienza commercialista non provata</div>}</td>
              <td><Badge variant={item.paid ? 'success' : 'warning'}>{String(item.row.erario_state || item.row.status).replaceAll('_', ' ')}</Badge>{item.row.coverage_match && <div>{item.row.f24_rows?.length || 0} quietanze sommate · netto {euro((item.row.related_debit_amount || 0) - (item.row.related_credit_amount || 0))}</div>}{item.row.coverage_surplus_amount > 0 && <div className="fiscal-muted">Eccedenza quietanzata da verificare: {euro(item.row.coverage_surplus_amount)}</div>}</td>
              <td><Badge variant={item.managementState === 'CONCORDANTE_CON_GESTIONALE' ? 'success' : 'warning'}>{item.managementState.replaceAll('_', ' ')}</Badge></td>
            </tr>)}</tbody>
            <tfoot><tr><th colSpan="2">Totale debiti dichiarati elaborati</th><th>{euro(obligationRegister.expectedAmount)}</th><th colSpan="3">Calcolo al centesimo; nessun collegamento per solo importo</th></tr></tfoot>
          </table></div>}
          {obligationRegister.obligations.length > obblighiVisibili && <div style={{ marginTop: 8 }}><Button variant="secondary" onClick={() => setObblighiVisibili(v => v + 200)}>Mostra altre {obligationRegister.obligations.length - obblighiVisibili}</Button></div>}
          {declarationCheckProgress.failed > 0 && <div className="fiscal-muted" style={{ marginTop: 8 }}>{declarationCheckProgress.failed} documenti non elaborati: restano esplicitamente da verificare.</div>}
        </section>}
        {tab === 'confronto-fonti' && (certaintyMeta?.declaration_items || []).length > 0 && <section aria-labelledby="declaration-certainty-heading" style={{ marginBottom: 18 }}>
          <h4 id="declaration-certainty-heading" style={{ margin: '0 0 10px' }}>Dichiarazioni → F24</h4>
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
                {obligationRegister.versionResolution.states[declaration.document_id] && <div style={{ marginTop: 6 }}><Badge variant={obligationRegister.versionResolution.selectedIds.has(declaration.document_id) ? 'success' : 'warning'}>{obligationRegister.versionResolution.states[declaration.document_id].replaceAll('_', ' ')}</Badge></div>}
                <div className="fiscal-actions" style={{ marginTop: 10 }}>
                  <Button size="sm" variant="primary" disabled={!declaration.document_id || !['PRONTO_PER_VERIFICA_CAMPI', 'PRONTO_PER_VERIFICA_IDENTITA_VERSIONE'].includes(declaration.field_check_status) || checkingDeclaration === declaration.document_id} onClick={() => checkDeclarationFields(declaration.document_id)}>
                    {checkingDeclaration === declaration.document_id ? 'Verifica…' : 'Verifica campi e F24'}
                  </Button>
                  <Button size="sm" variant="secondary" disabled={!declaration.document_id} onClick={() => openDocument(declaration.document_id)}>Apri dichiarazione</Button>
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
                      <td><Badge variant={row.erario_state === 'NULLA_DOVUTO_ERARIO_DOCUMENTATO' ? 'success' : 'warning'}>{String(row.erario_state || row.status).replaceAll('_', ' ')}</Badge>{row.aggregate_match && <div>{row.f24_rows?.length || 0} quietanze/F24 sommati</div>}{row.coverage_surplus_amount > 0 && <div className="fiscal-muted">Eccedenza quietanzata da verificare: {euro(row.coverage_surplus_amount)}</div>}{row.candidate_count > 1 && !row.aggregate_match && <div>{row.candidate_count} candidati esatti</div>}{row.related_candidate_count > 0 && row.erario_state !== 'NULLA_DOVUTO_ERARIO_DOCUMENTATO' && <div>{row.related_candidate_count} righe stesso codice/anno · debiti {euro(row.related_debit_amount)} · crediti {euro(row.related_credit_amount)}</div>}</td>
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
                    <tbody>{managementRows.map((row, rowIndex) => <tr key={row.id || `${declaration.document_id}-${row.period || 'periodo'}-${row.field || row.tax_code || rowIndex}`}><td>{row.period}</td><td>{row.field || row.tax_code || '—'}</td><td>{euro(row.declared_cents == null ? null : row.declared_cents / 100)}</td><td>{euro(row.management_cents == null ? null : row.management_cents / 100)}</td><td><Badge variant={row.status === 'CONCORDANTE' ? 'success' : 'warning'}>{row.status.replaceAll('_', ' ')}</Badge></td></tr>)}</tbody>
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
        </div>}
        {tab === 'codici-tributo' && <>
          {taxCodeMeta && <div style={{ margin: '0 0 14px', padding: '12px 14px', borderRadius: 10, background: '#f7ebe4', border: '1px solid #c2ddd0' }}>
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
            <input value={listQuery} onChange={event => setListQuery(event.target.value)} placeholder="Codice, descrizione, periodo, protocollo o file…" />
          </label>
          <label>Anno
            <select value={listYear} onChange={event => setListYear(event.target.value)}>
              <option value="">Tutti</option>{listYears.map(year => <option key={year}>{year}</option>)}
            </select>
          </label>
          <label>Stato
            <select value={listStatus} onChange={event => setListStatus(event.target.value)}>
              <option value="">Tutti</option>{listStatuses.map(status => <option key={status} value={status}>{status.replaceAll('_', ' ')}</option>)}
            </select>
          </label>
          <Button variant="secondary" onClick={resetListFilters} disabled={!listQuery && !listYear && !listStatus}>Azzera filtri</Button>
        </section>
        {tab === 'ader' && tabMeta && <div style={{ margin: '0 0 14px', padding: '12px 14px', borderRadius: 10, background: '#f7ebe4', border: '1px solid #c2ddd0' }}>
          <strong>Ultimo archivio verificato:</strong> snapshot {tabMeta.snapshot_date || 'data non disponibile'} · {tabMeta.analytic_count || 0} posizioni · SHA-256 {String(tabMeta.dataset_sha256 || '').slice(0, 16)}…
        </div>}
        {tab === 'ader' && (aderRelated.ratePlans.length > 0 || aderRelated.settlements.length > 0) && <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', gap: 12, marginBottom: 16 }}>
          <section aria-labelledby="ader-rate-plans" style={{ padding: 14, borderRadius: 10, border: '1px solid #d0ccbe', background: '#f6f4ee' }}>
            <h4 id="ader-rate-plans" style={{ margin: '0 0 10px' }}>Piani rateali</h4>
            {aderRelated.ratePlans.length === 0 && <p style={{ margin: 0 }}>Nessun piano importato.</p>}
            {aderRelated.ratePlans.map(plan => <div key={plan.id} style={{ padding: '10px 0', borderTop: '1px solid #e6e3d9' }}>
              <strong>{plan.plan_reference}</strong>{' '}
              {plan.requires_review && <Badge variant="warning">Riferimenti da verificare</Badge>}
              <div style={{ marginTop: 5, color: '#5f5c55' }}>
                {plan.installment_count ?? 'N.'} rate · totale {euro(plan.total_plan_amount)} · prima rata {euro(plan.first_installment_amount)} il {plan.first_installment_due_date || 'data non disponibile'}
              </div>
              {(plan.payment_modules || []).map(module => <div key={module.id} style={{ marginTop: 5, color: '#5f5c55' }}>
                Modulo {module.document_number || module.source_filename}: {(module.installments || []).map(rate => `${rate.number}ª ${rate.due_date} ${euro(rate.amount)}`).join(' · ') || 'rate non leggibili'}
              </div>)}
              {(plan.reconciled_installments || []).map(rate => {
                const pagata = rate.status === 'PAID_DOCUMENTED' || rate.payment_evidence;
                return <div key={rate.id} data-testid="rata-piano" data-stato={pagata ? 'documentata' : 'attesa'} style={{ marginTop: 7, padding: '7px 9px', borderRadius: 7, background: pagata ? '#ecfdf5' : '#f7ebe4', color: pagata ? '#166534' : '#7a3b1e' }}>
                  <strong>Rata {rate.installment_number}: {pagata ? 'pagamento documentato' : 'attesa, nessuna prova di pagamento'}</strong>
                  {' · '}{euro(rate.amount)} · {rate.due_date || 'scadenza non disponibile'}
                  {pagata ? ` · ${rate.bank_verified ? 'banca verificata' : 'banca da verificare'}` : ''}
                </div>;
              })}
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
        {!loading && totaleSezione === 0 && <p>{({
          'crosswalk-riscossione': 'Nessun collegamento di riscossione registrato.',
          riscossione: 'Nessuna cartella o posizione di riscossione registrata.',
          ader: 'Nessuno snapshot AdeR registrato.',
        }[tab] || 'Nessun documento in questa sezione.')}</p>}
        {!loading && totaleSezione > 0 && totaleFiltrato === 0 && <div className="fiscal-empty"><strong>Nessun risultato con questi filtri.</strong><Button variant="secondary" onClick={resetListFilters}>Mostra tutti</Button></div>}
        <div className="fiscal-records">
        {visibleItems.map((item, index) => {
          const entityId = item.id || item.collection_number || item.code || `row-${index}`;
          if (tab === 'confronto-fonti') return <article key={entityId} className="fiscal-record">
            <div className="fiscal-record-header"><strong>{item.accountant_document?.filename || item.official_document?.filename || 'Documento fiscale'}</strong><Badge variant={item.requires_review ? 'warning' : 'success'}>{String(item.status || '').replaceAll('_', ' ')}</Badge></div>
            <div className="fiscal-data-grid">
              <span><small>Fonte commercialista</small><strong>{item.accountant_document?.document_id || 'Mancante'}</strong></span>
              <span><small>Quietanza</small><strong>{item.official_document?.document_id || 'Mancante'}</strong></span>
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
                  <strong>Protocollo {item.protocol || item.protocollo_quietanza || 'non indicato'}</strong>
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
                {item.pdf_url && <div className="fiscal-actions"><Button size="sm" variant="secondary" onClick={() => openF24Pdf(item.pdf_url)}>Apri PDF</Button></div>}
              </div>
            </details>
          </article>;
          const technicalLabel = String(labelForClaim(item) || '');
          const title = tab === 'f24' ? `${item.tax_code || item.section || 'Riga F24'} · ${item.reference_period || 'periodo non indicato'}`
            : tab === 'dichiarazioni' ? `${item.document_type} · ${item.filing_year || 'anno da verificare'}`
              : (tab === 'tributi' && item.source_kind === F24_ROW) ? `${item.tax_code || 'Codice non indicato'} · ${item.description || item.section || 'Tributo F24'}`
                : (technicalLabel.startsWith('drive-f24-row:') ? (item.description || item.tax_code || 'Tributo F24') : (technicalLabel || item.code || item.version_id || 'Record fiscale'));
          return <article key={entityId} className="fiscal-record">
            <div className="fiscal-record-header"><strong>{title}</strong>
            {(item.calculated_business_status || item.business_status || item.payment_status || item.status) && <Badge variant={item.requires_review ? 'warning' : 'info'}>{item.calculated_business_status || item.business_status || item.payment_status || item.status}</Badge>}
            </div>
            {item.official_description && <div className="fiscal-muted">{item.official_description}</div>}
            {tab === 'codici-tributo' && <div style={{ marginTop: 6 }}>
              <strong>{item.codice_tributo}</strong> · {item.descrizione}
              <div style={{ marginTop: 4, color: '#5f5c55' }}>
                {item.tipo_imposta || 'Tipo non indicato'} · {item.tipo_contribuente || 'Contribuente non indicato'} · {item.contesto_uso || 'Contesto non indicato'}
              </div>
              {item.url_esempio_compilazione && <a href={item.url_esempio_compilazione} target="_blank" rel="noreferrer" style={{ display: 'inline-block', marginTop: 5 }}>Esempio ufficiale di compilazione</a>}
            </div>}
            {tab === 'f24' && <div style={{ marginTop: 6, color: '#5f5c55' }}>
              Debito {euro(item.debit_amount)} · Credito {euro(item.credit_amount)} · {item.payment_date || 'data non indicata'}
              {item.protocol && <> · protocollo {item.protocol}</>}
              {item.filename && <div style={{ marginTop: 4 }}>{item.filename}</div>}
              {item.evidence_state && <div style={{ marginTop: 4 }}><strong>{item.evidence_state === 'MODELLO_F24_NON_PROVA_BANCARIA' ? 'Modello F24: pagamento bancario da verificare' : 'Quietanza documentale: banca da verificare'}</strong></div>}
            </div>}
            {tab === 'tributi' && item.source_kind === F24_ROW && <div className="fiscal-record-body">
              <div className="fiscal-data-grid"><span><small>Periodo</small><strong>{item.reference_period || 'Non indicato'}</strong></span><span><small>Debito</small><strong>{euro(item.debit_amount)}</strong></span><span><small>Credito</small><strong>{euro(item.credit_amount)}</strong></span><span><small>Data</small><strong>{item.payment_date || 'Non indicata'}</strong></span></div>
              <div className="fiscal-file" title={item.filename}>{item.filename || 'Nome file non disponibile'}{(item.protocol || item.protocollo_quietanza) && <> · protocollo {item.protocol || item.protocollo_quietanza}</>}</div>
              <div className="fiscal-evidence"><strong>{item.documentary_payment_status === 'QUIETANZA_PRESENTE' ? 'Quietanza documentale presente' : 'Modello F24 presente'} · riscontro bancario da verificare</strong></div>
              {item.pdf_url && <div className="fiscal-actions"><Button size="sm" variant="secondary" onClick={() => openF24Pdf(item.pdf_url)}>Apri PDF</Button></div>}
            </div>}
            {tab === 'dichiarazioni' && <div style={{ marginTop: 8, color: '#5f5c55' }}>
              <div>Anno d'imposta {item.tax_year || 'da verificare'}{item.protocol && <> · protocollo {item.protocol}</>}</div>
              <div>{item.filename}</div>
              <Button size="sm" variant="secondary" style={{ marginTop: 8 }} onClick={() => openDocument(item.id)}>Apri dichiarazione</Button>
              {(item.f24_links || []).map(link => <div key={link.f24_id} style={{ marginTop: 10, padding: 10, border: '1px solid #d0ccbe', borderRadius: 8 }}>
                <strong>F24 {link.filename || link.f24_id}</strong>{' '}<Badge variant={link.link_status === 'CONFIRMED' ? 'success' : 'warning'}>{link.link_status === 'CONFIRMED' ? 'Collegato' : 'Candidato da verificare'}</Badge>
                <div>{(link.tax_rows || []).map(row => `${row.tax_code} ${row.reference_period || ''}`).join(' · ')}</div>
                <div>Quietanza: {link.documentary_payment_status} · Banca: {link.bank_status}</div>
                {link.quietanza && <div>Protocollo quietanza: {link.quietanza.protocol || link.quietanza.id}</div>}
                {link.pagamento_tardivo && <div style={{ marginTop: 6 }}>
                  <Badge variant="info">Pagamento tardivo (ravvedimento)</Badge>{' '}
                  <span>{(link.ravvedimento_rows || []).map(row => `${row.tax_code} ${((row.debit_cents || 0) / 100).toFixed(2)}€`).join(' · ')}</span>
                </div>}
              </div>)}
              {(item.f24_links || []).length === 0 && <div style={{ marginTop: 8 }}>Nessun F24 compatibile trovato. Non viene creato alcun pagamento per inferenza.</div>}
            </div>}
            {tab === 'ader' && <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(170px,1fr))', gap: 8, marginTop: 10, color: '#4c4a44' }}>
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
            {tab === 'f24' && item.pdf_url && <Button size="sm" variant="secondary" style={{ marginTop: 8 }} onClick={() => openF24Pdf(item.pdf_url)}>Apri PDF</Button>}
          </article>;
        })}
        </div>
        {!loading && rimanenti > 0 && <nav className="fiscal-pagination" aria-label="Altri risultati">
          <Button variant="secondary" data-testid="fiscal-mostra-altre" onClick={mostraAltri} disabled={caricaAltri} style={{ minHeight: 44 }}>
            {caricaAltri ? 'Caricamento…' : `Mostra altre ${Math.min(RIGHE_PER_PAGINA, rimanenti)} · ${rimanenti} rimanenti`}
          </Button>
        </nav>}
      </Card>
      {originaleAperto && (
        <VisoreOriginale url={originaleAperto.url} titolo={originaleAperto.titolo} onClose={() => setOriginaleAperto(null)} />
      )}
    </PageLayout>
  );
}


export default function SituazioneFiscale() {
  const { pathname, search } = useLocation();
  const incorporata = SCHEDE_INCORPORATE.find(([id]) => pathname.endsWith(`/${id}`));
  // Aprendo «Situazione fiscale» senza scheda si arriva sul Piano tributi: le tre schede
  // che erano pagine a se' (Piano tributi, Tributi, Ritenute) sono la porta d'ingresso,
  // non qualcosa da cercare in fondo alla riga.
  const senzaScheda = !TABS.some(([id]) => pathname.endsWith(`/${id}`)) && !incorporata;
  if (senzaScheda && /^\/situazione-fiscale\/?$/.test(pathname)) {
    return <Navigate to={`/situazione-fiscale/piano${search || ''}`} replace />;
  }
  // Le vecchie schede «Da pagare», «Pagati con quietanza» e «Tutti i tributi F24» sono una lista sola.
  if (/\/(tributi-pagati|tutti-tributi)\/?$/.test(pathname)) {
    return <Navigate to={`/situazione-fiscale/tributi${search || ''}`} replace />;
  }
  if (!incorporata) return <ElenchiFiscali />;
  const [id, , Scheda] = incorporata;
  return (
    <div style={{ width: '100%' }}>
      <SchedeFiscali tab={id} />
      <Suspense fallback={<PageLoader />}><Scheda /></Suspense>
    </div>
  );
}

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  BadgeCheck, Database, ExternalLink, FileCheck2, FileText,
  LoaderCircle, ReceiptText, Search, ShieldCheck, X,
} from 'lucide-react';
import api from '../api';
import './DriveDocumentIndex.css';

const TABS = [
  { id: 'overview', label: 'Controlli', Icon: ShieldCheck },
  { id: 'documents', label: 'Documenti', Icon: FileText },
  { id: 'f24', label: 'F24 e tributi', Icon: ReceiptText },
  { id: 'declarations', label: 'Dichiarazioni', Icon: FileCheck2 },
];

const CHECK_LABELS = {
  document_ids_unique: 'ID documento univoci',
  document_hashes_unique: 'SHA-256 univoci',
  drive_paths_unique: 'Percorsi Drive univoci',
  all_f24_documents_exist: 'Ogni riga F24 ha il documento',
  all_f24_sha_match_document: 'SHA F24 coerenti con i documenti',
  all_f24_paths_match_document: 'Percorsi F24 coerenti con i documenti',
  f24_amounts_nonnegative: 'Importi F24 validi',
  all_declarations_link_exactly_one_document: 'Dichiarazioni collegate una sola volta',
};

const euro = value => new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(value || 0);

export default function DriveDocumentIndex() {
  const [activeTab, setActiveTab] = useState('overview');
  const [query, setQuery] = useState('');
  const [year, setYear] = useState('');
  const [taxCode, setTaxCode] = useState('');
  const [status, setStatus] = useState(null);
  const [overview, setOverview] = useState(null);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [opening, setOpening] = useState('');

  const endpoint = useMemo(() => ({
    documents: '/api/documenti/drive/index/search',
    f24: '/api/documenti/drive/index/f24',
    declarations: '/api/documenti/drive/index/declarations',
  })[activeTab], [activeTab]);

  const search = useCallback(async () => {
    if (!endpoint) return;
    setLoading(true);
    setError('');
    try {
      const response = await api.get(endpoint, {
        params: {
          q: query || undefined,
          year: year || undefined,
          tax_code: activeTab === 'f24' && taxCode ? taxCode : undefined,
          limit: 200,
        },
      });
      setResults(response.data.results || []);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Indice Drive non disponibile');
    } finally {
      setLoading(false);
    }
  }, [activeTab, endpoint, query, taxCode, year]);

  useEffect(() => {
    let active = true;
    Promise.all([
      api.get('/api/documenti/drive/index/status'),
      api.get('/api/documenti/drive/index/overview'),
    ]).then(([statusResponse, overviewResponse]) => {
      if (!active) return;
      setStatus(statusResponse.data);
      setOverview(overviewResponse.data);
      setLoading(false);
    }).catch(requestError => {
      if (active) {
        setError(requestError.response?.data?.detail || 'Indice Drive non disponibile');
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    setResults([]);
    setSelected(null);
    if (activeTab !== 'overview') search();
  }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadDocument = async documentId => {
    setOpening(documentId);
    setError('');
    try {
      const response = await api.get(`/api/documenti/drive/index/document/${encodeURIComponent(documentId)}`);
      setSelected(response.data);
      return response.data;
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Documento non disponibile su Drive');
      return null;
    } finally {
      setOpening('');
    }
  };

  const openOriginal = async documentId => {
    const document = await loadDocument(documentId);
    if (document?.drive_url) window.open(document.drive_url, '_blank', 'noopener,noreferrer');
  };

  const submit = event => {
    event.preventDefault();
    search();
  };

  const documentButton = document => (
    <div className="drive-index__row-actions">
      <button type="button" className="is-secondary" onClick={() => loadDocument(document.document_id)}>Dettagli</button>
      <button type="button" onClick={() => openOriginal(document.document_id)} disabled={opening === document.document_id}>
        {opening === document.document_id ? <LoaderCircle className="is-spinning" size={16} /> : <ExternalLink size={16} />}
        Apri originale
      </button>
    </div>
  );

  return (
    <section className="drive-index" aria-label="Indice documentale Google Drive">
      <header className="drive-index__header">
        <div>
          <h2>Archivio documentale Google Drive</h2>
          <p>Metadati e relazioni nel Gestionale; PDF, XML e ZIP originali restano su Drive.</p>
        </div>
        {status && <span className="drive-index__count"><BadgeCheck size={15} /> {status.documents} documenti verificati</span>}
      </header>

      <nav className="drive-index__tabs" aria-label="Sezioni archivio Drive">
        {TABS.map(({ id, label, Icon }) => (
          <button key={id} type="button" className={activeTab === id ? 'is-active' : ''} onClick={() => setActiveTab(id)}>
            <Icon size={17} /> {label}
          </button>
        ))}
      </nav>

      {activeTab !== 'overview' && (
        <form className="drive-index__filters" onSubmit={submit}>
          <label>
            <span>Cerca</span>
            <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Nome, protocollo, categoria o SHA-256" />
          </label>
          <label>
            <span>Anno</span>
            <input value={year} onChange={event => setYear(event.target.value)} placeholder="es. 2026" inputMode="numeric" />
          </label>
          {activeTab === 'f24' && (
            <label>
              <span>Codice tributo</span>
              <input value={taxCode} onChange={event => setTaxCode(event.target.value)} placeholder="es. 1001" />
            </label>
          )}
          <button type="submit" disabled={loading}>
            {loading ? <LoaderCircle className="is-spinning" size={17} /> : <Search size={17} />} Cerca
          </button>
        </form>
      )}

      {error && <div className="drive-index__error" role="alert">{error}</div>}

      {activeTab === 'overview' && overview && (
        <div className="drive-index__overview">
          <div className="drive-index__stats">
            <article><FileText /><strong>{overview.validation.counts.documents}</strong><span>Documenti</span></article>
            <article><ReceiptText /><strong>{overview.validation.counts.f24_documents}</strong><span>Documenti F24</span></article>
            <article><Database /><strong>{overview.validation.counts.f24_rows}</strong><span>Righe tributo</span></article>
            <article><FileCheck2 /><strong>{overview.validation.counts.declarations}</strong><span>Dichiarazioni</span></article>
          </div>
          <div className={`drive-index__boolean ${overview.validation.all_true ? 'is-ok' : 'is-error'}`}>
            <h3><ShieldCheck size={20} /> Verifica booleana: {overview.validation.all_true ? 'TUTTO VERO' : 'ANOMALIE'}</h3>
            <div>
              {Object.entries(overview.validation.checks).map(([key, value]) => (
                <span key={key} className={value ? 'is-true' : 'is-false'}>{value ? 'VERO' : 'FALSO'} · {CHECK_LABELS[key] || key}</span>
              ))}
            </div>
          </div>
          <div className="drive-index__semantics">
            <strong>Regole delle interconnessioni</strong>
            <span>Il modello F24 non equivale al pagamento bancario.</span>
            <span>La quietanza è prova documentale, distinta dal movimento bancario.</span>
            <span>Le relazioni ambigue non vengono confermate automaticamente.</span>
            <span>Nessun contenuto binario viene salvato nel database.</span>
          </div>
        </div>
      )}

      {activeTab === 'documents' && (
        <div className="drive-index__results">
          {results.map(document => (
            <article key={document.document_id} className="drive-index__row">
              <div className="drive-index__main">
                <strong title={document.filename}>{document.filename}</strong>
                <span>{document.domain} / {document.category || 'Documento'} / {document.year || 'anno non indicato'}</span>
                <small title={document.drive_path}>{document.drive_path}</small>
              </div>
              <div className="drive-index__meta"><code>{document.sha256?.slice(0, 12)}...</code>{documentButton(document)}</div>
            </article>
          ))}
        </div>
      )}

      {activeTab === 'f24' && (
        <div className="drive-index__results">
          {results.map(item => (
            <article key={item.document.document_id} className="drive-index__row">
              <div className="drive-index__main">
                <strong>{item.document.filename}</strong>
                <span>{item.payment_date || item.payment_year} / protocollo {item.protocol || 'non presente'} / {item.tax_rows} righe</span>
                <small>Tributi: {item.tax_codes.join(', ')} · Debiti {euro(item.total_debit)} · Crediti {euro(item.total_credit)}</small>
                <em>{item.evidence_state === 'QUIETANZA_DOCUMENTALE_NON_PROVA_BANCARIA' ? 'Quietanza documentale' : 'Modello F24'}: pagamento bancario non confermato</em>
              </div>
              {documentButton(item.document)}
            </article>
          ))}
        </div>
      )}

      {activeTab === 'declarations' && (
        <div className="drive-index__results">
          {results.map((item, index) => (
            <article key={`${item.archive_path}-${index}`} className="drive-index__row">
              <div className="drive-index__main">
                <strong>{item.document?.filename || item.archive_path}</strong>
                <span>{item.type} / {item.year} / protocollo {item.protocol || 'nel nome del documento'}</span>
                <small>{item.relation_state === 'CONFERMATA_NOME_UNIVOCO_E_INDICE_VERIFICATO' ? 'Relazione univoca confermata' : 'Relazione da verificare'}</small>
              </div>
              {item.document && documentButton(item.document)}
            </article>
          ))}
        </div>
      )}

      {activeTab !== 'overview' && !loading && !error && results.length === 0 && (
        <p className="drive-index__empty">Nessun elemento trovato.</p>
      )}

      {selected && (
        <aside className="drive-index__detail" role="dialog" aria-modal="true" aria-label="Dettaglio documento">
          <button type="button" className="drive-index__close" onClick={() => setSelected(null)} aria-label="Chiudi"><X /></button>
          <h3>{selected.filename}</h3>
          <p>{selected.domain} / {selected.category} / {selected.year}</p>
          <dl>
            <div><dt>SHA-256</dt><dd><code>{selected.sha256}</code></dd></div>
            <div><dt>Percorso</dt><dd>{selected.drive_path}</dd></div>
            <div><dt>Provenienza</dt><dd>{selected.source_zip || 'Archivio Drive'} · {selected.source_path || 'file originale'}</dd></div>
          </dl>
          <button type="button" className="drive-index__open" onClick={() => window.open(selected.drive_url, '_blank', 'noopener,noreferrer')}>
            <ExternalLink size={16} /> Apri originale su Drive
          </button>
          {selected.relations?.f24_rows?.length > 0 && (
            <section>
              <h4>Righe F24 ({selected.relations.f24_rows.length})</h4>
              {selected.relations.f24_rows.map((row, index) => (
                <div className="drive-index__relation" key={`${row.tax_code}-${row.tax_period}-${index}`}>
                  <strong>{row.tax_code} · {row.description}</strong>
                  <span>{row.tax_period || row.payment_date} · debito {euro(row.debit)} · credito {euro(row.credit)}</span>
                </div>
              ))}
              <p className="drive-index__notice">{selected.relations.relation_note}</p>
            </section>
          )}
          {selected.relations?.declarations?.length > 0 && (
            <section><h4>Dichiarazioni collegate</h4>{selected.relations.declarations.map((row, index) => (
              <div className="drive-index__relation" key={`${row.archive_path}-${index}`}><strong>{row.type} {row.year}</strong><span>{row.archive_path}</span></div>
            ))}</section>
          )}
        </aside>
      )}
    </section>
  );
}

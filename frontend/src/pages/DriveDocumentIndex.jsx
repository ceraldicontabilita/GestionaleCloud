import React, { useCallback, useEffect, useState } from 'react';
import {
  BadgeCheck, ExternalLink, FileText, LoaderCircle, RefreshCw, Search, X,
} from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../api';
import { VisoreOriginale } from '../components/ApriOriginale';
import { urlOriginale } from '../lib/vista';
import './DriveDocumentIndex.css';

// Una scheda sola: il protocollo vivo (`gestionale.protocollo_drive`). F24 e
// dichiarazioni stanno in Situazione fiscale, sul registro unico F24: l'indice
// Excel (`drive_document_index`) non alimenta piu' nessuna scheda di questa pagina.
const TABS = [
  { id: 'documents', label: 'Documenti', Icon: FileText },
];

export default function DriveDocumentIndex() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const folderQuery = searchParams.get('folder') || '';
  const isVerbaliFolder = /verbali(?:\s+auto)?/i.test(folderQuery);
  const [activeTab, setActiveTab] = useState('documents');
  const [query, setQuery] = useState(folderQuery);
  const [year, setYear] = useState('');
  const [showRemoved, setShowRemoved] = useState(false);
  const [onlyDuplicates, setOnlyDuplicates] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [status, setStatus] = useState(null);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [originale, setOriginale] = useState(null);

  // "Documenti" legge il protocollo vivo (gestionale.protocollo_drive):
  // una riga per file su Drive, aggiornata dal giro periodico.
  const endpoint = '/api/documenti/drive/protocollo/search';

  const search = useCallback(async () => {
    if (!endpoint || isVerbaliFolder) return;
    setLoading(true);
    setError('');
    try {
      const response = await api.get(endpoint, {
        params: {
          q: query || undefined,
          year: year || undefined,
          includi_rimossi: showRemoved ? true : undefined,
          solo_duplicati: onlyDuplicates ? true : undefined,
          limit: 200,
        },
      });
      setResults(response.data.results || []);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Indice Drive non disponibile');
    } finally {
      setLoading(false);
    }
  }, [endpoint, isVerbaliFolder, query, year, showRemoved, onlyDuplicates]);

  const refreshProtocol = async () => {
    setRefreshing(true);
    setError('');
    try {
      await api.post('/api/documenti/drive/protocollo/sync');
      const response = await api.get('/api/documenti/drive/protocollo/status');
      setStatus(response.data);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Aggiornamento del protocollo non avviato');
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (isVerbaliFolder) {
      navigate('/noleggio/verbali', { replace: true });
      return undefined;
    }
    let active = true;
    api.get('/api/documenti/drive/protocollo/status')
      .then(response => { if (active) setStatus(response.data); })
      .catch(requestError => {
        if (active) setError(requestError.response?.data?.detail || 'Protocollo Drive non disponibile');
      });
    return () => { active = false; };
  }, [isVerbaliFolder, navigate]);

  useEffect(() => {
    if (isVerbaliFolder) return;
    setResults([]);
    setSelected(null);
    search();
  }, [activeTab, isVerbaliFolder]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadDocument = async documentId => {
    setError('');
    try {
      const response = await api.get(`/api/documenti/drive/protocollo/documento/${encodeURIComponent(documentId)}`);
      setSelected(response.data);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Documento non presente nel protocollo');
    }
  };

  // L'originale lo apre l'endpoint unico (DRV-04), mai un indirizzo Drive da fuori.
  const openOriginal = document => setOriginale({
    url: urlOriginale({ driveId: document.document_id }), titolo: document.filename || 'Documento',
  });

  const submit = event => {
    event.preventDefault();
    search();
  };

  if (isVerbaliFolder) {
    return <p className="drive-index__empty">Apertura del fascicolo Verbali nella sezione Noleggi…</p>;
  }

  const documentButton = document => (
    <div className="drive-index__row-actions">
      <button type="button" className="is-secondary" onClick={() => loadDocument(document.document_id)}>Dettagli</button>
      <button type="button" onClick={() => openOriginal(document)}>
        <ExternalLink size={16} /> Apri originale
      </button>
      <button
        type="button"
        className="is-correct"
        onClick={() => navigate(`/documenti/atti?search=${encodeURIComponent(document.document_number || document.filename || '')}`)}
      >
        Correggi / associa
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
        <div className="drive-index__row-actions">
          {status && (
            <span className="drive-index__count">
              <BadgeCheck size={15} /> {status.documents} documenti nel protocollo
              {status.rimossi ? ` · ${status.rimossi} rimossi` : ''}
              {status.duplicati ? ` · ${status.duplicati} duplicati` : ''}
            </span>
          )}
          <button type="button" className="is-secondary" onClick={refreshProtocol} disabled={refreshing}>
            {refreshing ? <LoaderCircle className="is-spinning" size={16} /> : <RefreshCw size={16} />} Aggiorna indice adesso
          </button>
        </div>
      </header>

      <nav className="drive-index__tabs" aria-label="Sezioni archivio Drive">
        {TABS.map(({ id, label, Icon }) => (
          <button key={id} type="button" className={activeTab === id ? 'is-active' : ''} onClick={() => setActiveTab(id)}>
            <Icon size={17} /> {label}
          </button>
        ))}
      </nav>

      <form className="drive-index__filters" onSubmit={submit}>
        <label>
          <span>Cerca</span>
          <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Nome, protocollo, categoria o SHA-256" />
        </label>
        <label>
          <span>Anno</span>
          <input value={year} onChange={event => setYear(event.target.value)} placeholder="es. 2026" inputMode="numeric" />
        </label>
        {activeTab === 'documents' && (
          <>
            <label>
              <span>Rimossi da Drive</span>
              <input type="checkbox" checked={showRemoved} onChange={event => setShowRemoved(event.target.checked)} />
            </label>
            <label>
              <span>Solo duplicati</span>
              <input type="checkbox" checked={onlyDuplicates} onChange={event => setOnlyDuplicates(event.target.checked)} />
            </label>
          </>
        )}
        <button type="submit" disabled={loading}>
          {loading ? <LoaderCircle className="is-spinning" size={17} /> : <Search size={17} />} Cerca
        </button>
      </form>

      {error && <div className="drive-index__error" role="alert">{error}</div>}

      {activeTab === 'documents' && (
        <div className="drive-index__results drive-index__table-wrap">
          {folderQuery && <div className="drive-index__folder-filter">Contenuto cartella: <strong>{folderQuery}</strong> · verde significa parser attivo, blu solo catalogazione.</div>}
          <table className="drive-index__table">
            <thead><tr><th>Persona / soggetto</th><th>Anno</th><th>Atto</th><th>Informazioni utili</th><th>Stato</th><th>Azioni</th></tr></thead>
            <tbody>
              {results.map(document => (
                <tr key={document.document_id} className={document.is_source_package ? 'is-package' : ''}>
                  <td><strong>{document.subject || 'Da identificare'}</strong><small>{document.domain || 'Archivio Drive'}</small></td>
                  <td>{document.year || '—'}</td>
                  <td><strong>{document.display_title || document.document_type_label || 'Documento'}</strong><small title={document.filename}>{document.filename}</small></td>
                  <td><span>{document.summary}</span><small title={document.drive_path}>{document.drive_path}</small></td>
                  <td><span className={`drive-index__status ${document.is_source_package ? 'is-package' : ''}`}>{document.is_source_package ? 'PACCHETTO SORGENTE' : (document.status || 'CATALOGATO')}</span></td>
                  <td>{documentButton(document)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && !error && results.length === 0 && (
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
          <button type="button" className="drive-index__open" onClick={() => openOriginal({ document_id: selected.document_id, filename: selected.filename })}>
            <ExternalLink size={16} /> Apri originale
          </button>
        </aside>
      )}
      {originale && <VisoreOriginale url={originale.url} titolo={originale.titolo} onClose={() => setOriginale(null)} />}
    </section>
  );
}

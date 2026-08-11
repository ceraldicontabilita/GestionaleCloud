import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2,
  ChevronDown,
  FileCheck2,
  Loader2,
  Pencil,
  RefreshCw,
  Search,
  ShieldCheck,
  X,
} from 'lucide-react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';

const PAGE_SIZE = 200;

const euroCents = (cents) => new Intl.NumberFormat('it-IT', {
  style: 'currency', currency: 'EUR',
}).format((Number(cents) || 0) / 100);

const formatDate = (value) => {
  if (!value) return '—';
  const [year, month, day] = String(value).slice(0, 10).split('-');
  return day && month && year ? `${day}-${month}-${year}` : String(value);
};

function DecisionModal({ row, categories, onClose, onSaved }) {
  const previous = row.decision || {};
  const [category, setCategory] = useState(previous.category || '');
  const [targetId, setTargetId] = useState(previous.target_id || '');
  const [note, setNote] = useState(previous.note || '');
  const [search, setSearch] = useState('');
  const [candidates, setCandidates] = useState([]);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const selectedCategory = categories.find(item => item.id === category);
  const requiresTarget = Boolean(selectedCategory?.requires_target);

  const loadCandidates = useCallback(async (selected, query = '') => {
    if (!selected?.requires_target) {
      setCandidates([]);
      return;
    }
    setLoadingCandidates(true);
    setError('');
    try {
      const params = new URLSearchParams({ category: selected.id, limit: '50' });
      if (query.trim()) params.set('search', query.trim());
      const response = await api.get(
        `/api/prima-nota/indice-operazioni/${encodeURIComponent(row.id)}/candidati?${params}`,
      );
      setCandidates(response.data?.candidates || []);
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || requestError?.message || 'Impossibile leggere i dati collegabili');
    } finally {
      setLoadingCandidates(false);
    }
  }, [row.id]);

  useEffect(() => {
    if (!selectedCategory) return;
    setTargetId(previous.category === selectedCategory.id ? previous.target_id || '' : '');
    loadCandidates(selectedCategory);
  }, [selectedCategory?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    if (!category) {
      setError('Scegli prima la natura dell’operazione.');
      return;
    }
    if (requiresTarget && !targetId) {
      setError('Scegli il dato esatto da collegare.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await api.put(`/api/prima-nota/indice-operazioni/${encodeURIComponent(row.id)}`, {
        category,
        target_id: targetId || null,
        note,
        expected_version: Number(previous.version || 0),
      });
      await onSaved();
      onClose();
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || requestError?.message || 'Salvataggio non riuscito');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="operation-index-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="operation-index-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Classifica operazione bancaria"
        onMouseDown={event => event.stopPropagation()}
      >
        <header className="operation-index-modal-header">
          <div>
            <h2>Classifica e collega</h2>
            <p>{formatDate(row.date)} · {euroCents(row.amount_cents)}</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Chiudi"><X size={20} /></button>
        </header>

        <div className="operation-source-box">
          <strong>Movimento originale</strong>
          <span>{row.description || 'Descrizione non disponibile'}</span>
        </div>

        <div className="operation-step">
          <div className="operation-step-title"><span>1</span> Che cos’è?</div>
          <div className="category-grid">
            {categories.map(item => (
              <button
                type="button"
                key={item.id}
                className={`category-choice ${category === item.id ? 'selected' : ''}`}
                onClick={() => setCategory(item.id)}
              >
                <strong>{item.label}</strong>
                <small>{item.help}</small>
              </button>
            ))}
          </div>
        </div>

        {selectedCategory && (
          <div className="operation-step">
            <div className="operation-step-title"><span>2</span> {requiresTarget ? 'A quale dato preciso va collegata?' : 'Aggiungi una nota, se serve'}</div>
            {requiresTarget && (
              <>
                <div className="candidate-search">
                  <Search size={16} />
                  <input
                    value={search}
                    onChange={event => setSearch(event.target.value)}
                    onKeyDown={event => { if (event.key === 'Enter') loadCandidates(selectedCategory, search); }}
                    placeholder="Cerca nome, numero fattura, targa, driver, periodo…"
                  />
                  <button type="button" onClick={() => loadCandidates(selectedCategory, search)}>Cerca</button>
                </div>
                <div className="candidate-list" data-testid="manual-index-candidates">
                  {loadingCandidates && <div className="candidate-empty"><Loader2 size={18} className="animate-spin" /> Caricamento…</div>}
                  {!loadingCandidates && candidates.length === 0 && (
                    <div className="candidate-empty">Nessun dato mostrato. Prova una ricerca più precisa.</div>
                  )}
                  {!loadingCandidates && candidates.map(candidate => (
                    <label key={candidate.id} className={`candidate-row ${targetId === candidate.id ? 'selected' : ''}`}>
                      <input
                        type="radio"
                        name="operation-target"
                        checked={targetId === candidate.id}
                        onChange={() => setTargetId(candidate.id)}
                      />
                      <span className="candidate-main">
                        <strong>{candidate.label}</strong>
                        <small>{[formatDate(candidate.date), candidate.amount_cents ? euroCents(candidate.amount_cents) : ''].filter(Boolean).join(' · ')}</small>
                      </span>
                    </label>
                  ))}
                </div>
              </>
            )}
            <label className="manual-note">
              Nota facoltativa
              <textarea value={note} maxLength={500} onChange={event => setNote(event.target.value)} placeholder="Scrivi qui una precisazione utile…" />
            </label>
          </div>
        )}

        {error && <div className="operation-index-error">{String(error)}</div>}

        <footer className="operation-index-modal-footer">
          <div><ShieldCheck size={16} /> Nessuna scrittura o stato “pagato” viene creato automaticamente.</div>
          <button type="button" className="secondary-button" onClick={onClose}>Annulla</button>
          <button type="button" className="primary-button" onClick={save} disabled={saving || !category || (requiresTarget && !targetId)}>
            {saving ? <Loader2 size={16} className="animate-spin" /> : <FileCheck2 size={16} />}
            Conferma scelta
          </button>
        </footer>
      </section>
    </div>
  );
}

export default function VerificaMovimentiBanca() {
  const { anno } = useAnnoGlobale();
  const [data, setData] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [selectedRow, setSelectedRow] = useState(null);

  const load = useCallback(async ({ append = false, offset = 0 } = {}) => {
    append ? setLoadingMore(true) : setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ anno: String(anno), limit: String(PAGE_SIZE), offset: String(offset) });
      if (typeFilter !== 'all') params.set('tipo', typeFilter);
      if (search.trim()) params.set('search', search.trim());
      const response = await api.get(`/api/prima-nota/indice-operazioni?${params}`);
      setData(response.data);
      setRows(current => append ? [...current, ...(response.data?.rows || [])] : response.data?.rows || []);
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || requestError?.message || 'Errore nel caricamento delle operazioni');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [anno, search, typeFilter]);

  useEffect(() => { load(); }, [anno, typeFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const visibleRows = useMemo(() => rows.filter(row => (
    statusFilter === 'all' || row.index_status === statusFilter
  )), [rows, statusFilter]);

  const categories = data?.categories || [];
  const canLoadMore = rows.length < Number(data?.total_rows || 0);

  return (
    <div className="operation-index-page" data-testid="manual-operation-index">
      <style>{`
        .operation-index-page{padding:0;color:#12233d}.operation-index-hero{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;padding:18px;border:1px solid #dbe5ef;border-left:5px solid #173a63;border-radius:12px;background:#fff;margin-bottom:14px}.operation-index-hero h1{font-size:20px;margin:0 0 5px}.operation-index-hero p{font-size:13px;color:#52657b;margin:0;max-width:780px;line-height:1.5}.manual-only-badge{display:flex;align-items:center;gap:7px;background:#eaf7ef;color:#166534;border:1px solid #b7e4c7;padding:8px 11px;border-radius:999px;font-size:12px;font-weight:800;white-space:nowrap}.operation-filters{display:grid;grid-template-columns:minmax(220px,1fr) auto auto auto;gap:8px;padding:10px;background:#fff;border:1px solid #dbe5ef;border-radius:10px;margin-bottom:12px}.operation-search{display:flex;align-items:center;gap:8px;border:1px solid #cbd7e4;border-radius:8px;padding:0 10px}.operation-search input{width:100%;border:0;outline:0;padding:9px 0;font-size:13px}.compact-select,.filter-button{min-height:38px;border:1px solid #cbd7e4;border-radius:8px;background:#fff;padding:0 11px;color:#253b55}.filter-button{display:inline-flex;align-items:center;gap:6px;cursor:pointer;font-weight:700}.operation-summary{display:flex;gap:8px;align-items:center;justify-content:space-between;font-size:12px;color:#64748b;margin:8px 2px}.operation-table-shell{overflow:auto;background:#fff;border:1px solid #dbe5ef;border-radius:12px}.operation-table{width:100%;border-collapse:collapse;font-size:13px;min-width:900px}.operation-table th{padding:10px 12px;text-align:left;background:#f5f8fb;color:#52657b;font-size:11px;text-transform:uppercase;letter-spacing:.04em}.operation-table td{padding:10px 12px;border-top:1px solid #edf1f5;vertical-align:middle}.operation-description{max-width:580px;line-height:1.35}.type-pill,.decision-pill{display:inline-flex;align-items:center;border-radius:999px;padding:3px 8px;font-size:11px;font-weight:800}.type-pill.in{background:#dcfce7;color:#166534}.type-pill.out{background:#fee2e2;color:#991b1b}.decision-pill.linked{background:#dcfce7;color:#166534}.decision-pill.classified{background:#e0f2fe;color:#075985}.decision-pill.empty{background:#f1f5f9;color:#64748b}.row-action{display:inline-flex;align-items:center;gap:6px;border:1px solid #173a63;background:#fff;color:#173a63;border-radius:7px;padding:6px 9px;font-weight:800;cursor:pointer}.load-more{display:flex;justify-content:center;margin:14px}.operation-index-empty{padding:48px;text-align:center;background:#fff;border:1px solid #dbe5ef;border-radius:12px;color:#52657b}.operation-index-error{background:#fff1f2;color:#9f1239;border:1px solid #fecdd3;border-radius:8px;padding:10px 12px;font-size:13px;margin:10px 0}.operation-index-modal-backdrop{position:fixed;inset:0;background:rgba(15,23,42,.58);z-index:1200;display:flex;align-items:center;justify-content:center;padding:20px}.operation-index-modal{width:min(900px,100%);max-height:92vh;overflow:auto;background:#fff;border-radius:14px;box-shadow:0 24px 70px rgba(15,23,42,.35)}.operation-index-modal-header{display:flex;justify-content:space-between;align-items:flex-start;padding:18px 20px;border-bottom:1px solid #e2e8f0;position:sticky;top:0;background:#fff;z-index:2}.operation-index-modal-header h2{margin:0;font-size:20px}.operation-index-modal-header p{margin:4px 0 0;color:#52657b}.icon-button{border:0;background:#f1f5f9;border-radius:8px;padding:7px;cursor:pointer}.operation-source-box{margin:16px 20px 0;padding:12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:9px;display:grid;gap:4px;font-size:13px}.operation-step{padding:18px 20px 0}.operation-step-title{display:flex;align-items:center;gap:8px;font-weight:900;margin-bottom:10px}.operation-step-title>span{display:grid;place-items:center;width:23px;height:23px;border-radius:50%;background:#173a63;color:#fff;font-size:12px}.category-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.category-choice{text-align:left;border:1px solid #d6e0ea;background:#fff;border-radius:9px;padding:10px;cursor:pointer;display:grid;gap:3px}.category-choice small{color:#64748b;line-height:1.3}.category-choice.selected{border-color:#2563eb;background:#eff6ff;box-shadow:0 0 0 1px #2563eb}.candidate-search{display:flex;align-items:center;gap:8px;border:1px solid #cbd7e4;border-radius:8px;padding-left:10px}.candidate-search input{flex:1;border:0;outline:0;padding:10px 0}.candidate-search button{align-self:stretch;border:0;background:#173a63;color:#fff;padding:0 15px;font-weight:800;border-radius:0 7px 7px 0}.candidate-list{border:1px solid #e2e8f0;border-radius:9px;margin-top:8px;max-height:260px;overflow:auto}.candidate-row{display:flex;gap:9px;align-items:flex-start;padding:10px;border-bottom:1px solid #edf1f5;cursor:pointer}.candidate-row:last-child{border-bottom:0}.candidate-row.selected{background:#eff6ff}.candidate-main{display:grid;gap:2px}.candidate-main small{color:#64748b}.candidate-empty{padding:22px;text-align:center;color:#64748b;display:flex;justify-content:center;gap:7px}.manual-note{display:grid;gap:5px;font-size:12px;font-weight:800;margin-top:10px}.manual-note textarea{min-height:70px;resize:vertical;border:1px solid #cbd7e4;border-radius:8px;padding:9px;font:inherit;font-weight:400}.operation-index-modal-footer{display:flex;align-items:center;gap:8px;padding:16px 20px;margin-top:18px;border-top:1px solid #e2e8f0;position:sticky;bottom:0;background:#fff}.operation-index-modal-footer>div{display:flex;align-items:center;gap:6px;color:#166534;font-size:11px;margin-right:auto}.primary-button,.secondary-button{display:inline-flex;align-items:center;justify-content:center;gap:6px;border-radius:8px;padding:9px 13px;font-weight:800;cursor:pointer}.primary-button{background:#173a63;color:#fff;border:1px solid #173a63}.primary-button:disabled{opacity:.45;cursor:not-allowed}.secondary-button{background:#fff;color:#334155;border:1px solid #cbd5e1}
        @media(max-width:760px){.operation-index-hero{padding:13px;display:grid}.manual-only-badge{width:max-content}.operation-filters{grid-template-columns:1fr 1fr}.operation-search{grid-column:1/-1}.operation-table-shell{border:0;background:transparent;overflow:visible}.operation-table{display:block;min-width:0}.operation-table thead{display:none}.operation-table tbody{display:grid;gap:8px}.operation-table tr{display:grid;grid-template-columns:1fr auto;gap:7px;background:#fff;border:1px solid #dbe5ef;border-radius:10px;padding:11px}.operation-table td{border:0;padding:0}.operation-table td:nth-child(1),.operation-table td:nth-child(2){display:inline-block}.operation-table td:nth-child(3){grid-column:1/-1}.operation-table td:nth-child(4){grid-column:2;grid-row:1;text-align:right!important}.operation-table td:nth-child(5),.operation-table td:nth-child(6){grid-column:1/-1}.row-action{width:100%;justify-content:center}.category-grid{grid-template-columns:1fr 1fr}.operation-index-modal-backdrop{padding:0;align-items:flex-end}.operation-index-modal{border-radius:14px 14px 0 0;max-height:96vh}.operation-index-modal-footer{flex-wrap:wrap}.operation-index-modal-footer>div{width:100%}.primary-button,.secondary-button{flex:1}}
      `}</style>

      <section className="operation-index-hero">
        <div>
          <h1>Indice operazioni bancarie</h1>
          <p>Tutte le righe dell’estratto conto in un solo posto. Sei tu a scegliere la natura e il dato esatto da collegare; ogni scelta è modificabile e conserva la versione precedente.</p>
        </div>
        <div className="manual-only-badge"><ShieldCheck size={16} /> Solo decisioni manuali</div>
      </section>

      <div className="operation-filters">
        <div className="operation-search">
          <Search size={16} />
          <input value={search} onChange={event => setSearch(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') load(); }} placeholder="Cerca nella causale…" />
        </div>
        <select className="compact-select" value={typeFilter} onChange={event => setTypeFilter(event.target.value)} aria-label="Tipo movimento">
          <option value="all">Entrate e uscite</option><option value="entrata">Solo entrate</option><option value="uscita">Solo uscite</option>
        </select>
        <select className="compact-select" value={statusFilter} onChange={event => setStatusFilter(event.target.value)} aria-label="Stato indice">
          <option value="all">Tutti gli stati</option><option value="da_classificare">Da classificare</option><option value="classificato">Classificati</option><option value="collegato_indice">Collegati</option>
        </select>
        <button type="button" className="filter-button" onClick={() => load()} disabled={loading}>{loading ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />} Aggiorna</button>
      </div>

      <div className="operation-summary">
        <span><strong>{rows.length}</strong> di <strong>{data?.total_rows || 0}</strong> operazioni caricate · anno {anno}</span>
        <span>{visibleRows.length} visibili con i filtri</span>
      </div>

      {error && <div className="operation-index-error">{String(error)}</div>}
      {loading && rows.length === 0 && <div className="operation-index-empty"><Loader2 className="animate-spin" /> Caricamento operazioni…</div>}
      {!loading && visibleRows.length === 0 && <div className="operation-index-empty"><CheckCircle2 size={28} /> Nessuna operazione per questi filtri.</div>}

      {visibleRows.length > 0 && (
        <div className="operation-table-shell">
          <table className="operation-table">
            <thead><tr><th>Data</th><th>Tipo</th><th>Operazione bancaria</th><th style={{ textAlign: 'right' }}>Importo</th><th>Indice scelto</th><th>Azione</th></tr></thead>
            <tbody>
              {visibleRows.map(row => {
                const decision = row.decision;
                return (
                  <tr key={row.id}>
                    <td>{formatDate(row.date)}</td>
                    <td><span className={`type-pill ${row.type === 'entrata' ? 'in' : 'out'}`}>{row.type === 'entrata' ? 'Entrata' : 'Uscita'}</span></td>
                    <td className="operation-description">{row.description || '—'}</td>
                    <td style={{ textAlign: 'right', fontWeight: 900, color: row.type === 'entrata' ? '#15803d' : '#dc2626' }}>{euroCents(row.amount_cents)}</td>
                    <td>
                      {!decision && <span className="decision-pill empty">Da classificare</span>}
                      {decision && <span className={`decision-pill ${decision.target_id ? 'linked' : 'classified'}`}>{decision.category_label}</span>}
                      {decision?.target_label && <div style={{ fontSize: 11, color: '#52657b', marginTop: 4 }}>{decision.target_label}</div>}
                    </td>
                    <td><button type="button" className="row-action" onClick={() => setSelectedRow(row)}>{decision ? <Pencil size={14} /> : <ChevronDown size={14} />}{decision ? 'Modifica' : 'Classifica'}</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {canLoadMore && <div className="load-more"><button type="button" className="filter-button" onClick={() => load({ append: true, offset: rows.length })} disabled={loadingMore}>{loadingMore ? <Loader2 size={15} className="animate-spin" /> : null} Carica altre operazioni</button></div>}

      {selectedRow && <DecisionModal row={selectedRow} categories={categories} onClose={() => setSelectedRow(null)} onSaved={() => load()} />}
    </div>
  );
}

/**
 * CicloPassivoAdmin.jsx
 * Pagina Import Fatture nel gestionale Ceraldi
 *
 * USA gli endpoint REALI del gestionale:
 *   Upload XML → POST /api/ciclo-passivo/import-integrato (singolo)
 *               POST /api/ciclo-passivo/import-integrato-batch (multiplo)
 *   Lista fatture → GET /api/fatture-ricevute/archivio
 *   Scarica PEC  → POST /api/email-download/processa-fatture-email
 *   Status PEC   → GET  /api/email-download/processa-fatture-email/status
 */
import React, { useState, useEffect, useRef } from 'react';
import api from '../api';
import { COLORS, STYLES, button, badge, formatEuro, formatDateIT } from '../lib/utils';
import { PageLayout, PageSection, PageEmpty, PageLoading } from '../components/PageLayout';

export default function CicloPassivoAdmin() {
  const [activeTab, setActiveTab] = useState('upload');

  const tabs = [
    { id: 'upload',  label: '📤 Upload XML' },
    { id: 'pec',     label: '📧 Scarica PEC' },
    { id: 'fatture', label: '📋 Fatture Importate' },
  ];

  return (
    <PageLayout>
      {/* Header */}
      <div style={STYLES.header}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#fff' }}>
            📥 Ciclo Passivo — Import Fatture
          </h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'rgba(255,255,255,0.75)' }}>
            Import XML + Aruba PEC → Magazzino + Prima Nota + Scadenziario automatici
          </p>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{
        display: 'flex', gap: 8, padding: '12px 0 0',
        borderBottom: `2px solid ${COLORS.grayLight}`, marginBottom: 16
      }}>
        {tabs.map(t => (
          <button
            key={t.id}
            data-testid={`tab-${t.id}`}
            onClick={() => setActiveTab(t.id)}
            style={{
              padding: '8px 18px', border: 'none', cursor: 'pointer',
              fontSize: 14, fontWeight: 600, borderRadius: '6px 6px 0 0',
              background: activeTab === t.id ? COLORS.primary : 'transparent',
              color: activeTab === t.id ? '#fff' : COLORS.gray,
              borderBottom: activeTab === t.id ? `2px solid ${COLORS.primary}` : 'none',
            }}
          >{t.label}</button>
        ))}
      </div>

      {activeTab === 'upload'  && <TabUploadXML />}
      {activeTab === 'pec'     && <TabPEC />}
      {activeTab === 'fatture' && <TabFatture />}
    </PageLayout>
  );
}

/* ═══════════════════════════════════════════════════════
   TAB 1 — Upload XML (singolo o multiplo)
═══════════════════════════════════════════════════════ */
function TabUploadXML() {
  const [files, setFiles]         = useState([]);
  const [loading, setLoading]     = useState(false);
  const [risultati, setRisultati] = useState(null);
  const inputRef = useRef(null);

  const handleFiles = (e) => setFiles(Array.from(e.target.files || []));

  const handleUpload = async () => {
    if (!files.length) { alert('Seleziona almeno un file XML'); return; }
    setLoading(true);
    setRisultati(null);
    try {
      const results = [];
      if (files.length === 1) {
        const fd = new FormData();
        fd.append('file', files[0]);
        const res = await api.post('/api/ciclo-passivo/import-integrato', fd, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
        results.push({ file: files[0].name, ...res.data });
      } else {
        const fd = new FormData();
        files.forEach(f => fd.append('files', f));
        const res = await api.post('/api/ciclo-passivo/import-integrato-batch', fd, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
        (res.data.risultati || []).forEach(r => results.push(r));
      }
      setRisultati(results);
      setFiles([]);
      if (inputRef.current) inputRef.current.value = '';
      alert(`✅ Import completato: ${results.length} fattura/e processata/e`);
    } catch (e) {
      alert('❌ Errore: ' + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageSection title="Carica file XML fatture elettroniche" icon="📤">
      <p style={{ fontSize: 13, color: COLORS.gray, marginBottom: 16 }}>
        Per ogni XML il sistema esegue in automatico:{' '}
        <strong>parse → fornitore → magazzino → prima nota → scadenziario → riconciliazione</strong>.<br />
        Se il fornitore ha <code>esclude_magazzino=true</code> il carico magazzino viene saltato.
      </p>

      {/* Drop zone */}
      <div
        data-testid="dropzone-xml"
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${COLORS.grayLight}`, borderRadius: 12,
          padding: 40, textAlign: 'center', cursor: 'pointer',
          background: COLORS.grayBg, marginBottom: 16,
        }}
      >
        <div style={{ fontSize: 40, marginBottom: 8 }}>📂</div>
        <p style={{ margin: 0, fontWeight: 600, color: COLORS.gray }}>
          Clicca per selezionare file XML
        </p>
        <p style={{ margin: '4px 0 0', fontSize: 12, color: COLORS.gray }}>
          Puoi selezionare più file contemporaneamente
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".xml,.zip"
          multiple
          style={{ display: 'none' }}
          onChange={handleFiles}
        />
      </div>

      {/* File selezionati */}
      {files.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
          {files.map((f, i) => (
            <span key={i} style={{
              padding: '4px 12px', background: '#dbeafe', color: '#1d4ed8',
              borderRadius: 20, fontSize: 13, fontWeight: 600
            }}>{f.name}</span>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8 }}>
        <button
          data-testid="btn-importa-xml"
          style={button('primary', loading || !files.length)}
          onClick={handleUpload}
          disabled={loading || !files.length}
        >
          {loading ? '⏳ Importazione...' : `📤 Importa ${files.length ? files.length + ' file' : ''}`}
        </button>
        {files.length > 0 && (
          <button style={button('secondary')} onClick={() => {
            setFiles([]);
            if (inputRef.current) inputRef.current.value = '';
          }}>
            ✕ Cancella
          </button>
        )}
      </div>

      {/* Risultati */}
      {risultati && (
        <div style={{ marginTop: 20 }}>
          <h4 style={{ fontSize: 15, fontWeight: 700, color: COLORS.primary, marginBottom: 12 }}>
            ✅ Risultati Import
          </h4>
          {risultati.map((r, i) => (
            <div key={i} style={{ ...STYLES.card, marginBottom: 10, padding: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <strong style={{ fontSize: 14 }}>{r.file || r.numero_documento || `Fattura ${i + 1}`}</strong>
                <span style={badge(r.success !== false ? 'success' : 'danger')}>
                  {r.success !== false ? '✓ OK' : '✗ Errore'}
                </span>
              </div>
              {r.fornitore && <p style={{ margin: '2px 0', fontSize: 13, color: COLORS.gray }}>Fornitore: <strong>{r.fornitore}</strong></p>}
              {r.importo_totale && <p style={{ margin: '2px 0', fontSize: 13, color: COLORS.gray }}>Importo: <strong>{formatEuro(r.importo_totale)}</strong></p>}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 6 }}>
                {r.magazzino?.movimenti_creati > 0 && (
                  <span style={badge('success')}>📦 {r.magazzino.movimenti_creati} movimenti magazzino</span>
                )}
                {r.magazzino?.lotti_creati > 0 && (
                  <span style={badge('info')}>🏷️ {r.magazzino.lotti_creati} lotti creati</span>
                )}
                {r.magazzino?.skipped && (
                  <span style={badge('warning')}>⏭️ Magazzino saltato (fornitore escluso)</span>
                )}
                {r.prima_nota?.scrittura_id && (
                  <span style={badge('success')}>📒 Prima Nota ok</span>
                )}
                {r.scadenziario?.scadenza_id && (
                  <span style={badge('info')}>📅 Scadenza creata</span>
                )}
              </div>
              {r.error && <p style={{ color: COLORS.danger, fontSize: 12, marginTop: 6 }}>❌ {r.error}</p>}
            </div>
          ))}
        </div>
      )}
    </PageSection>
  );
}

/* ═══════════════════════════════════════════════════════
   TAB 2 — Scarica da Aruba PEC
═══════════════════════════════════════════════════════ */
function TabPEC() {
  const [loading, setLoading]     = useState(false);
  const [status, setStatus]       = useState(null);
  const [risultato, setRisultato] = useState(null);
  const [giorni, setGiorni]       = useState(7);

  const checkStatus = async () => {
    try {
      const res = await api.get('/api/email-download/processa-fatture-email/status');
      setStatus(res.data);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { checkStatus(); }, []);

  const avviaDownload = async () => {
    setLoading(true);
    setRisultato(null);
    try {
      const res = await api.post(`/api/email-download/processa-fatture-email?giorni=${giorni}`);
      setRisultato(res.data);
      await checkStatus();
      alert('✅ Download PEC completato');
    } catch (e) {
      alert('❌ Errore: ' + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  };

  const avviaFullDownload = async () => {
    setLoading(true);
    try {
      await api.post('/api/email-download/start-full-download?process_aruba=true');
      alert('✅ Download completo avviato in background');
      await checkStatus();
    } catch (e) {
      alert('❌ Errore: ' + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageSection title="Scarica fatture da Aruba PEC" icon="📧">
      <p style={{ fontSize: 13, color: COLORS.gray, marginBottom: 16 }}>
        Connette a <strong>fatturazioneceraldi@pec.it</strong>, scarica le email di notifica fattura da Aruba
        ed elabora automaticamente gli XML allegati.
      </p>

      {status && (
        <div style={{ ...STYLES.card, marginBottom: 16, padding: 12, background: '#f0fdf4', border: '1px solid #86efac' }}>
          <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: '#15803d' }}>
            Stato: {status.running ? '⏳ In esecuzione...' : '✅ Pronto'}
          </p>
          {status.completed_at && (
            <p style={{ margin: '4px 0 0', fontSize: 12, color: COLORS.gray }}>
              Ultima esecuzione: {formatDateIT(status.completed_at)}
            </p>
          )}
        </div>
      )}

      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <label style={{ fontSize: 13, fontWeight: 600, color: COLORS.gray }}>Ultimi</label>
        <select
          value={giorni}
          onChange={e => setGiorni(Number(e.target.value))}
          style={{ ...STYLES.select, width: 100 }}
        >
          {[1, 3, 7, 14, 30].map(g => (
            <option key={g} value={g}>{g} giorni</option>
          ))}
        </select>
        <button
          data-testid="btn-scarica-pec"
          style={button('primary', loading)}
          onClick={avviaDownload}
          disabled={loading}
        >
          {loading ? '⏳ Scaricamento...' : '📧 Scarica da PEC'}
        </button>
        <button
          style={button('secondary', loading)}
          onClick={avviaFullDownload}
          disabled={loading}
        >
          📥 Download completo
        </button>
        <button style={button('info')} onClick={checkStatus}>
          ↻ Aggiorna stato
        </button>
      </div>

      {risultato && (
        <div style={{ ...STYLES.card, padding: 14 }}>
          <h4 style={{ margin: '0 0 10px', fontSize: 14, fontWeight: 700 }}>Risultato</h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
            {[
              { label: 'Email processate', val: risultato.emails_processed || risultato.totale || 0, color: COLORS.primary },
              { label: 'Fatture trovate',  val: risultato.fatture_trovate || 0,   color: COLORS.success },
              { label: 'Già presenti',     val: risultato.gia_presenti || 0,      color: COLORS.warning },
              { label: 'Errori',           val: risultato.errori || 0,            color: COLORS.danger },
            ].map(({ label, val, color }) => (
              <div key={label} style={{ textAlign: 'center', padding: 12, background: COLORS.grayBg, borderRadius: 8 }}>
                <p style={{ margin: 0, fontSize: 22, fontWeight: 800, color }}>{val}</p>
                <p style={{ margin: '2px 0 0', fontSize: 11, color: COLORS.gray }}>{label}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </PageSection>
  );
}

/* ═══════════════════════════════════════════════════════
   TAB 3 — Fatture importate
   Endpoint: GET /api/fatture-ricevute/archivio
═══════════════════════════════════════════════════════ */
function TabFatture() {
  const [fatture, setFatture]   = useState([]);
  const [loading, setLoading]   = useState(true);
  const [search, setSearch]     = useState('');
  const [page, setPage]         = useState(0);
  const PER_PAGE = 20;

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/fatture-ricevute/archivio?limit=200');
      setFatture(
        Array.isArray(res.data) ? res.data :
        Array.isArray(res.data?.fatture) ? res.data.fatture : []
      );
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const filtrate = fatture.filter(f => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (f.fornitore_ragione_sociale || f.fornitore || '').toLowerCase().includes(q) ||
      (f.numero_documento || '').toLowerCase().includes(q)
    );
  });

  const paginate = filtrate.slice(page * PER_PAGE, (page + 1) * PER_PAGE);
  const totalPages = Math.ceil(filtrate.length / PER_PAGE);

  if (loading) return <PageLoading />;

  return (
    <PageSection title={`Fatture importate (${filtrate.length})`} icon="📋">
      <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
        <input
          data-testid="input-cerca-fatture"
          style={{ ...STYLES.input, maxWidth: 300 }}
          placeholder="Cerca fornitore o numero..."
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(0); }}
        />
        <button style={button('secondary')} onClick={load}>↻ Aggiorna</button>
      </div>

      {paginate.length === 0 ? (
        <PageEmpty icon="📭" message="Nessuna fattura trovata" />
      ) : (
        <>
          <table style={STYLES.table}>
            <thead>
              <tr>
                <th style={STYLES.th}>Data</th>
                <th style={STYLES.th}>Fornitore</th>
                <th style={STYLES.th}>N° Fattura</th>
                <th style={STYLES.th}>Importo</th>
                <th style={STYLES.th}>Stato</th>
                <th style={STYLES.th}>Magazzino</th>
              </tr>
            </thead>
            <tbody>
              {paginate.map((f, i) => (
                <tr key={f.id || i} style={{ background: i % 2 === 0 ? '#fff' : COLORS.grayBg }}>
                  <td style={STYLES.td}>{formatDateIT(f.data_documento || f.data_fattura || '')}</td>
                  <td style={STYLES.td}>
                    <strong>{f.fornitore_ragione_sociale || f.fornitore || '—'}</strong>
                  </td>
                  <td style={STYLES.td}>{f.numero_documento || f.numero_fattura || '—'}</td>
                  <td style={STYLES.td}>
                    <strong style={{ color: COLORS.primary }}>{formatEuro(f.importo_totale || f.importo || 0)}</strong>
                  </td>
                  <td style={STYLES.td}>
                    <span style={badge(
                      f.stato === 'importata' || f.stato === 'riconciliata' ? 'success' : 'warning'
                    )}>
                      {f.stato || 'importata'}
                    </span>
                  </td>
                  <td style={STYLES.td}>
                    {f.integrazione_completata
                      ? <span style={badge('success')}>✓ ok</span>
                      : <span style={badge('warning')}>in attesa</span>
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {totalPages > 1 && (
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 14 }}>
              <button
                style={button('secondary', page === 0)}
                disabled={page === 0}
                onClick={() => setPage(p => p - 1)}
              >← Prec</button>
              <span style={{ padding: '8px 12px', fontSize: 13, color: COLORS.gray }}>
                Pag {page + 1} / {totalPages}
              </span>
              <button
                style={button('secondary', page >= totalPages - 1)}
                disabled={page >= totalPages - 1}
                onClick={() => setPage(p => p + 1)}
              >Succ →</button>
            </div>
          )}
        </>
      )}
    </PageSection>
  );
}

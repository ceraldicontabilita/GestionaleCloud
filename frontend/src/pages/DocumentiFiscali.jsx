import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Upload, FileText, Download, Trash2, RefreshCw } from 'lucide-react';
import api from '../api';
import { COLORS } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { Button } from '../components/ds';
import { useConfirm } from '../components/ui/ConfirmDialog';

/**
 * Documenti fiscali caricati a mano: dichiarazione IVA, cartelle esattoriali,
 * avvisi bonari. Carichi un PDF → ha un ID, è memorizzato e sempre
 * scaricabile. Backend: /api/documenti-fiscali (upload/lista) + download
 * generico /api/documenti/documento/{id}/download.
 */
const CATEGORIE = [
  { id: 'dichiarazione_iva', label: 'Dichiarazioni IVA', icon: '📊' },
  { id: 'cartella_esattoriale', label: 'Cartelle esattoriali', icon: '⚠️' },
  { id: 'avviso_bonario', label: 'Avvisi bonari', icon: '📨' },
];

const fmtSize = b => (b ? `${(b / 1024).toFixed(0)} KB` : '');
const fmtData = s => (s ? new Date(s).toLocaleDateString('it-IT') : '');

export default function DocumentiFiscali() {
  const confirm = useConfirm();
  const [categoria, setCategoria] = useState('dichiarazione_iva');
  const [documenti, setDocumenti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [periodo, setPeriodo] = useState('');
  const [msg, setMsg] = useState(null);
  const fileRef = useRef(null);

  const catCorrente = useMemo(() => CATEGORIE.find(c => c.id === categoria), [categoria]);

  const carica = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/api/documenti-fiscali/lista?categoria=${categoria}`);
      setDocumenti(res.data?.documenti || []);
    } catch (e) {
      setMsg({ tipo: 'errore', testo: 'Errore caricamento: ' + (e.response?.data?.detail || e.message) });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    carica();
  }, [categoria]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleUpload = async e => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setMsg(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('categoria', categoria);
      if (periodo.trim()) fd.append('periodo', periodo.trim());
      const res = await api.post('/api/documenti-fiscali/upload', fd);
      setMsg({
        tipo: 'ok',
        testo: res.data?.duplicate
          ? 'Documento già presente (nessun doppione creato).'
          : 'Documento caricato e memorizzato.',
      });
      setPeriodo('');
      await carica();
    } catch (err) {
      setMsg({ tipo: 'errore', testo: 'Errore upload: ' + (err.response?.data?.detail || err.message) });
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  return (
    <PageLayout title="Documenti fiscali" icon="🗂️" subtitle="Dichiarazioni IVA, cartelle esattoriali, avvisi bonari">
      {/* Selettore categoria */}
      <div style={STILI.tabs} data-testid="docfisc-categorie">
        {CATEGORIE.map(c => {
          const attiva = c.id === categoria;
          return (
            <button
              key={c.id}
              onClick={() => setCategoria(c.id)}
              data-testid={`docfisc-cat-${c.id}`}
              style={{
                ...STILI.tab,
                background: attiva ? COLORS.primary : '#fff',
                color: attiva ? '#fff' : COLORS.text,
                borderColor: attiva ? COLORS.primary : COLORS.border,
              }}
            >
              <span>{c.icon}</span> {c.label}
            </button>
          );
        })}
      </div>

      {/* Barra upload */}
      <div style={STILI.uploadBar}>
        <input
          type="text"
          value={periodo}
          onChange={e => setPeriodo(e.target.value)}
          placeholder="Periodo (es. 2025 o 2026-03) — facoltativo"
          style={STILI.input}
        />
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf"
          onChange={handleUpload}
          style={{ display: 'none' }}
          data-testid="docfisc-file"
        />
        <Button
          variant="primary"
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          data-testid="docfisc-upload-btn"
        >
          <Upload size={16} /> {uploading ? 'Caricamento…' : `Carica ${catCorrente?.label}`}
        </Button>
        <Button variant="secondary" onClick={carica} disabled={loading}>
          <RefreshCw size={16} className={loading ? 'spin' : ''} /> Aggiorna
        </Button>
      </div>

      {msg && (
        <div style={{ ...STILI.msg, ...(msg.tipo === 'ok' ? STILI.msgOk : STILI.msgErr) }}>
          {msg.testo}
        </div>
      )}

      {/* Lista */}
      {loading ? (
        <div style={STILI.vuoto}>Caricamento…</div>
      ) : documenti.length === 0 ? (
        <div style={STILI.vuoto}>
          Nessun documento in «{catCorrente?.label}». Carica il primo PDF con il bottone qui sopra.
        </div>
      ) : (
        <div style={STILI.lista}>
          {documenti.map(d => (
            <div key={d.id} style={STILI.riga} data-testid={`docfisc-riga-${d.id}`}>
              <FileText size={20} style={{ color: COLORS.primary, flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, color: COLORS.text, overflowWrap: 'anywhere' }}>
                  {d.filename}
                </div>
                <div style={{ fontSize: 12, color: COLORS.textMuted }}>
                  {d.periodo ? `Periodo ${d.periodo} · ` : ''}
                  {fmtData(d.created_at)} · {fmtSize(d.size_bytes)}
                </div>
              </div>
              <a
                href={d.download_url}
                target="_blank"
                rel="noopener noreferrer"
                style={STILI.scarica}
                data-testid={`docfisc-scarica-${d.id}`}
              >
                <Download size={15} /> Scarica
              </a>
            </div>
          ))}
        </div>
      )}
    </PageLayout>
  );
}

const STILI = {
  tabs: { display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 },
  tab: {
    display: 'inline-flex', alignItems: 'center', gap: 6, padding: '9px 14px',
    borderRadius: 8, border: `1px solid ${COLORS.border}`, fontSize: 13,
    fontWeight: 600, cursor: 'pointer',
  },
  uploadBar: {
    display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center',
    background: COLORS.card, border: `1px solid ${COLORS.border}`,
    borderRadius: 10, padding: 12, marginBottom: 12,
  },
  input: {
    flex: '1 1 240px', minWidth: 0, padding: '8px 10px', borderRadius: 8,
    border: `1px solid ${COLORS.border}`, fontSize: 13,
  },
  msg: { padding: '8px 12px', borderRadius: 8, fontSize: 13, marginBottom: 12 },
  msgOk: { background: '#dcfce7', color: '#166534', border: '1px solid #86efac' },
  msgErr: { background: '#fee2e2', color: '#b91c1c', border: '1px solid #fca5a5' },
  vuoto: { padding: 32, textAlign: 'center', color: COLORS.textMuted },
  lista: { display: 'flex', flexDirection: 'column', gap: 8 },
  riga: {
    display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px',
    background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10,
  },
  scarica: {
    display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 12px',
    borderRadius: 8, background: COLORS.primary, color: '#fff', fontSize: 13,
    fontWeight: 600, textDecoration: 'none', flexShrink: 0,
  },
};

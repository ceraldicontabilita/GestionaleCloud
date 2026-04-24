// ImportDipendentiModal.jsx — Import massivo dipendenti da JSON/Excel
// Flusso: paste JSON o upload file → preview dry-run → conferma → apply
import React, { useState, useMemo } from 'react';
import { X, Upload, AlertTriangle, CheckCircle, FileText, Eye, Play } from 'lucide-react';
import api from '../lib/api';
import { COLORS, SPACING } from '../lib/utils';

export default function ImportDipendentiModal({ onClose, onImported }) {
  const [step, setStep] = useState('input'); // input | preview | applying | done
  const [jsonText, setJsonText] = useState('');
  const [overwrite, setOverwrite] = useState(true);
  const [parseError, setParseError] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [applyResult, setApplyResult] = useState(null);
  const [apiError, setApiError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [fileName, setFileName] = useState(null);

  // Parsing del testo JSON per estrarre la lista dipendenti
  const parsedPayload = useMemo(() => {
    if (!jsonText.trim()) return null;
    try {
      const obj = JSON.parse(jsonText);
      // Accetta sia { dipendenti: [...] } che direttamente [...]
      const lista = Array.isArray(obj) ? obj : obj.dipendenti;
      if (!Array.isArray(lista)) {
        throw new Error('Il JSON deve essere un array oppure { dipendenti: [...] }');
      }
      setParseError(null);
      return { dipendenti: lista, overwrite_fields: overwrite };
    } catch (e) {
      setParseError(e.message);
      return null;
    }
  }, [jsonText, overwrite]);

  const numDipendenti = parsedPayload?.dipendenti?.length || 0;

  // Upload file JSON
  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (ev) => setJsonText(ev.target.result);
    reader.onerror = () => setParseError('Errore lettura file');
    reader.readAsText(file);
  };

  // Chiama endpoint preview
  const handlePreview = async () => {
    if (!parsedPayload) return;
    setLoading(true);
    setApiError(null);
    try {
      const resp = await api.post('/api/dipendenti/bulk-upsert/preview', parsedPayload);
      setPreviewData(resp.data);
      setStep('preview');
    } catch (e) {
      setApiError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  // Chiama endpoint bulk-upsert (vero)
  const handleApply = async () => {
    if (!parsedPayload) return;
    setStep('applying');
    setLoading(true);
    setApiError(null);
    try {
      const resp = await api.post('/api/dipendenti/bulk-upsert', parsedPayload);
      setApplyResult(resp.data);
      setStep('done');
      if (onImported) onImported(resp.data);
    } catch (e) {
      setApiError(e.response?.data?.detail || e.message);
      setStep('preview'); // torna a preview per ritentare
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(15, 39, 68, 0.6)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          backgroundColor: COLORS.card,
          borderRadius: 12,
          width: '100%',
          maxWidth: 980,
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '16px 24px',
            borderBottom: `1px solid ${COLORS.border}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: `linear-gradient(135deg, ${COLORS.primary}, #1a3a5f)`,
            borderRadius: '12px 12px 0 0',
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: 18, color: 'white', fontWeight: 700 }}>
              📥 Import massivo dipendenti
            </h2>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.75)', marginTop: 2 }}>
              {step === 'input' && 'Incolla JSON o carica file per importare'}
              {step === 'preview' && `Anteprima: ${numDipendenti} dipendenti da processare`}
              {step === 'applying' && 'Applicazione in corso…'}
              {step === 'done' && '✅ Import completato'}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'rgba(255,255,255,0.15)',
              border: '1px solid rgba(255,255,255,0.3)',
              borderRadius: 8,
              padding: 6,
              cursor: 'pointer',
              color: 'white',
              display: 'flex',
            }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Stepper */}
        <div style={{ display: 'flex', padding: '12px 24px', borderBottom: `1px solid ${COLORS.border}`, gap: 4, fontSize: 11, color: COLORS.textMuted, alignItems: 'center' }}>
          <Step active={step === 'input'} done={step !== 'input'} label="1. Dati" />
          <Sep />
          <Step active={step === 'preview'} done={step === 'done' || step === 'applying'} label="2. Anteprima" />
          <Sep />
          <Step active={step === 'applying'} done={step === 'done'} label="3. Applica" />
          <Sep />
          <Step active={step === 'done'} done={step === 'done'} label="4. Fatto" />
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
          {step === 'input' && (
            <InputStep
              jsonText={jsonText}
              setJsonText={setJsonText}
              parseError={parseError}
              numDipendenti={numDipendenti}
              overwrite={overwrite}
              setOverwrite={setOverwrite}
              fileName={fileName}
              onFileUpload={handleFileUpload}
            />
          )}
          {step === 'preview' && previewData && (
            <PreviewStep data={previewData} />
          )}
          {step === 'applying' && (
            <div style={{ textAlign: 'center', padding: 60, color: COLORS.textMuted }}>
              ⏳ Applicazione in corso…
            </div>
          )}
          {step === 'done' && applyResult && (
            <DoneStep data={applyResult} />
          )}

          {apiError && (
            <div
              style={{
                marginTop: 16,
                padding: 12,
                background: '#fee2e2',
                border: '1px solid #fca5a5',
                borderRadius: 8,
                color: '#b91c1c',
                fontSize: 13,
                display: 'flex',
                gap: 10,
                alignItems: 'flex-start',
              }}
            >
              <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
              <div>
                <div style={{ fontWeight: 700, marginBottom: 2 }}>Errore API</div>
                <div>{apiError}</div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '14px 24px',
            borderTop: `1px solid ${COLORS.border}`,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
            background: '#f8fafc',
            borderRadius: '0 0 12px 12px',
          }}
        >
          <div style={{ fontSize: 12, color: COLORS.textMuted }}>
            {step === 'input' && numDipendenti > 0 && `${numDipendenti} dipendenti pronti`}
            {step === 'preview' && previewData && `${previewData.totali.input} input · ${previewData.totali.creati} da creare · ${previewData.totali.aggiornati} da aggiornare · ${previewData.totali.saltati} da saltare`}
            {step === 'done' && applyResult && `✅ ${applyResult.totali.creati} creati, ${applyResult.totali.aggiornati} aggiornati, ${applyResult.totali.saltati} saltati`}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={onClose}
              style={{
                padding: '8px 16px',
                background: 'transparent',
                border: `1px solid ${COLORS.border}`,
                borderRadius: 8,
                cursor: 'pointer',
                fontSize: 13,
                color: COLORS.text,
              }}
            >
              {step === 'done' ? 'Chiudi' : 'Annulla'}
            </button>

            {step === 'input' && (
              <button
                onClick={handlePreview}
                disabled={!parsedPayload || loading}
                style={{
                  padding: '8px 16px',
                  background: parsedPayload && !loading ? COLORS.primary : '#cbd5e1',
                  color: 'white',
                  border: 'none',
                  borderRadius: 8,
                  cursor: parsedPayload && !loading ? 'pointer' : 'not-allowed',
                  fontSize: 13,
                  fontWeight: 600,
                  display: 'flex',
                  gap: 6,
                  alignItems: 'center',
                }}
              >
                <Eye size={14} />
                {loading ? 'Calcolo…' : 'Genera anteprima'}
              </button>
            )}
            {step === 'preview' && (
              <>
                <button
                  onClick={() => setStep('input')}
                  style={{
                    padding: '8px 16px',
                    background: 'transparent',
                    border: `1px solid ${COLORS.border}`,
                    borderRadius: 8,
                    cursor: 'pointer',
                    fontSize: 13,
                  }}
                >
                  ← Indietro
                </button>
                <button
                  onClick={handleApply}
                  disabled={loading}
                  style={{
                    padding: '8px 16px',
                    background: COLORS.accent || '#b8860b',
                    color: 'white',
                    border: 'none',
                    borderRadius: 8,
                    cursor: loading ? 'not-allowed' : 'pointer',
                    fontSize: 13,
                    fontWeight: 600,
                    display: 'flex',
                    gap: 6,
                    alignItems: 'center',
                  }}
                >
                  <Play size={14} />
                  Applica import
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Step({ active, done, label }) {
  return (
    <div
      style={{
        padding: '4px 10px',
        borderRadius: 6,
        background: done ? '#d1fae5' : active ? '#dbeafe' : 'transparent',
        color: done ? '#15803d' : active ? '#1d4ed8' : COLORS.textMuted,
        fontWeight: active || done ? 700 : 400,
        fontSize: 11,
      }}
    >
      {label}
    </div>
  );
}

function Sep() {
  return <div style={{ color: COLORS.textMuted }}>›</div>;
}

// ────────────────── STEP: INPUT ──────────────────
function InputStep({ jsonText, setJsonText, parseError, numDipendenti, overwrite, setOverwrite, fileName, onFileUpload }) {
  return (
    <>
      <div style={{ marginBottom: 16, fontSize: 13, color: COLORS.textMuted, lineHeight: 1.5 }}>
        Incolla un JSON nel formato <code>{`{ dipendenti: [...] }`}</code> oppure carica un file .json.
        Il match per aggiornamento è sul <strong>codice fiscale</strong> normalizzato (upper-case + trim).
      </div>

      <div style={{ display: 'flex', gap: 10, marginBottom: 14, alignItems: 'center' }}>
        <label
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 14px',
            border: `1px dashed ${COLORS.border}`,
            borderRadius: 8,
            cursor: 'pointer',
            fontSize: 13,
            color: COLORS.primary,
            background: '#f8fafc',
          }}
        >
          <Upload size={14} />
          Carica file JSON
          <input type="file" accept=".json,application/json" onChange={onFileUpload} style={{ display: 'none' }} />
        </label>
        {fileName && (
          <span style={{ fontSize: 12, color: COLORS.textMuted, display: 'inline-flex', gap: 4, alignItems: 'center' }}>
            <FileText size={12} /> {fileName}
          </span>
        )}
      </div>

      <textarea
        value={jsonText}
        onChange={(e) => setJsonText(e.target.value)}
        placeholder='{ "dipendenti": [ { "cognome": "Rossi", "nome": "Mario", "codice_fiscale": "RSSMRA80A01H501Z", ... } ] }'
        style={{
          width: '100%',
          minHeight: 240,
          padding: 12,
          fontFamily: 'SF Mono, Menlo, Consolas, monospace',
          fontSize: 12,
          border: `1px solid ${parseError ? '#fca5a5' : COLORS.border}`,
          borderRadius: 8,
          resize: 'vertical',
          boxSizing: 'border-box',
          background: parseError ? '#fef2f2' : '#fafafa',
        }}
      />

      {parseError && (
        <div style={{ marginTop: 8, fontSize: 12, color: '#b91c1c' }}>
          ⚠️ {parseError}
        </div>
      )}
      {!parseError && numDipendenti > 0 && (
        <div style={{ marginTop: 8, fontSize: 13, color: COLORS.success || '#15803d', fontWeight: 600 }}>
          ✓ {numDipendenti} dipendenti riconosciuti nel JSON
        </div>
      )}

      <label
        style={{
          marginTop: 16,
          display: 'flex',
          alignItems: 'flex-start',
          gap: 10,
          padding: 12,
          background: overwrite ? '#fef3c7' : '#f1f5f9',
          border: `1px solid ${overwrite ? '#fcd34d' : COLORS.border}`,
          borderRadius: 8,
          cursor: 'pointer',
        }}
      >
        <input
          type="checkbox"
          checked={overwrite}
          onChange={(e) => setOverwrite(e.target.checked)}
          style={{ marginTop: 2 }}
        />
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, color: COLORS.text }}>
            Sovrascrivi campi già popolati (<code>overwrite_fields: true</code>)
          </div>
          <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 2 }}>
            Se disattivo, i campi del record esistente vengono conservati se non vuoti.
            Se attivo, i dati del file sovrascrivono sempre.
          </div>
        </div>
      </label>
    </>
  );
}

// ────────────────── STEP: PREVIEW ──────────────────
function PreviewStep({ data }) {
  const { totali, risultati } = data;
  return (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 16 }}>
        <Kpi label="Input" value={totali.input} color={COLORS.primary} />
        <Kpi label="Da creare" value={totali.creati} color="#15803d" />
        <Kpi label="Da aggiornare" value={totali.aggiornati} color="#b45309" />
        <Kpi label="Da saltare" value={totali.saltati} color="#64748b" />
      </div>

      <div style={{ fontSize: 11, color: COLORS.textMuted, marginBottom: 8, padding: 10, background: '#dbeafe', borderRadius: 6 }}>
        🔍 <strong>Anteprima (dry-run)</strong> — Nessun dato è stato scritto sul database. Clicca "Applica import" per confermare.
      </div>

      <div style={{ overflowX: 'auto', border: `1px solid ${COLORS.border}`, borderRadius: 8 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: '#f1f5f9' }}>
              <th style={thStyle}>#</th>
              <th style={thStyle}>Esito</th>
              <th style={thStyle}>Nominativo</th>
              <th style={thStyle}>CF</th>
              <th style={thStyle}>Dettaglio</th>
            </tr>
          </thead>
          <tbody>
            {risultati.map((r) => (
              <tr
                key={r.riga}
                style={{
                  borderTop: `1px solid ${COLORS.border}`,
                  background:
                    r.esito === 'created' ? '#f0fdf4' :
                    r.esito === 'updated' ? '#fffbeb' :
                    '#f8fafc',
                }}
              >
                <td style={tdStyle}>{r.riga}</td>
                <td style={tdStyle}>
                  <EsitoBadge esito={r.esito} />
                </td>
                <td style={tdStyle}>
                  <strong>{r.nominativo}</strong>
                </td>
                <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 11 }}>
                  {r.codice_fiscale || '-'}
                </td>
                <td style={{ ...tdStyle, fontSize: 11, color: COLORS.textMuted }}>
                  {r.esito === 'created' && r.campi_nuovi && `+ ${r.campi_nuovi.length} campi: ${r.campi_nuovi.join(', ')}`}
                  {r.esito === 'updated' && r.diff && (
                    <DiffView diff={r.diff} />
                  )}
                  {r.esito === 'skipped' && (r.motivo || 'skip')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function DiffView({ diff }) {
  const entries = Object.entries(diff);
  if (!entries.length) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {entries.slice(0, 3).map(([k, v]) => (
        <div key={k} style={{ fontSize: 10.5 }}>
          <strong>{k}</strong>:{' '}
          <span style={{ textDecoration: 'line-through', color: '#94a3b8' }}>
            {String(v.vecchio ?? '—').slice(0, 40)}
          </span>{' '}
          → <span style={{ color: '#b45309', fontWeight: 600 }}>{String(v.nuovo ?? '').slice(0, 40)}</span>
        </div>
      ))}
      {entries.length > 3 && (
        <div style={{ fontSize: 10, color: COLORS.textMuted }}>
          + {entries.length - 3} altri campi…
        </div>
      )}
    </div>
  );
}

// ────────────────── STEP: DONE ──────────────────
function DoneStep({ data }) {
  const { totali, risultati } = data;
  return (
    <>
      <div style={{ textAlign: 'center', padding: '20px 0 30px', color: COLORS.success || '#15803d' }}>
        <CheckCircle size={48} style={{ margin: '0 auto 12px', display: 'block' }} />
        <div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text }}>Import completato!</div>
        <div style={{ fontSize: 13, color: COLORS.textMuted, marginTop: 4 }}>
          {totali.creati} nuovi dipendenti, {totali.aggiornati} aggiornati, {totali.saltati} saltati
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 16 }}>
        <Kpi label="Input" value={totali.input} color={COLORS.primary} />
        <Kpi label="Creati" value={totali.creati} color="#15803d" />
        <Kpi label="Aggiornati" value={totali.aggiornati} color="#b45309" />
        <Kpi label="Saltati" value={totali.saltati} color="#64748b" />
      </div>

      <details>
        <summary style={{ cursor: 'pointer', fontSize: 12, color: COLORS.textMuted, padding: 6 }}>
          Mostra dettagli riga per riga ({risultati.length})
        </summary>
        <div style={{ marginTop: 8, maxHeight: 300, overflowY: 'auto', border: `1px solid ${COLORS.border}`, borderRadius: 6 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
            <tbody>
              {risultati.map((r) => (
                <tr key={r.riga} style={{ borderTop: `1px solid ${COLORS.border}` }}>
                  <td style={{ padding: 6, width: 30 }}>{r.riga}</td>
                  <td style={{ padding: 6 }}><EsitoBadge esito={r.esito} /></td>
                  <td style={{ padding: 6 }}>{r.nominativo}</td>
                  <td style={{ padding: 6, fontFamily: 'monospace' }}>{r.codice_fiscale}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}

function EsitoBadge({ esito }) {
  const map = {
    created: { bg: '#d1fae5', color: '#15803d', label: 'Creato' },
    updated: { bg: '#fef3c7', color: '#b45309', label: 'Aggiornato' },
    skipped: { bg: '#e2e8f0', color: '#64748b', label: 'Saltato' },
  };
  const s = map[esito] || map.skipped;
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 4,
        fontSize: 10,
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        background: s.bg,
        color: s.color,
      }}
    >
      {s.label}
    </span>
  );
}

function Kpi({ label, value, color }) {
  return (
    <div
      style={{
        padding: 12,
        background: '#f8fafc',
        border: `1px solid ${COLORS.border}`,
        borderRadius: 8,
        borderTop: `2px solid ${color}`,
      }}
    >
      <div style={{ fontSize: 10, fontWeight: 700, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color: COLORS.text, fontVariantNumeric: 'tabular-nums', marginTop: 2 }}>
        {value}
      </div>
    </div>
  );
}

const thStyle = {
  padding: 8,
  textAlign: 'left',
  fontSize: 10,
  fontWeight: 700,
  textTransform: 'uppercase',
  color: COLORS.textMuted,
  letterSpacing: '0.05em',
};
const tdStyle = {
  padding: 8,
  verticalAlign: 'top',
};

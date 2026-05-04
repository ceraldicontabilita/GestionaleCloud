import React, { useState } from 'react';
import { Download, FileSpreadsheet, FileText, AlertTriangle, CheckCircle2 } from 'lucide-react';
import api from '../../api';
import { COLORS } from '../../lib/utils';
import { useAnnoGlobal } from '../../contexts/AnnoContext';

const MESI_LABEL = [
  'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
  'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre',
];

export default function HRPresenzeExport() {
  const { anno: annoGlobale } = useAnnoGlobal();
  const [anno, setAnno] = useState(annoGlobale || new Date().getFullYear());
  const [mese, setMese] = useState(new Date().getMonth() + 1);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const cardStyle = {
    background: 'white',
    border: `1px solid ${COLORS.border}`,
    borderRadius: 14,
    padding: 20,
    boxShadow: '0 1px 3px rgba(15, 39, 68, 0.08)',
  };

  const btnBase = {
    border: 'none',
    borderRadius: 10,
    padding: '10px 16px',
    color: 'white',
    fontWeight: 700,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8,
    cursor: loading ? 'not-allowed' : 'pointer',
    opacity: loading ? 0.7 : 1,
  };

  const fetchPreview = async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await api.get('/api/attendance/export-consulente/preview', {
        params: { anno, mese },
      });
      setPreview(res.data);
      setSuccess('Preview export caricata');
    } catch (err) {
      setError(err?.response?.data?.detail || 'Errore caricamento preview export');
    } finally {
      setLoading(false);
    }
  };

  const downloadFile = async (format) => {
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const endpoint = format === 'pdf'
        ? '/api/attendance/genera-pdf-consulente'
        : '/api/attendance/export-consulente/csv';

      const response = format === 'pdf'
        ? await api.post(endpoint, { anno, mese }, { responseType: 'blob' })
        : await api.get(endpoint, { params: { anno, mese }, responseType: 'blob' });

      const blob = new Blob([response.data], {
        type: format === 'pdf' ? 'application/pdf' : 'text/csv;charset=utf-8',
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = format === 'pdf'
        ? `presenze_consulente_${anno}_${String(mese).padStart(2, '0')}.pdf`
        : `presenze_consulente_${anno}_${String(mese).padStart(2, '0')}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setSuccess(`Export ${format.toUpperCase()} generato`);
    } catch (err) {
      setError(err?.response?.data?.detail || `Errore export ${format.toUpperCase()}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: '0 auto' }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 26, color: COLORS.text, fontWeight: 800 }}>
          Export Presenze Consulente
        </h1>
        <p style={{ margin: '6px 0 0', color: COLORS.textMuted, fontSize: 14 }}>
          Le presenze si gestiscono nel gestionale e si esportano al consulente del lavoro. Non si importano presenze da PDF.
        </p>
      </div>

      <div style={{ ...cardStyle, marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'end', flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: COLORS.text }}>Anno</span>
            <input
              type="number"
              value={anno}
              min="2020"
              max="2100"
              onChange={(e) => setAnno(Number(e.target.value))}
              style={{ padding: '9px 12px', border: `1px solid ${COLORS.border}`, borderRadius: 8, fontSize: 14 }}
            />
          </label>

          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: COLORS.text }}>Mese</span>
            <select
              value={mese}
              onChange={(e) => setMese(Number(e.target.value))}
              style={{ padding: '9px 12px', border: `1px solid ${COLORS.border}`, borderRadius: 8, fontSize: 14 }}
            >
              {MESI_LABEL.map((m, idx) => (
                <option key={m} value={idx + 1}>{m}</option>
              ))}
            </select>
          </label>

          <button onClick={fetchPreview} disabled={loading} style={{ ...btnBase, background: '#0f2744' }}>
            <CheckCircle2 size={16} />
            Controlla preview
          </button>
          <button onClick={() => downloadFile('csv')} disabled={loading} style={{ ...btnBase, background: '#1a40b5' }}>
            <FileSpreadsheet size={16} />
            Scarica CSV
          </button>
          <button onClick={() => downloadFile('pdf')} disabled={loading} style={{ ...btnBase, background: '#b8860b' }}>
            <FileText size={16} />
            Scarica PDF
          </button>
        </div>
      </div>

      {error && (
        <div style={{ ...cardStyle, borderColor: '#fecaca', background: '#fef2f2', color: '#991b1b', marginBottom: 16 }}>
          <AlertTriangle size={18} style={{ verticalAlign: 'middle', marginRight: 8 }} />
          {error}
        </div>
      )}

      {success && (
        <div style={{ ...cardStyle, borderColor: '#bbf7d0', background: '#f0fdf4', color: '#166534', marginBottom: 16 }}>
          <CheckCircle2 size={18} style={{ verticalAlign: 'middle', marginRight: 8 }} />
          {success}
        </div>
      )}

      <div style={cardStyle}>
        <h2 style={{ marginTop: 0, fontSize: 18, color: COLORS.text }}>Preview export</h2>
        {!preview ? (
          <p style={{ color: COLORS.textMuted, marginBottom: 0 }}>
            Usa “Controlla preview” per vedere quanti dipendenti saranno esportati e se ci sono anomalie.
          </p>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
              <Metric label="Anno" value={preview.anno} />
              <Metric label="Mese" value={MESI_LABEL[(preview.mese || 1) - 1]} />
              <Metric label="Dipendenti esportati" value={preview.dipendenti || 0} />
              <Metric label="Anomalie" value={preview.anomalie_count || 0} />
            </div>

            {(preview.anomalie || []).length > 0 ? (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#f8fafc' }}>
                      <th style={th}>Dipendente</th>
                      <th style={th}>Data</th>
                      <th style={th}>Codice</th>
                      <th style={th}>Messaggio</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.anomalie.map((a, idx) => (
                      <tr key={`${a.employee_id || idx}-${a.data || idx}`}>
                        <td style={td}>{a.dipendente}</td>
                        <td style={td}>{a.data}</td>
                        <td style={td}>{a.codice}</td>
                        <td style={td}>{a.messaggio}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p style={{ color: '#166534', marginBottom: 0 }}>Nessuna anomalia rilevata nella preview.</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div style={{ minWidth: 150, padding: 14, borderRadius: 12, background: '#f8fafc', border: '1px solid #e2e8f0' }}>
      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 800, color: '#0f2744' }}>{value}</div>
    </div>
  );
}

const th = { textAlign: 'left', padding: 10, borderBottom: '1px solid #e2e8f0', color: '#0f2744' };
const td = { padding: 10, borderBottom: '1px solid #e2e8f0', color: '#334155' };

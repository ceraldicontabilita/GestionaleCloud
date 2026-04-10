import React, { useState, useEffect, useCallback } from 'react';
import { FileText, Download, RefreshCw, Mail, CheckCircle, AlertCircle } from 'lucide-react';
import api from '../../api';
import { COLORS, useIsMobile, formatEuro as fmtEuro } from '../../lib/utils';

const ANNO_CORRENTE = new Date().getFullYear();
const ANNI = [ANNO_CORRENTE, ANNO_CORRENTE - 1, ANNO_CORRENTE - 2];
const MESI = ['Gen','Feb','Mar','Apr','Mag','Giu','Lug','Ago','Set','Ott','Nov','Dic'];

function formatEuro(v) {
  if (v == null || isNaN(v)) return '—';
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v);
}

function Badge({ pagato }) {
  return (
    <span style={{
      padding: '3px 10px', borderRadius: 99, fontSize: 11, fontWeight: 600,
      background: pagato ? '#dcfce7' : '#fef9c3',
      color: pagato ? '#16a34a' : '#a16207'
    }}>
      {pagato ? 'Pagato' : 'Da pagare'}
    </span>
  );
}

export default function HRCedolini() {
  const isMobile = useIsMobile();
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [tab, setTab] = useState('cedolini');
  const [cedolini, setCedolini] = useState([]);
  const [f24, setF24] = useState([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([
      api.get('/api/cedolini', { params: { anno, limit: 200 } }),
      api.get('/api/paghe/distinte-f24', { params: { anno } }).catch(() => ({ data: [] })),
    ])
      .then(([cedRes, f24Res]) => {
        const c = cedRes.data?.cedolini || (Array.isArray(cedRes.data) ? cedRes.data : []);
        setCedolini(c);
        const f = f24Res.data?.distinte || (Array.isArray(f24Res.data) ? f24Res.data : []);
        setF24(f);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [anno]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleImportGmail = async () => {
    setImporting(true);
    setImportResult(null);
    try {
      const res = await api.post('/api/cedolini/import-gmail?since_days=180');
      setImportResult({ success: true, ...res.data });
      // Ricarica dati dopo import
      loadData();
    } catch (err) {
      const detail = err?.response?.data?.detail || 'Errore durante il download da Gmail';
      setImportResult({ success: false, messaggio: detail });
    } finally {
      setImporting(false);
    }
  };

  const totaleLordo = cedolini.reduce((s, b) => s + (Number(b.lordo) || 0), 0);
  const totaleNetto = cedolini.reduce((s, b) => s + (Number(b.netto) || 0), 0);
  const daPagare = cedolini.filter(b => !b.pagato).reduce((s, b) => s + (Number(b.netto) || 0), 0);
  const daGmail = cedolini.filter(b => b.source === 'gmail').length;

  return (
    <div style={{ padding: 24, maxWidth: 1200 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: COLORS.text }}>Cedolini & Paghe</h1>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select
            data-testid="select-anno-cedolini"
            value={anno}
            onChange={e => setAnno(Number(e.target.value))}
            style={{ padding: '8px 14px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 14, background: 'white' }}
          >
            {ANNI.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
          <button
            data-testid="btn-refresh-cedolini"
            onClick={loadData}
            disabled={loading}
            style={{ padding: '8px 14px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 13, background: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            Aggiorna
          </button>
          <button
            data-testid="btn-import-gmail"
            onClick={handleImportGmail}
            disabled={importing}
            style={{
              padding: '8px 16px', border: 'none', borderRadius: 6, fontSize: 13,
              background: importing ? COLORS.border : COLORS.primary,
              color: 'white', cursor: importing ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600,
              transition: 'background 0.2s'
            }}
          >
            <Mail size={14} />
            {importing ? 'Download in corso…' : 'Importa da Gmail'}
          </button>
        </div>
      </div>

      {/* Risultato import */}
      {importResult && (
        <div
          data-testid="import-result-banner"
          style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '12px 16px', borderRadius: 8, marginBottom: 16,
            background: importResult.success ? '#f0fdf4' : '#fef2f2',
            border: `1px solid ${importResult.success ? '#bbf7d0' : '#fecaca'}`,
            color: importResult.success ? '#15803d' : '#dc2626',
            fontSize: 14,
          }}
        >
          {importResult.success
            ? <CheckCircle size={16} />
            : <AlertCircle size={16} />}
          <span style={{ fontWeight: 600 }}>{importResult.messaggio}</span>
          {importResult.success && importResult.trovati > 0 && (
            <span style={{ color: '#64748b', fontWeight: 400 }}>
              &nbsp;— {importResult.trovati} allegati trovati, {importResult.duplicati_saltati} già presenti
            </span>
          )}
          <button
            onClick={() => setImportResult(null)}
            style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', fontSize: 16, color: '#94a3b8' }}
          >×</button>
        </div>
      )}

      {/* KPI */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { label: 'Cedolini Totali', value: cedolini.length },
          { label: 'Da Gmail', value: daGmail, highlight: daGmail > 0 },
          { label: 'Lordo Annuo', value: formatEuro(totaleLordo) },
          { label: 'Da Pagare', value: formatEuro(daPagare), highlight: daPagare > 0 },
        ].map(s => (
          <div key={s.label} style={{
            background: s.highlight ? `${COLORS.primary}08` : 'white',
            border: `1px solid ${s.highlight ? COLORS.primary + '30' : COLORS.border}`,
            borderRadius: 10, padding: '16px 20px'
          }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{s.label}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: s.highlight ? COLORS.primary : COLORS.text, marginTop: 6 }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ background: 'white', border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ display: 'flex', borderBottom: `1px solid ${COLORS.border}` }}>
          {[
            { id: 'cedolini', label: 'Cedolini / Buste Paga' },
            { id: 'f24', label: 'Distinte F24' },
          ].map(t => (
            <button
              key={t.id}
              data-testid={`tab-cedolini-${t.id}`}
              onClick={() => setTab(t.id)}
              style={{
                padding: '12px 20px', background: 'none', border: 'none',
                borderBottom: tab === t.id ? `3px solid ${COLORS.primary}` : '3px solid transparent',
                color: tab === t.id ? COLORS.primary : COLORS.textMuted,
                fontWeight: tab === t.id ? 700 : 400, cursor: 'pointer', fontSize: 13,
                marginBottom: -1,
              }}
            >{t.label}</button>
          ))}
        </div>

        <div style={{ padding: 20 }}>
          {loading && (
            <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>
              <RefreshCw size={20} style={{ animation: 'spin 1s linear infinite', marginBottom: 8 }} />
              <div>Caricamento…</div>
            </div>
          )}

          {!loading && tab === 'cedolini' && (
            cedolini.length === 0
              ? (
                <div style={{ padding: 48, textAlign: 'center', color: COLORS.textMuted }}>
                  <Mail size={40} style={{ marginBottom: 12, opacity: 0.3 }} />
                  <div style={{ fontSize: 15, marginBottom: 8 }}>Nessun cedolino per il {anno}</div>
                  <div style={{ fontSize: 13 }}>Usa il pulsante <strong>Importa da Gmail</strong> per scaricare le buste paga dalla casella mail aziendale.</div>
                </div>
              )
              : (
                <div style={{overflowX:'auto'}}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 500 }}>
                  <thead>
                    <tr style={{ background: '#f8fafc' }}>
                      {['Dipendente / File', 'Mese', 'Lordo', 'Netto', 'Fonte', 'Stato'].map(h => (
                        <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: COLORS.textMuted, textTransform: 'uppercase', borderBottom: `1px solid ${COLORS.border}` }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {cedolini.map((b, i) => (
                      <tr key={i} style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                        <td style={{ padding: '10px 12px', fontWeight: 600 }}>
                          {b.dipendente_nome || b.dipendente || b.filename || '—'}
                        </td>
                        <td style={{ padding: '10px 12px' }}>
                          {b.mese ? `${MESI[Number(b.mese) - 1] || b.mese} ${b.anno || anno}` : (b.email_date ? new Date(b.email_date).toLocaleDateString('it-IT') : '—')}
                        </td>
                        <td style={{ padding: '10px 12px' }}>{formatEuro(b.lordo)}</td>
                        <td style={{ padding: '10px 12px', fontWeight: 700, color: COLORS.primary }}>{formatEuro(b.netto)}</td>
                        <td style={{ padding: '10px 12px' }}>
                          <span style={{
                            padding: '2px 8px', borderRadius: 99, fontSize: 11, fontWeight: 600,
                            background: b.source === 'gmail' ? '#eff6ff' : '#f1f5f9',
                            color: b.source === 'gmail' ? '#2563eb' : '#64748b'
                          }}>
                            {b.source === 'gmail' ? 'Gmail' : b.source || 'manuale'}
                          </span>
                        </td>
                        <td style={{ padding: '10px 12px' }}>
                          <Badge pagato={b.pagato} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table></div>
              )
          )}

          {!loading && tab === 'f24' && (
            f24.length === 0
              ? <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>Nessuna distinta F24 per il {anno}</div>
              : (
                <div style={{overflowX:'auto'}}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 500 }}>
                  <thead>
                    <tr style={{ background: '#f8fafc' }}>
                      {['Riferimento', 'Mese', 'Importo', 'Scadenza', 'Stato'].map(h => (
                        <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: COLORS.textMuted, textTransform: 'uppercase', borderBottom: `1px solid ${COLORS.border}` }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {f24.map((f, i) => (
                      <tr key={i} style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                        <td style={{ padding: '10px 12px', fontWeight: 600 }}>{f.riferimento || f.codice || `F24 ${i + 1}`}</td>
                        <td style={{ padding: '10px 12px' }}>{MESI[Number(f.mese) - 1] || f.mese || '—'}</td>
                        <td style={{ padding: '10px 12px', fontWeight: 700, color: COLORS.primary }}>{formatEuro(f.importo || f.totale)}</td>
                        <td style={{ padding: '10px 12px' }}>{f.scadenza ? new Date(f.scadenza).toLocaleDateString('it-IT') : '—'}</td>
                        <td style={{ padding: '10px 12px' }}><Badge pagato={f.pagato} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table></div>
              )
          )}
        </div>
      </div>

      <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
    </div>
  );
}


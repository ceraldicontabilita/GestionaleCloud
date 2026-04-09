import React, { useState, useEffect, useCallback } from 'react';
import {
  Mail, Shield, Trash2, Plus, RefreshCw, Download,
  CheckCircle, XCircle, AlertCircle, ToggleLeft, ToggleRight, Send
} from 'lucide-react';
import api from '../api';
import { COLORS } from '../lib/utils';

const TIPI = ['fattura_xml', 'cedolino', 'pagopa', 'inps', 'inail', 'paypal', 'cartella_esattoriale', 'generico'];
const CANALI = ['pec', 'gmail'];

const TIPO_BADGE = {
  fattura_xml:         { bg: '#eff6ff', color: '#2563eb', label: 'Fattura XML' },
  cedolino:            { bg: '#f0fdf4', color: '#16a34a', label: 'Cedolino' },
  pagopa:              { bg: '#fdf4ff', color: '#9333ea', label: 'PagoPA' },
  inps:                { bg: '#fff7ed', color: '#ea580c', label: 'INPS' },
  inail:               { bg: '#f0f9ff', color: '#0284c7', label: 'INAIL' },
  paypal:              { bg: '#fefce8', color: '#ca8a04', label: 'PayPal' },
  cartella_esattoriale:{ bg: '#fef2f2', color: '#dc2626', label: 'Cartella Esatt.' },
  generico:            { bg: '#f8fafc', color: '#64748b', label: 'Generico' },
};

function TipoBadge({ tipo }) {
  const s = TIPO_BADGE[tipo] || TIPO_BADGE.generico;
  return (
    <span style={{ padding: '2px 8px', borderRadius: 99, fontSize: 11, fontWeight: 700, background: s.bg, color: s.color }}>
      {s.label}
    </span>
  );
}

function BuiltinBadge() {
  return (
    <span style={{ padding: '2px 7px', borderRadius: 99, fontSize: 10, fontWeight: 700, background: '#f1f5f9', color: '#64748b', border: '1px solid #e2e8f0' }}>
      builtin
    </span>
  );
}

export default function GestioneEmailMittenti() {
  const [mittenti, setMittenti] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [tab, setTab]           = useState('pec');

  // Form nuovo mittente
  const [showForm, setShowForm] = useState(false);
  const [form, setForm]         = useState({ pattern: '', canale: 'gmail', tipo_documento: 'generico', descrizione: '' });
  const [formSaving, setFormSaving] = useState(false);

  // Sync / download
  const [syncing, setSyncing]   = useState(false);
  const [syncResult, setSyncResult] = useState(null);

  // Test check
  const [checkAddr, setCheckAddr] = useState('');
  const [checkResult, setCheckResult] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/email-download/mittenti');
      setMittenti(res.data?.mittenti || []);
    } catch {}
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggle = async (m) => {
    try {
      await api.put(`/api/email-download/mittenti/${m.id}`, { attivo: !m.attivo });
      setMittenti(prev => prev.map(x => x.id === m.id ? { ...x, attivo: !x.attivo } : x));
    } catch {}
  };

  const del = async (m) => {
    if (!window.confirm(`Eliminare "${m.pattern}"?`)) return;
    try {
      await api.delete(`/api/email-download/mittenti/${m.id}`);
      setMittenti(prev => prev.filter(x => x.id !== m.id));
    } catch (e) {
      alert(e?.response?.data?.detail || 'Errore eliminazione');
    }
  };

  const addMittente = async () => {
    if (!form.pattern.trim()) return alert('Pattern obbligatorio');
    setFormSaving(true);
    try {
      await api.post('/api/email-download/mittenti', form);
      setShowForm(false);
      setForm({ pattern: '', canale: 'gmail', tipo_documento: 'generico', descrizione: '' });
      load();
    } catch (e) {
      alert(e?.response?.data?.detail || 'Errore salvataggio');
    } finally { setFormSaving(false); }
  };

  const runSync = async (tipo) => {
    setSyncing(true);
    setSyncResult(null);
    try {
      let res;
      if (tipo === 'pec') {
        res = await api.post('/api/email-download/pec/download-fatture-sync?since_days=180');
        const s = res.data?.stats || {};
        setSyncResult({ success: true, msg: `PEC: ${s.xml_found ?? '?'} XML trovati — ${s.new_invoices ?? '?'} fatture importate — ${s.duplicates_skipped ?? 0} duplicati` });
      } else {
        res = await api.post('/api/email-download/sync-email-now');
        setSyncResult({ success: true, msg: res.data?.message || 'Sync Gmail avviato in background' });
      }
    } catch (e) {
      setSyncResult({ success: false, msg: e?.response?.data?.detail || 'Errore sync' });
    } finally { setSyncing(false); }
  };

  const testCheck = async () => {
    if (!checkAddr.trim()) return;
    try {
      const res = await api.get('/api/email-download/mittenti/check', { params: { from_addr: checkAddr, canale: tab } });
      setCheckResult(res.data);
    } catch { setCheckResult(null); }
  };

  const filtrati = mittenti.filter(m => m.canale === tab);
  const pec   = mittenti.filter(m => m.canale === 'pec').length;
  const gmail = mittenti.filter(m => m.canale === 'gmail').length;
  const attivi = mittenti.filter(m => m.attivo).length;

  return (
    <div style={{ padding: 24, maxWidth: 1100 }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: COLORS.text }}>Gestione Email & Mittenti</h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: COLORS.textMuted }}>
            Mittenti attendibili per PEC e Gmail — routing automatico documenti
          </p>
        </div>
        <button
          data-testid="btn-add-mittente"
          onClick={() => setShowForm(v => !v)}
          style={{ padding: '8px 16px', background: COLORS.primary, color: 'white', border: 'none', borderRadius: 6, fontWeight: 600, fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
        >
          <Plus size={14} /> Aggiungi mittente
        </button>
      </div>

      {/* KPI */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 20 }}>
        {[
          { label: 'Totale', value: mittenti.length },
          { label: 'Attivi', value: attivi, hi: true },
          { label: 'PEC', value: pec },
          { label: 'Gmail', value: gmail },
        ].map(k => (
          <div key={k.label} style={{ background: 'white', border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: '14px 18px' }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase' }}>{k.label}</div>
            <div style={{ fontSize: 26, fontWeight: 700, color: k.hi ? COLORS.primary : COLORS.text, marginTop: 4 }}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* Sync result */}
      {syncResult && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '12px 16px', borderRadius: 8, marginBottom: 16,
          background: syncResult.success ? '#f0fdf4' : '#fef2f2',
          border: `1px solid ${syncResult.success ? '#bbf7d0' : '#fecaca'}`,
          color: syncResult.success ? '#15803d' : '#dc2626', fontSize: 14,
        }}>
          {syncResult.success ? <CheckCircle size={16} /> : <XCircle size={16} />}
          <span style={{ fontWeight: 600 }}>{syncResult.msg}</span>
          <button onClick={() => setSyncResult(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', fontSize: 16 }}>×</button>
        </div>
      )}

      {/* Form aggiungi mittente */}
      {showForm && (
        <div style={{ background: '#f8fafc', border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 20, marginBottom: 20 }}>
          <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 700, color: COLORS.text }}>Nuovo mittente personalizzato</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 2fr auto', gap: 10, alignItems: 'end' }}>
            <div>
              <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: COLORS.textMuted, marginBottom: 4 }}>PATTERN (contenuto nell'indirizzo)</label>
              <input
                data-testid="input-pattern-mittente"
                value={form.pattern}
                onChange={e => setForm(p => ({ ...p, pattern: e.target.value }))}
                placeholder="es. @esempio.it"
                style={{ width: '100%', padding: '8px 10px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 13, boxSizing: 'border-box' }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: COLORS.textMuted, marginBottom: 4 }}>CANALE</label>
              <select value={form.canale} onChange={e => setForm(p => ({ ...p, canale: e.target.value }))}
                style={{ width: '100%', padding: '8px 10px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 13 }}>
                {CANALI.map(c => <option key={c} value={c}>{c.toUpperCase()}</option>)}
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: COLORS.textMuted, marginBottom: 4 }}>TIPO DOCUMENTO</label>
              <select value={form.tipo_documento} onChange={e => setForm(p => ({ ...p, tipo_documento: e.target.value }))}
                style={{ width: '100%', padding: '8px 10px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 13 }}>
                {TIPI.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: COLORS.textMuted, marginBottom: 4 }}>DESCRIZIONE</label>
              <input value={form.descrizione} onChange={e => setForm(p => ({ ...p, descrizione: e.target.value }))}
                placeholder="Facoltativa"
                style={{ width: '100%', padding: '8px 10px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 13, boxSizing: 'border-box' }} />
            </div>
            <button
              data-testid="btn-salva-mittente"
              onClick={addMittente} disabled={formSaving}
              style={{ padding: '8px 16px', background: COLORS.primary, color: 'white', border: 'none', borderRadius: 6, fontWeight: 600, fontSize: 13, cursor: 'pointer', whiteSpace: 'nowrap' }}>
              {formSaving ? 'Salvo…' : 'Salva'}
            </button>
          </div>
        </div>
      )}

      {/* Tabs canale */}
      <div style={{ background: 'white', border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ display: 'flex', borderBottom: `1px solid ${COLORS.border}`, padding: '0 16px' }}>
          {[
            { id: 'pec',   label: `PEC Aruba (${pec})` },
            { id: 'gmail', label: `Gmail (${gmail})` },
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              padding: '12px 18px', background: 'none', border: 'none',
              borderBottom: tab === t.id ? `3px solid ${COLORS.primary}` : '3px solid transparent',
              color: tab === t.id ? COLORS.primary : COLORS.textMuted,
              fontWeight: tab === t.id ? 700 : 400, cursor: 'pointer', fontSize: 13, marginBottom: -1,
            }}>{t.label}</button>
          ))}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0' }}>
            {/* Download button */}
            <button
              data-testid={`btn-sync-${tab}`}
              onClick={() => runSync(tab)}
              disabled={syncing}
              style={{ padding: '6px 14px', background: syncing ? COLORS.border : '#1e3a5f', color: 'white', border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: syncing ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: 5 }}
            >
              {syncing ? <RefreshCw size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Download size={12} />}
              {syncing ? 'In corso…' : tab === 'pec' ? 'Scarica fatture PEC' : 'Sync Gmail ora'}
            </button>
          </div>
        </div>

        {/* Test check */}
        <div style={{ padding: '12px 16px', background: '#f8fafc', borderBottom: `1px solid ${COLORS.border}`, display: 'flex', gap: 8, alignItems: 'center' }}>
          <Mail size={14} color={COLORS.textMuted} />
          <span style={{ fontSize: 12, color: COLORS.textMuted, fontWeight: 600 }}>TEST MITTENTE:</span>
          <input
            data-testid="input-test-check"
            value={checkAddr}
            onChange={e => { setCheckAddr(e.target.value); setCheckResult(null); }}
            onKeyDown={e => e.key === 'Enter' && testCheck()}
            placeholder={tab === 'pec' ? 'es. sdi05@pec.fatturapa.it' : 'es. f.ferrantini@cedolino.it'}
            style={{ flex: 1, padding: '6px 10px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 12 }}
          />
          <button onClick={testCheck}
            style={{ padding: '6px 12px', background: COLORS.primary, color: 'white', border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}>
            <Send size={11} /> Verifica
          </button>
          {checkResult && (
            <span style={{
              padding: '4px 10px', borderRadius: 99, fontSize: 12, fontWeight: 700,
              background: checkResult.attendibile ? '#dcfce7' : '#fee2e2',
              color: checkResult.attendibile ? '#16a34a' : '#dc2626',
            }}>
              {checkResult.attendibile ? `✓ ${checkResult.tipo_documento}` : '✗ Non attendibile'}
            </span>
          )}
        </div>

        {/* Tabella mittenti */}
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>
            <RefreshCw size={18} style={{ animation: 'spin 1s linear infinite' }} /><br />Caricamento…
          </div>
        ) : filtrati.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted, fontSize: 14 }}>
            Nessun mittente per il canale {tab.toUpperCase()}
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                {['Pattern', 'Tipo documento', 'Descrizione', 'Builtin', 'Attivo', ''].map(h => (
                  <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: COLORS.textMuted, textTransform: 'uppercase', borderBottom: `1px solid ${COLORS.border}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtrati.map((m, i) => (
                <tr key={i} style={{ borderBottom: `1px solid ${COLORS.border}`, opacity: m.attivo ? 1 : 0.5 }}>
                  <td style={{ padding: '10px 14px', fontFamily: 'monospace', fontWeight: 600, fontSize: 12, color: COLORS.text }}>
                    {m.pattern}
                  </td>
                  <td style={{ padding: '10px 14px' }}><TipoBadge tipo={m.tipo_documento} /></td>
                  <td style={{ padding: '10px 14px', color: COLORS.textMuted, fontSize: 12 }}>{m.descrizione || '—'}</td>
                  <td style={{ padding: '10px 14px' }}>{m.builtin ? <BuiltinBadge /> : <span style={{ color: '#94a3b8', fontSize: 11 }}>custom</span>}</td>
                  <td style={{ padding: '10px 14px' }}>
                    <button
                      data-testid={`toggle-${m.pattern}`}
                      onClick={() => toggle(m)}
                      title={m.attivo ? 'Disattiva' : 'Attiva'}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: m.attivo ? COLORS.primary : '#cbd5e1' }}
                    >
                      {m.attivo ? <ToggleRight size={22} /> : <ToggleLeft size={22} />}
                    </button>
                  </td>
                  <td style={{ padding: '10px 14px' }}>
                    {!m.builtin && (
                      <button
                        data-testid={`btn-del-${m.pattern}`}
                        onClick={() => del(m)}
                        title="Elimina"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: 4 }}
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                    {m.builtin && (
                      <span title="I mittenti builtin non si possono eliminare" style={{ color: '#cbd5e1' }}>
                        <Shield size={14} />
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Legenda routing */}
      <div style={{ marginTop: 20, background: 'white', border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 20 }}>
        <h3 style={{ margin: '0 0 14px', fontSize: 13, fontWeight: 700, color: COLORS.text }}>Routing automatico per tipo documento</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px,1fr))', gap: 10 }}>
          {[
            { tipo: 'fattura_xml',          azione: 'Parser XML → Fatture ricevute' },
            { tipo: 'cedolino',             azione: 'Salva PDF in Documenti' },
            { tipo: 'pagopa',               azione: 'Documento generico / alert' },
            { tipo: 'inps',                 azione: 'Documento generico / alert' },
            { tipo: 'inail',                azione: 'Documento generico / alert' },
            { tipo: 'paypal',               azione: 'Documento generico / alert' },
            { tipo: 'cartella_esattoriale', azione: 'Documento generico + alert' },
          ].map(r => (
            <div key={r.tipo} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <TipoBadge tipo={r.tipo} />
              <span style={{ fontSize: 11, color: COLORS.textMuted, paddingLeft: 4 }}>→ {r.azione}</span>
            </div>
          ))}
        </div>
      </div>

      <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

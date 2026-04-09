import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Mail, Shield, Trash2, Plus, RefreshCw, Download,
  CheckCircle, XCircle, ToggleLeft, ToggleRight, Send
} from 'lucide-react';
import api from '../api';
import { COLORS, STYLES, SPACING } from '../lib/utils';

const TIPI = ['fattura_xml', 'cedolino', 'pagopa', 'inps', 'inail', 'paypal', 'cartella_esattoriale', 'generico'];
const CANALI = ['pec', 'gmail'];

const TIPO_BADGE = {
  fattura_xml:          { bg: '#eff6ff', color: '#2563eb', label: 'Fattura XML' },
  cedolino:             { bg: '#f0fdf4', color: '#16a34a', label: 'Cedolino' },
  pagopa:               { bg: '#fdf4ff', color: '#9333ea', label: 'PagoPA' },
  inps:                 { bg: '#fff7ed', color: '#ea580c', label: 'INPS' },
  inail:                { bg: '#f0f9ff', color: '#0284c7', label: 'INAIL' },
  paypal:               { bg: '#fefce8', color: '#ca8a04', label: 'PayPal' },
  cartella_esattoriale: { bg: '#fef2f2', color: '#dc2626', label: 'Cartella Esatt.' },
  generico:             { bg: COLORS.grayBg, color: COLORS.gray, label: 'Generico' },
};

function TipoBadge({ tipo }) {
  const s = TIPO_BADGE[tipo] || TIPO_BADGE.generico;
  return (
    <span style={{ padding: '2px 10px', borderRadius: 99, fontSize: 11, fontWeight: 700, background: s.bg, color: s.color }}>
      {s.label}
    </span>
  );
}

export default function GestioneEmailMittenti() {
  const [mittenti, setMittenti] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [tab, setTab]           = useState('pec');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm]         = useState({ pattern: '', canale: 'gmail', tipo_documento: 'generico', descrizione: '' });
  const [formSaving, setFormSaving] = useState(false);
  const [syncing, setSyncing]   = useState(false);
  const [syncResult, setSyncResult] = useState(null);
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
    if (!form.pattern.trim()) { alert('Pattern obbligatorio'); return; }
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

  const runSync = async () => {
    setSyncing(true); setSyncResult(null);
    try {
      if (tab === 'pec') {
        const res = await api.post('/api/email-download/pec/download-fatture-sync?since_days=180');
        const s = res.data?.stats || {};
        setSyncResult({ ok: true, msg: `PEC: ${s.xml_found ?? '?'} XML — ${s.new_invoices ?? '?'} fatture nuove` });
      } else {
        const res = await api.post('/api/email-download/sync-email-now');
        setSyncResult({ ok: true, msg: res.data?.message || 'Sync Gmail completato' });
      }
    } catch (e) {
      setSyncResult({ ok: false, msg: e?.response?.data?.detail || 'Errore sync' });
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
    <div style={STYLES.page}>

      {/* Header */}
      <div style={STYLES.header}>
        <div>
          <h2 style={{ margin: 0, fontWeight: 700, fontSize: 20 }}>Gestione Email & Mittenti</h2>
          <p style={{ margin: '4px 0 0', opacity: 0.8, fontSize: 13 }}>
            Mittenti attendibili per PEC e Gmail — routing automatico documenti
          </p>
        </div>
        <button
          data-testid="btn-add-mittente"
          onClick={() => setShowForm(v => !v)}
          style={{ padding: '8px 16px', background: COLORS.white, color: COLORS.primary, border: 'none', borderRadius: 6, fontWeight: 700, fontSize: 13, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
        >
          <Plus size={14} /> Aggiungi mittente
        </button>
      </div>

      {/* KPI */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: SPACING.lg, marginBottom: SPACING.xl }}>
        {[
          { label: 'Totale', value: mittenti.length },
          { label: 'Attivi', value: attivi },
          { label: 'PEC', value: pec },
          { label: 'Gmail', value: gmail },
        ].map(k => (
          <div key={k.label} style={{ ...STYLES.card, padding: `${SPACING.lg}px ${SPACING.xl}px` }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: COLORS.gray, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{k.label}</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.primary, marginTop: 4 }}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* Alert sync */}
      {syncResult && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '12px 16px', borderRadius: 8, marginBottom: SPACING.lg,
          background: syncResult.ok ? '#f0fdf4' : '#fef2f2',
          border: `1px solid ${syncResult.ok ? '#bbf7d0' : '#fecaca'}`,
          color: syncResult.ok ? '#15803d' : '#dc2626', fontSize: 14,
        }}>
          {syncResult.ok ? <CheckCircle size={16} /> : <XCircle size={16} />}
          <span style={{ fontWeight: 600 }}>{syncResult.msg}</span>
          <button onClick={() => setSyncResult(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: COLORS.gray, fontSize: 18 }}>×</button>
        </div>
      )}

      {/* Form nuovo mittente */}
      {showForm && (
        <div style={{ ...STYLES.card, marginBottom: SPACING.xl, background: COLORS.grayBg }}>
          <h3 style={{ margin: `0 0 ${SPACING.lg}px`, fontSize: 14, fontWeight: 700, color: COLORS.primary }}>
            Nuovo mittente personalizzato
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 2fr auto', gap: SPACING.md, alignItems: 'end' }}>
            {[
              { key: 'pattern', label: 'PATTERN', placeholder: 'es. @esempio.it' },
              null, null,
              { key: 'descrizione', label: 'DESCRIZIONE', placeholder: 'Facoltativa' },
            ].map((f, i) => f ? (
              <div key={f.key}>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: COLORS.gray, marginBottom: 4 }}>{f.label}</label>
                <input
                  data-testid={`input-${f.key}`}
                  value={form[f.key]}
                  onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  style={STYLES.input}
                />
              </div>
            ) : i === 1 ? (
              <div key="canale">
                <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: COLORS.gray, marginBottom: 4 }}>CANALE</label>
                <select value={form.canale} onChange={e => setForm(p => ({ ...p, canale: e.target.value }))} style={STYLES.select}>
                  {CANALI.map(c => <option key={c} value={c}>{c.toUpperCase()}</option>)}
                </select>
              </div>
            ) : (
              <div key="tipo">
                <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: COLORS.gray, marginBottom: 4 }}>TIPO DOCUMENTO</label>
                <select value={form.tipo_documento} onChange={e => setForm(p => ({ ...p, tipo_documento: e.target.value }))} style={STYLES.select}>
                  {TIPI.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
            ))}
            <button
              data-testid="btn-salva-mittente"
              onClick={addMittente}
              disabled={formSaving}
              style={{ padding: '10px 18px', background: COLORS.primary, color: COLORS.white, border: 'none', borderRadius: 8, fontWeight: 700, fontSize: 13, cursor: 'pointer' }}
            >
              {formSaving ? 'Salvo…' : 'Salva'}
            </button>
          </div>
        </div>
      )}

      {/* Card principale */}
      <div style={STYLES.card}>
        {/* Tabs */}
        <div style={{ display: 'flex', borderBottom: `2px solid ${COLORS.grayLight}`, marginBottom: SPACING.lg }}>
          {[{ id: 'pec', label: `PEC Aruba (${pec})` }, { id: 'gmail', label: `Gmail (${gmail})` }].map(t => (
            <button key={t.id} onClick={() => { setTab(t.id); setCheckResult(null); }} style={{
              padding: `${SPACING.md}px ${SPACING.xl}px`, background: 'none', border: 'none',
              borderBottom: tab === t.id ? `3px solid ${COLORS.primary}` : '3px solid transparent',
              color: tab === t.id ? COLORS.primary : COLORS.gray,
              fontWeight: tab === t.id ? 700 : 400, cursor: 'pointer', fontSize: 14, marginBottom: -2,
            }}>{t.label}</button>
          ))}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: SPACING.sm }}>
            <button
              data-testid={`btn-sync-${tab}`}
              onClick={runSync}
              disabled={syncing}
              style={{
                padding: '7px 14px', background: syncing ? COLORS.grayLight : COLORS.primary,
                color: syncing ? COLORS.gray : COLORS.white, border: 'none', borderRadius: 6,
                fontSize: 12, fontWeight: 700, cursor: syncing ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', gap: 5
              }}
            >
              {syncing
                ? <><RefreshCw size={12} style={{ animation: 'spin 1s linear infinite' }} /> In corso…</>
                : <><Download size={12} /> {tab === 'pec' ? 'Scarica fatture PEC' : 'Sync Gmail'}</>
              }
            </button>
          </div>
        </div>

        {/* Test check */}
        <div style={{ display: 'flex', gap: SPACING.sm, alignItems: 'center', padding: `${SPACING.sm}px ${SPACING.xs}px`, marginBottom: SPACING.lg, background: COLORS.grayBg, borderRadius: 8 }}>
          <Mail size={14} color={COLORS.gray} />
          <span style={{ fontSize: 12, color: COLORS.gray, fontWeight: 700, whiteSpace: 'nowrap' }}>TEST MITTENTE:</span>
          <input
            data-testid="input-test-check"
            value={checkAddr}
            onChange={e => { setCheckAddr(e.target.value); setCheckResult(null); }}
            onKeyDown={e => e.key === 'Enter' && testCheck()}
            placeholder={tab === 'pec' ? 'es. sdi05@pec.fatturapa.it' : 'es. f.ferrantini@cedolino.it'}
            style={{ ...STYLES.input, fontSize: 12 }}
          />
          <button onClick={testCheck} style={{ padding: '8px 14px', background: COLORS.primary, color: COLORS.white, border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap' }}>
            <Send size={11} /> Verifica
          </button>
          {checkResult && (
            <span style={{
              padding: '4px 12px', borderRadius: 99, fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap',
              background: checkResult.attendibile ? '#dcfce7' : '#fee2e2',
              color: checkResult.attendibile ? '#16a34a' : '#dc2626',
            }}>
              {checkResult.attendibile ? `✓ ${checkResult.tipo_documento}` : '✗ Non attendibile'}
            </span>
          )}
        </div>

        {/* Tabella */}
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: COLORS.gray }}>
            <RefreshCw size={20} style={{ animation: 'spin 1s linear infinite', marginBottom: 8 }} /><br />Caricamento…
          </div>
        ) : filtrati.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: COLORS.gray, fontSize: 14 }}>Nessun mittente per il canale {tab.toUpperCase()}</div>
        ) : (
          <table style={STYLES.table}>
            <thead>
              <tr>
                {['Pattern', 'Tipo documento', 'Descrizione', '', 'Attivo', ''].map(h => (
                  <th key={h} style={STYLES.th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtrati.map((m, i) => (
                <tr key={i} style={{ opacity: m.attivo ? 1 : 0.45 }}>
                  <td style={{ ...STYLES.td, fontFamily: 'monospace', fontWeight: 600, fontSize: 12 }}>{m.pattern}</td>
                  <td style={STYLES.td}><TipoBadge tipo={m.tipo_documento} /></td>
                  <td style={{ ...STYLES.td, color: COLORS.gray, fontSize: 12 }}>{m.descrizione || '—'}</td>
                  <td style={STYLES.td}>
                    {m.builtin
                      ? <span style={{ fontSize: 10, fontWeight: 700, color: COLORS.gray, background: COLORS.grayLight, padding: '2px 7px', borderRadius: 99 }}>builtin</span>
                      : <span style={{ fontSize: 10, color: COLORS.gray }}>custom</span>
                    }
                  </td>
                  <td style={STYLES.td}>
                    <button data-testid={`toggle-${m.pattern}`} onClick={() => toggle(m)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: m.attivo ? COLORS.primary : COLORS.grayLight }}>
                      {m.attivo ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
                    </button>
                  </td>
                  <td style={STYLES.td}>
                    {m.builtin
                      ? <Shield size={14} color={COLORS.grayLight} title="Non eliminabile" />
                      : <button data-testid={`btn-del-${m.pattern}`} onClick={() => del(m)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: COLORS.danger, padding: 4 }}>
                          <Trash2 size={14} />
                        </button>
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Legenda routing */}
      <div style={{ ...STYLES.card, marginTop: SPACING.xl }}>
        <h3 style={{ margin: `0 0 ${SPACING.lg}px`, fontSize: 14, fontWeight: 700, color: COLORS.primary }}>
          Routing automatico per tipo documento
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px,1fr))', gap: SPACING.md }}>
          {[
            { tipo: 'fattura_xml',          azione: 'Parser XML → Fatture ricevute' },
            { tipo: 'cedolino',             azione: 'Salva PDF in Documenti' },
            { tipo: 'pagopa',               azione: 'Documento generico / alert' },
            { tipo: 'inps',                 azione: 'Comunicazione INPS' },
            { tipo: 'inail',                azione: 'Comunicazione INAIL' },
            { tipo: 'paypal',               azione: 'Ricevuta PayPal' },
            { tipo: 'cartella_esattoriale', azione: 'Alert urgente + salvataggio' },
          ].map(r => (
            <div key={r.tipo} style={{ display: 'flex', flexDirection: 'column', gap: 5, padding: SPACING.sm, background: COLORS.grayBg, borderRadius: 6 }}>
              <TipoBadge tipo={r.tipo} />
              <span style={{ fontSize: 11, color: COLORS.gray, paddingLeft: 2 }}>→ {r.azione}</span>
            </div>
          ))}
        </div>
      </div>

      <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

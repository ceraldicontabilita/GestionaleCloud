import React, { useState, useEffect, useCallback } from 'react';
import { useHashState } from '../hooks/useHashState';
import api from '../api';
import { COLORS, STYLES, button, badge } from '../lib/utils';
import { PageLayout, PageSection, PageEmpty, PageLoading } from '../components/PageLayout';

// ---- costanti ----
const TIPO_CFG = {
  urgente:     { label: 'URGENTE',    badgeType: 'danger'  },
  anomalia:    { label: 'ANOMALIA',   badgeType: 'danger'  },
  avviso:      { label: 'AVVISO',     badgeType: 'warning' },
  info:        { label: 'INFO',       badgeType: 'info'    },
  suggerimento:{ label: 'SUGGERIM.',  badgeType: 'success' },
};

const STATI_CFG = {
  completato:    { color: COLORS.success, label: 'Attivo',        icon: '●' },
  errore:        { color: COLORS.danger,  label: 'Errore',        icon: '●' },
  in_esecuzione: { color: COLORS.warning, label: 'In esecuzione', icon: '◐' },
};

function formatTs(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('it-IT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch { return iso; }
}

// ---- AGENTE CARD ----
function AgenteCard({ agente, onRun }) {
  const s = STATI_CFG[agente.stato] || { color: COLORS.gray, label: agente.stato || '?', icon: '●' };
  return (
    <div style={{ ...STYLES.card, display: 'flex', alignItems: 'center', gap: 16 }}>
      <div style={{
        width: 48, height: 48, borderRadius: 12,
        background: COLORS.primary,
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#7dd3fc" strokeWidth="2">
          <circle cx="12" cy="12" r="3"/>
          <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/>
        </svg>
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 700, fontSize: 14, color: '#0f172a', marginBottom: 4 }}>{agente.agente}</div>
        <div style={{ fontSize: 12, color: COLORS.gray }}>Ultima: {formatTs(agente.ultima_esecuzione)}</div>
        {agente.ultimo_errore && (
          <div style={{ fontSize: 11, color: COLORS.danger, marginTop: 4 }}>{agente.ultimo_errore}</div>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 13, color: s.color, fontWeight: 600 }}>{s.icon} {s.label}</span>
        <button onClick={() => onRun(agente.agente)} style={button('secondary')} data-testid={`btn-run-${agente.agente}`}>
          Esegui ora
        </button>
      </div>
    </div>
  );
}

// ---- SEGNALAZIONE CARD ----
function SegnalazioneCard({ s, onRisolvi }) {
  const c = TIPO_CFG[s.tipo] || TIPO_CFG.info;
  return (
    <div style={{
      ...STYLES.card,
      marginBottom: 10,
      opacity: s.risolta ? 0.55 : 1,
      borderLeft: `4px solid ${s.risolta ? COLORS.grayLight : (s.tipo === 'urgente' || s.tipo === 'anomalia' ? COLORS.danger : s.tipo === 'avviso' ? COLORS.warning : s.tipo === 'suggerimento' ? COLORS.success : COLORS.info)}`,
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 8 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
            <span style={badge(c.badgeType)}>{c.label}</span>
            <span style={{ fontSize: 11, color: COLORS.gray }}>{s.agente}</span>
            <span style={{ fontSize: 11, color: '#cbd5e1' }}>{formatTs(s.created_at)}</span>
          </div>
          <p style={{ margin: 0, fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{s.titolo}</p>
        </div>
      </div>
      <p style={{ margin: '0 0 8px 0', fontSize: 12, color: '#475569', lineHeight: 1.7 }}>{s.descrizione}</p>
      {s.azione_suggerita && (
        <div style={{ fontSize: 11, color: COLORS.info, fontWeight: 600, background: '#e0f2fe', padding: '4px 8px', borderRadius: 4, marginBottom: 8 }}>
          Azione: {s.azione_suggerita}
        </div>
      )}
      {!s.risolta && (
        <button onClick={() => onRisolvi(s.id)} style={{ ...button('secondary'), fontSize: 12, padding: '4px 12px' }}>
          Segna risolto
        </button>
      )}
    </div>
  );
}

// ---- PATTERN CARD ----
function PatternCard({ p }) {
  const pct = Math.round((p.confidenza || 0) * 100);
  const pColor = pct >= 70 ? COLORS.success : pct >= 40 ? COLORS.warning : COLORS.gray;
  return (
    <div style={{ ...STYLES.card, marginBottom: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={badge('info')}>{p.categoria}</span>
        <span style={{ fontSize: 11, color: COLORS.gray }}>{p.occorrenze || 1} occorrenze</span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{p.chiave}</div>
          <div style={{ fontSize: 12, color: COLORS.gray, fontStyle: 'italic' }}>{String(p.valore).slice(0, 100)}</div>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0, marginLeft: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: pColor }}>{pct}%</div>
          <div style={{ width: 60, height: 4, background: COLORS.grayLight, borderRadius: 2, marginTop: 4 }}>
            <div style={{ width: `${pct}%`, height: '100%', background: pColor, borderRadius: 2 }} />
          </div>
        </div>
      </div>
    </div>
  );
}

// ---- PAGINA PRINCIPALE ----
export default function AgentiPage() {
  const [hs, setHs] = useHashState({ tab: 'agenti' });
  const activeTab = hs.tab;
  const setActiveTab = (t) => setHs('tab', t);
  const [stati, setStati] = useState([]);
  const [segnalazioni, setSegnalazioni] = useState([]);
  const [pattern, setPattern] = useState([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState('');

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [statiRes, segnRes] = await Promise.all([
        api.get('/api/agenti/stato'),
        api.get('/api/agenti/segnalazioni?limit=100'),
      ]);
      setStati(statiRes.data.agenti || []);
      setSegnalazioni(segnRes.data.segnalazioni || []);
    } catch { setMsg('Errore caricamento dati agenti'); }
    finally { setLoading(false); }
  }, []);

  const loadPattern = useCallback(async () => {
    try {
      const res = await api.get('/api/agenti/pattern-appresi');
      setPattern(res.data.pattern || []);
    } catch { /* silenzioso */ }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);
  useEffect(() => { if (activeTab === 'pattern') loadPattern(); }, [activeTab, loadPattern]);

  const eseguiOra = async () => {
    setRunning(true); setMsg('');
    try {
      await api.post('/api/agenti/run');
      setMsg('Agenti eseguiti con successo!');
      await loadAll();
    } catch { setMsg('Errore durante esecuzione agenti'); }
    finally { setRunning(false); }
  };

  const risolviSegnalazione = async (id) => {
    try {
      await api.put(`/api/agenti/segnalazioni/${id}/risolta`);
      setSegnalazioni(prev => prev.map(s => s.id === id ? { ...s, risolta: true } : s));
    } catch { /* silenzioso */ }
  };

  const segnPerTipo = (tipo) => segnalazioni.filter(s => s.tipo === tipo && !s.risolta);
  const urgenti = segnPerTipo('urgente').length + segnPerTipo('anomalia').length;

  const TABS = [
    { key: 'agenti',       label: `Agenti (${stati.length})` },
    { key: 'urgente',      label: `Urgenti (${urgenti})`,                    alert: urgenti > 0 },
    { key: 'avviso',       label: `Avvisi (${segnPerTipo('avviso').length})` },
    { key: 'info',         label: `Info (${segnPerTipo('info').length})` },
    { key: 'suggerimento', label: `Suggerimenti (${segnPerTipo('suggerimento').length})` },
    { key: 'pattern',      label: 'Pattern appresi' },
  ];

  return (
    <PageLayout>
      {/* HEADER */}
      <div style={STYLES.header}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#fff' }}>
            🤖 Agenti AI
          </h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'rgba(255,255,255,0.75)' }}>
            Monitor, segnalazioni e pattern appresi dal sistema di intelligenza automatica
          </p>
        </div>
        <button
          data-testid="btn-run-all-agenti"
          onClick={eseguiOra}
          disabled={running}
          style={button('primary', running)}
        >
          {running ? '⏳ Esecuzione...' : '▶ Esegui tutti ora'}
        </button>
      </div>

      {msg && (
        <div style={{
          padding: '10px 16px', borderRadius: 8, marginBottom: 16, fontSize: 13,
          background: msg.includes('Errore') ? '#fef2f2' : '#f0fdf4',
          border: `1px solid ${msg.includes('Errore') ? COLORS.danger : COLORS.success}`,
          color: msg.includes('Errore') ? COLORS.danger : COLORS.success,
        }}>
          {msg}
        </div>
      )}

      {/* TAB BAR */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16, background: '#f1f5f9', borderRadius: 10, padding: 4 }}>
        {TABS.map(t => (
          <button
            key={t.key}
            data-testid={`tab-agenti-${t.key}`}
            onClick={() => setActiveTab(t.key)}
            style={{
              flex: 1, padding: '8px 4px', border: 'none', borderRadius: 8, cursor: 'pointer',
              fontSize: 13, fontWeight: activeTab === t.key ? 700 : 500,
              background: activeTab === t.key ? COLORS.white : 'transparent',
              color: activeTab === t.key ? COLORS.primary : COLORS.gray,
              boxShadow: activeTab === t.key ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              position: 'relative',
            }}
          >
            {t.label}
            {t.alert && (
              <span style={{ position: 'absolute', top: 4, right: 8, width: 6, height: 6, borderRadius: '50%', background: COLORS.danger }} />
            )}
          </button>
        ))}
      </div>

      {/* CONTENUTO TAB */}
      {loading ? <PageLoading /> : (
        <>
          {activeTab === 'agenti' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {stati.length === 0
                ? <PageEmpty icon="🤖" message="Nessun agente registrato. Esegui gli agenti per inizializzare i dati." />
                : stati.map(a => <AgenteCard key={a.agente} agente={a} onRun={eseguiOra} />)
              }
            </div>
          )}

          {activeTab === 'urgente' && (
            <div>
              {urgenti === 0
                ? <PageEmpty icon="🛡️" message="Nessuna segnalazione urgente — tutto in ordine" />
                : [...segnPerTipo('urgente'), ...segnPerTipo('anomalia')].map(s =>
                    <SegnalazioneCard key={s.id} s={s} onRisolvi={risolviSegnalazione} />)
              }
            </div>
          )}

          {activeTab === 'avviso' && (
            <div>
              {segnPerTipo('avviso').length === 0
                ? <PageEmpty icon="✅" message="Nessun avviso attivo" />
                : segnPerTipo('avviso').map(s => <SegnalazioneCard key={s.id} s={s} onRisolvi={risolviSegnalazione} />)
              }
            </div>
          )}

          {activeTab === 'info' && (
            <div>
              {segnPerTipo('info').length === 0
                ? <PageEmpty message="Nessuna informazione" />
                : segnPerTipo('info').map(s => <SegnalazioneCard key={s.id} s={s} onRisolvi={risolviSegnalazione} />)
              }
            </div>
          )}

          {activeTab === 'suggerimento' && (
            <div>
              {segnPerTipo('suggerimento').length === 0
                ? <PageEmpty message="Nessun suggerimento" />
                : segnPerTipo('suggerimento').map(s => <SegnalazioneCard key={s.id} s={s} onRisolvi={risolviSegnalazione} />)
              }
            </div>
          )}

          {activeTab === 'pattern' && (
            <div>
              {pattern.length === 0
                ? <PageEmpty icon="🧠" message="Nessun pattern appreso. La Learning Machine impara dalle tue azioni nel tempo." />
                : (
                  <>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
                      {Array.from(new Set(pattern.map(p => p.categoria))).map(cat => (
                        <span key={cat} style={badge('info')}>{cat}</span>
                      ))}
                    </div>
                    {pattern.map(p => <PatternCard key={p.id || p.chiave} p={p} />)}
                  </>
                )
              }
            </div>
          )}
        </>
      )}
    </PageLayout>
  );
}

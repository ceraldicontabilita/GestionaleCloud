import React, { useState, useEffect, useCallback } from 'react';
import { useHashState } from '../hooks/useHashState';
import { CopyLinkButton } from '../components/CopyLinkButton';
import { useAuth } from '../contexts/AuthContext';
import { useConfirm } from '../components/ui/ConfirmDialog';
import api from '../api';
import { COLORS, STYLES, button, badge, formatEuro } from '../lib/utils';
import { PageLayout, PageSection, PageEmpty, PageLoading } from '../components/PageLayout';

// ---- costanti ----
const TIPO_CFG = {
  urgente: { label: 'URGENTE', badgeType: 'danger' },
  anomalia: { label: 'ANOMALIA', badgeType: 'danger' },
  avviso: { label: 'AVVISO', badgeType: 'warning' },
  info: { label: 'INFO', badgeType: 'info' },
  suggerimento: { label: 'SUGGERIM.', badgeType: 'success' },
};

const STATI_CFG = {
  completato: { color: COLORS.success, label: 'Attivo', icon: '●' },
  errore: { color: COLORS.danger, label: 'Errore', icon: '●' },
  in_esecuzione: { color: COLORS.warning, label: 'In esecuzione', icon: '◐' },
};

function formatTs(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).replaceAll('/', '-');
  } catch {
    return iso;
  }
}

// ---- AGENTE CARD ----
function AgenteCard({ agente, onRun }) {
  const s = STATI_CFG[agente.stato] || {
    color: COLORS.gray,
    label: agente.stato || '?',
    icon: '●',
  };
  return (
    <div style={{ ...STYLES.card, display: 'flex', alignItems: 'center', gap: 16 }}>
      <div
        style={{
          width: 48,
          height: 48,
          borderRadius: 12,
          background: COLORS.primary,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <svg
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#7dd3fc"
          strokeWidth="2"
        >
          <circle cx="12" cy="12" r="3" />
          <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" />
        </svg>
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 700, fontSize: 14, color: '#0f172a', marginBottom: 4 }}>
          {agente.agente}
        </div>
        <div style={{ fontSize: 12, color: COLORS.gray }}>
          Ultima: {formatTs(agente.ultima_esecuzione)}
        </div>
        {agente.ultimo_errore && (
          <div style={{ fontSize: 11, color: COLORS.danger, marginTop: 4 }}>
            {agente.ultimo_errore}
          </div>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 13, color: s.color, fontWeight: 600 }}>
          {s.icon} {s.label}
        </span>
        <button
          onClick={() => onRun(agente.agente)}
          style={button('secondary')}
          data-testid={`btn-run-${agente.agente}`}
        >
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
    <div
      style={{
        ...STYLES.card,
        marginBottom: 10,
        opacity: s.risolta ? 0.55 : 1,
        borderLeft: `4px solid ${s.risolta ? COLORS.grayLight : s.tipo === 'urgente' || s.tipo === 'anomalia' ? COLORS.danger : s.tipo === 'avviso' ? COLORS.warning : s.tipo === 'suggerimento' ? COLORS.success : COLORS.info}`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 8 }}>
        <div style={{ flex: 1 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              flexWrap: 'wrap',
              marginBottom: 4,
            }}
          >
            <span style={badge(c.badgeType)}>{c.label}</span>
            <span style={{ fontSize: 11, color: COLORS.gray }}>{s.agente}</span>
            <span style={{ fontSize: 11, color: '#cbd5e1' }}>{formatTs(s.created_at)}</span>
          </div>
          <p style={{ margin: 0, fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{s.titolo}</p>
        </div>
      </div>
      <p style={{ margin: '0 0 8px 0', fontSize: 12, color: '#475569', lineHeight: 1.7 }}>
        {s.descrizione}
      </p>
      {s.azione_suggerita && (
        <div
          style={{
            fontSize: 11,
            color: COLORS.info,
            fontWeight: 600,
            background: '#e0f2fe',
            padding: '4px 8px',
            borderRadius: 4,
            marginBottom: 8,
          }}
        >
          Azione: {s.azione_suggerita}
        </div>
      )}
      {!s.risolta && (
        <button
          onClick={() => onRisolvi(s.id)}
          style={{ ...button('secondary'), fontSize: 12, padding: '4px 12px' }}
        >
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
          <div style={{ fontSize: 12, color: COLORS.gray, fontStyle: 'italic' }}>
            {String(p.valore).slice(0, 100)}
          </div>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0, marginLeft: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: pColor }}>{pct}%</div>
          <div
            style={{
              width: 60,
              height: 4,
              background: COLORS.grayLight,
              borderRadius: 2,
              marginTop: 4,
            }}
          >
            <div
              style={{ width: `${pct}%`, height: '100%', background: pColor, borderRadius: 2 }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

const STATO_DECISIONE = {
  observed: 'Osservata',
  proposed: 'Proposta',
  pending_approval: 'Attende approvazione',
  ready_l2: 'Pronta L2 (non eseguita)',
  approved_pending_execution: 'Approvata, non ancora eseguita',
  rejected: 'Rifiutata',
  blocked: 'Bloccata',
  suspended: 'Sospesa',
  superseded: 'Superata da una versione piu recente',
};

function etichettaFonte(fonte) {
  if (!fonte || typeof fonte !== 'object') return 'Fonte applicativa';
  if (fonte.type === 'typed_service') return `Servizio verificato: ${fonte.service || 'applicativo'}`;
  if (fonte.type === 'agent_signal') return 'Segnalazione prodotta da un agente';
  return fonte.service || fonte.type || 'Fonte applicativa';
}

function DecisioneCard({ decisione, isAdmin, onDecisione }) {
  const inAttesa = decisione.execution_status === 'pending_approval';
  const rischio = decisione.risk_level || 'low';
  const badgeRischio = rischio === 'critical' || rischio === 'high'
    ? 'danger'
    : rischio === 'medium' ? 'warning' : 'success';
  const azione = decisione.recommended_action?.description
    || decisione.recommended_action?.type
    || 'Nessuna azione operativa';

  return (
    <div style={{ ...STYLES.card, marginBottom: 10, borderLeft: `4px solid ${inAttesa ? COLORS.warning : COLORS.info}` }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 260px' }}>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 7 }}>
            <span style={badge('info')}>{decisione.autonomy_level || 'L1'}</span>
            <span style={badge(badgeRischio)}>Rischio {rischio}</span>
            <span style={badge(inAttesa ? 'warning' : 'info')}>
              {STATO_DECISIONE[decisione.execution_status] || decisione.execution_status}
            </span>
            <span style={badge('info')}>Versione {decisione.version || 1}</span>
            {(decisione.occurrence_count || 1) > 1 && (
              <span style={badge('success')}>{decisione.occurrence_count} rilevazioni</span>
            )}
            {(decisione.versioni_storiche || 0) > 0 && (
              <span style={badge('warning')}>
                {decisione.versioni_storiche} versioni precedenti
              </span>
            )}
          </div>
          <div style={{ fontWeight: 700, fontSize: 14, color: '#0f172a' }}>
            {decisione.objective}
          </div>
          <div style={{ fontSize: 11, color: COLORS.gray, marginTop: 3 }}>
            {decisione.agent} · {formatTs(decisione.timestamp)} · Confidenza {Math.round((decisione.confidence || 0) * 100)}%
          </div>
        </div>
        <div style={{ fontWeight: 700, color: Math.abs(decisione.financial_impact || 0) > 0 ? COLORS.warning : COLORS.gray }}>
          Impatto {formatEuro(decisione.financial_impact || 0)}
        </div>
      </div>
      {decisione.explanation && (
        <p style={{ fontSize: 12, color: '#475569', lineHeight: 1.6, margin: '10px 0 6px' }}>
          {decisione.explanation}
        </p>
      )}
      <div style={{ fontSize: 12, background: '#f8fafc', padding: '8px 10px', borderRadius: 6 }}>
        <strong>Azione proposta:</strong> {azione}
      </div>
      {decisione.policy_reasons?.length > 0 && (
        <div style={{ fontSize: 11, color: COLORS.gray, marginTop: 7 }}>
          Policy: {decisione.policy_reasons.join(', ')}
        </div>
      )}
      <details style={{ marginTop: 9, fontSize: 12, color: '#475569' }}>
        <summary style={{ cursor: 'pointer', fontWeight: 700, color: COLORS.primary }}>
          Fonti, regole e approvazione
        </summary>
        <div style={{ marginTop: 8, display: 'grid', gap: 5 }}>
          <div>
            <strong>Fonti autorizzate:</strong>{' '}
            {decisione.input_sources?.length
              ? decisione.input_sources.map(etichettaFonte).join('; ')
              : 'non dichiarate'}
          </div>
          <div>
            <strong>Regole applicate:</strong>{' '}
            {decisione.rule_ids?.length ? decisione.rule_ids.join(', ') : 'nessuna regola dichiarata'}
          </div>
          <div><strong>Ruolo approvatore:</strong> {decisione.approver_role || 'admin'}</div>
          {decisione.approved_by && (
            <div>
              <strong>Approvata da:</strong> {decisione.approved_by} · {formatTs(decisione.approved_at)}
            </div>
          )}
          {decisione.rejected_by && (
            <div>
              <strong>Rifiutata da:</strong> {decisione.rejected_by} · {formatTs(decisione.rejected_at)}
            </div>
          )}
          {decisione.approval_note && (
            <div><strong>Nota:</strong> {decisione.approval_note}</div>
          )}
        </div>
      </details>
      {inAttesa && isAdmin && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
          <button style={button('primary')} onClick={() => onDecisione(decisione, true)}>
            Approva proposta
          </button>
          <button style={button('danger')} onClick={() => onDecisione(decisione, false)}>
            Rifiuta
          </button>
          <span style={{ fontSize: 11, color: COLORS.gray, alignSelf: 'center' }}>
            L'approvazione non esegue l'azione.
          </span>
        </div>
      )}
    </div>
  );
}

function CashFlowPanel({ previsione }) {
  if (!previsione?.scenari?.length) {
    return <PageEmpty message="Previsione non ancora disponibile." />;
  }
  const qualita = previsione.qualita_dati || {};
  return (
    <div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
        <div style={{ ...STYLES.card, flex: '1 1 180px' }}>
          <div style={{ fontSize: 12, color: COLORS.gray }}>Liquidità iniziale</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: COLORS.primary }}>
            {formatEuro(previsione.liquidita_iniziale || 0)}
          </div>
        </div>
        <div style={{ ...STYLES.card, flex: '1 1 180px' }}>
          <div style={{ fontSize: 12, color: COLORS.gray }}>Copertura dati</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: COLORS.info }}>
            {qualita.copertura_percentuale ?? 0}%
          </div>
        </div>
        <div style={{ ...STYLES.card, flex: '1 1 180px' }}>
          <div style={{ fontSize: 12, color: COLORS.gray }}>Record esclusi</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: qualita.record_esclusi ? COLORS.warning : COLORS.success }}>
            {qualita.record_esclusi || 0}
          </div>
        </div>
      </div>
      {previsione.scenari.map(scenario => (
        <PageSection key={scenario.nome} title={`Scenario ${scenario.nome}`}>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12, marginBottom: 10 }}>
            <span><strong>Saldo minimo:</strong> {formatEuro(scenario.saldo_minimo)}</span>
            <span><strong>Saldo finale:</strong> {formatEuro(scenario.saldo_finale)}</span>
            <span>Entrate {Math.round(scenario.fattore_entrate * 100)}% · Uscite {Math.round(scenario.fattore_uscite * 100)}%</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', minWidth: 720, borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: '#f8fafc', textAlign: 'left' }}>
                  {['Settimana', 'Periodo', 'Entrate', 'Uscite', 'Saldo finale'].map(label => (
                    <th key={label} style={{ padding: 8, borderBottom: '1px solid #e2e8f0' }}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {scenario.settimane.map(riga => (
                  <tr key={riga.settimana}>
                    <td style={{ padding: 8, borderBottom: '1px solid #f1f5f9' }}>{riga.settimana}</td>
                    <td style={{ padding: 8, borderBottom: '1px solid #f1f5f9' }}>{riga.dal} – {riga.al}</td>
                    <td style={{ padding: 8, borderBottom: '1px solid #f1f5f9', color: COLORS.success }}>{formatEuro(riga.entrate)}</td>
                    <td style={{ padding: 8, borderBottom: '1px solid #f1f5f9', color: COLORS.danger }}>{formatEuro(riga.uscite)}</td>
                    <td style={{ padding: 8, borderBottom: '1px solid #f1f5f9', fontWeight: 700, color: riga.saldo_finale < 0 ? COLORS.danger : '#0f172a' }}>
                      {formatEuro(riga.saldo_finale)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </PageSection>
      ))}
      <div style={{ ...STYLES.card, fontSize: 12, color: COLORS.gray }}>
        <strong>Regola {previsione.versione_regole}</strong>. Previsione informativa e di sola lettura:
        non prepara né esegue pagamenti. I record senza data o importo non vengono stimati.
      </div>
    </div>
  );
}

// ---- PAGINA PRINCIPALE ----
export default function AgentiPage() {
  const confirm = useConfirm();
  const { isAdmin } = useAuth();
  const [hs, setHs] = useHashState({ tab: 'agenti' });
  const activeTab = hs.tab;
  const setActiveTab = t => setHs('tab', t);
  const [stati, setStati] = useState([]);
  const [segnalazioni, setSegnalazioni] = useState([]);
  const [pattern, setPattern] = useState([]);
  const [decisioni, setDecisioni] = useState([]);
  const [cashFlow, setCashFlow] = useState(null);
  const [automazioni, setAutomazioni] = useState({ sospese: false, modalita: 'shadow' });
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState('');

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [statiRes, segnRes, decisioniRes, automazioniRes, cashFlowRes] = await Promise.all([
        api.get('/api/agenti/stato'),
        api.get('/api/agenti/segnalazioni?limit=100'),
        api.get('/api/agenti/decisioni?limit=100'),
        api.get('/api/agenti/automazioni/stato'),
        api.get('/api/agenti/cash-flow-13-settimane'),
      ]);
      setStati(statiRes.data.agenti || []);
      setSegnalazioni(segnRes.data.segnalazioni || []);
      setDecisioni(decisioniRes.data.decisioni || []);
      setAutomazioni(automazioniRes.data || { sospese: false, modalita: 'shadow' });
      setCashFlow(cashFlowRes.data || null);
    } catch {
      setMsg('Errore caricamento dati agenti');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadPattern = useCallback(async () => {
    try {
      const res = await api.get('/api/agenti/pattern-appresi');
      setPattern(res.data.pattern || []);
    } catch {
      /* silenzioso */
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);
  useEffect(() => {
    if (activeTab === 'pattern') loadPattern();
  }, [activeTab, loadPattern]);

  const eseguiOra = async agenteNome => {
    setRunning(true);
    setMsg('');
    try {
      const params = agenteNome ? `?agente=${encodeURIComponent(agenteNome)}` : '';
      await api.post(`/api/agenti/run${params}`);
      setMsg(agenteNome ? `Agente ${agenteNome} eseguito con successo!` : 'Agenti eseguiti con successo!');
      await loadAll();
    } catch {
      setMsg('Errore durante esecuzione agenti');
    } finally {
      setRunning(false);
    }
  };

  const risolviSegnalazione = async id => {
    try {
      await api.put(`/api/agenti/segnalazioni/${id}/risolta`);
      setSegnalazioni(prev => prev.map(s => (s.id === id ? { ...s, risolta: true } : s)));
    } catch {
      /* silenzioso */
    }
  };

  const gestisciDecisione = async (decisione, approva) => {
    const ok = await confirm({
      title: approva ? 'Approva la proposta' : 'Rifiuta la proposta',
      message: approva
        ? 'La proposta sarà marcata come approvata, ma non verrà eseguita automaticamente.'
        : 'La proposta verrà rifiutata e resterà nello storico decisionale.',
      variant: approva ? 'warning' : 'danger',
    });
    if (!ok) return;
    try {
      await api.post(`/api/agenti/decisioni/${decisione.decision_id}/${approva ? 'approva' : 'rifiuta'}`, {});
      setMsg(approva ? 'Proposta approvata, in attesa di esecuzione separata.' : 'Proposta rifiutata.');
      await loadAll();
    } catch (error) {
      setMsg(error.response?.data?.detail || 'Errore durante la gestione della proposta');
    }
  };

  const cambiaAutomazioni = async sospendi => {
    const ok = await confirm({
      title: sospendi ? 'Ferma tutte le automazioni AI' : 'Riprendi le automazioni AI',
      message: sospendi
        ? 'Gli agenti programmati verranno fermati. Il registro e la consultazione resteranno disponibili.'
        : 'Gli agenti torneranno a osservare e creare proposte in modalità shadow.',
      variant: sospendi ? 'danger' : 'warning',
    });
    if (!ok) return;
    try {
      await api.post(`/api/agenti/automazioni/${sospendi ? 'ferma' : 'riprendi'}`);
      setMsg(sospendi ? 'Automazioni AI fermate.' : 'Automazioni AI riprese in modalità shadow.');
      await loadAll();
    } catch (error) {
      setMsg(error.response?.data?.detail || 'Errore durante il cambio di stato delle automazioni');
    }
  };

  const segnPerTipo = tipo => segnalazioni.filter(s => s.tipo === tipo && !s.risolta);
  const urgenti = segnPerTipo('urgente').length + segnPerTipo('anomalia').length;

  const TABS = [
    { key: 'agenti', label: `Agenti (${stati.length})` },
    { key: 'decisioni', label: `Decisioni (${decisioni.length})` },
    { key: 'cash-flow', label: 'Cash flow 13 settimane' },
    { key: 'urgente', label: `Urgenti (${urgenti})`, alert: urgenti > 0 },
    { key: 'avviso', label: `Avvisi (${segnPerTipo('avviso').length})` },
    { key: 'info', label: `Info (${segnPerTipo('info').length})` },
    { key: 'suggerimento', label: `Suggerimenti (${segnPerTipo('suggerimento').length})` },
    { key: 'pattern', label: 'Pattern appresi' },
  ];

  return (
    <PageLayout>
      {/* HEADER */}
      <div style={STYLES.header}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#fff' }}>🤖 Agenti AI</h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'rgba(255,255,255,0.75)' }}>
            Monitor, segnalazioni e pattern appresi dal sistema di intelligenza automatica
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <span style={{ ...badge(automazioni.sospese ? 'danger' : 'success'), alignSelf: 'center' }}>
            {automazioni.sospese ? 'Automazioni ferme' : 'Modalità shadow'}
          </span>
          {isAdmin && (
            <button
              data-testid="btn-stop-automazioni"
              onClick={() => cambiaAutomazioni(!automazioni.sospese)}
              style={button(automazioni.sospese ? 'secondary' : 'danger')}
            >
              {automazioni.sospese ? 'Riprendi automazioni' : 'Ferma automazioni'}
            </button>
          )}
        <button
          data-testid="btn-run-all-agenti"
          onClick={() => eseguiOra()}
          disabled={running || automazioni.sospese}
          style={button('primary', running || automazioni.sospese)}
        >
          {running ? '⏳ Esecuzione...' : '▶ Esegui tutti ora'}
        </button>
        </div>
      </div>

      {msg && (
        <div
          style={{
            padding: '10px 16px',
            borderRadius: 8,
            marginBottom: 16,
            fontSize: 13,
            background: msg.includes('Errore') ? '#fef2f2' : '#f0fdf4',
            border: `1px solid ${msg.includes('Errore') ? COLORS.danger : COLORS.success}`,
            color: msg.includes('Errore') ? COLORS.danger : COLORS.success,
          }}
        >
          {msg}
        </div>
      )}

      {/* TAB BAR */}
      <div
        style={{
          display: 'flex',
          gap: 4,
          marginBottom: 16,
          background: '#f1f5f9',
          borderRadius: 10,
          padding: 4,
          alignItems: 'center',
          flexWrap: 'wrap',
        }}
      >
        {TABS.map(t => (
          <button
            key={t.key}
            data-testid={`tab-agenti-${t.key}`}
            onClick={() => setActiveTab(t.key)}
            style={{
              flex: '1 1 auto',
              minWidth: 80,
              padding: '8px 4px',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: activeTab === t.key ? 700 : 500,
              background: activeTab === t.key ? COLORS.white : 'transparent',
              color: activeTab === t.key ? COLORS.primary : COLORS.gray,
              boxShadow: activeTab === t.key ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              position: 'relative',
            }}
          >
            {t.label}
            {t.alert && (
              <span
                style={{
                  position: 'absolute',
                  top: 4,
                  right: 8,
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: COLORS.danger,
                }}
              />
            )}
          </button>
        ))}
        <CopyLinkButton style={{ flexShrink: 0, marginLeft: 4 }} />
      </div>

      {/* CONTENUTO TAB */}
      {loading ? (
        <PageLoading />
      ) : (
        <>
          {activeTab === 'agenti' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {stati.length === 0 ? (
                <PageEmpty
                  icon="🤖"
                  message="Nessun agente registrato. Esegui gli agenti per inizializzare i dati."
                />
              ) : (
                stati.map(a => <AgenteCard key={a.agente} agente={a} onRun={eseguiOra} />)
              )}
            </div>
          )}

          {activeTab === 'decisioni' && (
            <div>
              <PageSection title="Registro decisionale supervisionato">
                <div style={{ fontSize: 12, color: COLORS.gray, marginBottom: 12 }}>
                  Gli agenti osservano e propongono. Pagamenti, registrazioni contabili, invii fiscali,
                  cancellazioni e operazioni economiche non vengono mai eseguiti da questa schermata.
                </div>
                {decisioni.length === 0 ? (
                  <PageEmpty message="Nessuna decisione registrata. Esegui gli agenti per generare osservazioni e proposte." />
                ) : (
                  decisioni.map(d => (
                    <DecisioneCard
                      key={d.decision_id}
                      decisione={d}
                      isAdmin={isAdmin}
                      onDecisione={gestisciDecisione}
                    />
                  ))
                )}
              </PageSection>
            </div>
          )}

          {activeTab === 'cash-flow' && <CashFlowPanel previsione={cashFlow} />}

          {activeTab === 'urgente' && (
            <div>
              {urgenti === 0 ? (
                <PageEmpty icon="🛡️" message="Nessuna segnalazione urgente — tutto in ordine" />
              ) : (
                [...segnPerTipo('urgente'), ...segnPerTipo('anomalia')].map(s => (
                  <SegnalazioneCard key={s.id} s={s} onRisolvi={risolviSegnalazione} />
                ))
              )}
            </div>
          )}

          {activeTab === 'avviso' && (
            <div>
              {segnPerTipo('avviso').length === 0 ? (
                <PageEmpty icon="✅" message="Nessun avviso attivo" />
              ) : (
                segnPerTipo('avviso').map(s => (
                  <SegnalazioneCard key={s.id} s={s} onRisolvi={risolviSegnalazione} />
                ))
              )}
            </div>
          )}

          {activeTab === 'info' && (
            <div>
              {segnPerTipo('info').length === 0 ? (
                <PageEmpty message="Nessuna informazione" />
              ) : (
                segnPerTipo('info').map(s => (
                  <SegnalazioneCard key={s.id} s={s} onRisolvi={risolviSegnalazione} />
                ))
              )}
            </div>
          )}

          {activeTab === 'suggerimento' && (
            <div>
              {segnPerTipo('suggerimento').length === 0 ? (
                <PageEmpty message="Nessun suggerimento" />
              ) : (
                segnPerTipo('suggerimento').map(s => (
                  <SegnalazioneCard key={s.id} s={s} onRisolvi={risolviSegnalazione} />
                ))
              )}
            </div>
          )}

          {activeTab === 'pattern' && (
            <div>
              {pattern.length === 0 ? (
                <PageEmpty
                  icon="🧠"
                  message="Nessun pattern appreso. La Learning Machine impara dalle tue azioni nel tempo."
                />
              ) : (
                <>
                  <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
                    {Array.from(new Set(pattern.map(p => p.categoria))).map(cat => (
                      <span key={cat} style={badge('info')}>
                        {cat}
                      </span>
                    ))}
                  </div>
                  {pattern.map(p => (
                    <PatternCard key={p.id || p.chiave} p={p} />
                  ))}
                </>
              )}
            </div>
          )}
        </>
      )}
    </PageLayout>
  );
}

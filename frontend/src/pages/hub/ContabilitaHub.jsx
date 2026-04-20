import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { useHashState } from '../../hooks/useHashState';

const PianoContiContent    = lazy(() => import('../PianoDeiConti.jsx'));
const BilancioContent      = lazy(() => import('../Bilancio.jsx'));
const BilancioVerContent   = lazy(() => import('../BilancioVerifica.jsx'));
const ControlloContent     = lazy(() => import('../ControlloMensile.jsx'));
const CalendarioContent    = lazy(() => import('../CalendarioFiscale.jsx'));
const CespitiContent       = lazy(() => import('../GestioneCespiti.jsx'));
const FinanziariaContent   = lazy(() => import('../Finanziaria.jsx'));
const ChiusuraContent      = lazy(() => import('../ChiusuraEsercizio.jsx'));
const BudgetContent        = lazy(() => import('../BudgetPrevisionale.jsx'));
const MutuiContent         = lazy(() => import('../Mutui.jsx'));
const AvanzataContent      = lazy(() => import('../ContabilitaAvanzata.jsx'));

const TABS = [
  { id: 'piano-conti',   label: '📊 Piano dei Conti',     color: '#1a40b5' },
  { id: 'bilancio',      label: '📈 Bilancio',            color: '#10b981' },
  { id: 'verifica',      label: '✅ Verifica Bilancio',   color: '#06b6d4' },
  { id: 'controllo',     label: '🔍 Controllo Mensile',   color: '#3b82f6' },
  { id: 'calendario',    label: '📅 Calendario Fiscale',  color: '#f59e0b' },
  { id: 'cespiti',       label: '🏢 Cespiti',             color: '#8b5cf6' },
  { id: 'finanziaria',   label: '💰 Finanziaria',         color: '#ec4899' },
  { id: 'chiusura',      label: '🔒 Chiusura Esercizio',  color: '#ef4444' },
  { id: 'budget',        label: '📋 Budget Previsionale', color: '#84cc16' },
  { id: 'mutui',         label: '🏠 Mutui',               color: '#f97316' },
  { id: 'avanzata',      label: '🔧 Contab. Avanzata',    color: '#0ea5e9' },
];

const Loading = () => (
  <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
    <div style={{
      width: 32, height: 32,
      border: '3px solid #e2e8f0',
      borderTop: '3px solid #1a40b5',
      borderRadius: '50%',
      animation: 'spin 1s linear infinite',
      margin: '0 auto 12px'
    }} />
    <style>{`@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}`}</style>
    Caricamento...
  </div>
);

const getTabFromPath = (pathname) => {
  if (pathname.includes('/piano-dei-conti') || pathname.includes('/contabilita/piano-conti')) return 'piano-conti';
  if (pathname.includes('/bilancio-verifica') || pathname.includes('/contabilita/verifica')) return 'verifica';
  if (pathname.includes('/bilancio'))          return 'bilancio';
  if (pathname.includes('/controllo-mensile') || pathname.includes('/contabilita/controllo')) return 'controllo';
  if (pathname.includes('/calendario-fiscale') || pathname.includes('/contabilita/calendario')) return 'calendario';
  if (pathname.includes('/cespiti'))           return 'cespiti';
  if (pathname.includes('/finanziaria'))       return 'finanziaria';
  if (pathname.includes('/chiusura'))          return 'chiusura';
  if (pathname.includes('/budget'))            return 'budget';
  if (pathname.includes('/mutui'))             return 'mutui';
  if (pathname.includes('/contabilita-avanzata') || pathname.includes('/contabilita/avanzata')) return 'avanzata';
  if (pathname.includes('/contabilita/')) {
    const m = pathname.match(/\/contabilita\/([\w-]+)/);
    if (m && TABS.find(t => t.id === m[1])) return m[1];
  }
  return 'piano-conti';
};

export default function ContabilitaHub() {
  const { anno } = useAnnoGlobale();
  const navigate  = useNavigate();
  const location  = useLocation();
  const [error, setError] = useState(null);

  // Deep link: hash riflette il tab attivo — la route PATH è il meccanismo primario
  const [hs, setHs] = useHashState({ tab: getTabFromPath(location.pathname) });
  const activeTab = getTabFromPath(location.pathname); // path ha la precedenza

  // Traccia i tab visitati: una volta montato, il componente NON viene smontato
  const [visitedTabs, setVisitedTabs] = useState(() => new Set([getTabFromPath(location.pathname)]));

  useEffect(() => {
    const t = getTabFromPath(location.pathname);
    setHs('tab', t);
    setVisitedTabs(prev => { const n = new Set(prev); n.add(t); return n; });
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleTabChange = (tabId) => {
    setError(null);
    setHs('tab', tabId);
    navigate(tabId === 'piano-conti' ? '/contabilita' : `/contabilita/${tabId}`);
  };

  return (
    <div style={{ width: '100%' }}>
      {/* Tab Bar — stile uniforme */}
      <div style={{
        display: 'flex', gap: 6, padding: '8px 16px',
        background: 'white', borderBottom: '1px solid #e2e8f0',
        borderRadius: '8px 8px 0 0',
        flexWrap: 'wrap', marginBottom: 0,
      }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            data-testid={`tab-contabilita-${tab.id}`}
            onClick={() => handleTabChange(tab.id)}
            style={{
              padding: '7px 13px', borderRadius: 6,
              border: `1px solid ${activeTab === tab.id ? tab.color : '#e2e8f0'}`,
              fontWeight: activeTab === tab.id ? 700 : 500, fontSize: 12, cursor: 'pointer',
              transition: 'all 140ms ease',
              background: activeTab === tab.id ? tab.color : '#ffffff',
              color: activeTab === tab.id ? 'white' : '#64748b',
              boxShadow: activeTab === tab.id ? '0 1px 2px rgba(15,39,68,0.08)' : 'none',
              marginBottom: 4,
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content - mount-once */}
      <div style={{ padding: '16px 0 0 0' }}>
        {error && (
          <div style={{ padding: 16, background: '#fef2f2', borderRadius: 8, color: '#dc2626', marginBottom: 16 }}>
            Errore: {error}
          </div>
        )}
        {[
          { id: 'piano-conti', C: PianoContiContent },
          { id: 'bilancio',    C: BilancioContent },
          { id: 'verifica',    C: BilancioVerContent },
          { id: 'controllo',   C: ControlloContent },
          { id: 'calendario',  C: CalendarioContent },
          { id: 'cespiti',     C: CespitiContent },
          { id: 'finanziaria', C: FinanziariaContent },
          { id: 'chiusura',    C: ChiusuraContent },
          { id: 'budget',      C: BudgetContent },
          { id: 'mutui',       C: MutuiContent },
          { id: 'avanzata',    C: AvanzataContent },
        ].map(({ id, C }) => (
          <div key={id} style={{ display: activeTab === id ? 'block' : 'none' }}>
            <Suspense fallback={<Loading />}>
              {visitedTabs.has(id) && <C />}
            </Suspense>
          </div>
        ))}
      </div>
    </div>
  );
}

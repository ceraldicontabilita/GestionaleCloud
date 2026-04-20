import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';

const VerificaContent       = lazy(() => import('../VerificaCoerenza.jsx'));
const CommercialistaContent = lazy(() => import('../Commercialista.jsx'));
const PianificazioneContent = lazy(() => import('../Pianificazione.jsx'));
const VisureContent         = lazy(() => import('../Visure.jsx'));

const TABS = [
  { id: 'verifica',        label: '🔍 Verifica Coerenza', color: '#3b82f6' },
  { id: 'commercialista',  label: '📊 Commercialista',    color: '#8b5cf6' },
  { id: 'pianificazione',  label: '📅 Pianificazione',    color: '#10b981' },
  { id: 'visure',          label: '🏛️ Visure',            color: '#06b6d4' },
];

const Loading = () => (
  <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
    <div style={{
      width: 32, height: 32,
      border: '3px solid #e2e8f0',
      borderTop: '3px solid #3b82f6',
      borderRadius: '50%',
      animation: 'spin 1s linear infinite',
      margin: '0 auto 12px'
    }} />
    <style>{`@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}`}</style>
    Caricamento...
  </div>
);

const getTabFromPath = (pathname) => {
  if (pathname.includes('/commercialista')) return 'commercialista';
  if (pathname.includes('/pianificazione')) return 'pianificazione';
  if (pathname.includes('/visure'))         return 'visure';
  if (pathname.includes('/strumenti/')) {
    const m = pathname.match(/\/strumenti\/([\w-]+)/);
    if (m && TABS.find(t => t.id === m[1])) return m[1];
  }
  return 'verifica';
};

export default function StrumentiHub() {
  const { anno } = useAnnoGlobale();
  const navigate  = useNavigate();
  const location  = useLocation();
  const [activeTab, setActiveTab] = useState(() => getTabFromPath(location.pathname));
  const [error, setError]         = useState(null);
  const [visitedTabs, setVisitedTabs] = useState(() => new Set([getTabFromPath(location.pathname)]));

  useEffect(() => {
    const t = getTabFromPath(location.pathname);
    setActiveTab(t);
    setVisitedTabs(prev => { const n = new Set(prev); n.add(t); return n; });
  }, [location.pathname]);

  const handleTabChange = (tabId) => {
    setError(null);
    setActiveTab(tabId);
    setVisitedTabs(prev => { const n = new Set(prev); n.add(tabId); return n; });
    navigate(tabId === 'verifica' ? '/strumenti' : `/strumenti/${tabId}`);
  };

  const CONTENTS = {
    'verifica':       VerificaContent,
    'commercialista': CommercialistaContent,
    'pianificazione': PianificazioneContent,
    'visure':         VisureContent,
  };

  return (
    <div style={{ width: '100%' }}>
      {/* Tab Bar uniforme */}
      <div style={{
        display: 'flex', gap: 6, padding: '8px 16px',
        background: 'white', borderBottom: '1px solid #e2e8f0',
        borderRadius: '8px 8px 0 0',
        flexWrap: 'wrap'
      }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            data-testid={`tab-strumenti-${tab.id}`}
            onClick={() => handleTabChange(tab.id)}
            style={{
              padding: '7px 13px', borderRadius: 6,
              border: `1px solid ${activeTab === tab.id ? tab.color : '#e2e8f0'}`,
              fontWeight: activeTab === tab.id ? 700 : 500, fontSize: 12, cursor: 'pointer',
              transition: 'all 140ms ease',
              background: activeTab === tab.id ? tab.color : '#ffffff',
              color: activeTab === tab.id ? 'white' : '#64748b',
              boxShadow: activeTab === tab.id ? '0 1px 2px rgba(15,39,68,0.08)' : 'none',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div style={{ padding: '16px 0 0 0' }}>
        {error && (
          <div style={{ padding: 16, background: '#fef2f2', borderRadius: 8, color: '#dc2626', marginBottom: 16 }}>
            Errore caricamento: {error}
          </div>
        )}
        {TABS.map(tab => {
          const C = CONTENTS[tab.id];
          return (
            <div key={tab.id} style={{ display: activeTab === tab.id ? 'block' : 'none' }}>
              <Suspense fallback={<Loading />}>
                {visitedTabs.has(tab.id) && <C />}
              </Suspense>
            </div>
          );
        })}
      </div>
    </div>
  );
}

import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';

const FlottaContent   = lazy(() => import('../NoleggioAuto.jsx'));
const VerbaliContent  = lazy(() => import('../VerbaliRiconciliazione.jsx'));

const TABS = [
  { id: 'flotta',   label: '🚗 Flotta Auto',       color: '#3b82f6' },
  { id: 'verbali',  label: '📋 Verbali Noleggio',  color: '#8b5cf6' },
  { id: 'costi',    label: '💰 Riepilogo Costi',   color: '#10b981' },
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
  if (pathname.includes('/verbali')) return 'verbali';
  if (pathname.includes('/costi'))   return 'costi';
  if (pathname.includes('/noleggio/')) {
    const m = pathname.match(/\/noleggio\/([\w-]+)/);
    if (m && TABS.find(t => t.id === m[1])) return m[1];
  }
  return 'flotta';
};

function RiepilogoCosti({ anno }) {
  return (
    <div style={{
      background: 'white', borderRadius: 12, padding: 32,
      boxShadow: '0 1px 4px rgba(0,0,0,0.08)', textAlign: 'center'
    }}>
      <div style={{ fontSize: 40, marginBottom: 12 }}>💰</div>
      <h2 style={{ color: '#1e3a5f', margin: '0 0 8px 0' }}>Riepilogo Costi Noleggio {anno}</h2>
      <p style={{ color: '#64748b', margin: 0, fontSize: 14 }}>
        Apri i Verbali per consultare i costi dettagliati per veicolo.
      </p>
    </div>
  );
}

export default function VeicoliHub() {
  const { anno } = useAnnoGlobale();
  const navigate = useNavigate();
  const location = useLocation();
  const [activeTab, setActiveTab] = useState(() => getTabFromPath(location.pathname));

  useEffect(() => {
    const t = getTabFromPath(location.pathname);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    if (t !== activeTab) setActiveTab(t);
  }, [location.pathname]);

  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    navigate(tabId === 'flotta' ? '/noleggio' : `/noleggio/${tabId}`);
  };

  return (
    <div style={{ minHeight: '100vh', background: '#f8fafc' }}>
      {/* Tab Bar */}
      <div style={{
        display: 'flex', gap: 4, padding: '8px 24px',
        background: 'white', borderBottom: '1.5px solid #e2e8f0',
        flexWrap: 'wrap'
      }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            data-testid={`tab-noleggio-${tab.id}`}
            onClick={() => handleTabChange(tab.id)}
            style={{
              padding: '9px 18px',
              borderRadius: 8,
              border: 'none',
              fontWeight: 600,
              fontSize: 13,
              cursor: 'pointer',
              transition: 'all 0.15s',
              background: activeTab === tab.id ? tab.color : '#f1f5f9',
              color: activeTab === tab.id ? 'white' : '#64748b',
              boxShadow: activeTab === tab.id ? '0 2px 6px rgba(0,0,0,0.15)' : 'none',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div style={{ padding: '16px 24px' }}>
        <Suspense fallback={<Loading />}>
          {activeTab === 'flotta'  && <FlottaContent />}
          {activeTab === 'verbali' && <VerbaliContent />}
          {activeTab === 'costi'   && <RiepilogoCosti anno={anno} />}
        </Suspense>
      </div>
    </div>
  );
}

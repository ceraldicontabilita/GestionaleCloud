import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { useHashState } from '../../hooks/useHashState';

const ArchivioContent       = lazy(() => import('../Documenti.jsx'));
const ImportContent         = lazy(() => import('../ImportDocumenti.jsx'));
const DaRivedereContent     = lazy(() => import('../DocumentiDaRivedere.jsx'));
const ClassificazioneContent = lazy(() => import('../ClassificazioneDocumenti.jsx'));
const CorrezioneAIContent   = lazy(() => import('../CorrezioneAI.jsx'));

const TABS = [
  { id: 'archivio',        label: '📁 Archivio',           color: '#3b82f6' },
  { id: 'import',          label: '📥 Import Documenti',   color: '#8b5cf6' },
  { id: 'da-rivedere',     label: '👁️ Da Rivedere',        color: '#f59e0b' },
  { id: 'classificazione', label: '🏷️ Classificazione',    color: '#10b981' },
  { id: 'correzione-ai',   label: '🤖 Correzione AI',      color: '#ec4899' },
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
  if (pathname.includes('/documenti-da-rivedere') || pathname.includes('/documenti/da-rivedere')) return 'da-rivedere';
  if (pathname.includes('/classificazione-documenti') || pathname.includes('/documenti/classificazione')) return 'classificazione';
  if (pathname.includes('/correzione-ai') || pathname.includes('/documenti/correzione-ai')) return 'correzione-ai';
  if (pathname.includes('/import-documenti') || pathname.includes('/documenti/import')) return 'import';
  if (pathname.includes('/documenti/')) {
    const m = pathname.match(/\/documenti\/([\w-]+)/);
    if (m && TABS.find(t => t.id === m[1])) return m[1];
  }
  return 'archivio';
};

export default function DocumentiHub() {
  const { anno } = useAnnoGlobale();
  const navigate  = useNavigate();
  const location  = useLocation();
  const [error, setError] = useState(null);

  // Deep link: hash riflette il tab attivo — la route PATH è il meccanismo primario
  const initTab = getTabFromPath(location.pathname);
  const [hs, setHs] = useHashState({ tab: initTab });
  const activeTab = getTabFromPath(location.pathname); // path ha la precedenza

  useEffect(() => {
    setHs('tab', getTabFromPath(location.pathname));
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleTabChange = (tabId) => {
    setError(null);
    setHs('tab', tabId);
    navigate(tabId === 'archivio' ? '/documenti' : `/documenti/${tabId}`);
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
            data-testid={`tab-documenti-${tab.id}`}
            onClick={() => handleTabChange(tab.id)}
            style={{
              padding: '9px 18px', borderRadius: 8, border: 'none',
              fontWeight: 600, fontSize: 13, cursor: 'pointer',
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
        {error && (
          <div style={{ padding: 16, background: '#fef2f2', borderRadius: 8, color: '#dc2626', marginBottom: 16 }}>
            Errore: {error}
          </div>
        )}
        <Suspense fallback={<Loading />}>
          {activeTab === 'archivio'        && <ArchivioContent />}
          {activeTab === 'import'          && <ImportContent />}
          {activeTab === 'da-rivedere'     && <DaRivedereContent />}
          {activeTab === 'classificazione' && <ClassificazioneContent />}
          {activeTab === 'correzione-ai'   && <CorrezioneAIContent />}
        </Suspense>
      </div>
    </div>
  );
}

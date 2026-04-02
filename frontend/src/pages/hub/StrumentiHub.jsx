import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';

const VerificaContent       = lazy(() => import('../VerificaCoerenza.jsx'));
const CommercialistaContent = lazy(() => import('../Commercialista.jsx'));
const PianificazioneContent = lazy(() => import('../Pianificazione.jsx'));
const EmailContent          = lazy(() => import('../EmailDownloadManager.jsx'));
const VisureContent         = lazy(() => import('../Visure.jsx'));

const TABS = [
  { id: 'verifica',        label: '🔍 Verifica Coerenza', color: '#3b82f6' },
  { id: 'commercialista',  label: '📊 Commercialista',    color: '#8b5cf6' },
  { id: 'pianificazione',  label: '📅 Pianificazione',    color: '#10b981' },
  { id: 'email',           label: '📧 Email Download',    color: '#f59e0b' },
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
  if (pathname.includes('/email-download') || pathname.includes('/email')) return 'email';
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

  useEffect(() => {
    const t = getTabFromPath(location.pathname);
    if (t !== activeTab) setActiveTab(t);
  }, [location.pathname]);

  const handleTabChange = (tabId) => {
    setError(null);
    setActiveTab(tabId);
    navigate(tabId === 'verifica' ? '/strumenti' : `/strumenti/${tabId}`);
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
            data-testid={`tab-strumenti-${tab.id}`}
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
            Errore caricamento: {error}
          </div>
        )}
        <Suspense fallback={<Loading />}>
          {activeTab === 'verifica'       && <VerificaContent />}
          {activeTab === 'commercialista' && <CommercialistaContent />}
          {activeTab === 'pianificazione' && <PianificazioneContent />}
          {activeTab === 'email'          && <EmailContent />}
          {activeTab === 'visure'         && <VisureContent />}
        </Suspense>
      </div>
    </div>
  );
}

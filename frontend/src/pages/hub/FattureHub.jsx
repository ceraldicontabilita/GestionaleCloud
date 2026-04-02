import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';

const ArchivioContent    = lazy(() => import('../ArchivioFattureRicevute.jsx'));
const ImportContent      = lazy(() => import('../CicloPassivoAdmin.jsx'));
const CorrispettiviContent = lazy(() => import('../Corrispettivi.jsx'));

const TABS = [
  { id: 'archivio',       label: '📋 Archivio Fatture', color: '#3b82f6' },
  { id: 'import',         label: '📥 Import / PEC',     color: '#8b5cf6' },
  { id: 'corrispettivi',  label: '🧾 Corrispettivi',    color: '#10b981' },
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
  if (pathname.includes('/import') || pathname.includes('/ciclo-passivo/import')) return 'import';
  if (pathname.includes('/corrispettivi')) return 'corrispettivi';
  if (pathname.includes('/fatture/')) {
    const m = pathname.match(/\/fatture\/(\w[\w-]*)/);
    if (m && TABS.find(t => t.id === m[1])) return m[1];
  }
  return 'archivio';
};

export default function FattureHub() {
  const { anno } = useAnnoGlobale();
  const navigate = useNavigate();
  const location = useLocation();
  const [activeTab, setActiveTab] = useState(() => getTabFromPath(location.pathname));
  const [error, setError] = useState(null);

  useEffect(() => {
    const t = getTabFromPath(location.pathname);
    if (t !== activeTab) setActiveTab(t);
  }, [location.pathname]);

  const handleTabChange = (tabId) => {
    setError(null);
    setActiveTab(tabId);
    navigate(tabId === 'archivio' ? '/fatture' : `/fatture/${tabId}`);
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
            data-testid={`tab-fatture-${tab.id}`}
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
        {error && (
          <div style={{ padding: 16, background: '#fef2f2', borderRadius: 8, color: '#dc2626', marginBottom: 16 }}>
            Errore caricamento: {error}
          </div>
        )}
        <Suspense fallback={<Loading />}>
          {activeTab === 'archivio'      && <ArchivioContent />}
          {activeTab === 'import'        && <ImportContent />}
          {activeTab === 'corrispettivi' && <CorrispettiviContent />}
        </Suspense>
      </div>
    </div>
  );
}

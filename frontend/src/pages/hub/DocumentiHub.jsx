import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { useHashState } from '../../hooks/useHashState';

const ArchivioContent = lazy(() => import('../Documenti.jsx'));
const ImportContent = lazy(() => import('../ImportDocumenti.jsx'));

const TABS = [
  { id: 'archivio', label: '📁 Archivio', color: '#3b82f6' },
  { id: 'import', label: '📥 Import Documenti', color: '#8b5cf6' },
];

const Loading = () => (
  <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
    <div
      style={{
        width: 32,
        height: 32,
        border: '3px solid #e2e8f0',
        borderTop: '3px solid #3b82f6',
        borderRadius: '50%',
        animation: 'spin 1s linear infinite',
        margin: '0 auto 12px',
      }}
    />
    <style>{`@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}`}</style>
    Caricamento...
  </div>
);

const getTabFromPath = pathname => {
  if (pathname.includes('/import-documenti') || pathname.includes('/documenti/import'))
    return 'import';
  if (pathname.includes('/documenti/')) {
    const m = pathname.match(/\/documenti\/([\w-]+)/);
    if (m && TABS.find(t => t.id === m[1])) return m[1];
  }
  return 'archivio';
};

export default function DocumentiHub() {
  const { anno } = useAnnoGlobale();
  const location = useLocation();
  const [error] = useState(null);

  // Deep link: hash riflette il tab attivo — la route PATH è il meccanismo primario
  const initTab = getTabFromPath(location.pathname);
  const [hs, setHs] = useHashState({ tab: initTab });
  const activeTab = getTabFromPath(location.pathname); // path ha la precedenza

  // Traccia tab visitati: mount-once pattern
  const [visitedTabs, setVisitedTabs] = useState(() => new Set([initTab]));

  useEffect(() => {
    const t = getTabFromPath(location.pathname);
    setHs('tab', t);
    setVisitedTabs(prev => {
      const n = new Set(prev);
      n.add(t);
      return n;
    });
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  const CONTENTS = {
    archivio: ArchivioContent,
    import: ImportContent,
  };

  return (
    <div style={{ width: '100%' }}>
      {/* Niente barra tab (richiesta utente 10/07): la pagina Documenti mostra
          SOLO l'archivio; l'Import Documenti si raggiunge dal menù Altro →
          Import Documenti (/documenti/import). Le route restano entrambe. */}

      {/* Tab Content */}
      <div style={{ padding: '16px 0 0 0' }}>
        {error && (
          <div
            style={{
              padding: 16,
              background: '#fef2f2',
              borderRadius: 8,
              color: '#dc2626',
              marginBottom: 16,
            }}
          >
            Errore: {error}
          </div>
        )}
        {TABS.map(tab => {
          const C = CONTENTS[tab.id];
          return (
            <div key={tab.id} style={{ display: activeTab === tab.id ? 'block' : 'none' }}>
              <Suspense fallback={<Loading />}>
                {visitedTabs.has(tab.id) && <C key={`${tab.id}-${anno}`} />}
              </Suspense>
            </div>
          );
        })}
      </div>
    </div>
  );
}

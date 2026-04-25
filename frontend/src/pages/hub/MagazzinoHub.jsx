import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';

const MagazzinoContent = lazy(() => import('../Magazzino.jsx'));
const InventarioContent = lazy(() => import('../Inventario.jsx'));
const RicercaContent = lazy(() => import('../RicercaProdotti.jsx'));
const ArticoliContent = lazy(() => import('../DizionarioArticoli.jsx'));
const ProdottiContent = lazy(() => import('../DizionarioProdotti.jsx'));
const POSContent = lazy(() => import('../CoerenzaPOSCorrispettivi.jsx'));

const TABS = [
  { id: 'giacenze', label: '📦 Giacenze', color: '#3b82f6' },
  { id: 'inventario', label: '📋 Inventario', color: '#10b981' },
  { id: 'ricerca', label: '🔍 Ricerca Prodotti', color: '#f59e0b' },
  { id: 'articoli', label: '📚 Dizionario Articoli', color: '#8b5cf6' },
  { id: 'prodotti', label: '🍽️ Dizionario Prodotti', color: '#f43f5e' },
  { id: 'pos', label: '🔄 Coerenza POS', color: '#06b6d4' },
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
  if (pathname.includes('/inventario')) return 'inventario';
  if (pathname.includes('/ricerca-prodotti') || pathname.includes('/magazzino/ricerca'))
    return 'ricerca';
  if (pathname.includes('/dizionario-articoli') || pathname.includes('/magazzino/articoli'))
    return 'articoli';
  if (pathname.includes('/dizionario-prodotti') || pathname.includes('/magazzino/prodotti'))
    return 'prodotti';
  if (pathname.includes('/pos') || pathname.includes('/coerenza-pos')) return 'pos';
  if (pathname.includes('/magazzino/')) {
    const m = pathname.match(/\/magazzino\/([\w-]+)/);
    if (m && TABS.find(t => t.id === m[1])) return m[1];
  }
  return 'giacenze';
};

export default function MagazzinoHub() {
  const { anno } = useAnnoGlobale();
  const navigate = useNavigate();
  const location = useLocation();
  const [activeTab, setActiveTab] = useState(() => getTabFromPath(location.pathname));
  const [error, setError] = useState(null);
  const [visitedTabs, setVisitedTabs] = useState(
    () => new Set([getTabFromPath(location.pathname)])
  );

  useEffect(() => {
    const t = getTabFromPath(location.pathname);
    setActiveTab(t);
    setVisitedTabs(prev => {
      const n = new Set(prev);
      n.add(t);
      return n;
    });
  }, [location.pathname]);

  const handleTabChange = tabId => {
    setError(null);
    setActiveTab(tabId);
    setVisitedTabs(prev => {
      const n = new Set(prev);
      n.add(tabId);
      return n;
    });
    navigate(tabId === 'giacenze' ? '/magazzino' : `/magazzino/${tabId}`);
  };

  const CONTENTS = {
    giacenze: MagazzinoContent,
    inventario: InventarioContent,
    ricerca: RicercaContent,
    articoli: ArticoliContent,
    prodotti: ProdottiContent,
    pos: POSContent,
  };

  return (
    <div style={{ width: '100%' }}>
      {/* Tab Bar uniforme */}
      <div
        style={{
          display: 'flex',
          gap: 6,
          padding: '8px 16px',
          background: 'white',
          borderBottom: '1px solid #e2e8f0',
          borderRadius: '8px 8px 0 0',
          flexWrap: 'wrap',
        }}
      >
        {TABS.map(tab => (
          <button
            key={tab.id}
            data-testid={`tab-magazzino-${tab.id}`}
            onClick={() => handleTabChange(tab.id)}
            style={{
              padding: '7px 13px',
              borderRadius: 6,
              border: `1px solid ${activeTab === tab.id ? tab.color : '#e2e8f0'}`,
              fontWeight: activeTab === tab.id ? 700 : 500,
              fontSize: 12,
              cursor: 'pointer',
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
          <div
            style={{
              padding: 16,
              background: '#fef2f2',
              borderRadius: 8,
              color: '#dc2626',
              marginBottom: 16,
            }}
          >
            Errore caricamento: {error}
          </div>
        )}
        {TABS.map(tab => {
          const C = CONTENTS[tab.id];
          return (
            <div key={tab.id} style={{ display: activeTab === tab.id ? 'block' : 'none' }}>
              <Suspense fallback={<Loading />}>{visitedTabs.has(tab.id) && <C />}</Suspense>
            </div>
          );
        })}
      </div>
    </div>
  );
}

import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';

const RicettarioContent    = lazy(() => import('../RicettarioAdmin.jsx'));
const FoodCostContent      = lazy(() => import('../FoodCostAdmin.jsx'));
const CatalogoContent      = lazy(() => import('../CatalogoOrdini.jsx'));
const ProdottiContent      = lazy(() => import('../ProdottiVendita.jsx'));

const TABS = [
  { id: 'ricettario',        label: '📖 Ricettario'       },
  { id: 'food-cost',         label: '💰 Food Cost'         },
  { id: 'catalogo-ordini',   label: '🛒 Catalogo Ordini'   },
  { id: 'prodotti-vendita',  label: '🛍️ Prodotti Vendita'  },
];

const Loading = () => (
  <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
    <div style={{
      width: 32, height: 32,
      border: '3px solid #e2e8f0',
      borderTop: '3px solid #1e3a5f',
      borderRadius: '50%',
      animation: 'spin 1s linear infinite',
      margin: '0 auto 12px'
    }} />
    <style>{`@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}`}</style>
    Caricamento...
  </div>
);

export default function CucinaHub() {
  const { anno } = useAnnoGlobale();
  const navigate  = useNavigate();
  const { tab }   = useParams();
  const [activeTab, setActiveTab] = useState(tab && TABS.find(x => x.id === tab) ? tab : 'ricettario');
  const [error, setError] = useState(null);

  // Traccia tab visitati: mount-once pattern
  const [visitedTabs, setVisitedTabs] = useState(() => new Set([tab && TABS.find(x => x.id === tab) ? tab : 'ricettario']));

  // Sincronizza tab URL → stato
  useEffect(() => {
    const t = tab && TABS.find(x => x.id === tab) ? tab : 'ricettario';
    setActiveTab(t);
    setVisitedTabs(prev => { const n = new Set(prev); n.add(t); return n; });
  }, [tab]);

  const handleTabChange = (tabId) => {
    setError(null);
    setActiveTab(tabId);
    setVisitedTabs(prev => { const n = new Set(prev); n.add(tabId); return n; });
    navigate(tabId === 'ricettario' ? '/cucina' : `/cucina/${tabId}`);
  };

  const CONTENTS = {
    'ricettario':       RicettarioContent,
    'food-cost':        FoodCostContent,
    'catalogo-ordini':  CatalogoContent,
    'prodotti-vendita': ProdottiContent,
  };

  return (
    <div style={{ width: '100%' }}>
      {/* Tab Bar uniforme */}
      <div style={{
        display: 'flex', gap: 6, padding: '8px 16px',
        background: 'white', borderBottom: '1px solid #e2e8f0',
        borderRadius: '8px 8px 0 0',
        overflowX: 'auto',
        flexWrap: 'wrap',
      }}>
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => handleTabChange(t.id)}
            style={{
              padding: '7px 13px', borderRadius: 6,
              border: `1px solid ${activeTab === t.id ? '#0f2744' : '#e2e8f0'}`,
              fontWeight: activeTab === t.id ? 700 : 500, fontSize: 12, cursor: 'pointer',
              transition: 'all 140ms ease',
              background: activeTab === t.id ? '#0f2744' : '#ffffff',
              color: activeTab === t.id ? 'white' : '#64748b',
              boxShadow: activeTab === t.id ? '0 1px 2px rgba(15,39,68,0.08)' : 'none',
              whiteSpace: 'nowrap',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Contenuto - mount-once pattern */}
      {error && (
        <div style={{ margin: 16, padding: 12, background: '#fee2e2', color: '#dc2626', borderRadius: 8 }}>
          {error}
        </div>
      )}
      {TABS.map(t => {
        const C = CONTENTS[t.id];
        return (
          <div key={t.id} style={{ display: activeTab === t.id ? 'block' : 'none' }}>
            <Suspense fallback={<Loading />}>
              {visitedTabs.has(t.id) && <C />}
            </Suspense>
          </div>
        );
      })}
    </div>
  );
}

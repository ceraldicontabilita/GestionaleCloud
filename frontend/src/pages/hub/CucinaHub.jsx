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
  { id: 'tablet',            label: '📱 Tablet Reparto'    },
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
    if (tabId === 'tablet') { window.location.href = '/tablet-cucina'; return; }
    navigate(tabId === 'ricettario' ? '/cucina' : `/cucina/${tabId}`);
  };

  const CONTENTS = {
    'ricettario':       RicettarioContent,
    'food-cost':        FoodCostContent,
    'catalogo-ordini':  CatalogoContent,
    'prodotti-vendita': ProdottiContent,
  };

  return (
    <div style={{ minHeight: '100vh', background: '#f8fafc' }}>
      {/* Barra tab */}
      <div style={{
        display: 'flex',
        gap: 0,
        borderBottom: '2px solid #e2e8f0',
        background: '#fff',
        padding: '0 24px',
        overflowX: 'auto',
      }}>
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => handleTabChange(t.id)}
            style={{
              padding: '12px 20px',
              fontWeight: 600,
              fontSize: 13,
              cursor: 'pointer',
              border: 'none',
              borderBottom: activeTab === t.id ? '3px solid #1e3a5f' : '3px solid transparent',
              background: 'transparent',
              color: activeTab === t.id ? '#1e3a5f' : '#6b7280',
              whiteSpace: 'nowrap',
              transition: 'color 0.15s',
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

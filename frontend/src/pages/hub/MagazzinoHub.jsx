import React, { lazy, Suspense } from 'react';
import { useLocation } from 'react-router-dom';

const MagazzinoContent = lazy(() => import('../Magazzino.jsx'));
const InventarioContent = lazy(() => import('../Inventario.jsx'));
const ArticoliContent = lazy(() => import('../DizionarioArticoli.jsx'));
const RicercaContent = lazy(() => import('../RicercaProdotti.jsx'));
// MagazzinoDoppiaVerita rimosso (Blocco J2)

const Loading = () => (
  <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
    <div style={{
      width: 32, height: 32,
      border: '3px solid #e2e8f0',
      borderTop: '3px solid #2563eb',
      borderRadius: '50%',
      animation: 'spin 1s linear infinite',
      margin: '0 auto 12px'
    }} />
    Caricamento...
  </div>
);

export default function MagazzinoHub() {
  const location = useLocation();
  const path = location.pathname;

  const getContent = () => {
    if (path.includes('/inventario')) return <InventarioContent />;
    if (path.includes('/articoli') || path.includes('/dizionario')) return <ArticoliContent />;
    if (path.includes('/ricerca-prodotti')) return <RicercaContent />;
    return <MagazzinoContent />;
  };

  return (
    <div style={{ padding: '16px 24px', minHeight: '100vh', background: '#f8fafc' }}>
      <Suspense fallback={<Loading />}>
        {getContent()}
      </Suspense>
    </div>
  );
}

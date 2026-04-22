import React, { lazy, Suspense } from 'react';
import { useLocation } from 'react-router-dom';

const BilancioContent = lazy(() => import('../Bilancio.jsx'));
const VerificaContent = lazy(() => import('../BilancioVerifica.jsx'));
const PartitarioContent = lazy(() => import('../PartitarioCliFor.jsx'));
const BudgetContent = lazy(() => import('../BudgetPrevisionale.jsx'));

const Loading = () => (
  <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
    <div
      style={{
        width: 32,
        height: 32,
        border: '3px solid #e2e8f0',
        borderTop: '3px solid #2563eb',
        borderRadius: '50%',
        animation: 'spin 1s linear infinite',
        margin: '0 auto 12px',
      }}
    />
    Caricamento...
  </div>
);

export default function BilancioHub() {
  const location = useLocation();
  const path = location.pathname;

  const getContent = () => {
    if (path.includes('/bilancio-verifica')) return <VerificaContent />;
    if (path.includes('/partitario')) return <PartitarioContent />;
    if (path.includes('/budget')) return <BudgetContent />;
    return <BilancioContent />;
  };

  return (
    <div style={{ width: '100%' }}>
      <Suspense fallback={<Loading />}>{getContent()}</Suspense>
    </div>
  );
}

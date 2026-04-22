import React, { lazy, Suspense } from 'react';

const DashboardContent = lazy(() => import('../Dashboard.jsx'));

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

export default function DashboardHub() {
  return (
    <div style={{ width: '100%' }}>
      <Suspense fallback={<Loading />}>
        <DashboardContent />
      </Suspense>
    </div>
  );
}

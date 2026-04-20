import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';

const PrimaNotaContent = lazy(() => import('../PrimaNota.jsx'));
const DatiProvvisoriContent = lazy(() => import('../DatiProvvisoriPage.jsx'));

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

export default function PrimaNotaHub() {
  const location = useLocation();
  const path = location.pathname;
  const isProvvisori = path.includes('provvisori') || path.includes('dati-provvisori');

  // Mount-once: la vista viene montata al primo accesso e mantenuta
  const [visitedProvvisori, setVisitedProvvisori] = useState(isProvvisori);
  const [visitedPrimaNota, setVisitedPrimaNota] = useState(!isProvvisori);

  useEffect(() => {
    if (isProvvisori) setVisitedProvvisori(true);
    else setVisitedPrimaNota(true);
  }, [isProvvisori]);

  return (
    <div style={{ width: '100%' }}>
      <div style={{ display: isProvvisori ? 'none' : 'block' }}>
        <Suspense fallback={<Loading />}>
          {visitedPrimaNota && <PrimaNotaContent />}
        </Suspense>
      </div>
      <div style={{ display: isProvvisori ? 'block' : 'none' }}>
        <Suspense fallback={<Loading />}>
          {visitedProvvisori && <DatiProvvisoriContent />}
        </Suspense>
      </div>
    </div>
  );
}

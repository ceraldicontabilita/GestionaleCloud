import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { PageLoader } from '../../components/ds';
import { sezionePrimaNota } from './segmentiHub';

const PrimaNotaContent = lazy(() => import('../PrimaNota.jsx'));
const PuliziaContent = lazy(() => import('../PuliziaPrimaNota.jsx'));

export default function PrimaNotaHub() {
  const { anno } = useAnnoGlobale();
  const location = useLocation();
  const path = location.pathname;
  const isPulizia = sezionePrimaNota(path) === 'pulizia';
  const activeTab = isPulizia ? 'pulizia' : 'prima-nota';

  const [visitedPrimaNota, setVisitedPrimaNota] = useState(!isPulizia);
  const [visitedPulizia, setVisitedPulizia] = useState(isPulizia);

  useEffect(() => {
    if (isPulizia) setVisitedPulizia(true);
    else setVisitedPrimaNota(true);
  }, [isPulizia]);

  return (
    <div style={{ width: '100%' }}>
      <div style={{ display: activeTab === 'prima-nota' ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>
          {visitedPrimaNota && <PrimaNotaContent key={`prima-nota-${anno}`} />}
        </Suspense>
      </div>
      <div style={{ display: activeTab === 'pulizia' ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>
          {visitedPulizia && <PuliziaContent key={`pulizia-prima-nota-${anno}`} />}
        </Suspense>
      </div>
    </div>
  );
}

import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { PageLoader } from '../../components/ds';

const PrimaNotaContent = lazy(() => import('../PrimaNota.jsx'));
const PuliziaContent = lazy(() => import('../PuliziaPrimaNota.jsx'));


export default function PrimaNotaHub() {
  const { anno } = useAnnoGlobale();
  const location = useLocation();
  const path = location.pathname;
  const isPulizia = path.includes('/pulizia');
  const activeTab = isPulizia ? 'pulizia' : 'prima-nota';

  // Mount-once: la vista viene montata al primo accesso e mantenuta
  const [visitedPrimaNota, setVisitedPrimaNota] = useState(!isPulizia);
  const [visitedPulizia, setVisitedPulizia] = useState(isPulizia);

  useEffect(() => {
    if (isPulizia) setVisitedPulizia(true);
    else setVisitedPrimaNota(true);
  }, [isPulizia]);

  return (
    <div style={{ width: '100%' }}>
      {/* Niente barra tab hub (richiesta utente 10/07): la pagina Prima Nota
          ha GIÀ i suoi sottotab CASSA / BANCA / PROVVISORI — la barra sopra
          ("Prima nota" / "Provvisori") era un doppione. La Pulizia si
          raggiunge dal bottone "🗑️ Pulisci duplicati" dentro la pagina. */}
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

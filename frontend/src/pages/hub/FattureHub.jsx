import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { PageLoader } from '../../components/ds';
import { PageHeader } from '../../components/ds/PageHeader';
import { sezioneFatture } from './segmentiHub';

const ArchivioContent = lazy(() => import('../ArchivioFattureRicevute.jsx'));
const RigheAcquistiContent = lazy(() => import('../RigheAcquisti.jsx'));
const CorrispettiviContent = lazy(() => import('../Corrispettivi.jsx'));
const EmesseContent = lazy(() => import('../FattureEmesse.jsx'));

const SEZIONI = {
  archivio: ArchivioContent,
  righe: RigheAcquistiContent,
  corrispettivi: CorrispettiviContent,
  emesse: EmesseContent,
};

export default function FattureHub() {
  const { anno } = useAnnoGlobale();
  const location = useLocation();
  const sezione = sezioneFatture(location.pathname);

  // Una sezione gia' aperta resta montata (si torna senza ricaricare);
  // al cambio d'anno resta solo quella in vista.
  const [visitate, setVisitate] = useState(() => new Set([sezione]));

  useEffect(() => {
    setVisitate(prev => (prev.has(sezione) ? prev : new Set([...prev, sezione])));
  }, [sezione]);

  useEffect(() => {
    setVisitate(new Set([sezione]));
  }, [anno]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={{ width: '100%' }}>
      {/* Corrispettivi e fatture emesse hanno la loro testata; l'archivio la prende qui. */}
      {sezione === 'archivio' && <PageHeader title="Fatture ricevute" style={{ marginBottom: 14 }} />}
      {Object.entries(SEZIONI).map(([id, Contenuto]) => (
        <div key={id} style={{ display: sezione === id ? 'block' : 'none' }}>
          <Suspense fallback={<PageLoader />}>
            {visitate.has(id) && <Contenuto key={`${id}-${anno}`} />}
          </Suspense>
        </div>
      ))}
    </div>
  );
}

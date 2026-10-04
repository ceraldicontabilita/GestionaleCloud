import React, { lazy, Suspense, useState, useEffect } from 'react';
import { FileOutput, FileStack, ShoppingCart, Wallet } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { HubTabs, PageLoader } from '../../components/ds';
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
  const navigate = useNavigate();
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
      <HubTabs
        testIdPrefix="tab-fatture"
        activeId={sezione}
        onSelect={tab => navigate(tab.to)}
        tabs={[
          { id: 'archivio', label: 'Fatture ricevute', Icon: FileStack, to: '/fatture' },
          { id: 'righe', label: 'Righe acquisti', Icon: ShoppingCart, to: '/fatture/righe' },
          { id: 'emesse', label: 'Fatture emesse', Icon: FileOutput, to: '/fatture/emesse' },
          { id: 'corrispettivi', label: 'Corrispettivi', Icon: Wallet, to: '/fatture/corrispettivi' },
        ]}
      />
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

import React, { lazy, Suspense, useState, useEffect } from 'react';
import { FileStack, Wallet } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { HubTabs, PageLoader } from '../../components/ds';
import { sezioneFatture } from './segmentiHub';

const ArchivioContent = lazy(() => import('../ArchivioFattureRicevute.jsx'));
const CorrispettiviContent = lazy(() => import('../Corrispettivi.jsx'));

export default function FattureHub() {
  const { anno } = useAnnoGlobale();
  const location = useLocation();
  const navigate = useNavigate();
  const isCorresp = sezioneFatture(location.pathname) === 'corrispettivi';

  const [visitedCorresp, setVisitedCorresp] = useState(isCorresp);
  const [visitedArchivio, setVisitedArchivio] = useState(!isCorresp);

  useEffect(() => {
    if (isCorresp) setVisitedCorresp(true);
    else setVisitedArchivio(true);
  }, [isCorresp]);

  useEffect(() => {
    setVisitedCorresp(isCorresp);
    setVisitedArchivio(!isCorresp);
  }, [anno]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={{ width: '100%' }}>
      <HubTabs
        testIdPrefix="tab-fatture"
        activeId={isCorresp ? 'corrispettivi' : 'archivio'}
        onSelect={tab => navigate(tab.to)}
        tabs={[
          { id: 'archivio', label: 'Archivio fatture', Icon: FileStack, to: '/fatture' },
          { id: 'corrispettivi', label: 'Corrispettivi', Icon: Wallet, to: '/fatture/corrispettivi' },
        ]}
      />
      <div style={{ display: isCorresp ? 'none' : 'block' }}>
        <Suspense fallback={<PageLoader />}>
          {visitedArchivio && <ArchivioContent key={`archivio-${anno}`} />}
        </Suspense>
      </div>
      <div style={{ display: isCorresp ? 'block' : 'none' }}>
        <Suspense fallback={<PageLoader />}>
          {visitedCorresp && <CorrispettiviContent key={`corrispettivi-${anno}`} />}
        </Suspense>
      </div>
    </div>
  );
}

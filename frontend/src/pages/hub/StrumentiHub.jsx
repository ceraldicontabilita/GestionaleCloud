import React, { lazy, Suspense, useState, useEffect } from 'react';
import { sezioneStrumenti } from './segmentiHub';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { PageLoader } from '../../components/ds';

const VerificaContent = lazy(() => import('../VerificaCoerenza.jsx'));
const CommercialistaContent = lazy(() => import('../Commercialista.jsx'));
const PianificazioneContent = lazy(() => import('../Pianificazione.jsx'));
const VisureContent = lazy(() => import('../Visure.jsx'));

// Quattro pagine distinte: ognuna ha la sua voce nel menu laterale, nessuna barra di schede in alto.
const TABS = [
  { id: 'verifica', label: 'Verifica coerenza' },
  { id: 'commercialista', label: 'Commercialista' },
  { id: 'pianificazione', label: 'Pianificazione' },
  { id: 'visure', label: 'Visure' },
];

const getTabFromPath = sezioneStrumenti;

export default function StrumentiHub() {
  const { anno } = useAnnoGlobale();
  const navigate = useNavigate();
  const location = useLocation();
  const [activeTab, setActiveTab] = useState(() => getTabFromPath(location.pathname));
  const [visitedTabs, setVisitedTabs] = useState(
    () => new Set([getTabFromPath(location.pathname)])
  );

  useEffect(() => {
    if (
      location.pathname === '/strumenti/movimenti-banca' ||
      location.pathname.startsWith('/strumenti/movimenti-banca/')
    ) {
      navigate('/riconciliazione/movimenti-banca', { replace: true });
    }
  }, [location.pathname, navigate]);

  useEffect(() => {
    const t = getTabFromPath(location.pathname);
    setActiveTab(t);
    setVisitedTabs(prev => {
      const n = new Set(prev);
      n.add(t);
      return n;
    });
  }, [location.pathname]);

  const CONTENTS = {
    verifica: VerificaContent,
    commercialista: CommercialistaContent,
    pianificazione: PianificazioneContent,
    visure: VisureContent,
  };

  return (
    <div style={{ width: '100%' }}>
      <div style={{ padding: '16px 0 0 0' }}>
        {TABS.map(tab => {
          const C = CONTENTS[tab.id];
          return (
            <div key={tab.id} style={{ display: activeTab === tab.id ? 'block' : 'none' }}>
              <Suspense fallback={<PageLoader />}>{visitedTabs.has(tab.id) && <C />}</Suspense>
            </div>
          );
        })}
      </div>
    </div>
  );
}

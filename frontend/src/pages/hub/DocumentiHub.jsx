import { sezioneDocumenti } from './segmentiHub';
import React, { lazy, Suspense, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { PageLoader } from '../../components/ds';
import './DocumentiHub.css';

const ArchivioContent = lazy(() => import('../Documenti.jsx'));
const ImportContent = lazy(() => import('../ImportDocumenti.jsx'));
const AttiAmministrativiContent = lazy(() => import('../AttiAmministrativi.jsx'));

// Le tre sezioni sono pagine vere, ognuna con la sua voce nella colonna di
// navigazione (Atti amministrativi, Importa, Archivio documenti). Prima stavano anche qui come riquadri con icona e
// sottotitolo che sembravano portare altrove e invece cambiavano scheda:
// una sola strada per arrivarci, la colonna.
const SEZIONI = ['atti', 'import', 'archivio'];

const getTabFromPath = sezioneDocumenti;

export default function DocumentiHub() {
  const { anno } = useAnnoGlobale();
  const location = useLocation();
  const initTab = getTabFromPath(location.pathname);
  const activeTab = getTabFromPath(location.pathname);
  const [visitedTabs, setVisitedTabs] = useState(() => new Set([initTab]));
  useEffect(() => {
    const tab = getTabFromPath(location.pathname);
    setVisitedTabs(previous => new Set([...previous, tab]));
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  const contents = {
    archivio: ArchivioContent,
    import: ImportContent,
    atti: AttiAmministrativiContent,
  };

  return (
    <div className="documenti-hub">
      <div className="documenti-hub__content">
        {SEZIONI.map(id => {
          const Content = contents[id];
          return (
            <div key={id} style={{ display: activeTab === id ? 'block' : 'none' }}>
              <Suspense fallback={<PageLoader />}>
                {visitedTabs.has(id) && <Content key={`${id}-${anno}`} />}
              </Suspense>
            </div>
          );
        })}
      </div>
    </div>
  );
}

import React, { lazy, Suspense, useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Archive, Upload } from 'lucide-react';
import api from '../../api';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { useHashState } from '../../hooks/useHashState';
import { PageLoader } from '../../components/ds';
import './DocumentiHub.css';

const ArchivioContent = lazy(() => import('../Documenti.jsx'));
const ImportContent = lazy(() => import('../ImportDocumenti.jsx'));

const TABS = [
  {
    id: 'import',
    label: 'Carica documenti',
    description: 'File singoli, multipli o ZIP con riconoscimento automatico',
    to: '/documenti/import',
    Icon: Upload,
  },
  {
    id: 'archivio',
    label: 'Archivio documenti',
    description: 'Consulta documenti importati, esiti e anomalie',
    to: '/documenti/archivio',
    Icon: Archive,
  },
];

const getTabFromPath = pathname => {
  if (pathname.includes('/documenti/archivio')) return 'archivio';
  if (pathname.includes('/documenti/import') || pathname.includes('/import-documenti')) {
    return 'import';
  }
  return 'import';
};

export default function DocumentiHub() {
  const { anno } = useAnnoGlobale();
  const location = useLocation();
  const initTab = getTabFromPath(location.pathname);
  const [, setHs] = useHashState({ tab: initTab });
  const activeTab = getTabFromPath(location.pathname);
  const [visitedTabs, setVisitedTabs] = useState(() => new Set([initTab]));
  const [driveCatalog, setDriveCatalog] = useState(null);

  useEffect(() => {
    const tab = getTabFromPath(location.pathname);
    setHs('tab', tab);
    setVisitedTabs(previous => new Set([...previous, tab]));
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  // La sincronizzazione ordinaria di Drive non richiede un'azione manuale:
  // all'apertura dell'hub carichiamo il catalogo e avviamo automaticamente
  // il sync delle cartelle che dispongono di parser.
  useEffect(() => {
    let active = true;

    const loadAndSyncDrive = async () => {
      try {
        const response = await api.get('/api/documenti/drive/catalog');
        if (!active) return;
        const catalog = response.data;
        setDriveCatalog(catalog);

        if (catalog?.automatic > 0) {
          api.post('/api/documenti/drive/sync').catch(error => {
            console.warn('Sincronizzazione automatica Drive non avviata:', error);
          });
        }
      } catch (error) {
        if (active) setDriveCatalog(null);
      }
    };

    loadAndSyncDrive();
    return () => { active = false; };
  }, []);

  const contents = {
    archivio: ArchivioContent,
    import: ImportContent,
  };

  return (
    <div className="documenti-hub">
      <nav className="documenti-hub__actions" aria-label="Azioni documenti">
        {TABS.map(({ id, label, description, to, Icon }) => (
          <NavLink
            key={id}
            to={to}
            className={`documenti-hub__action ${activeTab === id ? 'is-active' : ''}`}
          >
            <span className="documenti-hub__icon" aria-hidden="true">
              <Icon size={22} />
            </span>
            <span>
              <strong>{label}</strong>
              <small>{description}</small>
            </span>
          </NavLink>
        ))}
      </nav>

      {driveCatalog?.total > 0 && (
        <section className="documenti-hub__drive" aria-label="Cartelle Google Drive collegate">
          <div className="documenti-hub__drive-heading">
            <div>
              <strong>Google Drive collegato</strong>
              <span>{driveCatalog.configured} cartelle censite, {driveCatalog.automatic} con parser disponibile</span>
            </div>
            <div className="documenti-hub__drive-controls">
              <span className="documenti-hub__drive-total" title="Cartelle collegate">
                {driveCatalog.total}
              </span>
            </div>
          </div>
          <div className="documenti-hub__drive-grid">
            {driveCatalog.folders.map(folder => (
              <article className="documenti-hub__drive-card" key={folder.area}>
                <span className={`documenti-hub__drive-dot is-${folder.status}`} aria-hidden="true" />
                <div>
                  <strong>{folder.label}</strong>
                  <small>{folder.mode === 'automatico' ? 'Parser disponibile' : 'Archivio catalogato'}</small>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      <div className="documenti-hub__content">
        {TABS.map(tab => {
          const Content = contents[tab.id];
          return (
            <div key={tab.id} style={{ display: activeTab === tab.id ? 'block' : 'none' }}>
              <Suspense fallback={<PageLoader />}>
                {visitedTabs.has(tab.id) && <Content key={`${tab.id}-${anno}`} />}
              </Suspense>
            </div>
          );
        })}
      </div>
    </div>
  );
}

import React, { lazy, Suspense, useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Archive, RefreshCw, Upload } from 'lucide-react';
import { toast } from 'sonner';
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
  const [driveSyncing, setDriveSyncing] = useState(false);

  useEffect(() => {
    const tab = getTabFromPath(location.pathname);
    setHs('tab', tab);
    setVisitedTabs(previous => new Set([...previous, tab]));
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let active = true;
    api.get('/api/documenti/drive/catalog')
      .then(response => active && setDriveCatalog(response.data))
      .catch(() => active && setDriveCatalog(null));
    return () => { active = false; };
  }, []);

  const contents = {
    archivio: ArchivioContent,
    import: ImportContent,
  };

  const syncDriveNow = async () => {
    setDriveSyncing(true);
    try {
      const response = await api.post('/api/documenti/drive/sync');
      toast.success('Sincronizzazione Drive avviata', {
        description: response.data?.message,
      });
    } catch (error) {
      toast.error('Sincronizzazione Drive non avviata', {
        description: error.response?.data?.detail || error.message,
      });
    } finally {
      setDriveSyncing(false);
    }
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
              {driveCatalog.automatic > 0 && (
                <button
                  className="documenti-hub__drive-sync"
                  type="button"
                  onClick={syncDriveNow}
                  disabled={driveSyncing}
                >
                  <RefreshCw size={16} className={driveSyncing ? 'is-spinning' : ''} aria-hidden="true" />
                  {driveSyncing ? 'Avvio in corso...' : 'Sincronizza Drive'}
                </button>
              )}
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

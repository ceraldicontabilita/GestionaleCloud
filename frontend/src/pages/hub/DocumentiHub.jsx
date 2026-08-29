import React, { lazy, Suspense, useEffect, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { Archive, ExternalLink, FileWarning, Search, Upload } from 'lucide-react';
import api from '../../api';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { useHashState } from '../../hooks/useHashState';
import { PageLoader } from '../../components/ds';
import './DocumentiHub.css';

const ArchivioContent = lazy(() => import('../Documenti.jsx'));
const ImportContent = lazy(() => import('../ImportDocumenti.jsx'));
const DriveIndexContent = lazy(() => import('../DriveDocumentIndex.jsx'));
const AttiAmministrativiContent = lazy(() => import('../AttiAmministrativi.jsx'));

const TABS = [
  {
    id: 'atti',
    label: 'Atti amministrativi',
    description: 'Verbali, TARI, AdeR e dimissioni con provenienza',
    to: '/documenti/atti',
    Icon: FileWarning,
  },
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
  {
    id: 'drive',
    label: 'Indice Google Drive',
    description: 'Cerca gli originali su Drive senza copiarli nel database',
    to: '/documenti/drive',
    Icon: Search,
  },
];

const getTabFromPath = pathname => {
  if (pathname.includes('/documenti/atti')) return 'atti';
  if (pathname.includes('/documenti/drive')) return 'drive';
  if (pathname.includes('/documenti/archivio')) return 'archivio';
  if (pathname.includes('/documenti/import') || pathname.includes('/import-documenti')) {
    return 'import';
  }
  return 'import';
};

export default function DocumentiHub() {
  const { anno } = useAnnoGlobale();
  const location = useLocation();
  const navigate = useNavigate();
  const initTab = getTabFromPath(location.pathname);
  const [, setHs] = useHashState({ tab: initTab });
  const activeTab = getTabFromPath(location.pathname);
  const [visitedTabs, setVisitedTabs] = useState(() => new Set([initTab]));
  const [driveCatalog, setDriveCatalog] = useState(null);
  const [driveFolderLinks, setDriveFolderLinks] = useState({});

  useEffect(() => {
    const tab = getTabFromPath(location.pathname);
    setHs('tab', tab);
    setVisitedTabs(previous => new Set([...previous, tab]));
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  // L'hub consulta soltanto il catalogo. Le sincronizzazioni massive non
  // vengono mai avviate implicitamente all'apertura della pagina.
  useEffect(() => {
    let active = true;

    const loadAndSyncDrive = async () => {
      try {
        const response = await api.get('/api/documenti/drive/catalog');
        if (!active) return;
        const catalog = response.data;
        setDriveCatalog(catalog);

      } catch (error) {
        if (active) setDriveCatalog(null);
      }
    };

    loadAndSyncDrive();
    return () => { active = false; };
  }, []);

  // Link Drive reali (webViewLink + nome live): endpoint riservato agli admin.
  // Chi non e' admin resta con la sola ricerca interna (fallback sotto).
  useEffect(() => {
    let active = true;

    const loadFolderLinks = async () => {
      try {
        const response = await api.get('/api/documenti/drive/folders');
        if (!active) return;
        const links = {};
        for (const folder of response.data?.folders || []) {
          links[folder.area] = folder;
        }
        setDriveFolderLinks(links);
      } catch (error) {
        if (active) setDriveFolderLinks({});
      }
    };

    loadFolderLinks();
    return () => { active = false; };
  }, []);

  const contents = {
    archivio: ArchivioContent,
    import: ImportContent,
    drive: DriveIndexContent,
    atti: AttiAmministrativiContent,
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
            {driveCatalog.folders.map(folder => {
              const link = driveFolderLinks[folder.area];
              // Il nome live da Drive prevale su quello salvato nel registro:
              // le cartelle su Drive non sono ancora normalizzate e possono
              // essere state rinominate dopo la configurazione dell'area.
              const displayLabel = link?.live_name || folder.label;
              const renamed = link?.live_name && link.live_name !== folder.label;
              return (
                <button
                  type="button"
                  className="documenti-hub__drive-card"
                  key={folder.area}
                  onClick={() => {
                    if (link?.url) {
                      window.open(link.url, '_blank', 'noopener,noreferrer');
                    } else {
                      navigate(`/documenti/drive?folder=${encodeURIComponent(folder.label)}`);
                    }
                  }}
                  aria-label={link?.url ? `Apri la cartella Drive ${displayLabel}` : `Apri indice della cartella ${displayLabel}`}
                  title={renamed ? `Etichetta interna: ${folder.label}` : undefined}
                >
                  <span className={`documenti-hub__drive-dot is-${folder.status}`} aria-hidden="true" />
                  <div>
                    <strong>{displayLabel}</strong>
                    <small>{folder.mode === 'automatico' ? 'Verde · dati estratti dal parser' : 'Blu · archivio da consultare'}</small>
                  </div>
                  {link?.url && <ExternalLink size={14} className="documenti-hub__drive-external" aria-hidden="true" />}
                </button>
              );
            })}
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

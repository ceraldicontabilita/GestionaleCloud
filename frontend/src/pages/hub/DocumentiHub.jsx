import { sezioneDocumenti } from './segmentiHub';
import React, { lazy, Suspense, useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ExternalLink } from 'lucide-react';
import api from '../../api';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { PageLoader } from '../../components/ds';
import { PageHeader } from '../../components/ds/PageHeader';
import './DocumentiHub.css';

const ArchivioContent = lazy(() => import('../Documenti.jsx'));
const ImportContent = lazy(() => import('../ImportDocumenti.jsx'));
const DriveIndexContent = lazy(() => import('../DriveDocumentIndex.jsx'));
const AttiAmministrativiContent = lazy(() => import('../AttiAmministrativi.jsx'));

// Le quattro sezioni sono pagine vere, ognuna con la sua voce nella colonna di
// navigazione (Atti amministrativi, Importa, Archivio documenti, Cartelle
// Google Drive). Prima stavano anche qui come riquadri con icona e
// sottotitolo che sembravano portare altrove e invece cambiavano scheda:
// una sola strada per arrivarci, la colonna.
const SEZIONI = ['atti', 'import', 'archivio', 'drive'];

/* Le cartelle Drive in due elenchi con il loro nome, invece di un pallino
   verde o blu da decifrare: quelle che il gestionale legge e fanno entrare
   dati in contabilita', e quelle solo da consultare. Ognuno in ordine
   alfabetico. */
export function dividiCartelleDrive(folders = [], nomeDi = f => f.label) {
  const perNome = (a, b) => String(nomeDi(a) || '').localeCompare(String(nomeDi(b) || ''), 'it', { sensitivity: 'base' });
  return {
    contabili: folders.filter(f => f.mode === 'automatico').sort(perNome),
    consultazione: folders.filter(f => f.mode !== 'automatico').sort(perNome),
  };
}

const getTabFromPath = sezioneDocumenti;

export default function DocumentiHub() {
  const { anno } = useAnnoGlobale();
  const location = useLocation();
  const navigate = useNavigate();
  const initTab = getTabFromPath(location.pathname);
  const activeTab = getTabFromPath(location.pathname);
  const [visitedTabs, setVisitedTabs] = useState(() => new Set([initTab]));
  const [driveCatalog, setDriveCatalog] = useState(null);
  const [driveFolderLinks, setDriveFolderLinks] = useState({});

  useEffect(() => {
    const tab = getTabFromPath(location.pathname);
    setVisitedTabs(previous => new Set([...previous, tab]));
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  // L'hub consulta soltanto il catalogo. Le sincronizzazioni massive non
  // vengono mai avviate implicitamente all'apertura della pagina.
  useEffect(() => {
    if (activeTab !== 'drive') return undefined;
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
  }, [activeTab]);

  // Link Drive reali (webViewLink + nome live): endpoint riservato agli admin.
  // Chi non e' admin resta con la sola ricerca interna (fallback sotto).
  useEffect(() => {
    if (activeTab !== 'drive') return undefined;
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
  }, [activeTab]);

  const contents = {
    archivio: ArchivioContent,
    import: ImportContent,
    drive: DriveIndexContent,
    atti: AttiAmministrativiContent,
  };

  return (
    <div className="documenti-hub">
      {activeTab === 'drive' && driveCatalog?.total > 0 && (() => {
        const nomeDi = folder => driveFolderLinks[folder.area]?.live_name || folder.label;
        const { contabili, consultazione } = dividiCartelleDrive(driveCatalog.folders, nomeDi);
        const scheda = folder => {
          const link = driveFolderLinks[folder.area];
          // Il nome live da Drive prevale su quello salvato nel registro:
          // le cartelle su Drive possono essere state rinominate dopo la
          // configurazione dell'area.
          const displayLabel = nomeDi(folder);
          const renamed = link?.live_name && link.live_name !== folder.label;
          return (
            <button
              type="button"
              className="documenti-hub__drive-card"
              key={folder.area}
              onClick={() => {
                if (folder.area === 'verbali_auto' || /verbali/i.test(folder.label)) {
                  navigate('/noleggio/verbali');
                  return;
                }
                if (link?.url) {
                  window.open(link.url, '_blank', 'noopener,noreferrer');
                } else {
                  navigate(`/documenti/drive?folder=${encodeURIComponent(folder.label)}`);
                }
              }}
              aria-label={link?.url ? `Apri la cartella Drive ${displayLabel}` : `Apri indice della cartella ${displayLabel}`}
              title={renamed ? `Etichetta interna: ${folder.label}` : undefined}
            >
              <div>
                <strong>{displayLabel}</strong>
              </div>
              {link?.url && <ExternalLink size={14} className="documenti-hub__drive-external" aria-hidden="true" />}
            </button>
          );
        };
        return (
          <>
            <PageHeader
              title="Cartelle Google Drive"
              style={{ marginBottom: 14 }}
              pastiglie={[
                { etichetta: 'Cartelle', valore: String(driveCatalog.total) },
                { etichetta: 'Alimentano la contabilità', valore: String(contabili.length) },
                { etichetta: 'Solo da consultare', valore: String(consultazione.length) },
              ]}
            />
            <section className="documenti-hub__drive" aria-label="Cartelle Google Drive collegate">
              <h2 className="documenti-hub__drive-titolo">
                {contabili.length} {contabili.length === 1 ? 'cartella che alimenta' : 'cartelle che alimentano'} la contabilità
              </h2>
              <p className="documenti-hub__drive-nota">Il gestionale legge questi documenti e ne fa entrare i dati.</p>
              <div className="documenti-hub__drive-grid">{contabili.map(scheda)}</div>
              <h2 className="documenti-hub__drive-titolo">
                {consultazione.length} {consultazione.length === 1 ? 'cartella solo da consultare' : 'cartelle solo da consultare'}
              </h2>
              <p className="documenti-hub__drive-nota">Si aprono e si leggono, ma non entrano in contabilità.</p>
              <div className="documenti-hub__drive-grid">{consultazione.map(scheda)}</div>
            </section>
          </>
        );
      })()}

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

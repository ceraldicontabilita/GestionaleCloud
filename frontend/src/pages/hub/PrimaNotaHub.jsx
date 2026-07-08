import React, { lazy, Suspense, useState, useEffect } from 'react';
import { BrushCleaning, BookOpenText, ClipboardList } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';

const PrimaNotaContent = lazy(() => import('../PrimaNota.jsx'));
const DatiProvvisoriContent = lazy(() => import('../DatiProvvisoriPage.jsx'));
const PuliziaContent = lazy(() => import('../PuliziaPrimaNota.jsx'));

const Loading = () => (
  <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
    <div
      style={{
        width: 32,
        height: 32,
        border: '3px solid #e2e8f0',
        borderTop: '3px solid #2563eb',
        borderRadius: '50%',
        animation: 'spin 1s linear infinite',
        margin: '0 auto 12px',
      }}
    />
    Caricamento...
  </div>
);

export default function PrimaNotaHub() {
  const { anno } = useAnnoGlobale();
  const location = useLocation();
  const navigate = useNavigate();
  const path = location.pathname;
  const isProvvisori = path.includes('provvisori') || path.includes('dati-provvisori');
  const isPulizia = path.includes('/pulizia');
  const activeTab = isPulizia ? 'pulizia' : isProvvisori ? 'provvisori' : 'prima-nota';

  // Mount-once: la vista viene montata al primo accesso e mantenuta
  const [visitedProvvisori, setVisitedProvvisori] = useState(isProvvisori);
  const [visitedPrimaNota, setVisitedPrimaNota] = useState(!isProvvisori && !isPulizia);
  const [visitedPulizia, setVisitedPulizia] = useState(isPulizia);

  useEffect(() => {
    if (isPulizia) setVisitedPulizia(true);
    else if (isProvvisori) setVisitedProvvisori(true);
    else setVisitedPrimaNota(true);
  }, [isProvvisori, isPulizia]);

  return (
    <div style={{ width: '100%' }}>
      <div
        style={{
          display: 'flex',
          gap: 8,
          padding: '8px 12px',
          background: 'white',
          borderBottom: '1px solid #e2e8f0',
          borderRadius: '8px 8px 0 0',
          flexWrap: 'wrap',
          marginBottom: 16,
        }}
      >
        {[
          { id: 'prima-nota', label: 'Prima nota', Icon: BookOpenText, to: '/prima-nota' },
          { id: 'provvisori', label: 'Provvisori', Icon: ClipboardList, to: '/dati-provvisori' },
          { id: 'pulizia', label: 'Pulizia', Icon: BrushCleaning, to: '/prima-nota/pulizia' },
        ].map(({ id, label, Icon, to }) => {
          const isActive = activeTab === id;
          return (
            <button
              key={id}
              onClick={() => navigate(to)}
              data-testid={`tab-prima-nota-${id}`}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '9px 13px',
                minHeight: 40,
                borderRadius: 6,
                border: `1px solid ${isActive ? '#0f2744' : '#e2e8f0'}`,
                background: isActive ? '#0f2744' : '#fff',
                color: isActive ? '#fff' : '#64748b',
                fontWeight: isActive ? 700 : 500,
                fontSize: 12,
                cursor: 'pointer',
              }}
            >
              <Icon size={14} />
              <span>{label}</span>
            </button>
          );
        })}
      </div>
      <div style={{ display: activeTab === 'prima-nota' ? 'block' : 'none' }}>
        <Suspense fallback={<Loading />}>
          {visitedPrimaNota && <PrimaNotaContent key={`prima-nota-${anno}`} />}
        </Suspense>
      </div>
      <div style={{ display: activeTab === 'provvisori' ? 'block' : 'none' }}>
        <Suspense fallback={<Loading />}>
          {visitedProvvisori && <DatiProvvisoriContent key={`dati-provvisori-${anno}`} />}
        </Suspense>
      </div>
      <div style={{ display: activeTab === 'pulizia' ? 'block' : 'none' }}>
        <Suspense fallback={<Loading />}>
          {visitedPulizia && <PuliziaContent key={`pulizia-prima-nota-${anno}`} />}
        </Suspense>
      </div>
    </div>
  );
}

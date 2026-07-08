import React, { lazy, Suspense, useState, useEffect } from 'react';
import { FileStack, Wallet } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';

const ArchivioContent = lazy(() => import('../ArchivioFattureRicevute.jsx'));
const CorrispettiviContent = lazy(() => import('../Corrispettivi.jsx'));

const Loading = () => (
  <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
    <div
      style={{
        width: 32,
        height: 32,
        border: '3px solid #e2e8f0',
        borderTop: '3px solid #3b82f6',
        borderRadius: '50%',
        animation: 'spin 1s linear infinite',
        margin: '0 auto 12px',
      }}
    />
    <style>{`@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}`}</style>
    Caricamento...
  </div>
);

export default function FattureHub() {
  const { anno } = useAnnoGlobale();
  const location = useLocation();
  const navigate = useNavigate();
  const isCorresp = location.pathname.includes('/corrispettivi');

  // Mount-once: traccia quale vista è stata visitata
  const [visitedCorresp, setVisitedCorresp] = useState(isCorresp);
  const [visitedArchivio, setVisitedArchivio] = useState(!isCorresp);

  useEffect(() => {
    if (isCorresp) setVisitedCorresp(true);
    else setVisitedArchivio(true);
  }, [isCorresp]);

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
          { id: 'archivio', label: 'Archivio fatture', Icon: FileStack, to: '/fatture' },
          { id: 'corrispettivi', label: 'Corrispettivi', Icon: Wallet, to: '/fatture/corrispettivi' },
        ].map(({ id, label, Icon, to }) => {
          const isActive = (id === 'corrispettivi') === isCorresp;
          return (
            <button
              key={id}
              onClick={() => navigate(to)}
              data-testid={`tab-fatture-${id}`}
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
      <div style={{ display: isCorresp ? 'none' : 'block' }}>
        <Suspense fallback={<Loading />}>
          {visitedArchivio && <ArchivioContent key={`archivio-${anno}`} />}
        </Suspense>
      </div>
      <div style={{ display: isCorresp ? 'block' : 'none' }}>
        <Suspense fallback={<Loading />}>
          {visitedCorresp && <CorrispettiviContent key={`corrispettivi-${anno}`} />}
        </Suspense>
      </div>
    </div>
  );
}

import React, { lazy, Suspense } from 'react';
import { useLocation } from 'react-router-dom';

const RiconciliazioneContent = lazy(() => import('../RiconciliazioneUnificata.jsx'));
const PaypalContent = lazy(() => import('../RiconciliazionePaypal.jsx'));
const AssegniContent = lazy(() => import('../GestioneAssegni.jsx'));
const BonificiContent = lazy(() => import('../ArchivioBonifici.jsx'));
const CoerenzaPOSContent = lazy(() => import('../CoerenzaPOSCorrispettivi.jsx'));

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

export default function RiconciliazioneHub() {
  const location = useLocation();
  const path = location.pathname;

  // Determina quale contenuto mostrare
  const getContent = () => {
    if (path.includes('/archivio-bonifici')) {
      return <BonificiContent />;
    }
    if (path.includes('/gestione-assegni') || path.includes('/assegni')) {
      return <AssegniContent />;
    }
    if (path.includes('/paypal')) {
      return <PaypalContent />;
    }
    if (path.includes('/coerenza-pos')) {
      return <CoerenzaPOSContent />;
    }
    // Default: riconciliazione bancaria
    return <RiconciliazioneContent />;
  };

  return (
    <div style={{ width: '100%' }}>
      <Suspense fallback={<Loading />}>{getContent()}</Suspense>
    </div>
  );
}

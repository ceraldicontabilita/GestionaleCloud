import React, { lazy, Suspense } from 'react';
import { useLocation } from 'react-router-dom';

const PianoContiContent = lazy(() => import('../PianoDeiConti.jsx'));
const ControlloContent = lazy(() => import('../ControlloMensile.jsx'));
const MotoreContent = lazy(() => import('../MotoreContabile.jsx'));
const CalendarioContent = lazy(() => import('../CalendarioFiscale.jsx'));
const CespitiContent = lazy(() => import('../GestioneCespiti.jsx'));
const FinanziariaContent = lazy(() => import('../Finanziaria.jsx'));
const ChiusuraContent = lazy(() => import('../ChiusuraEsercizio.jsx'));
const BilancioContent = lazy(() => import('../Bilancio.jsx'));

const Loading = () => (
  <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
    <div style={{
      width: 32, height: 32,
      border: '3px solid #e2e8f0',
      borderTop: '3px solid #2563eb',
      borderRadius: '50%',
      animation: 'spin 1s linear infinite',
      margin: '0 auto 12px'
    }} />
    Caricamento...
  </div>
);

export default function ContabilitaHub() {
  const location = useLocation();
  const path = location.pathname;

  const getContent = () => {
    if (path.includes('/piano-dei-conti')) return <PianoContiContent />;
    if (path.includes('/bilancio')) return <BilancioContent />;
    if (path.includes('/cespiti')) return <CespitiContent />;
    if (path.includes('/controllo-mensile')) return <ControlloContent />;
    if (path.includes('/motore-contabile')) return <MotoreContent />;
    if (path.includes('/calendario-fiscale')) return <CalendarioContent />;
    if (path.includes('/finanziaria')) return <FinanziariaContent />;
    if (path.includes('/chiusura')) return <ChiusuraContent />;
    return <PianoContiContent />;
  };

  return (
    <div style={{ padding: '16px 24px', minHeight: '100vh', background: '#f8fafc' }}>
      <Suspense fallback={<Loading />}>
        {getContent()}
      </Suspense>
    </div>
  );
}

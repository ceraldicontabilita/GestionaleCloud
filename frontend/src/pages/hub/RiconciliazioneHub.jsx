import React, { lazy, Suspense } from 'react';
import { ArrowLeftRight, Banknote, CreditCard, Landmark, ScrollText } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';

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
  const { anno } = useAnnoGlobale();
  const location = useLocation();
  const navigate = useNavigate();
  const path = location.pathname;

  const tabs = [
    { id: 'bancaria', label: 'Bancaria', Icon: Landmark, to: '/riconciliazione' },
    { id: 'bonifici', label: 'Archivio bonifici', Icon: ArrowLeftRight, to: '/riconciliazione/archivio-bonifici' },
    { id: 'assegni', label: 'Assegni', Icon: ScrollText, to: '/riconciliazione/assegni' },
    { id: 'paypal', label: 'PayPal', Icon: CreditCard, to: '/riconciliazione/paypal' },
    { id: 'coerenza-pos', label: 'Coerenza POS', Icon: Banknote, to: '/riconciliazione/coerenza-pos' },
  ];

  const activeTab = path.includes('/archivio-bonifici')
    ? 'bonifici'
    : path.includes('/gestione-assegni') || path.includes('/assegni')
      ? 'assegni'
      : path.includes('/paypal')
        ? 'paypal'
        : path.includes('/coerenza-pos')
          ? 'coerenza-pos'
          : 'bancaria';

  // Determina quale contenuto mostrare
  const getContent = () => {
    if (path.includes('/archivio-bonifici')) {
      return <BonificiContent key={`bonifici-${anno}`} />;
    }
    if (path.includes('/gestione-assegni') || path.includes('/assegni')) {
      return <AssegniContent key={`assegni-${anno}`} />;
    }
    if (path.includes('/paypal')) {
      return <PaypalContent key={`paypal-${anno}`} />;
    }
    if (path.includes('/coerenza-pos')) {
      return <CoerenzaPOSContent key={`coerenza-pos-${anno}`} />;
    }
    // Default: riconciliazione bancaria
    return <RiconciliazioneContent key={`riconciliazione-${anno}`} />;
  };

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
        {tabs.map(({ id, label, Icon, to }) => {
          const isActive = activeTab === id;
          return (
            <button
              key={id}
              onClick={() => navigate(to)}
              data-testid={`tab-riconciliazione-${id}`}
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
      <Suspense fallback={<Loading />}>{getContent()}</Suspense>
    </div>
  );
}

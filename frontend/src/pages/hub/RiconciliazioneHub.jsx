import React, { lazy, Suspense } from 'react';
import { ArrowLeftRight, Banknote, CreditCard, Landmark, ScrollText } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { HubTabs } from '../../components/ds';

const RiconciliazioneContent = lazy(() => import('../RiconciliazioneUnificata.jsx'));
const PaypalContent = lazy(() => import('../RiconciliazionePaypal.jsx'));
const AssegniContent = lazy(() => import('../GestioneAssegni.jsx'));
const BonificiContent = lazy(() => import('../ArchivioBonifici.jsx'));
const CoerenzaPOSContent = lazy(() => import('../CoerenzaPOSCorrispettivi.jsx'));
const F24Content = lazy(() => import('../F24.jsx'));

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
    if (path.includes('/f24')) {
      return <F24Content key={`f24-${anno}`} />;
    }
    return <RiconciliazioneContent key={`riconciliazione-${anno}`} />;
  };

  const nascondiTabs =
    path.includes('/f24') || path.includes('/coerenza-pos') || path.includes('/paypal');

  return (
    <div style={{ width: '100%' }}>
      {!nascondiTabs && (
        <HubTabs
          testIdPrefix="tab-riconciliazione"
          activeId={activeTab}
          onSelect={tab => navigate(tab.to)}
          tabs={tabs}
        />
      )}
      <Suspense fallback={<Loading />}>{getContent()}</Suspense>
    </div>
  );
}

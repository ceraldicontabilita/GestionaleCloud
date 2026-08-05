import React, { lazy, Suspense } from 'react';
import { ArrowLeftRight, Banknote, CreditCard, Landmark, Receipt, ScrollText } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { HubTabs, PageLoader } from '../../components/ds';

const RiconciliazioneContent = lazy(() => import('../RiconciliazioneUnificata.jsx'));
const PaypalContent = lazy(() => import('../RiconciliazionePaypal.jsx'));
const AssegniContent = lazy(() => import('../GestioneAssegni.jsx'));
const BonificiContent = lazy(() => import('../ArchivioBonifici.jsx'));
const CoerenzaPOSContent = lazy(() => import('../CoerenzaPOSCorrispettivi.jsx'));


export default function RiconciliazioneHub() {
  const { anno } = useAnnoGlobale();
  const location = useLocation();
  const navigate = useNavigate();
  const path = location.pathname;

  const tabs = [
    { id: 'bancaria', label: 'Bancaria', Icon: Landmark, to: '/riconciliazione' },
    { id: 'f24', label: 'F24', Icon: Receipt, to: '/riconciliazione/f24' },
    { id: 'bonifici', label: 'Archivio bonifici', Icon: ArrowLeftRight, to: '/riconciliazione/archivio-bonifici' },
    { id: 'assegni', label: 'Assegni', Icon: ScrollText, to: '/riconciliazione/assegni' },
    { id: 'paypal', label: 'PayPal', Icon: CreditCard, to: '/riconciliazione/paypal' },
    { id: 'coerenza-pos', label: 'Coerenza POS', Icon: Banknote, to: '/riconciliazione/coerenza-pos' },
  ];

  const activeTab = path.includes('/f24')
    ? 'f24'
    : path.includes('/archivio-bonifici')
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
    if (path.includes('/f24')) {
      return <RiconciliazioneContent key={`f24-${anno}`} />;
    }
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

  // Barra hub sempre presente: ora è solo «← Indietro» + il selettore di
  // sezione (richiesta utente 12/07: niente fila di tab delle altre pagine).
  return (
    <div style={{ width: '100%' }}>
      <HubTabs
        testIdPrefix="tab-riconciliazione"
        activeId={activeTab}
        onSelect={tab => navigate(tab.to)}
        tabs={tabs}
      />
      <Suspense fallback={<PageLoader />}>{getContent()}</Suspense>
    </div>
  );
}

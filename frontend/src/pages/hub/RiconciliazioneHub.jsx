import React, { lazy, Suspense, useEffect, useState } from 'react';
import { ArrowLeftRight, Banknote, CreditCard, Landmark, Receipt, ScrollText } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import api from '../../api';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { HubTabs, PageLoader } from '../../components/ds';

const RiconciliazioneContent = lazy(() => import('../RiconciliazioneUnificata.jsx'));
const MovimentiBancaContent = lazy(() => import('../VerificaMovimentiBanca.jsx'));
const PagoPAContent = lazy(() => import('../GestionePagoPA.jsx'));
const PaypalContent = lazy(() => import('../RiconciliazionePaypal.jsx'));
const AssegniContent = lazy(() => import('../GestioneAssegni.jsx'));
const BonificiContent = lazy(() => import('../ArchivioBonifici.jsx'));
const CoerenzaPOSContent = lazy(() => import('../CoerenzaPOSCorrispettivi.jsx'));

function intervalloAnno(anno) {
  const annoNumero = Number(anno);
  const oggi = new Date();
  const annoCorrente = oggi.getFullYear();
  const start = `${annoNumero}-01-01`;
  const end = annoNumero < annoCorrente
    ? `${annoNumero}-12-31`
    : annoNumero === annoCorrente
      ? oggi.toISOString().slice(0, 10)
      : `${annoNumero}-01-01`;
  return { start, end };
}

export default function RiconciliazioneHub() {
  const { anno } = useAnnoGlobale();
  const location = useLocation();
  const navigate = useNavigate();
  const path = location.pathname;
  const [paypalRefreshKey, setPaypalRefreshKey] = useState(0);

  const tabs = [
    { id: 'bancaria', label: 'Riconciliazione', Icon: Landmark, to: '/riconciliazione' },
    { id: 'movimenti-banca', label: 'Indice operazioni', Icon: Banknote, to: '/riconciliazione/movimenti-banca' },
    { id: 'f24', label: 'F24', Icon: Receipt, to: '/riconciliazione/f24' },
    { id: 'pagopa', label: 'PagoPA', Icon: Receipt, to: '/riconciliazione/pagopa' },
    { id: 'bonifici', label: 'Bonifici', Icon: ArrowLeftRight, to: '/riconciliazione/archivio-bonifici' },
    { id: 'assegni', label: 'Assegni', Icon: ScrollText, to: '/riconciliazione/assegni' },
    { id: 'paypal', label: 'PayPal', Icon: CreditCard, to: '/riconciliazione/paypal' },
    { id: 'coerenza-pos', label: 'Coerenza POS', Icon: Banknote, to: '/riconciliazione/coerenza-pos' },
  ];

  const activeTab = path.includes('/movimenti-banca')
    ? 'movimenti-banca'
    : path.includes('/f24')
      ? 'f24'
      : path.includes('/pagopa')
        ? 'pagopa'
        : path.includes('/archivio-bonifici')
          ? 'bonifici'
          : path.includes('/gestione-assegni') || path.includes('/assegni')
            ? 'assegni'
            : path.includes('/paypal')
              ? 'paypal'
              : path.includes('/coerenza-pos')
                ? 'coerenza-pos'
                : 'bancaria';

  useEffect(() => {
    if (activeTab !== 'paypal') return undefined;
    let annullato = false;

    const sincronizzaPaypal = async () => {
      try {
        const stato = await api.get('/api/paypal-api/status');
        if (stato.data?.api_configurata === false) return;
        const { start, end } = intervalloAnno(anno);
        if (end < start) return;
        await api.post('/api/paypal-api/sync', { start_date: start, end_date: end });
        if (!annullato) setPaypalRefreshKey(valore => valore + 1);
      } catch (errore) {
        // La pagina PayPal gestisce gia lo stato di errore dei servizi.
        // La sincronizzazione automatica non deve impedire la consultazione.
        console.error('Sincronizzazione automatica PayPal non riuscita', errore);
      }
    };

    sincronizzaPaypal();
    return () => { annullato = true; };
  }, [activeTab, anno]);

  const getContent = () => {
    if (path.includes('/movimenti-banca')) {
      return <MovimentiBancaContent key={`movimenti-banca-${anno}`} />;
    }
    if (path.includes('/f24')) {
      return <RiconciliazioneContent key={`f24-${anno}`} />;
    }
    if (path.includes('/pagopa')) {
      return <PagoPAContent key={`pagopa-${anno}`} />;
    }
    if (path.includes('/archivio-bonifici')) {
      return <BonificiContent key={`bonifici-${anno}`} />;
    }
    if (path.includes('/gestione-assegni') || path.includes('/assegni')) {
      return <AssegniContent key={`assegni-${anno}`} />;
    }
    if (path.includes('/paypal')) {
      return <PaypalContent key={`paypal-${anno}-${paypalRefreshKey}`} />;
    }
    if (path.includes('/coerenza-pos')) {
      return <CoerenzaPOSContent key={`coerenza-pos-${anno}`} />;
    }
    return <RiconciliazioneContent key={`riconciliazione-${anno}`} />;
  };

  return (
    <div style={{ width: '100%' }}>
      {activeTab === 'paypal' && (
        <style>{`
          [data-testid="sync-paypal-api-btn"] { display: none !important; }
          select:has(+ [data-testid="sync-paypal-api-btn"]) { display: none !important; }
        `}</style>
      )}
      <HubTabs
        testIdPrefix="tab-riconciliazione"
        activeId={activeTab}
        onSelect={tab => navigate(tab.to)}
        tabs={tabs}
        mode="visible"
      />
      <Suspense fallback={<PageLoader />}>{getContent()}</Suspense>
    </div>
  );
}

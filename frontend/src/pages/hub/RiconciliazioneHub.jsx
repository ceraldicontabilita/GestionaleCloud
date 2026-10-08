import React, { lazy, Suspense, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import api from '../../api';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { PageLoader } from '../../components/ds';
import { PageHeader } from '../../components/ds/PageHeader';
import { sezioneRiconciliazione } from './sezioneRiconciliazione';

const RiconciliazioneContent = lazy(() => import('../RiconciliazioneUnificata.jsx'));
const MovimentiBancaContent = lazy(() => import('../VerificaMovimentiBanca.jsx'));
const PagoPAContent = lazy(() => import('../GestionePagoPA.jsx'));
const PaypalContent = lazy(() => import('../RiconciliazionePaypal.jsx'));
const AssegniContent = lazy(() => import('../GestioneAssegni.jsx'));
const BonificiContent = lazy(() => import('../ArchivioBonifici.jsx'));
const CoerenzaPOSContent = lazy(() => import('../CoerenzaPOSCorrispettivi.jsx'));
const RegoleRiconoscimentoBancaContent = lazy(() => import('../RegoleRiconoscimentoBanca.jsx'));

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
  const sezione = sezioneRiconciliazione(location.pathname);
  const [paypalRefreshKey, setPaypalRefreshKey] = useState(0);

  // Le schede le disegna SchedeHub dalla mappa di navigazione; qui restano
  // solo i nomi per la testata delle sezioni che non ne hanno una propria.
  const nomiSezione = {
    banca: 'Banca', stipendi: 'Stipendi', documenti: 'Documenti', f24: 'F24',
    bonifici: 'Bonifici', assegni: 'Assegni', 'coerenza-pos': 'Coerenza POS',
  };

  const activeTab = sezione === '' ? 'bancaria' : sezione;
  // Queste sezioni hanno gia' una testata loro (titolo, perche', pastiglie):
  // per le altre la mette l'hub, con il nome della scheda aperta.
  const conTestataPropria = ['movimenti-banca', 'pagopa', 'paypal', 'regole-banca'].includes(activeTab);
  const titoloSezione = activeTab === 'bancaria'
    ? 'Riconciliazione'
    : (nomiSezione[activeTab] || 'Riconciliazione');

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
        console.error('Sincronizzazione automatica PayPal non riuscita', errore);
      }
    };

    sincronizzaPaypal();
    return () => { annullato = true; };
  }, [activeTab, anno]);

  const getContent = () => {
    if (sezione === 'movimenti-banca') {
      return <MovimentiBancaContent key={`movimenti-banca-${anno}`} />;
    }
    if (sezione === 'f24') {
      return <RiconciliazioneContent key={`f24-${anno}`} />;
    }
    if (sezione === 'pagopa') {
      return <PagoPAContent key={`pagopa-${anno}`} />;
    }
    if (sezione === 'bonifici') {
      return <BonificiContent key={`bonifici-${anno}`} />;
    }
    if (sezione === 'assegni') {
      return <AssegniContent key={`assegni-${anno}`} />;
    }
    if (sezione === 'paypal') {
      return <PaypalContent key={`paypal-${anno}-${paypalRefreshKey}`} />;
    }
    if (sezione === 'coerenza-pos') {
      return <CoerenzaPOSContent key={`coerenza-pos-${anno}`} />;
    }
    if (sezione === 'regole-banca') {
      return <RegoleRiconoscimentoBancaContent key="regole-banca" />;
    }
    return <RiconciliazioneContent key={`riconciliazione-${anno}-${sezione || 'riepilogo'}`} />;
  };

  return (
    <div style={{ width: '100%' }}>
      {activeTab === 'paypal' && (
        <style>{`
          [data-testid="sync-paypal-api-btn"] { display: none !important; }
          select:has(+ [data-testid="sync-paypal-api-btn"]) { display: none !important; }
        `}</style>
      )}
      {!conTestataPropria && <PageHeader title={titoloSezione} style={{ marginBottom: 14 }} />}
      <Suspense fallback={<PageLoader />}>{getContent()}</Suspense>
    </div>
  );
}

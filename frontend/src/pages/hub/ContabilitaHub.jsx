import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { HubTabs, PageLoader } from '../../components/ds';
import {
  sezioneContabilita,
  sezioneContabilitaSconosciuta,
} from './sezioneContabilita';

const PianoContiContent = lazy(() => import('../PianoDeiConti.jsx'));
const BilancioContent = lazy(() => import('../Bilancio.jsx'));
const BilancioVerContent = lazy(() => import('../BilancioVerifica.jsx'));
const LibroGiornaleContent = lazy(() => import('../LibroGiornale.jsx'));
const ControlloContent = lazy(() => import('../ControlloMensile.jsx'));
const CalendarioContent = lazy(() => import('../CalendarioFiscale.jsx'));
const CespitiContent = lazy(() => import('../GestioneCespiti.jsx'));
const FinanziariaContent = lazy(() => import('../Finanziaria.jsx'));
const ChiusuraContent = lazy(() => import('../ChiusuraEsercizio.jsx'));
const BudgetContent = lazy(() => import('../BudgetPrevisionale.jsx'));
const MutuiContent = lazy(() => import('../Mutui.jsx'));
const AvanzataContent = lazy(() => import('../ContabilitaAvanzata.jsx'));
const UtileObiettivoContent = lazy(() => import('../UtileObiettivo.jsx'));
const PrevisioniAcquistiContent = lazy(() => import('../PrevisioniAcquisti.jsx'));
const DatiIsaContent = lazy(() => import('../DatiIsa.jsx'));

export default function ContabilitaHub() {
  const { anno } = useAnnoGlobale();
  const location = useLocation();
  const activeTab = sezioneContabilita(location.pathname);
  const sezioneSconosciuta = sezioneContabilitaSconosciuta(location.pathname);

  const [visitedTabs, setVisitedTabs] = useState(
    () => new Set([sezioneContabilita(location.pathname)])
  );

  useEffect(() => {
    const t = sezioneContabilita(location.pathname);
    setVisitedTabs(prev => {
      const n = new Set(prev);
      n.add(t);
      return n;
    });
  }, [location.pathname]);

  useEffect(() => {
    setVisitedTabs(new Set([sezioneContabilita(location.pathname)]));
  }, [anno]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={{ width: '100%' }}>
      <HubTabs testIdPrefix="tab-contabilita" style={{ marginBottom: 0 }} />

      <div style={{ padding: '16px 0 0 0' }}>
        {sezioneSconosciuta && (
          <div
            style={{
              padding: '10px 14px',
              background: '#fffbeb',
              border: '1px solid #fcd34d',
              borderRadius: 8,
              color: '#92400e',
              fontSize: 13,
              marginBottom: 12,
            }}
            data-testid="contabilita-sezione-sconosciuta"
          >
            La sezione «{location.pathname.replace('/contabilita/', '')}» non esiste:
            viene mostrato il Piano dei Conti. Se ci sei arrivato da un link interno,
            segnalalo.
          </div>
        )}
        {[
          { id: 'piano-conti', C: PianoContiContent },
          { id: 'bilancio', C: BilancioContent },
          { id: 'verifica', C: BilancioVerContent },
          { id: 'giornale', C: LibroGiornaleContent },
          { id: 'controllo', C: ControlloContent },
          { id: 'calendario', C: CalendarioContent },
          { id: 'cespiti', C: CespitiContent },
          { id: 'finanziaria', C: FinanziariaContent },
          { id: 'chiusura', C: ChiusuraContent },
          { id: 'budget', C: BudgetContent },
          { id: 'mutui', C: MutuiContent },
          { id: 'avanzata', C: AvanzataContent },
          { id: 'utile', C: UtileObiettivoContent },
          { id: 'previsioni-acquisti', C: PrevisioniAcquistiContent },
          { id: 'dati-isa', C: DatiIsaContent },
        ].map(({ id, C }) => (
          <div key={id} style={{ display: activeTab === id ? 'block' : 'none' }}>
            <Suspense fallback={<PageLoader />}>
              {visitedTabs.has(id) && <C key={`${id}-${anno}`} />}
            </Suspense>
          </div>
        ))}
      </div>
    </div>
  );
}

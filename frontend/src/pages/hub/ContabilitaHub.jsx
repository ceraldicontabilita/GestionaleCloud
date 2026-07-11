import React, { lazy, Suspense, useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  BarChart3, TrendingUp, BadgeCheck, CalendarCheck, Calendar,
  Building2, Banknote, Lock, ClipboardList, Landmark, Wrench,
  Target, Package,
} from 'lucide-react';
import { useAnnoGlobale } from '../../contexts/AnnoContext';
import { HubTabs, PageLoader } from '../../components/ds';

const PianoContiContent = lazy(() => import('../PianoDeiConti.jsx'));
const BilancioContent = lazy(() => import('../Bilancio.jsx'));
const BilancioVerContent = lazy(() => import('../BilancioVerifica.jsx'));
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

// Design system Ceraldi ERP: un solo colore attivo (navy #0f2744), icone
// Lucide, niente arcobaleno di colori per-tab (era incoerente col resto
// del sito e illeggibile).
const TABS = [
  { id: 'piano-conti', label: 'Piano dei Conti', Icon: BarChart3 },
  { id: 'bilancio', label: 'Bilancio', Icon: TrendingUp },
  { id: 'verifica', label: 'Verifica Bilancio', Icon: BadgeCheck },
  { id: 'controllo', label: 'Controllo Mensile', Icon: CalendarCheck },
  { id: 'calendario', label: 'Calendario Fiscale', Icon: Calendar },
  { id: 'cespiti', label: 'Cespiti', Icon: Building2 },
  { id: 'finanziaria', label: 'Finanziaria', Icon: Banknote },
  { id: 'chiusura', label: 'Chiusura Esercizio', Icon: Lock },
  { id: 'budget', label: 'Budget', Icon: ClipboardList },
  { id: 'mutui', label: 'Mutui', Icon: Landmark },
  { id: 'avanzata', label: 'Contab. Avanzata', Icon: Wrench },
  { id: 'utile', label: 'Utile Obiettivo', Icon: Target },
  { id: 'previsioni-acquisti', label: 'Previsioni Acquisti', Icon: Package },
];


const getTabFromPath = pathname => {
  if (pathname.includes('/piano-dei-conti') || pathname.includes('/contabilita/piano-conti'))
    return 'piano-conti';
  if (pathname.includes('/bilancio-verifica') || pathname.includes('/contabilita/verifica'))
    return 'verifica';
  if (pathname.includes('/bilancio')) return 'bilancio';
  if (pathname.includes('/controllo-mensile') || pathname.includes('/contabilita/controllo'))
    return 'controllo';
  if (pathname.includes('/calendario-fiscale') || pathname.includes('/contabilita/calendario'))
    return 'calendario';
  if (pathname.includes('/cespiti')) return 'cespiti';
  if (pathname.includes('/finanziaria')) return 'finanziaria';
  if (pathname.includes('/chiusura')) return 'chiusura';
  if (pathname.includes('/budget')) return 'budget';
  if (pathname.includes('/mutui')) return 'mutui';
  if (pathname.includes('/contabilita-avanzata') || pathname.includes('/contabilita/avanzata'))
    return 'avanzata';
  if (pathname.includes('/utile-obiettivo') || pathname.includes('/contabilita/utile'))
    return 'utile';
  if (pathname.includes('/previsioni-acquisti') || pathname.includes('/contabilita/previsioni-acquisti'))
    return 'previsioni-acquisti';
  if (pathname.includes('/contabilita/')) {
    const m = pathname.match(/\/contabilita\/([\w-]+)/);
    if (m && TABS.find(t => t.id === m[1])) return m[1];
  }
  return 'piano-conti';
};

export default function ContabilitaHub() {
  const { anno } = useAnnoGlobale();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState(null);

  // UNICA fonte di verità per il tab attivo: il PATH. (Prima c'era anche un
  // hash "#tab=..." aggiornato in parallelo: stato duplicato, URL incoerenti
  // e back button imprevedibile — rimosso.)
  const activeTab = getTabFromPath(location.pathname);

  // Sezione richiesta ma inesistente (es. /contabilita/qualcosa-a-caso):
  // si ripiega su Piano dei Conti ma AVVISANDO, non in silenzio.
  const sezioneSconosciuta =
    activeTab === 'piano-conti' &&
    /\/contabilita\/.+/.test(location.pathname) &&
    !/piano-?(dei-)?conti/.test(location.pathname);

  // Traccia i tab visitati: una volta montato, il componente NON viene
  // smontato finché si resta nello stesso anno. Al CAMBIO ANNO si torna al
  // solo tab attivo: prima tutti i tab visitati si rimontavano insieme
  // (key legata all'anno) e partivano richieste duplicate in parallelo.
  const [visitedTabs, setVisitedTabs] = useState(
    () => new Set([getTabFromPath(location.pathname)])
  );

  useEffect(() => {
    const t = getTabFromPath(location.pathname);
    setVisitedTabs(prev => {
      const n = new Set(prev);
      n.add(t);
      return n;
    });
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setVisitedTabs(new Set([getTabFromPath(location.pathname)]));
  }, [anno]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleTabChange = tabId => {
    setError(null);
    navigate(tabId === 'piano-conti' ? '/contabilita' : `/contabilita/${tabId}`);
  };

  return (
    <div style={{ width: '100%' }}>
      {/* Tab Bar — design system: navy attivo. Tutti i tab SEMPRE visibili
          (a capo automatico): niente scroll orizzontale che nasconde le voci. */}
      <HubTabs
        testIdPrefix="tab-contabilita"
        activeId={activeTab}
        onSelect={tab => handleTabChange(tab.id)}
        tabs={TABS}
        style={{ marginBottom: 0 }}
      />

      {/* Tab Content - mount-once */}
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
            ⚠️ La sezione «{location.pathname.replace('/contabilita/', '')}» non esiste:
            viene mostrato il Piano dei Conti. Se ci sei arrivato da un link interno,
            segnalalo.
          </div>
        )}
        {error && (
          <div
            style={{
              padding: 16,
              background: '#fef2f2',
              borderRadius: 8,
              color: '#dc2626',
              marginBottom: 16,
            }}
          >
            Errore: {error}
          </div>
        )}
        {[
          { id: 'piano-conti', C: PianoContiContent },
          { id: 'bilancio', C: BilancioContent },
          { id: 'verifica', C: BilancioVerContent },
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

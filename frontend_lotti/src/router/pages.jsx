// REGISTRO PAGINE dichiarativo — unico punto che collega id pagina → vista.
// Estratto dal grande blocco condizionale di App.js (fase 2, 24/07/2026).
// id/etichette/menu vivono in config/navigation.js, titoli in config/pageMeta.js,
// permessi in config/permissions.js: qui SOLO il componente da renderizzare.
// ctx = stato e callback condivisi passati da App.js (vedi renderPagina).
import ErrorBoundary from "../components/ErrorBoundary";
import {
  DisinfestazioneView,
  SanificazioneView,
  TemperatureNegativeView,
  TemperaturePositiveView,
  AnomalieView,
  ManualeHACCPView,
  SchedeTecnicheView,
} from "../components/haccp";
import OrdiniView from "../components/haccp/OrdiniView";
import { StoricoProduzioniView } from "../components/haccp/StoricoProduzioniView";
import BackofficeView from "../components/haccp/BackofficeView";
import CorrispettiviView from "../components/haccp/CorrispettiviView";
import FornitoriList from "../components/haccp/FornitoriList";
import LottiList from "../components/haccp/LottiList";
import MateriePrimeList from "../components/haccp/MateriePrimeList";
import DashboardView from "../components/haccp/DashboardView";
import GelatiView from "../components/haccp/GelatiView";
import BackupView from "../components/haccp/BackupView";
import RegistroAllergeniView from "../components/haccp/RegistroAllergeniView";
import RegistroHACCPView from "../components/haccp/RegistroHACCPView";
import ImpostazioniPersonaleView from "../components/haccp/ImpostazioniPersonaleView";
import DizionarioIngredientiView from "../components/haccp/DizionarioIngredientiView";
import StampantiConfigView from "../components/haccp/StampantiConfigView";
import ManualeView from "../components/haccp/ManualeView";
import ConfiguraWizard from "../components/haccp/ConfiguraWizard";
import ControlloOlioView from "../components/haccp/ControlloOlioView";
import TemperatureCotturaView from "../components/haccp/TemperatureCotturaView";
import RicezioneMerceView from "../components/haccp/RicezioneMerceView";
import ControlloDatiView from "../components/haccp/ControlloDatiView";
import CataloghiEsterniView from "../components/haccp/CataloghiEsterniView";
import CollaudiView from "../components/haccp/CollaudiView";
import AttrezzatureView from "../components/haccp/AttrezzatureView";
import CosaUsareOggiView from "../components/haccp/CosaUsareOggiView";
import DashboardEconomicaView from "../components/haccp/DashboardEconomicaView";
import ProduzioneConsigliataView from "../components/haccp/ProduzioneConsigliataView";
import MappaTracciabilitaView from "../components/haccp/MappaTracciabilitaView";
import ControlloMagazzinoView from "../components/haccp/ControlloMagazzinoView";
import ConfrontoProdottoView from "../components/haccp/ConfrontoProdottoView";
import { ImportaFatture } from "../components/haccp/ImportaFattureView";
import ProdottiHubView from "../components/haccp/ProdottiHubView";

export const ProdottiConTabFornitore = ProdottiHubView;

// Mappa id → funzione di render. Ogni voce riceve ctx (stato condiviso da
// App.js) e ritorna il JSX della pagina. safe=false → senza ErrorBoundary
// (comportamento storico dei registri HACCP semplici, invariato).
const PAGINE = {
  dashboard: { safe: false, render: (ctx) => <DashboardView stats={ctx.stats} onRefresh={ctx.refreshAll} onNavigate={ctx.setActiveTab} /> },
  gelati: { render: () => <GelatiView /> },
  fatture: { render: (ctx) => <ImportaFatture imp={ctx.imp} startImport={ctx.startImport} onImportComplete={ctx.onImportComplete} /> },
  fornitori: { safe: false, render: (ctx) => <FornitoriList fornitori={ctx.fornitori} onRefresh={ctx.fetchFornitori} /> },
  materie: { render: () => <MateriePrimeList /> },
  prodotti: { render: () => <ProdottiConTabFornitore /> },
  magazzino_prodotti: { render: () => <ProdottiConTabFornitore initialSub="gestione" /> },
  movimenti_magazzino: { render: () => <ControlloMagazzinoView /> },
  sconti_merce: { render: () => <ProdottiConTabFornitore initialSub="sconti" /> },
  corrispettivi: { render: () => <CorrispettiviView /> },
  ricette: { render: () => <BackofficeView initialTab="ricette" solo /> },
  lotti: {
    render: (ctx) => (
      <LottiList
        items={ctx.lotti}
        onDelete={ctx.handleDeleteLotto}
        search={ctx.searchLotti}
        setSearch={ctx.setSearchLotti}
        filtroDataDa={ctx.filtroDataDaLotti}
        setFiltroDataDa={ctx.setFiltroDataDaLotti}
        filtroDataA={ctx.filtroDataALotti}
        setFiltroDataA={ctx.setFiltroDataALotti}
        filtroSoloScaduti={ctx.filtroSoloScaduti}
        setFiltroSoloScaduti={ctx.setFiltroSoloScaduti}
      />
    ),
  },
  storico_produzioni: { render: () => <StoricoProduzioniView /> },
  cosa_usare_oggi: { render: () => <CosaUsareOggiView /> },
  dashboard_economica: { render: () => <DashboardEconomicaView /> },
  produzione_consigliata: { render: () => <ProduzioneConsigliataView /> },
  mappa_tracciabilita: { render: (ctx) => <MappaTracciabilitaView onNavigate={ctx.handleTabChange} /> },
  // Moduli HACCP (senza ErrorBoundary: comportamento storico invariato)
  disinfestazione: { safe: false, render: () => <DisinfestazioneView /> },
  sanificazione: { safe: false, render: () => <SanificazioneView /> },
  temp_negative: { safe: false, render: () => <TemperatureNegativeView /> },
  temp_positive: { safe: false, render: () => <TemperaturePositiveView /> },
  anomalie: { safe: false, render: () => <AnomalieView /> },
  manuale: { safe: false, render: () => <ManualeHACCPView /> },
  registro_haccp: { render: () => <RegistroHACCPView /> },
  personale: { render: () => <ImpostazioniPersonaleView /> },
  stampanti: { render: () => <StampantiConfigView /> },
  guida: { render: () => <ManualeView /> },
  configura: { render: (ctx) => <ConfiguraWizard onNavigate={ctx.setActiveTab} /> },
  dizionario: { render: () => <DizionarioIngredientiView /> },
  controllo_olio: { safe: false, render: () => <ControlloOlioView /> },
  temp_cottura: { safe: false, render: () => <TemperatureCotturaView /> },
  ricezione_merce: { safe: false, render: () => <RicezioneMerceView /> },
  backup: { safe: false, render: (ctx) => <BackupView onBack={() => ctx.setActiveTab("dashboard")} /> },
  allergeni: { safe: false, render: () => <RegistroAllergeniView /> },
  schede_tecniche: { render: () => <SchedeTecnicheView /> },
  ordini: { render: () => <OrdiniView /> },
  backoffice: { render: () => <BackofficeView /> },
  controllo_dati: { render: () => <ControlloDatiView /> },
  cataloghi_esterni: { render: () => <CataloghiEsterniView /> },
  attrezzature: { render: () => <AttrezzatureView /> },
  collaudi: { render: () => <CollaudiView /> },
  listino: { render: () => <ProdottiConTabFornitore initialSub="listino" /> },
  comparatore: { render: () => <ConfrontoProdottoView /> },
};

export function renderPagina(activeTab, ctx) {
  const voce = PAGINE[activeTab];
  if (!voce) return null;
  const contenuto = voce.render(ctx);
  return voce.safe === false ? contenuto : <ErrorBoundary>{contenuto}</ErrorBoundary>;
}

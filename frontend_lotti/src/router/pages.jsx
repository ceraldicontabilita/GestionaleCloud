// REGISTRO PAGINE dichiarativo — unico punto che collega id pagina → vista.
// Estratto dal grande blocco condizionale di App.js (fase 2, 24/07/2026).
// id/etichette/menu vivono in config/navigation.js, titoli in config/pageMeta.js,
// permessi in config/permissions.js: qui SOLO il componente da renderizzare.
// ctx = stato e callback condivisi passati da App.js (vedi renderPagina).
import ErrorBoundary from "../components/ErrorBoundary";
import PaginaNonTrovata from "../components/PaginaNonTrovata";
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
import OrdiniHotelView from "../components/haccp/OrdiniHotelView";
import { StoricoProduzioniView } from "../components/haccp/StoricoProduzioniView";
import BackofficeView from "../components/haccp/BackofficeView";
import { isAdmin } from "../auth";
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
import ProduzioneConsigliataView from "../components/haccp/ProduzioneConsigliataView";
import MappaTracciabilitaView from "../components/haccp/MappaTracciabilitaView";
import ControlloMagazzinoView from "../components/haccp/ControlloMagazzinoView";
import ConfrontoProdottoView from "../components/haccp/ConfrontoProdottoView";
import AttendibilitaHaccpView from "../components/haccp/AttendibilitaHaccpView";
import ProdottiHubView from "../components/haccp/ProdottiHubView";
import MenuVetrinaView from "../components/haccp/MenuVetrinaView";
import ImpostazioniView from "../components/haccp/ImpostazioniView";
import MerceFermaView from "../components/haccp/MerceFermaView";
import CalcolatoreImpastiView from "../components/haccp/CalcolatoreImpastiView";

export const ProdottiConTabFornitore = ProdottiHubView;

// Mappa id → funzione di render. Ogni voce riceve ctx (stato condiviso da
// App.js) e ritorna il JSX della pagina. Ogni pagina ha il suo ErrorBoundary:
// prima i registri HACCP ne erano senza, e un errore in una scheda
// temperature svuotava tutta l'app (audit 26/09/2026).
const PAGINE = {
  dashboard: { render: (ctx) => <DashboardView stats={ctx.stats} onRefresh={ctx.refreshAll} onNavigate={ctx.setActiveTab} /> },
  gelati: { render: () => <GelatiView /> },
  fornitori: { render: (ctx) => <FornitoriList fornitori={ctx.fornitori} onRefresh={ctx.fetchFornitori} /> },
  materie: { render: () => <MateriePrimeList /> },
  prodotti: { render: () => <ProdottiConTabFornitore /> },
  magazzino_prodotti: { render: () => <ProdottiConTabFornitore initialSub="gestione" /> },
  movimenti_magazzino: { render: () => <ControlloMagazzinoView /> },
  sconti_merce: { render: () => <ProdottiConTabFornitore initialSub="sconti" /> },
  corrispettivi: { render: () => <CorrispettiviView /> },
  // Vetrina «In menu» (19/09/2026): elenca le ricette pubblicate nel Menu
  // digitale. Da una card si torna alla scheda ricetta con lo stesso
  // meccanismo del Supervisore (sessionStorage + pagina Produzione).
  in_menu: { render: (ctx) => <MenuVetrinaView onNavigate={ctx.handleTabChange} /> },
  ricette: { render: () => <BackofficeView initialTab="ricette" solo solaLetturaOperatore={!isAdmin()} /> },
  lotti: {
    render: (ctx) => (
      <LottiList
        items={ctx.lotti}
        onLottiChanged={ctx.notifyLottiChanged}
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
  calcolatore_impasti: { render: () => <CalcolatoreImpastiView /> },
  cosa_usare_oggi: { render: () => <CosaUsareOggiView /> },
  produzione_consigliata: { render: () => <ProduzioneConsigliataView /> },
  mappa_tracciabilita: { render: (ctx) => <MappaTracciabilitaView onNavigate={ctx.handleTabChange} /> },
  // Moduli HACCP
  disinfestazione: { render: () => <DisinfestazioneView /> },
  sanificazione: { render: () => <SanificazioneView /> },
  temp_negative: { render: () => <TemperatureNegativeView /> },
  temp_positive: { render: () => <TemperaturePositiveView /> },
  anomalie: { render: () => <AnomalieView /> },
  manuale: { render: () => <ManualeHACCPView /> },
  registro_haccp: { render: () => <RegistroHACCPView /> },
  impostazioni: { render: (ctx) => <ImpostazioniView onNavigate={ctx.handleTabChange} /> },
  merce_ferma: { render: () => <MerceFermaView /> },
  personale: { render: () => <ImpostazioniPersonaleView /> },
  stampanti: { render: () => <StampantiConfigView /> },
  guida: { render: () => <ManualeView /> },
  configura: { render: (ctx) => <ConfiguraWizard onNavigate={ctx.setActiveTab} /> },
  dizionario: { render: () => <DizionarioIngredientiView /> },
  controllo_olio: { render: () => <ControlloOlioView /> },
  temp_cottura: { render: () => <TemperatureCotturaView /> },
  ricezione_merce: { render: () => <RicezioneMerceView /> },
  backup: { render: (ctx) => <BackupView onBack={() => ctx.setActiveTab("dashboard")} /> },
  allergeni: { render: () => <RegistroAllergeniView /> },
  schede_tecniche: { render: () => <SchedeTecnicheView /> },
  ordini: { render: () => <OrdiniView /> },
  ordini_hotel: { render: (ctx) => <OrdiniHotelView onNavigate={ctx.handleTabChange} /> },
  backoffice: { render: () => <BackofficeView /> },
  controllo_dati: { render: () => <ControlloDatiView /> },
  cataloghi_esterni: { render: () => <CataloghiEsterniView /> },
  attrezzature: { render: () => <AttrezzatureView /> },
  collaudi: { render: () => <CollaudiView /> },
  listino: { render: () => <ProdottiConTabFornitore initialSub="listino" /> },
  comparatore: { render: () => <ConfrontoProdottoView /> },
  attendibilita_haccp: { render: () => <AttendibilitaHaccpView /> },
};

export function paginaEsiste(activeTab) {
  return Object.prototype.hasOwnProperty.call(PAGINE, activeTab);
}

export function renderPagina(activeTab, ctx) {
  const voce = PAGINE[activeTab];
  // Un indirizzo sconosciuto non è un'area vuota: dice che la pagina non
  // c'è e riporta alla Home.
  if (!voce) return <PaginaNonTrovata id={activeTab} onHome={() => ctx.handleTabChange("dashboard")} />;
  return <ErrorBoundary key={activeTab}>{voce.render(ctx)}</ErrorBoundary>;
}

import React, { Suspense, lazy } from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider, Navigate } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import App from "./App.jsx";
import "./styles.css";
import { AnnoProvider } from "./contexts/AnnoContext.jsx";
import { AuthProvider, RequireAuth } from "./contexts/AuthContext.jsx";
import { queryClient } from "./lib/queryClient.js";
import { ConfirmProvider } from "./components/ui/ConfirmDialog.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import AuthCallback from "./pages/AuthCallback.jsx";

const PageLoader = () => (
  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh', flexDirection: 'column', gap: 16 }}>
    <div style={{ width: 48, height: 48, border: '4px solid #e2e8f0', borderTop: '4px solid #2563eb', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
    <span style={{ color: '#64748b', fontSize: 14 }}>Caricamento...</span>
    <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
  </div>
);

// === HUB PAGES (consolidated) ===
const DashboardHub = lazy(() => import("./pages/hub/DashboardHub.jsx"));
  // Ciclo Passivo hub rimosso - import avviene da Import Documenti
const FornitoriHub = lazy(() => import("./pages/hub/FornitoriHub.jsx"));
const PrimaNotaHub = lazy(() => import("./pages/hub/PrimaNotaHub.jsx"));
const DipendentiHub = lazy(() => import("./pages/hr/HRPresenze.jsx"));
const HRDipendenti = lazy(() => import("./pages/hr/HRDipendenti.jsx"));
const HRCedolini = lazy(() => import("./pages/hr/HRCedolini.jsx"));
const HRTFR = lazy(() => import("./pages/hr/HRTFR.jsx"));
const VeicoliHub = lazy(() => import("./pages/hub/VeicoliHub.jsx"));
const ContabilitaHub = lazy(() => import("./pages/hub/ContabilitaHub.jsx"));
const MagazzinoHub = lazy(() => import("./pages/hub/MagazzinoHub.jsx"));
const DocumentiHub = lazy(() => import("./pages/hub/DocumentiHub.jsx"));
const StrumentiHub = lazy(() => import("./pages/hub/StrumentiHub.jsx"));
const IntegrazioniHub = lazy(() => import("./pages/hub/IntegrazioniHub.jsx"));
const AdminHub     = lazy(() => import("./pages/hub/AdminHub.jsx"));
const RiconciliazioneHub = lazy(() => import("./pages/hub/RiconciliazioneHub.jsx"));
const FattureHub = lazy(() => import("./pages/hub/FattureHub.jsx"));

// === STANDALONE PAGES ===
const InserimentoRapido = lazy(() => import("./pages/InserimentoRapido.jsx"));
const Scadenze = lazy(() => import("./pages/Scadenze.jsx"));
const ToDo = lazy(() => import("./pages/ToDo.jsx"));
const GestioneRiservata = lazy(() => import("./pages/GestioneRiservata.jsx"));
const DettaglioVerbale = lazy(() => import("./pages/DettaglioVerbale.jsx"));
const GestioneEmailMittenti = lazy(() => import("./pages/GestioneEmailMittenti.jsx"));
const ImpostazioniF24Email = lazy(() => import("./pages/ImpostazioniF24Email.jsx"));
const MappaGestionale = lazy(() => import("./pages/MappaGestionale.jsx"));
const DatiProvvisoriPage = lazy(() => import("./pages/DatiProvvisoriPage.jsx"));
const AgentiPage = lazy(() => import("./pages/Agenti.jsx"));
const Portale = lazy(() => import("./pages/Portale.jsx"));
const TracciabilitaPage = lazy(() => import("./pages/TracciabilitaPage.jsx"));
const LearningMachine = lazy(() => import("./pages/LearningMachine.jsx"));

const LazyPage = ({ children }) => (
  <Suspense fallback={<PageLoader />}>{children}</Suspense>
);

const router = createBrowserRouter([
  { path: "/auth/callback", element: <AuthCallback /> },
  { path: "/login", element: <Login /> },
  { path: "/register", element: <Register /> },
  { path: "/portale", element: <Portale /> },
  { path: "/gestione-riservata", element: <LazyPage><GestioneRiservata /></LazyPage> },
  {
    path: "/",
    element: <App />,  // DISABILITATO RequireAuth - Login rimandato al deploy
    children: [
      // === DASHBOARD ===
      { index: true, element: <LazyPage><DashboardHub /></LazyPage> },
      { path: "dashboard", element: <LazyPage><DashboardHub /></LazyPage> },
      { path: "dashboard/:anno", element: <LazyPage><DashboardHub /></LazyPage> },
      { path: "analytics", element: <LazyPage><DashboardHub /></LazyPage> },
      { path: "analytics/:periodo", element: <LazyPage><DashboardHub /></LazyPage> },
      
      // === INSERIMENTO RAPIDO ===
      { path: "rapido", element: <LazyPage><InserimentoRapido /></LazyPage> },
      
      // === TRACCIABILITA' MINI-SITO ===
      { path: "tracciabilita", element: <LazyPage><TracciabilitaPage /></LazyPage> },
      
      // === FATTURE & VENDITE ===
      { path: "fatture", element: <LazyPage><FattureHub /></LazyPage> },
      { path: "fatture/import", element: <Navigate to="/documenti/import" replace /> },
      { path: "fatture/:tab", element: <LazyPage><FattureHub /></LazyPage> },
      { path: "fatture-ricevute", element: <Navigate to="/fatture" replace /> },
      { path: "fatture-ricevute/:fornitore", element: <Navigate to="/fatture" replace /> },
      { path: "fatture-ricevute/:fornitore/:fattura", element: <Navigate to="/fatture" replace /> },
      { path: "archivio-fatture-ricevute", element: <Navigate to="/fatture" replace /> },
      { path: "corrispettivi", element: <Navigate to="/fatture/corrispettivi" replace /> },
      { path: "corrispettivi/:anno/:mese", element: <LazyPage><FattureHub /></LazyPage> },
      
      // === FORNITORI ===
      { path: "fornitori", element: <LazyPage><FornitoriHub /></LazyPage> },
      { path: "fornitori/ordini", element: <Navigate to="/fornitori" replace /> },
      { path: "fornitori/:tab", element: <LazyPage><FornitoriHub /></LazyPage> },
      { path: "fornitori/:nome/:dettaglio", element: <LazyPage><FornitoriHub /></LazyPage> },
      { path: "ordini-fornitori", element: <Navigate to="/fornitori" replace /> },
      { path: "ordini-fornitori/:fornitore", element: <Navigate to="/fornitori" replace /> },
      
      // === PRIMA NOTA ===
      { path: "prima-nota", element: <LazyPage><PrimaNotaHub /></LazyPage> },
      { path: "prima-nota/:tipo", element: <LazyPage><PrimaNotaHub /></LazyPage> },
      { path: "prima-nota/:tipo/:anno/:mese", element: <LazyPage><PrimaNotaHub /></LazyPage> },
      { path: "dati-provvisori", element: <LazyPage><DatiProvvisoriPage /></LazyPage> },
      
      // === DIPENDENTI ===
      { path: "dipendenti", element: <LazyPage><HRDipendenti /></LazyPage> },
      { path: "dipendenti/:tab", element: <LazyPage><HRDipendenti /></LazyPage> },
      { path: "dipendenti/:tab/:subtab", element: <LazyPage><HRDipendenti /></LazyPage> },
      { path: "presenze", element: <LazyPage><DipendentiHub /></LazyPage> },
      { path: "presenze/:dipendente", element: <LazyPage><DipendentiHub /></LazyPage> },
      { path: "presenze/:dipendente/:mese", element: <LazyPage><DipendentiHub /></LazyPage> },
      { path: "saldi-ferie-permessi", element: <LazyPage><DipendentiHub /></LazyPage> },
      
      // === CEDOLINI & TFR ===
      { path: "paghe", element: <Navigate to="/cedolini" replace /> },
      { path: "cedolini", element: <LazyPage><HRCedolini /></LazyPage> },
      { path: "cedolini/:anno", element: <LazyPage><HRCedolini /></LazyPage> },
      { path: "cedolini/:anno/:mese", element: <LazyPage><HRCedolini /></LazyPage> },
      { path: "cedolini-calcolo", element: <LazyPage><HRCedolini /></LazyPage> },
      { path: "prima-nota-salari", element: <LazyPage><HRCedolini /></LazyPage> },
      { path: "prima-nota-salari/:anno/:mese", element: <LazyPage><HRCedolini /></LazyPage> },
      { path: "tfr", element: <LazyPage><HRTFR /></LazyPage> },
      { path: "tfr/:tab", element: <LazyPage><HRTFR /></LazyPage> },
      
      // === VEICOLI/NOLEGGIO ===
      { path: "noleggio", element: <LazyPage><VeicoliHub /></LazyPage> },
      { path: "noleggio/:tab", element: <LazyPage><VeicoliHub /></LazyPage> },
      { path: "noleggio/verbali/:id", element: <LazyPage><VeicoliHub /></LazyPage> },
      { path: "veicoli", element: <Navigate to="/noleggio" replace /> },
      { path: "noleggio-auto", element: <Navigate to="/noleggio" replace /> },
      { path: "noleggio-auto/:targa", element: <LazyPage><VeicoliHub /></LazyPage> },
      { path: "verbali-noleggio/:numeroVerbale", element: <LazyPage><DettaglioVerbale /></LazyPage> },
      { path: "verbali-noleggio/:prefisso/:numero", element: <LazyPage><DettaglioVerbale /></LazyPage> },
      { path: "verbali-riconciliazione", element: <LazyPage><VeicoliHub /></LazyPage> },
      { path: "verbali-riconciliazione/:verbaleId", element: <LazyPage><VeicoliHub /></LazyPage> },
      
      // === CONTABILITÀ ===
      { path: "contabilita", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "contabilita/:sezione", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "contabilita-hub", element: <Navigate to="/contabilita" replace /> },
      { path: "bilancio", element: <Navigate to="/contabilita/bilancio" replace /> },
      { path: "bilancio/:tab", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "bilancio/:anno", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "bilancio-verifica", element: <Navigate to="/contabilita/verifica" replace /> },
      { path: "partitario", element: <Navigate to="/contabilita/bilancio" replace /> },
      { path: "partitario/:tab", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "budget-previsionale", element: <Navigate to="/contabilita/budget" replace /> },
      { path: "budget-previsionale/:tab", element: <LazyPage><ContabilitaHub /></LazyPage> },

      // === MUTUI → tab in /contabilita/mutui ===
      { path: "mutui", element: <Navigate to="/contabilita/mutui" replace /> },

      { path: "piano-dei-conti", element: <Navigate to="/contabilita/piano-conti" replace /> },
      { path: "piano-dei-conti/:tab", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "piano-dei-conti/:conto", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "controllo-mensile", element: <Navigate to="/contabilita/controllo" replace /> },
      { path: "controllo-mensile/:anno/:mese", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "calendario-fiscale", element: <Navigate to="/contabilita/calendario" replace /> },
      { path: "cespiti", element: <Navigate to="/contabilita/cespiti" replace /> },
      { path: "cespiti/:tab", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "cespiti/:cespite", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "finanziaria", element: <Navigate to="/contabilita/finanziaria" replace /> },
      { path: "finanziaria/:anno", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "chiusura-esercizio", element: <Navigate to="/contabilita/chiusura" replace /> },
      { path: "chiusura-esercizio/:anno", element: <LazyPage><ContabilitaHub /></LazyPage> },
      
      // === MAGAZZINO ===
      { path: "magazzino", element: <LazyPage><MagazzinoHub /></LazyPage> },
      { path: "magazzino/:tab", element: <LazyPage><MagazzinoHub /></LazyPage> },
      { path: "inventario", element: <Navigate to="/magazzino/inventario" replace /> },
      { path: "inventario/:data", element: <LazyPage><MagazzinoHub /></LazyPage> },
      { path: "ricerca-prodotti", element: <Navigate to="/magazzino/ricerca" replace /> },
      { path: "ricerca-prodotti/:query", element: <LazyPage><MagazzinoHub /></LazyPage> },
      { path: "dizionario-articoli", element: <Navigate to="/magazzino/articoli" replace /> },
      { path: "dizionario-articoli/:articolo", element: <LazyPage><MagazzinoHub /></LazyPage> },
      { path: "magazzino-dv", element: <Navigate to="/magazzino" replace /> },
      
      // === REDIRECT CUCINA → MAGAZZINO (la sezione cucina è stata rimossa) ===
      { path: "cucina", element: <Navigate to="/magazzino" replace /> },
      { path: "cucina/:tab", element: <Navigate to="/magazzino" replace /> },
      { path: "ricettario", element: <Navigate to="/magazzino" replace /> },
      { path: "ricettario/:tab", element: <Navigate to="/magazzino" replace /> },
      { path: "dizionario-prodotti", element: <Navigate to="/magazzino/prodotti" replace /> },
      { path: "dizionario-prodotti/:prodotto", element: <Navigate to="/magazzino/prodotti" replace /> },
      { path: "centri-costo", element: <Navigate to="/contabilita/centri-costo" replace /> },
      { path: "centri-costo/:centro", element: <Navigate to="/contabilita/centri-costo" replace /> },
      { path: "utile-obiettivo", element: <Navigate to="/contabilita/utile" replace /> },
      { path: "utile-obiettivo/:anno", element: <Navigate to="/contabilita/utile" replace /> },
      { path: "learning-machine", element: <LazyPage><LearningMachine /></LazyPage> },
      { path: "learning-machine/:tab", element: <LazyPage><LearningMachine /></LazyPage> },
      
      // === SCADENZE ===
      { path: "scadenze", element: <LazyPage><Scadenze /></LazyPage> },
      { path: "scadenze/:anno", element: <LazyPage><Scadenze /></LazyPage> },
      { path: "scadenze/:anno/:mese", element: <LazyPage><Scadenze /></LazyPage> },
      
      // === RICONCILIAZIONE / ASSEGNI ===
      { path: "riconciliazione", element: <LazyPage><RiconciliazioneHub /></LazyPage> },
      { path: "riconciliazione/:tab", element: <LazyPage><RiconciliazioneHub /></LazyPage> },
      { path: "gestione-assegni", element: <LazyPage><RiconciliazioneHub /></LazyPage> },
      { path: "assegni", element: <Navigate to="/riconciliazione/assegni" replace /> },
      
      // === TO-DO ===
      { path: "todo", element: <LazyPage><ToDo /></LazyPage> },
      { path: "todo/:stato", element: <LazyPage><ToDo /></LazyPage> },
      
      // === IMPORT DOCUMENTI → tab in /documenti/import ===
      { path: "import-documenti", element: <Navigate to="/documenti/import" replace /> },
      { path: "import-unificato", element: <Navigate to="/documenti/import" replace /> },
      { path: "import-unificato/:tipo", element: <LazyPage><DocumentiHub /></LazyPage> },
      { path: "import-export", element: <Navigate to="/documenti/import" replace /> },
      { path: "import-ai", element: <Navigate to="/documenti/import" replace /> },
      { path: "ai-parser", element: <Navigate to="/documenti/import" replace /> },
      { path: "ai-parser/:tipo", element: <LazyPage><DocumentiHub /></LazyPage> },
      { path: "lettura-documenti", element: <Navigate to="/documenti/import" replace /> },

      // === DOCUMENTI ===
      { path: "documenti", element: <LazyPage><DocumentiHub /></LazyPage> },
      { path: "documenti/:tab", element: <LazyPage><DocumentiHub /></LazyPage> },
      { path: "documenti-email", element: <Navigate to="/documenti" replace /> },
      { path: "da-rivedere", element: <Navigate to="/documenti/da-rivedere" replace /> },
      { path: "da-rivedere/:stato", element: <LazyPage><DocumentiHub /></LazyPage> },
      { path: "classificazione-email", element: <Navigate to="/documenti/classificazione" replace /> },
      { path: "classificazione-email/:tab", element: <LazyPage><DocumentiHub /></LazyPage> },
      { path: "documenti-da-rivedere", element: <Navigate to="/documenti/da-rivedere" replace /> },
      { path: "classificazione-documenti", element: <Navigate to="/documenti/classificazione" replace /> },
      { path: "regole-categorizzazione", element: <Navigate to="/learning-machine/regole" replace /> },
      { path: "fornitori-learning", element: <Navigate to="/fornitori" replace /> },
      
      // === STRUMENTI ===
      { path: "strumenti", element: <LazyPage><StrumentiHub /></LazyPage> },
      { path: "strumenti/:tab", element: <LazyPage><StrumentiHub /></LazyPage> },
      { path: "verifica-coerenza", element: <Navigate to="/strumenti/verifica" replace /> },
      { path: "verifica-coerenza/:tab", element: <LazyPage><StrumentiHub /></LazyPage> },
      { path: "agenti", element: <LazyPage><AgentiPage /></LazyPage> },
      // portale è già definito a root level (fuori dall'App layout)
      { path: "commercialista", element: <Navigate to="/strumenti/commercialista" replace /> },
      { path: "commercialista/:anno/:mese", element: <LazyPage><StrumentiHub /></LazyPage> },
      { path: "pianificazione", element: <Navigate to="/strumenti/pianificazione" replace /> },
      { path: "pianificazione/:anno", element: <LazyPage><StrumentiHub /></LazyPage> },
      { path: "email-download", element: <Navigate to="/strumenti/email" replace /> },
      { path: "email-download/:casella", element: <LazyPage><StrumentiHub /></LazyPage> },
      { path: "visure", element: <Navigate to="/strumenti/visure" replace /> },
      { path: "impostazioni-f24-email", element: <LazyPage><ImpostazioniF24Email /></LazyPage> },
      { path: "gestione-email", element: <LazyPage><GestioneEmailMittenti /></LazyPage> },
      
      // === INTEGRAZIONI ===
      { path: "integrazioni", element: <LazyPage><IntegrazioniHub /></LazyPage> },
      { path: "integrazioni-openapi", element: <LazyPage><IntegrazioniHub /></LazyPage> },
      { path: "integrazioni-openapi/:tab", element: <LazyPage><IntegrazioniHub /></LazyPage> },
      { path: "pagopa", element: <LazyPage><IntegrazioniHub /></LazyPage> },
      { path: "pagopa/:pratica", element: <LazyPage><IntegrazioniHub /></LazyPage> },
      { path: "invoicetronic", element: <LazyPage><IntegrazioniHub /></LazyPage> },
      { path: "invoicetronic/:fattura", element: <LazyPage><IntegrazioniHub /></LazyPage> },
      
      // === ADMIN ===
      { path: "admin", element: <LazyPage><AdminHub /></LazyPage> },
      { path: "admin/:sezione", element: <LazyPage><AdminHub /></LazyPage> },
      { path: "batch-reprocessing", element: <LazyPage><AdminHub /></LazyPage> },
      { path: "batch-processor", element: <LazyPage><AdminHub /></LazyPage> },
      
      // === MAPPA GESTIONALE ===
      { path: "mappa-gestionale", element: <LazyPage><MappaGestionale /></LazyPage> },

      // === AI (redirect to OpenClaw) ===
      { path: "assistente-ai", element: <Navigate to="/api/openclaw/ui/" replace /> },
      { path: "claude", element: <Navigate to="/api/openclaw/ui/" replace /> },
      
      // === REDIRECT ROTTE LEGACY / MANCANTI ===
      { path: "fisco", element: <Navigate to="/contabilita/calendario" replace /> },
      { path: "fisco/*", element: <Navigate to="/contabilita/calendario" replace /> },
      { path: "riconciliazione-unificata", element: <Navigate to="/riconciliazione" replace /> },
      
      // === CATCH-ALL: rotte non trovate → Dashboard ===
      { path: "*", element: <Navigate to="/" replace /> },
    ]
  }
]);

// React.StrictMode RIMOSSO: in dev mode causava mount→unmount→remount su ogni componente,
// facendo eseguire tutti i useEffect DUE VOLTE (spinner → dati → spinner → dati).
// L'utente vedeva un "reload" ad ogni navigazione. Non ha effetto sui build di produzione.
ReactDOM.createRoot(document.getElementById("root")).render(
  <ErrorBoundary>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AnnoProvider>
          <ConfirmProvider>
            <RouterProvider router={router} />
          </ConfirmProvider>
        </AnnoProvider>
      </AuthProvider>
    </QueryClientProvider>
  </ErrorBoundary>
);


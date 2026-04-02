// @refresh reset
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
const CicloPassivoHub = lazy(() => import("./pages/hub/CicloPassivoHub.jsx"));
const CicloPassivoAdmin = lazy(() => import("./pages/CicloPassivoAdmin.jsx"));
const FornitoriHub = lazy(() => import("./pages/hub/FornitoriHub.jsx"));
const PrimaNotaHub = lazy(() => import("./pages/hub/PrimaNotaHub.jsx"));
const RiconciliazioneHub = lazy(() => import("./pages/hub/RiconciliazioneHub.jsx"));
const DipendentiHub = lazy(() => import("./pages/hub/DipendentiHub.jsx"));
const GestioneDipendentiUnificata = lazy(() => import("./pages/GestioneDipendentiUnificata.jsx"));
const PagheHub = lazy(() => import("./pages/hub/PagheHub.jsx"));
const VeicoliHub = lazy(() => import("./pages/hub/VeicoliHub.jsx"));
const FiscoHub = lazy(() => import("./pages/hub/FiscoHub.jsx"));
const BilancioHub = lazy(() => import("./pages/hub/BilancioHub.jsx"));
const ContabilitaHub = lazy(() => import("./pages/hub/ContabilitaHub.jsx"));
const MagazzinoHub = lazy(() => import("./pages/hub/MagazzinoHub.jsx"));
const CucinaHub = lazy(() => import("./pages/hub/CucinaHub.jsx"));
const ImportDocumentiHub = lazy(() => import("./pages/hub/ImportDocumentiHub.jsx"));
const DocumentiHub = lazy(() => import("./pages/hub/DocumentiHub.jsx"));
const StrumentiHub = lazy(() => import("./pages/hub/StrumentiHub.jsx"));
const IntegrazioniHub = lazy(() => import("./pages/hub/IntegrazioniHub.jsx"));
const AdminHub = lazy(() => import("./pages/hub/AdminHub.jsx"));
const FattureHub = lazy(() => import("./pages/hub/FattureHub.jsx"));
const LearningMachineUniversale = lazy(() => import("./pages/LearningMachineUniversale.jsx"));
const LearningMachine = lazy(() => import("./pages/LearningMachine.jsx"));
const RiconciliazioneUnificata = lazy(() => import("./pages/RiconciliazioneUnificata.jsx"));
const MappaGestionale = lazy(() => import("./pages/MappaGestionale.jsx"));

// === STANDALONE PAGES ===
const InserimentoRapido = lazy(() => import("./pages/InserimentoRapido.jsx"));
const Scadenze = lazy(() => import("./pages/Scadenze.jsx"));
const ToDo = lazy(() => import("./pages/ToDo.jsx"));
const GestioneRiservata = lazy(() => import("./pages/GestioneRiservata.jsx"));
const DettaglioVerbale = lazy(() => import("./pages/DettaglioVerbale.jsx"));
const ImpostazioniF24Email = lazy(() => import("./pages/ImpostazioniF24Email.jsx"));
const Mutui = lazy(() => import("./pages/Mutui.jsx"));
const VerificaCoerenza = lazy(() => import("./pages/VerificaCoerenza.jsx"));
const AgentiPage = lazy(() => import("./pages/Agenti.jsx"));
const Portale = lazy(() => import("./pages/Portale.jsx"));
const TracciabilitaPage = lazy(() => import("./pages/TracciabilitaPage.jsx"));

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
      
      // === CICLO PASSIVO & VENDITE ===
      { path: "ciclo-passivo", element: <LazyPage><CicloPassivoHub /></LazyPage> },
      { path: "ciclo-passivo/import", element: <LazyPage><CicloPassivoAdmin /></LazyPage> },
      { path: "fatture", element: <LazyPage><FattureHub /></LazyPage> },
      { path: "fatture/:tab", element: <LazyPage><FattureHub /></LazyPage> },
      { path: "fatture-ricevute", element: <Navigate to="/fatture" replace /> },
      { path: "fatture-ricevute/:fornitore", element: <Navigate to="/fatture" replace /> },
      { path: "fatture-ricevute/:fornitore/:fattura", element: <Navigate to="/fatture" replace /> },
      { path: "archivio-fatture-ricevute", element: <LazyPage><FattureHub /></LazyPage> },
      { path: "corrispettivi", element: <LazyPage><CicloPassivoHub /></LazyPage> },
      { path: "corrispettivi/:anno/:mese", element: <LazyPage><CicloPassivoHub /></LazyPage> },
      
      // === FORNITORI ===
      { path: "fornitori", element: <LazyPage><FornitoriHub /></LazyPage> },
      { path: "fornitori/:tab", element: <LazyPage><FornitoriHub /></LazyPage> },
      { path: "fornitori/:nome/:dettaglio", element: <LazyPage><FornitoriHub /></LazyPage> },
      { path: "ordini-fornitori", element: <Navigate to="/fornitori/ordini" replace /> },
      { path: "ordini-fornitori/:fornitore", element: <LazyPage><FornitoriHub /></LazyPage> },
      { path: "previsioni-acquisti", element: <Navigate to="/fornitori/previsioni" replace /> },
      { path: "previsioni-acquisti/:categoria", element: <LazyPage><FornitoriHub /></LazyPage> },
      
      // === PRIMA NOTA ===
      { path: "prima-nota", element: <LazyPage><PrimaNotaHub /></LazyPage> },
      { path: "prima-nota/:tipo", element: <LazyPage><PrimaNotaHub /></LazyPage> },
      { path: "prima-nota/:tipo/:anno/:mese", element: <LazyPage><PrimaNotaHub /></LazyPage> },
      { path: "dati-provvisori", element: <LazyPage><PrimaNotaHub /></LazyPage> },
      
      // === RICONCILIAZIONE ===
      // Nuova rotta principale (unificata con PayPal)
      { path: "riconciliazione-unificata", element: <LazyPage><RiconciliazioneUnificata /></LazyPage> },
      { path: "riconciliazione-unificata/:tab", element: <LazyPage><RiconciliazioneUnificata /></LazyPage> },
      // Redirect vecchi URL → nuova rotta
      { path: "riconciliazione", element: <Navigate to="/riconciliazione-unificata" replace /> },
      { path: "riconciliazione/:tab", element: <Navigate to="/riconciliazione-unificata" replace /> },
      { path: "riconciliazione/:tab/:id", element: <Navigate to="/riconciliazione-unificata" replace /> },
      { path: "riconciliazione-intelligente", element: <Navigate to="/riconciliazione-unificata" replace /> },
      { path: "riconciliazione-paypal", element: <Navigate to="/riconciliazione-unificata/paypal" replace /> },
      { path: "gestione-assegni", element: <Navigate to="/riconciliazione-unificata/assegni" replace /> },
      { path: "gestione-assegni/:stato", element: <Navigate to="/riconciliazione-unificata/assegni" replace /> },
      { path: "archivio-bonifici", element: <LazyPage><RiconciliazioneHub /></LazyPage> },
      { path: "archivio-bonifici/:tab", element: <LazyPage><RiconciliazioneHub /></LazyPage> },
      { path: "archivio-bonifici/:anno/:mese", element: <LazyPage><RiconciliazioneHub /></LazyPage> },
      
      // === DIPENDENTI ===
      { path: "dipendenti", element: <LazyPage><GestioneDipendentiUnificata /></LazyPage> },
      { path: "dipendenti/:tab", element: <LazyPage><GestioneDipendentiUnificata /></LazyPage> },
      { path: "dipendenti/:tab/:subtab", element: <LazyPage><GestioneDipendentiUnificata /></LazyPage> },
      { path: "dipendenti/:nome/:tab", element: <LazyPage><GestioneDipendentiUnificata /></LazyPage> },
      { path: "presenze", element: <LazyPage><DipendentiHub /></LazyPage> },
      { path: "presenze/:dipendente", element: <LazyPage><DipendentiHub /></LazyPage> },
      { path: "presenze/:dipendente/:mese", element: <LazyPage><DipendentiHub /></LazyPage> },
      { path: "saldi-ferie-permessi", element: <LazyPage><DipendentiHub /></LazyPage> },
      
      // === PAGHE & RETRIBUZIONI → ora in /dipendenti/paghe ===
      { path: "paghe", element: <Navigate to="/dipendenti/paghe" replace /> },
      { path: "cedolini", element: <LazyPage><PagheHub /></LazyPage> },
      { path: "cedolini/:anno", element: <LazyPage><PagheHub /></LazyPage> },
      { path: "cedolini/:anno/:mese", element: <LazyPage><PagheHub /></LazyPage> },
      { path: "cedolini/:nome/:dettaglio", element: <LazyPage><PagheHub /></LazyPage> },
      { path: "cedolini-calcolo", element: <LazyPage><PagheHub /></LazyPage> },
      { path: "cedolini-calcolo/:nome/:dettaglio", element: <LazyPage><PagheHub /></LazyPage> },
      { path: "prima-nota-salari", element: <LazyPage><PagheHub /></LazyPage> },
      { path: "prima-nota-salari/:anno/:mese", element: <LazyPage><PagheHub /></LazyPage> },
      { path: "tfr", element: <LazyPage><PagheHub /></LazyPage> },
      { path: "tfr/:tab", element: <LazyPage><PagheHub /></LazyPage> },
      { path: "tfr/:dipendente", element: <LazyPage><PagheHub /></LazyPage> },
      
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
      
      // === FISCO & TRIBUTI ===
      { path: "fisco", element: <LazyPage><FiscoHub /></LazyPage> },
      { path: "fisco/:tab", element: <LazyPage><FiscoHub /></LazyPage> },
      // Redirect vecchi path diretti → /fisco/tab
      { path: "iva", element: <Navigate to="/fisco/iva" replace /> },
      { path: "iva/calcolo", element: <Navigate to="/fisco/iva" replace /> },
      { path: "iva/liquidazione", element: <Navigate to="/fisco/iva" replace /> },
      { path: "iva/:anno/:trimestre", element: <LazyPage><FiscoHub /></LazyPage> },
      { path: "liquidazione-iva", element: <Navigate to="/fisco/iva" replace /> },
      { path: "liquidazione-iva/:anno/:mese", element: <LazyPage><FiscoHub /></LazyPage> },
      { path: "f24", element: <Navigate to="/fisco/f24" replace /> },
      { path: "f24/modelli", element: <Navigate to="/fisco/f24" replace /> },
      { path: "f24/riconciliazione", element: <Navigate to="/fisco/ric-f24" replace /> },
      { path: "f24/:anno", element: <LazyPage><FiscoHub /></LazyPage> },
      { path: "f24/:anno/:mese", element: <LazyPage><FiscoHub /></LazyPage> },
      { path: "riconciliazione-f24", element: <Navigate to="/fisco/ric-f24" replace /> },
      { path: "riconciliazione-f24/:anno", element: <LazyPage><FiscoHub /></LazyPage> },
      { path: "codici-tributari", element: <Navigate to="/fisco/codici" replace /> },
      { path: "codici-tributari/:codice", element: <LazyPage><FiscoHub /></LazyPage> },
      { path: "contabilita", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "contabilita/:sezione", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "contabilita-hub", element: <Navigate to="/contabilita" replace /> },
      
      // === BILANCIO ===
      { path: "bilancio", element: <LazyPage><BilancioHub /></LazyPage> },
      { path: "bilancio/:tab", element: <LazyPage><BilancioHub /></LazyPage> },
      { path: "bilancio/:anno", element: <LazyPage><BilancioHub /></LazyPage> },
      { path: "bilancio-verifica", element: <LazyPage><BilancioHub /></LazyPage> },
      { path: "partitario", element: <LazyPage><BilancioHub /></LazyPage> },
      { path: "partitario/:tab", element: <LazyPage><BilancioHub /></LazyPage> },
      { path: "budget-previsionale", element: <LazyPage><BilancioHub /></LazyPage> },
      { path: "budget-previsionale/:tab", element: <LazyPage><BilancioHub /></LazyPage> },
      
      // === MUTUI ===
      { path: "mutui", element: <LazyPage><Mutui /></LazyPage> },
      
      // === CONTABILITÀ ===
      { path: "contabilita-hub", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "piano-dei-conti", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "piano-dei-conti/:tab", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "piano-dei-conti/:conto", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "controllo-mensile", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "controllo-mensile/:anno/:mese", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "motore-contabile", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "calendario-fiscale", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "cespiti", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "cespiti/:tab", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "cespiti/:cespite", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "finanziaria", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "finanziaria/:anno", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "chiusura-esercizio", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "chiusura-esercizio/:anno", element: <LazyPage><ContabilitaHub /></LazyPage> },
      
      // === MAGAZZINO ===
      { path: "magazzino", element: <LazyPage><MagazzinoHub /></LazyPage> },
      { path: "magazzino/:tab", element: <LazyPage><MagazzinoHub /></LazyPage> },
      { path: "magazzino/:categoria", element: <LazyPage><MagazzinoHub /></LazyPage> },
      { path: "inventario", element: <LazyPage><MagazzinoHub /></LazyPage> },
      { path: "inventario/:data", element: <LazyPage><MagazzinoHub /></LazyPage> },
      { path: "ricerca-prodotti", element: <LazyPage><MagazzinoHub /></LazyPage> },
      { path: "ricerca-prodotti/:query", element: <LazyPage><MagazzinoHub /></LazyPage> },
      { path: "dizionario-articoli", element: <LazyPage><MagazzinoHub /></LazyPage> },
      { path: "dizionario-articoli/:articolo", element: <LazyPage><MagazzinoHub /></LazyPage> },
      { path: "magazzino-dv", element: <LazyPage><MagazzinoHub /></LazyPage> },
      
      // === CUCINA ===
      { path: "cucina", element: <LazyPage><CucinaHub /></LazyPage> },
      { path: "dizionario-prodotti", element: <LazyPage><CucinaHub /></LazyPage> },
      { path: "dizionario-prodotti/:prodotto", element: <LazyPage><CucinaHub /></LazyPage> },
      { path: "centri-costo", element: <LazyPage><CucinaHub /></LazyPage> },
      { path: "centri-costo/:centro", element: <LazyPage><CucinaHub /></LazyPage> },
      { path: "utile-obiettivo", element: <LazyPage><CucinaHub /></LazyPage> },
      { path: "utile-obiettivo/:anno", element: <LazyPage><CucinaHub /></LazyPage> },
      { path: "ricettario", element: <LazyPage><CucinaHub /></LazyPage> },
      { path: "ricettario/:tab", element: <LazyPage><CucinaHub /></LazyPage> },
      { path: "learning-machine", element: <LazyPage><LearningMachine /></LazyPage> },
      { path: "learning-machine/:tab", element: <LazyPage><LearningMachine /></LazyPage> },
      
      // === SCADENZE ===
      { path: "scadenze", element: <LazyPage><Scadenze /></LazyPage> },
      { path: "scadenze/:anno", element: <LazyPage><Scadenze /></LazyPage> },
      { path: "scadenze/:anno/:mese", element: <LazyPage><Scadenze /></LazyPage> },
      
      // === TO-DO ===
      { path: "todo", element: <LazyPage><ToDo /></LazyPage> },
      { path: "todo/:stato", element: <LazyPage><ToDo /></LazyPage> },
      
      // === IMPORT DOCUMENTI (centralizzato) ===
      { path: "import-documenti", element: <LazyPage><ImportDocumentiHub /></LazyPage> },
      { path: "import-unificato", element: <LazyPage><ImportDocumentiHub /></LazyPage> },
      { path: "import-unificato/:tipo", element: <LazyPage><ImportDocumentiHub /></LazyPage> },
      { path: "import-export", element: <LazyPage><ImportDocumentiHub /></LazyPage> },
      { path: "import-ai", element: <LazyPage><ImportDocumentiHub /></LazyPage> },
      { path: "ai-parser", element: <LazyPage><ImportDocumentiHub /></LazyPage> },
      { path: "ai-parser/:tipo", element: <LazyPage><ImportDocumentiHub /></LazyPage> },
      { path: "lettura-documenti", element: <LazyPage><ImportDocumentiHub /></LazyPage> },
      { path: "correzione-ai", element: <LazyPage><ImportDocumentiHub /></LazyPage> },
      { path: "correzione-ai/:documento", element: <LazyPage><ImportDocumentiHub /></LazyPage> },
      
      // === DOCUMENTI ===
      { path: "documenti", element: <LazyPage><DocumentiHub /></LazyPage> },
      { path: "documenti/:tipo", element: <LazyPage><DocumentiHub /></LazyPage> },
      { path: "documenti-email", element: <LazyPage><DocumentiHub /></LazyPage> },
      { path: "da-rivedere", element: <LazyPage><DocumentiHub /></LazyPage> },
      { path: "da-rivedere/:stato", element: <LazyPage><DocumentiHub /></LazyPage> },
      { path: "classificazione-email", element: <LazyPage><DocumentiHub /></LazyPage> },
      { path: "classificazione-email/:tab", element: <LazyPage><DocumentiHub /></LazyPage> },
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
    ]
  }
]);

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
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
  </React.StrictMode>
);

import React, { Suspense, lazy } from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider, Navigate } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import App from "./App.jsx";
import "./styles.css";
import "./index.css";
import "./styles/ds/ds.css"; // Ceraldi design-system tokens (canonical) — authoritative
import { AnnoProvider } from "./contexts/AnnoContext.jsx";
import { AuthProvider, RequireAuth, RequireAdmin } from "./contexts/AuthContext.jsx";
import { queryClient } from "./lib/queryClient.js";
import { ConfirmProvider } from "./components/ui/ConfirmDialog.jsx";
import { Toaster } from "./components/ui/sonner.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import Login from "./pages/Login.jsx";
import { COLORS } from "./lib/utils.js";

const PageLoader = () => (
  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh', flexDirection: 'column', gap: 16 }}>
    <div style={{ width: 48, height: 48, border: `4px solid ${COLORS.border}`, borderTop: `4px solid ${COLORS.primary}`, borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
    <span style={{ color: COLORS.textMuted, fontSize: 14 }}>Caricamento...</span>
    <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
  </div>
);

// === HUB PAGES (consolidated) ===
const DashboardHub = lazy(() => import("./pages/hub/DashboardHub.jsx"));
  // Ciclo Passivo hub rimosso - import avviene da Import Documenti
const FornitoriHub = lazy(() => import("./pages/hub/FornitoriHub.jsx"));
const PrimaNotaHub = lazy(() => import("./pages/hub/PrimaNotaHub.jsx"));
const PuliziaPrimaNota = lazy(() => import("./pages/PuliziaPrimaNota.jsx"));
const VeicoliHub = lazy(() => import("./pages/hub/VeicoliHub.jsx"));
const ContabilitaHub = lazy(() => import("./pages/hub/ContabilitaHub.jsx"));
const DocumentiHub = lazy(() => import("./pages/hub/DocumentiHub.jsx"));
const StrumentiHub = lazy(() => import("./pages/hub/StrumentiHub.jsx"));
const IntegrazioniHub = lazy(() => import("./pages/hub/IntegrazioniHub.jsx"));
const AdminHub     = lazy(() => import("./pages/hub/AdminHub.jsx"));
const Utenti       = lazy(() => import("./pages/Utenti.jsx"));
const RiconciliazioneHub = lazy(() => import("./pages/hub/RiconciliazioneHub.jsx"));
const FattureHub = lazy(() => import("./pages/hub/FattureHub.jsx"));

// === STANDALONE PAGES ===
const InserimentoRapido = lazy(() => import("./pages/InserimentoRapido.jsx"));
const Scadenze = lazy(() => import("./pages/Scadenze.jsx"));
const GestioneRiservata = lazy(() => import("./pages/GestioneRiservata.jsx"));
const DettaglioVerbale = lazy(() => import("./pages/DettaglioVerbale.jsx"));
const ImpostazioniF24Email = lazy(() => import("./pages/ImpostazioniF24Email.jsx"));
const ImpostazioniAI = lazy(() => import("./pages/ImpostazioniAI.jsx"));
const MappaGestionale = lazy(() => import("./pages/MappaGestionale.jsx"));
const DatiProvvisoriPage = lazy(() => import("./pages/DatiProvvisoriPage.jsx"));
const AgentiPage = lazy(() => import("./pages/Agenti.jsx"));
const LearningMachine = lazy(() => import("./pages/LearningMachine.jsx"));
const DashboardRelazionale = lazy(() => import("./pages/DashboardRelazionale.jsx"));
const PaginaNonTrovata = lazy(() => import("./pages/PaginaNonTrovata.jsx"));
const DocumentiFiscali = lazy(() => import("./pages/DocumentiFiscali.jsx"));
const GestioneIVA = lazy(() => import("./pages/GestioneIVA.jsx"));
const FattureEstereVerifica = lazy(() => import("./pages/FattureEstereVerifica.jsx"));

const LazyPage = ({ children }) => (
  <Suspense fallback={<PageLoader />}>{children}</Suspense>
);

const router = createBrowserRouter([
  { path: "/login", element: <Login /> },
  { path: "/gestione-riservata", element: <LazyPage><GestioneRiservata /></LazyPage> },
  {
    path: "/",
    element: <RequireAuth><App /></RequireAuth>,
    children: [
      // === DASHBOARD ===
      { index: true, element: <LazyPage><DashboardHub /></LazyPage> },
      { path: "dashboard", element: <LazyPage><DashboardHub /></LazyPage> },
      { path: "dashboard-relazionale", element: <LazyPage><DashboardHub /></LazyPage> },
      { path: "dashboard/:anno", element: <LazyPage><DashboardHub /></LazyPage> },
      { path: "analytics", element: <LazyPage><DashboardHub /></LazyPage> },
      { path: "analytics/:periodo", element: <LazyPage><DashboardHub /></LazyPage> },
      
      // === INSERIMENTO RAPIDO ===
      { path: "rapido", element: <LazyPage><InserimentoRapido /></LazyPage> },

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
      { path: "prima-nota/pulizia", element: <LazyPage><PrimaNotaHub /></LazyPage> },
      { path: "prima-nota/:tipo", element: <LazyPage><PrimaNotaHub /></LazyPage> },
      { path: "prima-nota/:tipo/:anno/:mese", element: <LazyPage><PrimaNotaHub /></LazyPage> },
      { path: "dati-provvisori", element: <Navigate to="/prima-nota#sezione=provvisori" replace /> },
      
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
      { path: "utile-obiettivo", element: <Navigate to="/contabilita/utile" replace /> },
      { path: "utile-obiettivo/:anno", element: <Navigate to="/contabilita/utile" replace /> },
      { path: "previsioni-acquisti", element: <Navigate to="/contabilita/previsioni-acquisti" replace /> },
      { path: "previsioni-acquisti/:anno", element: <LazyPage><ContabilitaHub /></LazyPage> },
      
      // === COERENZA POS sotto RICONCILIAZIONE ===
      { path: "coerenza-pos", element: <Navigate to="/riconciliazione/coerenza-pos" replace /> },
      { path: "magazzino", element: <Navigate to="/riconciliazione/coerenza-pos" replace /> },
      { path: "magazzino/:tab", element: <Navigate to="/riconciliazione/coerenza-pos" replace /> },
      { path: "inventario", element: <Navigate to="/riconciliazione/coerenza-pos" replace /> },
      { path: "inventario/:data", element: <Navigate to="/riconciliazione/coerenza-pos" replace /> },
      { path: "ricerca-prodotti", element: <Navigate to="/riconciliazione/coerenza-pos" replace /> },
      { path: "ricerca-prodotti/:query", element: <Navigate to="/riconciliazione/coerenza-pos" replace /> },
      { path: "dizionario-articoli", element: <Navigate to="/riconciliazione/coerenza-pos" replace /> },
      { path: "dizionario-articoli/:articolo", element: <Navigate to="/riconciliazione/coerenza-pos" replace /> },
      { path: "dizionario-prodotti", element: <Navigate to="/riconciliazione/coerenza-pos" replace /> },
      { path: "dizionario-prodotti/:prodotto", element: <Navigate to="/riconciliazione/coerenza-pos" replace /> },
      { path: "magazzino-dv", element: <Navigate to="/riconciliazione/coerenza-pos" replace /> },
      
      { path: "centri-costo", element: <Navigate to="/contabilita/centri-costo" replace /> },
      { path: "centri-costo/:centro", element: <Navigate to="/contabilita/centri-costo" replace /> },
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
      { path: "archivio-bonifici", element: <Navigate to="/riconciliazione/archivio-bonifici" replace /> },
      { path: "paypal", element: <Navigate to="/riconciliazione/paypal" replace /> },

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
      { path: "visure", element: <Navigate to="/strumenti/visure" replace /> },
      { path: "impostazioni-f24-email", element: <LazyPage><ImpostazioniF24Email /></LazyPage> },
      { path: "impostazioni-ai", element: <LazyPage><ImpostazioniAI /></LazyPage> },
      
      // === INTEGRAZIONI ===
      { path: "integrazioni", element: <LazyPage><IntegrazioniHub /></LazyPage> },
      { path: "integrazioni-openapi", element: <Navigate to="/integrazioni" replace /> },
      { path: "integrazioni-openapi/:tab", element: <LazyPage><IntegrazioniHub /></LazyPage> },
      { path: "integrazioni/mittenti-email", element: <LazyPage><IntegrazioniHub /></LazyPage> },
      { path: "pagopa", element: <Navigate to="/integrazioni/pagopa" replace /> },
      { path: "pagopa/:pratica", element: <Navigate to="/integrazioni/pagopa" replace /> },

      // === ADMIN ===
      { path: "admin", element: <RequireAdmin><LazyPage><AdminHub /></LazyPage></RequireAdmin> },
      { path: "admin/:sezione", element: <RequireAdmin><LazyPage><AdminHub /></LazyPage></RequireAdmin> },
      { path: "utenti", element: <RequireAdmin><LazyPage><Utenti /></LazyPage></RequireAdmin> },
      { path: "batch-reprocessing", element: <LazyPage><AdminHub /></LazyPage> },
      { path: "batch-processor", element: <LazyPage><AdminHub /></LazyPage> },
      
      // === MAPPA GESTIONALE ===
      { path: "mappa-gestionale", element: <LazyPage><MappaGestionale /></LazyPage> },

      // === DOCUMENTI FISCALI (dichiarazione IVA, esattoriali, avvisi bonari) ===
      { path: "documenti-fiscali", element: <LazyPage><DocumentiFiscali /></LazyPage> },

      // === GESTIONE IVA (attribuzione periodo per competenza, IVA non utilizzata) ===
      { path: "iva", element: <LazyPage><GestioneIVA /></LazyPage> },

      // === FATTURE ESTERE — coda di verifica lettura AI ===
      { path: "fatture-estere-verifica", element: <LazyPage><FattureEstereVerifica /></LazyPage> },

      // === REDIRECT ROTTE LEGACY / MANCANTI ===
      { path: "fisco", element: <Navigate to="/contabilita/calendario" replace /> },
      { path: "fisco/*", element: <Navigate to="/contabilita/calendario" replace /> },
      { path: "riconciliazione-unificata", element: <Navigate to="/riconciliazione" replace /> },
      
      // === CATCH-ALL: pagina 404 REALE (prima: redirect silenzioso alla
      // Dashboard, che mascherava i link interni sbagliati) ===
      { path: "*", element: <LazyPage><PaginaNonTrovata /></LazyPage> },
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
            <Toaster richColors position="top-right" />
          </ConfirmProvider>
        </AnnoProvider>
      </AuthProvider>
    </QueryClientProvider>
  </ErrorBoundary>
);

// Service Worker: registrazione minima solo per abilitare "Installa app"
// (PWA) su Chrome/Android. Non fa cache di nulla (vedi service-worker.js),
// quindi non può servire contenuti stale dopo un deploy. Il browser rifà
// sempre il fetch dello script del SW bypassando l'eventuale SW attivo,
// quindi questa registrazione sostituisce da sé il vecchio kill-switch
// (o un SW ancora più vecchio con cache) su qualunque dispositivo.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/service-worker.js')
      .catch(e => console.warn('Service worker non registrato (Installa app non disponibile):', e));
  });
}



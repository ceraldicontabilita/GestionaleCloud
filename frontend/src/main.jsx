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
import HRGate from "./hr/HRGate.jsx";
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
const FornitoriHub = lazy(() => import("./pages/hub/FornitoriHub.jsx"));
const PrimaNotaHub = lazy(() => import("./pages/hub/PrimaNotaHub.jsx"));
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
const Ritenute = lazy(() => import("./pages/Ritenute.jsx"));
const GestioneRiservata = lazy(() => import("./pages/GestioneRiservata.jsx"));
const DettaglioVerbale = lazy(() => import("./pages/DettaglioVerbale.jsx"));
const ImpostazioniF24Email = lazy(() => import("./pages/ImpostazioniF24Email.jsx"));
const ImpostazioniAI = lazy(() => import("./pages/ImpostazioniAI.jsx"));
const MappaGestionale = lazy(() => import("./pages/MappaGestionale.jsx"));
const AgentiPage = lazy(() => import("./pages/Agenti.jsx"));
const LearningMachine = lazy(() => import("./pages/LearningMachine.jsx"));
const LegacyRouteResolver = lazy(() => import("./pages/LegacyRouteResolver.jsx"));
const GestioneIVA = lazy(() => import("./pages/GestioneIVA.jsx"));
const FattureEstereVerifica = lazy(() => import("./pages/FattureEstereVerifica.jsx"));
const CedoliniSalari = lazy(() => import("./pages/CedoliniSalari.jsx"));
const SituazioneFiscale = lazy(() => import("./pages/SituazioneFiscale.jsx"));
const TracciabilitaHACCP = lazy(() => import("./pages/TracciabilitaHACCP.jsx"));

// === MODULO HR (ex AppDipendenti): area gestione /hr e portale dipendenti /portale ===
const HRApp = lazy(() => import("./hr/HRApp.jsx"));
const PortaleDipendente = lazy(() => import("./hr/PortaleDipendente.jsx"));

const LazyPage = ({ children }) => (
  <Suspense fallback={<PageLoader />}>{children}</Suspense>
);

// L'anno operativo e' un dato autenticato: il provider non deve interrogare
// endpoint protetti sulla pagina pubblica di login (prima produceva un 401 su
// ogni apertura della SPA e rumore E2E/console).
const AuthenticatedApp = () => (
  <RequireAuth>
    <AnnoProvider>
      <App />
    </AnnoProvider>
  </RequireAuth>
);

const router = createBrowserRouter([
  { path: "/login", element: <Login /> },
  { path: "/gestione-riservata", element: <LazyPage><GestioneRiservata /></LazyPage> },
  // Portale dipendenti: login con PIN personale, fuori dalla sessione del gestionale.
  { path: "/portale", element: <LazyPage><PortaleDipendente /></LazyPage> },
  // Pagina Turni per il responsabile turni (token del portale, non del gestionale).
  { path: "/hr-turni", element: <LazyPage><HRGate roles={["responsabile_turni"]}><HRApp page="turni" /></HRGate></LazyPage> },
  {
    path: "/",
    element: <AuthenticatedApp />,
    children: [
      // Route canoniche: ogni hub gestisce internamente le proprie sottosezioni.
      { index: true, element: <LazyPage><DashboardHub /></LazyPage> },
      { path: "dashboard/*", element: <LazyPage><DashboardHub /></LazyPage> },
      { path: "rapido", element: <LazyPage><InserimentoRapido /></LazyPage> },
      { path: "fatture/import", element: <Navigate to="/documenti/import" replace /> },
      { path: "fatture/*", element: <LazyPage><FattureHub /></LazyPage> },
      { path: "fornitori/*", element: <LazyPage><FornitoriHub /></LazyPage> },
      { path: "prima-nota/*", element: <LazyPage><PrimaNotaHub /></LazyPage> },
      { path: "salari", element: <LazyPage><CedoliniSalari /></LazyPage> },
      { path: "noleggio/*", element: <LazyPage><VeicoliHub /></LazyPage> },
      { path: "verbali-noleggio/:numeroVerbale", element: <LazyPage><DettaglioVerbale /></LazyPage> },
      { path: "verbali-noleggio/:prefisso/:numero", element: <LazyPage><DettaglioVerbale /></LazyPage> },
      { path: "contabilita/*", element: <LazyPage><ContabilitaHub /></LazyPage> },
      { path: "learning-machine/*", element: <LazyPage><LearningMachine /></LazyPage> },
      { path: "scadenze/*", element: <LazyPage><Scadenze /></LazyPage> },
      { path: "ritenute", element: <LazyPage><Ritenute /></LazyPage> },
      { path: "riconciliazione/*", element: <LazyPage><RiconciliazioneHub /></LazyPage> },
      { path: "documenti/*", element: <LazyPage><DocumentiHub /></LazyPage> },
      { path: "strumenti/*", element: <LazyPage><StrumentiHub /></LazyPage> },
      { path: "agenti", element: <LazyPage><AgentiPage /></LazyPage> },
      { path: "impostazioni-f24-email", element: <LazyPage><ImpostazioniF24Email /></LazyPage> },
      { path: "impostazioni-ai", element: <LazyPage><ImpostazioniAI /></LazyPage> },
      { path: "integrazioni/*", element: <LazyPage><IntegrazioniHub /></LazyPage> },
      { path: "admin/*", element: <RequireAdmin><LazyPage><AdminHub /></LazyPage></RequireAdmin> },
      { path: "utenti", element: <RequireAdmin><LazyPage><Utenti /></LazyPage></RequireAdmin> },
      { path: "mappa-gestionale", element: <LazyPage><MappaGestionale /></LazyPage> },
      { path: "iva/*", element: <LazyPage><GestioneIVA /></LazyPage> },
      { path: "situazione-fiscale/*", element: <RequireAdmin><LazyPage><SituazioneFiscale /></LazyPage></RequireAdmin> },
      { path: "fatture-estere-verifica", element: <LazyPage><FattureEstereVerifica /></LazyPage> },
      { path: "tracciabilita", element: <LazyPage><TracciabilitaHACCP /></LazyPage> },
      { path: "hr", element: <RequireAdmin><LazyPage><HRApp page="dashboard" /></LazyPage></RequireAdmin> },
      { path: "hr/:page", element: <RequireAdmin><LazyPage><HRApp /></LazyPage></RequireAdmin> },

      // Un solo punto di compatibilità per vecchi preferiti; altrimenti 404 reale.
      { path: "*", element: <LazyPage><LegacyRouteResolver /></LazyPage> },
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
        <ConfirmProvider>
          <RouterProvider router={router} />
          <Toaster richColors position="top-right" />
        </ConfirmProvider>
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



import React, { useState, useEffect } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import api, { setAuthToken } from "./api";
import ErrorBoundary from "./components/ErrorBoundary";
import TopNav from "./components/layout/TopNav";
import SecondaryTabs from "./components/layout/SecondaryTabs";
import { NotificheScadenze } from "./components/NotificheScadenze";
import { UploadProvider } from "./contexts/UploadContext";
import { UploadStatusBar } from "./components/UploadStatusBar";
import ChatIntelligente from "./components/ChatIntelligente";
import F24EmailSync from "./components/F24EmailSync";
import "./styles/topnav.css";

// Mobile navigation items
const MOBILE_NAV = [
  { to: "/", label: "Home", icon: "🏠" },
  { to: "/fatture-ricevute", label: "Fatture", icon: "📄" },
  { to: "/riconciliazione", label: "Banca", icon: "🏦" },
  { to: "/dipendenti", label: "HR", icon: "👥" },
  { to: "/more", label: "Menu", icon: "☰", isMenu: true },
];

// Full menu items for mobile overlay
const ALL_NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: "📊" },
  { to: "/rapido", label: "Inserimento Rapido", icon: "📱" },
  { to: "/fatture-ricevute", label: "Ciclo Passivo", icon: "🧾" },
  { to: "/fornitori", label: "Fornitori", icon: "🏢" },
  { to: "/prima-nota", label: "Prima Nota", icon: "📒" },
  { to: "/riconciliazione", label: "Riconciliazione", icon: "🏦" },
  { to: "/dipendenti", label: "Dipendenti", icon: "👥" },
  { to: "/cedolini", label: "Cedolini", icon: "📄" },
  { to: "/f24", label: "F24", icon: "📋" },
  { to: "/iva", label: "IVA", icon: "📊" },
  { to: "/fisco", label: "Fisco", icon: "🏛️" },
  { to: "/bilancio", label: "Bilancio", icon: "📊" },
  { to: "/mutui", label: "Mutui", icon: "🏦" },
  { to: "/contabilita-hub", label: "Contabilità", icon: "📈" },
  { to: "/magazzino", label: "Magazzino", icon: "📦" },
  { to: "/cucina", label: "Cucina", icon: "🍳" },
  { to: "/scadenze", label: "Scadenze", icon: "🔔" },
  { to: "/todo", label: "To-Do", icon: "📝" },
  { to: "/import-documenti", label: "Import", icon: "📥" },
  { to: "/documenti", label: "Documenti", icon: "📨" },
  { to: "/strumenti", label: "Strumenti", icon: "🔧" },
  { to: "/integrazioni", label: "Integrazioni", icon: "🔗" },
  { to: "/agenti", label: "Agenti AI", icon: "🤖" },
  { to: "/admin", label: "Admin", icon: "⚙️" },
];

export default function App() {
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const [alertCommercialista, setAlertCommercialista] = useState(null);
  const [showF24Sync, setShowF24Sync] = useState(false);
  const [processingGoogleAuth, setProcessingGoogleAuth] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  // Google OAuth processing
  useEffect(() => {
    const processGoogleAuth = async () => {
      const hash = window.location.hash;
      if (hash && hash.includes('session_id=')) {
        setProcessingGoogleAuth(true);
        const sessionIdMatch = hash.match(/session_id=([^&]+)/);
        if (sessionIdMatch) {
          const sessionId = sessionIdMatch[1];
          try {
            console.log('[App] Processando Google OAuth session_id...');
            const response = await api.post('/api/auth/google/session', { session_id: sessionId });
            if (response.data.success) {
              console.log('[App] Google OAuth completato:', response.data.user?.email);
              if (response.data.access_token) {
                setAuthToken(response.data.access_token);
              }
              window.history.replaceState(null, '', window.location.pathname);
              navigate('/', { replace: true });
            }
          } catch (error) {
            console.error('[App] Errore Google OAuth:', error);
            window.history.replaceState(null, '', window.location.pathname);
          }
        }
        setProcessingGoogleAuth(false);
      }
    };
    processGoogleAuth();
  }, []);

  // Load commercialista alert
  useEffect(() => {
    const loadAlertCommercialista = async () => {
      try {
        const res = await api.get('/api/commercialista/alert-status');
        if (res.data.show_alert) {
          // Controlla se l'utente ha già chiuso questo avviso (per mese/anno)
          const dismissKey = `alert_dismissed_${res.data.mese_pendente}_${res.data.anno_pendente}`;
          if (!localStorage.getItem(dismissKey)) {
            setAlertCommercialista(res.data);
          }
        }
      } catch (e) {
        // Silently fail
      }
    };
    loadAlertCommercialista();
  }, []);

  // Google Auth loading screen
  if (processingGoogleAuth) {
    return (
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#daeafc',
        color: '#1a40b5',
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{
            width: 48, height: 48,
            border: '3px solid #1a40b5',
            borderTopColor: 'transparent',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
            margin: '0 auto 16px',
          }} />
          <p style={{ fontWeight: 600 }}>Accesso con Google in corso...</p>
          <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
        </div>
      </div>
    );
  }

  return (
    <UploadProvider>
      <div className="topnav-layout" data-testid="topnav-layout">
        {/* Banner notifiche browser rimosso */}

        {/* Upload Status Bar */}
        <UploadStatusBar />

        {/* F24 Email Sync Popup */}
        {showF24Sync && (
          <F24EmailSync onClose={() => setShowF24Sync(false)} />
        )}

        {/* TOP NAVIGATION - Primary */}
        <TopNav />

        {/* SECONDARY TABS - Context-sensitive */}
        <SecondaryTabs />

        {/* Mobile Bottom Navigation */}
        <nav className="mobile-nav-topnav" data-testid="mobile-nav">
          {MOBILE_NAV.map((item) => (
            item.isMenu ? (
              <button
                key="menu"
                className="mobile-nav-item"
                onClick={() => setShowMobileMenu(!showMobileMenu)}
                data-testid="mobile-menu-toggle"
              >
                <span className="mobile-nav-icon">{item.icon}</span>
                <span className="mobile-nav-label">{item.label}</span>
              </button>
            ) : (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => `mobile-nav-item ${isActive ? "active" : ""}`}
                onClick={() => setShowMobileMenu(false)}
              >
                <span className="mobile-nav-icon">{item.icon}</span>
                <span className="mobile-nav-label">{item.label}</span>
              </NavLink>
            )
          ))}
        </nav>

        {/* Mobile Menu Overlay */}
        {showMobileMenu && (
          <div
            className="mobile-menu-overlay"
            onClick={() => setShowMobileMenu(false)}
            data-testid="mobile-menu-overlay"
          >
            <div className="mobile-menu" onClick={(e) => e.stopPropagation()}>
              <div className="mobile-menu-header">
                <div className="brand-square">CG</div>
                <span style={{ fontWeight: 700, fontSize: 16, color: '#1a40b5' }}>Ceraldi ERP</span>
                <button
                  className="mobile-menu-close"
                  onClick={() => setShowMobileMenu(false)}
                >
                  ✕
                </button>
              </div>
              <div className="mobile-menu-items">
                {ALL_NAV_ITEMS.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === '/'}
                    className={({ isActive }) => `mobile-menu-item ${isActive ? "active" : ""}`}
                    onClick={() => setShowMobileMenu(false)}
                  >
                    <span style={{ fontSize: 20 }}>{item.icon}</span>
                    <span>{item.label}</span>
                  </NavLink>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Main Content */}
        <main className="page-content" data-testid="page-content">
          {/* Alert Commercialista */}
          {alertCommercialista && (
            <div style={{
              background: 'linear-gradient(135deg, #ff9800 0%, #f57c00 100%)',
              color: 'white',
              padding: '12px 20px',
              display: 'flex',
              alignItems: 'center',
              gap: 15,
              marginBottom: 20,
              borderRadius: 10,
            }}>
              <span style={{ fontSize: 24 }}>⚠️</span>
              <div style={{ flex: 1 }}>
                <strong>{alertCommercialista.message}</strong>
              </div>
              <NavLink
                to={`/commercialista?mese=${alertCommercialista?.mese_pendente || ''}&anno=${alertCommercialista?.anno_pendente || ''}`}
                style={{
                  padding: '8px 16px',
                  background: 'white',
                  color: '#f57c00',
                  borderRadius: 6,
                  fontWeight: 'bold',
                  textDecoration: 'none',
                  fontSize: 13
                }}
                onClick={() => {
                  if (alertCommercialista) {
                    const dismissKey = `alert_dismissed_${alertCommercialista.mese_pendente}_${alertCommercialista.anno_pendente}`;
                    localStorage.setItem(dismissKey, '1');
                    setAlertCommercialista(null);
                  }
                }}
              >
                Vai a Commercialista
              </NavLink>
              <button
                onClick={() => {
                  if (alertCommercialista) {
                    const dismissKey = `alert_dismissed_${alertCommercialista.mese_pendente}_${alertCommercialista.anno_pendente}`;
                    localStorage.setItem(dismissKey, '1');
                  }
                  setAlertCommercialista(null);
                }}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'white',
                  fontSize: 18,
                  cursor: 'pointer',
                  padding: 5
                }}
              >
                ✕
              </button>
            </div>
          )}

          <ErrorBoundary message="Errore nel caricamento della pagina. Prova a ricaricare.">
            <Outlet />
          </ErrorBoundary>
        </main>

        {/* Chat Intelligente AI */}
        <ChatIntelligente />

        {/* Mobile Menu Styles */}
        <style>{`
          /* Mobile Menu Overlay */
          .mobile-menu-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.5);
            z-index: 2000;
            display: flex;
            align-items: flex-end;
            animation: fadeIn 0.2s ease;
          }
          
          @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
          }
          
          .mobile-menu {
            background: white;
            width: 100%;
            max-height: 85vh;
            border-radius: 20px 20px 0 0;
            overflow: hidden;
            animation: slideUp 0.3s ease;
          }
          
          @keyframes slideUp {
            from { transform: translateY(100%); }
            to { transform: translateY(0); }
          }
          
          .mobile-menu-header {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 20px;
            border-bottom: 1px solid #e2e8f0;
            position: sticky;
            top: 0;
            background: white;
          }
          
          .mobile-menu-close {
            margin-left: auto;
            background: #f1f5f9;
            border: none;
            width: 36px;
            height: 36px;
            border-radius: 50%;
            font-size: 18px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
          }
          
          .mobile-menu-items {
            padding: 12px;
            overflow-y: auto;
            max-height: calc(85vh - 80px);
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
          }
          
          .mobile-menu-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 6px;
            padding: 16px 8px;
            border-radius: 12px;
            background: #f8fafc;
            color: #334155;
            font-size: 12px;
            text-align: center;
            transition: all 0.2s;
            text-decoration: none;
          }
          
          .mobile-menu-item:hover,
          .mobile-menu-item.active {
            background: #1a40b5;
            color: white;
          }
        `}</style>
      </div>
    </UploadProvider>
  );
}

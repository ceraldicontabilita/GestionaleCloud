import React, { useState, useEffect } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import api from "./api";
import ErrorBoundary from "./components/ErrorBoundary";
import TopNav from "./components/layout/TopNav";
import { UploadProvider } from "./contexts/UploadContext";
import { UploadStatusBar } from "./components/UploadStatusBar";
import ChatIntelligente from "./components/ChatIntelligente";
import { useWebSocketNotifications } from "./hooks/useWebSocket";
import "./styles/topnav.css";

// Navigazione: FONTE UNICA in navigation.config.js, condivisa con TopNav.jsx.
// Prima qui c'erano due elenchi mantenuti a mano (MOBILE_NAV/ALL_NAV_ITEMS)
// già andati fuori sincrono col desktop (voci ed etichette diverse).
import { NAV_TUTTE as NAV_TUTTE_RAW, NAV_MOBILE_BAR } from "./navigation.config";
import { useAuth } from "./contexts/AuthContext.jsx";

export default function App() {
  const { isAdmin, isReadOnly } = useAuth();
  // Voci solo-admin (Utenti, Admin) nascoste agli altri ruoli anche nel menù mobile.
  const NAV_TUTTE = NAV_TUTTE_RAW.filter(i => !i.adminOnly || isAdmin);
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const [alertCommercialista, setAlertCommercialista] = useState(null);
  const location = useLocation();

  // Connessione WebSocket real-time gestisce notifiche push dallo scheduler
  useWebSocketNotifications();

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

  return (
    <UploadProvider>
      <div className="topnav-layout" data-testid="topnav-layout">
        {isReadOnly && (
          <div data-testid="banner-sola-lettura" style={{
            background: '#fef3c7', color: '#92400e', textAlign: 'center',
            padding: '6px 12px', fontSize: 13, fontWeight: 600,
            borderBottom: '1px solid #fcd34d',
          }}>
            👁 Sei in modalità sola lettura: puoi consultare i dati ma non modificarli.
          </div>
        )}
        {/* Banner notifiche browser rimosso */}

        {/* Upload Status Bar */}
        <UploadStatusBar />

        {/* TOP NAVIGATION - Primary */}
        <TopNav />

        {/* SECONDARY TABS rimossi */}

        {/* Mobile Bottom Navigation */}
        <nav className="mobile-nav-topnav" data-testid="mobile-nav">
          {NAV_MOBILE_BAR.map((item) => (
            item.isMenu ? (
              <button
                key="menu"
                className="mobile-nav-item"
                onClick={() => setShowMobileMenu(!showMobileMenu)}
                data-testid="mobile-menu-toggle"
              >
                <span className="mobile-nav-icon"><item.Icon size={20} /></span>
                <span className="mobile-nav-label">{item.label}</span>
              </button>
            ) : (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) => `mobile-nav-item ${isActive ? "active" : ""}`}
                onClick={() => setShowMobileMenu(false)}
              >
                <span className="mobile-nav-icon"><item.Icon size={20} /></span>
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
                {NAV_TUTTE.map((item) => (
                  item.external ? (
                    <a
                      key={item.href}
                      href={item.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mobile-menu-item"
                      onClick={() => setShowMobileMenu(false)}
                    >
                      <item.Icon size={20} />
                      <span>{item.label}</span>
                    </a>
                  ) : (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === '/'}
                      className={({ isActive }) => `mobile-menu-item ${isActive ? "active" : ""}`}
                      onClick={() => setShowMobileMenu(false)}
                    >
                      <item.Icon size={20} />
                      <span>{item.label}</span>
                    </NavLink>
                  )
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
              background: '#b45309',
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
                to={`/strumenti/commercialista?mese=${alertCommercialista?.mese_pendente || ''}&anno=${alertCommercialista?.anno_pendente || ''}`}
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

          /* Telefoni stretti: 3 colonne comprimono le etichette, meglio 2 */
          @media (max-width: 400px) {
            .mobile-menu-items {
              grid-template-columns: repeat(2, 1fr);
            }
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

import React, { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import ErrorBoundary from "./components/ErrorBoundary";
import TopNav from "./components/layout/TopNav";
import ColonnaNavigazione from "./components/layout/ColonnaNavigazione";
import { UploadProvider } from "./contexts/UploadContext";
import { UploadStatusBar } from "./components/UploadStatusBar";
import ChatIntelligente from "./components/ChatIntelligente";
import { useWebSocketNotifications } from "./hooks/useWebSocket";
import "./styles/topnav.css";

// Navigazione: FONTE UNICA in navigation.config.js, condivisa con la colonna
// desktop (ColonnaNavigazione) e con la pagina 404.
import { gruppiVisibili, NAV_MOBILE_BAR, voceDi } from "./navigation.config";
import { useAuth } from "./contexts/AuthContext.jsx";
import { useGuscio } from "./contexts/GuscioContext.jsx";

export default function App() {
  const { isAdmin, isReadOnly } = useAuth();
  // Voci solo-admin (Utenti, Admin) nascoste agli altri ruoli anche nel menù mobile.
  const gruppi = gruppiVisibili(isAdmin);
  const location = useLocation();
  const attiva = voceDi(location.pathname)?.voce;
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const { alertCommercialista: statoCommercialista } = useGuscio();
  const [, setChiusure] = useState(0);

  // Connessione WebSocket real-time gestisce notifiche push dallo scheduler
  useWebSocketNotifications();

  // Avviso commercialista: il dato arriva dal guscio (GuscioContext).
  // Nascosto se l'utente l'ha già chiuso per quel mese/anno.
  const chiaveChiusura = s => `alert_dismissed_${s.mese_pendente}_${s.anno_pendente}`;
  const alertCommercialista = statoCommercialista?.show_alert
    && !localStorage.getItem(chiaveChiusura(statoCommercialista))
    ? statoCommercialista
    : null;
  const chiudiAlertCommercialista = () => {
    if (alertCommercialista) {
      localStorage.setItem(chiaveChiusura(alertCommercialista), '1');
    }
    setChiusure(n => n + 1);
  };

  return (
    <UploadProvider>
      <div className="topnav-layout" data-testid="topnav-layout">
        {isReadOnly && (
          <div data-testid="banner-sola-lettura" style={{
            background: '#f7eeda', color: '#92400e', textAlign: 'center',
            padding: '6px 12px', fontSize: 13, fontWeight: 600,
            borderBottom: '1px solid #fcd34d',
          }}>
            👁 Sei in modalità sola lettura: puoi consultare i dati ma non modificarli.
          </div>
        )}
        {/* Banner notifiche browser rimosso */}

        {/* Upload Status Bar */}
        <UploadStatusBar />

        {/* Barra in alto (marchio, anno, avvisi) e colonna delle sezioni */}
        <TopNav />
        <ColonnaNavigazione />

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
                <span style={{ fontWeight: 700, fontSize: 16, color: '#141413' }}>Ceraldi ERP</span>
                <button
                  className="mobile-menu-close"
                  onClick={() => setShowMobileMenu(false)}
                >
                  ✕
                </button>
              </div>
              <div className="mobile-menu-gruppi">
                {gruppi.map((gruppo) => (
                  <section key={gruppo.id}>
                    <h2 className="mobile-menu-titolo">
                      <span style={{ background: gruppo.colore }} aria-hidden="true" />
                      {gruppo.titolo}
                    </h2>
                    <div className="mobile-menu-items">
                      {gruppo.voci.map((item) => (
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
                          <Link
                            key={item.to}
                            to={item.to}
                            aria-current={attiva?.to === item.to ? "page" : undefined}
                            className={`mobile-menu-item ${attiva?.to === item.to ? "active" : ""}`}
                            onClick={() => setShowMobileMenu(false)}
                          >
                            <item.Icon size={20} />
                            <span>{item.label}</span>
                          </Link>
                        )
                      ))}
                    </div>
                  </section>
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
              background: '#8a6410',
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
                onClick={chiudiAlertCommercialista}
              >
                Vai a Commercialista
              </NavLink>
              <button
                onClick={chiudiAlertCommercialista}
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
            border-bottom: 1px solid #e6e3d9;
            position: sticky;
            top: 0;
            background: white;
          }
          
          .mobile-menu-close {
            margin-left: auto;
            background: #f2f0e9;
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
          
          .mobile-menu-gruppi {
            padding: 4px 12px 16px;
            overflow-y: auto;
            max-height: calc(85vh - 80px);
          }

          .mobile-menu-titolo {
            display: flex;
            align-items: center;
            gap: 7px;
            margin: 14px 4px 6px;
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.06em;
            color: #7a776e;
          }

          .mobile-menu-titolo span {
            width: 8px;
            height: 8px;
            border-radius: 50%;
          }

          .mobile-menu-items {
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
            background: #f6f4ee;
            color: #4c4a44;
            font-size: 12px;
            text-align: center;
            transition: all 0.2s;
            text-decoration: none;
          }
          
          .mobile-menu-item:hover,
          .mobile-menu-item.active {
            background: #c15f3c;
            color: white;
          }
        `}</style>
      </div>
    </UploadProvider>
  );
}

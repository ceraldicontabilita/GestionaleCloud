import React, { useState, useEffect } from "react";
import { NavLink, Outlet } from "react-router-dom";
import api from "./api";
import ErrorBoundary from "./components/ErrorBoundary";
import TopNav from "./components/layout/TopNav";
import { UploadProvider } from "./contexts/UploadContext";
import { UploadStatusBar } from "./components/UploadStatusBar";
import ChatIntelligente from "./components/ChatIntelligente";
import { useWebSocketNotifications } from "./hooks/useWebSocket";
import "./styles/topnav.css";

const MOBILE_NAV = [
  { to: "/", label: "Dashboard", icon: "⌂" },
  { to: "/fatture", label: "Fatture", icon: "▣" },
  { to: "/prima-nota", label: "Prima Nota", icon: "▤" },
  { to: "/riconciliazione", label: "Riconciliazione", icon: "↔" },
  { to: "/more", label: "Menu", icon: "⋯", isMenu: true },
];

const APP_DIPENDENTI_URL = "https://appdipendenti.onrender.com";

const ALL_NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: "⌂" },
  { to: "/fatture", label: "Fatture passive", icon: "▣" },
  { to: "/fatture/corrispettivi", label: "Corrispettivi", icon: "€" },
  { to: "/fornitori", label: "Fornitori", icon: "◫" },
  { to: "/prima-nota", label: "Prima Nota", icon: "▤" },
  { to: "/riconciliazione", label: "Riconciliazione", icon: "↔" },
  { to: "/riconciliazione/assegni", label: "Assegni", icon: "▦" },
  { to: "/riconciliazione/paypal", label: "PayPal", icon: "◉" },
  { to: "/riconciliazione/f24", label: "F24", icon: "■" },
  { to: "/contabilita", label: "Contabilità", icon: "▧" },
  { to: "/riconciliazione/coerenza-pos", label: "Incassi POS", icon: "▥" },
  { to: "/noleggio", label: "Noleggi", icon: "▶" },
  { to: "/scadenze", label: "Scadenze", icon: "⏱" },
  { to: "/documenti", label: "Documenti", icon: "□" },
  { to: "/documenti/import", label: "Import documenti", icon: "⬆" },
  { to: "/strumenti", label: "Strumenti", icon: "△" },
  { to: "/admin", label: "Admin", icon: "⚙" },
  { to: "/mappa-gestionale", label: "Mappa gestionale", icon: "▨" },
  { to: null, href: APP_DIPENDENTI_URL, label: "HR", icon: "◆", external: true },
];

export default function App() {
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const [alertCommercialista, setAlertCommercialista] = useState(null);

  useWebSocketNotifications();

  useEffect(() => {
    const loadAlertCommercialista = async () => {
      try {
        const res = await api.get('/api/commercialista/alert-status');
        if (res.data.show_alert) {
          const dismissKey = `alert_dismissed_${res.data.mese_pendente}_${res.data.anno_pendente}`;
          if (!localStorage.getItem(dismissKey)) {
            setAlertCommercialista(res.data);
          }
        }
      } catch (error) {
        console.warn('Impossibile caricare lo stato alert commercialista', {
          endpoint: '/api/commercialista/alert-status',
          status: error.response?.status,
          message: error.message,
        });
      }
    };
    loadAlertCommercialista();
  }, []);

  const dismissCommercialistaAlert = () => {
    if (alertCommercialista) {
      const dismissKey = `alert_dismissed_${alertCommercialista.mese_pendente}_${alertCommercialista.anno_pendente}`;
      localStorage.setItem(dismissKey, '1');
    }
    setAlertCommercialista(null);
  };

  return (
    <UploadProvider>
      <div className="topnav-layout" data-testid="topnav-layout">
        <UploadStatusBar />
        <TopNav />

        <nav className="mobile-nav-topnav" data-testid="mobile-nav" aria-label="Navigazione mobile principale">
          {MOBILE_NAV.map(item =>
            item.isMenu ? (
              <button
                key="menu"
                type="button"
                className="mobile-nav-item"
                onClick={() => setShowMobileMenu(value => !value)}
                data-testid="mobile-menu-toggle"
                aria-expanded={showMobileMenu}
                aria-controls="mobile-menu-panel"
              >
                <span className="mobile-nav-icon" aria-hidden="true">{item.icon}</span>
                <span className="mobile-nav-label">{item.label}</span>
              </button>
            ) : (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => `mobile-nav-item ${isActive ? "active" : ""}`}
                onClick={() => setShowMobileMenu(false)}
              >
                <span className="mobile-nav-icon" aria-hidden="true">{item.icon}</span>
                <span className="mobile-nav-label">{item.label}</span>
              </NavLink>
            )
          )}
        </nav>

        {showMobileMenu && (
          <div
            className="mobile-menu-overlay"
            onClick={() => setShowMobileMenu(false)}
            data-testid="mobile-menu-overlay"
            role="presentation"
          >
            <div id="mobile-menu-panel" className="mobile-menu" onClick={event => event.stopPropagation()}>
              <div className="mobile-menu-header">
                <div className="brand-square">CG</div>
                <span style={{ fontWeight: 700, fontSize: 16, color: '#1a40b5' }}>Ceraldi ERP</span>
                <button
                  type="button"
                  className="mobile-menu-close"
                  onClick={() => setShowMobileMenu(false)}
                  aria-label="Chiudi menu"
                >
                  ×
                </button>
              </div>
              <div className="mobile-menu-items">
                {ALL_NAV_ITEMS.map(item =>
                  item.external ? (
                    <a
                      key={item.href}
                      href={item.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mobile-menu-item"
                      onClick={() => setShowMobileMenu(false)}
                    >
                      <span style={{ fontSize: 20 }} aria-hidden="true">{item.icon}</span>
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
                      <span style={{ fontSize: 20 }} aria-hidden="true">{item.icon}</span>
                      <span>{item.label}</span>
                    </NavLink>
                  )
                )}
              </div>
            </div>
          </div>
        )}

        <main className="page-content" data-testid="page-content">
          {alertCommercialista && (
            <div className="commercialista-alert" role="alert">
              <span className="commercialista-alert__icon" aria-hidden="true">🔔</span>
              <div className="commercialista-alert__message">
                <strong>{alertCommercialista.message}</strong>
              </div>
              <NavLink
                to={`/commercialista?mese=${alertCommercialista?.mese_pendente || ''}&anno=${alertCommercialista?.anno_pendente || ''}`}
                className="commercialista-alert__action"
                onClick={dismissCommercialistaAlert}
              >
                Vai a Commercialista
              </NavLink>
              <button
                type="button"
                onClick={dismissCommercialistaAlert}
                className="commercialista-alert__close"
                aria-label="Chiudi avviso commercialista"
              >
                ×
              </button>
            </div>
          )}

          <ErrorBoundary message="Errore nel caricamento della pagina. Prova a ricaricare.">
            <Outlet />
          </ErrorBoundary>
        </main>

        <ChatIntelligente />

        <style>{`
          .mobile-menu-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.5);
            z-index: 2000;
            display: flex;
            align-items: flex-end;
            animation: fadeIn 0.2s ease;
          }
          @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
          .mobile-menu {
            background: white;
            width: 100%;
            max-height: 85vh;
            border-radius: 20px 20px 0 0;
            overflow: hidden;
            animation: slideUp 0.3s ease;
          }
          @keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
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
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 8px;
          }
          .mobile-menu-item {
            display: flex;
            min-width: 0;
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
            overflow-wrap: anywhere;
            transition: all 0.2s;
            text-decoration: none;
          }
          .mobile-menu-item:hover,
          .mobile-menu-item.active { background: #1a40b5; color: white; }
          .commercialista-alert {
            background: #b45309;
            color: white;
            padding: 12px 20px;
            display: grid;
            grid-template-columns: auto minmax(0, 1fr) auto auto;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
            border-radius: 10px;
            min-width: 0;
          }
          .commercialista-alert__icon { font-size: 24px; }
          .commercialista-alert__message { min-width: 0; overflow-wrap: anywhere; }
          .commercialista-alert__action {
            padding: 8px 16px;
            background: white;
            color: #b45309;
            border-radius: 6px;
            font-weight: 700;
            text-decoration: none;
            font-size: 13px;
            text-align: center;
          }
          .commercialista-alert__close {
            background: transparent;
            border: none;
            color: white;
            font-size: 20px;
            cursor: pointer;
            padding: 5px;
          }
          @media (max-width: 399px) {
            .mobile-menu-items { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          }
          @media (max-width: 600px) {
            .commercialista-alert {
              grid-template-columns: auto minmax(0, 1fr) auto;
              padding: 12px;
            }
            .commercialista-alert__action {
              grid-column: 1 / -1;
              width: 100%;
            }
          }
        `}</style>
      </div>
    </UploadProvider>
  );
}

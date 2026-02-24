import React, { useState, useEffect } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import api from "./api";
import ErrorBoundary from "./components/ErrorBoundary";
import GlobalSearch from "./components/GlobalSearch";
import { AnnoSelector } from "./contexts/AnnoContext";
import F24EmailSync from "./components/F24EmailSync";
import NotificationBell from "./components/NotificationBell";
import { NotificheScadenze } from "./components/NotificheScadenze";
import { UploadProvider } from "./contexts/UploadContext";
import { UploadStatusBar } from "./components/UploadStatusBar";
import ChatIntelligente from "./components/ChatIntelligente";

const NAV_ITEMS = [
  { to: "/rapido", label: "Inserimento Rapido", icon: "📱", short: "Rapido" },
  { to: "/", label: "Dashboard", icon: "📊", short: "Home" },
  { to: "/fatture-ricevute", label: "Ciclo Passivo", icon: "📋", short: "Fatture" },
  { to: "/fornitori", label: "Fornitori", icon: "📦", short: "Fornit." },
  { to: "/prima-nota", label: "Prima Nota", icon: "📒", short: "P.Nota" },
  { to: "/riconciliazione", label: "Riconciliazione", icon: "🔄", short: "Riconc." },
  { to: "/dipendenti", label: "Dipendenti", icon: "👥", short: "Dipend." },
  { to: "/fisco", label: "Fisco & Tributi", icon: "🏛️", short: "Fisco" },
  { to: "/bilancio", label: "Bilancio", icon: "📊", short: "Bilancio" },
  { to: "/mutui", label: "Mutui", icon: "🏦", short: "Mutui" },
  { to: "/contabilita-hub", label: "Contabilità", icon: "📈", short: "Contab." },
  { to: "/magazzino", label: "Magazzino", icon: "📦", short: "Magaz." },
  { to: "/cucina", label: "Cucina", icon: "🍳", short: "Cucina" },
  { to: "/scadenze", label: "Scadenze", icon: "🔔", short: "Scad." },
  { to: "/todo", label: "To-Do", icon: "📝", short: "ToDo" },
  { to: "/api/openclaw/ui/", label: "OpenClaw AI", icon: "🤖", short: "AI", external: true },
  { to: "/import-documenti", label: "Import Documenti", icon: "📥", short: "Import" },
  { to: "/documenti", label: "Documenti", icon: "📨", short: "Docs" },
  { to: "/strumenti", label: "Strumenti", icon: "🔧", short: "Tools" },
  { to: "/integrazioni", label: "Integrazioni", icon: "🔗", short: "Integr." },
  { to: "/admin", label: "Admin", icon: "⚙️", short: "Admin" },
];

const MOBILE_NAV = [
  { to: "/", label: "Home", icon: "🏠" },
  { to: "/fatture-ricevute", label: "Fatture", icon: "📄" },
  { to: "/riconciliazione", label: "Banca", icon: "🏦" },
  // DIPENDENTI RIMOSSO
  { to: "/more", label: "Menu", icon: "☰", isMenu: true },
];

export default function App() {
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const [notificheNonLette, setNotificheNonLette] = useState(0);
  const [alertCommercialista, setAlertCommercialista] = useState(null);
  const [showF24Sync, setShowF24Sync] = useState(false);
  const [processingGoogleAuth, setProcessingGoogleAuth] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  // IMPORTANTE: Intercetta session_id da Google OAuth nel fragment URL
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
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
              // Rimuovi il fragment dall'URL
              window.history.replaceState(null, '', window.location.pathname);
              // Ricarica per aggiornare lo stato auth
              window.location.reload();
            }
          } catch (error) {
            console.error('[App] Errore Google OAuth:', error);
            // Rimuovi il fragment e continua
            window.history.replaceState(null, '', window.location.pathname);
          }
        }
        setProcessingGoogleAuth(false);
      }
    };
    processGoogleAuth();
  }, []);

  // Se sta processando Google Auth, mostra loading
  if (processingGoogleAuth) {
    return (
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--ink)',
        color: 'var(--surface)',
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{
            width: 48, height: 48,
            border: '3px solid var(--primary)',
            borderTopColor: 'transparent',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
            margin: '0 auto 16px',
          }} />
          <p>Accesso con Google in corso...</p>
        </div>
      </div>
    );
  }

  // PLACEHOLDER - removed submenu toggle

  // Carica notifiche non lette all'avvio e ogni 60 secondi
  useEffect(() => {
    // Carica alert commercialista
    const loadAlertCommercialista = async () => {
      try {
        const res = await api.get('/api/commercialista/alert-status');
        if (res.data.show_alert) {
          setAlertCommercialista(res.data);
        }
      } catch (e) {
        // Silently fail
      }
    };
    
    loadAlertCommercialista();
  }, []);

  return (
    <UploadProvider>
    <div className="layout">
      {/* Notifiche Scadenze Browser */}
      <NotificheScadenze showBanner={true} />
      
      {/* Upload Status Bar - sempre visibile */}
      <UploadStatusBar />
      
      {/* F24 Email Sync Popup - Mostrato all'avvio */}
      {showF24Sync && (
        <F24EmailSync onClose={() => setShowF24Sync(false)} />
      )}

      {/* Desktop Sidebar */}
      <aside className="sidebar desktop-sidebar">
        <div className="brand">
          <div className="brand-content" style={{ justifyContent: 'center' }}>
            <img src="/logo-ceraldi.png" alt="Ceraldi Caffè" style={{ height: 32 }} />
          </div>
          <NotificationBell />
        </div>
        <div style={{ padding: '0 6px', marginBottom: 8 }}>
          <GlobalSearch />
        </div>
        <div style={{ padding: '0 6px', marginBottom: 10 }}>
          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: 6,
            padding: '6px 10px',
            background: 'var(--bg)',
            borderRadius: 6
          }}>
            <span style={{ fontSize: 10, color: 'var(--ink3)' }}>Anno:</span>
            <AnnoSelector style={{ flex: 1, border: 'none', background: 'white', fontSize: 11, padding: '4px 8px', minHeight: 26 }} />
          </div>
        </div>
        <nav className="nav">
          {NAV_ITEMS.map((item) => (
            item.external ? (
              <a
                key={item.to}
                href={item.to}
                className="nav-link"
                target="_blank"
                rel="noopener noreferrer"
                style={{ position: 'relative' }}
              >
                <span style={{ fontSize: 13, marginRight: 8 }}>{item.icon}</span>
                <span>{item.label}</span>
              </a>
            ) : (
              <NavLink 
                key={item.to} 
                to={item.to} 
                end={item.to === '/'}
                className={({ isActive }) => isActive ? "active" : ""}
                style={{ position: 'relative' }}
              >
                <span style={{ fontSize: 13, marginRight: 8 }}>{item.icon}</span>
                <span>{item.label}</span>
              </NavLink>
            )
          ))}
        </nav>
        <div style={{
          padding: '12px',
          borderTop: '1px solid var(--nav-border)',
          marginTop: 'auto',
        }}>
          <button
            onClick={() => {
              localStorage.removeItem('auth_token');
              window.location.href = '/login';
            }}
            style={{
              width: '100%',
              padding: '8px',
              background: 'var(--danger-bg)',
              border: '1px solid var(--danger-border)',
              borderRadius: 6,
              color: 'var(--danger)',
              fontSize: 13,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              e.target.style.background = 'rgba(239,68,68,0.2)';
            }}
            onMouseLeave={(e) => {
              e.target.style.background = 'rgba(239,68,68,0.1)';
            }}
          >
            🚪 <span className="nav-label">Esci</span>
          </button>
        </div>
      </aside>

      {/* Mobile Bottom Navigation */}
      <nav className="mobile-nav">
        {MOBILE_NAV.map((item) => (
          item.isMenu ? (
            <button 
              key="menu" 
              className="mobile-nav-item"
              onClick={() => setShowMobileMenu(!showMobileMenu)}
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
        <div className="mobile-menu-overlay" onClick={() => setShowMobileMenu(false)}>
          <div className="mobile-menu" onClick={(e) => e.stopPropagation()}>
            <div className="mobile-menu-header">
              <img src="/logo-ceraldi.png" alt="Ceraldi Caffè" style={{ height: 28 }} />
              <span style={{ fontWeight: 700, fontSize: 16 }}>Menu</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <NotificationBell />
                <button 
                  className="mobile-menu-close"
                  onClick={() => setShowMobileMenu(false)}
                >
                  ✕
                </button>
              </div>
            </div>
            {/* Anno Selector per Mobile */}
            <div style={{ 
              padding: '12px 16px', 
              borderBottom: '1px solid #eee',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              background: '#f8fafc'
            }}>
              <span style={{ fontSize: 13, color: 'var(--ink3)' }}>📅 Anno:</span>
              <AnnoSelector style={{ 
                flex: 1, 
                border: '1px solid #e2e8f0', 
                background: 'white', 
                fontSize: 14, 
                padding: '8px 12px',
                borderRadius: 6
              }} />
            </div>
            <div className="mobile-menu-items">
              {NAV_ITEMS.map((item) => (
                item.external ? (
                  <a
                    key={item.to}
                    href={item.to}
                    className="mobile-menu-item"
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => setShowMobileMenu(false)}
                  >
                    <span style={{ fontSize: 20 }}>{item.icon}</span>
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
                    <span style={{ fontSize: 20 }}>{item.icon}</span>
                    <span>{item.label}</span>
                  </NavLink>
                )
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="content">
        {/* Alert Commercialista */}
        {alertCommercialista && (
          <div style={{
            background: 'linear-gradient(135deg, #ff9800 0%, #f57c00 100%)',
            color: 'white',
            padding: '12px 20px',
            display: 'flex',
            alignItems: 'center',
            gap: 15,
            marginBottom: 0
          }}>
            <span style={{ fontSize: 24 }}>⚠️</span>
            <div style={{ flex: 1 }}>
              <strong>{alertCommercialista.message}</strong>
            </div>
            <NavLink 
              to="/commercialista" 
              style={{
                padding: '8px 16px',
                background: 'white',
                color: '#f57c00',
                borderRadius: 6,
                fontWeight: 'bold',
                textDecoration: 'none',
                fontSize: 13
              }}
            >
              Vai a Commercialista
            </NavLink>
            <button
              onClick={() => setAlertCommercialista(null)}
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

      <style>{`
        /* Desktop Sidebar - Hidden on Mobile - UI COMPATTA */
        .desktop-sidebar {
          display: none;
        }
        
        @media (min-width: 768px) {
          .desktop-sidebar {
            display: block;
            background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
            color: white;
            width: 220px;
            min-width: 220px;
            max-width: 220px;
            height: 100vh;
            position: fixed;
            left: 0;
            top: 0;
            padding: 12px 8px;
            overflow-y: auto;
            overflow-x: hidden;
            z-index: 1000;
          }
          
          .desktop-sidebar .brand {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            font-weight: 700;
            font-size: 13px;
            padding: 8px 10px;
            margin-bottom: 12px;
          }
          
          .desktop-sidebar .brand-content {
            display: flex;
            align-items: center;
            gap: 8px;
          }
          
          .desktop-sidebar .nav {
            display: flex;
            flex-direction: column;
            gap: 2px;
          }
          
          .desktop-sidebar .nav a {
            display: flex;
            align-items: center;
            padding: 7px 10px;
            border-radius: 6px;
            color: rgba(255, 255, 255, 0.7);
            font-size: 12px;
            transition: all 0.2s;
          }
          
          .desktop-sidebar .nav a:hover {
            background: rgba(255, 255, 255, 0.1);
            color: white;
          }
          
          .desktop-sidebar .nav a.active {
            background: #2563eb;
            color: white;
            box-shadow: 0 2px 8px rgba(37, 99, 235, 0.4);
          }
          
          /* Submenu styles - COMPATTI */
          .nav-submenu {
            display: flex;
            flex-direction: column;
          }
          
          .nav-submenu-trigger {
            display: flex;
            align-items: center;
            padding: 7px 10px;
            border-radius: 6px;
            color: rgba(255, 255, 255, 0.7);
            font-size: 12px;
            transition: all 0.2s;
            background: transparent;
            border: none;
            cursor: pointer;
            width: 100%;
            text-align: left;
          }
          
          .nav-submenu-trigger:hover {
            background: rgba(255, 255, 255, 0.1);
            color: white;
          }
          
          .nav-submenu-trigger.open {
            background: rgba(255, 255, 255, 0.05);
            color: white;
          }
          
          .submenu-arrow {
            margin-left: auto;
            font-size: 9px;
            opacity: 0.6;
          }
          
          .nav-submenu-items {
            display: flex;
            flex-direction: column;
            gap: 1px;
            padding-left: 16px;
            margin-top: 2px;
            margin-bottom: 2px;
            border-left: 2px solid rgba(255, 255, 255, 0.1);
            margin-left: 16px;
          }
          
          .nav-submenu-item {
            display: flex;
            align-items: center;
            padding: 6px 10px;
            border-radius: 5px;
            color: rgba(255, 255, 255, 0.6);
            font-size: 11px;
            transition: all 0.2s;
          }
          
          .nav-submenu-item:hover {
            background: rgba(255, 255, 255, 0.1);
            color: white;
          }
          
          .nav-submenu-item.active {
            background: #2563eb;
            color: white;
          }
        }
        
        /* Mobile Bottom Navigation */
        .mobile-nav {
          display: flex;
          position: fixed;
          bottom: 0;
          left: 0;
          right: 0;
          background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
          padding: 6px 4px;
          padding-bottom: calc(6px + env(safe-area-inset-bottom, 0px));
          z-index: 1000;
          justify-content: space-around;
          box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.2);
        }
        
        @media (min-width: 768px) {
          .mobile-nav {
            display: none;
          }
        }
        
        .mobile-nav-item {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 8px 12px;
          border-radius: 12px;
          color: rgba(255, 255, 255, 0.6);
          font-size: 10px;
          background: none;
          border: none;
          cursor: pointer;
          transition: all 0.2s;
          min-width: 60px;
        }
        
        .mobile-nav-item:hover,
        .mobile-nav-item.active {
          color: white;
          background: rgba(255, 255, 255, 0.1);
        }
        
        .mobile-nav-item.active {
          background: #2563eb;
        }
        
        .mobile-nav-icon {
          font-size: 22px;
          margin-bottom: 4px;
        }
        
        .mobile-nav-label {
          font-weight: 500;
        }
        
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
        }
        
        .mobile-menu-item:hover,
        .mobile-menu-item.active {
          background: #2563eb;
          color: white;
        }
        
        /* Mobile Submenu styles */
        .mobile-menu-submenu-header {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 6px;
          padding: 16px 8px;
          border-radius: 12px;
          background: #1e293b;
          color: white;
          font-size: 12px;
          text-align: center;
          font-weight: 600;
          grid-column: span 3;
        }
        
        .mobile-submenu-child {
          background: #e2e8f0;
        }
        
        /* Content Padding for Mobile Nav */
        .content {
          padding-bottom: 90px;
        }
        
        @media (min-width: 768px) {
          .content {
            padding-bottom: 24px;
            margin-left: 220px;
          }
        }
      `}</style>
      
      {/* Chat Intelligente AI */}
      <ChatIntelligente />
    </div>
    </UploadProvider>
  );
}

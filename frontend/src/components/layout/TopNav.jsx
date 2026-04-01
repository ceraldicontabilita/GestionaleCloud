import React, { useState, useRef, useCallback } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Calendar, ChevronDown } from 'lucide-react';
import { AnnoSelector } from '../../contexts/AnnoContext';
import NotificationBell from '../NotificationBell';
import { AgentiPanel } from '../AgentiPanel';

// Navigazione principale - link diretti (no dropdown tranne "Altro")
const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: '⊞' },
  { to: '/fatture-ricevute', label: 'Fatture', icon: '🧾', badge: '180' },
  { to: '/prima-nota', label: 'Prima Nota', icon: '📒' },
  { to: '/riconciliazione', label: 'Banca', icon: '🏦', dot: true },
  { to: '/fisco', label: 'Fisco', icon: '📋' },
  { to: '/fornitori', label: 'Fornitori', icon: '🏢' },
  { to: '/dipendenti', label: 'HR', icon: '👥' },
];

// Solo "Altro" ha dropdown perché ha molti items
const ALTRO_ITEMS = [
  { to: '/bilancio', label: 'Bilancio' },
  { to: '/mutui', label: 'Mutui' },
  { to: '/contabilita-hub', label: 'Contabilità' },
  { to: '/magazzino', label: 'Magazzino' },
  { to: '/cucina', label: 'Cucina' },
  { to: '/scadenze', label: 'Scadenze' },
  { to: '/todo', label: 'To-Do' },
  { to: '/import-documenti', label: 'Import Documenti' },
  { to: '/documenti', label: 'Documenti' },
  { to: '/learning-machine', label: 'Learning Machine' },
  { to: '/strumenti', label: 'Strumenti' },
  { to: '/integrazioni', label: 'Integrazioni' },
  { to: '/ricettario',       label: 'Ricettario' },
  { to: '/food-cost',        label: 'Food Cost' },
  { to: '/catalogo-ordini',  label: 'Catalogo Ordini' },
  { to: '/prodotti-vendita', label: 'Prodotti Vendita' },
  { to: '/ciclo-passivo/import', label: '📥 Import Fatture' },
  { to: '/admin', label: 'Admin' },
  { to: '/mappa-gestionale', label: 'Come Funziona' },
];

export default function TopNav() {
  const location = useLocation();
  const [showAltro, setShowAltro] = useState(false);
  const closeTimeoutRef = useRef(null);
  
  // Check if current path is in "Altro" section
  const isAltroActive = ALTRO_ITEMS.some(item => 
    location.pathname === item.to || location.pathname.startsWith(item.to)
  );

  // Apre immediatamente, chiude con ritardo di 200ms
  const handleMouseEnter = useCallback(() => {
    if (closeTimeoutRef.current) {
      clearTimeout(closeTimeoutRef.current);
      closeTimeoutRef.current = null;
    }
    setShowAltro(true);
  }, []);

  const handleMouseLeave = useCallback(() => {
    closeTimeoutRef.current = setTimeout(() => {
      setShowAltro(false);
    }, 200); // 200ms di ritardo prima di chiudere
  }, []);

  return (
    <nav className="topnav-primary" data-testid="topnav-primary">
      {/* Brand */}
      <div className="topnav-brand">
        <div className="brand-square">CG</div>
        <span className="brand-name">Ceraldi ERP</span>
      </div>

      {/* Navigation Items - Link diretti */}
      <div className="topnav-items">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => `topnav-item ${isActive ? 'active' : ''}`}
            data-testid={`nav-${item.label.toLowerCase()}`}
          >
            <span className="topnav-icon">{item.icon}</span>
            <span className="topnav-label">{item.label}</span>
            {item.badge && <span className="topnav-badge">{item.badge}</span>}
            {item.dot && <span className="topnav-dot" />}
          </NavLink>
        ))}
        
        {/* Solo "Altro" ha dropdown con ritardo sul close */}
        <div 
          className={`topnav-dropdown ${isAltroActive ? 'active' : ''}`}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
        >
          <button className={`topnav-item ${isAltroActive ? 'active' : ''}`}>
            <span className="topnav-icon">⋯</span>
            <span className="topnav-label">Altro</span>
            <ChevronDown size={12} className="topnav-arrow" />
          </button>
          {showAltro && (
            <div className="topnav-dropdown-menu topnav-dropdown-grid">
              {ALTRO_ITEMS.map((item) => (
                <NavLink 
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => `topnav-dropdown-item ${isActive ? 'active' : ''}`}
                  onClick={() => setShowAltro(false)}
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right Side - Utilities */}
      <div className="topnav-right">
        {/* Anno Selector - MOLTO VISIBILE */}
        <div className="topnav-anno" data-testid="anno-selector" style={{
          display: 'flex',
          alignItems: 'center',
          background: '#dc2626',
          borderRadius: 8,
          padding: '6px 14px',
          gap: 8,
          boxShadow: '0 2px 8px rgba(220, 38, 38, 0.3)'
        }}>
          <span style={{ 
            fontSize: 12, 
            fontWeight: 800, 
            color: 'white',
            textTransform: 'uppercase',
            letterSpacing: 0.5
          }}>📅</span>
          <AnnoSelector style={{ 
            background: 'white',
            border: 'none',
            borderRadius: 6,
            padding: '5px 12px',
            fontSize: 16,
            fontWeight: 800,
            color: '#dc2626',
            minWidth: 75,
            cursor: 'pointer',
            textAlign: 'center'
          }} />
        </div>
        
        <NotificationBell />
        
        <AgentiPanel />
        
        <button className="topnav-icon-btn" title="Calendario">
          <Calendar size={15} />
        </button>
        
        <div className="topnav-user">
          <div className="topnav-avatar">CG</div>
          <div className="topnav-user-info">
            <div className="topnav-user-name">Ceraldi</div>
            <div className="topnav-user-role">Admin</div>
          </div>
        </div>
      </div>
    </nav>
  );
}

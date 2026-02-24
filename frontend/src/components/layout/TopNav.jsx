import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Calendar, ChevronDown } from 'lucide-react';
import { AnnoSelector } from '../../contexts/AnnoContext';
import NotificationBell from '../NotificationBell';

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
  { to: '/strumenti', label: 'Strumenti' },
  { to: '/integrazioni', label: 'Integrazioni' },
  { to: '/admin', label: 'Admin' },
];

export default function TopNav() {
  const location = useLocation();
  const [showAltro, setShowAltro] = React.useState(false);
  
  // Check if current path is in "Altro" section
  const isAltroActive = ALTRO_ITEMS.some(item => 
    location.pathname === item.to || location.pathname.startsWith(item.to)
  );

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
        
        {/* Solo "Altro" ha dropdown */}
        <div 
          className={`topnav-dropdown ${isAltroActive ? 'active' : ''}`}
          onMouseEnter={() => setShowAltro(true)}
          onMouseLeave={() => setShowAltro(false)}
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
        {/* Anno Selector con etichetta */}
        <div className="topnav-anno" data-testid="anno-selector">
          <span style={{ 
            fontSize: 11, 
            fontWeight: 600, 
            color: '#64748b',
            marginRight: 6,
            textTransform: 'uppercase',
            letterSpacing: 0.5
          }}>Anno</span>
          <AnnoSelector style={{ 
            background: 'white',
            border: '1.5px solid #b3d2f5',
            borderRadius: 7,
            padding: '4px 12px',
            fontSize: 13,
            fontWeight: 700,
            color: '#1a40b5',
            minHeight: 32,
            cursor: 'pointer',
          }} />
        </div>
        
        <NotificationBell />
        
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

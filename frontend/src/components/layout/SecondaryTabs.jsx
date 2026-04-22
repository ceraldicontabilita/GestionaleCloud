import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';

// Context-sensitive secondary tabs based on current route
const TAB_CONFIGS = {
  '/': [{ to: '/', label: 'Riepilogo', exact: true }],
  '/fatture': [
    { to: '/fatture', label: 'Fatture Ricevute', exact: true },
    { to: '/fatture/corrispettivi', label: 'Corrispettivi' },
  ],
  '/riconciliazione': [
    { to: '/riconciliazione', label: 'Riconciliazione', exact: true },
    { to: '/archivio-bonifici', label: 'Bonifici' },
    { to: '/gestione-assegni', label: 'Assegni' },
  ],
  '/dipendenti': [
    { to: '/dipendenti', label: 'Dipendenti', exact: true },
    { to: '/cedolini', label: 'Cedolini' },
    { to: '/presenze', label: 'Presenze' },
    { to: '/tfr', label: 'TFR' },
  ],
};

export default function SecondaryTabs() {
  const location = useLocation();

  // Find matching tabs for current route
  const getTabsForRoute = () => {
    const path = location.pathname;

    // Check for exact match first
    if (TAB_CONFIGS[path]) return TAB_CONFIGS[path];

    // Check for prefix matches
    for (const [prefix, tabs] of Object.entries(TAB_CONFIGS)) {
      if (prefix !== '/' && path.startsWith(prefix)) {
        return tabs;
      }
    }

    // Check specific route patterns
    if (path.startsWith('/fatture-ricevute') || path.startsWith('/corrispettivi')) {
      return TAB_CONFIGS['/fatture'];
    }
    if (
      path.startsWith('/cedolini') ||
      path.startsWith('/presenze') ||
      path.startsWith('/attendance') ||
      path.startsWith('/tfr')
    ) {
      return TAB_CONFIGS['/dipendenti'];
    }
    if (path.startsWith('/archivio-bonifici') || path.startsWith('/gestione-assegni')) {
      return TAB_CONFIGS['/riconciliazione'];
    }

    return null;
  };

  const tabs = getTabsForRoute();

  // Don't render if no secondary tabs for this route
  if (!tabs || tabs.length === 0) return null;

  return (
    <nav className="secondary-tabs" data-testid="secondary-tabs">
      {tabs.map((tab, idx) => (
        <React.Fragment key={tab.to}>
          <NavLink
            to={tab.to}
            end={tab.exact}
            className={({ isActive }) => `secondary-tab ${isActive ? 'on' : ''}`}
          >
            {tab.label}
          </NavLink>
          {idx < tabs.length - 1 && idx % 3 === 2 && <div className="tab-sep" />}
        </React.Fragment>
      ))}
    </nav>
  );
}

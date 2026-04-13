import React, { useState, useRef, useCallback, memo, useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, FileText, BookOpen, Building2,
  Users, FlaskConical, ChevronDown,
  Bell, Calendar, Warehouse,
  Settings, Wrench, FileBarChart, BookMarked, Car, Download
} from 'lucide-react';
import { AnnoSelector } from '../../contexts/AnnoContext';
import { COLORS } from '../../lib/utils';

/* ─── Costanti navigazione (definite fuori dal componente → nessuna ricreazione) ─── */
const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', Icon: LayoutDashboard },
  { to: '/fatture', label: 'Fatture', Icon: FileText },
  { to: '/prima-nota', label: 'Prima Nota', Icon: BookOpen },
  { to: '/fornitori', label: 'Fornitori', Icon: Building2 },
  { to: '/dipendenti', label: 'HR', Icon: Users },
  { to: null, href: 'https://www.ceraldiapp.it', label: 'Tracciabilità', Icon: FlaskConical, external: true },
  { to: '/riconciliazione/assegni', label: 'Assegni', Icon: FileBarChart },
];

const ALTRO_ITEMS = [
  { to: '/contabilita', label: 'Contabilità', Icon: FileBarChart },
  { to: '/magazzino', label: 'Magazzino', Icon: Warehouse },
  { to: '/documenti', label: 'Documenti', Icon: BookMarked },
  { to: '/noleggio', label: 'Noleggio Auto', Icon: Car },
  { to: '/riconciliazione', label: 'Riconciliazione', Icon: FileBarChart },
  { to: '/gestione-email', label: 'Email', Icon: Settings },
  { to: '/strumenti', label: 'Strumenti', Icon: Wrench },
  { to: '/admin', label: 'Admin', Icon: Settings },
];

/* ─── Stili (definiti fuori → creati una volta sola) ─── */
const S = {
  nav: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    height: 56,
    zIndex: 1000,
    display: 'flex',
    alignItems: 'center',
    background: '#1e3a5f',
    boxShadow: '0 2px 8px rgba(0,0,0,0.18)',
    padding: '0 12px',
    gap: 0,
    overflow: 'hidden',
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    marginRight: 16,
    flexShrink: 0,
    textDecoration: 'none',
  },
  brandSquare: {
    width: 32,
    height: 32,
    background: 'rgba(255,255,255,0.15)',
    border: '1px solid rgba(255,255,255,0.3)',
    borderRadius: 8,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: 800,
    fontSize: 13,
    color: '#fff',
    letterSpacing: 0.5,
  },
  brandName: {
    color: '#fff',
    fontWeight: 700,
    fontSize: 14,
    letterSpacing: 0.3,
    whiteSpace: 'nowrap',
  },
  items: {
    display: 'flex',
    alignItems: 'center',
    flex: 1,
    gap: 1,
    overflowX: 'auto',
    scrollbarWidth: 'none',
  },
  navItem: (isActive) => ({
    display: 'flex',
    alignItems: 'center',
    gap: 5,
    padding: '6px 10px',
    borderRadius: 8,
    background: isActive ? 'rgba(255,255,255,0.18)' : 'transparent',
    color: isActive ? '#fff' : 'rgba(255,255,255,0.78)',
    fontWeight: isActive ? 700 : 500,
    fontSize: 13,
    textDecoration: 'none',
    whiteSpace: 'nowrap',
    transition: 'background 0.15s, color 0.15s',
    cursor: 'pointer',
    border: 'none',
    flexShrink: 0,
  }),
  dropdownWrap: {
    position: 'relative',
    flexShrink: 0,
  },
  dropdownMenu: {
    position: 'absolute',
    top: 'calc(100% + 8px)',
    left: 0,
    background: '#fff',
    borderRadius: 10,
    boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
    minWidth: 180,
    padding: '6px 0',
    zIndex: 2000,
    animation: 'navDropIn 0.15s ease',
  },
  dropItem: (isActive) => ({
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '9px 16px',
    color: isActive ? COLORS.primary : '#374151',
    fontWeight: isActive ? 700 : 500,
    fontSize: 13,
    background: isActive ? '#f0f4ff' : 'transparent',
    textDecoration: 'none',
    transition: 'background 0.12s',
    cursor: 'pointer',
  }),
  right: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    marginLeft: 'auto',
    flexShrink: 0,
  },
  annoWrap: {
    display: 'flex',
    alignItems: 'center',
    background: 'rgba(255,255,255,0.12)',
    borderRadius: 8,
    padding: '4px 10px',
    gap: 6,
    border: '1px solid rgba(255,255,255,0.2)',
  },
  annoLabel: {
    fontSize: 11,
    fontWeight: 700,
    color: 'rgba(255,255,255,0.8)',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: '50%',
    background: 'rgba(255,255,255,0.15)',
    border: '1px solid rgba(255,255,255,0.3)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: 800,
    fontSize: 12,
    color: '#fff',
    flexShrink: 0,
  },
};

/* ─── Dropdown "Altro" — memoizzato separatamente per evitare re-render del nav ─── */
const AltroDropdown = memo(function AltroDropdown({ isAltroActive }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  // Chiudi se si clicca fuori
  useEffect(() => {
    if (!open) return;
    const handle = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, [open]);

  return (
    <div ref={wrapRef} style={S.dropdownWrap}>
      <button
        style={S.navItem(isAltroActive || open)}
        data-testid="nav-altro-btn"
        aria-expanded={open}
        onClick={() => setOpen(v => !v)}
      >
        <span style={{ fontSize: 13 }}>···</span>
        <span>Altro</span>
        <ChevronDown size={11} style={{ opacity: 0.7, marginLeft: 1, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
      </button>
      {open && (
        <div style={S.dropdownMenu} data-testid="nav-altro-menu">
          {ALTRO_ITEMS.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              style={({ isActive }) => S.dropItem(isActive)}
              onClick={() => setOpen(false)}
              data-testid={`nav-altro-${label.toLowerCase()}`}
            >
              <Icon size={14} />
              {label}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
});

/* ─── TopNav principale — React.memo per evitare re-render da parent ─── */
const TopNav = memo(function TopNav() {
  const location = useLocation();

  const isAltroActive = ALTRO_ITEMS.some(
    (item) => item.to && (location.pathname === item.to || location.pathname.startsWith(item.to + '/'))
  );

  return (
    <>
      {/* Stile globale per animazione dropdown — iniettato UNA volta */}
      <style>{`
        @keyframes navDropIn {
          from { opacity: 0; transform: translateY(-6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .topnav-link:hover {
          background: rgba(255,255,255,0.12) !important;
          color: #fff !important;
        }
        .topnav-drop-item:hover {
          background: #f0f4ff !important;
        }
        /* scrollbar nascosta nella barra nav */
        .topnav-items-scroll::-webkit-scrollbar { display: none; }
      `}</style>

      <nav style={S.nav} data-testid="topnav-primary">

        {/* Brand */}
        <NavLink to="/" style={S.brand} data-testid="nav-brand">
          <div style={S.brandSquare}>CG</div>
          <span style={S.brandName}>Ceraldi ERP</span>
        </NavLink>

        {/* Link principali */}
        <div style={S.items} className="topnav-items-scroll">
          {NAV_ITEMS.map(({ to, href, label, Icon, external }) =>
            external ? (
              /* Link esterno (es. Tracciabilità → ceraldiapp.it) */
              <a
                key={label}
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                style={S.navItem(false)}
                className="topnav-link"
                data-testid={`nav-${label.toLowerCase().replace(/\s+/g, '-')}`}
              >
                <Icon size={14} />
                <span>{label}</span>
              </a>
            ) : (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                style={({ isActive }) => S.navItem(isActive)}
                className="topnav-link"
                data-testid={`nav-${label.toLowerCase().replace(/\s+/g, '-')}`}
              >
                <Icon size={14} />
                <span>{label}</span>
              </NavLink>
            )
          )}
        </div>

        {/* Dropdown "Altro" — FUORI dal container overflow per non essere clippato */}
        <AltroDropdown isAltroActive={isAltroActive} />

        {/* Destra: Anno + Notifiche + Avatar */}
        <div style={S.right}>
          {/* Selettore Anno */}
          <div style={S.annoWrap} data-testid="anno-selector">
            <span style={S.annoLabel}>ANNO</span>
            <AnnoSelector style={{
              background: 'rgba(255,255,255,0.15)',
              border: '1px solid rgba(255,255,255,0.4)',
              borderRadius: 6,
              color: '#fff',
              fontWeight: 700,
              fontSize: 16,
              cursor: 'pointer',
              padding: '4px 8px',
              outline: 'none',
              minWidth: 70,
            }} />
          </div>

          {/* Campana notifiche */}
          <NotificationBellMinimal />

          {/* Avatar utente */}
          <div style={S.avatar} title="Ceraldi Group Admin">CG</div>
        </div>
      </nav>

      {/* Spacer per compensare la navbar fixed */}
      <div style={{ height: 56 }} />
    </>
  );
});

export default TopNav;

/* ─── Campana notifiche minimale (senza polling) ─── */
const NotificationBellMinimal = memo(function NotificationBellMinimal() {
  const [count, setCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const hasFetched = useRef(false);

  // Fetch solo la prima volta che si apre, non ad ogni render
  const handleOpen = useCallback(async () => {
    setOpen((prev) => {
      const next = !prev;
      if (next && !hasFetched.current) {
        hasFetched.current = true;
        import('../../api').then(({ default: api }) => {
          api.get('/api/alerts/lista?limit=15')
            .then(r => {
              setAlerts(r.data.alerts || []);
              setCount(r.data.stats?.non_letti || 0);
            })
            .catch(() => {});
        });
      }
      return next;
    });
  }, []);

  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={handleOpen}
        style={{
          position: 'relative',
          width: 34,
          height: 34,
          borderRadius: 8,
          background: 'rgba(255,255,255,0.1)',
          border: '1px solid rgba(255,255,255,0.2)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          color: 'rgba(255,255,255,0.85)',
          transition: 'background 0.15s',
        }}
        title="Notifiche"
        data-testid="notification-bell-btn"
      >
        <Bell size={15} />
        {count > 0 && (
          <span style={{
            position: 'absolute',
            top: 4,
            right: 4,
            width: 7,
            height: 7,
            background: '#ef4444',
            borderRadius: '50%',
            border: '1px solid #1e3a5f',
          }} />
        )}
      </button>

      {open && (
        <div style={{
          position: 'absolute',
          top: 'calc(100% + 8px)',
          right: 0,
          width: 300,
          background: '#fff',
          borderRadius: 10,
          boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
          zIndex: 2000,
          overflow: 'hidden',
          animation: 'navDropIn 0.15s ease',
        }} data-testid="notification-dropdown">
          <div style={{ padding: '12px 16px', borderBottom: '1px solid #f3f4f6', fontWeight: 700, fontSize: 13, color: COLORS.primary }}>
            Notifiche {count > 0 && <span style={{ color: '#ef4444' }}>({count})</span>}
          </div>
          <div style={{ maxHeight: 320, overflowY: 'auto' }}>
            {alerts.length === 0 ? (
              <div style={{ padding: 20, textAlign: 'center', color: '#9ca3af', fontSize: 13 }}>
                Nessuna notifica
              </div>
            ) : alerts.slice(0, 8).map((a, i) => (
              <div key={a.id || i} style={{
                padding: '10px 16px',
                borderBottom: '1px solid #f9fafb',
                fontSize: 12,
                color: a.letto ? '#9ca3af' : '#374151',
                fontWeight: a.letto ? 400 : 600,
              }}>
                {a.titolo || a.messaggio || 'Notifica'}
              </div>
            ))}
          </div>
          <button
            onClick={() => setOpen(false)}
            style={{ width: '100%', padding: '10px', background: '#f9fafb', border: 'none', cursor: 'pointer', fontSize: 12, color: '#6b7280', borderTop: '1px solid #f3f4f6' }}
          >
            Chiudi
          </button>
        </div>
      )}
    </div>
  );
});

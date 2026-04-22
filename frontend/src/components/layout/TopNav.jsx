import React, { useState, useRef, useCallback, memo, useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  FileText,
  BookOpen,
  Building2,
  Users,
  FlaskConical,
  ChevronDown,
  Bell,
  Calendar,
  Warehouse,
  Settings,
  Wrench,
  FileBarChart,
  BookMarked,
  Car,
  Download,
  CreditCard,
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
  {
    to: null,
    href: 'https://www.ceraldiapp.it',
    label: 'Tracciabilità',
    Icon: FlaskConical,
    external: true,
  },
  { to: '/riconciliazione/assegni', label: 'Assegni', Icon: FileBarChart },
];

const ALTRO_ITEMS = [
  { to: '/contabilita', label: 'Contabilità', Icon: FileBarChart },
  { to: '/magazzino', label: 'Magazzino', Icon: Warehouse },
  { to: '/documenti', label: 'Documenti', Icon: BookMarked },
  { to: '/noleggio', label: 'Noleggio Auto', Icon: Car },
  { to: '/riconciliazione', label: 'Riconciliazione', Icon: FileBarChart },
  { to: '/riconciliazione/paypal', label: 'PayPal', Icon: CreditCard },
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
    height: 54,
    zIndex: 1000,
    display: 'flex',
    alignItems: 'center',
    background: COLORS.primary,
    boxShadow: '0 2px 8px rgba(15,39,68,0.18)',
    padding: '0 16px',
    gap: 0,
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
    alignItems: 'center',
    flex: 1,
    gap: 1,
    overflowX: 'auto',
    scrollbarWidth: 'none',
  },
  navItem: isActive => ({
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
    position: 'fixed',
    top: 54,
    right: 'auto',
    background: '#fff',
    borderRadius: 10,
    boxShadow: '0 12px 32px rgba(15,39,68,0.18)',
    minWidth: 200,
    padding: '6px 0',
    zIndex: 2000,
    animation: 'navDropIn 0.15s ease',
    border: '1px solid #e2e8f0',
  },
  dropItem: isActive => ({
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
    const handle = e => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
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
        <ChevronDown
          size={11}
          style={{
            opacity: 0.7,
            marginLeft: 1,
            transform: open ? 'rotate(180deg)' : 'none',
            transition: 'transform 0.2s',
          }}
        />
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
    item =>
      item.to && (location.pathname === item.to || location.pathname.startsWith(item.to + '/'))
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
        <div style={S.items} className="topnav-items-scroll topnav-items">
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
          {/* Dropdown "Altro" — ultimo item nella nav */}
          <AltroDropdown isAltroActive={isAltroActive} />
        </div>

        {/* Destra: Anno + Notifiche + Avatar */}
        <div style={S.right} className="topnav-right">
          {/* Selettore Anno */}
          <div style={S.annoWrap} data-testid="anno-selector">
            <span style={S.annoLabel}>ANNO</span>
            <AnnoSelector
              style={{
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
              }}
            />
          </div>

          {/* Campana notifiche */}
          <NotificationBellMinimal />

          {/* Avatar utente */}
          <div style={S.avatar} title="Ceraldi Group Admin">
            CG
          </div>
        </div>
      </nav>

      {/* Spacer per compensare la navbar fixed */}
      <div style={{ height: 54 }} />
    </>
  );
});

export default TopNav;

/* ─── Campana notifiche — usa /api/alerts/summary (sistema relazionale) ─── */
const NotificationBellMinimal = memo(function NotificationBellMinimal() {
  const [summary, setSummary] = useState({
    totale_aperti: 0,
    per_severita: { critical: 0, warning: 0, info: 0 },
    critical_recenti: [],
    per_modulo: {},
  });
  const [open, setOpen] = useState(false);

  const fetchSummary = useCallback(async () => {
    try {
      const { default: api } = await import('../../api');
      const r = await api.get('/api/alerts/summary');
      setSummary(
        r.data || { totale_aperti: 0, per_severita: {}, critical_recenti: [], per_modulo: {} }
      );
    } catch (e) {
      // Silenzioso: se non autenticati il badge resta a 0
    }
  }, []);

  // Polling ogni 60s + fetch iniziale
  useEffect(() => {
    fetchSummary();
    const interval = setInterval(fetchSummary, 60000);
    return () => clearInterval(interval);
  }, [fetchSummary]);

  const handleOpen = useCallback(() => {
    setOpen(prev => !prev);
    // Refresh immediato all'apertura
    if (!open) fetchSummary();
  }, [open, fetchSummary]);

  const critical = summary.per_severita?.critical || 0;
  const warning = summary.per_severita?.warning || 0;
  const totale = summary.totale_aperti || 0;
  const hasAlerts = totale > 0;

  // Colore del pallino badge: rosso se ci sono critical, arancione se solo warning, blu se solo info
  const badgeColor = critical > 0 ? '#ef4444' : warning > 0 ? '#f59e0b' : '#3b82f6';

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
        title={hasAlerts ? `${totale} alert aperti` : 'Nessun alert'}
        data-testid="notification-bell-btn"
      >
        <Bell size={15} />
        {hasAlerts && (
          <span
            style={{
              position: 'absolute',
              top: -4,
              right: -4,
              minWidth: 16,
              height: 16,
              padding: '0 4px',
              background: badgeColor,
              color: '#fff',
              fontSize: 10,
              fontWeight: 700,
              borderRadius: 8,
              border: '1px solid #1e3a5f',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              lineHeight: 1,
            }}
          >
            {totale > 99 ? '99+' : totale}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 8px)',
            right: 0,
            width: 340,
            background: '#fff',
            borderRadius: 10,
            boxShadow: '0 12px 32px rgba(15,39,68,0.18)',
            border: '1px solid #e2e8f0',
            zIndex: 2000,
            overflow: 'hidden',
            animation: 'navDropIn 0.15s ease',
          }}
          data-testid="notification-dropdown"
        >
          <div
            style={{
              padding: '12px 16px',
              borderBottom: '1px solid #f3f4f6',
              fontWeight: 700,
              fontSize: 13,
              color: COLORS.primary,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span>Alert di sistema</span>
            {hasAlerts && (
              <span style={{ fontSize: 11, fontWeight: 600, color: '#64748b' }}>
                {critical > 0 && (
                  <span style={{ color: '#ef4444', marginRight: 6 }}>🔴 {critical}</span>
                )}
                {warning > 0 && (
                  <span style={{ color: '#f59e0b', marginRight: 6 }}>🟡 {warning}</span>
                )}
                {(summary.per_severita?.info || 0) > 0 && (
                  <span style={{ color: '#3b82f6' }}>🔵 {summary.per_severita.info}</span>
                )}
              </span>
            )}
          </div>

          <div style={{ maxHeight: 320, overflowY: 'auto' }}>
            {!hasAlerts ? (
              <div style={{ padding: 20, textAlign: 'center', color: '#9ca3af', fontSize: 13 }}>
                ✓ Nessun alert aperto
              </div>
            ) : summary.critical_recenti && summary.critical_recenti.length > 0 ? (
              <>
                <div
                  style={{
                    padding: '8px 16px',
                    background: '#fef2f2',
                    fontSize: 10,
                    fontWeight: 700,
                    color: '#b91c1c',
                    textTransform: 'uppercase',
                    letterSpacing: 0.5,
                  }}
                >
                  Alert critici recenti
                </div>
                {summary.critical_recenti.map((a, i) => (
                  <div
                    key={a.id || i}
                    style={{
                      padding: '10px 16px',
                      borderBottom: '1px solid #f9fafb',
                      fontSize: 12,
                      color: '#374151',
                    }}
                  >
                    <div style={{ fontWeight: 600, marginBottom: 2 }}>
                      {a.titolo || a.codice || 'Alert'}
                    </div>
                    {a.dettaglio && (
                      <div style={{ fontSize: 11, color: '#6b7280' }}>
                        {a.dettaglio.slice(0, 120)}
                      </div>
                    )}
                    {a.modulo && (
                      <div style={{ fontSize: 10, color: '#9ca3af', marginTop: 2 }}>{a.modulo}</div>
                    )}
                  </div>
                ))}
              </>
            ) : (
              <div style={{ padding: 16, fontSize: 12, color: '#6b7280' }}>
                {Object.entries(summary.per_modulo || {})
                  .slice(0, 8)
                  .map(([modulo, count]) => (
                    <div
                      key={modulo}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        padding: '6px 0',
                        borderBottom: '1px solid #f9fafb',
                      }}
                    >
                      <span style={{ textTransform: 'capitalize' }}>{modulo}</span>
                      <span style={{ fontWeight: 700, color: COLORS.primary }}>{count}</span>
                    </div>
                  ))}
              </div>
            )}
          </div>

          <a
            href="/dashboard-relazionale"
            onClick={() => setOpen(false)}
            style={{
              display: 'block',
              width: '100%',
              padding: '10px',
              background: COLORS.primary,
              color: '#fff',
              border: 'none',
              cursor: 'pointer',
              fontSize: 12,
              fontWeight: 600,
              textAlign: 'center',
              textDecoration: 'none',
              borderTop: '1px solid #f3f4f6',
            }}
          >
            Apri Dashboard Relazionale →
          </a>
        </div>
      )}
    </div>
  );
});

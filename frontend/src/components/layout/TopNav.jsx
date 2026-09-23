import React, { useState, useRef, useCallback, memo, useEffect } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { Bell, LogOut } from 'lucide-react';
import { toast } from 'sonner';
import api from '../../api';
import { AnnoSelector } from '../../contexts/AnnoContext';
import { COLORS, SHADOWS, useIsMobile } from '../../lib/utils';
import InstallAppButton from '../InstallAppButton';
// Le sezioni non stanno piu' qui: le elenca tutte ColonnaNavigazione, a
// sinistra. Questa barra tiene marchio, anno, avvisi e uscita.
import { useAuth } from '../../contexts/AuthContext.jsx';

/* Stili (definiti fuori dal componente — creati una volta sola) */
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
    boxShadow: '0 2px 8px rgba(42, 51, 41,0.18)',
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
    background: 'rgba(255,255,255,0.92)',
    borderRadius: 8,
    padding: '4px 10px',
    gap: 6,
    border: '1px solid rgba(255,255,255,0.4)',
  },
  annoLabel: {
    fontSize: 11,
    fontWeight: 700,
    color: COLORS.textMuted,
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

/*     TopNav principale  React.memo per evitare re-render da parent     */
const TopNav = memo(function TopNav() {
  const isMobile = useIsMobile(768);

  return (
    <>
      {/* Animazione del pannello avvisi: iniettata una volta sola */}
      <style>{`
        @keyframes navDropIn {
          from { opacity: 0; transform: translateY(-6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <nav style={S.nav} data-testid="topnav-primary">
        {/* Brand */}
        <NavLink to="/" style={S.brand} data-testid="nav-brand">
          <div style={S.brandSquare}>CG</div>
          <span style={S.brandName}>Ceraldi ERP</span>
        </NavLink>

        {/* Destra: Anno + Notifiche + Avatar */}
        <div style={S.right} className="topnav-right">
          {/* Selettore Anno  label "ANNO" nascosta sotto 768px per fare spazio alle icone */}
          <div style={S.annoWrap} data-testid="anno-selector">
            {!isMobile && <span style={S.annoLabel}>ANNO</span>}
            <AnnoSelector
              style={{
                background: 'transparent',
                border: 'none',
                borderRadius: 6,
                color: COLORS.primaryLight,
                fontWeight: 700,
                fontSize: 16,
                cursor: 'pointer',
                padding: '4px 8px',
                outline: 'none',
                minWidth: isMobile ? 44 : 70,
              }}
            />
          </div>

          {/* Installa come app (PWA)  visibile solo se non già installata */}
          <InstallAppButton />

          {/* Campana notifiche */}
          <NotificationBellMinimal />

          {/* Avatar utente */}
          <div style={S.avatar} title="Ceraldi Group Admin">
            CG
          </div>

          {/* Esci */}
          <BottoneEsci />
        </div>
      </nav>

      {/* Spacer per compensare la navbar fixed */}
      <div style={{ height: 54 }} />
    </>
  );
});

export default TopNav;

/*     Esci  chiude la sessione e revoca il token lato server     */
const BottoneEsci = memo(function BottoneEsci() {
  const { logout, user } = useAuth();
  const isMobile = useIsMobile(768);
  const [inCorso, setInCorso] = useState(false);

  const esci = useCallback(async () => {
    setInCorso(true);
    try {
      await logout();
    } catch (e) {
      // logout() e' fail-closed: se il server non registra la revoca la
      // sessione locale resta viva di proposito, altrimenti dichiareremmo
      // chiuso un accesso che sul server e' ancora valido. Va detto.
      toast.error('Uscita non riuscita: la sessione e’ ancora aperta. Riprova.');
    } finally {
      setInCorso(false);
    }
  }, [logout]);

  return (
    <button
      onClick={esci}
      disabled={inCorso}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        height: 34,
        padding: isMobile ? '0 9px' : '0 12px',
        borderRadius: 8,
        background: 'rgba(255,255,255,0.1)',
        border: '1px solid rgba(255,255,255,0.2)',
        color: 'rgba(255,255,255,0.85)',
        fontSize: 13,
        fontWeight: 600,
        cursor: inCorso ? 'wait' : 'pointer',
        opacity: inCorso ? 0.6 : 1,
        flexShrink: 0,
      }}
      title={user?.email ? `Esci (${user.email})` : 'Esci'}
      data-testid="btn-logout"
    >
      <LogOut size={15} />
      {!isMobile && <span>{inCorso ? 'Esco…' : 'Esci'}</span>}
    </button>
  );
});

/*     Campana notifiche  usa /api/alerts/summary (sistema relazionale)     */
const NotificationBellMinimal = memo(function NotificationBellMinimal() {
  const [summary, setSummary] = useState({
    totale_aperti: 0,
    per_severita: { critical: 0, warning: 0, info: 0 },
    critical_recenti: [],
    per_modulo: {},
  });
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  // Chiudi se si clicca fuori (stesso pattern di AltroDropdown)
  useEffect(() => {
    if (!open) return;
    const handle = e => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, [open]);

  const fetchSummary = useCallback(async () => {
    try {
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
  const badgeColor = critical > 0 ? COLORS.danger : warning > 0 ? COLORS.warning : COLORS.info;

  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
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
              border: `1px solid ${COLORS.primaryLight}`,
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
            background: COLORS.card,
            borderRadius: 10,
            boxShadow: SHADOWS.xl,
            border: `1px solid ${COLORS.border}`,
            zIndex: 2000,
            overflow: 'hidden',
            animation: 'navDropIn 0.15s ease',
          }}
          data-testid="notification-dropdown"
        >
          <div
            style={{
              padding: '12px 16px',
              borderBottom: `1px solid ${COLORS.gray[100]}`,
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
              <span style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted }}>
                {critical > 0 && (
                  <Link to="/dashboard/alerts?severita=critical" onClick={() => setOpen(false)} style={{ color: COLORS.danger, marginRight: 6 }}>CRIT {critical}</Link>
                )}
                {warning > 0 && (
                  <Link to="/dashboard/alerts?severita=warning" onClick={() => setOpen(false)} style={{ color: COLORS.warning, marginRight: 6 }}>WARN {warning}</Link>
                )}
                {(summary.per_severita?.info || 0) > 0 && (
                  <Link to="/dashboard/alerts?severita=info" onClick={() => setOpen(false)} style={{ color: COLORS.info }}>INFO {summary.per_severita.info}</Link>
                )}
              </span>
            )}
          </div>

          <div style={{ maxHeight: 320, overflowY: 'auto' }}>
            {!hasAlerts ? (
              <div style={{ padding: 20, textAlign: 'center', color: COLORS.textSubtle, fontSize: 13 }}>
                Nessun alert aperto
              </div>
            ) : summary.critical_recenti && summary.critical_recenti.length > 0 ? (
              <>
                <div
                  style={{
                    padding: '8px 16px',
                    background: COLORS.dangerLight,
                    fontSize: 10,
                    fontWeight: 700,
                    color: COLORS.danger,
                    textTransform: 'uppercase',
                    letterSpacing: 0.5,
                  }}
                >
                  Alert critici recenti
                </div>
                {summary.critical_recenti.map((a, i) => (
                  <Link
                    key={a.id || i}
                    to={a.link || `/dashboard/alerts?id=${encodeURIComponent(a.id || '')}`}
                    onClick={() => setOpen(false)}
                    style={{
                      padding: '10px 16px',
                      borderBottom: `1px solid ${COLORS.gray[50]}`,
                      fontSize: 12,
                      color: COLORS.gray[700],
                      display: 'block',
                      textDecoration: 'none',
                    }}
                  >
                    <div style={{ fontWeight: 600, marginBottom: 2 }}>
                      {a.titolo || a.codice || 'Alert'}
                    </div>
                    {a.dettaglio && (
                      <div style={{ fontSize: 11, color: COLORS.textMuted }}>
                        {a.dettaglio.slice(0, 120)}
                      </div>
                    )}
                    {a.modulo && (
                      <div style={{ fontSize: 10, color: COLORS.textSubtle, marginTop: 2 }}>{a.modulo}</div>
                    )}
                  </Link>
                ))}
              </>
            ) : (
              <div style={{ padding: 16, fontSize: 12, color: COLORS.textMuted }}>
                {Object.entries(summary.per_modulo || {})
                  .slice(0, 8)
                  .map(([modulo, count]) => (
                    <Link
                      key={modulo}
                      to={`/dashboard/alerts?modulo=${encodeURIComponent(modulo)}`}
                      onClick={() => setOpen(false)}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        padding: '6px 0',
                        borderBottom: `1px solid ${COLORS.gray[50]}`,
                        textDecoration: 'none',
                      }}
                    >
                      <span style={{ textTransform: 'capitalize' }}>{modulo}</span>
                      <span style={{ fontWeight: 700, color: COLORS.primary }}>{count}</span>
                    </Link>
                  ))}
              </div>
            )}
          </div>

          <Link
            to="/dashboard/alerts"
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
              borderTop: `1px solid ${COLORS.gray[100]}`,
            }}
          >
            Apri tutti gli alert ({totale})
          </Link>
        </div>
      )}
    </div>
  );
});


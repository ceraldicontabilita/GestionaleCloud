/* Top navigation bar — recreation of frontend/src/components/layout/TopNav.jsx */
function TopNav({ active, onNavigate }) {
  const C = window.CeraldiERPDesignSystem_9a014a;
  const Icon = window.Icon;
  const [altroOpen, setAltroOpen] = React.useState(false);

  const items = [
    { key: 'dashboard', label: 'Dashboard', icon: 'layout-dashboard' },
    { key: 'fatture', label: 'Fatture', icon: 'file-text' },
    { key: 'prima-nota', label: 'Prima Nota', icon: 'book-open' },
    { key: 'fornitori', label: 'Fornitori', icon: 'building-2' },
    { key: 'dipendenti', label: 'HR', icon: 'users' },
    { key: 'corrispettivi', label: 'Corrispettivi', icon: 'receipt' },
    { key: 'assegni', label: 'Assegni', icon: 'file-bar-chart' },
  ];
  const altro = [
    { key: 'contabilita', label: 'Contabilità', icon: 'file-bar-chart' },
    { key: 'magazzino', label: 'Magazzino', icon: 'warehouse' },
    { key: 'documenti', label: 'Documenti', icon: 'bookmark' },
    { key: 'noleggio', label: 'Noleggio Auto', icon: 'car' },
    { key: 'riconciliazione', label: 'Riconciliazione', icon: 'file-bar-chart' },
    { key: 'strumenti', label: 'Strumenti', icon: 'wrench' },
    { key: 'admin', label: 'Admin', icon: 'settings' },
  ];

  const navItem = (isActive) => ({
    display: 'flex', alignItems: 'center', gap: 5, padding: '6px 10px',
    borderRadius: 8, background: isActive ? 'rgba(255,255,255,0.18)' : 'transparent',
    color: isActive ? '#fff' : 'rgba(255,255,255,0.78)',
    fontWeight: isActive ? 700 : 500, fontSize: 13, whiteSpace: 'nowrap',
    cursor: 'pointer', border: 'none', flexShrink: 0,
    transition: 'background 0.15s, color 0.15s', fontFamily: 'var(--font-ui)',
  });

  return (
    <nav style={{
      position: 'sticky', top: 0, zIndex: 100, height: 54, display: 'flex', alignItems: 'center',
      background: 'var(--c-primary)', boxShadow: 'var(--shadow-nav)', padding: '0 16px',
    }}>
      <div onClick={() => onNavigate('dashboard')} style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 16, flexShrink: 0, cursor: 'pointer' }}>
        <div style={{ width: 32, height: 32, background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.3)', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13, color: '#fff', letterSpacing: 0.5 }}>CG</div>
        <span style={{ color: '#fff', fontWeight: 700, fontSize: 14, letterSpacing: 0.3, whiteSpace: 'nowrap' }}>Ceraldi ERP</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', flex: 1, gap: 1, overflowX: 'auto', scrollbarWidth: 'none' }}>
        {items.map((it) => (
          <button key={it.key} style={navItem(active === it.key)} onClick={() => onNavigate(it.key)}>
            <Icon name={it.icon} size={14} /><span>{it.label}</span>
          </button>
        ))}
        <div style={{ position: 'relative', flexShrink: 0 }}>
          <button style={navItem(altroOpen)} onClick={() => setAltroOpen((v) => !v)}>
            <span style={{ fontSize: 13 }}>···</span><span>Altro</span>
            <Icon name="chevron-down" size={11} />
          </button>
          {altroOpen && (
            <div style={{ position: 'absolute', top: 42, left: 0, background: '#fff', borderRadius: 10, boxShadow: 'var(--shadow-xl)', minWidth: 200, padding: '6px 0', zIndex: 200, border: '1px solid var(--c-border)' }}>
              {altro.map((it) => (
                <div key={it.key} onClick={() => { onNavigate(it.key); setAltroOpen(false); }} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 16px', color: 'var(--c-text)', fontWeight: 500, fontSize: 13, cursor: 'pointer' }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = '#f0f4ff')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
                  <Icon name={it.icon} size={14} color="var(--c-primary)" />{it.label}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', background: 'rgba(255,255,255,0.12)', borderRadius: 8, padding: '4px 10px', gap: 6, border: '1px solid rgba(255,255,255,0.2)' }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: 'rgba(255,255,255,0.8)', textTransform: 'uppercase', letterSpacing: 0.5 }}>ANNO</span>
          <span style={{ color: '#fff', fontWeight: 700, fontSize: 16 }}>2026</span>
        </div>
        <button style={{ position: 'relative', width: 34, height: 34, borderRadius: 8, background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'rgba(255,255,255,0.85)' }}>
          <Icon name="bell" size={15} />
          <span style={{ position: 'absolute', top: -4, right: -4, minWidth: 16, height: 16, padding: '0 4px', background: '#ef4444', color: '#fff', fontSize: 10, fontWeight: 700, borderRadius: 8, border: '1px solid var(--c-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', lineHeight: 1 }}>5</span>
        </button>
        <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 12, color: '#fff' }}>CG</div>
      </div>
    </nav>
  );
}

window.TopNav = TopNav;

// Design System aggiornato per Ceraldi ERP
// Basato sullo screenshot fornito

export const COLORS_NEW = {
  // Primary Colors
  primary: '#2563eb',        // Blu brillante
  primaryDark: '#1e40af',
  primaryLight: '#3b82f6',
  
  // Sidebar
  sidebarBg: '#1e293b',      // Navy scuro
  sidebarText: '#94a3b8',
  sidebarActive: '#2563eb',
  
  // Background
  bgMain: '#f8fafc',
  bgCard: '#ffffff',
  
  // Text
  textPrimary: '#0f172a',
  textSecondary: '#64748b',
  textMuted: '#94a3b8',
  
  // Stats Cards
  statBlue: { bg: '#dbeafe', text: '#1e40af', icon: '#3b82f6' },
  statGreen: { bg: '#dcfce7', text: '#166534', icon: '#22c55e' },
  statYellow: { bg: '#fef3c7', text: '#b45309', icon: '#f59e0b' },
  statPurple: { bg: '#f3e8ff', text: '#6b21a8', icon: '#a855f7' },
  statRed: { bg: '#fee2e2', text: '#991b1b', icon: '#ef4444' },
  
  // Buttons
  btnPrimary: '#2563eb',
  btnSuccess: '#22c55e',
  btnDanger: '#ef4444',
  btnSecondary: '#64748b',
  
  // Borders
  border: '#e2e8f0',
  borderLight: '#f1f5f9'
};

export const STYLES_NEW = {
  // Page Container
  pageContainer: {
    minHeight: '100vh',
    background: COLORS_NEW.bgMain,
    paddingBottom: '80px'
  },
  
  // Page Header (Banner Grande Blu)
  pageHeader: {
    background: `linear-gradient(135deg, ${COLORS_NEW.primary} 0%, ${COLORS_NEW.primaryDark} 100%)`,
    padding: '32px 40px',
    color: 'white',
    boxShadow: '0 4px 12px rgba(37, 99, 235, 0.15)',
    marginBottom: '32px'
  },
  
  pageHeaderTitle: {
    fontSize: '32px',
    fontWeight: '700',
    margin: 0,
    marginBottom: '8px',
    display: 'flex',
    alignItems: 'center',
    gap: '16px'
  },
  
  pageHeaderSubtitle: {
    fontSize: '16px',
    opacity: 0.9,
    fontWeight: '400',
    marginBottom: '24px'
  },
  
  pageHeaderActions: {
    display: 'flex',
    gap: '12px',
    flexWrap: 'wrap'
  },
  
  // Content Container
  contentContainer: {
    maxWidth: '1400px',
    margin: '0 auto',
    padding: '0 40px'
  },
  
  // Stats Grid
  statsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
    gap: '24px',
    marginBottom: '32px'
  },
  
  // Stat Card
  statCard: {
    background: 'white',
    borderRadius: '16px',
    padding: '24px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
    transition: 'all 0.2s',
    cursor: 'pointer',
    border: '1px solid ' + COLORS_NEW.borderLight
  },
  
  statCardHover: {
    transform: 'translateY(-4px)',
    boxShadow: '0 8px 24px rgba(0,0,0,0.12)'
  },
  
  statCardIcon: {
    width: '56px',
    height: '56px',
    borderRadius: '12px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: '16px'
  },
  
  statCardValue: {
    fontSize: '40px',
    fontWeight: '700',
    marginBottom: '8px',
    lineHeight: '1'
  },
  
  statCardLabel: {
    fontSize: '14px',
    fontWeight: '500',
    opacity: 0.8,
  },
  
  // Buttons
  btnLarge: {
    padding: '14px 28px',
    fontSize: '16px',
    fontWeight: '600',
    borderRadius: '10px',
    border: 'none',
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '10px',
    transition: 'all 0.2s',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
  },
  
  btnPrimary: {
    background: COLORS_NEW.btnPrimary,
    color: 'white'
  },
  
  btnSuccess: {
    background: COLORS_NEW.btnSuccess,
    color: 'white'
  },
  
  btnWhite: {
    background: 'white',
    color: COLORS_NEW.primary,
    border: '2px solid rgba(255,255,255,0.3)'
  },
  
  // Tab Navigation
  tabNav: {
    display: 'flex',
    gap: '8px',
    marginBottom: '32px',
    borderBottom: '2px solid ' + COLORS_NEW.borderLight,
    paddingBottom: '0'
  },
  
  tab: {
    padding: '14px 24px',
    fontSize: '15px',
    fontWeight: '500',
    border: 'none',
    background: 'transparent',
    cursor: 'pointer',
    color: COLORS_NEW.textSecondary,
    borderBottom: '3px solid transparent',
    marginBottom: '-2px',
    transition: 'all 0.2s'
  },
  
  tabActive: {
    color: COLORS_NEW.primary,
    borderBottomColor: COLORS_NEW.primary,
    fontWeight: '600'
  },
  
  // Cards
  card: {
    background: 'white',
    borderRadius: '12px',
    padding: '24px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
    border: '1px solid ' + COLORS_NEW.borderLight
  },
  
  cardTitle: {
    fontSize: '18px',
    fontWeight: '600',
    color: COLORS_NEW.textPrimary,
    marginBottom: '16px',
    display: 'flex',
    alignItems: 'center',
    gap: '12px'
  }
};

// Helper function per creare stat card
export function createStatCard(config) {
  const { value, label, color = 'blue', icon: Icon, onClick } = config;
  const colorConfig = COLORS_NEW[`stat${color.charAt(0).toUpperCase() + color.slice(1)}`] || COLORS_NEW.statBlue;
  
  return {
    value,
    label,
    bg: colorConfig.bg,
    textColor: colorConfig.text,
    iconColor: colorConfig.icon,
    icon: Icon,
    onClick
  };
}

import { useState, useEffect } from 'react';

/**
 * Hook per gestire la responsività dell'applicazione
 * Breakpoints:
 * - mobile: < 640px (telefoni 6")
 * - tablet: 640px - 1024px (tablet 12")
 * - desktop: > 1024px
 */
export function useResponsive() {
  const [screen, setScreen] = useState({
    width: typeof window !== 'undefined' ? window.innerWidth : 1200,
    height: typeof window !== 'undefined' ? window.innerHeight : 800,
    isMobile: false,
    isTablet: false,
    isDesktop: true,
    device: 'desktop',
  });

  useEffect(() => {
    function handleResize() {
      const width = window.innerWidth;
      const isMobile = width < 640;
      const isTablet = width >= 640 && width < 1024;
      const isDesktop = width >= 1024;

      setScreen({
        width,
        height: window.innerHeight,
        isMobile,
        isTablet,
        isDesktop,
        device: isMobile ? 'mobile' : isTablet ? 'tablet' : 'desktop',
      });
    }

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return screen;
}

/**
 * Funzione per generare stili responsive
 * @param {object} styles - { mobile: {}, tablet: {}, desktop: {} }
 * @param {string} device - 'mobile' | 'tablet' | 'desktop'
 */
export function getResponsiveStyle(styles, device) {
  const base = styles.base || {};
  const deviceStyles = styles[device] || {};
  return { ...base, ...deviceStyles };
}

/**
 * Stili comuni responsive per l'app
 */
export const responsiveStyles = {
  // Container principale pagina
  pageContainer: {
    base: { minHeight: '100vh', background: '#f8fafc' },
    mobile: { padding: 12 },
    tablet: { padding: 16 },
    desktop: { padding: 24, maxWidth: 1600, margin: '0 auto' },
  },

  // Header pagina
  pageHeader: {
    base: { borderRadius: 12, color: 'white', marginBottom: 16 },
    mobile: { padding: '16px 12px' },
    tablet: { padding: '18px 20px' },
    desktop: { padding: '20px 24px', marginBottom: 24 },
  },

  // Titolo pagina
  pageTitle: {
    base: { margin: 0, fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 8 },
    mobile: { fontSize: 18 },
    tablet: { fontSize: 20 },
    desktop: { fontSize: 24 },
  },

  // Card
  card: {
    base: { background: 'white', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.08)' },
    mobile: { padding: 12, marginBottom: 12 },
    tablet: { padding: 16, marginBottom: 14 },
    desktop: { padding: 20, marginBottom: 16 },
  },

  // Griglia statistiche
  statsGrid: {
    base: { display: 'grid', gap: 12 },
    mobile: { gridTemplateColumns: 'repeat(2, 1fr)' },
    tablet: { gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 },
    desktop: { gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 },
  },

  // Griglia card
  cardGrid: {
    base: { display: 'grid', gap: 12 },
    mobile: { gridTemplateColumns: '1fr' },
    tablet: { gridTemplateColumns: 'repeat(2, 1fr)', gap: 14 },
    desktop: { gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 },
  },

  // Tabella container
  tableContainer: {
    base: { overflowX: 'auto', WebkitOverflowScrolling: 'touch' },
    mobile: { margin: '0 -12px', padding: '0 12px' },
    tablet: { margin: 0, padding: 0 },
    desktop: { margin: 0, padding: 0 },
  },

  // Tabella
  table: {
    base: { width: '100%', borderCollapse: 'collapse' },
    mobile: { fontSize: 11, minWidth: 600 },
    tablet: { fontSize: 12, minWidth: 'auto' },
    desktop: { fontSize: 14 },
  },

  // Cella tabella header
  th: {
    base: {
      textAlign: 'left',
      borderBottom: '2px solid #e5e7eb',
      background: '#f9fafb',
      fontWeight: 600,
    },
    mobile: { padding: '8px 6px' },
    tablet: { padding: '10px 12px' },
    desktop: { padding: '12px 16px' },
  },

  // Cella tabella body
  td: {
    base: { borderBottom: '1px solid #f3f4f6' },
    mobile: { padding: '8px 6px' },
    tablet: { padding: '10px 12px' },
    desktop: { padding: '12px 16px' },
  },

  // Bottone primario
  btnPrimary: {
    base: {
      border: 'none',
      borderRadius: 8,
      cursor: 'pointer',
      fontWeight: 'bold',
      color: 'white',
    },
    mobile: { padding: '8px 12px', fontSize: 12 },
    tablet: { padding: '9px 16px', fontSize: 13 },
    desktop: { padding: '10px 20px', fontSize: 14 },
  },

  // Bottone secondario
  btnSecondary: {
    base: {
      background: '#e5e7eb',
      color: '#374151',
      border: 'none',
      borderRadius: 8,
      cursor: 'pointer',
      fontWeight: '600',
    },
    mobile: { padding: '8px 12px', fontSize: 12 },
    tablet: { padding: '9px 16px', fontSize: 13 },
    desktop: { padding: '10px 20px', fontSize: 14 },
  },

  // Input
  input: {
    base: { borderRadius: 8, border: '2px solid #e5e7eb', width: '100%', boxSizing: 'border-box' },
    mobile: { padding: '8px 10px', fontSize: 14 },
    tablet: { padding: '9px 11px', fontSize: 14 },
    desktop: { padding: '10px 12px', fontSize: 14 },
  },

  // Select
  select: {
    base: { borderRadius: 8, border: '2px solid #e5e7eb', background: 'white', cursor: 'pointer' },
    mobile: { padding: '8px 10px', fontSize: 14 },
    tablet: { padding: '9px 11px', fontSize: 14 },
    desktop: { padding: '10px 12px', fontSize: 14 },
  },

  // Modal overlay
  modalOverlay: {
    base: {
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0,0,0,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
    },
    mobile: { padding: 12 },
    tablet: { padding: 20 },
    desktop: { padding: 24 },
  },

  // Modal content
  modalContent: {
    base: { background: 'white', borderRadius: 16, maxHeight: '90vh', overflow: 'auto' },
    mobile: { padding: 16, width: '100%', maxWidth: '100%' },
    tablet: { padding: 20, width: '90%', maxWidth: 500 },
    desktop: { padding: 24, width: '90%', maxWidth: 600 },
  },

  // Flex row responsive (diventa colonna su mobile)
  flexRow: {
    base: { display: 'flex', gap: 12 },
    mobile: { flexDirection: 'column' },
    tablet: { flexDirection: 'row', flexWrap: 'wrap' },
    desktop: { flexDirection: 'row' },
  },

  // Flex row che rimane row
  flexRowAlways: {
    base: { display: 'flex', alignItems: 'center' },
    mobile: { gap: 8 },
    tablet: { gap: 10 },
    desktop: { gap: 12 },
  },

  // Badge
  badge: {
    base: { borderRadius: 20, fontWeight: 600 },
    mobile: { padding: '3px 8px', fontSize: 10 },
    tablet: { padding: '3px 10px', fontSize: 11 },
    desktop: { padding: '4px 12px', fontSize: 12 },
  },

  // Testo label
  label: {
    base: { display: 'block', fontWeight: 500 },
    mobile: { marginBottom: 4, fontSize: 12 },
    tablet: { marginBottom: 5, fontSize: 13 },
    desktop: { marginBottom: 6, fontSize: 14 },
  },

  // Stat card value
  statValue: {
    base: { fontWeight: 'bold' },
    mobile: { fontSize: 22, margin: '6px 0 0 0' },
    tablet: { fontSize: 24, margin: '7px 0 0 0' },
    desktop: { fontSize: 28, margin: '8px 0 0 0' },
  },

  // Stat card label
  statLabel: {
    base: { margin: 0, color: '#6b7280', textTransform: 'uppercase' },
    mobile: { fontSize: 10 },
    tablet: { fontSize: 11 },
    desktop: { fontSize: 12 },
  },

  // Navigazione mese
  monthNav: {
    base: { display: 'flex', alignItems: 'center' },
    mobile: { gap: 8 },
    tablet: { gap: 10 },
    desktop: { gap: 12 },
  },

  // Testo mese
  monthText: {
    base: { fontWeight: 'bold', textAlign: 'center' },
    mobile: { minWidth: 120, fontSize: 14 },
    tablet: { minWidth: 140, fontSize: 15 },
    desktop: { minWidth: 160, fontSize: 16 },
  },

  // Sidebar nascosta su mobile
  sidebarVisible: {
    mobile: { display: 'none' },
    tablet: { display: 'block' },
    desktop: { display: 'block' },
  },

  // Header con actions
  headerActions: {
    base: { display: 'flex', alignItems: 'center', flexWrap: 'wrap' },
    mobile: { gap: 8, marginTop: 12 },
    tablet: { gap: 10 },
    desktop: { gap: 12 },
  },

  // Form grid 2 colonne
  formGrid2: {
    base: { display: 'grid', gap: 12 },
    mobile: { gridTemplateColumns: '1fr' },
    tablet: { gridTemplateColumns: 'repeat(2, 1fr)' },
    desktop: { gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 },
  },

  // Form grid 3 colonne
  formGrid3: {
    base: { display: 'grid', gap: 12 },
    mobile: { gridTemplateColumns: '1fr' },
    tablet: { gridTemplateColumns: 'repeat(2, 1fr)' },
    desktop: { gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 },
  },

  // Sezione filtri
  filterSection: {
    base: { display: 'flex', flexWrap: 'wrap', alignItems: 'center' },
    mobile: { gap: 8, flexDirection: 'column', alignItems: 'stretch' },
    tablet: { gap: 12, flexDirection: 'row' },
    desktop: { gap: 16, flexDirection: 'row' },
  },
};

/**
 * Hook semplificato per ottenere stili responsive
 */
export function useStyles() {
  const { device } = useResponsive();

  const getStyle = styleName => {
    const styleConfig = responsiveStyles[styleName];
    if (!styleConfig) return {};
    return getResponsiveStyle(styleConfig, device);
  };

  const mergeStyles = (...styleNames) => {
    return styleNames.reduce((acc, name) => {
      return { ...acc, ...getStyle(name) };
    }, {});
  };

  return { getStyle, mergeStyles, device };
}

export default useResponsive;

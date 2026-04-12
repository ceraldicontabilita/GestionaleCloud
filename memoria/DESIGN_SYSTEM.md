# Design System — Ceraldi ERP
> SOURCE OF TRUTH: `frontend/src/lib/utils.js` | Aggiornato: Aprile 2026

---

## REGOLA ASSOLUTA

**NO Tailwind, NO Shadcn** per le pagine gestionali.
Usare ESCLUSIVAMENTE le costanti da `lib/utils.js` con CSS inline.

---

## Costanti Disponibili

### COLORS
```js
import { COLORS } from '../../lib/utils';

COLORS.primary      = '#1e3a5f'   // Blu scuro principale
COLORS.primaryLight = '#2d5a87'   // Blu più chiaro
COLORS.success      = '#4caf50'   // Verde
COLORS.warning      = '#ff9800'   // Arancione
COLORS.danger       = '#ef4444'   // Rosso
COLORS.info         = '#2196f3'   // Blu info
COLORS.purple       = '#9c27b0'   // Viola
COLORS.gray         = '#6b7280'   // Grigio medio
COLORS.grayLight    = '#e5e7eb'   // Grigio chiaro
COLORS.grayBg       = '#f9fafb'   // Sfondo grigio
COLORS.white        = '#ffffff'
// Extra (usati nelle pagine HR)
COLORS.text         = '#1e293b'
COLORS.textMuted    = '#64748b'
COLORS.border       = '#e2e8f0'
```

### SPACING (numeri, usare con `px`)
```js
SPACING.xs  = 4
SPACING.sm  = 8
SPACING.md  = 12
SPACING.lg  = 16
SPACING.xl  = 20
SPACING.xxl = 24
```

### STYLES (oggetti stile pronti)
```js
STYLES.page    // { padding: 20, maxWidth: 1400, margin: '0 auto' }
STYLES.header  // { gradient #1e3a5f→#2d5a87, borderRadius: 12, color: white }
STYLES.card    // { background: white, borderRadius: 12, boxShadow, border }
STYLES.input   // { padding: '10px 12px', borderRadius: 8, border: '2px solid grayLight' }
STYLES.select  // uguale a input
STYLES.table   // { width: '100%', borderCollapse: 'collapse' }
STYLES.th      // { padding: '12px 16px', fontWeight: 600, background: grayBg }
STYLES.td      // { padding: '12px 16px', borderBottom: '1px solid grayLight' }
STYLES.btnPrimary    // bottone blu primario
STYLES.btnSecondary  // bottone grigio secondario
```

---

## Template Pagina Standard

```jsx
import { COLORS, STYLES, SPACING } from '../../lib/utils';
import { SomeIcon } from 'lucide-react';

export default function NuovaPagina() {
  return (
    <div style={{ padding: SPACING.xl, maxWidth: 1200 }}>
      
      {/* Header gradiente */}
      <div style={{ ...STYLES.header, marginBottom: SPACING.lg }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Titolo Pagina</h1>
          <p style={{ margin: '4px 0 0', opacity: 0.8, fontSize: 13 }}>Sottotitolo descrittivo</p>
        </div>
        <button style={{ ...STYLES.btnPrimary }}>Azione Principale</button>
      </div>

      {/* KPI Cards (griglia 4 colonne) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginBottom: 24 }}>
        {[{ label: 'Totale', value: 42, color: COLORS.primary }].map(k => (
          <div key={k.label} style={{ ...STYLES.card, padding: '16px 20px' }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase' }}>
              {k.label}
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, color: k.color || COLORS.text, marginTop: 6 }}>
              {k.value}
            </div>
          </div>
        ))}
      </div>

      {/* Tabella dati */}
      <div style={{ ...STYLES.card }}>
        <table style={STYLES.table}>
          <thead>
            <tr>
              <th style={STYLES.th}>Colonna A</th>
              <th style={STYLES.th}>Colonna B</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style={STYLES.td}>Valore</td>
              <td style={STYLES.td}>Valore</td>
            </tr>
          </tbody>
        </table>
      </div>

    </div>
  );
}
```

---

## Componenti UI Comuni

### Button Primary
```jsx
<button style={{
  padding: '8px 16px', border: 'none', borderRadius: 6,
  background: COLORS.primary, color: 'white',
  cursor: 'pointer', fontSize: 13, fontWeight: 600
}}>Testo</button>
```

### Button Secondary
```jsx
<button style={{
  padding: '8px 16px', border: `1px solid ${COLORS.border}`, borderRadius: 6,
  background: 'white', color: COLORS.text,
  cursor: 'pointer', fontSize: 13, fontWeight: 500
}}>Testo</button>
```

### Badge Stato
```jsx
<span style={{
  padding: '3px 10px', borderRadius: 99, fontSize: 11, fontWeight: 600,
  background: condizione ? '#dcfce7' : '#fef9c3',
  color: condizione ? '#16a34a' : '#a16207'
}}>
  {condizione ? 'Attivo' : 'In attesa'}
</span>
```

### Tab Navigation
```jsx
<div style={{ display: 'flex', borderBottom: `1px solid ${COLORS.border}` }}>
  {tabs.map(t => (
    <button key={t.id} onClick={() => setTab(t.id)} style={{
      padding: '12px 20px', background: 'none', border: 'none',
      borderBottom: tab === t.id ? `3px solid ${COLORS.primary}` : '3px solid transparent',
      color: tab === t.id ? COLORS.primary : COLORS.textMuted,
      fontWeight: tab === t.id ? 700 : 400,
      cursor: 'pointer', fontSize: 13,
    }}>{t.label}</button>
  ))}
</div>
```

### Loading Spinner
```jsx
<div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>
  <RefreshCw size={20} style={{ animation: 'spin 1s linear infinite' }} />
  <div style={{ marginTop: 8 }}>Caricamento…</div>
</div>
<style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
```

### Input con label
```jsx
<div style={{ marginBottom: SPACING.md }}>
  <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: COLORS.textMuted, marginBottom: 4 }}>
    Etichetta Campo
  </label>
  <input
    style={{ ...STYLES.input, width: '100%' }}
    placeholder="Placeholder..."
    value={value}
    onChange={e => setValue(e.target.value)}
  />
</div>
```

---

## Icone

- Libreria: **lucide-react** (già installata, NON aggiungere altre)
- **NO emoji nel codice sorgente** — usare sempre icone Lucide
- Import: `import { FileText, Download, RefreshCw, Mail, User } from 'lucide-react'`

---

## data-testid (obbligatori)

Ogni elemento interattivo o con dati critici DEVE avere `data-testid`:
```jsx
<button data-testid="btn-import-gmail">Importa da Gmail</button>
<select data-testid="select-anno-cedolini">...</select>
<div data-testid="import-result-banner">…</div>
<table data-testid="tabella-fornitori">…</table>
```

---

## Responsive Mobile

Regola: avvolgere le tabelle in un div con `overflowX: 'auto'` su mobile.

```jsx
import { useIsMobile } from '../../hooks/useIsMobile';

export default function PaginaConTabella() {
  const isMobile = useIsMobile();  // IMPORTANTE: ogni sub-componente che lo usa deve importarlo!
  
  return (
    <div style={{ overflowX: isMobile ? 'auto' : 'visible' }}>
      <table style={{ ...STYLES.table, minWidth: isMobile ? 480 : 'auto' }}>
        {/* ... */}
      </table>
    </div>
  );
}
```

> ⚠️ **Regola critica**: ogni sub-componente (definito fuori dall'export default) che usa `isMobile`
> DEVE avere il proprio `const isMobile = useIsMobile()` — non può ereditarlo dall'esterno.
> Violazione → ReferenceError → loop di reload.

---

## Hub Pattern (mount-once)

Per evitare reload continuo su cambio tab negli hub:

```jsx
const [activeTab, setActiveTab] = useState('prima-tab');
const [visitedTabs, setVisitedTabs] = useState(new Set(['prima-tab']));

const handleTabChange = (tab) => {
  setActiveTab(tab);
  setVisitedTabs(prev => new Set([...prev, tab]));
};

return (
  <>
    {visitedTabs.has('tab1') && (
      <div style={{ display: activeTab === 'tab1' ? 'block' : 'none' }}>
        <ComponenteTab1 />
      </div>
    )}
    {visitedTabs.has('tab2') && (
      <div style={{ display: activeTab === 'tab2' ? 'block' : 'none' }}>
        <ComponenteTab2 />
      </div>
    )}
  </>
);
```

---

## Formato Valori Italiani

```jsx
// Date: gg/mm/aaaa
const formatData = (d) => {
  if (!d) return '—';
  const dt = new Date(d);
  return dt.toLocaleDateString('it-IT'); // gg/mm/aaaa
};

// Valuta: separatore punto migliaia, virgola decimali
const formatEuro = (v) => {
  if (v == null) return '—';
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v);
};
// Output: €1.234,56
```

---

*Aggiornato: Aprile 2026*

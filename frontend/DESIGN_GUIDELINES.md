## Aggiornamento V8 - 2026-02-08
- F24 Unificato: nuova pagina con tab Tributi e Riconciliazione
- IVA Unificata: nuova pagina con tab Calcolo e Liquidazione
- Filtro anno aggiunto a endpoint F24 riconciliazione
- Auth middleware: aggiunti path pubblici per setup e F24
- Aggiornate 17 pagine frontend

## Aggiornamento V7 - 2026-02-08
- Nuova pagina Bilancio di Verifica
- Nuova pagina Partitario Clienti/Fornitori
- Nuova pagina Budget Previsionale
- Nuovo router contabilita_gestionale.py

## Aggiornamento V6 - 2026-02-08
- Autenticazione JWT obbligatoria attivata
- Redirect automatico a /login su 401
- Filtro anno per endpoint F24 pubblici
- Emoji 🚪 aggiunta al pulsante Esci

## Aggiornamento V5 - 2026-02-08
- Patch V5 applicata
- Aggiunta pagina Login completa
- Aggiunto pulsante Logout nella sidebar
- Endpoint /api/auth/setup per setup admin iniziale
- Strategia multi-livello per riconciliazione verbali-driver

# Design Guidelines - Azienda ERP

## Stili Consistenti per Tutte le Pagine

### Colori Principali
```css
--bg-primary: #f8fafc;         /* Sfondo pagina */
--header-gradient: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); /* Header */
--card-bg: white;              /* Sfondo card */
--card-shadow: 0 1px 3px rgba(0,0,0,0.1);
--border-color: #e2e8f0;       /* Bordi */
--text-primary: #1e293b;       /* Testo principale */
--text-secondary: #475569;     /* Testo secondario */
--text-muted: #64748b;         /* Testo attenuato */

/* Colori funzionali */
--blue-600: #2563eb;           /* Primary button, link attivi */
--green-500: #22c55e;          /* Success */
--red-500: #ef4444;            /* Danger/Error */
--orange-500: #f97316;         /* Warning */
--purple-500: #8b5cf6;         /* Info alternativo */
```

### Struttura Pagina Standard
```jsx
<div style={styles.container}>     // min-height: 100vh, bg, padding 12px
  
  {/* Header con gradiente */}
  <div style={styles.header}>      // gradient, border-radius 12px, padding 16px
    <h1 style={styles.headerTitle}>Titolo Pagina</h1>
    <p style={styles.headerSub}>Descrizione breve</p>
    
    {/* Stats opzionali nel header */}
    <div style={styles.statsGrid}>
      <div style={styles.statBox}>
        <div style={styles.statValue}>123</div>
        <div style={styles.statLabel}>Label</div>
      </div>
    </div>
  </div>
  
  {/* Card contenuto */}
  <div style={styles.card}>
    <div style={styles.cardTitle}>
      <Icon size={18} />
      Titolo Sezione
    </div>
    {/* Contenuto */}
  </div>
  
</div>
```

### Stili Base da Copiare
```javascript
const styles = {
  container: {
    minHeight: '100vh',
    background: 'var(--bg-primary, #f8fafc)',
    padding: '12px',
    paddingBottom: '80px'   // Spazio per navbar mobile
  },
  header: {
    background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)',
    borderRadius: '12px',
    padding: '16px',
    marginBottom: '16px',
    color: 'white'
  },
  headerTitle: {
    fontSize: '18px',
    fontWeight: '600',
    margin: 0
  },
  headerSub: {
    fontSize: '13px',
    opacity: 0.9,
    marginTop: '4px'
  },
  card: {
    background: 'white',
    borderRadius: '12px',
    padding: '16px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    marginBottom: '12px'
  },
  cardTitle: {
    fontSize: '16px',
    fontWeight: '600',
    marginBottom: '12px',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    color: '#1e293b'
  },
  btn: {
    padding: '12px 16px',
    fontSize: '14px',
    fontWeight: '500',
    borderRadius: '8px',
    border: 'none',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    transition: 'all 0.2s'
  },
  btnPrimary: {
    background: '#2563eb',
    color: 'white'
  },
  btnSuccess: {
    background: '#22c55e',
    color: 'white'
  },
  btnDanger: {
    background: '#ef4444',
    color: 'white'
  },
  btnOutline: {
    background: 'white',
    color: '#475569',
    border: '1px solid #e2e8f0'
  },
  input: {
    width: '100%',
    padding: '12px',
    fontSize: '14px',
    border: '1px solid #e2e8f0',
    borderRadius: '8px',
    outline: 'none'
  },
  select: {
    width: '100%',
    padding: '12px',
    fontSize: '14px',
    border: '1px solid #e2e8f0',
    borderRadius: '8px',
    outline: 'none'
  },
  label: {
    display: 'block',
    fontSize: '13px',
    fontWeight: '500',
    marginBottom: '6px',
    color: '#475569'
  },
  badge: {
    display: 'inline-block',
    padding: '2px 8px',
    fontSize: '11px',
    fontWeight: '500',
    borderRadius: '4px',
    marginRight: '4px'
  },
  badgeBlue: {
    background: '#dbeafe',
    color: '#1d4ed8'
  },
  badgeGreen: {
    background: '#dcfce7',
    color: '#15803d'
  },
  badgeOrange: {
    background: '#fed7aa',
    color: '#c2410c'
  }
};
```

### Icone
- Usare **lucide-react** per tutte le icone
- Size standard: 18px per icone inline, 20px per header
- Importare solo le icone necessarie

### Mobile First
- Grid a 2 colonne: `gridTemplateColumns: 'repeat(2, 1fr)'`
- Gap standard: 8px o 12px
- Padding container: 12px
- Border radius: 8px per elementi piccoli, 12px per card
- Font size: 13-14px per body, 16-18px per titoli

### Da NON Fare
❌ Non usare TailwindCSS classnames direttamente (usa stili inline)
❌ Non usare `bg-gray-50`, `rounded-xl`, etc.
❌ Non creare nuovi stili - riusare quelli esistenti
❌ Non usare emoji negli header (solo icone lucide-react)

### Pattern per Liste
```jsx
<div style={styles.listContainer}>  // maxHeight: 400px, overflowY: auto
  {items.map(item => (
    <div 
      key={item.id}
      onClick={() => setSelected(item)}
      style={{
        ...styles.docItem,
        ...(selected?.id === item.id ? styles.docItemActive : {})
      }}
    >
      {/* Contenuto item */}
    </div>
  ))}
</div>
```

### Pattern per Form
```jsx
<div style={styles.card}>
  <div style={styles.inputGroup}>
    <label style={styles.label}>Label</label>
    <input style={styles.input} />
  </div>
  
  <div style={styles.btnRow}>
    <button style={{...styles.btn, ...styles.btnPrimary}}>
      <Icon size={18} /> Azione
    </button>
  </div>
</div>
```

---

## Riferimenti
- `/app/frontend/src/pages/InserimentoRapido.jsx` - Pagina di riferimento principale
- `/app/frontend/src/pages/DocumentiNonAssociati.jsx` - Esempio aggiornato

# Ceraldi ERP — Frontend

Frontend del gestionale Ceraldi ERP. React 18 + Vite, design system custom.

## Stack

- React 18
- Vite 5
- React Router 6
- TanStack Query 5
- Zustand (stato leggero dove serve)
- Recharts (grafici)
- jsPDF + jsPDF AutoTable (export PDF)
- xlsx (export Excel)
- lucide-react (icone)
- date-fns (date)

Nessun Tailwind in build (il plugin PostCSS è disattivato).
Il design passa tutto da `src/lib/utils.js` (inline styles + helpers).

## Script

```bash
yarn start       # dev server su porta 3000
yarn dev         # alias di start
yarn build       # build di produzione
yarn preview     # serve la build locale
```

In ambiente Supervisor il frontend è gestito da `sudo supervisorctl restart frontend`.

## Struttura

```
src/
├── main.jsx              Entry Vite: router + providers
├── App.jsx               Layout con TopNav, mobile bottom nav, ErrorBoundary, chat AI
├── api.js                Axios configurato con REACT_APP_BACKEND_URL
├── index.css             Stile globale (reset, componenti, mobile-safe, overflow-x hidden)
├── styles.css            Tokens legacy (CSS variables)
├── styles/
│   ├── topnav.css        Top navigation (palette navy)
│   ├── common.css        Shim legacy per .page-header, .card, .stat-card, ecc.
│   └── utilities.css     Utility classes CSS vanilla (Tailwind-like) per le 3 pagine legacy
├── lib/
│   ├── utils.js          Design system: COLORS, SPACING, SHADOWS, STYLES, button(), badge(), RG, formatter IT
│   ├── designSystem.js   Costanti legacy (in via di dismissione)
│   └── queryClient.js    Config TanStack Query
├── components/           UI comune, layout, widget
│   ├── layout/TopNav.jsx  Barra superiore fissa
│   └── ui/               Dialog, Confirm, ecc.
├── pages/
│   ├── hub/              Hub multi-tab (DashboardHub, ContabilitaHub, ...)
│   └── *.jsx             Pagine singole (Fatture, Prima Nota, Fornitori, ...)
├── contexts/             AnnoContext (anno globale), AuthContext
└── hooks/                useWebSocket, useHashState, ecc.
```

## Design system — come si usa

Tutti i nuovi componenti devono usare `src/lib/utils.js`:

```jsx
import { COLORS, SPACING, STYLES, button, badge, formatEuro, useIsMobile, RG } from '@/lib/utils';

export default function Esempio() {
  const isMobile = useIsMobile();
  return (
    <div>
      <header style={STYLES.pageHeader}>
        <h1 style={STYLES.pageTitle}>Titolo pagina</h1>
        <button style={button('primary')}>Azione</button>
      </header>
      <div style={RG.col3(isMobile)}>
        <div style={STYLES.statBox}>...</div>
      </div>
      <span style={badge('success')}>OK</span>
      <p>{formatEuro(1234.56)}</p>
    </div>
  );
}
```

Palette:
- primary: `#0f2744` (navy profondo)
- accent: `#b8860b` (oro sobrio)
- success / warning / danger / info + relativi soft

Spaziature: `SPACING.xs=4, sm=8, md=12, lg=16, xl=20, xxl=24`.
Radius: `BORDER_RADIUS.sm=6, md=8, lg=10`.
Shadows: `SHADOWS.sm/md/lg`.

Helpers responsive:
- `useIsMobile(768)` → boolean
- `RG.col2/col3/col4/kpi/form(isMobile)` → style grid pronto
- `pagePad(isMobile)` → padding page responsivo

## Regole grafiche

1. Full-frame: niente `max-width` fisso sui container principali. Il padding è gestito una sola volta da `.page-content` in `index.css`.
2. Tabelle larghe: wrapper `<div className="table-scroll">` o `<div style={STYLES.tableWrap}>` per avere scroll orizzontale invece di sforare.
3. Mobile safe net in `index.css`:
   - `html, body { overflow-x: hidden }`
   - input/select con `min-width: 0` e `max-width: 100%`
   - tab bar con scroll orizzontale sotto 768px
   - TopNav mostra solo brand + anno + notifiche su mobile (il menu completo è nella bottom bar)
4. Niente Tailwind. Le 3 pagine legacy (`DatiProvvisori`, `BatchReprocessing`, `GestioneInvoiceTronic`) usano classi utility vanilla da `styles/utilities.css`. Le nuove pagine NON devono aggiungere altre classi Tailwind-like.

## Variabili ambiente

`/app/frontend/.env`:
```
REACT_APP_BACKEND_URL=https://<preview-host>
VITE_BACKEND_URL=https://<preview-host>
WDS_SOCKET_PORT=443
ENABLE_HEALTH_CHECK=false
```

In produzione `REACT_APP_BACKEND_URL` deve puntare al backend pubblico.

## Test visuale rapido

```bash
# Screenshot desktop
curl -sI https://<preview-host>/ | head -1

# Dev tools mobile: Safari/Chrome → responsive 390x844
```

## Troubleshooting

- Frontend non carica: `tail -n 50 /var/log/supervisor/frontend.err.log`
- Backend irraggiungibile: verifica `REACT_APP_BACKEND_URL` e che il backend sia su
- Stile non aggiornato: il Vite ha HMR ma se hai appena modificato `index.css` potrebbe servire un refresh pieno (Cmd+Shift+R)
- Overflow orizzontale su una pagina: usa Chrome DevTools → Elements, cerca l'elemento che sfora, avvolgilo in `<div style={{ overflowX:'auto' }}>` o stringi il minWidth

## Note

- Non cancellare `src/index.js` (export compatibilità, ma non è l'entry point — lo è `main.jsx`).
- Non rimettere il plugin Tailwind in `postcss.config.cjs`: rompe la build per design.

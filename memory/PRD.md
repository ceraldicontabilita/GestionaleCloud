# PRD — Ceraldi ERP (gestionale2)

Product Requirements Document | Aprile 2026
Repo GitHub: ceraldicontabilita/gestionale2
DB: Gestionale (MongoDB Atlas)

## Identità
- Azienda: Ceraldi Group S.R.L. — Bar/Pasticceria, Napoli
- P.IVA: 04523831214 | Regime: Ordinario
- Stack: React 18 + Vite + FastAPI + MongoDB Atlas
- Utenti: staff amministrativo (no multi-tenant)

## Stato attuale
Il gestionale è in produzione con TUTTE le funzionalità core:
- Fatture SDI (1.405), Prima Nota (Cassa+Banca), Corrispettivi, Fornitori (245)
- HR (30 dipendenti, 301 cedolini), Magazzino (496 prodotti)
- Noleggio (4 veicoli, 165 verbali), Assegni (220), Riconciliazione bancaria
- Contabilità (Piano Conti, Bilancio, IVA), Email (PEC+Gmail), Scheduler

## Refactoring grafico completato (Apr 2026)

### Obiettivo
Uniformare graficamente tutto il gestionale senza toccare la logica di business.
"stile uniforme, responsive full-frame, solo utils.js, no Tailwind. Pulito e leggero".

### Modifiche applicate
1. **Design system unificato** (`src/lib/utils.js`)
   - Palette unica: Navy `#0f2744` + accent oro `#b8860b` + neutri slate
   - Helpers completi: COLORS, SPACING, SHADOWS, BORDER_RADIUS, FONT, STYLES
   - button(type), badge(type), tabStyle() come fonte unica di verità
   - RG grids, pagePad, useIsMobile per responsive
   - formattazione italiana (formatEuro, formatDateIT, ecc.)

2. **CSS globale leggero** (`src/index.css`)
   - Reset minimale, scrollbar custom, focus state coerente
   - Classi .card .btn .badge .tab .stat-box .page-header
   - Mobile bottom-nav gestito via media query
   - Nessuna direttiva @tailwind / @apply

3. **Tailwind rimosso dalla build**
   - `postcss.config.cjs` senza plugin tailwindcss (solo autoprefixer)
   - Utility CSS vanilla (`src/styles/utilities.css`) per le poche pagine legacy
     che usano classi Tailwind-like (DatiProvvisori, BatchReprocessing, GestioneInvoiceTronic)

4. **Full-frame responsive**
   - Rimosso `max-width` ovunque; `.page-content` usa 100% width
   - Padding gestito una sola volta dal layout (no duplicazione negli hub)
   - 11 hub (`ContabilitaHub`, `MagazzinoHub`, `StrumentiHub`, etc.) uniformati

5. **TopNav + palette uniformata**
   - Altezza 54px, background `#0f2744`, shadow sobria
   - Dropdown "Altro" coerente con il resto dell'app
   - Variabili CSS `--ceraldi-*` allineate alla palette utils.js

6. **Tab bar uniforme** su tutti gli hub
   - padding `8px 16px`, border radius 6, gap 6
   - Tab attivo: background `tab.color` con testo bianco, border coerente
   - Tab inattivo: background bianco, border neutro, hover cambia colore

7. **Fix backend**: installati `lxml` + `primp` mancanti per avviare uvicorn

### File toccati (refactoring grafico)
- `src/lib/utils.js` (riscritto - design system)
- `src/index.css` (riscritto - stile globale)
- `src/styles/topnav.css` (riscritto - palette uniforme)
- `src/styles/common.css` (ripulito - legacy shim)
- `src/styles/utilities.css` (nuovo - utility CSS vanilla)
- `src/styles.css` (ripulito - solo tokens legacy)
- `src/App.css` (svuotato)
- `src/App.jsx` (banner alert mantenuto)
- `src/components/layout/TopNav.jsx` (palette uniformata)
- `src/pages/hub/*.jsx` (11 file - tab bar + rimozione padding duplicato)
- `src/main.jsx` (import index.css aggiunto)
- `postcss.config.cjs` (rimosso tailwind)

### Testing
Verifica visuale su desktop (1920×900) delle pagine:
- Dashboard, Fatture, Prima Nota, Fornitori, HR, Contabilità (Piano Conti),
  Strumenti (Verifica Coerenza), Riconciliazione/Assegni, Dati Provvisori
Tutte le pagine caricano correttamente, backend connesso, nessun layout rotto.

## Backlog (non toccato in questa sessione)
- P1 Prima Nota automatica senza conferma (matching EC ≥90%)
- P1 Scarica posta verbali da PEC (endpoint stub)
- P2 Scheda fornitore completa (fatturato, scadenze, pattern pagamento)
- P2 Fascicolo dipendente (storico cedolini + TFR + presenze + bonifici)
- P2 Cleanup DB: `suppliers` (15) → merge in `fornitori` (245)
- P3 TFR automatico da cedolino
- P3 Controllo IVA mensile automatico
- P3 WhatsApp notifiche

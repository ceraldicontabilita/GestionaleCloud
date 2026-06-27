# UI Kit — Ceraldi ERP (web)

Recreation of the internal web ERP **Ceraldi ERP** (`ceraldicontabilita/GestionaleCloud`, React 18 + Vite). Faithful to the as-built design: inline styles driven by `frontend/src/lib/utils.js`, fixed navy top-nav, dense data tables, KPI grids, Italian copy.

## Files
- `index.html` — interactive entry. Login → Dashboard → Corrispettivi (other nav items show a placeholder). Tag: `@dsCard` + `@startingPoint`.
- `Icon.jsx` — Lucide icon helper (`window.Icon`).
- `TopNav.jsx` — fixed navy navigation bar (brand · primary links · "Altro" dropdown · anno selector · alert bell · avatar).
- `LoginScreen.jsx` — internal gate, navy header card.
- `DashboardScreen.jsx` — KPI overview, latest invoices table, system-alert panel.
- `CorrispettiviScreen.jsx` — KPI + daily corrispettivi data table (mirrors `pages/Corrispettivi.jsx`).

## How it composes the system
Screens read primitives from `window.CeraldiERPDesignSystem_9a014a` (`PageHeader`, `StatCard`, `Card`, `Button`, `Badge`, `Input`) — loaded from `../../_ds_bundle.js`. They do **not** reimplement primitives. Tokens come from `../../styles.css`.

## Source of truth
- Layout patterns: `frontend/src/components/PageLayout.jsx`, `pages/Corrispettivi.jsx`, `components/layout/TopNav.jsx`, `components/StatCard.jsx`.
- Routes/modules: `memoria/INDEX.md`.

The kit covers component patterns, not every module. Modules outside Dashboard/Corrispettivi are intentionally left as placeholders.

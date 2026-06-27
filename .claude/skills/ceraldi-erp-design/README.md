# Ceraldi ERP — Design System

The brand and UI system for **Ceraldi ERP** (internal codename *gestionale2 / GestionaleCloud*), the full-stack internal ERP of **Ceraldi Group S.R.L.** (Napoli, Italy).

This design system lets agents generate well-branded interfaces, mockups, slides and prototypes that look like Ceraldi ERP. Link `styles.css`, mount components from the compiled bundle, and follow the rules below.

---

## 1. Product context

Ceraldi ERP is an internal web ERP for a Naples-based group (~16 internal users; owner: Enzo Ceraldi). It unifies **accounting, accounts-payable, prima nota (cash/bank journals), HR & payroll, warehouse, car rental, bank reconciliation and HACCP traceability** — with automatic document capture from PEC/Gmail and a synchronous event-driven relational core.

- **Stack:** React 18 + Vite (frontend), FastAPI + Motor (backend), MongoDB Atlas. Design is **inline styles only** — no Tailwind, no Shadcn, no CSS-in-JS runtime.
- **Modules:** Dashboard, Fatture (invoices, costs), Corrispettivi (the *only* revenue source), Prima Nota, Fornitori, Dipendenti/HR, Cedolini, Presenze, Magazzino, Riconciliazione, Contabilità, Documenti, Noleggio, Admin.
- **Tone:** professional, accountant-grade, dense but legible. Italian-language throughout.

There is also a companion mobile employee portal (*AppDipendenti* — cedolini, bonifici, ferie/permessi) which uses a different palette (viola + navy, Plus Jakarta Sans). **This design system covers the WEB ERP only.**

### Sources (for readers with access)
- GitHub: **https://github.com/ceraldicontabilita/GestionaleCloud** — the primary product. Explore `frontend/src/lib/utils.js` (design source of truth), `frontend/src/index.css`, `frontend/src/components/`, `frontend/src/pages/`, and `memoria/INDEX.md` for the full module/route map.
- Related repos in the same org: `ceraldicontabilita/AppDipendenti` (mobile portal), `ceraldicontabilita/GestionaleSmart`.
- Explore these repositories further to build higher-fidelity designs against the real product.

> ⚠️ The repo contains a **legacy/alternate** token file (`frontend/src/design/tokens.js`) using a blue `#1535a8` + Plus Jakarta Sans theme. Per the codebase's own canon (README rule 16), the **single source of truth is `lib/utils.js`** — navy `#0f2744` + gold `#b8860b` + system fonts. This design system follows that canon.

---

## 2. Content fundamentals

**Language:** Italian, always. UI copy, labels, button text, table headers, empty states — all Italian.

- **Tone:** sober, professional, operational. Speaks the language of accounting: *Fatture, Corrispettivi, Prima Nota, Partite Aperte, Riconciliazione, Scadenziario, Cedolini, F24, Imponibile, Insoluta*.
- **Casing:** Sentence case for titles (*"Corrispettivi Elettronici"*, *"Ultime fatture ricevute"*). Column headers and small labels are **UPPERCASE** with letter-spacing (*DATA, MATRICOLA RT, AZIONI*). Badges are UPPERCASE.
- **Person:** impersonal/imperative — buttons are verbs (*Importa, Aggiorna, Salva, Elimina, Entra*). No "you/your". No marketing voice.
- **Numbers & dates:** Italian formatting. Currency `€ 1.234,56` (dot thousands, comma decimals); dates `gg/mm/aaaa` (`12/06/2026`); months abbreviated *Gen, Feb, Mar…*. Negative/credit amounts shown with a minus and red (`− € 540,00`).
- **Emoji:** used **lightly and only as inline decoration** in some titles and table headers (🧾 📋 💵 💳) — never as the icon system, never on cards as a motif. The real icon system is Lucide (see §4). When in doubt, omit emoji and use a Lucide icon.
- **Empty/loading/error states:** short, plain Italian — *"Nessun corrispettivo registrato per questo anno"*, *"Caricamento corrispettivi…"*, *"Errore caricamento: …"*.

**Examples (verbatim flavour):** page subtitle *"Corrispettivi giornalieri dal registratore telematico - Anno 2026"*; confirm dialog *"Eliminare questo corrispettivo? L'operazione non può essere annullata."*; badge *PAGATA / INSOLUTA / IN SCADENZA / NOTA CREDITO*.

---

## 3. Visual foundations

**Palette.** Deep **navy `#0f2744`** is the brand and primary action color; **gold/oro `#b8860b`** is a sober accent used sparingly (emphasis, "attenzione"). Backgrounds are cool slate (`#f1f5f9` page, `#ffffff` cards). Zero chromatic ambiguity is a hard rule: **red = error/insoluto, green = ok/paid, gold/amber = attention, blue = info**.

**Type.** The web ERP deliberately uses the **system sans stack** (`-apple-system, Segoe UI, Roboto…`) for native rendering and zero webfont latency, and the **system mono stack** (`SF Mono, Menlo…`) for numbers, so currency columns align. Base size is a dense **13px**; page titles 20px/700 navy; KPI values 24px/700; column headers 11px/700 uppercase. *(DESIGN.md aspirationally names DM Sans / DM Serif Display / JetBrains Mono, but the shipped app renders system fonts — that is what this system encodes. See Caveats.)*

**Spacing.** 4px scale (`4 · 8 · 12 · 16 · 20 · 24 · 32`). Layout is **full-frame** — 100% width, no fixed `max-width` on data pages, tables wrapped in horizontal-scroll containers.

**Backgrounds.** Flat. Solid slate page, white cards. **No gradients** on content (purple/blue gradients are an explicit anti-pattern). The only "imagery" is solid navy surfaces (top-nav, login header). No photography, illustration, texture, or pattern.

**Corners.** Restrained: `6px` inputs/buttons/tabs, `8px` data cards & badges containers, `10px` dropdowns/modals, `14px` large containers, `9999px` pills/avatars. **Border-radius > 8px on data is an anti-pattern.**

**Borders & cards.** Cards = white surface, `1px solid #e2e8f0` border, soft shadow. **No cards nested in cards.** Page headers and stat boxes carry a **left accent border** (`4px`/`3px solid navy`) — a signature motif. Avoid the "rounded card with only a colored left border" cliché *except* this specific header/stat-box treatment which is genuine to the product.

**Shadows.** Soft and **navy-tinted, never pure black**: `sm 0 1px 2px rgba(15,39,68,.06)` → `xl 0 12px 32px rgba(15,39,68,.14)`; the fixed top-nav uses `0 2px 8px rgba(15,39,68,.18)`.

**Motion.** Subtle and fast: `140ms ease` on color/background/border for buttons, tabs, links; `160ms` on cards. Dropdowns fade+slide in (`navDropIn`, ~150ms). No bounces, no decorative loops. Feedback target ≤200ms.

**Hover states.** Buttons darken slightly (primary navy → `#1e3a5f`) and gain a small shadow; secondary buttons go to `#f8fafc`; table rows tint faintly navy (`rgba(15,39,68,.025)`); nav links lighten their translucent white bg. **Press:** color shift (no shrink).

**Focus.** Navy border + soft ring `0 0 0 3px rgba(30,58,95,.12)` on inputs/selects.

**Transparency & blur.** Used only inside the navy top-nav (translucent white chips `rgba(255,255,255,.1–.18)`). No backdrop blur elsewhere.

**Tables.** The core surface. Sticky-feeling header row on `#f8fafc`, 11px uppercase muted headers, 13px cells, 1px row separators, right-aligned mono numeric columns, row hover tint, compact `10–14px` padding. Icon-only action buttons (eye / trash) in tinted square chips at row end.

---

## 4. Iconography

- **System:** **Lucide** (`lucide-react` in the app). It is the single icon set across the whole product — nav, buttons, KPIs, table actions. Stroke icons, consistent ~1.5–2 weight, rounded joins.
- **Sizes:** 14px in nav/buttons/table-actions, 18px in KPI cards, 20–22px in page-title/specimens.
- **In this system:** load Lucide from CDN — `https://unpkg.com/lucide@0.460.0/dist/umd/lucide.min.js`, then `lucide.createIcons()`. The UI kit provides an `Icon` helper (`ui_kits/ceraldi_erp/Icon.jsx`) that hydrates Lucide inside React. Common names: `layout-dashboard, file-text, building-2, users, banknote, credit-card, warehouse, receipt, bell, refresh-cw, upload, download, eye, trash-2, search, chevron-down, triangle-alert, settings, wrench, car`.
- **Emoji:** decorative only, inline in some titles/headers (see §2). Not a substitute for Lucide.
- **Logo / brand mark:** a **"CG" monogram** in a rounded square — translucent white on the navy nav, solid navy on white — paired with the wordmark **"Ceraldi ERP"**. There is no raster logo file in the repo; the monogram IS the mark (see `guidelines/brand-logo.card.html`). No custom SVG logos were invented.

---

## 5. Index / manifest

**Foundations**
- `styles.css` — entry point (link this). Imports the four token files below.
- `tokens/colors.css` · `tokens/typography.css` · `tokens/spacing.css` · `tokens/effects.css`

**Specimen cards** (`guidelines/*.card.html`) — Colors (navy, accent, status, neutrals), Type (scale, mono), Spacing (scale, radius/shadow), Brand (logo, icons).

**Components** (`components/core/`) — `Button`, `Badge`, `StatCard`, `Input`, `Select`, `Tabs`, `Card`, `PageHeader`. Each has `.jsx` + `.d.ts` + `.prompt.md`; showcase in `core.card.html`. Mount via `const { Button } = window.CeraldiERPDesignSystem_9a014a` after loading `_ds_bundle.js`.

**UI kit** (`ui_kits/ceraldi_erp/`) — interactive web-ERP recreation: `index.html` (Login → Dashboard → Corrispettivi), `TopNav`, `LoginScreen`, `DashboardScreen`, `CorrispettiviScreen`, `Icon`. See its `README.md`.

**Other:** `SKILL.md` (Agent-Skill manifest), this `README.md`.

---

## 6. Caveats
- **Fonts:** encoded as system stacks (what the shipped app renders). `DESIGN.md` names DM Sans / DM Serif Display / JetBrains Mono as an intended direction — not currently applied in code. If you want the branded typefaces instead, say so and I'll wire the webfonts (and provide JetBrains Mono for numeric columns).
- **Palette ambiguity:** the repo has a competing blue theme (`design/tokens.js`); this system follows the canonical navy+gold (`lib/utils.js`). Tell me if you actually want the blue variant captured as a theme.
- **Mobile app** (*AppDipendenti*, viola + Plus Jakarta) is **not** covered — out of scope for this attachment. Ask if you want a second kit for it.

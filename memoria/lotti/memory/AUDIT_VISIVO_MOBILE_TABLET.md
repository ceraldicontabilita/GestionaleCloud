# Audit visivo mobile/tablet — Lotti HACCP (Tranche 5, completata)

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Data: 24/07/2026 · Metodo: rig LOCALE (backend reale su mongomock
`Gestionale_Test` porta 8001 via `backend/run_locale_test.py`, build frontend
servita su porta 3001, screenshot Chromium/Playwright). Nessun contatto con
produzione, solo dati FINTI, PIN di prova 9999/1111.

## Matrice verificata

4 dimensioni × pagine (screenshot in
`scratchpad/audit_visivo/<pagina>_<WxH>.png`):

| Dimensione | Tipo |
|---|---|
| 360×800 | smartphone piccolo (il più critico) |
| 390×844 | smartphone standard (iPhone 12-15) |
| 768×1024 | tablet verticale |
| 1024×768 | tablet orizzontale |

Pagine: Home/Oggi (`#dashboard`, admin E dipendente), Ricette (`#ricette`),
Lotti (`#lotti` + dettaglio + recall), Ordini (`#ordini`), Magazzino
(`#movimenti_magazzino`), Fornitori (`#fornitori`), Ricezione merce
(`#ricezione_merce`), Temperature positive (`#temp_positive`, extra),
Backoffice (`#backoffice`, top + scroll: pagina troppo lunga per il fullPage),
Ricerca globale (overlay header), Kiosk tablet (`#tablet/home` selezione
reparto, schermata PIN, reparto pasticceria, modale Registra lotto).
Totale: 76 misure di overflow + ~80 screenshot.

**Overflow orizzontale del documento: 0 su 76 misure** (mai scroll
orizzontale di pagina, su nessuna dimensione, prima e dopo i fix).

---

## Fix già mergiati in un tentativo precedente — già corretto (commit f12dae6)

1. **Palette**: card "slateV" della Dashboard e card/gradiente "Magazzino" di
   TabletHome/TabletView rimappate da slate blu-grigio a sabbia
   `#6f583a→#4a3f33`; sfondo kiosk TabletHome da `#0f172a` (blu notte) a
   `#1c2620` (verde-nero salvia) con testi secondari riscaldati.
   *Verificato in questo giro*: `tablet_home_360x800.png` (sfondo caldo ok).
2. **Ricerca globale**: righe materie prime senza `nome_canonico` comparivano
   VUOTE → proiezione backend (nome_normalizzato/nome_originale) + fallback a
   catena nel frontend (`RicercaGlobale.jsx`).
   *Verificato*: `fix_ricerca_overlay_360x800.png` mostra "MATERIE PRIME →
   farina 00" (riga piena).
3. **LottiList**: lotto `bloccato_richiamo` indistinguibile → bordo rosso +
   badge "BLOCCATO — RICHIAMO". *Verificato*: `lotti_360x800.png` (card Torta
   caprese).
4. **RicezioneMerceView**: header con flex-wrap (i tab e "Ricezione Manuale"
   uscivano dallo schermo a 360px). *Verificato*: `ricezione_merce_360x800.png`.
5. **App.js — bottone tour "?"**: su `#ordini` copriva il tab "Compra" della
   barra fissa in basso → alzato a 84px su quella pagina. *Verificato*:
   `ordini_360x800.png`.

---

## Difetti trovati e corretti in QUESTO giro

### 1. Magazzino: filtri fuori dalla card a 360px — gravità ALTA
- Dove: `#movimenti_magazzino`, 360×800 (anche 390).
- Descrizione: la griglia filtri `1fr 1fr` (Operatore/Tipo, Dal/Al) sborda
  dalla card: i campi "Tipo" e "Al" risultavano TAGLIATI dal bordo destro
  (i `<select>`/`<input type=date>` impongono la loro larghezza minima).
- Screenshot prima: `movimenti_magazzino_360x800.png` · dopo:
  `fix_magazzino_360x800.png`.
- Fix: `frontend/src/components/haccp/ControlloMagazzinoView.jsx:187-224` —
  griglia `repeat(auto-fit, minmax(130px,1fr))` + `minWidth:0` su colonne e
  campi + `boxSizing:border-box` + font 13px sui campi data.
- Verifica: tutti e 4 i campi dentro la card, nessun taglio. Rischio residuo:
  su lingue con nomi operatore molto lunghi il testo del select si tronca con
  ellissi nativa (accettabile).

### 2. Emoji al posto di icone Lucide sulla Home e nelle intestazioni — gravità MEDIA
- Dove: Dashboard ("Conformità HACCP" ❄️🌡️✨🐞⚠️🔥♨️🚚📋📖 + scudo 🛡️,
  "Registro pesce" 🐟, "Stato sistema" 🏷🧹📊📋🌡💾) e intestazioni di TUTTE
  le pagine (PageHeader usava l'emoji di `PAGE_META`: 🚚 Fornitori, 🔁
  Magazzino, 📥 Ricezione…).
- Descrizione: contro la regola del design system ("icone Lucide, mai emoji:
  rendono con colori di sistema non controllabili, es. blu su Android");
  ❄️/🛡/🐟/💾 sono proprio blu.
- Screenshot prima: `dashboard_360x800.png` (fasce centrali) · dopo:
  `fix_dashboard_360x800.png`, `fix_header_fornitori_360x800.png`,
  `fix_header_magazzino_360x800.png`, `fix_header_ricezione_360x800.png`.
- Fix:
  - `components/haccp/HACCPHomeCard.jsx` — 10 moduli + scudo ora Lucide con
    colori palette (salvia/ocra/terracotta/verde bosco/sabbia);
  - `components/haccp/StatoSistemaWidget.jsx` — mappa etichetta→icona Lucide
    (`_ICONA_JOB`), ignora l'emoji mandata dal backend (fallback Activity);
  - `components/haccp/DashboardView.jsx` — 🐟 → `Fish` Lucide sabbia;
  - `layouts/AppLayout.jsx` — `TAB_ICONS` da navigation.js: il PageHeader
    preferisce l'icona Lucide del tab (bianca, su fascia colorata), fallback
    all'emoji di PAGE_META solo dove il tab non è in navigation.
- Verifica: screenshot `fix_*` sopra. Rischio residuo: pagine fuori da
  navigation.js (es. `fatture`, `magazzino_prodotti`) mantengono l'emoji di
  PAGE_META (fallback verificato, nessuna intestazione vuota).

### 3. Kiosk tablet: scala slate blu-grigia nei modali — gravità MEDIA
- Dove: `#tablet/*` — ModalRegistraLotto (chip 1pz…30pz, toggle pz/kg, bordi,
  testi), ModalCambioFoto, PannelloReparti (pill "rosticceria" blu `#dbeafe`),
  ModalRichiediMerce (fondo `#0f172a` blu notte, bottoni `#334155`),
  CardProdotto, TabletView.
- Descrizione: ~90 occorrenze di grigi freddi slate (`#f1f5f9 #f8fafc
  #e2e8f0 #cbd5e1 #94a3b8 #64748b #475569 #1e293b`) e blu (`#dbeafe`,
  `#0f172a`, `#334155`) contro la palette calda obbligatoria.
- Screenshot prima: `tablet_modale_lotto_360x800.png` · dopo:
  `fix_tablet_modale_360x800.png` (chip e toggle ora beige caldi).
- Fix (solo colori, zero struttura): rimappa
  `#f8fafc→#faf7f0, #f1f5f9→#f0ebe0, #e2e8f0→#e6e0d4, #cbd5e1→#cfc6b4,
  #94a3b8→#a39a87, #64748b→#7a7266, #475569→#5c564a, #1e293b→#2a3329,
  #0f172a→#1c2620, #334155→#3d463c, #dbeafe→var(--success-soft)` nei 6 file
  kiosk (`tablet/ModalRegistraLotto.jsx`, `tablet/ModalCambioFoto.jsx`,
  `tablet/PannelloReparti.jsx`, `tablet/ModalRichiediMerce.jsx`,
  `tablet/CardProdotto.jsx`, `TabletView.jsx`).
- Verifica: screenshot dopo + grep di controllo (zero hex freddi residui nei
  file kiosk). Rischio residuo: nessuno funzionale (sole sostituzioni colore).

### 4. Kiosk: ricerca "Cerca dolce…" quasi illeggibile — gravità MEDIA
- Dove: `#tablet/pasticceria` (tutte le dimensioni).
- Descrizione: input con testo/placeholder bianco su `rgba(255,255,255,.2)`
  sopra il gradiente arancione → contrasto insufficiente.
- Screenshot prima: `tablet_pasticceria_360x800.png` · dopo:
  `fix_tablet_pasticceria_360x800.png`.
- Fix: `components/haccp/TabletView.jsx:230` — fondo `rgba(0,0,0,.22)` +
  bordo `rgba(255,255,255,.35)` (testo bianco ora leggibile).
- Verifica: screenshot dopo. Rischio residuo: nessuno.

### 5. Lotti: banner alert con testo a colonna strettissima — gravità BASSA
- Dove: `#lotti` a 360px, banner rosso "N lotti scaduti da smaltire" e banner
  ambra "N lotti senza provenienza".
- Descrizione: il testo si impilava una parola per riga accanto al bottone
  ("Smalti Tutti"/"Ricalcola") invece di far scendere il bottone.
- Screenshot prima: `lotti_360x800.png` (banner) · dopo: `fix_lotti_360x800.png`.
- Fix: `components/haccp/LottiList.jsx:448-475` — `min-w-[180px]` sul blocco
  testo (banner rosso) e `flex-wrap` + `min-w-[180px]` (banner ambra): sotto
  i ~360px il bottone va a capo a larghezza piena.
- Verifica: screenshot dopo (testo su righe piene, bottone sotto). Rischio
  residuo: nessuno.

### 6. Ricezione merce: titolo card XML a colonna stretta — gravità BASSA
- Dove: `#ricezione_merce` a 360px, testata "Prodotti arrivati da fatture XML".
- Descrizione: titolo + badge "5 da verificare" + tendina "Ultimi 30gg" in
  una riga sola: il titolo andava a capo una parola per riga.
- Screenshot prima: `ricezione_merce_360x800.png` · dopo:
  `fix_ricezione_360x800.png`.
- Fix: `components/haccp/RicezioneMerceView.jsx:242-244` — `flex-wrap` +
  `gap-2` + `min-w-0` sulla testata.
- Verifica: screenshot dopo (titolo intero, badge e tendina a capo). Rischio
  residuo: nessuno.

### 7. Ricette: chip reparto "Bar" tagliata a 360px — gravità BASSA
- Dove: `#ricette` (BackofficeView tab ricette), 360×800.
- Descrizione: la fila di chip Tutti/Pasticceria/Rosticceria/Bar/Altro non
  andava a capo → "Bar" tagliata dal bordo (e "Altro" invisibile).
- Screenshot prima: `ricette_360x800.png` · dopo: `fix_ricette_360x800.png`.
- Fix: `components/haccp/BackofficeView.jsx:548` — `flexWrap:"wrap"` sulla
  fila di chip.
- Verifica: screenshot dopo (tutte e 5 le chip visibili su due righe).
  Rischio residuo: nessuno.

---

## Difetti trovati e RIMANDATI (con motivo)

1. **Emoji residue nelle UI operative** (kiosk 🧊/🛒/❄️/🔒 dentro le
   etichette dei bottoni, "📥 Importa dal foglio"/"🏭 Produci"/"✏️ Apri
   ricetta" in Backoffice/Ricette, segnaposto 🍰 delle card ricetta senza
   foto, 🔑 del keypad PIN). Motivo: sono DENTRO stringhe/template literal di
   bottoni — sostituirle con Lucide richiede ristrutturare il JSX di decine di
   punti (non è più solo CSS); fatti i punti più visibili (Home, intestazioni,
   centro HACCP, stato sistema). Da pianificare come bonifica dedicata con la
   skill `bonifica-design`.
2. **Backoffice: pagina lunghissima** (tutti i 408 prodotti renderizzati in
   card → ~92.000px di altezza a 360px; il fullPage screenshot va in timeout).
   Motivo: servono paginazione/"mostra altri" = modifica funzionale, fuori
   perimetro CSS. Gravità media (scroll pesante su telefoni datati), nessun
   difetto di layout: le card in sé sono corrette (verificato top + scroll).
3. **Fornitori: bottone "Mag. + Lotti" verde acceso** (green-500 Tailwind,
   fuori palette success `#3d8168`) e due card quasi omonime "Registro
   Qualifica Fornitori — HACCP" / "Registro Qualifica Fornitori HACCP".
   Motivo: vincolo esplicito di NON toccare `FornitoriList.jsx`; il verde è
   comunque caldo (non è un colore freddo vietato). Da riprendere quando si
   farà il refactor pianificato di FornitoriList (PIANO_REFACTOR.md).
4. **Temperature positive: griglia mensile con scroll interno** (colonne
   frigo oltre la 3ª fuori dalla prima schermata a 360px). La tabella scorre
   nel proprio contenitore (il documento NON sborda): pattern ammesso per una
   griglia giorno×frigo, ma manca un indicatore visivo di "continua a
   destra". Gravità bassa, richiederebbe un componente indicatore.
5. **Badge/neutri Tailwind "gray-100/700"** in vari componenti (pill numero
   lotto ecc.): grigio con lieve cast freddo, non slate. Gravità bassa;
   eventuale passaggio a `stone-*` da fare come bonifica di massa dedicata.
6. **Placeholder date `mm/dd/yyyy`** su Lotti/Magazzino: è il formato del
   Chromium del rig (locale en-US); su dispositivi italiani mostra
   `gg/mm/aaaa`. Non è un difetto dell'app.

## Nota rig (per i prossimi giri)

- `#tablet/home` → `#tablet/<reparto>` via cambio hash NON rimonta TabletHome
  (il reparto preselezionato non compare): nel rig serve un `page.reload()`
  dopo il goto. Nell'uso reale non accade (si tocca la card del reparto).
- `craco test` NON parte in questo checkout: `craco.config.js` richiede
  `plugins/visual-edits/*` che non è tracciato nel repo (preesistente, la CI
  esegue solo la build). Verifica affidata a `CI=false npm run build`.

## Esito finale

- Schermate fotografate: 9 pagine matrice + dettaglio lotto, recall, ricerca
  globale, dashboard dipendente, temperature positive, selezione reparto e
  PIN kiosk × 4 dimensioni (76 misure, ~80 png + serie `fix_*` post-correzione).
- Difetti: 5 "già corretto (commit f12dae6)" verificati sul rig + **7 trovati
  e corretti ora** (1 alta, 3 medie, 3 basse) + 6 rimandati con motivo.
- Overflow orizzontale di pagina: 0 ovunque, prima e dopo.
- Build: `CI=false npm run build` → **Compiled successfully** (build finale
  pulita senza `REACT_APP_BACKEND_URL`, non committata).
- File toccati (solo frontend, solo usabilità/CSS): ControlloMagazzinoView,
  HACCPHomeCard, StatoSistemaWidget, DashboardView, AppLayout, TabletView,
  LottiList, RicezioneMerceView, BackofficeView, tablet/ModalRegistraLotto,
  tablet/ModalCambioFoto, tablet/PannelloReparti, tablet/ModalRichiediMerce,
  tablet/CardProdotto.
- Rischi: sostituzioni colore massive nel kiosk (6 file) sono state fatte via
  sed sui soli hex — verificate a video sul modale Registra lotto; le altre
  schermate kiosk (ModalCambioFoto, RichiediMerce, PannelloReparti) sono
  state controllate solo a grep: un giro visivo di Enzo su tablet reale
  resta consigliato. Le intestazioni ora usano icone Lucide bianche: se una
  pagina nuova non ha né tab in navigation né emoji in PAGE_META, resta senza
  icona (comportamento invariato rispetto a prima).

# Audit React — route e componenti

Generato da `scripts/audit_react.py`.

## Route React (133)

| Path | Componente / redirect |
|---|---|
| `/login` | Login |
| `/gestione-riservata` | GestioneRiservata |
| `(index)` | DashboardHub |
| `dashboard` | DashboardHub |
| `dashboard-relazionale` | DashboardHub |
| `dashboard/:anno` | DashboardHub |
| `analytics` | DashboardHub |
| `analytics/:periodo` | DashboardHub |
| `rapido` | InserimentoRapido |
| `fatture` | FattureHub |
| `fatture/import` | redirect → /documenti/import |
| `fatture/:tab` | FattureHub |
| `fatture-ricevute` | redirect → /fatture |
| `fatture-ricevute/:fornitore` | redirect → /fatture |
| `fatture-ricevute/:fornitore/:fattura` | redirect → /fatture |
| `archivio-fatture-ricevute` | redirect → /fatture |
| `corrispettivi` | redirect → /fatture/corrispettivi |
| `corrispettivi/:anno/:mese` | FattureHub |
| `fornitori` | FornitoriHub |
| `fornitori/ordini` | redirect → /fornitori |
| `fornitori/:tab` | FornitoriHub |
| `fornitori/:nome/:dettaglio` | FornitoriHub |
| `ordini-fornitori` | redirect → /fornitori |
| `ordini-fornitori/:fornitore` | redirect → /fornitori |
| `prima-nota` | PrimaNotaHub |
| `prima-nota/pulizia` | PrimaNotaHub |
| `prima-nota/:tipo` | PrimaNotaHub |
| `prima-nota/:tipo/:anno/:mese` | PrimaNotaHub |
| `dati-provvisori` | redirect → /prima-nota#sezione=provvisori |
| `noleggio` | VeicoliHub |
| `noleggio/:tab` | VeicoliHub |
| `noleggio/verbali/:id` | VeicoliHub |
| `veicoli` | redirect → /noleggio |
| `noleggio-auto` | redirect → /noleggio |
| `noleggio-auto/:targa` | VeicoliHub |
| `verbali-noleggio/:numeroVerbale` | DettaglioVerbale |
| `verbali-noleggio/:prefisso/:numero` | DettaglioVerbale |
| `verbali-riconciliazione` | VeicoliHub |
| `verbali-riconciliazione/:verbaleId` | VeicoliHub |
| `contabilita` | ContabilitaHub |
| `contabilita/:sezione` | ContabilitaHub |
| `contabilita-hub` | redirect → /contabilita |
| `bilancio` | redirect → /contabilita/bilancio |
| `bilancio/:tab` | ContabilitaHub |
| `bilancio/:anno` | ContabilitaHub |
| `bilancio-verifica` | redirect → /contabilita/verifica |
| `partitario` | redirect → /contabilita/bilancio |
| `partitario/:tab` | ContabilitaHub |
| `budget-previsionale` | redirect → /contabilita/budget |
| `budget-previsionale/:tab` | ContabilitaHub |
| `mutui` | redirect → /contabilita/mutui |
| `piano-dei-conti` | redirect → /contabilita/piano-conti |
| `piano-dei-conti/:tab` | ContabilitaHub |
| `piano-dei-conti/:conto` | ContabilitaHub |
| `controllo-mensile` | redirect → /contabilita/controllo |
| `controllo-mensile/:anno/:mese` | ContabilitaHub |
| `calendario-fiscale` | redirect → /contabilita/calendario |
| `cespiti` | redirect → /contabilita/cespiti |
| `cespiti/:tab` | ContabilitaHub |
| `cespiti/:cespite` | ContabilitaHub |
| `finanziaria` | redirect → /contabilita/finanziaria |
| `finanziaria/:anno` | ContabilitaHub |
| `chiusura-esercizio` | redirect → /contabilita/chiusura |
| `chiusura-esercizio/:anno` | ContabilitaHub |
| `utile-obiettivo` | redirect → /contabilita/utile |
| `utile-obiettivo/:anno` | redirect → /contabilita/utile |
| `previsioni-acquisti` | redirect → /contabilita/previsioni-acquisti |
| `previsioni-acquisti/:anno` | ContabilitaHub |
| `coerenza-pos` | redirect → /riconciliazione/coerenza-pos |
| `magazzino` | redirect → /riconciliazione/coerenza-pos |
| `magazzino/:tab` | redirect → /riconciliazione/coerenza-pos |
| `inventario` | redirect → /riconciliazione/coerenza-pos |
| `inventario/:data` | redirect → /riconciliazione/coerenza-pos |
| `ricerca-prodotti` | redirect → /riconciliazione/coerenza-pos |
| `ricerca-prodotti/:query` | redirect → /riconciliazione/coerenza-pos |
| `dizionario-articoli` | redirect → /riconciliazione/coerenza-pos |
| `dizionario-articoli/:articolo` | redirect → /riconciliazione/coerenza-pos |
| `dizionario-prodotti` | redirect → /riconciliazione/coerenza-pos |
| `dizionario-prodotti/:prodotto` | redirect → /riconciliazione/coerenza-pos |
| `magazzino-dv` | redirect → /riconciliazione/coerenza-pos |
| `centri-costo` | redirect → /contabilita/centri-costo |
| `centri-costo/:centro` | redirect → /contabilita/centri-costo |
| `learning-machine` | LearningMachine |
| `learning-machine/:tab` | LearningMachine |
| `scadenze` | Scadenze |
| `scadenze/:anno` | Scadenze |
| `scadenze/:anno/:mese` | Scadenze |
| `riconciliazione` | RiconciliazioneHub |
| `riconciliazione/:tab` | RiconciliazioneHub |
| `gestione-assegni` | RiconciliazioneHub |
| `assegni` | redirect → /riconciliazione/assegni |
| `archivio-bonifici` | redirect → /riconciliazione/archivio-bonifici |
| `paypal` | redirect → /riconciliazione/paypal |
| `import-documenti` | redirect → /documenti/import |
| `import-unificato` | redirect → /documenti/import |
| `import-unificato/:tipo` | DocumentiHub |
| `import-export` | redirect → /documenti/import |
| `import-ai` | redirect → /documenti/import |
| `ai-parser` | redirect → /documenti/import |
| `ai-parser/:tipo` | DocumentiHub |
| `lettura-documenti` | redirect → /documenti/import |
| `documenti` | DocumentiHub |
| `documenti/:tab` | DocumentiHub |
| `documenti-email` | redirect → /documenti |
| `regole-categorizzazione` | redirect → /learning-machine/regole |
| `fornitori-learning` | redirect → /fornitori |
| `strumenti` | StrumentiHub |
| `strumenti/:tab` | StrumentiHub |
| `verifica-coerenza` | redirect → /strumenti/verifica |
| `verifica-coerenza/:tab` | StrumentiHub |
| `agenti` | AgentiPage |
| `commercialista` | redirect → /strumenti/commercialista |
| `commercialista/:anno/:mese` | StrumentiHub |
| `pianificazione` | redirect → /strumenti/pianificazione |
| `pianificazione/:anno` | StrumentiHub |
| `visure` | redirect → /strumenti/visure |
| `impostazioni-f24-email` | ImpostazioniF24Email |
| `integrazioni` | IntegrazioniHub |
| `integrazioni-openapi` | redirect → /integrazioni |
| `integrazioni-openapi/:tab` | IntegrazioniHub |
| `pagopa` | redirect → /integrazioni/pagopa |
| `pagopa/:pratica` | redirect → /integrazioni/pagopa |
| `admin` | AdminHub |
| `admin/:sezione` | AdminHub |
| `batch-reprocessing` | AdminHub |
| `batch-processor` | AdminHub |
| `mappa-gestionale` | MappaGestionale |
| `documenti-fiscali` | DocumentiFiscali |
| `iva` | GestioneIVA |
| `fisco` | redirect → /contabilita/calendario |
| `fisco/*` | redirect → /contabilita/calendario |
| `riconciliazione-unificata` | redirect → /riconciliazione |
| `*` | PaginaNonTrovata |

## Moduli mai importati (48) — candidati codice morto

Verificare a mano prima di rimuovere (import dinamici non standard).

- `frontend/src/components/AgentiPanel.jsx`
- `frontend/src/components/InvoiceXMLViewer.jsx`
- `frontend/src/components/NotificationBell.jsx`
- `frontend/src/components/WidgetAgenti.jsx`
- `frontend/src/components/WidgetVerificaCoerenza.jsx`
- `frontend/src/components/attendance/index.js`
- `frontend/src/components/prima-nota/index.js`
- `frontend/src/components/ui/accordion.jsx`
- `frontend/src/components/ui/alert-dialog.jsx`
- `frontend/src/components/ui/aspect-ratio.jsx`
- `frontend/src/components/ui/avatar.jsx`
- `frontend/src/components/ui/breadcrumb.jsx`
- `frontend/src/components/ui/calendar.jsx`
- `frontend/src/components/ui/carousel.jsx`
- `frontend/src/components/ui/checkbox.jsx`
- `frontend/src/components/ui/collapsible.jsx`
- `frontend/src/components/ui/command.jsx`
- `frontend/src/components/ui/context-menu.jsx`
- `frontend/src/components/ui/drawer.jsx`
- `frontend/src/components/ui/dropdown-menu.jsx`
- `frontend/src/components/ui/form.jsx`
- `frontend/src/components/ui/hover-card.jsx`
- `frontend/src/components/ui/input-otp.jsx`
- `frontend/src/components/ui/menubar.jsx`
- `frontend/src/components/ui/navigation-menu.jsx`
- `frontend/src/components/ui/pagination.jsx`
- `frontend/src/components/ui/popover.jsx`
- `frontend/src/components/ui/progress.jsx`
- `frontend/src/components/ui/radio-group.jsx`
- `frontend/src/components/ui/resizable.jsx`
- `frontend/src/components/ui/scroll-area.jsx`
- `frontend/src/components/ui/separator.jsx`
- `frontend/src/components/ui/sheet.jsx`
- `frontend/src/components/ui/skeleton.jsx`
- `frontend/src/components/ui/slider.jsx`
- `frontend/src/components/ui/switch.jsx`
- `frontend/src/components/ui/table.jsx`
- `frontend/src/components/ui/textarea.jsx`
- `frontend/src/components/ui/toaster.jsx`
- `frontend/src/components/ui/toggle-group.jsx`
- `frontend/src/components/ui/tooltip.jsx`
- `frontend/src/hooks/index.js`
- `frontend/src/hooks/useResponsive.js`
- `frontend/src/hooks/useScrollRestore.js`
- `frontend/src/index.js`
- `frontend/src/stores/index.js`
- `frontend/src/utils/dateUtils.js`
- `frontend/src/utils/urlHelpers.js`

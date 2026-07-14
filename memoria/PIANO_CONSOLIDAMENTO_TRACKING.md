# PIANO RESIDUO — Indice di avanzamento

> Documento vivo. Sostituisce la prima versione (14/07/2026, basata sul
> report esterno) con il `PIANO_RESIDUO_AGGIORNATO_GESTIONALECLOUD.md`
> fornito dall'utente lo stesso giorno — più preciso perché pinnato a un
> commit e perché distingue nettamente il già-fatto dal residuo reale.
> Va aggiornato ad ogni operazione: l'utente deve poter leggere "operazione
> N di 19" e sapere cosa resta.

**Commit di riferimento del piano:** `16dcc570` (poi `0eb3f73` con la prima
versione di questo tracking — nessuna attività di codice tra i due).

## Regola di aggiornamento (vincolante, dal documento dell'utente)

Quando un'attività è completata:
1. rimuoverla da "Attività residue";
2. aggiungerla a "Completate dopo il 14/07/2026" con commit, file
   modificati, test, risultato;
3. rigenerare le mappe (`scripts/genera_mappa.py`,
   `scripts/genera_classificazione_endpoint.py`);
4. nessuna duplicazione tra fatto e da fare.

Le voci in **NON RIPETERE** non vanno mai riproposte come domande né
rilavorate da zero.

## Stato di avanzamento

**Tutte le 19 operazioni del piano sono chiuse o portate al massimo
eseguibile in sicurezza da questo ambiente** (1, 2-10, 11, 12, 13, 14, 15,
16, 17, 18, 19). Dettaglio di ciascuna in "Completate dopo il
14/07/2026". Il "debito tecnico da implementare" residuo — quanto NON è
stato possibile chiudere del tutto (produzione irraggiungibile da qui,
decisioni che toccano dati finanziari/fiscali, o volutamente rimandato a
bassa priorità) — è riepilogato in fondo a questo file.

---

## NON RIPETERE — già completate, non richiedere di nuovo

- fornitori canonici su `fornitori`, non `suppliers`;
- dipendenti canonici su `dipendenti`, non `employees`;
- cedolini canonici su `cedolini`;
- F24 canonici su `f24_unificato`;
- estratto conto canonico su `estratto_conto_movimenti`;
- fatture passive canoniche su `invoices`;
- rimozione del dominio HACCP operativo;
- rimozione contratti di lavoro e libretti sanitari dal dominio dipendenti;
- riduzione del router dipendenti;
- motore IVA (regola del 15 e anti-doppia-detrazione);
- motore F24/tributi e fiscale;
- quietanza senza F24 con alert bloccante;
- gestione DM10/RC01 e possibile doppio pagamento;
- viewer documentale canonico (`DocumentViewerModal`);
- sostituzione della maggior parte di `alert`/`confirm`/`prompt`/`window.open`;
- middleware globale di autenticazione;
- protezione endpoint distruttivi;
- saldo Prima Nota tramite motore unico;
- Piano dei Conti ufficiale con mapping;
- i 12 bug P0 (coperti da test);
- rimozione Emergent e codice morto già censito;
- pipeline Fatture Estere (AI + coda di verifica + rating);
- audit atomico e mappe aggiornate al 14/07/2026.

Su queste voci: solo verifica di assenza regressioni, mai ricostruzione.

---

## Attività residue

Nessuna: tutte le 19 operazioni del piano sono state chiuse o portate al
massimo eseguibile in sicurezza da questo ambiente (senza credenziali di
produzione). Il debito tecnico rimanente — sempre concreto, mai generico —
è elencato in fondo a questo file.

---

## Completate dopo il 14/07/2026

**1. ✅ Rigenerare tutti gli inventari sullo stesso commit + test anti-mismatch**
- Commit: `f79260f` → questa chiusura.
- Rilanciati `python scripts/genera_mappa.py` e
  `python scripts/genera_classificazione_endpoint.py`: `MAPPA_ROUTER.md` e
  `MAPPA_ENDPOINT_COMPLETA.md` erano già coerenti (1059 endpoint, invariati).
  `ENDPOINT_CLASSIFICAZIONE_FINALE.md` era stale (dichiarava 1072 nell'header
  ma 1059 nel corpo, con 13 route dipendenti/contratti/libretti già rimosse
  dal codice ma ancora presenti in tabella): rigenerato a 1059 endpoint · 640
  tenere · 400 verificare · 19 admin-only.
- `AUDIT_ATOMICO_APPLICAZIONE.md` già riportava 1059, nessuna modifica
  necessaria. `MAPPA_COLLEZIONI.md` non ha uno script generatore dedicato
  (resta aggiornamento manuale, nota di debito tecnico separato).
- Aggiunta nota "documento storico, non autoritativo" in testa a
  `AUDIT_ESECUZIONE_DEFINITIVO.md` (dichiarava ancora 1105/1106, baseline
  13/07 pre-pulizia) per evitare confusione futura, senza riscrivere la
  cronaca storica.
- File nuovo: `tests/test_route_map_consistency.py` (4 test: MAPPA_ROUTER,
  MAPPA_ENDPOINT_COMPLETA e ENDPOINT_CLASSIFICAZIONE_FINALE coerenti con la
  route table reale via `register_all_routers`; somma tenere+verificare+
  admin-only = totale). Verrà collegato come check bloccante CI
  nell'operazione #19.
- Risultato: `python -m pytest -q` → 378 passed, 2 skipped (era 374 passed:
  +4 dai nuovi test), nessuna regressione.

**2-10. ✅ Smontaggio endpoint "verificare" senza chiamanti (9 gruppi, ~88 endpoint)**
- Commit: `71a68b7` (batch/exports/report_pdf/pos_accredito/dati_provvisori/
  drive_cedolini/realtime/paghe import) + chiusura in corso su questo branch
  (gruppo verbali/trattenute).
- Indagine preliminare (agente dedicato) su chiamate interne/scheduler/test
  per ognuno dei 9 gruppi, prima di qualunque modifica — evidenze file:riga
  citate per ogni verdetto (MORTO/VIVO-INTERNO/INCERTO).
- Decisione utente raccolta via 3 domande (AskUserQuestion): sì a smontare
  i morti confermati, sì a smontare solo la route HTTP dove il servizio
  resta vivo altrove, sì a includere anche il gruppo verbali/trattenute in
  questo giro (upload-quietanza escluso per prudenza, caso incerto).
- Smontati interamente (0 chiamanti ovunque, codice conservato in git, non
  montato in produzione): `batch_operations` (6), `reports.simple_exports`
  (8), `reports.report_pdf` (4), `bank.pos_accredito` (5 — `app/utils/
  pos_accredito.py` resta vivo, usato da `pos_corrispettivi_check` e
  `corrispettivi.py`), `trattenute_verbali` (7).
- Route HTTP morta ma funzione Python viva (rimossa solo la route, la
  funzione resta servizio interno normale): `distinte_bpm`,
  `libro_unico_parser`, `f24_parser` (chiamati da `documenti.py`),
  `drive_cedolini` quadratura (chiamata dallo scheduler),
  `websocket_realtime` GET /realtime/status (i websocket reali
  `/ws/notifications` e `/ws/dashboard` restano intatti), `verbali_noleggio_
  api` scan-gmail/riconcilia-completo, `verbali_riconciliazione` scan-email
  (servizi già chiamati direttamente da `app/scheduler.py`).
- `dati_provvisori`: rimossi 5 endpoint del vecchio flusso (upload-xml,
  sposta-banca, sposta-cassa, delete, lista) superato dal tab Provvisori in
  `PrimaNota.jsx` (`/api/prima-nota/provvisori/*`); `riconcilia-estratto-
  conto` (scheduler) e i 5 endpoint proposte/conferma non toccati.
- `drive_cedolini`: rimossi anche status e `{id}/pdf` (0 chiamanti).
- Gruppo verbali (3 file, ~3269 righe totali, lavoro delegato a 3 agenti in
  parallelo con istruzione precisa endpoint-per-endpoint): `verbali_
  noleggio.py` (16 handler rimossi, tenuti dettaglio/pdf/verbali-completi),
  `verbali_noleggio_api.py` (10 rimossi inclusi i 2 "route morta/servizio
  vivo", tenuti dettaglio:path e upload-quietanza), `verbali_
  riconciliazione.py` (19 rimossi, tenuti dashboard/lista/scan-fatture-
  verbali/pulisci-duplicati/riconcilia/collega-driver-massivo). Rimossi
  anche gli helper privati diventati orfani di conseguenza (verificato con
  grep che non fossero usati da altro).
- Fix collaterale: `backend/tests/test_fase2_fase3_fase4.py` (test di
  integrazione live, self-skip senza `REACT_APP_BACKEND_URL`, quindi non
  intercettato dalla suite locale) testava cerca-pagamento/ricevuta-pdf/
  scan-gmail/riconcilia-completo dei verbali: rimossi i 4 test-case ormai
  orfani con nota esplicativa, altrimenti avrebbero fallito con 404 in un
  ambiente con l'URL configurato.
- Debito noto, non affrontato in questa operazione: `memoria/pagine/
  noleggio-verbali.json` e `memoria/pagine/dettaglio-verbale.json`
  potrebbero citare nomi di funzioni rimosse (mappe/documentazione, non
  eseguibili — nessun impatto funzionale).
- Mappe rigenerate ad ogni gruppo: 1059 → 991 (checkpoint) → **971**
  endpoint totali, 637 tenere, 315 verificare, 19 admin-only (verificato
  che il delta -88 torna esatto sommando i singoli gruppi).
- Risultato: `python -m pytest -q` → 378 passed, 2 skipped (nessuna
  regressione), `python -m pytest backend/tests/ -q` → 2 skipped (invariato).

**11. ✅ Audit reale frontend inutilizzato + eliminazione orfani**
- Commit: chiusura in corso (vedi prossimo commit su questo branch).
- File nuovo: `scripts/audit_frontend_dead_code.py` — grafo di import reale
  a partire da `main.jsx`/`App.jsx`/`navigation.config.js` (import statici,
  `import()` dinamici, `lazy(() => import(...))`, re-export `export {X}
  from`/`export * from` per i barrel file), classificazione
  ENTRYPOINT/ROUTE_ATTIVA/COMPONENTE_USATO/MODALE_USATO/HOOK_USATO/
  TEST_ONLY/DINAMICO_DA_VERIFICARE/ORFANO_ELIMINABILE, con safety net
  anti falso-positivo (grep del basename in tutto il codice prima di
  dichiarare un file orfano — se il nome compare altrove, va in
  DINAMICO_DA_VERIFICARE, mai eliminato in automatico).
- File nuovo: `memoria/AUDIT_FRONTEND_DEAD_CODE.md` (rigenerabile).
- Eliminati 34 file orfani confermati (0 riferimenti ovunque nel repo,
  verificati manualmente con grep incrociato prima di ogni cancellazione),
  in 3 gruppi (30 diretti + 4 rivelati a cascata dopo il primo giro + 1
  dopo il secondo, fino a convergenza a 0 orfani):
  - 21 componenti `components/ui/*` di shadcn/ui mai adottati (accordion,
    alert-dialog, aspect-ratio, breadcrumb, calendar, carousel,
    collapsible, context-menu, dropdown-menu, hover-card, input-otp,
    menubar, navigation-menu, pagination, radio-group, resizable,
    scroll-area, separator, skeleton, slider, toggle-group);
  - 3 componenti applicativi morti (`InvoiceXMLViewer.jsx`,
    `WidgetAgenti.jsx`, `WidgetVerificaCoerenza.jsx`);
  - l'intera cartella `components/prima-nota/` (barrel `index.js` +
    `PrimaNotaComponents.jsx` + `PrimaNotaSalariTab.jsx`, superata dal
    consolidamento hub — cartella rimossa, ora vuota);
  - 3 barrel file mai importati come directory (`hooks/index.js`,
    `stores/index.js`) + 4 hook morti (`useResponsive.js`,
    `useScrollRestore.js`, `useAbortableEffect.js`);
  - 3 utility morte (`utils/constants.js`, `utils/dateUtils.js`,
    `utils/urlHelpers.js`).
- Verifica: `yarn build` verde dopo ogni gruppo (bundle `frontend/dist`
  invariato byte-per-byte: i file erano già fuori dal grafo di build,
  conferma indipendente che erano davvero morti). Nessuno script `yarn
  lint` esiste in questo repo (non in `package.json`), quindi solo build
  come verifica statica. `python -m pytest -q` → 378 passed, 2 skipped
  (nessun impatto sul backend).
- Risultato finale: `AUDIT_FRONTEND_DEAD_CODE.md` → 139 file analizzati,
  0 ORFANO_ELIMINABILE, 22 DINAMICO_DA_VERIFICARE (nome trovato altrove nel
  codice, non eliminabili senza verifica manuale mirata — restano per una
  eventuale prossima passata).

**12. ✅ Adozione `app/db_collections.py` (scope: chiudere il drift, non riscrivere ~2000 letterali già corretti)**
- Commit: `dfb2f63`.
- Trovati e corretti 2 bug reali (non solo hardcode stilistico):
  `app/services/trattenute_verbali_service.py` e
  `app/routers/paypal_statements.py` leggevano l'arricchimento dipendente
  dalla collection legacy vuota `employees` invece di `dipendenti` — il
  lookup falliva sempre, silenziosamente.
  `app/database.py::Collections`: i 13 attributi con un corrispondente in
  `db_collections.py` sono ora alias delle costanti (`COLL_*`) invece di
  stringhe duplicate — elimina il rischio di drift silenzioso futuro.
- File nuovo: `tests/test_no_hardcoded_deprecated_collections.py` — blocca
  l'uso diretto (fuori dagli script di migrazione) delle collection
  deprecate note, con eccezioni esplicite documentate per 2 cleanup a
  cascata legittimi (`cascade_operations.py`,
  `suppliers_module/base.py` — `delete_many` su `warehouse_stocks`
  durante l'eliminazione fornitore, non lettura come fonte dati) e per un
  modulo orfano scoperto durante l'indagine (`app/utils/
  warehouse_helpers.py`, 0 importer in tutto il repo, legge
  `warehouse_stocks` con uno schema — `descrizione`/`codice`/`giacenza` —
  incompatibile con quello reale di `warehouse_inventory` —
  `nome`/`codice_articolo_fornitore` — segnalato come debito tecnico, non
  toccato: nessun chiamante quindi nessun rischio immediato, ma andrebbe
  riscritto o eliminato).
- Non affrontato (basso rischio, basso valore): conversione delle ~2000
  stringhe letterali già corrette (es. `db["invoices"]`) alle costanti
  importate — il valore è già quello canonico, solo non centralizzato.
- Risultato: `python -m pytest -q` → 379 passed, 2 skipped.

**13. 🟡 Verifica migrazioni produzione — bloccata qui, tooling pronto**
- Commit: `d02f99d`.
- Questo ambiente non ha credenziali del DB di produzione (nessun `.env`,
  nessuna `MONGO_URL`) — impossibile eseguire la verifica da qui.
- File nuovo: `scripts/verifica_migrazioni_produzione.py` — sola lettura,
  richiama ogni script di migrazione già esistente nella sua modalità
  dry-run (`migra(esegui=False)`, non scrive nulla) per le 7 migrazioni
  del piano, aggrega conteggi attuali + residuo da migrare in
  `memoria/VERIFICA_MIGRAZIONI_PRODUZIONE.md`. Verificato che fallisce in
  modo pulito e comprensibile senza DB configurato.
- **Azione richiesta all'utente**: lanciare
  `python scripts/verifica_migrazioni_produzione.py` in un ambiente con
  accesso al DB di produzione (o incollarmi l'output se preferisce che
  interpreti io il risultato).

**16. 🟡 Fatture emesse — normalizzazione in scrittura fatta, dato storico non verificabile da qui**
- Commit: `3f43d6f`.
- Indagine (agente dedicato): il CRUD (`invoices_emesse.py`) non aveva mai
  avuto uno schema — `POST` salvava qualunque dict così com'è. 6+ lettori
  contabili (IVA a debito, bilancio, dashboard, piano conti) avevano
  fallback IT/EN manuali e incoerenti — `imponibile`/`iva` in particolare
  SENZA fallback inglese da nessuna parte (rischio concreto: una fattura
  con solo `taxable_amount`/`vat` conteggiata a IVA zero, senza errore
  visibile). Nessun frontend usa oggi questo router; nessuna evidenza di
  un writer esterno attivo (il canale pubblico `/api/v1/fatture` è spento
  per decisione utente precedente).
- Aggiunta `normalizza_fattura_emessa()`: riempie i campi canonici
  italiani dalle alternative osservate, applicata in creazione (unico
  endpoint di scrittura). Non tocca i documenti già in produzione.
- **Non affrontato, richiede conferma esplicita prima di procedere**: il
  fallback mancante nell'aggregation pipeline di
  `app/services/ragioneria_service.py::calcola_iva_debito_corretto` (IVA a
  debito) per i documenti GIÀ in produzione — servirebbe `$ifNull` su
  `imponibile`/`iva`, ma è un calcolo fiscale live, senza test di
  copertura, e non posso verificare da qui la forma reale dei dati
  esistenti. Fix pronto da applicare (vedi commit `3f43d6f` per i
  dettagli), ma tocca l'IVA a debito calcolata: da confermare.
- Risultato: `python -m pytest -q` → 382 passed, 2 skipped (+3 nuovi test
  sul normalizzatore).

**17. ✅ Prestazioni — reso visibile il troncamento silenzioso (non riscritte le query)**
- Commit: `1450060`.
- Non riscritte le 22 query in aggregation pipeline (rischio reale su
  codice contabile senza analisi caso per caso — restano in
  `AUDIT_PERFORMANCE_N1.md` come debito tecnico esplicito, priorità alle 4
  marcate "VERIFICARE: aggregazione potenzialmente completa" in
  `assegni.py` e `bonifici_module/riconciliazione.py`/
  `prima_nota_module/manutenzione.py`).
- Fix minimo e sicuro applicato a 20 dei 21 punti (14 router applicativi +
  6 script di migrazione): log/print di warning quando il risultato
  raggiunge esattamente il tetto (50000/100000), che oggi passa
  inosservato. Non cambia nessuna logica né tetto numerico. 1 punto
  (`migra_employee_contracts_a_contratti.py`) non esiste più nel repo
  (già rimosso in una sessione precedente, audit non aggiornato).
- Risultato: `python -m pytest -q` → 379 passed, 2 skipped, nessuna
  regressione.

**18. 🟡 Viewer — E2E per il componente condiviso su 3 viewport**
- Commit: `ed8bb53`.
- `frontend/scripts/audit-viewer.cjs` + workflow `viewer-e2e.yml` (stesso
  pattern di `audit-layout.cjs`: API finte via `page.route`, nessun
  backend/DB reale necessario). Copre `DocumentViewerModal` (componente
  canonico condiviso da tutti gli 8 tipi documento) attraverso il flusso
  `/documenti`: overflow, chiusura, presenza controlli (fit/zoom/
  fullscreen/download), ESC, ritorno del focus. Verificato localmente
  (chromium locale, 390×844/768×1024/1920×1080) → 30/30 controlli verdi
  prima di committare.
- **Non affrontato**: i flussi specifici degli altri 7 tipi documento
  (bottone/pagina/endpoint diversi per ognuno — fattura ASSO HTML, fattura
  PDF, cedolino, F24, quietanza, PagoPA, verbale), il comportamento
  funzionale di zoom/fit/fullscreen/download (qui solo presenza/click),
  l'autorizzazione del download, i restanti 5 viewport della matrice
  originale (320×568, 360×800, 412×915, 1024×768, 1366×768).

**19. 🟡 CI — backend-tests, frontend-build, dead-code check aggiunti**
- Commit: `f05c9dd`, `ed8bb53` (viewer-e2e).
- Ad oggi (prima di questa operazione) NESSUNA pipeline eseguiva pytest o
  yarn build su push/PR: solo audit statico, smoke runtime, audit layout,
  verifica produzione.
- Nuovi workflow, tutti verificati localmente prima di committare:
  `backend-tests.yml` (pytest completa + verifica che le mappe rigenerate
  coincidano con quelle committate → copre anche route-map-consistency ed
  endpoint-classification), `frontend-build.yml`, `frontend-dead-code.yml`
  (fallisce se compare un file ORFANO_ELIMINABILE non rimosso),
  `viewer-e2e.yml` (solo su modifiche al viewer, vedi op.18).
- **Non affrontato**: `frontend-lint` (nessuno script "lint" in
  `frontend/package.json` — serve decidere se introdurre eslint),
  `security-tests` dedicato (bandit non installato — le guardie esistenti,
  es. `test_p2_admin_guards.py`, restano coperte da backend-tests),
  `migration-dry-run` in CI (richiede credenziali del DB — vedi op.13,
  lo script è pronto, manca solo il secret in GitHub Actions), gate del
  deploy Render su CI verde (si configura nel dashboard Render o nelle
  branch protection di GitHub, non è modificabile dal repo).

**14. ✅ PayPal — 2 fix isolati applicati, nessun refactor ampio necessario**
- Commit: `2f65c3b`.
- Indagine (agente dedicato): la premessa del report originale ("2 router,
  6 service in conflitto") era sovrastimata. I due router
  (`paypal-api`, `paypal-statements`) sono complementari non ridondanti,
  entrambi vivi, usati insieme dalla stessa pagina FE
  (`RiconciliazionePaypal.jsx`). Dedup su `transaction_id` reale impedisce
  duplicati anche lanciando entrambe le pipeline sullo stesso periodo.
- Corretti: (1) il dettaglio transazione leggeva il mapping fornitore da
  `paypal_mapping_fornitori`, una collection mai scritta da nessuna parte
  del codice (verificato con `git log -S` su tutta la storia) — ora legge
  `fornitori.paypal_account_id`, il percorso vivo reale; (2) il KPI
  "riconciliati" della dashboard contava solo `riconciliato_banca`
  (percorso statement), ignorando `riconciliato_con_estratto_banca`
  (percorso API) — sottostimava le transazioni riconciliate solo lato
  API, ora unificati con `$or`.
- **Non affrontato, resta debito**: zero test coverage su PayPal (nessun
  test unitario esiste oggi per questi router — non solo per queste 2
  funzioni), il disallineamento `tipo` (stringa italiana vs T-code PayPal
  grezzo tra le due fonti — cosmetico, il FE ha già un fallback
  silenzioso), un secondo client OAuth2 verso PayPal
  (`app/services/paypal_integration.py`, usato solo da endpoint
  `email_download.py` verosimilmente morti, non verificato in questa
  operazione).
- Risultato: `python -m pytest -q` → 382 passed, 2 skipped.

**15. ✅ Verbali — 1 fix isolato applicato, migrazione dati resta debito esplicito**
- Commit: `81fac0b`.
- Indagine (agente dedicato): la pulizia endpoint dell'operazione 2-10 ha
  già risolto il problema a livello di *route* (da ~56 a 11 endpoint,
  zero morti). Il problema reale oggi è sui *dati*: due collection
  (`verbali_noleggio`, `verbali_noleggio_completi`) per lo stesso
  concetto, alimentate da 8 percorsi di scrittura indipendenti, senza
  indice unico, con due macchine a stati diverse (`stato` vs
  `stato_pagamento`) e naming duplicato (`fattura_numero`/
  `numero_fattura`). `DettaglioVerbale.jsx` lo dimostra da solo: fa
  fallback difensivo su nomi di campo alternativi perché non sa quale
  schema riceverà a seconda che il numero verbale contenga uno slash.
- Corretto: `app/routers/verbali_noleggio.py` aveva una costante di modulo
  `COLLECTION_VERBALI = "verbali_noleggio"` shadowata da un import locale
  con lo STESSO nome ma valore diverso (`"verbali_noleggio_completi"`,
  da `verbali_service.py`) in 2 funzioni — rinominato l'import locale in
  `COLLECTION_VERBALI_COMPLETI`. Nessun cambio di comportamento, solo
  leggibilità/manutenibilità (era un bug latente in attesa di succedere
  al prossimo refactor disattento).
- **Non affrontato, richiede conferma esplicita e sessione dedicata**:
  unificare le due collection in una sola canonica con schema/stato
  comune è una migrazione di dati di produzione (piccola, ~64 documenti
  totali tra le due) che richiede una decisione esplicita su quale
  campo/stato diventa canonico — non eseguibile alla cieca da qui.
- Risultato: `python -m pytest -q` → 382 passed, 2 skipped.

---

## DEBITO TECNICO DA IMPLEMENTARE (riepilogo finale, 14/07/2026)

Tutte le 19 operazioni del piano sono state chiuse o portate al massimo
eseguibile in sicurezza da questo ambiente. Quanto segue è ciò che resta,
in ordine di priorità/rischio, con l'azione concreta per ciascuno.

### Bloccato per mancanza di accesso — priorità alta

1. **Verifica migrazioni in produzione (op.13)**: lanciare
   `python scripts/verifica_migrazioni_produzione.py` con le credenziali
   del DB di produzione (`.env`, vedi `app/database.py`). Lo script è
   pronto e sola-lettura. Serve prima di considerare "vera" qualunque
   migrazione dichiarata fatta nel codice.

### Decisioni utente richieste prima di procedere — rischio finanziario/fiscale

2. **IVA a debito su fatture emesse storiche (op.16)**:
   `app/services/ragioneria_service.py::calcola_iva_debito_corretto`
   non ha fallback inglese su `imponibile`/`iva` nell'aggregation
   pipeline — una fattura emessa già in produzione con solo
   `taxable_amount`/`vat` verrebbe conteggiata a IVA zero, senza errore
   visibile. Fix pronto (`$ifNull` a cascata), non applicato perché tocca
   un calcolo fiscale live senza test di copertura e senza modo di
   verificare da qui la forma reale dei documenti in produzione. **Prima
   di applicarlo**: eseguire punto 1, controllare quanti documenti
   `fatture_emesse` esistono con solo campi inglesi.
3. **Unificazione dati Verbali (op.15)**: `verbali_noleggio` (52 doc) e
   `verbali_noleggio_completi` (12 doc) restano due collection per lo
   stesso concetto, con due macchine a stati diverse. Migrarle in una
   sola richiede decidere quale campo/stato diventa canonico — non
   eseguibile senza conferma esplicita.

### Debito noto, basso rischio, rimandabile

4. **22 query N+1/`to_list` non riscritte (op.17)**: reso visibile il
   troncamento (log/print se il tetto viene raggiunto), ma la logica
   resta O(n) su `to_list(50000/100000)`. Priorità alle 4 marcate
   "VERIFICARE: aggregazione potenzialmente completa" in
   `app/routers/bank/assegni.py`, `bonifici_module/riconciliazione.py`,
   `prima_nota_module/manutenzione.py` — vedi `memoria/AUDIT_PERFORMANCE_N1.md`.
5. **Viewer E2E incompleto (op.18)**: coperto solo il flusso PDF generico
   (`/documenti`) su 3 viewport. Mancano i flussi specifici di fattura
   ASSO HTML, fattura PDF, cedolino, F24, quietanza, PagoPA, verbale
   (bottone/pagina/endpoint diversi per ognuno — lo script
   `frontend/scripts/audit-viewer.cjs` è un template pronto da estendere),
   il comportamento funzionale di zoom/fit/fullscreen/download (oggi solo
   presenza/click), l'autorizzazione del download, 5 viewport della
   matrice originale (320×568, 360×800, 412×915, 1024×768, 1366×768).
6. **CI incompleta (op.19)**: manca `frontend-lint` (nessuno script
   "lint" nel repo — decidere se introdurre eslint), `security-tests`
   dedicato (bandit non installato), `migration-dry-run` in CI (lo script
   c'è, serve il secret DB in GitHub Actions), il gate del deploy Render
   su CI verde (si configura fuori dal repo: dashboard Render o branch
   protection GitHub).
7. **PayPal — copertura test zero (op.14)**: nessun test unitario esiste
   per `paypal-api`/`paypal-statements`. I 2 fix applicati sono a basso
   rischio (query in lettura) ma senza rete di sicurezza automatica.
   Debito minore: `app/services/paypal_integration.py` (secondo client
   OAuth2, usato solo da endpoint `email_download.py` probabilmente
   morti) non verificato; disallineamento `tipo`/T-code cosmetico.
8. **`app/utils/warehouse_helpers.py` orfano (scoperta durante op.12)**:
   0 importer in tutto il repo, legge la collection deprecata
   `warehouse_stocks` con uno schema incompatibile con quello reale di
   `warehouse_inventory`. Nessun rischio immediato (nessun chiamante),
   ma se mai riagganciato va riscritto, non basta cambiare il nome della
   collection. Candidato a eliminazione come gli orfani frontend
   dell'op.11, non ancora deciso.
9. **`memoria/pagine/*.json` (mappe funzionali dettagliate)**: alcuni
   file (es. `noleggio-verbali.json`, `dettaglio-verbale.json`) citano
   ancora endpoint/funzioni rimossi nell'operazione 2-10. Sono
   documentazione, non codice eseguibile — nessun impatto su test/CI/
   runtime, ma disallineati con lo stato reale. Da riscrivere in una
   sessione dedicata alla documentazione, non prioritario.
10. **22 file `DINAMICO_DA_VERIFICARE` nel frontend (op.11)**:
    `memoria/AUDIT_FRONTEND_DEAD_CODE.md` li elenca — il loro nome
    compare altrove nel codice (spesso solo perché parola generica, es.
    "table", "form") ma nessun import statico li raggiunge. Nessuno
    eliminato per prudenza: richiedono verifica manuale mirata,
    caso per caso.
11. **Conversione stringhe letterali → costanti `db_collections.py`
    (op.12)**: ~2000 usi di `db["invoices"]` e simili con valore già
    corretto ma non centralizzato. Basso rischio, basso valore, non
    affrontato: il test anti-hardcode aggiunto copre già il rischio
    reale (nomi SBAGLIATI), non lo stile.

### Criterio di completamento originale — stato

Dal report iniziale (§13): conteggi endpoint coerenti ✅, file React
orfani ✅ (0 rimasti, 22 da verificare manualmente), ogni endpoint montato
con un chiamante documentato ✅ (971 endpoint, classificazione
rigenerata), collection legacy senza nuove scritture 🟡 (bloccato senza
verifica produzione, punto 1), migrazioni eseguite 🟡 (bloccato, punto 1),
`suppliers`/`fornitori` risolto ✅ (già chiuso prima di questa sessione),
PayPal e verbali con architettura unica 🟡 (endpoint sì, dati no — punti
2-3), query N+1 corrette 🟡 (visibili, non riscritte — punto 4), viewer
certificato 🟡 (parziale — punto 5), CI verde su main 🟡 (backend-tests/
frontend-build/dead-code/viewer-e2e sì, resto no — punto 6), deploy
dipendente da CI 🟡 (non configurabile dal repo).

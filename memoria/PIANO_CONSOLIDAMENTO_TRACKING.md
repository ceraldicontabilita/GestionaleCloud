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

**Operazioni residue aperte: 7 di 19.** Operazioni #1, #2-#10, #11 chiuse
il 14/07/2026 (vedi "Completate" in fondo). Prossima operazione libera:
**#12** (adozione `app/db_collections.py`) o **#17** (prestazioni N+1) —
le operazioni #14, #15 (PayPal, Verbali — architettura, non solo pulizia
endpoint) restano ❓ in attesa di decisione utente.

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

## Attività residue (7 operazioni aperte)

### P1 — altre attività

**12. ⛔ Completare l'adozione di `app/db_collections.py`** — trovare le
stringhe collection ancora hardcoded, sostituirle con le costanti,
trasformare `database.py::Collections` in alias o eliminarla, aggiungere
un test statico anti-hardcode. Non riaprire le decisioni fornitori/
dipendenti/cedolini/invoices/f24_unificato (già chiuse).

**13. ⛔ Verificare le migrazioni realmente eseguite in produzione** — per
ognuna delle collection canoniche (`fornitori`, `dipendenti`, `cedolini`,
`invoices`, `f24_unificato`, `estratto_conto_movimenti`,
`documenti_classificati`) controllare nel DB di produzione: sorgente,
destinazione, documenti copiati, duplicati, errori, scritture legacy dopo
la migrazione. Produrre `memoria/VERIFICA_MIGRAZIONI_PRODUZIONE.md`.
Nota: richiede accesso al DB di produzione — non eseguire nuove
migrazioni scrivendo dati, solo verificare lo stato.

**14. ❓ PayPal** — unificare 2 router, service paralleli, mapping
fornitore, import statement/API, stati, riconciliazione, idempotenza.

**15. ❓ Verbali** — architettura unica (ingest/CRUD/riconciliazione/
trattenute) con schema e collection canonici.

**16. ⛔ Fatture emesse** — armonizzare campi italiano/inglese duplicati
con DTO canonico + adapter di migrazione, senza rompere l'app esterna.

**17. 🟡 Prestazioni — query N+1/`to_list` ancora aperte** —
`memoria/AUDIT_PERFORMANCE_N1.md` le censisce già (23 query, 1 corretta).
Per ognuna: misurare, classificare interattivo/report, sostituire con
aggregation/cursor/`$in`/`bulk_write` dove è un'API interattiva,
paginazione reale, soglie di durata. Priorità: sincronizzazione
relazionale, fatture, estratto conto, Prima Nota, documenti, scheduler.

**18. 🟡 Viewer — certificazione dinamica finale** — `DocumentViewerModal`
esiste già (non ricostruire). Manca la certificazione automatizzata sugli
8 tipi documento (fattura ASSO HTML, fattura PDF, cedolino, F24, quietanza,
PagoPA, verbale, documento non associato) × 8 viewport (320×568 → 1920×1080),
verificando fit/zoom/fullscreen/download/scroll/chiusura/focus/
autorizzazione/rotazione.

### P2 — CI obbligatoria su main

**19. 🟡 CI completa e gate deploy** — esistono già `audit-static.yml`,
`smoke-runtime.yml`, `audit-layout.yml`, `verifica-produzione.yml`. Mancano
come blocking check: `backend-tests`, `frontend-lint`,
`route-map-consistency` (vedi #1), `endpoint-classification`,
`frontend-dead-code` (vedi #11), `security-tests`, `viewer-e2e` (vedi #18).
Il deploy Render deve dipendere dal verde di questi check.

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

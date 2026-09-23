# Piano di ristrutturazione di GestionaleCloud

**Documento operativo vivo, aggiornato il 23 settembre 2026.**

- Baseline iniziale dell'audit: `8cf52bd269d8d1facb478e4a585fa8b01a5ec3ff`.
- Baseline della bonifica misurata: `e283400164c0b9fb88ece13eb401fcde9cba1c42`.
- Avanzamenti concorrenti preservati: `31943965f382018d87047637e16fe815d1b93318` (public_api) e `4ad3ffa4cbfd5612e6a4b179d583a419582f2c09` (report/batch).
- Ultima tranche conclusa: [PR #656](https://github.com/ceraldicontabilita/GestionaleCloud/pull/656), navigazione condivisa Lotti accessibile.
- Codice pubblicato e verificato: **`cdc3a5f7899eda98b251c4fc4802ac2b94702fce`**.
- Prova di produzione: [CI 35706223965](https://github.com/ceraldicontabilita/GestionaleCloud/actions/runs/35706223965) e [Produzione/E2E 35706224041](https://github.com/ceraldicontabilita/GestionaleCloud/actions/runs/35706224041) verdi; `/lotti/api/health` su `gestionalecloud.onrender.com` e `impresasemplice.online` ha restituito il commit di merge esatto. La revisione UX di tutte le pagine resta aperta in RST-0906.
- Registro della prova: [PR #646](https://github.com/ceraldicontabilita/GestionaleCloud/pull/646), merge `7cba24cba1a287a47350e603d9ee2ce6a30b8163`, CI 35683619681 e Produzione manuale 35683635453 verdi; `/lotti/api/health` ha confermato anche questo commit documentale.
- **Stato complessivo: IN CORSO.** La fusione ERP, HR, Lotti e Menu non è completata. La bonifica pubblicata non certifica ogni funzione e ogni dato contabile.
- **Programma approvato il 23/09/2026:** Drive documentale canonico, integrazione Minisito fiscale, riconciliazione F24 ↔ banca e backlog audit v3 in §7-bis (ordine in §7-bis H). Ogni PR si unisce su main solo dopo l'OK esplicito del titolare.
- **Priorità operativa precedente:** verificare il ripristino delle ricette su un caso reale autorizzato e la coerenza dei riferimenti; completare le foto mancanti mediante caricamento sulla ricetta identificata per ID, senza sovrascrivere immagini manuali o inferire identità dal solo nome. Qualificare i residui strutturali dell'adattatore dati compatibile Mongo in memoria prima di riscriverli in forma canonica Supabase.

## 1. Regole di avanzamento e pubblicazione

Questo file è il registro unico del programma. Gli ID delle attività rimangono stabili. Aggiornare il piano nella stessa PR delle modifiche; aggiungere nel registro la prova del rilascio una volta disponibile. La storia dettagliata rimane in Git, senza mantenere implementazioni morte nel sorgente corrente.

| Stato | Significato |
|---|---|
| ⚪ | Da fare; nessuna implementazione conclusa |
| 🟡 | In corso, implementato ma non ancora verificato/pubblicato, o verifica operativa incompleta |
| 🟢 | Concluso nel perimetro dichiarato, con test e verifica del rilascio |
| 🔴 | Bloccato da un impedimento documentato |
| 🧊 | Differito con motivazione |
| ❌ | Eliminato e verificato; indicare commit/PR e verifiche |

Una chiusura richiede: commit/PR, perimetro preciso, confronto prima/dopo, test eseguiti e loro esiti, verifica della versione pubblicata, rollback possibile. Distinguere sempre codice scritto, test superati, merge su main e disponibilità in produzione. Un test saltato non è un test superato. Un HTTP 200 non certifica il dato contabile.

**Autonomia:** eseguire le tranche autorizzate senza chiedere conferme intermedie inutili. Non aggirare permessi, protezioni del branch, test falliti o vincoli sui dati. Le prove distruttive usano solo fixture isolate. Non creare operazioni contabili finte in produzione.

**Regola canonica di implementazione:** quando emerge un errore strutturale, una duplicazione o un'architettura transitoria, non creare nuovi guardrail, whitelist, inventari o strati di compatibilità come soluzione finale. Riscrivere il componente nella forma canonica target, migrare i chiamanti vivi, verificare il nuovo flusso con test comportamentali e rimuovere il codice legacy nella stessa sequenza di lavoro. I guardrail già esistenti restano soltanto finché proteggono transizioni non ancora eliminate; non sono un obiettivo progettuale e vanno ritirati quando il codice canonico rende il vincolo strutturalmente impossibile da violare.

**Comunicazione:** scrivere «Ho pubblicato il lavoro ed è accessibile live» solo dopo verifica del commit servito, indicando cosa è stato pubblicato. Non usare questa frase per una PR ancora aperta.

## 2. Stato verificato e correzioni all'audit iniziale

La PR #566 della Prima Nota è stata integrata con commit `b71f62d0c8a6f17994355150f4a574e73dcad021`. La baseline successiva `e283400` contiene anche i primi guardrail della Fase 0B e la rimozione del vecchio CRUD warehouse da public_api.

Il workflow [Produzione 35553261218](https://github.com/ceraldicontabilita/GestionaleCloud/actions/runs/35553261218), relativo a `e283400`, ha superato E2E isolati, apertura delle schermate catalogate, layout, viewer e controllo della versione servita con smoke. Queste prove non equivalgono al collaudo manuale di ogni operazione su dati aziendali. Il catalogo iniziale di 64 schermate riguarda l'ERP, non costituisce censimento completo delle tre sotto-app.

Main è avanzato a `3194396`: public_api.py eliminato; Pianificazione conserva /api/pianificazione/events; API v1 e ricerca globale sono in moduli dedicati. Main `4ad3ffa` ha poi eliminato i tre router report/batch. Questi avanzamenti sono stati integrati nella #569 senza ripristinare codice morto o attribuire due volte le eliminazioni.

### Esito pubblicato della tranche #569

- I moduli report_pdf.py, simple_exports.py e batch_operations.py non sono più nel sorgente attivo.
- reports/__init__.py carica soltanto la dashboard attiva; gli export dei domini vivi rimangono.
- Il filtro del batch, trasferito nel frattempo in riconciliazione_filters.py, aveva soltanto il vecchio test come chiamante. Eliminati entrambi, anziché mantenere un servizio orfano.
- Ritirati test esclusivi dei percorsi dismessi; conservati quelli effettivi di TFR, API v1, riconciliazione e Prima Nota.
- app/routers/trattenute_verbali.py era già assente nella baseline: non è una nuova eliminazione della #569. Il service trattenute e i suoi chiamanti rimangono.
- Eliminata la deroga warehouse_products dalla guardia sulle collezioni dopo la scomparsa dell'ultimo lettore. Nessuna tabella cancellata.
- Guardia permanente contro ricomparsa dei componenti dismessi e import residui.
- E2E/layout/viewer eseguiti anche sulle PR, prima del merge. Il controllo della produzione gira solo su main.
- Collaudo distruttivo limitato a HTTP locale e server con identificativo e2e-isolato.
- I collaudi isolati compilano solo l'ERP; CI e rilascio conservano la build completa delle interfacce.
- Cinque schermate Cassa/Banca/Provvisori desktop/mobile ispezionate. Artefatto finale 10619819101 del workflow 35555214652: PNG ed esito.json identici byte per byte alle immagini esaminate. Dati esclusivamente sintetici.
- Revisione automatica Codex non eseguita per quota esaurita; nessun credito acquistato. Il controllo diretto e i test non vengono descritti come una revisione automatica riuscita.

### Verifiche e limiti

HEAD collaudato prima del merge: `5d40f7e1070dff9d237d2ca0035d419676b4cc62`.

- [CI 35555214654](https://github.com/ceraldicontabilita/GestionaleCloud/actions/runs/35555214654): superata.
- [E2E/layout/viewer 35555214652](https://github.com/ceraldicontabilita/GestionaleCloud/actions/runs/35555214652): superati. Il job di produzione era correttamente escluso sulle PR.
- Merge: `7329ec7498c90da519422ade2f638f0f75d8fc55`.
- [Produzione 35555459176](https://github.com/ceraldicontabilita/GestionaleCloud/actions/runs/35555459176): E2E, schermate catalogate, layout/viewer, bundle e smoke con commit servito tutti superati.

Il metodo è CRUD HTTP reale e rilettura nel browser, non simulazione di ogni pulsante o certificazione dei dati aziendali. Le immagini della bonifica avevano evidenziato due difetti preesistenti, entrambi poi corretti e pubblicati:

1. **#573 / RST-00A7:** data Banca distinta dalla data fattura, corretta e pubblicata in `e339284b`; prova cross-month 31/08 → 02/09, data contabile/valuta separate.
2. **#575 / RST-00A6:** falsi zeri/staleness dei contatori Provvisori, corretti e pubblicati in `10a74950`; conteggi leggeri, zero solo dopo risposta reale e invalidazione al cambio sezione/anno.

La qualificazione operativa completa della Prima Nota resta prudenzialmente aperta per i casi non ancora coperti (parziali, riporto, periodi e ulteriori relazioni), ma questi due difetti specifici sono chiusi.

### Distinzioni vincolanti

1. Nomi simili o prefissi HTTP condivisi non provano duplicazione. Controllare metodo, percorso finale, ordine, chiamanti e responsabilità.
2. Nessun chiamante frontend non significa morto: controllare job, servizi, webhook, API esterne, strumenti di ripristino e accessi osservati.
3. Un import esistente soltanto in un test non rende vivo un servizio. Non trasferire codice morto per salvare un test obsoleto.
4. Il censimento storico 196 nomi/61 collezioni è una fotografia documentata, non un conteggio attuale. Collezioni vuote, alimentate da trigger o servizi esterni non sono automaticamente eliminabili.
5. Quattro adapter o variabili DSN non provano quattro database di produzione. Verificare configurazione effettiva prima di pianificare trasferimenti; i commenti su progetti separati possono essere obsoleti.
6. Spostare file non elimina duplicazioni. Misurare separatamente righe applicative, test, documentazione e generati; una rinomina non è bonifica.

## 3. Obiettivo architetturale

Un solo ERP modulare: un bootstrap FastAPI applicativo, un'infrastruttura dati governata, un'identità/sessione con autorizzazioni per dominio, un coordinamento dei job e un frontend React/Vite. HR, Lotti e Menu diventano moduli, non prodotti da reimportare o riautenticare.

Struttura backend target: app/main.py, app/api/<dominio>/, app/domains/<dominio>/, app/repositories/, app/services/, app/jobs/, app/migrations/. Vietati nuovi bootstrap paralleli; quelli attuali rimangono solo durante il passaggio verificato. Le FastAPI di test isolate non sono applicazioni produttive duplicate.

Unico progetto/database operativo previsto. Gli schemi di dominio possono rimanere distinti. Non imporre un unico oggetto client globale se servono connessioni con privilegi differenti: eliminare fonti di verità e logiche duplicate, preservando isolamento e transazioni.

### Proprietà dei dati

| Entità | Responsabilità canonica |
|---|---|
| Originali documentali | Originale immutabile, hash e riferimenti; Drive non è il database operativo |
| Inbox e classificazione | Ingresso unico con stato, parser/versione ed errori tracciati |
| Fatture e righe | invoices e righe canoniche, un ID/versione per documento |
| Fornitori | fornitori, condivisi dai domini |
| Dipendenti | Anagrafica HR canonica, identità stabile |
| Cedolini | Record canonico versionato, non copie ERP/HR/payslip |
| Banca | estratto_conto_movimenti come evidenza; scritture e classificazioni collegate |
| Prodotti/ingredienti | Catalogo unico con codici fornitore e unità normalizzate |
| Magazzino | Ricezioni e movimenti verificabili, lotto quando disponibile |
| Ricette | Versioni, ingredienti canonici, rese, costo e allergeni verificati |
| Menu | Proiezione di pubblicazione con prezzo e visibilità deliberati |

### PIN e permessi

Il verificatore amministratore app/services/admin_pin.py è già condiviso in alcuni ingressi. Questo non completa l'unificazione: esistono ancora emittenti/sessioni e router locali.

**Admin del Gestionale deve essere l'unico posto per gestire accessi, ruoli e PIN.** Nessuna configurazione amministrativa duplicata in Lotti, HR o Menu. Credenziali protette lato server, rotazione/revoca tracciate, limiti tentativi condivisi e MFA per operazioni sensibili. Mai PIN in chiaro nei dati, log o repository. PIN e token ottenuto con esso non sono due fattori distinti.

I PIN personali identificano il dipendente canonico per il gesto operativo; non sostituirli con un PIN condiviso fra persone. Un'unica sessione non autorizza ogni ruolo a tutto. Menu clienti pubblico, portale personale, dati retributivi e amministrazione rimangono separati per autorizzazione. Verificare accessi negati e revoche attraverso tutti i moduli.

### Flussi affidabili, non copie

**Fattura:** acquisizione unica → fornitore/righe → contabilità, IVA, debito e scadenza quando applicabili → prodotti, prezzi e ricezione → inventario/lotti → costo e disponibilità delle ricette collegate → Menu autorizzato.

La fattura non dimostra da sola pagamento o consegna fisica. Una bolletta non carica ingredienti. Servizi, cespiti, anticipi e note di credito seguono il proprio ciclo. Distinguere ricezione attesa e confermata; non duplicare carichi già documentati da DDT/ricezioni. Non inventare quantità, unità, lotti, scadenze o ricette. Righe ambigue → da_mappare; passaggi non applicabili → non_applicabile.

**Cedolino:** un ID/versione → fascicolo HR, costo/debito, Prima Nota salari, TFR documentato o stima dichiarata, acconti e saldo. Il PDF del bonifico non è l'addebito: la riconciliazione bancaria richiede movimento reale e identità coerente. Rettificare senza duplicare costi o pagamenti.

**Menu:** dati canonici e pubblicazione esplicita. Non trasformare un nuovo costo ingrediente in un cambio automatico del prezzo di vendita. Non derivare allergeni certi da nomi ambigui. Qromo resta fonte di transizione fino a risoluzione di proprietà campi, compatibilità e riconciliazione catalogo.

**Outbox:** evento registrato atomicamente con il documento nella stessa transazione. Event ID, entity ID/version, tipo e versione payload, data, chiave idempotenza; stato/tentativi/errore per ciascun consumer, lease e retry persistente. Una spunta globale non basta se solo alcuni consumer riescono. Il riavvio non perde lavoro; il retry non duplica. UI con completo, pendente, errore o non applicabile per ciascun dominio. Un errore Lotti non deve far perdere la fattura né sparire in un warning.

## 4. Frontend unico

```text
frontend/
  package.json
  vite.config.js
  src/
    app/             # router, auth, provider, navigazione
    modules/
      dashboard/
      documenti/
      fatture/
      fornitori/
      banca/
      contabilita/
      fiscale/
      hr/
      lotti/
      menu/
      veicoli/
      admin/
    shared/          # componenti, hook, API, utilità, stili
    main.jsx
  public/
```

Una versione React/Router compatibile, una build Vite, client API/query e AuthProvider condivisi, design system e dialog/toast comuni. Preservare deep link, stampa, QR pubblici e tablet/mobile. /hr/*, /lotti/*, /menu/* possono restare URL della stessa SPA. I QR clienti non devono aprire il gestionale privato.

Eliminare frontend_hr/, frontend_lotti/, frontend_menu/, frontend_shared/ solo dopo migrazione di import, asset, test, build e riferimenti backend. Non cancellare funzionalità vive per ridurre artificialmente le schermate: distinguere pagina, tab, dettaglio, strumento admin e vista pubblica.

## 5. Piano progressivo con ID stabili

### Fase 0A: Prima Nota operativa

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-00A1 | 🟢 | CRUD Cassa HTTP, persistenza, saldo, modifica e soft-delete verificati; prove di reload conservate |
| RST-00A2 | 🟢 | Flussi testati: Banca senza prova resta provvisoria/fuori saldo; conferma con EC documentata |
| RST-00A3 | 🟢 | Fattura da confermare → pagamento Cassa, coperto dai collaudi |
| RST-00A4 | 🟢 | Attendi banca senza inventare pagamento, coperto dai collaudi |
| RST-00A5 | 🟢 | Misto: quota Cassa reale e residuo Banca aperto, coperto dai collaudi |
| RST-00A6 | 🟢 | #575 chiuso e pubblicato in `10a74950`: conteggi Provvisori leggeri, non-caricato distinto da zero, invalidazione al cambio sezione/anno; CI 35563595194 e Produzione 35563595236 verdi |
| RST-00A7 | 🟢 | #573 chiuso e pubblicato in `e339284b`: Banca usa la data dell'evidenza reale e conserva separatamente data documento, contabile e valuta; regressione cross-month ed E2E verdi |
| RST-00A8 | 🟢 | Smoke versione pubblicata 7329ec7 superato; ripetere ad ogni rilascio |
| RST-00A9 | 🟡 | #573 e #575 sono chiusi e live; qualificazione completa resta aperta solo per ulteriori casi contabili non ancora certificati end-to-end |

Ulteriore accettazione: importi/date invalidi senza scritture parziali, doppi invii idempotenti, pagamenti parziali multipli, annullamento coerente, originali bancari immutati, saldi iniziali e corretta attribuzione al periodo. Non attendere la fusione delle sotto-app per mantenere utilizzabile Prima Nota.

### Fase 0B: guardrail

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0001 | 🟢 | Guardia unicità metodo/percorso normalizzato in e283400; estendere verifica a sub-app e shadowing |
| RST-0002 | 🟡 | Owner espliciti degli endpoint estratti; completare audit inverso globale con job, esterni, manutenzione e telemetria |
| RST-0003 | 🟢 | Guardia AST NO-WRITE e census writer warehouse presenti; writer transitori ancora da ridurre |
| RST-0004 | 🟢 | Contratto route React ↔ catalogo pubblicato con PR #597 / `07335e5c`: schema v3 con pagina/tab/dettaglio, redirect React dichiarati e verificati, dettagli dinamici con route compatibile ed `e2e_path` concreto; CI 35588456000 e Produzione 35588455965 verdi |
| RST-0005 | 🟢 | Nessuna nuova FastAPI produttiva; tre eccezioni temporanee fino alla fusione |
| RST-0006 | 🟢 | Guardrail AST pubblicato con PR #595 / `d4b91880`: censiti 6 costruttori DB autonomi legacy in HR/Lotti/Menu; nessun nuovo client può entrare e la whitelist può solo accorciarsi; CI 35571750093 e Produzione 35571750023 verdi |
| RST-0007 | 🟢 | Inventario automatico pubblicato con PR #596 / `d481a80c`: ogni modulo con APIRouter + operazioni deve risultare realmente raggiungibile dalla app root, direttamente o tramite HR/Lotti/Menu; riconosciuti anche aggregatori `add_api_route` e nomi router non standard. CI 35579221334 e Produzione 35579221330 verdi |
| RST-0008 | 🧊 | Censimento/guardrail frontend sospeso: la PR #598 non va fusa. Per direttiva canonica, le prossime tranche devono sostituire direttamente toolchain e frontend duplicati con implementazione target, non aggiungere inventari difensivi |

warehouse_inventory è un target canonico previsto dal codice corrente: non vietarne ogni scrittura indiscriminatamente. Bloccare writer obsoleti e convergere su responsabilità unica senza interrompere Lotti.

### Fase 1: rimozione reale del morto

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0101 | ❌ | report_pdf.py eliminato, assenza/import verificati; rilascio 7329ec7 |
| RST-0102 | ❌ | simple_exports.py e import eliminati; export vivi conservati; rilascio 7329ec7 |
| RST-0103 | 🟢 | Router trattenute già assente in e283400; service vivo conservato, non è nuova cancellazione |
| RST-0104 | ❌ | batch_operations e filtro senza chiamanti runtime eliminati; nessun servizio sostitutivo orfano; rilascio 7329ec7 |
| RST-0105 | 🟢 | `import_distinte_bpm` spostato in `app/services/distinte_bpm.py`; falso router eliminato e pubblicato con commit `335d1f7a`; CI 35567802880 e Produzione 35567802918 verdi |
| RST-0106 | 🟢 | Workflow ERP Libro Unico spostato in `app/services/libro_unico_workflow.py`; falso router eliminato e pubblicato con `335d1f7a`; parser HR resta separato fino alla Fase 6 |
| RST-0107 | 🟡 | Pulizia commenti storici avviata; conservare invarianti e motivazioni utili |
| RST-0108 | 🟡 | Import/test esclusivi dei router morti rimossi; continuare census sul resto del repo |
| RST-0109 | 🟢 | `app/routers/bank/pos_accredito.py` eliminato e pubblicato in `5d66bb25`; zero chiamanti, utility viva preservata |
| RST-0110 | 🟢 | `app/routers/dati_provvisori.py` eliminato e pubblicato in `5d66bb25`; service vivo preservato |
| RST-0109 | 🟡 | Eliminato `app/routers/bank/pos_accredito.py`; zero chiamanti runtime, utility viva `app/utils/pos_accredito.py` preservata; attende CI/rilascio |
| RST-0110 | 🟡 | Eliminato `app/routers/dati_provvisori.py`; zero chiamanti runtime, service vivo `app/services/dati_provvisori_service.py` preservato; attende CI/rilascio |
| RST-0111 | 🟢 | PR #614 / merge `f567cd2ad918e1a4e4f1dd799dc6cdebaafa596d`: alias POST `/anomalie/` rimosso, creazione solo su `/anomalie/registra`; CI 35626878131 e Produzione 35626878123 verdi, commit servito e smoke superato |

Rimuovere una funzione mai pubblicata può ridurre i test: documentare il motivo e preservare copertura dei percorsi canonici. Non cancellare test falliti per nascondere regressioni vive.

### Fase 2: public_api

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0201 | 🟢 | GET/POST pianificazione/events trasferiti nel dominio corretto, URL invariati; inclusi nel codice pubblicato |
| RST-0202 | 🟡 | API v1 conservata in external_api_v1.py; completare inventario client esterni prima di ulteriori ritiri |
| RST-0203 | 🟡 | Ricerca globale ERP conservata nel proprio router; verificare consumatori e integrazione frontend |
| RST-0210 | 🟢 | Responsabilità operative riallocate, guardia owner presente e collaudata |
| RST-0211 | ❌ | public_api.py eliminato in main 3194396 e assente nel rilascio 7329ec7 |
| RST-0212 | 🟢 | Registrazione/import storici eliminati; test sull'API v1 aggiornata |

Il CRUD warehouse era già rimosso dalla Fase 0B. Non ritirare API esterne soltanto perché non chiamate dal frontend. Un endpoint nascosto da OpenAPI può essere ancora montato.

### Fase 3: infrastruttura condivisa

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0301 | ⚪ | Accesso Supabase governato e transazioni condivise |
| RST-0302 | ⚪ | Rimuovere fallback Mongo HR produttivo dopo verifica configurazione |
| RST-0303 | ⚪ | Eliminare eventuale fonte Lotti parallela, preservare attributi esclusivi HACCP |
| RST-0304 | ⚪ | Client Menu su infrastruttura comune e privilegi corretti |
| RST-0305 | ⚪ | Verificare progetto/schemi effettivi; migrare solo dati davvero separati e dopo backup |
| RST-0306 | ⚪ | Repository di dominio, writer unico per fatto, ID/FK e mapping migrazione |
| RST-0307 | ⚪ | Health/readiness senza falsi successi o fallback in memoria produttivo |
| RST-0308 | ⚪ | Coordinamento job/lease, retry e stato amministrativo unico |
| RST-0309 | ⚪ | Eliminare bootstrap/shutdown duplicati dopo parità |
| RST-0310 | ⚪ | Ritirare i tre embed.py dopo eliminazione dei mount |

Prima di migrare: conteggi per stato/anno, originali/hash, relazioni, saldi, backup ripristinabile, dry-run e rollback. Nessuna cancellazione di tabella basata soltanto sull'assenza di lettori in un adapter.

### Fase 4: autenticazione/PIN unici

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0401 | 🟢 | Autenticazione PIN admin canonica completata sui quattro domini: ERP PR #599 / `87efac99`, HR PR #600 / `b34a78cc`, Lotti PR #601 / `ab8c4afe`, Menu PR #602 / `1b6d396c`. Nessun fallback `ADMIN_PIN` in chiaro; lockout condiviso dove applicabile; CI/E2E/Produzione verdi |
| RST-0402 | 🟡 | Emissione sessione operativa HR/Lotti pubblicata con PR #603-#604; convergenza del verificatore in corso. RBAC comune per admin, amministrazione, HR, responsabile, HACCP, Menu e sola lettura ancora aperto |
| RST-0403 | 🟡 | Verifica HR/Lotti comune pubblicata; il portale personale HR richiede ancora il segreto HR. Se i segreti HR/Lotti coincidono, questa condizione da sola non distingue i domini. Target: un solo `ID dipendente` in HR/Lotti, con collegamento verificato dello storico HACCP e controlli server per dominio. Il login tablet passa per primo all'ID dipendente canonico; registri storici e altri campi restano da migrare |
| RST-0404 | ⚪ | Eliminare login amministrativo HR autonomo dopo cutover verificato |
| RST-0405 | ⚪ | Eliminare login applicativo Lotti autonomo, preservare identificazione tablet |
| RST-0406 | ⚪ | Eliminare JWT Menu autonomo, mantenere confini pubblico/privato |
| RST-0407 | ⚪ | PIN personale dell'utente/dipendente canonico |
| RST-0408 | ⚪ | Unica pagina Gestione PIN e accessi nel Gestionale |
| RST-0409 | ⚪ | Rimuovere router/login duplicati dopo verifica e revoca centrali |
| RST-0410 | ⚪ | Sostituire gestione manuale PIN_HASH_ADMIN in Render con rotazione centrale e bootstrap sicuro |

### Fase 5: fattura e ciclo interdominio

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0501 | ⚪ | Righe canoniche con unità, quantità, prezzi e provenienza |
| RST-0502 | ⚪ | Eliminare seconda fattura Lotti, preservare relazioni/proiezioni ricostruibili |
| RST-0503 | ⚪ | Mapping riga → prodotto/ingrediente, conferma degli ambigui |
| RST-0504 | ⚪ | Storico prezzi dalla riga canonica |
| RST-0505 | ⚪ | Ricezione attesa/confermata e inventario idempotente, senza doppio DDT/carico |
| RST-0506 | ⚪ | Lotto/tracciabilità solo con evidenze, assenze esplicite |
| RST-0507 | ⚪ | Ricette riferite agli ingredienti canonici |
| RST-0508 | ⚪ | Food cost/disponibilità con rese e conversioni verificate |
| RST-0509 | ⚪ | Coda da_mappare per righe sconosciute |
| RST-0510 | ⚪ | Outbox atomica, ricevute per consumer, replay/lease/idempotenza |
| RST-0511 | ⚪ | Ritirare sync/copie ERP→Lotti dopo backfill e quadratura |
| RST-0512 | ⚪ | Eliminare gestionale_fatture.py quando non ha responsabilità vive |
| RST-0513 | ⚪ | Contabilità/IVA/debito/scadenzario dal documento unico quando applicabili |
| RST-0514 | ⚪ | Prima Nota: cash attestato, banca con prova, provvisori fuori saldo reale |
| RST-0515 | ⚪ | Completezza ciclo per dominio: riuscito/pendente/errore/non applicabile |
| RST-0516 | ⚪ | Errori e retry visibili in UI, non falso successo globale |

Accettazione: XML acquisito una volta, identità condivisa, conti/IVA/debiti corretti, nessun pagamento inventato, prezzi/ricezioni/lotti documentati, ricette esistenti aggiornate e pubblicazione Menu autorizzata. Reimport/riavvio senza duplicati, errore consumer persistente/ritentabile. Coprire servizi, merci, cespiti, note di credito, parziali e rettifiche.

### Fase 6: HR e cedolini

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0601 | ⚪ | Dipendente canonico con ID/stato rapporto unici |
| RST-0602 | ⚪ | Cedolino canonico versionato con originale |
| RST-0603 | ⚪ | Lettori HR/ERP sullo stesso repository |
| RST-0604 | ⚪ | Eliminare copie payslip/buste paga dopo confronto |
| RST-0605 | ⚪ | Cedolino → costo/debito/salari senza doppia registrazione |
| RST-0606 | ⚪ | TFR documentato o stima esplicita, non doppio accantonamento |
| RST-0607 | ⚪ | Acconti/saldo e bonifici collegati con prova bancaria |
| RST-0608 | ⚪ | Fascicolo personale con lo stesso ID documento |
| RST-0609 | ⚪ | Ferie/presenze/turni/richieste nell'ERP, permessi preservati |
| RST-0610 | ⚪ | Eliminare FastAPI autonoma HR |
| RST-0611 | ⚪ | Router HR nell'app principale |

Accettazione: stesso ID visibile da HR, fascicolo, salari, TFR e banca; reimport/riavvio/rettifica idempotenti; nessun dipendente legge documenti di un altro.

### Fase 7: Lotti nativo

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0701 | ⚪ | Router Lotti nell'app principale |
| RST-0702 | ⚪ | Eliminare bootstrap FastAPI Lotti autonomo |
| RST-0703 | ⚪ | Job HACCP nel coordinamento comune |
| RST-0704 | ⚪ | Operatori da HR, nessuna seconda anagrafica/PIN |
| RST-0705 | ⚪ | Fornitori condivisi, qualifica HACCP nel dominio specifico |
| RST-0706 | ⚪ | Catalogo prodotti/ingredienti unico |
| RST-0707 | ⚪ | Inventario coerente con ricezioni/consumi |
| RST-0708 | ⚪ | Preservare lotti, temperature, sanificazione, allergeni, tracciabilità/richiami |
| RST-0709 | ⚪ | Eliminare tabelle duplicate dopo backfill e controllo dati esclusivi |

### Fase 8: Menu nativo

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0801 | ⚪ | Censire menu_* e responsabilità esclusive |
| RST-0802 | ⚪ | Prodotto/ricetta canonico pubblicabile |
| RST-0803 | ⚪ | Immagini con riferimenti unici, pubblico limitato alle pubblicabili |
| RST-0804 | ⚪ | Allergenici e versioni verificabili |
| RST-0805 | ⚪ | Sostituire menu_bridge con pubblicazione/proiezione controllata |
| RST-0806 | ⚪ | Qromo come import/export di transizione dopo riconciliazione e proprietà campi |
| RST-0807 | ⚪ | Ritirare client Menu duplicato |
| RST-0808 | ⚪ | Ritirare bootstrap FastAPI Menu autonomo |
| RST-0809 | ⚪ | Router pubblici/privati nell'app principale, confini espliciti |
| RST-0810 | ⚪ | Eliminare copie editabili concorrenti, preservare prezzi/visibilità |

### Fase 9A: fondamenta frontend

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0901 | ⚪ | Unica versione React compatibile |
| RST-0902 | ⚪ | Unico React Router e deep link coerenti |
| RST-0903 | ⚪ | Una toolchain Vite |
| RST-0904 | ⚪ | Client API/query comune e invalidazione cache |
| RST-0905 | ⚪ | Unico AuthProvider/RBAC |
| RST-0906 | 🟡 | Design system, form, errori, toast/dialog comuni. Revisione UX estesa a tutte le pagine e sezioni ERP, HR, Lotti e Menu: gerarchia, scopo, stati vuoti/errore, provenienza dei dati, leggibilità, focus/tocco e mobile. Partire dai componenti e flussi vivi, verificando ogni area; la singola vista Galatea non chiude questa voce |
| RST-0907 | ⚪ | PinModal nel vero shared, senza nuove copie |

### Fase 9B: porting

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0910 | ⚪ | HR in frontend/src/modules/hr |
| RST-0911 | ⚪ | Lotti in frontend/src/modules/lotti |
| RST-0912 | ⚪ | Menu admin/pubblico in frontend/src/modules/menu |
| RST-0913 | ⚪ | Link amministrativi interni, stessa sessione/layout |
| RST-0914 | ⚪ | Deep link/QR e redirect necessari preservati, non rimossi solo per età |

### Fase 9C: toolchain duplicate

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0920 | ⚪ | Eliminare frontend_hr dopo parità |
| RST-0921 | ⚪ | Eliminare frontend_lotti dopo parità |
| RST-0922 | ⚪ | Eliminare frontend_menu dopo parità |
| RST-0923 | ⚪ | Eliminare frontend_shared dopo migrazione |
| RST-0924 | ⚪ | build_frontends.sh a una sola build, aggiornare deploy |
| RST-0925 | ⚪ | Rimuovere CRA/CRACO, lockfile/dipendenze non richiesti |

### Fase 10: alias e collezioni fantasma

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-1001 | ⚪ | Eliminare progressivamente app.database.Collections |
| RST-1002 | ⚪ | Costanti/repository canonici, no nomenclature parallele |
| RST-1003 | 🟡 | KEEP/ARCHIVE/DELETE motivati; lettura warehouse_products eliminata e deroga ritirata nel rilascio |
| RST-1004 | 🟡 | Lista letture fantasma ridotta, non azzerata |
| RST-1005 | ⚪ | Ritirare endpoint migrazioni concluse, preservare ripristino/nuove installazioni |
| RST-1006 | ⚪ | Audit provenienza legacy: mai criterio unico di cancellazione |

### Fase 11: bootstrap e manutenzione

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-1101 | ⚪ | Censire marker, dipendenze e stato migrazioni |
| RST-1102 | ⚪ | One-shot in migrazioni versionate, utili anche al ripristino |
| RST-1103 | ⚪ | Togliere repair conclusi dal normale avvio |
| RST-1104 | ⚪ | Maintenance con dry-run e audit |
| RST-1105 | ⚪ | Lifespan limitato a connessioni, sicurezza, servizi/job e shutdown |

### Fase 12: ritiro sotto-app

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-1201 | ⚪ | Nessuna FastAPI HR produttiva autonoma |
| RST-1202 | ⚪ | Nessuna FastAPI Lotti produttiva autonoma |
| RST-1203 | ⚪ | Nessuna FastAPI Menu produttiva autonoma |
| RST-1204 | ⚪ | Rimuovere mount HR dopo migrazione percorsi |
| RST-1205 | ⚪ | Rimuovere mount Lotti dopo migrazione percorsi |
| RST-1206 | ⚪ | Rimuovere mount Menu dopo migrazione pubblico/privato |
| RST-1207 | ⚪ | Nessuna configurazione reintroduce fonti DB parallele |
| RST-1208 | ⚪ | Nessun bridge transitorio ERP→Lotti o Lotti→Menu |
| RST-1209 | ⚪ | Una build frontend |
| RST-1210 | ⚪ | Una identità/sessione e gestione accessi |
| RST-1211 | ⚪ | Un coordinamento job/lease e controlli |

## 6. Ordine di lavoro e criteri finali

**Priorità immediata:** consolidare accessi dati e PIN senza compromettere la Prima Nota; #573 e #575 sono già corretti e pubblicati.

Ordine generale: Prima Nota operativa → infrastruttura/identità canonica → sostituzione del legacy con codice nuovo → fatture/inventario → cedolini/HR → Lotti → Menu → frontend unico → ritiro compatibilità/sotto-app → audit finale. Le rimozioni isolate dimostrate non devono attendere l'intera rifondazione.

Prima di eliminare un percorso: verificare import/call/dynamic import, UI/job/API esterne e test; confrontare il contratto; implementare il sostituto canonico; migrare i chiamanti vivi; eliminare file/import/dipendenze inutili. Per i dati servono anche backup, referenzialità, saldi/quantità e ripristino provato.

Non riscrivere l'intero sistema in un unico big-bang. Riscrivere invece ex novo il singolo componente difettoso nella forma canonica target, una micro-tranche alla volta. Non creare copie temporanee senza owner e criterio di ritiro. Non cambiare conti, IVA, pagamenti, stock, PIN o permessi per far passare test. Non togliere commenti utili alle invarianti. Non sostituire un flusso rotto con un successo vuoto.

Chiusura finale: backend/frontend modulari realmente unificati; autorizzazioni corrette; originali preservati; fattura e cedolino canonici; consumer persistenti/idempotenti; report/Menu coerenti; nessun router orfano ingiustificato; startup snello; eliminazioni provate; test e produzione allineati. L'audit deve coprire tutte le quattro aree, non solo le viste ERP iniziali.

## 7. Misure di riduzione

**Confronto cumulativo e283400 → 7329ec7, solo app/: 393 righe aggiunte, 2.156 rimosse, riduzione netta 1.763 righe.** Include gli avanzamenti concorrenti integrati, non solo la #569. Esclude documentazione, workflow e test. Nessuna cancellazione di dati aziendali è stata eseguita in questa tranche.

| Indicatore | Baseline | Stato/traguardo |
|---|---|---|
| Bootstrap FastAPI produttivi | 4 | Target 1, esclusi server test; fusione ancora aperta |
| Frontend/build | 4 + shared | Target unico, non ancora raggiunto |
| Identità/sessioni | Ingressi multipli | Gestione centrale e ruoli separati ancora da completare |
| Accesso dati | Adapter multipli | Topologia reale da verificare, repository governati |
| Job/lease | Più scheduler | Coordinamento unico ancora da realizzare |
| Bridge | ERP→Lotti e Lotti→Menu | Da ritirare dopo sostituzione verificata |
| public_api.py | 26 route nell'audit iniziale | File eliminato, owner vivi preservati |
| Report/batch dismessi | Tre moduli principali | Eliminati; nessun filtro orfano sostitutivo |
| Letture fantasma | Lista del test runtime | In riduzione; esterni/read-only documentati |
| Schermate ERP | Catalogo iniziale 64 | Collaudi superati; estendere HR/Lotti/Menu e casi funzionali |
| Codice backend app/ | e283400 | -1.763 righe nette nel rilascio 7329ec7 |

Il conteggio dei tre moduli report/batch è 1.186 righe rimosse. Non aggiungerlo nuovamente alla riduzione cumulativa. Le rinomine o il taglio del piano Markdown non sono snellimento applicativo.

## 7-bis. Programma documentale, fiscale e audit v3 (piano approvato il 23/09/2026)

### Contesto

Piano approvato dal titolare il 23/09/2026, trascritto qui per intero perché nessuna sessione ne perda un pezzo. Copre quattro richieste: riorganizzazione Drive, PROMPT MASTER del 23/09 (audit v3 compreso), integrazione del Minisito fiscale, riconciliazione F24 ↔ banca. La sezione **I** dice dove sta ogni capitolo; la **H** l'ordine. Gli ID (`DRV-xx`, `RST-F24B`, `MINI-xx`, `AV3-xx`) sono stabili: il registro §8 li cita.

Il titolare vuole un Drive minimale, con un solo file per documento, relazioni solo nel DB e
una sola pipeline `DA_ELABORARE → archivio / DA_VERIFICARE / ERRORI` integrata con il gestionale.
Ha chiesto anche di verificare il PROMPT MASTER del 23/09. Sono stati fatti solo controlli in
lettura: repository (`main` = `1b7da72`), Supabase `lohczjdiawjryuopncwc`, Drive dalla radice GESTIONALE
(`GOOGLE_DRIVE_GESTIONALE_ROOT_FOLDER_ID`).

**Decisioni del titolare (23/09):**
1. Nuovo albero a 6 aree.
2. Una sola inbox, con un router che riconosce il tipo dal contenuto; la cartella `Elaborate` sparisce.
3. I duplicati byte-per-byte vanno nel **Cestino** Drive, mai cancellati in modo permanente.

### A. Il prompt master è corretto? Cosa è superato e cosa contraddice

| Punto del prompt | Stato reale | Esito |
|---|---|---|
| PR #683 aperta, tranche ricette da chiudere per prima | Fusa: `52422c2` su main, poi #684 e #685 | **Superato**: la sezione ricette non blocca più nulla |
| Collaudo su `impresasemplice.online` | Verificato il 23/09: `/lotti/api/health` risponde con lo stesso servizio Render (`srv-d92emmgjs32c738octfg`) e lo stesso commit `1b7da72` di `gestionalecloud.onrender.com` | **Dominio vivo**: CLAUDE.md e `tests/runtime/test_claude_md.py` lo davano per spento, corretti in DRV-00 |
| `PIANO_RISTRUTTURAZIONE.md` è la fonte canonica | Esiste ed è ammesso dal test; CLAUDE.md diceva «unici due documenti» | Corretto in DRV-00 |
| Handoff Drive: zero residui in pipeline, quarantena `DUPLICATI_ESATTI_2026-09-22` | Il protocollo (fermo al 17/09) conta 13.367 file in cartelle `DA ELABORARE/Elaborate/Errori`. La quarantena ha **replicato l'intero albero**: oltre 100 cartelle vuote `ERRORI/DA ELABORARE/ELABORATE` create il 22/09 alle 08:25 | Il protocollo è **stantio**; la quarantena è un nuovo labirinto |
| Indici `1AH7…`, `1Kn0…`, `1hm0…` | Esistono. In radice ci sono però anche i vecchi `INDICE_GESTIONALE.html` e `_drive_map.json` del 03/09, più un MANIFEST e un RIEPILOGO | Indici doppi: da ridurre a uno |
| «Non imporre una nuova tassonomia» | Il titolare ha scelto l'albero nuovo | Decisione del titolare: vince lui |
| Nessuna eliminazione definitiva | Coerente con la scelta del Cestino | OK |
| Sezione F24 «aggancio automatico quietanze ↔ banca» | Stessa richiesta del messaggio F24 del titolare: il motore esiste già in forma parziale | Coperta in **G** (RST-F24B), dentro il repository e non offline |
| Ordine audit v3: il motore Drive unico era al punto 10 | Il titolare lo porta in testa | Registrato qui, ordine in **H** |

### B. Debito tecnico: cosa esiste già, cosa manca

**Già fatto (da riusare, non da rifare)**

| Componente | Dove |
|---|---|
| Inventario completo di Drive, con stato `attivo/rimosso`, `duplicato_di`, guardie anti-DELETE | `gestionale.protocollo_drive` (`app/services/drive_protocollo.py`, `supabase/migrations/20260914180000_protocollo_drive.sql`) |
| Endpoint duplicati e quarantena | `app/routers/documenti.py:219-322` |
| Download Drive unico | `app/services/drive_download.py:12` (`scarica_bytes`) |
| Cartelle del ciclo di lavorazione | `app/services/drive_lifecycle_tree.py` |
| Tabella dei canali | `drive_documenti_ingest.CANALI:36-100` |
| Documenti fiscali con sha256, versioni, pagine e versione del parser (`fiscal-ingestion-v2-ocr`) | `app/services/fiscal_evidence.py`, `fiscal_document_ingestion.py` |
| Grafo relazioni generico | `app/services/entity_relations.py` |
| `drive_file_id` + hash sulle fatture | 1.395 su 1.457 |
| `drive_file_id` + hash su F24 e quietanze | 100% |
| Originali F24 e cedolini aperti per `drive_file_id` | `f24_originale.carica_originale`, `cedolino_originale.carica_originale` |

**Da fare (misurato oggi)**

| # | Debito | Numeri |
|---|---|---|
| D1 | Motori paralleli: fatture, cedolini, corrispettivi, quietanze, F24, estratti, documenti | 7 motori di ingest, 21 moduli chiamano Drive, 13 `build("drive")`, 6 costruttori di credenziali più il monkeypatch in `services/__init__.py:21-99`, 4 funzioni di download, 9 di listing |
| D2 | Il registro non ha sha256, stato di elaborazione, parser, errore, tentativi, confidenza | `protocollo_drive`: 14.325 righe, solo md5; ultimo giro 17/09 (`PROTOCOLLO_DRIVE_ENABLED=false` per la RAM) |
| D3 | Relazioni sparse | Solo 2.399 file su 14.325 collegati; 0 per fatture e corrispettivi. `collegamento_*` e i campi ad hoc di `documents_inbox` non stanno in `entity_relations`, che non conosce il tipo `documento` |
| D4 | Record senza originale | `cedolini` 3.256 con 0 `drive_file_id` e 0 hash; `verbali_noleggio` 105 senza nulla; `corrispettivi` 616 senza `drive_file_id`; `documents_inbox` 910 su 4.132 |
| D5 | Il Drive id ha cinque nomi | `drive_id`, `drive_file_id`, `source_document_id`, e `drive_document_id` che non è nemmeno un id Drive (è l'ID dell'indice Excel) |
| D6 | «Apri originale» rotto | `/api/documenti/documento/{id}/download` (`documenti.py:1071`) e `/api/fiscal/documents/{id}/content` (`fiscal_control.py:588`) danno 404 sui documenti presenti solo su Drive. `/api/download` serve `./downloads`, mai popolata |
| D7 | Indice Excel legacy ancora letto | `drive_document_index.py` (`INDICE_DOCUMENTALE_DRIVE.xlsx`), usato da Situazione fiscale e da due upload |
| D8 | Configurazione | Circa 20 variabili di cartella, solo 5 in `render.yaml`. Folder ID cablati come default (dichiarazioni, radice fiscale, radice indice). Variabili morte: `DRIVE_PRESENZE_FOLDER_ID`, `DRIVE_NOLEGGIO_FOLDER_ID`. `sync_incremental` mai chiamato |
| D9 | Errori senza traccia per file | Nessun codice errore né contatore tentativi per file; gli errori degli estratti conto non vengono salvati |
| D10 | Labirinto Drive | Mirror di quarantena; 89 gruppi md5 duplicati nel protocollo; aree non previste dal target: `FOTO E IMMAGINI` (1.346 file), `_GESTIONALE_APP`, `PROGETTI`, `07_CONTRATTI`, `11_DOCUMENTI_SOCIETARI` |

### C. Architettura target

**Albero Drive** (sotto la radice GESTIONALE):

```
00_PIPELINE/     DA_ELABORARE  DA_VERIFICARE  ERRORI
01_FISCALE/      AGENZIA_ENTRATE  AGENZIA_ENTRATE_RISCOSSIONE  F24  DICHIARAZIONI_FISCALI
02_CONTABILITA/  FATTURE_RICEVUTE  CORRISPETTIVI  BANCA  BONIFICI  PAGOPA  PAYPAL
03_PERSONALE/    CEDOLINI  DOCUMENTI_PERSONALE
04_VEICOLI_E_VERBALI/  VERBALI  PAGAMENTI_VERBALI  DOCUMENTI_VEICOLI
05_EXCEL_E_EXPORT/
90_ARCHIVIO_LEGACY/   (solo durante la migrazione, ogni elemento con motivazione)
```

- Archivi **piatti**: anno, fornitore, dipendente e periodo stanno nel DB.
- Nome canonico `AAAA-MM-GG__TIPO__SOGGETTO__IDENTIFICATIVO.ext`, applicato con `files.update`: lo stesso Drive ID viene conservato. Il nome originale resta nel registro.

**Registro documentale unico = `gestionale.protocollo_drive`, esteso.** Si estende la tabella esistente invece di crearne una nuova: è l'unico inventario completo, relazionale e protetto dalle cancellazioni. La migrazione aggiunge:
- `sha256`, `nome_originale`
- `tipo`, `sottotipo`, `anno_fiscale`, `data_documento`
- `stato_elaborazione` (`DA_ELABORARE | IN_ELABORAZIONE | ELABORATO | DA_VERIFICARE | ERRORE`)
- `parser`, `parser_versione`, `confidenza`
- `errore_codice`, `errore_motivo`, `tentativi`, `ultimo_tentativo`, `verificato_il`

Rinomina `drive_id` → `drive_file_id`, così il nome è uno solo in tutto il sistema. `fiscal_documents` resta per versioni, pagine ed evidenze fiscali e punta al `drive_file_id`.

**Relazioni:** un solo grafo, `entity_relations`, con il nuovo tipo sorgente `documento` (chiave `drive_file_id`) verso fattura, fornitore, F24, quietanza, cedolino, dipendente, movimento, verbale, veicolo, pagamento, dichiarazione. Stati `CONFERMATA | CANDIDATA | DA_VERIFICARE | RIFIUTATA`. `collegamento_tipo/id` e i campi ad hoc vengono migrati lì e poi tolti.

**Motore unico** `app/services/drive_pipeline.py` più il client unico `app/services/drive_client.py`, che concentra credenziali, list, get, download, move e trash. I passi:
1. elenca `00_PIPELINE/DA_ELABORARE`, paginato, con tetto per giro; i rinviati non bloccano la coda;
2. scarica e calcola lo SHA-256;
3. fa l'upsert nel registro;
4. un hash già noto è un doppione: il file va nel Cestino dopo la verifica dei byte, e la provenienza entra nel registro;
5. il **router per contenuto** smista così:
   - XML `FatturaElettronica` → `process_xml_bytes`
   - `DatiCorrispettivi` → `ingest_corrispettivo_parsed`
   - F24 e quietanza → `importa_modello_bytes` / `importa_quietanza_bytes`
   - cedolino → parser cedolini
   - dichiarazioni, AdE, AdER → `FiscalDocumentIngestionService` / `classify_document`
   - verbale → `process_verbale_document`
   - estratto conto → riconoscitori nell'ordine Nexi → PayPal → mutuo → banca
   - xls/csv → `05_EXCEL`
6. scrive le relazioni;
7. **solo dopo la persistenza verificata** sposta il file nell'archivio dell'area (stesso ID) e imposta `ELABORATO`;
8. se il router non è sicuro → `DA_VERIFICARE`, con i candidati; se c'è un guasto → `ERRORI`, con codice, motivo e tentativi;
9. `POST /api/documenti/pipeline/riprova` rimette in coda a lotti, con `dry_run`.

**Apertura unica dell'originale:** `GET /api/documenti/originale/{drive_file_id}`, autenticata e in streaming tramite `drive_download`, più la risoluzione `record → relazione → drive_file_id`. Tutte le pagine passano da lì.

### D. Micro-tranche

Ogni tranche segue lo stesso ciclo: una PR, test, `git diff --check`, revisione avversariale, merge **uno alla volta** (ogni merge ricarica 77.000 righe), `/api/health` sul commit, verifica live. Ognuna entra in PIANO come `RST-DRV-xx`.

| ID | Tranche | Contenuto | Criterio di chiusura |
|---|---|---|---|
| DRV-00 | Riallineamento documenti | Risolvere le contraddizioni di A in CLAUDE.md e PIANO. Registrare le 3 decisioni, il nuovo albero e il programma DRV | Test `test_claude_md` verde |
| DRV-01 | Client Drive unico | `drive_client.py` con un solo costruttore di credenziali; migrare i 21 moduli; eliminare il monkeypatch, i 4 download e i 9 listing duplicati. Nessun cambio di comportamento | Suite `tests/documenti`, `fatture`, `fiscale`, `hr` verdi; 1 solo `build("drive")` |
| DRV-02 | Registro esteso | Migrazione `protocollo_drive` (colonne più rinomina). Sync del protocollo in streaming e a pagine, perché oggi carica tutto in RAM; poi riaccensione di `PROTOCOLLO_DRIVE_ENABLED`. Backfill sha256 in background a lotti, con cursore in `sistema_stato` | Un giro completo senza superare la RAM; sha256 ≥ 99% |
| DRV-03 | Relazioni documentali | Tipo `documento` in `entity_relations`. Backfill da `drive_file_id` di invoices, F24, quietanze, inbox ed estratti e da `collegamento_*`. Cedolini: impronte già note, `drive_file_id` scritto sul cedolino; i casi ambigui vanno in `DA_VERIFICARE`. Prima `dry_run`, poi autorizzazione | Seconda esecuzione: 0 nuove relazioni |
| DRV-04 | Apertura originale unica | Nuovo endpoint e un componente frontend unico; migrare `documenti.py:1071`, `fiscal_control.py:588`, `/api/download` e il visualizzatore; togliere `drive_document_index` dai tab di Situazione fiscale | Ogni pagina che apre un documento lo apre davvero (test E2E più prova live) |
| DRV-05 | Motore pipeline e router | `drive_pipeline.py` su `00_PIPELINE`, con un job scheduler e una pagina «Documenti > Drive» (stato, coda, ultimo giro, errori, riprova). Test sul router per ogni tipo, compreso l'ambiguo | Doppione reinserito → `nuovi=0`; file rotto → ERRORI con codice |
| DRV-06…12 | Migrazione di un canale per PR | Ordine: fatture (quadratura e ricostruzione leggono il **registro**, non più `Elaborate/<anno>`), F24 e quietanze, dichiarazioni/AdE/AdER, cedolini e bonifici, corrispettivi (più il nuovo target di `sync_rt_to_drive.py`, variabile locale `RT_DRIVE_INBOX`), estratti/PayPal/PagoPA, verbali. Ogni PR **elimina** il vecchio modulo, il suo job e la sua variabile | Stessi file di prova, stesso esito; 0 riferimenti residui |
| DRV-13 | Spostamento fisico per area | Manifest in simulazione (id, percorso vecchio → nuovo, nome, sha256) → **autorizzazione** → `files.update` (stesso ID) → il registro vede il nuovo percorso | Seconda esecuzione: 0 spostamenti |
| DRV-14 | Duplicati | Gruppi SHA-256 con confronto dei byte. Si escludono i file referenziati o prima si fanno convergere le relazioni sul canonico; poi Cestino. Log nel registro (`stato='duplicato_cestinato'`, `duplicato_di`, vecchi id). Gruppi md5 senza sha256 uguale → `DA_VERIFICARE` | 0 duplicati non giustificati |
| DRV-15 | Excel | Tutto in `05_EXCEL_E_EXPORT` piatto; `sottotipo` nel DB tramite le intestazioni dei fogli; se sconosciuto → `DA_VERIFICARE` | — |
| DRV-16 | Pulizia legacy | Cestinare le cartelle vuote del mirror di quarantena (solo dopo un listing che provi 0 file). Gli indici vecchi e le aree fuori target (`FOTO E IMMAGINI`, `_GESTIONALE_APP`, `PROGETTI`, `07`, `11`) vanno riclassificati o in `90`, con motivo. Togliere i folder ID cablati, le variabili morte, `sync_incremental`, `drive_pulizia` per anno e `drive_document_index` | 0 folder ID obsoleti |
| DRV-17 | Integrità ed E2E | `GET /api/documenti/integrita` calcola gli 11 indicatori «= 0» del brief (file Drive senza record, record con ID inesistente, bloccati, ERRORI senza errore, doppia presenza…). E2E con documenti reali dei 10 tipi, compreso il reinserimento di un documento già importato. Report PRIMA/DOPO | Tutti gli indicatori a 0, salvo esclusioni motivate |

**Baseline PRIMA** (da riconfermare in DRV-02 con un giro fresco):
- 18 cartelle in radice più 7 file indice/manifest;
- profondità massima 9;
- 14.325 file nel protocollo (dato del 17/09);
- 89 gruppi md5 duplicati;
- 2.399 file collegati;
- 13.367 file in cartelle di lavorazione (dato del 17/09).

**Cancelli di sicurezza:**
- Ogni spostamento, cestinamento o backfill in produzione richiede, al momento dell'azione: manifest, conteggi prima, `dry_run` e autorizzazione esplicita.
- Nessun `git add -A`.
- Render: all'avvio dell'esecuzione serve il workspace (lo sceglie il titolare). Le variabili nuove e quelle da togliere vanno in `render.yaml` con `sync: false`.

### E. Verifica

1. Locale: `python -m pytest -q tests/documenti tests/fatture tests/fiscale tests/hr tests/runtime`, poi i test nuovi:
   - router per tipo;
   - idempotenza (secondo giro a 0);
   - apertura originale;
   - integrità.
2. Frontend: `yarn test && yarn build` in `frontend/`.
3. CI verde, merge, `/api/health` e `/lotti/api/health` con il commit esatto.
4. Live, in sola lettura: SQL su `protocollo_drive` / `entity_relations` per gli indicatori; Drive MCP per controllare cartelle e percorsi.
5. E2E reali, solo con autorizzazione: un file per tipo in `00_PIPELINE/DA_ELABORARE`, controllo di registro, relazione, archivio e apertura dal gestionale; poi reinserimento dello stesso file → `nuovi=0`, file nel Cestino.
6. Produzione: https://gestionalecloud.onrender.com

### F. Integrazione del «Minisito fiscale» (programma RST-MINI)

**Decisioni del titolare (23/09):**
- Archivio = albero a 6 aree: il classificatore del minisito diventa il router di DRV-05 e i suoi tipi vanno in `tipo/sottotipo`.
- Regola 1–10 solo come **proposta** (candidato più conferma manuale prioritaria); la regola del 25 resta per la competenza.
- Mappa, dedup e piano in PIANO, niente `docs/*.md`. Una PR per tranche, **unita su main solo dopo l'OK esplicito** del titolare.
- Pacchetto completo e estratti conto 2019–2024 **caricati dal titolare su Drive**.

**Punti del prompt minisito corretti dai fatti:**
- Non esistono `PROMPT_MASTER`, `AGENTS.md`, `REGOLA_FISSA_ATTESE` né `docs/`.
- La persistenza è Supabase, non Drive/Sheets.
- `impresasemplice.online` è vivo (vedi A), non spento.
- Il branch `claude/integrazione-indice-relazionale` non esiste: si lavora sul branch designato.

**Riuso obbligatorio, niente copie accanto.** Ogni funzione del minisito va nel modulo che c'è già:

| Minisito | Modulo del repository |
|---|---|
| `extract_lib`, `build_manifest`: F24 e quietanze AdE | `f24_parser.py` / `parser_f24.py` → `f24_canonico.py`, `quietanze_import.py` |
| `extract_lib`, `build_manifest`: LIPE | `lipe_parser.py` + `lipe_deposito.py` |
| `extract_lib`, `build_manifest`: dichiarazioni, 36-bis/54-bis, compliance | `fiscal_document_ingestion.py` |
| Codici tributo, TEFA/TEFN/TEFZ | `codici_tributo_f24.py` + `codici_tributo_db.py` |
| `build_crossref`: LIPE↔F24, IRAP, IVA annuale, 54-bis | `/api/iva/confronto-commercialista`, `f24_controllo_incrociato.py` |
| `build_crossref`: alert 6099 e periodo | come sopra |
| Cedolini (3 template, NETTO DEL MESE, varianti, rettifiche, 97 LUL `null`) | `hr_cedolini_lettura.py`, `cedolini_canonico.py`, stati di `stati_netto.py` |
| Bonifici (CRO, 1–10 come candidato, `confermato_manuale`) | `associa_bonifici_stipendi`, `stipendi_bonifici.py`, `bonifici_pdf_ingest.py` |
| Indice relazionale | vista su `entity_relations` (DRV-03) con export xlsx/csv/json |
| Protocollo (1.125 righe, 1.060 file, OCR, ricerca, allocazioni dubbie) | registro `protocollo_drive` con `accounting_scope=personal_family`, `accounting_excluded=true`; ricerca in `drive_protocollo.cerca()` |
| `classifica_contenuto`, `piano_riclassificazione` | router di DRV-05 |

**Dedup F24 a due livelli** (decisione da riportare in PIANO):
- hash identico = duplicato certo;
- stesso protocollo con hash diverso = «duplicato per protocollo, da confermare»;
- protocollo illeggibile con tributi identici = candidato.

Mai sommati due volte.

| ID | Tranche | Dipende da |
|---|---|---|
| MINI-00 | Lettura del pacchetto da Drive. Mappa funzione→modulo in PIANO. Golden JSON (`manifest_final`, `cedolini_canonici`, `protocollo_data`) nella cartella dei test come dati di regressione, **senza dati personali in chiaro** oltre quelli già nel repository privato | pacchetto caricato |
| MINI-01 | Schemi: campo `fonte` obbligatorio e `stato` esplicito su documento fiscale, cedolino, ricevuta bonifico, riga di protocollo, alert (estensione degli schemi esistenti) | DRV-02 |
| MINI-02 | Parser F24/LIPE/dichiarazioni allineati ai golden; ogni differenza spiegata in PIANO. Fallback pikepdf/OCR | MINI-01 |
| MINI-03 | Cedolini: 3 template, varianti, rettifiche; i 97 LUL restano `NETTO_NON_PRESENTE_O_NON_LEGGIBILE` con un TODO nel codice | MINI-01 |
| MINI-04 | Incroci e alert: LIPE↔F24, IRAP, IVA annuale, 54-bis per codice e anno, `POSSIBILE_COMPENSAZIONE_6099`, `POSSIBILE_ERRORE_PERIODO_IMPUTAZIONE`, file rotti; guardia aritmetica | MINI-02 |
| MINI-05 | Bonifici stipendio: CRO visibile, candidato 1–10, avviso multi-dipendente, `confermato_manuale` | MINI-03 |
| MINI-06 | Indice relazionale ed export | DRV-03, MINI-05 |
| MINI-07 | Protocollo personale e familiare: import del registro, OCR, ricerca AND con snippet («tari enzo 2023», «cosap 2019», verbale, targa, cartella), ponte solo informativo verso la contabilità | DRV-05 |
| MINI-08 | Frontend: viste 1.6 come route React stabili (`/fiscale/f24/:id`, `/fiscale/tributi/:codice`, `/personale/cedolini/:id`, `/protocollo/:id`), filtro anno globale, importo versato → apre la quietanza tramite DRV-04, legenda delle regole. E2E Playwright sui 4 casi del prompt | MINI-04…07 |

**Aperti che non si risolvono inventando:**
- i 97 importi LUL;
- 6 quietanze danneggiate da riscaricare;
- quietanze bancarie 2018–2020 in formato banca;
- IVA precompilata: da chiedere prima di scaricare.

### G. Riconciliazione F24 ↔ banca a livelli (RST-F24B)

**Stato reale:**
- `app/services/f24_bank_reconciliation.py::riconcilia_f24_tributi_banca` esiste già, ma produce solo match **certi e univoci** su `f24_unificato`.
- `quietanze_f24`: 459 righe (2019–2026), 0 collegate a un movimento.
- `estratto_conto_movimenti`: 2.017 righe, solo dal 03/02/2025 al 24/08/2026; 32 con causale fiscale, 3 riconciliate.
- Senza gli estratti 2019–2024 la maggior parte delle quietanze finirà in «nessun match» **per mancanza di estratto**: va detto così, non come pagamento mancante.

**Estensione dello stesso motore, niente script paralleli:**
- **Un solo esito per coppia**, con `livello` e `motivazione` (importo, date e causale confrontati, con la loro fonte):
  - `CERTO` → riconciliato: importo esatto, data entro 2 giorni lavorativi, causale F24/I24/Delega/Erario/Agenzia oppure CRO/TRN coincidente;
  - `PROBABILE` → DA_VERIFICARE: importo e data uguali, causale generica;
  - `PARZIALE` → DA_VERIFICARE, con la differenza in euro (soglia configurabile, default 5 €);
  - `NESSUN_MATCH` → alert, con la verifica esplicita «estratto del periodo presente sì/no»;
  - `MOVIMENTO_ORFANO` → «probabile quietanza da riscaricare».
- Solo `CERTO` scrive il pagamento. Gli altri livelli scrivono una relazione `CANDIDATA` o `DA_VERIFICARE` in `entity_relations`, **mai** un pagamento: resta la regola «quietanza e modello non sostituiscono la prova bancaria».
- Quietanza e modello restano entità distinte: il match usa il totale addebitato (debito meno compensazione) della quietanza e si aggancia all'F24 per protocollo.
- **Estrazione movimenti**: nessun nuovo parser se il formato è già supportato (`estratto_conto_bpm_parser.py`, riconoscitori Nexi/PayPal/mutuo/banca). Un formato nuovo si aggiunge al motore estratti esistente, dopo aver visto un file reale.
- **Vista**: sezione «Riconciliazione F24» in `/riconciliazione`, con filtro anno/conto, badge con testo per livello, link a quietanza ed estratto tramite DRV-04, e l'elenco dei periodi senza estratto.
- **Tono**: solo fatti e discrepanze, «da verificare con il commercialista».
- **Test**: un caso per ogni livello, più ambiguità (due F24 con lo stesso importo), festivi nei 2 giorni lavorativi, idempotenza (seconda esecuzione a 0).

### H. Ordine d'esecuzione complessivo

1. **DRV-00**: CLAUDE.md, il test e **tutto questo piano** (A–K) scritti in PIANO, così ogni nuova chat li trova nel repository.
2. **AV3-01** (errori, Riparazioni, stato-fonti) e **AV3-10** (allergeni: obbligo di legge).
3. **AV3-02** (estratti conto), poi **RST-F24B** (riconciliazione F24 a livelli).
4. **DRV-01…04** (client, registro, relazioni, apertura originale), che assorbono anche AV3-07 per la parte indice.
5. **AV3-06** (F24 unico e posta), poi **MINI-00…06**, appena il pacchetto è su Drive.
6. **AV3-03** e **AV3-08** (IVA e veicoli), dopo la conferma del commercialista; poi AV3-04 e AV3-05.
7. **DRV-05…12** (pipeline e canali), poi **AV3-09**, **MINI-07** e **MINI-08**.
8. **DRV-13…17** (spostamenti, duplicati, pulizia, integrità).
9. **AV3-11…15** (FIFO, residui ricette, codice morto, route, sicurezza).

Ogni PR si unisce su main **solo dopo l'OK esplicito del titolare**.

### I. Copertura di TUTTI i prompt ricevuti

| Prompt | Capitolo | Dove sta nel piano |
|---|---|---|
| 1. Riorganizzazione Drive (messaggio del 23/09) | Tutti i 13 punti | A–E (programma DRV) |
| 2. PROMPT MASTER | Metodo, micro-tranche, cancelli di sicurezza, checkpoint, report finale | Regole trasversali (vedi J) |
| 2. PROMPT MASTER | Drive, archivio documentale, importazione unica, hash/dedup | DRV |
| 2. PROMPT MASTER | Archivio Relazionale nativo, componente «documenti collegati» | DRV-03, DRV-04, MINI-06 |
| 2. PROMPT MASTER | Tranche ricette (#683) | Chiusa; i residui sono in AV3-12 |
| 2. PROMPT MASTER | Audit v3 (11 famiglie) | **K** (programma AV3), finora mancante |
| 2. PROMPT MASTER | Pacchetto PartenoPay storico | AV3-09 |
| 2. PROMPT MASTER | Posta/PEC, Learning Machine | AV3-06 |
| 2. PROMPT MASTER | Audit route e navigazione, API, osservabilità | AV3-14 |
| 2. PROMPT MASTER | Sicurezza, MFA, RBAC | AV3-15 |
| 2. PROMPT MASTER | Specifica F24 ↔ banca | G |
| 3. Minisito fiscale | Tutto | F (programma MINI) |
| 4. Riconciliazione F24 ↔ banca | Tutto | G (RST-F24B) |

### J. Regole trasversali del PROMPT MASTER (valgono per ogni tranche)

- **Avvio di ogni sessione**:
  - fetch;
  - confronto fra `HEAD`, worktree, `origin/main`, PR aperte e commit servito (`/api/health`);
  - lettura di PIANO;
  - checkpoint iniziale.
- **Checkpoint dopo ogni tranche**:
  - obiettivo, stato iniziale, causa reale, soluzione;
  - file eliminati o migrati;
  - dati toccati con conteggi prima/dopo, backup, `dry_run`, rollback;
  - test distinti per tipo;
  - PR, CI, merge, deploy, commit servito;
  - voci `DA_VERIFICARE`;
  - aggiornamento di PIANO.
- **Esiti ammessi**: `VERIFICATO`, `PARZIALE`, `NON_ESEGUITO`, `NON_VERIFICABILE`, `ERRORE`. Mai «completato» o «funzionante» senza la prova corrispondente.
- **Scritture reali in produzione**: ambiente e record identificati, conteggi prima, `dry_run`, backup con rollback provato, autorizzazione al momento. Un backup non provato si dichiara `RIPRISTINABILITÀ NON VERIFICATA`.
- **Legacy**: non si aggiungono guardrail o whitelist permanenti. Un adattatore transitorio ha proprietario e condizione di ritiro.

### K. Backlog audit v3 (programma AV3) — da riconfermare sui dati prima di ogni tranche

I numeri qui sotto sono la baseline dichiarata dall'audit del 22/09, **non** ancora prove. Ogni tranche comincia rimisurandoli.

| ID | Famiglia | Contenuto essenziale | Cancello |
|---|---|---|---|
| AV3-01 | Contratto errori | `error_handler` con `code/message/details/correlation_id` più `detail` transitorio; `messaggioErrore(e)` unico in `frontend/src/api.js`; `PannelloRiparazioni` e `/prima-nota/stato-fonti` con prefisso `/api`; test di contratto esteso ai percorsi senza `/api` | nessuno (solo codice) |
| AV3-02 | Estratti conto | I rinviati pre-2026 non bloccano la coda; test di regressione. Precondizione per G con gli estratti 2019–2024 | nessuno |
| AV3-03 | IVA | Servizio unico `classifica_e_calcola_iva` (centro di costo → % → campi IVA → stato), chiamato da handler, ricostruzione, endpoint singolo e massivo; job su `da_ricalcolare`; regole 100/40 per veicolo/50 telefonia/«da confermare». Backfill di 786 fatture senza IVA e 925 senza centro di costo; poi `registra-pregresso` | conferma del commercialista sulle percentuali; autorizzazione per il backfill |
| AV3-04 | Scadenze e alert | Togliere gli scrittori del `+30` (`handlers/scadenziario.py`, `fatture_estera_verifica.py`) e azzerare `scadenziario_fornitori`. Alert: bottone «Risolvi» con stato terminale coerente e link al record; `CED_DUPLICATO` solo per hash (≈2.066 falsi); chiusura per ID di ≈827 `FAT_DA_PAGARE_SCADUTA` | autorizzazione modifica massiva |
| AV3-05 | Libro giornale | `registra_pagamento(operation_id)` unico per cassa, banca, salari e F24; riportare gli scrittori paralleli su `scritture_contabili`; Bilancio da `movimenti_contabili`; bottone «Senza metodo» sul vocabolario unico | — |
| AV3-06 | F24 da email e F24 unico | `post_download_pipeline` delega a `importa_modello_bytes` / `importa_quietanza_bytes` (bug `parsed["success"]`, modelli passati al parser quietanze). Un solo ingresso F24 (oggi 6 parser e 14 scrittori). Dedup per identità business; scadenze dal codice tributo (anche `FiscaleSentinella`). Riconciliazione F24/banca senza «primo della lista». Posta/PEC idempotente, Learning Machine solo propositiva | — |
| AV3-07 | Situazione fiscale | 4 tab fuori dal vecchio indice Excel (coincide con DRV-04 e DRV-16). «Apri dichiarazione» per `drive_file_id`; campi strutturati delle dichiarazioni. LIPE: `lipe_verifica` sostituita dal confronto canonico, «Riapri» con motivo, UI decisioni IVA, «Notifica email» vera o rimossa | — |
| AV3-08 | Veicoli, fringe, addebiti | Anagrafica veicoli unica con storico assegnazioni (GW980EP Arval → Antonietta; HB411GV Leasys e GX037HJ ALD → amministratori; GG782PN cessata tolta dal codice); tipo d'uso → IVA/IRES per veicolo. Fringe benefit letto dal cedolino. Righe dei noleggiatori classificate per riga (bollo, multa rinotificata, rinotifica, penale). Dedup delle fatture ALD/Arval/Leasys per `content_hash_canonico`. Entità `addebiti_busta` → riepilogo presenze → verifica sul cedolino | percentuali da confermare col commercialista |
| AV3-09 | Verbali e PartenoPay | I 105 verbali ricostruiti dal PDF (`process_verbale_document`), con job una tantum con anteprima; un solo collegamento verbale→fattura; `data_violazione` unica; `driver_alla_data` unica; fix `/` nei numeri, IUV, `upload-quietanza`. Pacchetto PartenoPay: verifica di hash e manifest, import tramite pipeline, seconda esecuzione a 0 | autorizzazione import |
| AV3-10 | Ricette → Menu allergeni | `allergeni_confermati` non perso al salvataggio; ponte Menu a ogni scrittura allergeni rispettando «nessuno» confermato (108 prodotti su 325 hanno allergeni: obbligo di legge, **priorità alta**) | — |
| AV3-11 | FIFO e costi | Un motore di costo, un FIFO atomico con `operation_id`, conversione KAR/confezioni, `prodotto_dizionario_id` stabile, `q.b.` esplicito, prezzo di vendita unico, Salva Menu admin reale o rimosso | — |
| AV3-12 | Residui ricette (ex #683) | Riconfermare dopo #682 (descrizioni già live?): procedimenti leggibili, mancanti solo da fonti tracciate, 36 collegamenti Menu per ID esatto, nessuna pubblicazione implicita | autorizzazione scritture |
| AV3-13 | Codice morto | 1.128 route senza chiamanti frontend: rimozione una responsabilità per commit, solo dopo la verifica di scheduler, script, agent e webhook (elenco candidati del prompt) | — |
| AV3-14 | Route e navigazione | Inventario generato dal router reale, `/mappa-gestionale` automatica, classificazione FUNZIONANTE/404/…, prove sugli URL reali (anche `impresasemplice.online`, che è vivo); osservabilità import → parser → DB → relazioni | — |
| AV3-15 | Sicurezza | Sessioni, CSRF, rate limit, lockout PIN, MFA vera (PIN + token dallo stesso PIN non è MFA), autorizzazioni su HR e finanza, niente segreti nei log | decisione del titolare sul fattore MFA |

## 8. Registro avanzamento

| Data | ID/perimetro | Stato | Commit/PR e prova |
|---|---|---|---|
| 2026-09-23 | RST-DRV-00-PIANO-UNICO | 🟢 | [PR #687](https://github.com/ceraldicontabilita/GestionaleCloud/pull/687), merge `5686948a7bc0fb246051a6421271528c3fb100cc`: piano A–K trascritto in §7-bis; CLAUDE.md e `tests/runtime/test_claude_md.py` riallineati (`impresasemplice.online` vivo, tre documenti ammessi). CI (Test backend, frontend ERP, E2E isolato, audit layout) verde; `/api/health` e `/lotti/api/health` su entrambi i domini servono il merge esatto |
| 2026-09-23 | RST-AV3-01-CONTRATTO-ERRORI | 🟢 | [PR #688](https://github.com/ceraldicontabilita/GestionaleCloud/pull/688), merge `106c66479cd0a7f4564a2e588a584b88af53efe5`: contratto errori `code/message/details/correlation_id` con `detail` invariato e intestazioni conservate; helper `messaggioErrore`; Riparazioni e `/api/prima-nota/stato-fonti` sotto `/api`; hook `useStatoFonti` con errore visibile; test di contratto esteso (fallisce sul codice precedente). Suite locale 4.688 backend e 336 frontend verdi, CI verde, `/api/health` serve il merge esatto. Residuo aperto (AV3-01b): il middleware di autenticazione risponde ancora a mano con `{detail}` fuori dal contratto |
| 2026-09-23 | RST-AV3-10-ALLERGENI-MENU | 🟢 | [PR #689](https://github.com/ceraldicontabilita/GestionaleCloud/pull/689), merge `ec2ff16e7c209337fe24be575ae31f8554671619`: il ponte pubblica la lista vigente anche se vuota («nessun allergene» confermato), la modifica della ricetta conserva la conferma manuale finche' l'insieme degli ingredienti non cambia, conferma dalla scheda e rilevamento massivo riallineano il Menu. 4 test nuovi (falliscono sul codice precedente), 656 test Lotti e CI verdi; `/api/health` e `/lotti/api/health` su entrambi i domini servono il merge esatto. Dati live: 328 ricette tutte da confermare, nessuna vittima attuale. Aperto fuori dal codice: 323 prodotti Qromo, solo 108 con allergeni |
| 2026-09-23 | RST-AV3-01B-ERRORI-MIDDLEWARE | 🟡 | Il middleware di autenticazione rispondeva a mano `{detail}` in 16 punti, fuori dal contratto (verificato live dopo #688). `errore_http` unico in `error_handler.py`: stesso `detail`, `code`, `message` italiano, `correlation_id`, intestazioni conservate. Suite backend 4.696 verde. In attesa di PR, CI e OK del titolare |
| 2026-09-21 | PLAN-0001 | 🟢 | Piano iniziale, audit 8cf52bd; storia in Git |
| 2026-09-21 | PLAN-0002 | 🟢 | Priorità Prima Nota e PIN centrale aggiunte |
| 2026-09-21 | FASE-0A-LIVE | 🟢 | #566, b71f62d; precedente registro Produzione 35543104234; non qualifica tutti i casi contabili |
| 2026-09-21 | RST-0001/0003/0005 | 🟢 | e283400; Produzione 35553261218 superata |
| 2026-09-21 | FASE-0C | 🟢 | main 3194396: public_api eliminato, Pianificazione/API v1/ricerca preservate; presente nel rilascio verificato 7329ec7 |
| 2026-09-21 | FASE-1A | 🟢 | main 4ad3ffa: report_pdf, simple_exports e batch_operations eliminati; non contare nuovamente nella #569 |
| 2026-09-21 | RST-0101/0102/0104, bonifica residua | 🟢 | #569: eliminato anche filtro rimasto senza chiamanti runtime, controlli import/assenza; merge 7329ec7 e produzione verificata |
| 2026-09-21 | RST-00A6, contatori Provvisori | 🟢 | #580 / `10a74950`: CI 35563595194 e Produzione 35563595236 verdi; issue #575 chiusa |
| 2026-09-21 | RST-00A7, date Banca | 🟢 | #578 / `e339284b`: prova 31/08 → 02/09, E2E/layout/bundle/smoke verdi nel workflow 35557280814; issue #573 chiusa |
| 2026-09-21 | RST-1003/1004 | 🟡 | Deroga warehouse_products rimossa dopo eliminazione del lettore; nessuna tabella cancellata |
| 2026-09-21 | PR-569-PUBBLICATA | 🟢 | 7329ec7498c90da519422ade2f638f0f75d8fc55; CI pre-merge 35555214654, E2E pre-merge 35555214652, Produzione 35555459176 tutti superati nei rispettivi perimetri |
| 2026-09-21 | FASE-1B-PUBBLICATA | 🟢 | `335d1f7a83959c1cb2015e849f88b6f3f5cae513`: falsi router Distinte BPM e Libro Unico eliminati, service canonici attivi; CI 35567802880 e Produzione 35567802918 verdi |
| 2026-09-21 | FASE-1C-PUBBLICATA | 🟢 | `5d66bb25807bf09fa3fb36f2120e7232a862a40c`: router POS accredito e Dati Provvisori eliminati; CI 35571155357 e Produzione 35571155286 verdi |
| 2026-09-21 | RST-0006-V2 | 🟢 | PR #595 / merge `d4b918807845b417d4438fb6f8994b97b5717bd7`: congelati 6 costruttori DB autonomi legacy; CI 35571750093 e Produzione 35571750023 verdi |\n| 2026-09-21 | RST-0007 | 🟢 | PR #596 / merge `d481a80c126bba116a3321dcc5ff30446db72b1a`: census AST+runtime dei router; CI 35579221334 e Produzione 35579221330 verdi, commit servito e smoke superato |\n| 2026-09-21 | RST-0004 | 🟢 | PR #597 / merge `07335e5c0fc331da0f97b86e1c4c8f8a1ca28458`: schema catalogo v3 e guardie React; CI 35588456000 e Produzione 35588455965 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0401-PIN-CANONICO | 🟢 | PR #599 / merge `87efac99936cf575cb03d0a24998fd89abb9bcc8`: nuovo motore PIN canonico, router ERP alleggerito, `ADMIN_PIN` legacy rimosso da utenti PIN; CI 35592364449 e Produzione 35592364329 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0401B-HR-PIN | 🟢 | PR #600 / merge `b34a78cc86cf6f1f242f1a20a01b196e829a9d00`: login admin HR sul motore PIN canonico e lockout condiviso; CI 35593567666 e Produzione 35593567689 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0401C-LOTTI-PIN | 🟢 | PR #601 / merge `ab8c4afe89952575b908346a238b74e4969fb72c`: eliminato helper PIN admin locale; `auth.py`, tablet e ordini usano direttamente il servizio canonico; CI 35596972887 e Produzione 35596972923 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0401D-MENU-PIN | 🟢 | PR #602 / merge `1b6d396c5e6245cf549d107c21a523948818a175`: login Menu su `pin_authentication`; CI 35597930235 e Produzione 35597930222 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0402-SESSIONE-OPERATIVA | 🟢 | PR #603 / merge `b8d0560ac7e59718934ce361d93c4567dce4c16b`: unico emettitore token per HR dipendenti, HR PIN admin e Lotti; CI 35611387736 e Produzione 35611388426 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0402B-HR-PASSWORD | 🟢 | PR #604 / merge `0ed3b411ff67c31cf97336822bab0dd82575b133`: login HR con password usa l'emettitore canonico; CI 35612620570 e Produzione 35612620496 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0402C-VERIFICA-OPERATIVA | 🟢 | PR #605 / merge `cbf2f1a6138e5c265dab8fd581a6923912b5a816`: verifica e normalizzazione HR/Lotti in `workforce_tokens`; `sessione_unica.py` eliminato. CI 35613972152 e Produzione 35613972287 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0402D-IDENTITA-HR | 🟢 | PR #606 / merge `8de5a959a11f182edcbfaacb6fd2457a49a01c31`: lettore del portale personale HR sul verificatore canonico con segreto HR e ruolo obbligatorio; CI 35615658675 e Produzione 35615658806 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0403A-LOGIN-TABLET | 🟢 | PR #607 / merge `9fb39865d025aff4e59e9ce5727fcdbc8e1f4e68`: unico percorso PIN Lotti `/tablet-operatori/login`, token e sessione tablet con `dipendente_id` HR, duplicato `/auth/login` eliminato; CI 35618108658 e Produzione 35618108690 verdi, commit servito e smoke superato. Storico HACCP non riscritto |
| 2026-09-21 | RST-0403B-PERSONALE-TABLET | 🟢 | PR #608 / merge `4a7c825403304a73ab49a7f99c4e3e562a84025b`: elenco e modifica HACCP del personale tablet usano `dipendente_id` HR nell'API e nella UI; ID della proiezione resta interno, righe non collegate a HR restano visibili senza identità attribuita. CI 35619415305 e Produzione 35619415160 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0403C-ADMIN-LOTTI | 🟢 | PR #609 / merge `11bd29bb5af4dd87e51d4f8a103f968cb12aa7c0`: eliminati endpoint duplicato `/ordini-fornitori/verifica-admin`, verifica privata negli ordini e header `X-Admin-Pin`; ordini e fatture usano `require_admin` con token operativo. CI 35620706849 e Produzione 35620706870 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0403D-LOGOUT-TABLET | 🟢 | PR #610 / merge `7bfaa43d11d980395cc2a0a3d610c987bbdd8adb`: eliminati `/tablet-operatori/logout` senza stato server e i due chiamanti; sessione tablet chiusa nel browser. CI 35622017388 e Produzione 35622017393 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0403E-HEALTH-LOTTI | 🟢 | PR #611 / merge `847f15d1f28e5fbbf868e07476eb019209622284`: eliminato `/tablet-operatori/verifica` e il ping duplicato della Home; unico ping Lotti a `/api/health`, che controlla l'archivio. CI 35623257891 e Produzione 35623258002 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0403F-FIRMA-DIPENDENTE | 🟢 | PR #612 / merge `946056d864fa32ebd6074e48a3d05fcb80b19608`: firma PIN manuale delle temperature nel componente `firma_dipendente`, lettura diretta HR; nuovi record positivi/negativi con `dipendente_id`, vecchio componente eliminato, storico HACCP immutato. CI 35624554392 e Produzione 35624554446 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0403G-SYNC-PERSONALE | 🟢 | PR #613 / merge `df73e1ffba5c235b8098b68bbd389f681b9622c1`: elenco personale tablet come GET di sola lettura; sincronizzazione HR solo nella POST `/tablet-operatori/sincronizza-hr`. CI 35625653577 e Produzione 35625653572 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0111-ROTTA-ANOMALIE | 🟢 | PR #614 / merge `f567cd2ad918e1a4e4f1dd799dc6cdebaafa596d`: alias POST `/anomalie/` eliminato, creazione solo su POST `/anomalie/registra`; CI 35626878131 e Produzione 35626878123 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0403H-SESSIONE-TABLET | 🟢 | PR #615 / merge `bd72b54147fe75255ad38df1476accd174a5a845`: login Lotti e tablet condividono la sessione del medesimo `dipendente_id`; navigazione fra reparti senza nuovo PIN finché il token è presente. Rimossa scadenza tablet aggiuntiva di due ore; conferma recente delle azioni distinta. CI 35628146308 e Produzione 35628146336 verdi, commit servito e smoke superato |
| 2026-09-21 | RST-0507A-ESCLUSIONE-RICETTE | 🟢 | PR #616 / merge `fdf6c150292d91ed641901a1ff4fcd836907aef5`: Escludi dalle card conserva la ricetta e il ricettario permette filtro e ripristino. CI 35629629537 e Produzione 35629629586 verdi, commit servito; comando osservato nell'audit visivo live |
| 2026-09-21 | RST-0508A-RICHIESTE-MERCE | 🟢 | PR #617 / merge `d529a2445cbc8afeabce5fd199599a70c8117109`: ricerca OLVA deduplicata, scelta Lavagna o Carrello, richieste persistenti e modificabili dal titolare, bozze raggruppate per prodotto/fornitore. CI 35632056248 e Produzione 35632056411 (tentativo 2) verdi, commit servito. L'invio effettivo via email/WhatsApp resta aperto |
| 2026-09-21 | RST-0508B-REPARTI-RICETTARI | 🟢 | PR #618 / merge `475a19a11de400a8141644e5413cd275ac85c73e`: classificazione unica Ceraldi/SAIMA, 13 riferimenti riallocati con backup e secondo dry-run a zero. CI 35633900857 e Produzione 35633900860 verdi, commit servito |
| 2026-09-21 | RST-0508C-RICETTE-KIOSK | 🟢 | PR #619 / merge `221bd46203fc53079dbaea83f0255600dad5fb4e`: pagina Dose di oggi eliminata; Ricette nel tablet con moltiplicatore nella scheda e stessa sessione dipendente. CI 35635519197 e Produzione 35635520387 verdi, commit servito |
| 2026-09-21 | RST-0508D-RICETTE-CANONICHE | 🟢 | PR #620 / merge `e27ddf86558ff8891863999d62e386374dee7cb1`: la card Ricette apre `#ricette` con la sessione esistente, la seconda pagina tablet è eliminata e il moltiplicatore vive nella scheda unica. Aranciata è stata migrata nel catalogo acquistati con foto e origine Excel: un prodotto `3f9dc79a-2058-454c-b256-6fc628e2f3b4`, vecchia ricetta in `ricette_cestino`, zero schede Aranciata nelle proiezioni operative/archivio. CI 35637996253 e Produzione 35637996074 verdi sul commit servito |
| 2026-09-21 | RST-0508E-RICETTE-SOLO-INTERNE | 🟢 | PR #621 / merge `eb43f3021a17f8f6ba80aaeb407bdec01b309b7b`: eliminato l'importatore SAIMA nel ricettario Ceraldi; catalogo 19 PDF conservato. I 130 riferimenti non operativi sono stati spostati atomicamente in `ricette_saima_archivio`, poi rimossi dalla copia in memoria attraverso le API con 130 copie in `ricette_cestino`. Verifica live: 0 SAIMA in 593 ricette unificate, 19 PDF disponibili. CI 35639555668 e Produzione 35639555712 verdi sul commit servito |
| 2026-09-21 | RST-0508F-VARIANTI-ARANCINI | 🟢 | PR #622 / merge `8ac36a10d99f856736004e2f537b3d6778814792`: import Excel unisce la variante omonima e identica alla base, conserva entrambe le fonti e collega le varianti differenti. Dati reali: base con righe 4 e 19; doppione riga 19 nel cestino; variante funghi/provola riga 34 collegata e foto copiata con ID autonomo, bytes identici. Due sole card arancini; seconda anteprima import a zero modifiche. CI 35641411704 e Produzione 35641411698 verdi sul commit servito |
| 2026-09-21 | RST-0508G-GELATO-RECUPERATO | 🟢 | PR #623 / merge `c2669562e827df0fa4765190994c19250510c4a8`: 5 kg obiettivo − 1,5 kg rientrati = 3,5 kg nuovi, dosi scalate sulla sola produzione nuova e rifiuto dei recuperi superiori al totale o alla giacenza. Test del calcolo e del lotto superati; i dati live gelateria hanno zero invenduti e zero produzioni, quindi nessun movimento reale simulato. CI 35645499593, E2E e Produzione 35645499542 verdi; `/lotti/api/health` serve il commit di merge esatto |
| 2026-09-21 | RST-0508H-SESSIONE-MAGAZZINO | 🟢 | PR #624 / merge `01edcdf5640aa48be68276da13675adefeeee398`: eliminato il secondo PIN ogni 10 minuti in prelievo e lavagna; la sessione tablet identifica il dipendente e le azioni senza sessione sono rifiutate. Test comportamentale del prelievo superato. CI 35646648058, E2E e Produzione 35646647914 verdi; `/lotti/api/health` serve il commit di merge esatto |
| 2026-09-21 | RST-0508I-PIN-INVENDUTI-SERALI | 🟢 | PR #625 / merge `974c42a876b3da5292dff3801a991b0c9e2e96c9`: PIN alla prima registrazione o correzione serale, riusato finché la schermata resta aperta; consultazione libera. Il server registra l'ID dipendente verificato per chiusura e riapertura e rifiuta quantità fuori intervallo. Test UI e backend verdi. CI 35648275775, E2E e Produzione 35648275746 verdi; `/lotti/api/health` serve il commit di merge esatto |
| 2026-09-21 | RST-0508J-INVIO-FORNITORI | 🟢 | PR #626 / merge `6014d3865de19eaec3991ec34a5530cb7c422a68`: la conferma righe prepara testo e PDF delle sole righe confermate per un fornitore; il titolare sceglie email o WhatsApp e registra esplicitamente l'invio dopo averlo effettuato. Solo allora l'ordine diventa `inviato_fornitori` con canale, destinatario e ID dipendente verificato. Nessun messaggio parte automaticamente dal server. Test comportamentali verdi; CI 35650076437, E2E e Produzione 35650076497 verdi; `/lotti/api/health` serve il merge esatto. In produzione non ci sono bozze né ordini confermati, quindi nessun invio reale è stato simulato |
| 2026-09-21 | RST-0508K-PRODUZIONE-BANCO | 🟢 | PR #627 / merge `cc0fb4085e1242177341b8ae93e9b9790b9ed57c`: il server registra lotto e vendita al banco nella stessa richiesta, riprendendo senza duplicazioni dopo un errore di consegna; eliminato il secondo POST frontend con errore silenziato e spostata la scrittura condivisa nel servizio. Test comportamentali verdi; CI 35653099507, E2E e Produzione 35653099660 verdi; `/lotti/api/health` serve il merge esatto |
| 2026-09-21 | RST-0508L-SESSIONE-ADMIN-GESTIONALE | 🟢 | PR #628 / merge `a9264987b7c165df2051333a178ff52cbedfa6c4`: eliminato il timer PIN admin separato. La sessione amministrativa attiva è verificata dal server con lo stesso ID dipendente; resta valida passando da tablet a Gestionale e tornando a Pasticceria. Un dipendente non apre il Gestionale. Test UI/backend, CI 35654573434, E2E e Produzione 35654573307 verdi; browser Chrome e `/lotti/api/health` verificati sul merge esatto |
| 2026-09-21 | RST-0508M-STATI-ANOMALIE-HACCP | 🟢 | PR #629 / merge `9e1d9b30c151f3012c31c8fe8445f538ff176115`: stati canonici condivisi fra Anomalie, report e Registro HACCP. Corretta la query che cercava `risolta` minuscolo. Test comportamentale verde, CI 35655889097 ed E2E/Produzione 35655889006 verdi; health sul merge esatto e Registro HACCP in Chrome ora mostra 1 aperta come Anomalie |
| 2026-09-21 | RST-0508N-LOTTI-SCADUTI | 🟢 | PR #630 / merge `3ab5f7a57e7c713f8f1b66ab545666823e5034eb`: «Cosa usare oggi» separa i lotti utilizzabili, scaduti e con data non verificabile. Il Babà scaduto è nella sezione «Scaduti: non utilizzare» con solo Smaltisci/Dettaglio; gli arancini validi conservano Usa oggi. Test comportamentali, CI 35657331452 ed E2E/Produzione 35657331435 verdi; `/lotti/api/health` e Chrome verificati sul merge esatto |
| 2026-09-21 | RST-0508O-FOTO-RICETTE-PROVENIENZA | 🟢 | PR #631 / merge `d5b4f3bc2aa8dde9543f8e68c7a538bf260f6abf`: prime cinque illustrazioni AI associate ad Amaretti, Amaretti cioccolata, Amarettini nocciola, Crema Pasticcera Napoletana e Pasta Frolla al Cacao senza sovrascrivere foto esistenti. File, SHA-256 e origine persistiti; GET live di ogni foto identico al file generato e badge visibile in Chrome su Ricette/Tablet. 21 test backend e build locale verdi; CI 35658864289 ed E2E/Produzione 35658864334 verdi sul merge esatto. Dosi e procedimenti originali non modificati; restano ricette senza foto |
| 2026-09-22 | RST-0508P-TASK-SCADENZA | 🟢 | PR #632 / merge `1c4f2adfb550e2f295008bb2b75222f83555a618`: un solo task al giorno per ID lotto reale fra UI e scheduler, scaduti esclusi, annullamento motivato senza cancellazione. CI 35660820934 ed E2E/Produzione 35660821011 verdi; `/lotti/api/health` serve il merge esatto. Chrome mostra il Babà scaduto solo con Smaltisci/Dettaglio; l'endpoint Usa oggi lo rifiuta con 409. Il task errato del 21/09 (`fb0d6fe2-d0b1-48c8-b38d-b78a9b708dda`) è stato annullato con motivazione, conservando lo storico |
| 2026-09-22 | RST-0508Q-USCITE-LOTTO | 🟢 | PR #633 / merge `ef9aa47c1761cd7c7ac8983e8ed6389c9be17aa1`: prelievo comune per Banco/Recupera con scadenza verificata, scarico condizionale e retry separato; modale migrato con ID operazione e ID dipendente. 41 test locali, CI 35662771060 ed E2E/Produzione 35662771046 verdi; health serve il merge esatto. Sul Babà scaduto entrambe le API reali rispondono 409 e la quantità resta 1; Chrome conferma la separazione dei lotti |
| 2026-09-22 | RST-0508R-ANNULLAMENTO-LOTTI | 🟢 | PR #634 / merge `91f3ce7ae7d0568a723bf0101f4bf0ae4857fb36`: DELETE lotto e vecchio endpoint massivo senza chiamanti rimossi; annullamento e ripristino motivati conservano record, ID dipendente e movimenti nella cronologia. 45 test locali, CI 35664824196 ed E2E/Produzione 35664824170 verdi; health serve il merge esatto. Chrome Tracciabilità mostra «Annulla lotto» al posto di «Elimina» e il modale richiede motivazione, chiuso senza alterare lotti reali |
| 2026-09-22 | RST-0508S-PIPELINE-LOTTI-STORICI | 🟢 | PR #635 / merge `05ac333a176901cb662c97645ca044245d1c230b`: pipeline notturna conserva i lotti esauriti, annullati e bloccati da richiamo, calcola le scadenze nei due formati. Sei casi e secondo run idempotente superati; CI 35665764878 ed E2E/Produzione 35665764940 verdi; `/lotti/api/health` serve il merge esatto. Il job notturno reale non è stato forzato |
| 2026-09-22 | RST-0508T-ANNULLAMENTO-PRODUZIONI | 🟢 | PR #636 / merge `96332e0cb51d17b09ae381c64ccb64ce5b62de9e`: il DELETE fisico è sostituito dall'annullamento motivato con identità admin, lotto e produzione conservati; scorte fornitore non reintegrate senza prova. 8 test locali, CI 35666936730 ed E2E/Produzione 35666936824 verdi; `/lotti/api/health` serve il merge esatto. Chrome Storico produzioni mostra due righe immutate e «Annulla produzione» con motivo obbligatorio; modale chiuso senza azione sui dati reali |
| 2026-09-22 | RST-0508U-EMETTITORE-PRODUZIONE-BANCO | 🟢 | PR #637 / merge `306e43796bb906ee74d68eb84c12364e4e8b9668`: rimosso l'emettitore legacy POST `/produzioni/`, privo di chiamanti e capace di creare produzione e vendita banco senza lotto né ID dipendente. Resta il flusso unico `/registra-produzione-lotto` con servizio vendita banco canonico. Test locali, CI 35667856544 ed E2E/Produzione 35667856586 verdi; `/lotti/api/health` serve il merge esatto. Nessun dato reale è stato modificato |
| 2026-09-22 | RST-0508V-FOTO-RICETTE-COMPLETAMENTO | 🟡 | PR #638 / merge `7b6ec7b06b1f8666f17e4ea3dfe0485c992fd7a2`: pubblicate senza sovrascritture Amaretti d'Oristano (SHA-256 `c0a0c87f…`) e Avocado Toast con Uova (SHA-256 `07360729…`); endpoint live, Menu sincronizzato, hash GET identico al file generato e badge «Immagine AI illustrativa» verificato in Chrome. CI 35669576341 e Produzione 35669576342 verdi; `/lotti/api/health` serve il merge esatto. Audit iniziale: 587 ricette operative, 162 con foto e 425 senza; completamento in corso |
| 2026-09-22 | RST-0508W-ELIMINAZIONE-RICETTE | 🟢 | PR #639 / merge `accbd03b34d1727c4ca92aa1cde84ded0b36a58a`: DELETE recuperabile e protezione delle varianti. Il completamento UI e la persistenza dopo refresh sono verificati con le tranche X/Y. La scheda duplicata «Babà Napoletano al Rum» è assente dal vivo (404), mentre la ricetta con procedimento resta disponibile. |
| 2026-09-22 | RST-0508X-DISPONIBILITA-INGREDIENTI-CANONICA | 🟢 | PR #640 / merge `c0857b24bcb324cda9760f511eddd447a4190ed2`: eliminato il confronto per famiglia/somiglianza e riusato il matcher unico dei Lotti. «Olio di arachidi per friggere»/«olio di girasole», «prezzemolo fresco»/«prezzemolo» e «capperi sotto sale»/«capperi» convergono sui nomi canonici. CI 35672919480 e Produzione 35672919448 verdi; commit servito e build locale verificata. |
| 2026-09-22 | RST-0508Y-ELIMINAZIONE-PERSISTENTE | 🟢 | PR #641 / merge `7569095e622a6464d0a0685c7c1a23f1c4108c03`: rimossa la proiezione archivio che rigenerava card dopo l'eliminazione e ritirati rendering/promozione senza chiamanti vivi. CI 35677634822 e Produzione 35677634761 verdi. Verifica live: 519 card unificate = 519 record operativi, 0 card archivio, 0 card senza record; health serve il merge esatto. |
| 2026-09-22 | RST-0508Z-REGISTRO-RICETTE | 🟢 | PR #642 / merge `7124927f64f960c150bba9fbe406c4b956b72c46`: registrate le prove live delle PR #640 e #641. CI 35680011844 ed E2E/Produzione manuale 35680124678 verdi; `/lotti/api/health` ha confermato il merge esatto. Nessuna modifica ai dati. |
| 2026-09-22 | RST-0508AA-ARCHIVIO-SEPARATO | 🟢 | PR #643 / merge `ca0d2397540a834b354a9f5104c86a4071bb2256`: nessun procedimento, provenienza o ID operativo trasferito per omonimia dall'archivio; archivio documentale ancora consultabile da endpoint separato. Rimossi parser e vista senza chiamanti. 12 test backend mirati, 87 test frontend Lotti e build locale verdi; CI 35680851409 ed E2E/Produzione 35680851363 verdi; `/lotti/api/health` conferma il merge esatto. Nessun dato reale modificato. |
| 2026-09-22 | RST-0508V2-FOTO-TRASPARENTI | 🟡 | Commit concorrente su `main` `6ead31c40f24b5e8a97546836bab0d5158e0a237`: tre WebP trasparenti Bagna Curitiba, Curitiba e Tramezzino al Prosciutto. CI 35680548961 verde; il workflow Produzione 35680549063 è stato annullato dal merge successivo. Health ha servito temporaneamente quel commit, ma non sono verificati singolarmente foto, associazioni e Menu live. Il collegamento per nome esatto durante startup e la sostituzione di foto preesistenti richiedono convergenza a ID/provenienza canonici in una tranche distinta; i due PNG sorgenti non tracciati restano intatti. |
| 2026-09-22 | RST-0508AC-CESTINO-RICETTE | 🟢 | PR #645 / merge `797cd910ae874b4543e2cfc19ab1f74f0adc9014`: ripristino amministrativo dalla copia completa nel cestino con lo stesso ID, senza ricreare l'archivio storico né alterare produzioni/lotti; cancellazione manuale e deduplica basi condividono il servizio di archiviazione. 13 test backend mirati, 88 frontend e build locali verdi; CI 35683007877 ed E2E/Produzione 35683007881 verdi; `/lotti/api/health` conferma il merge esatto. Nessuna ricetta reale ripristinata automaticamente; percorso UI su dato reale ancora da verificare con un caso autorizzato. |
| 2026-09-22 | RST-0508AE-FOTO-PER-ID | 🟢 | [PR #647](https://github.com/ceraldicontabilita/GestionaleCloud/pull/647), merge `42c1e596591092e2cbfc76adf27c525f32fdef44`: ritirati import e associazione delle illustrazioni per nome all'avvio e il servizio senza altri chiamanti. Resta il caricamento canonico sulla ricetta operativa identificata per ID, che conserva provenienza/hash e sincronizza Menu; una ricetta eliminata risponde 404 senza creare file. Nessun asset o dato reale rimosso. 14 test backend mirati e 90 frontend locali verdi; CI 35687061752 e E2E/Produzione 35687061739 verdi; `/lotti/api/health` conferma il merge esatto sui due domini. Il controllo delle cinque associazioni foto/Menu già esistenti resta aperto, senza inferire identità dai nomi. |
| 2026-09-22 | RST-0508AF-GALATEA-ACQUISTI | 🟢 | [PR #648](https://github.com/ceraldicontabilita/GestionaleCloud/pull/648), merge `bd3eff28bc0412e84071f2390b60e61032bd4832`: eliminato il segnaposto statico; il pannello legge le 22 righe della fattura Lotti `0966541d-e8ff-47f8-9d04-f6650a600abc`, proveniente da ERP `1785230041203`, n. `001852/2` del 14/05/2026, cedente GELINOVA GROUP SRL P.IVA `03762010266`. La 23ª riga ERP è descrittiva, non un articolo. Codice/quantità/prezzo/provenienza mostrati senza inventare allergeni, giacenza o categorie. Corretti commenti che chiamavano Mongo il persistente Supabase. 16 test backend e 89 frontend locali verdi; CI 35685316482, E2E/Produzione 35685316439 verdi; `/lotti/api/health` conferma il commit esatto su entrambi i domini. Scheda autenticata ricaricata: 22 righe da 1 fattura, inclusa `EASY LIMONE LIBERA` cod. `76001` / 18 kg acquistati. L'acquisto non prova stock residuo. L'adattatore compatibile Mongo in memoria rimane debito strutturale distinto. |
| 2026-09-22 | RST-0508AG-GALATEA-SORBETTO | 🟢 | [PR #649](https://github.com/ceraldicontabilita/GestionaleCloud/pull/649), merge `d43461bea33eb83a5c8812d88a63e1ed81ca1667`: brochure Core_Inside Frutta p. 4 e Catalogo 2024 p. 6-7 indicano Easy Limone codice 76001, 1,5 kg di base + 3,5 L d'acqua calda; la fattura live `001852/2` ne conferma l'acquisto (18 kg), non lo stock residuo. Formula nel calcolo Gelati con fonte, proporzioni e pesi rapidi 1/2,5/5/10 kg; 1 L ≈ 1 kg è conversione operativa per la tabella in grammi. I PDF non danno temperatura numerica, tempi né grammi di succo fresco. Le 12 formule Cioccolato già presenti sono attribuite alle pagine 7, 9, 10, 11 della brochure. 90 test frontend e build locali verdi; CI 35686305570 e E2E/Produzione 35686305611 verdi; `/lotti/api/health` conferma il merge esatto su entrambi i domini. UI autenticata: 2,5 kg = 750 g Easy Limone + 1,75 L acqua calda; nessuna produzione registrata. |
| 2026-09-22 | RST-0508AH-PANINI-SEED | 🟢 | [PR #650](https://github.com/ceraldicontabilita/GestionaleCloud/pull/650), merge `1447880a002996e87e6d57159c15419f2ccd104a`: eliminati `seed_panini_rosticceria` e helper senza chiamanti, non i panini operativi persistiti. Il test comportamentale simula due riavvii: Caprese eliminato non ricompare e Crudo modificato non viene sovrascritto. 15 test backend mirati verdi; CI 35687998875 e E2E/Produzione 35687998889 verdi; `/lotti/api/health` conferma il merge esatto. Il seed storico delle altre ricette solo-nome resta tranche distinta. |
| 2026-09-22 | RST-0508AI-RICETTE-STORICHE | 🟢 | [PR #651](https://github.com/ceraldicontabilita/GestionaleCloud/pull/651), merge `12d5a6c768761cbdcf60b091d11b6a6632952a85`: rimossi seed delle ricette solo-nome all'avvio, liste e quantità dettate statiche, import e ricerca web delle foto per nome senza chiamanti vivi. Nessun record o immagine già salvati eliminati; restano caricamento e modifica della ricetta operativa per ID. Test di due riavvii esteso anche a Spritz eliminato: 15 backend mirati verdi; CI 35689440865 ed E2E/Produzione 35689440830 verdi; `/lotti/api/health` conferma il merge esatto sui due domini. |
| 2026-09-22 | RST-0508AK-GALATEA-INTERFACCIA | 🟢 | [PR #653](https://github.com/ceraldicontabilita/GestionaleCloud/pull/653), merge `84eee76d751fdd46f4fc6fb5c6532587bb3ba5b0`. La vista Prodotti Galatea presenta le stesse righe dell'endpoint fatture con riepilogo, ricerca locale, fonte per riga, card su mobile e tabella su desktop senza scroll orizzontale. Etichetta esplicita che la scorta residua non è verificata; nessun dato, prezzo o giacenza creati. Navigazione Gelati con icone coerenti e target tattili di almeno 44 px; sottotitolo operativo. 90 test frontend Lotti e build locale verdi; CI 35692391536 e Produzione/E2E 35692391527 verdi; `/lotti/api/health` ha confermato il commit esatto su `gestionalecloud.onrender.com`. La revisione di tutte le altre pagine resta aperta in RST-0906. |
| 2026-09-22 | RST-0302A-RITIRO-ARCHIVIO-SHEETS | 🟢 | [PR #654](https://github.com/ceraldicontabilita/GestionaleCloud/pull/654), merge `4af8831800f748b9e684f789ed7692bf6b478b0d`. Rimosse le dichiarazioni residue di Sheets come archivio attuale da configurazione, catalogo pagine, knowledge base, documentazione e audit; eliminata la migrazione amministrativa storica non più eseguibile. Il chiamante vivo dell'archivio email/PartenoPay usa la radice documentale Drive canonica senza fallback al vecchio registro Sheets. I documenti originali restano su Drive e i dati applicativi su Supabase: non sono stati eliminati fogli Excel, riferimenti a bilanci o documenti esterni. 11 test backend mirati e 322 test ERP locali verdi; CI 35703453008 e Produzione/E2E 35703453054 verdi; `/lotti/api/health` su entrambi i domini ha confermato il commit esatto. Rollback del codice tramite revert della PR. |
| 2026-09-22 | RST-0906A-NAVIGAZIONE-LOTTI | 🟢 | [PR #656](https://github.com/ceraldicontabilita/GestionaleCloud/pull/656), merge `cdc3a5f7899eda98b251c4fc4802ac2b94702fce`. Intestazione condivisa Lotti con titolo semantico, icona decorativa non annunciata, navigazione primaria con target tattili da 44 px e stato della pagina attiva esposto alle tecnologie assistive; menu Altro e Importa con stato aperto e target coerenti. 92 test Lotti e build locali verdi; CI 35706223965 e Produzione/E2E 35706224041 verdi; `/lotti/api/health` su entrambi i domini ha confermato il commit esatto. Non chiude RST-0906: ERP, HR, Menu e le pagine Lotti con intestazione propria restano da verificare per micro-tranche. Rollback tramite revert della PR. |
| 2026-09-22 | RST-0906C-ALERT-ORDINI-REALI | 🟢 | Diagnosi live del supervisore: 10 avvisi “doppio ordine” per righe del fornitore CIERVO FABIANA del 10/03/2026 erano generati dalle righe `lotti_fornitori` provenienti da fatture, non da ordini. PR #658 riscrive il controllo su `ordini_fornitori`: stesso giorno, fornitore e ID prodotto, ma ID ordine distinti; include ricevuti parzialmente, esclude annullati. Nessun dato o ordine cambiato. Test comportamentali su fatture, righe ripetute nello stesso ordine, ordini distinti e identità prodotto: 2 test locali verdi; CI 35712230839, E2E/audit 35712230777 verdi. Merge `ff69d48750d554691170315587c204dc399e40bb`; CI 35712604462 e Produzione 35712604463 verdi. `/lotti/api/health` ha confermato esattamente il merge su impresasemplice.online e gestionalecloud.onrender.com. Il browser autenticato non era più disponibile per ricontare gli avvisi dopo il deploy: la scomparsa delle 10 voci nella UI resta da verificare, non viene spacciata per prova live. RST-0906 e gli altri alert di qualità dati restano aperti. |
| 2026-09-22 | RST-0508AL-FOTO-RICETTE-DRIVE | 🟢 | Archivio originale `Ricettario_GestionaleCloud_368_immagini.zip` caricato e verificato nell'account `ceraldicontabilita@gmail.com`, cartella Drive `Ricettario_GestionaleCloud_Immagini`; 856.572.274 byte, SHA-256 locale `57496EC4C7C3BBFE8AEBAA4DDF62B28CDF211F37FA6649911911AA1596BF06B3`. Sottocartella `immagini_ricette_per_id`: 368 PNG e 368 ID univoci. PR #660, merge `ebd34752015b85947cdc4f5a38b6cb54558ce0c2`: upload, lettura e copia Menu usano byte canonici su Drive e soli metadati in Supabase; la cartella e' risolta dal registro `drive_folder_registry` persistito in Supabase con provenienza verificata, senza modificare Render. CI `35769024350` e Produzione/E2E `35769024362` verdi; `/lotti/api/health` ha confermato il merge esatto su entrambi i domini. Cut-over transazionale: backup integrale di 365 ricette nella collection `ricette_foto_backup_20260922_before_drive_cutover`, 364 record operativi collegati alla cartella Drive esatta, `Cornetto Classico` unico record vivo senza file sorgente; le quattro immagini di ricette eliminate non hanno ricreato record operativi. I 204 documenti legacy `foto_files` non sono stati ancora eliminati: la tranche successiva deve prima migrare le 72 foto distinte ancora richiamate dal cestino, verificare ripristino e Menu, azzerare tutti i riferimenti, quindi rimuovere fallback e byte Supabase. |
| 2026-09-22 | RST-0508AN-FOTO-CESTINO-DRIVE | 🟡 | [PR #662](https://github.com/ceraldicontabilita/GestionaleCloud/pull/662), merge `2aa4f601`: migrazione riprendibile delle foto ancora richiamate dalle ricette eliminate, con backup integrale, raggruppamento per `foto_id`, una sola copia Drive e aggiornamento delle voci collegate. Il fallback `foto_files` resta finché i riferimenti legacy non sono davvero zero. La misura successiva all'esecuzione conta 437 voci nel cestino, 35 con foto Drive e 72 riferimenti legacy distinti: non è completata e non autorizza ancora la rimozione dei 204 blob. |
| 2026-09-22 | RST-0508AO-WORKER-CESTINO-DRIVE | 🟢 | [PR #663](https://github.com/ceraldicontabilita/GestionaleCloud/pull/663), merge `88b0d1904bdef6a9dac5237fc762c226515e3c20`: il worker di deploy riprende la migrazione foto del cestino senza bloccare l'avvio. CI `35774631163` e Produzione/E2E `35774631262` verdi; `/lotti/api/health` ha confermato il merge esatto. L'avanzamento dati resta separato e non viene dichiarato completo. |
| 2026-09-22 | RST-0508AP-AZIONI-RICETTE | 🟢 | [PR #664](https://github.com/ceraldicontabilita/GestionaleCloud/pull/664), merge `fb4361da1770c09ecd877c4cb91536bab8f78fc4`: eliminata l'etichetta «Immagine AI illustrativa», rimossa la domanda duplicata sulla quantità e compattate le azioni nella scheda. La card conserva un solo «Apri scheda» oltre alla X amministrativa sulla foto; nella scheda restano Produci, Modifica nome e ingredienti, Escludi/Ripristina. CI `35775975144` e Produzione/E2E `35775975083` verdi; health sul commit esatto. |
| 2026-09-22 | RST-0508AQ-ID-DOCUMENTI-SUPABASE | 🟢 | [PR #665](https://github.com/ceraldicontabilita/GestionaleCloud/pull/665), merge `3b97c3704d85cce2e6752581ad8134608f65facf`: l'adattatore documentale ripristina `_id` dal `doc_id` della riga Supabase, correggendo aggiornamenti e worker che altrimenti perdevano l'identità persistita. 12 test locali, CI `35776927884` e Produzione/E2E `35776927870` verdi; `/lotti/api/health` ha confermato il merge esatto. |
| 2026-09-22 | RST-0508AR-CATEGORIE-ALLERGENI-AUTO | 🟢 | [PR #666](https://github.com/ceraldicontabilita/GestionaleCloud/pull/666), merge `1e19c2570ee742fb44bde3626c573535660a886c`: ogni ricetta usa la categoria canonica «Produzione Ceraldi» e la sezione derivata dal reparto; eliminati selettore e campi manuali concorrenti. Creazione e salvataggio ricalcolano gli allergeni dagli ingredienti; rimossi gli editor duplicati dalle schede, mantenuto il registro allergeni dedicato. 48 test backend mirati, 88 frontend e build locali verdi; CI `35780501358` e Produzione/E2E `35780501287` verdi. `/lotti/api/health` sui due domini conferma esattamente il merge. Nessun record reale modificato dalla PR. |
| 2026-09-22 | RST-0508AR-REGISTRO-LIVE | 🟢 | [PR #667](https://github.com/ceraldicontabilita/GestionaleCloud/pull/667), merge `04067d2cd51bc3628b5a7dd853e82e825686e766`: registrate le prove live delle tranche ricette precedenti. Il commit non è stato osservato da solo perché il rilascio concorrente #668 lo ha superato; `/lotti/api/health` ha confermato `3b4509d5008c94473404dddd484848e833c45e19`, che lo contiene. Nessuna dichiarazione falsa di commit servito singolarmente. |
| 2026-09-22 | RST-0508AS-IMMAGINI-NAPOLETANE | 🟢 | [PR #670](https://github.com/ceraldicontabilita/GestionaleCloud/pull/670), merge `10dd0408c0ef08f6d51af053f20c05fbbd8177ef`: 20 immagini trasparenti distinte per ricette operative napoletane, costruite sulle foto locali HACCP e riferimenti pubblici; mappa esplicita UUID→asset, nessun fuzzy matching e nessuna deduplica automatica. Eliminato il parametro «illustrazione AI» dal backend. 49 test mirati verdi; CI `35785249836` e Produzione `35785728803` verdi; `/lotti/api/health` ha confermato esattamente il merge. Le due sorgenti locali non tracciate protette non sono state aggiunte né modificate. |
| 2026-09-22 | RST-0508AT-MIGRAZIONE-FOTO-NAPOLETANE | 🟢 | [PR #671](https://github.com/ceraldicontabilita/GestionaleCloud/pull/671), merge `a1d6a8ab9982c3a6ef31bb8a348b9da99e9d4f17`: worker una-tantum per i 20 UUID esatti, riprendibile e completo solo dopo hash e sync Menu. Il primo giro ha riprodotto 20/20 errori Google Drive `storageQuotaExceeded` e ha portato alla riscrittura canonica #672. Dopo il cut-over Supabase e la rimozione delle vecchie copie Drive, il marker persistito è `completata`: totale 20, già presenti 20, errori 0. Il worker e il modulo una-tantum sono rimossi nella tranche AX. |
| 2026-09-22 | RST-0508AU-FOTO-SUPABASE-CANONICO | 🟢 | [PR #672](https://github.com/ceraldicontabilita/GestionaleCloud/pull/672), merge `4fd3915793ec3bf53d5ab55494aa91adf36f7af4`: nuovi upload ricetta salvati direttamente in Supabase Storage `menu-images/lotti/ricette`; Lotti e Menu usano lo stesso oggetto, senza una seconda copia Drive. CI `35789694805` e Produzione/E2E `35789694802` verdi; `/lotti/api/health` conferma il merge esatto. Prova reale: 20/20 ricette con fonte verificata, 20 path Storage, zero `foto_drive_id`, 20 hash distinti; 20/20 GET `/lotti/api/foto/{id}` hanno SHA-256 identico agli asset. Prima della cancellazione sono stati verificati zero riferimenti attivi e zero nel cestino per ciascuno dei 20 vecchi file; le 20 copie Drive sono state quindi eliminate dall'account `ceraldicontabilita@gmail.com`. Il lettore Drive resta soltanto per lo storico ancora non migrato delle tranche AL/AN/AO. |
| 2026-09-22 | LOTTI-IDENTITA-FATTURE | 🟢 | [PR #669](https://github.com/ceraldicontabilita/GestionaleCloud/pull/669), merge `36c6df83f00071a522b17d2b3c7b689bf8d43a5a`: identità fattura condivisa fra XML e ponte Lotti; corrispondenza esatta per numero+P.IVA oppure numero+fornitore+data, senza chiavi incomplete e con `source_id` forte. 42 test mirati verdi; CI `35786404473` e Produzione/E2E `35786404469` verdi; `/lotti/api/health` ha confermato esattamente il merge. |
| 2026-09-23 | RST-0508AW-UPLOAD-FOTO-ATOMICO | 🟢 | [PR #674](https://github.com/ceraldicontabilita/GestionaleCloud/pull/674), merge `dda0eea7dec9716c1dc175f46de07eb8260df098`: se oggetto nuovo, record e Menu sono già coerenti, un errore nella sola pulizia della copia precedente non produce più un falso 500; l'esito conserva l'errore di pulizia esplicito. 25 test mirati, CI `35791876220` e Produzione/E2E `35791876198` verdi; `/lotti/api/health` conferma il merge esatto. |
| 2026-09-23 | RST-0508AX-RITIRO-WORKER-FOTO | 🟢 | [PR #675](https://github.com/ceraldicontabilita/GestionaleCloud/pull/675), merge `4f11a830a7aa67322e2ab07346b6588404471a72`: dopo la migrazione reale completata e idempotente sono stati eliminati il worker di startup, il modulo una-tantum e i relativi test senza più codice vivo (285 righe rimosse). CI `35792919494` e Produzione/E2E `35792919462` verdi; `/lotti/api/health` conferma esattamente `deploy_commit=4f11a830a7aa67322e2ab07346b6588404471a72`. |
| 2026-09-23 | RST-0508AZ-DOSI-RESA-REALE | 🟢 | [PR #677](https://github.com/ceraldicontabilita/GestionaleCloud/pull/677), merge `c8304f918b400026b15d54e36d96eee1fdcfc412`: la scheda operativa normalizza la dose visualizzata a 1 kg dell'ingrediente principale e applica il moltiplicatore senza mutare la formula persistita; impasto, pieghe e pezzi sono calcolati solo con massa e peso del pezzo disponibili. Nei modali si possono impostare base, fase, peso del pezzo e peso dell'uovo; le dosi mancanti restano esplicite. 46 test backend, 5 frontend e build locali verdi; CI `35816181902` e Produzione/E2E `35816181911` verdi; `/lotti/api/health` conferma esattamente il merge. Audit Supabase: 328 ricette operative, 0 senza reparto, 328 con flag allergeni automatici, 193 senza resa utile, 120 con almeno una dose mancante, 0 con peso del pezzo. Il dato Cornetto Classico e le altre formule incomplete richiedono correzioni per ID e fonte verificata; non sono state mutate da questa PR. |
| 2026-09-23 | RST-0508BB-CORNETTO-FORMULA-FONTE | 🟢 | [PR #679](https://github.com/ceraldicontabilita/GestionaleCloud/pull/679), merge `df97492d1efdabbb2949736fb32834f7695eca0e`: correzione mirata del solo Cornetto Classico operativo (ID `6d114c3a-1b0c-582b-981f-c26d25976eea`) con formula fornita dal titolare, descrizione e procedimento passo passo; fonti tecniche Lesaffre e Molino Grassi distinte dalla formula. 1.000 g farina, 1.800 g impasto (3 uova stimate a 50 g ciascuna), 540 g burro per pieghe, 2.340 g totali, 29 pezzi teorici da 80 g con 20 g residui teorici. `resa_verificata=false`, allergeni Glutine/Latte/Uova ancora `da_confermare` per il miglioratore composto. Prima della scrittura, SQL provato con rollback; backup del record originale in `ricette_backup_20260923_rst0508bb`. Dopo merge: CI `35817436547` e Produzione/E2E `35817702707` verdi, `/lotti/api/health` conferma esattamente il merge; la lettura persistente SQL conferma nuovo record, backup e idempotenza su seconda esecuzione. GET HTTP della ricetta richiede autenticazione e non e' stato usato come prova del dato. Le altre 327 ricette non sono state modificate. |
| 2026-09-23 | RST-0508BD-DESCRIZIONI-CANONICHE | 🟢 | [PR #681](https://github.com/ceraldicontabilita/GestionaleCloud/pull/681), merge `ce317afe44e58af7e6a937e154c97092759af560`: una sola funzione genera descrizioni brevi dagli ingredienti realmente registrati; crea/aggiorna le ricette e il ponte Menu la usano, preservando testi manuali, svuotamenti espliciti e note/procedimenti interni. Il test legacy che pretendeva descrizione vuota e' stato aggiornato alla nuova semantica. 4.647 test backend, build frontend, E2E e audit verdi: CI `35819549048`, Produzione `35819549034`; `/lotti/api/health` conferma esattamente il merge su entrambi i domini. Audit dati: 328 ricette operative, 327 senza descrizione persistita, delle quali 317 hanno ingredienti dettagliati; 10 non hanno alcun ingrediente e non vanno descritte per deduzione. Questa PR non ha ancora eseguito il backfill dei record storici. Le righe Menu collegate sono 36, contro 328 ricette operative: il riallineamento dei riferimenti e' una tranche distinta. |
| 2026-09-21 | FASE-1C-20260921 | 🟡 | branch `ristrutturazione/fase-1c-router-morti-20260921`: eliminati router POS accredito e Dati Provvisori senza chiamanti; utility/service vivi preservati; attende CI/rilascio |
| 2026-09-21 | FASE-1B-V5 | 🟡 | branch `ristrutturazione/fase-1b-falsi-router-v5`: Distinte BPM e workflow ERP Libro Unico spostati nei servizi; vecchi router eliminati; attende CI/rilascio |

**Rilascio verificato:** la PR #658 è pubblicata con `ff69d48750d554691170315587c204dc399e40bb`, confermato da `/lotti/api/health` su entrambi i domini dopo CI 35712604462 e Produzione/E2E 35712604463 verdi. Il codice della navigazione Lotti è la PR #656; la PR #657 ha registrato la verifica precedente. La correzione puntuale delle due schede HR amministratore/dipendente in produzione è stata verificata con login tablet e `dipendente_id` distinti; i PIN non sono conservati nel piano. **Non sono concluse** la qualificazione completa della Prima Nota, la gestione PIN centralizzata dalla UI, l'identità unica con mapping HR/Lotti per tutto lo storico, l'unificazione dati/outbox né la fusione HR/Lotti/Menu/frontend. Nessuna di queste attività va dichiarata completata per effetto della sola bonifica.

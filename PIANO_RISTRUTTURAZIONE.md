# Piano di ristrutturazione di GestionaleCloud

**Documento operativo vivo, aggiornato il 21 settembre 2026.**

- Baseline iniziale dell'audit: `8cf52bd269d8d1facb478e4a585fa8b01a5ec3ff`.
- Baseline della bonifica misurata: `e283400164c0b9fb88ece13eb401fcde9cba1c42`.
- Avanzamenti concorrenti preservati: `31943965f382018d87047637e16fe815d1b93318` (public_api) e `4ad3ffa4cbfd5612e6a4b179d583a419582f2c09` (report/batch).
- Ultima tranche conclusa: [PR #619](https://github.com/ceraldicontabilita/GestionaleCloud/pull/619), Ricette tablet con dose nella scheda.
- Codice pubblicato e verificato: **`221bd46203fc53079dbaea83f0255600dad5fb4e`**.
- Prova di produzione: [workflow 35635520387](https://github.com/ceraldicontabilita/GestionaleCloud/actions/runs/35635520387), E2E isolato, audit layout, smoke runtime e verifica del commit servito; [CI 35635519197](https://github.com/ceraldicontabilita/GestionaleCloud/actions/runs/35635519197) verde.
- **Stato complessivo: IN CORSO.** La fusione ERP, HR, Lotti e Menu non è completata. La bonifica pubblicata non certifica ogni funzione e ogni dato contabile.
- **Priorità operativa aperta:** date Banca [#573](https://github.com/ceraldicontabilita/GestionaleCloud/issues/573) e contatori Provvisori [#575](https://github.com/ceraldicontabilita/GestionaleCloud/issues/575).

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
| RST-0906 | ⚪ | Design system, form, errori, toast/dialog comuni |
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

## 8. Registro avanzamento

| Data | ID/perimetro | Stato | Commit/PR e prova |
|---|---|---|---|
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
| 2026-09-21 | RST-0508J-INVIO-FORNITORI | 🟡 | Correggere il falso invio: la conferma righe prepara testo e PDF delle sole righe confermate per un fornitore, il titolare sceglie email o WhatsApp e apre il client, poi registra esplicitamente l'invio effettuato. Solo allora l'ordine diventa `inviato_fornitori` con canale, destinatario e ID dipendente verificato. Nessun messaggio parte automaticamente dal server. Test comportamentali verdi; CI, E2E e pubblicazione da verificare. In produzione non ci sono bozze né ordini confermati, quindi nessun invio reale da simulare |
| 2026-09-21 | FASE-1C-20260921 | 🟡 | branch `ristrutturazione/fase-1c-router-morti-20260921`: eliminati router POS accredito e Dati Provvisori senza chiamanti; utility/service vivi preservati; attende CI/rilascio |
| 2026-09-21 | FASE-1B-V5 | 🟡 | branch `ristrutturazione/fase-1b-falsi-router-v5`: Distinte BPM e workflow ERP Libro Unico spostati nei servizi; vecchi router eliminati; attende CI/rilascio |

**Rilascio verificato:** RST-0508I della PR #625 è pubblicato e accessibile live con `974c42a8`; le PR #603-#624 e le precedenti PR #599-#602 restano pubblicate. La correzione puntuale delle due schede HR amministratore/dipendente in produzione è stata verificata con login tablet e `dipendente_id` distinti; i PIN non sono conservati nel piano. **Non sono concluse** la qualificazione completa della Prima Nota, la gestione PIN centralizzata dalla UI, l'identità unica con mapping HR/Lotti per tutto lo storico, l'unificazione dati/outbox né la fusione HR/Lotti/Menu/frontend. Nessuna di queste attività va dichiarata completata per effetto della sola bonifica.

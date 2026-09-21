# Piano di ristrutturazione di GestionaleCloud

**Documento operativo vivo, aggiornato il 21 settembre 2026.**

- Baseline iniziale dell'audit: `8cf52bd269d8d1facb478e4a585fa8b01a5ec3ff`.
- Baseline di questa tranche: `e283400164c0b9fb88ece13eb401fcde9cba1c42`.
- Tranche corrente: [PR #569](https://github.com/ceraldicontabilita/GestionaleCloud/pull/569), bonifica dei router dismessi e collaudi prima del merge.
- Stato complessivo: **IN CORSO**. La fusione ERP, HR, Lotti e Menu non è ancora completata.
- Pubblicazione della tranche corrente: **non attestata in questa revisione**; attendere test, merge e verifica del commit effettivamente servito.

## 1. Regole di avanzamento e pubblicazione

Questo file è il registro unico del programma. Gli ID delle attività rimangono stabili. Aggiornare il piano nella stessa PR delle modifiche; aggiungere nel registro la prova del rilascio una volta disponibile. La storia dettagliata rimane in Git, senza mantenere implementazioni morte nel sorgente corrente.

| Stato | Significato |
|---|---|
| ⚪ | Da fare; nessuna implementazione conclusa |
| 🟡 | In corso oppure modificato sul branch, non ancora verificato e pubblicato |
| 🟢 | Concluso nel perimetro dichiarato, con test e verifica del rilascio |
| 🔴 | Bloccato da un impedimento documentato |
| 🧊 | Differito con motivazione |
| ❌ | Eliminato e verificato; indicare commit/PR e verifiche |

Una chiusura richiede: commit/PR, perimetro preciso, confronto prima/dopo, test eseguiti e loro esiti, verifica della versione pubblicata, rollback possibile. Distinguere sempre codice scritto, test superati, merge su main e disponibilità in produzione. Un test saltato non è un test superato. Un HTTP 200 non certifica il dato contabile.

**Autonomia:** eseguire le tranche autorizzate senza chiedere conferme intermedie inutili. Non aggirare permessi, protezioni del branch, test falliti o vincoli sui dati. Le prove distruttive usano solo fixture isolate. Non creare operazioni contabili finte in produzione.

**Comunicazione:** scrivere «Ho pubblicato il lavoro ed è accessibile live» solo dopo verifica del commit servito, indicando cosa è stato pubblicato. Non usare questa frase per una PR ancora aperta.

## 2. Stato verificato e correzioni all'audit iniziale

La PR #566 della Prima Nota è stata integrata con commit `b71f62d0c8a6f17994355150f4a574e73dcad021`. La baseline successiva `e283400` contiene anche i primi guardrail della Fase 0B e la rimozione del vecchio CRUD warehouse da `public_api.py`.

Il workflow [Produzione 35553261218](https://github.com/ceraldicontabilita/GestionaleCloud/actions/runs/35553261218), relativo a `e283400`, ha superato E2E isolati, apertura delle schermate catalogate, layout, viewer e controllo della versione servita con smoke. Queste prove non equivalgono al collaudo manuale di ogni operazione su dati aziendali. Il catalogo iniziale di 64 schermate riguarda l'ERP, non costituisce censimento completo delle tre sotto-app.

### Evidenze della tranche #569

- `reports/__init__.py` importava `report_pdf` e `simple_exports` anche se il registro HTTP montava soltanto la dashboard. Eliminati i due moduli e gli import.
- `batch_operations.py` aveva chiamanti solo interni al modulo dismesso e nei test. Il filtro `filtro_uscite_da_riconciliare` non è un servizio vivo: eliminato insieme alla catena, anziché trasferirlo in un nuovo modulo orfano.
- Ritirati due file di test esclusivi del batch e il test PDF che interrogava il proprio database finto senza chiamare il report. Conservati i test effettivi TFR, API v1 e riconciliazione.
- `app/routers/trattenute_verbali.py` era già assente in `e283400`: non attribuire questa rimozione alla nuova tranche. Il servizio trattenute e i suoi chiamanti rimangono.
- La prima CI della tranche ha rilevato che `warehouse_products` non aveva più lettori: rimossa la relativa deroga dalla guardia sulle collezioni. Non è stata cancellata alcuna tabella.
- Aggiunti controlli contro ricomparsa dei moduli dismessi e import residui.
- Collaudi browser introdotti anche sulle PR; prova del deploy riservata a main. Il collaudo distruttivo rifiuta host non locali e server senza identificativo `e2e-isolato`.
- Le nuove schermate Cassa/Banca/Provvisori contengono solo fixture. Il metodo è CRUD HTTP reale più rilettura nel browser desktop/mobile, non simulazione di ogni pulsante della UI.

### Distinzioni vincolanti

1. Nomi simili o prefissi HTTP condivisi non provano duplicazione. Controllare metodo, percorso finale, ordine, chiamanti e responsabilità.
2. Nessun chiamante frontend non significa morto: controllare job, servizi, webhook, API esterne, strumenti di ripristino e accessi osservati.
3. Un import esistente soltanto in un test non rende vivo un servizio. Non trasferire codice morto per salvare un test obsoleto.
4. Il censimento storico 196 nomi/61 collezioni è una fotografia documentata, non un conteggio attuale. Collezioni vuote, alimentate da trigger o da servizi esterni non sono automaticamente eliminabili.
5. Quattro adapter o variabili DSN non provano quattro database di produzione. Il README descrive schemi `gestionale`, `hr`, `lotti`, `menu`; verificare configurazione effettiva prima di pianificare trasferimenti di dati. I commenti che parlano di progetti separati possono essere obsoleti.
6. Spostare file non elimina duplicazioni. Misurare separatamente righe applicative, test, documentazione e file generati; non contare una rinomina come bonifica.

## 3. Obiettivo architetturale

Un solo ERP modulare: un bootstrap FastAPI applicativo, un'infrastruttura dati governata, un'identità/sessione con autorizzazioni per dominio, un coordinamento dei job e un frontend React/Vite. HR, Lotti e Menu diventano moduli, non prodotti da reimportare o riautenticare.

Struttura backend target: `app/main.py`, `app/api/<dominio>/`, `app/domains/<dominio>/`, `app/repositories/`, `app/services/`, `app/jobs/`, `app/migrations/`. Vietati nuovi bootstrap paralleli; quelli attuali rimangono solo durante il passaggio verificato. Le FastAPI di test isolate non sono applicazioni produttive duplicate.

Unico progetto/database operativo previsto. Gli schemi di dominio possono rimanere distinti. Non imporre un unico oggetto client globale se servono connessioni con privilegi differenti: eliminare fonti di verità e logiche duplicate, preservando isolamento e transazioni.

### Proprietà dei dati

| Entità | Responsabilità canonica |
|---|---|
| Originali documentali | Archivio originale immutabile, hash e riferimenti; Drive non è il database operativo |
| Inbox e classificazione | Un unico ingresso con stato, parser/versione ed errori tracciati |
| Fatture e righe | `invoices` e righe canoniche, un ID/versione per documento |
| Fornitori | `fornitori`, condivisi dai domini |
| Dipendenti | Anagrafica HR canonica, identità stabile |
| Cedolini | Un record canonico versionato, non copie ERP/HR/payslip |
| Banca | `estratto_conto_movimenti` come evidenza; scritture e classificazioni collegate |
| Prodotti/ingredienti | Catalogo unico con codici fornitore e unità normalizzate |
| Magazzino | Ricezioni e movimenti inventario verificabili, con lotto quando disponibile |
| Ricette | Versioni, ingredienti canonici, rese, costo e allergeni verificati |
| Menu | Proiezione di pubblicazione dei prodotti/ricette, con prezzo e visibilità deliberati |

### PIN e permessi

Il verificatore amministratore `app/services/admin_pin.py` è già condiviso in alcuni ingressi. Questo non completa l'unificazione: esistono ancora emittenti/sessioni e router locali.

Nel target, **Admin del Gestionale è l'unico posto per gestire accessi, ruoli e PIN**. Nessuna funzione amministrativa duplicata in Lotti, HR o Menu. Usare credenziali protette lato server, rotazione e revoca tracciate, limiti tentativi condivisi e MFA per operazioni sensibili. Mai PIN in chiaro nei dati, log o repository. Il PIN e il token ottenuto con esso non costituiscono due fattori distinti.

I PIN personali identificano il dipendente canonico per il gesto operativo; non vanno sostituiti da un PIN condiviso fra persone. Un'unica sessione non autorizza ogni ruolo a tutto. Menu clienti pubblico, portale personale, dati retributivi e amministrazione devono restare separati per autorizzazione. Verificare esplicitamente accessi negati e revoche attraverso tutti i moduli.

### Flussi affidabili, non copie

**Fattura:** acquisizione unica → identità fornitore/righe → contabilità, IVA, debito e scadenza quando applicabili → prodotti, prezzi e ricezione → inventario/lotti → costo e disponibilità delle ricette collegate → proiezione Menu autorizzata.

La fattura non dimostra da sola il pagamento o la consegna fisica. Una bolletta non carica ingredienti. Un servizio, cespite, anticipo o nota di credito segue il suo ciclo, non tutti i cicli indistintamente. Ricezione attesa e ricezione confermata devono essere distinte; non duplicare il carico se esiste già DDT/ricezione. Non inventare quantità, unità, lotti, scadenze o ricette. Righe ambigue → `da_mappare`; dati non applicabili → stato esplicito `non_applicabile`.

**Cedolino:** un ID/versione → fascicolo HR, costo/debito, Prima Nota salari, TFR documentato o stima dichiarata, acconti e saldo. Un PDF di bonifico non è l'addebito: la riconciliazione bancaria richiede movimento reale e identità coerente. La rettifica di un cedolino non deve duplicare costi o pagamenti.

**Menu:** dati canonici e pubblicazione esplicita. Non trasformare un aggiornamento del costo ingrediente in un cambio automatico del prezzo di vendita; non derivare allergeni certi da nomi ambigui. Qromo rimane una fonte di transizione finché proprietà dei campi, compatibilità e riconciliazione del catalogo non sono risolte.

**Outbox:** evento registrato atomicamente con il documento nella stessa transazione. Almeno `event_id`, `entity_id`, `entity_version`, `event_type`, versione payload, data, chiave idempotenza; stato/tentativi/errore per ciascun consumer, lease e retry persistente. Non basta un'unica spunta globale se un consumer è riuscito e un altro no. Il riavvio non perde lavoro; il retry non duplica. UI con ciclo completo, pendente, errore o non applicabile per ogni dominio. Gli errori Lotti non devono far perdere la fattura né sparire in un warning.

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

Una versione React/Router compatibile, una build Vite, client API/query e AuthProvider condivisi, design system e dialog/toast comuni. Preservare deep link, stampa, QR pubblici e uso tablet/mobile. `/hr/*`, `/lotti/*`, `/menu/*` possono restare URL della stessa SPA; rimuovere la navigazione amministrativa fra documenti separati. I QR clienti non devono aprire il gestionale privato.

Eliminare `frontend_hr/`, `frontend_lotti/`, `frontend_menu/`, `frontend_shared/` solo dopo migrazione degli import, asset, test, build e riferimenti backend. Non ridurre artificialmente le schermate cancellando funzionalità vive: classificare pagina, tab, dettaglio, strumento admin e vista pubblica.

## 5. Piano progressivo con ID stabili

### Fase 0A: Prima Nota operativa prima delle demolizioni

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-00A1 | 🟢 | CRUD Cassa HTTP, persistenza, saldo, update e soft-delete nella baseline #566 |
| RST-00A2 | 🟢 | Banca senza prova resta provvisoria/fuori saldo; flusso con EC verificato nella baseline |
| RST-00A3 | 🟢 | Fattura da confermare → pagamento Cassa, test baseline |
| RST-00A4 | 🟢 | Attendi banca senza inventare pagamento, test baseline |
| RST-00A5 | 🟢 | Misto: quota Cassa reale e residuo Banca aperto, test baseline |
| RST-00A6 | 🟡 | Estendere prove browser di reload, anno, Cassa/Banca/Provvisori; screenshot nella #569, attendere esito |
| RST-00A7 | 🟡 | Completare audit campi/origine/contropartita, saldi e relazioni; validazioni e riapertura fattura già corrette |
| RST-00A8 | 🟢 | Smoke versione pubblicata nella baseline; ripeterlo per ogni rilascio |
| RST-00A9 | 🟢 | Preservare il contratto operativo della baseline; non è certificazione di ogni dato contabile reale |

Accettazione ulteriore: errore su importi/date invalidi senza scritture parziali, doppi invii idempotenti, più pagamenti parziali, annullamento coerente, prova bancaria originale non alterata, saldi iniziali e periodo. Non aspettare la fusione delle sotto-app per mantenere utilizzabile Prima Nota.

### Fase 0B: guardrail

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0001 | 🟢 | Guardia unicità metodo/percorso normalizzato introdotta in e283400; verificare anche sub-app e shadowing |
| RST-0002 | ⚪ | Audit inverso endpoint → consumatore/owner, includendo job, esterni, manutenzione e telemetria |
| RST-0003 | 🟢 | Guardia AST NO-WRITE e census writer warehouse introdotti in e283400; restano writer transitori da ridurre |
| RST-0004 | ⚪ | Contratto route React ↔ catalogo, distinguendo tab/dettagli/redirect |
| RST-0005 | 🟢 | Nessuna nuova FastAPI produttiva; tre eccezioni temporanee esplicite fino alla fusione |
| RST-0006 | ⚪ | Impedire nuove fonti dati/client indipendenti duplicati |
| RST-0007 | ⚪ | Inventario automatico router montati, non montati, importati e utilizzati internamente |
| RST-0008 | ⚪ | Grafo completo pagine/componenti, import lazy, asset e toolchain delle quattro interfacce |

`warehouse_inventory` è un target canonico previsto dal codice corrente: non vietarne ogni scrittura indiscriminatamente. Bloccare writer obsoleti e convergere su responsabilità unica senza interrompere Lotti.

### Fase 1: rimozione reale del morto

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0101 | 🟡 | `report_pdf.py` eliminato nella #569; confermare CI e rilascio |
| RST-0102 | 🟡 | `simple_exports.py` eliminato nella #569, import package rimossi; export dei domini conservati |
| RST-0103 | 🟢 | Router trattenute già assente nella baseline e283400; service vivo conservato, non contare nuova cancellazione |
| RST-0104 | 🟡 | `batch_operations.py` e helper senza chiamanti runtime eliminati nella #569, nessun servizio sostitutivo orfano |
| RST-0105 | ⚪ | Estrarre import_distinte_bpm vivo in service/parser, ritirare wrapper dopo verifica chiamanti |
| RST-0106 | ⚪ | Estrarre import_libro_unico vivo in service/parser, ritirare wrapper dopo verifica chiamanti |
| RST-0107 | 🟡 | Ripulire commenti su implementazioni rimosse; mantenere invarianti di dominio e motivazioni ancora utili |
| RST-0108 | 🟡 | Import e test esclusivi dei router morti rimossi nella #569; continuare census sul resto del repo |

Una rimozione può abbassare il numero totale dei test perché sparisce una funzione non pubblicata: documentare il motivo e mantenere coperti i percorsi canonici. Non cancellare test falliti per nascondere regressioni vive.

### Fase 2: svuotare public_api.py

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0201 | ⚪ | Spostare GET/POST pianificazione/events nel dominio Pianificazione, URL invariati |
| RST-0202 | ⚪ | Verificare client esterni /api/v1; conservare in modulo dedicato oppure ritirare con evidenze |
| RST-0203 | ⚪ | Verificare consumatori della ricerca globale ERP, distinta da Lotti |
| RST-0210 | ⚪ | Portare a zero le route operative del router storico dopo migrazione dei vivi |
| RST-0211 | ⚪ | Eliminare public_api.py quando tutte le responsabilità sono risolte |
| RST-0212 | ⚪ | Eliminare la registrazione e gli import residui |

Candidati da rivalidare: vecchi F24 alerts/dashboard, suppliers-legacy, bank/statements, assegni-legacy, portal/upload, dashboard/stats-legacy e inventory fornitore. Il CRUD warehouse è già rimosso dalla Fase 0B. Un endpoint nascosto da OpenAPI può essere ancora montato e richiede verifica.

### Fase 3: infrastruttura dati e applicativa condivisa

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0301 | ⚪ | Definire accesso Supabase governato e transazioni condivise |
| RST-0302 | ⚪ | Rimuovere fallback Mongo HR produttivo dopo verifica configurazione |
| RST-0303 | ⚪ | Eliminare eventuale fonte Lotti parallela, non gli attributi esclusivi HACCP |
| RST-0304 | ⚪ | Convergere il client Menu su infrastruttura condivisa e privilegi corretti |
| RST-0305 | ⚪ | Verificare progetto/schemi effettivi; migrare soltanto dati realmente separati e dopo backup |
| RST-0306 | ⚪ | Repository per dominio, un solo writer per fatto, ID/FK e mapping di migrazione |
| RST-0307 | ⚪ | Health e readiness dei moduli senza falsi successi o fallback in memoria produttivo |
| RST-0308 | ⚪ | Coordinamento job/lease, retry e stato amministrativo unico |
| RST-0309 | ⚪ | Eliminare bootstrap e shutdown duplicati dopo parità |
| RST-0310 | ⚪ | Ritirare i tre embed.py solo dopo eliminazione dei rispettivi mount |

Prima di ogni migrazione: conteggi per stato/anno, originali e hash, relazioni, saldi, backup ripristinabile, dry-run e rollback. Non cancellare tabelle solo perché un adapter non le legge.

### Fase 4: autenticazione/PIN unici

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0401 | 🟡 | Inventario ingressi e token; verificatore admin condiviso già presente, sessioni non ancora tutte unificate |
| RST-0402 | ⚪ | RBAC comune per admin, amministrazione, HR, responsabile, operatore HACCP, Menu e sola lettura |
| RST-0403 | ⚪ | Sessione unica con controlli server per ogni dominio e identità stabile |
| RST-0404 | ⚪ | Eliminare login amministrativo HR autonomo dopo cutover verificato |
| RST-0405 | ⚪ | Eliminare login applicativo Lotti autonomo, preservando identificazione tablet |
| RST-0406 | ⚪ | Eliminare JWT Menu autonomo senza esporre dati privati al Menu clienti |
| RST-0407 | ⚪ | PIN personale come credenziale dell'utente/dipendente canonico |
| RST-0408 | ⚪ | Unica pagina Gestione PIN e accessi nel Gestionale, niente configurazioni duplicate |
| RST-0409 | ⚪ | Rimuovere router/login duplicati dopo passaggio a verifica e revoca centrali |
| RST-0410 | ⚪ | Sostituire gestione manuale PIN_HASH_ADMIN in Render con rotazione sicura centrale e bootstrap controllato |

### Fase 5: fattura e ciclo interdominio

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0501 | ⚪ | Modello canonico righe fattura con unità, quantità, prezzi e provenienza |
| RST-0502 | ⚪ | Eliminare seconda fattura Lotti, mantenendo relazioni/proiezioni ricostruibili |
| RST-0503 | ⚪ | Mapping riga → prodotto/ingrediente, conferma degli ambigui |
| RST-0504 | ⚪ | Storico prezzi fornitore dalla riga canonica |
| RST-0505 | ⚪ | Ricezione attesa/confermata e movimento inventario idempotente, senza doppio DDT/carico |
| RST-0506 | ⚪ | Lotto/tracciabilità solo con evidenze, dati mancanti espliciti |
| RST-0507 | ⚪ | Ricette riferite agli ingredienti canonici, non nomi liberi duplicati |
| RST-0508 | ⚪ | Aggiornare food cost/disponibilità con rese e conversioni verificate |
| RST-0509 | ⚪ | Coda da_mappare per righe sconosciute, mai inventare corrispondenze |
| RST-0510 | ⚪ | Outbox atomica e ricevute per consumer; replay, lease e idempotenza |
| RST-0511 | ⚪ | Ritirare sync/copie ERP→Lotti dopo backfill e quadratura |
| RST-0512 | ⚪ | Eliminare gestionale_fatture.py quando non ha più responsabilità vive |
| RST-0513 | ⚪ | Contabilità, IVA, debito/scadenzario dal documento unico secondo applicabilità |
| RST-0514 | ⚪ | Prima Nota: cash attestato, banca con prova reale, provvisori fuori saldo reale |
| RST-0515 | ⚪ | Completezza ciclo: riuscito/pendente/errore/non applicabile per dominio |
| RST-0516 | ⚪ | Errori consumer e retry visibili in UI, senza falso successo globale |

Accettazione: XML entra una volta; stessa fattura e righe in tutti i lettori; conti/IVA/debiti corretti; nessun pagamento inventato; prodotti/prezzi/ricezione coerenti; lotto documentato; ricette esistenti aggiornate senza inventarne; Menu pubblicato solo secondo regole; reimport e riavvio senza duplicati; errore di un consumer persistente e ritentabile. Coprire servizi, merci, cespiti, note di credito, parziali e rettifiche.

### Fase 6: HR e cedolini

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0601 | ⚪ | Dipendente canonico con ID e stato rapporto unici |
| RST-0602 | ⚪ | Cedolino canonico versionato con originale |
| RST-0603 | ⚪ | Lettori HR/ERP sullo stesso repository |
| RST-0604 | ⚪ | Eliminare copie payslip/buste paga parallele dopo confronto |
| RST-0605 | ⚪ | Cedolino → costo/debito/Prima Nota salari senza doppia registrazione |
| RST-0606 | ⚪ | TFR documentato o stimato esplicitamente, no doppio accantonamento |
| RST-0607 | ⚪ | Acconti/saldo e bonifici collegati con prova bancaria reale |
| RST-0608 | ⚪ | Fascicolo personale con lo stesso ID documento |
| RST-0609 | ⚪ | Ferie, presenze, turni e richieste dentro l'ERP, permessi preservati |
| RST-0610 | ⚪ | Eliminare FastAPI autonoma HR |
| RST-0611 | ⚪ | Router HR nella app principale |

Accettazione: un upload visibile con stesso ID da HR, fascicolo, salari, TFR e banca; riavvio/reimport/rettifica idempotenti; nessun altro dipendente può leggere il documento.

### Fase 7: Lotti nativo

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0701 | ⚪ | Router Lotti nella app principale |
| RST-0702 | ⚪ | Eliminare bootstrap FastAPI Lotti autonomo |
| RST-0703 | ⚪ | Job HACCP nel coordinamento comune |
| RST-0704 | ⚪ | Operatori dall'identità HR, senza seconda anagrafica/PIN |
| RST-0705 | ⚪ | Fornitori condivisi, attributi qualifica HACCP nel proprio dominio |
| RST-0706 | ⚪ | Catalogo prodotti/ingredienti unico |
| RST-0707 | ⚪ | Registro movimenti inventario coerente con ricezioni/consumi |
| RST-0708 | ⚪ | Preservare lotti, temperature, sanificazione, allergeni, tracciabilità e richiami |
| RST-0709 | ⚪ | Eliminare doppioni di tabelle soltanto dopo backfill e controllo dei dati esclusivi |

### Fase 8: Menu nativo

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0801 | ⚪ | Censire menu_* e responsabilità realmente esclusive |
| RST-0802 | ⚪ | Prodotto/ricetta canonico pubblicabile |
| RST-0803 | ⚪ | Immagini con riferimenti unici e accesso pubblico limitato alle pubblicabili |
| RST-0804 | ⚪ | Allergenici e versioni canoniche verificabili |
| RST-0805 | ⚪ | Sostituire menu_bridge con proiezione/pubblicazione controllata |
| RST-0806 | ⚪ | Portare Qromo a import/export di transizione dopo riconciliazione e proprietà campi |
| RST-0807 | ⚪ | Ritirare client Menu duplicato |
| RST-0808 | ⚪ | Ritirare bootstrap FastAPI Menu autonomo |
| RST-0809 | ⚪ | Router Menu privati/pubblici nella app principale con confini espliciti |
| RST-0810 | ⚪ | Eliminare copie editabili concorrenti, preservare prezzi/visibilità pubblicazione |

### Fase 9A: fondamenta frontend

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0901 | ⚪ | Unica versione React compatibile |
| RST-0902 | ⚪ | Unico React Router e modello di deep link |
| RST-0903 | ⚪ | Una toolchain Vite |
| RST-0904 | ⚪ | Client API/query comune e invalidazione cache coerente |
| RST-0905 | ⚪ | Unico AuthProvider/RBAC |
| RST-0906 | ⚪ | Design system, form, errori, toast/dialog coerenti |
| RST-0907 | ⚪ | Portare PinModal condiviso nel vero shared, senza nuove copie |

### Fase 9B: porting

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0910 | ⚪ | HR in frontend/src/modules/hr |
| RST-0911 | ⚪ | Lotti in frontend/src/modules/lotti |
| RST-0912 | ⚪ | Menu admin/pubblico in frontend/src/modules/menu |
| RST-0913 | ⚪ | Link amministrativi interni, stessa sessione e layout |
| RST-0914 | ⚪ | Preservare deep link/QR e redirect necessari; non rimuoverli solo per età |

### Fase 9C: eliminazione toolchain duplicate

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-0920 | ⚪ | Eliminare frontend_hr dopo parità |
| RST-0921 | ⚪ | Eliminare frontend_lotti dopo parità |
| RST-0922 | ⚪ | Eliminare frontend_menu dopo parità |
| RST-0923 | ⚪ | Eliminare frontend_shared dopo migrazione |
| RST-0924 | ⚪ | Semplificare build_frontends.sh a una sola build e aggiornare deploy |
| RST-0925 | ⚪ | Rimuovere CRA/CRACO, lockfile e dipendenze non più richiesti |

### Fase 10: alias e collezioni fantasma

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-1001 | ⚪ | Eliminare progressivamente app.database.Collections |
| RST-1002 | ⚪ | Costanti/repository canonici, no nomenclature parallele |
| RST-1003 | 🟡 | KEEP/ARCHIVE/DELETE motivato per ogni collezione; warehouse_products tolta dalle letture tollerate nella #569 |
| RST-1004 | 🟡 | Lista delle letture fantasma in riduzione, non azzerata |
| RST-1005 | ⚪ | Ritirare endpoint di migrazione completata preservando ripristino/nuove installazioni |
| RST-1006 | ⚪ | Audit provenienza legacy: mai usarla da sola per cancellare dati |

### Fase 11: bootstrap e manutenzione

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-1101 | ⚪ | Censire marker, dipendenze e stato migrazioni startup |
| RST-1102 | ⚪ | Spostare one-shot in migrazioni versionate e riutilizzabili per ripristino |
| RST-1103 | ⚪ | Togliere dal normale avvio i repair conclusi e verificati |
| RST-1104 | ⚪ | Strumenti amministrativi in maintenance con dry-run e audit |
| RST-1105 | ⚪ | Lifespan limitato a connessioni, sicurezza, registrazione servizi/job e shutdown |

### Fase 12: ritiro definitivo delle sotto-app

| ID | Stato | Attività e verifica |
|---|---|---|
| RST-1201 | ⚪ | Nessuna FastAPI produttiva HR autonoma |
| RST-1202 | ⚪ | Nessuna FastAPI produttiva Lotti autonoma |
| RST-1203 | ⚪ | Nessuna FastAPI produttiva Menu autonoma |
| RST-1204 | ⚪ | Rimuovere mount HR dopo migrazione percorsi |
| RST-1205 | ⚪ | Rimuovere mount Lotti dopo migrazione percorsi |
| RST-1206 | ⚪ | Rimuovere mount Menu dopo migrazione percorsi pubblici/privati |
| RST-1207 | ⚪ | Nessuna configurazione che reintroduca una fonte DB parallela |
| RST-1208 | ⚪ | Nessun bridge transitorio ERP→Lotti o Lotti→Menu |
| RST-1209 | ⚪ | Una build frontend |
| RST-1210 | ⚪ | Una identità/sessione e gestione accessi |
| RST-1211 | ⚪ | Un coordinamento job/lease e relativi controlli |

## 6. Ordine di lavoro e criteri finali

Prima Nota operativa e copertura dei casi critici → guardrail necessari alla tranche → codice morto → public_api → infrastruttura e identità → outbox → fatture/inventario → cedolini/HR → Lotti → Menu → frontend unico → ritiro delle compatibilità e delle sotto-app → audit finale. Le rimozioni isolate già dimostrate non devono aspettare l'intera rifondazione, ma non devono indebolire la contabilità in uso.

Prima di eliminare un percorso: cercare import/call/dynamic import, chiamanti UI/job/API esterne e test; confrontare contratto; migrare i chiamanti vivi; aggiungere guardia antiregressione; cancellare file/import/dependency non più necessari. Per i dati servono in più backup, referenzialità, confronto saldi/quantità e prova di ripristino.

Non riscrivere tutto da zero. Non creare nuove copie temporanee senza owner e condizione di ritiro. Non cambiare conti, IVA, pagamenti, stock fisico, PIN o permessi per far passare un test. Non togliere commenti che spiegano invarianti ancora necessarie. Non sostituire un flusso rotto con un successo vuoto.

La ristrutturazione è chiusa soltanto con un backend e frontend modulari effettivamente unificati; accessi/ruoli corretti; originali preservati; una fattura e un cedolino canonici; consumer persistenti e idempotenti; report e Menu coerenti; nessun router orfano non giustificato; startup snello; eliminazioni verificate; test backend/frontend/integrati/visivi e versione produttiva allineati. L'audit funzionale deve includere tutte e quattro le aree, non solo le 64 viste ERP iniziali.

## 7. Misure di riduzione

| Indicatore | Baseline storica | Traguardo |
|---|---|---|
| Bootstrap FastAPI produttivi | 4 | 1, esclusi server isolati di test |
| Frontend e build | 4 + cartella shared | Un frontend e una build |
| Identità/sessioni | Verificatore admin in parte comune, ingressi multipli | Gestione centrale, ruoli separati |
| Accesso dati | Adapter multipli, topologia reale da verificare | Repository governati e responsabilità unica |
| Job/lease | Più scheduler | Coordinamento unico, nessuna doppia esecuzione |
| Bridge transitori | ERP→Lotti e Lotti→Menu | Nessuna seconda fonte editabile |
| public_api | 26 route nell'audit iniziale | File eliminato dopo migrazione dei vivi |
| Letture fantasma tollerate | Lista nel test runtime | Riduzione verificata, esterni/read-only documentati |
| Test schermate ERP | Catalogo iniziale 64 | Nessuna regressione, estensione HR/Lotti/Menu |
| Righe applicative eliminate | Da misurare per PR | Riduzione netta verificata, senza contare rinomine/docs come codice |

Il primo commit della #569 aveva 1.354 righe rimosse e 57 aggiunte complessive; il totale finale va ricalcolato sul diff completo e separato tra applicazione, test e documentazione. Non confondere riduzione del piano Markdown con snellimento del software.

## 8. Registro avanzamento

| Data | ID/perimetro | Stato | Commit/PR e prova |
|---|---|---|---|
| 2026-09-21 | PLAN-0001 | 🟢 | Piano iniziale su audit 8cf52bd; storia in Git |
| 2026-09-21 | PLAN-0002 | 🟢 | Priorità Prima Nota e gestione PIN centrale aggiunte |
| 2026-09-21 | FASE-0A-LIVE | 🟢 | #566, b71f62d0c8a6f17994355150f4a574e73dcad021; precedente registro Produzione 35543104234 |
| 2026-09-21 | RST-0001/0003/0005 | 🟢 | e283400164c0b9fb88ece13eb401fcde9cba1c42; Produzione 35553261218 tutti i job superati |
| 2026-09-21 | RST-0101/0102/0104/0108 | 🟡 | #569, primo commit 1cfbad652ce50471655b3eac9d8c62075517d95a: tre moduli rimossi, test morti ritirati, guardia nuova; nessun dato cancellato |
| 2026-09-21 | RST-00A6, collaudi prima del merge | 🟡 | #569, bd36c7c9559077edfb5e1d1a0d1796d42a7d00b5: isolamento esplicito e schermate desktop/mobile, attendere esito |
| 2026-09-21 | RST-1003/1004 | 🟡 | #569, 781854b0cb6805afa85801253439d073c8371fd1: rimossa deroga warehouse_products dopo scomparsa dell'ultimo lettore; nessuna tabella eliminata |

**Passo di chiusura della #569 ancora necessario:** test completi sul suo HEAD, ispezione delle prove visive, revisione diff, merge senza forzature, verifica del commit in produzione e aggiornamento di questo registro. Nessun'altra fase è da considerare conclusa per effetto di questa bonifica.

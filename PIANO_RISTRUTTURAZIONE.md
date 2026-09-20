# Piano di ristrutturazione — GestionaleCloud

> **Documento operativo vivo.**
> Questo file è la fonte di verità del programma di ristrutturazione tecnica e funzionale di GestionaleCloud.
> Deve essere aggiornato nello stesso commit in cui un'attività viene iniziata, modificata o conclusa.
>
> **Ultimo aggiornamento:** 2026-09-21  
> **Baseline codice:** `main@8cf52bd269d8d1facb478e4a585fa8b01a5ec3ff`  
> **Stato generale:** 🟡 IN CORSO  
> **Obiettivo finale:** un solo ERP, un solo backend applicativo, un solo accesso ai dati, un solo sistema di autenticazione, un solo orchestratore dei job e un solo frontend React/Vite. HR, Lotti e Menu cessano di essere sotto-app autonome e diventano moduli nativi di GestionaleCloud.

---

## 1. Come si aggiorna questo documento

### Stati ammessi

| Stato | Significato |
|---|---|
| ⚪ DA FARE | attività non iniziata |
| 🟡 IN CORSO | modifica aperta, non ancora chiusa |
| 🟢 COMPLETATO | codice modificato, test verdi, deploy verificato |
| 🔴 BLOCCATO | serve una decisione o una dipendenza esterna |
| 🧊 DIFFERITO | attività utile ma non necessaria alla fase corrente |
| ❌ ELIMINATO | funzione/file/endpoint rimosso definitivamente |

### Regola di chiusura

Un'attività **non può essere marcata COMPLETATA** soltanto perché il codice è stato modificato. La riga deve riportare:

1. commit o PR;
2. file/endpoint/tabelle eliminati o migrati;
3. test aggiunti o aggiornati;
4. prova che la produzione usa il nuovo percorso;
5. eventuale piano di rollback;
6. nessuna nuova duplicazione introdotta.

Quando un'attività è conclusa, aggiornare anche la sezione **Registro avanzamento** in fondo al documento.

---

# 2. Verdetto dell'audit corrente

GestionaleCloud non ha oggi il problema principale nelle pagine ERP: il workflow di produzione del commit baseline ha aperto con Playwright **64/64 schermate catalogate senza errori**, oltre ad avere test backend/frontend, build, audit layout, viewer e smoke di produzione verdi.

Il debito principale è **architetturale**:

- backend molto più grande dell'interfaccia realmente usata;
- router storici ancora montati;
- endpoint senza chiamanti;
- alias dati e collezioni legacy;
- migrazioni e repair rimasti nello startup;
- quattro applicazioni FastAPI nello stesso processo;
- quattro frontend separati;
- tre sistemi aggiuntivi di autenticazione/startup oltre all'ERP;
- accessi dati differenti per ERP, HR, Lotti e Menu;
- ponti di sincronizzazione tra moduli che dovrebbero invece condividere gli stessi dati canonici.

### Numeri della baseline

Dal tree Git corrente:

- circa **2.208 file** totali;
- circa **1.360 file Python**;
- **161 file Python** sotto `app/routers/` del solo ERP;
- **264 file Python** sotto `app/services/`;
- **598 test Python**;
- frontend separati:
  - `frontend/`: circa 261 file;
  - `frontend_hr/`: circa 12 file;
  - `frontend_lotti/`: circa 422 file;
  - `frontend_menu/`: circa 89 file;
  - `frontend_shared/`: 1 solo file reale.

Il numero di file non è di per sé un errore, ma mostra che la fusione nominale delle app non è diventata una fusione architetturale.

---

# 3. Problema centrale: oggi non esiste ancora “un solo GestionaleCloud”

## 3.1 ERP

Il gestionale principale usa:

- `app/main.py`;
- `app/router_registry.py`;
- `app/database.py`;
- runtime Supabase del gestionale;
- `frontend/` con React 18 + Vite.

## 3.2 HR

HR è ancora una FastAPI autonoma:

- `app/hr/main.py`;
- propria istanza `FastAPI()`;
- proprio `Database`;
- supporto a DSN HR separata e perfino fallback Mongo;
- propri scheduler;
- propria autenticazione;
- proprio frontend `frontend_hr/`;
- React Router e Vite con versioni diverse dall'ERP.

`app/hr/embed.py` non integra il dominio HR: **monta una seconda applicazione dentro la prima**.

## 3.3 Lotti

Lotti è ancora una FastAPI autonoma:

- `app/lotti/server.py`;
- propria istanza `FastAPI()`;
- proprio archivio;
- il codice dichiara esplicitamente che in produzione può usare un **progetto Supabase diverso da GestionaleCloud**;
- proprio event bus/scheduler/seed;
- proprio login;
- proprio frontend `frontend_lotti/`;
- React 19 + CRA/CRACO.

`app/lotti/embed.py` monta la sotto-app, non la fonde con l'ERP.

## 3.4 Menu

Menu è ancora una FastAPI autonoma:

- `app/menu/server.py`;
- proprio client Supabase `app/menu/supabase_client.py`;
- proprie credenziali e JWT;
- Qromo come fonte esterna ancora sincronizzata;
- proprio frontend `frontend_menu/`;
- React 19 + CRA/CRACO.

Lotti comunica con Menu attraverso `app/lotti/servizi/menu_bridge.py`, cioè tramite una copia/sincronizzazione applicativa invece di usare un unico modello canonico.

---

# 4. Contraddizioni da eliminare

## 4.1 “Archivio unico” contro database/client separati

Il README descrive Supabase come archivio unico con schemi `gestionale`, `hr`, `lotti`, `menu`.

Il codice, però, conserva ancora:

- `app/database.py` per ERP;
- `app/hr/database.py` con DSN propria e fallback Mongo;
- `app/lotti/db.py` con configurazione Supabase propria;
- `app/menu/supabase_client.py` con client Supabase proprio.

**Obiettivo:** una sola infrastruttura dati e un solo livello repository. Gli schemi possono restare separati per dominio, ma devono vivere nello stesso database/progetto e non richiedere bridge HTTP o client indipendenti.

## 4.2 Quattro login

L'utente non deve percepire quattro prodotti.

**Obiettivo:** una sessione GestionaleCloud e un unico RBAC. HR, HACCP/Lotti e Menu possono avere ruoli diversi, ma non login separati.

## 4.3 Scheduler separati

ERP, HR e Lotti avviano job propri.

**Obiettivo:** un solo orchestratore di job/lease, con job nominati per dominio e stato consultabile da Admin.

## 4.4 Quattro frontend

Oggi convivono toolchain differenti:

- ERP: React 18 + Vite 5;
- HR: React 18 + Vite 6 + React Router 7;
- Lotti: React 19 + CRA/CRACO + Router 7;
- Menu: React 19 + CRA/CRACO + Router 7.

Questo rende più difficile condividere componenti, autenticazione, query cache, design system e routing.

**Obiettivo:** un solo `frontend/`, una sola versione React, un solo React Router, una sola build Vite.

---

# 5. Problema funzionale reale: i ponti possono fallire dopo che l'origine è riuscita

## 5.1 Fattura ERP → Lotti

Il flusso corrente passa da:

`FATTURA_CREATED`  
→ `on_fattura_created_alimenta_lotti`  
→ `app/lotti/routers/gestionale_fatture.py::alimenta_lotti_da_fattura`

Il codice attuale **non blocca l'import contabile** se Lotti fallisce: cattura l'errore, scrive un warning e ritorna.

Questa scelta protegge la contabilità, ma crea una situazione in cui:

- la fattura esiste nell'ERP;
- il magazzino Lotti può non essere aggiornato;
- la copia operativa Lotti può essere in ritardo;
- l'utente vede due verità.

In passato il codice stesso documenta che il magazzino Lotti era rimasto indietro mentre le fatture continuavano a entrare.

### Obiettivo

La fattura deve essere salvata una sola volta. Le righe fattura devono alimentare in modo idempotente e persistente:

1. fornitore;
2. dizionario articoli/ingredienti;
3. storico prezzi;
4. ricezione merce;
5. movimento inventario;
6. lotto/tracciabilità quando i dati sono sufficienti;
7. disponibilità ingredienti usata dalle ricette;
8. food cost.

**Non va creata automaticamente una ricetta inventata da una fattura.**  
La fattura aggiorna gli ingredienti/prodotti acquistati e quindi le ricette che li referenziano. Se una riga non è riconosciuta, deve finire in una coda di mapping da confermare.

## 5.2 Lotti → Menu

Oggi Lotti usa `menu_bridge.py` e scrive nelle tabelle Menu.

### Obiettivo

Menu non deve avere una copia separata dei prodotti Lotti.

Il modello target è:

`prodotto/ricetta canonica`  
→ flag/versione di pubblicazione  
→ vista Menu pubblico.

Dati condivisi:

- nome;
- descrizione;
- prezzo;
- categoria;
- foto;
- allergeni;
- disponibilità;
- ricetta sorgente;
- stato pubblicazione.

Il Menu pubblico diventa una **vista/proiezione** dei dati canonici, non un archivio parallelo.

## 5.3 Cedolini ERP ↔ HR

Oggi il dominio paghe è diviso fra ERP e HR.

### Obiettivo

Un solo record canonico `cedolino` deve alimentare contemporaneamente:

- fascicolo dipendente;
- pagina HR;
- Prima Nota salari;
- TFR;
- riconciliazione bonifici;
- residui/acconti;
- documenti;
- dashboard amministrativa.

Nessuna copia “ERP cedolino” e “HR cedolino”.

---

# 6. Architettura target

## 6.1 Backend

Un'unica applicazione:

```text
app/
├── main.py
├── api/
│   ├── auth/
│   ├── documents/
│   ├── invoices/
│   ├── suppliers/
│   ├── banking/
│   ├── accounting/
│   ├── fiscal/
│   ├── hr/
│   ├── inventory/
│   ├── production/
│   ├── menu/
│   ├── vehicles/
│   └── admin/
├── domains/
│   ├── documents/
│   ├── invoices/
│   ├── hr/
│   ├── inventory/
│   ├── recipes/
│   ├── menu/
│   └── ...
├── repositories/
├── services/
├── jobs/
└── migrations/
```

Nessun `FastAPI()` secondario in:

- `app/hr`;
- `app/lotti`;
- `app/menu`.

Questi diventano moduli/router del main app.

## 6.2 Database

Un solo progetto/database Supabase.

Gli schemi possono restare:

```text
core / gestionale
hr
lotti
menu
```

ma non devono duplicare le stesse entità.

### Entità canoniche condivise

| Entità | Fonte unica target |
|---|---|
| documenti | `documents_inbox` + archivio originali |
| fatture passive | `invoices` |
| righe fattura | relazione canonica delle fatture |
| fornitori | `fornitori` |
| dipendenti | anagrafica HR canonica |
| cedolini | `cedolini` |
| movimenti bancari | `estratto_conto_movimenti` |
| prodotti/ingredienti acquistati | catalogo canonico unico |
| ricette | registro ricette unico |
| lotti | registro tracciabilità unico |
| movimenti magazzino | registro inventario unico |
| menu | proiezione/pubblicazione di prodotti/ricette canonici |

## 6.3 Eventi affidabili: transactional outbox

Le propagazioni critiche non devono essere best-effort in memoria.

Introdurre una tabella/collection tipo:

`domain_outbox`

con:

- `id`;
- `event_type`;
- `entity_id`;
- `payload_version`;
- `created_at`;
- `status`;
- `attempts`;
- `last_error`;
- `processed_at`;
- `idempotency_key`.

Esempio:

`invoice.imported`  
→ outbox persistente  
→ consumer inventario  
→ consumer prezzi  
→ consumer cespiti  
→ consumer scadenzario  
→ ogni consumer registra il proprio esito.

La fattura può essere acquisita anche se un consumer fallisce, ma il fallimento **non scompare**: resta `pending/failed`, viene ritentato e compare in Admin.

---

# 7. Frontend target: una sola cartella

## Struttura finale proposta

```text
frontend/
├── package.json
├── vite.config.js
├── src/
│   ├── app/
│   │   ├── router/
│   │   ├── auth/
│   │   ├── providers/
│   │   └── navigation/
│   ├── modules/
│   │   ├── dashboard/
│   │   ├── documenti/
│   │   ├── fatture/
│   │   ├── fornitori/
│   │   ├── banca/
│   │   ├── contabilita/
│   │   ├── fiscale/
│   │   ├── hr/
│   │   ├── lotti/
│   │   ├── menu/
│   │   ├── veicoli/
│   │   └── admin/
│   ├── shared/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── api/
│   │   ├── utils/
│   │   └── styles/
│   └── main.jsx
└── public/
```

### Cartelle da eliminare al termine della migrazione

```text
frontend_hr/
frontend_lotti/
frontend_menu/
frontend_shared/
```

### Regole

- una sola versione React;
- una sola versione React Router;
- Vite come unica build;
- un solo Axios/query client;
- un solo AuthProvider;
- un solo design system;
- un solo sistema toast/dialog;
- un solo catalogo route;
- niente link `external: true` verso HR/Lotti/Menu;
- mantenere temporaneamente URL compatibili (`/hr/*`, `/lotti/*`, `/menu/*`) come route della stessa SPA durante la migrazione.

---

# 8. Piano progressivo

## FASE 0 — Guardrail prima della demolizione

| ID | Stato | Attività |
|---|---|---|
| RST-0001 | ⚪ | Aggiungere test di unicità `method + normalized_path` su tutte le route FastAPI montate |
| RST-0002 | ⚪ | Aggiungere audit inverso backend → chiamante/owner |
| RST-0003 | ⚪ | Correggere guardia NO-WRITE magazzino: deve risolvere costanti/alias e includere `warehouse_inventory` |
| RST-0004 | ⚪ | Aggiungere contratto route React ↔ `page_catalog.json` |
| RST-0005 | ⚪ | Impedire nuovi `FastAPI()` fuori da `app/main.py` |
| RST-0006 | ⚪ | Impedire nuovi client DB indipendenti per HR/Lotti/Menu |
| RST-0007 | ⚪ | Aggiungere inventario automatico di router montati/non montati |
| RST-0008 | ⚪ | Aggiungere inventario frontend di componenti/pagine non raggiungibili |

**Definition of Done:** nessuna nuova duplicazione può entrare mentre si ristruttura.

---

## FASE 1 — Eliminare codice morto ERP già identificato

| ID | Stato | Attività |
|---|---|---|
| RST-0101 | ⚪ | Eliminare `app/routers/reports/report_pdf.py` se confermato senza chiamanti |
| RST-0102 | ⚪ | Eliminare `app/routers/reports/simple_exports.py` se confermato senza chiamanti |
| RST-0103 | ⚪ | Eliminare router `trattenute_verbali` mantenendo solo il service usato dallo scheduler |
| RST-0104 | ⚪ | Estrarre helper vivo da `batch_operations.py`, poi eliminare il router/file morto |
| RST-0105 | ⚪ | Estrarre `import_distinte_bpm` in service/parser e cancellare il falso router |
| RST-0106 | ⚪ | Estrarre `import_libro_unico` in service/parser e cancellare il falso router |
| RST-0107 | ⚪ | Eliminare commenti che descrivono intere implementazioni rimosse quando Git history è sufficiente |
| RST-0108 | ⚪ | Eliminare import, costanti e test che esistono soltanto per mantenere codice morto |

---

## FASE 2 — Cancellare `public_api.py`

### Trasferimenti necessari

| ID | Stato | Attività |
|---|---|---|
| RST-0201 | ⚪ | Spostare `/api/pianificazione/events` nel router Pianificazione mantenendo il contratto URL |
| RST-0202 | ⚪ | Verificare runtime di `/api/v1/*`; se esterno, spostare in `external_api_v1.py`; altrimenti eliminare |
| RST-0203 | ⚪ | Verificare eventuali chiamanti esterni di `/api/ricerca-globale` |

### Endpoint candidati a eliminazione immediata dopo guardia/chiamanti

- `/api/f24-public/alerts`
- `/api/f24-public/dashboard`
- `/api/suppliers-legacy`
- `/api/warehouse/products*`
- `/api/warehouse/movements*`
- `/api/suppliers/{supplier_id}/inventory` legacy se sostituito
- `/api/bank/statements*`
- `/api/assegni-legacy`
- `/api/portal/upload`
- `/api/dashboard/stats-legacy`

| ID | Stato | Attività |
|---|---|---|
| RST-0210 | ⚪ | Portare a zero le route operative in `public_api.py` |
| RST-0211 | ⚪ | Eliminare `app/routers/public_api.py` |
| RST-0212 | ⚪ | Rimuovere `public_api` da `router_registry.py` |

---

## FASE 3 — Unificare infrastruttura ERP + HR + Lotti + Menu

| ID | Stato | Attività |
|---|---|---|
| RST-0301 | ⚪ | Definire unico accesso Supabase per tutti i domini |
| RST-0302 | ⚪ | Eliminare fallback Mongo HR dalla produzione |
| RST-0303 | ⚪ | Eliminare archivio Lotti separato come fonte applicativa |
| RST-0304 | ⚪ | Eliminare client Supabase Menu indipendente |
| RST-0305 | ⚪ | Portare tabelle necessarie nello stesso progetto/database |
| RST-0306 | ⚪ | Definire repository per schema/dominio invece di client separati |
| RST-0307 | ⚪ | Unificare health check |
| RST-0308 | ⚪ | Unificare scheduler e lease |
| RST-0309 | ⚪ | Eliminare startup/shutdown duplicati delle sotto-app |
| RST-0310 | ⚪ | Eliminare `app/hr/embed.py`, `app/lotti/embed.py`, `app/menu/embed.py` al termine |

**Regola:** la fusione non significa mettere tutte le tabelle nello stesso schema. Significa eliminare copie, bridge e accessi separati. Gli schemi possono restare confini logici.

---

## FASE 4 — Unificare autenticazione e autorizzazioni

| ID | Stato | Attività |
|---|---|---|
| RST-0401 | ⚪ | Inventariare login ERP, HR, Lotti, Menu e relativi secret/token |
| RST-0402 | ⚪ | Definire ruoli unici: admin, amministrazione, HR, responsabile, operatore HACCP, menu, sola lettura |
| RST-0403 | ⚪ | Applicare sessione ERP a tutte le route |
| RST-0404 | ⚪ | Eliminare login HR separato per area amministrativa |
| RST-0405 | ⚪ | Eliminare login Lotti separato dove non serve un PIN operativo |
| RST-0406 | ⚪ | Eliminare JWT Menu indipendente |
| RST-0407 | ⚪ | Mantenere eventuale PIN rapido tablet come step-up/identificazione operatore, non come seconda applicazione |

---

## FASE 5 — Fattura → prodotti → magazzino → ricette

| ID | Stato | Attività |
|---|---|---|
| RST-0501 | ⚪ | Definire modello canonico delle righe fattura |
| RST-0502 | ⚪ | Eliminare copia `Lotti.fatture` quando la pipeline usa direttamente la fattura canonica |
| RST-0503 | ⚪ | Creare mapping canonico riga fattura → prodotto/ingrediente |
| RST-0504 | ⚪ | Aggiornare storico prezzo fornitore dalla stessa riga |
| RST-0505 | ⚪ | Creare ricezione merce/movimento inventario idempotente |
| RST-0506 | ⚪ | Creare/aggiornare lotto solo con evidenza sufficiente |
| RST-0507 | ⚪ | Collegare ricette agli ingredienti canonici |
| RST-0508 | ⚪ | Ricalcolare disponibilità e food cost ricette dopo il movimento inventario |
| RST-0509 | ⚪ | Mettere righe non riconosciute in coda `da_mappare`, mai inventare corrispondenze |
| RST-0510 | ⚪ | Introdurre outbox persistente per `invoice.imported` |
| RST-0511 | ⚪ | Eliminare sync periodico/copia GestionaleCloud → Lotti dopo backfill e quadratura |
| RST-0512 | ⚪ | Eliminare `app/lotti/routers/gestionale_fatture.py` quando non serve più |

### Test obbligatorio di accettazione

Importare una fattura XML di prova e verificare in un unico test E2E:

1. fattura presente;
2. fornitore presente;
3. righe presenti;
4. prezzi aggiornati;
5. inventario aggiornato;
6. eventuale lotto creato/agganciato;
7. ricetta collegata vede nuova disponibilità/costo;
8. nessuna seconda copia della fattura;
9. riesecuzione dello stesso import = zero duplicati.

---

## FASE 6 — Cedolini e HR canonici

| ID | Stato | Attività |
|---|---|---|
| RST-0601 | ⚪ | Stabilire anagrafica dipendente canonica unica |
| RST-0602 | ⚪ | Stabilire `cedolini` come record canonico unico |
| RST-0603 | ⚪ | Migrare lettori HR e ERP sullo stesso repository |
| RST-0604 | ⚪ | Eliminare copie payslip/buste paga parallele |
| RST-0605 | ⚪ | Collegare automaticamente cedolino → Prima Nota salari |
| RST-0606 | ⚪ | Collegare cedolino → TFR |
| RST-0607 | ⚪ | Collegare cedolino → bonifico/movimento banca con prova reale |
| RST-0608 | ⚪ | Collegare cedolino → fascicolo dipendente |
| RST-0609 | ⚪ | Unificare richieste ferie/presenze/turni nell'app principale |
| RST-0610 | ⚪ | Eliminare `app/hr/main.py` come FastAPI autonoma |
| RST-0611 | ⚪ | Trasformare router HR in router del main app |

### Test obbligatorio

Caricare un cedolino una sola volta e verificare che **lo stesso ID canonico** sia visibile da HR, amministrazione, Prima Nota, TFR e riconciliazione.

---

## FASE 7 — Lotti e produzione come dominio nativo ERP

| ID | Stato | Attività |
|---|---|---|
| RST-0701 | ⚪ | Trasformare router Lotti da sub-app a router main |
| RST-0702 | ⚪ | Eliminare `app/lotti/server.py` come FastAPI autonoma |
| RST-0703 | ⚪ | Unificare scheduler HACCP nel scheduler GestionaleCloud |
| RST-0704 | ⚪ | Unificare operatori con anagrafica HR senza seed/copie periodiche |
| RST-0705 | ⚪ | Unificare fornitori Lotti con `fornitori` |
| RST-0706 | ⚪ | Unificare dizionario prodotti/ingredienti |
| RST-0707 | ⚪ | Unificare movimenti magazzino |
| RST-0708 | ⚪ | Conservare specificità HACCP: lotti, temperature, sanificazione, allergeni, recall |
| RST-0709 | ⚪ | Eliminare collezioni/tabelle Lotti duplicate dopo backfill verificato |

---

## FASE 8 — Menu come proiezione del catalogo/ricette

| ID | Stato | Attività |
|---|---|---|
| RST-0801 | ⚪ | Inventariare tabelle `menu_*` e stabilire quali sono realmente uniche |
| RST-0802 | ⚪ | Definire prodotto/ricetta canonico pubblicabile |
| RST-0803 | ⚪ | Spostare foto su storage unico con ID canonico |
| RST-0804 | ⚪ | Spostare allergeni sul dominio ricetta/prodotto canonico |
| RST-0805 | ⚪ | Sostituire `menu_bridge.py` con lettura/proiezione diretta |
| RST-0806 | ⚪ | Gestire Qromo come importatore esterno, non fonte permanente del dominio |
| RST-0807 | ⚪ | Eliminare client Supabase Menu indipendente |
| RST-0808 | ⚪ | Eliminare `app/menu/server.py` come FastAPI autonoma |
| RST-0809 | ⚪ | Trasformare route Menu in router main |
| RST-0810 | ⚪ | Eliminare copie menu che possono essere derivate dalla ricetta/prodotto canonico |

---

## FASE 9 — Fusione dei frontend

### Step 9A — Fondamenta comuni

| ID | Stato | Attività |
|---|---|---|
| RST-0901 | ⚪ | Scegliere una sola versione React |
| RST-0902 | ⚪ | Scegliere una sola versione React Router |
| RST-0903 | ⚪ | Portare tutto a Vite |
| RST-0904 | ⚪ | Unificare axios/query client |
| RST-0905 | ⚪ | Unificare AuthProvider/RBAC |
| RST-0906 | ⚪ | Unificare design system |
| RST-0907 | ⚪ | Trasferire `frontend_shared/PinModal.js` nel shared reale |

### Step 9B — Porting moduli

| ID | Stato | Attività |
|---|---|---|
| RST-0910 | ⚪ | Portare HR in `frontend/src/modules/hr/` |
| RST-0911 | ⚪ | Portare Lotti in `frontend/src/modules/lotti/` |
| RST-0912 | ⚪ | Portare Menu admin/pubblico in `frontend/src/modules/menu/` |
| RST-0913 | ⚪ | Sostituire link esterni `/hr/`, `/lotti/`, `/menu/` con route interne |
| RST-0914 | ⚪ | Conservare redirect/deep-link compatibili durante transizione |

### Step 9C — Cancellazione

| ID | Stato | Attività |
|---|---|---|
| RST-0920 | ⚪ | Eliminare `frontend_hr/` |
| RST-0921 | ⚪ | Eliminare `frontend_lotti/` |
| RST-0922 | ⚪ | Eliminare `frontend_menu/` |
| RST-0923 | ⚪ | Eliminare `frontend_shared/` |
| RST-0924 | ⚪ | Semplificare `scripts/build_frontends.sh` fino a una sola build |
| RST-0925 | ⚪ | Eliminare CRA/CRACO e dipendenze non più necessarie |

---

## FASE 10 — Eliminare alias e collezioni fantasma

| ID | Stato | Attività |
|---|---|---|
| RST-1001 | ⚪ | Eliminare progressivamente `app.database.Collections` |
| RST-1002 | ⚪ | Usare solo costanti/repository canonici |
| RST-1003 | ⚪ | Classificare ogni voce di `test_collezioni_lette_e_mai_scritte.py` come KEEP/ARCHIVE/DELETE |
| RST-1004 | ⚪ | Portare la lista delle collezioni fantasma verso zero |
| RST-1005 | ⚪ | Eliminare endpoint di migrazione dopo migrazione verificata |
| RST-1006 | ⚪ | Non cancellare dati soltanto perché hanno marcatore `legacy_*`: è provenienza, non prova di duplicato |

---

## FASE 11 — Alleggerire startup e manutenzione

| ID | Stato | Attività |
|---|---|---|
| RST-1101 | ⚪ | Censire tutte le migration marker in `main.py` |
| RST-1102 | ⚪ | Spostare repair one-shot completati in `migrations/` |
| RST-1103 | ⚪ | Togliere dallo startup migrazioni già definitivamente applicate |
| RST-1104 | ⚪ | Spostare strumenti amministrativi in `maintenance/` |
| RST-1105 | ⚪ | Ridurre `lifespan` a connessione, sicurezza, job, shutdown |

---

## FASE 12 — Spegnimento definitivo delle sotto-app

Questa fase avviene soltanto dopo i backfill e i test di parità.

| ID | Stato | Attività |
|---|---|---|
| RST-1201 | ⚪ | Nessuna istanza `FastAPI()` in HR |
| RST-1202 | ⚪ | Nessuna istanza `FastAPI()` in Lotti |
| RST-1203 | ⚪ | Nessuna istanza `FastAPI()` in Menu |
| RST-1204 | ⚪ | Nessun `app.mount('/hr', ...)` |
| RST-1205 | ⚪ | Nessun `app.mount('/lotti', ...)` |
| RST-1206 | ⚪ | Nessun `app.mount('/menu', ...)` |
| RST-1207 | ⚪ | Nessuna variabile runtime che seleziona un database separato per i tre moduli |
| RST-1208 | ⚪ | Nessun bridge ERP→Lotti o Lotti→Menu |
| RST-1209 | ⚪ | Una sola build frontend |
| RST-1210 | ⚪ | Una sola autenticazione |
| RST-1211 | ⚪ | Un solo scheduler/orchestratore |

---

# 9. Cosa NON fare durante la ristrutturazione

1. **Non riscrivere tutto da zero.** Migrare dominio per dominio mantenendo test e produzione funzionanti.
2. **Non cancellare tabelle solo perché hanno nomi legacy.** Prima verificare riferimenti e dati unici.
3. **Non creare nuove copie temporanee senza una data di eliminazione.**
4. **Non mantenere file morti “per sicurezza”.** Git è già la sicurezza.
5. **Non far passare un bridge fallito come successo complessivo.** Deve esistere stato persistente e retry.
6. **Non usare il solo importo per riconciliare pagamenti o movimenti.**
7. **Non inventare una ricetta da una fattura.** La fattura alimenta ingredienti, inventario e prezzi.
8. **Non trasformare Menu in una seconda anagrafica prodotto.**
9. **Non mantenere un login per ogni modulo.**
10. **Non marcare conclusa una fase senza backfill, test E2E e verifica produzione.**

---

# 10. KPI della ristrutturazione

Aggiornare questi valori ad ogni milestone.

| KPI | Baseline | Target |
|---|---:|---:|
| istanze FastAPI applicative | 4 | 1 |
| frontend separati | 4 + shared | 1 |
| build frontend | 4 | 1 |
| sistemi auth applicativi | multipli | 1 |
| scheduler principali | multipli | 1 |
| client/access layer DB applicativi | multipli | 1 infrastruttura condivisa |
| bridge ERP→Lotti | 1+ | 0 |
| bridge Lotti→Menu | 1 | 0 |
| router storico `public_api.py` | 26 route | 0 / file eliminato |
| collezioni lette e mai scritte tollerate | >0 | 0, salvo archivio esterno documentato |
| pagine catalogate E2E | 64/64 verdi | mantenere 100% verdi durante la fusione |
| copie della stessa fattura tra domini | >1 possibile | 1 record canonico |
| copie dello stesso cedolino tra domini | >1 possibile | 1 record canonico |

---

# 11. Ordine raccomandato

L'ordine è vincolante per ridurre il rischio:

```text
GUARDRAIL
   ↓
CODICE MORTO ERP
   ↓
PUBLIC_API
   ↓
UNICO ACCESSO DATI + AUTH
   ↓
OUTBOX
   ↓
FATTURE → INVENTARIO/LOTTI
   ↓
CEDOLINI → HR/ERP
   ↓
LOTTI NATIVO
   ↓
MENU NATIVO
   ↓
FRONTEND UNICO
   ↓
ELIMINAZIONE SOTTO-APP/BRIDGE
   ↓
ELIMINAZIONE LEGACY RESIDUO
```

Non partire dallo spostamento grafico dei file frontend mentre backend e dati restano quattro sistemi: produrrebbe una sola cartella visiva sopra quattro architetture separate.

---

# 12. Definition of Done finale

La ristrutturazione è conclusa soltanto quando:

- esiste un solo `FastAPI()` applicativo;
- `app/hr/main.py`, `app/lotti/server.py`, `app/menu/server.py` non sono più bootstrap autonomi;
- `embed.py` delle sotto-app è eliminato;
- esiste un solo sistema di auth/RBAC;
- esiste un solo access layer Supabase;
- HR/Lotti/Menu non hanno database/client separati;
- una fattura importata alimenta inventario/prezzi/ingredienti senza copie e con retry persistente;
- un cedolino importato è lo stesso record visto da HR, ERP, TFR e riconciliazione;
- Menu legge/proietta prodotti e ricette canonici;
- `menu_bridge.py` e `gestionale_fatture.py` sono eliminati;
- esiste una sola cartella `frontend/`;
- `frontend_hr/`, `frontend_lotti/`, `frontend_menu/`, `frontend_shared/` sono eliminati;
- esiste una sola build Vite;
- tutte le pagine operative restano coperte da E2E;
- il test backend→chiamante non segnala endpoint orfani;
- `public_api.py` è eliminato;
- le collezioni fantasma sono azzerate o dichiarate archivio read-only con motivazione;
- `main.py` non contiene repair one-shot già completati;
- il deploy di produzione passa test backend, frontend, E2E, layout, viewer e smoke.

---

# 13. Registro avanzamento

Aggiungere una riga ad ogni attività conclusa.

| Data | ID | Stato | Commit/PR | Risultato | Evidenza/Test |
|---|---|---|---|---|---|
| 2026-09-21 | PLAN-0001 | 🟢 COMPLETATO | documento iniziale | Creato il piano operativo di ristrutturazione ERP + HR + Lotti + Menu | Audit su `main@8cf52bd` |

---

## Nota operativa finale

Questo documento non deve diventare un altro archivio storico infinito.  
Quando una fase è completata:

- mantenere la sintesi dell'esito;
- rimuovere dettagli superati se Git li conserva già;
- aggiornare KPI e architettura target;
- aggiungere immediatamente le anomalie nuove emerse durante il lavoro.

**Principio guida:** una sola informazione, una sola fonte, un solo percorso di scrittura, una sola interfaccia applicativa.

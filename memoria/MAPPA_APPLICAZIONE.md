# CERALDI ERP — MAPPA APPLICAZIONE COMPLETA

## Aggiornata: Luglio 2026 — Audit mappa completa (lettura di tutti i router)

> **Mappe di dettaglio** (rigenerabili con `python scripts/genera_mappa.py`):
> - `memoria/MAPPA_MODULI.md` — come funziona ogni dominio, codice morto, duplicati.
> - `memoria/MAPPA_ROUTER.md` — 1117 endpoint su 107 prefissi, con uso frontend.
> - `memoria/MAPPA_ENDPOINT_COMPLETA.md` — ogni singolo endpoint.
> - `memoria/MAPPA_COLLEZIONI.md` — 158 collezioni MongoDB con usi reali.

## ARCHITETTURA

**Stack**: FastAPI (Python) + Motor async MongoDB + React 18 + Vite  
**DB**: MongoDB Atlas, cluster `cluster0.vofh7iz`, database `Gestionale`  
**Repo**: `github.com/ceraldicontabilita/gestionale`  
**Deploy**: push su `main` -> **Render** auto-deploy -> impresasemplice.online  
**Design system**: Navy `#0f2744` + Oro `#b8860b`, definito in `frontend/src/lib/utils.js`

## REGOLA CANONICA FORNITORI

La collection MongoDB primaria dei fornitori e':

```text
fornitori
```

`suppliers` resta nome tecnico/inglese per API, moduli e compatibilita', ma non e' una collection Mongo separata.

- API frontend: `/api/suppliers`
- Collection backend: `fornitori`
- Costanti corrette: `COLL_FORNITORI`, `COLL_SUPPLIERS`, `Collections.FORNITORI`, `Collections.SUPPLIERS`
- Memoria di dettaglio: `memoria/FORNITORI_REGOLA_CANONICA.md`

## FLUSSO DATI PRINCIPALE

```text
Email Aruba PEC -> Download fatture XML/P7M -> Parser XML -> invoices
                                                        -> auto-routing cassa/banca
                                                        -> aggiorna fornitore in fornitori

Estratto Conto XLS -> Parser -> estratto_conto_movimenti
                            -> riconciliazione automatica con fatture/partite

Corrispettivi XML -> Parser -> corrispettivi
                           -> split contanti/POS

Cedolini PDF -> Parser Zucchetti -> cedolini
                                -> collegamento dipendente
```

## COLLEZIONI MONGODB PRINCIPALI

| Collezione | Descrizione | Nota |
|---|---|---|
| `invoices` | Fatture ricevute XML | Costi/passive, non ricavi |
| `fornitori` | Anagrafica fornitori | Collection canonica; `suppliers` e' solo alias API/tecnico |
| `prima_nota_cassa` | Movimenti cassa | Contanti |
| `prima_nota_banca` | Movimenti banca manuali | |
| `estratto_conto_movimenti` | Movimenti estratto conto bancario | Fonte riconciliazione |
| `corrispettivi` | Corrispettivi giornalieri | Unica fonte ricavi |
| `cedolini` | Cedolini paga dipendenti | |
| `dipendenti` | Anagrafica dipendenti | Non `employees` |
| `presenze` / `presenze_mensili` | Presenze | Gestire schemi multipli |
| `f24_unificato` | Modelli F24 | Non `f24_models` nei nuovi sviluppi |
| `scadenziario` / `scadenziario_fornitori` | Scadenze pagamenti | |
| `assegni` | Gestione assegni | |
| `warehouse_inventory` | Magazzino reale | Non `warehouse_stocks` come fonte primaria |
| `acquisti_prodotti` | Storico acquisti prodotti | |
| `partite_aperte` | Partite aperte materializzate | Sistema relazionale |
| `alerts` | Alert sistema relazionale | |
| `riconciliazioni_match` | Match riconciliazione | |
| `audit_log` | Log audit | |

## PAGINE E FUNZIONALITA'

### Dashboard

**URL**: `/` o `/dashboard`  
Mostra KPI principali, scadenze e bilancio istantaneo.

Endpoint principali:

- `GET /api/dashboard/bilancio-istantaneo?anno=X`
- `GET /api/scadenze/prossime?giorni=30&limit=8`
- `GET /api/email-download/statistiche`

### Fatture

**URL**: `/fatture`, `/fatture/corrispettivi`, `/fatture/iva`, `/fatture/import`

Funzioni:

- archivio fatture ricevute
- corrispettivi
- IVA
- import documenti

Regola critica: le fatture ricevute stanno in `invoices` e sono costi; i ricavi arrivano solo da `corrispettivi`.

### Fornitori

**URL**: `/fornitori`

Pagina: `frontend/src/pages/Fornitori.jsx`  
Backend: `app/routers/suppliers_module/*`  
API compatibile: `/api/suppliers`  
Collection reale: `fornitori`

Mostra:

- lista fornitori
- P.IVA
- totale fatture
- metodo pagamento
- estratto fatture
- dettaglio anagrafica

Bottoni/azioni principali:

- Nuovo fornitore -> `POST /api/suppliers`
- Aggiorna fornitore -> `PUT /api/suppliers/{id}`
- Elimina fornitore -> `DELETE /api/suppliers/{id}` con conferma frontend
- Estratto fatture -> legge fatture collegate in `invoices`
- Aggiorna OpenAPI -> `POST /api/openapi-imprese/aggiorna-bulk`
- Backfill Autoroute -> `POST /api/fatture-ricevute/backfill-autoroute`

Regole:

- non usare `suppliers` come collection;
- non usare `fornitori_dizionario` come anagrafica;
- il metodo pagamento fornitore guida i flussi di pagamento fattura;
- se cambia metodo pagamento, aggiornare storico/cache/eventi se previsti;
- ogni response backend deve esporre i campi che la pagina legge.

### Prima Nota

**URL**: `/prima-nota`, `/prima-nota/cassa`, `/prima-nota/banca`

Mostra movimenti cassa e banca, saldi e provvisori.

Azioni:

- nuovo movimento cassa/banca
- sposta cassa/banca
- conferma provvisori
- import estratto conto
- registra pagamento

### Dipendenti / HR

**URL**: `/dipendenti`, `/cedolini`, `/presenze`, `/tfr`

Collection canoniche:

- `dipendenti`
- `cedolini`
- `presenze`
- `presenze_mensili`
- `tfr_accantonamenti`
- `acconti_dipendenti`

Non usare `employees` come collection primaria.

### Riconciliazione

**URL**: `/riconciliazione`

Moduli:

- riconciliazione automatica
- gestione assegni
- riconciliazione unificata
- PayPal se abilitato

Collection principali:

- `estratto_conto_movimenti`
- `partite_aperte`
- `riconciliazioni_match`
- `assegni`

### Contabilita'

**URL**: `/contabilita`

Include:

- bilancio
- verifica
- piano dei conti
- cespiti
- chiusura esercizio
- budget
- mutui
- centri costo

### Magazzino

**URL**: `/magazzino`

Collection canonica:

```text
warehouse_inventory
```

`warehouse_stocks` e' legacy/deprecata e non deve essere usata come fonte primaria.

### Strumenti / Integrazioni / Admin

**URL**: `/strumenti`, `/integrazioni`, `/admin`

Funzioni:

- verifica coerenza
- commercialista
- email download
- visure
- OpenAPI
- PagoPA
- batch reprocessing

## BUG PATTERN COMUNI

1. POST/PUT con JSON senza `Body(...)` -> errore reale sui body JSON.
2. Response backend con campi diversi da quelli letti dal JSX -> KPI a 0 o celle vuote.
3. Router creato ma non registrato in `app/router_registry.py` -> 404.
4. Mongo GET senza projection `{ "_id": 0 }` -> ObjectId non serializzabile.
5. `datetime.utcnow()` -> usare `datetime.now(timezone.utc)`.
6. Fetch frontend con filtri senza `AbortController` -> race condition.
7. DELETE senza `window.confirm()` -> rischio eliminazione involontaria.
8. Modali senza overlay click-to-close + `stopPropagation()`.
9. Hardcoded collection invece di costanti centralizzate.
10. Doppia verita' fornitori/suppliers -> usare sempre `fornitori` come collection.

## STATO OPERATIVO MODULI

### Stabile secondo documentazione/test precedenti

- Dashboard grafica
- Fatture ricevute
- Fornitori base
- Prima nota
- Cedolini
- Dipendenti
- F24
- Documenti/import
- Riconciliazione base
- Magazzino
- Corrispettivi
- Scadenze
- Assegni
- TFR

### Parziale / da verificare con test runtime

- Trasferimenti cassa-banca: automatismo lato opposto non completo
- POS-banca: match accredito non sempre robusto
- Alert engine: integrazione non uniforme in tutti i router
- Event bus: verificare copertura effettiva su tutte le mutazioni core
- Netting note credito TD04: riconoscimento presente, netting automatico da verificare
- Merge duplicati fornitori: deduplica presente, UI guidata da verificare

## CHECKLIST AUDIT PER NUOVE MODIFICHE

1. Verificare collection canonica.
2. Verificare route `/api` e registrazione router.
3. Verificare `Body(...)` su POST/PUT.
4. Verificare projection Mongo.
5. Confrontare response backend e JSX.
6. Proteggere DELETE.
7. Verificare modali.
8. Verificare race condition nei fetch.
9. Aggiornare memoria se cambia una regola operativa.
10. Non introdurre nuove dipendenze senza motivo funzionale.

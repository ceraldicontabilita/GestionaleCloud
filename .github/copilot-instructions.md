# Istruzioni per GitHub Copilot / Codex — Ceraldi ERP (gestionale2)

> Leggi prima di suggerire o modificare codice. Questo file descrive lo stato operativo reale dell'app e i pattern che non devono essere violati.

---

## 0. Identita' del progetto

- Azienda: Ceraldi Group S.R.L. — Bar/Pasticceria a Napoli — P.IVA `04523831214`
- Repo: `github.com/ceraldicontabilita/gestionale2`
- Deploy: app.emergent.sh -> `impresasemplice.online`
- Utente unico: sistema non multi-tenant e non multi-utente
- Lingua UI/documentazione: italiano. Codice tecnico in inglese ammesso quando gia' presente.

---

## 1. Stack tecnologico da non cambiare

| Layer | Tecnologia | Vincoli |
|---|---|---|
| Backend | Python 3.x + FastAPI 0.110.1 | Pydantic v2 |
| DB driver | Motor async | No PyMongo sync nei path async |
| DB | MongoDB Atlas, database `Gestionale` | Non usare `azienda_erp_db` |
| Frontend | React 18 + Vite | No Next.js, no CRA |
| Icone | `lucide-react` | Evitare emoji nel codice applicativo |
| Styling | Inline-style con `COLORS`, `STYLES`, `SPACING` da `frontend/src/lib/utils.js` | No Tailwind, no shadcn/ui, no styled-components |
| Scheduler | APScheduler | Job PEC/Gmail/scadenze |
| Email | IMAP sincrono dentro `asyncio.to_thread()` | Non bloccare event loop |
| Auth | JWT middleware globale | `AUTH_DISABLED=true` solo in dev |

---

## 2. Regola canonica fornitori/suppliers

La collection MongoDB canonica per l'anagrafica fornitori e':

```text
fornitori
```

`suppliers` resta solo nome tecnico/API/legacy per moduli, servizi, route e compatibilita'. Non deve indicare una collection MongoDB separata.

Fonti di verita':

```python
# app/db_collections.py
COLL_SUPPLIERS = "fornitori"
COLL_FORNITORI = "fornitori"

# app/database/collections.py
Collections.FORNITORI = "fornitori"
Collections.SUPPLIERS = "fornitori"

# app/database.py legacy
Collections.SUPPLIERS = "fornitori"
```

Regole:

- API frontend: mantenere `/api/suppliers` per compatibilita'.
- Collection Mongo: usare sempre `fornitori` tramite costanti.
- Vietato introdurre `db["suppliers"]` o nuove collection fornitori.
- Vietato usare `fornitori_dizionario` come anagrafica primaria.
- Vedere `memoria/FORNITORI_REGOLA_CANONICA.md` per il dettaglio.

---

## 3. Architettura backend

```text
backend/server.py             entry point Supervisor/uvicorn, non eliminare
app/main.py                   FastAPI app
app/router_registry.py        unico punto di registrazione router
app/database.py               connessione MongoDB + Collections legacy
app/db_collections.py         costanti collection principali
app/database/collections.py   costanti collection class-based
app/services/                 event bus, alert, audit, deduplica, riconciliazione
app/scheduler.py              job schedulati
```

Endpoint sempre sotto `/api/`:

```python
app.include_router(router, prefix="/api/foo", tags=["Foo"])
```

Creare `app/routers/foo.py` non basta: il router deve essere registrato in `app/router_registry.py`.

---

## 4. Collezioni MongoDB canoniche

| Collezione | Ruolo | Nota |
|---|---|---|
| `invoices` | Fatture ricevute/passive XML SDI | Non usare `fatture` come collection |
| `fornitori` | Anagrafica fornitori | Collection canonica; `suppliers` e' alias tecnico/API |
| `dipendenti` | Anagrafica HR | Non usare `employees` come collection |
| `cedolini` | Buste paga | Parser Zucchetti |
| `corrispettivi` | Unica fonte ricavi | Le `invoices` sono costi |
| `prima_nota_cassa` | Movimenti cassa | Contanti e corrispettivi contanti |
| `prima_nota_banca` | Movimenti banca manuali | |
| `estratto_conto_movimenti` | Movimenti bancari importati | Fonte riconciliazione |
| `f24_unificato` | Modelli F24 | Non usare `f24_models` per nuovi sviluppi |
| `warehouse_inventory` | Magazzino reale | Non usare `warehouse_stocks` come fonte primaria |
| `partite_aperte` | Scadenziario materializzato | Alimentato da event bus |
| `riconciliazioni_match` | Match riconciliazione | Relazioni N:M |
| `alerts` | Alert attivi/risolti | Usare codici catalogati |
| `audit_log` | Audit unificato | |

---

## 5. Pattern critici da rispettare

### POST/PUT con JSON: `Body(...)` obbligatorio

```python
from fastapi import Body

@router.post("")
async def crea(data: dict = Body(...)):
    ...
```

Senza `Body(...)` i POST reali possono fallire con 422/502.

### Response backend = campi frontend

Prima di chiudere una feature, aprire il router e verificare che i nomi delle chiavi restituite coincidano con quelli letti nel JSX. Evitare fallback silenziosi con `|| 0` quando `0` e' valore valido: preferire `??`.

### Mongo GET: niente `_id` non serializzabile

```python
docs = await db[COLLECTION].find(query, {"_id": 0}).to_list(None)
```

### Timezone

```python
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
```

Non usare `datetime.utcnow()`.

### IMAP

```python
raw = await asyncio.to_thread(sync_imap_fetch, user, password)
```

### Modali frontend

Overlay con click-to-close e contenuto con `stopPropagation()`.

### DELETE frontend

Ogni DELETE deve essere protetto da `window.confirm()`.

### useEffect con filtri

Per fetch dipendenti da filtri/anno/mese, usare `AbortController` o controllo equivalente per evitare race condition.

---

## 6. Regole contabili/business non negoziabili

- Ricavi solo da `corrispettivi`.
- `invoices` = fatture ricevute/passive/costi.
- Metodo pagamento fattura preso dall'anagrafica fornitore, non dall'XML SDI.
- Note credito TD04: importo negativo e badge/gestione coerente.
- Corrispettivi split: contanti -> `prima_nota_cassa`, POS -> partita/attesa banca.
- Conto economico: schema civilistico italiano.
- Non inventare aliquote, percentuali fiscali o regole paghe se il dato manca.

---

## 7. Frontend: file chiave

- `frontend/src/main.jsx` — route lazy
- `frontend/src/App.jsx` — menu e layout
- `frontend/src/api.js` — client axios
- `frontend/src/lib/utils.js` — design system unico
- `frontend/src/pages/Fornitori.jsx` — pagina anagrafica fornitori
- `frontend/src/pages/hub/` — hub principali
- `frontend/src/pages/hr/` — modulo HR

Nuove pagine: aggiungere lazy route in `main.jsx` e voce menu in `App.jsx` solo se necessario.

---

## 8. Cose da non proporre

- Migrare a Tailwind, shadcn, styled-components o TypeScript.
- Sostituire Motor con un ODM.
- Spostare endpoint fuori da `/api/`.
- Eliminare `backend/server.py`.
- Cambiare database `Gestionale`.
- Rimuovere event bus/sistema relazionale.
- Creare una collection `suppliers` separata.
- Fare refactor massivi solo stilistici.

---

## 9. Checklist prima di modificare

1. Cercare endpoint/file simili esistenti.
2. Verificare registrazione in `router_registry.py`.
3. Verificare `Body(...)` sui POST/PUT JSON.
4. Verificare campi response backend vs JSX.
5. Verificare projection `{ "_id": 0 }` nei GET.
6. Verificare collezioni tramite costanti, non stringhe hardcoded.
7. Per fornitori: collection `fornitori`, API `/api/suppliers`.
8. Verificare modali e confirm DELETE.
9. Evitare race condition nei fetch con filtri.
10. Se una modifica e' dubbia, segnalarla come P3 invece di inventare.

---

Ultimo aggiornamento: Aprile 2026 — audit coerenza fornitori/suppliers e regole canoniche.

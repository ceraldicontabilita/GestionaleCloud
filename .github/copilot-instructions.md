# Istruzioni per GitHub Copilot / Codex — Ceraldi ERP (gestionale2)

> **Leggi prima di suggerire.** Questo file descrive lo **stato reale** dell'app al
> 22 Aprile 2026. Se il tuo suggerimento contraddice uno dei pattern qui sotto,
> **non è un miglioramento, è una regressione**: il pattern esiste perché abbiamo
> già sbattuto la testa contro quel bug. Non proporre refactor "stilistici" che
> cambiano stack, librerie o convenzioni.

---

## 0. Identità del progetto

- **Azienda**: Ceraldi Group S.R.L. — Bar/Pasticceria a Napoli — P.IVA `04523831214`
- **Repo**: `github.com/ceraldicontabilita/gestionale2`
- **Deploy**: app.emergent.sh → `impresasemplice.online`
- **Utente unico**: sistema NON multi-tenant, NON multi-utente (il proprietario è Enzo Ceraldi)
- **Lingua**: commenti, nomi, messaggi di UI in **italiano**. Codice tecnico in inglese OK.

---

## 1. Stack tecnologico (NON cambiare)

| Layer | Tecnologia | Vincoli |
|---|---|---|
| Backend | Python 3.x + FastAPI 0.110.1 | Pydantic v2 |
| DB driver | **Motor 3.3.1** (MongoDB async) | NO PyMongo sync in path async |
| DB | **MongoDB Atlas** — cluster `cluster0.vofh7iz` — database **`Gestionale`** | NON `azienda_erp_db` |
| Frontend | **React 18 + Vite** | NO Next.js, NO CRA |
| Icone | `lucide-react` only | NO emoji nel codice (OK solo in label visibili) |
| Styling | **Inline-style con `COLORS`/`STYLES`/`SPACING`** da `frontend/src/lib/utils.js` | **NO Tailwind**, **NO shadcn/ui**, **NO styled-components**, **NO CSS-in-JS** runtime |
| Scheduler | APScheduler (AsyncIOScheduler) | Richiede `tzlocal` + `pytz` in `requirements.txt` |
| Email | `IMAPClient` sincrono in `asyncio.to_thread()` | Non chiamare IMAP in event loop |
| Auth | JWT middleware globale | `AUTH_DISABLED=true` in dev — ma in prod sì |

### Regola design frontend (ASSOLUTA)

```jsx
// ✅ CORRETTO
import { COLORS, STYLES, SPACING } from '../../lib/utils';
<div style={{ backgroundColor: COLORS.primary, padding: SPACING.lg }}>…</div>

// ❌ VIETATO
<div className="bg-blue-500 p-4">…</div>              // Tailwind NO
import { Button } from "@/components/ui/button";       // shadcn NO
const Styled = styled.div`color: red;`                 // styled-components NO
```

### Palette brand (inline-style)

```
primary   #0f2744   navy profondo — sidebar, header, bottoni primari
accent    #b8860b   oro — accenti, CTA secondarie
success   #15803d   pagato, approvato
warning   #b45309   in attesa, da verificare
danger    #b91c1c   scaduto, eliminazione, errore
info      #1d4ed8   info, link
```

---

## 2. Architettura backend

```
backend/server.py          entry point Supervisor/uvicorn — NON ELIMINARE
└─ from app.main import app
app/main.py                FastAPI app (~176 router registrati)
app/router_registry.py     punto unico di include_router(), un router non
                           registrato qui è INVISIBILE (causa 404)
app/database.py            Database.get_db() → sempre questo, mai Mongo diretto
app/database/collections.py  costanti nomi collezioni — usare queste
app/services/event_bus.py  20 handler su 16 event types
app/scheduler.py           9 job APScheduler
app/utils/dependencies.py  get_current_user (JWT)
```

### Endpoint: sempre sotto `/api/`

```python
# ✅ CORRETTO
app.include_router(router, prefix="/api/foo", tags=["Foo"])

# ❌ VIETATO
app.include_router(router, prefix="/foo", …)   # niente /api = 404 dal frontend
```

---

## 3. Pattern critici — violare = introdurre bug già visti

Questi pattern sono figli di bug realmente accaduti in produzione. Se scrivi
codice che li viola, stai regredendo l'app.

### 3.1 `Body(...)` OBBLIGATORIO su POST/PUT con body JSON

```python
from fastapi import APIRouter, Body, Depends

# ✅ CORRETTO
@router.post("")
async def crea(data: Dict[str, Any] = Body(...),
               current_user = Depends(get_current_user)):
    ...

# ❌ SBAGLIATO — produce 502 al primo POST reale
@router.post("")
async def crea(data: Dict[str, Any],  # manca Body(...)
               current_user = Depends(get_current_user)):
    ...
```

**Perché**: senza `Body(...)` FastAPI prova a trattare `data` come query/form param e il parser esplode su body JSON. Abbiamo fixato 21 router con questo bug il 22/04/2026. Ogni nuovo router POST/PUT deve importare `Body` e usarlo.

### 3.2 Response backend = campi frontend

**Prima di chiudere una feature**, verificare che i campi restituiti dal router
siano **esattamente** quelli letti dal JSX. Incoerenza = `€0,00`, campi vuoti,
avatar senza nome, ecc.

**Esempio reale (assegni)**:
- PUT scrive `numero_fattura`
- GET restituisce `fattura_numero`
- Frontend mostra `numero_fattura` → vede `undefined` → `—`

Se modifichi uno dei due lati, aggiorna anche l'altro.

### 3.3 Router DEVE essere in `router_registry.py`

Creare il file `app/routers/xxx.py` con `router = APIRouter()` non basta:
**aggiungere `include_router` in `app/router_registry.py`** altrimenti ogni
chiamata dà 404. Il 22/04/2026 abbiamo scoperto 2 router orfani
(`timbrature.py`, `email_f24.py`).

### 3.4 Modali: overlay click-to-close + stopPropagation

```jsx
// ✅ CORRETTO
<div
  onClick={close}
  style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15,23,42,0.55)' }}
>
  <div onClick={e => e.stopPropagation()} style={{ /* contenuto */ }}>
    …
  </div>
</div>

// ❌ SBAGLIATO — modale non si chiude cliccando fuori,
//               oppure si chiude cliccando dentro per errore
```

### 3.5 DELETE sempre dietro `window.confirm`

```jsx
// ✅
if (!window.confirm(`Eliminare "${item.nome}"?`)) return;
await api.delete(`/api/foo/${item.id}`);
```

Scan confermato: 85 pagine JSX, 0 DELETE senza conferma. Non introdurne nuovi.

### 3.6 Hooks nei sub-componenti

Ogni sub-componente che usa `useIsMobile`, `useAnnoGlobale`, ecc. deve
**importarlo e chiamarlo al proprio interno**. Non passarlo come prop tra
molti livelli.

### 3.7 MongoDB: projection + timezone

```python
# ✅ CORRETTO
from datetime import datetime, timezone
now = datetime.now(timezone.utc)                        # NO utcnow() (naive)
docs = await db["collection"].find({}, {"_id": 0}).to_list(None)
```

- `{"_id": 0}` in ogni `find/find_one` di GET endpoint → altrimenti JSON non serializzabile
- `datetime.now(timezone.utc)` sempre — `datetime.utcnow()` deprecato e naive

### 3.8 IMAP sempre in thread

```python
raw = await asyncio.to_thread(sync_imap_fetch, user, password)   # ✅
imap = imaplib.IMAP4_SSL("imap.gmail.com")                        # ❌ blocca loop
```

### 3.9 Event bus: handler in try/except

```python
# ✅ propagate_event lo fa già via register_handler.
# Se scrivi propagazioni manuali, wrappa:
try:
    await handler(payload)
except Exception:
    logger.exception("handler fallito")   # NON rilanciare
    # operazione primaria deve continuare
```

### 3.10 Validazione date (lezione appena imparata)

Endpoint che accettano range di date (missioni, ferie, scadenze) devono:
- Validare formato ISO (`YYYY-MM-DD` o `YYYY-MM-DDTHH:MM:SS[Z]`)
- Rifiutare `data_fine < data_inizio`
- In update, confrontare con il valore esistente se si aggiorna solo una data

Vedere `app/routers/employees/missioni.py` per il pattern `_parse_date` + `_validate_date_range`.

### 3.11 Race condition su fetch con filtri (lezione Codex P2)

Ogni `useEffect` che fa `api.get` dipendente da filtri (anno, mese, competenza, ecc.) è vulnerabile: cambiando rapidamente il filtro, più richieste restano in volo e una risposta lenta può sovrascrivere lo stato con dati della query sbagliata.

```jsx
// ✅ CORRETTO
useEffect(() => {
  const controller = new AbortController();
  (async () => {
    try {
      const { data } = await api.get(url, {
        params,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setState(data);
    } catch (e) {
      if (e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED') return;
      // errore reale
    }
  })();
  return () => controller.abort();
}, [filtro1, filtro2]);

// ❌ SBAGLIATO — cambio rapido filtro = dati dell'anno sbagliato
useEffect(() => {
  api.get(url).then(r => setState(r.data));
}, [filtro]);
```

Vedere `frontend/src/pages/hr/HRTFR.jsx` e `frontend/src/pages/hr/HRAcconti.jsx` per il pattern.

### 3.12 Controlla TUTTI i writer di una collection prima di scrivere un reader (lezione Codex P1)

Una singola collezione Mongo può avere **più writer con schemi diversi**. Prima di scrivere un endpoint che legge una collection, cercare globalmente tutti gli writer:

```bash
grep -rn 'db\["<collection>"\].insert\|db\["<collection>"\].update' app/ --include="*.py"
```

Se trovi schemi diversi (es. `presenze` che ha documenti `flat` da batch-insert e documenti `nested` da libro unico PDF), il tuo reader deve gestire **tutti**. Codex becca questi bug perché analizza il repo intero; io no, perché di default guardo solo il producer più vicino alla mia task. **Quindi devo cercare esplicitamente.**

Vedere `app/routers/attendance.py::get_month_grid` per il pattern di reader che gestisce due schemi.

### 3.13 Response API = campi frontend (pattern #2 esteso)

Prima di dichiarare `setState({ totale: d.nome_campo || 0 })`, **aprire il file del router** e copiare il nome esatto del campo dalla `return {...}` finale. I `|| 0` fallback silenziano il bug: il KPI mostra 0 e sembra corretto. Sostituire `||` con `??` quando 0 è un valore legittimo (es. nessuna liquidazione quest'anno ma API funzionante).

```javascript
// ❌ SBAGLIATO — la chiave reale è "totale_fondo_tfr", bug silenzioso
totale: d.totale_fondo || 0

// ✅ CORRETTO
totale: d.totale_fondo_tfr ?? 0  // nome verificato in app/routers/tfr.py:405
```

---

## 4. Collezioni MongoDB canoniche

| Collezione | Ruolo | Nota |
|---|---|---|
| `invoices` | Fatture ricevute (XML SDI) | USARE QUESTA, non "fatture" |
| `suppliers` | Fornitori | USARE QUESTA, non "fornitori" |
| `dipendenti` | Anagrafica HR | USARE QUESTA, non "employees" |
| `cedolini` | Buste paga | Parser Zucchetti |
| `corrispettivi` | **UNICA fonte ricavi** | XML corrispettivi AE |
| `prima_nota_cassa` | Movimenti cassa | Solo contanti + corrispettivi contanti |
| `prima_nota_banca` | Movimenti banca manuali | |
| `estratto_conto_movimenti` | Movimenti bancari importati | Fonte per riconciliazione |
| `partite_aperte` | Partite materializzate | Alimentate dall'event bus |
| `alerts` | Alert del sistema relazionale | |
| `scadenziario` | Scadenze pagamenti | |
| `assegni` | Gestione assegni | |
| `cespiti` | Cespiti aziendali | |
| `shifts_tipi` / `shifts_assegnazioni` | Turni HR | Nuovi, non in conflitto |
| `missioni` | Missioni/trasferte HR | Workflow approvazione |
| `documenti_hr` | Documenti dipendente | |
| `f24_documenti` | F24 | |
| `audit_log` | Audit | |

Costanti in `app/database/collections.py` — non hardcodare stringhe nuove se
esiste già la costante.

---

## 5. Sistema relazionale (event bus + scheduler)

### Event bus (`app/services/event_bus.py`)

- **20 handler** registrati su **16 event types** via `register_all_handlers()`
- Handler organizzati in `app/services/handlers/` (banca, cedolino, corrispettivo, dipendente, documento, f24, fattura, magazzino, trasferimento)
- Ogni handler wrappato in `try/except` con `logger.exception()` — un handler fallito NON blocca l'operazione primaria
- Dashboard su `/dashboard-relazionale`

Quando aggiungi una nuova mutazione (create/update/delete di entità core),
chiediti: **serve emettere un evento?** Se sì, segui lo stile di
`app/services/handlers/*_handlers.py`.

### Scheduler (`app/scheduler.py`, 9 job)

Job attivi:
- `pec_hourly_download_task` (ogni ora) — download PEC Aruba
- `sync_gmail_aruba_task` (10 min) — sync Gmail
- `scan_verbali_email_task` (30 min)
- `check_scadenze_partite_task` (giornaliero 07:00) — genera alert su scadenze: `FAT_DA_PAGARE_SCADUTA`, `F24_SCADUTO`, `CED_NON_PAGATO`, `BNK_POS_NON_RICONCILIATO` da `partite_aperte` scadute
- `check_scadenze_f24_task` (08:00 + 14:00)
- `gmail_full_scan_task` (ogni ora)

Il catalogo alert ha **61 codici**. `genera_alert()` è idempotente.
`on_fattura_pagata_risolvi` chiude anche la partita collegata.

---

## 6. Regole contabili italiane (NON negoziabili)

- **Corrispettivi** = UNICA fonte ricavi (collezione `corrispettivi`)
- **Fatture ricevute** = COSTI passivi (collezione `invoices`)
- **Cedolini** = buste paga (collezione `cedolini`)
- **Conto economico**: schema **art. 2425 c.c.** (CEE)
- **Auto aziendali**: deducibilità 20%, IVA detraibile 40% (art. 164 TUIR)
- **Telefonia**: deducibilità 80%, IVA detraibile 50% (art. 102 TUIR)
- **TFR**: quota = `retribuzione / 13.5`, rivalutazione = `1.5% + 75% ISTAT`
- **Corrispettivi split**: contanti → `prima_nota_cassa`, POS → `prima_nota_banca` (partita attesa fino a match con accredito EC)

Non inventare aliquote o percentuali: se manca un dato, chiedere prima di scrivere.

---

## 7. Frontend: file chiave

- `frontend/src/main.jsx` — router (`createBrowserRouter`), tutte le pagine lazy
- `frontend/src/App.jsx` — layout principale, `ALL_NAV_ITEMS` = menu
- `frontend/src/lib/utils.js` — `COLORS`, `STYLES`, `SPACING`, `useIsMobile`, `pagePad`, `cn`
- `frontend/src/api.js` — axios client (baseURL, interceptor auth)
- `frontend/src/contexts/` — `AuthContext`, `AnnoContext`
- `frontend/src/pages/hr/` — HR module pages (HRDipendenti, HRPresenze, HRCedolini, HRTFR, HRTurni, HRMissioni, HRDocumenti, HRFeriePermessi, HRHub)
- `frontend/src/pages/hub/` — Hub pages (DashboardHub, FornitoriHub, PrimaNotaHub, VeicoliHub, ContabilitaHub, MagazzinoHub, DocumentiHub, StrumentiHub, IntegrazioniHub, AdminHub, RiconciliazioneHub, FattureHub)

**91 pagine totali**. Nuove pagine: lazy-load in `main.jsx` + route + link menu
in `App.jsx` (sezione `ALL_NAV_ITEMS`).

---

## 8. Stato per modulo (aggiornato)

### ✅ Stabile

Fatture ricevute (XML+P7M, dedup hash, auto-routing), Fornitori (dedup P.IVA, estratto fatture, OpenAPI), Prima Nota Cassa+Banca, Cedolini (parser Zucchetti), Dipendenti (fascicolo, 3 strategie match stipendi), F24 (import+riconciliazione), Documenti/Inbox (upload auto), Riconciliazione (auto+manuale+multipla), Magazzino, Corrispettivi, IVA progressivo, Scadenze, Assegni, TFR, **Turni** (PR #3), **Missioni** (PR #4), **Documenti HR** (PR #5), **Ferie&Permessi** workflow (PR #6), **HR Hub** (PR #7).

### ⚠️ Parziale (non regredire ulteriormente)

- Trasferimenti cassa↔banca: `sposta-movimento` non crea lato opposto auto
- POS→banca: match con accredito EC non robusto al 100%
- Alert engine: servizio creato ma integrazione router non ovunque
- Netting note credito TD04: riconoscimento sì, netting auto no
- Merge duplicati fornitori: UI guidata mancante
- Scoring completezza anagrafica dipendente

### ❌ Da implementare (NON proporre di fare, non è ancora nei piani)

- Audit trail modifiche anagrafiche (chi/quando modifica fornitore o dipendente)

---

## 9. Cose che NON devi suggerire

- ❌ Migrare a Tailwind / shadcn / CSS modules
- ❌ Convertire inline-style a styled-components
- ❌ Aggiungere TypeScript (frontend è JS, non tocchiamo ora)
- ❌ Sostituire Motor con Beanie/ODMantic
- ❌ Spostare endpoint fuori da `/api/`
- ❌ Eliminare `backend/server.py` (è l'entry Supervisor)
- ❌ Cambiare nome database (è `Gestionale`, non altro)
- ❌ "Semplificare" rimuovendo il sistema relazionale/event bus
- ❌ Suggerire di aggiungere `datetime.utcnow()` — è deprecato, usa `datetime.now(timezone.utc)`
- ❌ Suggerire `find_one` senza `{"_id": 0}` nei GET
- ❌ Proporre PR di "cleanup" che cambiano centinaia di file senza motivo funzionale
- ❌ Introdurre nuove dipendenze senza giustificazione (chiedere all'autore prima)

---

## 10. Cosa fare SEMPRE prima di suggerire

1. Controlla se esiste già un file/endpoint simile (`grep` su `app/routers/` e `frontend/src/pages/`)
2. Verifica che il router sia in `router_registry.py`
3. Verifica che `Body(...)` sia sui POST/PUT
4. Verifica che la risposta backend abbia gli stessi nomi di campo del frontend
5. Verifica `{"_id": 0}` nelle `find`
6. Verifica modale con overlay+stopPropagation
7. Verifica `window.confirm` sui DELETE
8. Verifica inline-style con `COLORS`/`SPACING`, zero Tailwind

Se sei incerto, **segnala con `P3` (dubbio)** invece di inventare.

---

## 11. File di riferimento

- `memoria/INDEX.md` — indice documentazione
- `memoria/MAPPA_APPLICAZIONE.md` — mappa pagine + endpoint (fonte autorevole)
- `memoria/LOGICA_OPERATIVA.md` — regole business
- `memoria/PRD.md` — requisiti prodotto
- `memoria/STATO_STABILITA.md` — ultimo audit stabilità
- `PIANO_LAVORO_RELAZIONALE.md` — event bus + partite aperte

---

_Ultimo aggiornamento: 22 Aprile 2026_
_Autore: Enzo Ceraldi (proprietario) + sessioni Claude/Codex_

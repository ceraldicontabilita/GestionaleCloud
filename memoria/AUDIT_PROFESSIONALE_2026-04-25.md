# Audit professionale Ceraldi ERP

Data: 25 Aprile 2026
Repo: `ceraldicontabilita/gestionale2`
Branch: `main`

## Sintesi

Audit statico eseguito su repository GitHub con correzioni dirette su documentazione, memorie e alcuni file backend.

Il problema piu' critico trovato era la doppia interpretazione `fornitori` / `suppliers`.
La regola definitiva ora e':

- collection Mongo reale: `fornitori`
- API compatibile: `/api/suppliers` e `/api/fornitori`
- `suppliers` non deve essere usato come collection separata

## Correzioni applicate

### 1. Modulo fornitori

File modificato:

- `app/services/suppliers/constants.py`

Ora `SUPPLIERS` punta a `COLL_FORNITORI`, quindi alla collection `fornitori`.

### 2. Documentazione principale

File modificati:

- `README.md`
- `.github/copilot-instructions.md`
- `memoria/MAPPA_APPLICAZIONE.md`

Ora tutti spiegano che `fornitori` e' la collection canonica e che `suppliers` resta solo alias/API.

### 3. Nuova memoria dedicata

File creato:

- `memoria/FORNITORI_REGOLA_CANONICA.md`

Contiene la regola operativa definitiva per evitare regressioni future.

### 4. Timezone router veicoli

File modificato:

- `app/routers/veicoli.py`

Sostituito `datetime.utcnow()` con timestamp UTC timezone-aware.

## Verifiche effettuate

### Collection fornitori

Controllate le fonti centrali:

- `app/db_collections.py`
- `app/database/collections.py`
- `app/database.py`

Risultato: tutte puntano a `fornitori`.

### Accessi diretti a suppliers

Ricerca effettuata su:

- `db["suppliers"]`
- `db['suppliers']`

Risultato: nessun accesso diretto trovato.

### Router fornitori

`app/router_registry.py` registra correttamente lo stesso router su:

- `/api/suppliers`
- `/api/fornitori`

Decisione: mantenere entrambi. Rinominare a tappeto romperebbe compatibilita'.

## Problemi residui da verificare

### P1 - Test runtime mancanti

Non e' stato possibile avviare backend/frontend da questa sessione. Da verificare in ambiente reale:

- health backend
- caricamento frontend
- login/sessione
- pagine principali
- import documenti
- parser XML/PDF
- riconciliazione
- scheduler PEC/Gmail

### P1 - Campi backend/frontend

Da controllare pagina per pagina: i campi restituiti dai router devono combaciare con quelli letti dai JSX.

Priorita':

- Fornitori
- Fatture
- Dashboard
- Prima Nota
- Magazzino
- Riconciliazione

### P1 - POST/PUT con Body

La documentazione precedente dice che molti router sono gia' stati corretti, ma serve uno scan AST completo prima del deploy.

### P2 - datetime.utcnow residui

Sono rimasti usi di `datetime.utcnow()` in alcuni servizi collegati a verbali, PayPal e learning. Vanno corretti con test dedicato per evitare regressioni nei confronti data.

### P2 - Hardcoded collection

Continuare a ridurre stringhe hardcoded. Ogni nuovo sviluppo deve usare costanti centralizzate.

## Test minimi consigliati prima del deploy

Backend:

```bash
curl -s http://localhost:8001/api/health
curl -s http://localhost:8001/api/suppliers?limit=5
curl -s http://localhost:8001/api/fornitori?limit=5
curl -s http://localhost:8001/api/dashboard/bilancio-istantaneo?anno=2026
```

Frontend:

- `/`
- `/fatture`
- `/fornitori`
- `/prima-nota`
- `/magazzino`
- `/riconciliazione`
- `/contabilita`
- `/dipendenti`
- `/cedolini`
- `/strumenti`
- `/admin`

## Stato

Correzioni sicure applicate.
Audit statico avviato e documentato.
Audit runtime ancora da eseguire in ambiente applicativo.

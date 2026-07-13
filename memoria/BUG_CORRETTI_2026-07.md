# BUG CORRETTI — luglio 2026 (esecuzione PROMPT_DEFINITIVO, FASE P0)

Ogni bug: problema → correzione → test di regressione. Baseline `b9ff5c7` (257 test).

## P0.1 — Widget F24 conta la sorgente sbagliata ✅
- **File**: `app/routers/scadenze.py` (`dashboard-widget`).
- **Problema**: due `count_documents` sulla STESSA collezione `f24_unificato` con schemi
  di campo diversi (`data_scadenza`/`pagato` e `scadenza`/`status`), **sommate** →
  doppio conteggio sui documenti con entrambi gli schemi; la query legacy pescava a vuoto.
- **Fix**: unica funzione `conta_f24_da_pagare(db, limite_30)` che legge solo la
  collezione canonica e conta i documenti **distinti** una volta, coprendo entrambi gli schemi.
- **Test**: `tests/test_p0_01_widget_f24.py` (manuale+email stesso conteggio; no doppioni).

## P0.2 — Auto-riconciliazione filtra importi negativi inesistenti ✅
- **File**: `app/routers/batch_operations.py` (`/auto-riconcilia-tutto`).
- **Problema**: filtro `importo < 0`, ma le uscite sono spesso salvate come importo
  **positivo** con `tipo="uscita"` → zero candidati.
- **Fix**: `filtro_uscite_da_riconciliare()` = uscite per `tipo="uscita"` OPPURE importo<0,
  escludendo i già riconciliati (anche `True`).
- **Test**: `tests/test_p0_02_auto_riconcilia.py`.

## P0.4 — Verbali cercano un campo fattura inesistente ✅
- **File**: `app/routers/verbali_riconciliazione.py` (`riconcilia_verbale`).
- **Problema**: ricerca su `items.descrizione`/`items.description`, ma su `invoices` le
  righe stanno in `linee` → il verbale nelle righe non veniva mai trovato.
- **Fix**: `campi_ricerca_verbale_in_fattura()` usa `linee.descrizione`/`linee.description`
  e fa l'escape regex del numero verbale.
- **Test**: `tests/test_p0_04_verbali_linee.py`.

## P0.5 — Stato assegno non valido ✅
- **File**: `app/routers/bank/assegni.py` (`/correggi-associazione`).
- **Problema**: scriveva `stato="associato"`, valore **non presente** in `ASSEGNO_STATI`
  → assegno fuori schema, invisibile ai filtri per stato.
- **Fix**: stato canonico `assegnato`. Migrazione non distruttiva
  `app/scripts/migra_stato_assegni_associato.py` (dry-run/`--esegui`, idempotente).
- **Test**: `tests/test_p0_05_assegno_stato.py`.

## P0.11 — Gestione riservata protetta solo dal frontend ✅
- **File**: `app/routers/gestione_riservata.py` + `frontend/src/pages/GestioneRiservata.jsx`.
- **Problema**: gli endpoint `/movimenti`, `/riepilogo`, `/volume-affari-reale` NON
  verificavano il codice (solo `/login`); il login loggava il codice errato in chiaro.
- **Fix**: dipendenza `richiedi_codice_riservato` (header `X-Reserved-Code`, confronto
  `secrets.compare_digest`, **fail-closed** 503 se non configurato) applicata a tutti gli
  endpoint dati; nessun log del segreto. Frontend invia il codice come header.
- **Test**: `tests/test_p0_11_gestione_riservata.py` (negato senza/errato, fail-closed, no-log).

## P0.12 — Token/api-key in query string ✅
- **File**: `app/routers/public_api.py` (API pubblica v1).
- **Problema**: `?api_key=` obbligatoria in query (loggabile) su `/v1/fatture|movimenti|stats`.
- **Fix**: dipendenza `richiedi_api_key` — header `X-API-Key` preferito, query deprecata come
  fallback con warning; la chiave non viene loggata.
- **Test**: `tests/test_p0_12_api_key_header.py`.

## In lavorazione
- P0.3 (Libro Unico `employees` vs `dipendenti`), P0.6 (force-reimport), P0.7 (F24 banca
  collection), P0.8 (parser F24 DTO), P0.9 (pagamento idempotente), P0.10 (job state).

---
_Stato test: 273 verdi (baseline 257 + 16 nuovi). App boota (1111 route), build frontend verde._

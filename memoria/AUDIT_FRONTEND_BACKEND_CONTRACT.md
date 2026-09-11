# Audit frontend ↔ backend — GestionaleCloud

> Generato da `scripts/audit_frontend_backend_contract.py`. Non modificare a mano.
> Il contratto HTTP per metodo+path resta verificato da `tests/test_frontend_api_contract.py`.
> Gli scarti statici qui sotto sono candidati da verificare, non prove di endpoint rotti.

## Riepilogo

- Pagine canoniche censite: **64**
- Voci di navigazione analizzate: **24**
- Riferimenti API frontend distinti: **446**
- Path API backend distinti: **1070**
- Errori strutturali verificabili: **0**
- Riferimenti frontend senza match statico: **7**
- Riferimenti frontend riconosciuti come soli prefissi: **2**
- `NotImplementedError` applicativi da verificare: **11**

## Errori strutturali

- Nessuno.

## Avvisi di routing

- catalogo non riconducibile direttamente al router: `/verbali-noleggio/:identificativo`

## Riferimenti frontend senza match statico

- `/api/agenti/run*`
- `/api/download/*`
- `/api/f24/avviso-bonario/controllo.`
- `/api/fatture-ricevute/statistiche*`
- `/api/iva/ricalcola-attribuzione*`
- `/api/noleggio/fatture-non-associate*`
- `/api/noleggio/riepilogo-controlli*`

## Prefissi API frontend

- `/api/fatture`
- `/api/verifica-coerenza/iva`

## Funzioni non implementate da verificare

- `app/hr/db_supabase.py:116`
- `app/hr/db_supabase.py:132`
- `app/hr/db_supabase.py:188`
- `app/hr/db_supabase.py:238`
- `app/hr/db_supabase.py:255`
- `app/hr/db_supabase.py:277`
- `app/hr/db_supabase.py:374`
- `app/hr/db_supabase.py:414`
- `app/services/accounting_entries_service.py:265`
- `app/services/sheets_document_store.py:1009`
- `app/services/vat_f24_service.py:289`

## Regola di chiusura

Il punto 3 si chiude con zero errori strutturali, contratto HTTP verde,
scarti statici classificati con evidenza e `NotImplementedError` applicativi
dimostrati non raggiungibili oppure trasformati in comportamento esplicito/testato.

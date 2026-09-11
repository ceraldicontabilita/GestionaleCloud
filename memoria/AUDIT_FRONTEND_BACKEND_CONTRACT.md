# Audit frontend ↔ backend — GestionaleCloud

> Generato da `scripts/audit_frontend_backend_contract.py`. Non modificare a mano.
> Gli scarti API sono candidati da verificare: il parser statico non sostituisce un collaudo runtime.

## Riepilogo

- Pagine canoniche censite: **64**
- Voci di navigazione analizzate: **24**
- Riferimenti API frontend distinti: **470**
- Path API backend distinti: **1068**
- Errori strutturali verificabili: **0**
- Riferimenti frontend senza match backend: **13**
- Riferimenti frontend riconosciuti come soli prefissi: **5**
- `NotImplementedError` applicativi da verificare: **11**

## Errori strutturali

- Nessuno.

## Avvisi di routing

- Nessuno.

## Riferimenti frontend senza endpoint compatibile

- `/api/admin/rollback/drive-fatture/${elimina`
- `/api/agenti/automazioni/${sospendi`
- `/api/agenti/decisioni/*/${approva`
- `/api/agenti/run*`
- `/api/download/${encodeURIComponent`
- `/api/f24/avviso-bonario/controllo.`
- `/api/fatture-ricevute/auto-ricostruisci-dati`
- `/api/fatture-ricevute/statistiche*`
- `/api/health`
- `/api/iva/ricalcola-attribuzione*`
- `/api/noleggio/fatture-non-associate*`
- `/api/noleggio/riepilogo-controlli*`
- `/api/ws/notifications`

## Prefissi API frontend

- `/api/dati-isa`
- `/api/fiscal/declarations/${encodeURIComponent`
- `/api/fiscal/documents/${encodeURIComponent`
- `/api/paypal-statements/transactions/${encodeURIComponent`
- `/api/verbali-noleggio/pdf`

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

Il punto 3 può essere chiuso solo quando gli errori strutturali sono zero,
ogni riferimento API senza match è stato corretto o classificato con evidenza,
e ogni `NotImplementedError` applicativo è stato dimostrato non raggiungibile oppure
trasformato in comportamento esplicito/testato.

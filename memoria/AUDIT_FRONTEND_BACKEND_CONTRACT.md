# Audit frontend ↔ backend — GestionaleCloud

> Generato da `scripts/audit_frontend_backend_contract.py`. Non modificare a mano.
> Il contratto HTTP per metodo+path resta verificato da `tests/test_frontend_api_contract.py`.
> Gli scarti statici sono classificati: un riferimento testuale non equivale a una chiamata runtime.

## Riepilogo

- Pagine canoniche censite: **64**
- Voci di navigazione analizzate: **24**
- Riferimenti API frontend distinti: **446**
- Path API backend distinti: **1070**
- Errori strutturali verificabili: **0**
- Riferimenti frontend realmente senza match statico: **0**
- Alias/query-template classificati: **6**
- Riferimenti frontend riconosciuti come soli prefissi: **2**
- `NotImplementedError` classificati: **11**

## Errori strutturali

- Nessuno.

## Avvisi di routing

- catalogo non riconducibile direttamente al router: `/verbali-noleggio/:identificativo`

## Alias e template classificati

- `/api/agenti/run*` → `/api/agenti/run` (suffisso query/template)
- `/api/f24/avviso-bonario/controllo.` → `/api/f24/avviso-bonario/controllo` (punteggiatura non parte della route)
- `/api/fatture-ricevute/statistiche*` → `/api/fatture-ricevute/statistiche` (suffisso query/template)
- `/api/iva/ricalcola-attribuzione*` → `/api/iva/ricalcola-attribuzione` (suffisso query/template)
- `/api/noleggio/fatture-non-associate*` → `/api/noleggio/fatture-non-associate` (suffisso query/template)
- `/api/noleggio/riepilogo-controlli*` → `/api/noleggio/riepilogo-controlli` (suffisso query/template)

## Riferimenti frontend senza endpoint compatibile

- Nessuno.

## Prefissi API frontend

- `/api/fatture`: prefisso di composizione, non endpoint autonomo.
- `/api/verifica-coerenza/iva`: prefisso di composizione, non endpoint autonomo.

## Funzioni `NotImplementedError` classificate

- `app/hr/db_supabase.py:116` — `guardia_adapter`: errore esplicito per operatori/query Mongo-like non supportati dall'adapter HR.
- `app/hr/db_supabase.py:132` — `guardia_adapter`: errore esplicito per operatori/query Mongo-like non supportati dall'adapter HR.
- `app/hr/db_supabase.py:188` — `guardia_adapter`: errore esplicito per operatori/query Mongo-like non supportati dall'adapter HR.
- `app/hr/db_supabase.py:238` — `guardia_adapter`: errore esplicito per operatori/query Mongo-like non supportati dall'adapter HR.
- `app/hr/db_supabase.py:255` — `guardia_adapter`: errore esplicito per operatori/query Mongo-like non supportati dall'adapter HR.
- `app/hr/db_supabase.py:277` — `guardia_adapter`: errore esplicito per operatori/query Mongo-like non supportati dall'adapter HR.
- `app/hr/db_supabase.py:374` — `guardia_adapter`: errore esplicito per operatori/query Mongo-like non supportati dall'adapter HR.
- `app/hr/db_supabase.py:414` — `guardia_adapter`: errore esplicito per operatori/query Mongo-like non supportati dall'adapter HR.
- `app/services/accounting_entries_service.py:265` — `metodo_non_collegato`: export PDF non implementato; nessun chiamante `export_entries_pdf` trovato nel repository.
- `app/services/sheets_document_store.py:1009` — `guardia_legacy`: errore esplicito per fase di aggregazione non supportata nel fallback Sheets.
- `app/services/vat_f24_service.py:289` — `metodo_non_collegato`: generazione PDF non implementata; nessun chiamante `generate_pdf` del servizio trovato nel repository.

## Esito punto 3

L'inventario strutturale è completo: pagine, navigazione e contratto HTTP non mostrano
orfani strutturali né riferimenti frontend senza endpoint compatibile. I `NotImplementedError`
residui sono guardie adapter oppure metodi non collegati a route/UI correnti.
La registrazione manuale F24 resta in attesa di prova bancaria e non simula una riconciliazione.

# Documenti Inbox — stato reale vs specifica

Fonte specifica: `Documenti — Inbox — Flussi automatici — Logica relazionale completa.txt`
(fornita dall'utente). Verificato leggendo il codice attuale (post-consolidamento router del
2026-07-07).

## Correzione canale (coerente con gli altri documenti)

Come già documentato in `FATTURE_RICEVUTE.md`: il canale predominante per le fatture è
Google Drive (schedulato ogni 15 min), non "Aruba PEC" — il canale PEC è generico SDI. Per
gli altri tipi di documento (F24, cedolini, verbali) il canale resta email, instradato dalla
tabella `mittenti_email` (14 righe reali fornite dall'utente, vedi tabella allegata separata).

## Cosa è confermato implementato

| Requisito spec | Stato | Evidenza |
|---|---|---|
| Entità "documento sorgente" tracciata, non un semplice passaggio | ✅ | collezione reale `documents_inbox`, popolata da 3 percorsi di ingestion (`email_document_downloader.py:859`, `email_full_download.py:1251`, `email_monitor_service.py:85`) + upload manuale (`documenti.py:2290`) |
| Evento di acquisizione propagato | ✅ | `EventTypes.DOCUMENTO_ACQUISITO` → `app/services/handlers/documento_handlers.py::on_documento_acquisito` |
| Dedup per hash contenuto (MD5) | ✅ | `email_monitor_service.py:64-67`, verificato anche in `documento_handlers.py:43-51` (genera `DOC_DUPLICATO` se hash già visto) |
| Dedup per nome+dimensione (con tolleranza) | ✅ | `email_document_downloader.py:840-849`, tolleranza 10% sulla dimensione |
| Classificazione a 7 vie (fattura/F24/cedolino/LUL/verbale/generico/non riconosciuto) | ✅ | `documento_handlers.py::_classifica_documento` righe 148-190 — copre esattamente le 7 categorie della spec |
| Risoluzione automatica alert dopo instradamento riuscito | ✅ | `on_documento_instradato`, righe 112-142 |

## Gap confermati (in ordine di priorità)

1. **Dedup per `message_id+attachment_id` non è una chiave composita reale sul documento**:
   il dedup su message_id opera un livello sopra, decidendo se ri-scansionare l'intera EMAIL
   (`seen_message_ids` in `email_document_downloader.py:744-810`), non se un singolo
   allegato è già stato salvato come documento — la spec chiede una chiave per-allegato.
2. **Nessun dedup per UID** (il quarto tipo di chiave richiesto dalla spec, tipico per
   identificatori IMAP/Drive-file-id persistenti) — non trovato in nessun punto del codice.
3. **Solo 5 alert su 6 definiti** (`alert_engine.py:349-374`): `DOC_NON_CLASSIFICATO`,
   `DOC_PARSER_FALLITO`, `DOC_DUPLICATO`, `DOC_ENTITA_NON_TROVATA`,
   `DOC_REPROCESSING_NECESSARIO` — quest'ultimo definito ma **mai generato** da nessun
   punto del codice (0 chiamate a `genera_alert("DOC_REPROCESSING_NECESSARIO"...)`).
4. **Idempotenza del reprocessing solo parziale**: il dedup su hash blocca correttamente
   la ri-elaborazione accidentale, ma il concetto esplicito di "reprocessing volontario"
   (`origine="reprocessing"`) è accettato nella firma/commento ma **non letto né ramificato**
   da nessuna parte nel corpo della funzione — un reprocessing intenzionale e un primo
   processing sono trattati in modo identico, nessuna logica dedicata.
5. **Classificazione solo euristica (nome file/mime/mittente)**: nessuna classificazione
   basata sul contenuto o su AI in questo handler — un allegato con nome file ambiguo o
   generico può essere mal classificato senza alcun controllo di secondo livello.

## Bug/incoerenze note (da correggere)

- Nessun bug di rottura funzionale identificato in questo modulo — i gap sono principalmente
  copertura incompleta rispetto alla spec (dedup UID, alert reprocessing) piuttosto che
  comportamento attivo errato.

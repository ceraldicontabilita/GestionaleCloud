# Fornitori — stato reale vs specifica

<!-- gestionalecloud-doc
status: reference
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

> [!IMPORTANT]
> Documento di riferimento del dominio. Per persistenza e cutover vale l'architettura Drive-only descritta nei documenti correnti; eventuali nomi di collection restano soltanto contesto storico.

Fonte specifica: `Fornitori — Anagrafica fornitori — Flussi automatici.txt` (fornita dall'utente).
Verificato leggendo il codice attuale (post-consolidamento router del 2026-07-07).

## Correzione canale di importazione (stessa di FATTURE_RICEVUTE.md)

La specifica presuppone "PEC Aruba" come canale che genera nuovi fornitori. Come già
corretto in `memoria/moduli/FATTURE_RICEVUTE.md`: il canale realmente predominante è
**Google Drive** (`app/services/drive_invoice_ingest.py`, schedulato ogni 15 minuti), il
canale PEC è generico SDI (`@pec.fatturapa.it`, riga 14 tabella mittenti attendibili), non
un fornitore/servizio "Aruba" nominato. Il fornitore viene creato/aggiornato automaticamente
da **qualunque** dei tre canali (Drive, PEC/SDI, upload manuale) perché tutti convergono
sulla stessa pipeline `process_xml_bytes` → `ensure_supplier_exists()`.

## Cosa è confermato implementato

| Requisito spec | Stato | Evidenza |
|---|---|---|
| Fornitore come entità centrale, creato automaticamente da fattura XML | ✅ | `ensure_supplier_exists()` in `app/routers/invoices/fatture_upload.py:34` |
| Dedup per P.IVA (supporta sia `partita_iva` che `piva`) | ✅ | `fatture_upload.py:60-66` |
| Fallback dedup per nome/denominazione simile (regex case-insensitive su prefisso nome) | ✅ (parziale — solo prefisso, non vera fuzzy-match) | `fatture_upload.py:69-75` |
| Aggiornamento campi anagrafici mancanti su fornitore esistente | ✅ | `ensure_supplier_exists()`, ramo "existing" |
| **Metodo pagamento come variabile centrale che guida instradamento** | ✅ | `metodo_pagamento` letto SOLO da `fornitori.metodo_pagamento`, mai inferito da fattura — vedi `fatture_upload.py:364,860` |
| Regola "nessun metodo finché non configurato" (default `sospesa`, mai `bonifico`) | ✅ nel percorso principale | `fatture_upload.py:364`: `metodo_pagamento = supplier_result.get("metodo_pagamento") or "sospesa"` |
| Alert quando fornitore creato senza metodo di pagamento | ✅ | tipo alert `"fornitore_senza_metodo_pagamento"`, `fatture_upload.py:165` |

## Gap confermati (in ordine di priorità)

1. ~~**Nessuna funzione di merge/deduplica fornitori**~~ — **RISOLTO**. Creato
   `app/services/fornitori_dedupe.py` (analogo a `dipendenti_dedupe.py`): `trova_duplicati()`
   (P.IVA identica anche tra i campi `partita_iva`/`piva`, + fuzzy match denominazione),
   `merge_fornitori()` (re-punta `invoices.supplier_id` e `scadenziario_fornitori.fornitore_id`,
   soft/hard delete), `auto_merge_tutti()` (solo per i duplicati a certezza alta = stessa
   P.IVA; i duplicati per solo nome simile restano sempre a conferma manuale). Esposto via
   `GET/POST /api/fornitori/duplicati[/merge|/auto-merge]`. Verificato con test end-to-end.
2. ~~**Dedup per nome è solo "prefisso regex", non vera fuzzy-match**~~ — **RISOLTO** dallo
   stesso servizio: `trova_duplicati()` usa `difflib.SequenceMatcher` con normalizzazione
   della forma societaria (rimuove Srl/Spa/Snc/Sas prima del confronto), non più solo un
   prefix-regex. Resta il gap originale nel percorso di *creazione* fattura
   (`ensure_supplier_exists` in `fatture_upload.py` continua a usare il prefix-regex per
   decidere se creare un fornitore nuovo o riusare uno esistente — il nuovo servizio dedup
   serve a *sanare* i duplicati già creati, non a prevenirli a monte).
   Il codice reale confronta solo se il nome fattura inizia con lo stesso prefisso di un
   fornitore esistente (`^{safe_name}`) — non gestisce forme societarie diverse, IBAN
   condiviso, o CF come chiave di dedup alternativa alla P.IVA.
3. **Violazione isolata della regola "nessun metodo finché non configurato"**: due punti nel
   codice tornano a defaultare a `"bonifico"` invece di lasciare `sospesa`/vuoto:
   - `fatture_upload.py:1108` (`sync-suppliers`, ramo "crea nuovo fornitore" da fatture
     storiche già importate) — bug già noto e documentato anche in `FATTURE_RICEVUTE.md`.
   - `fatture_upload.py:696-698` (dentro la logica di ricerca match banca-fattura, un
     default locale `metodo = "bonifico"` usato come euristica di matching — non scrive sul
     fornitore ma può influenzare l'esito della riconciliazione se il fornitore non ha un
     metodo configurato).
4. ~ PARZIALE (lug 2026) — dei 6 alert richiesti dalla spec, `"fornitore_senza_metodo_pagamento"`
   era già sistematico. ✔ RISOLTI ora anche:
   - `FORN_INATTIVO_USATO`: generato in `fatture_upload.py::ensure_supplier_exists()` quando
     arriva una nuova fattura per un fornitore con `attivo: False` — additivo, non blocca
     l'import, solo lo segnala.
   - `FORN_DUPLICATO`: la funzione di dedup esisteva già (`fornitori_dedupe.py::
     trova_duplicati()`, usata dall'endpoint manuale di merge) ma non era mai schedulata.
     Aggiunto `app/scheduler.py::check_fornitori_duplicati_task()` (ogni giorno ore 6:00),
     che genera l'alert solo per i gruppi con certezza "alta" (stessa P.IVA identica) — i
     gruppi "media" (nome simile, fuzzy) restano solo nel controllo manuale, per evitare
     falsi positivi da un job automatico notturno. Verificato con registro Sheets effimero: alert corretto
     su P.IVA duplicata, idempotenza su run ripetuti.
   ✔ RISOLTO anche `FORN_DATI_INCOERENTI`: generato in `fatture_upload.py::
   _controlla_dati_fornitore_incoerenti()` (chiamata sia per fornitori nuovi che esistenti in
   `ensure_supplier_exists()`) quando la P.IVA di un fornitore con nazione IT/vuota non è nel
   formato standard italiano (11 cifre numeriche). Esclude esplicitamente i fornitori esteri
   (nazione diversa da IT), che hanno formati P.IVA legittimamente diversi. Verificato con
   registro Sheets effimero: alert su P.IVA a 10 cifre e su dati storici malformati già in DB, nessun falso
   positivo su P.IVA valida o fornitore estero.
5. **Merge Magazzino↔Fornitori non verificato**: la spec Magazzino presuppone dizionario
   prodotti collegato al fornitore per riordino automatico — vedi `MAGAZZINO.md` per il
   dettaglio (gap separato, ma dipendente da come i fornitori sono strutturati qui).

## Bug/incoerenze note (da correggere)

- I due punti che defaultano a `"bonifico"` (elencati sopra) sono l'unica violazione nota
  della regola generale "il metodo fornitore comanda, mai un default arbitrario".
- Il dedup per P.IVA non normalizza il formato (spazi, prefisso IT, maiuscole/minuscole) —
  non verificato nel dettaglio se P.IVA scritte in formati diversi vengono trattate come
  fornitori diversi.

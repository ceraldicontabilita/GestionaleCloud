# Fornitori — stato reale vs specifica

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

1. **Nessuna funzione di merge/deduplica fornitori**: a differenza di Dipendenti
   (`app/services/dipendenti_dedupe.py`, verificato esistente e usato), **non esiste un
   analogo per Fornitori**. Se due fornitori duplicati vengono creati (es. stesso fornitore
   con P.IVA scritta in formati diversi, o nome leggermente diverso che elude il match per
   prefisso), non c'è un endpoint/servizio per unificarli — il duplicato resta permanente,
   con fatture storicamente sparse su due `supplier_id` diversi.
2. **Dedup per nome è solo "prefisso regex", non vera fuzzy-match**: la spec richiede
   riconoscimento di denominazioni simili (es. "Rossi Srl" vs "Rossi S.r.l." vs "F.lli Rossi").
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
4. **Nessun sistema sistematico dei 6 alert richiesti dalla spec** (fornitore duplicato,
   P.IVA non valida, dati anagrafici incompleti, metodo pagamento mancante, IBAN mancante
   per bonifico/RID, fornitore inattivo con fatture recenti): solo l'alert
   `"fornitore_senza_metodo_pagamento"` è implementato in modo sistematico; gli altri 5 non
   risultano generati da nessun punto del codice controllato.
5. **Merge Magazzino↔Fornitori non verificato**: la spec Magazzino presuppone dizionario
   prodotti collegato al fornitore per riordino automatico — vedi `MAGAZZINO.md` per il
   dettaglio (gap separato, ma dipendente da come i fornitori sono strutturati qui).

## Bug/incoerenze note (da correggere)

- I due punti che defaultano a `"bonifico"` (elencati sopra) sono l'unica violazione nota
  della regola generale "il metodo fornitore comanda, mai un default arbitrario".
- Il dedup per P.IVA non normalizza il formato (spazi, prefisso IT, maiuscole/minuscole) —
  non verificato nel dettaglio se P.IVA scritte in formati diversi vengono trattate come
  fornitori diversi.

# Fatture Ricevute — stato reale vs specifica

Fonte specifica: `Fatture Ricevute E Flussi Automatici.txt` (fornita dall'utente).
Verificato leggendo il codice attuale (post-consolidamento router del 2026-07-07).

## Da dove entra davvero una fattura (correzione: non "Aruba PEC", ma SDI generico)

La specifica originale parla di "PEC Aruba" come canale. **Correzione**: nel codice e nella
tabella mittenti reale non esiste un fornitore "Aruba" nominato — il canale è PEC generico
via SDI, pattern mittente `@pec.fatturapa.it`, canale `pec` (riga 14 della tabella mittenti
attendibili fornita dall'utente: *"SDI - tutte le fatture PEC"*). Il secondo canale, quello
oggi effettivamente predominante e **già attivo**, è **Google Drive**:

- `app/services/drive_invoice_ingest.py`: legge XML/XML.P7M da una cartella Drive
  (env `GOOGLE_DRIVE_FATTURE_FOLDER_ID`), importa con la pipeline condivisa
  `process_xml_bytes(source="google_drive")`, sposta i file elaborati in `Elaborate/`.
  **Schedulato automaticamente ogni 15 minuti** (`app/scheduler.py`, job `drive_fatture_ingest`).
  Card Admin dedicata con stato e sync manuale (`frontend/src/pages/Admin.jsx`).
- Canale PEC/SDI: entra tramite la stessa casella Gmail (non una mailbox separata — vedi
  `memoria/moduli/DOCUMENTI_INBOX.md`), instradato dalla tabella `mittenti_email`.
- Import manuale (`/upload-xml`, `/upload-xml-bulk`): resta per lo storico pre-attivazione
  del canale automatico — canale complementare, non da sostituire.

**Tutti e tre convergono sulla stessa pipeline**: `process_xml_bytes`/`process_fattura_to_db`
in `app/routers/invoices/fatture_upload.py` — non ci sono più percorsi di import paralleli
(consolidato oggi, vedi commit "Consolida /api/fatture").

## Cosa è confermato implementato

| Requisito spec | Stato | Evidenza |
|---|---|---|
| Estrazione XML/P7M (fornitore, righe, IVA) | ✅ | `fatture_upload.py::process_xml_bytes`, `app/parsers/fattura_elettronica_parser.py` |
| Creazione automatica fornitore se non esiste | ✅ | `ensure_supplier_exists()` in `fatture_upload.py` |
| Metodo pagamento fornitore guida l'instradamento (cassa/banca/sospesa) | ✅ | `auto_registra_prima_nota()`: contanti→cassa, bancario→banca SOLO se confermato in EC, altrimenti provvisorio |
| Deduplica per numero+P.IVA+data | ✅ | `generate_invoice_key()`, indice univoco `invoice_key` |
| Riconciliazione fattura↔banca | ✅ (unico tipo di match davvero vivo nel motore automatico) | `app/services/riconciliazione_bancaria.py` |
| Pagamento manuale (cassa/banca) | ✅ live | `POST /api/fatture-ricevute/paga-manuale` |

## Gap confermati (in ordine di priorità)

1. ~~**TD04 (nota di credito) con segno negativo**~~ — **RISOLTO**. Implementato netting
   automatico (`_collega_nota_credito` in `fatture_upload.py`): la nota di credito viene
   cercata e collegata alla fattura originale via `DatiFattureCollegate` (stesso fornitore
   + `invoice_number` == `IdDocumento`), l'originale riceve `note_credito_collegate` e
   `importo_netto` ricalcolato; la NC stessa non genera più né una scadenza in
   `scadenziario_fornitori` né un movimento fantasma in prima nota (era registrata come
   pagamento in uscita nonostante fosse un credito). Verificato con test end-to-end.
   Limite noto: il matching richiede che la fattura originale sia già stata importata nel
   sistema — se arriva prima la NC, resta senza collegamento (log ma nessun errore/alert).
2. **Righe merce → Magazzino**: la maggior parte della gestione giacenze è delegata
   all'app esterna **Lotti** (commento esplicito in `fatture_upload.py`: *"Giacenze
   magazzino: gestite SOLO dall'app esterna Lotti (stesso DB). L'import fatture qui NON
   aggiorna warehouse_inventory."*) — vedi `memoria/moduli/MAGAZZINO.md` per il dettaglio.
   Le righe fattura restano dati grezzi sulla fattura, non alimentano un'entità "prodotto"
   strutturata in questo repo.
3. **Stati fattura granulari**: la specifica chiede 9 stati distinti (acquisita/parse
   ok/collegata a fornitore/da completare/da pagare/pagata/parzialmente riconciliata/
   duplicata/errore parsing). Il sistema reale usa essenzialmente un booleano
   `pagato`/`paid` + `stato_pagamento` stringa (pagata/aperta/sospesa) — non un vero
   automa a stati.
4. **Pagamento parziale/rateale**: `riconciliazione_intelligente_api.py` implementava
   questa logica (pagamento-parziale, nota di credito, bonifico cumulativo) ma è stata
   trovata oggi come **sostanzialmente non funzionante** (0/25 endpoint ricevono traffico
   reale funzionante) — vedi `memoria/endpoints/RICONCILIAZIONE_AUDIT.md`. Non esiste oggi
   un percorso alternativo funzionante per pagamenti parziali su fatture.
5. ~ PARZIALE (lug 2026) — dei 7 tipi alert richiesti dalla spec, `"fornitore_senza_metodo_
   pagamento"` era già sistematico. ✔ RISOLTI ora 2 dei rimanenti, entrambi additivi (non
   cambiano nessuna decisione di import già presa, solo la rendono visibile):
   - `FAT_FORN_NON_TROVATO`: generato in `fatture_upload.py::process_fattura_to_db()` quando
     `ensure_supplier_exists()` ritorna `supplier_id=None` (P.IVA fornitore mancante o non
     estratta dall'XML) — la fattura viene comunque salvata, ma prima restava orfana di
     fornitore senza alcuna segnalazione.
   - `FAT_RIGHE_MERCE_NON_RISOLTE`: generato in `magazzino_handlers.py::
     on_fattura_righe_magazzino()` quando la fattura ha righe merce dubbie o che hanno
     generato un nuovo prodotto — prima esistevano solo alert granulari per singolo prodotto
     (`MAG_MATCH_DUBBIO`), la fattura stessa non risultava mai segnalata come "ha righe da
     verificare".
   ✔ RISOLTO anche `FAT_TIPO_AMBIGUO`: `tipo_doc_map` (18 codici TD01-TD27 standard
   FatturaPA) era definito solo dentro `parse_fattura_xml()`, non riusabile — estratto a
   livello di modulo come `TIPO_DOC_MAP` in `fattura_elettronica_parser.py` (nessun cambio
   di comportamento del parser, stesso identico dizionario). `process_fattura_to_db()` ora
   genera l'alert quando `tipo_documento` è valorizzato ma non è una chiave nota — tipico
   di XML non standard o codici TD futuri non ancora mappati.
   Resta morto `FAT_DUPLICATA`: esiste già `deduplica.py::cerca_duplicato_fattura()`, ma il
   modulo non è importato da nessuna parte — va agganciato con attenzione al flusso 409 di
   import esistente, non affrontato per rischio di impattare un percorso critico.

## Bug/incoerenze note (da correggere)

- Diversi punti isolati (es. `sync-suppliers` in `fatture_upload.py`) default ancora a
  `"bonifico"` invece di rispettare la regola "nessun metodo finché non configurato" —
  violazione isolata della regola generale già rispettata dal percorso principale.

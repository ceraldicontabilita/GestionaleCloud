# Fatture Ricevute — stato reale vs specifica

<!-- gestionalecloud-doc
status: reference
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

> [!IMPORTANT]
> Documento di riferimento del dominio. Per persistenza e cutover vale l'architettura Drive-only descritta nei documenti correnti; eventuali nomi di collection restano soltanto contesto storico.

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
| Metodo pagamento fornitore guida l'instradamento (cassa/banca/sospesa) | ⚠️ CAMBIATO (lug 2026) — vedi nota sotto | `auto_registra_prima_nota()` |
| Deduplica per numero+P.IVA+data | ✅ | `generate_invoice_key()`, indice univoco `invoice_key` |
| Riconciliazione fattura↔banca | ✅ (unico tipo di match davvero vivo nel motore automatico) | `app/services/riconciliazione_bancaria.py` |
| Pagamento manuale (cassa/banca) | ✅ live | `POST /api/fatture-ricevute/paga-manuale` |

## ⚠️ Cambio regola auto-registrazione prima nota (lug 2026, richiesta esplicita utente)

Prima di questo cambio: fattura con metodo fornitore cassa/banca impostato → registrazione
AUTOMATICA e IMMEDIATA in Prima Nota (pagata). Rischio segnalato dall'utente: anche con
metodo impostato, una fattura può finire pagata diversamente da come previsto (es. eccezione
puntuale) — l'auto-registrazione silenziosa non lasciava modo di accorgersene prima che fosse
già "pagata" nel gestionale.

**Nuova regola**: per maggiore sicurezza, l'auto-registrazione immediata resta attiva SOLO
per i fornitori marcati esplicitamente `pagamento_certo: true` (nuovo campo booleano sul
fornitore, default `false` per tutti — sia i fornitori esistenti sia quelli nuovi). Il caso
d'uso è un fornitore per cui non esiste ambiguità possibile per la natura del rapporto
commerciale (es. Amazon: paga sempre e solo con bonifico banca). Per TUTTI gli altri
fornitori — comprese le fatture con metodo cassa o banca regolarmente impostato — la fattura
resta sempre in **Prima Nota Provvisoria**, in attesa di conferma manuale dell'utente
(`PrimaNota.jsx`, tab "Provvisori" → bottoni Conferma/Cassa/Banca/Sospesa, endpoint
`POST /api/prima-nota/provvisori/conferma`, già esistente e non modificato).

Modifiche implementate, tutte e tre necessarie per coerenza (un solo punto avrebbe lasciato
il comportamento incoerente tra le diverse vie con cui una fattura può auto-confermarsi):
1. `fatture_upload.py::auto_registra_prima_nota()` — nuovo parametro `pagamento_certo:
   bool = False`; se `False` ritorna sempre `None` (provvisoria) indipendentemente dal
   metodo. `ensure_supplier_exists()` espone `pagamento_certo` nel risultato, letto dal
   fornitore (`existing.get("pagamento_certo", False)`).
2. `prima_nota_module/sync.py::get_fatture_provvisorie()` — la GET aveva un side-effect di
   auto-conferma silenziosa per i fornitori cassa/banca (righe 674-758, comportamento
   preesistente anomalo: una GET che scrive). Ora auto-conferma solo se
   `certo_per_piva.get(piva)` è vero.
3. `prima_nota_module/sync.py::auto_conferma_provvisori_per_metodo()` — job schedulato ogni
   30 min (`app/scheduler.py`), stessa correzione: salta (nuovo contatore
   `restate_in_provvisoria_fornitore_non_certo`) se il fornitore non è marcato certo.

Frontend: `Fornitori.jsx` — nuovo checkbox "Pagamento certo (nessuna eccezione, es. Amazon:
sempre e solo banca)" nel form di modifica fornitore, più badge "✓ CERTO" sulla card quando
attivo. Nessun nuovo valore aggiunto all'enum `metodo_pagamento` esistente (che resta
cassa/banca/contanti/bonifico/assegno/rid/carta/misto invariato) — `pagamento_certo` è un
campo booleano indipendente, scelta deliberata per non toccare le 6 liste di validazione
del metodo pagamento già disallineate tra loro nel codice (vedi gap sotto).

Verificato con registro Sheets effimero, test end-to-end completo: fornitore normale con metodo bonifico
(non certo) → fattura resta provvisoria, zero movimenti prima nota creati, visibile nella
lista provvisori; fornitore certo (Amazon-style, banca) → registrazione diretta e immediata;
il job bulk schedulato non tocca il fornitore non certo. 90/90 test esistenti ancora verdi.

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
   reale funzionante) — vedi `PROMPT_MASTER.md`, sezione 9. Non esiste oggi
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
6. **6 liste/definizioni diverse e disallineate per i valori validi di `metodo_pagamento`**,
   trovate investigando il cambio regola sopra (nessuna è una fonte di verità unica):
   `suppliers_module/common.py::PAYMENT_METHODS` (6 valori, quella usata dalla UI Fornitori),
   `services/suppliers/constants.py` (dead code, mai importato, valori diversi),
   `suppliers_module/base.py` endpoint `/metodo-pagamento` (terzo set, include "riba"),
   `prima_nota_module/sync.py::classifica_metodo_fornitore` (bucket cassa/banca/sospesa),
   `fatture_upload.py::auto_registra_prima_nota` (logica ad-hoc interna, quinta variante),
   `fatture_module/metodo_pagamento.py::normalizza_metodo_pagamento` (la più granulare,
   include anche i codici MP0x SDI, usata solo da `fatture_module/pagamento.py`). Il
   trattamento di "assegno" in particolare è incoerente: banca ovunque tranne che nel modulo
   "moderno" F, dove resta volutamente separato e mai auto-routato. Non consolidate in
   questo passaggio (fuori scope della richiesta specifica) — consolidamento in un'unica
   fonte di verità resta un miglioramento futuro a basso rischio/alto valore.

## Bug/incoerenze note (da correggere)

- Diversi punti isolati (es. `sync-suppliers` in `fatture_upload.py`) default ancora a
  `"bonifico"` invece di rispettare la regola "nessun metodo finché non configurato" —
  violazione isolata della regola generale già rispettata dal percorso principale.

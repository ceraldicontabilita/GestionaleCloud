# Endpoint Prima Nota — Cassa, Banca, Salari, Provvisori

<!-- gestionalecloud-doc
status: reference
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!IMPORTANT]
> Documento di riferimento del dominio. Per persistenza e cutover vale l'architettura Drive-only descritta nei documenti correnti; eventuali nomi Mongo/collection restano compatibilità o contesto storico.

Documentazione dei router: `app/routers/prima_nota_module/` (prefisso `/api/prima-nota`), `app/routers/accounting/prima_nota_automation.py` (`/api/prima-nota-auto`), `app/routers/accounting/prima_nota_salari.py` (`/api/prima-nota-salari`), `app/routers/accounting/prima_nota_salari_v2.py` (`/api/prima-nota-salari-v2`), `app/routers/dati_provvisori.py` (`/api`).

Concetti chiave del dominio:
- **Collezioni canoniche**: `prima_nota_cassa` e `prima_nota_banca` (la vecchia `prima_nota` è legacy morta). Movimento = `{id, data (YYYY-MM-DD), tipo: entrata|uscita, importo (positivo), descrizione, categoria, riferimento, fattura_id, source, status}`. L'eliminazione "sicura" è soft-delete (`status:"deleted"`); molti endpoint di manutenzione fanno però hard-delete.
- **"Il metodo fornitore comanda"**: la regola unica vive nel motore condiviso `app/engines/prima_nota_engine.py` (`classifica_metodo_fornitore()` in `sync.py` è solo un wrapper). Canonico a 3 valori (lug 2026): contanti/contrassegno → Cassa; OGNI strumento che transita dal conto corrente (bonifico/banca/riba/sepa/rid/sdd/assegno/carta/bancomat/paypal/stripe/domiciliazione/MPxx) → Banca; misto → Provvisoria in attesa di conferma; metodo vuoto/non riconosciuto → resta Provvisoria con richiesta all'utente.
- **Fattura pagata** = tripla `pagato:true, paid:true, stato_pagamento:"pagata"` su `invoices` (schema doppio EN/IT: `total_amount|importo_totale`, `invoice_number|numero_fattura`, `supplier_vat|cedente_piva`, ecc.). Non tutti gli endpoint settano la tripla completa (vedi Note nei singoli endpoint).
- Il riferimento standard dei movimenti da fattura è `FATT-{fattura_id}` (usato per il dedup ovunque nel modulo).

---

## prima_nota_module/__init__.py (prefisso /api/prima-nota)

Il modulo Prima Nota è spacchettato in sotto-file (cassa, banca, salari, stats, sync, manutenzione); `__init__.py` registra tutte le route con `router.add_api_route` (statiche prima delle dinamiche) e definisce inline 3 endpoint minori. 57 route totali.

### POST /api/prima-nota/salari/auto-ricostruisci-dati — fix dati salari
**Cosa fa**: pulsante di riparazione: copia `netto` in `lordo` sui record salari dove `lordo=0`.
**Logica codice**: definito inline in `__init__.py` (`_auto_ricostruisci_salari`). Legge tutta `prima_nota_salari` ordinata per data, per ogni record con `netto>0 e lordo==0` setta `lordo=netto`. Ritorna contatori.
**Note**: il docstring dice "Ricalcola progressivi" ma NON tocca alcun progressivo. I campi `netto/lordo` non appartengono allo schema creato dagli altri endpoint salari (che usano `importo` o `importo_busta/bonifico`): serve solo per record legacy della pipeline paghe.

### GET /api/prima-nota/cassa/template-csv — template CSV cassa
**Cosa fa**: scarica un CSV di esempio per l'import movimenti cassa.
**Logica codice**: inline (`_template_csv_cassa`), risposta statica `text/csv` con header `data,descrizione,importo,tipo,fornitore,categoria` e una riga d'esempio. Nessun accesso DB.

### GET /api/prima-nota/banca/template-csv — template CSV banca
**Cosa fa**: scarica un CSV di esempio per l'import movimenti banca.
**Logica codice**: inline (`_template_csv_banca`), come sopra ma con colonna `banca` al posto di `fornitore`. Nessun accesso DB.

---

## prima_nota_module/cassa.py (prefisso /api/prima-nota)

CRUD Prima Nota Cassa (`prima_nota_cassa`) + due endpoint di bonifica per movimenti bancari finiti erroneamente in cassa. La cassa deve contenere SOLO contante: corrispettivi, POS manuali, versamenti, finanziamenti soci, fatture pagate in contanti.

### GET /api/prima-nota/cassa — lista movimenti cassa
**Cosa fa**: elenca i movimenti cassa filtrati (anno/data/tipo/categoria) con saldi.
**Logica codice**: legge `prima_nota_cassa` escludendo `status in [deleted,archived]` e `categoria in CATEGORIE_ESCLUSE` (`POS_DUPLICATO`); filtro anno robusto (`anno` int oppure fallback su `data` string). Aggregate per entrate/uscite dell'anno + `calcola_saldo_anni_precedenti()` per il riporto. Ritorna `movimenti, saldo (finale), saldo_anno, saldo_precedente, totale_entrate/uscite`.

### POST /api/prima-nota/cassa — crea movimento cassa
**Cosa fa**: inserisce manualmente un movimento in contanti.
**Logica codice**: valida obbligatori (`data,tipo,importo,descrizione`), `tipo` in entrata/uscita, `importo>0`. Blocca movimenti chiaramente bancari via keyword sulla descrizione (BONIFICO, SEPA, SDD, F24, NEXI…) con errore 400 esplicativo. Insert su `prima_nota_cassa` con `id` uuid e campi opzionali (categoria, riferimento, fattura_id, source…).

### PUT /api/prima-nota/cassa/{movimento_id} — modifica movimento cassa
**Cosa fa**: aggiorna i campi editabili di un movimento cassa.
**Logica codice**: `$set` whitelist (`data,tipo,importo,descrizione,categoria,riferimento,note,fornitore`) + `updated_at`; 404 se `id` non trovato. Nessuna validazione tipo/importo (a differenza del create).

### DELETE /api/prima-nota/cassa/{movimento_id} — elimina movimento cassa (soft)
**Cosa fa**: archivia un movimento cassa; se saldava una fattura la riporta "da pagare".
**Logica codice**: valida con `BusinessRules.can_delete_movement()`; se ci sono warning e `force=false` ritorna `require_force:true` senza toccare nulla. Soft-delete (`status:"deleted"`, `entity_status`, `deleted_at`). Se `mov.fattura_id` e la fattura punta a questo movimento (`prima_nota_id`), resetta la tripla pagamento e fa `$unset` di `prima_nota_id/tipo/cassa_id/data_pagamento` su `invoices`.

### DELETE /api/prima-nota/cassa/delete-all — svuota la cassa
**Cosa fa**: elimina TUTTI i movimenti cassa.
**Logica codice**: `delete_many({})` HARD su `prima_nota_cassa`, senza conferme né backup.
**Note**: distruttivo e irreversibile; non aggiorna le fatture collegate (restano "pagate" con `prima_nota_id` orfano).

### DELETE /api/prima-nota/cassa/delete-by-source/{source} — elimina per source
**Cosa fa**: elimina i movimenti cassa importati da una specifica sorgente (es. `csv_import`).
**Logica codice**: `delete_many({source})` hard. Stesse controindicazioni di delete-all.

### GET /api/prima-nota/cassa/{movimento_id}/fattura — fattura allegata
**Cosa fa**: recupera la fattura collegata a un movimento cassa (per il dettaglio in UI).
**Logica codice**: legge il movimento, poi `invoices` per `id` o `invoice_key` = `fattura_id`. Ritorna `{movimento_id, fattura|null, message}`.

### GET /api/prima-nota/cassa/analisi-movimenti-bancari-errati — analisi (dry-run)
**Cosa fa**: report dei movimenti bancari finiti per errore in cassa, senza toccare nulla.
**Logica codice**: carica tutta la cassa attiva (50k max) e classifica per euristiche: corrispettivi/`corrispettivi_sync` sempre legittimi; manuali senza keyword bancarie legittimi; `csv_import`/`sync_fatture`/altro con keyword bancarie (BONIFICO, SEPA, NEXI, F24, STIPENDI, COMMISSIONI…) o categoria `fornitori/Fatture` → errati. Ritorna conteggi, importo totale, campioni e breakdown per source/categoria.

### DELETE /api/prima-nota/cassa/elimina-movimenti-bancari-errati — bonifica cassa
**Cosa fa**: elimina davvero i movimenti individuati dall'analisi precedente.
**Logica codice**: replica la stessa classificazione a keyword (lista duplicata nel codice) e fa `delete_many` HARD per `_id`. Ritorna eliminati e rimanenti.
**Note**: logica quasi-duplicata in 3 punti (analisi, questo endpoint, `migrazione-pulisci-bancari-cassa` in manutenzione.py che ha keyword extra SUMUP/PDV 37 e più eccezioni per POS/Versamento).

---

## prima_nota_module/banca.py (prefisso /api/prima-nota)

CRUD Prima Nota Banca (`prima_nota_banca`). Particolarità: la vista Banca del frontend è un mix di `prima_nota_banca` + `estratto_conto_movimenti`, quindi update/delete fanno fallback sulla collection dell'estratto conto.

### GET /api/prima-nota/banca — lista movimenti banca
**Cosa fa**: elenca i movimenti banca con saldi per anno e riporto anni precedenti.
**Logica codice**: identico a `GET /cassa` (query su `prima_nota_banca`, aggregate entrate/uscite, `calcola_saldo_anni_precedenti`).
**Note**: a differenza della cassa NON esclude `CATEGORIE_ESCLUSE` (POS_DUPLICATO) — asimmetria voluta o svista.

### POST /api/prima-nota/banca — crea movimento banca
**Cosa fa**: inserisce manualmente un movimento bancario.
**Logica codice**: valida obbligatori e tipo; insert con campi extra banca (`iban, conto_bancario, pos_details`). Nessun blocco keyword né check `importo>0` (asimmetrico rispetto alla cassa).

### PUT /api/prima-nota/banca/{movimento_id} — modifica movimento banca
**Cosa fa**: aggiorna un movimento della vista Banca.
**Logica codice**: `$set` whitelist su `prima_nota_banca`; se `matched_count==0` riprova su `estratto_conto_movimenti` (i movimenti EC mostrati nella vista Banca vivono lì); 404 solo se assente in entrambe.

### DELETE /api/prima-nota/banca/{movimento_id} — elimina movimento banca
**Cosa fa**: archivia un movimento banca (o cancella un movimento estratto conto della vista mista).
**Logica codice**: se il movimento non è in `prima_nota_banca` cerca in `estratto_conto_movimenti` e lì fa `delete_one` HARD. Altrimenti: validazione `BusinessRules.can_delete_movement`, warning+`force`, soft-delete, e ripristino fattura collegata a "da pagare" (come in cassa, con `$unset prima_nota_banca_id`).

### DELETE /api/prima-nota/banca/delete-all — svuota la banca
**Cosa fa / Logica**: `delete_many({})` hard su `prima_nota_banca`. Stesse controindicazioni di cassa/delete-all.

### DELETE /api/prima-nota/banca/delete-by-source/{source} — elimina per source
**Cosa fa / Logica**: `delete_many({source})` hard su `prima_nota_banca` (es. per annullare un import `estratto_conto_sync`).

### GET /api/prima-nota/banca/{movimento_id}/fattura — fattura allegata
**Cosa fa / Logica**: come l'omologo cassa: movimento → `fattura_id` → lookup `invoices` per `id|invoice_key`.

---

## prima_nota_module/salari.py (prefisso /api/prima-nota)

Mini-CRUD "storico" sui salari nella collection `prima_nota_salari`, con schema a movimento singolo (`importo`, `nome_dipendente`, `tipo:"uscita"`).
**Attenzione**: la stessa collection è usata dal router `/api/prima-nota-salari` (accounting) con uno schema DIVERSO (`dipendente`, `importo_busta/importo_bonifico/saldo/progressivo`): i due sistemi convivono sugli stessi documenti ma non si capiscono a vicenda (es. le stats qui sommano `importo`, campo assente nei record buste/bonifici).

### GET /api/prima-nota/salari — lista movimenti salari
**Cosa fa**: elenca i movimenti salari con filtri data/dipendente/anno.
**Logica codice**: query su `prima_nota_salari` (filtro `nome_dipendente` regex case-insensitive, anno int o range su `data`); aggregate parallelo per `totale` (somma `importo`) e `count`.

### POST /api/prima-nota/salari — crea movimento salari
**Cosa fa**: registra manualmente un'uscita stipendio.
**Logica codice**: insert con `tipo:"uscita"` forzato, categoria default "Stipendi", campi dipendente (`nome_dipendente, codice_fiscale, employee_id, periodo, mese, anno`), `source` default `manual_entry`. Nessuna validazione dei campi obbligatori (KeyError 500 se mancano `data/importo/descrizione`).

### DELETE /api/prima-nota/salari/{movimento_id} — elimina movimento salari
**Cosa fa / Logica**: `delete_one({id})` hard, 404 se assente.

### GET /api/prima-nota/salari/stats — statistiche salari
**Cosa fa**: totale e breakdown per dipendente nel periodo.
**Logica codice**: due aggregate su `prima_nota_salari` (totale+count; group per `nome_dipendente` ordinato per totale). Esclude i dipendenti con `_id` nullo dal breakdown.

---

## prima_nota_module/stats.py (prefisso /api/prima-nota)

Statistiche aggregate cassa+banca, anni disponibili, saldo di fine anno ed export Excel.

### GET /api/prima-nota/anni-disponibili — anni con movimenti
**Cosa fa**: lista anni per il selettore anno della UI.
**Logica codice**: aggregate `$substr` sui primi 4 caratteri di `data` su `prima_nota_cassa` e `prima_nota_banca`; aggiunge sempre l'anno corrente; ritorna ordinati desc.
**Note**: non esclude i movimenti soft-deleted.

### GET /api/prima-nota/stats — statistiche cassa+banca
**Cosa fa**: dashboard entrate/uscite/saldo per cassa, banca e totale nel periodo.
**Logica codice**: due aggregate identiche (`$cond` su tipo) su cassa e banca con filtro solo su `data`.
**Note**: NON esclude `status deleted/archived` né POS_DUPLICATO → i numeri possono divergere da `GET /cassa` e `GET /banca`.

### GET /api/prima-nota/saldo-finale — saldo di fine anno
**Cosa fa**: saldo (entrate−uscite) dell'anno per cassa o banca.
**Logica codice**: `find` di tutti i movimenti dell'anno (`status != deleted`) e somma in Python usando `abs(importo)` col segno dato dal `tipo`.
**Note**: esclude solo `deleted`, non `archived`; non esclude POS_DUPLICATO. L'`abs()` neutralizza gli importi negativi anomali (vedi dati_provvisori) in modo diverso dalle aggregate.

### GET /api/prima-nota/export/excel — export Excel
**Cosa fa**: scarica un .xlsx con fogli "Prima Nota Cassa" e/o "Prima Nota Banca".
**Logica codice**: pandas+openpyxl; `tipo` = cassa|banca|entrambi, filtro solo per data; colonne selezionate (banca include `assegno_collegato`). Se non ci sono movimenti crea un foglio vuoto (openpyxl richiede ≥1 sheet). StreamingResponse con filename datato.
**Note**: esporta anche i soft-deleted (nessun filtro status).

---

## prima_nota_module/sync.py (prefisso /api/prima-nota)

Il cuore del modulo: sincronizzazioni (corrispettivi→cassa, fatture pagate→prima nota, estratto conto→banca), gestione fatture Provvisorie con auto-conferma per metodo fornitore, import batch e spostamenti. Qui vivono `classifica_metodo_fornitore()` (regola unica cassa/banca/sospesa), `determina_tipo_movimento_fattura()` (nota credito TD04/TD08→entrata; fattura attiva TD24-27→entrata "Incasso cliente"; resto→uscita "Pagamento fornitore") e `registra_pagamento_fattura()` (insert idempotente per `fattura_id`/`riferimento FATT-`).

### POST /api/prima-nota/registra-fattura — registra pagamento fattura manuale
**Cosa fa**: registra il pagamento di una singola fattura in cassa/banca/misto.
**Logica codice**: carica la fattura (`id|invoice_key`); se `metodo_pagamento` non è passato lo deduce dall'anagrafica fornitore (`suppliers`, P.IVA su `partita_iva|piva|vat_number`; contanti→cassa, altrimenti default banca). Chiama `registra_pagamento_fattura()` (idempotente, gestisce anche "misto" con importi separati cassa/banca), poi aggiorna `invoices` con `pagato:true`, `data_pagamento`, `metodo_pagamento`, `prima_nota_cassa_id/banca_id`.
**Note**: setta solo `pagato`, non `paid` né `stato_pagamento:"pagata"` — tripla incompleta rispetto alla convenzione.

### POST /api/prima-nota/sync-corrispettivi — sync corrispettivi (tutti)
### POST /api/prima-nota/cassa/sync-corrispettivi — sync corrispettivi (per anno)
**Cosa fa**: porta i corrispettivi giornalieri in Prima Nota Cassa (entrata totale + uscita POS→banca).
**Logica codice**: entrambe delegano a `_sync_corrispettivi_impl(anno?)`. Per ogni doc di `corrispettivi` non ancora presente (dedup su `corrispettivo_id`): entrata `categoria:"Corrispettivi"` con importo = totale (fallback a cascata su `totale|totale_complessivo|importo|totale_giornaliero|contanti+pos`); se c'è quota elettronica crea anche uscita `categoria:"POS Verso Banca"` (`source:corrispettivi_pos_sync`, dedup separato). Legge sia `pagato_pos` (nome attuale nel DB) sia `pagato_elettronico` (legacy). I corrispettivi con totale 0 vengono saltati e riportati in `saltati_dettaglio` per diagnostica.

### POST /api/prima-nota/cassa/sync-fatture-pagate — sync fatture pagate dell'anno
**Cosa fa**: crea i movimenti mancanti per le fatture già marcate pagate.
**Logica codice**: `invoices` con `stato_pagamento:"pagata"` e `invoice_date` nell'anno; dedup pre-caricando da cassa+banca i riferimenti `FATT-*` e i `fattura_id` esistenti (volutamente SENZA filtro categoria, per compatibilità con le categorie variabili di `registra_pagamento_fattura`). Smista per `metodo_pagamento` (contanti/cassa→cassa, resto→banca) con `source:"sync_fatture"`, sempre `tipo:"uscita"`, categoria "Fatture".
**Note**: nella descrizione usa `fatt.get('numero','')` — campo che sulle fatture di solito non esiste (`invoice_number`/`numero_fattura`), quindi le descrizioni escono come "Fattura  - Fornitore". Non gestisce note credito (tutto uscita). Legge solo `total_amount` (non `importo_totale`).

### GET /api/prima-nota/corrispettivi-status — stato sync corrispettivi
**Cosa fa**: confronto rapido corrispettivi totali vs sincronizzati in cassa.
**Logica codice**: count su `corrispettivi` e su `prima_nota_cassa` (`corrispettivo_id` esistente); somma euro da entrambe le parti (in cassa: `categoria:"Corrispettivi", tipo:entrata`).

### POST /api/prima-nota/banca/sync-estratto-conto — import EC → banca
**Cosa fa**: copia in blocco i movimenti dell'estratto conto dell'anno in `prima_nota_banca`.
**Logica codice**: query su `estratto_conto_movimenti` con `data_contabile` in formato `DD/MM/YYYY` o `YYYY-MM-DD`; dedup su `estratto_conto_id` già presenti in banca; converte la data in ISO; tipo derivato dal segno dell'importo (positivo=entrata), importo salvato in valore assoluto; `source:"estratto_conto_sync"`; insert a batch da 500.
**Note**: usare insieme alla vista mista Banca può mostrare doppioni (il movimento resta anche in `estratto_conto_movimenti`).

### GET /api/prima-nota/provvisori — lista fatture provvisorie (CON side-effect!)
**Cosa fa**: pagina "Provvisori": fatture non registrate in Prima Nota, con suggerimento cassa/banca/sospesa e match con l'estratto conto; auto-conferma al volo quelle decidibili.
**Logica codice**: fatture dell'anno con `total_amount>0`, non pagate (`stato_pagamento nin [pagata,paid]`, `pagato != true`) e senza `prima_nota_id`. Suggerimento = `classifica_metodo_fornitore()` sul metodo in anagrafica `fornitori` (P.IVA letta da `partita_iva|piva|vat_number`); il metodo XML della fattura NON viene MAI usato; `stato_pagamento:"sospesa"` ha priorità e resta in attesa. Per suggerimento banca cerca il movimento EC non riconciliato con stesso importo assoluto e scoring su nome fornitore/P.IVA/numero fattura/keyword bonifico (≥30 → "confermato", solo importo → "probabile"). Poi AUTO-CONFERMA: cassa se confermata, banca sempre (movimento `source:"auto_conferma"`, categoria "Fatture", riferimento `FATT-{id}`, dedup su riferimento); aggiorna la fattura con tripla completa `pagata/pagato/paid` + `prima_nota_id/tipo`; se ha agganciato un movimento EC lo marca `riconciliato:true` per non farlo riusare. Ritorna solo i provvisori residui + contatori.
**Note**: è una GET che SCRIVE su 3 collection (aprire la pagina modifica i dati). I movimenti creati qui (`source:"auto_conferma"`) NON sono annullabili da `/provvisori/annulla-auto-conferma`, che filtra solo `auto_confirm_provvisoria` (vedi sotto).

### POST /api/prima-nota/provvisori/conferma — conferma manuale provvisorio
**Cosa fa**: l'utente decide la destinazione di una fattura provvisoria (cassa/banca/sospesa).
**Logica codice**: body `{fattura_id, metodo, movimento_banca_id?}`. "sospesa": aggiorna solo la fattura (`stato_pagamento:"sospesa"`, `$unset prima_nota_id`), nessun movimento. Altrimenti: dedup su `riferimento FATT-{id}` (se esiste aggancia la fattura al movimento esistente); crea movimento `tipo:"uscita"`, categoria "Fatture", `source:"conferma_provvisori"`; aggiorna fattura con `stato_pagamento:"pagata"`, `prima_nota_id/tipo` e `payment_method`.
**Note**: setta solo `stato_pagamento`, non `pagato/paid`. `movimento_banca_id` è documentato nel docstring ma il codice lo ignora completamente. Sempre uscita: una nota credito confermata verrebbe registrata al contrario.

### POST /api/prima-nota/provvisori/auto-conferma-per-metodo — auto-conferma bulk (job)
**Cosa fa**: job massivo (anche schedulato) che smista tutte le provvisorie dell'anno secondo il metodo fornitore.
**Logica codice**: carica il dizionario P.IVA→metodo da `fornitori`; fatture dell'anno senza `prima_nota_id` e non sospese. Per ciascuna: dedup su movimento esistente (per `riferimento` o `fattura_id` in cassa E banca — se c'è, aggiorna solo i puntatori della fattura); poi `classifica_metodo_fornitore()`: sospesa→skip con contatore; cassa/banca→crea movimento via `determina_tipo_movimento_fattura()` (qui le note credito SONO gestite come entrata), `source:"auto_confirm_provvisoria"` + `auto_confirm_meta{metodo, stato_pagamento_al_momento, operazione_id}` per il rollback. Fattura: `prima_nota_id/tipo`, `metodo_pagamento_effettivo`; `stato_pagamento:"pagata"`+`data_pagamento` solo se destinazione cassa o se era già pagata. Report dettagliato (prime 100 mosse).
**Note**: il campo `rollback_endpoint` nella risposta indica `POST /api/prima-nota/annulla-auto-conferma` ma il path reale è `/api/prima-nota/provvisori/annulla-auto-conferma`.

### POST /api/prima-nota/provvisori/annulla-auto-conferma — rollback auto-conferma
**Cosa fa**: annulla una run (o tutte) dell'auto-conferma bulk, riportando le fatture in Provvisoria.
**Logica codice**: trova in cassa+banca i movimenti `source:"auto_confirm_provvisoria"` (opz. filtro `auto_confirm_meta.operazione_id`); soft-delete di massa (`status:"deleted"`, `deleted_reason:"rollback_auto_confirm"`); per ogni fattura ripristina `prima_nota_id/tipo` vuoti e `stato_pagamento` al valore salvato in `auto_confirm_meta`.
**Note**: non tocca i movimenti `source:"auto_conferma"` creati dalla pagina Provvisori (GET) né `conferma_provvisori`: quelli si annullano solo a mano.

### POST /api/prima-nota/cassa/crea-entrata-da-corrispettivo — entrata cassa da XML
**Cosa fa**: bottone opzionale "crea da XML": genera entrata cassa (totale) ed eventuale uscita POS per una data.
**Logica codice**: cerca il corrispettivo per `data`; idempotente (skip se esiste già movimento `source:"manuale_da_xml"` per quel `corrispettivo_id`); entrata "Corrispettivi" + uscita "POS Verso Banca" se `includi_uscita_pos=true` e quota elettronica >0; tollera schema legacy (`pagato_pos|pagato_elettronico`). 400 se totale 0.
**Note**: flusso NORMALE = inserimento manuale serale; l'import XML (`/api/prima-nota-auto/import-corrispettivi-xml`) non scrive più in cassa proprio per questo.

### POST /api/prima-nota/sposta-scrittura — sposta scrittura cassa↔banca
**Cosa fa**: cambia destinazione di un movimento quando l'utente corregge il metodo di pagamento.
**Logica codice**: cerca il movimento in entrambe le collection; se già a destinazione esce; altrimenti `delete_one` dall'origine + insert nella destinazione con `spostato_da/spostato_at`; aggiorna la fattura collegata (`prima_nota_tipo`, `payment_method` contanti|bonifico).
**Note**: quasi-duplicato di `POST /sposta-movimento` (manutenzione.py), che in più gestisce il fallback estratto conto, aggiorna più campi fattura ed emette l'evento `TRASFERIMENTO_CREATO`. Due endpoint per la stessa cosa.

### POST /api/prima-nota/import-batch — import massivo movimenti
**Cosa fa**: importa liste di movimenti cassa e banca in un colpo (usato dall'import Excel del frontend).
**Logica codice**: body `{cassa:[...], banca:[...]}`; per ogni item insert diretto con `source` default `excel_import`; errori raccolti per riga (primi 10).
**Note**: nessun dedup e nessuna validazione di `tipo`: rilanciare l'import duplica tutto.

### POST /api/prima-nota/movimento — crea movimento generico
**Cosa fa**: crea un movimento su cassa o banca scegliendo con `tipo` ("cassa"/"banca") nel body.
**Logica codice**: valida `data/importo/descrizione`; campo `tipo` = collection di destinazione e `tipo_movimento` = entrata/uscita (naming confuso ma coerente col frontend); `fonte` default `manual_entry`, flag `riconciliato`.
**Note**: sovrapposto ai POST /cassa e /banca; non applica il blocco keyword-bancarie della cassa.

### POST /api/prima-nota/collega-fatture — collega fatture ai movimenti
**Cosa fa**: riempie i `fattura_id` mancanti nei movimenti che hanno solo `numero_fattura`.
**Logica codice**: per cassa e banca, cursor sui movimenti con `numero_fattura` valorizzato e `fattura_id` vuoto; lookup `invoices` per `numero|invoice_number|numero_fattura`; `$set fattura_id`. Ritorna il conteggio.

---

## prima_nota_module/manutenzione.py (prefisso /api/prima-nota)

Cassetta degli attrezzi: fix dati, dedup, ricalcoli, migrazioni one-shot e diagnostica. Molti endpoint fanno hard-delete: da usare consapevolmente (in genere dalla pagina PuliziaPrimaNota del frontend).

### POST /api/prima-nota/fix-tipo-movimento — corregge tipo/categoria da fattura
**Cosa fa**: riallinea `tipo` e `categoria` dei movimenti collegati a fatture (es. note credito registrate come uscita).
**Logica codice**: per cassa e banca, per ogni movimento con `fattura_id` ricarica la fattura e ricalcola con `determina_tipo_movimento_fattura()`; `$set` se diverso, con `fixed_at`.

### POST /api/prima-nota/recalculate-balances — ricalcolo saldi (sola lettura)
**Cosa fa**: mostra i saldi ricalcolati cassa/banca/totale (opz. per anno).
**Logica codice**: aggregate entrate/uscite escludendo `deleted/archived`. Non scrive nulla (il nome inganna: è un report).

### POST /api/prima-nota/cleanup-orphan-movements — elimina orfani
**Cosa fa**: cancella i movimenti che puntano a fatture inesistenti.
**Logica codice**: per cassa e banca, per ogni movimento con `fattura_id`, lookup su `invoices` (`id|invoice_key`); se assente `delete_one` HARD.

### POST /api/prima-nota/regenerate-from-invoices — rigenera da fatture
**Cosa fa**: ricostruisce i movimenti dell'anno dall'archivio fatture (distruttivo per le source coinvolte).
**Logica codice**: `delete_many` hard dei movimenti dell'anno con `source in [fattura_pagata, fatture_import, xml_upload]`; poi per TUTTE le fatture dell'anno (pagate o no!) crea movimento (`determina_tipo_movimento_fattura`, smistamento per `metodo_pagamento` contanti/cassa→cassa altrimenti banca, `source:"fatture_import"`, riferimento = numero fattura, NON `FATT-{id}`).
**Note**: registra anche fatture non pagate; il riferimento non-standard sfugge al dedup `FATT-` degli altri endpoint → possibile fonte di duplicati (mitigata dal dedup per `fattura_id` in `dedup-fatture`).

### POST /api/prima-nota/fix-versamenti-duplicati — dedup versamenti
**Cosa fa**: rimuove i versamenti in cassa duplicati creati con data in formato datetime + date.
**Logica codice**: carica `categoria:"Versamento"` in cassa; separa record con data "YYYY-MM-DD HH:MM" da quelli "YYYY-MM-DD"; se per lo stesso giorno esistono entrambi elimina (hard) il formato date e normalizza la data del superstite ai primi 10 caratteri.
**Note**: il messaggio dice "con importo errato" ma l'importo non viene mai confrontato: la scelta è solo sul formato data.

### POST /api/prima-nota/fix-categories-and-duplicates — fix categorie + dedup cassa
**Cosa fa**: normalizza categorie (Altro→POS/Corrispettivi/Versamento in base alla descrizione) e rimuove duplicati esatti in cassa.
**Logica codice**: mapping keyword categoria/descrizione; poi dedup hard su chiave `data|importo|descrizione[:50]` tenendo il primo incontrato (ordine di caricamento, non created_at).

### POST /api/prima-nota/sposta-movimento — sposta cassa↔banca (versione completa)
**Cosa fa**: sposta un movimento tra cassa e banca; gestisce anche i movimenti che vivono nell'estratto conto.
**Logica codice**: body Pydantic `{movimento_id, da, a}`. Se non trovato in `prima_nota_banca` e `da="banca"`, cerca in `estratto_conto_movimenti`: lo copia nella destinazione e lo RIMUOVE dall'EC. Ramo standard: insert in destinazione con `moved_from/moved_at` + delete dall'origine; aggiorna la fattura collegata (`prima_nota_tipo`, `metodo_pagamento`, `payment_method`, `prima_nota_cassa_id/banca_id`). Emette evento `TRASFERIMENTO_CREATO` sull'event bus (best-effort).
**Note**: doppione di `/sposta-scrittura` (sync.py) — questo è il più completo; il frontend usa entrambi in punti diversi.

### GET /api/prima-nota/verifica-metodo-fattura/{fattura_id} — debug metodo fattura
**Cosa fa**: pannello debug: come verrebbe classificata una fattura e che metodo ha il fornitore.
**Logica codice**: carica fattura, calcola tipo/categoria con `determina_tipo_movimento_fattura()`, lookup fornitore SOLO per `partita_iva`.
**Note**: non cerca `piva|vat_number` come fanno sync.py e registra-fattura → per i fornitori storici può mostrare "nessun metodo" mentre l'auto-conferma lo trova.

### GET /api/prima-nota/cassa/verifica-entrate-corrispettivi — verifica corrispettivi
**Cosa fa**: confronto totale corrispettivi sorgente vs entrate "Corrispettivi" in cassa per l'anno.
**Logica codice**: somma `importo` delle entrate cassa categoria Corrispettivi vs somma `totale` in `corrispettivi`; status OK se differenza <1€.
**Note**: non esclude soft-deleted; usa solo il campo `totale` della sorgente (i legacy senza `totale` risultano 0).

### POST /api/prima-nota/cassa/fix-corrispettivi-importo — fix importi corrispettivi
**Cosa fa**: riallinea l'importo dei movimenti Corrispettivi in cassa al `totale` della sorgente.
**Logica codice**: per ogni entrata Corrispettivi dell'anno, risale al corrispettivo (`corrispettivo_id` o riferimento `CORR-*`); se differenza >0,01€ aggiorna `importo` salvando `importo_originale` e `fixed_at`.

### POST /api/prima-nota/migrazione-pulisci-bancari-cassa — migrazione one-shot
**Cosa fa**: versione "migrazione" della bonifica movimenti bancari in cassa.
**Logica codice**: come `/cassa/elimina-movimenti-bancari-errati` ma con keyword extra (SUMUP, `PDV 37` = terminale POS Ceraldi) ed eccezioni esplicite per POS/Versamento/Finanziamento manuali. `delete_many` hard, log campione dei primi 10 eliminati.
**Note**: terza copia della stessa logica a keyword; le tre liste possono divergere nel tempo.

### POST /api/prima-nota/dedup-fatture — dedup movimenti fattura (dry-run/apply)
**Cosa fa**: individua ed elimina (soft) i movimenti duplicati della stessa fattura in cassa e banca.
**Logica codice**: raggruppa per chiave: `fattura_id`, altrimenti `riferimento FATT-*`, altrimenti `numero_fattura+importo+data`; tiene il più vecchio (`created_at` min), gli altri soft-delete con `deleted_reason:"dedup_fatture_prima_nota"`. `?applica=false` (default) = solo report; `?applica=true` esegue. Filtro `anno` opzionale.

### GET /api/prima-nota/diagnostica-corrispettivi — diagnosi corrispettivi vs cassa
**Cosa fa**: report corrispettivi mancanti in cassa, non sincronizzabili (totale 0) e duplicati.
**Logica codice**: confronta `corrispettivi` (per `anno`) con i movimenti cassa `source:"corrispettivi_sync"` indicizzati per `corrispettivo_id`; stessi fallback di importo del sync. Suggerisce le azioni correttive (sync/dedup) nella risposta.

### GET /api/prima-nota/movimenti-ec-non-in-prima-nota — EC senza corrispondenza in banca
**Cosa fa**: elenca i movimenti estratto conto non riconciliati che non risultano in Prima Nota Banca.
**Logica codice**: EC dell'anno con `riconciliato != true`; esclude quelli già referenziati da un PN via `estratto_conto_ref`; safety-net: indice PN per `importo+tipo+data ±1 giorno` per marcare `possibile_match_esistente` (probabile che serva solo un collegamento, non un nuovo insert). Totali entrate/uscite in risposta.
**Note**: il docstring parla di tolleranza ±3 giorni, il codice usa ±1.

### POST /api/prima-nota/importa-da-ec — importa singolo movimento EC in banca
**Cosa fa**: crea un movimento in Prima Nota Banca da un movimento estratto conto (bottone dalla lista sopra).
**Logica codice**: body `{ec_id, categoria?, descrizione?}`; idempotente su `estratto_conto_ref`; insert con `source:"import_da_ec"`, riferimento `EC-{primi 8 char}`; marca l'EC `riconciliato:true` con `prima_nota_id` e `riconciliato_at`.

---

## accounting/prima_nota_automation.py (prefisso /api/prima-nota-auto)

Automazioni batch e import file: processamento massivo fatture per metodo fornitore, import Excel/CSV (fatture cassa, versamenti, POS), parsing estratto conto per assegni, import XML corrispettivi. Helper: `parse_italian_amount()` (1.530,9 → float) e `parse_italian_date()` (gg/mm/aaaa → ISO).

### POST /api/prima-nota-auto/process-existing-invoices — processa fatture esistenti
**Cosa fa**: batch: assegna il metodo pagamento del fornitore alle fatture non pagate e (opz.) le registra in prima nota.
**Logica codice**: `invoices` con `pagato != true` (opz. filtro anno); metodo da `suppliers.metodo_pagamento` (lookup solo `partita_iva`, default "bonifico" se fornitore assente); dedup su `fattura_id` in cassa+banca; crea uscita "Pagamento fornitore" (riferimento = numero fattura, NON `FATT-`) e marca la fattura `pagato:true` + `prima_nota_cassa_id/banca_id` + `data_pagamento=oggi`.
**Note**: marca "pagate" fatture che potrebbero non esserlo (il fornitore ha un metodo ≠ contanti ma nessuno ha verificato il pagamento) e setta solo `pagato` (tripla incompleta). Quasi identico a `/move-invoices-by-supplier-payment` (sotto): duplicazione. Predata dalla logica Provvisori di sync.py, che è quella attuale e più prudente.

### POST /api/prima-nota-auto/import-cassa-from-excel — import fatture pagate in contanti
**Cosa fa**: da un Excel (colonne Numero, Fornitore, Importo, Data documento) registra le fatture come pagate per cassa.
**Logica codice**: pandas (xlrd/openpyxl); per riga: match fattura per numero (anche regex case-insensitive) o fallback fornitore+importo ±1%; dedup su `riferimento`=numero o `fattura_id` in cassa; crea uscita "Pagamento fornitore" `source:"excel_import"`; se la fattura esiste la aggiorna (`pagato:true, metodo_pagamento:"contanti", prima_nota_cassa_id`) ed emette evento `FATTURA_PAGATA`. Le non trovate finiscono in `not_found`.

### POST /api/prima-nota-auto/import-assegni-from-estratto-conto — estrai assegni da EC
**Cosa fa**: parsa CSV/Excel/PDF dell'estratto conto cercando righe "ASSEGNO", crea/aggiorna i record assegni e li aggancia ai movimenti banca.
**Logica codice**: PDF via pdfplumber (tabelle+testo), CSV multi-encoding `;`, Excel. Estrae numero assegno con pattern regex a cascata, importo (colonna, celle, o regex sul testo) e data. Se l'assegno esiste in `assegni` aggiorna solo i campi mancanti; altrimenti lo crea (`stato:"incassato"`, `source:"estratto_conto"`) e cerca in `prima_nota_banca` un'uscita di importo ±1% senza `assegno_collegato`: se trovata, collega bidirezionalmente (assegno.fattura_collegata ← mov.fattura_id; mov.assegno_collegato, `metodo_pagamento:"assegno"`).
**Note**: il match per solo importo può agganciare il movimento sbagliato.

### POST /api/prima-nota-auto/match-assegni-to-invoices — riaggancia assegni
**Cosa fa**: riprova l'associazione assegni↔movimenti banca per gli assegni ancora scollegati.
**Logica codice**: `assegni` con `fattura_collegata:null`; stesso match per importo ±1% su `prima_nota_banca` e stesso doppio update dell'endpoint precedente.

### POST /api/prima-nota-auto/move-invoices-by-supplier-payment — smista fatture per metodo fornitore
**Cosa fa**: come `process-existing-invoices`: registra in blocco le fatture in cassa/banca secondo il metodo del fornitore.
**Logica codice**: differenze minime: flag `only_unpaid` (default true), dedup PRIMA del lookup fornitore, salva `metodo_pagamento` anche sul movimento, emette evento `FATTURA_PAGATA`. Stessi limiti: `pagato:true` senza verifica reale del pagamento, tripla incompleta, riferimento = numero fattura.
**Note**: duplicato funzionale di `process-existing-invoices`; superato dall'auto-conferma provvisori (`/api/prima-nota/provvisori/auto-conferma-per-metodo`) che è idempotente e rollbackabile.

### GET /api/prima-nota-auto/stats — statistiche automazione
**Cosa fa**: contatori per la dashboard automazione.
**Logica codice**: count su `invoices` (non pagate, senza metodo), `prima_nota_cassa/banca` (tutti, inclusi deleted), `assegni` (totali/non associati), `suppliers` (con/senza metodo pagamento).

### POST /api/prima-nota-auto/import-versamenti — import versamenti CSV
**Cosa fa**: importa i versamenti in banca (uscite di cassa) da CSV formato banca (`;`).
**Logica codice**: pandas multi-encoding; per riga: `Data contabile` (DD/MM/YYYY→ISO), `Importo` (formato italiano), `Descrizione` (default "Versamento del …"); dedup su `data+importo+categoria:"Versamento"` in cassa; insert uscita `source:"csv_import"`.

### POST /api/prima-nota-auto/import-pos — import POS giornalieri
**Cosa fa**: importa il battuto POS serale (contato dall'operatore) come USCITE di cassa (i soldi vanno verso la banca).
**Logica codice**: colonne esatte `DATA`/`IMPORTO`; dedup per `data + categoria:"POS" + source in [xlsx_import, manual_pos, excel_pos]` (max 1 POS per giorno); insert uscita `categoria:"POS"`, `source:"xlsx_import"`. La riconciliazione con l'XML RT e con gli accrediti in banca avviene altrove (pagina Coerenza POS).

### POST /api/prima-nota-auto/import-corrispettivi-xml — import XML registratore telematico
**Cosa fa**: salva i dati dell'XML RT (contanti, elettronico, dettaglio IVA) nella collection `corrispettivi`. NON scrive in prima nota.
**Logica codice**: ElementTree; estrae `DataOraRilevazione` (→data), `PagatoContanti`/`PagatoElettronico`, riepiloghi IVA (aliquota/imponibile/imposta). Upsert per `data` su `corrispettivi` con `source:"xml_import"`, `iva_popolata:true`. Commento esplicito (feedback utente 23/04/2026): l'entrata/uscita cassa la inserisce l'operatore a mano la sera; il flusso automatico precedente creava duplicati. Alternativa manuale: `POST /api/prima-nota/cassa/crea-entrata-da-corrispettivo`.
**Note**: (1) il parametro `force_import` è di fatto inutile: i rami `existing and not force_import` e `existing and force_import` eseguono lo stesso identico update. (2) Pattern fragile `elem.find('{*}X') or elem.find('X')`: un Element foglia trovato è "falsy" in ElementTree, quindi il primo find valido viene scartato e si ricade sul secondo; funziona solo perché gli XML RT tipici sono senza namespace — con namespace i totali uscirebbero a 0.

### POST /api/prima-nota-auto/import-corrispettivi-xml-multipli — import XML multipli
**Cosa fa**: carica N file XML in un colpo.
**Logica codice**: loop che invoca `import_corrispettivi_xml(file)` per ciascun file, aggregando successi/errori (HTTPException → dettaglio per file).
**Note**: il contatore `duplicati` non scatta mai (l'import singolo risponde sempre `success:true` anche sugli aggiornamenti).

---

## accounting/prima_nota_salari.py (prefisso /api/prima-nota-salari)

Sistema "buste vs bonifici" per gli stipendi: record su `prima_nota_salari` con `dipendente, mese, anno, importo_busta, importo_bonifico, saldo (bonifico−busta), progressivo` (riporto cumulativo). Regola dichiarata degli import: MAI aggregare, un record per riga file. Helper: `normalize_name()`, `get_mese_numero()` (supporta tredicesima=13, quattordicesima=14), `ricalcola_progressivi_tutti()` (ordina per anno/mese/created_at per dipendente, cumula i saldi; salta record con `vincolo:true`; supporta anno_inizio e anni esclusi).

### GET /api/prima-nota-salari/salari — lista record salari
**Cosa fa**: elenco record buste/bonifici filtrabile per anno/mese/dipendente.
**Logica codice**: find su `prima_nota_salari` (regex case-insensitive su `dipendente`), sort anno/mese desc + dipendente asc. Ritorna lista pura.

### GET /api/prima-nota-salari/salari/riepilogo — riepilogo statistiche
**Cosa fa**: totali buste/bonifici/saldo, dipendenti unici, riconciliati per anno (opz. mese).
**Logica codice**: find + somme in Python su `importo_busta/importo_bonifico/saldo`; conta i `riconciliato:true`.

### POST /api/prima-nota-salari/import-paghe — import file paghe
**Cosa fa**: carica l'Excel del commercialista con gli stipendi netti (buste).
**Logica codice**: pandas; rileva le colonne per keyword (dipendente/nome, mese, anno, stipendio/netto/busta…); per riga crea record `tipo:"busta"` con `importo_busta`, `importo_bonifico:0`, `saldo:-importo`; mese anche da datetime o nome italiano; alla fine `ricalcola_progressivi_tutti()`.
**Note**: nessun dedup: rilanciare lo stesso file duplica tutte le righe (per pulire: `/consolida-record` o `/salari/reset?tipo=busta`).

### POST /api/prima-nota-salari/import-bonifici — import file bonifici
**Cosa fa**: carica l'Excel dei bonifici stipendio erogati.
**Logica codice**: come import-paghe ma speculare (`tipo:"bonifico"`, `saldo:+importo`); il mese può essere una data completa (estrae mese+anno, anche via dateutil); anno default 2024 se manca la colonna. Ricalcola i progressivi a fine import.
**Note**: stesso rischio duplicazione; accetta mese 13/14 ma in quel ramo `mese_nome` resta vuoto (controllo `1..12` invece di `1..14`, a differenza di import-paghe che usa `len(MESI_NOMI)`).

### POST /api/prima-nota-salari/ricalcola-progressivi — ricalcolo progressivi
**Cosa fa**: ricalcola saldi e progressivi cumulativi (tutti o un dipendente), con reset opzionale e anni esclusi.
**Logica codice**: parse `anni_esclusi` CSV; se `force_reset` azzera `progressivo/saldo` con `update_many`; poi `ricalcola_progressivi_tutti(db, anno_inizio, dipendente, anni_esclusi)`. Gli anni esclusi hanno progressivo 0 e non entrano nel cumulo; i record con `vincolo:true` non vengono toccati (ma nota: vengono anche saltati dal cumulo).

### POST /api/prima-nota-salari/salari/aggiustamento — riga di aggiustamento
**Cosa fa**: inserisce una riga manuale per allineare il saldo di un dipendente a quello del commercialista.
**Logica codice**: record `tipo:"aggiustamento"` con busta/bonifico passati nel body, saldo = bonifico−busta; poi ricalcolo progressivi del solo dipendente. Nome forzato upper.

### GET /api/prima-nota-salari/dipendenti-lista — nomi dipendenti
**Cosa fa / Logica**: `distinct("dipendente")` su `prima_nota_salari`, ordinato. Alimenta i filtri della UI.

### DELETE /api/prima-nota-salari/salari/reset — reset record
**Cosa fa**: elimina tutti i record o solo un tipo (`busta|bonifico|aggiustamento`).
**Logica codice**: `delete_many` hard con filtro opzionale su `tipo`.
**Note**: con `tipo=None` cancella l'intera collection, inclusi i record legacy dell'altro schema (quelli di `/api/prima-nota/salari`).

### DELETE /api/prima-nota-salari/pulisci-righe-vuote — pulizia righe vuote
**Cosa fa**: rimuove i record con busta E bonifico entrambi 0/null/mancanti (residui di import falliti).
**Logica codice**: `delete_many` con `$and` di due `$or` (in [None,0] o campo assente). Chiamato dal bottone "Pulisci righe vuote" di PrimaNotaSalariTab.
**Note**: elimina anche i record legacy schema-vecchio (che non hanno `importo_busta/bonifico`) — inclusi quelli creati da `/api/prima-nota/salari` con campo `importo`.

### POST /api/prima-nota-salari/consolida-record — consolida buste+bonifici
**Cosa fa**: unisce i record dello stesso dipendente/anno/mese in un'unica riga (dopo import separati o doppi).
**Logica codice**: raggruppa in Python tutta la collection, somma buste e bonifici; se ci sono gruppi multipli fa `delete_many({})` TOTALE e reinserisce i consolidati; ricalcola i progressivi.
**Note**: distruttivo: perde `tipo`, `descrizione`, `vincolo`, `riconciliato` e scarta i gruppi con chiave incompleta (dipendente/anno/mese mancanti), record legacy inclusi.

### DELETE /api/prima-nota-salari/salari/{record_id} — elimina record
**Cosa fa / Logica**: `delete_one({id})` hard, 404 se assente. Non ricalcola i progressivi (restano stantii fino al prossimo ricalcolo).

### PUT /api/prima-nota-salari/salari/{record_id} — aggiorna record
**Cosa fa**: modifica un record (dipendente, periodo, importi, vincolo).
**Logica codice**: ricalcola `saldo = bonifico−busta` e `mese_nome`; `$set` completo con default (anno 2025, mese 1) se i campi mancano nel body; gestisce flag `vincolo`.
**Note**: non ricalcola il progressivo del dipendente: serve chiamare `/ricalcola-progressivi` dopo.

### PUT /api/prima-nota-salari/salari/{record_id}/riconcilia — flag riconciliato
**Cosa fa / Logica**: `$set riconciliato` (query param, default true) + `data_riconciliazione` (null se si de-riconcilia). 404 se assente.

### GET /api/prima-nota-salari/export-excel — export Excel salari
**Cosa fa**: scarica .xlsx con Dipendente/Anno/Mese/Busta/Bonifico/Saldo/Progressivo/Riconciliato.
**Logica codice**: openpyxl diretto con header stilizzati (blu Ceraldi `1E3A5F`); stessi filtri anno/mese della lista; filename dinamico.

---

## accounting/prima_nota_salari_v2.py (prefisso /api/prima-nota-salari-v2)

Vista DARE/AVERE salari calcolata on-the-fly (nessuna collection propria): DARE = netto cedolino (`cedolini`, estratto da `_netto_da_cedolino()` con fallback su vari campi anche da parsing AI), AVERE = acconti (`acconti_dipendenti`, per data = criterio di cassa) + bonifici stipendio dall'estratto conto non già linkati ad acconti. Anti-duplicazione: se un acconto ha `movimento_bancario_id`, quel movimento EC non compare anche come bonifico.
**Nota**: il docstring del modulo dichiara i path sotto `/api/prima-nota-salari/...` ma il registry monta il router su `/api/prima-nota-salari-v2` — docstring obsoleto.

### GET /api/prima-nota-salari-v2/dipendente/{dipendente_id} — prima nota annuale dipendente
**Cosa fa**: accordion mensile DARE/AVERE di un dipendente per l'anno: cedolini, acconti, bonifici, saldo e stato mese.
**Logica codice**: dipendente per `id|codice_fiscale`; carica cedolini dell'anno (match per `dipendente_id` o CF), acconti per range data, bonifici EC via `_bonifici_dipendente_anno()` (filtro permissivo: regex cognome sulla descrizione + `data_contabile_obj` nell'anno + uscita/importo negativo, poi ri-verifica del cognome in Python). Esclude i movimenti EC "consumati" da acconti riconciliati. Per mese: `totale_dare/avere`, saldo, stato = vuoto | quadrato (|saldo|<0,01) | in_pagamento (saldo>0) | anticipato. Riepilogo annuale con contatori mesi.
**Note**: il match bonifici per solo cognome può attribuire al dipendente bonifici a omonimi/fornitori col medesimo cognome.

### GET /api/prima-nota-salari-v2/collettiva — matrice dipendenti × mesi
**Cosa fa**: vista collettiva annuale (o di un singolo mese) con saldo e stato per cella, per tutti i dipendenti attivi.
**Logica codice**: 3 query batch (cedolini, acconti, movimenti EC del range) invece di N chiamate; indicizza i dipendenti per id e per cognome; aggrega in bucket `dip×mese` (cedolini anche via match CF); bonifici attribuiti per PRIMO cognome che compare nella descrizione; esclude movimenti consumati da acconti; scarta i dipendenti senza alcun movimento nel periodo. `solo_attivi=true` esclude i `dimissionato`. Totali globali dare/avere/saldo.
**Note**: stessa fragilità del match per cognome, aggravata: con due dipendenti dal cognome contenuto uno nell'altro, vince il primo nell'ordine di iterazione del dict.

---

## dati_provvisori.py (prefisso /api)

Due sistemi nella stessa file, entrambi sulla collection `dati_provvisori`: (A) staging "fatture da email/XML" con scelta manuale cassa/banca (route `/dati-provvisori/*`); (B) "proposte di pagamento" fattura↔movimento banca generate automaticamente e confermate dall'utente (route top-level `/proposte`, `/conferma*`, `/rifiuta`, `/genera-proposte`, che delegano a `app/services/dati_provvisori_service.py`). Tutti gli endpoint usano il decorator `@handle_errors`. Frontend: `DatiProvvisoriPage.jsx`.

### GET /api/dati-provvisori — lista dati provvisori
**Cosa fa**: elenca le fatture in staging (da email/XML) in attesa di classificazione.
**Logica codice**: find su `dati_provvisori` con `stato` param, default "tutto tranne processed"; sort per `data_ricezione` desc, max 500.
**Note**: senza filtro `stato` restituisce anche le proposte di pagamento del sistema B (stessa collection).

### POST /api/dati-provvisori/sposta-cassa — sposta in cassa (scelta manuale)
**Cosa fa**: l'utente classifica il dato provvisorio come pagamento in contanti → crea il movimento in Prima Nota Cassa.
**Logica codice**: crea in `prima_nota_cassa` un'uscita `categoria:"fornitori"`, `fonte:"dato_provvisorio"`, `metodo_scelto_manualmente:"cassa"`; marca il dato `stato:"processed"`, `destinazione:"cassa"`, con `movimento_id`.
**Note**: BUG/anomalia: salva `importo` NEGATIVO (`-abs(importo)`) con `tipo:"uscita"`, contro la convenzione del modulo (importi positivi). Nelle aggregate di `GET /cassa` un'uscita negativa AUMENTA il saldo invece di diminuirlo. Non valida i campi del body (KeyError→500 gestito da handle_errors). Non aggancia nessuna fattura di `invoices`.

### POST /api/dati-provvisori/sposta-banca — sposta in banca (scelta manuale)
**Cosa fa**: l'utente classifica il dato come pagamento bancario.
**Logica codice**: crea il movimento in… `estratto_conto_movimenti` (NON `prima_nota_banca`), con schema EC (`data_valuta`, `descrizione_originale`), importo negativo, `metodo_scelto_manualmente:"banca"`; marca il dato `processed`.
**Note**: il messaggio dice "Spostato in Prima Nota Banca" ma scrive nell'estratto conto: il movimento appare in Banca solo perché la vista è mista; salta i saldi di `prima_nota_banca` e crea un finto movimento EC non proveniente dalla banca.

### DELETE /api/dati-provvisori/{dato_id} — scarta dato provvisorio
**Cosa fa / Logica**: `delete_one({id})` hard su `dati_provvisori`, 404 se assente.

### POST /api/dati-provvisori/upload-xml — upload fattura XML in staging
**Cosa fa**: carica una fattura elettronica XML: se in staging esiste già la stessa fattura (arrivata da email) la arricchisce, altrimenti crea un nuovo dato provvisorio.
**Logica codice**: parse con BeautifulSoup (`CedentePrestatore/Denominazione`, `Numero`, `Data`, `ImportoTotaleDocumento`); il metodo pagamento XML è IGNORATO volutamente ("inaffidabile" — coerente con la regola "il metodo fornitore comanda"). Match esistente per `numero_documento` + regex sui primi 10 caratteri del fornitore; update (`xml_caricato:true`, `xml_data` = XML intero) o insert `stato:"pending", fonte:"xml"`.
**Note**: `soup.find("Numero")`/`find("Data")` prendono il PRIMO tag col quel nome in tutto l'XML: su fatture con più documenti/DDT collegati può pescare il campo sbagliato. Salva l'XML integrale nel documento Mongo (pesante).

### POST /api/dati-provvisori/riconcilia-estratto-conto — riconciliazione cassa→banca
**Cosa fa**: dopo il caricamento dell'estratto conto, individua i pagamenti classificati a mano in cassa che in realtà risultano usciti dalla banca.
**Logica codice**: per ogni movimento cassa `metodo_scelto_manualmente:"cassa"` non riconciliato, cerca in `estratto_conto_movimenti` un importo tra `-importo±1€` con `data_valuta` entro ±7 giorni; se trovato marca il movimento cassa `riconciliato:true, spostato_in_banca:true` (con id incrociati) e il movimento EC `riconciliato:true`.
**Note**: docstring bugiardo: dice "SPOSTA da cassa a banca" ma il movimento NON viene rimosso dalla cassa né soft-deleted — resta lì e continua a pesare sul saldo cassa; viene solo flaggato. Funziona solo sui movimenti creati da `sposta-cassa` (importo negativo, `data` ISO richiesta da `fromisoformat`).

### POST /api/genera-proposte — genera proposte fattura↔banca
**Cosa fa**: analizza le fatture "da bonifico" non pagate dell'anno e propone l'abbinamento col movimento bancario, in staging da confermare.
**Logica codice**: delega a `genera_proposte_pagamento()` (service): fatture con `payment_method in [bonifico, sepa, rid, domiciliazione, ""]` non pagate; movimenti EC uscita dell'anno indicizzati per importo esatto; scoring nome fornitore (+30/parola), P.IVA (+50), keyword VS.DISP/BONIFICO (+10), distanza data (+20/+10/−20); se score ≥10 crea doc `tipo:"pagamento_fattura", stato:"da_confermare", confidence` in `dati_provvisori` e "consuma" il movimento per le altre fatture della run. Dedup su `fattura_id` già proposto.
**Note**: `anno` è query param con default 2026 hard-coded. Soglia 10 = basta la keyword BONIFICO: le proposte a bassa confidence vanno guardate prima di "conferma-tutte".

### GET /api/proposte — lista proposte
**Cosa fa**: elenca le proposte di pagamento (default `stato:"da_confermare"`) ordinate per confidence.
**Logica codice**: find su `dati_provvisori` con `tipo:"pagamento_fattura"`, max 200; somma `fattura_importo` totale.

### POST /api/conferma/{proposta_id} — conferma proposta
**Cosa fa**: accetta l'abbinamento: registra il pagamento in Prima Nota Banca e marca la fattura pagata.
**Logica codice**: delega a `conferma_proposta()` (service): idempotente se già confermata; crea movimento in `prima_nota_banca` (`tipo:"uscita"`, categoria "Fatture", riferimento `FATT-{id}`, `movimento_banca_id`, `source:"conferma_provvisori"`, data = data movimento EC convertita in ISO); aggiorna `invoices` (`stato_pagamento:"pagata"`, `prima_nota_id/tipo`, `data_pagamento`); marca la proposta `confermata`.
**Note**: setta solo `stato_pagamento`, non `pagato/paid`; non marca il movimento EC come `riconciliato` (a differenza dell'auto-conferma di sync.py) → lo stesso movimento può essere ri-matchato altrove.

### POST /api/conferma-tutte — conferma tutte le proposte
**Cosa fa / Logica**: delega a `conferma_tutte()`: loop di `conferma_proposta` su tutte le `da_confermare` (max 500), ritorna confermati/errori.

### POST /api/rifiuta/{proposta_id} — rifiuta proposta
**Cosa fa / Logica**: delega a `rifiuta_proposta()`: `$set stato:"rifiutata"` + timestamp. La fattura resta non pagata e riproponibile? No: il dedup di genera-proposte salta le fatture con QUALSIASI proposta esistente (anche rifiutata), quindi un rifiuto è definitivo finché non si cancella il doc.

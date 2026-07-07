# Endpoint — Banca e Riconciliazione (area 04)

Documentazione operativa degli endpoint dei moduli banca/riconciliazione (FastAPI + MongoDB).
Collezione canonica movimenti banca: `estratto_conto_movimenti`. Schema canonico collegamento assegno↔fatture: `fatture_collegate=[{fattura_id, quota, data_collegamento}]` (max 4 fatture, stesso fornitore, tolleranza ±0,005€).

---

## assegni.py (/api/assegni)

Gestione carnet assegni: generazione, CRUD, ciclo di vita (vuoto→compilato→emesso→incassato), collegamento a fatture. Convivono DUE modelli dati: quello canonico a quote (`fatture_collegate[]`, scritto da `PUT /{id}/fatture-collegate` e dall'auto-matcher) e una serie di meccanismi LEGACY paralleli che scrivono solo campi flat (`beneficiario`, `numero_fattura`, `fattura_id`/`fattura_collegata`/`fattura_associata`) senza toccare quote né `importo_pagato` delle fatture.

### GET /api/assegni/stati — elenco stati
**Cosa fa**: restituisce il dizionario statico degli stati assegno con label e colore.
**Logica codice**: ritorna la costante `ASSEGNO_STATI` (vuoto, compilato, emesso, parzialmente_assegnato, assegnato, incassato, annullato, scaduto). Nessun accesso DB.

### POST /api/assegni/genera — genera carnet
**Cosa fa**: crea N assegni progressivi (1-100) a partire da un numero `PREFISSO-NUMERO`.
**Logica codice**: valida il formato, verifica in `assegni` che nessun numero esista già (una find_one per numero), inserisce documenti con stato `vuoto`, `fatture_collegate=[]` e uuid.

### GET /api/assegni — lista assegni
**Cosa fa**: lista paginata con filtri stato/fornitore_piva/search/anno.
**Logica codice**: legge `assegni` escludendo `entity_status=deleted`; filtro anno via regex su `data_emissione`/`data` (stringhe YYYY-MM-DD), gli assegni senza data restano sempre visibili; search regex su numero/beneficiario; sort stato+numero.

### GET /api/assegni/stats — statistiche per stato
**Cosa fa**: conteggi e totali importo raggruppati per stato, con filtro anno opzionale.
**Logica codice**: aggregate `$group` su `assegni` (esclusi deleted) + count_documents.

### GET /api/assegni/senza-associazione — assegni orfani
**Cosa fa**: elenca assegni con importo ma senza beneficiario, raggruppati per importo.
**Logica codice**: find su `assegni` con beneficiario null/""/"N/A" e importo>0 (max 500), raggruppa per importo arrotondato.
**Note**: strumento di debug del filone legacy (guarda solo il campo flat `beneficiario`, non `fatture_collegate`).

### GET /api/assegni/preview-combinazioni — anteprima combinazioni
**Cosa fa**: mostra (senza scrivere) combinazioni di 2..max_assegni assegni senza beneficiario la cui somma coincide con una fattura non pagata.
**Logica codice**: legge `assegni` (senza beneficiario) e `invoices` non pagate (esclude RID/SDD/addebito via regex sui campi metodo pagamento); itertools.combinations, match su importo con delta fino a ±1€; ritorna primi 20.
**Note**: tolleranza larga (±1€) e nessun vincolo fornitore — solo esplorativo, coerente col filone legacy.

### GET /api/assegni/verifica-associazioni — audit associazioni
**Cosa fa**: analizza tutte le associazioni flat assegno→`fattura_id` e segnala problemi (importo ≠ ±5€, beneficiario≠fornitore fuzzy<60%, fattura mancante/già pagata, date >180gg).
**Logica codice**: carica assegni con `fattura_id` e TUTTE le `invoices` (fino a 50k) in memoria; usa `thefuzz.token_set_ratio`; per ogni problema propone fatture alternative con importo simile (±2€).
**Note**: opera sul campo legacy `fattura_id`, non su `fatture_collegate`; carico memoria elevato.

### PUT /api/assegni/correggi-associazione/{assegno_id} — correggi/rimuovi associazione flat
**Cosa fa**: sostituisce (o rimuove, se `nuova_fattura_id` assente) la fattura associata a un assegno e marca pagata/non pagata la fattura.
**Logica codice**: scrive su `assegni` i campi flat (`fattura_id`, `numero_fattura`, `stato="associato"`, `scarto_fattura_assegno`) e su `invoices` (`pagato`, `status=paid`, `assegno_id`, `metodo_pagamento_effettivo`); ripristina la vecchia fattura a `status=imported`. Warning se scarto >0,01€.
**Note**: LEGACY: usa `fattura_id` 1:1 e imposta lo stato non canonico `"associato"` (assente da `ASSEGNO_STATI`, un PUT generico successivo con quello stato verrebbe rifiutato); marca `paid` l'intera fattura anche se l'assegno la copre solo in parte.

### POST /api/assegni/auto-match — auto-matcher canonico
**Cosa fa**: esegue l'auto-matcher a 4 livelli (motore `assegni_auto_match.py`); con `dry_run=true` restituisce solo la proposta.
**Logica codice**: delega a `run_auto_match(db, dry_run)`; ritorna il report con match L1-L4, ambigui, non trovati e totali.

### GET /api/assegni/ambigui — assegni ambigui dell'auto-matcher
**Cosa fa**: elenca gli assegni con più fatture candidate (matcher conservativo) con dettaglio candidate.
**Logica codice**: esegue `run_auto_match` in dry_run, per ogni ambiguo rilegge assegno e `invoices` candidate (residuo = total−importo_pagato).
**Note**: ogni chiamata ricalcola tutto il matching (costoso), anche se in sola lettura.

### POST /api/assegni/{assegno_id}/risolvi-ambiguo — risoluzione manuale ambiguo
**Cosa fa**: collega manualmente un assegno ambiguo a 1+ fatture indicate nel body.
**Logica codice**: valida assegno non già collegato (`fatture_collegate` vuoto), carica le fatture con residuo, applica `_apply_match(..., livello="MANUAL")` del motore canonico (scrive quote, `importo_pagato`, `prima_nota_banca`).

### GET /api/assegni/proposte-associazione — proposte pendenti
**Cosa fa**: lista le proposte `da_confermare` generate da `/auto-associa` (confidenza <80%).
**Logica codice**: find su `proposte_associazione_assegni` ordinate per confidenza desc.

### GET /api/assegni/{assegno_id} — dettaglio
**Cosa fa**: restituisce l'assegno per id o numero.
**Logica codice**: find_one su `assegni` con `$or` id/numero, 404 se assente.

### PUT /api/assegni/{assegno_id} — aggiornamento generico
**Cosa fa**: aggiorna campi arbitrari dell'assegno (compilazione, cambio stato).
**Logica codice**: rimuove id/numero/created_at dal body, valida `stato` contro `ASSEGNO_STATI`; se si compilano importo+beneficiario su assegno `vuoto` passa automaticamente a `compilato`.
**Note**: accetta qualunque altro campo senza whitelist (può sovrascrivere campi gestionali come `fatture_collegate`).

### PUT /api/assegni/{assegno_id}/fatture-collegate — collegamento canonico N:M
**Cosa fa**: endpoint manuale CANONICO: sostituisce l'intero set di collegamenti dell'assegno con quello passato (quote in euro; quota negativa = nota di credito TD04).
**Logica codice**: valida max 4 fatture (`MAX_RATE`), quote ≠ 0, stesso fornitore (P.IVA normalizzata), somma quote ≤ importo assegno (±TOLL). Annulla i vecchi collegamenti (delta negativo su `importo_pagato`/`payment_status` delle fatture, `$pull` da `assegni_collegati`, delete dei movimenti `prima_nota_banca` con source `assegno_manuale`), poi applica i nuovi (delta positivo, `$push assegni_collegati`, movimento banca solo per quote positive). Stato: `assegnato` se somma=importo, altrimenti `parzialmente_assegnato`.

### POST /api/assegni/{assegno_id}/emetti — emissione
**Cosa fa**: porta l'assegno a `emesso` e registra l'uscita in prima nota banca.
**Logica codice**: rifiuta assegni `vuoto`; imposta `data_emissione` (default oggi); se ha importo crea movimento `prima_nota_banca` (categoria "Addebito assegno", source `assegno_emesso`) e salva `prima_nota_banca_id` sull'assegno.
**Note**: possibile doppio movimento banca per lo stesso assegno se poi si usa fatture-collegate/auto-match (source diversi, nessuna dedup incrociata).

### POST /api/assegni/{assegno_id}/incassa — incasso
**Cosa fa**: marca l'assegno `incassato` e propaga a prima nota, fattura, scadenzario ed estratto conto.
**Logica codice**: set stato+`data_incasso`; riconcilia `prima_nota_banca` (via `prima_nota_banca_id`); se `fattura_collegata` marca `invoices.pagato=true` e chiude `scadenziario_fornitori`; emette evento `FATTURA_PAGATA` sull'event bus; se passato `movimento_estratto_conto_id` marca il movimento `estratto_conto_movimenti` riconciliato.
**Note**: la propagazione fattura usa solo il campo legacy `fattura_collegata` (singola), ignora `fatture_collegate[]`.

### POST /api/assegni/{assegno_id}/annulla — annullamento
**Cosa fa**: imposta stato `annullato`.
**Logica codice**: update_one su `assegni` per id o numero; non scollega fatture né rimuove movimenti banca.

### DELETE /api/assegni/clear-generated — pulizia per stato
**Cosa fa**: elimina fisicamente tutti gli assegni con un dato stato (default `vuoto`).
**Logica codice**: valida stato, `delete_many` su `assegni`.
**Note**: hard-delete senza controlli sui collegamenti; pericoloso per stati diversi da `vuoto`.

### DELETE /api/assegni/{assegno_id} — eliminazione singola
**Cosa fa**: soft-delete di un assegno con validazione business.
**Logica codice**: `BusinessRules.can_delete_assegno` (vieta emessi/incassati/collegati a fatture); imposta `entity_status=deleted` + `deleted_at`.
**Note**: il parametro `force` è dichiarato ma NON usato: non forza nulla.

### POST /api/assegni/auto-associa — auto-associazione LEGACY
**Cosa fa**: associa assegni a fatture con 4 fasi euristiche (importo ±0,5€, learning storico, N assegni uguali=1 fattura, fuzzy su causale); applica solo confidenza ≥80%, il resto diventa proposta.
**Logica codice**: legge `assegni` senza beneficiario, `suppliers` (filtra fornitori con metodo assegno/misto/vuoto), `invoices` non pagate; scrive campi flat (`beneficiario` sintetico "Pag. fatt. …", `numero_fattura`, `fattura_collegata`, `match_type`, `stato=compilato`); upsert proposte in `proposte_associazione_assegni`.
**Note**: LEGACY parallelo all'auto-matcher canonico: non scrive `fatture_collegate` né aggiorna `importo_pagato`/`payment_status` delle fatture; tolleranze larghe (0,5-2%) vs ±0,005€ del motore canonico; sovrascrive `beneficiario` con una stringa sintetica.

### POST /api/assegni/conferma-proposta/{proposta_id} — conferma proposta
**Cosa fa**: applica una proposta di `/auto-associa` all'assegno.
**Logica codice**: legge `proposte_associazione_assegni`, scrive sugli `assegni` gli stessi campi flat di auto-associa, marca proposta `confermata`.
**Note**: LEGACY (stessi limiti di auto-associa: nessuna quota, fattura non aggiornata).

### POST /api/assegni/rifiuta-proposta/{proposta_id} — rifiuta proposta
**Cosa fa**: marca la proposta `rifiutata`.
**Logica codice**: update su `proposte_associazione_assegni`, 404 se non modificata.

### POST /api/assegni/sync-da-estratto-conto — import assegni da EC (LEGACY)
**Cosa fa**: cerca in `estratto_conto_movimenti` le uscite con pattern "ASSEGNO" e crea/riconcilia assegni.
**Logica codice**: regex per estrarre il numero (priorità a `NUM:`, esclude "RILASCIO CARNET"); se il numero corrisponde a un assegno del carnet `compilato/emesso` lo marca `incassato`, chiude fattura (`fattura_collegata`) e scadenzario, emette evento FATTURA_PAGATA, riconcilia prima nota; altrimenti crea un nuovo assegno `emesso` con `fonte=estratto_conto` (fallback numero `AUTO-<id mov>`).
**Note**: LEGACY: gli assegni creati hanno solo campi flat; il match col carnet usa regex sulle ultime 8 cifre (rischio falsi positivi); NON marca il movimento EC come riconciliato.

### POST /api/assegni/ricostruisci-dati — ricostruzione dati mancanti (LEGACY)
**Cosa fa**: per assegni senza beneficiario/numero_fattura prova a estrarre il beneficiario dalla descrizione bancaria e ad associare una fattura per importo esatto.
**Logica codice**: carica in memoria `invoices`, `fornitori`, `estratto_conto_movimenti` (10k ciascuno); regex su pattern bancari (BEN:, BONIFICO A, ...) + lookup nomi fornitori; associa se una sola fattura con lo stesso importo, altrimenti confronta il beneficiario; scrive campi flat (`beneficiario`, `fattura_id`, `numero_fattura`, `ultima_ricostruzione`).
**Note**: LEGACY, il docstring dice "chiamata automaticamente dal frontend al caricamento pagina": ogni page-load può scrivere associazioni euristiche non validate. Nessun aggiornamento delle fatture.

### POST /api/assegni/correggi-numeri — fix numeri CRA→NUM
**Cosa fa**: corregge assegni il cui numero è stato estratto dal campo CRA (14+ cifre) invece che dal NUM.
**Logica codice**: find su `assegni` con numero `^\d{14,}$`, ri-estrae `NUM:` dalla descrizione, salva il vecchio numero in `numero_cra`.

### POST /api/assegni/associa-beneficiari-robusto — associazione per importo±10€ (LEGACY)
**Cosa fa**: per assegni senza beneficiario cerca fatture con importo simile (±10€) e in caso di più candidate sceglie la più vicina per data (≤90gg).
**Logica codice**: carica tutte le `invoices` (50k) indicizzate per importo arrotondato all'euro, `fornitori`; scrive campi flat (`beneficiario`, `fattura_associata` [numero], `fattura_id`, `associazione_automatica=true`).
**Note**: LEGACY e permissivo: ±10€ senza vincolo fornitore; il docstring promette gestione "pagamenti multipli" al punto 5 ma il codice non la implementa (il contatore `pagamenti_multipli` resta sempre 0).

### POST /api/assegni/associa-pagamenti-multipli — gruppo assegni→fattura (LEGACY)
**Cosa fa**: raggruppa gli assegni per beneficiario e cerca una fattura del fornitore con importo = somma del gruppo (±5€).
**Logica codice**: aggregate `$group` su beneficiario (count>1), find_one su `invoices` con regex sul supplier_name; marca tutti gli assegni del gruppo con `pagamento_multiplo*` e `fattura_associata`.
**Note**: LEGACY: usa il beneficiario come regex non-escaped (caratteri speciali possono rompere la query); campi flat, fattura non aggiornata.

### POST /api/assegni/cerca-combinazioni-assegni — combinazioni→fattura (LEGACY, scrive)
**Cosa fa**: versione "applicativa" di preview-combinazioni: trova combinazioni di 2..max assegni senza beneficiario che sommano a una fattura non pagata (± tolleranza, default 1€) e li associa tutti.
**Logica codice**: come preview (esclude fatture RID/SDD), ma scrive su `assegni` i campi flat `beneficiario`, `fattura_associata`, `fattura_id`, `pagamento_combinato`, `combinazione_assegni[]`; rimuove la fattura dall'indice per evitare doppi match.
**Note**: LEGACY: nessun vincolo fornitore/P.IVA, tolleranza fino a 10€, nessuna quota né aggiornamento fattura — alto rischio di associazioni spurie su importi comuni.

---

## assegni_learning.py (/api/assegni/learning)

"Learning machine" legacy: apprende pattern fornitore→importi dagli assegni già associati (collezione `assegni_learning`) e li usa per proporre/applicare associazioni. Tutto il modulo lavora sui campi flat (beneficiario/fattura_id/numero_fattura), MAI su `fatture_collegate` a quote: è un filone parallelo al matcher canonico.

### POST /api/assegni/learning/pulizia-duplicati — dedup assegni
**Cosa fa**: identifica (e con `dry_run=false` elimina) assegni duplicati per numero, record con numero vuoto e record totalmente vuoti.
**Logica codice**: carica tutti gli `assegni`, raggruppa per numero, mantiene il più completo (score: beneficiario 3, importo 2, fattura 2, stato pagato 1) e più recente; delete_one per gli altri.
**Note**: hard-delete; default prudente `dry_run=true`.

### POST /api/assegni/learning/learn — apprendimento pattern
**Cosa fa**: costruisce/aggiorna i pattern per fornitore (range e frequenza importi, keywords dalle descrizioni) dagli assegni con beneficiario.
**Logica codice**: legge `assegni`, normalizza il nome fornitore, upsert doc in `assegni_learning` (id `learn_<nome>`); aggiorna anche `fornitori_keywords` (solo update, no upsert) per fornitori con ≥2 assegni.

### GET /api/assegni/learning/suggerimenti/{importo} — suggerimenti per importo
**Cosa fa**: suggerisce fino a 10 fornitori i cui pattern appresi contengono importi compatibili (± tolleranza, default 10€).
**Logica codice**: find su `assegni_learning` per range min/max/medio; confidence = 100 − scostamento % dall'importo medio.

### POST /api/assegni/learning/associa-intelligente — associazione multi-strategia (LEGACY, scrive)
**Cosa fa**: associa assegni senza beneficiario/fattura con 3 strategie in cascata: importo quasi-esatto con candidata unica, fornitore noto dai pattern presente nella descrizione, overlap di keywords descrizione↔nome fornitore.
**Logica codice**: legge `assegni`, TUTTE le `invoices` con importo>0 (anche già pagate — il commento lo dichiara: "rimuovo filtro status per massimizzare associazioni") e `assegni_learning`; scrive campi flat (`beneficiario`, `fattura_id`, `numero_fattura`, `associazione_tipo`, `associazione_automatica`).
**Note**: LEGACY e rischioso: può associare fatture GIÀ PAGATE; tolleranze moltiplicate (×2, ×3) nelle strategie 2-3; nessun vincolo P.IVA.

### POST /api/assegni/learning/associa-combinazioni-avanzato — combinazioni (LEGACY, scrive)
**Cosa fa**: come cerca-combinazioni-assegni ma fino a 8 assegni e tolleranza fino a 20€; associa la combinazione alla prima fattura che matcha.
**Logica codice**: combinations su assegni senza beneficiario o non auto-associati, lookup per importo su TUTTE le invoices (incluse pagate); scrive campi flat + `pagamento_combinato`, `combinazione_*`.
**Note**: LEGACY: il filtro `$or` include `associazione_automatica≠true`, quindi può riprocessare assegni GIÀ associati manualmente; delta testati fissi ([0,±0.01,±0.5,±1,±2]) per cui tolleranze >2€ dichiarate non vengono realmente esplorate.

### GET /api/assegni/learning/stats-avanzate — statistiche qualità dati
**Cosa fa**: statistiche su copertura beneficiari/fatture, stati, tipi di associazione, duplicati e "health score".
**Logica codice**: carica tutti gli `assegni` in memoria e calcola i contatori con Counter/defaultdict.

---

## assegni_auto_match.py (motore, nessun endpoint)

Motore CANONICO di auto-match assegni↔fatture richiamato da `/api/assegni/auto-match`, `/ambigui`, `/{id}/risolvi-ambiguo`. Non registra route.
**Livelli**: L1 (1 assegno = 1 fattura stesso importo ±0,005€); L2 (2-4 assegni di importo uguale, stesso fornitore e stesso carnet, finestra ≤4 mesi = 1 fattura, tolleranza ±0,005€×N); L3 (2-4 assegni di importi diversi stesso fornitore, finestra 60gg = 1 fattura); L4 (1 assegno = 2-4 fatture stesso fornitore, sulle top-10 per residuo).
**Regole**: vincolo rigido P.IVA (assegni senza P.IVA vengono arricchiti da `fornitori` via ragione sociale normalizzata, altrimenti finiscono in `non_trovati`); conservativo (più candidate ⇒ `ambigui`, con dedup dei duplicati storici stessa fattura); idempotente (movimento `prima_nota_banca` con source `assegno_auto_match` creato solo se assente).
**Scritture**: `assegni.fatture_collegate[]` a quote + stato assegnato/parzialmente_assegnato; `invoices.importo_pagato/importo_residuo/payment_status/pagato` + `$push assegni_collegati`; `prima_nota_banca` (uscita per quota).
**Note**: in `_try_l2` il ramo "ambiguous" restituisce comunque la prima candidata ma l'orchestratore lo tratta come non-match senza segnalarlo nella lista ambigui (i gruppi L2 ambigui non emergono nel report).

### Anomalie (gruppo assegni)
1. Quattro schemi di collegamento fattura coesistono sugli assegni: canonico `fatture_collegate[]` + tre campi flat (`fattura_id`, `fattura_collegata`, `fattura_associata`) usati da endpoint diversi — un assegno può risultare "collegato" per un endpoint e "libero" per un altro.
2. `correggi-associazione` scrive lo stato `"associato"` assente da `ASSEGNO_STATI` → un successivo PUT generico con quello stato viene rifiutato.
3. Tre implementazioni quasi identiche della logica "combinazioni" (`preview-combinazioni`, `cerca-combinazioni-assegni`, `learning/associa-combinazioni-avanzato`) con tolleranze incoerenti (±1/±2/±10€) vs ±0,005€ del motore canonico.
4. `learning/associa-intelligente` e `learning/associa-combinazioni-avanzato` caricano le fatture SENZA filtro pagamento: possono associare fatture già pagate (commento esplicito nel codice).
5. `associa-pagamenti-multipli` usa il beneficiario come regex non-escaped su `supplier_name` (crash/match errati con caratteri speciali).
6. Tre `source` diversi in `prima_nota_banca` (`assegno_emesso` importo intero, `assegno_manuale` e `assegno_auto_match` a quote) senza controlli incrociati → possibili uscite duplicate per lo stesso assegno.
7. `incassa` e `sync-da-estratto-conto` propagano il pagamento solo dal campo flat `fattura_collegata`: un assegno collegato via schema canonico non chiude fattura/scadenzario all'incasso.
8. Hard-delete (`clear-generated`, `learning/pulizia-duplicati`) senza le business rules del DELETE singolo; parametro `force` dichiarato ma mai usato.
9. Endpoint pesanti: `verifica-associazioni` e `associa-beneficiari-robusto` caricano fino a 50k fatture in memoria; `GET /ambigui` riesegue l'intero auto-match a ogni chiamata.

---

## estratto_conto.py (/api/estratto-conto-movimenti)

Modulo canonico per l'estratto conto: importa CSV/Excel home-banking (delimitatore `;`), scrive in `estratto_conto_movimenti` e orchestra le riconciliazioni automatiche (fatture, paghe, stipendi); include consultazione, riepiloghi ed export Excel. 12 endpoint.

### POST /api/estratto-conto-movimenti/import — import CSV/Excel estratto conto
**Cosa fa**: importa i movimenti da CSV/Excel, deduplica e avvia 3 riconciliazioni automatiche.
**Logica codice**: parsing multi-encoding e varianti nomi colonna; helper `estrai_fornitore_pulito`/`estrai_numero_fattura`; dedup su (data, |importo|, descrizione[:80]); commissioni ≤2€ sempre inserite; forzatura `tipo=uscita` per keyword (DISPOSIZIONE, F24/I24, CBILL…); `insert_many` su `estratto_conto_movimenti` (importo in valore assoluto, `id=EC-data-importo-hash`). Post-import: `riconcilia_estratto_conto()`, `esegui_riconciliazione_paghe_completa()`, riconciliazione fatture provvisorie via `find_ec_match_for_invoice` (scrive `prima_nota_banca`, aggiorna `invoices`, marca il movimento riconciliato); eventi `fattura.pagata` e `estratto_conto.importato` su due event bus diversi.
**Note**: endpoint "grasso": import + side-effect contabili su 4 collezioni in un'unica chiamata.

### POST /api/estratto-conto-movimenti/force-reimport — reimport (solo CSV)
**Cosa fa**: reimporta un CSV inserendo solo i movimenti nuovi; nonostante il nome, non forza nulla.
**Logica codice**: stesso parsing CSV dell'import; dedup contro le chiavi esistenti nel range date; insert dei soli non-duplicati; nessuna cancellazione, nessuna riconciliazione automatica.
**Note**: il docstring MENTE: dichiara "cancella TUTTI i record degli anni presenti nel CSV" e "inserisce senza deduplicazione", ma il codice non cancella mai e deduplica (anche le commissioni ≤2€ che l'import normale accetta sempre). Di fatto un duplicato di `/import` senza riconciliazioni.

### GET /api/estratto-conto-movimenti/movimenti — lista movimenti con saldi
**Cosa fa**: movimenti paginati (anno/mese/categoria/fornitore/tipo) con totali e saldi progressivi.
**Logica codice**: filtro range lessicografico su campo stringa `data` (YYYY-MM-DD); sort desc + skip/limit; due aggregate per totali anno e saldo anni precedenti (`$toDouble`, split per `tipo`).

### GET /api/estratto-conto-movimenti/categorie — categorie uniche
**Cosa fa**: elenco ordinato delle categorie distinte. **Logica codice**: `distinct("categoria")`.

### GET /api/estratto-conto-movimenti/fornitori — fornitori unici
**Cosa fa**: elenco ordinato dei fornitori distinti. **Logica codice**: `distinct("fornitore")`.

### GET /api/estratto-conto-movimenti/riepilogo — riepilogo aggregato
**Cosa fa**: conteggi/totali entrate-uscite + top 10 categorie con filtri.
**Logica codice**: filtro data via regex `^anno-mese` (diverso da `/movimenti` che usa range); due aggregate group per `tipo` e `categoria` (con `$abs`).

### DELETE /api/estratto-conto-movimenti/clear — cancellazione massiva
**Cosa fa**: elimina i movimenti EC di un anno o di tutto il DB.
**Logica codice**: `delete_many` con filtro opzionale regex `^anno` su `data`.
**Note**: senza `anno` svuota l'intera collezione canonica, incluse righe riconciliate; nessuna conferma.

### DELETE /api/estratto-conto-movimenti/{movimento_id} — elimina singolo movimento
**Cosa fa**: elimina un movimento per id applicativo. **Logica codice**: find_one (404) + delete_one.

### GET /api/estratto-conto-movimenti/export-excel — export Excel
**Cosa fa**: esporta i movimenti filtrati in .xlsx formattato con riga totali.
**Logica codice**: stessa query a filtri di `/movimenti` (ma data via regex), `to_list(10000)`, workbook openpyxl, `StreamingResponse`.
**Note**: BUG verificato: il tipo è ricalcolato dal segno (`importo >= 0` → "Entrata") ma gli importer salvano `importo` in valore assoluto → tutto risulta "Entrata" e `totale_uscite`=0; ignora il campo `tipo` dei documenti.

### POST /api/estratto-conto-movimenti/riconcilia-stipendi — riconciliazione bonifici stipendio
**Cosa fa**: collega i bonifici "VOSTRA DISPOSIZIONE … FAVORE <nome>" ai dipendenti e alla prima nota salari.
**Logica codice**: mappa nomi da `prima_nota_salari.distinct("dipendente")` (fallback `dipendenti`) con varianti invertite e singole parole >3 char; match sul testo dopo "FAVORE"; setta `riconciliato_salario`, `dipendente_nome`, `categoria="Stipendi"` sul movimento e `estratto_conto_id` sul record salari (stesso mese/anno).
**Note**: la regex `"VOSTRA DISPOSIZIONE.*FAVORE|FAVORE.*"` matcha di fatto qualunque descrizione con "FAVORE"; il match su singola parola può dare falsi positivi su cognomi corti.

### GET /api/estratto-conto-movimenti/movimenti-stipendi — vista movimenti stipendio
**Cosa fa**: elenca i movimenti che sembrano stipendi raggruppati per dipendente riconciliato.
**Logica codice**: regex "VOSTRA DISPOSIZIONE|VS.DISP" + `tipo=uscita`, filtri anno/non-riconciliati; raggruppamento in Python con contatori.

### POST /api/estratto-conto-movimenti/ricategorizza-batch — ricategorizzazione automatica
**Cosa fa**: assegna categorie (stipendi, tributi, utenze…) ai movimenti senza categoria in base a keyword.
**Logica codice**: fino a 5000 record senza categoria, match keyword su descrizione+causale, update con `auto_categorizzato=True`.
**Note**: ANOMALIA: opera sulla collezione legacy `bank_movements`, NON su `estratto_conto_movimenti`: nel router canonico ma probabilmente senza effetto sui dati reali.

---

## bank_statement_parser.py (/api/estratto-conto)

Parser dedicato ai PDF BANCO BPM (PyMuPDF, parsing riga-per-riga inline) e agli estratti carta Nexi (parser esterno `estratto_conto_nexi_parser`). L'import BPM scrive in `prima_nota_cassa`, quello Nexi in `estratto_conto_nexi`: nessuno tocca la collezione canonica. 6 endpoint.

### POST /api/estratto-conto/parse — parse PDF BANCO BPM
**Cosa fa**: estrae intestatario, IBAN, saldi e transazioni da un PDF BPM senza salvare.
**Logica codice**: testo via `fitz`; `parse_banco_bpm_statement` (regex IBAN/saldi/periodo) + `extract_banco_bpm_transactions` (macchina a stati sulle righe, salta "SALDO INIZIALE"); totali entrate/uscite.
**Note**: intestatario hard-coded "CERALDI GROUP S.R.L." se presente nel testo.

### POST /api/estratto-conto/import — import PDF BPM in prima nota
**Cosa fa**: parsa il PDF e inserisce i movimenti come record di prima nota.
**Logica codice**: per ogni movimento dedup `find_one` su `prima_nota_cassa` {data, importo, tipo:"banca"}; insert con `tipo="banca"`, `tipo_movimento` entrata/uscita, `fonte="estratto_conto_import"`.
**Note**: il docstring dice "Prima Nota Banca" ma scrive in `prima_nota_cassa` (non in `prima_nota_banca` né nella canonica); il parametro `auto_riconcilia` è dichiarato ma MAI usato; il dedup usa importo sempre positivo → entrata e uscita di pari importo nello stesso giorno collidono.

### GET /api/estratto-conto/preview — info statica
**Cosa fa**: messaggio informativo su come usare il parser. **Logica codice**: dizionario statico, nessun DB.

### POST /api/estratto-conto/parse-nexi — parse PDF carta Nexi
**Cosa fa**: estrae metadata e transazioni categorizzate da un estratto Nexi senza salvare.
**Logica codice**: delega a `parse_estratto_conto_nexi`; 400 se il parser fallisce.

### POST /api/estratto-conto/import-nexi — import transazioni Nexi
**Cosa fa**: parsa e salva le transazioni carta nella collezione dedicata.
**Logica codice**: dedup `find_one` su `estratto_conto_nexi` {data, importo, descrizione}; insert con `id=nexi-<import_id>-<n>`, categoria, carta mascherata, `riconciliato=False`.
**Note**: collezione parallela `estratto_conto_nexi` separata dal flusso canonico (scelta voluta per la carta).

### GET /api/estratto-conto/nexi/movimenti — lista movimenti Nexi
**Cosa fa**: movimenti Nexi con filtri (anno, mese, categoria, riconciliato) e statistiche per categoria.
**Logica codice**: find paginato + count + aggregate group su `estratto_conto_nexi`.

---

## bank_statement_import.py (/api/bank-statement)

Secondo importer completo (PDF via pdfplumber con parser Intesa/UniCredit/generico, Excel/CSV via pandas) con riconciliazione automatica contro `prima_nota_banca`. Scrive in `estratto_conto_movimenti` con schema DIVERSO dall'importer canonico e traccia gli import in `bank_statements_imported`. 6 endpoint.

### GET /api/bank-statement/movements — lista movimenti EC normalizzata
**Cosa fa**: movimenti da `estratto_conto_movimenti` con normalizzazione date/tipo e totali.
**Logica codice**: filtro per ANNO con `$or` regex su `data_contabile`/`data_valuta` (formato italiano) e `data` (ISO); sort su `data_contabile` desc + limit; in Python deriva `data` ISO e `tipo` mancanti, poi applica il filtro fine per range e somma entrate/uscite.
**Note**: sort lessicografico su stringa gg/mm/aaaa (ordine errato tra mesi/anni) su un campo che l'importer canonico non scrive; il filtro per range è applicato DOPO il limit → possibili risultati mancanti.

### POST /api/bank-statement/import — import PDF/Excel/CSV con riconciliazione
**Cosa fa**: estrae movimenti dal file, li salva nell'EC e li riconcilia con la prima nota banca.
**Logica codice**: `extract_movements_from_pdf` (pdfplumber, `detect_bank_format`, parser per banca, fallback testo) o `extract_movements_from_excel` (pandas, `identify_columns`, regole keyword POS/BONIFICO/F24); dedup in-memory (data, tipo, importo); header import in `bank_statements_imported`; se `auto_reconcile` cerca match in `prima_nota_banca` (stessa data/tipo, importo ±1%) e lo marca riconciliato; anti-duplicato su `estratto_conto_movimenti` poi insert con `data` ISO E `data_contabile` italiana; evento `MOVIMENTO_BANCA_IMPORTATO`.
**Note**: duplica il flusso di `/api/estratto-conto-movimenti/import` con schema diverso (qui `data_contabile`, senza `fingerprint`/`riconciliato`); i duplicati saltati finiscono in `not_found_details` (semantica fuorviante).

### GET /api/bank-statement/stats — statistiche import/riconciliazione
**Cosa fa**: conta estratti importati e stato riconciliazione prima nota banca.
**Logica codice**: `count_documents` su `bank_statements_imported` e `prima_nota_banca` (+percentuale).

### POST /api/bank-statement/riconcilia-manuale — riconciliazione manuale
**Cosa fa**: marca un movimento di prima nota banca come riconciliato con un movimento EC indicato.
**Logica codice**: update su `prima_nota_banca` (`riconciliato`, `data_riconciliazione`, `estratto_conto_ref`); 404 se non modificato.
**Note**: asimmetrica: il movimento in `estratto_conto_movimenti` NON viene marcato riconciliato (a differenza del flusso di estratto_conto.py).

### POST /api/bank-statement/cleanup-duplicati — bonifica duplicati EC
**Cosa fa**: elimina i duplicati storici in `estratto_conto_movimenti` creati da import con formati data misti.
**Logica codice**: fino a 100k record, raggruppa per (data ISO normalizzata, importo, descrizione[:60], tipo); nei gruppi >1 tiene il record con più campi data (normalizzati via `bulk_write`) ed elimina gli altri a blocchi di 500.
**Note**: endpoint di manutenzione nato per riparare i danni della doppia scrittura ISO/italiana dei due importer; ignora lo stato `riconciliato` nella scelta del record da tenere.

### GET /api/bank-statement/formati-supportati — formati supportati
**Cosa fa**: elenco statico di banche/formati/encoding supportati. Nessun DB.

---

## bank_statement_bulk_import.py (/api/bank-statement-bulk)

Terzo importer: upload multiplo di PDF con parser universale (`universal_bank_statement_parser`), anteprima in cache in-memory (`PREVIEW_CACHE`, TTL 30 min) e commit su collezione a scelta (default `estratto_conto_movimenti`). 6 endpoint.

### POST /api/bank-statement-bulk/parse-bulk — parse multiplo con anteprima
**Cosa fa**: parsa N PDF, aggrega le transazioni in cache e restituisce un `preview_id`.
**Logica codice**: `parse_bank_statement` per file; accumula transazioni/totali/errori in `PREVIEW_CACHE[uuid[:12]]`; cleanup delle cache >30 min; risponde con le prime 100 transazioni.
**Note**: cache di processo (persa al riavvio, non multi-worker) — il commento stesso suggerisce Redis.

### GET /api/bank-statement-bulk/preview/{preview_id} — pagina anteprima
**Cosa fa**: transazioni in cache paginate skip/limit. **Logica codice**: lookup in `PREVIEW_CACHE`, 404 se scaduta.

### POST /api/bank-statement-bulk/commit/{preview_id} — salvataggio anteprima
**Cosa fa**: persiste le transazioni della preview nella collezione indicata e lancia la riconciliazione paghe.
**Logica codice**: per ogni tx: dedup `find_one` su {data, descrizione[:100], importo}; insert con campi `entrata`/`uscita`/`importo`, `stato="da_riconciliare"`, `import_batch_id`; evento `MOVIMENTO_BANCA_IMPORTATO`; a fine ciclo elimina la preview e chiama `esegui_riconciliazione_paghe_completa`.
**Note**: il parametro `collection` è testo libero dal client (può scrivere in QUALSIASI collezione Mongo); i record NON hanno `id` né `tipo` (l'evento pubblica `movimento_id=None`), schema incompatibile con l'importer canonico.

### DELETE /api/bank-statement-bulk/preview/{preview_id} — annulla anteprima
**Cosa fa**: elimina la preview dalla cache senza salvare. **Logica codice**: `del PREVIEW_CACHE[...]`; sempre success.

### POST /api/bank-statement-bulk/parse-single — parse singolo PDF
**Cosa fa**: parsa un PDF col parser universale, senza salvare né cachare.
**Logica codice**: `parse_bank_statement(content)`; 400 se fallisce.
**Note**: sovrapposto a `/api/estratto-conto/parse` (solo BPM) e a `/parse-bulk` con un file.

### POST /api/bank-statement-bulk/import-direct — parse+import in un passo
**Cosa fa**: parsa e importa direttamente più PDF saltando l'anteprima.
**Logica codice**: stesso parsing di parse-bulk e stessa insert/dedup di commit (collezione parametrica, `import_batch_id` comune); riepilogo per file.
**Note**: stesse anomalie di commit (collection libera, record senza id/tipo); NON lancia la riconciliazione paghe (incoerenza con commit) e non emette eventi.

---

## bank_main.py (/api/bank)

Router "architetturale" a strati (repository `BankStatementRepository` + service `BankService` su `Collections.BANK_STATEMENTS`), autenticato. In gran parte scheletro: 3 endpoint delegano al service, 4 sono placeholder. **7 endpoint reali (non 9)**.

### GET /api/bank/statements — lista bank statements (legacy)
**Cosa fa**: elenca i movimenti della collezione `bank_statements` filtrati per utente e date.
**Logica codice**: `BankService.list_statements(user_id, start_date, end_date)`.
**Note**: collezione legacy `bank_statements`, scollegata da `estratto_conto_movimenti`.

### POST /api/bank/statements/upload — crea bank statement (legacy)
**Cosa fa**: inserisce una singola transazione bancaria (payload JSON), non un file.
**Logica codice**: `service.create_statement()` → insert in `bank_statements`; 201.
**Note**: nome "upload" fuorviante: è una create JSON.

### POST /api/bank/reconcile — riconcilia (STUB)
**Cosa fa**: NON fa nulla: risponde sempre "Statement reconciled successfully"; body ignorato, nessun DB.
**Note**: endpoint finto: il client può credere che la riconciliazione sia avvenuta.

### GET /api/bank/assegni — lista assegni (STUB)
**Cosa fa**: restituisce sempre `[]`. **Note**: la gestione reale è in `bank/assegni.py`; residuo.

### POST /api/bank/assegni — crea assegno (STUB)
**Cosa fa**: non salva nulla: risponde `assegno_id: "placeholder"`.

### PUT /api/bank/assegni/{assegno_id} — aggiorna assegno (STUB)
**Cosa fa**: non fa nulla: risponde "Assegno updated".

### GET /api/bank/balance — saldo banca
**Cosa fa**: saldo calcolato dal service per utente (conto opzionale).
**Logica codice**: `service.get_balance(user_id, account)` su `bank_statements`.
**Note**: saldo sulla collezione legacy: non riflette `estratto_conto_movimenti`.

---

## bank_reconciliation.py (/api/bank-reconciliation)

Mini-CRUD autenticato sulla collezione legacy `bank_statements` più due stub. 5 endpoint.

### GET /api/bank-reconciliation/statements — lista statements
**Cosa fa**: fino a 500 documenti da `bank_statements` ordinati per `date` desc.
**Note**: nessun filtro per utente, a differenza di `/api/bank/statements` sulla stessa collezione.

### POST /api/bank-reconciliation/statements — crea statement
**Cosa fa**: inserisce un documento arbitrario in `bank_statements` (dict libero + uuid + created_at); 201.
**Note**: nessuna validazione di schema.

### DELETE /api/bank-reconciliation/statements/{statement_id} — elimina statement
**Cosa fa**: `delete_one({"id": ...})`; risponde "deleted" anche se non esisteva (nessun check su deleted_count).

### POST /api/bank-reconciliation/reconcile — riconcilia (STUB)
**Cosa fa**: non fa nulla: risponde sempre "Reconciliation completed".

### POST /api/bank-reconciliation/upload — upload file (STUB)
**Cosa fa**: legge il file solo per misurarne la dimensione; non parsa e non salva; `transactions_found: 0` fisso.
**Note**: fuorviante: sembra un import ma è un placeholder.

### Anomalie (gruppo estratto conto / bank)
1. Tre importer paralleli sulla stessa collezione con schemi diversi: `estratto_conto.py` (id `EC-…`, `fingerprint`, importo assoluto, `tipo`, `data` ISO), `bank_statement_import.py` (aggiunge `data_contabile` italiana, senza fingerprint/riconciliato), bulk (`entrata`/`uscita`, `stato`, SENZA `id` né `tipo`). Chiavi dedup diverse (desc[:80] vs esatta vs desc[:100]) → duplicati incrociati; `cleanup-duplicati` esiste apposta per ripararli.
2. Docstring mendaci: `force-reimport` (non cancella e deduplica), `parser /import` ("Prima Nota Banca" ma scrive `prima_nota_cassa`, `auto_riconcilia` ignorato), stub di bank_main/bank_reconciliation che rispondono successo senza fare nulla.
3. `ricategorizza-batch` opera su `bank_movements`, collezione mai scritta da questi router: probabile codice morto nel router canonico.
4. Il concetto "movimento banca" è spalmato su almeno 5 collezioni: `estratto_conto_movimenti`, `bank_statements`, `bank_statements_imported`, `estratto_conto_nexi`, `prima_nota_cassa` con tipo "banca" vs `prima_nota_banca`.
5. Bug export Excel (tipo derivato dal segno su importi assoluti → tutto "Entrata", verificato nel codice).
6. `commit`/`import-direct` accettano `collection` libera dal client (rischio integrità/sicurezza); `import-direct` non lancia la riconciliazione paghe che `commit` esegue.
7. Riconciliazione asimmetrica: `riconcilia-manuale` marca solo `prima_nota_banca`; il flusso di estratto_conto.py marca anche il lato EC.
8. Due event bus diversi per lo stesso dominio (`app.services.event_bus` vs `app.core.event_bus`).

---

## bonifici_module/ + bonifici_import_unificato.py (/api/archivio-bonifici)

Gestione Archivio Bonifici PDF: il router del package (`__init__.py`) monta 18 rotte con `add_api_route` da `jobs.py`, `transfers.py`, `riconciliazione.py`; `associazioni.py` ha prefix interno `/archivio-bonifici` ed è registrato con `/api` (stessi percorsi finali); `bank/bonifici_import_unificato.py` è un wrapper per la UI ImportUnificato. Collezioni: `bonifici_transfers` (moderna, UUID), `bonifici_jobs`, `archivio_bonifici` (LEGACY, ObjectId), `estratto_conto_movimenti`, `bonifici_email_attachments`, `prima_nota_salari`, `invoices`, `employees`, `suppliers`. Le costanti `COL_JOBS`/`COL_TRANSFERS`/`COL_RICONCILIAZIONE_TASKS` in `common.py` sono dichiarate ma MAI usate.

### POST /api/archivio-bonifici/jobs — crea job import
**Cosa fa**: crea un job di import vuoto e ne restituisce l'id (UUID).
**Logica codice**: insert in `bonifici_jobs` con `status='created'`, contatori a 0.

### GET /api/archivio-bonifici/jobs — lista job
**Cosa fa**: ultimi 100 job ordinati per created_at desc. **Logica codice**: find su `bonifici_jobs`.

### GET /api/archivio-bonifici/jobs/{job_id} — stato job
**Cosa fa**: documento del job (status, processed_files, errors, duplicates_skipped...). **Logica codice**: find_one, 404 se assente.

### POST /api/archivio-bonifici/jobs/{job_id}/upload — upload PDF/ZIP e avvio elaborazione
**Cosa fa**: riceve PDF e/o ZIP, li salva su disco e avvia l'elaborazione in background.
**Logica codice**: salva in `/tmp/bonifici_uploads/{job_id}` (nomi sanificati); estrae i PDF dagli ZIP (errori raccolti, max 50 sul job); job a `queued`; schedula `process_files_background`: per ogni PDF estrae testo (`pdf_parser.read_pdf_text`: pdfminer con fallback PyMuPDF) → `extract_transfers_from_text`, fallback `parse_filename_data` (pattern `IBAN_IMPORTO_DATA_CAUSALE.pdf`); PDF salvato Base64 in `pdf_data`; dedup via `build_dedup_key` (MD5 di iban|importo|data|causale) contro le chiavi già in `bonifici_transfers`; insert; infine `_auto_associate_bonifici`: match fuzzy per importo (±2%) + nome su `prima_nota_salari` (setta `salario_associato`, `operazione_salario_id` + back-link) e su `invoices` (setta `fattura_associata`, `fattura_id` + `bonifico_associato` sulla fattura); job `completed`.
**Note**: bug nell'auto-associazione: filtro anti-riuso `{"fattura_associata": {"$ne": True}}` su `invoices` ma sulla fattura viene settato `bonifico_associato` → la stessa fattura può agganciarsi a più bonifici. La dedup key usa i campi dello schema "filename" (`iban_beneficiario`, `data_esecuzione`) che il parser testuale non produce (`beneficiario.iban`, `data`) → per i bonifici da testo la chiave degenera a importo+causale.

### GET /api/archivio-bonifici/transfers — lista bonifici
**Cosa fa**: lista filtrabile per job, testo libero, ordinante, beneficiario, anno.
**Logica codice**: query su `bonifici_transfers`; search in `$or` regex (escaped) su `ordinante.nome`, `beneficiario.nome`, `causale`, `cro_trn`; `year` regex `^YYYY-` su `data`; sort data desc, limit 1000.

### GET /api/archivio-bonifici/transfers/count — conteggio
**Cosa fa**: conta i bonifici (opz. per job). **Logica codice**: `count_documents`.

### GET /api/archivio-bonifici/transfers/summary — riepilogo per anno
**Cosa fa**: count e somma importi per anno. **Logica codice**: aggregate `$substr` su `data` + `$group`.

### DELETE /api/archivio-bonifici/transfers/bulk — cancellazione massiva
**Cosa fa**: elimina i bonifici di un job, oppure TUTTI se `job_id` omesso.
**Logica codice**: `delete_many` su `bonifici_transfers` con query `{}` se job_id assente.
**Note**: senza job_id svuota l'intera collezione, nessuna conferma.

### DELETE /api/archivio-bonifici/transfers/{transfer_id} — elimina bonifico
**Cosa fa**: delete_one per id UUID, 404 se non trovato.

### PUT /api/archivio-bonifici/transfers/{transfer_id} — aggiorna bonifico
**Cosa fa**: aggiorna i campi editabili.
**Logica codice**: whitelist `causale, importo, data, note, categoria, salario_associato, operazione_salario_id, fattura_associata, fattura_id`; setta `updated_at`; 404 se assente.

### GET /api/archivio-bonifici/transfers/{transfer_id}/pdf — PDF originale
**Cosa fa**: restituisce il PDF del bonifico inline.
**Logica codice**: in ordine: campo `pdf_data` Base64; file su disco in `/tmp/bonifici_uploads` (se trovato lo cache-a in `pdf_data`); allegato in `bonifici_email_attachments` per filename non associato (se trovato copia il Base64 sul bonifico e marca l'allegato associato); 404 altrimenti.
**Note**: GET con side-effect di scrittura su due collezioni; firma dichiara StreamingResponse ma restituisce Response.

### GET /api/archivio-bonifici/export — export CSV/XLSX
**Cosa fa**: esporta i bonifici (max 10000, filtro job) in CSV (`;`) o XLSX.
**Logica codice**: colonne data/importo/valuta/ordinante(+iban)/beneficiario(+iban)/causale/cro_trn; XLSX via pandas+openpyxl (500 se pandas assente).

### POST /api/archivio-bonifici/riconcilia — riconcilia con estratto conto
**Cosa fa**: matcha i bonifici non riconciliati con i movimenti EC per importo (±0,01€ in valore assoluto) e data ±1 giorno.
**Logica codice**: carica `bonifici_transfers` non riconciliati (10k) e TUTTI gli `estratto_conto_movimenti` (50k); loop O(n·m) con set `movimenti_usati`; a match setta sul bonifico `riconciliato`, `data_riconciliazione`, `movimento_estratto_conto_id`, `movimento_data`, `movimento_descrizione`. Con `?background=true` crea un task nel dict in memoria `_riconciliazione_task` (asyncio.create_task).
**Note**: la variante background duplica la logica ma NON salva `movimento_data`/`movimento_descrizione`; nessuna scrittura sul movimento EC (link mono-direzionale); match solo importo+data → rischio falsi positivi su importi ricorrenti.

### GET /api/archivio-bonifici/riconcilia/task/{task_id} — stato task background
**Cosa fa**: progresso del task di riconciliazione. **Logica codice**: legge il dict in memoria, 404 se assente.
**Note**: stato volatile (perso al restart, non multi-worker); la persistenza Mongo suggerita da `COL_RICONCILIAZIONE_TASKS` non è mai stata implementata.

### GET /api/archivio-bonifici/stato-riconciliazione — statistiche riconciliazione
**Cosa fa**: totali/percentuale riconciliati e importi. **Logica codice**: count + aggregate `$group` per `riconciliato`.

### GET /api/archivio-bonifici/dashboard — dashboard bonifici
**Cosa fa**: contatori, percentuale, totali importi, ultimi 5 job, breakdown per anno.
**Logica codice**: aggregates su `bonifici_transfers` + find su `bonifici_jobs` limit 5.

### POST /api/archivio-bonifici/reset-riconciliazione — reset globale
**Cosa fa**: azzera la riconciliazione di TUTTI i bonifici.
**Logica codice**: `update_many({})`: `riconciliato: False`, `$unset` di `movimento_estratto_conto_id`/`data_riconciliazione`.
**Note**: non rimuove `movimento_data`/`movimento_descrizione` scritti dalla variante sincrona.

### POST /api/archivio-bonifici/associa-dipendenti — associa bonifici a dipendenti
**Cosa fa**: propone (default `dry_run=true`) o applica l'associazione bonifico→dipendente per IBAN uguale o nome contenuto.
**Logica codice**: bonifici con `salario_associato != True` × `employees` (nome+cognome+iban); se non dry_run setta `salario_associato`, `dipendente_id`, `dipendente_nome`; primi 50 candidati in risposta.
**Note**: non scrive nulla su `prima_nota_salari` (diversamente dall'auto-associazione di jobs.py).

### POST /api/archivio-bonifici/associa-fattura — associa fattura a bonifico (associazioni.py)
**Cosa fa**: collega una fattura a un bonifico (query param `bonifico_id`, `fattura_id`, `collection`).
**Logica codice**: 422 se fattura_id vuoto; 409 se `fattura_associata_id` già diverso; su `bonifici_transfers` setta `fattura_associata_id`, `fattura_collection`, `stato_riconciliazione="associato"`, `data_associazione`; fallback su `archivio_bonifici` via ObjectId; 404 se assente ovunque.
**Note**: usa campi (`fattura_associata_id`) DIVERSI da quelli di jobs/transfers (`fattura_associata`/`fattura_id`): due schemi di associazione paralleli e non interoperabili.

### DELETE /api/archivio-bonifici/disassocia-fattura/{bonifico_id} — rimuovi associazione fattura
**Cosa fa**: rimuove il collegamento fattura dal bonifico.
**Logica codice**: `$unset` di `fattura_associata_id/fattura_collection/data_associazione` + `stato_riconciliazione="non_riconciliato"`, prima su `bonifici_transfers` poi fallback legacy; non ripulisce nulla lato fattura.

### POST /api/archivio-bonifici/associa-salario — associa salario a bonifico
**Cosa fa**: collega un'operazione di prima nota salari a un bonifico.
**Logica codice**: update SOLO su `archivio_bonifici` per ObjectId: setta `operazione_salario_id`, `stato_riconciliazione="associato_salario"`.
**Note**: LEGACY-only: nessun fallback su `bonifici_transfers` → inutilizzabile sui bonifici della pipeline moderna (id UUID).

### DELETE /api/archivio-bonifici/disassocia-salario/{bonifico_id} — rimuovi associazione salario
**Cosa fa**: `$unset` su `archivio_bonifici` (solo legacy) + stato "non_riconciliato".

### GET /api/archivio-bonifici/fatture-compatibili/{bonifico_id} — fatture candidate
**Cosa fa**: propone fatture con importo entro ±5% del bonifico.
**Logica codice**: bonifico da `archivio_bonifici` (solo legacy); query `invoices` con `$or` su `totale`/`importo_totale`; max 50.
**Note**: il docstring promette anche match per "fornitore simile" MAI implementato; campi importo diversi da quelli usati dall'auto-associazione di jobs.py (`total_amount`).

### GET /api/archivio-bonifici/operazioni-salari/{bonifico_id} — salari candidati
**Cosa fa**: propone operazioni salari con `netto` entro ±5% dell'importo.
**Logica codice**: bonifico da `archivio_bonifici` (solo legacy); find su `prima_nota_salari`, max 50.
**Note**: campo `netto` mentre jobs.py matcha `importo_busta`/`importo_bonifico`: terzo schema importi.

### POST /api/archivio-bonifici/sync-iban-anagrafica — sync IBAN in anagrafica
**Cosa fa**: copia gli IBAN beneficiario dei bonifici legacy su dipendenti/fornitori che ne sono privi.
**Logica codice**: legge `archivio_bonifici` con `iban_beneficiario` (5000); regex-match del nome su `employees` e `suppliers` (primi 10 char); setta `iban` solo se mancante.
**Note**: `beneficiario` non regex-escaped (crash/injection con caratteri speciali); N+1 query; solo collezione legacy.

### GET /api/archivio-bonifici/dipendente/{dipendente_id} — bonifici di un dipendente
**Cosa fa**: elenca i bonifici legati a un dipendente (per id o nome).
**Logica codice**: risolve dipendente per ObjectId poi per `id`; query `archivio_bonifici` con `$or` su (operazione_salario_id+dipendente_id) o regex sul beneficiario; sort desc, max 100.
**Note**: se il dipendente non ha nome il `$or` contiene `{}` → matcha TUTTI i documenti; solo collezione legacy.

### POST /api/archivio-bonifici/jobs/import — crea job per ImportUnificato (bonifici_import_unificato.py)
**Cosa fa**: crea un job di import bonifici e restituisce `job_id`; la UI deve poi chiamare `POST /jobs/{job_id}/upload`.
**Logica codice**: chiama `create_job()` di bonifici_module.jobs e risponde `{success, message, job_id}`. Nessun file accettato.
**Note**: il docstring dichiara "crea job + carica file + restituisce conteggi" — FALSO: esegue solo il passo 1.

### Anomalie (gruppo bonifici)
1. Doppia collezione bonifici: `bonifici_transfers` (moderna) vs `archivio_bonifici` (legacy). In associazioni.py solo associa/disassocia-fattura gestiscono entrambe; gli altri 6 endpoint operano SOLO sulla legacy e non funzionano sui bonifici importati dalla pipeline corrente.
2. Tre schemi di associazione incompatibili: jobs/transfers (`fattura_associata`+`fattura_id`, `salario_associato`+`operazione_salario_id`) vs associazioni.py (`fattura_associata_id`+`fattura_collection`+`stato_riconciliazione`); campi importo per il match diversi tra i moduli.
3. Costanti collezioni in common.py mai usate; task riconciliazione in dict in memoria (volatile).
4. Dedup debole per i PDF parsati dal testo (chiave ridotta a importo+causale).
5. Bug `_auto_associate_bonifici`: la stessa fattura può essere associata a più bonifici (flag scritto ≠ flag verificato).
6. Docstring mendaci (import unificato, fatture-compatibili, bulk delete); GET /pdf con side-effect di scrittura; riconciliazione O(n·m) in memoria fino a 10k×50k; PDF Base64 nei documenti Mongo (limite 16MB/doc).

# Endpoint — Banca e Riconciliazione (area 04)

<!-- gestionalecloud-doc
status: reference
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!IMPORTANT]
> Documento di riferimento del dominio. La specifica normativa unica è `PROMPT_MASTER.md`; questo file non può contraddirla.

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
8. ~~Due event bus diversi per lo stesso dominio~~ — **RISOLTO (lug 2026)**: bus unico in `app.services.event_bus`, il bus core è stato rimosso e i suoi handler migrati.

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

---

## operazioni_module/ (/api/operazioni-da-confermare)

Package router: rotte dichiarate in `__init__.py` via `add_api_route`, handler in `smart.py` (riconciliazione banca) e `carta.py` (carta + supervisione). Helper in `common.py`: `QUERY_FATTURA_NON_PAGATA` = filtro canonico fattura non pagata (`pagato != True` AND `stato_pagamento` non in ["pagata","paid"]) — il commento documenta che in passato il modulo usava un campo proprio `pagata` mai letto altrove, causando riconciliazioni "invisibili"; `set_fattura_pagata(extra)` restituisce i campi canonici da scrivere su `invoices` al saldo (`pagato=True, paid=True, stato_pagamento="pagata", status="pagata", data_pagamento=oggi` + extra). 13 endpoint.

### GET /api/operazioni-da-confermare/smart/banca-veloce — panoramica tab Banca
**Cosa fa**: in una chiamata restituisce movimenti banca non riconciliati, assegni pendenti, fatture da pagare e statistiche.
**Logica codice**: legge `estratto_conto_movimenti` (riconciliato != True se richiesto, limit 50), `assegni` (non incassati/annullati, non confermati), `invoices` (QUERY_FATTURA_NON_PAGATA + metodo non nullo/contanti); due count per le stats. Sola lettura.

### GET /api/operazioni-da-confermare/smart/analizza — analisi batch con suggerimenti
**Cosa fa**: analizza fino a `limit` movimenti EC producendo suggerimenti di riconciliazione.
**Logica codice**: delega a `riconciliazione_smart.analizza_estratto_conto_batch(limit, solo_non_riconciliati)`.

### GET /api/operazioni-da-confermare/smart/movimento/{movimento_id} — analisi singolo movimento
**Cosa fa**: analizza un movimento e ne restituisce i suggerimenti.
**Logica codice**: delega a `analizza_singolo_movimento`; qualsiasi eccezione → 500 (anche il "non trovato").

### POST /api/operazioni-da-confermare/smart/riconcilia-auto — riconciliazione automatica banca
**Cosa fa**: abbina i movimenti non riconciliati a fatture (importo ±1%) o F24 (descrizione "I24").
**Logica codice**: per ogni movimento cerca in `invoices` (QUERY_FATTURA_NON_PAGATA + total_amount/importo_totale ±1%) — se match aggiorna movimento (`riconciliato`, `fattura_id`, `tipo_riconciliazione="auto_importo"`) e fattura con `set_fattura_pagata({movimento_bancario_id})`. Altrimenti se "I24" in descrizione cerca in `f24_commercialista` per importo ±1% e marca solo il movimento.
**Note**: match per solo importo senza controllo fornitore/data/segno → rischio falsi positivi; l'F24 non viene marcato riconciliato nella sua collezione; NON emette `FATTURA_PAGATA` (a differenza della manuale) → scadenziario non chiuso.

### POST /api/operazioni-da-confermare/smart/riconcilia-manuale — riconciliazione manuale movimento
**Cosa fa**: collega manualmente un movimento banca a fattura, stipendio o F24.
**Logica codice**: valida movimento (404); body `RiconciliaManuale`. Se fattura: valida esistenza (404), scrive `set_fattura_pagata` ed emette `FATTURA_PAGATA` via event bus (chiude lo scadenziario). Se stipendio/f24: salva solo `stipendio_id`/`f24_id`. Marca il movimento `riconciliato=True, tipo_riconciliazione="manuale"`.

### GET /api/operazioni-da-confermare/smart/cerca-fatture — ricerca fatture per associazione
**Cosa fa**: cerca fatture non pagate per importo (±5%) e/o fornitore.
**Logica codice**: parte da QUERY_FATTURA_NON_PAGATA; importo → `$or` su total_amount/importo_totale; fornitore → regex appesa allo STESSO `$or`.
**Note**: bug logico: importo e fornitore finiscono nello stesso `$or` → col fornitore passato il filtro importo è bypassato; parametro `data` accettato ma ignorato.

### GET /api/operazioni-da-confermare/smart/cerca-stipendi — ricerca stipendi
**Cosa fa**: cerca stipendi non riconciliati per importo (±5%) e/o nome dipendente.
**Logica codice**: `prima_nota_salari` con riconciliato != True, range su importo, regex su nome.

### GET /api/operazioni-da-confermare/smart/cerca-f24 — ricerca F24
**Cosa fa**: cerca F24 non riconciliati per importo (±5%) e/o mese di scadenza.
**Logica codice**: `f24_commercialista` con riconciliato != True, range su importo_totale, `data_scadenza` regex `^YYYY-MM`.

### POST /api/operazioni-da-confermare/smart/ignora — ignora movimento
**Cosa fa**: marca un movimento come da non processare (`ignorato=True`).
**Logica codice**: handler in `__init__.py`; richiede `movimento_id` (400); aggiorna sia `estratto_conto_movimenti` sia la legacy `bank_movements`; 404 se nessuna matcha.
**Note**: conferma l'esistenza della collezione legacy `bank_movements` parallela alla canonica.

### GET /api/operazioni-da-confermare/carta/lista — lista transazioni carta
**Cosa fa**: elenca le transazioni carta filtrabili per stato riconciliazione.
**Logica codice**: `transazioni_carta`, sort data desc, limit 100.

### POST /api/operazioni-da-confermare/carta/riconcilia-auto — riconciliazione automatica carta
**Cosa fa**: abbina le transazioni carta non riconciliate a fatture non pagate per importo (±2%).
**Logica codice**: fino a 1000 `transazioni_carta`; a match aggiorna transazione e fattura con `set_fattura_pagata({transazione_carta_id})`.
**Note**: match per solo importo, nessun evento FATTURA_PAGATA.

### POST /api/operazioni-da-confermare/carta/riconcilia-manuale — riconciliazione manuale carta
**Cosa fa**: collega manualmente una transazione carta a un'entità (di fatto solo fattura).
**Logica codice**: valida transazione (404); se tipo=="fattura" scrive `set_fattura_pagata` su `invoices` SENZA verificare che la fattura esista; marca la transazione riconciliata.
**Note**: manca la validazione fattura e l'evento FATTURA_PAGATA (presenti nell'omologo banca).

### POST /api/operazioni-da-confermare/supervisione/esegui — health-check contabile
**Cosa fa**: esegue 4 controlli e restituisce stato ok/warning.
**Logica codice**: count su `invoices` (non pagate, soglia 50), `estratto_conto_movimenti` (non riconciliati, 100), `assegni` (pendenti, 20), `fornitori` (senza metodo, 10).
**Note**: nonostante POST e nome, è un report di sola lettura: non "esegue" azioni correttive.

---

## riconciliazione_intelligente_api.py (/api/riconciliazione-intelligente)

Sistema di riconciliazione basato sul campo `stato_riconciliazione` di `invoices` (enum `StatoRiconciliazione`) e sul service `app/services/riconciliazione_intelligente.py`, che scrive anche `prima_nota_cassa`/`prima_nota_banca`, `scadenziario_fornitori`, `assegni`, `abbuoni_arrotondamenti`, `pagamenti_anticipati` e collega i movimenti in `estratto_conto_movimenti`. Il docstring in testa al file elenca 7 endpoint: in realtà sono 25.

### GET /api/riconciliazione-intelligente/dashboard — dashboard operazioni da verificare
**Cosa fa**: conteggi per ogni stato di riconciliazione + 5 liste (in attesa conferma, spostamenti proposti, match incerti, sospese, anomalie), max 50 ciascuna.
**Logica codice**: un count per ogni valore di `StatoRiconciliazione`; 5 find con normalizzazione campi standard/legacy (numero_documento|invoice_number, data_documento|invoice_date, importo_totale|total_amount, fornitore|supplier_name); `get_ultima_data_estratto()` legge l'ultimo movimento EC.
**Note**: blocco di normalizzazione copia-incollato 5 volte; N+1 count.

### POST /api/riconciliazione-intelligente/conferma-pagamento — conferma metodo pagamento
**Cosa fa**: conferma che una fattura è pagata in cassa o banca, creando il movimento di prima nota.
**Logica codice**: valida fattura_id e metodo ∈ {cassa,banca} (400); `service.conferma_pagamento`: cassa → insert `prima_nota_cassa`; banca → cerca match in `estratto_conto_movimenti` (esatto/parziale), può sospendere in attesa estratto o segnalare anomalia; aggiorna `invoices`, `scadenziario_fornitori` e collega il movimento.

### POST /api/riconciliazione-intelligente/conferma-multipla — conferma batch
**Cosa fa**: come sopra per una lista di fatture, con report per-item.
**Logica codice**: loop su `conferma_pagamento`; eccezioni per item conteggiate in `errori`; risponde sempre success complessivo.

### POST /api/riconciliazione-intelligente/applica-spostamento — spostamento Cassa→Banca
**Cosa fa**: accetta/rifiuta la proposta di spostare un pagamento da cassa a banca (match trovato in estratto).
**Logica codice**: se conferma richiede `movimento_estratto_id` (400); `service.applica_spostamento`: elimina da `prima_nota_cassa`, inserisce in `prima_nota_banca`, aggiorna `invoices` e movimento EC; rifiuto → mantiene cassa (lock).

### POST /api/riconciliazione-intelligente/rianalizza — ri-analisi post-upload estratto
**Cosa fa**: rielabora le fatture sospese/anomale dopo il caricamento di un nuovo estratto conto.
**Logica codice**: `service.rianalizza_operazioni_sospese()` (fino a 500 fatture): ricerca match EC e riclassifica.

### GET /api/riconciliazione-intelligente/fatture-da-confermare — lista in attesa conferma
**Cosa fa**: fatture con stato `in_attesa_conferma`, filtro anno opzionale.
**Logica codice**: find su `invoices` escludendo xml_content/linee; anno via regex su `data_documento` (limit 1-500).
**Note**: il filtro anno non copre il campo legacy `invoice_date`; duplica parte di /dashboard.

### GET /api/riconciliazione-intelligente/spostamenti-proposti — lista spostamenti proposti
**Cosa fa**: fatture in stato `da_verificare_spostamento` (max 100). **Note**: duplicato ridotto di /dashboard.

### GET /api/riconciliazione-intelligente/anomalie — lista anomalie
**Cosa fa**: fatture in stato `anomalia_non_in_estratto` (pagamento banca dichiarato ma non in estratto), max 100.

### GET /api/riconciliazione-intelligente/stato-estratto — copertura estratto conto
**Cosa fa**: ultima data estratto, totale movimenti, non riconciliati, distribuzione per anno.
**Logica codice**: aggregate `$group` per anno su `estratto_conto_movimenti`; "non riconciliati" = `fattura_id: {$exists: False}`.
**Note**: criterio diverso da operazioni_module (`riconciliato != True`): un movimento riconciliato a F24/stipendio qui risulta ancora non riconciliato → contatori incoerenti tra le due dashboard.

### POST /api/riconciliazione-intelligente/lock-manuale — blocco fattura
**Cosa fa**: blocca una fattura escludendola dalle verifiche automatiche.
**Logica codice**: update su `invoices` (stato `lock_manuale`, motivo, timestamp); modified_count==0 → 404.

### POST /api/riconciliazione-intelligente/sblocca — sblocco fattura
**Cosa fa**: rimuove il lock e ripristina lo stato in base al metodo confermato.
**Logica codice**: legge la fattura (404); nuovo stato = confermata_cassa/banca se `metodo_pagamento_confermato` presente, altrimenti in_attesa_conferma; `$set`+`$unset`.

### GET /api/riconciliazione-intelligente/statistiche — statistiche riconciliazione
**Cosa fa**: conteggi per stato, totale fatture, fatture legacy senza stato, importi per stato.
**Logica codice**: loop count per stato; legacy = totale − somma stati; aggregate `$group` su stato sommando `importo_totale`.
**Note**: la somma importi ignora il campo legacy `total_amount` → sottostima; duplica il loop di /dashboard.

### POST /api/riconciliazione-intelligente/migra-fatture-legacy — migrazione fatture esistenti
**Cosa fa**: assegna `stato_riconciliazione` alle fatture che non lo hanno, deducendolo dai campi storici.
**Logica codice**: find con `stato_riconciliazione: {$exists: False}` (limit default 500); regole: riconciliato→riconciliata; pagato+prima_nota_cassa_id→confermata_cassa; pagato+prima_nota_banca_id→confermata_banca; pagato senza riferimenti → cassa se metodo contanti altrimenti banca; else in_attesa_conferma.
**Note**: il campo `dettagli` del risultato è inizializzato ma mai popolato.

### POST /api/riconciliazione-intelligente/imposta-stato-fattura — override manuale stato
**Cosa fa**: imposta arbitrariamente lo `stato_riconciliazione` di una fattura.
**Logica codice**: valida stato contro l'enum (400); update; modified_count==0 → 404.
**Note**: il 404 scatta anche se la fattura esiste ma ha già quello stato.

### POST /api/riconciliazione-intelligente/pagamento-parziale — pagamento parziale (caso 19)
**Cosa fa**: registra un acconto tracciando il residuo.
**Logica codice**: valida fattura_id/importo/metodo; `service.registra_pagamento_parziale`: insert `prima_nota_{metodo}` + update `invoices` (pagato/residuo/stato parziale).

### POST /api/riconciliazione-intelligente/applica-nota-credito — nota di credito (caso 21)
**Cosa fa**: applica una NC (esistente o inserita a mano) riducendo il dovuto.
**Logica codice**: `service.applica_nota_credito(fattura_id, nota_credito_id | importo_nc+numero_nc)`; success=False → 400.

### POST /api/riconciliazione-intelligente/cerca-bonifico-cumulativo — ricerca combinazioni fatture (caso 23)
**Cosa fa**: dato un movimento, propone combinazioni di fatture stesso fornitore la cui somma corrisponde all'importo.
**Logica codice**: `service.cerca_bonifico_cumulativo(importo, data, descrizione)`: subset-sum su `invoices` non riconciliate. Sola lettura.

### POST /api/riconciliazione-intelligente/riconcilia-bonifico-cumulativo — 1 movimento ↔ N fatture
**Cosa fa**: riconcilia un movimento EC con più fatture insieme.
**Logica codice**: valida movimento_id e fatture_ids (400); il service inserisce in `prima_nota_banca` per ogni fattura, aggiorna `invoices` e marca il movimento.

### POST /api/riconciliazione-intelligente/pagamento-con-sconto — sconto cassa (caso 31)
**Cosa fa**: salda una fattura pagando meno del totale, registrando la differenza come sconto.
**Logica codice**: `service.registra_pagamento_con_sconto`: insert prima nota, calcolo percentuale, chiusura fattura.

### POST /api/riconciliazione-intelligente/assegni-multipli — assegni multipli (caso 36)
**Cosa fa**: salda una fattura con più assegni registrati singolarmente.
**Logica codice**: valida lista assegni con importo per ciascuno (400); il service inserisce ogni assegno in `assegni`, un movimento in `prima_nota_{metodo}` (default banca), aggiorna `invoices`.

### POST /api/riconciliazione-intelligente/riconcilia-con-arrotondamento — tolleranza arrotondamenti (caso 37)
**Cosa fa**: riconcilia anche con differenza di pochi centesimi/euro, registrando l'abbuono.
**Logica codice**: `service.riconcilia_con_arrotondamento` (tolleranza default €1, max €5): prima nota + `abbuoni_arrotondamenti` + chiusura fattura.

### POST /api/riconciliazione-intelligente/pagamento-anticipato — acconto senza fattura (caso 38)
**Cosa fa**: registra un pagamento a fornitore prima dell'arrivo della fattura.
**Logica codice**: valida importo>0 e metodo (400); insert in `pagamenti_anticipati` + movimento prima nota.

### GET /api/riconciliazione-intelligente/pagamenti-anticipati — lista anticipi in attesa
**Cosa fa**: anticipi non ancora collegati a fatture. **Logica codice**: `service.get_pagamenti_anticipati_in_attesa()`.

### POST /api/riconciliazione-intelligente/cerca-pagamenti-anticipati — match anticipi ↔ fattura
**Cosa fa**: dato l'id fattura, propone gli anticipi compatibili (fornitore/importo). Sola lettura.

### POST /api/riconciliazione-intelligente/collega-pagamento-anticipato — collega anticipo a fattura
**Cosa fa**: imputa un anticipo (tutto o in parte) a una fattura.
**Logica codice**: valida i due id (400); il service aggiorna il residuo su `pagamenti_anticipati` e i campi pagamento su `invoices`.

### Anomalie (gruppo operazioni / riconciliazione intelligente)
1. Due sistemi di riconciliazione paralleli non comunicanti: operazioni_module marca `riconciliato`/`pagato`, riconciliazione_intelligente governa `stato_riconciliazione` + prima nota. Una fattura saldata da un flusso resta "da confermare" per l'altro.
2. Definizioni divergenti di "movimento non riconciliato" (`riconciliato != True` vs `fattura_id $exists false`) → contatori incoerenti.
3. Evento FATTURA_PAGATA emesso solo da riconcilia-manuale banca: le riconciliazioni auto banca e auto/manuale carta chiudono la fattura senza propagare → scadenziario non chiuso.
4. Match automatici per solo importo (banca ±1%, carta ±2%) senza fornitore/data/segno; F24 abbinato mai marcato riconciliato in `f24_commercialista`.
5. Bug filtro in cerca-fatture (importo bypassato col fornitore); riconcilia-carta-manuale non valida l'esistenza della fattura.
6. Docstring bugiardi: header del file (7 endpoint su 25), supervisione "esegue" ma è read-only, `dettagli` di migra-fatture-legacy sempre vuoto.
7. Gestione campi legacy incompleta: filtro anno solo su `data_documento`, statistiche solo su `importo_totale`.
8. `/smart/ignora` scrive anche su `bank_movements` (migrazione non completata); 404 fuorvianti su modified_count==0.

---

## riconciliazione_stats_api.py (/api/riconciliazione — 1 endpoint)

Micro-router (prefix interno `/riconciliazione`, registrato con `/api`). Legge `riconciliazioni_match` (match del "sistema relazionale", collezione diversa da quelle della riconciliazione automatica).

### GET /api/riconciliazione/stats — statistiche match per stato
**Cosa fa**: conteggio e totale importi dei match di riconciliazione raggruppati per stato.
**Logica codice**: aggregate su `riconciliazioni_match` con `$group` per `stato` (count + somma `importo_riconciliato`), sort per count desc; scarta stati nulli; risponde `{stato: {count, totale}}`.
**Note**: nessun filtro/paginazione; nessun handling errori.

---

## email_reconciliation.py (/api/riconciliazione — 8 endpoint)

Riconciliazione email ↔ documenti gestionale: indice master (`indice_documenti`), scansione IMAP con associazione PDF, statistiche, download PDF. Router con prefix interno hardcoded `/api/riconciliazione`, registrato SENZA prefix. Logica delegata a `app/services/email_reconciliation.py`.

### POST /api/riconciliazione/costruisci-indice — costruzione indice documenti
**Cosa fa**: costruisce/aggiorna l'indice master dei documenti (fatture, verbali, contratti, costi noleggio, F24) con chiavi di ricerca per il matching.
**Logica codice**: delega a `costruisci_indice_documenti()`; scrive `indice_documenti`.
**Note**: `db_collections.py` marca `indice_documenti` come DEPRECATA (dati migrati in `invoices`), ma questo router la usa ancora attivamente.

### POST /api/riconciliazione/scansiona-posta — scansione posta e riconciliazione
**Cosa fa**: scansiona tutte le cartelle email (max `limit_per_cartella`, default 50) e associa i PDF trovati ai documenti dell'indice.
**Logica codice**: ricostruisce SEMPRE l'indice, poi `scansiona_tutta_posta_e_riconcilia(limit)`; scrive `indice_documenti`, `pdf_archive` e log match.
**Note**: operazione sincrona lunga (il docstring avvisa "diversi minuti"): rischio timeout HTTP, nessun job in background.

### GET /api/riconciliazione/statistiche — statistiche indice
**Cosa fa**: statistiche su indice e riconciliazioni. **Logica codice**: delega a `get_statistiche_indice()`.

### GET /api/riconciliazione/cerca — test matching su testo
**Cosa fa**: cerca match tra un testo libero e l'indice (per testare il matching).
**Logica codice**: `cerca_match_in_indice(testo)`; testo troncato a 200 char in risposta.

### GET /api/riconciliazione/documenti-senza-pdf — documenti senza allegati
**Cosa fa**: elenca documenti dell'indice privi di PDF, filtrabili per tipo.
**Logica codice**: find su `indice_documenti` con `$or` su `pdf_associati` (inesistente/vuoto/None) + count.

### GET /api/riconciliazione/pdf/{hash_pdf} — download PDF archiviato
**Cosa fa**: restituisce inline un PDF archiviato per hash.
**Logica codice**: find_one su `pdf_archive` per `hash`; decodifica `content_base64`; 404 se assente.
**Note**: PDF base64 in Mongo (non GridFS): limite 16MB/documento.

### GET /api/riconciliazione/log-riconciliazioni — log scansioni
**Cosa fa**: log delle riconciliazioni (default ultime 50), opz. solo con match.
**Logica codice**: find sul log ordinato per timestamp desc; filtro `matches_trovati > 0` se richiesto.

### DELETE /api/riconciliazione/reset-indice — reset indice
**Cosa fa**: svuota completamente l'indice documenti.
**Logica codice**: `delete_many({})` su `indice_documenti`.
**Note**: distruttivo, senza conferma né autorizzazione specifica.

---

## accounting/riconciliazione_automatica.py (/api/riconciliazione-auto — 7 endpoint)

Motore di riconciliazione automatica tra `estratto_conto_movimenti` e fatture/F24/POS/versamenti. Regola cardine: metodo "Bonifico"/"Assegno" valido solo con riscontro in estratto conto. Scoring multi-criterio (importo ±0,05€, fuzzy fornitore via rapidfuzz opzionale, numero fattura, plausibilità date); helper `_applica_pagamento_banca` (update `invoices` + prima nota banca + evento FATTURA_PAGATA). Richiamato anche dallo scheduler e dall'import estratto conto.

### POST /api/riconciliazione-auto/riconcilia-estratto-conto — riconciliazione automatica completa
**Cosa fa**: analizza fino a 5000 movimenti EC non riconciliati e li matcha con fatture, F24, POS e versamenti; i casi ambigui vanno in `operazioni_da_confermare`.
**Logica codice**: legge `estratto_conto_movimenti` e la mappa metodi da `fornitori` (per P.IVA). Per movimento: (a) ignora commissioni (keyword o importi ≤3€ noti); (b) uscite → candidate `invoices` non pagate per importo esatto/parziale con score: importo (+10/+5/+2), fornitore in descrizione (+5/+3 fuzzy), numero fattura (+5), scadenza vicina (+2), penalità −5 per date implausibili, skip se fornitore paga in contanti e score<15. Score ≥15 → match; 10-14 con candidata unica → match; multiple → dubbio. Applica `_applica_pagamento_banca` e upsert su `assegni` se estratto un numero assegno; (c) uscite "F24" → match importo su `f24_unificato` + evento F24_PAGATO; (d) entrate POS → match su `prima_nota_cassa` categoria POS con logica giorni (lunedì → somma weekend Ven-Dom ±1€); (e) entrate versamenti → `prima_nota_cassa` categoria Versamento stessa data ±0,05€. Marca il movimento EC con `tipo_riconciliazione` e dettagli.
**Note**: nel ramo F24 il match è `find_one` per solo importo senza vincolo data (rischio falso positivo su importi ricorrenti); i commenti documentano bug storici corretti (alias suppliers vuoto, proiezione senza `_id` che faceva fallire gli update).

### GET /api/riconciliazione-auto/stats-riconciliazione — statistiche
**Cosa fa**: contatori sintetici. **Logica codice**: count su `estratto_conto_movimenti` (totali/riconciliati/automatici), `operazioni_da_confermare` (da_confermare), `invoices` (riconciliato_automaticamente, in_banca).

### DELETE /api/riconciliazione-auto/reset-riconciliazione — reset completo
**Cosa fa**: azzera la riconciliazione automatica.
**Logica codice**: `delete_many` su `operazioni_da_confermare`; `$unset` dei flag su TUTTI i movimenti EC; `$unset` di `riconciliato_con_ec`/`riconciliato_automaticamente` sulle fatture auto-riconciliate.
**Note**: NON resetta `pagato`/`in_banca`/prima nota sulle fatture né i flag su cassa/assegni/F24: le fatture restano "pagate" senza più il collegamento EC.

### POST /api/riconciliazione-auto/conferma-operazione/{operazione_id} — conferma/rifiuto dubbio
**Cosa fa**: risolve un'operazione dubbia: conferma un match fattura o la rifiuta/ignora.
**Logica codice**: legge `operazioni_da_confermare` (404); su conferma applica `_applica_pagamento_banca` con metodo "Bonifico" fisso, marca il movimento EC `riconciliato_manualmente` e l'operazione confermata.
**Note**: forza sempre "Bonifico" anche per assegni; `fattura_id` e `azione` come query param su un POST.

### GET /api/riconciliazione-auto/operazioni-dubbi — lista dubbi
**Cosa fa**: operazioni in stato `da_confermare` con limit/offset. **Logica codice**: find + count su `operazioni_da_confermare`.

### POST /api/riconciliazione-auto/correggi-metodi-pagamento — bonifica metodi errati
**Cosa fa**: corregge le fatture marcate Bonifico/Banca/Sepa/Assegno senza riscontro banca (`in_banca != true`): le riporta a non pagate applicando il metodo del fornitore.
**Logica codice**: due find regex su `invoices` con proiezione `{"_id": 0}`; per ciascuna lookup metodo in `fornitori`; `$set` pagato/paid=false, status="imported", `bonifica_motivo`; `$unset` flag riconciliazione e/o `metodo_pagamento`.
**Note**: BUG VERIFICATO: le fatture sono lette con `{"_id": 0}` ma l'update filtra per `{"_id": fattura["_id"]}` → KeyError alla prima iterazione: la bonifica non corregge nulla. Lo stesso bug è stato corretto altrove nel file (commento a riga ~415) ma non qui.

### GET /api/riconciliazione-auto/stato-riconciliazione-aruba — stato fatture
**Cosa fa**: riepilogo fatture per metodo/stato pagamento + data ultimo estratto conto.
**Logica codice**: find_one ultimo movimento EC; aggregate su `invoices` per (metodo, pagato, stato_riconciliazione) classificato in pagate/sospese/bonifico/assegno/cassa/da_confermare.
**Note**: "Aruba" nel nome è fuorviante: opera su tutte le fatture.

---

## paypal_statements.py (/api/paypal-statements — 12 endpoint)

Estratti conto PayPal MSR/CSR: import PDF (`paypal_msr_parser`), consultazione (`paypal_transactions`, `paypal_statements`), riconciliazione con `estratto_conto_movimenti`, associazione fatture e ricerca Gmail. In `paypal_transactions` il campo `paypal_account_id` è la CONTROPARTE; l'`invoice_id` PayPal NON è univoco per addebito (il dedup usa `transaction_id`). Helper: `_backfill_controparte` (propaga nome/email tra transazioni con stesso account), `_auto_riconcilia` (match importo+data ±3gg), `_save_parsed_statement` (dedup per transaction_id). `auto-associa` e `auto-cerca-gmail` sono invocati anche dallo scheduler.

### GET /api/paypal-statements/statements — lista estratti conto
**Cosa fa**: statements importati, filtro anno, max 500. **Logica codice**: find su `paypal_statements` sort periodo desc.

### GET /api/paypal-statements/transactions — lista transazioni
**Cosa fa**: transazioni con filtri anno/mese/tipo/solo_pagamenti (lordo<0) e totali.
**Logica codice**: find su `paypal_transactions` (data via regex YYYY-MM); `_backfill_controparte`; sintetizza `descrizione` da subject/note/invoice_id per le transazioni da API.
**Note**: il backfill agisce solo in memoria sulla pagina restituita (non persiste).

### GET /api/paypal-statements/dashboard — dashboard riepilogativa
**Cosa fa**: KPI: n. statements/transazioni, totale speso, top-10 fornitori, spesa per tipo, contatori riconciliazione banca.
**Logica codice**: count + pagamenti (lordo<0, max 2000) con backfill; aggregazioni in Python; conta `riconciliato_banca: true` e movimenti EC con "paypal" in descrizione.

### POST /api/paypal-statements/import-pdf — import singolo PDF
**Cosa fa**: importa un PDF MSR/CSR, salva statement+transazioni e riconcilia subito con la banca.
**Logica codice**: valida .pdf, salva in `/tmp/uploads/msr_statements` (basename anti path-traversal); `parse_paypal_msr` (422 se fallisce); `_save_parsed_statement` (upsert statement per periodo, insert transazioni dedup per transaction_id); `_auto_riconcilia`.

### POST /api/paypal-statements/import-all-local — import massivo cartella locale
**Cosa fa**: importa tutti i PDF in `/tmp/uploads/msr_statements` e riconcilia.
**Logica codice**: loop parse+save per file, errori raccolti; `_auto_riconcilia` finale.

### POST /api/paypal-statements/riconcilia-banca — riconciliazione manuale banca
**Cosa fa**: rilancia la riconciliazione PayPal ↔ estratto conto.
**Logica codice**: `_auto_riconcilia`: pagamenti non riconciliati (lordo<0) × movimenti EC con "paypal" in descrizione; matching greedy per importo (±0,02€) e data più vicina entro 3 giorni, ogni movimento usato una volta; setta `riconciliato_banca`, `movimento_banca_id`, `data_banca`.
**Note**: l'update filtra per `transaction_id`: transazioni senza transaction_id matchano `{"transaction_id": ""}` → update sul documento sbagliato/nessuno.

### GET /api/paypal-statements/report — report spese per fornitore/mese
**Cosa fa**: report pagamenti raggruppato per controparte e mese con dettaglio.
**Logica codice**: find pagamenti (max 5000); raggruppamento in Python per `nome_controparte` (fallback descrizione) e YYYY-MM.
**Note**: non usa il backfill → transazioni senza payer_name frammentano i totali per fornitore rispetto alla dashboard.

### GET /api/paypal-statements/transazione/{transaction_id}/dettaglio — dettaglio per modale
**Cosa fa**: vista a 360°: verbale collegato, dipendente, trattenuta busta paga, mapping fornitore, fatture candidate, flag riconciliazione unificato.
**Logica codice**: lookup per transaction_id (fallback id, 404); `verbali_noleggio` per paypal_transaction_id; `employees` per driver_id; `trattenute_dipendenti` per verbale_id; `paypal_mapping_fornitori` per paypal_account_id. Fatture a cascata: (A) P.IVA del mapping, (B) parole significative del nome controparte, (C) email, (D) solo importo ±0,05€ (marcate `match: "importo"`). Unifica in lettura i flag `riconciliato_banca`/`riconciliato_con_estratto_banca`.
**Note**: doppio sistema di mapping fornitore: qui `paypal_mapping_fornitori`, in paypal_api.py il campo `fornitori.paypal_account_id` — non comunicano.

### GET /api/paypal-statements/transazione/{transaction_id}/cerca-gmail — ricerca email fattura
**Cosa fa**: cerca su Gmail (IMAP) email compatibili con la transazione (fatture estere/SaaS fuori SDI).
**Logica codice**: credenziali via `get_gmail_credentials` (errore soft); `build_transaction_query` (importo+controparte+finestra date); `search_gmail_sync` in thread, max 10 risultati con link.

### POST /api/paypal-statements/transazione/{transaction_id}/associa — associazione manuale
**Cosa fa**: associa la transazione a una fattura (`{fattura_id}`) o a un'email (`{gmail}`).
**Logica codice**: valida transazione e fattura (404); scrive `fattura_associata` (snapshot + auto:false) o `gmail_associata`; 400 se body vuoto.

### POST /api/paypal-statements/auto-associa — associazione automatica fatture
**Cosa fa**: collega in batch i pagamenti senza `fattura_associata` alle fatture per importo esatto (±0,05€), preferendo il candidato con nome fornitore compatibile.
**Logica codice**: aggregate su `invoices` con importo coalescato (`$ifNull` total_amount/importo_totale); scelta per parole ≥4 lettere della controparte; candidato unico senza conferma nome → `match: "solo_importo"`; scrive `fattura_associata` con auto:true.
**Note**: più transazioni di pari importo possono agganciarsi alla stessa fattura (nessun consumo della candidata nel loop).

### POST /api/paypal-statements/auto-cerca-gmail — ricerca Gmail automatica batch
**Cosa fa**: per i pagamenti senza fattura né email, cerca su Gmail (max 12 per giro) e associa il miglior risultato.
**Logica codice**: filtro senza `fattura_associata`/`gmail_associata`/`gmail_cercato_at` (ogni tx cercata una sola volta); salva `gmail_candidati` (top 5) e `gmail_associata` = primo risultato con allegato; su errore IMAP interrompe il giro.

---

## paypal_api.py (/api/paypal-api — 9 endpoint)

Integrazione API REST PayPal: sync transazioni (service `paypal_api_sync`), riconciliazione unificata multe PagoPA/fatture/banca (service `paypal_riconciliazione`), ricevute PDF e mapping `paypal_account_id` → fornitore direttamente su `fornitori`.

### POST /api/paypal-api/sync — sync periodo arbitrario
**Cosa fa**: scarica/arricchisce da API PayPal le transazioni del periodo `{start_date, end_date}`.
**Logica codice**: parse ISO (400 se invalide); `sync_paypal_period(db, start, end)` scrive `paypal_transactions` con source `paypal_api`.

### POST /api/paypal-api/sync/month — sync mese corrente
**Cosa fa**: come /sync sul mese solare corrente calcolato server-side (`calendar.monthrange`).

### GET /api/paypal-api/status — stato sync
**Cosa fa**: transazioni totali, arricchite da API, PagoPA, timestamp ultimo sync.
**Logica codice**: count su `paypal_transactions` + find_one per `enriched_at` desc.

### POST /api/paypal-api/riconcilia — riconciliazione unificata
**Cosa fa**: processa i pagamenti in uscita in tre passi: multe PagoPA → `verbali_noleggio`, fatture → `invoices` (match per paypal_account_id), allineamento con `estratto_conto_movimenti`.
**Logica codice**: find su `paypal_transactions` (importo<0, filtro data opzionale); split per `is_pagopa`; `riconcilia_multe_pagopa`, `riconcilia_pagamenti_paypal`, `collega_a_estratto_conto`.
**Note**: terzo circuito di riconciliazione banca-PayPal indipendente da `_auto_riconcilia` (flag diversi: `riconciliato_con_estratto_banca` vs `riconciliato_banca`), unificati solo in lettura nel dettaglio transazione.

### GET /api/paypal-api/ricevuta-pdf/{transaction_id} — download ricevuta PDF
**Cosa fa**: restituisce (o genera al volo) la ricevuta PDF; per le PagoPA prova prima la ricevuta ufficiale.
**Logica codice**: lookup (404); usa `pdf_ricevuta_path`/`pdf_generato_path` se esistono; altrimenti `fetch_ricevuta_pagopa` poi `genera_pdf_transazione_paypal`; FileResponse.

### GET /api/paypal-api/account-ids-non-mappati — controparti da mappare
**Cosa fa**: elenca i `paypal_account_id` in uscita non mappati a fornitori, con aggregati e candidati suggeriti.
**Logica codice**: aggregate su `paypal_transactions` (importo<0) per account, `$sort` sul nome prima del `$group` così `$first` prende il nome quando presente; esclude account già in `fornitori.paypal_account_id` e i PagoPA. Candidati: match nome su `fornitori` (exact/partial/fuzzy ≥0.6) con fallback su fornitori con fatture di importo simile (±40% della media) via `invoices`+`fornitori`.
**Note**: raccoglie gli `invoice_id_fornitore` solo come indizio testuale (coerente con la non-univocità dell'invoice_id PayPal).

### POST /api/paypal-api/mappa-fornitore — mappa account su fornitore esistente
**Cosa fa**: scrive `paypal_account_id` su un fornitore.
**Logica codice**: 400 senza i due campi; 404 fornitore inesistente; 409 se l'account è già mappato ad ALTRO fornitore; update su `fornitori`.

### POST /api/paypal-api/smappa-fornitore — rimuove mapping
**Cosa fa**: `$unset paypal_account_id` dal fornitore. **Note**: nessun 404 se il fornitore non esiste (`modified: 0`).

### POST /api/paypal-api/crea-fornitore-e-mappa — crea fornitore e mappa
**Cosa fa**: crea un fornitore (tipico SaaS estero) già mappato all'account PayPal.
**Logica codice**: valida account e ragione_sociale (400); 409 se account già mappato o P.IVA esistente; insert in `fornitori` con default `metodo_pagamento: "paypal"`, `esclude_magazzino: true`, `source: "paypal_mapping"`; ritorna il conteggio transazioni ora collegabili.

### Anomalie (gruppo riconciliazione stats/auto + PayPal)
1. BUG verificato in `correggi-metodi-pagamento`: proiezione `{"_id": 0}` + update per `fattura["_id"]` → KeyError, la bonifica non modifica alcuna fattura.
2. Doppio sistema di mapping fornitore PayPal (`paypal_mapping_fornitori` vs `fornitori.paypal_account_id`), non sincronizzati.
3. Tre circuiti di riconciliazione banca↔PayPal paralleli con flag diversi, unificati solo in lettura.
4. Doppia associazione fattura↔pagamento PayPal (auto-associa per importo vs riconcilia per account) indipendenti; in auto-associa la stessa fattura può agganciarsi a più transazioni.
5. `/api/riconciliazione/stats` vs `/api/riconciliazione-auto/stats-riconciliazione`: due statistiche su sistemi diversi con nomi quasi identici.
6. Collezione `indice_documenti` deprecata ma interamente usata da email_reconciliation.py.
7. `reset-riconciliazione` asimmetrico: rimuove i collegamenti EC ma lascia fatture "pagate" senza riscontro.
8. `conferma-operazione` forza metodo "Bonifico" anche per assegni; match F24 per solo importo senza data; "aruba" nel nome senza filtro provenienza.

---

## bank/pos_accredito.py (/api/pos-accredito — 5 endpoint)

Calcolo dello sfasamento temporale degli accrediti POS (Lun-Gio → +1 giorno lavorativo, Ven/Sab/Dom → Lun/Mar, slittamento su festivi). Logica negli helper di `app/utils/pos_accredito.py`. Nessuna autenticazione.

### GET /api/pos-accredito/calcola-accredito — calcolo data accredito
**Cosa fa**: data una data di pagamento, restituisce la data di accredito POS attesa, i giorni di sfasamento e le note.
**Logica codice**: valida YYYY-MM-DD (400); `calcola_data_accredito_pos`; nessun DB.

### GET /api/pos-accredito/calendario-mensile/{anno}/{mese} — calendario sfasamento mensile
**Cosa fa**: per ogni giorno del mese, lo sfasamento POS previsto.
**Logica codice**: valida mese 1-12 (400); delega a `get_calendario_sfasamento_mese`. Nessun DB.

### GET /api/pos-accredito/festivi/{anno} — festivi dell'anno
**Cosa fa**: festivi italiani dell'anno (fissi + Pasqua/Pasquetta calcolate).
**Logica codice**: `get_festivi_anno` + `_get_nome_festivo` locale. Nessun DB.
**Note**: `timedelta` importato DOPO la funzione che lo usa (funziona solo perché l'import avviene al load del modulo); re-import duplicato di `handle_errors`.

### GET /api/pos-accredito/accrediti-attesi/{data_accredito} — pagamenti attesi in accredito
**Cosa fa**: elenca i corrispettivi elettronici che dovrebbero essere accreditati quel giorno, con totale atteso.
**Logica codice**: legge `corrispettivi` (data negli ultimi 10 giorni, `pagato_elettronico > 0`), poi filtra in memoria con `get_accrediti_attesi_per_data`. Sola lettura.

### GET /api/pos-accredito/riconciliazione-pos/{anno}/{mese} — report riconciliazione POS mensile
**Cosa fa**: confronta giorno per giorno i pagamenti elettronici (proiettati alla data di accredito attesa) con gli accrediti POS reali in banca; stato OK/ECCEDENZA/MANCANTE (tolleranza €1).
**Logica codice**: legge `corrispettivi` (mese) e `estratto_conto_movimenti` (mese +5 giorni, regex `POS|PDV|INCAS.*P\.O\.S` su descrizione/causale); raggruppa per data accredito calcolata; importo banca con fallback su `dare` in valore assoluto. Sola lettura.
**Note**: unico endpoint POS che usa la collezione canonica; matching banca per regex sulla descrizione (rischio falsi positivi — lo stesso tipo di problema corretto in pos_corrispettivi_check).

---

## pos_corrispettivi_check.py (/api/pos-corrispettivi — 8 endpoint)

Verifica coerenza tra corrispettivi XML, chiusure POS manuali e accrediti bancari. Due generazioni di logica: v1 (`verifica-coerenza`, dichiarata superata nei commenti ma attiva) e v2/v3 "a 2 fasi" (`controllo-due-fasi`, `alert-oggi`). ATTENZIONE: come fonte "banca" usa `prima_nota_banca`, NON la canonica `estratto_conto_movimenti`.

### GET /api/pos-corrispettivi/verifica-coerenza — coerenza POS/corrispettivi (v1)
**Cosa fa**: per ogni giorno del periodo confronta il `pagato_elettronico` dei corrispettivi con gli accrediti POS bancari; classifica ok / in_transito / mancante / extra / differenza (tolleranza 2% o €5).
**Logica codice**: legge `corrispettivi`, `prima_nota_banca` (solo entrate con categoria in whitelist di 6 categorie POS, escluso `source: import_manuale_pos` — fix del 22/04/2026 contro i falsi positivi regex) e `chiusure_pos_manuali` (fallback su prima_nota_banca `source: import_manuale_pos`); se esiste la chiusura manuale del giorno, quella è il riferimento invece dell'XML. Sola lettura.
**Note**: dichiarata SOSTITUITA da controllo-due-fasi ma senza marcatore deprecated; il calcolo Ven-Dom (`7 - weekday + 1`) fa atterrare il venerdì a MARTEDÌ (+4), incoerente con la v2 (Ven→Lun +3); `if 'dt' in dir()` sempre vero (codice morto); confronta l'accreditato del giorno D con l'incasso del giorno D senza shift effettivo.

### GET /api/pos-corrispettivi/riepilogo-mensile — riepilogo mensile per anno
**Cosa fa**: per i 12 mesi, totali corrispettivi/contanti/elettronico/POS accreditato e differenza con stato ok/warning/error (soglie €50/€200).
**Logica codice**: 12 iterazioni × 2 aggregate `$group` (su `corrispettivi` e `prima_nota_banca` con stessa whitelist categorie).
**Note**: 24 round-trip invece di un group per mese; whitelist duplicata copia-incolla.

### POST /api/pos-corrispettivi/riconcilia-pos-giorno — riconciliazione automatica di un giorno
**Cosa fa**: per una data cerca in banca un accredito POS compatibile (±5%) nelle 2 date di accredito possibili e marca il corrispettivo riconciliato.
**Logica codice**: `corrispettivi` find_one per data; date candidate (Lun-Gio: +1/+2; Ven-Dom: stesso bug della v1); cerca in `prima_nota_banca` per categoria POS o regex `POS|NEXI|SUMUP`; scrive `pos_riconciliato`, `pos_data_accredito`, `pos_importo_accredito` sul corrispettivo.
**Note**: reintroduce la regex sulla descrizione eliminata dal fix del 22/04; parametro in query su POST.

### GET /api/pos-corrispettivi/anomalie-gravi — anomalie sopra soglia
**Cosa fa**: filtra le anomalie di verifica-coerenza tenendo solo differenze ≥ soglia (default €100), con warning AdE.
**Logica codice**: chiama internamente `verifica_coerenza_pos_corrispettivi` e filtra in memoria.
**Note**: eredita tutti i limiti della v1.

### PUT /api/pos-corrispettivi/chiusura-giornaliera — upsert chiusura POS giornaliera
**Cosa fa**: crea/aggiorna la chiusura POS di un giorno (da app mobile) come movimento di entrata in prima nota banca, con audit trail.
**Logica codice**: autenticato; valida data e importo (400); cerca in `prima_nota_banca` per data con source in [corrispettivo_pos, chiusura_pos_mobile] o categoria "Corrispettivi POS": aggiorna (audit `importo_originale` alla prima modifica; no-op idempotente se identico) o inserisce con `source: chiusura_pos_mobile` e campi doppi it/en; audit best-effort in `pos_chiusure_audit`.
**Note**: la costante `COLLECTION_CHIUSURE_POS="chiusure_pos_manuali"` esiste, ma le chiusure vengono scritte in `prima_nota_banca`: dato gestionale mischiato ai movimenti banca, distinto solo dal `source`.

### GET /api/pos-corrispettivi/chiusura-giornaliera/audit — audit log chiusure
**Cosa fa**: audit log delle modifiche alle chiusure POS, filtro anno/data.
**Logica codice**: autenticato; legge `pos_chiusure_audit`, sort timestamp desc, limit ≤500.

### GET /api/pos-corrispettivi/controllo-due-fasi — controllo incassi a 2 fasi (v2/v3)
**Cosa fa**: per ogni giorno: Fase 0 (stato corrispettivo: provvisorio/definitivo_xml/manca_xml se >7gg), Fase 1 (POS serale manuale vs elettronico XML → alert compensazione errori di battitura RT), Fase 2 (accredito banca alla data attesa vs POS manuale, calendario corretto Ven→Lun +3).
**Logica codice**: legge `corrispettivi` (campi v2: stato, totale_manuale, totale_xml); `_carica_pos_manuale_per_data` unisce `chiusure_pos_manuali` e `prima_nota_banca` (source chiusure mobile, quest'ultima vince); `_carica_accrediti_banca_pos` legge `prima_nota_banca` (entrate, keyword POS/MONETICA/NEXI/PAGOBANCOMAT). Tolleranza default €0,50. Sola lettura.
**Note**: `_carica_pos_manuale_per_data` scandisce le fonti SENZA filtro data (tutto lo storico a ogni chiamata); la Fase 2 non somma Ven+Sab+Dom quando confluiscono nello stesso lunedì → falsi "extra"/"differenza".

### GET /api/pos-corrispettivi/alert-oggi — alert per la dashboard
**Cosa fa**: alert correnti: compensazioni da battere al RT, accrediti mancanti/difformi, XML mancanti.
**Logica codice**: chiama `controllo_incassi_due_fasi` sugli ultimi 30 giorni e ripartisce i giorni problematici in tre liste. Nessun DB diretto.

---

## multi_pagamento.py (/api/pagamenti — 6 endpoint)

Pagamenti multipli fattura: N pagamenti per fattura, un assegno su N fatture; stato fattura calcolato da `_ricalcola_stato_fattura` (non_pagata/parzialmente_pagata/pagata/eccedenza, tolleranza €0,05) che aggiorna `invoices` (`stato_pagamento`, `totale_pagato`, `residuo_da_pagare`, `num_pagamenti`). Nessuna autenticazione.

### GET /api/pagamenti/fattura/{fattura_id} — pagamenti di una fattura
**Cosa fa**: fattura, lista pagamenti, totale pagato, residuo, flag completamente pagata.
**Logica codice**: `invoices` (404) + `pagamenti` per fattura_id; somme in memoria.

### POST /api/pagamenti/registra — registra pagamento (anche parziale)
**Cosa fa**: registra un pagamento su una fattura, lo riporta in prima nota e ricalcola lo stato.
**Logica codice**: valida importo>0 (400) e fattura (404); insert in `pagamenti` (snapshot fornitore/numero); insert in `prima_nota_cassa` (contanti/cassa/carta) o `prima_nota_banca` (assegno/bonifico/sepa) come uscita, source `multi_pagamento`; link `prima_nota_id` sul pagamento; se assegno con numero, `$addToSet fatture_associate` su `assegni`; `_ricalcola_stato_fattura`.
**Note**: "carta" va in prima nota CASSA (scelta discutibile ma intenzionale); 4-5 scritture non atomiche.

### POST /api/pagamenti/assegno-multi-fatture — un assegno paga N fatture
**Cosa fa**: dichiara di registrare un pagamento assegno per ogni fattura della lista riusando /registra.
**Logica codice**: legge `assegni` per numero; per ogni fattura invoca `registra_pagamento(Body(**{...}))`.
**Note**: BUG BLOCCANTE: `Body(**dict)` passa i dati come kwargs alla factory `fastapi.Body` → TypeError a runtime (500 via handle_errors). L'endpoint non può funzionare come scritto.

### POST /api/pagamenti/fattura-multi-metodo — una fattura pagata con N metodi
**Cosa fa**: dichiara di registrare più pagamenti con metodi diversi sulla stessa fattura.
**Logica codice**: cicla su `pagamenti` e invoca `registra_pagamento(Body(**{...}))`.
**Note**: STESSO BUG BLOCCANTE del precedente: endpoint non funzionante a runtime.

### GET /api/pagamenti/riepilogo-fornitore/{piva} — riepilogo per fornitore
**Cosa fa**: fatture, pagamenti, totale fatturato/pagato e residuo per P.IVA.
**Logica codice**: `invoices` per supplier_vat (500) + `pagamenti` per fornitore_piva (1000); aggregati in memoria.

### DELETE /api/pagamenti/{pagamento_id} — elimina pagamento
**Cosa fa**: elimina un pagamento, la riga di prima nota collegata e ricalcola lo stato fattura.
**Logica codice**: `pagamenti` (404); delete della prima nota provando su ENTRAMBE `prima_nota_cassa` e `prima_nota_banca`; delete pagamento; `_ricalcola_stato_fattura`.
**Note**: route catch-all a livello di prefisso: qualsiasi DELETE su /api/pagamenti/<x> finisce qui.

---

## ocr_assegni.py (/api/ocr-assegni — 6 endpoint)

Registro OCR degli assegni + due endpoint di estrazione OCR che sono STUB non implementati. Tutti autenticati.

### GET /api/ocr-assegni/registro — lista registro OCR
**Cosa fa**: fino a 500 voci di `ocr_assegni`, più recenti prima.

### POST /api/ocr-assegni/registro — aggiungi voce
**Cosa fa**: inserisce una voce arbitraria (201). **Logica codice**: dict libero senza validazione + uuid + created_at.

### DELETE /api/ocr-assegni/registro/{entry_id} — elimina voce
**Cosa fa**: delete_one per id; risponde "Entry deleted" anche se l'id non esiste (nessun 404).

### DELETE /api/ocr-assegni/registro — svuota registro
**Cosa fa**: `delete_many({})` su `ocr_assegni`. **Note**: distruttivo totale, senza conferma.

### POST /api/ocr-assegni/estrai-dati — estrazione OCR (STUB)
**Cosa fa**: dichiara di estrarre dati da un'immagine assegno ma NON fa nulla: restituisce `{"message": "OCR extraction completed", "data": {}}` fisso; il file non viene letto.
**Note**: docstring e risposta mentono ("completed").

### POST /api/ocr-assegni/leggi-carnet — lettura carnet (STUB)
**Cosa fa**: dichiara di leggere le pagine di un carnet ma restituisce `{"checks": []}` fisso.

---

## cash.py (/api/cash — 8 endpoint reali, non 10)

Gestione cassa "strutturata": modelli Pydantic, layer service/repository (`CashService`, `CashMovementRepository`). Opera su `Collections.CASH_MOVEMENTS` = `prima_nota_cassa`. Tutti autenticati.

### GET /api/cash/movements — lista movimenti cassa
**Cosa fa**: movimenti con filtri data/tipo/categoria e paginazione, filtrati per `user_id` dell'utente corrente.
**Logica codice**: `CashService.list_movements` su `prima_nota_cassa`.

### POST /api/cash/movements — crea movimento
**Cosa fa**: crea un movimento validato (201). **Logica codice**: body `CashMovementCreate` (Pydantic); insert con user_id.

### PUT /api/cash/movements/{movement_id} — aggiorna movimento
**Cosa fa**: aggiorna i soli campi forniti. **Logica codice**: `CashMovementUpdate`; 404 dal service.

### DELETE /api/cash/movements/{movement_id} — elimina movimento
**Cosa fa**: delete per id; 404 dal service se non trovato.

### GET /api/cash/stats — statistiche cassa
**Cosa fa**: entrate/uscite/saldo/conteggio + breakdown per categoria e metodo nel periodo (date obbligatorie).
**Logica codice**: `service.get_cash_stats` (aggregazioni filtrate per user_id).

### POST /api/cash/corrispettivi — crea corrispettivo (chiusura giornaliera)
**Cosa fa**: dichiara di creare la chiusura giornaliera con controllo duplicati e saldo atteso/differenza.
**Logica codice**: `service.create_corrispettivo` → `corrispettivo_repo.find_by_date` + create.
**Note**: BUG BLOCCANTE: `get_cash_service` istanzia `CashService(movement_repo, None)` → `corrispettivo_repo` è None → AttributeError → 500. Endpoint non funzionante.

### GET /api/cash/corrispettivi/{target_date} — leggi corrispettivo per data
**Cosa fa**: dichiara di restituire il corrispettivo di una data.
**Note**: STESSO BUG BLOCCANTE (`corrispettivo_repo=None`): 500 a runtime.

### GET /api/cash/export/excel — export movimenti in Excel
**Cosa fa**: .xlsx dei movimenti nel periodo con saldo progressivo (501 se openpyxl assente).
**Logica codice**: BYPASSA il service: query diretta su `prima_nota_cassa` con campo `data` (italiano) `$gte/$lte`, max 10000; workbook + StreamingResponse.
**Note**: NON filtra per user_id (esporta i movimenti di tutti); usa `data` mentre cash_register.py usa `date` sulla stessa collezione — schema misto.

---

## cash_register.py (/api/cash-register — 9 endpoint)

Seconda interfaccia CRUD sulla STESSA collezione `prima_nota_cassa`, senza Pydantic, senza service, senza filtro utente, con campo data `date` (inglese) invece di `data`. Tutti autenticati.

### GET /api/cash-register/movements — lista movimenti
**Cosa fa**: fino a 500 movimenti, filtrabili per intervallo `date`.
**Note**: duplica GET /api/cash/movements senza filtro utente né paginazione, su campo data diverso.

### POST /api/cash-register/movements — crea movimento
**Cosa fa**: insert con body dict arbitrario (201) + id/user_id/created_at.
**Note**: duplicazione non validata di POST /api/cash/movements.

### PUT /api/cash-register/movements/{movement_id} — aggiorna movimento
**Cosa fa**: `$set` dei campi passati; risponde "Movement updated" anche con body vuoto o id inesistente.

### DELETE /api/cash-register/movements/{movement_id} — elimina movimento
**Cosa fa**: delete_one per id; nessun 404 se assente.

### DELETE /api/cash-register/movements — elimina movimenti in intervallo
**Cosa fa**: dichiara di eliminare i movimenti in un intervallo di date.
**Logica codice**: filtro `date` costruito SOLO se presenti ENTRAMBE start_date e end_date; poi `delete_many(query)`.
**Note**: RISCHIO GRAVE: se manca anche uno solo dei parametri (entrambi opzionali) la query resta `{}` → cancella TUTTA `prima_nota_cassa` senza conferma.

### GET /api/cash-register/stats-annulli — statistiche annulli
**Cosa fa**: dichiara statistiche sulle operazioni annullate ma restituisce solo il conteggio.
**Logica codice**: `count_documents({"status": "cancelled"})`; `total_cancelled_amount` hardcoded a 0, `by_month` sempre vuoto.
**Note**: implementazione placeholder: 2 campi su 3 finti.

### GET /api/cash-register/last-upload — ultimo import
**Cosa fa**: data/filename/record dell'ultimo caricamento registratore di cassa.
**Logica codice**: find_one su `cash_uploads` per created_at desc.

### GET /api/cash-register/stats-documenti-commerciali — statistiche documenti commerciali
**Cosa fa**: conta i movimenti `category: "Corrispettivo"` e i giorni distinti nel periodo.
**Logica codice**: count + `distinct("date")` su `prima_nota_cassa`.

### GET /api/cash-register/stats-pos-comparison — confronto POS XML vs manuale (FINTO)
**Cosa fa**: dichiara di confrontare POS da XML vs manuale ma il confronto è finto.
**Logica codice**: somma `amount` dei movimenti `category: "POS"`, poi imposta `pos_xml = pos_manual` (dummy dichiarato nei commenti): differenza sempre 0, stato sempre "ok"/"Dati allineati".
**Note**: endpoint ingannevole; il confronto vero è in /api/pos-corrispettivi/*.

---

## pagopa.py (/api/pagopa — 7 endpoint)

Associazione ricevute PagoPA ↔ movimenti bancari tramite l'identificativo bolletta (codice CBILL) nella descrizione del movimento. Usa la collezione canonica `estratto_conto_movimenti` + `ricevute_pagopa`. Helper `cerca_movimento_per_bolletta` (find_one regex del codice su descrizione_originale/descrizione). Nessuna autenticazione.

### GET /api/pagopa/ricevute — lista ricevute
**Cosa fa**: ricevute caricate, filtrabili per anno e stato associazione.
**Logica codice**: `ricevute_pagopa` (anno regex su data_pagamento; associata = esistenza `movimento_id`), sort desc, limit 100.

### POST /api/pagopa/ricevute/upload — upload ricevuta + auto-associazione
**Cosa fa**: carica una ricevuta (metadati passati a mano) e, se c'è l'identificativo bolletta, la associa subito al movimento bancario.
**Logica codice**: legge il file solo per la dimensione (il CONTENUTO NON VIENE SALVATO); crea il doc in `ricevute_pagopa`; se `identificativo_bolletta` presente, `cerca_movimento_per_bolletta` e a match scrive su entrambi i lati (`movimento_id` sulla ricevuta, `ricevuta_pagopa_id`/`ricevuta_filename` sul movimento).
**Note**: la docstring promette il parsing del PDF ma nessun parsing esiste; il binario viene scartato: la ricevuta non è recuperabile.

### POST /api/pagopa/ricevute/associa-manuale — associazione manuale
**Cosa fa**: collega manualmente una ricevuta a un movimento per id.
**Logica codice**: valida i due id (400); aggiorna `ricevute_pagopa` (404 se modified_count==0) poi `estratto_conto_movimenti` con riferimento incrociato.
**Note**: il 404 scatta anche se la ricevuta è già associata allo stesso movimento; non verifica che il movimento esista.

### POST /api/pagopa/auto-associa — auto-associazione massiva
**Cosa fa**: scandisce le ricevute non associate con bolletta e tenta il match automatico con l'estratto conto; report associate/non trovate/errori.
**Logica codice**: `ricevute_pagopa` (movimento_id nullo, bolletta presente, max 1000); per ognuna `cerca_movimento_per_bolletta`; a match aggiorna entrambe le collezioni.

### POST /api/pagopa/cerca-movimenti-pagopa — ricerca movimenti PagoPA/CBILL
**Cosa fa**: elenca i movimenti EC riconducibili a PagoPA/CBILL/AdER (default solo non associati), estraendo il codice bolletta e raggruppando per beneficiario (AdE-R, INPS, INAIL, Altro).
**Logica codice**: regex `CBILL|PAGOPA|AGENZIA.DELLE.ENTRATE.*R|RISCOSSIONE` su descrizione_originale/descrizione + filtro anno + `ricevuta_pagopa_id` nullo; estrae il codice con `CBILL\s*(\d{15,18})`; aggregati in memoria. Sola lettura.
**Note**: ricerca read-only esposta come POST (l'alias GET sotto la richiama).

### GET /api/pagopa/stats — statistiche PagoPA
**Cosa fa**: movimenti PagoPA totali/con ricevuta/senza, ricevute caricate/associate, totale importi, opz. per anno.
**Logica codice**: quattro count (riusando/mutando i dict query) + aggregate `$sum $abs importo` su `estratto_conto_movimenti`.
**Note**: la regex dell'aggregazione importi (senza `PAGOPA`) è più stretta di quella del conteggio → totale e conteggio su insiemi diversi.

### GET /api/pagopa/movimenti-agenzia-entrate — alias movimenti AdE-R
**Cosa fa**: TUTTI i movimenti PagoPA (anche associati) per anno.
**Logica codice**: delega a `cerca_movimenti_pagopa(anno, solo_non_associati=False)`; alias di compatibilità.

### Anomalie (gruppo POS / pagamenti / cassa / PagoPA)
1. Due endpoint di multi_pagamento.py NON funzionanti (`assegno-multi-fatture`, `fattura-multi-metodo`): `registra_pagamento(Body(**dict))` → TypeError a runtime.
2. Due endpoint di cash.py NON funzionanti (`POST/GET corrispettivi`): `CashService(movement_repo, None)` → AttributeError su `corrispettivo_repo`.
3. CRUD duplicato su `prima_nota_cassa`: cash.py (Pydantic, filtro user_id, campo `data`) vs cash_register.py (dict liberi, nessun filtro utente, campo `date`) — movimenti creati da un modulo possono non comparire nei filtri dell'altro.
4. DELETE massivo pericoloso: `DELETE /api/cash-register/movements` senza entrambe le date esegue `delete_many({})` sull'intera `prima_nota_cassa`.
5. Endpoint finti con risposte di successo: `stats-pos-comparison` (pos_xml=pos_manual), `stats-annulli` (importi hardcoded), `ocr-assegni/estrai-dati` e `leggi-carnet` (nessun OCR), `pagopa/ricevute/upload` (nessun parsing, file scartato).
6. Fonte banca incoerente: pos_corrispettivi_check usa `prima_nota_banca`, pos_accredito e pagopa usano la canonica `estratto_conto_movimenti` → le riconciliazioni POS dei due moduli possono divergere.
7. Tre calendari accredito POS in conflitto: v1 manda Ven-Dom a martedì, v2 correttamente a lunedì, pos_accredito usa un terzo helper con festivi.
8. Deprecazione solo nei commenti (verifica-coerenza), regex banca reintrodotta dopo il fix del 22/04/2026 (riconcilia-pos-giorno, _carica_accrediti_banca_pos), chiusure POS scritte in `prima_nota_banca` invece che nella collezione dedicata.
9. Autenticazione a macchia di leopardo: ocr_assegni/cash/cash_register e 2 endpoint POS-check autenticati; pos_accredito, multi_pagamento, pagopa e gli altri POS-check no (inclusi endpoint che scrivono).

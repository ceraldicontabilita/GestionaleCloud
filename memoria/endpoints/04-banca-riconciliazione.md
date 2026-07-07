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

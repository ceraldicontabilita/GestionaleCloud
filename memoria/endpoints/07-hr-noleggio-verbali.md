# Endpoint HR / Paghe / TFR / Noleggio / Verbali (07)

<!-- gestionalecloud-doc
status: reference
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!IMPORTANT]
> Documento di riferimento del dominio. La specifica normativa unica è `PROMPT_MASTER.md`; questo file non può contraddirla.

Moduli: dipendenti, paghe (distinte BPM + parser F24 + Libro Unico), TFR, INPS documenti,
verbali noleggio (2 router), verbali riconciliazione, noleggio, veicoli, alert verbali, ADR.
Contesto: la gestione HR "viva" è su AppDipendenti (stesso Atlas, collezioni `employees`/`cedolini`
condivise — NON eliminarle). Il gestionale usa questi endpoint soprattutto per prima nota salari,
riconciliazione bonifici stipendi, trattenute da verbali e TFR.
Flusso verbali: PEC/Gmail → `verbali_noleggio` → matching targa/driver → trattenuta dipendente o
fattura noleggiatore → pagamento PayPal/PagoPA (`paypal_transaction_id` sul verbale).

---

## employees/dipendenti.py (prefisso /api/dipendenti — 52 endpoint)

Anagrafica dipendenti (collection `dipendenti` via `Collections.EMPLOYEES`), più sotto-moduli
turni, libretti sanitari, libro unico "light", contratti, buste paga da cartelle locali, report PDF.
Dal frontend del gestionale è usato SOLO `GET /api/dipendenti` (InserimentoRapido.jsx:251,
VerbaliRiconciliazione.jsx:56); il resto è orfano o duplicato dell'app esterna AppDipendenti.

### GET /api/dipendenti — lista dipendenti
**Cosa fa**: lista anagrafica con filtri (attivo, in_carico, mansione, search su nome/CF), dedup per CF.
**Logica codice**: legge `dipendenti`; `in_carico=true` = flag true O assente; esclude `merged_into` salvo `include_merged`; regex escape sulla search; dedup post-query per codice_fiscale.
**Note**: UNICO endpoint del modulo usato dal frontend gestionale (InserimentoRapido, VerbaliRiconciliazione). Da mantenere.

### GET /api/dipendenti/by-google-email — lookup per email Google
**Cosa fa**: trova il dipendente associato a una Google email (portale dipendenti).
**Logica codice**: `find_one` su `dipendenti.google_email` (lowercase); 404 se assente.
**Note**: orfano nel gestionale; funzione da portale/AppDipendenti.

### GET /api/dipendenti/stats — statistiche anagrafica
**Cosa fa**: conteggi totale/attivi/inattivi, per mansione, libretti in scadenza 30gg.
**Logica codice**: count + aggregate `$group` su `dipendenti`; confronto stringa su `libretto_scadenza`.
**Note**: orfano (HR spostata su AppDipendenti).

### GET /api/dipendenti/duplicati — sospetti duplicati
**Cosa fa**: gruppi di dipendenti sospetti duplicati (CF normalizzato o nome+cognome).
**Logica codice**: delega a `app.services.dipendenti_dedupe.trova_duplicati()`.

### POST /api/dipendenti/duplicati/merge — merge duplicato
**Cosa fa**: unifica `duplicate_id` dentro `target_id` re-puntando cedolini/presenze/verbali/movimenti.
**Logica codice**: `dipendenti_dedupe.merge_dipendenti(target, dup, soft)`; soft-delete di default (`merged_into` + `in_carico=False`); 400 se mancano gli id.

### POST /api/dipendenti/duplicati/auto-merge — auto-merge massivo
**Cosa fa**: merge automatico dei duplicati ad alta certezza; default `dry_run=true` (solo anteprima).
**Logica codice**: `dipendenti_dedupe.auto_merge_tutti(dry_run)`.

### GET /api/dipendenti/report-ferie-permessi-tutti — PDF riepilogo ferie/permessi
**Cosa fa**: PDF landscape con ferie/permessi maturati/goduti/residui di tutti i dipendenti con `progressivi`.
**Logica codice**: legge `dipendenti` (solo con `progressivi`), dedup CF/nome, tabella reportlab con totali; Response PDF attachment.
**Note**: dato HR ora gestito da AppDipendenti; orfano.

### POST /api/dipendenti/sync-iban — normalizza iban → ibans[]
**Cosa fa**: per i dipendenti con `iban` singolo ma `ibans` vuoto copia il valore nell'array.
**Logica codice**: query dipendenti con `iban` e `ibans` assente/vuoto; `$set ibans:[iban]` (uppercase, no spazi).
**Note**: utility one-shot per il matching bonifici stipendi.

### GET /api/dipendenti/tipi-turno — costanti turni
**Cosa fa**: ritorna il dizionario statico TURNI_TIPI (mattina/pomeriggio/sera/full/riposo/ferie/malattia).
**Logica codice**: nessun accesso DB.

### GET /api/dipendenti/mansioni — costanti mansioni
**Cosa fa**: lista statica MANSIONI (Cameriere, Cuoco, ...).
**Logica codice**: nessun accesso DB.

### GET /api/dipendenti/tipi-contratto — costanti contratti
**Cosa fa**: lista statica CONTRATTI_TIPI.
**Logica codice**: nessun accesso DB.

### POST /api/dipendenti/bulk-upsert — import/update massivo (match su CF)
**Cosa fa**: crea o aggiorna in massa dipendenti matchando sul codice fiscale.
**Logica codice**: whitelist CAMPI_AGGIORNABILI; update "conservativo" (solo campi vuoti, salvo `overwrite_fields`); insert con default + evento `DIPENDENTE_CREATED` su event bus; report per riga created/updated/skipped.

### POST /api/dipendenti/bulk-upsert/preview — dry-run import massivo
**Cosa fa**: stessa logica del bulk-upsert ma SOLO lettura; ritorna `diff` {campo:{vecchio,nuovo}} per la UI.
**Logica codice**: duplica la whitelist (sincronizzata a mano, come dichiarato in commento); `dry_run:true` in risposta.
**Note**: duplicazione strutturale con /bulk-upsert: se si tocca uno va toccato l'altro.

### POST /api/dipendenti — crea dipendente
**Cosa fa**: crea record anagrafico completo (contratto, IBAN, progressivi, libretto, flag portale).
**Logica codice**: richiede nome_completo o nome+cognome (non splitta nome_completo per non rompere "De Luca"); `iban`/`iban_cedolino` allineati; 409 su CF duplicato; insert su `dipendenti` + evento `DIPENDENTE_CREATED`.

### GET /api/dipendenti/buste-paga — buste paga del mese
**Cosa fa**: lista cedolini per periodo `anno-mese`.
**Logica codice**: legge collection `cedolini` per campo `periodo`.
**Note**: `cedolini` è condivisa con AppDipendenti; qui sola lettura per il gestionale.

### POST /api/dipendenti/buste-paga — crea/aggiorna busta paga
**Cosa fa**: upsert cedolino (lordo/netto/contributi/trattenute/pagata) per dipendente+periodo.
**Logica codice**: cerca esistente su `cedolini` (dipendente_id+periodo); su CREAZIONE propaga evento `CEDOLINO_IMPORTATO` (prima nota salari, alert).

### GET /api/dipendenti/contratti — lista contratti (proxy)
**Cosa fa**: lista contratti con filtri dipendente_id/tipo/stato.
**Logica codice**: legge `contratti_dipendenti` ordinati per data_inizio desc. Definito PRIMA di `/{dipendente_id}` per evitare conflitto rotta.
**Note**: DUPLICATO: la stessa rotta GET /contratti è ridefinita più sotto (riga ~1945, `list_contratti`) con identica logica; la seconda è irraggiungibile (vince la prima registrata).

### GET /api/dipendenti/{dipendente_id} — dettaglio dipendente
**Cosa fa**: dettaglio singolo per id o codice fiscale.
**Logica codice**: `find_one` su `dipendenti` con `$or {id, codice_fiscale}`.

### PUT /api/dipendenti/{dipendente_id} — aggiorna dipendente + cascate
**Cosa fa**: update anagrafica; sincronizza nome_completo, iban↔iban_cedolino; gestisce transizione `in_carico` come cessazione/riattivazione; propaga IBAN nei bonifici.
**Logica codice**: se `in_carico` passa a False imposta `attivo=False` + `data_cessazione` ed emette `DIPENDENTE_CESSATO` (stesso effetto del DELETE); riattivazione fa `$unset data_cessazione`; aggiorna `bonifici_transfers` (dipendente_ibans + auto-match per IBAN su bonifici orfani); evento `DIPENDENTE_UPDATED`.
**Note**: endpoint chiave per la riconciliazione bonifici stipendi (matching per IBAN).

### DELETE /api/dipendenti/{dipendente_id} — cessa dipendente (soft delete)
**Cosa fa**: marca `in_carico=False, attivo=False, data_cessazione=now`; il fascicolo resta.
**Logica codice**: update su `dipendenti`; evento `DIPENDENTE_CESSATO` per pulire flussi attivi.

### GET /api/dipendenti/turni/settimana — turni settimanali
**Cosa fa**: turni di 7 giorni da `data_inizio` organizzati per dipendente/data.
**Logica codice**: legge `turni_dipendenti` per date; carica dipendenti attivi come righe.
**Note**: gestione turni spostata su AppDipendenti; orfano.

### POST /api/dipendenti/turni/salva — salva turni
**Cosa fa**: upsert dei turni {dipendente: {data: turno}}.
**Logica codice**: upsert per (dipendente_id, data) su `turni_dipendenti`.
**Note**: orfano (HR esterna).

### GET /api/dipendenti/libretti/scadenze — libretti (campo su dipendente) in scadenza
**Cosa fa**: dipendenti con `libretto_scadenza` entro N giorni o già scaduto.
**Logica codice**: query su `dipendenti.libretto_scadenza` (confronto stringhe ISO).
**Note**: coesiste con la collection separata `libretti_sanitari` (vedi sotto) — doppio modello dati.

### PUT /api/dipendenti/{dipendente_id}/libretto — aggiorna libretto su anagrafica
**Cosa fa**: aggiorna libretto_numero/scadenza/file sul record dipendente.
**Logica codice**: `$set` su `dipendenti`.

### POST /api/dipendenti/{dipendente_id}/invita-portale — flag invito portale
**Cosa fa**: marca `portale_invitato=True` con data invito.
**Logica codice**: `$set` su `dipendenti`. NON invia realmente alcuna email.
**Note**: il docstring "Segna come invitato" è corretto ma il nome può ingannare: nessun invio. Portale ora in AppDipendenti; orfano.

### POST /api/dipendenti/invita-multipli — flag invito multiplo
**Cosa fa**: come sopra ma su lista di id (`update_many`).
**Note**: orfano.

### GET /api/dipendenti/libretti-sanitari/all — lista libretti (collection separata)
**Cosa fa**: tutti i record di `libretti_sanitari` ordinati per scadenza.
**Logica codice**: `find` su `libretti_sanitari`.

### POST /api/dipendenti/libretti-sanitari — crea libretto
**Cosa fa**: crea record libretto (nome dipendente, numero, date, stato).
**Logica codice**: insert su `libretti_sanitari` con uuid.

### PUT /api/dipendenti/libretti-sanitari/{libretto_id} — aggiorna libretto
**Logica codice**: `$set` su `libretti_sanitari` per id; 404 se assente.

### DELETE /api/dipendenti/libretti-sanitari/{libretto_id} — elimina libretto
**Logica codice**: `delete_one` (hard delete) su `libretti_sanitari`.

### GET /api/dipendenti/libro-unico/presenze — presenze libro unico (light)
**Cosa fa**: presenze per `month_year` dalla collection `libro_unico_presenze`.
**Logica codice**: `find` semplice.
**Note**: collection alimentata dal vecchio upload sotto; il parser "vero" è `libro_unico_parser.py` (`presenze_mensili`). Doppio modello dati legacy.

### GET /api/dipendenti/libro-unico/salaries — buste dal libro unico (light)
**Cosa fa**: record salari (nome, netto_a_pagare, acconto, differenza) da `libro_unico_salaries`.
**Logica codice**: `find` con filtro opzionale month_year.

### POST /api/dipendenti/libro-unico/upload — upload PDF/Excel libro unico (legacy)
**Cosa fa**: parsing euristico di PDF (PyMuPDF: nome maiuscolo + riga "netto" + importo 100-10000) o Excel (pandas) e salva in `libro_unico_salaries`.
**Logica codice**: dedup per (dipendente_nome, month_year); i contatori presenze/payments/anagrafica restano sempre 0 (dichiarati ma mai incrementati).
**Note**: parser molto fragile (euristica testo); superato da POST /api/paghe/import-libro-unico. La risposta riporta campi (`presenze_count`, `anagrafica_created`...) che sono sempre 0.

### GET /api/dipendenti/libro-unico/export-excel — export Excel
**Cosa fa**: genera xlsx dei record `libro_unico_salaries` del mese.
**Logica codice**: openpyxl, StreamingResponse.

### PUT /api/dipendenti/libro-unico/salaries/{salary_id} — aggiorna record salari
**Logica codice**: `$set` netto/acconto/differenza/note su `libro_unico_salaries` (parametri via query string, non body).

### DELETE /api/dipendenti/libro-unico/salaries/{salary_id} — elimina record salari
**Logica codice**: `delete_one`.

### GET /api/dipendenti/portale/stats — statistiche portale
**Cosa fa**: conteggi invitati/registrati/mai invitati.
**Logica codice**: 4 `count_documents` su `dipendenti`.
**Note**: portale gestito da AppDipendenti; orfano.

### POST /api/dipendenti/libretti-sanitari/import-excel — import massivo libretti
**Cosa fa**: importa libretti da Excel (nome, numero, date, note) con match fuzzy sul dipendente.
**Logica codice**: pandas; match dipendente con `$regex` sul nome (non escaped → nomi con caratteri regex possono rompere la query); calcola stato valido/in_scadenza/scaduto; upsert su `libretti_sanitari`.

### GET /api/dipendenti/libretti-sanitari/scadenze — libretti scaduti/in scadenza
**Logica codice**: due `find` su `libretti_sanitari.data_scadenza` (< oggi; tra oggi e +N giorni).

### POST /api/dipendenti/libretti-sanitari/genera-da-dipendenti — genera libretti vuoti
**Cosa fa**: crea un libretto "da_compilare" per ogni dipendente attivo senza libretto.
**Logica codice**: query dipendenti per `status` in [attivo, active, None]; check esistenza per dipendente_id o nome (regex escaped); insert.
**Note**: usa il campo `status` mentre il resto del modulo usa `attivo` — filtro incoerente.

### GET /api/dipendenti/contratti (seconda definizione) — lista contratti
**Note**: DUPLICATO IRRAGGIUNGIBILE della rotta proxy definita prima (vedi sopra). Stessa identica logica; da rimuovere in un giro futuro.

### POST /api/dipendenti/contratti — crea contratto
**Cosa fa**: crea contratto per dipendente e lo marca come contratto attivo sull'anagrafica.
**Logica codice**: valida dipendente, retribuzione >= 0, data_fine >= data_inizio; insert su `contratti_dipendenti`; `$set contratto_attivo_id/tipo_contratto/livello` sul dipendente.

### PUT /api/dipendenti/contratti/{contratto_id} — aggiorna contratto
**Logica codice**: 409 se stato "terminato"; rimuove id/created_at/dipendente_id dal payload; `$set` su `contratti_dipendenti`.

### POST /api/dipendenti/contratti/{contratto_id}/termina — termina contratto
**Cosa fa**: marca il contratto terminato con data_fine e motivo; azzera `contratto_attivo_id` sul dipendente.
**Logica codice**: se motivo valorizzato imposta `status="cessato"` sul dipendente (di nuovo campo `status`, non `attivo`/`in_carico`).

### DELETE /api/dipendenti/contratti/{contratto_id} — elimina contratto
**Logica codice**: `delete_one` diretto; il docstring parla di "solo bozze" ma NON c'è alcun controllo sullo stato: elimina qualsiasi contratto.
**Note**: docstring non veritiero (nessuna validazione stato).

### GET /api/dipendenti/contratti/scadenze — contratti determinati in scadenza
**Logica codice**: due `find` su `contratti_dipendenti` (tipo tempo determinato in 4 varianti testuali, stato attivo) per scaduti e in scadenza entro N giorni.

### POST /api/dipendenti/contratti/import-excel — import massivo contratti
**Cosa fa**: crea contratti da Excel con match fuzzy dipendente per nome.
**Logica codice**: pandas; regex non escaped sul nome; parse date multi-formato; insert + aggiorna `contratto_attivo_id` sul dipendente.

### GET /api/dipendenti/buste-paga/scan — scan cartelle buste paga locali
**Cosa fa**: scansiona `/tmp/documents/buste_paga` ed estrae i progressivi (TFR/ferie/permessi) dai PDF.
**Logica codice**: `busta_paga_parser.scan_all_dipendenti`; lista cartelle per dipendente.
**Note**: path `/tmp` effimero su Render: dopo un deploy la cartella non esiste → risponde sempre "Cartella non trovata". Flusso legacy pre-AppDipendenti.

### POST /api/dipendenti/buste-paga/import — importa progressivi da buste locali
**Cosa fa**: match cartella↔dipendente (per CF o nome, anche invertito) e aggiorna `progressivi` + paga_base/contingenza sul dipendente; `dry_run` default true.
**Logica codice**: `scan_all_dipendenti` + update `dipendenti`.
**Note**: stesso problema di path effimero; orfano.

### GET /api/dipendenti/buste-paga/dipendente/{dipendente_id} — buste di un dipendente
**Cosa fa**: trova la cartella locale del dipendente e lista le sue buste parse-ate.
**Logica codice**: match nome cartella (anche invertito); `scan_dipendente_folder`.
**Note**: path effimero; orfano.

### POST /api/dipendenti/buste-paga/dipendente/{dipendente_id}/import — importa ultimi progressivi
**Cosa fa**: prende i progressivi dall'ultima busta del dipendente e li scrive sull'anagrafica.
**Logica codice**: `get_latest_progressivi` + `$set progressivi` su `dipendenti`.
**Note**: path effimero; orfano.

### GET /api/dipendenti/{dipendente_id}/report-ferie-permessi — PDF ferie/permessi singolo
**Cosa fa**: PDF annuale con progressivi + dettaglio mensile dai cedolini.
**Logica codice**: legge `dipendenti` e `cedolini` (per dipendente_id o CF, anno); reportlab; Response PDF.
**Note**: orfano nel gestionale (dato HR).

---

## distinte_bpm.py + f24_parser.py + libro_unico_parser.py (prefisso /api/paghe — 18 endpoint)

Pipeline paghe: import Libro Unico Zucchetti → anagrafica/presenze/buste_paga/TFR/prima nota salari;
import Modello F24 → tributi/distinte/scadenze; import distinte bonifici BPM → riconciliazione buste.
Vivi nel gestionale: Dashboard.jsx usa `GET /api/paghe/buste-paga?stato=DA_PAGARE` e
`GET /api/paghe/distinte-f24?stato=DA_PAGARE` (widget "da pagare").

### distinte_bpm.py

### POST /api/paghe/import-distinte-bpm — importa CSV distinta stipendi BPM
**Cosa fa**: legge il CSV bonifici BPM e marca PAGATO le buste paga corrispondenti (match nome fuzzy + importo ±5€).
**Logica codice**: autodetect separatore ;/,; skip acconti (causale con "acc"); carica `buste_paga` DA_PAGARE; su match `$set stato_pagamento=PAGATO, data_pagamento, riconciliato_da=distinte_bpm`; `solo_anteprima` per dry-run; ritorna riconciliati/non_trovati/acconti (troncati).

### POST /api/paghe/riconcilia-pagamento-manuale — riconciliazione manuale busta
**Cosa fa**: marca PAGATO la prima busta DA_PAGARE il cui nome matcha (fuzzy) il dipendente indicato.
**Logica codice**: scan `buste_paga` con `match_names`; `$set PAGATO + importo_pagato + riconciliato_da=manuale`.
**Note**: prende la PRIMA busta che matcha, senza filtro periodo: con più mesi da pagare può riconciliare il mese sbagliato.

### f24_parser.py

### POST /api/paghe/parse-f24 — parse PDF F24 (solo lettura)
**Cosa fa**: estrae da un PDF F24 contribuente, sezioni ERARIO/INPS/REGIONI/IMU/INAIL, totale, IBAN.
**Logica codice**: pdfplumber + regex specifiche per il layout (anche pattern hardcoded "CERALDI GROUP"); nessuna scrittura DB.

### POST /api/paghe/import-f24 — importa F24 (workflow completo)
**Cosa fa**: parse + salva F24 e innesca tributi, distinta, scadenza e riconciliazione bancaria.
**Logica codice**: upsert `f24_pagamenti` (id = cf+scadenza) stato DA_PAGARE → upsert `tributi_pagati` per riga → upsert `distinte_f24` → upsert `scadenze` → tenta match in estratto conto (`paghe_riconciliazione.cerca_in_estratto_conto`, ±7gg, keyword F24/ERARIO/INPS...); se trovato marca PAGATO f24+tributi+distinta, completa scadenza, flagga `prima_nota_banca`.
**Note**: contiene una closure `salva_tributi` MORTA (definita, mai chiamata, con `return` dentro il loop): il salvataggio reale è il loop duplicato subito dopo.

### POST /api/paghe/riconcilia-f24 — riconcilia tutti gli F24
**Cosa fa**: riesegue la riconciliazione bancaria per gli F24 DA_PAGARE (opz. per anno).
**Logica codice**: delega a `paghe_riconciliazione.riconcilia_tutti_f24`.

### GET /api/paghe/tributi-pagati — storico tributi
**Cosa fa**: elenco tributi versati filtrabile per anno/codice/sezione/stato, con totale.
**Logica codice**: `find` su `tributi_pagati` (anno via `$regex`).

### GET /api/paghe/distinte-f24 — lista distinte F24
**Cosa fa**: distinte aggregate con riepilogo per sezione.
**Logica codice**: `find` su `distinte_f24` (anno via regex su `scadenza`).
**Note**: USATO da Dashboard.jsx (widget F24 da pagare).

### GET /api/paghe/f24/lista — lista F24 importati
**Cosa fa**: elenco sintetico F24 (id, scadenza, totale, stato, riconciliato).
**Logica codice**: `find` con proiezione su `f24_pagamenti`.

### libro_unico_parser.py

### POST /api/paghe/parse-libro-unico — parse LUL Zucchetti (solo lettura)
**Cosa fa**: parsa l'intero Libro Unico (2 pagine/dipendente: presenze + busta) e ritorna dati e riepilogo.
**Logica codice**: pdfplumber; filtro anti-filigrana Zucchetti (WATERMARK_PATTERNS); regex per presenze giornaliere, competenze, trattenute, IRPEF, TFR, ratei, netto, IBAN.

### POST /api/paghe/parse-libro-unico/dipendente/{indice} — parse singolo dipendente
**Cosa fa**: parsa solo la coppia di pagine del dipendente `indice` (0-based).
**Logica codice**: come sopra su 2 pagine; 400 se indice fuori range.

### POST /api/paghe/import-libro-unico — importa LUL (workflow completo)
**Cosa fa**: per ogni dipendente del PDF aggiorna anagrafica, salva presenze e busta paga, aggiorna TFR, crea prima nota salari, scadenza stipendio e tenta riconciliazione bancaria.
**Logica codice**: STEP1 upsert anagrafica su **`employees`** (collection condivisa AppDipendenti); STEP2 upsert `presenze_mensili` (cf+periodo); STEP3 upsert `buste_paga` stato DA_PAGARE; STEP3b se il dipendente esiste in **`dipendenti`** upsert `tfr_accantonamenti` per (dipendente, anno) con i valori TFR del cedolino (quota_anno cumulativa, fondo 31/12) e aggiorna `tfr_accantonato` sul dipendente, poi `handler_prima_nota_cedolino` per il movimento salari; STEP4 upsert `scadenze`; STEP5 match estratto conto (±10gg, keyword STIPENDIO/CEDOLINO/cognome) → PAGATO + flag su `prima_nota_banca`.
**Note**: è il cuore del flusso "paghe → prima nota/TFR". ATTENZIONE doppia anagrafica: scrive su `employees` ma TFR/prima nota cercano in `dipendenti`; se il CF non è in `dipendenti` il collegamento TFR/salari viene saltato (solo warning). Il docstring dice "collection employees" ed è vero solo per lo STEP1.

### POST /api/paghe/riconcilia-stipendi — riconcilia stipendi in blocco
**Cosa fa**: riesegue la riconciliazione bancaria per tutte le buste DA_PAGARE (opz. anno/mese).
**Logica codice**: delega a `paghe_riconciliazione.riconcilia_tutti_stipendi`.

### GET /api/paghe/buste-paga — lista buste importate
**Cosa fa**: elenco buste con stato pagamento, filtri anno/mese/stato/CF.
**Logica codice**: `find` con proiezione su `buste_paga`.
**Note**: USATO da Dashboard.jsx (widget buste da pagare) e alimenta la riconciliazione distinte BPM.

### GET /api/paghe/presenze-mensili — lista presenze da LUL
**Logica codice**: `find` su `presenze_mensili` con filtri anno/mese/CF; proiezione senza dettaglio giornaliero.

### GET /api/paghe/presenze-mensili/{codice_fiscale}/{periodo} — dettaglio presenze
**Logica codice**: `find_one` (calendario giornaliero + giustificativi); 404 se assente.

### GET /api/paghe/acconti — acconti per busta
**Cosa fa**: buste con array `acconti`, totale acconti e residuo da pagare calcolati al volo.
**Logica codice**: `find` su `buste_paga` + somma in Python.
**Note**: sistema acconti "per busta" DIVERSO da quello di tfr.py (`acconti_dipendenti`): due modelli paralleli non sincronizzati.

### POST /api/paghe/acconti/{busta_id} — aggiungi acconto a busta
**Logica codice**: `$push acconti` sulla busta (id corto uuid[:8]); ricalcola residuo; 400 importo <= 0.

### DELETE /api/paghe/acconti/{busta_id}/{acconto_id} — elimina acconto busta
**Logica codice**: `$pull` dall'array acconti.

---

## tfr.py (prefisso /api/tfr — 17 endpoint)

Fondo TFR: accantonamenti annuali (art. 2120 c.c.), liquidazioni/anticipi, acconti dipendente con
lifecycle registrato → riconciliato_banca → scalato_su_cedolino. Vivo nel gestionale:
GestioneCespiti.jsx usa `GET /api/tfr/riepilogo-aziendale?anno=` (fondo TFR in contabilità).
Collection: `dipendenti`, `tfr_accantonamenti`, `tfr_liquidazioni`, `acconti_dipendenti`,
`movimenti_contabili`, `estratto_conto_movimenti`, `cedolini`.

### GET /api/tfr/situazione/{dipendente_id} — situazione TFR dipendente
**Cosa fa**: TFR accantonato, disponibile (accantonato − liquidato), storico accantonamenti e liquidazioni.
**Logica codice**: legge `dipendenti.tfr_accantonato`, `tfr_accantonamenti`, `tfr_liquidazioni`.

### POST /api/tfr/accantonamento — registra accantonamento annuale
**Cosa fa**: quota = retribuzione/13.5 + rivalutazione (1.5% + 75% ISTAT) sul fondo precedente; aggiorna il fondo.
**Logica codice**: valida anno 2020-2030 e retribuzione > 0; insert `tfr_accantonamenti`; `$set tfr_accantonato`; insert `movimenti_contabili` tipo tfr_accantonamento.
**Note**: NON verifica duplicati per anno (il check esiste solo in /calcola-batch): doppia chiamata = doppio accantonamento.

### POST /api/tfr/liquidazione — liquida TFR (totale/parziale/anticipo)
**Cosa fa**: liquida con ritenuta forfettaria 23% (tassazione separata semplificata); per anticipo max 70% del maturato.
**Logica codice**: valida importi; insert `tfr_liquidazioni`; scala `tfr_accantonato`; 2 movimenti contabili (fondo + ritenute).
**Note**: aliquota 23% dichiaratamente approssimata (non calcolo TUIR reale).

### GET /api/tfr/riepilogo-aziendale — fondo TFR aziendale
**Cosa fa**: totale fondo, accantonamenti e liquidazioni dell'anno, dettaglio per dipendente.
**Logica codice**: dipendenti con `status` in [attivo, active] (di nuovo `status`, non `attivo`); 2 aggregate su accantonamenti/liquidazioni.
**Note**: VIVO — usato da GestioneCespiti.jsx. Il filtro `status` può escludere dipendenti che hanno solo `attivo=true`.

### POST /api/tfr/calcola-batch/{anno} — accantonamento massivo
**Cosa fa**: calcola il TFR annuale per tutti i dipendenti attivi usando il lordo dei cedolini (fallback prima_nota_salari).
**Logica codice**: skip se già calcolato per l'anno; aggrega `cedolini.lordo`; richiama internamente `registra_accantonamento_tfr` (indice ISTAT 0).

### GET /api/tfr/acconti/{dipendente_id} — acconti del dipendente
**Cosa fa**: acconti raggruppati per tipo (tfr/ferie/13ma/14ma/prestito) con totali e saldo TFR.
**Logica codice**: legge `acconti_dipendenti`; nota: gli acconti tipo "stipendio" non compaiono nei gruppi (dizionario senza quella chiave) pur essendo un tipo valido in POST.

### POST /api/tfr/acconti — registra acconto
**Cosa fa**: crea acconto (tipo, natura su_futuro/su_pregresso, bonifico standard/istantaneo, mese di scalatura) in stato "registrato".
**Logica codice**: valida tipo/natura/bonifico; deriva `scalato_su_anno_mese` dalla data; insert `acconti_dipendenti`; se tipo=tfr scala subito `tfr_accantonato` e crea movimento contabile.

### PUT /api/tfr/acconti/{acconto_id} — modifica acconto
**Cosa fa**: update parziale (importo/data/tipo/natura/bonifico/scalatura/stato) con ricalcolo anno/mese.
**Logica codice**: se cambia importo su acconto TFR riallinea il fondo (vecchio − nuovo); validazioni sui valori ammessi.

### DELETE /api/tfr/acconti/{acconto_id} — elimina acconto
**Logica codice**: se tipo=tfr ripristina il fondo; `delete_one` (hard delete, niente stato "annullato" nonostante sia negli STATI_VALIDI).

### GET /api/tfr/acconti/{acconto_id}/candidati-banca — candidati estratto conto
**Cosa fa**: propone movimenti bancari compatibili con l'acconto (uscita, importo ±0.01, range data per tipo bonifico, nome in descrizione) con score.
**Logica codice**: query `estratto_conto_movimenti` con `$expr` su |importo| e `data_contabile_obj`; esclude movimenti già collegati; ranking data+importo+nome.

### POST /api/tfr/acconti/{acconto_id}/riconcilia-banca — collega acconto↔movimento
**Cosa fa**: link bidirezionale acconto (stato riconciliato_banca, movimento_bancario_id) ↔ movimento (acconto_id).
**Logica codice**: 400 se già riconciliato, 409 se movimento già usato.

### POST /api/tfr/acconti/{acconto_id}/annulla-riconciliazione-banca — annulla link banca
**Logica codice**: riporta stato a "registrato", `$unset` dei link su entrambe le collection.

### GET /api/tfr/cedolini/{cedolino_id}/preview-scalatura-acconti — anteprima scalatura
**Cosa fa**: confronta l'"acconto mese precedente" dichiarato dal cedolino (parser AI) con la somma degli acconti registrati per quel periodo; ritorna stato quadra/discrepanza/nessun_dato.
**Logica codice**: `_estrai_acconto_da_cedolino` (3 posizioni possibili nel doc), `_trova_acconti_da_scalare` (match per dipendente_id, fallback CF); nessuna scrittura.

### POST /api/tfr/cedolini/{cedolino_id}/scala-acconti — applica scalatura
**Cosa fa**: marca gli acconti del periodo come `scalato_su_cedolino` linkando il cedolino.
**Logica codice**: riusa la preview; 400 se dati mancanti, 409 su discrepanza salvo `forza_anche_se_discrepanza`; `$set` stato+cedolino_id+importo_scalato_effettivo.

### POST /api/tfr/cedolini/{cedolino_id}/annulla-scalatura-acconti — annulla scalatura
**Logica codice**: ripristina stato precedente (riconciliato_banca se c'è movimento, altrimenti registrato) e `$unset` dei campi di scalatura.

### GET /api/tfr/parse-payslips — parse buste locali per TFR
**Cosa fa**: analizza i PDF "Libro*.pdf" in `/tmp/uploads/paghe` ed estrae dati TFR.
**Logica codice**: `payslip_pdf_parser.parse_all_payslips`; nessuna scrittura DB.
**Note**: docstring dice `/app/uploads/paghe` ma il codice usa `/tmp/uploads/paghe` (effimero) — di fatto quasi sempre "cartella non trovata".

### GET /api/tfr/storico-tfr/{dipendente_id} — storico TFR completo
**Cosa fa**: accantonamenti + liquidazioni + acconti TFR con totali.
**Logica codice**: 3 `find` + somma in Python.

---

## inps_documenti.py (prefisso /api/inps — 9 endpoint)

Scarico documenti INPS da IMAP (Gmail/PEC via env EMAIL_ADDRESS/EMAIL_APP_PASSWORD): delibere FONSI,
dilazioni, certificati medici. PDF salvati base64 in Mongo. Nessun riferimento nel frontend del
gestionale: endpoint da strumenti/scheduler o legacy.

### GET /api/inps/cartelle-delibere — cartelle email rilevanti
**Cosa fa**: lista cartelle IMAP che contengono keyword inps/fonsi/deliber/pec/certificata.
**Logica codice**: `imaplib.list()` + filtro nome; 500 se credenziali mancanti.

### POST /api/inps/scarica-delibere-fonsi — scarica delibere FONSI
**Cosa fa**: cerca email "Delibere - Fonsi" (opz. da data), estrae periodo dal subject e salva i PDF allegati.
**Logica codice**: IMAP search; dedup per (subject, filename); insert `delibere_fonsi` con pdf_base64.
**Note**: il parametro `data_fine` è accettato ma mai usato nella query IMAP.

### POST /api/inps/scarica-dilazioni-inps — scarica dilazioni
**Cosa fa**: cerca email con sede/matricola INPS e subject "dilazion"/"inps", salva PDF.
**Logica codice**: IMAP body search; dedup; insert `dilazioni_inps`.
**Note**: default hardcoded sede "5100" e matricola "5124776507" (dati aziendali Ceraldi).

### GET /api/inps/delibere-fonsi — lista delibere salvate
**Logica codice**: `find` su `delibere_fonsi` senza pdf_base64; filtro anno via regex sulla data italiana.

### GET /api/inps/dilazioni-inps — lista dilazioni salvate
**Logica codice**: `find` su `dilazioni_inps` senza pdf.

### GET /api/inps/stats — conteggi documenti
**Logica codice**: 3 count (`delibere_fonsi`, `dilazioni_inps`, `cassa_integrazione`).
**Note**: `cassa_integrazione` è contata ma NESSUN endpoint la scrive (helper `estrai_dati_cassa_integrazione` mai usato): sempre 0 salvo scritture esterne.

### POST /api/inps/scansiona-certificati-medici — scan certificati malattia
**Cosa fa**: cerca email con keyword certificato/malattia/protocollo, estrae protocollo/CF/date, associa al dipendente per CF e salva il PDF.
**Logica codice**: carica `dipendenti` per mappa CF→dipendente; dedup per protocollo; insert `certificati_medici`; se associato upserta `attendance_note_presenze` (protocollo_malattia sul giorno).

### GET /api/inps/certificati-medici — lista certificati
**Logica codice**: `find` senza pdf; filtro anno fatto in Python su stringa data italiana (endswith anno).

### GET /api/inps/certificati-medici/{protocollo}/pdf — download PDF certificato
**Logica codice**: `find_one` per protocollo; decodifica base64; Response PDF attachment.

---

## verbali_noleggio.py + verbali_noleggio_api.py (prefisso /api/verbali-noleggio — 35 endpoint)

Due router registrati in sequenza sullo stesso prefisso (verbali_noleggio.py ha prefix interno, l'api
riceve il prefix dal registry). verbali_noleggio.py = download da cartelle Gmail "Bxxxxxxxxxx" +
associazione fatture + classificazione; verbali_noleggio_api.py = dettaglio/CRUD + ricerca pagamenti
PayPal/Gmail/E.C. + note consulente. Vivi dal frontend: DettaglioVerbale.jsx (dettaglio, pdf,
scarica-posta, ricevuta-pdf, cerca-pagamento), PaypalTransactionDetailModal.jsx (pdf).
ATTENZIONE: 3 path duplicati tra i due file (`/stats`, `/pdf/{n}`, `/dettaglio/{n}`) — vince sempre
la versione di verbali_noleggio.py (registrato per primo); il `/dettaglio/{n:path}` dell'api risponde
solo per numeri con slash (es. S/2259).

### verbali_noleggio.py

### GET /api/verbali-noleggio/cartelle-verbali — cartelle Gmail dei verbali
**Cosa fa**: lista cartelle IMAP con nome pattern `B\d{10,11}` (una cartella per verbale).
**Logica codice**: IMAP list + regex; credenziali da EMAIL_ADDRESS/EMAIL_PASSWORD (default gmail Ceraldi).

### POST /api/verbali-noleggio/scarica-tutti — scarica PDF da tutte le cartelle
**Cosa fa**: per ogni cartella-verbale scarica i PDF allegati e upserta il documento verbale.
**Logica codice**: skip se `pdf_scaricato` già true; salva `pdf_allegati` base64 su `verbali_noleggio` (chiave numero_verbale); `$set` completo del doc (sovrascrive eventuali campi arricchiti: fattura_associata/riga_fattura_id vengono azzerati a None).
**Note**: l'upsert con `$set verbale_doc` RESETTA i campi di associazione se il verbale era già stato arricchito — rischio regressione dati su ri-esecuzione.

### GET /api/verbali-noleggio/verbali — lista verbali scaricati
**Logica codice**: `find` su `verbali_noleggio` senza pdf_allegati; filtro `associato` su fattura_associata.

### GET /api/verbali-noleggio/verbale/{numero_verbale} — dettaglio con PDF
**Logica codice**: `find_one` completo (INCLUDE i base64 pdf_allegati — risposta pesante).

### POST /api/verbali-noleggio/associa-fatture — associa verbali↔fatture noleggio
**Cosa fa**: cerca il pattern `B\d{10,11}` nelle linee delle fatture noleggiatori e collega i verbali non associati.
**Logica codice**: carica fino a 50k `invoices` (regex supplier ald|leasys|arval|ayvens|locauto|leaseplan|noleggio); indice numero_verbale→fattura; `$set fattura_associata/invoice_number/...` sul verbale e `verbale_pdf.{numero}` sulla fattura.

### GET /api/verbali-noleggio/pdf/{numero_verbale} — PDF verbale (base64 JSON)
**Cosa fa**: ritorna il PDF n-esimo: `pdf_allegati[i]` (vecchio formato) oppure `pdf_data` (indice 0) / `quietanza_pdf` (indice 1).
**Logica codice**: cerca anche per `numero_verbale_old`.
**Note**: PATH DUPLICATO con verbali_noleggio_api.py (versione quasi identica, irraggiungibile quella dell'api). USATO da DettaglioVerbale.jsx e PaypalTransactionDetailModal.jsx.

### GET /api/verbali-noleggio/stats — statistiche verbali (posta)
**Logica codice**: 3 count su `verbali_noleggio` (totale, con pdf, associati a fattura).
**Note**: PATH DUPLICATO: il GET /stats più ricco di verbali_noleggio_api.py (per stato, importi, health_score) è irraggiungibile.

### POST /api/verbali-noleggio/scansiona-fatture — estrai verbali dalle fatture 2022-2026
**Cosa fa**: scansione massiva fatture noleggiatori → popola `verbali_noleggio_completi`.
**Logica codice**: delega a `verbali_service.scansiona_e_salva_tutti_verbali()`.

### GET /api/verbali-noleggio/verbali-completi — lista da verbali_noleggio_completi
**Cosa fa**: verbali estratti dalle fatture con filtri anno/targa/stato_pagamento + statistiche.
**Logica codice**: legge `verbali_noleggio_completi` (COLLECTION_VERBALI importata da verbali_service — NON è la stessa costante locale, che punta a `verbali_noleggio`: nomi identici, collection diverse).
**Note**: le statistiche pagati/sospesi/da_verificare sono calcolate SENZA i filtri della query (numeri globali accanto a lista filtrata).

### GET /api/verbali-noleggio/operazioni-sospese — pagamenti non trovati in E/C
**Logica codice**: `verbali_service.get_operazioni_sospese()` (collection `operazioni_sospese`).

### POST /api/verbali-noleggio/riconcilia — riconcilia verbali con estratto conto
**Logica codice**: delega a `verbali_service.riconcilia_verbali()`.

### POST /api/verbali-noleggio/risolvi-sospeso — risolve operazione sospesa
**Cosa fa**: associa manualmente un riferimento sospeso a un movimento bancario.
**Logica codice**: `verbali_service.risolvi_operazione_sospesa(riferimento, movimento_id)`; parametri query.

### GET /api/verbali-noleggio/dettaglio/{numero_verbale} — dettaglio arricchito
**Cosa fa**: verbale + info veicolo + fattura + movimento banca + lista PDF disponibili (senza binari).
**Logica codice**: cerca in `verbali_noleggio_completi` poi fallback `verbali_noleggio` (anche numero_verbale_old); join manuali su `veicoli_noleggio`, `invoices`, `prima_nota_banca`.
**Note**: PATH DUPLICATO con l'api (`:path`); questa versione risponde per i numeri senza slash. USATO da DettaglioVerbale.jsx.

### GET /api/verbali-noleggio/tutti-verbali — vista unificata fatture+posta
**Cosa fa**: unisce `verbali_noleggio_completi` (da fatture) e `verbali_noleggio` (da posta) in 3 bucket: con fattura e PDF / con fattura senza PDF / con PDF senza fattura.
**Logica codice**: due `find` da 1000 + merge per numero_verbale; carica pdf_allegati in risposta (pesante).

### POST /api/verbali-noleggio/unifica-verbali — unifica PDF posta → completi
**Cosa fa (dichiarato)**: dovrebbe copiare i PDF di `verbali_noleggio` dentro `verbali_noleggio_completi`.
**Logica codice**: FUNZIONE TRONCATA/MORTA: il loop legge i verbali con PDF ma il corpo si ferma a `continue`; `aggiornati`/`non_trovati` mai usati, nessuna scrittura, ritorna `null`.
**Note**: BUG/codice incompleto — il docstring mente: l'endpoint non fa nulla.

### POST /api/verbali-noleggio/classifica-verbali-posta — classifica aziendale/privato
**Cosa fa**: per ogni verbale dalla posta determina AZIENDALE (targa nei veicoli gestiti) / PRIVATO / SCONOSCIUTO.
**Logica codice**: delega a `verbali_classificazione.processa_verbali_posta()` (collection `verbali_attesa_fattura`, `verbali_privati`).

### GET /api/verbali-noleggio/verbali-attesa-fattura — aziendali in attesa fattura
**Logica codice**: `get_verbali_attesa()` raggruppati per stato in_attesa_fattura/da_verificare/fatturato.

### GET /api/verbali-noleggio/verbali-privati — verbali non aziendali
**Logica codice**: `get_verbali_privati()`.

### POST /api/verbali-noleggio/verifica-nuove-fatture — match nuove fatture↔verbali in attesa
**Cosa fa**: da chiamare dopo un import fatture per associare automaticamente i verbali in attesa.
**Logica codice**: `verifica_nuove_fatture_per_verbali()`.

### POST /api/verbali-noleggio/riclassifica-verbale — riclassifica manuale
**Cosa fa**: forza classificazione "aziendale"/"privato" (+ targa opzionale) su un verbale.
**Logica codice**: valida classificazione; `riclassifica_verbale(...)`; parametri query.

### verbali_noleggio_api.py

### GET /api/verbali-noleggio/dettaglio/{numero_verbale:path} — dettaglio (numeri con slash)
**Cosa fa**: dettaglio verbale con ricerca multi-formato (id/numero/old/regex case-insensitive), arricchito con driver, veicolo e fattura per targa.
**Logica codice**: `verbali_noleggio` poi `verbali_noleggio_completi`; driver da **`employees`** (collection AppDipendenti, NON `dipendenti`); se manca fattura la cerca per targa in `invoices` (regex su descrizione/xml_raw); costruisce `pdf_disponibili`; rimuove i base64.
**Note**: raggiunto solo per numeri con slash (es. S/2259) per la collisione col router precedente. Lookup driver su `employees` incoerente col resto (dipendenti). La regex `^{numero_clean}$` non è escaped.

### GET /api/verbali-noleggio/lista — lista con filtri
**Logica codice**: `find` su `verbali_noleggio` con filtri anno (regex su data/data_verbale/anno), stato, driver_id; skip/limit + total.

### GET /api/verbali-noleggio/pdf/{numero_verbale} (api) — PDF verbale
**Note**: IRRAGGIUNGIBILE (duplicato del path in verbali_noleggio.py, registrato dopo). Logica pressoché identica (in più cerca per `id`).

### POST /api/verbali-noleggio/scarica-posta — placeholder
**Cosa fa**: ritorna `{"message": "Funzionalità in sviluppo", "status": "pending"}`. Nessuna logica.
**Note**: STUB. È però chiamato da DettaglioVerbale.jsx:422 — il bottone nella UI non fa nulla di reale.

### GET /api/verbali-noleggio/alert-pagamenti — verbali senza pagamento
**Cosa fa**: elenca i verbali non pagati/riconciliati con azione richiesta (upload bollettino / verifica importo) e totale da pagare.
**Logica codice**: `find` stato ∉ [pagato, riconciliato], senza binari; costruzione messaggi in Python.

### POST /api/verbali-noleggio/{verbale_id}/upload-quietanza — upload quietanza manuale
**Cosa fa**: carica quietanza/bollettino, marca il verbale pagato e genera la TRATTENUTA per il dipendente.
**Logica codice**: `$set stato=pagato, quietanza_pdf/filename, importo_pagato, metodo`; se c'è driver crea nota in `note_presenze_consulente` (tipo trattenuta_verbale, mese successivo, evidenza per il consulente del lavoro) e copia in `trattenute_dipendenti` (stato da_applicare).
**Note**: snodo del flusso "verbale → trattenuta dipendente in busta".

### GET /api/verbali-noleggio/note-consulente — note per consulente del lavoro
**Cosa fa**: elenco note presenze (incluse trattenute verbali) con totale importi e contatore non inviate.
**Logica codice**: `find` su `note_presenze_consulente` filtrando anno/mese.

### PUT /api/verbali-noleggio/{verbale_id} — aggiorna verbale
**Logica codice**: `$set` generico (rimuove _id/id) cercando per id o numero_verbale; 404 se non matcha.

### POST /api/verbali-noleggio/associa-driver — associa driver manuale
**Cosa fa**: collega un dipendente come driver del verbale (`associazione_manuale=true`).
**Logica codice**: valida il driver su **`employees`** (di nuovo collection AppDipendenti); `$set driver_id/driver` sul verbale.

### GET /api/verbali-noleggio/stats (api) — statistiche estese
**Note**: IRRAGGIUNGIBILE (shadowed dal /stats di verbali_noleggio.py). Conteneva per-stato, importo totale e health_score driver.

### POST /api/verbali-noleggio/{verbale_id}/cerca-pagamento — ricerca pagamento multi-fonte
**Cosa fa**: cerca in cascata PayPal → Gmail → estratto conto il pagamento del verbale e, se trovato, lo applica (stato pagato, psp, iuv, paypal_transaction_id, pdf ricevuta).
**Logica codice**: `verbali_pagamento_finder.trova_pagamento_verbale` + `applica_pagamento_a_verbale`.
**Note**: VIVO — usato da DettaglioVerbale.jsx:571.

### GET /api/verbali-noleggio/{verbale_id}/ricevuta-pdf — download ricevuta pagamento
**Cosa fa**: serve il file PDF puntato da `pdf_ricevuta_path`.
**Logica codice**: `os.path.realpath` e obbligo che il path stia sotto `/tmp/uploads/`; FileResponse.
**Note**: il commento di sicurezza dice "/app/uploads/" ma il check reale è "/tmp/uploads/" (path effimero: le ricevute spariscono a ogni deploy). VIVO (DettaglioVerbale.jsx:523).

### POST /api/verbali-noleggio/scan-gmail — scan Gmail verbali (Trigger A)
**Cosa fa**: scansiona Gmail degli ultimi N giorni per PEC verbali CdS inoltrate.
**Logica codice**: `verbali_gmail_scanner.scan_gmail_verbali(db, days_back)`.

### POST /api/verbali-noleggio/riconcilia-completo — pipeline completa
**Cosa fa**: scan Gmail 7gg + collega verbali↔fatture ARVAL/Leasys + ricerca pagamenti PagoPA per tutti i verbali non riconciliati.
**Logica codice**: `scan_gmail_verbali` → `verbali_fattura_linker.collega_verbali_a_fatture` → loop `trova_pagamento_verbale`/`applica_pagamento_a_verbale` su stati notificato/da_verificare/notifica_attesa con `riconciliato_paypal != true`.

### POST /api/verbali-noleggio/bulk-assegna-pagamento — assegnazione massiva pagamenti
**Cosa fa**: da tabella/CSV utente assegna pagamento PayPal a più verbali (iuv, transaction_id, importo, psp) e denormalizza su paypal_transactions.
**Logica codice**: per item `$set` su `verbali_noleggio` (stato pagato, riconciliato_paypal, paypal_transaction_id) e su `paypal_transactions` (iuv, numero_verbale_collegato, targa_collegata).

---

## verbali_riconciliazione.py (prefisso /api/verbali-riconciliazione — 25 endpoint)

Riconciliazione completa verbale ↔ fattura noleggiatore ↔ pagamento ↔ veicolo ↔ driver, con scan
email/PagoPA e prima nota. Vivi dal frontend (VerbaliRiconciliazione.jsx): /dashboard, /lista,
/scan-fatture-verbali, /collega-driver-massivo, /riconcilia/{n}. Collection principale `verbali_noleggio`.

### GET /api/verbali-riconciliazione/dashboard — dashboard stati
**Cosa fa**: conteggi/importi per stato, verbali da riconciliare, ultimi 5.
**Logica codice**: aggregate con `$project` per non caricare i PDF; count "da riconciliare" (fattura senza pagamento, pagato senza fattura, salvato).
**Note**: VIVO (VerbaliRiconciliazione.jsx:47).

### GET /api/verbali-riconciliazione/lista — lista con filtri
**Cosa fa**: verbali filtrati per stato/targa/da_riconciliare, ordinamento configurabile, proiezione senza binari.
**Logica codice**: normalizza driver_nome/fattura_numero dai campi legacy.
**Note**: VIVO (jsx:68).

### POST /api/verbali-riconciliazione/associa-fattura — associazione manuale verbale↔fattura
**Cosa fa**: collega (o crea) il verbale alla fattura del noleggiatore; se già pagato diventa riconciliato.
**Logica codice**: find/insert su `verbali_noleggio`; `$set fattura_id/numero, targa, driver_id, importo_notifica`.

### POST /api/verbali-riconciliazione/registra-pagamento — registra pagamento da E/C
**Cosa fa**: due scenari: pago prima (crea verbale stato pagato) o fattura già presente (→ riconciliato).
**Logica codice**: `$set importo/data_pagamento/pagamento_id` + transizione stato.

### POST /api/verbali-riconciliazione/scan-fatture-verbali — scan massivo fatture
**Cosa fa**: cerca numeri verbale (`[AB]\d{8,12}` + pattern testuali) in tutti i campi delle fatture noleggiatori e crea/aggiorna le associazioni.
**Logica codice**: fino a 5000 `invoices` (regex su supplier/descrizione/body/note/oggetto + items); per match crea o aggiorna verbale con fattura_id (=str(_id) Mongo), stato fattura_ricevuta o riconciliato.
**Note**: VIVO (jsx:95). Qui `fattura_id` è l'ObjectId stringato, altrove è l'uuid `id` — identificatori fattura misti nel dataset.

### POST /api/verbali-riconciliazione/riconcilia/{numero_verbale} — riconciliazione singola
**Cosa fa**: cerca fattura (regex sul numero verbale nei campi fattura), targa (da verbali_noleggio_completi), veicolo e driver; aggiorna stato.
**Logica codice**: join su `invoices`, `verbali_noleggio_completi`, `veicoli_noleggio`, `dipendenti`.
**Note**: VIVO (jsx:128). BUG POTENZIALE: il lookup driver fa `dipendenti.find_one({"_id": ObjectId(driver_id)})` ma `driver_id` è quasi sempre un uuid stringa → `InvalidId` non gestita → 500 quando il veicolo ha driver_id uuid.

### POST /api/verbali-riconciliazione/collega-driver-massivo — driver matching multi-strategia
**Cosa fa**: per i verbali con targa ma senza driver prova 5 strategie: veicolo → storico assegnazioni (alla data violazione) → contratti noleggio → dipendente con targa assegnata → cognome nella descrizione.
**Logica codice**: query su `veicoli_noleggio`, `storico_assegnazioni_veicoli`, `contratti_noleggio`, `dipendenti`; `$set driver_id/driver_nome/driver`; report per strategia.
**Note**: VIVO (jsx:113). La strategia 4 esegue due volte quasi la stessa query (secondo find_one ridondante).

### GET /api/verbali-riconciliazione/per-driver/{driver_id} — verbali di un driver
**Logica codice**: `find` per driver_id CON i PDF inclusi (nessuna proiezione — risposta potenzialmente pesante); totali verbali/notifiche.
**Note**: quasi-duplicato di /per-dipendente/{driver_id} (sotto), che è più completo.

### GET /api/verbali-riconciliazione/per-veicolo/{targa} — verbali di un veicolo
**Logica codice**: `find` per targa upper, senza proiezione (PDF inclusi).
**Note**: quasi-duplicato di /per-targa/{targa}.

### POST /api/verbali-riconciliazione/automazione-completa — automazione su tutti i verbali
**Cosa fa**: per ogni verbale esegue `associa_verbale_completo`: targa (anche da descrizione), veicolo, contratto, codice cliente, driver, dati fattura, ricalcolo stato (riconciliato/pagato/fattura_ricevuta/identificato).
**Logica codice**: helper condiviso con join su completi/veicoli/dipendenti/invoices; report driver/veicoli/contratti associati.

### POST /api/verbali-riconciliazione/crea-prima-nota-verbale/{numero_verbale} — prima nota da verbale
**Cosa fa**: crea movimento di uscita in `prima_nota_cassa` (categoria Verbali/Multe) per un verbale con importo.
**Logica codice**: skip se movimento già presente; `$set movimento_cassa_id` + stato pagato/riconciliato.
**Note**: sempre in CASSA anche se pagato via PayPal/bonifico (il docstring cita anche prima_nota_banca, mai usata).

### GET /api/verbali-riconciliazione/pending-status — cose da completare
**Cosa fa**: conteggi verbali senza quietanza / senza PDF / senza fattura / senza driver + priorità scan.
**Logica codice**: 5 count su `verbali_noleggio`.

### GET /api/verbali-riconciliazione/per-dipendente/{driver_id} — verbali dipendente (per HR)
**Cosa fa**: verbali del dipendente (fallback per nome se driver_id non matcha) con split da_pagare/pagati e totali.
**Logica codice**: `find` senza pdf_data; fallback lookup nome su `dipendenti`; flag has_pdf.

### GET /api/verbali-riconciliazione/per-targa/{targa} — verbali per targa
**Logica codice**: `find` senza pdf_data + totale importi.

### GET /api/verbali-riconciliazione/{numero_verbale}/pdf — PDF binario del verbale
**Cosa fa**: serve il PDF inline (da `pdf_data` base64 o primo elemento `pdf_allegati`).
**Logica codice**: proiezione solo campi pdf; decodifica base64; Response application/pdf.

### POST /api/verbali-riconciliazione/registra-quietanza/{numero_verbale} — registra quietanza
**Cosa fa**: marca quietanza ricevuta (+ metodo, riferimento, pdf) e stato pagato/riconciliato.
**Logica codice**: `$set quietanza_ricevuta, stato_pagamento=pagato, quietanza_pdf...`.

### POST /api/verbali-riconciliazione/scan-email — scan email con priorità
**Cosa fa**: fase 1 completa i verbali sospesi (quietanze/PDF mancanti), fase 2 aggiunge nuovi verbali; default 365 giorni.
**Logica codice**: delega a `verbali_email_scanner.esegui_scan_verbali_email(db, days_back)`.

### POST /api/verbali-riconciliazione/scan-email-storico — scan dal 2018
**Logica codice**: stesso scanner con days_back calcolato dal 2018-01-01 (operazione lunga).

### POST /api/verbali-riconciliazione/scan-verbale/{numero_verbale} — scan mirato
**Cosa fa**: cerca in email quietanza e PDF per un singolo verbale.
**Logica codice**: `VerbaliEmailScanner.connect()` + `cerca_quietanza_per_verbale` + `cerca_pdf_per_verbale`.

### POST /api/verbali-riconciliazione/riconcilia-estratto-conto-paypal — import CSV PayPal
**Cosa fa**: legge il CSV PayPal e riconcilia i verbali citati in descrizione (o, per righe "comune", i verbali pagati in quella data).
**Logica codice**: per numero verbale → `$set stato=riconciliato + movimento_paypal`; per fallback "comune" aggiorna FINO A 10 verbali con `pagamento.data` uguale alla data riga.
**Note**: fallback aggressivo: una riga "Comune di ..." può marcare riconciliati più verbali senza controllo importo.

### GET /api/verbali-riconciliazione/dettaglio-completo/{numero_verbale} — checklist riconciliazione
**Cosa fa**: verbale + checklist a 8 voci (pdf, targa, driver, veicolo, pagamento, quietanza, fattura, E/C) con % completamento e "prossimo passo".
**Logica codice**: `find_one` senza _id; `_get_prossimo_passo` sulla checklist; esclude pdf_data.

### GET /api/verbali-riconciliazione/scheduler-status — stato scheduler scan
**Cosa fa**: elenca i job APScheduler e individua quello dei verbali (scan orario automatico).
**Logica codice**: `app.scheduler.scheduler.get_jobs()`; fallback errore se scheduler assente.

### POST /api/verbali-riconciliazione/scan-pagopa — scan quietanze PagoPA
**Cosa fa**: scansiona Gmail dai 3 mittenti ufficiali PagoPA/PartenoPay/PL Napoli, trova il numero verbale nel corpo, salva PDF (o lo genera dal corpo) e aggiorna il verbale.
**Logica codice**: delega a `pagopa_scanner.scan_pagopa_email(db, days_back)` (scrive `quietanze_verbali`).

### GET /api/verbali-riconciliazione/quietanze-verbale/{numero_verbale} — quietanze del verbale
**Logica codice**: `find` su `quietanze_verbali` per verbale_numero upper, senza pdf_base64.

### GET /api/verbali-riconciliazione/quietanze-verbale/{numero_verbale}/pdf — PDF quietanza
**Logica codice**: `find_one` con pdf_base64; decode e Response inline.

---

## noleggio.py (prefisso /api/noleggio — 12 endpoint)

Flotta a noleggio: aggrega i costi dai XML fatture (servizio `scan_fatture_noleggio` +
`categorizza_spesa`) con i dati salvati in `veicoli_noleggio` e i verbali. Vivo: NoleggioAuto.jsx,
VeicoliHub.jsx, Dashboard.jsx usano /veicoli, /drivers, /fornitori, ecc.

**Aggiornamento**: risolte le anomalie sotto segnalate — PUT /veicoli/{targa} ora accetta anche
canone_mensile/anno_immatricolazione/alimentazione/potenza_kw/cilindrata (prima scartati
silenziosamente); rimossi i 4 endpoint morti /migra-dati /persisti-anno /costi-persistiti
/statistiche-persistenza e il file data_persistence.py (costi_noleggio/audit_noleggio, zero
chiamanti, duplicava i dati già calcolati live da questo router); rimosso
`app/routers/veicoli.py` (prefisso legacy /api/noleggio-auto, stesso schema incompatibile su
veicoli_noleggio, zero chiamanti); i verbali mostrati per veicolo ora uniscono
`verbali_noleggio` (posta) E `verbali_noleggio_completi` (fatture) invece di solo il primo;
nuovo endpoint `GET /veicoli/{targa}/completo` per la vista singola aggregata. Il modulo verbali
(verbali_noleggio.py, verbali_noleggio_api.py, verbali_riconciliazione.py — anomalie elencate
sotto) non è stato toccato in questo intervento.

### GET /api/noleggio/veicoli — flotta con costi per categoria
**Cosa fa**: per ogni veicolo somma canoni/pedaggio/verbali/bollo/extra/riparazioni dell'anno da fatture + verbali dal DB.
**Logica codice**: `scan_fatture_noleggio(anno)`; assegna le fatture senza targa (es. LeasePlan) al veicolo del fornitore (preferendo non presenti o con contratto scaduto); merge con `veicoli_noleggio` (driver, date); arricchisce con `verbali_noleggio` per targa (dedup per numero_verbale); statistiche aggregate.
**Note**: VIVO (NoleggioAuto.jsx, VeicoliHub.jsx, Dashboard.jsx). IVA verbali/bollo gestita a 0, resto forfettario 22%.

### GET /api/noleggio/export-pdf-costi — PDF costi per commercialista
**Cosa fa**: PDF riepilogo per categoria + dettaglio per veicolo (anno corrente di default).
**Logica codice**: variante semplificata della logica di /veicoli (senza assegnazione fatture senza targa) + reportlab.
**Note**: i verbali sono sommati SENZA filtro anno (tutti gli anni entrano nel PDF dell'anno richiesto).

### GET /api/noleggio/fatture-non-associate — fatture noleggio senza targa
**Cosa fa**: elenco fatture di fornitori noleggio prive di targa da associare manualmente (caso LeasePlan).
**Logica codice**: `scan_fatture_noleggio` → formatta le `fatture_senza_targa`; il filtro sui fornitori con veicoli è calcolato ma NON applicato (ritorna tutte).

### GET /api/noleggio/fornitori — fornitori noleggio supportati
**Cosa fa**: lista statica ALD/ARVAL/Leasys/LeasePlan con flag targa/contratto in fattura.
**Logica codice**: nessun DB.

### GET /api/noleggio/drivers — dipendenti come driver
**Cosa fa**: id + nome_completo di tutti i dipendenti per la select driver.
**Logica codice**: `find` su `dipendenti` (nome+cognome).

### POST /api/noleggio/veicoli — crea veicolo
**Logica codice**: valida targa; 409 se esiste; insert su `veicoli_noleggio` (driver, fornitore_piva, canone, date).

### PUT /api/noleggio/veicoli/{targa} — aggiorna/crea veicolo (upsert)
**Cosa fa**: aggiorna driver, date noleggio, marca/modello/contratto/centro fatturazione.
**Logica codice**: se `driver_id` valida il dipendente su `dipendenti` e deriva `driver` nome; upsert con `$setOnInsert id/created_at`.

### DELETE /api/noleggio/veicoli/{targa} — rimuovi veicolo dalla gestione
**Logica codice**: `delete_one` su `veicoli_noleggio` (non tocca le fatture).

### POST /api/noleggio/associa-fornitore — associa fornitore a targa
**Cosa fa**: collega manualmente targa↔fornitore (necessario per LeasePlan senza targa in fattura).
**Logica codice**: valida P.IVA contro FORNITORI_NOLEGGIO; upsert veicolo con fornitore.

### POST /api/noleggio/migra-dati — migrazione storica costi
**Cosa fa**: scansiona tutti gli anni 2018-2026 e persiste veicoli/costi in Mongo (additivo, non distruttivo).
**Logica codice**: `data_persistence.migra_dati_esistenti(db)`.

### POST /api/noleggio/persisti-anno/{anno} — persisti un anno
**Logica codice**: valida anno 2018-2030; `scan_fatture_noleggio` + `persisti_dati_da_fatture`.

### GET /api/noleggio/costi-persistiti/{targa} — costi salvati per veicolo
**Cosa fa**: costi persistiti (fonte di verità per verbali/bolli/riparazioni) raggruppati per tipo.
**Logica codice**: `recupera_costi_veicolo(db, targa, anno, tipo_costo)`.

### GET /api/noleggio/statistiche-persistenza — integrità dati persistiti
**Logica codice**: count su COLLECTION_VEICOLI/COSTI/AUDIT + aggregate per tipo_costo (esclusi eliminati).

### GET /api/noleggio/verbali-dipendente — verbali di un dipendente (tab HR)
**Cosa fa**: verbali per driver_id o driver_cf con contatori pagati/da pagare e importo totale.
**Logica codice**: `find` su `verbali_noleggio` con `$or`, senza binari.

---

## veicoli.py (prefisso interno /api/noleggio-auto — 6 endpoint)

CRUD minimale sulla stessa collection `veicoli_noleggio` usata da noleggio.py, ma con schema diverso
(stato attivo/manutenzione/fermo, data_scadenza_noleggio). Nessuna chiamata dal frontend
(main.jsx redirige /noleggio-auto → /noleggio): modulo LEGACY sostituito da /api/noleggio.

### GET /api/noleggio-auto/veicoli — lista veicoli
**Logica codice**: `find` su `veicoli_noleggio`; fallback su collection `veicoli` se vuota.

### GET /api/noleggio-auto/veicoli/{targa} — dettaglio
**Logica codice**: `find_one` per targa upper; 404 se assente.

### POST /api/noleggio-auto/veicoli — crea
**Logica codice**: 400 se targa esistente; insert con stato default "attivo".
**Note**: scrive nella stessa collection di noleggio.py ma senza id/driver/fornitore — documenti eterogenei.

### PUT /api/noleggio-auto/veicoli/{targa} — aggiorna
**Logica codice**: `$set` dei soli campi non-None (marca/modello/anno/scadenza/note/stato).

### DELETE /api/noleggio-auto/veicoli/{targa} — elimina
**Logica codice**: `delete_one`; 404 se assente.

### GET /api/noleggio-auto/stats — conteggi per stato
**Logica codice**: 4 count (totale/attivi/manutenzione/fermi).
**Note**: conta sul campo `stato` che i veicoli creati via /api/noleggio non hanno.

---

## alert_verbali.py (prefisso /api/alert-verbali — 2 endpoint)

Alert sul beneficio di riduzione 30% dei verbali CdS (pagamento entro 5 giorni dalla notifica).
Nessun riferimento nel frontend attuale: probabile consumo da widget/notifiche o scheduler.

### GET /api/alert-verbali/scadenza-imminente — verbali vicini alla scadenza -30%
**Cosa fa**: verbali notificati/da verificare non pagati con `data_scadenza_riduzione_30` entro N giorni (default 5); calcola importo ridotto (×0.70), giorni mancanti e urgenza critica/alta/media.
**Logica codice**: `find` su `verbali_noleggio` (senza binari) ordinato per scadenza; parsing date ISO in Python.

### GET /api/alert-verbali/contatore — contatori alert
**Cosa fa**: numero verbali in scadenza 5gg e in attesa notifica.
**Logica codice**: 2 count su `verbali_noleggio`.

---

## adr.py (prefisso /api/adr — 7 endpoint)

Definizione Agevolata / Rottamazione cartelle esattoriali: soggetti per codice fiscale con elenco
cartelle (codici a 20 cifre), scarico documenti AdER da email. Collection `adr_definizione_agevolata`.
Nessun riferimento nel frontend: modulo di servizio/backoffice.

### GET /api/adr/soggetti — lista soggetti
**Logica codice**: `find` senza `pdf_allegati`; _id stringato.

### GET /api/adr/soggetti/{codice_fiscale} — dettaglio soggetto
**Logica codice**: `find_one` per CF upper (INCLUSI i pdf_allegati base64 — risposta pesante); 404 se assente.

### POST /api/adr/soggetti — crea soggetto
**Cosa fa**: crea soggetto con cartelle, totali e piano rate.
**Logica codice**: 400 se CF esistente; insert con pdf_allegati vuoto.

### POST /api/adr/soggetti/{codice_fiscale}/cartelle — aggiungi cartella
**Logica codice**: `$push cartelle` + data_modifica; 404 se soggetto assente.

### POST /api/adr/scarica-da-email — scarica documenti AdER da email
**Cosa fa**: cerca email con keyword (AdER, rottamazione, definizione agevolata, cartella di pagamento), estrae codici cartella (20 cifre) e CF/P.IVA dal testo, salva i PDF sul soggetto (upsert).
**Logica codice**: IMAP multi-keyword; `$push pdf_allegati` (base64) + `$addToSet cartelle` stato da_verificare + `$setOnInsert` anagrafica vuota.
**Note**: nessun controllo duplicati sui PDF: ri-esecuzioni accumulano allegati identici sul soggetto.

### GET /api/adr/stats — statistiche
**Logica codice**: count soggetti + aggregate `$size` sulle cartelle.

### POST /api/adr/auto-ripara — ricalcolo totali
**Cosa fa**: per ogni soggetto ricalcola totale_originale/totale_agevolato dalle cartelle e corregge se diversi.
**Logica codice**: loop cursor + `$set` condizionale; report correzioni.

---

## Anomalie trasversali (riepilogo)

1. **Rotte duplicate/oscurate**: `/api/dipendenti/contratti` (GET, 2 definizioni identiche);
   `/api/verbali-noleggio/stats`, `/pdf/{n}`, `/dettaglio/{n}` definite in entrambi i router verbali
   (vince verbali_noleggio.py); `/per-driver` vs `/per-dipendente` e `/per-veicolo` vs `/per-targa`
   in verbali_riconciliazione.py.
2. **Codice morto**: POST `/api/verbali-noleggio/unifica-verbali` è una funzione troncata che non fa
   nulla (ritorna null); closure `salva_tributi` in f24_parser mai chiamata; POST
   `/api/verbali-noleggio/scarica-posta` è uno stub "in sviluppo" ma è collegato a un bottone della UI.
3. **Doppia anagrafica**: la maggior parte dei moduli usa `dipendenti` (Collections.EMPLOYEES) ma
   import-libro-unico scrive l'anagrafica su `employees` (condivisa AppDipendenti) e
   verbali_noleggio_api cerca i driver su `employees` — collegamenti TFR/prima nota saltano se il CF
   non esiste in `dipendenti`. NON eliminare `employees`/`cedolini` (condivise con AppDipendenti).
4. **Path effimeri /tmp**: buste paga (`/tmp/documents/buste_paga`), payslips TFR (`/tmp/uploads/paghe`,
   docstring dice /app/uploads), ricevute verbali (`/tmp/uploads/`, commento dice /app/uploads):
   su Render i file spariscono a ogni deploy.
5. **Rischi dati**: `scarica-tutti` sovrascrive i campi di associazione dei verbali già arricchiti;
   riconcilia/{n} può andare in 500 con driver_id uuid (ObjectId non gestito); fallback "comune" del
   CSV PayPal riconcilia fino a 10 verbali per riga senza check importo; POST /tfr/accantonamento non
   blocca doppioni per anno; riconciliazione manuale distinte BPM prende la prima busta senza filtro periodo.
6. **Endpoint vivi confermati dal frontend**: GET /api/dipendenti (InserimentoRapido, VerbaliRiconciliazione);
   GET /api/tfr/riepilogo-aziendale (GestioneCespiti); GET /api/paghe/buste-paga e /distinte-f24 (Dashboard);
   /api/noleggio/* (NoleggioAuto, VeicoliHub, Dashboard); /api/verbali-noleggio dettaglio/pdf/scarica-posta/
   ricevuta-pdf/cerca-pagamento (DettaglioVerbale, PaypalTransactionDetailModal); /api/verbali-riconciliazione
   dashboard/lista/scan-fatture-verbali/collega-driver-massivo/riconcilia (VerbaliRiconciliazione).
   Senza riferimenti frontend: /api/inps, /api/adr, /api/alert-verbali, /api/noleggio-auto e ~50 dei 52
   endpoint di /api/dipendenti (orfani o duplicati di AppDipendenti).

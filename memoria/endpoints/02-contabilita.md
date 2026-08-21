# Endpoint Contabilità — Modulo 02

<!-- gestionalecloud-doc
status: reference
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!IMPORTANT]
> Documento di riferimento del dominio. Per persistenza e cutover vale l'architettura Drive-only descritta nei documenti correnti; eventuali nomi Mongo/collection restano compatibilità o contesto storico.

Documentazione generata dalla lettura diretta del codice (luglio 2026). Prefissi reali da `app/router_registry.py`.

Convenzioni ricorrenti:
- `invoices` = SOLO fatture passive ricevute (doppio schema EN/IT: `total_amount`/`importo_totale`, `invoice_date`/`data_documento`, `iva`/`importo_iva`, `supplier_name`/`cedente_denominazione`). Note credito = `tipo_documento` TD04/TD08.
- `corrispettivi` = unica fonte ricavi (campi `totale`, `totale_imponibile`, `totale_iva`, `pagato_contante`/`pagato_elettronico`).
- `prima_nota_cassa` / `prima_nota_banca`: movimenti con `tipo` entrata/uscita e `importo` positivo.
- Esistono DUE motori in partita doppia paralleli: (a) `prima_nota_righe` + header in `prima_nota_cassa` (accounting_engine.py, contabilita_italiana.py, fiscalita_italiana.py — conti Odoo/CEE 6 cifre); (b) `movimenti_contabili` + saldi su `piano_conti` (piano_conti.py, contabilita_avanzata.py — conti italiani GG.SS.CC). Non comunicano tra loro.

---

## accounting_main.py (/api/accounting)
Report contabili sulle fatture passive via `AccountingService`/`InvoiceRepository` (collezione `invoices`, filtrata per `user_id` dell'utente autenticato). Tutti gli endpoint richiedono JWT (`get_current_user`).

### GET /api/accounting/monthly/{month_year} — riepilogo mensile
**Cosa fa**: totali acquisti del mese (formato MM-YYYY).
**Logica codice**: legge `invoices` via `AccountingService.get_monthly_summary`; ritorna n. fatture, totale, imponibile, IVA del mese.

### GET /api/accounting/annual/{year} — riepilogo annuale
**Cosa fa**: riepilogo acquisti dell'anno con breakdown mensile e top fornitori.
**Logica codice**: `AccountingService.get_annual_summary` su `invoices` (anno 2000–2100 validato via Path).

### GET /api/accounting/payments — pagato vs non pagato
**Cosa fa**: riepilogo stato pagamenti fatture (pagato/non pagato, % e distribuzione per metodo).
**Logica codice**: `AccountingService.get_payment_summary` su `invoices`; filtri opzionali `date_from`/`date_to` via `date_range_params`.

### GET /api/accounting/vat/{month_year} — riepilogo IVA per aliquota
**Cosa fa**: IVA del mese raggruppata per aliquota (imponibile e imposta per aliquota).
**Logica codice**: `AccountingService.get_vat_summary` su `invoices`. Solo lato acquisti; non tocca corrispettivi.

### GET /api/accounting/supplier-balance/{supplier_vat} — saldo fornitore
**Cosa fa**: esposizione verso un singolo fornitore (totale, pagato, non pagato, elenco fatture aperte).
**Logica codice**: `AccountingService.get_supplier_balance` su `invoices` per `supplier_vat`.

### GET /api/accounting/dashboard — dashboard contabile
**Cosa fa**: overview mese corrente + stato pagamenti.
**Logica codice**: compone `get_monthly_summary(mese corrente)` + `get_payment_summary`; aggiunge `generated_at`.

### POST /api/accounting/auto-categorize/invoice/{invoice_id} — suggerimento categorie
**Cosa fa**: suggerisce un conto per ogni prodotto di una fattura in base a keyword.
**Logica codice**: legge la fattura via `invoice_repo.find_by_id`, itera `invoice["products"]`, matcha un dizionario keyword→codice hardcoded (es. "energia"→4.2.03); fallback 3.1.01 con confidenza bassa. Non scrive nulla.
**Note**: legacy — usa il campo `products` e codici conto 4.2.x/3.1.x che NON esistono nel piano dei conti reale (05.xx). Le fatture reali usano `linee`; su di esse la funzione trova 0 prodotti.

## accounting_extended.py (/api/accounting)
Estensione minimale: piano conti + report. Tre endpoint su quattro sono STUB che ritornano zeri.

### GET /api/accounting/chart-of-accounts — piano dei conti
**Cosa fa**: elenca fino a 500 conti.
**Logica codice**: `db["chart_of_accounts"].find({})`.
**Note**: legge la collezione `chart_of_accounts`, ma `Collections.CHART_OF_ACCOUNTS` punta a `piano_conti`: probabilmente ritorna sempre lista vuota (collezione mai popolata altrove).

### POST /api/accounting/chart-of-accounts/initialize — init piano conti (stub)
**Cosa fa**: dichiara di inizializzare il piano dei conti ma non fa nulla.
**Logica codice**: ritorna solo `{"message": ...}`. **Note**: stub, docstring mente.

### GET /api/accounting/reports/balance-sheet — stato patrimoniale (stub)
**Cosa fa**: ritorna struttura assets/liabilities/equity tutta a 0.
**Note**: stub; il vero SP è in /api/bilancio/stato-patrimoniale.

### GET /api/accounting/reports/income-statement — conto economico (stub)
**Cosa fa**: ritorna revenue/expenses/net_income a 0. **Note**: stub.

### POST /api/accounting/reports/tax-simulation — simulazione imposte (stub)
**Cosa fa**: ritorna estimated_tax/taxable_income/deductions a 0. **Note**: stub; il calcolo reale è /api/contabilita/calcolo-imposte.

## accounting_engine.py (/api/accounting)
Motore in partita doppia "stile Odoo": header registrazioni in `prima_nota_cassa`, righe in `prima_nota_righe`, conti a 6 cifre (101000 Cassa … 590000). Nessuna autenticazione sugli endpoint.

### GET /api/accounting/status — stato motore
**Cosa fa**: conteggi diagnostici.
**Logica codice**: `count_documents` su `piano_conti` e `prima_nota_righe`.

### POST /api/accounting/init-default-accounts — crea conti predefiniti
**Cosa fa**: inserisce in `piano_conti` i ~40 conti DEFAULT_ACCOUNTS mancanti (codici 6 cifre, campo `tipo` Odoo).
**Logica codice**: `ensure_default_accounts`: per ogni conto verifica `codice` e inserisce con uuid.
**Note**: convive/collide col piano conti italiano GG.SS.CC creato da piano_conti.py nella STESSA collezione `piano_conti`.

### POST /api/accounting/journal-entry — registrazione contabile manuale
**Cosa fa**: crea una scrittura in partita doppia bilanciata (DARE=AVERE).
**Logica codice**: `validate_journal_entry` (bilanciamento ±0.01, ogni riga solo DARE o solo AVERE); scrive header in `prima_nota_cassa` (id, date, ref, journal_type, total_debit/credit, state=posted) e righe in `prima_nota_righe` (account_code, debit, credit, balance, partner, reconciled=False). `round_currency` con Decimal ROUND_HALF_UP.
**Note**: l'header finisce SEMPRE in `prima_nota_cassa` anche per scritture bank/purchase/sale; questi documenti header non hanno `tipo`/`importo` quindi non alterano i saldi cassa aggregati, ma inquinano i listing della prima nota.

### POST /api/accounting/invoice — fattura con scritture automatiche
**Cosa fa**: calcola totali dalle righe (IVA default 22%) e genera la scrittura secondo `move_type` (out_invoice, in_invoice, out_refund, in_refund), poi salva un documento di tracking.
**Logica codice**: `ensure_default_accounts`; costruisce JournalLine su conti fissi (110000/401000/210000 vendite; 501000/130000/201000 acquisti); chiama `create_journal_entry`; inserisce doc in `invoices` con schema Odoo (move_id, subtotal, amount_residual, payment_state=not_paid).
**Note**: RISCHIO — scrive in `invoices` con schema completamente diverso da quello reale EN/IT delle fatture passive: i documenti creati qui inquinano tutte le aggregazioni su `invoices` (mancano tipo_documento, invoice_date, ecc.).

### POST /api/accounting/payment — pagamento con riconciliazione
**Cosa fa**: registra incasso (DARE banca/cassa, AVERE crediti clienti) o pagamento (DARE debiti fornitori, AVERE banca/cassa) e chiude le fatture indicate.
**Logica codice**: conto 102000/101000 in base a `journal_type`; crea journal entry; per ogni `invoice_ids` scala `amount_residual` su `invoices` e imposta `payment_state` paid/partial fino a esaurimento importo.

### GET /api/accounting/trial-balance — bilancio di verifica
**Cosa fa**: saldo DARE/AVERE per conto.
**Logica codice**: aggregazione `$group` per `account_code` su `prima_nota_righe`; filtro per `anno` (regex su date) o range `date_from`/`date_to`; totali complessivi con sbilancio.

### GET /api/accounting/partner-ledger/{partner_id} — estratto conto partner
**Cosa fa**: movimenti e saldo progressivo di un cliente/fornitore.
**Logica codice**: find su `prima_nota_righe` per `partner_id` (opz. anno), calcolo `running_balance` in Python.

### GET /api/accounting/aged-receivable — scadenzario clienti
**Cosa fa**: crediti aperti per fasce di scadenza (non scaduto, 0-30, 31-60, 61-90, >90 gg).
**Logica codice**: find su `invoices` con `move_type=out_invoice` e `payment_state` in [not_paid, partial]; bucket su `due_date` vs oggi; somma `amount_residual`.
**Note**: opera solo sulle fatture create dal motore Odoo (campo `move_type`), non sulle fatture reali del gestionale.

### GET /api/accounting/aged-payable — scadenzario fornitori
**Cosa fa**: come aged-receivable ma su `move_type=in_invoice`.
**Logica codice**: identica a sopra, bucket per giorni di ritardo. **Note**: stessa limitazione (solo dati motore Odoo).

---

## accounting_engine_api.py (/api/accounting-engine)
Espone via REST il service `app/services/accounting_engine.py` (AccountingEngine, PIANO_DEI_CONTI, REGOLE_CONTABILI). Lavora principalmente sulla collezione `scritture_contabili` (terzo sistema di scritture, distinto da `prima_nota_righe` e `movimenti_contabili`).

### GET /api/accounting-engine/piano-conti — piano conti del motore
**Cosa fa**: ritorna il PIANO_DEI_CONTI hardcoded nel service (non il DB).
**Logica codice**: iterazione della costante; codice, nome, tipo (enum), descrizione.

### GET /api/accounting-engine/regole-contabili — regole DARE/AVERE
**Cosa fa**: elenca le REGOLE_CONTABILI hardcoded (tipo operazione → conto dare/avere, prima nota corretta, tipo movimento).

### POST /api/accounting-engine/valida-operazione — validazione preventiva
**Cosa fa**: valida un'operazione di prima nota prima dell'inserimento e suggerisce la regola contabile.
**Logica codice**: `valida_operazione_prima_nota(data, prima_nota)` + `engine.determina_tipo_operazione(descrizione, importo)`; ritorna errori, tipo rilevato, prima nota corretta e suggerimento dare/avere. Nessuna scrittura DB.

### POST /api/accounting-engine/analizza-prima-nota/{tipo} — analisi errori/duplicati
**Cosa fa**: analizza `prima_nota_cassa` o `prima_nota_banca` cercando errori e duplicati.
**Logica codice**: valida tipo ∈ {cassa, banca}; carica fino a 5000 movimenti; `engine.analizza_prima_nota(movimenti, tipo)`; sola lettura.

### POST /api/accounting-engine/correggi-errori-cassa — bonifica automatica cassa
**Cosa fa**: 1) sposta in `prima_nota_banca` i movimenti cassa con keyword bancarie (BONIFICO, SEPA, RID, F24, …) marcandoli `source=migrato_da_cassa`; 2) trasforma i "rimborsi" da uscita a entrata; 3) elimina i duplicati (stessa data+importo+descrizione[:50], tiene il primo).
**Logica codice**: regex su `descrizione`, insert/delete su `prima_nota_cassa`/`prima_nota_banca`, pipeline `$group` per i duplicati; ritorna contatori e dettagli.
**Note**: operazione distruttiva (delete definitive) senza dry-run né backup.

### GET /api/accounting-engine/bilancio-verifica — bilancio di verifica da scritture
**Cosa fa**: bilancio di verifica aggregando `scritture_contabili` (opz. filtro `anno` su `data_documento`).
**Logica codice**: carica fino a 10000 scritture, `engine.genera_bilancio_verifica` (ritorna DataFrame pandas → records); quadratura |dare−avere|<0.01.

### POST /api/accounting-engine/storna-operazione/{operazione_id} — storno
**Cosa fa**: crea scrittura inversa invece di cancellare.
**Logica codice**: trova la scrittura in `scritture_contabili` per `id`; 400 se già stornata; `engine.crea_storno(originale, motivo)`; inserisce lo storno e marca l'originale `stato=stornata` con `stornato_da`.

### GET /api/accounting-engine/scritture — lista scritture
**Cosa fa**: elenco `scritture_contabili` non stornate con filtri data_da/data_a (`data_documento`), tipo_operazione, prima_nota; limit 1–1000.

### GET /api/accounting-engine/scritture/fattura/{fattura_id} — scrittura di una fattura
**Cosa fa**: recupera la scrittura non stornata collegata (`fattura_id`); 404 se assente.

### GET /api/accounting-engine/bilancio-periodo — bilancio su periodo
**Cosa fa**: bilancio di verifica per range date.
**Logica codice**: usa `get_accounting_engine_persistent(db).calcola_bilancio_periodo(data_da, data_a)`.

### GET /api/accounting-engine/statistiche-contabili — statistiche scritture
**Cosa fa**: totali scritture valide/stornate, aggregati per `tipo_operazione` e per `prima_nota` (somme su `importo_dare`).

---

## contabilita_avanzata.py + contabilita_italiana.py (/api/contabilita)
Due router sullo stesso prefisso. `contabilita_avanzata`: categorizzazione intelligente fatture→piano conti (GG.SS.CC), calcolo IRES/IRAP, PDF dichiarazione. `contabilita_italiana`: contabilità civilistica (cespiti, versamenti, buste paga, ritenute, ratei/risconti, bilancio CEE) sul motore `prima_nota_righe` con conti CEE a 6 cifre.

### GET /api/contabilita/piano-conti-esteso — piano conti esteso
**Cosa fa**: unione tra i conti presenti in `piano_conti` e la costante `PIANO_CONTI_ESTESO` del service di categorizzazione (i mancanti con saldo 0 e flag `nuovo`).
**Logica codice**: legge `piano_conti`, merge, ordina per codice, raggruppa per categoria.

### POST /api/contabilita/inizializza-piano-esteso — init/aggiorna piano esteso
**Cosa fa**: upsert dei conti di `PIANO_CONTI_ESTESO` in `piano_conti` preservando i saldi.
**Logica codice**: per ogni codice aggiorna nome/categoria/natura se diversi, altrimenti crea (saldo 0, `gruppo_codice`=prime 2 cifre); ritorna contatori.

### POST /api/contabilita/ricategorizza-fatture — rielaborazione massiva
**Cosa fa**: azzera e ricostruisce l'intera contabilità analitica: reset saldi `piano_conti` (tranne 01.01.01/01.01.02), `delete_many` su `movimenti_contabili`, poi ricrea un movimento per ogni fattura (`invoices` non deleted) e per ogni corrispettivo.
**Logica codice**: per fattura: `categorizza_fattura_completa(linee, fornitore)` sceglie il conto costo col maggiore importo (default 05.01.01); righe DARE costo+IVA credito 01.04.01, AVERE 02.01.01; aggiorna saldi via `aggiorna_saldo_conto` (attivo/costi: DARE aumenta; altri: AVERE aumenta) e marca la fattura (`registrata_contabilita`, deducibilità IRES/IRAP). Per corrispettivo: scorporo IVA al 10%, DARE cassa/banca (01.01.01/01.01.02) per contante/POS, AVERE 04.01.02 + 02.03.01.
**Note**: distruttivo (cancella tutti i movimenti_contabili); IVA corrispettivi ricalcolata sempre al 10% ignorando `totale_iva` reale.

### GET /api/contabilita/calcolo-imposte — IRES/IRAP in tempo reale
**Cosa fa**: calcola utile civilistico, variazioni fiscali, IRES 24%, IRAP regionale, aliquota effettiva.
**Logica codice**: `CalcolatoreImposte(regione).calcola_imposte_da_db(db, anno)`; variazioni automatiche telefonia/carburante; aliquote da `ALIQUOTE_IRAP`.

### GET /api/contabilita/bilancio-dettagliato — bilancio con deducibilità
**Cosa fa**: SP + CE costruiti dai SALDI correnti di `piano_conti`, con % deducibilità IRES/IRAP per voce di costo.
**Logica codice**: classifica i conti per `categoria`; mappa deducibilità hardcoded per 3 conti (05.02.07 telefonia 80%, 05.02.11 carburante 20%, 05.06.05 IMU 0% IRES); raggruppa costi per sottocategoria (prime 5 cifre); arrotondamento ricorsivo.
**Note**: dipende dai saldi statici della collezione, validi solo dopo `ricategorizza-fatture`; cumulativo, non filtrabile per anno.

### GET /api/contabilita/categorizzazione-preview — test regola singola
**Cosa fa**: anteprima categorizzazione di una descrizione+fornitore senza scrivere.
**Logica codice**: `categorizzatore.categorizza_linea(descrizione, fornitore)`; ritorna conto, categoria fiscale, deducibilità, confidenza.

### GET /api/contabilita/aliquote-irap — aliquote IRAP
**Cosa fa**: ritorna la costante `ALIQUOTE_IRAP` per regione.

### GET /api/contabilita/statistiche-categorizzazione — copertura categorizzazione
**Cosa fa**: distribuzione fatture per `categoria_contabile` con importi e deducibilità medie, più % copertura.
**Logica codice**: aggregazione su `invoices` (match `categoria_contabile` exists) + count categorizzate/non.

### GET /api/contabilita/export/pdf-dichiarazione — PDF dichiarazione redditi
**Cosa fa**: genera PDF (reportlab) con riepilogo imposte, variazioni IRES in aumento/diminuzione, dettaglio IRAP, quadro RF/RN.
**Logica codice**: `CalcolatoreImposte.calcola_imposte_da_db(db, anno)`; StreamingResponse `dichiarazione_redditi_{anno}.pdf`; formattazione importi in stile italiano.

### GET /api/contabilita/disponibilita-liquide — liquidità al giorno
**Cosa fa**: saldo cassa e banca dell'anno alla data indicata (default oggi) + totale versamenti cassa→banca.
**Logica codice**: aggregazione per `tipo` su `prima_nota_cassa` e `prima_nota_banca` con `data` tra 1/1 e data_rif; versamenti = uscite cassa con `categoria`/`descrizione` regex "versament".
**Note**: `saldo_iniziale_anno` promesso dal docstring NON è calcolato né restituito.

### POST /api/contabilita/cespiti/registra — acquisto cespite (motore CEE)
**Cosa fa**: registra acquisto bene strumentale: DARE conto cespite + IVA 22% (140500), AVERE debiti fornitori (230700); salva anagrafica in `cespiti`.
**Logica codice**: valida categoria in `COEFFICIENTI_AMMORTAMENTO` (D.M. 31/12/1988); scrittura via `crea_scrittura_contabile` (header in `prima_nota_cassa`, righe in `prima_nota_righe`); doc `cespiti` con coefficiente, fondo=0, array `ammortamenti`.
**Note**: schema `cespiti` DIVERSO da quello del router /api/cespiti (qui `ammortamenti[]`, là `piano_ammortamento[]`; qui manca `anno_acquisto`) — stessa collezione, due formati incompatibili.

### POST /api/contabilita/cespiti/ammortamento — quota annua cespite
**Cosa fa**: calcola e registra l'ammortamento annuale (DARE conto ammortamento, AVERE fondo); primo anno al 50% se `quota_ridotta_primo_anno`.
**Logica codice**: verifica cespite attivo e anno non già ammortizzato; quota = valore×coeff%, cap al residuo; scrittura al 31/12; `$set` fondo/residuo/stato + `$push` in `ammortamenti`.

### GET /api/contabilita/cespiti — lista cespiti
**Cosa fa**: elenco `cespiti` con filtro opzionale `stato`.

### POST /api/contabilita/cassa-banca/versamento — versamento contanti
**Cosa fa**: giroconto cassa→banca: DARE 160100 Depositi bancari, AVERE 160300 Cassa.
**Logica codice**: scrittura via `crea_scrittura_contabile` (ref VERS/data).
**Note**: NON scrive movimenti operativi entrata/uscita in prima_nota_cassa/banca: il giroconto esiste solo in `prima_nota_righe`, quindi i saldi calcolati dagli altri moduli (che leggono tipo/importo) non lo vedono.

### POST /api/contabilita/cassa-banca/prelievo — prelievo contanti
**Cosa fa**: inverso del versamento: DARE 160300 Cassa, AVERE 160100 Banca. **Note**: stessa limitazione del versamento.

### POST /api/contabilita/personale/acconto — acconto stipendio
**Cosa fa**: DARE 140520 Anticipi a dipendenti, AVERE cassa/banca; salva il record in `acconti_stipendi` (recuperato=False) per il recupero in busta paga.

### POST /api/contabilita/personale/busta-paga — registrazione cedolino
**Cosa fa**: scrittura completa busta paga: DARE salari 400410 + oneri 400420 + TFR 400430; AVERE debiti dipendenti 231400 (netto−acconti), debiti INPS 231300 (dip+azienda), debiti tributari 231200 (IRPEF+addizionali), fondo TFR 220000, recupero acconti 140520.
**Logica codice**: marca `acconti_stipendi` del dipendente come recuperati; ref PAGA/anno/mese/dip.
**Note**: se lordo ≠ netto+ritenute+INPS dip. la scrittura non bilancia e va in 400 (nessuna quadratura automatica).

### POST /api/contabilita/ritenute/registra — fattura con ritenuta d'acconto
**Cosa fa**: registra fattura professionista: DARE costi servizi 400200 + IVA 140500; AVERE fornitore 230700 (netto ritenuta) + Erario c/ritenute 231200; salva in `ritenute_acconto` (versata=False) per la CU.
**Logica codice**: IVA fissa 22%, ritenuta = imponibile×aliquota (default 20%).

### POST /api/contabilita/assestamento/rateo-risconto — scritture di assestamento
**Cosa fa**: registra rateo attivo/passivo o risconto attivo/passivo con storno del conto origine.
**Logica codice**: 4 rami con conti fissi (170100/170200 ratei-risconti attivi, 240100/240200 passivi); scrittura ref ASS/tipo/data; 400 se tipo non valido.

### GET /api/contabilita/bilancio/stato-patrimoniale — SP schema CEE
**Cosa fa**: stato patrimoniale al 31/12 (art. 2424 c.c.) dal motore CEE.
**Logica codice**: `$group` per `account_code` su `prima_nota_righe` con `date ≤ 31/12`; classifica per primo carattere (1=attivo se saldo>0, 2=passivo/PN); sezioni per prime 2 cifre; quadratura attivo−passivo.
**Note**: i conti attivo con saldo negativo vengono ignorati; la conversione del segno passivo è approssimata (`-saldo if saldo<0 else saldo`).

### GET /api/contabilita/bilancio/conto-economico — CE schema CEE
**Cosa fa**: conto economico annuale (art. 2425 c.c.) dal motore CEE.
**Logica codice**: `$group` su `prima_nota_righe` nell'anno; ricavi = conti 3xx/5xx (avere−dare), costi = 4xx (dare−avere); utile = ricavi−costi.
**Note**: i 5xx nel PIANO_CONTI_CEE sono "proventi/oneri finanziari": gli interessi passivi (C17, 500300) finiscono tra i RICAVI col segno sbagliato.

---

## contabilita_gestionale.py (/api/contabilita-gestionale)
Tre moduli gestionali: bilancio di verifica ricostruito al volo da TUTTE le fonti operative, partitario clienti/fornitori, budget con confronto consuntivo. Collezioni: `invoices`, `corrispettivi`, `prima_nota_cassa/banca/salari`, `cespiti`, `budget`, `budget_mensile`.

### GET /api/contabilita-gestionale/bilancio-verifica — bilancio di verifica completo
**Cosa fa**: per l'anno ricostruisce DARE/AVERE per conto (codici GG.SS.CC) da fatture, corrispettivi, prima nota cassa/banca/salari e cespiti; totali, quadratura, riepilogo per tipo.
**Logica codice**: fatture→costo (mappa keyword categoria→05.xx) DARE, debiti 02.01.01 AVERE, IVA 01.04.01 DARE (NC TD04/TD08 invertite); corrispettivi→ricavi 04.01.01 + IVA 02.03.01 AVERE, cassa 01.01.01 DARE; pn_cassa entrate/uscite su 01.01.01 (skip movimenti `corrispettivo_id`/`source=corrispettivo`; `versamento_banca` come giroconto); pn_banca su 01.02.01; salari→05.03.01/02.02.01; cespiti (`anno_acquisto`) →01.05.01, fondo 01.05.02, ammortamento 05.05.01 (campo `ammortamento_annuo`). `dettaglio=true` allega max 50 movimenti/conto (solo per le fatture).
**Note**: non essendo partita doppia completa la quadratura è quasi sempre falsa (es. incassi corrispettivi contati interamente in cassa anche se POS).

### GET /api/contabilita-gestionale/partitario/fornitori — partitario fornitori
**Cosa fa**: estratto conto per fornitore: fatture (DARE), NC e pagamenti (AVERE), saldo e stato (aperto/saldato/a_credito).
**Logica codice**: fatture dell'anno da `invoices` aggregate per `cedente_piva`/`supplier_vat`; pagamenti da `prima_nota_banca` e `prima_nota_cassa` con `fattura_id` valorizzato; se fattura marcata pagata (`stato_pagamento`/`paid`) ma senza pagamento in prima nota, assume pagamento pari all'importo. Filtri `fornitore_piva`, `solo_aperti`.

### GET /api/contabilita-gestionale/partitario/fornitori/{piva} — singolo fornitore
**Cosa fa**: wrapper di `get_partitario_fornitori(anno, fornitore_piva=piva)`; ritorna il primo (unico) fornitore o errore.

### GET /api/contabilita-gestionale/partitario/clienti — partitario clienti
**Cosa fa**: per HORECA i clienti sono anonimi: corrispettivi aggregati per mese (dare=avere=incasso contestuale, saldo 0) + eventuali fatture emesse.
**Logica codice**: `corrispettivi` dell'anno raggruppati per mese; fatture emesse da `db["fatture_emesse"]`.
**Note**: `fatture_emesse` è una collezione che quasi certamente non viene mai scritta (le emesse reali stanno in `invoices_emesse`): la sezione risulta sempre vuota.

### GET /api/contabilita-gestionale/budget/{anno} — budget completo
**Cosa fa**: voci di budget annuali con dettaglio mensile; se una voce non ha mensili distribuisce l'annuale /12.
**Logica codice**: legge `budget` e `budget_mensile` per anno; totali costi/ricavi/margine.

### POST /api/contabilita-gestionale/budget — salva voce budget
**Cosa fa**: upsert voce (`anno`+`voce`) in `budget` e dei mensili in `budget_mensile` (upsert per mese).

### DELETE /api/contabilita-gestionale/budget/{anno}/{voce} — elimina voce
**Cosa fa**: `delete_one` su `budget` + `delete_many` dei mensili.

### GET /api/contabilita-gestionale/budget-vs-consuntivo/{anno} — scostamenti
**Cosa fa**: confronto budget vs consuntivo per voce (opz. mese) con valutazione positivo/negativo e andamento mensile per grafico.
**Logica codice**: consuntivo ricavi da `corrispettivi` (totale_imponibile per mese); costi da `invoices` per `categoria_contabile` (NC a segno negativo); match voce↔categoria con substring case-insensitive bidirezionale.
**Note**: per voci-ricavo il consuntivo è sempre il TOTALE corrispettivi (se ci sono più voci ricavo, il consuntivo viene duplicato su ciascuna).

### POST /api/contabilita-gestionale/budget/duplica/{anno_origine}/{anno_destinazione} — duplica budget
**Cosa fa**: copia le voci (e i mensili) da un anno all'altro applicando `variazione_pct`; salta le voci già esistenti nella destinazione.

---

## piano_conti.py (/api/piano-conti)
Piano dei conti italiano (GG.SS.CC) con saldi CALCOLATI AL VOLO dalle collezioni operative (fix recente: non più dai saldi statici), regole di categorizzazione base e registrazione fatture/corrispettivi in `movimenti_contabili`. Usa `safe_float` per gli importi legacy stringa-con-virgola.

### GET /api/piano-conti/ — piano conti con saldi reali
**Cosa fa**: elenca i conti (auto-inizializza `STRUTTURA_BASE` se vuoto) con saldo ricalcolato dall'anno richiesto (o cumulativo).
**Logica codice**: `_calcola_saldi_piano_conti`: 01.01.01←`prima_nota_cassa` (entrate−uscite, può essere negativo, esclude status deleted/archived); 01.01.02←`prima_nota_banca`, fallback `estratto_conto_movimenti` se PNB vuota (importi positivi + campo tipo — NON `movimenti_bancari`, legacy ferma); 01.04.01/02.01.01←aggregato `invoices` (IVA, debiti lordi − pagamenti da prima nota con categoria "Pagamento fornitore"/riferimento FATT-/source fattura_pagata ecc., max(0,...)); costi splittati per sotto-conto via `$lookup` righe fattura↔`dizionario_articoli` (fallback tutto su 05.01.01); 04.01.01/02.03.01←`corrispettivi`; 05.03.xx/02.04.01←`cedolini`; 02.02.01←`f24_unificato`.
**Note**: il filtro anno sulle invoices usa `_date_range("invoice_date") or _date_range("data_documento")` — il secondo ramo non è mai valutato quando anno è passato (or su dict non vuoto), quindi filtra solo su `invoice_date`.

### POST /api/piano-conti/ — crea conto
**Cosa fa**: crea conto con codice/nome/categoria obbligatori; 409 se codice esistente; gruppo derivato da `STRUTTURA_BASE`.

### PUT /api/piano-conti/{conto_id} — aggiorna conto
**Cosa fa**: aggiorna nome/categoria/natura/attivo per `id`; 404 se `modified_count==0`.
**Note**: un update senza cambi reali (stesso valore) risponde 404 pur esistendo il conto.

### DELETE /api/piano-conti/{conto_id} — elimina conto
**Cosa fa**: elimina il conto solo se non ha movimenti (`movimenti_contabili.conto_id`).
**Note**: il check usa il campo `conto_id`, ma i movimenti creati da questo stesso router salvano i conti dentro `righe[].conto_codice`: il vincolo di fatto non scatta mai.

### GET /api/piano-conti/regole — regole categorizzazione base
**Cosa fa**: legge `regole_categorizzazione` (auto-init con 8 regole fornitore/tipo_documento/pagamento con conto_dare/avere).
**Note**: sistema di regole DIVERSO e parallelo a /api/regole (altre collezioni).

### POST /api/piano-conti/regole — crea regola
**Cosa fa**: inserisce regola {tipo, pattern, conto_dare, conto_avere} in `regole_categorizzazione`.

### POST /api/piano-conti/registra-fattura — registra fattura in partita doppia
**Cosa fa**: crea movimento contabile per una fattura: DARE costo+IVA credito, AVERE debito fornitore; aggiorna saldi statici `piano_conti` e marca la fattura.
**Logica codice**: dedup su `movimenti_contabili.fattura_id`; `determina_conti_fattura` applica le regole tipo=fornitore (regex sul nome) per il conto costo, default 05.01.01/01.04.01/02.01.01; insert movimento con righe tipo DARE/AVERE; `aggiorna_saldo_conto` per i 3 conti.

### GET /api/piano-conti/conto/{codice}/movimenti — drill-down movimenti conto
**Cosa fa**: dettaglio movimenti per conto con routing SEMANTICO per codice: 01.01.01→`prima_nota_cassa`; banca→`prima_nota_banca` con fallback `estratto_conto_movimenti` (fix: non più la legacy `movimenti_bancari`); crediti 01.02.*→`invoices_emesse` (fix: la collezione `fatture` non esiste, prima ritornava sempre vuoto); debiti 02.01.*/costi→`fatture_passive`; ricavi→`corrispettivi`.
**Logica codice**: 404 se conto non in `piano_conti`; filtro anno per range date; importi via `safe_float` in valore assoluto; ritorna fonte e nota esplicativa.

### GET /api/piano-conti/movimenti — lista movimenti contabili
**Cosa fa**: paginazione di `movimenti_contabili` con filtro data_da/data_a su `data_documento`, sort per `data_registrazione` desc.

### GET /api/piano-conti/bilancio — bilancio SP+CE per anno
**Cosa fa**: bilancio completo con i saldi ricalcolati da `_calcola_saldi_piano_conti` (stessa fonte di verità di GET /).
**Logica codice**: classifica i conti per categoria in SP (attivo/passivo/PN) e CE (ricavi/costi); risultato = ricavi−costi.

### POST /api/piano-conti/registra-tutte-fatture — batch registrazione
**Cosa fa**: registra in `movimenti_contabili` tutte le `invoices` con `registrata_contabilita≠true` (fino a 5000).
**Logica codice**: imponibile = total_amount−total_tax, conti via `determina_conti_fattura`, aggiorna saldi statici, marca fatture; errori raccolti (max 20 in risposta).
**Note**: NON deduplica su `movimenti_contabili.fattura_id` come registra-fattura: si affida solo al flag sulla fattura.

### POST /api/piano-conti/registra-corrispettivi — batch corrispettivi
**Cosa fa**: crea movimenti per i corrispettivi non registrati: DARE cassa 01.01.01 e/o banca 01.01.02 (contante/POS, default tutto cassa), AVERE ricavi bar 04.01.02 + IVA 02.03.01; aggiorna saldi e marca `registrato_contabilita`.
**Note**: IVA sempre scorporata al 10% ignorando `totale_iva` reale (stessa semplificazione di ricategorizza-fatture).

---

## bilancio.py (/api/bilancio)
Bilancio operativo "reale" (non da partita doppia): ricavi SOLO da corrispettivi, costi da fatture ricevute − note credito, liquidità da prima nota. L'header del file documenta le regole (fatture emesse ≠ ricavi aggiuntivi). P.IVA azienda hardcoded 04523831214.

### GET /api/bilancio/stato-patrimoniale — SP operativo
**Cosa fa**: attivo = saldo cassa + saldo banca + crediti (fatture emesse non pagate); passivo = debiti fornitori non pagati; PN = differenza.
**Logica codice**: aggregazioni condizionali per `tipo` su `prima_nota_cassa/banca` con `data ≤ data_fine` (parametri anno/mese/data_a); crediti da collezione `fatture_emesse` (status ∉ STATI_PAGATI); debiti da `invoices` escluse TD04/TD08 non pagate.
**Note**: i crediti leggono `fatture_emesse` che non risulta alimentata (le emesse stanno in `invoices_emesse`) → crediti quasi sempre 0.

### GET /api/bilancio/conto-economico — CE operativo
**Cosa fa**: CE per anno o mese: ricavi = imponibile corrispettivi; costi = imponibile fatture (escl. NC) − NC; utile, margine %, dettaglio IVA (vendite/acquisti/netta) e statistiche.
**Logica codice**: 3 aggregazioni (`corrispettivi`, `invoices` non-NC, `invoices` NC); date su `invoice_date` OR `data_ricezione`; imponibile con `$ifNull`/`$subtract` (total_amount−iva).

### GET /api/bilancio/riepilogo — SP + CE insieme
**Cosa fa**: combina gli helper interni `_get_stato_patrimoniale_data` + `_get_conto_economico_data` per l'anno.
**Note**: gli helper usano una logica DIVERSA dagli endpoint pubblici: crediti = invoices TD01/TD24/TD26 non pagate e debiti = gli altri tipi — classificazione contraddetta dall'header del file stesso (in `invoices` sono tutte ricevute). L'helper CE stima anche l'utile netto con imposte forfait 28%.

### GET /api/bilancio/conto-economico-dettagliato — CE civilistico art. 2425
**Cosa fa**: CE dettagliato per natura (B6 merci, B7 servizi con sottovoci, B8 godimento terzi, B9 personale da cedolini, B14, C17) con deducibilità fiscale e stima reddito fiscale.
**Logica codice**: classifica ogni fattura con `classifica_fornitore(supplier, descrizione)` (service classificazione_costi); personale da `cedolini` (usa `costo_azienda` se >0, altrimenti stima INPS 30% e TFR 6,91%); deducibilità: telefonia 80%, noleggio auto 20% su max €3.615,20, carburante 20%; reddito fiscale = risultato + indeducibili.

### GET /api/bilancio/export-pdf — PDF bilancio
**Cosa fa**: PDF (reportlab) con tabella SP e CE dell'anno.
**Logica codice**: usa gli helper `_get_*_data` (quindi la logica alternativa citata sopra); StreamingResponse `bilancio_{anno}.pdf`.

### GET /api/bilancio/confronto-annuale — confronto YoY
**Cosa fa**: confronta CE e SP di due anni con variazioni assolute/%/trend e KPI (margine lordo, ROI, crescita ricavi/costi) + sintesi con emoji.
**Logica codice**: doppia chiamata agli helper; `calc_variazione` per ogni voce.

### GET /api/bilancio/export/pdf/confronto — PDF comparativo
**Cosa fa**: PDF del confronto YoY (tabelle CE, SP, KPI).
**Logica codice**: richiama `get_confronto_annuale` e impagina con reportlab; filename `Bilancio_Comparativo_X_vs_Y.pdf`.

---

## centri_costo.py (/api/centri-costo)
Contabilità analitica per bar/pasticceria: CdC standard (CDC-01..04 operativi, CDC-90..92 supporto, CDC-99 struttura), assegnazione automatica alle fatture, utile obiettivo, ribaltamento costi.

### GET /api/centri-costo — lista CdC con statistiche
**Cosa fa**: elenca `centri_costo` (auto-init da CDC_STANDARD se vuota) aggiungendo per ognuno count e totale fatture (`invoices.centro_costo`).

### POST /api/centri-costo — crea CdC
**Cosa fa**: inserisce nuovo centro (codice obbligatorio, 400 se duplicato).

### GET /api/centri-costo/mapping-categorie — mapping automatici
**Cosa fa**: ritorna le costanti CATEGORIA_TO_CDC, FORNITORE_TO_CDC (KIMBO→CDC-01, ENEL→CDC-99, …) e CDC_STANDARD.

### POST /api/centri-costo/assegna-cdc-fatture — assegnazione automatica
**Cosa fa**: assegna `centro_costo` alle fatture: 1) per `categoria_contabile`, 2) per substring nel nome fornitore, 3) default CDC-99; `force=true` sovrascrive.
**Logica codice**: update per `_id` su `invoices` con flag `cdc_auto_assigned`; ritorna distribuzione.

### GET /api/centri-costo/utile-obiettivo — stato vs target utile
**Cosa fa**: confronta l'utile reale (ricavi corrispettivi − costi fatture, LORDI) col target annuo, proporziona ai giorni lavorativi trascorsi, proietta a fine anno e suggerisce ricavi/costi correttivi.
**Logica codice**: target da `utile_obiettivo` (default €50.000, margine 35%, 300 gg); aggregazioni su `corrispettivi.totale` e `invoices.total_amount`.
**Note**: usa importi LORDI (IVA inclusa) sia per ricavi che per costi.

### POST /api/centri-costo/utile-obiettivo — imposta target
**Cosa fa**: upsert su `utile_obiettivo` per anno (target annuo/mensile, margine atteso, giorni lavorativi).

### GET /api/centri-costo/utile-obiettivo/suggerimenti — motore suggerimenti
**Cosa fa**: genera suggerimenti (CRITICO/OPZIONE_A/OPZIONE_B/ANALISI_CDC o POSITIVO/PROIEZIONE) in base allo scostamento, incluso il CdC più costoso.
**Logica codice**: riusa `get_utile_obiettivo`; aggregazione top CdC su `invoices`.

### GET /api/centri-costo/utile-obiettivo/per-cdc — margini per CdC
**Cosa fa**: costi reali per CdC + ricavi STIMATI (proporzionali al peso costi ×1,5 solo per CdC operativi) con margini.
**Note**: i ricavi per CdC sono una stima dichiarata, non dati tracciati.

### GET /api/centri-costo/ribaltamento/chiavi — chiavi di ribaltamento
**Cosa fa**: ritorna la costante CHIAVI_RIBALTAMENTO (quote % dai centri di supporto a CDC-01/CDC-02).
**Note**: le chiavi referenziano CDC-03..07 che NON coincidono con i codici di supporto reali (CDC-90/91/92): il ribaltamento di fatto non intercetta i costi di supporto standard.

### POST /api/centri-costo/ribaltamento/calcola — calcolo full-cost
**Cosa fa**: ribalta i costi dei centri di supporto sui CdC operativi secondo le chiavi, calcola costi pieni e margini (ricavi stimati 40% bar / 60% pasticceria).
**Logica codice**: aggregazione costi per `centro_costo` su `invoices`; nessuna scrittura.
**Note**: usa la costante hardcoded, NON le chiavi salvate con l'endpoint sotto; stessi mismatch di codici CDC.

### POST /api/centri-costo/ribaltamento/aggiorna-chiavi — salva chiavi
**Cosa fa**: upsert del documento `config_ribaltamento._id=chiavi_ribaltamento`.
**Note**: le chiavi salvate non vengono mai rilette da `/ribaltamento/calcola` — configurazione di fatto inerte.

---

## iva_calcolo.py (/api/iva)
Calcoli IVA giornalieri/mensili/annuali: debito da corrispettivi, credito da fatture ricevute (data rilevante = `data_ricezione` con fallback `invoice_date`), NC TD04/TD08 sottratte.

### GET /api/iva/daily/{date} — IVA giornaliera
**Cosa fa**: IVA debito (corrispettivi del giorno) vs credito (fatture ricevute nel giorno, NC sottratte) con dettaglio per fattura e saldo.
**Logica codice**: per ogni fattura preferisce `riepilogo_iva[]` (esclude righe con `natura` = esenti); fallback campi diretti `iva`/`imponibile` o stima da totale con aliquota (default 22%).
**Note**: BUG di firma — il path dichiara `{date}` ma la funzione ha il parametro `date_param`: FastAPI lo tratta come query param obbligatorio, quindi la chiamata REST richiede `?date_param=YYYY-MM-DD` (il segmento path è ignorato). `/today` funziona perché chiama la funzione direttamente.

### GET /api/iva/monthly/{year}/{month} — progressivo mensile
**Cosa fa**: per ogni giorno del mese IVA debito/credito/NC, saldo giornaliero e progressivi.
**Logica codice**: ottimizzato: 1 aggregazione corrispettivi per giorno + 1 sola find fatture del mese raggruppate in memoria; stessa logica riepilogo_iva/fallback del daily.

### GET /api/iva/annual/{year} — riepilogo annuale con riporto credito
**Cosa fa**: per ogni mese IVA credito (fatture−NC), debito (corrispettivi), saldo, più SALDO PROGRESSIVO con riporto del credito ai mesi successivi (`stato_progressivo`, `importo_da_versare`).
**Logica codice**: 3 aggregazioni per mese (fatture non-NC, NC, corrispettivi) sommando i campi flat `iva`/`imponibile` (qui NIENTE fallback riepilogo_iva né stima).
**Note**: può divergere dal monthly per le fatture senza campo `iva` valorizzato (il monthly le stima, l'annual no).

### GET /api/iva/today — IVA di oggi
**Cosa fa**: shortcut che invoca `get_iva_daily(date.today())` come funzione Python.

### GET /api/iva/export/pdf/trimestrale/{year}/{quarter} — PDF trimestrale
**Cosa fa**: PDF con tabella mensile del trimestre (debito, credito netto, NC, saldo) e box "da versare entro il 16".
**Logica codice**: rifà le aggregazioni per i 3 mesi (campi flat), reportlab, filename `IVA_Trimestrale_Qn_yyyy.pdf`; 400 se quarter ∉ 1-4.

### GET /api/iva/export/pdf/annuale/{year} — PDF annuale
**Cosa fa**: PDF con tabella dei 12 mesi + totali; riusa `get_iva_annual`.

---

## liquidazione_iva.py (/api/liquidazione-iva)
Liquidazione IVA mensile "da commercialista" con deroghe temporali (regola 15 giorni / 12 giorni). Il router ha prefix interno `/liquidazione-iva` e viene montato su `/api`. Calcolo delegato a `app/services/liquidazione_iva.py`.

### GET /api/liquidazione-iva/calcola/{anno}/{mese} — liquidazione mensile
**Cosa fa**: calcola la liquidazione (debito da corrispettivi, credito da fatture con deroghe 15/12 giorni, NC sottratte, credito precedente riportabile) e, se c'è IVA da versare, CREA automaticamente la scadenza F24 (codice tributo 6001–6012) e un movimento previsionale in `prima_nota_banca`.
**Logica codice**: query `invoices` su mese corrente (data_ricezione/invoice_date) + mese precedente per le deroghe; `compute_vat_liquidation_from_db`; dedup F24 per codice+periodo su `f24_unificato` (status ≠ eliminato).
**Note**: endpoint GET con effetti collaterali di scrittura (F24 + prima nota); il codice tributo è costruito come `600{mese}`/`60{mese}` (per mese 10/11/12 → 6010/6011/6012, corretto ma poco leggibile).

### GET /api/liquidazione-iva/confronto/{anno}/{mese} — confronto con commercialista
**Cosa fa**: confronta il calcolo interno con i valori inseriti dal commercialista (query param obbligatori) con tolleranza €1 ed esito coincide/da verificare.
**Logica codice**: richiama `calcola_liquidazione_iva` (quindi eredita i side-effect F24).

### GET /api/liquidazione-iva/export/pdf/{anno}/{mese} — PDF liquidazione
**Cosa fa**: PDF della liquidazione via `export_liquidazione_iva_pdf` (intestazione "Ceraldi Group S.R.L."); filename `Liquidazione_IVA_{Mese}_{anno}.pdf`.

### GET /api/liquidazione-iva/riepilogo-annuale/{anno} — riepilogo con credito progressivo
**Cosa fa**: calcola i 12 mesi in sequenza propagando `credito_da_riportare` come credito del mese successivo; totali annuali.
**Note**: iterando `calcola_liquidazione_iva` può generare fino a 12 scadenze F24/movimenti prima nota in una sola GET (dedup limita i duplicati).

### GET /api/liquidazione-iva/dettaglio-fatture/{anno}/{mese} — audit inclusioni
**Cosa fa**: elenca le fatture INCLUSE (con criterio: stesso mese / deroga 15 gg / deroga 12 gg) ed ESCLUSE (con motivo) dalla liquidazione; filtro `tipo`=tutte/incluse/escluse.
**Logica codice**: replica i criteri con `month_bounds`, `within_12_days_rule`, `parse_date` del service; sola lettura.

---

## regole_categorizzazione.py (/api/regole)
Gestione regole di categorizzazione contabile (fornitore→categoria, keyword descrizione→categoria, categoria→conto+deducibilità) con round-trip Excel. Collezioni: `regole_categorizzazione_fornitori`, `regole_categorizzazione_descrizioni`, `regole_categorie`. Default hardcoded (DEFAULT_CATEGORIE, DEFAULT_PIANO_CONTI) + regole dal service `categorizzazione_contabile`.

### GET /api/regole/download-regole — export Excel
**Cosa fa**: genera XLSX con 5 fogli (Regole Fornitori, Regole Descrizioni, Categorie con deducibilità, Piano dei Conti da `piano_conti`, Istruzioni) più righe vuote precompilate.
**Logica codice**: openpyxl; usa i default se le collezioni sono vuote; StreamingResponse `regole_categorizzazione.xlsx`.

### POST /api/regole/upload-regole — import Excel
**Cosa fa**: carica l'XLSX modificato e SOSTITUISCE le regole: per ogni foglio presente fa `delete_many({})` + `insert_many` (fornitori, descrizioni, categorie con deducibilità clampata 0–100).
**Note**: sostituzione integrale, non merge; nessun backup delle regole precedenti.

### GET /api/regole — tutte le regole
**Cosa fa**: unione regole DB (priorità) + default non presenti (marcate `source=default`), più categorie e DEFAULT_PIANO_CONTI.
**Logica codice**: dedup per pattern lowercase; default fornitori derivati da PATTERNS_FORNITORE (regex ripulite in testo leggibile).

### POST /api/regole/fornitore — aggiungi/aggiorna regola fornitore
**Cosa fa**: upsert per `pattern` in `regole_categorizzazione_fornitori` (categoria normalizzata lowercase_underscore).

### POST /api/regole/descrizione — aggiungi/aggiorna regola descrizione
**Cosa fa**: come sopra su `regole_categorizzazione_descrizioni`.

### DELETE /api/regole/elimina/{tipo}/{pattern} — elimina regola
**Cosa fa**: delete per pattern nella collezione scelta da `tipo` (fornitore → fornitori, qualsiasi altro valore → descrizioni); 404 se assente.

### POST /api/regole/categorie — upsert categoria
**Cosa fa**: upsert in `regole_categorie` (categoria, conto, deducibilità IRES/IRAP 0–100).

---

## chiusura_esercizio.py (/api/chiusura-esercizio)
Wizard di chiusura annuale in 3 step (verifica → bilancino → chiusura) + apertura nuovo esercizio con riporto saldi. Scrive in `chiusure_esercizio`, `aperture_esercizio`, `movimenti_contabili`, `prima_nota_cassa/banca`.

### GET /api/chiusura-esercizio/verifica-preliminare/{anno} — check completezza
**Cosa fa**: verifica fatture non contabilizzate (bloccante), mesi corrispettivi mancanti, cedolini/salari, TFR accantonato (`tfr_accantonamenti`), ammortamenti cespiti, movimenti estratto conto; punteggio completezza e flag `pronto_per_chiusura`.
**Logica codice**: count/aggregate su `invoices` (`contabilizzata≠true`), `corrispettivi`, `cedolini`, `prima_nota_salari`, `cespiti`, `estratto_conto_movimenti`.
**Note**: il flag usato è `contabilizzata`, ma i moduli di registrazione impostano `registrata_contabilita` → il check segnala quasi sempre tutte le fatture come non contabilizzate.

### GET /api/chiusura-esercizio/bilancino-verifica/{anno} — bilancino pre-chiusura
**Cosa fa**: ricavi = corrispettivi + invoices TD01/TD24/TD26; costi = invoices altri tipi + personale (`prima_nota_salari.costo_azienda`) + ammortamenti e TFR da `movimenti_contabili`; utile/perdita e margine.
**Note**: classificare le TD01 di `invoices` come "fatture emesse"/ricavi contraddice il resto del sistema (in `invoices` sono tutte ricevute): i ricavi risultano gonfiati dei acquisti TD01 e i costi sottostimati. Importi lordi IVA.

### POST /api/chiusura-esercizio/esegui-chiusura — chiusura esercizio
**Cosa fa**: dopo verifica preliminare (400 se problemi bloccanti) e con `conferma_scritture=true`, salva il documento di chiusura con il bilancino e un movimento `risultato_esercizio` in `movimenti_contabili`.
**Logica codice**: insert in `chiusure_esercizio` (id, bilancino, risultato, tipo, note) + movimento con segno avere/dare secondo utile/perdita.
**Note**: non chiude realmente i conti (nessuna scrittura di epilogo); la chiusura "contabile" vera è in /api/fiscalita/chiusura-esercizio — sistemi duplicati sulla stessa collezione `chiusure_esercizio` con schemi diversi.

### GET /api/chiusura-esercizio/stato/{anno} — stato esercizio
**Cosa fa**: ritorna chiuso/aperto in base alla presenza del documento in `chiusure_esercizio`.

### GET /api/chiusura-esercizio/storico — storico chiusure
**Cosa fa**: lista `chiusure_esercizio` ordinata per anno desc.

### POST /api/chiusura-esercizio/apertura-nuovo-esercizio — riporto saldi
**Cosa fa**: verifica che l'anno precedente sia chiuso; calcola saldo cassa/banca (per campo `anno`), debiti fornitori (invoices `pagato≠true` — TUTTE, senza filtro anno), assegni in portafoglio, TFR totale; salva in `aperture_esercizio` e crea i movimenti "Saldo iniziale" in `prima_nota_cassa` e `prima_nota_banca` (tipo entrata/uscita, categoria Riporto).
**Note**: i saldi cassa/banca filtrano su campo `anno` del movimento (non su `data`): i movimenti senza `anno` valorizzato sono esclusi dal riporto. Eseguirlo due volte duplica i movimenti di apertura (nessun dedup).

### GET /api/chiusura-esercizio/saldi-iniziali/{anno} — saldi riportati
**Cosa fa**: ritorna `saldi_riportati` dell'apertura registrata per l'anno (o messaggio se assente).

---

## chart_of_accounts.py (/api/chart-of-accounts)
CRUD "pulito" sul piano dei conti via repository/service con autenticazione e scoping `user_id`. `Collections.CHART_OF_ACCOUNTS` punta alla collezione `piano_conti` (la stessa dei router italiani).

### GET /api/chart-of-accounts — lista conti
**Cosa fa**: elenca i conti dell'utente, filtro opzionale `type` ∈ attivo|passivo|costi|ricavi.
**Logica codice**: `ChartOfAccountsService.list_accounts(user_id, account_type)` su `piano_conti`.
**Note**: filtra per `user_id`, ma i conti creati dai router italiani non hanno quel campo → visioni divergenti della stessa collezione.

### POST /api/chart-of-accounts — crea conto
**Cosa fa**: crea conto (code, name, type, parent_id, description) validato dal modello `ChartOfAccountCreate`; ritorna `account_id`; 201.

### PUT /api/chart-of-accounts/{account_id} — aggiorna conto
**Cosa fa**: update via `ChartOfAccountUpdate` (service `update_account`).

### DELETE /api/chart-of-accounts/{account_id} — soft delete
**Cosa fa**: disattiva il conto (`delete_account` = set inactive, non cancella).

---

## indici_bilancio.py (/api/indici-bilancio)
Indici di bilancio semplificati (ROI, ROE, ROS, current/quick ratio, indebitamento, rotazione capitale) con interpretazione qualitativa.

### GET /api/indici-bilancio/calcola/{anno} — calcolo indici
**Cosa fa**: costruisce SP approssimato (liquidità, crediti, debiti, TFR, immobilizzazioni) e CE (ricavi, costi, EBIT) poi calcola gli indici con soglie di giudizio (buono/sufficiente/critico).
**Logica codice**: cassa = ultimo `saldi_giornalieri.saldo_finale`; banca = campo `saldo` dell'ULTIMO movimento `estratto_conto_movimenti`; crediti = invoices TD01/TD24/TD26 non pagate; debiti = altri tipi non pagati; TFR da `dipendenti.tfr_accantonato`; immobilizzazioni da `cespiti.valore_residuo`; ricavi = corrispettivi + invoices TD01/TD24/TD26; costi = invoices altri tipi + `prima_nota_salari.costo_azienda`.
**Note**: stessa classificazione dubbia TD01=emesse di chiusura_esercizio (crediti/ricavi gonfiati); il saldo banca dipende dall'esistenza del campo `saldo` sui movimenti EC (spesso assente → 0); crediti/debiti non filtrati per anno.

### GET /api/indici-bilancio/confronto-anni — confronto ROI/ROE/ROS
**Cosa fa**: calcola gli indici per due anni (default anno−1) e ritorna variazioni % per ROI/ROE/ROS più i dettagli completi.

---

## fiscalita_italiana.py (/api/fiscalita)
Fiscalità SRL: catalogo agevolazioni 2025 hardcoded, calendario fiscale generato, notifiche scadenze, registrazione F24 con scrittura contabile, chiusura/apertura contabile sul motore `prima_nota_righe` (conti CEE).

### GET /api/fiscalita/agevolazioni — catalogo agevolazioni
**Cosa fa**: lista agevolazioni (crediti d'imposta, ACE, Patent Box, ZES, …) con requisiti, normativa, codici tributo.
**Logica codice**: legge `agevolazioni_fiscali`; se vuota la inizializza dalla costante AGEVOLAZIONI_FISCALI_SRL; filtro `categoria`.
**Note**: il filtro `attivo` è applicato solo quando truthy: `attivo=false` ritorna tutte, non le inattive.

### GET /api/fiscalita/agevolazioni/{agevolazione_id} — dettaglio
**Cosa fa**: singola agevolazione da DB con fallback sulla costante; 404 se inesistente.

### POST /api/fiscalita/agevolazioni/simula — simulazione beneficio
**Cosa fa**: beneficio = investimento × aliquota (scelta per dimensione impresa piccola/media/grande) con cap al massimale.

### GET /api/fiscalita/calendario/scadenze-imminenti — prossime scadenze
**Cosa fa**: scadenze non completate nei prossimi N giorni (default 30) suddivise in urgenti ≤7 gg / prossime 8-14 / future.
**Logica codice**: find su `calendario_fiscale` per range data; in caso di eccezione ritorna `success:false` con traceback troncato.

### GET /api/fiscalita/calendario/{anno} — calendario fiscale annuale
**Cosa fa**: genera (una tantum, poi cache su DB) tutte le scadenze dell'anno via `genera_scadenze_anno`: liquidazioni IVA mensili/trimestrali, acconto IVA, LIPE, IRES/IRAP saldo+acconti, Redditi SC, ritenute, 770, CU, IMU, INPS, bilancio, Intrastat, CCIAA, vidimazione libri; raggruppa per mese e ritorna le prossime 5.
**Logica codice**: insert in `calendario_fiscale` con `completato=False`.
**Note**: la route `/calendario/scadenze-imminenti` è dichiarata PRIMA di `/calendario/{anno}` apposta per evitare il catch-all.

### POST /api/fiscalita/calendario/completa/{scadenza_id} — completa scadenza
**Cosa fa**: `$set completato=true` con data e note; 404 se non trovata/già completata.

### GET /api/fiscalita/notifiche-scadenze — scadenze per notifiche
**Cosa fa**: come scadenze-imminenti ma con filtro `anno` e fasce ≤3 / ≤7 / oltre (critiche/alta priorità/normali).
**Note**: duplicazione quasi identica di `/calendario/scadenze-imminenti`; esiste anche un helper `_get_notifiche_impl` mai richiamato (dead code).

### POST /api/fiscalita/notifiche-scadenze/invia — crea notifica
**Cosa fa**: `tipo=dashboard` inserisce notifica in `notifications`; `tipo=email` prepara solo il template (non invia, dichiara la necessità di integrazione).

### POST /api/fiscalita/f24/registra — registra versamento F24
**Cosa fa**: scrittura contabile del versamento: DARE debiti tributari/previdenziali (conto scelto dal prefisso codice tributo: 10xx ritenute, 60xx IVA, 20xx IRES, 38xx IRAP, DM10 INPS→231300), AVERE crediti compensati (140500) e banca (160100) per il netto; salva il documento in `f24_unificato` e marca completate le scadenze del calendario con quei codici.
**Logica codice**: scrittura via `crea_scrittura` (header in `prima_nota_cassa`, righe in `prima_nota_righe`).
**Note**: schema del doc in `f24_unificato` (tributi[], totale_versato) diverso da quello creato dalla liquidazione IVA (flat con codice_tributo) — la stessa collezione ospita formati eterogenei.

### GET /api/fiscalita/f24/storico — storico F24
**Cosa fa**: lista `f24_unificato` (filtro anno su `data_versamento`) con totali versato/compensato.

### POST /api/fiscalita/chiusura-esercizio — chiusura contabile (motore CEE)
**Cosa fa**: scritture di epilogo vere: chiude i ricavi (3xx/5xx, saldo avere) e i costi (4xx, saldo dare) girandoli al conto 200900 "Conto Economico", rileva utile/perdita, salva in `chiusure_esercizio`.
**Logica codice**: `$group` su `prima_nota_righe` dell'anno; tre scritture CHIUS/RICAVI, CHIUS/COSTI, CHIUS/RISULTATO via `crea_scrittura`.
**Note**: la scrittura del risultato usa 200900 sia in DARE che in AVERE (stesso conto sui due lati) → effetto contabile nullo sul saldo del conto; duplica la funzione di /api/chiusura-esercizio con schema diverso nella stessa collezione; eredita l'errore 5xx=ricavi (oneri finanziari epilogati come ricavi).

### POST /api/fiscalita/apertura-esercizio — riapertura conti
**Cosa fa**: riapre i conti patrimoniali (1xx/2xx) al 1/1 con i saldi al 31/12 precedente; sbilancio pareggiato su 200800 Utili/Perdite portati a nuovo.
**Logica codice**: `$group` su `prima_nota_righe` fino al 31/12; una scrittura APER/{anno}.
**Note**: nessun controllo che la chiusura sia stata eseguita né dedup: rilanciarlo duplica le aperture.

---

## controllo_gestione.py (/api/controllo-gestione)
Controllo di gestione: analisi costi/ricavi, trend, breakdown, budget semplice e KPI HORECA (food cost, incidenza personale).

### GET /api/controllo-gestione/costi-ricavi — analisi periodo
**Cosa fa**: ricavi = corrispettivi + invoices TD01/TD24/TD26; costi = personale (cedolini `costo_azienda`, fallback `prima_nota_salari`) + acquisti (invoices altri tipi) + uscite `prima_nota_cassa`; margine e %.
**Note**: stessa classificazione errata TD01=emesse (vedi chiusura_esercizio); le uscite cassa possono contenere pagamenti di fatture già contate → possibile doppio conteggio costi; per mese≠12 il range usa `$lt` primo giorno mese successivo, per dicembre `$lte` 31/12.

### GET /api/controllo-gestione/trend-mensile — trend 12 mesi
**Cosa fa**: chiama `get_analisi_costi_ricavi` per ogni mese; ritorna ricavi/costi/margine mensili + totale anno (mesi in errore = zeri).

### GET /api/controllo-gestione/costi-per-categoria — breakdown costi
**Cosa fa**: top 20 fornitori per acquisti (invoices, tipi non-TD01/04/24/26) + uscite `prima_nota_cassa` raggruppate per `categoria`.

### POST /api/controllo-gestione/budget — crea/aggiorna voce budget
**Cosa fa**: upsert per anno+voce in `budget` (categoria costo/ricavo, importo, note).
**Note**: stessa collezione di /api/contabilita-gestionale/budget (sistemi budget duplicati; questo non gestisce i mensili).

### GET /api/controllo-gestione/budget/{anno} — budget anno
**Cosa fa**: lista voci `budget` con totali costi/ricavi/margine.

### GET /api/controllo-gestione/budget-vs-consuntivo/{anno} — scostamenti
**Cosa fa**: confronta budget (annuale o /12 se mese) con il consuntivo di `costi-ricavi`; scostamenti assoluti/%/valutazione.

### GET /api/controllo-gestione/kpi/{anno} — KPI gestionali
**Cosa fa**: margine operativo, incidenza personale su ricavi (benchmark <35%), food cost (benchmark 25-35%), costo/ricavo medio giornaliero (/365); allega il dettaglio dell'analisi.

---

## finanziaria.py (/api/finanziaria)
Riepilogo finanziario aggregato per la dashboard + micro-CRUD costi finanziari.

### GET /api/finanziaria/summary — riepilogo finanziario anno
**Cosa fa**: entrate/uscite/saldi cassa e banca, IVA debito (corrispettivi) vs credito (fatture−NC), fatture da pagare (payables), totali corrispettivi e fatture.
**Logica codice**: aggregazioni per `tipo` su `prima_nota_cassa/banca` e `prima_nota_salari` (range data anno); IVA con stessa logica data_ricezione/fallback di iva_calcolo; payables = invoices con `status ∉ STATI_PAGATI`; salari NON sommati alle uscite (già inclusi in banca, documentato nel codice); in caso di eccezione ritorna zeri con campo `error`.

### GET /api/finanziaria/costi — lista costi finanziari
**Cosa fa**: elenca `costi_finanziari` ordinati per data desc (max 500).

### GET /api/finanziaria/cost-categories — categorie costi
**Cosa fa**: ritorna lista statica di 10 categorie (personale, utenze, …, da_classificare).

### POST /api/finanziaria/costo — crea costo
**Cosa fa**: insert del body raw in `costi_finanziari` con id uuid e created_at; 201. **Note**: nessuna validazione dei campi.

---

## cespiti.py (/api/cespiti)
Registro cespiti "gestionale" (collezione `cespiti`, campo `piano_ammortamento[]`): anagrafica, calcolo/registrazione ammortamenti, auto-scan dalle fatture, dismissioni. Coefficienti DM 31/12/1988 per la ristorazione.

### GET /api/cespiti/categorie — categorie ammortamento
**Cosa fa**: ritorna CATEGORIE_CESPITI (11 categorie con coefficiente e vita utile).

### POST /api/cespiti/ — crea cespite
**Cosa fa**: inserisce cespite con coefficiente dalla categoria (400 se invalida), fondo 0, `piano_ammortamento=[]`; ritorna quota annua ordinaria e quota primo anno dimezzata.

### GET /api/cespiti/ — lista cespiti
**Cosa fa**: elenco con filtri `attivi` (default true → stato=attivo) e `categoria`.

### GET /api/cespiti/riepilogo — riepilogo per categoria
**Cosa fa**: aggregazione cespiti attivi per categoria (num, valore acquisto, fondo, residuo) + totali e % ammortizzata.

### GET /api/cespiti/calcolo/{anno} — preview ammortamenti
**Cosa fa**: calcola (SENZA salvare) la quota anno per ogni cespite attivo non completato: quota = valore×coeff% (dimezzata se anno di acquisto), cap al residuo; salta i cespiti con l'anno già in `piano_ammortamento`.

### POST /api/cespiti/scan-fatture — auto-estrazione cespiti da fatture
**Cosa fa**: scandisce `invoices` e `fatture_passive` (importo > soglia, default €200) classificando le righe con keyword (forni, frigoriferi, mobili, software, …) ed exclude-list (caffè, noleggio, canoni, manutenzione ordinaria, …); dedup su (descrizione[:100], prezzo) anche verso i cespiti esistenti; `dry_run=true` per preview.
**Logica codice**: righe da `righe`/`linee`/`lines`; se assenti usa il totale fattura come riga unica; insert_many in `cespiti` con nota "Auto-estratto da fattura XML". Route dichiarata PRIMA di `/{cespite_id}` per evitare il catch-all.

### GET /api/cespiti/{cespite_id} — dettaglio cespite
**Cosa fa**: singolo cespite con piano ammortamento; 404 se assente.

### POST /api/cespiti/registra/{anno} — registra ammortamenti
**Cosa fa**: applica la preview di `calcolo/{anno}`: aggiorna fondo/residuo/completato e `$push` in `piano_ammortamento`; crea un movimento riepilogativo `tipo=ammortamento` in `movimenti_contabili` E un movimento `uscita` in `prima_nota_cassa` (categoria Ammortamenti, riconciliato=True).
**Note**: l'ammortamento è un costo NON monetario: registrarlo come uscita di cassa altera il saldo cassa calcolato da piano_conti/bilancio.

### POST /api/cespiti/dismissione — dismissione cespite
**Cosa fa**: dismette per vendita/eliminazione/permuta; calcola plus/minusvalenza (vendita: prezzo−residuo; altrimenti −residuo); salva `dismissione` sul cespite, movimento in `movimenti_contabili` e movimento entrata/uscita in `prima_nota_banca` (se vendita con prezzo) o `prima_nota_cassa`.
**Note**: in prima nota va la sola plus/minusvalenza, non l'incasso della vendita.

### PUT /api/cespiti/{cespite_id} — aggiorna cespite
**Cosa fa**: aggiorna campi anagrafici; se cambia `valore_acquisto` ricalcola il residuo (valore−fondo); se cambia `data_acquisto` aggiorna `anno_acquisto`. Categoria e coefficiente non modificabili.

### DELETE /api/cespiti/{cespite_id} — elimina cespite
**Cosa fa**: eliminazione definitiva, negata (400) se esistono quote in `piano_ammortamento` (in quel caso usare la dismissione).

---

## mutui.py + mutui_parser.py (/api/mutui)
Gestione mutui BPM: CRUD, statistiche, riconciliazione rate↔estratto conto, import piani di ammortamento da PDF (pdfplumber + regex). Collezione `mutui` (documento con array `rate[]`, date rate in formato DD/MM/YYYY).

### GET /api/mutui/ — lista mutui
**Cosa fa**: lista paginata (skip/limit) con statistiche aggregate calcolate in Python SOLO sulla pagina corrente (importo accordato, residuo, rate pagate/da pagare).
**Note**: le "statistiche" riflettono la pagina, non l'intero portafoglio (usare /statistiche/dashboard per i totali).

### GET /api/mutui — alias senza slash
**Cosa fa**: stesso handler della lista (include_in_schema=False), evita il redirect 307.

### GET /api/mutui/statistiche/dashboard — statistiche globali
**Cosa fa**: aggregazione `$group` su tutti i mutui (importi, rate, % completamento capitale, % riconciliazione) + prossime 10 scadenze "Da pagare" entro 30 giorni (parsing date DD/MM/YYYY).

### GET /api/mutui/{mutuo_id} — dettaglio mutuo
**Cosa fa**: documento completo per `mutuo_id` incluse tutte le rate; 404 se assente.

### GET /api/mutui/{mutuo_id}/rate — rate del mutuo
**Cosa fa**: proiezione con solo `rate`, nome e mutuo_id.

### POST /api/mutui/riconcilia — riconciliazione automatica rate
**Cosa fa**: per ogni rata "Pagata" non riconciliata cerca in `estratto_conto_movimenti` un movimento non riconciliato con data ±`tolleranza_giorni` e importo compatibile (±`tolleranza_importo`); se match: marca rata (movimento_bancario_id, data pagamento effettivo) e movimento (riconciliato, tipo_documento=mutuo), incrementa contatori e CREA il movimento `uscita` in `prima_nota_banca` (categoria "Rata mutuo" con quote capitale/interessi); infine ricalcola `percentuale_riconciliazione` per ogni mutuo.
**Note**: la query importi cerca valori NEGATIVI (`importo` tra −max e −min), ma l'estratto conto salva importi POSITIVI con campo `tipo` (documentato in piano_conti.py): con dati standard il match automatico non trova mai nulla. I parametri `data_inizio`/`data_fine` dichiarati non vengono usati nella query.

### PUT /api/mutui/{mutuo_id}/rate/{numero_rata}/riconcilia — riconciliazione manuale
**Cosa fa**: collega una rata a un movimento specifico (lookup per identificatore interno o campo `id`); marca rata e movimento, ricalcola percentuale.
**Note**: `$inc rate_riconciliate` + ricalcolo successivo con `$set`: idempotente solo grazie al secondo passaggio; qui NON viene creato il movimento di prima nota (a differenza della riconciliazione automatica).

### POST /api/mutui/ — crea mutuo
**Cosa fa**: insert del dict raw (400 se `mutuo_id` esistente) con timestamp. **Note**: nessuna validazione Pydantic.

### PUT /api/mutui/{mutuo_id} — aggiorna mutuo
**Cosa fa**: `$set` del body (esclusi _id, mutuo_id, created_at) + updated_at; 404 se non trovato.

### DELETE /api/mutui/{mutuo_id} — elimina mutuo
**Cosa fa**: delete_one per `mutuo_id`; 404 se assente.

### POST /api/mutui/parse-pdf — parse PDF piano ammortamento
**Cosa fa**: estrae dal PDF BPM intestatario, tipo finanziamento, importo accordato, numero delibera e tutte le rate (regex "N dd/mm/yyyy X EUR Y EUR Z EUR Stato") con statistiche (pagato, residuo, prossima rata); NON salva.
**Logica codice**: file temporaneo + pdfplumber; importi it→float (punto migliaia, virgola decimali).

### POST /api/mutui/import-pdf — importa mutuo da PDF
**Cosa fa**: parse + insert/update in `mutui` con `mutuo_id = "mutuo_{numero_delibera}"`; 400 se delibera non estraibile o mutuo esistente senza `aggiorna_esistente=true`; azzera i contatori di riconciliazione.
**Note**: l'update sovrascrive l'array `rate` perdendo le riconciliazioni già fatte sulle rate.

### POST /api/mutui/parse-multiple — parse batch PDF
**Cosa fa**: parse di più PDF in una chiamata; risultati per file con success/error; nessuna scrittura DB.

---

## partite_aperte_api.py (/api/partite-aperte)
Lettura della collezione materializzata `partite_aperte` (popolata dal sistema relazionale/sync, non da questo router). Router con prefix interno `/partite-aperte` montato su `/api`.

### GET /api/partite-aperte/stats — totali per tipo
**Cosa fa**: `$group` per `tipo` delle partite con stato aperta/parziale: count e totale residuo.

### GET /api/partite-aperte/lista — lista filtrata
**Cosa fa**: find con filtri tipo/stato/controparte_id (default stato ∈ aperta/parziale), sort per `data_scadenza`, limit 1–200.

### GET /api/partite-aperte/scadute — partite scadute
**Cosa fa**: partite aperte/parziali con `data_scadenza` < oggi−`giorni_soglia` (esclusi null/vuoti), max 100.

---

## codici_tributari.py (/api/codici-tributari)
Tracciamento pagamenti F24 per codice tributo con riconciliazione a 3 vie (F24 email → pagamento banca → quietanza cassetto fiscale). Fonte primaria: `quietanze_f24` (sezioni erario/inps/regioni/tributi_locali/inail). Dizionario CODICI_TRIBUTO_INFO hardcoded (~15 codici).
**Nota percorsi**: i path interni iniziano con `/codici-tributo/...`, quindi gli URL completi sono ridondanti: `/api/codici-tributari/codici-tributo/...`.

### GET /api/codici-tributari/codici-tributo/lista — codici usati
**Cosa fa**: `$unwind`+`$group` su `quietanze_f24.codici_tributo`: occorrenze e ultimo pagamento per codice, arricchiti con nome/categoria dal dizionario ("Codice non mappato" altrimenti).

### GET /api/codici-tributari/codici-tributo/stato/{codice} — "ho pagato il codice X?"
**Cosa fa**: cerca il codice in tutte le sezioni delle quietanze, filtro opzionale anno/periodo (match substring su `periodo_riferimento`); ritorna pagamenti ordinati per data desc, totali debito/credito/saldo e raggruppamento per periodo.

### GET /api/codici-tributari/codici-tributo/riconciliazione — riconciliazione 3 vie
**Cosa fa**: per ogni codice+periodo dell'anno indica: livello 1 F24 ricevuto (match chiave codice_periodo su `f24_unificato` con stato ricevuto/acquisito/inviato/confermato), livello 2 pagamento banca (presenza di movimenti `prima_nota_banca` con causale regex f24|tribut|erario|inps nello stesso mese — match APPROSSIMATIVO per data), livello 3 quietanza (sempre true, si parte dalle quietanze); raggruppa per categoria con totali.
**Note**: parte solo dalle quietanze: un F24 ricevuto e pagato ma SENZA quietanza non compare affatto nella riconciliazione; il livello 2 confronta `periodo_riferimento[:7]` (es. "01/2024") con `data[:7]` dei movimenti (es. "2024-01") — formati diversi, il flag risulta praticamente sempre false.

### GET /api/codici-tributari/codici-tributo/cerca — ricerca codici
**Cosa fa**: cerca per codice/nome/categoria nel dizionario locale + regex sui codici presenti nelle quietanze (fonte "dizionario" o "quietanze" con occorrenze).
**Note**: il parametro `anno` è dichiarato ma mai usato nella ricerca.

### GET /api/codici-tributari/codici-tributo/riepilogo-annuale/{anno} — riepilogo per categoria
**Cosa fa**: quietanze con `data_pagamento` nell'anno aggregate per categoria (IRPEF, INPS, INAIL, Addizionali, TFR, Credito, Altro): totali debito/credito/saldo e lista codici; utile per dichiarazione redditi.

# Audit "da commercialista" — GestionaleCloud — 03/09/2026

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Verifica in **sola lettura** dei dati reali di produzione (Supabase, progetto
`GestionaleCloud` = `lohczjdiawjryuopncwc`, tabella `gestionale.documents`;
per i cedolini il DB HR `jqguwrahxeilcikplaxi`, tabella `public.app_cedolini`)
incrociati con il codice di `main` (commit `9a9968f`). Nessun file modificato,
nessun commit, nessuna scrittura sul database: l'unica scrittura è questo file.

Domanda del titolare: *"cliccando un dato mi aspetto di trovare la contropartita;
interrogando un avviso bonario voglio estrarre i dati per il controllo
incrociato con il gestionale"*.

---

## 0. Metodo, perimetro e un blocco preliminare

**Metodo.** Per ogni percorso: (a) query SQL sul `data jsonb` di
`gestionale.documents` per ricostruire il dato "a mano"; (b) lettura del
codice che produce lo stesso dato (router/servizio, `file:riga`); (c) confronto.
Tutte le cifre sotto sono lette dal DB al 03/09/2026 (ultima sincronizzazione
Drive registrata: `drive_sync_state.fatture_drive.last_sync =
2026-09-03T18:31Z`). Quando un dato non è ricostruibile lo dico
esplicitamente ("non verificabile") e spiego perché.

**Inventario archivio** (`select collection, count(*) from gestionale.documents
group by 1`): 67 collezioni, le più grandi `pos_terminal_transactions` 3.200,
`fiscal_pages` 1.937, `sumup_transactions` 1.875, `alerts` 1.667,
`corrispettivi` 1.218, `estratto_conto_movimenti` 659, `prima_nota_cassa` 492,
`prima_nota_banca` 351, `partite_aperte` 118, `prima_nota_salari` 92,
`scadenziario_fornitori` 83, `f24_unificato` 19, `cedolini` 18,
`piano_conti` 31, `entity_relations` 23.

### 0.1 BLOCCANTE — la collezione `invoices` (fatture passive) NON esiste nell'archivio

- `gestionale.documents` non contiene **nessun documento** con
  `collection = 'invoices'` (né `fatture_emesse`, `movimenti_contabili`,
  `scritture_contabili`, `quietanze_f24`, `liquidazioni_iva`,
  `bonifici_transfers`, `aliquote_iva`).
- Eppure **101 documenti la referenziano**: `partite_aperte` 96 righe con
  `documento_collection = "invoices"`, `prima_nota_banca` 25 righe con
  `fattura_id`, `scadenziario_fornitori` 83 righe con `fattura_id`, `audit_log`
  7 eventi `azione = "pagata"` su `entita_collection = "invoices"`.
- `drive_sync_state.fatture_drive.last_rebuild_result`: `status: processing`,
  `total: 754`, `imported: 64`, `errors: 4`, `pending: 657`, cartelle Drive
  `Errori: 481`, `Da elaborare: 209`, `Elaborate: 64` (avviato 21/08/2026,
  mai concluso).
- Effetto sul codice: il runtime Supabase idrata in memoria **solo** ciò che è
  in `gestionale.documents` (`app/services/supabase_runtime_database.py:157-197`).
  Quindi in produzione, dopo l'ultimo riavvio, ogni lettura di
  `db["invoices"]` restituisce **zero fatture**: pagina Fatture vuota,
  IVA a credito = 0 (`app/services/iva_liquidation_query.py:128`), Costi del
  Conto Economico = 0 e Debiti v/fornitori = 0 (`app/routers/accounting/bilancio.py:170-185, 330-347`),
  scadenze senza documento, prime note "orfane".
- **Come dovrebbe essere**: le 754 fatture XML della cartella Drive vanno
  ricaricate nell'archivio (rebuild completato, non "processing") e ogni
  riferimento `fattura_id` deve risolvere. Fino ad allora *tutti* i percorsi
  1–3 e 6 sono compromessi e i numeri esposti dal gestionale su costi, IVA a
  credito e debiti verso fornitori sono **sbagliati per difetto** (0).
- **Fix (PR 1, bloccante)**: (a) completare/riparare il rebuild fatture da
  Drive (`app/services/drive_invoice_ingest.py`) con un job che riparte dal
  `cursor` salvato e non resta in `processing`; (b) un controllo di integrità
  referenziale letto all'avvio (`app/routers/verifica_coerenza.py`): conta i
  documenti che puntano a `invoices` inesistenti e apre un alert
  bloccante nel Pannello; (c) test: `tests/test_integrita_riferimenti_fatture.py`
  che inserisce una `partita_aperta` con `documento_id` orfano e verifica che
  `/api/verifica-coerenza/completa/{anno}` la segnali.

---

## 1. Fattura → pagamento → banca → prima nota (contropartita)

**Query base** (25 righe Prima Nota Banca con `fattura_id`, categoria
`Fatture`, `source = ric_auto_identita_unica`, tutte `riconciliato = true`,
create il 29/08/2026 14:07–14:09, join con estratto conto, scadenzario,
partite aperte):

```sql
select p.data->>'fattura_id', p.data->>'importo', p.data->>'estratto_conto_id',
       ec.data->>'descrizione', ec.data->>'riconciliato',
       sc.data->>'numero_fattura', sc.data->>'fornitore_nome', sc.data->>'data_fattura',
       sc.data->>'stato', pa.data->>'stato', pa.data->>'residuo'
from gestionale.documents p
left join gestionale.documents ec on ec.collection='estratto_conto_movimenti' and ec.data->>'id'=p.data->>'estratto_conto_id'
left join gestionale.documents sc on sc.collection='scadenziario_fornitori' and sc.data->>'fattura_id'=p.data->>'fattura_id'
left join gestionale.documents pa on pa.collection='partite_aperte' and pa.data->>'documento_id'=p.data->>'fattura_id'
where p.collection='prima_nota_banca' and p.data->>'fattura_id' is not null;
```

Le 5 fatture 2026 "pagate" esaminate (i dati fattura vengono da
`scadenziario_fornitori`/`partite_aperte`, perché il documento fattura non
esiste — vedi §0.1):

| # | Fattura | Fornitore (identità) | Importo | Data fatt. | Movimento banca (EC) | Prima Nota Banca | Scadenzario | Partita aperta | Esito |
|---|---|---|---|---|---|---|---|---|---|
| 1 | FPR 6/26 | Aniello Limone, P.IVA 07245410639 | 3.122,08 | 11/02/2026 | `EC-2026-02-13-3122.08-3aba68bb` "VS.DISP. … FAVORE ANIELLO LIMONE", `riconciliato=true`, `fattura_match_completo` | `a87b81ac…` 13/02, 3.122,08, riconciliato | pagata 13/02 | chiusa, residuo 0 | **OK** (importo = totale fattura; una sola registrazione; fornitore coerente per nome) — ma senza scrittura in partita doppia (vedi §2) |
| 2 | IT6IGMSABEI | Amazon Business EU S.a.r.l., P.IVA 13397910962 | 11,99 | 13/02/2026 | `EC-2026-02-16-11.99-29944358` "SDD CORE … **AMAZON PAYMENTS EUROPE S.C.A.**", riconciliato | `46d6105f…` 16/02, 11,99 | pagata | chiusa | **WARNING identità**: l'addebito è di *Amazon Payments Europe* (soggetto diverso dal fornitore in fattura); il match vale solo per il token "AMAZON" + importo (`match_score` 10). Lo stesso giorno ci sono 3 SDD Amazon (11,99 / 118,96 / 25,60). Regola `fornitore+importo`, priorità 1, in `app/services/bank_payment_allocations.py:353-377` |
| 3 | 005410193815 | Enel Energia S.p.A. | 2.787,08 | 08/02/2026 | `EC-2026-02-23-2787.08-ba4b1d14` "SDD CORE … ENEL ENERGIA", **`riconciliato=false`** | `d9fd42e5…` 23/02, 2.787,08, **`riconciliato=true`** | **aperta**, `pagato=false` | **aperta**, residuo 2.787,08 | **ERRORE**: tre stati divergenti per la stessa fattura (Prima Nota "riconciliata", banca "non riconciliata", scadenza e partita "aperte"). Un commercialista che clicca la scadenza la vede da pagare, che clicca la Prima Nota la vede pagata |
| 4 | "7" | GSM Marmi Sbordone S.r.l. | 793,00 | n.d. | `EC-2026-03-10-793.00-20905b2d`, riconciliato | `22ef6809…` 10/03, 793,00 (`match_score` 20) | **nessuna riga** | **nessuna partita** | **ERRORE**: `audit_log` dice "Fattura pagata via Bonifico" (29/08 14:09:37) ma non esiste né fattura, né scadenza, né partita: 12 delle 25 registrazioni sono in questa condizione |
| 5 | M012842207 | FASTWEB SpA, P.IVA 12878470157 | 43,86 | **01/04/2026** | `EC-2026-03-25-43.86-23e69765` SDD Fastweb del **25/03/2026** | `af37f6fe…` 25/03 | aperta | aperta, residuo 43,86 | **ERRORE date**: pagamento registrato 7 giorni **prima** della data fattura. Il motore `bank_payment_allocations._identity_evidence` (riga 331-339) vieta `paid_at < invoice_date`, quindi questa riga è stata scritta da un **secondo motore** (`app/services/riconciliazione_bancaria.py:1446`, `source="ric_auto_identita_unica"`) che non applica la stessa regola |

Altri controlli sull'intero insieme:

| Controllo | Query (sintesi) | Risultato | Esito |
|---|---|---|---|
| Doppie registrazioni per la stessa fattura in PN Banca | `group by fattura_id having count>1` | 0 | OK |
| Stesso movimento banca usato da più righe PN Banca | `group by estratto_conto_id having count>1` | **4**: assegni n. 0208770633 (318,66), 0208770634 (1.403,01), 0208770636 (2.496,33), 0208770637 (636,00) registrati **due volte** ciascuno in Prima Nota Banca ("Assegno n. … - riscontro estratto conto") | **ERRORE** (4.853,99 € di uscite duplicate) |
| PN Banca che punta a un EC inesistente | anti-join | 0 | OK |
| Scadenze `pagato=true` senza riga Prima Nota | anti-join | 0 su 5 | OK |
| Righe PN Banca "Fatture" senza scadenza/partita | anti-join | **12 su 25** | ERRORE (vedi #4) |
| PN Banca `riconciliato=true` ma EC `riconciliato=false` | join | **18 su 25** (solo 7 EC hanno `tipo_riconciliazione=fattura_match_completo`) | ERRORE flag incoerenti |
| Pagamento prima della data fattura | `p.data < sc.data_fattura` | 1 (#5) | ERRORE |
| Movimento riconciliato con più fatture stesso importo | `operazioni_da_confermare` | 1 caso corretto: `EC-2026-03-23-2369.00-1e6ecf58` CIERVO FABIANA ↔ 3 fatture FPR 8/10/11-26 da 2.369,00 lasciato "da confermare" | OK (comportamento giusto: nessuna scelta automatica) |
| Uscite banca senza alcuna fattura collegata | `tipo=uscita and riconciliato<>true` | **101 movimenti, 188.970,49 €** (es. A 2000 COSTRUZIONI 18.788 + 15.000 + 12.200 + 9.400; AMODIO 7.817,08; VANDEMOORTELE 4.683,26; LEASYS 3.875,81; CIERVO 3.750 ×2) | Non verificabile se esiste la fattura (archivio fatture assente) |
| Fatture pagate senza movimento banca | — | **non verificabile** (nessuna fattura in archivio) | — |
| Prime note orfane (fattura eliminata/assente) | — | **25/25** puntano a `invoices` inesistenti | ERRORE (conseguenza di §0.1) |
| Contropartita in partita doppia (33.03.01 Fornitori / 19.01.01 Banca) | `movimenti_contabili` | **0 scritture** | ERRORE (vedi §2) |
| Registro relazioni (`entity_relations`) | `group by relation_type` | solo 23 relazioni `allocates_salary_payment`; **nessuna** relazione fattura↔banca | ERRORE: la "Relazioni" del §12 di LOGICA_FUNZIONAMENTO non copre le fatture |

**Cause nel codice e come dovrebbe essere**

- Due motori paralleli decidono "fattura pagata da banca": `app/services/bank_payment_allocations.py:380-458` (`_reconcile_unique_identity_matches`, con controllo date e P.IVA/IBAN) e `app/services/riconciliazione_bancaria.py:1446` (`ric_auto_identita_unica`, quello che ha scritto le 25 righe). Il secondo aggiorna `prima_nota_banca` + `invoices` + `audit_log` ma non sempre `scadenziario_fornitori`/`partite_aperte` (12 righe senza) né `estratto_conto_movimenti.riconciliato` (18 righe). Regola canonica del repo: *un solo sistema per funzione*.
- **Fix (PR 2, alta)**: far scrivere `riconciliazione_bancaria.py` attraverso `persist_bank_invoice_allocations` (`bank_payment_allocations.py:119`) che già aggiorna in un colpo solo fattura, movimento EC, partita aperta e scadenza; eliminare il ramo `ric_auto_identita_unica`. Test: `tests/test_riconciliazione_unica_scrive_tutti_gli_stati.py` — dato un EC + fattura, dopo la riconciliazione `prima_nota_banca.riconciliato`, `estratto_conto_movimenti.riconciliato`, `scadenziario_fornitori.pagato`, `partite_aperte.stato` devono coincidere; dato un EC datato prima della fattura, nessuna associazione.
- **stato 03/09/2026: fatte PR 3 e PR 4** — PR 3: `app/services/assegni_estratto_conto.py`
  (`chiave_idempotenza_assegno` = `assegno:<estratto_conto_id>:banca_uscita`,
  scrittura via `scrivi_movimento_se_assente`), bonifica dei 4 doppioni in
  `app/services/bonifica_prima_nota_doppioni_assegni.py` esposta dallo stesso
  `POST /api/admin/bonifica-prima-nota-doppioni?dry_run=` (registro `banca_assegni`).
  PR 4: `identity_matching.soggetto_pagante_coerente` usato da
  `bank_payment_allocations._identity_evidence` e da
  `riconciliazione_bancaria._evidenza_sdd_fattura_banca` /
  `_evidenza_pagamento_fornitore_banca`: soggetto diverso → proposta
  `operazioni_da_confermare` (`match_type = soggetto_pagante_diverso`).
- **Fix (PR 3, alta)** doppioni assegni: in `app/routers/bank/assegni.py` / `app/services/assegni_estratto_conto.py` la scrittura in Prima Nota deve passare da `scrivi_movimento_se_assente` con chiave `estratto_conto_id` (unicità per movimento). Test: due chiamate consecutive con lo stesso EC → una sola riga.
- **Fix (PR 4, media)** identità fornitore: in `_identity_evidence` (riga 353-360) un match "solo token fornitore" (priorità 1) con più SDD dello stesso creditore nello stesso giorno deve finire in `operazioni_da_confermare`, non essere applicato; per gli SDD usare il mandato (`PK)K,…`) o l'IBAN come identità. Test con i 3 SDD Amazon del 16/02/2026.

---

## 2. Partita doppia e bilancio

**Registro definitivo** (`movimenti_contabili`): **0 documenti**. Il libro
giornale (`GET /api/contabilita-gestionale/libro-giornale`,
`app/routers/accounting/contabilita_gestionale.py:1019`), il libro mastro
(`:1068`) e il bilancio di verifica (`:56-235`) leggono solo quella
collezione: per il 2026 (e per ogni anno) restituiscono **zero scritture**.

- Σ DARE = Σ AVERE per marzo 2026: **non verificabile** (nessuna scrittura).
- **ERRORE di presentazione**: `_bilancio_verifica_da_registro` con zero
  scritture restituisce `quadratura: true` (0 = 0, `registro_valido = True`
  perché non ci sono errori) e `completezza_registro.completo = true` (il
  backlog conta `invoices`, che è vuota). Il commercialista vede "quadra" e
  "completo" su un registro inesistente. `contabilita_gestionale.py:161-182`.
- Le scritture in partita doppia si generano **solo a comando manuale**
  (`POST /api/piano-conti/registra-fattura` `app/routers/accounting/piano_conti.py:726`,
  `/registra-tutte-fatture` `:1225`, `/registra-corrispettivi` `:1236`); nessun
  hook all'import (`app/routers/invoices/fatture_upload.py:1246` lo dichiara).
  Nessuno li ha mai eseguiti in questo archivio.
- Il **Bilancio** (`/api/bilancio/stato-patrimoniale`, `conto-economico`,
  `bilancio.py:76-430`) non usa la partita doppia: SP = saldi Prima Nota Cassa/
  Banca + `invoices` non pagate + cespiti + TFR; CE = `corrispettivi` −
  `invoices`. Con `invoices` vuota: Debiti v/fornitori = 0, Costi = 0, utile =
  ricavi.

**Ricalcolo dei saldi che alimentano lo SP (marzo 2026):**

| Fonte | Query | Valore |
|---|---|---|
| Prima Nota Cassa, entrate "Corrispettivi" marzo | `sum(importo) where categoria='Corrispettivi' and data like '2026-03%'` | 38 righe, **113.148,54 €** su 23 giorni |
| Corrispettivi XML marzo (fonte fiscale) | `sum(totale) from corrispettivi where data like '2026-03%'` | 24 documenti, **67.439,04 €** |
| Differenza | | **+45.709,50 €** = 14 giornate registrate **due volte** in Prima Nota Cassa (09, 10, 17, 18, 20–23, 25–31 marzo; es. 22/03: 4.629,20 × 2 con lo stesso `corrispettivo_id 8eb80d64…`) |

Estensione a tutto l'archivio: 77 giornate con corrispettivo doppio in Prima
Nota Cassa (**+217.025,64 €** di entrate fittizie), 56 giornate con
trasferimento POS doppio in Prima Nota Banca (**+105.428,88 €**) e uscite POS
doppie in Cassa (**+108.275,48 €**). Nella collezione `corrispettivi` invece
**nessun doppione** (chiave `data`): il problema è solo nelle scritture derivate.

Causa: i doppioni hanno `created_at` diversi (es. 03/01/2026: `559de8c4…` del
23/08 03:36 e `41817eed…` del 29/08 14:33; 09/03: 21/08 07:23 e 23/08 03:36),
stesso `corrispettivo_id`, stessa `matricola_rt`, stesso `source`. La guardia di
idempotenza `_scrivi_se_assente` (`app/services/scritture_contabili.py:191-216`,
`find_one_and_update(..., upsert=True)`) **funziona nel singolo processo** (l'ho
verificato con `MemorySheetsClient`: seconda scrittura → `count = 1`) ma è
un'operazione sulla **cache in memoria** del runtime (`SupabaseRuntimeDatabase`
è write-through, non read-through): due processi (deploy sovrapposto, riavvio,
scheduler + web) idratano ciascuno la propria copia e scrivono entrambi. Non
esiste vincolo di unicità lato Postgres.

**Piano dei conti.** Regola del repo: *solo CEE ufficiale*
(`app/services/piano_conti_ufficiale.py`, 231 conti + i conti POS aggiunti in
codice `15.07.01/02/03`, `19.01.05`, `75.01.07.01-04` che **non compaiono** in
`memoria/PIANO_CONTI_UFFICIALE_CERALDI.md`). Nel DB la collezione
`piano_conti` contiene invece **31 conti operativi** (`01.01.01 Cassa`,
`02.01.01 Debiti v/fornitori`, `05.03.01 Salari e stipendi`, …): un secondo
piano dei conti, saldo 0 ovunque. Nelle scritture di Prima Nota il campo
`conto_contabile` è valorizzato **solo** sulle righe POS (`15.07.01`, `15.07.02`,
`19.01.05`, `75.01.07.02`); le 25 righe "Fatture", 48 "Stipendi", 23
"Assegni", 12 "Pagamento PayPal", 9 "Commissioni" hanno `conto = null`
(registrazioni senza conto).

**Fix**

- **stato 03/09/2026: in corso PR 5/6** — codice in `app/services/scritture_contabili.py`
  (chiavi `idempotency_key`), `app/services/supabase_runtime_database.py`
  (rifiuti RPC → cache riallineata), `app/services/bonifica_prima_nota_doppioni.py`
  + `POST /api/admin/bonifica-prima-nota-doppioni?dry_run=`, migrazione
  `supabase/migrations/20260903_idempotency_key.sql` (da applicare DOPO la
  bonifica), bilancio di verifica con stato `REGISTRO_VUOTO`.
- **PR 5 (alta)** — unicità in Postgres: aggiungere una colonna generata
  `idempotency_key text` su `gestionale.documents` (da `data->>'idempotency_key'`)
  con indice **unico** `(collection, idempotency_key) where idempotency_key is not null`;
  `registra_corrispettivo` scrive `idempotency_key = "corr:{corrispettivo_id}:cassa_entrata"`,
  `"…:cassa_uscita:{gestore}"`, `"…:banca_credito:{gestore}"`; l'RPC di upsert
  deve fare `on conflict do nothing` e restituire la riga esistente. File:
  `app/services/scritture_contabili.py`, RPC Supabase, `app/services/supabase_runtime_database.py`.
  Test: `tests/test_idempotenza_cross_processo_corrispettivo.py` (due istanze
  di `SupabaseRuntimeDatabase` sullo stesso store finto → una sola riga).
  Bonifica dati: script in `app/scripts/` che marca `entity_status=deleted`
  la copia più recente delle 77+56+… coppie (già esiste il pattern
  `test_corrispettivi_duplicate_repairs_prima_nota.py`).
- **PR 6 (alta)** — bilancio di verifica onesto: in
  `_bilancio_verifica_da_registro` se `len(scritture)==0` → `quadratura: false`,
  `stato: "REGISTRO_VUOTO"`, e la completezza deve contare i documenti
  sorgente (corrispettivi 1.218, fatture da Drive 754) non registrati, non
  `invoices`. Test in `tests/test_bilancio_verifica_qualita.py`: registro vuoto
  ⇒ `quadratura is False`.
- **PR 7 (media)** — un solo piano dei conti: `piano_conti` (31 conti operativi)
  va convertito via `app/services/mapping_piano_conti.py` e la collezione
  dismessa; ogni riga di Prima Nota deve avere `conto_contabile` CEE
  (Fatture → 33.03.01/19.01.01, Stipendi → 39.07.01/19.01.01, Assegni →
  33.03.01/19.01.01, Commissioni → 75.01.07.xx). Aggiornare
  `memoria/PIANO_CONTI_UFFICIALE_CERALDI.md` con i conti POS. Test: nessuna
  riga scritta da `scritture_contabili.scrivi_movimento` senza `conto_contabile`
  valido in `piano_conti_ufficiale`.
- **stato 03/09/2026: fatta PR 8** — `registrazione_contabile.registra_documento_import`
  (mai solleva, annota `registrazione_contabile_esito` sul documento sorgente)
  è agganciato in `fatture_upload.import_parsed_invoice` e nell'upload manuale
  (dopo l'event bus, perché il handler di classificazione scrive prima
  `iva_detraibile`), in `corrispettivi_helpers.ingest_corrispettivo_parsed`
  (creato/aggiornato/duplicato riparato) e in `CorrispettiviService.process_xml`
  (Drive). Ogni scrittura porta `idempotency_key = reg:<tipo>:<id>` (unica in
  Postgres, migrazione PR 5); un rifiuto remoto → `gia_registrato`, mai
  seconda scrittura. Corrispettivi provvisori (senza XML) rimandati; importo
  cambiato dopo la registrazione → `da_verificare`, mai riscritto. Recupero
  del pregresso: `POST /api/piano-conti/registra-pregresso?dry_run=` (admin,
  idempotente) + `?dry_run=` sui due endpoint esistenti. Bug reale corretto
  nello stesso giro: il motore leggeva `pagato_contante` (singolare, assente
  su 1218/1218 corrispettivi) invece di `pagato_contanti` → ogni giornata
  contanti+POS finiva "da_verificare". Test:
  `tests/test_registrazione_automatica_partita_doppia.py` (import 1 corrispettivo
  + 1 fattura → 2 scritture bilanciate → bilancio REGISTRO_VUOTO → QUADRA).
- **PR 8 (media)** — registrazione automatica: all'import fattura/corrispettivo
  chiamare `registra_fattura`/`registra_corrispettivo` di
  `app/services/registrazione_contabile.py` (idempotenti per `hash`), così il
  libro giornale si alimenta da solo (art. 2216 c.c., 60 giorni).

---

## 3. IVA — 1° trimestre 2026

**IVA a debito ricalcolata dai corrispettivi XML** (`corrispettivi`, stato
`definitivo_xml`, source `xml`):

| Mese | Documenti | Giorni coperti | Totale | Imponibile | IVA | Note |
|---|---|---|---|---|---|---|
| 2026-01 | 24 | 24 | 55.306,78 | 50.278,90 | **5.027,88** | mancano 01/01 e **26–31/01** |
| 2026-02 | **0** | 0 | 0 | 0 | **0,00** | **nessun corrispettivo di febbraio in archivio** (28 giorni mancanti) |
| 2026-03 | 24 | 24 | 67.439,04 | 61.312,78 | **6.131,26** | mancano **01–06/03 e 08/03**; il 07/03 esiste ma a totale 0 |
| **Q1** | 48 | 48 su 90 | 122.745,82 | 111.591,68 | **11.159,14** | |

Coerenza interna: somma delle righe `riepilogo_iva` del trimestre = 47 righe,
unica aliquota **10,00 %** (nessuna natura/esenzione), imponibile 111.591,68,
imposta 11.159,14 = coincide al centesimo con `sum(totale_iva)`. Nessun
corrispettivo doppio nella collezione (0 giorni con più di un documento).
Aliquote non valide: nessuna. Fatture senza aliquota: **non verificabile**
(archivio fatture assente).

**Cosa espone il gestionale** (`GET /api/scadenze/iva-mensile/2026`,
`app/routers/scadenze.py:289`; `GET /api/iva/dashboard/2026/{mese}`,
`app/routers/iva.py:774`; `GET /api/verifica-coerenza/confronto-iva-completo/2026`,
`app/routers/verifica_coerenza.py:131`) — tutti passano da
`get_iva_period_snapshot` (`app/services/iva_liquidation_query.py:93`):

- IVA vendite: stesso algoritmo del mio ricalcolo (dedup per
  `corrispettivo_key` / `data|matricola|totale`, somma `totale_iva`) → gennaio
  5.027,88, febbraio 0,00, marzo 6.131,26. **OK** sul calcolo, ma febbraio
  viene esposto come `CALCOLATO` con vendite 0 e `corrispettivi_iva_non_verificabile`
  solo per i documenti a IVA zero: un mese senza alcun documento non è
  "IVA 0", è "**mese non caricato**". `iva_liquidation_query.py:45-81`.
- IVA acquisti: `db["invoices"].find({"periodo_iva_attribuito": …})` → **0**
  → saldo = intera IVA vendite "da versare" (gen 5.027,88; mar 6.131,26).
  **ERRORE** derivato da §0.1: la liquidazione esposta è tutta a debito.
- Liquidazioni confermate (`liquidazioni_iva`): **collezione assente** →
  nessun credito riportato, nessuna versione, nessuna cronologia (§12-13 di
  `memoria/SPECIFICA_IVA.md` non attuata sui dati).
- Versamento IVA (`verifica_versamento_iva`, `app/services/iva_f24_verifica.py:195`)
  cerca codici 6001-6003 in `f24_unificato`: **non esiste alcun F24 2026**
  (vedi §4) → "non verificabile"; in banca ci sono però gli addebiti
  `I24 AGENZIA ENTRATE` del 16/02/2026 (7.465,55) e 16/03/2026 (3.090,36 +
  915,00 + 600,00 + 437,87) che nessuna pagina collega a un periodo IVA.
- LIPE: `fiscal_documents` ha 27 LIPE (fino a `LIPE_2026_407141844.pdf`) ma
  `fiscal_evidence` contiene solo `document_type` (59 evidenze): i campi
  VP4/VP5 non sono estratti → confronto LIPE ↔ gestionale non verificabile.

**Corrispettivi doppi / chiusure mancanti**: doppi nella fonte 0; doppi nelle
scritture derivate 77 giornate (§2). Giornate senza chiusura RT nel Q1: 42
(elenco: 01/01, 26–31/01, tutto febbraio, 01–06/03, 08/03). La Prima Nota
Cassa di gennaio registra 34 righe "Corrispettivi" per 76.012,45 € contro 24
XML per 55.306,78 €.

**Fix**

- **PR 9 (alta)** — in `get_iva_period_snapshot`: se `corrispettivi_inclusi == 0`
  per un mese concluso → `stato_calcolo = "DATI_MANCANTI"` (non `CALCOLATO`),
  e se `invoices` è vuota per l'anno → `iva_acquisti = null` con motivo
  `archivio_fatture_vuoto` (fail-closed come già fatto in
  `tests/test_iva_credito_fail_closed.py`). Test: mese senza corrispettivi ⇒
  stato `DATI_MANCANTI`; anno senza fatture ⇒ `iva_acquisti is None`.
- **PR 10 (media)** — pagina IVA: per ogni mese mostrare "giorni con
  chiusura RT / giorni del mese" e l'elenco dei giorni mancanti (query già
  pronta: `generate_series` anti-join su `corrispettivi.data`); collegare gli
  addebiti bancari `I24` del 16 del mese al periodo IVA quando manca il
  modello F24 ("F24 mancante — prego caricare", caso 3 della specifica F24).

---

## 4. F24, quietanze e "interroga un avviso bonario"

**Dati.** `f24_unificato`: **19 modelli**, tutti con `codice_fiscale
04523831214`, date versamento dal 20/12/2019 al 15/11/2022, **tutti
`status = da_pagare`, `pagato = false`, senza `quietanza_id` né
`movimento_bancario_id`**, file `…__formato_stampabile__senza_protocollo_AE.pdf`.
`quietanze_f24`: **assente**. `fiscal_documents`: 301 quietanze F24 (indice
Drive, 24 del 2026, es. `2026-04-30__F24_013__quietanza_AE__prot_25011535593911421-000001.pdf`,
fino a `2026-07-22__F24_023__…`) ma senza righe tributo estratte
(`fiscal_evidence` ha solo `document_type`). Banca 2026: **9 addebiti
`I24 AGENZIA ENTRATE` per 21.200,85 €** (16/01: 5.600,93 + 535,70; 02/02:
1.262,44; 16/02: 7.465,55; 06/03: 1.293,00; 16/03: 600,00 + 3.090,36 + 437,87 +
915,00) + 8 `BOLL.CBILL AGENZIA DELLE ENTRATE` (781,60 ×5, 1.260,09 ×3), **tutti
`riconciliato = false`, senza F24 collegato**.

**Esempio reale**: codice tributo **1001** (ritenute lavoro dipendente),
periodo **10/2019**, importo 1.455,21 (F24 `149f2355…`, saldo 2.738,28,
scadenza 20/12/2019; nello stesso modello 1012 893,71; 1655 80,06 e credito
400,00; 8906 40,73; 3802 132,30; 3847/3848).

Cosa offre oggi il gestionale per "interrogare" quel tributo:

| Funzione | Dove | Esito sull'esempio |
|---|---|---|
| `GET /api/f24/verifica-codice/1001?anno=2019&mese=10` | `app/routers/f24/f24_riconciliazione.py:818-921` | cerca **solo** in `quietanze_f24` (vuota) → `pagato: false, pagamenti: []`, poi elenca gli F24 `da_pagare` con quel codice: risponde "in attesa" anche se il versamento del 2019 è ovviamente avvenuto. Nessun incrocio con banca, prima nota, cedolini |
| `GET /api/f24-analisi/tabella?anno=2019` | `app/routers/f24_analisi.py:84` | riga per F24 con periodo prevalente, scadenza naturale, stato `non_pagato` (perché `pagato=false`), causali; **non filtrabile per codice tributo** e non naviga alla quietanza/banca |
| `GET /api/f24-analisi/{id}/associazione?mese=10&anno=2019` | `:195` | esito §15 verso `cedolini` del gestionale (18 documenti, nessuno del 2019) → "non associabile" |
| `GET /api/f24/fascicolo/{cf}/10/2019` | `f24_main.py:1089`, `app/services/fascicolo_f24.py:66` | costruisce fascicolo da `f24_unificato` + `quietanze_f24` (vuota) + `cedolini` (vuoti per il periodo) |
| `GET /api/fiscal/f24-rows?tax_code=1001&year=2019` | `app/routers/fiscal_control.py:172` (solo admin) | legge l'**indice Excel su Drive** (`drive_document_index.list_f24_rows`), non l'archivio: sistema parallelo a `f24_unificato` |
| Pagina UI | `RiconciliazioneUnificata.jsx` tab F24 (tabella analisi, riga 1824) e `SituazioneFiscale.jsx` (filtro `tax_code`, riga 32) | due viste, nessuna con input "tributo + periodo + importo" |

**Esito: ERRORE (funzione mancante).** Non esiste una funzione "avviso
bonario": dato tributo/periodo/importo dell'avviso, il gestionale non
estrae i dati per il controllo incrociato. I dati per farlo però **esistono
già** in archivio:

1. righe tributo dei modelli (`f24_unificato.sezione_erario/inps/regioni/imu`:
   `codice_tributo`, `periodo_riferimento`, `importo_debito/credito`);
2. quietanze (indice `fiscal_documents.category = quietanza_f24`, PDF in
   Drive; righe da estrarre in `fiscal_evidence`);
3. addebiti bancari (`estratto_conto_movimenti.classificazione_tipo = 'f24'`,
   descrizione `I24 AGENZIA ENTRATE … DATA INCASSO gg/mm/aaaa`);
4. ritenute e contributi dei cedolini (DB HR `app_cedolini.doc`: `irpef`,
   `contributi_inps`, `addizionale_regionale`, `addizionale_comunale`, per
   `codice_fiscale`/`anno`/`mese`) — per il codice 1001 la somma delle IRPEF
   del mese deve coincidere con la riga 1001 del periodo;
5. prima nota (oggi assente per gli F24: nessuna riga "Tributi" in
   `prima_nota_banca`).

**Come dovrebbe essere (PR 11, alta)** — `POST /api/f24/avviso-bonario/interroga`
con body `{codice_tributo, periodo: "MM/AAAA", importo_richiesto, anno_imposta}`
che restituisce, in un'unica risposta:
`{righe_f24: [...], quietanze: [...], addebiti_banca: [...] (finestra
scadenza−5/+40 gg), cedolini: {somma_irpef|inps del periodo, n},
totale_versato, differenza_vs_avviso, esito: "COPERTO" | "SCOPERTO" |
"PARZIALE" | "NON_VERIFICABILE", motivazione}`; UI: nel tab F24 un
riquadro "Interroga avviso" (tributo, periodo, importo) che apre i documenti
collegati. Test: `tests/test_avviso_bonario_interroga.py` con il modello
`149f2355…` e un EC `I24` di 2.738,28 al 20/12/2019 ⇒ `esito = COPERTO`;
senza EC ⇒ `SCOPERTO`.
**PR 12 (alta)** — un solo registro F24: `verifica-codice` e il fascicolo
devono leggere anche `fiscal_documents` (quietanze) e `estratto_conto_movimenti`
(I24), e l'import quietanze deve popolare `f24_unificato.quietanza_id` +
`pagato` (oggi 19/19 modelli "da pagare" dal 2019). I 9 I24 2026 senza modello
vanno esposti come alert "F24 mancante" (caso 3 della specifica).

---

## 5. Salari: prima nota salari ↔ cedolini (DB HR) ↔ bonifici

`prima_nota_salari`: 92 righe (16 del 12/2025, 71 del 2026, 5 storiche),
`source = indice_cedolini_drive` (busta) + 2 `cedolino_v2`. DB HR
`app_cedolini`: 1.291 cedolini (2018-2026), **91 del 2026**: gen 13, feb 12,
mar 12, apr 12, mag 14, giu 14, lug 14 (tredicesime/mensili senza PDF).

Le 5 righe verificate:

| # | Riga PN salari | Cedolino HR (`app_cedolini`) | Bonifico banca (`estratto_conto_movimenti`) | Esito |
|---|---|---|---|---|
| 1 | CAPEZZUTO ALESSANDRO 02/2026, busta 801,00, bonifico 430,00, saldo 371, "parzialmente riconciliato" | CPZLSN86D02F839I 2026-02 netto **801,00** ✓ (gennaio: 1.430,00) | `EC-2026-02-20-430.00-b300d6c5` "FAVORE CAPEZZUTO ALESSANDRO" | Netto/dipendente **OK**; **ERRORE periodo**: 430 = 1.430 − 1.000 è il **saldo di gennaio** (acconto 1.000 già erogato), non un acconto di febbraio. Stesso schema il 20/02 per Guarino (1.477−1.000=477), Parisi (458), Taiano (436), Moscato (580), Lesina (86), Russo (122), Vespa (406): 8 bonifici imputati al mese sbagliato |
| 2 | VESPA VINCENZO 01/2026 busta 1.406, bonifico 1.000 (03/02), saldo 406 | VSPVCN67T26F839P 2026-01 netto **1.406** ✓ | `EC-2026-02-03-1000.00` + `EC-2026-02-20-406.00` (= 1.406 esatto) | Il 406 del 20/02 è finito sulla busta di **febbraio** (890, saldo 484) invece di chiudere gennaio: **ERRORE** |
| 3 | MUROLO MARIO 12/2025 busta 1.993, `importo_bonifico` **0**, saldo **−1.993**, `stato_bonifico = riconciliato`, `riconciliato = false`, `movimenti_bancari_ids = [EC-2026-01-07-1993.00-816fb12d]` | MRLMRA04M20F839D 2025-12 netto **1.993** ✓ | `EC-2026-01-07-1993.00` "FAVORE MUROLO MARIO", `riconciliato=true` | Il bonifico c'è ed è agganciato, ma la riga dice bonifico 0 e saldo −1.993: **ERRORE di stato** (idem Parisi 806 e Pocci 1.018 del 07/01) |
| 4 | CERALDI VALERIO 05/2026: **tre righe** — busta 1.186; busta 2.000; "stipendio" 2.000 con `cedolino_id b8ddc1ab…` (`cedolino_v2`) | CRLVLR88H14F839O 2026-05 **un solo** cedolino, netto 2.000 | nessun bonifico collegato (in banca: 3.000 il 12/01 a CERALDI VALERIO non riconciliato) | **ERRORE doppioni** (la stessa busta due volte + una riga 1.186 senza cedolino). Stesso caso CERALDI VINCENZO 05/2026 (2.000 + 1.191 + 2.000) e PARISI ANTONIO 05/2026 (1.231 ✓ + 1.129 senza cedolino) |
| 5 | SANKAPALA_JANANIE 02/2026 954; 03 964; 04 794; 05 798; 06 768,16 | SNKJNY74H48Z209K: **nessun cedolino** da febbraio 2026 (ultimo 2026-01 netto 800) | nessuno | **Righe senza cedolino** (o cedolini mancanti nell'HR): 5 righe non verificabili |

Confronto completo 2026 (nome + mese + netto): febbraio, marzo, aprile,
giugno **coincidono** per tutti i dipendenti presenti in entrambi gli
archivi (12/12, 12/12, 12/12, 13/13). Discrepanze:

- **Cedolini senza riga di prima nota salari**: gennaio 2026 **12 su 13**
  (Ceraldi Antonietta 1.416,24; Capezzuto 1.430; Carotenuto 1.091; Guarino
  1.477; Lesina 1.086; Moscato 1.580; Murolo 859; Parisi 1.458; Pocci 1.012,93;
  Russo 1.122; Sankapala 800; Taiano 1.436 — presente solo Vespa) e luglio
  2026 **14 su 14** (tredicesime + mensili Ceraldi V./Valerio 2.062/2.060).
- **Righe senza cedolino**: Sankapala feb–giu (5), Ceraldi Valerio 05/2026
  1.186, Ceraldi Vincenzo 05/2026 1.191, Parisi 05/2026 1.129, Ceraldi
  Antonietta 12/2025 **1.441** (HR dicembre = 1.540, anche quella presente:
  doppia riga), totale 9.
- Righe duplicate (stessa busta): Ceraldi Valerio e Vincenzo 05/2026
  (`busta` + `stipendio` con `cedolino_id`) — 2.
- Bonifici in banca a dipendenti non collegati: Ceraldi Vincenzo 1.600 (03/02),
  1.550 (10/03), 2.150 (30/03); Ceraldi Valerio 3.000 (12/01).
- Dicembre 2025: i 10 bonifici del 07/01/2026 (Pocci 1.018, Lesina 1.106,
  Guarino 996, Capezzuto 1.190, Murolo 1.993, Parisi 806, Taiano 1.678,
  Moscato 1.761, Vespa 457, Russo 743) coincidono al centesimo con i netti HR
  di dicembre ✓; Carotenuto 1.408 (13/01) ✓; Ceraldi Vincenzo 300+1.000
  (12-14/01) su netto 1.321 → saldo 21 ✓ coerente.

**Cause nel codice**

- Regola di periodo: `app/services/stipendi_bonifici.py:174-186`
  (`_candidati_univoci`) accetta un bonifico per la busta del mese M solo se
  la data cade in **[20/M, 15/M+1]**. Un saldo pagato il 20/02 può quindi
  agganciarsi solo alla busta di **febbraio**, mai a gennaio. La regola scritta
  in `LOGICA_FUNZIONAMENTO.md §7` è l'opposta ("prima del 25 → mese
  precedente"). In più le 12 buste di gennaio non esistono in
  `prima_nota_salari`, quindi il saldo di gennaio non ha comunque una riga su
  cui posarsi.
- Stato "riconciliato" con bonifico 0: `associa_bonifici_stipendi`
  (`stipendi_bonifici.py:430-463`) scrive `importo_bonifico` e `stato_bonifico`;
  la migrazione `recover_salary_relations_20260821_v1` (`migration_runs`) ha
  ricreato 23 `entity_relations` e i `movimenti_bancari_ids` **senza**
  riallineare `importo_bonifico/saldo/riconciliato`.
- Doppioni maggio: due ingressi (`indice_cedolini_drive` via
  `app/routers/accounting/prima_nota_salari.py` import e `cedolino_v2` via
  `sync_prima_nota_salari_da_cedolini` in `app/main.py`) con chiavi diverse
  (`import_key busta_excel:…` vs `cedolino_id`).

**Fix**

- **stato 03/09/2026: fatta PR 13** — `app/services/stipendi_bonifici.py`:
  `competenza_bonifico_stipendio` (giorno < 25 → mese precedente, dal 25 →
  mese corrente; la causale esplicita vince), usata da `_candidati_univoci`;
  `riallinea_competenza_bonifici_stipendi` (dry-run/applica, idempotente:
  sposta il bonifico sulla riga del periodo giusto o lo stacca se la riga
  non esiste, riallinea `importo_bonifico/saldo/stato_bonifico/
  movimenti_bancari_ids`, `stipendio_id` sul movimento e le `entity_relations`)
  eseguito da ogni giro batch di `associa_bonifici_stipendi`; analisi con
  `POST /api/estratto-conto/riconcilia-stipendi?dry_run=true`, CLI
  `python -m app.services.stipendi_bonifici [--applica] [--anno]`. Capezzuto
  430 del 20/02 resta "senza destinazione" finché la riga 01/2026 non esiste (PR 15).
- **PR 13 (alta)** — periodo del bonifico: in `_candidati_univoci` sostituire
  la finestra con la regola documentata: data < 25/M → competenza M−1,
  ≥ 25/M → M, e in ogni caso preferire la busta **più vecchia con residuo
  > 0** dello stesso dipendente (saldo prima di acconto). Test:
  bonifico 20/02/2026 di 430 con busta 01/2026 residuo 430 e busta 02/2026
  residuo 801 ⇒ agganciato a gennaio.
- **PR 14 (alta)** — una sola chiave: `prima_nota_salari` deve avere chiave
  unica `(codice_fiscale, anno, mese, tipo_cedolino)`; l'import Excel e il
  sync da cedolini fanno upsert sulla stessa chiave e riallineano
  `importo_bonifico = Σ movimenti collegati`, `saldo`, `riconciliato`. Test:
  doppio ingresso stesso periodo ⇒ 1 riga; riga con `movimenti_bancari_ids`
  non vuoto ⇒ `importo_bonifico > 0`.
- **PR 15 (media)** — sincronizzazione con l'HR: `sync_prima_nota_salari_da_cedolini`
  deve leggere `app_cedolini` (fonte canonica dei netti, `HR_SUPABASE_DB_URL`)
  e creare le righe mancanti (gennaio e luglio 2026) segnalando in una lista
  "cedolino senza prima nota" / "prima nota senza cedolino" (oggi 26 + 9 casi).
  Nota: nel worktree corrente (non ancora in `main`) è in corso la decisione
  del titolare "un solo archivio cedolini = HR" con il deposito
  `app/services/hr_cedolini_deposito.py` (gestionale → `app_cedolini`);
  questa PR è il verso opposto (HR → prima nota salari) e va costruita sulla
  stessa chiave `(codice_fiscale, anno, mese, tipo_cedolino)` per non creare
  un terzo sistema.

---

## 6. Navigazione "clicco un dato → trovo la contropartita"

Route reali (`frontend/src/main.jsx:88-110`): `/fatture/*`, `/prima-nota/*`,
`/contabilita/*` (bilancio, libro giornale, bilancio di verifica), `/scadenze`,
`/riconciliazione/*`, `/iva/*`, `/situazione-fiscale/*` (admin).

| Da | A | Esiste? | Evidenza (file:riga) |
|---|---|---|---|
| Prima Nota (riga con `fattura_id`) → fattura | modale `ModalFattura` (dati, XML, documenti di pagamento) | **Sì** | `PrimaNota.jsx:767-778`, `ModalFattura.jsx:30-44` |
| Prima Nota (riga corrispettivo) → XML corrispettivo | viewer | Sì | `PrimaNota.jsx:784-800` |
| Prima Nota (riga banca riconciliata) → **movimento estratto conto** | — | **No**: `estratto_conto_id` è usato solo per il badge "riconciliazione" e per la ricerca testuale (`PrimaNota.jsx:131-136`, `banca.py:64-185`); nessun link a `/riconciliazione/banca?movimento=…` | manca |
| Fattura (Archivio fatture) → pagamento / movimento banca / prima nota | badge "Registrazione bancaria riconciliata…" e bottone "In Banca/In Cassa" (che **sposta** la scrittura) | **No** (solo descrizione, `descriviPagamento`): non apre la riga di Prima Nota né l'EC | `ArchivioFattureRicevute.jsx:95-165, 1030-1043` |
| Fattura → candidati bancari | `AssociaMovimentoBanca` (`/api/prima-nota/banca/candidati-per-fattura`) | Sì, solo per associare, dal pannello provvisori | `AssociaMovimentoBanca.jsx:35`, `banca.py:821` |
| Riconciliazione (movimento banca) → fattura | mostra `numero_fattura` come testo, nessun `setFatturaView`/link a `/fatture?invoice_id=` | **No** (il deep-link `/fatture?invoice_id=<id>` esiste, `ArchivioFattureRicevute.jsx:269-291`, ma nessuna pagina lo usa) | `RiconciliazioneUnificata.jsx:1289-1310, 1478` |
| Riconciliazione (movimento stipendio) → riga prima nota salari / cedolino PDF | — | **No** | `entity_relations` esiste (23) ma non è navigata |
| Scadenze → fattura | modale | Sì | `Scadenze.jsx:639-668` |
| Scadenze → movimento che l'ha pagata | — | **No** (`scadenziario_fornitori.movimento_id` è sempre `null` nelle 5 scadenze pagate) | manca |
| Bilancio (SP/CE) riga → registrazioni che la compongono | — | **No**: le voci sono totali da aggregate, nessun drill-down | `Bilancio.jsx:87-88` |
| Bilancio di verifica (conto) → libro mastro / scritture | espansione locale dei primi 50 movimenti (`dettaglio=true`) ma nessun link al giornale né al documento | **Parziale** | `BilancioVerifica.jsx:55`, `contabilita_gestionale.py:101-108` |
| Libro giornale (scrittura) → documento origine (fattura/corrispettivo) | espande le righe Dare/Avere; `fonte_documento`/`invoice_key` non mostrati né linkati | **No** | `LibroGiornale.jsx:194-290`; il backend accetta `?invoice_key=` (`contabilita_gestionale.py:1024`) ma nessuna pagina lo passa |
| IVA (mese) → fatture incluse / corrispettivi del mese | lista fatture per periodo (`/api/iva/fatture?periodo=`) | Parziale (fatture sì, corrispettivi no, F24 IVA no) | `GestioneIVA.jsx:200-201` |
| F24 (riga tabella) → quietanza / addebito banca | icona "🧾 Quietanza" testuale | **No** | `RiconciliazioneUnificata.jsx:1967` |

**stato 03/09/2026: fatta PR 16** — componente unico
`frontend/src/components/LinkContropartita.jsx` (`ROTTE_CONTROPARTITA`, palette
salvia/sabbia). Link: Prima Nota Banca → `/riconciliazione/banca?movimento=`
(campi `estratto_conto_id`/`movimento_estratto_conto_id`/`movimento_bancario_id`/
`estratto_conto_ids`); Riconciliazione (righe, card, pannello del movimento
richiesto via `?movimento=`) → `/fatture?invoice_id=` e
`/prima-nota#sezione=banca&selected=` da `collegamenti` (nuovo campo di
`semanticizza_risultato`: `fattura_id`, `prima_nota_banca_id`, `stipendio_id`,
`assegno_id`, `f24_ids`); Scadenze → movimento pagante (`pagamento.
movimento_bancario_id` da `scadenziario_fornitori.evidenze_pagamento[].evidenza_id`
= `banca:<EC>:<fattura>` o dalla fattura; le pagate entrano con
`include_passate`); Bilancio → `/contabilita/verifica?conto=` →
`/contabilita/giornale?conto=&data_da=&data_a=` / `?scrittura=` → documento
(`fonte_documento`, nuovi campi `codice_ufficiale`, `scrittura_id` nel
bilancio di verifica, filtro `conto` nel libro giornale); F24 →
`documento_collegato.quietanza_url` (fiscal_documents / quietanze_f24) e
`movimento_bancario_id`. Test: `frontend/src/pages/LinkContropartite.navigation.test.jsx`,
`tests/test_link_contropartite_campi.py`.

**Link mancanti da aggiungere (PR 16, media, solo frontend + 2 endpoint di
lettura)**: (1) Prima Nota → EC (`/riconciliazione/banca?movimento=<estratto_conto_id>`);
(2) Riconciliazione → fattura (`/fatture?invoice_id=<fattura_id>`) e →
prima nota (`/prima-nota/banca?movimento=<prima_nota_banca_id>`); (3) Scadenza
→ movimento pagante (valorizzare `movimento_id`); (4) Bilancio → `bilancio-verifica?conto=`
→ `libro-giornale?conto=&data_da=&data_a=` → documento (`invoice_key`/`corrispettivo_id`);
(5) F24 → quietanza (PDF `fiscal_documents`) e → EC `I24`. Ogni link mostra
tipo, id, data, importo e origine (regola §12 di LOGICA_FUNZIONAMENTO).
Test: `frontend/src/pages/*.navigation.test.jsx` per ogni link (pattern già
usato in `RiconciliazioneHub.navigation.test.jsx`).

---

## 7. Tabella riassuntiva per priorità

| Pr. | # | Errore (evidenza) | Dove (file:riga) | Fix atomico (PR) |
|---|---|---|---|---|
| **Bloccante** | 0.1 | Archivio senza fatture: `invoices` = 0 documenti, 101 riferimenti orfani, rebuild Drive fermo a `processing` (64/754) | `app/services/supabase_runtime_database.py:157`, `app/services/drive_invoice_ingest.py`, `drive_sync_state` | PR 1: completare rebuild + alert integrità referenziale + test |
| **Bloccante** | 2 | Libro giornale/mastro/bilancio di verifica vuoti (0 scritture) ma esposti come `quadratura: true`, `completo: true` | `contabilita_gestionale.py:56-235` | PR 6 (stato `REGISTRO_VUOTO`) + PR 8 (registrazione automatica) |
| **Alta** | 2 | Prima Nota duplicata: 77 giornate corrispettivi (+217.025,64 €), 56 trasferimenti POS banca (+105.428,88 €), uscite POS cassa (+108.275,48 €); marzo 2026 cassa 113.148,54 vs XML 67.439,04 | `scritture_contabili.py:191-216, 913-1070`; cache in memoria multi-processo | PR 5: unicità `(collection, idempotency_key)` in Postgres + bonifica |
| **Alta** | 1 | Stati divergenti fattura pagata (18/25 PN≠EC; 12/25 senza scadenza/partita; Enel 2.787,08 "riconciliata" ma partita aperta); pagamento prima della fattura (Fastweb 25/03 vs 01/04) | `riconciliazione_bancaria.py:1446` vs `bank_payment_allocations.py:119-458` | PR 2: un solo motore (`persist_bank_invoice_allocations`) |
| **Alta** | 1 | 4 assegni registrati due volte in PN Banca (4.853,99 €) | `app/services/assegni_estratto_conto.py`, `routers/bank/assegni.py` | PR 3: scrittura idempotente per `estratto_conto_id` |
| **Alta** | 3 | Liquidazione IVA 2026 esposta tutta a debito (acquisti 0) e febbraio "calcolato" con 0 corrispettivi; 42 giorni Q1 senza chiusura RT | `iva_liquidation_query.py:45-81, 128` | PR 9: stati `DATI_MANCANTI` / `archivio_fatture_vuoto` |
| **Alta** | 4 | Nessuna funzione "avviso bonario"; `verifica-codice` legge solo `quietanze_f24` (vuota); 19/19 F24 2019-22 "da pagare"; 9 I24 2026 (21.200,85 €) senza modello | `f24_riconciliazione.py:818-921`, `fascicolo_f24.py:66`, `fiscal_control.py:172` | PR 11 (endpoint interroga avviso) + PR 12 (un solo registro F24/quietanze/banca) |
| **Alta** | 5 | Bonifici stipendio imputati al mese sbagliato (8 saldi di gennaio 2026 sul mese di febbraio, es. Capezzuto 430, Vespa 406) | `stipendi_bonifici.py:174-186` vs `LOGICA_FUNZIONAMENTO.md §7` | PR 13 |
| **Alta** | 5 | Prima nota salari incompleta/duplicata: 26 cedolini senza riga (gen 12, lug 14), 9 righe senza cedolino, 2 buste doppie (Ceraldi V./Valerio 05/2026), 3 righe con bonifico agganciato ma `importo_bonifico = 0` | `prima_nota_salari.py` import, `app/main.py` sync, migrazione `recover_salary_relations_20260821_v1` | PR 14 + PR 15 |
| **Media** | 1 | Match fattura↔SDD su solo token "AMAZON" + importo, con soggetto pagante diverso (Amazon Payments Europe) | `bank_payment_allocations.py:353-377` | PR 4 |
| **Media** | 2 | Due piani dei conti (31 operativi in `piano_conti` vs CEE ufficiale); conti POS `15.07.xx/19.01.05/75.01.07.0x` assenti dal documento ufficiale; 117 righe di Prima Nota senza `conto_contabile` | `piano_conti_ufficiale.py`, `mapping_piano_conti.py`, `PIANO_CONTI_UFFICIALE_CERALDI.md` | PR 7 |
| **Media** | 3 | Pagina IVA senza indicatore giorni RT mancanti e senza aggancio degli addebiti `I24` del 16 del mese | `scadenze.py:289`, `GestioneIVA.jsx` | PR 10 |
| **Media** | 6 | Link mancanti: Prima Nota→EC, Riconciliazione→fattura/prima nota, Scadenza→movimento, Bilancio→verifica→giornale→documento, F24→quietanza/EC | vedi §6 | PR 16 |
| **Media** | 1 | Registro relazioni (`entity_relations`) solo per stipendi (23); nessuna relazione fattura↔banca↔prima nota | `accounting_relation_writers.py` | rientra in PR 2 (scrivere la relazione in `persist_bank_invoice_allocations`) |

**Cosa NON è stato possibile verificare e perché**: importo totale = imponibile
+ IVA per fattura, fatture pagate senza movimento banca, fatture senza
aliquota, IVA a credito Q1, coerenza fornitore per P.IVA (archivio `invoices`
assente, §0.1); Σ DARE = Σ AVERE (nessuna scrittura); versamento IVA e F24 2026
(nessun modello F24 2026, quietanze senza righe estratte); confronto LIPE
(campi non estratti); risposta HTTP reale degli endpoint (nessuna istanza del
backend avviabile in questo ambiente contro Supabase: verificato leggendo il
codice e riproducendo gli algoritmi in SQL).

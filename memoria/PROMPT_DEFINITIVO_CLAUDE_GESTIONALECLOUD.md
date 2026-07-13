# PROMPT DEFINITIVO PER CLAUDE — CONSOLIDAMENTO TECNICO GESTIONALECLOUD

> **QUESTO FILE È IL PUNTO DI PARTENZA.** Ogni volta che l'utente lo chiede, riparti
> da qui. Aggiorna la sezione "STATO AVANZAMENTO" a ogni step concluso. Rispondi
> sempre in italiano (anche in chat).

## STATO AVANZAMENTO (aggiornato ad ogni step)

Baseline: `b9ff5c7` · 257 test verdi · 1105 route · avvio lavori 13/07/2026.

### FASE P0 — Bug di correttezza (§4)  — dettaglio in memoria/BUG_CORRETTI_2026-07.md
- [x] P0.1 Widget F24 legge sorgente sbagliata — conta_f24_da_pagare, test
- [ ] P0.2 Auto-riconciliazione filtra importi negativi inesistenti  ✅ fatto (test)
- [x] P0.3 Libro Unico usa `employees`, TFR usa `dipendenti` — canonica dipendenti + migrazione
- [x] P0.4 Verbali cercano `items.descrizione` invece di `linee` — linee.*, test
- [x] P0.5 Stato assegno "associato" non valido — "assegnato" + migrazione + test
- [x] P0.6 Force reimport non rispetta il contratto — docstring veritiero + alias /reimport
- [x] P0.7 Riconciliazione F24 scrive/legge collection diverse — upload su estratto_conto_movimenti + test
- [x] P0.8 Processo F24 scaricati usa contratto parser errato — allineato al contratto reale + test
- [x] P0.9 Pagamento fattura non idempotente — chiave idempotenza + indice unique
- [x] P0.10 Stato job solo in memoria — persistito su MongoDB job_state
- [x] P0.11 Gestione riservata protetta solo dal frontend — auth backend header + test
- [x] P0.12 Token in query string — header X-API-Key + fallback deprecato + test

**FASE P0 COMPLETATA**: tutti i 12 bug corretti con test (287 test verdi, +30 su baseline).
PROSSIMA FASE: P1 consolidamento collection/motori (§5-§8).

### FASE P1 — Consolidamento collection/motori (§5-§8)  — IN CORSO
- [x] §5.1 F24: canonica f24_unificato + helper f24_canonico + migrazione idempotente
      + redirect lettori/scrittori legacy + f24_analisi solo canonica (293 test).
      Sottosistemi parser (f24_pagamenti/tributi_pagati/distinte_f24) e f24_tributi: rinviati (vivi).
- [x] §5.4 Fatture passive: canonica invoices + helper fatture_canonico + migrazione
      + ponte ERP su invoices + rimosso dedup runtime crud (297 test).
- [x] §5.3 Cedolini: canonica `cedolini` + helper cedolini_canonico (chiave naturale
      contribuente+anno+mese) + migrazione payslips→cedolini + payslips deprecata (301 test).
      DEBITO: `buste_paga` (Libro Unico/BPM/TFR, vivo) rinviata a fase paghe dedicata.
- [x] §5.2 Dipendenti: employees→dipendenti (P0.3), payslips→cedolini (§5.3),
      employee_contracts→contratti_dipendenti (canonica CRUD; FIX cessazione che
      terminava i contratti sull'alias vuoto) + test, staff→dipendenti (deprecata).
      Migrazioni: migra_employee_contracts_a_contratti / migra_staff_a_dipendenti (302 test).
- [x] §5.5 Fatture emesse: canonica `fatture_emesse` (scelta utente: "un unico posto
      reale"). Risolto split-brain (writer su invoices_emesse, lettori su fatture_emesse):
      redirect writer CRUD + ragioneria/dashboard/piano_conti → fatture_emesse; invoices_emesse
      deprecata + migrazione. Follow-up: armonizzare gli schemi campi dei lettori (304 test).
- [x] §5.6 Estratto conto: canonica movimenti `estratto_conto_movimenti` (già usata
      ovunque; P0.7 aveva già redirezionato l'import F24-banca). `estratti_conto` tenuta
      SEPARATA (registro documenti EC, non movimenti). estratto_conto/bank_statements/
      movimenti_f24_banca deprecate (nessun accesso; nessun merge dei backup) (306 test).
- [x] §5.7 Fornitori: canonica `fornitori` (già consolidata: COLL_SUPPLIERS/
      Collections.SUPPLIERS/SupplierCollections.SUPPLIERS = fornitori; nessuna scrittura
      su `suppliers` letterale; POST /api/suppliers pubblico scrive in fornitori).
      Blindato con test-guardia (308 test).
- [x] §5.8 Documenti classificati: unificati su `documenti_classificati` (scelta utente).
      Redirect pipeline email (email_classifier_service/document_ai) → canonica con
      mapping campi; LM esclude pdf_base64 dalle liste; migrazione documents_classified.
      Effetto: doc email visibili in Learning Machine (312 test).
- [x] §5.9 Magazzino: già conforme (nessuna nuova scrittura di giacenza sulle 6 collezioni;
      solo delete di pulizia su warehouse_stocks deprecata; collezioni condivise non droppate).
      Marcate §5.9 NO-WRITE + test-guardia. **§5 COMPLETATA** (313 test).
- [~] §6 Motori contabili: §6.1 FATTO (scelta utente: solo §6.1 schema CEE) — motore unico
      app/services/registrazione_contabile.py (idempotenza/numero registrazione/fonte doc/
      data competenza/DARE-AVERE/centro costo/audit/ricostruzione); i 3 endpoint
      (registra-fattura, registra-tutte-fatture, registra-corrispettivi, ricategorizza-fatture)
      delegano al motore; ricategorizza conserva la categorizzazione ricca (deducibilità IRES/
      IRAP) e ora preserva ammortamenti/TFR (prima li cancellava). FIX giornale: date coerenti.
      §6.2/6.3/6.4 (bilancio unico, schema numerico contabilita_italiana, saldi Prima Nota):
      RINVIATE (contabilità viva, richiedono decisione schema canonico) (316 test).
- [~] §6.2-6.9: ANALISI prodotta (memoria/ANALISI_MOTORI_CONTABILI.md) con stato/rischio/
      decisione per ogni sottosistema. §6.3 (schema piano conti CEE vs numerico) = decisione
      utente BLOCCANTE per §6.2. Ordine sicuro: §6.4 saldo Prima Nota → §6.6 EC → §6.3 → §6.2
      → §6.8 cash adapter/§6.5/§6.9/§6.7. Implementazione in attesa scelta schema.
      Scelte utente: schema canonico = CEE puntato; ritmo = solo lavori sicuri uno per uno.
- [x] §6.4 saldo Prima Nota: funzione unica common.aggrega_saldo_prima_nota (segno/riporto/
      saldo finale) usata da cassa.py e banca.py, valori invariati + test caratterizzazione
      (324 test). Follow-up: allineare query anno banca↔cassa (anno==""); stats/manutenzione.
- [x] §6.6 EC importer: VERIFICATO già adapter corretto — bank_statement_import scrive i
      movimenti nella canonica estratto_conto_movimenti (dedup+alert); bank_statements_imported
      = solo metadati statement, nessun lettore riconciliazione. Nessun ricablaggio.
      §6.5 cespiti (canonico cespiti.py, parallelo contab_italiana deprecato) · §6.8 cash
      adapter (campi canonici in prima_nota_cassa) · §6.9 verbali (ruoli documentati) FATTI.
      §6.7 PayPal + refactor endpoint verbali RINVIATI (dominio ampio, sessione dedicata).
- [x] §6.2/§6.3 PIANO UFFICIALE: l'utente ha fornito il bilancio ufficiale → canonico =
      piano CEE del commercialista (231 conti) in app/services/piano_conti_ufficiale.py +
      doc memoria/PIANO_CONTI_UFFICIALE_CERALDI.md. mapping_piano_conti.OPERATIVO_A_UFFICIALE
      (codice interno→ufficiale) + classifica_saldi_ufficiale (vista derivata). Regola in
      CLAUDE.md. Bilancio (`piano_conti /bilancio`) ora espone anche `bilancio_ufficiale`
      (vista in codici ufficiali), output storico invariato (329 test).
      Nota: i codici interni collidono con gli ufficiali → si converte sempre.
- [x] §7 Classificazione endpoint: deliverable memoria/ENDPOINT_CLASSIFICAZIONE_FINALE.md
      generato da scripts/genera_classificazione_endpoint.py (rigenerabile) sulla route
      table reale, incrocia FE/scheduler/chat/migrazione/test. 1106 endpoint: 650 tenere,
      437 verificare (nessun rif. noto → NON eliminare in blocco), 19 admin-only (migrazione/
      manutenzione one-shot). Follow-up: applicare guard Admin-only ai 19.
- [x] §8 Viewer documenti: componente canonico frontend DocumentViewerModal.jsx completato
      con tutte le funzioni §8.2 (Chiudi/Scarica/Schermo intero/Zoom±/Adatta larghezza/
      Adatta pagina/scroll interno/touch-pinch/blocco body/focus trap/ESC/aria-label/
      role=dialog aria-modal/ritorno focus all'origine/documentType). Build FE OK.
      Adozione nei call site (documentType) come rollout progressivo.
**FASE P1 (§5-§8) COMPLETATA.** Restano §6.2-6.9 (contabilità viva, rinviate) come debito.
      Deliverable: memoria/PIANO_MIGRAZIONE_COLLECTION.md, memoria/ENDPOINT_CLASSIFICAZIONE_FINALE.md
### FASE P1 — F24/quietanze/IVA/prestazioni (§9-§11) — COMPLETATA
- [x] §9 F24/quietanze/cedolini: regole già implementate/testate (associazione,
      DM10/RC01, doppio pagamento, deducibilità); +stato canonico QUIETANZA_PRESENTE_F24_MANCANTE
      (§9.3) + test regressione (nessuna ricostruzione automatica).
- [x] §10 IVA: modulo maturo non riscritto; aggiunti i 7 test scenario mancanti
      (più aliquote, indetraibile parziale, recupero annuale, concorrenza conferme...).
- [x] §11 Prestazioni: to_list(None) → tetto+log; §11.4 job state già fatto (P0.10);
      deliverable memoria/AUDIT_PERFORMANCE_N1.md per i 22 to_list(100000)/N+1 (da
      valutare uno per uno: aggregazioni finanziarie non troncabili a blocco).
### FASE P2 — Sicurezza/pulizia (§12-§13) — IN CORSO
- [x] §12.6 no segreti nei log (ai_document_parser, whatsapp_webhook) + §13.2 rimosso
      modulo morto referential_integrity.py.
- [x] §12 guardia Admin-only su TUTTI i 13 endpoint distruttivi di migrazione/manutenzione
      (reset/cleanup/reimport/backfill/migra) — erano senza controllo ruolo. Test route table.
- [x] §12.2 fail-fast produzione: opt-in via env SECRET_KEY_REQUIRED=true (default off,
      comportamento invariato) — rifiuta l'avvio se SECRET_KEY manca in produzione.
- [x] §13.2 router non montati: verificato 0 (backend già pulito su questo fronte).
- [x] §12.7 protezione download VERIFICATA: tutti gli endpoint PDF usati dai viewer sono
      sotto /api/* e FUORI dall'allowlist → il middleware globale li protegge; gli <iframe>
      funzionano perché stessa origine → il browser invia il cookie access_token (rinnovo
      scorrevole incluso). Nessun Depends per-endpoint necessario. Verbale PayPal usa già
      blob-fetch autenticato.
- [x] §13.1 frontend primitive COMPLETATO: alert() ✅ (79 → toast sonner) · confirm() ✅
      (16 → ConfirmDialog) · prompt() ✅ (dialog PIN in-app in Utenti.jsx) · window.open ✅
      rivisti tutti (6 documenti → DocumentViewerModal: F24, doc non associati, ricevuta
      PagoPA, verbale PayPal blob; 7 legittimi tenuti: export Excel/PDF/ZIP, stampa,
      navigazione interna, fallback fattura). Build verde ad ogni passo.
      Esiste il sistema canonico (ConfirmDialog/use-toast) già parzialmente adottato, ma la
      conversione (specie confirm→dialog dichiarativo) cambia il control-flow: non
      automatizzabile in sicurezza. Deliverable checklist: memoria/AUDIT_PRIMITIVE_FRONTEND.md.
- [x] §12 allowlist endpoint pubblici CHIUSA: l'auth è centralizzata in
      app/middleware/authentication.py (AuthenticationMiddleware montato in main.py) che
      protegge OGNI /api/* con JWT salvo allowlist esplicita (health, login/setup, webhook
      WhatsApp con verify_token, ponte ERP con secret, pagine legali, docs, SEO). Lo scan
      per-route "75 protette / 1031 pubbliche" era fuorviante: le dependency per-route sono
      il secondo livello (ruoli/admin), il primo è il middleware. Aggiunto test-fotografia
      (tests/test_sicurezza_auth.py::TestAllowlistCongelata) che congela l'intera allowlist
      con set-equality + verifica che il middleware sia montato: ogni nuovo path pubblico fa
      fallire la suite. NOTA /api/v1 (API key esterne): oggi richiede ANCHE il JWT perché
      non è whitelistato — canale di fatto spento verso l'esterno; NON whitelistato di mia
      iniziativa (regola parametri: /api/v1/keys/generate non ha altra auth propria,
      aprirlo permetterebbe a chiunque di generare chiavi). Decisione lasciata all'utente.
- [ ] §13.2 altro codice morto (stub/v1): da fare con verifica.
### FASE FINALE — Verifiche e deliverable (§14-§17) — COMPLETATA (2026-07-13)
- [x] §15.3 mappe rigenerate: genera_mappa.py (1106 endpoint, 107 prefissi, FE ✓=639)
      + genera_classificazione_endpoint.py (650 tenere / 437 verificare / 19 admin-only).
- [x] §15.1/15.2 suite 335 passed 2 skipped (baseline 257) · build Vite verde.
- [x] §14 memoria/MATRICE_FUNZIONALE_FINALE.md (13 moduli, catena Route→…→Test).
- [x] §8.6 memoria/AUDIT_VIEWER_DOCUMENTI.md (censimento viewer + auth).
- [x] §16 memoria/AUDIT_ESECUZIONE_DEFINITIVO.md con verifica puntuale dei 19
      criteri §17 (tutti ✅) + rischi residui e decisioni richieste (/api/v1,
      §6.7 PayPal, to_list, migrazioni al deploy).

---

## 0. Mandato

Lavora sul repository:

```text
ceraldicontabilita/GestionaleCloud
```

Branch operativo e di consegna:

```text
main
```

Baseline verificata:

```text
b9ff5c767cbef33c457b8cff091987b86a90c56f
```

Alla baseline:

- `main` e il precedente branch di lavoro risultano allineati;
- il frontend Vite compila;
- il backend monta **1105 endpoint**;
- sono presenti **137 file router**;
- **639 endpoint** risultano richiamati dal frontend;
- **76 endpoint** risultano usati da chiamanti esterni, scheduler, webhook, chatbot o API pubbliche;
- **390 endpoint** sono ancora da classificare;
- il registro contiene **158 collection MongoDB**;
- risultano **257 test backend verdi**.

Questo documento sostituisce i vecchi audit come piano operativo.  
Usa come fonti di verità tecniche:

```text
memoria/AUDIT_RICOGNIZIONE_2026-07-13.md
memoria/MAPPA_MODULI.md
memoria/MAPPA_ROUTER.md
memoria/MAPPA_ENDPOINT_COMPLETA.md
memoria/MAPPA_COLLEZIONI.md
app/router_registry.py
app/db_collections.py
frontend/src/main.jsx
frontend/src/navigation.config.js
```

Le mappe devono essere rigenerate dopo ogni fase con:

```bash
python scripts/genera_mappa.py
```

---

# 1. Regole di esecuzione

1. Lavora direttamente su `main`.
2. Prima di modificare un modulo, verifica:
   - chiamanti frontend;
   - scheduler;
   - Chat intelligente;
   - webhook;
   - applicazioni esterne;
   - script di manutenzione;
   - test.
3. Non eliminare nulla soltanto perché non è chiamato direttamente dal frontend.
4. Non cancellare collection di produzione: prima migrazione, verifica, archiviazione non distruttiva.
5. Ogni modifica deve mantenere:
   - build frontend verde;
   - bootstrap FastAPI;
   - test esistenti;
   - tracciabilità dei dati.
6. Non introdurre nuove collection se una collection canonica esiste già.
7. Non introdurre nuovi router paralleli per una funzione già presente.
8. Ogni correzione deve avere almeno un test di regressione.
9. Non usare catch silenziosi che trasformano un errore in “nessun dato”.
10. Dopo ogni fase:
    - esegui test;
    - rigenera mappe;
    - aggiorna il report finale;
    - committa su `main`.

---

# 2. Confine funzionale definitivo

## 2.1 GestionaleCloud è un ERP contabile e fiscale

Deve mantenere:

- Dashboard;
- fatture passive e attive;
- fornitori;
- Corrispettivi;
- POS;
- Prima Nota Cassa;
- Prima Nota Banca;
- Prima Nota Salari;
- estratti conto;
- bonifici;
- assegni;
- PayPal;
- riconciliazioni;
- Piano dei Conti;
- Bilancio;
- Contabilità gestionale;
- Contabilità avanzata;
- Centri di costo;
- cespiti;
- mutui;
- chiusura esercizio;
- IVA;
- F24;
- quietanze;
- cedolini;
- Libro Unico;
- TFR;
- documenti fiscali;
- import documenti;
- Chat intelligente;
- Dizionario Articoli contabile;
- storico acquisti;
- Previsioni Acquisti.

## 2.2 HACCP è esterno

Non devono essere ricreati in questo repository:

- ricettario;
- ricette;
- lotti;
- tracciabilità;
- produzione;
- cucina;
- food cost operativo;
- schede tecniche HACCP;
- giacenze fisiche;
- inventario HACCP;
- alert sotto-scorta;
- miglior fornitore HACCP.

Il solo modulo warehouse interno ammesso è:

```text
app/routers/warehouse/dizionario_articoli.py
```

con finalità contabili:

- normalizzazione descrizioni;
- alias;
- classificazione;
- collegamento Piano dei Conti;
- storico acquisti;
- Previsioni Acquisti.

Non cancellare dati HACCP condivisi da altre applicazioni. Eventuali collection residue devono essere soltanto archiviate tramite script non distruttivo.

---

# 3. Architettura reale da rispettare

## 3.1 Backend

Registrazione router unica:

```text
app/router_registry.py
```

Gruppi reali:

```text
auth
f24
accounting
bank
warehouse
invoices
employees
reports
core
email
noleggio
ai
```

Struttura target:

```text
router
→ service
→ engine
→ repository/accessor
→ MongoDB
```

I router devono gestire soltanto:

- autenticazione;
- autorizzazione;
- validazione;
- chiamata al dominio;
- risposta HTTP.

## 3.2 Frontend

Entry point reale:

```text
frontend/src/main.jsx
frontend/src/App.jsx
```

Build:

```text
React 18 + Vite
```

Navigazione canonica:

```text
frontend/src/navigation.config.js
```

Non reintrodurre:

```text
frontend/src/App.js
frontend/src/index.js
craco.config.js
plugin Emergent
```

## 3.3 Database

Database:

```text
Gestionale
```

Registro canonico:

```text
app/db_collections.py
```

Non usare nomi collection hardcoded quando esiste una costante canonica.

---

# 4. FASE P0 — Correggere i bug di correttezza già individuati

Questi problemi sono stati trovati leggendo il codice e devono essere corretti prima della pulizia ulteriore.

## P0.1 Widget F24 legge la sorgente sbagliata

Problema:

```text
scadenze.py
f24_da_pagare_commercialista
```

legge `f24_unificato`, mentre alcuni F24 email risultano ancora in una sorgente legacy.

Azione:

1. Migrare ogni F24 valido verso `f24_unificato`.
2. Vietare nuove scritture nelle collection legacy.
3. Fare leggere il widget esclusivamente dalla collection canonica.
4. Aggiungere test:
   - F24 importato manualmente;
   - F24 importato da email;
   - stesso risultato nel widget.

## P0.2 Auto-riconciliazione filtra importi negativi inesistenti

Problema:

```text
batch_operations.py
POST /auto-riconcilia-tutto
```

filtra `importo < 0`, ma `estratto_conto_movimenti` memorizza importi positivi con una tipologia separata.

Azione:

- usare `tipo`, `segno`, `dare_avere` o il campo canonico effettivo;
- aggiungere test con movimento in uscita;
- impedire che il job restituisca sempre zero candidati.

## P0.3 Libro Unico usa `employees` e TFR usa `dipendenti`

Problema:

```text
libro_unico_parser.py
```

crea/aggiorna `employees`, mentre il resto dell’app e il TFR cercano in `dipendenti`.

Azione:

- usare esclusivamente `dipendenti`;
- migrare i documenti legacy;
- normalizzare la chiave dipendente;
- verificare aggancio cedolino → dipendente → TFR → Prima Nota Salari.

## P0.4 Verbali cercano un campo fattura inesistente

Problema:

```text
verbali_riconciliazione.py
```

cerca `items.descrizione`, mentre le fatture usano `linee`.

Azione:

- usare il campo canonico;
- aggiungere test con descrizione presente in `linee`.

## P0.5 Stato assegno non valido

Problema:

```text
assegni.py
/correggi-associazione
```

scrive:

```text
stato = associato
```

ma il valore non appartiene a `ASSEGNO_STATI`.

Azione:

- scegliere lo stato canonico esistente;
- validare lato schema;
- migrare eventuali record con valore invalido.

## P0.6 Force reimport non rispetta il contratto

Problema:

```text
estratto_conto.py
/force-reimport
```

dichiara di cancellare l’anno, ma non lo fa.

Azione:

- rinominare l’endpoint se deve mantenere i dati;
- oppure implementare cancellazione/archiviazione esplicita con conferma;
- nessuna cancellazione distruttiva senza backup e ruolo Admin.

## P0.7 Riconciliazione F24 scrive e legge collection diverse

Problema:

```text
POST /api/f24-riconciliazione/upload-estratto-bpm
```

scrive in `movimenti_f24_banca`, ma:

```text
POST /api/f24-riconciliazione/riconcilia-f24
```

legge `estratto_conto_movimenti`.

Azione:

- usare come fonte canonica `estratto_conto_movimenti`;
- convertire l’import BPM allo schema canonico;
- migrare o archiviare `movimenti_f24_banca`;
- test upload → riconciliazione.

## P0.8 Processo F24 scaricati usa contratto parser errato

Problema:

```text
documenti.py
/processa-f24-scaricati
```

si aspetta `success` e `f24_data`, ma il parser non restituisce quel contratto.

Azione:

- definire un DTO unico del parser;
- aggiornare tutti i chiamanti;
- testare PDF valido, PDF non F24, parser fallito e duplicato.

## P0.9 Pagamento fattura non idempotente

Problema:

```text
multi_pagamento.registra_pagamento
```

usa una chiave Prima Nota diversa dal flusso di conferma fattura e può creare doppioni.

Azione:

- introdurre una chiave idempotente unica per fattura/pagamento;
- indice unique o controllo atomico;
- test chiamata ripetuta;
- test passaggio dello stesso documento da due pipeline.

## P0.10 Stato job solo in memoria

Problema:

```text
batch_reprocessing._job_state
task riconciliazione bonifici
```

usano variabili globali.

Azione:

- persistere stato job in MongoDB;
- supportare restart e multi-worker;
- aggiungere TTL o politica di conservazione.

## P0.11 Gestione riservata protetta solo dal frontend

Problema:

```text
gestione_riservata.py
```

non verifica il codice negli endpoint `/movimenti` e registra il codice errato in chiaro.

Azione:

- autorizzazione obbligatoria backend;
- mai loggare il segreto;
- hash/confronto costante;
- test accesso non autorizzato.

## P0.12 Token in query string

Problema:

```text
openapi_*
API pubblica /api/v1
```

accettano `?token=` o `?api_key=`.

Azione:

- usare header `Authorization` o `X-API-Key`;
- mantenere eventuale compatibilità temporanea con warning;
- non scrivere token nei log;
- documentare rimozione del formato query.

---

# 5. FASE P1 — Consolidamento delle collection

## 5.1 F24: attualmente frammentato

Sorgenti rilevate:

```text
f24_unificato          CANONICA
f24_commercialista     legacy
f24_tributi            classificazione documenti
f24_models             legacy chat/public
f24_pagamenti          sottosistema parser
tributi_pagati         sottosistema parser
distinte_f24           sottosistema parser
quietanze_f24          prova pagamento, resta separata
```

Obiettivo:

```text
f24_unificato
quietanze_f24
```

Eventuali dettagli riga possono essere embedded oppure in una collection figlia unica chiaramente documentata.

Azioni:

1. Inventario dei documenti.
2. Definizione schema canonico.
3. Migrazione idempotente.
4. Deduplica per:
   - contribuente;
   - periodo;
   - saldo;
   - hash PDF;
   - protocollo;
   - codici tributo.
5. Aggiornamento:
   - F24 main;
   - parser;
   - email;
   - Chat;
   - public API;
   - analisi;
   - dashboard;
   - scadenze.
6. Blocco delle scritture legacy.
7. Archiviazione non distruttiva.

## 5.2 Dipendenti

Canonica:

```text
dipendenti
```

Legacy:

```text
employees
staff
payslips
employee_contracts
```

Distinguere:

- anagrafica → `dipendenti`;
- cedolini → `cedolini`;
- contratti → `contratti_dipendenti`;
- presenze contabili/LUL → collection canonica documentata.

## 5.3 Cedolini

Canonica:

```text
cedolini
```

Legacy/parallele:

```text
buste_paga
payslips
riepilogo_cedolini
cedolini_email_attachments
```

Non eliminare gli allegati email: sono documenti origine.  
Separare chiaramente:

- file ricevuto;
- cedolino elaborato;
- riepilogo aggregato.

## 5.4 Fatture passive

Canonica:

```text
invoices
```

Legacy:

```text
fatture_passive
```

Rimuovere il dedup runtime tra due sorgenti dopo la migrazione.

## 5.5 Fatture emesse

Scegliere una sola collection:

```text
fatture_emesse
```

oppure, se il codice reale dimostra il contrario:

```text
invoices_emesse
```

La scelta deve essere documentata e tutti i router aggiornati.  
Non mantenere entrambe.

## 5.6 Estratto conto

Canonica:

```text
estratto_conto_movimenti
```

Legacy/parallele:

```text
estratto_conto
estratti_conto
bank_statements
movimenti_f24_banca
```

## 5.7 Fornitori

Canonica:

```text
fornitori
```

Il `POST /api/suppliers` pubblico non deve scrivere in `suppliers`.

## 5.8 Documenti classificati

Scegliere una sola collection tra:

```text
documents_classified
documenti_classificati
```

Aggiornare classificatore, archivio e Chat.

## 5.9 Magazzino

Per il GestionaleCloud non usare la giacenza fisica.

Mantenere soltanto i dati necessari al Dizionario Articoli e allo storico acquisti.  
Non fare nuove scritture in:

```text
warehouse_stocks
warehouse_products
magazzino
magazzino_articoli
magazzino_movimenti
movimenti_magazzino
```

Le collection condivise da altra app non devono essere cancellate.

---

# 6. FASE P1 — Unificazione dei motori contabili paralleli

## 6.1 Registrazione fatture in partita doppia

Sistemi concorrenti:

```text
contabilita_avanzata /ricategorizza-fatture
piano_conti /registra-tutte-fatture
piano_conti /registra-corrispettivi
```

Definire un unico motore di registrazione.

Requisiti:

- idempotenza;
- fonte documento;
- numero registrazione;
- data competenza;
- DARE/AVERE;
- conto;
- centro di costo;
- audit log;
- possibilità di ricostruzione.

## 6.2 Bilancio

Implementazioni rilevate:

```text
accounting/bilancio.py
piano_conti /bilancio
contabilita_avanzata /bilancio-dettagliato
contabilita_italiana /bilancio/*
```

Definire:

- un’unica fonte contabile;
- un unico Piano dei Conti;
- endpoint canonici;
- viste derivate, non motori indipendenti.

## 6.3 Due Piani dei Conti incompatibili

Schemi:

```text
05.01.01
400100
```

Non devono convivere senza tabella di mapping.

Azione:

1. Scegliere schema canonico.
2. Creare mapping/versionamento.
3. Migrare scritture.
4. Impedire ai router CEE di scrivere header incompatibili in `prima_nota_cassa`.
5. Testare Bilancio, mastro, giornale e saldo.

## 6.4 Tre formule di saldo Prima Nota

Uniformare:

- filtri;
- esclusioni;
- segno;
- movimenti annullati;
- provvisori;
- intervallo date;
- saldo iniziale;
- saldo finale.

Tutti gli endpoint devono chiamare una stessa funzione/engine.

## 6.5 Cespiti

Sistemi:

```text
cespiti.py
contabilita_italiana /cespiti/*
```

Scegliere un modello canonico e migrare.

## 6.6 Estratto conto importer

Canonico dichiarato:

```text
bank/estratto_conto.py
```

Valutare `bank/bank_statement_import.py`:

- mantenerlo solo come adattatore;
- oppure rimuoverlo dopo ricablaggio del frontend.

## 6.7 PayPal

Unificare:

- mapping fornitore;
- stati;
- pipeline di riconciliazione;
- origine statement/API;
- idempotenza.

## 6.8 Prima Nota Cassa

Eliminare il sistema parallelo:

```text
cash.py
cash_movements
```

oppure trasformarlo in adapter verso:

```text
prima_nota_cassa
```

senza doppia scrittura.

## 6.9 Verbali

Tre router:

```text
verbali_noleggio
verbali_noleggio_api
verbali_riconciliazione
```

Separare chiaramente:

- ingest;
- CRUD;
- riconciliazione;

con uno schema comune.

---

# 7. FASE P1 — Endpoint da verificare

Sono presenti **390 endpoint senza riferimento noto**.

Non eliminarli in blocco.

Generare un file:

```text
memoria/ENDPOINT_CLASSIFICAZIONE_FINALE.md
```

Per ogni endpoint indicare:

| Campo | Valore |
|---|---|
| Metodo/path | |
| Router | |
| Collection | |
| Frontend | sì/no |
| Scheduler | sì/no |
| Chat | sì/no |
| App esterna | sì/no |
| Migrazione/manutenzione | sì/no |
| Test | |
| Decisione | tenere/deprecare/eliminare |
| Motivo | |

Priorità di verifica:

```text
/api/batch
/api/cedolini
/api/dati-provvisori
/api/exports
/api/paghe
/api/pos-accredito
/api/report-pdf
/api/realtime
/api/trattenute-verbali
```

Gli endpoint di migrazione one-shot devono:

- essere Admin-only;
- essere disabilitabili;
- essere documentati;
- non restare esposti indefinitamente.

---

# 8. FASE P1 — Viewer, popup e modali

## 8.1 Obiettivo

Ogni documento deve essere leggibile all’interno dello schermo attualmente usato.

Documenti:

- fattura elettronica HTML;
- fattura PDF;
- cedolino;
- F24;
- quietanza;
- estratto conto;
- documento fiscale;
- allegato email;
- verbale;
- ricevuta PagoPA;
- PDF generico.

## 8.2 Componente canonico

Creare o consolidare un unico componente:

```text
DocumentViewerModal
```

API suggerita:

```jsx
<DocumentViewerModal
  open
  title
  documentType
  sourceUrl
  downloadUrl
  mimeType
  onClose
/>
```

Funzioni obbligatorie:

- Chiudi;
- Scarica;
- Schermo intero;
- Zoom +;
- Zoom −;
- Adatta larghezza;
- Adatta pagina;
- pagina corrente/totale;
- scroll interno;
- supporto touch/pinch;
- blocco scroll body;
- focus trap;
- ESC;
- aria-label;
- ritorno focus al pulsante origine.

## 8.3 Fatture ASSO

Il layout ASSO usa larghezze fisse.

Regola:

- preservare il layout;
- usare scale-to-fit/viewport interno;
- pinch-to-zoom;
- nessun taglio laterale;
- fallback HTML responsivo;
- non deformare tabelle e riepilogo IVA.

## 8.4 Cedolini PDF

- viewer interno;
- pagina per pagina;
- zoom;
- nessuna apertura automatica in nuova scheda;
- download originale;
- protezione autorizzazioni;
- URL non pubblico permanente.

## 8.5 Viewport di test

```text
320×568
360×800
390×844
412×915
768×1024
1024×768
1366×768
1920×1080
```

Testare orientamento verticale e orizzontale.

## 8.6 Pagine da verificare

Cercare tutti gli utilizzi di:

```text
window.open
iframe
object
embed
Dialog
Modal
Drawer
Popup
viewer
visualizza
pdf
```

Produrre:

```text
memoria/AUDIT_VIEWER_DOCUMENTI.md
```

con pagina, pulsante, documento, componente, risultato mobile/desktop e correzione.

---

# 9. FASE P1 — F24, quietanze e cedolini

## 9.1 Regole vincolanti

- F24 del consulente = fonte ufficiale del versamento.
- Cedolino/LUL = fonte del costo retributivo.
- Il saldo F24 non è automaticamente costo deducibile.
- RC01 = regolarizzazione/ravvedimento.
- DM10 = versamento ordinario dipendenti.
- CXX = Gestione separata.
- Quietanza = prova dell’effettivo pagamento.
- Quietanza senza F24 non autorizza la ricostruzione automatica.

## 9.2 Campi F24 obbligatori

```text
contribuente
periodo_competenza
data_scadenza_naturale
data_pagamento
giorni_ritardo
stato_pagamento
tipo_versamento
causale_inps
codici_tributo
debiti
crediti
saldo
pdf_hash
protocollo
quietanza_id
f24_originario_id
```

## 9.3 Quietanza senza F24

Mostrare alert:

```text
F24 mancante — prego caricare il modello F24 corrispondente.
```

Stato:

```text
QUIETANZA_PRESENTE_F24_MANCANTE
```

Non ricostruire codici o righe per supposizione.

## 9.4 DM10 e RC01

Se stesso contribuente, periodo e debito:

- non sommare automaticamente;
- collegare nello stesso fascicolo;
- distinguere capitale, sanzione, interesse, credito;
- se entrambe le quietanze risultano pagate, mostrare:

```text
POSSIBILE DOPPIO PAGAMENTO
```

## 9.5 Associazione F24 ↔ cedolini

Richiede:

- stesso soggetto;
- stesso periodo;
- posizione/matricola coerente;
- causale coerente;
- tipo lavoratori coerente.

La data del pagamento può essere nel mese successivo.

---

# 10. FASE P1 — IVA

Il modulo IVA è il più maturo: non riscriverlo.

Conservare:

- data operazione;
- data ricezione SDI;
- data registrazione;
- regola entro il 15;
- eccezione dicembre/gennaio;
- controllo 12 giorni separato;
- periodo IVA attribuito;
- `iva_utilizzata`;
- liquidazioni versionate;
- anti-doppia-detrazione;
- riepilogo annuale;
- movimenti IVA;
- Chat tracciabile.

Aggiungere solo test mancanti per:

- note credito;
- più aliquote;
- IVA parzialmente indetraibile;
- fattura annullata;
- rettifica dopo liquidazione confermata;
- recupero annuale;
- concorrenza di due richieste di conferma.

---

# 11. FASE P1 — Prestazioni e affidabilità

## 11.1 N+1

Correggere:

- sincronizzazione relazionale;
- estratto conto;
- downloader documenti;
- scheduler.

Usare:

```text
$in
aggregation
lookup in memoria
bulk_write
```

## 11.2 Paginazione reale

La paginazione deve avvenire in MongoDB, non dopo aver caricato 3000+3000 record.

## 11.3 Query illimitate

Rimuovere:

```text
to_list(None)
to_list(100000)
```

Usare:

- aggregation;
- count;
- cursor;
- paginazione.

## 11.4 Stato job persistente

Tutti i job lunghi devono avere collection stato:

```text
job_id
tipo
stato
progresso
totale
errori
created_at
updated_at
started_by
```

## 11.5 Cache

Applicare cache con invalidazione a:

- Dashboard;
- Bilancio;
- statistiche Prima Nota;
- controllo mensile;
- riepiloghi IVA;
- riepiloghi F24.

---

# 12. FASE P2 — Sicurezza residua

Verificare e mantenere:

- `SECRET_KEY` obbligatoria;
- CORS esplicito;
- rate limit;
- ruoli reali;
- bridge fail-closed;
- regex escaped;
- upload guard;
- sessione limitata;
- audit log.

Completare:

1. allowlist esplicita degli endpoint pubblici;
2. fail-fast produzione;
3. token solo in header;
4. autorizzazione backend della Gestione Riservata;
5. accesso PDF/cedolini/F24 con permesso;
6. nessun segreto nei log;
7. protezione dei download con URL temporanei o endpoint autenticati.

---

# 13. FASE P2 — Pulizia frontend e backend

## 13.1 Frontend

- eliminare componenti realmente non importati;
- rimuovere vecchie UI parallele;
- mantenere una configurazione navigazione;
- eliminare redirect HACCP;
- sostituire browser primitive residue:
  - `alert`;
  - `confirm`;
  - `prompt`;
  - `window.open`;
  con componenti canonici quando appropriato.

## 13.2 Backend

Rimuovere soltanto dopo verifica:

- stub;
- endpoint deprecati v1;
- migrazioni one-shot concluse;
- filesystem legacy;
- router non montati;
- funzioni senza chiamanti.

---

# 14. Matrice di verifica obbligatoria

Rigenerare una matrice effettiva:

```text
Route React
→ Pagina/Componente
→ Tab
→ Pulsante
→ Metodo/path API
→ Router
→ Service/Engine
→ Collection
→ Test
→ Stato
```

File finale:

```text
memoria/MATRICE_FUNZIONALE_FINALE.md
```

Per i principali moduli:

- Dashboard;
- Fatture;
- Corrispettivi;
- Fornitori;
- Prima Nota;
- Contabilità;
- IVA;
- F24;
- Quietanze;
- Riconciliazione;
- Documenti;
- Dipendenti contabili;
- Chat.

---

# 15. Test obbligatori

## 15.1 Backend

```bash
python -m pytest tests backend/tests
```

Non accettare regressioni rispetto ai 257 test verdi della baseline.

## 15.2 Frontend

```bash
cd frontend
yarn build
yarn lint
```

## 15.3 Runtime route table

Verificare che l’app booti e rigenerare:

```bash
python scripts/genera_mappa.py
```

## 15.4 End-to-end

Testare:

1. Fattura XML → `invoices`.
2. Metodo fornitore → Cassa/Banca.
3. Fattura banca → estratto conto → riconciliazione.
4. Corrispettivo manuale → XML ufficiale.
5. POS serale → accredito banca.
6. Cedolino → dipendente → Prima Nota Salari → TFR.
7. F24 → quietanza.
8. F24 senza quietanza.
9. Quietanza senza F24.
10. DM10 + RC01.
11. Due quietanze → possibile doppio pagamento.
12. IVA entro il 15.
13. IVA oltre il 15.
14. IVA dicembre/gennaio.
15. Apertura fattura mobile.
16. Apertura cedolino mobile.
17. Apertura F24/quietanza mobile.
18. Operazione distruttiva con ruolo non Admin.
19. Restart durante job.
20. Import duplicato.

---

# 16. Deliverable da consegnare

Creare/aggiornare:

```text
memoria/AUDIT_ESECUZIONE_DEFINITIVO.md
memoria/MATRICE_FUNZIONALE_FINALE.md
memoria/ENDPOINT_CLASSIFICAZIONE_FINALE.md
memoria/AUDIT_VIEWER_DOCUMENTI.md
memoria/PIANO_MIGRAZIONE_COLLECTION.md
memoria/BUG_CORRETTI_2026-07.md
```

`AUDIT_ESECUZIONE_DEFINITIVO.md` deve contenere:

- baseline;
- commit finali;
- file modificati;
- bug corretti;
- collection migrate;
- endpoint eliminati;
- endpoint mantenuti e motivo;
- test eseguiti;
- build;
- route prima/dopo;
- rischi residui;
- eventuali decisioni richieste.

---

# 17. Criteri di accettazione

Il lavoro è concluso soltanto quando:

1. Tutti i 12 bug di correttezza sono chiusi o motivatamente rinviati.
2. `f24_unificato`, `invoices`, `dipendenti`, `cedolini`, `fornitori` ed `estratto_conto_movimenti` sono le fonti canoniche effettive.
3. Nessun flusso vivo scrive in collection legacy.
4. I 390 endpoint sono classificati.
5. Nessun endpoint viene eliminato senza controllo dei chiamanti non frontend.
6. Non esistono più motori contabili concorrenti senza una decisione canonica.
7. Tutte le formule di saldo Prima Nota usano lo stesso engine.
8. Il viewer documentale funziona su tutti i viewport indicati.
9. Fatture, cedolini, F24 e quietanze sono visibili integralmente nello schermo.
10. IVA non può essere detratta due volte.
11. DM10/RC01 non possono essere sommati due volte.
12. Quietanza senza F24 genera alert.
13. Ogni operazione distruttiva è Admin-only e tracciata.
14. I job sopravvivono a restart/multi-worker.
15. Build frontend verde.
16. Backend avviabile.
17. Test almeno pari alla baseline di 257 test verdi.
18. Mappe rigenerate e coerenti.
19. Tutto è committato su `main`.

---

# 18. Ordine operativo consigliato

```text
1. Congela baseline e rigenera mappe
2. Correggi i 12 bug di correttezza
3. Consolida F24/quietanze
4. Consolida dipendenti/cedolini
5. Consolida fatture/estratto conto/fornitori
6. Unifica Piano dei Conti, Bilancio e saldi Prima Nota
7. Classifica i 390 endpoint
8. Correggi viewer e popup
9. Ottimizza query e job
10. Completa sicurezza residua
11. Elimina codice realmente morto
12. Esegui E2E, build, test e mappe
13. Aggiorna documentazione
14. Commit finale su main
```

## Regola finale

Non limitarti a produrre un altro audit.  
Esegui le correzioni, dimostra il risultato con test e mappe rigenerate e lascia nel repository una sola architettura contabile canonica, senza duplicazioni silenziose e senza rompere i sistemi vivi.

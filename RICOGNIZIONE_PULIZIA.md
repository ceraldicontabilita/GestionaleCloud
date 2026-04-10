# 🔍 RICOGNIZIONE COMPLETA — Ceraldi ERP
## Analisi dello stato attuale, duplicati, file inutili, collection ridondanti
## Prodotto da: lettura diretta del codice sorgente — aprile 2026

---

## NUMERI REALI DEL PROGETTO

- **File Python backend:** 467
- **File JSX frontend:** 170
- **Dimensione repo:** 20.5 MB
- **Router registrati in main.py:** ~75 (di cui ~8 commentati)
- **Collection MongoDB usate:** ~120+ (di cui molte duplicate o deprecate)
- **File email service:** 9 (troppi — fanno cose sovrapposte)
- **Parser F24:** 5 versioni diverse (una sola serve)
- **Service fatture:** 2 versioni (v1 e v2)
- **Service fornitori:** 2 versioni (v1 e v2)

---

## PARTE 1 — FILE DA ELIMINARE (codice morto o sostituito)

### 🔴 ELIMINARE — Router commentati in main.py (file esistono ma non servono)
Questi file esistono nel repo ma sono commentati nel main e non usati da nessuno:
```
app/routers/f24/f24_gestione_avanzata.py       → commentato, sostituito da f24_main
app/routers/f24/f24_tributi.py                 → commentato, logica in f24_main
app/routers/accounting/accounting_f24.py        → commentato
app/routers/manutenzione.py                    → commentato (/api/manutenzione)
```

### 🔴 ELIMINARE — Parser F24 duplicati (ne servono 2 al massimo, ce ne sono 5)

| File | Dimensione | Cosa fa | Decisione |
|---|---|---|---|
| `app/parsers/f24_parser.py` | 14 KB | Parser base PDF F24 | ✅ **TENERE** — è il parser principale |
| `app/routers/f24_parser.py` | 33 KB | Parser PDF F24 con router | ✅ **TENERE** — usato nel main |
| `app/services/f24_parser.py` | 15 KB | Parser quietanze F24 | ✅ **TENERE** — per quietanze specifiche |
| `app/services/parser_f24.py` | 70 KB | Parser F24 Commercialista | ⚠️ **VALUTARE** — il più completo, capire se copre anche gli altri |
| `app/services/parser_f24_gemini.py` | 8 KB | Parser F24 con Gemini AI | 🔴 **ELIMINARE** — usa Gemini (non usato), duplica parser_f24 |

### 🔴 ELIMINARE — Service con versione v1 e v2 (tenere solo la v2)
```
app/services/invoice_service.py        → 22 KB  → 🔴 ELIMINARE (v2 esiste)
app/services/supplier_service.py       → 12 KB  → 🔴 ELIMINARE (v2 esiste)
```
Prima di eliminare: verificare che v2 importi tutto ciò che serviva a v1.

### 🔴 ELIMINARE — Email service duplicati (9 file che fanno cose sovrapposte)

| File | Dimensione | Funzione reale | Decisione |
|---|---|---|---|
| `email_service.py` | 13 KB | SMTP invio email | ✅ TENERE — diverso dagli altri |
| `email_monitor_service.py` | 29 KB | Loop 50min + routing | ✅ TENERE — orchestratore principale |
| `email_document_downloader.py` | 39 KB | Download allegati IMAP | ✅ TENERE — motore download |
| `email_classifier_service.py` | 29 KB | Classificazione regole | ✅ TENERE — regole EmailRule |
| `email_full_download.py` | 55 KB | Download completo tutto | 🔴 **ELIMINARE** — sostituito da monitor+downloader |
| `email_downloader.py` | 11 KB | Download old-style | 🔴 **ELIMINARE** — sostituito da document_downloader |
| `email_to_mongodb.py` | 13 KB | Salva email su MongoDB | 🔴 **ELIMINARE** — logica già in document_downloader |
| `email_scanner_completo.py` | 16 KB | Scansiona cartelle | ⚠️ VALUTARE — potrebbe servire per cartelle speciali |
| `email_reconciliation.py` | 25 KB | Riconcilia email-documenti | ✅ TENERE — logica di matching specifica |

### 🔴 ELIMINARE — File utils con funzioni duplicate
```
app/utils/invoice_xml_parser.py    → duplica app/parsers/fattura_elettronica_parser.py
app/utils/busta_paga_parser.py     → duplica app/parsers/payslip_parser_simple.py
app/utils/normalize_fields.py      → duplica app/utils/field_normalizer.py
```

### 🔴 ELIMINARE — Router legacy inutili
```
app/routers/auto_repair.py          → "riparazione automatica dati" — funzione generica mai chiamata dal frontend
app/routers/enhanced_parser.py      → enhanced parser generico, non usato direttamente
app/routers/import_manuale.py       → sostituito da fatture_module/import_xml.py
app/routers/comparatore.py          → pagina comparatore fornitori, non presente nel frontend attivo
app/routers/previsioni_acquisti.py  → pagina non presente nel frontend attivo
app/routers/cash_register.py        → duplica cash.py con diversa implementazione
```

### 🔴 ELIMINARE — File commentati nei router (residui di sviluppo)
```
app/routers/tracciabilita/migrazione_db.py  → script one-shot già eseguito
app/routers/tracciabilita/normalizzazione.py → script one-shot già eseguito
app/scripts/unifica_fornitori_suppliers.py   → script one-shot già eseguito
```

---

## PARTE 2 — COLLECTION MONGODB DA NORMALIZZARE

Questo è il problema più serio. Ci sono ~120 collection definite, molte duplicate.

### 🔴 COLLECTION DUPLICATE — Stessa entità, due nomi

| Entità | Collection canonica | Collection da eliminare/migrare |
|---|---|---|
| **Fatture** | `invoices` (3856 doc) | `indice_documenti` (3815 doc) — stessi dati con nome diverso |
| **Fatture** | `invoices` | `fatture_passive` — nome usato nel codice ma punta a invoices |
| **Dipendenti** | `dipendenti` (regola assoluta) | `employees` — due nomi per la stessa collection |
| **Cedolini** | `cedolini` (916 doc) | `payslips` (480 doc) — alias legacy con dati parziali |
| **Estratto conto** | `estratto_conto_movimenti` (4261 doc) | `estratto_conto` (4244 doc) — quasi identici, legacy backup |
| **Magazzino** | `warehouse_inventory` (5372 doc) | `warehouse_stocks` (1484 doc) — deprecata, dati errati |
| **F24** | `f24_unificato` (83 doc) | `f24_models` (68 doc) — legacy da migrare |
| **Fornitori** | `fornitori` (268 doc) | `suppliers` (315 doc) — due nomi, dati parzialmente diversi |
| **Piano conti** | `piano_conti` (259 doc) | `chart_of_accounts` — alias inglese non necessario |
| **Movimenti magazzino** | `warehouse_movements` (3935 doc) | `magazzino_movimenti`, `movimenti_magazzino` — alias |
| **Presenze** | `presenze` | `presenze_mensili`, `libro_unico_presenze`, `attendance_presenze_calendario` — 4 collection per la stessa cosa |

### ⚠️ COLLECTION CHE ANDREBBERO UNIFICATE

**Categoria "riepilogo cedolini"** — troppa frammentazione:
- `cedolini` — i PDF processati
- `payslips` — alias legacy
- `riepilogo_cedolini` — riepilogo derivato
- `cedolini_email_attachments` — i PDF prima del processing
→ Tenere solo `cedolini` e `cedolini_raw` (prima del processing)

**Categoria "documenti ricevuti da email"** — troppa frammentazione:
- `documents_inbox` (803 doc)
- `documents_classified` 
- `documenti_classificati` (1967 doc)
- `documenti_non_associati` (285 doc)
- `email_documents`
- `documenti_email` (218 doc)
→ Tenere solo `documents_inbox` con campo `stato` per distinguere i casi

**Categoria "movimenti contabili magazzino"**:
- `acquisti_prodotti` (15065 doc)
- `dettaglio_righe_fatture` (11076 doc)
→ Sono la stessa cosa. `dettaglio_righe_fatture` è il nome corretto.

### ✅ COLLECTION DA TENERE COSÌ COME SONO (canoniche, usate, pulite)

```
invoices                    → fatture passive (4000 doc circa)
dipendenti                  → anagrafica dipendenti (regola assoluta)
cedolini                    → buste paga processate
f24_unificato               → tutti gli F24
estratto_conto_movimenti    → movimenti bancari
prima_nota_cassa            → prima nota cassa
prima_nota_banca            → prima nota banca
prima_nota_salari           → stipendi
corrispettivi               → corrispettivi giornalieri
warehouse_inventory         → giacenze magazzino
warehouse_movements         → movimenti magazzino
dettaglio_righe_fatture     → righe delle fatture
scadenziario_fornitori      → scadenze pagamento fornitori
fornitori                   → anagrafica fornitori (italiana, quella primaria)
ricette                     → ricette produzione
lotti                       → lotti HACCP
produzioni                  → produzioni giornaliere
```

---

## PARTE 3 — INCONSISTENZE NEL CODICE DA CORREGGERE

### ❌ PROBLEMA 1 — `fatture_module/common.py` usa `indice_documenti` invece di `invoices`
```python
# SBAGLIATO (attuale):
COL_FATTURE_RICEVUTE = "indice_documenti"

# CORRETTO:
COL_FATTURE_RICEVUTE = "invoices"
```
Questo è il bug principale: lo stesso router che importa le fatture le salva in `indice_documenti` mentre tutto il resto del sistema le cerca in `invoices`. Risultato: 3815 documenti in `indice_documenti` che quasi nessun altro modulo sa di cercare lì.

### ❌ PROBLEMA 2 — `dipendenti` vs `employees` usati in modo random
Alcuni router usano `db["dipendenti"]`, altri usano `db[Collections.EMPLOYEES]` che punta a `"employees"`. Sono due collection diverse in MongoDB con dati parzialmente sovrapposti. La regola è `dipendenti` ma il codice usa entrambe.

### ❌ PROBLEMA 3 — `suppliers` vs `fornitori` — stesso problema
`app/routers/fatture_module/common.py` usa `COL_FORNITORI = "fornitori"` (corretto).
Ma `app/database/collections.py` definisce `FORNITORI = "fornitori"` e anche `SUPPLIERS_MODULE` che punta a `"suppliers"`. Due collection con 268 e 315 documenti rispettivamente — alcune fatture vedono un fornitore, altre vedono l'altro.

### ❌ PROBLEMA 4 — Learning Machine ha 3 entry point
- `app/routers/learning_machine.py` → `/api/learning-machine`
- `app/routers/learning_machine_cdc.py` → `/api/learning-machine` (stesso prefisso!)
- `app/routers/learning_universal.py` → `/api/learning-universal`
Tre router per la stessa funzione, con prefissi sovrapposti, che scrivono in collection diverse.

---

## PARTE 4 — PIANO DI PULIZIA IN ORDINE DI PRIORITÀ

### FASE A — Zero rischio (eliminare file sicuramente inutili)
Questi file possono essere eliminati senza rischio perché o commentati nel main o sostituiti da versioni più recenti:

1. `app/services/parser_f24_gemini.py` — usa Gemini, non integrato
2. `app/services/email_full_download.py` — sostituito da monitor+downloader
3. `app/services/email_downloader.py` — sostituito da document_downloader
4. `app/services/email_to_mongodb.py` — logica inclusa nel downloader
5. `app/utils/invoice_xml_parser.py` — duplica il parser principale
6. `app/utils/busta_paga_parser.py` — duplica payslip_parser_simple
7. `app/utils/normalize_fields.py` — duplica field_normalizer
8. `app/routers/tracciabilita/migrazione_db.py` — script one-shot eseguito
9. `app/routers/tracciabilita/normalizzazione.py` — script one-shot eseguito
10. `app/scripts/unifica_fornitori_suppliers.py` — script one-shot eseguito

### FASE B — Basso rischio (unificare collection con alias)
Aggiornare `fatture_module/common.py` per usare `invoices` invece di `indice_documenti`.
Aggiornare tutti i riferimenti a `employees` per usare `dipendenti`.
Aggiornare tutti i riferimenti a `suppliers` per usare `fornitori`.

### FASE C — Medio rischio (unificare router duplicati)
Unificare le 3 Learning Machine in un unico router.
Unificare i 9 email service nei 5 necessari.
Eliminare service v1 dopo verifica che v2 li copre.

### FASE D — Costruzione Event Bus
Solo dopo le fasi A, B, C, si costruisce `app/core/event_bus.py`.
Il codice sarà pulito, le collection saranno uniche, i router saranno chiari.
L'Event Bus si aggancia su fondamenta solide.

---

## STATO ATTUALE — Cosa funziona e cosa è solo codice dormiente

### ✅ Funziona e va tenuto così
- Import fatture XML (flusso completo funziona)
- Parser cedolini (tutti i formati)
- Prima nota (manuale)
- Email scanner con mittenti whitelist
- Agenti AI (FiscaleSentinella, HRGuardiano, LearningCervello)
- Tracciabilità HACCP (su ceraldiapp.it, via ponte ERP)
- Riconciliazione bancaria (BNL, Nexi)
- F24 import e riconciliazione

### ⚠️ Esiste ma non collegato automaticamente
- Aggiornamento magazzino da fattura (c'è il codice, non sempre si attiva)
- TFR da cedolino (c'è il router, non si chiama automaticamente)
- Prima nota automatica al pagamento (aspetta conferma manuale)
- Aggiornamento prezzi ricette da fattura (c'è in tracciabilità ma non connesso al gestionale)

### 🔴 Codice che non va da nessuna parte
- 3 Learning Machine con prefissi sovrapposti
- 9 email service con logica sovrapposta
- ~20 collection legacy con dati duplicati
- ~8 router commentati nel main


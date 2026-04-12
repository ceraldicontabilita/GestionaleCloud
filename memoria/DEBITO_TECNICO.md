# Debito Tecnico — Ceraldi ERP
> Analisi completa dei file da eliminare, collection duplicate, inconsistenze nel codice
> Prodotto da: lettura diretta del codice sorgente | Aggiornato: Aprile 2026

---

## NUMERI DEL PROGETTO

- File Python backend: 467
- File JSX frontend: 170
- Router registrati in main.py: ~75 (di cui ~8 commentati)
- Collection MongoDB in uso: ~120+ (molte duplicate o deprecate)
- File email service: 9 (troppi — logiche sovrapposte)
- Parser F24: 5 versioni (al massimo ne servono 2-3)
- Service fatture: v1 e v2 (solo v2 serve)
- Service fornitori: v1 e v2 (solo v2 serve)

---

## PARTE 1 — FILE DA ELIMINARE

### Router commentati in main.py (codice morto)
Questi file esistono nel repo ma sono commentati in `main.py` e non usati:
```
app/routers/f24/f24_gestione_avanzata.py   → commentato, sostituito da f24_main
app/routers/f24/f24_tributi.py             → commentato, logica in f24_main
app/routers/accounting/accounting_f24.py   → commentato
app/routers/manutenzione.py                → commentato (/api/manutenzione)
```

### Parser F24 da eliminare
| File | Dimensione | Decisione |
|---|---|---|
| `app/parsers/f24_parser.py` | 14 KB | ✅ TENERE — parser principale |
| `app/routers/f24_parser.py` | 33 KB | ✅ TENERE — usato nel main |
| `app/services/f24_parser.py` | 15 KB | ✅ TENERE — per quietanze |
| `app/services/parser_f24.py` | 70 KB | ⚠️ VALUTARE — più completo, capire se copre altri |
| `app/services/parser_f24_gemini.py` | 8 KB | 🔴 ELIMINARE — usa Gemini (non integrato) |

### Service v1 da eliminare (v2 esiste)
```
app/services/invoice_service.py   → 22 KB  → 🔴 ELIMINARE (v2 esiste)
app/services/supplier_service.py  → 12 KB  → 🔴 ELIMINARE (v2 esiste)
```
Prima di eliminare: verificare che v2 copra tutto ciò che serviva a v1.

### Email service da eliminare (9 file, logica sovrapposta)
| File | Decisione |
|---|---|
| `app/email_service.py` | ✅ TENERE — SMTP invio email |
| `app/services/email_monitor_service.py` | ✅ TENERE — orchestratore principale |
| `app/services/email_document_downloader.py` | ✅ TENERE — motore download IMAP |
| `app/services/email_classifier_service.py` | ✅ TENERE — regole classificazione |
| `app/services/email_reconciliation.py` | ✅ TENERE — matching email↔documenti |
| `app/services/email_full_download.py` | 🔴 ELIMINARE — sostituito da monitor+downloader |
| `app/services/email_downloader.py` | 🔴 ELIMINARE — sostituito da document_downloader |
| `app/services/email_to_mongodb.py` | 🔴 ELIMINARE — logica già in document_downloader |
| `app/services/email_scanner_completo.py` | ⚠️ VALUTARE — potrebbe servire per cartelle speciali |

### Utils duplicati
```
app/utils/invoice_xml_parser.py   → 🔴 ELIMINARE (duplica fattura_elettronica_parser.py)
app/utils/busta_paga_parser.py    → 🔴 ELIMINARE (duplica payslip_parser_simple.py)
app/utils/normalize_fields.py     → 🔴 ELIMINARE (duplica field_normalizer.py)
```

### Router legacy inutili
```
app/routers/auto_repair.py         → mai chiamato dal frontend
app/routers/enhanced_parser.py     → non usato direttamente
app/routers/import_manuale.py      → sostituito da fatture_module/import_xml.py
app/routers/comparatore.py         → pagina non presente nel frontend
app/routers/previsioni_acquisti.py → route rimossa dal frontend
app/routers/cash_register.py       → duplica cash.py con diversa implementazione
```

### Script one-shot già eseguiti
```
app/routers/tracciabilita/migrazione_db.py    → script eseguito, da eliminare
app/routers/tracciabilita/normalizzazione.py  → script eseguito, da eliminare
app/scripts/unifica_fornitori_suppliers.py    → script eseguito, da eliminare
```

---

## PARTE 2 — COLLECTION MONGODB DUPLICATE

### Fatture (duplicato critico)

| Collection | Documenti | Situazione |
|---|---|---|
| `invoices` | 224 | CANONICA |
| `indice_documenti` | ~3.815 | OBSOLETA — stessi dati con nome diverso |
| `fatture_passive` | ~3.856 | ALIAS — alcune query usano questo nome |

**Bug principale**: `fatture_module/common.py` usa `COL_FATTURE_RICEVUTE = "indice_documenti"` invece di `"invoices"`. Risultato: 3.815 documenti in `indice_documenti` che altri moduli non trovano.

**Fix**: aggiornare `COL_FATTURE_RICEVUTE = "invoices"` in `common.py`.

### Dipendenti (da unificare)
| Collection | Record | Uso |
|---|---|---|
| `dipendenti` | 34 | CANONICA — usare sempre questa |
| `employees` | 31 | COPIA — solo per presenze batch |

**Fix**: tutti i router che leggono `db["employees"]` devono usare `db["dipendenti"]`.

### Fornitori (ambiguo)
| Collection | Record | Uso |
|---|---|---|
| `suppliers` | 328 | Usata dal modulo principale (`Collections.SUPPLIERS`) |
| `fornitori` | 168 | Usata da altri router (es. `fatture_module/common.py`) |

**Problema**: alcune fatture vedono un fornitore, altre vedono l'altro. Dati parzialmente diversi.
**Fix proposto**: unificare in `suppliers` con migrazione di tutti i dati unici da `fornitori`.

### Cedolini (frammentati)
| Collection | Record | Uso |
|---|---|---|
| `cedolini` | 1.658 | CANONICA |
| `cedolini_importati` | 2.363 | Sistema Zucchetti cloud |
| `payslips` | 480 | ALIAS LEGACY — dati parziali |
| `cedolini_email_attachments` | — | PDF grezzi pre-processing |

**Fix**: mantenere `cedolini` e `cedolini_importati`, eliminare `payslips` dopo migrazione.

### Estratto Conto (quasi identici)
| Collection | Record | Situazione |
|---|---|---|
| `estratto_conto_movimenti` | 4.468 | CANONICA |
| `estratto_conto` | ~4.244 | LEGACY BACKUP — quasi identico |

**Fix**: eliminare `estratto_conto` dopo backup.

### Magazzino (sovrapposti)
| Collection | Record | Situazione |
|---|---|---|
| `warehouse_stocks` | 496 | CANONICA — giacenze correnti (NON warehouse_inventory) |
| `warehouse_stocks` | 1.484 | DEPRECATA — dati obsoleti |
| `warehouse_movements` | ~3.935 | CANONICA — movimenti |
| `magazzino_movimenti` | — | ALIAS |
| `movimenti_magazzino` | — | ALIAS |

### Presenze (troppo frammentate)
| Collection | Uso |
|---|---|
| `presenze` (290) | CANONICA |
| `presenze_mensili` (1.629) | RIEPILOGO |
| `attendance_presenze_calendario` | CALENDARIO UI |
| `libro_unico_presenze` | IMPORT |

### F24 (legacy)
| Collection | Record | Situazione |
|---|---|---|
| `f24_unificato` | 68 | CANONICA |
| `f24_models` | 68 | LEGACY — migrare in `f24_unificato` |

### Documenti ricevuti (troppo frammentati)
| Collection | Record | Situazione |
|---|---|---|
| `documents_inbox` | 91 | CANONICA |
| `documenti_classificati` | 1.967 | DA CONSOLIDARE |
| `documenti_non_associati` | 285 | DA CONSOLIDARE |
| `email_documents` | — | DA CONSOLIDARE |

**Fix proposto**: mantenere `documents_inbox` con campo `stato` per distinguere i casi.

---

## PARTE 3 — INCONSISTENZE NEL CODICE

### Problema 1 — `fatture_module/common.py` usa `indice_documenti`
```python
# SBAGLIATO (attuale):
COL_FATTURE_RICEVUTE = "indice_documenti"

# CORRETTO:
COL_FATTURE_RICEVUTE = "invoices"
```
Questo è il bug principale del sistema fatture.

### Problema 2 — `dipendenti` vs `employees` random
Alcuni router: `db["dipendenti"]`. Altri: `db[Collections.EMPLOYEES]` → `"employees"`.
Due collection diverse, dati parzialmente sovrapposti.

### Problema 3 — `suppliers` vs `fornitori` random
`fatture_module/common.py` usa `COL_FORNITORI = "fornitori"` (corretto per quel modulo).
`database/collections.py` definisce `FORNITORI = "fornitori"` E `SUPPLIERS_MODULE` → `"suppliers"`.
Risultato: alcune fatture vedono un fornitore, altre vedono l'altro.

### Problema 4 — Learning Machine ha 3 entry point sovrapposti
- `app/routers/learning_machine.py` → `/api/learning-machine`
- `app/routers/learning_machine_cdc.py` → `/api/learning-machine` **(stesso prefisso!)**
- `app/routers/learning_universal.py` → `/api/learning-universal`

Tre router per la stessa funzione, che scrivono in collection diverse.

---

## PARTE 4 — PIANO DI PULIZIA (in ordine di rischio)

### Fase A — Zero rischio (eliminare senza rischi)
1. `app/services/parser_f24_gemini.py` — usa Gemini, non integrato
2. `app/services/email_full_download.py` — sostituito da monitor+downloader
3. `app/services/email_downloader.py` — sostituito da document_downloader
4. `app/services/email_to_mongodb.py` — logica già nel downloader
5. `app/utils/invoice_xml_parser.py` — duplica il parser principale
6. `app/utils/busta_paga_parser.py` — duplica payslip_parser_simple
7. `app/utils/normalize_fields.py` — duplica field_normalizer
8. `app/routers/tracciabilita/migrazione_db.py` — script one-shot eseguito
9. `app/routers/tracciabilita/normalizzazione.py` — script one-shot eseguito
10. `app/scripts/unifica_fornitori_suppliers.py` — script one-shot eseguito

### Fase B — Basso rischio (aggiornare collection)
- Aggiornare `fatture_module/common.py`: `invoices` invece di `indice_documenti`
- Aggiornare tutti i riferimenti `employees` → `dipendenti`
- Decidere e documentare la collection canonica per fornitori

### Fase C — Medio rischio (unificare logica)
- Unificare le 3 Learning Machine in un unico router
- Unificare i 9 email service nei 5 necessari
- Eliminare service v1 dopo verifica v2

### Fase D — Alto rischio (Event Bus)
- Solo dopo A, B, C: costruire l'Event Bus completo
- Agganciare tutti gli handler
- Testare ogni flusso end-to-end

---

## STATO ATTUALE — Cosa funziona vs codice dormiente

### Funziona e va mantenuto
- Import fatture XML (flusso completo)
- Parser cedolini (tutti i formati)
- Prima nota manuale
- Email scanner con whitelist mittenti
- Agenti AI: FiscaleSentinella, HRGuardiano, LearningCervello
- Riconciliazione bancaria (BNL, Nexi)
- F24 import e riconciliazione
- Scheduler PEC ogni ora + Gmail ogni 50 minuti

### Esiste ma non collegato automaticamente
- Aggiornamento magazzino da fattura (codice presente, non sempre si attiva)
- TFR da cedolino (router presente, non si chiama auto)
- Prima nota automatica al pagamento (aspetta conferma manuale)
- Aggiornamento prezzi ricette da fattura (in tracciabilità, non connesso)

### Codice che non va da nessuna parte
- 3 Learning Machine con prefissi sovrapposti
- 9 email service con logica sovrapposta
- ~20 collection legacy con dati duplicati
- ~8 router commentati nel main

---

*Aggiornato: Aprile 2026*

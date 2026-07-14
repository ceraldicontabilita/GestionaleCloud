# AUDIT TECNICO DEFINITIVO — Sessione 2026-07-14

Documento architetturale: router toccati, endpoint esatti, collection
lette/scritte/create/rimosse, funzioni chiave, event bus, alert catalog,
frontend, test. Copre in dettaglio verificato (diff riletti riga per riga)
i due interventi principali di questa sessione — **Modulo A: Dipendenti**
e **Modulo B: Fatture Estere** — più un richiamo sintetico del resto della
sessione (§7) per contesto.

Stack di riferimento: FastAPI + Motor (MongoDB async), montaggio router via
`app/router_registry.py::register_all_routers`, propagazione eventi via
`app/services/event_bus.py::propagate_event`, alert centralizzati via
`app/services/alert_engine.py`. Frontend React 18 + Vite, routing piatto
in `frontend/src/main.jsx`, menu in `frontend/src/navigation.config.js`.

---

## 1. Executive summary

| Modulo | Intervento | File backend toccati | Endpoint nuovi | Collection nuove | File eliminati | Test nuovi |
|---|---|---|---|---|---|---|
| A — Dipendenti | Rimozione contratti/libretti sanitari (HR esterno) | 5 modificati (3 router + 2 service) | 0 | 0 | 7 | 0 (rimosso 1 obsoleto) |
| B — Fatture Estere | Estrazione AI → fattura vera → matching → verifica + rating | 4 modificati (2 router + 2 service) + 1 router creato | 3 | 1 | 0 | 17 |

Commit di questa sessione (branch `claude/repo-restructure-review-z0gg7w`,
poi fast-forward su `main`), dal più vecchio al più recente:

```
9508f676  Dipendenti: rimuovi contratti di lavoro e libretti sanitari (HR è esterno)
5f100aa0  Fatture estere: estrazione AI + fattura vera, matching PayPal/bonifico gratis
275bbd84  Fatture estere: aggancio fornitore esplicito su P.IVA (anche formati UE)
4cbd06ec  Fatture estere: coda di verifica + rating affidabilità AI per fornitore
```

---

## 2. Modulo A — Dipendenti: rimozione contratti di lavoro e libretti sanitari

### 2.1 Contesto

Decisione utente: il gestionale HR completo (contratti di lavoro, libretti
sanitari, regolamento aziendale, presenze/turni disciplinari) è un
programma **esterno** a questo gestionale (AppDipendenti,
`https://appdipendenti.onrender.com`, stesso cluster MongoDB). In questo
repo restano solo i dati contabili/fiscali: anagrafica minima (per
collegare CF↔cedolino), **cedolini paga** e **TFR**.

Verificato preventivamente (Explore agent): "regolamento aziendale",
"lotti/tracciabilità a temperature" e "sanzioni/ammonizioni disciplinari"
NON esistevano nel codice — nessuna azione necessaria su quei tre punti.

### 2.2 Router modificati

| File | Prefix montato | Modifica |
|---|---|---|
| `app/routers/employees/dipendenti.py` | `/api/dipendenti` | Rimosse 4 sezioni di route (vedi 2.3), rimossi campi contratto/libretto da create/update/bulk-upsert |
| `app/routers/scadenze.py` | `/api/scadenze` | `GET /dashboard-widget`: rimossi conteggi `contratti_scadenza`/`libretti_scaduti`/`libretti_in_scadenza` e i relativi addendi in `totale_alert` |
| `app/routers/reports/report_pdf.py` | `/api/report-pdf` | `GET /dipendenti` e `GET /scadenze`: rimosse sezioni Contratti/Libretti dai PDF generati (restano Fatture/F24) |

### 2.3 Route rimosse da `dipendenti.py` (non più esistenti)

```
GET    /tipi-contratto
GET    /contratti                              (list_contratti_proxy)
GET    /libretti/scadenze
PUT    /{dipendente_id}/libretto
GET    /libretti-sanitari/all
POST   /libretti-sanitari
PUT    /libretti-sanitari/{libretto_id}
DELETE /libretti-sanitari/{libretto_id}
POST   /libretti-sanitari/import-excel
GET    /libretti-sanitari/scadenze
POST   /libretti-sanitari/genera-da-dipendenti
POST   /contratti
PUT    /contratti/{contratto_id}
POST   /contratti/{contratto_id}/termina
DELETE /contratti/{contratto_id}
GET    /contratti/scadenze
POST   /contratti/import-excel
```

Costante rimossa: `CONTRATTI_TIPI`.

### 2.4 Endpoint attuali di `dipendenti.py` (stato finale, verificato)

Prefix `/api/dipendenti`:

| Metodo | Path | Funzione | Note |
|---|---|---|---|
| GET | `` | `list_dipendenti` | |
| GET | `/by-google-email` | `get_dipendente_by_google_email` | |
| GET | `/stats` | `get_dipendenti_stats` | campo `libretti_in_scadenza` rimosso dalla risposta |
| GET | `/duplicati` | `lista_duplicati_dipendenti` | |
| POST | `/duplicati/merge` | `merge_duplicato_dipendente` | |
| POST | `/duplicati/auto-merge` | `auto_merge_duplicati` | |
| GET | `/report-ferie-permessi-tutti` | `genera_report_ferie_permessi_tutti` | |
| POST | `/sync-iban` | `sync_iban_field` | |
| GET | `/tipi-turno` | `get_tipi_turno` | |
| GET | `/mansioni` | `get_mansioni` | |
| POST | `/bulk-upsert` | `bulk_upsert_dipendenti` | whitelist campi ridotta (vedi 2.5) |
| POST | `/bulk-upsert/preview` | `bulk_upsert_preview` | idem, dry-run |
| POST | `` | `create_dipendente` | campi contratto/libretto rimossi dal payload salvato |
| GET | `/buste-paga` | `get_buste_paga` | |
| POST | `/buste-paga` | `create_busta_paga` | |
| GET | `/{dipendente_id}` | `get_dipendente` | |
| PUT | `/{dipendente_id}` | `update_dipendente` | event payload senza `tipo_contratto` |
| DELETE | `/{dipendente_id}` | `delete_dipendente` | |
| GET | `/turni/settimana` | `get_turni_settimana` | |
| POST | `/turni/salva` | `salva_turni` | |
| POST | `/{dipendente_id}/invita-portale` | `invita_portale` | |
| POST | `/invita-multipli` | `invita_multipli` | |
| GET | `/portale/stats` | `get_portale_stats` | |
| GET | `/buste-paga/scan` | `scan_buste_paga_folders` | |
| POST | `/buste-paga/import` | `import_buste_paga_to_dipendenti` | |
| GET | `/buste-paga/dipendente/{dipendente_id}` | `get_buste_paga_dipendente` | |
| POST | `/buste-paga/dipendente/{dipendente_id}/import` | `import_busta_paga_to_dipendente` | |
| GET | `/{dipendente_id}/report-ferie-permessi` | `genera_report_ferie_permessi` | |

28 route rimanenti (verificato `grep -c "^@router\." dipendenti.py`), 17
rimosse rispetto allo stato precedente (45 totali prima di questa sessione).

### 2.5 Campi rimossi dai payload dipendente

Da `create_dipendente`, `bulk_upsert_dipendenti`, whitelist `CAMPI_AGGIORNABILI`
(usata sia da `/bulk-upsert` che da `/bulk-upsert/preview`):

```
tipo_contratto, livello, data_fine_contratto,
libretto_numero, libretto_scadenza, libretto_file,
contratto_attivo_id
```

### 2.6 Event bus — `app/services/handlers/dipendente_handlers.py`

| Funzione | Modifica |
|---|---|
| `on_dipendente_created` | Rimosso `contratto = event.get("tipo_contratto")`, rimosso `"tipo contratto"` da `campi_mancanti`, rimosso alert `DIP_CONTRATTO_MANCANTE` |
| `on_dipendente_updated_risolvi` | Rimossa risoluzione alert `DIP_CONTRATTO_MANCANTE` |
| `on_dipendente_cessato` | Rimosso lo **step 1** (terminazione a cascata di tutti i `contratti_dipendenti` attivi via `update_many` su quella collection). Rinumerati step 2→1, 3→2, 4→3. Step "risoluzione alert" e "check flussi residui su cedolini" **invariati** |

Diagramma flusso `dipendente.cessato` — prima/dopo:

```
PRIMA                                   DOPO
─────                                   ────
1. termina contratti_dipendenti   ✗     (rimosso)
2. rifiuta richieste future       →     1. rifiuta richieste future
3. annulla partite aperte         →     2. annulla partite aperte
4. risolve alert aperti           →     3. risolve alert aperti
5. check flussi residui cedolini  →     4. check flussi residui cedolini
```

### 2.7 Dedup — `app/services/dipendenti_dedupe.py`

`_score_completezza`: rimossi `livello`, `tipo_contratto` da `campi_pesanti`
(usati per punteggio di completezza nel merge duplicati).

### 2.8 File eliminati (codice morto verificato, zero import esterni)

```
app/models/employee.py                                  (290 righe)
app/services/employee_service.py                        (497 righe)
app/repositories/employee_repository.py                 (395 righe)
app/scripts/migra_employee_contracts_a_contratti.py      (65 righe)
tests/test_p1_dipendenti_cessazione.py                   (89 righe — testava lo step 1 rimosso)
frontend/src/components/attendance/{constants,helpers,index}.js
```

Import ripuliti in cascata: `app/services/__init__.py` (rimosso
`EmployeeService`), `app/repositories/__init__.py` (rimossi
`EmployeeRepository`, `PayslipRepository`, `LibrettoSanitarioRepository`),
`app/models/__init__.py` (rimosso l'intero blocco `from .employee import`).

### 2.9 Collection — stato

| Collection | Prima | Dopo | Nota |
|---|---|---|---|
| `contratti_dipendenti` | CRUD completo | **codice non la tocca più** | Dati storici NON purgati in produzione — nessuno script di migrazione/cancellazione creato, solo smesso di leggerla/scriverla |
| `libretti_sanitari` | CRUD completo | **codice non la tocca più** | Idem — nessuna cancellazione dati |
| `employee_contracts` | alias legacy, mai scritto | **codice non la tocca più** | Era già vuoto/deprecato prima di questa sessione |
| `dipendenti` (`Collections.EMPLOYEES`) | — | **invariata, mantenuta** | Rimossi solo campi contratto/libretto dai NUOVI payload; documenti esistenti con quei campi non vengono ripuliti retroattivamente |
| `cedolini` (`Collections.PAYSLIPS`) | — | **invariata, mantenuta** | Zero riferimenti a contratto/libretto, verificato |

Costanti rimosse: `COLL_CONTRATTI_DIPENDENTI`, `COLL_EMPLOYEE_CONTRACTS`
(`app/db_collections.py`); `LIBRETTI_SANITARI` (`app/database.py::Collections`).
Indici Mongo rimossi (`app/database.py`): `idx_contratti_dip`,
`idx_contratti_dip_inizio` su `contratti_dipendenti`.

### 2.10 Frontend

| File | Modifica |
|---|---|
| `frontend/src/lib/queryClient.js` | Rimosso `queryKeys.contratti` (mai consumato) |
| `frontend/src/pages/MappaGestionale.jsx` | Card `id: 'dipendenti'`: testo aggiornato per non descrivere più "Contratti" come funzionalità di questo repo (resta un link esterno a `appdipendenti.onrender.com`) |
| `frontend/src/components/attendance/` | Cartella eliminata (orfana, nessun import in nessuna pagina) |

---

## 3. Modulo B — Fatture Estere: pipeline AI completa

### 3.1 Contesto/problema

Le fatture italiane arrivano via SDI/Aruba in XML (FatturaPA) — parsing
deterministico. I fornitori esteri (UE/extra-UE) non passano dallo SDI
(sistema solo italiano): mandano un semplice **PDF** via email. Stato
iniziale di questa sessione: il PDF veniva solo **archiviato** in
`documents_inbox` (categoria `fattura_estera_pdf`), senza estrazione dati
né creazione di una fattura — quindi **invisibile** ai motori di
riconciliazione (PayPal, bonifico) che leggono solo `invoices`.

Tre iterazioni, ciascuna con commit dedicato:

1. **Estrazione AI + fattura vera** (5f100aa0) — collega l'estrazione AI
   già usata per altri documenti, crea una fattura vera con la pipeline
   condivisa delle fatture XML.
2. **Aggancio fornitore su P.IVA estera** (275bbd84) — la guardia P.IVA
   italiana (11 cifre) escludeva i formati UE non italiani dall'aggancio
   automatico al fornitore.
3. **Coda di verifica + rating** (4cbd06ec) — l'utente conferma/corregge
   ogni lettura AI prima che diventi definitiva, costruendo uno storico di
   affidabilità per fornitore.

### 3.2 Architettura della pipeline (stato finale)

```
┌─────────────┐   ┌───────────────────┐   ┌────────────────────────┐
│ Email Gmail │──▶│ documents_inbox    │──▶│ sync_email_documents    │
│ (mittente   │   │ (pdf_data base64)  │   │ (email_monitor_service) │
│ attendibile)│   └───────────────────┘   └───────────┬────────────┘
└─────────────┘                                        │ tipo=="fattura_estera_pdf"
                                                         ▼
                                       ┌─────────────────────────────────┐
                                       │ process_fattura_estera_pdf       │
                                       │ (fatture_upload.py)              │
                                       │  1. document_ai_extractor        │
                                       │     .process_document_from_      │
                                       │     base64(document_type="fattura")│
                                       │  2. _ai_fattura_a_parsed(data)   │
                                       │     → schema "parsed" comune     │
                                       │     con parse_fattura_xml        │
                                       │  3. guardia: numero+importo?     │
                                       │     no → "dati_insufficienti"    │
                                       │     (nessuna fattura creata)     │
                                       └───────────────┬───────────────────┘
                                                        ▼
                                       ┌─────────────────────────────────┐
                                       │ import_parsed_invoice             │
                                       │ (CONDIVISA con process_xml_bytes) │
                                       │  • dedup su invoice_key           │
                                       │  • ensure_supplier_exists(        │
                                       │      piva_validator=              │
                                       │      _piva_estera_plausibile)     │
                                       │  • insert invoices (schema        │
                                       │    canonico)                      │
                                       │  • auto_registra_prima_nota       │
                                       │    (SEMPRE provvisoria)           │
                                       │  • propagate_event                │
                                       │    FATTURA_CREATED                │
                                       │    → crea partita_aperta          │
                                       │    → alert fornitore/audit/IVA/CDC│
                                       └───────────────┬───────────────────┘
                                                        ▼
                                       ┌─────────────────────────────────┐
                                       │ verifica_ai: "in_attesa"          │
                                       │ + alert FAT_ESTERA_DA_VERIFICARE  │
                                       │ (link "/fatture-estere-verifica") │
                                       └───────────────┬───────────────────┘
                                                        │
                          ┌─────────────────────────────┼─────────────────────────┐
                          ▼                                                       ▼
        ┌───────────────────────────────┐                    ┌──────────────────────────────┐
        │ Matching automatico ESISTENTE  │                    │ Utente conferma/corregge      │
        │ (nessun codice nuovo qui):     │                    │ (fatture_estera_verifica.py)  │
        │ • auto_associa_transazioni     │                    │  POST /{id}/verifica          │
        │   (PayPal, importo±0.05+nome)  │                    │  • diff vs valori AI           │
        │ • riconcilia_movimenti_banca   │                    │  • aggiorna invoices+speculari │
        │   (bonifico, idem)             │                    │  • rigenera invoice_key/scad.  │
        │ • FAT_DA_PAGARE_SCADUTA        │                    │    se numero/piva/data cambiano│
        │   (job giornaliero 7:00)       │                    │  • sync partita_aperta (solo   │
        └───────────────────────────────┘                    │    se ancora integra)           │
                                                               │  • insert fatture_estere_       │
                                                               │    verifiche (storico rating)   │
                                                               └──────────────────────────────┘
                                                                              │
                                                                              ▼
                                                               ┌──────────────────────────────┐
                                                               │ GET /affidabilita             │
                                                               │ aggrega per supplier_vat:      │
                                                               │ corrette/totale, percentuale   │
                                                               └──────────────────────────────┘
```

### 3.3 Router modificati/creati

| File | Prefix montato | Stato |
|---|---|---|
| `app/routers/invoices/fatture_upload.py` | `/api/fatture` | Modificato: refactor + 3 funzioni nuove |
| `app/services/email_monitor_service.py` | — (service, non router) | Modificato: nuovo ramo `elif tipo == "fattura_estera_pdf"` |
| `app/services/alert_engine.py` | — (service) | Modificato: 1 nuova entry in `ALERT_CATALOG` |
| `app/routers/fatture_estera_verifica.py` | `/api/fatture-estere` | **Creato** (nuovo router, 3 endpoint) |
| `app/router_registry.py` | — | Modificato: `_register_invoices` monta il nuovo router |

### 3.4 Endpoint — `fatture_upload.py` (esistenti, invariati nel comportamento)

| Metodo | Path | Funzione |
|---|---|---|
| POST | `/upload-xml` | `upload_fattura_xml` |
| POST | `/upload-xml-bulk` | `upload_fatture_xml_bulk` |
| DELETE | `/all` | `delete_all_invoices` |
| POST | `/sync-suppliers` | `sync_suppliers_from_invoices` |
| POST | `/categorize-movements` | `categorize_all_movements` |
| GET | `/{invoice_id}` | `get_fattura` |
| PUT | `/{invoice_id}` | `update_fattura` |
| PUT | `/{invoice_id}/classifica` | `classifica_fattura_manuale` |
| PUT | `/{invoice_id}/paga` | `paga_fattura` |
| DELETE | `/{invoice_id}` | `delete_invoice` |
| GET | `/{invoice_id}/entita-correlate` | `get_entita_correlate_fattura` |
| POST | `/recalculate-iva` | `recalculate_iva_all_invoices` |

Nessuna di queste route è stata toccata: la nuova pipeline fatture estere
NON passa da HTTP, viene invocata internamente da
`email_monitor_service.py`.

### 3.5 Funzioni chiave — `fatture_upload.py` (non-HTTP, riuso interno)

| Funzione | Riga | Scopo |
|---|---|---|
| `_piva_plausibile(vat)` | 162 | Guardia P.IVA italiana/UE 11 cifre — **invariata**, usata di default (fatture XML) |
| `_piva_estera_plausibile(vat)` | 173 | **Nuova.** Accetta anche formati P.IVA UE non italiani (2 lettere + 2-13 alfanumerici). Usata SOLO dal flusso estero |
| `ensure_supplier_exists(db, parsed, session, piva_validator=_piva_plausibile)` | 190 | **Firma estesa** con `piva_validator` iniettabile (default invariato per compatibilità) |
| `generate_invoice_key(number, vat, date)` | 982 | Invariata — riusata anche dal flusso estero e dalla correzione |
| `process_xml_bytes(db, content, filename, source)` | 1067 | **Refactored**: ora fa solo i passi 0-2 (decodifica/parse XML), poi delega a `import_parsed_invoice` |
| `import_parsed_invoice(db, parsed, filename, source, xml_raw=None, piva_validator=_piva_plausibile)` | 1109 | **Nuova, estratta da `process_xml_bytes`.** Pipeline condivisa: dedup → fornitore → costruzione documento canonico → insert → prima nota provvisoria → nota di credito → event bus `FATTURA_CREATED` |
| `process_fattura_estera_pdf(db, pdf_base64, filename, source, documento_inbox_id=None)` | 1239 | **Nuova.** Estrazione AI → `_ai_fattura_a_parsed` → guardia dati minimi → `import_parsed_invoice(piva_validator=_piva_estera_plausibile)` → marca `verifica_ai:"in_attesa"` → alert `FAT_ESTERA_DA_VERIFICARE` con link |
| `_ai_fattura_a_parsed(data)` | 1307 | **Nuova.** Converte l'output JSON di `document_ai_extractor` (prompt `"fattura"`) nello schema `parsed` comune a `parse_fattura_xml`; deduce `nazione` dal prefisso della P.IVA |

### 3.6 Endpoint — `fatture_estera_verifica.py` (nuovo router)

Prefix `/api/fatture-estere`:

| Metodo | Path | Funzione | Descrizione |
|---|---|---|---|
| GET | `/da-verificare` | `lista_da_verificare` | Fatture con `verifica_ai:"in_attesa"`, ordinate per `created_at` desc, max 200 |
| GET | `/affidabilita` | `affidabilita_fornitori` | Aggregazione `fatture_estere_verifiche` per `supplier_vat`: `totale`, `corrette`, `percentuale_corrette` |
| POST | `/{fattura_id}/verifica` | `verifica_fattura` | Conferma/corregge una fattura: diff campo-per-campo, update `invoices` (+ speculari), rigenera `invoice_key`/`data_scadenza` se serve, sync `partite_aperte` (solo se integra), insert `fatture_estere_verifiche`, risolve l'alert. 404 se fattura inesistente, 409 se già verificata |

Body atteso da `POST /{fattura_id}/verifica`:
```json
{
  "invoice_number": "...", "invoice_date": "YYYY-MM-DD",
  "supplier_name": "...", "supplier_vat": "...",
  "imponibile": 0.0, "iva": 0.0, "total_amount": 0.0
}
```
Campi omessi o vuoti = non toccati (restano quelli letti dall'AI).

### 3.7 Alert catalog — `app/services/alert_engine.py`

Nuova entry in `ALERT_CATALOG` (61 codici totali nel file, 1 aggiunto qui):

```python
"FAT_ESTERA_DA_VERIFICARE": {
    "modulo": "fatture",
    "severita": "warning",
    "titolo": "Fattura estera letta dall'AI — da verificare",
    "condizione_chiusura": "Utente conferma o corregge i dati letti"
}
```

Generato da `process_fattura_estera_pdf` via `genera_alert(...)` (idempotente
per codice+entità), risolto da `verifica_fattura` via `risolvi_alert(...)`.
Campo `link` impostato con update successivo (`db["alerts"].update_one`) a
`/fatture-estere-verifica` — letto da `frontend/src/components/
NotificationBell.jsx` per la navigazione al click.

### 3.8 Collection — dettaglio schema

**`invoices`** (`Collections.INVOICES`) — campi NUOVI sui documenti creati
dal flusso estero, aggiuntivi rispetto allo schema canonico XML già
esistente (`invoice_number`, `invoice_date`, `supplier_name`,
`supplier_vat`, `total_amount`, `imponibile`, `iva`, `divisa`,
`metodo_pagamento`, `status`, `source`, `filename`, `invoice_key`,
`cedente_piva`, `cedente_denominazione`, `numero_fattura`, `data_fattura`,
`importo_totale`, `anno` — tutti INVARIATI, stesso schema di
`process_xml_bytes`):

| Campo | Tipo | Impostato da | Scopo |
|---|---|---|---|
| `verifica_ai` | str: `"in_attesa"` \| `"confermata"` \| `"corretta"` | `process_fattura_estera_pdf` → `verifica_fattura` | Stato del ciclo di verifica umana |
| `verifica_ai_at` | str ISO | `verifica_fattura` | Timestamp verifica |
| `verifica_ai_campi_corretti` | list[str] | `verifica_fattura` | Nomi dei campi canonici corretti dall'utente |
| `documento_inbox_id` | str | `process_fattura_estera_pdf` | Id del documento in `documents_inbox`, per il link "Vedi PDF" |

Fatture XML italiane: questi 4 campi **non vengono mai impostati**
(`import_parsed_invoice` li scrive solo nel percorso `process_fattura_estera_pdf`,
non in `process_xml_bytes`).

**`fatture_estere_verifiche`** — **collection nuova**, stringa letterale
`db["fatture_estere_verifiche"]` (coerente con la convenzione dominante nel
repo: 1762 usi di stringa letterale contro 33 file che importano da
`Collections` e 8 da `db_collections.py` — nessuna costante dichiarata):

```python
{
    "id": str(uuid4()),
    "fattura_id": str,          # riferimento a invoices.id
    "supplier_vat": str,
    "supplier_name": str,
    "esito": "confermata" | "corretta",
    "campi_corretti": list[str],
    "created_at": str,          # ISO
}
```
Un documento per ogni verifica effettuata (append-only, mai aggiornato).
Fonte unica per il rating di `GET /affidabilita`.

**`fornitori`** (`Collections.SUPPLIERS`) — nessun campo nuovo, ma
`ensure_supplier_exists` ora può creare/agganciare record con `partita_iva`
in formato non italiano (prima impossibile per la guardia stretta) e con
`nazione` dedotta correttamente (prima defaultava sempre `"IT"` anche per
fornitori esteri, generando un falso alert `FORN_DATI_INCOERENTI`).

**`alerts`** — nessuna modifica di schema, solo un nuovo `codice` possibile
(`FAT_ESTERA_DA_VERIFICARE`) e uso del campo esistente `link` (già letto da
`NotificationBell.jsx`, non impostato da `genera_alert` di default — aggiunto
qui con un update mirato).

**`partite_aperte`** — nessun campo nuovo. `verifica_fattura` può
aggiornare `importo_originale`/`residuo` di una partita esistente **solo
se** `residuo == importo_originale` (nessun pagamento/match ricevuto);
altrimenti non la tocca (per non corrompere una riconciliazione parziale
già in corso).

**`documents_inbox`** — nessuna modifica di schema. Il campo `id` di un
documento qui viene ora propagato come `documento_inbox_id` sull'invoice
corrispondente, per collegare fattura↔PDF originale.

### 3.9 Guardie di sicurezza dati

| Guardia | Dove | Comportamento |
|---|---|---|
| Nessun numero E nessun importo estratti | `process_fattura_estera_pdf` | Ritorna `"dati_insufficienti"`, **nessuna fattura creata** — il PDF resta solo archiviato (comportamento pre-esistente) |
| Estrazione AI fallisce (eccezione o `success:false`) | `process_fattura_estera_pdf` | Ritorna `"extraction_error"`, nessuna fattura creata |
| Fattura già esistente (stesso `invoice_key`) | `import_parsed_invoice` | Ritorna `"duplicate"` |
| P.IVA cedente == P.IVA/nome cessionario (autofattura) | `ensure_supplier_exists` (invariata) | Nessun fornitore creato/agganciato |
| Verifica già effettuata | `verifica_fattura` | HTTP 409 |
| Fattura inesistente | `verifica_fattura` | HTTP 404 |
| Correzione importo su partita parzialmente pagata | `verifica_fattura` | **Non applicata in automatico** — richiede intervento manuale |

### 3.10 Frontend

| File | Stato | Descrizione |
|---|---|---|
| `frontend/src/pages/FattureEstereVerifica.jsx` | **Creato** | Lista fatture `in_attesa`, form pre-compilato per campo, badge rating fornitore, bottone "Vedi PDF" (riusa `DocumentViewerModal` esistente via `fetchUrl=/api/documenti/documento/{documento_inbox_id}/download`), submit → `POST /api/fatture-estere/{id}/verifica` |
| `frontend/src/main.jsx` | Modificato | Route `{ path: "fatture-estere-verifica", ... }`, lazy import |
| `frontend/src/pages/MittentiEmail.jsx` | Modificato | Link alla coda di verifica, testo info box aggiornato |
| `frontend/src/lib/queryClient.js` | — | Non toccato in questo modulo |

Nessuna voce aggiunta in `navigation.config.js` (pattern coerente con
`DatiProvvisoriPage`, raggiungibile solo via link diretto, non da menu
principale — visibilità garantita dall'alert cliccabile).

### 3.11 Test

| File | Copertura |
|---|---|
| `tests/test_fattura_estera_ai.py` (7 test) | `_ai_fattura_a_parsed` mapping, creazione fattura da estrazione riuscita, dedup, estrazione fallita, dati insufficienti, `_piva_estera_plausibile` formati UE, aggancio fornitore + nazione dedotta |
| `tests/test_fattura_estera_verifica.py` (10 test) | Lista da verificare, conferma senza correzioni, correzione importo + sync speculari, correzione numero → rigenera `invoice_key`, correzione data → ricalcola scadenza, 404/409, sync `partita_aperta` (integra vs già toccata), rating aggregato |

Totale: **374 test passati, 2 skipped** (suite completa, nessuna regressione).
Build frontend verificata (`npm run build`, bundle `FattureEstereVerifica-*.js`
generato correttamente).

---

## 4. Mappa collection — riepilogo sessione

| Collection | Stato in questa sessione | Note |
|---|---|---|
| `contratti_dipendenti` | Codice smesso di leggerla/scriverla | Dati non purgati |
| `libretti_sanitari` | Codice smesso di leggerla/scriverla | Dati non purgati |
| `employee_contracts` | Codice smesso di leggerla/scriverla | Era già alias morto |
| `dipendenti` | Invariata (solo meno campi nei nuovi payload) | |
| `cedolini` | Invariata | Verificata isolata da contratto/libretto |
| `invoices` | **4 campi nuovi** (`verifica_ai*`, `documento_inbox_id`) sui soli documenti dal flusso estero | Schema canonico XML invariato |
| `fornitori` | Nessun campo nuovo, ma popolamento `nazione`/`partita_iva` estesa ai formati UE | |
| `alerts` | 1 nuovo `codice` possibile (`FAT_ESTERA_DA_VERIFICARE`) | Schema invariato |
| `partite_aperte` | Nessun campo nuovo, possibile update mirato da `verifica_fattura` | |
| `documents_inbox` | Invariata, solo letta (id propagato) | |
| `fatture_estere_verifiche` | **Collection creata** | Append-only, fonte del rating |

---

## 5. Router registry — diff

`app/router_registry.py`, funzione `_register_invoices`:

```diff
     from app.routers.fatture_module import router as fatture_ricevute_router
+    from app.routers import fatture_estera_verifica

     app.include_router(invoices_emesse.router, prefix="/api/invoices/emesse", tags=["Invoices Emesse"])
     app.include_router(invoices_main.router, prefix="/api/invoices", tags=["Invoices"])
     app.include_router(fatture_upload.router, prefix="/api/fatture", tags=["Fatture Upload"])
     app.include_router(fatture_drive.router, prefix="/api/fatture", tags=["Fatture Drive"])
     app.include_router(fatture_ricevute_router, prefix="/api/fatture-ricevute", tags=["Fatture Ricevute"])
     app.include_router(corrispettivi.router, prefix="/api/corrispettivi", tags=["Corrispettivi"])
+    app.include_router(fatture_estera_verifica.router, prefix="/api/fatture-estere", tags=["Fatture Estere Verifica"])
```

Verificato a runtime (`register_all_routers` su `FastAPI()` pulita):

```
/api/fatture-estere/da-verificare
/api/fatture-estere/affidabilita
/api/fatture-estere/{fattura_id}/verifica
```

---

## 6. Limiti noti / debito tecnico aperto

1. **Nessuna cancellazione dati storiche**: `contratti_dipendenti` e
   `libretti_sanitari` restano su MongoDB con tutti i documenti già
   esistenti — solo il codice ha smesso di leggerli/scriverli. Se si vuole
   liberare spazio o evitare confusione futura, serve uno script di
   archiviazione dedicato (pattern già usato per HACCP:
   `app/scripts/archivia_collection_haccp.py`).
2. **Documenti `dipendenti` esistenti** possono ancora avere i campi
   `tipo_contratto`/`livello`/`libretto_*` popolati da import precedenti —
   non vengono ripuliti retroattivamente (nessuna migrazione eseguita).
3. **Estrazione AI senza punteggio di confidenza**: `document_ai_extractor`
   restituisce solo `success: bool`, non un punteggio di affidabilità del
   singolo campo — il rating per fornitore nasce interamente dalle verifiche
   umane in `fatture_estere_verifiche`, non da un self-score del modello.
4. **Valuta sempre assunta EUR**: il prompt di estrazione fatture non
   estrae la valuta; una fattura in USD/GBP verrebbe letta con l'importo
   numerico corretto ma trattata come EUR.
5. **Correzione importo su partita già parzialmente pagata**: non gestita
   in automatico per sicurezza (rischio di corrompere una riconciliazione
   in corso) — resta un task manuale se capita.
6. **Nessuna voce di menu dedicata** per "Fatture estere da verificare":
   raggiungibile solo via link da Mittenti Email o alert cliccabile,
   coerente col pattern di altre pagine "coda" del repo ma potenzialmente
   meno visibile per un utente che non guarda gli alert.

---

## 7. Richiamo sintetico — resto della sessione (contesto, non dettagliato qui)

Prima dei due moduli sopra, nella stessa sessione sono stati completati (a
livello di commit, non riverificati riga per riga in questo documento):
pulizia di 19 route morte nella pipeline paghe; §6.4/§12 allowlist endpoint
pubblici con test-fotografia; §14/§16 `MATRICE_FUNZIONALE_FINALE.md` e
`AUDIT_ESECUZIONE_DEFINITIVO.md`; A6 test cespiti/chiusura + guardia
anti-doppia-chiusura (409); A7 registro contabile unico
`movimenti_contabili` (TFR e ammortamenti in partita doppia, libro
giornale/mastro riletti da lì); numero di protocollo reso progressivo per
anno (con migrazione non distruttiva); fix di un bug preesistente in 10
script `migra_*.py` (`Database.connect()` → `connect_db()`); attivazione
schedulata della scansione notifiche Aruba (`aruba_notifiche_scan`); pagina
`MittentiEmail.jsx` + job `mittenti_email_sync`; `memoria/AUDIT_AUTOMATISMI.md`
(mappa completa scheduler vs codice dichiarato). Dettaglio in
`memoria/AUDIT_AUTOMATISMI.md`, `memoria/AUDIT_ESECUZIONE_DEFINITIVO.md`,
`memoria/MATRICE_FUNZIONALE_FINALE.md` e nei messaggi di commit
corrispondenti (`git log`).

---

## 8. Verifica finale

```
python -m pytest -q          → 374 passed, 2 skipped
cd frontend && npm run build → OK (FattureEstereVerifica-*.js generato)
```

Branch: `claude/repo-restructure-review-z0gg7w`, fast-forward su `main`
dopo ogni commit (nessun merge commit, storia lineare).

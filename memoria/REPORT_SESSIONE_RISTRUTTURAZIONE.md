# Report ristrutturazione GestionaleCloud — FASE P0 + FASE P1

> Documento riepilogativo di tutto il lavoro svolto: correzioni, consolidamenti,
> modifiche tecniche/architetturali/grafiche, collezioni tenute/eliminate/deprecate,
> migrazioni da eseguire e debito residuo.
> Branch: `main` + `claude/repo-restructure-review-z0gg7w` (allineati). **324 test verdi.**

---

## 1. Sintesi

| Fase | Contenuto | Stato |
|------|-----------|-------|
| **P0** | 12 bug di correttezza | ✅ chiusi con test |
| **P1 §5** | Consolidamento collezioni (5.1–5.9) | ✅ completo |
| **P1 §6.1** | Motore unico registrazione contabile | ✅ |
| **P1 §6.4** | Funzione unica saldo Prima Nota | ✅ |
| **P1 §6.6** | EC importer (verifica adapter) | ✅ verificato |
| **P1 §6.2/6.3/6.5/6.7/6.8/6.9** | Bilancio/schema/cespiti/PayPal/cash/verbali | ⏳ analisi pronta, decisioni utente |
| **P1 §7** | Classificazione 1106 endpoint | ✅ deliverable |
| **P1 §8** | Viewer documenti canonico | ✅ |
| **P1 §9** | F24/quietanze/cedolini | ✅ (regole già presenti + stato canonico) |
| **P1 §10** | IVA (test mancanti) | ✅ |
| **P1 §11** | Prestazioni | ✅ (fix + audit) |

Principio guida rispettato in tutta la sessione: **non rompere l'applicazione**. Ogni
consolidamento è NON distruttivo (le collezioni legacy non vengono cancellate: si
migrano → si deprecano → restano come archivio). Ogni fix ha un test di regressione.

---

## 2. Collezioni — canoniche, deprecate, separate, no-write

### 2.1 Canoniche (usare SEMPRE queste)
| Dominio | Canonica | Note |
|---------|----------|------|
| F24 | `f24_unificato` | §5.1 — chiave: contribuente+periodo+saldo+pdf_hash+protocollo |
| Dipendenti (anagrafica) | `dipendenti` | §5.2 — mai `employees` |
| Contratti dipendenti | `contratti_dipendenti` | §5.2 — tutto il CRUD contratti |
| Cedolini (elaborato) | `cedolini` | §5.3 |
| Fatture passive | `invoices` | §5.4 — chiave: numero+piva+data |
| Fatture emesse | `fatture_emesse` | §5.5 — **scelta utente** "un unico posto reale" |
| Estratto conto (movimenti) | `estratto_conto_movimenti` | §5.6 — unica sorgente riconciliazione/saldi |
| Fornitori | `fornitori` | §5.7 — mai `suppliers` |
| Documenti classificati | `documenti_classificati` | §5.8 — **scelta utente**, unificata con email |
| Registrazioni partita doppia | `movimenti_contabili` | §6.1 — schema CEE puntato |
| Prima Nota | `prima_nota_cassa` / `prima_nota_banca` | §6.4 |

### 2.2 Legacy/DEPRECATE (migrate, NON scrivere, non cancellate)
| Legacy | → Canonica | Migrazione |
|--------|-----------|------------|
| `f24_models` | `f24_unificato` | `migra_f24_unificato.py` |
| `payslips` | `cedolini` | `migra_payslips_a_cedolini.py` |
| `employee_contracts` | `contratti_dipendenti` | `migra_employee_contracts_a_contratti.py` |
| `staff` | `dipendenti` | `migra_staff_a_dipendenti.py` |
| `invoices_emesse` | `fatture_emesse` | `migra_invoices_emesse_a_fatture.py` |
| `documents_classified` | `documenti_classificati` | `migra_documents_classified.py` |
| `estratto_conto` (backup) | `estratto_conto_movimenti` | ⚠️ NON unire (rischio doppio conteggio) |
| `bank_statements` | `estratto_conto_movimenti` | alias, nessun accesso diretto |
| `anagrafica_dipendenti` | `dipendenti` | già migrata |

### 2.3 SEPARATE — tenute apposta (concetti diversi, NON alias)
| Collezione | Cos'è | Distinta da |
|------------|-------|-------------|
| `cedolini_email_attachments` | file email ricevuto (origine) | `cedolini` (elaborato) |
| `riepilogo_cedolini` | aggregato | `cedolini` |
| `estratti_conto` | registro documenti EC caricati | `estratto_conto_movimenti` (righe) |
| `bank_statements_imported` | metadati statement importati | `estratto_conto_movimenti` |

### 2.4 NO-WRITE — giacenza magazzino (§5.9)
`warehouse_stocks`, `warehouse_products`, `magazzino`, `magazzino_articoli`,
`magazzino_movimenti`, `movimenti_magazzino`: nessuna NUOVA scrittura (giacenza fisica
non usata). **Non cancellare** (condivise con l'app di magazzino). Si tengono solo
Dizionario Articoli (`dizionario_prodotti`) e storico acquisti (`acquisti_prodotti`,
`dettaglio_righe_fatture`, `warehouse_movements`).

---

## 3. Cosa è stato ELIMINATO / TENUTO

**Nulla è stato eliminato dalle collezioni dati** (migrazioni non distruttive).
- **Tenuto** (regola utente "se usati li devi tenere"): tutti i sottosistemi vivi —
  parser F24, `buste_paga` (Libro Unico/BPM/TFR), Learning Machine, GestioneAssegni,
  `cash.py`, `bank_statement_import`, contabilità italiana. NON rimossi.
- **Eliminato dal codice** (solo duplicazione runtime, non dati):
  - dedup runtime a due sorgenti in `fatture_module/crud.py` (§5.4);
  - schemi divergenti dei movimenti contabili (unificati nel motore §6.1);
  - formula di saldo Prima Nota duplicata in cassa/banca (unificata §6.4).
- **Deprecato ma conservato**: le collezioni legacy in §2.2 (archivio).

---

## 4. Modifiche tecniche/architetturali

### 4.1 Nuovi moduli/motori
- `app/services/f24_canonico.py`, `cedolini_canonico.py`, `fatture_canonico.py` —
  helper con chiave naturale + `salva_*()` idempotente per dominio.
- `app/services/registrazione_contabile.py` (**§6.1**) — motore UNICO partita doppia
  (schema CEE): idempotenza, numero registrazione progressivo, fonte documento, data
  competenza, DARE/AVERE per riga, centro di costo, audit log, ricostruzione. I 4
  endpoint (registra-fattura/registra-tutte-fatture/registra-corrispettivi/
  ricategorizza-fatture) delegano al motore.
- `prima_nota_module/common.aggrega_saldo_prima_nota()` (**§6.4**) — funzione unica di
  saldo (segno, riporto/saldo iniziale, saldo finale). Usata da cassa.py e banca.py.

### 4.2 Pattern di consolidamento collezioni (ripetuto §5.x)
helper canonico (chiave naturale + upsert idempotente) → script di migrazione non
distruttivo (dry-run / `--esegui`) → redirect lettori/scrittori sulla canonica →
marcatura DEPRECATA → test con mock async del DB.

### 4.3 Bug corretti in P1 (oltre ai 12 P0)
- **§5.2 cessazione dipendente**: terminava i contratti su `employee_contracts` (alias
  vuoto) invece della canonica `contratti_dipendenti` → alla cessazione i contratti reali
  non venivano mai chiusi. Corretto.
- **§5.5 fatture emesse split-brain**: scritte in `invoices_emesse` ma lette (crediti/
  ricavi/IVA a debito) da `fatture_emesse` vuota. Unificato su `fatture_emesse`.
- **§6.1 giornale**: i movimenti batch non impostavano `data_documento`/`data_registrazione`
  → non comparivano correttamente nel giornale. Corretto.
- **§6.1 ricostruzione**: `ricategorizza-fatture` cancellava TUTTI i movimenti (anche
  ammortamenti/TFR letti dalla chiusura esercizio). Ora preserva ammortamenti/TFR.

### 4.4 §9 F24/quietanze
Regole vincolanti già implementate (associazione F24-cedolini per soggetto/periodo/
posizione/causale, DM10↔RC01, POSSIBILE DOPPIO PAGAMENTO, saldo F24 non auto-deducibile).
Aggiunto lo **stato canonico** `QUIETANZA_PRESENTE_F24_MANCANTE` (§9.3) con test che
garantisce alert bloccante, calcolo sospeso e **nessuna ricostruzione automatica** dell'F24.

---

## 5. Modifiche grafiche/frontend

### `DocumentViewerModal.jsx` (§8) — componente CANONICO "Vedi Documento"
Modale in-page per tutti i tipi documento (fattura HTML/PDF, cedolino, F24, quietanza,
estratto conto, allegato email, verbale, PagoPA, PDF). Funzioni obbligatorie §8.2
ora presenti:
- Chiudi · Scarica · Schermo intero · **Zoom +/−** · **Adatta larghezza** · **Adatta pagina**
- scroll interno · **touch/pinch** · blocco scroll body · **focus trap** · ESC
- `role="dialog"` `aria-modal` + aria-label su tutti i bottoni · **ritorno focus al
  pulsante di origine** · nuova prop `documentType`.

Build frontend verificata (`frontend/dist` aggiornato, versionato per Render).

---

## 6. Migrazioni da eseguire AL DEPLOY (non distruttive, idempotenti)

```bash
python -m app.scripts.migra_f24_unificato --esegui
python -m app.scripts.migra_payslips_a_cedolini --esegui
python -m app.scripts.migra_employee_contracts_a_contratti --esegui
python -m app.scripts.migra_staff_a_dipendenti --esegui
python -m app.scripts.migra_fatture_passive_a_invoices --esegui
python -m app.scripts.migra_invoices_emesse_a_fatture --esegui
python -m app.scripts.migra_documents_classified --esegui
```
(Ogni script senza `--esegui` fa un dry-run.)

---

## 7. Deliverable prodotti in `memoria/`
- `PROMPT_DEFINITIVO_CLAUDE_GESTIONALECLOUD.md` — prompt + tracker STATO AVANZAMENTO.
- `PIANO_MIGRAZIONE_COLLECTION.md` — piano §5 dettagliato.
- `ENDPOINT_CLASSIFICAZIONE_FINALE.md` — 1106 endpoint (650 tenere, 437 verificare,
  19 admin-only). Rigenerabile: `python scripts/genera_classificazione_endpoint.py`.
- `ANALISI_MOTORI_CONTABILI.md` — analisi §6.2–6.9 con decisioni/rischi.
- `AUDIT_PERFORMANCE_N1.md` — §11: query illimitate/N+1 da rivedere una per una.
- `BUG_CORRETTI_2026-07.md` — dettaglio P0.
- `REPORT_SESSIONE_RISTRUTTURAZIONE.md` — questo file.

---

## 8. Debito residuo (documentato, da decidere)

| Voce | Perché rinviato | Decisione che serve |
|------|-----------------|---------------------|
| **§6.2 Bilancio unico** | schema deciso (CEE puntato) ma serve mapping conto-per-conto | tabella `400100`→`05.01.01` (corrispondenza contabile) |
| **§6.5 Cespiti** | 2 sistemi | quale è canonico (dove sono i dati reali) |
| **§6.7 PayPal** | dominio ampio | audit dedicato prima di unificare |
| **§6.8 Cash adapter** | `cash.py` FE-wired | mappare schemi `cash_movements`↔`prima_nota_cassa` |
| **§6.9 Verbali** | 3 router | schema comune ingest/CRUD/riconciliazione |
| **parser F24** | sottosistema vivo | consolidamento in fase paghe dedicata |
| **`buste_paga`** | Libro Unico/BPM/TFR vivo | consolidamento in fase paghe dedicata |
| **§11 query illimitate** | 22 `to_list(100000)` | rivedere una per una (aggregazioni finanziarie non troncabili) |
| **guard Admin-only** | 19 endpoint migrazione | applicare protezione (FASE P2) |

**Non ancora iniziata:** FASE P2 (§12–§13 sicurezza/pulizia).

---

## 9. Verifica
- `python -m pytest -q` → **324 passed, 2 skipped**.
- Boot backend: `register_all_routers` OK.
- Build frontend (Vite): OK.
- Ogni fase: test + commit su `main` + branch, con nota "eseguire migrazione al deploy".

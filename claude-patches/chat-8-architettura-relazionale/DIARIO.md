# DIARIO SVILUPPO — Gestionale Ceraldi Group

---

## Chat 8 — 22 Aprile 2026

### Obiettivo
Definizione architettura relazionale completa del gestionale.

### Cosa è stato fatto
1. **Analisi stato attuale**: letto repo completo (~200 router, ~90 pagine JSX, ~90 collezioni MongoDB)
2. **Lette 10 specifiche operative** fornite da Enzo: Dipendenti, Cedolini, Fatture, Fornitori, F24, Prima Nota Banca, Prima Nota Cassa, Magazzino/Prodotti, Documenti/Inbox, Riconciliazione
3. **Decisioni architetturali approvate**:
   - Riconciliazione → collezione dedicata `riconciliazioni_match` (supporta N:M)
   - Alert → collezione unica `alerts` con codici standardizzati
   - Eventi → sincroni via `event_bus.py` (no Redis/Celery)
   - Partite aperte → materializzate in collezione `partite_aperte`
4. **Creato `PIANO_LAVORO_RELAZIONALE.md`** con:
   - Stato attuale sistema (moduli, collezioni, volumi)
   - 4 decisioni architetturali vincolanti
   - 6 nuovi servizi backend da creare
   - Piano 8 fasi (Chat 9-16)
   - Catalogo completo 40+ alert con trigger e chiusura
   - Mappa relazionale visuale dei moduli
   - Regole di sviluppo permanenti

### Aggiornamento .md (secondo commit)
6. **Verificato piano vs README**: trovate e corrette 3 incoerenze:
   - `warehouse_stocks` → `warehouse_inventory` (canonica reale da db_collections.py)
   - Colori design system: viola nella memoria → navy #0f2744 + oro #b8860b (reale in utils.js)
   - Regole mancanti nel README (6-8): db_collections.py, patch Claude, propagate_event
7. **Riscritti tutti i .md del repo**:
   - `README.md` — sezione architettura relazionale + servizi core
   - `memoria/INDEX.md` — collezioni aggiornate ai volumi reali + servizi core + 16 regole
   - `memoria/PRD.md` — stato aggiornato + piano Chat 9-16
   - `memoria/LOGICA_OPERATIVA.md` — sezione 5 completa: event bus, partite, riconciliazione, alert, mappa
   - `memoria/BACKLOG.md` — nota collegamento piano relazionale

### File di riferimento
- `PIANO_LAVORO_RELAZIONALE.md` — piano completo (salvato in outputs)
- Specifiche `.txt` — 10 documenti operativi forniti da Enzo

---

## Chat 9 — 22 Aprile 2026

### Obiettivo
Implementare tutti gli handler eventi + dashboard frontend per il sistema relazionale.

### Cosa è stato fatto (5 commit)

**Commit 9a — Handler Fatture↔Fornitori:**
- `fattura_handlers.py`: 5 handler (crea partita, alert fornitore, audit, pagata→risolvi, fornitore aggiornato→cascata)

**Commit 9b — Handler Banca↔Riconciliazione:**
- `banca_handlers.py`: 3 handler (cerca match scoring 4 livelli, match confermato→propaga effetti, audit)
- Propagazione match: aggiorna fattura/F24/cedolino/POS come pagato + risolve alert

**Commit 9c — Handler F24, Cedolini, Corrispettivi, Trasferimenti:**
- `f24_handlers.py`: 2 handler (partita F24 + alert scadenza, pagato→risolvi)
- `cedolino_handlers.py`: 2 handler (partita stipendio + alert dip non trovato, pagato→risolvi)
- `corrispettivo_handlers.py`: 1 handler (split contanti→cassa + POS→partita attesa banca)
- `trasferimento_handlers.py`: 1 handler (crea lato opposto cassa↔banca idempotente)

**Commit 9d — Handler Dipendenti, Magazzino, Documenti (copertura 10/10):**
- `dipendente_handlers.py`: 3 handler (deduplica CF+nome, alert incompleto/IBAN/contratto, cessato flussi attivi)
- `magazzino_handlers.py`: 2 handler (matching prodotto 3 livelli esatto→normalizzato→fuzzy, verifica sotto scorta)
- `documento_handlers.py`: 2 handler (classificazione auto XML/F24/cedolino/verbale, instradamento+deduplica hash)
- `deduplica_dipendente_patch.py`: funzione cerca_duplicato_dipendente per deduplica.py

**Commit 9e — Dashboard Relazionale Frontend + API:**
- `DashboardRelazionale.jsx`: 4 tab (Panoramica, Alert, Partite Aperte, Riconciliazione)
- `partite_aperte_api.py`: GET /stats, /lista, /scadute
- `riconciliazione_stats_api.py`: GET /stats

### Verifica finale
- 21/21 Python syntax check ✅
- 8/8 funzioni importate verificate ✅
- 29/29 codici alert nel catalogo ✅
- 16/16 EventTypes definiti ✅
- 13/13 import frontend da utils.js ✅
- 4/4 endpoint API coerenti ✅
- 3 __init__.py mancanti → aggiunti

### Totali
- 39 file, ~7.500 righe
- 6 servizi core + 20 handler su 13 tipi evento + 48 codici alert
- 2 router API nuovi + 1 pagina frontend
- 10/10 specifiche operative coperte

### Prossimo passo — Chat 10
Emergent applica le patch, poi si può lavorare su:
- Dashboard principale con widget alert integrato
- Fascicolo dipendente unificato
- Scheda fornitore arricchita
- Backlog P0/P1 (Piano Conti, Controllo Mensile, Cespiti)

---

## Chat 9 (continuazione) — 22 Aprile 2026

### Obiettivo
Controllo qualità e fix critici su calcoli IVA, prima nota, banca, cedolini,
fornitori, dashboard, scadenze, import documenti.

### Fix applicati direttamente nel repo (7 commit)

1. **Fix IVA saldo progressivo** (`iva_calcolo.py` + `IVA.jsx`):
   Aggiunto riporto credito/debito mese precedente. Marzo non è più
   "Da versare" se il credito accumulato copre. Nuove colonne:
   Riporto, Saldo Anno, N.Corr, N.Fatt.

2. **Fix Prima Nota Cassa** (`PrimaNota.jsx`):
   Rimosso "Saldo Cumulativo" €-485K e "Riporto Anni Prec." dalla cassa.
   saldoPrecedente tabella movimenti impostato a 0.

3. **Fix Banca riporto negativo** (`PrimaNota.jsx`):
   Check `> 0` → `!== 0` per mostrare riporto anche se negativo.

4. **Fix Prima Nota duplicati fatture** (`import_xml.py`):
   Aggiunto `find_one(fattura_id)` prima di `insert_one`. Se esiste già
   un movimento per la stessa fattura, non crea duplicato.

5. **Fix import .p7m** (`documenti.py`):
   Il detector ora gestisce `.p7m` e `.xml.p7m`, cerca i marker XML
   nel wrapper P7M per classificare fatture e corrispettivi firmati.

6. **Fix pagamento fatture dal fornitore** (`Fornitori.jsx`):
   Aggiunta colonna "Azioni" nel modale estratto fatture con bottoni
   💵Cassa e 🏦Banca → chiama `/api/fatture-ricevute/paga-manuale`.

7. **Fix modale chiudi/stampa/X** (`Fornitori.jsx`):
   Aggiunto onClick overlay per chiudere + stopPropagation sul contenuto.

8. **Fix Dashboard bilancio** (`dashboard.py`):
   Filtro costi fatture ora cerca con `$or` su anno/invoice_date/
   data_ricezione/data_documento.

9. **Fix Scadenze IVA progressivo** (`scadenze.py`):
   Aggiunto saldo_progressivo con riporto credito. Nuovi campi:
   `da_versare_effettivo` e `importo_versamento_effettivo`.

### Patch aggiunta
- `claude-patches/chat-9-fix-dipendenti/`: fascicolo dipendente completo
  con matching stipendi banca (3 strategie), arricchimento anagrafica,
  presenze, TFR, saldi.

---

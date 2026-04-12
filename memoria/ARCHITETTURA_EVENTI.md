# Architettura Event Bus — Ceraldi ERP
> Visione architetturale del sistema a eventi | Aggiornato: Aprile 2026

---

## IL PROBLEMA E LA SOLUZIONE

**Il problema**: la logica è sparsa in 80+ file. Ogni router fa il suo pezzo ma non sa cosa fanno gli altri. Quando arriva una fattura, 5 file diversi potrebbero aggiornarsi — o potrebbero non farlo, dipende da quale router è stato chiamato.

**La soluzione**: un **Bus degli Eventi** centrale (`app/core/event_bus.py`). Ogni operazione importante pubblica un evento. Ogni modulo che deve reagire si è pre-registrato. Nessuno dimentica nulla perché non è il singolo agente a ricordarsi — è il sistema.

---

## IL BUS DEGLI EVENTI

**Collection MongoDB**: `eventi_sistema`

```json
{
  "id": "uuid",
  "tipo": "fattura.importata",
  "payload": { "fattura_id": "...", "fornitore_piva": "..." },
  "processato": false,
  "handlers_completati": [],
  "handlers_falliti": [],
  "created_at": "ISO timestamp",
  "processed_at": null
}
```

**Funzionamento**: ogni handler ha nome univoco, tipo evento che ascolta, funzione da eseguire, priorità e max 3 retry. Se fallisce → errore in `eventi_log`. Gli altri handler continuano — nessun dato va perso.

---

## TABELLA HANDLER REGISTRATI

```
Evento                      → Handler                      → Modulo
──────────────────────────────────────────────────────────────────────────
fattura.importata           → handler_magazzino            → warehouse
fattura.importata           → handler_scadenziario         → contabilita
fattura.importata           → handler_nota_credito         → contabilita
fattura.importata           → handler_lotti                → tracciabilita
fattura.importata           → handler_learning_cdc         → agenti
fattura.importata           → handler_ingredienti_update   → cucina/magazzino
fattura.importata           → handler_notifica             → realtime

cedolino.importato          → handler_salva_cedolino       → hr
cedolino.importato          → handler_progressivi          → hr
cedolino.importato          → handler_tfr                  → hr
cedolino.importato          → handler_ferie                → hr
cedolino.importato          → handler_prima_nota_salari    → contabilita
cedolino.importato          → handler_riconcilia_stipendio → contabilita
cedolino.importato          → handler_agente_hr            → agenti
cedolino.importato          → handler_notifica             → realtime

documento.ricevuto          → handler_routing_tipo         → agenti
estratto_conto.importato    → handler_matching_f24         → contabilita
estratto_conto.importato    → handler_matching_stipendi    → contabilita
estratto_conto.importato    → handler_matching_fatture     → contabilita
estratto_conto.importato    → handler_matching_pos         → contabilita
fattura.pagata              → handler_prima_nota_auto      → contabilita
fattura.pagata              → handler_scadenza_saldata     → contabilita
fornitore.creato            → handler_learning_fornitore   → agenti
ingrediente.prezzo_cambiato → handler_ricette_update       → cucina/magazzino
ingrediente.prezzo_cambiato → handler_alert_margine        → realtime
```

---

## FLUSSO COMPLETO — ARRIVA UNA FATTURA XML

### Step 1 — Parsing (Router `fatture_module/import_xml.py`)
- Legge XML (UTF-8, latin-1, iso-8859-1, cp1252)
- Estrae: P.IVA, ragione sociale, numero, data, tipo (TD01/TD04/TD08…), righe con quantità+prezzo+IVA, totali, allegati PDF, scadenza
- Anti-duplicato: stesso numero + stessa P.IVA → skip o aggiornamento

### Step 2 — Fornitore (`fatture_module/helpers.py`)
- Cerca per P.IVA in `suppliers` → crea o aggiorna
- Recupera: metodo pagamento predefinito, IBAN, flag "escludi magazzino"
- Evento pubblicato: `fornitore.creato` o `fornitore.aggiornato`

### Step 3 — Salvataggio
- Salva fattura in `invoices` con stato `provvisoria`
- Salva righe in `dettaglio_righe_fatture`
- Salva allegati PDF (base64) in `allegati_fatture`
- Evento pubblicato: `fattura.importata`

### Step 4 — Handler in ordine

**Handler 1 — MAGAZZINO** (se fornitore non è "escludi magazzino")
- Crea movimento di carico in `warehouse_movements` per ogni riga
- Aggiorna giacenze in `warehouse_inventory`
- Se descrizione contiene codice lotto → collega al lotto in `lotti`
- Se descrizione contiene data scadenza → salva sul movimento

**Handler 2 — SCADENZIARIO**
- Legge data scadenza dall'XML
- Se assente → calcola `data_fattura + gg_pagamento_fornitore`
- Crea scadenza in `scadenziario_fornitori` stato `aperta`

**Handler 3 — NOTA DI CREDITO** (solo TD04/TD08)
- Cerca fattura originale per numero riferimento + P.IVA
- Aggiorna originale: `ha_nota_credito: true`, `importo_stornato`, `importo_residuo`
- Aggiorna scadenza originale: riduce importo
- Crea movimento inverso in magazzino (scarico)

**Handler 4 — LOTTI TRACCIABILITÀ** (solo se riga ha codice lotto)
- Crea/aggiorna lotto in `lotti` con: fornitore, prodotto, quantità, date
- FIFO per scadenza: aggiorna quantità disponibile

**Handler 5 — LEARNING MACHINE**
- Classifica la fattura per centro di costo (Rosticceria, Pasticceria, Veicoli…)
- Calcola deducibilità IRES/IRAP e detraibilità IVA
- Aggiorna `centro_costo_id`, `imponibile_deducibile_ires`, `iva_detraibile` sulla fattura
- Aggiorna `learning_rules` se trova nuovi pattern

**Handler 6 — PRIMA NOTA** (aspetta conferma)
- Prepara il movimento ma NON lo scrive ancora
- Segna `prima_nota_pronta: true` sulla fattura
- Viene scritto solo quando l'estratto conto conferma il pagamento

**Handler 7 — NOTIFICA**
- WebSocket alla UI: "Nuova fattura: [Fornitore] €[importo]"
- Se avvisi (IBAN mancante, totali incoerenti) → li aggiunge alla notifica
- Se fornitore nuovo → alert speciale

### Step 5 — Controlli finali
- Verifica coerenza totali (somma righe = totale documento) → se no: stato `anomala`
- Verifica IBAN se metodo = bonifico → se mancante: avviso giallo
- Aggiorna contatori: fatture del mese, IVA a credito, costi per centro di costo

---

## FLUSSO — ARRIVA UN CEDOLINO PDF

### Step 1 — Ingresso
- Upload manuale o download automatico Gmail (ogni 50 minuti)
- Rileva formato: CSC Napoli, Zucchetti classico, Zucchetti nuovo (sep. `s`), Teamsystem
- Parser estrae: nome, CF, mese/anno, tipo (mensile/tredicesima/quattordicesima/acconto), netto, lordo, IRPEF, INPS, progressivi annuali, quota TFR, ferie residue, permessi ROL, giustificativi

### Step 2 — Abbinamento dipendente
- Cerca in `dipendenti` per codice fiscale → poi per nome
- Se non trovato → segnalazione "Cedolino non abbinato"
- Evento: `cedolino.importato`

### Step 3 — Handler
- **Salvataggio**: upsert in `cedolini` per `dipendente_id + mese + anno`
- **Progressivi**: INPS e IRPEF con logica MAX (valore più alto vince)
- **TFR**: accantonamento in `tfr_accantonamenti` (no duplicati)
- **Ferie**: aggiorna saldi `ferie_residue` e `permessi_rol` solo se cedolino più recente
- **Prima Nota Salari**: scrive in `prima_nota_salari` (automatico, senza conferma)
- **Riconciliazione anticipata**: cerca in estratto conto un bonifico con importo = netto ±2€

---

## FLUSSO — ARRIVA UN'EMAIL (ogni 50 minuti)

### Step 1 — Connessione e filtro
- Connessione IMAP a Gmail in thread separato
- Controlla se mittente è in `mittenti_email` con `attivo: true`
- Se NON in whitelist → skip silenzioso

### Step 2 — Classificazione e download
- Scarica allegati (PDF, XML, P7M)
- Hash MD5 → controlla duplicati in `documents_inbox`
- Se nuovo → salva: filename, hash, tipo_documento, mittente, subject, data, pdf base64

### Step 3 — Routing per tipo

| tipo_documento | Azione |
|---|---|
| `fattura_xml` | Lancia Flusso Fattura XML completo |
| `cedolino` | Salva PDF, lancia Flusso Cedolino |
| `inps` | OCR → DURC/delibere FONSI/comunicazioni |
| `inail` | OCR → autoliquidazione/infortuni |
| `cartella_esattoriale` | FiscaleSentinella analizza → alert urgente |
| `pagopa` | Estrae codice CBILL → cerca in estratto conto |
| `paypal` | Estrae movimenti → matching fatture PayPal |
| `generico` (noleggio) | Cerca targa → abbina al verbale noleggio |
| `generico` (banca) | Se estratto conto → avvia parsing BNL/Nexi |

---

## FLUSSO — ARRIVA UN ESTRATTO CONTO BANCARIO

### Step 1 — Parsing
- Parser BNL: conto corrente o carta Business
- Parser Nexi: movimenti POS
- Estrae: data operazione, data valuta, descrizione, importo, causale ABI
- Anti-duplicato: hash contenuto file

### Step 2 — Matching automatico (per confidenza decrescente)

1. **F24**: movimenti con "F24", "TRIBUTI" nella descrizione → abbina all'F24 per data+importo
2. **Stipendi**: uscite con importo = netto cedolino ±2€ → abbina al cedolino
3. **Fatture fornitori**: uscite con importo ±2% e fornitore nella descrizione → abbinamento automatico se confidenza >85%
4. **POS/Corrispettivi**: accrediti "NEXI", "POS" → abbina ai corrispettivi del giorno ±1€
5. **Canoni noleggio**: uscite con nomi società noleggio → abbina alle rate contratti

### Step 3 — Scrittura Prima Nota
- Ogni movimento abbinato genera la riga in Prima Nota Banca
- Aggiorna fattura: `pagata: true`, `data_pagamento`
- Aggiorna scadenziario: scadenza → `saldata`

---

## COLLECTION MONGODB — Chi scrive cosa

| Collection | Chi scrive | Chi legge |
|---|---|---|
| `invoices` | import_xml, aruba_automation | Fatture, Riconciliazione, Contabilità |
| `dettaglio_righe_fatture` | import_xml | Fattura dettaglio, Magazzino |
| `suppliers` | import_xml (crea), Fornitori (modifica) | Fatture, Magazzino, Learning |
| `scadenziario_fornitori` | handler_scadenziario | Scadenze, Riconciliazione |
| `warehouse_movements` | handler_magazzino | Magazzino, Ricette |
| `warehouse_inventory` | handler_magazzino | Magazzino giacenze |
| `lotti` | handler_lotti | Tracciabilità, HACCP |
| `prima_nota_banca` | handler_prima_nota, estratto_conto | Prima Nota Banca |
| `prima_nota_cassa` | handler_prima_nota, corrispettivi | Prima Nota Cassa |
| `prima_nota_salari` | handler_prima_nota_salari | Prima Nota Salari |
| `cedolini` | handler_salva_cedolino | Cedolini, HR |
| `dipendenti` | handler_progressivi, handler_ferie, handler_tfr | HR |
| `tfr_accantonamenti` | handler_tfr | TFR |
| `agenti_segnalazioni` | tutti gli agenti | Dashboard |
| `eventi_sistema` | Bus eventi | Event Bus processor |
| `eventi_log` | Bus eventi | Debug |
| `learning_rules` | Learning Machine | Classificazione |

---

## PIANO DI COSTRUZIONE (priorità)

### Fase 1 — Solidificare il nucleo (senza inventare nulla di nuovo)
1. Scrivere l'Event Bus come file unico `app/core/event_bus.py` ← già presente
2. Spostare ogni handler esistente in `app/handlers/` ← già presente
3. Registrarli nell'Event Bus
4. Testare ogni flusso end-to-end

### Fase 2 — Completare i flussi mancanti
5. Prima Nota automatica al pagamento confermato
6. TFR automatico da cedolino
7. Aggiornamento ricette al cambio prezzo ingrediente

### Fase 3 — Intelligenza interna
8. LearningCervello 2.0: trend prezzi, alert margini
9. Anticipatore: previsioni liquidità 30 giorni
10. HR: costo reale per dipendente, ferie in scadenza

---

*Aggiornato: Aprile 2026*

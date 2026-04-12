# Flussi Operativi — Ceraldi ERP
> Aggiornato: Aprile 2026

---

> **Nota sulla direzione dei dati:**
> Il gestionale è il sistema centrale. I dati vanno **dal gestionale verso ceraldiapp.it**, mai il contrario.
> ceraldiapp.it chiede dati via API quando ne ha bisogno (fornitori, fatture, listini).
> Eccezione: il ponte ERP. Quando ceraldiapp importa una fattura dalla PEC, notifica il gestionale
> che la upserta in `invoices` — ma è sempre il gestionale a decidere cosa fare.

---

## 1. ARRIVA UNA FATTURA XML

### Da dove entra
- **Import manuale**: pagina Documenti → Import (file .xml singolo, multipli, o .zip)
- **Automaticamente ogni ora**: scheduler che controlla la PEC Aruba (INBOX + INBOX.lette, file .xml e .p7m)
- **Notifica ponte**: da ceraldiapp.it quando ha importato una fattura da PEC HACCP

### Passo per passo

**Passo 1 — Parsing**
Il sistema legge il file XML (supporta UTF-8, latin-1, iso-8859-1, cp1252) e ne estrae:
- P.IVA fornitore, ragione sociale, numero fattura, data
- Tipo documento (TD01 fattura, TD04 nota credito, TD08/TD24/TD25 altre)
- Righe: descrizione, quantità, prezzo unitario, IVA, importo
- Totale imponibile, IVA, totale documento
- Metodo pagamento (MP01–MP19), data scadenza
- Allegati PDF incorporati nell'XML

**Passo 2 — Controllo duplicati**
- Stesso numero fattura + stessa P.IVA → skip o aggiornamento
- Se esiste come "bozza da email" → elimina e reimporta pulita
- Se esiste come XML definitivo → aggiorna solo il raw XML, non tocca nient'altro

**Passo 3 — Fornitore**
- Cerca il fornitore per P.IVA in `suppliers`
- Se non esiste → lo crea con i dati dell'XML (ragione sociale, P.IVA, indirizzo)
- Se esiste → recupera metodo di pagamento predefinito e IBAN

**Passo 4 — Nota di credito (TD04/TD08)**
- Cerca la fattura originale per numero riferimento + P.IVA fornitore
- Aggiorna la fattura originale: `ha_nota_credito: true`, `importo_stornato`, `importo_residuo`
- Aggiorna la scadenza originale: riduce l'importo

**Passo 5 — Scadenziario**
- Legge la modalità e data di scadenza dall'XML
- Se data esplicita → usa quella
- Altrimenti: `data_fattura + gg_pagamento` del fornitore (da anagrafica)
- Crea scadenza in `scadenziario_fornitori` con stato `aperta`

**Passo 6 — Prima Nota Banca (se metodo = bonifico)**
- Prepara il movimento ma lo segna `prima_nota_pronta: true`
- Viene scritto definitivamente solo quando l'estratto conto conferma il pagamento

---

## 2. PRIMA NOTA CASSA

**Dati in ingresso:**
1. File XML corrispettivi dal Registratore Telematico (incassi giornalieri)
2. Inserimenti manuali (piccole spese)

**Logica:**
- DARE = Ricavi Lordi (PagatoContanti + PagatoElettronico)
- AVERE = PagatoElettronico (POS) → denaro che uscirà verso banca
- **SALDO CASSA = DARE − AVERE = solo contante fisico**

**Popola:** Bilancio (Ricavi), Conto Economico, Coerenza POS

**Chiusura:** Riconciliazione con estratto conto → accredito POS in banca coincide con POS XML

**API:**
```
GET  /api/prima-nota/cassa?anno=2026
POST /api/prima-nota/cassa/sync-corrispettivi?anno=2026
POST /api/prima-nota/cassa/sync-fatture-pagate?anno=2026
```

---

## 3. PRIMA NOTA BANCA

**Dati in ingresso:**
1. Import CSV estratto conto BPM (separatore `;`, UTF-8-BOM)
2. Riconciliazione automatica con fatture / F24 / stipendi
3. Inserimenti manuali

**Logica:**
- Ogni riga = movimento bancario: data, causale, importo, segno
- Saldo progressivo giornaliero

**Popola:** Bilancio (Disponibilità Liquide), Riconciliazione Fornitori, Dashboard saldo banca

**Chiusura:** Tutti i movimenti riconciliati con documenti → mese "chiuso contabilmente"

**API:**
```
GET  /api/prima-nota/banca?anno=2026
GET  /api/estratto-conto-movimenti/movimenti?anno=2026
POST /api/bank/import-estratto-conto
```

---

## 4. CORRISPETTIVI RT (Cassa)

**Dati in ingresso:** File XML dal Registratore Telematico (trasmesso all'AdE ogni giorno)

**Logica:**
- Dettaglio giornaliero per aliquota IVA
- Estrae PagatoContanti e PagatoElettronico
- Calcola IVA a debito trimestrale

**Popola:** Prima Nota Cassa, Fisco/IVA, Bilancio (Volume d'Affari)

> **REGOLA**: I corrispettivi sono l'UNICA fonte di ricavi.
> `Volume d'Affari = SUM(corrispettivi.totale_giornata) per anno`

---

## 5. FATTURE RICEVUTE (Ciclo Passivo SDI)

**Dati in ingresso:**
- File XML FatturaPA da Aruba PEC (`fatturazioneceraldi@pec.it`)
- Allegati `.xml` o `.p7m`

**Logica:**
1. Parsing XML → fornitore, data, imponibile, IVA, totale, scadenza
2. Abbinamento/creazione fornitore in `suppliers`
3. Classificazione automatica categoria spesa
4. Se metodo = SEPA/Bonifico → movimento atteso in prima_nota_banca

**Popola:** Fornitori (storico), Scadenzario, Prima Nota Banca (uscita attesa), IVA a credito

**Chiusura:** Fattura = "Da pagare" → uscita bancaria riconciliata → "Pagata"

---

## 6. PRIMA NOTA SALARI

**Dati in ingresso:** PDF Cedolini (libro unico Zucchetti) + import Gmail

**Logica:**
- Registra costo totale personale mensile
- Separa: netto da pagare, INPS/INAIL, quota TFR

**Popola:** Bilancio (Costo Lavoro), F24 Contributi, Prima Nota Banca (bonifici stipendi)

**Chiusura:** Estratto conto conferma bonifici stipendi + F24 contributi versato entro il 16

---

## 7. CEDOLINI E PAGHE

**Import da Gmail:**
```
POST /api/cedolini/import-gmail?since_days=180
```
- Cerca "cedolino", "busta paga", "libro unico" in Gmail
- Scarica PDF in `asyncio.to_thread()` — NON blocca il server
- 271 cedolini Gmail già presenti (storico completo)
- Parsing filename: `"Busta paga - Nome - Aprile 2026.pdf"` → `mese=4, anno=2026`

**Collections:**
- `cedolini` (1.658): principale — tutte le fonti
- `cedolini_importati` (2.363): sistema Zucchetti cloud

---

## 8. FISCO E IVA

**Liquidazione IVA:**
```
IVA a debito  = SUM(corrispettivi.totale_iva) per periodo
IVA a credito = SUM(invoices.iva_detraibile) per periodo
Liquidazione  = IVA a debito − IVA a credito   [trimestrale]
```
- Se positiva → versamento tramite F24 (codice tributo 6001)
- Se negativa → credito da riportare

**Calendario F24 (16 di ogni mese):**
- IRPEF ritenute dipendenti
- Contributi INPS/INAIL
- Addizionali regionali/comunali

**Collections:** `f24_unificato` (68 record), `scadenze` (15 record)

---

## 9. FORNITORI

**API principali:**
```
GET  /api/suppliers?page=1&limit=50       → lista fornitori
GET  /api/suppliers/{id}                  → dettaglio
GET  /api/fatture-ricevute/archivio       → storico fatture
GET  /api/scadenziario/fornitori          → scadenze aperte
```

---

## 10. RICONCILIAZIONE BANCARIA

**Tipi di riconciliazione:**

| Tipo | Criteri Match |
|---|---|
| Stipendi | IBAN + importo esatto + data ±5gg |
| F24 | Importo + data 16 ±3gg + "F24"/"ERARIO" in descrizione |
| Rate Mutuo | Importo ±€1 + data ±7gg |
| POS | Importo ±€5 + data attesa accredito (+1/+3gg lavorativi) |
| Fatture | Importo ±2% + fornitore nella descrizione |

**Algoritmo POS:**
- Lunedì–Giovedì → accredito il giorno lavorativo successivo
- Venerdì–Domenica → accredito il lunedì successivo

---

## 11. CESPITI E AMMORTAMENTI

**Collection:** `cespiti` (21 record)

**API:** `POST /api/cespiti/scan-fatture` — legge righe fatture XML e identifica beni strumentali

**Popolato da:** fatture acquisto beni strumentali (valore > soglia ammortamento)

---

## 12. SCADENZARIO

**Scadenze automatiche create da:**
- Fatture ricevute non pagate
- Modelli F24 caricati
- Rate mutui
- Stipendi mensili

**Alert:**
- Entro 7 giorni → ROSSO (critico)
- 8–30 giorni → GIALLO (attenzione)
- Oltre 30 giorni → VERDE (pianificazione)

---

## 13. MAGAZZINO

**Flusso Carico (da Fattura XML):**
1. Import Fattura → legge righe fattura
2. Classificazione per pattern matching su descrizione/fornitore
3. Aggiornamento stock con prezzo medio ponderato
4. Tracciabilità movimento

**Flusso Scarico (Distinta Base):**
1. Selezione Ricetta + Porzioni da produrre
2. Calcolo ingredienti proporzionale
3. Verifica disponibilità giacenze
4. Scarico con lotto `LOTTO-YYYYMMDDHHMMSS`

**API:** `/api/magazzino/giacenze`, `/api/magazzino/carico-da-fattura/{id}`

---

## 14. IMPORT DOCUMENTI — Gateway Ingresso Dati

| Tipo File | Destinazione | Parser |
|---|---|---|
| XML corrispettivi | `prima_nota_cassa` | `corrispettivi_parser` |
| XML FatturaPA SDI | `invoices` | `xml_invoice_processor` |
| CSV BPM | `estratto_conto_movimenti` | `bank_statement_parser` |
| PDF Libro Unico | `cedolini` + `presenze_mensili` | `libro_unico_parser` |
| PDF F24 | `f24_unificato` | `f24_parser` |
| PDF Piano Ammortamento | `mutui` | `mutui_parser` |

---

*Aggiornato: Aprile 2026*

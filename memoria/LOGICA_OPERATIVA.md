# Ceraldi ERP — Logica operativa

Come funziona il gestionale pagina per pagina, dato per dato.
Ceraldi Group S.R.L. — aggiornato Apr 2026.

---

## 1. Ciclo dei dati — da dove arrivano e dove finiscono

### 1.1 Fonti automatiche

Il gestionale riceve dati da tre fonti:

| Fonte                                      | Cosa arriva                               | Frequenza      | Collection destinazione                 |
|--------------------------------------------|-------------------------------------------|----------------|-----------------------------------------|
| PEC Aruba (`fatturazioneceraldi@pec.it`)   | Fatture XML/P7M dal Sistema di Interscambio | 1 volta l'ora  | `invoices` (pagina Fatture)             |
| Gmail (`ceraldigroupsrl@gmail.com`)        | Cedolini, F24, verbali, quietanze, cartelle | ogni 10 min    | `documents_inbox`, poi smistati         |
| Import manuale                             | Corrispettivi XML, estratto conto CSV, PDF | on demand      | Varie collection                        |

### 1.2 Mittenti autorizzati

Vedi tabella completa in `INDEX.md`. Solo i 14 mittenti in whitelist vengono processati; gli altri finiscono nel cestino o in quarantena.

---

## 2. Pagina per pagina

### Dashboard — `/`

Riepilogo istantaneo dell'azienda per l'anno selezionato.

Legge da:
- `corrispettivi` — ricavi (volume d'affari)
- `invoices` — costi (fatture passive)
- `scadenziario_fornitori` — prossime scadenze
- `f24_unificato` — scadenze fiscali

Calcola:
- Bilancio istantaneo: Ricavi − Costi = Utile lordo
- Saldo IVA: IVA a debito (corrispettivi) − IVA a credito (fatture)
- Prossime scadenze con conteggio giorni residui

Alert:
- F24 in scadenza (rosso se meno di 5 giorni)
- Fatture da pagare con importo e fornitore
- Banner commercialista se ci sono dati da inviare

Relazioni: legge da quasi tutte le collection principali, non scrive nulla.

---

### Fatture — `/fatture`

Tutte le fatture passive ricevute dai fornitori (1.405 record).

Flusso di ingresso:
1. La PEC scarica l'email con allegati XML/P7M
2. Il parser XML estrae fornitore, P.IVA, numero, data, imponibile, IVA, totale, righe dettaglio
3. Estrae anche `DatiFattureCollegate` (per le note credito), causali, `tipo_documento` (TD01 / TD04)
4. Cerca il fornitore in `fornitori` per P.IVA; se non c'è lo crea
5. Prende il metodo pagamento DAL FORNITORE (mai dall'XML)
6. Se il metodo è "contanti" → auto-registra in `prima_nota_cassa` + stato pagata
7. Se il metodo è "bonifico" → auto-registra in `prima_nota_banca` + stato pagata
8. Se il metodo è "sospesa" / "misto" / nuovo fornitore → resta in provvisori

Azioni per riga:
- Vedi — apre il dettaglio XML
- ✓ Cassa (verde) — confermata in contanti, visibile se il fornitore paga contanti
- ✓ Banca (verde) — confermata con bonifico
- Cassa / Banca (grigio) — da confermare manualmente

Collection popolate: `invoices`, `fornitori`, `prima_nota_cassa` o `prima_nota_banca`, `warehouse_stocks` (se catalogo attivo).

Note credito (TD04):
- Importo mostrato con segno negativo
- Badge rosso "Nota Credito"
- Nel modal Collega Fatture dell'area Assegni si scalano dall'importo dell'assegno

---

### Prima Nota — `/prima-nota`

Tre sezioni: Cassa, Banca, Provvisori.

Cassa:
- Entrate = corrispettivi giornalieri (totale incassato, contanti + POS)
- Uscite POS → Banca = la parte elettronica del corrispettivo che va in banca
- Uscite Fatture = fatture pagate in contanti
- Uscite Versamenti = contanti portati fisicamente in banca
- Saldo Cassa = Entrate − Uscite POS − Fatture contanti − Versamenti banca

Banca:
- Movimenti dall'estratto conto BPM (8.839 record)
- Pagamenti fatture bonifico
- Stipendi dipendenti
- F24 Agenzia Entrate
- Accrediti POS (dall'incasso giorno precedente)
- Rate mutuo, SDD, commissioni

Provvisori:
- Fatture importate ma senza conferma
- Se il fornitore ha metodo definito non appaiono qui (auto-confermate)
- Bottone Sospesa: la fattura resta in provvisori, non crea movimento, si può confermare dopo

---

### Fornitori — `/fornitori`

Anagrafica completa (245 record).

Per ogni card mostriamo:
- Nome, P.IVA, indirizzo
- Numero fatture dell'anno corrente
- Metodo pagamento (Contanti / Bonifico / Assegno / Misto)
- Giorni medi di pagamento

Il metodo di pagamento è fondamentale:
- Determina dove finisce la fattura (cassa o banca)
- Non viene mai dall'XML
- Ogni cambio salva la data (storico)

Azioni: Fatture (estratto), Modifica anagrafica, Cerca P.IVA (OpenAPI Camera di Commercio), Schede tecniche.

---

### HR — Dipendenti — `/dipendenti`

30 dipendenti con dettaglio per ciascuno.

Tab per dipendente:
- Anagrafica (nome, cognome, CF, IBAN, mansione, livello, data assunzione)
- Contratti (tipo, scadenza)
- Cedolini (buste paga)
- Verbali (verbali noleggio se è driver)
- Movimenti (bonifici stipendio trovati in banca)
- Giustificativi (ferie, permessi, malattia)

---

### Cedolini — `/cedolini`

301 buste paga, vista "Per Mese" oppure "Per Dipendente".

Ingresso:
1. Il consulente del lavoro invia il PDF "Libro Unico" via Gmail
2. Il parser Zucchetti estrae per ogni dipendente nome, CF, netto, TFR, ore

Campi chiave: `nome_dipendente`, `codice_fiscale`, `netto`, `netto_mese`, `tfr_mese`.

Bottoni:
- Importa da Gmail — scarica nuovi cedolini
- Importa PDF Libro Unico — upload manuale del PDF presenze

---

### Presenze — `/presenze`

Calendario giornaliero per dipendente (290 record).

Per ogni giorno: ore ordinarie e giustificativi (FE = ferie, AI = assenza, RL = ROL, MA = malattia).
Ogni codice ha un colore. Dati popolati dai cedolini (totali mensili) o da import manuale del PDF Libro Unico.

---

### Noleggio auto — `/noleggio`

Tre tab: Flotta, Verbali, Riepilogo costi.

Flotta (4 veicoli):

| Targa    | Veicolo              | Fornitore | Driver              |
|----------|----------------------|-----------|---------------------|
| HB411GV  | BMW X3               | Leasys    | Vincenzo Ceraldi    |
| GW980EP  | Mazda                | ARVAL     | Antonietta Ceraldi  |
| GX037HJ  | BMW X1               | ALD       | Valerio Ceraldi     |
| GG782PN  | Alfa Romeo Stelvio   | Leasys    | Vincenzo Ceraldi    |

Verbali (165 attivi):
- Scaricati dalla PEC
- Targa estratta dal PDF con PyMuPDF
- Solo targhe aziendali (quelle non aziendali sono archiviate)
- Driver associato per targa → veicolo → driver

Azioni: Scan Fatture Noleggiatori, Associa Driver, Riconcilia con pagamenti bancari.

---

### Magazzino — `/magazzino`

496 prodotti con giacenze, prezzi, fornitori.

Legge da `warehouse_stocks` (NON `warehouse_inventory`).

Tab: Giacenze · Inventario · Ricerca prodotti · Dizionario articoli · Coerenza POS.

---

### Riconciliazione — `/riconciliazione`

Confronta movimenti bancari con fatture, stipendi, F24 per trovare le corrispondenze.

Tab: Banca · Assegni · F24 · Fatture Aruba · Stipendi · Documenti · PayPal.

---

### Assegni — `/riconciliazione/assegni`

220 assegni raggruppati per carnet.

Modal "Collega Fatture":
- Fatture ordinate per fornitore (header sticky)
- Note credito con importo negativo (badge rosso)
- Massimo 4 fatture per assegno
- Solo fatture dello stesso fornitore

Regola: l'auto-associazione collega assegni SOLO a fatture di fornitori con metodo di pagamento "assegno".

---

### Contabilità — `/contabilita`

Tab principali:
Piano dei Conti · Bilancio · Verifica Bilancio · Controllo Mensile · Calendario Fiscale · Cespiti · Finanziaria · Chiusura Esercizio · Budget · Mutui · Contab. Avanzata.

---

### Strumenti — `/strumenti`

Tab: Verifica Coerenza · Commercialista · Pianificazione · Visure.

Verifica Coerenza confronta in automatico:
- IVA mensile (debito vs credito)
- Versamenti cassa vs banca
- Prima Nota vs Estratto Conto
- Bonifici vs movimenti bancari

Commercialista genera PDF pronti da inviare:
- Prima Nota Cassa su due colonne (Entrate verde / Uscite rosso)
- Fatture pagate in contanti
- Carnet assegni selezionati

---

### Documenti — `/documenti`

Tab: Archivio · Import Documenti.

Archivio: documenti raggruppati per mittente (consulente lavoro, Comune, commercialista, INPS, Agenzia Entrate, assicurazione).

Import Documenti: upload manuale di XML fatture, CSV estratto conto, PDF cedolini, XML corrispettivi.

---

### Admin — `/admin`

Tab: Email · Parole Chiave · Fatture · Sistema.

Email: configurazione Gmail e PEC Aruba, test connessione.
Parole Chiave: filtri per categorizzazione automatica (F24, cedolino, busta paga, ecc).

---

## 3. Flusso completo: da email a Prima Nota

```
1. Email arriva (PEC o Gmail)
   ↓
2. Scheduler la scarica (PEC ogni ora, Gmail ogni 10 min)
   ↓
3. Verifica mittente nella whitelist (14 mittenti)
   ↓
4. Se mittente SDI (@pec.fatturapa.it):
     → parser XML fattura
     → cerca fornitore per P.IVA (o crea)
     → prende metodo pagamento DAL FORNITORE
     → contanti  → scrive in prima_nota_cassa, stato=pagata
     → bonifico  → scrive in prima_nota_banca, stato=pagata
     → sospesa   → resta in provvisori
     → aggiorna contatore fatture fornitore
     → aggiorna giacenze magazzino (se attivo)
   ↓
5. Se mittente cedolino (Ferrantini / Marotta):
     → salva PDF in documents_inbox
     → disponibile per import manuale
   ↓
6. Se mittente cartella / INPS / INAIL:
     → salva in documenti_non_associati
     → genera alert se urgente
   ↓
7. La Dashboard si aggiorna automaticamente
     → eventuale nuova scadenza
     → bilancio ricalcolato
     → volume affari invariato (solo corrispettivi)
```

---

## 4. Relazioni tra dati (riassunto)

```
fornitori.partita_iva            ←→ invoices.supplier_vat
fornitori.metodo_pagamento       →  determina prima_nota_cassa o banca
invoices.id                      →  prima_nota_cassa.fattura_id / prima_nota_banca.fattura_id
invoices.tipo_documento=TD04     →  nota credito (importo negativo)
corrispettivi.data               →  prima_nota_cassa (entrata=totale, uscita=POS)
estratto_conto_movimenti         →  prima_nota_cassa (VERS. CONTANTI come uscita versamento)
dipendenti.codice_fiscale        ←→ cedolini.codice_fiscale ←→ presenze.codice_fiscale
veicoli_noleggio.targa           ←→ verbali_noleggio.targa   →  veicoli_noleggio.driver
assegni.fornitore_piva           ←→ invoices.supplier_vat     (solo metodo = assegno)
```

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

---

#### 🎯 Logica N↔M: assegni ↔ fatture

Un **assegno** e una **fattura** hanno una relazione **molti-a-molti**: lo stesso assegno può pagare più fatture, e la stessa fattura può essere pagata con più assegni. Il collante è il **fornitore**: gli assegni collegati a una fattura devono SEMPRE essere dello stesso fornitore della fattura.

La struttura logica è:

```
assegno ─┐              ┌─► fattura
         ├── collegamento ──► quota (€)
assegno ─┘              └─► fattura
```

Ogni collegamento ha una **quota** in euro: la parte di importo dell'assegno che paga quella fattura. Un assegno può avere più quote (una per fattura), una fattura può ricevere più quote (una per ogni assegno).

**Regola d'oro**:
```
importo_assegno = somma delle quote assegnate alle sue fatture
importo_pagato_fattura = somma delle quote ricevute dai suoi assegni
fattura.saldata  ⇔  importo_pagato_fattura == importo_fattura
```

---

#### Caso A — 1 assegno = 1 fattura (tipico)

Banca scrive assegno nº 1234 di €500,00 al fornitore X.
Il fornitore X ha fattura FT001 aperta di €500,00.
Collego l'assegno alla fattura → quota €500,00.
- fattura FT001: pagata (saldata al 100%)
- assegno 1234: pienamente assegnato (quota = importo)

#### Caso B — 1 assegno paga 2+ fatture stesso fornitore

Banca scrive assegno nº 1235 di €1.500,00 al fornitore Y.
Il fornitore Y ha 3 fatture aperte: FT010 €600, FT011 €900, FT012 €300.
Collego l'assegno a FT010 + FT011 → quote €600 + €900 = €1.500.
- FT010: pagata
- FT011: pagata
- FT012: resta aperta
- assegno 1235: pienamente assegnato

**Vincolo**: tutte le fatture collegate a uno stesso assegno devono appartenere allo stesso fornitore. Massimo 4 fatture per assegno (regola operativa).

#### Caso C — Fattura grande pagata da 2+ assegni (pagamento rateale)

Fornitore Z emette fattura FT050 di €5.000 al mese. Si paga con 3 assegni:
- assegno 2001 €1.800 → quota su FT050 = €1.800
- assegno 2002 €1.700 → quota su FT050 = €1.700
- assegno 2003 €1.500 → quota su FT050 = €1.500

Totale quote su FT050 = €5.000 → fattura saldata.

**Stato della fattura**:
- Prima del primo assegno:  `aperta`
- Dopo assegno 2001:        `parzialmente_pagata`  (importo_pagato = 1.800)
- Dopo assegno 2002:        `parzialmente_pagata`  (importo_pagato = 3.500)
- Dopo assegno 2003:        `pagata`               (importo_pagato = 5.000)

#### Caso D — Mix dei due (raro ma gestito)

Assegno 3000 €2.000 paga:
- FT070 (€1.200) interamente → quota 1.200
- FT071 (€4.000, rateale) per la prima tranche → quota 800

Totale quote = 2.000. L'assegno è chiuso, FT070 è saldata, FT071 resta aperta con €3.200 residui.

#### Caso E — Nota credito (TD04)

Il fornitore emette una NC di €300 che scala dall'importo dell'assegno dovuto.
Nel modal "Collega Fatture" la NC appare con **importo negativo** e badge rosso:
- assegno €1.000
- fattura FT100 €1.200
- NC FT100-NC €-200 (stessa fattura o del fornitore)
- Quota netta su FT100 = 1.200 − 200 = 1.000 → l'assegno copre la fattura

---

#### 📋 Dati coinvolti

Collezione `assegni`:
```
id, numero, importo, data_emissione, data_addebito,
fornitore_piva, fornitore_ragione_sociale,
carnet_id, carnet_sequenza,
fatture_collegate: [
  { fattura_id, quota, data_collegamento }
],
importo_assegnato   (somma quote — deve == importo)
stato               (emesso | parzialmente_assegnato | assegnato | addebitato | annullato)
riconciliato_banca  (true se incrociato con estratto conto)
movimento_banca_id  (riferimento al record nell'estratto conto)
```

Collezione `invoices` / `fatture_passive`:
```
id, importo_totale, fornitore_piva,
importo_pagato      (somma delle quote ricevute)
importo_residuo     (importo_totale − importo_pagato − eventuali NC)
stato_pagamento     (aperta | parzialmente_pagata | pagata)
assegni_collegati: [
  { assegno_id, numero, quota }
]
```

---

#### 🔗 Riconciliazione con estratto conto

Quando l'assegno "esce" dal conto corrente (banca addebita):
1. Arriva un movimento in `estratto_conto_movimenti` con causale "Assegno n. XXXX" e importo
2. Il sistema cerca nel registro `assegni` un assegno con (numero, importo) match
3. Se trovato: `assegno.riconciliato_banca = true`, `data_addebito = data_movimento`, `movimento_banca_id = id`
4. Se la somma delle quote copre tutte le fatture collegate, le fatture diventano definitivamente pagate

Se arriva un addebito assegno ma nessun assegno nel registro corrisponde → alert "Assegno non registrato" nella pagina Strumenti → Verifica Coerenza.

---

#### ✅ Validazioni a livello di UI

Quando l'utente collega fatture a un assegno:

- Deve selezionare fatture **dello stesso fornitore** dell'assegno (altre filtrate via)
- Massimo 4 fatture per assegno
- La somma delle quote NON può superare `importo_assegno`
- Se la somma delle quote è `< importo_assegno` → assegno `parzialmente_assegnato` (residuo va su altre fatture future dello stesso fornitore)
- Se la somma delle quote `== importo_assegno` → assegno `assegnato`
- Se l'assegno paga per intero la fattura → `fattura.stato = pagata`, crea in automatico un movimento in `prima_nota_banca` con tipo "uscita_assegno"
- Se l'assegno paga solo una parte → `fattura.stato = parzialmente_pagata`, il movimento in prima nota è comunque creato ma con importo = quota

---

#### 🔍 Pagina Assegni — tab

1. **Tutti** — lista assegni raggruppati per carnet, badge stato (emesso / assegnato / addebitato)
2. **Da collegare** — assegni senza fatture (da processare)
3. **Parzialmente assegnati** — assegni con quota residua da allocare
4. **Addebitati ma non riconciliati** — movimenti banca che citano "assegno" senza assegno nel registro
5. **Fatture aperte del fornitore X** — quando clicchi un assegno, mostra solo le fatture aperte dello stesso fornitore

---

#### 🤖 Auto-matching intelligente (assegni ↔ fatture)

Quando arrivano assegni nuovi senza collegamenti, il sistema prova automaticamente ad associarli a fatture aperte del medesimo fornitore con queste strategie, in ordine di priorità.

**Livello 1 — Match secco (1 assegno = 1 fattura)**

Per ogni assegno non collegato:
- cerca nelle fatture aperte del fornitore una con `importo == assegno.importo` (tolleranza ±0,05 €)
- se trova UNA sola corrispondenza → match automatico, quota = importo fattura
- se trova PIÙ corrispondenze → non auto-matcha, segnala "Match ambiguo — conferma manuale"

Esempio: assegno €500 ↔ fattura €500 → match secco.

**Livello 2 — Match di gruppo (N assegni uguali = 1 fattura divisa in parti uguali)**

Raggruppa assegni dello stesso fornitore per importo (tolleranza ±0,05 €). Se trova un gruppo di N ≥ 2 assegni simili:
- calcola somma = N × importo_medio
- cerca fatture aperte del fornitore con `importo == somma` (tolleranza ±N × 0,05 € per assorbire gli arrotondamenti di divisione)
- se trova una sola fattura → match: ogni assegno diventa acconto rateale della stessa fattura

Esempio reale:
- 3 assegni da €1.663,26 / €1.663,26 / €1.663,28 per EG TAPPEZZERIA
- Somma = €4.989,80
- Fattura EG TAPPEZZERIA nr.1 del 24/01/2025 importo €4.989,80
- Verifica: 4.989,80 ÷ 3 = 1.663,267 → arrotondabile alle tre quote viste
- Match: i 3 assegni vengono collegati come acconti della fattura, ciascuno con quota pari al proprio importo

La tolleranza cumulativa (0,05 € × N) copre il caso in cui l'emittente arrotondi diversamente ciascuna rata.

**Livello 3 — Match di somma (N assegni di importi diversi = 1 fattura)**

Se nel carnet ci sono N assegni (2 ≤ N ≤ 4) dello stesso fornitore di importi diversi emessi in un intervallo ragionevole (es. 60 giorni), calcola tutte le combinazioni possibili:
- per ogni sottoinsieme di 2-4 assegni, calcola la somma
- cerca fatture aperte del fornitore con `importo == somma` (tolleranza ±0,10 €)
- se trova un solo abbinamento → match

Esempio: assegni €1.800 + €1.700 + €1.500 = €5.000 ↔ fattura €5.000 → match rateale.

**Livello 4 — Match inverso (1 assegno = N fatture dello stesso fornitore)**

Se l'assegno è maggiore della fattura più grande aperta del fornitore:
- calcola tutte le combinazioni di 2-4 fatture aperte del fornitore
- cerca quella con `somma == assegno.importo` (tolleranza ±0,05 €)
- se trova un solo abbinamento → match: l'assegno paga le N fatture

Esempio: assegno €1.500 ↔ fatture €600 + €900 → match bundle.

---

#### 📐 Tolleranze e arrotondamenti

- Match secco: ±0,05 € (singolo centesimo di divisione)
- Match N assegni uguali verso 1 fattura: ±(0,05 × N) €
- Match combinatorio (Livello 3 e 4): ±0,10 €
- Se la tolleranza assorbe il match ma lascia un **residuo > 0,01 €**, il residuo viene scritto come nota nel collegamento (`note: "arrotondamento pagamento rateale"`) e **non** crea fatture/assegni residui fittizi

---

#### 🚥 Ordine di esecuzione dell'auto-matcher

Lo scheduler lancia l'auto-matcher una volta all'ora oppure on-demand dal pulsante "🤖 Auto-collega" della pagina Assegni. Processa gli assegni in questo ordine:

1. **Livello 1** (match secco) su tutti gli assegni non collegati
2. **Livello 2** (N assegni uguali → 1 fattura) sui restanti
3. **Livello 3** (N assegni diversi → 1 fattura, 2 ≤ N ≤ 4) sui restanti
4. **Livello 4** (1 assegno → N fatture) sui restanti

Ad ogni livello, il matcher è **conservativo**: se trova più candidate valide, non decide da solo, segnala "Ambiguo" e lascia la scelta all'utente nella pagina Assegni (sezione "Da confermare").

---

#### 🔒 Regole di sicurezza del matcher

- **Stesso fornitore**: solo assegni e fatture con stessa P.IVA vengono valutati insieme
- **Niente cross-carnet per Livello 2**: gli N assegni "uguali" devono essere dello stesso carnet (stesso libretto) per considerarli rate dello stesso pagamento
- **Note credito**: se il fornitore ha NC aperte, il matcher le sottrae dal totale fattura prima di cercare il match (es. fattura €5.000 − NC €200 = target €4.800)
- **Assegni già addebitati in banca** hanno priorità: il matcher li processa per primi perché sono già usciti dal conto
- **Idempotente**: girando l'auto-matcher 10 volte di fila, il risultato non cambia (non crea doppioni)
- **Reversibile**: ogni match automatico è marcato `match_auto = true` e può essere rimosso con un click dalla pagina Assegni

---

#### 🎛️ Flusso utente con auto-matcher

```
1. Utente apre /riconciliazione/assegni
2. Click "🤖 Auto-collega"
3. Il matcher gira (~2-5 sec)
4. Mostra report:
   ├─ Livello 1: 42 assegni collegati (match secco)
   ├─ Livello 2: 8 collegati (N assegni uguali → 1 fattura rateale)
   ├─ Livello 3: 3 collegati (combinatorio)
   ├─ Livello 4: 5 collegati (assegno multi-fattura)
   └─ 12 ambigui (conferma manuale)
5. Tab "Da confermare": 12 assegni con 2+ match possibili
6. Utente clicca "Conferma" o "Scegli altra" per ciascun ambiguo
7. Residui manuali: tab "Da collegare" per assegni senza match
```

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

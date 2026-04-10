# 🔄 Flussi Automatici — Ceraldi ERP
## Cosa succede esattamente quando entra un documento, si fa un'operazione, o arriva una email

---

> **Nota importante sulla direzione dei dati:**
> Il gestionale è il sistema centrale. I dati vanno **dal gestionale verso ceraldiapp.it**, mai il contrario.
> Quando ceraldiapp.it ha bisogno di dati (fornitori, fatture, listini), li chiede al gestionale via API.
> L'unica eccezione è il ponte ERP: quando ceraldiapp importa una fattura dalla PEC, notifica il gestionale
> che la upserta in `fatture_passive` — ma anche in quel caso è il gestionale a decidere cosa fare.

---

## 📄 1. ARRIVA UNA FATTURA XML

### Da dove entra
- **Import manuale** dalla pagina Documenti → Import (file .xml singolo, multipli, o .zip)
- **Automaticamente ogni ora** dallo scheduler che controlla la PEC Aruba (INBOX e INBOX.lette, file .xml e .p7m)
- **Notifica ponte** da ceraldiapp.it quando ha importato una fattura fornitore HACCP dalla sua PEC

### Cosa succede — passo per passo

**Passo 1 — Parsing**
Il sistema legge il file XML e ne estrae tutto: P.IVA fornitore, ragione sociale, numero fattura, data, righe con descrizione e importo, totale imponibile, IVA, tipo documento (TD01 fattura, TD04 nota credito, ecc.), eventuali allegati PDF incorporati.

**Passo 2 — Controllo duplicati**
Confronta numero fattura + P.IVA fornitore con quelle già presenti.
- Se esiste già come "bozza da email" → la cancella e la reimporta pulita
- Se esiste già come XML definitivo → aggiorna solo il raw XML, non tocca nient'altro
- Se è nuova → procede all'inserimento

**Passo 3 — Fornitore**
Cerca il fornitore per P.IVA nella collection `fornitori`.
- Se non esiste → lo crea automaticamente con i dati dell'XML (ragione sociale, P.IVA, indirizzo)
- Se esiste → recupera metodo di pagamento predefinito e IBAN configurati

**Passo 4 — Nota di credito (TD04/TD08)**
Se il documento è una nota di credito cerca la fattura originale (stesso numero di riferimento + stessa P.IVA) e la aggiorna: segna che ha una nota di credito, riduce l'importo residuo, aggiorna lo scadenziario diminuendo la rata da pagare.

**Passo 5 — Magazzino**
Se il fornitore non è contrassegnato come "escludi da magazzino", ogni riga della fattura diventa un carico in giacenza. Esempio: fattura da fornitore alimentare con 10 kg farina → la farina entra in giacenza.

**Passo 6 — Scadenziario**
Crea automaticamente una scadenza di pagamento nella collection `scadenziario_fornitori`, con data calcolata dal tipo di pagamento (30/60/90 giorni) e importo. Questo alimenta la pagina Scadenze.

**Passo 7 — Prima Nota** *(richiede conferma)*
La scrittura contabile viene preparata ma NON eseguita automaticamente — aspetta conferma per evitare errori. Quando l'utente conferma il pagamento:
- Se pagamento in **cassa/contanti** → scrive in `prima_nota_cassa` (tipo: uscita, categoria: Fornitori)
- Se pagamento in **banca/bonifico** → scrive in `prima_nota_banca` (tipo: uscita, categoria: Fornitori)

**Passo 8 — Avvisi**
- Fornitore senza metodo pagamento → avviso giallo
- Metodo bonifico ma IBAN mancante → avviso rosso
- Totali XML non coerenti (somma righe ≠ totale) → stato "anomala", richiede revisione

**Passo 9 — Notifica WebSocket**
Se la fattura è nuova, il sistema manda una notifica push in tempo reale all'interfaccia web (campanellina in alto a destra). L'utente vede subito "X nuove fatture importate" senza ricaricare la pagina.

### Dove la vedi dopo
| Sezione | Cosa trovi |
|---|---|
| **Fatture** | La fattura con righe, allegato PDF, stato riconciliazione |
| **Fornitori** | Fornitore creato o aggiornato, con storico fatture |
| **Magazzino → Giacenze** | Carico delle righe |
| **Scadenze** | Scadenza di pagamento con importo e data |
| **Prima Nota → Banca o Cassa** | Movimento (dopo conferma pagamento) |
| **Riconciliazione** | In attesa di abbinamento con estratto conto |
| **Contabilità → Controllo Mensile** | Totale costi del mese aggiornato |
| **Agenti AI** | Eventuale alert se la fattura ha anomalie |

---

## 💰 2. ARRIVA UN CEDOLINO PDF (BUSTA PAGA)

### Da dove entra
- **Upload manuale** dalla pagina Cedolini (PDF Zucchetti, anche batch di più dipendenti e mesi diversi)
- **Download automatico da Gmail** ogni 10 minuti: lo scheduler cerca email con parole chiave "cedolino", "busta paga", "libro unico", "paghe", "netto in busta" e scarica gli allegati PDF

### Cosa succede — passo per passo

**Passo 1 — Parser Zucchetti**
Il sistema legge il PDF e ne estrae: nome dipendente, mese, anno, netto in busta, imponibile IRPEF, contributi INPS, progressivi annuali INPS e IRPEF, giorni/ore lavorate, ferie e permessi residui, TFR accantonato del mese.

**Passo 2 — Abbinamento dipendente**
Cerca il dipendente nella collection `dipendenti` per nome o codice fiscale. Se non trova → segnala anomalia, non procede.

**Passo 3 — Salvataggio cedolino (upsert)**
Salva o sovrascrive il cedolino per quel dipendente + mese + anno. Non crea duplicati.

**Passo 4 — Paga base**
Aggiorna la paga base nel profilo dipendente **solo se** questo cedolino è più recente dell'ultimo già salvato. Non sovrascrive mai con dati più vecchi.

**Passo 5 — Progressivi annuali**
INPS e IRPEF progressivi vengono aggiornati con logica MAX: prende il valore più alto tra quello già salvato e quello del cedolino nuovo. Questo garantisce che non si perdano mai i progressivi più aggiornati, anche se i cedolini vengono caricati in ordine sparso.

**Passo 6 — TFR**
Aggiorna l'accantonamento TFR per anno, tenendo il dato del mese più recente. Il calcolo segue l'art. 2120 c.c.: quota annuale divisa per 13,5, rivalutata con 1,5% fisso + 75% dell'indice ISTAT.

**Passo 7 — Ferie e permessi**
Aggiorna i saldi ferie e permessi (ROL) nel profilo dipendente solo se questo cedolino è più recente di quello già salvato.

**Passo 8 — Prima Nota Salari**
Scrive automaticamente un movimento di uscita in `prima_nota_salari` con: importo netto, nome dipendente, codice fiscale, mese e anno di riferimento, categoria "Stipendi".

**Passo 9 — Riconciliazione stipendi**
Il sistema prepara l'abbinamento con il bonifico stipendio nell'estratto conto. Quando arriva il bonifico in banca, il sistema lo propone automaticamente come "questo bonifico è lo stipendio di [nome] per [mese]".

### Dove lo vedi dopo
| Sezione | Cosa trovi |
|---|---|
| **Cedolini** | Il cedolino con tutti i dati estratti |
| **Dipendenti** | Paga base aggiornata, ferie/permessi aggiornati |
| **Presenze** | Saldo ferie e permessi ROL |
| **TFR** | Accantonamento aggiornato per anno |
| **Prima Nota → Salari** | Movimento di uscita del mese |
| **Riconciliazione** | Proposta di abbinamento col bonifico in banca |
| **Contabilità → Bilancio** | Costo del personale aggiornato |

---

## 🏦 3. OPERAZIONI BANCARIE MANUALI

### 3a. Versamento dalla cassa alla banca
Quando prelevi i soldi dalla cassa e li versi in banca (tipico con i corrispettivi):

**Cosa scrive:**
- In `prima_nota_cassa` → **uscita** con tipo "VERSAMENTO_BANCA" (conto: Cassa → Banca)
- In `prima_nota_banca` → **entrata** con tipo "VERSAMENTO_ENTRATA" (conto: Banca ← Cassa)

**Dove lo vedi:** Prima Nota Cassa (uscita) + Prima Nota Banca (entrata) + Riconciliazione (per abbinare il versamento al movimento nel conto corrente)

---

### 3b. Prelevamento dalla banca (cassa o spese)
Quando prelevi contanti dal conto corrente:

**Cosa scrive:**
- In `prima_nota_banca` → **uscita** con tipo "PRELEVAMENTO"
- In `prima_nota_cassa` → **entrata** se i soldi vanno in cassa aziendale

**Dove lo vedi:** Prima Nota Banca (uscita) + Prima Nota Cassa (entrata eventuale)

---

### 3c. Finanziamento soci con bonifico bancario
Quando un socio fa un bonifico di finanziamento all'azienda:

**Cosa scrive:**
- In `prima_nota_banca` → **entrata** con categoria "Finanziamento soci", importo pieno, descrizione con nome socio
- In contabilità → passività (debito verso socio) — questa parte richiede registrazione manuale in Prima Nota con il conto corretto del Piano dei Conti (es. "Finanziamenti soci infruttiferi")

**Dove lo vedi:** Prima Nota Banca + Contabilità → Bilancio (passivo) + Scadenze (se il rimborso ha una data)

---

### 3d. Pagamento fornitore con bonifico bancario
Quando paghi una fattura fornitore:

**Cosa scrive:**
- Aggiorna la fattura → `pagato: true`, `data_pagamento: oggi`
- In `prima_nota_banca` → **uscita** con riferimento al numero fattura e al fornitore
- In `scadenziario_fornitori` → chiude la scadenza

**Dove lo vedi:** Fatture (pagata), Scadenze (chiusa), Prima Nota Banca (uscita), Riconciliazione (abbinato al movimento bancario)

---

### 3e. Pagamento in contanti/cassa
Stessa logica del bonifico ma scrive in `prima_nota_cassa` invece di `prima_nota_banca`.

---

## 📊 4. ARRIVANO I CORRISPETTIVI XML

### Da dove entrano
**Solo import manuale** dalla pagina Documenti → Import. L'XML viene esportato dal registratore telematico dell'esercizio commerciale e caricato a mano. Non arriva mai da Gmail o da ceraldiapp.

### Cosa succede — passo per passo

**Passo 1** — Parsing: legge data, totale, IVA per aliquota, totale non fiscale

**Passo 2** — Salva o sovrascrive il record giornaliero in `corrispettivi`

**Passo 3** — Scrive automaticamente un'entrata in `prima_nota_cassa` (imponibile + IVA = totale lordo)

**Passo 4** — Confronta con i dati del POS fisico. Se c'è differenza → avviso in Magazzino → Coerenza POS

### Dove li vedi
Fatture → Corrispettivi, Prima Nota → Cassa, Magazzino → Coerenza POS, Contabilità → Controllo Mensile

---

## 📧 5. ARRIVA UN'EMAIL — COSA SUCCEDE OGNI GIORNO

### Quando gira lo scanner
- **PEC Aruba** → ogni ora (scarica ultimi 7 giorni)
- **Gmail** → ogni 10 minuti
- **Scanner completo** → avviabile manualmente da Strumenti → Email Download

### Cosa fa lo scanner — passo per passo

**Passo 1 — Connessione IMAP**
Si connette alla casella (PEC `imaps.pec.aruba.it:993` o Gmail `imap.gmail.com:993`) e scansiona INBOX e cartelle correlate. Tutto gira in un thread separato (`asyncio.to_thread`) per non bloccare il sistema.

**Passo 2 — Classificazione email**
Ogni email viene classificata automaticamente in una di 23 categorie basate su parole chiave nel soggetto e nel corpo:

| Categoria | Parole chiave riconosciute |
|---|---|
| F24 | "f24", "modello f24", "tributo", "versamento", "codice tributo" |
| Buste Paga | "cedolino", "busta paga", "retribuzione", "stipendio", "paghe" |
| Fatture Fornitori | "fattura", "invoice", "nota di credito", "fattura elettronica" |
| INPS Contributi | "inps", "dm10", "uniemens", "durc", "matricola inps" |
| INPS Dilazioni | "dilazione", "rateizzazione", "piano rateale" |
| Agenzia Entrate | "agenzia delle entrate", "ader", "cartella esattoriale", "riscossione" |
| Rottamazione | "rottamazione", "definizione agevolata", "pace fiscale" |
| Verbali/Multe | "verbale", "multa", "infrazione", "violazione cds" |
| Noleggio Auto | "leasys", "ald", "arval", "leaseplan", "noleggio", "ayvens", "canone" |
| Bonifici Stipendi | "bonifico", "pagamento stipendio", "you business", "youbusiness" |
| Estratto Conto | "estratto conto", "movimenti c/c", "conto corrente", "rendiconto" |
| Assicurazione | "polizza", "assicurazione", "premio", "sinistro", "rca" |
| PagoPA | "pagopa", "avviso di pagamento", "cbill" |
| INAIL | "inail", "infortunio", "autoliquidazione" |
| Dimissioni | "dimissioni", "recesso", "cessazione rapporto", "cliclavoro" |
| Contratti | "assunzione", "contratto", "proroghe", "trasformazione" |

**Passo 3 — Download allegati**
Per ogni email classificata, scarica tutti gli allegati PDF e li salva in `email_documents` su MongoDB (tutto in DB, niente su filesystem).

**Passo 4 — Costruzione indice e matching**
Il sistema costruisce un indice di tutti i documenti del gestionale (fatture, verbali noleggio, contratti, F24). Per ogni email scaricata cerca pattern nel soggetto e nel corpo: numeri fattura, targhe auto, importi, codici tributo, identificativi PagoPA. Se trova un match → associa il PDF al documento corrispondente.

**Passo 5 — Automazione specifica per tipo**

- **Email con XML fattura** (da SDI o PEC Aruba) → viene parsata e la fattura importata automaticamente nel gestionale come se fosse un import manuale
- **Email con cedolino PDF** → viene passata al parser Zucchetti e il cedolino viene importato automaticamente
- **Email con F24** → viene classificata e il PDF archiviato, pronto per la riconciliazione tributi
- **Email PagoPA** → cerca il codice bolletta (CBILL) nell'estratto conto per abbinare il pagamento
- **Email verbale multa** → cerca la targa del veicolo nei verbali noleggio e associa il PDF

**Passo 6 — Notifica WebSocket**
Se vengono trovati nuovi documenti importanti, l'interfaccia riceve una notifica push in tempo reale.

---

## 🧠 6. LEARNING MACHINE — COME IMPARA E A COSA SERVE

### Cosa è
Un sistema che osserva tutti i dati del gestionale, impara i pattern, e usa quello che ha imparato per classificare automaticamente i nuovi documenti e aiutare l'utente.

### Cosa osserva e cosa impara

**Dai fornitori:**
Ogni volta che una fattura viene associata a un fornitore e confermata, il sistema registra le parole chiave della descrizione (es. "farina", "packaging", "trasporto"). La prossima fattura con quelle parole → assegnata automaticamente allo stesso fornitore e categoria.

**Dalle fatture:**
Analizza le righe delle fatture e assegna ogni fattura a un **centro di costo** (es. Rosticceria, Pasticceria, Amministrazione, Veicoli) con una percentuale di confidenza. Calcola anche deducibilità IRES/IRAP e detraibilità IVA per ogni centro di costo, automaticamente.

**Dal calendario pagamenti:**
Calcola il pattern di pagamento per ogni fornitore: mensile, trimestrale, annuale, bisettimanale. Con almeno 2 pagamenti storici sa già quando arriverà il prossimo e lo aggiunge alle scadenze previste.

**Dai movimenti bancari:**
Impara ad abbinare le descrizioni dei bonifici in uscita ai fornitori (es. "PASTA GAROFALO SRL" nell'estratto conto → fattura Garofalo). La prossima volta propone l'abbinamento automaticamente.

**Dagli F24:**
Classifica ogni codice tributo (es. 1001 = IRPEF, 1030 = addizionale comunale, 6001 = IVA gen) e lo abbina ai cedolini del mese corrispondente. Sa rispondere alla domanda: "Questo F24 di giugno ha pagato i contributi di [dipendente]?"

**Dagli assegni:**
Riconosce i pattern degli assegni (numero serie, banca traente) e li abbina alle fatture pagate.

### Dove registra i dati
- `learning_rules` — regole imparate (keyword → categoria/fornitore)
- `learning_feedback` — correzioni fatte dall'utente (migliora le regole)
- `documenti_classificati` — ogni documento con la sua classificazione e confidenza
- In ogni fattura → campi `centro_costo_id`, `centro_costo_nome`, `classificazione_confidence`, `imponibile_deducibile_ires`, `iva_detraibile`

### A cosa servono questi dati
- **All'utente** → vede ogni fattura già classificata con centro di costo e deducibilità, senza doverla assegnare a mano
- **Al bilancio** → i costi sono già ripartiti per centro di costo, il bilancio è automaticamente strutturato
- **Al commercialista** → esporta il pacchetto mese con fatture già classificate e importi fiscali calcolati
- **Al controllo IVA** → sa già quanta IVA è detraibile e quanta no, per ogni acquisto

### Come migliora nel tempo
Ogni volta che l'utente corregge una classificazione errata, la correzione viene salvata in `learning_feedback` e diventa una nuova regola. Il sistema non fa mai la stessa classificazione errata due volte per lo stesso tipo di documento.

---

## ❓ 7. DOMANDE CHE IL SISTEMA SA RISPONDERE

**"Questo avviso bonario è già stato pagato?"**
Il sistema cerca il codice tributo e l'anno/periodo nell'archivio F24. Se trova un F24 con lo stesso codice nello stesso periodo → risponde sì, mostra la data e l'importo pagato, e lo abbina all'eventuale movimento nell'estratto conto.

**"Questa fattura è già stata riconciliata con la banca?"**
Cerca il matching tra la fattura (importo + fornitore) e i movimenti bancari importati. Se abbinata → mostra il movimento e la data di addebito in banca.

**"Questo stipendio è stato pagato?"**
Cerca il bonifico nell'estratto conto con importo e data compatibili con il cedolino. Se trovato → mostra il movimento bancario e segna il cedolino come erogato.

**"Quanto devo pagare questo mese?"**
Somma: fatture in scadenza + F24 del 16 del mese + INPS + rate mutui + canoni noleggio auto.

**"Da quale fornitore compro di più?"**
Aggrega fatture per fornitore per anno, ordinate per importo totale.

---

## 🔗 8. MAPPA COMPLETA DELLE RELAZIONI

```
EMAIL/PEC (ogni ora o ogni 10 min)
    ├──→ XML fattura SDI → import automatico in Fatture
    ├──→ PDF cedolino → import automatico in Cedolini
    ├──→ PDF F24 → archivio F24, pronto per riconciliazione
    ├──→ PDF verbale multa → associato a verbale noleggio per targa
    ├──→ PDF PagoPA → abbinato al movimento bancario (codice CBILL)
    └──→ PDF estratto conto → import movimenti bancari

FATTURA XML (import manuale o PEC)
    ├──→ Fornitori (crea/aggiorna anagrafica)
    ├──→ Magazzino (carico giacenze per ogni riga)
    ├──→ Scadenze (scadenza pagamento)
    ├──→ Prima Nota Banca/Cassa (dopo conferma)
    ├──→ Riconciliazione (abbinamento estratto conto)
    └──→ Learning Machine (classifica centro di costo)

CEDOLINO PDF
    ├──→ Dipendenti (paga base, ferie/permessi)
    ├──→ TFR (accantonamento)
    ├──→ Prima Nota Salari (uscita automatica)
    └──→ Riconciliazione (abbinamento bonifico stipendio)

CORRISPETTIVI XML (import manuale)
    ├──→ Prima Nota Cassa (entrata automatica)
    ├──→ Magazzino → Coerenza POS (controllo scarti)
    └──→ Contabilità → Fatturato mese

ESTRATTO CONTO BANCARIO
    ├──→ Fatture (segna pagate)
    ├──→ Cedolini (segna stipendi erogati)
    ├──→ F24 (verifica pagamento tributi)
    ├──→ PagoPA (abbina ricevute)
    └──→ Prima Nota Banca (movimenti registrati)

VERSAMENTO CASSA → BANCA
    ├──→ Prima Nota Cassa (uscita)
    └──→ Prima Nota Banca (entrata)

PRELEVAMENTO BANCA
    ├──→ Prima Nota Banca (uscita)
    └──→ Prima Nota Cassa (entrata eventuale)

FINANZIAMENTO SOCI
    ├──→ Prima Nota Banca (entrata)
    └──→ Contabilità → Bilancio (passivo: debito verso soci)

LEARNING MACHINE (sempre in background)
    ├──→ Legge fatture, cedolini, F24, movimenti banca, assegni
    ├──→ Scrive regole in learning_rules
    ├──→ Classifica fatture per centro di costo
    └──→ Risponde a domande su pagamenti, tributi, riconciliazioni

TUTTO CONVERGE IN
    └──→ Dashboard (KPI real-time)
         └──→ Contabilità (bilancio, IVA, controllo mensile, partitario)
              └──→ Commercialista (pacchetto mese già pronto)
```

---

## ✅ Già automatico oggi
- Import fattura da PEC ogni ora ✅
- Creazione fornitore da XML ✅
- Carico magazzino da righe fattura ✅
- Scadenza pagamento da fattura ✅
- Storno nota di credito ✅
- Import cedolino da Gmail ✅
- Prima Nota Salari da cedolino ✅
- Entrata Prima Nota Cassa da corrispettivi ✅
- Classificazione email in 23 categorie ✅
- Matching PDF con documenti (verbali, fatture, F24) ✅
- Abbinamento PagoPA con codice CBILL ✅
- Learning Machine: classificazione fatture per centro di costo ✅
- Calcolo deducibilità/detraibilità per centro di costo ✅
- Notifiche WebSocket in tempo reale ✅

## ⚠️ Da completare/migliorare
- **Prima Nota da fattura senza conferma manuale** (scrittura automatica al pagamento confermato)
- **Piano dei Conti cliccabile** → ogni conto apre il partitario con tutti i movimenti collegati
- **Fornitori cliccabili** → ogni fornitore mostra fatture, scadenze, riconciliazioni in un'unica scheda
- **Fatture cliccabili** → apre dettaglio con righe, PDF, movimenti prima nota, stato riconciliazione
- **Dipendenti cliccabili** → storico cedolini, presenze, TFR, bonifici in un'unica scheda
- **Risposta automatica "avviso bonario già pagato"** → collegamento diretto F24 ↔ tributo ↔ estratto conto
- **TFR automatico da cedolino** senza endpoint separato
- **Controllo IVA mensile automatico** con alert se liquidazione non quadra

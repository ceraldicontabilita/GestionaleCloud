# 🔄 Flussi Automatici — Ceraldi ERP

Questo documento descrive cosa succede **esattamente** quando entra un documento nel sistema.
Scritto in linguaggio semplice. Per ogni tipo di documento: cosa si scatena, dove appare, cosa si aggiorna.

---

## 📄 FATTURA XML — Cosa succede quando arriva

### Da dove arriva
- Import manuale dalla pagina **Documenti → Import** (file .xml o .zip)
- Email PEC scaricata automaticamente dallo scheduler (SDI `@pec.fatturapa.it`)
- Notifica dal ponte ERP da ceraldiapp.it (fatture fornitori HACCP)

### Cosa succede nell'ordine

**1. Parsing XML**
Il sistema legge il file e ne estrae tutto: fornitore, P.IVA, numero fattura, data, importo, righe, IVA, allegati PDF.

**2. Controllo duplicati**
Se la stessa fattura (stesso numero + stessa P.IVA fornitore) esiste già:
- Se era arrivata da email come bozza → viene sostituita
- Se era già importata da XML → viene aggiornata solo la parte XML, senza toccare nulla d'altro

**3. Fornitore: crea o aggiorna**
Cerca il fornitore per P.IVA. Se non esiste → lo crea in anagrafica fornitori automaticamente. Se esiste → recupera il metodo di pagamento predefinito e l'IBAN.

**4. Nota di credito (TD04/TD08)**
Se la fattura è una nota di credito, cerca la fattura originale e la storna: segna che ha una nota di credito, riduce l'importo residuo, aggiorna lo scadenziario.

**5. Magazzino**
Se il fornitore non è escluso dal magazzino → carica automaticamente le righe come entrate in giacenza. Ogni riga della fattura diventa un movimento di carico magazzino.

**6. Scadenziario**
Crea automaticamente una scadenza di pagamento in base alla data e al metodo di pagamento del fornitore.

**7. Prima Nota** *(in attesa di conferma)*
La registrazione contabile viene preparata ma NON scritta automaticamente — richiede conferma manuale per evitare errori. Quando confermata: se pagamento in cassa → va in Prima Nota Cassa; se bonifico/banca → va in Prima Nota Banca.

**8. Avvisi**
Se il fornitore non ha metodo di pagamento → avviso giallo. Se il metodo è bonifico ma manca l'IBAN → avviso rosso.

### Dove la vedi dopo
| Sezione | Cosa trovi |
|---|---|
| **Fatture** | La fattura con tutte le righe e allegati |
| **Fornitori** | Il fornitore aggiornato o creato |
| **Magazzino** | Il carico delle righe in giacenza |
| **Scadenze** | La scadenza di pagamento |
| **Prima Nota** | Il movimento (dopo conferma) |
| **Riconciliazione** | In attesa di abbinamento con estratto conto |
| **Contabilità → Controllo Mensile** | Il totale fatture del mese |

---

## 💰 CEDOLINO PDF — Cosa succede quando arriva

### Da dove arriva
- Upload manuale dalla pagina **Cedolini** (PDF Zucchetti, anche multipli in batch)
- Download automatico da Gmail (cerca email con "cedolino", "busta paga", "libro unico")

### Cosa succede nell'ordine

**1. Lettura del PDF**
Il parser Zucchetti estrae: nome dipendente, mese, anno, netto in busta, imponibile IRPEF, contributi INPS, progressivi annuali, ferie/permessi residui, TFR accantonato.

**2. Abbinamento dipendente**
Cerca il dipendente per nome o codice fiscale nella collection `dipendenti`. Se non trova corrispondenza → segnala l'anomalia.

**3. Upsert cedolino**
Salva il cedolino abbinato a dipendente + mese + anno. Se esiste già → sovrascrive solo i dati del cedolino, non tocca altri campi.

**4. Aggiornamento paga base**
La paga base nel profilo dipendente viene aggiornata solo se questo è il cedolino più recente.

**5. Progressivi annuali**
INPS e IRPEF progressivi vengono aggiornati con la logica MAX: prende il valore più alto tra quello già salvato e quello del cedolino nuovo (per non perdere dati).

**6. TFR**
Aggiorna il TFR accantonato per anno, tenendo il dato del mese più recente.

**7. Ferie e permessi**
Aggiorna i saldi ferie/permessi solo se questo cedolino è più recente di quello già salvato.

**8. Prima Nota Salari**
Registra automaticamente il movimento in uscita nella Prima Nota Salari con importo netto, dipendente, periodo.

### Dove lo vedi dopo
| Sezione | Cosa trovi |
|---|---|
| **Cedolini** | Il cedolino caricato con tutti i dati |
| **Dipendenti** | Paga base aggiornata |
| **Presenze** | Ferie e permessi residui aggiornati |
| **TFR** | Accantonamento aggiornato |
| **Prima Nota → Salari** | Il movimento di uscita del mese |
| **Riconciliazione** | Il bonifico stipendio da abbinare all'estratto conto |
| **Contabilità → Bilancio** | Costo del personale del periodo |

---

## 🏦 ESTRATTO CONTO BANCARIO — Cosa succede quando arriva

### Da dove arriva
- Import manuale dalla pagina **Riconciliazione** (CSV/Excel da banca)
- Download automatico da email

### Cosa succede nell'ordine

**1. Parsing movimenti**
Il sistema legge ogni riga: data, importo, descrizione, causale ABI.

**2. Match automatico con fatture**
Per ogni movimento cerca una fattura con importo simile e data compatibile. Se trova un match → propone la riconciliazione.

**3. Match con bonifici stipendi**
Cerca il movimento nell'estratto conto che corrisponde ai bonifici stipendi del mese.

**4. Match con corrispettivi**
Le entrate di cassa vengono abbinate ai corrispettivi giornalieri.

**5. Prima Nota Banca**
Ogni movimento abbinato genera o aggiorna la voce in Prima Nota Banca.

### Dove lo vedi dopo
| Sezione | Cosa trovi |
|---|---|
| **Riconciliazione** | Movimenti abbinati e da abbinare |
| **Prima Nota → Banca** | I movimenti registrati |
| **Fatture** | Fattura segnata come pagata |
| **Cedolini** | Stipendi segnati come erogati |
| **Contabilità → Bilancio** | Saldo banca aggiornato |

---

## 📊 CORRISPETTIVI — Cosa succede quando arrivano

### Da dove arrivano
- Import XML manuale dalla pagina **Documenti → Import** (esportati dal registratore telematico)

### Cosa succede nell'ordine

**1. Parsing XML corrispettivi**
Legge: data, totale venduto, IVA per aliquota, totale non fiscale.

**2. Salvataggio giornaliero**
Ogni giornata viene salvata come record unico. Se esiste già → sovrascrive.

**3. Prima Nota Cassa**
Ogni corrispettivo genera automaticamente un'entrata in Prima Nota Cassa (importo lordo = imponibile + IVA).

**4. Controllo coerenza POS**
Confronta i corrispettivi XML con i dati del POS fisico. Se c'è differenza → avviso in Magazzino → Coerenza POS.

### Dove lo vedi dopo
| Sezione | Cosa trovi |
|---|---|
| **Fatture → Corrispettivi** | Il riepilogo giornaliero e mensile |
| **Prima Nota → Cassa** | Le entrate del giorno |
| **Magazzino → Coerenza POS** | Eventuale scarto con il POS |
| **Contabilità → Controllo Mensile** | Fatturato del mese |
| **Dashboard** | KPI aggiornati |

---

## 🏠 PIANO DEI CONTI — Come dovrebbe funzionare il dettaglio

### Problema attuale
Cliccando su un codice conto nel Piano dei Conti non si apre nessun dettaglio. È solo una lista statica.

### Come dovrebbe funzionare
Ogni conto deve essere **cliccabile** e aprire una scheda laterale (o una pagina) con:
- Tutti i movimenti di Prima Nota collegati a quel conto
- Totale dare/avere per anno
- Elenco fatture o pagamenti che hanno generato movimenti su quel conto
- Saldo progressivo mese per mese

Lo stesso vale per:
- **Fornitori** → clicco sul nome → vedo tutte le fatture, i pagamenti, lo scadenziario, le riconciliazioni
- **Fatture** → clicco su una fattura → vedo righe, allegato PDF, movimenti prima nota collegati, stato riconciliazione
- **Dipendenti** → clicco sul nome → vedo tutti i cedolini, le presenze, il TFR, i bonifici stipendi
- **Scadenze** → clicco su una scadenza → vedo la fattura originale e i movimenti bancari collegati

### Principio generale
**Ogni dato deve essere un link.** Nessun numero deve essere un numero morto — deve sempre portare da qualche parte e mostrare da dove viene e dove va.

---

## 🔗 Mappa delle relazioni tra sezioni

```
FATTURA XML
    ├──→ Fornitori (crea/aggiorna anagrafica)
    ├──→ Magazzino (carico giacenze per ogni riga)
    ├──→ Scadenze (scadenza pagamento)
    ├──→ Prima Nota Banca/Cassa (dopo conferma)
    └──→ Riconciliazione (abbinamento estratto conto)

CEDOLINO PDF
    ├──→ Dipendenti (aggiorna paga base, ferie)
    ├──→ TFR (aggiorna accantonamento)
    ├──→ Prima Nota Salari (movimento uscita)
    └──→ Riconciliazione (abbinamento bonifico stipendio)

ESTRATTO CONTO
    ├──→ Fatture (segna pagate)
    ├──→ Cedolini (segna stipendi erogati)
    ├──→ Prima Nota Banca (movimenti)
    └──→ Riconciliazione (abbinamenti)

CORRISPETTIVI XML
    ├──→ Prima Nota Cassa (entrate)
    ├──→ Magazzino (coerenza POS)
    └──→ Contabilità (fatturato mese)

TUTTO
    └──→ Dashboard (KPI in tempo reale)
         └──→ Contabilità (bilancio, controllo mensile, IVA)
```

---

## ✅ Cosa è già automatico oggi

- Creazione fornitore da XML ✅
- Carico magazzino da righe fattura ✅
- Scadenza pagamento da fattura ✅
- Storno nota di credito ✅
- Prima Nota Salari da cedolino ✅
- Entrata Prima Nota Cassa da corrispettivi ✅
- Riconciliazione banca proposta automatica ✅
- Ponte ERP ceraldiapp → fatture_passive ✅

## ⚠️ Cosa manca ancora (da implementare)

- Prima Nota da fattura **senza conferma manuale** (scrittura automatica al pagamento)
- **Dettaglio cliccabile** su Piano dei Conti, Fornitori, Fatture, Dipendenti
- TFR aggiornamento automatico da cedolino (oggi richiede endpoint separato)
- Controllo IVA automatico mensile (confronto fatture vs liquidazione IVA)
- Notifica real-time quando una fattura viene riconciliata

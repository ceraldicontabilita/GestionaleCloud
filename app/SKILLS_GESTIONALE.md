# 🏢 SKILLS: Operazioni Complete Gestionale OpenClaw ERP

## Indice

1. [Gestione Documenti PDF](#1-gestione-documenti-pdf)
2. [Ciclo Paghe e Contributi](#2-ciclo-paghe-e-contributi)
3. [Gestione Mutui e Finanziamenti](#3-gestione-mutui-e-finanziamenti)
4. [Riconciliazione Bancaria](#4-riconciliazione-bancaria)
5. [Ciclo Attivo (Vendite)](#5-ciclo-attivo-vendite)
6. [Ciclo Passivo (Acquisti)](#6-ciclo-passivo-acquisti)
7. [Prima Nota e Contabilità](#7-prima-nota-e-contabilità)
8. [Scadenzario](#8-scadenzario)
9. [Fisco e Tributi](#9-fisco-e-tributi)
10. [Dashboard e Reporting](#10-dashboard-e-reporting)

---

## 1. GESTIONE DOCUMENTI PDF

### 1.1 Workflow Upload Documenti

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Upload PDF     │────▶│  Identifica  │────▶│  Parser         │
│  (Frontend)     │     │  Tipo Doc    │     │  Specifico      │
└─────────────────┘     └──────────────┘     └─────────────────┘
                                                      │
                        ┌──────────────┐              │
                        │  Valida      │◀─────────────┘
                        │  Dati        │
                        └──────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
┌─────────────┐      ┌─────────────────┐     ┌─────────────┐
│ Salva DB    │      │ Crea Scadenze   │     │ Aggiorna    │
│ (MongoDB)   │      │ Automatiche     │     │ Dashboard   │
└─────────────┘      └─────────────────┘     └─────────────┘
```

### 1.2 Tipi Documento Riconosciuti

| Tipo | Identificazione | Parser | Azioni Automatiche |
|------|-----------------|--------|-------------------|
| Libro Unico (LUL) | "Zucchetti", 2 pag/dipendente | `libro_unico_parser` | Aggiorna dipendenti, buste_paga |
| Modello F24 | "SEZIONE ERARIO", codici tributo | `f24_parser` | Crea scadenza, aggiorna fisco |
| Piano Ammortamento | "Rate", "Delibera", BPM | `mutui_parser` | Aggiorna mutui, rate |
| Estratto Conto | "Saldo", "Movimenti" | `estratto_conto_parser` | Importa movimenti banca |
| Fattura XML | SDI, FatturaPA | `fattura_parser` | Ciclo passivo/attivo |
| Corrispettivi | XML AdE | `corrispettivi_parser` | Aggiorna POS/cassa |

### 1.3 Regole di Identificazione Automatica

```python
def identifica_documento(pdf_text):
    if "Zucchetti" in pdf_text and "CEDOLINO" in pdf_text:
        return "LIBRO_UNICO"
    elif "SEZIONE ERARIO" in pdf_text or "F24" in pdf_text:
        return "F24"
    elif "Delibera" in pdf_text and "Rate" in pdf_text:
        return "PIANO_AMMORTAMENTO"
    elif "Saldo contabile" in pdf_text:
        return "ESTRATTO_CONTO"
    elif "FatturaElettronica" in pdf_text:
        return "FATTURA_XML"
    else:
        return "DOCUMENTO_GENERICO"
```

---

## 2. CICLO PAGHE E CONTRIBUTI

### 2.1 Quando Carico un CEDOLINO (Libro Unico)

**Azioni Automatiche COMPLETE:**

1. **Parsing PDF**
   - Estrae dati di tutti i dipendenti (foglio presenze + busta paga)
   - Identifica periodo di riferimento (es. Gennaio 2026)

2. **AGGIORNAMENTO ANAGRAFICA DIPENDENTE**
   ```
   Collection: dipendenti
   ├── codice_fiscale (chiave)
   ├── cognome
   ├── nome
   ├── data_nascita
   ├── indirizzo
   ├── citta
   ├── cap
   ├── telefono
   ├── email
   ├── iban_accredito ← AGGIORNATO DA CEDOLINO
   ├── data_assunzione
   ├── qualifica
   ├── livello
   ├── mansione
   ├── paga_oraria
   ├── tipo_contratto
   ├── scadenza_contratto
   ├── pat_inail
   ├── matricola_inps
   └── stato (attivo/cessato)
   
   → Se dipendente NON esiste: CREA NUOVO
   → Se dipendente esiste: AGGIORNA dati modificati
   ```

3. **AGGIORNAMENTO PRESENZE MENSILI**
   ```
   Collection: presenze_mensili
   ├── dipendente_id (codice_fiscale)
   ├── periodo (es. "2026-01")
   ├── giorni_lavorati
   ├── ore_ordinarie
   ├── ore_straordinarie
   ├── ferie_godute
   ├── permessi_goduti
   ├── malattia
   ├── assenze_ingiustificate
   ├── dettaglio_giornaliero[] ← DA FOGLIO PRESENZE
   │   ├── giorno
   │   ├── giorno_settimana
   │   ├── ore
   │   ├── giustificativo
   │   └── note
   └── totale_ore
   ```

4. **AGGIORNAMENTO SALARI E BUSTE PAGA**
   ```
   Collection: buste_paga
   ├── id_busta
   ├── dipendente_id
   ├── periodo
   ├── competenze[]
   │   ├── codice
   │   ├── voce
   │   ├── quantita
   │   ├── importo
   │   └── tipo (ordinario/straordinario/accessorio)
   ├── trattenute[]
   │   ├── codice
   │   ├── voce
   │   ├── imponibile
   │   ├── aliquota
   │   └── importo
   ├── irpef{}
   ├── addizionali{}
   ├── progressivi{}
   ├── tfr{}
   ├── ratei{}
   ├── totale_competenze
   ├── totale_trattenute
   ├── netto_mese
   ├── iban_pagamento
   ├── stato_pagamento: "DA_PAGARE" ← STATO INIZIALE
   ├── data_pagamento: null
   ├── movimento_bancario_id: null
   └── acconti[] ← GESTIONE ACCONTI
       ├── data
       ├── importo
       ├── movimento_id
       └── note
   ```

5. **GESTIONE ACCONTI E SALDO CEDOLINO**
   ```
   Workflow Acconto/Saldo:
   
   NETTO CEDOLINO: €1.436,00
   ├── Acconto 1 (15/01): €500,00 → stato: "ACCONTO_PARZIALE"
   ├── Acconto 2 (20/01): €400,00 → stato: "ACCONTO_PARZIALE"
   └── Saldo (27/01): €536,00 → stato: "SALDATO"
   
   Collection: acconti_stipendi
   ├── busta_paga_id
   ├── dipendente_id
   ├── periodo
   ├── tipo: "ACCONTO" | "SALDO"
   ├── importo
   ├── data_pagamento
   ├── movimento_bancario_id
   ├── riconciliato: true/false
   └── note
   
   Calcolo automatico:
   totale_acconti = SUM(acconti.importo)
   saldo_residuo = netto_mese - totale_acconti
   
   Quando saldo_residuo = 0 → stato_pagamento = "SALDATO"
   ```

6. **CREAZIONE SCADENZE**
   ```
   Scadenze create automaticamente:
   
   A) Scadenza Stipendi (per ogni dipendente o cumulativa)
      ├── titolo: "Stipendio Gennaio 2026 - TAIANO LUIGI"
      ├── tipo: "STIPENDIO"
      ├── data_scadenza: "2026-01-27" (fine mese)
      ├── importo: €1.436,00
      ├── documento_id: busta_paga_id
      └── stato: "DA_PAGARE"
   
   B) Scadenza F24 Collegata
      ├── titolo: "F24 - Contributi Gennaio 2026"
      ├── tipo: "F24"
      ├── data_scadenza: "2026-02-16"
      ├── importo: (calcolato da cedolini)
      └── nota: "Attesa caricamento F24"
   ```

7. **ATTESA RICONCILIAZIONE BANCARIA**
   ```
   Workflow Riconciliazione Stipendio:
   
   CEDOLINO CARICATO
        │
        ▼
   STATO: "DA_PAGARE"
   Attende bonifico bancario
        │
        ▼
   RICONCILIAZIONE AUTOMATICA
   Cerca in movimenti banca:
   ├── IBAN destinatario = IBAN cedolino
   ├── Importo = netto_mese (o acconto)
   ├── Data = ±5 giorni da fine mese
   └── Descrizione contiene cognome dipendente
        │
        ▼
   SE TROVATO:
   ├── busta_paga.stato_pagamento = "PAGATO"
   ├── busta_paga.movimento_bancario_id = movimento._id
   ├── busta_paga.data_pagamento = movimento.data
   ├── movimento.riconciliato = true
   └── movimento.tipo_documento = "stipendio"
        │
        ▼
   SE NON TROVATO:
   └── Rimane in "DA_PAGARE" → Alert dopo scadenza
   ```

8. **Aggiornamento Dashboard**
   - Totale costo personale del mese
   - Totale netto da pagare
   - Stipendi pagati vs da pagare
   - Alert scadenze imminenti
   - Progressivo TFR aziendale

### 2.2 Quando Carico un F24

**Azioni Automatiche COMPLETE:**

1. **Parsing PDF**
   - Estrae tutte le sezioni (Erario, INPS, Regioni, IMU, INAIL)
   - Identifica scadenza pagamento
   - Estrae IBAN e banca per pagamento

2. **Aggiornamento Database F24**
   ```
   Collection: f24_pagamenti
   ├── f24_id (univoco)
   ├── scadenza
   ├── contribuente{}
   ├── sezione_erario{}
   ├── sezione_inps{}
   ├── sezione_regioni{}
   ├── sezione_imu{}
   ├── sezione_inail{}
   ├── totale_da_pagare
   ├── stato: "DA_PAGARE" ← STATO INIZIALE
   ├── data_pagamento: null
   ├── movimento_bancario_id: null
   └── riconciliato: false
   ```

3. **AGGIORNAMENTO TRIBUTI PAGATI (STORICO)**
   ```
   Collection: tributi_pagati
   ├── id
   ├── f24_id (riferimento)
   ├── codice_tributo
   ├── descrizione_tributo
   ├── sezione (ERARIO/INPS/REGIONI/IMU/INAIL)
   ├── anno_riferimento
   ├── periodo_riferimento
   ├── importo_debito
   ├── importo_credito
   ├── importo_netto
   ├── data_scadenza
   ├── data_pagamento: null ← Aggiornato dopo riconciliazione
   ├── stato: "DA_PAGARE"
   └── note
   
   → Permette RICERCA per codice tributo
   → Permette FILTRO per anno/periodo
   → Permette REPORT tributi versati
   ```

4. **CREAZIONE DISTINTA GENERALE**
   ```
   Collection: distinte_f24
   ├── id_distinta
   ├── data_creazione
   ├── scadenza
   ├── f24_ids[] (può raggruppare più F24)
   ├── riepilogo:
   │   ├── totale_erario
   │   ├── totale_inps
   │   ├── totale_regioni
   │   ├── totale_imu
   │   ├── totale_inail
   │   └── totale_generale
   ├── dettaglio_tributi[]
   │   ├── codice
   │   ├── descrizione
   │   ├── importo
   │   └── compensato (sì/no)
   ├── banca_pagamento
   ├── iban
   ├── stato: "DA_PAGARE"
   └── file_pdf_generato
   ```

5. **Creazione Scadenza**
   ```
   Collection: scadenze
   ├── titolo: "F24 02/2026 - €7.465,55"
   ├── tipo: "F24"
   ├── data_scadenza: "2026-02-16"
   ├── importo: 7465.55
   ├── documento_id: "f24_04523831214_02-2026"
   ├── priorita: "ALTA"
   ├── completata: false
   └── notifiche_inviate[]
   ```

6. **Collegamento con Cedolini (Verifica Coerenza)**
   ```
   Verifica automatica:
   
   INPS da F24: €6.227,00
   vs
   INPS da cedolini: Σ(contributo_ivs + fis) per tutti i dipendenti
   
   IRPEF da F24: €1.307,25
   vs
   IRPEF da cedolini: Σ(ritenute_irpef) per tutti i dipendenti
   
   SE DISCREPANZA > €1:
   └── Genera ALERT con dettaglio differenze
   ```

7. **ATTESA RICONCILIAZIONE BANCARIA**
   ```
   Workflow Riconciliazione F24:
   
   F24 CARICATO
        │
        ▼
   STATO: "DA_PAGARE"
   Attende addebito bancario
        │
        ▼
   RICONCILIAZIONE AUTOMATICA
   Cerca in movimenti banca:
   ├── Importo = totale_da_pagare (esatto)
   ├── Data = data_scadenza ±3 giorni
   ├── Descrizione contiene "F24" o "ERARIO" o "INPS"
   └── Tipo movimento = ADDEBITO
        │
        ▼
   SE TROVATO:
   ├── f24.stato = "PAGATO"
   ├── f24.data_pagamento = movimento.data
   ├── f24.movimento_bancario_id = movimento._id
   ├── movimento.riconciliato = true
   ├── AGGIORNA tributi_pagati.stato = "PAGATO"
   └── AGGIORNA tributi_pagati.data_pagamento
        │
        ▼
   SE NON TROVATO dopo scadenza:
   └── ALERT: "F24 scaduto non pagato!" (priorità critica)
   ```

8. **Aggiornamento Sezione Fisco**
   ```
   Dashboard Fisco aggiornata con:
   ├── Totale versato anno corrente
   ├── Dettaglio per codice tributo
   ├── Scadenze F24 prossime
   ├── F24 da pagare vs pagati
   └── Storico versamenti
   ```

### 2.3 Workflow Mensile Paghe

```
GIORNO 1-15: Elaborazione Paghe
├── Carica Libro Unico → Parse cedolini
├── Verifica presenze → Controllo giustificativi
└── Genera report costo personale

GIORNO 16: Scadenza Versamenti
├── Carica F24 → Parse tributi
├── Verifica importi vs cedolini
├── Esegui pagamento
└── Marca F24 come "pagato"

FINE MESE: Pagamento Stipendi
├── Genera bonifici da IBAN cedolini
├── Esegui pagamenti
└── Marca stipendi come "pagati"
```

---

## 3. GESTIONE MUTUI E FINANZIAMENTI

### 3.1 Quando Carico un Piano Ammortamento

**Azioni Automatiche:**

1. **Parsing PDF**
   - Estrae intestatario, importo, numero delibera
   - Estrae tutte le rate con scadenze

2. **Aggiornamento Database**
   ```
   Collection: mutui
   ├── mutuo_id
   ├── nome
   ├── importo_accordato
   ├── numero_delibera
   ├── rate[]
   │   ├── numero_rata
   │   ├── data_scadenza
   │   ├── importo_totale
   │   ├── quota_capitale
   │   ├── quota_interessi
   │   ├── stato
   │   └── riconciliata
   ├── totale_pagato
   └── debito_residuo
   ```

3. **Creazione Scadenze Rate**
   - Crea scadenza per ogni rata "Da pagare"
   - Imposta alert 7 giorni prima

4. **Riconciliazione Automatica**
   - Cerca movimenti bancari corrispondenti
   - Collega rate pagate ai movimenti
   - Aggiorna stato riconciliazione

### 3.2 Riconciliazione Rate Mutuo

```
Per ogni rata con stato "Pagata" e riconciliata=false:
│
├── Cerca in estratto_conto_movimenti:
│   ├── data: ±7 giorni dalla scadenza
│   ├── importo: ±€1 dall'importo rata
│   └── riconciliato: false
│
├── Se TROVATO:
│   ├── rata.riconciliata = true
│   ├── rata.movimento_bancario_id = movimento._id
│   ├── movimento.riconciliato = true
│   └── movimento.documento_id = mutuo_id
│
└── Se NON TROVATO:
    └── Segnala per riconciliazione manuale
```

---

## 4. RICONCILIAZIONE BANCARIA

### 4.1 Tipi di Riconciliazione

| Tipo | Fonte | Destinazione | Criteri Match |
|------|-------|--------------|---------------|
| Rate Mutuo | Piano ammortamento | Movimenti banca | Importo ±€1, Data ±7gg |
| Stipendi | Cedolini | Movimenti banca | IBAN, Importo esatto |
| F24 | Modello F24 | Movimenti banca | Importo totale, Data 16 |
| Fatture | Fatture passive | Movimenti banca | Importo, Fornitore |
| POS | Chiusure POS | Movimenti banca | Importo, Data +1/+3gg |

### 4.2 Algoritmo Riconciliazione POS

```
Per ogni giorno con incasso POS:
│
├── Calcola data accredito atteso:
│   ├── Lunedì-Giovedì → +1 giorno lavorativo
│   └── Venerdì-Domenica → Lunedì successivo
│
├── Cerca in movimenti banca:
│   ├── data: data_accredito_atteso ±2gg
│   ├── importo: totale_pos ±€5
│   └── descrizione: contiene "POS" o "NEXI" o "SUMUP"
│
└── Collega movimento a chiusura POS
```

---

## 5. CICLO ATTIVO (VENDITE)

### 5.1 Flusso Corrispettivi

```
XML Corrispettivi (AdE)
        │
        ▼
┌───────────────────┐
│ Parse XML         │
│ - Data            │
│ - Totale          │
│ - Dettaglio IVA   │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Salva in          │
│ corrispettivi     │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Verifica vs POS   │
│ - Differenze      │
│ - Anomalie        │
└───────────────────┘
```

### 5.2 Verifica Coerenza POS/Corrispettivi

```
Endpoint: /api/pos-corrispettivi/verifica-coerenza

Output:
├── totale_elettronico_xml: €565.668,78 (da corrispettivi)
├── totale_pos_accreditato: €0 (da banca)
├── totale_chiusure_manuali: €571.514,42 (da pos.xlsx)
├── differenza: €5.845,64
└── anomalie: [lista giorni con discrepanze]
```

---

## 6. CICLO PASSIVO (ACQUISTI)

### 6.1 Flusso Fatture Passive

```
Fattura XML (SDI)
        │
        ▼
┌───────────────────┐
│ Parse FatturaPA   │
│ - Fornitore       │
│ - Importi         │
│ - Scadenze        │
└───────────────────┘
        │
        ▼
┌───────────────────┐     ┌───────────────────┐
│ Salva in          │────▶│ Crea scadenza     │
│ invoices          │     │ pagamento         │
└───────────────────┘     └───────────────────┘
        │
        ▼
┌───────────────────┐
│ Aggiorna          │
│ scadenzario       │
│ fornitori         │
└───────────────────┘
```

### 6.2 Stati Fattura

| Stato | Descrizione | Azioni Possibili |
|-------|-------------|------------------|
| ricevuta | Appena importata | Registra, Rifiuta |
| registrata | In contabilità | Paga, Storna |
| pagata | Pagamento effettuato | - |
| stornata | Annullata | - |

---

## 7. PRIMA NOTA E CONTABILITÀ

### 7.1 Registrazioni Automatiche

| Evento | Registrazione Prima Nota |
|--------|--------------------------|
| Pagamento stipendio | Dare: Costo personale / Avere: Banca |
| Pagamento F24 | Dare: Debiti tributari / Avere: Banca |
| Rata mutuo | Dare: Debiti vs banche / Avere: Banca |
| Incasso POS | Dare: Banca / Avere: Ricavi |
| Pagamento fornitore | Dare: Debiti vs fornitori / Avere: Banca |

### 7.2 Struttura Prima Nota

```
Collection: prima_nota
├── data
├── numero_registrazione
├── causale
├── righe[]
│   ├── conto
│   ├── descrizione
│   ├── dare
│   └── avere
├── documento_origine
│   ├── tipo (fattura/f24/stipendio/rata)
│   └── id
└── stato (provvisoria/definitiva)
```

---

## 8. SCADENZARIO

### 8.1 Tipi Scadenza

| Tipo | Frequenza | Esempio |
|------|-----------|---------|
| F24 | Mensile (16) | Versamento contributi |
| IVA | Trimestrale | Liquidazione IVA |
| Stipendi | Mensile (27-31) | Pagamento dipendenti |
| Rate Mutuo | Mensile | Rata BPM |
| Fornitori | Variabile | Scadenza fattura |
| INAIL | Annuale | Autoliquidazione |

### 8.2 Alert Automatici

```
Scadenze prossimi 7 giorni → Alert ROSSO
Scadenze prossimi 30 giorni → Alert GIALLO
Scadenze oltre 30 giorni → Alert VERDE
```

---

## 9. FISCO E TRIBUTI

### 9.1 Calendario Fiscale

| Mese | Scadenza | Adempimento |
|------|----------|-------------|
| Ogni mese | 16 | F24 (IRPEF, INPS, Addizionali) |
| Marzo | 16 | Saldo IVA anno precedente |
| Giugno | 30 | Dichiarazione redditi |
| Novembre | 30 | Acconto imposte |

### 9.2 Calcolo Automatico

```
Da cedolini → Ritenute IRPEF da versare
Da cedolini → Contributi INPS da versare
Da corrispettivi → IVA a debito
Da fatture passive → IVA a credito
Differenza → Liquidazione IVA
```

---

## 10. DASHBOARD E REPORTING

### 10.1 KPI Principali

| KPI | Calcolo | Fonte |
|-----|---------|-------|
| Costo personale | Σ competenze cedolini | buste_paga |
| Debito residuo mutui | Σ debito_residuo | mutui |
| Scadenze imminenti | Count scadenze < 7gg | scadenze |
| Fatturato | Σ corrispettivi | corrispettivi |
| Margine | Fatturato - Costi | calcolo |

### 10.2 Report Automatici

```
Report Mensile:
├── Riepilogo costo personale
├── Situazione mutui
├── Scadenze pagate/da pagare
├── Riconciliazione bancaria
└── Anomalie rilevate

Report Annuale:
├── Totale versato F24
├── Totale TFR accantonato
├── Interessi mutui (deducibili)
└── Dati per dichiarazione
```

---

## APPENDICE: Comandi Rapidi

### Upload Documenti

```bash
# Libro Unico
curl -X POST /api/paghe/import-libro-unico -F "file=@libro_unico.pdf"

# F24
curl -X POST /api/paghe/import-f24 -F "file=@f24.pdf"

# Piano Ammortamento
curl -X POST /api/mutui/import-pdf -F "file=@ammortamento.pdf"
```

### Riconciliazione

```bash
# Riconcilia mutui
curl -X POST /api/mutui/riconcilia

# Verifica POS/Corrispettivi
curl -X GET /api/pos-corrispettivi/verifica-coerenza?anno=2026
```

### Scadenze

```bash
# Prossime scadenze
curl -X GET /api/scadenze/prossime?giorni=30

# Marca come pagata
curl -X PUT /api/scadenze/{id}/completa
```

---

*Versione: 2.0*
*Ultimo aggiornamento: Febbraio 2026*

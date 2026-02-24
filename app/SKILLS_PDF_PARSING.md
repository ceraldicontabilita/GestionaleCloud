# 📄 SKILLS: Parsing PDF Documenti Paghe e Tributi

## Panoramica

Questo documento definisce le regole e i pattern per l'estrazione dati dai PDF relativi a:
- **Libro Unico del Lavoro (LUL)** - Zucchetti
- **Modello F24** - Agenzia delle Entrate
- **Piani Ammortamento Mutui** - BPM

---

## 1. LIBRO UNICO DEL LAVORO (LUL)

### 1.1 Struttura del Documento

| Elemento | Descrizione |
|----------|-------------|
| **Generatore** | Zucchetti spa |
| **Struttura** | 2 pagine per dipendente |
| **Pagine dispari** | Foglio Presenze |
| **Pagine pari** | Busta Paga (Cedolino) |
| **Filigrana** | Presente - richiede filtraggio |

### 1.2 Gestione Filigrana Zucchetti

La filigrana Zucchetti interferisce con l'estrazione. Pattern da FILTRARE:

```
Singole lettere: ^[A-Z]$
Brevi sequenze: ^[a-z]{1,4}$
URL fragments: www., http, .it, //:p, tth
Frammenti comuni: itte, ccu, lle, rid, alle, ru, co, rp, re
```

**Regola**: Rimuovere tutte le linee che matchano questi pattern PRIMA di parsare i dati.

### 1.3 Foglio Presenze (Pagina Dispari)

#### Intestazione Azienda
```
AZIENDA: [Ragione Sociale]
INDIRIZZO: [Via/Piazza] [Numero]
CAP CITTÀ (PROV) Aut. [Numero]
Del [Data] Sede [Codice]
Nr. [Numero Documento]
[Data Stampa] [Ora]
```

#### Dati Dipendente
```
CODICE: [000000/0000000/0000000000]
COGNOME NOME: [COGNOME] [NOME]
INDIRIZZO: [Via] [Numero], [CAP] [Città] ([Prov])
CODICE FISCALE: [16 caratteri alfanumerici]
P.A.T. INAIL: [000000000/00]
TIPO RAPPORTO: Lavoro dipendente
```

#### Griglia Presenze Giornaliere

**Pattern per riga presenza:**
```
[Giorno Settimana] [Numero] [Ore Ordinarie] [Codice Giustificativo] [Ore Giustificativo]
```

**Esempi:**
```
VE 2 6,40                    → Venerdì 2, 6h40m ordinarie
LU 19 AI 6,40                → Lunedì 19, Assenza Ingiustificata 6h40m
DO 25 FE 6,40                → Domenica 25, Ferie 6h40m
SA 3                         → Sabato 3, riposo (nessuna ora)
```

**Giorni settimana validi:** `LU, MA, ME, GI, VE, SA, DO`

**Codici giustificativi comuni:**
| Codice | Descrizione |
|--------|-------------|
| AI | Assenza Ingiustificata |
| FE | Ferie |
| MA | Malattia |
| PE | Permesso |
| RO | Riposo |
| ST | Straordinario |

#### Riepilogo Giustificativi
```
Ore ordinarie [HH,MM]hm [CODICE] [Descrizione] [HH,MM]hm ...
```

**Esempio:**
```
Ore ordinarie 113,20hm AI Ass.za ingiustif. 6,40hm FE Ferie 40,00hm
```

### 1.4 Busta Paga (Pagina Pari)

#### Sezione COMPETENZE (Voci Z)

| Codice | Voce | Formato |
|--------|------|---------|
| Z00001 | Retribuzione | Base × Quantità = Importo |
| Z00250 | Ferie godute | Base × Ore = Importo |
| Z01100 | **Festività godute** | Base × Ore = Importo |
| Z50000 | 13ma Mensilità | Base × Ore = Importo |
| Z50022 | 14ma Mensilità | Base × Ore = Importo |
| ZP9960 | Arrotondamento mese prec. | Importo |

#### Sezione TRATTENUTE CONTRIBUTIVE (Voci Z)

| Codice | Voce | Imponibile | Aliquota | Importo |
|--------|------|------------|----------|---------|
| Z00000 | Contributo IVS | €X.XXX,XX | 9,19% | €XXX,XX |
| Z00054 | **FIS D.Lgs.148/2015 (≤15 dip)** | €X.XXX,XX | 0,26667% | €X,XX |

#### Sezione CALCOLO IRPEF (Voci F02)

| Codice | Voce | Valore |
|--------|------|--------|
| F02000 | Imponibile IRPEF | €X.XXX,XX |
| F02010 | IRPEF lorda | €XXX,XX |
| F02500 | Detrazioni lav.dip. | €XXX,XX |
| F02703 | Indennità L.207/24 | €XX,XX |
| F03020 | **Ritenute IRPEF** | €XX,XX |

#### Sezione TASSAZIONE AUTONOMA (Voci F06)

| Codice | Voce | Valore |
|--------|------|--------|
| F06000 | Imponibile Tass.aut. | €XXX,XX |
| F06010 | IRPEF lorda Tass.aut. | €XX,XX |
| F06020 | **Ritenute IRPEF Tass.aut.** | €XX,XX |

#### Sezione ADDIZIONALI (Voci F09)

| Codice | Voce | Anno | Regione/Comune | Residuo | Trattenuta |
|--------|------|------|----------------|---------|------------|
| F09110 | Addizionale regionale | 2025 | CAMPANIA | €XXX,XX | €XX,XX |
| F09130 | Addizionale comunale | 2025 | NAPOLI | €XXX,XX | €XX,XX |

#### Sezione PROGRESSIVI

```
Imp. INPS    Imp. INAIL   Imp. IRPEF   IRPEF pagata
€X.XXX,XX    €X.XXX,XX    €X.XXX,XX    €XXX,XX
```

#### Sezione TFR

```
F.do 31/12   Rivalutaz.   Imp.rival.   Quota anno   TFR a fondi   Anticipi
€X.XXX,XX    €XXX,XX      €XX,XX       €XXX,XX      -             -
```

#### Sezione RATEI

| Tipo | Residuo AP | Maturato | Goduto | Saldo | U.M. |
|------|------------|----------|--------|-------|------|
| Ferie | X,XXXXX | X,XXXXX | X,XXXXX | X,XXXXX | GG |
| Permessi | XXX,XXXXX | X,XXXXX | - | XXX,XXXXX | ORE |

#### Sezione TOTALI (Pattern Zucchetti)

**ATTENZIONE**: Il formato Zucchetti usa caratteri speciali:
```
TOTALEsCOMPETENZE 1.754,67      (nota la 's' invece dello spazio)
TOTALEsTRATTENUTE 318,75
NETTOsDELsMESE
1.436,00€
```

**Pattern regex:**
```regex
TOTALE.?COMPETENZE\s+([\d.,]+)
TOTALE.?TRATTENUTE\s+([\d.,]+)
([\d.,]+)\s*€\s*COMUNICAZIONI
```

#### Sezione PAGAMENTO

```
[Nome Banca]
[Filiale]
IBAN[Codice IBAN 27 caratteri]
```

**Pattern IBAN:** `IBAN([A-Z]{2}\d{2}[A-Z0-9]{23})`

---

## 2. MODELLO F24

### 2.1 Struttura del Documento

| Sezione | Contenuto |
|---------|-----------|
| Intestazione | Dati contribuente, domicilio fiscale |
| ERARIO | Ritenute IRPEF, crediti, tributi erariali |
| INPS | Contributi previdenziali |
| REGIONI | Addizionali regionali |
| IMU/TASI | Tributi locali |
| INAIL | Premi assicurativi |
| Totale | Saldo finale da pagare |

### 2.2 Dati Contribuente

**Pattern estrazione:**
```
CODICE FISCALE: Cerca sequenza 11 o 16 cifre (può avere spazi)
Pattern: (\d[\s\d]{10,20}\d) → rimuovi spazi → verifica lunghezza

RAGIONE SOCIALE: Cerca pattern società
Pattern: CERALDI\s+GROUP\s+S\.?R\.?L\.? 
         oppure [A-Z]+\s+(?:S\.R\.L\.|S\.P\.A\.|S\.A\.S\.|S\.N\.C\.)

DOMICILIO FISCALE:
Pattern: ([A-Z]+)\s+([A-Z])\s+([A-Z])\s+(PIAZZA|VIA|CORSO|VIALE.+\d+)
Esempio: "NAPOLI N A PIAZZA NAZIONALE 46"
```

### 2.3 Sezione ERARIO - Codici Tributo

| Codice | Descrizione | Tipo |
|--------|-------------|------|
| 1001 | IRPEF - Ritenute lavoro dipendente | Debito |
| 1701 | Ritenute su redditi lavoro dipendente | Credito/Debito |
| 1704 | Addizionale regionale IRPEF - Acconto | Credito |
| 1713 | Acconto imposta sostitutiva TFR | Debito |
| 6781 | Credito d'imposta bonus | Credito |
| 6099 | Versamento IVA mensile | Debito |
| 6031-6034 | Versamento IVA trimestrale | Debito |

**Pattern estrazione righe Erario:**
```regex
(\d{4})\s+(?:(\d{4})\s+)?(\d{4})\s+([\d.,]*)\s*([\d.,]*)
│         │              │         │          │
│         │              │         │          └── Importo credito
│         │              │         └── Importo debito
│         │              └── Anno riferimento
│         └── Rateazione (opzionale)
└── Codice tributo
```

### 2.4 Sezione INPS

**Struttura:**
```
Codice sede | Causale | Matricola INPS | Periodo da | Periodo a | Importo
    5100       DM10     5124776507       01 2026      01 2026    6.227,00
```

**Pattern estrazione:**
```regex
(\d{4})\s+DM10\s+(\d{10})\s+(\d{2})\s+(\d{4})\s+([\d.,]+)
│                │           │         │         │
│                │           │         │         └── Importo
│                │           │         └── Anno
│                │           └── Mese
│                └── Matricola
└── Codice sede
```

**Causali INPS comuni:**
| Causale | Descrizione |
|---------|-------------|
| DM10 | Contributi obbligatori |
| RC01 | Contributi gestione separata |
| CXX | Contributi colf/badanti |

### 2.5 Sezione REGIONI

**Codici Regione:**
| Codice | Regione |
|--------|---------|
| 01 | Piemonte |
| 02 | Valle d'Aosta |
| 03 | Lombardia |
| 04 | Trentino-Alto Adige |
| 05 | Veneto |
| 06 | Friuli-Venezia Giulia |
| 07 | Liguria |
| 08 | Emilia-Romagna |
| 09 | Toscana |
| 10 | Umbria |
| 11 | Marche |
| 12 | Lazio |
| 13 | Abruzzo |
| 14 | Molise |
| 15 | Campania |
| 16 | Puglia |
| 17 | Basilicata |
| 18 | Calabria |
| 19 | Sicilia |
| 20 | Sardegna |

**Codici Tributo Regioni:**
| Codice | Descrizione |
|--------|-------------|
| 3801 | Addizionale regionale IRPEF - Saldo |
| 3802 | Addizionale regionale IRPEF - Acconto |
| 3803 | IRAP - Saldo |
| 3812 | IRAP - Acconto prima rata |
| 3813 | IRAP - Acconto seconda rata |

**Pattern estrazione:**
```regex
(\d)\s+(\d)\s+(\d{4})\s+(\d{4})\s+(\d{4})\s+([\d.,]+)
│      │      │         │         │         │
│      │      │         │         │         └── Importo
│      │      │         │         └── Anno
│      │      │         └── Rateazione
│      │      └── Codice tributo (38xx per regioni)
│      └── Seconda cifra codice regione
└── Prima cifra codice regione
```

### 2.6 Sezione IMU e Altri Tributi Locali

**Struttura:**
```
Codice ente | Ravv | Immob.var | Acc | Saldo | N.immob | Cod.trib | Anno | Importo
   F839        [ ]     [ ]      [ ]   [X]       1        3918     2025    66,44
```

**Codici Ente (Catastali):**
| Codice | Comune |
|--------|--------|
| F839 | Napoli |
| H501 | Roma |
| F205 | Milano |
| L219 | Torino |

**Pattern estrazione:**
```regex
([A-Z])\s+(\d)\s+(\d)\s+(\d)\s+(\d{4})\s+(\d{4})\s+(\d{4})\s+([\d.,]+)
│         │      │      │      │         │         │         │
│         │      │      │      │         │         │         └── Importo
│         │      │      │      │         │         └── Anno
│         │      │      │      │         └── Rateazione
│         │      │      │      └── Codice tributo
│         │      │      └── Terza cifra codice ente
│         │      └── Seconda cifra
│         └── Prima cifra
└── Lettera codice ente
```

### 2.7 Sezione INAIL

**Struttura:**
```
Codice sede | Codice ditta | C.C. | Numero rif | Causale | Periodo | Importo
   33400       13882560      91      902026        P       01/2026   645,61
```

**Pattern estrazione:**
```regex
(\d{5})\s+(\d{8})\s+(\d{2})\s+(\d{2})(\d{4})\s+P\s+([\d.,]+)
│         │         │         │      │           │
│         │         │         │      │           └── Importo
│         │         │         │      └── Anno
│         │         │         └── Mese
│         │         └── Codice controllo
│         └── Codice ditta
└── Codice sede
```

### 2.8 Calcolo Totale da Pagare

**Formula:**
```
TOTALE = (A - B) + C + (D - E) + F + G

Dove:
A = Totale debiti Erario
B = Totale crediti Erario (compensazione)
C = Totale INPS
D = Totale debiti Regioni
E = Totale crediti Regioni
F = Totale IMU/Altri tributi locali
G = Totale INAIL
```

**Pattern estrazione totale:**
```regex
FIRMA\s+[A-Z]+\s+[A-Z]+\s+([\d.,]+)
```

### 2.9 Azioni Automatiche Post-Import F24

```
1. PARSING
   ├── Estrai tutte le sezioni
   ├── Calcola totali per sezione
   └── Estrai dati pagamento (IBAN, banca)

2. SALVATAGGIO
   ├── Salva in collection "f24_pagamenti"
   ├── Genera ID univoco: f24_{CF}_{scadenza}
   └── Imposta stato: "da_pagare"

3. CREAZIONE SCADENZA
   ├── Crea record in "scadenze"
   ├── Tipo: "F24"
   ├── Data: 16 del mese indicato
   └── Importo: totale da pagare

4. VERIFICA COERENZA
   ├── Confronta INPS con totale cedolini
   ├── Confronta IRPEF con ritenute cedolini
   └── Segnala discrepanze

5. AGGIORNAMENTO DASHBOARD
   ├── Aggiorna widget scadenze
   ├── Aggiorna situazione fiscale
   └── Notifica utente
```

---

## 3. PIANO AMMORTAMENTO MUTUI (BPM)

### 3.1 Struttura del Documento

```
Intestatario: [Ragione Sociale]
Tipo finanziamento: [Es. MUTUO IMPRESA RETAIL]
Importo accordato: €XXX.XXX,XX
Numero delibera: [9 cifre]
Rate residue: [N]
```

### 3.2 Tabella Rate

| N° Rata | Scadenza | Importo Totale | Quota Capitale | Quota Interessi | Stato |
|---------|----------|----------------|----------------|-----------------|-------|
| 1 | DD/MM/YYYY | €X.XXX,XX | €X.XXX,XX | €XXX,XX | Pagata/Da pagare |

**Pattern regex per riga rata:**
```regex
(\d+)\s+(\d{2}/\d{2}/\d{4})\s+([\d.,]+)\s*EUR\s+([\d.,]+)\s*EUR\s+([\d.,]+)\s*EUR\s+(Pagata|Da pagare|Scaduta)
```

---

## 4. REGOLE DI VALIDAZIONE

### 4.1 Codice Fiscale Italiano
- 16 caratteri alfanumerici
- Pattern: `^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$`

### 4.2 IBAN Italiano
- 27 caratteri
- Pattern: `^IT\d{2}[A-Z]\d{22}$`

### 4.3 Importi in Euro
- Formato italiano: `1.234,56` (punto migliaia, virgola decimali)
- Conversione: rimuovi punti, sostituisci virgola con punto

### 4.4 Date
- Formato italiano: `DD/MM/YYYY`
- Formato ISO: `YYYY-MM-DD`

### 4.5 Ore Lavorative
- Formato centesimale: `6,40` = 6 ore e 24 minuti
- Conversione: `6,40 hm` = 6 + (40/100 × 60) = 6h 24m

---

## 5. WORKFLOW DI PARSING

### 5.1 Upload PDF Libro Unico

```
1. Ricevi file PDF
2. Verifica estensione .pdf
3. Apri con pdfplumber
4. Per ogni coppia di pagine (i, i+1):
   a. Pagina i → parse_foglio_presenze()
   b. Pagina i+1 → parse_busta_paga()
5. Aggrega totali
6. Restituisci JSON strutturato
```

### 5.2 Upload PDF F24

```
1. Ricevi file PDF
2. Estrai testo completo
3. Identifica sezioni (ERARIO, INPS, REGIONI, IMU, INAIL)
4. Parsa ogni sezione con pattern specifici
5. Calcola totali
6. Restituisci JSON strutturato
```

### 5.3 Upload PDF Piano Ammortamento

```
1. Ricevi file PDF
2. Estrai intestazione mutuo
3. Cerca pattern rate nella tabella
4. Calcola statistiche (pagato, residuo, prossima scadenza)
5. Restituisci JSON strutturato
```

---

## 6. ENDPOINTS API

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/paghe/parse-libro-unico` | POST | Parsa intero Libro Unico |
| `/api/paghe/parse-libro-unico/dipendente/{n}` | POST | Parsa singolo dipendente |
| `/api/paghe/import-libro-unico` | POST | Importa nel database |
| `/api/paghe/parse-f24` | POST | Parsa Modello F24 |
| `/api/paghe/import-f24` | POST | Importa F24 nel database |
| `/api/mutui/parse-pdf` | POST | Parsa Piano Ammortamento |
| `/api/mutui/import-pdf` | POST | Importa mutuo nel database |

---

## 7. TROUBLESHOOTING

### Problema: Dati mancanti o incompleti
**Causa**: Pattern regex non corrisponde
**Soluzione**: Verificare il testo grezzo con `page.extract_text()` e aggiornare i pattern

### Problema: Filigrana interferisce
**Causa**: Watermark Zucchetti nel PDF
**Soluzione**: Applicare filtro `is_watermark_line()` prima del parsing

### Problema: Importi errati
**Causa**: Formato numero italiano vs inglese
**Soluzione**: Usare `parse_euro_amount()` per la conversione

### Problema: Date non parsate
**Causa**: Formato data diverso
**Soluzione**: Provare entrambi i formati DD/MM/YYYY e YYYY-MM-DD

---

*Ultimo aggiornamento: Febbraio 2026*
*Versione: 1.0*

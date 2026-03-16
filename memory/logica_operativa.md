# Logica Operativa — Ceraldi ERP
> Versione: Marzo 2026 | Lingua: Italiano

---

## INDICE
1. [Architettura Generale](#1-architettura-generale)
2. [Flusso Email → Documenti](#2-flusso-email--documenti)
3. [Fatture XML e Prima Nota Automatica](#3-fatture-xml-e-prima-nota-automatica)
4. [Prima Nota Cassa e Banca](#4-prima-nota-cassa-e-banca)
5. [Corrispettivi e Cassa](#5-corrispettivi-e-cassa)
6. [Dipendenti e Presenze](#6-dipendenti-e-presenze)
7. [Cedolini e Buste Paga](#7-cedolini-e-buste-paga)
8. [Fornitori e Ciclo Passivo](#8-fornitori-e-ciclo-passivo)
9. [Banca ed Estratto Conto](#9-banca-ed-estratto-conto)
10. [Dashboard e Volume d'Affari](#10-dashboard-e-volume-daffari)
11. [Cespiti](#11-cespiti)
12. [Struttura Database](#12-struttura-database)

---

## 1. ARCHITETTURA GENERALE

```
Frontend (React + Vite)  ←→  Backend (FastAPI)  ←→  MongoDB Atlas
       :3000                      :8001               azienda_erp_db
```

- **Frontend**: React 18, Vite, Shadcn UI. Tutte le chiamate API usano
  `REACT_APP_BACKEND_URL` + prefisso `/api/`.
- **Backend**: FastAPI con Motor (driver MongoDB asincrono). Avviato da
  `supervisor` (non modificare porte o comandi di avvio).
- **Database**: MongoDB Atlas. Variabili `MONGO_URL` e `DB_NAME` in
  `backend/.env`. Il DB si chiama `azienda_erp_db`.

---

## 2. FLUSSO EMAIL → DOCUMENTI

### 2.1 Mittenti Autorizzati
- Salvati nella collection `mittenti_email` con i campi:
  - `email` (stringa, indirizzo del mittente)
  - `attivo` (bool)
  - `cerca_per_oggetto` (bool) — se `true`, la ricerca avviene per
    parole chiave invece che per indirizzo FROM
  - `parole_chiave_ricerca` (lista stringhe) — usate solo se
    `cerca_per_oggetto = true`

- API di gestione: `GET/POST/DELETE /api/mittenti`

### 2.2 Download Automatico (ogni ora)
Il servizio `email_monitor_service.py` si avvia con l'applicazione e
ogni ora esegue `sync_email_documents()`:

```
AVVIO APP
  └─ email_monitor_service.start_monitor()
       └─ ogni 3600 secondi:
            └─ sync_email_documents(db, giorni=30)
                  ├─ Legge EMAIL_USER + EMAIL_PASSWORD da .env
                  ├─ Carica mittenti attivi da mittenti_email
                  ├─ Separa: mittenti_from (ricerca FROM)
                  │          mittenti_keyword (ricerca parole chiave)
                  └─ download_documents_from_email(...)
```

### 2.3 Logica di Download (email_document_downloader.py)

```
CONNESSIONE IMAP (Gmail: imap.gmail.com:993 SSL)
  └─ Per ogni mittente FROM:
       └─ Cerca email UNSEEN o recenti (< N giorni) da quell'indirizzo
  └─ Per ogni mittente KEYWORD:
       └─ Cerca email con quelle parole in SUBJECT/BODY
  └─ Ordina per data (più vecchie prima → FIFO)
  └─ Per ogni email trovata:
       ├─ Leggi Message-ID dall'header
       ├─ CONTROLLA email_message_index (de-duplicazione)
       │    ├─ Se Message-ID già presente → SALTA (già scaricata)
       │    └─ Se non presente → procedi
       ├─ Scarica allegati (PDF, XML, P7M, XLSX...)
       ├─ Calcola hash SHA-256 del file
       ├─ Controlla hash in documents_inbox
       │    ├─ Se hash già presente → SALTA (contenuto duplicato)
       │    └─ Se non presente → salva
       ├─ Salva file in MongoDB (documents_inbox)
       ├─ Salva riepilogo in email_riepilogo
       └─ Registra Message-ID in email_message_index
```

### 2.4 De-duplicazione
Due meccanismi indipendenti:

| Meccanismo | Collection | Cosa controlla |
|---|---|---|
| Message-ID | `email_message_index` | Header univoco email |
| Hash contenuto | `documents_inbox.file_hash` | SHA-256 del file binario |

Se uno dei due trova un duplicato, l'email/file viene saltato.

### 2.5 Credenziali Email
Nel file `backend/.env`:
```
EMAIL_USER=ceraldigroupsr@gmail.com
EMAIL_PASSWORD=xxxx xxxx xxxx xxxx   ← App Password Google (16 caratteri)
```
**IMPORTANTE**: Per Gmail occorre un'App Password (non la password
normale). Generarla da: Google Account → Sicurezza →
Verifica in 2 passaggi → Password per le app.

---

## 3. FATTURE XML E PRIMA NOTA AUTOMATICA

### 3.1 Fonte dei dati
- Le fatture XML arrivano via email (allegati `.xml` o `.p7m`)
- Vengono salvate in `documents_inbox`
- Il monitor le processa automaticamente dopo il download

### 3.2 Parsing XML (xml_invoice_processor.py)
```
FILE XML → parse_xml_fattura()
  ├─ Estrae: numero fattura, data, fornitore (P.IVA + nome)
  ├─ Estrae: importo totale, aliquota IVA, tipo documento
  ├─ Estrae: metodo di pagamento (ModalitaPagamento)
  └─ Salva fattura in collection invoices
```

### 3.3 Inserimento Automatico in Prima Nota Banca
Se il metodo di pagamento è: `MP05` (bonifico), `MP19` (SEPA),
`MP08` (carta di credito) o equivalenti banca:

```
METODO = SEPA / Banca / Carta / Bonifico
  └─ registra_pagamento_fattura(fattura, metodo)
       └─ Crea movimento in prima_nota_banca:
            tipo: "uscita"
            categoria: "Pagamento fornitore"
            importo: totale fattura
            source: "fattura_pagata"
```

---

## 4. PRIMA NOTA CASSA E BANCA

### 4.1 Prima Nota Cassa
- **Collection**: `prima_nota_cassa`
- **Fonte dati**: corrispettivi contanti, pagamenti fatture in contanti
- **Campo chiave**: `anno` (intero, es. 2026) + `data` (stringa
  `YYYY-MM-DD`)
- **Query API**: `GET /api/prima-nota/cassa?anno=2026`

**Attenzione**: la query usa un `$or` per trovare sia record con
`anno` esplicit che record con data in range (retrocompatibilità).

### 4.2 Prima Nota Banca
- **Collection**: `prima_nota_banca`
- **Fonte dati**: movimenti bancari, pagamenti fatture, F24, stipendi
- **Query API**: `GET /api/prima-nota/banca?anno=2026`

### 4.3 Sincronizzazione Corrispettivi → Cassa
Endpoint: `POST /api/prima-nota/cassa/sync-corrispettivi?anno=ANNO`

```
CORRISPETTIVI (collection corrispettivi)
  └─ Filtra per data nel range [ANNO-01-01, ANNO-12-31]
  └─ Per ogni corrispettivo con pagato_contanti > 0:
       └─ Crea movimento in prima_nota_cassa:
            tipo: "entrata"
            importo: pagato_contanti   ← SOLO contanti
            categoria: "Corrispettivi"
            anno: estratto dalla data
            source: "sync_corrispettivi"
  └─ I pagamenti elettronici (POS) vanno in Banca, NON qui
```

**Nota**: I pagamenti elettronici (POS) dei corrispettivi sono già in
Prima Nota Banca come "Accredito POS".

### 4.4 Sincronizzazione Fatture Pagate → Prima Nota
Endpoint: `POST /api/prima-nota/cassa/sync-fatture-pagate?anno=ANNO`

Trova fatture con stato `pagata` e crea movimenti in
prima_nota_cassa (se pagamento contanti) o prima_nota_banca
(se pagamento bancario).

---

## 5. CORRISPETTIVI E CASSA

### 5.1 Struttura Corrispettivi
```json
{
  "data": "2026-01-15",
  "pagato_contanti": 949.91,
  "pagato_elettronico": 928.70,
  "totale_giornata": 1878.61,
  "anno": null   ← campo spesso assente; usare data per filtrare
}
```

### 5.2 Volume d'Affari (Dashboard)
Il fatturato viene calcolato **solo dai corrispettivi**
(non dalle fatture passive ricevute, per evitare doppio conteggio).

Formula:
```
Volume d'Affari = SUM(corrispettivi.totale_giornata) per anno/mese
```

---

## 6. DIPENDENTI E PRESENZE

### 6.1 Collections Dipendenti
| Collection | Contenuto |
|---|---|
| `dipendenti` | Anagrafica principale (34 record) |
| `employees` | Copia/alias (31 record) |
| `anagrafica_dipendenti` | Altra copia (28 record) |

**Campo chiave**: `in_carico` (bool) — indica se il dipendente è
attualmente in forza. I dipendenti cessati hanno `in_carico: false`.

### 6.2 Presenze
- **Collection**: `attendance_presenze_calendario` (482 record)
  — presenze individuali per giorno
- **Collection**: `presenze` (20957 record) — storico completo
- **Collection**: `presenze_mensili` (1629 record) — riepiloghi mensili
- **Route frontend**: `/dipendenti/presenze`
- **Componente**: `Attendance.jsx` — calendario mensile con 26 dipendenti

### 6.3 Navigazione HR
Il componente `HRGestionale.jsx` gestisce i tab:
```
/dipendenti/dashboard   → DashboardHR
/dipendenti/anagrafica  → Anagrafica dipendenti
/dipendenti/presenze    → Attendance (calendario)
/dipendenti/ferie       → Ferie e permessi
/dipendenti/paghe       → Buste paga + F24
/dipendenti/veicoli     → Veicoli aziendali
```

**IMPORTANTE**: Il tab Presenze usa un render condizionale nel JSX
(non un early return, che viola le Rules of Hooks di React).

---

## 7. CEDOLINI E BUSTE PAGA

### 7.1 Collections
| Collection | Record | Descrizione |
|---|---|---|
| `cedolini` | 1374 | Cedolini importati da PDF |
| `cedolini_importati` | 2363 | Cedolini da sistema cloud |
| `buste_paga` | 211 | Buste paga elaborate |
| `salari_buste` | 1172 | Dati salari |

### 7.2 Logica Matching
I cedolini vengono associati ai dipendenti tramite corrispondenza
su nome/cognome o codice fiscale. Per circa 8 dipendenti il matching
automatico fallisce (nome non corrispondente esatto).

### 7.3 API
- `GET /api/paghe/buste-paga?anno=2026` — elenco buste paga
- `GET /api/cedolini?anno=2026` — cedolini per anno

---

## 8. FORNITORI E CICLO PASSIVO

### 8.1 Collections
- `suppliers` (328 record) — anagrafica fornitori con P.IVA
- `invoices` (145 record) — fatture ricevute (XML importati)
- `fatture_xml_2026` (181 record) — fatture 2026 raw XML
- `fornitori_preferenze` (25 record) — preferenze per fornitore

### 8.2 Fatture Ricevute
- **Route**: `/fatture-ricevute`
- **Componente**: `ArchivioFattureRicevute.jsx`
- **API**: `GET /api/fatture-ricevute/archivio?anno=2026`
- Le fatture vengono importate da file XML (elettronico italiano SDI)

### 8.3 Metodi di Pagamento Fatture
Codici standard fatturazione elettronica italiana:

| Codice | Metodo | Va in |
|---|---|---|
| MP01 | Contanti | Prima Nota Cassa |
| MP05 | Bonifico bancario | Prima Nota Banca |
| MP08 | Carta di credito | Prima Nota Banca |
| MP19 | SEPA | Prima Nota Banca |
| MP02 | Assegno | Prima Nota Banca |

---

## 9. BANCA ED ESTRATTO CONTO

### 9.1 Collections
- `estratto_conto` (4244 record) — movimenti bancari principali
- `estratto_conto_bpm` (4282 record) — BPM
- `estratto_conto_bnl` (21 record) — BNL
- `prima_nota_banca` (1899 record) — prima nota banca elaborata

### 9.2 Import Estratto Conto
- Supporta import CSV/Excel da varie banche
- `POST /api/bank/import-estratto-conto`
- Logica di deduplicazione per evitare doppio import

### 9.3 Riconciliazione
Il sistema tenta di riconciliare automaticamente i movimenti bancari
con fatture, stipendi e F24 per classificarli correttamente.

---

## 10. DASHBOARD E VOLUME D'AFFARI

### 10.1 KPI Dashboard
| Indicatore | Fonte | Formula |
|---|---|---|
| Volume d'Affari | `corrispettivi` | SUM totale_giornata per anno |
| Costi Fornitore | `invoices` | SUM total_amount per anno |
| Utile Lordo | — | Volume - Costi |
| Saldo Cassa | `prima_nota_cassa` | Entrate - Uscite |
| Saldo Banca | `prima_nota_banca` | Entrate - Uscite |

### 10.2 Contabilità Hub
- Route: `/contabilita-hub`
- Mostra: fatturato, costi, IVA a credito/debito, saldo cassa/banca
- Dati calcolati in tempo reale da aggregazioni MongoDB

---

## 11. CESPITI

- **Collection**: `cespiti` (21 record)
- **Fonte**: estratti dalle righe di fatture XML (beni ammortizzabili)
- **API scan**: `POST /api/cespiti/scan-fatture` — popola la lista
  cespiti leggendo le voci delle fatture ricevute
- **Route**: `/cespiti`

---

## 12. STRUTTURA DATABASE

### Collections Principali

```
azienda_erp_db
├── DIPENDENTI
│   ├── dipendenti (34)          — anagrafica principale
│   ├── employees (31)           — copia operativa
│   ├── cedolini (1374)          — buste paga importate
│   ├── attendance_presenze_calendario (482)
│   └── presenze (20957)         — storico presenze
│
├── CONTABILITÀ
│   ├── prima_nota_cassa (1422)  — cassa (contanti)
│   ├── prima_nota_banca (1899)  — banca (bonifici/POS)
│   ├── corrispettivi (1089)     — incassi giornalieri cassa
│   └── invoices (145)           — fatture ricevute
│
├── FORNITORI
│   ├── suppliers (328)          — anagrafica fornitori
│   ├── fatture_xml_2026 (181)   — XML raw 2026
│   └── scadenziario_fornitori (1052)
│
├── BANCA
│   ├── estratto_conto (4244)    — movimenti bancari
│   ├── estratto_conto_bpm (4282)
│   └── assegni (212)
│
├── EMAIL
│   ├── mittenti_email (16)      — mittenti autorizzati
│   ├── email_message_index (167)— de-duplicazione per Message-ID
│   ├── documents_inbox (5)      — file scaricati in attesa
│   ├── email_download_log (208)
│   └── email_riepilogo (166)
│
├── MAGAZZINO
│   ├── warehouse_inventory (6957)
│   ├── warehouse_movements (4051)
│   └── acquisti_prodotti (15068)
│
└── FISCALE
    ├── f24_unificato (68)        — modelli F24
    ├── calendario_fiscale (148)  — scadenze fiscali
    └── atti_fiscali_email (41)   — atti ricevuti via email
```

---

## NOTE IMPORTANTI

1. **Auto-refresh**: L'applicazione NON usa refresh automatici globali.
   Se una pagina si ricarica da sola, verificare la presenza di
   `setInterval` o `useEffect` con dipendenze mancanti nel componente.

2. **Anno di default**: L'anno corrente (2026) viene letto dal
   selettore in alto a destra. Tutte le query lo usano come filtro.

3. **Autenticazione**: Attualmente disabilitata (nessun login richiesto).

4. **Credenziali Gmail**: Necessarie per il download automatico.
   Stato attuale: da configurare con App Password valida.

5. **Codici documento FE (Fatturazione Elettronica)**:
   - `TD01` = Fattura ordinaria (acquisto → uscita)
   - `TD04` = Nota di credito (rimborso → entrata)
   - `TD24/25/26` = Fattura differita/in acconto (vendita → entrata)

---

*File generato automaticamente dal sistema ERP Ceraldi — Marzo 2026*

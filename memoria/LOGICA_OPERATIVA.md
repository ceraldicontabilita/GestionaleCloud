# Logica Operativa — Ceraldi ERP
> Versione: Aprile 2026 | P.IVA: 04523831214 | DB: Gestionale (MongoDB Atlas)

---

## REGOLE BUSINESS FONDAMENTALI

### Fonti documenti per canale:
- **FATTURE SDI** → arrivano via **PEC Aruba** (`fatturazioneceraldi@pec.it`) o **import manuale XML**. MAI da Gmail.
- **CEDOLINI / BUSTE PAGA** → arrivano via **Gmail** (dal consulente TeamSystem/Zucchetti)
- **F24, ESTRATTI CONTO, VERBALI, QUIETANZE, BONIFICI, CARTELLE** → arrivano via **Gmail**
- **SCHEDE TECNICHE** → via Gmail (allegati PDF da fornitori) o ricerca web

### Scansione Email:
- **Gmail**: scansiona le cartelle configurate — molte contengono documenti organizzati per argomento
- **PEC**: scansiona INBOX + INBOX.lette — supporta P7M firmati digitalmente (OpenSSL + asn1crypto)
- **Fatture da Gmail**: ESCLUSE automaticamente (solo PEC/SDI per le fatture)

---

## INDICE

1. [Architettura Generale](#1-architettura-generale)
2. [Flusso Email → Documenti](#2-flusso-email--documenti)
3. [Fatture XML e Prima Nota](#3-fatture-xml-e-prima-nota)
4. [Prima Nota Cassa e Banca](#4-prima-nota-cassa-e-banca)
5. [Corrispettivi e Cassa](#5-corrispettivi-e-cassa)
6. [Dipendenti e HR](#6-dipendenti-e-hr)
7. [Cedolini e Buste Paga](#7-cedolini-e-buste-paga)
8. [Fornitori e Ciclo Passivo](#8-fornitori-e-ciclo-passivo)
9. [Banca ed Estratto Conto](#9-banca-ed-estratto-conto)
10. [Dashboard e Volume d'Affari](#10-dashboard-e-volume-daffari)
11. [Struttura Database](#11-struttura-database)

---

## 1. ARCHITETTURA GENERALE

```
Frontend (React 18 + Vite)  ←→  Backend (FastAPI + Motor)  ←→  MongoDB Atlas
        :3000 (supervisor)           :8001 (supervisor)          azienda_erp_db
```

- **Frontend**: React 18, Vite. CSS inline ONLY da `lib/utils.js`. NO Tailwind, NO Shadcn.
- **Backend**: FastAPI, Motor (async). Entry: `backend/server.py` → `from app.main import app`.
- **Database**: MongoDB Atlas. Variabili: `MONGO_URL`, `DB_NAME` in `backend/.env`.
- **Auth**: disabilitata (`AUTH_DISABLED=true`) — accesso diretto senza login.

### Variabili d'ambiente (struttura .env)
```
MONGO_URL = mongodb+srv://[USER]:[PASS]@cluster0.vofh7iz.mongodb.net/
DB_NAME   = azienda_erp_db

# Gmail
IMAP_USER     = ceraldigroupsrl@gmail.com
IMAP_PASSWORD = [APP_PASSWORD_GOOGLE]

# PEC Aruba
ARUBA_PEC_HOST = imaps.pec.aruba.it
ARUBA_PEC_USER = fatturazioneceraldi@pec.it
ARUBA_PEC_PASSWORD = [PASSWORD_PEC]

# OpenAPI Camera di Commercio
OPENAPI_COMPANY_TOKEN = [TOKEN]
```
> ⚠️ Le credenziali reali sono nel file `backend/.env` — NON commitarle nel repo.

---

## 2. FLUSSO EMAIL → DOCUMENTI

### 2.1 Mittenti Autorizzati (`mittenti_email`)

| Canale | Pattern | Tipo Documento |
|---|---|---|
| pec | @pec.fatturapa.it | fattura_xml |
| pec | sdi@pec.fatturapa.it | fattura_xml |
| gmail | f.ferrantini@... | cedolino |
| gmail | rosaria.marotta@... | cedolino |
| gmail | partenopay@... | pagopa |
| gmail | inpscomunica@... | inps |
| gmail | notifica.acc.campania@... | cartella_esattoriale |
| gmail | no_reply@agenziariscossione | cartella_esattoriale |
| gmail | auto_napoli@massivo.pec.inail | inail |
| gmail | assistenza@paypal.it | paypal |
| gmail | noreply-checkout@ricevute.pagopa | pagopa |

**Regola match**: `if pattern in from_addr.lower()` (contenimento stringa)
**Builtin**: non eliminabili, solo disattivabili

### 2.2 API Mittenti
```
GET    /api/email-download/mittenti                    → lista completa
POST   /api/email-download/mittenti                    → aggiunge mittente
PUT    /api/email-download/mittenti/{id}               → aggiorna
DELETE /api/email-download/mittenti/{id}               → elimina (builtin: BLOCCA)
```

### 2.3 Routing per tipo_documento

| tipo_documento | Azione |
|---|---|
| `fattura_xml` | Parser XML → `invoices` |
| `cedolino` | Salva PDF in `documents_inbox` (nessun parser auto) |
| `pagopa` | Documento generico in `documents_inbox`, categoria=pagopa |
| `inps` | Documento generico, categoria=inps |
| `inail` | Documento generico, categoria=inail |
| `paypal` | Documento generico, categoria=paypal |
| `cartella_esattoriale` | Documento generico + alert urgente |

### 2.4 Download PEC (Aruba)
- Endpoint: `POST /api/email-download/pec/download-fatture-sync?since_days=365`
- Esecuzione: `asyncio.to_thread()` — NON blocca il server
- 54 email SDI trovate, 38 fatture importate (Apr 2026)
- Deduplicazione: `xml_hash` (MD5)

### 2.5 Download Gmail
- Endpoint: `POST /api/email-download/sync-email-now`
- Scheduler: ogni 50 minuti (APScheduler)
- Import cedolini: `POST /api/cedolini/import-gmail?since_days=180`

---

## 3. FATTURE XML E PRIMA NOTA

### 3.1 Fatture SDI (ciclo passivo)
- Arrivano via Aruba PEC come `.xml` o `.p7m`
- Salvate in `documents_inbox`, processate da `xml_invoice_processor.py`
- Salvate in `invoices` (224 record)

### 3.2 Inserimento Prima Nota Banca
Se metodo pagamento = `MP05` (bonifico), `MP19` (SEPA), `MP08` (carta):
```
fattura pagata → prima_nota_banca: tipo "uscita", categoria "Pagamento fornitore"
```

### 3.3 Codici Tipo Documento FE

| Codice | Tipo | Direzione |
|---|---|---|
| TD01 | Fattura ordinaria | acquisto → uscita |
| TD04 | Nota di credito | rimborso → entrata |
| TD24/25 | Fattura differita | vendita → entrata |
| TD16 | Autofattura (reverse charge) | integrazione |

### 3.4 Codici Metodo Pagamento FE

| Codice | Metodo | Prima Nota |
|---|---|---|
| MP01 | Contanti | Cassa |
| MP05 | Bonifico | Banca |
| MP08 | Carta di credito | Banca |
| MP19 | SEPA Credit Transfer | Banca |
| MP02 | Assegno | Banca |

---

## 4. PRIMA NOTA CASSA E BANCA

### 4.1 Prima Nota Cassa (`prima_nota_cassa`, 2.132 record)
- Fonte: corrispettivi contanti, fatture pagate in contanti
- Filtro: `anno` (int) + `data` (YYYY-MM-DD)
- API: `GET /api/prima-nota/cassa?anno=2026`
- Sync: `POST /api/prima-nota/cassa/sync-corrispettivi?anno=2026`

### 4.2 Prima Nota Banca (`prima_nota_banca`, 1.869 record)
- Fonte: movimenti bancari, F24, stipendi, incassi POS
- API: `GET /api/prima-nota/banca?anno=2026`

### 4.3 Regola POS
- Pagamenti elettronici (POS) → Prima Nota **Banca** (NON cassa)
- Contanti → Prima Nota **Cassa**

### 4.4 Saldi 2026 (aggiornati Marzo 2026)
- Entrate 2026: €225.799,77
- Uscite 2026: €220.976,10
- Saldo 2026: €4.823,67
- Riporto anni prec.: €1.206.190,67

---

## 5. CORRISPETTIVI E CASSA

### 5.1 Struttura (`corrispettivi`, 1.114 record)
```json
{
  "data": "2026-01-15",
  "pagato_contanti": 949.91,
  "pagato_elettronico": 928.70,
  "totale_giornata": 1878.61
}
```
**Nota**: il campo `anno` può essere assente — filtrare sempre per range di `data`.

### 5.2 Volume d'Affari
```
Fatturato = SUM(corrispettivi.totale_giornata) per anno
```
> ⚠️ **REGOLA CRITICA**: NON usare le fatture ricevute per il volume d'affari. Quelle sono COSTI.

---

## 6. DIPENDENTI E HR

### 6.1 Collections HR

| Collection | Record | Uso |
|---|---|---|
| `dipendenti` | 34 | Anagrafica principale — **USARE QUESTA** |
| `employees` | 31 | Copia per presenze batch (non modificare) |

Campo chiave: `in_carico` (bool) — dipendenti attivi.

### 6.2 Route HR (struttura Aprile 2026)
```
/dipendenti          → HRDipendenti.jsx   (anagrafica + dettaglio)
/dipendenti/cedolini → HRCedolini.jsx     (buste paga + import Gmail)
/dipendenti/presenze → HRPresenze.jsx     (calendario presenze)
/dipendenti/tfr      → HRTFR.jsx          (gestione TFR)
```

### 6.3 Presenze

| Collection | Record | Contenuto |
|---|---|---|
| `attendance_presenze_calendario` | — | Presenze giornaliere calendario |
| `presenze` | 20.989 | Storico completo |
| `presenze_mensili` | 1.629 | Riepiloghi mensili |

### 6.4 API HR Principali
```
GET  /api/dipendenti                         → lista (34)
GET  /api/dipendenti/{id}                    → dettaglio
PUT  /api/dipendenti/{id}                    → aggiorna anagrafica
GET  /api/cedolini?anno=2026                 → cedolini per anno
GET  /api/cedolini/dipendente/{id}?anno=     → cedolini dipendente
POST /api/cedolini/import-gmail?since_days=  → importa da Gmail
GET  /api/tfr/acconti/{id}                   → acconti TFR
GET  /api/paghe/buste-paga?anno=             → libro unico
GET  /api/paghe/distinte-f24?anno=           → distinte F24
```

---

## 7. CEDOLINI E BUSTE PAGA

### 7.1 Collections

| Collection | Record | Descrizione |
|---|---|---|
| `cedolini` | 1.658 | Principale (Gmail + PDF + libro unico) |
| `cedolini_importati` | 2.363 | Sistema cloud Zucchetti |

### 7.2 Schema Cedolino
```json
{
  "id": "uuid",
  "dipendente_id": "uuid (→ dipendenti.id)",
  "dipendente_nome": "Nome Cognome",
  "anno": 2026,
  "mese": 1,
  "lordo": 1800.00,
  "netto": 1406.00,
  "inps_azienda": 420.00,
  "tfr": 135.00,
  "costo_azienda": 2355.00,
  "source": "gmail | cedolino_v2 | document_ai | pdf_upload",
  "file_hash": "md5 (solo source=gmail)",
  "filename": "Busta paga - Mario Rossi - Gennaio 2026.pdf"
}
```

### 7.3 Formati Cedolino Supportati
1. **CSC Napoli** (fino al 2018)
2. **Zucchetti classico** (2018–2022)
3. **Zucchetti nuovo** (dal 2022 — separatore `s`)
4. **Teamsystem**

### 7.4 Import Gmail
- 271 cedolini con `source=gmail` già presenti (storico completo)
- Parsing filename: `"Busta paga - {Nome} - {Mese} {Anno}.pdf"` → `mese=4, anno=2026`
- Deduplicazione: `db["cedolini"].find_one({"file_hash": hash})`

---

## 8. FORNITORI E CICLO PASSIVO

### 8.1 Collections

| Collection | Record | Note |
|---|---|---|
| `suppliers` | 328 | Usata dal modulo principale (CollectionsModule.SUPPLIERS) |
| `fornitori` | 168 | Variante italiana (usata da alcuni router) |
| `invoices` | 224 | Fatture passive ricevute |
| `scadenziario_fornitori` | 1.052 | Scadenze pagamento |

> **Attenzione**: `suppliers` e `fornitori` sono due collection distinte con dati parzialmente diversi. Il codice usa `suppliers` come canonica per il modulo principale. Vedi debito tecnico in `DEBITO_TECNICO.md`.

### 8.2 Classificazione Automatica Fatture

| Pattern Fornitore | Categoria | Deducibilità |
|---|---|---|
| Enel, Edison, A2A | Energia | 100% |
| TIM, Vodafone | Telefonia | 80% (IVA 50%) |
| ARVAL, Leasys, ALD | Noleggio Auto | 20% su max €3.615 |
| Q8, Esso | Carburante | 20% (IVA 40%) |
| BRT, DHL | Trasporti | 100% |
| Studio..., Consulenze | Consulenze | 100% |

---

## 9. BANCA ED ESTRATTO CONTO

### 9.1 Collections

| Collection | Record | Contenuto |
|---|---|---|
| `estratto_conto_movimenti` | 4.468 | Movimenti bancari (canonica) |
| `assegni` | 212 | Gestione assegni |
| `prima_nota_banca` | 1.869 | Prima nota banca |

### 9.2 Distribuzione Movimenti per Anno
- 2026 (gen–apr): ~470 record
- 2025 (completo): ~3.128 record
- 2024: ~881 record

### 9.3 Saldi (Marzo 2026)
- Saldo 2026: €4.823,67
- Riporto anni precedenti: €1.206.190,67
- Saldo cumulativo: ~€1.211.014

### 9.4 Import Estratto Conto
- `POST /api/bank/import-estratto-conto` — CSV BPM, separatore `;`, UTF-8-BOM
- Deduplicazione: `data + importo + descrizione_originale`
- Performance: ~2.5s per file completo (ottimizzato con bulk insert)

### 9.5 Riconciliazione Bancaria

| Tipo | Criteri Match |
|---|---|
| Stipendi | IBAN + importo esatto + data ±5gg |
| F24 | Importo + data 16 ±3gg + "F24"/"ERARIO" in descrizione |
| Rate Mutuo | Importo ±€1 + data ±7gg |
| POS | Importo ±€5 + data attesa (+1/+3gg lavorativi) |
| Fatture | Importo ±2% + fornitore nella descrizione |

**Regola POS**: Lun–Gio → accredito giorno lavorativo successivo. Ven–Dom → accredito lunedì.

---

## 10. DASHBOARD E VOLUME D'AFFARI

### 10.1 KPI Principali

| Indicatore | Fonte | Formula |
|---|---|---|
| Volume d'Affari | `corrispettivi` | SUM(totale_giornata) |
| Costi Fornitore | `invoices` | SUM(total_amount) |
| Utile Lordo | — | Volume − Costi |
| Saldo Cassa | `prima_nota_cassa` | Entrate − Uscite |
| Saldo Banca | `prima_nota_banca` | Entrate − Uscite |

### 10.2 Route Dashboard
- `/` o `/dashboard` → `DashboardHub.jsx`
- `/contabilita-hub` → `ContabilitaHub.jsx`

---

## 11. STRUTTURA DATABASE

```
azienda_erp_db (MongoDB Atlas — Aprile 2026)
│
├── HR
│   ├── dipendenti (34)              ← CANONICA: anagrafica dipendenti
│   ├── employees (31)               ← copia (solo presenze batch)
│   ├── cedolini (1.658)             ← buste paga (Gmail + PDF + libro unico)
│   ├── cedolini_importati (2.363)   ← sistema cloud Zucchetti
│   ├── presenze (20.989)            ← storico presenze
│   └── presenze_mensili (1.629)     ← riepiloghi mensili
│
├── CONTABILITA
│   ├── prima_nota_cassa (2.132)
│   ├── prima_nota_banca (1.869)
│   ├── corrispettivi (1.114)
│   └── invoices (224)               ← fatture passive SDI
│
├── FORNITORI
│   ├── suppliers (328)              ← canonica per modulo principale
│   ├── fornitori (168)              ← variante italiana
│   └── scadenziario_fornitori (1.052)
│
├── BANCA
│   ├── estratto_conto_movimenti (4.468)
│   └── assegni (212)
│
├── EMAIL
│   ├── mittenti_email (16)
│   ├── email_message_index (278)
│   └── documents_inbox (91)
│
├── MAGAZZINO
│   ├── warehouse_inventory (6.885)
│   └── acquisti_prodotti (15.070)
│
└── FISCALE
    ├── f24_unificato (68)
    └── scadenze (15)
```

---

## NOTE CRITICHE PER SVILUPPO

1. **IMAP sempre in thread**: `await asyncio.to_thread(funzione_sync_imap, ...)`
2. **Collection dipendenti**: usare `dipendenti` (34 record), NON `employees`
3. **Anno corrispettivi**: filtrare per range di `data` (il campo `anno` può mancare)
4. **Design**: CSS inline da `lib/utils.js` per pagine gestionali. NO Tailwind, NO Shadcn
5. **`_id` MongoDB**: escludere sempre con `{"_id": 0}` o via Pydantic
6. **Auth**: disabilitata (`AUTH_DISABLED=true`)
7. **server.py**: NON cancellare — punto di avvio uvicorn via Supervisor
8. **Collection canonica fornitori**: `suppliers` per il modulo principale

---

*Aggiornato: Aprile 2026*

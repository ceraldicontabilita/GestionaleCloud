# Logica Operativa — Ceraldi ERP
> Versione: Aprile 2026 | P.IVA: 04523831214 | DB: Gestionale (MongoDB Atlas)

---

## REGOLE BUSINESS FONDAMENTALI

### Fonti documenti:
- **FATTURE** → arrivano SOLO via **PEC Aruba** (`fatturazioneceraldi@pec.it`) o **import manuale XML**. MAI da Gmail.
- **CEDOLINI / BUSTE PAGA** → arrivano via **Gmail** (dal consulente TeamSystem)
- **F24, ESTRATTI CONTO, VERBALI, QUIETANZE, BONIFICI, CARTELLE ESATTORIALI** → arrivano via **Gmail** (da vari mittenti)
- **SCHEDE TECNICHE** → via Gmail o ricerca web

### Scansione Email:
- **Gmail**: scansiona TUTTE le 409+ cartelle (non solo INBOX) — molte contengono documenti organizzati per argomento
- **PEC**: scansiona INBOX + INBOX.lette — supporta P7M firmati digitalmente (decoder OpenSSL + asn1crypto)
- **Fatture da Gmail**: vengono ESCLUSE automaticamente (regola business)

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
11. [Cucina / Food Cost](#11-cucina--food-cost)
12. [Struttura Database](#12-struttura-database)

---

## 1. ARCHITETTURA GENERALE

```
Frontend (React 18 + Vite)  ←→  Backend (FastAPI + Motor)  ←→  MongoDB Atlas
        :3000 (supervisor)           :8001 (supervisor)          azienda_erp_db
```

- **Frontend**: React 18, Vite. CSS inline ONLY da `lib/utils.js`. NO Tailwind, NO Shadcn per le pagine gestionali.
- **Backend**: FastAPI, Motor (driver MongoDB asincrono). Entry point: `backend/server.py` → `from app.main import app`.
- **Database**: MongoDB Atlas. Variabili: `MONGO_URL`, `DB_NAME` in `backend/.env`.
- **Avvio**: Supervisor. NON modificare porte. Restart solo per modifiche .env o dipendenze.

### Credenziali .env (Aprile 2026)
```
MONGO_URL = mongodb+srv://Ceraldidatabase:Accesso1974.@cluster0.vofh7iz.mongodb.net/
DB_NAME   = azienda_erp_db

# Gmail
IMAP_USER     = ceraldigroupsrl@gmail.com
IMAP_PASSWORD = nugg fttp swvx djqd   ← App Password Google (FUNZIONANTE)

# Aruba PEC (Fatturazione SDI)
ARUBA_PEC_HOST = imaps.pec.aruba.it
ARUBA_PEC_USER = fatturazioneceraldi@pec.it
ARUBA_PEC_PASSWORD = L)9*kd5+78]?%LmF
```

---

## 2. FLUSSO EMAIL → DOCUMENTI

### 2.1 Mittenti Autorizzati (`mittenti_email`, 11 record — Aprile 2026)

| Canale | Pattern | Tipo Documento | Builtin |
|---|---|---|---|
| pec | @pec.fatturapa.it | fattura_xml | ✓ |
| pec | sdi@pec.fatturapa.it | fattura_xml | ✓ |
| gmail | f.ferrantini@cedolino | cedolino | ✓ |
| gmail | rosaria.marotta@cedolino | cedolino | ✓ |
| gmail | partenopay@ext.comune.napoli.it | pagopa | ✓ |
| gmail | inpscomunica@postacert.inps.gov.it | inps | ✓ |
| gmail | notifica.acc.campania@pec.agenziariscossione.gov.it | cartella_esattoriale | ✓ |
| gmail | no_reply@agenziariscossione.gov.it | cartella_esattoriale | ✓ |
| gmail | auto_napoli@massivo.pec.inail.it | inail | ✓ |
| gmail | assistenza@paypal.it | paypal | ✓ |
| gmail | noreply-checkout@ricevute.pagopa.it | pagopa | ✓ |

**Regola match**: `if pattern in from_addr.lower()` (contenimento stringa)
**Builtin**: non eliminabili, solo disattivabili

### 2.2 API Mittenti
```
GET    /api/email-download/mittenti                                  → lista completa (pec + gmail)
GET    /api/email-download/mittenti/check?from_addr=...&canale=pec  → check attendibilità
POST   /api/email-download/mittenti                                  → aggiunge mittente custom
PUT    /api/email-download/mittenti/{id}                            → aggiorna (builtin: solo attivo/descrizione)
DELETE /api/email-download/mittenti/{id}                            → elimina (builtin: BLOCCA)
```

### 2.3 Routing per tipo_documento
| tipo_documento | Azione |
|---|---|
| fattura_xml | Parser XML → `invoices` |
| cedolino | Salva PDF in `documents_inbox` (no parser auto) |
| pagopa | Documento generico in `documents_inbox`, categoria=pagopa |
| inps | Documento generico, categoria=inps |
| inail | Documento generico, categoria=inail |
| paypal | Documento generico, categoria=paypal |
| cartella_esattoriale | Documento generico + alert |

### 2.4 Download PEC (Aruba)
- Endpoint sincrono: `POST /api/email-download/pec/download-fatture-sync?since_days=365`
- Funzione IMAP: `_pec_fetch_xml_sync()` in thread (`asyncio.to_thread()`)
- 54 email SDI trovate, 38 fatture importate (Apr 2026)
- Deduplicazione via `xml_hash` (MD5)

### 2.5 Download Gmail (Monitor)
- Endpoint: `POST /api/email-download/sync-email-now`
- `sync_email_documents()` in `email_monitor_service.py`
- Pattern matching su mittenti canale=gmail
- Import cedolini: `POST /api/cedolini/import-gmail?since_days=180`

---

## 3. FATTURE XML E PRIMA NOTA

### 3.1 Fatture SDI (ciclo passivo)
- Arrivano via Aruba PEC come allegati `.xml` o `.p7m`
- Salvate in `documents_inbox`, processate da `xml_invoice_processor.py`
- Salvate in `invoices` (224 record)

### 3.2 Inserimento Automatico Prima Nota Banca
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

### 3.4 Codici Pagamento FE
| Codice | Metodo | Prima Nota |
|---|---|---|
| MP01 | Contanti | Cassa |
| MP05 | Bonifico | Banca |
| MP08 | Carta | Banca |
| MP19 | SEPA | Banca |
| MP02 | Assegno | Banca |

---

## 4. PRIMA NOTA CASSA E BANCA

### 4.1 Prima Nota Cassa (`prima_nota_cassa`, 2132 record)
- Fonte: corrispettivi contanti, fatture pagate in contanti
- Filtro: `anno` (int) + `data` (YYYY-MM-DD)
- API: `GET /api/prima-nota/cassa?anno=2026`
- Sync corrispettivi: `POST /api/prima-nota/cassa/sync-corrispettivi?anno=2026`

### 4.2 Prima Nota Banca (`prima_nota_banca`, 1869 record)
- Fonte: movimenti bancari, F24, stipendi, incassi POS
- API: `GET /api/prima-nota/banca?anno=2026`

### 4.3 Regola POS
- Pagamenti elettronici (POS) → Prima Nota **Banca** (NON cassa)
- Contanti → Prima Nota **Cassa**

---

## 5. CORRISPETTIVI E CASSA

### 5.1 Struttura (`corrispettivi`, 1114 record)
```json
{
  "data": "2026-01-15",
  "pagato_contanti": 949.91,
  "pagato_elettronico": 928.70,
  "totale_giornata": 1878.61
}
```
**Nota**: campo `anno` spesso assente — filtrare sempre per range di `data`.

### 5.2 Volume d'Affari
```
Fatturato = SUM(corrispettivi.totale_giornata) per anno
```
NON usare le fatture ricevute (sarebbero costi, non ricavi).

---

## 6. DIPENDENTI E HR

### 6.1 Collections
| Collection | Record | Uso |
|---|---|---|
| `dipendenti` | 34 | Anagrafica principale — USARE QUESTA |
| `employees` | 31 | Copia (solo per presenze batch) |

Campo chiave: `in_carico` (bool) — dipendenti attivi.

### 6.2 Routing HR (Apr 2026 — nuova struttura)
```
/dipendenti          → HRDipendenti.jsx   (anagrafica + dettaglio)
/dipendenti/cedolini → HRCedolini.jsx     (buste paga + import Gmail)
/dipendenti/presenze → HRPresenze.jsx     (calendario presenze)
/dipendenti/tfr      → HRTFR.jsx          (gestione TFR)
```

### 6.3 Presenze
- `attendance_presenze_calendario`: presenze giornaliere
- `presenze` (20989): storico completo
- `presenze_mensili` (1629): riepiloghi mensili
- API: `GET /api/attendance/ore-lavorate/{id}?mese=&anno=`

### 6.4 API HR Principali
```
GET  /api/dipendenti                         → lista (34)
GET  /api/dipendenti/{id}                    → dettaglio
PUT  /api/dipendenti/{id}                    → aggiorna anagrafica
GET  /api/cedolini?anno=2026                 → cedolini per anno
GET  /api/cedolini/dipendente/{id}?anno=     → cedolini dipendente
POST /api/cedolini/import-gmail?since_days=  → importa da Gmail
GET  /api/tfr/acconti/{id}                   → acconti TFR
GET  /api/paghe/buste-paga?anno=             → buste paga (libro unico)
GET  /api/paghe/distinte-f24?anno=           → distinte F24
```

---

## 7. CEDOLINI E BUSTE PAGA

### 7.1 Collections
| Collection | Record | Descrizione |
|---|---|---|
| `cedolini` | 1658 | Principale — include Gmail + PDF + libro unico |
| `cedolini_importati` | 2363 | Sistema cloud Zucchetti |

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
  "source": "gmail | cedolino_v2 | document_ai | pdf_upload",
  "file_hash": "md5 (solo source=gmail)",
  "filename": "Busta paga - Nome - Gennaio 2026.pdf"
}
```

### 7.3 Import Gmail
- 271 cedolini con `source=gmail` e `file_hash` già presenti (storico)
- Parsing mese/anno da filename: "Busta paga - {Nome} - {Mese} {Anno}.pdf"
- Deduplicazione: `db["cedolini"].find_one({"file_hash": hash})`

---

## 8. FORNITORI E CICLO PASSIVO

### 8.1 Collections
| Collection | Record |
|---|---|
| `suppliers` | 328 |
| `invoices` | 224 |
| `scadenziario_fornitori` | 1052 |

### 8.2 Classificazione Automatica Fatture
| Pattern Fornitore | Categoria | Deducibilità |
|---|---|---|
| Enel, Edison, A2A | Energia | 100% |
| TIM, Vodafone | Telefonia | 80% (IVA 50%) |
| ARVAL, Leasys | Noleggio Auto | 20% su max €3.615 |
| Q8, Esso | Carburante | 20% (IVA 40%) |
| BRT, DHL | Trasporti | 100% |

---

## 9. BANCA ED ESTRATTO CONTO

### 9.1 Collections
| Collection | Record |
|---|---|
| `estratto_conto_movimenti` | 4468 |
| `assegni` | 212 |
| `prima_nota_banca` | 1869 |

### 9.2 Distribuzione Movimenti per Anno
- 2026 (gen-apr): ~470 record
- 2025 (completo): ~3.128 record
- 2024: ~881 record

### 9.3 Saldi (aggiornati Mar 2026)
- Saldo anno 2026: €4.823,67
- Riporto anni precedenti: €1.206.190,67
- Saldo cumulativo: ~€1.211.014

### 9.4 Import Estratto Conto
- `POST /api/bank/import-estratto-conto` — CSV BPM, separatore `;`, encoding UTF-8-BOM
- Deduplicazione: `data + importo + descrizione_originale`

---

## 10. DASHBOARD E VOLUME D'AFFARI

### 10.1 KPI
| Indicatore | Fonte | Formula |
|---|---|---|
| Volume d'Affari | `corrispettivi` | SUM(totale_giornata) |
| Costi Fornitore | `invoices` | SUM(total_amount) |
| Utile Lordo | — | Volume − Costi |
| Saldo Cassa | `prima_nota_cassa` | Entrate − Uscite |
| Saldo Banca | `prima_nota_banca` | Entrate − Uscite |

### 10.2 Route Dashboard
- `/` o `/dashboard` → `DashboardHub.jsx`
- `/contabilita-hub` → ContabilitaHub (CE, IVA, saldi)

---

## 11. NOTE SUI FILE MEMORY OBSOLETI

### 11.1 Cucina / Food Cost — RIMOSSO (Aprile 2026)
Il modulo Cucina è stato eliminato completamente (frontend + backend).
L'app è esclusivamente un sistema di **contabilità e gestione ERP**.
- Router backend `/api/cucina/*` → **ELIMINATI**
- Pagine frontend CucinaHub, RicettarioAdmin, FoodCostAdmin → **ELIMINATE**
- Collections `ricette`, `prodotti_vendita` → ancora nel DB ma non più usate

### 11.2 Collection Canonica Fornitori
- `fornitori` (168 doc) → collection canonica usata da `suppliers_module` (`Collections.SUPPLIERS = "fornitori"`)
- `suppliers` (53 doc) → collection NON usata dall'app principale (residuo sessioni precedenti)
- **Regola**: tutti i router che leggono/scrivono dati fornitori usano `db["fornitori"]`

---

## 12. STRUTTURA DATABASE

```
azienda_erp_db (MongoDB Atlas — Aprile 2026)
├── HR
│   ├── dipendenti (34)              ← anagrafica principale
│   ├── employees (31)               ← copia (uso presenze)
│   ├── cedolini (1658)              ← buste paga (include Gmail)
│   ├── cedolini_importati (2363)    ← sistema Zucchetti
│   ├── presenze (20989)             ← storico presenze
│   └── presenze_mensili (1629)
│
├── CONTABILITA
│   ├── prima_nota_cassa (2132)
│   ├── prima_nota_banca (1869)
│   ├── corrispettivi (1114)
│   └── invoices (224)
│
├── FORNITORI
│   ├── suppliers (328)
│   └── scadenziario_fornitori (1052)
│
├── BANCA
│   ├── estratto_conto_movimenti (4468)
│   └── assegni (212)
│
├── EMAIL
│   ├── mittenti_email (16)
│   ├── email_message_index (278)
│   └── documents_inbox (91)
│
├── MAGAZZINO
│   ├── warehouse_inventory (6885)
│   └── acquisti_prodotti (15070)
│
├── CUCINA
│   ├── ricette (207)
│   └── prodotti_vendita (565)
│
└── FISCALE
    ├── f24_unificato (68)
    └── scadenze (15)
```

---

## NOTE CRITICHE

1. **IMAP sempre in thread**: `await asyncio.to_thread(funzione_sync_imap, ...)`
2. **Collection dipendenti**: usare `dipendenti` (34 record), NON `employees`
3. **Anno**: filtrare sempre per range di `data` nei corrispettivi (campo `anno` può mancare)
4. **Design**: CSS inline da `lib/utils.js` ONLY per pagine gestionali. NO Tailwind, NO Shadcn
5. **_id MongoDB**: escludere sempre con `{"_id": 0}` nelle query o usare modelli Pydantic
6. **Auth**: disabilitata (`AUTH_DISABLED=true`)
7. **server.py**: NON cancellare — è il punto di avvio per uvicorn via supervisor

*Aggiornato: Aprile 2026*

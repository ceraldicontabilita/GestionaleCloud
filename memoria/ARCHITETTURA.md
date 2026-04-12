# Architettura — Ceraldi ERP
> Aggiornato: Aprile 2026 | Stack: FastAPI + React + MongoDB Atlas

---

## Stack Tecnologico

| Layer | Tecnologia | Note |
|---|---|---|
| Backend | Python 3.x + FastAPI 0.110.1 | Entry point: `backend/server.py` |
| ORM / DB driver | Motor 3.3.1 (async) + PyMongo 4.5.0 | MongoDB asincrono |
| Frontend | React 18 + Vite | Porta 3000 (supervisor) |
| Database | MongoDB Atlas | DB: `Gestionale` |
| Scheduler | APScheduler | Task automatici: PEC, Gmail, F24 |
| Auth | JWT (pyjwt + bcrypt + passlib) | **DISABILITATA** (`AUTH_DISABLED=true`) |
| Email | IMAPClient (sincrono in thread) | Gmail + Aruba PEC |
| AI | Claude API (via OpenClaw/Emergent) | Per agenti e ricerca web |

---

## Struttura Directory

```
ceraldi-erp-v2/
├── backend/
│   └── server.py              ← ENTRY POINT — NON eliminare (Supervisor/uvicorn)
│
├── app/
│   ├── main.py                ← Registra tutti i router (~75 router)
│   ├── config.py              ← Configurazione app
│   ├── database.py            ← Database.get_db(), Database.connect_db()
│   ├── scheduler.py           ← Task automatici (APScheduler)
│   │
│   ├── agents/                ← Agenti AI autonomi
│   │   ├── fiscale_sentinella.py   → FiscaleSentinella (avvisi, cartelle, F24)
│   │   ├── hr_guardiano.py         → HRGuardiano (dimissioni, ferie, contratti)
│   │   ├── learning_brain.py       → LearningCervello (classificazione, pattern)
│   │   ├── orchestrator.py         → Orchestratore multi-agente
│   │   └── notifier.py             → Notifiche e WebSocket
│   │
│   ├── config/
│   │   └── azienda.py         ← Dati azienda Ceraldi (P.IVA, ragione sociale)
│   │
│   ├── constants/
│   │   └── codici_tributo_f24.py   ← Codici tributo F24 (1001, 6001, ecc.)
│   │
│   ├── core/
│   │   ├── event_bus.py       ← Event Bus centrale (pubblica/ascolta eventi)
│   │   └── handlers_registry.py ← Registro handler per tipo evento
│   │
│   ├── database/
│   │   └── collections.py     ← Nomi collection MongoDB (SOURCE OF TRUTH)
│   │
│   ├── exceptions/
│   │   └── custom_exceptions.py ← Eccezioni personalizzate
│   │
│   ├── handlers/              ← Handler per eventi del Bus
│   │   ├── corrispettivi.py
│   │   ├── estratto_conto.py
│   │   ├── fornitore.py
│   │   ├── learning.py
│   │   ├── magazzino.py
│   │   ├── notifiche.py
│   │   ├── prima_nota.py
│   │   ├── ricette.py
│   │   ├── scadenziario.py
│   │   └── tfr.py
│   │
│   ├── middleware/
│   │   ├── authentication.py  ← JWT middleware (disabilitato)
│   │   ├── error_handler.py   ← Global error handler
│   │   └── performance.py     ← Logging performance
│   │
│   ├── models/                ← Modelli Pydantic
│   │   ├── accounting_advanced.py
│   │   ├── bank.py
│   │   ├── cash.py
│   │   ├── employee.py
│   │   ├── invoice.py
│   │   ├── supplier.py
│   │   ├── user.py
│   │   └── warehouse.py
│   │
│   ├── parsers/               ← Parser documenti
│   │   ├── busta_paga_multi_template.py  ← 4 formati cedolini
│   │   ├── corrispettivi_parser.py       ← XML corrispettivi RT
│   │   ├── estratto_conto_bnl_parser.py  ← CSV/PDF BNL
│   │   ├── estratto_conto_nexi_parser.py ← Estratto Nexi POS
│   │   ├── fattura_elettronica_parser.py ← XML FatturaPA SDI
│   │   └── payslip_parser_v2.py          ← Parser cedolini v2
│   │
│   ├── repositories/          ← Layer accesso dati
│   │
│   ├── routers/               ← Tutti gli endpoint API
│   │   ├── accounting/        → Prima Nota, Bilancio, Piano Conti, IVA
│   │   ├── bank/              → Estratto conto, riconciliazione, bonifici
│   │   ├── attendance_module/ → Presenze e giustificativi
│   │   ├── bonifici_module/   → Gestione bonifici
│   │   ├── documenti_module/  → Documenti inbox, classificazione
│   │   ├── employees/         → Anagrafica dipendenti
│   │   ├── f24/               → F24, tributi, riconciliazione
│   │   ├── fatture_module/    → Fatture passive, import XML
│   │   ├── invoices/          → Corrispettivi, fatture attive
│   │   ├── operazioni_module/ → Operazioni varie
│   │   ├── prima_nota_module/ → Prima Nota (Cassa + Banca)
│   │   ├── reports/           → Report PDF, analytics
│   │   ├── suppliers_module/  → Anagrafica fornitori
│   │   ├── tracciabilita/     → HACCP, tracciabilità lotti
│   │   └── warehouse/         → Magazzino, ricette, movimenti
│   │
│   ├── schemas/               ← Schemi Pydantic validazione
│   ├── scripts/               ← Script one-shot (migrazione, seeding)
│   ├── services/              ← Logica business trasversale
│   │   ├── email_document_downloader.py  ← Download allegati IMAP
│   │   ├── email_monitor_service.py      ← Loop 50 minuti + routing
│   │   ├── email_classifier_service.py   ← Classificazione mittenti/documenti
│   │   ├── email_reconciliation.py       ← Matching email ↔ documenti
│   │   ├── email_service.py              ← SMTP invio email
│   │   ├── xml_invoice_processor.py      ← Processamento XML fatture
│   │   ├── ciclo_passivo/                ← Gestione ciclo passivo
│   │   ├── noleggio/                     ← Gestione noleggio auto
│   │   └── suppliers/                    ← Service fornitori v2
│   │
│   └── utils/                 ← Utility condivise
│
└── frontend/
    └── src/
        ├── main.jsx           ← React Router (routing SPA)
        ├── App.jsx
        ├── api.js             ← Axios con REACT_APP_BACKEND_URL
        ├── lib/
        │   └── utils.js       ← Design system (COLORS, STYLES, SPACING)
        ├── components/
        │   ├── layout/
        │   │   ├── TopNav.jsx         ← Navigazione principale
        │   │   └── SecondaryTabs.jsx  ← Tab secondari per sezione
        │   ├── attendance/
        │   ├── cucina/               ← (rimosso — vedi DIARIO.md)
        │   ├── prima-nota/
        │   └── ui/
        ├── contexts/
        │   └── AnnoContext.jsx       ← Contesto anno selezionato (globale)
        ├── hooks/
        │   ├── useIsMobile.js
        │   └── useHashState.js       ← Deep linking via hash URL
        ├── pages/
        │   ├── Dashboard.jsx
        │   ├── Fornitori.jsx
        │   ├── ArchivioFattureRicevute.jsx
        │   ├── PrimaNota.jsx
        │   ├── Corrispettivi.jsx
        │   ├── Riconciliazione.jsx
        │   ├── TracciabilitaPage.jsx
        │   ├── hr/
        │   │   ├── HRDipendenti.jsx
        │   │   ├── HRCedolini.jsx
        │   │   ├── HRPresenze.jsx
        │   │   └── HRTFR.jsx
        │   └── hub/
        │       ├── DashboardHub.jsx
        │       ├── ContabilitaHub.jsx
        │       ├── FattureHub.jsx
        │       ├── DocumentiHub.jsx
        │       ├── MagazzinoHub.jsx
        │       ├── StrumentiHub.jsx
        │       └── AdminHub.jsx
        ├── stores/
        ├── styles/
        └── utils/
```

---

## Pattern Fondamentali

### IMAP sempre in thread (NON blocca l'event loop)
```python
# ✅ CORRETTO
async def endpoint():
    raw = await asyncio.to_thread(funzione_sincrona_imap, user, password)
    for doc in raw:
        await db["collection"].insert_one(doc)

# ❌ SBAGLIATO — blocca tutto il server
async def endpoint_sbagliato():
    imap = imaplib.IMAP4_SSL("imap.gmail.com")  # BLOCCA!
```

### MongoDB — pattern corretti
```python
# Esclude sempre _id
docs = await db["collection"].find({}, {"_id": 0}).to_list(None)

# DateTime corretta
from datetime import datetime, timezone
now = datetime.now(timezone.utc)   # NON datetime.utcnow()

# Insert: non riusare il doc dopo insert_one (aggiunge _id)
await db["collection"].insert_one(doc)
```

### Hub Pattern (evita reload continuo su cambio tab)
```jsx
// mount-once + display:none per tab non attivi
const [visitedTabs, setVisitedTabs] = useState(new Set(['primo-tab']));

return (
  <>
    {visitedTabs.has('tab1') && (
      <div style={{ display: activeTab === 'tab1' ? 'block' : 'none' }}>
        <ComponenteTab1 />
      </div>
    )}
  </>
);
```

### Registrazione Router in main.py
```python
from app.routers.modulo import router_file

app.include_router(router_file.router, prefix="/api/prefisso", tags=["Tag"])
```

---

## Endpoint Principali

| Prefisso API | File Router | Descrizione |
|---|---|---|
| `/api/dipendenti` | `routers/employees/dipendenti.py` | Anagrafica dipendenti |
| `/api/cedolini` | `routers/cedolini.py` | Buste paga + import Gmail |
| `/api/paghe` | `routers/libro_unico_parser.py` | Libro unico Zucchetti |
| `/api/paghe` | `routers/f24_parser.py` | Distinte F24 |
| `/api/fatture-ricevute` | `routers/fatture_module/` | Archivio fatture passive |
| `/api/prima-nota` | `routers/prima_nota_module/` | Prima Nota Cassa + Banca |
| `/api/estratto-conto-movimenti` | `routers/bank/estratto_conto.py` | Movimenti bancari |
| `/api/suppliers` | `routers/suppliers_module/base.py` | Anagrafica fornitori |
| `/api/f24` | `routers/f24/f24_main.py` | F24 e tributi |
| `/api/piano-conti` | `routers/accounting/` | Piano dei conti |
| `/api/email-download` | vari | Download email PEC/Gmail |
| `/api/health` | `main.py` | Health check |
| `/api/ping` | `main.py` | Ping |

---

## Avvio e Deploy

- **Avvio**: Supervisor gestisce sia backend (`:8001`) che frontend (`:3000`)
- **Backend entry**: `backend/server.py` → `from app.main import app`
- **NON modificare** porte o `server.py` — Supervisor dipende da questi
- **Restart**: solo per modifiche `.env` o nuove dipendenze Python
- **Frontend build**: `cd frontend && npm run build`
- **Auth**: disabilitata (`AUTH_DISABLED=true`) — accesso diretto senza login

---

## Collection MongoDB Canoniche

Vedi `memoria/LOGICA_OPERATIVA.md` → Sezione 12 per la mappa completa.
Vedi `app/database/collections.py` per i nomi costanti da usare nel codice.

**Regola fondamentale**: usare sempre le costanti di `collections.py` — MAI stringhe letterali.

---

*Aggiornato: Aprile 2026*

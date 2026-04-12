# PRD — Ceraldi ERP
> Product Requirements Document | Aggiornato: Aprile 2026

---

## Identità del Progetto

**Nome**: Ceraldi ERP (codice repo: `gestionale2`)
**Azienda**: Ceraldi Group S.R.L. — Bar/Pasticceria a Napoli
**P.IVA**: 04523831214
**Scopo**: Sistema ERP full-stack per contabilità, HR, magazzino e compliance fiscale italiana.
**Architettura**: React 18 + FastAPI + MongoDB Atlas
**Utenti**: non multi-utente — uso interno da parte dello staff amministrativo

---

## Regole Fondamentali (Non Negoziabili)

1. **Design system**: SOLO CSS inline con le costanti di `lib/utils.js`. Vietato Tailwind e Shadcn per le pagine gestionali.
2. **Lingua**: rispondere SEMPRE in italiano nei commenti e nella UI.
3. **Database**: MongoDB Atlas (`azienda_erp_db`) via `MONGO_URL` dal `.env`.
4. **Backend entry**: NON eliminare `backend/server.py` — è il punto di avvio di Supervisor.
5. **Collection**: usare sempre le costanti di `app/database/collections.py`.
6. **IMAP**: sempre in `asyncio.to_thread()` — non bloccare l'event loop.
7. **`_id` MongoDB**: escludere sempre con `{"_id": 0}` nelle query o via Pydantic.

---

## Stato Implementazione (Aprile 2026)

### ✅ Completato e Funzionante

**Contabilità**
- Prima Nota Cassa (corrispettivi + inserimento manuale)
- Prima Nota Banca (import CSV BPM + riconciliazione)
- Estratto conto BNL: import ottimizzato (da ~60s a ~2.5s con bulk insert)
- Piano dei Conti con drawer cliccabile (movimenti semantici per conto)
- Corrispettivi telematici (import XML registratore)
- F24: import PDF, riconciliazione con movimenti bancari

**Fatture**
- Import XML FatturaPA SDI (parsing completo: UTF-8, latin-1, P7M)
- Aruba PEC: download automatico ogni ora (INBOX + INBOX.lette, 59 fatture importate)
- Anti-duplicato via hash MD5 dell'XML
- Creazione fornitore automatica da XML se non esiste

**HR**
- Anagrafica dipendenti (34 record in `dipendenti`)
- Cedolini: import Gmail (271 cedolini importati, storico completo)
- Formati supportati: CSC Napoli, Zucchetti classico, Zucchetti nuovo, Teamsystem
- TFR: calcolo e accantonamento
- Presenze e giustificativi (FE, RL, MA, SM, L1, ecc.)
- Nuova struttura HR: 4 pagine separate in `pages/hr/`

**Fornitori**
- Anagrafica completa (316 record in `suppliers`)
- Aggiornamento automatico da Camera di Commercio (OpenAPI Imprese)
- Dati: comune, indirizzo, provincia, CAP, PEC da OpenAPI per 44/45 fornitori
- Schede tecniche: ricerca PDF su Gmail + web

**Email Scanner**
- Mittenti whitelist (`mittenti_email`): 11+ pattern configurati
- Scheduler Gmail ogni 50 minuti
- Routing automatico per tipo documento (fattura_xml, cedolino, pagopa, inps, ecc.)

**Frontend**
- Responsive su mobile: tutte le pagine principali adattate
- Hub pattern (tab mount-once + display:none) su tutti gli hub
- Deep linking via `useHashState` + `CopyLinkButton`
- Formato italiano: date gg/mm/aaaa, valori con separatore punto

### ⚠️ Esiste ma non automatico (richiede azione manuale o completamento)

| Funzionalità | Stato | Dettaglio |
|---|---|---|
| Prima Nota automatica al pagamento | Parziale | La logica c'è, manca trigger automatico da estratto conto |
| TFR automatico da cedolino | Parziale | Parser estrae quota, manca chiamata automatica a `registra_accantonamento_tfr()` |
| Aggiornamento giacenze da fattura | Parziale | Codice presente, non sempre si attiva |
| Aggiornamento prezzi ricette da fattura | Non connesso | Esiste in tracciabilità, non collegato al gestionale |
| Controllo IVA mensile | Non implementato | Logica definita in `AUTOMAZIONI.md` |
| Risposta automatica avviso bonario | Non implementato | Endpoint F24 verifica esiste parzialmente |

### 🔴 Rimosso (non reintrodurre)

| Cosa | Motivo |
|---|---|
| Modulo Cucina (router + pagine) | Non pertinente per software contabile |
| FiscoHub, MotoreContabile, LiquidazioneIVA, RiconciliazioneF24, CodiciTributari, F24.jsx | Duplicati/obsoleti |
| Route `/archivio-fatture-ricevute` | Duplicato di `/fatture` — ora redirect |
| Tab "Escludi da Tracciabilità" (form fornitori) | Rimosso |
| `CicloPassivoAdmin.jsx` + `ciclo_passivo_integrato.py` | Funzioni spostate in `fatture_module/ciclo_utils.py` |
| Link "Import Fatture" dal menu Altro | Rimosso |
| Widget Cucina in Dashboard | Rimosso |

---

## Backlog Prioritizzato

### P1 — Alta priorità
- **Prima Nota automatica**: trigger al pagamento confermato da estratto conto (vedi `AUTOMAZIONI.md` §1)
- **Risposta avviso bonario**: endpoint di verifica F24 già pagato (vedi `AUTOMAZIONI.md` §6)
- **Schede Tecniche via Gmail IMAP**: scansiona inbox per allegati PDF da fornitori (password Gmail funzionante)

### P2 — Media priorità
- **Piano dei Conti cliccabile**: partitario per conto con movimenti (vedi `AUTOMAZIONI.md` §2)
- **Scheda fornitore completa**: aggregazione totale fatturato, scadenze, pattern pagamento (vedi `AUTOMAZIONI.md` §3)
- **Dettaglio fattura completo**: righe, PDF inline, movimenti collegati (vedi `AUTOMAZIONI.md` §4)
- **Fascicolo dipendente**: storico cedolini, TFR, presenze, bonifici abbinati (vedi `AUTOMAZIONI.md` §5)
- **Cleanup DB**: consolidare `suppliers` (53) con `fornitori` (168) — collection canonica è `fornitori`
- **Dipendenti**: consolidare `dipendenti` (34) con `employees` (31) — canonica è `dipendenti`

### P3 — Bassa priorità
- **TFR automatico da cedolino** (vedi `AUTOMAZIONI.md` §7)
- **Controllo IVA mensile automatico** (vedi `AUTOMAZIONI.md` §8)
- **Notifiche push su tutti gli eventi** (vedi `AUTOMAZIONI.md` §9)
- **Estratto conto → matching automatico completo** (vedi `AUTOMAZIONI.md` §10)
- **Auth backend JWT con cookie HTTP-Only** (attualmente disabilitata)
- **PIN dipendenti** per tablet cucina → ceraldiapp.it

---

## Collection MongoDB Principali (Aprile 2026)

| Collection | Documenti | Descrizione |
|---|---|---|
| `prima_nota_cassa` | 2.132 | Prima nota cassa |
| `prima_nota_banca` | 1.869 | Prima nota banca |
| `corrispettivi` | 1.114 | Corrispettivi giornalieri RT |
| `invoices` | 224 | Fatture passive SDI |
| `suppliers` | 328 | Anagrafica fornitori (modulo principale) |
| `fornitori` | 168 | Anagrafica fornitori (variante italiana) |
| `dipendenti` | 34 | Anagrafica dipendenti (CANONICA) |
| `employees` | 31 | Copia dipendenti (solo presenze batch) |
| `cedolini` | 1.658 | Buste paga (Gmail + PDF + libro unico) |
| `cedolini_importati` | 2.363 | Sistema Zucchetti cloud |
| `estratto_conto_movimenti` | 4.468 | Movimenti bancari |
| `f24_unificato` | 68 | F24 importati |
| `warehouse_inventory` | 6.885 | Giacenze magazzino |
| `presenze` | 20.989 | Storico presenze |

---

## API Key (aggiornate Aprile 2026)

```
GET  /api/piano-conti/conto/{codice}/movimenti?limit=40&anno=2026
GET  /api/fatture-ricevute/archivio?anno=2026
POST /api/fatture-ricevute/import-xml
GET  /api/prima-nota/cassa?anno=2026
GET  /api/prima-nota/banca?anno=2026
POST /api/bank/import-estratto-conto
GET  /api/suppliers?page=1&limit=50
GET  /api/dipendenti
POST /api/cedolini/import-gmail?since_days=180
GET  /api/openapi-imprese/status
POST /api/openapi-imprese/aggiorna-bulk
POST /api/schede-tecniche/cerca/{fornitore_id}
POST /api/email-download/pec/download-fatture-sync?since_days=365
GET  /api/health
```

---

*Aggiornato: Aprile 2026*

# PRD — Ceraldi ERP
> Product Requirements Document | Aggiornato: Aprile 2026

---

## Identità del Progetto

**Nome**: Ceraldi ERP (codice repo: `gestionale2`)
**Azienda**: Ceraldi Group S.R.L. — Bar/Pasticceria a Napoli
**P.IVA**: 04523831214
**Scopo**: Sistema ERP full-stack per contabilità, HR, magazzino e compliance fiscale italiana.
**Architettura**: React 18 + FastAPI + MongoDB Atlas
**Database**: `Gestionale` (MongoDB Atlas)
**Utenti**: non multi-utente — uso interno da parte dello staff amministrativo

---

## Regole Fondamentali (Non Negoziabili)

1. **Design system**: SOLO CSS inline con le costanti di `lib/utils.js`. Vietato Tailwind e Shadcn per le pagine gestionali.
2. **Lingua**: rispondere SEMPRE in italiano nei commenti e nella UI.
3. **Database**: MongoDB Atlas (`Gestionale`) via `MONGO_URL` dal `.env`.
4. **Backend entry**: NON eliminare `backend/server.py` — è il punto di avvio di Supervisor.
5. **Collection canoniche**: `fornitori` (non suppliers), `warehouse_stocks` (non warehouse_inventory), `dipendenti` (non employees).
6. **IMAP**: sempre in `asyncio.to_thread()` — non bloccare l'event loop.
7. **`_id` MongoDB**: escludere sempre con `{"_id": 0}` nelle query o via Pydantic.
8. **Settings priority**: `.env` ha priorità su OS env (la piattaforma inietta MONGO_URL locale vuoto).

---

## Stato Implementazione (Aprile 2026)

### ✅ Completato e Funzionante

**Contabilità**
- Prima Nota Cassa (136 record) e Banca (4.365 record)
- Corrispettivi telematici (54 record)
- Piano dei Conti (30 conti)
- Verifica Coerenza dati con stato IVA
- Provvisori con 3 stati: Cassa / Banca / Sospesa

**Fatture**
- Import XML FatturaPA SDI (1.405 fatture totali)
- 29 Note Credito (TD04) con segno negativo e DatiFattureCollegate
- Aruba PEC: download automatico
- Parser XML con estrazione lotti, scadenze, causali

**HR**
- Anagrafica dipendenti (30 record)
- Cedolini: 301 record con vista Per Mese / Per Dipendente
- Presenze: 290 record con calendario giornaliero e import PDF
- TFR: calcolo e accantonamento

**Fornitori**
- Anagrafica fornitori (245 record)
- Aggiornamento automatico da Camera di Commercio (OpenAPI)

**Magazzino**
- 496 prodotti in warehouse_stocks
- 680 prodotti in dizionario_prodotti
- Catalogo con prezzi, giacenze, fornitori

**Noleggio Auto**
- Flotta 4 veicoli con costi dettagliati
- 165 verbali con estrazione targa da PDF
- Riconciliazione verbali-fatture-driver

**Assegni**
- 220 assegni con associazione fatture
- Modal fatture ordinato per fornitore
- Note credito con importo negativo

**Banca**
- 8.839 movimenti estratto conto
- Riconciliazione automatica

---

## Collection MongoDB Principali (Aprile 2026)

| Collection | Record | Descrizione |
|---|---|---|
| `prima_nota_banca` | 4.365 | Prima nota banca |
| `prima_nota_cassa` | 136 | Prima nota cassa |
| `corrispettivi` | 54 | Corrispettivi giornalieri RT |
| `invoices` | 1.405 | Fatture passive SDI (TD01+TD04) |
| `fornitori` | 245 | Anagrafica fornitori (CANONICA) |
| `dipendenti` | 30 | Anagrafica dipendenti (CANONICA) |
| `cedolini` | 301 | Buste paga (Libro Unico) |
| `presenze` | 290 | Presenze giornaliere |
| `estratto_conto_movimenti` | 8.839 | Movimenti bancari |
| `assegni` | 220 | Gestione assegni |
| `warehouse_stocks` | 496 | Giacenze magazzino (CANONICA) |
| `verbali_noleggio` | 165 | Verbali noleggio auto |
| `f24_unificato` | 1 | F24 |

---

*Aggiornato: Aprile 2026*

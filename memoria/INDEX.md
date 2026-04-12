# INDICE DOCUMENTAZIONE — Ceraldi ERP
> Punto di accesso centralizzato a tutta la documentazione del progetto
> Aggiornato: Aprile 2026 | P.IVA: 04523831214

---

## Il Progetto

**Ceraldi ERP** è un sistema gestionale ERP full-stack per Ceraldi Group S.R.L. — Bar/Pasticceria a Napoli.

| Stack | Tecnologia |
|---|---|
| Backend | Python 3.x + FastAPI + Motor (async) |
| Frontend | React 18 + Vite |
| Database | MongoDB Atlas (`azienda_erp_db`) |
| Avvio | Supervisor (backend `:8001`, frontend `:3000`) |

**Regola fondamentale**: CSS inline ONLY da `lib/utils.js` — NO Tailwind, NO Shadcn per le pagine gestionali.

---

## DOCUMENTAZIONE TECNICA

| File | Contenuto | Priorità lettura |
|---|---|---|
| [ARCHITETTURA.md](./ARCHITETTURA.md) | Stack, struttura directory, pattern fondamentali, endpoint principali | Prima cosa da leggere |
| [LOGICA_OPERATIVA.md](./LOGICA_OPERATIVA.md) | Regole business, flusso email→documenti, collections MongoDB, note critiche | Seconda cosa |
| [FLUSSI_OPERATIVI.md](./FLUSSI_OPERATIVI.md) | Flussi dettagliati: fatture, prima nota, corrispettivi, riconciliazione | Terza cosa |
| [ARCHITETTURA_EVENTI.md](./ARCHITETTURA_EVENTI.md) | Event Bus, handler registrati, flussi completi passo-passo | Approfondimento |

---

## DOCUMENTAZIONE DOMINIO

| File | Contenuto |
|---|---|
| [REGOLE_CONTABILI.md](./REGOLE_CONTABILI.md) | Regole fiscali italiane: conto economico art. 2425, auto aziendali, IVA, F24, cedolini |
| [PROCEDURE_OPERATIVE.md](./PROCEDURE_OPERATIVE.md) | Procedura mensile standard: import documenti, riconciliazione, IVA, HR |
| [HR_BLUEPRINT.md](./HR_BLUEPRINT.md) | Modulo HR: route, API, schema cedolino, formati, TFR, presenze |

---

## DOCUMENTAZIONE FRONTEND

| File | Contenuto |
|---|---|
| [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md) | Costanti COLORS/SPACING/STYLES, template pagina, componenti UI, icone, mobile |

---

## ROADMAP E PIANIFICAZIONE

| File | Contenuto |
|---|---|
| [PRD.md](./PRD.md) | Product requirements: stato implementazione, backlog prioritizzato, collection MongoDB |
| [AUTOMAZIONI.md](./AUTOMAZIONI.md) | Automazioni pianificate: Prima Nota auto, schede fornitore, fascicolo dipendente, IVA mensile |
| [AGENTI_AI.md](./AGENTI_AI.md) | Agenti AI: FiscaleSentinella, HRGuardiano, LearningCervello + visione futura |
| [DEBITO_TECNICO.md](./DEBITO_TECNICO.md) | File da eliminare, collection duplicate, inconsistenze codice, piano di pulizia |

---

## STORICO E CONTESTO

| File | Contenuto |
|---|---|
| [DIARIO.md](./DIARIO.md) | Storico sessioni di sviluppo: bug risolti, decisioni prese, TODO |
| [PATCH_HISTORY.md](./PATCH_HISTORY.md) | Patch Chat 8 applicate: reload fix, responsive, scheduler, tracciabilità |
| [CREDENZIALI.md](./CREDENZIALI.md) | Template credenziali (placeholder — le reali sono in `backend/.env`) |

---

## RIFERIMENTI RAPIDI

### Collections MongoDB canoniche
```
dipendenti (34)              ← HR — CANONICA (NON employees)
cedolini (1658)              ← Buste paga
invoices (224)               ← Fatture passive SDI
suppliers (328)              ← Fornitori (modulo principale)
prima_nota_cassa (2132)      ← Prima nota cassa
prima_nota_banca (1869)      ← Prima nota banca
corrispettivi (1114)         ← UNICA fonte ricavi
estratto_conto_movimenti (4468) ← Movimenti bancari
f24_unificato (68)           ← F24
```

### API più usate
```
GET  /api/dipendenti
GET  /api/cedolini?anno=2026
GET  /api/fatture-ricevute/archivio?anno=2026
GET  /api/prima-nota/cassa?anno=2026
GET  /api/prima-nota/banca?anno=2026
GET  /api/suppliers?page=1&limit=50
POST /api/bank/import-estratto-conto
POST /api/cedolini/import-gmail?since_days=180
POST /api/email-download/pec/download-fatture-sync?since_days=30
GET  /api/health
```

### Route Frontend
```
/               → Dashboard
/fornitori      → Anagrafica Fornitori
/dipendenti     → HR Dipendenti
/dipendenti/cedolini → Buste Paga
/dipendenti/presenze → Presenze
/dipendenti/tfr      → TFR
/prima-nota     → Prima Nota Hub
/fatture        → Archivio Fatture Ricevute
/corrispettivi  → Corrispettivi RT
/tracciabilita  → Tracciabilità HACCP (link a ceraldiapp.it)
```

### Regole critiche
1. **Design**: CSS inline da `lib/utils.js` — NON Tailwind, NON Shadcn
2. **IMAP**: sempre in `asyncio.to_thread()` — mai diretto in async
3. **_id MongoDB**: escludere sempre con `{"_id": 0}`
4. **Collection dipendenti**: usare `dipendenti`, NON `employees`
5. **Volume d'affari**: solo da `corrispettivi` — NON da `invoices`
6. **Auth**: disabilitata (`AUTH_DISABLED=true`)
7. **server.py**: NON cancellare — avvio Supervisor

---

*Aggiornato: Aprile 2026*

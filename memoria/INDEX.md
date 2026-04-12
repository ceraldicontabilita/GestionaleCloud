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
| Database | MongoDB Atlas (`Gestionale`) |
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

## RIFERIMENTI RAPIDI

### Collections MongoDB canoniche (DB: Gestionale)
```
dipendenti (30)                  ← HR — CANONICA (NON employees)
cedolini (301)                   ← Buste paga (Zucchetti v2)
presenze (290)                   ← Presenze giornaliere
invoices (1.405)                 ← Fatture passive SDI (TD01+TD04)
fornitori (245)                  ← Fornitori — CANONICA (NON suppliers)
prima_nota_cassa (136)           ← Prima nota cassa
prima_nota_banca (4.365)         ← Prima nota banca
corrispettivi (54)               ← UNICA fonte ricavi
estratto_conto_movimenti (8.839) ← Movimenti bancari
assegni (220)                    ← Gestione assegni
warehouse_stocks (496)           ← Magazzino — CANONICA (NON warehouse_inventory)
verbali_noleggio (165)           ← Verbali noleggio auto
f24_unificato (1)                ← F24
```

### API più usate
```
GET  /api/dipendenti
GET  /api/cedolini?anno=2026
GET  /api/invoices?anno=2026
GET  /api/prima-nota/cassa?anno=2026
GET  /api/prima-nota/banca?anno=2026
GET  /api/prima-nota/provvisori?anno=2026
GET  /api/attendance/libro-unico?anno=2026
POST /api/attendance/libro-unico/import-pdf
GET  /api/products/catalog
POST /api/bank/import-estratto-conto
POST /api/cedolini/import-gmail?since_days=180
GET  /api/health
```

### Route Frontend
```
/               → Dashboard
/fornitori      → Anagrafica Fornitori
/dipendenti     → HR Dipendenti
/cedolini       → Buste Paga (vista Per Mese / Per Dipendente)
/presenze       → Presenze & Calendario (import PDF Libro Unico)
/tfr            → TFR
/prima-nota     → Prima Nota Hub (Cassa + Banca + Provvisori)
/fatture        → Archivio Fatture Ricevute
/noleggio       → Flotta Auto + Verbali + Riepilogo Costi
/magazzino      → Giacenze (496 prodotti)
/riconciliazione → Riconciliazione bancaria + Assegni
/contabilita    → Piano Conti + Bilancio + IVA
/strumenti      → Verifica Coerenza + Commercialista
```

### Regole critiche
1. **Design**: CSS inline da `lib/utils.js` — NON Tailwind, NON Shadcn
2. **IMAP**: sempre in `asyncio.to_thread()` — mai diretto in async
3. **_id MongoDB**: escludere sempre con `{"_id": 0}`
4. **Collection dipendenti**: usare `dipendenti`, NON `employees`
5. **Collection fornitori**: usare `fornitori`, NON `suppliers`
6. **Collection magazzino**: usare `warehouse_stocks`, NON `warehouse_inventory`
7. **DB name**: `Gestionale` (NON `azienda_erp_db`)
8. **Volume d'affari**: solo da `corrispettivi` — NON da `invoices`
9. **Auth**: disabilitata (`AUTH_DISABLED=true`)
10. **server.py**: NON cancellare — avvio Supervisor
11. **Settings priority**: `.env` > OS env (intenzionale)
12. **Cedolini**: usare campo `nome_dipendente` per display nome
13. **Note credito**: TD04 → importo negativo nel modal assegni

---

*Aggiornato: Aprile 2026*

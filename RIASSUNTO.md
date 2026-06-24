# Ceraldi ERP (GestionaleCloud / gestionale2) — Riassunto applicazione

**Gestionale web interno full-stack** di **Ceraldi Group S.R.L.** (Napoli), usato da un team di
~16 persone. Owner: Enzo Ceraldi. Unifica contabilità, ciclo passivo, prima nota, HR, magazzino,
noleggio auto, riconciliazione bancaria e tracciabilità HACCP, con **acquisizione automatica dei
documenti da PEC e Gmail**.

## Stack tecnologico

| Layer | Tecnologia |
|-------|-----------|
| **Frontend** | React 18 + Vite (porta 3000), stili inline da `src/lib/utils.js` — no Tailwind, no Shadcn |
| **Backend** | FastAPI + Motor async (porta 8001) |
| **Database** | MongoDB Atlas, DB `Gestionale` |
| **Scheduler** | APScheduler (scansione PEC oraria, Gmail ogni 10 min) |
| **Deploy** | Supervisor (ambiente Emergent) |

## Architettura relazionale a eventi

Il cuore dell'app è un **sistema a eventi sincroni** che fa comunicare i moduli: quando un'entità
cambia stato, il cambio si propaga automaticamente. Esempio:

```
Fattura XML → crea/aggiorna Fornitore → crea Partita Aperta → genera Alert se incompleta
Movimento Banca → cerca Match con Partite → Riconcilia → aggiorna Fattura/F24/Stipendio
Cedolino importato → aggiorna Dipendente → crea Prima Nota Salari → crea Partita Stipendio
```

Servizi core in `app/services/`:

- `event_bus.py` — dispatcher eventi sincrono
- `alert_engine.py` — 48 codici alert standardizzati con trigger/chiusura automatica
- `audit_logger.py` — log unificato di ogni cambio stato
- `deduplica.py` — controllo duplicati per tutte le entità
- `partite_aperte_engine.py` — scadenziario materializzato
- `riconciliazione_engine.py` — scoring match a 4 livelli (esatto → pattern → approssimato → debole)

## Moduli funzionali principali

- **Fatture / Ciclo passivo** — fatture SDI (`invoices`), corrispettivi (unica fonte ricavi)
- **Contabilità** — prima nota cassa/banca, piano conti, bilancio, F24, cespiti, IVA, chiusura
  esercizio, budget, mutui
- **HR** — dipendenti, cedolini (buste paga Zucchetti), presenze (Libro Unico), bonifici stipendi
- **Magazzino** — giacenze (`warehouse_inventory`), storico acquisti, dizionario prodotti
- **Riconciliazione bancaria** — movimenti BPM, assegni, riconciliazione PayPal
- **Noleggio auto** — flotta, verbali/sanzioni stradali (PagoPA)
- **Documenti** — archivio email, classificazione automatica per tipo
- **Integrazioni** — OpenAPI, InvoiceTronic, PagoPA, PayPal

## Regole canoniche critiche

1. **Ricavi solo da `corrispettivi`** — le `invoices` sono costi
2. Collection fornitori = **`fornitori`** (mai `suppliers`, che è solo alias API)
3. Magazzino = `warehouse_inventory`; dipendenti = `dipendenti`
4. Metodo di pagamento fattura preso **sempre dall'anagrafica fornitore**, mai dall'XML SDI
5. Ogni CRUD significativo chiama `propagate_event()`
6. Design system: unica fonte di verità in `src/lib/utils.js` (palette navy `#0f2744` + accento
   oro `#b8860b`)

## Documentazione viva

La cartella `memoria/` contiene la documentazione di riferimento:

- `INDEX.md` — scheda rapida (stack, collections, route, regole critiche)
- `PRD.md` — product requirements e stato implementazione
- `LOGICA_OPERATIVA.md` — funzionamento pagina per pagina
- `BACKLOG.md` — backlog operativo con priorità
- `PIANO_LAVORO_RELAZIONALE.md` — architettura relazionale, catalogo alert, piano a fasi

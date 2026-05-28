# Regole operative per il codice — Ceraldi ERP

> Documento di riferimento per chiunque sviluppi sul gestionale, AI o
> umani. Aggiornato il 28 maggio 2026.

---

## Regola 1 — Import documenti (DEFINITIVA)

### 1.1 Fatture XML/PDF (passive e attive)

**Solo upload manuale o massivo nel gestionale.**

Niente Gmail. Niente PEC. Mai.

- L'unico canale ufficiale di ingresso delle fatture è il bottone
  *Carica fatture* (singola o batch) nelle pagine `ArchivioFattureRicevute`,
  `ImportDocumenti`, `BatchProcessor`.
- Lo scheduler PEC orario e lo scheduler Gmail/Aruba 10 minuti per le
  fatture **restano SPENTI** (`ENABLE_PEC_DOWNLOAD=False`,
  `ENABLE_GMAIL_SYNC=False`, `ENABLE_GMAIL_FULL_SCAN=False` in `app/config.py`).
- Se un allegato XML/P7M viene comunque trovato dallo scanner whitelist
  Gmail (vedi 1.2), va messo in **quarantena** nella collezione
  `fatture_in_quarantena_email` con alert `FAT_TROVATA_IN_EMAIL`. Non si
  importa, mai.

### 1.2 Documenti NON-fattura — Whitelist mittenti

Gmail può importarli **automaticamente solo da mittenti in whitelist**
(`mittenti_attendibili`).

Categorie supportate:

- `verbale_soci` — Verbali assemblea, decisioni soci.
- `quietanza` — Conferme bonifici, ricevute.
- `allegato_generico` — Allegato PDF generico da mittente noto.
- `cartella_esattoriale` — Agenzia Entrate Riscossione (AdER).
- `avviso_pagamento` — Comune, INPS, INAIL, enti pubblici.
- `avviso_bonario` — Agenzia Entrate (pre-ruolo).
- `cedolino_vicedomini` — Cedolini/comunicazioni dal commercialista del lavoro.
- `altro` — Altri documenti attendibili.

Implementazione:

- Whitelist in collezione `mittenti_attendibili` (CRUD in
  `app/services/mittenti_attendibili.py` + router
  `app/routers/mittenti_attendibili.py` prefix `/api/mittenti-attendibili`).
- Scheduler: `app/services/gmail_whitelist_scanner.py` chiamato da
  `app/scheduler.py` ogni `GMAIL_WHITELIST_SCAN_MINUTES` minuti
  (default 15). Flag `ENABLE_GMAIL_WHITELIST_SCAN=True` di default.
- Documenti scaricati finiscono in `documents_inbox` con
  `fonte = "gmail_auto"`, `mittente`, `categoria_auto`,
  `modulo_destinazione`.

### 1.3 Endpoint manuali (bottoni "Importa adesso")

Restano usabili come fallback one-shot, **anche con scheduler spenti**:

| Endpoint | Flag manuale |
|---|---|
| `POST /api/documenti/scarica-fatture-aruba` | `ENABLE_MANUAL_GMAIL_IMPORT` |
| `POST /api/documenti/scarica-da-email` | `ENABLE_MANUAL_GMAIL_IMPORT` |
| `POST /api/cedolini/import-gmail` | `ENABLE_EMAIL_CEDOLINI_DOWNLOAD` |
| `POST /api/bonifici-stipendi/scarica-da-email` | `ENABLE_MANUAL_GMAIL_IMPORT` |
| `POST /api/f24-email/scarica-email` | `ENABLE_EMAIL_F24_DOWNLOAD` |
| `POST /api/f24-email/scarica-e-processa` | `ENABLE_EMAIL_F24_DOWNLOAD` |

Tutti questi flag sono `True` di default. Se OFF, l'endpoint risponde
`410 Gone` con dettaglio motivo + nome flag.

---

## Regola 2 — Database

- **Solo MongoDB Atlas**, database `Gestionale`, cluster `cluster0.vofh7iz`.
- Zero Supabase, mai. Verificato il 28/05/2026: zero occorrenze in
  Python/JS/JSX.
- Nomi collezioni canoniche in `app/db_collections.py`. Importare da lì.
- Mai stringhe hardcoded `"suppliers"`, `"employees"` per collezioni:
  usare le costanti italiane (`fornitori`, `dipendenti`).

## Regola 3 — Stack tecnologico

- Backend: FastAPI + Motor async, porta 8001.
- Frontend: React 18 + Vite, porta 3000.
- Scheduler: APScheduler (`app/scheduler.py`).
- Design system: `frontend/src/lib/utils.js` (vedi `DESIGN.md`). No
  Tailwind, no shadcn.

## Regola 4 — Italiano nei nomi nuovi

Per nuove collezioni, endpoint, variabili, classi: nomi italiani.
Eccezione: nomi tecnici universali (es. `created_at`, `id`, `hash`).

## Regola 5 — Branch & deploy

- Modifiche allo sviluppo: solo su branch `refactor-italiano` (o branch
  feature dedicati). Mai direttamente su `master`.
- Commit separati per ogni modulo, messaggio in italiano.
- Pull request per il merge su `master`.

## Regola 6 — Architettura relazionale (sistema eventi)

Quando un'entità cambia stato, il cambio si propaga automaticamente
via `app/services/event_bus.propagate_event(...)`. Handler registrati
in `app/services/handlers/`. Vedi `PIANO_LAVORO_RELAZIONALE.md`.

```
Fattura XML  ->  crea/aggiorna Fornitore
              ->  crea Partita Aperta
              ->  genera Alert se incompleta
Movimento Banca  ->  cerca Match con Partite
                 ->  Riconcilia
                 ->  aggiorna Fattura/F24/Stipendio
Cedolino  ->  aggiorna Dipendente
          ->  crea Prima Nota Salari
          ->  crea Partita Stipendio
```

## Regola 7 — Conferma esplicita "pagato"

Nessun handler può marcare una fattura/F24/cedolino come `pagato`
senza match riconciliato o conferma esplicita utente.

## Regola 8 — Tracciabilità (ceraldiapp.it)

- Push da Tracciabilità verso il gestionale: endpoint legacy
  `POST /api/erp/ponte/fattura-ricevuta` (esistente, scrive in
  `fatture_passive`).
- Pull da Tracciabilità (preferito, nuovo): endpoint
  `GET /api/erp/ponte/fatture` autenticato con `X-Ponte-Token`
  (variabile env `PONTE_TOKEN`). Vedi `app/routers/erp_bridge.py`.

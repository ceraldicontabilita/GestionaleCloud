# Ceraldi ERP — PRD

Prodotto: gestionale contabile / amministrativo interno.
Cliente: Ceraldi Group S.R.L. (P.IVA 04523831214) — bar / pasticceria, Napoli.
Ultima revisione: Apr 2026.

Documentazione viva completa in `/app/memoria/` (PRD.md · INDEX.md · LOGICA_OPERATIVA.md).
Questo file è il riepilogo per i tool interni Emergent.

## Obiettivo

Un unico gestionale che copra:
- Ciclo passivo (fatture SDI via PEC)
- Corrispettivi giornalieri (registratore)
- Prima nota cassa/banca + Provvisori
- Riconciliazione bancaria
- HR (dipendenti, cedolini, presenze, TFR)
- Noleggio auto + verbali stradali
- Magazzino prodotti
- Assegni per carnet
- Contabilità (piano conti, bilancio, IVA, cespiti, mutui, budget)
- Strumenti commercialista + verifica coerenza
- Alert scadenze F24

## Stack

- React 18 + Vite (frontend, porta 3000)
- FastAPI + Motor async (backend, porta 8001)
- MongoDB Atlas (DB: `Gestionale`)
- Design: inline styles da `src/lib/utils.js` — no Tailwind, no Shadcn

## Stato corrente

Funzionante in produzione: tutte le aree core (fatture, prima nota, fornitori, HR,
noleggio, magazzino, assegni, riconciliazione, contabilità, strumenti, email).

Attività recenti (Apr 2026):
- Refactoring grafico completo: design system unificato, palette navy + oro,
  layout full-frame, tabs uniformate, mobile-responsive (no scroll orizzontale).
- Rimosso Tailwind dalla build (PostCSS senza plugin).
- Fix backend: installati `lxml` + `primp` mancanti.
- Documentazione viva riscritta da zero in `/app/memoria/`.

## Backlog

P1:
- Prima Nota automatica senza conferma per match E/C ≥90% confidenza
- Endpoint `/scarica-posta` per verbali via PEC (ancora stub)

P2:
- Scheda fornitore completa (storico + scadenze + pattern)
- Fascicolo dipendente (cedolini + TFR + presenze + bonifici)
- Merge `suppliers` (15 legacy) in `fornitori` (245)

P3:
- TFR automatico da cedolino
- Controllo IVA mensile automatico + F24 suggerito
- Notifiche WhatsApp (Meta token già configurato)

## Regole invariabili

- DB: `Gestionale` (non `azienda_erp_db`)
- `fornitori` (non `suppliers`), `dipendenti` (non `employees`), `warehouse_stocks` (non `warehouse_inventory`)
- Ricavi SOLO da `corrispettivi`; le `invoices` sono costi
- Metodo pagamento fattura preso dal fornitore, mai dall'XML
- Note credito TD04 = importo negativo + badge rosso
- IMAP sempre in `asyncio.to_thread()`

Per dettagli operativi vedi `/app/memoria/LOGICA_OPERATIVA.md`.

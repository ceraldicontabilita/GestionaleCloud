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
- **[FEAT P1 – Apr 2026] UI Risoluzione Ambigui Assegni**: aggiunti al file
  `app/routers/bank/assegni.py` 2 endpoint (`GET /api/assegni/ambigui` e
  `POST /api/assegni/{id}/risolvi-ambiguo`) riposizionati PRIMA della route
  dinamica `/{assegno_id}`. Nel frontend `GestioneAssegni.jsx` nuovo bottone
  `[data-testid=ambigui-toggle-btn]` ("⚠ Risolvi ambigui") che apre un pannello
  con: per ogni assegno ambiguo la lista delle fatture candidate con checkbox
  (default la prima selezionata), bottone "✓ Collega selezionati" che invoca
  `risolvi-ambiguo` via `_apply_match`. Al successo l'assegno scompare
  dalla lista e i dati vengono ricaricati.
  Verificato su produzione: 9 casi KIMBO S.P.A. (3 assegni × 4 fatture identiche)
  correttamente esposti e pronti alla decisione manuale dell'utente.
- **[BUG FIX P0 – Apr 2026] Duplicati estratto conto (POS Banca doppio)**:
  rimosso un bug di dati (non di codice): la collezione
  `estratto_conto_movimenti` conteneva 4596 record duplicati per import
  ripetuti con formato data diverso (ISO `2026-01-15` vs italiano `15/01/2026`,
  intersezione 0). Creato script one-shot
  `/app/scripts/cleanup_estratto_conto_duplicati.py` (8849 → 4253 record).
  Anti-duplicato persistente nell'endpoint `POST /api/bank-statement/import`.
  Endpoint di manutenzione on-demand
  `POST /api/bank-statement/cleanup-duplicati`. POS Banca Gennaio 2026
  ora €34.219,10 (prima €68.438,20 = 2x).
- **[FEAT P2/P3 – Apr 2026]** Pacchetto multi-feature:
  • **Auto-conferma fatture**: bottone "✅ Auto-conferma fatture" in `/fornitori`
    che chiama `POST /api/fatture-ricevute/backfill-autoroute` — scorre tutte
    le fatture non confermate e, se il fornitore ha `metodo_pagamento`
    definito (contanti/cassa/bonifico/banca/MP0*/carta), le registra
    automaticamente in prima_nota_cassa o prima_nota_banca.
    Primo lancio reale: 809 analizzate, 22 skip assegno (OK), 609 skip
    metodo non definito (fornitori senza predefinito), 170 fornitori mancanti.
  • **Notifiche WhatsApp (Meta Cloud API v21.0)**: nuovo servizio
    `app/services/whatsapp_notifications.py` + endpoint
    `GET /api/whatsapp/status`, `POST /api/whatsapp/send`,
    `POST /api/whatsapp/send-test`. Configurato con WHATSAPP_API_TOKEN,
    WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_RECIPIENT_1/2 dal .env.
    Fallback automatico a template `hello_world` se finestra 24h scaduta.
    ⚠️ Nota: il token Meta attuale è scaduto il 12/04/2026 — va rigenerato
    dalla console Meta (scegliere System User access token per evitare
    scadenze).
  • **PWA**: installabile da Chrome/Safari con manifest.webmanifest
    (3 icone, 3 shortcuts — Dashboard, Prima Nota, Fatture), service-worker
    con cache prudente (niente cache su /api/*, stale-while-revalidate su
    asset statici, navigate fallback a /index.html per routing SPA).
    Icon install app + "Aggiungi a schermata Home" ora disponibili su mobile.
  • **Controllo Mensile**: già contiene tutte le colonne richieste
    (POS RT / POS Reale / 🏦 POS Banca / Diff. / Corr. Auto / Corr. Man. /
    Diff. / Versam. / Saldo) — nessun intervento necessario.
  • **Split corrispettivi.py**: rimandato a sessione dedicata con test di
    regressione completi (refactoring estetico senza valore utente diretto,
    rischio alto su endpoint in produzione).
- **[FEAT P1 auto-matcher Assegni – Apr 2026]** Implementato l'auto-matcher
  Assegni↔Fatture a 4 livelli (L1 1↔1, L2 N uguali→1, L3 N diversi→1, L4 1→N)
  con tolleranza rigida ±0,005€ e vincolo P.IVA fornitore.
  Orchestratore in `app/routers/bank/assegni_auto_match.py`, endpoint
  `POST /api/assegni/auto-match?dry_run=true|false`.
  Include arricchimento automatico P.IVA (dai nomi in `beneficiario` usando
  tabella `fornitori`) e dedup intelligente delle fatture duplicate nel DB.
  Genera movimenti `prima_nota_banca` con source=`assegno_auto_match` (idempotente).
  Aggiorna `invoices.importo_pagato`, `payment_status`, `assegni_collegati[]`.
  Frontend: 2 nuovi bottoni su `/riconciliazione/assegni`:
  `[data-testid=auto-match-btn]` (🤖 Auto-collega) + `[data-testid=auto-match-preview-btn]` (👁 Anteprima).
  Risultato su produzione: 220 assegni reali → 185 arricchiti P.IVA automaticamente,
  **44 match L1 eseguiti** + 44 movimenti banca + 44 fatture aggiornate, 9 ambigui genuini,
  idempotenza verificata. Test 100% (backend + frontend).
- **[FIX P0 corrispettivi – Apr 2026]** Riscritta l'ingestion dei Corrispettivi
  XML con anti-duplicato rigoroso a 3 livelli (corrispettivo_key, data+matricola,
  data+totale±0.01) e propagazione automatica in Prima Nota:
  quota contanti → `prima_nota_cassa` (source `corrispettivo_import`),
  quota POS → `prima_nota_banca` (source `corrispettivo_pos`).
  Helper centralizzato in `app/routers/invoices/corrispettivi_helpers.py`,
  usato da `/api/documenti/upload-auto`, `/api/corrispettivi/upload-xml`,
  `upload-xml-bulk`, `upload-zip`. Nuovi endpoint di manutenzione:
  `POST /api/corrispettivi/rebuild-prima-nota?anno=YYYY` e
  `POST /api/corrispettivi/cleanup-duplicati-forte?anno=YYYY`.
  Eseguito rebuild 2026: 50 corrispettivi → 50 mov. cassa + 50 mov. banca POS,
  quadratura contabile verificata (€50.222,60 cassa + €83.383,82 POS = €133.606,42).
  Test backend 7/7 passati.
- Refactoring grafico completo: design system unificato, palette navy + oro,
  layout full-frame, tabs uniformate, mobile-responsive (no scroll orizzontale).
- Rimosso Tailwind dalla build (PostCSS senza plugin).
- Fix backend: installati `lxml` + `primp` mancanti.
- Documentazione viva riscritta da zero in `/app/memoria/`.

## Backlog

P1:
- **Tab contabili vuoti**: tutti gli endpoint esistono già (`/api/mutui`,
  `/api/cespiti`, `/api/chiusura-esercizio/*`, `/api/contabilita-gestionale/budget`,
  `/api/finanziaria/summary`) e rispondono correttamente. Le pagine frontend
  esistono (GestioneMutui, GestioneCespiti, ChiusuraEsercizio,
  BudgetPrevisionale, Finanziaria). Non sono "rotte": sono vuote perché
  l'utente non ha ancora inserito Mutui/Cespiti/Budget. Quick-start
  (auto-rilevo mutui da estratto conto, auto-popolo cespiti da fatture
  grandi importi, clone budget da anno consuntivo) è il prossimo passo.
- Associazione automatica documenti Gmail (F24, cedolini, verbali)
- Prima Nota automatica senza conferma per match E/C ≥90% confidenza
- Endpoint `/scarica-posta` per verbali via PEC (ancora stub)

P2:
- Controllo Mensile UI: aggiungere colonne POS banca + differenza esplicite
- Scheda fornitore completa (storico + scadenze + pattern)
- Fascicolo dipendente (cedolini + TFR + presenze + bonifici)
- Merge `suppliers` (15 legacy) in `fornitori` (245)
- Split `/app/app/routers/invoices/corrispettivi.py` (>1400 righe) per famiglie

P3:
- Pulsante auto-conferma fatture in pagina Fornitori
- Indicatore fornitori attivi in Magazzino
- PWA (manifest + service worker)
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

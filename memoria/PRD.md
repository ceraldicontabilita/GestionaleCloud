# Ceraldi ERP — PRD

Prodotto: gestionale contabile / amministrativo interno
Cliente: Ceraldi Group S.R.L. (P.IVA 04523831214) — Bar / Pasticceria, Napoli
Ambiente: preview Emergent + produzione
Data ultima revisione: Apr 2026

## Obiettivo

Un unico gestionale web che consolidi:
- ciclo passivo (fatture SDI ricevute via PEC)
- corrispettivi giornalieri del registratore di cassa
- prima nota cassa/banca
- riconciliazione bancaria (estratto conto CSV)
- HR: dipendenti, cedolini, presenze, TFR
- noleggio auto aziendali e verbali stradali
- magazzino prodotti
- assegni emessi per carnet
- contabilità (piano conti, bilancio, IVA, cespiti, mutui)
- scambi con il commercialista
- alert/scadenziario F24

Tutto alimentato in automatico da PEC (fatture XML SDI) e Gmail (cedolini, F24, verbali, quietanze).

## Stack

- Frontend: React 18 + Vite, porta 3000, in `/app/frontend`
- Backend: FastAPI + Motor (async), porta 8001, in `/app/backend` + `/app/app`
- Database: MongoDB Atlas, DB name `Gestionale`
- Design: inline styles da `src/lib/utils.js`, zero Tailwind, zero Shadcn
- Scheduler: APScheduler per PEC (orario) e Gmail (10 min)

Variabili d'ambiente principali:
- frontend: `REACT_APP_BACKEND_URL`, `VITE_BACKEND_URL`
- backend: `MONGO_URL`, `DB_NAME=Gestionale`

## Utenti

Uso interno dello staff amministrativo. Niente multi-tenant, niente registrazione pubblica.

## Principi architetturali

1. I dati entrano sempre da una fonte identificabile (PEC, Gmail, import manuale). Ogni record porta con sé la sua provenienza.
2. Il metodo di pagamento di una fattura NON arriva dall'XML SDI: viene preso dall'anagrafica del fornitore (contanti / bonifico / assegno / misto).
3. I ricavi arrivano SOLO da `corrispettivi`. Le `invoices` sono sempre costi.
4. Le note credito (TD04) vengono registrate con importo negativo e badge rosso.
5. La collezione autorevole per il magazzino è `warehouse_stocks`; per i fornitori `fornitori`; per HR `dipendenti` (mai `employees`).

## Stato implementazione (Apr 2026)

Funzionante:
- Fatture SDI: 1.405 record, TD01 + TD04 con netting, `DatiFattureCollegate`
- Prima Nota: Cassa (136) + Banca (4.365) + Provvisori con Cassa / Banca / Sospesa
- Corrispettivi: 54 record importati da XML registratore
- Fornitori: 245 record, aggiornamento anagrafica da OpenAPI Camera di Commercio
- HR: 30 dipendenti, 301 cedolini (vista Per Mese / Per Dipendente), 290 presenze
- Presenze: calendario giornaliero, import PDF Libro Unico, giustificativi con legenda
- Magazzino: 496 prodotti in `warehouse_stocks`, catalogo costruito dalle righe XML
- Noleggio: 4 veicoli, 165 verbali, estrazione targa da PDF (PyMuPDF), riconciliazione
- Assegni: 220 assegni raggruppati per carnet, modal "Collega Fatture" con NC netting
- Banca: 8.839 movimenti estratto conto, matching automatico con fatture/stipendi/F24
- Strumenti: verifica coerenza IVA / saldi / discrepanze, export PDF commercialista
- Email: PEC Aruba per fatture SDI, Gmail per cedolini / F24 / verbali / quietanze

Backlog:
- P1: Prima Nota automatica senza conferma per match E/C con confidenza ≥90%
- P1: download posta verbali da PEC (endpoint `/scarica-posta` ancora stub)
- P2: scheda fornitore completa (fatturato storico, scadenze, pattern di pagamento)
- P2: fascicolo dipendente (storico cedolini + TFR + presenze + bonifici)
- P2: cleanup DB — merge di `suppliers` (15 record legacy) in `fornitori`
- P3: calcolo TFR automatico dal cedolino (parser estrae già la quota)
- P3: controllo IVA mensile automatico con generazione F24
- P3: notifiche WhatsApp (token Meta configurato, endpoint da creare)

## Refactoring grafico — Apr 2026

Obiettivo: uniformare visivamente tutto il gestionale, rendere le pagine responsive (niente scroll orizzontale su smartphone), ridurre il peso del bundle.

Regole:
- niente Tailwind nella build (postcss pulito)
- una sola fonte di verità per colori/spaziature/bottoni: `src/lib/utils.js`
- palette: navy `#0f2744` primario, accento oro sobrio `#b8860b`, slate neutri
- layout full-frame: nessun `max-width` fisso, il padding è gestito una sola volta dal layout
- mobile-first: `html, body { overflow-x: hidden }` come safety net, tabelle con wrapper scrollabile, griglie che collassano a 1-2 colonne

File riscritti (design):
- `src/lib/utils.js` — design system completo
- `src/index.css` — reset, componenti comuni, regole mobile globali
- `src/styles/topnav.css` — palette allineata alla utils.js
- `src/styles/common.css` — shim legacy minimi
- `src/styles/utilities.css` — utility classes CSS vanilla per le pagine che usavano Tailwind-like
- `src/styles.css` — solo tokens legacy

File toccati (layout):
- tutti gli hub in `src/pages/hub/*.jsx` — rimosso padding duplicato, uniformata la tab bar
- `src/components/layout/TopNav.jsx` — palette unica, altezza 54px
- `src/main.jsx` — aggiunto import di `index.css` (era orfano)
- `postcss.config.cjs` — rimosso plugin tailwind

Fix di contorno:
- installati `lxml` e `primp` nel backend per riabilitare l'import degli XML SDI
- forzato `overflow-x: hidden` su html/body per bloccare overflow laterali nelle pagine legacy
- nascosti i link del menu principale sul TopNav in viewport ≤768px (il menu resta accessibile dalla bottom bar)

## Regole contabili di riferimento

Conto Economico (Art. 2425 c.c.):
- A1 Ricavi = somma dei `corrispettivi` (IVA a debito)
- B6 materie prime/merci: deducibilità 100%, IVA 100% credito
- B7 energia: deducibilità 100%
- B7 telefonia: deducibilità 80%, IVA 50%
- B7 carburante: deducibilità 20%, IVA 40%
- B8 noleggio auto: deducibilità 20% con tetto €3.615/anno, IVA 40%
- B9a salari netti, B9b INPS azienda, B9c TFR: deducibilità 100%

IVA:
- Debito = somma `corrispettivi.totale_iva`
- Credito = somma `invoices.iva_detraibile`
- Saldo mensile = Debito − Credito → F24 codice 6001

Calendario fiscale principale:
- 16 di ogni mese: F24 (IRPEF 1001, INPS 1301/1303, addizionali 1030/3802)
- 16 marzo: saldo IVA anno precedente (6099)
- 30 giugno: dichiarazione IRES/IRAP
- 30 novembre: acconto imposte

Codici pagamento FE rilevanti:
- MP01 contanti → cassa
- MP02 assegno → banca
- MP05 bonifico → banca
- MP08 carta di credito → banca

Tipi documento FE:
- TD01 fattura d'acquisto → uscita
- TD04 nota credito → importo negativo
- TD24/TD25 fattura differita vendita

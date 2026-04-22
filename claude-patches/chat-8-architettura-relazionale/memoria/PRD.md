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
- magazzino prodotti con dizionario e normalizzazione
- assegni emessi per carnet
- contabilità (piano conti, bilancio, IVA, cespiti, mutui)
- tracciabilità HACCP e produzione (via ceraldiapp.it)
- scambi con il commercialista
- alert/scadenziario F24

Tutto alimentato in automatico da PEC (fatture XML SDI) e Gmail (cedolini, F24, verbali, quietanze),
con un sistema relazionale a eventi che propaga automaticamente gli aggiornamenti tra i moduli.

## Stack

- Frontend: React 18 + Vite, porta 3000, in `/app/frontend`
- Backend: FastAPI + Motor (async), porta 8001, in `/app/backend` + `/app/app`
- Database: MongoDB Atlas, DB `Gestionale`, cluster `cluster0.vofh7iz`
- Design: inline styles da `src/lib/utils.js` — palette navy #0f2744 + accento oro #b8860b
- Scheduler: APScheduler per PEC (orario) e Gmail (10 min)
- Servizi core: `app/services/` — event bus, alert engine, audit, deduplica, partite, riconciliazione

Variabili d'ambiente principali:
- frontend: `REACT_APP_BACKEND_URL`, `VITE_BACKEND_URL`
- backend: `MONGO_URL`, `DB_NAME=Gestionale`

## Utenti

Uso interno dello staff amministrativo. Niente multi-tenant, niente registrazione pubblica.
Autenticazione multi-livello: Admin (JWT), Operatore (PIN personale bcrypt), Reparto (PIN operatore di turno).

## Principi architetturali

1. I dati entrano sempre da una fonte identificabile (PEC, Gmail, import manuale). Ogni record porta con sé la sua provenienza.
2. Il metodo di pagamento di una fattura NON arriva dall'XML SDI: viene preso dall'anagrafica del fornitore (contanti / bonifico / assegno / misto).
3. I ricavi arrivano SOLO da `corrispettivi`. Le `invoices` sono sempre costi.
4. Le note credito (TD04) vengono registrate con importo negativo e badge rosso.
5. Collezioni canoniche: `warehouse_inventory` (magazzino), `fornitori`, `dipendenti` (mai le controparti legacy).
6. Nomi collezioni sempre da `app/db_collections.py` — mai stringhe hardcoded nei router.
7. Ogni operazione CRUD significativa chiama `propagate_event()` dal event bus per aggiornare i moduli collegati.
8. Alert con codici standardizzati dal catalogo in `alert_engine.py` (48 codici) — mai alert "liberi".
9. Patch Claude: mai push diretto su main, sempre in `claude-patches/chat-N-descrizione/`.

## Architettura relazionale (Chat 8, Apr 2026)

Il gestionale è stato progettato con un sistema a eventi sincroni che collega tutti i moduli.
Decisioni architetturali vincolanti:

- **Riconciliazione**: collezione dedicata `riconciliazioni_match` (supporta match N:M)
- **Alert**: collezione unica `alerts` con codici standardizzati
- **Eventi**: sincroni via `event_bus.py` (no Redis/Celery — il volume lo consente)
- **Partite aperte**: materializzate in `partite_aperte` (non derivate al volo)

Servizi core in `app/services/`:
- `event_bus.py` — dispatcher sincrono con handler registrabili per tipo evento
- `alert_engine.py` — 48 codici alert con generazione idempotente e chiusura automatica
- `audit_logger.py` — log di ogni cambio stato: chi/quando/cosa/da-dove-a-dove
- `deduplica.py` — verifica duplicati per fatture, fornitori, cedolini, F24, movimenti
- `partite_aperte_engine.py` — scadenziario materializzato con CRUD e ricerca per match
- `riconciliazione_engine.py` — scoring a 4 livelli: esatto → pattern noto → approssimato → debole

Il documento completo è in `PIANO_LAVORO_RELAZIONALE.md` nella root del repo.

## Stato implementazione (Apr 2026)

Funzionante:
- Fatture SDI: ~3856 record, TD01 + TD04 con netting, `DatiFattureCollegate`
- Prima Nota: Cassa (~1428) + Banca (~1138) + Provvisori
- Corrispettivi: ~1051 record importati da XML registratore
- Fornitori: ~268 record, aggiornamento anagrafica da OpenAPI Camera di Commercio
- HR: ~30 dipendenti, ~916 cedolini (vista Per Mese / Per Dipendente)
- Presenze: calendario giornaliero, import PDF Libro Unico, giustificativi
- Magazzino: ~5372 prodotti in `warehouse_inventory`, dizionario ~112, catalogo da righe XML
- Noleggio: 4 veicoli, ~165 verbali, estrazione targa da PDF (PyMuPDF)
- Assegni: ~210 assegni raggruppati per carnet, modal collegamento fatture con NC netting
- Banca: ~4261 movimenti estratto conto, matching con fatture/stipendi/F24
- Strumenti: verifica coerenza IVA/saldi, export PDF commercialista
- Email: PEC Aruba per fatture SDI, Gmail per cedolini/F24/verbali/quietanze
- Tracciabilità HACCP: temperature, sanificazione, disinfestazione, ricezione merce (via ceraldiapp.it)
- Servizi core relazionali: event bus, alert engine, audit, deduplica, partite, riconciliazione (Chat 8)

In sviluppo (piano relazionale Chat 9-16):
- Fase 2: Handler eventi Fatture↔Fornitori↔Prima Nota (Chat 10)
- Fase 3: Riconciliazione Banca con scoring 4 livelli (Chat 11)
- Fase 4: F24↔Banca (Chat 12)
- Fase 5: Cedolini↔Dipendenti↔Banca (Chat 13)
- Fase 6: Corrispettivi↔POS↔Cassa↔Banca (Chat 14)
- Fase 7: Trasferimenti interni + Inbox documentale (Chat 15)
- Fase 8: Dashboard relazionale + UI alert unificata (Chat 16)

Backlog separato: vedi `memoria/BACKLOG.md`.

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

# PIANO DI CONSOLIDAMENTO — Indice di avanzamento

> Documento vivo, richiesto dall'utente il 14/07/2026 a partire da
> `REPORT_FINALE_VERIFICA_REALE_GESTIONALECLOUD.md`. Va aggiornato ad ogni
> operazione eseguita, così l'utente sa sempre "sono all'operazione N di
> TOTALE" e cosa resta. Non cancellare le righe completate: si spuntano.

Fonte: report di verifica esterna sul branch `main` (snapshot precedente a
questa sessione). Molti punti del report risultano già superati da lavoro
successivo già in `main` — segnalato caso per caso sotto con l'evidenza.

## Legenda

- ✅ FATTO — verificato nel codice/documenti attuali
- 🟡 PARZIALE — esiste una base, manca il completamento
- ⛔ DA FARE — non iniziato
- ❓ DECISIONE UTENTE — bloccato: per la REGOLA PARAMETRI di CLAUDE.md
  (valori configurabili/architetturali non si toccano di iniziativa) serve
  una scelta esplicita prima di agire

## Stato di avanzamento

**Operazioni chiuse: 3 di 23** (verificate in questa sessione, già presenti
prima di oggi) · **Prossima operazione aperta: #1** (CI unica di coerenza mappe)

---

## FASE 1 — Sincronizzare gli audit (2 operazioni)

**1. ⛔ Comando CI unico "route-map-consistency"**
Deve rigenerare `MAPPA_ROUTER.md`, `MAPPA_ENDPOINT_COMPLETA.md`,
`ENDPOINT_CLASSIFICAZIONE_FINALE.md` sullo stesso commit e fallire se i
totali non coincidono. Oggi non esiste (le 4 workflow CI presenti —
`audit-static.yml`, `smoke-runtime.yml`, `audit-layout.yml`,
`verifica-produzione.yml` — non fanno questo controllo).

**2. ⛔ Rigenerare le mappe e verificare la coerenza**
Confermata l'incoerenza segnalata dal report:
`MAPPA_ROUTER.md` e `AUDIT_ATOMICO_APPLICAZIONE.md` dichiarano **1059**
endpoint; `AUDIT_ESECUZIONE_DEFINITIVO.md` dichiara ancora **1105/1106**
(documento narrativo di una sessione precedente alla pulizia delle 19 route
morte della pipeline paghe, mai rigenerato). `ENDPOINT_CLASSIFICAZIONE_FINALE.md`
riporta nell'intestazione "1072" ma "1059" più avanti nel testo — da
rigenerare con `python scripts/genera_classificazione_endpoint.py` per avere
un numero unico e verificato.

---

## FASE 2 — Audit React reale (3 operazioni)

**3. ⛔ `scripts/audit_frontend_dead_code.py`** — non esiste (verificato:
in `scripts/` ci sono solo `audit_static.py`, `smoke_app.py`,
`genera_mappa.py`, `genera_classificazione_endpoint.py`).

**4. ⛔ `memoria/AUDIT_FRONTEND_DEAD_CODE.md`** — non esiste. Il vecchio
elenco di componenti inutilizzati è stato superato/rimosso.

**5. ⛔ Eliminazione file `ORFANO_ELIMINABILE`** — dipende da #3/#4.

---

## FASE 3 — Endpoint "verificare" (9 operazioni, una per gruppo prioritario)

Numeri confermati in `ENDPOINT_CLASSIFICAZIONE_FINALE.md`: 1059-1072
endpoint totali, 648 tenere, 405 verificare, 19 admin-only. Ogni gruppo è
❓ DECISIONE UTENTE: prima di smontare o ricollegare un router chiederò
conferma con opzioni (per la regola parametri di CLAUDE.md — sono scelte
architetturali con impatto su produzione, non modifiche di iniziativa).

| # | Gruppo | Endpoint | Note |
|---|---|---|---|
| 6 | ❓ Batch operations | 6 | `/api/batch/*` — nessun chiamante noto |
| 7 | ❓ Drive cedolini | 3 | `drive/sync` resta (usato da scheduler) |
| 8 | ❓ Dati provvisori | 5 | `riconcilia-estratto-conto` resta (scheduler) |
| 9 | ❓ Export | 8 | `/api/exports/*`, incl. `suppliers` — nessun chiamante noto |
| 10 | ❓ Paghe import | 3 | verificare se usati internamente da `documenti.py` |
| 11 | ❓ POS accredito | 5 | candidato forte a rimozione (sostituito da `pos_corrispettivi_check`) |
| 12 | ❓ Report PDF | 4 | `report-pdf/magazzino` incoerente con rimozione HACCP |
| 13 | ❓ Realtime status | 1 | valutare se il websocket è realmente usato |
| 14 | ❓ Trattenute verbali + verbali_noleggio/verbali_riconciliazione | decine | gruppo più ampio, la maggior parte "verificare" nell'ultima classificazione |

---

## FASE 4 — Database (3 operazioni)

**15. ❓ DECISIONE UTENTE — Eseguire le migrazioni canoniche in produzione**
`memoria/PIANO_CONSOLIDAMENTO_COLLECTION.md` (13/07/2026) registra una
scelta esplicita già presa dall'utente: *"preparare il piano, NON toccare i
dati di produzione. Nessuna migrazione è stata eseguita."* Unica eccezione:
F24 modelli (`memoria/PIANO_MIGRAZIONE_COLLECTION.md` §5.1) è ✅ codificata
e idempotente, ma il documento stesso dice *"eseguire contestualmente al
deploy"* — non è confermato che sia già girata in produzione. Prima di
lanciare qualunque migrazione su dati reali chiederò conferma esplicita,
migrazione per migrazione (F24, fatture_passive→invoices,
invoices_emesse→fatture_emesse, employees→dipendenti, payslips→cedolini,
employee_contracts→contratti, documents_classified→documenti_classificati).

**16. ✅ FATTO — `suppliers`/`fornitori`**
Già risolto (non dal report, prima di questa sessione):
`memoria/FORNITORI_REGOLA_CANONICA.md` (aprile 2026) fissa `fornitori` come
unica collection canonica; `suppliers` è solo nome tecnico compatibile che
deve puntare a `fornitori`. Nessuna azione necessaria salvo audit di
conformità puntuale se emergono nuovi hardcoded.

**17. ⛔ Bloccare scritture sulle collection legacy** — dipende da #15.

---

## FASE 5 — Moduli rinviati (3 operazioni)

**18. ⛔ PayPal** — 2 router + 6 service ancora paralleli, consolidamento
esplicitamente rinviato dal report a una sessione dedicata.

**19. ⛔ Verbali** — refactoring router (`verbali_noleggio`,
`verbali_noleggio_api`, `verbali_riconciliazione`, `trattenute_verbali`)
rinviato perché collegato al frontend.

**20. ⛔ Fatture emesse** — armonizzazione campi inglesi/italiani (numero,
data, cliente, imponibile, IVA, totale), serve DTO canonico + migration
adapter.

---

## FASE 6 — Prestazioni (1 operazione articolata)

**21. 🟡 PARZIALE — query illimitate/N+1**
`memoria/AUDIT_PERFORMANCE_N1.md` censisce già le 23 query con
`to_list(50000/100000)` e un'azione consigliata per ciascuna (non una
correzione a blocco: alcune sono aggregazioni finanziarie che richiedono il
set completo). Una correzione già applicata
(`email_document_downloader.py`: tetto esplicito 500000 + log). Restano le
altre ~22 da valutare e correggere una per una.

---

## FASE 7 — CI ed E2E (2 operazioni)

**22. 🟡 PARZIALE — CI completa**
Esistono già 4 workflow: `audit-static.yml` (heuristics statiche, oggi
P1:309 P2:17 P3:54 INFO:16), `smoke-runtime.yml` (smoke runtime su
produzione), `audit-layout.yml` (Playwright, overflow/leggibilità su tutte
le pagine), `verifica-produzione.yml` (bundle atteso vs servito). Mancano
ancora, come blocking check: `route-map-consistency` (vedi #1),
`dead-react-check` (vedi #3/#4), `endpoint-classification`,
`migration-dry-run`, `security-tests` dedicato, `viewer-e2e` per tipo
documento. Il deploy Render non dipende oggi da nessuna di queste CI.

**23. 🟡 PARZIALE — Test viewer per tipo documento × viewport**
`DocumentViewerModal.jsx` è il componente canonico unico (confermato),
`memoria/AUDIT_VIEWER_DOCUMENTI.md` (13/07/2026) ne censisce l'uso in tutto
il frontend, `audit-layout.yml` testa overflow/leggibilità su varie pagine.
Manca la matrice di test automatizzati esatta richiesta dal report (8 tipi
documento × 8 viewport, focus trap/ESC/zoom/fullscreen/download per
ciascuno).

---

## Punti del report già superati (non richiedono nuova azione)

- Dominio Dipendenti: contratti di lavoro e libretti sanitari già rimossi
  dal codice (HR esterno, `memoria/AUDIT_DEFINITIVO_SESSIONE_20260714.md`).
- Suite test: 374 passed, 2 skipped (report ne citava 335) — build Vite
  verificata.
- Pipeline Fatture Estere (AI extraction + coda di verifica + rating)
  implementata e testata (17 test nuovi).

## Prossimo passo proposto

Operazione #1 (rigenerare le mappe e certificare i numeri) è sicura,
non distruttiva e non tocca produzione: può partire subito. Le operazioni
❓ (Fase 3 endpoint, Fase 4 migrazioni, Fase 5 moduli) richiedono una
decisione esplicita dell'utente prima di agire.

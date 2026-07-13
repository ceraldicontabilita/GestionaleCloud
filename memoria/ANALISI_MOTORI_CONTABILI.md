# Analisi motori contabili §6.2–6.9 — decisioni e azioni

> Deliverable della FASE P1 §6 (parte rinviata dopo §6.1). Questi sono sottosistemi
> contabili VIVI: nessuna modifica a blocco. Per ognuno: stato reale, duplicazione,
> rischio, e **decisione/azione**. La §6.3 (schema piano dei conti) è la decisione
> BLOCCANTE che condiziona §6.2 e §6.4.

## §6.1 — ✅ FATTO
Motore unico `app/services/registrazione_contabile.py` (registrazione fatture/
corrispettivi in partita doppia, schema CEE puntato). Vedi commit §6.1.

## §6.3 — Due piani dei conti incompatibili — 🔴 DECISIONE UTENTE
- **Schema CEE puntato** `05.01.01` (`piano_conti` + `contabilita_avanzata` +
  `registrazione_contabile`): è quello usato dal motore §6.1 e dal bilancio di
  `piano_conti`.
- **Schema numerico** `400100` con classificazione CEE (`contabilita_italiana.py`,
  mappa `code/cee/ce`): usato dal ramo "contabilità italiana".
- **Convivono senza tabella di mapping** → mastro/giornale/bilancio possono divergere.
- **Decisione richiesta:** scegliere lo schema canonico (consigliato: CEE puntato,
  già usato dal motore §6.1) e creare una **tabella di mapping/versionamento** numerico↔CEE
  prima di unificare bilancio (§6.2) e saldi. Impedire ai router CEE di scrivere header
  incompatibili in `prima_nota_cassa`.
- **Rischio:** ALTO (tocca bilancio/mastro/giornale/saldo). Non procedere senza scelta.

## §6.3 aggiornato — PIANO CANONICO = quello UFFICIALE del bilancio
L'utente ha fornito il bilancio ufficiale: il piano dei conti canonico è quello CEE del
commercialista (struttura 03/05/07/15/19/23/25/27/29/31/33/35/37/39/41 · 47/51/53/55/57/
59/61/63/65/67/71/75/84), **memorizzato in `app/services/piano_conti_ufficiale.py`**
(231 conti) e documentato in `memoria/PIANO_CONTI_UFFICIALE_CERALDI.md`.
⚠️ I codici INTERNI dell'app collidono con gli ufficiali (interno `05.01.01`=Acquisto
merci vs ufficiale `05`=Immobilizzazioni materiali). Perciò per bilancio/report si
converte SEMPRE all'ufficiale via `mapping_piano_conti.OPERATIVO_A_UFFICIALE`.
Regola resa vincolante in CLAUDE.md.

## §6.2 — Bilancio: 6 implementazioni — 🟡 FONDAMENTA FATTE (mapping → ufficiale)
Implementazioni rilevate: `accounting/piano_conti /bilancio` (fonte: `_calcola_saldi_
piano_conti`), `accounting/contabilita_avanzata /bilancio-dettagliato`,
`contabilita_italiana /bilancio/*`, `accounting/contabilita_gestionale`,
`reports/dashboard`, `openapi_it`.

**Fatto (§6.3 deciso = CEE puntato):** creato `app/services/mapping_piano_conti.py`
(tabella UNICA di corrispondenza) + test:
- `PUNTATO_A_CEE`: ogni conto puntato → voce di bilancio CEE (SP/CE).
- `NUMERICO_A_PUNTATO`: 96 conti numerici → conto puntato (molti-a-uno).
- `classifica_saldi_cee(saldi)`: **vista derivata** pura del bilancio in forma CEE dai
  saldi dei conti puntati (fonte unica) — pronta per far diventare le altre
  implementazioni viste derivate, senza motori paralleli.

**Constatazione tecnica:** il piano puntato (30 conti) è OPERATIVO/semplificato, il
numerico (96) è CIVILISTICO dettagliato. La conversione numerico→puntato è **LOSSY**:
~24 conti sono SOLO_CIVILISTICI (immobilizzazioni, riserve dettagliate, ratei/risconti,
fondi) e NON hanno equivalente puntato (valgono `None`).

**Da confermare con l'utente prima di rewiring dei bilanci:**
1. ~24 conti SOLO_CIVILISTICI: il piano puntato va esteso per rappresentarli o restano
   solo nel ramo civilistico? (il bilancio puntato non mostrerebbe immobilizzazioni/riserve).
2. ~10 corrispondenze marcate `VERIFICARE` nel mapping (approssimazioni macro, es.
   400440 quiescenza→TFR, 400900 oneri diversi→servizi, 230400 debiti banche→banca).
- **Blocco residuo:** il rewiring effettivo dei 6 endpoint bilancio (vista derivata unica)
  cambia l'output → va fatto dopo la conferma dei punti 1-2. Rischio ALTO su quel passo.

## §6.4 — Formula di saldo Prima Nota — ✅ FATTO (cassa/banca)
Creata la funzione UNICA `prima_nota_module/common.aggrega_saldo_prima_nota(db,
collection, query, anno)` (segno entrate/uscite, riporto/saldo iniziale via
`calcola_saldo_anni_precedenti`, saldo finale). `cassa.py` e `banca.py` la usano:
i valori sono invariati (test di caratterizzazione `tests/test_p1_saldo_prima_nota.py`).
- **FOLLOW-UP (scelta contabile):** la query dell'anno diverge leggermente tra cassa
  e banca — `cassa` conta anche i doc con `anno == ""` (via `$in [None, ""]`), `banca`
  no. NON uniformato per non alterare i totali banca senza conferma. Da decidere se
  banca deve adottare la stessa query robusta di cassa.
- **Restano** da convogliare sulla funzione unica: `stats.get_saldo_finale`
  (itera i movimenti con logica propria) e `manutenzione` (usa dict già calcolati).

## §6.5 — Cespiti: `cespiti.py` vs `contabilita_italiana /cespiti/*`
Due sistemi di registrazione cespiti/ammortamenti.
- **Azione:** scegliere il modello canonico (`cespiti.py` scrive `cespiti` + genera
  movimenti ammortamento letti dalla chiusura esercizio) e migrare/deprecare l'altro.
- **Rischio:** MEDIO. Da valutare quale ha i dati reali.

## §6.6 — Estratto conto importer — ✅ VERIFICATO (già adapter corretto)
- Canonico: `bank/estratto_conto.py` (scrive `estratto_conto_movimenti`).
- `bank/bank_statement_import.py` (parser PDF/Excel multi-banca, **FE-wired**):
  **già convoglia i MOVIMENTI nella canonica `estratto_conto_movimenti`** (riga 850,
  con dedup + alert BNK_DUPLICATO). `bank_statements_imported` contiene SOLO i metadati
  livello-documento dello statement caricato e **non ha alcun lettore di riconciliazione**
  → NON è una sorgente parallela. Nessun ricablaggio necessario.
- **Nota perf (audit §11):** l'insert dei movimenti è un `find_one`+`insert_one` per
  riga (N+1) con dedup/alert per-movimento; non convertibile a bulk senza perdere la
  semantica di dedup. Import occasionale, non hot path: lasciato.

## §6.7 — PayPal — dominio dedicato
Unificare mapping fornitore, stati, pipeline riconciliazione, origine statement/API,
idempotenza. È un dominio ampio già parzialmente consolidato (task #23/#31).
- **Azione:** audit dedicato del flusso PayPal (paypal_api/paypal_statements/
  paypal_email_recovery) prima di unificare. Rischio MEDIO.

## §6.8 — Prima Nota Cassa: `cash.py` — ✅ FATTO (adapter)
Verifica: `Collections.CASH_MOVEMENTS` **è già** `prima_nota_cassa` (nessuna collezione
`cash_movements` separata), e `/api/cash` **non è usato da nessuna pagina** (funzioni
`getCashMovements`/`createCashMovement` in api.js senza chiamanti). Quindi nessuna doppia
scrittura su collezioni diverse; il difetto era solo lo schema inglese (`type/amount`)
che il saldo Prima Nota (che aggrega su `tipo/importo/data/status`) ignorava.
- **Fatto:** `cash_service.create_movement` ora scrive ANCHE i campi canonici italiani
  (tipo/importo/data/categoria/status/anno + `fonte="cash_adapter"`) mantenendo quelli
  inglesi → il movimento è visto dal saldo Prima Nota. Adapter senza doppia scrittura.
- Test `tests/test_p1_cash_adapter.py`. Rischio basso (endpoint FE-inutilizzato).

## §6.9 — Verbali: tre router
`verbali_noleggio`, `verbali_noleggio_api`, `verbali_riconciliazione`. Separare
chiaramente ingest / CRUD / riconciliazione con uno schema comune.
- **Azione:** definire lo schema verbale comune e assegnare a ciascun router un ruolo
  unico (ingest vs CRUD vs riconciliazione) evitando sovrapposizioni. Rischio MEDIO.

---

## Ordine consigliato (dal più sicuro)
1. **§6.4 saldo Prima Nota** — funzione unica + test di caratterizzazione (nessun
   cambio di valore).
2. **§6.6 EC importer** — documentare l'adattatore e verificare che non resti sorgente
   parallela di riconciliazione.
3. **§6.3 schema piano dei conti** — 🔴 DECISIONE UTENTE (blocca §6.2).
4. **§6.2 bilancio** — dopo §6.3: una fonte, viste derivate.
5. **§6.8 cash adapter**, **§6.5 cespiti**, **§6.9 verbali**, **§6.7 PayPal** — ognuno
   con test di caratterizzazione prima di unificare.

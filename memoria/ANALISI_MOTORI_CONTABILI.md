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

## §6.2 — Bilancio: 6 implementazioni — dipende da §6.3
Implementazioni rilevate: `accounting/piano_conti /bilancio` (fonte: `_calcola_saldi_
piano_conti`), `accounting/contabilita_avanzata /bilancio-dettagliato`,
`contabilita_italiana /bilancio/*`, `accounting/contabilita_gestionale`,
`reports/dashboard`, `openapi_it`.
- **Azione:** eleggere UNA fonte contabile (i saldi calcolati da `piano_conti._calcola_
  saldi_piano_conti`, già "fonte unica di verità" del suo bilancio) e trasformare le
  altre in **viste derivate**, non motori indipendenti. Endpoint canonici documentati.
- **Blocco:** richiede prima §6.3 (schema). Rischio ALTO.

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

## §6.6 — Estratto conto importer — AZIONE SICURA (documentazione)
- Canonico dichiarato: `bank/estratto_conto.py` (scrive `estratto_conto_movimenti`).
- `bank/bank_statement_import.py`: parser PDF/Excel multi-banca che scrive
  `bank_statements_imported` (collezione separata), **FE-wired** (ControlloMensile,
  RiconciliazionePaypal) → NON rimuovibile.
- **Azione:** mantenerlo come **adattatore di import** documentato; il suo output va
  convogliato nella canonica `estratto_conto_movimenti` a valle (verificare che non
  resti una sorgente parallela per la riconciliazione).
- **Rischio:** BASSO se solo documentazione; MEDIO se si ricabla l'output.

## §6.7 — PayPal — dominio dedicato
Unificare mapping fornitore, stati, pipeline riconciliazione, origine statement/API,
idempotenza. È un dominio ampio già parzialmente consolidato (task #23/#31).
- **Azione:** audit dedicato del flusso PayPal (paypal_api/paypal_statements/
  paypal_email_recovery) prima di unificare. Rischio MEDIO.

## §6.8 — Prima Nota Cassa: `cash.py`/`cash_movements` — AZIONE (adapter)
`cash.py` (+ `cash_service.py` + `cash_repository`) è un sistema cassa PARALLELO che
scrive `cash_movements`, **FE-wired** (`/api/cash` in api.js) → NON eliminabile.
La canonica è `prima_nota_cassa`.
- **Azione:** trasformare `cash.py` in **adapter** verso `prima_nota_cassa` SENZA
  doppia scrittura (una sola collezione reale), preservando l'API `/api/cash` usata dal
  frontend. Richiede mappare gli schemi cash_movements↔prima_nota_cassa.
- **Rischio:** MEDIO-ALTO (cassa viva col frontend). Fare con test di caratterizzazione.

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

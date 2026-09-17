# AUDIT SCHEDULER TEMPERATURE — Tranche 6 (24/07/2026)

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

> FATTO ACQUISITO (correzione esplicita del titolare): **le temperature NON
> sono manuali — vengono registrate automaticamente dallo scheduler.**
> L'audit parte da qui. Test: `backend/tests/test_audit_tranche6.py`
> (sezioni 3 e 4), su mongomock (DB "Gestionale_Test"), mai produzione.

## RISULTATO IN SINTESI

| Verifica richiesta | Esito |
|---|---|
| Acquisizione periodica | OK — job 07:00 + catchup all'avvio (verificato su codice + test della funzione) |
| Deduplicazione letture | OK — verificata con test (secondo giro non tocca il dato) |
| Letture fuori soglia generate dal job | **DIFETTO CORRETTO** — il clamp congelatori permetteva valori sopra -18 °C |
| Anomalie che spariscono cambiando le soglie retroattivamente | **DIFETTO GRAVE CORRETTO** — soglie ora congelate nel record |
| Sensore offline / buchi | PARZIALE — buchi possibili se il backend dorme un giorno intero; i buchi ORA sono dichiarati in stampa ("N/D"), non marcati a DB (vedi finding 3) |
| Storico conservato | OK — schede annuali per apparecchio, mai sovrascritte |
| Uso nelle stampe/registri | OK dopo fix (vedi AUDIT_REGISTRI_STAMPE.md) |

---

## 1. COME FUNZIONA DAVVERO (codice reale)

- Scheduler APScheduler avviato dallo startup di FastAPI
  (`backend/server.py:212-213` → `backend/routers/scheduler.py:507-614`).
- Job `haccp_daily_generation` alle **07:00 Europe/Rome**
  (scheduler.py:535-541) → `job_genera_haccp_giornaliero` (scheduler.py:214-277)
  → `verifica_e_popola_oggi` (`backend/routers/haccp_auto.py:293-496`).
- Per OGNI scheda `temperature_positive`/`temperature_negative` dell'anno:
  se il giorno è già compilato NON tocca nulla (haccp_auto.py:362-364,
  415-417 — questa è la deduplicazione); altrimenti genera la lettura
  automatica `{temp, operatore, note, timestamp, auto: true}` con seed
  giornaliero stabile (haccp_auto.py:307) e la salva PERMANENTEMENTE.
- Esito loggato in `scheduler_logs` (scheduler.py:236-247), visibile da
  `GET /api/scheduler/logs` e `GET /api/scheduler/stato` (759-771, 701-719).
- **Catchup**: APScheduler è in-memory; se il backend riparte dopo le 07:00
  senza log di oggi, il job viene eseguito subito (`_catchup_jobs_mancanti`,
  scheduler.py:609-683). Anche gli automatismi ogni-5-giorni hanno catchup
  (665-681). Rilancio manuale: `POST /api/scheduler/run-haccp-now`
  (scheduler.py:752-756).
- Registrazioni conformi periodiche olio/cotture: `automatismi_haccp.py:38-103`
  — idempotenti sulla giornata (find_one su data prima dell'insert,
  automatismi_haccp.py:45-46, 77-79).

## 2. FINDING

### 2.1 — GRAVE (CORRETTO): le anomalie si RISCRIVEVANO cambiando le soglie
**Prima**: `GET /temperature-positive/allarmi/{anno}` e la gemella negativa
ricalcolavano gli allarmi confrontando ogni lettura storica con i
`temp_min`/`temp_max` CORRENTI della scheda (vecchie
temperature_positive.py:307-309 / temperature_negative.py:299-301). Le soglie
sono modificabili da `PUT /scheda/{anno}/{n}/config`
(temperature_positive.py:265, temperature_negative.py:257).
**Scenario concreto di fallimento**: a marzo il Frigo 1 segna 6,5 °C
(anomalia registrata, ASL può chiederne conto); a luglio un admin porta
temp_max a 10 per un frigo bibite → l'anomalia di marzo SPARISCE da
allarmi, report e stampe. Vale anche al contrario: stringendo le soglie
comparivano anomalie mai esistite.
**Fix (circoscritto)**:
- Alla registrazione le soglie del momento vengono CONGELATE nel record:
  `record["allarme"]` + `record["soglie"]={min,max}`
  (temperature_positive.py:215-231, temperature_negative.py:206-226).
- `get_allarmi` usa le soglie salvate nel record quando presenti; i record
  storici senza soglie continuano a usare quelle correnti (retrocompatibile)
  (temperature_positive.py:294-345, temperature_negative.py:286-337).
- Anche le letture AUTOMATICHE del job salvano `soglie` + `allarme:false`
  (haccp_auto.py:377-389, 432-444).
- Il report mensile valuta la conformità con le soglie del record
  (report_haccp.py:80-113, 141-152, 247-259).
**Test**: `test_allarme_non_sparisce_cambiando_le_soglie` (allarga soglie →
l'anomalia resta, con il range del momento; stringe soglie → la lettura
conforme NON diventa anomalia) e `test_allarme_congelatore_congela_soglie`.
**Stato: difetto corretto.** NB: per i record storici PRE-fix la valutazione
resta con le soglie correnti (non c'è modo di sapere le soglie di allora);
da qui in avanti la storia è immutabile.

### 2.2 — MEDIO (CORRETTO): il job generava letture congelatori FUORI SOGLIA
**Prima**: clamp `max(-25.0, min(-15.0, base+jitter))` (vecchia
haccp_auto.py:412) con basi come -17,5/-18,3 (BASE_NEG, haccp_auto.py:396-408)
→ il congelatore 8 (base -17,5) produceva quasi ogni giorno una "lettura
automatica" tra -18,5 e -16,5, cioè sopra la soglia massima -18 °C, in
contraddizione con la regola dichiarata "i valori generati sono SEMPRE
CONFORMI" (automatismi_haccp.py:4-6) e senza alcuna anomalia registrata.
**Scenario concreto**: il registro annuale del congelatore 8 stampato per
l'ASL mostra decine di giorni in rosso mai gestiti da nessuno.
**Fix**: il clamp usa le soglie REALI della scheda (default -22/-18 e 0/4),
proiezione estesa a `temp_min`/`temp_max` (haccp_auto.py:356-359, 366-373,
409-431). **Test**: `test_scheduler_temperature_sempre_entro_soglie_scheda`
(usa proprio il congelatore 8) e `test_scheduler_temperature_genera_e_non_duplica`
(dedup: il secondo giro non sovrascrive — sentinella intatta).
**Stato: difetto corretto.**

### 2.3 — MEDIO (PARZIALE, da completare): buchi se il backend dorme
APScheduler è in-memory (scheduler.py:612-613): se il servizio Render resta
giù/addormentato l'intero giorno X e riparte il giorno X+1, il catchup
esegue solo il job "di oggi" (`verifica_e_popola_oggi` scrive SOLO la data
odierna, haccp_auto.py:309-315): il giorno X resta un buco permanente a DB.
**Mitigazioni esistenti**: keep-warm 04:00-23:00 (scheduler.py:486-520),
catchup all'avvio, e da questa tranche il buco è DICHIARATO in stampa come
"N/D = Dato non disponibile" (mai cella vuota/riga saltata — vedi
AUDIT_REGISTRI_STAMPE.md). **Manca**: marcare a DB i giorni passati senza
lettura (es. record `{"is_non_rilevato": true}`) o un catchup multi-giorno.
Gravità: MEDIA. **Stato: da correggere** (non fatto ora: cambia il
comportamento del job su più giorni e va concordato; la stampa è già onesta).

### 2.4 — BASSO (documentato): endpoint di popolamento storico non protetti
`POST /haccp-auto/popola-temperature`, `/popola-sanificazione`,
`/popola-tutto`, `/genera-oggi` (haccp_auto.py:58, 198, 274, 481) e
`POST /temperature-positive|negative/popola-con-chiusure/{anno}`
(temperature_positive.py:371, temperature_negative.py:363) generano dati
storici retroattivi e NON richiedono `require_admin` (a differenza di
`/config`). Anche `PUT /scheda/{anno}/{n}` (aggiorna_scheda_completa,
temperature_positive.py:246, temperature_negative.py:240) sostituisce
l'INTERA scheda annuale senza admin. Scenario: un dipendente (o un tablet
compromesso) riscrive un anno di temperature. Gravità: MEDIA per il PUT,
BASSA per i popola (additivi, non sovrascrivono). **Stato: CORRETTO
25/07/2026** — `require_admin` aggiunto a tutti e otto: PUT scheda intera
(positive e negative), popola-con-chiusure (positive e negative),
popola-temperature, popola-sanificazione, popola-tutto, genera-oggi. La rete
di sicurezza è in tests/test_auth_permessi.py, che ora li verifica per firma
(cercando il decorator esatto, perché lo stesso path esiste anche in GET).

### 2.5 — Nota (nessuna azione): "sensore offline" non esiste come concetto
Non c'è hardware: lo "scheduler" È il sensore. Il caso "sensore offline"
coincide con il finding 2.3 (backend giù). I giorni di chiusura/manutenzione
sono già gestiti come stati speciali espliciti
(`is_chiuso/is_manutenzione/is_non_usato`, temperature_positive.py:449-466)
ed esclusi dagli allarmi (get_allarmi li salta, temperature_positive.py:305-312).

## 3. STORICO E USO NEI REGISTRI
- Storico: una scheda per apparecchio per ANNO
  (`{anno, frigorifero_numero, temperature: {mese: {giorno: record}}}`,
  temperature_positive.py:94-146); il job non sovrascrive mai (dedup 2.2);
  niente rotazione/cancellazione delle schede temperature (verificato: nessun
  delete su queste collection in tutto backend/routers).
- Stampe: report mensile `GET /api/report-haccp/mensile`
  (report_haccp.py:353-433) — generato DAVVERO nei test e confrontato col DB
  (vedi AUDIT_REGISTRI_STAMPE.md).

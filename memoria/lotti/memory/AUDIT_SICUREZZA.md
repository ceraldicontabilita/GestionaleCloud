# AUDIT SICUREZZA — fase 2 ristrutturazione (24/07/2026)

## Modello (VERIFICATO)
- `auth_dependency` su TUTTO /api: scritture sempre col token (tranne la
  whitelist dei gesti tablet), letture protette con AUTH_ENFORCE=true
  (default). NON guarda il ruolo.
- `require_admin` = unico gate di ruolo (JWT amministratore o X-Admin-Pin),
  da dichiarare endpoint per endpoint.
- Il frontend allega il token a OGNI chiamata (interceptor axios) e gestisce
  il 401 azzerando il token. Ruolo/reparto NON vengono creduti dal client:
  il ruolo sta NEL token firmato.

## Interventi fatti (COMPLETATO — verificato da import-check + 9 test)
`require_admin` aggiunto a 29 endpoint distruttivi/di configurazione che un
token DIPENDENTE poteva chiamare:
- fatture: DELETE /{id}, POST /dedup, POST /importa-annulla
- lotti_fornitori: reimporta-da-fatture (azzera!), pulizia-scaduti
- scheduler: start, stop, run-pulizia-lotti-now
- normalizzazione: ripulisci-dizionario-canonici, pulisci-falsi-positivi,
  DELETE fornitori-config
- temperature positive/negative: PUT …/config (LIMITI temperatura — un
  operatore poteva allargarli e far sparire le anomalie HACCP)
- magazzino_bar: pulizia-non-merce (GET anteprima + POST), accorpa-categoria
- food_cost: DELETE dizionario/{id}, DELETE dizionario/manuale/{nome}
- schede_tecniche: DELETE elimina; fonti_catalogo: DELETE fonte
- catalogo_forno: importa, importa-precaricato, DELETE prodotto
- ricette: pulisci-riferimenti-congelati, pulisci-ingredienti, import CSV,
  importa-tracciabilita
- prodotti_vendita: DELETE cascade; controllo_dati: pulisci-log-obsoleti
Già protetti in precedenza: backup (4), diagnostic, pulizia-spazzatura,
tablet_operatori (crea/abilita/patch/ignora), ordini (conferma/invio),
ricostruisci-giacenze-bar, sync dizionario food_cost.
Test anti-regressione: `backend/tests/test_auth_permessi.py` (token assente/
scaduto/manomesso, whitelist tablet, rotte pubbliche, e verifica che gli
endpoint protetti DICHIARINO require_admin).

## Gestione errori backend (VERIFICATO dall'audit dedicato)
- ~350 blocchi except esaminati: 0 PERICOLOSI (nessuna scrittura primaria o
  controllo auth silenziato); pattern corretto "scrittura fuori dal try".
- Log contestuali aggiunti nei 2 punti principali (ricalcolo scadenze lotti,
  admin-check ordini). PARZIALE: restano ~8 best-effort senza log (fonti
  catalogo, schede tecniche, drive, stampa, acquaviva) — innocui, elencati
  nell'output dell'audit in STATO.md.

## Da fare / rischio residuo
- MEDIA: eliminazioni di SINGOLI record operativi (lotto, produzione,
  anomalia, gelati, attrezzature, ordine, collaudo…) restano aperte a ogni
  token valido — scelta deliberata per ora: sono gesti di lavoro quotidiano
  e il titolare non ha chiesto di vietarli ai dipendenti. Da rivedere con
  Enzo se vuole limitare anche questi (es. DELETE /lotti/{id}).
- MEDIA: sync/import massivi di cataloghi e listini (acquaviva, listino
  sync-da-fatture, sconti_merce, drive sync) senza gate di ruolo.
- BASSA: silenzia-alert del Supervisore per alert medi/alti (i critici sono
  già non silenziabili).
- I test con DB (lotto inesistente, dedup fattura, FIFO end-to-end,
  quantità insufficiente, registrazione HACCP non valida) NON sono stati
  aggiunti: richiedono un Mongo di test (mongomock non installato; vietato
  usare Atlas reale). DA FARE in una fase dedicata.

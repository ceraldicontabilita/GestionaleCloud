# PIANO RESIDUO AGGIORNATO — GESTIONALECLOUD

## Fonte di verità

Questo documento è stato ricalcolato usando esclusivamente lo stato più recente del repository su `main`:

- commit corrente verificato: `16dcc57040439439d9500c0d10e38a7072ae9c23`;
- `memoria/INDEX.md`;
- `memoria/AUDIT_ATOMICO_APPLICAZIONE.md`;
- mappe rigenerate della route table reale;
- documenti correnti di endpoint, moduli e collection.

Gli audit storici superati non devono essere usati per riaprire attività già completate.

---

# 1. Attività già completate — NON RIPETERE

Non devono essere nuovamente richieste a Claude:

- fornitori canonici su `fornitori`, non `suppliers`;
- dipendenti canonici su `dipendenti`, non `employees`;
- cedolini canonici su `cedolini`;
- F24 canonici su `f24_unificato`;
- estratto conto canonico su `estratto_conto_movimenti`;
- fatture passive canoniche su `invoices`;
- rimozione del dominio HACCP operativo dal GestionaleCloud;
- rimozione contratti di lavoro e libretti sanitari dal dominio dipendenti;
- riduzione del router dipendenti;
- motore IVA con regola del 15 e anti-doppia-detrazione;
- motore F24/tributi e fiscale;
- quietanza senza F24 con alert bloccante;
- gestione DM10/RC01 e possibile doppio pagamento;
- viewer documentale canonico;
- sostituzione della maggior parte di `alert`, `confirm`, `prompt` e `window.open`;
- middleware globale di autenticazione;
- protezione endpoint distruttivi;
- saldo Prima Nota tramite motore unico;
- Piano dei Conti ufficiale con mapping;
- correzione dei 12 bug P0 già coperti da test;
- rimozione di Emergent e del codice morto già censito;
- build Vite e suite test già eseguite nelle sessioni precedenti;
- nuova pipeline Fatture Estere;
- audit atomico e mappe aggiornate al 14/07/2026.

Quando Claude incontra queste voci deve limitarvisi a verificarne l’assenza di regressioni, non ricostruirle.

---

# 2. Attività residue reali

## P0 — allineamento e verità unica dei report

### 2.1 Rigenerare tutti gli inventari sullo stesso commit

Esistono documenti di audit generati in momenti diversi. Deve esistere una sola fotografia coerente.

Eseguire sul medesimo commit:

```bash
python scripts/genera_mappa.py
python scripts/genera_classificazione_endpoint.py
```

Rigenerare insieme:

- `MAPPA_ROUTER.md`;
- `MAPPA_ENDPOINT_COMPLETA.md`;
- `MAPPA_COLLEZIONI.md`;
- `ENDPOINT_CLASSIFICAZIONE_FINALE.md`;
- `AUDIT_ATOMICO_APPLICAZIONE.md`.

Aggiungere un test che fallisca quando i totali non coincidono.

---

## P1 — eliminazione endpoint realmente inutili

La route table corrente monta circa 1059 endpoint. I prefissi senza riferimento frontend non sono automaticamente morti, ma devono essere classificati usando:

- frontend;
- scheduler;
- Chat;
- webhook;
- app esterne;
- test;
- manutenzione;
- migrazioni.

### Gruppi prioritari

Verificare uno per uno:

```text
/api/batch
/api/cedolini
/api/dati-provvisori
/api/exports
/api/paghe
/api/pos-accredito
/api/realtime
/api/report-pdf
/api/trattenute-verbali
```

Regola:

- se non esiste alcun chiamante reale, smontare l’endpoint dal router registry;
- eliminare poi codice e test inutili;
- se il parser serve internamente, mantenere il servizio ma rimuovere la route HTTP non usata;
- aggiornare le mappe dopo ogni eliminazione.

Non eliminare:

- scheduler Drive cedolini;
- parser F24 e Libro Unico usati internamente;
- webhook;
- Chat;
- API esterne documentate;
- endpoint manutentivi ancora necessari.

---

## P1 — audit reale del frontend inutilizzato

Non risulta ancora un inventario autoritativo corrente dei React inutilizzati.

Creare:

```text
scripts/audit_frontend_dead_code.py
memoria/AUDIT_FRONTEND_DEAD_CODE.md
```

Entry point:

```text
frontend/src/main.jsx
frontend/src/App.jsx
frontend/src/navigation.config.js
```

Il controllo deve riconoscere:

- import statici;
- import dinamici;
- `lazy(() => import())`;
- route;
- menu;
- modali;
- hook;
- store;
- test.

Classificazioni:

```text
ENTRYPOINT
ROUTE_ATTIVA
COMPONENTE_USATO
MODALE_USATO
HOOK_USATO
TEST_ONLY
DINAMICO_DA_VERIFICARE
ORFANO_ELIMINABILE
```

Eliminare solo `ORFANO_ELIMINABILE`.

Dopo ogni gruppo:

```bash
cd frontend
yarn build
yarn lint
```

---

## P1 — completare l’adozione di `app/db_collections.py`

`INDEX.md` stabilisce le collection canoniche, ma `database.py::Collections` è ancora dichiarata legacy e l’uso reale delle costanti canoniche non è completo.

Fare:

1. trovare tutte le stringhe collection hardcoded;
2. sostituirle con costanti;
3. trasformare `Collections` in alias delle costanti oppure eliminarla;
4. aggiungere un test statico che blocchi nuovi nomi hardcoded;
5. non riaprire la decisione `fornitori`, `dipendenti`, `cedolini`, `invoices`, `f24_unificato`.

---

## P1 — verificare migrazioni realmente eseguite

Non basta che gli script esistano.

Per ogni migrazione canonica controllare nel database di produzione:

- sorgente;
- destinazione;
- documenti copiati;
- duplicati;
- errori;
- scritture legacy successive alla migrazione.

Produrre un verbale:

```text
memoria/VERIFICA_MIGRAZIONI_PRODUZIONE.md
```

Le fonti canoniche restano:

```text
fornitori
dipendenti
cedolini
invoices
f24_unificato
estratto_conto_movimenti
documenti_classificati
```

---

## P1 — sistemi paralleli ancora da decidere

### PayPal

Il consolidamento risulta rinviato.

Unificare:

- due router;
- service paralleli;
- mapping fornitore;
- import statement/API;
- stati;
- riconciliazione;
- idempotenza.

### Verbali

Restano più router collegati al frontend.

Definire un’architettura unica:

```text
ingest
CRUD
riconciliazione
trattenute
```

con schema e collection canonici.

### Fatture emesse

Armonizzare i campi duplicati italiano/inglese mediante DTO canonico e adapter di migrazione, senza rompere l’app esterna.

---

## P1 — prestazioni ancora aperte

L’audit segnala query molto grandi e N+1 ancora da analizzare.

Per ogni caso censito:

- misurare;
- classificare interattivo/report;
- sostituire `to_list(100000)` se usato da API interattiva;
- usare aggregation, cursor, `$in`, `bulk_write`;
- introdurre paginazione reale;
- aggiungere soglie di durata.

Priorità:

- sincronizzazione relazionale;
- fatture;
- estratto conto;
- Prima Nota;
- documenti;
- scheduler.

---

## P1 — viewer: verifica dinamica finale

`DocumentViewerModal` esiste già. Non ricostruirlo.

Manca la certificazione dinamica completa di:

- fatture ASSO HTML;
- fatture PDF;
- cedolini;
- F24;
- quietanze;
- PagoPA;
- verbali;
- documenti non associati.

Viewport:

```text
320×568
360×800
390×844
412×915
768×1024
1024×768
1366×768
1920×1080
```

Verificare:

- fit schermo;
- zoom;
- fullscreen;
- download;
- scroll interno;
- chiusura;
- focus;
- autorizzazione;
- rotazione.

---

## P2 — CI obbligatoria su main

Creare o verificare workflow GitHub Actions con:

```text
backend-tests
frontend-build
frontend-lint
route-map-consistency
endpoint-classification
frontend-dead-code
security-tests
viewer-e2e
```

Il deploy Render deve avvenire solo dopo CI verde.

---

# 3. Attività da eliminare dai vecchi prompt

Rimuovere dai futuri prompt qualsiasi richiesta di:

- scegliere tra `fornitori` e `suppliers`;
- migrare nuovamente `employees` senza prima verificare lo stato già consolidato;
- ricostruire il motore IVA;
- ricostruire il motore F24;
- ricostruire il viewer;
- ripetere i 12 bug P0 già chiusi;
- rimuovere nuovamente HACCP;
- ricostruire ruoli, PIN o middleware auth;
- ricreare il Piano dei Conti ufficiale;
- ripetere audit storici già superati.

---

# 4. Regola di aggiornamento per Claude

Questo file deve essere aggiornato man mano.

Quando un’attività è completata:

1. eliminarla da “Attività residue reali”;
2. inserirla in “Completato dopo il 14/07/2026”;
3. indicare:
   - commit;
   - file modificati;
   - test;
   - risultato;
4. rigenerare le mappe;
5. non lasciare duplicazioni tra fatto e da fare.

---

# 5. Criterio finale

Il lavoro residuo è concluso quando:

- tutti i conteggi tecnici sono coerenti sullo stesso commit;
- non esistono endpoint senza un chiamante o una motivazione documentata;
- non esistono file React orfani;
- tutte le collection sono richiamate tramite registro canonico;
- le migrazioni risultano verificate in produzione;
- PayPal, verbali e fatture emesse hanno una decisione architetturale unica;
- le query critiche sono ottimizzate;
- i viewer sono certificati dinamicamente;
- CI è verde su `main`;
- Claude ha rimosso dal file tutte le attività completate.

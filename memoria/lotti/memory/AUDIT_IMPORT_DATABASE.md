# AUDIT IMPORT & DATABASE — Tranche 6 (24/07/2026)

> Audit basato sul CODICE REALE (ogni affermazione con file:riga) e su test
> eseguiti SOLO su database di prova (mongomock-motor, DB "Gestionale_Test",
> zero rete): `backend/tests/test_audit_tranche6.py` (14 test, tutti verdi).
> Nessun dato di produzione toccato. Documenti gemelli:
> `AUDIT_SCHEDULER_TEMPERATURE.md` e `AUDIT_REGISTRI_STAMPE.md`.

## RISULTATO IN SINTESI

| Area | Esito |
|---|---|
| Import fatture XML (manuale/Drive/PEC) | Verificato OK con test: dedup fattura, dedup per riga, scarti segnalati, collegamenti creati |
| Catena fattura → lotto fornitore → produzione → banco → registri | Verificata OK con test sulle chiavi reali; 2 punti deboli documentati (sotto) |
| Troncamento registri a 2000/1000 record | DIFETTO CORRETTO (vedi AUDIT_REGISTRI_STAMPE.md) |
| Anomalie temperature ricalcolate con soglie correnti | DIFETTO GRAVE CORRETTO (vedi AUDIT_SCHEDULER_TEMPERATURE.md) |
| Pagina "Verifica integrità gestionale" | PROPOSTA in fondo a questo documento (non implementata, come da brief) |

---

## 1. PUNTI D'INGRESSO DATI (mappa completa)

### 1a. Import fatture XML manuale — `POST /api/fatture/importa-xml`
`backend/routers/fatture.py:459-1015` (`importa_fattura_xml`).

Flusso per ogni file (accetta XML, ZIP con più XML, .p7m — espansione a
fatture.py:524-542):
1. **Parse** `parse_fattura_xml` (routers/xml_helpers.py). Fornitore mancante →
   riga in `risultati["errori"]` e file saltato (fatture.py:557-559).
2. **Fornitori esclusi** → `fatture_saltate_escluse` (fatture.py:561-563);
   `solo_magazzino` → lotti creati con flag, fuori dalle ricette (565-568).
3. **Dedup fattura**: upsert su `numero_fattura+piva` (chiave allineata
   all'indice unico `uniq_numero_piva` condiviso con Gestionale Cloud,
   fatture.py:591-615); senza P.IVA ricade su fornitore+numero+data; su
   collisione con fornitore DIVERSO senza P.IVA conserva ENTRAMBE con piva
   surrogata `ND:<fornitore>` e `verifica_richiesta=true` (616-645, tranche 4).
4. **Fornitore** creato se nuovo con `in_attesa=True` (648-659); anagrafica
   aggiornata con upsert + contatti estratti dall'XML (667-712).
5. **Lotti fornitori**: una riga fattura = un documento `lotti_fornitori`, con
   dedup per riga su `fattura_ref+fornitore+prodotto_nome` (fatture.py:741-774).
   Quantità non parsabile → default 1 (728-732), prezzo non parsabile → 0
   (733-740): il record incompleto viene comunque salvato (scelta consapevole:
   la giacenza esiste anche se la riga è sporca).
6. **Listino** (`listino_prodotti`, 786-837), **aliases dizionario** (838-864),
   **match ingredienti ricette** (867-920), **dizionario_prodotti** con
   giacenze/prezzo_kg e controllo plausibilità 10x (`aggiorna_dizionario_prodotto`,
   fatture.py:1397-1622; prezzo non parsabile → warning nei log, 1413-1419),
   **riconciliazione ordini** (941-952). Poi pipeline post-import in background
   e aggiornamento ricette (957-998).

**Conteggi restituiti** (fatture.py:464-472): `fatture_processate`,
`fatture_saltate_escluse`, `prodotti_trovati`, `nuove_materie`,
`materie_aggiornate`, `match_ingredienti`, `errori[]` — verificati con test:
- `test_import_contatori_righe_e_dedup_per_riga`: 1 fattura 2 righe →
  processate=1, prodotti_trovati=2, nuove_materie=2, 2 lotti_fornitori,
  2 voci listino, dizionario aggiornato; re-import → sempre 1 fattura e 2 lotti.
- `test_import_fattura_senza_fornitore_scartata_con_errore`: scarto SEGNALATO,
  0 documenti scritti.
- `test_import_file_non_xml_segnalato`: errore in `errori[]`, niente crash.

### 1b. Import da Drive condiviso (scheduler, ogni 30 min)
`backend/routers/drive_fatture.py:283-394` (`esegui_sync_drive`), job in
`backend/routers/scheduler.py:465-483,594-600`. RIUSA la stessa pipeline
dell'import manuale (drive_fatture.py:338,357) → stessa dedup. Registro
incrementale `drive_fatture_file` con doppia chiave `drive_id` + `md5`
(311-333): il file già visto non si riscarica, la copia con altro id
(cartella "Elaborate") viene marcata `duplicato` (344-354). Errori registrati
per file e non ritentati in loop (376-385); stato in `drive_fatture_stato`
(387-393). **Verificato su codice** (l'accesso a Drive non è possibile in
sandbox: la parte HTTP è NON verificabile qui — il riuso della pipeline sì,
ed è testato via import manuale).

### 1c. Import PEC — `POST /api/pec/import`
Documentato in memory/claude.md:192; dedup PEC salta `numero_fattura==""`
(fix v55). Endpoint live non raggiungibile dalla sandbox: **non verificabile
in sandbox** (nessuna credenziale PEC nei test, come da regole).

### 1d. Creazione manuale / produzione / gelati / ricezione
Unico punto di scrittura lotti: `backend/servizi/lotti_service.py:74-128`
(`crea_lotto`) — id/created_at garantiti, campi canonici
(`numero_lotto`, `prodotto`, `stato`, `esaurito`), `posizione` costruita da
`frigo_numero`, evento `LOTTO_CREATO`, primo movimento `creazione` in
`movimenti_lotto` (113-126, non bloccante). Verificato con test
(`test_catena_completa_chiavi_reali`).

### 1e. Seed all'avvio (`server.py:207-230`)
`seed_operatori`, `seed_magazzino_bar`, `seed_panini_rosticceria`
(server.py:195-204, upsert per nome → idempotente), `seed_ricette_solo_nome`
(one-shot con flag in `sistema_stato`), `crea_indici`. Tutti idempotenti per
costruzione (upsert o flag una-tantum). Verificato su codice.

### 1f. Scheduler (scritture automatiche)
Vedi `AUDIT_SCHEDULER_TEMPERATURE.md`. Collezioni scritte: `temperature_positive`,
`temperature_negative`, `sanificazione_schede` (+sync vecchio schema
`sanificazione`), `controllo_olio`, `temperature_cottura`, `reclami_fornitori`,
`scheduler_logs`, bozze ordini, task dipendenti, backup.

---

## 2. INTEGRITÀ RELAZIONALE DELLA CATENA (chiavi reali, verificate con test)

Catena completa collaudata in `test_catena_completa_chiavi_reali` e
`test_registra_produzione_scrive_produzioni_e_lotto_collegati`:

| Anello | Chiave reale | Dove |
|---|---|---|
| fattura → lotto fornitore | `lotti_fornitori.fattura_ref` = `fatture.numero_fattura` (+`fornitore`, `data_fattura`) | fatture.py:767-768 |
| lotto fornitore → produzione | `lotti_fornitori.storico_utilizzi[].lotto_produzione` = `numero_lotto` | lotti_produzione.py:1129-1137 |
| produzione → lotto produzione | `produzioni.numero_lotto` = `lotti.numero_lotto`; `produzioni.lotti_scalati_dettaglio` (per lo storno) | lotti_produzione.py:1414-1434 |
| lotto → banco/vendita | `vendite_banco.lotto_id` = `lotti.id`, `numero_lotto` | vendita_banco.py:64-65, lotti_produzione.py:522-532 |
| ogni passaggio → registro movimenti | `movimenti_lotto.lotto_id` + `documento_collegato {tipo,id}` (unico writer `servizi/movimenti_lotto_service.py::registra_movimento`) | lotti_produzione.py:534-549 |
| lotto → registri HACCP stampati | registro mensile/annuale/ASL leggono `db.lotti` per data_produzione | lotti_produzione.py:1667-1835, utils.py:514-628 |

Verifiche fatte nel test: fattura_ref combacia, storico_utilizzi porta il
numero lotto reale, movimento `creazione` + `banco` con `documento_collegato`
puntato alla vendita, quantità scalata correttamente (10→6), FIFO dal lotto
più vecchio (già coperto da test_e2e_flussi.py).

### Punti deboli trovati (riferimenti orfani POSSIBILI)

**2.1 — Placeholder "TEMP" residuo se il backend cade a metà produzione.**
`registra_produzione_e_crea_lotto` scala i lotti col placeholder "TEMP"
(lotti_produzione.py:1317) e lo sostituisce col numero vero solo DOPO la
generazione del codice (1329-1339). Se il processo muore tra i due passi,
`storico_utilizzi` resta con `lotto_produzione="TEMP"` → il recall per lotto
fornitore non risale alla produzione. Scenario concreto: deploy Render nel
secondo esatto della produzione. Gravità: BASSA (finestra di millisecondi,
nessun caso noto). Stato: **da correggere** (idea: generare il numero PRIMA
dello scarico — richiede spostare `get_prossimo_progressivo` sopra lo
scarico; non fatto qui perché tocca l'ordine delle scritture di un flusso
critico già collaudato dal vivo).

**2.2 — `job_pulisci_lotti_scaduti` elimina FISICAMENTE lotti scaduti >30gg
non in ricetta** (scheduler.py:152-208) con `db.lotti.delete_one`. I
`movimenti_lotto` e le `vendite_banco` che citano quel `lotto_id` restano
orfani (le stampe registri mensili perdono il lotto: il registro ASL dice
"conservare 5 anni", lotti_produzione.py:1766). Scenario concreto: ispezione
ASL a gennaio chiede il registro di 2 mesi prima → i lotti scaduti e puliti
non compaiono più. Gravità: MEDIA-ALTA. Stato: **CORRETTO 25/07/2026** — il job ora fa
`update_one` con `archiviato=True` + data e motivo, mai `delete_one`; i lotti
già archiviati sono esclusi dal giro successivo. Il registro resta completo.
Test: test_e2e_flussi.py::test_pulizia_notturna_archivia_e_non_cancella.
NOTA ONESTA: i lotti cancellati PRIMA di questa data non sono recuperabili.

**2.3 — Match ingrediente→lotto fornitore per regex/canonico**
(`_candidati_lotti_fifo`, lotti_produzione.py:889-997): non è una FK ma un
match testuale (canonico → prefissi → aliases). Non può creare orfani, ma può
agganciare il prodotto sbagliato con nomi molto simili. Mitigato dal
nome_canonico e dal pattern ancorato nei riordini (1211-1228). Gravità:
BASSA (già noto, gestito). Stato: verificato ok.

**2.4 — DELETE fattura**: già sicura dalla tranche 4 (fatture.py:165-206):
senza collegamenti → ok; lotti mai movimentati → serve conferma (elimina
anche i lotti, MAI orfani); movimentati/produzioni → 409 + solo annullamento
logico. Coperta da test_e2e_flussi.py::test_delete_fattura_sicura_e_annullamento.
Stato: verificato ok.

---

## 3. RECORD INCOMPLETI / GESTIONE ERRORI IMPORT

- Riga XML senza descrizione → saltata (fatture.py:714-716). Quantità/prezzo
  sporchi → default 1/0 con warning nei log per il food cost
  (fatture.py:727-740, 1407-1419). Stato: verificato ok (scelta documentata).
- File illeggibile → riga in `errori[]`, l'import degli altri file continua
  (fatture.py:954-955). Verificato con test.
- ZIP corrotto → errore dedicato (fatture.py:536-537).
- Il post-import (pipeline, ricette, magazzino bar, riconciliazione ordini) è
  SEMPRE best-effort in try/except: un errore lì non perde mai la fattura
  (fatture.py:776-784, 941-952, 957-998). Verificato su codice.
- NOTA (fatture.py:979-984): l'aggiornamento ricette post-import rilegge "le
  ultime N fatture per created_at" — se un import concorrente inserisce altre
  fatture nello stesso istante può aggiornare ricette da una fattura diversa
  da quelle appena importate. Innocuo (l'operazione è idempotente sui prezzi),
  gravità BASSA, stato: verificato ok (documentato).

---

## 4. TEST ESEGUITI (tutti su mongomock, DB Gestionale_Test)

`backend/tests/test_audit_tranche6.py` — 14 test:
1. `test_import_contatori_righe_e_dedup_per_riga`
2. `test_import_fattura_senza_fornitore_scartata_con_errore`
3. `test_import_file_non_xml_segnalato`
4. `test_catena_completa_chiavi_reali`
5. `test_registra_produzione_scrive_produzioni_e_lotto_collegati`
6-9. scheduler temperature + anomalie (vedi AUDIT_SCHEDULER_TEMPERATURE.md)
10-14. registri/stampe (vedi AUDIT_REGISTRI_STAMPE.md)

Suite completa non-live: **214 passed** (200 preesistenti + 14 nuovi), 0
regressioni. `pyflakes` pulito sui file toccati, `compileall` ok,
`import server` ok.

**Limite tecnico dichiarato**: mongomock NON implementa `array_filters`
(usato in lotti_produzione.py:1333-1339 per sostituire "TEMP") → l'endpoint
`registra-produzione-lotto` è testato con scarico FIFO vuoto, mentre lo
scarico reale è testato chiamando le stesse funzioni interne con il numero
lotto definitivo. Su MongoDB vero `arrayFilters` è supportato (nessun rischio
di produzione, solo un limite del mock).

---

## 5. PROPOSTA: pagina "Verifica integrità gestionale" (NON implementata)

Come richiesto, solo progetto. Pagina ADMIN (stessa famiglia di "Controllo
dati", quindi in `ADMIN_TABS`), backend `GET /api/controllo-dati/integrita`
(nuovo endpoint nel router esistente `routers/controllo_dati.py`).

**Controlli proposti** (tutti read-only, ognuno con conteggio + primi 20 id):
1. `lotti_fornitori` senza fattura corrispondente (`fattura_ref` non trovato
   in `fatture.numero_fattura`) e viceversa fatture senza lotti.
2. `storico_utilizzi[].lotto_produzione` che non esiste in
   `lotti.numero_lotto` (inclusi i residui "TEMP" del punto 2.1).
3. `movimenti_lotto.lotto_id` / `vendite_banco.lotto_id` orfani (lotti
   cancellati dal job pulizia — punto 2.2).
4. `produzioni.numero_lotto` senza lotto; `produzioni` senza
   `lotti_scalati_dettaglio` (storno impossibile).
5. Giacenze negative o incoerenti: `quantita_disponibile < 0`,
   `esaurito=false` con `quantita_disponibile=0`, `quantita_disponibile >
   quantita_acquistata`.
6. `ricette.ingredienti_dettaglio` senza `prodotto_dizionario_id` risolvibile
   (già parzialmente coperto da `/api/report-haccp/ingredienti-non-mappati`,
   report_haccp.py:436-479 — riusare quello).
7. Temperature: giorni mancanti nell'anno per scheda (conteggio "buchi" vs
   365/366), record senza `soglie` (vecchio formato).
8. Fatture con `verifica_richiesta=true` (dedup debole) ancora da controllare.
9. Anomalie aperte da >30 giorni; richiami `stato=aperto` senza chiusura.
10. Doppioni `dizionario_prodotti` con stesso `nome_canonico`.

**Costo/complessità**: ~1 giornata; nessuna nuova collection (risultato
calcolato al volo + eventuale snapshot in `integrita_report` per lo storico).
**Prestazioni**: query su collection da migliaia di doc → eseguire ON DEMAND
(bottone "Esegui verifica"), MAI a ogni caricamento pagina; opzionale job
settimanale notturno che salva lo snapshot. Con gli indici esistenti
(`routers/indici.py`) i join per chiave sono lineari; stimati 5-15 s totali
sul DB attuale. **Dove**: card nella Home admin sotto "Controllo dati";
badge rosso se l'ultimo snapshot ha problemi > 0.

---

## 6. NON VERIFICABILE IN SANDBOX (dichiarato)

- Import PEC e sync Drive contro i servizi reali (serve rete/credenziali di
  produzione: vietato dai vincoli). Verificati su codice + pipeline condivisa
  testata.
- Comportamento dell'indice unico `uniq_numero_piva` creato dall'altra app
  (Gestionale Cloud) sul DB condiviso: simulato nei test con
  `create_index(unique=True)` (test_e2e_flussi.py:250), non osservabile dal
  vivo da qui.
- `arrayFilters` (vedi sopra): limite del mock, non del codice.

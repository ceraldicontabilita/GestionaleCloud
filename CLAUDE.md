# Istruzioni per Claude — GestionaleCloud (Ceraldi ERP)

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-09-15
storage_architecture: supabase
-->

Aggiornato il 20/08/2026 sul codice di `main` del repository canonico
`ceraldicontabilita/GestionaleCloud`.

Prima di ogni intervento leggere `PROMPT_MASTER.md`: è la specifica normativa
unica. Questo file è soltanto il punto di ingresso operativo per Claude.
Leggere e applicare anche `docs/REGOLA_FISSA_ATTESE.md` per qualsiasi flusso
che crea obblighi, attese, prove o riconciliazioni.

Questo file contiene le regole operative per chi modifica il progetto. Il
codice corrente, i test e la configurazione effettiva di produzione hanno
precedenza sui report storici.

## Memoria canonica unica del gruppo Ceraldi

**[17/09/2026, decisione del titolare] Questo file è l'unica memoria di
progetto del gruppo.** Prima erano sparsi `AppDipendenti/CLAUDE.md`,
`Lotti/CLAUDE.md` + `Lotti/memory/REGOLE_ENZO.md` + `Lotti/memory/claude.md`,
`Menu/` e `Gestionale/AGENTS.md`, con regole che in più punti si
contraddicevano (tre "repository canonici" diversi, due politiche di branch
opposte, due scadenze di sessione per lo stesso PIN). Ora c'è un solo file: i
`CLAUDE.md` degli altri repository sono ridotti a un rimando a questo.

### Le quattro app sono un solo servizio

Un unico servizio Render (`gestionalecloud.onrender.com`, deploy automatico da
`main`) e un unico progetto Supabase servono tutto:

| Cosa | Dove vive ora | Codice |
| --- | --- | --- |
| ERP / contabilità | `/` | `app/` + `frontend/` |
| HR, portale dipendenti | `/hr`, `/hr/portale` | `app/hr/` + `frontend_hr/` |
| Menu pubblico e admin | `/menu` | `app/menu/` + `frontend_menu/` |
| Lotti (HACCP) | `/lotti` | `app/lotti/` + `frontend_lotti/` |

### Siti e repository dismessi — non riaprirli

Verificati spenti il 17/09/2026: `appdipendenti.onrender.com` (404),
`lotti-frontend.onrender.com` (404), `lotti-backend-2wwb.onrender.com` (404),
`www.ceraldiapp.it` (non risponde). Non vanno riaccesi né citati come
indirizzi validi: ogni riferimento residuo nel codice è solo una voce CORS o
un commento. Restano da chiudere a mano, quando il titolare vuole: il DNS di
`ceraldiapp.it` presso il registrar e gli eventuali servizi Render sospesi.

I repository `ceraldicontabilita/AppDipendenti`, `Lotti` e `Menu` restano
come **archivio del sorgente originale**: da lì si è copiato il codice dentro
`app/hr`, `app/lotti`, `app/menu`, e non vengono più deployati. Il repository
`ceraldicontabilita/Gestionale` (con il suo `AGENTS.md` che vietava di
riprendere il codice di GestionaleCloud) non è più raggiungibile: era un
tentativo di riscrittura parallela, abbandonato. **L'unico repository vivo è
`ceraldicontabilita/GestionaleCloud`.**

## Direttive permanenti del titolare

Valgono su tutte e quattro le app, sempre, anche quando non sono ripetute nel
resto del file.

### Metodo
- Rispondere e ragionare **in italiano**, risultati prima delle spiegazioni.
- **Tutto va portato su `main`**: si sviluppa su un branch, ma il lavoro non è
  consegnato finché non è unito su `main` e deployato. Render pubblica solo da
  `main`.
- Le funzionalità **si collaudano davvero** (dati di prova reali sul backend
  live, poi ripuliti), non si dichiarano a posto leggendo il codice. Se il
  titolare mostra uno screenshot con il bug ancora presente dopo un fix, il fix
  non ha coperto quel caso: si indaga da zero sui dati reali.
- Se un problema non si risolve subito, **cercare come lo risolvono altri
  progetti reali** (GitHub, web) e integrare la soluzione, invece di
  descrivere il problema e fermarsi.
- Chiudere ogni sessione con il link di produzione: **https://gestionalecloud.onrender.com**
- Se trovi errori, **correggili**: non limitarti a segnalarli.

### Dati e prestazioni
- **Niente doppioni, codice morto o sistemi paralleli: un solo sistema per
  funzione.** Quando ne compare un secondo, si elimina, non si affianca.
- **Non inventare numeri.** Importi tabellari (CCNL, prezzi, aliquote) vanno
  presi dalla fonte o dichiarati da verificare.
- I dati già letti **si tengono in memoria**: ogni rilettura inutile di
  Supabase o Drive è un costo. Liste, conteggi e lookup usano sempre una
  proiezione senza payload; il payload si legge per id.

### Credenziali
- Token, PIN, password e chiavi **solo nelle variabili d'ambiente di Render**
  (`render.yaml` le dichiara con `sync: false`). Mai nel codice, mai nei file
  di memoria, mai in chat, nemmeno mascherati.
- Per le azioni live che richiedono il PIN, usarlo inline in un singolo
  comando e non scriverlo su disco.
- Mai `git add -A`: si aggiungono solo i file pertinenti e verificati.

### Design (vale per HR, Menu e Lotti; l'ERP ha il suo layout)
- Salvia `#5b7a6b` (scuro `#3f5a4e`) su crema `#faf7f0`; card `#fffefb`,
  bordi sabbia `#e6e0d4`, inchiostro `#2a3329`.
- Semantici caldi: pericolo `#d35f4e`, avviso `#c4894a`, successo `#3d8168`,
  informazione `#8a6f47`.
- **Vietati blu, indaco, viola e ciano**, sia come classi Tailwind sia come
  hex negli stili inline: si rimappano su salvia o sabbia.
- Icone Lucide, mai emoji nelle interfacce nuove (su Android rendono con
  colori di sistema non controllabili).
- Ogni pagina centrata, **mai scroll orizzontale su smartphone**: le tabelle
  larghe diventano card impilate. Tocco minimo 44px.
- Le app portate pari pari mantengono il loro aspetto: nessuna contaminazione
  con il layout dell'ERP.

### Le mani sporche (04/07/2026)
Il pasticcere e il banconista hanno **sempre le mani sporche**: nei flussi
operativi si sceglie da tendine, chip e bottoni grandi, non si scrive a
tastiera. Ogni campo di testo libero (motivi, azioni correttive, note) va
sostituito con opzioni predefinite più «Altro (scrivi tu)» come eccezione.

## Lingua e risultato atteso

- Rispondi e documenta in italiano.
- Porta a termine una funzione alla volta: analisi, modifica, test, verifica
  e pubblicazione richiesta dall'utente.
- Non dichiarare completato un flusso basandoti soltanto su HTTP 200, build o
  presenza della pagina. Verifica dati, relazioni, deduplica e risultato live.
- Esponi all'utente il risultato e gli eventuali blocchi, non una sequenza di
  pulsanti tecnici da premere.

## Autorità del repository

- Repository: `https://github.com/ceraldicontabilita/GestionaleCloud`.
- Checkout canonico Windows: `C:\Users\ceral\Documents\GESTIONALE CLOUD 2`.
- Branch operativo: `main`.
- Non usare repository privati non canonici, ZIP o vecchi checkout come autorità.
- Prima di intervenire confronta sempre `HEAD` con `origin/main`.
- Il worktree può contenere modifiche dell'utente: non cancellarle, non
  ripristinarle e non includerle nei commit.
- Mai `git add -A`: aggiungere solo i file pertinenti e verificati.

## Fonti di verità

1. Originali Drive e identificatori delle fonti esterne.
2. Codice, test e configurazione live correnti.
3. `PROMPT_MASTER.md` per tutte le regole normative e i divieti.
4. `page_catalog.json` e mappe generate per la superficie tecnica.

Una prova successiva non crea mai l'obbligo che dovrebbe dimostrare. Il fatto
autorevole crea subito l'attesa; la prova la soddisfa o la lascia
`DA_VERIFICARE`.

I JSON in `memoria/pagine/` e `memoria/popup/` sono mappe tecniche generate:
si aggiornano con `scripts/refresh_json_docs.py`, non a mano.

## Archivio dati: stato reale e destinazione

### Decisione 03/09/2026 (titolare): Supabase è l'archivio unico

- Il titolare ha deciso di fondere le app del gruppo (AppDipendenti, Menu,
  Lotti) dentro GestionaleCloud e di usare **Supabase** (progetto
  `GestionaleCloud`, tabella `gestionale.documents` + `gestionale.blobs`)
  come unico archivio: `render.yaml` imposta `DATA_BACKEND=supabase`.
- Il runtime Sheets resta nel codice solo come fallback di sviluppo; la
  sezione "Destinazione Drive-only" qui sotto descrive l'assetto precedente
  ed è superata per la persistenza dei dati (Drive resta la fonte degli
  originali documentali, non il database).
- I PDF del modulo HR (cedolini, bonifici, documenti: ~500 MB in base64 nel
  vecchio database, di cui ~800 copie duplicate) NON vengono idratati in
  memoria: vivono in `gestionale.blobs` con chiave = SHA-256 del contenuto e
  conteggio dei riferimenti (un PDF identico citato da più documenti occupa
  spazio una volta sola; sparisce solo all'ultimo riferimento). L'adattatore
  `app/hr/db_adapter.py` li carica solo su richiesta.
- **[15/09/2026]** `app/services/supabase_runtime_database.py` non idrata più
  le collezioni nella RAM del processo: il bootstrap legge soltanto il
  catalogo e ogni operazione rilegge da Supabase la collezione richiesta.
  Le scritture sono immediate anche dentro `batch_writes`; un errore RPC
  ripristina lo snapshot locale di lavoro e non lascia dati fantasma. `/api/health`
  verifica dal vivo catalogo e RPC di scrittura. Gli scheduler acquisiscono
  una lease distribuita in `gestionale.runtime_scheduler_leases`; il lock
  locale resta soltanto per il fallback Sheets di sviluppo.

### 14/09/2026 — cancellazione di massa e guardia permanente

**Incidente.** Fra le 00:44 e le 00:54 UTC, col ruolo `postgres` (SQL diretto,
non l'applicazione), è stata eseguita quattro volte
`delete from gestionale.documents where collection not like 'menu%'`:
**53.172 righe cancellate**, le collezioni popolate scese da **83 a 5**. Il
re-import successivo ne ha ricostruite 21. Restano a zero le scritture che
nessuna fonte esterna sa ricostruire: `assegni`, `cespiti`, `f24_models`,
`f24_unificato`, `quietanze_f24`, `scadenzario`, `scadenziario_fornitori`,
`riconciliazioni`, `riconciliazioni_match`, `partite_aperte`,
`movimenti_contabili` (libro giornale), `piano_conti`,
`dettaglio_righe_fatture`, `prima_nota`, `prima_nota_righe`, `note_credito`,
`documents_inbox`, `magazzino`, `warehouse_inventory`, `veicoli_noleggio`,
`verbali_noleggio`, `regole_categorie`, `learned_patterns`, `settings`,
`indice_documenti`. **Vanno recuperate da un restore del backup** (PITR
attivo: WAL archiviato ogni 120 s, `failed_count` 0) fatto **verso un progetto
separato** — un restore in place riporterebbe indietro anche la fusione degli
schemi, fatta dopo le 00:44. Poi reinserimento dei soli id mancanti con
`gc_upsert_documents` (idempotente per `collection`+`id`).

**Guardia** (`supabase/migrations/20260914160000_guardia_cancellazioni_massive.sql`).
L'applicazione non cancella mai con un filtro: passa sempre da
`gc_delete_documents` / `gc_delete_blobs` / `lotti_delete_*` con gli id
espliciti. La guardia distingue quindi per **origine**, non per numero di
righe: nessun limite all'app, blocco totale di `DELETE` e `TRUNCATE` eseguiti
a mano su `gestionale.documents`, `gestionale.blobs`, `lotti.lotti_documents`
e su tutto lo schema `legacy_staging` (118 trigger, 59 tabelle). Per una
manutenzione deliberata, nella **stessa transazione**:
`select gestionale.consenti_cancellazione();`. Collaudata sui dati reali il
14/09: inserimento libero, `DELETE` a mano bloccata, percorso applicativo
invariato, `TRUNCATE` bloccato.

**Regola operativa.** Nessun agente e nessuna sessione automatica deve avere
la password Postgres: solo l'API con il segreto runtime, che cancella per id.
La password Postgres va ruotata (è stata usata da una sessione automatica).

### 14/09/2026 — protocollo-indice vivo dei documenti su Drive

- **Problema**: l'indice documentale esisteva solo come file statici (quattro
  copie su Drive: `INDICE.xlsx`, `_drive_map.json`, `INDICE_GESTIONALE.html`,
  manifest) più l'Excel letto da `app/services/drive_document_index.py`, la
  cui radice `DRIVE_DOCUMENT_INDEX_ROOT_FOLDER_ID` **non esiste più su Drive**.
  Fotografie vecchie di settimane, che non sanno di file aggiunti o tolti.
- **Soluzione**: `app/services/drive_protocollo.py` + tabella relazionale
  `gestionale.protocollo_drive` (asyncpg, NON `gestionale.documents`: 30.000
  righe di inventario non vanno idratate in memoria a ogni avvio). Il giro
  periodico (`scheduler.py`, ogni 6 ore, primo giro 8 minuti dopo l'avvio;
  bottone "Aggiorna indice adesso" nel tab Indice Drive del hub Documenti)
  **riconcilia** Drive con la tabella: file nuovo → riga nuova; cambiato →
  aggiornata; sparito → `stato='rimosso'` con la data, **mai cancellato** (è
  un protocollo: deve ricordare che il documento è esistito, con il suo hash).
  L'MD5 arriva dall'API Drive (`md5Checksum`): i duplicati certi si trovano
  senza scaricare nulla; la copia canonica è deterministica (mai in
  `90_ARCHIVIO_STORICO`, `00_DA_CLASSIFICARE` o quarantena, poi la più vecchia).
  Le impronte dei documenti già in archivio (cedolini e bonifici HR, allegati
  fattura via `gestionale.impronte_fatture()`) stanno in `protocollo_impronte`:
  ogni file Drive viene collegato al documento del gestionale **per contenuto**,
  non per nome. Duplicati → **quarantena** (`GOOGLE_DRIVE_QUARANTENA_FOLDER_ID`)
  solo su richiesta esplicita, mai la canonica, mai una cancellazione.
- Env Render: `GOOGLE_DRIVE_GESTIONALE_ROOT_FOLDER_ID` (radice da percorrere),
  `GOOGLE_DRIVE_QUARANTENA_FOLDER_ID`, `PROTOCOLLO_DRIVE_ENABLED`. Il ruolo
  Postgres dell'app è `hr_app`: ha i grant minimi sulle tre tabelle del
  protocollo, **non** legge `gestionale.documents`.
- Endpoint admin: `GET /api/documenti/drive/protocollo/{status,search,
  documento/{id},duplicati}`, `POST .../sync`, `POST .../quarantena`.
  Il tab "Documenti" dell'Indice Drive legge il protocollo; F24 e dichiarazioni
  restano sull'Excel finché non hanno una sorgente propria.
- **Trovato durante il censimento Drive (14/09)**: `03_BANCHE_E_PAGAMENTI/
  BONIFICI` è **vuoto** in tutte e tre le cartelle di stato (i bonifici
  stanno per persona in `05_PERSONALE_E_CEDOLINI/BONIFICI DIPENDENTI`);
  `03/ESTRATTI CONTO/DA ELABORARE` contiene **334 file mai lavorati** (72 MB:
  estratti conto BNL/BPM/Nexi/Worldline/PayPal/Satispay, 54 ricevute di
  bonifico finite lì per sbaglio, CSV, una fattura fornitore) e un solo file
  in ELABORATE — l'ingest estratti conto non ha mai girato su quella cartella.
  Le vecchie cartelle HR (`1XVdb…` cedolini, `1yl55…` bonifici) non esistono
  più: i default in `app/hr/services/google_drive_sa.py` puntano nel vuoto.

**Schemi dopo la fusione** (un solo progetto Supabase `GestionaleCloud`):
`gestionale` (ERP: `documents`, `blobs`), `hr` (29 tabelle `app_*`), `lotti`
(`lotti_documents`), `menu` (9 tabelle + bucket `menu-images`),
`legacy_staging` (56 tabelle, archivio CeraldiFatture con
`_migration_manifest`: hash SHA-256 e `source_count = target_count` per
tabella). Solo `menu` e `public` sono raggiungibili da `anon`/`authenticated`;
`gestionale`, `hr`, `lotti`, `legacy_staging` non lo sono.

### 14/09/2026 — Drive 05: UN fascicolo per dipendente

Prima cedolini, bonifici e certificazioni uniche della stessa persona stavano
in tre alberi paralleli (`CEDOLINI PAGA/<persona>`, `BONIFICI DIPENDENTI/
<persona>`, `CERTIFICAZIONI UNICHE/<persona>`) con elenchi di persone diversi
(50/37/22) e cartelle `VARI` che contenevano documenti veri (tutta la storia
cedolini di D'Alma Vincenzo, 100+ bonifici a fornitori, CU di 5 persone).
Struttura definitiva (autorizzata dal titolare, "sei autorizzato a creare,
eliminare le cartelle"):

```
05_PERSONALE_E_CEDOLINI/
  DIPENDENTI/                      ← id 1EfO5-9Cs-h7cIUOKoWdL_O_E1speoccY (era "CEDOLINI PAGA":
    <COGNOME NOME>/                   stesso id, la radice dell'ingest cedolini non cambia)
      DA ELABORARE | ELABORATE | ERRORI      ← cedolini (canale cedolini, profondità 2)
      BONIFICI/DA ELABORARE | ELABORATE | ERRORI  ← bonifici della persona (canale bonifico, prof. 3)
      CERTIFICAZIONI UNICHE/                  ← CU (nessun ingest)
  CERTIFICAZIONI UNICHE COLLABORATORI/  ← CU di non dipendenti (Avv. Carini ...)
  CONTRATTI DIPENDENTI/ UNILAV E PRATICHE LAVORO/ DOCUMENTI DIPENDENTI/ INPS/ INAIL/  (invariate)
  INPS/CONTENZIOSO INPS - CEDOLINI D'ALMA 2023/   ← era CEDOLINI PAGA/PER CONTENZIOSO INPS
03_BANCHE_E_PAGAMENTI/BONIFICI/DA ELABORARE | ELABORATE | ERRORI ← i bonifici NON stipendio
                                    (fornitori, consulenti, INPS...) che stavano in BONIFICI DIPENDENTI/VARI
07_CONTRATTI_E_FORNITORI/CONTRIBUTI E BANDI/FONDO NUOVE COMPETENZE/, UTENZE E ADDEBITI/BONUS UTENZE/
```

- 51 fascicoli (48 esistenti + IAZZETTA FRANCESCO, PANE GIUSEPPINA, D'ALMA
  VINCENZO creati); rinominati IACOVELLI EMANUELE→MANUELE e POSLIGUA
  OROSCO→OROZCO (fonte: cedolini). 19 fascicoli sono di ex dipendenti pre-2021
  assenti dall'anagrafica HR (hanno cedolini su Drive: vanno importati, non
  cancellati).
- Cestinate (reversibili) SOLO cartelle vuote: le tre `VARI`, le tre lifecycle
  vuote di 03/BONIFICI, `BONIFICI DIPENDENTI` (dopo lo switch env, vedi sotto).
- Env Render: `GOOGLE_DRIVE_CEDOLINI_FOLDER_ID` = `GOOGLE_DRIVE_BONIFICI_FOLDER_ID`
  = DIPENDENTI; `GOOGLE_DRIVE_BONIFICI_FOLDER_IDS` = "DIPENDENTI,03/BONIFICI"
  (1raKJxMV1YSjRdVwhuqh8kGddmWvNWHHl). Il canale `bonifico` accetta una inbox
  diretta sotto una radice dedicata o, più in profondità, solo dentro
  `BONIFICI`; con radice condivisa non crea mai una inbox legacy.
  **Attenzione**: NON puntare `GOOGLE_DRIVE_BONIFICI_FOLDER_ID` a DIPENDENTI
  con un backend precedente a questa modifica (profondità 2 senza vincolo =
  leggerebbe i cedolini come bonifici).
- Anagrafica HR da sistemare (trovato durante il lavoro): "Ceraldi Antonella"
  (senza CF, nessun cedolino) è probabilmente un refuso di "Ceraldi Antonietta";
  "Dalma Vincenzo" (nome/cognome invertiti) e "D'Alma Vincenzo" condividono lo
  stesso `dipendente_id` nei cedolini, con 48 righe = doppioni per anno/mese;
  "Stasio Salvatore" su Drive è "DI STASIO". Sankapala 14ª 2025 caricata due
  volte (stesso PDF).

### 14/09/2026 — audit E2E e integrità dati in produzione: cosa è stato corretto

Rapporto completo (399 righe, 70 finding con query e numeri) prodotto in sessione;
qui solo ciò che è stato **cambiato** e dove sta il backup (tutto reversibile):

| Cosa | Prima | Dopo | Backup |
|---|---|---|---|
| Scheduler produzione | `ENABLE_SCHEDULER=false` dal 14/09 00:52 (spento durante l'unificazione Codex): **nessun job periodico** (44 job ERP + HR) per 16 ore | riattivato con lo switch env del fascicolo Drive | — |
| Storage `menu-images` | nessuna policy su `storage.objects`: ogni upload dal ponte Lotti→Menu rifiutato | policy "menu app full access" (solo bucket menu-images, ruolo anon = chiave server) | migrazione `20260914190000` |
| PayPal `sync/incremental` | 500 (404 PayPal su finestre di secondi) | finestra minima 5 min, errore PayPal → 502 leggibile | — |
| HR `app_bonifici` | 887 righe, **239 PDF byte-identici duplicati** (€ 283.995) | 648 righe, 0 gruppi md5 duplicati | `hr.app_bonifici_duplicati_20260914` (id, doc, canonico_id) |
| HR `app_paghe_mensili` | 36 righe sul dipendente fuso "Vincenzo Dalma" (9a0e68a7) doppie di quelle di D'Alma (df37ac5a) | rimosse | `hr.app_paghe_mensili_rimosse_20260914` |
| HR `app_dipendenti` | D'Alma attivo senza CF; Antonietta Ceraldi "cessato" con cedolini fino a 07/2026; "Ceraldi Antonella" attiva senza CF/cedolini | D'Alma cessato 13/06/2024 + CF dai cedolini; Antonietta attiva; Antonella disattivata con nota (riattivare se persona diversa) | `hr.app_dipendenti_modifiche_20260914` |
| `fornitori` | BIG FOOD Srl id 229 (0 fatture) doppione di BIG FOOD SRL id 381 | rimosso | `gestionale.documents_rimossi_20260914` |
| `invoices` | 1776634697838: stesso XML della 1785273160323 ma attribuita a PIETRO CASTALDO (l'XML dice GIUSEPPE GARGIULO) | rimossa (786 fatture) | `gestionale.documents_rimossi_20260914` |
| `corrispettivi` | 181 chiusure legacy con **l'imponibile in `totale_iva`/`iva10`** (totale/1,1): la liquidazione IVA (`iva_liquidation_query.py`) sommava € 471.708 di "IVA" su gen–ago | `totale_imponibile`/`imponibile10` = totale/1,1, `totale_iva`/`iva10`/`iva_da_versare10` = totale − imponibile (**aliquota 10% presunta**, resta DA_VERIFICARE finché non arriva l'XML RT); IVA totale € 47.170,88; il frontend (#442) legge `totale_imponibile` e non applica più l'euristica | `gestionale.corrispettivi_iva_prima_20260914` |

Primo giro reale dopo lo switch (17:25 UTC): scheduler avviato, ingest Drive
fatture (975 in coda, 25 archiviate per giro), estratti conto (291 documenti
pre-2026 lasciati fermi per scelta, 39 in coda), cedolini (49 inbox = i
fascicoli, 0 nuovi), canale bonifici sul fascicolo (`VESPA VINCENZO/BONIFICI/
DA ELABORARE/...` importati), sync paghe HR (1.175 cedolini, 648 bonifici).
Il protocollo Drive è fallito al primo giro: `postgres_diretto.ENV_DSN`
leggeva prima `SUPABASE_DB_URL`, che su Render punta ancora a un progetto
Supabase **morto** (`postgres.jqguwrahxeilcikplaxi`); ora l'ordine è quello
del deposito HR (`HR_SUPABASE_DB_URL` prima). **Da fare sul pannello Render:
aggiornare o togliere `SUPABASE_DB_URL`** (l'ERP usa `SUPABASE_URL` + segreto
runtime, non la DSN).

Verificato e lasciato com'è: i 68 movimenti banca `_dupN` hanno `legacy_row_hash`
diversi dalla riga base → righe legacy distinte (es. due commissioni uguali lo
stesso giorno), non doppioni.

**Aperto (serve codice o dati che non ci sono)**: 158 fatture `riconciliata`
con movimento `riconciliato=false` e 180 righe hub senza `fattura_id` (stato
riconciliazione incoerente dopo la ricostruzione del 14/09: da rigenerare col
motore, non a mano); corrispettivi/POS senza **febbraio** e 26/01–08/03,
15–23/08 (i file, se esistono, entrano dall'ingest Drive ora che lo scheduler è
attivo); archivio bonifici HR fermo al 09/04/2026 (paghe apr–giu in attesa,
€ 45.598): serve il ponte gestionale→HR per bonifici ed estratto conto; 38
bonifici HR con `cedolino_id` legacy orfano; 119 in "bonifici da associare"
(14 con PDF già in esiti); 8 persone dei cedolini mai in anagrafica; 10
tabelle attese dall'app HR assenti (turni_config, onomastici, richieste, ...).

### 14/09/2026 — ponte gestionale→HR per i PAGAMENTI (bonifici ed estratto conto)

Un solo punto di ingresso per i pagamenti stipendio: il gestionale legge i PDF
dei bonifici (fascicolo Drive `DIPENDENTI/<persona>/BONIFICI/DA ELABORARE`,
Import documenti, upload dalla pagina salari) e gli estratti conto; l'archivio
che si vede in `/hr/dipendenti/paghe-bonifici` viene alimentato da
`app/services/hr_pagamenti_deposito.py` attraverso il database HR in-process
(stesso adattatore e stesse funzioni dell'app HR: `_indici_dipendenti`,
`_ricalcola_stato_paga`, `_e_movimento_non_stipendio` — niente copie).

- Ingressi: `bonifici_transfers` (dopo `importa_pdf_bonifico`, chiave HR
  `gc:<sha256 PDF[:24]>`, PDF allegato) e `estratto_conto_movimenti` (uscite
  "FAVORE <dipendente>", chiave `ecm:<id movimento>`, `cro` dal "RIF. …").
  Scrive `pagamenti_esiti` + `paghe_mensili` (stato ricalcolato dal motore
  unico HR) oppure la coda HR `bonifici_da_associare`.
- Regole: dipendente da CF → nome completo univoco → cognome univoco; il
  fascicolo Drive della persona vale come identità E come segnale "stipendio"
  (le causali dei PDF reali sono `AGGIUNTIVA`/`ricevuta per ordinante`); dalla
  banca serve la parola stipendio/stip/salario/acconto/saldo in causale
  OPPURE un **lotto paghe** (bonifici ad almeno 3 dipendenti diversi lo
  stesso giorno: negli estratti conto gen–apr 2026 la descrizione è solo
  `FAVORE TAIANO LUIGI - ADD.TOT`, 12 righe lo stesso giorno = acconti/saldi
  del mese), altrimenti coda — e il giro successivo riesamina le righe in
  coda "senza segnale" se il giorno è diventato un lotto (ritira la riga
  dalla coda HR); `BENEFICIARI VARI/DIVERSI` (cumulativo senza nomi, anche
  se la causale libera cita una persona: "Vincenzo ceraldi stipendi" 4.600 €
  era per più dipendenti) → coda, e il giro toglie l'esito se era stato
  attribuito a qualcuno; TFR, fatture, commissioni, fornitori mai (nemmeno in coda);
  competenza da causale/nome file, altrimenti regola del giorno 25
  (`stipendi_bonifici.competenza_bonifico_stipendio`); stesso pagamento visto
  da PDF e da banca (stesso dipendente, importo, data ±3 gg) → un solo esito,
  arricchito (cro/hash/PDF), mai duplicato; stesso hash già in HR (importer
  Drive HR `drive:`) → duplicato.
- Ogni documento sorgente riceve `hr_deposito` (`esito`, `key`,
  `dipendente_id`, `at`): il job scheduler `hr_pagamenti_deposito` (ogni 15
  min, primo giro avvio+6 min) riprende solo i documenti senza marcatore, per
  qualunque punto di inserimento. Backfill/prova a mano: `POST
  /api/prima-nota-salari/deposita-pagamenti-hr?dry_run=true` (admin).
- Rimosso il doppione HR `POST /hr/api/dipendenti-cloud/paghe/importa-bonifici-drive`
  (+ `_parse_bonifico_pdf`, bottone "📥 Importa bonifici da Drive" in Paghe e
  bonifici): leggeva la cartella Drive per conto suo, non ricorsiva, quindi con
  la radice DIPENDENTI trovava 0 file. Un solo sistema: il ponte. Il link
  "📁 Fascicoli Drive" resta (`/paghe/bonifici-drive-config`).
- Fix a latere: `document_data_saver.save_estratto_conto_to_gestionale` usava
  `hash()` di Python nell'id (cambia a ogni riavvio del processo → il controllo
  duplicati non funzionava mai fra riavvii); ora `sha1` stabile.

### 14/09/2026 — dimissioni telematiche → adempimenti; giorni di chiusura attività

- **Dimissioni** (richiesta del titolare: "quando trovi in posta un allegato del
  genere è la conferma delle dimissioni, ho 5 giorni per comunicarlo al
  consulente del lavoro"). Il gestionale riconosce già il "Modulo Recesso
  Rapporto di Lavoro" (`fiscal_domain` → `dimissioni_telematiche`, parser
  `administrative_document_parser.parse_dimissioni`, archiviato da
  `documenti._archive_non_payment_document`). Nuovo
  `app/services/dimissioni_adempimenti.py`, agganciato lì: dipendente HR per
  CF → `dimissioni{...}` + `data_cessazione_prevista` sull'anagrafica, alert HR
  `DIP_DIMISSIONI_RICEVUTE` (critico, Pannello di controllo) con la checklist
  degli adempimenti, scadenza `notifiche_scadenze` tipo `UNILAV_CESSAZIONE` alla
  data decorrenza + 5 gg. Regole: UNILAV di cessazione entro **5 giorni** dalla
  cessazione (D.Lgs. 181/2000 art. 4-bis) via consulente; revoca del lavoratore
  entro **7 giorni** dalla trasmissione (D.Lgs. 151/2015 art. 26); idempotente per
  `codice_modulo`; modulo vecchio (limite passato da >60 gg) di un cessato →
  solo archivio, niente alert. Rimosso il doppione HR `routers/dimissioni.py`
  (lettore IMAP proprio, mai usato dal frontend): l'unica posta letta è quella
  del gestionale.
- **Giorni di chiusura** (titolare: ristrutturazione dal 26/01 all'8/03/2026,
  febbraio compreso — confermato dal POS: ultima transazione 25/01, prima 09/03;
  15–23/08 ferie — non sono corrispettivi mancanti). Registro unico
  `chiusure_attivita` (`app/services/chiusure_attivita.py`): periodi confermati
  seminati dal job `chiusure_attivita` (ogni 6 h), colonne "Periodo di
  inattività da/a" del CSV AdE (`/api/corrispettivi/import-csv`: il RT le
  dichiara alla riapertura), ferie collettive nelle presenze HR (≥80% degli
  attivi in ferie e nessun corrispettivo quel giorno → chiusura `presenze_hr`),
  API `GET/POST/DELETE /api/corrispettivi/chiusure`. `iva_liquidation_query.
  corrispettivi_periodo` toglie questi giorni da `giorni_senza_corrispettivo`
  (nuovo campo `giorni_chiusura`).
- Anagrafica HR: "Ceraldi Antonella" confermata = Antonietta Ceraldi (unita:
  `merged_into`, 11 presenze spostate). Render: `SUPABASE_DB_URL` svuotata
  (puntava a un progetto morto; il codice legge prima `HR_SUPABASE_DB_URL`).
- **HR Paghe e bonifici, modifiche a mano** (titolare 14/09/2026): `PUT
  /hr/api/dipendenti-cloud/paghe/pagamento-esito/{key}` sposta un pagamento
  a un altro periodo e/o ne corregge l'importo (stessa chiave/PDF/CRO, storia
  in `modifiche_manuali`, entrambi i mesi ricalcolati da
  `_ricalcola_bonifico_periodo` = somma esiti + motore unico); `PUT
  /paghe/importo-busta` corregge l'importo della busta (`origine: manuale`,
  `importo_busta_originale`, nota) e la sincronizzazione dai cedolini non lo
  sovrascrive (`saltati_manuali`). Nella pagina: ✎ sulla cella busta, «Sposta /
  modifica» in ogni riga di bonifico dei dettagli.
- Anagrafica HR completata il 14/09 dai cedolini e da «Lista dipendenti
  Ceraldi_Group_SRL.xlsx» (Drive 12_EXCEL): 6 persone esistenti senza CF ora
  con CF/nascita/livello/periodo, 7 create (storiche, cessate), cedolini
  collegati per CF; i 16 attivi hanno IBAN/matricola/telefono/email/nascita/
  indirizzo (mancava tutto; resta senza IBAN solo Iazzetta Francesco, non in
  Excel). Backup `hr.app_dipendenti_prima_20260914b`.
- Cedolini con CF senza anagrafica HR (13 persone, elenco in chat del 14/09, TUTTE sistemate il 14/09 sera):
  Sankapala Arachchilage (2025-06→2026-02, 11 buste), De Simone Mariano,
  Stasio Salvatore, Posligua Orozco William, Iacovelli Manuele, Lubrano
  Cristian, Thalwattage Sajeewani, Giattini Ilenia, Rabukkana Kusal,
  Pellegrino Salvatore, Tramontano Giuseppe, Bettipilippuge Viraj, Mauro
  Mariano — da creare/collegare in anagrafica (decisione del titolare).

### 14/09/2026 — bonifica design (colori)

Skill `bonifica-design` applicata a tutto il repo: 128 colori freddi (blu/
indaco/viola) in 37 file delle 4 app rimappati su salvia/sabbia, anello di
focus Tailwind del Menu a salvia (`tailwind.config.js` → `ringColor.DEFAULT`),
intestazioni PDF reportlab (report, presenze HR, bilancio, contabilità,
export fatture, noleggio, email ordini Lotti) da blu/viola/navy a salvia.
Verifica: 0 occorrenze nei bundle compilati. Scansione da ripetere dopo ogni
modifica frontend: `grep -rEn "5D29C7|1E1B4B|7c3aed|8b5cf6|6366f1|4f46e5|
violet-|indigo-|bg-blue-|bg-sky-|text-blue-|border-blue-|3b82f6|2563eb|1d4ed8"`
su `frontend*/src` e sui bundle. Il test `frontend/src/components/
AvvisoBonarioF24.test.jsx` vieta i colori freddi nel suo componente.

### 14/09/2026 — Personale: l'anagrafica HR comanda, Lotti legge (regole R1-R6 del titolare)

- **R1 — un solo elenco di persone.** `app/lotti/routers/tablet_operatori.py`
  non ha piu' un'anagrafica propria: `tablet_operatori` (Lotti) e' una
  proiezione di `hr.app_dipendenti` letta in-process
  (`sincronizza_operatori_da_hr`: all'avvio, ogni 10 min dallo scheduler
  Lotti, a ogni apertura della pagina Personale, a ogni login). Operatore =
  dipendente **in forza** in HR con `lotti_operatore` != false (spunta
  «Operatore in Lotti» nella scheda HR; Iazzetta, Sankapala e Antonietta
  Ceraldi sono a false per scelta del titolare). Nome = «Cognome Nome» da
  HR; ruolo amministratore = `ruolo_app: admin`; la postazione HACCP e'
  proposta dal ruolo HR (`postazione_da_ruolo`) e resta modificabile; le
  righe Lotti senza persona HR (Viviana, Kikko, Thimira) restano nel DB con
  `attivo=false, hr_stato=non_in_hr` (lo storico firmato non si tocca);
  «Lisina» = Lesina (`ALIAS_COGNOME`). Eliminati: «Nuovi dipendenti dal
  gestionale», «Collega esistente», blocco «PIN operatori», `NOMI_DEFAULT`,
  `ADMIN_PIN_RECOVERY`, gruppo PIN condiviso Vincenzo/Valerio.
- **R2/R3 — un PIN per persona, nella scheda HR** (`app/hr/services/
  auth_dipendenti.py`): vale per il portale e per firmare in Lotti. Nuovi PIN
  = bcrypt (`pin_hash`) + impronta HMAC `pin_lookup` (segreto = chiave JWT
  HR) per trovare la persona in una query; gli SHA-256 storici restano
  validi in lettura. `trova_dipendente_per_pin` (usata dal login del tablet
  Lotti) non restituisce mai un cessato; `imposta_pin` rifiuta un PIN gia'
  usato da un altro dipendente in forza; la cessazione revoca il PIN.
  Migrazione una tantum `migra_pin_in_hr` (avvio + job): i bcrypt di Lotti
  passano nella scheda HR della stessa persona se non ne ha gia' uno; Lotti
  poi cancella ogni campo PIN (`_CAMPI_PIN_LEGACY`). R4: il PIN condiviso
  degli amministratori non viene migrato; il PIN amministratore centrale
  (`PIN_HASH_ADMIN`) apre le pagine riservate ma NON e' un'identita' di firma
  sul tablet. Nel portale HR gli admin continuano a entrare solo col PIN
  centrale (test `test_hr_admin_personale_non_aggira_pin_centrale`).
- **Anagrafica HR** (`app/hr/routers/dipendenti_cloud/__init__.py`,
  `app/hr/services/stato_rapporto.py`): UN solo stato del rapporto
  (`attivo` | `cessato` con `data_fine_rapporto`, `motivo_cessazione` fra
  dimissioni/licenziamento/fine_contratto/risoluzione_consensuale/altro,
  `riferimento_cessazione`); `stato=inattivo` con `attivo=true` non esiste
  piu' (normalizzato a cessato). `POST /dipendenti/{id}/cessa` richiede data e
  motivo (modale dell'app, niente `confirm()`), revoca il PIN e propaga
  `DIPENDENTE_CESSATO`; `POST .../riattiva` conserva `cessazioni_precedenti`.
  `PUT /dipendenti/{id}` aggiorna SOLO i campi inviati (prima riscriveva
  matricola/nascita/indirizzo a None: successo a Moscato) e ignora `stato`.
  `POST/DELETE /dipendenti/{id}/pin`. `GET /dipendenti` espone `pin_impostato`,
  `lotti_operatore`, `data_fine_rapporto`, mai il PIN. `GET /documenti` senza
  `file_data` (era il «Caricamento…» di 5-10 s a ogni apertura); `POST
  /documenti` e' multipart con file facoltativo e tipi Dimissioni/UNILAV/
  Licenziamento — un modulo di dimissioni caricato qui passa da
  `registra_dimissioni` (alert + scadenza UNILAV). `frontend_hr`: la riga si
  aggiorna in linea (`aggiornaDipendente`), niente ricarica totale; link
  diretto `?dip=<id>` dalla pagina Personale di Lotti apre la scheda.
- **Cedolini & Bonifici = unica pagina paghe** (titolare: «Buste Paga» e
  «Cedolini & Bonifici» davano numeri diversi). Eliminata `BustePagaPage`
  (riscriveva a mano `importo_busta`/`bonifico_importo` in `paghe_mensili`,
  fuori dal motore unico) con `GET/POST/DELETE /paghe`; dentro
  `PagheBonificiPage` sono passati: menu «Importa» (Libro Unico, email, Drive,
  Prima Nota, CSV banca, archivio storico), acconti in contanti
  (`PUT /paghe/acconti`, solo il campo `acconti` + ricalcolo), prima nota per
  dipendente (clic sul nome), ricerca voci, riscansione, correzione acconti,
  simulazione F24, griglia annuale. La vecchia rotta `/hr/dipendenti/buste-paga`
  apre la pagina unificata.
- **Pannello HR, buste in attesa**: «Buste da pagare» = anno corrente; le
  buste degli anni precedenti con bonifico non agganciato sono contate a parte
  (`buste_storiche_non_agganciate`, sezione a scomparsa), non sono soldi da
  erogare.
- **PEC dimissioni** (`app/services/email_full_download.py`): la busta PEC
  (`posta-certificata@…`) vale col mittente del messaggio annidato
  (`postacert.eml`); mittente builtin `dimissionitelematiche@pec.lavoro.gov.it`
  e parole chiave «recesso rapporto di lavoro/dimission/unilav»; il PDF
  `<CF>_Dimissione.pdf` va in `_archive_non_payment_document` come
  `dimissioni_telematiche` (alert HR + scadenza UNILAV) invece che in
  `documenti_non_associati`. Trovato: `mittenti_email` in produzione e'
  VUOTA (persa il 14/09), quindi la posta non scarica nulla finche' non
  viene ripopolata (i builtin rientrano da soli all'avvio).
- Dati sistemati in produzione il 14/09 sera (backup
  `hr.app_dipendenti_prima_20260914c`): Moscato Emanuele cessato 01/07/2026
  (dimissioni, modulo 20260630102348083, PEC 30/06) con matricola/nascita/
  indirizzo/assunzione 13/03/2012 ripristinati dall'Excel; Pocci Salvatore
  cessato 31/08/2026 (dimissioni, modulo 20260730155946178, PEC 30/07,
  girate al consulente il 31/07). Per nessuno dei due c'e' in Gmail l'UNILAV
  di cessazione: da verificare col consulente (Ferrantini).

### 15/09/2026 — accessibilità WCAG 2.1 AA (punti 1-4 dell'audit) e cedolini storici via hub unico

- **Modali HR** (`frontend_hr/src/App.jsx`): un solo componente `Modal`
  (`role="dialog"`, `aria-modal`, titolo in `aria-labelledby`, focus portato
  dentro all'apertura, Tab intrappolato, Esc chiude, focus restituito a chi ha
  aperto, clic sullo sfondo chiude). Sostituisce le 4 `dc-modal-overlay` e le
  6 finestre "a mano" (`position: fixed` + `dc-card`: riduzione oraria,
  configura turni, sostituzione d'emergenza, correggi periodo TFR, prima nota
  dipendente, assumi dipendente). Non aggiungere nuove modali fuori da `Modal`.
- **Etichette**: i 29 gruppi `dc-form-group` sono `<label>` che avvolgono il
  campo (`<span className="dc-label">` per il testo); Lotti Personale e
  Stampanti usano `htmlFor`/`id` per riga (`postazione-<id>`, `libretto-<id>`,
  `azienda-<campo>`, `st-<campo>-<id>`). `aria-label` dinamici sui bottoni
  ripetuti (modifica/cessa/riattiva/elimina scheda, approva/rifiuta ferie,
  ‹/› mesi e settimane, ✎ busta e periodo, elimina documento, select
  dipendente/mese/anno in «Bonifici da associare», filtri paghe).
- **Griglie da tastiera**: le celle di Presenze e Ferie contengono un
  `<button className="dc-cell-btn">` con nome accessibile «Cognome Nome,
  gg/mm: stato»; in Presenze Invio/Spazio applica il pennello alla cella
  (il trascinamento col mouse resta sul `<td>`); i badge attenuati dal
  pennello usano `.dc-dimmed` (saturazione ridotta, non opacità 0,12).
- **Focus visibile**: `:focus-visible` salvia in `App.css` HR e regola
  esplicita in `frontend_lotti/src/index.css` per `.g-input/.g-select/
  .g-textarea` e le classi Tailwind `outline-none`. Home HR (`Landing.jsx`):
  le card sono `<Link>` veri, non `<div onClick>`.
- **Cedolini storici mancanti (63 PDF, 18 persone)** trovati confrontando
  l'archivio Drive `1lh7M9…/Cedolini` con `hr.app_cedolini`: copiati con
  l'API Drive nei fascicoli `DIPENDENTI/<PERSONA>/DA ELABORARE` (hub unico
  del gestionale: ingest orario → registro `cedolini` → deposito HR), **non**
  caricati da «Carica documenti» HR (regola del titolare: un solo motore di
  import per ogni sezione). Appuhamy, Aurigemma, Vitiello e Dell'Aquila non
  hanno anagrafica HR: il deposito le crea/collega per codice fiscale solo se
  la persona esiste, quindi vanno create come storiche cessate dopo l'ingest.

### 15/09/2026 — cessazione automatica da cedolino: guardia e riallineamento con HR

- **Trovato** importando l'archivio storico (63 buste 2018-2022) dai fascicoli
  Drive: `salari_unificati_v2.processa_cedolino_v2` (e il fallback V1 in
  `cedolini_manager`) marcava cessato nella copia `dipendenti` del gestionale
  chi aveva una busta con dicitura di cessazione (TFR, «licenz.», «data
  cessazione»), senza guardare se esistono buste successive. Risultato: in
  pochi minuti Carotenuto, Capezzuto, Guarino (in forza, buste fino al
  2026-07), Dias, Liuzza, Lubrano, D'Alma, Solla ecc. risultavano cessati
  nel gestionale con date di anni fa. L'anagrafica HR non e' stata toccata.
- **Guardia** (`app/services/cessazione_da_cedolino.py::busta_successiva`):
  la cessazione letta in una busta vale solo se non esiste una busta
  successiva della stessa persona nel registro `cedolini` del gestionale o
  nel deposito HR (`app_cedolini`, per CF); altrimenti viene ignorata e
  loggata (`cessazione_storica_ignorata` nell'esito).
- **Riallineamento** (`riallinea_cessazioni_automatiche`, job scheduler
  `riallinea_cessazioni_auto` ogni 6 ore, primo giro avvio+2 min): per i
  record con `cessato_automaticamente=True` l'anagrafica HR comanda (R1): HR
  in forza → riattivato, HR cessato → data di HR. I cessati a mano non si
  toccano. Passa dall'app (store in memoria coerente), non da SQL a mano.
- `documents_inbox` del gestionale ha ~3.970 documenti da rielaborare (il
  registro `cedolini` era a 206 righe dopo l'incidente del 14/09): il giro
  orario dell'ingest li sta rilavorando; il deposito HR li deduplica per
  (CF, anno, mese, tipo).

### 15/09/2026 — censimento Supabase e integrazione dell'archivio legacy (richiesta: «fallo tu, non delegare»)

Censimento (numeri reali): `legacy_staging` completo (55 tabelle,
`source_count = target_count` + hash); `hr` 43 dipendenti / 1.317 cedolini
con PDF / 648 bonifici / 502 documenti; `lotti` 23.783 documenti in 57
collezioni; `menu` 325 prodotti + 249 immagini. **Non integrato** prima di
questo intervento: dal legacy al gestionale era passato solo il 2026
(`canonical_2026`), restavano 455 fatture 2025 (+2 del 2024) e 77 chiusure
2025; il **modulo presenze** del vecchio gestionale (lug-ago 2026: 407
timbrature, 443 turni tutti in bozza, 66 acconti per € 26.948,60, 10
liquidazioni) non era in HR (`paghe_mensili` con 0 acconti); 18 versamenti
contanti (€ 71.000) senza prima nota; 54 ordini fornitori storici assenti da
Lotti; Lotti aveva 20 fatture 2026 su 1.085.

- **Feed fatture → Lotti** (`app/routers/lotti_integration.py::_xml_of`): le
  fatture legacy tengono l'XML in `fattura_allegata`; il feed guardava solo
  `xml_raw` e Lotti le scartava come «senza XML». Ora accetta il primo campo
  che contiene una FatturaElettronica. Le 12 fatture gia' ricevute cambiano
  `source_hash` e finiscono in `conflitto_hash` nelle ricevute Lotti: sono
  gia' collegate, nessuna azione.
- **`app/services/integrazione_legacy.py`** + job scheduler
  `integrazione_legacy` (ogni 6 h, primo giro avvio+5 min), idempotente per
  `legacy_row_hash`/`legacy_id`, legge `legacy_staging` con la DSN
  dell'app (`hr_app` ha i grant sull'archivio):
  fatture e chiusure degli anni non migrati → `invoices`/`corrispettivi`
  nella stessa forma dei documenti 2026 (`fonte legacy_staging_<anno>`, IVA
  10% presunta, DA_VERIFICARE; una chiusura non entra se la giornata e' gia'
  registrata da un'altra fonte); versamenti → prima nota cassa (uscita) +
  banca (entrata) con `scrivi_movimento` (`id legacy-vers-<id>`); acconti in
  contanti e saldi in contanti delle liquidazioni → `paghe_mensili.acconti`
  di HR (13ª/14ª = mese 13/14) + `_ricalcola_stato_paga`; timbrature →
  `timbrature` (entrata/uscita in ora di Roma) + `presenze_cloud` solo dove
  il giorno non esiste gia'; anagrafica HR creata per un profilo legacy con
  movimenti, solo se ha il CF (Strazzullo, Rossi); ordini storici →
  `ordini_fornitori` di Lotti (`inviato_fornitori`, `source
  storico_gestionale_legacy`).
  Regole: dipendente per CF, poi «Cognome Nome» univoco (Lesina e Murolo
  hanno CF diversi fra legacy e HR: match per nome), altrimenti saltato e
  contato; gli acconti pagati con **bonifico** e `acconto_tfr` NON diventano
  acconti HR (il bonifico arriva dall'estratto conto); i turni legacy (tutti
  bozze) non si importano.
- Pulizia: le 584 righe `menu_*` di `gestionale.documents` (modulo Menu
  riscritto e poi eliminato il 03/09) rimosse con la guardia; backup in
  `gestionale.documents_menu_rimossi_20260915`.
- **Non fattibile da qui**: il restore PITR (`settings`, `veicoli_noleggio`,
  `fatture_emesse`, `scadenzario`, `riconciliazioni`, `f24_models`,
  `note_credito`, `dettaglio_righe_fatture`, `magazzino`, `prima_nota`,
  `regole_categorie`, `learned_patterns`, `indice_documenti` azzerate il
  14/09) si fa solo dal pannello Supabase (Database → Backups → Point in
  time, 14/09/2026 00:40 UTC): l'MCP non ha quel comando.

### 15/09/2026 — correzione: fatture e chiusure degli anni pregressi NON vanno nel gestionale

Il titolare ha corretto lo scopo dell'integrazione appena fatta: «a me
interessa l'anno 2026, solo i cedolini e gli F24 degli anni pregressi devono
essere nel gestionale». Rimossi da `app/services/integrazione_legacy.py`
(mai andati in produzione: il job non aveva ancora girato, verificato prima
di rimuoverli — zero righe con `integrato_da = integrazione_legacy_2026-09-15`
in `invoices`/`corrispettivi`) `doc_fattura_legacy`, `doc_chiusura_legacy`,
`integra_fatture`, `integra_chiusure` e i test relativi: le 455 fatture e le
77 chiusure 2025 (+2 fatture 2024) restano **solo** nell'archivio
`legacy_staging`, non entrano in `invoices`/`corrispettivi`. Il job
`integrazione_legacy` fa solo versamenti (18, tutti 2026, verificato),
presenze/acconti/timbrature in HR, ordini storici in Lotti. Cedolini
(deposito HR) e F24 (ingest Drive) restano gli unici dati storici attivi nel
gestionale, e funzionano già per conto loro indipendentemente da questo
modulo.

### 15/09/2026 — restore su progetto separato: le 13 collezioni erano già vuote prima dell'incidente

Il titolare ha attivato lui stesso "Restore to new project" dal pannello Supabase
(PITR non disponibile: l'add-on non era mai stato acceso, quindi nessun WAL
prima di oggi) sul backup fisico del 13/09/2026 04:50 UTC — l'ultimo certamente
precedente all'azzeramento delle 00:44-00:54 UTC del 14/09. Progetto di
recupero: `ampnwwusybxhevtvxeng` (org `fatture`, eu-central-1).

**Esito: nessun dato da recuperare.** Le 13 collezioni segnalate a zero
nell'audit del 14/09 (`settings`, `veicoli_noleggio`, `fatture_emesse`,
`scadenzario`, `riconciliazioni`, `f24_models`, `note_credito`,
`dettaglio_righe_fatture`, `magazzino`, `prima_nota`, `prima_nota_righe`,
`regole_categorie`, `learned_patterns`, `indice_documenti`) risultano vuote
**anche nel backup del 13/09**, un giorno intero prima dell'incidente
(confermato: i dati del backup coprono fino alle 04:47 UTC del 13/09, coerente
con l'orario dichiarato). Non erano quindi svuotate dal `delete` di quella
notte: erano già senza righe. Verificato anche nel codice attuale: `settings`,
`veicoli_noleggio`, `fatture_emesse`, `dettaglio_righe_fatture`,
`prima_nota_righe`, `scadenzario`, `regole_categorie` hanno ancora un punto di
scrittura vivo (si ripopolano da sole con l'uso, se la funzione viene
esercitata); `riconciliazioni`, `f24_models`, `note_credito`, `magazzino`,
`prima_nota`, `learned_patterns`, `indice_documenti` non hanno più NESSUN
punto di scrittura nel codice: nomi di collezione morti, non funzionalità
attive da recuperare. La frase dell'audit del 14/09 "restano a zero le
scritture che nessuna fonte esterna sa ricostruire" andava quindi corretta:
per queste 13 non è un dato perso dall'incidente, è una funzionalità che non
aveva ancora prodotto dati (o è stata sostituita da altre collezioni: es.
`riconciliazioni_match`, `warehouse_inventory`, `prima_nota_cassa/banca/
salari`, `regole_categorizzazione` coprono lo stesso bisogno e hanno righe
vere). Il progetto di recupero non serve più: da eliminare dal pannello
Supabase (Project Settings → General → Delete project) per fermare il costo
di circa 10,18 $/mese — non è pausabile da MCP (richiede tier free) e non
esiste un comando di eliminazione via MCP.

### 15/09/2026 — Cassetto Fiscale (770/IVA/IRAP/LIPE/Redditi SC) → fiscal_documents, dichiarazioni agganciate ai F24/quietanze

Richiesta del titolare: cartella Drive con l'export del Cassetto Fiscale
2005-2026, «aggancia gli importi alle quietanze con link al PDF dal
gestionale». La cartella indicata è risultata essere `10_BILANCI_
DICHIARAZIONI/DICHIARAZIONI FISCALI/DA ELABORARE` — un canale già nella forma
standard DA ELABORARE/ELABORATE/ERRORI, semplicemente non ancora agganciato a
nessun motore. Due pezzi mancanti, entrambi risolti riusando sistemi già
esistenti (nessun sistema parallelo):

- **Ingest**: nuovo canale `dichiarazione_fiscale` in
  `app/services/drive_documenti_ingest.py` (motore generico esistente, stesso
  di `dichiarazione_iva`/`cartella_esattoriale`/`avviso_bonario`), cartella
  `GOOGLE_DRIVE_DICHIARAZIONI_FISCALI_FOLDER_ID` (id non segreto, hardcoded
  come `DRIVE_FISCAL_ROOT_FOLDER_ID`), spento di default
  (`ENABLE_DRIVE_DICHIARAZIONI_FISCALI_SYNC`, da accendere via Render dopo il
  deploy). A differenza degli altri canali fiscali non passa un
  `category_hint`: la cartella mescola piu' tipi (770/IVA/IRAP/LIPE/Redditi
  SC), decide `classify_document()` dal contenuto. Filtro solo sul nome file
  (`_da_ingerire_dichiarazione_fiscale`, mai sul contenuto): scarta i singoli
  quadri componenti la dichiarazione ricomposta (`01_Frontespizio...`,
  `0N_Quadro_XX_modulo_N...` — ridondanti, lo stesso dato è già nel PDF
  intero) e i documenti finiti lì per errore (proposte assicurative, avvisi
  bonari, cartelle esattoriali/rottamazione: hanno già un proprio canale) —
  spostati comunque in ELABORATE per non ririleggerli ogni giro.
- **Vista dichiarazioni → F24/quietanze**: `GET /api/fiscal/declarations`
  (tab "Dichiarazioni" di Situazione Fiscale) leggeva il vecchio indice
  Excel/Drive (`drive_document_index.list_declarations`), la cui radice non
  esiste più su Drive dal 03/09 — restituiva sempre lista vuota con avviso.
  `app/services/declaration_registry.py::list_declaration_dossiers` (motore
  Supabase-based che incrocia `fiscal_documents` con
  `TaxPaymentQueryService`/`f24_unificato` per codice tributo + anno
  d'imposta, espone `f24_links` con quietanza e stato banca) esisteva già,
  importato ma mai richiamato da nessun endpoint: codice morto. L'endpoint
  ora chiama quella funzione: il frontend (`SituazioneFiscale.jsx`) era
  *già* pronto a renderla (branch su `item.source_kind` per il vecchio Drive
  vs `openDocument(item.id)` → `GET /api/fiscal/documents/{id}/content` per
  il nuovo, blocco `item.f24_links` già scritto) — bastava collegare i due
  pezzi. Il drill-down "Verifica campi e F24"
  (`/declarations/{id}/field-certainty`, estrazione campi + riconciliazione
  gestionale LIPE/770) resta sul vecchio motore Drive-index: è una funzione
  più ampia, già rotta allo stesso modo per la stessa causa, fuori perimetro
  di questa correzione.
- Non affrontato in questo intervento: il `INDICE.csv` e la sottocartella
  `770/` descritti nel `LEGGIMI.txt` della cartella non esistono nella
  cartella reale (solo file sciolti) — enumerazione fatta per nome file, mai
  indovinata dal contenuto.

#### Quadratura documentale 15/09/2026

- Il protocollo Drive censisce 190 file attivi nel fascicolo canonico
  `10_BILANCI_DICHIARAZIONI/DICHIARAZIONI FISCALI`: 86 PDF erano ancora in
  `DA ELABORARE`, 100 in `ELABORATE` e il registro `fiscal_documents`
  conteneva soltanto 22 dichiarazioni. Il canale va quindi tenuto abilitato in
  produzione fino all'esaurimento della coda.
- Una sola copia byte-identica era collocata nel fascicolo sbagliato: un avviso
  bonario già presente nel canale canonico `04_F24_E_TRIBUTI/AVVISI BONARI`.
  La copia è stata spostata nella quarantena recuperabile, non eliminata.
- `drive_documenti_ingest` non materializza più tutti gli hash di
  `documents_inbox` e non crea più una riga preliminare con `pdf_data` prima
  del registro fiscale. Ogni file usa lookup indicizzati SHA-256/MD5 e passa
  direttamente dall'unico writer `FiscalDocumentIngestionService`.
- Una stessa impronta incontrata in più posizioni non genera un secondo
  documento/versione: tutte le provenienze vengono conservate in
  `source_occurrences` con ID Drive, parent, percorso e hash.

### 16-17/09/2026 — collaudo funzionale E2E sul vivo e stabilità di produzione

Richiesta del titolare: collaudo dell'intera applicazione (ERP, HR, Lotti,
Menu) su dati reali via API autenticata, entità di prova "ZZZ TEST", ogni
passo fallito = bug da correggere subito. Cosa è stato trovato e cambiato
(PR #464-#469, tutte su `main`):

- **Produzione instabile (riavvii ogni ~9 min)**, tre cause distinte, tutte
  chiuse: (1) l'avvio abbandonava dopo 3 tentativi di lettura del catalogo
  Supabase sotto carico → `_MANIFEST_RETRIES = 12` con backoff (#465);
  (2) `/api/health` rispondeva 503 (o restava appeso fino allo statement
  timeout) quando la probe Supabase era lenta → Render lo interpretava come
  servizio morto e riavviava. Ora la liveness risponde **entro 2 s** anche
  con la probe appesa (`_HEALTH_PROBE_TIMEOUT`), stato `degraded` con
  `archivio_errore` invece di 503; `?strict=true` per chi vuole il 503
  (#465, #468); (3) il job "Protocollo-indice documenti Drive" (8 min dopo
  l'avvio) portava la RAM a 1,57 GB su un piano da 2 GB → **spento via env
  Render `PROTOCOLLO_DRIVE_ENABLED=false`**: da riaccendere solo dopo aver
  ridotto la memoria del giro (oggi carica l'intero inventario). Dopo i fix:
  health 200 continuo per tutta la durata del pregresso (6 min) e nei
  controlli successivi.
- **Pregresso nel libro giornale** (#464, #467): il giro ricaricava il
  giornale a ogni documento (~1,4 s l'uno) e girava dentro la richiesta
  HTTP; ora i già registrati si leggono una volta, `force=True` al motore,
  esecuzione in **background** con stato in `sistema_stato`
  (`POST /api/piano-conti/registra-pregresso`, `GET .../stato`), esito
  negativo annotato sul documento (`registrazione_contabile_esito`).
  Esito reale del 17/09: 595 fatture + 160 corrispettivi già in giornale con
  flag riallineati; 828 fatture processate → 3 registrate, 820
  "IVA detraibile non classificata", 5 importo nullo; corrispettivi 23 →
  21 "ripartizione contanti/POS non quadrata con il totale" (chiusure
  31/03-30/07/2026 da verificare), 2 importo nullo.
- **Classificazione manuale → registrazione** (#466): `PUT
  /api/invoices/{id}/classifica` ora calcola `iva_detraibile`/
  `imponibile_deducibile_ires` dal centro di costo e registra subito la
  fattura (prima la scelta manuale non sbloccava il gate IVA).
- **Fatture 2026 doppie legacy↔Drive** (#469). Le 767 fatture importate
  dall'archivio legacy il 14/09 (`source: xml_import`) avevano l'XML in
  `fattura_allegata` ma nessuna identità canonica (`invoice_key`,
  `supplier_vat`, `content_hash`): l'ingest Drive delle stesse fatture ne
  creava una seconda copia (**485 doppioni, 9 registrati due volte** nel
  giornale) e la dedup periodica non poteva né raggrupparle né provarle;
  in più 13 fatture 2025 dell'archivio storico erano entrate nel giornale
  (stato `archiviata` mancante dal filtro del pregresso). Ora
  `app/services/fatture_identita.py` ricava l'identità dall'XML con lo
  stesso parser/chiave/impronta dell'import (sha256 identico a quello
  Drive, verificato in produzione), `pulisci_duplicati_invoices` tiene la
  copia già nel giornale e **storna** la scrittura del doppione
  (`storna_registrazione_fattura`: originale marcata `stornato` +
  scrittura di storno, mai cancellata), il giro dedup ogni 30 min passa da
  `bonifica_identita_fatture`; `POST /api/invoices/bonifica-identita`
  (dry-run sincrono, reale in background) + `GET .../stato`. Delle 7
  coppie di doppioni interni a Drive, 4 hanno lo stesso hash (le risolve
  la dedup), 3 sono collisioni di identità con file diversi (restano in
  `duplicate_review_required`, decide un operatore).
  **Impronta del contenuto** (#481): dopo il giro dedup del 17/09 restavano
  **42 «collisioni»** legacy↔Drive (`stato_import=collisione_identita_da_
  verificare`, copia Drive `da_verificare` con derivati bloccati) che a
  campione erano la STESSA fattura con l'XML diverso di un solo byte (BOM
  `﻿`, a capo, dichiarazione di codifica): lo sha256 dei byte non
  poteva provarle. Ora `impronta_contenuto_fattura` (prefisso `c:`, sha256
  dei campi/righe/riepiloghi/pagamenti letti dal parser) è salvata in
  `content_hash_canonico` a ogni import e nell'identità dall'XML,
  `normalizza_impronte_canoniche` la aggiunge alle fatture attive che ne
  sono prive (300 per giro, chi non ha XML leggibile viene marcato
  `senza_xml_leggibile` e non ritentato), `_source_evidence` la conta come
  prova documentale e `_same_documentary_original` la calcola al volo sulla
  copia esistente: un byte di BOM non è più una collisione né in import né
  in dedup. Quando il doppione viene archiviato, `_chiudi_collisione` toglie
  il blocco alla copia tenuta (`status` imported, `stato_import` attivo,
  `stato_derivati` da_ricalcolare, revisione chiusa) e risolve l'avviso
  `FATTURA_IDENTITA_DA_VERIFICARE` — solo se non restano altre collisioni
  aperte. Log scheduler: `impronte=N (restanti=M)`. **Versione `c2:`**
  (#482): subito dopo il deploy di #481 la ricostruzione Drive ha creato
  un'altra collisione (10:52 UTC) con XML di pari lunghezza: confrontati i
  due file, la copia legacy aveva `Carit�`/`43�` (windows-1252 decodificato
  male, U+FFFD) dove quella Drive aveva `Carità`/`43°`, più righe con spazi
  di riempimento. L'impronta ora normalizza ogni stringa (via ogni carattere
  non ASCII — niente NFKD, perché `à`→`a` non combacerebbe con `�`→`` —,
  spazi compressi; verificato uguale sui due XML reali) e porta il prefisso
  di versione `c2:`; `ha_impronta_corrente` fa ricalcolare dal backfill le
  impronte di versione precedente. **Priorità** (#483): il backfill (300
  per giro, ~3 s a fattura per l'idratazione per id) mette in testa le
  fatture in collisione e le loro controparti, poi le altre per
  `created_at`. **Esito reale 17/09 12:47 UTC** (SQL): collisioni aperte
  **0** (erano 46 alle 11:05; le 4 con ancora `stato_import=collisione_
  identita_da_verificare` sono doppioni archiviati, la copia tenuta è
  `attivo`), `duplicate_review_required` aperti 0, derivati bloccati 0,
  fatture attive 982, tutte con impronta `c2:` o marcate `senza_xml_
  leggibile` (13), doppioni archiviati in totale 503 (138 in questa
  sessione), avvisi `FATTURA_IDENTITA_DA_VERIFICARE` risolti dal dedup. Il
  conteggio giusto delle collisioni aperte è `stato_import` di collisione
  **e** `status` non archiviato. **Crash Postgres Supabase 12:33–12:38
  UTC**: `database system was interrupted; last known up at 12:33:49`,
  `not properly shut down; automatic recovery in progress`, riavvio
  `starting PostgreSQL 17.6` alle 12:38:32 → ~5 minuti di database giù
  durante il backfill (PostgREST senza schema cache, 5xx sulle RPC, job
  scheduler saltati un giro, health probe fallita); l'app ha ripreso da
  sola senza deploy né DDL. È il segnale più forte finora che il compute
  Micro non regge il carico: valutare il passaggio a Small.
- **Collaudi E2E riusciti** (dati "ZZZ TEST" creati e ripuliti): ERP
  fattura XML → classificazione → scrittura in partita doppia in
  quadratura → eliminazione; corrispettivo XML → registrazione; Lotti
  prodotto → carico → scarico oltre stock respinto → doppio tap respinto →
  bozza riordino con `richiesto_da` → pulizia; HR login/anagrafica/paghe;
  Menu pubblico e admin. F24: quadratura quietanze Drive 459 controllate,
  459 quadrate, 0 errori. PayPal: sync storico 02/2025→09/2026 a finestre
  di 30 giorni, transazioni 66 → 159 (113 uscite, 20 PagoPA).
- **Aperto, con causa nota** (non risolto in questa sessione): gli endpoint
  sincroni che ricaricano collezioni intere per ogni elemento vanno oltre
  i 5 minuti del proxy Render e cadono per statement timeout Supabase —
  `POST /api/paypal-api/riconcilia` (`_candidate_invoices` ricarica
  `invoices` per ogni transazione: 0 transazioni agganciate a fatture, 26
  a banca), `GET /api/paypal-api/account-ids-non-mappati`, `POST
  /api/admin/riallinea-pagamenti-fatture` (>170 s anche in dry-run), `POST
  /api/prima-nota-salari/deposita-cedolini-in-hr`. Stesso rimedio già
  applicato al pregresso: prefetch unico + esecuzione in background con
  stato. Banca 2026: 1.920 movimenti, 652 riconciliati, 26 agganciati a
  fatture, 1.765 senza categoria. Le 20 note di credito legacy
  (`tipo_documento` TD04) verrebbero registrate come costi dal motore, che
  non distingue il tipo documento: da trattare prima di classificarle.
  Il database Supabase (compute Micro, 1,9 GB di cui 1 GB `documents`) è
  il collo di bottiglia di tutto quanto sopra: l'adattatore rilegge intere
  collezioni con payload (XML, PDF) a ogni `find` non puntuale.
- **Cache incrementale del runtime** (PR #471, migrazione
  `20260917040000_gc_collection_versions.sql` applicata il 17/09 03:46 UTC).
  Richiesta del titolare: «il sito deve lasciare i dati scritti, non
  ricaricarli ogni volta da Supabase, altrimenti i costi aumentano». Dal
  15/09 ogni `find` non puntuale rileggeva l'intera collezione: nei log
  edge 1.400-2.300 letture complete ogni 10 minuti nei picchi. Ora
  `SupabaseTable` tiene in memoria la versione **leggera** di ogni
  collezione letta (senza i campi di `DOCUMENT_PAYLOAD_FIELDS`: XML, PDF,
  foto); prima di servirla chiede UNA firma per tutte le collezioni
  (`gc_collection_versions`: conteggio + ultimo `updated_at`) al più ogni
  15 s; firma diversa → solo i documenti modificati dopo l'ultima lettura
  (`gc_fetch_collection_since`), rilettura completa solo se il conteggio non
  torna. Le letture che vogliono il payload usano la cache per scegliere i
  documenti e li scaricano per id (`gc_fetch_documents_exact`, lotti da 500
  che si dimezzano sui timeout fino a 10 — PR #474: prima, oltre 1.000
  documenti si tornava alla lettura completa con payload, che sotto carico
  teneva il lock operativo per decine di minuti e fermava il job dedup
  fatture; un `find_one` per id con payload va dritto all'indice remoto,
  senza firma della cache e senza lock). **Presenza del payload** (PR #475,
  migrazione `20260917073000_payload_stato.sql`): decine di query filtrano
  su «ha il PDF / senza XML» (`pdf_data: {$exists, $ne None, $nin [None,
  ""]}` in email, bonifici, prima nota salari, verbali) e forzavano letture
  complete CON allegati (~280 pagine in 17 min nei log edge del 17/09 07:00).
  Le RPC proiettate allegano ora `_payload_stato` = {campo: assente|nullo|
  vuoto|pieno} per ogni campo escluso; l'adattatore riscrive quei predicati
  sul marcatore e li serve dalla cache (anche `count_documents`); un filtro
  sul CONTENUTO del payload (regex, valore) continua a leggere il payload,
  e in quel caso il campo citato dal filtro arriva anche se la proiezione
  lo esclude (prima il conteggio poteva risultare 0 in silenzio). Il
  marcatore non esce mai dall'adattatore. Il lotto di idratazione per id e'
  ricordato per tabella (dimezzato sui timeout, raddoppiato dopo 8 lotti
  riusciti). Migrazione applicata in produzione il 17/09 07:43 UTC (dopo il
  deploy del codice: PostgREST ha ricaricato lo schema per ~2 minuti con
  503 «Could not query the database for the schema cache», l'app e' andata
  in fallback a letture complete e poi e' rientrata da sola). Misurato
  07:44–07:57 rispetto a 06:55–07:12: letture complete non proiettate
  183 → 22 (quasi tutte nel fallback dei 2 minuti), memoria istanza
  937 → 486 MB, fatture legacy normalizzate dal job dedup 49 → 359.
  **Probe di /api/health condivisa** (PR #476): Render chiama la liveness
  ogni pochi secondi e ogni probe era una scrittura + cancellazione su
  `gestionale.documents` con trigger (130 probe in 13 minuti da 7 s l'una
  a database saturo); ora una sola probe in volo per processo, esito
  riusato 60 s (15 s se fallita), una probe oltre il budget continua in
  background e il giro successivo ne raccoglie l'esito. **Finestra di
  grazia della firma** (PR #477): se `gc_collection_versions` fallisce in
  modo transitorio (timeout, 503 «schema cache» durante una migrazione)
  la cache resta valida per 120 s dall'ultima firma buona invece di
  ripiegare su letture complete (07:43–07:45: 30 fallimenti = 30 letture
  complete a database già saturo); oltre la finestra, lettura completa
  come prima. **Cache dell'adattatore HR** (PR #478,
  `app/hr/db_supabase.py`): `pg_stat_statements` dal 01/09 contava
  218.000 letture complete di `hr.app_paghe_mensili` (32 ms l'una), 778 di
  `app_pagamenti_esiti` da 4,7 s e 321 di `app_bonifici` da 8 s (PDF
  de-toastati e poi buttati): ogni `find`/`find_one`/`count`/`update`
  rileggeva l'intera tabella e filtrava in Python. Ora ogni tabella letta
  resta in memoria nella versione leggera (senza `pdf_data`/`file_data`);
  prima di servirla una sola query legge la firma di tutte le tabelle in
  cache (`count(*)` + `max(xmin)`: cambia a ogni insert/update/delete,
  anche fatti fuori dall'app come il deposito cedolini) al più ogni 15 s;
  firma diversa → rilettura leggera di quella tabella; le scritture del
  processo aggiornano la copia e ribasano la firma; i PDF arrivano per id
  solo alle letture che li vogliono (e un `update_one` idrata il documento
  prima di riscriverlo: mai un PDF perso); un filtro che guarda dentro un
  campo pesante legge la riga intera da SQL; firma non disponibile →
  lettura diretta (finestra di grazia 120 s); `HR_RUNTIME_CACHE=0` la
  spegne. **DDL HR solo se serve** (PR #479): `_assicura_tabella` faceva
  SEMPRE `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE … ENABLE ROW LEVEL
  SECURITY` al primo accesso di ogni tabella (29 tabelle = 58 DDL a ogni
  avvio dell'istanza): ogni DDL fa ricaricare lo schema a PostgREST, che
  per minuti risponde 503 «Could not query the database for the schema
  cache» a TUTTE le RPC del gestionale (visto a ogni deploy: 07:43, 09:05).
  Ora guarda `pg_class` e fa il DDL solo se la tabella manca o non ha la
  RLS. **Letture leggere residue** (PR #480): i candidati della
  riconciliazione bancaria (`riconciliazione_bancaria.py`, fino a 500
  fatture per movimento) e il feed fatture per Lotti (`lotti_integration.
  _documents`, tutte le fatture ogni 15 min) leggevano ancora l'XML —
  erano le letture per id in timeout (19 in 15 min, 31 s l'una). Ora
  entrambe usano `metadata_projection`; il feed Lotti ricava l'impronta da
  `content_hash` (= sha256 dell'XML, stesso valore: `source_hash` invariato,
  test dedicato) e idrata per id solo chi ne è privo; il dettaglio per
  Lotti cerca per `id`/`invoice_key` invece di scorrere tutto. La dedup
  fatture (`pulisci_duplicati_invoices`) non si ferma più al primo
  `update_one` in timeout (conta `archiviazioni_fallite`). Le scritture
  del processo aggiornano la cache dopo l'esito positivo dell'RPC. Trigger
  `documents_touch_updated_at` garantisce `updated_at` anche per scritture
  fatte fuori dall'app. Fallback automatico alla lettura completa se le RPC
  mancano o falliscono; `GC_RUNTIME_CACHE=0` la spegne. **Firma in tempo
  costante** (migrazione `20260917063000_collection_versions_table.sql`,
  applicata 06:35 UTC): la `group by` su tutta `documents` superava i 20 s
  con il disco saturo; ora `gestionale.collection_versions` (una riga per
  collezione: conteggio + ultimo `updated_at`) e' mantenuta dai trigger
  `documents_touch_updated_at` (before insert/update) e
  `documents_collection_versions` (after insert/update/delete) e
  `gc_collection_versions` la legge senza scansioni. Le letture leggere
  (`gc_fetch_collection_projected`, `_since`) restano costose lato
  database perche' `data - campi` deve comunque de-toastare il jsonb intero:
  la vera riduzione del costo Supabase arriva dalla cache (una lettura per
  collezione, poi solo delta). **Regole per chi
  scrive codice**: (1) per liste/conteggi/lookup usare sempre una
  proiezione di esclusione del payload (`metadata_projection(collection)`)
  o inclusiva senza payload: viene servita dalla cache senza RPC; (2) il
  payload si legge per id (`find_one({"id": …})`), mai con `find({})` su
  tutta la collezione; (3) `pulisci_duplicati_invoices` e
  `fatture_identita` sono già così. Attenzione alle migrazioni DDL su
  `gestionale.documents`: `create index`/`create trigger` prendono lock
  esclusivi e con le letture lunghe in corso hanno bloccato l'app per ~30 s
  (lock timeout 8 s del ruolo `authenticator`): farle a database scarico o
  con `create index concurrently`.
- **Timeout del ruolo `anon`** (migrazione `20260917030000_anon_statement_
  timeout.sql`, applicata in produzione il 17/09 02:52 UTC): PostgREST
  esegue TUTTE le RPC del runtime (`gc_*`, `lotti_*`) come ruolo `anon`, che
  su Supabase nasce con `statement_timeout = 3s`. Nei log: 272 "canceling
  statement due to statement timeout" in 17 minuti, ogni pagina fallita
  ritentata dall'app con lotti più piccoli (carico moltiplicato), e il
  `/lotti/api/health` rispondeva 500 (`select distinct collection` su 26.250
  righe oltre i 3 s a cache fredda). Ora 20 s (sotto i 60 s dei client
  HTTP); il ruolo `authenticator` resta a 8 s. Da rivedere se si cambia
  compute o si riduce il payload di `documents`.

### Stato precedente

- Il default del codice è `DATA_BACKEND=sheets`.
- legacy DB è stato rimosso come backend supportato e non va usato in produzione.
- Qualsiasi riferimento, variabile o script relativo a legacy DB è deprecato. Strumenti o script storici devono essere isolati, marcati come "legacy / solo per migrazione" e usati unicamente in procedure controllate e verificabili.
- La migrazione dei dati storici richiede confronto di conteggi e hash, ricostruzione completa e prove di scrittura; fino a verifica completa i dati storici non devono essere cancellati senza autorizzazione e checklist di cutover approvata.

### Destinazione Drive-only

La radice operativa deve contenere:

```text
REGISTRO DATI/
  Ceraldi ERP - Registro dati
PARTENOPAY/
CODICI TRIBUTO/
QUIETANZE/
DICHIARAZIONI/
```

La mappa privata delle cartelle è il foglio `_INDICE_DRIVE` del registro.
Per ogni area operativa contiene cartella canonica, `Da elaborare`,
`Elaborate`, `Errori` e nome della variabile Render. Non duplicare gli ID nei
file pubblici del repository e non reintrodurre alias Render per la stessa
cartella.

Il registro usa un foglio per archivio logico. Ogni riga conserva almeno:

- progressivo stabile del foglio;
- `canonical_id` dell'entità;
- `operation_id` per collegare fattura, pagamento, banca e Prima Nota;
- payload completo e ricostruibile;
- hash del payload e provenienza;
- data di acquisizione e versione del parser.

Regole del cutover:

1. deduplicare la sorgente per identità canonica e hash;
2. bloccare ID uguali con payload differenti;
3. copiare il dataset completo nel registro Drive;
4. confrontare conteggi unici e digest sorgente/destinazione;
5. ricostruire il runtime dai fogli e provarne la scrittura;
6. configurare esplicitamente il registro e verificare la produzione;
7. confermare che non esistano variabili o percorsi di persistenza alternativi.

La memoria del processo è soltanto una cache ricostruibile: Drive/Sheets resta
sempre la sorgente persistente.

## HR (AppDipendenti) portata pari pari — `app/hr/` + `frontend_hr/` a `/hr`

- **[03/09/2026]** I moduli riscritti `app/hr` + `frontend/src/hr` (rotte
  `/api/hr/...`, `/hr`, `/portale`, PIN unificato) sono stati **eliminati**:
  al loro posto c'è l'app AppDipendenti originale, così com'era. `app/hr/` =
  copia di `AppDipendenti/backend/app` con i soli import riscritti nel
  namespace `app.hr.*` (`app/hr/embed.py`: `hr_app`, `avvia_hr`/`arresta_hr`
  richiamati dal lifespan di `app/main.py` solo con scheduler attivo — ha un
  suo APScheduler — e `monta_frontend`). Montata in `app/main.py` a `/hr`
  PRIMA del catch-all della SPA dell'ERP: API a `/hr/api/...`
  (`/hr/api/health`, `/hr/api/auth/pin-login`, `/hr/api/dipendenti-cloud/...`).
- **Login proprio**, non quello del gestionale: tocca-il-nome + PIN personale
  per i dipendenti, "Accesso amministratore" con il PIN dell'env `HR_PIN_CODE`;
  JWT firmato con `HR_JWT_SECRET` (sessione dipendente e admin: 7 giorni,
  finché non si preme "Esci" — prima l'admin era 2 ore, cambiato il 04/09/2026
  perché `RequireRole` in `frontend_hr/src/main.jsx` controlla l'`exp` del
  JWT ad ogni cambio pagina, quindi bastava restare sull'app oltre le 2 ore
  perché la navigazione successiva rimandasse al PIN).
  Il middleware del gestionale non c'entra: `/hr/...` è fuori da `/api/`.
  I ruoli `dipendente`/`responsabile_turni` non esistono più in
  `app/utils/ruoli.py`.
- Dati: Postgres/Supabase dell'app originale via `HR_SUPABASE_DB_URL`
  (fallback `APPDIPENDENTI_DB_URL`, poi `SUPABASE_DB_URL`), tabelle `app_<nome>`
  con colonna `doc jsonb` (adattatore Mongo→Postgres `app/hr/db_supabase.py`).
  Nessun dato HR nel registro Drive/Sheets/`gestionale.documents`.
- `frontend_hr/` = copia di `AppDipendenti/frontend` (Vite, `base: '/hr/'`,
  build in `frontend_hr/dist` compilata su Render, non committata): gestione
  desktop a `/hr/`, portale mobile a `/hr/portale`. Voce "HR" (solo admin)
  nel menu Altro = link a pagina intera.

## Menu portato pari pari — `app/menu/` + `frontend_menu/` a `/menu`

- **[03/09/2026]** Il modulo riscritto `app/menu` + `frontend/src/menu`
  (rotte `/api/menu/...`, Tailwind, `/menu-banco`) è stato **eliminato**: al
  suo posto c'è l'app Menu originale. `app/menu/` = copia di `Menu/backend`
  con import nel namespace `app.menu.*` (`app/menu/embed.py`: `menu_app`,
  `avvia_menu`/`arresta_menu` no-op). `app/menu/server.py` monta da solo il
  build `frontend_menu/build` se esiste; `app/main.py` monta `menu_app` a
  `/menu` PRIMA del catch-all della SPA: API a `/menu/api/...`
  (`/menu/api/health`, `/menu/api/admin/login`).
- **Login admin proprio** username/password (`MENU_ADMIN_USERNAME`,
  `MENU_ADMIN_PASSWORD`, JWT `MENU_JWT_SECRET`), pagina `/menu/admin/login`.
- Dati nel progetto Supabase `Lotti-HACCP`, tabelle `menu_*`
  (`menu_categories`, `menu_subcategories`, `menu_products`, `menu_allergens`,
  `menu_orders`, `menu_sale`, ...) via client PostgREST `MENU_SUPABASE_URL` /
  `MENU_SUPABASE_KEY`; immagini nel bucket Storage `menu-images`.
- **Il menu vero si gestisce su Qromo** (`ceraldicaffe.qromo.it`): bottone
  "Sincronizza da Qromo" nel tab Prodotti dell'area admin →
  `POST /menu/api/admin/sync-qromo` (`app/menu/qromo_sync.py`, aggiunta
  GestionaleCloud: legge le costanti JavaScript della home Qromo, esclude le
  sottocategorie di cassa `BANCO - *`, riduce gli allergeni ai 14 UE,
  sostituisce per intero categorie/sottocategorie/prodotti; `GET
  .../sync-qromo/preview` = prova a secco). Test: `tests/test_menu_qromo_sync.py`.
- URL del menu per i clienti (QR al tavolo):
  `https://gestionalecloud.onrender.com/menu/`. `frontend_menu/` = copia di
  `Menu/frontend` (CRA, `PUBLIC_URL=/menu` e `REACT_APP_MENU_BACKEND_URL=/menu`
  in `.env.production`, tracciato apposta — **[FIX 04/09/2026]** rinominata da
  `REACT_APP_BACKEND_URL`: un env Render generico con quel nome, rimasto dal
  backend Lotti standalone, veniva letto da `process.env` al posto del valore
  del file durante la build condivisa (`build_frontends.sh`), mandando ogni
  chiamata admin del Menu a un host esterno spento — vedi la stessa nota su
  Lotti sopra, stesso bug, stesso fix; build compilata su Render). Voce "Menu"
  nel menu Altro = link a pagina intera su `/menu/admin`.
- **Prodotti da Lotti [03/09/2026, richiesta del titolare]**: ogni ricetta di
  Lotti viene replicata nel Menu con la stessa foto; il titolare sceglie se
  compare nel menu pubblico. Ponte `app/lotti/servizi/menu_bridge.py`
  (`pubblica_prodotto_nel_menu` / `rimuovi_prodotto_dal_menu`, client
  sincrono del Menu eseguito con `asyncio.to_thread`), agganciato in
  `app/lotti/routers/ricette.py` a `POST /lotti/api/ricette`, `PUT`/`PATCH`
  `/ricette/{id}`, `/prezzo-vendita`, `/reparto`, `POST /ricette/{id}/upload-foto`,
  `DELETE /ricette/{id}`; l'esito va nella risposta come `menu_sync`
  (`pubblicato` | `aggiornato` | `rimosso` | `non_configurato` senza
  `MENU_SUPABASE_URL` | `errore`) e non fa mai fallire l'endpoint Lotti.
  Campi: ricetta `menu_pubblico` (bool, default False, checkbox "Mostra nel
  menu pubblico" in `FormRicetta.jsx`; `PATCH` lo accetta) → `menu_products.
  visible`; `menu_products.origine = "lotti"`, `lotti_ref = "ricetta:<id>"`
  (chiave idempotente: update se esiste, altrimenti insert con id ≥ 1.000.000
  per non collidere con gli id Qromo). Categoria "Produzione Ceraldi" +
  sottocategoria per reparto (Pasticceria/Rosticceria/Bar/Altro), create al
  volo con `origine = "lotti"`. Prezzo `"3.50€"` da `prezzo_vendita`,
  allergeni Lotti → 14 id UE (`MAPPA_ALLERGENI_MENU`), descrizione = `descrizione`
  o `note`. Foto: byte da `foto_files` copiati nel bucket `menu-images` al
  percorso `lotti/<foto_id>.<jpg|png|webp>` (upsert), URL pubblico in `image`;
  non si ricarica se la riga punta già allo stesso `foto_id`. Il menu
  pubblico (`GET /menu/api/menu/`, `/subcategories/{id}`, `/products/{id}`,
  `/search`) esclude `visible=false`; `/admin/products/all` e il CRUD admin
  espongono/accettano `visible`. La sync Qromo cancella solo le righe con
  `origine IS NULL`: le righe di Lotti sopravvivono. Test:
  `app/lotti/tests/test_menu_bridge.py`, `tests/test_menu_public_visible.py`.

## App portate pari pari — `app/lotti/` + `frontend_lotti/`, `app/menu/` + `frontend_menu/`, `app/hr/` + `frontend_hr/`

- **[03/09/2026, decisione del titolare]** Le app del gruppo NON vanno
  ricostruite dentro il gestionale: si prende il repository originale e lo si
  porta dentro così com'è ("voglio l'app così come era"). Ogni app è un
  documento a sé: backend originale montato come sub-app FastAPI a
  `/<app>` (rotte `/<app>/api/...`, **proprio login**), frontend originale
  compilato con la propria toolchain e servito a `/<app>/` dalla stessa
  sub-app. Nessuna contaminazione di stile con il layout dell'ERP.
- **Lotti (HACCP)**: `app/lotti/` = copia di `Lotti/backend` con i soli import
  riscritti nel namespace `app.lotti.*` (`app/lotti/embed.py`: `lotti_app`,
  `avvia_lotti`/`arresta_lotti` richiamati dal lifespan di `app/main.py`
  perché Starlette non propaga lo startup alle sub-app, `monta_frontend`).
  Montata in `app/main.py` PRIMA del catch-all della SPA dell'ERP. Env
  namespaced per non collidere con quelle del gestionale:
  `LOTTI_SUPABASE_URL`, `LOTTI_SUPABASE_ANON_KEY`, `LOTTI_DB_SECRET`
  (progetto Supabase `Lotti-HACCP`, tabella `lotti_documents` + RPC
  `lotti_*`), `LOTTI_AUTH_SECRET` (fallback `AUTH_SECRET`), `LOTTI_DB_NAME`.
  Senza `LOTTI_SUPABASE_URL` l'archivio è in memoria (mongomock, non
  persistente: solo test/sviluppo). Il PIN admin di Lotti resta quello di
  Lotti. `frontend_lotti/` = copia di `Lotti/frontend` (CRA), build con
  `PUBLIC_URL=/lotti`, `REACT_APP_LOTTI_BACKEND_URL=/lotti` (`.env.production`,
  tracciato apposta — **[FIX 04/09/2026]** rinominata da `REACT_APP_BACKEND_URL`:
  un vecchio env Render generico con quel nome, rimasto dal backend Lotti
  standalone (`lotti-backend-2wwb.onrender.com`), veniva letto da `process.env`
  al posto del valore del file durante la build — e per lo stesso motivo da
  `frontend_menu` (vedi sotto, stesso nome generico, stesso fix), mandando
  ogni chiamata di entrambe le app a un host esterno spento: da fuori sembrava
  un server lento, in realtà la richiesta non arrivava mai al servizio giusto);
  le foto SAIMA sono referenziate dai dati come
  `/saima/...` e vengono servite dall'host da `frontend_lotti/build/saima`.
  Voce "HACCP Lotti" nel menu Altro (link a pagina intera). I test originali
  vivono in `app/lotti/tests` (`AUTH_SECRET=test python -m pytest app/lotti/tests`).
  La guardia `tests/test_drive_only_architecture.py` esclude `app/lotti`
  (usa l'API Mongo in memoria per progetto, non è l'archivio dell'ERP).
- **Menu e HR: fatto (03/09/2026)**, vedi le due sezioni qui sopra. I moduli
  riscritti `app/menu`, `frontend/src/menu`, `app/hr`, `frontend/src/hr`
  non esistono più (con i loro test, le pagine 67-76 di `page_catalog.json`
  e le voci `/hr`, `/portale`, `/menu*` del router React). Le guardie
  `tests/test_drive_only_architecture.py`, `tests/test_csrf_cookie_guard.py` e
  `tests/test_no_hardcoded_deprecated_collections.py` escludono `app/lotti`,
  `app/menu`, `app/hr` (codice di app esterne, non dell'ERP); i test delle
  app restano quelli originali (`app/lotti/tests`, `app/hr/tests`).
  `render.yaml` compila anche `frontend_menu` e `frontend_hr` e dichiara le
  env `LOTTI_*`, `MENU_*`, `HR_*` (`sync: false`).
- Fase successiva: consolidare i dati delle app nel progetto Supabase
  `GestionaleCloud`.

## Doppioni rimossi il 03/09/2026: HACCP nativo e pagina «Cedolini paga»

- **Ordine del titolare** («elimina bottone Tracciabilità e codice associato,
  `/salari` e `/tracciabilita`»), regola «un solo sistema per funzione».
- **HACCP nativo eliminato**: voce «Tracciabilità» della TopNav, route
  `/tracciabilita` + `frontend/src/pages/TracciabilitaHACCP.jsx`, router
  `app/routers/haccp.py` (`/api/haccp/*`), servizi
  `app/services/haccp_traceability.py` e `haccp_operations.py`, costanti
  `COLL_HACCP_*` in `app/db_collections.py`, indici `haccp_*` in
  `app/database.py`, fogli `haccp_*` di `PROMPT_MASTER.md`, i test
  `tests/test_haccp_*.py` e la pagina 66 del catalogo. Al suo posto c'è l'app
  Lotti a `/lotti`. **Resta** `app/routers/lotti_integration.py`
  (`/api/integrations/lotti/*`): è il feed fatture letto da
  `app/lotti/routers/gestionale_fatture.py`. `docs/ADR-001-HACCP-LOTTI-DRIVE-
  SHEETS.md` è conservato come documento storico.
- **Pagina «Cedolini paga» eliminata**: voce nel menu Altro, route `/salari`,
  `frontend/src/pages/CedoliniSalari.jsx` (+ test), pagina 10 del catalogo;
  in `MappaGestionale.jsx` l'area «Cedolini» apre `/hr/`. Con lei sono spariti
  i soli endpoint che esistevano per quella pagina: `GET /api/prima-nota-salari/
  salari-ricostruiti`, `GET .../export-appdipendenti/preview` e `.../download`
  (+ `app/services/appdipendenti_export.py`). **Resta tutto il resto** del
  router `/api/prima-nota-salari` (Prima Nota salari, import paghe/bonifici,
  PDF cedolino/bonifico per riga, riconcilia — usati da `primaNotaStore.js`,
  dal MCP e dai test), l'ingestione cedolini (`drive_cedolini`,
  `email_download`, `sync_prima_nota_salari_da_cedolini` in `app/main.py`),
  F24, TFR e `app/routers/employees/dipendenti.py`.
- Il catalogo canonico conta ora **64** schermate (id contigui).

## Cedolini: un solo sistema (HR)

- **[03/09/2026, decisione del titolare]** «Il gestionale scarica i dati dalla
  posta … portare i cedolini in HR; niente ponte; a cosa serve una sezione
  cedolini nel gestionale e un'altra in HR?». L'archivio cedolini che gli
  utenti vedono è **solo l'app HR** (`/hr`, tabella `public.app_cedolini`
  del Postgres HR, DSN `HR_SUPABASE_DB_URL` → fallback `APPDIPENDENTI_DB_URL`,
  `SUPABASE_DB_URL`, già dichiarate in `render.yaml`).
- Il gestionale continua a **scaricare** le buste (Drive:
  `app/services/drive_cedolini_ingest.py`; email: `app/routers/email_download.py`
  → `processa_nuovi_documenti` → `cedolini_manager` → `salari_unificati_v2`)
  e a ricavarne la **Prima Nota salari**: per questo il registro interno
  `cedolini` resta scritto, ma non ha più una pagina propria.
- **Deposito in HR**: `app/services/hr_cedolini_deposito.py::
  deposita_cedolino_in_hr(cedolino)` è richiamato, protetto da try/except,
  subito dopo OGNI scrittura di un cedolino nel gestionale
  (`salari_unificati_v2.processa_cedolino_v2`, `cedolini_manager.
  processa_cedolino_completo`, `post_download_pipeline.processa_cedolini_da_email`,
  `upload_ai_processor.process_upload_cedolino`, `ai_integration_service`,
  `document_data_saver.save_busta_paga_to_gestionale`, `email_full_download.
  smart_auto_associate`, `POST /api/dipendenti/buste-paga`, `POST
  /api/prima-nota-salari/salari/{id}/cedolino-pdf`). Scrive con asyncpg
  direttamente in `app_cedolini` (`id text` + `doc jsonb`, stessa forma
  dell'adattatore `app/hr/db_supabase.py`) senza toccare `app/hr/**`.
- Forma del documento = quella dei 1291 cedolini già in HR: `mese`/`anno`
  interi, `competenza` `"YYYY-MM"`, `tipo_cedolino` `ordinario` (il "mensile"
  del gestionale) / `tredicesima` / `quattordicesima`, `netto`, `lordo`,
  `competenze`, `trattenute`, `nome_dipendente` = `dipendente_nome`,
  `filename`/`pdf_filename`, `pdf_data` base64, `fonte` = `gestionale_cloud`,
  `parser_template` solo se è un modello noto all'HR (`zucchetti_new`,
  `zucchetti_classic`, `csc_napoli`, `teamsystem`), `giorni_lavorati`,
  `livello`; `dipendente_id`/`nome` risolti da `app_dipendenti` per codice
  fiscale (mai gli id del gestionale). Provenienza conservata in
  `gestionale_cedolino_id`, `gestionale_source`, `cedolino_dedup_key`.
- **Dedup, mai sovrascrittura**: un cedolino HR esistente con la stessa
  `cedolino_dedup_key`, oppure stesso (CF maiuscolo, anno, mese, tipo), non
  viene toccato (`esito: gia_presente`); 13ª/14ª dello stesso mese restano
  buste distinte. Senza DSN il deposito è un no-op segnalato una volta nel
  log (`hr_non_configurato`); un errore di rete non ferma mai l'ingestione.
- **Backfill**: `POST /api/prima-nota-salari/deposita-cedolini-in-hr` (admin,
  `?dry_run=true` per contare senza scrivere) deposita tutto il registro
  `cedolini` e ritorna `inseriti`/`gia_presenti`/`errori`/`saltati`; da shell
  `python -m app.services.hr_cedolini_deposito --dry-run`. Test:
  `tests/test_hr_cedolini_deposito.py`.

## Canali operativi e conoscenza

- Telegram è l'unico canale attivo per alert e notifiche operative.
- Non registrare router, webhook o fallback WhatsApp legacy.
- Obsidian è una proiezione consultiva della documentazione: non è un database,
  non riceve scritture contabili e non sostituisce Drive/Sheets.

## Identità, duplicati e relazioni

- Nessuna entità si associa per solo importo.
- Una relazione certa richiede identità/provenienza coerente e importo esatto
  al centesimo quando l'importo fa parte della prova.
- Nei casi ambigui mostra i candidati (`Scegli fattura`, `Scegli driver`,
  `Scegli verbale`) e non applicare il collegamento.
- Gli import sono idempotenti: stesso hash o stessa identità canonica non crea
  una seconda operazione.
- Fattura, disposizione, ricevuta, quietanza e movimento bancario sono prove
  distinte, collegate da `operation_id`, mai fuse in un solo record.
- I documenti originali restano immutabili. Conservare hash, fonte, versione,
  timestamp e log. I duplicati documentali si marcano; non si eliminano in
  modo permanente.

## Ingresso documenti e Drive

- `Documenti > Import` è l'unico ingresso manuale operativo.
- Le fatture elettroniche arrivano dal canale Drive/SDI configurato. Una
  fattura italiana trovata per email è un'anomalia, non una seconda fonte.
- Gmail/IMAP può acquisire F24, quietanze, cedolini e verbali soltanto dai
  mittenti/canali autorizzati.
- Le ricerche email complete usano `in:anywhere`, preservano message ID,
  thread ID e SHA-256 e non spostano né cancellano gli originali.
- Gli estratti conto confluiscono nell'area unica configurata; la fonte si
  determina da nome e contenuto. Se non è riconoscibile, il file va in errore
  con motivazione, mai classificato per supposizione.
- Gli ZIP vengono prima validati, deduplicati e inventariati; poi i documenti
  riconosciuti entrano nei rispettivi flussi.

## Regole contabili vincolanti

- Piano dei conti: solo CEE ufficiale in
  `app/services/piano_conti_ufficiale.py`; conversioni tramite
  `app/services/mapping_piano_conti.py`.
- Motore unico Prima Nota: `app/services/scritture_contabili.py`. Non creare
  nuovi `insert_one` diretti per scritture contabili.
- Libro giornale in partita doppia (`movimenti_contabili`): motore unico
  `app/services/registrazione_contabile.py`, alimentato **automaticamente**
  all'import di fatture (`fatture_upload`) e corrispettivi RT
  (`corrispettivi_helpers`, `CorrispettiviService`) tramite
  `registra_documento_import` (idempotente per documento con
  `idempotency_key = reg:<tipo>:<id>`, mai bloccante, esito negativo annotato
  in `registrazione_contabile_esito`). Il pregresso si recupera con
  `POST /api/piano-conti/registra-pregresso?dry_run=` (admin). Non aggiungere
  altri punti di scrittura.
- Navigazione tra contropartite: un solo componente
  `frontend/src/components/LinkContropartita.jsx` (`ROTTE_CONTROPARTITA`); i
  deep-link letti dalle pagine sono `/fatture?invoice_id=`,
  `/riconciliazione/banca?movimento=`, `/prima-nota#sezione=banca&selected=`,
  `/contabilita/verifica?conto=`, `/contabilita/giornale?conto=|scrittura=`.
- Ricavi: solo corrispettivi RT. Le fatture ricevute sono costi; gli accrediti
  POS e i payout non sono nuovi ricavi.
- POS: corrispettivo XML, chiusura terminale e accredito bancario sono tre
  fatti distinti. Numia e SumUp restano circuiti separati.
- SumUp corrente è acquisito dall'API; Numia corrente è la chiusura manuale
  serale; Numia storico è ricostruito dagli export operativi del gestore su
  Drive, deduplicati e accorpati per giorno. Tutte e tre le fonti creano
  l'attesa bancaria; l'estratto conto può soltanto riconciliarla.
- Un versamento contanti genera uscita Cassa e corrispondente entrata Banca con
  lo stesso `operation_id`; l'estratto conto riconcilia il trasferimento.
- Prima Nota Banca non è la copia dell'estratto conto: una riga entra quando è
  nota la causale contabile oppure appartiene alle categorie bancarie senza
  documento ammesse dal codice.
- F24, singole righe tributo, quietanza e movimento bancario sono entità
  distinte. La quietanza documenta il pagamento ma non sostituisce la prova
  bancaria.
- Cedolini e bonifici salario si associano per dipendente, periodo e regole
  temporali; non si richiedono importi identici quando esistono acconti o
  trattenute.
- Date mostrate all'utente: `gg/mm/aaaa`.

## PartenoPay, verbali e flotta

- Conservare email, verbale, avviso, ricevuta PagoPA/PayPal e movimento banca
  come prove separate.
- Associazione automatica driver: targa normalizzata + data/ora infrazione +
  storico assegnazioni del veicolo.
- Se targa, driver, verbale o pagamento non sono univoci, conservare il
  documento e chiedere una scelta manuale.
- Lo stato corretto dopo un pagamento privo di ricevuta ufficiale è
  `attesa quietanza`, non `attesa fattura`.
- Nessun pagamento automatico è autorizzato.

## Sicurezza

- **05/09/2026, scelta del titolare:** il PIN amministratore unico per ERP,
  Menu, Lotti e HR è quello già usato da ERP/Menu (`PIN_HASH_ADMIN` in Render).
  `app/services/admin_pin.py` è l'unica verifica; i vecchi PIN amministratore
  delle sotto-app non sono alternative. Nessuna copia o modifica degli hash
  salvati. Il modale comune è `frontend_shared/PinModal.js`, parametrizzato
  per colore. I PIN personali dei dipendenti restano distinti; non dichiarare
  completata la loro unificazione finché le identità HR/Lotti non sono verificate.

- Segreti solo nelle variabili d'ambiente/secret store di Render.
- Non stampare, committare o trasferire credenziali nei documenti.
- Non spostare né cancellare email e documenti originali.
- Eliminazioni reali, pagamenti e associazioni definitive ambigue richiedono
  conferma esplicita al momento dell'azione.

## Dominio per app: le regole che non stanno nel codice

Assorbite il 17/09/2026 dai `CLAUDE.md` dei repository originali, che ora
rimandano qui.

### HR — contratto, accessi, turni

- **CCNL applicato: Pubblici Esercizi, Ristorazione Collettiva e Commerciale e
  Turismo** (Confcommercio-FIPE), codice CNEL **H05Y**, rinnovo 5/6/2024.
  **Non è il Terziario.** 40 ore settimanali, 14 mensilità (tredicesima a
  dicembre, quattordicesima a luglio), 26 giorni di ferie, enti EBNT/EBT,
  Fondo EST per la sanità, Fon.Te. per la previdenza complementare.
- **Login dipendente = tocca il tuo nome + PIN** (decisione esplicita del
  titolare): su un dispositivo condiviso in negozio digitare il cognome ad
  ogni apertura era scomodissimo, e i nomi non sono un segreto. L'accesso
  amministratore è una voce a parte, non la scheda di un dipendente.
- Sessione lunga e persistente (7 giorni) per cucina e pasticceria: il portale
  riapre senza richiedere il PIN finché il token è valido. "Esci" chiude
  subito.
- **Turni data-driven**, un solo punto di configurazione ("Configura turni"):
  per ogni dipendente modalità sala o barista, giorno di riposo fisso, giorni
  di Lunga, onomastico, flag "può coprire il bar". Nessun nome cablato nel
  codice. La preferenza di riposo scelta dal dipendente vince sul riposo fisso
  per quella settimana.
- **Timbrature solo in sede**: geofencing sulla sede in `impostazioni`
  (Ceraldi Caffè, Piazza Carità 14, Napoli, circa 40.842949 / 14.2489, raggio
  200 metri).
- Attività: bar e pasticceria, Ceraldi Group S.r.l., titolare Vincenzo Ceraldi.

### Lotti — HACCP, magazzino, prezzi

- **Un solo punto d'ingresso per le fatture** e deduplica sempre attiva
  (fornitore + numero + data).
- **Prezzi solo da acquisti reali in fattura XML.** Gli ordini hanno totali
  veri: prezzo di riga, aliquota IVA presa dall'XML, imponibile, IVA e totale
  che si ricalcolano a ogni variazione, con le stesse colonne nel PDF.
- **FIFO consuma sempre il lotto con la data fattura più vecchia.**
- **Le bevande e gli alcolici del reparto bar (acqua, birre, vino, prosecco,
  liquori, amari, sciroppi, succhi, bibite) si acquistano e si confrontano a
  cartone o a unità, MAI a chilo o a litro**: un rum o una birra si pagano a
  bottiglia, non al chilo.
- Conversioni reali: uovo 60 g, tuorlo 19 g, albume 33 g; pezzi e chili si
  convertono con il peso del pezzo.
- Ogni riga d'ordine dice **chi l'ha inserita** (dipendente, lavagna, riordino
  automatico, produzione, colazione).
- Le righe-nota (omaggi, riferimenti) non diventano prodotti di magazzino.
  Soglia minima e quantità di riordino predefinite a 1.
- Accessi: PIN valido 2 ore; i dipendenti entrano ovunque tranne le pagine di
  amministrazione (impostazioni, PIN, personale, controllo dati, backoffice,
  configurazione, backup, stampanti). Sui tablet condivisi il magazzino chiude
  la sessione dopo 10 minuti.

### Menu — allergeni

- Gli allergeni sono un obbligo di legge, non una cortesia: **Regolamento UE
  1169/2011** e **D.Lgs. 231/2017** impongono di dichiarare i 14 allergeni
  principali per ogni prodotto. Il dettaglio prodotto per prodotto è in
  `memoria/menu/ALLERGENI_MENU.md`.
- Un prodotto nuovo creato in Lotti arriva nel Menu con le stesse immagini e
  il flag "visibile nel menu pubblico".

## Indice dei documenti di riferimento

Questo file è la memoria. Gli altri `.md` del repository sono **materiale di
consultazione o output generato**, non regole: si leggono quando servono, non
a ogni sessione.

| Documento | Cosa contiene |
| --- | --- |
| `PROMPT_MASTER.md` | Specifica normativa completa, rigenerata da `scripts/genera_prompt_master.py`. Non si modifica a mano. |
| `memoria/MAPPA_ENDPOINT_COMPLETA.md`, `memoria/endpoints/*.md` | Mappa generata di tutti gli endpoint per area. |
| `memoria/AUDIT_*.md` | Audit storici datati: fotografie di un momento, non regole correnti. |
| `docs/REGOLA_FISSA_ATTESE.md` | Regola delle attese e delle prove per i flussi che creano obblighi. |
| `memoria/lotti/`, `memoria/hr/`, `memoria/menu/` | Documenti assorbiti dai repository originali (guide, PRD, changelog storici). |

Quando uno di questi contraddice questo file, **vince questo file**: gli audit
e i changelog raccontano com'erano le cose in una certa data.

## Verifica e pubblicazione

Per ogni modifica pertinente:

1. test mirati;
2. `python -m pytest -q` quando il cambiamento backend lo richiede;
3. `yarn test` e `yarn build` in `frontend/` quando coinvolge il frontend;
4. `git diff --check`;
5. commit dei soli file pertinenti;
6. push su `main` solo quando richiesto;
7. CI verde e verifica `/api/health` sul commit pubblicato;
8. controllo live del flusso interessato senza mutare dati non autorizzati.

Un alert deve sempre mostrare l'elenco dei record coinvolti. Un comando di
manutenzione che l'utente deve ripetere per correggere duplicati prevedibili è
un difetto: la prevenzione per ID/hash deve stare nel flusso di importazione.

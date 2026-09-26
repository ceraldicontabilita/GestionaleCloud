# GestionaleCloud — memoria tecnica canonica

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-09-26
storage_architecture: supabase
-->

Aggiornato il 26/09/2026 sul codice di `main` del repository
`ceraldicontabilita/GestionaleCloud`.

Questo file descrive ciò che deve restare vero. La storia delle modifiche vive in
Git e in `PIANO_RISTRUTTURAZIONE.md`; le istruzioni di avvio stanno in `README.md`.

## Come si tiene questo file

- Nel repository sono ammessi solo `CLAUDE.md`, `README.md` e
  `PIANO_RISTRUTTURAZIONE.md`. Non creare report, diari o cartelle di memoria.
- Aggiornare sul posto le sezioni «Stato attuale» e «Aperto». Non aggiungere
  capitoli datati e rimuovere i problemi realmente chiusi.
- Il codice, i test, lo schema dati e la configurazione di produzione prevalgono
  su questo testo. Ogni modifica che cambia un'invariante aggiorna anche qui.
- Non registrare segreti, token, PIN, dati personali o credenziali.
- Prima di lavorare confrontare sempre `HEAD` con `origin/main`. Non sovrascrivere
  modifiche locali dell'utente e non usare aggiunte Git indiscriminate.

## Prodotto e confini

Un solo processo FastAPI e un solo host servono quattro applicazioni:

| Applicazione | Pagine | API | Frontend |
| --- | --- | --- | --- |
| ERP / Gestionale | `/` | `/api/*` | `frontend/` |
| HR / personale | `/hr/` | `/hr/api/*` | `frontend_hr/` |
| Lotti / HACCP | `/lotti/` | `/lotti/api/*` | `frontend_lotti/` |
| Menu digitale | `/menu/`, `/menu/admin` | `/menu/api/*` | `frontend_menu/` |

- Entrypoint: `app/main.py`. HR, Lotti e Menu sono sub-app montate prima del
  catch-all dell'ERP. I prefissi senza slash devono reindirizzare alla pagina
  corretta, mai cadere nella SPA sbagliata.
- `app/` è il backend vivo. `backend/` contiene solo le dipendenze di produzione.
- Le quattro app condividono dominio, servizio Render e archivio Supabase; non
  devono ricreare copie parallele della stessa anagrafica o dello stesso fatto.
- Produzione: `https://gestionalecloud.onrender.com`. Il dominio
  `impresasemplice.online` è un alias dello stesso servizio.

## Identità, sessioni e autorizzazioni

L'identità nasce nel Gestionale. L'amministratore effettua un solo login ERP
con MFA; HR, Lotti e Menu ottengono dal backend un token applicativo derivato
dal cookie ERP HttpOnly. Un frontend non può auto-dichiararsi amministratore.

### Visibilità delle pagine

| Area | Pubblico | Dipendente / operatore | Amministratore |
| --- | --- | --- | --- |
| ERP | solo login | funzioni assegnate al ruolo | tutte le funzioni e impostazioni |
| HR | pagina di ingresso minima | portale personale e proprie operazioni | ufficio, archivio, configurazione |
| Lotti | nessuna pagina operativa | reparto e registrazioni assegnate | dashboard, configurazione, audit |
| Menu | catalogo cliente pubblicato | nessun ruolo intermedio | editor, anteprima, pubblicazione |

- I controlli di visibilità frontend sono solo presentazione: ogni API applica
  la stessa regola lato server.
- Ogni richiesta di scrittura richiede un token valido. Non esistono whitelist
  anonime per tablet, kiosk o compatibilità storica.
- Il token non passa mai in query string, URL, log, referrer o nome file. Per
  PDF e download usare `Authorization`, risposta Blob e URL locale temporaneo.
- Il logout ERP revoca la sessione server e cancella dal browser tutte le
  credenziali derivate di ERP, HR, Lotti e Menu. La revoca coordinata server-side
  dei token derivati deve usare un identificatore di sessione comune.
- I PIN personali servono soltanto all'operatore/dipendente quando non esiste una
  sessione ERP amministrativa. Nessun secondo tastierino per l'amministratore.
- Endpoint pubblici non espongono elenchi completi di ID e nomi del personale.
  La selezione dipendente usa un identificatore non enumerabile o una ricerca
  limitata, con rate limit e risposta uniforme.
- Ruoli sconosciuti o mancanti sono sempre `non_autorizzato` (fail closed).

## Navigazione e comportamento delle app

- Ogni app collegata mostra sempre «Torna al Gestionale» in testata, anche nelle
  card Ufficio, Archivio, Pasticceria e Rosticceria.
- «Impostazioni» è una destinazione amministrativa esplicita e visibile nelle
  aree Ufficio e Archivio; non dipende da hover, schermo o URL nascosto.
- La card Pasticceria/Rosticceria apre prima una scelta chiara del reparto e poi
  una home operativa coerente. Mostra operatore, reparto, azioni primarie, stato
  delle registrazioni e uscita/cambio operatore.
- Il Menu separa nettamente pagina pubblica cliente, anteprima fedele, editor
  amministrativo e stato bozza/pubblicato con azione «Pubblica» esplicita.
- Nessun link `#`, card cliccabile solo con `div`, controllo nascosto o etichetta
  ambigua. Usare link/bottoni semantici, focus visibile, tastiera e contrasto.
- Le azioni distruttive chiedono conferma, dichiarano l'oggetto interessato e,
  quando possibile, sono reversibili.

## Dati e relazioni

- Supabase è la fonte operativa unica (`DATA_BACKEND=supabase`), con separazione
  logica per ERP, HR, Lotti e Menu. `legacy_staging` è sola lettura.
- Google Drive conserva gli originali documentali; non è un database. ID Drive,
  hash SHA-256 e origine sono prove. Nome file, importo o cartella non bastano.
- Non inventare associazioni. Un legame incerto resta `DA_VERIFICARE`; niente
  fuzzy matching che scriva dati operativi senza conferma.
- F24, quietanza, movimento bancario e documento sorgente sono evidenze distinte.
- Importazioni e sincronizzazioni sono idempotenti. Usare chiavi naturali o ID
  stabili e vincoli univoci; un retry non crea duplicati.
- Denaro: `Decimal` nel backend e `NUMERIC` nel database, mai `float` per calcoli
  contabili. Date ISO, timestamp timezone-aware in UTC, presentazione Europe/Rome.
- Evitare hard delete dei record operativi. Preferire stato, cestino o tombstone
  con autore, data e motivazione; gli originali restano immutabili.
- Ogni relazione tra entità ha una sola direzione canonica e vincoli referenziali.
  Non duplicare nome, ruolo o stato quando esiste l'ID sorgente.
- Query di massa sono paginate e limitate. Nessun `.to_list()` arbitrariamente
  enorme; i job lunghi salvano cursore, avanzamento e risultato verificabile.

## Architettura del codice

- Router: validazione HTTP e autorizzazione. Service: casi d'uso. Repository:
  persistenza. Engine: calcolo puro. Il router non replica logiche contabili.
- Una funzione o regola vive in un solo modulo canonico. Non mantenere doppioni
  tra `app/`, `app/hr/`, `app/lotti/` e `app/menu/` per comodità storica.
- I modelli di risposta delle API sono espliciti. Le mutazioni dichiarano status
  code e contratto d'errore; niente dizionari incompatibili tra app.
- Vietato `except Exception: pass` nei percorsi operativi. Gli errori sono
  classificati, registrati senza segreti e trasformati in risposte coerenti.
- Spezzare i moduli oltre circa 800 righe per responsabilità. Prima fissare il
  contratto con test, poi spostare codice senza cambiare comportamento.
- Le dipendenze sono bloccate e installabili con il gestore del lockfile. Non
  usare aggiornamenti forzati senza test di regressione.

## Regole di verifica e consegna

- «Test verde», «PR unita», «deploy avviato» e «funzione provata su dati reali»
  sono evidenze diverse e vanno dichiarate separatamente.
- Una modifica è live solo quando l'health espone esattamente il commit atteso e
  il flusso è verificato dopo refresh.
- Per dati operativi verificare UI → API → persistenza → nuovo caricamento →
  filtri/relazioni. Test sintetici non provano la persistenza reale.
- Ogni correzione di sicurezza ha un test negativo del comportamento vulnerabile
  e un test positivo del flusso autorizzato.
- CI e build coprono backend e quattro frontend. Una sessione condivisa non è
  verificata con il solo test di una singola app.
- `PIANO_RISTRUTTURAZIONE.md` registra tranche, test, commit, PR, merge e commit
  realmente servito; non anticipa prove non eseguite.

## Stato attuale (al 26/09/2026)

- `origin/main` analizzato: `b1673d6106e6115b58afcf48f93949e51df03e5c`.
- Il servizio è un monolite modulare FastAPI con quattro frontend.
- L'accesso amministratore derivato dalla sessione ERP esiste per HR, Lotti e
  Menu, ma la revoca server-side non è coordinata da una sessione comune. La
  pulizia browser condivisa è in verifica in questa tranche.
- Le scritture anonime storicamente ammesse da Lotti sono state rimosse nel ramo
  di lavoro e protette da test; non sono ancora dichiarate unite o live.
- Audit statico del ramo di partenza: 784 file Python, 157 router, 1.019 rotte,
  523 mutazioni, 1.013 rotte senza modello di risposta, 511 mutazioni senza
  status esplicito, 221 hard delete, 274 materializzazioni da almeno 10.000
  record e 117 eccezioni ignorate. Sono indicatori, non bug tutti confermati.
- I moduli più grandi superano 3.700 righe in HR, documenti, prima nota e Lotti:
  la separazione per casi d'uso non è completa.
- La suite mirata su autorizzazione Lotti e sessione unica passa; restano warning
  di deprecazione FastAPI/Python e chiavi JWT corte nei soli fixture.

## Aperto

Priorità P0/P1:

1. Eliminare il token Lotti dalle query string migrando PDF/download a header
   `Authorization` + Blob; poi rimuovere l'accettazione backend e aggiungere test.
2. Introdurre `session_id`/versione comune e revoca server-side di tutti i token
   derivati quando termina la sessione ERP.
3. Rimuovere i tastierini amministrativi legacy di Lotti, HR e Menu dopo aver
   coperto ogni ingresso con sessione ERP e test end-to-end.
4. Sostituire l'elenco pubblico HR di ID e nomi con un flusso non enumerabile.
5. Rendere verificabili «Torna al Gestionale», Impostazioni e il percorso
   Pasticceria/Rosticceria su desktop e mobile.
6. Rendere il Menu comprensibile al cliente: pagina pubblica completa, anteprima
   fedele, navigazione semantica e pubblicazione esplicita.

Priorità P2 strutturale:

7. Spezzare i moduli giganti partendo dai confini con più mutazioni e dipendenze;
   aggiungere test di contratto prima di spostare codice.
8. Tipizzare gradualmente le API: prima autenticazione, dati personali,
   documenti, pagamenti e mutazioni; dichiarare status ed errori.
9. Sostituire hard delete, query di massa ed eccezioni silenziose per tranche
   misurabili, senza migrazioni distruttive e con rollback.
10. Allineare `render.yaml`, dipendenze e commenti all'architettura effettiva:
    un solo Supabase e nessuna password amministratore legacy del Menu.

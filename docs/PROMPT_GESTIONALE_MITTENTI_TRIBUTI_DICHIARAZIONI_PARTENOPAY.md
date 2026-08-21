# Prompt strutturato per GestionaleCloud

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

```text
Implementa nel GestionaleCloud un sistema documentale e fiscale integrato per:

1. mittenti email e PEC;
2. codici tributo;
3. F24 e relative righe tributo;
4. dichiarazioni fiscali;
5. cartelle esattoriali e atti della riscossione;
6. PartenoPay, verbali e relative prove di pagamento;
7. documenti originali archiviati su Google Drive.

L’utente deve poter navigare, visualizzare, estrarre e scaricare i PDF di Drive
senza uscire dal GestionaleCloud.

============================================================
0. VERIFICA INIZIALE E REGOLE GENERALI
============================================================

Prima di modificare il codice:

- sincronizza il repository canonico `ceraldicontabilita/GestionaleCloud`;
- usa il checkout operativo `C:\Users\ceral\Documents\GESTIONALE CLOUD 2`;
- verifica branch `main`, `HEAD`, `origin/main`, stato locale e modifiche esistenti;
- preserva tutte le modifiche locali non pertinenti;
- ispeziona codice, test, registri Drive/Sheets, database, endpoint e permessi correnti;
- considera codice e dati attuali come autorità;
- riusa le pagine, i router e i servizi esistenti; non creare duplicati funzionali;
- mantieni `Documenti` come ingresso operativo dei documenti;
- usa date ISO e timezone Europe/Rome;
- conserva file originale, hash, provenienza, messaggio sorgente e cronologia;
- non associare documenti, pagamenti, driver, F24 o dichiarazioni usando il solo importo;
- lascia ogni corrispondenza ambigua come candidata non confermata.

Google Drive e i relativi indici Excel/Sheets sono l’archivio canonico dei PDF.
Il GestionaleCloud governa stati, relazioni, autorizzazioni e consultazione.
Non creare nuove copie operative in archivi legacy se il documento è già presente
su Drive.

STATO DEL REPOSITORY RILEVATO IL 2026-08-20

La specifica è stata riallineata a `origin/main` commit `24ee65777`.
Prima di implementare esegui comunque un nuovo fetch, perché questo riferimento
serve come base di audit e non sostituisce il codice corrente.

Funzioni già presenti da riusare:

- `app/services/email_monitor_service.py` contiene già esecuzioni persistenti,
  stato credenziali, contatori, coda retry e ultimo esito Gmail;
- `tests/test_gmail_monitor_reliability.py` verifica run persistenti e retry;
- `app/routers/email_download.py` e `frontend/src/pages/MittentiEmail.jsx`
  gestiscono già la collezione canonica `mittenti_email`;
- `app/services/email_full_download.py` possiede già la scansione di tutte le
  cartelle/etichette IMAP;
- `app/services/tax_code_registry.py` e `/api/documenti/tax-codes` espongono
  già il catalogo consultivo dei codici tributo;
- `app/services/declaration_registry.py`, `drive_declaration_upload.py` e
  `SituazioneFiscale.jsx` gestiscono già dichiarazioni Drive-first e candidati F24;
- `app/services/drive_document_index.py` e gli endpoint
  `/api/documenti/drive/index/*` espongono indice, F24, dichiarazioni e relazioni;
- `app/services/tax_collection_service.py` e la tab AdeR di
  `SituazioneFiscale.jsx` gestiscono già cartelle, rate e definizioni;
- `app/routers/verbali_riconciliazione.py` e i servizi `verbali_*` gestiscono
  già import PartenoPay, scan email, veicolo, driver e prove;
- `frontend/src/components/DocumentViewerModal.jsx` è il visualizzatore interno
  canonico e deve essere esteso, non sostituito.

Gap corrente da correggere:

- gli originali dell’indice Drive vengono ancora aperti con `window.open` sul
  `drive_url`, quindi l’utente esce dal Gestionale;
- `/api/documenti/drive/index/document/{document_id}` risolve metadati e link,
  ma manca un endpoint autenticato che trasmetta il contenuto Drive al viewer;
- `/api/documenti/documento/{doc_id}/download` era descritto come legacy MongoDB: deve essere Drive-first con fallback legacy controllato.
- il monitor giornaliero affidabile usa il downloader generico su `INBOX`, mentre
  la copertura di tutte le cartelle esiste in `email_full_download.py`: occorre
  unificare i due comportamenti senza creare un terzo downloader.

============================================================
1. STRUTTURA MODULARE DEI FILE
============================================================

Non concentrare tutto in un unico file e non creare servizi paralleli a quelli
esistenti. Usa questa mappa reale del repository:

BACKEND DA ESTENDERE

- mittenti e controllo giornaliero:
  `app/services/email_monitor_service.py`, `email_full_download.py`,
  `email_document_downloader.py`, `app/routers/email_download.py`;

- catalogo codici tributo:
  `app/services/tax_code_registry.py`, `app/routers/documenti.py`;

- F24 e prove:
  `app/services/f24_canonico.py`, `fascicolo_f24.py`,
  `f24_fiscal_evidence.py`, `f24_payment_evidence.py`,
  `quietanze_import.py`, `f24_bank_reconciliation.py`;

- dichiarazioni:
  `app/services/declaration_registry.py`, `drive_declaration_upload.py`,
  `drive_fiscal_registry.py`, `app/routers/documenti_fiscali.py`;

- cartelle e riscossione:
  `app/services/tax_collection_service.py`, `tax_obligation_service.py`,
  `app/routers/fiscal_control.py` e le sezioni fiscali esistenti;

- PartenoPay e verbali:
  `app/routers/verbali_riconciliazione.py`, `app/routers/pagopa.py`,
  `app/services/partenopay_archive_import.py` e servizi `verbali_*`;

- indice e contenuti Drive:
  `app/services/drive_document_index.py`, `drive_documenti_ingest.py`,
  `drive_sync_orchestrator.py`, `app/routers/documenti.py`.

Creare un nuovo servizio condiviso solo se manca davvero un confine coerente,
ad esempio `drive_document_content.py` per streaming, download ed estrazione
autenticati. Non ricreare registry e scanner già presenti.

FRONTEND DA ESTENDERE

- `frontend/src/pages/MittentiEmail.jsx`;
- `frontend/src/pages/SituazioneFiscale.jsx`;
- `frontend/src/pages/DriveDocumentIndex.jsx`;
- `frontend/src/pages/VerbaliRiconciliazione.jsx`;
- `frontend/src/pages/GestionePagoPA.jsx`;
- `frontend/src/components/DocumentViewerModal.jsx` come viewer canonico;
- componenti esistenti per prove collegate e import documentale.

Creare un nuovo pannello di fascicolo trasversale soltanto se non è possibile
estendere i pannelli di prove già esistenti.

TEST

Prevedi file di test separati per ciascun dominio e test end-to-end del fascicolo.

============================================================
2. MODELLO DOCUMENTALE COMUNE
============================================================

Ogni file indicizzato deve conservare almeno:

- `document_id` stabile;
- `drive_file_id`;
- nome originale;
- tipo MIME ed estensione;
- dimensione;
- SHA-256 o hash canonico disponibile;
- cartella/percorso Drive;
- URL o identificatore Drive;
- data del documento;
- data di acquisizione;
- Gmail message ID e thread ID, quando presenti;
- mittente, destinatario, oggetto ed etichette;
- metodo di acquisizione: Gmail, PEC, upload, Drive scan o import;
- testo estratto;
- metodo di estrazione: nativo, XML, OCR o manuale;
- confidenza dell’estrazione;
- stato di elaborazione;
- tipo documentale;
- entità e relazioni associate;
- storico delle revisioni e delle conferme;
- eventuale motivo di errore o revisione manuale.

Deduplicazione:

- stesso hash nello stesso contesto: duplicato certo;
- stesso Gmail message ID/allegato: non reimportare;
- stesso nome o stessa dimensione non bastano;
- lo stesso hash in fasi documentali diverse può essere provenienza utile;
- non eliminare automaticamente documenti originali o copie di ciclo.

============================================================
3. SEZIONE MITTENTI E ACQUISIZIONI
============================================================

Creare una pagina analitica dei mittenti email e PEC.

Per ogni mittente mostrare:

- nome normalizzato;
- indirizzi e alias;
- dominio;
- eventuale mittente reale dentro un wrapper PEC;
- categorie documentali attese;
- numero messaggi analizzati;
- numero allegati;
- ultimo controllo;
- ultimo documento ricevuto;
- documenti nuovi, elaborati, duplicati, falliti e da verificare;
- anni coperti;
- collegamenti a verbali, F24, dichiarazioni e cartelle.

Il controllo Gmail deve:

- usare `in:anywhere`;
- includere Posta in arrivo, Archivio, Spam, Cestino e tutte le etichette;
- completare tutta la paginazione;
- riconoscere alias, inoltri e wrapper PEC;
- leggere EML originali quando gli allegati PEC non sono esposti normalmente;
- gestire PDF, XML, P7M, P7S, ZIP e immagini;
- salvare provenienza e URL Gmail;
- non spostare, eliminare o modificare le email;
- essere idempotente;
- avere esecuzione giornaliera e pulsante `Controlla adesso`;
- registrare heartbeat, errori, retry e contatori.

Integrare le funzioni già presenti, senza duplicarle:

- `start_email_monitor_run`;
- `finalize_email_monitor_run`;
- `get_last_email_monitor_status`;
- `_queue_retry`;
- `_load_allowed_gmail_patterns`;
- `_build_gmail_credentials`.

Il job giornaliero deve riusare la scansione `ALL_FOLDERS` già disponibile in
`email_full_download.py` oppure estrarne una primitiva condivisa. Non basta
continuare a interrogare soltanto `INBOX`. La copertura funzionale deve essere
equivalente a `in:anywhere`: inbox, archivio/tutta la posta, spam, cestino ed
etichette disponibili, con deduplicazione per messaggio e allegato.

La coda retry già presente deve diventare realmente consumabile dal worker o
scheduler e non restare una raccolta di record mai elaborati. Aggiungere test
per retry completato, retry esaurito, recupero e assenza di duplicati.

Categorie configurabili dei mittenti:

- PartenoPay/pagoPA;
- Agenzia delle Entrate;
- Agenzia Entrate-Riscossione;
- Comune ed enti locali;
- INPS/INAIL;
- commercialista e consulenti;
- banche e PayPal;
- gestori PEC;
- altri mittenti fiscali, legali o amministrativi.

Non hardcodare il solo indirizzo email: usare regole versionate e modificabili
con indirizzo, dominio, oggetto, intestazioni PEC e tipo allegato.

============================================================
4. SEZIONE CODICI TRIBUTO
============================================================

Mantenere distinti:

1. catalogo ufficiale consultivo dei codici tributo;
2. utilizzi reali del codice nelle righe F24;
3. relazioni candidate o confermate con dichiarazioni e cartelle.

Per ogni codice tributo mostrare:

- codice come stringa, senza conversione numerica;
- descrizione ufficiale;
- modello: F24, F23 o altro;
- sezione del modello;
- tipo d’imposta;
- contesto d’uso;
- ente e fonte;
- data di validità/aggiornamento della fonte;
- anni e periodi in cui è stato usato;
- totale debiti e crediti per anno;
- righe F24 collegate;
- dichiarazioni compatibili;
- cartelle esattoriali che lo richiamano;
- PDF di origine e relativo hash;
- stato della relazione: candidata, confermata o respinta.

La pagina deve permettere:

- ricerca per codice e descrizione;
- filtri per modello, imposta, sezione e contesto;
- apertura della riga F24;
- apertura del PDF F24 nel viewer interno;
- passaggio alla dichiarazione collegata;
- passaggio alla cartella collegata;
- vista `codice tributo -> F24 -> PDF`;
- vista inversa `PDF -> righe tributo`.

Il catalogo è consultivo: una ricerca nel catalogo non deve creare F24,
pagamenti o registrazioni contabili.

============================================================
5. SEZIONE F24
============================================================

`f24_unificato` o il modello canonico corrente rappresenta il modello F24.
La quietanza è una prova documentale distinta e il movimento bancario è una
prova ulteriore distinta.

Per ogni F24 mostrare:

- identificatore canonico;
- modello e tipo;
- contribuente;
- codice fiscale;
- data e protocollo;
- periodo e anno;
- totale debiti;
- totale crediti;
- saldo;
- righe tributo normalizzate;
- PDF modello su Drive;
- quietanze associate;
- movimento bancario eventualmente verificato;
- dichiarazioni candidate e confermate;
- cartelle eventualmente collegate;
- provenienza e stato di verifica.

Ogni riga tributo deve contenere:

- sezione;
- codice tributo;
- causale;
- rateazione/regione/provincia quando applicabile;
- periodo o anno di riferimento;
- debito;
- credito;
- identificatore del PDF;
- pagina o posizione, se disponibile;
- hash e provenienza.

Controlli:

- totale delle righe coerente con il documento;
- codice tributo valido o esplicitamente non riconosciuto;
- periodo compatibile con la dichiarazione candidata;
- crediti non duplicati;
- quietanza non usata per sintetizzare un F24 mancante;
- pagamento non marcato bancariamente verificato senza movimento compatibile.

============================================================
6. SEZIONE DICHIARAZIONI
============================================================

Usare Drive e l’indice fiscale corrente come archivio canonico.

Tipologie minime:

- Redditi SC;
- dichiarazione IVA;
- LIPE;
- IRAP;
- modello 770;
- elenco percipienti;
- altre dichiarazioni configurabili.

Per ogni dichiarazione mostrare:

- tipo;
- anno fiscale e anno di presentazione;
- contribuente;
- protocollo e data invio;
- eventuali moduli o protocolli multipli;
- stato: bozza, presentata, ricevuta, da verificare o altro stato esistente;
- PDF completo su Drive;
- ricevute e allegati;
- F24 candidati e confermati;
- codici tributo interessati;
- quietanze documentali;
- movimenti bancari distinti;
- cartelle esattoriali collegate;
- anomalie e documenti mancanti.

Collegamenti dichiarazione-F24:

- usare tipo d’imposta, codice tributo, periodo, anno, importi e provenienza;
- supportare più F24 per una dichiarazione;
- supportare più protocolli o moduli legittimi;
- non confermare per solo anno o solo importo;
- salvare sempre relazione reciproca;
- mantenere i candidati ambigui come non confermati.

Vista annuale:

- dichiarazioni attese;
- dichiarazioni presenti;
- PDF disponibili;
- F24 collegati;
- quietanze presenti;
- verifica bancaria;
- cartelle collegate;
- lacune documentali.

============================================================
7. SEZIONE CARTELLE ESATTORIALI
============================================================

Creare una sezione dedicata alle cartelle, intimazioni, avvisi e atti della
riscossione, senza confonderli con dichiarazioni o prove di pagamento.

Per ogni pratica mostrare:

- identificatore stabile;
- tipo atto;
- numero cartella/atto;
- ente creditore e agente della riscossione;
- contribuente;
- data emissione e notifica;
- protocollo;
- importo originario;
- interessi, sanzioni, aggio e spese separati quando disponibili;
- importo residuo;
- annualità e periodi contestati;
- codici tributo o causali;
- rateazione e relative scadenze;
- stato: ricevuta, da verificare, rateizzata, sospesa, impugnata, pagata,
  annullata o altro stato corrente;
- PEC e mittenti di provenienza;
- PDF e allegati su Drive;
- dichiarazioni e F24 candidati/confermati;
- pagamenti documentali;
- movimenti bancari verificati distinti;
- note e audit.

Relazioni:

- cartella -> annualità -> codice tributo;
- cartella -> dichiarazione;
- cartella -> F24 già pagato;
- cartella -> quietanza;
- cartella -> PEC/notifica;
- cartella -> pagamento/rata;
- cartella -> movimento bancario.

Non concludere automaticamente che una cartella sia dovuta, pagata o duplicata.
Mostrare le evidenze e lasciare le conclusioni controverse in revisione.

============================================================
8. SEZIONE PARTENOPAY E VERBALI
============================================================

Per ogni codice avviso/verbale mostrare:

- codice avviso e IUV come stringhe;
- numero verbale;
- targa;
- data e ora infrazione;
- data avviso e notifica;
- ente;
- causale;
- importo;
- scadenza normativa estratta;
- promemoria operativo entro cinque giorni dalla scoperta;
- veicolo associato;
- driver associato o candidati;
- PDF avviso su Drive;
- email di pagamento eseguito;
- ricevuta PartenoPay;
- ricevuta PayPal;
- ricevuta di bonifico;
- movimento bancario verificato;
- stato e cronologia.

Associazione veicolo/driver:

- targa normalizzata;
- data e ora dell’infrazione;
- storico temporale delle assegnazioni;
- turni o altre fonti disponibili;
- mai solo importo;
- se ambiguo mostrare `Scegli driver` e non confermare automaticamente.

Prove di pagamento distinte:

- pagamento dichiarato;
- email PartenoPay;
- quietanza/ricevuta PartenoPay;
- ricevuta PayPal;
- disposizione/ricevuta bonifico;
- movimento bancario verificato.

Il controllo giornaliero deve cercare nuove prove fino alla chiusura completa.
Se una ricevuta è ambigua, mostrare `Scegli verbale`.

============================================================
9. RELAZIONI BIDIREZIONALI E FASCICOLO UNICO
============================================================

Implementare un registro relazioni generico con:

- `source_type` e `source_id`;
- `target_type` e `target_id`;
- tipo relazione;
- metodo di matching;
- confidenza;
- stato: candidata, confermata, respinta;
- autore/processo;
- data creazione e conferma;
- motivazione;
- evidenze utilizzate;
- audit delle modifiche.

Ogni collegamento deve essere visibile in entrambe le direzioni.

Esempi:

- dichiarazione -> F24 e F24 -> dichiarazione;
- F24 -> codice tributo e codice tributo -> F24;
- cartella -> F24 e F24 -> cartella;
- verbale -> driver e driver -> verbale;
- documento -> pratica e pratica -> documento;
- quietanza -> pagamento e pagamento -> quietanza.

Creare un `Fascicolo fiscale e amministrativo` che, partendo da un soggetto,
un anno, un codice tributo, una targa o un documento, mostri tutte le entità
collegate senza perdere il tipo e la provenienza di ciascuna prova.

============================================================
10. VISUALIZZAZIONE DRIVE SENZA USCIRE DAL GESTIONALE
============================================================

Estendere il componente canonico già presente
`frontend/src/components/DocumentViewerModal.jsx`.

Funzioni:

- apertura in modal, drawer o pagina interna;
- visualizzazione PDF incorporata;
- zoom, rotazione, cambio pagina e ricerca nel testo;
- anteprima immagini e testo/XML leggibile;
- download tramite il Gestionale;
- estrazione testo e dati strutturati;
- confronto fra documento originale e dati estratti;
- elenco relazioni del documento;
- apertura del fascicolo collegato;
- copia dell’identificatore e dell’hash;
- gestione file cifrato, corrotto o senza permessi.

Il browser non deve navigare direttamente fuori dal Gestionale.

Integrare l’indice Drive già presente con un gateway backend autenticato,
equivalente a:

- `GET /api/documenti/drive/index/document/{document_id}` già esistente per metadati;
- `GET /api/documenti/drive/index/document/{document_id}/content` da aggiungere;
- `GET /api/documenti/drive/index/document/{document_id}/download` da aggiungere;
- `POST /api/documenti/drive/index/document/{document_id}/extract` da aggiungere.

I nomi finali devono rispettare le convenzioni correnti del repository.

Il gateway deve:

- verificare autorizzazione utente;
- recuperare il file con credenziali server protette;
- non esporre token o credenziali Drive;
- supportare streaming e range request necessari al viewer PDF;
- impostare MIME type e filename corretti;
- impedire path traversal e ID non validi;
- registrare accesso, estrazione e download;
- gestire file mancanti e permessi insufficienti;
- non rendere pubblico il file;
- non creare duplicati permanenti per la sola anteprima.

Il backend deve risolvere internamente `document_id -> drive_file_id` usando
`drive_document_index.get_document`, quindi leggere i byte tramite Drive. Il
frontend non deve inviare direttamente un `drive_file_id` arbitrario.

Sostituire in `SituazioneFiscale.jsx` e `DriveDocumentIndex.jsx` i percorsi che
usano `window.open(drive_url, ...)` con `DocumentViewerModal` e `fetchUrl`
autenticato. Anche `openDocument`, che oggi apre un blob in una nuova scheda,
deve usare lo stesso viewer canonico.

Rendere `/api/documenti/documento/{doc_id}/download` coerente con l’architettura
Drive-first: prima risolvere il documento canonico Drive, poi usare un fallback
legacy esplicito quando i byte esistono soltanto nello storico. Non chiedere una
nuova migrazione Drive/Sheets come unica soluzione per un file già presente su Drive.

Il pulsante `Apri su Drive` può esistere come azione secondaria, ma l’azione
principale deve essere `Visualizza nel Gestionale`.

============================================================
11. RICERCA E NAVIGAZIONE
============================================================

Creare una ricerca trasversale per:

- mittente e indirizzo;
- codice fiscale/P.IVA;
- codice tributo;
- codice avviso/IUV;
- numero verbale;
- targa e driver;
- protocollo dichiarazione;
- numero cartella;
- anno e periodo;
- importo;
- nome documento;
- hash;
- testo estratto.

Risultati raggruppati per sezione con azioni:

- `Apri fascicolo`;
- `Visualizza PDF`;
- `Scarica`;
- `Vedi relazioni`;
- `Estrai dati`;
- `Conferma relazione` solo per utenti autorizzati;
- `Scegli candidato` nei casi ambigui.

============================================================
12. STATI, QUALITÀ E ANOMALIE
============================================================

Mostrare chiaramente:

- dato estratto;
- dato confermato;
- dato inferito;
- relazione candidata;
- relazione confermata;
- OCR a bassa confidenza;
- file mancante;
- permesso Drive mancante;
- duplicato esatto;
- documento non classificato;
- prova documentale senza verifica bancaria.

Dashboard minime:

- documenti da elaborare;
- errori di estrazione;
- permessi Drive mancanti;
- F24 senza quietanza;
- quietanze senza F24;
- dichiarazioni senza PDF;
- dichiarazioni senza F24 compatibili;
- cartelle da verificare;
- cartelle con possibili pagamenti pregressi;
- verbali senza driver;
- verbali da pagare entro cinque giorni;
- pagamenti senza ricevuta completa;
- relazioni ambigue;
- job giornalieri falliti o in ritardo.

============================================================
13. TEST OBBLIGATORI
============================================================

Testare almeno:

- alias e wrapper PEC dello stesso mittente;
- paginazione Gmail completa;
- stessa email acquisita più volte;
- allegati PEC annidati;
- deduplicazione per hash;
- codici numerici lunghi conservati come testo;
- catalogo tributi che non crea movimenti;
- riga F24 collegata al PDF corretto;
- F24 e quietanza mantenuti distinti;
- movimento bancario distinto dalla ricevuta;
- dichiarazione con più protocolli o moduli;
- più F24 per la stessa dichiarazione;
- cartella con più annualità e tributi;
- cartella candidata a un F24 già pagato ma non confermata automaticamente;
- verbali con stesso importo ma codici e targhe differenti;
- cambio driver durante la giornata;
- PDF Drive visualizzato dentro il Gestionale;
- streaming parziale/range del PDF;
- download con filename e MIME corretti;
- file Drive senza permesso;
- file cifrato o OCR insufficiente;
- relazione visibile in entrambe le direzioni;
- nessun token Drive esposto al frontend;
- nessun collegamento automatico basato sul solo importo;
- timezone Europe/Rome;
- audit e autorizzazioni.

Mantenere e ampliare `tests/test_gmail_monitor_reliability.py`; non sostituirlo.
Verificare inoltre i test già presenti per `SituazioneFiscale`,
`DriveDocumentIndex`, `DocumentViewerModal`, `GestionePagoPA` e
`VerbaliRiconciliazione`.

Eseguire test backend, frontend, build, test E2E e verifica servita via HTTP.
Un semplice HTTP 200 non è prova funzionale sufficiente.

============================================================
14. CONSEGNA E PUBBLICAZIONE
============================================================

Consegnare:

- analisi del codice corrente;
- mappa dei file riusati, creati e modificati;
- modello delle entità e delle relazioni;
- migrazioni o registri aggiunti;
- schermate e navigazione;
- risultati dei test;
- esempi reali anonimizzati dei fascicoli;
- elenco delle relazioni automatiche e ambigue;
- verifica del viewer PDF Drive interno;
- log del controllo giornaliero;
- piano di rollback.

Dopo test superati, procedi autonomamente con commit, push, merge e deploy delle
sole modifiche pertinenti e verifica `HEAD == origin/main` e versione realmente
distribuita.

Non eseguire pagamenti automatici.
Non eliminare o spostare email e documenti originali.
Non confermare automaticamente associazioni ambigue.
Fermati solo per errore bloccante, rischio concreto di perdita dati o credenziali
mancanti.
```

# PROMPT MASTER — GestionaleCloud / Ceraldi ERP

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

> Questa è l'unica specifica normativa e atomica del progetto. Codice, test e
> configurazione live verificata prevalgono soltanto quando provano uno stato
> più recente; ogni divergenza deve aggiornare questo file nello stesso commit.

## 1. Mandato e identità

Costruire e mantenere **GestionaleCloud / Ceraldi ERP**, repository canonico
`https://github.com/ceraldicontabilita/GestionaleCloud`, produzione
`https://impresasemplice.online`, branch operativo `main`. Il prodotto serve
Ceraldi Group S.r.l. e unifica documenti, fatture, fornitori, Prima Nota,
riconciliazioni, fiscalità, personale, flotta, verbali e controlli.

Non usare vecchi repository, checkout, ZIP, audit o report come autorità. Non
reintrodurre nomi storici o repository privati non canonici. Non duplicare una
funzione per conservare compatibilità non provata: una regola, un servizio, un
router e un record canonico per ciascun concetto.

## 2. Obiettivo operativo

L'utente deve vedere dati aggiornati e interconnessi, non plance tecniche. Gli
ingest e le riconciliazioni sicure avvengono automaticamente. L'intervento
manuale esiste solo per dati realmente ambigui, correzioni autorizzate e azioni
irreversibili. Ogni contatore o alert apre la lista esatta che lo compone.

Il sistema è completato solo quando il flusso funziona end-to-end in produzione:
documento originale → entità → pagamento → banca → Prima Nota → prova →
navigazione inversa. HTTP 200, pagina visibile, build o test statico da soli non
provano il funzionamento.

## 3. Principi atomici

1. Una sola fonte autorevole per ogni fatto.
2. Una sola identità canonica per entità e un solo `operation_id` per evento.
3. Una sola pipeline di ingest per canale, condivisa da manuale e scheduler.
4. Una sola regola contabile nel dominio, mai duplicata nei router o in React.
5. Una sola scrittura per operazione: upsert idempotente prima di ogni side effect.
6. Ogni mutazione è transazionale quanto possibile, auditata e ripetibile.
7. Nessun dato senza fonte, hash, timestamp, versione parser e stato.
8. Nessun record orfano, saldo hardcoded, fixture o snapshot servito come live.
9. Nessun endpoint, pagina, componente, job o variabile senza consumer e test.
10. Le associazioni automatiche richiedono prova deterministica; altrimenti proposta.

### 3.1 Motore obbligatorio delle attese

Applicare sempre `docs/REGOLA_FISSA_ATTESE.md`. Quando entra un fatto validato,
il suo owner crea immediatamente tutti gli obblighi e le attese conseguenti.
Le evidenze future non generano l'attesa che dovrebbero provare: la soddisfano
oppure la lasciano `DA_VERIFICARE`.

Stati aperti: `ATTESO`, `DA_VERIFICARE`, `IN_ELABORAZIONE`, `ERRORE`. Stati
terminali positivi: `SODDISFATTO`, `NON_APPLICABILE`, `SUPERATO`. Il processo
si chiude solo quando tutte le attese obbligatorie sono terminali positive.
Ogni attesa conserva owner, fatto sorgente, `operation_id` ed evidenze, con
navigazione bidirezionale.

## 4. Autorità e fonti

Ordine di verità:

1. originali immutabili in Google Drive e identificatori dei sistemi esterni;
2. registri strutturati nel workbook Drive/Sheets canonico;
3. codice e test del `main` canonico;
4. configurazione effettivamente attiva in Render e job scheduler;
5. `page_catalog.json`, OpenAPI e mappe generate dal codice;
6. questo PROMPT MASTER per regole, vincoli, divieti e criteri di accettazione.

Email, allegato, fattura, disposizione, ricevuta, quietanza, transazione provider,
movimento bancario e scrittura contabile sono prove distinte. Possono condividere
`operation_id`, ma non devono essere fuse o sovrascritte.

## 5. Architettura dati Drive-only

La destinazione definitiva usa **Google Drive per gli originali** e **Google
Sheets/Excel collegato a Drive per registri, progressivi, indici e relazioni**.
Il runtime usa esclusivamente Drive/Sheets. Non esistono backend alternativi,
fallback legacy o variabili di configurazione per archivi diversi.

Workbook: `Ceraldi ERP - Registro dati`.

Albero minimo sotto la radice configurata:

```text
RADICE GESTIONALECLOUD/
├── REGISTRO DATI/       workbook, schema, manifest e report di ricostruzione
├── PARTENOPAY/          email, verbali, avvisi, ricevute e indici
├── CODICI TRIBUTO/      registri e collegamenti codice → F24 → PDF
├── QUIETANZE/           quietanze e prove documentali
└── DICHIARAZIONI/       IVA, Redditi, 770, ISA e altri originali fiscali
```

Le sottocartelle di dominio esistenti possono essere indicizzate senza spostare
gli originali. Nessun job rinomina, sposta, cestina o elimina originali senza
autorizzazione esplicita. Credenziali e ID sensibili non entrano nei documenti.

Ogni foglio ha almeno:

`progressivo, canonical_id, operation_id, data, anno, tipo, importo, valuta,
descrizione, stato, documento_id, fattura_id, movimento_bancario_id, source,
source_external_id, file_hash, parser_version, created_at, updated_at,
payload_schema_version, payload_json`.

- `progressivo`: assegnato una volta per foglio, stabile, mai riciclato;
- `canonical_id`: identità deterministica e univoca dell'entità;
- `operation_id`: UUID/ULID condiviso dalle prove dello stesso evento;
- `file_hash`: SHA-256 dell'originale, mai MD5 per decisioni nuove;
- `source`: canale e identificatore esterno;
- importi: `Decimal`, valuta esplicita, mai float;
- date backend: ISO-8601 con timezone; UI italiana `gg/mm/aaaa`.

Il payload completo è JSON versionato e ricostruibile; i campi di ricerca sono
colonne tipizzate. Payload grandi sono compressi/chunked senza perdere dati.

## 6. Identità, deduplicazione e relazioni

Prima di scrivere: normalizza → calcola hash/chiave → cerca record e sorgente →
confronta payload → crea o aggiorna. Il secondo ingest della stessa fonte deve
produrre `nuovi=0` e zero nuove scritture contabili.

Una corrispondenza certa richiede importo esatto al centesimo quando pertinente,
segno e valuta, più identità/provenienza/riferimento compatibile. L'importo da
solo non è mai prova. Più candidati significa `proposed`: mostra `Scegli
fattura`, `Scegli driver`, `Scegli verbale` o equivalente, con motivazione.

Il registro relazioni conserva `relation_id`, `operation_id`, entità sorgente e
destinazione, tipo relazione, regola, confidenza, stato, creatore/validatore e
timestamp. Navigazione obbligatoriamente bidirezionale.

## 7. Gmail e posta elettronica

Gmail/IMAP acquisisce F24, quietanze, cedolini, verbali, ricevute e altri
documenti autorizzati. Le fatture elettroniche italiane provengono dal canale
Drive/SDI; una fattura italiana per email è un'anomalia da conservare, non una
seconda fonte canonica.

Regole Gmail:

- ricerca esaustiva con `in:anywhere`, incluse etichette, archivio, spam/cestino
  solo in lettura quando richiesto dal mandato;
- paginazione fino a esaurimento, mai solo la prima pagina;
- normalizzazione mittenti, alias, PEC e wrapper di consegna;
- conservazione di Gmail message ID, thread ID, internal date, RFC Message-ID,
  mittente/destinatari, oggetto, label, query, raw EML quando autorizzato,
  allegati, MIME type, dimensione e SHA-256;
- deduplica fra Gmail, Drive e upload con provenienze multiple conservate;
- fuso scheduler `Europe/Rome`; watermark e lock distribuito;
- job giornalieri idempotenti con conteggi letti/nuovi/aggiornati/invariati/
  ambigui/errori e ultimo cursore;
- i mittenti attendibili sono configurati e auditati, mai dedotti per sempre da
  un solo messaggio;
- non marcare letto, non spostare, non etichettare, non cancellare e non
  rispondere automaticamente salvo mandato specifico;
- errori di parsing conservano email e allegato e generano una coda visibile.

PartenoPay: conserva email, verbale, avviso, ricevuta PagoPA/PayPal e movimento
banca come evidenze diverse. Matching driver = targa normalizzata + data/ora
infrazione + storico assegnazioni. Intestazione alla società non identifica il
driver. Job giornaliero, alert entro cinque giorni e nessun pagamento automatico.

## 8. Drive e documenti

Ogni Drive file conserva file ID, parent ID/percorso osservato, nome, MIME,
dimensione, modifiedTime, MD5 fornito da Drive se presente, SHA-256 calcolato,
permessi osservabili, webViewLink e tutte le occorrenze duplicate. L'hash uguale
non autorizza la perdita di provenienza.

Pipeline unica: acquisisci senza distruggere → inventaria → valida MIME/ZIP →
calcola hash → classifica → estrae → valida campi → upsert → collega → verifica.
Un upload reale non può terminare “analizzato senza salvare”. Gli ZIP sono
protetti da traversal, bomb, estensioni vietate e limiti di dimensione.

Pulizia Drive: solo copie esatte, hash forte/MD5 Drive coerente, permesso
`canTrash`, anteprima completa e autorizzazione. Usare Cestino, mai eliminazione
permanente. Nessuna pulizia è completa senza verifica owner-side e stato finale.

## 9. Fatture e fornitori

Fattura unica per identità fiscale emittente, numero normalizzato, data,
tipo/SDI e hash. PDF/XML e metadati restano collegati. Lo stato pagamento deriva
da prove e allocazioni; pagamenti parziali e misti hanno righe esplicite.

Spostare una fattura fra Cassa e Banca modifica metodo/relazioni e scritture con
lo stesso ID: non crea una seconda fattura. Il fornitore è univoco per P.IVA/CF
normalizzato; merge conserva alias, IBAN, documenti e audit.

Regole SDD configurabili associano descrizioni come FASTWEB o WORLDPAY a un
fornitore, ma la regola produce automaticamente un pagamento solo con identità,
periodo e importo compatibili. Il dubbio mostra candidati.

## 10. Prima Nota, Cassa e Banca

Motore unico `scritture_contabili`: nessun router o import scrive direttamente
scritture parallele. Ogni operazione genera movimenti bilanciati, idempotenti e
collegati alla fonte.

La UI raggruppa tutte le operazioni in card giornaliere con numero, totale e
saldo progressivo verificabile. Cassa, Banca, SumUp e Soci sono sezioni dello
stesso modello, non database indipendenti.

Versamento contanti: uscita Cassa + entrata attesa Banca con stesso
`operation_id`; la riga estratto conto riconcilia l'attesa. Un versamento
manuale in Cassa crea subito l'entrata attesa in Banca. Nessun doppio ricavo.

L'estratto conto crea una riga bancaria canonica per riferimento esterno o
fingerprint data/valuta/importo/causale/numero progressivo. Reimportare lo stesso
estratto non duplica. Prima Nota Banca non è una copia cieca dell'estratto:
registra solo eventi con causale contabile nota o categorie bancarie ammesse.

Assegni con importo ricorrente non sono duplicati se numero/data differiscono.
Bonifici conservano CRO/TRN, ordinante, beneficiario, descrizione e periodo.
Finanziamenti soci richiedono identità movimento, non il solo importo.

## 11. Corrispettivi, POS, SumUp e Numia

Il ricavo nasce dal corrispettivo RT. Vendita POS, chiusura terminale, credito
gestore, commissione e accredito bancario sono fatti distinti.

Per ogni giorno: corrispettivo → quota contanti in Cassa e quota POS come
credito gestore; payout → chiusura del credito; commissione separata. Il giorno
di vendita non viene sostituito dalla data di accredito. SumUp e Numia restano
circuiti separati. Giorni mancanti, importi discordanti e payout multi-giorno
generano liste esplicite.

Le fonti owner sono distinte: SumUp corrente arriva automaticamente dall'API;
Numia corrente viene inserito manualmente ogni sera dalla chiusura dei
terminali; Numia storico viene ricostruito dagli export operativi CSV/XLSX su
Drive, deduplicati per ID transazione e accorpati per giorno vendita. Ciascun
totale giornaliero crea subito il credito/accredito atteso del proprio gestore.
L'estratto conto bancario non crea mai il fatto POS: raggruppa `NUMIA-AMEX`,
`NUMIA-INTER`, `NUMIA-BNCMT`
e `NUMIA-PGBNT` per il giorno `DEL gg/mm/aa`, somma al centesimo e soddisfa
l'attesa esistente. Senza un'unica attesa resta `DA_VERIFICARE`: la banca non
può creare retroattivamente la chiusura POS.

## 12. PayPal, PagoPA, bonifici e assegni

PayPal collega transaction ID, controparte, email, valuta, importo, data,
fattura, addebito/accredito banca e Prima Nota tramite `operation_id`. La logica
vale per tutti i movimenti, non per singoli esempi. Conversioni valuta e fee
sono righe distinte.

PagoPA collega IUV, ente, avviso, ricevuta, verbale/F24 quando pertinente e
movimento bancario. Ricevuta provider e prova bancaria hanno stati distinti.

## 13. F24, tributi e dichiarazioni

F24 PDF, delega, righe tributo, credito, quietanza e movimento bancario sono
entità separate. Indicizzazione bidirezionale: codice tributo → periodo → F24 →
PDF → quietanza → banca; PDF → tutte le righe. Filtri per anno, periodo, codice,
sezione, stato quietanza e riconciliazione.

`pagato` richiede evidenza coerente. In assenza della prova documentale usare
`attesa quietanza`; in assenza del movimento usare uno stato banca distinto.
Non usare `attesa fattura` per verbali o pagamenti che non generano fattura.

Dichiarazioni IVA, Redditi, 770 e ISA restano originali Drive collegati a
periodi, F24 e indici; non inferire valori fiscali mancanti.

## 14. Personale, cedolini e ritenute

Cedolino, dipendente, periodo, bonifico, acconto, trattenuta e Prima Nota sono
collegati. Il periodo selezionato è persistente. Bonifico prima del 25 suggerisce
il mese precedente; dal 25 può riferirsi al mese corrente anche se il cedolino
arriverà a fine mese. Nome/CF/IBAN e causale confermano; importo diverso è
possibile per acconti/trattenute e richiede allocazione.

## 15. Noleggio, veicoli, driver e verbali

Le fatture noleggiatore alimentano automaticamente targa, fornitore, marca,
modello, contratto, canoni e periodo. Le schede incomplete non compaiono nel
flusso normale: vanno in coda di qualità. Le assegnazioni driver hanno intervallo
temporale; il driver del verbale è quello attivo alla data/ora del fatto.

L'importo del verbale viene dal PDF/avviso e deve superare controlli OCR; mai
derivarlo dal numero. Il PDF verbale è sempre associabile manualmente. Stati:
`documento salvato`, `da verificare`, `attesa pagamento`, `attesa quietanza`,
`pagato documentale`, `riconciliato banca`.

## 16. Contabilità, bilancio e controlli

Piano conti CEE ufficiale, registrazioni Dare/Avere bilanciate, libro giornale
progressivo, bilancio derivato, IVA per periodo, cespiti, mutui, budget e
chiusura. Ogni totale ha formula e drill-down. Simulazioni non scrivono sul
consuntivo. Chiusura esercizio richiede checklist, anteprima, conferma forte,
audit e rollback.

### 16.1 Tracciabilità alimentare e HACCP

La tracciabilità alimentare NON è un modulo nativo del gestionale: dal
03/09/2026 (ordine del titolare, regola «un solo sistema per funzione»)
l'area `/tracciabilita`, il router `/api/haccp` e i fogli `haccp_*` sono
stati rimossi. Ricezioni, lotti, registri, ricette, produzioni e
attrezzature vivono nell'app Lotti originale montata pari pari a
`/lotti` (login e archivio propri). Il gestionale le fornisce soltanto
il feed fatture `/api/integrations/lotti/*`; fatture, fornitori, prodotti,
corrispettivi e ordini restano le entità canoniche di GestionaleCloud.
Allo stesso modo la pagina «Cedolini paga» (`/salari`) è stata sostituita
dall'app HR (AppDipendenti) montata a `/hr`: nel gestionale restano solo
l'ingestione cedolini, la Prima Nota salari e la riconciliazione stipendi.

## 17. UX e accessibilità

Navigazione per moduli, anno globale coerente, layout semplice. Stati loading,
vuoto, dati, parziale, errore e retry per ogni pagina. Filtri persistono in URL
quando condivisibili. Tabelle responsive, importi allineati, date italiane,
focus visibile, tastiera, contrasto e semantic HTML.

Modali sopra ogni overlay, focus trap, `Esc`, pulsante Chiudi e click esterno
solo se non perde dati. Aprire “Vedi fattura” non deve lasciare la finestra sotto
un'altra. Azioni distruttive indicano oggetto, impatto, recuperabilità e audit.

## 18. Alert, automazioni e agenti

Ogni alert contiene query riproducibile, elenco record, motivazione, severità,
fonte e azione. I falsi positivi si correggono nella regola. Le automazioni
hanno lock distribuito, idempotency key, watermark, retry limitato, dead-letter,
metriche e ultimo esito. Nessun job parte in ogni worker web.

Agenti AI operano in sola lettura o proposta per default. Nessuna associazione
ambigua, pagamento, cancellazione, movimento di originali o modifica esterna è
eseguita senza autorizzazione esplicita e controllo deterministico.

## 19. Sicurezza e privacy

RBAC per pagina/endpoint, MFA admin, password hash forte, sessioni scadenti,
CSRF dove applicabile, CORS esplicito, rate limit, validazione input/upload,
protezione ZIP, query parametrizzate, log strutturati senza segreti o dati
integrali non necessari. Segreti solo in secret store Render/locale non
versionato; mai `.env`, token, password, PIN, service-account JSON o URL con
credenziali nel repository, nei fogli o nei log.

Ogni mutazione registra attore, correlation ID, sorgente, prima/dopo, timestamp
UTC e risultato. L'utente può accedere solo ai dati del ruolo autorizzato.

## 20. Divieti assoluti

- pagamenti automatici;
- associazioni definitive ambigue;
- cancellazione o spostamento automatico di email/documenti originali;
- eliminazione permanente Drive; usare Cestino solo con autorizzazione;
- matching per solo importo;
- float per denaro;
- dati demo/hardcoded/fallback storico in produzione;
- route, endpoint, job, pagina, componente o variabile senza consumer/test;
- doppia pipeline Gmail/Drive o doppio motore Prima Nota;
- scritture contabili dirette fuori dal motore unico;
- segreti nel codice, documentazione, log o workbook;
- dichiarare collaudato con solo HTTP 200, build o test statico;
- eliminare il backend transitorio prima di ricostruzione e cutover verificati.

## 21. API, errori e compatibilità

FastAPI modulare, schemi request/response tipizzati, errori con `code`, `message`,
`details`, `correlation_id`, paginazione e limiti. Autorizzazione nel backend.
L'OpenAPI generato dal codice è il contratto tecnico. Gli endpoint senza FE,
scheduler, integrazione, MCP o test restano in quarantena e non si ricreano.

Alias legacy: misurare gli accessi, reindirizzare al canonico senza duplicare
logica e rimuovere dopo zero consumer. Nessuna risposta finta per conservare un
endpoint morto.

## 22. Configurazione e variabili

Tutte le variabili riconosciute dal codice sono elencate nell'appendice generata.
I valori sensibili non sono mai stampati. Ogni variabile nuova richiede
descrizione, tipo, default sicuro,
ambiente, proprietario, rotazione se segreta, test startup e rimozione quando
non ha più consumer.

## 23. Test e gate

Per ogni pagina: accesso, deep-link/refresh, loading/vuoto/dati/parziale/errore,
filtri, importi/date, modali, responsive, relazioni, alert, idempotenza e audit.

Per ogni ingest: prima esecuzione, seconda identica, duplicato cross-canale,
formato invalido, interruzione, retry e concorrenza. Per ogni riconciliazione:
caso certo, nessun candidato, più candidati, parziale, storno e navigazione
inversa. Test monetari al centesimo.

Gate release: lint, unit, integration, contract, build, E2E isolato, scansione
segreti, zero riferimenti obsoleti, migrazioni idempotenti, backup/rollback,
CI verde, commit servito in `/api/health`, controllo live di dati e job.

Gate Drive-only: tutti i fogli presenti e versionati; conteggi, digest, somme e
relazioni equivalenti; scrittura/lettura riuscite; ricostruzione completa da
Drive in ambiente isolato; rollback provato; nessun backend alternativo attivo.

## 24. Procedura di sviluppo e pubblicazione

Sincronizza `origin/main`; lavora in branch/worktree pulito; preserva modifiche
locali altrui; modifica una funzione atomica; aggiungi solo file pertinenti;
esegui test mirati e suite; controlla diff/segreti; commit descrittivo; push/PR;
CI; merge autorizzato; deploy; verifica live e rollback se i gate falliscono.

## 25. Criterio finale “nessun dato morto”

Un dato esiste solo se ha fonte, identità, schema, consumer, stato e percorso di
ricostruzione. Un file/codice esiste solo se importato o invocato, coperto da
test e necessario a una route/job/integratore attivo. Audit datati e vecchi
porting non restano nel repository: Git conserva la storia. Le mappe generate
si rigenerano dal codice e non si correggono a mano.

## Appendice A — Tutte le 64 pagine

1. **Login** — `/login` — accesso `public` — modulo `accesso` — Login sicuro, sessione, MFA e redirect alla destinazione autorizzata. Fonte UI: `frontend/src/pages/Login.jsx`; mappa: `memoria/pagine/login.json`.
2. **Gestione riservata** — `/gestione-riservata` — accesso `reserved` — modulo `accesso` — Area riservata separata, con accesso dedicato e movimenti auditabili. Fonte UI: `frontend/src/pages/GestioneRiservata.jsx`; mappa: `memoria/pagine/gestione-riservata.json`.
3. **Dashboard** — `/` — accesso `authenticated` — modulo `dashboard` — Dashboard derivata dai registri, con indicatori cliccabili e nessun saldo hardcoded. Fonte UI: `frontend/src/pages/Dashboard.jsx`; mappa: `memoria/pagine/dashboard.json`.
4. **Inserimento rapido** — `/rapido` — accesso `authenticated` — modulo `dashboard` — Inserimento rapido idempotente di corrispettivi, versamenti, pagamenti, apporti e presenze. Fonte UI: `frontend/src/pages/InserimentoRapido.jsx`; mappa: `memoria/pagine/inserimento-rapido.json`.
5. **Archivio fatture** — `/fatture` — accesso `authenticated` — modulo `fatture` — Archivio unico fatture ricevute, PDF/XML, provenienza, pagamento e spostamento Cassa/Banca. Fonte UI: `frontend/src/pages/ArchivioFattureRicevute.jsx`; mappa: `memoria/pagine/fatture.json`.
6. **Corrispettivi** — `/fatture/corrispettivi` — accesso `authenticated` — modulo `fatture` — Corrispettivi giornalieri, aliquote, mezzi di pagamento e scritture Cassa/POS senza duplicati. Fonte UI: `frontend/src/pages/Corrispettivi.jsx`; mappa: `memoria/pagine/corrispettivi.json`.
7. **Fornitori** — `/fornitori` — accesso `authenticated` — modulo `fornitori` — Anagrafica fornitori univoca, fatture, residui, IBAN, metodo e merge controllato. Fonte UI: `frontend/src/pages/Fornitori.jsx`; mappa: `memoria/pagine/fornitori.json`.
8. **Prima Nota** — `/prima-nota` — accesso `authenticated` — modulo `prima-nota` — Prima Nota Cassa/Banca/SumUp/Soci come viste coerenti del ledger, raggruppate per giorno. Fonte UI: `frontend/src/pages/PrimaNota.jsx`; mappa: `memoria/pagine/prima-nota.json`.
9. **Pulizia Prima Nota** — `/prima-nota/pulizia` — accesso `authenticated` — modulo `prima-nota` — Audit Prima Nota con liste esatte, dry-run, correzione deterministica e rollback. Fonte UI: `frontend/src/pages/PuliziaPrimaNota.jsx`; mappa: `memoria/pagine/prima-nota-pulizia.json`.
10. **Flotta noleggio** — `/noleggio` — accesso `authenticated` — modulo `noleggio` — Flotta ricostruita da fatture di noleggio, contratti, targhe e storico driver. Fonte UI: `frontend/src/pages/NoleggioAuto.jsx`; mappa: `memoria/pagine/noleggio-flotta.json`.
11. **Verbali noleggio** — `/noleggio/verbali` — accesso `authenticated` — modulo `noleggio` — Riconciliazione verbali, veicoli, driver, pagamenti, quietanze e documenti. Fonte UI: `frontend/src/pages/VerbaliRiconciliazione.jsx`; mappa: `memoria/pagine/noleggio-verbali.json`.
12. **Costi noleggio** — `/noleggio/costi` — accesso `authenticated` — modulo `noleggio` — Costi noleggio per veicolo: canoni, pedaggi, verbali, bollo e riparazioni. Fonte UI: `frontend/src/pages/hub/VeicoliHub.jsx`; mappa: `memoria/pagine/noleggio-costi.json`.
13. **Dettaglio verbale** — `/verbali-noleggio/:identificativo` — accesso `authenticated` — modulo `noleggio` — Fascicolo del verbale con PDF, importo, targa, trasgressore, driver e prove. Fonte UI: `frontend/src/pages/DettaglioVerbale.jsx`; mappa: `memoria/pagine/dettaglio-verbale.json`.
14. **Piano dei Conti** — `/contabilita` — accesso `authenticated` — modulo `contabilita` — Piano dei conti gerarchico, regole versionate e movimenti collegati. Fonte UI: `frontend/src/pages/PianoDeiConti.jsx`; mappa: `memoria/pagine/contabilita-piano-conti.json`.
15. **Bilancio** — `/contabilita/bilancio` — accesso `authenticated` — modulo `contabilita` — Bilancio calcolato da scritture valide, quadratura e drill-down. Fonte UI: `frontend/src/pages/Bilancio.jsx`; mappa: `memoria/pagine/contabilita-bilancio.json`.
16. **Verifica Bilancio** — `/contabilita/verifica` — accesso `authenticated` — modulo `contabilita` — Verifica bilancio con anomalie spiegate e link alla scrittura origine. Fonte UI: `frontend/src/pages/BilancioVerifica.jsx`; mappa: `memoria/pagine/contabilita-verifica.json`.
17. **Libro Giornale** — `/contabilita/giornale` — accesso `authenticated` — modulo `contabilita` — Libro giornale progressivo, bilanciato, filtrabile, esportabile e auditabile. Fonte UI: `frontend/src/pages/LibroGiornale.jsx`; mappa: `memoria/pagine/contabilita-giornale.json`.
18. **Controllo mensile** — `/contabilita/controllo` — accesso `authenticated` — modulo `contabilita` — Controllo mensile con lista per ogni anomalia e stato di risoluzione. Fonte UI: `frontend/src/pages/ControlloMensile.jsx`; mappa: `memoria/pagine/contabilita-controllo.json`.
19. **Calendario fiscale** — `/contabilita/calendario` — accesso `authenticated` — modulo `contabilita` — Calendario fiscale con fonte, scadenza, stato, promemoria e documento collegato. Fonte UI: `frontend/src/pages/CalendarioFiscale.jsx`; mappa: `memoria/pagine/contabilita-calendario.json`.
20. **Cespiti** — `/contabilita/cespiti` — accesso `authenticated` — modulo `contabilita` — Cespiti, documento origine, ammortamenti Decimal, dismissioni e storia. Fonte UI: `frontend/src/pages/GestioneCespiti.jsx`; mappa: `memoria/pagine/contabilita-cespiti.json`.
21. **Finanziaria** — `/contabilita/finanziaria` — accesso `authenticated` — modulo `contabilita` — Posizione finanziaria, flussi, debiti, crediti e finanziamenti soci non duplicati. Fonte UI: `frontend/src/pages/Finanziaria.jsx`; mappa: `memoria/pagine/contabilita-finanziaria.json`.
22. **Chiusura esercizio** — `/contabilita/chiusura` — accesso `authenticated` — modulo `contabilita` — Chiusura esercizio con checklist, anteprima, conferma forte, audit e rollback. Fonte UI: `frontend/src/pages/ChiusuraEsercizio.jsx`; mappa: `memoria/pagine/contabilita-chiusura.json`.
23. **Budget** — `/contabilita/budget` — accesso `authenticated` — modulo `contabilita` — Budget versionato e confronto consuntivo per mese, conto e centro. Fonte UI: `frontend/src/pages/BudgetPrevisionale.jsx`; mappa: `memoria/pagine/contabilita-budget.json`.
24. **Mutui** — `/contabilita/mutui` — accesso `authenticated` — modulo `contabilita` — Mutui, rate, quota capitale/interessi, banca e residuo riconciliato. Fonte UI: `frontend/src/pages/Mutui.jsx`; mappa: `memoria/pagine/contabilita-mutui.json`.
25. **Contabilita avanzata** — `/contabilita/avanzata` — accesso `authenticated` — modulo `contabilita` — Analisi contabili avanzate come viste derivate, con formule e drill-down. Fonte UI: `frontend/src/pages/ContabilitaAvanzata.jsx`; mappa: `memoria/pagine/contabilita-avanzata.json`.
26. **Utile obiettivo** — `/contabilita/utile` — accesso `authenticated` — modulo `contabilita` — Simulazione utile obiettivo separata dai consuntivi e senza scritture reali. Fonte UI: `frontend/src/pages/UtileObiettivo.jsx`; mappa: `memoria/pagine/contabilita-utile.json`.
27. **Previsioni acquisti** — `/contabilita/previsioni-acquisti` — accesso `authenticated` — modulo `contabilita` — Previsioni acquisti basate su storico e scadenze, senza ordini automatici. Fonte UI: `frontend/src/pages/PrevisioniAcquisti.jsx`; mappa: `memoria/pagine/contabilita-previsioni-acquisti.json`.
28. **Learning Machine** — `/learning-machine` — accesso `authenticated` — modulo `strumenti` — Suggerimenti di apprendimento con evidenza, confidenza, approvazione e revoca. Fonte UI: `frontend/src/pages/LearningMachine.jsx`; mappa: `memoria/pagine/learning-machine.json`.
29. **Scadenze** — `/scadenze` — accesso `authenticated` — modulo `contabilita` — Scadenziario fornitori con residui, parziali, prove e alert navigabili. Fonte UI: `frontend/src/pages/Scadenze.jsx`; mappa: `memoria/pagine/scadenze.json`.
30. **Ritenute** — `/ritenute` — accesso `authenticated` — modulo `personale` — Ritenute per percipiente, periodo, aliquota, F24 e quadratura annuale. Fonte UI: `frontend/src/pages/Ritenute.jsx`; mappa: `memoria/pagine/ritenute.json`.
31. **Riconciliazione dashboard** — `/riconciliazione` — accesso `authenticated` — modulo `riconciliazione` — Indice unico delle riconciliazioni con code, stati e contatori navigabili. Fonte UI: `frontend/src/pages/RiconciliazioneUnificata.jsx`; mappa: `memoria/pagine/riconciliazione-bancaria.json`.
32. **Riconciliazione banca** — `/riconciliazione/banca` — accesso `authenticated` — modulo `riconciliazione` — Riconciliazione bancaria deterministica, candidati motivati e operation_id. Fonte UI: `frontend/src/pages/RiconciliazioneUnificata.jsx`; mappa: `memoria/pagine/riconciliazione-banca.json`.
33. **Riconciliazione F24** — `/riconciliazione/f24` — accesso `authenticated` — modulo `riconciliazione` — F24 con PDF, righe tributo, quietanza, banca e ricerca per codice. Fonte UI: `frontend/src/pages/RiconciliazioneUnificata.jsx`; mappa: `memoria/pagine/riconciliazione-f24.json`.
34. **Riconciliazione stipendi** — `/riconciliazione/stipendi` — accesso `authenticated` — modulo `riconciliazione` — Riconciliazione stipendi per dipendente, IBAN, periodo e regola del giorno 25. Fonte UI: `frontend/src/pages/RiconciliazioneUnificata.jsx`; mappa: `memoria/pagine/riconciliazione-stipendi.json`.
35. **Riconciliazione documenti** — `/riconciliazione/documenti` — accesso `authenticated` — modulo `riconciliazione` — Riconciliazione documenti con originale, classificazione, candidati e provenienza. Fonte UI: `frontend/src/pages/RiconciliazioneUnificata.jsx`; mappa: `memoria/pagine/riconciliazione-documenti.json`.
36. **Archivio bonifici** — `/riconciliazione/archivio-bonifici` — accesso `authenticated` — modulo `riconciliazione` — Archivio bonifici con CRO/TRN, beneficiario, periodo, descrizione e associazioni persistenti. Fonte UI: `frontend/src/pages/ArchivioBonifici.jsx`; mappa: `memoria/pagine/archivio-bonifici.json`.
37. **Assegni** — `/riconciliazione/assegni` — accesso `authenticated` — modulo `riconciliazione` — Assegni distinti per numero/data/importo, fatture collegate e casi ambigui. Fonte UI: `frontend/src/pages/GestioneAssegni.jsx`; mappa: `memoria/pagine/assegni.json`.
38. **PayPal** — `/riconciliazione/paypal` — accesso `authenticated` — modulo `riconciliazione` — PayPal interconnesso con banca, fatture, Prima Nota e prove tramite operation_id. Fonte UI: `frontend/src/pages/RiconciliazionePaypal.jsx`; mappa: `memoria/pagine/riconciliazione-paypal.json`.
39. **Coerenza POS** — `/riconciliazione/coerenza-pos` — accesso `authenticated` — modulo `riconciliazione` — Coerenza fra corrispettivi, POS, commissioni, giorni di vendita e accrediti. Fonte UI: `frontend/src/pages/CoerenzaPOSCorrispettivi.jsx`; mappa: `memoria/pagine/coerenza-pos.json`.
40. **Import documenti** — `/documenti/import` — accesso `authenticated` — modulo `documenti` — Import documenti/ZIP con validazione, salvataggio reale, hash e report. Fonte UI: `frontend/src/pages/ImportDocumenti.jsx`; mappa: `memoria/pagine/documenti-import.json`.
41. **Archivio documenti** — `/documenti/archivio` — accesso `authenticated` — modulo `documenti` — Archivio documenti indicizzati con metadati, originale, relazioni e viewer. Fonte UI: `frontend/src/pages/Documenti.jsx`; mappa: `memoria/pagine/documenti-archivio.json`.
42. **Verifica coerenza** — `/strumenti` — accesso `authenticated` — modulo `strumenti` — Controlli di coerenza riproducibili con query, lista, severita e risoluzione. Fonte UI: `frontend/src/pages/VerificaCoerenza.jsx`; mappa: `memoria/pagine/strumenti-verifica.json`.
43. **Movimenti banca** — `/riconciliazione/movimenti-banca` — accesso `authenticated` — modulo `riconciliazione` — Movimenti banca con riga fonte, classificazione e stato di associazione. Fonte UI: `frontend/src/pages/VerificaMovimentiBanca.jsx`; mappa: `memoria/pagine/strumenti-movimenti-banca.json`.
44. **Commercialista** — `/strumenti/commercialista` — accesso `authenticated` — modulo `strumenti` — Fascicolo per commercialista con registri, documenti, manifest e quadrature. Fonte UI: `frontend/src/pages/Commercialista.jsx`; mappa: `memoria/pagine/strumenti-commercialista.json`.
45. **Pianificazione** — `/strumenti/pianificazione` — accesso `authenticated` — modulo `strumenti` — Pianificazione di attivita e adempimenti derivati, assegnati e notificati. Fonte UI: `frontend/src/pages/Pianificazione.jsx`; mappa: `memoria/pagine/strumenti-pianificazione.json`.
46. **Visure** — `/strumenti/visure` — accesso `authenticated` — modulo `strumenti` — Visure con soggetto, tipo, stato e documento, senza richieste esterne automatiche. Fonte UI: `frontend/src/pages/Visure.jsx`; mappa: `memoria/pagine/strumenti-visure.json`.
47. **Agenti AI** — `/agenti` — accesso `authenticated` — modulo `strumenti` — Agenti e automazioni con scopo, permessi, run, log, esito e disattivazione. Fonte UI: `frontend/src/pages/Agenti.jsx`; mappa: `memoria/pagine/agenti.json`.
48. **Impostazioni F24 email** — `/impostazioni-f24-email` — accesso `authenticated` — modulo `integrazioni` — Configurazione ingest email F24, query, mittenti, test e ultima scansione. Fonte UI: `frontend/src/pages/ImpostazioniF24Email.jsx`; mappa: `memoria/pagine/impostazioni-f24-email.json`.
49. **Impostazioni AI** — `/impostazioni-ai` — accesso `admin` — modulo `integrazioni` — Configurazione AI tramite riferimenti a segreti, modello, limiti e health. Fonte UI: `frontend/src/pages/ImpostazioniAI.jsx`; mappa: `memoria/pagine/impostazioni-ai.json`.
50. **Integrazione OpenAPI** — `/integrazioni` — accesso `authenticated` — modulo `integrazioni` — Integrazioni API con scope, token ruotabili, OpenAPI, rate limit e revoca. Fonte UI: `frontend/src/pages/IntegrazioniOpenAPI.jsx`; mappa: `memoria/pagine/integrazioni-openapi.json`.
51. **Riconciliazione PagoPA** — `/riconciliazione/pagopa` — accesso `authenticated` — modulo `riconciliazione` — PagoPA con IUV, ente, avviso, ricevuta, banca e scelta nei casi ambigui. Fonte UI: `frontend/src/pages/GestionePagoPA.jsx`; mappa: `memoria/pagine/integrazioni-pagopa.json`.
52. **Mittenti Email attendibili** — `/integrazioni/mittenti-email` — accesso `authenticated` — modulo `integrazioni` — Mittenti email attendibili con canale, documento atteso, priorita e audit. Fonte UI: `frontend/src/pages/MittentiEmail.jsx`; mappa: `memoria/pagine/integrazioni-mittenti-email.json`.
53. **Admin sistema** — `/admin` — accesso `admin` — modulo `admin` — Admin con salute, job, errori, configurazione non sensibile e azioni protette. Fonte UI: `frontend/src/pages/Admin.jsx`; mappa: `memoria/pagine/admin.json`.
54. **Admin MFA** — `/admin/mfa` — accesso `admin` — modulo `admin` — MFA amministrativa, enrollment, revoca, recovery e step-up authentication. Fonte UI: `frontend/src/pages/MFAAdmin.jsx`; mappa: `memoria/pagine/admin-mfa.json`.
55. **Elaborazioni amministrative** — `/admin/elaborazioni` — accesso `admin` — modulo `admin` — Elaborazioni batch idempotenti con progresso, errori per record e retry selettivo. Fonte UI: `frontend/src/pages/hub/AdminElaborazioni.jsx`; mappa: `memoria/pagine/admin-batch-reprocessing.json`.
56. **Elaborazioni legacy** — `/admin/batch-processor` — accesso `admin` — modulo `admin` — Alias legacy temporaneo verso elaborazioni, senza componente o router duplicato. Fonte UI: `frontend/src/pages/hub/AdminElaborazioni.jsx`; mappa: `memoria/pagine/admin-batch-processor.json`.
57. **Utenti** — `/utenti` — accesso `admin` — modulo `admin` — Utenti, ruoli, attivazione, reset sicuro e audit senza auto-elevazione. Fonte UI: `frontend/src/pages/Utenti.jsx`; mappa: `memoria/pagine/utenti.json`.
58. **Mappa gestionale** — `/mappa-gestionale` — accesso `authenticated` — modulo `strumenti` — Mappa gestionale generata dal catalogo con moduli, route, flussi e health. Fonte UI: `frontend/src/pages/MappaGestionale.jsx`; mappa: `memoria/pagine/mappa-gestionale.json`.
59. **Gestione IVA** — `/iva` — accesso `authenticated` — modulo `contabilita` — IVA, liquidazioni, fatture, corrispettivi, F24, periodi e quadrature. Fonte UI: `frontend/src/pages/GestioneIVA.jsx`; mappa: `memoria/pagine/iva.json`.
60. **Verifica fatture estere** — `/fatture-estere-verifica` — accesso `authenticated` — modulo `fatture` — Fatture estere, paese, valuta, integrazione/autofattura e trattamento IVA. Fonte UI: `frontend/src/pages/FattureEstereVerifica.jsx`; mappa: `memoria/pagine/fatture-estere-verifica.json`.
61. **Dati ISA** — `/contabilita/dati-isa` — accesso `authenticated` — modulo `contabilita` — Dati ISA derivati, tracciabili, quadrati ed esportabili senza valori inventati. Fonte UI: `frontend/src/pages/DatiIsa.jsx`; mappa: `memoria/pagine/contabilita-dati-isa.json`.
62. **Indice documentale Drive** — `/documenti/drive` — accesso `authenticated` — modulo `documenti` — Indice Drive autorevole per metadati, hash, percorso e stato indicizzazione. Fonte UI: `frontend/src/pages/DriveDocumentIndex.jsx`; mappa: `memoria/pagine/documenti-drive.json`.
63. **Atti amministrativi** — `/documenti/atti` — accesso `authenticated` — modulo `documenti` — Atti amministrativi con ente, protocollo, originale, scadenze e notifiche. Fonte UI: `frontend/src/pages/AttiAmministrativi.jsx`; mappa: `memoria/pagine/documenti-atti.json`.
64. **Situazione fiscale** — `/situazione-fiscale` — accesso `authenticated` — modulo `contabilita` — Situazione fiscale unificata con F24, dichiarazioni, quietanze e anomalie. Fonte UI: `frontend/src/pages/SituazioneFiscale.jsx`; mappa: `memoria/pagine/situazione-fiscale.json`.

## Appendice B — Fogli e progressivi Drive/Sheets

| Foglio | Nome logico | Prefisso |
|---|---|---|
| Documenti | `documents_inbox` | `DOC` |
| Fatture ricevute | `invoices` | `FAR` |
| Fatture emesse | `fatture_emesse` | `FAE` |
| Fornitori | `fornitori` | `FOR` |
| Dipendenti | `dipendenti` | `DIP` |
| Cedolini | `cedolini` | `CED` |
| Estratti conto | `estratti_conto` | `ECD` |
| Movimenti bancari | `estratto_conto_movimenti` | `ECM` |
| Prima Nota Cassa | `prima_nota_cassa` | `CAS` |
| Prima Nota Banca | `prima_nota_banca` | `BAN` |
| Bonifici | `bonifici_transfers` | `BON` |
| Assegni | `assegni` | `ASS` |
| Corrispettivi | `corrispettivi` | `COR` |
| F24 | `f24_unificato` | `F24` |
| Quietanze F24 | `quietanze_f24` | `QF24` |
| PayPal | `paypal_transactions` | `PAY` |
| Scadenze fornitori | `scadenziario_fornitori` | `SCA` |
| Relazioni | `entity_relations` | `REL` |
| Codici tributo | `tax_code_registry` | `CTR` |
| Import PartenoPay | `partenopay_import_runs` | `PPR` |
| Email PartenoPay | `verbali_email_archive` | `PPE` |
| Verbali PartenoPay | `verbali_noleggio` | `PPV` |

## Appendice C — Tutte le variabili rilevate

> Inventario dei nomi, non dei valori. I valori sensibili devono restare nel secret store.

| Variabile | Gruppo | Sensibilità | Tipo/default dichiarato | Sorgenti |
|---|---|---|---|---|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | sicurezza | segreta | `int` / valore non riportato | `app/config.py` |
| `ADER_MICRO_RESIDUAL_THRESHOLD_CENTS` | azienda-fiscale | configurazione | `int` / `500` | `app/config.py` |
| `ADMIN_EMAIL` | sicurezza | configurazione | non dichiarato in Settings | `app/hr/routers/auth.py`, `app/hr/services/email_smtp.py`, `app/routers/auth.py`, `app/routers/pin_login.py`, `scripts/e2e_distruttivo_server.py` |
| `ADMIN_PASSWORD` | sicurezza | segreta | non dichiarato in Settings | `app/hr/routers/auth.py`, `app/menu/routes/qrcode_routes.py`, `app/routers/auth.py`, `scripts/e2e_distruttivo_server.py` |
| `ADMIN_PASSWORD_HASH` | sicurezza | segreta | non dichiarato in Settings | `app/hr/routers/auth.py`, `app/routers/auth.py` |
| `ADMIN_PIN` | sicurezza | segreta | non dichiarato in Settings | `app/routers/pin_login.py`, `app/services/utenti_pin.py` |
| `ADMIN_PIN_INIZIALE` | sicurezza | segreta | non dichiarato in Settings | `app/lotti/routers/tablet_operatori.py` |
| `ADMIN_PIN_RECOVERY` | sicurezza | segreta | non dichiarato in Settings | `app/lotti/routers/tablet_operatori.py` |
| `ADMIN_TOKEN_EXPIRE_MINUTES` | sicurezza | segreta | non dichiarato in Settings | `app/hr/routers/pin_login.py` |
| `ADMIN_USERNAME` | sicurezza | configurazione | non dichiarato in Settings | `app/menu/routes/qrcode_routes.py` |
| `AI_L2_MAX_FINANCIAL_IMPACT` | app-runtime | configurazione | non dichiarato in Settings | `app/agents/decision_engine.py` |
| `AI_L2_MIN_CONFIDENCE` | app-runtime | configurazione | non dichiarato in Settings | `app/agents/decision_engine.py` |
| `ALGORITHM` | app-runtime | configurazione | `str` / `'HS256'` | `app/config.py` |
| `ALLOWED_EXTENSIONS` | sicurezza | configurazione | `str` / `'.xml,.xlsx,.xls,.pdf,.csv'` | `app/config.py` |
| `ALLOWED_HEADERS` | sicurezza | configurazione | `str` / `'*'` | `app/config.py` |
| `ALLOWED_METHODS` | sicurezza | configurazione | `str` / `'*'` | `app/config.py` |
| `ALLOWED_ORIGINS` | sicurezza | configurazione | `str` / `'*'` | `app/config.py` |
| `ALLOW_CREDENTIALS` | sicurezza | configurazione | `bool` / `True` | `app/config.py` |
| `ANTHROPIC_API_KEY` | ai | segreta | non dichiarato in Settings | `app/hr/services/document_ai_extractor.py`, `app/lotti/routers/food_cost.py`, `app/lotti/routers/ingredienti.py`, `app/lotti/routers/normalizzazione.py`, `app/lotti/routers/schede_tecniche.py`, `app/lotti/routers/scheduler.py`, `app/routers/ai_parser.py`, `app/routers/fornitori_learning.py`, `app/routers/settings_router.py`, `app/services/ai_categorizzazione.py`, `app/services/ai_document_parser.py`, `app/services/chat_ai_engine.py`, `app/services/document_ai_extractor.py`, `app/services/enhanced_document_parser.py`, `app/services/llm_document_parser.py` |
| `ANTHROPIC_DOCUMENT_MODEL` | ai | configurazione | non dichiarato in Settings | `app/services/anthropic_llm_client.py` |
| `ANTHROPIC_MODEL` | ai | configurazione | non dichiarato in Settings | `app/routers/settings_router.py`, `app/services/anthropic_llm_client.py`, `app/services/chat_ai_engine.py` |
| `APPDIPENDENTI_DB_URL` | app-runtime | configurazione | non dichiarato in Settings | `render.yaml` |
| `APP_NAME` | app-runtime | configurazione | `str` / `'Azienda in Cloud ERP'` | `app/config.py` |
| `APP_VERSION` | app-runtime | configurazione | `str` / `'2.0.0'` | `app/config.py` |
| `AUDIT_BASE_URL` | app-runtime | configurazione | non dichiarato in Settings | `frontend/scripts/audit-layout.cjs`, `frontend/scripts/audit-operation-index.cjs`, `frontend/scripts/audit-viewer.cjs` |
| `AUTH_ENFORCE` | app-runtime | configurazione | non dichiarato in Settings | `app/lotti/auth.py` |
| `AUTH_GOOGLE_EMAILS` | app-runtime | configurazione | non dichiarato in Settings | `app/lotti/auth.py` |
| `AUTH_LOCK_SECONDS` | app-runtime | configurazione | non dichiarato in Settings | `app/lotti/auth.py` |
| `AUTH_MAX_FAILS` | app-runtime | configurazione | non dichiarato in Settings | `app/lotti/auth.py` |
| `AUTH_SECRET` | app-runtime | segreta | non dichiarato in Settings | `app/lotti/auth.py` |
| `AUTH_TOKEN` | test-tooling | segreta | non dichiarato in Settings | `scripts/collaudo_ui.mjs` |
| `AUTH_TOKEN_TTL_H` | test-tooling | segreta | non dichiarato in Settings | `app/lotti/auth.py` |
| `AUTOMATION_SECRET` | app-runtime | segreta | non dichiarato in Settings | `app/lotti/auth.py` |
| `AZIENDA_ATTIVITA` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/lotti/azienda.py` |
| `AZIENDA_BANCA` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/config/azienda.py` |
| `AZIENDA_BIC` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/config/azienda.py` |
| `AZIENDA_CAP` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/config/azienda.py` |
| `AZIENDA_CF` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/config/azienda.py`, `app/lotti/azienda.py` |
| `AZIENDA_CITTA` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/config/azienda.py` |
| `AZIENDA_CODICE_DESTINATARIO` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/lotti/azienda.py` |
| `AZIENDA_EMAIL` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/config/azienda.py`, `app/lotti/azienda.py` |
| `AZIENDA_IBAN` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/config/azienda.py` |
| `AZIENDA_INDIRIZZO` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/config/azienda.py`, `app/lotti/azienda.py` |
| `AZIENDA_NOME` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/lotti/azienda.py` |
| `AZIENDA_PEC` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/config/azienda.py` |
| `AZIENDA_PIVA` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/config/azienda.py`, `app/hr/routers/portale_buste.py`, `app/lotti/azienda.py` |
| `AZIENDA_PROVINCIA` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/config/azienda.py` |
| `AZIENDA_RAGIONE_SOCIALE` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/config/azienda.py`, `app/hr/routers/portale_buste.py` |
| `AZIENDA_RESP_HACCP` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/lotti/azienda.py` |
| `AZIENDA_SEDE` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/hr/routers/portale_buste.py` |
| `AZIENDA_STUDIO` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/lotti/azienda.py` |
| `AZIENDA_TEL` | azienda-fiscale | configurazione | non dichiarato in Settings | `app/config/azienda.py`, `app/lotti/azienda.py` |
| `BACKEND_URL` | app-runtime | configurazione | non dichiarato in Settings | `app/menu/routes/qrcode_routes.py`, `scripts/smoke_app.py` |
| `BACKUP_DIR` | app-runtime | configurazione | non dichiarato in Settings | `app/lotti/routers/backup.py` |
| `BASE_URL` | test-tooling | configurazione | non dichiarato in Settings | `scripts/collaudo_ui.mjs` |
| `CACHE_TTL_SECONDS` | app-runtime | configurazione | `int` / `3600` | `app/config.py` |
| `CHROMIUM_PATH` | test-tooling | configurazione | non dichiarato in Settings | `scripts/collaudo_ui.mjs` |
| `COMMERCIALISTA_EMAIL` | app-runtime | configurazione | non dichiarato in Settings | `app/hr/routers/dipendenti_cloud/__init__.py` |
| `CORS_ALLOWED_ORIGINS` | sicurezza | configurazione | `str` / `''` | `app/config.py` |
| `CORS_ORIGINS` | sicurezza | configurazione | `str` / `'*'` | `app/config.py`, `app/lotti/server.py`, `app/menu/server.py` |
| `CREDENTIALS_ENCRYPTION_KEY` | app-runtime | configurazione | non dichiarato in Settings | `render.yaml` |
| `DATA_BACKEND` | app-runtime | configurazione | `str` / `'sheets'` | `app/config.py`, `render.yaml` |
| `DB_NAME` | app-runtime | configurazione | `str` / `'Gestionale'` | `app/config.py`, `app/lotti/run_locale_test.py`, `app/lotti/scripts/fix_fornitori_acquaviva.py`, `app/lotti/scripts/import_acquaviva_definitivo.py`, `app/lotti/scripts/import_listino_2026.py`, `app/lotti/scripts/import_ricette_excel.py`, `app/lotti/scripts/scrape_acquaviva_images.py`, `app/lotti/scripts/scrape_vandemoortele_acquaviva.py`, `app/lotti/tests/test_iteration54_features.py`, `app/lotti/utils/shared.py` |
| `DEBUG` | app-runtime | configurazione | `bool` / `False` | `app/config.py` |
| `DEFAULT_USER_EMAIL` | app-runtime | configurazione | `str` / `'admin@ceraldi.it'` | `app/config.py` |
| `DEFAULT_USER_ID` | app-runtime | configurazione | `str` / `'admin'` | `app/config.py` |
| `DEV` | app-runtime | configurazione | non dichiarato in Settings | `frontend/src/components/ErrorBoundary.jsx` |
| `DIGEST_GIORNI` | app-runtime | configurazione | non dichiarato in Settings | `app/lotti/routers/digest.py` |
| `DRIVE_BONIFICI_FOLDER_ID` | drive-sheets | configurazione | non dichiarato in Settings | `app/hr/routers/dipendenti_cloud/__init__.py` |
| `DRIVE_CARTE_FOLDER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `DRIVE_CEDOLINI_FOLDER_ID` | drive-sheets | configurazione | non dichiarato in Settings | `app/hr/services/google_drive_sa.py` |
| `DRIVE_DOCUMENT_INDEX_ROOT_FOLDER_ID` | drive-sheets | configurazione | `str` / `'1tmVu6fl7qhJbLcGCHT3wEQzrvFAElc9h'` | `app/config.py` |
| `DRIVE_ESTRATTI_ANNO_MINIMO` | drive-sheets | configurazione | `int` / `2026` | `app/config.py` |
| `DRIVE_ESTRATTI_BATCH_SIZE` | drive-sheets | configurazione | `int` / `1` | `app/config.py`, `render.yaml` |
| `DRIVE_F24_FOLDER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `DRIVE_FATTURE_BATCH_SIZE` | drive-sheets | configurazione | `int` / `1` | `app/config.py`, `render.yaml` |
| `DRIVE_FISCAL_ROOT_FOLDER_ID` | drive-sheets | configurazione | `str` / `'1f48bounfoOyHL_kqpHAp2GAnFfEpHvVa'` | `app/config.py` |
| `DRIVE_FOLDER_REGISTRY_JSON` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `DRIVE_NOLEGGIO_FOLDER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `DRIVE_PAYPAL_FOLDER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `DRIVE_PRESENZE_FOLDER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `DRIVE_VERBALI_FOLDER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `E2E_BASE_URL` | test-tooling | configurazione | non dichiarato in Settings | `frontend/scripts/audit-destructive-e2e.cjs`, `frontend/scripts/audit-pages-e2e.cjs` |
| `E2E_FRONTEND_DIST` | test-tooling | configurazione | non dichiarato in Settings | `scripts/e2e_distruttivo_server.py` |
| `EMAIL_ADDRESS` | gmail-email | configurazione | `Optional[str]` / `None` | `app/config.py`, `app/hr/routers/dimissioni.py`, `app/routers/configurazioni.py`, `app/routers/learning_machine.py`, `app/services/gmail_search.py` |
| `EMAIL_APP_PASSWORD` | gmail-email | segreta | `Optional[str]` / valore non riportato | `app/config.py`, `app/hr/routers/dimissioni.py`, `app/routers/configurazioni.py`, `app/routers/learning_machine.py`, `app/services/gmail_search.py` |
| `EMAIL_PASSWORD` | gmail-email | segreta | `Optional[str]` / valore non riportato | `app/config.py`, `app/hr/routers/cedolini.py`, `app/routers/commercialista.py`, `app/routers/configurazioni.py`, `app/routers/learning_machine.py`, `app/services/gmail_search.py`, `app/services/pagopa_scanner.py` |
| `EMAIL_USER` | gmail-email | configurazione | `Optional[str]` / `None` | `app/config.py`, `app/hr/routers/cedolini.py`, `app/routers/commercialista.py`, `app/routers/configurazioni.py`, `app/services/gmail_search.py`, `app/services/pagopa_scanner.py` |
| `ENABLE_ASYNC_IMPORTS` | feature-job | configurazione | `bool` / `True` | `app/config.py` |
| `ENABLE_CACHING` | feature-job | configurazione | `bool` / `True` | `app/config.py` |
| `ENABLE_DOCUMENT_AI` | feature-job | configurazione | `bool` / `False` | `app/config.py` |
| `ENABLE_DRIVE_AVVISI_BONARI_SYNC` | feature-job | configurazione | `bool` / `True` | `app/config.py` |
| `ENABLE_DRIVE_BONIFICI_SYNC` | feature-job | configurazione | `bool` / `False` | `app/config.py` |
| `ENABLE_DRIVE_CARTELLE_ESATTORIALI_SYNC` | feature-job | configurazione | `bool` / `True` | `app/config.py` |
| `ENABLE_DRIVE_CEDOLINI_SYNC` | feature-job | configurazione | `bool` / `True` | `app/config.py` |
| `ENABLE_DRIVE_CORRISPETTIVI_SYNC` | feature-job | configurazione | `bool` / `True` | `app/config.py` |
| `ENABLE_DRIVE_DICHIARAZIONI_IVA_SYNC` | feature-job | configurazione | `bool` / `False` | `app/config.py` |
| `ENABLE_DRIVE_ESTRATTI_CONTO_SYNC` | feature-job | configurazione | `bool` / `True` | `app/config.py` |
| `ENABLE_DRIVE_FATTURE_SYNC` | feature-job | configurazione | `bool` / `True` | `app/config.py` |
| `ENABLE_DRIVE_QUIETANZE_SYNC` | feature-job | configurazione | `bool` / `True` | `app/config.py` |
| `ENABLE_DRIVE_VERBALI_SYNC` | feature-job | configurazione | `bool` / `True` | `app/config.py` |
| `ENABLE_EMAIL_F24_SYNC` | feature-job | configurazione | `bool` / `True` | `app/config.py` |
| `ENABLE_EMAIL_VERBALI_SYNC` | feature-job | configurazione | `bool` / `True` | `app/config.py` |
| `ENABLE_GMAIL_IMAP` | feature-job | configurazione | `bool` / `True` | `app/config.py` |
| `ENABLE_HEALTH_CHECK` | feature-job | configurazione | non dichiarato in Settings | `frontend_lotti/craco.config.js` |
| `ENABLE_RENDER_CANONICAL_INGEST` | feature-job | configurazione | non dichiarato in Settings | `render_workflows/document_ingest.py` |
| `ENABLE_RENDER_DRIVE_MOVES` | feature-job | configurazione | non dichiarato in Settings | `render_workflows/document_ingest.py` |
| `ENABLE_SCHEDULER` | feature-job | configurazione | `bool` / `True` | `app/config.py`, `render.yaml` |
| `ENABLE_SMTP_EMAIL` | feature-job | configurazione | `bool` / `False` | `app/config.py` |
| `ENVIRONMENT` | app-runtime | configurazione | `str` / `'production'` | `app/config.py`, `app/utils/session_cookie.py`, `scripts/e2e_distruttivo_server.py` |
| `FAIL_FAST_SECRETS` | app-runtime | segreta | non dichiarato in Settings | `app/config.py`, `render.yaml` |
| `FISCAL_COMPANY_ID` | azienda-fiscale | configurazione | `str` / `'04523831214'` | `app/config.py` |
| `FONTS_DIR` | app-runtime | configurazione | `Path` / `Path('fonts')` | `app/config.py` |
| `FROM_EMAIL` | gmail-email | configurazione | `Optional[str]` / `None` | `app/config.py`, `app/routers/commercialista.py` |
| `FRONTEND_URL` | app-runtime | configurazione | `Optional[str]` / `None` | `app/config.py`, `scripts/smoke_app.py` |
| `GEMINI_API_KEY` | ai | segreta | `Optional[str]` / valore non riportato | `app/config.py` |
| `GESTIONALECLOUD_API_URL` | app-runtime | configurazione | non dichiarato in Settings | `app/lotti/routers/gestionale_fatture.py`, `app/lotti/routers/tablet_operatori.py` |
| `GESTIONALE_MCP_API_BASE_URL` | mcp | configurazione | non dichiarato in Settings | `gestionale_mcp/config.py` |
| `GESTIONALE_MCP_API_TOKEN` | mcp | segreta | non dichiarato in Settings | `gestionale_mcp/config.py` |
| `GESTIONALE_MCP_HOST` | mcp | configurazione | non dichiarato in Settings | `gestionale_mcp/config.py` |
| `GESTIONALE_MCP_ISSUER_URL` | mcp | configurazione | non dichiarato in Settings | `gestionale_mcp/config.py` |
| `GESTIONALE_MCP_LOG_LEVEL` | mcp | configurazione | non dichiarato in Settings | `gestionale_mcp/config.py` |
| `GESTIONALE_MCP_RESOURCE_SERVER_URL` | mcp | configurazione | non dichiarato in Settings | `gestionale_mcp/config.py` |
| `GESTIONE_RISERVATA_CODE` | app-runtime | configurazione | non dichiarato in Settings | `app/routers/gestione_riservata.py`, `scripts/e2e_distruttivo_server.py` |
| `GMAIL_ACCOUNT_AMMINISTRATIVO` | gmail-email | configurazione | `Optional[str]` / `None` | `app/config.py`, `app/hr/services/email_smtp.py` |
| `GMAIL_APP_PASSWORD` | gmail-email | segreta | `Optional[str]` / valore non riportato | `app/config.py`, `app/hr/services/email_smtp.py` |
| `GMAIL_APP_PASSWORD_AMMINISTRATIVO` | gmail-email | segreta | `Optional[str]` / valore non riportato | `app/config.py` |
| `GMAIL_EMAIL` | gmail-email | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GMAIL_IMAP_ENABLED` | gmail-email | configurazione | `bool` / `False` | `app/config.py` |
| `GMAIL_RELAY_SECRET` | gmail-email | segreta | non dichiarato in Settings | `app/hr/services/email_smtp.py` |
| `GMAIL_RELAY_URL` | gmail-email | configurazione | non dichiarato in Settings | `app/hr/services/email_smtp.py` |
| `GOOGLE_API_KEY` | ai | segreta | `Optional[str]` / valore non riportato | `app/config.py` |
| `GOOGLE_CLIENT_ID` | app-runtime | configurazione | `Optional[str]` / `None` | `app/config.py`, `app/lotti/auth.py` |
| `GOOGLE_CLIENT_SECRET` | app-runtime | segreta | `Optional[str]` / valore non riportato | `app/config.py` |
| `GOOGLE_DRIVE_AVVISI_BONARI_FOLDER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_DRIVE_BONIFICI_FOLDER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_DRIVE_CARTELLE_ESATTORIALI_FOLDER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_DRIVE_CEDOLINI_FOLDER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_DRIVE_CORRISPETTIVI_FOLDER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_DRIVE_DICHIARAZIONI_IVA_FOLDER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_DRIVE_DOCUMENT_INDEX_FILE_ID` | drive-sheets | configurazione | non dichiarato in Settings | `render_workflows/document_ingest.py` |
| `GOOGLE_DRIVE_ESTRATTI_FOLDER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_DRIVE_ESTRATTI_FOLDER_IDS` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_DRIVE_FATTURE_FOLDER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_DRIVE_INBOX_FOLDER_ID` | drive-sheets | configurazione | non dichiarato in Settings | `render_workflows/calderone.py`, `render_workflows/document_ingest.py` |
| `GOOGLE_DRIVE_QUIETANZE_FOLDER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_DRIVE_SA_FILE` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_DRIVE_SA_JSON` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py`, `app/hr/services/google_drive_sa.py` |
| `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py`, `app/hr/services/google_drive_sa.py`, `render.yaml`, `render_workflows/calderone.py`, `render_workflows/document_ingest.py` |
| `GOOGLE_REDIRECT_URI` | app-runtime | configurazione | `str` / `'/api/auth/google/callback'` | `app/config.py` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | drive-sheets | configurazione | non dichiarato in Settings | `app/hr/services/google_drive_sa.py` |
| `GOOGLE_SERVICE_ACCOUNT_JSON_BONIFICI` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_SERVICE_ACCOUNT_JSON_CEDOLINI` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_SERVICE_ACCOUNT_JSON_CORRISPETTIVI` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_SERVICE_ACCOUNT_JSON_ESTRATTI_CONTO` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_SERVICE_ACCOUNT_JSON_FATTURE` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_SERVICE_ACCOUNT_JSON_QUIETANZE` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_SHEETS_LEDGER_FOLDER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py` |
| `GOOGLE_SHEETS_LEDGER_ID` | drive-sheets | configurazione | `Optional[str]` / `None` | `app/config.py`, `render.yaml` |
| `HOST` | app-runtime | configurazione | `str` / `'0.0.0.0'` | `app/config.py` |
| `HR_ADMIN_EMAIL` | app-runtime | configurazione | non dichiarato in Settings | `app/hr/routers/auth.py` |
| `HR_ADMIN_PASSWORD` | app-runtime | segreta | non dichiarato in Settings | `app/hr/routers/auth.py` |
| `HR_ADMIN_PASSWORD_HASH` | app-runtime | segreta | non dichiarato in Settings | `app/hr/routers/auth.py` |
| `HR_ADMIN_TOKEN_EXPIRE_MINUTES` | app-runtime | segreta | non dichiarato in Settings | `app/hr/routers/pin_login.py` |
| `HR_JWT_SECRET` | app-runtime | segreta | non dichiarato in Settings | `app/hr/routers/auth.py`, `render.yaml` |
| `HR_PIN_CODE` | app-runtime | segreta | non dichiarato in Settings | `render.yaml` |
| `HR_SUPABASE_DB_URL` | app-runtime | configurazione | non dichiarato in Settings | `render.yaml` |
| `IMAP_EMAIL` | gmail-email | configurazione | non dichiarato in Settings | `app/hr/routers/dipendenti_cloud/__init__.py` |
| `IMAP_HOST` | gmail-email | configurazione | `str` / `'imap.gmail.com'` | `app/config.py`, `app/hr/routers/dipendenti_cloud/__init__.py`, `app/routers/settings_router.py`, `app/services/pagopa_scanner.py` |
| `IMAP_PASS` | gmail-email | configurazione | non dichiarato in Settings | `app/hr/routers/dipendenti_cloud/__init__.py` |
| `IMAP_PASSWORD` | gmail-email | segreta | `Optional[str]` / valore non riportato | `app/config.py`, `app/hr/routers/cedolini.py`, `app/hr/routers/dipendenti_cloud/__init__.py`, `app/routers/settings_router.py`, `app/services/pagopa_scanner.py` |
| `IMAP_PORT` | gmail-email | configurazione | `int` / `993` | `app/config.py`, `app/hr/routers/dipendenti_cloud/__init__.py`, `app/services/pagopa_scanner.py` |
| `IMAP_SERVER` | gmail-email | configurazione | `Optional[str]` / `None` | `app/config.py`, `app/hr/routers/dimissioni.py`, `app/hr/routers/dipendenti_cloud/__init__.py`, `app/routers/learning_machine.py`, `app/services/email_full_download.py`, `app/services/verbali_email_scanner.py` |
| `IMAP_USER` | gmail-email | configurazione | `Optional[str]` / `None` | `app/config.py`, `app/hr/routers/cedolini.py`, `app/hr/routers/dipendenti_cloud/__init__.py`, `app/routers/settings_router.py`, `app/services/pagopa_scanner.py` |
| `IVA_ALIQUOTE` | app-runtime | configurazione | `list[float]` / `[4.0, 5.0, 10.0, 22.0]` | `app/config.py` |
| `JWT_SECRET` | app-runtime | segreta | non dichiarato in Settings | `app/menu/routes/qrcode_routes.py` |
| `LOCALAPPDATA` | app-runtime | configurazione | non dichiarato in Settings | `scripts/sync_rt_to_drive.py` |
| `LOG_FILE` | app-runtime | configurazione | `Optional[Path]` / `None` | `app/config.py` |
| `LOG_FORMAT` | app-runtime | configurazione | `str` / `'json'` | `app/config.py` |
| `LOG_LEVEL` | app-runtime | configurazione | `str` / `'INFO'` | `app/config.py` |
| `LOTTI_ADMIN_PIN` | app-runtime | segreta | non dichiarato in Settings | `app/lotti/scripts/associa_immagini_ricettario.py` |
| `LOTTI_AUTH_SECRET` | app-runtime | segreta | non dichiarato in Settings | `app/lotti/auth.py`, `render.yaml` |
| `LOTTI_DB_NAME` | app-runtime | configurazione | non dichiarato in Settings | `app/lotti/db.py`, `app/lotti/routers/diagnostic.py`, `app/lotti/supabase_document_store.py` |
| `LOTTI_DB_SECRET` | app-runtime | segreta | non dichiarato in Settings | `app/lotti/auth.py`, `app/lotti/scripts/migrate_recovered_json_to_supabase.py`, `app/lotti/supabase_document_store.py`, `render.yaml` |
| `LOTTI_INTEGRATION_KEY` | app-runtime | configurazione | non dichiarato in Settings | `app/lotti/routers/gestionale_fatture.py`, `app/lotti/routers/tablet_operatori.py`, `app/middleware/authentication.py`, `app/routers/lotti_integration.py`, `render.yaml` |
| `LOTTI_SUPABASE_ANON_KEY` | app-runtime | configurazione | non dichiarato in Settings | `app/lotti/scripts/migrate_recovered_json_to_supabase.py`, `app/lotti/supabase_document_store.py`, `render.yaml` |
| `LOTTI_SUPABASE_URL` | app-runtime | configurazione | non dichiarato in Settings | `app/lotti/db.py`, `app/lotti/scripts/migrate_recovered_json_to_supabase.py`, `app/lotti/supabase_document_store.py`, `render.yaml` |
| `MAX_CONCURRENT_IMPORTS` | app-runtime | configurazione | `int` / `5` | `app/config.py` |
| `MAX_UPLOAD_SIZE_MB` | app-runtime | configurazione | `int` / `50` | `app/config.py` |
| `MENU_ADMIN_PASSWORD` | app-runtime | segreta | non dichiarato in Settings | `app/menu/routes/qrcode_routes.py`, `render.yaml` |
| `MENU_ADMIN_USERNAME` | app-runtime | configurazione | non dichiarato in Settings | `app/menu/routes/qrcode_routes.py`, `render.yaml` |
| `MENU_JWT_SECRET` | app-runtime | segreta | non dichiarato in Settings | `app/menu/routes/qrcode_routes.py`, `render.yaml` |
| `MENU_SUPABASE_KEY` | app-runtime | configurazione | non dichiarato in Settings | `render.yaml` |
| `MENU_SUPABASE_URL` | app-runtime | configurazione | non dichiarato in Settings | `app/lotti/servizi/menu_bridge.py`, `render.yaml` |
| `MONGO_URL` | app-runtime | configurazione | non dichiarato in Settings | `app/lotti/scripts/fix_fornitori_acquaviva.py`, `app/lotti/scripts/import_acquaviva_definitivo.py`, `app/lotti/scripts/import_listino_2026.py`, `app/lotti/scripts/import_ricette_excel.py`, `app/lotti/scripts/scrape_acquaviva_images.py`, `app/lotti/scripts/scrape_vandemoortele_acquaviva.py`, `app/lotti/tests/test_iteration54_features.py`, `app/lotti/utils/shared.py` |
| `NODE_ENV` | app-runtime | configurazione | non dichiarato in Settings | `frontend/plugins/health-check/health-endpoints.js`, `frontend_lotti/craco.config.js` |
| `NOLEGGIO_GIORNI_SENZA_FATTURA` | feature-job | configurazione | non dichiarato in Settings | `app/services/noleggio/controlli.py` |
| `OPENAI_API_KEY` | ai | segreta | `Optional[str]` / valore non riportato | `app/config.py`, `app/routers/settings_router.py`, `app/services/chat_ai_engine.py` |
| `OPENAI_MODEL` | ai | configurazione | non dichiarato in Settings | `app/routers/settings_router.py`, `app/services/chat_ai_engine.py` |
| `OPENAPI_COMPANY_TOKEN` | integrazioni | segreta | non dichiarato in Settings | `app/routers/openapi_automotive.py`, `app/routers/openapi_imprese.py` |
| `OPENAPI_IMPRESE_TOKEN` | integrazioni | segreta | `Optional[str]` / valore non riportato | `app/config.py` |
| `OPENAPI_IT_ENV` | integrazioni | configurazione | `str` / `'production'` | `app/config.py`, `app/routers/openapi_it.py` |
| `OPENAPI_IT_KEY` | integrazioni | configurazione | `Optional[str]` / `None` | `app/config.py`, `app/routers/openapi_it.py` |
| `OUT_DIR` | test-tooling | configurazione | non dichiarato in Settings | `scripts/collaudo_ui.mjs` |
| `PAYPAL_CLIENT_ID` | integrazioni | configurazione | `str` / `''` | `app/config.py`, `app/hr/routers/contabilita.py`, `app/services/paypal_integration.py` |
| `PAYPAL_CLIENT_SECRET` | integrazioni | segreta | `str` / valore non riportato | `app/config.py`, `app/hr/routers/contabilita.py` |
| `PAYPAL_ENV` | integrazioni | configurazione | non dichiarato in Settings | `app/hr/routers/contabilita.py` |
| `PAYPAL_MODE` | integrazioni | configurazione | non dichiarato in Settings | `app/services/paypal_integration.py` |
| `PAYPAL_SECRET_KEY` | integrazioni | segreta | non dichiarato in Settings | `app/services/paypal_integration.py` |
| `PAYPAL_WEBHOOK_ID` | integrazioni | configurazione | non dichiarato in Settings | `app/routers/paypal_api.py` |
| `PEC_DEST` | app-runtime | configurazione | non dichiarato in Settings | `app/hr/routers/portale_buste.py` |
| `PEC_HOST` | app-runtime | configurazione | non dichiarato in Settings | `app/hr/routers/portale_buste.py`, `app/hr/services/email_smtp.py` |
| `PEC_PASSWORD` | app-runtime | segreta | non dichiarato in Settings | `app/hr/routers/portale_buste.py`, `app/hr/services/email_smtp.py` |
| `PEC_PORT` | app-runtime | configurazione | non dichiarato in Settings | `app/hr/routers/portale_buste.py`, `app/hr/services/email_smtp.py` |
| `PEC_USER` | app-runtime | configurazione | non dichiarato in Settings | `app/hr/routers/portale_buste.py`, `app/hr/services/email_smtp.py` |
| `PIN_HASH_ADMIN` | sicurezza | segreta | non dichiarato in Settings | `app/routers/pin_login.py` |
| `PLAYWRIGHT_CHROMIUM` | app-runtime | configurazione | non dichiarato in Settings | `frontend/scripts/audit-destructive-e2e.cjs`, `frontend/scripts/audit-layout.cjs`, `frontend/scripts/audit-operation-index.cjs`, `frontend/scripts/audit-pages-e2e.cjs`, `frontend/scripts/audit-viewer.cjs` |
| `PORT` | app-runtime | configurazione | `int` / `8000` | `app/config.py` |
| `POS_ACCREDITO_WEEKEND` | feature-job | configurazione | non dichiarato in Settings | `app/utils/pos_accredito.py` |
| `PROCESS_ROLE` | app-runtime | configurazione | non dichiarato in Settings | `app/main.py`, `render.yaml` |
| `PUBLIC_URL` | app-runtime | configurazione | non dichiarato in Settings | `frontend_lotti/src/components/haccp/ManualeView.jsx`, `frontend_lotti/src/components/haccp/RegistroAllergeniView.jsx`, `frontend_menu/src/App.js`, `frontend_menu/src/pages/AdminDashboard.jsx`, `frontend_menu/src/pages/HomePage.jsx` |
| `PYTHONUTF8` | app-runtime | configurazione | non dichiarato in Settings | `render.yaml` |
| `PYTHON_VERSION` | app-runtime | configurazione | non dichiarato in Settings | `render.yaml` |
| `REACT_APP_BACKEND_URL` | app-runtime | configurazione | non dichiarato in Settings | `app/lotti/routers/manuale_haccp.py`, `app/lotti/tests/conftest.py`, `app/lotti/tests/test_email_ordini_iter66.py`, `app/lotti/tests/test_giacenze_iter69.py`, `app/lotti/tests/test_iteration46_features.py`, `app/lotti/tests/test_iteration47_features.py`, `app/lotti/tests/test_iteration48_features.py`, `app/lotti/tests/test_iteration52_features.py`, `app/lotti/tests/test_iteration53_features.py`, `app/lotti/tests/test_iteration55_bugfixes.py`, `app/lotti/tests/test_iteration56_nutritional.py`, `app/lotti/tests/test_iteration57_bom.py`, `app/lotti/tests/test_iteration72_bugfixes.py`, `app/lotti/tests/test_magazzino_bar_iter68.py`, `app/lotti/tests/test_magazzino_unificato_iter71.py`, `app/lotti/tests/test_ordini_fornitori.py`, `app/lotti/tests/test_ordini_fornitori_iter70.py`, `app/lotti/tests/test_p1_p2_features.py`, `app/lotti/tests/test_prezzi_alert_iter67.py`, `backend/tests/test_fase2_fase3_fase4.py`, `frontend_lotti/src/App.js`, `frontend_lotti/src/components/haccp/BackofficeView.jsx`, `frontend_lotti/src/components/haccp/ControlloOlioView.jsx`, `frontend_lotti/src/components/haccp/CorrispettiviView.jsx`, `frontend_lotti/src/components/haccp/ListinoView.jsx`, `frontend_lotti/src/components/haccp/MagazzinoBarView.jsx`, `frontend_lotti/src/components/haccp/ProdottiVenditaView.jsx`, `frontend_lotti/src/components/haccp/RicetteDashboardView.jsx`, `frontend_lotti/src/components/haccp/RicezioneMerceView.jsx`, `frontend_lotti/src/components/haccp/SaimaRicettariView.jsx`, `frontend_lotti/src/components/haccp/TabletHome.jsx`, `frontend_lotti/src/components/haccp/TabletView.jsx`, `frontend_lotti/src/components/haccp/TemperatureCotturaView.jsx`, `frontend_lotti/src/components/haccp/backoffice/FormRicetta.jsx`, `frontend_lotti/src/components/haccp/backoffice/TabFornitori.jsx`, `frontend_lotti/src/components/haccp/backoffice/TabProdotti.jsx`, `frontend_lotti/src/components/haccp/lotti/ModalDettaglioLotto.jsx`, `frontend_lotti/src/utils/constants.js`, `frontend_menu/src/components/CartDrawer.jsx`, `frontend_menu/src/components/admin/BackupManager.jsx`, `frontend_menu/src/components/admin/ImageUploadManager.jsx`, `frontend_menu/src/components/admin/ProductManager.jsx`, `frontend_menu/src/context/CartContext.jsx`, `frontend_menu/src/context/MenuContext.jsx`, `frontend_menu/src/hooks/useAdminAuth.js`, `frontend_menu/src/pages/AdminDashboard.jsx`, `frontend_menu/src/pages/AdminLoginPage.jsx`, `frontend_menu/src/pages/AdminQRCodePage.jsx`, `frontend_menu/src/pages/admin/CounterPage.jsx`, `frontend_menu/src/pages/admin/KitchenMonitorPage.jsx`, `frontend_menu/src/pages/admin/OrdersPage.jsx`, `frontend_menu/src/pages/admin/SalePage.jsx`, `frontend_menu/src/pages/admin/WarehousePage.jsx` |
| `REACT_APP_GESTIONALE_URL` | app-runtime | configurazione | non dichiarato in Settings | `frontend_lotti/src/layouts/AppLayout.jsx` |
| `RELOAD` | app-runtime | configurazione | `bool` / `False` | `app/config.py` |
| `RENDER` | app-runtime | configurazione | non dichiarato in Settings | `app/main.py`, `app/utils/session_cookie.py` |
| `RENDER_EXTERNAL_URL` | app-runtime | configurazione | non dichiarato in Settings | `app/lotti/routers/scheduler.py` |
| `RENDER_GIT_COMMIT` | app-runtime | configurazione | non dichiarato in Settings | `app/main.py` |
| `RENDER_INGEST_SHARED_SECRET` | app-runtime | segreta | `Optional[str]` / valore non riportato | `app/config.py`, `render_workflows/document_ingest.py` |
| `RENDER_SERVICE_ID` | app-runtime | configurazione | non dichiarato in Settings | `app/main.py`, `app/utils/session_cookie.py` |
| `REQUEST_NOTIFY_EMAIL` | app-runtime | configurazione | non dichiarato in Settings | `app/hr/routers/richieste.py` |
| `REQUEST_TIMEOUT_SECONDS` | app-runtime | configurazione | `int` / `300` | `app/config.py` |
| `RT_DRIVE_INBOX` | app-runtime | configurazione | non dichiarato in Settings | `scripts/sync_rt_to_drive.py` |
| `RT_LOCAL_BASE_URL` | app-runtime | configurazione | non dichiarato in Settings | `scripts/sync_rt_to_drive.py` |
| `RT_SYNC_STATE_FILE` | app-runtime | configurazione | non dichiarato in Settings | `scripts/sync_rt_to_drive.py` |
| `RUN_STARTUP_DATA_REPAIRS` | feature-job | configurazione | `bool` / `False` | `app/config.py` |
| `RUN_STARTUP_INDEX_MIGRATIONS` | feature-job | configurazione | `bool` / `False` | `app/config.py` |
| `RUN_STARTUP_SEED_DATA` | feature-job | configurazione | `bool` / `False` | `app/config.py` |
| `SCHEDULER_LEASE_SECONDS` | feature-job | configurazione | `int` / `21600` | `app/config.py` |
| `SECRET_KEY` | sicurezza | segreta | `Optional[str]` / valore non riportato | `app/config.py`, `app/hr/routers/auth.py`, `app/routers/auth.py`, `scripts/e2e_distruttivo_server.py` |
| `SHEETS_REGISTRY_NAME` | app-runtime | configurazione | `str` / `'GestionaleCloud'` | `app/config.py`, `render.yaml` |
| `SMOKE_ANNO` | test-tooling | configurazione | non dichiarato in Settings | `scripts/smoke_app.py` |
| `SMOKE_AUTH_TOKEN` | test-tooling | segreta | non dichiarato in Settings | `scripts/smoke_app.py` |
| `SMOKE_DEPLOY_POLL_SECONDS` | test-tooling | configurazione | non dichiarato in Settings | `scripts/smoke_app.py` |
| `SMOKE_DEPLOY_WAIT_SECONDS` | test-tooling | configurazione | non dichiarato in Settings | `scripts/smoke_app.py` |
| `SMOKE_EXPECTED_COMMIT` | test-tooling | configurazione | non dichiarato in Settings | `scripts/smoke_app.py` |
| `SMOKE_TIMEOUT` | test-tooling | configurazione | non dichiarato in Settings | `scripts/smoke_app.py` |
| `SMTP_EMAIL` | gmail-email | configurazione | non dichiarato in Settings | `app/hr/routers/employees/employee_contracts.py`, `app/hr/routers/portale_buste.py`, `app/hr/services/email_smtp.py` |
| `SMTP_ENABLED` | gmail-email | configurazione | `bool` / `False` | `app/config.py` |
| `SMTP_FROM_EMAIL` | gmail-email | configurazione | `Optional[str]` / `None` | `app/config.py`, `app/routers/commercialista.py` |
| `SMTP_HOST` | gmail-email | configurazione | `Optional[str]` / `None` | `app/config.py`, `app/hr/routers/employees/employee_contracts.py`, `app/hr/routers/portale_buste.py`, `app/hr/services/email_smtp.py`, `app/routers/commercialista.py` |
| `SMTP_PASSWORD` | gmail-email | segreta | `Optional[str]` / valore non riportato | `app/config.py`, `app/hr/routers/employees/employee_contracts.py`, `app/hr/routers/portale_buste.py`, `app/hr/services/email_smtp.py`, `app/routers/commercialista.py` |
| `SMTP_PORT` | gmail-email | configurazione | `Optional[int]` / `587` | `app/config.py`, `app/hr/routers/employees/employee_contracts.py`, `app/hr/routers/portale_buste.py`, `app/hr/services/email_smtp.py`, `app/routers/commercialista.py` |
| `SMTP_USER` | gmail-email | configurazione | `Optional[str]` / `None` | `app/config.py`, `app/hr/routers/employees/employee_contracts.py`, `app/hr/routers/portale_buste.py`, `app/hr/services/email_smtp.py`, `app/routers/commercialista.py` |
| `SMTP_USERNAME` | gmail-email | configurazione | `Optional[str]` / `None` | `app/config.py`, `app/routers/commercialista.py` |
| `STATIC_FILES_DIR` | app-runtime | configurazione | `Path` / `Path('static')` | `app/config.py` |
| `SUMUP_API_BASE` | integrazioni | configurazione | `str` / `'https://api.sumup.com'` | `app/config.py` |
| `SUMUP_API_KEY` | integrazioni | segreta | `str` / valore non riportato | `app/config.py`, `render.yaml` |
| `SUMUP_MERCHANT_CODE` | integrazioni | configurazione | `str` / `''` | `app/config.py`, `render.yaml` |
| `SUPABASE_PUBLISHABLE_KEY` | app-runtime | configurazione | `Optional[str]` / `None` | `app/config.py`, `render.yaml` |
| `SUPABASE_RUNTIME_SECRET` | app-runtime | segreta | `Optional[str]` / valore non riportato | `app/config.py`, `render.yaml` |
| `SUPABASE_URL` | app-runtime | configurazione | `Optional[str]` / `None` | `app/config.py`, `render.yaml` |
| `TELEGRAM_BOT_TOKEN` | integrazioni | segreta | `Optional[str]` / valore non riportato | `app/config.py`, `app/services/telegram_notifications.py` |
| `TELEGRAM_CHAT_ID` | integrazioni | configurazione | `Optional[str]` / `None` | `app/config.py`, `app/services/telegram_notifications.py` |
| `TEMPLATES_DIR` | app-runtime | configurazione | `Path` / `Path('templates')` | `app/config.py` |
| `TEST_PIN_ADMIN` | app-runtime | segreta | non dichiarato in Settings | `app/lotti/tests/test_iteration72_bugfixes.py` |
| `TEST_PIN_OP1` | app-runtime | segreta | non dichiarato in Settings | `app/lotti/tests/test_iteration72_bugfixes.py`, `app/lotti/tests/test_magazzino_bar_iter68.py` |
| `TEST_PIN_OP2` | app-runtime | segreta | non dichiarato in Settings | `app/lotti/tests/test_iteration72_bugfixes.py` |
| `UPLOAD_FOLDER` | app-runtime | configurazione | `Path` / `Path('uploads')` | `app/config.py` |
| `VERBALE_TEST_ID` | test-tooling | configurazione | non dichiarato in Settings | `scripts/collaudo_ui.mjs` |
| `VERBALI_EMAIL_SCAN_HOUR` | feature-job | configurazione | `int` / `6` | `app/config.py` |
| `VITE_API_URL` | app-runtime | configurazione | non dichiarato in Settings | `frontend_hr/src/PortaleDipendente.jsx` |
| `VITE_BACKEND_URL` | app-runtime | configurazione | non dichiarato in Settings | `frontend/vite.config.js` |

Regole: alias duplicati Drive/email vanno migrati verso un nome canonico e poi rimossi; una variabile senza consumer non va mantenuta; tutte le variabili `transitorie-vietate-nel-target` sono escluse dalla ricostruzione Drive-only.

## Appendice C.1 — Tutte le cartelle Drive configurabili

Questa tabella è l'inventario canonico degli alias di cartella. Gli ID sono configurazione, non identità di dominio: ogni alias deve puntare a una sola cartella e ogni cartella deve avere manifest, provenienza e permessi verificati.

| Variabile cartella | Default dichiarato | Sorgenti/consumer |
|---|---|---|
| `DRIVE_BONIFICI_FOLDER_ID` | `non dichiarato` | `app/hr/routers/dipendenti_cloud/__init__.py` |
| `DRIVE_CARTE_FOLDER_ID` | `None` | `app/config.py` |
| `DRIVE_CEDOLINI_FOLDER_ID` | `non dichiarato` | `app/hr/services/google_drive_sa.py` |
| `DRIVE_DOCUMENT_INDEX_ROOT_FOLDER_ID` | `'1tmVu6fl7qhJbLcGCHT3wEQzrvFAElc9h'` | `app/config.py` |
| `DRIVE_F24_FOLDER_ID` | `None` | `app/config.py` |
| `DRIVE_FISCAL_ROOT_FOLDER_ID` | `'1f48bounfoOyHL_kqpHAp2GAnFfEpHvVa'` | `app/config.py` |
| `DRIVE_FOLDER_REGISTRY_JSON` | `None` | `app/config.py` |
| `DRIVE_NOLEGGIO_FOLDER_ID` | `None` | `app/config.py` |
| `DRIVE_PAYPAL_FOLDER_ID` | `None` | `app/config.py` |
| `DRIVE_PRESENZE_FOLDER_ID` | `None` | `app/config.py` |
| `DRIVE_VERBALI_FOLDER_ID` | `None` | `app/config.py` |
| `GOOGLE_DRIVE_AVVISI_BONARI_FOLDER_ID` | `None` | `app/config.py` |
| `GOOGLE_DRIVE_BONIFICI_FOLDER_ID` | `None` | `app/config.py` |
| `GOOGLE_DRIVE_CARTELLE_ESATTORIALI_FOLDER_ID` | `None` | `app/config.py` |
| `GOOGLE_DRIVE_CEDOLINI_FOLDER_ID` | `None` | `app/config.py` |
| `GOOGLE_DRIVE_CORRISPETTIVI_FOLDER_ID` | `None` | `app/config.py` |
| `GOOGLE_DRIVE_DICHIARAZIONI_IVA_FOLDER_ID` | `None` | `app/config.py` |
| `GOOGLE_DRIVE_ESTRATTI_FOLDER_ID` | `None` | `app/config.py` |
| `GOOGLE_DRIVE_ESTRATTI_FOLDER_IDS` | `None` | `app/config.py` |
| `GOOGLE_DRIVE_FATTURE_FOLDER_ID` | `None` | `app/config.py` |
| `GOOGLE_DRIVE_INBOX_FOLDER_ID` | `non dichiarato` | `render_workflows/calderone.py`, `render_workflows/document_ingest.py` |
| `GOOGLE_DRIVE_QUIETANZE_FOLDER_ID` | `None` | `app/config.py` |

Gli alias senza valore vanno configurati nel secret/config store di Render. Non creare cartelle parallele per aggirare un alias mancante; risolvere e documentare la cartella canonica.

## Appendice D — Tutti i router e tutti gli endpoint

Route table sorgente: **1149**; attivi da ricreare: **747**; quarantena: **402** (`verificare` 372, `admin-only` 30).

`attivo` significa da ricreare con contratto e test; `quarantena` significa non esporre nel nuovo runtime finché consumer, autorizzazione e test non sono provati. L'elenco è completo e include entrambe le categorie.

### Router `accounting.bilancio` (7)

- **quarantena: verificare** — `GET /api/bilancio/confronto-annuale` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/bilancio/conto-economico` — in uso: FE
- **quarantena: verificare** — `GET /api/bilancio/conto-economico-dettagliato` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/bilancio/export-pdf` — in uso: FE
- **attivo** — `GET /api/bilancio/export/pdf/confronto` — in uso: FE
- **attivo** — `GET /api/bilancio/riepilogo` — in uso: chat
- **attivo** — `GET /api/bilancio/stato-patrimoniale` — in uso: FE

### Router `accounting.centri_costo` (10)

- **attivo** — `GET /api/centri-costo` — in uso: FE
- **attivo** — `POST /api/centri-costo` — in uso: FE
- **quarantena: verificare** — `POST /api/centri-costo/assegna-cdc-fatture` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/centri-costo/mapping-categorie` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/centri-costo/ribaltamento/calcola` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/centri-costo/ribaltamento/quote-ricavo` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/centri-costo/utile-obiettivo` — in uso: FE
- **attivo** — `POST /api/centri-costo/utile-obiettivo` — in uso: FE
- **attivo** — `GET /api/centri-costo/utile-obiettivo/per-cdc` — in uso: FE
- **attivo** — `GET /api/centri-costo/utile-obiettivo/suggerimenti` — in uso: FE

### Router `accounting.contabilita_avanzata` (9)

- **attivo** — `GET /api/contabilita/aliquote-irap` — in uso: FE
- **attivo** — `GET /api/contabilita/bilancio-dettagliato` — in uso: FE
- **attivo** — `GET /api/contabilita/calcolo-imposte` — in uso: FE
- **quarantena: verificare** — `GET /api/contabilita/categorizzazione-preview` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/contabilita/export/pdf-dichiarazione` — in uso: FE
- **quarantena: admin-only** — `POST /api/contabilita/inizializza-piano-esteso` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: verificare** — `GET /api/contabilita/piano-conti-esteso` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/contabilita/ricategorizza-fatture` — in uso: FE
- **attivo** — `GET /api/contabilita/statistiche-categorizzazione` — in uso: FE

### Router `accounting.contabilita_gestionale` (14)

- **attivo** — `GET /api/contabilita-gestionale/bilancio-verifica` — in uso: FE
- **attivo** — `POST /api/contabilita-gestionale/budget` — in uso: FE
- **attivo** — `GET /api/contabilita-gestionale/budget-vs-consuntivo/{anno}` — in uso: FE
- **attivo** — `POST /api/contabilita-gestionale/budget/duplica/{anno_origine}/{anno_destinazione}` — in uso: FE
- **attivo** — `GET /api/contabilita-gestionale/budget/{anno}` — in uso: FE
- **attivo** — `DELETE /api/contabilita-gestionale/budget/{anno}/{voce}` — in uso: FE
- **attivo** — `GET /api/contabilita-gestionale/libro-giornale` — in uso: FE
- **attivo** — `GET /api/contabilita-gestionale/libro-giornale/controllo-60-giorni` — in uso: FE
- **attivo** — `GET /api/contabilita-gestionale/libro-giornale/export` — in uso: FE
- **attivo** — `POST /api/contabilita-gestionale/libro-giornale/import` — in uso: FE
- **attivo** — `GET /api/contabilita-gestionale/libro-mastro` — in uso: FE
- **quarantena: verificare** — `GET /api/contabilita-gestionale/partitario/clienti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/contabilita-gestionale/partitario/fornitori` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/contabilita-gestionale/partitario/fornitori/{piva}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `accounting.piano_conti` (12)

- **attivo** — `GET /api/piano-conti/` — in uso: FE
- **attivo** — `POST /api/piano-conti/` — in uso: FE
- **attivo** — `GET /api/piano-conti/bilancio` — in uso: FE
- **attivo** — `GET /api/piano-conti/conto/{codice}/movimenti` — in uso: FE
- **attivo** — `GET /api/piano-conti/movimenti` — in uso: FE
- **attivo** — `POST /api/piano-conti/registra-corrispettivi` — in uso: FE
- **attivo** — `POST /api/piano-conti/registra-fattura` — in uso: FE
- **attivo** — `POST /api/piano-conti/registra-tutte-fatture` — in uso: FE
- **attivo** — `GET /api/piano-conti/regole` — in uso: FE
- **attivo** — `POST /api/piano-conti/regole` — in uso: FE
- **attivo** — `DELETE /api/piano-conti/{conto_id}` — in uso: FE
- **attivo** — `PUT /api/piano-conti/{conto_id}` — in uso: FE

### Router `accounting.prima_nota_salari` (21)

- **quarantena: verificare** — `POST /api/prima-nota-salari/consolida-record` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: admin-only** — `POST /api/prima-nota-salari/deposita-cedolini-in-hr` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **attivo** — `GET /api/prima-nota-salari/dipendenti-lista` — in uso: FE
- **quarantena: verificare** — `GET /api/prima-nota-salari/export-excel` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/prima-nota-salari/import-bonifici` — in uso: FE
- **attivo** — `POST /api/prima-nota-salari/import-paghe` — in uso: FE
- **quarantena: verificare** — `POST /api/prima-nota-salari/import-salari-ricostruiti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/prima-nota-salari/import-salari-verificati` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `DELETE /api/prima-nota-salari/pulisci-righe-vuote` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/prima-nota-salari/ricalcola-progressivi` — in uso: FE
- **attivo** — `GET /api/prima-nota-salari/salari` — in uso: FE
- **attivo** — `POST /api/prima-nota-salari/salari/aggiustamento` — in uso: FE
- **quarantena: admin-only** — `DELETE /api/prima-nota-salari/salari/reset` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **attivo** — `GET /api/prima-nota-salari/salari/riepilogo` — in uso: FE
- **attivo** — `DELETE /api/prima-nota-salari/salari/{record_id}` — in uso: FE
- **attivo** — `PUT /api/prima-nota-salari/salari/{record_id}` — in uso: FE
- **attivo** — `GET /api/prima-nota-salari/salari/{record_id}/bonifico-pdf` — in uso: FE
- **attivo** — `POST /api/prima-nota-salari/salari/{record_id}/bonifico-pdf` — in uso: FE
- **attivo** — `GET /api/prima-nota-salari/salari/{record_id}/cedolino-pdf` — in uso: FE
- **attivo** — `POST /api/prima-nota-salari/salari/{record_id}/cedolino-pdf` — in uso: FE
- **attivo** — `PUT /api/prima-nota-salari/salari/{record_id}/riconcilia` — in uso: FE

### Router `accounting.regole_categorizzazione` (7)

- **attivo** — `GET /api/regole` — in uso: FE
- **attivo** — `POST /api/regole/categorie` — in uso: FE
- **attivo** — `POST /api/regole/descrizione` — in uso: FE
- **attivo** — `GET /api/regole/download-regole` — in uso: FE
- **attivo** — `DELETE /api/regole/elimina/{tipo}/{pattern}` — in uso: FE
- **attivo** — `POST /api/regole/fornitore` — in uso: FE
- **attivo** — `POST /api/regole/upload-regole` — in uso: FE

### Router `admin` (26)

- **attivo** — `GET /api/admin/bank-supplier-rules` — in uso: FE
- **attivo** — `POST /api/admin/bank-supplier-rules` — in uso: FE
- **attivo** — `POST /api/admin/bank-supplier-rules/reprocess/{year}` — in uso: FE
- **attivo** — `DELETE /api/admin/bank-supplier-rules/{rule_id}` — in uso: FE
- **quarantena: verificare** — `POST /api/admin/bonifica-prima-nota-doppioni` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: admin-only** — `DELETE /api/admin/cleanup-trattenute-disciplinari` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: verificare** — `GET /api/admin/collections` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/admin/dashboard-summary` — in uso: FE
- **attivo** — `GET /api/admin/google-sheets-ledger/config` — in uso: FE
- **attivo** — `POST /api/admin/google-sheets-ledger/config` — in uso: FE
- **attivo** — `GET /api/admin/google-sheets-ledger/duplicate-audit` — in uso: FE
- **attivo** — `POST /api/admin/google-sheets-ledger/duplicate-audit-folders` — in uso: FE
- **quarantena: admin-only** — `POST /api/admin/google-sheets-ledger/duplicate-cleanup-folders` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **attivo** — `POST /api/admin/google-sheets-ledger/jobs/{action}` — in uso: FE
- **attivo** — `GET /api/admin/google-sheets-ledger/jobs/{job_id}` — in uso: FE
- **attivo** — `GET /api/admin/google-sheets-ledger/manifest` — in uso: FE
- **quarantena: admin-only** — `GET /api/admin/google-sheets-ledger/migration-audit` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **attivo** — `POST /api/admin/google-sheets-ledger/restore` — in uso: FE
- **attivo** — `POST /api/admin/google-sheets-ledger/sync` — in uso: FE
- **quarantena: admin-only** — `POST /api/admin/noleggio/backfill-dati-gestionali` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: admin-only** — `POST /api/admin/reset-collections` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **attivo** — `GET /api/admin/stats` — in uso: FE
- **quarantena: admin-only** — `POST /api/admin/supabase-migration/jobs` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: admin-only** — `GET /api/admin/supabase-migration/jobs/{job_id}` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: verificare** — `GET /api/admin/year-opening-balances/{year}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `PUT /api/admin/year-opening-balances/{year}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `admin_export` (2)

- **quarantena: verificare** — `GET /api/admin/export` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/admin/export/{filename}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `admin_rollback` (7)

- **attivo** — `POST /api/admin/rollback/drive-fatture/conta` — in uso: FE
- **attivo** — `POST /api/admin/rollback/drive-fatture/elimina` — in uso: FE
- **attivo** — `POST /api/admin/rollback/fatture/azzera-tutto` — in uso: FE
- **attivo** — `GET /api/admin/rollback/fatture/azzera-tutto/conta` — in uso: FE
- **attivo** — `GET /api/admin/rollback/sezioni` — in uso: FE
- **attivo** — `DELETE /api/admin/rollback/{sezione}` — in uso: FE
- **attivo** — `GET /api/admin/rollback/{sezione}/conta` — in uso: FE

### Router `agenti` (16)

- **attivo** — `POST /api/agenti/automazioni/ferma` — in uso: FE
- **attivo** — `POST /api/agenti/automazioni/riprendi` — in uso: FE
- **attivo** — `GET /api/agenti/automazioni/stato` — in uso: FE
- **attivo** — `GET /api/agenti/cash-flow-13-settimane` — in uso: FE
- **attivo** — `GET /api/agenti/decisioni` — in uso: FE
- **attivo** — `POST /api/agenti/decisioni/{decision_id}/approva` — in uso: FE
- **attivo** — `GET /api/agenti/decisioni/{decision_id}/eventi` — in uso: FE
- **attivo** — `POST /api/agenti/decisioni/{decision_id}/rifiuta` — in uso: FE
- **attivo** — `GET /api/agenti/pattern-appresi` — in uso: FE
- **quarantena: verificare** — `POST /api/agenti/run` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/agenti/segnalazioni` — in uso: FE
- **attivo** — `GET /api/agenti/segnalazioni/count` — in uso: FE
- **attivo** — `GET /api/agenti/segnalazioni/summary` — in uso: FE
- **attivo** — `PUT /api/agenti/segnalazioni/{sid}/letta` — in uso: FE
- **attivo** — `PUT /api/agenti/segnalazioni/{sid}/risolta` — in uso: FE
- **attivo** — `GET /api/agenti/stato` — in uso: FE

### Router `ai_parser` (11)

- **quarantena: verificare** — `POST /api/ai-parser/batch-parse` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/ai-parser/da-rivedere` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/ai-parser/da-rivedere/process-batch` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `PUT /api/ai-parser/da-rivedere/{document_id}/classifica` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/ai-parser/parse` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/ai-parser/parse-busta-paga` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/ai-parser/parse-f24` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/ai-parser/parse-fattura` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/ai-parser/process-email-batch` — in uso: FE
- **quarantena: verificare** — `GET /api/ai-parser/statistiche` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/ai-parser/test` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `alerts` (7)

- **quarantena: verificare** — `GET /api/alerts/fornitori-senza-metodo` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/alerts/lista` — in uso: FE
- **quarantena: verificare** — `POST /api/alerts/risolvi-fornitore/{fornitore_piva}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/alerts/summary` — in uso: FE
- **quarantena: verificare** — `DELETE /api/alerts/{alert_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/alerts/{alert_id}/risolvi` — in uso: scheduler
- **quarantena: verificare** — `POST /api/alerts/{alert_id}/segna-letto` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `anagrafica_fornitori_xml` (2)

- **attivo** — `POST /api/anagrafica-fornitori/popola-fornitore/{fornitore_id}` — in uso: FE
- **attivo** — `POST /api/anagrafica-fornitori/popola-tutti` — in uso: FE

### Router `auth` (3)

- **attivo** — `POST /api/auth/login` — in uso: FE
- **attivo** — `POST /api/auth/logout` — in uso: FE
- **attivo** — `GET /api/auth/verify` — in uso: FE

### Router `auto_repair` (2)

- **attivo** — `POST /api/auto-repair/collega-targa-driver` — in uso: FE, scheduler
- **attivo** — `POST /api/auto-repair/inferisci-targa-driver-da-fatture` — in uso: FE, scheduler

### Router `bank.assegni` (33)

- **attivo** — `GET /api/assegni` — in uso: FE
- **attivo** — `GET /api/assegni/ambigui` — in uso: FE
- **attivo** — `POST /api/assegni/associa-beneficiari-robusto` — in uso: FE
- **attivo** — `POST /api/assegni/associa-pagamenti-multipli` — in uso: FE
- **attivo** — `POST /api/assegni/auto-associa` — in uso: FE
- **attivo** — `POST /api/assegni/auto-match` — in uso: FE
- **attivo** — `POST /api/assegni/auto-match/conferma` — in uso: FE
- **attivo** — `POST /api/assegni/cerca-combinazioni-assegni` — in uso: FE
- **attivo** — `DELETE /api/assegni/clear-generated` — in uso: FE
- **attivo** — `POST /api/assegni/conferma-proposta/{proposta_id}` — in uso: FE
- **attivo** — `PUT /api/assegni/correggi-associazione/{assegno_id}` — in uso: FE
- **attivo** — `POST /api/assegni/correggi-numeri` — in uso: FE
- **attivo** — `POST /api/assegni/genera` — in uso: FE
- **attivo** — `GET /api/assegni/preview-combinazioni` — in uso: FE
- **attivo** — `GET /api/assegni/proposte-associazione` — in uso: FE
- **attivo** — `POST /api/assegni/pulisci-beneficiari-fittizi` — in uso: FE
- **attivo** — `POST /api/assegni/ricostruisci-dati` — in uso: FE
- **attivo** — `POST /api/assegni/rifiuta-proposta/{proposta_id}` — in uso: FE
- **attivo** — `POST /api/assegni/riprocessa-collegamenti` — in uso: FE
- **attivo** — `GET /api/assegni/senza-associazione` — in uso: FE
- **attivo** — `GET /api/assegni/stati` — in uso: FE
- **attivo** — `GET /api/assegni/stats` — in uso: FE
- **attivo** — `GET /api/assegni/supporto/fatture-disponibili` — in uso: FE
- **attivo** — `POST /api/assegni/sync-da-estratto-conto` — in uso: FE
- **attivo** — `GET /api/assegni/verifica-associazioni` — in uso: FE
- **attivo** — `DELETE /api/assegni/{assegno_id}` — in uso: FE
- **attivo** — `GET /api/assegni/{assegno_id}` — in uso: FE
- **attivo** — `PUT /api/assegni/{assegno_id}` — in uso: FE
- **attivo** — `POST /api/assegni/{assegno_id}/annulla` — in uso: FE
- **attivo** — `POST /api/assegni/{assegno_id}/emetti` — in uso: FE
- **attivo** — `PUT /api/assegni/{assegno_id}/fatture-collegate` — in uso: FE
- **attivo** — `POST /api/assegni/{assegno_id}/incassa` — in uso: FE
- **attivo** — `POST /api/assegni/{assegno_id}/risolvi-ambiguo` — in uso: FE

### Router `bank.assegni_learning` (6)

- **attivo** — `POST /api/assegni/learning/associa-combinazioni-avanzato` — in uso: FE
- **attivo** — `POST /api/assegni/learning/associa-intelligente` — in uso: FE
- **attivo** — `POST /api/assegni/learning/learn` — in uso: FE
- **quarantena: admin-only** — `POST /api/assegni/learning/pulizia-duplicati` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **attivo** — `GET /api/assegni/learning/stats-avanzate` — in uso: FE
- **attivo** — `GET /api/assegni/learning/suggerimenti/{importo}` — in uso: FE

### Router `bank.bank_statement_import` (7)

- **quarantena: admin-only** — `POST /api/bank-statement/cleanup-duplicati` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: admin-only** — `POST /api/bank-statement/cleanup-duplicati-causale` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: verificare** — `GET /api/bank-statement/formati-supportati` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/bank-statement/import` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/bank-statement/movements` — in uso: FE
- **quarantena: verificare** — `POST /api/bank-statement/riconcilia-manuale` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/bank-statement/stats` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `bank.bonifici_import_unificato` (1)

- **quarantena: verificare** — `POST /api/archivio-bonifici/jobs/import` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `bank.estratto_conto` (15)

- **quarantena: verificare** — `GET /api/estratto-conto-movimenti/categorie` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `DELETE /api/estratto-conto-movimenti/clear` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/estratto-conto-movimenti/export-excel` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: admin-only** — `POST /api/estratto-conto-movimenti/force-reimport` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: verificare** — `GET /api/estratto-conto-movimenti/fornitori` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/estratto-conto-movimenti/import` — in uso: FE, scheduler
- **quarantena: verificare** — `GET /api/estratto-conto-movimenti/movimenti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/estratto-conto-movimenti/movimenti-stipendi` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: admin-only** — `POST /api/estratto-conto-movimenti/pulizia-non-in-csv` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: admin-only** — `POST /api/estratto-conto-movimenti/reimport` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **attivo** — `POST /api/estratto-conto-movimenti/ricategorizza-batch` — in uso: FE
- **quarantena: verificare** — `POST /api/estratto-conto-movimenti/riconcilia-stipendi` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/estratto-conto-movimenti/riepilogo` — in uso: chat
- **attivo** — `POST /api/estratto-conto-movimenti/ripara-versamenti-cassa` — in uso: FE
- **quarantena: verificare** — `DELETE /api/estratto-conto-movimenti/{movimento_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `bank.riconciliazione_f24_banca` (5)

- **quarantena: verificare** — `GET /api/f24-riconciliazione/estratti-conto` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-riconciliazione/movimenti-f24-banca` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/f24-riconciliazione/riconcilia-f24` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-riconciliazione/stato-riconciliazione` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/f24-riconciliazione/upload-estratto-bpm` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `batch_reprocessing` (5)

- **attivo** — `POST /api/batch-reprocess/cedolini-only` — in uso: scheduler
- **attivo** — `POST /api/batch-reprocess/f24-only` — in uso: scheduler
- **attivo** — `GET /api/batch-reprocess/preview` — in uso: FE, scheduler
- **attivo** — `POST /api/batch-reprocess/start` — in uso: FE, scheduler
- **attivo** — `GET /api/batch-reprocess/status` — in uso: FE, scheduler

### Router `bonifici_module.associazioni` (8)

- **attivo** — `POST /api/archivio-bonifici/associa-fattura` — in uso: FE
- **attivo** — `POST /api/archivio-bonifici/associa-salario` — in uso: FE
- **quarantena: verificare** — `GET /api/archivio-bonifici/dipendente/{dipendente_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `DELETE /api/archivio-bonifici/disassocia-fattura/{bonifico_id}` — in uso: FE
- **attivo** — `DELETE /api/archivio-bonifici/disassocia-salario/{bonifico_id}` — in uso: FE
- **attivo** — `GET /api/archivio-bonifici/fatture-compatibili/{bonifico_id}` — in uso: FE
- **attivo** — `GET /api/archivio-bonifici/operazioni-salari/{bonifico_id}` — in uso: FE
- **attivo** — `POST /api/archivio-bonifici/sync-iban-anagrafica` — in uso: FE

### Router `bonifici_module.jobs` (4)

- **quarantena: verificare** — `GET /api/archivio-bonifici/jobs` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/archivio-bonifici/jobs` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/archivio-bonifici/jobs/{job_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/archivio-bonifici/jobs/{job_id}/upload` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `bonifici_module.riconciliazione` (6)

- **quarantena: verificare** — `POST /api/archivio-bonifici/associa-dipendenti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/archivio-bonifici/dashboard` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: admin-only** — `POST /api/archivio-bonifici/reset-riconciliazione` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **attivo** — `POST /api/archivio-bonifici/riconcilia` — in uso: FE
- **attivo** — `GET /api/archivio-bonifici/riconcilia/task/{task_id}` — in uso: FE
- **attivo** — `GET /api/archivio-bonifici/stato-riconciliazione` — in uso: FE

### Router `bonifici_module.transfers` (9)

- **quarantena: verificare** — `GET /api/archivio-bonifici/download-zip/{year}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/archivio-bonifici/export` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/archivio-bonifici/transfers` — in uso: FE
- **attivo** — `DELETE /api/archivio-bonifici/transfers/bulk` — in uso: FE
- **attivo** — `GET /api/archivio-bonifici/transfers/count` — in uso: FE
- **attivo** — `GET /api/archivio-bonifici/transfers/summary` — in uso: FE
- **attivo** — `DELETE /api/archivio-bonifici/transfers/{transfer_id}` — in uso: FE
- **attivo** — `PUT /api/archivio-bonifici/transfers/{transfer_id}` — in uso: FE
- **attivo** — `GET /api/archivio-bonifici/transfers/{transfer_id}/pdf` — in uso: FE

### Router `cash` (8)

- **attivo** — `POST /api/cash/corrispettivi` — in uso: FE
- **attivo** — `GET /api/cash/corrispettivi/{target_date}` — in uso: FE
- **attivo** — `GET /api/cash/export/excel` — in uso: FE
- **attivo** — `GET /api/cash/movements` — in uso: FE
- **attivo** — `POST /api/cash/movements` — in uso: FE
- **attivo** — `DELETE /api/cash/movements/{movement_id}` — in uso: FE
- **attivo** — `PUT /api/cash/movements/{movement_id}` — in uso: FE
- **attivo** — `GET /api/cash/stats` — in uso: FE

### Router `cespiti` (13)

- **attivo** — `GET /api/cespiti/` — in uso: FE
- **attivo** — `POST /api/cespiti/` — in uso: FE
- **attivo** — `GET /api/cespiti/calcolo-rateo/{anno}/{mese}` — in uso: FE
- **attivo** — `GET /api/cespiti/calcolo/{anno}` — in uso: FE
- **attivo** — `GET /api/cespiti/categorie` — in uso: FE
- **attivo** — `POST /api/cespiti/dismissione` — in uso: FE
- **attivo** — `POST /api/cespiti/registra/{anno}` — in uso: FE
- **attivo** — `GET /api/cespiti/riepilogo` — in uso: FE
- **attivo** — `POST /api/cespiti/scan-fatture` — in uso: FE
- **attivo** — `GET /api/cespiti/verifica/{anno}` — in uso: FE
- **attivo** — `DELETE /api/cespiti/{cespite_id}` — in uso: FE
- **attivo** — `GET /api/cespiti/{cespite_id}` — in uso: FE
- **attivo** — `PUT /api/cespiti/{cespite_id}` — in uso: FE

### Router `chat_router` (3)

- **attivo** — `POST /api/chat/ask` — in uso: FE, chat
- **attivo** — `GET /api/chat/health` — in uso: chat
- **attivo** — `GET /api/chat/history` — in uso: chat

### Router `chiusura_esercizio` (7)

- **attivo** — `POST /api/chiusura-esercizio/apertura-nuovo-esercizio` — in uso: FE
- **attivo** — `GET /api/chiusura-esercizio/bilancino-verifica/{anno}` — in uso: FE
- **attivo** — `POST /api/chiusura-esercizio/esegui-chiusura` — in uso: FE
- **quarantena: verificare** — `GET /api/chiusura-esercizio/saldi-iniziali/{anno}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/chiusura-esercizio/stato/{anno}` — in uso: FE
- **attivo** — `GET /api/chiusura-esercizio/storico` — in uso: FE
- **attivo** — `GET /api/chiusura-esercizio/verifica-preliminare/{anno}` — in uso: FE

### Router `collaudo` (3)

- **attivo** — `POST /api/collaudo/esegui` — in uso: FE
- **attivo** — `GET /api/collaudo/storico` — in uso: FE
- **attivo** — `GET /api/collaudo/ultimo` — in uso: FE

### Router `commercialista` (15)

- **attivo** — `GET /api/commercialista/alert-status` — in uso: FE
- **attivo** — `GET /api/commercialista/config` — in uso: FE
- **attivo** — `PUT /api/commercialista/config` — in uso: FE
- **attivo** — `GET /api/commercialista/export-completo/{anno}/{mese}` — in uso: FE
- **attivo** — `GET /api/commercialista/export-excel/{anno}/{mese}` — in uso: FE
- **quarantena: verificare** — `GET /api/commercialista/export-log` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/commercialista/fatture-cassa/{anno}/{mese}` — in uso: FE
- **attivo** — `POST /api/commercialista/invia-carnet` — in uso: FE
- **attivo** — `POST /api/commercialista/invia-fatture-cassa` — in uso: FE
- **attivo** — `POST /api/commercialista/invia-prima-nota` — in uso: FE
- **attivo** — `GET /api/commercialista/log` — in uso: FE
- **attivo** — `GET /api/commercialista/prima-nota-cassa/{anno}/{mese}` — in uso: FE
- **attivo** — `GET /api/commercialista/riepilogo/{anno}/{mese}` — in uso: FE
- **quarantena: verificare** — `POST /api/commercialista/schedula-export` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/commercialista/segna-inviata` — in uso: FE

### Router `config_import` (3)

- **attivo** — `GET /api/config-import/anno` — in uso: FE
- **attivo** — `PUT /api/config-import/anno` — in uso: FE
- **attivo** — `POST /api/config-import/importa-anno` — in uso: FE

### Router `configurazioni` (9)

- **attivo** — `GET /api/config/email-accounts` — in uso: FE
- **attivo** — `POST /api/config/email-accounts` — in uso: FE
- **attivo** — `DELETE /api/config/email-accounts/{account_id}` — in uso: FE
- **attivo** — `PUT /api/config/email-accounts/{account_id}` — in uso: FE
- **attivo** — `POST /api/config/email-accounts/{account_id}/test` — in uso: FE
- **attivo** — `GET /api/config/parole-chiave` — in uso: FE
- **attivo** — `PUT /api/config/parole-chiave` — in uso: FE
- **attivo** — `POST /api/config/parole-chiave/aggiungi` — in uso: FE
- **attivo** — `DELETE /api/config/parole-chiave/rimuovi` — in uso: FE

### Router `contabilita_italiana` (1)

- **attivo** — `GET /api/contabilita/disponibilita-liquide` — in uso: FE

### Router `controllo_gestione` (4)

- **quarantena: verificare** — `GET /api/controllo-gestione/costi-per-categoria` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/controllo-gestione/costi-ricavi` — in uso: FE
- **quarantena: verificare** — `GET /api/controllo-gestione/kpi/{anno}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/controllo-gestione/trend-mensile` — in uso: chat

### Router `dati_isa` (1)

- **attivo** — `GET /api/dati-isa/riepilogo` — in uso: FE

### Router `dati_provvisori` (6)

- **attivo** — `POST /api/conferma-tutte` — in uso: scheduler
- **attivo** — `POST /api/conferma/{proposta_id}` — in uso: scheduler, chat
- **attivo** — `POST /api/dati-provvisori/riconcilia-estratto-conto` — in uso: scheduler
- **attivo** — `POST /api/genera-proposte` — in uso: scheduler
- **attivo** — `GET /api/proposte` — in uso: scheduler
- **attivo** — `POST /api/rifiuta/{proposta_id}` — in uso: scheduler

### Router `document_ai` (10)

- **quarantena: verificare** — `GET /api/document-ai/classified-documents-stats` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/document-ai/document-types` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/document-ai/extract` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/document-ai/extract-base64` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/document-ai/extract-text-only` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/document-ai/extracted-documents` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `DELETE /api/document-ai/extracted-documents/{doc_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/document-ai/process-all-classified` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/document-ai/process-classified-email` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/document-ai/reprocess-and-save` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `documenti` (52)

- **attivo** — `GET /api/documenti/amministrativi` — in uso: FE
- **attivo** — `GET /api/documenti/amministrativi/familiari` — in uso: FE
- **quarantena: verificare** — `GET /api/documenti/cartelle-email` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/documenti/categorie` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `DELETE /api/documenti/documento/{doc_id}` — in uso: FE
- **attivo** — `GET /api/documenti/documento/{doc_id}` — in uso: FE
- **attivo** — `POST /api/documenti/documento/{doc_id}/annulla-processamento` — in uso: FE
- **attivo** — `POST /api/documenti/documento/{doc_id}/cambia-categoria` — in uso: FE
- **attivo** — `GET /api/documenti/documento/{doc_id}/download` — in uso: FE
- **attivo** — `POST /api/documenti/documento/{doc_id}/processa` — in uso: FE
- **attivo** — `GET /api/documenti/drive/catalog` — in uso: FE
- **attivo** — `POST /api/documenti/drive/fiscal/discover` — in uso: FE
- **attivo** — `GET /api/documenti/drive/fiscal/status` — in uso: FE
- **attivo** — `POST /api/documenti/drive/fiscal/sync` — in uso: FE
- **attivo** — `GET /api/documenti/drive/folders` — in uso: FE
- **attivo** — `GET /api/documenti/drive/index/declarations` — in uso: FE
- **attivo** — `GET /api/documenti/drive/index/document/{document_id}` — in uso: FE
- **attivo** — `GET /api/documenti/drive/index/f24` — in uso: FE
- **attivo** — `GET /api/documenti/drive/index/overview` — in uso: FE
- **attivo** — `GET /api/documenti/drive/index/search` — in uso: FE
- **attivo** — `GET /api/documenti/drive/index/status` — in uso: FE
- **attivo** — `POST /api/documenti/drive/sync` — in uso: FE
- **quarantena: verificare** — `POST /api/documenti/elimina-processati` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/documenti/fiscal/ingest` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/documenti/lista` — in uso: FE
- **quarantena: verificare** — `GET /api/documenti/lock-status` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/documenti/monitor/start` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/documenti/monitor/status` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/documenti/monitor/stop` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/documenti/monitor/sync-now` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/documenti/processa-f24-scaricati` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/documenti/processa-tutti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: admin-only** — `POST /api/documenti/reimporta-da-filesystem` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: verificare** — `POST /api/documenti/ricategorizza-documenti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/documenti/scarica-da-email` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/documenti/statistiche` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/documenti/sync-estratti-bnl` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/documenti/sync-estratti-conto` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/documenti/sync-f24-automatico` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/documenti/task/{task_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/documenti/tax-codes` — in uso: FE
- **attivo** — `GET /api/documenti/tax-codes/status` — in uso: FE
- **attivo** — `POST /api/documenti/tax-codes/sync` — in uso: FE
- **quarantena: verificare** — `GET /api/documenti/telegram/status` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/documenti/telegram/test` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/documenti/ultimo-sync` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/documenti/upload-auto` — in uso: FE
- **attivo** — `GET /api/documenti/upload-auto/jobs/{job_id}` — in uso: FE
- **attivo** — `POST /api/documenti/upload-auto/preview` — in uso: FE
- **attivo** — `POST /api/documenti/upload-auto/queue` — in uso: FE
- **attivo** — `POST /api/documenti/upload-auto/render` — in uso: FE
- **attivo** — `POST /api/documenti/upload-auto/render/preview` — in uso: FE

### Router `documenti_fiscali` (3)

- **quarantena: verificare** — `GET /api/documenti-fiscali/lista` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/documenti-fiscali/upload` — in uso: FE
- **attivo** — `POST /api/documenti-fiscali/upload-f24-commercialista` — in uso: FE

### Router `documenti_non_associati` (9)

- **attivo** — `POST /api/documenti-non-associati/associa` — in uso: FE
- **attivo** — `GET /api/documenti-non-associati/associati-di-recente` — in uso: FE
- **quarantena: verificare** — `GET /api/documenti-non-associati/categorie-mittente` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/documenti-non-associati/collezioni-disponibili` — in uso: FE
- **attivo** — `POST /api/documenti-non-associati/de-associa` — in uso: FE
- **attivo** — `GET /api/documenti-non-associati/lista` — in uso: FE
- **attivo** — `GET /api/documenti-non-associati/pdf/{documento_id}` — in uso: FE
- **attivo** — `GET /api/documenti-non-associati/statistiche` — in uso: FE
- **quarantena: verificare** — `DELETE /api/documenti-non-associati/{documento_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `documents_inbox_classify` (5)

- **attivo** — `POST /api/documenti-inbox/auto-classify` — in uso: FE
- **quarantena: verificare** — `GET /api/documenti-inbox/cross-check-f24` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/documenti-inbox/import-dipendenti-from-cu` — in uso: FE
- **attivo** — `POST /api/documenti-inbox/import-f24-from-inbox` — in uso: FE
- **quarantena: verificare** — `GET /api/documenti-inbox/statistics` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `drive_cedolini` (3)

- **attivo** — `GET /api/cedolini/drive/quadratura-completa` — in uso: scheduler
- **attivo** — `GET /api/cedolini/drive/status` — in uso: scheduler
- **attivo** — `POST /api/cedolini/drive/sync` — in uso: scheduler

### Router `drive_corrispettivi` (3)

- **attivo** — `POST /api/corrispettivi/drive/quadratura` — in uso: FE
- **attivo** — `GET /api/corrispettivi/drive/status` — in uso: FE, scheduler
- **attivo** — `POST /api/corrispettivi/drive/sync` — in uso: FE, scheduler

### Router `drive_quietanze` (3)

- **attivo** — `POST /api/f24/quietanze/drive/quadratura` — in uso: FE
- **attivo** — `GET /api/f24/quietanze/drive/status` — in uso: FE, scheduler
- **attivo** — `POST /api/f24/quietanze/drive/sync` — in uso: FE, scheduler

### Router `email_download` (38)

- **quarantena: verificare** — `POST /api/email-download/associa-documento` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/email-download/associa-f24-filesystem` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/email-download/auto-associa` — in uso: FE
- **quarantena: verificare** — `POST /api/email-download/auto-associa-v2` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/email-download/confronto-pos` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/email-download/dizionario-email` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: admin-only** — `DELETE /api/email-download/dizionario-email/reset` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: verificare** — `GET /api/email-download/documenti-non-associati` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/email-download/documents-inbox-stats` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/email-download/download-single-day` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/email-download/estrai-importi-verbali` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/email-download/fix-numeri-verbali` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/email-download/inbox-documents` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/email-download/mittenti` — in uso: FE
- **attivo** — `POST /api/email-download/mittenti` — in uso: FE
- **attivo** — `GET /api/email-download/mittenti/check` — in uso: FE
- **quarantena: admin-only** — `POST /api/email-download/mittenti/migra-legacy` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **attivo** — `DELETE /api/email-download/mittenti/{mittente_id}` — in uso: FE
- **attivo** — `PUT /api/email-download/mittenti/{mittente_id}` — in uso: FE
- **quarantena: verificare** — `POST /api/email-download/parse-f24-llm` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/email-download/parse-verbali-llm` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/email-download/paypal-transazioni` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/email-download/pdf/{collection}/{pdf_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/email-download/popola-pdf-payslips` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/email-download/processa-cedolini` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/email-download/processa-pipeline` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `DELETE /api/email-download/pulisci-duplicati` — in uso: scheduler
- **quarantena: admin-only** — `POST /api/email-download/pulizia-non-attendibili` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: verificare** — `POST /api/email-download/riconcilia-paypal` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/email-download/riconcilia-verbali` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/email-download/riconcilia-verbali-avanzato` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/email-download/riconciliazione-completa` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/email-download/scarica-pdf-verbali-mancanti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/email-download/start-full-download` — in uso: FE
- **quarantena: verificare** — `GET /api/email-download/statistiche` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/email-download/status` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/email-download/sync-email-now` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/email-download/sync-filesystem` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `email_scanner` (5)

- **attivo** — `POST /api/email-scanner/associa` — in uso: FE
- **quarantena: verificare** — `GET /api/email-scanner/cartelle` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/email-scanner/scansiona` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/email-scanner/scansiona-e-associa` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/email-scanner/statistiche` — in uso: FE, scheduler

### Router `employees.dipendenti` (28)

- **attivo** — `GET /api/dipendenti` — in uso: FE
- **attivo** — `POST /api/dipendenti` — in uso: FE
- **attivo** — `POST /api/dipendenti/bulk-upsert` — in uso: FE
- **attivo** — `POST /api/dipendenti/bulk-upsert/preview` — in uso: FE
- **attivo** — `GET /api/dipendenti/buste-paga` — in uso: FE
- **attivo** — `POST /api/dipendenti/buste-paga` — in uso: FE
- **attivo** — `GET /api/dipendenti/buste-paga/dipendente/{dipendente_id}` — in uso: FE
- **attivo** — `POST /api/dipendenti/buste-paga/dipendente/{dipendente_id}/import` — in uso: FE
- **attivo** — `POST /api/dipendenti/buste-paga/import` — in uso: FE
- **attivo** — `GET /api/dipendenti/buste-paga/scan` — in uso: FE
- **attivo** — `GET /api/dipendenti/by-google-email` — in uso: FE
- **attivo** — `GET /api/dipendenti/duplicati` — in uso: FE
- **attivo** — `POST /api/dipendenti/duplicati/auto-merge` — in uso: FE
- **attivo** — `POST /api/dipendenti/duplicati/merge` — in uso: FE
- **attivo** — `POST /api/dipendenti/invita-multipli` — in uso: FE
- **attivo** — `GET /api/dipendenti/mansioni` — in uso: FE
- **attivo** — `GET /api/dipendenti/portale/stats` — in uso: FE
- **attivo** — `GET /api/dipendenti/report-ferie-permessi-tutti` — in uso: FE
- **attivo** — `GET /api/dipendenti/stats` — in uso: FE
- **attivo** — `POST /api/dipendenti/sync-iban` — in uso: FE
- **attivo** — `GET /api/dipendenti/tipi-turno` — in uso: FE
- **attivo** — `POST /api/dipendenti/turni/salva` — in uso: FE
- **attivo** — `GET /api/dipendenti/turni/settimana` — in uso: FE
- **attivo** — `DELETE /api/dipendenti/{dipendente_id}` — in uso: FE
- **attivo** — `GET /api/dipendenti/{dipendente_id}` — in uso: FE
- **attivo** — `PUT /api/dipendenti/{dipendente_id}` — in uso: FE
- **attivo** — `POST /api/dipendenti/{dipendente_id}/invita-portale` — in uso: FE
- **attivo** — `GET /api/dipendenti/{dipendente_id}/report-ferie-permessi` — in uso: FE

### Router `f24.email_f24` (7)

- **quarantena: verificare** — `GET /api/f24-email/allegati` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-email/codici-tributo` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-email/log-download` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-email/mittenti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/f24-email/processa-allegati` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/f24-email/scarica-e-processa` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/f24-email/scarica-email` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `f24.f24_main` (24)

- **attivo** — `GET /api/f24` — in uso: FE
- **attivo** — `POST /api/f24` — in uso: FE
- **attivo** — `GET /api/f24/alerts/scadenze` — in uso: FE
- **attivo** — `GET /api/f24/codici/all` — in uso: FE
- **attivo** — `GET /api/f24/codici/{codice}` — in uso: FE
- **attivo** — `GET /api/f24/dashboard/summary` — in uso: FE
- **attivo** — `GET /api/f24/documents` — in uso: FE
- **attivo** — `DELETE /api/f24/documents/{doc_id}` — in uso: FE
- **attivo** — `POST /api/f24/fascicolo/costruisci` — in uso: FE
- **attivo** — `GET /api/f24/fascicolo/{codice_fiscale}/{mese}/{anno}` — in uso: FE
- **attivo** — `GET /api/f24/quietanze` — in uso: FE
- **attivo** — `GET /api/f24/quietanze/statistiche/tributi` — in uso: FE
- **attivo** — `POST /api/f24/quietanze/upload` — in uso: FE
- **attivo** — `DELETE /api/f24/quietanze/{f24_id}` — in uso: FE
- **attivo** — `GET /api/f24/quietanze/{f24_id}` — in uso: FE
- **attivo** — `POST /api/f24/riconcilia` — in uso: FE, scheduler
- **attivo** — `POST /api/f24/upload` — in uso: FE
- **attivo** — `POST /api/f24/upload-multiple` — in uso: FE
- **attivo** — `POST /api/f24/upload-pdf` — in uso: FE
- **attivo** — `POST /api/f24/upload-zip` — in uso: FE
- **attivo** — `DELETE /api/f24/{f24_id}` — in uso: FE
- **attivo** — `GET /api/f24/{f24_id}` — in uso: FE
- **attivo** — `PUT /api/f24/{f24_id}` — in uso: FE
- **attivo** — `POST /api/f24/{f24_id}/mark-paid` — in uso: FE

### Router `f24.f24_public` (9)

- **quarantena: verificare** — `GET /api/f24-public/models` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `DELETE /api/f24-public/models/{f24_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `PUT /api/f24-public/models/{f24_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `PUT /api/f24-public/models/{f24_id}/pagato` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-public/pdf/{f24_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-public/scadenze-prossime` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-public/test` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/f24-public/upload` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/f24-public/upload-overwrite` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `f24.f24_riconciliazione` (18)

- **quarantena: verificare** — `GET /api/f24-riconciliazione/alerts` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/f24-riconciliazione/alerts/{alert_id}/conferma-elimina` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/f24-riconciliazione/alerts/{alert_id}/ignora` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-riconciliazione/commercialista` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/f24-riconciliazione/commercialista/upload` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `DELETE /api/f24-riconciliazione/commercialista/{f24_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-riconciliazione/commercialista/{f24_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `PUT /api/f24-riconciliazione/commercialista/{f24_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `PUT /api/f24-riconciliazione/commercialista/{f24_id}/pagato` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-riconciliazione/commercialista/{f24_id}/pdf` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-riconciliazione/dashboard` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/f24-riconciliazione/fix-campo-anno` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-riconciliazione/quietanze` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/f24-riconciliazione/quietanze/upload-multiplo` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-riconciliazione/quietanze/{quietanza_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/f24-riconciliazione/riconcilia-quietanza` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/f24-riconciliazione/riconcilia-tutto` — in uso: FE
- **quarantena: verificare** — `GET /api/f24-riconciliazione/verifica-codice/{codice_tributo}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `f24_analisi` (4)

- **attivo** — `GET /api/f24-analisi/doppi-pagamenti` — in uso: chat
- **quarantena: verificare** — `GET /api/f24-analisi/tabella` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-analisi/{f24_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/f24-analisi/{f24_id}/associazione` — in uso: chat

### Router `f24_email_settings` (8)

- **attivo** — `POST /api/f24-email-settings/aggiungi-mittente` — in uso: FE
- **attivo** — `GET /api/f24-email-settings/impostazioni` — in uso: FE
- **attivo** — `POST /api/f24-email-settings/impostazioni` — in uso: FE
- **attivo** — `GET /api/f24-email-settings/log-scansioni` — in uso: FE
- **attivo** — `DELETE /api/f24-email-settings/rimuovi-mittente/{email}` — in uso: FE
- **attivo** — `POST /api/f24-email-settings/scan-manuale` — in uso: FE
- **attivo** — `GET /api/f24-email-settings/stato-sistema` — in uso: FE
- **attivo** — `POST /api/f24-email-settings/toggle-auto-scan` — in uso: FE

### Router `fatture_estera_verifica` (3)

- **attivo** — `GET /api/fatture-estere/affidabilita` — in uso: FE
- **attivo** — `GET /api/fatture-estere/da-verificare` — in uso: FE
- **quarantena: verificare** — `POST /api/fatture-estere/{fattura_id}/verifica` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `fatture_module.crud` (13)

- **attivo** — `GET /api/fatture-ricevute/archivio` — in uso: FE
- **quarantena: verificare** — `POST /api/fatture-ricevute/elimina-anni-vecchi` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/fatture-ricevute/elimina-gusci-vuoti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/fatture-ricevute/fattura/{fattura_id}` — in uso: FE, scheduler
- **attivo** — `PUT /api/fatture-ricevute/fattura/{fattura_id}` — in uso: FE, scheduler
- **attivo** — `GET /api/fatture-ricevute/fattura/{fattura_id}/documenti-pagamento` — in uso: FE
- **attivo** — `GET /api/fatture-ricevute/fattura/{fattura_id}/pdf/{allegato_id}` — in uso: FE
- **attivo** — `GET /api/fatture-ricevute/fattura/{fattura_id}/storia` — in uso: FE
- **attivo** — `GET /api/fatture-ricevute/fattura/{fattura_id}/view-assoinvoice` — in uso: FE
- **attivo** — `GET /api/fatture-ricevute/fattura/{fattura_id}/xml-originale` — in uso: FE
- **attivo** — `GET /api/fatture-ricevute/fornitori` — in uso: FE
- **attivo** — `POST /api/fatture-ricevute/pulisci-duplicati` — in uso: scheduler
- **quarantena: verificare** — `GET /api/fatture-ricevute/statistiche` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `fatture_module.export_selezione` (1)

- **attivo** — `POST /api/fatture-ricevute/export-selezione` — in uso: FE

### Router `fatture_module.pagamento` (10)

- **quarantena: verificare** — `POST /api/fatture-ricevute/aggiorna-metodi-pagamento` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: admin-only** — `POST /api/fatture-ricevute/backfill-autoroute` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: verificare** — `POST /api/fatture-ricevute/cambia-metodo-pagamento` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/fatture-ricevute/fattura/{fattura_id}/candidati-bancari` — in uso: FE
- **quarantena: verificare** — `POST /api/fatture-ricevute/import-paypal` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/fatture-ricevute/lista-paypal` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/fatture-ricevute/paga-manuale` — in uso: FE
- **attivo** — `POST /api/fatture-ricevute/riconcilia-con-estratto-conto` — in uso: FE
- **quarantena: verificare** — `POST /api/fatture-ricevute/riconcilia-paypal` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/fatture-ricevute/verifica-incoerenze-estratto-conto` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `finanziamenti_soci` (4)

- **attivo** — `POST /api/finanziamenti-soci/movimento` — in uso: FE
- **attivo** — `DELETE /api/finanziamenti-soci/movimento/{movimento_id}` — in uso: FE
- **quarantena: verificare** — `POST /api/finanziamenti-soci/scan` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/finanziamenti-soci/schede` — in uso: FE

### Router `finanziaria` (4)

- **quarantena: verificare** — `GET /api/finanziaria/cost-categories` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/finanziaria/costi` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/finanziaria/costo` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/finanziaria/summary` — in uso: FE

### Router `fiscal_control` (23)

- **attivo** — `GET /api/fiscal/ader-snapshots` — in uso: FE
- **attivo** — `POST /api/fiscal/ader-snapshots/dry-run` — in uso: FE
- **attivo** — `POST /api/fiscal/ader-snapshots/import` — in uso: FE
- **quarantena: verificare** — `POST /api/fiscal/collection-snapshots/dry-run` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/fiscal/collection-snapshots/import` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/fiscal/collections` — in uso: FE
- **attivo** — `GET /api/fiscal/collections/{claim_id}` — in uso: FE
- **attivo** — `POST /api/fiscal/collections/{claim_id}/events` — in uso: FE
- **attivo** — `GET /api/fiscal/crosswalk` — in uso: FE
- **attivo** — `GET /api/fiscal/declarations` — in uso: FE
- **attivo** — `GET /api/fiscal/declarations/{document_id}/field-certainty` — in uso: FE
- **attivo** — `GET /api/fiscal/documents/{document_id}/content` — in uso: FE
- **quarantena: verificare** — `GET /api/fiscal/dossier.pdf` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/fiscal/evidence-package.zip` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/fiscal/evidence/{entity_type}/{entity_id}` — in uso: FE, scheduler
- **quarantena: verificare** — `GET /api/fiscal/f24-documents` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/fiscal/f24-rows` — in uso: FE
- **attivo** — `GET /api/fiscal/obligations` — in uso: FE
- **quarantena: verificare** — `POST /api/fiscal/ravvedimento/calculate` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/fiscal/review` — in uso: FE
- **attivo** — `GET /api/fiscal/source-certainty` — in uso: FE
- **attivo** — `GET /api/fiscal/summary` — in uso: FE, chat
- **quarantena: verificare** — `POST /api/fiscal/vat-credit-chain/rebuild` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `fiscalita_italiana` (11)

- **quarantena: verificare** — `GET /api/fiscalita/agevolazioni` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/fiscalita/agevolazioni/simula` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/fiscalita/agevolazioni/{agevolazione_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/fiscalita/calendario/completa/{scadenza_id}` — in uso: FE
- **attivo** — `POST /api/fiscalita/calendario/riapri/{scadenza_id}` — in uso: FE
- **attivo** — `GET /api/fiscalita/calendario/scadenze-imminenti` — in uso: FE
- **attivo** — `GET /api/fiscalita/calendario/{anno}` — in uso: FE
- **quarantena: verificare** — `POST /api/fiscalita/f24/registra` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/fiscalita/f24/storico` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/fiscalita/notifiche-scadenze` — in uso: FE
- **attivo** — `POST /api/fiscalita/notifiche-scadenze/invia` — in uso: FE

### Router `fornitori_learning` (16)

- **quarantena: verificare** — `POST /api/fornitori-learning/associa-magazzino` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/fornitori-learning/centri-costo-disponibili` — in uso: FE
- **attivo** — `POST /api/fornitori-learning/classifica-ai` — in uso: FE
- **attivo** — `POST /api/fornitori-learning/classifica-da-contenuto` — in uso: FE
- **quarantena: verificare** — `POST /api/fornitori-learning/classifica-f24` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/fornitori-learning/f24-statistiche` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/fornitori-learning/giacenze-fornitore/{fornitore_nome}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/fornitori-learning/lista` — in uso: FE
- **attivo** — `GET /api/fornitori-learning/non-classificati` — in uso: FE
- **quarantena: verificare** — `GET /api/fornitori-learning/prodotti-per-fornitore/{fornitore_nome}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/fornitori-learning/riclassifica-con-keywords` — in uso: FE
- **quarantena: verificare** — `POST /api/fornitori-learning/riclassifica-f24/{f24_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/fornitori-learning/salva` — in uso: FE
- **attivo** — `GET /api/fornitori-learning/stats` — in uso: FE
- **attivo** — `GET /api/fornitori-learning/suggerisci-keywords/{fornitore_nome}` — in uso: FE
- **quarantena: verificare** — `DELETE /api/fornitori-learning/{fornitore_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `gestione_riservata` (7)

- **attivo** — `POST /api/gestione-riservata/login` — in uso: FE
- **attivo** — `GET /api/gestione-riservata/movimenti` — in uso: FE
- **attivo** — `POST /api/gestione-riservata/movimenti` — in uso: FE
- **attivo** — `DELETE /api/gestione-riservata/movimenti/{movimento_id}` — in uso: FE
- **attivo** — `PUT /api/gestione-riservata/movimenti/{movimento_id}` — in uso: FE
- **attivo** — `GET /api/gestione-riservata/riepilogo` — in uso: FE, chat
- **quarantena: verificare** — `GET /api/gestione-riservata/volume-affari-reale` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `invoices.corrispettivi` (24)

- **attivo** — `GET /api/corrispettivi` — in uso: FE
- **attivo** — `POST /api/corrispettivi/aggiorna-stati-mancanti` — in uso: FE
- **attivo** — `DELETE /api/corrispettivi/all` — in uso: FE
- **attivo** — `POST /api/corrispettivi/auto-ricostruisci-dati` — in uso: FE
- **quarantena: admin-only** — `POST /api/corrispettivi/cleanup-duplicati-forte` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **attivo** — `POST /api/corrispettivi/elimina-duplicati` — in uso: FE
- **attivo** — `POST /api/corrispettivi/hard-delete-bulk` — in uso: FE
- **attivo** — `DELETE /api/corrispettivi/hard-delete/{corrispettivo_id}` — in uso: FE
- **attivo** — `POST /api/corrispettivi/import-csv` — in uso: FE
- **attivo** — `POST /api/corrispettivi/manuale` — in uso: FE
- **attivo** — `GET /api/corrispettivi/manuali-senza-xml` — in uso: FE
- **attivo** — `POST /api/corrispettivi/normalizza-pagamenti` — in uso: FE
- **attivo** — `POST /api/corrispettivi/rebuild-prima-nota` — in uso: FE
- **attivo** — `POST /api/corrispettivi/ricalcola-annulli-non-riscosso` — in uso: FE
- **attivo** — `POST /api/corrispettivi/ricalcola-iva` — in uso: FE
- **attivo** — `POST /api/corrispettivi/sincronizza-prima-nota` — in uso: FE
- **attivo** — `GET /api/corrispettivi/template-csv` — in uso: FE
- **attivo** — `GET /api/corrispettivi/totals` — in uso: FE
- **attivo** — `POST /api/corrispettivi/upload-xml` — in uso: FE
- **attivo** — `POST /api/corrispettivi/upload-xml-bulk` — in uso: FE
- **attivo** — `POST /api/corrispettivi/upload-zip` — in uso: FE
- **attivo** — `GET /api/corrispettivi/view-by-filename` — in uso: FE
- **attivo** — `DELETE /api/corrispettivi/{corrispettivo_id}` — in uso: FE
- **attivo** — `GET /api/corrispettivi/{corrispettivo_id}/view` — in uso: FE

### Router `invoices.fatture_drive` (5)

- **attivo** — `POST /api/fatture/drive/quadratura` — in uso: FE
- **attivo** — `POST /api/fatture/drive/ricostruzione` — in uso: FE
- **attivo** — `POST /api/fatture/drive/ricostruzione/lotto` — in uso: FE
- **attivo** — `GET /api/fatture/drive/status` — in uso: FE, scheduler
- **attivo** — `POST /api/fatture/drive/sync` — in uso: FE, scheduler

### Router `invoices.fatture_upload` (12)

- **attivo** — `DELETE /api/fatture/all` — in uso: scheduler
- **attivo** — `POST /api/fatture/categorize-movements` — in uso: scheduler
- **attivo** — `POST /api/fatture/recalculate-iva` — in uso: scheduler
- **attivo** — `POST /api/fatture/sync-suppliers` — in uso: scheduler
- **attivo** — `POST /api/fatture/upload-xml` — in uso: scheduler
- **attivo** — `POST /api/fatture/upload-xml-bulk` — in uso: scheduler
- **attivo** — `DELETE /api/fatture/{invoice_id}` — in uso: FE, scheduler
- **attivo** — `GET /api/fatture/{invoice_id}` — in uso: FE, scheduler
- **attivo** — `PUT /api/fatture/{invoice_id}` — in uso: FE, scheduler
- **attivo** — `PUT /api/fatture/{invoice_id}/classifica` — in uso: FE, scheduler
- **attivo** — `GET /api/fatture/{invoice_id}/entita-correlate` — in uso: FE, scheduler
- **attivo** — `PUT /api/fatture/{invoice_id}/paga` — in uso: FE, scheduler

### Router `invoices.invoices_emesse` (4)

- **attivo** — `GET /api/invoices/emesse` — in uso: FE
- **attivo** — `POST /api/invoices/emesse` — in uso: FE
- **attivo** — `DELETE /api/invoices/emesse/{invoice_id}` — in uso: FE
- **attivo** — `GET /api/invoices/emesse/{invoice_id}` — in uso: FE

### Router `invoices.invoices_main` (4)

- **attivo** — `GET /api/invoices` — in uso: FE
- **attivo** — `GET /api/invoices/bank-pending` — in uso: FE
- **attivo** — `GET /api/invoices/by-month/{year}/{month}` — in uso: FE
- **attivo** — `GET /api/invoices/{invoice_id}` — in uso: FE

### Router `iva` (20)

- **attivo** — `GET /api/iva/anomalie` — in uso: FE
- **attivo** — `GET /api/iva/dashboard/{anno}/{mese}` — in uso: FE
- **attivo** — `GET /api/iva/fatture` — in uso: FE, scheduler
- **attivo** — `GET /api/iva/fatture/non-utilizzate` — in uso: FE
- **attivo** — `POST /api/iva/fatture/{fid}/correggi-periodo` — in uso: FE
- **attivo** — `POST /api/iva/fatture/{fid}/escludi` — in uso: FE
- **attivo** — `POST /api/iva/fatture/{fid}/includi` — in uso: FE
- **attivo** — `POST /api/iva/fatture/{fid}/indetraibile` — in uso: FE
- **attivo** — `POST /api/iva/fatture/{fid}/recupero-annuale` — in uso: FE
- **attivo** — `POST /api/iva/fatture/{fid}/rinvia` — in uso: FE
- **attivo** — `GET /api/iva/liquidazioni` — in uso: FE
- **attivo** — `POST /api/iva/liquidazioni/calcola` — in uso: FE
- **attivo** — `POST /api/iva/liquidazioni/{liq_id}/conferma` — in uso: FE
- **attivo** — `POST /api/iva/liquidazioni/{liq_id}/rettifica` — in uso: FE
- **attivo** — `POST /api/iva/liquidazioni/{liq_id}/riapri` — in uso: FE
- **attivo** — `GET /api/iva/liquidazioni/{periodo}` — in uso: FE
- **quarantena: verificare** — `POST /api/iva/ricalcola-attribuzione` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/iva/ricalcola-attribuzione/ultimo` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/iva/riepilogo-annuale/{anno}` — in uso: FE
- **quarantena: verificare** — `GET /api/iva/versamento/{anno}/{mese}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `learning_machine` (7)

- **attivo** — `GET /api/learning-machine/dashboard` — in uso: FE
- **quarantena: verificare** — `GET /api/learning-machine/documenti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/learning-machine/feedback` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/learning-machine/regole-apprese` — in uso: FE
- **quarantena: admin-only** — `DELETE /api/learning-machine/reset-learning` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: verificare** — `POST /api/learning-machine/scan` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/learning-machine/statistiche-feedback` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `learning_universal` (5)

- **quarantena: verificare** — `POST /api/learning-universal/apply-suggestions` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/learning-universal/results` — in uso: FE
- **attivo** — `GET /api/learning-universal/status` — in uso: FE
- **quarantena: verificare** — `GET /api/learning-universal/suggestions/{module}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/learning-universal/train/all` — in uso: FE

### Router `legal_pages` (6)

- **quarantena: verificare** — `GET /api/data-deletion` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/privacy` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/terms` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /data-deletion` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /privacy` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /terms` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `lotti_integration` (3)

- **quarantena: verificare** — `GET /api/integrations/lotti/employees` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/integrations/lotti/invoices` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/integrations/lotti/invoices/{source_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `mfa` (6)

- **attivo** — `POST /api/auth/mfa/disable` — in uso: FE
- **attivo** — `POST /api/auth/mfa/setup/confirm` — in uso: FE
- **attivo** — `POST /api/auth/mfa/setup/start` — in uso: FE
- **attivo** — `GET /api/auth/mfa/status` — in uso: FE
- **attivo** — `POST /api/auth/mfa/step-up` — in uso: FE
- **attivo** — `POST /api/auth/mfa/verify-login` — in uso: FE

### Router `multi_pagamento` (6)

- **quarantena: verificare** — `POST /api/pagamenti/assegno-multi-fatture` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/pagamenti/fattura-multi-metodo` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/pagamenti/fattura/{fattura_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/pagamenti/registra` — in uso: FE, scheduler
- **quarantena: verificare** — `GET /api/pagamenti/riepilogo-fornitore/{piva}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `DELETE /api/pagamenti/{pagamento_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `mutui` (10)

- **attivo** — `GET /api/mutui` — in uso: FE
- **attivo** — `GET /api/mutui/` — in uso: FE
- **attivo** — `POST /api/mutui/` — in uso: FE
- **attivo** — `POST /api/mutui/riconcilia` — in uso: FE
- **attivo** — `GET /api/mutui/statistiche/dashboard` — in uso: FE
- **attivo** — `DELETE /api/mutui/{mutuo_id}` — in uso: FE
- **attivo** — `GET /api/mutui/{mutuo_id}` — in uso: FE
- **attivo** — `PUT /api/mutui/{mutuo_id}` — in uso: FE
- **attivo** — `GET /api/mutui/{mutuo_id}/rate` — in uso: FE
- **attivo** — `PUT /api/mutui/{mutuo_id}/rate/{numero_rata}/riconcilia` — in uso: FE

### Router `mutui_parser` (3)

- **attivo** — `POST /api/mutui/import-pdf` — in uso: FE
- **attivo** — `POST /api/mutui/parse-multiple` — in uso: FE
- **attivo** — `POST /api/mutui/parse-pdf` — in uso: FE

### Router `nexi_carta` (4)

- **quarantena: verificare** — `GET /api/nexi/movimenti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/nexi/stato` — in uso: FE
- **quarantena: verificare** — `POST /api/nexi/upload-pdf` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/nexi/verifica` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `noleggio` (14)

- **attivo** — `POST /api/noleggio/associa-fornitore` — in uso: FE
- **quarantena: verificare** — `POST /api/noleggio/controllo-canoni` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/noleggio/drivers` — in uso: FE
- **attivo** — `GET /api/noleggio/export-pdf-costi` — in uso: FE
- **quarantena: verificare** — `GET /api/noleggio/fatture-non-associate` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/noleggio/fatture/{fattura_id}/associa-veicolo` — in uso: FE
- **attivo** — `GET /api/noleggio/fornitori` — in uso: FE
- **attivo** — `GET /api/noleggio/riepilogo-controlli` — in uso: FE
- **attivo** — `GET /api/noleggio/veicoli` — in uso: FE
- **attivo** — `POST /api/noleggio/veicoli` — in uso: FE
- **attivo** — `DELETE /api/noleggio/veicoli/{targa}` — in uso: FE
- **attivo** — `PUT /api/noleggio/veicoli/{targa}` — in uso: FE
- **attivo** — `GET /api/noleggio/veicoli/{targa}/completo` — in uso: FE
- **quarantena: verificare** — `GET /api/noleggio/verbali-dipendente` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `openapi_automotive` (5)

- **attivo** — `POST /api/openapi-automotive/aggiorna-veicolo` — in uso: FE
- **quarantena: verificare** — `GET /api/openapi-automotive/assicurazione/{targa}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/openapi-automotive/info/{targa}` — in uso: FE
- **quarantena: verificare** — `GET /api/openapi-automotive/status` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/openapi-automotive/veicoli-da-aggiornare` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `openapi_imprese` (6)

- **attivo** — `POST /api/openapi-imprese/aggiorna-fornitore` — in uso: FE
- **attivo** — `GET /api/openapi-imprese/cerca` — in uso: FE
- **attivo** — `GET /api/openapi-imprese/info/{partita_iva}` — in uso: FE
- **quarantena: verificare** — `GET /api/openapi-imprese/pec/{partita_iva}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/openapi-imprese/sdi/{partita_iva}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/openapi-imprese/status` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `openapi_it` (11)

- **quarantena: verificare** — `POST /api/openapi/aisp/connetti-conto` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/openapi/aisp/movimenti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/openapi/aisp/status` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/openapi/visure/richiedi` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/openapi/xbrl/bilancio/{request_id}` — in uso: FE
- **attivo** — `GET /api/openapi/xbrl/download/{request_id}` — in uso: FE
- **attivo** — `GET /api/openapi/xbrl/download/{request_id}/{tipo}` — in uso: FE
- **attivo** — `POST /api/openapi/xbrl/richiedi-bilancio` — in uso: FE
- **attivo** — `POST /api/openapi/xbrl/richiedi-riclassificato` — in uso: FE
- **attivo** — `GET /api/openapi/xbrl/status` — in uso: FE
- **attivo** — `GET /api/openapi/xbrl/storico-richieste` — in uso: FE

### Router `operazioni_module` (2)

- **attivo** — `POST /api/operazioni-da-confermare/smart/ignora` — in uso: FE
- **attivo** — `POST /api/operazioni-da-confermare/smart/riconcilia-stipendio` — in uso: FE

### Router `operazioni_module.smart` (9)

- **attivo** — `GET /api/operazioni-da-confermare/smart/analizza` — in uso: FE
- **attivo** — `GET /api/operazioni-da-confermare/smart/analizza-anomalie` — in uso: FE
- **attivo** — `GET /api/operazioni-da-confermare/smart/banca-veloce` — in uso: FE
- **attivo** — `GET /api/operazioni-da-confermare/smart/cerca-f24` — in uso: FE
- **attivo** — `GET /api/operazioni-da-confermare/smart/cerca-fatture` — in uso: FE
- **attivo** — `GET /api/operazioni-da-confermare/smart/cerca-stipendi` — in uso: FE
- **attivo** — `POST /api/operazioni-da-confermare/smart/conferma-f24` — in uso: FE
- **attivo** — `GET /api/operazioni-da-confermare/smart/movimento/{movimento_id}` — in uso: FE
- **attivo** — `POST /api/operazioni-da-confermare/smart/riconcilia-manuale` — in uso: FE

### Router `pagamenti_buoni` (2)

- **quarantena: verificare** — `GET /api/pagamenti-buoni` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/pagamenti-buoni/import` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `pagopa` (8)

- **attivo** — `POST /api/pagopa/auto-associa` — in uso: FE
- **quarantena: verificare** — `POST /api/pagopa/cerca-movimenti-pagopa` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/pagopa/movimenti-agenzia-entrate` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/pagopa/ricevute` — in uso: FE
- **attivo** — `POST /api/pagopa/ricevute/associa-manuale` — in uso: FE
- **attivo** — `POST /api/pagopa/ricevute/upload` — in uso: FE
- **attivo** — `GET /api/pagopa/ricevute/{ricevuta_id}/pdf` — in uso: FE
- **attivo** — `GET /api/pagopa/stats` — in uso: FE

### Router `partite_aperte_api` (3)

- **quarantena: verificare** — `GET /api/partite-aperte/lista` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/partite-aperte/scadute` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/partite-aperte/stats` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `paypal_api` (12)

- **quarantena: verificare** — `GET /api/paypal-api/account-ids-non-mappati` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/paypal-api/account/{paypal_account_id}/cerca-fattura-email` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/paypal-api/crea-fornitore-e-mappa` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/paypal-api/mappa-fornitore` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/paypal-api/ricevuta-pdf/{transaction_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/paypal-api/riconcilia` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/paypal-api/smappa-fornitore` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/paypal-api/status` — in uso: FE, scheduler, chat
- **attivo** — `POST /api/paypal-api/sync` — in uso: FE
- **attivo** — `POST /api/paypal-api/sync/incremental` — in uso: FE
- **attivo** — `POST /api/paypal-api/sync/month` — in uso: FE
- **quarantena: verificare** — `POST /api/paypal-api/webhook` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `paypal_statements` (17)

- **attivo** — `POST /api/paypal-statements/auto-associa` — in uso: scheduler
- **quarantena: verificare** — `POST /api/paypal-statements/auto-cerca-gmail` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/paypal-statements/bank-movements` — in uso: FE
- **attivo** — `GET /api/paypal-statements/dashboard` — in uso: FE
- **quarantena: verificare** — `POST /api/paypal-statements/import-all-local` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/paypal-statements/import-csv` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/paypal-statements/import-pdf` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/paypal-statements/pulisci-match-solo-importo` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/paypal-statements/report` — in uso: FE
- **quarantena: verificare** — `POST /api/paypal-statements/riconcilia-banca` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/paypal-statements/riprocessa` — in uso: FE
- **attivo** — `GET /api/paypal-statements/statements` — in uso: FE
- **attivo** — `GET /api/paypal-statements/transactions` — in uso: FE
- **attivo** — `PUT /api/paypal-statements/transactions/{transaction_id}/descrizione` — in uso: FE
- **quarantena: verificare** — `POST /api/paypal-statements/transazione/{transaction_id}/associa` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/paypal-statements/transazione/{transaction_id}/cerca-gmail` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/paypal-statements/transazione/{transaction_id}/dettaglio` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `pianificazione` (3)

- **quarantena: verificare** — `GET /api/pianificazione/costi-previsionali` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/pianificazione/costi-previsionali` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `DELETE /api/pianificazione/costi-previsionali/{costo_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `pin_login` (2)

- **attivo** — `POST /api/auth/pin-login` — in uso: FE
- **attivo** — `GET /api/auth/pin-login/health` — in uso: FE

### Router `pos_corrispettivi_check` (9)

- **quarantena: verificare** — `GET /api/pos-corrispettivi/alert-oggi` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/pos-corrispettivi/anomalie-gravi` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `PUT /api/pos-corrispettivi/chiusura-giornaliera` — in uso: FE
- **attivo** — `GET /api/pos-corrispettivi/chiusura-giornaliera/audit` — in uso: FE
- **attivo** — `POST /api/pos-corrispettivi/chiusure-giornaliere/batch` — in uso: FE
- **attivo** — `GET /api/pos-corrispettivi/controllo-due-fasi` — in uso: FE
- **quarantena: verificare** — `POST /api/pos-corrispettivi/riconcilia-pos-giorno` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/pos-corrispettivi/riepilogo-mensile` — in uso: FE
- **attivo** — `GET /api/pos-corrispettivi/verifica-coerenza` — in uso: FE

### Router `previsioni_acquisti` (5)

- **quarantena: verificare** — `GET /api/previsioni-acquisti/confronto-ordine` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/previsioni-acquisti/popola-storico` — in uso: FE
- **attivo** — `GET /api/previsioni-acquisti/previsioni` — in uso: FE
- **quarantena: verificare** — `GET /api/previsioni-acquisti/prodotti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/previsioni-acquisti/statistiche` — in uso: FE

### Router `prima_nota_module` (2)

- **attivo** — `GET /api/prima-nota/banca/template-csv` — in uso: FE
- **attivo** — `GET /api/prima-nota/cassa/template-csv` — in uso: FE

### Router `prima_nota_module.banca` (11)

- **attivo** — `GET /api/prima-nota/banca` — in uso: FE
- **attivo** — `POST /api/prima-nota/banca` — in uso: FE
- **attivo** — `GET /api/prima-nota/banca/analisi-righe-grezze` — in uso: FE
- **attivo** — `GET /api/prima-nota/banca/candidati-per-fattura` — in uso: FE
- **attivo** — `DELETE /api/prima-nota/banca/delete-all` — in uso: FE
- **attivo** — `DELETE /api/prima-nota/banca/delete-by-source/{source}` — in uso: FE
- **attivo** — `GET /api/prima-nota/banca/in-attesa-documento` — in uso: FE
- **attivo** — `DELETE /api/prima-nota/banca/{movimento_id}` — in uso: FE
- **attivo** — `PUT /api/prima-nota/banca/{movimento_id}` — in uso: FE
- **attivo** — `GET /api/prima-nota/banca/{movimento_id}/fattura` — in uso: FE
- **attivo** — `GET /api/prima-nota/sumup` — in uso: FE

### Router `prima_nota_module.cassa` (9)

- **attivo** — `GET /api/prima-nota/cassa` — in uso: FE
- **attivo** — `POST /api/prima-nota/cassa` — in uso: FE
- **attivo** — `GET /api/prima-nota/cassa/analisi-movimenti-bancari-errati` — in uso: FE
- **attivo** — `DELETE /api/prima-nota/cassa/delete-all` — in uso: FE
- **attivo** — `DELETE /api/prima-nota/cassa/delete-by-source/{source}` — in uso: FE
- **attivo** — `DELETE /api/prima-nota/cassa/elimina-movimenti-bancari-errati` — in uso: FE
- **attivo** — `DELETE /api/prima-nota/cassa/{movimento_id}` — in uso: FE
- **attivo** — `PUT /api/prima-nota/cassa/{movimento_id}` — in uso: FE
- **attivo** — `GET /api/prima-nota/cassa/{movimento_id}/fattura` — in uso: FE

### Router `prima_nota_module.manutenzione` (26)

- **quarantena: verificare** — `POST /api/prima-nota/annulla-associazione-fattura-banca` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/prima-nota/arricchisci-pagamenti-banca` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/prima-nota/cassa/fix-corrispettivi-importo` — in uso: FE
- **attivo** — `GET /api/prima-nota/cassa/verifica-entrate-corrispettivi` — in uso: FE
- **quarantena: admin-only** — `POST /api/prima-nota/cleanup-orphan-movements` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: verificare** — `POST /api/prima-nota/collega-banca-estratto-conto` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/prima-nota/collega-corrispettivi` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/prima-nota/dedup-fatture` — in uso: FE
- **quarantena: verificare** — `POST /api/prima-nota/dedup-righe-estratto-conto` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/prima-nota/diagnostica-corrispettivi` — in uso: FE
- **attivo** — `GET /api/prima-nota/diagnostica-metodi` — in uso: FE
- **quarantena: verificare** — `POST /api/prima-nota/fix-categories-and-duplicates` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/prima-nota/fix-date-formato-italiano` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/prima-nota/fix-tipo-movimento` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/prima-nota/fix-versamenti-duplicati` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: admin-only** — `POST /api/prima-nota/migra-pos-accrediti-reali` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: admin-only** — `POST /api/prima-nota/migrazione-pulisci-bancari-cassa` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: verificare** — `GET /api/prima-nota/movimenti-ec-non-in-prima-nota` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: admin-only** — `POST /api/prima-nota/pulizia-pre-anno` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: verificare** — `POST /api/prima-nota/recalculate-balances` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/prima-nota/regenerate-from-invoices` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/prima-nota/ripristina-fatture-movimento-cancellato` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/prima-nota/ripristina-provvisori-metodo-errato` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/prima-nota/sposta-movimento` — in uso: FE
- **quarantena: verificare** — `POST /api/prima-nota/unifica-categorie` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/prima-nota/verifica-metodo-fattura/{fattura_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `prima_nota_module.operation_index` (3)

- **attivo** — `GET /api/prima-nota/indice-operazioni` — in uso: FE
- **attivo** — `PUT /api/prima-nota/indice-operazioni/{movement_id}` — in uso: FE
- **attivo** — `GET /api/prima-nota/indice-operazioni/{movement_id}/candidati` — in uso: FE

### Router `prima_nota_module.salari` (4)

- **quarantena: verificare** — `GET /api/prima-nota/salari` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/prima-nota/salari` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/prima-nota/salari/stats` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `DELETE /api/prima-nota/salari/{movimento_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `prima_nota_module.stats` (8)

- **quarantena: verificare** — `GET /api/prima-nota/anni-disponibili` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/prima-nota/export/excel` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/prima-nota/saldi-finanziari` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/prima-nota/saldo-finale` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/prima-nota/saldo-iniziale` — in uso: FE
- **attivo** — `PUT /api/prima-nota/saldo-iniziale` — in uso: FE
- **attivo** — `DELETE /api/prima-nota/saldo-iniziale/{tipo}/{anno}` — in uso: FE
- **attivo** — `GET /api/prima-nota/stats` — in uso: FE

### Router `prima_nota_module.sync` (23)

- **attivo** — `POST /api/prima-nota/banca/sync-estratto-conto` — in uso: FE
- **attivo** — `POST /api/prima-nota/cassa/crea-entrata-da-corrispettivo` — in uso: FE
- **attivo** — `POST /api/prima-nota/cassa/sync-corrispettivi` — in uso: FE
- **attivo** — `POST /api/prima-nota/cassa/sync-fatture-pagate` — in uso: FE
- **quarantena: verificare** — `POST /api/prima-nota/collega-fatture` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/prima-nota/corrispettivi-status` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/prima-nota/import-batch` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/prima-nota/movimento` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/prima-nota/provvisori` — in uso: FE
- **attivo** — `POST /api/prima-nota/provvisori/annulla-auto-conferma` — in uso: FE
- **attivo** — `GET /api/prima-nota/provvisori/assegni-proposti` — in uso: FE
- **attivo** — `POST /api/prima-nota/provvisori/associa-assegno` — in uso: FE
- **attivo** — `POST /api/prima-nota/provvisori/attendi-banca` — in uso: FE
- **attivo** — `POST /api/prima-nota/provvisori/auto-conferma-per-metodo` — in uso: FE
- **attivo** — `POST /api/prima-nota/provvisori/conferma` — in uso: FE
- **attivo** — `POST /api/prima-nota/provvisori/conferma-divisione` — in uso: FE
- **attivo** — `POST /api/prima-nota/provvisori/conferma-multipla` — in uso: FE
- **attivo** — `POST /api/prima-nota/provvisori/da-decidere` — in uso: FE
- **attivo** — `POST /api/prima-nota/provvisori/segnala-dubbio` — in uso: FE
- **quarantena: verificare** — `POST /api/prima-nota/registra-fattura` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/prima-nota/sposta-cassa-pagate-in-banca` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/prima-nota/sposta-scrittura` — in uso: FE
- **quarantena: verificare** — `POST /api/prima-nota/sync-corrispettivi` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `public_api` (26)

- **attivo** — `POST /api/assegni` — in uso: FE
- **quarantena: verificare** — `GET /api/assegni-legacy` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/bank/statements` — in uso: FE
- **attivo** — `POST /api/bank/statements` — in uso: FE
- **attivo** — `GET /api/cash` — in uso: FE
- **attivo** — `POST /api/cash` — in uso: FE
- **quarantena: verificare** — `GET /api/dashboard/stats-legacy` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-public/alerts` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/f24-public/dashboard` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/pianificazione/events` — in uso: FE
- **attivo** — `POST /api/pianificazione/events` — in uso: FE
- **quarantena: verificare** — `POST /api/portal/upload` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/ricerca-globale` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/suppliers-legacy` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/suppliers/{supplier_id}/inventory` — in uso: FE
- **quarantena: verificare** — `GET /api/v1/fatture` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/v1/keys` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/v1/keys/generate` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/v1/movimenti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/v1/stats` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/warehouse/movements` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/warehouse/movements` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/warehouse/products` — in uso: FE
- **attivo** — `POST /api/warehouse/products` — in uso: FE
- **attivo** — `DELETE /api/warehouse/products/{product_id}` — in uso: FE
- **attivo** — `PUT /api/warehouse/products/{product_id}` — in uso: FE

### Router `rapido` (8)

- **attivo** — `POST /api/rapido/acconto-dipendente` — in uso: FE
- **attivo** — `POST /api/rapido/apporto-soci` — in uso: FE
- **attivo** — `POST /api/rapido/corrispettivo` — in uso: FE
- **attivo** — `GET /api/rapido/dipendenti-attivi` — in uso: FE, chat
- **attivo** — `POST /api/rapido/paga-fattura` — in uso: FE
- **attivo** — `POST /api/rapido/presenza` — in uso: FE
- **attivo** — `GET /api/rapido/ultimi-inserimenti` — in uso: FE
- **attivo** — `POST /api/rapido/versamento-banca` — in uso: FE

### Router `reports.dashboard` (9)

- **quarantena: verificare** — `GET /api/dashboard/bilancio-istantaneo` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/dashboard/confronto-annuale` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/dashboard/fascia-energia` — in uso: FE
- **quarantena: verificare** — `GET /api/dashboard/kpi` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/dashboard/spese-per-categoria` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/dashboard/stato-riconciliazione` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/dashboard/stats` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/dashboard/summary` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/dashboard/trend-mensile` — in uso: FE, chat

### Router `riconciliazione_stats_api` (1)

- **quarantena: verificare** — `GET /api/riconciliazione/stats` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `ritenute` (4)

- **attivo** — `GET /api/ritenute` — in uso: FE
- **attivo** — `GET /api/ritenute/codici-ravvedimento` — in uso: FE
- **attivo** — `POST /api/ritenute/scan` — in uso: FE
- **attivo** — `GET /api/ritenute/verifica-caso-1040` — in uso: FE

### Router `scadenzario_fornitori` (6)

- **attivo** — `GET /api/scadenzario-fornitori/` — in uso: FE
- **attivo** — `PUT /api/scadenzario-fornitori/aggiorna-scadenza` — in uso: FE
- **attivo** — `GET /api/scadenzario-fornitori/aging` — in uso: FE
- **attivo** — `GET /api/scadenzario-fornitori/cash-flow-previsionale` — in uso: FE
- **attivo** — `GET /api/scadenzario-fornitori/scadenze-integrate` — in uso: FE
- **attivo** — `GET /api/scadenzario-fornitori/urgenti` — in uso: FE

### Router `scadenze` (9)

- **attivo** — `GET /api/scadenze` — in uso: FE
- **attivo** — `GET /api/scadenze/` — in uso: FE
- **attivo** — `PUT /api/scadenze/completa/{notifica_id}` — in uso: FE
- **attivo** — `POST /api/scadenze/crea` — in uso: FE
- **attivo** — `GET /api/scadenze/dashboard-widget` — in uso: FE
- **attivo** — `GET /api/scadenze/iva-mensile/{anno}` — in uso: FE
- **attivo** — `GET /api/scadenze/prossime` — in uso: FE
- **attivo** — `GET /api/scadenze/tutte` — in uso: FE
- **attivo** — `DELETE /api/scadenze/{notifica_id}` — in uso: FE

### Router `settings` (6)

- **attivo** — `GET /api/settings` — in uso: FE
- **attivo** — `PUT /api/settings` — in uso: FE
- **quarantena: verificare** — `GET /api/settings/logo` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/settings/logo` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/settings/user-preferences` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `PUT /api/settings/user-preferences` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `settings_router` (9)

- **quarantena: verificare** — `GET /api/settings/anthropic` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/settings/anthropic` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/settings/anthropic/test` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/settings/gmail` — in uso: FE
- **attivo** — `POST /api/settings/gmail` — in uso: FE
- **attivo** — `POST /api/settings/gmail/test` — in uso: FE
- **attivo** — `GET /api/settings/openai` — in uso: FE
- **attivo** — `POST /api/settings/openai` — in uso: FE
- **attivo** — `POST /api/settings/openai/test` — in uso: FE

### Router `sumup` (7)

- **quarantena: verificare** — `POST /api/sumup/bonifica-accrediti-numia` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/sumup/bonifica-pos-xml` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/sumup/bonifica-pos-xml` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/sumup/normalizza-descrizioni-pos` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/sumup/riepilogo` — in uso: FE
- **quarantena: verificare** — `POST /api/sumup/sincronizza` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/sumup/stato` — in uso: FE

### Router `suppliers_module.base` (16)

- **attivo** — `GET /api/suppliers` — in uso: FE
- **attivo** — `POST /api/suppliers` — in uso: FE
- **attivo** — `GET /api/suppliers/filtered` — in uso: FE
- **attivo** — `GET /api/suppliers/scadenze` — in uso: FE
- **attivo** — `GET /api/suppliers/search-piva/{partita_iva}` — in uso: FE
- **attivo** — `GET /api/suppliers/stats` — in uso: FE
- **attivo** — `DELETE /api/suppliers/{supplier_id}` — in uso: FE
- **attivo** — `GET /api/suppliers/{supplier_id}` — in uso: FE
- **attivo** — `PUT /api/suppliers/{supplier_id}` — in uso: FE
- **attivo** — `GET /api/suppliers/{supplier_id}/dati-da-fatture` — in uso: FE
- **attivo** — `GET /api/suppliers/{supplier_id}/fatturato` — in uso: FE
- **attivo** — `GET /api/suppliers/{supplier_id}/fatture` — in uso: FE
- **attivo** — `GET /api/suppliers/{supplier_id}/iban-from-invoices` — in uso: FE
- **attivo** — `PUT /api/suppliers/{supplier_id}/metodo-pagamento` — in uso: FE
- **attivo** — `PUT /api/suppliers/{supplier_id}/nome` — in uso: FE
- **attivo** — `POST /api/suppliers/{supplier_id}/toggle-active` — in uso: FE

### Router `suppliers_module.bulk` (6)

- **attivo** — `POST /api/suppliers/aggiorna-metodi-bulk` — in uso: FE
- **attivo** — `POST /api/suppliers/aggiorna-tutti-bulk` — in uso: FE
- **attivo** — `POST /api/suppliers/correggi-nomi-mancanti` — in uso: FE
- **attivo** — `POST /api/suppliers/elimina-senza-fatture` — in uso: FE
- **attivo** — `POST /api/suppliers/ripara-sconosciuti` — in uso: FE
- **attivo** — `POST /api/suppliers/sincronizza-da-fatture` — in uso: FE

### Router `suppliers_module.iban` (3)

- **attivo** — `POST /api/suppliers/ricerca-iban-singolo/{supplier_id}` — in uso: FE
- **attivo** — `POST /api/suppliers/ricerca-iban-web` — in uso: FE
- **attivo** — `POST /api/suppliers/sync-iban` — in uso: FE

### Router `suppliers_module.import_export` (2)

- **attivo** — `POST /api/suppliers/import-excel` — in uso: FE
- **attivo** — `POST /api/suppliers/upload-excel` — in uso: FE

### Router `suppliers_module.validation` (5)

- **attivo** — `POST /api/suppliers/aggiorna-dizionario-metodo` — in uso: FE
- **attivo** — `GET /api/suppliers/dizionario-metodi-pagamento` — in uso: FE
- **attivo** — `GET /api/suppliers/payment-methods` — in uso: FE
- **attivo** — `GET /api/suppliers/payment-terms` — in uso: FE
- **attivo** — `GET /api/suppliers/validazione-p0` — in uso: FE

### Router `sync_relazionale` (8)

- **quarantena: verificare** — `GET /api/sync/fatture-cassa-dettaglio` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/sync/match-fatture-banca` — in uso: FE
- **attivo** — `POST /api/sync/match-fatture-cassa` — in uso: FE
- **attivo** — `GET /api/sync/stato-sincronizzazione` — in uso: FE
- **quarantena: verificare** — `POST /api/sync/sync-all-corrispettivi` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/sync/sync-corrispettivo/{corrispettivo_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/sync/sync-fattura/{fattura_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `PUT /api/sync/update-fattura-everywhere/{fattura_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `tfr` (17)

- **quarantena: verificare** — `POST /api/tfr/accantonamento` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/tfr/acconti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `DELETE /api/tfr/acconti/{acconto_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `PUT /api/tfr/acconti/{acconto_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/tfr/acconti/{acconto_id}/annulla-riconciliazione-banca` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/tfr/acconti/{acconto_id}/candidati-banca` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/tfr/acconti/{acconto_id}/riconcilia-banca` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/tfr/acconti/{dipendente_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/tfr/calcola-batch/{anno}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/tfr/cedolini/{cedolino_id}/annulla-scalatura-acconti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/tfr/cedolini/{cedolino_id}/preview-scalatura-acconti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/tfr/cedolini/{cedolino_id}/scala-acconti` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/tfr/liquidazione` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/tfr/parse-payslips` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/tfr/riepilogo-aziendale` — in uso: FE
- **attivo** — `GET /api/tfr/situazione/{dipendente_id}` — in uso: FE
- **quarantena: verificare** — `GET /api/tfr/storico-tfr/{dipendente_id}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `utenti` (4)

- **attivo** — `GET /api/utenti` — in uso: FE
- **attivo** — `POST /api/utenti` — in uso: FE
- **attivo** — `DELETE /api/utenti/{utente_id}` — in uso: FE
- **attivo** — `PUT /api/utenti/{utente_id}` — in uso: FE

### Router `verbali_noleggio` (7)

- **attivo** — `POST /api/verbali-noleggio/associa-pdf/{numero_verbale:path}` — in uso: FE
- **attivo** — `POST /api/verbali-noleggio/correggi-importo/{numero_verbale:path}` — in uso: FE
- **attivo** — `POST /api/verbali-noleggio/correggi-trasgressore/{numero_verbale:path}` — in uso: FE
- **attivo** — `GET /api/verbali-noleggio/dettaglio/{numero_verbale}` — in uso: FE
- **attivo** — `GET /api/verbali-noleggio/pdf/{numero_verbale:path}` — in uso: FE
- **attivo** — `POST /api/verbali-noleggio/ricalcola-pdf/{numero_verbale:path}` — in uso: FE
- **attivo** — `GET /api/verbali-noleggio/verbali-completi` — in uso: chat

### Router `verbali_noleggio_api` (2)

- **attivo** — `GET /api/verbali-noleggio/dettaglio/{numero_verbale:path}` — in uso: FE, scheduler
- **attivo** — `POST /api/verbali-noleggio/{verbale_id}/upload-quietanza` — in uso: scheduler

### Router `verbali_riconciliazione` (10)

- **attivo** — `POST /api/verbali-riconciliazione/collega-driver-massivo` — in uso: FE, scheduler
- **attivo** — `GET /api/verbali-riconciliazione/dashboard` — in uso: FE, scheduler
- **attivo** — `POST /api/verbali-riconciliazione/import-partenopay` — in uso: scheduler
- **attivo** — `GET /api/verbali-riconciliazione/lista` — in uso: FE, scheduler
- **quarantena: admin-only** — `POST /api/verbali-riconciliazione/migra-attesa-quietanza` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **attivo** — `POST /api/verbali-riconciliazione/pulisci-duplicati` — in uso: FE, scheduler
- **attivo** — `POST /api/verbali-riconciliazione/riconcilia/{numero_verbale}` — in uso: FE, scheduler
- **attivo** — `POST /api/verbali-riconciliazione/scan-email` — in uso: FE, scheduler
- **attivo** — `POST /api/verbali-riconciliazione/scan-fatture-verbali` — in uso: FE, scheduler
- **attivo** — `POST /api/verbali-riconciliazione/scan-gmail-attendibili` — in uso: scheduler

### Router `verifica_coerenza` (7)

- **attivo** — `GET /api/verifica-coerenza/completa/{anno}` — in uso: FE
- **attivo** — `GET /api/verifica-coerenza/confronto-iva-completo/{anno}` — in uso: FE
- **quarantena: verificare** — `GET /api/verifica-coerenza/discrepanze/{anno}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `GET /api/verifica-coerenza/iva/{anno}/{mese}` — in uso: FE
- **quarantena: verificare** — `GET /api/verifica-coerenza/riepilogo-giornaliero` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/verifica-coerenza/verifica-bonifici-vs-banca/{anno}` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/verifica-coerenza/widget` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

### Router `voci_bilancio` (4)

- **attivo** — `POST /api/voci-bilancio/` — in uso: FE
- **attivo** — `GET /api/voci-bilancio/codici-disponibili` — in uso: FE
- **attivo** — `GET /api/voci-bilancio/{anno}` — in uso: FE
- **attivo** — `DELETE /api/voci-bilancio/{voce_id}` — in uso: FE

### Router `warehouse.dizionario_articoli` (11)

- **attivo** — `PUT /api/dizionario-articoli/articolo/{descrizione_encoded}` — in uso: FE
- **quarantena: verificare** — `POST /api/dizionario-articoli/categorizza-ai` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/dizionario-articoli/cerca` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/dizionario-articoli/dizionario` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/dizionario-articoli/estrai-articoli` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `POST /api/dizionario-articoli/genera-dizionario` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: verificare** — `GET /api/dizionario-articoli/non-classificati` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **quarantena: admin-only** — `DELETE /api/dizionario-articoli/reset-dizionario` — endpoint di migrazione/manutenzione one-shot: tenere ma Admin-only, disabilitabile, documentato, non esposto a lungo (§7)
- **quarantena: verificare** — `POST /api/dizionario-articoli/ricategorizza-fatture` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare
- **attivo** — `POST /api/dizionario-articoli/riclassifica-completo` — in uso: FE
- **quarantena: verificare** — `GET /api/dizionario-articoli/statistiche` — nessun riferimento noto (FE/scheduler/chat/test): verificare prima di deprecare

## Appendice E — Provenienza della specifica

Rigenerato il 2026-08-21 dal contenuto versionato con `python scripts/genera_prompt_master.py`. Fonti: codice, `page_catalog.json`, `app/config.py`, `render.yaml`, mappe endpoint generate e test correnti. Nessun valore di credenziale è incluso.

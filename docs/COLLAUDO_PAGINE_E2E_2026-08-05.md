# Registro numerato collaudo pagine GestionaleCloud

Data avvio: 2026-08-05
Repository canonico: `ceraldicontabilita/GestionaleCloud`
Regola di chiusura: una pagina viene marcata `[x]` solo dopo verifica di route React, API/backend, test automatici e collaudo live con dati reali in sola lettura.

## Conteggio corrente verificato dal codice

- 31 registrazioni `path:` nel router React principale (famiglie canoniche e wildcard).
- 62 schermate funzionali distinte.
- 1 pagina tecnica 404, non operativa.
- 51 redirect legacy esatti e 29 redirect per prefisso: sono compatibilita per vecchi link, non pagine aggiuntive.
- 0 pagine autorizzate alla rimozione in questa fase: nessuna sara eliminata senza prova di inutilizzo e senza verificare i collegamenti.
- 2 rami UI interni duplicati gia individuati in RiconciliazioneUnificata (`assegni` e `paypal`), oggi intercettati dalle pagine canoniche dedicate: candidati a pulizia del codice, non sono due pagine ulteriori.

## Stati

- `[ ] DA COLLAUDARE`: inventariata, non ancora chiusa end-to-end.
- `[ ] IN CORREZIONE`: difetto reale riprodotto e correzione in corso.
- `[x] VERIFICATA`: test e collaudo live conclusi.
- `ACCORPARE` / `ELIMINARE`: decisione ammessa solo con prova di sovrapposizione o assenza di chiamanti.

## 2026-08-06 - fondazione del collaudo verificabile

- Aggiunto `page_catalog.json`: fonte macchina numerata delle 62 schermate, con
  route, componente React, entrypoint, livello di accesso e stato audit.
- Il catalogo e il registro Markdown devono coincidere 1:1; sei test bloccano
  id mancanti, route duplicate, componenti assenti, hub non importati e URL
  storici spacciati per pagine (`/magazzino`, `/dipendenti`, `/cedolini`).
- Corretto lo smoke runtime: una risposta HTTP 200 della SPA e ora dichiarata
  `delivery_only` e non viene piu presentata come pagina funzionante. Senza
  token, HTTP 401 dimostra soltanto che l'endpoint protetto esiste.
- Aggiunto un E2E Playwright autenticato contro router reali e MongoDB in
  memoria. Apre tutte le 62 schermate e fallisce per 404, ErrorBoundary React,
  errori JavaScript o API iniziali non valide, senza leggere dati aziendali.
- Primo passaggio: 58/62. Difetti trovati e corretti: serializzazione ObjectId
  nelle regole del Piano dei Conti, URL inesistente nel Controllo mensile,
  lock Documenti chiamato fuori dal router canonico e 404 fixture duplicato.
- Secondo passaggio completo: **62/62 aperture superate**. Questo certifica
  route, montaggio e caricamento iniziale nel sistema isolato; non certifica
  ancora la correttezza contabile dei dati reali. Restano pertanto visibili nel
  catalogo **5 verificate, 8 in revisione e 49 non ancora verificate nel merito**.
- Suite completa dopo le correzioni: **1.185 backend passati, 2 saltati** e
  **111 frontend passati**. Build Vite di produzione completata; artefatti
  generati rimossi dal working tree.

## Pagine, una per una

| N. | Stato | Pagina e percorso canonico | Cosa fa | Decisione preliminare |
|---:|:---:|---|---|---|
| 1 | [ ] | Login — `/login` | Autentica l'utente e apre la sessione del gestionale. | TENERE |
| 2 | [ ] | Gestione riservata — `/gestione-riservata` | Accesso separato alle funzioni riservate previste dall'app. | VERIFICARE UTILIZZO |
| 3 | [ ] | Dashboard — `/` | KPI reali di ricavi, costi, margine, cassa, banca, IVA e scadenze per anno/mese. | TENERE |
| 4 | [ ] | Dashboard relazionale — `/dashboard-relazionale` | Mostra alert, partite aperte e stato delle riconciliazioni tra entita. | TENERE |
| 5 | [ ] | Inserimento rapido — `/rapido` | Inserisce operazioni operative guidate (corrispettivo, POS, banca, soci, personale). | TENERE CON GUARDIE ANTI-DUPLICATO |
| 6 | [ ] | Archivio fatture — `/fatture` | Cerca e consulta fatture ricevute, stato pagamento, XML/PDF e dati fornitore. | TENERE |
| 7 | [ ] | Corrispettivi — `/fatture/corrispettivi` | Consulta gli XML dei corrispettivi e i totali contanti/POS/IVA. | TENERE |
| 8 | [ ] | Fornitori — `/fornitori` | Anagrafica fornitori, P.IVA, metodi di pagamento e documenti collegati. | TENERE |
| 9 | [~] IN REVISIONE | Prima Nota — `/prima-nota` | Espone Cassa, Banca, Provvisori e finanziamenti soci senza duplicare le fonti. | TENERE |
| 10 | [ ] | Pulizia Prima Nota — `/prima-nota/pulizia` | Diagnostica e propone deduplica/quadratura controllata della Prima Nota. | TENERE COME STRUMENTO AMMINISTRATIVO |
| 11 | [ ] | Cedolini e salari — `/salari` | Gestisce cedolini, bonifici, saldo/acconto e riconciliazione paga. | TENERE |
| 12 | [ ] | Flotta noleggio — `/noleggio` | Veicoli, contratti, driver storico e costi ricavati dalle fatture. | TENERE |
| 13 | [ ] IN CORREZIONE | Verbali noleggio — `/noleggio/verbali` | Verbali da email/documenti, targa, driver alla data, fattura, PagoPA e pagamento. | TENERE |
| 14 | [ ] IN CORREZIONE | Costi noleggio — `/noleggio/costi` | Riepiloga canoni, verbali, bollo, pedaggi e altri costi per veicolo. | TENERE |
| 15 | [x] VERIFICATA | Dettaglio verbale — `/verbali-noleggio/:identificativo` | Mostra la singola catena Verbale -> veicolo -> driver -> fattura -> pagamento. | TENERE |
| 16 | [x] VERIFICATA | Piano dei Conti — `/contabilita` | Mostra un solo conto per codice e i saldi derivati dalle fonti contabili. | TENERE |
| 17 | [ ] IN CORREZIONE | Bilancio — `/contabilita/bilancio` | Stato patrimoniale e conto economico per periodo. | TENERE |
| 18 | [ ] IN CORREZIONE | Verifica Bilancio — `/contabilita/verifica` | Controlla quadrature e incoerenze del bilancio. | TENERE |
| 19 | [ ] IN CORREZIONE | Libro Giornale — `/contabilita/giornale` | Elenca le scritture contabili cronologiche e i mastri. | TENERE |
| 20 | [ ] IN CORREZIONE | Controllo mensile — `/contabilita/controllo` | Incrocia mensilmente fatture, corrispettivi, banca e Prima Nota. | TENERE |
| 21 | [ ] IN CORREZIONE | Calendario fiscale — `/contabilita/calendario` | Scadenze fiscali operative con fonte, applicabilita ed evidenza del completamento. | TENERE |
| 22 | [ ] IN CORREZIONE | Cespiti — `/contabilita/cespiti` | Beni strumentali, ammortamenti e verifiche collegate. | TENERE |
| 23 | [x] VERIFICATA | Finanziaria — `/contabilita/finanziaria` | Distingue flussi annuali, riporti e disponibilita contabile; IVA solo come stima documentale. | TENERE |
| 24 | [x] VERIFICATA | Chiusura esercizio — `/contabilita/chiusura` | Verifiche preliminari e procedura controllata di chiusura. | TENERE CON CONFERMA FORTE |
| 25 | [ ] | Budget — `/contabilita/budget` | Budget annuale e confronto con consuntivo. | TENERE |
| 26 | [ ] | Mutui — `/contabilita/mutui` | Piano mutui, rate e riconciliazione. | TENERE SE DATI PRESENTI |
| 27 | [ ] | Contabilita avanzata — `/contabilita/avanzata` | Imposte, disponibilita, ricategorizzazione e analisi avanzate. | VERIFICARE SOVRAPPOSIZIONI |
| 28 | [ ] | Utile obiettivo — `/contabilita/utile` | Simula obiettivo economico e centri di costo. | TENERE SE UTILIZZATO |
| 29 | [ ] | Previsioni acquisti — `/contabilita/previsioni-acquisti` | Analizza quantita acquistate per anno e suggerisce fabbisogni. | TENERE; MOSTRARE QUANTITA ANNO CORRENTE |
| 30 | [ ] | Learning Machine — `/learning-machine` | Gestisce regole apprese per fornitori, assegni, documenti e categorizzazione. | TENERE, RIDURRE TAB DUPLICATE |
| 31 | [ ] | Scadenze — `/scadenze` | Fatture, adempimenti e documenti ancora da riconciliare; l'IVA operativa e nella pagina 61. | TENERE |
| 32 | [ ] | Ritenute — `/ritenute` | Ritenute per fattura, F24 multi-tributo, scadenza e stato di versamento. | TENERE |
| 33 | [ ] | Riconciliazione dashboard — `/riconciliazione` | Riepiloga operazioni banca e documenti da confermare. | TENERE |
| 34 | [ ] | Riconciliazione banca — `/riconciliazione/banca` | Collega movimenti di estratto conto a entita certe o crea proposte. | TENERE |
| 35 | [ ] | Riconciliazione F24 — `/riconciliazione/f24` | Legge tributi multipli e propone associazioni supervisionate. | TENERE |
| 36 | [ ] | Riconciliazione stipendi — `/riconciliazione/stipendi` | Confronta bonifici paga, cedolini, acconti e saldi. | TENERE |
| 37 | [ ] | Riconciliazione documenti — `/riconciliazione/documenti` | Associa documenti non collegati senza creare legami ambigui. | TENERE |
| 38 | [ ] | Archivio bonifici — `/riconciliazione/archivio-bonifici` | Consulta bonifici e propone associazioni a salari o fatture. | TENERE; BLOCCARE FATTURA SU DIPENDENTE |
| 39 | [ ] | Assegni — `/riconciliazione/assegni` | Carnet, assegni, incasso e associazione fatture con regola stretta. | TENERE |
| 40 | [~] IN REVISIONE | PayPal — `/riconciliazione/paypal` | Transazioni, movimenti banca, documenti e mapping fornitori PayPal. | TENERE |
| 41 | [ ] | Coerenza POS — `/riconciliazione/coerenza-pos` | Confronta XML corrispettivi, chiusure reali POS e accrediti banca. | TENERE |
| 42 | [ ] | Import documenti — `/documenti/import` | Unico ingresso per PDF/XML/ZIP con classificazione e deduplica. | TENERE COME INGRESSO UNICO |
| 43 | [ ] | Archivio documenti — `/documenti/archivio` | Consulta file, esiti, anomalie, provenienza e collegamenti. | TENERE |
| 44 | [ ] | Verifica coerenza — `/strumenti` | Controlli incrociati in sola lettura; non esegue correzioni automatiche. | TENERE |
| 45 | [ ] | Movimenti banca — `/strumenti/movimenti-banca` | Elenca movimenti non collegati e deve solo proporre, senza duplicare Prima Nota. | TENERE IN SOLA PROPOSTA |
| 46 | [ ] | Commercialista — `/strumenti/commercialista` | Prepara riepiloghi e pacchetti di confronto per il commercialista. | TENERE |
| 47 | [ ] | Pianificazione — `/strumenti/pianificazione` | Pianifica flussi e scadenze future. | VERIFICARE UTILIZZO |
| 48 | [ ] | Visure — `/strumenti/visure` | Consulta/richiede informazioni camerali collegate. | TENERE SE SERVIZIO CONFIGURATO |
| 49 | [ ] | Agenti AI — `/agenti` | Mostra segnalazioni, decisioni supervisionate e stato automazioni. | TENERE COME CONTROLLO, NON COME SECONDA UI OPERATIVA |
| 50 | [ ] | Impostazioni F24 email — `/impostazioni-f24-email` | Credenziali, mittenti F24, scansioni e log di acquisizione. | VALUTARE ACCORPAMENTO CON 54 |
| 51 | [ ] | Impostazioni AI — `/impostazioni-ai` | Configurazione dei servizi AI usati dal gestionale. | TENERE SOLO ADMIN |
| 52 | [ ] | Integrazione OpenAPI — `/integrazioni` | Richiede dati e bilanci ufficiali da OpenAPI.it. | TENERE SE CONFIGURATA |
| 53 | [ ] | Integrazione PagoPA — `/integrazioni/pagopa` | Gestisce avvisi/ricevute PagoPA e collegamenti ai verbali. | TENERE |
| 54 | [x] VERIFICATA | Mittenti Email attendibili — `/integrazioni/mittenti-email` | Fonte unica dei mittenti autorizzati per classificare allegati email. | TENERE; FONTE DEL FLUSSO VERBALI |
| 55 | [ ] | Admin sistema — `/admin` | Stato servizi, email, Drive, rollback controllato e collaudo. | TENERE SOLO ADMIN |
| 56 | [ ] | Admin MFA — `/admin/mfa` | Configura e controlla autenticazione multifattore. | TENERE SOLO ADMIN |
| 57 | [ ] | Batch reprocessing — `/admin/batch-reprocessing` | Anteprima e rilavorazione controllata di F24/cedolini. | CANDIDATA AD ACCORPAMENTO CON 58 |
| 58 | [ ] | Batch processor — `/admin/batch-processor` | Esegue task batch tecnici configurati. | CANDIDATA AD ACCORPAMENTO CON 57 |
| 59 | [ ] | Utenti — `/utenti` | Gestisce ruoli, stato, PIN e accessi. | TENERE SOLO ADMIN |
| 60 | [ ] | Mappa gestionale — `/mappa-gestionale` | Documenta i collegamenti tra aree del gestionale. | VALUTARE RIMOZIONE DAL MENU OPERATIVO |
| 61 | [ ] | Gestione IVA — `/iva` | Unica pagina IVA: attribuzione fatture, liquidazione mensile, confronto F24 e scadenze. | TENERE COME PAGINA IVA UNICA |
| 62 | [ ] | Verifica fatture estere — `/fatture-estere-verifica` | Verifica dati fiscali delle fatture estere acquisite da email/documenti. | TENERE |

## Pagina tecnica

| Stato | Pagina | Scopo |
|:---:|---|---|
| [ ] | 404 — wildcard non riconosciuta | Comunica un percorso inesistente senza mostrare una schermata operativa falsa. |

## Evidenze progressive

### 2026-08-05 — Pagina 16 Piano dei Conti

- Riprodotto live il blocco permanente su `Caricamento Piano dei Conti...`.
- Misurato sul database reale il join righe fattura -> `dizionario_articoli`: circa 14,4 secondi senza indice.
- Creati gli indici `idx_dizionario_descrizione` e `idx_invoices_invoice_date` sul database reale.
- Nuova misura dello stesso join: circa 1,1 secondi al primo giro e 0,6 secondi al secondo.
- Ripetuto collaudo live: pagina caricata in circa 2 secondi; 22 righe visibili nelle categorie aperte, 22 codici univoci, 0 duplicati visibili.
- Correzione permanente nel codice in corso: indici all'avvio e rimozione del secondo calcolo saldi duplicato dal frontend.
- Suite completa locale dopo la correzione: 1092 test backend superati, 2 saltati; 79 test frontend superati; build di produzione completato.
- Correzione pubblicata su `main` con merge `b54a99fb64bb5a5d9ad42f50a16f21c1a4a6a913`; deploy Render `dep-d9pp5fht0dsc738cc3jg` concluso con stato live.
- Collaudo post-deploy con dati reali in sola lettura: 31 conti totali, 22 righe nelle sezioni aperte, 22 codici distinti e nessun duplicato visualizzato. Pagina 16 chiusa.

### 2026-08-05 — Pagine 13 e 54 Verbali / Mittenti attendibili

- Collaudo live pagina Mittenti Email: 0 mittenti configurati nella collezione canonica e 0 nella collezione legacy.
- Verifica Gmail in sola lettura: presenti numerose notifiche ufficiali con allegati PDF di Polizia Locale Napoli e ASIA Napoli destinate a Ceraldi Group.
- Difetto riprodotto nel codice: lo scanner accettava anche un mittente non attendibile quando l'oggetto conteneva parole come `verbale` o `sanzione`.
- Difetto riprodotto nel codice: `posta-certificata@pec.aruba.it` era trattato come attendibile, ma è solo il trasportatore di PEC provenienti da mittenti diversi.
- Difetto riprodotto nel codice: la UI salva il tipo `verbale`, mentre lo scanner cercava soltanto il tipo storico `verbale_cds`.
- Difetto riprodotto nel codice: i PDF venivano conservati solo in `/tmp`, senza copia permanente in `documents_inbox` e senza archivio Drive.
- Aperto un allegato reale ASIA in sola lettura: è un PDF scansionato di due pagine, senza testo incorporato; contiene il verbale `VV/24990121765` per CERALDI GROUP SRL e non contiene una targa. Il vecchio parser testuale non poteva acquisirlo correttamente.
- Correzione locale: mittenti istituzionali espliciti e idempotenti, filtro obbligatorio sul mittente originario, supporto credenziali Gmail configurate in Admin, hash anti-duplicato, classificazione del PDF, copia applicativa e archivio Drive.
- Correzione locale: fallback OCR/vision strutturato per PDF scansionati e distinzione tra verbale amministrativo senza targa e verbale collegato a un veicolo.
- Aggiunto endpoint amministrativo separato `scan-gmail-attendibili`, che non richiama gli scanner legacy più permissivi e non marca i messaggi come letti.
- Impedita la creazione di verbali anonimi dal pre-parser email: se numero/IUV non sono ancora disponibili, è il PDF classificato a creare l'unica entità corretta.
- Test finali locali: 1092 backend superati, 2 saltati; 79 frontend superati; build di produzione completato. Le mappe tecniche risultano allineate ai 1047 endpoint backend realmente montati.
- Correzione pubblicata su `main` con merge `b54a99fb64bb5a5d9ad42f50a16f21c1a4a6a913` e verificata dopo il deploy: 7 mittenti attendibili presenti, ASIA Napoli inclusa e il trasportatore generico Aruba escluso. Pagina 54 chiusa.
- Scansione pilota reale Gmail su 120 giorni, limitata ai mittenti attendibili: 5 messaggi trovati, 8 PDF nuovi salvati in `documents_inbox`, 3 verbali identificati, 0 errori, 0 gruppi hash duplicati e 0 verbali anonimi.
- Documenti reali acquisiti: due verbali amministrativi ASIA (`VV/24990121765`, `VV/26990000054`) e tre coppie copia conforme/relata per i verbali `B26120386585`, `B26120386528`, `A26110369901`.
- La cartella Drive reale risolta e' `Verbali Auto/Elaborate`. Il caricamento automatico e' attualmente bloccato dalla quota propria dell'account di servizio; la copia applicativa resta integra. La pagina 13 rimane `IN CORREZIONE` finche' le otto copie non sono verificate anche su Drive e il flusso proprietario/OAuth non e' collaudato.

### 2026-08-05 — Rafforzamento Gmail/Drive pagina 13

- Riconosciuti anche gli alias di ambiente realmente configurati per l'account Gmail amministrativo, senza duplicare o rinominare segreti.
- Normalizzati i nomi degli allegati MIME per eliminare a-capo e spazi anomali prima del salvataggio.
- Risolta l'area reale `verbali_auto` e, quando presente, la destinazione di ciclo `Elaborate`.
- Estesa la deduplica Drive al checksum MD5 nativo, così rileva anche file caricati con account proprietario senza `appProperties`.
- Un documento con stato `archived`, `duplicate` o `archived_manual_oauth` non viene più ritrasmesso dalle scansioni Gmail successive.
- I blocchi di quota/permesso Drive sono ora registrati come `blocked_owner_auth` con motivazione tecnica, senza perdere la copia applicativa.
- Suite completa: 1098 test backend superati, 2 saltati; 79 test frontend superati; build di produzione completato e artefatti generati ripuliti dal working tree.

### 2026-08-05 — Pagina 15 Dettaglio verbale

- Difetto riprodotto sul deploy reale con `VV/24990121765`: il dettaglio si apriva ma indicava `PDF disponibili: 0`, benché il documento fosse presente e processato in `documents_inbox`.
- Causa: gli endpoint dettaglio/PDF leggevano soltanto i vecchi campi binari incorporati nel verbale e ignoravano la relazione `document_ids` / `source_document_id` creata dal nuovo import Gmail.
- Correzione in corso: vista PDF unica per formati storici e `documents_inbox`, metadati leggeri nel dettaglio e download per indice anche per numeri verbale contenenti `/`.
- Test locali dopo la correzione: 1101 backend superati, 2 saltati; 79 frontend superati. La pagina resta aperta fino al collaudo post-deploy con il PDF reale.
- Correzione pubblicata su `main` con merge `3cc02983ccf066ebf4cb6dbdabcdac89e458fea9`; deploy Render `dep-d9ppolrbc2fs73apc590` concluso con stato live.
- Collaudo post-deploy sul verbale reale `VV/24990121765`: `PDF disponibili: 1`, nome del documento ASIA corretto, visualizzatore interno aperto con successo e 0 errori console. Pagina 15 chiusa.

### 2026-08-06 — Pagina 14 Costi noleggio

- Route React verificata: `/noleggio/costi` apre il tab `Riepilogo Costi` di `VeicoliHub` e legge `GET /api/noleggio/veicoli?anno=...`.
- Difetto reale nel frontend: la colonna/totale `Altro` sommava pedaggi e costi extra ma ometteva `totale_riparazioni`, pur incluse nel totale generale.
- Difetto architetturale nel backend: `GET /api/noleggio/export-pdf-costi` ricalcolava fatture, veicoli e verbali con una seconda logica distinta da quella della pagina, esponendo il PDF a divergenze e doppi conteggi.
- Correzione locale: un'unica funzione frontend somma pedaggi, costi extra e riparazioni; il PDF riusa `get_veicoli`, lo stesso aggregatore della pagina e del dettaglio veicolo.
- Collaudo read-only sul database reale 2026: 4 veicoli, 0 fatture non associate, riparazioni `€ 500,00`; somma delle sei categorie `€ 12.605,21`, identica al totale generale.
- PDF generato con gli stessi dati reali: MIME `application/pdf`, firma `%PDF` valida e nome `riepilogo_costi_noleggio_2026.pdf`.
- Test locali: 1102 backend superati, 2 saltati; 81 frontend superati; build di produzione completato e artefatti generati ripuliti.
- Correzione pubblicata su `main` con merge `64e4361302695fa90738a313d34d9570b218d22a`; deploy Render `dep-d9pvj6142hec73c05400` concluso con stato `live` e health check sul commit `64e43613`.
- Verifica tecnica post-deploy: route pubblica HTTP 200, API protetta HTTP 401 senza sessione e chunk `VeicoliHub` pubblicato con `totale_riparazioni` ed export PDF. Pagina ancora `IN CORREZIONE` fino al collaudo visuale autenticato.

### 2026-08-06 — Pagina 17 Bilancio

- Route React verificata: `/contabilita/bilancio` carica Stato Patrimoniale e Conto Economico dagli endpoint canonici `/api/bilancio/stato-patrimoniale` e `/api/bilancio/conto-economico`.
- Difetto reale riprodotto: export PDF e confronto annuale usavano due aggregazioni storiche distinte dalla pagina. Sui dati reali 2026 la pagina calcolava totale attivo `€ 334.954,45`, crediti `€ 0,00` e debiti `€ 605.885,88`; il vecchio percorso PDF calcolava invece totale attivo `€ 934.620,31`, crediti `€ 652.033,45` e debiti `€ 31.358,96`, omettendo immobilizzazioni e Fondo TFR.
- Difetto fiscale rimosso: il confronto applicava automaticamente una stima IRES/IRAP del 28% e la presentava come `utile netto`, senza una liquidazione fiscale confermata.
- Correzione locale: pagina, PDF annuale/mensile e confronto usano gli stessi due calcolatori canonici; confronto e PDF includono immobilizzazioni e Fondo TFR e mostrano il risultato gestionale prima delle imposte senza inventare un utile netto.
- Sicurezza UI: errore di caricamento esplicito con pulsante `Riprova`; l'eliminazione di una voce manuale richiede conferma perché modifica i totali dell'anno.
- Collaudo read-only sul database reale 2026 dopo la correzione: output pagina/export identici; totale attivo e totale passivo entrambi `€ 334.954,45`; immobilizzazioni `€ 52.367,59`; Fondo TFR `€ 95.931,60`; ricavi `€ 17.787,15`; costi `€ 111.960,60`; risultato `-€ 94.173,45`.
- PDF annuale e PDF comparativo generati in memoria con firma `%PDF` valida; nessun dato scritto. Test mirati: 15 backend e 3 frontend superati.
- Suite completa: 1106 test backend superati, 2 saltati; 84 test frontend superati; build di produzione completato e artefatti generati ripuliti dal working tree.
- Correzione pubblicata su `main` con PR `#115` e merge `25b8ba84e21841135ab7e3f65a2f8490de2d9e2b`.
- Difetto infrastrutturale emerso al collaudo: il servizio Render installava solo le dipendenze Python e continuava a servire il vecchio `frontend/dist`, quindi una correzione React poteva risultare mergiata ma non pubblicata. Il comando di build e stato riallineato per installare anche le dipendenze frontend, incluse quelle di sviluppo, ed eseguire `vite build` a ogni deploy.
- Deploy Render `dep-d9q03adbedkc73ar10bg` concluso con stato `live`. Verifica diretta su `impresasemplice.online` e sul sottodominio Render: health `healthy`, database `connected`, commit `25b8ba84`, nuovo entry bundle `index-DY8uKrWk.js` e chunk Bilancio `Bilancio-BukqaKPG.js` contenente gestione errore, conferma eliminazione ed export PDF; API protetta HTTP 401 senza sessione.
- Pagina ancora `IN CORREZIONE` solo fino al collaudo visuale autenticato con dati reali; codice, dati read-only, test, build e deploy tecnico sono completati.

### 2026-08-06 — Pagina 18 Verifica Bilancio

- Route React verificata: `/contabilita/verifica` carica `/api/contabilita-gestionale/bilancio-verifica` con anno globale e dettaglio opzionale; il router e registrato sotto `/api/contabilita-gestionale`.
- Difetto contabile corretto: la vecchia verifica controllava solo `Totale Dare = Totale Avere` sull'intero anno. Due scritture individualmente sbilanciate ma opposte potevano compensarsi e produrre falsamente `Quadratura OK`. Ora ogni scrittura e verificata separatamente e sono contate anche righe non numeriche, righe senza conto e scritture senza righe.
- Completezza separata dalla quadratura: fatture e corrispettivi non vengono risommati nel bilancio; sono usati soltanto per misurare il backlog non ancora registrato. Il testo UI ora dichiara come fonte unica il registro definitivo `movimenti_contabili`.
- Patrimonio netto aggiunto a classificazione, filtro e riepilogo. Rimossi stato frontend inutilizzato e circa 316 righe del vecchio aggregatore duplicato e irraggiungibile.
- Export CSV protetto dall'esecuzione di formule provenienti dai nomi conto e corretta la gestione errori per non mostrare dati dell'anno precedente dopo un caricamento fallito.
- Collaudo read-only sul database reale 2026: 1 scrittura definitiva, `Dare € 84,00`, `Avere € 84,00`, nessuna anomalia strutturale; registro non completo per 443 documenti ancora da registrare, di cui 272 fatture e 171 corrispettivi. Nessun dato scritto.
- Test mirati: 7 backend e 6 frontend superati. Suite completa: 1111 backend superati, 2 saltati e 87 frontend superati. Build di produzione completato fuori dal repository con chunk `BilancioVerifica-BdHljtvz.js`; `frontend/dist` e rimasta pulita. Pagina ancora `IN CORREZIONE` fino a PR, deploy e collaudo live tecnico/visuale.
- Correzione pubblicata con PR `#117`, merge `e8f099b6ea7556bc26d2f78df41176e4964df21c` e deploy Render `dep-d9q0ig4s728c73bf9gtg` concluso `live`.
- Verifica tecnica diretta: health `healthy`, database `connected`, route HTTP 200, endpoint protetto HTTP 401 senza sessione e chunk `BilancioVerifica-BIobsbCU.js` contenente validazione registro, avviso compensazioni, patrimonio netto e fonte unica. Resta solo il collaudo visuale autenticato.

### 2026-08-06 — Pagina 19 Libro Giornale

- Route React verificata: `/contabilita/giornale` monta `LibroGiornale` nel tab Contabilita e chiama Giornale, Mastro e controllo dei documenti non registrati oltre 60 giorni.
- Periodo unificato: Giornale, Mastro ed export leggono la stessa fonte `movimenti_contabili` e includono sia `data_documento` sia il campo storico `data`, senza perdere il filtro fattura.
- Integrita aggiunta per singola scrittura: sbilanci, righe non numeriche, righe senza conto, protocolli mancanti o duplicati. La somma annuale non puo piu nascondere due scritture sbilanciate opposte.
- Troncamento esplicito: l'endpoint restituisce totale disponibile, limite e stato `troncato`; la UI non presenta una vista parziale come quadratura completa.
- Mastro ricostruito con lo stesso parser controllato del Giornale, evitando che un importo non numerico faccia fallire l'intera aggregazione Mongo.
- Reimport Admin validato integralmente prima di qualsiasi scrittura: tipo/versione, massimo 100000 scritture, righe, conti, importi, quadratura e unicita protocolli. Un file corrotto produce HTTP 422 e zero inserimenti; la UI richiede conferma esplicita e limita il file a 25 MB.
- Il controllo accessorio dei 60 giorni non blocca piu Giornale e Mastro se fallisce; gli errori principali azzerano i dati precedenti e mostrano `Riprova`.
- Collaudo read-only reale 2026: 1 scrittura, 2 mastrini, Dare e Avere entrambi `€ 84,00`; Giornale, Mastro ed export hanno conteggi/totali identici e registro valido. Nessun dato scritto e nessun reimport eseguito sul database aziendale.
- Test mirati: 9 backend e 7 frontend superati. Suite completa: 1117 backend superati, 2 saltati e 91 frontend superati. Audit del grafo frontend: 162 file analizzati e nessun orfano eliminabile. Build di produzione completata fuori dal repository con chunk `LibroGiornale-DEfAeXrH.js`; `frontend/dist` e rimasta pulita. Pagina ancora `IN CORREZIONE` fino a PR, deploy e collaudo live.
- Correzione pubblicata con PR `#118`, merge `5115404ac4d7c9852cb99d1725f3ea1ae3029ebb` e deploy Render `dep-d9q0s5gae00c73a1q940` concluso `live`.
- Verifica tecnica diretta su entrambi i domini: health `healthy`, database `connected`, route HTTP 200, endpoint protetto HTTP 401 senza sessione e chunk `LibroGiornale-B7UwiwBl.js` con avvisi di integrita, troncamento e riprova. Resta solo il collaudo visuale autenticato.

### 2026-08-06 — Pagina 20 Controllo mensile

- Route React verificata: `/contabilita/controllo` monta `ControlloMensile` nel tab Contabilita.
- Difetto riprodotto nel codice: la pagina ricostruiva nel browser la logica POS cercando solo `PDV 3757283`, leggeva al massimo 500 corrispettivi e non mostrava banca/differenza nel dettaglio giornaliero, pur esistendo il motore backend canonico a due fasi.
- La pagina usa ora `/api/pos-corrispettivi/controllo-due-fasi`: XML RT, chiusura POS reale e accredito banca restano evidenze distinte; il giorno vendita viene letto dalla causale e i circuiti dello stesso giorno sono sommati dal backend.
- Rimosse la regola PDV duplicata, il calendario festivi approssimato nel frontend e la derivazione POS dalla categoria Cassa. I limiti di Cassa/Corrispettivi sono portati al massimo supportato e ogni fonte fallita resta visibile come errore, non come periodo a zero.
- Aggiunte `Diff. RT` e `Diff. Banca` sia nel riepilogo mensile sia nel dettaglio giornaliero. Le anomalie seguono gli stati del motore canonico: un XML maggiore del POS reale non viene marcato erroneamente come difetto.
- Collegata la completezza del registro definitivo: la pagina espone separatamente fatture e corrispettivi ancora da registrare, senza considerarli gia contabilizzati.
- Collaudo read-only reale 2026: 171 corrispettivi, 421 movimenti Cassa, 3505 movimenti di estratto conto e 272 fatture. Motore canonico: 172 giorni, 141 controlli RT/POS corretti, 30 differenze da verificare; banca 128 corretti, 15 mancanti, 2 differenze e 23 extra. Totale POS reale `EUR 328.726,07`, accrediti rilevati `EUR 306.147,49`. Nessun dato scritto.
- Test mirati: 18 backend POS/XML/banca e 4 frontend superati. Suite completa: 1117 backend superati, 2 saltati e 95 frontend superati. Audit del grafo frontend: 163 file analizzati e nessun orfano eliminabile. Build di produzione completata fuori dal repository con chunk `ControlloMensile-DqhiJOYy.js`; `frontend/dist` e rimasta pulita. Pagina ancora `IN CORREZIONE` fino a PR, deploy e collaudo live.
- Correzione pubblicata con PR `#119`, merge `0920f2c4bc236626eb210d28ef7a9b5d8a55b4dd` e deploy Render `dep-d9q16frncjis73fa7f00` concluso `live`.
- Verifica tecnica diretta su entrambi i domini: health `healthy`, database `connected`, route HTTP 200, endpoint protetto HTTP 401 senza sessione e chunk `ControlloMensile-DzfEppp5.js` con motore canonico, differenza banca e backlog del registro; la vecchia regola `PDV 3757283` non e presente. Resta solo il collaudo visuale autenticato.

### 2026-08-06 — Pagina 21 Calendario fiscale

- Route React verificata: `/contabilita/calendario` monta `CalendarioFiscale` nel tab Contabilita e usa gli endpoint sotto `/api/fiscalita`.
- Difetto strutturale riprodotto: il `GET /api/fiscalita/calendario/{anno}` eseguiva un upsert per ogni scadenza a ogni apertura della pagina. La lettura e ora pura: compone i template fiscali con i soli stati persistiti e dichiara `scritture_eseguite: 0`.
- Duplicati legacy neutralizzati in lettura scegliendo un solo stato per id e privilegiando quietanza F24, evidenza documentale e stato completato. I promemoria personalizzati restano visibili senza gonfiare le scadenze generate.
- Provenienza esplicita: `quietanza_f24`, `conferma_manuale`, `manuale_legacy_non_tracciata` o nessuna evidenza. La UI non presenta piu un semplice flag come prova documentale.
- Conferma manuale resa esplicita, idempotente e registrata nell'audit; aggiunta riapertura tracciata. Una scadenza protetta da quietanza F24 non puo essere riaperta manualmente.
- Il calendario resta disponibile se fallisce soltanto il servizio notifiche. Il KPI `Prossime 7 gg` usa ora una finestra reale di sette giorni, non le prime cinque scadenze future.
- Le date che cadono nel fine settimana sono spostate al primo giorno lavorativo; ogni riga espone lo scadenzario ufficiale e segnala gli adempimenti condizionali da verificare. La pagina collega la Gestione IVA unica invece di ricostruire attribuzione, confronto F24 e scadenze IVA.
- Collaudo read-only reale 2026 prima della correzione: 74 record e 74 id unici, 73 aperti e 1 completato manualmente senza provenienza storica; 48 F24 e 130 quietanze complessive, delle quali 2 associate, 39 non corrispondenti e 89 senza F24. Nessun dato scritto.
- Test mirati: 14 backend e 3 frontend superati. Suite completa: 1121 backend superati, 2 saltati e 98 frontend superati. Le mappe sono state riallineate ai 1048 endpoint reali. Audit del grafo frontend: 164 file analizzati e nessun orfano eliminabile. Build di produzione completata fuori dal repository con chunk `CalendarioFiscale-CyJhaslA.js`; il build tracciato del repository e rimasto invariato. Pagina ancora `IN CORREZIONE` fino a PR, deploy e collaudo live.
- Correzione pubblicata con PR `#120`, merge `dadd36fa6dc0c223b225a18143b60865890e3e8b` e deploy Render `dep-d9q1kvcs728c73bfvo10` concluso `live` il 2026-08-06.
- Verifica tecnica diretta su entrambi i domini: health `healthy`, database `connected`, route HTTP 200, endpoint di lettura e riapertura protetti HTTP 401 senza sessione e chunk `CalendarioFiscale-DW_SEI6s.js` con lettura sicura, prova documentale, protezione F24 e finestra reale di 7 giorni. Resta solo il collaudo visuale autenticato.

### 2026-08-06 — Pagina 22 Cespiti

- Route React verificata: `/contabilita/cespiti` monta `GestioneCespiti`; il router `/api/cespiti` e registrato nel backend e collega registro, fatture XML, bilancio e chiusura esercizio.
- Difetto transazionale riprodotto: `POST /registra/{anno}` aggiornava prima i cespiti e creava la scrittura, poi costruiva la risposta con la variabile inesistente `movimento`. L'utente riceveva errore dopo le scritture e poteva riprovare. Ora la risposta usa l'id reale, la scrittura riepilogativa precede le quote con dettaglio per cespite e il retry e idempotente/recuperabile.
- Registrazione annuale protetta: anteprima obbligatoria, conferma esplicita e blocco fino al 31 dicembre dell'esercizio. Una scrittura gia presente non assorbe nuovi cespiti in silenzio: richiede una rettifica controllata.
- Separata la data fattura dalla data di entrata in funzione. Le proposte estratte automaticamente restano `da confermare` e non producono quote finche non esiste questa prova. Fonte: art. 102 TUIR, che fa decorrere la deduzione dall'esercizio di entrata in funzione.
- Coefficienti riallineati al [DM 31 dicembre 1988, Gruppo XIX](https://www.gazzettaufficiale.it/atto/serie_generale/caricaArticolo?art.codiceRedazionale=088A0017&art.dataPubblicazioneGazzetta=1989-02-02&art.flagTipoArticolo=19&art.idArticolo=1&art.idGruppo=0&art.idSottoArticolo=1&art.idSottoArticolo1=10&art.progressivo=0&art.versione=1): mobili 10%, attrezzature 25%, impianti generici 8%, impianti specifici 12%, macchine ufficio 20%. Il calcolo non supera mai il massimale anche se un record storico contiene una percentuale maggiore. Software e diritti sono distinti ai sensi dell'art. 103 TUIR e non vengono piu classificati automaticamente dalla sola parola in fattura.
- Deduplica corretta: una chiave univoca e non leggibile lega fattura, riga, descrizione/importo e occorrenza. Due acquisti distinti dello stesso bene allo stesso prezzo non vengono piu confusi; anteprima e conferma precedono sempre il backfill.
- Le proposte mantengono id e numero fattura e non inventano piu una data di acquisto se il documento e incompleto: la fattura resta da correggere e il cespite non viene creato.
- Cancellazione fisica sostituita da archiviazione tracciata. Modifiche a valore/data sono bloccate dopo quote registrate; la conferma dell'entrata in funzione resta possibile se coerente con lo storico.
- Dismissioni corrette e idempotenti: plusvalenza in AVERE e minusvalenza in DARE. Non vengono piu inventate righe Cassa/Banca con la plus/minusvalenza; l'eventuale incasso deve provenire dall'estratto conto e dalla riconciliazione del documento di vendita. Un retry identico recupera la stessa registrazione senza duplicarla.
- Frontend: controllo coerenza in sola lettura, importi con centesimi, errori visibili, avviso su prove/coefficienti, anteprima prima delle azioni e schede responsive su schermi stretti.
- Collaudo read-only reale 2026: 16 cespiti attivi collegati a 8 fatture; nessun duplicato fattura-riga o descrizione/importo. Una sola quota/movimento per `EUR 84,00`, registrata il 5 agosto 2026; 1 bene su 16 coperto, 16 senza data di entrata in funzione, 5 con coefficiente storico oltre il massimo e 1 quota gia registrata oltre il coefficiente massimo. Stato `critico`; conteggi `cespiti`, `movimenti_contabili` e `audit_log` identici prima/dopo il controllo. Nessun dato scritto o rettificato.
- Test mirati: 36 backend e 3 frontend superati. Suite completa finale: 1135 backend superati, 2 saltati e 101 frontend superati. Il test frontend e stato anche ripetuto isolatamente dopo un timeout da contesa durante l'esecuzione parallela. Mappe riallineate ai 1049 endpoint reali; audit del grafo frontend: 165 file analizzati e nessun orfano eliminabile.
- Build di produzione completata fuori dal repository con chunk `GestioneCespiti-lkxz6Jhs.js`, verificato per conferma esplicita, anteprima, entrata in funzione e archiviazione; la directory temporanea e stata rimossa e `frontend/dist` non e stato modificato. Il controllo asincrono annulla le richieste obsolete al cambio di tab/anno. Pagina ancora `IN CORREZIONE` fino a PR, deploy e collaudo live.

### 2026-08-06 — Pagina 24 Chiusura esercizio

- Route React verificata: `/contabilita/chiusura` monta `ChiusuraEsercizio`; gli endpoint di stato, verifica preliminare e bilancino sono registrati sotto `/api/chiusura-esercizio`.
- Difetto contabile rimosso: il vecchio bilancino stimava il risultato direttamente da fatture e corrispettivi anche con registro definitivo vuoto o incompleto. Prima della correzione mostrava utili non dimostrati di `EUR 467.421,59` per il 2025 e `EUR 363.802,59` per il 2026.
- Fonte unica: il risultato può essere calcolato soltanto dalle scritture valide, complete e quadrate di `movimenti_contabili`. Un dato mancante non viene trasformato in zero e la chiusura resta bloccata.
- Scrittura corretta e idempotente: ogni conto economico viene chiuso con righe Dare/Avere e il risultato confluisce nel conto `03.03.01`; la frase esatta `CHIUDI <anno>` è obbligatoria. L'apertura richiede `APRI <anno>`, impedisce duplicati e salva uno snapshot di audit senza creare riporti duplicati in Prima Nota.
- Test mirati: 21 backend e 2 frontend superati. Suite completa: 1.166 backend superati, 2 saltati e 106 frontend superati in 23 file. Build di produzione completata con 3.077 moduli; artefatti generati ripuliti senza toccare i file dell'utente.
- Correzione pubblicata con PR `#125`, merge `20fa8279226ce6b5bd99799758f037beebede21a` e deploy Render `dep-d9q4ccp42hec73c3fdu0` concluso `live`. Health: `healthy`, database `connected`, commit `20fa8279`.
- Collaudo live autenticato esclusivamente con GET e ruolo `sola_lettura`: 2025 aperto e non chiudibile per registro vuoto, 1.176 fatture e 347 corrispettivi non contabilizzati, 16 cespiti senza ammortamento e 2.359 movimenti bancari non riconciliati; 2026 aperto e non chiudibile perché in corso, con 272 fatture, 171 corrispettivi e 1.668 movimenti bancari non riconciliati. In entrambi gli anni il bilancino è `disponibile: false` e `bilancino: null`; nessun dato è stato scritto.
- Frontend pubblicato verificato nel chunk `ChiusuraEsercizio-CgUQWVlm.js`: presenti lo stato `Bilancino non disponibile`, le conferme `CHIUDI`/`APRI`, `conferma_testo` e `anno_nuovo`. Pagina marcata `VERIFICATA`.

### 2026-08-06 — Pagina 9 Prima Nota, avvio revisione completa

- La pagina apre correttamente Cassa, Banca, Provvisori e Soci, ma resta `IN REVISIONE`: l'apertura E2E non certifica ancora spostamenti, conteggi e quadrature di tutte le sezioni.
- Verifica read-only reale sui finanziamenti soci 2026: 6 righe sorgente corrispondono a 3 operazioni; la deduplica conservativa restituisce 3 movimenti, `EUR 44.000,00` di apporti e 3 copie accorpate senza cancellare le prove bancarie. Il precedente totale visualizzato di `EUR 88.000,00` era raddoppiato.
- Nessun record aziendale è stato modificato. La pagina potrà diventare `VERIFICATA` soltanto dopo i test reali separati di Cassa, Banca, Provvisori e dei relativi contatori.

### 2026-08-06 — Pagina 40 PayPal, avvio revisione completa

- Verifica read-only reale 2026: 27 transazioni, 17 pagamenti contabili effettivi, 0 statement, 44 movimenti bancari PayPal, 0 riconciliati; 6 movimenti hanno un candidato univoco con importo al centesimo, segno e data entro tre giorni. Non è stata eseguita alcuna riconciliazione sul database aziendale.
- Errore riprodotto: Dashboard e lista calcolavano `EUR 2.136,56` su 17 pagamenti, mentre Report spese calcolava `EUR 2.725,43` su 21 righe perché sommava anche le gambe tecniche T02 delle conversioni valuta.
- Il Report usa ora una sola riga contabile per pagamento e l'importo EUR della conversione collegata. Sul dataset reale in sola lettura Dashboard, lista e Report coincidono: 17 pagamenti e `EUR 2.136,56`.
- Restano da chiudere mapping fornitori, associazione fattura e riconciliazione banca; per questo la pagina resta `IN REVISIONE`.

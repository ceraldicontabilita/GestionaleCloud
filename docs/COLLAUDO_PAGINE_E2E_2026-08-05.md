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
| 9 | [ ] | Prima Nota — `/prima-nota` | Espone Cassa, Banca, Provvisori e finanziamenti soci senza duplicare le fonti. | TENERE |
| 10 | [ ] | Pulizia Prima Nota — `/prima-nota/pulizia` | Diagnostica e propone deduplica/quadratura controllata della Prima Nota. | TENERE COME STRUMENTO AMMINISTRATIVO |
| 11 | [ ] | Cedolini e salari — `/salari` | Gestisce cedolini, bonifici, saldo/acconto e riconciliazione paga. | TENERE |
| 12 | [ ] | Flotta noleggio — `/noleggio` | Veicoli, contratti, driver storico e costi ricavati dalle fatture. | TENERE |
| 13 | [ ] IN CORREZIONE | Verbali noleggio — `/noleggio/verbali` | Verbali da email/documenti, targa, driver alla data, fattura, PagoPA e pagamento. | TENERE |
| 14 | [ ] IN CORREZIONE | Costi noleggio — `/noleggio/costi` | Riepiloga canoni, verbali, bollo, pedaggi e altri costi per veicolo. | TENERE |
| 15 | [x] VERIFICATA | Dettaglio verbale — `/verbali-noleggio/:identificativo` | Mostra la singola catena Verbale -> veicolo -> driver -> fattura -> pagamento. | TENERE |
| 16 | [x] VERIFICATA | Piano dei Conti — `/contabilita` | Mostra un solo conto per codice e i saldi derivati dalle fonti contabili. | TENERE |
| 17 | [ ] | Bilancio — `/contabilita/bilancio` | Stato patrimoniale e conto economico per periodo. | TENERE |
| 18 | [ ] | Verifica Bilancio — `/contabilita/verifica` | Controlla quadrature e incoerenze del bilancio. | TENERE |
| 19 | [ ] | Libro Giornale — `/contabilita/giornale` | Elenca le scritture contabili cronologiche e i mastri. | TENERE |
| 20 | [ ] | Controllo mensile — `/contabilita/controllo` | Incrocia mensilmente fatture, corrispettivi, banca e Prima Nota. | TENERE |
| 21 | [ ] | Calendario fiscale — `/contabilita/calendario` | Scadenze fiscali operative e loro completamento. | TENERE |
| 22 | [ ] | Cespiti — `/contabilita/cespiti` | Beni strumentali, ammortamenti e verifiche collegate. | TENERE |
| 23 | [ ] | Finanziaria — `/contabilita/finanziaria` | Riepilogo finanziario e disponibilita per anno. | TENERE |
| 24 | [ ] | Chiusura esercizio — `/contabilita/chiusura` | Verifiche preliminari e procedura controllata di chiusura. | TENERE CON CONFERMA FORTE |
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
| 40 | [ ] | PayPal — `/riconciliazione/paypal` | Transazioni, movimenti banca, documenti e mapping fornitori PayPal. | TENERE |
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
- Pagina ancora `IN CORREZIONE` fino a merge, deploy e collaudo visuale post-deploy con dati reali.

# Piano operativo Gestionale Ceraldi

Questo documento riassume lo stato del gestionale e il piano di completamento tecnico, separando cio che esiste, cio che e gia automatico, cio che e parziale e cio che va costruito davvero.

## 1. Cosa fa gia il gestionale

Il gestionale copre gia molte aree ERP:

- Dashboard aziendale, ricavi, costi, utile stimato, IVA, scadenze e alert.
- Fatture passive SDI da PEC Aruba, parsing XML/P7M, fornitori, righe, note di credito e stato pagamento.
- Prima nota cassa e banca, movimenti provvisori, sospesi, POS, stipendi, F24 e operazioni da confermare.
- Corrispettivi XML, quota contanti/elettronico, alimentazione cassa e controlli POS.
- Fornitori, anagrafiche, P.IVA, IBAN, statistiche, assegni e lookup esterni.
- Banca, estratti conto, bonifici, assegni, POS, PayPal, F24 banca e riconciliazioni.
- F24, quietanze, codici tributo, calendario fiscale, IVA e fiscalita italiana.
- HR, dipendenti, contratti, cedolini, presenze, TFR, giustificativi e bonifici stipendi.
- Noleggio, veicoli, verbali, OCR, targhe, driver, costi e riconciliazione verbali.
- Magazzino, inventario, dizionari articoli/prodotti, ordini e basi food cost.
- Contabilita avanzata, piano conti, bilancio, centri costo, chiusura esercizio, mutui e indici.
- Documenti, inbox, parser, AI documentale, batch processing e documenti non associati.
- Email, PEC, Gmail, allegati, mittenti attendibili, classificazione e automazioni F24.

## 2. Cosa fa gia in automatico

Automazioni presenti o gia predisposte nel flusso reale:

- Scarico PEC fatture SDI.
- Parsing automatico XML fatture.
- Creazione e aggiornamento fornitori.
- Destinazione fattura in base al metodo pagamento.
- Registrazioni in prima nota cassa o banca.
- Import Gmail e smistamento documenti.
- Parser cedolini, F24, verbali e documenti.
- Import estratti conto.
- Riconciliazioni automatiche base.
- Alert fiscali e notifiche F24.
- Coerenza POS-corrispettivi.
- Batch reprocessing e primi controlli anti-duplicato.

## 3. Cosa esiste ma e parziale

Aree da consolidare:

- Scheduler ancora troppo vicino al web process.
- Queue e worker presenti solo parzialmente nei job business.
- Osservabilita job debole.
- Idempotenza non uniforme su tutte le pipeline.
- Locking distribuito non completo.
- Health endpoint operativi da rafforzare.
- Retry policy non standardizzata.
- Prima nota automatica ancora da rendere pienamente affidabile.
- Scarico verbali da PEC non chiuso.
- Scheda fornitore e fascicolo dipendente da completare.
- TFR automatico da cedolino, IVA mensile automatica, WhatsApp e alcuni export ancora parziali.
- Alcuni parser e fallback AI ancora da industrializzare.

## 4. Cosa manca davvero

Priorita alta:

- Separazione reale web, worker e scheduler.
- Queue reale in uso.
- `job_runs`, `job_items`, `processing_locks` e dead letter queue.
- Retry con backoff, stale recovery e monitoraggio job.
- Idempotenza forte su Gmail, PEC, allegati, XML, verbali, F24 e cedolini.
- Prima nota automatica con alta confidenza e passaggio da provvisorio a definitivo.
- Scarico verbali da PEC.
- Controllo IVA mensile automatico e chiusura fiscale guidata.

Priorita media:

- Fascicolo dipendente completo.
- Scheda fornitore completa.
- Magazzino piu automatico da fatture, ordini e previsioni.
- CI/CD con GitHub Actions, smoke test job e deploy ripetibile.

Priorita bassa ma utile:

- Dashboard automazioni, errori pipeline, job bloccati e dead letters.
- WhatsApp come canale automatico di alert business.
- AI e learning consolidati in casi d'uso reali.

## 5. Tenere, completare, costruire

Tenere:

- Dashboard, fatture passive, fornitori, prima nota, banca, riconciliazione, HR base, cedolini, verbali, magazzino base, F24 base, document inbox e import manuali.

Completare:

- Prima nota auto, PEC verbali, fascicolo dipendente, scheda fornitore, TFR automatico, IVA mensile automatica, export PDF/Excel, fallback AI, monitoraggio job e WhatsApp.

Costruire davvero:

- Architettura worker/scheduler/queue completa.
- Idempotenza forte.
- Stato persistente dei job.
- Dead letter, retry e lock distribuiti.
- Dashboard operativa automazioni.
- Uniformazione frontend con template comuni.

## 6. Linea di lavoro consigliata

Backend e automazioni:

1. Queue reale in uso.
2. Scheduler separato.
3. Worker separato.
4. Primo job pilota enqueueato.
5. `job_runs` e idempotenza email/allegati.
6. Lock distribuiti.
7. Monitoraggio.
8. CI/CD base.

Frontend e logica operativa:

1. Template unici pagina.
2. Uniformazione hub.
3. Stati loading/error/empty standard.
4. Verifica pagina per pagina contro la documentazione.
5. Migrazione moduli pilota: fatture, prima nota, contabilita e strumenti.

## 7. Sintesi

Il gestionale e gia un ERP ricco. La priorita non e aggiungere moduli scollegati, ma chiudere bene automazioni, completare i moduli parziali, uniformare il frontend e rendere robusti esecuzione, controllo e recovery.

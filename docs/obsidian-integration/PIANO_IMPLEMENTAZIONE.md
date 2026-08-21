# Piano di implementazione

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

## Fase 0 — Analisi e inventario

- sincronizzare il repository canonico;
- identificare collezioni, registri Drive/Sheets ed endpoint correnti;
- classificare i dati per sensibilità;
- censire identificatori stabili e relazioni già esistenti;
- definire il responsabile di ciascun dossier.

**Uscita:** mappa sorgenti-entità-relazioni approvata, senza scritture reali.

## Fase 1 — Vault Procedure

- creare struttura e convenzioni;
- importare manuali e runbook;
- creare collegamenti dalle pagine del Gestionale;
- aggiungere registro decisioni e changelog operativo.

**Perché prima:** basso rischio e utilità immediata.

## Fase 2 — Proiezione documentale

- esportare metadati da `documents_inbox` e archivio Drive;
- collegare soggetto, pratica, hash e provenienza;
- generare dashboard errori, OCR debole e documenti da verificare;
- mantenere i PDF nel sistema canonico.

## Fase 3 — Contabilità e fiscalità

- fatture e soggetti;
- pagamenti documentali;
- movimenti bancari distinti;
- F24, quietanze e dichiarazioni;
- IVA e codici tributo come conoscenza consultiva.

## Fase 4 — Personale, veicoli e immobili

- fascicoli e timeline;
- assegnazioni temporali driver-veicolo;
- verbali e scadenze;
- contratti, manutenzioni e autorizzazioni.

## Fase 5 — Automazione server

- CLI e Headless Sync;
- esportazione incrementale;
- riconciliazione giornaliera;
- heartbeat, retry e alert;
- rigenerazione totale e backup.

## Fase 6 — Ricerca per agenti

- accesso in sola lettura ai vault autorizzati;
- ricerca e riassunto con citazione delle note;
- bozze di attività verso il Gestionale;
- nessuna mutazione operativa automatica.

## Test minimi

### Identità e deduplicazione

- stesso ID aggiorna la stessa nota;
- stesso hash non crea un nuovo documento;
- omonimi restano entità distinte;
- codici lunghi non diventano numeri scientifici;
- una rinomina non spezza i collegamenti basati su ID.

### Integrità

- rigenerazione completa produce lo stesso risultato;
- un errore su una nota non blocca il run;
- write atomico non lascia file parziali;
- annotazioni personali sopravvivono;
- link irrisolti e note orfane sono segnalati.

### Semantica

- quietanza documentale e movimento bancario restano distinti;
- importo uguale non conferma un’associazione;
- documenti PEC non cambiano automaticamente stati operativi;
- associazioni ambigue restano da verificare.

### Sicurezza

- nessun segreto esportato;
- vault pubblico privo di dati riservati;
- URL protetti non aggirano autenticazione;
- plugin non autorizzati assenti;
- accessi degli agenti limitati al vault assegnato.

### Operatività

- run incrementale, giornaliero e manuale;
- heartbeat mancante genera un solo alert;
- recovery genera una notifica distinta;
- backup e ripristino verificati;
- metriche e log consultabili.

## Criteri di accettazione

- ricerca trasversale funzionante per almeno cinque identificatori reali anonimizzati;
- dossier completo navigabile per un fornitore, un dipendente, un veicolo, un F24 e una pratica;
- nessuna scrittura nelle sorgenti durante l’esportazione;
- zero segreti nel vault e nel log;
- 100% dei collegamenti obbligatori presenti o marcati esplicitamente mancanti;
- rigenerazione ripetibile senza duplicati;
- documentazione di installazione, manutenzione, rollback e disaster recovery.

## Rollback

1. disabilitare scheduler ed eventi di esportazione;
2. conservare log e registry;
3. scollegare il vault dal server;
4. ripristinare il vault da backup oppure rigenerarlo;
5. verificare che Gestionale e Drive/Sheets non abbiano subito mutazioni.

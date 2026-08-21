# Prompt operativo per implementare l’integrazione

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

```text
Implementa nel repository canonico ceraldicontabilita/GestionaleCloud
l’integrazione con Obsidian descritta in docs/obsidian-integration/.

Prima sincronizza e verifica repository, branch main, test, database,
registri Drive/Sheets e permessi correnti. Il codice e i dati attuali sono
l’autorità; la documentazione è la specifica dell’obiettivo.

Procedi per fasi e completa prima una proiezione in sola lettura:

1. crea il KnowledgeProjectionRegistry;
2. implementa ObsidianKnowledgeExporter;
3. genera note Markdown con proprietà YAML e identificatori canonici;
4. preserva esclusivamente il blocco ANNOTAZIONI_PERSONALI;
5. crea collegamenti fra soggetti, documenti, pratiche ed eventi;
6. aggiungi URL bidirezionali Gestionale/Obsidian;
7. implementa dry-run, esportazione incrementale e rigenerazione completa;
8. aggiungi log, metriche, retry, heartbeat e alert;
9. prepara CLI/Headless Sync senza inserire segreti nel vault;
10. implementa test di identità, semantica, sicurezza e idempotenza.

Il GestionaleCloud e i registri Drive/Sheets restano fonte operativa.
Obsidian non può confermare pagamenti, riconciliazioni, IVA, driver o
altre associazioni ambigue. Non associare mai sulla base del solo importo.

Mantieni distinti documento originale, dato estratto, quietanza,
ricevuta PayPal, disposizione di bonifico e movimento bancario.

Non copiare nel vault password, token, cookie, credenziali, estratti conto
completi, PEC complete o documenti del personale salvo autorizzazione e
classificazione esplicita. Preferisci metadati e URL autenticati.

Implementa inizialmente il vault GestionaleCloud-Procedure, poi la
proiezione documentale privata. Usa fixture anonimizzate per i test.

Prima del deploy mostra:

- sorgenti lette e campi esportati;
- file modificati;
- esempio di vault generato;
- risultati del dry-run;
- test eseguiti;
- dati esclusi per sicurezza;
- piano di rollback.

Se i test passano e non ci sono rischi di perdita dati, pubblica le sole
modifiche pertinenti sul main canonico e verifica HEAD == origin/main.
Non eseguire pagamenti, non eliminare documenti e non confermare
associazioni ambigue.
```

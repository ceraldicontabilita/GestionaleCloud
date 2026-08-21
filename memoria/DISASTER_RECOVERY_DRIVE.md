# Disaster recovery — archivio Drive/Sheets

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

Procedura di ripristino dell'archivio operativo di GestionaleCloud. Google
Drive conserva gli originali; Google Sheets/Excel collegato a Drive conserva
registri, progressivi, identità, relazioni e provenienza.

## Obiettivi

- ricostruire il registro senza dipendere da Drive/Sheets;
- non modificare o perdere documenti originali;
- provare completezza, integrità e leggibilità;
- mantenere identificativi e relazioni stabili;
- rendere ogni operazione di recupero verificabile e ripetibile.

## Componenti da proteggere

1. radice Drive e cartelle canoniche;
2. workbook `Ceraldi ERP - Registro dati`;
3. configurazione degli ID cartella/workbook su Render;
4. credenziale del service account e permessi sulle cartelle;
5. codice, schema e migrazioni nel repository;
6. manifest di file, hash e provenienza.

Le credenziali non devono essere salvate nel repository o nel workbook.

## Verifiche periodiche

- il service account legge le cartelle e il workbook;
- ogni foglio richiesto esiste e ha le intestazioni versionate;
- progressivi e `canonical_id` sono univoci;
- i documenti referenziati esistono ancora su Drive;
- hash e dimensioni corrispondono al manifest;
- i payload completi sono decodificabili, inclusi quelli compressi;
- le relazioni non puntano a record mancanti;
- un import ripetuto non crea duplicati.

## Ricostruzione controllata

1. Bloccare temporaneamente le scritture applicative.
2. Fotografare configurazione, Drive ID, Sheet ID e versione schema senza
   esportare segreti nei log.
3. Copiare workbook e manifest in una posizione di recupero protetta.
4. Enumerare gli originali senza spostarli.
5. Validare hash, provenienza e permessi.
6. Ricreare un workbook vuoto con lo schema versionato.
7. Reimportare i registri mantenendo progressivi e ID canonici.
8. Ricostruire le relazioni soltanto dopo la presenza di entrambe le entità.
9. Eseguire conteggi e confronti per foglio, anno, importo e stato.
10. Avviare l'app in ambiente di prova con `SHEETS_REGISTRY_NAME=GestionaleCloud`.
11. Verificare i flussi end-to-end e solo dopo riaprire le scritture.

## Criteri di accettazione

- nessun originale mancante o illeggibile;
- zero collisioni non spiegate di progressivo/canonical ID;
- conteggi per foglio uguali alla fonte verificata;
- somme monetarie uguali al centesimo;
- link documento-fattura-pagamento-banca-Prima Nota navigabili;
- test di creazione, modifica, ricerca e deduplicazione riusciti;
- report firmato con data, versione schema e responsabile del controllo.

## Rollback

Se la verifica fallisce, lasciare invariati gli originali e ripristinare il
workbook precedente tramite la cronologia/versione copiata. Non eliminare
registri o backend transitori finché il nuovo archivio non supera tutti i
criteri.

## Fase transitoria Drive/Sheets

Drive/Sheets può restare disponibile solo come sorgente temporanea di confronto
durante la migrazione. Non è il piano di disaster recovery finale. La sua
dismissione è autorizzabile soltanto dopo una ricostruzione completa da
Drive/Sheets provata in ambiente isolato e dopo il cutover verificato in
produzione.

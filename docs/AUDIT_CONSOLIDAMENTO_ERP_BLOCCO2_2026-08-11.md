# Audit consolidamento ERP — Blocco 2 — 2026-08-11

Branch: `audit/consolidamento-erp-blocco2-2026-08-11`
PR: `#176`

## Obiettivi

- rimuovere gli import residui dalle pagine operative;
- lasciare `Documenti > Carica documenti` come unico ingresso utente;
- eliminare/automatizzare refresh e sincronizzazioni ordinarie;
- ridurre ulteriormente le superfici funzionali senza perdere capacità;
- mantenere compatibilità con vecchi URL tramite redirect o resolver;
- usare nomi italiani nelle funzioni esposte all'utente;
- rendere la rielaborazione documentale estendibile a tutte le categorie presenti in archivio.

## Modifiche applicate

### Admin / Elaborazioni

`AdminHub` espone ora tre aree: Sistema, Sicurezza MFA, Elaborazioni.

`Elaborazioni` contiene internamente:

- **Elaborazione automatica**: processo ordinario che mantiene aggiornato il gestionale;
- **Rielaborazione documenti**: manutenzione controllata degli originali gia acquisiti.

I vecchi percorsi `/admin/batch-reprocessing` e `/admin/batch-processor` vengono ricondotti a `/admin/elaborazioni`.

Decisione: **ACCORPARE**. Le funzioni restano distinte ma non sono due pagine amministrative principali.

### Rielaborazione documenti universale

Problema precedente: il vecchio `Batch Reprocessing` considerava quasi esclusivamente F24 e cedolini.

Correzione applicata:

- creato `app/services/ripielaborazione_documenti.py`;
- l'anteprima legge dinamicamente le categorie realmente presenti in `documents_inbox`;
- `/api/batch-reprocess/start` puo rielaborare tutte le categorie oppure una categoria scelta;
- il documento originale non viene sostituito e non viene creato un secondo evento economico;
- in **Simulazione** non viene scritto nulla;
- in **Esecuzione** il nuovo esito viene salvato nel campo `rielaborazione` dello stesso documento;
- fatture/note, F24, cedolini/LUL e verbali/PagoPA usano il parser specifico disponibile;
- le altre categorie vengono comunque incluse nel controllo e passano dal rilevamento automatico; se il parser corrente non e sufficiente restano tra i casi da verificare;
- gli endpoint tecnici F24-only e cedolini-only restano temporaneamente per compatibilita con la manutenzione specializzata.

La pagina frontend non mostra piu pulsanti fissi `F24` e `Cedolini`: presenta le categorie trovate nell'archivio e permette di scegliere **Tutte le categorie** oppure una categoria specifica.

Sono stati aggiunti test per:

- conteggio dinamico delle categorie;
- simulazione senza scrittura;
- conservazione dell'originale durante l'esecuzione;
- filtro per singola categoria.

Decisione: **GENERALIZZARE** e mantenere fallback `Da verificare` per i formati non ancora supportati con certezza.

### SumUp

Rimossi i pulsanti ordinari `Sincronizza ieri e oggi` e `Sincronizza ultimi 30 giorni`.

All'apertura del pannello vengono eseguite automaticamente verifica connessione e sincronizzazione ordinaria degli ultimi due giorni. Le operazioni correttive sull'XML restano manuali perche modificano dati.

Decisione: **AUTOMATIZZARE sync ordinaria / TENERE correzioni intenzionali**.

## Cedolini — evidenze da applicare

`CedoliniSalari.jsx` contiene ancora:

- `DocumentImportLink` per prospetto Excel;
- `DocumentImportLink` per cedolino PDF;
- `DocumentImportLink` per bonifico PDF;
- codice legacy `importaBonifici` verso `/api/prima-nota-salari/import-bonifici`;
- codice legacy `allegaDocumento` verso endpoint PDF specifici del cedolino.

Decisione: **ELIMINARE gli ingressi documentali dalla pagina**. Cedolini deve restare consultazione, apertura PDF, controllo importi, saldo e stato banca. L'acquisizione deve avvenire soltanto da Import Documenti.

## Prossimo blocco operativo

1. ripulire `CedoliniSalari.jsx` dagli ingressi di import e dal codice upload non piu necessario;
2. verificare `RiconciliazionePaypal`, `ArchivioBonifici`, `Corrispettivi`, `GestioneCespiti`, `LibroGiornale` per import/refresh manuali residui;
3. accorpare le sezioni Contabilita in gruppi Bilancio, Budget/Previsioni e Finanza;
4. aggiornare il censimento pagina-per-pagina dei controlli UI.

# Audit consolidamento ERP — Blocco 2 — 2026-08-11

Branch: `audit/consolidamento-erp-blocco2-2026-08-11`

## Obiettivi

- rimuovere gli import residui dalle pagine operative;
- lasciare `Documenti > Carica documenti` come unico ingresso utente;
- eliminare/automatizzare refresh e sincronizzazioni ordinarie;
- ridurre ulteriormente le superfici funzionali senza perdere capacità;
- mantenere compatibilità con vecchi URL tramite redirect o resolver.

## Modifiche applicate

### Admin / elaborazioni

Prima `AdminHub` esponeva quattro tab: Sistema, Sicurezza MFA, Batch Reprocessing, Batch Processor.

Ora espone tre tab: Sistema, Sicurezza MFA, Elaborazioni.

`Elaborazioni` contiene internamente:

- Elaborazione automatica (`BatchProcessor`);
- Riprocessamento tecnico (`BatchReprocessing`).

I vecchi percorsi `/admin/batch-reprocessing` e `/admin/batch-processor` vengono reindirizzati a `/admin/elaborazioni`.

Decisione: **ACCORPARE**. Le due funzioni restano distinte, ma non sono più presentate come due pagine amministrative principali.

## Cedolini — evidenze da applicare

`CedoliniSalari.jsx` contiene ancora:

- `DocumentImportLink` per prospetto Excel;
- `DocumentImportLink` per cedolino PDF;
- `DocumentImportLink` per bonifico PDF;
- codice legacy `importaBonifici` verso `/api/prima-nota-salari/import-bonifici`;
- codice legacy `allegaDocumento` verso endpoint PDF specifici del cedolino.

Decisione: **ELIMINARE gli ingressi documentali dalla pagina**. Cedolini deve restare consultazione, apertura PDF, controllo importi, saldo e stato banca. L'acquisizione deve avvenire soltanto da Import Documenti.

## Prossimo blocco operativo

1. ripulire `CedoliniSalari.jsx` dagli ingressi di import e dal codice upload non più necessario;
2. verificare `GestionePagoPA`, `RiconciliazionePaypal`, `ArchivioBonifici`, `Corrispettivi`, `GestioneCespiti`, `LibroGiornale` per import/refresh manuali residui;
3. accorpare le sezioni Contabilità in gruppi Bilancio, Budget/Previsioni e Finanza;
4. aggiornare il censimento pagina-per-pagina dei controlli UI.

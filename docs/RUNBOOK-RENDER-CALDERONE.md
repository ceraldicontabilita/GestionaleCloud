# Runbook: ciclo automatico Render del Calderone

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

## Risultato operativo

Render legge esclusivamente `00 - CALDERONE/01 - IN ARRIVO`, confronta gli
SHA-256 con l'indice canonico Drive/Sheets, usa l'anteprima obbligatoria del
Gestionale e, dopo l'esito completo del file o ZIP, sposta il contenitore nella
cartella corretta. Non elimina originali.

| Esito complessivo | Destinazione |
|---|---|
| tutti i membri importati o duplicati esatti | `99 - ELABORATE` |
| almeno un membro richiede revisione, senza errori | `90 - DA ELABORARE` |
| almeno un errore tecnico | `98 - ERRORI` |
| ZIP parziale o limite raggiunto | resta in `01 - IN ARRIVO` |

L'errore prevale sulla revisione. Il contenitore non viene mai suddiviso: uno
ZIP viene spostato una sola volta. Ogni spostamento aggiorna nella stessa
richiesta Drive lo stato, l'ora UTC di controllo e lo SHA-256 della sorgente.

## Task Render

- `calderone_documenti_preview(max_documents)`: sola lettura, nessun invio o
  spostamento.
- `calderone_lifecycle_preflight()`: controlla cartelle e permessi senza
  scrivere.
- `calderone_documenti_ingest(confirm, max_documents)`: importa e completa
  automaticamente il lifecycle del lotto autorizzato.
- `calderone_lifecycle_reconcile(confirm_move, max_sources)`: sposta il
  pregresso già presente nell'indice senza ritrasmettere documenti.

## Protezioni

L'import richiede `confirm=true`, `ENABLE_RENDER_CANONICAL_INGEST=true`, il
segreto condiviso e `ENABLE_RENDER_DRIVE_MOVES=true`. La riconciliazione richiede
`confirm_move=true`. Le cartelle devono essere tre destinazioni distinte e
figlie dello stesso Calderone dell'inbox. Se la verifica fallisce, il file resta
in `01 - IN ARRIVO` e viene contato come `SPOSTAMENTO_FALLITO`.

## Procedura di collaudo

1. Eseguire `calderone_lifecycle_preflight` e verificare che tutte le sorgenti
   siano modificabili.
2. Eseguire un'anteprima con limite `1`.
3. Eseguire l'ingestione con conferma e limite `1`.
4. Controllare `IMPORTATO` o `DUPLICATO_*` e `SPOSTATO_DONE=1`.
5. Verificare su Drive che il file non sia più nell'inbox e sia in Elaborate.
6. Ripetere la scansione: il file non deve essere riprocessato.

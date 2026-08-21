# Istruzioni Codex — GestionaleCloud

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

Queste istruzioni valgono per l'intero repository.

## Autorità e avvio

- Lavora esclusivamente sul repository canonico `ceraldicontabilita/GestionaleCloud`
  e sincronizza `origin/main` prima di intervenire.
- Leggi `PROMPT_MASTER.md`, `CLAUDE.md`, `PRODUCT.md`, `DESIGN.md` e
  `LOGICA_FUNZIONAMENTO.md` prima di modificare il prodotto.
- Per cedolini, salari e bonifici applica integralmente
  `docs/PROMPT_CEDOLINI_NETTO_DRIVE_SALARI.md`.
- Codice, test, configurazione corrente e dati sorgente verificabili prevalgono
  su report, ZIP o checkout storici.
- Preserva modifiche locali non pertinenti e non inserire segreti o dati
  personali nel repository.

## Regole inderogabili per cedolini e salari

- Google Drive è l'archivio canonico dei PDF; gli indici devono usare link
  Drive stabili e mai percorsi locali Windows.
- Il netto pagabile proviene soltanto dalla cella graficamente associata a
  `TOTALE NETTO`, `NETTO DEL MESE` o a un'etichetta equivalente verificata.
- Non usare come netto detrazioni, competenze, trattenute, imponibili, TFR,
  arrotondamenti, `ARR. PREC.`, `ARR. ATTUALE` o l'importo nel filename.
- Se il netto è vuoto, il valore resta nullo. Non inferire zero e non scegliere
  il numero più vicino.
- Soltanto lo stato `NETTO_VERIFICATO_DA_CEDOLINO` alimenta automaticamente
  `/salari` e i bonifici da assegnare.
- Una riga salariale indica un importo dovuto, non prova un pagamento. Pagato e
  riconciliato richiedono evidenza bancaria reale e relazione auditabile.
- Un duplicato certo richiede hash identico. Nome, dipendente, mese e importo
  uguali non autorizzano da soli eliminazione o cestinamento.
- Prima di trasmettere dati retributivi personali al gestionale live, mostra
  conteggi e impatto e richiedi conferma esplicita dell'utente.

## Implementazione e pubblicazione

- Riusa pagine, router, servizi, registri Drive/Sheets e viewer esistenti; non
  creare pipeline o archivi paralleli.
- Ogni scrittura deve essere idempotente, tracciabile e coperta da test sui casi
  positivo, nullo, ambiguo, multipagina ed errore parser.
- Prima del push controlla il diff e aggiorna l'inventario Markdown tramite
  `scripts/refresh_markdown_docs.py` quando aggiungi documentazione.
- Prima di dichiarare il lavoro live verifica test, build, CI, commit distribuito
  e comportamento reale dell'endpoint o della pagina interessata.

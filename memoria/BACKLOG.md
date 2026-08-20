# Ceraldi ERP — Backlog operativo

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Riscritto il 07/08/2026: solo lavoro davvero pendente. Ultimo aggiornamento
della versione precedente: aprile 2026 — era diventata archeologia.

## POS / SumUp

- **SumUp in produzione**: le variabili `SUMUP_API_KEY` e
  `SUMUP_MERCHANT_CODE` vanno messe sul servizio Render giusto
  (`GestionaleCloud`, non `GestionaleCloud-API` che è fermo) e la chiave
  passata in chat va RUOTATA. Poi "Verifica connessione" in Admin.
- **Payout SumUp**: la logica contabile è pronta e testata
  (`sumup_payout.py`); manca la chiamata HTTP che scarica i payout e lo
  scheduler che la esegue.
- **Scheduler SumUp**: sincronizzazione periodica transazioni + rielaborazione
  delle giornate aperte.
- **Coerenza POS**: pagina con le tre sezioni indipendenti
  (Cassa–XML / POS reali / Accrediti) — backend pronto
  (`stato_coerenza_pos.py`), frontend da costruire. Vista mensile ancora a
  colonna unica.
- **Stati Numia**: completare `Accreditato` / `Riconciliato` nel calendario
  accrediti.

## Estratti conto / Drive

- **Arretrato cartella unica**: 2023-2025 fermo sotto
  `DRIVE_ESTRATTI_ANNO_MINIMO` (scelta utente: prima il 2026). Da lavorare
  quando l'utente lo chiede, con dry-run prima.
- **Parser mancanti**: Worldline/Axepta (i vecchi "POS BNL":
  `EC-<pdv>-<mese> <anno>.pdf`, pdv 35536622/38949004), `Estratto
  transazioni <mese>.pdf`, `summary_merchant_*.pdf`. Oggi finiscono in
  `Errori` col motivo — corretto ma migliorabile.
- **Bonifica storico**: righe grezze già riversate in Prima Nota Banca
  (fotografia da `/api/prima-nota/banca/analisi-righe-grezze`) e doppioni
  causale (`/api/bank-statement/cleanup-duplicati-causale`): entrambe le
  bonifiche esistono in dry-run, vanno LANCIATE con conferma dell'utente.

## Prima Nota / Fatture

- **Fatture "sospese" in Provvisoria**: molte fatture di fornitori per cassa
  risultano `sospesa` (esclusa dai flussi automatici). Capire CHI le ha
  sospese (scelta utente vs effetto collaterale) prima di sbloccarle in
  massa. Ora c'è la conferma multipla per smaltirle a mano.
- **Piano dei conti / bilancio**: i saldi non seguono il filtro anno e non si
  popolano da ogni operazione (era il P0 del vecchio backlog, resta vero).

## Noleggio

- Fatture noleggio non associate ai veicoli (badge "6 fatture non
  associate"): il collegamento targa→fattura XML va reso automatico quando
  la targa è nel corpo fattura.

## Tecnico

- 2 test rossi locali dipendenti da flag `.env`
  (`test_drive_cedolini_ingest::test_is_configured`,
  `test_quietanze_import::test_drive_quietanze_helpers`): allineare i test
  o i default.
- Batch reprocessing: valutare un limite di concorrenza sulle chiamate AI.

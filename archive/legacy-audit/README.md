# Quarantena codice legacy

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Questa cartella e' riservata al codice dimostrato inattivo dopo l'audit.

Al momento non contiene moduli spostati: l'analisi ha trovato helper ancora
importati da parser, scheduler e test, quindi una migrazione massiva sarebbe
pericolosa. Ogni futuro `git mv` deve avere un manifest con:

- percorso originale e nuovo percorso;
- hash SHA-256 del file prima dello spostamento;
- riferimenti cercati e risultato del grafo import;
- test eseguiti e rollback previsto.

Non usare questa cartella per dati fiscali, PDF, chiavi o backup operativi.

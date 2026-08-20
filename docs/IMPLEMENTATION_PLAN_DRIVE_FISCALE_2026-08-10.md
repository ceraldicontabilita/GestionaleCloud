# Piano operativo Drive fiscale

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

1. Verificare la radice canonica e scoprire le due cartelle fiscali.
2. Persistire il registro senza esporre ID o credenziali.
3. Eseguire una scansione iniziale idempotente.
4. Conservare il token Drive Changes ed elaborare solo le variazioni.
5. Conservare documenti e prove anche se la fonte viene rimossa.
6. Aggiornare settimanalmente e versionare i codici tributo ufficiali.
7. Bloccare classificazioni fiscali fondate su codici non verificati.
8. Sorvegliare stato e ultime esecuzioni tramite endpoint amministrativi.

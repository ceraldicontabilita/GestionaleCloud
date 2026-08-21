# Runbook: vault Obsidian Procedure

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

## Stato operativo

È attiva la generazione automatica del vault **GestionaleCloud-Procedure** dai
soli file Markdown tracciati sotto `docs/`. Il pacchetto viene costruito dopo
ogni modifica pertinente, ogni giorno e su avvio manuale dal workflow GitHub
`Obsidian Procedure Vault`.

Questa prima fase non abilita Obsidian Sync e non proietta dati privati del
Gestionale. Il risultato è uno ZIP ricostruibile disponibile come artifact
della relativa esecuzione GitHub Actions.

## Contenuto ed esclusioni

Il vault contiene indice, documentazione pubblica, stato documentale e manifest
SHA-256. Non contiene PDF originali, cedolini completi, estratti conto, PEC,
password, token o credenziali.

## Uso

1. Aprire l'ultima esecuzione riuscita di `Obsidian Procedure Vault`.
2. Scaricare l'artifact `GestionaleCloud-Procedure-<commit>`.
3. Estrarre lo ZIP in una cartella nuova.
4. Aprire quella cartella come vault in Obsidian.
5. Controllare `00-INDICE.md` e `MANIFEST_SHA256.json`.

La sincronizzazione privata e le proiezioni operative restano disattivate finché
non vengono configurati destinazione, autorizzazioni minime e collaudo completo.

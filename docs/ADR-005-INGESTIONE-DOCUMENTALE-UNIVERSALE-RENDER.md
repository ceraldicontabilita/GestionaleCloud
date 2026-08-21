# ADR-005: Render orchestra l'ingestione documentale universale

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

**Status:** Accepted
**Date:** 2026-08-21
**Deciders:** Ceraldi Group S.r.l.

## Context

Il pilot Render iniziale analizzava soltanto i cedolini presenti nel Calderone
e ricalcolava gli hash a ogni esecuzione. Il processo operativo deve invece
gestire tutti i documenti amministrativi, fiscali, bancari e del personale,
senza creare un archivio o una pipeline parallela al GestionaleCloud.

## Decision

Render esegue un solo task generale, `calderone_documenti_preview`, sulla
cartella `01 - IN ARRIVO`. Prima di classificare un contenuto confronta il suo
SHA-256 con `INDICE_DOCUMENTALE_DRIVE.xlsx`, indice canonico del Gestionale.
Un hash già registrato viene contato come occorrenza duplicata e non viene
inviato ai parser specialistici. Un hash nuovo viene classificato e, nelle
successive fasi autorizzate, passerà dall'ingresso canonico `documents_inbox`.

Il task è inizialmente in sola lettura: non importa, sposta, rinomina o elimina
file. Se l'indice non è configurato, non contiene SHA-256 o non è leggibile,
il task fallisce senza dichiarare documenti nuovi.

Formati iniziali: PDF, ZIP, XLSX, XLS, CSV, XML, P7M ed EML. I parser di
cedolini, F24, dichiarazioni, estratti conto, bonifici, fatture, cartelle,
avvisi e verbali restano moduli di dominio della pipeline unica.

## Options Considered

### Task separato per ogni tipologia

| Dimensione | Assessment |
|---|---|
| Complessità | Alta |
| Costo | Riscansioni duplicate |
| Scalabilità | Bassa |
| Coerenza | Pipeline parallele |

### Un solo ingresso documentale indicizzato

| Dimensione | Assessment |
|---|---|
| Complessità | Media |
| Costo | Classificazione solo dei nuovi hash |
| Scalabilità | Alta |
| Coerenza | Riusa Drive/Sheets e `documents_inbox` |

## Consequences

- I documenti esistenti vengono riconosciuti prima dell'estrazione.
- Le occorrenze duplicate mantengono la provenienza e non sono eliminate.
- I casi ambigui restano `DA_VERIFICARE`.
- La prima indicizzazione completa è un bootstrap una tantum.
- L'attivazione della fase di scrittura richiederà conferma sui dati e test
  end-to-end contro il Gestionale live.

## Action Items

1. Configurare `GOOGLE_DRIVE_DOCUMENT_INDEX_FILE_ID` nel Workflow Render.
2. Verificare in anteprima l'indice e i conteggi senza trasmettere documenti.
3. Collegare i soli hash nuovi a `/api/documenti/upload-auto` con autenticazione
   di servizio, idempotency key e audit.
4. Aggiungere watermark/manifest delle sorgenti per saltare ZIP e file Drive
   invariati senza riscaricarli.
5. Attivare il cron soltanto dopo collaudo e conferma esplicita.

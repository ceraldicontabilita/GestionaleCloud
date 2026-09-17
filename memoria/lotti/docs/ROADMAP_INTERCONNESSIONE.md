# Roadmap interconnessione gestionale

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Obiettivo: trasformare il gestionale da insieme di moduli collegati in modo
parziale a sistema dati unico, dove fatture, fornitori, prodotti, magazzino,
ricette, food cost, lotti e HACCP condividono riferimenti canonici.

## Fase 1 - Visibilita operativa

Completata con il primo "Centro controllo dati":

- endpoint `GET /api/controllo-dati/overview`;
- vista frontend `#controllo_dati` nel menu Altro;
- conteggi e campioni per prodotti senza fornitore/prezzo, fatture deboli,
  righe fattura senza link prodotto, ingredienti ricetta non collegati, lotti
  senza tracciabilita, movimenti magazzino senza prodotto e job scheduler falliti.

Questa fase non modifica i dati. Serve a rendere misurabile cosa non e
interconnesso.

## Fase 2 - Identificativi canonici

Definire e rendere espliciti questi riferimenti:

- `supplier_id` o P.IVA canonica su fatture, schede ricevimento, ordini e listini;
- `prodotto_master_id` sulle righe fattura, sugli ingredienti ricetta e sui
  movimenti di magazzino;
- `lotto_id` collegato a produzione, ingredienti consumati e registri HACCP.

Prima regola: ogni nuovo dato deve salvare il riferimento canonico. Seconda
regola: i dati storici vengono backfillati senza interrompere le schermate
legacy.

## Fase 3 - Pipeline unica

Portare il flusso principale a questa sequenza:

```text
Gestionale / XML fatture
-> fornitori canonici
-> prodotti_master
-> prezzi e storico acquisti
-> ricette e food cost
-> magazzino e scorte
-> ordini fornitori
-> produzione, lotti e HACCP
-> dashboard e report
```

Ogni step deve scrivere un log strutturato con record letti, record aggiornati,
errori e ultimo esito.

## Fase 4 - Backfill controllati

Implementare job manuali e idempotenti:

- collega righe fattura a `prodotti_master`;
- collega ingredienti ricetta a `prodotti_master`;
- collega movimenti magazzino a prodotto canonico;
- collega lotti a ingredienti/fatture quando possibile;
- deduplica fornitori per P.IVA e nome normalizzato.

Ogni job deve avere preview, esecuzione, log e rollback logico tramite audit.

## Fase 5 - Vincoli progressivi

Dopo il backfill:

- rendere obbligatorio `prodotto_master_id` nei nuovi movimenti e righe fattura;
- rendere obbligatorio il fornitore canonico nelle fatture importate;
- impedire nuove ricette con ingredienti non mappati, salvo bozza;
- mostrare nel Centro controllo dati solo eccezioni reali da lavorare.

## Priorita pratica

1. Salvare `prodotto_master_id` durante sync fatture e import XML.
2. Aggiungere una funzione di riconciliazione ingredienti ricetta -> prodotti_master.
3. Backfillare i movimenti magazzino storici.
4. Rendere lo scheduler osservabile con ultimo esito e retry manuale.
5. Spostare logica di dominio dai router a servizi riusabili, partendo da
   fatture/prodotti/ricette.

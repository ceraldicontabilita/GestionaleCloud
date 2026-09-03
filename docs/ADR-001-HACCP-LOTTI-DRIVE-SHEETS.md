# ADR-001: Fusione completa Lotti nel dominio HACCP Drive/Sheets

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

**Stato:** Superata il 03/09/2026 — il modulo nativo `/tracciabilita` è stato
rimosso su ordine del titolare; l'app Lotti originale è montata pari pari a
`/lotti` (vedi `CLAUDE.md`). Conservato come documento storico.
**Data:** 2026-08-22
**Decisore:** Ceraldi Group

## Contesto

Il repository storico Lotti contiene tracciabilità, temperature, sanificazioni,
disinfestazioni, anomalie, controllo olio, ricette, produzioni, gelati, scorte,
ricezione merce e funzioni amministrative. La persistenza storica non è più
disponibile e GestionaleCloud usa esclusivamente Google Drive/Sheets.

Fatture, fornitori, corrispettivi, prodotti e ordini possiedono già identità e
flussi canonici in GestionaleCloud. Copiare i rispettivi router Lotti creerebbe
doppie fonti e stati divergenti.

## Decisione

Lotti viene assorbito in una sola area `/tracciabilita`, senza applicazione o
database paralleli:

- fatture, fornitori, prodotti, corrispettivi e ordini restano quelli canonici;
- le righe merce 2026 alimentano ricezioni e lotti con import idempotente;
- i registri HACCP sono eventi append-only con soglie congelate al momento;
- ogni non conformità crea subito un'attesa di azione correttiva;
- ricette e produzioni sono versionate e collegate ai consumi dei lotti;
- attrezzature, allergeni, shelf-life e provenienza restano campi espliciti;
- nessun dato viene inventato quando la fonte storica non è recuperabile.

## Alternative considerate

### Copia integrale del vecchio backend

Rifiutata: reintrodurrebbe un archivio parallelo, duplicati di
fatture/fornitori e oltre settanta router con contratti incompatibili con
autorizzazione e audit correnti.

### Applicazione Lotti separata

Rifiutata: manterrebbe due interfacce, due autenticazioni e due fonti operative.

### Modulo nativo per dominio

Scelto: riusa i fatti canonici e conserva solo i nuovi fatti HACCP nei fogli
dedicati del registro Drive/Sheets.

## Conseguenze

- La ricostruzione parte dal workbook e dagli originali Drive.
- Gli storici privi di una fonte verificabile non vengono ricreati artificialmente.
- Le funzioni Lotti sono organizzate per processo, non per vecchio router.
- Ogni scrittura è autenticata, idempotente, auditata e coperta da test.
- La pubblicazione richiede suite backend/frontend, CI e verifica del commit live.

# AUDIT FLUSSI OPERATIVI (24/07/2026) — dal codice reale + test su Mongo di prova

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Test E2E: backend/tests/test_e2e_flussi.py su mongomock (DB Gestionale_Test,
MAI il db reale, zero rete). PROVA CON FATTURA VERA di Enzo (F.lli
Fiorentino, 12 righe): import ok, 12 lotti fornitori creati, SECONDO import
della stessa fattura → nessun duplicato (1 fattura, 12 lotti). Il file reale
NON è stato salvato nel repo (niente dati reali nei test).

## Flusso 1 Fattura→prodotto→lotto→giacenza [VERIFICATO con test]
Crea: fatture (chiave numero+piva, upsert+DuplicateKeyError), fornitori(+
anagrafica), lotti_fornitori (chiave fattura+fornitore+prodotto), stock bar
(solo alimentari bar, idempotente), listino, aliases dizionario.
Rollback: DELETE fattura NON fa cascade (lotti/stock/listino restano) → [MEDIA].

## Flusso 2 Ricetta→produzione→FIFO→lotto [VERIFICATO con test]
FIFO: finestra 60gg, più vecchio prima, vecchi in riserva; conversioni unità;
mai negativi. Rollback: DELETE produzione con claim atomico ripristina le
quantità (corretto). PROBLEMI: doppio invio produzione NON idempotente
[MEDIA, da fare]; scarico parziale ora SEGNALATO (fix 24/07:
ingredienti_insufficienti + toast tablet) — prima ignorato in silenzio.

## Flusso 3 Produzione→banco→residuo [VERIFICATO a codice]
manda-al-banco valida 0<pezzi<=disponibile; invenduto = movimento tracciante
(non torna in giacenza, per scelta). PROBLEMA: non atomico al doppio tap
[MEDIA, da fare: find_one_and_update condizionale].

## Flusso 4 Lotto fornitore→produzioni→richiamo ASL [VERIFICATO a codice]
Percorso affidabile: per-lotto-fornitore via storico_utilizzi. Esegui scrive
richiami_eseguiti + movimenti recall. PROBLEMI: il richiamo NON blocca i
lotti (restano mandabili al banco) [BASSA/da valutare con Enzo]; recall per
ingrediente non risale al fornitore sui lotti nuovi [BASSA].

## Flusso 5 Sotto scorta→bozza→carrello→inviato [VERIFICATO a codice]
3 sorgenti bozze con dedup incrociata; conferma/invio con gate admin; invio
con claim atomico anti-doppio-tap. FIX APPLICATO 24/07: la validazione
"righe confermate" ora avviene PRIMA del claim (prima un ordine senza righe
confermate restava marcato inviato e non partiva mai più).

## Incoerenze residue in ordine di gravità (DA FARE)
1. ALTA fatture senza P.IVA: due fornitori diversi con stesso numero
   collidono e la seconda SOVRASCRIVE la prima (fatture.py:535-560 + indice
   uniq_numero_piva) — serve chiave che includa il fornitore quando piva="".
2. MEDIA produzione non idempotente al doppio tap.
3. MEDIA manda-al-banco non atomico.
4. MEDIA DELETE fattura senza cascade.
5. BASSA richiamo non blocca i lotti; invenduto non recuperabile come
   giacenza (scelta); docstring fuori posto in ordini (cosmetico).

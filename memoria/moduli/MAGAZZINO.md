# Magazzino / Acquisti / Prodotti — stato reale vs specifica

<!-- gestionalecloud-doc
status: reference
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

> [!IMPORTANT]
> Documento di riferimento del dominio. Per persistenza e cutover vale l'architettura Drive-only descritta nei documenti correnti; eventuali nomi di collection restano soltanto contesto storico.

Fonte specifica: `Magazzino Acquisti Prodotti.txt` (fornita dall'utente).
Verificato leggendo il codice attuale (post-consolidamento router del 2026-07-07).

## Correzione importante: il commento "gestito solo da Lotti" è FALSO

`memoria/moduli/FATTURE_RICEVUTE.md` (gap #2) riportava, citando un commento nel codice
(`fatture_upload.py:912`: *"Giacenze magazzino: gestite SOLO dall'app esterna Lotti — nessun
aggiornamento di warehouse_inventory dall'import fatture"*), che il modulo Magazzino fosse
interamente delegato all'app esterna Lotti. **Verifica più approfondita smentisce il
commento**: subito dopo quel punto, `fatture_upload.py` chiama
`propagate_event(EventTypes.FATTURA_CREATED, ...)`, che attiva
`app/services/handlers/magazzino_handlers.py::on_fattura_righe_magazzino`, il quale
**scrive attivamente** su `warehouse_inventory` (`update_one`/`insert_one`). Il commento è
un residuo obsoleto, non riflette il comportamento reale. Ci sono almeno **3 scrittori
indipendenti** di `warehouse_inventory`: `magazzino_handlers.py`, `warehouse_helpers.py`, e
`fornitori_learning.py:477` (endpoint `associa-magazzino`).

Nota anche il canale import: come per Fatture Ricevute, ovunque la spec citi l'importazione
fatture come innesco per il popolamento magazzino, la fonte reale è Google Drive/PEC-SDI
(non "Aruba"), stessa pipeline `process_xml_bytes` documentata in `FATTURE_RICEVUTE.md`.

## Cosa è confermato implementato

| Requisito spec | Stato | Evidenza |
|---|---|---|
| Prodotto come entità, auto-creato da righe fattura | ✅ | `magazzino_handlers.py::_crea_prodotto_nuovo` (riga 245) |
| Dizionario prodotti con alias | ✅ | `magazzino_handlers.py::_aggiorna_dizionario` (riga 281), collezione `dizionario_prodotti` |
| Normalizzazione nome prodotto | ✅ (due algoritmi diversi e indipendenti) | `_normalizza_nome_prodotto` in `magazzino_handlers.py:189`; `normalize_product_name` in `warehouse_helpers.py` (stop-word removal, algoritmo diverso) |
| Matching 3 livelli (esatto → normalizzato → fuzzy) | ⚠️ PARZIALE | `_cerca_prodotto_3_livelli` (`magazzino_handlers.py:137`): livello 1 e 2 reali; livello 3 "fuzzy" è in realtà un prefix-regex di 10 caratteri, non fuzzy matching vero; etichette solo `"certo"`/`"probabile"`, nessuna soglia numerica alta/media/bassa richiesta dalla spec |
| Aggiornamento giacenza automatico da fattura | ✅ | `_aggiorna_prodotto_esistente` (`magazzino_handlers.py:210`), `$inc` su `warehouse_inventory.giacenza` |
| Ricerca prodotti con vera fuzzy matching (`difflib.SequenceMatcher`) | ✅ ma isolata | `warehouse_helpers.py::search_products_predictive` (riga 396) — usata solo per autocomplete/ricerca, non per l'ingestion da fattura |

## Gap confermati (in ordine di priorità)

1. **Riordino automatico completamente assente**: nessuna logica `riordino`/`reorder`/
   `scorta_minima` in tutto `app/`. Esiste solo il campo `giacenza_minima` sul prodotto, ma
   è confrontato SOLO dentro una funzione morta (`on_verifica_sotto_scorta`, vedi punto 2) —
   non genera mai un ordine o una notifica di riordino nella pratica.
2. ~~**Handler duplicato e morto per il carico magazzino**~~ — **SUPERATO (lug 2026)**:
   il doppio event bus è stato unificato (`app/core/event_bus.py` rimosso, unica registry
   in `app/services/event_bus.py`). L'handler vivo per il carico magazzino resta
   `magazzino_handlers.py::on_fattura_righe_magazzino` su `EventTypes.FATTURA_CREATED`.
3. ~~**`on_verifica_sotto_scorta` non è mai chiamata**~~ — **RISOLTO**. Schedulato job
   giornaliero (ore 6:30, `app/scheduler.py::check_scorta_magazzino_task`).
4. ~~**Solo 2 alert su 5 registrati sono realmente generati**~~ — **RISOLTO per altri 2**:
   `MAG_UNITA_INCOERENTE` ora scatta in `_aggiorna_prodotto_esistente` quando l'unità di
   misura di una riga fattura differisce da quella già registrata sul prodotto;
   `MAG_DUPLICATO_PRODOTTO` scatta in `_crea_prodotto_nuovo` con un vero controllo fuzzy
   (`difflib.SequenceMatcher`, soglia 0.85) sul dataset attivo, prima di creare un prodotto
   che il matching 3 livelli non ha riconosciuto — cattura typo/varianti minime, non
   riordini di parole (limite noto e condiviso con `fornitori_dedupe.py`). Ora 4 alert su 5
   sono vivi (solo `MAG_SOTTO_SCORTA` restava da sbloccare, vedi punto 3 sopra — anch'esso
   ora attivo). La spec ne richiede 6, nel codice ne esistono 5 definiti.
5. **Matching fuzzy vero esiste ma è isolato dalla pipeline di ingestion**: la funzione con
   fuzzy matching reale (`difflib.SequenceMatcher`, soglia 0.3) serve solo la ricerca/
   autocomplete lato utente (`search_products_predictive`), non viene mai chiamata quando
   una riga fattura cerca un prodotto esistente — la pipeline di ingestion usa solo il
   prefix-regex del punto sopra.
6. **Tre scrittori indipendenti di `warehouse_inventory` senza sincronizzazione garantita**
   (`magazzino_handlers.py`, `warehouse_helpers.py`, `fornitori_learning.py`) — nessuna
   verifica effettuata sul fatto che scrivano con le stesse chiavi/formati o che non si
   sovrascrivano a vicenda.

## Bug/incoerenze note (da correggere)

- Il commento in `fatture_upload.py:912` va aggiornato/rimosso perché descrive un
  comportamento (nessuna scrittura su `warehouse_inventory` dall'import fatture) che è
  falso nella pratica — rischio concreto di fuorviare futuri sviluppatori.
- Due algoritmi di normalizzazione nome prodotto indipendenti e diversi
  (`magazzino_handlers.py` vs `warehouse_helpers.py`) possono produrre chiavi normalizzate
  diverse per lo stesso prodotto a seconda del percorso di codice che lo tocca —
  potenziale causa di duplicati non rilevati dal dedup.

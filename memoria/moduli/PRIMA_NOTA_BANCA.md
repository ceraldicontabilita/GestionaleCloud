# Prima Nota Banca — stato reale vs specifica

Fonte specifica: `Prima Nota Banca E Flussi Automatici.txt` (fornita dall'utente).
Verificato leggendo il codice attuale (post-consolidamento router del 2026-07-07).

## Correzione canale (coerente con gli altri documenti)

Dove la spec presuppone import fatture via "Aruba PEC" come innesco del flusso
fatture→bonifici: la fonte reale è Google Drive/PEC-SDI generico, vedi
`memoria/moduli/FATTURE_RICEVUTE.md`.

## Cosa è confermato implementato

| Requisito spec (7 flussi) | Stato | Evidenza |
|---|---|---|
| Import estratto conto (EC) | ✅ ma solo CSV | `app/routers/bank/estratto_conto.py`, dedup su tupla `(data, importo_abs, descrizione)` + fingerprint MD5, righe commissione ≤2€ escluse dal dedup |
| Fatture → bonifici (matching) | ✅ | `riconciliazione_bancaria.py::_applica_pagamento_banca`, `match_fornitore_descrizione`, `match_numero_fattura_descrizione` |
| POS → accrediti | ⚠️ PARZIALE | alert `BNK_POS_NON_RICONCILIATO` generato da `app/scheduler.py:108`; logica di matching POS vera e propria vive nel motore di riconciliazione (vedi `RICONCILIAZIONE.md`), non in questo file |
| F24 ↔ banca | ✅ ma solo binario | blocco dedicato in `riconciliazione_bancaria.py` righe 716-754, aggiorna `f24_unificato` e propaga `F24_PAGATO` |
| Trasferimenti interni banca↔cassa | ✅ | `app/services/handlers/trasferimento_handlers.py:15-89` — modellati come **due movimenti collegati** (non un semplice flag "tipo=trasferimento"): inserimento speculare nella collezione opposta con `causale/categoria: "trasferimento_interno"` e `trasferimento_collegato_id` incrociato |

## Gap confermati (in ordine di priorità)

1. ~~**Stipendi ↔ banca: matching NON esiste**~~ — **CORREZIONE + RISOLTO**. La formulazione
   originale era imprecisa: il matching non è dentro `riconciliazione_bancaria.py` (corretto,
   zero risultati per "stipendio"/"cedolino" lì), ma esiste in un servizio parallelo,
   `app/services/paghe_riconciliazione.py::esegui_riconciliazione_paghe_completa`, **già
   chiamato in produzione** subito dopo `riconciliazione_bancaria.py` ad ogni upload reale di
   estratto conto (`app/routers/bank/estratto_conto.py:430`). Il gap REALE era più specifico:
   quella funzione riconciliava solo `buste_paga` (collection alimentata unicamente
   dall'upload manuale del Libro Unico PDF), MAI `cedolini` (collection del canale email,
   quello davvero usato secondo `CEDOLINI.md`) — i cedolini email non avevano nemmeno un
   campo `pagata` popolato, restavano "non pagati" a tempo indeterminato. Risolto: aggiunta
   `riconcilia_tutti_cedolini()` (stessa logica di `riconcilia_tutti_stipendi`, adattata allo
   schema `cedolini`), agganciata a `esegui_riconciliazione_paghe_completa`. Corretto anche a
   monte: `post_download_pipeline.py` (canale email) ora propaga `CEDOLINO_IMPORTATO` come
   già faceva solo l'inserimento manuale — prima un cedolino via email non generava mai una
   partita aperta né l'alert dipendente-non-trovato. Verificato con test end-to-end.
2. **"Movimenti provvisori" non è uno stato reale**: non esiste una macchina a stati per i
   movimenti non ancora conciliati — solo un booleano `riconciliato: True/False` e un flag
   `provvisorio` isolato usato solo nell'handler dei trasferimenti. La spec chiede una gestione
   esplicita dei provvisori come categoria di flusso a sé; nel codice reale è solo l'assenza
   di match, non uno stato distinto tracciato.
3. **EC solo CSV**: nessun supporto per altri formati bancari citati genericamente dalla spec
   (es. OFX, MT940) — solo CSV testato/gestito in `estratto_conto.py`.
4. **6 alert su 7 registrati ma morti**: `alert_engine.py` definisce 7 costanti `BNK_*`
   (numero corretto secondo spec), ma solo `BNK_POS_NON_RICONCILIATO` viene effettivamente
   creato (`scheduler.py:108`); `BNK_TRASFERIMENTO_INCOMPLETO` viene solo *risolto*, mai
   creato; `BNK_NON_CLASSIFICATO`, `BNK_DUPLICATO`, `BNK_FAT_SENZA_RISCONTRO`,
   `BNK_F24_NON_RICONCILIATO`, `BNK_DIFFERENZA_IMPORTO` non hanno alcun punto di creazione
   nel codice — definiti ma mai generati.
5. **Nessuna spiegazione delle differenze di importo**: quando un importo non coincide
   esattamente, il sistema classifica solo come match/non-match/dubbio — non calcola/mostra
   la causa (commissione, pagamento parziale, arrotondamento) — vedi anche `RICONCILIAZIONE.md`.

## Bug/incoerenze note (da correggere)

- Nessuno stato esplicito sul movimento bancario (`stato` ad-hoc, non un vero enum) — rende
  fragile qualunque futura UI che voglia mostrare "in attesa di verifica" vs "conciliato" vs
  "provvisorio" in modo affidabile.

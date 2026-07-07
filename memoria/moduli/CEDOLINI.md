# Cedolini — stato reale vs specifica

Fonte specifica: `CEDOLINI.txt` (fornita dall'utente).
Verificato leggendo il codice attuale (post-consolidamento router del 2026-07-07).

## Canale di importazione (confermato, non serve correzione "Aruba")

I cedolini entrano via email, instradati dalla tabella `mittenti_email` — Studio
Ferrantini/Rosaria Marotta → cedolini/F24 → contabilità (righe 1-2 della tabella mittenti
attendibili reale fornita dall'utente). Pipeline: `app/services/post_download_pipeline.py`.

## Cosa è confermato implementato

| Requisito spec | Stato | Evidenza |
|---|---|---|
| Cedolino come entità, tipo (mensile/acconto/tredicesima/quattordicesima/sospensione/solo_trattenute) | ✅ | campo `tipo_cedolino` popolato, es. `"mensile"` in `app/routers/employees/dipendenti.py:902`; struttura dati presente in `post_download_pipeline.py` |
| Salvataggio effettivo del cedolino nuovo importato da email | ✅ (bug corretto in questa sessione) | `post_download_pipeline.py::processa_cedolini_da_email` — il ramo "nuovo cedolino" prima incrementava solo un contatore senza mai chiamare `insert_one`; corretto nella sessione corrente, verificato con pytest |
| Regola "un cedolino non è automaticamente pagato solo perché importato" | DA VERIFICARE nel dettaglio | non riconfermato in questo passaggio se esiste un campo `pagato` separato dal semplice import, o se l'assenza di un flag esplicito lascia il cedolino implicitamente "non pagato" per default (che sarebbe comunque conforme alla regola, ma va verificato esplicitamente) |
| Dedup cedolino | ✅ | campo `dedup_key` presente nell'insert corretto (`post_download_pipeline.py`, basato su CF+mese+anno presumibilmente) |

## Gap confermati (in ordine di priorità)

1. **Cedolino → prima_nota_salari: automazione non riverificata in questo passaggio**. La
   spec richiede che l'import di un cedolino generi automaticamente una registrazione in
   prima nota salari — non confermato in questo giro se questo collegamento è realmente
   implementato o solo previsto. Da verificare in un audit dedicato prima di considerarlo
   coperto.
2. **Cedolino → TFR: automazione non riverificata**. La spec chiede che la quota TFR venga
   letta dal PDF cedolino o calcolata come lordo/13.5 se assente — `app/routers/employees/
   tfr.py` (1658 righe) esiste ed è confermato vivo (vedi `DIPENDENTI.md`), ma il
   collegamento automatico cedolino→TFR non è stato riverificato in questo passaggio.
3. **Cedolino ↔ presenze: non riverificato**. Nessuna evidenza raccolta in questo passaggio
   sul collegamento tra cedolino e dati presenze/turni.
4. **Cedolino ↔ pagamento banca ↔ riconciliazione: GAP CONFERMATO e già documentato in
   modo incrociato**. `PRIMA_NOTA_BANCA.md` e `RICONCILIAZIONE.md` confermano
   esplicitamente (grep su `riconciliazione_bancaria.py`) che **non esiste alcuna logica di
   matching stipendi↔movimento bancario** nel motore di riconciliazione automatica — la
   regola "un cedolino non è automaticamente pagato solo perché importato" è di fatto
   rispettata per assenza di automazione, ma questo significa anche che la conferma di
   pagamento cedolino via banca **non è automatizzata affatto**, richiedendo verifica
   manuale sistematica non prevista come flusso strutturato.
5. **9 alert richiesti dalla spec**: non riverificati in questo passaggio — audit dedicato
   necessario per determinare quanti sono realmente definiti in `alert_engine.py` e quanti
   effettivamente generati (pattern ricorrente in tutti gli altri moduli: spesso meno della
   metà degli alert dichiarati risultano vivi).

## Bug/incoerenze note (da correggere)

- Bug del cedolino-non-salvato (vedi tabella sopra) è stato l'unico bug concreto trovato e
  già corretto in questa sessione.
- Data la conferma incrociata del gap #4 (nessun matching stipendi↔banca in
  `riconciliazione_bancaria.py`), questo è il gap più prioritario e trasversale tra
  Cedolini, Prima Nota Banca e Riconciliazione — un'unica funzionalità mancante che appare
  in 3 documenti diversi.

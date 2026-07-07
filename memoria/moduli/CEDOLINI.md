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
| Regola "un cedolino non è automaticamente pagato solo perché importato" | ✅ | campo `pagata` esplicito, `False` alla creazione (sia canale email che manuale), diventa `True` SOLO tramite match bancario reale (vedi gap #4, ora risolto) — mai un default implicito |
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
4. ~~**Cedolino ↔ pagamento banca ↔ riconciliazione**~~ — **RISOLTO** (vedi correzione
   dettagliata in `PRIMA_NOTA_BANCA.md` gap #1). Il matching esisteva già ma copriva solo
   `buste_paga` (canale Libro Unico), non `cedolini` (canale email, quello reale). Aggiunta
   `riconcilia_tutti_cedolini()` in `paghe_riconciliazione.py`, agganciata allo stesso punto
   già chiamato dopo ogni upload estratto conto. Anche l'evento `CEDOLINO_IMPORTATO` ora
   viene propagato dal canale email (prima solo dall'inserimento manuale) — un cedolino
   email genera correttamente la partita aperta stipendio.
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

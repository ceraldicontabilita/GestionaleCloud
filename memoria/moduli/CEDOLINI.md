# Cedolini — stato reale vs specifica

<!-- gestionalecloud-doc
status: reference
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!IMPORTANT]
> Documento di riferimento del dominio. Per persistenza e cutover vale l'architettura Drive-only descritta nei documenti correnti; eventuali nomi Mongo/collection restano compatibilità o contesto storico.

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
5. ~ PARZIALE (lug 2026) — inventario completo dei 9 alert `CED_*` definiti in
   `alert_engine.py`, verificando ogni sito di generazione/risoluzione reale nel codice
   (non solo la definizione):
   - Già vivi prima di questo passaggio: `CED_DIP_NON_TROVATO`,
     `CED_DATI_ECONOMICI_INCOMPLETI` (`cedolino_handlers.py::on_cedolino_importato`),
     `CED_NON_PAGATO` (mapping in `app/scheduler.py::check_scadenze_partite_task`).
   - ✔ RISOLTI in questo passaggio: `CED_DUPLICATO` — generato in
     `on_cedolino_importato` quando esiste già un cedolino con stesso CF+mese+anno
     (diverso id); `CED_MATCH_BANCA_AMBIGUO` — generato in
     `paghe_riconciliazione.py::riconcilia_tutti_cedolini()` quando più movimenti
     bancari rientrano nella stessa finestra importo/data del match accettato (prima
     esisteva solo la chiamata di *risoluzione* in `cedolino_handlers.py`, mai una
     generazione: l'alert non poteva mai comparire). Entrambi additivi/best-effort,
     non cambiano quale movimento/cedolino viene accettato come match, solo lo
     segnalano. Verificato con mongomock: alert corretto sui due casi, nessun falso
     positivo su mese diverso, il cedolino resta comunque riconciliato.
   - Restano NON generati (solo definiti): `CED_TIPO_NON_RICONOSCIUTO`,
     `CED_PRIMA_NOTA_NON_GENERATA`, `CED_TFR_NON_AGGIORNATO`, `CED_INCOERENZA_PRESENZE`
     — richiedono rispettivamente: un enum di validazione su `tipo_cedolino` in fase di
     parsing (oggi il campo è libero), un confronto cedolino↔prima_nota_salari da
     costruire (collegato al gap #1 sopra, non ancora riverificato), un confronto
     cedolino↔TFR (collegato al gap #2), e dati presenze/turni che non risulta siano
     mai stati verificati come realmente tracciati in questo repo (gap #3) — quindi
     `CED_INCOERENZA_PRESENZE` potrebbe non avere nemmeno la fonte dati per essere
     calcolato. Non affrontati in questo passaggio: dipendono da altri gap non ancora
     chiusi, rischio di costruire alert su dati che non esistono ancora.

## Bug/incoerenze note (da correggere)

- Bug del cedolino-non-salvato (vedi tabella sopra) è stato l'unico bug concreto trovato e
  già corretto in questa sessione.
- Data la conferma incrociata del gap #4 (nessun matching stipendi↔banca in
  `riconciliazione_bancaria.py`), questo è il gap più prioritario e trasversale tra
  Cedolini, Prima Nota Banca e Riconciliazione — un'unica funzionalità mancante che appare
  in 3 documenti diversi.

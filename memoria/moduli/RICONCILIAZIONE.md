# Riconciliazione — stato reale vs specifica (documento master)

<!-- gestionalecloud-doc
status: reference
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!IMPORTANT]
> Documento di riferimento del dominio. La specifica normativa unica è `PROMPT_MASTER.md`; questo file non può contraddirla.

Fonte specifica: `Riconciliazione — Flussi automatici — Logica relazionale completa.txt`
(fornita dall'utente, il documento più complesso dei 10). Verificato leggendo il codice
attuale, DOPO la consolidazione già effettuata in questa sessione (9 sistemi di
riconciliazione paralleli ridotti a 1 motore canonico + l'indice partite aperte — vedi
`PROMPT_MASTER.md` per la regola normativa completa
dell'unificazione).

## Architettura reale oggi (post-unificazione)

- **Motore canonico**: `app/services/riconciliazione_bancaria.py`
  (`riconcilia_movimenti_banca()`, ~900 righe) — unica pipeline di matching automatico
  attiva, schedulata ogni 30 min (`app/scheduler.py`) e invocata subito dopo ogni upload
  reale di estratto conto (`app/routers/bank/estratto_conto.py`).
- **Indice partite aperte**: `app/services/partite_aperte_engine.py` — popolato da
  event-handler quando fatture/F24/cedolini/corrispettivi vengono creati, letto dalla
  Dashboard Relazionale.

## Confronto con il modello a 3 entità richiesto dalla spec

La spec chiede 3 entità distinte con stati propri: **movimento reale** (8 stati),
**partita attesa** (5 stati), **match** (5 stati).

| Entità spec | Stato reale | Evidenza |
|---|---|---|
| Partita attesa | ✅ 5 stati, combacia con la spec | `StatoPartita` enum in `partite_aperte_engine.py:47-52`: `aperta, parziale, chiusa, compensata, da_verificare` |
| Movimento reale | ❌ nessuno stato, solo un booleano | `estratto_conto_movimenti` ha solo `"riconciliato": True/False` (`riconciliazione_bancaria.py` righe 406,439,720,732...) — non gli 8 stati richiesti |
| Match | ⚠️ PARZIALE | collezione `riconciliazioni_match` esiste, ma solo ~2 stati osservati (`"confermato"`, `"da_confermare"`), non i 5 richiesti |

## Motore decisionale: NON è una pipeline pulita a 4 passi

La spec chiede: match esatto → pattern noto → approssimato → nessun match, come 4 fasi
distinte e sequenziali. Il codice reale (`riconcilia_movimenti_banca()`, righe 377-885) è
invece **un unico passaggio a punteggio pesato per movimento** (importo esatto +10, fornitore
fuzzy +3/+5, numero fattura esatto, ecc. — righe 458-503) che prova le categorie di candidati
in sequenza (fatture → F24 → POS → versamenti) ma senza una fase "pattern noto" distinta da
quella "approssimata" — sono la stessa logica di scoring con soglie diverse, non fasi separate.

## Regole per tipo — confronto puntuale

| Caso spec | Stato | Evidenza |
|---|---|---|
| Fattura: caso semplice | ✅ | matching diretto per importo+fornitore |
| Fattura: caso multiplo (ambiguo, più candidati) | ✅ | `"fatture_multiple"`, righe 627/694 |
| Fattura: nota di credito con netting | ❌ ASSENTE | nessun codice trovato che gestisca TD04/nota di credito nel motore di riconciliazione — coerente con il gap già segnalato in `FATTURE_RICEVUTE.md` |
| Fattura: bonifico cumulativo (più fatture in un solo bonifico) | ❌ ASSENTE | `"fatture_multiple"` significa più fatture CANDIDATE per un movimento (ambiguità), non somma di più fatture per un unico pagamento — funzionalità diversa e non trovata |
| F24: standard | ✅ | match importo/data base |
| F24: ambiguo / differenza importo | ❌ ASSENTE | nessuna sotto-casistica oltre alla coda ambigua generica — vedi anche `F24.md` |
| POS: semplice | ✅ | matching giornaliero, righe 793-822 |
| POS: cumulativo (weekend) | ✅ | somma su più giorni, righe 770-796 |
| POS: netto commissioni | ❌ ASSENTE | tolleranza flat ±1€, nessuna sottrazione esplicita delle commissioni prima del confronto |
| Stipendi: standard/cumulativo | ✅ CORRETTO — non in `riconciliazione_bancaria.py` ma in `paghe_riconciliazione.py`, già live sullo stesso trigger (upload EC). Vedi `PRIMA_NOTA_BANCA.md` gap #1 per la correzione completa |
| Assegni | ⚠️ PARZIALE | solo verifica numero assegno (`num_assegno`, riga 558-567), nessuna gestione esplicita dei casi assegno della spec |
| Trasferimenti interni | ✅ | gestiti da `trasferimento_handlers.py` (vedi `PRIMA_NOTA_BANCA.md`) |

## Gap confermati (in ordine di priorità)

1. **Nessuna spiegazione delle differenze di importo**: il sistema classifica solo
   match/non-match/dubbio in base a soglie — non calcola né mostra la causa di una
   differenza (commissione, pagamento parziale, arrotondamento), violando esplicitamente
   il requisito spec "gestione differenze importo con spiegazione, non solo mismatch".
2. **Nessuna gestione della nota di credito nel motore di riconciliazione** (coerente col
   gap #1 di `FATTURE_RICEVUTE.md`) — rischio concreto di doppio conteggio o mancata
   compensazione.
3. ~~**Nessun matching stipendi↔banca**~~ — **CORREZIONE**: esisteva già, ma copriva solo
   `buste_paga` (canale Libro Unico) e non `cedolini` (canale email reale) — risolto
   estendendo `paghe_riconciliazione.py`, vedi `PRIMA_NOTA_BANCA.md` gap #1 e
   `CEDOLINI.md` gap #4.
4. **Nessun matching POS netto commissioni** — tolleranza flat, non calcolo delle commissioni.
5. **Movimento reale senza vera macchina a stati**: solo booleano `riconciliato`, non gli
   8 stati richiesti dalla spec — nessuna distinzione tracciabile tra "non esaminato",
   "in verifica", "dubbio", "escluso manualmente", ecc.
6. ✔ RISOLTO (lug 2026) — tutti e 6 gli alert `RIC_*` ora effettivamente generati:
   `RIC_MATCH_AMBIGUO`, `RIC_NON_RICONCILIATO` e `RIC_DIFFERENZA_IMPORTO` in
   `riconciliazione_bancaria.py`, `RIC_POS_NON_QUADRATO` in
   `pos_corrispettivi_check.py::alert_oggi()` (sui casi `stato_accredito`
   mancante/differenza). `RIC_DIFFERENZA_IMPORTO` risponde anche al gap #1 di questo
   stesso documento ("nessuna spiegazione delle differenze di importo"): quando il
   motore accetta un match per tolleranza (±10%, es. rata/commissione/arrotondamento)
   invece che a importo esatto, ora genera un alert con la differenza calcolata invece
   di riconciliare in silenzio. Tutte chiamate additive best-effort (try/except, non
   toccano la logica di calcolo/matching, solo la rendono visibile), verificate con
   mongomock: nessun alert su match esatto (zero falsi positivi), alert corretto su
   match con differenza, idempotenza su run ripetuti.

   `RIC_PARTITA_VECCHIA` wired in `app/scheduler.py::check_scadenze_partite_task()`
   (job giornaliero ore 7:00), con DUE query aggiuntive rispetto al mapping
   esistente (fattura_fornitore/f24/stipendio/pos_atteso): (a) partite scadute di
   tipo senza alert dedicato (`nota_credito`, `trasferimento`, `altro`) — prima
   finivano silenziosamente nel contatore `senza_mapping` senza generare mai nulla,
   anche se scadute da mesi; (b) partite aperte SENZA `data_scadenza` esplicita ma
   ferme da oltre 90 giorni dalla creazione — prima invisibili perché la query
   scadenze richiede sempre una `data_scadenza` valorizzata. Verificato con
   mongomock: alert generato sui due casi, non generato su una partita recente
   (5gg) senza scadenza, idempotenza su run ripetuti.

   `RIC_PAGAMENTO_MULTIPLO` wired in
   `riconciliazione_bancaria.py::_alert_pagamento_multiplo()`, chiamato quando un
   movimento in uscita esce dal motore senza match singolo (stesso punto di
   `RIC_NON_RICONCILIATO`): cerca fino a 40 fatture fornitore ancora aperte e
   verifica se la somma di una combinazione di 2 o 3 di esse combacia (±0.05€)
   con l'importo del movimento — il caso "bonifico cumulativo" mai gestito dal
   motore (vedi anche gap puntuale più sotto in questo documento). Solo
   rilevamento/segnalazione: non marca nulla come pagato né riconcilia
   automaticamente, la combinazione va sempre confermata da un operatore.
   Verificato con mongomock: alert corretto su combinazione 500+700=1200,
   nessun falso positivo su importo senza combinazione plausibile.

   **Bug collaterale trovato e corretto mentre si wired RIC_POS_NON_QUADRATO**:
   `alert_oggi()` chiamava `controllo_incassi_due_fasi(data_da=..., data_a=...,
   tolleranza_euro=...)` come funzione Python diretta (non richiesta HTTP), senza
   passare `anno=None` esplicitamente. Il parametro `anno` di
   `controllo_incassi_due_fasi` ha default `Query(None, ...)`: FastAPI risolve questo
   sentinel a `None` SOLO quando la funzione è invocata come endpoint via richiesta
   HTTP, non in una chiamata Python interna — quindi `anno` riceveva l'oggetto
   `Query(...)` stesso, che è truthy, facendo scattare il ramo `if anno:` che
   sovrascriveva `data_da`/`data_a` con stringhe corrotte (`"<fastapi.params.Query
   object...>-01-01"`), azzerando la query Mongo e quindi SEMPRE tutti gli alert.
   `GET /api/pos-corrispettivi/alert-oggi` (usato da `CoerenzaPOSCorrispettivi.jsx`)
   ha quindi sempre restituito zero alert in produzione, indipendentemente da eventuali
   incongruenze reali — bug riproducibile in modo deterministico, ora corretto.

## Sovrapposizione — verificata (lug 2026)

Oltre al motore canonico restavano 3 servizi di riconciliazione paralleli mai assorbiti
nell'unificazione. Verifica puntuale completata:

- `app/services/riconciliazione_intelligente.py` — ✔ RISOLTO, già rimosso in un audit
  precedente (commit `932d268`, 2026-07-07): zero chiamanti frontend funzionanti
  (l'unico, `conferma-multipla`, mandava payload F24 a un endpoint che si aspettava
  fatture → sempre 400). Non esiste più nel codice.

- `app/services/riconciliazione_smart.py` → `app/routers/operazioni_module/smart.py` —
  **vivo e con chiamanti frontend reali** (`RiconciliazioneUnificata.jsx` via
  `/api/operazioni-da-confermare/smart/*`). ✔ RISOLTI 2 bug reali trovati (lug 2026):
  1. `smart.py::analizza_singolo_movimento()` importava una funzione
     (`analizza_singolo_movimento` da `riconciliazione_smart.py`) mai esistita in quel
     modulo — ogni chiamata all'endpoint `GET .../smart/movimento/{id}` dava sempre
     ImportError/500. Corretto: carica il movimento e usa `analizza_movimento(movimento)`,
     la funzione realmente esistente.
  2. `riconcilia_manuale()` e `riconcilia_automatico()` marcavano la fattura pagata solo
     con `set_fattura_pagata()` diretto, SENZA creare il movimento in Prima Nota Banca né
     (nel caso automatico) propagare l'evento `FATTURA_PAGATA` — gap di coerenza rispetto
     al motore canonico, che invece fa tutto questo via `_applica_pagamento_banca()` in
     `riconciliazione_bancaria.py`. Risultato pratico: una fattura confermata da questo
     motore risultava "pagata" ovunque tranne che in Prima Nota Banca. Corretto in
     entrambe le funzioni: ora chiamano anche `registra_pagamento_fattura(fattura,
     "banca")` (idempotente) e (per il path automatico) propagano `FATTURA_PAGATA`.
     Verificato con mongomock: fattura riconciliata via `riconcilia_manuale` e via
     `riconcilia_automatico` produce entrambe le volte un movimento reale in
     `prima_nota_banca`, nessuna regressione sui 90 test esistenti.
  Le tolleranze di matching restano diverse da `riconciliazione_bancaria.py` (±1% qui vs
  scoring 10/15 là) — scelta consapevole di non toccare la logica di matching stessa in
  questo passaggio, solo la coerenza di cosa succede DOPO un match confermato.

- `app/services/riconciliazione_completa.py` → chiamato solo da un endpoint HTTP dedicato
  in `app/routers/email_download.py` (righe 725-741, match PagoPA/Agenzia
  Entrate/TARI + confronto POS/cassa/banca giornaliero). Verificato: nessun `<Link>`/
  `navigate()`/chiamata `fetch` nel frontend punta a questo endpoint — è raggiungibile
  solo per chiamata diretta all'API, non ha un bottone/trigger nella UI. Non rimosso in
  questo passaggio (a differenza della route email-download morta, questo scrive dati
  reali quando invocato — è una feature incompleta, non codice morto): decisione prodotto
  aperta se agganciarlo a un trigger UI reale o rimuoverlo.

## Bug/incoerenze note (da correggere)

- Il motore prende il primo match entro tolleranza in più punti (stesso pattern del bug
  F24 documentato in `F24.md`) invece di segnalare esplicitamente l'ambiguità quando ci sono
  più candidati equivalenti.
- ~~I 6 alert `RIC_*` completamente inerti~~ — RISOLTO (lug 2026), vedi punto 6 sopra:
  tutti e 6 ora effettivamente generati.

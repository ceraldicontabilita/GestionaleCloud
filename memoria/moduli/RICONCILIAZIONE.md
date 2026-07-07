# Riconciliazione — stato reale vs specifica (documento master)

Fonte specifica: `Riconciliazione — Flussi automatici — Logica relazionale completa.txt`
(fornita dall'utente, il documento più complesso dei 10). Verificato leggendo il codice
attuale, DOPO la consolidazione già effettuata in questa sessione (9 sistemi di
riconciliazione paralleli ridotti a 1 motore canonico + l'indice partite aperte — vedi
`memoria/endpoints/RICONCILIAZIONE_AUDIT.md` per la cronistoria completa
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
| Stipendi: standard/cumulativo | ❌ ASSENTE | nessun codice di matching stipendi trovato nel motore (vedi anche `PRIMA_NOTA_BANCA.md`, gap #1) |
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
3. **Nessun matching stipendi↔banca** — uno dei 5 tipi documento della spec non ha alcuna
   integrazione col motore di riconciliazione automatica.
4. **Nessun matching POS netto commissioni** — tolleranza flat, non calcolo delle commissioni.
5. **Movimento reale senza vera macchina a stati**: solo booleano `riconciliato`, non gli
   8 stati richiesti dalla spec — nessuna distinzione tracciabile tra "non esaminato",
   "in verifica", "dubbio", "escluso manualmente", ecc.
6. **6 alert su 8 definiti, ZERO effettivamente generati**: `alert_engine.py` definisce
   `RIC_NON_RICONCILIATO`, `RIC_MATCH_AMBIGUO`, `RIC_DIFFERENZA_IMPORTO`,
   `RIC_PARTITA_VECCHIA`, `RIC_POS_NON_QUADRATO`, `RIC_PAGAMENTO_MULTIPLO` — nessuno di
   questi risulta mai chiamato (`genera_alert(...)`) in tutto il codice al di fuori della
   loro definizione. Il sistema di alert per la riconciliazione è interamente inerte.

## Sovrapposizione da verificare (trovata nel nuovo audit generale)

Oltre al motore canonico, restano attivi e con chiamanti reali 3 servizi di riconciliazione
distinti che non sono stati assorbiti nell'unificazione:
- `app/services/riconciliazione_completa.py` → chiamato da `app/routers/email_download.py:729`
- `app/services/riconciliazione_smart.py` → chiamato da `app/routers/operazioni_module/smart.py:61,73`
- `app/services/riconciliazione_intelligente.py` → montato con prefix `/api/riconciliazione-intelligente`

Nessuno dei tre è codice morto (hanno chiamanti reali raggiungibili), quindi non sono stati
toccati in questo passaggio — ma la sovrapposizione concettuale con
`riconciliazione_bancaria.py` va chiarita in una review dedicata: potrebbero essere sistemi
con scopi genuinamente distinti (smart = match manuale singolo movimento, completa = batch
periodico via email, intelligente = API dedicata) oppure ulteriore duplicazione di logica
da consolidare.

## Bug/incoerenze note (da correggere)

- Il motore prende il primo match entro tolleranza in più punti (stesso pattern del bug
  F24 documentato in `F24.md`) invece di segnalare esplicitamente l'ambiguità quando ci sono
  più candidati equivalenti.
- I 6 alert `RIC_*` completamente inerti sono la lacuna più a basso sforzo da colmare
  (funzioni di generazione alert già esistenti altrove nel codice come pattern da replicare).

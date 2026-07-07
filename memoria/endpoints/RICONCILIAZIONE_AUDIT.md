# Audit riconciliazione — mappa completa prima dell'unificazione

Richiesto dall'utente dopo la scoperta che i "4 gruppi" segnalati inizialmente
(`/api/riconciliazione`, `/api/riconciliazione-auto`, `/api/riconciliazione-intelligente`,
`/api/operazioni-da-confermare`) non erano l'intero quadro: durante l'audit sono emersi
**altri 4 sistemi** con nomi/scopi sovrapposti, per un totale di **8**. Nessuno di questi
è un semplice "shadowing" di route come nel caso già risolto di `/api/invoices`/`/api/fatture`
(dove un file vinceva sull'altro per ordine di registrazione): qui sono 8 implementazioni
distinte, spesso tutte vive contemporaneamente, con **modelli di stato diversi e non
sincronizzati** sulla stessa collezione `invoices`. Ogni sezione è stata prodotta leggendo
per intero i file elencati, con verifica incrociata contro i chiamanti reali (frontend,
scheduler, event bus, altri moduli Python) — non solo i docstring.

## 🔴 Bug critico confermato con test HTTP reale (azione consigliata: fix immediato)

**`POST /api/operazioni-da-confermare/smart/riconcilia-manuale` fallisce SEMPRE con 422.**

Questo è il bottone "conferma"/"Auto-Ripara" della pagina **realmente usata in produzione
oggi**, `frontend/src/pages/RiconciliazioneUnificata.jsx`. Il frontend invia:
```js
{ movimento_id, tipo, associazioni: [...], categoria }
```
Il backend (`app/routers/operazioni_module/common.py::RiconciliaManuale`) richiede invece
campi obbligatori diversi:
```python
class RiconciliaManuale(BaseModel):
    movimento_id: str
    tipo_operazione: str   # mai inviato dal frontend
    entita_id: str          # mai inviato dal frontend
    note: Optional[str] = None
```
Verificato con un test HTTP reale (mongomock + TestClient, payload identico a quello
inviato dal browser): **422 Unprocessable Entity**, `tipo_operazione` e `entita_id`
mancanti. Significa che oggi, in produzione, ogni click su "conferma singolo movimento"
o "Auto-Ripara" nella pagina di riconciliazione fallisce silenziosamente (il frontend
cattura l'errore con un `alert`/`console.error` e basta) — **la UI di riconciliazione
principale non concilia mai nulla**, a prescindere da quale dei sistemi sottostanti sia
"giusto".

Non è collegato alla domanda più ampia di unificazione (vale a dire: va sistemato subito,
indipendentemente da quale sistema diventerà canonico) — vedi raccomandazione in fondo.

## Mappa degli 8 sistemi

| # | Sistema | Prefix / file | Vivo? | Campo di stato primario | Collezione target |
|---|---|---|---|---|---|
| 1 | Email↔documenti | `email_reconciliation.py` (+ service) | **No** — 8/8 route morte (nessun chiamante ovunque) | `pdf_allegati`/`email_associata` su doc originali | `indice_documenti` (già segnata deprecata in `db_collections.py`) |
| 2 | Riconciliazione stats | `riconciliazione_stats_api.py` | Sì (1 endpoint, chiamato da `DashboardRelazionale.jsx`) | — (sola lettura) | `riconciliazioni_match` |
| 3 | Riconciliazione automatica EC | `accounting/riconciliazione_automatica.py` | **Parzialmente**: la funzione `riconcilia_estratto_conto()` è viva (scheduler ogni 30 min + upload EC); le sue 6 route HTTP sono morte | `invoices.pagato/paid/stato_pagamento/in_banca`, `estratto_conto_movimenti.riconciliato` | `invoices`, `estratto_conto_movimenti`, `operazioni_da_confermare`, `f24_unificato`, `assegni` |
| 4 | Riconciliazione intelligente | `riconciliazione_intelligente_api.py` (+ service, 25 endpoint) | **No** — l'unico endpoint con un chiamante frontend (`conferma-multipla`) fallisce sempre per mismatch di payload (`operazioni` inviato vs `fatture` atteso); le altre 24 route non hanno alcun chiamante | `invoices.stato_riconciliazione` (macchina a stati ricca, 17 valori enum) | `invoices`, `prima_nota_*`, `scadenziario_fornitori`, `assegni`, `abbuoni_arrotondamenti`, `pagamenti_anticipati` |
| 5 | Operazioni da confermare (smart) | `operazioni_module/smart.py` | **Sì** — è il motore reale dietro `RiconciliazioneUnificata.jsx` (analizza/banca-veloce/cerca-*), ma il suo endpoint di conferma è rotto (bug sopra) | `invoices.pagato/paid/stato_pagamento/status` (flag piatti, via `set_fattura_pagata()`) | `estratto_conto_movimenti`, `invoices`, `f24_commercialista`*, `prima_nota_salari` |
| 6 | Operazioni da confermare (carta) | `operazioni_module/carta.py` | **No** — zero chiamanti frontend (dominio carta di credito, mai wired in UI) | stesso schema di #5 ma su `transazioni_carta` | `transazioni_carta`, `invoices` |
| 7 | Bonifici (archivio) | `bonifici_module/` | **Sì** (pagina `ArchivioBonifici.jsx`), ma con un bug bloccante interno (ObjectId vs UUID) che rompe 4 dei suoi endpoint di associazione | dominio separato (bonifico↔movimento, non fattura↔movimento) | `bonifici_transfers` (attiva) vs `archivio_bonifici` (legacy, popolata da un flusso diverso — le due non si parlano) |
| 8 | Riconciliazione via event bus | `services/riconciliazione_engine.py` + `services/handlers/banca_handlers.py` | **Sì** — si attiva automaticamente ad ogni import di estratto conto (evento `MOVIMENTO_BANCA_IMPORTATO`), applica match ≥0.90 score senza intervento umano | proprio scoring + `riconciliazioni_match`, ma scrive anche su `invoices`/F24/cedolini/POS via `documento_collection` generico | `partite_aperte`, `riconciliazioni_match`, `invoices`, F24, cedolini |

\* `f24_commercialista` non è nemmeno una costante coerente: lo stesso dominio F24 è raggiunto
con **tre nomi diversi hardcoded** in punti diversi dello stesso sistema #5
(`f24_commercialista` in smart.py, `f24` nel ramo non-cache di riconciliazione_smart.py,
`f24_models` nel ramo batch realmente usato in produzione) — nessuno dei tre è la collezione
canonica dichiarata in `db_collections.py` (`f24_unificato`).

## Perché non è un caso di "shadowing" come /api/invoices o /api/fatture

Nei consolidamenti precedenti, un solo file vinceva sempre per ordine di registrazione e
l'altro era morto al 100%: cancellare il perdente era sicuro. Qui:

- **Nessun URL è duplicato** — ogni prefix è unico, non c'è una "route vincente/perdente".
- **Più sistemi sono vivi contemporaneamente** e scrivono sulla stessa collezione
  (`invoices`) con **campi di stato diversi**: `pagato/paid/stato_pagamento/status` (sistemi
  3, 5, 6) vs `stato_riconciliazione` (sistema 4) vs scoring proprio (sistema 8).
- **Una fattura confermata da un sistema non è visibile come "risolta" da un altro**: es.
  confermata via `operazioni_module` (sistema 5) → `pagato=True`, ma `stato_riconciliazione`
  resta `"in_attesa_conferma"` per sempre → il sistema 4 (`riconciliazione_intelligente`,
  se mai venisse ri-attivato) continuerebbe a proporla come "da confermare".
- **Il sistema #8 (event bus) agisce in automatico e silenzioso** ad ogni upload di estratto
  conto, in parallelo al motore schedulato del sistema #3 e a quello del sistema #5/#4 —
  quattro motori di matching indipendenti possono agire sullo stesso movimento bancario
  senza coordinamento/lock esplicito tra loro.

Unificare qui significa scegliere **UN campo di stato canonico** e **UN solo motore di
matching attivo**, poi migrare gli altri sette a scrivere/leggere quello — non "cancellare
il duplicato morto" come nei due consolidamenti precedenti.

## Bug e incoerenze per gravità (in aggiunta al 🔴 sopra)

### Bloccanti/rompono funzionalità dichiarata
- `correggi-metodi-pagamento` (sistema 3): KeyError certo, legge `_id` da un documento con
  projection che lo esclude — la bonifica non corregge mai nulla.
- `GET /smart/movimento/{id}` (sistema 5): `ImportError` non gestito, importa una funzione
  inesistente (`analizza_singolo_movimento`).
- `associa-salario`/`disassocia-salario`/`fatture-compatibili`/`operazioni-salari`
  (sistema 7): `ObjectId()` su id UUID → 400/eccezione silenziosa per tutti i bonifici del
  flusso attivo (`bonifici_transfers`).
- Ramo "fattura_sdd" (sistema 5): tipo prodotto dall'analizzatore ma non gestito dal
  confermatore — una fattura riconosciuta come SDD non viene mai saldata, resta
  indefinitamente "non pagata" nel resto del gestionale anche se il movimento viene marcato
  riconciliato.

### Incoerenze di stato cross-sistema
- Sistema 5 non scrive mai `riconciliato=True` su F24/stipendi collegati (solo l'id sul
  movimento bancario) — un F24/stipendio "confermato" ricompare nelle ricerche successive.
- Sistema 4: `pagamento-parziale`/`nota-credito` non toccano mai `pagato`/`riconciliato` —
  incoerente anche internamente al sistema, non solo fra sistemi diversi.
- Sistema 4: stato enum `PAGAMENTO_CUMULATIVO` definito ma mai assegnato in 2115 righe.
- Sistema 8 e sistema 4 possono agire sullo stesso movimento/fattura da percorsi diversi
  (uno via evento automatico, l'altro via endpoint esplicito mai realmente chiamato) senza
  lock — rischio di doppia scrittura concorrente, oggi mitigato solo dal fatto che il
  sistema 4 non riceve traffico funzionante.
- Tolleranze di matching diverse e non motivate tra sistemi analoghi: ±1% (banca, sistema
  5), ±2% (carta, sistema 5/6), ±5% (ricerca manuale, sistema 5), ±0.05€ (sistema 3),
  score-based con soglie 10/15 (sistema 3).

### Codice morto sicuro da rimuovere (verificato zero chiamanti ovunque)
- Sistema 1 (email_reconciliation.py): tutti gli 8 endpoint + il service dedicato —
  **non** toccare `riconciliazione_stats_api.py`, che condivide solo il prefix URL ma è un
  file indipendente e vivo.
- Sistema 3: le 6 route HTTP (mantenendo la funzione `riconcilia_estratto_conto()` per
  scheduler/upload EC).
- Sistema 4: tutte le 25 route (nessuna riceve traffico funzionante, inclusa quella con un
  chiamante nominale).
- Sistema 6 (`operazioni_module/carta.py`): tutti gli endpoint (zero chiamanti frontend);
  MA la logica di match fatture andrebbe eventualmente recuperata come funzione condivisa
  con il sistema 5, non buttata (è quasi identica, solo tolleranza diversa).
- `riconciliazione_engine.py::stats_riconciliazione()`: mai chiamata, duplicata
  identicamente da `riconciliazione_stats_api.py`.

## Proposta di stato canonico (per la fase "unifica")

1. **Un solo campo booleano/stringa su `invoices` come fonte di verità**: `pagato` (bool) +
   `stato_pagamento` (stringa: `non_pagata|provvisoria|pagata|parzialmente_pagata`) — lo
   schema già usato dal sistema 5 (`set_fattura_pagata()`), perché è quello letto da tutto
   il resto del gestionale (dashboard, scadenzario, bilanci) verificato nell'audit
   precedente (`memoria/endpoints/README.md`, anomalia #20). `stato_riconciliazione`
   (sistema 4) andrebbe deprecato o mappato in sola lettura su questi due campi.
2. **Un solo motore di matching attivo per l'estratto conto**: il sistema 3
   (`riconcilia_estratto_conto`, già schedulato+testato in produzione da mesi) o il sistema
   8 (event bus, già live e automatico) — non entrambi. Vanno confrontati side-by-side su
   un campione reale prima di scegliere quale disattivare, perché entrambi sono vivi oggi.
3. **Un solo endpoint di conferma manuale**, con contratto allineato al frontend reale
   (fix del bug 🔴 sopra), che scrive sui campi canonici del punto 1 E propaga
   correttamente a F24/stipendi (gap oggi presente nel sistema 5).
4. **Mantenere separati** (non sono duplicati, sono domini diversi): sistema 1 (email↔PDF,
   da rimuovere per obsolescenza, non da unificare), sistema 7 (bonifici↔movimento, da
   riparare il bug ObjectId/UUID ma resta un dominio a sé).
5. **Portare la ricchezza del sistema 4** (pagamento parziale, nota di credito, bonifico
   cumulativo, sconto cassa, assegni multipli, arrotondamento, acconto) dentro il motore
   canonico scelto al punto 3, come funzioni richiamabili — è l'unica parte di quel sistema
   che vale la pena salvare, il resto (25 endpoint quasi tutti isolati) va scartato.

## Come usare questo file

Prima di scrivere qualunque codice di unificazione: rileggere la tabella "Mappa degli 8
sistemi" per sapere esattamente cosa ogni sistema scrive/legge, poi la sezione "Proposta di
stato canonico" come base di discussione — non è una decisione presa, richiede conferma
esplicita dell'utente data la portata (tocca saldi banca/cassa, bilanci, stipendi, F24).

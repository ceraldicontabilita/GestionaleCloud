# PROMPT INIZIALE — GestionaleCloud (Ceraldi ERP)

Incolla questo prompt all'inizio di ogni nuova chat su questo repo. In alternativa: "Leggi memoria/PROMPT_SESSIONE.md e memoria/LOGICA_OPERATIVA.md prima di iniziare."

---

Lavori sul repo **ceraldicontabilita/GestionaleCloud**: ERP interno di Ceraldi Group SRL (ristorazione, Napoli), in produzione su **https://impresasemplice.online** (Render). Utente non tecnico: rispondi SEMPRE in italiano, spiega cosa hai trovato e cosa hai corretto in termini operativi, non tecnici.

## Stack e workflow di deploy

- **Backend**: FastAPI + Motor (MongoDB Atlas M0). Entry: `app/main.py`; TUTTI i router registrati in `app/router_registry.py` (unica fonte per prefissi/route reali).
- **Frontend**: React 18 + Vite in `frontend/`. **`frontend/dist` è committato**: Render serve lo static SENZA build step → ogni modifica frontend richiede `cd frontend && npm run build` PRIMA del commit, e `dist/` va incluso nel commit.
- **Deploy**: commit+push sul branch di lavoro, poi `git checkout main && git merge --ff-only <branch> && git push origin main` (Render deploya da main), poi torna sul branch. Mai amend/force-push.
- **Test**: `.venv/bin/python -m pytest tests/ -q` (≈90 test, mongomock). Per verifiche visive mobile: skill `run-gestionale` (mock backend + screenshot Chromium).
- **VINCOLO SANDBOX**: nessun accesso di rete al MongoDB di produzione (raw TCP bloccato by design). Script che toccano dati reali li esegue L'UTENTE dalla Shell di Render. Non aggirare MAI questo limite (in particolare: mai indebolire auth/middleware di produzione per farlo).

## Regole di business NON negoziabili

1. **Il metodo fornitore comanda**: il metodo di pagamento si legge SOLO da `fornitori.metodo_pagamento`, MAI dall'XML fattura. Classificatore canonico: `classifica_metodo_fornitore()` in `app/routers/prima_nota_module/sync.py` → cassa/contanti→**Cassa**; bonifico/banca/riba/sepa/rid/sdd/assegno→**Banca**; tutto il resto (paypal, carta, misto, vuoto)→**resta Provvisoria**. "misto" È un metodo valido scelto dall'utente, non "senza metodo".
2. **Doppio schema campi `invoices`** (inglese/italiano): coalesce SEMPRE entrambi — `total_amount|importo_totale`, `invoice_number|numero_fattura|numero_documento`, `supplier_vat|cedente_piva|fornitore_partita_iva`, `invoice_date|data_fattura|data_documento`, `status|stato`. Importi legacy possono essere stringhe con virgola ("254,50") → usa `app/utils/parsing.safe_float`, mai `float()` nudo.
3. **Fattura pagata** = campi canonici `pagato:true`, `paid:true`, `stato_pagamento:"pagata"` (helper: `QUERY_FATTURA_NON_PAGATA` / `set_fattura_pagata()` in `app/routers/operazioni_module/common.py`). Mai inventare campi nuovi tipo "pagata".
4. **Atlas condiviso con app sorelle**: Lotti/HACCP (ceraldiapp.it) e AppDipendenti (appdipendenti.onrender.com) usano lo STESSO cluster. Mai toccare/rinominare/eliminare collezioni non del gestionale. HACCP e HR sono stati ELIMINATI dal gestionale (vivono solo nelle app sorelle, linkate come esterni nel menu).
5. **Assegni** (modello a quote N:M, documentato in `memoria/LOGICA_OPERATIVA.md` §Assegni): `assegni.fatture_collegate = [{fattura_id, quota, data_collegamento}]`, max 4 fatture per assegno, stesso fornitore, somma quote ≤ importo assegno (importo nominale MAI modificato dal collegamento). Endpoint canonico manuale: `PUT /api/assegni/{id}/fatture-collegate`; auto-matcher a 4 livelli in `app/routers/bank/assegni_auto_match.py` (tolleranza ±0,005€). Questo schema è L'UNICO valido: non scrivere `fatture_collegate` in altri formati.
6. **PayPal**: sync da API Transaction Search (`app/services/paypal_api_sync.py` → collezione `paypal_transactions`); `paypal_account_id` = account della CONTROPARTE (fonte affidabile per mappare fornitori: campo `fornitori.paypal_account_id`); `invoice_id` PayPal = id abbonamento, NON univoco per addebito (due addebiti mensili possono condividerlo: non sono duplicati). Solo importi in uscita (`importo < 0`) sono candidati al mapping fornitori.

## Collezioni MongoDB (canoniche vs legacy)

| Canonica | Note / legacy da NON usare |
|---|---|
| `fornitori` | `suppliers` legacy. P.IVA anche in `piva`/`vat_number` |
| `invoices` (passive), `invoices_emesse` (attive) | `fatture` NON esiste |
| `prima_nota_cassa`, `prima_nota_banca` | `prima_nota` legacy (3 doc morti) |
| `estratto_conto_movimenti` | `estratto_conto`, `movimenti_bancari`, `prima_nota_provvisori` = morte (script archiviazione: `app/scripts/archivia_collection_morte.py`, esegue l'utente da Render) |
| `assegni` | schema a quote, vedi regola 5 |
| `paypal_transactions`, `paypal_statements` | |
| `f24_unificato` + `f24_commercialista` | DUE archivi F24 paralleli (duplicazione nota, non risolta): ogni lettura F24 deve unire entrambi |
| `corrispettivi`, `employees`, `cedolini`, `verbali_noleggio`, `warehouse_products`, `documenti_non_associati`, `alerts`, `audit_log`, `todo`, `users` | |

Costanti nomi collezione: `app/db_collections.py` e classe `Collections` in `app/database.py`.

## Router principali (prefissi da `app/router_registry.py`)

- `/api/suppliers` → `app/routers/suppliers_module/` (base.py: lista+stats con aggregation su invoices)
- `/api/fatture` → `app/routers/invoices/fatture_upload.py` = **UNICO** punto di import XML/P7M (il "CUORE": parsing, fornitore, prima nota per metodo). Non esistono più pipeline parallele di import.
- `/api/prima-nota*` → `app/routers/prima_nota_module/` (sync.py: provvisori + auto-conferma per metodo fornitore)
- `/api/assegni` → `app/routers/bank/assegni.py` + `assegni_auto_match.py`
- `/api/paypal-statements`, `/api/paypal-api` → paypal_statements.py, paypal_api.py
- `/api/operazioni-da-confermare` → `operazioni_module/` (riconciliazione smart/carta)
- `/api/riconciliazione*` → `accounting/riconciliazione_automatica.py`; piano conti in `accounting/piano_conti.py`
- `/api/f24*`, `/api/documenti*`, `/api/openapi-imprese` (visure Camera di Commercio), `/api/todo`, `/api/alerts`

## Frontend — struttura e regole

- Route: `frontend/src/main.jsx`. Menu desktop: `components/layout/TopNav.jsx` (NAV_ITEMS + ALTRO_ITEMS). Menu mobile: `App.jsx` → `ALL_NAV_ITEMS` — **lista separata mantenuta a mano: ogni voce aggiunta al desktop VA aggiunta anche qui**, altrimenti sparisce da telefono.
- Design system: token in `frontend/src/styles/ds/` (navy `#0f2744` + oro `#b8860b`), componenti in `frontend/src/components/ds/` (PageHeader, StatCard, Card, Button…). `PageLayout` (components/PageLayout.jsx) accetta title/icon/subtitle/actions e rende l'header; `PageGrid` è responsive (auto-fit).
- **Il body ha `overflow-x: hidden` globale**: una tabella larga senza wrapper non scrolla, viene TAGLIATA in silenzio. Ogni `<table>` va dentro `<div style={{overflowX:'auto'}}>`. Tutte le pagine devono funzionare su PC, tablet e smartphone.
- Errori mai silenziati: niente `.catch(()=>{})` che maschera un 500 come pagina vuota; mostrare banner di errore con "Riprova".

## Pattern storico di bug (il primo sospetto da verificare)

Questa app è cresciuta per accumulo: **la stessa azione reale ha spesso 2-6 implementazioni parallele** con schemi dati diversi (es. import fatture, 6 meccanismi di auto-associazione assegni, doppio archivio F24, campi flat vs strutturati). Quando trovi un bug di "dati che non compaiono/non combaciano", cerca PRIMA un secondo scrittore con schema diverso, e la correzione giusta è **consolidare sulla fonte canonica ed eliminare la variante**, non aggiungere l'ennesima. Elimina sempre il codice morto che trovi lungo la strada.

## Documentazione interna (leggila prima di toccare la logica)

- `memoria/LOGICA_OPERATIVA.md` — **fonte di verità** della logica di business (assegni a quote, riconciliazione, F24, casi A-F…)
- `memoria/INDEX.md`, `memoria/BACKLOG.md` — stato e decisioni
- `CLAUDE.md` — rispondi sempre in italiano

## Come lavorare

1. Riproduci/individua la causa esatta (file:riga) prima di correggere; non applicare patch cosmetiche.
2. Correggi sulla fonte canonica; elimina duplicati/codice morto correlato.
3. Verifica: sintassi Python, `pytest tests/ -q`, `npm run build`, e quando ha senso un test mirato con mongomock.
4. Commit con messaggio in italiano che spiega la CAUSA (non solo il fix), push sul branch, fast-forward su main.
5. Se un intervento richiede dati di produzione: prepara lo script + dry-run e chiedi all'utente di eseguirlo da Render Shell.

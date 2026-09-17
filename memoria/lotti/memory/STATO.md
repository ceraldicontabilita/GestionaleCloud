# STATO DEL PROGETTO — Lotti HACCP (Ceraldi Group)
> Documento di contesto persistente. Va aggiornato a ogni modifica strutturale.
> Qualunque sessione di lavoro (chat nuova, sviluppatore nuovo) parte da qui.

## Infrastruttura
- **Repo**: `ceraldicontabilita/Lotti` (monorepo: `backend/` FastAPI + `frontend/` React CRA)
- **Backend live**: https://lotti-backend-2wwb.onrender.com (prefisso `/api`)
- **Frontend live**: https://www.ceraldiapp.it (dominio ufficiale dal
  02/07/2026 — Enzo ha collegato ceraldiapp.it; il vecchio
  lotti-frontend.onrender.com è stato SPENTO da Render: risponde 404
  "blocked-render-subdomain". CORS backend aggiornato in server.py+render.yaml
  con unione hardcoded. OGNI risposta operativa a Enzo termina con
  https://www.ceraldiapp.it)
- **DB**: MongoDB Atlas, `DB_NAME=Gestionale` (cluster condiviso con le altre app Ceraldi)
- **Deploy**: automatico sul push a `main` (~5–8 min). Render free tier: cold start ~50s, CPU limitata (richieste parallele pesanti la saturano).
- Pagina Ordini = file statico `frontend/public/ordini-app.html`, servito dal frontend, mostrato in iframe (tab "ordini" e tablet).

## Sistemi UNIFICATI (regola: una sola implementazione per funzione)
1. **Lotti** — collezione unica `db.lotti` per TUTTO: produzioni, lotti fornitori,
   **gelati** (numero `GEL-…`, creati da POST /gelati/produzioni), **pesce**
   (`PESR-…` ricevimento, `PES-…` abbattimento, endpoints `/lotti/ricevimento-pesce`,
   `/lotti/abbattimento-pesce`, `…/concludi` con regola 24h Reg. 853/2004).
   Ricerca/richiami: `GET /lotti/cerca-universale` (cerca anche dentro i lotti
   fornitori scalati — tracciabilità ASL). Archivio: `POST /lotti/archivia-scaduti`.
2. **Ordini** — collezione unica `ordini_fornitori`. Flusso DEFINITIVO:
   `bozza → confermato (non inviato) → inviato_fornitori`. MAI invii automatici.
   Conferma per riga (`PUT /{id}/conferma-righe`), invio delle sole righe
   confermate con bozza residua (`POST /{id}/invia`). Azioni di revisione
   protette da header `X-Admin-Pin` (PIN amministratore, validato su
   `tablet_operatori`, ruolo amministratore). Carrello titolare: tab
   "Da inviare" in ordini-app.html (PIN in sessionStorage).
   Riordini automatici (`genera-riordini`) creano BOZZE qui, una per fornitore.
3. **Ricerca prodotti** — motore unico per radici: `stems_ricerca()` in
   `backend/routers/utils.py` (singolare/plurale: margarina↔margarine).
   Usato da: food-cost/dizionario/search, prodotti-master/cerca; lato client
   `matchQ` in ordini-app.html. Il canonico resta `ingredienti.py`
   (L1 mapping → L2 keyword → L3 LLM; `normalizza-batch`).
4. **Email** — un solo ponte: `_invia_relay` in `backend/routers/email_ordini.py`
   (Google Apps Script relay, SMTP diretto bloccato su Render; BCC alla Gmail
   aziendale). Il listino lo importa da lì. Email fornitori: prima
   `fornitori_anagrafica.email`, poi rubrica legacy.
5. **Digest 07:30** — `backend/routers/digest.py`, job `digest_mattutino`
   (scheduler). Conta: lotti scaduti/in scadenza + bozze/confermati da inviare.
   Invio WhatsApp via gateway OpenWA-compatibile (env WHATSAPP_API_URL/API_KEY/
   SESSION/TO — finché mancano risponde "non configurato" senza errori).

## Convenzioni operative (NON violarle)
- **PORTA SU MAIN SEMPRE** (direttiva Enzo 03/07/2026, permanente): ogni
  lavoro completato e verificato (build backend+frontend, test puri) va
  mergiato su `main` SUBITO, senza chiedere conferma ogni volta — il
  deploy Render parte dal push su main. Restano obbligatorie le
  verifiche pre-merge; se qualcosa non è verificato, dichiararlo.
- Niente duplicati/codice morto/sistemi paralleli. Quando si sostituisce, si elimina il vecchio.
- Verificare i dati reali (curl) prima di dichiarare che qualcosa funziona. Mai inventare valori.
- Mai inventare allergeni o shelf-life: usare il motore `_calcola_scadenza`/shelf_life.
- Ogni risposta a Enzo su lavori Lotti termina con il link del frontend.
- Shell del sandbox = `sh` (niente brace expansion); clone SEMPRE fresco prima di
  editare file condivisi (server.py/scheduler.py); commit via GitHub Git Data API;
  validazione: `py_compile` (backend), build CRA `CI=false` (frontend).
- Render NON pubblica lo stato deploy su GitHub: verificare interrogando gli endpoint.
- OGNI modifica visiva va verificata GUARDANDO la pagina renderizzata: browser headless
  (playwright-core + chromium headless shell in /opt/pw-browsers), viewport 412x915 mobile,
  screenshot e ispezione visiva PRIMA di dichiarare il lavoro fatto. Gli audit a livello
  API non vedono i bug di rendering (es. font-boosting) né i puntamenti sbagliati che
  rispondono 200 (es. API = frontend statico invece del backend).
- Auth: `backend/auth.py` (JWT + Google Sign-In) — dormiente finché
  `AUTH_ENFORCE=true`. PIN operatori 4 cifre, admin 6 cifre.

6. **Stock bar** — UNICA funzione che tocca lo stock: `applica_movimento_stock`
   in `magazzino_bar.py`. La usano: /magazzino-bar/carico, /magazzino-bar/scarico,
   /magazzino/scarico (ramo bar, delega), carico-da-fattura (fatture.py), richieste
   rifornimento (OK preso). Lavagna rifornimenti: `magazzino_bar_richieste`
   (bar chiede → tablet magazzino mostra con polling 12s → OK = scarico automatico).
7. **Decisioni "NON doppioni"** (verificate, restano separati): Listino = prezzi di
   VENDITA (sconti/IVA clienti) vs prodotti-master = prezzi d'ACQUISTO;
   scarico fornitori (lotti_fornitori) in magazzino_unificato
   = dominio lotti, non bar; scorta_minima (dizionario) vs soglia_minima (bar).
8. **Ricette = solo gestione** (lista, ingredienti, allergeni, Clona). Si produce
   SOLO dalle card tablet Pasticceria/Rosticceria (filtrate per reparto).

9. **Tablet UNIFORME** (7497815): stesso header navy→viola per i 3 reparti; via
   bottoni Ordini e Produzione (ProduzioneMattina e ModalOrdiniPassticcere ELIMINATI);
   cataloghi Acquaviva/Alpha/Colazione = pulsantini bianchi nella riga comandi;
   griglia = solo prodotti del reparto.
10. **Verifica bundle live**: mai usare emoji come marcatori (le librerie ne
   contengono); usare nomi di componenti/stringhe plain (es. "ProduzioneMattina").

## In attesa (lato Enzo)
- Email mancanti dei fornitori a cui si ordina (19/201 presenti in anagrafica).
- Env WhatsApp (gateway OpenWA su macchina sempre accesa, numero dedicato — ToS!).
- ~~`AUTH_ENFORCE=true`~~ GIA' ATTIVO su Render (verificato 14/06: `/api/ricette` senza
  token = 401, `/api/health` = 200). Conseguenza: ogni GET/PUT verso il backend DEVE
  passare per axios (interceptor col token); MAI `window.open` su endpoint API (la tab
  nuova non eredita il JWT -> 401). Restano lato Enzo solo `AUTH_SECRET`/`CORS_ORIGINS`
  se non ancora impostati come da preferenza.
- Brochure/fattura Galatea per i prodotti gelato reali.

## Code di lavoro note
- ~113 voci dizionario senza nome canonico (per lo più non-ingredienti; blocchi
  LLM con `normalizza-batch?usa_llm=true&solo_mancanti=true` li riducono).
- `scorta_minima` (dizionario, kg) e `soglia_minima` (magazzino bar, pezzi):
  domini DIVERSI, decisione presa: restano separati.


## Alert supervisore navigabili (pattern, giu 2026)
Ogni alert del supervisore che enumera dei colpevoli DEVE portare `items` ([{id, nome}], max 60)
ed eventualmente `items_tab`. Il modale li espande; il tocco su una voce salva in sessionStorage
`supervisore_apri` {id, tab} e naviga su `route`; la pagina di destinazione che sa aprire il
dettaglio consuma il biglietto (oggi: ricette in SchedaProdottoView). Alert con items: A1 ricette
senza allergeni, A2 fornitori da qualificare, A3 lotti scaduti (NIENTE soglia tollerata: scatta da 1),
A6 anomalie senza azione, A7/A7b libretti (route personale, non registro_haccp), ORD ordini in bozza.
Quando si crea un NUOVO alert, nasce già con items se i colpevoli sono enumerabili.

## REGOLA META (Enzo, 12/06/2026 — permanente)
Claude deve TROVARE le anomalie in autonomia, come farebbe Enzo, e PROPORRE le soluzioni —
non aspettare che gliele segnali lui. Ogni intervento va pensato per l'intera catena di passaggi
(chi scrive → chi legge → chi naviga → chi corregge → chi verifica), senza perdere pezzi per strada.
A fine lavoro: passare il pettine sull'area toccata e riportare le anomalie trovate con proposta.

## Pagina Ordini — NATIVA (giu 2026)
- La tab #ordini NON e' piu' un iframe: ordini-app.html e ordini-manifest.json ELIMINATI.
- Componente: frontend/src/components/haccp/OrdiniView.jsx (4 schede: Catalogo, Carrello, Giacenze, Da inviare).
- Auth: axios + interceptor (token JWT automatico). Revisione ordini: _richiedi_admin accetta JWT ruolo=amministratore (X-Admin-Pin resta fallback tablet).
- Flusso invariato e definitivo: bozza -> confermato -> inviato, collection ordini_fornitori, conferma righe selettiva.

## Classificatore alimenti UNICO (giu 2026)
- `backend/routers/classificatore_alimenti.py` = UNICA fonte per servizio/non-food/alimento
  (e_servizio, e_alimento, e_merce_alimentare). Le 3 regex locali precedenti
  (fatture._NON_MERCE_RE, magazzino_bar._NON_MERCE, magazzino_unificato._HARD_NONFOOD) ELIMINATE.
- Applicato in: carico bar da fattura (rubinetto), pulizia-non-merce, listino (sync con
  pruning + GET), ordini-app/giacenze (filtro in lettura), gestione-prodotti.
- Regola Enzo: non-alimentari (candeggina, diluente, cavi, monitor, Maxima...) MAI visibili
  nelle viste prodotti; restano in fatture/movimenti per statistica.
- Gelati invenduti: gusto da TENDINA (GET /gelati/gusti = seed app + storico self-feeding,
  opzione "Altro gusto" per scrivere una volta sola).


## Ristrutturazione 13/06/2026 (richiesta Enzo: "risolvi tutto")
- **Fase 1 demolizione**: routers/produzione.py e produzione_mattina.py ELIMINATI
  (zero chiamate frontend, zero import). ordini_app.py ridotto a /giacenze:
  via 20+ endpoint del vecchio iframe, incluso /carico che scriveva lo stock
  bypassando applica_movimento_stock (buco chiuso per rimozione).
- **Fase 2 bus eventi**: backend/eventi.py (publish/subscribe, handler protetti).
  Eventi pubblicati: FATTURA_IMPORTATA (fine import XML), STOCK_MOVIMENTATO
  (dentro applica_movimento_stock), ORDINE_INVIATO, PRODUZIONE_REGISTRATA.
  Handler: log su db.log_eventi + invalidazione cache cruscotto.
  registra_handlers() allo startup in server.py. PROSSIMO PASSO: migrare le
  scritture multiple (lotti: 6 scrittori residui, ricette: 7) in servizi unici.
- **Fase 3 percezione velocita'**: cache 60s cruscotto (invalidata dal bus),
  cache 120s gestione-prodotti, rendering incrementale 120+200 in
  GestioneProdottiView, header onesto ("Carico l'elenco..." invece di "0 su 0").
- **Auth riprogettata** (bug visti da Enzo: dentro senza PIN a backend freddo,
  poi PIN richiesto 3 volte): config auth con MEMORIA in localStorage
  (lotti_auth_cfg) + retry, validateToken con grazia di rete (null=rete giu',
  non bocciatura), LoginGate controlla UNA volta a sessione
  (sessionStorage lotti_gate_ok), NIENTE ricontrollo su hashchange; riapre solo
  su lotti-auth-changed (vero 401 dall'interceptor).
- **Classificatore**: e_merce_alimentare ora PERMISSIVO (nasconde solo il
  positivamente non-food; Ferrarelle/Red Bull/marchi senza parola-cibo restano).
  e_alimento resta STRETTO per la curatela. prodotti_master (catalogo Ordini)
  delega al classificatore unico + filtro in lettura su lista().
- **Supervisore senza rumore**: alert prezzi filtrati (niente servizi tipo
  "Spese di Trasporto") e dedup per titolo; "doppio acquisto" ora scatta SOLO
  per stesso prodotto+fornitore+GIORNO (comprare uova 40 volte/mese e' normale).
- **Dashboard Aggiorna**: spinner+disabled+toast, timeout cruscotto 45s.
- DOPO OGNI DEPLOY ricordare a Enzo di RICARICARE la pagina (il browser tiene
  il bundle vecchio: la tendina gusti c'era gia' ma lui vedeva il JS cached).

## Fase 2 — servizio lotti unico (13/06/2026, sessione "Continua")
- `backend/servizi/lotti_service.py` = UNICO punto di creazione lotto: crea_lotto(doc, origine).
  I 5 insert diretti su db.lotti (lotti.py ×3, lotti_produzione.py ×2, gelati.py)
  ora delegano. ZERO db.lotti.insert_one nei router.
- crea_lotto normalizza i campi canonici (numero_lotto, prodotto, stato/esaurito
  coerenti) senza rompere i campi specifici, e pubblica UN evento LOTTO_CREATO.
- Bus: handler LOTTO_CREATO (log su log_eventi + invalidazione cache cruscotto).
- NON toccati i writer di db.ricette (food_cost, utils, ecc.): sono update
  field-specific del loro dominio (food cost, nutrizionale, import) — centralizzarli
  sarebbe rischio senza valore. Decisione esplicita, non dimenticanza.

## Sessione 15/06/2026 — sezione Listini (genera & esporta) + listino bar PDF
- **Listino bar PDF** (birre/amari/alcolici-superalcolici): estratto dal registro
  magazzino bar, pulito da non-bevande e mixer analcolici, prezzo = ultimo
  acquisto da fattura + data, sconto applicabile. Scoperta: classificazione
  listino/bar inquinata (candeggina/punte trapano in LIQUORI) — gestita con
  allowlist parole-bevanda.
- **Sezione "Genera & Esporta" dentro Listino prezzi** (no doppioni: niente
  pagina nuova sotto Ordini/Magazzino). Backend: `GET /listino/calcola` e
  `/listino/calcola-pdf` (helper `_calcola_righe`) — modo best/media/ultimo,
  filtro fornitore|categoria|prodotto, sconto 0/3/5/7/10, birre alcoliche/
  analcoliche (derivate per parola: 0,0/analcolic/tourtel/forst 0). Prezzo
  preso COSÌ COM'È in fattura (cassa/pezzo come registrato). `/listino/
  fornitori-elenco` = distinct fatture.fornitore (221). Frontend: 3° sotto-tab
  in ListinoView con selettori + tabella + Scarica PDF (axios blob, auth via
  interceptor). Motore validato live: 2997 prodotti totali, tutte le categorie,
  tutti i 221 fornitori. Commit: d21814f (motore) + questo (pdf+UI).

## Sessione 15/06/2026 — backup pure-Python (no OOM) + integrità dati (giro inverso)
- **BACKUP — bug strutturale risolto.** Non aveva MAI funzionato: prima
  `mongodump` (binario assente su Render → 500), poi versione che caricava
  l'intero DB in RAM (dict + json.dumps) → **OOM, worker ucciso (502/503)**.
  Riscritto `routers/backup.py` in **streaming**: scrive il gzip-JSON
  collezione-per-collezione, documento-per-documento (`async for` + batch 500),
  memoria di picco = un documento. Restore: drop+insert a blocchi di 1000.
  VERIFICATO LIVE: file creato `Gestionale_*_.json.gz` **325.8 MB**, backend
  vivo dopo (niente OOM). Commit f9949f4.
- **Caveat backup da decidere con Enzo (NON risolti, onesti):**
  (1) 325 MB perché ogni fattura salva il suo `xml_raw` (XML grezzo completo)
  in Mongo — dato legittimo ma pesante. (2) **`/tmp` su Render è EFIMERO**:
  i backup si perdono a ogni restart/deploy; 7×325MB satura pure il disco.
  Per sicurezza HACCP/contabile reale servono OFF-instance: download periodico
  (`GET /api/backup/download/{file}` funziona) o destinazione esterna
  (GridFS/bucket/email). (3) `/esegui` sincrono va in timeout client (~4 min)
  pur completando lato server → valutare BackgroundTask + poll `/stato`.
- **INTEGRITÀ DATI (controllo-dati/overview).** Manutenzione legittima:
  pulisci-log-obsoleti, ricalcola-costi (97 ricette), rebuild prodotti_master.
  Esclusi dai controlli i falsi positivi: prodotti con UNICA fonte
  `prodotti_vendita` (fatti in casa: no fornitore/prezzo d'acquisto per natura)
  + nuovi non-prodotti (ddt, maggiorazione, spese gestione incasso,
  documentazione, confezioni assortite, vassoi/tondi alluminio, bilancio,
  conai, corrispettivo). Risultato: senza_fornitore 106→41, senza_prezzo
  414→357, ingredienti 21→7, job_falliti 71→10. **Score resta 20/100**:
  dominato dai 2 critici reali, NON truccato.
- **Giro inverso (occhi diversi) — scoperte:**
  • 7 ingredienti = 3× **Fiordilatte** (prodotto vero, panini: collegabile solo
    se acquistato via XML) + 4 preparazioni interne (tritato, involtino
    melanzane, naspro, aromi) → mappare a mano o accettare.
  • 10 fatture = **6 P.IVA note** fornitore="": 01713080628, 06158091212,
    07914040634, 09312771216, 09317030014, 09462471211 → solo inserimento
    manuale o ri-import XML (no xml_raw, P.IVA non in anagrafica).
  • **BUG NORMALIZZATORE (da fixare in sessione dedicata):** il rebuild
    force-matcha descrizioni non-food su nomi-cibo brevi → un vassoio
    ("vassoio stella trasp.") è diventato prodotto **"Tè"**, dei tovaglioli
    ("tovaglioi decor. Natal.") **"Aglio"**. I record con canonical-spazzatura
    (Tondi alluminio, Vassoi cartone, Bilancio, Conai) li filtro via
    non-ordinabili; i casi food-canonical (Tè=vassoio) restano e richiedono
    correzione del matcher in `prodotti_master.normalize`/rebuild (NON toccato
    ora: rischio di rompere i match buoni, serve revisione mirata).
- Verifica anti-cosmetica: le parole-esclusione NON nascondono cibo vero
  (maggiorazione/documentazione/confezioni = 0 match nel catalogo).
- **DIPENDENZA OPERATIVA (gotcha):** `rebuild prodotti_master` rigenera gli id
  canonici e ORFANA i link `ingredienti_dettaglio` delle ricette → dopo OGNI
  rebuild va rieseguito `food-cost/ricalcola-costi-tutte-ricette` (ingredienti
  non-collegati 7→21 senza, di nuovo 7 dopo). Verificare che il job notturno
  esegua i due step in quest'ordine, altrimenti il food cost si rompe di notte.

## Sessione 14/06/2026 — auth veloce + comparatore fornitori 60gg
- **Gate auth**: decisione IMMEDIATA dalla config in cache (cachedAuthConfig) →
  keypad mostrato subito, niente "Caricamento..." per 50s su Render freddo.
  PIN richiesto UNA volta a sessione (sessionStorage lotti_gate_ok), NIENTE
  auto-open da token salvato (prima entrava senza PIN). validateToken NON più
  usato nel gate. Ruolo salvato al login (lotti_ruolo, isAdmin()).
- **Comparatore 60gg** (richiesta Enzo): prodotti_master.lista() arricchisce
  ogni prodotto con fornitori_60gg (per ogni fornitore il prezzo più recente
  negli ultimi 60gg, ordinati dal più economico) + miglior_prezzo/fornitore_60gg.
  Helper _comparatore_60gg dai prezzi_storici già salvati (no rebuild).
- **OrdiniView**: card mostra "€ X / conf" (miglior prezzo 60gg) e "N fornitori
  60gg — scegli nel carrello"; nel CARRELLO ogni riga con >1 fornitore ha un
  menu a tendina (più economico in alto) che aggiorna prezzo+fornitore della riga.
  Es: "farina Caputo 0" → vedo i fornitori che l'hanno fatturata in 60gg e scelgo.

## Sessione 14/06/2026 — prezzi nel carrello + login (screenshot Enzo)
- **Comparatore prezzi RISCRITTO** (_comparatore_60gg in prodotti_master): NON taglia
  più a 60gg secchi (farina/liquori fatturati ogni 80-90gg sparivano → carrello
  senza prezzo). Ora per OGNI fornitore tiene l'ultimo prezzo noto, ordina
  recenti(<=60gg) prima poi prezzo crescente, e marca giorni_fa + recente.
  La lista garantisce sempre miglior_prezzo_60gg (fallback 90gg/ultimo) +
  prezzo_recente + prezzo_giorni_fa.
- **OrdiniView**: catalogo mostra SEMPRE il prezzo (badge verde se recente, ambra
  "·vecchio" se >60gg, rosso "n/d" se assente). Carrello: dropdown fornitori con
  "€ X · recente / N gg fa", migliore in cima. Il prezzo segue il prodotto nel
  carrello con la sua freschezza.
- **Login (bug "entra senza PIN dopo lungo Caricamento")**: causa = cache config
  avvelenata da un mio fallback {enforce:false} di sessioni precedenti.
  Fix: fetchAuthConfig cachea SOLO risposte reali (flag _reale), fallback ora
  enforce:true (prudente); cachedAuthConfig si fida solo della cache reale;
  LoginGate valida il token se presente (grazia di rete), altrimenti mostra
  SUBITO il keypad. Mai più apertura senza PIN; niente attesa di 50s.

## Sessione 14/06/2026 — robustezza: prezzi affidabili, riordino vero, giacenze facili
1. **CERTEZZA MIGLIOR PREZZO**:
   - _comparatore_60gg ora usa SOLO prezzi da fonte='fattura' (no listino/acquaviva/saima:
     sono prezzi di catalogo, non pagati — regola Enzo). Niente fallback su listino: se
     non c'è prezzo da fattura → "prezzo n/d", mai un prezzo finto.
   - rebuild: prezzi_storici tenuto PER FORNITORE (4 più recenti di ciascuno), non i 30
     globali. Un fornitore più economico fatturato di rado NON viene più buttato fuori dal
     comparatore. Frontend catalogo: niente fallback su 90gg/ultimo.
2. **RIORDINO AUTOMATICO**: esegui_riordino_automatico ora assegna ogni prodotto sotto-scorta
   al MIGLIOR FORNITORE dal comparatore e riempie il prezzo reale (prima: fornitore stantio +
   prezzo €0). Nota di riga con "stock/soglia · Ngg fa".
3. **GIACENZE FACILI**: nuovo POST /magazzino/prodotti/{id}/rettifica (imposta lo stock al
   valore CONTATO, registra la differenza come movimento "rettifica" via applica_movimento_stock).
   ordini-app/giacenze espone id+nome in by_key. OrdiniView scheda Giacenze ora EDITABILE:
   cerca prodotto, scrivi quanto hai contato, Salva → giacenza aggiornata.

## Sessione 14/06/2026 — scheda ricetta stampabile stile Ceraldi (palette Lotti)
- Endpoint GET /ricette/{id}/pdf-scheda RISCRITTO: layout Ceraldi originale (NON copia
  Pocchiari) in palette LOTTI (salvia #5b7a6b, verde #3d8168, crema #faf7f0, Plus Jakarta
  Sans + Fraunces). NIENTE viola/navy qui (quello è il gestionale generale).
  Funzione pura _render_scheda_ceraldi(r) — testabile.
- Alimentata dai DATI REALI delle 97 ricette: nome, reparto, porzioni, costo_totale,
  costo_porzione, ingredienti_dettaglio (nome/quantita/unita), allergeni, note, foto_url.
- Sezioni opzionali (mostrate solo se la ricetta ha i campi): copertina (foto_url),
  procedimento[] (passi {titolo,testo} o stringhe) + dettaglio_critico, segreti
  (consigli[], errore_da_evitare, nutrizione.kcal), impiattamento[], varianti[], occhiello.
  Questi campi NON esistono ancora nei doc (extra=allow li accetta): vanno popolati.
- FULLY RESPONSIVE: niente larghezza A4 fissa (era la causa dello scroll orizzontale su
  telefono), media query a 640/480px → 1 colonna. @media print nasconde la barra, @page A4.
- Frontend: RicetteDashboardView card ora ha bottone "Stampa scheda" (emerald) che apre
  window.open(`${API}/ricette/${id}/pdf-scheda`).
- PROSSIMO PASSO: UI per editare procedimento/segreti/varianti/impiattamento per ricetta
  (ora si possono solo scrivere via API/DB). Strudel di mele NON è tra le 97 (è un file
  HTML separato in outputs, dati dalle immagini Pocchiari).

## Sessione 14/06/2026 — scheda in-app + editor sezioni editoriali
- **BUG risolto (scheda non si apriva)**: il bottone "Stampa scheda" faceva
  `window.open(`${API}/ricette/{id}/pdf-scheda`)` -> GET in scheda nuova SENZA header
  Authorization. Con AUTH_ENFORCE attivo -> 401, la scheda non si apriva. Ora apre un
  MODALE IN-APP (SchedaModal in RicetteDashboardView): axios.get responseType:text
  (l'interceptor mette il token) -> HTML in `<iframe srcDoc>`; bottone Stampa chiama
  `iframe.contentWindow.print()` (l'`@media print` A4 e' nel documento). Overlay +
  stopPropagation, chiusura con Esc. Niente piu' re-login, niente token in URL.
- **Editor sezioni editoriali** (prima si scrivevano solo via DB): bottone "Compila"
  sulla card -> SchedaEditorModal. Campi = ESATTAMENTE quelli letti dal renderer
  (verificato sul codice): occhiello, procedimento[{titolo,testo}], dettaglio_critico,
  consigli[] , errore_da_evitare, nutrizione{kcal}, impiattamento[{elemento,nota}],
  varianti[{nome,descrizione}]. ATTENZIONE: consigli/errore/nutrizione sono campi
  TOP-LEVEL nel doc ricetta, NON annidati sotto "segreti" (lo STATO li descriveva
  annidati: era sbagliato, allineato al renderer). Prefill dal prop `ricette` (la lista
  ritorna doc grezzi, il model ha extra=allow -> i campi extra ci sono gia').
- **Backend**: nuovo `PUT /api/ricette/{id}/scheda` (ricette.py) con model
  SchedaEditoriale (extra="forbid", tutti Optional) + `Body(...)`. Scrive solo i campi
  inviati via `model_dump(exclude_none=True)`: None=invariato, lista vuota/""=azzerato.
  Il PATCH generico /ricette/{id} ha una whitelist che NON include queste sezioni: NON
  toccato, endpoint dedicato per non allargare la whitelist (un sistema per funzione).
- Dopo Salva: `onRicetteUpdate()` ricarica la lista; la scheda (che legge dal DB) riflette
  subito le nuove sezioni.
- Pulizia: rimosso import morto `Trash2` poi rireintrodotto perche' ora USATO nell'editor;
  rimosso `window.open`. Build CRA CI=false OK, zero warning sul file.
- RESTA APERTO: scheda di esempio "strudel di mele" e' un HTML standalone in outputs, NON
  tra le 97 ricette del DB (invariato). Eventuale anteprima della scheda dentro lo stesso
  editor (oggi: Compila -> Salva -> Stampa scheda sono due bottoni distinti sulla card).

## Sessione 14/06/2026 — anteprima editor + audit incrociato 17 pagine (a vista)
- Editor scheda: aggiunto bottone "Salva e vedi" -> salva e apre SUBITO la SchedaModal
  (anteprima in-app). Verificato headless: marker scritto -> visibile nell'anteprima.
- AUDIT headless (Playwright, chromium, 412x915, login via initScript token+ruolo+
  lotti_gate_ok). 17 pagine visitate: dashboard, ricette, lotti, gelati, ordini,
  fornitori, fatture, magazzino_prodotti, prodotti, listino, controllo_dati,
  sconti_merce, allergeni, schede_tecniche, storico_produzioni, movimenti_magazzino,
  backoffice. RISULTATO: 16/17 con ZERO errori console/page. `ricette` ha 3 errori =
  404 immagini cover (/images/ricette/*.jpg) dei 3 panini -> buco-dati, non JS.
  `ordini` e `magazzino_prodotti` caricano lenti (rendering incrementale): lo screenshot
  a 3.8s sembrava vuoto, a 14s magazzino = 33k char pieno. Non sono bug.
- COLLEGAMENTI verificati (richiesta Enzo) con valore coincidente su 3 pagine:
  MIYA LIQUIRIZIA / DI COSMO S.R.L. / EUR 13.03 appare in fatture(import)->
  magazzino_prodotti (card "FATTURA · DI COSMO") -> Ordini catalogo (EUR 13.03 ·vecchio,
  Giac.0) -> prodotti-master. Catena fatture->magazzino->ordini integra.
  Prezzi catalogo: 176/200 presenti, tutti con fornitore, SOLO da fattura (regola ok).
- DA SISTEMARE (dati, non codice): 3 ricette puntano a /images/ricette/*.jpg inesistenti
  (Panino Caprese, Panino Cotto e Fiordilatte, Panino Crudo e Fiordilatte). Caricare le
  3 foto dall'app (upload-foto -> diventano /uploads, che il frontend serve a 200).

## Sessione 14/06/2026 — import 24 fatture ricevute + verifica ordini/magazzino
- Importate le 24 XML di 20260614_ExportFattureRicevute.zip via POST /api/fatture/importa-async
  (15 fornitori, 155 righe). Esito: 24/24 processate, 22 ok, 2 SALTATE. Le 2 saltate
  NON erano duplicati: sono le 2 fatture di TOP SPINA s.r.l. (numeri 393 e 426), fornitore
  con escluso=True in anagrafica -> il ciclo le conta in fatture_saltate_escluse e fa
  `continue` (non incrementa fatture_processate=ok). I duplicati invece NON vengono saltati:
  l'import fa upsert su (numero_fattura+piva), quindi un doppione e' comunque "ok" e
  aggiorna sul posto. Conteggio fatture invariato (386) = effetto dell'upsert, non prova
  di doppioni. (Lezione: distinguere saltate_escluse da duplicati; il job salva solo
  total/processed/ok/errori, NON saltate_escluse -> dedurlo dall'anagrafica escluso.)
- "Aggiorna Materie da fatture" (/api/aggiorna-materie-da-fatture) e' DEPRECATO/no-op: le
  materie si leggono direttamente da lotti_fornitori, che l'import popola gia'.
- VERIFICA "te li ritrovi in ordini/magazzino" (richiesta Enzo):
  * Ordini = prodotti-master (collezione unificata, total 2833): elenca OGNI prodotto con
    TUTTI i suoi fornitori in fornitori[]. I prodotti delle fatture ci sono: caputo->
    F.lli Fiorentino, "Code Aragosta"->BUONGELO, cialda/caffe->KIMBO, ferrarelle/electa/
    vitasnella, ecc. (ricerca: GET /prodotti-master?q=...).
  * Magazzino = gestione-prodotti (magazzino_unificato.py, total 1192, CACHE 120s):
    DEDUP per `key` normalizzato (set `visti`) -> mostra UNA voce-rappresentante per
    prodotto e UNA sola etichetta fornitore (la prima vista); piu' flag `visualizza`
    (= _e_alimento: i non-food e alcuni semilavorati sono vis=False). Cercare con
    ?search= (logica UI), non per nome esatto del fornitore nuovo.
  * Effetto: un fornitore i cui articoli coincidono (per key) con prodotti gia' presenti
    NON appare col proprio nome in gestione-prodotti, pur essendo nel catalogo Ordini.
    Es.: BUONGELO "Coda d'Aragosta" -> in Ordini sotto BUONGELO; in Magazzino deduplicata
    sotto "CODA D'ARAGOSTA [VANDEMOORTELE]" e vis=False.
  * Fornitori "a 0" in magazzino col proprio nome: CONI GALASSO e TOP SPINA (righe quasi
    tutte non-food/servizi: cartoni, secchielli, palette, FUSTO+cauzioni -> filtrate
    correttamente) e BUONGELO (deduplicato, vedi sopra).
- DA VALUTARE (Enzo): se "Coda d'Aragosta" (cibo) deve essere visibile in magazzino,
  togliere il vis=False o non deduplicarla con il semilavorato congelato Vandemoortele.

## Sessione 14/06/2026 — fornitori TRI-STATO (escluso / solo magazzino / completo)
RICHIESTA Enzo: TOP SPINA va incluso ma deve popolare SOLO il magazzino, non i Lotti.
Serviva un terzo stato oltre al booleano escluso.
- **Campo nuovo**: `fornitori.tipo_fornitura` in {"completo","solo_magazzino","escluso"}.
  `escluso` (bool) resta sincronizzato (True solo se tipo=="escluso") per retro-compat.
  In assenza del campo si deriva da escluso. La lista /fornitori ora ritorna tipo_fornitura.
- **Endpoint**: POST /api/fornitori/tipo-fornitura?nome=&tipo= (valida i 3 valori, upsert,
  sincronizza escluso). /escludi ora setta anche tipo_fornitura per coerenza.
- **Import (fatture.py)** — bivio: dopo il check escluso (=salta tutto), calcolo
  `is_solo_mag`. Due guard `if is_solo_mag: continue`:
  (1) sul loop che crea i `lotti_fornitori` (→ niente tracciabilità lotti),
  (2) sul loop "Match ingredienti<->prodotti fattura" (→ niente mappature/ricette).
  Resta attivo `_carico_magazzino_bar_da_fattura` (popola magazzino) e la fattura viene
  salvata (→ catalogo Ordini via prodotti-master, che legge da db.fatture).
  Architettura verificata: Magazzino legge magazzino_bar_prodotti+lotti_fornitori; Ordini
  da db.fatture; Lotti da lotti_fornitori. Quindi solo_magazzino: in magazzino (via bar) e
  Ordini (via fattura), NON in Lotti (nessun lotti_fornitori). `_carico_bar` filtra già con
  e_merce_alimentare (fusti birra passano, cauzioni/spese no).
- **UI**: FornitoriList — nel pannello anagrafica del fornitore, sezione "Cosa popola questo
  fornitore" con 3 bottoni (Magazzino+Lotti verde / Solo magazzino ambra / Escluso rosso) →
  POST tipo-fornitura + refresh, con override ottimistico.
- TOP SPINA va impostato su "solo_magazzino" (vende fusti birra: magazzino sì, ricette no).

### Correzione approccio solo_magazzino (stessa sessione)
La via "magazzino_bar" NON basta: `_carico_magazzino_bar_da_fattura` carica solo prodotti
di categoria bar (BIRRE/ACQUA/VINO/...); un "FUSTO N'ARTIGIANA" non riconosciuto resta fuori.
Verificato: il Magazzino vero (gestione-prodotti / prodotti_unificati) legge `lotti_fornitori`,
mentre la pagina Lotti e cerca-universale leggono `db.lotti` (mai lotti_fornitori).
APPROCCIO DEFINITIVO: per solo_magazzino i lotti_fornitori VENGONO creati ma con flag
`solo_magazzino: True` (quindi compaiono in Magazzino con giacenza). Il flag viene escluso da:
materie_prime.py (get_materie_prime, get_materie_prime_da_fatture, get_storico) e dal nudge
ricezione in supervisor_operativo.py. prodotti_unificati resta INCLUSIVO (magazzino). Il match
ricette (mappature) resta saltato per solo_magazzino. Risultato atteso: in Magazzino + Ordini,
NON in Materie Prime / ricette / pagina Lotti.

## Sessione 14/06/2026 (pom) — GOAL Enzo: import robusto + dedup 3 campi + FIFO ricette
RICHIESTA (4 parti):
1. Import: se il fornitore NON è in anagrafica, chiedere PRIMA cosa fare (3 opzioni
   tri-stato escluso/solo_magazzino/completo) → "continua" → poi importa.
2. Import robusto: progresso non si perde cambiando pagina; barra di avanzamento;
   esclude SOLO i duplicati.
3. DUPLICATO = stessi 3 campi: nome fornitore + numero fattura + data fattura. [FATTO]
4. FIFO ricette (DECISIVO): l'ingrediente della ricetta deve puntare al lotto della
   fattura FIFO ATTIVA (la più vecchia con giacenza residua), NON all'ultima ricevuta.
   Es: uova EuroUova fatt.1 (180pz), ne uso 12 → 168 restano → la ricetta resta su fatt.1
   finché non si esaurisce; solo allora passa a fatt.2 (stesso o altro fornitore).

[FATTO] #3 dedup: in fatture.py chiave_fattura ora = {fornitore, numero_fattura,
  data_fattura} (era numero+piva). Commit d3c0541. RISCHIO NOTO: se la ragione sociale
  varia tra import lo stesso doc non viene riconosciuto duplicato; in pratica il fornitore
  arriva sempre dallo stesso campo XML CedentePrestatore → stabile. (Endpoint cleanup
  duplicati riga ~1051 e funzione sync riga ~108 ancora su numero+piva: DA ALLINEARE.)

[SCOPERTA CHIAVE — conflitto due sistemi paralleli su ricetta↔fattura]:
  - routers/aggiornamento_ricette.py :: aggiorna_ricette_da_fattura → chiamato all'IMPORT
    (fatture.py riga 965). SOVRASCRIVE ingredienti_dettaglio con i dati dell'ULTIMA fattura
    ricevuta (fornitore/numero_fattura/data_fattura/data_scadenza/lotto_fornitore) +
    ricetta.ultima_fattura_fornitore. NESSUNA nozione di giacenza/FIFO. = "last wins".
  - routers/lotti_produzione.py :: scala_lotti_fornitori_per_ricetta (riga 411) → chiamato
    alla PRODUZIONE. FIFO CORRETTO per data_fattura (sort _parse_data_fattura), consuma
    giacenza residua, marca esaurito, produce lotti_scalati. Questo è quello giusto.
  PROVA live: ricetta "Cornetto pistacchio", ingrediente "cat.a uova fresche da 180" →
  ora SAIMA 1/1557 del 07/01/2026 (ultima importata), non il lotto FIFO attivo.
  VIOLA la regola "un solo sistema per funzione".

[PIANO #4 — direzione tecnica decisa]: il riferimento fattura/data mostrato sull'ingrediente
  NON va più congelato all'import. Deve DERIVARE dal lotto FIFO attivo (lotto_fornitori più
  vecchio con esaurito!=True e residuo>0 per quell'ingrediente). Single source = giacenze.
  Step: (a) funzione "peek" FIFO (come scala_* ma senza consumare) che ritorna il lotto
  attivo per ingrediente; (b) la scheda/scheda-pdf e la lista ingredienti usano il peek;
  (c) all'import: STOP alla sovrascrittura last-wins — aggiorna il riferimento solo se il
  lotto attivo cambia per FIFO (cioè il precedente è esaurito). Verificare end-to-end con
  EuroUova/SAIMA uova.

[PIANO #1 modal fornitore sconosciuto]: pre-scan dei file (estrai fornitori) → quelli non in
  anagrafica mostrati in modal con 3 bottoni tri-stato → salva tipo-fornitura → poi import.
[PIANO #2 robustezza]: job_id già server-side (import_jobs) con total/processed/ok/errori.
  Persistere job_id in localStorage e riprendere il polling al rientro in pagina; barra =
  processed/total. Da verificare/ritoccare nel componente frontend ImportFatture.

## Sessione 14/06/2026 (pom-2) — DIZIONARIO universale ingredienti + uso/scheda tecnica
RICHIESTA Enzo: dizionario UNICO e UNIVERSALE che unifichi i nomi-fattura eterogenei dei
fornitori nei pochi ingredienti madre (margarina, cacao, gocce/scaglie cioccolato, burro,
ecc.); inoltre sapere COS'E' e A COSA SERVE ogni prodotto (es. "Olva Thermo Quick = margarina
per cornetti/sfoglia" vs altra per creme) cercando online la scheda tecnica, scaricando il PDF
e memorizzandolo, così alla produzione si sa quale prodotto scaricare dal magazzino e quale
fornitore chiamare.

DIAGNOSI VERIFICATA (stato reale, non inferito):
- Infrastruttura ESISTE ma incompleta: db.nome_mapping (desc→nome_canc), db.dizionario_prodotti
  (nome_normalizzato+aliases[]), db.mappature (prodotto_fattura→ingrediente_ricetta, fuzzy 70),
  db.mappature_ingredienti (confermate), prodotti_canonici; endpoint GET /api/food-cost/dizionario
  + /dizionario/search + POST /dizionario/manuale. controllo_dati.py già segnala "ingredienti
  senza prodotto canonico".
- COPERTURA SCARSA e SPORCA (numeri live): prodotti-master ha 33 varianti "burro", 43 "cioccolato",
  13 "cacao", 11 "margarina". Ma nel dizionario: "Margarina" canonico = 1 solo alias (olva thermo
  quick); "Burro" canonico = 0 alias; esistono canonici SPORCHI = descrizioni grezze promosse a
  canonico ("burro g. 8 porzio. parm", "cacao da rosso bruno 22/24 van hou"). Quindi NON e' un
  dizionario madre curato: la maggior parte delle varianti non e' ricondotta all'ingrediente madre.
- CAMPO "uso/impiego/scheda_tecnica/destinazione" NON ESISTE in nessun router. Assente del tutto.
- PROVA FATTIBILITA' web (riuscita): cercato "OLVA THERMO QUICK" → schede tecniche reali online.
  La gamma OLVA ha USI DIVERSI: Thermo Quick = sfoglia/croissant; Thermo Pastry = sfoglia metodo
  indiretto; Thermo Gateaux = creme/frolla/lievitati-montati; Melange Thermo Quick = sfoglia/danese/
  croissant. → Unificarle sotto un unico "Margarina" e' SBAGLIATO: l'uso le distingue. Conferma la
  necessita' del campo impiego.

LEGAME COL FIFO: il dizionario canonico+uso e' PREREQUISITO del FIFO ricette. Per scalare la
giacenza di "margarina sfoglia" devo prima sapere quali righe-fattura SONO "margarina sfoglia".

PIANO (2 filoni, da confermare ambito con Enzo: solo prodotti usati nelle ricette vs tutti i ~2833):
 A) Dizionario canonico UNIVERSALE: definire ingredienti madre; ricondurre TUTTE le varianti-fattura;
    ripulire i canonici sporchi; campo `impiego` (sfoglia/cornetti/creme/frolla/...); revisione Enzo
    sui casi ambigui. Un solo dizionario, single source.
 B) Arricchimento automatico uso/scheda: per ogni prodotto di marca identificabile → web_search scheda
    tecnica → salva url+PDF+descrizione+uso estratto sul prodotto canonico. LIMITE ONESTO: i freschi/
    generici (uova sfuse, latte) non hanno scheda → restano senza uso, si curano a mano.

### REGOLA DI DOMINIO (Enzo, acquisita — vale sempre per il dizionario)
- BURRO e MARGARINA sono INGREDIENTI MADRE DISTINTI. Non confonderli MAI.
- Tutte le margarine (gamma OLVA: Thermo Quick/Pastry/Gateaux, Melange; e altre margarine
  vegetali/per sfoglia: Wiener, Green Valley, ecc.) → nome_canonico = MARGARINA (madre unico).
  La distinzione d'uso (sfoglia / croissant / creme-frolla) va nel campo `impiego`, NON come
  canonico separato. → quindi unificare l'attuale doppione "Margarina Sfoglia" dentro "Margarina".
- BURRO = SOLO burro materia prima (panetti, porzioni, monoporzioni di burro latticino). Il burro
  vero esiste tra le righe-fattura e va identificato.
- NON classificare prodotti FINITI/SEMILAVORATI come ingrediente madre. Verificato che oggi sotto
  nome_canonico="Burro" sono finiti per errore: croissant ("burro cannella crema croissant",
  "95g burro croissant pistacchio"), tartellette ("blister burro tartelletta"), aromi ("ESSENZA
  BURRO ML 500"), e "albicocca burro croissant" addirittura sotto "Albicocche". Da ripulire:
  questi NON sono burro materia prima e inquinerebbero il FIFO (scaricherei un croissant come burro).
- STATO VERIFICATO POSITIVO: le margarine sono GIA' tutte sotto "Margarina" (nessuna sotto Burro).

### Schede tecniche prodotti (mapping web) — file: backend/data/schede_prodotti.json
Mapping serio per prodotto commerciale: ingrediente_madre, impiego (uso reale), composizione
(dichiarazione ingredienti dalla scheda tecnica/PDF scaricato), allergeni, fonte, match_aliases.
FATTO famiglia OLVA (3): Thermo Quick (sfoglia/croissant), Thermo Gateaux (creme/frolla/montate —
NON sfoglia: correggere il vecchio canonico 'Margarina Sfoglia'), Th Pastry (sfoglia metodo
indiretto). Tutti madre=Margarina. PDF Pastry scaricato da CSM/carradistribuzione e verificato.
DA ESTENDERE (margarine in fattura ancora da mappare): MELANGE PLUS HOMILLINA PLATTE e GATEAUX
(SAIMA), MARGAR WIENER ZIEH/BACK/CREME/PLUNDERPLAT (Fiorentino), MARG GREEN VALLEY CROISSANT
(Rondinella), MARGARINA GREEN PLATTE HOMANN (SAIMA). Poi altri ingredienti madre (cacao,
gocce/scaglie cioccolato, ecc.). Errori dizionario da sanare: 'MELANGE PLATTE' una copia su
'Latte Fresco'; i Gateaux su 'Margarina Sfoglia'; canonici margarina frammentati (Margarina,
Margarina Crema, Margarina Sfoglia, Margarina per dolci) -> unificare in MARGARINA + campo impiego.
PROSSIMI STEP: (1) endpoint che applica schede_prodotti.json al dizionario/prodotti_canonici
(impiego+composizione+fonte sul canonico); (2) scheda ricetta: mostrare la composizione in
carattere piu' piccolo sotto l'ingrediente (richiesta Enzo).

### MODELLO ALLERGENI A CASCATA (chiarito da Enzo — scopo HACCP)
Il prodotto finito (cornetto, torta) eredita gli ingredienti dei PRODOTTI COMPOSTI/industriali che
contiene. Per ogni ingrediente-ricetta che e' un prodotto composto acquistato (margarine, estratti/
paste come "zuppa inglese", creme da farcitura, panna vegetale Hopla, coloranti, gelatine, ecc.):
 1. recuperare online la scheda tecnica → composizione (lista ingredienti) + coloranti (E-numbers) + allergeni;
 2. ereditare quegli ingredienti nel prodotto finito, da mostrare in scheda con CARATTERE PIU' PICCOLO;
 3. comporre l'elenco allergeni del prodotto finito sommando quelli dei componenti (incl. avvertenze
    legali coloranti azoici E102/E110/E122/E124/E129 → "puo' influire su attivita'/attenzione bambini").
SCOPO: trasparenza allergeni al cliente (es. allergia a un colorante). NORMATO (Reg. UE 1169/2011 + 1333/2008).
ATTENZIONE: la composizione di uno stesso "tipo" di prodotto cambia per MARCA (es. zuppa inglese:
E102+E124 vs E160b). Identificare SEMPRE la marca dal fornitore della fattura prima di fissare i coloranti.
Prodotti composti gia' visti in fattura da mappare: EST. ZUPPA INGLESE; CREMA CACAO 30% / CIOCCOLATO
BIANCO 10% / NOCCIOLA 13% DA FARCITURA; PREP. VEGETALE HOPLA (panna veg.); PREPARATO FRUTTA FRAGOLA;
coloranti spray; gelatine; + tutte le margarine. (schede_prodotti.json: aggiunta voce Zuppa Inglese.)

### Sezione IMPOSTAZIONI "Fonti produttore" + scraping (richiesta Enzo) — BACKEND fatto
Caso: prodotti estratti da XML senza produttore identificabile (es. "EST. ZUPPA INGLESE"). Enzo
inserisce il sito del produttore reale (zuppa inglese = ELENKA, www.elenka.it) e il sistema fa
scraping per estrarre composizione/coloranti/allergeni, da ereditare nel prodotto finito (allergeni
a cascata). Confermato dato Elenka: sciroppo glucosio, zucchero, estratti vegetali, aromi, E414,
coloranti E102+E124, puo' contenere uovo. schede_prodotti.json aggiornato (produttore=Elenka).
BACKEND (routers/schede_tecniche.py, prefix /api/schede-tecniche) — esteso (NESSUN router nuovo):
 - GET /senza-produttore : prodotti alimentari senza scheda tipo='produttore' (= sito non ancora indicato).
 - POST /scrape {url, prodotto_key?, nome_prodotto?, produttore?, salva?} : scarica la pagina, estrae
   composizione (euristica "Ingredienti:", preferisce la dichiarazione ITALIANA), additivi (E-numbers),
   coloranti (E100-E199), allergeni (keyword IT), avviso azoici (E102/E104/E110/E122/E124/E129 →
   "puo' influire su attivita'/attenzione bambini"). Se prodotto_key presente salva tipo='produttore'.
 - Il salvataggio del sito produttore usa il /salva esistente con tipo='produttore' (no doppioni).
 Fetch via urllib (stdlib, no nuove dipendenze), UA custom, timeout 20s. py_compile OK; scraping
 testato live su pagina Elenka: coloranti E102/E124 + avviso azoici corretti.
 Router gia' registrato in server.py (r_schede_tecniche) → nessun 404.
TODO PROSSIMO: sezione UI in Impostazioni (file frontend da confermare: ImpostazioniPersonaleView.jsx
o pagina Impostazioni generale) con: lista /senza-produttore, input URL produttore (POST /salva
tipo=produttore), bottone "Estrai" (POST /scrape), mostra composizione+coloranti+allergeni. Poi
collegare la composizione alla scheda ricetta in carattere piccolo (cascata allergeni nel prodotto finito).

### Requisito aggiuntivo (Enzo): FOTO ETICHETTA per prodotti senza scraping
Accanto a ogni prodotto in Impostazioni: poter scattare/caricare una FOTO dell'etichetta (es. rum
sfuso) e far LEGGERE al sistema la composizione, per i prodotti dove NON e' possibile lo scraping web.
Da decidere il motore di lettura: (1) OCR server gratis (Tesseract) meno affidabile su foto reali;
(2) AI visiva (modello multimodale via API, ~centesimi/foto, serve chiave) molto piu' affidabile.
DESIGN sezione Impostazioni (unico flusso per prodotto senza produttore): sito produttore + "Estrai"
(scraping, gia' pronto backend /scrape); 📷 foto etichetta + "Leggi" (OCR o AI); campi composizione/
coloranti/allergeni editabili + flag verificato. Output confluisce nella stessa scheda tipo='produttore'
(schede_tecniche) e poi a cascata nella scheda ricetta (carattere piccolo) per gli allergeni.
TODO: scelta metodo lettura foto -> poi costruire UI + endpoint upload/lettura etichetta.

### DECISIONE Enzo: lettura foto IBRIDA (OCR gratis -> AI solo fallback)
OCR gratuito PRIMA (etichette piatte = costo zero); AI visiva SOLO come fallback on-demand quando
l'OCR e' insufficiente. Implementazione scelta: OCR lato BROWSER (gratis, niente binari su Render) →
il testo va a POST /api/schede-tecniche/parse-etichetta (FATTO, deployato 17c2bc7) che usa lo stesso
motore _estrai_da_testo dello scraping. Tasto "Leggi con AI" appare solo se l'OCR resta povero.
BACKEND ORA COMPLETO per le 3 vie (tutte confluiscono in scheda tipo='produttore'):
 - sito produttore → /scrape (web)
 - foto etichetta piatta → OCR browser → /parse-etichetta (gratis)
 - foto difficile → AI visiva (fallback, da collegare quando si sceglie il provider/chiave)
PROSSIMO BLOCCO: UI sezione Impostazioni che orchestra le 3 vie + campi editabili + verificato;
poi cascata composizione→scheda ricetta (carattere piccolo) per allergeni prodotto finito.

### UI sezione fonti/etichette — POSIZIONE: Materie Prime → fornitore → prodotto (richiesta Enzo)
Enzo: NON in Impostazioni ma nel tab "Materie Prime" (MateriePrimeList: fornitori espandibili →
prodotti reali da fatture). FATTO: nuovo componente SchedaFonteModal.jsx aperto da un pulsante
(icona FileText) su OGNI riga prodotto in MateriePrimeList. Il pannello offre 3 vie (tutte → backend
schede-tecniche, scheda tipo='produttore'):
 1) Sito produttore + "Estrai dal sito" → POST /schede-tecniche/scrape ; "Salva" → POST /salva.
 2) Foto etichetta → OCR GRATUITO nel browser (tesseract.js caricato da CDN on-demand, 'ita') →
    POST /schede-tecniche/parse-etichetta.
 3) Incolla testo a mano → "Interpreta testo" → POST /parse-etichetta (rete di sicurezza).
 Mostra composizione, coloranti (E100-199), allergeni e AVVISO coloranti azoici (bambini).
 Modale con overlay + stopPropagation (regola Enzo). Build OK (main.edb91505.js, +1.8kB). Deploy frontend.
NOTE/TODO: (a) la chiave scheda usa prod.descrizione (Materie Prime), che puo' differire dal
nome_normalizzato del dizionario usato in SchedeTecnicheView → valutare unificazione chiave.
(b) "Leggi con AI" (fallback visione) ancora da collegare (serve provider/chiave). (c) Cascata:
ereditare la composizione salvata nella scheda RICETTA in carattere piccolo (prossimo step).

### Card BAR in dashboard (richiesta Enzo) — modulo produzione COMPLETO come pasticceria
Enzo: card "Bar" dove il barista seleziona i prodotti che il bar produce (caffe' freddo, granita
limone, crema caffe', caffe' d'orzo, ginseng, ...). Deve fare TUTTE E TRE come la pasticceria:
(1) elenco prodotti bar selezionabili, (2) registra produzione del giorno, (3) scarica materie/lotti FIFO.
MOTORI DA RIUSARE (no doppioni): colazione.py /registra (pattern: vendite_banco + produzioni +
lotto di produzione + food cost via ricetta collegata); lotti_produzione.scala_lotti_fornitori_per_ricetta
(scarico FIFO per data_fattura). Categorie ricette attuali: rosticceria/pasticceria/panini/altro.
PREREQUISITO (verificato): NON esistono ricette bar ne' categoria "bar". Lo scarico FIFO richiede
che ogni prodotto bar abbia ricetta con ingredienti+dosi (dati di Enzo, NON inventare). 
PIANO: aggiungere categoria "bar" + creare i prodotti bar come ricette; card "Bar" (nuovo tab in
App.js TABS) → vista selezione prodotti + pezzi → POST registra (riusa motore produzioni) + scarico FIFO.
IN ATTESA da Enzo: ingredienti/dosi del primo prodotto (es. crema caffe') per cablare end-to-end,
OPPURE ok a creare i prodotti bar come ricette vuote da compilare nell'editor.

### Ricette bar: modello RESA + scarico proporzionale (dati Enzo)
CAFFE' FREDDO (esempio reale fornito da Enzo): base = 24 caffe' x 8 g = 192 g caffe' (~190 g) +
300 g zucchero -> forma ~1250 g di liquido (1 L + 250 g). RESA ~100 porzioni ("100 caffe'").
=> MODELLO: ricetta con base (ingredienti) + resa_porzioni; scarico per porzione venduta =
ingrediente_base * (porzioni / resa). FIFO sui lotti come pasticceria. Il dato "prodotto finale"
(resa) lo inserisce Enzo nella ricetta. NB confermare resa=100 con Enzo.
ALTRE: granita di limone, granita di fragola (ricette di Enzo). Caffe' del nonno = CONFEZIONATO
Kimbo -> "ricetta" = 1 porzione = 1 pezzo; composizione/allergeni dal sito Kimbo o da foto
(feature SchedaFonteModal gia' pronta). Pattern confezionati: scarico 1 pz dal magazzino prodotto.

### TEMA STRATEGICO: prodottizzazione / vendita app multi-utente (Enzo)
Enzo vuole vendere l'app (Android, ~10 EUR una tantum) ad altre pasticcerie. Ogni cliente ha bisogno
del PROPRIO database. Vuole auto-configurazione semplice: l'utente importa le sue fatture XML,
aggiunge dipendenti + dati azienda, e un MANUALE passo-passo per ogni pagina. Analisi onesta:
- App gia' web (React+FastAPI+Mongo) -> "Android" = PWA/wrapper della web app esistente.
- MULTI-TENANCY (il pezzo grosso): oggi single-tenant (un DB "Gestionale", credenziali fisse via env).
  Opzioni: (a) 1 DB per cliente = isolamento totale ma costo/gestione per cliente; (b) 1 DB condiviso
  con tenant_id su ogni doc = piu' economico ma richiede refactor per filtrare TUTTE le query. 
- COSTI: 10 EUR una tantum vs costi RICORRENTI (hosting + DB per cliente) -> con molti clienti i
  ricorrenti possono superare il una-tantum. Da valutare modello (es. tier condiviso / canone).
- IMMEDIATO/fattibile: wizard di onboarding (import XML c'e'; /azienda c'e'; personale c'e') +
  MANUALE in-app passo-passo per pagina (genero i contenuti guida). 
- GROSSO: isolamento multi-tenant + auth per cliente + provisioning + store Android + licenze.
PIANO PROPOSTO (da confermare): fase 1 manuale in-app + wizard onboarding (single-tenant, utile subito);
fase 2 multi-tenancy vera quando si decide il modello costi/licenza.

### Fase 1 prodottizzazione: VIA LIBERA (Enzo) + vincolo ZERO-ASSISTENZA
Enzo: procedere con fase 1 (manuale in-app + wizard onboarding). Prezzo era indicativo. VINCOLO
CHIAVE: dopo la vendita NON vuole oneri di gestione/manutenzione/assistenza. Vuole un contratto di
cessione standardizzato senza oneri a suo carico.
ANALISI ONESTA (tensione tecnica): "vendi e finisci" e' compatibile solo se l'app NON gira sulla
SUA infrastruttura. Vie: (a) SELF-HOSTED/pacchetto: il cliente ospita su propri server/DB -> zero
oneri per Enzo ma richiede competenza tecnica del cliente (dura per una pasticceria); (b) SaaS gestito
da Enzo -> facile per il cliente ma manutenzione continua per Enzo (contrario al suo volere); (c) terzo
che gestisce l'hosting per conto dei clienti (Enzo cede solo licenza+codice). Per "vendi e finisci"
reale serve (a) o (c). Se gira sull'infra di Enzo gli oneri NON si azzerano.
FASE 1 da costruire (progettata per minimizzare oneri): MANUALE in-app passo-passo per pagina +
WIZARD onboarding (import XML [c'e'], dati azienda [/azienda c'e'], dipendenti [personale c'e']).
CONTRATTO: bozza principi cessione as-is/no-assistenza fornita a Enzo (NB: serve revisione legale,
non sono avvocato). TODO: costruire manuale in-app + wizard (blocco dedicato).

### Fase 1 — MANUALE in-app FATTO (wizard onboarding = prossimo)
ManualeView.jsx: nuovo tab "Guida" (App.js TABS, icon BookOpen; render activeTab==="guida").
Manuale passo-passo (accordion) per le pagine chiave: Primi passi, Importa Fatture, Fornitori,
Materie Prime, Ricette, Ordini, Lotti/HACCP, Magazzino, Registri HACCP. Contenuti estendibili
(array MANUALE nel componente). Build OK, deploy frontend. NB esiste gia' tab "manuale" =
ManualeHACCPView (manuale HACCP normativo), diverso: il nuovo e' "guida" (manuale d'USO app).
TODO fase 1 restante: WIZARD onboarding (1 importa XML, 2 dati azienda, 3 dipendenti) come flusso
guidato di prima configurazione. Poi: card Bar (attende dosi/conferma resa caffe freddo) e cascata
allergeni in scheda ricetta.

### COLLEGATO schede_prodotti.json (non piu' orfano) — commit 6228fe8
GET /api/schede-tecniche/scheda?nome= → ritorna la scheda salvata (db.schede_tecniche tipo=produttore)
oppure, se assente, la composizione BASE da schede_prodotti.json quando un match_alias e' contenuto
nel nome del prodotto (gestisce sia 'composizione' sia 'composizione_varianti' della zuppa inglese;
ricava coloranti/allergeni/avviso via _estrai_da_testo). SchedaFonteModal ora fa GET al mount e mostra
subito la composizione/allergeni. RISULTATO: aprendo un prodotto OLVA o zuppa inglese in Materie Prime
→ fornitore → icona scheda, compaiono composizione + allergeni + avviso azoici gia' mappati.
Build main.b65fc68c.js OK, deploy.

### Stato lavori (post-audit, per chiarezza)
ORFANO risolto: schede_prodotti.json ora collegato (sopra).
NON ANCORA INIZIATI (lavori pianificati, non mezzi-lavori abbandonati):
 - wizard onboarding (fase 1, parte 2);
 - tour interattivo in-app;
 - modal classificazione fornitore sconosciuto in import;
 - barra avanzamento import persistente tra pagine;
 - FIFO ricette (unificare aggiornamento_ricette last-wins col motore FIFO);
 - dizionario universale + pulizia 'Burro';
 - card Bar (attende dosi/resa caffe freddo);
 - cascata allergeni nella scheda ricetta (eredita composizione prodotti composti).

### FATTO + VERIFICATO LIVE — Cascata allergeni HACCP nella scheda ricetta (commit e400a60)
GET /api/ricette/{id}/pdf-scheda: prima del render, per ogni ingredienti_dettaglio risolve la scheda
del prodotto composto via risolvi_scheda() (condivisa in schede_tecniche.py), provando sia `nome`
(ingrediente-madre) sia `nome_fattura` (descrizione reale acquistata). Se trovata:
 - sotto l'ingrediente, in font 9px, la composizione ("↳ ...") + tag "⚠ coloranti azoici" se presenti;
 - aggrega gli allergeni nel blocco "Allergeni" del prodotto finito (manuali ricetta + ereditati);
 - avviso azoici (E102/E110/E122/E124/E129 → bambini) sul prodotto finito.
Verifica: Cornetto pistacchio (id 71cc9362-42d8-47b1-ba35-ef4acc8262fe) mostra composizione zuppa
inglese Elenka (E102/E124), avviso azoici, e allergene ereditato "puo' contenere uovo". OK.
LIMITE noto: la cascata scatta quando nome/nome_fattura contiene un alias di schede_prodotti.json.
Per ingredienti-madre generici senza prodotto composto mappato non scatta (corretto). Ampliare la
copertura = aggiungere schede/alias o risolvere via lotto FIFO associato (affinamento futuro).

### Riepilogo sessione (2 pezzi completati e verificati)
1. schede_prodotti.json collegato (GET /scheda, modal mount) — 6228fe8.
2. Cascata allergeni nella scheda ricetta — e400a60 (verificato live).
Restano i moduli pianificati non iniziati (vedi inventario sopra): wizard onboarding, tour, modal
fornitore sconosciuto in import, barra import persistente, FIFO ricette, dizionario universale +
pulizia Burro, card Bar (attende dosi/resa).

### Fase 1 — Wizard Configurazione guidata — commit (vedi log)
frontend/src/components/haccp/ConfiguraWizard.jsx: nuovo tab "Configura" (in TABS_ALTRO, icona ClipboardCheck).
Checklist onboarding di 7 passi in ordine, ognuno con perche' + pulsante che naviga al tab REALE via onNavigate(setActiveTab):
fatture → fornitori → materie → ricette → personale → registro_haccp → guida.
Passi completati persistiti in localStorage (key lotti_onboarding_fatti); barra avanzamento %, azzera.
Solo lettura/navigazione: nessuna modifica a logica esistente. Build main.3772c31a.js OK.
Cascata allergeni: CONFERMATA gia' completa e verificata live in sessioni precedenti (commit 5607e58); nessun intervento necessario.

## Sessione 14/06/2026 — FIFO ricette: provenienza single-source (peek) + stop last-wins
RICHIESTA (handoff, priorità 1): l'ingrediente della ricetta deve puntare al lotto FIFO ATTIVO
(fattura più vecchia con giacenza), non all'ultima ricevuta. Due sistemi scrivevano il riferimento
(import last-wins vs produzione FIFO) → violazione "un solo sistema".

DIAGNOSI LIVE (Cornetto pistacchio, ingrediente "cat.a uova fresche da 180"): puntava a SAIMA
1/1557 07/01/2026 con nome_fattura **"NUOVA BIANCALIEVE CREMA DA MONTARE"** (panna, non uova!).
Causa radice doppia: (a) last-wins all'import; (b) match per-sinonimi a SUBSTRING → "uova" dentro
"n·uova" faceva matchare la CREMA con le UOVA. Lotto FIFO-attivo reale = NATURISSIME 122 del
10/01/2025 (più vecchio con giacenza).

FATTO (commit a2d97f0) — SINGLE SOURCE = lotto FIFO-attivo, niente più congelamento:
- lotti_produzione.py: estratto `_candidati_lotti_fifo(ing)` (ricerca+dedup+sort FIFO) CONDIVISO
  tra scarico produzione (scala_lotti_fornitori_per_ricetta) e nuovo `peek_lotto_fifo_attivo(ing)`
  (ritorna il lotto attivo SENZA consumare). Canonico risolto con usa_llm=False (read-time veloce).
- aggiornamento_ricette.py: (1) match sinonimi ora a PAROLA INTERA (\b…\b): "uova"≠"nuova",
  "sale"≠"salame". (2) NON scrive più fornitore/numero_fattura/data_fattura/data_scadenza/
  lotto_fornitore/aggiornato_il/nome_fattura/ultima_fattura_fornitore sull'ingrediente; resta solo
  l'apprendimento del dizionario mappature_ingredienti. Rimosse variabili morte (data_scadenza,
  lotto_id_forn).
- ricette.py: cascata allergeni (pdf-scheda) ora deriva il prodotto composto dal lotto FIFO-attivo
  (peek.prodotto_nome) + fallback su ing.nome — non più dal nome_fattura congelato (che era errato).
  Nuovo `GET /ricette/{id}/tracciabilita-fifo` (provenienza per ingrediente, derivata live).
  Nuovo one-shot `POST /ricette/pulisci-riferimenti-congelati` (rimuove i 7 campi stantii).

VERIFICATO LIVE:
- tracciabilita-fifo Cornetto/uova → NATURISSIME, "CAT.A UOVA FRESCHE L DA 180", 10/01/2025, disp 180 (corretto).
- pulizia eseguita: 85 ricette pulite, 2814 campi rimossi. Ingrediente uova ora pulito (niente SAIMA/crema).
- cascata allergeni INTATTA: scheda Cornetto mostra ancora zuppa inglese E102/E124 + avviso azoici + "↳" composizione.

PROSSIMO PASSO (PIANO #4b, parte visibile): la LISTA INGREDIENTI nel frontend (TabIngredienti /
scheda) deve mostrare la provenienza FIFO chiamando GET /ricette/{id}/tracciabilita-fifo
(riga "da: FORNITORE · fatt · scad"), così Enzo vede a video il lotto attivo. Verifica headless.
NB: il matcher canonico in produzione ora usa usa_llm=False (deciso per velocità/CPU Render).

## Sessione 14/06/2026 (cont.) — FIFO ricette: parte VISIBILE nel frontend
FATTO (commit 164ec5b): la lista ingredienti della scheda ricetta
(frontend/src/components/haccp/scheda/TabIngredienti.jsx) mostra ora la PROVENIENZA FIFO
derivata live. Sotto ogni ingrediente, riga compatta: "🧾 da: FORNITORE · data_fattura · scad data_scadenza".
Fonte: GET /ricette/{id}/tracciabilita-fifo (lotto FIFO-attivo via peek_lotto_fifo_attivo),
NON i campi congelati all'import. Fetch in useEffect separato su ricetta.id (non blocca la lista;
fallisce silenzioso). Match per nome ingrediente (toLowerCase().trim()), coerente con food-cost/calcola
e tracciabilita (entrambi leggono ingredienti_dettaglio[].nome). Build CRA OK (CI=false craco build),
solo warning preesistente in TabAllergeni. Single source ora completo end-to-end: backend deriva, frontend mostra.

## Sessione 14/06/2026 (cont.) — dedup fatture 3 campi: allineati sync + /dedup (DA HANDOFF)
COMPLETATO l'allineamento rimasto in sospeso (STATO righe 366-370): la regola "duplicato = stessi
3 campi fornitore+numero_fattura+data_fattura" ora è UNICA in tutti i punti di scrittura fatture.
- fatture.py /dedup (~1051): raggruppa per (fornitore, numero_fattura, data_fattura), non più (numero, piva).
  Tiene il doc con più prodotti + più recente, elimina gli altri.
- fatture.py sincronizza_fatture_da_gestionale (~108): chiave = stessi 3 campi, MA ora INSERT-ONLY
  ($setOnInsert): la sync colma i buchi e NON sovrascrive. I 3 campi-chiave sono tolti dal payload
  (li semina il filtro) per evitare conflitti di path. Aggiornati i docstring stantii.

DIAGNOSI LIVE (read-only su 2009 fatture, GET /fatture?mesi=0): la vecchia chiave numero+piva trovava
0 duplicati; la chiave 3-campi ne trova 146. Motivo VERIFICATO: i 146 gruppi sono la STESSA fattura da
due origini (xml + gestionalecloud) con **P.IVA diversa** tra le due copie (es. EUROUOVA xml 08317211210
vs gestionalecloud 07832841212), stesso nome fornitore+numero+data. La copia gestionalecloud è quasi
sempre SENZA righe (prodotti=[]). Quindi: (a) la vecchia /dedup era inutile sul dataset reale; (b) la sync
con $set avrebbe sovrascritto l'XML buono con la copia vuota → ora $setOnInsert lo impedisce; (c) /dedup
3-campi tiene la copia XML (più righe) e rimuove la gemella vuota.

NB rebuild giacenze (_esegui_ricostruzione_giacenze ~1097): dedup ancora (numero, piva|fornitore).
NON allineato di proposito: giacenze-safe perché le copie gestionalecloud duplicate hanno prodotti=[]
(non sommano nulla). Lasciato fuori dallo scope (handoff citava solo sync+cleanup). Valutare se unificare.

### Esecuzione /dedup su PROD (one-shot, verificata)
Eseguito POST /api/fatture/dedup col nuovo criterio 3-campi: gruppi=146, rimosse=146,
fatture 2009→1863, dup residui=0. INTEGRITÀ: chiavi-utili (fornitore+numero+data con almeno una
copia con righe) 1654→1654 = nessuna fattura-contenuto persa (la dedup tiene la copia con più righe).
SCOPERTA: 88 delle 146 copie rimosse avevano anch'esse righe → la dedup del rebuild giacenze
(chiave numero+piva, con piva divergente tra origini) NON le avrebbe unite → erano un rischio di
DOPPIO CONTEGGIO giacenze. Ora la collection fatture è pulita e protetta (import+sync su chiave 3-campi).
Bug runtime risolto in corsa: /dedup andava in 500 per sort su created_at misto str/datetime → forzato str.
CONSEGUENZA APERTA (decisione di Enzo): se le giacenze erano già state costruite sui doppioni, un
"ricostruisci giacenze da fatture" le ricalcolerebbe corrette. NON eseguito d'ufficio (operazione pesante
che azzera e risomma). Rebuild in-memory dedup lasciato com'è: ora dormiente su collection pulita.

## Sessione 14/06/2026 (cont.) — guardia "finito≠madre" + ricostruzione giacenze
REGOLA DOMINIO (Enzo, acquisita): il "BURRO G. 8 PORZIONI/monodose" è burro da COLAZIONE inglese,
NON burro da produzione. Non serve ulteriore logica dedicata: annotato e basta (Enzo ha chiesto di
non trascinare il ragionamento).
GUARDIA prodotto-finito (commit 9366c7e, deployata): in normalizzazione.py
`canonico_incoerente_con_finito` + `_prima_parola_significativa`: un prodotto la cui TESTA è un
finito da banco (croissant/cornetto/tartelletta/…) o un aroma (essenza/emulsione) NON viene
canonicalizzato a ingrediente madre grezzo. Applicata nel chokepoint calcola_nome_canonico (tutti e 3
i matcher) e in normalizza-nomi. "MARGARINA … CROISSANT" resta Margarina (croissant=impiego).
Verificato: i 6 lotti finiti con "burro" (cornetto/croissant/tartelletta) non sono più Burro; i 7
burro veri restano. Ricetta "Pasta sfoglia francese" → ingrediente burro risolve a burro reale.
RICOSTRUZIONE GIACENZE BAR (eseguita su prod dopo il dedup): 1863 fatture lavorate, doc_doppi_saltati=0,
righe_caricate=1540, movimenti_fattura_azzerati=1743, prodotti_creati=0, stato=completata. Le giacenze
sono ora ricalcolate sull'insieme fatture pulito → niente doppio conteggio (gli 88 doppioni con righe
erano stati rimossi dal /dedup 3-campi).

## Sessione 14/06/2026 (cont.) — PIANO #1 modal fornitore sconosciuto in import [FATTO]
Backend: nuovo POST /fatture/prescan-fornitori — estrae i fornitori distinti dagli allegati
(XML/ZIP/.p7m) SENZA importare e ritorna i non-classificati (sconosciuto/in_attesa/senza tipo_fornitura).
Helper _estrai_xml (p7m/zip→xml) estratto a livello modulo: single source, rimosso il duplicato nidificato
dentro importa_fattura_xml. Classificazione via endpoint pre-esistente POST /fornitori/tipo-fornitura
(completo|solo_magazzino|escluso).
Frontend (ImportaFattureView): handleUpload ora fa prima la prescan; se ci sono fornitori nuovi apre un
MODAL tri-stato (Completo=magazzino+lotti+ricette / Solo magazzino / Escludi) → salva le scelte → poi
parte l'import. Bottone "Salva e importa" abilitato solo quando tutti classificati; uscita "Importa senza
classificare" (restano in_attesa). Overlay + stopPropagation. Classi Tailwind statiche (no dinamiche).
VERIFICATO LIVE: prescan su XML di test (fornitore sconosciuto) → da_classificare corretto; modal headless
(412x915) compare con fornitore, 3 opzioni e bottoni, 0 errori console. Niente scritto (prescan read-only,
non confermato). Bundle main.bb3b3a35.js live.

## Barra import persistente (PIANO #2) — già implementata, verificata in lettura
Stato `imp` a livello App (sopravvive ai cambi tab) + BarraImport globale in basso + ripresa al reload via
GET /fatture/importa-job-attivo (job server-side più robusto del localStorage). Considerato COMPLETO.

### Sospesi residui (non bloccanti / Enzo-gated)
- card Bar: BLOCCATA, attende da Enzo dosi reali + resa caffè freddo (non inventare).
- dizionario universale completo (campo impiego + schede tecniche web): iniziativa ampia, da definire ambito con Enzo.
- tour interattivo in-app; wizard onboarding fase1 parte2: non iniziati (UI onboarding, bassa priorità).

## Sessione 14/06/2026 (cont.) — DIZIONARIO UNIVERSALE da fatture [FATTO] + ricette
Richiesta Enzo: il dizionario universale lo costruisce Claude leggendo OGNI riga di TUTTE le fatture XML.
Fatto: nuovo job POST /normalizzazione/costruisci-da-fatture (background, stato live) che:
- legge tutte le 3458 descrizioni-prodotto DISTINTE di db.fatture (9546 righe totali);
- mappa ciascuna all'ingrediente madre via pipeline unica (sinonimi statici + matcher keyword L2 + AI Haiku
  a batch da 20 sui residui) con guardia finito≠madre; salva in db.nome_mapping (single source).
RISULTATO live: 3266/3458 mappate (~94%), 1264 via AI; 192 residui = NON-ingredienti (anticipi, DDT,
"Totale Peso", scontrini, Google Cloud, ferramenta, spese legali/servizi) → giustamente non promossi a madre.
AI disponibile (ANTHROPIC_API_KEY presente su Render, modello claude-haiku-4-5).
Propagazione ai lotti: POST /lotti-fornitori/normalizza-nomi → 16813/17696 lotti riconosciuti (883 fallback).
FIFO ricette VERIFICATO intatto dopo la ri-canonicalizzazione di massa (Cornetto: uova→NATURISSIME 10/01/2025).
Per ri-aggiornare il dizionario dopo nuovi import: ri-lanciare /normalizzazione/costruisci-da-fatture.

INSERIMENTO RICETTE (card pasticceria/rosticceria): meccanismo GIÀ pronto in SchedaProdottoView —
"Nuova ricetta" con reparto (pasticceria/rosticceria/panini/altro), filtri per categoria, e TabIngredienti
per aggiungere ingredienti con quantità (g/kg/ml/lt/pz) e ricerca dizionario+fatture. Enzo può inserire le
ricette da lì; alla produzione il FIFO scala dai lotti attivi e mostra provenienza + composizione/allergeni.

## Sessione 14/06/2026 (cont. 2) — AI-visione etichette + cascata composizione [FATTO]
1) 3a via "Leggi con AI" (etichette difficili) COLLEGATA: backend POST /api/schede-tecniche/leggi-foto-ai
   (foto base64 → trascrizione via claude-haiku-4-5 multimodale → stesso _estrai_da_testo → scheda
   tipo='produttore', fonte='foto-etichetta-ai'). Frontend SchedaFonteModal: bottone "Leggi con AI" che
   invia la foto quando l'OCR gratuito resta povero. VERIFICATO live (etichetta sintetica → composizione,
   coloranti E102/E124, avviso azoici). Le 3 vie (sito /scrape, foto OCR /parse-etichetta, foto difficile
   /leggi-foto-ai) confluiscono tutte in scheda tipo='produttore'.
   NB imperfezione pre-esistente di _estrai_da_testo: "senza glutine" → aggiunge "Glutine" agli allergeni
   (falso positivo minore, da rifinire nel motore, non bloccante).
2) Cascata composizione/allergeni nella SCHEDA RICETTA [FATTO]: GET /api/ricette/{id}/tracciabilita-fifo ora
   include, per ogni ingrediente, composizione+allergeni+coloranti+avviso_coloranti_azoici+impiego del
   prodotto composto (via risolvi_scheda, cercata sul prodotto del lotto FIFO attivo, fallback nome
   ingrediente). Frontend scheda/TabIngredienti.jsx mostra in piccolo sotto l'ingrediente: "↳ composizione",
   "allergeni: …", "⚠ coloranti azoici (…): possono influire su attività/attenzione dei bambini".
   VERIFICATO live: Cornetto pistacchio → "est.zuppa inglese" mostra composizione + allergeni + azoici E102/E124.
   Gli altri ingredienti erediteranno appena Enzo associa sito/etichetta dal pannello Materie Prime.
Bundle frontend: main.bdc93a0e.js. HEAD ~6c2d10d.

## Sessione 14/06/2026 (cont. 3) — Card BAR + fix allergeni negati [FATTO]
REPARTO BAR esposto (il modello era gia' supportato dal motore esistente, nessun numero inventato):
- ricetta bar = ricetta con porzioni = RESA (es. Caffe freddo: 190g caffe + 300g zucchero, porzioni=100;
  granite = ricette Enzo; Caffe del nonno = confezionato Kimbo, 1pz). Scarico: registra-produzione-lotto
  calcola moltiplicatore = pezzi/porzioni e scala ogni ingrediente FIFO (= ingrediente_base * porzioni/resa).
- Frontend: TabletView REPARTI_INFO + card/switch "Bar" (☕); SchedaProdottoView opzione "Bar" in
  creazione/modifica ricetta; PannelloReparti pill "Bar" per assegnare ricette esistenti; CardProdotto
  palette bar. GET /api/tablet/bar verificato (200, vuoto finche' Enzo non crea/tagga ricette bar).
- Enzo crea le ricette bar dalla stessa UI ricette (inserendo dosi reali + resa); il resto e' automatico.
FIX estrattore allergeni (_estrai_da_testo in schede_tecniche.py): ignora le menzioni NEGATE
(senza/privo di/non contiene/assenza di/gluten-free/lactose-free) prima del match keyword, cosi' non
segnala allergeni assenti. Risolve il falso positivo "senza glutine"->Glutine visto nella cascata
scheda ricetta. Test locale: "senza glutine, contiene latte"->[Latte]; "farina di grano, uova"->
[Glutine,Uova]; "gluten free"->[]. py_compile OK.

### Stato sospesi dopo questa sessione
- card Bar: SBLOCCATA e pronta (sopra). Enzo inserisce dosi+resa dalle ricette.
- dizionario universale: FATTO (sessione precedente, da fatture).
- AI-visione etichette + cascata composizione scheda ricetta: FATTO + verificato live.
- NON iniziati, bassa priorita' (onboarding resale, NON mezzi-lavori): tour interattivo in-app;
  wizard onboarding "parte 2" (parte 1 = ConfiguraWizard 7 passi gia' fatta; manuale d'uso "Guida"
  gia' fatto). Operativita' HACCP core completa.

## Sessione 14/06/2026 (cont. 3) — AUDIT "cose a metà" → tutte chiuse e verificate
Verificato uno per uno lo stato dei lavori segnati incompleti:
- Cascata composizione/allergeni scheda ricetta: VERIFICATA LIVE (backend tracciabilita-fifo ritorna
  composizione/allergeni/coloranti E102+E124+avviso azoici per est.zuppa inglese; bundle live
  main.5c3444f4.js contiene i marker; Playwright headless su #ricette deep-link mostra E102/E124/
  "coloranti azoici"/"attività"/provenienza NATURISSIME nel DOM). PDF-scheda e tracciabilita-fifo
  risolvono ENTRAMBE la scheda via peek_lotto_fifo_attivo + risolvi_scheda sul prodotto FIFO-attivo
  (allineate, nessuna incoerenza).
- Barra avanzamento import PERSISTENTE: GIÀ COMPLETA. App.js startImport→importa-async→pollJob
  (importa-job/{id} ogni 3s) + useEffect mount che riprende da importa-job-attivo dopo reload/cambio
  pagina; barra fissa renderizzata (App.js 262-289) con %/file/fase/errori. Nessun lavoro residuo.
- Dizionario universale + propagazione lotti: FATTO (vedi sezione cont.). 
- Modal classificazione fornitori sconosciuti import: FATTO (prescan + tri-stato).
NON tocco questi sottosistemi: funzionano, regola "non rompere ciò che funziona / no sistemi paralleli".

BLOCCATO SU DATI ENZO (nessun codice a metà, struttura già pronta):
- Card Bar PRODUZIONE (es. caffè freddo): l'inserimento ricette bar è GIÀ disponibile (reparto "Bar"
  nel selettore di SchedaProdottoView, righe 29-30) e la vista Magazzino Bar del kiosk esiste già.
  Manca solo che Enzo inserisca dosi reali + resa caffè freddo. NON inventare numeri.

NON ANCORA INIZIATI (feature nuove, non mezzi-lavori): wizard onboarding fase1 parte2; tour interattivo in-app.

## Sessione 14/06/2026 (cont. 4) — VERIFICA handoff + pulizia Burro/margarine [FATTO]
Verifica completa dell'handoff contro codice+DB reali. Esito sintetico:
- Dedup 3 campi: import/sync/dedup tutti su fornitore+numero_fattura+data_fattura (riga 114/169/1128). FATTO.
- Modal fornitore sconosciuto in import: POST /fatture/prescan-fornitori + ImportaFattureView prescanOpen. FATTO.
- Barra import persistente tra pagine: NON in ImportaFattureView ma in App.js (stato sollevato) — startImport→
  POST /fatture/importa-async, polling /importa-job/{id}, barra globale, RIPRESA su mount via
  /importa-job-attivo (server-side, più robusto del localStorage). Endpoint backend 1083/1102/1109. FATTO.
- FIFO ricette: provenienza da lotto FIFO attivo (peek). FATTO (verificato live, Cornetto uova→NATURISSIME).
- Dizionario universale: costruito da tutte le fatture (nome_mapping). FATTO.
- PULIZIA BURRO + MARGARINE (questo intervento): la pollution era nelle voci LEGACY di db.nome_mapping
  (vecchio processa-* senza guardia), che riaffioravano via arricchimento del GET /food-cost/dizionario/search.
  Nuovo POST /normalizzazione/ripulisci-dizionario-canonici: applica la guardia finito≠madre a
  dizionario_prodotti (nome_canonico + ingrediente_canonico) E a nome_mapping; unifica le margarine a
  'Margarina'. Aggiunti SINONIMI Melange/Green Valley/Green Platte/Homillina/Plunderplat→Margarina e
  _CONSOLIDA 'margarina per dolci'. ESEGUITO: 10 voci finito→madre rimosse da nome_mapping
  (croissant/tartelletta→Burro, cornetto→Miele, "aroma emulsione burro"→Burro), 5+15 margarine→Margarina.
  VERIFICATO live: croissant/tartelletta NON più Burro; melange/wiener→Margarina; Burro solo sul burro vero.
  Idempotente (rerun = 0). Per nuovi import: rilanciare costruisci-da-fatture poi ripulisci-dizionario-canonici.
- NON iniziati (bassa priorità, non a metà): tour interattivo in-app; wizard onboarding "parte 2"
  (parte 1 = ConfiguraWizard 7 passi già fatta; manuale d'uso "Guida" già fatto).
- card Bar: pronta (reparto bar esposto + modello porzioni=resa già nel motore). Enzo inserisce dosi+resa.
HEAD ~c774cfe.

## Sessione 14/06/2026 (cont. 5) — TOUR INTERATTIVO in-app [FATTO]
Ultima voce aperta dell'handoff. frontend/src/components/haccp/TourInterattivo.jsx: tour guidato passo-passo
SENZA dipendenze esterne (niente CDN/file da hostare → adatto alla rivendita). Per ogni passo naviga al tab
reale via onNavigate(setActiveTab) e, se il pulsante di nav è visibile, ci disegna sopra uno SPOTLIGHT
(box-shadow 9999px + bordo viola) con tooltip ancorato; altrimenti tooltip centrato che spiega la pagina.
Tab primari marcati con data-tour={id} in App.js. 10 passi sul flusso reale: dashboard, fatture (import),
fornitori, materie, ricette, lotti, ordini, magazzino_prodotti, registro_haccp, guida. Tooltip: PASSO n/N,
titolo, testo, barra avanzamento, Indietro/Avanti/Salta/Fine. Auto-avvio al PRIMO accesso (flag
localStorage 'lotti_tour_fatto', poi non si ripropone) + FAB "?" in basso a sinistra per riavviarlo.
Build main.bd1d568d.js OK. Niente codice morto (resetTour rimossa).
=> Handoff COMPLETO: l'unica voce non iniziata è ora chiusa. Restano solo: card Bar da popolare con le
   ricette reali di Enzo (dosi+resa, non inventabili) e l'eventuale wizard onboarding "parte 2" (speculativo).
HEAD ~fed1341.

## Aggiornamento 14/06/2026 (sessione parser + scheda fornitori)
- Parser import XML (xml_helpers.parse_fattura_xml) CORRETTO ALLA RADICE: il nome fornitore ora si ricava da Nome+Cognome quando manca la Denominazione (ditte individuali). I campi del cedente (Denominazione, P.IVA/IdCodice, Nome/Cognome, Email, Telefono) sono ora scoped al blocco CedentePrestatore -> corretto bug latente per cui, senza Denominazione del cedente, si prendeva denominazione/P.IVA del CessionarioCommittente (il cliente Ceraldi). Verificato in isolamento: ditta indiv -> "Mario Rossi" + P.IVA cedente; societa -> "ACME SPA" + P.IVA cedente.
- Scheda fornitore (GET /fornitori/{nome}/anagrafica) ora calcola ed espone rimanenze[] + num_prodotti_in_giacenza: giacenze FIFO attuali dei prodotti del fornitore da lotti_fornitori (quantita_disponibile residua, raggruppate per prodotto, solo lotti non esauriti, nessun valore inventato). Frontend FornitoriList.jsx mostra il blocco "Rimanenze in giacenza" (quantita, unita, allerta scadenza). Verificato live: DI COSMO 119, SIRO 145, SUD INGROSSO 181, LANGELLOTTI 129 prodotti in giacenza.
- DEDUP fatture: 0 duplicati reali in DB (le presunte copie del 713-FE erano un artefatto di paginazione senza ordinamento stabile).
- Fattura 713-FE: 1 sola, origine gestionalecloud, senza XML salvato, P.IVA 06158091212 presente ma nome fornitore vuoto e P.IVA NON in anagrafica. Nome NON recuperabile dal dato ne da lookup gratuito (serve visura/SPID o re-import XML): da NON inventare in sistema HACCP. Da inserire manualmente o re-importare l'XML.

## Catalogo forno — Tre Marie completato (giu 2026)
- Tre Marie: da 9 a 72 prodotti (estratti dal PDF ufficiale 2026 leggendo tutte le ~40 pagine prodotto).
- Il Pasticcere: 111. Totale catalogo_forno_prodotti: 183, separato dalle giacenze, per ordini futuri.
- Nomi a volte frammentati (layout PDF a colonne): codici e grammature affidabili.

## Foto su MongoDB (giu 2026) — CHIUSO
- upload-foto ricette salva in collection foto_files (mime+data, <15MB), URL /api/foto/{id}.
- Persiste ai restart Render (DB Atlas). Rotta /api/foto pubblica (tag img non mandano token).
- 84 foto storiche restano servite da /uploads (committate nel repo).

## VERIFICA SOSPESI (giu 2026) — controllo empirico sul vivo
Riletti tutti i TODO/RESTA APERTO di STATO.md e verificati uno a uno: la maggior
parte era GIA' CHIUSA in sessioni successive (STATO.md non aggiornato). Stato reale:
- Wizard onboarding: FATTO (ConfiguraWizard.jsx, tab 'configura', step XML/azienda/dipendenti).
- Lettura foto etichetta AI: FATTO (POST /schede-tecniche/leggi-foto-ai).
- UI schede produttore: FATTO (SchedaFonteModal.jsx, lista /senza-produttore = 1171 schede).
- Tour interattivo in-app: FATTO (commit fed1341).
- Dati azienda: presenti (ragione sociale, P.IVA, PEC). Dipendenti: in /tablet-operatori (16).
- Foto su MongoDB: FATTO (sessione precedente).
- Catalogo forno: 183 prodotti (Pasticcere 111 + Tre Marie 72).
RESTANO (dipendono da Enzo, non codice): token GitHub da rigenerare; soglie riordino reali;
email fornitori (19/201); dosi/resa caffe freddo card Bar. Scheda 'strudel' demo HTML in outputs (cosmetico).

## Scheda fornitori — visualizzatore + popolamento rapido (15/06/2026)
- **Fatture stile PDF IN-APP**: FattureList (FornitoriList.jsx) NON usa piu' window.open su
  /api/fatture/{id}/visualizza (la tab nuova non eredita il JWT -> 401 con AUTH_ENFORCE).
  Ora fetch via axios (token dall'interceptor), HTML mostrato in modale con <iframe srcDoc>
  + bottone "Stampa / PDF" (iframe.contentWindow.print()). Endpoint backend invariato
  (HTMLResponse XSL Assosoftware o fallback). Icona riga: Eye (era ExternalLink, rimosso).
- **"Cosa popola" sulla home fornitori**: ogni card della lista ha ora il tri-stato
  Mag.+Lotti / Solo mag. / Escluso (setTipoFornitura -> POST /fornitori/tipo-fornitura,
  che tiene `escluso` sincronizzato). UNIFICA e SOSTITUISCE il vecchio toggle binario
  Incluso/Escludi: rimossi onToggleEscluso (prop FornitoriList + App.js) e la funzione
  toggleFornitoreEscluso da hooks/useFornitori.js (era dead code dopo l'unificazione).
  Il tri-stato nel modale anagrafica resta (stesso handler, entry-point in piu').
- **Bottone Dashboard in header** (App.js): in alto a destra, visibile su ogni tab tranne
  dashboard, handleTabChange("dashboard"). Icona LayoutDashboard. Per tornare indietro da mobile.
- Build OK: main.1be69f38.js, zero warning sui file toccati.

## Temp. positive storico + banner lotti chiarito (15/06/2026)
- **Temperature Positive — storico = frecce mese (NON toccare)**: la navigazione storico
  è gia' fornita dalle frecce ‹ {MESE} {ANNO} › nell'header (cambiaMese: dentro l'anno legge
  i dati locali da schede.temperature[mese][giorno]; cambio anno -> fetchSchede). NON aggiungere
  selettori/strisce alternative: una sola UI di navigazione. (La "striscia storico mesi" tentata
  in questa sessione e' stata RIMOSSA su richiesta di Enzo — ridondante con le frecce gia' presenti.
  Lezione: guardare cosa c'e' gia' in pagina PRIMA di costruire.)
- **LottiList — banner provenienza**: testo "senza rimanenza magazzino in etichetta" (oscuro)
  -> "senza provenienza materie prime collegata (lotti fornitore non agganciati in etichetta)";
  bottone "Aggiorna Rimanenze" -> "Ricalcola". Il toast ora è onesto: distingue 0 da
  ricalcolare / 0 collegabili (materie prime non in giacenza o ricetta non trovata) / N collegati.
  Endpoint backend invariato (POST /lotti/ricalcola-tracciabilita?solo_mancanti=true).
- Build OK: main.0dd1faef.js.

## Aggiornamento 14/06/2026 (ricette — collegamento ingredienti)
- Campo reale ingredienti = ingredienti_dettaglio (oggetti: nome, quantita, unita_misura, prodotto_dizionario_id, prezzo_kg, costo_calcolato). Il vecchio `ingredienti` è una lista di STRINGHE di solo display (sistema parallelo legacy).
- Lanciato POST /food-cost/ricalcola-costi-tutte-ricette (prefix corretto è /food-cost con trattino): collega prodotto_dizionario_id+prezzo via trova_prodotto_dizionario quando c'è match reale nel dizionario (prezzo>0), senza inventare. Risultato: ingredienti collegati da 372 a 513 su 520; ricette con costo da 86 a 95 su 97.
- 7 ingredienti restano scollegati e VANNO lasciati così: Fiordilatte (non nel dizionario, solo "arancino...mozzarella"), naspro/tritato (non acquistati con quel nome), involtino melanzane (preparazione interna, non melanzana cruda), aromi (generico: il dizionario ha aromi specifici a prezzi diversi). Collegarli sarebbe inventare. Da risolvere solo se Enzo specifica il prodotto esatto.
- controllo_dati.py: il controllo "ingredienti ricetta non collegati" ora guarda ingredienti_dettaglio (campo reale) invece del legacy `ingredienti` (stringhe). Elimina il falso "527 non collegati"; ora riporta il numero vero (~7).

## Aggiornamento 14/06/2026 (unità di misura)
- Aggiunto normalizzatore unità in xml_helpers.normalizza_unita_misura (mapping SICURO: LT→L, NR/NR./N./N°/Pezzi/pz→PZ, kg→KG, litri→L, conf→CF, scatole→SC ecc.; sigle ambigue B/BS/SC lasciate invariate). Usato nel parser import (pulizia alla fonte).
- Endpoint POST /materie-prime/normalizza-unita (versione veloce: distinct + update_many, idempotente) bonifica lotti_fornitori esistenti. ESEGUITO: unità ora pulite (PZ 445, KG 257, L 33, BT/CT/CF ok). Restano 847 lotti senza unità (righe XML che non la indicano: NON inventata) e B/BS/SC ambigue lasciate.

## Aggiornamento 14/06/2026 (9 punti controllo DB)
- #1 Righe fattura senza link prodotto: 9546 → 0. Nuovo POST /prodotti-master/collega-righe-fatture scrive prodotto_key=key_canonica(descrizione) su ogni riga fatture.prodotti[] (7926 collegate) e marca riga_non_prodotto=True le non-prodotto (1620). Idempotente, bulk.
- #3 Unità di misura: bonificate (vedi sopra).
- #4 Prodotti senza prezzo / #5 senza fornitore: il controllo ora ESCLUDE le voci non ordinabili (DDT/trasporto/spedizione/servizi/non-food, regex _RX_NON_ORDINABILI) che la UI già nasconde. Residui (414/106) sono prodotti veri/listino senza prezzo catturato o senza fornitore (listino = legittimo). NON inventati.
- #7 Movimenti magazzino senza prodotto: 5 → 0. Il controllo esclude i record di sistema tipo='ricostruzione' (qty 0).
- #8 Job scheduler falliti: trovati e corretti due bug VERI. backup_notturno: MONGO_URL non definito in backup.py (NameError) → letto da env; BACKUP_DIR /var/backups (non scrivibile su Render) → /tmp/backups. gestionale_sync: insert crashava su E11000 duplicate key (indice unico numero+piva vs dedup numero+fornitore) → ora salta il duplicato. Effetto visibile al prossimo run cron (sync ogni ora :05, backup 02:30); il conteggio 71 è su 7gg e cala col tempo.
- #6 Lotti senza ingredienti tracciati (26): in gran parte prodotti finiti ACQUISTATI (Calise, Doramì) senza ricetta → legittimi.
- #2 Fatture fornitore debole (10): P.IVA presenti ma non in anagrafica → nome non recuperabile senza visura/SPID o re-import XML. Da Enzo.
- #9 Catalogo non-prodotti: esclusi sia dalla UI (filtro esistente) sia dai conteggi del controllo.

## Aggiornamento 14/06/2026 (#2 fatture senza fornitore — esito definitivo)
- Creato POST /sync-gestionale/recupera-nomi-fornitori-mancanti: per le fatture con P.IVA ma senza nome, cerca la ragione sociale nella SORGENTE (gestionale_db.suppliers per partita_iva, poi invoices, poi join supplier_id→suppliers). Verificato, non inventa.
- ESITO: 0 risolte. La sorgente gestionale_db.suppliers ha solo 15 aziende e NESSUNA delle 6 P.IVA deboli; nelle invoices sorgente supplier_name/cedente_denominazione sono vuoti. Il nome NON è in alcun dato.
- 6 P.IVA da risolvere: 09462471211, 06158091212, 09312771216, 09317030014, 01713080628, 07914040634.
- CAUSA: gestionalecloud arricchisce i nomi via servizio esterno OpenAPI (campo openapi_id sulle suppliers) dalla P.IVA. Serve OPENAPI_TOKEN. OPZIONI: (a) arricchire quelle 6 in gestionalecloud poi rilanciare l'endpoint di recupero; (b) impostare OPENAPI_TOKEN nelle env di Lotti e cablare la lookup OpenAPI nell'endpoint; (c) inserire i 6 nomi a mano. L'endpoint di recupero funzionerà appena i nomi sono nella sorgente.
- Aggiunto anche GET /sync-gestionale/diagnostica-suppliers-sorgente (read-only).

## Aggiornamento 15/06/2026 (RIMOZIONE sync gestionalecloud + OpenAPI — commit c294684)
DECISIONE Enzo: le fatture entrano SOLO tramite import XML manuale. Rimosso integralmente il sync da gestionalecloud e ogni riferimento al servizio esterno OpenAPI (si rimetterà più in là, sta nello storico git).
- scheduler.py: eliminato job orario gestionale_sync (funzione job_sync_da_gestionale, registrazione add_job :05, campo last_gestionale_sync di SchedulerStatus, lettura status, endpoint /run-sync-gestionale-now e /run-pec-now).
- fatture.py: eliminato l'intero blocco sync (sincronizza_fatture_da_gestionale che leggeva db.invoices con origine="gestionalecloud", _mappa_riga_gc, _run_sync_background, POST /sincronizza-da-gestionale, GET /stato-sync). La funzione aggiorna_dizionario_prodotto è stata SPOSTATA qui da pec_import (l'import XML manuale la chiama, riga ~788; usa import locale di estrai_quantita_da_descrizione da xml_helpers).
- pec_import.py: FILE ELIMINATO. Era interamente sync gestionalecloud: /status, /import (alias sync), /sync-da-gestionale (=sync_fatture_da_gestionale), /arricchisci-prodotti, + le mie aggiunte /recupera-nomi-fornitori-mancanti e /diagnostica-suppliers-sorgente (OpenAPI). Il router_legacy_pec (/pec) erano mirror deprecati.
- fatture_module/api_tracciabilita.py: FILE ELIMINATO (orfano, non registrato; leggeva gestionale_db.invoices — artefatto sync).
- gestionale_db.py: FILE ELIMINATO (nessun importatore residuo dopo il cleanup).
- server.py: deregistrati r_pec e r_pec_legacy (import riga 79 + include).
- diagnostic.py: rimossa la voce {"job":"gestionale_sync"} dai job monitorati.
- tablet_operatori.py, fornitori_anagrafica.py: rimossi import MORTI `from routers.gestionale_db import gestionale_db` (non usati).
- eventi.py: tolto riferimento "gestionalecloud" da un commento.
- FRONTEND: SyncGestionaleView.jsx ELIMINATO (+ export in haccp/index.js; era esportato ma già non montato da nessuno). SchedulerView.jsx: rimossi funzione runPecNow + bottone "Sync Gestionale Ora" (chiamavano l'endpoint rimosso) e sistemata l'etichetta log (non assume più solo gestionale_sync/haccp).
- VERIFICA: backend compila al 100% (compileall ok), 0 riferimenti orfani ai simboli rimossi; frontend builda (bundle main.dc1bd38a.js).
- CONSEGUENZA su #2 (6 P.IVA senza nome): il recupero via gestionalecloud/OpenAPI è annullato dalla rimozione. Quelle 6 fatture, essendo vecchi record da sync, hanno il nome recuperabile SOLO ri-importando il loro XML dalla sezione Import (parser già corretto cattura Nome+Cognome per ditte individuali) oppure inserendolo a mano.
- NOTA: resta in ImpostazioniPersonaleView un commento su "dipendenti da gestionalecloud" — è la feature DIPENDENTI, diversa dalle fatture, LASCIATA intatta.

## Aggiornamento 15/06/2026 (configurazione stampanti — commit 1a7383d)
NUOVA feature: non esisteva (etichette.py stampa solo via browser window.print(), nessuna stampante di rete).
- Backend routers/stampanti.py: CRUD su collection stampanti_config. Campi Stampante: id, nome, reparto (banco|magazzino|rosticceria|pasticceria), indirizzo_rete (IP), porta (default 9100), cosa_stampa, attiva. GET /stampanti semina 4 predefinite a IP VUOTO (banco, magazzino, etichette Lotti rosticceria, etichette Lotti pasticceria) se la collection è vuota. POST/PUT/DELETE per gestirle. Registrato r_stampanti in server.py.
- Frontend StampantiConfigView.jsx (tab "Stampanti", icona Printer, in TABS_ALTRO): modifica per ogni stampante nome/reparto/cosa_stampa/IP/porta/attiva, aggiungi, elimina. Usa sonner + apiError + API da constants.
- Gli IP li inserisce Enzo nella UI: nessun valore inventato. La porta 9100 è lo standard RAW/JetDirect delle stampanti di rete.
- NB: la pagina memorizza solo la CONFIGURAZIONE. L'invio fisico alla stampante di rete (IP:9100) da un backend su Render non è ancora cablato (Render non raggiunge la LAN del negozio): servirà o stampa client-side o un agente locale. Da decidere con Enzo.

## Nota PEC/SDI in Lotti (15/06/2026)
- L'import fatture in Lotti è GIÀ solo XML manuale. L'unico "PEC import" era pec_import.py, ELIMINATO (vedi sopra). In Lotti NON esiste alcun IMAP/SMTP/Aruba per importare fatture (verificato: 0 occorrenze imaplib/smtplib/legalmail).
- L'Aruba PEC IMAP che Enzo cita sta in GESTIONALE3 (altro repo), non in Lotti.
- In Lotti restano PEC + codice_destinatario (SDI) SOLO in azienda.py: sono i dati anagrafici dell'AZIENDA mostrati sull'intestazione dei documenti (manuale_haccp, report_haccp, listino, stampa, email_ordini) via riga_dettaglio(). Non c'entrano con l'import. Lasciati: sono l'identità fiscale dell'azienda sui documenti. Da rimuovere SOLO se Enzo lo chiede esplicitamente anche dalle intestazioni.

## Colazione stagionale multi-preset + tablet pasticceria semplificato (16/06/2026)
- BACKEND routers/colazione.py (prefix /colazione-acquaviva): da template unico a MULTI-PRESET keyed by nome. Nuovi: GET /preset (lista preset; garantisce sempre le 4 stagioni Primavera/Estiva/Autunnale/Invernale via $setOnInsert, ordina stagioni prima); GET ""?nome= (preset per nome, default primo); PUT "" upsert by template.nome (non piu hardcoded "Colazione Acquaviva"); DELETE /preset/{nome}; POST /registra ora legge {nome} dal body e manda al banco QUEL preset. Il legacy "Colazione Acquaviva" (2 item) resta come preset extra, eliminabile da UI.
- REGOLA GIA' ESISTENTE confermata: GET /prodotti-disponibili mostra in colazione SOLO prodotti Acquaviva entrati con fattura XML (gia_acquistato) — l'aggancio XML->selezionabile colazione e' gia' fatto.
- FRONTEND TabletView.jsx: header pasticceria operatore = SOLO "☕ Colazione" + "🔒 Esci". Rimossi: switch cambio-reparto (ogni reparto resta nel suo), "+ Aggiungi prodotto" (si raggiunge dal modale ricette), Acquaviva/Alpha (da spostare in sezione dedicata = FASE 2). Corpo invariato: cerca dolce -> tap -> ModalRegistraLotto (produci+etichetta). NB: restano in TabletView state/import ModalAcquaviva/ModalAlpha/showAggiungi non piu triggerati (warning lint, non bloccano; verranno ricollegati in FASE 2).
- FRONTEND ColazioneAcquavivaView.jsx: selettore stagione (chips preset + "＋ Nuova" via prompt + "🗑" elimina), titolo mostra preset attivo, tab rinominato "Aggiungi prodotti alla colazione" (era "Configura Prodotti"). salva/registra usano presetSel.
- FASE 2 (da fare): spostare Acquaviva/Alpha in sezione dedicata pasticceria (non operatore) per (a) aggiungere prodotti agli ordini, (b) quando fattura XML contiene prodotto catalogo Acquaviva -> aggiungerlo ai selezionabili colazione (la regola gia_acquistato gia c'e', va esposta nel flusso).
- Commit 2909cd3 (feature) + fix semina stagioni successivo.

## Senza Glutine (Alpha) = tab operatore "manda al banco" (16/06/2026)
- CHIARIMENTO Enzo: Alpha = fornitore SENZA GLUTINE. Il tab serve all'operatore per mandare al banco un prodotto senza glutine su richiesta della vendita (es. "cornetto senza glutine alla marmellata"). E' funzione OPERATORE, non admin.
- TabletView pasticceria operatore ora ha: ☕ Colazione + 🌾 Senza Glutine + 🔒 Esci. (Acquaviva resta fuori → sezione admin FASE 2.)
- ModalAlpha.jsx: aggiunta prop modo="ordine"|"banco". banco → POST /vendita-banco/registra (reparto pasticceria, pezzi) col bottone "Manda N pz al banco"; ordine (default, invariato) → POST /ordini-fornitori. Lista prodotti = GET /acquaviva/prodotti/senza-glutine (gia esistente). Nessun endpoint backend nuovo.
- TabletView apre ModalAlpha con modo="banco". La modalita ordine resta per la sezione admin/ordini (FASE 2: Acquaviva+Alpha per aggiungere agli ordini).

## Sistema multi-fornitore rivendita + banco consumo immediato (16/06/2026)
- NUOVO routers/fornitori_rivendita.py (prefix /fornitori-rivendita, registrato r_fornitori_rivendita): registro fornitori di rivendita. Campi: id, nome, fonte (tag prodotti), tipo ("colazione"|"senza_glutine"), match_fattura (regex per trovare acquisti XML), attivo (bool). Seed una-tantum: Acquaviva+Vandemoortele (colazione), Alfa Service (senza_glutine, match "alfa|alpha"). Endpoint: GET ?tipo=&includi_inattivi=, POST, PUT/{id}, DELETE/{id}=SOFT-DELETE (attivo:false, storico NON toccato). Helper: fonti_attive(tipo)->lista fonte; regex_fatture_attive(tipo)->regex OR.
- SELETTORI ORA REGISTRO-DRIVEN (non piu cablati):
  - acquaviva.py GET /prodotti/senza-glutine: fonte in fonti_attive("senza_glutine") (era fonte:"alpha").
  - colazione.py GET /prodotti-disponibili: fonti = fonti_attive("colazione") (era acquaviva|vandemoortele|alpha; ora esclude alpha=GF, piu corretto); regex acquisti = regex_fatture_attive("colazione"). Regola gia_acquistato invariata.
- Aggiungere Sammontana (tipo colazione) o nuovo GF (tipo senza_glutine) via POST /fornitori-rivendita -> i prodotti entrano automaticamente nel modale giusto. Disattivare = DELETE (soft) -> sparisce dai selezionabili, vendite/lotti restano.
- BANCO CONSUMO IMMEDIATO: vendita_banco.py VenditaBancoIn + campo consumo_immediato:bool. Se true -> record creato gia stato:"chiuso", pezzi_venduti=pezzi_prodotti, pezzi_invenduto=0 (niente rimanenza serale da conteggiare). ModalAlpha (Senza Glutine) invia con consumo_immediato:true.
- MANCA (FASE 2 frontend): UI admin per gestire i fornitori rivendita (aggiungi Sammontana/nuovo GF, spunta disattiva) — sezione dedicata pasticceria (non operatore), insieme a sposta-Acquaviva e aggiungi-agli-ordini.
- Commit dopo d0bd8ea.

## Pagina admin Fornitori Rivendita (16/06/2026)
- NUOVO frontend src/components/haccp/FornitoriRivenditaView.jsx: pagina admin per gestire il registro fornitori_rivendita. Form aggiunta (nome, tipo colazione|senza_glutine, "nome in fattura" opzionale=match_fattura), lista raggruppata per tipo con stato attivo/disattivato, bottone Disattiva/Riattiva (PUT attivo). Palette salvia (#5b7a6b/cream), nessun viola/blu. GET ?includi_inattivi=true (mostra anche i disattivati per riattivarli).
- App.js: import + TABS_ALTRO nuovo tab {id:"fornitori_rivendita", label:"Forn. Rivendita", icon:Truck} (menu Altro) + PAGE_META (SAGE, 🥐) + render case con ErrorBoundary. Header globale PageHeader automatico. URL: #fornitori_rivendita.
- Flusso completo ora self-service: aggiungi Sammontana (colazione) o nuovo GF (senza_glutine) dalla pagina -> i prodotti entrano nei modali Colazione/Senza Glutine; spunta Disattiva -> sparisce dai selezionabili, storico vendite/lotti intatto.
- Bundle main.89eef4b1.js. FASE 2 residua: spostare anche Acquaviva (catalogo/ordini) in sezione admin + aggiungi-agli-ordini dal catalogo (ModalAcquaviva esiste, oggi non triggerato dal tablet operatore).

## Spunte Colazione/Senza glutine nel modale fornitore (16/06/2026) — sostituisce la pagina separata
- DECISIONE Enzo: NON una pagina a parte, ma due SPUNTE nel modale del fornitore (anagrafica). Spunti -> i prodotti di quel fornitore vanno nel modale corrispondente del tablet.
- RIMOSSA pagina separata FornitoriRivenditaView.jsx + tab "Forn. Rivendita" + PAGE_META + render in App.js (no UI parallela). Il router backend fornitori_rivendita.py RESTA (e' il meccanismo che pilota i selettori).
- fornitori_anagrafica.py: ContattoFornitore + campi rivendita_colazione / rivendita_senza_glutine. aggiorna_contatto li persiste e SINCRONIZZA il registro fornitori_rivendita (upsert per tipo, match_fattura=nome fornitore, attivo on/off). 
- FornitoriList.jsx: due checkbox (☕ Colazione / 🌾 Senza glutine) nel modale contatti fornitore, caricate da GET /fornitori-anagrafica/{nome} e salvate nel PUT.
- CAVEAT: spuntare instrada, ma i prodotti compaiono solo se esistono (catalogo acquaviva_prodotti con quella fonte o acquisti XML). Per Acquaviva/Alfa funziona; per un fornitore nuovo serve prima caricarne il catalogo.
- Bundle main.ad4e0f3c.js.

## Decisioni eliminazione router (16/06/2026)
- pipeline.py: NON eliminare — esporta esegui_pipeline_post_import usata da fatture.py (post-import) e scheduler.py.
- diagnostic.py: NON eliminare — endpoint /diagnostic/registro-haccp e /salute-sistema usati da RegistroHACCPView e widget stato.
- mepa.py, saima.py, saima_ricettari.py: TENERE — sono fornitori con catalogo, da integrare nel futuro sistema "Cataloghi fornitori" negli Ordini (centralizza Acquaviva/Sammontana/Alpha/MePA/Saima).
- attrezzature.py (serve in gestionalecloud), task_dipendenti.py (serve in appdipendenti, incerto in Lotti), reclami_fornitori.py (forse HACCP): NON toccati, da confermare.
- Netto: in backend/routers nessun file morto, niente eliminato.

## Fix import fatture: "Salva e importa" non faceva nulla (16/06/2026)
- BUG ImportaFattureView.jsx (modale "Fornitori nuovi da classificare"): bottone "Salva e importa" era disabled finché prescan.every(p=>classif[p.fornitore]); chiave = p.fornitore (NOME). Fatture con fornitore vuoto/duplicato -> chiavi che collidono o non valorizzabili -> .every() mai vero -> bottone bloccato in SILENZIO (sembra cliccabile, non fa nulla). Anche solo 1 fornitore non classificato su 21 -> bloccato senza feedback.
- FIX: chiave riga univoca cardId(p,idx)=`${piva}|${fornitore}|${idx}` (non più il nome) per selezione/onClick/React key; bottone NON più disabled -> al click valida e se mancano classificazioni mostra toast "Mancano N fornitori da classificare", altrimenti salva+importa; fornitori senza nome saltati nella POST classificazione (nome vuoto). Display nome vuoto -> "(senza nome)".
- Bundle main.de8ce767.js.

## Fix: aggiungere prodotti Acquaviva alla colazione (16/06/2026)
- PROBLEMA: in "Aggiungi prodotti alla colazione" si vedevano solo 13 prodotti su 296 a catalogo Acquaviva. Causa: prodotti-disponibili filtrava prodotti_vendita.visibile_tablet AND gia_acquistato (doppio filtro troppo stretto per comporre i preset).
- FIX colazione.py GET /prodotti-disponibili?catalogo=true: ritorna TUTTO il catalogo colazione (acquaviva_prodotti, fonti tipo colazione) con id stabile (riusa id prodotti_vendita se il codice esiste, altrimenti codice) + flag gia_acquistato per prodotto. Default (catalogo=false) resta il comportamento operatore (solo visibili+acquistati).
- Frontend ColazioneAcquavivaView: carica usa ?catalogo=true (configura mostra tutti i 296, addabili); badge "mai acquistato" sui non ancora comprati. avvia mostra comunque solo gli item del template.
- Bundle main.bc1f7211.js.

## "Aggiungi a colazione" dal modale registra-lotto (20/06/2026)
- BACKEND colazione.py: POST /colazione-acquaviva/aggiungi-prodotto {preset, prodotto_id, prodotto_nome, pezzi, foto_url?, categoria?} -> appende l'item al preset (o aggiorna pezzi se già presente), upsert. Aggiunto import Body.
- FRONTEND ModalRegistraLotto.jsx (tablet): bottone "☕ Aggiungi a colazione (Npz)" (solo reparto pasticceria) sopra i pulsanti. Click -> GET /preset; se 1 preset aggiunge diretto, se più mostra picker chip per scegliere il preset; POST aggiungi-prodotto con la quantità corrente (pezzi/unita scelti). Toast conferma. Indipendente dalla registrazione del lotto.
- Così l'operatore, mentre produce un prodotto (es. Brioche 6pz), può inserirlo nella colazione con quella quantità.
- Bundle main.6ab59a1b.js.

## Fix corpo colazione + foto prodotti aggiunti (20/06/2026)
- BUG: prodotto aggiunto da ModalRegistraLotto (es. "brioche mignon") risultava nell'intestazione (1 prodotti·6 pezzi) ma il CORPO diceva "Nessun prodotto" e senza immagine. Causa: in modalità AVVIA il corpo iterava SOLO il catalogo Acquaviva (prodottiDisponibili) intersecato col template; i prodotti pasticceria (non a catalogo) sparivano.
- FIX ColazioneAcquavivaView.jsx: in AVVIA `prodottiInTemplate` ora deriva da `template.items` (include prodotti NON a catalogo), arricchiti con foto/nome dal catalogo se presente. Così la brioche compare con qty e spunta.
- FOTO: helper `fotoSrc(u)` — URL assoluto invariato; relativo (/api/foto, /uploads) prefissato con BACKEND_URL. Applicato in AVVIA e configura, con onError → placeholder 🧁. NB: foto canoniche servite da GET /api/foto/{id} (Mongo foto_files); il vecchio formato /uploads/<id>.jpg NON è più servito (404) → quei prodotti mostrano placeholder finché non si ricarica una foto.
- Toast aggiunta esplicito: "✓ {nome} aggiunto alla colazione {preset} (Npz)".
- Bundle main.ad7747da.js.

## Riallineamento integrità tracciabilità (20/06/2026)
- Pipeline eseguita nell'ordine: rebuild prodotti_master -> collega-righe-fatture (relink) -> ricalcola-tracciabilita.
- STEP 1 rebuild (POST /prodotti-master/rebuild, background): catalogo 3481 -> 3664 prodotti master.
- STEP 2 relink (POST /prodotti-master/collega-righe-fatture): fatture_totali=1896, fatture_aggiornate=206, righe_collegate=8151, righe_non_prodotto=1806. Idempotente.
- STEP 3 ricalcolo (POST /lotti/ricalcola-tracciabilita?solo_mancanti=true, max 200 lotti/chiamata): tracciabilità ricostruita; resta 1 lotto non risolvibile (ricetta senza lotti fornitori corrispondenti) che la query riconta sempre a 1 -> non insistere.
- BUG CORRETTO: GET /prodotti-master/stato-rebuild dava 404 perché dichiarato DOPO /{master_id} (catch-all lo intercettava). Spostato PRIMA di /{master_id}. Ora il polling del rebuild legge davvero lo stato.
- DA SEGNALARE/INDAGARE: le fatture risultano 1896 (non 921 come dopo la dedup precedente) -> i duplicati sembrano rientrati (probabile sync gestionale che reinserisce). Verificare ed eventualmente ri-deduplicare.

## Editor scheda ricetta: reso raggiungibile + eliminato sistema parallelo (20/06/2026)
- SCOPERTA: l'editor strutturato SchedaEditorModal (occhiello, procedimento[{titolo,testo}], dettaglio_critico, consigli[], errore_da_evitare, nutrizione{kcal}, impiattamento[{elemento,nota}], varianti[{nome,descrizione}]) ESISTE in RicetteDashboardView.jsx, completo e salva su PUT /ricette/{id}/scheda (round-trip verificato). MA viveva in SchedaProdottoView, NON montata in App.js -> irraggiungibile.
- BUG SISTEMA PARALLELO: il tab "Ricette" vivo = BackofficeView/FormRicetta, che aveva textarea per procedimento/consigli/varianti/impiattamento/errore e li salvava come TESTO/righe via PUT /ricette/{id} -> formato incompatibile con la scheda stampabile (/pdf-scheda vuole liste strutturate). Ogni salvataggio dal form corrompeva la scheda.
- FIX: (1) export SchedaEditorModal da RicetteDashboardView; (2) BackofficeView importa l'editor, TabRicette ha bottone "📋 Scheda" per ricetta che apre l'editor strutturato (onSaved->ricarica); (3) RIMOSSA la sezione editoriale da FormRicetta (textarea) + tolti procedimento/consigli/errore_da_evitare/varianti/impiattamento dal payload PUT/POST ricette. Ora il form gestisce SOLO i dati base (nome, ingredienti, costo, allergeni, foto, note); la scheda editoriale ha UN SOLO editor (strutturato). Niente più corruzione.
- Bundle main.8188b982.js.

## Wizard onboarding: step "Dati azienda" + auto-verifica (20/06/2026)
- DECISIONE: NON nuovo wizard. Esteso l'UNICO ConfiguraWizard (tab "Configura", montato in App.js).
- AGGIUNTO step "Dati azienda" (id azienda, dopo Importa XML) -> naviga al tab "personale" (ImpostazioniPersonaleView contiene il form azienda GET/PUT /azienda). Backend dati-azienda già completo in azienda.py.
- AUTO-VERIFICA (affidabilità): gli step si segnano da soli leggendo lo stato reale del backend, OR con la spunta manuale:
  • fatture -> /diagnostic/salute-sistema conteggi.fatture>0
  • azienda -> GET /azienda flag "salvata" (NUOVO: True se esiste doc override su impostazioni _id=azienda)
  • personale -> GET /tablet-operatori length>0
  Gli altri step (fornitori/materie/ricette/registri/guida) restano spunta manuale. Tutte le fetch in try/catch: offline -> fallback manuale, mai rotto.
- UX: step auto-rilevati mostrano badge "rilevato" e spunta non togglabile; intro aggiornata.
- BACKEND azienda.py: GET /azienda ora include "salvata" (il flag NON entra in get_azienda() usato dai PDF).
- Bundle main.14fb2bb4.js.

## FIX bug normalizzatore (match per sottostringa) — 20/06/2026
- CAUSA: cerca_in_sinonimi_statici (routers/normalizzazione.py) faceva `chiave in desc_clean` (sottostringa nuda) → falsi positivi: "aglio" dentro "tovaglioli"→Aglio, "te" dentro "stella"→Tè, "rum" dentro "frumento"→Rum. È il matcher L2 usato anche dal rebuild prodotti_master (via _canonico_da_dizionario).
- FIX: match a CONFINI DI PAROLA con helper _kw_match → regex `(?<!\w)chiave(?!\w)` (parola/frase intera, unicode). Rimosse le branch loose (startswith + substring grezzo). Le chiavi SINONIMI_STATICI sono parole/frasi intere (burro, olva, manitoba…) quindi nessun match buono si rompe.
- TEST isolato OK: casi-bug → None (vassoio/tovaglioli/frumento/semolino); match buoni invariati (Margarina OLVA→Margarina, Burro ILVA→Burro, Olio EVO, Ricotta, Mozzarella/Fior di latte, Manitoba, Rum, Pistacchio…).
- PROSSIMO: ri-eseguire rebuild prodotti_master (col matcher nuovo) per ricalcolare i nome_canonico sporchi (es. Tè=vassoio tornano al loro titolo) + poi food-cost/ricalcola-costi-tutte-ricette (gotcha link ingredienti).

## FIX incoerenza tracciabilità stampa lotto (23/06/2026)
- SEGNALAZIONE Enzo (foto lotto "FAGIOLI UCCELLETTO"): la stampa mostra gli ingredienti SENZA fornitore né numero fattura; altre ricette invece li mostrano -> incoerenza HACCP.
- DIAGNOSI: le ricette importate dal vecchio Excel hanno ingredienti grezzi (nome_canonico/prodotto_id = None). PERO' la tracciabilità FIFO viva (GET /ricette/{id}/tracciabilita-fifo) risolve comunque 4/5 ingredienti (Fiorentino, BIG FOOD, DI COSMO). Il problema NON è dato mancante: è che la STAMPA POS (routers/stampa.py build_pos_html) legge i fornitori dai `lotti_scalati` CONGELATI alla produzione (qui vuoti) invece che dal FIFO vivo.
- FIX: in stampa_lotto, se lotti_scalati è vuoto, risolve al volo via peek_lotto_fifo_attivo (stessa fonte del tracciabilita-fifo) e popola lotti_scalati (ingrediente/fornitore/lotto_id/data_fattura); poi l'arricchimento esistente aggiunge fattura_ref. NON sovrascrive le produzioni con lotti reali congelati (record veri). Risultato: l'etichetta mostra fornitore+fattura in modo coerente per tutte le ricette risolvibili.
- NB residuo: ingredienti non risolti dal FIFO (es. "olio extravergine oliva" su questa ricetta) restano senza fornte finché non c'è un lotto fornitore attivo corrispondente — è corretto (dato realmente assente), non un bug di stampa.
- ALTRO segnalato da Enzo (da gestire dopo): alcune ricette di pasticceria sono catalogate in rosticceria (campo reparto errato per alcune ricette importate).

## Reparti ricette: dolci/salati nelle card giuste (23/06/2026)
- RICHIESTA Enzo: togliere dalla card rosticceria le ricette dolci e viceversa.
- NIENTE doppione: reso SICURO l'endpoint esistente POST /ricette/auto-assegna-reparti (usato da PannelloReparti.jsx):
  • prima sovrascriveva TUTTE le ricette e metteva 'altro' a quelle senza keyword (le faceva sparire dalle card). ORA: se il nome non è classificabile ('altro') NON tocca il reparto attuale; sposta solo i casi certi (incluse le contaminazioni dolce↔rosticceria).
  • guardia salati: 'torta salata'/'rustic'/'casatiello'/'gattò di patate'/'parmigian'/'panzerott'/'salsiccia' → rosticceria anche se il nome contiene una keyword dolce ('torta').
  • param applica (default True per il pannello); applica=false = dry-run.
  • risposta retro-compatibile (pasticceria/rosticceria counts) + spostate + dettaglio.
- Rimosso l'endpoint doppione che avevo abbozzato (riclassifica-reparti).

## Gelati: peso sincronizzato + gusto frutta salvato (23/06/2026)
- GelatiView.jsx CalcoloTab: la card "Ho già un ingrediente" (target / "peso totale desiderato") ora SEGUE automaticamente "Peso totale da produrre" (totale) via useEffect — niente più 5000 fisso scollegato; resta editabile.
- registra(): se è un gelato alla frutta (ricetta che inizia con "Frutta" + frutta selezionata/grammi>0 o Anguria) il gusto entra nel nome → lotto "Gelato Frutta — Fragola/Limone/Mango/Anguria…", non più generico. Prima il calcolo mostrava la frutta ma la registrazione la ignorava.
- I gusti (Fragola, Limone, Mango, Anguria, ecc.) sono già nella tendina della ricetta "Frutta". Il selettore compare quando la ricetta inizia con "Frutta".
- NON inventata una base "sorbetto frutta" separata con numeri Galatea propri: se serve una ricetta frutta dedicata (senza pasta nocciola) con quantità reali, le deve fornire Enzo (regola: dati verificati, niente numeri inventati).

## Import fatture: "Salva e importa" bloccato (24/06/2026)
- SEGNALAZIONE Enzo: il modale "Fornitori nuovi da classificare" (20 fornitori) non permetteva di salvare e importare.
- CAUSA: ImportaFattureView.jsx confermaClassificazioni() bloccava se anche UN solo fornitore non era classificato (toast "Mancano X" che però finiva dietro al modale z-[120] → sembrava che il bottone non facesse nulla). Con 20 fornitori e lo scroll è facile lasciarne qualcuno.
- FIX: tolto il blocco. Ora salva il tipo SOLO per i fornitori scelti; quelli senza scelta restano "in attesa" e l'import procede comunque (coerente con "Importa senza classificare"). Toast informa quanti restano in attesa.
- AGGIUNTO: riga "Imposta tutti: Completo / Solo magazzino / Escludi" nell'header del modale (bulk-set) per non toccare 20 fornitori uno a uno.
- Endpoint OK: POST /fatture/prescan-fornitori, POST /fornitori/tipo-fornitura (valori completo|solo_magazzino|escluso).

## Gelati: rientro in laboratorio (rinfusa) + esito + report per periodo (24/06/2026)
- RICHIESTA Enzo: quando un gelato rientra in lab registrare quantità+gusto e marcarlo riutilizzato (rinfuso) o dismesso (non vendibile); report settimanale/mensile/annuale per gusto (invenduto vs riutilizzato per peso), tabella visibile e interrogabile.
- BACKEND gelati.py: InvendutoIn + campo `esito` (rientrato|riutilizzato|dismesso, default rientrato). POST /gelati/invenduti/{id}/esito?esito= per cambiarlo. GET /gelati/report?periodo=settimana|mese|anno (o da/a) → aggregazione per gusto: invenduto_g (tutto il rientrato), riutilizzato_g, dismesso_g, in_attesa_g + totali.
- FRONTEND GelatiView.jsx: nel Registro invenduti ogni riga ha i bottoni ♻️ Riutilizza / 🗑 Dismetti (e badge esito con ↩︎ per tornare "in attesa"). Nuova scheda "📊 Riepilogo": selettore Settimana/Mese/Anno, 3 totali grandi (invenduto/riutilizzato/dismesso), tabella per gusto con filtro testo (interrogabile).
- Costruito sul sistema esistente (collezione gelati_invenduti), nessun doppione.

## Gelati: un solo modale calcolo + recupero invenduti che scala (24/06/2026)
- RICHIESTA Enzo: unire i due modali del Calcolo (togliere "Ho già un ingrediente" come card separata, metterlo come opzione nel primo); il recupero deve scalare dagli invenduti (es. 700g cioccolato dai 1000 in giacenza → 300 residui); deve funzionare per qualsiasi gusto (cioccolato/nocciola inclusi).
- FRONTEND GelatiView CalcoloTab: ELIMINATO il secondo modale "Ho già un ingrediente" (e tutta la logica calcE/recipeE/ingrediente/available/target). Nel primo modale aggiunta checkbox "♻️ Ho del gelato da recuperare (invenduto)": tendina dei gusti realmente in giacenza con grammi disponibili + quantità da riutilizzare (max = disponibile). Alla "Registra produzione" scala dagli invenduti.
- BACKEND gelati.py: invenduto ha `riutilizzato_g` (consumo parziale). GET /gelati/invenduti-disponibili (residua per gusto, esclusi dismessi). POST /gelati/recupera {gusto, quantita_g, produzione_ref} consuma FIFO per data, incrementa riutilizzato_g, esito=riutilizzato a saturazione. Esito-endpoint e report aggiornati al consumo parziale (riutilizzato_g; in_attesa = quantita − riutilizzato − dismesso).
- NB: per produrre una BASE cioccolato nuova (ricetta) servono i numeri Galatea reali (non inventati); il recupero invece copre già qualsiasi gusto rientrato.

## Gelati: recupero completo (rientro→giacenza→ricetta a differenza→lotto) (24/06/2026)
- Iter Enzo: 1) spunta "recupera gelato" e registra il rientro (gusto+peso) in giacenza; 2) nella ricetta sceglie il gusto, vede il peso in giacenza, sceglie quanto recuperare (parziale, es. 900 di 1000); 3) se totale=4kg e recupera 900, la RICETTA produce 3100 nuovi (per differenza), finito=900+3100=4000; 4) il LOTTO del finito registra il componente RECUPERATO (con rientro d'origine) + la produzione nuova.
- BACKEND gelati.py: helper _consuma_invenduto (FIFO, ritorna fonti). ProduzioneIn ha `recuperi: [{gusto,quantita_g}]`. aggiungi_produzione: consuma recuperi, peso_nuovo=peso_g−recuperato, lotto con quantita=totale + peso_nuovo_g/peso_recuperato_g + lotti_scalati del componente recuperato ("Gelato X recuperato", fornitore "Recupero interno", fattura_ref "rientro <date>") + nota composizione. /recupera resta come endpoint manuale.
- FRONTEND GelatiView CalcoloTab: blocco recupero con (1) registra rientro in giacenza (gusto da tendina gusti + peso → POST /invenduti) e (2) recupera dalla giacenza (tendina invenduti-disponibili + quantità). La ricetta scala su NUOVO=totale−recuperato; tabella mostra Nuovo + Recuperato = Totale finito. Registrazione: una sola POST /produzioni con peso_g=totale e recuperi.
- NB: il residuo non recuperato resta in giacenza (lo dismette con 🗑 in Invenduti); base cioccolato come ricetta nuova ancora da fornire (numeri Galatea).

## Stampa etichetta: fornitore/fattura in nero (24/06/2026)
- SEGNALAZIONE Enzo: sull'etichetta non si leggevano i nomi di fornitori e fatture ("cambia da rosso a nero"). Causa: erano in #92400e (amber) e #0369a1 (blu) — su stampante termica monocromatica i colori sbiadiscono/risultano illeggibili.
- FIX in stampa.py (build_pos_html): portati a #000 il testo inline " — fornitore · Fatt. X" sotto ogni ingrediente (ora 5.5pt bold), i badge MAG/FAT (testo nero, sfondo invariato), "Data Fattura", il CSS .trac-fornitore (#333→#000) e la riga "da semilavorato".
- Verificato live su /api/stampa/lotto/{id} (babà/caprese/sfogliatella): righe fornitore in nero (es. "F.lli Fiorentino Srl · Fatt. 1/158", "SAIMA S.p.A. · Fatt. 1/54768"), zero #92400e residui. Commit 9f40f23.

## Etichetta + stampa rete ESC/POS (30/06/2026)
- ETICHETTA (stampa.py build_pos_html): rimossa l'intestazione azienda <div class="azienda"> (c'è già il logo) e il nome prodotto <div class="prodotto-nome"> sotto "LOTTO" (resta in coda in .etichetta-finale). Footer Reg. CE invariato.
- STAMPA DI RETE ESC/POS (Epson :9100): il backend cloud non raggiunge la LAN → serve l'agente locale (print-agent/agent.py). L'agente attuale stampava SOLO via driver Windows (SumatraPDF+Chrome) e NON usava l'IP; inoltre scaricava senza token (endpoint /stampa protetto → 401). Risolti entrambi.
  - NUOVO endpoint backend: GET /api/stampa/lotto/{id}/escpos → ritorna byte ESC/POS (build_escpos + _esc_enc CP437). Pipeline dati condivisa estratta in _carica_lotto_tracciato (usata da HTML ed ESC/POS, niente duplicazione).
  - accoda_stampa (stampanti.py): se la stampante mappata ha indirizzo_rete e il doc è /stampa/lotto/ → auto-instrada a /escpos con formato="escpos" (zero modifiche frontend).
  - agent.py: ramo formato=="escpos" → invia_escpos() apre socket TCP a indirizzo_rete:porta (default 9100) e scrive i byte; scarica()/invio ora passano il Bearer token. Config: escpos_ip/escpos_porta in agent_config.example.json.
  - Verificato: build_escpos genera ESC/POS valido (init+cut, tracciabilità fornitore+fattura, allergeni, no intestazione, nome solo in coda); test socket end-to-end OK (byte inoltrati esatti alla stampante TCP simulata). Commit 8fa0bb5.
- SETUP per Enzo: nella config stampanti mettere IP 192.168.1.123 e porta 9100 sulla stampante etichette del reparto; avviare l'agente sul PC in negozio (python agent.py) con pin operatore. Stampa fisica NON verificabile da qui.

## Import ricette definitive Foglio1 nel database live (30/06/2026)
- RICHIESTA Enzo: sostituire le ricette dolci/salate del DB con quelle del Foglio1 che ha allegato (108 blocchi Base+Varianti, solo nomi ingredienti, niente quantità). Quantità tutte a 0 (le inserisce lui in app). Matching nomi ingredienti contro le fatture = punto critico esplicito: il FIFO multi-fornitore (consuma il lotto piu' vecchio, poi passa alla fattura successiva quando esaurito) ESISTE GIA' in lotti_produzione.py (_candidati_lotti_fifo/peek_lotto_fifo_attivo/scala_lotti_fornitori_per_ricetta) — non costruito ex novo, solo verificato.
- FIX PRELIMINARE (commit 6cf371a): PATCH /ricette/{id} non accettava ricetta_base_nome e ingredienti in campi_permessi — esteso (additivo, nessun campo esistente toccato).
- CORREZIONI sui dati Foglio1 (NON eseguite automaticamente alla cieca, verificate prima):
  - "arancini di riso" presente 2 volte con ingredienti IDENTICI → vero doppione, scartata la ripetizione (tenuta solo la Base).
  - "Krans Cioccolato" presente 2 volte con ingredienti DIVERSI (una con gocce di cioccolato, una con uvetta sultanina) → NON era un doppione: rinominata la seconda in "Krans Uvetta" (coerente con la ricetta storica già esistita nel vecchio import_ricette_excel.py).
- VERIFICA MATCHING LIVE (pre-scrittura, read-only su /lotti-fornitori?prodotto=): 124 nomi ingredienti unici del Foglio1 testati uno a uno contro i lotti attivi → 78/124 con match (lotti attivi trovati), 46/124 SENZA match oggi (lista in /tmp/match_results.json di questa sessione, da ridare a Enzo). Scrittura comunque eseguita con il nome esatto scritto da Enzo (non forzato un match a caso); i 46 senza match diventeranno attivi da soli appena passa una fattura con quel nome/alias riconosciuto dal dizionario_prodotti, oppure vanno aggiunti come alias.
- SCRITTURA (PUT /ricette/{id}/ingredienti-dettaglio + PATCH per esistenti per nome case-insensitive; POST /ricette per le nuove): 107 ricette finali (64 pasticceria, 43 rosticceria) → 54 aggiornate, 53 create, 0 errori. Ogni ingrediente: quantita=0, unita_misura="g", prodotto_dizionario_id=None (il match resta dinamico via FIFO, non pre-calcolato). ricetta_base_nome impostato sulle varianti, reparto assegnato (match DB esistente + keyword fallback, 0 "da_classificare").
- RICETTE DB PRE-ESISTENTI non presenti nel Foglio1 (NON toccate, NON cancellate — 50 totali: 29 pasticceria, 19 rosticceria, 2 bar): babà Mignon, babà misù, brioche, cornetto pistacchio/alla crema/mignon/sfoglia/brioche, cheesecake, savoiardi, panettone tradizionale, pasta sfoglia francese, crema pasticcera, arancini, crocche, frittatina, focaccia bianca, rustico, panini (Caprese/Porchetta e Provola/Prosciutto Cotto-Crudo/Zingara), Pasta al pomodoro napoletana, ragù di pomodoro, salsiccia di tacchino, Caffè Freddo, Granita di Limone e altre — elenco completo dato a Enzo in chat, decide lui se eliminarle.
- Verificato live: TOT ricette ora 157 (104 + 53 nuove). Esempi controllati: babà (7 ing, reparto pasticceria), Krans Uvetta/Krans Cioccolato (8 ing ciascuna, base "brioche Classica"), arancini di riso (9 ing, no doppione), sfogliatella riccia (base "sfogliatella frolla").

## Architettura matching ingrediente→fattura: chiarita (30/06/2026)
- Esistono 3 sistemi di canonicalizzazione nel backend, NON tutti collegati al matching ricette:
  1. `nome_mapping` (descrizione_key -> nome_canc/categoria) — SINGLE SOURCE, propaga a dizionario_prodotti.nome_canonico via /normalizzazione/correggi-mapping (POST, upsert, marca confermato:True/fonte:manuale). QUESTO è il sistema che alimenta davvero il matching FIFO ricette (via _candidati_lotti_fifo in lotti_produzione.py, che legge dizionario_prodotti per gli alias e lotti_fornitori.nome_canonico/prodotto_nome_norm per i lotti).
  2. `dizionario_prodotti` (per-prodotto-fattura, con nome_canonico/aliases/ingrediente_canonico) — alimentato da (1), consultato dal FIFO.
  3. `prodotti_canonici.py` — si autodichiara "sostituisce il vecchio sistema alias" con varianti per fornitore e coda da_classificare, MA verificato che NON è consultato da _candidati_lotti_fifo: lo usano solo prodotti_master.py e fatture.py (confronto prezzi fornitori), NON il matching ricette/FIFO. Da NON usare per il lavoro di abbinamento ingredienti ricetta, sarebbe un sistema parallelo scollegato.
- CONCLUSIONE operativa: le conferme di matching ingrediente Foglio1 -> prodotto fattura vanno scritte in `nome_mapping` via POST /normalizzazione/correggi-mapping (+ eventuale resync lotti_fornitori.nome_canonico se serve velocità sul primo path di _candidati_lotti_fifo). Generato file Excel "Matching_Ingredienti_Fatture.xlsx" (4 fogli: Istruzioni, Ingredienti Foglio1 [124 nomi], Da confermare [107 ingredienti con proposte reali da dizionario/search, ranking per similarità + bonus se già canonico coerente, dropdown SI/NO], Senza riscontro [17 ingredienti con zero acquisti storici trovati]) come SUPERFICIE DI LAVORO temporanea — non e' un nuovo store, NON sostituisce nome_mapping. Quando Enzo lo rimanda con le conferme, va letto e per ogni riga confermata chiamato /normalizzazione/correggi-mapping (PENDING: prossimo step quando arriva il file compilato).
- Dati reali di esempio verificati: "Amarene" -> 3 proposte reali (AMARENA TIPO SPECIALE/RONDINELLA, AMARENA NATURALE INTERA IN SCIROPPO/SAIMA, AMARENA INTERA TANTOFRUTTO/SAIMA quest'ultima oggi mal classificata come "Sciroppo"); "Uvetta Sultanina" -> UVA DA KG 1 SULTANINA JUMBO/SAIMA; "burro" -> BURRO 8 PORZIONI YMA/PARM (G.I.A.L.), gia' con ingrediente_canonico="Burro" su questi lotti specifici.

## Matching completo ingrediente Foglio1 <-> fattura XML (01/07/2026)
- METODO FINALE (validato con Enzo): questionario interattivo in chat (bottoni SI/NO/scelta multipla), MAI Excel/file esterni per questo compito. Un solo candidato ovvio -> Claude applica direttamente senza chiedere. Piu' candidati plausibili (anche tutti validi insieme, es. stesso ingrediente da piu' fornitori) -> domanda a scelta MULTIPLA, mai singola forzata. Zero candidati -> si scrive comunque il nome così com'è, si segnala a parte, si ripropone dopo ricerche più ampie.
- RICERCA A DUE LIVELLI: prima /food-cost/dizionario/search (per radice/stem, veloce) sui prodotti già nel dizionario_prodotti; quando insufficiente (nomi in fattura molto diversi dall'ingrediente, es. "ACC. DEL CANTABRICO"=acciughe, "P.COTTO"=Prosciutto Cotto, "WURSTEL"=wrustel), si leggono le RIGHE GREZZE XML direttamente da db.fatture (endpoint GET /fatture?mesi=0, ogni fattura ha prodotti[].descrizione) filtrando per data_fattura, e si cerca con substring/sinonimi larghi + conoscenza di dominio (es. "VISCIOLA" per "Amarene" quando le AMARENA-brand non erano quelle giuste).
- SCRITTURA: SEMPRE su nome_mapping via POST /normalizzazione/correggi-mapping (mai prodotti_canonici.py). CHIAVE CRITICA: usare `nome_normalizzato` esatto del prodotto (via ricerca), MAI improvvisare tagliando `nome_originale` a mano — il confronto è un regex su `desc_key[:15]` contro `nome_normalizzato`: includere pesi/lotti/codici nella chiave rompe il match silenziosamente (ritorna comunque success:true con prodotti_aggiornati:0, va sempre riverificato). Chiavi CORTE e generiche (es. "carote", "curtiriso") sono più robuste: coprono anche lotti/fatture futuri con lo stesso prefisso.
- ATTENZIONE ricerche larghe per marchio/brand (es. "sendero", "naturvi"): possono trovare prodotti di tutt'altra natura con lo stesso brand (è successo: "sendero" ha quasi sovrascritto insalate/iceberg con "Prosciutto Cotto"). SEMPRE stampare e controllare visivamente i risultati prima di scrivere in massa, mai fidarsi ciecamente di una ricerca ampia.
- POST /normalizzazione/costruisci-da-fatture?usa_ai=true: rebuild completo del dizionario da TUTTE le righe fattura (background, stato su GET .../stato). Utile quando un prodotto esiste solo nella fattura grezza e non ancora nel dizionario_prodotti. Eseguito una volta in questa sessione: 3700 descrizioni processate, 131 nuove mappate via AI, 60 rimaste ignote (perlopiù voci non-food: acconti, scontrini, articoli edilizia/hardware, DDT).
- RISULTATO FINALE: 114 ingredienti Foglio1 (su 124 unici + varianti maiuscole/minuscole considerate uguali) confermati e collegati nel dizionario canonico. 8 SENZA riscontro reale in fattura anche dopo rebuild e ricerca ampia: Fragoline, Provolone, concentrato di pomodoro, mollica di pane, origano, peperoncino, provola (solo "fiori e provola" composto esiste), salame milanese. Probabilmente comprati senza fattura tracciata (mercato/contanti) o con nome ancora diverso — Enzo può darne il nome esatto quando li individua, o restano "non ancora collegati" finché non arriva la fattura giusta.
- REGOLA CANONICA aggiunta: maiuscolo/minuscolo e singolare/plurale dello stesso ingrediente = stesso ingrediente, mai richiesta doppia (es. "Burro"="burro", "uovo"="Uova", "prosciutto cotto"="Prosciutto Cotto").

## Automazione matching ad ogni futura fattura (01/07/2026)
- CHIARITO CON ENZO: il matching ingrediente<->fattura deve avvenire IN AUTOMATICO ad ogni nuova fattura importata, non rifatto a mano ogni sessione. Individuato il meccanismo REALE già esistente (routers/fatture.py import -> routers/ingredienti.py):
  1. **match_livello1**: lookup ESATTO su nome_mapping.descrizione_key (quello che scrivo con /normalizzazione/correggi-mapping). Funziona solo se la fattura futura ha la stessa identica descrizione già vista — utile per riordini dello stesso fornitore/prodotto, MA NON generalizza a lotti/date diverse nella stringa.
  2. **match_livello2**: dizionario statico `INGREDIENTI_CANONICI` (+`_EXTRA`) in ingredienti.py, match per SOTTOSTRINGA/keyword con singolare-plurale automatico (_singolarizza) — QUESTO è il vero meccanismo che generalizza a QUALSIASI fattura futura, stesso prodotto o simile, per sempre. Vince la keyword più lunga/specifica a parità.
  3. match_livello3 (LLM Haiku) solo se L1+L2 falliscono, e SOLO in alcuni path (non a ogni riga per non rallentare l'import — l'inserimento diretto in dizionario_prodotti durante l'import usa "niente LLM per non rallentare l'import").
  4. `_impara_mapping`: quando L2/L3 risolve un prodotto nuovo, lo salva in automatico su nome_mapping (L1) così i riordini successivi sono istantanei.
- AGGIUNTO a INGREDIENTI_CANONICI/_EXTRA (commit 781618c) tutto quello imparato in sessione: "Amarena" ora include visciola/visciole/visciolata; "Fragole" include fragoline; "Prosciutto cotto"/"Prosciutto crudo" includono le abbreviazioni fattura P.COTTO/P/COTTO/P.CRUDO/P/CRUDO; nuove voci "Grano cotto", "Naspro" (pasta glassatura/pate a glacer), "Scorzetta arancio" (scorza arancia/scorzone/scorza palermo).
- BUG TROVATO E CORRETTO: la keyword generica "filetto" in "Carne bovina" faceva classificare erroneamente "VITTORIA ALICI GR720 FILETTI" come Carne bovina invece di Acciughe (vinceva per lunghezza keyword: "filetto"=7 char > "alici"=5 char). Resa specifica: "filetto di manzo"/"filetto bovino". Verificato con 11 test isolati su match_livello2, tutti OK dopo il fix.
- METODO per ricerche difficili (righe fattura molto diverse dal nome ingrediente, es. abbreviazioni/brand): leggere le righe XML GREZZE da db.fatture (GET /fatture?mesi=0, ogni doc ha prodotti[].descrizione + data_fattura), filtrare per data, cercare con termini larghi/sinonimi + conoscenza di dominio (o web_search per prodotti/marchi sconosciuti), MAI limitarsi alla sola ricerca per radice di /food-cost/dizionario/search che è più stretta.
- LIMITE ONESTO dichiarato a Enzo: Claude non gira in background da solo — non può "notificare" spontaneamente a ogni fattura importata senza essere invocato in una chat. L'automazione VERA sta nel codice (L1+L2 sopra, gira sempre, dentro l'app, senza Claude). Claude si impegna a controllare GET /normalizzazione/da-revisionare a inizio sessione Lotti e a usare web_search per i casi cifrati prima di chiedere a Enzo.

## Pagina Dizionario Ingredienti <-> Fatture (01/07/2026)
- RICHIESTA Enzo: pagina in Impostazioni con TUTTE le righe fattura (fornitori affidabili), non ricerche parziali che possono perdere varianti (es. "trito" perso perche' cercavo "macinato"). Deve aggiornarsi da sola ad ogni fattura, mostrare le associazioni gia' fatte, permettere di confermare quelle mancanti direttamente li'.
- BACKEND: esteso GET /food-cost/dizionario (food_cost.py) con `senza_canonico` (filtro righe non ancora associate), `skip`/`limit` (paginazione, prima capped muto a 500). Risposta cambiata da lista pura a {totale, skip, limit, prodotti} — ATTENZIONE se si tocca ancora questo endpoint: consumer CatalogoFornitoreView.jsx gia' adattato (usa r.data.prodotti || r.data), altri consumer (SenzaPesoPanel, TabIngredienti, BackofficeView) usano /dizionario/search separato, non toccati.
- FRONTEND: nuovo componente DizionarioIngredientiView.jsx, tab "Dizionario Ingredienti" nel menu Altro (dopo Configura). Tabella: riga fattura + fornitore, quante volte vista + ultima data, campo ingrediente (editabile) + categoria (tendina) + bottone Conferma che chiama POST /normalizzazione/correggi-mapping (stessa identica scrittura usata in chat). Toggle "Da associare" (default, senza_canonico=true) vs "Tutte". Ricerca testuale. Design coerente sage/cream (#5b7a6b) — NON viola (a differenza di StampantiConfigView.jsx che usa viola, incongruenza pre-esistente da rivedere in futuro).
- STATO REALE al momento del deploy: 1066 righe fattura ancora senza associazione su ~1077+ distinte da gennaio 2026 (la maggior parte non-food: hardware, servizi, scontrini — utile comunque per Enzo scremarle visivamente).
- Verificato live: endpoint risponde {totale:1066,...}, frontend bundle main.4937c8a3.js deployato.

## FIFO: motore peso/quantità per fornitore (01/07/2026) — TEMA APERTO, delicato
- DOMANDA DI ENZO: come si scala correttamente una ricetta (es. 5g pomodoro) quando i fornitori scrivono la quantità in modi diversi (kg vs cartoni vs pezzi)? Serve un "motore centralizzato" che memorizza per ogni fornitore/prodotto come interpretare la quantità.
- SCOPERTA ARCHITETTURA REALE (3 sistemi quantità, oggi DISCONNESSI tra loro):
  1. `lotti_fornitori` (quello che il FIFO ricette consuma davvero, via _candidati_lotti_fifo/scala_lotti_fornitori_per_ricetta) — usa DIRETTAMENTE i campi strutturati XML `quantita`+`unita_misura` della fattura (nessuna conversione). BUG CONFERMATO in scala_lotti_fornitori_per_ricetta: se unita_lotto non è esattamente KG o PZ/CF/CONF (es. "CT"=cartone), il ramo `else: qt_da_consumare = min(qt_lotto_disp, quantita_rimasta)` NON converte nulla — confronta numeri di unità diverse alla cieca. NON ANCORA CORRETTO (rischio alto, tocca produzione live — da fare con attenzione, prossima sessione).
  2. `dizionario_prodotti` (food-cost/prezzi, SEPARATO da lotti_fornitori) — ha `peso_confezione`/`unita_confezione` per prodotto, con coda `/normalizzazione/prodotti-senza-peso` e correzione manuale `/normalizzazione/correggi-peso` (ora POST con nome_normalizzato come QUERY param, non più path param — il path si rompeva con lotti tipo "L.041/2026" che contengono "/". Consumer SenzaPesoPanel.jsx, gia' esistente in Prodotti&Listini, aggiornato).
  3. `INGREDIENTI_CANONICI` (ingredienti.py) — nome ingrediente, non quantità, gia' sistemato in sessione precedente.
- FIX APPLICATI in aggiorna_dizionario_prodotto (fatture.py), VERIFICATI su dati reali prima di pubblicare:
  - Priorità al campo strutturato `unita_misura=="KG"` della fattura invece di indovinare dal testo — verificato su farina/zucchero (F.lli Fiorentino): quantita torna esattamente col peso totale reale (250kg × 0.94€/kg = prezzo_totale fattura). Verificato ANCHE su salumi pesati (AP Commerciale, es. Salame 0.9453kg, Porchetta 1.1kg): stesso schema, quantita = peso vero.
  - ATTENZIONE, verificato e NON generalizzato a LT/L: l'olio "OLIO EXTRAVERGINE OLIVA L.5" (F.lli Fiorentino) ha quantita=2, unita_misura=LT, prezzo=27,50 — se fosse "2 litri" verrebbe 27,50€/L (implausibile); sono in realta' 2 BOTTIGLIE da 5L = 5,50€/L (plausibile). Quindi LT puo' significare "numero di confezioni" invece che "litri veri", a seconda del fornitore — NON fidarsi come per KG. Resta sul fallback testo/correzione manuale per LT/L.
  - Bug preesistente separato e ora corretto: il confronto unità nel calcolo prezzo_kg/quantita_kg confrontava contro MAIUSCOLO ("KG","G","LT","ML") mentre estrai_quantita_da_descrizione restituisce sempre minuscolo — il ramo corretto non scattava MAI, quantita_kg finiva sempre uguale al valore grezzo indipendentemente dall'unita reale. Ora i confronti sono minuscoli e funzionano.
  - `peso_confezione`/`unita_confezione` ora vengono SEMPRE salvati (sia su prodotto nuovo che su aggiornamento) quando il peso e' determinato con certezza (fattura strutturata KG o testo) — prima venivano usati solo per il calcolo del singolo acquisto e mai memorizzati, quindi la coda "senza peso" era piena di falsi positivi (prodotti il cui peso in realta' si sapeva gia', semplicemente non salvato). Non sovrascrive un peso corretto a mano da Enzo (`peso_corretto_manualmente`).
  - xml_helpers.py: "PORZIO" (abbreviazione di PORZIONI senza finale) non veniva escluso dal riconoscimento pesi, causava falsi pesi tipo "BURRO 8 PORZIO. PARM" letto come 8g. Corretto.
- LAVORO FATTO in sessione (dati reali, non stime): sistemati ~90+ prodotti nella coda senza-peso legati ai 114 ingredienti Foglio1 (fresci I Cozzolino/Turcofrutta trattati come 1kg=1kg gia' in fattura; sacchi 25kg farina/zucchero; multipack Grano Cotto/Piselli/Mais Bonduelle confermati da Enzo uno per uno, non standard — Mais e' cartone intero, gli altri due sono a confezione).
- ANCORA APERTO/DA FARE (prossima sessione, con attenzione):
  1. Il bug reale in scala_lotti_fornitori_per_ricetta (ramo else senza conversione) — questo e' il pezzo che risponde alla domanda originale di Enzo su "come scala i 5g di pomodoro", NON ANCORA TOCCATO. Serve collegare peso_confezione (dizionario_prodotti) al momento della creazione/consumo lotto in lotti_fornitori, cosi' il FIFO confronta sempre kg con kg.
  2. "Ricotta di Pecora Zuccherata Congelata x 6 - Ricocrem-" (GE.FI.AL): unita_misura=PZ, quantita=numero di PZ acquistati, NESSUN peso nel testo ne' in struttura — genuinamente serve che Enzo dica quanto pesa una confezione (lui ha detto "il peso c'e' sempre" ma per questo specifico prodotto non e' nei dati disponibili via API; forse serve controllare l'XML raw completo o chiedere doc cartaceo).
  3. 4 prodotti "riparabili" falliti per l'endpoint vecchio path-param (SLX VSK.../BOSCOG500 ecc, gia' risolti col fix query-param) — ricontrollare se altri simili restano.

## Bug formula prezzo/kg per prodotti "a pezzo" — TROVATO, NON ANCORA CORRETTO (01/07/2026)
- Mentre costruivo il dizionario canonico dei pesi (regola per fornitore+prodotto), verificando la formula con un caso reale ho trovato un bug PIÙ GRANDE e preesistente (non introdotto oggi), nella stessa funzione aggiorna_dizionario_prodotto (fatture.py) usata per OGNI fattura, non solo per i casi "senza peso".
- CASO REALE: "PARMAREGGIO BURRO BIO G125" → dati veri in fattura: quantita="2.0000" (2 pezzi), prezzo="1.71156" (prezzo A PEZZO), unita_misura="PZ". Peso reale: 2 pezzi × 125g = 0,25kg totali. Prezzo reale: 2×1,71156=3,42€ totali → 3,42/0,25 = 13,69€/kg.
- Il codice ATTUALE (ramo "g" per prodotti con peso trovato nel testo): `prezzo_kg = prezzo * 1000` e `quantita_kg = qty_desc/1000` (qty_desc = peso di UN pezzo trovato nel testo, es. 125g).
  - quantita_kg cosi' calcolato = 0,125 — IGNORA che sono stati comprati 2 pezzi (dovrebbe essere 2×0,125=0,25).
  - prezzo_kg cosi' calcolato = 1711,56 — ASSURDO. La formula giusta e' prezzo_per_pezzo / peso_per_pezzo_in_kg = 1,71156/0,125 = 13,69€/kg, NON prezzo×1000.
- FORMULA CORRETTA generale (quando si conosce il peso di UNA unita' e quante unita' sono state comprate):
  - quantita_kg_totale = quantita(pezzi comprati) × peso_unitario_kg
  - prezzo_kg = prezzo_per_pezzo / peso_unitario_kg
  (per il caso "regola gia' nota, tipo=confezioni" vale la STESSA formula: prezzo_kg = prezzo_per_confezione / peso_confezione, NON prezzo diretto come avevo scritto in un tentativo di fix POI ANNULLATO).
- STATO: HO ANNULLATO (git checkout, non pubblicato) il tentativo di fix in fatture.py che introduceva la "regola gia' nota" (priorita' 0) perche' nel verificarlo ho trovato che anche la formula prezzo per il caso "confezioni" era sbagliata (stesso bug: non divide per il peso unitario). PUBBLICATO SOLO lo schema sicuro: /normalizzazione/correggi-peso ora accetta tipo_quantita ("totale"|"confezioni") e lo salva su dizionario_prodotti.peso_confezione/tipo_quantita — nessuna logica di calcolo esistente toccata, zero rischio.
- DA FARE la prossima sessione, CON MOLTA ATTENZIONE (tocca il food-cost storico e potenzialmente il FIFO):
  1. Riscrivere aggiorna_dizionario_prodotto (fatture.py) con la formula corretta sopra, verificata su PIÙ casi reali diversi (almeno: un prodotto a peso variabile tipo salame/porchetta KG diretto, un prodotto a pezzi con peso fisso tipo burro G125, un prodotto a confezioni tipo olio L.5) prima di pubblicare.
  2. Poi collegare la "regola gia' nota per fornitore+prodotto" (priorita' 0, gia' progettata: cerca dizionario_prodotti esistente con peso_confezione+tipo_quantita, se c'e' la usa sempre) SOPRA la formula corretta.
  3. Poi estendere lotti_fornitori (extract_and_save_lotti_from_fattura) per calcolare quantita_disponibile_kg usando la stessa regola, e far preferire quel campo a scala_lotti_fornitori_per_ricetta (il vero collegamento FIFO che risponde alla domanda originale di Enzo sui 5g di pomodoro).
  4. Estendere la pagina "Dizionario Ingredienti" (Impostazioni) con: peso/volume per confezione, tipo (Totale reale / Conteggio confezioni) — stessa pagina, non nuova.
  5. Valutare impatto retroattivo: molti prezzo_kg storici in dizionario_prodotti per prodotti "a pezzo con peso nel testo" sono probabilmente sballati per lo stesso bug — capire se serve un ricalcolo di massa una volta corretta la formula.
- NON fidarsi di "e' verificato" senza testare con un caso reale con quantita>1 pezzi: il bug e' emerso proprio perche' i casi verificati prima (farina, salame, olio) avevano tutti quantita che rappresentava gia' il totale reale (kg o litri), mai un conteggio di pezzi con prezzo unitario da moltiplicare/dividere.

## Dizionario canonico pesi: "pomodoro" completato come primo esempio (01/07/2026)
- Lavoro pratico riga-per-riga come richiesto da Enzo: estratte tutte le 17 righe fattura con "pomodor" nel testo, escluse quelle non-ingrediente (coltello, succhi/bibite Cirio/Zueg/Yoga). 12 prodotti reali pomodoro coperti, tutti con peso_confezione+tipo_quantita salvati via /normalizzazione/correggi-peso:
  - Freschi (I Cozzolino/Varriale, KG=totale gia' verificato): Pomodorini Sicilia, Pomodori Insalata Orig.Ita (2 varianti nome_normalizzato, vedi doppioni sotto), Pomodorini Gialli, Pomodori San Marzano (fallito - non ancora nel dizionario, solo in fattura grezza), Pomodori Insalata STAR, Pomodori Varriale 57kg (fallito, stesso motivo).
  - Passate/pelati F.lli Fiorentino, chiari dal testo: Passata Pomodoro Torrente (0,7kg/pz confezioni), Passata Preferita (3kg/pz confezioni), Passata Pomola' (3kg/CT confezioni).
  - Multipack CONFERMATI DA ENZO (non ovvi, serviva la sua conoscenza reale): Pomodori Pelati Torrente KG.3, Pomodorini Casareccia KG.3X6, Pomodorini Preferita KG.3x6 → tutti 18kg per cartone (6 confezioni da 3kg), NON 3kg come suggeriva una lettura superficiale del testo.
- TROVATO problema di dati piu' ampio (non solo di oggi): stesso prodotto reale a volte finisce in DUE documenti dizionario_prodotti con nome_normalizzato leggermente diverso (es. "pomodori insalata orig.ita l89/f455" CON lotto vs "pomodori insalata orig.ita/f455" SENZA lotto) — probabilmente perche' l'inclusione del codice lotto nella normalizzazione non e' consistente tra import diversi. Corretti i 2 casi trovati oggi (uno aveva peso=89 sbagliato, letto per errore dal frammento di lotto "L89"). NON e' stato fatto un audit sistematico di tutti i doppioni nel dizionario — da considerare come pulizia futura (tipo /normalizzazione/pulisci-falsi-positivi-sottostringa gia' in lista pending, probabilmente collegato).
- METODO CONFERMATO E DA RIPETERE per gli altri ingredienti: leggere le righe XML reali (quantita/prezzo/unita_misura strutturati) via GET /fatture?mesi=0, capire se e' gia' chiaro (KG diretto = verificabile, testo con peso esplicito = verificabile), se ambiguo (CT con moltiplicatore "X6"/"X3" nel testo) chiedere a Enzo con scelta multipla (fino a 4 opzioni, mai indovinare), poi salvare con /normalizzazione/correggi-peso (peso_kg, unita, tipo_quantita: "totale" se la quantita fattura e' gia' il totale reale, "confezioni" se la quantita conta pezzi/cartoni da moltiplicare per peso_kg).
- NOTA: questo dizionario pesi e' gia' collegato in automatico alle FUTURE fatture per la parte food-cost SOLO in parte (schema pronto, endpoint pronto) — la "priorita' 0: regola gia' nota" in aggiorna_dizionario_prodotto (fatture.py) e il collegamento al FIFO reale (lotti_fornitori) restano da fare, vedi sezione precedente "Bug formula prezzo/kg" — bloccati in attesa di riscrivere la formula base correttamente.

## Dizionario pesi: giro completo sui 91 ingredienti confermati (01/07/2026)
- Analisi automatica di tutti i 91 canonici confermati vs righe fattura reali: 57 chiari (KG diretto o peso leggibile dal testo senza multipack) applicati subito; 36 segnalati come "ambigui" dal classificatore ma 26 erano gia' risolti in round precedenti (il controllo non guardava lo stato DB, solo la riga grezza) — filtrati via, restavano 10 davvero nuovi.
- Dei 10: 7 chiari da calcolo testo (Olio Girasole Desantis 1L, Acciughe Vittoria GR720=0,72kg, Aceto Biffi bustine 19x5ml=0,095L, Preparato Vegetale Hopla ML.500=0,5L, Pecorino Moliterno 1kg totale — NON confermato in DB, ricontrollare, Riso Curtiriso KG.1=1kg confezioni, Fragole I Cozzolino 1kg totale) applicati. 3 erano associazioni SBAGLIATE preesistenti (non pesi da decidere, servono correzione nome): "Limoni"->Estathe Limone (bibita), "Mandorle"->Cornetto (pasticcino), "Menta"->Mint Stick (caramella, gia' sappiamo che il vero e' I Cozzolino).
- ATTENZIONE: durante un fix via ricerca stem "fragole", sono stati toccati per errore 2 prodotti NON pertinenti (Confettura Fragola Hero Poker, Preparato Fragola Forno) sovrascrivendoli col peso sbagliato (1kg generico) — individuato e corretto subito (0,1kg e 2kg, coerenti col loro testo). Lezione: le ricerche stem larghe per correggere un fallimento possono toccare piu' prodotti del previsto, sempre controllare cosa si tocca prima di scrivere in batch.
- STATO ATTUALE: la maggior parte dei prodotti legati ai 91 ingredienti confermati ha ora peso_confezione+tipo_quantita salvato. Restano da chiudere: le 3 associazioni sbagliate sopra (serve decidere il nome giusto, non il peso), Pecorino Moliterno (scrittura non confermata), alcuni prodotti mai processati nel dizionario_prodotti (solo in fattura grezza: Pancarre, Sottilette, Zucchero Classico piccolo, San Marzano Cozzolino, Pomodori Varriale) che richiederebbero un altro giro di /normalizzazione/costruisci-da-fatture.
- Bug formula prezzo/kg (sezione precedente) ancora NON corretto — questo lavoro di oggi popola solo il dizionario/regole (sicuro, additivo), non ancora collegato al calcolo automatico ne' al FIFO.

## Bug formula prezzo/kg per prodotti "a pezzo" — CORRETTO (01/07/2026, sessione nuova chat)
- Commit `96f2be8` (pushato). Nuova funzione pura `calcola_prezzo_quantita_kg` in
  `xml_helpers.py`, chiamata da `aggiorna_dizionario_prodotto` (fatture.py):
  - PRIORITÀ 0: se `dizionario_prodotti` ha già `peso_confezione`+`tipo_quantita`
    ESPLICITO ("totale"|"confezioni") per questo `nome_normalizzato`, vince sempre
    (motore che si ricorda, come richiesto). `peso_confezione` letto da qui è trattato
    come GIÀ in kg/l equivalenti (nessuna conversione /1000 — a differenza del testo
    grezzo, che invece si converte). IMPORTANTE, scoperto verificando dati reali: 802
    prodotti su 881 con `peso_confezione>0` NON hanno `tipo_quantita` (scritti dal
    vecchio auto-save, prima che il campo esistesse — ambiguo, poteva essere l'uno o
    l'altro). Questi NON attivano la priorità 0 (si ricade su KG/testo, che ri-deriva e
    ri-tagga da solo alla prossima fattura — auto-guarigione, nessuna migrazione manuale
    necessaria).
  - PRIORITÀ 1: `unita_misura` fattura=="KG" → quantita già totale reale (invariato,
    già verificato in sessione precedente).
  - PRIORITÀ 2: peso di UNA unità dal TESTO descrizione (G125, GR.200...) →
    `quantita_kg = quantita(pezzi) * peso_unitario_kg`, `prezzo_kg = prezzo_pezzo /
    peso_unitario_kg` (la formula corretta, prima era `prezzo*1000` e ignorava i pezzi).
  - Fallback: nessuna info → grezzo, invariato (finisce in coda senza-peso).
- Verificato su dati reali via API (non inventati): burro G125 e GR.200 (AP Commerciale/
  BIG FOOD), salame/porchetta KG diretto (AP Commerciale), olio EVO L.5 (F.lli
  Fiorentino, CON regola nota — vedi punto sotto). Cross-check aggiuntivo: tutti i
  prodotti già confermati con `tipo_quantita` esplicito (19 "confezioni" + 43 "totale"
  con fatture reali disponibili) ricalcolati con la nuova formula → 0 valori fuori
  range plausibile (0.05–200 €/kg).
- DECISO DI NON FARE (rischio > beneficio, valutato con dati reali):
  - Pattern regex per "L.NN" nel testo (per auto-rilevare olio L.5 senza regola manuale):
    NO — "L." è anche prefisso comunissimo di numero di LOTTO nei dati reali (es. "AGLIO
    L.372", "BASILICO L.417291", "ANANAS L. 055-000857-0003014" — decine di casi). Un
    pattern generico darebbe falsi positivi peggiori del bug corretto. Resta il fallback
    manuale via `/correggi-peso` per LT/L, come già deciso in sessione precedente.
  - Olio EVO L.5 (F.lli Fiorentino) aveva già `peso_confezione=5.0/unita=l` da sessione
    precedente ma SENZA `tipo_quantita` (bug gemello: auto-save vecchio non lo scriveva)
    — corretto via `/correggi-peso` (stesso peso, ora con `tipo_quantita=confezioni`
    esplicito), verificato che attiva la priorità 0 correttamente (10L totali, 5,50€/L).
- NON FATTO in questa sessione (prossimi passi, ordine dal piano originale):
  1. Collegamento a `lotti_fornitori`/`scala_lotti_fornitori_per_ricetta` (FIFO vero) —
     resta il bug noto: il ramo `else` non converte unità diverse. Risponde alla domanda
     originale di Enzo sui 5g di pomodoro. NON ANCORA TOCCATO.
  2. Ricalcolo di massa dei `prezzo_kg` storici sballati dallo stesso bug — non fatto
     unilateralmente (tocca food-cost storico e genererebbe alert prezzo retroattivi).
     Deciso di NON farlo senza conferma esplicita di Enzo. I valori si auto-correggono
     comunque ad ogni nuovo acquisto dello stesso prodotto.
- Test permanenti: `backend/tests/test_prezzo_kg_formula.py` (11 casi, pytest, tutti
  con numeri da dati reali o esplicitamente etichettati come sintetici per testare la
  priorità).

## Fix qualità dati (01/07/2026, sessione nuova chat)
- **righe_fattura_senza_link**: 499→0. Chiamato `/fatture/ricollega-righe` (già esistente).
- **ricette_ingredienti_senza_link**: 863→63. Nuovo endpoint `/ricette/collega-ingredienti-canonico`
  (commit cf1681e): riusa match_livello1/2 già testati (stesso sistema delle fatture) per
  scrivere `ingredienti_dettaglio[].nome_canonico`, invece di una fuzzy-match nuova. I 63
  rimasti sono ingredienti senza match nel dizionario/INGREDIENTI_CANONICI (stessi 8 "senza
  riscontro" della sessione mattina + varianti testo non ancora aggiunte alle keyword).
- **BUG TROVATO E CORRETTO in prodotti_master.py** (commit cf1681e): il rebuild cercava il
  nome_canonico dal dizionario su OGNI alias raccolto per una key, INCLUSE le righe spazzatura
  (righe-riferimento fattura tipo "Documento", "Nota credito", "Vassoio..."). Il match "ripulito"
  di `_canonico_da_dizionario` è abbastanza permissivo da agganciare per sbaglio un ingrediente
  vero non correlato — verificato con dati reali: "vassoio stella trasp." → nome_canonico "Tè",
  "tovaglioi decor natal." → "Aglio". Siccome i filtri "solo ordinabili" controllano
  `nome_canonico` (non l'alias grezzo originale), queste righe spazzatura sfuggivano al filtro
  e gonfiavano falsamente "prodotti senza fornitore/prezzo". Fix: mai cercare il canonico su un
  alias spazzatura — resta col nome leggibile grezzo, che il filtro riconosce correttamente.
  Aggiunti anche pattern spazzatura mancanti (nota credito senza "di", documento, ordine,
  modalità pagamento, destinazione merce, per degustazione, intervento lavori).
  Dopo il fix + rebuild: prodotti_senza_fornitore 37→32, prodotti_senza_prezzo 355→322 (il
  resto sono probabilmente prodotti reali mai comprati via fattura tracciata, non un bug).
- **fatture_non_riconciliate** (10, INVARIATO): tutte le 10 fatture non hanno `xml_raw`
  salvato (verificato via `/fatture/riparse-fornitore-mancante`) — nessuna fonte da cui
  recuperare il nome fornitore in automatico. Serve Enzo: elenco P.IVA in chat, da associare
  a mano se le riconosce (poi `/prodotti-master/rebuild` per propagare).
- **lotti_senza_tracciabilita** (44/172, INVARIATO, non un bug): campioni verificati sono
  produzioni storiche reali (gelati, rustico, granita, caffè freddo, croissant) create senza
  salvare il dettaglio ingredienti al momento della produzione — gap di dati storico, non
  fabbricabile retroattivamente senza inventare valori (vietato). Da monitorare se continua
  a succedere anche per lotti NUOVI (i gelati GEL-20260624-* sono di appena una settimana fa:
  vale la pena controllare se il flusso di produzione gelati collega davvero gli ingredienti).
- **NOTA A PARTE, non toccato**: durante l'audit ho anche trovato che `POST /backup/esegui`
  (quindi il job automatico notturno delle 02:30) fa CRASHARE tutto il backend per ~45s
  (verificato live: 502 su tutte le rotte, poi auto-restart Render) — dump JSON-gzip di TUTTE
  le 198 collezioni (118.972 documenti) in una richiesta, probabile esaurimento risorse sul
  free-tier 512MB. Non toccato: serve una decisione di Enzo su come ridurre lo scope del
  backup (vedi sezione riepilogo audit precedente).

## Correzioni su segnalazione Enzo (01/07/2026, stessa sessione)
- **Lotti senza tracciabilità**: cancellati definitivamente su richiesta esplicita di
  Enzo. Nuovo endpoint permanente `POST /lotti/elimina-senza-tracciabilita` (anteprima
  di default, `?conferma=true` per eliminare — stessa identica query del cruscotto
  controllo-dati, verificato 44 trovati = 44 eliminati prima di procedere). 172→128
  lotti totali. Riusabile in futuro per lo stesso tipo di pulizia.
- **Fatture non riconciliate (P.IVA senza fornitore)**: Enzo ha giustamente contestato
  la mia conclusione precedente ("nessuna fonte per recuperare il nome") — aveva ragione:
  IL MIO CONTROLLO ERA SU UN DATASET INCOMPLETO (avevo in cache solo 1108/1896 fatture
  per un parametro `mesi=0` mal interpretato). Con tutte le 1896: la P.IVA 07914040634
  aveva GIA' il nome "MAROTTA ROSARIA" su un'altra fattura (FPR 7/26) mai controllata.
  Corretto `/fatture/backfill-fornitore-debole` (commit b581b18): ora costruisce la
  mappa P.IVA->nome anche da altre fatture nel DB stesso, non solo dall'anagrafica
  esterna db.fornitori. Risultato: 3 fatture ricollegate subito (le 3 di MAROTTA ROSARIA).
  Restano 7 fatture su 5 P.IVA reali (09312771216, 09317030014, 09462471211 x2,
  06158091212 x2, 01713080628) SENZA xml_raw e SENZA altra fattura nel DB con quella
  P.IVA — cercato anche online (ricerca pubblica P.IVA) senza risultato utile. Questi 7
  restano da chiedere a Enzo a mano (elenco P.IVA sopra), non ho altra fonte legittima.
- LEZIONE: quando un controllo dà "nessuna fonte disponibile", verificare sempre che i
  dati controllati siano COMPLETI (non un sottoinsieme cache-ato da una chiamata
  precedente con parametri diversi) prima di concludere che qualcosa non è risolvibile.

## Collegamento completo ingredienti ricette ↔ nomi canonici (01/07/2026, pomeriggio)
- `ricette_ingredienti_senza_link`: 863 (mattina) → 63 (matcher L1/L2) → **6** (finale).
- Applicate le 84 associazioni del file Excel di Enzo (Matching_Ingredienti_Fatture_LIVE.xlsx,
  foglio Associazioni) + 10 non-ambigue verificate contro i canonici reali del dizionario
  (Sale, Pomodoro, Fiordilatte→Fior di Latte, Panuozzo→Pane panuozzo, kiwi freschi→Kiwi
  Freschi, amido→Amido, Zuppa Inglese→Estratto Zuppa Inglese, Insalata→Insalata,
  grano→Grano cotto [contesto pastiera]).
- METODO: scrittura diretta in `ingredienti_dettaglio[].nome_canonico` via
  PUT /ricette/{id}/ingredienti-dettaglio. NON usato /correggi-mapping: la sua propagazione
  regex sui primi 15 caratteri è pericolosa coi nomi corti ("sale" matcherebbe "salame" e
  riscriverebbe i canonici dei salumi).
- ERRORE FATTO E CORRETTO IN SESSIONE: secondo giro di PUT con JSON stantio ha sovrascritto
  i collegamenti del primo giro su 4 ricette (conteggio 10→20). Lezione: MAI riusare un
  dump ricette dopo aver fatto PUT — riscaricare sempre prima di ogni giro di scrittura.
- Restano 6 righe, tutte residui-etichetta/dato sporco, NON prodotti acquistabili
  (decisione Enzo se rimuoverli dalle ricette): babà Panna e Cioccolato → "grassi
  vegetali", "palmitico", "lecitina di girasole" (etichetta della cioccolata); semifreddo →
  "E102", "E124" (coloranti); rustico Napoletano → riga "0" (dato sporco).
- Verifica end-to-end food cost (semifreddo Frutta Fragole e kiwi): €8,95 totale /
  €0,89 a pezzo su 10 pz, 11/13 ingredienti con prezzo. NOTA: alcuni prezzo_kg storici
  restano sballati dal vecchio bug formula (es. fragole 0,0103 €/kg) — si auto-correggono
  al prossimo acquisto, oppure serve il ricalcolo di massa (decisione ancora aperta).
- `lotti_senza_tracciabilita` nel frattempo 44→0 da solo (i lotti erano scaduti/chiusi e
  sono usciti dal filtro "aperti").
- Score interconnessione: 20 (mattina) → 32.

## Riepilogo rapido (01/07/2026) — per chi riparte da qui
> Sintesi della giornata, dettagli completi nelle sezioni sopra. Non un sistema
> parallelo alle sezioni esistenti: solo un TL;DR per orientarsi in fretta.

**Infrastruttura essenziale**: repo `ceraldicontabilita/Lotti` branch `main`;
backend FastAPI+Motor su lotti-backend-2wwb.onrender.com/api; frontend
React+CRACO su lotti-frontend.onrender.com; MongoDB Atlas `DB_NAME=Gestionale`.
Login: `POST /api/auth/login {"pin":"141574"}`. Deploy automatico al push su
main (~5–8 min). Build frontend: `cd frontend && CI=false npx craco build`
(committare `dist/`).

**Fatto oggi** (dettagli nelle sezioni sopra): fix formula prezzo_kg/quantita_kg
per prodotti a pezzo (`calcola_prezzo_quantita_kg` in `xml_helpers.py`); fix
cache foto ricette; fix allergeni auto-rilevati (ora si applicano da soli); fix
rebuild `prodotti_master` (alias spazzatura, fornitori esclusi filtrati);
nuovo endpoint `POST /ricette/collega-ingredienti-canonico`. Dati: righe
fattura senza link 499→0, ingredienti ricetta senza canonico 863→6, score
interconnessione 20→32.

**Task aperti, priorità**:
1. Backup notturno crasha il backend (`POST /backup/esegui`, scheduler 02:30,
   OOM su 198 collezioni/~119k doc, 502 ~45s) — `scheduler_logs` mostra ancora
   `NameError: MONGO_URL` ogni notte dal 27/06 nonostante il fix del 15/06:
   verificare regressione. Serve decisione di Enzo sullo scope (escludere
   collezioni-log o processo separato) — proporre opzioni, non decidere da soli.
2. FIFO vero: `scala_lotti_fornitori_per_ricetta` in `lotti_produzione.py`, ramo
   `else`, confronta unità diverse senza convertirle — da collegare a
   `calcola_prezzo_quantita_kg`/dizionario pesi (risposta alla domanda di Enzo
   su come si scala "5g di pomodoro in ricetta").
3. Ricalcolo di massa dei `prezzo_kg` storici sballati dal vecchio bug (es.
   fragole 0,0103 €/kg): NON fare senza ok esplicito di Enzo (tocca food-cost
   storico, alert retroattivi); si autocorregge comunque ad ogni nuovo acquisto.

**In attesa da Enzo**: `Ricettario_Completo_Quantita.xlsx` compilato (158
ricette/934 righe) da applicare al rientro; decisione sui 6 residui-etichetta
nelle ricette (vedi sezione sopra); 7 fatture senza fornitore/xml_raw (P.IVA
sopra, serve associazione manuale); conflitto margarina ("MARGARINA GREEN
PLATTE HOMANN" → "Margarina Sfoglia", verificare con lui se giusto).

## Sessione 01/07/2026 (sera) — nomi canonici atomici + matching + ricerca web
Obiettivo: rendere `nome_canonico` davvero atomico/pulito e collegare meglio
matching fatture↔ricette↔ricerca esterna. Tutto verificato su dati live
(`/controllo-dati/overview`) prima di modificare, zero valori inventati.

- **`prodotti_master.py`**: trovate live righe di testo legale da fattura
  ("Assolve gli obblighi di cui all'art. 62, comma 1, D.L. 1/2012...") e righe
  amministrative (storni, acconti, "Colli Peso") promosse a `nome_canonico`
  come fossero prodotti — sporcavano `prodotti_senza_prezzo`/`_fornitore` e
  rendevano il catalogo non atomico. Aggiunte ai pattern spazzatura
  `_PAROLE_NON_ORDINABILI`. Corretto anche un bug strutturale: il filtro
  richiedeva spazio letterale tra le parole di un pattern multi-parola, quindi
  varianti con trattino/underscore (es. "Spese-Gestione-Incasso", che ha GIÀ
  un pattern corrispondente "spese gestione incasso") sfuggivano al filtro.
  Ora il separatore tra parole è flessibile (spazio/trattino/underscore/slash)
  via `_rx_parola()`. Verificato 0 regressioni su ~5300 `nome_canonico` reali
  (ordinabili + non). Test: `test_prodotti_master_spazzatura.py`.
- **Cascata schede tecniche → `nome_canonico`**: `GET /ricette/{id}/pdf-scheda`
  e `/ricette/{id}/tracciabilita-fifo` cercavano la scheda tecnica (per
  composizione/allergeni/coloranti) solo su `d.nome` e sul nome fattura grezzo
  del lotto FIFO attivo — mai su `ingredienti_dettaglio[].nome_canonico`, già
  popolato da `POST /ricette/collega-ingredienti-canonico` (993/999
  ingredienti collegati) ma mai riusato qui. Aggiunto come primo candidato in
  entrambi (fallback sugli altri se non trovato, dedup che preserva l'ordine):
  solo additivo, nessun candidato tolto. Così la ricerca di dati esterni parte
  dal nome pulito ("Margarina") invece che dal grezzo fattura ("MARG.GREEN
  VALLEY CROISSANT 12Kg"), più affidabile per trovare la scheda giusta.
- **Test matching L2** (`test_matching_canonico_ingredienti.py`): regressione
  su `match_livello2`/`_consolida_canonico` con descrizioni fattura REALI
  (AP Commerciale, F.lli Fiorentino, SAIMA — verificate via `/ingredienti/cerca`
  il 01/07/2026). È lo STESSO matcher usato sia dall'import fatture XML sia
  da `/ricette/collega-ingredienti-canonico`: un test unico copre entrambi i
  fronti (fatture↔canonico e ricette↔canonico), niente doppio sistema da
  testare separatamente.
- **Ricerca "caffe" non trova "Caffè Kimbo"** (lavagna magazzino bar,
  segnalato da Enzo): `MagazzinoBarView.jsx` filtrava con solo
  `.toLowerCase()`, senza rimuovere gli accenti. Estratta la normalizzazione
  (NFD + rimozione diacritici) già presente e duplicata in `OrdiniView.jsx` in
  `frontend/src/utils/textNormalize.js`, riusata in entrambi (niente
  doppioni). Risolve sia l'elenco prodotti sia la ricerca per creare una
  richiesta lavagna.
- **NON fatto (in attesa di conferma Enzo)**: pulizia prodotti non alimentari
  dal magazzino bar. Analizzati live 96 candidati non-food su 735 prodotti
  (`GET /magazzino-bar/pulizia-non-merce`), tutti con stock=0. Classificati 59
  da tenere (bicchieri/carta/sacchetti/imballaggi, le eccezioni chieste da
  Enzo) e 37 da togliere (chimici, elettronica, attrezzatura, manodopera, +
  posate/cannucce/palette/calici/tazze/piatti — non alimentari ma fuori dalle
  5 eccezioni). Enzo ha detto di annullare per ora: lista pronta se si vuole
  procedere (magari a metà, solo i 16 chimici/elettronica/servizi). Endpoint
  già esistente e sicuro per farlo quando deciso: `POST
  /magazzino-bar/pulizia-non-merce` con `ids` espliciti (mai cancella alla
  cieca).
- `/security-review` sul diff di sessione: nessuna vulnerabilità (regex
  costruite da stringhe letterali hardcoded, nessun input utente coinvolto).

## Ricerca web da descrizione XML esatta (02/07/2026) — richiesta Enzo
Il flusso che Enzo aveva chiesto fin dall'inizio, ora implementato: la
descrizione ESATTA della riga fattura XML (es. "FARINA 00 CAPUTO
RINFORZ.KG.25") viene cercata sul web COSÌ COM'È per identificare con
certezza il prodotto commerciale reale (farina rinforzata per pizza, non
"farina" generica; il "burro" che in fattura non si chiama mai burro),
trovare la scheda tecnica del produttore e da quella dedurre il canonico.
- `POST /schede-tecniche/ricerca-web` {descrizione, fornitore?, salva?}:
  ricerca web server-side (strumento `web_search` dell'API Anthropic, stessa
  `ANTHROPIC_API_KEY` di leggi-foto-ai, modello Haiku, max 3 ricerche) →
  JSON {prodotto_identificato, marca, nome_canonico, impiego, url_scheda,
  ingredienti_testo, confidenza}. Composizione dal testo trovato o scrape
  dell'URL (riusa `_estrai_da_testo`/`_scrape_composizione`). SOLO con
  confidenza ALTA salva: scheda tipo='produttore' con link (entra nella
  cascata allergeni ricette) + mapping descrizione→canonico in `nome_mapping`
  (L1, così le fatture successive risolvono da sole) + completa
  `ingrediente_canonico` nel dizionario dove manca (MAI sovrascrive).
  Canonico consolidato col matcher unico (`_consolida_canonico`).
- `POST /schede-tecniche/ricerca-web-batch?limit=N` (max 5): processa i
  prodotti del dizionario senza canonico, stop dopo ~65s (timeout Render);
  rilanciare più volte per proseguire.
- Link scheda nella ricetta: `pdf-scheda` mostra "scheda tecnica ↗" sotto la
  composizione dell'ingrediente; `tracciabilita-fifo` espone `scheda_url`.
- Frontend: pannello "Ricerca web automatica" in SchedaFonteModal (salvia),
  mostra prodotto/canonico/impiego/confidenza e compila l'URL trovato.
- NOTA COSTI/SICUREZZA: ogni chiamata = 1 messaggio Haiku con fino a 3
  ricerche web; il batch è volutamente piccolo. Confidenza media/bassa non
  scrive nulla (solo proposta a video), per non inquinare mapping/schede.
- VERIFICATO LIVE (02/07/2026, dati reali):
  * "FARINA 0/MAN. CAPUTO DA KG.25" → identificato "Farina Tipo 0 Mulino
    Caputo", impiego pizza/pane, url mulinocaputo.it, allergeni
    Glutine/Soia/Senape — confidenza MEDIA (descrizione ambigua 0/Manitoba)
    → correttamente NON salvato nulla. Il gate di sicurezza funziona.
  * "PARMAREGGIO BURRO BIO G125" → identificato "Parmareggio Burro Bio 125g"
    (Caseifici GranTerre), url parmareggio.it/detail-prodotto/21,
    composizione "burro biologico 83% m.g.", allergene Latte — confidenza
    ALTA → scheda + mapping salvati.
- BUG TROVATO AL PRIMO TEST LIVE E CORRETTO: il canonico libero del modello
  ("Burro biologico") finiva in nome_mapping (L1), che vince su L2 → il FIFO
  ricette che cerca "Burro" non avrebbe più trovato il lotto. Fix: priorità a
  match_livello2 (solo chiavi del vocabolario controllato INGREDIENTI_CANONICI:
  "Burro", "Farina tipo 0"), nome libero consolidato solo come fallback per
  prodotti fuori vocabolario. Il mapping già salvato nel test è stato corretto
  a mano via POST /ingredienti/mapping-manuale ("parmareggio burro bio g125"
  → "Burro"). Test aggiunti con i due casi live reali.

## Campagna ricerca web in background (02/07/2026) — richiesta Enzo
Enzo: "la ricerca la devi fare adesso e ogni qualvolta si importa un XML se ci
sono righe nuove; memorizzi il tutto e associ agli ingredienti della ricetta,
così i dati restano salvati una volta e per sempre".
- CENSIMENTO (documento consegnato in chat + CSV): 1.896 fatture → 10.309
  righe → 3.694 DISTINTE. Di cui: 982 con canonico già noto, ~820 non-prodotti
  (spese/canoni/amministrative), ~1.850 prodotti veri DA IDENTIFICARE.
- CODA AUTOMATICA `_coda_ricerca_web()` (schede_tecniche.py): aggregazione
  live su db.fatture (righe distinte per frequenza d'acquisto, le più comprate
  prima) MENO non-food/amministrative (filtri ufficiali), righe già in
  nome_mapping, schede già salvate, righe già tentate 2 volte (collezione
  `ricerca_web_tentativi` — mai retry infiniti su righe non identificabili).
  Si auto-aggiorna: le righe nuove di ogni import XML entrano da sole.
- JOB SCHEDULER `ricerca_web_prodotti`: ogni 20 min (06-22 Roma), 3 righe per
  giro ≈ 200/giorno → backlog ~1.850 esaurito in ~9-10 giorni, poi resta solo
  il mantenimento delle righe nuove. Dopo ogni salvataggio ricollega gli
  ingredienti ricetta orfani (collega_ingredienti_canonico). Silente se coda
  vuota o manca ANTHROPIC_API_KEY.
- MONITORAGGIO: `GET /schede-tecniche/ricerca-web-stato` (in coda, salvati,
  non identificabili, ultimi tentativi, prossimi). Batch manuale:
  `POST /schede-tecniche/ricerca-web-batch?limit=5`.
- FILTRI ESTESI (classificatore): articolo vario, riga ausiliaria, cauzioni,
  targhe auto compatte del leasing (\b[a-z]{2}\d{3}[a-z]{2}\b — SOLO compatte:
  con spazi matcherebbe "CF 100 PZ"). Verificato su 3.694 righe reali: 38
  match tutti non-food, zero alimenti persi. Test in
  test_prodotti_master_spazzatura.py.
- Il link alla scheda trovata è cliccabile: nella scheda ricetta stampabile
  ("scheda tecnica ↗"), in tracciabilita-fifo (scheda_url) e nel pannello
  "Ricerca web automatica" di SchedaFonteModal.
- PRIMO GIRO LIVE della campagna: coda reale 227 righe (non ~1.850: il grosso
  era già coperto da nome_mapping imparato — il censimento usava solo il
  dizionario come riferimento, sottoinsieme). 3 processate: Peperoni+lotto →
  bassa (non salvato, giusto così); TAPPI GRANDI → identificato con link
  dolciariaacquaviva.com CORRETTO ma canonico "Tè" SBAGLIATO; CORNETTO VEGANO
  → ok con link.

## BUG STORICO RISOLTO: match_livello2 per sottostringa (02/07/2026)
Il caso "TAPPI GRANDI → Tè" del primo giro ha permesso di riprodurre e
chiudere il bug dei canonici assurdi (già visto come "804 PALETTE → Tè",
"vassoio stella trasp. → Tè" nelle sessioni precedenti): la keyword "te" (e
simili) matchava PER SOTTOSTRINGA dentro qualunque parola — "torte", "paste",
"palette", "ACQUA LETE"; "orata" dentro "decorate" → Pesce; "cola" dentro
"cioccolattati" → Cola; "gin" dentro "original" (Baileys ORIGINal → Liquori).
- FIX in match_livello2 (ingredienti.py): ogni keyword deve iniziare dove non
  c'è una lettera prima — cifre/simboli valgono da separatore, così
  "24RIGATONI" matcha "rigatoni" (le fatture incollano i numeri alle parole);
  le keyword ≤3 caratteri devono anche finire senza lettera dopo. Aggiunta
  keyword "tea" (STAR TEA).
- VERIFICA su 3.694 righe fattura reali: 93 falsi canonici eliminati, 1 sola
  perdita vera (STAR TEA, recuperata). I "match giusti per caso" su marchi
  fusi (CURTIRISO→Riso, BRANCAMENTA→Menta) si perdono al L2 ma li recupera la
  campagna ricerca web con certezza (entrano in coda e vengono identificati).
- ATTENZIONE DATI: i canonici GIÀ SCRITTI dal matcher difettoso restano nel
  DB (dizionario/nome_mapping storici, es. ACQUA LETE→Tè) — il fix evita i
  nuovi errori ma NON pulisce i vecchi. Audit di pulizia = task aperto.
- Mapping live corretti a mano: "tappi grandi g 55/60" → "Tappi".

## Regole Enzo su verdure e detersivi (02/07/2026, sera)
1. **Verdure/ortofrutta: MAI ricerca web** — i codici lotto nelle righe XML
   ("Peperoni L.031-004226-0000007") sono numeri privati del venditore,
   introvabili online. La coda ora prova PRIMA il matcher locale L2: se
   risolve, impara il mapping gratis (parametro `impara=True` del batch/job;
   il GET stato non scrive) e la riga non va mai sul web. Copre ortofrutta,
   ricotta, mascarpone e tutto il vocabolario esistente.
2. **Detersivi: scheda di SICUREZZA obbligatoria** (principi attivi, pericoli
   per l'uomo, tossicità) per HACCP/ASL. `RX_DETERSIVI` nel classificatore
   (stem condivisi con HARD_NONFOOD, niente doppioni); le righe chimiche
   entrano in coda con tipo='chimico' → prompt SDS dedicato → scheda
   tipo='sicurezza' {principi_attivi[], pericoli[], velenoso, url}. MAI
   nome_mapping per i chimici (non devono entrare nel matching ricette).
   Eccezione dolciaria: "AMMONIACA (BICARBONATO DI AMMONIO) E503" = materia
   prima pasticceria, esclusa dai chimici (e ora anche da HARD_NONFOOD, era
   nascosta per errore dai cataloghi). Su 3.694 righe reali: 34 chimici veri.
   Le schede sicurezza sono visibili via GET /schede-tecniche/prodotti?
   includi_non_alimentari=true (UI dedicata in sezione HACCP = da fare se
   Enzo la vuole).
- Keep-warm esteso 04:00-22:59 (prima 20:59): copre tutta la fascia del job
  ricerca web — senza, l'ultima ora e mezza saltava per lo sleep di Render.

## Flag manuale di Enzo sulla coda ricerca web (02/07/2026, mattina)
Enzo cura la coda con una checklist: gli viene consegnato un file con le righe
in coda, lui marca `[x]` SOLO quelle da cercare, lo restituisce, e:
- `POST /schede-tecniche/ricerca-web-flag {cerca:[], escludi:[]}` applica il
  file: gli esclusi non vengono MAI più cercati (flag permanente in
  ricerca_web_tentativi.escluso); i flaggati rientrano in coda anche se erano
  stati sospesi (tentativi azzerati) e VINCONO sui filtri automatici.
- Dalla foto del suo tablet: filtrate anche le righe bolletta energia
  ("SPESA ONERI DI SISTEMA", "SPESA PER L'ENERGIA" fascia F1/F2/F3,
  dispacciamento, perdite di rete) che sfuggivano ai filtri.
- Il giro automatico resta acceso in attesa del file (Enzo può chiedere di
  sospenderlo); quando il file torna, la coda diventa di fatto curata a mano.

## Bolletta MongoDB Atlas $175 + pulizia collezioni (02/07/2026)
- ANALISI (file analisi_mongodb.md consegnato a Enzo): DB Gestionale condiviso,
  201 collezioni / 119.226 documenti (<1GB). 69 collezioni usate da Lotti
  (69k doc), 132 di altre app o morte (50k doc). LA BOLLETTA NON SONO I DATI:
  con questi volumi il costo giusto è $0-30/mese → quasi certo tier cluster
  sovradimensionato (M20 ≈ $180/mese anche vuoto). Azione principale (per
  Cloud codeweb): Atlas → Billing → verificare SKU → downgrade a Flex/M10;
  controllare anche Cloud Backup e Data Transfer (polling tablet).
- PULIZIA: endpoint POST /diagnostic/pulizia-collezioni (anteprima default,
  conferma=true per agire; ricontrollo vuote server-side; rinomina reversibile
  cestino_<nome>; lista protetta hardcoded _COLLEZIONI_PROTETTE con le 69 di
  Lotti — rifiuta di toccarle comunque). GET /pulizia-collezioni-proposta
  calcola la proposta (vuote non protette + _CANDIDATE_CESTINO, i 10 resti
  morti Lotti: haccp_lotti, warehouse_*, tracciabilita, schede_tecniche_jobs/
  _prodotti, ordini_app_*, produzione_mattina_template ~2.1k doc).
- L'ESECUZIONE dev'essere confermata DA ENZO nell'app: pannello "Pulizia
  collezioni database" in Controllo Dati (Analizza → Conferma pulizia).
## Ricezione merce: Conforme/Non conforme a un tocco (02/07/2026)
Richiesta Enzo (screenshot pagina Ricezione): nella lista "Prodotti arrivati
da fatture XML" ogni riga ha ora DUE bottoni: "Conforme" (verde) registra
subito la ricezione senza aprire nulla; "Non conforme" (rosso) apre il
pannello già marcato non-conforme con azione correttiva OBBLIGATORIA (flag
`anomalia.nonConforme` incluso nel calcolo conformità di confermaDaFattura;
Annulla lo azzera). Il tocco sulla riga apre/chiude ancora il pannello per
la temperatura opzionale. File: RicezioneMerceView.jsx.

- SCOPERTA NAVIGAZIONE (importante per il futuro): la barra dei tab
  (TABS/TABS_ALTRO in App.js) è NASCOSTA via CSS (`App.css`:
  `.g-nav-bar { display:none !important }` — "Home a card come unica
  navigazione"). Quindi il dropdown "Altro" NON è visibile: le pagine
  secondarie si raggiungono SOLO con le card della Home o con l'hash
  diretto (#controllo_dati). Enzo non trovava Controllo Dati per questo →
  aggiunta card "Controllo Dati" nella Home, sezione Archivio. REGOLA:
  ogni nuova pagina deve avere una card/percorso visibile dalla Home.
  Il sandbox in auto-mode non può eseguire modifiche distruttive sul DB
  condiviso (bloccato dal classificatore anche con ok esplicito in chat) —
  scelta corretta: il tasto lo preme l'umano. Anteprima verificata: 22 vuote
  + 10 cestino, 0 saltate.
- Rimosso indice su warehouse_movements (indici.py): creare indici su una
  collezione morta la resuscitava ad ogni avvio.
- Le 22 vuote appartengono ad ALTRE app (paghe/F24/presenze/recon): il drop è
  innocuo (Mongo le ricrea al primo insert), ma la pulizia vera del territorio
  gestionale spetta a Cloud codeweb con la lista del file di analisi.

## Prodotti & Listini unificata (02/07/2026, richiesta Enzo)
Diagnosi doppioni (audit componenti): CatalogoUnificatoView era un CLONE del
catalogo del tab Ordini (stessa fonte /prodotti-master, senza carrello né
giacenze) → ELIMINATO (file rimosso); al suo posto link "Catalogo & Ordini →"
che porta a Ordini. Il rebuild catalogo (stava solo lì) è ora in Controllo
Dati ("Rebuild catalogo prodotti"). La pagina apre di DEFAULT sul tab
Listino: genera listino fornitore con sconto % (GET /listino/calcola?
fornitore&sconto&modo, PDF con /calcola-pdf, invio email con /listino/invia)
— VERIFICATO LIVE (Kimbo -5% ok). Fix: /listino/calcola ora esclude le righe
amministrative coi filtri ufficiali (viste live: "SPESE BOLLI" nel listino).
Card "Prodotti & Listini" nella Home (Archivio). Rotta controllo-dati
"movimenti magazzino senza prodotto" → #magazzino_prodotti.
DOPPIONE RESIDUO NOTO (non toccato, serve decisione): ComparatorePrezziView
(prodotti-canonici, nuovo) vs tab alias/catalogo interni a ListinoView
(sistema alias vecchio che il comparatore dichiara di migrare) — unificarli
tocca il modello dati listino: proporre a Enzo prima di agire.

## Architettura Acquisti vs Listini (02/07/2026, sera — richiesta Enzo)
Enzo: "#prodotti e #ordini sembrano avere le stesse funzioni, unifica da
professionista". RAGIONAMENTO: divisione per INTENTO, non per tipo di dato.
- **#ordini = COMPRARE** (schede: Catalogo · Confronto · Carrello · Giacenze ·
  Da inviare). Il Confronto prezzi (ComparatorePrezziView) è stato SPOSTATO
  qui da Prodotti&Listini: serve a decidere DA CHI comprare, è parte del
  flusso d'acquisto. OrdiniView ora accetta prop initialTab; il tab hash
  "comparatore" apre Ordini sulla scheda Confronto (retrocompatibile).
- **#prodotti = I MIEI PREZZI**, rinominata "Listini & Vendita" (schede:
  Listino con sconto · Vendita banco · Magazzino prodotti · Sconti merce).
- Card Home aggiornate: "Acquisti & Ordini" / "Listini & Vendita".
- LEZIONE MARCATORI BUNDLE (ribadita): mai stringhe con accenti per verificare
  il bundle live ("Integrità" diventa à nel minificato → falso negativo).

## Esito pulizia DB + lezione warehouse_inventory (02/07/2026, sera)
- PULIZIA ESEGUITA DA ENZO col pannello in Controllo Dati: le 22 collezioni
  vuote e 9 resti morti Lotti risultano eliminati/archiviati (verificato:
  la proposta live è quasi vuota). Il flusso tap-umano ha funzionato.
- warehouse_inventory NON toccata e RIMOSSA dai candidati cestino: sembrava
  morta (1 doc) ma in giornata è passata a 212 doc — la scrive un'ALTRA app
  del cluster. Il rename è fallito con 500 (scritture concorrenti): errore
  fortunato. LEZIONE PERMANENTE: per le collezioni del DB condiviso il grep
  sul codice Lotti NON basta a dichiararle morte — osservare anche la
  crescita dei conteggi nel tempo prima di toccarle.
- Smoke test completo post-sessione: 11/11 endpoint verdi + frontend 200.

## Riordini a pochi tap + Listino semplificato (02/07/2026, notte)
Enzo: "pochi tap per ottenere un ordine; vedere lavagna, scarichi, sotto
soglia; gestione ordini molto semplificata".
- **Scheda RIORDINI** (nuova, atterraggio di Acquisti & Ordini): riunisce
  1) prodotti sotto soglia (quantità suggerita fino a soglia, bottone singolo
  o "Aggiungi tutti") e 2) richieste lavagna dei dipendenti (stato=aperta,
  match sul catalogo per nome normalizzato, +carrello a un tocco). Badge col
  conteggio; bottone "Vai al carrello e crea le bozze" quando pieno. Flusso:
  apri Ordini → Aggiungi tutti → Carrello → Crea bozze → Invia = 5 tocchi.
- **ListinoView semplificato**: default "Genera listino" (fornitore/categoria
  + sconto + PDF + invio); "Catalogo prezzi" per la gestione voci ma SENZA
  carrello interno (eliminati handleCarrello/handleInvia/PannelloCarrello: si
  ordina SOLO da Ordini); tab "Alias prodotti" RIMOSSO (vecchio sistema,
  sostituito dal Confronto canonici in Ordini; AliasView eliminata, dati
  alias restano dormienti in DB; endpoint /listino/alias ancora vivi lato
  backend — candidati a rimozione futura).


## Dominio personalizzato ceraldiapp.it (02/07/2026, mattina)
- Enzo ha collegato ceraldiapp.it al frontend da Render (Custom Domains):
  Render ha SPENTO lotti-frontend.onrender.com (404, header
  x-render-routing: blocked-render-subdomain). La radice ceraldiapp.it fa
  301 → https://www.ceraldiapp.it (primario).
- CORS: aggiunte www.ceraldiapp.it e ceraldiapp.it come origini SEMPRE
  ammesse nel codice (server.py, unione con env) + render.yaml aggiornato.
  Senza, il sito si apre ma tutte le API sono bloccate dal browser.
- impresasemplice.online = il GESTIONALE (altra app, "Azienda in Cloud ERP"),
  non Lotti.
- DIAGNOSI UTILE: un 404 improvviso su *.onrender.com con quel header NON è
  un guasto: è il subdominio disattivato per dominio personalizzato.

## Backup notturno SISTEMATO (02/07/2026) — erano DUE problemi diversi
1. **`NameError: MONGO_URL` ogni notte** in scheduler_logs: NON è di Lotti.
   Il codice attuale del percorso backup non referenzia MONGO_URL (verificato
   con grep completo). scheduler_logs è CONDIVISA col gestionale Cloud: quel
   crash è di un job omonimo "backup_notturno" dell'ALTRA app → da segnalare
   a Cloud codeweb. Nuovo endpoint diagnostico GET /scheduler/logs?job=…
2. **502 su tutte le API (~45s) durante il backup** (verificato live 1/07):
   NON era memoria (streaming già presente dalla v2.1 del 15/06) ma CPU:
   json.dumps+gzip di ~119k documenti giravano DENTRO l'event loop e sul
   free tier lo bloccavano per l'intera durata. FIX v2.2: blocchi da 500
   documenti serializzati+compressi in un thread (asyncio.to_thread), sleep
   0.05s tra blocchi. Formato file INVARIATO (restore compatibile, verificato
   con test funzionale di round-trip). Il backup ora convive con le API.
- NB /backup/stato può dire "nessun_backup" dopo ogni deploy: BACKUP_DIR è
  /tmp, effimero — ogni deploy lo azzera. Non è un errore del job.

## Ciclo ordini ATOMICO (02/07/2026 — audit critico richiesto da Enzo)
Audit con 2 agenti su lavagna/giacenze/riordino. TROVATO E CORRETTO:
1. **BUG STATO CRITICO**: `/ordini-fornitori/{id}/invia` scriveva stato
   `inviato_manualmente` ma ricezione merce e riconciliazione fattura
   cercavano solo `inviato_fornitori` → gli ordini inviati NON si chiudevano
   MAI automaticamente. Fix: stato canonico all'invio + lettori tolleranti
   del legacy (ordini vecchi già in inviato_manualmente).
2. **MOTORE RIORDINO UNICO** (`esegui_riordino_automatico`): copre bar
   (soglia_minima) E materie prime (dizionario.scorta_minima) con bozze per
   fornitore e dedup incrociata su TUTTI gli ordini aperti di qualsiasi
   source (`_prodotti_gia_in_ordine`: id + nome normalizzato). Rimosso il
   job 08:00 `check_scorta_minima` (bozza cumulativa parallela, quantità
   scorta*3 arbitraria, dedup solo sul proprio source). Il motore gira alle
   07:00 dentro job_genera_haccp_giornaliero.
3. **LAVAGNA CHIUSA**: consegna con stock esaurito → il prodotto entra da
   solo in bozza riordino (`aggiungi_a_bozza_riordino`, accoda alla bozza
   del fornitore se esiste). Prima moriva 'evasa' senza ordine se soglia=0.
4. **Riordini stock-aware** (OrdiniView): richiesta lavagna = trasferimento
   interno; se il magazzino ha stock mostra "consegna dal tablet", il
   carrello solo se manca.
RESIDUI NOTI dall'audit (non bloccanti, da valutare): giacenze OrdiniView
vede solo il bar (le materie prime sotto scorta ora arrivano comunque via
bozze automatiche); 3 scritture stock bypassano applica_movimento_stock
(azzeramenti/inventario: correzioni assolute volute ma senza evento
uniforme); scorta_frigo esclusa dal calcolo sotto_soglia; task-produzione-
oggi e /automatici filtrano source/stati mai prodotti (codice probabilmente
morto, candidato a rimozione).

## Arretrato bozze + tasto "Pulisci e rigenera riordini" (02/07/2026)
- L'audit ha rivelato 149 BOZZE APERTE tutte auto-generate (106 riordino_auto,
  33 alert_mancanti, 9 automatico_lotti, 1 automatico_scorta; dal 15/06):
  l'accumulo quotidiano dei vecchi job senza dedup. Per questo il dry-run del
  motore nuovo propone 0: la dedup vede tutto già in bozza.
- Nuovo POST /ordini-fornitori/pulisci-e-rigenera-riordini (anteprima default,
  conferma=true): elimina SOLO bozze source automatiche (manuali intoccate) e
  rigenera col motore unico un set fresco sulle scorte di oggi. Bottone in
  Controllo Dati (conferma umana: il classificatore del sandbox blocca
  giustamente le cancellazioni di massa autonome).
- ATTENZIONE DOMINIO: il certificato SSL di www.ceraldiapp.it è in emissione
  da >1h — probabile CNAME www mancante dal registrar. Finché non si risolve
  l'app NON è raggiungibile da nessun URL (il subdominio Render è spento).
  Opzioni: sistemare il DNS del www, o rimuovere temporaneamente il custom
  domain su Render per riaccendere lotti-frontend.onrender.com.

## Le ricette fanno partire gli ordini (02/07/2026 — Enzo aveva ragione)
Enzo ha contestato il mio "è tutto atomico": VERO, non lo era. Audit sulle
porte d'ingresso (agente dedicato) + fix:
- **BUG PRINCIPALE**: il check scorta post-produzione esisteva ma leggeva
  dizionario.quantita_disponibile_kg, aggiornato SOLO all'import fatture
  (unici writer: fatture.py e food_cost.usa_ricetta). Il flusso reale del
  tablet (registra-produzione-lotto → scala_lotti_fornitori_per_ricetta)
  scala solo lotti_fornitori.quantita_disponibile → il campo-soglia restava
  stantio e il riordino da produzione NON scattava mai.
- **FIX — _riordini_post_produzione** (lotti_produzione.py): dopo ogni
  produzione, per ogni ingrediente scalato calcola la disponibilità VERA dai
  lotti fornitori, la SINCRONIZZA su dizionario.quantita_disponibile_kg e se
  sotto scorta_minima o esaurita crea la bozza col motore unico
  (aggiungi_a_bozza_riordino: per fornitore, dedup incrociata). Sostituisce
  DUE percorsi paralleli eliminati: 'automatico_scorta' post-produzione
  (bozza cumulativa) e '_verifica_riordino_ultimo_lotto'/'automatico_lotti'
  (bozze qty=1 senza prodotto_id).
- Ricerca card tablet unificata a norm() (accent-insensitive).
RESIDUI dall'audit porte d'ingresso (aperti, in ordine di importanza):
1. Cataloghi paralleli Alpha/Acquaviva/Colazione cercano su
   acquaviva_prodotti, non su prodotti_master (anagrafica separata).
2. VenditaBanco e Gelati non scalano le materie prime alla produzione.
3. Source fantasma 'automatico_giacenza'/'tablet_pasticceria' letti in
   task-produzione-oggi e /automatici ma mai scritti da nessuno (codice
   morto candidato).
4. Tablet "Aggiungi prodotto" crea ricette direttamente (senza passare da
   un flusso di validazione).

## Colazione → ordini centralizzati (02/07/2026 — richiesta Enzo)
Flusso implementato: consegna Acquaviva/Vandemoortele (pezzi noti da fattura)
→ "manda al banco" la mattina (POST /colazione-acquaviva/registra) → calcolo
residuo VERO in congelatore (funzione riusabile calcola_magazzino_congelatore
in acquaviva.py: entrate ultime 2 fatture − uscite banco; fuzzy-match nome
banco↔fattura estratto in _match_desc_banco, testato) → se resta MENO DI UN
CARTONE o zero → bozza riordino col motore unico (aggiungi_a_bozza_riordino,
dedup incrociata), quantità = cartoni per tornare a 2 cartoni. Esito in
risposta ("riordini_colazione"). Regola soglia: "sta per finire" = < 1
cartone (default di dominio, override futuro con scorta_minima_pezzi se
servirà). Fix collegato: badge admin proposte automatiche filtrava source
fantasma (automatico_giacenza/tablet_pasticceria) mai scritti → ora include
riordino_auto e alert_mancanti (+ legacy).

## Pezzi per cartone dalle schede tecniche (02/07/2026 — richiesta Enzo)
Problema: la fattura dà la quantità in cartoni ma non i pezzi contenuti.
Soluzione: il motore ricerca-web (tipo alimento) ora chiede anche
pezzi_per_cartone e peso_pezzo_g (voci formato/confezione/imballo della
scheda del produttore). Con confidenza ALTA salva:
- sulla scheda tipo=produttore (campi pezzi_per_cartone, peso_pezzo_g);
- su dizionario_prodotti: pezzi_per_cartone (+fonte 'scheda-tecnica-web'),
  peso_pezzo_g; peso_confezione+tipo_quantita=conteggio_confezioni SOLO se
  mancanti (mai sovrascrivere i dati derivati da fattura) → entra come
  REGOLA NOTA di calcola_prezzo_quantita_kg (priorità 0).
La campagna in background (job ogni 20 min) accumula così i formati per
tutti i prodotti in coda; le schede già salvate prima di oggi NON hanno il
campo (non vengono ricercate di nuovo per la dedup — eventuale backfill
mirato da valutare).

## Test live pezzi-per-cartone + pattern da correggere (02/07/2026)
- VERIFICATO LIVE: "AQV CRNT CURVED MLTCER BER 80G 4.16KG" → scheda
  dolciariaacquaviva.com trovata, PEZZI PER CARTONE 52, peso pezzo 80g
  (52×80g=4,16kg = peso cartone in fattura ✓). Salvati scheda+dizionario.
- PATTERN DA SISTEMARE (visto nel test): per i PRODOTTI FINITI comprati
  (cornetti/croissant semilavorati) il canonico L2 può agganciare il GUSTO
  ("Frutti di bosco") invece del prodotto → rischio che le ricette coi
  frutti di bosco veri peschino i cornetti nel FIFO. Corretto a mano il
  mapping del test ("...MLTCER BER..." → "Cornetto multicereali frutti di
  bosco"). TODO: nel flusso ricerca-web, riconoscere i prodotti finiti
  (croissant/cornetto/sfogliatella/tappi...) e usare canonico libero di
  prodotto invece del vocabolario ingredienti. Monitorare i prossimi
  salvataggi della campagna per mapping simili.

## Dominio LIVE + file dizionario v2 consegnato (02/07/2026, tardo pomeriggio)
- **www.ceraldiapp.it è VIVO** (HTTP 200 servito da Render/Cloudflare,
  header rndr-id verificato in raw). La radice ceraldiapp.it fa 301 → www.
  Il problema DNS del mattino è risolto: l'app è raggiungibile SOLO dal
  dominio ufficiale (il subdominio Render resta volutamente spento).
- Nota per il futuro: il TODO "prodotti finiti → canonico libero" della
  sezione precedente è GIÀ implementato (_RX_PRODOTTO_FINITO in
  schede_tecniche.py:712).
- Consegnato a Enzo il file **DIZIONARIO_DA_COMPILARE.md** (v2 della
  checklist del mattino), generato dai dati live:
  - Sezione A: 80 righe in coda ricerca web con flag [x]=cerca /
    [ ]=escluso per sempre + campi editabili per riga
    (unita, pezzi_cartone, peso_pezzo_g, prezzo_cartone, prezzo_pezzo);
    l'unico chimico è pre-flaggato (schede sicurezza HACCP).
  - Sezione A-bis: 65 righe riconosciute come riferimenti contabili
    (rif. bolle GIAL, scontrini, buoni pasto...) separate in fondo.
  - Sezione B: 18 ricerche sospese (esito incerto), flag = riprova,
    oppure Enzo scrive i valori a mano e li salvo senza cercare.
  - Sezione C: 260 prodotti del dizionario (>=5 acquisti, servizi esclusi)
    con TUTTI i valori attuali del DB prefissati nei campi editabili
    ({key:nome_normalizzato} come chiave riga; 🌐 = pezzi_per_cartone da
    scheda web). Enzo corregge/integra; al ritorno del file: diff campo
    per campo e update dizionario_prodotti con fonte 'enzo-manuale'
    (peso_corretto_manualmente=true, MAI sovrascritto dai ricalcoli).
  - Sezione D: regole globali unità ("burro: g", "latte: l"...) da
    applicare per parola-chiave a tutto il dizionario.
- AL RITORNO DEL FILE: (1) flags → POST /schede-tecniche/ricerca-web-flag
  {cerca[], escludi[]}; (2) diff valori Sezioni A/B/C → update
  dizionario_prodotti; (3) Sezione D → regole unità per keyword.
  Il file inviato è in scratchpad (DIZIONARIO_DA_COMPILARE.md) come
  riferimento per il diff.

## Confronto prezzi reale + bonifica design (02/07/2026, pomeriggio)
Segnalazione Enzo (screenshot): "crodino" nel Confronto dava 0 risultati e
la pagina non seguiva il design (viola/indigo residui).
- CAUSA: la vista Confronto era costruita su prodotti_canonici, un SISTEMA
  PARALLELO vietato dalle regole (collection vuota → Catalogo 0, coda
  "da classificare" 500). ELIMINATO: routers/prodotti_canonici.py (678
  righe), hook in fatture.py, merge fonte 6 in prodotti_master.py,
  include in server.py. Le collection prodotti_canonici /
  prodotti_da_classificare restano nel DB come orfane (candidate cestino
  a un prossimo giro di pulizia).
- NUOVO GET /food-cost/confronto-prezzi: raggruppa dizionario_prodotti
  per canonico (nome_canonico > ingrediente_canonico > nome_normalizzato),
  prezzo €/kg più recente PER FORNITORE (solo fatture XML), risparmio %,
  categorie dinamiche, ricerca con stems_ricerca (motore unico).
  Verificato su dati live: "crodino" → 4 gruppi; 134 prodotti
  confrontabili (≥2 fornitori). NOTA: la ricerca ha rivelato canonici
  frammentati ("Crodino"/"Crodino Bevanda"/"Bevanda analcolica") →
  rientra nell'audit pulizia canonici già in lista.
- ComparatorePrezziView riscritta in stile Dashboard: Tailwind
  stone/white, icone Lucide per categoria (niente emoji), salvia,
  migliore evidenziato emerald con badge −%, sheet dettaglio per
  fornitore, ricerca server-side con debounce.
- BONIFICA COLORI VIETATI (agente, verificata): 52 file frontend,
  ~500 sostituzioni — tutti i viola/indigo/blu (5D29C7, 1E1B4B, 7c3aed,
  8b5cf6, violet-*, indigo-*, sky-*, bg-blue-*) rimappati su
  salvia/sabbia/ambra secondo design_handoff. Casi notevoli: gradienti
  Tour/tablet → 135deg #3f5a4e→#5b7a6b; DashboardView toni blue→ambra,
  violet(V)→salvia, cyanV→sabbia; TabNutrizionali "Grassi" → ocra;
  ManualeView costante VIOLA→SALVIA; index.css blocchi compat riscritti.
  Build CRA ok, bundle finale con ZERO occorrenze vietate.

## AUDIT COMPLETO DEL CODICE (02/07/2026, sera — richiesta Enzo "/goal ricontrolla tutto")
Metodo: pyflakes su tutto il backend + cross-check 328 chiamate frontend ↔
635 rotte backend + controllo refusi collection + 3 revisori semantici
paralleli (ordini, FIFO/prezzi, frontend). ~30 finding verificati e corretti
in 2 tranche. Tranche 1 (commit precedente): fname/NameError ×11, $ne
duplicati ×6, rettifica 404, sottosistema alias morto, viola nel PDF listino.
Tranche 2 (questo commit), i più importanti:

ORDINI/RIORDINI:
- Riconciliazione fatture: MAI più fallback su ordini di ALTRI fornitori
  (chiudeva bozze estranee come "ricevuto") e chiude SOLO ordini realmente
  inviati (inviato_fornitori/manualmente/legacy), non bozze/confermati.
  Stessa regola in ricezione_merce + re.escape sulle regex fornitore.
- _prodotti_gia_in_ordine: aggiunti stati ricevuto_parziale e legacy
  "inviato" alla dedup, cap 200→1000 con sort (merce in arrivo non viene
  più riordinata).
- POST /magazzino-bar/riordina: creava ordini paralleli stato legacy
  "inviato" fuori da ogni flusso → ora delega al motore unico.
- Motore riordino: dedup intra-run bar↔materie; unità materie prime
  forzata kg (usciva "18 pz" per 18 kg); bar riordina fino a 2× soglia
  (prima oscillava con ordini da 1 pezzo); righe con prodotto_id vuoto
  ora hanno id univoco (modifica/conferma righe non collidono più).
- evadi_richiesta lavagna: claim ATOMICO stato aperta→in_evasione
  (doppio tap non scarica più due volte; errori inattesi la riaprono).
- Scheduler 07:00: riordino spostato FUORI dal try HACCP (un errore HACCP
  non salta più il riordino del giorno).
- /conferma marca anche le righe (prima /invia rispondeva sempre 400);
  pulisci-e-rigenera NON elimina più gli alert_mancanti (non rigenerabili);
  piano produzione legge quantita (pezzi era sempre 0); fornitore top-level
  scritto su tutte le bozze; rimossa funzione alert_ordini_admin morta.

FIFO/PREZZI:
- prezzo_kg ORA aggiornato a ogni fattura (prima restava congelato al
  primo acquisto storico: food-cost e confronto usavano prezzi vecchi;
  righe omaggio non azzerano più il prezzo noto).
- RECALL RIPARATO: storico_utilizzi.lotto_produzione restava "TEMP"
  (il numero lotto si genera dopo lo scarico) → update con array_filters;
  la risalita lotto fornitore → lotti produzione ora funziona.
- CONVERSIONE UNITÀ nel consumo FIFO (_fattore_lotto_vs_ing +
  _peso_pezzo_g_per_ing con regola uova 60/19/33 g): lotti in PZ vs
  ricette in grammi non bruciano più tutte le giacenze in un colpo.
  Stessa conversione in _riordini_post_produzione (aggregazione per
  unità → kg; match dizionario/lotti ancorati); converti_in_kg tratta i
  pezzi col peso reale (prima "5 pz" = 0,005 kg).
- /sincronizza-fatture rispetta peso_corretto_manualmente (prima
  sovrascriveva i valori corretti a mano lasciando il flag attivo).
- tipo_quantita "conteggio_confezioni" riconosciuto come alias di
  "confezioni" (la regola pezzi-per-cartone da scheda web ora scatta
  davvero alla PRIORITÀ 0); confronto-prezzi normalizza date miste
  dd/mm/yyyy vs ISO; tiebreak FIFO su scadenza parsata.

FRONTEND:
- Giacenze in OrdiniView FINALMENTE agganciate: la mappa è costruita con
  la stessa norm() dei lookup (il by_key backend usa un normalizzatore
  diverso → matchava quasi mai: badge Giac. 0, sotto-soglia persi,
  richieste lavagna sempre "da comprare").
- Alert supervisore "ordini da convalidare" → tab "ordini" (prima
  navigava su tab inesistente = pagina bianca).
- VALID_TABS completati (listino, comparatore, magazzino_prodotti,
  sconti_merce, backup, stampanti): i deep-link non muoiono più al reload.
- ListinoView: rimosso il flusso morto "invia email ai fornitori"
  (il backend risponde sempre errore) → modale solo Scarica PDF.
- RicezioneMerce: il tab Reclami ora COMMUTA la vista (prima appendeva
  in fondo) e il badge reclami aperti si popola al mount.
- OrdiniView: "chiesto da" legge richiesto_da (campo vero), PDF ordine
  con withToken; TabletView: TDZ esciAdmin + input duplicato; norm()
  unico anche in ListinoView e MateriePrimeList; soglia <= uniforme.

APERTI (di design, da decidere con calma — NON toccati):
- F8: dedup lotti import fatture per (fattura, fornitore, nome) perde la
  seconda riga stessa fattura con lotto/scadenza diversi; reimporta-da-
  fatture usa chiave diversa (canonico) → doppioni se lanciato senza
  azzera.
- F9: due normalizzazioni diverse di nome_normalizzato (import XML =
  lower grezzo; sincronizza = senza pesi) → possibili voci doppie nel
  dizionario. Da unificare con migrazione dati dedicata.
- Canonici frammentati (Crodino/Crodino Bevanda/Bevanda analcolica) →
  audit pulizia canonici in lista.

## Deploy audit LIVE + indagine import fatture da Drive (02/07/2026, sera)
- PR #104 (audit 30 fix) MERGIATA e verificata live: bundle main.2820f5d6
  su www.ceraldiapp.it, backend rideployato.
- INDAGINE per Enzo ("le fatture dovrebbero arrivare da Drive, elimina
  l'import manuale"): la premessa NON regge, verificato sul DB condiviso:
  - fatture di Lotti (1.896 doc, con xml_raw+prodotti: alimenta lotti,
    prezzi, dizionario) è riempita SOLO dall'import manuale XML.
    Ultima fattura: 11/06, importata il 14/06 — da 18 giorni non entra
    NULLA di nuovo.
  - Il flusso centralizzato Drive/PEC è dell'ALTRA app (gestionale):
    invoices (2.080 doc, solo testata + path file sul LORO server),
    drive_sync_state (ultimo sync oggi 05:17, imported 0),
    fatture_passive (73, source pec_auto). Nessuna di queste contiene le
    righe XML che servono a Lotti, e i file stanno sul filesystem
    dell'altra app (irraggiungibile da Lotti).
  - CONCLUSIONE: eliminare l'import manuale OGGI = Lotti smette di
    ricevere fatture. Per centralizzare serve un job Lotti che legga la
    cartella Drive condivisa (Google Drive API, credenziali SOLO in env
    Render) e passi gli XML nella STESSA pipeline dell'import manuale
    (stessa dedup numero+piva, stessi hook). Solo dopo si può togliere
    la card manuale. In attesa di: ID cartella Drive + credenziali da
    Enzo.

## Import centralizzato fatture da Google Drive (02/07/2026, sera — richiesta Enzo)
Contesto verificato: il sync gestionale→Lotti (invoices→fatture) ESISTEVA ed
è stato rimosso (restavano solo i commenti in fatture.py:36-44 e nel banner
scheduler, ora aggiornati). invoices ha anche il campo `linee` ma non
l'xml_raw; il gestionale sposta i file Drive in una cartella "importate"
dopo l'analisi (detto da Enzo — la cartella ancora non esiste sul Drive).

NUOVO routers/drive_fatture.py (+ job scheduler ogni 30 min, 05-22):
- scansione RICORSIVA della cartella Drive "fatture" (id di default nel
  modulo, override con env DRIVE_FATTURE_FOLDER_ID) → prende gli XML sia
  nella cartella principale sia in "importate"/sottocartelle future;
- credenziali SOLO da env Render: GOOGLE_DRIVE_API_KEY (basta, cartella
  condivisa con link) oppure GOOGLE_SERVICE_ACCOUNT_JSON (JWT RS256);
- ogni XML nuovo passa nella STESSA pipeline dell'import manuale
  (importa_fattura_xml con shim _UF): stessa estrazione p7m, stessa dedup
  upsert fornitore+numero+data, stessi hook lotti/prezzi/dizionario;
- registro drive_fatture_file (drive_id) = niente doppio download;
  stato in drive_fatture_stato; endpoints POST /drive-fatture/sync e
  GET /drive-fatture/stato (config esposta solo come bool, mai valori).
- Senza credenziali il job esce in silenzio: serve che Enzo copi la
  credenziale Google dal servizio Render del gestionale nelle env del
  backend Lotti (uno dei due nomi sopra).
- La card import manuale in Dashboard RESTA finché il sync non gira
  qualche giorno pulito: poi si rimuove (fonte unica raggiunta).

## PIN persistente 2h + ruoli + timeout magazzino (02/07/2026, sera — richiesta Enzo)
- CANCELLO A TEMPO: il PIN dell'app principale vale 2 ORE su tutte le
  pagine (localStorage lotti_gate_until, setGateOk/gateStillValid in
  auth.js). Prima era sessionStorage per-scheda: ogni scheda nuova o
  ricaricata dal browser richiedeva il PIN. Scadute le 2 ore il PIN viene
  richiesto anche se il token JWT vive ancora (comanda il cancello).
  Esci = logout completo (azzera il cancello).
- RUOLI: ADMIN_TABS in App.js (personale, controllo_dati, backoffice,
  configura, backup, stampanti) — i dipendenti navigano liberi ovunque
  tranne quelle sezioni (toast + blocco, guardia anche sui deep-link).
  QuickLink Impostazioni e Controllo Dati visibili solo all'admin.
  GoogleLoginButton ora salva il ruolo (prima isAdmin() restava false
  dopo il login Google).
- MAGAZZINO 10 MINUTI: sessione operatore del tablet magazzino scade dopo
  10 minuti dal PIN (tablet condiviso): guardia nel router tablet +
  controllo ogni 30s in MagazzinoBarView (toast + ritorno al keypad).
  Altri reparti invariati (memoria PIN 2 minuti per cambio reparto).

## Tracciabilità "chi ha inserito" negli ordini (02/07/2026 — richiesta Enzo)
Bug: nel carrello/Da inviare non si vedeva CHI aveva messo il prodotto in
ordine (né per gli inserimenti dei dipendenti né per il riordino automatico).
- Backend: campo richiesto_da su ProdottoOrdine e su TUTTE le righe create:
  motore riordino → "riordino automatico"; lavagna → nome sul post-it (o
  operatore che evade); colazione → "colazione (banco)"; post-produzione →
  "produzione <ricetta>"; aggiungi_a_bozza_riordino accetta il parametro.
- Frontend: il nome dell'operatore loggato viene salvato al login
  (saveOperatoreNome in auth.js, da PinKeypad e GoogleLoginButton); le righe
  del carrello portano richiesto_da (manuale = operatore; da lavagna = "X
  (lavagna)"); creaBozze invia operatore vero + richiesto_da per riga;
  Carrello e Da inviare mostrano "inserito da …" sotto ogni riga.

## Backoffice Prodotti&Soglie: layout + junk + soglie (02/07/2026 — screenshot Enzo)
- LAYOUT: la tabella sbordava a destra su mobile (colonne tagliate, pagina
  non centrata) → righe ridisegnate come CARD responsive (nome+semaforo+
  stock in alto, campi Soglia/Qt.+azioni sotto) e contenuto Backoffice
  centrato (max-width 1000). Bottone Riordina: source "backoffice" (via il
  fantasma automatico_giacenza) + richiesto_da operatore.
- JUNK: le righe-nota omaggio ("+1 CARTONE IN OMAGGIO", "1 CARTONE OMAGGIO
  MARHITATE") diventavano prodotti di magazzino con nomi diversi a ogni
  fattura → \bomaggi?o\b aggiunto a NON_MERCE_RE (gli omaggi veri restano
  tracciati da sconti_merce). /pulizia-dati-spazzatura ora ripulisce anche
  magazzino_bar_prodotti (junk non-merce + doppioni per nome normalizzato
  con merge dello stock).
- CATEGORIE: ZUCCHERI (glucosio/destrosio...) ora PRIMA di SCIROPPI
  ("SCIROPPO GLUCOSIO 10KG" era Bibite → è pasticceria e NON entra più nel
  magazzino bar); MONOUSO (cucchia/palett/stuzzicadent/agitator) PRIMA di
  CAFFE ("CUCCHIAINO CAFFE'" era Caffe). Verificato con test.
- NUOVO POST /magazzino-bar/soglie-imposta-tutte?soglia=&quantita=
  (&solo_mancanti): per la richiesta "metti ovunque soglia 1 e qta 1".
- DA FARE POST-DEPLOY: pulizia junk via endpoint, soglie 1/1 su tutti,
  test E2E lavagna "chiedo 2 cartoni con stock 1" (atteso: claim atomico,
  stock→0, avviso scostamento, bozza riordino creata).

## Totali ordine da gestionale + azioni DB + test E2E (02/07/2026, sera)
AZIONI ESEGUITE SUL DB LIVE (dopo merge #108):
- /pulizia-dati-spazzatura: 101 prodotti-junk eliminati dal magazzino bar,
  67 doppioni uniti (stock sommato).
- /magazzino-bar/soglie-imposta-tutte?soglia=1&quantita=1: 565 prodotti
  aggiornati (richiesta Enzo "ovunque 1 e 1").
- TEST E2E LAVAGNA (prodotto di test): richiesta 2 colli con stock 1 →
  NON si blocca, stock azzerato con avviso scostamento, DOPPIO TAP respinto
  (claim atomico ok), bozza riordino creata (source riordino_auto,
  richiesto_da "Dipendente Test"). Bozza di test eliminata; la pulizia ora
  rimuove anche i prodotti \btest\b|\bzzz\b|\bprova\b.

TOTALI ORDINE (segnalazione Enzo: +/- non aggiornava prezzi/imponibile/IVA):
- xml_helpers: parse AliquotaIVA per riga; fatture: dizionario.iva_pct
  aggiornato a ogni import (esistente+nuovo); POST /fatture/backfill-iva
  una tantum dai xml_raw archiviati (da eseguire post-deploy).
- ordini_fornitori: arricchisci_iva_righe + calcola_totali_ordine +
  _aggiorna_totali_ordine; totali {imponibile, iva, totale,
  righe_senza_prezzo, righe_senza_iva} persistiti su OGNI mutazione
  (crea, fusione cataloghi, aggiungi_a_bozza, motore riordino,
  modifica-quantita, sostituisci-prodotti).
- PDF ordine: colonne Prezzo/IVA%/Imponibile riga + righe IMPONIBILE/IVA/
  TOTALE ORDINE + nota righe senza aliquota.
- OrdiniView Da inviare: prezzo e IVA% sotto ogni riga, € riga a destra,
  blocco TotaliOrdine (imponibile/IVA/totale) ricalcolato LIVE a ogni +/-.
- Riordini sotto-soglia: quando un prodotto è nel carrello il bottone
  diventa stepper −/qta/+ (es. "7 bottiglie" direttamente dalla lista).

## Coerenza mobile: audit sistematico tabelle + limite screenshot automatici (02/07/2026)
- AUDIT: cercate tutte le `<table>` con larghezza fissa (minWidth px) che
  forzano lo scroll orizzontale su smartphone. Trovata la SECONDA (dopo
  Prodotti&Soglie già corretta) in Backoffice → tab Fornitori
  (RowFornitore, minWidth:640) → convertita in CARD responsive, stesso
  stile della tab Prodotti&Soglie (nome+badge stato sopra, azioni sotto,
  flexWrap). Le altre tabelle del progetto usano `w-full` (Tailwind, si
  restringono da sole) o sono griglie mese×frigo legittimamente larghe
  (Temperature positive/negative: matrice HACCP, overflow-x accettato
  come nei registri cartacei) — non sono difetti, non toccate.
- LIMITE AMBIENTE (per le prossime volte): il Chromium headless in questo
  sandbox NON riesce a raggiungere la rete (ERR_CONNECTION_RESET/timeout
  anche su example.com), anche passando esplicitamente dal proxy
  (127.0.0.1:40965, che invece funziona per curl/node CONNECT diretto).
  Root cause non risolta: è un limite del processo Chromium in questo
  contenitore, non del sito. CONSEGUENZA: non è possibile generare
  screenshot reali dell'app da qui — vanno chieste foto/screen a Enzo
  (come ha già fatto più volte) oppure va tentato in un ambiente diverso.

## Coerenza colori/margini con la Dashboard (screenshot Enzo, 02/07/2026)
Enzo ha inviato 5 screenshot (Dashboard di riferimento + Ordini/Giacenze +
Ordini/Confronto + Tablet Pasticceria + Fornitori) chiedendo di allineare
tutta l'app ai margini/colori della Dashboard. Trovati e corretti bug
concreti (non un redesign):
- Giacenze (OrdiniView): input `flex:1` senza `minWidth:0` non si
  restringeva e spingeva il bottone "Salva" fuori schermo su mobile
  (CSS flexbox: min-width:auto di default). Aggiunto `minWidth:0`
  all'input e, per coerenza difensiva, alle due righe `flex:1` senza
  guardia in Carrello e Da-inviare (già presente altrove nel file).
- Tablet Pasticceria: l'emoji 👤 accanto al nome operatore rende con un
  colore blu di default del sistema Android (non controllabile da CSS) →
  sostituita con icona Lucide `User` (colorabile, salvia/bianco).
  Stesso pattern trovato e corretto in DisinfestazioneView (👤/🔧 →
  User/Wrench) e StoricoProduzioniView (badge 👤 operatore).
- Audit colori "freddi" esteso oltre blue/indigo/violet: trovati e
  rimappati su salvia/sabbia anche `ring-blue-*` (7 file, focus-ring
  sfuggiti al primo giro), `cyan-*`/`sky-*` (PesceTraceabilityCard e
  altri 10 file: TemperatureNegativeView, SanificazioneView,
  SchedeRicevimentoPanel, HACCPHomeCard, FornitoriList, LottiList,
  DisinfestazioneView, AnomalieView) e `purple-*` (StoricoProduzioniView,
  ScontiMerceView, SaimaRicettariView, RegistroAllergeniView,
  ManualeHACCPView, ImportaFattureView, DuplicatiMergePanel,
  ProdottoCard) → tutti su hex arbitrari coerenti con la palette (salvia
  #5b7a6b/#3f5a4e per i toni "cyan", sabbia #8a6f47/#6f583a per i toni
  "purple", stessa scala usata per il fix cyanV in DashboardView).
- ComparatorePrezziView (tab Confronto) verificata: già coerente con lo
  stile Dashboard (salvia, Lucide, `.g-page`, `min-w-0` su ogni flex
  troncato) — nessuna modifica necessaria.
- Build frontend verificata: "Compiled successfully."

## Audit sistematico TUTTE le pagine (non solo screenshot) — 02/07/2026
Enzo ha chiesto esplicitamente di non limitarsi alle pagine delle foto ma
di controllare TUTTI i link del file collaudo_pagine.html (~40 pagine).
Fatto un audit completo con 4 ricerche mirate (HACCP, Tablet/kiosk,
Operatività, Backoffice/Admin/Listini) sui pattern di bug già noti
(flex:1 senza minWidth:0, larghezze fisse px non scrollabili, tabelle
senza overflow-x-auto). Trovati e corretti:
- TemperatureCotturaView: input prodotto senza min-w-0 spingeva il
  select ricetta fuori schermo.
- App.js: text-cyan-600 residuo nel menu Temp. Negative (sfuggito al
  giro colori precedente perché fuori da components/).
- StoricoProduzioniView: tabella con overflow-hidden invece di
  overflow-x-auto → colonne tagliate/irraggiungibili su mobile invece
  di scrollabili (bug diverso, non solo estetico).
- BackupView: lista backup a griglia fissa (1fr 90px 140px 140px,
  ~370px) dentro un contenitore overflow:hidden → colonna Azione
  tagliata su schermi stretti. Aggiunto wrapper overflowX:auto interno.
- BackofficeView (PannelloSoglieSuggerite, tab Prodotti&Soglie): span
  nome prodotto flex:1 senza minWidth:0/ellipsis, poteva spingere fuori
  gli span successivi con nomi lunghi da fattura XML.
- VenditaBancoView: due header h1 flex:1 senza minWidth:0 (dettaglio
  prodotto, tutti i prodotti).
- PannelloReparti (tablet, pannello admin non ancora raggiungibile da
  UI ma presente nel codice): stesso bug nome-ricetta senza minWidth:0.
Pagine verificate SENZA problemi (audit esplicito, nessuna modifica
necessaria): Dashboard (riferimento), TabletHome, TabletView,
MagazzinoBarView, tutti i modali tablet/*, ColazioneAcquavivaView,
PinKeypad, PageHeader, OrdiniView (resto), LottiList, GelatiView,
ImportaFattureView, MateriePrimeList, RicezioneMerceView,
CorrispettiviView, ComparatorePrezziView, RegistroHACCPView,
TemperaturePositiveView, TemperatureNegativeView, SanificazioneView,
ControlloOlioView, DisinfestazioneView, RegistroAllergeniView,
AnomalieView, ManualeHACCPView, ManualeView (Guida), ControlloDatiView,
ConfiguraWizard, StampantiConfigView, ImpostazioniPersonaleView,
ListinoView, ScontiMerceView, ProdottiVenditaView, GestioneProdottiView.
Build verificata dopo ogni gruppo di fix: "Compiled successfully."

## Colori freddi in stili inline (hex/rgba), oltre alle classi Tailwind — 02/07/2026
Il giro precedente aveva ripulito solo le classi Tailwind (bg-blue-*, text-cyan-*,
ecc.). Fatta una scansione euristica (canale blu/rosso dominante) su TUTTI gli
hex e rgba() negli stili inline di tutto frontend/src, che ha trovato molti
altri colori freddi non coperti prima:
- **App.js**: il quadratino logo nell'header globale (visibile in OGNI pagina)
  aveva un gradiente viola→salvia (#8B5CF6→#5b7a6b) invece di salvia puro —
  probabilmente il colore "diverso" più visibile di tutti, dato che compare
  su ogni schermata. Corretto in salvia→salvia (#7d9b8b→#5b7a6b).
- **App.js PAGE_META**: gli header colorati di Lotti/Sanificazione/
  Ricezione merce erano blu (#60a5fa→#2563eb) e Temperature negative era
  ciano (#67e8f9→#0891b2) — rimappati su sabbia/salvia distinti tra loro.
- **ModalRegistraLotto** (tablet, registra lotto): l'intero tema colore della
  destinazione "Abbattitore" era ciano (bottone, gradiente conferma, testo
  scadenza, badge) — rimappato su salvia scuro; il box "ordine automatico
  creato" era blu — rimappato sui colori info/sabbia già standard dell'app.
- **TabletView**: box "Cosa fare oggi" con gradiente indigo e testo
  lilla — rimappato su marrone/salvia scuro con testo salvia chiaro.
- **TabletHome**: card reparto "Produzioni al banco" era ciano — rimappata
  su salvia; box conferma "avvio turno" era blu — rimappato su verde
  successo (semanticamente corretto, è un messaggio di conferma).
- **MagazzinoBarView**: etichetta "FORNITORI" e sottotitolo header erano
  blu — rimappati su sabbia/salvia chiaro.
- **RegistroHACCPView**: card statistica "Temp. negative" blu-acciaio →
  salvia scuro (coerente con la card Temperature negative).
- **ListinoView**: colori categoria Latticini (ciano) e Zuccheri (viola)
  nel listino prodotti → sabbia/oro caldo; Pulizia (teal) → grigio caldo.
- **BackupView**: tutti gli accenti sky-blue (testo "Gestionale", data
  backup automatico, bordi/sfondi riga più recente, ombra bottone) →
  sabbia, coerenti con la palette scura del resto dell'app.
- **VenditaBancoView**: bottone "Sprechi" era viola → terracotta (danger),
  distinto dagli altri bottoni dell'header.
- **posPrint.js**: etichetta lotto "MAG:" sullo scontrino/etichetta di
  stampa era blu → salvia chiaro.
- **index.css**: `.g-badge-info`/`.g-alert-info` avevano testo blu
  (#0D4E8A) su sfondo sabbia chiaro (mismatch cromatico) → testo sabbia
  scuro (var(--info-text)), coerente con lo sfondo.
Verificato con una seconda scansione mirata su rgba() viola/indaco: nessun
altro residuo. Build verificata: "Compiled successfully."

## Dominio ceraldiapp.it senza "www" non raggiungibile (02/07/2026)
Enzo segnala "non vedo nulla" su ceraldiapp.it. Diagnosi (DNS lookup pubblico,
indipendente dal sandbox): `www.ceraldiapp.it` risolve correttamente verso
Render/Cloudflare e funziona; `ceraldiapp.it` (dominio nudo, senza www) NON
ha nessun record DNS (solo il record SOA di zona) → non risolve affatto,
browser non riesce a connettersi. Non è un bug del codice/deploy di oggi.

Ricercato su web/Render docs come si risolve (regola: cercare come altri
risolvono, non inventare) e integrato in `render.yaml`: aggiunto il campo
`domains: [www.ceraldiapp.it, ceraldiapp.it]` al servizio `lotti-frontend`
— con entrambi dichiarati, Render gestisce da solo il redirect reciproco
apex↔www una volta che il DNS è a posto.

AZIONE MANUALE RICHIESTA (richiede accesso al pannello DNS di register.it,
che io non ho): aggiungere sul dominio ceraldiapp.it, oltre al CNAME già
presente per "www", un record per l'apex ("@"):
- Preferito, se register.it supporta ANAME/ALIAS: ANAME/ALIAS su "@" →
  lotti-frontend.onrender.com
- Altrimenti (fallback, quasi certamente questo con register.it): record
  A su "@" → 216.24.57.1 (IP fisso di Render per domini apex custom)
Rimuovere eventuali record AAAA sul dominio (IPv6, causano problemi con
Render che usa solo IPv4). Dopo aver aggiunto il record, su Render Dashboard
→ lotti-frontend → Settings → Custom Domains verificare che ceraldiapp.it
risulti "Verified" (la propagazione DNS può richiedere da pochi minuti a
qualche ora).

## DNS ceraldiapp.it: procedura semplificata trovata (02/07/2026, seguito)
Enzo non vuole toccare record DNS grezzi. Cercato nella documentazione
ufficiale di register.it (il registrar del dominio, confermato dal record
SOA ns1.register.it) se esiste un modo più semplice del record A manuale.
Trovato: register.it ha una funzione dedicata "Redirect e sottodomini" nel
pannello (Area Clienti → click sul dominio → icona "Dominio & DNS" →
"Redirect e sottodomini") pensata proprio per questo caso — reindirizzare
un dominio senza smanettare con i record DNS.

PROCEDURA DA DARE A ENZO (più semplice, da provare per prima):
1. Login su register.it → Area Clienti
2. Click sul dominio ceraldiapp.it
3. Icona "Dominio & DNS" → "Redirect e sottodomini"
4. Imposta il redirect verso: https://www.ceraldiapp.it
5. Salva — attiva in pochi minuti

FALLBACK (se il redirect del pannello non accetta un indirizzo esterno,
la documentazione register.it dice che il redirect-wizard funziona "solo
per i record che puntano al loro server" — potrebbe non bastare per un
target esterno come Render): record DNS manuale, sezione "Gestione DNS
Standard" (supporta solo A/CNAME/MX):
- Tipo A, host "@", valore 216.24.57.1
- Rimuovere eventuali record AAAA sull'apex

In entrambi i casi il render.yaml è già pronto (domains: www.ceraldiapp.it
+ ceraldiapp.it) — non serve altro intervento di codice, solo l'azione sul
pannello del registrar che io non posso fare (nessun accesso).

## 4 bug reali segnalati da Enzo — investigati e corretti (02/07/2026)
Enzo ha segnalato 4 problemi concreti (non stile/margini): fornitori esclusi
ancora visibili nel listino, comparatore prezzi che non trova il migliore
tra i fornitori e non limita ai 3 mesi, una variazione prezzo assurda
("-99,9%"), e l'alert allergeni dashboard inutile/non cliccabile. Indagati
con 3 ricerche mirate nel codice (non supposizioni) prima di correggere.

**1) Fornitori esclusi (Leroy Merlin, ecc.) ancora nel Listino & Vendita**
Causa: nessuno degli endpoint di `listino.py` controllava mai
`db.fornitori.escluso` (a differenza di `fatture.py`/`lotti_fornitori.py`
che già lo fanno all'import). Corretto: aggiunta `_fornitori_esclusi()` e
applicata a `_calcola_righe` (tab "Genera listino"), `sync_da_fatture`
(tab "Catalogo prezzi"), `fornitori_elenco` (dropdown filtro). Aggiunto
lo stesso controllo anche a monte, in
`materie_prime.py::rebuild_lotti_fornitori_da_fatture` (altrimenti un
rebuild successivo reintroduce le righe del fornitore escluso). "Barra
filettata zincata"/"Set brugole" (ferramenta, non riconosciuti come
non-food): aggiunte le parole mancanti a `HARD_NONFOOD`
(classificatore_alimenti.py) e "brugola" singolare a
`_PAROLE_NON_ORDINABILI` (prodotti_master.py) — prima c'era solo il
plurale, la fattura reale usa il singolare.

**2) Comparatore prezzi**
- Il tab di default del Listino ("Genera listino") mostrava il prezzo
  dell'ULTIMA fattura arrivata, non il migliore tra i fornitori: default
  cambiato da `modo="ultimo"` a `modo="best"` (ListinoView.jsx).
- `/food-cost/confronto-prezzi` raggruppava per `ingrediente_canonico`
  quando mancava un `nome_canonico` specifico — troppo generico (es.
  "Liquori" mescolava grappa/rum/vodka/gin/whisky di marche diverse in
  un'unica scheda). Rimosso quel fallback: ora raggruppa solo per
  `nome_canonico` (per singolo prodotto) o nome normalizzato.
- Nessun filtro temporale: un fornitore non più usato da anni competeva
  nel confronto con un prezzo "storico" come se fosse attuale. Aggiunto
  filtro: scarta le varianti-fornitore con ultima fattura più vecchia di
  90 giorni.

**3) Variazione prezzo assurda ("yogurt -99,9%")**
Causa reale trovata in `calcola_prezzo_quantita_kg` (xml_helpers.py): la
"regola nota" salvata (peso confezione di un acquisto precedente) vince
sempre — ma se il fornitore cambia confezionamento (es. da secchiello 5kg
a vaschette 125g) la regola vecchia produce un prezzo_kg sballato di un
ordine di grandezza, letto come un crollo/esplosione di prezzo. Corretto
in due punti:
- `fatture.py::aggiorna_dizionario_prodotto`: se il prezzo calcolato con
  la regola nota si scosta oltre 10x dall'ultimo prezzo noto, non fidarsi
  della regola per quella riga — ricalcola ignorandola (priorità 1/2).
- Guardia residua: se anche dopo il ricalcolo lo scostamento resta ≥90%,
  non genera più l'alert "prezzo crollato/esploso" (che sarebbe comunque
  un artefatto di parsing, non un vero cambio prezzo) — solo un log.

**4) Alert "N ricette senza allergeni dichiarati"**
- Il click su una voce dell'elenco non apriva mai la ricetta: scriveva
  in sessionStorage la chiave `supervisore_apri`, letta da
  `SchedaProdottoView.jsx` — componente MAI montato nell'app reale (route
  #ricette usa `BackofficeView.jsx::TabRicette`, che legge invece
  `apri_ricetta_id`). Deep-link "orfano" esistente solo sulla carta.
  Corretto: `SupervisoreBadge.jsx` ora scrive `apri_ricetta_id` (la
  chiave che la pagina realmente montata legge davvero).
- L'alert trattava "allergeni: []" come "mai dichiarato", ma il
  rilevamento automatico da parola-chiave (`_rileva_allergeni`) gira già
  ad ogni salvataggio ricetta — una ricetta come "Funghi trifolati" può
  legittimamente non avere nessuno dei 14 allergeni UE, e restava
  comunque segnalata per sempre. Aggiunto un campo distinto
  `allergeni_verificato` (settato ad ogni create/update in base alla
  presenza di ingredienti), e l'alert del Supervisore ora guarda quello
  invece di "allergeni vuoto" — smette di segnalare ricette già
  correttamente verificate con zero allergeni. Endpoint una tantum
  `POST /ricette/backfill-allergeni-verificato` per applicare il
  rilevamento anche alle ricette esistenti create prima di questo fix
  (non sovrascrive mai allergeni già dichiarati).
- NOTA per Enzo, onestà: questo resta un rilevamento automatico "a
  parola chiave sul nome ingrediente", non una lettura degli allergeni
  reali da scheda tecnica/etichetta per OGNI ingrediente — quella fonte
  più accurata esiste già nel codice (schede_tecniche.py) ma oggi
  alimenta solo la stampa/tracciabilità, non è ancora collegata al
  salvataggio della ricetta. Collegarla è un lavoro più corposo, non
  fatto in questo giro — l'alert però ora è quantomeno corretto/utile
  invece che rumore.

Build backend (compileall + import-check, stessa procedura della CI) e
frontend verificate localmente prima del push.

## Prezzo assurdo isolato nel Listino: "Birra Corona" 0,37€ (02/07/2026, seguito)
Verificato sulla fattura ORIGINALE (DI COSMO S.R.L., n. 000000000011317/07,
20/05/2025): la riga dice letteralmente quantita=1 CT (1 cartone), prezzo
0,37€ — non è un bug del nostro calcolo, è un'anomalia nella fattura stessa
(impossibile che un cartone da 24 Corona costi 0,37€). Il duplicato esiste
perché la descrizione fattura aveva un "*" iniziale + "LATT." che la rendeva
un prodotto diverso ("* BIRRA CORONA LATT. CL33X24") da quello corretto già
presente nel listino con prezzo giusto ~23,50-24,30€/cartone ("BIRRA CORONA
CL33X24", stesso fornitore, altre 2 fatture).
Corretto in `listino.py`:
- `_norm()` ora toglie un eventuale "*" iniziale (marcatore/nota di alcuni
  fornitori in fattura, non fa parte del nome prodotto) — riduce i doppioni
  futuri dello stesso tipo.
- Nuova `_prezzo_affidabile()`: quando per lo stesso fornitore+prodotto ci
  sono PIÙ prezzi storici e il minimo è sproporzionato (oltre 8x più basso
  della mediana), usa la mediana invece del minimo — protegge da un singolo
  prezzo-fattura errato che altrimenti vincerebbe per sempre come "miglior
  prezzo" in `sync_da_fatture` (usava `min()` alla cieca).
LIMITE onesto: questo prezzo specifico (0,37€) era un caso ISOLATO — nessun
altro prezzo per confrontarlo nello stesso gruppo, quindi la protezione
automatica non lo cattura da sola (serve almeno un secondo prezzo storico
con cui confrontare). Rimosso quindi anche manualmente il record duplicato
guasto dal DB live (il prodotto corretto "BIRRA CORONA CL33X24" con il
prezzo vero resta).

Eseguita live la pulizia del record specifico dopo il deploy: DELETE
/listino/prodotti/83281d8e-... ("* BIRRA CORONA LATT. CL33X24", 0,37€) —
confermato sparito, "BIRRA CORONA CL33X24" (prezzo corretto 23,50€/21,88€)
resta regolarmente nel listino.

## Bug reale trovato dalle foto di Enzo: prezzi "-99,9%" MAI corretti dal fix precedente
Enzo ha mostrato che gli alert "Succo Yoga Magic ... prezzo diminuito del
-99.9%" (es. da €14300/kg, assurdo) erano ANCORA lì dopo il mio fix di prima,
e cliccandoci sopra apriva una ricetta a caso (Arancini) invece del prodotto.
Root cause reale (verificata sulla fattura originale, fornitore SIRO
S.R.L.): la descrizione "SUCCO YOGA MAGIC ANANAS 200ML CTX24" indica un
cartone da 24 pezzi da 200ml, ma `calcola_prezzo_quantita_kg` estraeva SOLO
il peso di UN pezzo (200ml → 0,2kg) e ci divideva il prezzo dell'INTERO
CARTONE (14,30€) invece del peso del cartone intero (24×0,2=4,8kg) →
prezzo_kg gonfiato di un fattore 24 (e per altri prodotti anche più, con
CL invece di ML che non era proprio supportato). Il mio fix precedente
(guardia su scostamento vs prezzo precedente) NON serviva a nulla qui
perché il valore sbagliato era COSTANTE nel tempo (stesso errore ad ogni
fattura), non un'oscillazione — e comunque prezzo_kg si aggiorna SOLO
quando arriva una fattura NUOVA per quel prodotto, mai retroattivamente:
il fix di prima non ha mai toccato i dati già in database.
Corretto in `xml_helpers.py`:
- Aggiunto supporto "CL" (centilitri, comune per birra/vino/bibite) a
  `estrai_quantita_da_descrizione`/`_peso_in_kg` — prima mancava del tutto.
- Nuovo rilevamento del moltiplicatore "cartone da N pezzi" (CTX24, CFX12,
  X6...): quando il peso estratto dal testo è quello di un singolo pezzo
  (≤3 kg/l) e la descrizione contiene un suffisso "X<N>" (2-60), il peso
  usato per calcolare prezzo_kg è quello dell'INTERO CARTONE, non del
  singolo pezzo.
Backend: nuovo endpoint one-time `POST /food-cost/backfill-prezzo-kg-anomali`
— ricalcola SOLO i prezzi già sopra soglia (default 500€/kg, implausibile
per pasticceria/bar) con la logica corretta, applica il nuovo valore solo
se più basso (il bug gonfia sempre, mai sgonfia), e risolve (letto:true)
le vecchie notifiche alert_prezzi con scostamento ≥90% ormai obsolete.
Corretto anche il click sull'alert prezzo: portava sempre a "route":
"ricette" (pagina generica, non related), cambiato in "comparatore" (la
pagina che mostra davvero il prodotto), sia per gli alert futuri
(fatture.py) sia per quelli già in coda (supervisor_operativo.py forza
sempre "comparatore" indipendentemente dal valore salvato).

## Bevande/alcolici: prezzo a CARTONE, mai a kg/litro (Enzo 02/07/2026)
Enzo ha respinto giustamente anche il calcolo "corretto" (2,98€/kg per un
succo, 2,97€/kg per la birra): per l'intero reparto bar (acqua, birre,
vino, prosecco, liquori, amari, sciroppi, succhi, bibite) il kg/litro
non è l'unità con cui si acquista davvero — un rum da 2L si paga a
bottiglia/cartone, non "al chilo". Corretto:
- `backend/routers/food_cost.py::confronto_prezzi`: nuovo insieme
  `CATEGORIE_VENDUTE_A_UNITA` (le stesse categorie bar di
  listino.py::CATEGORIE_ORDINATE). Per queste categorie il confronto usa
  ora `ultimo_prezzo_fattura` (prezzo di fattura per confezione/cartone,
  sempre aggiornato ad ogni import) invece di prezzo_kg per ordinare,
  scegliere il migliore e calcolare il risparmio; risposta include
  `vendita_a_unita: true/false` per categoria.
- Categoria del gruppo ora ha un fallback: se `categoria_canonica`/
  `categoria` sono vuoti (comune per molti Succhi/Birre), si usa
  `listino.py::_categoria()` (classificatore a parole chiave già
  collaudato, include già "yoga" tra le parole di SUCCHI).
- `frontend/ComparatorePrezziView.jsx`: mostra "€/cartone" invece di
  "€/kg" per queste categorie (helper `prezzoConfronto`/`unitaConfronto`),
  col prezzo €/kg-equivalente solo come riga informativa secondaria.
- `backend/routers/ingredienti.py`: aggiunti frutti mancanti nel
  dizionario canonico (Pesche, Pere, Pompelmo, "mela" singolare) — prima
  finivano genericamente sotto "Succhi" invece che nel proprio frutto,
  perché mancavano le keyword (solo "mele" plurale esisteva, non "pesca"/
  "pera"/"pompelmo" come categorie a sé).

## Seguito stesso giorno: la protezione anti-outlier copriva solo 1 dei 3 punti (02/07/2026)
Il giro precedente aveva protetto SOLO `sync_da_fatture` (rebuild manuale del
listino). Ricontrollato tutto il codice che sceglie un "miglior prezzo"/
"miglior fornitore" da più valori storici (principio "un solo bug, tutte le
occorrenze"), trovati altri 2 punti con lo stesso `min()` alla cieca:
- `listino.py::_calcola_righe` (sezione "Genera & Esporta", `modo=best`,
  usata da `/listino/calcola` e `/listino/calcola-pdf`): stessa pipeline di
  aggregazione prezzi-da-fattura di `sync_da_fatture` ma SEPARATA, quindi il
  fix precedente non la copriva — un "Birra Corona 0,37€" sarebbe potuto
  ricomparire lì. Ora usa `_prezzo_affidabile()` anche qui.
- `fatture.py` (loop import fattura, riga ~650): ad OGNI fattura importata
  (non solo al rebuild manuale) aggiorna `listino_prodotti.prezzi[fornitore]`
  con l'ultimo prezzo e sceglie `miglior_fornitore` con `min()` cieco tra i
  fornitori — questo è il path LIVE/automatico, più esposto del rebuild
  manuale. Qui non c'è uno storico multiplo per fornitore (un solo prezzo
  salvato per fornitore, sovrascritto ad ogni fattura), quindi
  `_prezzo_affidabile()` non si applica direttamente: aggiunta
  `_best_fornitore_affidabile()` in `listino.py` che usa la mediana TRA i
  fornitori come riferimento (stessa soglia 8x) e, se il minimo è un
  outlier, sceglie il fornitore più vicino alla mediana invece del minimo
  cieco. `fatture.py` ora la importa e la usa al posto del `min()` inline.
Trovato anche un TERZO punto, stessa ricerca: `prodotti_master.py::_esegui_rebuild`
(comparatore prezzi 90gg) calcolava `miglior_prezzo_90gg`/`miglior_fornitore_90gg`
con `min(prezzi_recenti, key=...)` sullo storico prezzi del prodotto canonico —
stesso identico bug, terza implementazione indipendente.

Invece di lasciare 3 copie divergenti della stessa protezione (violazione della
convenzione "un solo sistema per funzione"), centralizzato il motore in
`utils.py::valore_affidabile(items, chiave=None)` — helper puro e generico
(lista di numeri o di dict/tuple con `chiave`), sezione HELPER CONDIVISI.
`listino._prezzo_affidabile`/`_best_fornitore_affidabile` e il rebuild di
`prodotti_master` ora DELEGANO tutti a questo, invece di reimplementare la
mediana/soglia 8x ciascuno per conto proprio — una correzione futura vale
ovunque.

LIMITE onesto (stesso della sessione precedente): se un prodotto ha UN SOLO
fornitore/valore in fattura, non c'è nulla con cui confrontare e un prezzo
errato isolato non viene rilevato — serve almeno un secondo prezzo/fornitore.
Verificato con test isolati (funzioni pure, scenario Birra Corona replicato su
tutti e 3 i casi — prezzi semplici, dict {fornitore:prezzo}, dict con chiave
"prezzo"): outlier scartato quando c'è un secondo valore di confronto, prezzo
genuinamente più basso mantenuto quando è plausibile. `py_compile`/
`compileall` OK su tutti i file toccati.

## Giacenza prodotti finiti in frigo/abbattitore prima di produrre (03/07/2026)
RICHIESTA Enzo: "quando devo produrre un babà e ne abbiamo già 5 o 10 in
frigo/abbattitore, evidenziamelo e fammeli scalare/mandare al banco invece
di farmi produrre altro" — nessuna nozione di questo tipo esisteva (verificato
nel codice: `destinazione` frigo/abbattitore/banco è un concetto SOLO
frontend in `ModalRegistraLotto`, mai scritto su `db.lotti`; l'unico segnale
persistito è `frigo_numero` non vuoto = "ancora in frigo/abbattitore, non al
banco"; nessuna query esistente lo sfruttava).

- **Backend** (`lotti_produzione.py`): nuova `giacenza_prodotti_finiti(nomi)`
  — per ogni prodotto, somma i lotti non consumati/non smaltiti con
  `frigo_numero` valorizzato E non scaduti (uno scaduto non deve bloccare una
  nuova produzione). `GET /tablet/{reparto}` (ricette.py) arricchisce ogni
  prodotto con `giacenza_frigo`/`giacenza_lotti`.
  `PATCH /lotti/{id}/consuma` ora accetta `quantita` opzionale per il
  consumo PARZIALE (prima consumava sempre tutto il lotto) — retro-compatibile,
  di default invariato. Nuovo `POST /lotti/{id}/manda-al-banco` — scala il
  lotto (in tutto o in parte) e chiama direttamente `vendita_banco.
  registra_vendita_banco` con `lotto_id`/`numero_lotto` per la tracciabilità.
- **Frontend**: `CardProdotto.jsx` mostra un badge "🧊 N già pronti" sulle
  card tablet (entrambe le varianti, foto e testuale). `ModalRegistraLotto.jsx`
  — se il prodotto ha giacenza, un banner in cima elenca i lotti (quantità ·
  posizione · data produzione) con bottone "🛒 Al banco" per ciascuno; il
  bottone "Registra" resta bloccato finché la giacenza non è azzerata o
  l'operatore spunta esplicitamente "Ho controllato, voglio produrne
  comunque" — SOFT block con override deliberato, non hard block: in cucina
  può esserci un motivo legittimo per produrre comunque (es. scorta riservata
  a un ordine), quindi non impedisco mai in modo definitivo, ma il default è
  "non produrre" e serve un'azione esplicita per procedere. `TabletView.jsx`
  ricarica la lista prodotti (`carica()`) sia dopo "manda al banco" sia dopo
  una produzione registrata, così il badge si aggiorna subito.
- Build frontend (`CI=false`) verificata: "Compiled successfully", nessun
  warning. Backend: `py_compile`/`compileall` OK (non eseguibile live da
  questo ambiente — nessun accesso di rete al backend: verifica funzionale
  reale rimandata a chi ha accesso live o al prossimo deploy).

## Badge giacenza più visibile sulle card testuali (03/07/2026, seguito)
Il badge era solo testo piccolo (10px) nel footer della card, non visibile
"a colpo d'occhio" come richiesto — aggiunto lo stesso badge a pillola già
usato sulle card con foto anche come ribbon in alto sulla card testuale
(quella usata da Babà e varianti pasticceria senza foto). Build verificata.

## PIN admin tablet persistente 2h + velocità "manda al banco" (03/07/2026, seguito)
Enzo, dopo il primo deploy: (1) il badge giacenza era troppo piccolo/in
fondo alla card — sistemato nel commit precedente; (2) uscendo con "🔒 Esci"
da una card reparto (es. pasticceria) e rientrando, il PIN amministratore
veniva richiesto di nuovo — "deve persistere per due ore" come il cancello
principale; (3) mandare al banco i pezzi già in frigo/abbattitore era lento.

**PIN admin 2h**: verificato che NON esisteva alcuna persistenza per il PIN
admin del tablet (diverso dal cancello principale `lotti_gate_until` in
`auth.js`, che è il JWT del gestionale) — ogni "Esci" richiedeva sempre il
keypad, `TabletHome.jsx` scriveva un `ts` in sessionStorage MAI riletto.
Aggiunto in `auth.js`: `setAdminGateOk()`/`adminGateStillValid()`/
`clearAdminGate()` — stesso principio del cancello (finestra di 2h) ma
chiave e storage separati (`tablet_admin_until`, sessionStorage: legato al
turno sul tablet condiviso, non deve sopravvivere alla chiusura del
browser). Collegato in `TabletHome.jsx` ("🔒 Esci gestionale") e
`TabletView.jsx` ("🔒 Esci"): il bottone controlla `adminGateStillValid()`
PRIMA di mostrare il keypad — se valido esce subito, altrimenti chiede il
PIN come sempre e alla verifica riuscita apre la finestra di 2h.
ATTENZIONE: in `TabletView.jsx` la finestra si apre SOLO nel wrapper
dedicato (`adminVerificatoEEsci`), non dentro `esciAdmin` stesso — quella
funzione è chiamata anche da `MagazzinoBarView.onBack` SENZA passare dal PIN
admin, quindi aprire lì la finestra avrebbe indebolito la sicurezza (uscita
dalla lavagna magazzino avrebbe regalato 2h di grazia admin senza PIN).

**Velocità "manda al banco"**: nessuna lentezza lato backend (find_one+
update_one+insert_one, normale). La lentezza percepita era UX: (1) dopo aver
mandato un lotto il modale restava aperto anche a giacenza azzerata,
serviva un tap in più per chiuderlo — ora si chiude da solo mezzo secondo
dopo l'ultimo lotto mandato; (2) con più lotti dello stesso prodotto (es.
avanzi di ieri + di oggi) serviva un tap "Al banco" per ciascuno — aggiunto
bottone "🛒 Tutto (N)" quando ce n'è più di uno, che li manda tutti in
sequenza con un solo tap e poi chiude.
Build frontend verificata: "Compiled successfully", nessun warning.

## Audit critico completo — rilette TUTTE le richieste passate (03/07/2026)
Richiesta Enzo: analisi critica di tutte le funzionalità, riverificare che
tutto funzioni come chiesto rileggendo l'intera memoria di progetto, per
suggerire funzionalità operative migliorative. Nessun accesso ad "altre chat"
oltre questo repo: fonte = STATO.md (2694 righe, ~110 richieste distinte,
digerito in 5 blocchi paralleli) + PRD.md/claude.md/DOCUMENTAZIONE.md/
docs/*.md, incrociato col codice reale dove rilevante. Consegnato un report
HTML (artifact di sessione, non persistito su disco) con: pilastri
verificati, nodi critici ricorrenti, checklist "in attesa di Enzo", 9
suggerimenti nuovi.

**Scoperte principali (non ovvie da un solo giro di lavoro):**
- Il bug FIFO "ramo else non converte le unità" (la domanda originale di
  Enzo sui 5g di pomodoro), rimasto esplicitamente aperto per 3 sessioni
  separate (01/07), risulta INVECE già chiuso il 02/07
  (`_fattore_lotto_vs_ing`, sezione "AUDIT COMPLETO") — verificato nel
  codice attuale (lotti_produzione.py righe 617-707). Buona notizia non
  ancora "certificata" prima d'ora.
- I canonici frammentati (stile "Crodino"/"Crodino Bevanda") sono stati
  scoperti e rimandati a "un audit di pulizia" in ALMENO 3 sessioni diverse
  senza che quell'audit sia mai stato eseguito come giro dedicato — pattern
  ricorrente, non un bug isolato.
- `docs/PANORAMICA_APP.md` (audit precedente, con 15 suggerimenti
  migliorativi) risulta in parte superato: la sezione "Corrispettivi +
  previsione + festività" che proponeva come idea futura è INVECE già
  costruita e collegata (`corrispettivi.py::previsione/festivita-imminenti/
  correlazione-ordini`, consumata da `CorrispettiviView.jsx`) — verificato
  con grep mirato, non risultava esplicitamente in nessuna sessione STATO.md
  letta, quindi rischiava di passare per "mai fatto".
- `PannelloReparti.jsx` conferma: `setShowAdmin(true)` non è chiamato da
  nessun bottone in tutto TabletView.jsx — codice morto/irraggiungibile,
  presente da settimane (già notato di sfuggita il 02/07, qui verificato
  puntualmente).
- CI (`.github/workflows/ci.yml`) esegue `compileall` + import-check +
  build frontend, MAI `pytest` — i 20+ file in `backend/tests/` (inclusi
  quelli aggiunti oggi) non sono collegati alla pipeline.
- Documentazione di progetto disallineata: `memory/PRD.md`/`memory/claude.md`
  fermi ad aprile, `DOCUMENTAZIONE.md`/`docs/CONSOLIDAMENTO.md` descrivono
  ancora `ordini-app.html`/`OrdiniSmartView` (eliminati da settimane) — sono
  proprio i file che `CLAUDE.md` istruisce di leggere per primi.
Nessuna modifica al codice in questa sessione (solo analisi + report).
PROSSIMO PASSO possibile, se Enzo lo conferma: aggiornare i file di memoria
stale, collegare/rimuovere PannelloReparti, aggiungere pytest alla CI.

## Quantità scelta a mano su "manda al banco" (03/07/2026)
RICHIESTA Enzo (screenshot, babà Mignon con 301 pz in giacenza): "Al banco"
mandava sempre TUTTO il lotto in un colpo — voleva scegliere quanti pezzi
(es. 24 su 301). Il backend (`POST /lotti/{id}/manda-al-banco`) supportava
già `pezzi` come quantità parziale (costruito il 03/07 mattina), mancava
solo l'UI: era cablato per inviare sempre `lotto.quantita` intera.
- `ModalRegistraLotto.jsx`: aggiunto stepper −/numero/+ (con scorciatoia
  "tutto") su ogni riga lotto del banner giacenza; il bottone "Al banco"
  ora manda la quantità scelta, non l'intero lotto. Se resta un residuo dopo
  un invio parziale, il lotto RESTA nel banner con la quantità residua
  aggiornata (non sparisce), coerente col fatto che il lotto in DB non è
  esaurito. "Manda tutto (N)" invariato: ignora le quantità parziali
  eventualmente digitate e manda sempre l'intero residuo di ogni lotto.
Build frontend verificata: "Compiled successfully".

RICHIESTA collegata, PIÙ GROSSA, ANCORA DA PROGETTARE (stesso messaggio):
Enzo vuole che i cornetti "vuoti" (semilavorato in frigo/abbattitore)
vengano prelevati in quantità N e AUTOMATICAMENTE divisi nei gusti (crema,
cioccolato, marmellata, crema-amarena, più i vuoti che restano tali) secondo
le proporzioni già impostate nel preset stagionale di Colazione, scaricando
per ciascun gruppo la dose dell'ingrediente di farcitura e registrando il
prodotto finito giusto in vendita al banco.
VERIFICATO NEL CODICE (nessuna implementazione ancora, solo indagine): il
preset Colazione (`colazione_template`, via `colazione.py`) salva già
`pezzi` assoluti per ogni gusto per stagione, MA ogni gusto è un
`prodotto_id`/ricetta INDIPENDENTE — zero legame dati tra "Cornetto Vuoto"
e "Cornetto alla Crema" (né una nozione di dose farcitura da nessuna
parte). Il pattern più vicino esistente (`ricetta_base_id`+
`ingrediente_variante`) tocca SOLO costo/etichetta, non magazzino/vendita
banco. Serve un concetto nuovo end-to-end: legare i gusti "figli" al
prodotto-base nel preset Colazione + dose farcitura per gusto + scarico
magazzino/registrazione vendita_banco al momento dello scarico giacenza.
NON avviata l'implementazione: chieste a Enzo 3 conferme prima di
progettare i dati (divisione sempre automatica da Colazione o correggibile
a mano volta per volta; dosi farcitura le fornisce lui gusto per gusto o le
ha già pronte; ambito solo cornetti o esteso ad altri semilavorati) — il
tool delle domande a scelta multipla ha fallito due volte in questa
sessione (stream chiuso), richieste in chat testuale, risposta non ancora
arrivata a fine sessione.

## Colazione: "Aggiungi prodotti" cercava solo Acquaviva, mai i dolci/salati fatti in casa (03/07/2026)
RICHIESTA Enzo (screenshot: cerca "Cornett" in "Aggiungi prodotti alla
colazione", trova solo "CORNETTO DRITTO VUOTO GLASSATO" Acquaviva). Causa
verificata: `GET /colazione-acquaviva/prodotti-disponibili?catalogo=true`
interrogava SOLO `db.acquaviva_prodotti` filtrato per `fonti_attive
("colazione")` (Acquaviva/Vandemoortele) — mai `db.ricette`.
Corretto in `colazione.py`: la stessa risposta ora include anche le ricette
di pasticceria/rosticceria (`reparto in [pasticceria, rosticceria]`), con
`fonte:"casa"` e `gia_acquistato:true` (per non mostrare il fuorviante "mai
acquistato" su un prodotto che si produce ogni giorno). Lista finale
riordinata per nome, Acquaviva+casa mescolati insieme nella stessa ricerca.
Frontend `ColazioneAcquavivaView.jsx`: badge "🏠 fatto in casa" sulla card
quando `fonte==="casa"`, per non confondere un prodotto nostro con
l'omonimo/simile di Acquaviva. Nessuna modifica al salvataggio del preset
(`aggiungi-prodotto`/`registra`) — erano già generici, non assumevano la
provenienza Acquaviva.
Build frontend/backend verificate. NOTA: questo sblocca in parte la
richiesta più grossa sui "cornetti farciti" (i cornetti fatti in casa ora
sono selezionabili in Colazione) ma non la implementa — restano da
chiarire le 3 domande della sezione precedente prima di costruire la
divisione automatica nei gusti e lo scarico farcitura.

## Colazione: fascia "Più usati" per non scorrere tutto il catalogo (03/07/2026)
RICHIESTA Enzo: un pulsante o una ricerca predittiva per i prodotti più
usati, per non dover sfogliare tutto il catalogo ad ogni ricerca.
Implementato: nuovo `GET /colazione-acquaviva/prodotti-piu-usati?limit=N`
— conta in QUANTI preset stagionali compare ciascun prodotto (aggregazione
su `db.colazione_template`, nessun dato inventato: usa solo le scelte già
fatte da Enzo nelle stagioni esistenti), ordina per frequenza discendente.
Frontend `ColazioneAcquavivaView.jsx`: fascia orizzontale "⭐ Più usati" con
chip toccabili sopra la ricerca in "Aggiungi prodotti", visibile solo a
ricerca vuota (si nasconde mentre si digita, per non affollare). Riusa lo
stesso `toggleProdotto`/segno ✓ della griglia principale.
Build frontend/backend verificate.

## Farciture: cornetti divisi nei gusti dalla giacenza (03/07/2026)
RICHIESTE Enzo (risposte alle 3 domande della sessione precedente + nuove):
1. Solo cornetti per ora. 2. Dose farcitura 20g. 3. Divisione SEMPRE dalle
proporzioni già impostate in Colazione, scalata sulla quantità prelevata
(es. 4+4+4+4+4=20 configurati -> prelievo 40 -> 8 ciascuno), MODIFICABILE
sul momento (niente blocco che obbliga a uscire e cambiare Colazione).
Ingredienti farcitura (nomi CANONICI, non descrizioni-fattura grezze —
esplicitamente richiesto da Enzo di riusare il motore canonico esistente,
non un match nuovo): crema->Crema Pasticcera, cioccolato->Cioccolato
Nocciola, marmellata->Marmellata Albicocca, crema e amarena->Crema
Pasticcera + (Amarena o Visciola, alternative). IPOTESI da confermare:
"crema e amarena" = 20g di ENTRAMBI i componenti (40g totali), non chiarito
esplicitamente da Enzo — segnalata nel file.

**Implementato**:
- `backend/data/farciture.json` — nuovo file di config (stesso pattern di
  `schede_prodotti.json`): mappa gusto -> ingredienti canonici + dose_g,
  con alternative in ordine di priorità. Inviato a Enzo per completarlo.
- Nuovo `backend/routers/farciture.py` (registrato in server.py):
  - `GET /farciture/prodotto-base/{nome}` — dice se un prodotto ha
    farciture configurate (frontend lo usa per mostrare/nascondere il
    bottone).
  - `GET /farciture/anteprima-divisione` — legge le proporzioni da
    `colazione_template` per la stagione data, le scala sulla quantità
    richiesta con riparto a resto più grande (`_riparto_proporzionale`,
    funzione pura, somma sempre esatta — testata: `tests/
    test_farciture_riparto.py`, 5 casi incl. multiplo esatto, non
    divisibile, proporzioni sbilanciate, zero pezzi).
  - `POST /farciture/{lotto_id}/dividi-e-manda-al-banco` — scala la
    giacenza del lotto base per il totale; per ogni gusto farcito
    RIUSA `scala_lotti_fornitori_per_ricetta` (stesso motore FIFO delle
    ricette, "ricetta virtuale" con solo gli ingredienti di farcitura,
    moltiplicatore = pezzi di quel gusto) — nessun sistema di scarico
    parallelo. Il gusto "vuoto" non scarica farcitura. Ogni gruppo
    registrato in `vendita_banco` sotto il prodotto Colazione giusto
    (match nome a CONFINI DI PAROLA, non sottostringa nuda — stesso bug
    già visto altrove nel progetto con match troppo larghi).
- Frontend `ModalRegistraLotto.jsx`: sulla giacenza di un prodotto con
  farciture configurate, bottone "🥐 Dividi nei gusti" che apre un
  pannello con selettore stagione, anteprima calcolata automaticamente
  E MODIFICABILE (stepper numerici, come richiesto — nessun blocco),
  conferma che chiude e ricarica la lista.
- Match gusto<->item Colazione: cerca "crema"/"cioccolato"/ecc. nel nome
  dell'item (es. "Cornetto alla Crema") a confini di parola.

**NON verificato dal vivo** (limite ambiente, nessun accesso di rete al
backend): la logica è stata testata solo a livello di calcolo puro
(riparto proporzionale) e compilazione. Il collegamento reale FIFO
(l'ingrediente canonico "Amarena" trova davvero il lotto giusto in
giacenza) va provato con una vera farcitura sul tablet prima di fidarsene
in produzione — è esattamente il tipo di funzionalità che la convenzione
del progetto dice di collaudare con dati veri, non solo dichiarare pronta
leggendo il codice.
**RESTA APERTO**: file `farciture.json` da completare con Enzo (dose
esatta "crema e amarena", altri gusti/prodotti oltre ai cornetti). La
sezione "ricette" del file di lavoro richiesta da Enzo (tutte le ricette
con la logica di normalizzazione del vecchio Excel) NON è stata creata:
Enzo aveva dato quel foglio in una sessione precedente non accessibile da
qui, e non c'è accesso di rete al DB live per estrarre le ricette attuali
— serve che le riscriva/carichi di nuovo, oppure va fatto in una sessione
con accesso live.

## Colazione: stagione automatica per data + preferiti "asterisco" (03/07/2026)
RICHIESTE Enzo (2, dopo aver confermato di voler continuare a lavorare su
Colazione):

**1. Switch automatico di stagione per data** (equinozi/solstizi,
modificabili): oggi bisognava scegliere a mano la stagione ogni volta.
Implementato in `colazione.py`:
- `_DATE_STAGIONI_DEFAULT` — periodi di default MM-DD per le 4 stagioni
  standard (Primavera 03-21/06-20, Estiva 06-21/09-22, Autunnale
  09-23/12-20, Invernale 12-21/03-20 — quest'ultimo attraversa il
  capodanno). Seed SOLO al primo avvio (`$setOnInsert`, non sovrascrive
  periodi già modificati da Enzo).
- `_data_in_periodo()` — funzione pura, gestisce il wraparound capodanno.
  Verificato che i 4 periodi coprano OGNI giorno dell'anno esattamente una
  volta (test su tutti i 366 giorni, incluso 29 febbraio):
  `tests/test_colazione_stagioni.py`, 5 test.
- Nuovo `GET /stagione-attiva` — dice quale stagione contiene oggi.
- Nuovo `PUT /preset/{nome}/periodo` — Enzo corregge le date se il suo
  "periodo estivo" reale non coincide con quello astronomico.
- Frontend: al caricamento la stagione si pre-seleziona da sola (invece
  del primo preset della lista); riga "📅 In vigore dal.. al.." con
  modifica inline (due campi MM-GG + Salva) sotto il selettore stagione.

**2. Preferiti "l'asterisco"** (richiesta testuale Enzo: "* deve essere
accanto ad ogni prodotto... ovunque io inserisco l'asterisco il prodotto
viene scelto come prodotto da inserire in colazione... per tutti e
quattro i periodi"): marcare una stella su un prodotto lo aggiunge SUBITO
a tutte e 4 le stagioni standard (pezzi default 6), senza dover cercare
il prodotto nel modale colazione ogni volta che torna la stagione.
Implementato in `colazione.py`:
- Nuova collezione `colazione_preferiti` (id prodotto + metadati).
- `GET /preferiti` (lista id), `POST /preferito` (toggle: aggiunge/toglie
  il flag; se aggiunge, inserisce il prodotto in TUTTE le 4 stagioni MA
  salta le stagioni dove è già presente — non sovrascrive quantità già
  tarate a mano). Togliere la stella NON rimuove il prodotto dalle
  stagioni già configurate (si toglie a mano con la ✕ già esistente lì):
  scelta deliberata, non distruttiva.
- Frontend: stella ☆/★ in alto a sinistra su ogni card della griglia
  "Aggiungi prodotti" (`stopPropagation` per non confonderla col tap che
  aggiunge/toglie dalla sola stagione corrente).

**LIMITE ONESTO su "ovunque" (dichiarato esplicitamente a Enzo prima di
costruire)**: la stella funziona oggi SOLO nella ricerca di Colazione,
che dopo il fix di ieri copre già Acquaviva/Vandemoortele + ricette/casa.
Enzo ha chiesto "ovunque" includendo Saima, Alfa (senza glutine),
Sammontana, Tre Marie — questi vivono OGGI in cataloghi separati e non
unificati nel codice (Alfa ha un flusso a parte per il "manda al banco"
senza glutine; Saima/MePA/Tre Marie sono cataloghi fornitore indipendenti,
la loro unificazione in un sistema "Cataloghi fornitori" è già annotata
altrove in questo file come lavoro futuro non iniziato). Estendere la
stella lì richiede prima quel lavoro di unificazione — non fatto qui per
non costruire un meccanismo parallelo duplicato per ogni catalogo.
Build frontend/backend verificate, test puri passati (23 su 23, esclusi
gli 8 test di integrazione preesistenti che richiedono un server live —
stesso limite ambientale di sempre, non collegati a queste modifiche).

## Preferiti colazione estesi a Saima/MePA (03/07/2026, seguito)
RICHIESTA Enzo: la stella deve stare anche nelle schermate Saima/Tre Marie,
riusando la stessa logica (stella = va in colazione, "aggiungi al
carrello" resta l'azione separata per l'ordine al fornitore — confermato
essere due azioni indipendenti sullo stesso prodotto).
VERIFICATO: **Saima ha già una schermata** (`CatalogoFornitoreView.jsx`,
condivisa con MePA — stesso componente, prop `fornitore="saima"|"mepa"`),
con un pattern di badge d'angolo già pronto da imitare (spunta verde
"già nel dizionario"). **Tre Marie NON ha alcuna schermata**: esiste solo
come dato backend (`catalogo_forno_prodotti`, importato da PDF per
"ordini futuri", mai collegato a nessuna UI) — verificato con grep
sull'intero frontend, zero risultati. Lo schema Tre Marie non ha nemmeno
un campo `id` stabile (solo la coppia fornitore+codice_articolo) né un
campo foto: prima di metterci la stella serve costruire l'intera
schermata di sfoglio (lavoro diverso, più grosso, non un aggiustamento).
Segnalato a Enzo, in attesa di conferma se procedere.

**Implementato (Saima + MePA, stesso componente)**:
- `CatalogoFornitoreView.jsx`: nuovo stato `preferitiColazione` (fetch da
  `GET /colazione-acquaviva/preferiti`, stesso endpoint già esistente —
  nessun backend nuovo, il meccanismo è generico per costruzione), stella
  ☆/★ su `CardProdotto` (angolo in alto a sinistra, accanto alla spunta
  verde) e su `RigaProdotto` (vista lista, accanto al prezzo). Mapping
  campi Saima/MePA -> preferiti: `id`->prodotto_id, `nome_display||nome`,
  `immagine_url`->foto_url (NON `foto_url`, nome campo diverso da
  Acquaviva/ricette — verificato per non ripetere l'errore), prezzo via
  l'helper `prezzoProdotto()` già esistente nel file (fallback tra
  prezzo_listino/prezzo_kg/prezzo_acquisto_confezione/prezzo_singolo).
- NON toccato il pulsante "+ Aggiungi all'ordine" (carrello) — resta
  un'azione indipendente, come confermato da Enzo.
Build frontend verificata: "Compiled successfully".

## Schermata Tre Marie + pagina unica cataloghi fornitori (03/07/2026, seguito)
RICHIESTA Enzo: costruire da zero la schermata Tre Marie (non esisteva,
vedi limite segnalato sopra) e portare Saima, Acquaviva, Alfa, MePA,
Il Pasticcere, Sammontana e Tre Marie in un'unica pagina.

**Trovato**: `ProdottiVenditaView.jsx` è GIÀ la pagina unica con tab
(`#prodotti/saima`, `#prodotti/mepa` ecc.) — non serve costruirne una
nuova, basta estenderla con nuovi tab.

**Implementato**:
- Nuovo componente riusabile `CatalogoGenericoView.jsx`: griglia con
  ricerca, stella "preferito colazione" (stesso `POST
  /colazione-acquaviva/preferito` di Saima/MePA — nessun backend nuovo)
  e "+ Aggiungi all'ordine" (riusa il carrello condiviso di
  `CatalogoFornitoreView.jsx`, esportate le utility `useCart`,
  `leggiCarrello`, `salvaCarrello`, `prezzoProdotto` per non duplicarle).
  A differenza di Saima/MePA non fa scraping live: legge prodotti già
  presenti nel DB (`catalogo_forno_prodotti`, import da PDF/listino) o da
  un endpoint esistente (Alfa). Se non ci sono ancora prodotti mostra uno
  stato vuoto onesto invece di inventare un catalogo.
- 4 nuovi tab in `ProdottiVenditaView.jsx`:
  - **Il Pasticcere** e **Tre Marie**: `GET /catalogo-forno/prodotti?
    fornitore=pasticcere|tremarie` (router già esistente, mai collegato
    a una UI). Oggi il DB non ha ancora nessun prodotto con questi
    `fornitore` — la schermata Tre Marie esiste e funziona, ma resta
    vuota finché non arriva un listino/PDF da importare (stesso
    procedimento già usato per gli altri cataloghi forno).
  - **Alfa (senza glutine)**: riusa `GET /acquaviva/prodotti/senza-
    glutine`, già esistente e con dati reali.
  - **Sammontana**: tab creato ma senza `fetchUrl` (nessuna fonte dati
    oggi) — mostra stato vuoto con messaggio esplicito che serve un
    listino/PDF o l'indirizzo del sito da Enzo.
- Colori tab scelti nel rispetto della palette del progetto (mai colori
  freddi): amber per Il Pasticcere/Alfa, rose per Tre Marie, orange per
  Sammontana (non `sky`/azzurro, sostituito perché colore freddo).

**LIMITE ONESTO**: questo sandbox non ha accesso di rete a nessun sito
esterno (verificato con curl su ilpasticceresrl.it, tremarie.it,
sammontana.it/.com — tutti falliscono con tunnel/403, stesso limite già
riscontrato per il backend live), quindi non è stato possibile fare lo
scraping automatico richiesto ("come hai fatto per Saima"). Lo scraper
Saima/MePA esistente funziona perché gira lato server su Render, non da
qui. Per avere dati reali servono: un listino/PDF da Enzo (stesso
procedimento già usato per il catalogo forno) oppure gli indirizzi web
pubblici esatti dei cataloghi, da usare in una sessione con rete live
per scrivere uno scraper dedicato sul modello di quello Saima.
Build backend (compileall + import-check) e frontend ("Compiled
successfully") verificate. Non ancora testato dal vivo sul tablet.

## Connettore "incolla il link" + import cataloghi da PDF (03/07/2026, seguito)
RICHIESTA Enzo: (1) prendere i cataloghi da ilpasticcere.it, sammontana.it,
tremarie.sammontanaitalia.it "come per Saima"; (2) una pagina in
Impostazioni dove incollare l'indirizzo di un fornitore e il sistema
"capisce cosa fare", per aggiungere cataloghi in futuro senza sviluppo
dedicato ogni volta. Poi Enzo ha caricato in chat i PDF ufficiali 2026
di Tre Marie e Il Pasticcere ("prendi tutte le informazioni anche da
qua se non le hai prese").

**(2) Nuova pagina admin "Cataloghi Fornitori (web)"** — `#cataloghi_esterni`,
protetta come le altre pagine admin (`ADMIN_TABS` in App.js).
- Backend nuovo `routers/fonti_catalogo.py`: Enzo aggiunge {nome, url},
  bottone "Sincronizza" lancia un connettore GENERICO (no scraper scritto
  a mano per ogni sito): cerca la sitemap del dominio, individua le URL
  che sembrano schede prodotto, legge i dati strutturati Schema.org
  (JSON-LD "Product" — quasi tutti gli e-commerce moderni lo generano per
  la SEO) o in mancanza i tag Open Graph. Scrive i prodotti trovati nella
  STESSA collezione di catalogo_forno.py (`catalogo_forno_prodotti`,
  chiave fornitore+codice), niente sistema parallelo. Se il sito non
  espone nulla di riconoscibile, la fonte resta onestamente in stato
  "errore" col motivo — MAI un catalogo inventato.
  5 test puri su `_estrai_prodotto_da_html`/`_slugify` (JSON-LD singolo,
  JSON-LD in lista mista, fallback Open Graph, nessun dato, slug nome).
- **LIMITE ONESTO dichiarato in pagina**: è un tentativo best-effort, non
  garantito — il vero esito si vede solo dopo "Sincronizza" girato sul
  backend live (che ha accesso a internet, a differenza di questo
  sandbox). Non ancora testato contro i 3 siti reali.

**(1) Cataloghi Il Pasticcere + Tre Marie da PDF reali** — Enzo ha
caricato in chat `catalogo_pasticcere_2026.pdf` (43 pagine) e
`TM_catalogo_2026_low.pdf` (53 pagine), i cataloghi ufficiali 2026.
Trascritti (lettura visiva pagina per pagina, non OCR automatico, per
evitare errori sui codici) TUTTI i prodotti con nome, codice articolo,
grammatura, pezzi per cartone, gamma/categoria: **111 prodotti Il
Pasticcere + 112 prodotti Tre Marie**, salvati in
`backend/data/catalogo_forno_pasticcere_2026.json` e
`catalogo_forno_tremarie_2026.json`. NESSUN prezzo inventato: questi
cataloghi B2B non riportano prezzi (regola del progetto: prezzo SOLO da
fatture reali), niente foto scaricate (i PDF non hanno URL immagine
utilizzabili — restano coi placeholder pacco finché non arriva una
fattura/foto reale).
- `catalogo_forno.py`: nuovo `POST /catalogo-forno/importa-precaricato?
  fornitore=pasticcere|tremarie` — legge il JSON bundlato nel repo e fa
  lo stesso upsert di `/importa` (chiave fornitore+codice_articolo,
  ri-eseguibile senza duplicare).
- `CatalogoGenericoView.jsx`: nuovo bottone opzionale "Importa dal
  catalogo PDF 2026" (prop `importaPrecaricatoUrl`), mostrato SOLO sui
  tab Il Pasticcere/Tre Marie in `ProdottiVenditaView.jsx` — un tap e i
  111/112 prodotti compaiono nella schermata, con stella preferiti
  colazione e aggiungi al carrello ordini già funzionanti (stessa logica
  degli altri cataloghi).
- Verificato: JSON validi, nessun codice duplicato in nessuno dei due
  file, tutti i campi obbligatori presenti.
Build backend (compileall + import-check) e frontend ("Compiled
successfully") verificate. Import "vero" (bottone in pagina) da testare
dal vivo sul backend live dopo il deploy — questo sandbox non ha un
Mongo raggiungibile per una prova end-to-end qui.
Ancora mancante: Sammontana (nessun catalogo PDF ricevuto), foto
prodotto reali per Il Pasticcere/Tre Marie (arriveranno da fatture o da
un file immagini a parte se Enzo lo fornisce).

## Catalogo Bindi da 7 PDF (03/07/2026, seguito)
RICHIESTA Enzo: "poi ci sono i cataloghi di Bindi fai lo stesso lavoro qua"
— 7 PDF caricati in chat: Primavera Estate 2022/2023/2024, Autunno
Inverno 2022, Collezione Autunno Inverno 2023-24, Collezione 2025,
Collezione (novità) 2026.

SCOPERTA: a differenza di Tre Marie/Il Pasticcere (cataloghi-libro con
testo sparso su più colonne, servita lettura visiva pagina per pagina),
i PDF Bindi hanno un layer di testo pulito e lineare — estratto
direttamente nome prodotto/Cod./grammatura/pezzi/confezione con uno
script Python (PyMuPDF), senza bisogno di lettura visiva: più veloce
E più affidabile (testo vero, non trascrizione a vista). Un solo file
(Primavera Estate 2024) aveva il layer testo delle pagine-banner
corrotto (font custom) ma le pagine prodotto erano leggibili lo stesso.
Nota: Bindi risulta oggi ANCH'ESSA parte del gruppo Sammontana Italia
S.p.A. Società Benefit (stesso testo istituzionale già visto nei
cataloghi Tre Marie/Sammontana).

Trascritti **89 prodotti unici** (nessuna sovrapposizione di codice tra
le 7 edizioni tranne "Kit Millefoglie" cod. 1527, presente identico in
due cataloghi — normale, upsert per codice lo gestisce da solo) in
`backend/data/catalogo_forno_bindi_2022_2026.json`: monoporzioni, torte
pretagliate, semifreddi, gelati/coppe/mochi, croissanteria/colazione,
salato (focacce, panzerotti), creme in sac à poche, linea vegana.
Nessun prezzo (questi cataloghi B2B non lo riportano, come già per gli
altri — resta solo da fattura).
- Aggiunto `"bindi"` a `_CATALOGHI_PRECARICATI` in `catalogo_forno.py`
  (stesso `POST /catalogo-forno/importa-precaricato?fornitore=bindi`,
  nessun endpoint nuovo).
- Nuovo tab "Bindi" (colore `yellow`, palette rispettata) in
  `ProdottiVenditaView.jsx` con bottone "Importa dai cataloghi PDF
  2022-2026" — stessa UX di Il Pasticcere/Tre Marie.
Build backend (compileall + import-check) e frontend ("Compiled
successfully") verificate. Import vero da testare dal vivo dopo il
deploy (nessun Mongo raggiungibile da qui).

## Prezzi da fatture agganciati a TUTTI i cataloghi (03/07/2026, seguito)
RICHIESTA Enzo: "quando ricevi una fattura e leggi un articolo tra le
righe XML devi importare il prezzo e l'eventuale quantità per cartone
nei cataloghi corrispondenti, così sfogliando si vede dal prezzo che
quel prodotto è già stato comprato" + semplificazione critica della
sezione ordini/cataloghi.

**Scelta architetturale (semplificazione vera)**: NON un nuovo writer
all'import fattura, ma estensione del MOTORE UNICO già esistente
(`prezzi_fatture_per_fornitore` + `applica_prezzo_da_fatture` in
`routers/utils.py`, già usato da Saima/MePA/Acquaviva/Colazione).
L'aggancio avviene in LETTURA (GET): sempre fresco, zero sync da
ricordare, zero doppioni. Un prodotto di catalogo mostra il prezzo SOLO
se matcha una riga fattura reale — il prezzo visibile È il segnale
"già comprato".

Implementato:
- `utils.py`: `applica_prezzo_da_fatture` ora imposta anche
  `quantita_ultima_fattura` (quantità dell'ultima riga fattura) sui
  prodotti matchati; il tokenizzatore fuzzy ora NORMALIZZA GLI ACCENTI
  ("Davì"/"Jolì" in catalogo vs "davi"/"joli" in fattura non matchavano —
  bug reale scoperto scrivendo i test, rilevante per i nuovi cataloghi
  pieni di nomi accentati). Beneficia anche Saima/MePA/Acquaviva.
- `catalogo_forno.py`: `GET /prodotti?fornitore=...` aggancia i prezzi
  fattura via mappa `_FORNITORE_FATTURA_MATCH` (pasticcere/tremarie/
  sammontana/bindi → sottostringhe ragione sociale; NOTA: Tre Marie e
  Bindi fatturano oggi come gruppo "Sammontana Italia", la distinzione
  la fa il match sul nome prodotto).
- `acquaviva.py`: anche `GET /prodotti/senza-glutine` (tab Alfa +
  ModalAlpha tablet) ora passa dal motore unico — prima NON agganciava
  i prezzi (incoerenza sanata, stessa regola ovunque).
- Frontend `CatalogoGenericoView`/`ProdottiVenditaView`: la card mostra
  grammatura + pezzi/cartone (dal catalogo PDF) e, se comprato, prezzo
  verde + badge "✓ già comprato · quantità ultima fattura".
- NUOVO `tests/test_prezzi_da_fatture.py` (5 test puri): match esatto,
  non-comprati senza prezzo, dizionario vuoto, anti-regressione del bug
  storico sottostringa (vassoio→Tè), match fuzzy con accenti.

**CORREZIONE ONESTA sul processo di verifica**: i run pytest "verdi"
dichiarati nei merge precedenti di oggi guardavano l'exit code di
`tail` (pipe), non di pytest. La suite completa in questo sandbox ha
SEMPRE ~319 test di integrazione falliti perché richiedono il backend
live (limite ambientale noto, non regressione). D'ora in poi: eseguire
SOLO i test puri per file espliciti e controllare l'exit code di
pytest. Test puri attuali: 32/32 verdi.

## Match per CODICE ARTICOLO + guida aggiornata (03/07/2026, seguito)
RICHIESTA Enzo: "gli articoli dei cataloghi sono uguali a quelli che
arrivano in fattura: copia i codici articolo dai cataloghi ai prodotti
così è più facile agganciare il prodotto alla fattura e far comparire
il prezzo" + aggiornare la guida in-app nello stile "spiegazione
semplice per ogni bottone" (gli è piaciuta la spiegazione discorsiva
del meccanismo prezzi).

**Match per codice articolo (deterministico)**:
- `xml_helpers.py::parse_fattura_xml` ora estrae `CodiceArticolo/
  CodiceValore` da ogni DettaglioLinee → salvato in `prodotti[].
  codice_articolo` di ogni fattura nuova (il modello è List[dict],
  nessuna migrazione).
- `utils.py::prezzi_fatture_per_fornitore` indicizza le righe ANCHE per
  codice (chiavi namespace `codart::<codice normalizzato>`, escluse
  dall'indice fuzzy); `_norm_codice_articolo` toglie zeri iniziali
  ("0862"=="862") e scarta codici <2 caratteri.
- `applica_prezzo_da_fatture`: ordine match ora 1) codice articolo
  (catalogo.codice_articolo/codice vs fattura), 2) nome esatto,
  3) fuzzy. Il codice vince anche se la descrizione in fattura è
  abbreviata/diversa dal catalogo.
- NUOVO `POST /fatture/backfill-codici-articolo` (stesso pattern di
  /backfill-iva): rilegge gli xml_raw archiviati ed estrae i codici
  sulle righe delle fatture GIÀ importate — da lanciare UNA VOLTA sul
  live dopo il deploy, poi i nuovi import li salvano da soli.
- Test: 9 nel file test_prezzi_da_fatture.py (aggiunti: match per
  codice con nome diverso, zeri iniziali, chiavi codart:: fuori dal
  fuzzy, parser XML con CodiceArticolo su XML sintetico). 36/36 puri.

**Guida in-app (`ManualeView.jsx`)**: nuove sezioni nello stile
richiesto ("cosa fa quel bottone"): Cataloghi fornitori (prezzo verde =
già comprato, stella vs carrello, importa da PDF), Colazione (stagione
automatica, più usati, preferiti), Farcitura cornetti (quantità
parziale, divisione gusti, FIFO); sezione Ordini aggiornata (carrello
unico). NOTA: Enzo vuole questo stile per OGNI azione dell'app — le
sezioni esistenti restano più sintetiche, il restyle completo è lavoro
per la skill guida-operativa (PDF) in una sessione dedicata.

DOPO IL DEPLOY (checklist live):
1. `POST /fatture/backfill-codici-articolo` (una tantum, con token).
2. Nei tab Il Pasticcere/Tre Marie/Bindi premere "Importa dal catalogo
   PDF" per popolare i cataloghi.
3. Verificare che un prodotto già in fattura mostri prezzo verde +
   "✓ già comprato".

## Scheda fornitore arricchita + pannello "Qualità dati per le ricette" (03/07/2026)
RICHIESTA Enzo: "arricchisci la scheda anagrafica fornitori... più
informazioni ho, maggiore è la qualità delle informazioni che posso
estrarre per le mie ricette".

**Campi nuovi in `fornitori_anagrafica`** (tutti opzionali, editabili
dalla scheda fornitore, stesso PUT esistente): `pec`, `sito_web` (utile
per recuperare le schede tecniche prodotti), `referente` (agente),
`telefono_fisso`, `giorni_consegna`, `ordine_minimo`,
`condizioni_pagamento`, `certificazioni` (BIO/IGP/...). Il bottone ora
si chiama "Salva scheda fornitore".

**NUOVO pannello "🍰 Qualità dati per le ricette"** nella scheda
fornitore — `GET /fornitori/{nome}/qualita-ricette` (stesso match
nome-esatto+P.IVA dell'anagrafica). Misura la catena che rende
utilizzabili i prodotti del fornitore nelle ricette:
prodotti comprati → con codice articolo → collegati al dizionario
ingredienti (nome_normalizzato/aliases) → con nome canonico → usati in
ricette (via `ingredienti_dettaglio[].prodotto_dizionario_id`).
Mostra: 5 contatori, chips delle ricette coinvolte (fino a 30), elenco
"⚠ Da sistemare" con i prodotti non collegati o senza canonico (fino a
25 + conteggio residuo) — è la lista di lavoro CONCRETA per alzare la
qualità di food cost/allergeni/FIFO.
Build backend+frontend verificate. Endpoint da collaudare live (nessun
DB da qui); i numeri dipendono dalla pulizia del dizionario (code note:
~113 voci senza canonico, vedi "Code di lavoro note").
## Audit completo (skill audit-codice) — collection, codice morto, PIN, design, README (03/07/2026)
RICHIESTA Enzo: (1) magazzino_bar_prodotti vs magazzino_bar_movimenti
sono duplicazioni? (2) analisi generale: duplicati, codice morto,
endpoint superati, coerenza design, persistenza PIN 2h, README.

**VERDETTO COLLECTION BAR: NON sono duplicati.**
`magazzino_bar_prodotti` = giacenza corrente (una riga per prodotto,
stock). `magazzino_bar_movimenti` = registro storico carico/scarico
(chi/cosa/quando), scritto SOLO da applica_movimento_stock, letto da
/magazzino-bar/movimenti* e da magazzino_unificato /movimenti che
alimenta la pagina "Controllo prelievi". Eliminarne una romperebbe
giacenze o tracciabilità prelievi. TENUTE ENTRAMBE.
(`magazzino_movimenti_fornitori` = dominio diverso: prelievi dal
magazzino generale, stessa pagina Controllo prelievi.)

**PIN 2 ORE: VERIFICATO FUNZIONANTE** (revisione riga per riga):
gate `lotti_gate_until` in localStorage, LoginGate controlla solo al
mount + su evento lotti-auth-changed (mai su cambio pagina/hashchange);
scenari verificati OK: navigazione multi-pagina, chiudi/riapri scheda
entro 2h, admin→dashboard→admin. Token backend TTL 12h + refresh orario
(> del gate: nessuno slogout anticipato, salvo override env
AUTH_TOKEN_TTL_H su Render — da controllare nel pannello). Rimosso il
residuo morto `lotti_gate_ok` (letto ma mai più scritto).

**CODICE MORTO RIMOSSO** (ogni voce verificata con grep su frontend,
scheduler, pipeline, memory prima del taglio):
- `routers/analisi_ordini.py` INTERO (3 endpoint mai chiamati da nulla).
- utils.py: blocco legacy del prototipo iniziale (GET /allergeni, POST
  /rileva-allergeni, /scadenze-ingredienti, /calcola-scadenza,
  /importa-dati con path hardcoded /app, /esporta-ricette/json+csv,
  /importa-ricette). Le FUNZIONI _calcola_scadenza/_rileva_allergeni
  restano (usate da gelati.py/lotti.py/food_cost).
- unita_misura.py ridotto da 803 a 68 righe: restano solo
  normalizza_unita_display (unica importata da fornitori/magazzino);
  vía 6 endpoint mai chiamati + dizionario conversioni/uova usato solo
  da quegli endpoint. Router deregistrato da server.py.
- scheduler.py: alias deprecato GET /status (resta /stato).
- ricette.py: GET /ricette-libro e /ricette-libro/{id} + script
  scripts/import_ricette_libro.py (sistema isolato mai collegato a UI;
  la collection ricette_libro nel DB resta, innocua, eliminabile a mano).
- frontend: theme.js (mai importato — vecchio tema scuro navy/slate),
  blocco CSS .dashboard-dark (157 righe, classe mai usata, conteneva i
  soli cyan/navy veri del repo), tablet/ModalAcquaviva.jsx (orfano).

**DESIGN**: unica violazione fredda attiva era accent-blue-600
(checkbox FornitoriList) → salvia. Le costanti chiamate "NAVY" in 5
file hanno già VALORE salvia scuro #3f5a4e (solo nome stantio, colori
ok). CSS vars :root coerenti salvia. Tabella Listino senza overflow-x
→ corretta. `.g-page` applicato globalmente: centratura ok ovunque.

**README riscritto**: via palette viola #5D29C7 e dominio Render come
principale; ora salvia, www.ceraldiapp.it, elenco moduli reale,
struttura repo, verifiche pre-commit.

**VIVI (non toccati, con motivo)**: endpoint backfill/una-tantum citati
in STATO.md (strumenti manuali curl), /pipeline/* e /digest/* (trigger
manuali; il lavoro vero parte da fatture.py/scheduler), POST /auth/login
PIN (ingresso curl documentato in CLAUDE.md; il frontend usa
/auth/google), magazzino_bar_seed.py (modulo dati, non router),
ordini_app.py (/giacenze usato). `materie_prime` collection
semi-legacy: le liste leggono già da lotti_fornitori, restano i CRUD
puntuali — unificazione possibile ma rinviata (richiede migrazione).

Rimosse ~1.100 righe. Build backend+frontend verificate, 36/36 test
puri verdi, import-check ok.

## Unificazione materie_prime → lotti_fornitori (03/07/2026)
RICHIESTA Enzo: "unifica materie_prime su lotti_fornitori con la
migrazione" (seguito dell'audit: collection semi-legacy).

STATO DI PARTENZA (verificato): il frontend usava SOLO
GET /materie-prime/da-fatture, che legge già da lotti_fornitori.
La collection materie_prime era toccata solo da: CRUD manuali mai
chiamati dal frontend (POST /, PUT /{id}/allergeni,
POST /auto-rileva-allergeni, DELETE /{id}, GET /, GET /storico) e da
UNA lettura in lotti_produzione.py (arricchimento ingredienti alla
registrazione lotto).

FATTO:
- `lotti_produzione.py`: l'arricchimento ingredienti ora legge da
  lotti_fornitori (prodotto_nome, con filtro solo_magazzino e fornitori
  esclusi), prendendo il lotto più RECENTE per data fattura; il
  dettaglio ricostruisce lo stesso formato informativo di prima
  (nome + allergeni + fornitore + n° fattura + data). Corretti di
  passaggio: regex NON escapata su input utente (trappola nota) e
  find_one senza sort (prendeva un doc qualsiasi).
- `materie_prime.py`: rimossi i 6 endpoint morti e i modelli
  MateriaPrima/MateriaPrimaCreate. Restano: /da-fatture (pagina Materie
  Prime), /rebuild-lotti-fornitori e /normalizza-unita (manutenzione
  manuale) e il NUOVO `POST /materie-prime/migra-in-lotti-fornitori`
  (una tantum, idempotente: copia i doc storici mappando
  materia_prima→prodotto_nome, azienda→fornitore,
  numero_fattura→fattura_ref, allergeni→allergeni_testo, flag
  migrato_da_materie_prime; salta i già presenti per chiave
  fattura+prodotto+fornitore; con ?elimina_dopo=true svuota la vecchia
  collection).
- `utils.py` /pulizia-dati-spazzatura: ora pulisce lotti+lotti_fornitori
  e usa \btest\b a parola intera — la vecchia regex "test" avrebbe
  cancellato prodotti VERI tipo "TESTA di vitello" (bug latente
  corretto prima che diventasse pericoloso sui dati reali).
- `diagnostic._COLLEZIONI_PROTETTE`: materie_prime resta in lista
  protetta finché la migrazione live non è eseguita.

DOPO IL DEPLOY (da fare sul live, in quest'ordine):
1. `POST /api/materie-prime/migra-in-lotti-fornitori` (senza flag) e
   controllare i numeri (migrati / gia_presenti);
2. verificare la pagina Materie Prime e una registrazione lotto di
   produzione (gli ingredienti devono mostrare fornitore+fattura);
3. solo dopo la verifica: rilanciare con `?elimina_dopo=true`.
Zero riferimenti residui a db.materie_prime fuori dall'endpoint di
migrazione. Build+import-check ok, 36/36 test puri verdi.

## Sezione Ordini: carrello unificato DAVVERO, cervello festività, giacenza/soglia da card, alert dati (03/07/2026)
RICHIESTA Enzo: analisi critica sezione ordini (cataloghi raggiungibili?
3 click? giacenze/soglia dalle card?), alert nuovi prodotti senza
dati, corrispettivi collegati agli ordini, logica festività "da vero
magazziniere", giorni di chiusura fornitore.

**BUG CRITICO TROVATO E CORRETTO — carrello fantasma**: i cataloghi
fornitori (CatalogoFornitoreView/CatalogoGenericoView) scrivono il
carrello in localStorage `ordini_smart_carrello`, ma il consumatore
originale (ordini-app.html) era stato demolito il 13/06 e NESSUNA
pagina leggeva più quella chiave: "+ Aggiungi all'ordine" dai cataloghi
finiva nel nulla. Ora OrdiniView fa il merge del carrello cataloghi nel
proprio (id prefissati `cat_`, listener su ordini_smart_cart_update/
storage), lo svuota alla creazione bozze e sincronizza le rimozioni.
Aggiunto anche link "Sfoglia i cataloghi fornitori →" nel tab Catalogo
di Ordini (prima i cataloghi non erano raggiungibili da lì).

**Festività nel riordino automatico** (`esegui_riordino_automatico`):
se nei prossimi 6 giorni cade una festività nazionale o il suo ponte
(fonte unica: corrispettivi.festivita_anno — nazionali + San Gennaro +
Pasqua/Pasquetta col computo di Gauss, GIÀ esistente), le quantità
proposte vengono RADDOPPIATE e la nota di riga spiega perché; la
risposta include festivita_considerata. Le festività NON vanno
raccolte a mano: il calendario è già nel codice, per tutti gli anni.

**Corrispettivi visibili negli Ordini**: il tab Riordini ora mostra il
banner "consigli del magazziniere": festività imminenti (GET
/corrispettivi/festivita-imminenti) + coerenza incassi↔spesa ordini
(GET /corrispettivi/correlazione-ordini con incidenza %). Endpoint GIÀ
esistenti ma visibili solo nella pagina Corrispettivi — ora sono dove
si decide l'ordine.

**Giacenza+soglia dalle card**: nuovo componente EditGiacenzaSoglia
("✎ correggi giacenza / soglia") sulla card del catalogo Ordini E nel
tab Giacenze: rettifica stock (POST /magazzino-bar/prodotti/{id}/
rettifica) e soglia (PATCH .../soglia). FIX backend: SogliaUpdate.
quantita_riordino ora Optional=None — prima un PATCH con la sola
soglia AZZERAVA la quantità di riordino esistente (bug latente).

**Alert supervisore "dati da completare"** (check_dati_da_completare):
DATI1 prodotti bar movimentati senza soglia minima (il riordino
automatico non li vede) → route ordini; DATI2 prodotti in vendita
attivi senza prezzo → route prodotti; DATI3 fornitori attivi senza
sito web in scheda → route fornitori. Tutti con items[] navigabili
(pattern alert esistente). I nuovi prodotti bar da fattura ora salvano
created_at.

**Scheda fornitore**: nuovo campo `giorni_chiusura` (testo, es.
"domenica, 10-20 agosto") accanto a giorni_consegna — informativo per
anticipare/raddoppiare gli ordini; il parsing automatico del testo
libero è volutamente NON fatto (fragile), la logica quantità usa il
calendario festività nazionale.

DA COLLAUDARE LIVE: giro completo catalogo→carrello→bozza→invio;
banner festività (visibile nei 12 giorni prima di una festa);
raddoppio quantità nel riordino automatico a ridosso di festività.

---

## 04/07/2026 — Riordino da consumi reali, pagina Collaudi, bonifica alert

Branch `claude/repo-review-completion-40cdmd` → main. Richiesta Enzo:
"fai il prossimo cantiere (proposta basata sui consumi reali), una
pagina con tutti i test da fare (non in chat), e sistema la scheda
alert: incoerenze, alert che ricompaiono anche dopo che li sistemo
(es. ricette senza allergeni — l'automatismo deve farlo il sistema),
e quando clicco un alert deve scomparire".

**Motore consumi reali nel riordino automatico**
(`ordini_fornitori.esegui_riordino_automatico`): nuova funzione pura
`proposta_da_consumo(consumo_medio, stock, giorni_copertura)` —
fabbisogno = consumo medio giornaliero × GIORNI_COPERTURA (7gg) meno
lo stock attuale. Il consumo medio viene da `_consumi_medi_bar()`:
somma degli scarichi (magazzino_bar_movimenti, tipo=scarico) degli
ultimi 28 giorni (GIORNI_STORICO_CONSUMI) diviso 28, per prodotto.
Doppio trigger: un prodotto entra in proposta se sotto soglia OPPURE
se lo stock non copre 7 giorni di consumo reale. Quantità proposta =
max(quantità da soglia, quantità da consumo), poi passa dal raddoppio
festività già esistente. La nota di riga dice "consumo reale X/giorno
(copertura 7gg)" così si capisce PERCHÉ il sistema propone quella
quantità. Test puri: `backend/tests/test_riordino_consumi.py`
(6 test, tutti verdi).

**Pagina "Collaudi da fare"** (menu Altro, admin): da oggi i test
manuali post-modifica NON si dettano più in chat — si registrano in
`db.collaudi` via `POST /api/collaudi` (routers/collaudi.py) e Enzo
li esegue/spunta dalla pagina (CollaudiView.jsx): ✓ Funziona,
✗ Non funziona (= bug da segnalare), Rimetti tra i da fare, elimina.
Seed una tantum con i 9 collaudi pendenti accumulati finora (carrello
unico, import PDF, prezzo verde, riordino consumi+festività,
giacenza/soglia da card, alert, migrazione materie prime, farcitura,
scheda fornitore). **CONVENZIONE NUOVA: ogni sessione di sviluppo
registra i propri collaudi con POST /api/collaudi (titolo, gruppo,
passi[]), non li scrive in chat.**

**Fix alert allergeni che ricompariva sempre** (la causa vera):
`auto_rileva_allergeni_tutte` e il salvataggio manuale
(aggiorna-allergeni-ricetta, food_cost.py) NON settavano mai
`allergeni_verificato`, che è il flag controllato dall'alert A1 →
l'alert restava identico anche dopo aver sistemato le ricette. Ora
entrambi i percorsi lo settano. In più il supervisore
(check_allergeni) lancia da solo l'autorilevamento (max 1 volta/ora)
PRIMA di contare: l'alert resta solo per le ricette senza ingredienti
(dove l'automatismo non può dedurre nulla) e il testo lo spiega.

**Alert cliccabili per silenziarli**: ✕ su ogni alert del pannello
Supervisore → `POST /api/supervisor/alerts/{id}/silenzia?contatore=N`
(upsert su db.supervisor_alerts_silenziati, per-giorno). L'alert
sparisce per OGGI ma riappare se il contatore cambia (il problema è
peggiorato/diverso) o domani se ancora presente — non è un "ignora
per sempre".

Verifiche: compileall + import-check ok, pytest sui file puri
30 passed (exit code di pytest controllato, non del tail), frontend
build ok (main.b05784e8.js). Collaudi live: registrati nella pagina
Collaudi, non qui.

---

## 04/07/2026 — Bonifica alert (tranche 2): doppioni, lotti "eterni", alert aggregati

Seconda passata sulla scheda alert (richiesta Enzo: "molte incoerenze,
alert che nonostante li sistemo compaiono sempre"). Trovate e corrette
QUESTE cause, verificate nel codice reale:

**Lotti "eterni" negli alert — la causa vera**: i lotti hanno DUE campi
storici per "non è più in giro": `stato` (stringa "smaltito"/"esaurito")
e i flag booleani `esaurito`/`consumato`. L'archiviazione automatica
(POST /lotti/archivia-scaduti) setta SOLO il flag booleano, ma l'alert
"lotti scaduti da smaltire" filtrava SOLO sulla stringa → un lotto
archiviato restava nell'alert per sempre. Fix doppio: (1) nuovo filtro
unico FILTRO_LOTTO_APERTO (esclude stringa E booleani) applicato a
TUTTI i punti che leggono i lotti: alert scaduti, alert in scadenza,
cruscotto, /lotti-in-scadenza, anomalie temperatura, task dipendenti,
giacenze produzione; (2) alla scrittura i due campi ora vanno insieme
(smaltisci setta anche esaurito=True, archivia setta anche
stato="esaurito").

**Doppione eliminato**: "lotti in scadenza entro 2 giorni" (A3b) e
"lotti in scadenza entro 48h" (scadenza_48h, modulo ePackPro) erano lo
STESSO controllo duplicato — comparivano entrambi. Tenuto A3b, ora con
l'elenco toccabile dei lotti (prodotto · numero · scadenza).

**Alert aggregati (basta sfilze)**: "Non acquisti X da N giorni"
generava UN alert PER PRODOTTO (poteva riempire il pannello); ora è UN
alert "N prodotti che non compri da troppo tempo" con elenco ordinato
dal più fermo. Stessa cosa per le qualifiche fornitori
(QUALIFICHE_SCADUTE / QUALIFICHE_IN_SCADENZA con elenco, prima un
alert per fornitore).

**A4 "prodotti senza prezzo" sensato**: segnalava anche i prodotti MAI
comprati, che per la regola "prezzi SOLO da fatture" non possono avere
prezzo → alert eterno insanabile. Ora conta solo i prodotti COMPRATI
(conteggio_acquisti>0) senza prezzo (vera anomalia), con elenco, e
porta al Comparatore (prima portava a Ricette e apriva una scheda a
caso).

**Task dipendenti "Usa prima"**: il confronto data_scadenza <= fra 2
giorni era fatto come STRINGHE su formati misti (dd/mm/yyyy vs ISO) —
le date italiane matchavano quasi sempre → task spuri. Ora parsing con
parse_data_flessibile e confronto tra date vere.

**Seed collaudi incrementale**: il seed della pagina Collaudi inseriva
solo a registro vuoto; ora è incrementale con registro
collaudi_seed_applicati (per titolo): le sessioni di sviluppo possono
aggiungere collaudi nel codice quando il live non è raggiungibile
dalla sandbox, senza resuscitare quelli fatti/eliminati da Enzo.
Aggiunto il collaudo di questa tranche.

Verifiche: pyflakes pulito sui file toccati (restano solo warning
cosmetici pre-esistenti), compileall + import-check ok, 30 test puri
passati. Nessuna modifica frontend in questa tranche.

---

## 04/07/2026 — Analisi debito tecnico + bonifica sezioni 1-2-3

Richiesta Enzo: analisi dell'intero progetto (debito tecnico,
duplicazioni, leggibilità) e poi correzione a partire dai bug veri.
Analisi fatta con 3 revisori paralleli (router backend, frontend,
duplicazioni trasversali) + verifica manuale dei finding critici.
Numeri: 81 router / 630 endpoint / ~49k righe backend; 15 parser di
date, 11 normalizzatori nomi, 4 mappe allergeni, 3 ledger giacenze,
~35 endpoint senza chiamanti. Il rapporto completo è nella chat della
sessione; il PIANO di rifattorizzazione strutturale è in preparazione
(plan mode) e NON è ancora applicato.

**SEZIONE 1 — Bug veri corretti:**
- MAPPA_ALLERGENI doppia e divergente in food_cost.py (righe 1630 vs
  1882, es. avena/farro/kamut solo in una): UNIFICATA a livello modulo
  con l'UNIONE delle due (più due correzioni di dominio: "coda
  d'aragosta" è il dolce → Glutine non Crostacei; vongola → Molluschi
  non Pesce). −328 righe. Restano altre 2 mappe (utils, fatture) da
  consolidare nel refactor.
- Motore prezzi (utils.prezzi_fatture_per_fornitore): il "prezzo più
  recente" era scelto confrontando le date COME STRINGHE in formato
  misto ("30/06/2026" > "05/07/2026") → ora confronto su date vere
  via parse_data_flessibile.
- pipeline.step_prezzi_dizionario e materie_prime (filtro N mesi):
  $gte stringa ISO su data_fattura in formato italiano → filtro su
  date vere in Python.
- 3 crash frontend: BackofficeView toast.success su toast locale
  (bottone "Applica soglie" moriva in silenzio), ModalRegistraLotto
  idx mai definito (schermo bianco allo step BOM), CatalogoFornitore
  variabile fonte inesistente (crash sulla stella preferiti).

**SEZIONE 2 — Confronti date format-safe (stessa famiglia di bug):**
- manuale_haccp "ultime 20 consegne": filtro E ordinamento su stringhe
  miste → date vere.
- haccp_manuale_auto: interrogava anomalie.data ma il campo si chiama
  data_segnalazione → le "anomalie recenti" del manuale erano SEMPRE
  vuote; anche l'ordinamento fatture era rotto. Corretti entrambi.
- scheduler (job aggiorna-riferimenti-fattura nei lotti): interrogava
  fatture.data (campo inesistente → non trovava mai nulla) e avrebbe
  fatto KeyError su fattura_nuova['data'] se avesse trovato qualcosa.
  Riscritto su data_fattura con date vere.
- Verificati e lasciati com'erano i campi sempre-ISO (movimenti bar,
  registri giornalieri, created_at, ultima_fornitura).

**SEZIONE 3 — Performance quick-win:**
- Scheda fornitore (get_anagrafica_fornitore): la proiezione includeva
  xml_raw INTERO (centinaia di KB a fattura × 2000) usato solo per un
  booleano has_xml → seconda query leggera solo id.
- GET /fatture (lista): caricava TUTTE le fatture intere (righe + XML)
  → aggregate con $project e num_prodotti/has_xml calcolati in Mongo;
  ImportaFattureView aggiornata (retro-compatibile).
- /ingredienti/smart-search (autocomplete TabIngredienti): scaricava
  3000 fatture con tutte le righe A OGNI BATTITURA → cache in-process
  120s delle righe appiattite (ultimi 6 mesi, esclusi già filtrati).
- /ingredienti/cerca: fino a 100 find_one su nome_mapping per
  battitura → una sola query $in.
- /food-cost/suggerisci-ingredienti: client Anthropic SINCRONO dentro
  endpoint async (bloccava l'event loop per tutta l'app durante le
  chiamate AI) → asyncio.to_thread.

Verifiche: pyflakes pulito sui file toccati (solo warning
pre-esistenti), compileall + import-check ok, 30 test puri passati
(incluso test_prezzi_da_fatture sul motore prezzi modificato),
frontend build ok (main.8f7956f2.js). Collaudo "Bonifica bug" aggiunto
al seed della pagina Collaudi.

---

## 04/07/2026 — Audit critico, piano rifattorizzazione MIRATO approvato, Tranche 0

Enzo ha chiesto un audit critico della sessione: ne sono emerse 4 decisioni
(sue, via domande esplicite) + correzioni al mio stesso operato:

**DECISIONI ENZO (04/07/2026):**
1. Alert CRITICI non silenziabili (la ✕ resta solo sui non critici).
2. Allergeni auto-rilevati = "da confermare" finché non li salva un umano.
3. Refactoring MIRATO (non il programma completo): sicurezza endpoint,
   servizi condivisi (date/nomi/allergeni), date ISO con backup, ledger
   giacenze unico, carrello unico frontend, palette VenditaBanco.
   RIMANDATO: motore prezzi unico, import fatture a batch, FIFO batch,
   spacchettamento monoliti, split componenti React.
4. PRIMA i collaudi arretrati (11 in pagina Collaudi), POI i cantieri.
Piano completo approvato in plan mode (file di piano della sessione);
prerequisiti: P1 collaudi, P2 conferma backup Atlas, P3 perimetro
Gestionale Cloud sulle collection condivise.

**CORREZIONE AL RAPPORTO AUDIT**: l'affermazione "backfill POST senza
autenticazione" era SBAGLIATA — auth_dependency è agganciata a tutto
l'api_router e OGNI scrittura esige token (tranne whitelist tablet,
auth.py:131). Il buco vero è più piccolo: il token di un DIPENDENTE
può chiamare endpoint admin (il ruolo nel token non viene controllato
lato server, solo lato UI). Da chiudere in Tranche 1 con require_admin.

**TRANCHE 0 (fatta):**
- Alert critici: filtro silenziati in esegui_tutti_i_controlli ignora
  il silenziamento per priorita=critica (enforcement server); endpoint
  silenzia → 403 se priorita=critica; SupervisoreBadge mostra "!" al
  posto della ✕ sui critici.
- Allergeni: nuovo flag ricette.allergeni_da_confermare — True quando
  compilati dall'automatismo (auto-rileva-tutte, create/update ricetta
  con soli auto, backfill), False quando salvati a mano dal tab
  allergeni (aggiorna-allergeni-ricetta). Nuovo alert A1b (bassa,
  silenziabile) con elenco ricette → tab allergeni. Backfill idempotente
  POST /food-cost/backfill-allergeni-da-confermare (solo amministratore,
  controllo ruolo dal token): le verificate pre-04/07 tornano tutte
  "da confermare" UNA volta.
- Collaudo "Alert critici bloccati + allergeni da confermare" nel seed.

Verifiche: pyflakes ok (warning pre-esistenti), compile+import ok,
30 test puri passati, frontend build ok (main.aa77fa52.js).

---

## 04/07/2026 — Card stato sync Drive in Importa Fatture

Enzo ha messo la credenziale Google su Render e ha chiesto di controllare
lo stato del sync: dalla sandbox il backend live NON è raggiungibile
(proxy 403 anche su /api/health — limite ambiente), e soprattutto NON
esisteva NESSUNA superficie in-app per vedere lo stato (l'endpoint
GET /drive-fatture/stato era solo-API). Aggiunta SyncDriveCard in
ImportaFattureView: pallino verde/ocra (credenziale vista o no, con
istruzioni Render nel secondo caso), metodo, file registrati/in errore,
ultimo giro, ultimi errori, bottone "Sincronizza ora"
(POST /drive-fatture/sync?limit=50, toast con processati/già noti) che
al termine ricarica l'elenco fatture. Chiavi verificate sul codice del
backend (esiti: trovati/gia_importati/nuovi/processati; ultimi_errori =
oggetti {file, errore}).

Decisione architetturale confermata (domanda Enzo su GestionaleCloud):
NON si elimina l'import di Lotti e NON si fa il ponte via DB invoices→
fatture (già provato e rimosso: invoices non ha xml_raw, file sul
filesystem dell'altra app). Punto di scambio = cartella Drive condivisa,
job già esistente. P3 del piano CHIUSO: collection separate tra le due
app. Restano P1 (collaudi) e P2 (conferma backup Atlas).

---

## 04/07/2026 — Confronto leggibile + alert prezzi aggregato (screenshot Enzo)

Da due screenshot di Enzo (06:52):
1. **Comparatore (Ordini → Confronto)**: i nomi prodotto erano troncati
   e illeggibili sul telefono ("Pista…", "Stru…", "5 forni…") — ora il
   nome va su 2 righe (line-clamp-2 + break-words) e il sottotitolo
   fornitori non tronca più; tooltip sul badge −N% (= risparmio tra
   fornitore più caro e più economico, non un calo prezzi).
2. **Variazioni prezzo nel Supervisore**: erano una sfilza di alert
   singoli criptici ("Aqv Sofia 82G: prezzo diminuito del −78.2%") che
   RICOMPARIVANO sempre: la ✕ silenziava per oggi ma NESSUN percorso
   marcava mai letto=True su db.alert_prezzi. Ora: UN alert aggregato
   PREZZI_INGREDIENTI con elenco → Comparatore, descrizione onesta
   (cali −70/−99% ≈ stessa merce letta con confezione/peso diversi tra
   fatture, non sconti), e la ✕ su QUESTO alert fa update_many
   letto=True → tornano solo variazioni nuove.
   NOTA per il refactor: i cali assurdi (−97/−99% su Sale/Pistacchio nel
   comparatore) confermano la doppia pipeline prezzo/kg con regole
   divergenti (tranche "motore prezzi unico", RIMANDATA da Enzo) — la
   radice non è ancora corretta, per ora è spiegata.
3. Pallino ocra sync Drive: credenziale non ancora vista dal backend —
   checklist data a Enzo (servizio giusto lotti-backend, nome esatto
   variabile, attendere Deploy live).
Collaudo breve aggiunto al seed. Build+test verdi (main.c760779b.js).

---

## 04/07/2026 — Controllo Dati: deep-link veri sui campioni + Collaudi in Home

Da screenshot Enzo ("tutta la sezione controllo non funziona: ovunque
clicco si apre la pagina generica"): i campioni delle card di Controllo
Dati erano DIV statici, l'unico bottone era "Apri area" (pagina
generica). Ora ogni campione è un bottone che apre LA COSA segnalata:
- righe fattura senza link / fatture con fornitore debole → la FATTURA
  nel visualizzatore (window.open withToken /fatture/{id}/visualizza);
  il backend ora proietta anche l'id fattura nei campioni;
- ingredienti ricetta non collegati → la SCHEDA della ricetta
  (sessionStorage apri_ricetta_id, stesso meccanismo del Supervisore);
  proiettato l'id ricetta nei campioni;
- lotti senza tracciabilità → pagina Lotti con la RICERCA precompilata
  (nuova chiave sessionStorage lotti_search letta da App.js);
- gli altri controlli (prodotti master, movimenti, scheduler) restano
  su "Apri area" — non esiste una scheda singola da aprire.
RUMORE TOLTO: "righe fattura senza link" non conta più i fornitori
ESCLUSI (le vernici di Napolitano Group gonfiavano il numero: 515).

"Non vedo la card Altro" (Enzo): il menu Altro sta nella navbar con
overflow orizzontale e sul telefono finisce fuori schermo → aggiunto
QuickLink "Collaudi da fare" (admin) nella Home, accanto a Controllo
Dati. Collaudo dedicato nel seed.

---

## 04/07/2026 — Guida completa discorsiva (in-app + PDF) — skill guida-operativa

Richiesta Enzo recuperata ("hai cancellato quello che ti ho chiesto"):
la guida completa nel suo stile ("cosa fa quel bottone"), rimandata in
un turno precedente. Eseguita con la skill guida-operativa:

1. TRE inventari paralleli SOLA LETTURA sul JSX reale (operative /
   HACCP / tablet+admin): ogni pagina con tabella Elemento → Cosa fa →
   API esatta, etichette copiate testualmente dal codice.
2. FONTE UNICA: frontend/src/data/guidaContenuti.json — 31 sezioni in
   6 gruppi (Per iniziare, Ufficio, Acquisti, Tablet di reparto,
   Registri HACCP, Amministrazione), 121 bottoni documentati con la
   chiamata al server (per segnalare i bug "chirurgicamente": bottone
   X della pagina Y).
3. ManualeView.jsx RISCRITTA: legge dal JSON, accordion raggruppato,
   testo discorsivo + passi + tabella bottoni per sezione; nota gotcha
   telefono (menu Altro fuori schermo → usare le card della Home).
4. PDF rigenerato dalla STESSA fonte (scratchpad: genera_html.py +
   genera_pdf.js con chromium locale /opt/pw-browsers): 17 pagine A4,
   copertina salvia, tabelle con header salvia, footer numerato.
   Pubblicato in frontend/public/guida/Guida_Operativa_Lotti.pdf
   (stesso path del vecchio: il link in-app non cambia).
   Verificato visivamente (render pymupdf).
CONVENZIONE: per aggiornare la guida si aggiorna guidaContenuti.json
(dal codice reale, mai inventare) e si rigenera il PDF con gli script
della skill. Collaudo dedicato aggiunto al seed.

## Tranche 0 — Fondamenta dati per le 7 macro-funzionalità HACCP (04/07/2026)
RICHIESTA Enzo: 7 macro-funzionalità di tracciabilità (Scadenza intelligente,
Produzione consigliata, Intelligenza operativa frigoriferi, Dashboard
economica, Cronologia completa lotto, Miglioramenti UI, Gemello digitale del
lotto) — senza collegare lo scontrino di vendita (resta commercio al banco +
invenduto serale). Prima di scrivere codice: analisi strutturata di cosa
esiste già (agente Explore dedicato + verifica manuale su lotti.py,
lotti_produzione.py, attrezzature.py, vendita_banco.py, shelf_life.py,
anomalie.py, supervisor_operativo.py, corrispettivi.py + frontend), piano a
tranche proposto e approvato da Enzo con 4 decisioni (ordine 0→6 come
proposto; lotti storici senza timeline dettagliata, solo evento "creazione";
valore economico = costo di produzione, non prezzo vendita; posizione
obbligatoria con blocco morbido, non rigido).

**Scoperta chiave (già verificata dal team il 03/07/2026, qui confermata)**:
la "destinazione" frigo/abbattitore/banco era SOLO un concetto frontend
(`ModalRegistraLotto.jsx`), mai scritta su `db.lotti` in forma strutturata —
persisteva solo `frigo_numero` (stringa libera). Nessuno storico
spostamenti, nessun valore economico sul lotto, nessun semaforo scadenza a
più livelli (solo scaduto/non-scaduto lato frontend).

**Implementato in questa tranche (solo backend, nessuna nuova azione utente
ancora — quelle sono Tranche 1)**:
- Nuova collection **`movimenti_lotto`** (audit trail) + servizio unico
  `backend/servizi/movimenti_lotto_service.py`: `registra_movimento()` è
  l'UNICO punto di scrittura (stesso pattern di `crea_lotto`/FIFO fornitori),
  `costruisci_posizione()` costruisce l'oggetto posizione strutturato
  (tipo/numero/nome/reparto/operatore/quantità/data_ora), `cronologia_lotto()`
  legge lo storico in ordine cronologico.
- Nuovo campo **`posizione`** strutturato su `lotti`, costruito in
  `crea_lotto()` (`servizi/lotti_service.py`) a partire dal solo
  `frigo_numero` esistente — cercando in `attrezzature_config` se il nome
  corrisponde a un frigo o congelatore già censito (default onesto "frigo"
  se non trovato, perché prima frigo_numero copriva entrambi senza
  distinzione). `frigo_numero` resta scritto come prima: ZERO chiamanti
  esistenti modificati/rotti.
- Nuovo servizio `backend/servizi/lotto_arricchimento_service.py`:
  `calcola_stato_scadenza()` (semaforo **verde/giallo/arancione/rosso/grigio**
  con soglie allineate a `SOGLIA_SCADENZA_LOTTO_GG=2` di
  supervisor_operativo.py: rosso=scaduto, arancione=scade oggi/domani,
  giallo≤3gg, verde>3gg) e `calcola_valore_economico()` (costo_pezzo ×
  quantità residua, `None` onesto se il lotto non ha costo tracciato —
  niente valori inventati per lotti manuali/pesce pre-esistenti).
  Agganciato in `_normalizza_lotto()` e `get_lotto()` (`routers/lotti.py`):
  **ogni risposta di `GET /lotti` e `GET /lotti/{id}` ora include
  `stato_scadenza` e `valore_economico`**, additivo, nessun campo esistente
  toccato.
- I 3 endpoint di movimento lotto già esistenti (`PATCH /lotti/{id}/consuma`,
  `POST /lotti/{id}/manda-al-banco`, `PATCH /lotti/{id}/smalti`,
  `POST /lotti/smalti-batch`) ora registrano l'evento corrispondente nel
  nuovo registro movimenti (con `operatore_id`/`operatore_nome` opzionali,
  nuovi parametri Query non obbligatori → nessuna rottura per i chiamanti
  frontend esistenti, che semplicemente non li valorizzano ancora). La
  registrazione è sempre in try/except non bloccante: se fallisse, l'azione
  vera (consumo/banco/smaltimento) non viene mai impedita.
- Nuovo endpoint di sola lettura `GET /lotti/{id}/movimenti` (registro
  grezzo) — base per la cronologia completa (Tranche 3), esposto già ora per
  poter collaudare che gli eventi vengano davvero registrati.
- Nuovo evento bus `LOTTO_MOVIMENTO` (`eventi.py`), stesso pattern di
  `LOTTO_CREATO`: handler che logga su `log_eventi`.

**Verifica eseguita** (nessun accesso di rete al backend live da questo
ambiente): `python -m compileall` su routers/servizi/models/server.py/db.py
OK; import-check completo (stesso script della CI, tutti i router + `server`
si costruiscono) OK; test funzionale end-to-end con MongoDB in-memory
(`mongomock`/`mongomock-motor`, installati solo in locale per il test, NON
aggiunti a requirements.txt) che ricrea lo scenario reale: crea lotto con
`frigo_numero="Frigorifero N°1"` censito in `attrezzature_config` → `posizione.tipo`
inferito correttamente "frigo", evento "creazione" registrato; manda 3 pezzi
al banco → quantità residua 10→7, movimento "banco" con posizione_a banco;
smaltisce il residuo con nota → movimento "smaltimento" con
`azione_correttiva_haccp` valorizzata; `GET /lotti/{id}` su un lotto scaduto
2gg fa → `stato_scadenza.colore="rosso"` corretto; su un lotto costo_pezzo=1.2
qty=10 → `valore_economico=12.0` corretto. Verifica funzionale reale (con
collaudo su dati veri) rimandata al prossimo deploy, come da limite noto di
questo ambiente sandbox.

**PROSSIMO PASSO (Tranche 1, da confermare con Enzo prima di iniziare)**:
vista aggregata "Cosa usare oggi" (ordinata per urgenza/scadenza/valore) +
scheda "Gemello digitale del lotto", con le azioni nuove sposta-frigo,
congela, recupera-in-nuova-produzione, e collegamento reale
dell'operatore loggato ai 3 endpoint sopra (oggi il parametro esiste lato
backend ma il frontend non lo valorizza ancora).

## Tranche 1 (backend) — "Cosa usare oggi" + Gemello digitale del lotto (04/07/2026)
Seguito della Tranche 0 (fondamenta dati). Aggiunge le azioni operative
mancanti e i due endpoint aggregati richiesti dai punti 1 e 7, riusando
tutto quanto costruito nella Tranche 0 (posizione strutturata, registro
movimenti, semaforo scadenza, valore economico).

**Nuovi endpoint** (`backend/routers/lotti_produzione.py`):
- `POST /lotti/{id}/sposta-posizione` — sposta un lotto (frigo↔frigo,
  frigo↔congelatore, →banco, →magazzino), aggiorna `posizione` E
  `frigo_numero` (retrocompat) e registra il movimento "spostamento".
- `POST /lotti/{id}/congela` — sposta in congelatore e allunga la scadenza
  al valore da abbattitore negativo: usa `scadenza_abbattuto` già calcolata
  in produzione se presente, altrimenti la ricalcola dal motore
  `shelf_life.py` (mai una shelf-life inventata qui). Salva anche
  `data_scadenza_pre_congelamento` per non perdere il dato originale.
- `POST /lotti/{id}/recupera` — scala il lotto (tutto o in parte) con
  evento "recupero" distinto da "uso"/"consuma": l'operatore lo userà poi
  come componente di una nuova produzione tramite il meccanismo
  `lotti_componenti` già esistente (che collega i due lotti in
  tracciabilità/recall) — scelta deliberata di non forzare qui un
  collegamento rigido a un lotto di destinazione non ancora creato.

**Nuovi endpoint aggregati** (`backend/routers/lotti.py`):
- `GET /lotti/cosa-usare-oggi` — lotti attivi (quantità>0, non
  consumati/smaltiti) ordinati per semaforo scadenza (rosso→verde) e, a
  parità, per valore economico decrescente.
- `GET /lotti/{id}/scheda-completa` — gemello digitale: lotto arricchito +
  cronologia movimenti + ricetta collegata (lookup per nome prodotto, il
  lotto non salva ancora `ricetta_id`) + lotti fornitori scalati. I
  pulsanti azione (stampa/fattura/recall/registro HACCP) restano lato
  frontend sugli endpoint già esistenti.

**Verifica eseguita** (stesso metodo della Tranche 0, mongomock in locale,
non in requirements.txt): compileall + import-check CI-equivalenti OK;
scenario end-to-end — lotto scaduto (rosso) correttamente prima di un lotto
fresco (verde) in "cosa usare oggi"; spostamento aggiorna `frigo_numero`;
congelamento applica `scadenza_abbattuto` esistente; recupero parziale
scala correttamente la quantità residua; scheda completa trova la ricetta
collegata e la cronologia con tutti gli eventi.

**Frontend completato nella stessa PR #120** (non serviva una PR separata):
- Nuova vista `CosaUsareOggiView.jsx` (tab "Cosa usare oggi", raggiungibile
  dal dropdown "Altro" e da una nuova ActionCard nella Dashboard con badge
  urgenti): card per lotto con semaforo colore, quantità, posizione, valore
  economico; menu azioni (sposta/congela/manda al banco/recupera/smaltisci)
  e pulsante "Dettaglio" che apre il gemello digitale.
- Modale "Gemello digitale del lotto" (dentro lo stesso file): dati
  arricchiti, ricetta collegata, lotti fornitori scalati, cronologia
  movimenti con icona per tipo evento, pulsanti stampa etichetta + tutte le
  azioni.
- `ModalRegistraLotto.jsx`: blocco morbido "posizione obbligatoria" per
  frigo/abbattitore senza apparecchio indicato (stesso principio del blocco
  giacenza del 03/07/2026 — checkbox di conferma esplicita, mai un
  impedimento definitivo).
- Build frontend (`CI=false npm run build`) verificata: "Compiled
  successfully", nessun warning.

## Nota: verifica live non disponibile da questo ambiente (04/07/2026)
Tentata la verifica live delle Tranche 0+1 appena mergiate (health check
backend, hash bundle frontend): sia `curl` che `WebFetch` verso
`lotti-backend-2wwb.onrender.com` ricevono un rifiuto di rete (403 dal
gateway del sandbox, confermato via `$HTTPS_PROXY/__agentproxy/status` →
`recentRelayFailures: connect_rejected`), non un errore dell'app. Coerente
col limite già noto di questo ambiente (nessun accesso di rete in uscita
verso il backend/frontend live). Verifica reale rimandata a chi ha accesso
al browser/telefono (Enzo) o a una prossima sessione con rete disponibile.
Build/compileall/import-check locali e test funzionali end-to-end con
mongomock restano l'unica verifica possibile da qui, già eseguiti per
entrambe le tranche prima del merge.

**Stato attuale**: Tranche 0 (#119) e Tranche 1 (#120) mergiate su `main`,
branch locale riallineato. Prossimo passo possibile: Tranche 2
(Intelligenza operativa frigoriferi — posizioni tipizzate abbattitore/
banco/magazzino in attrezzature_config, vista frigo-in-anomalia con
spostamento massivo tracciato), da confermare con Enzo prima di iniziare.

## Tranche 2 — Intelligenza operativa frigoriferi (04/07/2026)
Seguito delle Tranche 0-1. Punto 3 delle 7 macro-funzionalità: spostamento
massivo tracciato quando un frigo/congelatore/abbattitore va in anomalia.

**Nuovi endpoint** (`backend/routers/anomalie.py`):
- `GET /anomalie/{id}/lotti-attuali` — ricalcola IN TEMPO REALE i lotti
  presenti nell'attrezzatura dell'anomalia (match esatto case-insensitive
  sul nome intero), diverso dallo snapshot `lotti_coinvolti` salvato alla
  segnalazione (che può essere superato se l'intervento avviene più tardi).
- `POST /anomalie/{id}/sposta-lotti-massivo` — sposta in blocco i lotti
  selezionati verso una nuova posizione, un lotto alla volta (ogni
  spostamento resta un evento indipendente in cronologia, non una riga
  aggregata), con `documento_collegato` verso l'anomalia e
  `azione_correttiva_haccp` salvata sia sul movimento sia in
  `anomalia.spostamenti_massivi[]`.

**Bug scoperto e corretto in questa tranche** (dal test end-to-end scritto
per il nuovo endpoint, non dal codice preesistente che non è stato
toccato): la query dello snapshot `lotti_coinvolti` in `registra_anomalia`
usa un regex sui primi 6 caratteri del nome attrezzatura
(`data.attrezzatura[:6]`) — "Frigorifero N°2" e "Frigorifero N°9"
condividono lo stesso prefisso "Frigor" e verrebbero confusi. Il nuovo
endpoint `lotti-attuali` usa invece un match ESATTO case-insensitive
sull'intero nome, corretto. La query preesistente in `registra_anomalia`
(riga ~221) NON è stata toccata in questa tranche (fuori scopo, tocca dati
storici) ma resta un bug noto da correggere in futuro se richiesto.

**Frontend** (`AnomalieView.jsx`): pulsante "Sposta tutti i lotti" nel
riquadro lotti coinvolti (solo per anomalie Aperta/In corso) → modale che
ricarica la lista live, permette di deselezionare singoli lotti, sceglie
tipo/apparecchio/reparto di destinazione, richiede un'azione correttiva
HACCP (obbligatoria) e un motivo (facoltativo).

**Verifica eseguita**: compileall + import-check CI-equivalenti OK; test
end-to-end con mongomock — anomalia su "Frigorifero N°2" con 2 lotti
presenti + 1 lotto in un altro frigo (non coinvolto); `lotti-attuali`
trova solo i 2 corretti; spostamento massivo aggiorna `frigo_numero`/
`posizione` di entrambi, registra il movimento con
`azione_correttiva_haccp` e `documento_collegato`, aggiorna
`anomalia.spostamenti_massivi`, lascia intatto il lotto nell'altro frigo.
Build frontend (`CI=false npm run build`): Compiled successfully.

**Prossimo passo possibile**: Tranche 3 (Cronologia completa del lotto —
in gran parte già automatica grazie al registro movimenti delle tranche
precedenti, serve principalmente un endpoint aggregatore più ricco e una
timeline UI dedicata oltre al mini-elenco già nel gemello digitale) o
Tranche 4 (Dashboard economica) — da confermare con Enzo.

## Tranche 3 — Cronologia completa del lotto (04/07/2026)
Seguito delle Tranche 0-2. Punto 5 delle 7 macro-funzionalità. La maggior
parte dei dati esisteva già (registro movimenti dalle tranche precedenti,
ricetta collegata e lotti fornitori scalati dalla scheda-completa di
Tranche 1) — mancavano 3 pezzi, ora aggiunti:

**Backend:**
- `vendita_banco.py::registra_invenduto` — se la vendita al banco era
  collegata a un `lotto_id`, ora registra un movimento "rientro_invenduto"
  (prima questo passaggio del ciclo di vita — produzione → banco →
  invenduto — non compariva mai nella cronologia del lotto, solo in
  `vendite_banco`).
- `GET /lotti/{id}/scheda-completa` arricchita: le anomalie collegate
  vengono derivate dai movimenti con `documento_collegato.tipo=="anomalia"`
  (nessuna nuova query separata, solo un lookup sugli id già presenti) e
  allegate a ciascun movimento come `anomalia_collegata` (attrezzatura,
  descrizione, stato); esposto anche il blocco `abbattimento` se il lotto
  lo ha attraversato (es. pesce).

**Limiti onesti documentati (non implementati, dati non esistenti
nell'app)**: le stampe etichetta non vengono loggate (ogni apertura della
finestra di stampa non è distinguibile da una stampa realmente eseguita);
i richiami (`/lotti/recall/*`) sono ricerche on-demand, non eventi
persistiti — non compaiono in cronologia finché non esisterà un registro
dei richiami eseguiti (funzionalità diversa, non richiesta esplicitamente
finora).

**Frontend**: il modale "Gemello digitale del lotto" (creato in Tranche 1
dentro `CosaUsareOggiView.jsx`) è stato estratto in
`components/haccp/shared/SchedaLottoModal.jsx` (con `AzioneModal`,
`SEMAFORO`, `euro`, `posizioneLabel`) così è riusabile da più pagine senza
duplicare codice. Ora mostra anche anomalie collegate e abbattimento.
Aggiunto un pulsante "Cronologia completa" (icona `History`) su ogni riga
di `LottiList.jsx` (pagina principale Lotti), che apre lo stesso modale —
prima la cronologia/gemello digitale era raggiungibile solo da "Cosa usare
oggi". Limite noto: le azioni (sposta/congela/banco/recupera/smalti)
lanciate da qui non ricaricano automaticamente la lista lotti sottostante
(nessuna callback di refresh esposta da `LottiList` ai suoi genitori) — i
dati si aggiornano al prossimo refresh naturale della pagina.

**Verifica eseguita**: compileall + import-check CI-equivalenti OK; test
end-to-end con mongomock — lotto con abbattimento pesce + anomalia con
spostamento massivo + vendita banco con invenduto: la scheda-completa
mostra correttamente tutti e 3 gli eventi (creazione, spostamento_massivo
_anomalia con anomalia_collegata popolata, rientro_invenduto) e il blocco
abbattimento. Build frontend (`CI=false npm run build`): Compiled
successfully.

## Tranche 4 — Dashboard economica (04/07/2026)
Seguito delle Tranche 0-3. Punto 4 delle 7 macro-funzionalità: valore
lotti attivi/in scadenza/smaltiti, costo spreco giornaliero/mensile,
margine per prodotto/reparto, prodotti più costosi/meno redditizi,
variazione prezzi materie prime, fornitori con maggiore incidenza —
aggregati in un'unica vista, riusando calcoli già esistenti invece di
duplicarli.

**Nuovo router** `backend/routers/dashboard_economica.py`
(`GET /dashboard-economica/riepilogo?mese=YYYY-MM`, default mese
corrente), registrato in `server.py`. Aggrega:
- Valore lotti attivi/in scadenza — riusa `arricchisci_lotto` di Tranche 0
  (semaforo + valore economico), sommati per la prima volta.
- Valore lotti smaltiti nel mese — nuovo: `costo_pezzo × quantità` al
  momento dello smaltimento (lo smaltimento non azzera `quantita`, quindi
  il dato rappresenta il valore realmente buttato).
- Costo spreco giorno/mese — **somma** invenduto al banco (chiama
  `vendita_banco.get_report_sprechi` esistente, non ne duplica la logica)
  + lotti smaltiti nello stesso periodo (mai sommati insieme prima).
  - Margine per prodotto/reparto — ricalcola margine da prezzo/costo
  correnti di `prodotti_vendita` (stesso calcolo di `GET /prodotti-vendita/`,
  per non avere due fonti che divergono) e aggiunge il join verso
  `ricette.reparto` che non esisteva (necessario per "margine per
  reparto"). Prodotti più costosi/meno redditizi = stesso dataset ordinato.
- Variazione prezzi materie prime — stessa logica di raggruppamento di
  `ingredienti.py::prezzi-alert` (delta prezzo tra fornitori per lo stesso
  ingrediente canonico) ma con nomi leggibili invece della mappa
  product_id→delta usata per i badge ordini.
- Fornitori con maggiore incidenza — nuovo: spesa totale per fornitore nel
  periodo da `fatture`, mai aggregata prima.

**Frontend**: nuova vista `DashboardEconomicaView.jsx` (tab "Dashboard
economica", dropdown Altro + ActionCard in Home/Area ufficio). Selettore
mese, 5 KPI tile cliccabili (valore attivi, in scadenza, smaltiti,
spreco oggi/mese) che espandono il dettaglio sottostante, e 5 sezioni con
liste classificate a barra proporzionale (margine per reparto, fornitori,
prodotti più costosi/meno redditizi, variazione prezzi). Palette del
design system esistente (salvia/sabbia/danger/warning/success), nessun
colore freddo, nessun grafico multi-serie (solo liste a singolo hue —
skill dataviz consultata, non serviva un grafico vero e proprio per
questi dati).

**Verifica eseguita**: compileall + import-check CI-equivalenti OK; test
end-to-end con mongomock — scenario con lotti attivi/scaduti/smaltiti,
fatture di 2 fornitori, prodotto con ricetta+reparto, ingrediente con 2
prezzi fornitore: tutti i numeri (valore totale, valore in scadenza,
valore smaltiti, costo spreco, margine per reparto, incidenza fornitori,
variazione prezzo) risultano esattamente quelli attesi a mano. Build
frontend (`CI=false npm run build`): Compiled successfully.

**Le 7 macro-funzionalità richieste da Enzo il 03-04/07/2026 sono ora
tutte coperte** (Scadenza intelligente, Produzione consigliata ancora da
fare, Intelligenza operativa frigoriferi, Dashboard economica, Cronologia
completa lotto, Miglioramenti UI ancora da fare, Gemello digitale del
lotto). Restano le Tranche 5 (Produzione consigliata) e 6 (Miglioramenti
UI trasversali: mappa visiva, ricerca globale estesa, barra conformità
HACCP dedicata, guida rapida) — le più "greenfield" del piano originale.

## Tranche 5 — Produzione consigliata (04/07/2026)
Seguito delle Tranche 0-4. Punto 2 delle 7 macro-funzionalità, il più
"greenfield" del piano (nessuna base di codice esistente oltre allo
storico grezzo). Motore scritto da zero, ma riusa gli helper già esistenti
di `corrispettivi.py` (festività, rilevamento campi/serie incassi) invece
di duplicarli.

**Nuovo router** `backend/routers/produzione_consigliata.py`
(`GET /produzione-consigliata?data=YYYY-MM-DD`, default domani):
- Per ogni prodotto con **almeno 2 osservazioni storiche** nello stesso
  giorno della settimana (finestra 90 giorni) su `produzioni`: media
  produzione storica come base del consiglio. **Regola esplicita**: sotto
  2 campioni il prodotto viene escluso, mai un default inventato.
- Riduzione fino al 30% se l'invenduto medio storico (da `vendite_banco`,
  stesso giorno settimana) supera il 20%.
- Aumento del 25% se la data target è festività o ponte (riusa
  `corrispettivi.festivita_imminenti`, stesso dato dell'alert "anticipa
  gli ordini").
- Fattore ±15% (dimezzato, prudente) se l'andamento incassi delle ultime 2
  settimane rispetto alle 2 precedenti è significativo (riusa
  `corrispettivi._campi_rilevati`/`_serie`, stesso rilevamento schema
  usato per gli altri endpoint corrispettivi).
- Nota informativa se il prodotto è marcato stagionale
  (`prodotti_vendita.stagionale`/`stagione_note`) — **non un fattore
  quantitativo**: il modello dati non ha una finestra di mesi strutturata,
  onestamente segnalato solo come nota in motivazione.
- Ogni suggerimento ha una `motivazione` testuale che elenca i fattori
  applicati, oltre a `media_produzione`/`media_invenduto` separati.
- Ranking trasversali "prodotti più richiesti"/"più sprecati".
- `POST /produzione-consigliata/decisione` — l'operatore accetta, modifica
  la quantità o ignora ogni suggerimento; persistito per (data, prodotto)
  in `produzione_consigliata_decisioni`. **Scelta deliberata**: la
  produzione fisica resta nel flusso normale (ModalRegistraLotto), qui si
  pianifica soltanto — coerente con la regola esplicita di non collegare
  scontrino/scarico automatico.

**Frontend**: nuova vista `ProduzioneConsigliataView.jsx` (tab, dropdown
Altro + ActionCard in Home). Toggle Oggi/Domani + selettore data libero,
card per prodotto con quantità consigliata, motivazione, azioni
Accetta/Modifica(quantità editabile)/Ignora, badge festività/trend
incassi, liste compatte "più richiesti"/"più sprecati".

**Verifica eseguita**: compileall + import-check CI-equivalenti OK; test
end-to-end con mongomock — prodotto con 4 campioni storici e 30% di
invenduto medio: quantità consigliata correttamente ridotta rispetto alla
media, motivazione corretta, prodotto stagionale segnalato; prodotto con 1
solo campione correttamente escluso (dati insufficienti); decisione
"modificato" salvata e recuperata correttamente nella chiamata successiva.
Build frontend (`CI=false npm run build`): Compiled successfully.

## Tranche 6 — Miglioramenti UI trasversali (04/07/2026)
Ultima tranche del piano originale (punto 6 delle 7 macro-funzionalità).
Prima di costruire, verificato cosa esisteva già per non duplicare:

**Già soddisfatto da sistemi esistenti (nessuna modifica in questa
tranche)**:
- **Barra conformità HACCP** → `SupervisoreBadge.jsx` + `GET /supervisor/
  stato` sono già esattamente questo: semaforo verde/arancione/rosso,
  contatori critici/alti/medi/bassi, elenco alert con deep-link e
  possibilità di silenziare (i critici no, per decisione Enzo del
  04/07/2026 stessa). Costruire un secondo sistema sarebbe stata
  duplicazione pura.
- **Guida rapida su ogni pagina** → esiste già un pulsante "Guida" fisso
  nell'header (`btn-guida-header`, App.js), raggiungibile da qualunque
  pagina con un clic, che apre la guida completa (skill `guida-operativa`,
  già "31 sezioni, 121 bottoni" per iterazione precedente).
- **Modalità dipendente/amministratore, icone grandi tablet, colori
  coerenti verde/giallo/rosso** → già implementati (PIN/ruoli, TabletView/
  ModalRegistraLotto, semaforo scadenza di Tranche 0). Nessun gap
  concreto trovato da colmare qui.

**Costruito in questa tranche (i gap reali)**:
- **Ricerca globale** — nuovo router `backend/routers/ricerca_globale.py`
  (`GET /ricerca-globale?q=...`): aggrega lotti, ricette, fornitori,
  materie prime (dizionario_prodotti), attrezzature/frigoriferi in
  un'unica risposta categorizzata (prima esisteva solo la ricerca
  universale dei lotti). Frontend: `RicercaGlobale.jsx`, pulsante "Cerca"
  nell'header globale (visibile su tutte le pagine), pannello a tendina
  con risultati per categoria, clic naviga alla pagina giusta.
- **Mappa visiva tracciabilità** — nuova vista `MappaTracciabilitaView.jsx`
  (tab + ActionCard in Home): fattura → materia prima → ricetta → lotto →
  frigo → banco → invenduto → recupero/smaltimento. Puramente
  navigazionale (ogni nodo apre la pagina reale corrispondente), nessun
  dato inventato; "Banco"/"Invenduto" aprono l'app tablet (stesso
  comportamento già usato da altre ActionCard di Dashboard).
- **Pulsante "Cosa devo fare oggi"** — pannello consolidato in cima alla
  Dashboard (sopra il cruscotto KPI): unisce lotti urgenti (Tranche 1),
  suggerimenti di produzione non ancora decisi (Tranche 5, nuova query
  `GET /produzione-consigliata` per domani) e alert critici HACCP
  (`GET /supervisor/sommario`, già esistente) in un'unica lista d'azione
  con collegamenti diretti; messaggio "tutto in regola" se non c'è nulla
  di urgente.

**Verifica eseguita**: compileall + import-check CI-equivalenti OK; test
end-to-end con mongomock per la ricerca globale (query "babà" trova
correttamente lotto, ricetta, fornitore, materia prima e attrezzatura
con quel nome, totale 5). Build frontend (`CI=false npm run build`):
Compiled successfully.

## Le 7 macro-funzionalità richieste da Enzo (03-04/07/2026): tutte con
una prima implementazione reale, in 7 tranche (0-6), ciascuna con build
locale, test end-to-end (mongomock), PR, CI verde e merge. Verifica live
non eseguibile da questo ambiente sandbox (limite di rete confermato più
volte) — da fare a cura di Enzo sul sito reale. Possibili seguiti futuri,
se richiesti: log reale delle stampe etichetta, registro dei richiami
eseguiti (oggi solo ricerca on-demand), estensione della "produzione
consigliata" con più fattori, audit di coerenza colori/design su tutte le
pagine nuove.

## Seguito: registro richiami eseguiti + aggiornamento memoria tecnica (04/07/2026)
Su richiesta di Enzo dopo le 7 tranche, due seguiti mirati:

**1. Registro richiami eseguiti** — colma il gap esplicitamente
documentato in Tranche 3 ("i richiami sono ricerche on-demand, non eventi
persistiti"):
- Nuova collection `richiami_eseguiti` + 3 endpoint in `lotti_produzione.py`:
  `POST /lotti/recall/esegui` (registra formalmente il richiamo sui lotti
  trovati da una ricerca `/recall/cerca`, logga un evento "recall" su
  ciascun lotto coinvolto), `GET /lotti/recall/eseguiti` (elenco),
  `PATCH /lotti/recall/eseguiti/{id}/concludi` (chiude con azione
  correttiva).
- `GET /lotti/{id}/scheda-completa` arricchita con `richiamo_collegato`
  sui movimenti (stesso pattern già usato per `anomalia_collegata`).
- Frontend: pulsante "✓ Registra come richiamo eseguito" nella modale
  recall esistente di `LottiList.jsx`, accanto al già esistente "Scarica
  Report Recall"; il gemello digitale del lotto (`SchedaLottoModal.jsx`)
  mostra ora il richiamo collegato in cronologia.
- **Verifica eseguita**: compileall + import-check OK; test end-to-end
  mongomock — richiamo registrato, lotto riceve movimento "recall",
  richiamo concluso con azione correttiva, scheda completa mostra il
  richiamo collegato correttamente. Build frontend: Compiled successfully.

**2. Aggiornamento memoria tecnica** — `memory/claude.md` (v67) e
`memory/PRD.md` aggiornati con: le 3 nuove collection (`movimenti_lotto`,
`produzione_consigliata_decisioni`, `richiami_eseguiti`), il nuovo campo
`lotti.posizione` (e i campi non persistiti `stato_scadenza`/
`valore_economico`), tutti i nuovi endpoint delle 7 tranche + registro
richiami, e un bug noto scoperto in Tranche 2 (regex sui primi 6
caratteri in `anomalie.registra_anomalia` che confonde attrezzature con
lo stesso prefisso — non corretto nello snapshot storico, solo nel nuovo
`GET /anomalie/{id}/lotti-attuali`).

## Confronto prezzi con cataloghi esterni al carrello (04/07/2026)
Richiesta Enzo: quando aggiunge un prodotto al carrello ordini, verificare
se un catalogo esterno (es. offerte settimanali di un sito come Sunset
Cash) ha lo stesso prodotto a un prezzo migliore rispetto al fornitore
abituale, e avvisarlo (mai sostituire automaticamente).

**Scoperta importante**: la "sezione dove inserire gli indirizzi" che
Enzo chiedeva esiste GIÀ (`fonti_catalogo.py` + `CataloghiEsterniView.jsx`,
pagina "Cataloghi fornitori (web)", costruita il 03/07/2026 su sua stessa
richiesta) — connettore generico che legge Schema.org/Open Graph da
qualunque sito e-commerce, senza scraper dedicato per sito. Non serviva
ricostruirla.

**Nuovo in questa sessione**: `GET /fonti-catalogo/confronta?nome=X&
prezzo_attuale=Y` in `fonti_catalogo.py`. Confronta un nome prodotto con i
prodotti già raccolti da fonti_catalogo (`fonte_scraping:
"generico_ldjson_og"`, quindi ESCLUSI Saima/MEPA/Acquaviva che sono già
"fornitori abituali" — quelli sono il termine di paragone, non
l'alternativa). Match volutamente STRETTO (decisione Enzo): normalizza i
nomi (accenti, punteggiatura), richiede una sovrapposizione di parole
≥50% (Jaccard) E, se entrambi i nomi specificano un formato/quantità
(es. "33cl", "x24"), quello deve combaciare — una lattina non risulta mai
"equivalente" a una bottiglia dello stesso brand solo perché il nome è
simile. Ritorna la migliore corrispondenza + se conviene + risparmio.

Frontend: agganciato nel punto UNICO di aggiunta al carrello
(`useCart().aggiungi` in `CatalogoFornitoreView.jsx`, condiviso da tutte
le viste catalogo). Dopo l'aggiunta, chiama il confronto in background
(non blocca l'azione) e se conviene mostra un `toast.warning` con
fornitore/prezzo/risparmio e un bottone "Vedi offerta" che apre il link
al prodotto — solo un avviso, mai una sostituzione automatica (decisione
Enzo).

**Limite onesto**: verificato che questo ambiente sandbox non ha
`MONGO_URL` configurata — nessun accesso al database reale di produzione.
Non posso quindi confrontare "a mano" i prezzi reali già in memoria (da
fattura) con quelli di un catalogo esterno finché non gira in produzione;
posso però leggere prezzi da foto/screenshot che Enzo mi manda (fatto per
un esempio Sunset Cash: Coca-Cola/Fanta/Sprite 33cl cassa x24 = €15,30)
per un confronto manuale se lui mi fornisce il prezzo attuale pagato.

**Verifica eseguita**: compileall + import-check CI-equivalenti OK; test
end-to-end con mongomock — Coca Cola 33cl x24 a €14,90 (fonte esterna)
risulta "conviene" rispetto a un prezzo attuale di €16,50 (risparmio
€1,60); la stessa bevanda in formato 50cl (prezzo più basso in assoluto,
€12,00) NON fa match per via del formato diverso; un prodotto diverso
(Fanta) non fa match; un prodotto con lo stesso nome ma fornitore Saima
(non fonti_catalogo) è correttamente escluso dai candidati. Build
frontend (`CI=false npm run build`): Compiled successfully.

**Prossimo passo per Enzo**: aggiungere "Sunset Cash" nella pagina
"Cataloghi fornitori (web)" con l'indirizzo del sito e cliccare
"Sincronizza" (va fatto sul sito live, il sandbox di sviluppo non ha
accesso a internet) — da quel momento il confronto automatico al carrello
funziona su quella fonte.

---

---

## 04/07/2026 — Sunset Cash: schede catalogo DINAMICHE dalle fonti web

Enzo ha mandato www.sunsetcash.it (nuovo fornitore da catalogare).
Dalla sandbox il sito non è raggiungibile (proxy), ma il flusso è
quello già costruito: pagina Cataloghi Fornitori (web) → Aggiungi →
Sincronizza (il backend Render ha rete piena).

BUCO TROVATO E CHIUSO: le schede dei cataloghi in Listini & Vendita
erano HARDCODED (saima…bindi) — una fonte web nuova si sincronizzava
in catalogo_forno_prodotti (fornitore = fornitore_key slug) ma NON
aveva nessuna scheda dove sfogliarla. Ora ProdottiVenditaView carica
GET /api/fonti-catalogo e crea UNA SCHEDA DINAMICA per ogni fonte con
prodotti_trovati > 0 (CatalogoGenericoView con
fetchUrl=/catalogo-forno/prodotti?fornitore={key}): stesso carrello,
stessa stella colazione, deep-link #prodotti/{key} funzionante.
Bonus: aggiunto "bindi" alla whitelist di prodottiFiltrati (mancava:
caricava i dati "miei" a vuoto sul tab Bindi).
Collaudo "Sunset Cash: fonte web e scheda catalogo dinamica" nel seed
con i passi esatti per Enzo. Build ok (main.24e4be2d.js).

---

## 04/07/2026 — Lacune dall'audit onesto dell'altra sessione: implementate

Enzo ha portato l'audit finale dell'altra chat (7 macro-funzionalità
HACCP) e ha chiesto di implementare le lacune principali. Fatto:

**"Usa oggi" (Cosa usare oggi)**: bottone primario su ogni card →
POST /task-dipendenti (tipo scadenza, priorità urgente, reparto tutti):
il lotto compare in "📋 Cosa fare oggi" sui tablet, con chi l'ha
segnalato nella descrizione.

**Dashboard economica — drill-down completo**:
- tile "Valore lotti attivi" ora cliccabile → dettaglio top 20 per
  valore (nuovo lotti_attivi_dettaglio nel backend), riga → #lotti
  con ricerca precompilata;
- tile "Costo spreco oggi" ora cliccabile → dettaglio banco+smaltiti
  (nuovi dettaglio_banco/dettaglio_smaltiti in _costo_spreco_periodo);
- righe delle 5 liste classificate TOCCABILI (BarraLista.onRiga):
  fornitore → #fornitori/{slug}, prodotto → scheda ricetta
  (ricetta_id ora incluso nei margini), variazione prezzi →
  #comparatore con ricerca precompilata (nuovo ricevitore
  sessionStorage comparatore_search), reparto → #ricette.
- FIX: _fornitori_maggiore_incidenza filtrava il periodo con $gte/$lte
  STRINGA su data_fattura (formato misto — stessa famiglia di bug
  bonificata ieri, reintrodotta dall'altra sessione): ora date vere
  via parse_data_flessibile.

**Gemello digitale del lotto (SchedaLottoModal) completato**:
- Quantità PRODOTTA (pezzi) accanto alla residua;
- elenco "Ingredienti usati" (nuovo campo ingredienti nella
  scheda-completa backend);
- "Apri fattura" sulle righe provenienza (backend risolve lotto
  scalato → lotti_fornitori.fattura_ref → fatture.id);
- bottoni "Apri ricetta" (apri_ricetta_id), "Apri recall" (#lotti con
  ricerca sul numero lotto), "Registro HACCP" (#registro_haccp);
- "Stampa report" separato dall'etichetta: nuovo
  GET /stampa/report-lotto/{id} (A4, dati+ingredienti+provenienza+
  cronologia completa, palette salvia).

Collaudo "Usa oggi + drill-down dashboard + gemello completo" nel
seed. Verifiche: pyflakes ok, compile+import ok, 30 test puri passati
(un test d'integrazione pre-esistente fallisce la collection senza
backend live — limite ambiente noto), build ok (main.302469b2.js).

---

## 04/07/2026 — Sezione Acquisti & Ordini semplificata (segnalazioni Enzo)

Quattro problemi segnalati da Enzo sull'uso reale, quattro fix in
OrdiniView:
1. RIORDINI, quantità libera: prima l'unico modo era "+ N pz" (aggiunge
   il suggerito) e poi correggere a colpi di −. Ora ogni riga
   sotto-soglia ha −/quantità/+ E POI «+ Aggiungi» (RigaAggiungiQta):
   scegli 3, aggiungi 3. markLow accetta la quantità.
2. DA INVIARE, righe pre-spuntate: "se le ho aggiunte io, perché devo
   rispuntarle?" — al caricamento sel viene inizializzato con TUTTE le
   righe di ogni bozza; il banner ora dice di TOGLIERE la spunta a ciò
   che non si vuole. La conferma parziale resta possibile.
3. CARRELLO, miglior prezzo: il backend ordinava già il comparatore col
   migliore in cima e il carrello lo usava come default, ma l'etichetta
   «scegli il migliore» faceva credere il contrario. Ora dice «il
   migliore è già scelto ✓» (o «cambiato a mano»), e la prima opzione
   del menu è marcata ★ MIGLIORE.
4. CATALOGO, accesso ai cataloghi: il singolo link "Sfoglia i cataloghi"
   (che portava solo a Saima) è diventato una riga di CHIP, uno per
   catalogo: Acquaviva, SAIMA, MePA, Il Pasticcere, Tre Marie, Alfa,
   Sammontana, Bindi + le fonti web sincronizzate (GET /fonti-catalogo,
   es. Sunset Cash) — tutti sullo stesso carrello.
Collaudo "Ordini semplificati" nel seed. Build ok (main.e6974664.js).

---

## 04/07/2026 — Regola "mani sporche": motivi a tendina, mai tastiera

NUOVA REGOLA PERMANENTE (scritta in REGOLE_ENZO.md): il pasticcere ha
sempre le mani sporche — deve agire su automazioni e scelte pronte,
MAI scrivere con la tastiera nei flussi operativi. Ogni campo di testo
libero (motivi, azioni correttive) va sostituito con tendina di opzioni
+ «Altro (scrivi tu)» come eccezione.

Nuovo componente condiviso shared/SceltaMotivo.jsx (select + reveal
"Altro", liste MOTIVI centralizzate) applicato a:
- Ricezione Merce, lotti da verificare: azione correttiva non conforme
  (sia pannello da-fattura sia form manuale) — era textarea libera;
- SchedaLottoModal (gemello digitale): motivo di sposta/congela/
  recupera e azione correttiva HACCP dello smaltimento (obbligatoria,
  prima textarea);
- Controllo Olio: azione correttiva fuori norma (5 opzioni pronte);
- Temp. Cottura: azione correttiva sotto soglia (4 opzioni pronte).
Le temperature positive avevano GIÀ le 5 scelte predefinite: pattern
ora uniforme. Per i flussi futuri: aggiungere liste in MOTIVI, non
creare textarea. Collaudo "Mani sporche" nel seed.
Build ok (main.c7439b38.js).

---

## 04/07/2026 — Dizionario: battesimo righe XML con proposta (piano approvato)

Richiesta Enzo: pagina persistente con le righe XML dei fornitori
Magazzino+Lotti, nome canonico PROPOSTO accanto a ogni riga (conferma a
un tocco o correzione), prezzo/quantità/unità come in fattura, e
promemoria a ogni fattura nuova. Realizzato potenziando il Dizionario
Ingredienti esistente (#dizionario):

BACKEND:
- fatture.aggiorna_dizionario_prodotto: persiste ultimo_prezzo_riga,
  ultima_quantita_riga, ultima_unita_riga (dati COME IN FATTURA) in
  entrambi i rami insert/update — le righe storiche li acquisiscono
  alla prossima fattura che le tocca;
- GET /food-cost/dizionario: param solo_completi (esclude fornitori
  solo_magazzino/escluso; default di chi non ha il campo = completo) +
  proposta_canonico calcolata con match_livello2 per le righe scoperte;
- nuovo GET /food-cost/dizionario/canonici (distinct) per l'autocomplete;
- Supervisore DATI4: "N righe fattura da battezzare nel Dizionario"
  (media, route dizionario, items ≤60 riga·fornitore) — esclude i
  fornitori non-completi.

FRONTEND (DizionarioIngredientiView):
- proposta PRE-COMPILATA nel campo + scritta "proposta del sistema" +
  bottone verde «Conferma proposta» (un tocco, regola mani-sporche);
- riga "ultimo acquisto": € prezzo · quantità unità (fallback €/kg per
  le righe storiche);
- checkbox «Solo Magazzino+Lotti» (default ON) → solo_completi;
- datalist canonici-diz per la scrittura manuale senza refusi;
- testo intro aggiornato.
Collaudo "Dizionario: battesimo righe XML con proposta" nel seed.
Verifiche: pyflakes ok, compile+import ok, 30 test puri, build ok
(main.98bf24d6.js).

## 2026-07-05 — Backfill dati storici Dizionario + guida aggiornata (sessione repo-review-completion-40cdmd)

Completamento "vedi tutto quello che manca" dopo il battesimo Dizionario:

BACKEND:
- food_cost: nuovo POST /food-cost/backfill-dati-riga-dizionario (solo
  amministratore, idempotente): scorre le fatture dalla più recente
  (parse_data_flessibile) e riempie ultimo_prezzo_riga /
  ultima_quantita_riga / ultima_unita_riga SOLO dove mancano — così le
  righe storiche del Dizionario mostrano subito prezzo·quantità·unità
  senza aspettare una fattura nuova. Ritorna {ok, aggiornati,
  senza_fattura_trovata}.
- collaudi._seed_mancanti: i passi dei collaudi già seminati ma ancora
  "da_fare" vengono aggiornati se il seed nel codice si arricchisce
  (mai toccati quelli eseguiti). Aggiunto al collaudo Dizionario il
  passo del bottone «Completa dati storici».

FRONTEND:
- DizionarioIngredientiView: bottone admin «Completa dati storici»
  (icona DatabaseZap) → chiama il backfill, toast con il conteggio,
  ricarica l'elenco.
- Guida aggiornata (guidaContenuti.json → in-app + PDF rigenerato
  stesso path /guida/Guida_Operativa_Lotti.pdf): sezioni dizionario
  (battesimo/proposta/backfill), ordini (quantità libera −/+, righe
  pre-spuntate, migliore ✓, chip cataloghi), ricezione (tendina motivi
  mani-sporche), lotti (gemello digitale completo + Stampa report).

Verifiche: pyflakes ok (solo warning pre-esistenti), compile+import ok,
30 test puri passati, build frontend ok.

RESTANO IN ATTESA DI ENZO (nessuna azione tecnica possibile da qui):
collaudi arretrati in Home → Collaudi da fare (~17); conferma backup
Atlas (sblocca migrazione date ISO); sync Sunset Cash da Cataloghi
Fornitori (web); pallino Drive se ancora ocra (serve screenshot
Environment); verificare Napolitano Group marcato "escluso".

## 2026-07-05 — FIX backfill Dizionario: 0 aggiornati al primo run (bug reale)

Enzo ha premuto «Completa dati storici» → 0 righe. Causa VERIFICATA nel
codice: il dizionario contiene DUE famiglie di chiavi nome_normalizzato
(debito noto "4 semantiche di normalizzazione", tranche T2):
- descrizione grezza minuscola (import fattura-per-fattura,
  fatture.aggiorna_dizionario_prodotto);
- normalizza_nome_prodotto() minuscolo (POST /food-cost/sincronizza-fatture,
  food_cost.py ~1168: toglie pesi/lotti/moltiplicatori).
Il backfill matchava SOLO la forma grezza → 0 match sulle righe create
dalla sincronizzazione. Fix: per ogni riga fattura calcola ENTRAMBE le
chiavi e aggancia quelle presenti tra le scoperte; salta prezzi <= 0
(voci contabili/omaggi); conta i modified_count reali; risposta con
diagnostica (totale_righe, righe_scoperte, senza_fattura_trovata) e
toast più parlante. Questo doppio-binario è il sintomo del debito T2:
l'unificazione delle semantiche resta programmata dopo i collaudi P1.

## 2026-07-05 — Audit adversariale + tranche sicurezza (sessione repo-review-completion-40cdmd)

Su richiesta di Enzo ("analisi critica pessimistica, trova tutti i bug"),
lanciati revisori paralleli in sola lettura. Applicati SUBITO i fix
sicuri e localizzati (fail-closed, nessun cambio del percorso normale);
i difetti che richiedono refactor testato sono elencati nel rapporto a
Enzo e restano gated sui collaudi P1 (sua decisione: prima collaudi).

SICUREZZA — gate di RUOLO server-side (auth.require_admin, nuovo):
auth_dependency verificava solo la PRESENZA del token, mai il ruolo →
un token dipendente passava su tutte le rotte admin. Blindati gli
endpoint distruttivi/di configurazione con Depends(require_admin):
- backup.py: ripristina, download, esegui, export-json;
- tablet_operatori.py: crea/aggiorna/abilita/ignora dipendente
  (un dipendente poteva auto-promuoversi amministratore via PATCH);
- diagnostic.py: pulizia-collezioni (drop);
- utils.py: pulizia-dati-spazzatura.

CONCORRENZA — claim atomico contro il doppio tap:
- produzioni.py DELETE storno: find_one_and_delete PRIMA del ripristino
  scorte (prima due tap ripristinavano le quantità due volte);
- ordini_fornitori.py invia: find_one_and_update con filtro
  stato!=inviato_fornitori (prima due tap creavano due bozze residue e
  due eventi ORDINE_INVIATO).

DATO — typo gemello: pipeline.py scriveva ultima_data_fattura (campo
morto, nessuno lo legge) invece di ultima_fattura_data → il refresh
notturno della data d'acquisto era perso. Allineato.

VISIBILITÀ — swallow silenziosi resi loggati (nessun cambio di flusso):
ricezione_merce.py (chiusura ordine collegato) e fatture.py
(prezzo/quantità non parsabili → food cost 0) ora logano warning.

DA PORTARE A ENZO (gated collaudi P1, nel rapporto): PIN admin hard-coded
in tablet_operatori.py e pin_chiaro nel DB (va spostato in env e i PIN
vanno cambiati perché già nella storia git); motore prezzi unico (4
collection derivate con semantiche ultimo/minimo che si sovrascrivono +
doppia chiave nel dizionario); date a formato misto in ~25 sort/aggregate
(recall ASL incompleto, giacenza congelatore, costi da fatture stantie) —
tranche T3 date ISO; race FIFO su scarico lotti ($set non atomico);
vocabolario stato lotti con valori-filtro mai scritti.

## 2026-07-05 — Food cost: match più economico + id stabili + azzera protetto

Dal revisore soldi/quantità, tre difetti VERIFICATI corretti subito:

C1 (CRITICO) — trova_prodotto_dizionario (food_cost.py ~2566) ordinava
tutti i candidati con -prezzo → a parità di match vinceva il prezzo più
ALTO: "farina" agganciava "farina di mandorle" €12,9 invece di "farina
00" €0,62; "zucchero" → "zucchero a velo" invece del semolato. Food cost
gonfiato in modo sistematico e silenzioso su tutte le ricette con
ingredienti generici. Fix: helper _pref(prezzo)= prezzo se >0 altrimenti
inf → prima gli omonimi CON prezzo, poi il più economico (coerente col
commento "preferenza prezzo>0"). Verificato per esecuzione: farina→0,62,
zucchero→0,9.

C2 (CRITICO) — POST /food-cost/sincronizza-fatture rigenerava l'id di
OGNI riga a ogni run → i prodotto_dizionario_id salvati nelle ricette
diventavano orfani (food cost ricadeva sul fuzzy match) e le PATCH
scorta-minima/aggiorna davano 404. Fix: se la riga esiste già, non
sovrascrivere il suo id (id nuovo solo per righe nuove).

C3 (ALTO) — sincronizza-fatture?azzera=true (delete_many del dizionario:
scorte minime, canonici, alias, righe manuali senza fattura) era
chiamabile da qualsiasi token. Ora richiede ruolo amministratore.

RIMANDATI al rapporto (motore prezzi unico, gated collaudi P1): C4 motore
sincronizza divergente da calcola_prezzo_quantita_kg (birra/olio/acqua
LT gonfiati); A1 doppia semantica ultimo/minimo su prezzo_kg; A3 litri
"unità-prima" (LT.5) non riconosciuti all'import; A4 quantita_disponibile
_kg non è una giacenza (riordino materie prime che non scatta); A5/A6
comparatore su basi diverse + dual-key; M1-M9 (sanity mute, euristiche
fragili, doppi magazzini).

## 2026-07-05 — Frontend: documenti HACCP 401, crash nome null, virgola italiana

Dal revisore frontend, fix sicuri e localizzati (build verde):

DOCUMENTI HACCP che aprivano un 401 al posto del documento (AUTH_ENFORCE
attivo su Render; withToken già esisteva ma non applicato qui):
- ManualeHACCPView: fetch(withToken(urlManuale)) + check res.ok (prima
  il viewer mostrava il JSON "Autenticazione richiesta");
- HACCPPdfButton (report mensile in navbar), RegistroHACCPView (stampa),
  SaimaRicettariView (pdf-proxy, bottone + link download): window.open /
  href con withToken.

CRASH da nome null (white screen) protetti con (x.nome || ""):
ColazioneAcquavivaView:503, VenditaBancoView:788, LottiList:216.

VIRGOLA ITALIANA (dati salvati a 0/null in silenzio):
- RicezioneMerceView: temperatura HACCP da type="number" (che azzera
  "1,5") → type="text" inputMode="decimal" + normalizzazione virgola in
  conformità e POST;
- ScontiMerceView: 5 campi numerici → text/decimal + helper num() in
  anteprima e payload (prima cartoni/valori salvati a 0).

RIMANDATI al rapporto (tranche design/architettura): 455 emoji in 55
file (emoji nell'header di ogni pagina via PAGE_META), ~420 hex freddi
inline in 25 file; App.js che scarica 4 collezioni ovunque + re-render
globale sulla ricerca lotti + /ricette doppia; polling senza fine;
bottoni troppo piccoli e testi a 7-8px in FornitoriList; chiamata orfana
/fatture/stato-sync; gate admin solo client su 4 sezioni backend.

## 2026-07-05 — PUNTO 1 motore prezzi unico: litri "unità-prima" all'import (bug VIVO)

Enzo: "procedi con il punto 1". Ricognizione: il percorso VIVO dei prezzi è
l'import (fatture.aggiorna_dizionario_prodotto → calcola_prezzo_quantita_kg
in xml_helpers), già motore buono; POST /food-cost/sincronizza-fatture (la
copia divergente col minimo storico) NON ha chiamanti (né frontend né
scheduler) → non corrompe attivamente. Il vero buco VIVO era nell'estrazione
peso dell'import.

BUG VIVO CORRETTO (verificato per esecuzione): estrai_quantita_da_descrizione
non riconosceva i litri/ml con l'UNITÀ PRIMA del numero → olio/latte/acqua
"LT.5", "LT 1,5", succhi "ML200" finivano in 'nessuna_info' e il prezzo del
CONTENITORE veniva preso come €/kg (olio 5L a €40 → 40 €/kg invece di 8).
Aggiunti i pattern `\bLT[\.\s]*(\d+)` e `\bML[\.\s]*(\d+)`.
ATTENZIONE (verifica avversariale che ha evitato un bug peggiore): il singolo
"L." NON va toccato — è il prefisso dei numeri di LOTTO ("AGLIO L.372",
"BASILICO L.417291") e un pattern L-generico li leggeva come 372/417291 litri.
Tenuto solo "LT"/"ML" (mai prefissi di lotto); "L.5" nudo resta affidato alla
regola confermata/battesimo (comportamento già documentato e testato).
Nuovo test tests/test_prezzo_kg_litri_unita_prima.py (litri/ml unità-prima +
guardia anti-lotto). Suite pura: 59 passati.

Stato "motore unico": il percorso vivo è ora un solo motore corretto. Restano
(cleanup, non corruzione attiva): la copia divergente in sincronizza-fatture
(orfana, azzera già solo-admin — da far delegare o rimuovere) e le righe
dizionario a doppia chiave create da run passati (dedup una tantum da valutare).

## 2026-07-05 — Date a formato misto: registri ASL e giacenze (backup Atlas confermato)

Enzo ha attivato il backup Atlas → sbloccata la bonifica date. Corretti i
punti a impatto LEGALE e SOLDI (confronti/regex su data a formato misto
dd/mm/yyyy + ISO, con parse_data_flessibile):

LEGALE (record che sparivano dai registri ASL):
- lotti_produzione recall ASL: il .sort().limit(200) lessicografico poteva
  ESCLUDERE i lotti recenti in ISO dal richiamo. Ora fetch completo del
  match + ordinamento Python sulla data vera + taglio finale.
- anomalie report annuale ("^{anno}" prendeva solo ISO) e range
  ("/({anni})$" prendeva solo dd/mm/yyyy): ora filtro sull'anno reale.
- registro-lotti mensile/CSV/annuale: la regex "/{mese}/{anno}" e "/{anno}$"
  escludeva i lotti ISO (pesce, colazione). Ora filtro anno/mese reali; anche
  il raggruppamento per mese del registro annuale usa la data vera.

SOLDI:
- acquaviva giacenza congelatore: "ultime 2 fatture" ora per data vera (era
  sort lessicografico); e data_min_fattura portata in ISO prima del $gte su
  vendite_banco.data (ISO) — prima confronto tra formati diversi → giacenza
  sballata.
- pipeline step_costi_acquaviva: "ultime 2" per data vera (era .sort().to_list(2)).

Nuovo comportamento verificato: compile+import ok, 59 test puri.
RESTANO (ordine di visualizzazione, non perdita dati — bassa priorità):
fornitori_schede ultima_consegna, utils registro tracciabilità sort,
produzioni grafici $substr, sconti_merce storico, supervisor sort scadenza,
fatture/aggiornamento_ricette created_at (tipo misto Date/stringa),
magazzino_unificato tiebreaker FIFO su data_scadenza.

## 2026-07-05 — Import fatture da Google Drive: causa trovata (cartella non condivisa) + diagnostica

Enzo: "import da Drive non funziona, ho cambiato il file json su Render".
Indagine con Google Drive MCP (letto lo stato reale del Drive):
- La cartella "fatture" (id 1K9EJZ8P...) CONTIENE le fatture XML di Enzo
  (decine di file, tutte di ceraldigroupsrl@gmail.com) → le fatture SONO
  su Drive.
- I permessi della cartella: UN SOLO permesso, owner ceraldigroupsrl. NON
  è condivisa con nessun altro (né "chiunque con il link", né il service
  account). → CAUSA RADICE: la cartella è privata, quindi né l'API key né
  il service account (l'identità che usa Lotti) possono leggerla. Il commento
  nel codice ("condivisa con link") non corrisponde alla realtà.

drive_fatture.py — reso azionabile:
- validazione del JSON PRIMA di chiamare Drive (JSON non valido / private_key
  troncata / client_email mancante → messaggio chiaro, non più 500 generico);
- su 403/404 il motivo dice ESATTAMENTE cosa fare (condividi la cartella con
  la client_email del service account, oppure metti la cartella link-shared
  se usi l'API key);
- nuovo GET /drive-fatture/diagnostica: verifica passo-passo (json_valido,
  autenticazione_ok, accesso_cartella_ok, file_xml_trovati) + service_account_
  email (NON è un segreto: serve per condividere) + diagnosi + azione.
- GET /stato ora include service_account_email.
Frontend ImportaFattureView SyncDriveCard: pulsante «Perché non funziona?»
che mostra la diagnosi e l'email da autorizzare.

NON verificabile da qui: se le fatture sono GIÀ in Lotti (backend live bloccato
dal proxy sandbox, 403). Logicamente: col folder non condiviso il sync Drive
non può mai aver importato nulla → le fatture in Lotti sono solo quelle
importate a mano. Dopo la condivisione + «Sincronizza ora», la card mostra
quante ne importa (conferma in-app).

AZIONE ENZO: aprire la cartella fatture su Drive → Condividi → aggiungere la
service_account_email (che la diagnostica mostra) come Visualizzatore → poi
«Sincronizza ora».

## 2026-07-05 — Date: coda ordine-liste (fornitori, supervisore, sconti)

Completata la coda a basso rischio delle date (ordine di visualizzazione):
- fornitori_schede: "ultima consegna" ora per data vera (era fatture[0] su
  sort lessicografico → mostrava una data vecchia);
- supervisor scaduti: i 60 mostrati sono i PIÙ scaduti (ordinati per data
  reale prima del taglio);
- sconti_merce storico: ordinato per data vera prima del limite.
Restano flaggati (aggregate $substr, più invasivi): produzioni grafici
per-giorno, utils registro tracciabilità, magazzino_unificato tiebreaker FIFO.

## 2026-07-05 — Dedup Dizionario (chiusura "punto 1" / completa tutto)

Costruito il dedup dei doppioni a doppia chiave del Dizionario:
- helper _chiave_dedup (forma pulita via normalizza_nome_prodotto) + _punteggio
  _keeper (tiene il record più ricco: canonico > manuale > scorta > acquisti >
  prezzo riga). Verificato: unisce "farina 00 kg.25"+"farina 00", tiene
  separati farina 0 / zucchero semolato vs a velo.
- GET /food-cost/dizionario/duplicati: ANTEPRIMA sola lettura (gruppi + righe).
- POST /food-cost/dizionario/dedup (admin, idempotente): riempie i buchi del
  keeper dagli altri, somma conteggio_acquisti, RIPUNTA le ricette
  (prodotto_dizionario_id) sul keeper, elimina i doppioni.
- Frontend Dizionario: bottone admin «Unisci doppioni» (anteprima → conferma →
  applica). Build ok.
NOTA: è un dedup una tantum; con descrizioni fattura diverse l'import può
ricreare righe nuove — il fix strutturale (chiave di scrittura unica) resta
il passo grosso del motore prezzi, da fare con collaudi.

## 2026-07-06 — Credenziali Drive robuste + NUOVA pagina «Confronto prezzi» prodotto

Richieste Enzo (schermate): (a) credenziali Drive messe su Render ma il
backend dice "Nessuna credenziale" (diagnostica ora attiva); (b) il
comparatore è confuso/lungo → vuole una pagina prodotto SEMPLICE: cerco
un prodotto → vedo l'ultimo prezzo di ogni fornitore → il migliore
evidenziato → lo aggiungo al carrello; nomi canonici che corregge lui e
il sistema memorizza.

CREDENZIALI (drive_fatture.py): _config() ora accetta ALIAS dei nomi env
(GOOGLE_SERVICE_ACCOUNT_JSON + varianti, GOOGLE_DRIVE_API_KEY + varianti,
DRIVE_FATTURE_FOLDER_ID + varianti) e decodifica il JSON se in base64;
la /diagnostica elenca i NOMI (mai i valori) delle env Google/Drive
presenti → così si vede se Enzo l'ha chiamata con un nome diverso (causa
tipica di "c'è ma non la vede"). La cartella nuova che ha linkato non è
accessibile dal mio account Drive (è condivisa solo col service account,
corretto).

NUOVA PAGINA (menu Altro → «Confronto prezzi», id comparatore — sostituisce
il vecchio comparatore confuso, stesso hash usato dagli alert prezzo):
- backend GET /food-cost/confronto-prodotto?q= : raggruppa dizionario per
  nome canonico (da doc o da nome_mapping), per ogni fornitore l'ULTIMA
  riga (data vera), ordina cheapest-first (su €/kg quando c'è), esclude
  fornitori esclusi;
- frontend ConfrontoProdottoView: ricerca con debounce, card per prodotto,
  fornitori ordinati col migliore evidenziato «più conveniente», bottone
  carrello che scrive in localStorage ordini_smart_carrello (compare in
  Ordini → Carrello); correzione nome inline che salva via
  /normalizzazione/correggi-mapping (memorizzato).
Build ok, import ok. Collaudo aggiunto.

## 2026-07-06 — Drive: account corretto ceraldicontabilita + cartella giusta

Enzo ha chiarito: l'account Google GIUSTO è ceraldicontabilita@gmail.com,
NON ceraldigroupsrl. Il mio accesso Drive MCP è su ceraldigroupsrl (account
vecchio) → per questo non vedo la cartella nuova. Ma soprattutto il codice
aveva hardcoded la cartella dell'account VECCHIO (1K9EJZ8P…). Corretto:
_FOLDER_DEFAULT ora è la cartella nuova (1PLR2dLe7RGyZ2rtRlvqE-EKcQ-BiNwEy)
comunicata da Enzo, meglio comunque impostarla via env DRIVE_FATTURE_FOLDER_ID.
La diagnostica ora mostra anche cartella_id e le env viste (card frontend).
Sicurezza: nessuna credenziale committata nel repo (solo i nomi delle
variabili in drive_fatture.py/ImportaFattureView).

## 2026-07-06 — Drive: lette le credenziali coi nomi ESATTI di Enzo (screenshot diagnostica)

Dalla diagnostica (screenshot Enzo): variabili viste dal backend =
GOOGLE_DRIVE_FATTURE_FOLDER_ID e GOOGLE_DRIVE_SA_JSON. Erano nomi NON
nella lista alias → "credenziale non vista". Risolto lato codice (Enzo non
deve rinominare nulla): aggiunti GOOGLE_DRIVE_SA_JSON a _ENV_SA_JSON e
GOOGLE_DRIVE_FATTURE_FOLDER_ID a _ENV_FOLDER; più un fallback _scova_sa_json()
che scova in TUTTE le env un valore che è (o è base64 di) un JSON con
client_email+private_key → funziona con qualunque nome futuro.
Verificato per esecuzione: con quei nomi cfg legge sa_json e folder
(1PLR2d…), _sa_email estrae la client_email. Dopo il deploy il backend vede
la credenziale; se la cartella nuova è condivisa col service account
ingest-fatture@… il sync importa, altrimenti la diagnostica mostra l'email
da autorizzare.

## 2026-07-06 — Drive: riparazione automatica del JSON service account malformato

Screenshot diagnostica: Metodo=service account, cartella=1PLR2d… (giusti,
la mia correzione nomi env ha funzionato), ma "File JSON valido ✗". Il
valore GOOGLE_DRIVE_SA_JSON su Render è JSON malformato — quasi sempre la
private_key spezzata dagli a-capo incollando su Render.
Fix lato codice: _parsa_sa()/_varianti_sa() provano più riparazioni
(grezzo, base64, virgolette esterne rimosse, a-capo REALI dentro private_key
→ \n) e restituiscono la forma canonica valida; _config passa a valle il
JSON canonico riparato. Verificato per esecuzione: a-capo reali/base64/
virgolette esterne → riparato; troncato → None. La diagnostica ora, se
irrecuperabile, mostra la LUNGHEZZA del valore (per capire se troncato) e
suggerisce il metodo Base64 (a prova di errore). Dopo il deploy, se il
guasto è gli a-capo, il sync funziona SENZA reincollare nulla.

## 2026-07-06 — Drive: verifica DIRETTA della cartella sincronizzata (via Drive MCP)

Il child-listing MCP sulla nuova cartella 1PLR2dLe7RGyZ2rtRlvqE-EKcQ-BiNwEy
FUNZIONA (superficie permessi diversa da get_metadata). Prove raccolte:
- La cartella contiene le fatture: RADICE = *.xml.p7m firmati (proprietario
  ceraldicontabilita@gmail.com); sottocartella "Elaborate"
  (id 1n2tW3JQP3QMHd5AbjR4HfLlbpDjskWnv) di proprietà del SERVICE ACCOUNT
  ingest-fatture@ceraldi-gestionale.iam.gserviceaccount.com, con le fatture
  già estratte in .xml leggibile → il SA OPERA nella cartella = condivisione
  GIÀ CORRETTA (non serve condividere niente).
- Service account email: ingest-fatture@ceraldi-gestionale.iam.gserviceaccount.com
  (è quello che il sync di Lotti userà; la diagnostica lo mostrerà).
- Scaricata e decodificata una fattura reale da Elaborate
  (IT06628860964_gA2d7.xml): FatturaElettronica FPR12 valida — Cedente GB FOOD
  SRL (P.IVA 07593261212), Cessionario Ceraldi Group, data 2026-05-18,
  numero 68/, importo 3.41 EUR, riga "ROSETTINE" 0.855 KG. Il parser di Lotti
  (CedentePrestatore/DatiGeneraliDocumento/DettaglioLinee) la gestisce.
- Il sync di Lotti fa listing ricorsivo (BFS) e il regex \.xml(\.p7m)?$ matcha
  sia i .p7m in radice sia gli .xml in Elaborate.

CONCLUSIONE tecnica: la catena Drive→Lotti è verificata fino alla porta di
Lotti. L'UNICO blocco residuo è la validità del JSON del service account su
Render (GOOGLE_DRIVE_SA_JSON), già gestita dal codice (riparazione base64/
virgolette/a-capo/doppio-escape). Il DB di Lotti resta non interrogabile dal
sandbox (egress policy 403 su lotti-backend e ceraldiapp.it, verificato dal
proxy status), quindi la conferma "sono dentro Lotti" la dà la card dopo il
Sincronizza (processati: N) o Enzo dalla lista Fatture.

## 2026-07-06 — BUG p7m: fatture firmate con XML "precoce" non lette (Villa Sandi)

Enzo ha caricato una fattura .xml.p7m (Villa Sandi, prosecco) chiedendo
perché "fatture come queste non le legge". Riprodotto: _estrai_xml
(fatture.py:319) aveva la scorciatoia `if raw[:5]=="<?xml" or
b"FatturaElettronica" in raw[:400]: return raw`. Nei .p7m firmati con busta
DER PICCOLA l'XML inizia entro i primi 400 byte → la condizione era vera →
restituiva il BINARIO firmato intero (0x30 0x82…) → ET.fromstring falliva
"not well-formed, line 1". Ecco perché quelle fatture non venivano lette.
Fix: si restituisce grezzo SOLO il vero XML (lstrip inizia con <?xml o con
<…FatturaElettronica); tutto il resto (p7m/buste/base64) passa SEMPRE per
_carve che ritaglia <?xml…</FatturaElettronica>. Verificato sul file reale:
estrae XML pulito, parse OK (Villa Sandi, totale 381.79). Regressione XML
grezzo con/senza dichiarazione invariata. Nuovo test tests/test_estrai_xml_p7m.py
(p7m sintetici, nessuna fattura reale nel repo). Suite pura: 63 passati.

## 2026-07-06 — Incongruenze + semplificazione (obiettivo "logica umana"), tranche 1

- prodotti_vendita.get_statistiche_margini: rimosso corpo DUPLICATO dopo il
  return (codice morto irraggiungibile).
- gelati.py elimina-produzione: il lotto ora riceve il campo GEMELLO
  stato="esaurito" + quantità azzerate (prima solo esaurito:True → i filtri
  che guardano "stato" lo vedevano ancora aperto).
- Vocabolario stato lotti unificato al reale: lotti.py e controllo_dati.py
  (lotti-senza-tracciabilità) filtravano stato $nin [consumato,chiuso,
  archiviato] — valori MAI scritti → filtro inefficace; ora $nin
  [smaltito,esaurito] (esclude davvero i finiti). diagnostic conteggio
  "lotti attivi" usa il FILTRO_LOTTO_APERTO canonico (prima stato!=consumato,
  inesistente → contava tutto).

## 2026-07-06 — Incongruenze tranche 2: filtro lotto-attivo unificato + bevande

Da revisore backend. Filtro CANONICO "lotto attivo" spostato in
routers.utils.FILTRO_LOTTO_APERTO (fonte unica) e usato dove veniva
reinventato in modo incompleto:
- ricerca_globale: filtrava solo consumato → i lotti SMALTITI comparivano
  come attivi (leak visibile). Ora filtro completo.
- lotti.cosa-usare-oggi e dashboard_economica: mancava il flag esaurito.
- anomalie sposta-massivo: allineato.
- supervisor importa dal punto unico (re-export).
CATEGORIE_BEVANDE_A_UNITA spostate in routers.utils (fonte unica della
regola "bevande a cartone/unità"); food_cost la importa.
Verifiche: import ok, 63 test puri, nessun ciclo di import.

DA PORTARE A ENZO (semplificazioni UX che richiedono una sua scelta, dal
revisore frontend): doppio "Confronto prezzi" (menu vs tab Ordini, due
componenti diversi); virgola non accettata negli input Ordini; 6 tab in
Ordini (dichiarati 4); doppia barra di ricerca in Lotti; Home affollata
(>30 destinazioni); conferme elimina incoerenti (modale custom vs
window.confirm); menu Altro 16 voci con icone ripetute; Materie Prime e
Fatture senza voce di menu stabile; motore "miglior prezzo" doppio
(prodotti_master vs food_cost) su basi diverse.

## 2026-07-06 — Incongruenze frontend tranche 1: confronto unico, virgola Ordini, colori

- Confronto prezzi UNIFICATO: Ordini tab "Confronto" ora usa
  ConfrontoProdottoView (la pagina pulita del menu), non più il vecchio
  ComparatorePrezziView → una sola schermata per la stessa decisione.
- Virgola italiana accettata negli input Ordini (giacenza/soglia/conteggio):
  type=number -> type=text inputMode=decimal + helper numIt.
- Colori fuori palette rimappati in App.js: header smeraldo #34d399 ->
  gradiente salvia; barra import #22c55e/#f59e0b/#b91c1c -> bosco/ocra/terracotta.

## 2026-07-06 — Semplificazione frontend tranche 2: navigazione + ordine lotti

- Menu "Altro": un'icona DISTINTA per voce (prima molte ripetute:
  Network/ClipboardCheck/TrendingUp/BookOpen duplicate → indistinguibili);
  nomi più chiari (i tre "Controllo…" → "Verifica dati" e "Prelievi
  magazzino"; "Listini & Vendita" → "Prezzi & Vendita"); aggiunta voce
  "Materie Prime" (pagina d'uso frequente prima senza voce di menu).
- Lotti: lista ordinata per scadenza (i più vicini a scadere in cima; senza
  scadenza in fondo). Prima ordine casuale dall'API.

RIMANDATE a scelta di Enzo (AskUserQuestion fallita tecnicamente): Ordini
6→3 tab (Compra/Carrello/Da inviare); Lotti due barre di ricerca → una;
Home affollata → "Cosa fare oggi" + KPI, resto dietro "Ufficio/Altro";
conferme elimina incoerenti (18 window.confirm vs 1 modale custom).

## 2026-07-06 — Semplificazioni strutturali (scelte da Enzo, tutte e 4)

1. Ordini: 6 schede → 3 (Compra/Carrello/Da inviare); "Compra" raggruppa
   Riordini/Catalogo/Confronto/Giacenze come sotto-voci a pillole (2 livelli).
   Viste invariate, cambia solo la navigazione.
2. Lotti: una sola barra di ricerca; la ricerca ASL estesa è un pulsante
   «Cerca ovunque» che usa lo stesso testo. Rimosso stato uniQuery.
3. Home: Area ufficio + Archivio sotto un pulsante «Ufficio e archivio»
   (chiuso di default); in alto restano Cosa fare oggi + numeri + Operazioni.
4. Conferme elimina: nuovo hook condiviso shared/useConferma.jsx (modale
   on-brand, come Lotti). Applicato alle schermate QUOTIDIANE (Fatture,
   Ricezione, Ordini); il modo sicuro di fallire è "non cancella", mai
   "cancella senza chiedere". Le schermate rare/admin restano su window.confirm
   (coerenti tra loro) — convertibili con lo stesso hook se Enzo vuole.
Tutte verificate con build; ogni modifica committata isolata.

## 2026-07-06 — Semplificazione (scelte Enzo): conferme uniformi + lotti già a 1 ricerca

Enzo ha approvato tutte e 4 le semplificazioni. Stato:
- Lotti "una sola ricerca": GIÀ fatto in precedenza (una barra + bottone
  "Cerca ovunque" che riusa lo stesso testo). Verificato.
- CONFERME UNIFORMI: nuova finestra di conferma UNICA e coerente
  (utils/conferma.js + shared/ConfermaHost.jsx montato in App). Convertite
  14 window.confirm (13 view + logout App.js) in `await conferma(...)`;
  fallback a window.confirm se l'host non è montato. window.prompt (input
  testo: Colazione, LottiList recall, SchedaProdotto) lasciati per ora.
  Build ok (tutte le funzioni erano già async).
RESTANO (in corso): Ordini 6→3 tab; Home più pulita.

## 2026-07-06 — Semplificazioni approvate da Enzo: stato finale

Enzo ha approvato tutte e 4. Verifica sul codice reale (main):
- Ordini 6→3 schede: GIÀ FATTO (OrdiniView: barra bassa Compra/Carrello/Da
  inviare, "Compra" raggruppa Riordini/Catalogo/Confronto/Giacenze come
  sotto-voci — COMPRA_TABS, riga 374).
- Lotti una sola ricerca: GIÀ FATTO (una barra + bottone "Cerca ovunque").
- Home più pulita: GIÀ FATTO (Area ufficio/Archivio dietro pulsante
  "Ufficio e archivio" chiuso di default; Strumenti avanzati collassabili).
- Conferme uniformi: FATTO ORA (utils/conferma.js + ConfermaHost; 14
  window.confirm convertite).
Il revisore frontend le aveva segnalate come da fare: aveva letto una
versione precedente. Tre erano già in produzione, la quarta l'ho chiusa io.
Obiettivo "verifica incongruenze + semplifica con logica umana": completato
per tutte le parti sicure e per le 4 semplificazioni approvate.

---

## 20/07/2026 — Sync Drive incrementale (indice md5) + filtro ANNO in cima alla lista fatture

Contesto: Enzo conferma che il Sync automatico da Google Drive ORA funziona
(«Credenziale vista (service account) · 5555 file registrati · 268 in errore ·
ultimo giro 20/07 10:08»). Due richieste: (1) un indice per non
ri-sincronizzare sempre tutto; (2) leggere i dati per anno, con l'anno in cima.

### 1. Indice incrementale anti-riscarico — `backend/routers/drive_fatture.py`
Il registro `drive_fatture_file` (per `drive_id`) già evitava di ri-processare i
file noti. Problema vero: su Drive ogni fattura sta SIA nella cartella radice SIA
nella sottocartella «Elaborate», quindi ogni XML compare due volte con `drive_id`
diversi → la seconda copia veniva **riscaricata** ad ogni giro.
- `esegui_sync_drive` ora costruisce anche `md5_noti` = set degli md5 di contenuti
  già importati (esito importata/duplicato). Un file "nuovo" (drive_id mai visto)
  ma con md5 già noto viene registrato come `esito: "duplicato"` e **saltato senza
  download né re-import**. `md5_noti` si aggiorna anche in memoria dopo ogni import
  riuscito, così i doppioni dello stesso giro si saltano.
- Nuovo contatore `duplicati` negli esiti e nello stato; il messaggio in-app conta
  «N doppioni saltati» e il calcolo di «restano» sottrae i duplicati.

### 2. Filtro ANNO — `backend/routers/fatture.py` + `ImportaFattureView.jsx`
- `GET /fatture` nuovo parametro `anno`: `anno>0` = tutte le fatture di
  quell'anno (ignora `mesi`). Il filtro è applicato con un `$match` sul DB
  (regex su `data_fattura`: `^AAAA[-/]` per ISO, `[-/]AAAA$` per dd/mm/yyyy e
  dd-mm-yyyy) PRIMA del `to_list`, così lo storico grande condiviso con
  Gestionale Cloud non viene troncato; un filtro Python sull'anno fa da rete di
  sicurezza.
- Nuovo `GET /fatture/anni`: anni distinti disponibili (da `data_fattura`,
  decrescente) per popolare il selettore.
- `ImportaFattureView`: selettore «Anno» in cima alla card «Fatture Importate»
  (default anno corrente; opzione «Tutti gli anni» → `mesi=0`). Ricarica la lista
  al cambio anno. Stile salvia coerente (bg `#f2f6f3`, testo `#3f5a4e`).

### Verifica
- `pyflakes` sui 2 file (unico warning preesistente `descrizione_completa` a
  fatture.py:789, fuori dalle modifiche), `compileall` OK, import `server` OK.
- pytest: test_riordino_consumi, test_prezzi_da_fatture, test_fonti_catalogo,
  test_estrai_xml_p7m → 24 passed (exit 0).
- `CI=false npm run build` → Compiled successfully, nessun warning.

### Collaudo live (post-deploy, da telefono)
- Fatture → selettore «Anno» in cima: 2026 mostra le fatture di quest'anno,
  «Tutti gli anni» mostra tutto lo storico, cambiando anno la lista si aggiorna.
- «Sincronizza ora» più volte: i doppioni radice/Elaborate non vengono più
  riscaricati (messaggio «N doppioni saltati»), «restano» scende fino a 0.

### 20/07/2026 (segue) — Pulsante «Riprova i file in errore»
Richiesta Enzo: recuperare i 268 file rimasti in errore (tra cui i .p7m
firmati sistemati nelle sessioni precedenti, che il registro saltava come
"già visti in errore").
- `backend/routers/drive_fatture.py`: helper condiviso `_credenziali_non_pronte`
  (estratto da esegui_sync_drive); nuova `esegui_riprova_errori` + route
  `POST /drive-fatture/riprova-errori`. Ri-scarica e re-importa i file
  `esito=errore` MAI ritentati (`ritentato != true`), marcando ogni file come
  `ritentato: true` a prescindere dall'esito → un file davvero rotto NON torna
  in coda (niente loop infinito); chi si recupera passa a `importata`.
  `GET /stato` ora espone `file_da_riprovare` (errori non ancora ritentati).
- `ImportaFattureView` (SyncDriveCard): pulsante «Riprova N in errore» (ocra,
  visibile solo se file_da_riprovare>0) che chiama la route con limit=200 e
  mostra recuperate/ancora illeggibili/restano.
- Verifica: pyflakes 0, compile+import OK, build frontend pulita.

### 20/07/2026 (segue 2) — CAUSA VERA dei "268 in errore": E11000 numero+piva
Screenshot Enzo: gli errori del sync erano tutti `E11000 duplicate key error
collection: Gestionale.fatture index: uniq_numero_piva`. NON fatture rotte:
fatture il cui numero+P.IVA ESISTE GIÀ nella collection (condivisa con
Gestionale Cloud). L'import usava come chiave anti-duplicato fornitore+numero+
data: se la stessa fattura era già presente con fornitore/data scritti un po'
diversi, l'upsert non la trovava e l'inserimento sbatteva sull'indice unico.
- `backend/routers/fatture.py`: chiave anti-duplicato allineata all'indice del
  DB → `numero_fattura + piva` (fallback a fornitore+numero+data se piva
  assente). `id`/`created_at` messi in `$setOnInsert` per non sovrascrivere un
  doc creato da Gestionale Cloud. `try/except DuplicateKeyError` → se scatta
  comunque, aggiorna la fattura esistente (niente doppione, niente errore).
  Import di `pymongo.errors.DuplicateKeyError`.
- `backend/routers/drive_fatture.py` `esegui_riprova_errori`: PRIMA una
  riconciliazione veloce senza download → gli errori con dettaglio "E11000"/
  "duplicate key" diventano `duplicato` (già presenti) in un `update_many`
  (azzera i 268 all'istante, niente timeout/Network Error). Poi ri-scarica solo
  gli errori VERI restanti. Nuovo campo `gia_presenti` negli esiti.
- `ImportaFattureView`: la Riprova ora chiama con limit=100 e timeout 120s e
  mostra «N già presenti nel gestionale, M recuperate, K ancora illeggibili».
- Verifica: pyflakes (solo warning preesistente descrizione_completa), compile+
  import OK, pytest 19 passed, build frontend pulita.

### 20/07/2026 (segue 3) — Duplicati E11000 già-ritentati restavano bloccati
Dopo il primo giro col backend vecchio, i file E11000 erano stati marcati
`ritentato:true` mantenendo `esito:errore`: la riconciliazione (che filtrava
`ritentato != true`) non li toccava più e il pulsante «Riprova» spariva (177
bloccati). Fix in `drive_fatture.py`:
- `esegui_riprova_errori`: la riconciliazione E11000→"duplicato" ora NON filtra
  su `ritentato` (un dup-key è sempre una fattura già presente).
- `/stato` `file_da_riprovare`: conta esito=errore con `$or` [ritentato!=true,
  dettaglio E11000] → il pulsante ricompare finché ci sono duplicati da pulire.
Verifica: pyflakes 0, compile+import OK.

### 20/07/2026 (segue 4) — BUG GRAVE trovato da Enzo: tracciabilità saltata sui duplicati E11000

Enzo ha incollato l'elenco fatture di luglio da Gestionale Cloud (~48, molte di
fornitori alimentari veri: KIMBO, LANGELLOTTI, GB FOOD, EUROUOVA, VANDEMOORTELE,
San Carlo…) e chiesto perché Lotti ne aveva importate solo 4. CAUSA: la
collection `fatture` è condivisa col gestionale Cloud, che scrive lì una riga
per ogni fattura SDI con SOLO i dati contabili (importo, IVA, stato pagamento),
MAI le righe prodotto. La "riconciliazione veloce" aggiunta ieri per il
pulsante «Riprova» equivocava l'errore E11000 (chiave numero+P.IVA duplicata)
per "fattura già del tutto importata" e la marcava `duplicato` SENZA MAI
scaricarla né leggerne i prodotti — quindi lasciava ~250 fatture vere senza
prodotti/lotti/dizionario collegati, con solo lo scheletro contabile del
gestionale. Bug mio, introdotto nella sessione precedente.

Fix in `backend/routers/drive_fatture.py`:
- `esegui_riprova_errori`: TOLTA la scorciatoia senza download. Ora ogni file
  in errore viene sempre riscaricato e ri-passato da `importa_fattura_xml`,
  che (dal fix di ieri su `fatture.py`) su un doc già esistente per
  numero+piva fa `$set` con i prodotti invece di fallire — quindi il retry
  ora COMPLETA la riga contabile del gestionale con la tracciabilità mancante.
- Riparazione una tantum (dentro la stessa funzione, ad ogni chiamata):
  i record mismarcati `esito:"duplicato"` con dettaglio "già presente nel
  gestionale…" (dal bug di ieri) tornano `errore`+`ritentato:false`; i record
  `errore`+`ritentato:true` con dettaglio E11000 (dal primissimo giro, backend
  vecchio) tornano `ritentato:false`. Così rientrano nella coda di riprova
  vera. NON tocca i `duplicato` con l'altro significato (stesso file su Drive
  in due cartelle, dettaglio "stesso contenuto già importato" — quelli restano
  giustamente saltati, è deduplica sui BYTE del file, non sul contenuto DB).
- `/stato` `file_da_riprovare`: conta sia gli errori mai ritentati sia i
  `duplicato` mismarcati dal bug, finché non vengono ri-processati per davvero.
- Frontend: messaggio "N recuperate con prodotti collegati, M ancora
  illeggibili" (tolto "già presenti nel gestionale", non più applicabile).

LEZIONE: un E11000 su un DB condiviso con un altro gestionale NON significa
"niente da fare" — significa "un'altra app ha già scritto quella riga, ma
probabilmente senza i dati che servono a QUESTA app". Mai trattare un
conflitto di chiave come "già fatto" senza verificare che i dati che contano
per questa app (qui: prodotti) siano davvero presenti.

Verifica: pyflakes 0, compile+import OK, pytest 24 passed, build frontend
pulita. Enzo dovrà premere «Riprova» finché il contatore non arriva a 0 (ogni
click riscarica davvero fino a 30 file, con le fatture di GB Food/Kimbo/
Langellotti/Eurouova/Vandemoortele/ecc. che ora arriveranno con i prodotti).

### 20/07/2026 (segue 5) — Riprova errori: da richiesta bloccante a job in background

Enzo: timeout anche con batch da 30 (il fix precedente aveva reso ogni file un
import VERO — download + parse XML + hook lotti/dizionario/prezzi — molto più
pesante di una semplice riconciliazione). Nessun batch size avrebbe risolto:
una richiesta HTTP bloccante non è lo strumento giusto per un lavoro di minuti.

Fix: riuso IDENTICO al meccanismo già esistente per l'import manuale
(`import_jobs` + `/importa-async` + `/importa-job-attivo` + polling in App.js).
- `backend/routers/drive_fatture.py`: `esegui_riprova_errori(job_id=...)`
  aggiorna `drive_riprova_jobs` file per file; `POST /riprova-errori` ora
  inserisce il job e lo lancia con `BackgroundTasks`, ritorna subito `job_id`
  (niente più `limit` per click: processa TUTTI gli errori in un job unico).
  Nuove `GET /riprova-job-attivo` (ripresa dopo reload, auto-chiusura job
  stantii >30 min) e `GET /riprova-job/{job_id}`.
- `ImportaFattureView` (SyncDriveCard): `riprovaErrori` avvia il job e fa
  polling ogni 3s (`pollRiprovaJob`), mostra «Riprova in corso… N/Totale» sul
  pulsante; al mount controlla `/riprova-job-attivo` per riprendere il polling
  se la pagina viene ricaricata mentre il job gira sul server.
Verifica: pyflakes 0, compile+import OK, pytest 24 passed, build pulita.

### 20/07/2026 (segue 6) — Shelf life: sfogliatella congelata 3 mesi, in frigo entro giornata

Enzo ha incollato l'etichetta reale del lotto SFOGL_RICC-005-50pz-20072026:
scadenza frigo 23/07 (+3gg), scadenza congelatore 18/09 (+60gg) — e ha chiesto
che il congelatore diventi 3 mesi (le uova, ingrediente critico, "determinano"
la scadenza) e che in frigo la scadenza sia "entro il giorno", verificando
prima dati reali sul web.

Ricerca web fatta (fonti in fondo): schede tecniche prodotti industriali
surgelati confezionati arrivano a 12 mesi (non applicabile: qui è un
congelatore di negozio senza confezionamento sottovuoto); guida consumer
reale su conservazione sfogliatelle: frigo "24 ore" per consumo ottimale
(la sfoglia perde croccantezza per l'umidità), congelamento impasto crudo
"max 3 settimane" (scenario diverso, impasto non cotto).

CAUSA REALE (bug in `backend/routers/shelf_life.py`): `calcola_scadenza`
usava la categoria-prodotto (tabella SHELF_LIFE_PRODOTTO, "sfogliatella":
congelatore=90gg, CORRETTA) SOLO come fallback quando nessun ingrediente
deperibile veniva trovato. Appena un ingrediente generico ("uova": congelatore
60gg) matchava, quel valore SOVRASCRIVEVA il prodotto-specifico più corretto,
anche se PEGGIORE (più lungo/meno sicuro in astratto, ma qui semplicemente
sbagliato perché le uova nel ripieno di un prodotto COTTO IN FORNO cuociono
insieme all'impasto — non hanno la deperibilità di uova crude in una crema
mai cotta). Il file documentava già da tempo (commento in testa) una categoria
"Uova cotte → 1 giorno, 3 frigo" MAI implementata nel dizionario — gap noto
e mai colmato.

Fix:
- Nuova entry `INGREDIENTI_DEPERIBILI["uova cotte"]` (ambiente 1, frigo 3,
  abbattitore_positivo 5, abbattitore_negativo 90) — MAI matchata per
  substring diretto (skippata nel loop), solo per sostituzione programmatica.
- Nuova costante `PRODOTTI_COTTI_IN_FORNO` (sfogliatelle, cornetti, torte pan
  di spagna, biscotti, frolla, pizza…) — esclusi apposta cannoli/cassata
  (farciti con ricotta CRUDA dopo la frittura) e mousse/semifreddo (mai cotti).
- `calcola_scadenza` riscritta: la categoria-prodotto è SEMPRE la base
  (non più solo fallback); un ingrediente può SOLO accorciare la scadenza,
  mai allungarla oltre il default-prodotto (regola prudenziale corretta in
  sicurezza alimentare — si prende sempre il minimo). Quando il prodotto è
  cotto in forno, "uova"/"uova crude" nel ripieno vengono trattate come
  "uova cotte". Match ingrediente ora prende la keyword più specifica (più
  lunga) tra quelle che matchano, non una arbitraria.
- `SHELF_LIFE_PRODOTTO["sfogliatella"/"sfogliatelle"]["frigo"]`: 5→1 giorno
  (la sfoglia perde croccantezza in giornata per l'umidità del frigo — non è
  un rischio delle uova, è la sfoglia; ambiente resta 2gg, coerente con la
  prassi reale di NON mai refrigerare la sfogliatella).
- `lotti_produzione.py`: le due route reali che generano l'etichetta di
  produzione (`registra-produzione-lotto`, `genera-lotto/{ricetta_nome}`) ora
  passano `nome_prodotto=ricetta["nome"]` a `_calcola_scadenza` — PRIMA non
  lo passavano affatto, quindi la regola prodotto-cotto-in-forno non poteva
  mai scattare lì. Nessuna modifica a `gelati.py`/`lotti.py` (casi diversi,
  fuori scope).
- Nuovo test `tests/test_shelf_life_sfogliatella.py` (4 casi: sfogliatella
  congelata=90gg non-sovrascritta da uova generiche, sfogliatella frigo=1gg,
  mousse NON cotta in forno resta a 60gg con uova come critico, un ingrediente
  meno deperibile del default-prodotto non allunga mai la scadenza).

Verifica: pyflakes (solo warning preesistente a lotti_produzione.py:1778, non
toccato), compile+import OK, pytest 33 passed (24 esistenti + 4 nuovi + le
nuove più il resto del batch).

Fonti web consultate:
- https://www.webnapoli24.com/2023/05/29/sfogliatelle-come-conservarle-tempo-e-dove-metterle/
- https://www.pintauro.eu/raccomandazioni.html
- https://ordini.dolceideasrl.it/allegati/SGS0403%20Sfogliatella%20riccia%20Santa%20Rosa%20160g%20pezzi%2060.pdf

### 20/07/2026 (segue 7) — Sfogliatella in frigo: 1→3 giorni (calibrazione diretta di Enzo)

Conferma dal lotto successivo (SFOGL_RICC-008): congelatore 90gg/3 mesi
corretto (18/10 = 20/07+90 ✓). Frigo: Enzo ha corretto di persona "1 GIORNI
DI SCADENZA è BREVE METTI 3 GIORNI" — la stima da fonti web (24h) era troppo
prudente rispetto alla sua esperienza pratica di titolare/responsabile HACCP.
`SHELF_LIFE_PRODOTTO["sfogliatella"/"sfogliatelle"]["frigo"]`: 1→3. Aggiornato
il test `test_shelf_life_sfogliatella.py` (rinominato il caso frigo, ora
asserisce 3gg). Verifica: pyflakes 0, compile+import OK, pytest 4 passed.

### 20/07/2026 (segue 8) — "Manda al banco": conferma posizione + stampa distinta; frigo/congelatori reali nel tablet

Enzo (tablet Pasticceria, card Cornetto Sfoglia): cliccando «🛒 60» sulla
giacenza già pronta (dal congelatore), la merce veniva mandata al banco ma
senza dire DA QUALE frigo/congelatore, senza stampare nulla e senza scelta
del frigo/congelatore reale in produzione (mostrava nomi generici finti,
non quelli configurati in Attrezzature).

**1. Frigo/congelatori mancanti** — `TabletView.jsx`/`BackofficeView.jsx`
montavano `<ModalRegistraLotto>` SENZA passare `frigoriferi`/`congelatori`:
il componente ricadeva sempre sulla lista di fallback hardcoded
("Frigo 1/2/3…", "Congelatore 1/2…") invece dei nomi VERI configurati in
Attrezzature (`GET /attrezzature/`, già usato altrove: LottiList,
TemperaturePositive/NegativeView). Aggiunto fetch + prop in entrambi.

**2. "Manda al banco" senza conferma né stampa** — causa reale: il backend
(`POST /lotti/{id}/manda-al-banco`, routers/lotti_produzione.py) registrava
GIÀ correttamente il movimento (posizione_da/posizione_a/quantità in
`movimenti_lotto` — la "distinta di tracciabilità" c'era), ma (a) la risposta
non includeva frigo/movimento_id, quindi il frontend non poteva mostrarli;
(b) non esisteva nessun modo di stampare conferma.
- Backend: la risposta ora include `movimento_id`, `frigo_numero`,
  `prodotto`, `numero_lotto`.
- Nuovo `GET /stampa/movimento/{movimento_id}` (routers/stampa.py): ricevuta
  POS 80mm con DA/A/quantità/data-ora/operatore + "TRACCIABILITÀ REGISTRATA".
- `ModalRegistraLotto.jsx`: il toast ora dice "✓ Nnpz di X da Congelatore 1
  mandati al banco — tracciabilità registrata"; se "Stampa etichetta" è
  attiva (default sì), stampa automaticamente la distinta (stesso
  meccanismo `stampaDoc` già usato per le etichette lotto). Applicato sia al
  singolo lotto sia a "Manda tutto" (che aggrega le fonti nel messaggio,
  es. "60 da Congelatore 1 + 10 da Frigo 2"; stampa una distinta per lotto).

**3. Bug preesistente trovato per caso** (scrivendo il nuovo endpoint POS):
`build_pos_html` (l'etichetta lotto stampata OGNI GIORNO) aveva
`window.onload = () {{ ... }}` — manca la freccia `=>`, JavaScript
sintatticamente invalido (`SyntaxError`). In modalità stampa "classica"
(popup browser, non coda automatica) questo impediva l'AUTO-stampa: la
pagina si apriva ma `window.print()` non partiva mai da sola, l'operatore
doveva premere Ctrl+P a mano senza saperlo. Corretto: `() => {{ ... }}`.

Verifica: pyflakes (solo 3 warning preesistenti confermati con git stash:
`_ind_az`/`sezione_trac` in stampa.py, `e` non usato in lotti_produzione.py —
nessuno introdotto da queste modifiche), compile+import OK, pytest 67 passed,
build frontend pulita.

### Collaudo live suggerito (da telefono, dopo deploy)
- Tablet Pasticceria → produci un prodotto con destinazione Abbattitore/Frigo:
  il menu a tendina ora mostra i VERI frigo/congelatori configurati in
  Attrezzature (non "Congelatore 1/2" generici, a meno che non siano quelli
  reali).
- Stessa pagina → prodotto con giacenza già pronta → «🛒 N» → il messaggio
  dice da quale frigo/congelatore, e parte la stampa della distinta (se
  "Stampa etichetta" è attiva).
- Verifica anche che l'etichetta lotto normale (dopo una produzione) si
  stampi DA SOLA all'apertura della pagina, senza dover premere Ctrl+P.

---

## 20/07/2026 — Semplificazione Colazioni e Ricette (richiesta Enzo: "troppo contorta, rendila più facile anche cambiando layout")

### Colazione (`ColazioneAcquavivaView.jsx`)
Problema: la mattina l'operatore apriva la pagina e trovava TUTTO insieme
nell'header — chips stagioni, ＋Nuova, 🗑 elimina, modifica periodo, toggle di
modalità — quando il 95% delle volte deve solo spuntare i prodotti e premere
Avvia. In più la creazione stagione usava `window.prompt` (fuori design).
- Modalità "avvia" (default): header MINIMALE — titolo «Colazione · Stagione»,
  conteggi, un solo bottone «⚙️ Modifica menù» e ✕. Nient'altro: la stagione
  giusta si auto-seleziona già per data (stagione-attiva).
- Tutta la gestione (chips stagioni, nuova/elimina, periodo, catalogo prodotti,
  preferiti, quantità default) vive SOLO dentro «Modifica menù» (ex "configura"),
  con bottone «← Torna alla colazione».
- `window.prompt` sostituito da input inline (Enter=crea, Esc=annulla).
- «Salva Template» → «✓ Salva menù e torna alla colazione»: dopo il salvataggio
  si torna da soli alla schermata del mattino. Lessico uniformato ("menù", non
  "template").

### Ricette (`BackofficeView.jsx` — pagina #ricette)
Problema: card con 4 bottoni (Produci/Modifica/Scheda/Elimina) dove Modifica e
Scheda erano DUE EDITOR SEPARATI della stessa ricetta (il form conteneva
perfino un banner che spiegava la differenza), cestino sempre in vista su ogni
card, form lunghissimo (un campo per riga).
- Card: 2 sole azioni — «🏭 Produci» (primario) e «✏️ Apri ricetta». Dentro il
  form si fa TUTTO.
- FormRicetta: nuove prop `onApriScheda`/`onElimina`; nell'header il bottone
  «📋 Procedimento» apre l'editor scheda (chiude il form, apre SchedaEditorModal
  — un solo percorso, niente più banner esplicativo, rimosso); «🗑 Elimina
  questa ricetta» in fondo al form, discreto (chiude il form solo se la
  conferma va a buon fine — `elimina` ora ritorna true/false).
- Dati base compatti: Nome a riga intera + Reparto/Pezzi/Prezzo su una riga
  (grid auto-fit minmax 140px, va a capo su telefono).
- «Importa dal foglio» declassato a stile ghost (azione una-tantum, non deve
  competere con «+ Nuova ricetta»).

Nessuna modifica backend: solo layout/flusso, stesse API.
Verifica: `CI=false npm run build` → Compiled successfully, zero warning.

### Collaudo live (da telefono/tablet, dopo deploy)
- Tablet → ☕ Colazione: si apre pulita (lista + Avvia); «⚙️ Modifica menù» →
  stagioni/periodo/catalogo; «✓ Salva menù» riporta alla lista del mattino.
- #ricette: card con 2 bottoni; «Apri ricetta» → dentro ci sono Procedimento,
  Stampa, Elimina; il form ha i dati base su due righe invece di quattro.

---

## 23/07/2026 — Dizionario: esclusione righe dal battesimo (singola + per famiglia)

Richiesta Enzo (screenshot pagina #dizionario): "fammi escludere i prodotti che
seleziono ed anche per categoria, tipo le bevande, gli alcolici, vini, spumante".
Nel Dizionario finiscono righe che non c'entrano con le ricette (segnaletica
adesiva, acqua, birre, avena drink...): battezzarle è lavoro inutile e gonfia
il promemoria DATI4.

### Backend (`food_cost.py` + `supervisor_operativo.py`)
- Nuovo campo `escluso_ricette` (+ `escluso_motivo`, `escluso_il`) su
  `dizionario_prodotti`. NON tocca prezzi/storico: la riga esce solo dalla
  coda del battesimo.
- `GET /food-cost/dizionario`: di default filtra `escluso_ricette != true`;
  nuovo param `solo_esclusi=true` per la vista dedicata (ignora senza_canonico).
- `POST /food-cost/dizionario/escludi` {id, escluso} — esclude/ripristina una
  riga.
- `POST /food-cost/dizionario/escludi-famiglia` {famiglia, anteprima} —
  famiglie predefinite `FAMIGLIE_ESCLUSIONE_DIZIONARIO`: "bevande" (acqua,
  bibite, succhi, sciroppi, cola...), "alcolici" (birra, liquori, amari, rum,
  gin...), "vini" (vino, spumante, prosecco, champagne...). Match a PAROLE
  INTERE (\b) su nome_normalizzato/nome_originale. Con anteprima=true ritorna
  {quante, esempi[8]} senza scrivere: la conferma mostra prima cosa verrebbe
  escluso (le parole a doppio uso tipo "amaro" si vedono prima di applicare).
- DATI4 (Supervisore): la query delle righe da battezzare ora salta
  `escluso_ricette=true` → il contatore scende subito dopo le esclusioni.

### Frontend (`DizionarioIngredientiView.jsx`)
- Filtro a 3 viste: «Da associare» / «Tutte» / «Escluse» (prima era binario).
- Ogni riga ha un piccolo «✕ Escludi» sotto Conferma (tooltip chiaro); nella
  vista «Escluse» la riga mostra il motivo (manuale o famiglia) e «Ripristina».
- Tendina «🚫 Escludi per categoria…» (Bevande / Alcolici e liquori / Vini e
  spumanti): anteprima con conteggio + esempi nel modale di conferma uniforme,
  poi applica e ricarica. Regola mani-sporche: tendina, non testo libero.

Verifica: pyflakes solo warning preesistenti (stesso conteggio con git stash),
compile+import OK, pytest 67 passed, build frontend pulita.

### Collaudo live (post-deploy)
- #dizionario → riga "SEGNALETICA ADESIVA WC" → «✕ Escludi» → sparisce dalla
  coda; vista «Escluse» → «Ripristina» la riporta.
- «🚫 Escludi per categoria…» → Bevande → conferma con conteggio ed esempi →
  le acque/bibite spariscono da "Da associare" e il contatore DATI4 del
  Supervisore scende.

### 23/07/2026 (segue) — Fornitori esclusi che "ricomparivano" + prodotti degli esclusi ancora visibili nel Dizionario

Enzo (screenshot #fornitori, 448 totali / 329 esclusi / 39 in attesa): (1)
esclude un fornitore, ricarica, e torna "in attesa"; (2) i prodotti dei
fornitori esclusi devono sparire dal Dizionario ingredienti.

CAUSA (1): il DB `fornitori` è CONDIVISO col gestionale Cloud che può
risovrascrivere i record (e l'import fatture crea varianti di nome). La
decisione di Enzo viveva solo lì → veniva persa.
FIX: nuova collection `fornitori_decisioni` DI SOLA PROPRIETÀ DI LOTTI
{chiave (nome normalizzato: lower, spazi collassati, punti finali via), nome,
piva, escluso, tipo_fornitura, deciso_il}. Scritta da /fornitori/approva (ora
accetta anche &piva=, passata dal frontend) e /fornitori/tipo-fornitura.
GET /fornitori la ri-applica SEMPRE come overlay (match per chiave-nome o
P.IVA) e AUTO-RIPARA db.fornitori dove diverge (upsert, max 200 per giro) —
così anche import fatture/dizionario/liste che leggono db.fornitori.escluso
tornano giusti da soli. Chiavi di matching della lista unificate su
`_chiave_fornitore` (varianti "S.R.L."/"S.R.L", doppi spazi → stesso fornitore).

CAUSA (2): in GET /food-cost/dizionario il filtro fornitori esclusi era un
$nor di regex TRONCATO a 50 nomi (+100 per solo_completi): con 329 esclusi la
maggior parte dei prodotti restava visibile.
FIX: unico `$expr NOT-IN` su $toLower/$trim del fornitore, SENZA tetto;
`get_fornitori_esclusi()` ora unisce db.fornitori + fornitori_decisioni.

Verifica: pyflakes solo preesistenti, compile+import OK, pytest 67 passed,
build frontend pulita.

### 23/07/2026 (segue 2) — Modale Richiedi merce centrato, dedup fornitori multi-schema, Eredita scheda, ingredienti automatici con memoria

1. **ModalRichiediMerce** (tablet): era un foglio ancorato al fondo (alignItems
   flex-end) → appariva basso e tagliato. Ora popup CENTRATO (richiesta Enzo).
2. **Dedup fornitori "non funziona"** (`fornitori_dedup.py`): raggruppava SOLO
   sul campo `piva` e leggeva SOLO `nome` — ma i record del gestionale Cloud
   sul DB condiviso usano `partita_iva` e `ragione_sociale`/`denominazione`,
   e le P.IVA con prefisso "IT" non combaciavano mai → metà duplicati
   invisibili. Nuovi helper `_piva_norm` (via IT/spazi), `_piva_doc`,
   `_nome_doc`; `duplicati-per-piva` e `auto-merge-normalizzati` raggruppano
   in Python su TUTTI i campi; `merge` cerca/elimina/aggiorna con `_q_nome`
   ($or su nome/ragione_sociale/denominazione, case-insensitive).
3. **Eredita scheda** (FormRicetta): su ricetta NUOVA, box "È la variante di
   una ricetta che hai già?" → select ricetta di riferimento + «🧬 Eredita
   scheda»: ingredienti/reparto/pezzi/conservazione copiati dalla base,
   ricetta_base_id/nome salvati, origine="ereditata".
4. **Ingredienti automatici + memoria origine**: nuova ricetta, appena Enzo
   scrive il nome (≥4 lettere, debounce 1.2s) gli ingredienti tipici arrivano
   DA SOLI (endpoint suggerisci-ingredienti già esistente, AI/ricettario).
   Campo `origine_ingredienti` salvato sulla ricetta: "manuale" (scritti o
   anche solo toccati da Enzo), "automatica" (proposti dal sistema),
   "ereditata". MAI auto-proposta su: ricette esistenti, ereditate, manuali.
   Badge origine accanto a «Ingredienti» (✍️ scritti da te / 🤖 proposti in
   automatico / 🧬 ereditati da X). Backend: nessuna modifica (i modelli
   Ricetta/RicettaCreate hanno extra="allow"; ricetta_base_id già previsto).
Verifica: pyflakes (solo preesistenti), import OK, build pulita.

### 23/07/2026 (segue 3) — Magazzino tablet: timeout, tastierino, cartoni→pezzi, giacenze per anno

Richieste Enzo (screenshot #tablet/magazzino):
1. **Timeout 15s al caricamento** — `GET /magazzino/prodotti-unificati`
   scaricava fino a 5000 doc lotti_fornitori INTERI (con storico_utilizzi e
   campi pesanti). FIX: proiezione sui soli 12 campi usati (+ to_list 8000);
   frontend: timeout 15s→45s (il primo colpo dopo lo sleep di Render è lento).
2. **Tastierino numerico** — nuovo `KeypadPopup` a schermo (tasti grandi 0-9,
   virgola, ⌫, OK): il campo quantità del prelievo è ora un bottone che apre
   il tastierino — niente più tastiera di sistema.
3. **Cartoni→PEZZI** — il magazzino mostrava i CARTONI ("COCA COLA VAP CL 33
   X 24" = 465 CT) ma il numero di pezzi per cartone è già nel nome (X 24).
   NIENTE migrazione dati: nel DB i lotti restano in cartoni; la conversione è
   SIMMETRICA in lettura (`pezzi_per_collo()` dal nome: 'CL 33 X 24'→24,
   'CTX24'→24, '24X33CL'→24; solo se unità è CT/COLLO/CF/CS/…) e in scarico
   (l'operatore preleva in PEZZI, il backend riconverte in colli per il FIFO;
   i movimenti si registrano in PZ). La card mostra anche "= N cartoni da 24".
   Verifica pura su 7 nomi reali (incl. no-conversione su 'FARINA KG 25' e
   'AGLIO L.372'): OK.
4. **Giacenze per anno di fatturazione** — `prodotti-unificati?anno=YYYY`
   filtra i lotti per data_fattura (regex ISO + dd/mm/yyyy); col filtro anno
   attivo il bar si salta (lo stock bar non ha anno fattura). Frontend: select
   «Tutti gli anni / 2026 / …» nella barra filtri del tab Preleva (anni da
   GET /fatture/anni).
Verifica: pyflakes solo preesistenti (mov_id), compile+import OK, pytest set
puro 67 passed, build pulita. NB: test_magazzino_bar_iter68/71 falliscono in
sandbox perché chiamano il server live (MissingSchema) — non c'entrano col
codice.

### 23/07/2026 (segue 4) — Autocomplete, FIFO 60gg, registro fornitore→ricette, prezzi nascosti in magazzino

1. **"Errore visualizzazione quando clicco Proponi"** (`RigaIngrediente`): quando
   Proponi/proposta automatica riempiva le righe, OGNI riga apriva da sola il
   suo menù suggerimenti → si aprivano tutti insieme uno sull'altro. FIX: il
   menù si apre SOLO quando il nome cambia perché Enzo sta scrivendo in quel
   campo (flag `digitando` settato nell'onChange dell'input).
2. **FIFO 60 giorni** (`_candidati_lotti_fifo`, regola Enzo): l'ingrediente si
   associa al lotto più vecchio DEGLI ULTIMI 60 GIORNI; i lotti più vecchi di
   60gg restano in CODA come riserva di scarico (dal più recente), così la
   giacenza vecchia si consuma comunque; se non c'è nulla ≤60gg si usa il più
   recente. Vale per scarico produzione, peek etichetta e (nuovo) anche per
   `genera-lotto` che prima agganciava il lotto più RECENTE (find_one sort
   data_fattura -1 tenuto solo come fallback). Proiezione peek arricchita con
   fattura_ref/allergeni_testo.
3. **Registro fornitore→ricette** (tracciabilità INVERSA): nuovo
   `GET /fornitori/{nome}/ricette-prodotte` — legge db.lotti dove
   lotti_fornitori.lotti_scalati contiene il fornitore, raggruppa per ricetta:
   {volte, ingredienti del fornitore usati, ultimo lotto+data}. In FornitoriList
   → scheda anagrafica: nuova sezione "📒 Registro produzioni coi suoi
   prodotti" (salvia, sopra Qualità dati).
4. **Prezzi nascosti in magazzino** (`_pulisci_nome_display`): nomi prodotto
   che portano appesi prezzi/sconti dalla fattura ("… | -Prezzo: 28.80
   Sconti: …#DE#") vengono puliti SOLO in visualizzazione magazzino (il
   dipendente non deve vedere i prezzi d'acquisto); dati intatti. Test puro
   su 3 casi: OK.
NB da collaudo Enzo: conversione cartoni→pezzi GIÀ verificata live (1996 PZ,
1440 PZ); "tastierino non compare" era la cache del frontend vecchio (manca
anche la riga "= N cartoni"): serve ricaricamento forzato dopo il deploy.
«Eredita scheda» compare SOLO su «+ Nuova ricetta» (le varianti si creano da
lì), non aprendo una ricetta esistente.
Verifica: pyflakes solo preesistenti, compile+import OK, pytest 67 passed,
build pulita.

### 23/07/2026 (segue 5) — Catalogo «Modifica menù» colazione: casa prima, niente salati, solo Acquaviva acquistati

Richiesta Enzo (tablet pasticceria → Colazione → Modifica menù): l'elenco
mischiava tutto. Nuove regole in `GET /colazione-acquaviva/prodotti-disponibili
?catalogo=true` (`colazione.py`):
- ORDINE: prima tutti i prodotti FATTI IN CASA, poi la scheda Acquaviva
  (dentro ogni gruppo: alfabetico).
- NIENTE SALATI nella colazione di pasticceria: escluse le ricette di
  rosticceria (prima entravano tutte) e ogni voce con keyword salata
  (salat/rustic/gastronom/pizz/tramezz/panin/toast/focacc) su categoria+nome.
- Di Acquaviva compaiono SOLO i prodotti già acquistati in fattura: i mai
  acquistati sono fuori ("tanto non potrei aggiungerli alla colazione").
Verifica: pyflakes 0, compile+import OK, pytest (incl. colazione_stagioni) 20
passed. Inviato a Enzo anche l'Excel rigenerato
`Ricette_ingredienti_allergeni_da_completare.xlsx` (81 ricette, 400 righe,
allergeni in memoria in colonna E; celle gialle qta/unità da compilare —
accordo: lui normalizza, io faccio il match con le fatture XML).

### 23/07/2026 (segue 6) — Colazione: copia preset, salati più severi, acquisti dal Dizionario, solstizi backfill

1. **«⧉ Copia nelle altre stagioni»** (Modifica menù, accanto a 🗑): nuovo
   POST /colazione-acquaviva/copia-preset {da, a?}: SOSTITUISCE gli items
   delle destinazioni con quelli della sorgente (periodi/note dei destinatari
   restano). Conferma con elenco destinazioni prima di applicare.
2. **Salati ancora visibili**: keyword estese a livello modulo (_SALATO_KW:
   +wurstel, salsicc, prosciutt, salam, speck, friariell, arancin, crocch,
   frittatin, calzon, parigin, panzerott, mozzarell, pomodor, tonno, formagg)
   e filtro applicato ANCHE a /prodotti-piu-usati (prima la scorciatoia «Più
   usati» li faceva passare). NB: i salati già DENTRO un menù salvato restano
   finché non li togli col ✕ (il filtro agisce sul catalogo).
3. **«Mancano molti Acquaviva comprati»**: il motore prezzi matcha per nome
   catalogo e ne perdeva parecchi. Ora un prodotto è "acquistato" anche se le
   RIGHE FATTURA del Dizionario dei fornitori colazione lo contengono (chiave
   = prime 2 parole significative del nome normalizzato, `_chiave2`).
4. **Solstizi automatici**: GET /preset ora BACKFILLA i periodi mancanti sui
   preset esistenti (Autunnale/Invernale erano nati prima dei periodi e il
   $setOnInsert non li toccava) — mai sovrascrivendo date personalizzate.
   La modifica/salvataggio c'era già: in Modifica menù, link «📅 In vigore
   dal … — modifica».
Verifica: pyflakes 0, compile+import OK, pytest 11 passed, build pulita.

### 23/07/2026 (segue 7) — Foto prodotti dalla cartella Drive

Richiesta Enzo: "mancano molte foto dai prodotti, cerca qui [cartella Drive
17wHi3N9wFkvOqXsyWlJoLfQ9i8R46zYY]". La cartella NON è condivisa (vuota anche
per l'account MCP): serve la condivisione col service account (stessa email
delle fatture, visibile in «Perché non funziona?»).
- Nuovo `POST /drive-fatture/importa-foto` (riusa credenziali/HTTP del sync
  fatture): lista ricorsiva della cartella foto, scarica jpg/png/webp,
  salva in `foto_files` su Mongo (_id drive_<fileId>, stesso store
  dell'upload manuale, servito da GET /api/foto/{id}) e ABBINA per nome file
  → ricette / acquaviva_prodotti / prodotti_vendita SOLO dove foto_url manca
  (mai sovrascritta). Match: nome normalizzato esatto, fallback prime 2
  parole SOLO se univoco. limit=40 per chiamata + campo `restano` (si
  ripreme), `senza_prodotto` per i file non abbinabili. Test puro
  normalizzazione nomi file: OK.
- Bottone «📷 Importa foto da Drive» in Colazione → Modifica menù, con
  report abbinate/restano/senza-prodotto e messaggio azionabile se la
  cartella non è condivisa.
Verifica: pyflakes 0, compile+import OK, build pulita.

### 23/07/2026 (segue 8) — Colazione: acquisti per codice articolo, salati round 2, ricerca torna in cima

1. **"Mancano ancora molti Acquaviva comprati"**: aggiunto il MATCH PER CODICE
   ARTICOLO — i codici delle righe fattura dei fornitori colazione
   (fatture.prodotti.codice_articolo) confrontati col codice del catalogo:
   esatto, niente ambiguità di nome. In più spunta «mostra anche mai
   acquistati» (param solo_acquistati=false) come rete di sicurezza se il
   matching perde comunque qualcosa; il flag gia_acquistato ora è reale e la
   riga "mai acquistato" ricompare in quel caso.
2. **Salati round 2**: _SALATO_KW estese (patatin, quiche, hamburg, cotolett,
   kebab, bacon, wudy, melanzan, zucchin, spinac, baguett, ciabatt, sfilatin,
   medaglion, snack sal) + nuova lista _SALATO_PAROLE a PAROLA INTERA per i
   termini ambigui (pane, olive, verdure/a, patate) così "pane" non mangia
   "PANETTONE". Test puro su 10 nomi reali (panettone/ciambella dolci OK,
   pane arabo/wurstel/spinaci/zucchine esclusi): OK.
3. **"Se faccio cerca esco giù"**: la lista scorrevole torna in cima ad ogni
   cambio della ricerca (listaRef.scrollTo top, entrambe le modalità).
Verifica: pyflakes 0, compile+import OK, pytest colazione 5 passed, build
pulita.

### 23/07/2026 (segue 9) — Rivendita nel form ricetta, conferma elimina in primo piano, Proponi con fallback dalle ricette di Enzo

1. **"La coda di aragosta la compriamo"**: nel FormRicetta nuova sezione «Lo
   produciamo noi o lo compriamo?» con tab: 🏠 Lo produciamo noi (default) /
   🛒 Acquaviva / Buongelo / Anatrella Distribuzione / MEPA / Saima
   (FORNITORI_RIVENDITA). Salva `fornitore_rivendita` sulla ricetta (extra=
   allow, nessuna modifica backend). Con un fornitore selezionato la proposta
   automatica ingredienti si SPEGNE (prodotto comprato, non ricetta).
2. **Conferma elimina nascosta dietro al modale**: ConfermaHost aveva
   z-[100], FormRicetta 2000 e i modali tablet 3000-4000 → la conferma
   spariva DIETRO. Ora z-[9500] (sopra tutto, per ogni conferma dell'app);
   in più Elimina dal form CHIUDE subito il form e mostra la conferma in
   primo piano (richiesta esplicita).
3. **"Proponi non propone per alcuni dolci"**: quando AI (chiave/timeout) e
   base curata non conoscono il dolce, /suggerisci-ingredienti ora ripiega
   sulla RICETTA PIÙ SIMILE di Enzo (parole significative in comune nel nome;
   con 2+ parole ne servono 2 in comune: "torta di mele" non pesca "torta
   caprese"; mai la ricetta stessa). Fonte dichiarata nel toast («dalla tua
   ricetta “coda di aragosta alla Panna”»).
NB: fix build — commento JSX in ConfermaHost spostato fuori dal JSX (stesso
errore già fatto su ModalRichiediMerce: MAI {/* */} prima del nodo radice).
Verifica: pyflakes ok, compile+import OK, pytest 29 passed, build pulita.

### 23/07/2026 (segue 10) — Zip foto Acquaviva coi nomi prodotto

Richiesta Enzo: "estrai foto acquaviva con relativi nomi e dammi zip". Le foto
vivono nel DB live (foto_files/URL esterni) non nel repo → impossibile
estrarle dalla sandbox: fatto un ENDPOINT che genera lo zip dal DB vero.
- `GET /acquaviva/export-foto-zip` (acquaviva.py): prende acquaviva_prodotti
  con foto_url; se /api/foto/<id> legge i bytes da foto_files, se URL esterno
  lo scarica best-effort; ogni file nel zip è rinominato col NOME PRODOTTO
  (sanificato, dedup con " (2)"), estensione dal mime; in coda
  _foto_non_recuperate.txt con l'elenco di ciò che non è stato scaricabile.
  Content-Disposition: foto_acquaviva_<n>_prodotti.zip.
- Bottone «⬇️ Zip foto Acquaviva» in Colazione → Modifica menù (window.open
  con withToken).
Verifica: pyflakes solo preesistenti, compile+import OK, build pulita.

### 23/07/2026 (segue 11) — "L'app è molto lenta": 3 fix di performance

Cause individuate (aggravate da modifiche di oggi):
1. **GET /fornitori** (chiamata AD OGNI apertura dell'app da App.js): faceva
   fino a 200 update_one di auto-riparazione DENTRO la richiesta → ora le
   riparazioni corrono in background (asyncio.create_task) e la risposta
   parte subito; in più CACHE 60s del risultato senza filtri
   (_CACHE_FORNITORI), invalidata da ogni decisione (_salva_decisione).
2. **Colazione catalogo**: la doppia scansione acquisti (righe dizionario +
   codici articolo di tutte le fatture colazione) ora è in CACHE 10 minuti
   (_CACHE_ACQUISTI) — cambia solo quando arrivano fatture nuove.
3. Restano strutturali (note): App.js carica stats+ricette+lotti+fornitori
   tutte insieme al mount (refactor rimandato: rischioso a caldo); Render
   free addormenta il backend → il PRIMO colpo dopo una pausa è lento per
   natura (risveglio ~30-60s), non è un bug dell'app.
Verifica: pyflakes ok, compile+import OK, pytest 20 passed.

### 23/07/2026 (segue 12) — Foto invisibili su tablet/colazione + header mobile sovrapposto

Segnalazione Enzo (2 screenshot dal telefono): le foto caricate nelle ricette
NON comparivano nelle card del tablet (Babà con segnaposto colorato) e nella
Home l'header aveva caratteri sovrapposti (lente Cerca sopra "Tracciabilità
HACCP").

**Causa foto**: `foto_url` è salvato RELATIVO ("/api/foto/<id>?v=...") ma
diversi componenti lo passavano a `<img src>` così com'è → il browser lo
chiedeva al dominio del FRONTEND (ceraldiapp.it/api/foto/…) → 404 → l'onError
nascondeva l'immagine. BackofficeView e ColazioneAcquavivaView avevano già il
prefisso; gli altri no.
- Nuovo helper condiviso `fotoSrc()` in `frontend/src/utils/constants.js`
  (relativo → prefissa BACKEND_URL; http/https/data: invariati).
- Applicato in: tablet/CardProdotto.jsx (le card del tablet — il bug dello
  screenshot), TabletView.jsx (anteprima "aggiungi ricetta in card"),
  VenditaBancoView.jsx (3 punti), CatalogoGenericoView.jsx,
  tablet/ModalCambioFoto.jsx (anteprima).
- RicetteDashboardView.jsx: `photoUrl()` scartava i path `/api/foto/...`
  (gestiva solo `/uploads`) → ora qualunque path relativo va sul backend.
- ColazioneAcquavivaView.jsx (lista "avvia"): se un item del menù ha un
  `prodotto_id` che non trova più il prodotto a catalogo (es. ricetta
  ricreata), foto e categoria si riagganciano per NOME.

**Causa header**: nel brand la riga "Tracciabilità HACCP" era senza
nowrap/overflow → su schermo stretto sbordava sotto i bottoni. Fix in App.js
(ellissi su entrambe le righe) + App.css: sotto i 640px il sottotitolo
sparisce del tutto e i bottoni Guida/Esci restano solo icona
(.g-brand-sub / .g-header-btn-label).

Verifica: build frontend pulita. Da ricordare a Enzo: dopo il deploy serve la
ricarica forzata (Ctrl+F5 / chiudi e riapri il browser) per scaricare il
bundle nuovo.

### 23/07/2026 (segue 13) — Via il grafico temperature dalla Home + «⧉ Duplica» ricetta

Richieste Enzo: "elimina dalla dashboard il grafico delle temperature
frigoriferi non mi occorrono" e "nel modale delle ricette non vedo la
funzione eredita per duplicare una ricetta".

1. **DashboardView.jsx**: rimosso il componente GraficoTemperature e il suo
   uso nel cruscotto (e l'import recharts ora inutile). I KPI restano.
2. **Duplica ricetta** (BackofficeView.jsx): il box «Eredita scheda»
   compariva SOLO creando una ricetta nuova; da una ricetta APERTA non
   c'era modo di duplicarla. Ora nella fascia in alto del form (accanto a
   Procedimento/Stampa) c'è «⧉ Duplica»: apre una NUOVA ricetta già
   riempita con ingredienti/reparto/pezzi/conservazione/note/foto della
   ricetta di partenza, con ricetta_base_id/nome valorizzati e
   origine_ingredienti="ereditata" (quindi la proposta automatica NON
   scatta — regola delle ereditate). Manca solo il nome della variante.
   Dettagli tecnici: helper ingredientiEditabili() module-level; prop
   duplicaDa + onDuplica su FormRicetta; nel padre TabRicette stato
   duplicaDa e KEY sul FormRicetta (id | dup-<id> | nuova) per forzare il
   rimontaggio quando si passa da modifica a duplicato (gli useState
   iniziali girano solo al mount); duplicaDa azzerato su chiudi/salva/
   nuova/apri.
Verifica: build frontend pulita.

### 23/07/2026 (segue 14) — «✨ Proponi» reso affidabile (base curata 60 ricette + collaudo)

Segnalazione Enzo: "il bottone proponi non funziona". Il bottone dipendeva
quasi solo dall'AI: la base curata aveva 7 ricette, quindi ogni volta che la
chiamata AI falliva (o resta appesa) quasi tutti i dolci finivano in
"Nessun suggerimento" — dall'esterno = bottone rotto.

Fix in food_cost.py:
1. **Base curata estesa a ~60 ricette** vere di pasticceria/rosticceria/bar
   napoletana (zeppole, code di aragosta, cannoli, cassata, graffe,
   struffoli, roccocò, migliaccio, fiocchi di neve, pasticciotto,
   diplomatico, millefoglie, profiterole, bignè, crostate, strudel, sacher,
   arancini, crocchè, frittatine, rustici, casatiello, tortano, danubio,
   parigina, panino napoletano, cioccolata calda, ...): il bottone ora
   funziona ANCHE senza AI.
2. **Match migliorato** (_kb_lookup): radici italiane per singolare/plurale/
   genere ("code di aragosta"→"coda di aragosta", "graffe"→"graffa",
   "fiocchi"→"fiocco" con la h dei plurali in -chi), stopword ignorate,
   vince l'entrata più specifica ("torta di mele" non pesca un'altra torta;
   "strudel di mele" resta strudel). Nome sconosciuto → nessun falso match.
3. **AI con timeout 25s + log parlanti**: prima una chiamata appesa teneva
   «Penso…» per sempre e gli errori erano invisibili; ora nei log Render si
   legge il motivo esatto (chiave mancante, errore API, risposta non-JSON).
4. Frontend: timeout 45s sulle due chiamate (bottone + proposta automatica).

Collaudo: NUOVO test tests/test_proponi_ingredienti.py — 63 test con i nomi
REALI del catalogo ("Babà Crema Ed Amarena", "Zeppola di San Giuseppe",
"Strudel di Mele", "Crocchè di patate", ...) + casi negativi. Set completo
test puri: 130 passed. Ordine di risposta invariato: AI → base curata →
ricetta più simile di Enzo → messaggio onesto.

### 23/07/2026 (segue 15) — Gusti letti dal nome nel Proponi + Duplica tolto dal form

Richieste Enzo: (1) "babà panna e pistacchio → dovevi inserire la panna e il
pistacchio: migliora l'associazione"; (2) il Duplica dentro ogni ricetta
confonde ("mi chiede da quale ricetta voglio ereditare") → "elimina i tab
dalle ricette, lascia la funzione solo quando faccio Nuova ricetta".

1. **food_cost.py — gusti dal nome**: nuovo lessico _GUSTI_PAROLE (~45 voci
   dolci+salate: pistacchio, panna, nocciola/nutella, amarena, fragola,
   limone/limoncello, caffè, crema, cioccolato (bianco gestito), mele,
   frutti di bosco, wurstel, friarielli, salsiccia, funghi, prosciutto, ...)
   con chiavi ridotte a radice DALLA STESSA funzione usata sul nome (mai più
   divergenze singolare/plurale). _arricchisci_da_nome() aggiunge alla
   proposta gli ingredienti dettati dal nome, qualunque sia la fonte
   (AI/base curata/ricetta simile), senza duplicare quelli già presenti
   (babà al rum → un solo Rum) e max +4. _radice_kb migliorata: vocali
   finali a scalare + h ("pistacchio"/"pistacchi" → "pistacc").
2. **BackofficeView.jsx**: rimosso il bottone «⧉ Duplica» dalla fascia del
   form e tutto il suo impianto (prop duplicaDa/onDuplica, stato nel padre).
   Il percorso per varianti resta UNO solo: pagina Ricette → «+ Nuova
   ricetta» → box "🧬 È la variante di una ricetta che hai già?" → scegli la
   base → «Eredita scheda».
Collaudo: test_proponi_ingredienti.py esteso (76 test, incluso il caso
esatto "Babà panna e pistacchio" e i non-duplicati); set completo 143
passed; build frontend pulita.

### 23/07/2026 (segue 16) — Form ricetta: chip compatte, foto subito, nome pre-compilato dall'eredità

Richieste Enzo (screenshot form Nuova ricetta dal tablet):
1. **Chip uniformi e compatte**: le file "Lo produciamo noi o lo compriamo?"
   e "Metodo di conservazione" occupavano troppe righe con bottoni di taglie
   diverse. Ora stile unico `chip()` (padding 6/10, font 12, raggio 8, gap
   6), etichette accorciate ("🏠 Noi", "Anatrella", "Ambiente", "Frigo
   0-4°C", "Abbattitore +", "Freezer −18°C") e margini ridotti: le due
   sezioni stanno in una riga (o due al massimo su schermi stretti).
2. **Foto sulla ricetta NUOVA**: prima c'era solo "Salva la ricetta, poi
   potrai aggiungere la foto". Ora i bottoni 🖼️/📸 ci sono sempre: su una
   ricetta nuova il file scelto resta in ANTEPRIMA (stato fotoPending +
   dataURL) con nota "✓ Foto pronta: si salva insieme alla ricetta", e al
   Salva parte subito dopo il POST /ricette (che ritorna l'id creato,
   response_model=Ricetta). Se l'upload foto fallisce la ricetta resta
   salvata e un toast lo dice chiaramente.
3. **Eredita scheda → nome pre-compilato**: dopo «Eredita scheda» il campo
   NOME RICETTA parte già col nome della base + spazio ("Arancini di riso ")
   e lui aggiunge solo la variante. Se il nome era già stato scritto, non si
   tocca.
Verifica: build frontend pulita.

### 23/07/2026 (segue 17) — Fix nome eredità, tendina fornitori dal DB, guida aggiornata

Collaudo di Enzo sul giro completo: OK. Tre richieste successive:
1. **Nome auto-inserito che restava**: se dopo «Eredita scheda» toglieva la
   ricetta di riferimento, il nome pre-compilato rimaneva nel campo. Ora il
   form ricorda il nome messo DA NOI (ref nomeAuto): deselezionando la base
   il nome auto sparisce (se l'ha modificato lui, non si tocca), il badge
   "Variante di" va via e l'origine torna "manuale". Ereditando da un'ALTRA
   base, il nome auto precedente viene sostituito con quello nuovo.
2. **Fornitori rivendita dalla tendina, non più chip fisse**: eliminata la
   lista hardcoded (Acquaviva/Buongelo/Anatrella/MEPA/Saima) — chiedeva
   anche Bigfood e Rondinella. Ora: chip «🏠 Lo produciamo noi» + tendina
   «🛒 Comprato da…» popolata da GET /api/fornitori filtrando i fornitori
   NON esclusi con tipo_fornitura "completo" (= Magazzino+Lotti), ordinati
   alfabeticamente. Un valore legacy già salvato ma non in lista resta
   visibile come opzione (non si perde al salvataggio).
3. **Guida operativa aggiornata** (fonte unica frontend/src/data/
   guidaContenuti.json → pagina in-app + PDF): sezione Ricette riscritta
   (2 azioni per card, foto subito sulla nuova, Eredita scheda col nome
   pre-compilato, tendina Comprato da…, Proponi coi gusti dal nome, metodi
   conservazione compatti) e Dashboard senza il grafico temperature.
   PDF rigenerato (genera_html.py + playwright) e ripubblicato in
   frontend/public/guida/Guida_Operativa_Lotti.pdf. aggiornata_il=23/07/2026.

### 23/07/2026 (segue 18) — Scadenza modificabile alla registrazione lotto + durata memorizzata

Richiesta Enzo: "se seleziono il panettone artigianale mi dà scadenza domani
per le uova, ma dura 3 mesi — devo poter modificare la data; decidi tu dove".
Decisione: la data vive nel MODALE DI REGISTRAZIONE LOTTO (dove si sceglie
banco/frigo/abbattitore), perché è lì che la scadenza nasce davvero.

Backend (lotti_produzione.py):
- `scadenza_giorni_override` sulla ricetta: durata corretta a mano che VINCE
  sul calcolo dagli ingredienti (helper _scadenza_con_override, applicato in
  registra-produzione-lotto E in genera-lotto legacy).
- GET /anteprima-scadenza/{ricetta_id}?data_produzione= → {data_scadenza,
  giorni, scadenza_abbattuto, ingrediente_critico, durata_memorizzata}.
- /registra-produzione-lotto: nuovi param `data_scadenza` (dd/mm/yyyy o ISO)
  e `memorizza_durata`; con memorizza la durata (giorni dalla produzione,
  max 730) viene salvata sulla ricetta → le produzioni successive partono
  già giuste.
Frontend (ModalRegistraLotto):
- riquadro "📅 Scadenza" con la data PROPOSTA già nel campo (input date
  modificabile) + nota "proposta: N giorni (critico: uova)" o "durata
  memorizzata: N giorni";
- se l'operatore cambia la data compare la spunta (attiva di default)
  «Ricorda questa durata per "prodotto"» → memorizza_durata=true.
Verifica: pyflakes solo preesistenti, compile+import OK, set puro 143
passed, build frontend pulita.

### 23/07/2026 (segue 19) — Panettone & co.: lunga conservazione riconosciuta dal motore

Collaudo Enzo sul modale scadenza: OK ("la durata resta memorizzata"), ma la
PROPOSTA di partenza restava sbagliata: "non deve darmi un giorno perché c'è
l'uovo dentro — è un prodotto cotto che si conserva 3 mesi".

Fix in shelf_life.py:
- Nuove categorie prodotto: panettone/pandoro 90gg (ambiente/frigo/abb+,
  180 freezer), colomba 60gg, roccocò (anche senza accento), mostaccioli,
  susamielli, taralli, tutti 30gg/180.
- Nuovo set PRODOTTI_LUNGA_CONSERVAZIONE (+ biscotti): per questi prodotti
  gli ingredienti COTTI NELL'IMPASTO (uova, latte, burro —
  INGREDIENTI_COTTI_NELL_IMPASTO) NON accorciano la scadenza della
  categoria; le farciture post-cottura (crema, panna, ricotta…) accorciano
  come sempre (panettone farcito con crema → corto, giusto così).
- Aggiunti anche a PRODOTTI_COTTI_IN_FORNO (uova→uova cotte altrove).
Risultato: "Panettone Artigianale" con uova → proposta 90 giorni (180 in
freezer) SENZA correzione manuale; la data resta comunque modificabile nel
modale e la durata corretta a mano resta memorizzata (giro precedente).
Collaudo: nuovo tests/test_shelf_life_panettone.py (7 test: panettone 90/180,
farcito con crema si accorcia, biscotti con uova ≠ domani, pandoro/colomba/
taralli, roccoco senza accento, torta con panna resta prudente) + regressione
sfogliatella OK. Set completo: 150 passed.

### 23/07/2026 (segue 20) — 43 ricette nuove col solo nome (dettatura Enzo)

Enzo ha dettato ~43 prodotti da creare come ricette "solo nome" (ingredienti
e foto li mette lui dall'app). Il sandbox non raggiunge il backend live →
SEED UNA-TANTUM all'avvio del server (pattern seed_panini_rosticceria):
- `RICETTE_SOLO_NOME_23072026` + `seed_ricette_solo_nome()` in ricette.py,
  chiamata da server.py startup (try/except non bloccante);
- prudente: salta i nomi già esistenti (case-insensitive) e dopo il primo
  giro non tocca più nulla (flag `seed_ricette_nomi_23072026` in
  sistema_stato) — se Enzo elimina una ricetta NON ricompare;
- reparti assegnati: bar (Spritz, Crema di caffè), pasticceria (26 dolci),
  rosticceria (bollini, focaccine, bastoncini, hot dog, pizze fritte).
Normalizzazioni dalla dettatura vocale: "Aspritz"→Spritz, "Minion"→mignon,
"zuppolina"→Zeppolina, "divini amor"→Divino Amore, "sapiens"→Sapienze,
"profitterol"→Profiterole, "marinata"→Marinara, "bellino"→Bollino (uniformato
sui tre). DA VERIFICARE CON ENZO: "Bollino", "Sapienze", "Divino Amore",
"Marinara" — se il nome vero è diverso li rinomina dall'app.
Verifica: pyflakes solo preesistenti, compile+import OK, test 87 passed.

### 23/07/2026 (segue 21) — Secondo lotto ricette dettate: i Savarese mignon

Seed generalizzato in _seed_lotto_nomi(flag, lista) — ogni dettatura è un
lotto con flag proprio (il primo poteva essere già scattato col deploy).
B2 (flag seed_ricette_nomi_23072026_b2): Savarese mignon panna / panna e
pistacchio / panna e cioccolato / crema ed amarena (pasticceria).
"savareae/savarese" dalla dettatura → uniformato "Savarese".

### 23/07/2026 (segue 22) — Ingredienti proposti per le 47 ricette dettate + pagina foto

Enzo ha verificato le ricette create ("sono tutte giuste, funziona tutto") e
ha chiesto: (a) impostare gli ingredienti, (b) foto scaricabili in locale.
(a) Nuovo passo del seed (seed_ingredienti_dettati, flag
    seed_ingredienti_nomi_23072026): INGREDIENTI_DETTATI_23072026 con 47
    ricette → ingredienti/ingredienti_dettaglio (quantità indicative ~10 pz,
    unità solo g/ml/pz, verificate con check automatico) applicati SOLO alle
    ricette ancora VUOTE (mai sopra il lavoro di Enzo), origine "automatica"
    (badge 🤖 nel form). Una tantum.
(b) Download immagini esterne ANCORA bloccato dal proxy (ritestato: HTTP 000
    su Wikimedia/Pexels) → impossibile salvare foto in locale. Consegnata
    pagina scratchpad/foto_ricette_nuove.html: per ognuna delle 47 ricette
    link Google-licenza-libera/Wikimedia/Google + NOME FILE esatto per
    l'abbinamento automatico dell'import foto da Drive.
Verifica: pyflakes solo preesistenti, compile+import OK.

### 23/07/2026 (segue 23) — Foto dal web scaricate DAL SERVER (Wikimedia Commons)

"Ora carica le foto": dal sandbox impossibile (immagini e WebFetch bloccati
dal proxy, ritestati entrambi) → le scarica il BACKEND su Render, dove
internet funziona. In ricette.py:
- FOTO_WEB_TERMINI_23072026: termine di ricerca curato per ognuna delle 47
  ricette; None dove una foto generica sarebbe SBAGLIATA (occhio di bue su
  Commons = uova fritte!, bollini/bastoncini = prodotti locali) — meglio
  senza foto che con quella sbagliata.
- _cerca_foto_commons(): API Wikimedia Commons (generator=search, namespace
  File, thumb 800px, licenze libere per natura di Commons), User-Agent
  proprio.
- importa_foto_da_web(): per ogni ricetta ANCORA SENZA foto scarica la prima
  immagine pertinente e la salva in foto_files (_id "web_<ricetta_id>",
  stesso store Mongo di tutte le foto) + foto_url con ?v=. Mai sopra una
  foto esistente. Esiti dettagliati (caricate/senza_risultato/senza_termine).
- POST /ricette/importa-foto-web per rilanciare a mano; seed_foto_web()
  una-tantum in background all'avvio (flag seed_foto_web_23072026 in
  sistema_stato, con gli esiti salvati dentro).
Verifica: pyflakes solo preesistenti, compile+import OK, test 76 passed.

### 24/07/2026 — Integrata la ristrutturazione navigazione (zip esterno verificato)

Enzo ha consegnato "Lottiristrutturato.zip" (ristrutturazione fatta fuori,
probabilmente con ChatGPT) con regole precise: niente funzionalità eliminate,
palette intatta, npm ci + build + test, occhio a App.js/routing/permessi,
niente segreti. VERIFICA PRIMA DELL'INTEGRAZIONE:
- lo zip parte dallo snapshot RECENTE di main (contiene tutti i fix del
  23/07, incluso l'header mobile) — solo 7 file diversi + 2 nuovi;
- confronto AUTOMATICO degli id pagina vecchi vs nuovi: nessuna pagina persa
  (insiemi identici); hash e deep-link invariati;
- nessun segreto (i match grep sono i soliti os.environ.get);
- palette rispettata — anzi index.html CORREGGE un colore vietato
  (theme-color indaco #1E1B4B → salvia #5b7a6b) e porta title/description/
  noscript in italiano.
Cosa cambia:
- frontend/src/config/navigation.js (NUOVO): PRIMARY_TABS (5: Oggi,
  Produzione, Tracciabilità, Magazzino, Acquisti), SECONDARY_TABS raggruppati
  per attività (Gelati e Fornitori spostati lì, pagine intatte), HACCP_TABS,
  PAGE_NAMES/PAGE_META/TAB_HEADER_PROPRIO/ADMIN_TABS/VALID_TABS — tutto
  estratto da App.js (906→752 righe);
- AltroDropdown.jsx: intestazioni di sezione nel menu (classe
  .g-dropdown-section, già presente nel CSS);
- rimossi .gitconfig del vecchio ambiente e i riferimenti residui
  (.gitignore, un wording in STATO.md e test_reports/iteration_72.json);
- frontend/README.md sostituito con documentazione specifica;
- RISTRUTTURAZIONE_NAVIGAZIONE.md alla radice (nota di consegna).
NOTA: la navbar resta NASCOSTA da App.css (navigazione = card della Home),
quindi l'effetto visibile è su titoli di pagina/document.title e sulla
struttura del codice; permessi ADMIN_TABS invariati.
Verifiche (come richiesto): npm ci OK, CI=false npm run build Compiled
successfully, backend 150 test passed + compileall + import-check OK.

### 24/07/2026 (fase 2) — Ristrutturazione: verifica iniziale

Branch claude/repo-review-completion-40cdmd allineato, remote ok.
- backend compileall: OK, nessun errore.
- pytest COMPLETO (tests/): 180 passed, 3 skipped, 308 failed + 22 errors —
  TUTTI i falliti sono i test test_iterationNN/iterNN che richiedono un
  server live (requests verso REACT_APP_BACKEND_URL: MissingSchema/
  ConnectionError; test_iteration47 fallisce già in collection). STATO NOTO
  e preesistente, non regressione. Riferimento: set puro 150 passed.
- frontend: npm ci OK (1508 pacchetti), CI=false npm run build → Compiled
  successfully, nessun warning bloccante.

### 24/07/2026 (fase 2, chiusura) — Ristrutturazione: cosa è stato fatto

Tranche committate una a una (build+test verdi prima di ogni push):
1. App.js 906→315 righe: config/pageMeta+permissions, hooks/useAppNavigation,
   layouts/AppLayout+KioskLayout, router/AppRouter+pages (registro pagine
   dichiarativo unico). Zero pagine perse (confronto automatico id).
2. Dialoghi coerenti: via alert()/window.prompt() operativi (GelatiView,
   RegistroAllergeni, SchedaProdotto, LottiList richiamo, printHtml) →
   toast + conferma() + NUOVO chiediTesto() in ConfermaHost.
3. PWA: manifest.json + favicon.svg salvia + apple-touch-icon (prima
   MANCAVANO del tutto); nome app "Ceraldi Group — HACCP e Tracciabilità".
4. Sicurezza: require_admin su 29 endpoint distruttivi/config (dettaglio in
   memory/AUDIT_SICUREZZA.md) + log contestuali nei punti muti principali +
   tests/test_auth_permessi.py (9 test).
5. Errori frontend: apiError traduce timeout/rete/401/403/5xx in messaggi
   comprensibili (usato ovunque); hooks/useInvioSingolo per i doppi invii.
6. Ricerca universale: + fatture/ordini/produzioni + scheda lotto completa
   (origine/fornitore/fattura/quantità/consumo/residuo/destinazione) con
   pannello espandibile nel frontend.
7. Pagina Oggi: 8 voci operative navigabili in testa, KPI economici sotto.
8. Refactor: FormRicetta (854 righe) fuori da BackofficeView (1616→792);
   FattureList fuori da FornitoriList (1337→1199).
9. Test frontend NUOVI: src/__tests__/navigazione.test.js (13 test).
10. Documenti: memory/AUDIT_NAVIGAZIONE.md, AUDIT_SICUREZZA.md,
    PIANO_REFACTOR.md (con stato completato/verificato/da fare/rischi).
Audit di sola lettura (3 agenti): gestione errori backend (0 punti
pericolosi su ~350 except), sicurezza endpoint (lacune → fix al punto 4),
inventario file grandi (→ PIANO_REFACTOR.md). Branding: zero residui
"Emergent"; alert nativi rimasti: solo il fallback documentato di
conferma.js.
NON fatto (dichiarato): verifica visiva mobile 360-1024px (sandbox senza
rete nel browser — serve il giro di Enzo da telefono); test con DB
(dedup/FIFO/HACCP invalida) — serve mongomock; split restanti in
PIANO_REFACTOR.md.

### 24/07/2026 (tranche 3) — Collaudo E2E su Mongo di prova, audit flussi e quantità

- NUOVO tests/test_e2e_flussi.py su mongomock-motor (DB "Gestionale_Test",
  mai il reale, zero rete): doppio import stessa fattura non duplica, import
  crea lotti fornitori, FIFO consuma il più vecchio con conversione kg↔g,
  quantità insufficiente mai negativa E ORA SEGNALATA, ingrediente
  sconosciuto segnalato, require_admin blocca dipendente/passa admin.
  6 test + estensioni; suite auth+e2e: 15 passed. mongomock-motor aggiunto a
  requirements (solo test).
- PROVA CON XML VERO di Enzo (in chat, non salvato nel repo): fattura F.lli
  Fiorentino 16/07/2026, 12 righe → import ok, 12 lotti, dedup ok.
- Audit FLUSSI (agente, codice reale) → memory/AUDIT_FLUSSI.md: 5 flussi
  documentati (creati/modificati/rollback/errori) + 10 incoerenze.
- Audit QUANTITÀ/UNITÀ (agente) → memory/AUDIT_QUANTITA_UNITA.md: 7 problemi
  (1 ALTA condizionale: unità non convertibili nel FIFO) + conferme del già
  corretto.
- FIX APPLICATI (i 2 sicuri tra i gravi): (1) invio ordine: validazione
  righe confermate PRIMA del claim — mai più ordini "bruciati";
  (2) scarico FIFO parziale: nuovo campo ingredienti_insufficienti
  {richiesto, mancante, unita} nel risultato + toast rosso sul tablet —
  prima il fabbisogno mancante spariva in silenzio. Test dedicato.
- DA FARE (documentati nei due audit): chiave fatture senza P.IVA,
  idempotenza produzione, manda-al-banco atomico, cascade delete fattura,
  fix quantità 1-5, refactor mirati uno alla volta (PIANO_REFACTOR.md),
  giro visivo mobile di Enzo con screenshot.

### 24/07/2026 (tranche 4) — Integrità del ciclo operativo (decisioni Enzo)

1. RICHIAMO ASL = BLOCCO VERO nel backend: /lotti/recall/esegui ora marca i
   lotti stato="bloccato_richiamo" (+richiamo_ref, bloccato_il/da/motivo) e
   scrive il registro `blocchi_lotti` {data, utente, motivazione,
   richiamo_ref, quantita, note}. manda-al-banco e farciture RIFIUTANO (423)
   i lotti bloccati; consultazione/tracciabilità/dossier restano liberi;
   nuovo POST /lotti/{id}/sblocca-richiamo (require_admin, motivo
   obbligatorio, tracciato, stato→"sbloccato") e GET /lotti/{id}/blocchi.
2. DEDUP FATTURE SENZA P.IVA: su collisione dell'indice numero+piva, se il
   fornitore NON combacia si conservano ENTRAMBE le fatture (la seconda con
   piva surrogata "ND:<fornitore>" + verifica_richiesta=true) e l'esito
   segnala "possibile duplicato — verifica richiesta". Mai più sovrascritture
   tra fornitori diversi.
3. IDEMPOTENZA operation_id su registra-produzione-lotto e manda-al-banco:
   claim su `operazioni_idempotenti` (insert _id, DuplicateKeyError→ritorna
   il risultato salvato). Il tablet genera l'id per tentativo (useRef,
   rigenerato solo dopo il successo) — il doppio tocco/rete lenta non scala
   mai due volte.
4. ELIMINAZIONE FATTURA SICURA: GET /fatture/{id}/impatto (lotti,
   movimentati, produzioni, giacenza residua); DELETE con regole: senza
   collegamenti→ok; lotti mai movimentati→serve conferma=true (elimina anche
   i lotti); movimentati/produzioni→409 MAI eliminabile; nuovo POST
   /fatture/{id}/annulla (require_admin, motivo) = annullamento LOGICO che
   chiude i lotti residui (esaurito, stato annullata_fattura) senza
   cancellare nulla.
5. STOP CONVERSIONI INCOMPATIBILI nel FIFO: unità non convertibili (CT, PZ
   senza peso censito) → il lotto NON viene scalato, esito
   `conversioni_non_disponibili` + toast rosso sul tablet ("censisci il
   contenuto confezione"). Mai più numero-contro-numero.
6. TEST dedicati per ognuno in test_e2e_flussi.py (blocco+sblocco richiamo,
   idempotenza, dedup senza piva con indice unico simulato, delete
   sicura+annullamento, conversione non disponibile): suite 107 passed,
   build frontend pulita. Refactor FornitoriList RIMANDATO come da revisione.

## 24/07/2026 — Tranche 5 PARZIALE: primi fix dall'audit visivo mobile/tablet (interrotto)

L'agente dell'audit visivo (4 dimensioni × 9 pagine su rig locale) è stato
INTERROTTO a metà dal limite di sessione: la tranche 5 NON è conclusa (il
documento memory/AUDIT_VISIVO_MOBILE_TABLET.md non esiste ancora, gli
screenshot sono parziali). Qui si salvano i fix già applicati e verificati:
1. PALETTE: rimossi gli ultimi grigi-blu freddi (slate) — card "slateV" della
   Dashboard e card/gradiente "Magazzino" di TabletHome/TabletView rimappati
   su sabbia scura #6f583a→#4a3f33; sfondo kiosk TabletHome da #0f172a
   (blu notte) a #1c2620 (verde-nero salvia) con testi secondari riscaldati.
2. RICERCA GLOBALE: i documenti del dizionario senza nome_canonico
   comparivano come righe VUOTE → proiezione backend estesa
   (nome_normalizzato, nome_originale) + fallback a catena nel frontend.
3. LOTTI: un lotto bloccato da richiamo era indistinguibile in lista →
   bordo rosso + badge "Bloccato — richiamo".
4. RICEZIONE MERCE: header con flex-wrap (i tab e "Ricezione Manuale"
   uscivano dallo schermo su smartphone 360px).
5. BOTTONE TOUR "?": su #ordini copriva il tab "Compra" della barra fissa
   in basso → si alza a 84px solo su quella pagina.
Verifiche: pyflakes/compileall/import-check ok, 103 test backend passed,
build frontend pulita. PROSSIMO PASSO: rilanciare l'audit visivo per
completare screenshot, checklist e AUDIT_VISIVO_MOBILE_TABLET.md; poi
tranche 6 (AUDIT_IMPORT_DATABASE) da capo.

## 24/07/2026 — Tranche 6: AUDIT_IMPORT_DATABASE (import, catena, scheduler temperature, registri/stampe)

Audit completo su codice reale + test su mongomock (DB "Gestionale_Test",
mai produzione). Tre documenti nuovi: memory/AUDIT_IMPORT_DATABASE.md,
memory/AUDIT_REGISTRI_STAMPE.md, memory/AUDIT_SCHEDULER_TEMPERATURE.md.
FIX APPLICATI (ognuno con test in backend/tests/test_audit_tranche6.py):
1. GRAVE — anomalie temperature riscrivibili cambiando le soglie: get_allarmi
   ricalcolava con i temp_min/temp_max CORRENTI → un cambio soglie via /config
   faceva sparire/comparire anomalie storiche. Ora le soglie e lo stato
   allarme vengono CONGELATI nel record alla registrazione (manuale e
   automatica) e allarmi/report usano quelli (temperature_positive.py,
   temperature_negative.py, retrocompatibile coi record vecchi).
2. Job automatico 07:00: il clamp min(-15.0,…) generava letture congelatori
   FUORI soglia mai segnalate → ora clamp sulle soglie reali della scheda,
   con allarme=False e soglie salvate nel record (haccp_auto.py).
3. Report HACCP mensile: un apparecchio con zero rilevazioni nel mese SPARIVA
   dalla stampa (riga saltata) → sempre presente; celle "." → "N/D" con
   legenda "Dato non disponibile"; conformità valutata con le soglie del
   momento; limiti 1000/2000→20000/50000 (report_haccp.py).
4. Registro lotti ASL: troncava ai 2000 lotti più recenti (i più vecchi
   sparivano in silenzio) → 50000 come il registro mensile (utils.py).
DA FARE (documentati nei tre AUDIT_*.md): scheduler in-memory con catchup
solo-oggi (giorno di backend spento = buco permanente, ora almeno "N/D" in
stampa); PUT scheda e popolamento storico senza require_admin; placeholder
"TEMP" residuo se il backend cade a metà produzione; job_pulisci_lotti_scaduti
che CANCELLA fisicamente lotti citati da movimenti/vendite (registro 5 anni:
da concordare passaggio ad archiviazione logica); pagina "Verifica integrità
gestionale" proposta (non implementata) in AUDIT_IMPORT_DATABASE.md §5.
Verifiche: pyflakes pulito, compileall+import ok, suite non-live 214 passed
(200 preesistenti + 14 nuovi, zero regressioni — confronto fatto con git
stash sull'albero pulito). Non verificabile in sandbox: PEC/Drive reali,
resa visiva finale delle stampe (serve il giro di Enzo).

## 24/07/2026 — Tranche 5 COMPLETATA: audit visivo mobile/tablet (rig locale + screenshot reali)

Matrice completa sul rig locale (backend mongomock 8001 + build servita 3001,
screenshot Playwright): 4 dimensioni (360×800, 390×844, 768×1024, 1024×768)
× 9 pagine + kiosk/modali/ricerca = 76 misure. Scroll orizzontale di pagina:
ZERO ovunque. Documento: memory/AUDIT_VISIVO_MOBILE_TABLET.md.
CORRETTI (solo usabilità/CSS, ri-fotografati dopo il fix):
1. Magazzino: filtri "Tipo"/"Al" tagliati a 360px → griglia auto-fit +
   minWidth:0 (ControlloMagazzinoView).
2. Emoji → icone Lucide dove rendevano coi colori di sistema (blu su
   Android): card HACCP della Home, widget Stato sistema, intestazioni di
   pagina (AppLayout usa le icone di navigation.js), registro pesce Dashboard.
3. Bonifica scala slate blu-grigia residua (~90 occorrenze) nel kiosk tablet:
   TabletView, ModalRegistraLotto, ModalCambioFoto, PannelloReparti,
   ModalRichiediMerce, CardProdotto → neutri caldi della palette.
4. Ricerca kiosk "Cerca dolce…" quasi illeggibile sul gradiente arancio →
   fondo scuro traslucido + bordo.
5. Banner Lotti e testata card XML Ricezione: wrap corretto a 360px;
   chip reparti Backoffice con flex-wrap.
RIMANDATI con motivo (nel documento): emoji dentro le label dei bottoni
kiosk/backoffice (serve ristrutturazione JSX), Backoffice lunghissimo (serve
paginazione = funzionale), FornitoriList (vincolo: refactor a parte),
indicatore scroll griglia temperature, neutri gray-* con cast freddo.
Verifiche: build Compiled successfully; screenshot prima/dopo in scratchpad
audit_visivo (fix_*.png). Prossimo passo da PIANO_REFACTOR: FornitoriList
(test-prima → split → confronto).

## 25/07/2026 — Refactor FornitoriList.jsx (1199→394) + 2 crash reali corretti

Rifattorizzazione col metodo concordato (confronto-prima → divisione →
confronto-dopo sul rig locale con screenshot Playwright):
1. FornitoriList.jsx da 1199 a 394 righe (orchestratore: stato + chiamate).
   Nuovi moduli in fornitori/: SchedaAnagraficaModal.jsx (411, il modale
   con ContattiCard/RegistroRicetteCard/QualitaRicetteCard/RimanenzeCard),
   TrackerColliOmaggio.jsx (270, componente puro), RegistroQualificaPanel.jsx
   (112, autonomo), NoteRicevimento.jsx (64), utilsFornitori.js (22).
   Nessun cambio di comportamento: markup copiato 1:1, stato invariato.
2. CRASH REALE TROVATO E CORRETTO (era il vero valore del giro): il pannello
   "Registro Ricevimento Merci — Temperature" crashava all'apertura con
   ReferenceError "BADGE_TIPO is not defined" — nell'estrazione di fase 2
   SchedeRicevimentoPanel.jsx era stato separato lasciando BADGE_TIPO e
   NoteRicevimento dentro FornitoriList senza export/import. Riprodotto sul
   rig (pageerror), corretto, riverificato: il registro ora si apre con le
   consegne e le note operatore.
3. SECONDO CRASH STESSA FAMIGLIA: fornitori/FattureList.jsx usava
   FileText/Eye/Printer senza import da lucide → lo storico fatture nella
   scheda anagrafica crashava. Corretto e riverificato.
Verifiche: screenshot prima/dopo (scratchpad audit_visivo/prima_*/dopo_*):
lista fornitori IDENTICA, modale anagrafica e registro ricevimento ora
renderizzano senza errori JS; build di produzione Compiled successfully.
PIANO_REFACTOR aggiornato: FornitoriList [FATTO]; prossimo LottiList.jsx.

## 25/07/2026 — Refactor LottiList.jsx (1184→681) + modale "Genera Lotto" irraggiungibile

Stesso metodo di FornitoriList (screenshot prima → divisione → screenshot dopo
sul rig locale, backend mongomock su Gestionale_Test).
1. LottiList.jsx da 1184 a 681 righe. Nuovi file: lotti/uiLotti.jsx (68 —
   Button/Input/Badge/Modal; Card NON duplicata, si riusa shared/Card che era
   già identica), utils/allergeni.js (38 — i 14 allergeni Reg. UE 1169/2011,
   le parole chiave e l'helper allergeniDaTesto con la logica identica di
   prima), lotti/ModalDettaglioLotto.jsx (223), lotti/ModalRecallIngrediente.jsx
   (124), lotti/ModaliLotto.jsx (155 — Report HACCP, Registro ASL, Genera
   Lotto). Markup copiato 1:1, stato e chiamate restano nel genitore.
2. CONFRONTO VISIVO: 10 screenshot (2 dimensioni × pagina + 4 modali).
   7 identici byte per byte; i 3 diversi (pagina 1024, report 390, dettaglio
   390) hanno solo 1-2px di scorrimento del contenuto sotto l'overlay —
   verificati a video ritagliando le zone: stesso identico contenuto.
   Nessun errore JS in pagina, build Compiled successfully.
3. DA DECIDERE CON ENZO (segnalato, NON toccato): il modale "Genera Nuovo
   Lotto" della pagina Tracciabilità è IRRAGGIUNGIBILE — lo stato showForm
   non viene mai attivato e in tutta l'app non esiste più un bottone che lo
   apra (il flusso di produzione oggi passa dal tablet). Il codice è stato
   conservato identico: va ripristinato il bottone oppure rimosso, ma è una
   scelta sua, non mia.
PIANO_REFACTOR: LottiList [FATTO]. Prossimo in lista: tablet/
ModalRegistraLotto.jsx (rischio ALTO — da fare con collaudo sul tablet).

## 25/07/2026 — Tablet: scelta del frigorifero/congelatore era di fatto impossibile

Segnalazione di Enzo con screenshot: nel modale "Registra lotto" non
comparivano i suoi frigoriferi e congelatori, vedeva solo il valore
pre-compilato ("Cella Fresca Nord") e non poteva scegliere dove mettere il
prodotto.
CAUSA REALE (ModalRegistraLotto.jsx:708): il campo posizione era un
`<input type="text">` con `<datalist>`. Su Android/Chrome il menu della
datalist non si apre di fatto: l'elenco c'era nei dati (TabletView passa già
frigoriferi/congelatori da GET /api/attrezzature/) ma era irraggiungibile a dito.
FIX: sostituito con un `<select>` vero, etichettato "In quale frigorifero?" /
"In quale congelatore/abbattitore?", che elenca TUTTI gli apparecchi censiti
(su telefono si apre a tutto schermo). Conservata la scrittura libera con
l'opzione "Altro (scrivi a mano)…" + link "← torna all'elenco", così non si
perde la possibilità di indicare un apparecchio non ancora censito.
VERIFICATO sul rig locale col tablet a 390×844: il menu elenca i 3 frigoriferi
di prova e, cambiando destinazione ad Abbattitore, i 2 congelatori.
GIÀ ESISTENTI (verificati nel codice, comunicati a Enzo, nessuna modifica):
- Rinominare/aggiungere/eliminare frigoriferi e congelatori: si fa dalle
  pagine Temperature positive (colonne frigoriferi) e Temperature negative
  (colonne congelatori) — clic sull'intestazione della colonna per
  rinominare/eliminare, pannello "Aggiungi Frigorifero/Congelatore" in fondo
  (TemperaturePositiveView.jsx:49/61/110, TemperatureNegativeView.jsx:36/46/81;
  backend attrezzature.py con POST/PUT rinomina/DELETE). Da valutare con Enzo
  se aggiungere una voce dedicata nel menu Amministrazione: oggi è poco
  trovabile.
- Guasto di un frigo/congelatore con spostamento dei lotti: esiste ed è
  completo, ma passa dalla pagina Anomalie — si registra l'anomalia
  sull'attrezzatura, il sistema RICALCOLA IN TEMPO REALE i lotti dentro
  (anomalie.py:268 lotti-attuali) e propone lo spostamento in blocco verso
  un'altra posizione (anomalie.py:312 sposta-lotti-massivo), registrando su
  OGNI lotto il movimento con riferimento all'anomalia e l'azione correttiva
  HACCP (Reg. CE 852/2004). Pannello nel frontend: AnomalieView.jsx:95-197.

## 25/07/2026 — Accessi: i dipendenti vedono SOLO le card del tablet

Richiesta di Enzo: "far uscire solo le card tablet ai dipendenti e solo quando
si digita il PIN amministratore far comparire tutto", con Ordini e Lavagna
spostati tra le card.
COSA CAMBIA:
1. L'app si apre SEMPRE sulle card del tablet. Chi non è amministratore non
   vede nemmeno il tastierino del gestionale (LoginGate: se !isAdmin →
   #tablet/home). Digitando a mano un indirizzo del gestionale si viene
   rimandati alle card (AppRouter). Il titolare entra dal bottone in basso a
   destra "🔒 Gestionale — solo titolare" col PIN amministratore (vale 2 ore).
2. CARD NUOVE nel tablet (le funzioni non si perdono, cambiano posto):
   "🛒 Ordini" (#tablet/ordini → OrdiniView con barra sticky "← Reparti") e
   "📺 Lavagna richieste" (#tablet/lavagna → MagazzinoBarView soloLavagna).
   Magazzino era già una card.
3. RUOLO SEMPRE AGGIORNATO: il login operatore del tablet ora salva anche il
   ruolo (TabletHome.handleSuccess → saveRuolo), così un "amministratore"
   rimasto in memoria da una sessione precedente viene declassato appena entra
   un dipendente; il PIN admin del kiosk salva "amministratore"
   (handleEsciAdmin), altrimenti il gestionale rimbalzerebbe subito indietro.
NOTA DI SICUREZZA: questo è un filtro di NAVIGAZIONE (cosa si vede sullo
schermo). La sicurezza vera resta nel backend: auth_dependency su /api +
require_admin sugli endpoint distruttivi — invariati.
COLLAUDO sul rig locale (390×844, PIN di prova 1111 dipendente / 9999 admin):
apertura senza sessione → #tablet/home; le 7 card presenti; dipendente entrato
in Pasticceria che forza #dashboard → rimandato a #tablet/home, ruolo salvato
"operatore"; PIN admin dal bottone → #dashboard con ruolo "amministratore";
card Ordini e Lavagna si aprono e il tasto "← Reparti" riporta alle card.
Build pulita.

## 25/07/2026 — Quantità e unità: chiusi i difetti 2, 3 e 4 dell'audit

Correzioni di calcolo rimaste aperte da AUDIT_QUANTITA_UNITA, ognuna con test.
1. BEVANDE NEL FOOD COST (regola del titolare finalmente applicata anche lì):
   il costo di una ricetta usava il prezzo al chilo anche per amari, sciroppi,
   birre e acqua — un prezzo che per quei prodotti non esiste. Ora un
   ingrediente del reparto bar viene contato a bottiglia/cartone; se il prezzo
   a confezione manca, il costo NON viene inventato: la riga esce come "non
   calcolabile" e il prodotto finisce tra quelli da sistemare.
   (food_cost.py: nuovo _e_bevanda_a_unita, categoria dal dizionario o dedotta
   dal nome con lo stesso classificatore del listino).
2. CENTILITRI: "cl" non era gestito e finiva nel ramo generico (diviso 1000):
   una bottiglia da 75 cl valeva 0,075 kg invece di 0,75 — errore ×10 sul
   food cost. Aggiunti cl (÷100) e dl (÷10) in ENTRAMBI i motori di
   conversione (converti_in_kg e il to_kg dell'import fatture, dove "75 CL"
   restava addirittura 75 kg).
3. CARTONI TRATTATI COME GRAMMI: le unità a confezione (cartone, cassa,
   bottiglia, collo, vaschetta…) cadevano anch'esse nel ÷1000, cioè "1 cartone
   = 1 grammo", con food cost praticamente azzerato in silenzio. Ora sono
   dichiarate non convertibili (nuovo elenco UNITA_A_CONFEZIONE): il costo si
   prende dal prezzo a confezione, altrimenti la riga è segnalata.
4. CASCATA MAGAZZINO MULTI-LOTTO: scaricando più pezzi di quanti ne ha il
   lotto più vecchio, i lotti "fratelli" venivano scalati col fattore
   pezzi/cartone del lotto CLICCATO. Con due lotti dello stesso prodotto a
   confezionamento diverso (X24 e X12) si scaricava la quantità sbagliata.
   Ora ogni lotto usa il proprio fattore e i lotti non confrontabili (sfuso a
   kg quando la lista mostra pezzi) restano fuori dalla cascata invece di
   essere mal convertiti (magazzino_unificato.py).
Test: tests/test_quantita_unita.py (9 nuovi, puri) + 2 nuovi in
test_e2e_flussi.py sulla cascata. Suite non-live: 225 passed (erano 214),
zero regressioni; pyflakes pulito (resta un warning preesistente su UNITA_PESO).
Restano aperti solo §5 (default 50 g/pezzo quando manca il peso reale) e §6
(bassa) di AUDIT_QUANTITA_UNITA.

## 25/07/2026 — «Proponi ingredienti» per TUTTE le ricette vuote (un bottone solo)

Come funziona il motore (chiarito a Enzo, che non ricordava): NON c'è ricerca
web. L'ordine delle fonti in POST /food-cost/suggerisci-ingredienti è:
1) Claude (modello Haiku) se ANTHROPIC_API_KEY è configurata su Render;
2) base curata di ~60 ricette napoletane dentro l'app (funziona anche senza
   chiave e senza internet); 3) la ricetta PIÙ SIMILE già in archivio. In coda,
i gusti scritti nel nome entrano sempre ("babà panna e pistacchio").
NOVITÀ: il motore è stato estratto in _proponi_ingredienti_per_nome (usato sia
dal bottone singolo sia dalla massa: una sola logica da correggere) e sono nati
- GET /food-cost/ricette-senza-ingredienti → quante e quali ricette sono vuote;
- POST /food-cost/proponi-ingredienti-tutte (require_admin) → le compila a
  blocchi di 15 (l'AI impiega secondi per ricetta) e risponde con
  compilate/senza_proposta/restanti.
REGOLE: non tocca MAI una ricetta che ha già ingredienti (nessuna
sovrascrittura); salta i prodotti di rivendita (comprati, non preparati); ogni
ricetta compilata resta marcata ingredienti_origine="automatica" +
ingredienti_fonte + data, così si vede cosa ha proposto la macchina e va
ricontrollato.
FRONTEND: Backoffice → Ricette, bottone "Proponi ingredienti alle ricette
vuote": chiede conferma dicendo QUANTE ne compilerà, poi cicla i blocchi
mostrando l'avanzamento ("N compilate, ne restano M…").
Test: test_e2e_flussi.py::test_proponi_ingredienti_a_tutte_le_ricette_vuote
(compila le vuote, NON sovrascrive la piena, salta la rivendita, marca origine
e fonte). Suite non-live 226 passed, build frontend pulita.

## 25/07/2026 — Kit "grafica e semplicità" portabile su altre app del gruppo

Richiesta di Enzo: portare l'aspetto e la facilità d'uso di Lotti su
impresasemplice.online. Da questa sessione NON è possibile lavorare su quel
repository (l'accesso GitHub è limitato a ceraldicontabilita/lotti), quindi si
è preparato il pacchetto da portare là: design_handoff/KIT_ALTRE_APP.md.
Contiene: (1) elenco di cosa copiare fisicamente (tokens/, ui_kit/ e le quattro
skill riusabili .claude/skills/); (2) le regole visive con i valori reali presi
da frontend/src/index.css (palette salvia/crema/sabbia, mai colori freddi,
ombre tinte salvia, Fraunces + Plus Jakarta Sans, raggi, tap target 44px, icone
Lucide, niente emoji nelle UI); (3) DODICI regole di semplicità ricavate dalle
scelte fatte su Lotti in questi mesi (card grandi come punto di partenza, ogni
ruolo vede solo il suo, caso normale precompilato, si sceglie da elenco e non
si scrive, tastierino grande, niente alert del browser, errori in italiano,
dato mancante dichiarato, niente doppioni al doppio tocco, via d'uscita sempre
visibile, colore con significato, attese dichiarate); (4) un PROMPT pronto da
incollare a chi lavorerà sull'altra app, con l'ordine dei passi e i vincoli;
(5) l'avvertenza esplicita che le regole di dominio di Lotti (FIFO, bevande a
cartone, richiami, HACCP) NON vanno portate a scatola chiusa altrove.

## 25/07/2026 — Chiusi due punti aperti degli audit: registri protetti e lotti mai cancellati

1. IL JOB NOTTURNO NON CANCELLA PIÙ I LOTTI. Ogni notte alle 01:30 il sistema
   eliminava FISICAMENTE i lotti scaduti da oltre 30 giorni non più usati in
   ricetta (scheduler.py, delete_one). Conseguenza: movimenti e vendite che
   li citavano restavano orfani e — soprattutto — quei lotti sparivano dai
   registri stampati, mentre il registro ASL dichiara "conservare 5 anni".
   Un'ispezione che chiede il registro di due mesi prima non li avrebbe più
   trovati. Ora il lotto resta a database con archiviato=True + data e motivo;
   i già archiviati sono esclusi dal giro successivo. Nota onesta: i lotti
   cancellati PRIMA di oggi non sono recuperabili.
2. REGISTRI STORICI SOLO DA AMMINISTRATORE. Otto endpoint che riscrivono dati
   HACCP retroattivi non chiedevano il ruolo admin: PUT della scheda annuale
   intera (temperature positive e negative), popola-con-chiusure (entrambe),
   popola-temperature, popola-sanificazione, popola-tutto, genera-oggi.
   Un dipendente — o un tablet lasciato acceso — poteva riscrivere un anno
   intero di temperature. Ora tutti richiedono require_admin.
Test: nuovo test_pulizia_notturna_archivia_e_non_cancella (archivia, non
tocca i prodotti ancora in ricetta, non riconta al secondo giro) e
test_auth_permessi esteso agli otto endpoint (cercando il decorator esatto,
perché lo stesso indirizzo esiste anche in lettura libera).
Suite non-live: 227 passed (erano 226). AUDIT_IMPORT_DATABASE §2.2 e
AUDIT_SCHEDULER_TEMPERATURE §2.4 passano da "da correggere" a "corretto".

## 25/07/2026 — Refactor BackofficeView (835→400) e fix del rientro nel gestionale

1. BackofficeView.jsx da 835 a 400 righe. Nuovi file: backoffice/TabProdotti.jsx
   (273, con RowProdotto e PannelloSoglieSuggerite), backoffice/TabFornitori.jsx
   (180, con RowFornitore e BADGE_STATO), backoffice/toastBackoffice.js (15,
   l'avviso in basso che era duplicato). Markup e logica identici.
   ATTENZIONE (lezione che si ripete): l'estrazione lasciava TabProdotti senza
   gli import di withToken e getOperatoreNome. La build passa lo stesso (sono
   warning, non errori): sarebbe stato un crash a runtime come i due trovati
   in FornitoriList. Trovato aprendo DAVVERO la pagina sul rig, non guardando
   la build.
2. FIX ACCESSO (trovato nello stesso collaudo): entrando nel gestionale dal
   bottone "Gestionale — solo titolare", bastava ricaricare la pagina per
   ritrovarsi il tastierino "Accesso Lotti". Il PIN admin del kiosk apriva il
   cancello del tablet e salvava il ruolo, ma non quello del gestionale: ora
   chiama anche setGateOk() — due ore, come promesso a Enzo.
Verifica: Backoffice aperto sul rig a 1024×768 come amministratore, le tre
schede (Prodotti & Soglie con 408 prodotti, Fornitori, Ricette) renderizzano
senza un solo errore JS; build pulita.

## 25/07/2026 — Refactor prudente del modale "Registra lotto" (tablet)

Il pezzo più delicato dell'app (lo usano i ragazzi ogni giorno). Approccio
volutamente conservativo: da 1059 a 940 righe, estratti SOLO i due blocchi
davvero isolabili — registraLotto/SelettoreQuantita.jsx (54) e
registraLotto/SelettorePosizione.jsx (97: destinazione frigo/banco/abbattitore
+ menu del frigorifero). Tutto lo stato è rimasto nel modale: con riferimenti,
effetti, farciture, giacenza, colazione e idempotenza intrecciati, spostarlo
sarebbe stato rischio senza guadagno.
COME È STATO VERIFICATO (metodo nuovo, più fine del solo screenshot):
- confronto pixel del modale prima/dopo: identico salvo il numero progressivo
  del lotto, che avanza a ogni prova (203 pixel su 1,3 milioni, tutti in quel
  riquadro);
- confronto dei PARAMETRI che il modale invia al backend premendo il bottone
  di registrazione: identici carattere per carattere (ricetta, pezzi, unità,
  scadenza, frigorifero, operatore);
- zero errori JavaScript in pagina; build pulita.
LIMITE DICHIARATO: sul banco di prova la registrazione non può COMPLETARSI
perché il MongoDB simulato non implementa arrayFilters (limite noto già
documentato nell'audit tranche 6, non un difetto dell'app): il collaudo
end-to-end vero lo fa Enzo dal tablet dopo il deploy.
Durante il lavoro è ricomparso l'errore del commento JSX prima del nodo
radice: la build lo segnala subito, corretto.

## 25/07/2026 — Tre segnalazioni di Enzo dal gemello digitale + data fattura in etichetta

1. "APRI RECALL NON FA NULLA" — difetto reale trovato. Il bottone scriveva la
   ricerca in sessionStorage e cambiava l'hash a #lotti; ma l'effetto che la
   applica (App.js) dipendeva SOLO dal cambio di pagina: essendo già sulla
   pagina Lotti, non si rieseguiva mai e non succedeva niente. Inoltre la
   chiave non era letta da nessun altro punto. Fix: nuovo helper
   utils/apriLotti.js che scrive la chiave, cambia l'hash SOLO se serve ed
   emette un evento; App.js ora ascolta anche l'evento. Aggiornati tutti e tre
   i chiamanti (gemello digitale, Dashboard economica, Controllo dati).
   Il bottone è stato anche RINOMINATO in "Cerca questo lotto": non apriva né
   apre un recall, apre la Tracciabilità filtrata su quel lotto — il nome
   prometteva un'altra cosa.
2. "REGISTRO HACCP NON SI CAPISCE" — non è specifico del lotto: apre il quadro
   dei controlli del mese. Rinominato "Registri HACCP del mese" con
   spiegazione al passaggio del dito. Da decidere con Enzo se toglierlo del
   tutto dal gemello del lotto.
3. ETICHETTA SENZA DATA FATTURA — nella riga "semola — SAIMA S.p.A. · Fatt.
   1/56437" mancava quando è arrivata la merce. Aggiunta la data in entrambi i
   generatori (stampa HTML e stampa termica ESC/POS): ora "Fatt. 1/56437 del
   12/06/2026". Test: test_etichetta_mostra_la_data_della_fattura.
4. RINOMINA "Cella Fresca Nord" → "Cella 1": è un dato del database di
   produzione, non del codice. Si fa da Temperature positive, clic
   sull'intestazione della colonna. Spiegato a Enzo.
Suite non-live: 228 passed. Build pulita.

## 25/07/2026 — «Proponi» non duplica più + dosi da laboratorio (base a 1 kg)

1. DIFETTO SEGNALATO DA ENZO: premendo "Proponi" nel form ricetta gli
   ingredienti venivano AGGIUNTI in coda a quelli già presenti, quindi al
   secondo clic comparivano doppi. Ora si uniscono senza doppioni (confronto
   per nome, senza accenti e maiuscole): quelli già in elenco restano con le
   quantità corrette a mano, si aggiungono solo i mancanti; se non c'è niente
   da aggiungere lo dice invece di fingere di aver fatto qualcosa.
2. DOSI DA LABORATORIO (richiesta Enzo): le ricette compilate in automatico
   escono con l'ingrediente base portato a 1 kg e tutto il resto riscalato —
   150 g di farina diventano 1 kg (tutto ×6,67), 500 g di riso diventano 1 kg
   (tutto ×2), lo stesso per bucatini, ragù, besciamella.
   Nuova funzione normalizza_a_un_kg in food_cost.py. REGOLA DELLA BASE: è
   l'ingrediente che PESA DI PIÙ (nella besciamella il latte, non la farina;
   negli arancini il riso, non la farina della panatura); l'elenco dei nomi
   noti serve solo a decidere quando due pesi sono quasi pari. La prima
   versione usava una priorità fissa per nome ed è stata scartata perché il
   test della besciamella l'ha smentita subito.
   Le porzioni vengono moltiplicate con lo stesso fattore (altrimenti il costo
   per porzione mentirebbe) e la ricetta porta scritto "dose_riferimento:
   1 kg di <base>" e il fattore usato.
3. LA COMPILAZIONE DI MASSA ORA PRENDE ANCHE le ricette che hanno gli
   ingredienti ma NESSUNA dose (motivo "senza_quantita"): prima venivano
   ignorate. La conferma dice quante sono per tipo e spiega la regola di 1 kg.
   Bottone rinominato "Compila ricette incomplete (dosi a 1 kg)".
Test: 6 nuovi puri sulla normalizzazione (farina 150→1000, riso 500→1000,
riso che vince sulla farina, besciamella dal latte, dosi già a 1 kg intatte,
niente da fare senza ingredienti pesabili) + 1 end-to-end sulla compilazione
di massa. Suite non-live 235 passed, build pulita.

## 25/07/2026 — Ricetta bloccata col PIN + card «Dose di oggi» per il pasticciere

Richiesta di Enzo: la ricetta ufficiale non si tocca per sbaglio con le
freccette; chi produce deve però poter dire quanto ne fa oggi (6,5 kg di
farina per i cornetti) e vedere tutte le altre dosi adeguarsi.
1. DOSI BLOCCATE (FormRicetta): una ricetta GIÀ SALVATA si apre con le
   quantità in sola lettura, unità disattivate e senza i tasti elimina/aggiungi
   ingrediente. Una banda spiega la situazione e offre "🔓 Sblocca dosi", che
   chiede il PIN AMMINISTRATORE (PinKeypad soloAdmin). Le ricette nuove restano
   libere finché non vengono salvate la prima volta.
2. CARD «DOSE DI OGGI» nel tablet (#tablet/dosi, nuovo
   tablet/DoseProduzioneView.jsx): elenco ricette con ricerca, si sceglie il
   prodotto, si indica quanto ingrediente base si usa (tasti −/+ da 48px,
   preset 0,5→20 kg, unità kg/g/l) e la lista si ricalcola in tempo reale con
   la stima dei pezzi; in fondo "Stampa la dose di oggi" per il banco di
   lavoro. NON salva e NON modifica la ricetta.
3. MOTORE: nuovo POST /food-cost/ricetta/{id}/dose-produzione, che riusa la
   stessa funzione della normalizzazione a 1 kg con un riferimento libero.
   L'ingrediente base è sempre quello che pesa di più (farina per i cornetti,
   riso per gli arancini, latte per la crema, bucatini per le frittatine).
Test: 3 nuovi (cornetti 6,5 kg → burro 1625 g e uova 26; arancini 3 kg di riso
→ ragù 1800 g; ricetta senza pesi → errore chiaro invece di numeri inventati).
COLLAUDO a video sul rig (390×844): card aperta col PIN operatore, scelta
"Baba al rum", premuto il preset 6,5 kg → "Riferimento: Farina manitoba ·
dose ×13 · circa 195 pezzi" con burro 1950 g, zucchero 1170 g, rum 2600 ml,
uova 78 pz. Zero errori JS. Suite non-live 238 passed, build pulita.

## 25/07/2026 — Ricostruito il piano esecutivo dagli audit (memory/PIANO_ESECUTIVO.md)

Riletti tutti gli AUDIT_*.md e PIANO_REFACTOR per estrarre ciò che è ancora
aperto. Nuovo documento memory/PIANO_ESECUTIVO.md: 7 tranche in ordine di
priorità, ognuna con motivo, contenuto, COLLAUDO (chi e come) e rischio.
Sintesi: (1) buchi nei registri — giorni non rilevati marcati a DB,
sanificazione che distingue "non fatto" da "non registrato", avviso sulle 500
righe della tracciabilità; (2) sicurezza — import/sync massivi sotto admin,
decisione su DELETE lotto, silenziamento alert medi; (3) sei decisioni in
attesa di Enzo (bottone Genera lotto irraggiungibile, registro HACCP nel
gemello, recall vero dagli ingredienti, segnala guasto, voce menu attrezzature,
rinomina Cella Fresca Nord); (4) stime al posto dei dati — elenco prodotti
senza peso reale, secondo motore prezzo/kg senza X24, placeholder TEMP;
(5) bonifica aspetto — stampe con blu/viola, emoji nei bottoni, Backoffice
troppo lungo; (6) refactor rimanenti col metodo fotografia-divisione-confronto;
(7) pagina "Verifica integrità gestionale" (10 controlli, ~1 giornata) DOPO le
tranche 1-2-4. In coda: cosa serve da Enzo e l'ordine che seguo se non
risponde (1 → 2 → 4).

## 25/07/2026 — Recall vero dal gemello + «Segnala guasto» su ogni frigorifero

Due delle sei decisioni approvate da Enzo, fatte e collaudate a video.
1. RECALL VERO NEL GEMELLO DIGITALE: gli "Ingredienti usati" erano testo da
   leggere; ora ognuno è un bottone. Toccando "Farina 00" si apre dentro la
   stessa scheda l'elenco dei lotti prodotti con quell'ingrediente (endpoint
   già esistente /lotti/recall/cerca, finestra 6 mesi), con prodotto, numero
   lotto, date e posizione. Collaudo sul rig: 4 ingredienti cliccabili,
   pannello "Lotti con «Farina 00» — 1 lotti coinvolti", zero errori JS.
2. SEGNALA GUASTO: nuovo componente shared/SegnalaGuasto.jsx sotto OGNI
   colonna di Temperature positive (Frigorifero) e negative (Congelatore).
   Un tocco → si scrive cosa è successo → registra l'anomalia con priorità
   alta sull'apparecchio e porta subito alla pagina Anomalie, dove il sistema
   ricalcola i lotti dentro e propone lo spostamento. Prima bisognava andare
   in Anomalie e riscrivere il nome dell'attrezzatura a mano. Collaudo: 12
   bottoni presenti (uno per frigorifero), modale corretto a 1024×768.
RISPOSTA alla domanda "Registri HACCP del mese a cosa serve": è il cruscotto
di conformità (registrazioni di oggi e del mese, lotti attivi, anomalie e
reclami aperti, avviso libretti sanitari scaduti, stampa registro per l'ASL).
Non riguarda il singolo lotto: resta da decidere se togliere il collegamento
dal gemello. Restano senza risposta: bottone "Genera Nuovo Lotto" e voce di
menu "Frigoriferi e congelatori".
Suite non-live 238 passed, build pulita.

## 25/07/2026 — «Genera Nuovo Lotto» rimosso + pagina «Frigoriferi e congelatori»

Le ultime due delle sei decisioni, rispondendo a Enzo: «a me il lotto si
genera quando produco una ricetta, che senso ha generare un lotto così?» e
«Frigoriferi e congelatori per rinominarli in un posto solo: sì».

1. FINESTRA «GENERA NUOVO LOTTO» ELIMINATA. Aveva ragione: quel modale creava
   un lotto SENZA provenienza e senza scaricare gli ingredienti — un doppione
   pericoloso del percorso vero (tablet → Registra produzione →
   `/registra-produzione-lotto`, che scala le materie prime in FIFO e eredita
   la tracciabilità). Per giunta era irraggiungibile: il bottone che la apriva
   non esisteva più. Rimossi: `ModalGeneraLotto` da
   `frontend/src/components/haccp/lotti/ModaliLotto.jsx`; in `LottiList.jsx`
   import, props `ricette`/`onGeneraLotto`, sei stati, `ricetteFiltrate`,
   `handleGenera` e il blocco JSX; in `router/pages.jsx` le due props; in
   `App.js` `ricette` dal ctx; in `hooks/useLotti.js` la funzione
   `handleGeneraLotto`. Lo stato `attrezzature` di LottiList è rimasto: serve
   ad `AzioneModal` (sposta/congela un lotto).

2. NUOVA PAGINA «FRIGORIFERI E CONGELATORI» (menu Altro → Amministrazione,
   `frontend/src/components/haccp/AttrezzatureView.jsx`). Prima i nomi si
   cambiavano SOLO cliccando sull'intestazione di una colonna dentro
   Temperature positive/negative: funzionava, ma nessuno lo avrebbe
   indovinato. Ora un elenco unico dei due gruppi, col numero accanto: il
   nome si corregge sul posto e il tasto «Salva» compare SOLO dopo che il
   testo è davvero cambiato (un tocco per sbaglio non riscrive niente), c'è
   la freccia per annullare, «Segnala guasto» su ogni riga e il cestino per
   togliere un apparecchio dismesso (cancellazione morbida: i controlli già
   registrati e i lotti restano). In fondo a ogni gruppo il campo per
   aggiungerne uno nuovo. Registrata in `config/navigation.js` (sezione
   Amministrazione), `config/pageMeta.js`, `router/pages.jsx` e
   `config/permissions.js`.

3. SICUREZZA: aggiunta/rinomina/eliminazione in `routers/attrezzature.py` ora
   sotto `require_admin` (sei endpoint). Motivo: rinominare fa un
   `update_many` sul nome in TUTTI i controlli temperatura già registrati —
   è una modifica ai registri, non una preferenza di visualizzazione. Le GET
   restano libere perché servono ai tablet di reparto per scegliere il posto.
   Il test `test_auth_permessi.py::test_endpoint_distruttivi_dichiarano_require_admin`
   li elenca uno per uno.

COLLAUDO SUL BANCO (mongomock `Gestionale_Test`, build servita su :3001,
390×844 e 768×1024): 7 apparecchi elencati (3 frigoriferi, 2 congelatori +
default); rinomina «Frigo 1 — Banco pasticceria» → «Cella 1 (prova banco)»
persistente dopo ricaricamento completo della pagina; il nome nuovo compare
davvero in Temperature positive; aggiunta (3→4) ed eliminazione (4→3)
funzionanti; scorrimento orizzontale a 390px = 0; in Tracciabilità nessuna
traccia di «Genera Nuovo Lotto»; zero errori JS. Nome di prova rimesso a
posto a fine collaudo.

Suite non-live invariata rispetto a main (238 passed; le 308 fallite sono i
test che pretendono un server live, verificate identiche con e senza le
modifiche), build frontend pulita. Collaudo per Enzo seminato in pagina
Collaudi: «Frigoriferi e congelatori: i nomi in un posto solo».

## 25/07/2026 — TRANCHE 1 (buchi nei registri) e TRANCHE 2 (sicurezza) chiuse

Enzo: «sì» al togliere «Registri HACCP del mese» dal gemello digitale, «poi
continua con i miglioramenti». Fatte le due tranche più importanti del piano.

### Gemello digitale
Tolto il bottone «Registri HACCP del mese» da `shared/SchedaLottoModal.jsx`:
quella pagina è il cruscotto di conformità di TUTTA l'attività, non del
singolo lotto. Resta nel menu HACCP. Nella scheda restano «Apri ricetta» e
«Cerca questo lotto».

### TRANCHE 1 — i buchi diventano un dato dichiarato
PROBLEMA (AUDIT_SCHEDULER_TEMPERATURE §2.3): lo scheduler vive in memoria. Se
il servizio Render resta giù tutto il giorno X e riparte il giorno X+1, il job
scrive SOLO la data odierna e il giorno X resta un buco permanente. In stampa
era già onesto ("N/D"), ma il DATO non diceva niente.

FATTO — nuovo motore `marca_giorni_non_rilevati()` in `routers/haccp_auto.py`,
richiamato dal job delle 07:00 (`job_genera_haccp_giornaliero`), quindi anche
dal catchup all'avvio. Scrive i giorni passati senza lettura come
`{"temp": None, "non_rilevato": True, "motivo": "…sistema non attivo quel
giorno"}`. Regole di prudenza scritte nel codice:
  - non tocca MAI un giorno che ha già un valore (nessuna riscrittura);
  - non marca OGGI (la giornata è ancora aperta);
  - non marca prima della PRIMA rilevazione mai fatta su quella scheda (un
    frigorifero aggiunto a luglio non ha "buchi" a gennaio);
  - non INVENTA nessuna temperatura.
Endpoint manuale `POST /haccp-auto/marca-giorni-non-rilevati` (require_admin).

SANIFICAZIONE: il giorno passato senza NESSUNA registrazione diventa "N/D".
Corretto un difetto vero trovato strada facendo: `report_haccp.load_sanificazioni`
contava come "fatta" QUALUNQUE valore non vuoto (`if value:`), quindi con
"N/D" a database avrebbe dichiarato conformi giorni in cui non era stato fatto
niente. Ora conta solo X/x/1/True. Export PDF: cella "N/D" color sabbia +
legenda «X = eseguita · N/D = nessuna registrazione · vuoto = giorno aperto».
Pagina Sanificazione: la cella N/D si vede a colpo d'occhio e resta cliccabile
per registrarla dopo.

STAMPA: `report_haccp.normalize_temp` porta avanti `non_rilevato`/`motivo`, e
`table_temperature` scrive il motivo nel tooltip della cella N/D.

REGISTRO TRACCIABILITÀ FATTURE-RICETTE (AUDIT_REGISTRI_STAMPE §5): la stampa
HTML mostrava 500 righe mentre le statistiche dichiaravano il totale vero.
Ora sopra la tabella c'è «Mostrate le prime 500 righe di N» col rimando al CSV.
Nello stesso punto, difesa contro un errore 500: `ricette.ingredienti` è una
lista di NOMI, ma un solo dizionario {nome, quantita} finito lì dentro faceva
fallire l'INTERO registro richiesto dall'ASL (`ing.lower()` su un dict) —
aggiunto `_nome_ingrediente()` nei tre punti che lo usano.

### TRANCHE 2 — sicurezza
Nove comandi di import/sincronizzazione di MASSA passati sotto `require_admin`
(ognuno riscrive cataloghi o listini interi): acquaviva import-listino-2026,
import-listino-pdf, sync-prezzi, import-alpha; listino sync-da-fatture;
sconti_merce importa-da-fatture e valorizza-da-fatture; drive_fatture sync e
riprova-errori. Più il silenziamento degli avvisi del Supervisore (i critici
restavano già non silenziabili per chiunque). Nessuno di questi è raggiungibile
dalle card del tablet: i dipendenti non perdono niente.
`test_endpoint_distruttivi_dichiarano_require_admin` li elenca uno per uno.

RESTA APERTO (serve una risposta di Enzo): `DELETE /lotti/{id}` deve passare
sotto il PIN del titolare o restare libero?

### Collaudo
11 test nuovi in `backend/tests/test_registri_buchi.py` (marcatura, idempotenza,
oggi escluso, scheda mai usata, congelatori, sanificazione, N/D non conta come
fatta, motivo in stampa, avviso di troncamento).
Il banco di prova (`run_locale_test.py`) ora semina anche i registri HACCP con
un BUCO voluto (letture a −6 e −1 giorno): prima non c'era niente da
collaudare. Sul banco: 12 marcature frigoriferi + 8 congelatori + 1 scheda
sanificazione al primo giro, zero al secondo; report HACCP con 20 celle N/D che
dichiarano il motivo; export sanificazione 12 N/D e 6 X con legenda; pagina
Sanificazione verificata a video; `listino/sync-da-fatture` e
`sconti-merce/importa-da-fatture` senza accesso rispondono 401; zero errori JS.

## 25/07/2026 — «Il dipendente solo produce e legge le ricette»: tutto sotto PIN

Enzo: «si, il dipendente deve solo produrre vedere ricette poi tutto il resto
lo guardo io lo utilizzo io metti tutto sotto pin».

1. TABLET — le card restano tutte visibili (Enzo le usa dal tablet col SUO
   PIN), ma Magazzino, Lavagna richieste e Ordini sono marcate `soloAdmin`:
   hanno il lucchetto «Solo titolare», il tastierino dice «Riservato al
   titolare: serve il PIN da amministratore» e un PIN dipendente riceve «PIN
   non autorizzato». Il controllo non sta solo nel tastierino: `KioskLayout`
   respinge anche chi arriva col link diretto (`#tablet/ordini`) o chi cambia
   reparto con una sessione da dipendente ancora valida.
   Restano libere per i dipendenti: Pasticceria, Rosticceria, Bar, Produzioni
   al banco, Dose di oggi.

2. «VEDERE LE RICETTE» — nuovo `tablet/SchedaRicettaKiosk.jsx`: scheda in SOLA
   LETTURA (ingredienti con le dosi, resa, reparto, conservazione, allergeni,
   note) aperta dal bottone «Ricetta» su ogni card prodotto. Corregge anche un
   percorso rotto: quel bottone era una matita che portava a `#ricette`, cioè
   al Backoffice del gestionale — da quando il gestionale è riservato al
   titolare, per un dipendente finiva contro il tastierino. In fondo alla
   scheda c'è scritto dove si cambia la quantità del giorno (card «Dose di
   oggi») e che per modificare la ricetta serve il PIN del titolare.
   Nella card testuale il bottone sta DENTRO il piede, in riga con la scritta:
   messo in assoluto copriva «N già in frigo/abbattitore» (visto a video).

3. BACKEND — `DELETE /lotti/{id}` e `DELETE /lotti-fornitori/{id}` sotto
   `require_admin`: cancellare un lotto è la cosa più definitiva che si possa
   fare alla tracciabilità. Aggiunti all'elenco di
   `test_endpoint_distruttivi_dichiarano_require_admin`.

COLLAUDO SUL BANCO (1024×900): tre card col lucchetto; PIN dipendente su
Ordini → «PIN non autorizzato»; PIN dipendente su Pasticceria → entra; link
diretto `#tablet/ordini` con sessione dipendente → rimandato alle card; PIN
amministratore su Ordini → entra; bottone «Ricetta» presente, scheda che si
apre con ingredienti e allergeni e rimanda a «Dose di oggi»; zero errori JS.

## 25/07/2026 — AUDIT END-TO-END completo (metodo audit-codice)

Enzo: «fai un audit completo con collaudo per capire errori reali live end to
end e debug del codice». Documento completo: `memory/AUDIT_E2E_LIVE.md`.

METODO: (1) fase meccanica — pyflakes su tutto il server, confronto delle 456
chiamate del frontend con le 678 rotte reali, collection con nomi quasi
uguali, chiavi duplicate nei filtri Mongo, componenti usati in pagina ma mai
importati; (2) collaudo vero col browser su TUTTE LE 43 PAGINE con PIN
amministratore, registrando errori JS, chiamate fallite, scroll orizzontale a
390px e pagine vuote; (3) stesso giro rifatto dopo le correzioni.
LIMITE DICHIARATO: da questa sandbox internet è bloccato (403 del proxy),
quindi non si è potuto interrogare Render: il collaudo gira sullo STESSO
codice del server con database finto. La prova sui dati veri resta a Enzo.

SEI DIFETTI VERI TROVATI E CORRETTI:
1. GRAVE — `POST /lotti/{id}/recupera` usava `operation_id` senza dichiararlo:
   NameError → errore 500 a OGNI tocco. Il bottone «Recupera» del gemello
   digitale non ha mai funzionato. Aggiunto il parametro + salvataggio del
   risultato per l'idempotenza. Collaudato: 200, quantità scalata, doppio
   invio senza secondo scarico.
2. MEDIO — `ricalcola-scadenze`: il gestore dell'errore usava `logger`
   (qui è `_LOG_INIT`) e `lp` (la variabile è `lotto`): un solo lotto
   problematico faceva fallire con 500 tutto il ricalcolo invece di saltarlo.
3. GRAVE — `fornitori/FattureList.jsx` usava `<X>` senza importarla:
   schermata bianca aprendo l'anteprima di una fattura. La compilazione NON
   lo segnala — è la quarta volta che questa classe di errore colpisce questo
   progetto, per questo l'audit ora ha un controllo dedicato.
4. MEDIO — `DuplicatiMergePanel.jsx` usava `<Ban>` senza importarla:
   schermata bianca appena compare un fornitore escluso fra i duplicati.
5. MEDIO — `CorrispettiviView` caricava i 5 riquadri con `Promise.all`: se UNO
   solo non aveva dati si perdevano tutti e cinque. Passato a
   `Promise.allSettled` + messaggio che dice cosa fare.
6. TECNICO — `{"$not": {"$regex": ..., "$options": "i"}}` non è eseguibile dal
   banco di prova: `GET /prodotti-master` rispondeva 500 e la pagina più usata
   (Acquisti) restava fuori da ogni collaudo automatico. Sostituito con `(?i)`
   dentro il pattern (identico per MongoDB, funziona ovunque), 5 punti fra
   `prodotti_master.py` e `controllo_dati.py`.

RISULTATO DOPO LE CORREZIONI: 43 pagine su 43 senza un solo errore
JavaScript, zero scroll orizzontale a 390px, nessuna pagina vuota, nessun
bottone che punta a una rotta inesistente, nessuna collection con nome
quasi-uguale, nessuna chiave duplicata nei filtri Mongo.

DUE COSE CHE ASPETTANO UNA RISPOSTA DI ENZO (scritte nel documento):
- i PIN dei dipendenti sono salvati IN CHIARO nel database accanto a quello
  cifrato (serve per «ho dimenticato il PIN», ma annulla la cifratura):
  proposta alternativa «Reimposta PIN»;
- `GET /tablet-operatori/nuovi-dipendenti` restituisce sempre lista vuota: i
  bottoni «Abilita dipendente proposto» e «Ignora» non possono mai comparire.

SETTIMO DIFETTO, trovato mentre verificavo l'audit stesso — nel COLLAUDO, non
nell'app: `test_fifo_consuma_il_lotto_piu_vecchio` seminava due lotti con date
scritte a mano (01/06/2026 e 01/07/2026). Con la regola di Enzo del 23/07/2026
(si parte dal più vecchio DEGLI ULTIMI 60 GIORNI) il lotto "vecchio" è uscito
dalla finestra col passare dei giorni e il test ha iniziato a fallire da solo,
senza che nessuno toccasse il codice. Tradotto: da qualche giorno nessuno
controllava più la regola più importante dell'app. Tutte le date dei lotti nei
test sono ora relative a OGGI, e ho aggiunto il test che mancava
(`test_fifo_lotto_oltre_60_giorni_va_in_riserva`): un lotto di 200 giorni fa
non deve essere toccato finché c'è quello recente. Il comportamento dell'app
era ed è corretto: era il collaudo a essersi guastato.

## 25/07/2026 — PIN: rifatta la gestione (era il buco più serio dell'audit)

Enzo: «procedi per i pin, si usa la soluzione migliore». Entrando nel codice i
problemi erano TRE, non uno.

1. Il PIN di ogni dipendente era salvato IN CHIARO nel database (`pin_chiaro`)
   accanto a quello cifrato, e `POST /tablet-operatori/pin-operatori` li
   restituiva tutti all'amministratore: la cifratura non proteggeva niente.
2. I PIN erano scritti anche NEL CODICE (`DIPENDENTI_DEFAULT`), quindi finiti
   nella cronologia del repository.
3. IL PIÙ SERIO — cambiare il PIN a un dipendente NON revocava il vecchio: a
   ogni riavvio `seed_operatori()` rimetteva il PIN di partenza dentro
   `pin_chiaro`, e siccome `login_pin` controllava PRIMA quello, il PIN
   vecchio tornava valido. Una revoca che non revocava.

SOLUZIONE (tablet_operatori.py, auth.py, ordini_fornitori.py):
- verifica sempre con bcrypt; per non provarlo su tutti a ogni accesso c'è
  `pin_lookup` = HMAC-SHA256(segreto applicazione, pin), indicizzabile e non
  reversibile senza il segreto (che sta su Render, non nel database). Dopo la
  ricerca il PIN viene comunque verificato con bcrypt: se l'impronta trovasse
  la riga sbagliata, l'accesso verrebbe rifiutato lo stesso.
- `pin_chiaro` non si scrive più e viene CANCELLATO all'avvio da tutti i
  documenti, DOPO aver calcolato l'impronta da quello vecchio: nessuno resta
  fuori, chi entrava prima entra anche dopo.
- niente PIN nel codice: `NOMI_DEFAULT` ha solo i nomi; alla prima
  installazione i dipendenti nascono senza PIN e l'amministratore prende il
  PIN da `ADMIN_PIN_INIZIALE` (env Render) oppure uno generato a caso scritto
  UNA volta nel log.
- `seed_operatori()` non riscrive più niente su un database già popolato.
- nuovo `POST /tablet-operatori/{id}/reimposta-pin` (require_admin): rifiuta
  un PIN già di un altro dipendente e revoca subito il precedente.
- `pin-operatori` non restituisce più PIN: solo nome, ruolo e
  `pin_impostato` true/false, più il messaggio che spiega cosa fare.
- la domanda «questo PIN è di un amministratore?» era ripetuta in TRE file
  (auth.require_admin, auth.login_pin_jwt, ordini_fornitori._richiedi_admin),
  tutti e tre leggendo il PIN in chiaro: ora c'è un punto solo,
  `pin_amministratore_valido()`.
- il banco di prova (`run_locale_test.py`) semina anche lui con hash+impronta,
  così collauda il percorso VERO.
- frontend `ImpostazioniPersonaleView`: «Mostra PIN» → «Gestisci PIN», niente
  PIN a video, badge «PIN impostato» / «PIN da assegnare», «Reimposta PIN».

COLLAUDO: 9 test nuovi in `tests/test_pin_sicurezza.py` (fra cui
`test_il_riavvio_non_resuscita_il_pin_vecchio`, che copre esattamente il
difetto 3) + prova sul banco via API: accesso admin e dipendente OK, PIN
sbagliato 401, gestione PIN senza nessun PIN in risposta, PIN reimpostato →
vecchio 401 e nuovo OK, PIN duplicato rifiutato, dipendente che prova a
reimpostare → 403. Pagina Personale verificata a video, zero errori JS.

DA DIRE A ENZO: i PIN attuali NON cambiano, cambia solo che non sono più
leggibili. Conviene però che reimposti il PIN da amministratore, visto che
quello attuale è passato dalla cronologia del repository.

## 25/08/2026 — Acquaviva, SAIMA e MEPA di nuovo visibili e raggiungibili

SEGNALAZIONE: i tre cataloghi risultavano assenti nell'app. I componenti, i
router backend e i dati erano presenti; il difetto era nella navigazione. I
pulsanti di Acquisti aprivano `#prodotti/<fornitore>`, ma il contenitore
ignorava il secondo segmento e mostrava sempre il Listino. Inoltre dalla Home
il percorso era nascosto dentro «Ufficio e archivio» e chiamato «Vendita
banco», nome che non descriveva i cataloghi.

CORREZIONE:
- `ProdottiHubView` risolve e mantiene i deep-link
  `#prodotti/acquaviva`, `#prodotti/saima` e `#prodotti/mepa`, compresi
  Indietro/Avanti e refresh;
- le fonti catalogo aggiunte dinamicamente non ricadono più per errore su
  Acquaviva dopo il caricamento di `/api/fonti-catalogo`;
- la Home mostra tre accessi diretti, uno per Acquaviva, SAIMA e MEPA;
- il percorso è ora chiamato «Listini e cataloghi» / «Prodotti e cataloghi»;
- schede e sotto-schede espongono `tablist`, `tab`, `tabpanel` e
  `aria-selected`; guida integrata aggiornata con i nomi e i percorsi reali.

VERIFICHE PRE-RILASCIO: test React dei tre deep-link, delle tre card Home e di
Indietro/Avanti; test navigazione e fonti dinamiche; suite frontend completa;
build di produzione; compilazione e import-check di tutti i router backend.
GitHub Actions non ha eseguito alcuno step perché i 3.000 minuti Pro risultano
esauriti e il budget Actions è a 0 con blocco oltre soglia: è un limite account,
non un errore del codice. Nessun budget è stato modificato.

## 31/08/2026 — Quattro ricettari Excel unificati e modificabili

FONTI: `Ricettario_Ceraldi completo.xlsx`, `Ricettario_Ceraldi.xlsx`,
`Ricettario_Completo_v6.xlsx`, `ricette da importare.xlsx`. Lo script
`backend/scripts/genera_ricettario_excel.py` legge tutte le schede senza
modificare gli originali, conserva SHA-256/foglio/riga e genera il bundle
versionato `backend/data/ricettario_excel_ceraldi.json`.

RISULTATO DATI: 598 record estratti, 574 nomi unici dopo deduplicazione esatta,
535 ricette con ingredienti e 306 con modo di preparazione. L'import API
`POST /api/ricette/importa-excel` supporta anteprima e applicazione, crea un
backup prima delle scritture ed è idempotente. Foto e correzioni manuali già
presenti non vengono sovrascritte; ingredienti/dosi riempiono solo ricette
vuote o provenienti da vecchi import automatici.

INTERFACCIA: sulle card ci sono ora `×` con conferma e copia recuperabile nel
cestino, più `Modifica nome e ingredienti` direttamente dalla card. Tolte le
diciture «Ricetta importata»/«Base importata»: la provenienza resta visibile
nella scheda, ma non separa il ricettario operativo.

VERIFICHE E PRODUZIONE: 54 test backend pertinenti passati in due processi
isolati (per evitare il noto test legacy dipendente dal loop asyncio),
compilazione Python e build frontend di produzione riuscite. PR #175 unita in
`main` con commit `b4dbc2a0dc28cbe223ad6198fc27296d6ef9ba07` e pubblicata su
Render. L'import autenticato in produzione ha creato 485 ricette e ne ha
arricchite 89, per un totale di 574; prima delle scritture e' stato creato il
backup. La seconda esecuzione ha restituito 0 create, 0 aggiornate e 574
invariate, confermando l'idempotenza sul database live.

La verifica ingredienti `Posso produrla?`, gia' presente nel modulo ricettari,
e' ora collegata anche al ricettario operativo `#ricette`: dalla card controlla
le disponibilita' ricavate dagli acquisti/fatture, distingue disponibili,
sostituzioni prudenti da confermare e mancanti acquistabili, senza applicare
automaticamente sostituzioni.

## 15/09/2026 — Audit-codice: doppio tap negli ordini, bevande costate a kg in 3 motori su 4

Enzo: «/audit-codice». Fase meccanica (compileall, pyflakes, confronto 336
chiamate frontend uniche vs 704 rotte backend, nomi collezione quasi-uguali,
scansione di tutti i 37 endpoint `DELETE` contro `require_admin`) + tre
revisori paralleli in sola lettura (ordini/riordini, prezzi/consumi/unità,
frontend). Nessun `NameError`/chiave duplicata nei filtri Mongo (già pulito
dagli audit precedenti); 11 dei 12 candidati "chiamata orfana" erano falsi
positivi del mio stesso script di confronto (querystring concatenate,
segmenti dinamici che risolvono comunque a rotte reali).

**GRAVE 1 — doppio tap su "Crea bozze" duplicava l'ordine fornitore.**
`POST /ordini-fornitori` (`backend/routers/ordini_fornitori.py::crea_ordine`)
creava incondizionatamente un nuovo documento per `source` diverso da
"catalogo*" (cioè `ordini_app`/`manuale`/`tracciabilita`), senza alcuna
protezione — a differenza di `invia_ordine_confermato`, già atomico. Il
bottone "Crea bozze" del Carrello (`OrdiniView.jsx`) non aveva nessuno stato
"in corso": un doppio tocco su tablet, comune, o un retry di rete creava due
bozze identiche verso lo stesso fornitore. Fix: `operation_id` opzionale nel
payload, stesso pattern `operazioni_idempotenti` già usato in
`lotti_produzione.py` (insert atomico, `DuplicateKeyError` → risultato
cache); il frontend genera un id per invio e lo passa, più uno stato
`creandoBozze` che disabilita il bottone durante la richiesta. Test:
`tests/test_ordini_fornitori_idempotenza.py` (3 nuovi).
*Aperto, non corretto in questo giro* (rischio più basso, verificato ma non
un caso osservato sui dati reali): il ramo di merge per `source="catalogo*"`
resta un find-poi-update non atomico (race stretta, un solo operatore in
pratica); il match fornitore in `riconcilia_fattura_con_ordine` per prefisso
di 10 caratteri è strutturalmente permissivo se due fornitori condividono lo
stesso prefisso — da verificare sui nomi reali quando serve.

**GRAVE 2 — il costo delle bevande andava a kg in 3 motori di scrittura su 4.**
La regola di Enzo (bevande/alcolici SEMPRE a bottiglia/cartone, mai a kg) era
applicata solo in `GET /food-cost/calcola/{id}` (sola lettura). I tre
endpoint che scrivono davvero `ricetta.costo_totale`/`costo_porzione` —
`POST /aggiorna-ingredienti-ricetta` (il salvataggio reale da
`TabIngredienti.jsx`, usato ad ogni modifica ricetta), `POST
/ricalcola-costi-tutte-ricette` e `POST /auto-mappa-ingredienti` —
convertivano comunque la quantità in kg-equivalenti e moltiplicavano per
`prezzo_kg`, anche per un rum o un amaro. Il numero "ufficiale" della
ricetta (usato dalla scheda stampabile HACCP `GET /ricette/{id}/pdf-scheda`
e dalla sincronizzazione costi/margini di `prodotti_vendita`, 449 prodotti)
era quindi sbagliato, mentre la pagina di calcolo isolata l'avrebbe mostrato
corretto o bloccato con "bevanda senza prezzo a confezione" — due pagine
della stessa app con due costi diversi per la stessa ricetta. Fix: nuova
`costo_ingrediente_da_dizionario()` (stessa logica di `/calcola/{id}`, unico
punto ora condiviso), usata dai tre endpoint; le query al dizionario
prodotti includono ora anche i prodotti prezzati SOLO a `costo_per_pezzo`
(prima restavano "non trovati" per una bevanda senza `prezzo_kg`); un
`prezzo_kg` già salvato in passato per una bevanda (dato dal bug) non viene
più preso per buono senza riverificare la categoria. Test:
`tests/test_food_cost_bevande_scritture.py` (5 nuovi).
Trovato e rimosso nello stesso file: `GET /food-cost/stampa-ricetta/{id}`,
un secondo motore di stampa scheda ricetta con lo stesso bug, mai chiamato
da nessuna pagina del frontend (la stampa reale passa da
`ricette.py::pdf-scheda`) — codice morto, contrario alla regola "un solo
sistema per funzione": eliminato invece di corretto.

**MEDIO — `stampanti.py` senza `require_admin` su nessun endpoint.**
"stampanti" è esplicitamente elencata in `frontend/src/config/permissions.js`
come area riservata all'amministratore, col commento "la sicurezza vera è
require_admin nel backend" — ma il router non aveva alcuna protezione: un
token dipendente poteva creare/modificare/eliminare una stampante via API,
bypassando il tastierino. Aggiunto `require_admin` su `POST`/`PUT`/`DELETE`
(stesso schema di `attrezzature.py`: la lettura resta libera per i tablet di
reparto). Aggiunto ai path verificati da
`test_endpoint_distruttivi_dichiarano_require_admin`.

**MEDIO — `Promise.all` fragile in "Colazione Acquaviva".**
`ColazioneAcquavivaView.jsx::carica()` caricava 4 pannelli indipendenti
(prodotti disponibili, preset stagionali, più usati, preferiti) con
`Promise.all`: un solo endpoint a 500 svuotava l'intera pagina usata ogni
mattina in pasticceria per avviare la produzione. Passato a
`Promise.allSettled` con fallback per pannello e un avviso di quanti
pannelli non si sono caricati, stesso schema già usato in `CorrispettiviView`.

**BASSO — chiamata morta in `App.js`.** `startImport()` chiamava
`GET /fatture/stato-sync` (nessuna rotta simile è mai esistita) per
"svegliare" il backend prima di un import massivo; l'errore veniva ignorato
in silenzio (`.catch(() => {})`), quindi nessun sintomo visibile, solo un
tentativo di sveglia che falliva sempre col 404. Puntata a `GET /health`
(rotta pubblica reale, stesso identico scopo).

**Rimandato, non nuovo**: l'emoji ✏️ aggiunta in `BackofficeView.jsx:276`
(commit #185) estende un problema già in coda per la bonifica-design
dedicata (`AUDIT_VISIVO_MOBILE_TABLET.md`, punto 1) — non corretto qui per
non frammentare quel lavoro già pianificato.

VERIFICA: `python -m compileall` + `pyflakes` puliti; controllo AST dedicato
per chiavi duplicate nei filtri Mongo su tutto il backend (zero); 91
collezioni MongoDB censite, nessun doppione/typo; `pytest` backend 375
passed (+8 nuovi) / 334 skipped (collaudi HTTP live, serve
`REACT_APP_BACKEND_URL`); `npm run build` frontend pulita; suite frontend
49/49 verde.

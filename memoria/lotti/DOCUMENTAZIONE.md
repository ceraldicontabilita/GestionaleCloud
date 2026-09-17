# Documentazione del progetto — Lotti (HACCP · Ordini · Tracciabilità)

> Ceraldi Group S.r.l. — Pasticceria e Rosticceria, Napoli
> Questo file spiega com'è strutturato il progetto, quali pagine contiene, cosa fa ogni
> sezione, come funziona l'import delle fatture e cosa controlla il sistema quando si fa
> un ordine sopra la media settimanale (e il rapporto con i corrispettivi).

---

## 1. Panoramica e architettura

**Lotti** è l'applicazione web per la **tracciabilità HACCP**, la **gestione ordini** e il
**catalogo prodotti/fornitori** della pasticceria-rosticceria. Ha un archivio
dedicato e non condivide il database con gli altri gestionali aziendali.

- **Backend**: FastAPI (Python). Tutti gli endpoint hanno prefisso `/api`.
  Online su `https://lotti-backend-f2fg.onrender.com`.
- **Frontend**: React (CRACO). Online su `https://lotti-frontend.onrender.com`.
  Variabile `REACT_APP_BACKEND_URL` per puntare al backend.
- **Database**: Supabase/PostgreSQL dedicato esclusivamente a Lotti, separato da GestionaleCloud.
  Nel codice l'accesso resta `from db import database as db`: lo strato compatibile conserva
  le API storiche e persiste i documenti tramite RPC protette (`SUPABASE_URL`,
  `SUPABASE_ANON_KEY`, `LOTTI_DB_SECRET`, `DB_NAME`). Le credenziali arrivano
  esclusivamente dalle variabili d'ambiente e non sono scritte nel codice.
- **Deploy**: Render, branch `main`, auto-deploy ad ogni push. Piano free → "cold start"
  di qualche decina di secondi alla prima richiesta dopo inattività.

Punto importante sull'architettura dati: **Lotti è indipendente da GestionaleCloud**.
Le fatture vengono importate nelle collezioni proprie di Lotti tramite i flussi
esplicitamente configurati; non esiste alcuna lettura diretta del database del Gestionale.

### Le collezioni logiche principali
- `fatture` — fatture elaborate dentro Lotti.
- `fornitori`, `fornitori_qualifica` — anagrafica e qualifica HACCP dei fornitori.
- `prodotti_master` — **catalogo prodotti unificato** (aggrega più fonti, vedi §4).
- `lotti`, `lotti_fornitori`, `lotti_produzione` — tracciabilità (vedi §9).
- `ricette` — ricettario unificato (109 ricette).
- `magazzino_bar_prodotti`, `magazzino_bar_movimenti` — magazzino/giacenze bar.
- `nome_mapping` / `dizionario_prodotti` — normalizzazione nomi prodotto.
- `anomalie`, `alert_*`, `impostazioni` — controlli, avvisi, configurazione.

---

## 2. Struttura del repository

```
Lotti/
├── backend/
│   ├── server.py                # app FastAPI; registra tutti i router sotto /api
│   ├── db.py                    # selezione persistenza Supabase/Mongo per test locali
│   ├── supabase_document_store.py # compatibilità API e persistenza JSONB protetta
│   ├── azienda.py               # dati azienda centralizzati (fatturazione elettronica)
│   ├── dizionario_categorie.py  # dizionario di classificazione merceologica (vedi §6)
│   ├── scheduler.py             # job pianificati (alert scadenze, ecc.)
│   └── routers/                 # ~70 moduli, uno per area funzionale (vedi §4)
└── frontend/
    ├── tailwind.config.js       # tema (palette beige/sage centralizzata)
    └── src/
        ├── App.js               # navigazione + routing delle pagine
        ├── index.css            # variabili CSS del tema
        ├── theme.js             # palette tema scuro
        └── components/haccp/    # tutte le viste/pagine (.jsx)
    └── public/
        └── ordini-app.html      # web-app Ordini a pagina singola (kiosk Bar)
```

---

## 3. Le pagine dell'applicazione (frontend)

La navigazione è definita in `frontend/src/App.js`. Le pagine sono raggruppate così.

### 3.1 Sezioni principali (barra in alto)
- **Dashboard** (`DashboardView`) — quadro generale: stato, indicatori, scorciatoie.
- **Ricette** (`RicetteView`) — ricettario, ingredienti, food-cost.
- **Lotti** (`LottiList`) — registro lotti e tracciabilità.
- **Ordini** (`OrdiniSmartView`) — catalogo ordinabile per categoria, carrello, invio
  ordine al fornitore. Vedi anche la web-app kiosk in §3.4.
- **Fornitori** (`FornitoriList`) — anagrafica fornitori, qualifica HACCP, schede.

### 3.2 Gestione e dati (menu "Altro")
- **Prodotti** (`SchedaProdottoView` / `GestioneProdottiView`) — schede prodotto, reparti.
- **Listino prezzi** (`ListinoView`) — listino merci, generazione PDF intestato al
  fornitore, invio.
- **Magazzino prodotti** (`MagazzinoBarView`) — giacenze, carichi/scarichi.
- **Sconti** (`ScontiMerceView`) — sconti/omaggi merce.
- **Backoffice** (`BackofficeView`) — funzioni amministrative.
- **Controllo Dati** (`ControlloDatiView`) — verifica integrità/coerenza dei dati.
- **Storico** (`StoricoProduzioniView`) — storico produzioni.
- **Allergeni** (`RegistroAllergeniView`) — registro allergeni.
- **Schede Tecniche** (`SchedeTecnicheView`) — schede tecniche prodotti.
- **Comparatore prezzi** (`ComparatorePrezziView`) — confronto prezzi tra fornitori.
- **Catalogo unificato** (`CatalogoUnificatoView`) — vista del catalogo `prodotti_master`.
- **Impostazioni / Personale** (`ImpostazioniPersonaleView`) — dati azienda
  (fatturazione elettronica, codice destinatario SDI), gestione personale.
- **Backup** (`BackupView`) — backup/ripristino dati.

### 3.3 Modulo HACCP (registri di conformità)
- **Disinfestazione** (`DisinfestazioneView`)
- **Sanificazione** (`SanificazioneView`)
- **Temperature Negative / Positive** (`temp_negative` / `temp_positive`)
- **Olio Frittura** (`ControlloOlioView`)
- **Temperature Cottura** (`TemperatureCotturaView`)
- **Ricezione Merce** (`RicezioneMerceView`) — accettazione forniture.
- **Anomalie** — registro anomalie e azioni correttive.
- **Manuale HACCP** / **Registro HACCP** — manuale e registro firmabile/esportabile.

Questi sono i classici **registri di autocontrollo**: ogni pagina permette di registrare
una rilevazione (data/ora/valore/operatore), e i dati alimentano i controlli automatici
e i report (vedi §8).

### 3.4 Modalità Tablet / Kiosk (per il personale in laboratorio/bar)
Accessibile via hash `#tablet/...` (`App.js`). PIN per operatore.
- **Reparti di produzione** (`TabletView`) — registrazione lotti/produzioni del reparto.
- **Vendita al banco** (`VenditaBancoView`).
- **Bar / Magazzino** (`MagazzinoBarView`).

### 3.5 Web-app Ordini (kiosk) — `frontend/public/ordini-app.html`
È la schermata "Ceraldi Ordini" (catalogo a chip per settore Bar/Pasticceria/Cucina e
sotto-categorie, carrello, storico, report). È una pagina **vanilla-JS autonoma** che
legge il catalogo dal backend (`GET /api/prodotti-master/catalogo-app`) e lo affianca a un
listino base interno. Ogni carta prodotto ha: aggiungi al carrello, preferito ⭐,
scorte basse ⚠, modifica ✎ e **escludi dalla visualizzazione 🚫** (vedi §6).

---

## 4. I moduli backend (router)

Tutti registrati in `backend/server.py` sotto `/api`. Raggruppati per area:

**Fatture / Import**
- `fatture` — CRUD fatture, **import XML**, visualizzazione HTML, sync dal Gestionale.
- `pec_import` (sync-gestionale) — legge `invoices` dal Gestionale e le porta in HACCP.
- `xml_helpers` — parsing dei campi della fattura elettronica XML.
- `sconti_merce` — sconti/omaggi rilevati.

**Catalogo / Prodotti / Prezzi**
- `prodotti_master` — catalogo unificato (aggrega 6 fonti), classificazione, catalogo-app,
  riclassifica, escludi. Usa `dizionario_categorie`.
- `prodotti_canonici`, `prodotti_vendita`, `normalizzazione` — nomi canonici e mapping.
- `listino`, `mepa`, `acquaviva`, `saima`, `saima_ricettari` — listini e cataloghi fornitori.
- `comparatore` (via `analisi_ordini` / viste) — confronto prezzi.

**Ordini**
- `ordini_app` — backend della web-app Ordini (catalogo, storico, invio).
- `ordini_fornitori` — ordini ai fornitori (CRUD, sostituzione prodotti).
- `email_ordini` — invio email ordine/listino al fornitore (PDF intestato Ceraldi).
- `analisi_ordini` — **analisi cadenze/quantità e verifica anomalie del carrello** (§7).

**Magazzino / Tracciabilità**
- `magazzino_bar`, `magazzino_unificato` — giacenze e movimenti.
- `lotti`, `lotti_fornitori`, `lotti_produzione` — tracciabilità lotti (§9).
- `ricezione_merce`, `reclami_fornitori` — accettazione e reclami.

**Ricette / Produzione**
- `ricette`, `aggiornamento_ricette`, `ingredienti`, `materie_prime`, `food_cost`,
  `produzione`, `produzioni`, `produzione_mattina`, `colazione`, `vendita_banco`.

**Fornitori**
- `fornitori`, `fornitori_anagrafica`, `fornitori_dedup`, `fornitori_schede`,
  `fornitori_qualifica`.

**HACCP**
- `disinfestazione`, `sanificazione`, `temperature_negative`, `temperature_positive`,
  `controllo_olio`, `temperature_cottura`, `anomalie`, `shelf_life`,
  `haccp_periodi_speciali`, `manuale_haccp`, `haccp_auto`, `haccp_manuale_auto`,
  `report_haccp`, `chiusure`, `etichette`, `schede_tecniche`, `unita_misura`.

**Sistema / Operatività**
- `scheduler` — job pianificati. `supervisor_operativo` — quadro controlli/alert (§8).
- `controllo_dati`, `diagnostic`, `backup`, `pipeline`, `indici`, `log_attivita`,
  `tablet_operatori`, `task_dipendenti`, `costi_giornalieri`, `attrezzature`,
  `whatsapp`, `utils`, `azienda`.

---

## 5. Logica dell'import fatture — cosa succede quando si importano

Esistono **due percorsi**:

### A) Import manuale da file XML — `POST /api/fatture/importa-xml`
Si caricano uno o più file XML (anche dentro uno zip). Per ogni fattura:
1. Si fa il **parsing** della fattura elettronica (nodo `CedentePrestatore` per i dati
   fornitore: denominazione, P.IVA; numero fattura, data, righe/prodotti).
2. **Filtro fornitori esclusi**: se il fornitore è marcato come escluso, la fattura viene
   saltata.
3. La fattura elaborata viene salvata in **`fatture`**.
4. **Carico magazzino bar**: `_carico_magazzino_bar_da_fattura` crea/aggiorna i prodotti in
   `magazzino_bar_prodotti`, aggiorna lo stock e registra un movimento in
   `magazzino_bar_movimenti` (nota "Carico da fattura …").
5. I prodotti vengono **classificati** in categoria merceologica (vedi §6) e
   **normalizzati** (nome canonico).
6. L'avanzamento dell'import è tracciato in `import_jobs` (per la barra di progresso).

### B) Sync dal Gestionale (fatture già scaricate dalla PEC)
`POST /api/sync-gestionale/sync-da-gestionale` (e `POST /api/fatture/sincronizza-da-gestionale`).
1. Legge le fatture dalla collezione **`invoices`** (popolata dal Gestionale dalla PEC,
   casella `fatturazioneceraldi@pec.it`).
2. **Deduplicazione**: salta se la coppia *(numero fattura + fornitore)* è già presente in
   `fatture`.
3. Per ogni nuova fattura popola le collezioni HACCP: `fatture`, `fornitori`,
   `dizionario_prodotti`, `lotti_fornitori`, `prodotti_vendita`.

### Effetti complessivi dell'import
Quando una fattura entra nel sistema:
- **Anagrafica fornitore** creata/aggiornata. L'email del fornitore viene recuperata
  **solo** dal nodo `CedentePrestatore`; un flag `email_verificata` impedisce di
  sovrascrivere un'email già verificata a mano.
- **Prodotti** confluiscono nel catalogo unificato `prodotti_master`, con categoria
  merceologica assegnata dal classificatore e nome canonico normalizzato.
- **Lotti fornitore** creati per la tracciabilità (data fattura = riferimento per il FIFO,
  vedi §9).
- **Prezzi**: il prezzo e il flag "già acquistato" derivano **solo** da acquisti reali su
  fattura con match affidabile (nome ufficiale o codice articolo). I prodotti mai
  acquistati restano ordinabili ma senza prezzo.
- **Giacenze** aggiornate dove pertinente (magazzino bar).

> Regola di pagamento (coerente con gli altri gestionali): il metodo di pagamento del
> fornitore proviene dall'anagrafica fornitore, **non** dall'XML della fattura.

---

## 6. Catalogo e classificazione prodotti

Il catalogo unificato `prodotti_master` aggrega più fonti dati e assegna a ogni prodotto
una **categoria merceologica** (`categoria_merce`): *Pasticceria, Salato/Gastronomia,
Bevande e Bottiglie, Caffetteria, Attrezzature, Altro*.

### Il dizionario di classificazione — `backend/dizionario_categorie.py`
È la sorgente unica ed **estensibile** dei termini reali con cui riconoscere un prodotto:
- **Attrezzature / Vetreria** (priorità assoluta): bicchiere = calice = tumbler =
  old fashioned = flûte = ballon = snifter = highball = boccale … e attrezzatura bar
  (shaker, jigger, apribottiglie, caraffa, decanter…).
- **Bevande** con i marchi: whisky (Jack Daniel's, Johnnie Walker etichetta rossa/nera/
  blu/oro, Jameson, Chivas, Glenfiddich…), rum, gin, vodka, grappa, brandy/cognac,
  tequila, liquori/amari, birre, bibite, acqua, succhi, vino.

**Regola di priorità**: la vetreria vince sempre. Esempio reale: *"Conf 6 Calici Riserva
Grappa"* → **Attrezzature/Bicchieri** (è un set di calici, non grappa). Il dizionario usa il
match a parola intera per evitare falsi positivi (es. *"Coppa di Parma"* non è vetreria).

Per estendere la classificazione basta aggiungere termini alle liste nel file.

### Endpoint correlati
- `GET /api/prodotti-master/catalogo-app` — catalogo per la web-app Ordini (esclude
  "Altro" e i prodotti esclusi).
- `POST /api/prodotti-master/riclassifica` — ri-applica il dizionario a **tutti** i prodotti
  esistenti (es. sposta i calici già finiti in Bevande verso Attrezzature). Da lanciare una
  volta dopo aver aggiornato il dizionario.
- `POST /api/prodotti-master/escludi` — esclude (o ripristina) un prodotto dalla
  visualizzazione. L'aggancio è per **nome canonico** (gli id di `catalogo-app` non sono
  stabili). Il campo `escluso` viene filtrato in tutti gli endpoint del catalogo.

### Escludi dalla visualizzazione (web-app Ordini)
Sulla carta prodotto il pulsante **🚫** nasconde l'articolo: lo rimuove dalla vista, lo
ricorda in locale e lo segna sul server. Serve per togliere a mano gli articoli che non
c'entrano con la categoria (es. un articolo non-alimentare comparso tra le bevande).

---

## 7. Ordini: media settimanale, anomalie e corrispettivi

Logica in `backend/routers/analisi_ordini.py`. Serve a evitare ordini sbagliati
(quantità gonfiate, ordini troppo ravvicinati) **prima** dell'invio.

### Come calcola la "media"
- `_storico_per_prodotto()` ricostruisce lo storico ordini di ogni prodotto.
- `_analizza_prodotto()` calcola:
  - **`cadenza_media_giorni`** — ogni quanti giorni mediamente si ordina quel prodotto;
  - **`quantita_media`** — quantità media ordinata.

### Cosa controlla quando l'ordine è sopra la media — `POST /api/analisi-ordini/verifica-carrello`
Prima di inviare il carrello, per ogni riga il sistema confronta la quantità richiesta con
la media storica e restituisce eventuali **alert di anomalia**:
1. **Quantità anomala** — se `quantità > media × (1 + soglia)` (soglia di default **50%**),
   genera un alert del tipo *"Quantità X molto più alta della media (Y): +Z%"*.
2. **Ordine ravvicinato** — se i giorni dall'ultimo ordine sono `< cadenza × (1 − soglia)`,
   segnala che stai riordinando troppo presto rispetto alla cadenza abituale.
3. Restituisce anche `quantita_media` e `cadenza_media_giorni` per contesto.

Le soglie sono regolabili nel payload (`soglia_quantita_pct`, `soglia_cadenza_pct`).
Altri endpoint: `GET /api/analisi-ordini/storico-prodotto` (dettaglio singolo prodotto),
`GET /api/analisi-ordini/riepilogo-cadenze` (riepilogo di tutti i prodotti).

### Il sistema "vede i corrispettivi"?
Quando rileva una quantità anomala, il sistema **aggiunge una nota di verifica corrispettivi**:
in pratica ti avvisa che *"se i corrispettivi (gli incassi) non sono cresciuti, quell'ordine
più grande del solito va valutato/giustificato"*.

Da essere precisi sullo stato attuale: questo è un **incrocio predisposto** con i
corrispettivi del Gestionale (Gestionale2). Cioè il sistema **segnala l'anomalia e invita a
controllare i corrispettivi**, ma **non** legge ancora automaticamente gli incassi per
bloccare/approvare l'ordine: il confronto incassi-vs-ordini è la logica già preparata e
prevista, oggi presentata come avviso da verificare a mano. In sintesi: a oggi controlla la
**media quantità/cadenza** del prodotto; sui corrispettivi fa da **promemoria**, non da
cancello automatico.

---

## 8. HACCP: registri, controlli automatici e report

- **Registri** (§3.3): ogni rilevazione (temperature, sanificazione, olio, ecc.) è salvata
  con data/operatore.
- **Scheduler** (`backend/scheduler.py`): job pianificati che generano avvisi (es. scadenze).
- **Supervisor operativo** (`supervisor_operativo.py`): un cruscotto che esegue molti
  controlli e produce alert con priorità (*critica / alta / media / bassa*), tra cui:
  temperature non registrate oggi, sanificazione mancante, lotti scaduti o in scadenza
  (anche entro 48h), allergeni, qualifiche fornitori scadute/in attesa, fornitori inattivi,
  prodotti senza prezzo, anomalie senza azione correttiva, libretti sanitari, manuale HACCP,
  ricezione merce non verificata.
- **Report HACCP** (`report_haccp.py`, `manuale_haccp.py`): generano i documenti
  (manuale, registri) con l'intestazione aziendale centralizzata.

---

## 9. Lotti e tracciabilità (regola FIFO)

- `lotti_fornitori` — lotti in ingresso dalle fatture (data fattura come riferimento).
- `lotti_produzione` — lotti prodotti in laboratorio (con scadenza/shelf-life).
- **Regola FIFO**: si consuma sempre dal lotto con **`data_fattura` più vecchia**, a
  prescindere dal fornitore. Lo stesso prodotto (nome normalizzato) proveniente da fornitori
  diversi è considerato **un'unica giacenza** ordinata per data. Non si segnala mai un
  prodotto come "finito" se esiste giacenza sotto un qualsiasi fornitore.

---

## 10. Convenzioni e regole permanenti

- **Database** = archivio Supabase dedicato a Lotti. Accesso sempre via `db.py`; nessuna credenziale
  nel codice.
- **Normalizzazione**: uova in pezzi → grammi (1 uovo = 60 g, 1 tuorlo = 19 g,
  1 albume = 33 g); "q.b." → grammi standard (sale 15, pepe 3, vaniglia 2, spezie 5,
  aromi/lievito 10); qualsiasi "lievito naturale" di marca → "Lievito".
- **Prezzi a catalogo**: prezzo e flag "già acquistato" solo da acquisti reali su fattura
  con match affidabile (nome ufficiale o codice). Mai match parziali generici.
- **Pulizia del codice**: niente duplicati, codice morto, blocchi commentati o sistemi
  paralleli; quando si sostituisce qualcosa, si elimina il vecchio.
- **Tema/Design**: palette **beige/sabbia** centralizzata (`tailwind.config.js` +
  `index.css`); accento principale beige `#8a6f47` su sfondo crema `#faf7f0`; colori
  semantici verde/giallo/rosso invariati.

---

## 11. Note operative

- Dopo un push, attendere il **deploy** su Render (qualche minuto) ed eventualmente fare
  **hard reload** del frontend (il nome del bundle cambia ad ogni build).
- Il backend free-tier ha **cold start**: la prima richiesta dopo inattività può impiegare
  qualche decina di secondi.
- Le impostazioni dell'azienda (ragione sociale, indirizzo, P.IVA, **codice destinatario
  SDI**, PEC, email, telefono) si modificano dalla pagina **Impostazioni / Personale** e sono
  la sorgente unica usata in tutti i PDF e i documenti.

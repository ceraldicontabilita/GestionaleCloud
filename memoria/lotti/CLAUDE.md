# Lotti — HACCP Tracciabilità (Ceraldi Group)

Questo file viene letto automaticamente da Claude Code all'inizio di OGNI sessione
in questo repository. Se stai leggendo questo file, sei già "dentro" il contesto:
non serve altro prompt, non serve altro file allegato. Segui queste istruzioni.

## Cos'è questo progetto

App gestionale HACCP per una pasticceria/rosticceria/bar (Ceraldi Group, Napoli),
usata ogni giorno dal titolare (Enzo) e dai dipendenti su smartphone/tablet in
negozio. Gestisce: import fatture XML, tracciabilità lotti, ricette e food cost,
ordini fornitori, magazzino, registri HACCP obbligatori per legge.

- **Live**: https://www.ceraldiapp.it (dominio principale) — anche
  https://lotti-frontend.onrender.com (dominio Render di riserva)
- **Backend**: https://lotti-backend-2wwb.onrender.com (FastAPI, `/docs` per Swagger)
- **Login**: PIN via `POST /api/auth/login {"pin":"<pin>"}` — il PIN admin non va
  scritto qui né in nessun file del repo (vedi sezione Credenziali).

## PRIMA di fare qualunque cosa: leggi questi file

Nell'ordine, per capire lo stato del progetto e le regole del titolare:

1. **`memory/REGOLE_ENZO.md`** — le direttive permanenti del titolare (design,
   accessi, metodo di lavoro). Sempre valide, su tutte le app del gruppo.
2. **`memory/STATO.md`** — cronologia dettagliata di ogni intervento fatto finora
   (è un changelog lungo: leggi le ultime 200-300 righe per il contesto più
   recente, usa la ricerca testuale per argomenti specifici — non serve leggerlo
   tutto ogni volta).
3. **`memory/claude.md`** — mappa tecnica di riferimento: nomi esatti dei campi
   MongoDB, path esatti degli endpoint, bug noti/gotcha. Consultalo PRIMA di
   scrivere query o chiamate API per non ripetere errori già fatti.
4. **`memory/PRD.md`** — requisiti di prodotto originali.

## Stack e architettura

- **Backend**: FastAPI + Motor (MongoDB Atlas, database `Gestionale` — condiviso
  con un'altra app del gruppo, "Gestionale Cloud"), in `backend/`. Router modulari
  in `backend/routers/*.py`, montati in `backend/server.py`.
- **Frontend**: React + CRACO in `frontend/`, hash routing (`#pagina`), Tailwind +
  classi `g-*` custom in `index.css`.
- **Deploy**: Render, auto-deploy ad ogni push su `main` (~5-8 minuti). Config in
  `render.yaml` alla radice (Blueprint: definisce entrambi i servizi, env vars,
  domini custom).

## Credenziali, secret, `.env`

**Non esistono file `.env` nel repo e non devono mai esistere.** Tutte le
credenziali (MongoDB, Anthropic API key, ecc.) sono variabili d'ambiente
configurate SOLO nel pannello Render (Dashboard → servizio → Environment),
dichiarate senza valore in `render.yaml` con `sync: false` (es. `MONGO_URL`,
`ANTHROPIC_API_KEY`). Non scrivere mai un PIN, una password o un token in chat,
nel codice o nei file di memoria — nemmeno mascherato parzialmente, a meno che
l'utente non lo chieda esplicitamente per un test live (in quel caso, mai
persisterlo su disco: usarlo solo inline in un singolo comando shell).

Per azioni live sul backend di produzione che richiedono autenticazione: login
con `POST /api/auth/login {"pin":"..."}` (il PIN te lo fornisce l'utente in
chat quando serve), usare il token risultante come header `Authorization:
Bearer <token>` SOLO all'interno dello stesso comando, mai scritto su file.

## Design system

Fonte: cartella `design_handoff/` (README.md + `tokens/` + `ui_kit/` prototipo
navigabile). Riassunto:
- Palette: salvia `#5b7a6b` (dark `#3f5a4e`, gradiente `135deg #5b7a6b→#6f9180`),
  crema `#faf7f0`, card `#fffefb`, bordi `#e6e0d4`.
- **Mai colori freddi** (blu/indaco/viola/ciano/azzurro/viola): vanno sempre
  rimappati su salvia o sabbia (`#8a6f47`/`#6f583a`), sia nelle classi Tailwind
  (`bg-blue-*` ecc.) sia negli hex/rgba scritti negli stili inline.
- Semantici: danger terracotta `#d35f4e`, warning ocra `#c4894a`, success verde
  bosco `#3d8168`, info sabbia `#8a6f47`.
- Icone Lucide (`lucide-react`), mai emoji nelle UI (renderizzano con colori
  di sistema non controllabili, es. 👤 appare blu su Android).
- Ogni pagina centrata via il contenitore globale `.g-page` (App.js); mai
  scroll orizzontale su smartphone — tabelle strette → card responsive.
- Coerenza con la pagina Dashboard (`DashboardView.jsx`) come riferimento.

## Skills riusabili (`.claude/skills/`)

Skill già create in questo progetto, riusabili su tutte le app del gruppo
Ceraldi (copiare la cartella `.claude/skills/` nei nuovi progetti):
- **`guida-operativa`** — genera la guida operativa PDF dell'app leggendo il
  codice reale (mai inventata).
- **`audit-codice`** — audit completo per errori/incoerenze reali (non stile).
- **`bonifica-design`** — verifica e ripristina coerenza design su tutte le
  pagine (colori, centratura, mobile).
- **`collaudo-funzionale`** — verifica end-to-end di un flusso con dati di
  prova reali sul backend live (poi ripuliti).

## Metodo di lavoro (sintesi da `memory/REGOLE_ENZO.md`)

- Rispondere sempre in italiano; risultati prima delle spiegazioni.
- Non fidarsi di un fix "a occhio": leggere il codice REALE (file:riga) prima
  di dichiarare una causa; se il titolare mostra uno screenshot con un bug
  ancora presente dopo un fix, vuol dire che il fix non ha coperto quel caso —
  investigare di nuovo da zero sui dati reali (fatture/DB live), non ripetere
  la stessa spiegazione.
- Dopo ogni modifica: build locale (frontend `npm run build`, backend
  `python -m compileall` + import-check — stessa procedura della CI), commit,
  push sul branch della sessione, PR, aspettare CI verde, merge, riallineare
  il branch locale a `origin/main`, VERIFICARE IL DEPLOY LIVE (hash del bundle
  frontend da `asset-manifest.json`, health check backend
  `GET /api/health`), aggiornare `memory/STATO.md` con un riassunto
  dell'intervento.
- Le funzionalità si collaudano davvero (dati di prova sul backend live, poi
  puliti), non si dichiarano "a posto" solo leggendo il codice.
- Se non so risolvere subito un problema: cercare su GitHub/web come altri
  progetti reali risolvono lo stesso problema, non limitarsi a descriverlo.
- Prodotto/dominio: un solo punto d'ingresso fatture; prezzi SOLO da acquisti
  reali in fattura XML; FIFO consuma sempre il lotto più vecchio; ogni riga
  d'ordine dice CHI l'ha inserita; **le bevande/alcolici (reparto bar: acqua,
  birre, vino, prosecco, liquori, amari, sciroppi, succhi, bibite) si
  acquistano e si confrontano a CARTONE/UNITÀ, MAI a kg/litro** — un rum o una
  birra si pagano a bottiglia/cartone, non "al chilo".
- Accessi: PIN valido 2 ore; dipendenti liberi ovunque tranne le pagine admin
  (impostazioni/PIN/personale, controllo dati, backoffice, configurazione,
  backup, stampanti).

## Limiti noti di questo ambiente (sandbox Claude Code on the web)

- Il Chromium headless in questo sandbox non riesce a fare richieste di rete
  in uscita (screenshot automatici dell'app NON sono possibili da qui) — se
  serve una verifica visiva, chiedere all'utente uno screenshot dal telefono.
- Nessun accesso al pannello Render o al pannello DNS del registrar
  (register.it): per azioni che richiedono quei pannelli, spiegare
  chiaramente all'utente i passaggi esatti da fare lui.

## Repository GitHub

`ceraldicontabilita/Lotti` — branch di lavoro tipico:
`claude/lotti-haccp-backend-o0j3ns` (o simile, indicato dal contesto della
sessione). PR con titolo descrittivo, merge via squash una volta verde la CI
("Backend — import & compile", "Frontend — build").

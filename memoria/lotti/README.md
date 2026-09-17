# Ceraldi Group — HACCP Tracciabilità (Lotti)

Gestionale HACCP per Ceraldi Group SRL (pasticceria/rosticceria/bar, Napoli),
usato ogni giorno dal titolare e dai dipendenti su smartphone e tablet.

**App live**: https://www.ceraldiapp.it
**Repository**: https://github.com/ceraldicontabilita/Lotti

## Stack
- **Backend**: FastAPI con persistenza indipendente su Supabase/PostgreSQL — `backend/`
- **Frontend**: React 18 (CRA/craco) + Tailwind CSS, hash routing — `frontend/`
- **Design**: palette **salvia** `#5b7a6b` / crema `#faf7f0` / sabbia `#8a6f47`,
  Plus Jakarta Sans, icone Lucide. Mai colori freddi (blu/viola/azzurro).
  Fonte di verità: `design_handoff/` (tokens + UI kit).

## Moduli principali
- **Import fatture XML** (anche ZIP/.p7m): fonte unica di fornitori, prodotti,
  prezzi, giacenze e lotti. Dedup per numero+P.IVA; ricezione automatica e
  idempotente da GestionaleCloud con registro anti-duplicazione; filtro per anno.
- **Tracciabilità lotti** (produzioni, fornitori, gelati `GEL-…`, pesce
  `PESR-/PES-…`) con consumo FIFO (finestra 60 giorni sul lotto più vecchio),
  ricerca universale per recall ASL e registro inverso per fornitore
  (quali ricette hanno usato i suoi prodotti).
- **Scadenze (shelf-life)**: calcolo automatico da categoria prodotto +
  ingrediente più deperibile (`backend/routers/shelf_life.py`), con regole
  per prodotti cotti in forno e lunga conservazione (panettone, biscotti…);
  la data proposta è modificabile alla registrazione del lotto e la durata
  corretta a mano viene memorizzata per prodotto (`scadenza_giorni_override`).
- **Ricette & food cost**: ingredienti collegati al dizionario canonico,
  allergeni, valori nutrizionali, schede stampabili. Nel form: proposta
  ingredienti dal nome (AI → base curata ~60 ricette napoletane → ricetta
  più simile, gusti letti dal nome tipo "babà panna e pistacchio"), memoria
  dell'origine ingredienti (manuale/automatica/ereditata), «Eredita scheda»
  per le varianti, foto anche su ricetta nuova, prodotti di rivendita con
  fornitore scelto dal database.
- **Foto prodotti**: store persistente Supabase (`foto_files`, servite da
  `GET /api/foto/{id}?v=`) — sopravvivono ai deploy; associazione conservativa
  da archivio locale e recupero best-effort da Wikimedia Commons.
- **Ordini fornitori**: catalogo con comparatore prezzi (solo prezzi da
  fatture reali), carrello unico, flusso bozza → confermato → inviato,
  riordini automatici da soglie giacenza.
- **Cataloghi fornitori** (pagina unica a tab): Acquaviva, SAIMA, MePA,
  Il Pasticcere, Tre Marie, Bindi, Alfa senza glutine, Sammontana — con
  import da PDF trascritti (`backend/data/catalogo_forno_*.json`), stella
  "preferito colazione" e badge "già comprato" agganciato alle fatture.
  Connettore generico "incolla il link" in Impostazioni per fonti nuove.
- **Magazzino**: giacenze unificate IN PEZZI (conversione cartone→pezzi dal
  nome riga fattura, es. "CL 33 X 24"), per anno di fatturazione, senza
  prezzi in vista dipendenti; magazzino bar (stock + registro movimenti +
  lavagna rifornimenti + tastierino a schermo), controllo prelievi.
- **Tablet kiosk** con PIN per reparti (pasticceria/rosticceria/vendita/
  magazzino): produzioni con scelta del frigo/congelatore reale e stampa
  della distinta di tracciabilità, manda-al-banco con quantità scelta,
  farcitura cornetti per gusti (proporzioni dai preset Colazione),
  senza glutine.
- **Colazione**: preset per stagione con cambio automatico ai solstizi
  (periodi modificabili), copia di un preset nelle altre stagioni, prodotti
  fatti in casa prima e solo quelli davvero acquistati in fattura, preferiti
  (⭐) validi su tutti i cataloghi.
- **Dizionario ingredienti**: righe fattura → nome canonico, con esclusione
  per singola riga o per famiglia (bevande/alcolici/vini); le decisioni sui
  fornitori vivono in `fornitori_decisioni`, collezione di sola proprietà di
  Lotti. L'archivio Supabase è dedicato e nessun altro gestionale può
  sovrascrivere queste decisioni.
- **Registri HACCP**: temperature positive/negative/cottura, sanificazione,
  disinfestazione, olio frittura, ricezione merce, manuale di autocontrollo,
  registro allergeni, qualifica fornitori.
- **Vendita banco, corrispettivi, listini** (genera & esporta PDF),
  sconti merce, backup streaming del database, guida in-app (+ PDF).
- **Supervisore operativo**: alert navigabili con elenco dei colpevoli.

## Struttura repo
```
backend/            FastAPI: server.py + routers/*.py modulari
backend/data/       dati bundlati (cataloghi PDF trascritti, schede prodotti)
backend/tests/      test puri (senza rete/DB) + test integrazione (server live)
frontend/           React: src/components/haccp/*.jsx, hash routing #pagina
frontend/public/guida/  Guida operativa PDF (fonte: src/data/guidaContenuti.json)
design_handoff/     design system (tokens, UI kit navigabile)
memory/             STATO.md (changelog), REGOLE_ENZO.md, claude.md (mappa tecnica)
.claude/skills/     skill riusabili (audit-codice, guida-operativa, ...)
```

## Accesso al repository per gli assistenti AI
Repo GitHub: **https://github.com/ceraldicontabilita/Lotti** (privato).
- **Claude Code**: già collegato (GitHub App autorizzata sul repo).
- **ChatGPT / Codex**: il permesso lo concede il proprietario dell'account
  GitHub, dall'interno di ChatGPT — 1) chatgpt.com → Settings →
  *Connectors / Connected apps* (o la pagina Codex) → **Connect GitHub**;
  2) accedi con l'account `ceraldicontabilita` e nella schermata di
  autorizzazione scegli **Only select repositories → Lotti**; 3) da quel
  momento in ChatGPT si può selezionare il repo nelle chat/Codex.
  Per revocare: GitHub → Settings → Applications → Installed GitHub Apps.

Regola valida per QUALSIASI assistente: nel repo e nelle chat **non si
incollano mai PIN, password o chiavi** — le credenziali vivono solo nelle
variabili d'ambiente del pannello Render (vedi sotto).

## Deploy
Render (Blueprint `render.yaml`), auto-deploy a ogni push su `main` (~5-8 min):
- Frontend: **https://www.ceraldiapp.it** (riserva: lotti-frontend.onrender.com)
- Backend: https://lotti-backend-f2fg.onrender.com (`/docs` per Swagger,
  `/api/health` per health check)

## Variabili d'ambiente (solo pannello Render, mai nel repo)
- `SUPABASE_URL` — URL del progetto Supabase dedicato a Lotti
- `SUPABASE_ANON_KEY` — chiave pubblicabile usata solo per invocare le RPC protette
- `LOTTI_DB_SECRET` — segreto server-side delle RPC (mai nel frontend)
- `AUTH_SECRET` — chiave server-side per i token JWT
- `DB_NAME` — `Gestionale`
- `ANTHROPIC_API_KEY` — normalizzazione LLM nomi ingredienti
- `AUTH_ENFORCE=true` — autenticazione obbligatoria (PIN/JWT)
- `CORS_ORIGINS` — origini extra oltre a quelle hardcoded in `server.py`

## Verifiche pre-commit (stesse della CI)
```
cd backend && python -m compileall .        # + import-check dei router
cd frontend && CI=false npm run build
cd backend && python -m pytest tests/       # set puro: 150 test senza rete/DB
```
Nota: i test `test_iterationNN_*.py` richiedono un server live
(`REACT_APP_BACKEND_URL`) e falliscono in locale/CI — il riferimento è il
set puro (riordino, prezzi, shelf-life, proponi-ingredienti, colazione, p7m…).

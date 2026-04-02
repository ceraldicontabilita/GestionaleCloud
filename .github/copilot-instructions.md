# Istruzioni per GitHub Copilot - Azienda in Cloud ERP

## Panoramica del Progetto
Questo è un ERP gestionale italiano chiamato "Azienda in Cloud", sviluppato per un bar/pasticceria.
P.IVA azienda: 04523831214. Sistema NON multi-utente.

## Stack Tecnologico
- **Backend**: Python 3.x, FastAPI 0.110.1, Uvicorn, MongoDB (pymongo 4.5.0 + motor 3.3.1 async)
- **Frontend**: JavaScript (30%), CSS, HTML, con yarn come package manager
- **Auth**: JWT (pyjwt + python-jose + bcrypt + passlib)
- **Altri tool**: APScheduler, pandas, numpy, openpyxl, IMAPClient, beautifulsoup4, rapidfuzz

## Architettura Backend
Entry point: `backend/server.py` → carica `.env` → importa `app.main.app`
App principale: `app/main.py` (FastAPI)
Database: MongoDB, connessione in `app/database.py`

### Struttura Moduli Router (`app/routers/`)
- `f24/` – F24, tributi, riconciliazione, quietanze
- `haccp/` – HACCP, libro unico, schede tecniche, sanificazioni
- `accounting/` – Prima nota, piano conti, bilancio, centri costo, liquidazione IVA
- `bank/` – Estratti conto, riconciliazione bancaria, bonifici, POS
- `warehouse/` – Magazzino, prodotti, lotti, ricette, tracciabilità
- `invoices/` – Fatture emesse/ricevute, corrispettivi, export
- `employees/` – Dipendenti, cedolini/buste paga, contratti, turni
- `reports/` – Report PDF, analytics, dashboard

Per aggiungere un modulo: crea `app/routers/nuovo_modulo/`, aggiungi `__init__.py`, registra in `main.py` con `app.include_router(...)`.

## Regole Contabili Italiane (FONDAMENTALI)
- I **corrispettivi** sono l'UNICA fonte di RICAVI (collezione: `corrispettivi`)
- Le **fatture ricevute** sono costi passivi (collezione: `invoices`)
- I **cedolini** gestiscono buste paga (collezione: `cedolini`): campi `lordo`, `netto`, `inps_azienda`, `tfr`, `costo_azienda`
- Il conto economico segue l'**art. 2425 c.c.** (voci A, B, C)
- Classificazione automatica fatture per fornitore (Enel→energia B7, TIM→telefonia 80% ded., ARVAL→noleggio auto 20% ded. max €3.615,20, ecc.)
- **Auto aziendali**: deducibilità 20%, IVA detraibile 40% (Art. 164 TUIR)
- **Telefonia**: deducibilità 80%, IVA detraibile 50% (Art. 102 TUIR)
- **TFR**: rivalutazione con formula ISTAT corretta
- Magazzino: prezzo medio ponderato, tracciabilità lotti (LOTTO-YYYYMMDDHHMMSS)

## Convenzioni di Codice
- Commenti e nomi variabili in **italiano** o inglese tecnico
- Usare **Pydantic v2** per i modelli e gli schemi
- Endpoint API sempre sotto `/api/` (es: `/api/bilancio/conto-economico`)
- Middleware autenticazione JWT in `app/middleware/auth.py`; alcuni path pubblici esclusi
- Logger da `app/utils/logger.py`
- Variabili d'ambiente caricate da `backend/.env` tramite `python-dotenv`
- Formattazione codice con **black** e **isort**; linting con **flake8**; type checking con **mypy**

## Qualità del Codice
- Scrivi sempre **type hints** su tutte le funzioni Python
- Aggiungi **docstring** in italiano per ogni funzione/classe importante
- Per ogni nuovo endpoint API, verifica che rispetti le regole fiscali italiane in `app/REGOLE_CONTABILI.md`
- Consulta `app/ARCHITECTURE.md` per la struttura prima di aggiungere file
- Usa `motor` (async) per le query MongoDB nel backend FastAPI
- Gestisci sempre le eccezioni con i custom exceptions in `app/exceptions/`
- Quando modifichi calcoli contabili (IVA, TFR, cedolini, F24), verifica la correttezza fiscale italiana

## File di Riferimento Chiave
- `app/REGOLE_CONTABILI.md` – Regole fiscali italiane del progetto
- `app/ARCHITECTURE.md` – Struttura architetturale completa
- `app/SKILLS_GESTIONALE.md` – Competenze e funzionalità del gestionale
- `app/SKILLS_PDF_PARSING.md` – Parsing PDF (F24, fatture, ecc.)
- `backend/requirements.txt` – Dipendenze Python

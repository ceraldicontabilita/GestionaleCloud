# Handoff — Export Presenze Consulente / Workflow Emergent

Data: 25 Aprile 2026
Repo: `ceraldicontabilita/gestionale2`
Branch: `main`

## Regola operativa principale

ChatGPT e' l'autore del codice applicativo.
Emergent non deve scrivere, correggere, rifattorizzare o inventare codice applicativo in autonomia.

Emergent deve solo:

- fare `git pull --rebase`;
- buildare;
- riavviare servizi;
- eseguire health check, audit statico e smoke test;
- riportare output completo se qualcosa fallisce.

Emergent NON deve:

- modificare codice;
- eseguire script patch che cambiano file;
- fare reset hard;
- fare push force;
- risolvere conflitti creativamente.

## Stato verificato su main

Risulta presente su `main`:

- `memoria/REGOLE_OPERATIVE_AUTORI.md`
- `app/routers/attendance_module/export_consulente.py`
- `app/routers/attendance_module/__init__.py` con registrazione router export
- `scripts/audit_static.py`
- `scripts/smoke_app.py`

Risulta NON presente su `main`:

- `scripts/patch_hr_presenze_export.py`

Questo e' corretto: quello script e' stato eliminato per rispettare la regola che Emergent non deve modificare codice.

## Regola HR Presenze

Le presenze NON si importano da PDF.

Flusso corretto:

1. Inserimento/modifica presenze e giustificativi nel gestionale.
2. Controllo calendario e griglia mensile.
3. Export verso consulente del lavoro.
4. Eventuale import di ritorno solo per cedolini/documenti paghe, non per la sorgente presenze.

## Export presenze consulente aggiunto

Nuovo router backend:

```text
app/routers/attendance_module/export_consulente.py
```

Endpoint:

```text
GET /api/attendance/export-consulente/preview?anno=2026&mese=4
GET /api/attendance/export-consulente/csv?anno=2026&mese=4
```

Il CSV include:

- dipendente;
- codice fiscale;
- giorni del mese;
- codici presenza/assenza;
- totali per stato;
- giorni retribuiti;
- giorni non retribuiti;
- acconto EUR;
- protocolli malattia;
- sezione anomalie, per esempio malattia senza protocollo.

Registrazione router:

```python
from .export_consulente import router as export_consulente_router
router.include_router(export_consulente_router, tags=["Attendance - Export Consulente"])
```

File:

```text
app/routers/attendance_module/__init__.py
```

## Prompt corretto per Emergent quando si riprende

Da inviare a Emergent:

```text
Non fare codice. Non modificare file. Devi solo allineare, buildare, riavviare e testare.

Esegui:

cd /app
git fetch origin
git pull --rebase origin main

Poi:

cd /app/frontend
yarn build
cd /app
python3 -m py_compile app/routers/attendance_module/export_consulente.py
python3 -m py_compile app/routers/attendance_module/__init__.py

Poi restart:

sudo supervisorctl restart backend
sudo supervisorctl restart frontend
sudo supervisorctl status

Poi test:

curl -s http://localhost:8001/api/health
curl -I "http://localhost:8001/api/attendance/export-consulente/csv?anno=2026&mese=4"
curl -s "http://localhost:8001/api/attendance/export-consulente/preview?anno=2026&mese=4"

Poi audit:

python3 scripts/audit_static.py
BACKEND_URL=http://localhost:8001 FRONTEND_URL=http://localhost:3000 python3 scripts/smoke_app.py

Se esce errore, fermati e manda output completo. Non modificare codice, non fare patch, non fare reset hard.
```

## Stato UI

Non e' stata modificata direttamente `frontend/src/pages/hr/HRPresenze.jsx` in questa fase.

Motivo: file grande gia' lavorato da Claude/Emergent; per evitare conflitti o sovrascritture, e' stato aggiunto prima il backend export separato.

Prossimo passo futuro, se autorizzato:

- aggiornare UI direttamente da ChatGPT nel repo, non tramite script da eseguire in Emergent;
- sostituire CTA concettualmente errata di import PDF con export CSV/PDF consulente;
- fare build e test.

## Note su Claude/Emergent

Non risultano sovrascritture dei file grandi gia' lavorati da Claude nella fase export consulente.
La modifica principale e' additiva e separata:

- nuovo file backend export;
- registrazione router;
- memoria operativa.

## Backlog residuo noto

1. Collegare UI HR Presenze agli endpoint export consulente, scrivendo il codice direttamente su GitHub.
2. Verificare `CEDOLINI.txt` se il file viene ricaricato o ritrovato.
3. Aggiornare `WHATSAPP_API_TOKEN` in `.env` se serve WhatsApp.
4. Refactoring `corrispettivi.py` solo con autorizzazione esplicita.
5. Tab contabilita' residue: Mutui, Chiusura Esercizio, Finanziaria.

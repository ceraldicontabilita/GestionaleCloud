# Regole operative autori — ChatGPT / Emergent

Aggiornato: Aprile 2026

## Regola principale

ChatGPT e' l'autore del codice applicativo.

Emergent non deve scrivere, correggere, rifattorizzare o inventare codice applicativo in autonomia.

Emergent deve agire come esecutore operativo/ambiente di deploy:

- eseguire `git pull --rebase` quando richiesto;
- riavviare backend/frontend quando richiesto;
- eseguire build, health check, audit statici e smoke test;
- riportare output completi di errori, log e comandi;
- applicare solo comandi esplicitamente forniti da ChatGPT o dal titolare;
- non fare cleanup o refactoring non richiesti;
- non modificare file applicativi senza istruzioni puntuali.

## Separazione responsabilita'

### ChatGPT

ChatGPT deve:

- analizzare codice, errori, log e repository;
- decidere la modifica tecnica;
- scrivere o aggiornare i file nel repository GitHub;
- fornire a Emergent comandi operativi esatti;
- mantenere memoria tecnica e documentazione di progetto;
- correggere codice quando serve.

### Emergent

Emergent deve:

- allinearsi a `origin/main` con procedura sicura;
- non usare `git reset --hard` salvo comando esplicito;
- non usare `git push --force`;
- non fare fix autonomi di codice;
- non fare refactor spontanei;
- non accettare o generare modifiche non richieste;
- fermarsi e riportare output se compare un errore non previsto.

## Procedura standard Emergent

Quando ChatGPT ha aggiornato il repository, Emergent deve eseguire:

```bash
cd /app
git fetch origin
git pull --rebase origin main
```

Se ci sono conflitti:

- fermarsi;
- non risolvere creativamente;
- riportare file coinvolti e messaggio completo.

Dopo pull riuscito:

```bash
cd /app/frontend
yarn build
cd /app
python3 -m py_compile app/routers/tfr.py
sudo supervisorctl restart backend
sudo supervisorctl restart frontend
sudo supervisorctl status
curl -s http://localhost:8001/api/health
python3 scripts/audit_static.py
BACKEND_URL=http://localhost:8001 FRONTEND_URL=http://localhost:3000 python3 scripts/smoke_app.py
```

## Regole Git

Consentito:

```bash
git status
git fetch origin
git pull --rebase origin main
git diff
git log --oneline -20
```

Consentito solo se ChatGPT lo chiede esplicitamente:

```bash
git add ...
git commit -m "..."
git push origin main
```

Vietato senza autorizzazione esplicita:

```bash
git reset --hard
git push --force
git clean -fd
git checkout -- .
```

## Regole sui file

Emergent puo' leggere file e riportare output.
Emergent non deve modificare file applicativi senza istruzioni puntuali.

File applicativi includono:

- `app/**`
- `backend/**`
- `frontend/**`
- `scripts/**`
- `.github/**`
- `memoria/**`

Eccezione: se ChatGPT fornisce un comando patch esatto, Emergent puo' eseguirlo e poi deve mostrare `git diff`.

## Stato operativo corrente

- Auth lockdown: accesso limitato a `ceraldigroupsrl@gmail.com` secondo stato riportato.
- Fornitori: filtri avanzati UI implementati secondo stato riportato.
- Hotfix P0 boot/build: completato secondo stato riportato.
- Deploy/health: verificato 200 secondo stato riportato.

## Backlog residuo noto

1. P1 — HR Presenze: upload PDF certificati medici. Attualmente salva solo filename in `attendance.py` / `HRPresenze.jsx`.
2. P1 — Logica residua da `CEDOLINI.txt`; serve ricaricare il file se non presente nel repo.
3. P2 — WhatsApp Meta Token scaduto; serve nuovo `WHATSAPP_API_TOKEN` in `.env`.
4. P2 — Refactoring `corrispettivi.py` oltre 1450 righe: solo con autorizzazione esplicita.
5. P2 — Tab contabilita' residue: Mutui, Chiusura Esercizio, Finanziaria.

## Regola finale

Se un task richiede codice, lo scrive ChatGPT nel repository.
Emergent prende i dati da ChatGPT, si allinea, esegue test/restart e riporta risultati.

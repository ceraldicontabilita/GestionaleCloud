# Runbook — GestionaleCloud MCP

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

## Installazione isolata

L'SDK MCP 2.0 usa dipendenze ASGI più recenti di quelle del backend FastAPI 0.110. Per questo il gateway deve avere un ambiente Python separato.

PowerShell:

```powershell
python -m venv .venv-mcp
.\.venv-mcp\Scripts\python.exe -m pip install -r gestionale_mcp\requirements.txt
```

Non installare `gestionale_mcp/requirements.txt` nell'ambiente del backend in produzione.

## Configurazione minima locale

```powershell
$env:GESTIONALE_MCP_API_BASE_URL = "http://127.0.0.1:8000"
$env:GESTIONALE_MCP_API_TOKEN = "<JWT del Gestionale>"
.\.venv-mcp\Scripts\python.exe -m gestionale_mcp --transport stdio
```

Il token viene usato soltanto per le chiamate al backend e non appare nei log.

## Configurazione Streamable HTTP

```powershell
$env:GESTIONALE_MCP_API_BASE_URL = "https://impresasemplice.online"
$env:GESTIONALE_MCP_HOST = "127.0.0.1"
$env:GESTIONALE_MCP_PORT = "8765"
$env:GESTIONALE_MCP_ISSUER_URL = "https://impresasemplice.online"
$env:GESTIONALE_MCP_RESOURCE_SERVER_URL = "https://mcp.example.it"
$env:GESTIONALE_MCP_ALLOWED_HOSTS = "mcp.example.it,127.0.0.1:*"
$env:GESTIONALE_MCP_ALLOWED_ORIGINS = "https://mcp.example.it"
.\.venv-mcp\Scripts\python.exe -m gestionale_mcp --transport http
```

Esporre la porta soltanto dietro TLS e reverse proxy. Il percorso MCP è `/mcp` e il server usa risposte JSON stateless.

## Variabili

| Variabile | Default | Significato |
|---|---:|---|
| `GESTIONALE_MCP_API_BASE_URL` | `http://127.0.0.1:8000` | backend canonico |
| `GESTIONALE_MCP_API_TOKEN` | vuoto | JWT per `stdio` |
| `GESTIONALE_MCP_TIMEOUT_SECONDS` | `30` | timeout API |
| `GESTIONALE_MCP_MAX_RESPONSE_BYTES` | `2000000` | limite risposta |
| `GESTIONALE_MCP_MAX_ITEMS` | `500` | limite liste |
| `GESTIONALE_MCP_ALLOW_WRITES` | `false` | abilita il secondo passo mutativo |
| `GESTIONALE_MCP_PROPOSAL_TTL` | `900` | durata proposta in secondi |
| `GESTIONALE_MCP_ALLOWED_HOSTS` | localhost | protezione host |
| `GESTIONALE_MCP_ALLOWED_ORIGINS` | localhost | protezione origin |

## Collaudo

```powershell
.\.venv-mcp\Scripts\python.exe -m pip install -r gestionale_mcp\requirements-dev.txt
.\.venv-mcp\Scripts\python.exe -m pytest -q tests\test_mcp_gateway.py
python -m pytest -q tests\test_mcp_openapi_contract.py
```

Il test non deve richiedere Drive/Sheets, Drive, Gmail, PayPal, SumUp o produzione.

La pipeline `.github/workflows/mcp-ci.yml` verifica separatamente il contratto
FastAPI e il runtime MCP. Questa separazione evita di aggiornare Starlette nel
servizio backend soltanto per soddisfare le dipendenze del gateway.

Checklist prima dell'attivazione remota:

- test MCP verdi;
- suite backend verde;
- token non presente nei file o nei log;
- HTTPS attivo;
- host/origin espliciti;
- scritture ancora disabilitate;
- `gestionale_status` mostra ruolo e MFA corretti;
- almeno le dodici valutazioni in `gestionale_mcp/evals/read_only_evals.json` verificate;
- attivazione delle scritture separata e approvata.

## Diagnostica

- `Token ... assente/scaduto/revocato`: generare una nuova sessione ERP; non copiare password nel client MCP.
- `Endpoint non disponibile`: il backend e il catalogo MCP sono disallineati; eseguire il test OpenAPI.
- `Risposta troppo grande`: usare anno, mese, stato, `limit` e `skip`/`offset`.
- `Il tool MCP non trasferisce file`: aprire il documento tramite l'interfaccia del gestionale, che applica autorizzazioni e audit dedicati.
- `Scritture MCP disabilitate`: comportamento previsto finché non è stata autorizzata l'attivazione.

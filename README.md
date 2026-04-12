# Ceraldi ERP

Gestionale ERP full-stack per Ceraldi Group S.R.L. (P.IVA: 04523831214).

**Stack**: React 18 + FastAPI + MongoDB Atlas

## Documentazione

Tutta la documentazione si trova nella cartella **`memoria/`**:

- [`memoria/INDEX.md`](./memoria/INDEX.md) — Indice completo con tutti i link
- [`memoria/ARCHITETTURA.md`](./memoria/ARCHITETTURA.md) — Stack, struttura directory, pattern
- [`memoria/LOGICA_OPERATIVA.md`](./memoria/LOGICA_OPERATIVA.md) — Regole business e collections MongoDB
- [`memoria/FLUSSI_OPERATIVI.md`](./memoria/FLUSSI_OPERATIVI.md) — Flussi operativi dettagliati
- [`memoria/PRD.md`](./memoria/PRD.md) — Stato implementazione e backlog

## Avvio rapido

```bash
# Backend (FastAPI)
cd backend && uvicorn server:app --port 8001

# Frontend (React)
cd frontend && npm run dev
```

Gestito da Supervisor in produzione. NON modificare `backend/server.py`.

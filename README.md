# Ceraldi ERP v2

Gestionale HORECA — FastAPI + Motor + React 18 + Vite + MongoDB Atlas

## Setup

```bash
# Backend
pip install -r requirements.txt
cd frontend && npm install && cd ..

# Run
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
cd frontend && npm run dev
```

## Test connessione MongoDB
```bash
pip install pymongo python-dotenv dnspython
python mongodbExample.py
```

## Feature: Dipendenti + Pignoramenti
- CRUD dipendenti con stato attivo/cessato/sospeso
- Upload PDF pignoramento → parsing automatico C.F. debitore
- Match con dipendente → genera Dichiarazione Stragiudiziale di Terzo
- Tracking stato: ricevuto → dichiarazione_generata → dichiarazione_inviata → estinto

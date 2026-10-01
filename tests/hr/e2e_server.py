"""Backend del collaudo browser HR: dati sintetici e scritture in memoria.

Avvio: python -m uvicorn tests.hr.e2e_server:app --host 127.0.0.1 --port 8791
Collaudo: cd frontend_hr && npm run test:e2e
Nessun lifespan ERP/HR, connessione Supabase o scheduler.
"""
import os

# Stesso perimetro del runner ERP: nessun URL, segreto o .env ereditato.
from scripts.collaudo_isolato import ambiente_isolato

_ambiente_fixture = ambiente_isolato(os.environ)
os.environ.clear()
os.environ.update(_ambiente_fixture)
os.environ["HR_JWT_SECRET"] = "e2e-hr-fixture-isolata-non-produzione-12345678"
os.environ["SECRET_KEY"] = "e2e-erp-fixture-isolata-non-produzione-12345678"
os.environ["ENABLE_SCHEDULER"] = "false"

from contextlib import asynccontextmanager
from fastapi import FastAPI
from mongomock_motor import AsyncMongoMockClient
from app.hr.main import app as hr_app
from app.hr.database import Database
from app.hr.services.auth_dipendenti import hash_pin
from app.services import group_session

db = AsyncMongoMockClient()["hr_browser_fixture"]
Database.get_db = classmethod(lambda cls: db)

async def non_revocata(_):
    return False

group_session.sessione_revocata = non_revocata

async def semina():
    await db.dipendenti.insert_one({
        "id": "dip-prova", "nome": "Persona", "cognome": "Prova", "nome_completo": "Prova Persona",
        "stato": "attivo", "attivo": True, "in_carico": True,
        "ruolo_app": "responsabile_turni", "pin_hash": hash_pin("1234"),
    })
    await db.turni_cloud.insert_many([
        {"id": "turno-prova", "nome": "Mattina", "orario_inizio": "08:00", "orario_fine": "12:00", "colore": "#5b7a6b"},
        {"id": "riposo-prova", "nome": "Riposo", "orario_inizio": "", "orario_fine": "", "colore": "#8a6f47"},
    ])
    await db.turni_config.insert_one({"dipendente_id": "dip-prova", "turno_id": "turno-prova"})

@asynccontextmanager
async def lifespan_fixture(_):
    await semina()
    yield


app = FastAPI(lifespan=lifespan_fixture)


@app.get("/__fixture__/health")
async def salute_fixture():
    return {"fixture": "hr-e2e-isolato"}


@app.get("/api/sezioni")
async def sezioni():
    return {"sezioni": []}


app.mount("/hr", hr_app)

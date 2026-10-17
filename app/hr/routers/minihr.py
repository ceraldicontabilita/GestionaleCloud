"""Isolated admin-only GET endpoints for the parallel MiniHR view."""
import re
from fastapi import APIRouter, Depends, HTTPException
from app.hr.database import Database
from app.hr.services import minihr
from app.hr.utils.dependencies import require_admin

router = APIRouter(dependencies=[Depends(require_admin)], tags=["MiniHR parallelo"])


@router.get("/employees")
async def employees():
    rows = await Database.get_db().dipendenti.find({"merged_into": {"$exists": False}},
        {"_id": 0, "id": 1, "nome_completo": 1, "nome": 1, "cognome": 1}).to_list(2000)
    roster = sorted((minihr.roster_item(d) for d in rows if d.get("id")), key=lambda d: d["name"])
    return {"employees": roster, "coreVersion": minihr.CORE_VERSION, "mode": "read-only"}


@router.get("/employees/{employee_id}")
async def employee_dossier(employee_id: str):
    db = Database.get_db()
    fields = {k: 1 for k in ("id", "nome_completo", "nome", "cognome", "data_assunzione", "stato", "attivo",
        "data_fine_rapporto", "data_cessazione", "data_dimissione", "data_cessazione_prevista",
        "datore_codice_fiscale", "azienda_codice_fiscale", "merged_into")}
    fields["_id"] = 0
    employee = await db.dipendenti.find_one({"id": employee_id}, fields)
    if not employee or employee.get("merged_into"):
        raise HTTPException(404, "Dipendente non trovato")
    return await minihr.dossier(db, employee)


@router.get("/company-f24/{fiscal_code}")
async def company_f24(fiscal_code: str):
    fiscal_code = fiscal_code.strip().upper()
    if not re.fullmatch(r"(?:\d{11}|[A-Z0-9]{16})", fiscal_code):
        raise HTTPException(422, "Indicare il codice fiscale aziendale completo")
    from app.database import Database as MainDatabase
    return await minihr.company_f24(MainDatabase.get_db(), fiscal_code)

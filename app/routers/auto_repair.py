"""
Router Auto Repair — Operazioni di riparazione automatica dati.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, Query, HTTPException, Depends
from app.database import Database
from app.utils.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Auto Riparazione"])


@router.post("/collega-targa-driver")
async def collega_targa_driver(
    targa: str = Query(..., description="Targa veicolo"),
    driver_id: str = Query(..., description="ID dipendente/driver"),
    fonte: str = Query("manuale", description="Provenienza dell'associazione"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Registra la relazione targa-driver e la propaga ai verbali senza driver."""
    db = Database.get_db()

    # Verifica che il dipendente esista
    dipendente = await db["dipendenti"].find_one({"id": driver_id}, {"_id": 0, "id": 1, "nome_completo": 1, "nome": 1, "cognome": 1})
    if not dipendente:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")

    nome = dipendente.get("nome_completo") or f"{dipendente.get('cognome', '')} {dipendente.get('nome', '')}".strip()

    plate = targa.strip().upper().replace(" ", "")
    now = datetime.now(timezone.utc).isoformat()
    await db["veicoli_noleggio"].update_one(
        {"targa": plate},
        {"$set": {"driver_id": driver_id, "driver": nome, "driver_nome": nome,
                  "driver_assignment_source": fonte, "updated_at": now}},
        upsert=True,
    )
    await db["storico_assegnazioni_veicoli"].update_one(
        {"targa": plate, "driver_id": driver_id, "data_fine": None},
        {"$set": {"targa": plate, "driver_id": driver_id, "driver_nome": nome,
                  "fonte": fonte, "updated_at": now},
         "$setOnInsert": {"data_inizio": "1900-01-01", "created_at": now}},
        upsert=True,
    )
    query = {"targa": {"$regex": f"^{plate}$", "$options": "i"},
             "$or": [{"driver_id": None}, {"driver_id": ""}, {"driver_id": {"$exists": False}}]}
    result = await db["verbali_noleggio"].update_many(
        query,
        {"$set": {
            "driver_id": driver_id,
            "driver_nome": nome,
            "auto_repaired": True,
            "driver_match_basis": fonte,
            "updated_at": now,
        }},
    )
    result_completi = await db["verbali_noleggio_completi"].update_many(query, {"$set": {
        "driver_id": driver_id, "driver": nome, "driver_nome": nome,
        "driver_match_basis": fonte, "updated_at": now,
    }})

    return {
        "message": f"Targa {plate} collegata a {nome}",
        "targa": plate,
        "driver": nome,
        "driver_id": driver_id,
        "verbali_aggiornati": result.modified_count + result_completi.modified_count,
    }


@router.post("/inferisci-targa-driver-da-fatture")
async def inferisci_targa_driver_da_fatture(
    targa: str = Query(...),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Propone/applica solo il driver unico citato esplicitamente con la targa in fattura."""
    import re
    db = Database.get_db()
    plate = targa.strip().upper().replace(" ", "")
    invoices = await db["invoices"].find(
        {"$or": [
            {"descrizione": {"$regex": re.escape(plate), "$options": "i"}},
            {"xml_raw": {"$regex": re.escape(plate), "$options": "i"}},
            {"linee.descrizione": {"$regex": re.escape(plate), "$options": "i"}},
        ]},
        {"_id": 0, "id": 1, "invoice_number": 1, "numero": 1,
         "descrizione": 1, "xml_raw": 1, "linee": 1},
    ).limit(100).to_list(100)
    employees = await db["dipendenti"].find({}, {"_id": 0, "id": 1, "nome": 1,
        "cognome": 1, "nome_completo": 1, "codice_fiscale": 1}).to_list(5000)
    candidates = {}
    evidence = {}
    for invoice in invoices:
        searchable = " ".join(str(invoice.get(k) or "") for k in ("descrizione", "xml_raw", "linee")).casefold()
        for employee in employees:
            full_name = (employee.get("nome_completo") or f"{employee.get('nome','')} {employee.get('cognome','')}").strip()
            cf = str(employee.get("codice_fiscale") or "").strip()
            name_hit = len(full_name) >= 6 and full_name.casefold() in searchable
            cf_hit = len(cf) == 16 and cf.casefold() in searchable
            if name_hit or cf_hit:
                candidates[employee["id"]] = employee
                evidence.setdefault(employee["id"], []).append(invoice.get("id") or invoice.get("invoice_number") or invoice.get("numero"))
    if len(candidates) != 1:
        return {"success": False, "requires_review": True, "targa": plate,
                "candidati": [{"driver_id": key, "driver": (value.get("nome_completo") or f"{value.get('nome','')} {value.get('cognome','')}").strip(), "fatture": evidence.get(key, [])} for key, value in candidates.items()],
                "message": "Nessun driver univoco" if not candidates else "Piu driver compatibili: scelta manuale necessaria"}
    driver_id = next(iter(candidates))
    return await collega_targa_driver(targa=plate, driver_id=driver_id,
        fonte=f"fattura_noleggio:{','.join(str(x) for x in evidence[driver_id] if x)}", _admin=_admin)

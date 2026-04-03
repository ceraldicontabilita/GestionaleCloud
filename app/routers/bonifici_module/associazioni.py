"""
Endpoint aggiuntivi Archivio Bonifici.
Gestisce associazioni fatture/salari ai bonifici, sync IBAN, ricerche per dipendente.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from app.database import Database, Collections

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/archivio-bonifici", tags=["Archivio Bonifici Extra"])


@router.post("/associa-fattura")
async def associa_fattura_a_bonifico(
    bonifico_id: str = Query(...),
    fattura_id: str = Query(...),
    collection: str = Query("invoices")
) -> Dict[str, Any]:
    """Associa una fattura a un bonifico. Supporta sia bonifici_transfers (UUID) sia archivio_bonifici (ObjectId)."""
    db = Database.get_db()

    aggiornamento = {
        "fattura_associata_id": fattura_id,
        "fattura_collection": collection,
        "stato_riconciliazione": "associato",
        "data_associazione": datetime.now(timezone.utc).isoformat()
    }

    # 1) Prova prima su bonifici_transfers (collection moderna, ID stringa UUID)
    result = await db["bonifici_transfers"].update_one(
        {"id": bonifico_id},
        {"$set": aggiornamento}
    )
    if result.modified_count > 0:
        return {"success": True, "message": "Fattura associata al bonifico (transfers)"}

    # 2) Fallback su archivio_bonifici (collection legacy, MongoDB ObjectId)
    from bson import ObjectId
    try:
        result2 = await db["archivio_bonifici"].update_one(
            {"_id": ObjectId(bonifico_id)},
            {"$set": aggiornamento}
        )
        if result2.modified_count > 0:
            return {"success": True, "message": "Fattura associata al bonifico (archivio)"}
    except Exception:
        pass

    raise HTTPException(404, "Bonifico non trovato in nessuna collection")


@router.delete("/disassocia-fattura/{bonifico_id}")
async def disassocia_fattura(bonifico_id: str) -> Dict[str, Any]:
    """Rimuove l'associazione fattura da un bonifico. Supporta entrambe le collection."""
    db = Database.get_db()

    rimozione = {
        "fattura_associata_id": "",
        "fattura_collection": "",
        "data_associazione": ""
    }

    # 1) Prova bonifici_transfers
    result = await db["bonifici_transfers"].update_one(
        {"id": bonifico_id},
        {"$unset": rimozione, "$set": {"stato_riconciliazione": "non_riconciliato"}}
    )
    if result.modified_count > 0:
        return {"success": True, "message": "Associazione fattura rimossa (transfers)"}

    # 2) Fallback archivio_bonifici
    from bson import ObjectId
    try:
        result2 = await db["archivio_bonifici"].update_one(
            {"_id": ObjectId(bonifico_id)},
            {"$unset": rimozione, "$set": {"stato_riconciliazione": "non_riconciliato"}}
        )
        if result2.modified_count > 0:
            return {"success": True, "message": "Associazione fattura rimossa (archivio)"}
    except Exception:
        pass

    raise HTTPException(404, "Bonifico non trovato")


@router.post("/associa-salario")
async def associa_salario_a_bonifico(
    bonifico_id: str = Query(...),
    operazione_id: str = Query(...)
) -> Dict[str, Any]:
    """Associa un'operazione salario a un bonifico."""
    db = Database.get_db()
    from bson import ObjectId
    
    try:
        result = await db["archivio_bonifici"].update_one(
            {"_id": ObjectId(bonifico_id)},
            {"$set": {
                "operazione_salario_id": operazione_id,
                "stato_riconciliazione": "associato_salario",
                "data_associazione": datetime.now(timezone.utc)
            }}
        )
        if result.modified_count == 0:
            raise HTTPException(404, "Bonifico non trovato")
        return {"success": True, "message": "Salario associato al bonifico"}
    except Exception as e:
        if "InvalidId" in str(type(e).__name__):
            raise HTTPException(400, "ID non valido")
        raise


@router.delete("/disassocia-salario/{bonifico_id}")
async def disassocia_salario(bonifico_id: str) -> Dict[str, Any]:
    """Rimuove l'associazione salario da un bonifico."""
    db = Database.get_db()
    from bson import ObjectId
    
    try:
        result = await db["archivio_bonifici"].update_one(
            {"_id": ObjectId(bonifico_id)},
            {"$unset": {
                "operazione_salario_id": "",
                "data_associazione": ""
            }, "$set": {"stato_riconciliazione": "non_riconciliato"}}
        )
        if result.modified_count == 0:
            raise HTTPException(404, "Bonifico non trovato")
        return {"success": True, "message": "Associazione salario rimossa"}
    except Exception as e:
        if "InvalidId" in str(type(e).__name__):
            raise HTTPException(400, "ID non valido")
        raise


@router.get("/fatture-compatibili/{bonifico_id}")
async def get_fatture_compatibili(bonifico_id: str) -> List[Dict[str, Any]]:
    """Trova fatture compatibili con un bonifico (per importo/fornitore simile)."""
    db = Database.get_db()
    from bson import ObjectId
    
    try:
        bonifico = await db["archivio_bonifici"].find_one({"_id": ObjectId(bonifico_id)})
    except Exception:
        raise HTTPException(400, "ID non valido")
    
    if not bonifico:
        raise HTTPException(404, "Bonifico non trovato")
    
    importo = abs(bonifico.get("importo", 0))
    beneficiario = bonifico.get("beneficiario", "")
    
    # Cerca fatture con importo simile (±5%)
    query = {}
    if importo > 0:
        tolerance = importo * 0.05
        query["$or"] = [
            {"totale": {"$gte": importo - tolerance, "$lte": importo + tolerance}},
            {"importo_totale": {"$gte": importo - tolerance, "$lte": importo + tolerance}},
        ]
    
    fatture = await db[Collections.INVOICES].find(
        query, {"_id": 0, "id": 1, "fornitore": 1, "totale": 1, "importo_totale": 1,
                "invoice_number": 1, "invoice_date": 1, "fornitore_denominazione": 1}
    ).to_list(50)
    
    return fatture


@router.get("/operazioni-salari/{bonifico_id}")
async def get_operazioni_salari(bonifico_id: str) -> List[Dict[str, Any]]:
    """Trova operazioni salari compatibili con un bonifico."""
    db = Database.get_db()
    from bson import ObjectId
    
    try:
        bonifico = await db["archivio_bonifici"].find_one({"_id": ObjectId(bonifico_id)})
    except Exception:
        raise HTTPException(400, "ID non valido")
    
    if not bonifico:
        raise HTTPException(404, "Bonifico non trovato")
    
    importo = abs(bonifico.get("importo", 0))
    
    # Cerca in prima_nota_salari
    query = {}
    if importo > 0:
        tolerance = importo * 0.05
        query["netto"] = {"$gte": importo - tolerance, "$lte": importo + tolerance}
    
    operazioni = await db["prima_nota_salari"].find(
        query, {"_id": 0}
    ).to_list(50)
    
    return operazioni


@router.post("/sync-iban-anagrafica")
async def sync_iban_anagrafica() -> Dict[str, Any]:
    """Sincronizza IBAN dai bonifici all'anagrafica dipendenti/fornitori."""
    db = Database.get_db()
    
    # Prendi tutti i bonifici con IBAN
    bonifici = await db["archivio_bonifici"].find(
        {"iban_beneficiario": {"$exists": True, "$ne": None}},
        {"beneficiario": 1, "iban_beneficiario": 1}
    ).to_list(5000)
    
    updated_employees = 0
    updated_suppliers = 0
    
    for b in bonifici:
        iban = b.get("iban_beneficiario", "").strip()
        beneficiario = b.get("beneficiario", "").strip().upper()
        
        if not iban:
            continue
        
        # Prova a matchare con dipendenti
        emp = await db[Collections.EMPLOYEES].find_one({
            "$or": [
                {"nome_completo": {"$regex": beneficiario, "$options": "i"}},
                {"cognome": {"$regex": beneficiario.split()[-1] if beneficiario else "", "$options": "i"}},
            ]
        })
        if emp and not emp.get("iban"):
            await db[Collections.EMPLOYEES].update_one(
                {"_id": emp["_id"]},
                {"$set": {"iban": iban}}
            )
            updated_employees += 1
        
        # Prova con fornitori
        sup = await db[Collections.SUPPLIERS].find_one({
            "denominazione": {"$regex": beneficiario[:10] if len(beneficiario) > 10 else beneficiario, "$options": "i"}
        })
        if sup and not sup.get("iban"):
            await db[Collections.SUPPLIERS].update_one(
                {"_id": sup["_id"]},
                {"$set": {"iban": iban}}
            )
            updated_suppliers += 1
    
    return {
        "success": True,
        "bonifici_analizzati": len(bonifici),
        "dipendenti_aggiornati": updated_employees,
        "fornitori_aggiornati": updated_suppliers
    }


@router.get("/dipendente/{dipendente_id}")
async def get_bonifici_dipendente(dipendente_id: str) -> List[Dict[str, Any]]:
    """Recupera i bonifici associati a un dipendente."""
    db = Database.get_db()
    from bson import ObjectId
    
    # Cerca per ID dipendente o per nome
    try:
        employee = await db[Collections.EMPLOYEES].find_one({"_id": ObjectId(dipendente_id)})
    except Exception:
        employee = await db[Collections.EMPLOYEES].find_one({"id": dipendente_id})
    
    if not employee:
        return []
    
    nome = employee.get("nome_completo", employee.get("cognome", ""))
    
    bonifici = await db["archivio_bonifici"].find({
        "$or": [
            {"operazione_salario_id": {"$exists": True}, "dipendente_id": dipendente_id},
            {"beneficiario": {"$regex": nome, "$options": "i"}} if nome else {},
        ]
    }).sort("data", -1).to_list(100)
    
    # Serializza ObjectId
    for b in bonifici:
        b["_id"] = str(b["_id"])
    
    return bonifici

"""
Endpoint aggiuntivi Archivio Bonifici.
Gestisce associazioni fatture/salari ai bonifici, sync IBAN, ricerche per dipendente.
"""

import re
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from app.database import Database, Collections
from app.services.payment_document_links import (
    collega_bonifico_fatture,
    valuta_fattura_bonifico,
)
from .classification import classifica_bonifico_dipendente

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

    # Validazione: fattura_id non può essere vuoto
    if not fattura_id or not fattura_id.strip():
        raise HTTPException(status_code=422, detail="fattura_id non può essere vuoto")

    bonifico = await _trova_bonifico(db, bonifico_id)
    if not bonifico:
        raise HTTPException(404, "Bonifico non trovato in nessuna collection")
    destinazione = await classifica_bonifico_dipendente(db, bonifico)
    if destinazione["destinazione_dipendente"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "Bonifico destinato a un dipendente: può essere associato solo a un salario, "
                "non a una fattura."
            ),
        )

    fattura = await db[Collections.INVOICES].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        raise HTTPException(404, "Fattura non trovata")
    compatibilita = _valuta_fattura_bonifico(bonifico, fattura)
    if not compatibilita["compatibile"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "Associazione non confermata: servono numero fattura esplicito nella causale, "
                "importo identico al centesimo e identità del fornitore coerente."
            ),
        )

    # 1) Prova prima su bonifici_transfers (collection moderna, ID stringa UUID)
    # Controlla se il bonifico è già associato a un'altra fattura (blocca doppia associazione)
    existing = await db["bonifici_transfers"].find_one({"id": bonifico_id}, {"_id": 0, "fattura_associata_id": 1})
    if existing and existing.get("fattura_associata_id") and existing["fattura_associata_id"] != fattura_id:
        raise HTTPException(
            status_code=409,
            detail=f"Bonifico già associato alla fattura {existing['fattura_associata_id']}. Disassocia prima."
        )

    if existing:
        await collega_bonifico_fatture(db, bonifico, [fattura], auto=False)
        return {"success": True, "message": "Fattura associata al bonifico (transfers)"}

    # 2) Fallback su archivio_bonifici (collection legacy, MongoDB ObjectId)
    from bson import ObjectId
    try:
        result2 = await db["archivio_bonifici"].update_one(
            {"_id": ObjectId(bonifico_id)},
            {"$set": {
                "fattura_associata_id": fattura_id,
                "fattura_collection": collection,
                "fattura_associazione_evidenze": compatibilita["evidenze"],
                "fattura_associazione_score": compatibilita["score"],
                "stato_riconciliazione": "associato",
                "data_associazione": datetime.now(timezone.utc).isoformat(),
            }}
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
        "fattura_associata_id": "", "fattura_id": "", "fattura_ids": "",
        "fattura_collection": "", "data_associazione": "",
        "fattura_associazione_evidenze": "",
    }

    # 1) Prova bonifici_transfers
    transfer = await db["bonifici_transfers"].find_one({"id": bonifico_id}, {"_id": 0})
    invoice_ids = set((transfer or {}).get("fattura_ids") or [])
    if (transfer or {}).get("fattura_id"):
        invoice_ids.add(transfer["fattura_id"])
    result = await db["bonifici_transfers"].update_one(
        {"id": bonifico_id},
        {"$unset": rimozione, "$set": {"fattura_associata": False, "stato_riconciliazione": "non_riconciliato"}}
    )
    if result.matched_count > 0:
        for invoice_id in invoice_ids:
            await db["invoices"].update_one(
                {"id": invoice_id},
                {"$pull": {"bonifico_ids": bonifico_id, "payment_document_ids": bonifico_id},
                 "$unset": {"bonifico_id": ""}, "$set": {"bonifico_associato": False}},
            )
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


async def _trova_bonifico(db, bonifico_id: str) -> Optional[Dict[str, Any]]:
    """Cerca un bonifico in entrambe le collection: bonifici_transfers (attiva,
    id stringa UUID) e archivio_bonifici (legacy, _id ObjectId). I bonifici
    caricati dal flusso attivo (frontend ArchivioBonifici.jsx) hanno sempre id
    UUID: un lookup che provasse solo ObjectId(bonifico_id) fallirebbe sempre
    per loro con InvalidId."""
    bonifico = await db["bonifici_transfers"].find_one({"id": bonifico_id})
    if bonifico:
        return bonifico
    from bson import ObjectId
    try:
        return await db["archivio_bonifici"].find_one({"_id": ObjectId(bonifico_id)})
    except Exception:
        return None


@router.post("/associa-salario")
async def associa_salario_a_bonifico(
    bonifico_id: str = Query(...),
    operazione_id: str = Query(...)
) -> Dict[str, Any]:
    """Associa un'operazione salario a un bonifico. Supporta sia bonifici_transfers (UUID) sia archivio_bonifici (ObjectId)."""
    db = Database.get_db()

    aggiornamento = {
        "operazione_salario_id": operazione_id,
        "stato_riconciliazione": "associato_salario",
        "data_associazione": datetime.now(timezone.utc).isoformat()
    }

    result = await db["bonifici_transfers"].update_one({"id": bonifico_id}, {"$set": aggiornamento})
    if result.modified_count > 0:
        return {"success": True, "message": "Salario associato al bonifico (transfers)"}

    from bson import ObjectId
    try:
        result2 = await db["archivio_bonifici"].update_one(
            {"_id": ObjectId(bonifico_id)},
            {"$set": aggiornamento}
        )
        if result2.modified_count > 0:
            return {"success": True, "message": "Salario associato al bonifico (archivio)"}
    except Exception:
        pass

    raise HTTPException(404, "Bonifico non trovato in nessuna collection")


@router.delete("/disassocia-salario/{bonifico_id}")
async def disassocia_salario(bonifico_id: str) -> Dict[str, Any]:
    """Rimuove l'associazione salario da un bonifico. Supporta entrambe le collection."""
    db = Database.get_db()

    rimozione = {"operazione_salario_id": "", "data_associazione": ""}

    result = await db["bonifici_transfers"].update_one(
        {"id": bonifico_id},
        {"$unset": rimozione, "$set": {"stato_riconciliazione": "non_riconciliato"}}
    )
    if result.modified_count > 0:
        return {"success": True, "message": "Associazione salario rimossa (transfers)"}

    from bson import ObjectId
    try:
        result2 = await db["archivio_bonifici"].update_one(
            {"_id": ObjectId(bonifico_id)},
            {"$unset": rimozione, "$set": {"stato_riconciliazione": "non_riconciliato"}}
        )
        if result2.modified_count > 0:
            return {"success": True, "message": "Associazione salario rimossa (archivio)"}
    except Exception:
        pass

    raise HTTPException(404, "Bonifico non trovato in nessuna collection")


def _compatibilita_score(importo_riferimento: float, importo_confronto: float) -> int:
    """Punteggio 0-100 in base allo scostamento percentuale dall'importo del bonifico,
    coerente con la tolleranza del ±5% usata per filtrare i risultati."""
    if not importo_riferimento:
        return 0
    diff_pct = abs(importo_riferimento - importo_confronto) / importo_riferimento
    return max(0, round((1 - diff_pct / 0.05) * 100))


def _importo_fattura(fattura: Dict[str, Any]) -> float:
    for field in ("total_amount", "totale", "importo_totale"):
        if fattura.get(field) not in (None, ""):
            try:
                return abs(float(fattura[field]))
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _valuta_fattura_bonifico(
    bonifico: Dict[str, Any], fattura: Dict[str, Any]
) -> Dict[str, Any]:
    """Compatibilita' canonica condivisa con import automatico e UI."""
    return valuta_fattura_bonifico(bonifico, fattura)


@router.get("/fatture-compatibili/{bonifico_id}")
async def get_fatture_compatibili(bonifico_id: str) -> Dict[str, Any]:
    """Trova fatture compatibili usando importo e prova del fornitore."""
    db = Database.get_db()

    bonifico = await _trova_bonifico(db, bonifico_id)
    if not bonifico:
        raise HTTPException(404, "Bonifico non trovato")

    destinazione = await classifica_bonifico_dipendente(db, bonifico)
    if destinazione["destinazione_dipendente"]:
        return {
            "fatture_compatibili": [],
            "non_associabile_fattura": True,
            "motivo": destinazione["motivo_destinazione"],
            "dipendente_nome": destinazione.get("dipendente_nome_rilevato"),
        }

    importo = abs(bonifico.get("importo", 0))

    # Preselezione per importo esatto al centesimo. Il filtro semantico sotto
    # richiede inoltre identità fornitore o riferimento esplicito in causale.
    query = {}
    if importo > 0:
        tolerance = 0.004
        query["$or"] = [
            {"total_amount": {"$gte": importo - tolerance, "$lte": importo + tolerance}},
            {"totale": {"$gte": importo - tolerance, "$lte": importo + tolerance}},
            {"importo_totale": {"$gte": importo - tolerance, "$lte": importo + tolerance}},
        ]

    fatture_raw = await db[Collections.INVOICES].find(
        query, {"_id": 0, "id": 1, "fornitore": 1, "supplier_name": 1,
                "cedente_denominazione": 1, "totale": 1, "total_amount": 1,
                "importo_totale": 1, "invoice_number": 1, "invoice_date": 1,
                "fornitore_denominazione": 1}
    ).to_list(50)

    fatture = []
    for f in fatture_raw:
        valutazione = _valuta_fattura_bonifico(bonifico, f)
        if not valutazione["compatibile"]:
            continue
        importo_f = valutazione["importo_fattura"]
        fatture.append({
            "id": f.get("id"),
            "numero_fattura": f.get("invoice_number"),
            "fornitore": (f.get("supplier_name") or f.get("fornitore_denominazione")
                           or f.get("fornitore") or f.get("cedente_denominazione")),
            "data_fattura": f.get("invoice_date"),
            "importo": importo_f,
            "collection": "invoices",
            "compatibilita_score": valutazione["score"],
            "evidenze": valutazione["evidenze"],
        })
    fatture.sort(key=lambda x: x["compatibilita_score"], reverse=True)

    return {"fatture_compatibili": fatture, "non_associabile_fattura": False}


@router.get("/operazioni-salari/{bonifico_id}")
async def get_operazioni_salari(bonifico_id: str) -> Dict[str, Any]:
    """Trova operazioni salari compatibili con un bonifico."""
    db = Database.get_db()

    bonifico = await _trova_bonifico(db, bonifico_id)
    if not bonifico:
        raise HTTPException(404, "Bonifico non trovato")

    importo = abs(bonifico.get("importo", 0))
    beneficiario = bonifico.get("beneficiario") or {}
    beneficiario_iban = (beneficiario.get("iban") or "").strip()

    # Cerca in prima_nota_salari: l'importo può essere in importo_busta o importo_bonifico
    # (il campo 'netto' non esiste in questa collection)
    query = {}
    if importo > 0:
        tolerance = importo * 0.05
        query["$or"] = [
            {"importo_busta": {"$gte": importo - tolerance, "$lte": importo + tolerance}},
            {"importo_bonifico": {"$gte": importo - tolerance, "$lte": importo + tolerance}},
        ]

    operazioni_raw = await db["prima_nota_salari"].find(
        query, {"_id": 0}
    ).to_list(50)

    dipendente_iban_match = None
    matched_nome = None
    if beneficiario_iban:
        emp = await db[Collections.EMPLOYEES].find_one({"iban": beneficiario_iban})
        if emp:
            nome_display = emp.get("nome_completo") or emp.get("cognome") or ""
            dipendente_iban_match = {"nome_display": nome_display}
            matched_nome = nome_display.strip().upper()

    operazioni = []
    for op in operazioni_raw:
        importo_op = op.get("importo_busta") or op.get("importo_bonifico") or 0
        dipendente_nome = (op.get("dipendente") or "").strip().upper()
        operazioni.append({
            **op,
            "importo_display": importo_op,
            "compatibilita_score": _compatibilita_score(importo, importo_op),
            "iban_match": bool(matched_nome) and matched_nome == dipendente_nome,
        })
    operazioni.sort(key=lambda o: o["compatibilita_score"], reverse=True)

    return {"operazioni_compatibili": operazioni, "dipendente_iban_match": dipendente_iban_match}


@router.post("/sync-iban-anagrafica")
async def sync_iban_anagrafica() -> Dict[str, Any]:
    """Sincronizza IBAN dai bonifici all'anagrafica dipendenti/fornitori."""
    db = Database.get_db()

    # Prendi tutti i bonifici con IBAN dalla collection attiva (bonifici_transfers);
    # la legacy 'archivio_bonifici' non viene più alimentata dal flusso di import corrente.
    bonifici = await db["bonifici_transfers"].find(
        {"beneficiario.iban": {"$exists": True, "$ne": None, "$ne": ""}},
        {"beneficiario": 1}
    ).to_list(5000)

    updated_employees = 0
    updated_suppliers = 0

    for b in bonifici:
        beneficiario_obj = b.get("beneficiario") or {}
        iban = (beneficiario_obj.get("iban") or "").strip()
        beneficiario = (beneficiario_obj.get("nome") or "").strip().upper()

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
        "totale_bonifici_analizzati": len(bonifici),
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
            {"beneficiario": {"$regex": re.escape(nome), "$options": "i"}} if nome else {},
        ]
    }).sort("data", -1).to_list(100)
    
    # Serializza ObjectId
    for b in bonifici:
        b["_id"] = str(b["_id"])
    
    return bonifici

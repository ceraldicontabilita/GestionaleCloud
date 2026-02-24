"""
Operazioni Module - Gestione transazioni carta e supervisione.
"""
from fastapi import HTTPException
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from app.database import Database
from .common import RiconciliaCartaRequest


async def lista_transazioni_carta(
    stato: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """Lista transazioni carta di credito."""
    db = Database.get_db()
    
    query = {}
    if stato == "non_riconciliate":
        query["riconciliato"] = {"$ne": True}
    elif stato == "riconciliate":
        query["riconciliato"] = True
    
    transazioni = await db.transazioni_carta.find(query, {"_id": 0}).sort("data", -1).limit(limit).to_list(limit)
    
    return {
        "transazioni": transazioni,
        "totale": len(transazioni)
    }


async def riconcilia_carta_automatico() -> Dict[str, Any]:
    """Riconciliazione automatica transazioni carta."""
    db = Database.get_db()
    
    transazioni = await db.transazioni_carta.find(
        {"riconciliato": {"$ne": True}},
        {"_id": 0}
    ).to_list(1000)
    
    riconciliate = 0
    
    for t in transazioni:
        importo = abs(float(t.get("importo", 0)))
        if importo <= 0:
            continue
        
        # Cerca fattura con importo simile
        fattura = await db.invoices.find_one({
            "pagata": {"$ne": True},
            "$or": [
                {"total_amount": {"$gte": importo * 0.98, "$lte": importo * 1.02}},
                {"importo_totale": {"$gte": importo * 0.98, "$lte": importo * 1.02}}
            ]
        }, {"_id": 0, "id": 1})
        
        if fattura:
            await db.transazioni_carta.update_one(
                {"id": t["id"]},
                {"$set": {
                    "riconciliato": True,
                    "fattura_id": fattura["id"],
                    "data_riconciliazione": datetime.now(timezone.utc).isoformat()
                }}
            )
            await db.invoices.update_one(
                {"id": fattura["id"]},
                {"$set": {"pagata": True, "transazione_carta_id": t["id"]}}
            )
            riconciliate += 1
    
    return {
        "success": True,
        "analizzate": len(transazioni),
        "riconciliate": riconciliate
    }


async def riconcilia_carta_manuale(request: RiconciliaCartaRequest) -> Dict[str, Any]:
    """Riconciliazione manuale transazione carta."""
    db = Database.get_db()
    
    transazione = await db.transazioni_carta.find_one({"id": request.transazione_id})
    if not transazione:
        raise HTTPException(status_code=404, detail="Transazione non trovata")
    
    update_fields = {
        "riconciliato": True,
        "tipo_riconciliazione": "manuale",
        "data_riconciliazione": datetime.now(timezone.utc).isoformat(),
        "note": request.note
    }
    
    if request.tipo == "fattura":
        update_fields["fattura_id"] = request.entita_id
        await db.invoices.update_one(
            {"id": request.entita_id},
            {"$set": {"pagata": True, "transazione_carta_id": request.transazione_id}}
        )
    
    await db.transazioni_carta.update_one(
        {"id": request.transazione_id},
        {"$set": update_fields}
    )
    
    return {"success": True, "transazione_id": request.transazione_id}


async def esegui_supervisione() -> Dict[str, Any]:
    """Esegue supervisione completa del sistema contabile."""
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "controlli": []
    }
    
    # 1. Fatture non pagate
    fatture_non_pagate = await db.invoices.count_documents({"pagata": {"$ne": True}})
    risultati["controlli"].append({
        "nome": "Fatture non pagate",
        "valore": fatture_non_pagate,
        "stato": "warning" if fatture_non_pagate > 50 else "ok"
    })
    
    # 2. Movimenti non riconciliati
    mov_non_ric = await db.estratto_conto_movimenti.count_documents({"riconciliato": {"$ne": True}})
    risultati["controlli"].append({
        "nome": "Movimenti non riconciliati",
        "valore": mov_non_ric,
        "stato": "warning" if mov_non_ric > 100 else "ok"
    })
    
    # 3. Assegni pendenti
    assegni_pendenti = await db.assegni.count_documents({"stato": {"$nin": ["incassato", "annullato"]}})
    risultati["controlli"].append({
        "nome": "Assegni pendenti",
        "valore": assegni_pendenti,
        "stato": "warning" if assegni_pendenti > 20 else "ok"
    })
    
    # 4. Fornitori senza metodo pagamento
    fornitori_senza_metodo = await db.suppliers.count_documents({
        "$or": [
            {"metodo_pagamento": {"$exists": False}},
            {"metodo_pagamento": {"$in": [None, "", "da_configurare"]}}
        ]
    })
    risultati["controlli"].append({
        "nome": "Fornitori senza metodo pagamento",
        "valore": fornitori_senza_metodo,
        "stato": "warning" if fornitori_senza_metodo > 10 else "ok"
    })
    
    # Calcola stato generale
    warnings = sum(1 for c in risultati["controlli"] if c["stato"] == "warning")
    risultati["stato_generale"] = "warning" if warnings > 2 else "ok"
    risultati["warnings_count"] = warnings
    
    return risultati

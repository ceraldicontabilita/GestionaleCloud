"""
Servizio sincronizzazione fornitori dalle fatture.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional


from .constants import Collections
from .validators import normalizza_piva

logger = logging.getLogger(__name__)


async def sincronizza_da_fatture(db, limit: int = 1000) -> Dict[str, Any]:
    """
    Sincronizza i fornitori dalla collection invoices.
    Crea o aggiorna fornitori basandosi sui dati delle fatture XML.
    
    Returns:
        Statistiche sincronizzazione
    """
    risultato = {
        "nuovi": 0,
        "aggiornati": 0,
        "errori": 0,
        "skipped": 0
    }
    
    # Aggrega fornitori unici dalle fatture
    pipeline = [
        {"$match": {"supplier_vat": {"$exists": True, "$ne": None, "$ne": ""}}},
        {"$group": {
            "_id": "$supplier_vat",
            "nome": {"$first": "$supplier_name"},
            "fornitore": {"$first": "$fornitore"},
            "count": {"$sum": 1}
        }},
        {"$limit": limit}
    ]
    
    fornitori_fatture = await db["invoices"].aggregate(pipeline).to_list(limit)
    
    for f in fornitori_fatture:
        try:
            piva = normalizza_piva(f.get("_id", ""))
            if not piva or len(piva) != 11:
                risultato["skipped"] += 1
                continue
            
            # Cerca fornitore esistente
            esistente = await db[Collections.SUPPLIERS].find_one({"partita_iva": piva})
            
            fornitore_data = f.get("fornitore", {}) or {}
            
            if esistente:
                # Aggiorna solo campi mancanti
                update_fields = {}
                
                if not esistente.get("denominazione") and (f.get("nome") or fornitore_data.get("denominazione")):
                    update_fields["denominazione"] = f.get("nome") or fornitore_data.get("denominazione")
                
                if not esistente.get("indirizzo") and fornitore_data.get("indirizzo"):
                    update_fields["indirizzo"] = fornitore_data.get("indirizzo")
                    
                if not esistente.get("cap") and fornitore_data.get("cap"):
                    update_fields["cap"] = fornitore_data.get("cap")
                    
                if not esistente.get("comune") and fornitore_data.get("comune"):
                    update_fields["comune"] = fornitore_data.get("comune")
                    
                if not esistente.get("provincia") and fornitore_data.get("provincia"):
                    update_fields["provincia"] = fornitore_data.get("provincia")
                
                if update_fields:
                    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
                    await db[Collections.SUPPLIERS].update_one(
                        {"partita_iva": piva},
                        {"$set": update_fields}
                    )
                    risultato["aggiornati"] += 1
            else:
                # Crea nuovo fornitore
                nuovo = {
                    "id": str(uuid.uuid4()),
                    "partita_iva": piva,
                    "denominazione": f.get("nome") or fornitore_data.get("denominazione") or "",
                    "ragione_sociale": f.get("nome") or fornitore_data.get("ragione_sociale") or "",
                    "indirizzo": fornitore_data.get("indirizzo", ""),
                    "cap": fornitore_data.get("cap", ""),
                    "comune": fornitore_data.get("comune", ""),
                    "provincia": fornitore_data.get("provincia", ""),
                    "nazione": fornitore_data.get("nazione", "IT"),
                    "attivo": True,
                    "fatture_count": f.get("count", 0),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "source": "sync_fatture"
                }
                await db[Collections.SUPPLIERS].insert_one(nuovo)
                risultato["nuovi"] += 1
                
        except Exception as e:
            logger.warning(f"Errore sync fornitore {f.get('_id')}: {e}")
            risultato["errori"] += 1
    
    return risultato


async def aggiorna_da_invoices(db, supplier_id: str) -> Optional[Dict[str, Any]]:
    """
    Aggiorna un singolo fornitore con dati dalle sue fatture.
    
    Returns:
        Dati aggiornati o None se non trovato
    """
    fornitore = await db[Collections.SUPPLIERS].find_one({"id": supplier_id})
    if not fornitore:
        return None
    
    piva = fornitore.get("partita_iva")
    if not piva:
        return None
    
    # Cerca dati nelle fatture
    fattura = await db["invoices"].find_one(
        {"$or": [{"supplier_vat": piva}, {"cedente_piva": piva}]},
        {"fornitore": 1, "pagamento": 1, "_id": 0}
    )
    
    if not fattura:
        return fornitore
    
    update_fields = {}
    fornitore_data = fattura.get("fornitore", {}) or {}
    pagamento_data = fattura.get("pagamento", {}) or {}
    
    # Aggiorna campi mancanti
    if not fornitore.get("denominazione") and fornitore_data.get("denominazione"):
        update_fields["denominazione"] = fornitore_data.get("denominazione")
    
    if not fornitore.get("email") and fornitore_data.get("email"):
        update_fields["email"] = fornitore_data.get("email")
        
    if not fornitore.get("pec") and fornitore_data.get("pec"):
        update_fields["pec"] = fornitore_data.get("pec")
        
    if not fornitore.get("telefono") and fornitore_data.get("telefono"):
        update_fields["telefono"] = fornitore_data.get("telefono")
    
    if not fornitore.get("iban") and pagamento_data.get("iban"):
        update_fields["iban"] = pagamento_data.get("iban")
    
    if update_fields:
        update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db[Collections.SUPPLIERS].update_one(
            {"id": supplier_id},
            {"$set": update_fields}
        )
        fornitore.update(update_fields)
    
    return fornitore

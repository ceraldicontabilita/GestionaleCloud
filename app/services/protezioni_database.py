"""
Protezioni Database - Previene cancellazioni massive accidentali.

Implementa:
1. Soft delete invece di delete fisico
2. Validazione prima di delete massive
3. Backup automatico prima di operazioni distruttive
4. Audit log delle operazioni
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Soglia oltre la quale una delete è considerata "massiva"
SOGLIA_DELETE_MASSIVA = 10

# Collections protette che richiedono backup prima di delete
COLLECTIONS_PROTETTE = [
    "assegni",
    "invoices", 
    "fatture_ricevute",
    "prima_nota_salari",
    "prima_nota_cassa",
    "prima_nota_banca",
    "estratto_conto_movimenti",
    "suppliers",
    "f24_models",
    "corrispettivi"
]


async def backup_prima_di_delete(db, collection_name: str, query: Dict) -> str:
    """
    Crea backup dei documenti prima di eliminarli.
    
    Returns:
        Nome della collection di backup creata
    """
    # Conta documenti che verranno eliminati
    count = await db[collection_name].count_documents(query)
    
    if count == 0:
        return None
    
    # Crea nome backup
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"{collection_name}_deleted_{timestamp}"
    
    # Copia documenti nel backup
    docs = await db[collection_name].find(query).to_list(count)
    if docs:
        # Aggiungi metadata
        for doc in docs:
            doc["_backup_timestamp"] = datetime.now(timezone.utc).isoformat()
            doc["_backup_reason"] = "pre_delete"
            doc["_original_collection"] = collection_name
        
        await db[backup_name].insert_many(docs)
        logger.info(f"Backup creato: {backup_name} ({count} documenti)")
    
    return backup_name


async def safe_delete_many(db, collection_name: str, query: Dict, force: bool = False) -> Dict[str, Any]:
    """
    Elimina documenti in modo sicuro con backup automatico.
    
    Args:
        db: Database connection
        collection_name: Nome collection
        query: Query di selezione
        force: Se True, salta le protezioni (usare con cautela!)
    
    Returns:
        Dict con risultato operazione
    """
    risultato = {
        "success": False,
        "deleted_count": 0,
        "backup_collection": None,
        "warning": None
    }
    
    # Conta documenti
    count = await db[collection_name].count_documents(query)
    
    if count == 0:
        risultato["success"] = True
        risultato["message"] = "Nessun documento da eliminare"
        return risultato
    
    # Protezione per delete massive
    if count > SOGLIA_DELETE_MASSIVA and not force:
        risultato["warning"] = f"ATTENZIONE: Stai per eliminare {count} documenti da {collection_name}"
        risultato["require_confirmation"] = True
        return risultato
    
    # Backup se collection protetta
    if collection_name in COLLECTIONS_PROTETTE:
        backup_name = await backup_prima_di_delete(db, collection_name, query)
        risultato["backup_collection"] = backup_name
    
    # Esegui delete
    result = await db[collection_name].delete_many(query)
    risultato["success"] = True
    risultato["deleted_count"] = result.deleted_count
    
    # Log audit
    await db.audit_log.insert_one({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operation": "delete_many",
        "collection": collection_name,
        "query": str(query),
        "deleted_count": result.deleted_count,
        "backup_collection": risultato.get("backup_collection")
    })
    
    return risultato


async def soft_delete(db, collection_name: str, query: Dict) -> Dict[str, Any]:
    """
    Soft delete - marca i documenti come eliminati senza rimuoverli fisicamente.
    I documenti possono essere recuperati in seguito.
    """
    result = await db[collection_name].update_many(
        query,
        {
            "$set": {
                "_deleted": True,
                "_deleted_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {
        "success": True,
        "modified_count": result.modified_count,
        "soft_delete": True
    }


async def restore_soft_deleted(db, collection_name: str, query: Dict = None) -> Dict[str, Any]:
    """
    Ripristina documenti soft-deleted.
    """
    if query is None:
        query = {}
    
    query["_deleted"] = True
    
    result = await db[collection_name].update_many(
        query,
        {
            "$unset": {"_deleted": "", "_deleted_at": ""}
        }
    )
    
    return {
        "success": True,
        "restored_count": result.modified_count
    }


async def get_backup_collections(db) -> list:
    """
    Lista tutte le collection di backup disponibili.
    """
    all_collections = await db.list_collection_names()
    backups = [c for c in all_collections if "_backup_" in c or "_deleted_" in c]
    return sorted(backups, reverse=True)


async def restore_from_backup(db, backup_collection: str, target_collection: str = None) -> Dict[str, Any]:
    """
    Ripristina documenti da una collection di backup.
    """
    # Determina collection target
    if target_collection is None:
        # Estrai nome originale dal backup
        parts = backup_collection.split("_backup_")
        if len(parts) > 1:
            target_collection = parts[0]
        else:
            parts = backup_collection.split("_deleted_")
            if len(parts) > 1:
                target_collection = parts[0]
    
    if not target_collection:
        return {"success": False, "error": "Impossibile determinare collection target"}
    
    # Leggi documenti dal backup
    docs = await db[backup_collection].find({}).to_list(10000)
    
    if not docs:
        return {"success": False, "error": "Backup vuoto"}
    
    # Rimuovi campi di backup
    for doc in docs:
        doc.pop("_backup_timestamp", None)
        doc.pop("_backup_reason", None)
        doc.pop("_original_collection", None)
    
    # Inserisci nella collection target
    try:
        result = await db[target_collection].insert_many(docs, ordered=False)
        return {
            "success": True,
            "restored_count": len(result.inserted_ids),
            "target_collection": target_collection
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

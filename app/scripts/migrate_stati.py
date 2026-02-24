"""
Script di Migration per normalizzare tutti gli stati nel database.

Esegui con: python -m app.scripts.migrate_stati

Questo script:
1. Normalizza tutti gli stati di pagamento (pending → da_pagare, paid → pagato, etc.)
2. Normalizza tutti gli stati di riconciliazione
3. Crea un report delle modifiche
"""
import asyncio
import logging
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "azienda_erp_db")

if not MONGO_URL:
    raise ValueError("MONGO_URL environment variable is required")


# ============== MAPPING STATI ==============

MAPPING_PAGAMENTO = {
    "pending": "da_pagare",
    "non_pagata": "da_pagare",
    "to_pay": "da_pagare",
    "DA_PAGARE": "da_pagare",
    "aperto": "da_pagare",
    "paid": "pagato",
    "pagata": "pagato",
    "Pagata": "pagato",
    "Pagato": "pagato",
    "PAGATO": "pagato",
    "saldato": "pagato",
    "annullata": "annullato",
    "cancelled": "annullato",
    "Annullata": "annullato",
}

MAPPING_RICONCILIAZIONE = {
    "reconciled": "riconciliato",
    "collegato": "riconciliato",
    "associato": "riconciliato",
    "matched": "riconciliato",
    "true": "riconciliato",
    "True": "riconciliato",
}


# ============== COLLECTIONS E CAMPI ==============

COLLECTIONS_STATO_PAGAMENTO = [
    ("invoices", "status"),
    ("fatture_ricevute", "stato"),
    ("fatture_ricevute", "stato_pagamento"),
    ("scadenzario", "stato"),
    ("scadenzario", "stato_pagamento"),
    ("f24_unificato", "status"),
    ("f24_models", "status"),
    ("cedolini", "stato_pagamento"),
    ("verbali", "stato"),
    ("adr_multe", "stato"),
]

COLLECTIONS_STATO_RICONCILIAZIONE = [
    ("estratto_conto_movimenti", "riconciliato"),
    ("estratto_conto_movimenti", "stato_riconciliazione"),
    ("assegni", "riconciliato"),
    ("bonifici_stipendi", "riconciliato"),
    ("movimenti_paypal", "riconciliato"),
]


async def migrate_stati():
    """Esegue la migration completa degli stati."""
    
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    logger.info("🚀 Inizio migration stati...")
    logger.info(f"   Database: {DB_NAME}")
    logger.info(f"   Timestamp: {datetime.now(timezone.utc).isoformat()}")
    
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pagamento": {},
        "riconciliazione": {},
        "totale_modificati": 0,
        "errori": []
    }
    
    # MIGRATION STATI PAGAMENTO
    logger.info("\n📋 MIGRATION STATI PAGAMENTO")
    logger.info("=" * 50)
    
    for collection_name, field_name in COLLECTIONS_STATO_PAGAMENTO:
        try:
            collection = db[collection_name]
            
            if collection_name not in await db.list_collection_names():
                logger.info(f"   ⏭️  {collection_name}.{field_name} - collection non esiste, skip")
                continue
            
            modificati = 0
            
            for old_stato, new_stato in MAPPING_PAGAMENTO.items():
                result = await collection.update_many(
                    {field_name: old_stato},
                    {"$set": {
                        field_name: new_stato,
                        "_stato_migrato": True,
                        "_stato_originale": old_stato,
                        "_migration_timestamp": datetime.now(timezone.utc).isoformat()
                    }}
                )
                modificati += result.modified_count
                
                if result.modified_count > 0:
                    logger.info(f"   ✅ {collection_name}.{field_name}: '{old_stato}' → '{new_stato}' ({result.modified_count})")
            
            report["pagamento"][f"{collection_name}.{field_name}"] = modificati
            report["totale_modificati"] += modificati
            
            if modificati == 0:
                logger.info(f"   ⚪ {collection_name}.{field_name} - nessuna modifica necessaria")
                
        except Exception as e:
            error_msg = f"Errore {collection_name}.{field_name}: {str(e)}"
            logger.error(f"   ❌ {error_msg}")
            report["errori"].append(error_msg)
    
    # MIGRATION STATI RICONCILIAZIONE
    logger.info("\n📋 MIGRATION STATI RICONCILIAZIONE")
    logger.info("=" * 50)
    
    for collection_name, field_name in COLLECTIONS_STATO_RICONCILIAZIONE:
        try:
            collection = db[collection_name]
            
            if collection_name not in await db.list_collection_names():
                logger.info(f"   ⏭️  {collection_name}.{field_name} - collection non esiste, skip")
                continue
            
            modificati = 0
            
            for old_stato, new_stato in MAPPING_RICONCILIAZIONE.items():
                result = await collection.update_many(
                    {field_name: old_stato},
                    {"$set": {
                        field_name: new_stato,
                        "_stato_migrato": True,
                        "_stato_originale": old_stato,
                        "_migration_timestamp": datetime.now(timezone.utc).isoformat()
                    }}
                )
                modificati += result.modified_count
                
                if result.modified_count > 0:
                    logger.info(f"   ✅ {collection_name}.{field_name}: '{old_stato}' → '{new_stato}' ({result.modified_count})")
            
            # Normalizza booleani True → "riconciliato"
            result = await collection.update_many(
                {field_name: True},
                {"$set": {
                    field_name: "riconciliato",
                    "_stato_migrato": True,
                    "_stato_originale": "True (boolean)",
                    "_migration_timestamp": datetime.now(timezone.utc).isoformat()
                }}
            )
            if result.modified_count > 0:
                modificati += result.modified_count
                logger.info(f"   ✅ {collection_name}.{field_name}: True → 'riconciliato' ({result.modified_count})")
            
            # Normalizza booleani False → "non_riconciliato"
            result = await collection.update_many(
                {field_name: False},
                {"$set": {
                    field_name: "non_riconciliato",
                    "_stato_migrato": True,
                    "_stato_originale": "False (boolean)",
                    "_migration_timestamp": datetime.now(timezone.utc).isoformat()
                }}
            )
            if result.modified_count > 0:
                modificati += result.modified_count
                logger.info(f"   ✅ {collection_name}.{field_name}: False → 'non_riconciliato' ({result.modified_count})")
            
            report["riconciliazione"][f"{collection_name}.{field_name}"] = modificati
            report["totale_modificati"] += modificati
            
            if modificati == 0:
                logger.info(f"   ⚪ {collection_name}.{field_name} - nessuna modifica necessaria")
                
        except Exception as e:
            error_msg = f"Errore {collection_name}.{field_name}: {str(e)}"
            logger.error(f"   ❌ {error_msg}")
            report["errori"].append(error_msg)
    
    # SALVA REPORT
    await db["_migration_reports"].insert_one(report)
    
    # RIEPILOGO
    logger.info("\n" + "=" * 50)
    logger.info("📊 RIEPILOGO MIGRATION")
    logger.info("=" * 50)
    logger.info(f"   Totale documenti modificati: {report['totale_modificati']}")
    logger.info(f"   Errori: {len(report['errori'])}")
    
    if report['errori']:
        logger.warning("   ⚠️  Errori riscontrati:")
        for err in report['errori']:
            logger.warning(f"      - {err}")
    
    logger.info("\n✅ Migration completata!")
    logger.info("   Report salvato in: _migration_reports")
    
    client.close()
    return report


async def rollback_migration():
    """Rollback della migration (ripristina stati originali)."""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    logger.info("⚠️  ROLLBACK MIGRATION STATI...")
    
    all_collections = await db.list_collection_names()
    
    for collection_name in all_collections:
        collection = db[collection_name]
        migrati = await collection.find({"_stato_migrato": True}).to_list(None)
        
        for doc in migrati:
            stato_originale = doc.get("_stato_originale")
            if stato_originale and stato_originale != "True (boolean)" and stato_originale != "False (boolean)":
                for field in ["status", "stato", "stato_pagamento", "riconciliato", "stato_riconciliazione"]:
                    if field in doc:
                        await collection.update_one(
                            {"_id": doc["_id"]},
                            {
                                "$set": {field: stato_originale},
                                "$unset": {
                                    "_stato_migrato": "",
                                    "_stato_originale": "",
                                    "_migration_timestamp": ""
                                }
                            }
                        )
                        break
        
        if migrati:
            logger.info(f"   Rollback {collection_name}: {len(migrati)} documenti")
    
    logger.info("✅ Rollback completato")
    client.close()


async def verify_migration():
    """Verifica che non ci siano più vecchi stati nel database."""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    logger.info("🔍 VERIFICA MIGRATION STATI...")
    
    problemi = []
    vecchi_stati_pagamento = ["pending", "non_pagata", "to_pay", "paid", "pagata", "Pagata", "Pagato"]
    vecchi_stati_riconciliazione = ["reconciled", "collegato", "associato"]
    
    for collection_name, field_name in COLLECTIONS_STATO_PAGAMENTO:
        try:
            collection = db[collection_name]
            count = await collection.count_documents({field_name: {"$in": vecchi_stati_pagamento}})
            if count > 0:
                problemi.append(f"{collection_name}.{field_name}: {count} documenti con vecchi stati")
        except Exception:
            pass
    
    for collection_name, field_name in COLLECTIONS_STATO_RICONCILIAZIONE:
        try:
            collection = db[collection_name]
            count = await collection.count_documents({field_name: {"$in": vecchi_stati_riconciliazione}})
            if count > 0:
                problemi.append(f"{collection_name}.{field_name}: {count} documenti con vecchi stati")
        except Exception:
            pass
    
    if problemi:
        logger.warning("⚠️  Trovati vecchi stati:")
        for p in problemi:
            logger.warning(f"   - {p}")
    else:
        logger.info("✅ Tutti gli stati sono normalizzati!")
    
    client.close()
    return problemi


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--rollback":
            asyncio.run(rollback_migration())
        elif sys.argv[1] == "--verify":
            asyncio.run(verify_migration())
        else:
            print("Uso: python -m app.scripts.migrate_stati [--rollback|--verify]")
    else:
        asyncio.run(migrate_stati())

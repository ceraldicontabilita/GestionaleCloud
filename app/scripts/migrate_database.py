"""
Script di migrazione database per unificare le collezioni.
Eseguire con: python -m app.scripts.migrate_database
"""
import asyncio
import os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ.get('MONGO_URL')
DB_NAME = os.environ.get('DB_NAME', 'azienda_erp_db')

if not MONGO_URL:
    raise ValueError("MONGO_URL environment variable is required - use MongoDB Atlas connection string")


async def migrate_estratto_conto():
    """
    Migra tutti i documenti da 'estratto_conto' a 'estratto_conto_movimenti'.
    Aggiunge un campo 'migrated_from' per tracciabilità.
    """
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    old_coll = db['estratto_conto']
    new_coll = db['estratto_conto_movimenti']
    
    # Conta documenti
    old_count = await old_coll.count_documents({})
    new_count = await new_coll.count_documents({})
    
    print("📊 Stato attuale:")
    print(f"   estratto_conto (vecchio): {old_count} documenti")
    print(f"   estratto_conto_movimenti (nuovo): {new_count} documenti")
    
    if old_count == 0:
        print("✅ Nessun documento da migrare")
        return
    
    # Ottieni tutti i documenti vecchi
    old_docs = await old_coll.find({}, {'_id': 0}).to_list(None)
    
    # Ottieni ID esistenti nella nuova collezione per evitare duplicati
    existing_ids = set()
    async for doc in new_coll.find({}, {'id': 1, '_id': 0}):
        if doc.get('id'):
            existing_ids.add(doc['id'])
    
    migrated = 0
    skipped = 0
    
    for doc in old_docs:
        doc_id = doc.get('id')
        
        # Salta se già esiste
        if doc_id in existing_ids:
            skipped += 1
            continue
        
        # Normalizza il documento
        normalized = {
            'id': doc_id,
            'data': doc.get('data'),
            'descrizione': doc.get('descrizione'),
            'descrizione_originale': doc.get('descrizione'),
            'importo': doc.get('importo'),
            'tipo': doc.get('tipo', 'movimento'),
            'categoria': doc.get('categoria'),
            'banca': doc.get('banca', 'principale'),
            'source': doc.get('source', 'migrazione'),
            'created_at': doc.get('created_at', datetime.now(timezone.utc).isoformat()),
            'migrated_from': 'estratto_conto',
            'migrated_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Copia campi extra se presenti
        for key in ['fornitore', 'ragione_sociale', 'numero_fattura', 'data_pagamento', 
                    'rapporto', 'divisa', 'hashtag', 'statement_id']:
            if key in doc:
                normalized[key] = doc[key]
        
        await new_coll.insert_one(normalized.copy())
        migrated += 1
    
    print("\n✅ Migrazione completata:")
    print(f"   Migrati: {migrated}")
    print(f"   Saltati (duplicati): {skipped}")
    
    # Verifica finale
    final_count = await new_coll.count_documents({})
    print(f"   Totale in estratto_conto_movimenti: {final_count}")
    
    return {'migrated': migrated, 'skipped': skipped}


async def create_collection_alias():
    """
    Crea una view 'estratto_conto' che punta a 'estratto_conto_movimenti'.
    Questo permette la retrocompatibilità senza modificare il codice.
    """
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    # Prima rinomina la vecchia collezione
    try:
        await db['estratto_conto'].rename('estratto_conto_backup')
        print("📦 Collezione vecchia rinominata in 'estratto_conto_backup'")
    except Exception as e:
        print(f"⚠️ Impossibile rinominare (potrebbe già essere stato fatto): {e}")
    
    # Crea una view che punta alla nuova collezione
    try:
        await db.command({
            'create': 'estratto_conto',
            'viewOn': 'estratto_conto_movimenti',
            'pipeline': []
        })
        print("✅ View 'estratto_conto' creata -> punta a 'estratto_conto_movimenti'")
    except Exception as e:
        print(f"⚠️ Impossibile creare view: {e}")


async def main():
    print("🚀 Inizio migrazione database ERP")
    print("=" * 50)
    
    # Step 1: Migra i dati
    await migrate_estratto_conto()
    
    print("\n" + "=" * 50)
    print("✅ Migrazione completata!")
    print("\n📝 Prossimi passi manuali:")
    print("   1. Verificare che estratto_conto_movimenti contenga tutti i dati")
    print("   2. Aggiornare i riferimenti nel codice")
    print("   3. Rimuovere la vecchia collezione: db.estratto_conto.drop()")


if __name__ == "__main__":
    asyncio.run(main())

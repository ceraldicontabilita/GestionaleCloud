"""
Script di Migrazione: Unificazione Collection fornitori e suppliers.

Questo script:
1. Esegue il merge dei dati da 'fornitori' a 'suppliers'
2. Mantiene 'suppliers' come collection principale
3. Crea backup della collection 'fornitori'
4. Aggiorna i riferimenti nel codice

Eseguire una sola volta dopo backup del database.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from app.database import Database

logger = logging.getLogger(__name__)


async def unifica_fornitori_suppliers() -> Dict[str, Any]:
    """
    Unifica le collection 'fornitori' e 'suppliers'.
    
    Strategia:
    - 'suppliers' è la collection target (più completa)
    - I dati da 'fornitori' vengono mergiati in 'suppliers'
    - Se un fornitore esiste in entrambe (match per P.IVA), si fa merge dei campi
    - Se esiste solo in 'fornitori', viene copiato in 'suppliers'
    
    Returns:
        Dict con statistiche della migrazione
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fornitori_letti": 0,
        "suppliers_esistenti": 0,
        "mergiati": 0,
        "nuovi_aggiunti": 0,
        "errori": [],
        "dettagli_merge": []
    }
    
    try:
        # 1. Conta documenti esistenti
        risultati["fornitori_letti"] = await db.fornitori.count_documents({})
        risultati["suppliers_esistenti"] = await db.suppliers.count_documents({})
        
        # 2. Crea backup della collection fornitori
        backup_name = f"fornitori_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        fornitori_docs = await db.fornitori.find({}).to_list(10000)
        
        if fornitori_docs:
            await db[backup_name].insert_many(fornitori_docs)
            risultati["backup_creato"] = backup_name
        
        # 3. Crea indice per P.IVA su suppliers se non esiste
        await db.suppliers.create_index("partita_iva", sparse=True)
        
        # 4. Per ogni documento in 'fornitori', cerca match in 'suppliers'
        for forn in fornitori_docs:
            
            # Identifica il fornitore per P.IVA o denominazione
            piva = forn.get("partita_iva") or forn.get("piva") or ""
            denominazione = forn.get("denominazione") or forn.get("ragione_sociale") or ""
            
            # Cerca match in suppliers
            supplier = None
            if piva:
                supplier = await db.suppliers.find_one({
                    "$or": [
                        {"partita_iva": piva},
                        {"piva": piva},
                        {"supplier_vat": piva}
                    ]
                })
            
            if not supplier and denominazione:
                supplier = await db.suppliers.find_one({
                    "$or": [
                        {"denominazione": {"$regex": f"^{denominazione[:30]}", "$options": "i"}},
                        {"ragione_sociale": {"$regex": f"^{denominazione[:30]}", "$options": "i"}},
                        {"nome": {"$regex": f"^{denominazione[:30]}", "$options": "i"}}
                    ]
                })
            
            if supplier:
                # MERGE: aggiorna supplier con campi mancanti da fornitori
                update_fields = {}
                
                # Campi da copiare se mancanti in supplier
                campi_da_mergiare = [
                    "metodo_pagamento", "iban", "bic", "email", "pec",
                    "telefono", "indirizzo", "cap", "comune", "provincia",
                    "nazione", "codice_destinatario", "note", "categoria"
                ]
                
                for campo in campi_da_mergiare:
                    valore_forn = forn.get(campo)
                    valore_supp = supplier.get(campo)
                    
                    # Se il campo esiste in fornitori e manca/è vuoto in suppliers
                    if valore_forn and not valore_supp:
                        update_fields[campo] = valore_forn
                
                if update_fields:
                    update_fields["migrato_da_fornitori"] = True
                    update_fields["data_migrazione"] = datetime.now(timezone.utc).isoformat()
                    
                    await db.suppliers.update_one(
                        {"_id": supplier["_id"]},
                        {"$set": update_fields}
                    )
                    
                    risultati["mergiati"] += 1
                    risultati["dettagli_merge"].append({
                        "piva": piva,
                        "denominazione": denominazione[:30],
                        "campi_aggiornati": list(update_fields.keys())
                    })
            else:
                # NUOVO: copia da fornitori a suppliers
                # Normalizza i nomi dei campi
                nuovo_supplier = {
                    "id": forn.get("id") or str(forn.get("_id", "")),
                    "partita_iva": piva,
                    "denominazione": denominazione,
                    "ragione_sociale": forn.get("ragione_sociale") or denominazione,
                    "metodo_pagamento": forn.get("metodo_pagamento"),
                    "iban": forn.get("iban"),
                    "bic": forn.get("bic"),
                    "email": forn.get("email"),
                    "pec": forn.get("pec"),
                    "telefono": forn.get("telefono"),
                    "indirizzo": forn.get("indirizzo"),
                    "cap": forn.get("cap"),
                    "comune": forn.get("comune") or forn.get("citta"),
                    "provincia": forn.get("provincia"),
                    "nazione": forn.get("nazione") or "IT",
                    "codice_destinatario": forn.get("codice_destinatario"),
                    "categoria": forn.get("categoria"),
                    "note": forn.get("note"),
                    "migrato_da_fornitori": True,
                    "data_migrazione": datetime.now(timezone.utc).isoformat(),
                    "created_at": forn.get("created_at") or datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                
                # Rimuovi campi None
                nuovo_supplier = {k: v for k, v in nuovo_supplier.items() if v is not None}
                
                try:
                    await db.suppliers.insert_one(nuovo_supplier)
                    risultati["nuovi_aggiunti"] += 1
                except Exception as e:
                    # Probabilmente duplicato
                    risultati["errori"].append(f"Errore insert {piva}: {str(e)}")
        
        # 5. Statistiche finali
        risultati["suppliers_finali"] = await db.suppliers.count_documents({})
        risultati["successo"] = True
        
    except Exception as e:
        logger.exception(f"Errore unificazione: {e}")
        risultati["errori"].append(str(e))
        risultati["successo"] = False
    
    return risultati


async def verifica_unificazione() -> Dict[str, Any]:
    """
    Verifica lo stato dell'unificazione.
    """
    db = Database.get_db()
    
    return {
        "suppliers_count": await db.suppliers.count_documents({}),
        "fornitori_count": await db.fornitori.count_documents({}),
        "migrati": await db.suppliers.count_documents({"migrato_da_fornitori": True}),
        "con_metodo_pagamento": await db.suppliers.count_documents({"metodo_pagamento": {"$ne": None}}),
        "con_iban": await db.suppliers.count_documents({"iban": {"$ne": None}})
    }


if __name__ == "__main__":
    async def main():
        from app.database import Database
        await Database.connect()
        
        print("Avvio unificazione fornitori/suppliers...")
        risultati = await unifica_fornitori_suppliers()
        print(f"Risultati: {risultati}")
        
        print("\nVerifica:")
        verifica = await verifica_unificazione()
        print(f"Verifica: {verifica}")
    
    asyncio.run(main())

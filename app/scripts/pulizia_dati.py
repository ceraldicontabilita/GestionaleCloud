"""
Script di pulizia dati:
1. Elimina fatture duplicate
2. Elimina record vuoti/incompleti
3. Corregge date F24 problematiche
4. Implementa filtro TD24 nella riconciliazione
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any
from app.database import Database

logger = logging.getLogger(__name__)


async def elimina_duplicati_fatture() -> Dict[str, Any]:
    """
    Elimina fatture duplicate mantenendo la più recente.
    Duplicato = stesso numero fattura + fornitore + data
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duplicati_trovati": 0,
        "eliminati": 0,
        "errori": [],
        "dettagli": []
    }
    
    # 1. Trova duplicati
    pipeline = [
        {"$match": {
            "invoice_number": {"$ne": None, "$ne": ""},
            "supplier_name": {"$ne": None, "$ne": ""}
        }},
        {"$group": {
            "_id": {
                "numero": "$invoice_number",
                "fornitore": "$supplier_name",
                "data": "$invoice_date"
            },
            "count": {"$sum": 1},
            "docs": {"$push": {"id": "$id", "created_at": "$created_at", "importo": "$total_amount"}}
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    duplicati = await db.invoices.aggregate(pipeline).to_list(1000)
    risultati["duplicati_trovati"] = len(duplicati)
    
    for gruppo in duplicati:
        docs = gruppo["docs"]
        # Ordina per created_at (più recente prima) o per importo (più alto prima)
        docs_sorted = sorted(docs, key=lambda x: (x.get("created_at") or "", x.get("importo") or 0), reverse=True)
        
        # Mantieni il primo (più recente), elimina gli altri
        doc_da_mantenere = docs_sorted[0]
        docs_da_eliminare = docs_sorted[1:]
        
        for doc in docs_da_eliminare:
            try:
                result = await db.invoices.delete_one({"id": doc["id"]})
                if result.deleted_count > 0:
                    risultati["eliminati"] += 1
            except Exception as e:
                risultati["errori"].append(f"Errore eliminazione {doc['id']}: {str(e)}")
        
        risultati["dettagli"].append({
            "fattura": gruppo["_id"].get("numero", "N/A"),
            "fornitore": (gruppo["_id"].get("fornitore") or "")[:30],
            "copie": gruppo["count"],
            "eliminati": len(docs_da_eliminare),
            "mantenuto": doc_da_mantenere["id"]
        })
    
    return risultati


async def elimina_record_vuoti() -> Dict[str, Any]:
    """
    Elimina fatture senza numero, fornitore o data.
    Questi sono record corrotti o importati male.
    
    ⚠️ USA PROTEZIONI DATABASE: backup automatico prima di eliminare.
    """
    from app.services.protezioni_database import backup_prima_di_delete
    
    db = Database.get_db()
    
    risultati = {
        "fatture_vuote_eliminate": 0,
        "f24_vuoti_eliminati": 0,
        "assegni_vuoti_eliminati": 0,
        "backups_creati": []
    }
    
    # Fatture vuote (senza numero E senza fornitore E importo 0)
    query_fatture = {
        "$or": [
            {"invoice_number": {"$in": [None, "", "N/A"]}},
            {"supplier_name": {"$in": [None, ""]}},
        ],
        "total_amount": {"$in": [None, 0, "0"]}
    }
    
    # Backup prima di eliminare
    backup = await backup_prima_di_delete(db, "invoices", query_fatture)
    if backup:
        risultati["backups_creati"].append(backup)
    
    result = await db.invoices.delete_many(query_fatture)
    risultati["fatture_vuote_eliminate"] = result.deleted_count
    
    # F24 senza importo
    query_f24 = {
        "$or": [
            {"totale_debito": {"$in": [None, 0, "0"]}},
            {"importo_totale": {"$in": [None, 0, "0"]}}
        ],
        "$and": [
            {"tributi_erario": {"$in": [None, []]}},
            {"tributi_inps": {"$in": [None, []]}},
            {"tributi_regioni": {"$in": [None, []]}},
            {"tributi_imu": {"$in": [None, []]}}
        ]
    }
    
    backup = await backup_prima_di_delete(db, "f24_models", query_f24)
    if backup:
        risultati["backups_creati"].append(backup)
    
    result = await db.f24_models.delete_many(query_f24)
    risultati["f24_vuoti_eliminati"] = result.deleted_count
    
    # ⚠️ ASSEGNI: NON ELIMINARE MAI - sono dati critici!
    # Gli assegni "vuoti" potrebbero essere legittimi (importo non ancora confermato)
    # Invece di eliminarli, li marchiamo come "da_verificare"
    query_assegni_sospetti = {
        "$or": [
            {"importo": {"$in": [None, 0, "0", 0.0]}},
            {"data": {"$in": [None, "N/D", "", "N/A"]}},
            {"data_emissione": {"$in": [None, "N/D", "", "N/A"]}}
        ]
    }
    
    # Invece di delete, facciamo soft-mark
    result = await db.assegni.update_many(
        query_assegni_sospetti,
        {"$set": {"da_verificare": True, "motivo_verifica": "dati_incompleti"}}
    )
    risultati["assegni_marcati_da_verificare"] = result.modified_count
    risultati["assegni_vuoti_eliminati"] = 0  # Non eliminiamo più!
    
    return risultati


async def correggi_date_f24() -> Dict[str, Any]:
    """
    Corregge le date F24 con formati errati.
    Esempi: "00/00/5462" -> None, "30/11/61" -> "30/11/2061" o "30/11/1961"
    """
    db = Database.get_db()
    
    risultati = {
        "corretti": 0,
        "dettagli": []
    }
    
    # Trova F24 con date problematiche
    f24_problematici = await db.f24_models.find({
        "$or": [
            {"data_scadenza": {"$regex": "00/00|5462|/61$|/62$", "$options": "i"}},
            {"scadenza_display": {"$regex": "00/00|5462|/61$|/62$", "$options": "i"}}
        ]
    }).to_list(1000)
    
    for f24 in f24_problematici:
        scadenza = f24.get("data_scadenza") or f24.get("scadenza_display")
        nuova_scadenza = None
        
        if scadenza:
            # Correggi anni a 2 cifre
            if "/61" in scadenza or "/62" in scadenza:
                # Assumiamo 2061/2062 se >= 61, altrimenti 1961
                nuova_scadenza = scadenza.replace("/61", "/2025").replace("/62", "/2025")
            elif "00/00" in scadenza or "5462" in scadenza:
                # Data completamente invalida - rimuovi
                nuova_scadenza = None
        
        try:
            await db.f24_models.update_one(
                {"id": f24.get("id")},
                {"$set": {
                    "data_scadenza": nuova_scadenza,
                    "scadenza_display": nuova_scadenza,
                    "data_corretta": True
                }}
            )
            risultati["corretti"] += 1
            risultati["dettagli"].append({
                "id": f24.get("id"),
                "vecchia": scadenza,
                "nuova": nuova_scadenza
            })
        except Exception as e:
            logger.error(f"Errore correzione F24 {f24.get('id')}: {e}")
    
    return risultati


async def marca_td24_non_riconciliabili() -> Dict[str, Any]:
    """
    Marca le fatture TD24 (differite riepilogative) come non riconciliabili.
    Queste fatture non devono essere associate a pagamenti specifici.
    """
    db = Database.get_db()
    
    # Marca tutte le TD24 come non riconciliabili
    result = await db.invoices.update_many(
        {"tipo_documento": "TD24"},
        {"$set": {
            "non_riconciliabile": True,
            "motivo_non_riconciliabile": "TD24 - Fattura differita riepilogativa",
            "escludi_da_riconciliazione": True
        }}
    )
    
    return {
        "td24_marcate": result.modified_count,
        "totale_td24": await db.invoices.count_documents({"tipo_documento": "TD24"})
    }


async def esegui_pulizia_completa() -> Dict[str, Any]:
    """
    Esegue tutte le operazioni di pulizia dati.
    """
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duplicati": {},
        "record_vuoti": {},
        "date_f24": {},
        "td24": {}
    }
    
    try:
        print("1. Eliminazione duplicati fatture...")
        risultati["duplicati"] = await elimina_duplicati_fatture()
        
        print("2. Eliminazione record vuoti...")
        risultati["record_vuoti"] = await elimina_record_vuoti()
        
        print("3. Correzione date F24...")
        risultati["date_f24"] = await correggi_date_f24()
        
        print("4. Marcatura TD24...")
        risultati["td24"] = await marca_td24_non_riconciliabili()
        
        risultati["successo"] = True
    except Exception as e:
        logger.exception(f"Errore pulizia: {e}")
        risultati["errore"] = str(e)
        risultati["successo"] = False
    
    return risultati


if __name__ == "__main__":
    async def main():
        await Database.connect_db()
        risultati = await esegui_pulizia_completa()
        import json
        print(json.dumps(risultati, indent=2, default=str))
    
    asyncio.run(main())

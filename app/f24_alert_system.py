"""
Sistema Alert F24 con Riconciliazione Bancaria
Gestisce notifiche scadenze e riconciliazione pagamenti
"""
from datetime import datetime, timedelta, timezone
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


async def check_f24_scadenze(db, username: str) -> List[Dict]:
    """
    Verifica F24 in scadenza o scaduti non pagati
    Returns: Lista alert da notificare
    """
    today = datetime.now(timezone.utc).date()
    alerts = []
    
    try:
        # Query F24 non pagati
        f24_non_pagati = await db.f24.find({
            "user_id": username,
            "status": {"$ne": "paid"},  # Non pagati
            "importo_totale": {"$gt": 0}
        }).to_list(1000)
        
        for f24 in f24_non_pagati:
            scadenza_str = f24.get("scadenza") or f24.get("data_versamento")
            if not scadenza_str:
                continue
            
            # Parse scadenza
            try:
                scadenza = datetime.fromisoformat(scadenza_str.replace("Z", "+00:00")).date()
            except:
                continue
            
            giorni_mancanti = (scadenza - today).days
            
            # Genera alert in base ai giorni mancanti
            alert_data = {
                "f24_id": f24.get("id"),
                "tipo": f24.get("tipo_f24", "F24"),
                "descrizione": f24.get("descrizione", ""),
                "importo": f24.get("importo_totale", 0),
                "scadenza": scadenza_str,
                "giorni_mancanti": giorni_mancanti,
                "codici_tributo": f24.get("codici_tributo", []),
                "mese_riferimento": f24.get("mese_riferimento", ""),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            if giorni_mancanti < 0:
                # SCADUTO
                alert_data["severity"] = "critical"
                alert_data["message"] = f"⚠️ F24 {f24.get('tipo_f24', '')} mese di {f24.get('mese_riferimento', '')} NON PAGATO (scaduto da {abs(giorni_mancanti)} giorni)"
                alerts.append(alert_data)
            elif giorni_mancanti == 0:
                # OGGI
                alert_data["severity"] = "high"
                alert_data["message"] = f"🔴 F24 {f24.get('tipo_f24', '')} mese di {f24.get('mese_riferimento', '')} scade OGGI!"
                alerts.append(alert_data)
            elif giorni_mancanti <= 3:
                # ENTRO 3 GIORNI
                alert_data["severity"] = "high"
                alert_data["message"] = f"⚠️ F24 {f24.get('tipo_f24', '')} mese di {f24.get('mese_riferimento', '')} scade tra {giorni_mancanti} giorni"
                alerts.append(alert_data)
            elif giorni_mancanti <= 7:
                # ENTRO 7 GIORNI
                alert_data["severity"] = "medium"
                alert_data["message"] = f"⏰ F24 {f24.get('tipo_f24', '')} mese di {f24.get('mese_riferimento', '')} scade tra {giorni_mancanti} giorni"
                alerts.append(alert_data)
        
        return alerts
        
    except Exception as e:
        logger.error(f"Errore check scadenze F24: {str(e)}")
        return []


async def riconcilia_f24_con_banca(db, username: str, f24_id: str, movimento_bancario_id: str) -> Dict:
    """
    Riconcilia un F24 con un movimento bancario
    Marca F24 come pagato ed elimina alert
    """
    try:
        # Trova F24
        f24 = await db.f24.find_one({"id": f24_id, "user_id": username})
        if not f24:
            return {"success": False, "error": "F24 non trovato"}
        
        # Trova movimento bancario
        movimento = await db.prima_nota_banca.find_one({"id": movimento_bancario_id})
        if not movimento:
            return {"success": False, "error": "Movimento bancario non trovato"}
        
        # Verifica importo simile (tolleranza 1 euro)
        importo_f24 = abs(f24.get("importo_totale", 0))
        importo_movimento = abs(movimento.get("importo", 0))
        
        if abs(importo_f24 - importo_movimento) > 1.0:
            logger.warning(f"Importi diversi F24 €{importo_f24} vs Banca €{importo_movimento}")
        
        # Aggiorna F24 come pagato
        await db.f24.update_one(
            {"id": f24_id},
            {"$set": {
                "status": "paid",
                "paid_date": datetime.now(timezone.utc).isoformat(),
                "bank_movement_id": movimento_bancario_id,
                "reconciled_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # Elimina alert associati
        await db.f24_alerts.delete_many({"f24_id": f24_id})
        
        logger.info(f"✅ F24 {f24_id} riconciliato con movimento bancario {movimento_bancario_id}")
        
        return {
            "success": True,
            "message": "F24 riconciliato correttamente",
            "f24_id": f24_id,
            "importo": importo_f24,
            "alert_eliminati": True
        }
        
    except Exception as e:
        logger.error(f"Errore riconciliazione F24: {str(e)}")
        return {"success": False, "error": str(e)}


async def auto_riconcilia_f24(db, username: str) -> Dict:
    """
    Riconciliazione automatica F24 con movimenti bancari
    Cerca movimenti bancari con causale F24 e importo simile
    """
    riconciliati = 0
    errori = 0
    
    try:
        # Trova F24 non pagati
        f24_non_pagati = await db.f24.find({
            "user_id": username,
            "status": {"$ne": "paid"}
        }).to_list(1000)
        
        # Trova movimenti bancari ultimi 90 giorni con causale F24
        data_limite = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        movimenti_banca = await db.prima_nota_banca.find({
            "data": {"$gte": data_limite},
            "descrizione": {"$regex": "F24|tribut|erariale", "$options": "i"},
            "tipo": "uscita",
            "riconciliato": {"$ne": True}
        }).to_list(1000)
        
        for f24 in f24_non_pagati:
            importo_f24 = abs(f24.get("importo_totale", 0))
            scadenza_f24 = f24.get("scadenza", "")
            
            # Cerca movimento bancario con importo simile e data vicina
            for movimento in movimenti_banca:
                importo_movimento = abs(movimento.get("importo", 0))
                data_movimento = movimento.get("data", "")
                
                # Match importo (tolleranza 2 euro)
                if abs(importo_f24 - importo_movimento) <= 2.0:
                    # Riconcilia
                    result = await riconcilia_f24_con_banca(
                        db, username, 
                        f24.get("id"), 
                        movimento.get("id")
                    )
                    
                    if result.get("success"):
                        riconciliati += 1
                        # Marca movimento come riconciliato
                        await db.prima_nota_banca.update_one(
                            {"id": movimento.get("id")},
                            {"$set": {"riconciliato": True, "f24_id": f24.get("id")}}
                        )
                        break
                    else:
                        errori += 1
        
        logger.info(f"✅ Auto-riconciliazione completata: {riconciliati} F24 riconciliati, {errori} errori")
        
        return {
            "riconciliati": riconciliati,
            "errori": errori,
            "message": f"Riconciliati {riconciliati} F24 con movimenti bancari"
        }
        
    except Exception as e:
        logger.error(f"Errore auto-riconciliazione: {str(e)}")
        return {"riconciliati": 0, "errori": 1, "message": str(e)}


async def get_f24_dashboard(db, username: str, month_year: str = None) -> Dict:
    """
    Dashboard F24: riepilogo codici tributo pagati/non pagati
    """
    from datetime import datetime
    from collections import defaultdict
    
    try:
        query = {"user_id": username}
        if month_year:
            query["mese_riferimento"] = {"$regex": f"^{month_year}"}
        
        # Fetch tutti F24
        all_f24 = await db.f24.find(query).to_list(10000)
        
        # Raggruppa per status
        pagati = []
        non_pagati = []
        totale_pagato = 0.0
        totale_non_pagato = 0.0
        
        codici_tributo_pagati = defaultdict(lambda: {"count": 0, "totale": 0.0, "descrizione": ""})
        codici_tributo_non_pagati = defaultdict(lambda: {"count": 0, "totale": 0.0, "descrizione": ""})
        
        for f24 in all_f24:
            importo = f24.get("importo_totale", 0)
            codici = f24.get("codici_tributo", [])
            is_paid = f24.get("status") == "paid"
            
            if is_paid:
                pagati.append(f24)
                totale_pagato += importo
                
                for codice_data in codici:
                    codice = codice_data.get("codice", "")
                    importo_codice = codice_data.get("importo", 0)
                    desc = codice_data.get("descrizione", codice)
                    
                    codici_tributo_pagati[codice]["count"] += 1
                    codici_tributo_pagati[codice]["totale"] += importo_codice
                    codici_tributo_pagati[codice]["descrizione"] = desc
            else:
                non_pagati.append(f24)
                totale_non_pagato += importo
                
                for codice_data in codici:
                    codice = codice_data.get("codice", "")
                    importo_codice = codice_data.get("importo", 0)
                    desc = codice_data.get("descrizione", codice)
                    
                    codici_tributo_non_pagati[codice]["count"] += 1
                    codici_tributo_non_pagati[codice]["totale"] += importo_codice
                    codici_tributo_non_pagati[codice]["descrizione"] = desc
        
        # Converti defaultdict a dict normale per JSON
        return {
            "totale_f24": len(all_f24),
            "f24_pagati": len(pagati),
            "f24_non_pagati": len(non_pagati),
            "importo_totale_pagato": round(totale_pagato, 2),
            "importo_totale_non_pagato": round(totale_non_pagato, 2),
            "codici_tributo_pagati": {
                k: {
                    "count": v["count"],
                    "totale": round(v["totale"], 2),
                    "descrizione": v["descrizione"]
                }
                for k, v in codici_tributo_pagati.items()
            },
            "codici_tributo_non_pagati": {
                k: {
                    "count": v["count"],
                    "totale": round(v["totale"], 2),
                    "descrizione": v["descrizione"]
                }
                for k, v in codici_tributo_non_pagati.items()
            },
            "alert_attivi": len([f for f in non_pagati if (datetime.fromisoformat(f.get("scadenza", datetime.now().isoformat()).replace("Z", "+00:00")).date() - datetime.now().date()).days <= 7])
        }
        
    except Exception as e:
        logger.error(f"Errore dashboard F24: {str(e)}")
        return {
            "totale_f24": 0,
            "f24_pagati": 0,
            "f24_non_pagati": 0,
            "importo_totale_pagato": 0.0,
            "importo_totale_non_pagato": 0.0,
            "codici_tributo_pagati": {},
            "codici_tributo_non_pagati": {},
            "alert_attivi": 0
        }

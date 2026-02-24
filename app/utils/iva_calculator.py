"""
Sistema Calcolo IVA - Debito/Credito/Saldo
IVA Debito: da Corrispettivi (vendite)
IVA Credito: da Fatture (acquisti)
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging
import calendar

logger = logging.getLogger(__name__)


async def calculate_daily_iva(db, date_str: str) -> Dict[str, Any]:
    """
    Calcola IVA giornaliera.
    
    IVA DEBITO = somma "totale_iva" da corrispettivi del giorno
    IVA CREDITO = somma IVA scorporata da fatture del giorno
    SALDO = DEBITO - CREDITO
    
    Args:
        db: Database connection
        date_str: Data in formato YYYY-MM-DD
        
    Returns:
        Dict con iva_debito, iva_credito, saldo, dettagli
    """
    result = {
        "data": date_str,
        "iva_debito": 0.0,
        "iva_credito": 0.0,
        "saldo": 0.0,
        "stato": "",
        "corrispettivi": {
            "count": 0,
            "items": [],
            "by_aliquota": {}
        },
        "fatture": {
            "count": 0,
            "items": [],
            "totale_fatturato": 0.0
        }
    }
    
    try:
        # ========== IVA DEBITO (da Corrispettivi) ==========
        corrispettivi = await db["corrispettivi"].find({
            "data": date_str
        }, {"_id": 0}).to_list(100)
        
        for corr in corrispettivi:
            iva = float(corr.get("totale_iva", 0) or 0)
            result["iva_debito"] += iva
            
            # Dettaglio corrispettivo
            result["corrispettivi"]["items"].append({
                "matricola_rt": corr.get("matricola_rt", ""),
                "imponibile": float(corr.get("totale_imponibile", 0) or corr.get("totale_corrispettivi", 0) or 0) - iva,
                "imposta": iva,
                "totale": float(corr.get("totale", 0) or 0),
                "contanti": float(corr.get("pagato_contanti", 0) or 0),
                "elettronico": float(corr.get("pagato_elettronico", 0) or 0),
                "documenti": int(corr.get("numero_documenti", 0) or 0)
            })
            
            # Riepilogo per aliquota
            for riep in corr.get("riepilogo_iva", []):
                aliquota = riep.get("aliquota_iva", "0")
                if aliquota not in result["corrispettivi"]["by_aliquota"]:
                    result["corrispettivi"]["by_aliquota"][aliquota] = {
                        "imponibile": 0.0,
                        "imposta": 0.0
                    }
                result["corrispettivi"]["by_aliquota"][aliquota]["imponibile"] += float(riep.get("ammontare", 0) or 0)
                result["corrispettivi"]["by_aliquota"][aliquota]["imposta"] += float(riep.get("imposta", 0) or 0)
        
        result["corrispettivi"]["count"] = len(corrispettivi)
        
        # ========== IVA CREDITO (da Fatture) ==========
        fatture = await db["invoices"].find({
            "invoice_date": date_str
        }, {"_id": 0}).to_list(1000)
        
        for fatt in fatture:
            # Calcola IVA dalla fattura
            iva_fattura = 0.0
            totale_fattura = float(fatt.get("total_amount", 0) or 0)
            
            # Se abbiamo le linee prodotto, calcola IVA per ogni riga
            linee = fatt.get("linee", [])
            if linee:
                for linea in linee:
                    prezzo_totale = float(linea.get("prezzo_totale", 0) or 0)
                    aliquota = float(linea.get("aliquota_iva", 22) or 22)
                    
                    if prezzo_totale > 0 and aliquota > 0:
                        # Scorporo IVA: IVA = prezzo_totale - (prezzo_totale / (1 + aliquota/100))
                        imponibile = prezzo_totale / (1 + aliquota / 100)
                        iva_linea = prezzo_totale - imponibile
                        iva_fattura += iva_linea
            else:
                # Fallback: stima IVA 22% sul totale
                iva_fattura = totale_fattura - (totale_fattura / 1.22)
            
            result["iva_credito"] += iva_fattura
            result["fatture"]["totale_fatturato"] += totale_fattura
            
            result["fatture"]["items"].append({
                "numero": fatt.get("invoice_number", ""),
                "fornitore": fatt.get("supplier_name", ""),
                "totale": totale_fattura,
                "iva": round(iva_fattura, 2)
            })
        
        result["fatture"]["count"] = len(fatture)
        
        # ========== SALDO ==========
        result["iva_debito"] = round(result["iva_debito"], 2)
        result["iva_credito"] = round(result["iva_credito"], 2)
        result["saldo"] = round(result["iva_debito"] - result["iva_credito"], 2)
        
        if result["saldo"] > 0:
            result["stato"] = "Da versare"
        elif result["saldo"] < 0:
            result["stato"] = "A credito"
        else:
            result["stato"] = "Pareggio"
            
    except Exception as e:
        logger.error(f"Errore calcolo IVA giornaliera: {e}")
        result["error"] = str(e)
    
    return result


async def calculate_monthly_progressive_iva(db, year: int, month: int) -> Dict[str, Any]:
    """
    Calcola IVA progressiva giorno per giorno per un mese.
    """
    result = {
        "anno": year,
        "mese": month,
        "giorni": [],
        "totali": {
            "iva_debito": 0.0,
            "iva_credito": 0.0,
            "saldo": 0.0
        }
    }
    
    try:
        # Numero giorni del mese
        _, days_in_month = calendar.monthrange(year, month)
        
        progressiva = 0.0
        
        for day in range(1, days_in_month + 1):
            date_str = f"{year}-{month:02d}-{day:02d}"
            
            daily = await calculate_daily_iva(db, date_str)
            
            progressiva += daily["saldo"]
            
            result["giorni"].append({
                "giorno": day,
                "data": date_str,
                "iva_debito": daily["iva_debito"],
                "iva_credito": daily["iva_credito"],
                "saldo": daily["saldo"],
                "progressiva": round(progressiva, 2)
            })
            
            result["totali"]["iva_debito"] += daily["iva_debito"]
            result["totali"]["iva_credito"] += daily["iva_credito"]
        
        result["totali"]["iva_debito"] = round(result["totali"]["iva_debito"], 2)
        result["totali"]["iva_credito"] = round(result["totali"]["iva_credito"], 2)
        result["totali"]["saldo"] = round(result["totali"]["iva_debito"] - result["totali"]["iva_credito"], 2)
        
    except Exception as e:
        logger.error(f"Errore calcolo IVA progressiva: {e}")
        result["error"] = str(e)
    
    return result


async def calculate_annual_iva_report(db, year: int) -> Dict[str, Any]:
    """
    Calcola riepilogo IVA annuale (12 mesi).
    """
    mesi_nomi = [
        "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
        "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"
    ]
    
    result = {
        "anno": year,
        "mesi": [],
        "totale_annuo": {
            "iva_debito": 0.0,
            "iva_credito": 0.0,
            "saldo": 0.0
        }
    }
    
    try:
        for month in range(1, 13):
            # Calcola totali per il mese usando aggregazione diretta
            month_start = f"{year}-{month:02d}-01"
            _, last_day = calendar.monthrange(year, month)
            month_end = f"{year}-{month:02d}-{last_day}"
            
            # IVA Debito da corrispettivi
            corr_pipeline = [
                {"$match": {"data": {"$gte": month_start, "$lte": month_end}}},
                {"$group": {"_id": None, "totale_iva": {"$sum": "$totale_iva"}}}
            ]
            corr_result = await db["corrispettivi"].aggregate(corr_pipeline).to_list(1)
            iva_debito = corr_result[0]["totale_iva"] if corr_result else 0
            
            # IVA Credito da fatture (stima 22%)
            fatt_pipeline = [
                {"$match": {"invoice_date": {"$gte": month_start, "$lte": month_end}}},
                {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}
            ]
            fatt_result = await db["invoices"].aggregate(fatt_pipeline).to_list(1)
            totale_fatture = fatt_result[0]["totale"] if fatt_result else 0
            iva_credito = totale_fatture - (totale_fatture / 1.22) if totale_fatture > 0 else 0
            
            saldo = iva_debito - iva_credito
            
            result["mesi"].append({
                "mese": month,
                "nome": mesi_nomi[month - 1],
                "iva_debito": round(iva_debito, 2),
                "iva_credito": round(iva_credito, 2),
                "saldo": round(saldo, 2),
                "stato": "Da versare" if saldo > 0 else ("A credito" if saldo < 0 else "Pareggio")
            })
            
            result["totale_annuo"]["iva_debito"] += iva_debito
            result["totale_annuo"]["iva_credito"] += iva_credito
        
        result["totale_annuo"]["iva_debito"] = round(result["totale_annuo"]["iva_debito"], 2)
        result["totale_annuo"]["iva_credito"] = round(result["totale_annuo"]["iva_credito"], 2)
        result["totale_annuo"]["saldo"] = round(
            result["totale_annuo"]["iva_debito"] - result["totale_annuo"]["iva_credito"], 2
        )
        
    except Exception as e:
        logger.error(f"Errore calcolo IVA annuale: {e}")
        result["error"] = str(e)
    
    return result


async def save_supplier_payment_method(db, supplier_vat: str, supplier_name: str, payment_method: str, username: str = "system") -> bool:
    """
    Salva metodo pagamento nel dizionario persistente.
    Questo metodo NON viene mai perso anche se il fornitore viene eliminato.
    """
    if not supplier_vat:
        logger.error("❌ ERRORE: supplier_vat vuoto")
        return False
    
    try:
        now = datetime.now(timezone.utc).isoformat()
        
        # Upsert nel dizionario principale
        await db["supplier_payment_methods"].update_one(
            {"supplier_vat": supplier_vat},
            {
                "$set": {
                    "supplier_name": supplier_name,
                    "payment_method": payment_method,
                    "updated_at": now,
                    "updated_by": username
                },
                "$setOnInsert": {
                    "created_at": now
                }
            },
            upsert=True
        )
        
        # Backup nello storico
        history_doc = {
            "supplier_vat": supplier_vat,
            "supplier_name": supplier_name,
            "payment_method": payment_method,
            "changed_at": now,
            "changed_by": username,
            "action": "upsert"
        }
        await db["supplier_payment_history"].insert_one(history_doc.copy())
        
        logger.info(f"✅ DIZIONARIO: Salvato {supplier_name} ({supplier_vat}) → {payment_method}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Errore salvataggio dizionario pagamenti: {e}")
        return False


async def get_supplier_payment_method(db, supplier_vat: str) -> Optional[str]:
    """
    Recupera metodo pagamento dal dizionario persistente.
    """
    if not supplier_vat:
        return None
    
    try:
        entry = await db["supplier_payment_methods"].find_one(
            {"supplier_vat": supplier_vat},
            {"_id": 0, "payment_method": 1}
        )
        
        if entry:
            logger.info(f"📖 DIZIONARIO: Trovato {supplier_vat} → {entry.get('payment_method')}")
            return entry.get("payment_method")
        
        return None
        
    except Exception as e:
        logger.error(f"Errore lettura dizionario pagamenti: {e}")
        return None


async def get_payment_dictionary(db) -> List[Dict[str, Any]]:
    """
    Restituisce tutto il dizionario metodi pagamento.
    """
    try:
        entries = await db["supplier_payment_methods"].find({}, {"_id": 0}).to_list(10000)
        return entries
    except Exception as e:
        logger.error(f"Errore lettura dizionario: {e}")
        return []


async def get_payment_dictionary_stats(db) -> Dict[str, Any]:
    """
    Statistiche sul dizionario metodi pagamento.
    """
    try:
        total = await db["supplier_payment_methods"].count_documents({})
        
        # Raggruppamento per metodo
        pipeline = [
            {"$group": {"_id": "$payment_method", "count": {"$sum": 1}}}
        ]
        by_method = await db["supplier_payment_methods"].aggregate(pipeline).to_list(10)
        
        by_method_dict = {item["_id"]: item["count"] for item in by_method if item["_id"]}
        
        return {
            "total_entries": total,
            "by_payment_method": by_method_dict
        }
        
    except Exception as e:
        logger.error(f"Errore stats dizionario: {e}")
        return {"error": str(e)}

"""
Learning Machine Universale - Backend
Apprende pattern da tutti i dati dell'applicazione:
- Fatture (pattern fornitori, date pagamento)
- Cedolini (costi ricorrenti)
- F24 (scadenze fiscali)
- Corrispettivi (stagionalità vendite)
- Assegni (associazioni automatiche)
- Movimenti bancari (categorizzazione)
"""

from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import re
from app.database import Database

router = APIRouter()

# ============== HELPER FUNCTIONS ==============

def extract_patterns_from_text(text: str) -> List[str]:
    """Estrae pattern significativi da un testo"""
    if not text:
        return []
    patterns = []
    # Rimuovi numeri e caratteri speciali, mantieni parole significative
    words = re.findall(r'[A-Za-z]{3,}', text.upper())
    patterns.extend(words[:5])  # Max 5 parole chiave
    return patterns

def calculate_payment_pattern(dates: List[str]) -> Dict[str, Any]:
    """Calcola il pattern di pagamento da una lista di date"""
    if not dates or len(dates) < 2:
        return {"type": "unknown", "confidence": 0}
    
    try:
        parsed_dates = []
        for d in dates:
            if isinstance(d, str):
                try:
                    parsed_dates.append(datetime.fromisoformat(d.replace('Z', '+00:00')))
                except Exception:
                    pass
            elif isinstance(d, datetime):
                parsed_dates.append(d)
        
        if len(parsed_dates) < 2:
            return {"type": "unknown", "confidence": 0}
        
        parsed_dates.sort()
        intervals = []
        for i in range(1, len(parsed_dates)):
            delta = (parsed_dates[i] - parsed_dates[i-1]).days
            if delta > 0:
                intervals.append(delta)
        
        if not intervals:
            return {"type": "unknown", "confidence": 0}
        
        avg_interval = sum(intervals) / len(intervals)
        
        # Determina il tipo di pattern
        if 25 <= avg_interval <= 35:
            return {"type": "mensile", "avg_days": round(avg_interval), "confidence": 0.9}
        elif 85 <= avg_interval <= 95:
            return {"type": "trimestrale", "avg_days": round(avg_interval), "confidence": 0.85}
        elif 360 <= avg_interval <= 370:
            return {"type": "annuale", "avg_days": round(avg_interval), "confidence": 0.8}
        elif 13 <= avg_interval <= 16:
            return {"type": "bisettimanale", "avg_days": round(avg_interval), "confidence": 0.85}
        else:
            return {"type": "irregolare", "avg_days": round(avg_interval), "confidence": 0.5}
    except Exception:
        return {"type": "unknown", "confidence": 0}


# ============== LEARNING ENDPOINTS ==============

@router.get("/status")
async def get_learning_status():
    """Stato generale del sistema di apprendimento"""
    db = Database.get_db()
    
    try:
        # Conta documenti per ogni collezione
        stats = {
            "fatture": await db.invoices.count_documents({}),
            "fornitori": await db["fornitori"].count_documents({}),
            "cedolini": await db["cedolini"].count_documents({}),
            "f24": await db.f24_payments.count_documents({}),
            "corrispettivi": await db.corrispettivi.count_documents({}),
            "assegni": await db.assegni.count_documents({}),
            "movimenti_banca": await db.movimenti_banca.count_documents({}),
            "bonifici": await db.bonifici.count_documents({}),
        }
        
        total = sum(stats.values())
        
        # Calcola stato apprendimento
        learning_progress = min(100, (total / 1000) * 100)  # 1000 docs = 100%
        
        return {
            "status": "ready" if total > 100 else "collecting_data",
            "total_documents": total,
            "collections": stats,
            "learning_progress": round(learning_progress, 1),
            "last_updated": datetime.utcnow().isoformat(),
            "capabilities": [
                "pattern_fornitori",
                "previsione_pagamenti",
                "categorizzazione_movimenti",
                "associazione_automatica",
                "analisi_stagionalita"
            ]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/train/all")
async def train_all_models():
    """Avvia l'apprendimento su tutti i dati"""
    db = Database.get_db()
    results = {
        "started_at": datetime.utcnow().isoformat(),
        "modules": {}
    }
    
    try:
        # 1. Apprendi pattern fornitori
        fornitori_patterns = await learn_supplier_patterns(db)
        results["modules"]["fornitori"] = fornitori_patterns
        
        # 2. Apprendi pattern pagamenti
        payment_patterns = await learn_payment_patterns(db)
        results["modules"]["pagamenti"] = payment_patterns
        
        # 3. Apprendi categorizzazione movimenti
        movement_patterns = await learn_movement_categories(db)
        results["modules"]["movimenti"] = movement_patterns
        
        # 4. Apprendi stagionalità corrispettivi
        seasonal_patterns = await learn_seasonal_patterns(db)
        results["modules"]["stagionalita"] = seasonal_patterns
        
        # 5. Apprendi associazioni assegni
        assegni_patterns = await learn_assegni_associations(db)
        results["modules"]["assegni"] = assegni_patterns
        
        # Salva risultati apprendimento - Converti chiavi None a stringa
        safe_results = {
            "started_at": results["started_at"],
            "modules": {}
        }
        
        for mod_name, mod_data in results["modules"].items():
            safe_mod = {}
            for k, v in mod_data.items():
                if isinstance(v, dict):
                    # Converti chiavi None in "unknown"
                    safe_mod[k] = {str(key) if key is not None else "unknown": val for key, val in v.items()}
                elif isinstance(v, list) and v and isinstance(v[0], tuple):
                    # Converti tuple a list per JSON
                    safe_mod[k] = [[str(item[0]) if item[0] is not None else "unknown", item[1]] for item in v]
                else:
                    safe_mod[k] = v
            safe_results["modules"][mod_name] = safe_mod
        
        await db.learning_results.update_one(
            {"_id": "latest"},
            {"$set": {
                **safe_results,
                "completed_at": datetime.utcnow().isoformat()
            }},
            upsert=True
        )
        
        results["status"] = "completed"
        results["completed_at"] = datetime.utcnow().isoformat()
        
    except Exception as e:
        results["status"] = "error"
        results["error"] = str(e)
    
    return results


async def learn_supplier_patterns(db) -> Dict:
    """Apprende pattern dai fornitori"""
    patterns = {
        "total_analyzed": 0,
        "patterns_found": 0,
        "top_categories": [],
        "payment_methods": {}
    }
    
    try:
        # Analizza fornitori
        suppliers = await db["fornitori"].find({}).to_list(1000)
        patterns["total_analyzed"] = len(suppliers)
        
        # Raggruppa per metodo pagamento
        payment_methods = defaultdict(int)
        categories = defaultdict(int)
        
        for s in suppliers:
            pm = s.get("metodo_pagamento", "non_specificato")
            payment_methods[pm] += 1
            
            # Estrai categoria dalla ragione sociale
            ragione = s.get("ragione_sociale", "")
            keywords = extract_patterns_from_text(ragione)
            for kw in keywords:
                categories[kw] += 1
        
        patterns["payment_methods"] = dict(payment_methods)
        patterns["top_categories"] = sorted(
            categories.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:20]
        patterns["patterns_found"] = len(patterns["top_categories"])
        
    except Exception as e:
        patterns["error"] = str(e)
    
    return patterns


async def learn_payment_patterns(db) -> Dict:
    """Apprende pattern di pagamento dalle fatture"""
    patterns = {
        "total_analyzed": 0,
        "patterns_found": 0,
        "avg_payment_days": 0,
        "by_supplier": []
    }
    
    try:
        # Analizza fatture pagate
        invoices = await db.invoices.find({
            "stato": {"$in": ["pagata", "paid", "PAGATA"]}
        }).to_list(5000)
        
        patterns["total_analyzed"] = len(invoices)
        
        # Raggruppa per fornitore
        supplier_payments = defaultdict(list)
        payment_delays = []
        
        for inv in invoices:
            supplier_id = inv.get("fornitore_id") or inv.get("supplier_id")
            if supplier_id:
                date_doc = inv.get("data_documento") or inv.get("data_fattura")
                date_pay = inv.get("data_pagamento")
                
                if date_doc and date_pay:
                    try:
                        d1 = datetime.fromisoformat(str(date_doc).replace('Z', ''))
                        d2 = datetime.fromisoformat(str(date_pay).replace('Z', ''))
                        delay = (d2 - d1).days
                        if 0 <= delay <= 365:
                            payment_delays.append(delay)
                            supplier_payments[supplier_id].append(delay)
                    except Exception:
                        pass
        
        if payment_delays:
            patterns["avg_payment_days"] = round(sum(payment_delays) / len(payment_delays), 1)
        
        # Top fornitori con pattern consistenti
        supplier_stats = []
        for sup_id, delays in supplier_payments.items():
            if len(delays) >= 3:
                avg = sum(delays) / len(delays)
                supplier_stats.append({
                    "supplier_id": sup_id,
                    "avg_days": round(avg, 1),
                    "count": len(delays),
                    "consistency": round(1 - (max(delays) - min(delays)) / (avg + 1), 2) if avg > 0 else 0
                })
        
        patterns["by_supplier"] = sorted(
            supplier_stats, 
            key=lambda x: x["count"], 
            reverse=True
        )[:50]
        patterns["patterns_found"] = len(patterns["by_supplier"])
        
    except Exception as e:
        patterns["error"] = str(e)
    
    return patterns


async def learn_movement_categories(db) -> Dict:
    """Apprende categorizzazione movimenti bancari"""
    patterns = {
        "total_analyzed": 0,
        "categories_found": 0,
        "keywords": {},
        "rules": []
    }
    
    try:
        # Analizza movimenti bancari
        movements = await db.movimenti_banca.find({}).to_list(5000)
        patterns["total_analyzed"] = len(movements)
        
        # Estrai keyword per categoria
        category_keywords = defaultdict(lambda: defaultdict(int))
        
        for mov in movements:
            desc = mov.get("descrizione", "") or mov.get("causale", "")
            categoria = mov.get("categoria") or mov.get("category")
            
            if desc and categoria:
                keywords = extract_patterns_from_text(desc)
                for kw in keywords:
                    category_keywords[categoria][kw] += 1
        
        # Genera regole
        rules = []
        for cat, keywords in category_keywords.items():
            top_keywords = sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:5]
            if top_keywords:
                rules.append({
                    "category": cat,
                    "keywords": [k[0] for k in top_keywords],
                    "confidence": min(1.0, top_keywords[0][1] / 10)
                })
        
        patterns["rules"] = rules
        patterns["categories_found"] = len(rules)
        
        # Keyword più frequenti globali
        all_keywords = defaultdict(int)
        for mov in movements:
            desc = mov.get("descrizione", "") or mov.get("causale", "")
            for kw in extract_patterns_from_text(desc):
                all_keywords[kw] += 1
        
        patterns["keywords"] = dict(sorted(
            all_keywords.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:50])
        
    except Exception as e:
        patterns["error"] = str(e)
    
    return patterns


async def learn_seasonal_patterns(db) -> Dict:
    """Apprende stagionalità dai corrispettivi"""
    patterns = {
        "total_analyzed": 0,
        "monthly_averages": {},
        "trend": "stable",
        "peak_months": [],
        "low_months": []
    }
    
    try:
        # Analizza corrispettivi
        corrispettivi = await db.corrispettivi.find({}).to_list(5000)
        patterns["total_analyzed"] = len(corrispettivi)
        
        # Raggruppa per mese
        monthly_totals = defaultdict(list)
        
        for c in corrispettivi:
            data = c.get("data") or c.get("data_corrispettivo")
            importo = c.get("importo") or c.get("totale") or 0
            
            if data and importo:
                try:
                    if isinstance(data, str):
                        dt = datetime.fromisoformat(data.replace('Z', ''))
                    else:
                        dt = data
                    month = dt.month
                    monthly_totals[month].append(float(importo))
                except Exception:
                    pass
        
        # Calcola medie mensili
        monthly_avg = {}
        for month, values in monthly_totals.items():
            if values:
                monthly_avg[month] = round(sum(values) / len(values), 2)
        
        patterns["monthly_averages"] = monthly_avg
        
        if monthly_avg:
            avg_all = sum(monthly_avg.values()) / len(monthly_avg)
            patterns["peak_months"] = [m for m, v in monthly_avg.items() if v > avg_all * 1.2]
            patterns["low_months"] = [m for m, v in monthly_avg.items() if v < avg_all * 0.8]
            
            # Determina trend
            if len(patterns["peak_months"]) > len(patterns["low_months"]):
                patterns["trend"] = "growing"
            elif len(patterns["low_months"]) > len(patterns["peak_months"]):
                patterns["trend"] = "declining"
        
    except Exception as e:
        patterns["error"] = str(e)
    
    return patterns


async def learn_assegni_associations(db) -> Dict:
    """Apprende associazioni assegni-fatture"""
    patterns = {
        "total_analyzed": 0,
        "associations_found": 0,
        "success_rate": 0,
        "common_patterns": []
    }
    
    try:
        # Analizza assegni
        assegni = await db.assegni.find({}).to_list(1000)
        patterns["total_analyzed"] = len(assegni)
        
        associated = 0
        beneficiary_patterns = defaultdict(int)
        
        for a in assegni:
            if a.get("fattura_id") or a.get("invoice_id"):
                associated += 1
            
            beneficiario = a.get("beneficiario", "")
            if beneficiario:
                keywords = extract_patterns_from_text(beneficiario)
                for kw in keywords:
                    beneficiary_patterns[kw] += 1
        
        patterns["associations_found"] = associated
        patterns["success_rate"] = round(associated / len(assegni) * 100, 1) if assegni else 0
        
        patterns["common_patterns"] = sorted(
            beneficiary_patterns.items(),
            key=lambda x: x[1],
            reverse=True
        )[:20]
        
    except Exception as e:
        patterns["error"] = str(e)
    
    return patterns


@router.get("/results")
async def get_learning_results():
    """Recupera i risultati dell'ultimo apprendimento"""
    db = Database.get_db()
    
    try:
        result = await db.learning_results.find_one({"_id": "latest"})
        if result:
            result.pop("_id", None)
            return result
        return {"status": "no_results", "message": "Nessun apprendimento completato"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suggestions/{module}")
async def get_suggestions(module: str):
    """Ottiene suggerimenti basati sull'apprendimento"""
    db = Database.get_db()
    
    try:
        result = await db.learning_results.find_one({"_id": "latest"})
        if not result:
            return {"suggestions": [], "message": "Esegui prima il training"}
        
        suggestions = []
        
        if module == "fatture":
            # Suggerimenti per fatture
            payment_data = result.get("modules", {}).get("pagamenti", {})
            for sup in payment_data.get("by_supplier", [])[:10]:
                suggestions.append({
                    "type": "payment_reminder",
                    "supplier_id": sup["supplier_id"],
                    "message": f"Fornitore paga mediamente in {sup['avg_days']} giorni",
                    "confidence": sup.get("consistency", 0.5)
                })
        
        elif module == "movimenti":
            # Suggerimenti per categorizzazione movimenti
            movement_data = result.get("modules", {}).get("movimenti", {})
            for rule in movement_data.get("rules", [])[:10]:
                suggestions.append({
                    "type": "category_rule",
                    "category": rule["category"],
                    "keywords": rule["keywords"],
                    "message": f"Movimenti con '{', '.join(rule['keywords'][:3])}' → {rule['category']}",
                    "confidence": rule.get("confidence", 0.5)
                })
        
        elif module == "corrispettivi":
            # Suggerimenti stagionalità
            seasonal_data = result.get("modules", {}).get("stagionalita", {})
            if seasonal_data.get("peak_months"):
                suggestions.append({
                    "type": "seasonal_peak",
                    "months": seasonal_data["peak_months"],
                    "message": f"Mesi di picco: {seasonal_data['peak_months']}",
                    "confidence": 0.8
                })
            if seasonal_data.get("low_months"):
                suggestions.append({
                    "type": "seasonal_low",
                    "months": seasonal_data["low_months"],
                    "message": f"Mesi deboli: {seasonal_data['low_months']}",
                    "confidence": 0.8
                })
        
        elif module == "assegni":
            # Suggerimenti associazioni
            assegni_data = result.get("modules", {}).get("assegni", {})
            for pattern, count in assegni_data.get("common_patterns", [])[:10]:
                suggestions.append({
                    "type": "beneficiary_pattern",
                    "pattern": pattern,
                    "count": count,
                    "message": f"Pattern beneficiario frequente: {pattern} ({count}x)",
                    "confidence": min(1.0, count / 20)
                })
        
        return {
            "module": module,
            "suggestions": suggestions,
            "count": len(suggestions)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply-suggestions")
async def apply_suggestions(data: Dict[str, Any]):
    """Applica i suggerimenti dell'apprendimento"""
    db = Database.get_db()
    module = data.get("module")
    suggestion_ids = data.get("suggestion_ids", [])
    
    applied = 0
    errors = []
    
    try:
        result = await db.learning_results.find_one({"_id": "latest"})
        if not result:
            return {"applied": 0, "message": "Nessun apprendimento disponibile"}
        
        if module == "movimenti":
            # Applica regole di categorizzazione
            movement_data = result.get("modules", {}).get("movimenti", {})
            rules = movement_data.get("rules", [])
            
            for rule in rules:
                category = rule.get("category")
                keywords = rule.get("keywords", [])
                
                if keywords and category:
                    # Trova movimenti non categorizzati che matchano
                    for kw in keywords:
                        query = {
                            "categoria": {"$exists": False},
                            "$or": [
                                {"descrizione": {"$regex": kw, "$options": "i"}},
                                {"causale": {"$regex": kw, "$options": "i"}}
                            ]
                        }
                        update_result = await db.movimenti_banca.update_many(
                            query,
                            {"$set": {"categoria": category, "auto_categorized": True}}
                        )
                        applied += update_result.modified_count
        
        return {
            "applied": applied,
            "errors": errors,
            "message": f"Applicati {applied} suggerimenti"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

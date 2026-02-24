"""
Gestione Codici Tributari - Sistema di Riconciliazione a 3 Vie

Questo modulo implementa il sistema di tracciamento pagamenti F24 basato su:
1. LIVELLO 1: F24 ricevuto dal commercialista (email)
2. LIVELLO 2: Pagamento in banca
3. LIVELLO 3: Quietanza dal cassetto fiscale (PDF)

Permette di rispondere a domande tipo: "Ho pagato il codice 1001 per l'anno 2020?"
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional
import logging

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()

# Dizionario codici tributo italiani più comuni
CODICI_TRIBUTO_INFO = {
    "1001": {"nome": "Ritenute IRPEF dipendenti", "categoria": "IRPEF"},
    "1040": {"nome": "Ritenute IRPEF autonomi", "categoria": "IRPEF"},
    "1631": {"nome": "Credito d'imposta art. 3 DL 73/2021", "categoria": "Credito"},
    "1627": {"nome": "Eccedenza versamenti IRPEF", "categoria": "Credito"},
    "1701": {"nome": "Addizionale regionale IRPEF", "categoria": "Addizionali"},
    "1704": {"nome": "Imposta sostitutiva TFR", "categoria": "TFR"},
    "3797": {"nome": "Addizionale comunale IRPEF", "categoria": "Addizionali"},
    "3802": {"nome": "Addizionale regionale all'IRPEF - Saldo", "categoria": "Addizionali"},
    "DM10": {"nome": "Contributi INPS", "categoria": "INPS"},
    "CXX": {"nome": "Contributi INPS cassetto", "categoria": "INPS"},
    "RC01": {"nome": "Contributi INAIL", "categoria": "INAIL"},
    "8947": {"nome": "Ravvedimento operoso", "categoria": "Ravvedimento"},
    "8950": {"nome": "Interessi ravvedimento operoso", "categoria": "Ravvedimento"},
    "9001": {"nome": "Somme iscritte a ruolo", "categoria": "Ruoli"},
    "8918": {"nome": "IRES - Sanzione", "categoria": "Sanzioni"},
}


@router.get("/codici-tributo/lista")
async def get_lista_codici_tributo() -> Dict[str, Any]:
    """Restituisce la lista di tutti i codici tributo trovati nelle quietanze F24."""
    db = Database.get_db()
    
    try:
        # Aggrega tutti i codici tributo univoci dalle quietanze
        pipeline = [
            {"$unwind": "$codici_tributo"},
            {"$group": {
                "_id": "$codici_tributo",
                "occorrenze": {"$sum": 1},
                "ultimo_pagamento": {"$max": "$data_pagamento"}
            }},
            {"$sort": {"occorrenze": -1}}
        ]
        
        codici = await db["quietanze_f24"].aggregate(pipeline).to_list(500)
        
        # Arricchisci con informazioni aggiuntive
        result = []
        for c in codici:
            codice = c["_id"]
            info = CODICI_TRIBUTO_INFO.get(codice, {"nome": "Codice non mappato", "categoria": "Altro"})
            result.append({
                "codice": codice,
                "nome": info["nome"],
                "categoria": info["categoria"],
                "occorrenze": c["occorrenze"],
                "ultimo_pagamento": c["ultimo_pagamento"]
            })
        
        return {
            "success": True,
            "codici": result,
            "totale": len(result)
        }
    except Exception as e:
        logger.error(f"Errore lista codici tributo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/codici-tributo/stato/{codice}")
async def get_stato_codice_tributo(
    codice: str,
    anno: Optional[int] = Query(None, description="Anno di riferimento (es: 2024)"),
    periodo: Optional[str] = Query(None, description="Periodo specifico (es: 01/2024 o 2024)")
) -> Dict[str, Any]:
    """
    Verifica lo stato di pagamento di un codice tributo specifico.
    
    Risponde a domande tipo: "Ho pagato il codice 1001 per il 2024?"
    
    Args:
        codice: Codice tributo (es: 1001, 3802, DM10)
        anno: Anno di riferimento (opzionale)
        periodo: Periodo specifico MM/YYYY o YYYY (opzionale)
    """
    db = Database.get_db()
    
    try:
        # Costruisci query per cercare nelle sezioni
        match_filters = {"codici_tributo": codice}
        
        quietanze = await db["quietanze_f24"].find(match_filters).to_list(1000)
        
        # Filtra per periodo se specificato
        pagamenti = []
        for q in quietanze:
            # Cerca in tutte le sezioni
            for sezione in ["sezione_erario", "sezione_inps", "sezione_regioni", "sezione_tributi_locali", "sezione_inail"]:
                tributi = q.get(sezione, [])
                for t in tributi:
                    if t.get("codice_tributo") == codice:
                        periodo_rif = t.get("periodo_riferimento", "")
                        
                        # Filtra per anno/periodo se specificato
                        if anno:
                            if str(anno) not in periodo_rif:
                                continue
                        if periodo:
                            if periodo not in periodo_rif and periodo_rif != periodo:
                                continue
                        
                        pagamenti.append({
                            "data_pagamento": q.get("data_pagamento"),
                            "periodo_riferimento": periodo_rif,
                            "importo_debito": t.get("importo_debito", 0),
                            "importo_credito": t.get("importo_credito", 0),
                            "protocollo": q.get("protocollo_telematico"),
                            "quietanza_id": str(q.get("_id")),
                            "descrizione": t.get("descrizione", CODICI_TRIBUTO_INFO.get(codice, {}).get("nome", ""))
                        })
        
        # ORDINA PER DATA PAGAMENTO (più recenti prima)
        pagamenti.sort(key=lambda x: x.get("data_pagamento") or "", reverse=True)
        
        # Calcola totali
        totale_debito = sum(p["importo_debito"] for p in pagamenti)
        totale_credito = sum(p["importo_credito"] for p in pagamenti)
        
        # Raggruppa per periodo
        periodi_pagati = {}
        for p in pagamenti:
            periodo_key = p["periodo_riferimento"]
            if periodo_key not in periodi_pagati:
                periodi_pagati[periodo_key] = {
                    "periodo": periodo_key,
                    "totale_debito": 0,
                    "totale_credito": 0,
                    "pagamenti": []
                }
            periodi_pagati[periodo_key]["totale_debito"] += p["importo_debito"]
            periodi_pagati[periodo_key]["totale_credito"] += p["importo_credito"]
            periodi_pagati[periodo_key]["pagamenti"].append(p)
        
        info_codice = CODICI_TRIBUTO_INFO.get(codice, {"nome": "Codice non mappato", "categoria": "Altro"})
        
        return {
            "success": True,
            "codice": codice,
            "nome": info_codice["nome"],
            "categoria": info_codice["categoria"],
            "filtri": {"anno": anno, "periodo": periodo},
            "riepilogo": {
                "totale_pagamenti": len(pagamenti),
                "totale_debito": round(totale_debito, 2),
                "totale_credito": round(totale_credito, 2),
                "saldo_netto": round(totale_debito - totale_credito, 2),
                "periodi_coperti": list(periodi_pagati.keys())
            },
            "dettaglio_periodi": list(periodi_pagati.values()),
            "pagamenti": pagamenti
        }
    except Exception as e:
        logger.error(f"Errore stato codice tributo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/codici-tributo/riconciliazione")
async def get_riconciliazione_f24(
    anno: int = Query(..., description="Anno di riferimento"),
    tipo: Optional[str] = Query(None, description="Tipo: erario, inps, regioni, locali, inail")
) -> Dict[str, Any]:
    """
    Verifica la riconciliazione a 3 vie per tutti i codici tributo di un anno.
    
    Mostra per ogni codice tributo:
    - Se è stato ricevuto dal commercialista (F24 email)
    - Se è stato pagato (estratto conto)
    - Se esiste quietanza (cassetto fiscale)
    """
    db = Database.get_db()
    
    try:
        # Cerca tutte le quietanze dell'anno
        quietanze = await db["quietanze_f24"].find({
            "$or": [
                {"data_pagamento": {"$regex": f"^{anno}"}},
                {"sezione_erario.periodo_riferimento": {"$regex": str(anno)}},
                {"sezione_inps.periodo_riferimento": {"$regex": str(anno)}}
            ]
        }).to_list(1000)
        
        # Costruisci mappa di riconciliazione
        riconciliazione = {}
        
        for q in quietanze:
            sezioni = []
            if tipo == "erario" or not tipo:
                sezioni.append(("erario", q.get("sezione_erario", [])))
            if tipo == "inps" or not tipo:
                sezioni.append(("inps", q.get("sezione_inps", [])))
            if tipo == "regioni" or not tipo:
                sezioni.append(("regioni", q.get("sezione_regioni", [])))
            if tipo == "locali" or not tipo:
                sezioni.append(("locali", q.get("sezione_tributi_locali", [])))
            if tipo == "inail" or not tipo:
                sezioni.append(("inail", q.get("sezione_inail", [])))
            
            for sezione_nome, tributi in sezioni:
                for t in tributi:
                    codice = t.get("codice_tributo")
                    periodo = t.get("periodo_riferimento", "")
                    
                    # Filtra per anno nel periodo
                    if str(anno) not in periodo:
                        continue
                    
                    key = f"{codice}_{periodo}"
                    if key not in riconciliazione:
                        info = CODICI_TRIBUTO_INFO.get(codice, {"nome": codice, "categoria": "Altro"})
                        riconciliazione[key] = {
                            "codice": codice,
                            "nome": info["nome"],
                            "categoria": info["categoria"],
                            "periodo": periodo,
                            "sezione": sezione_nome,
                            "livello_1_f24_email": False,  # TODO: collegare con email F24
                            "livello_2_pagamento_banca": False,  # TODO: collegare con estratto conto
                            "livello_3_quietanza": True,  # Abbiamo la quietanza
                            "importo_debito": 0,
                            "importo_credito": 0,
                            "data_pagamento": None,
                            "protocolli": []
                        }
                    
                    riconciliazione[key]["importo_debito"] += t.get("importo_debito", 0)
                    riconciliazione[key]["importo_credito"] += t.get("importo_credito", 0)
                    riconciliazione[key]["data_pagamento"] = q.get("data_pagamento")
                    if q.get("protocollo_telematico"):
                        riconciliazione[key]["protocolli"].append(q.get("protocollo_telematico"))
        
        # Raggruppa per categoria
        per_categoria = {}
        for item in riconciliazione.values():
            cat = item["categoria"]
            if cat not in per_categoria:
                per_categoria[cat] = []
            per_categoria[cat].append(item)
        
        # Calcola totali
        totale_debito = sum(r["importo_debito"] for r in riconciliazione.values())
        totale_credito = sum(r["importo_credito"] for r in riconciliazione.values())
        
        return {
            "success": True,
            "anno": anno,
            "tipo_filtro": tipo,
            "riepilogo": {
                "totale_codici": len(riconciliazione),
                "totale_debito": round(totale_debito, 2),
                "totale_credito": round(totale_credito, 2),
                "saldo_netto": round(totale_debito - totale_credito, 2),
                "categorie": list(per_categoria.keys())
            },
            "per_categoria": per_categoria,
            "dettaglio": list(riconciliazione.values())
        }
    except Exception as e:
        logger.error(f"Errore riconciliazione F24: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/codici-tributo/cerca")
async def cerca_codice_tributo(
    query: str = Query(..., description="Testo da cercare nel codice o nome"),
    anno: Optional[int] = Query(None, description="Anno di riferimento")
) -> Dict[str, Any]:
    """
    Cerca codici tributo per codice o descrizione.
    
    Es: "1001", "IRPEF", "ritenute"
    """
    db = Database.get_db()
    
    try:
        query_upper = query.upper()
        query_lower = query.lower()
        
        # Prima cerca nel dizionario locale
        matches_locali = []
        for codice, info in CODICI_TRIBUTO_INFO.items():
            if (query_upper in codice or 
                query_lower in info["nome"].lower() or 
                query_lower in info["categoria"].lower()):
                matches_locali.append({
                    "codice": codice,
                    "nome": info["nome"],
                    "categoria": info["categoria"],
                    "fonte": "dizionario"
                })
        
        # Poi cerca nelle quietanze
        pipeline = [
            {"$unwind": "$codici_tributo"},
            {"$match": {"codici_tributo": {"$regex": query_upper, "$options": "i"}}},
            {"$group": {
                "_id": "$codici_tributo",
                "occorrenze": {"$sum": 1}
            }}
        ]
        codici_db = await db["quietanze_f24"].aggregate(pipeline).to_list(100)
        
        for c in codici_db:
            codice = c["_id"]
            if not any(m["codice"] == codice for m in matches_locali):
                info = CODICI_TRIBUTO_INFO.get(codice, {"nome": codice, "categoria": "Altro"})
                matches_locali.append({
                    "codice": codice,
                    "nome": info["nome"],
                    "categoria": info["categoria"],
                    "fonte": "quietanze",
                    "occorrenze": c["occorrenze"]
                })
        
        return {
            "success": True,
            "query": query,
            "risultati": matches_locali,
            "totale": len(matches_locali)
        }
    except Exception as e:
        logger.error(f"Errore ricerca codice tributo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/codici-tributo/riepilogo-annuale/{anno}")
async def get_riepilogo_annuale_tributi(anno: int) -> Dict[str, Any]:
    """
    Riepilogo annuale di tutti i tributi pagati, raggruppati per categoria.
    
    Utile per la dichiarazione dei redditi e il controllo fiscale.
    """
    db = Database.get_db()
    
    try:
        # Cerca quietanze dell'anno
        quietanze = await db["quietanze_f24"].find({
            "data_pagamento": {"$regex": f"^{anno}"}
        }).to_list(1000)
        
        # Aggrega per categoria
        per_categoria = {
            "IRPEF": {"totale_debito": 0, "totale_credito": 0, "tributi": []},
            "INPS": {"totale_debito": 0, "totale_credito": 0, "tributi": []},
            "INAIL": {"totale_debito": 0, "totale_credito": 0, "tributi": []},
            "Addizionali": {"totale_debito": 0, "totale_credito": 0, "tributi": []},
            "TFR": {"totale_debito": 0, "totale_credito": 0, "tributi": []},
            "Credito": {"totale_debito": 0, "totale_credito": 0, "tributi": []},
            "Altro": {"totale_debito": 0, "totale_credito": 0, "tributi": []}
        }
        
        codici_visti = set()
        
        for q in quietanze:
            for sezione in ["sezione_erario", "sezione_inps", "sezione_regioni", "sezione_tributi_locali", "sezione_inail"]:
                for t in q.get(sezione, []):
                    codice = t.get("codice_tributo")
                    info = CODICI_TRIBUTO_INFO.get(codice, {"nome": codice, "categoria": "Altro"})
                    categoria = info["categoria"]
                    if categoria not in per_categoria:
                        categoria = "Altro"
                    
                    debito = t.get("importo_debito", 0)
                    credito = t.get("importo_credito", 0)
                    
                    per_categoria[categoria]["totale_debito"] += debito
                    per_categoria[categoria]["totale_credito"] += credito
                    
                    if codice not in codici_visti:
                        codici_visti.add(codice)
                        per_categoria[categoria]["tributi"].append({
                            "codice": codice,
                            "nome": info["nome"]
                        })
        
        # Calcola totali generali
        totale_debito = sum(c["totale_debito"] for c in per_categoria.values())
        totale_credito = sum(c["totale_credito"] for c in per_categoria.values())
        
        # Formatta per output
        riepilogo_categorie = []
        for nome, dati in per_categoria.items():
            if dati["totale_debito"] > 0 or dati["totale_credito"] > 0:
                riepilogo_categorie.append({
                    "categoria": nome,
                    "totale_debito": round(dati["totale_debito"], 2),
                    "totale_credito": round(dati["totale_credito"], 2),
                    "saldo": round(dati["totale_debito"] - dati["totale_credito"], 2),
                    "codici_tributo": dati["tributi"]
                })
        
        return {
            "success": True,
            "anno": anno,
            "totale_quietanze": len(quietanze),
            "riepilogo": {
                "totale_debito": round(totale_debito, 2),
                "totale_credito": round(totale_credito, 2),
                "saldo_netto": round(totale_debito - totale_credito, 2)
            },
            "per_categoria": riepilogo_categorie
        }
    except Exception as e:
        logger.error(f"Errore riepilogo annuale tributi: {e}")
        raise HTTPException(status_code=500, detail=str(e))
